#!/usr/bin/env python3
"""Offline validator for the B-FE7 deterministic HSPICE stimulus package.

The validator treats CSV files as the numerical source of truth and `.inc`
files as their HSPICE serialization.  The only electrical port accepted is
``V_VDD_MONITORED vdd_monitored vss_a``: the first node is the monitored
positive supply and the second is the local return.  No circuit simulation is
used; every assertion is a parser, arithmetic, or provenance check.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import generate_droop12_waveforms as generator  # noqa: E402


TOLERANCE_V = 2.0e-12
FORMAL_MINIMUM_V = 0.8
SOURCE_RE = re.compile(r"^V_VDD_MONITORED vdd_monitored vss_a PWL\($")
FORBIDDEN_TOKENS = ("ARCH0", "ARCH1", "bfe_backend_top", "LATQ", "DFF", "detector", "sensor")


def sha256_file(path):
    """Hash one artifact in streaming mode for the anti-drift manifest."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_csv(path):
    """Load one generated scenario CSV and normalize its SI fields."""

    with Path(path).open(newline="", encoding="ascii") as stream:
        rows = []
        for raw in csv.DictReader(stream):
            time_s = float(raw["time_s"])
            time_ps = int(round(time_s * 1.0e12))
            if abs(time_s - time_ps * 1.0e-12) > 1.0e-18:
                raise AssertionError("{} has non-integer-ps time".format(path))
            row = {"time_ps": time_ps, "noise_v": float(raw["noise_v"]),
                   "attack_depth_v": float(raw["attack_depth_v"]), "vdd_v": float(raw["vdd_v"])}
            if not all(math.isfinite(float(row[key])) for key in row):
                raise AssertionError("{} contains non-finite values".format(path))
            rows.append(row)
    if not rows or rows[0]["time_ps"] != 0 or rows[-1]["time_ps"] != generator.T_STOP_PS:
        raise AssertionError("{} has invalid endpoints".format(path))
    if any(right["time_ps"] <= left["time_ps"] for left, right in zip(rows, rows[1:])):
        raise AssertionError("{} time is not strictly increasing".format(path))
    return rows


def parse_inc(path):
    """Parse exactly one multiline HSPICE monitored-rail PWL source."""

    lines = Path(path).read_text(encoding="ascii").splitlines()
    source_lines = [line for line in lines if line.startswith("V_VDD_MONITORED ")]
    if len(source_lines) != 1 or not SOURCE_RE.match(source_lines[0]):
        raise AssertionError("{} violates monitored source contract".format(path))
    if sum("PWL(" in line for line in lines) != 1:
        raise AssertionError("{} must contain one PWL source".format(path))
    points = []
    in_pwl = False
    for line in lines:
        if SOURCE_RE.match(line):
            in_pwl = True
            continue
        if in_pwl and line.startswith("+"):
            fields = line[1:].strip().rstrip(")").split()
            if len(fields) != 2:
                raise AssertionError("{} has malformed PWL point".format(path))
            time_s, voltage_v = float(fields[0]), float(fields[1])
            time_ps = int(round(time_s * 1.0e12))
            if abs(time_s - time_ps * 1.0e-12) > 1.0e-18:
                raise AssertionError("{} has non-SI/integer-ps PWL time".format(path))
            points.append((time_ps, voltage_v))
    if not points or points[0][0] != 0 or points[-1][0] != generator.T_STOP_PS:
        raise AssertionError("{} PWL endpoints are invalid".format(path))
    if any(right[0] <= left[0] for left, right in zip(points, points[1:])):
        raise AssertionError("{} PWL time is not strictly increasing".format(path))
    return points


def _attack_value(points, time_ps):
    """Linearly evaluate an expected attack envelope at one time."""

    if time_ps < points[0][0] or time_ps > points[-1][0]:
        return 0.0
    for (left_t, left_v), (right_t, right_v) in zip(points, points[1:]):
        if left_t <= time_ps <= right_t:
            fraction = float(time_ps - left_t) / float(right_t - left_t)
            return left_v + fraction * (right_v - left_v)
    return 0.0


def _assert_scenario(record, rows, inc_points, background_rows):
    """Validate numerical, geometric, and HSPICE serialization invariants."""

    expected_points = [(int(point[0]), float(point[1])) for point in record["attack_breakpoints_ps"]]
    expected_map = {time: value for time, value in expected_points}
    bg_map = {row["time_ps"]: row["noise_v"] for row in background_rows}
    for row in rows:
        expected_attack = _attack_value(expected_points, row["time_ps"])
        assert abs(row["attack_depth_v"] - expected_attack) <= TOLERANCE_V
        expected_noise = generator.interpolate_noise(background_rows, row["time_ps"])
        assert abs(row["noise_v"] - expected_noise) <= TOLERANCE_V
        assert abs(row["vdd_v"] - (generator.V_NOM + row["noise_v"] - row["attack_depth_v"])) <= TOLERANCE_V
        assert row["vdd_v"] >= FORMAL_MINIMUM_V - TOLERANCE_V
    assert all(abs(row["noise_v"]) <= generator.BACKGROUND_LIMIT_V + TOLERANCE_V for row in rows)
    assert len(inc_points) == len(rows)
    for row, point in zip(rows, inc_points):
        assert row["time_ps"] == point[0]
        assert abs(row["vdd_v"] - point[1]) <= TOLERANCE_V
    # Every W2 attack breakpoint must survive the merge, including ramps and
    # plateau boundaries that are not present in the 250 ps background grid.
    actual_times = {row["time_ps"] for row in rows}
    assert set(expected_map).issubset(actual_times)


def _assert_special_geometry(records):
    """Check the plan's high-signal shape invariants without detector results."""

    by_id = {record["scenario_id"]: record for record in records}
    d10 = by_id["D10"]["attack_breakpoints_ps"]
    d11 = by_id["D11"]["attack_breakpoints_ps"]
    mirrored = sorted([[2 * 21000 - point[0], point[1]] for point in d10])
    assert mirrored == sorted(d11)
    for identifier, expected_count in (("D07", 2), ("D08", 4)):
        points = by_id[identifier]["attack_breakpoints_ps"]
        assert sum(value > 0.0 for _, value in points) >= expected_count
        starts = [time for index, (time, value) in enumerate(points)
                  if value > 0.0 and (index == 0 or points[index - 1][1] == 0.0)]
        assert len(starts) == expected_count
        assert all(right - left == 10000 for left, right in zip(starts, starts[1:]))
    d12 = by_id["D12"]["attack_breakpoints_ps"]
    assert _attack_value(d12, 21000) == 0.030
    assert _attack_value(d12, 31000) == 0.030


def build_manifest(root, contract_path, background_paths, artifact_paths):
    """Build the W4 hash manifest; figure hashes are added by W5 later."""

    files = {"contract": str(contract_path.relative_to(root)), "generator": str((root / "generate_droop12_waveforms.py").relative_to(root)),
             "validator": str((root / "validate_droop12_waveforms.py").relative_to(root))}
    files.update({"normal_background_csv": str(background_paths[0].relative_to(root)),
                  "normal_background_inc": str(background_paths[1].relative_to(root)),
                  "normal_background_metadata": str(background_paths[2].relative_to(root))})
    for path in artifact_paths:
        files[path.name] = str(path.relative_to(root))
    return {"schema_version": 1, "study": "B-FE7-DROOP12", "frozen": False,
            "files": {key: {"path": value, "sha256": sha256_file(root / value)} for key, value in sorted(files.items())},
            "figures": {}, "simulation_accounting": {"hspice_runs": 0, "vcs_runs": 0, "primesim_runs": 0, "dc_runs": 0, "arch0_tests": 0, "arch1_tests": 0}}


def validate_package(root):
    """Validate the complete W3 package and write the W4 manifest."""

    root = Path(root)
    contract_path = root / "DROOP12_WAVEFORM_CONTRACT.json"
    contract = json.loads(contract_path.read_text(encoding="ascii"))
    assert contract["frozen"] is True
    assert contract["nominal_vdd_v"] == 1.1 and contract["temperature_c"] == 25.0
    assert contract["time_frame"]["stop_s"] == 6.5e-8
    assert contract["background"]["seed"] == generator.SEED
    records = contract["scenarios"]
    assert len(records) == 12 and len({record["scenario_id"] for record in records}) == 12
    background_paths = (root / "normal_background/NBG_7301.csv", root / "normal_background/NBG_7301.inc", root / "normal_background/NBG_7301_METADATA.json")
    background_rows = generator.read_background(background_paths[0])
    generator.validate_background(generator.generate_background())
    parse_inc(background_paths[1])
    artifact_paths = []
    for record in records:
        stem = record["scenario_id"] + "_" + record["short_name"]
        csv_path, inc_path = root / "waveforms" / (stem + ".csv"), root / "waveforms" / (stem + ".inc")
        rows = load_csv(csv_path)
        inc_points = parse_inc(inc_path)
        _assert_scenario(record, rows, inc_points, background_rows)
        artifact_paths.extend([csv_path, inc_path])
        # Comments may explain that forbidden circuitry is absent.  Scan only
        # electrical source text so documentation cannot trigger a false fail.
        source_text = "\n".join(line.split("*", 1)[0] for line in inc_path.read_text(encoding="ascii").splitlines()).lower()
        assert not any(token.lower() in source_text for token in FORBIDDEN_TOKENS)
    _assert_special_geometry(records)
    manifest = build_manifest(root, contract_path, background_paths, artifact_paths)
    manifest_path = root / "DROOP12_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return manifest


def main(argv=None):
    """CLI entry point for the simulator-free W4 gate."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    manifest = validate_package(args.root)
    print("BFE7_W4_VALIDATION_PASS files={} scenarios=12".format(len(manifest["files"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
