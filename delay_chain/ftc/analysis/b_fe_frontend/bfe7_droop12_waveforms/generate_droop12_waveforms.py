#!/usr/bin/env python3
"""Generate the deterministic B-FE7 DROOP12 voltage-stimulus package.

The module is intentionally stimulus-only.  It contains no detector, sensor,
clock, latch, DFF, backend, or RTL dependency.  Its electrical boundary is a
single monitored-domain source with the project port contract::

    V_VDD_MONITORED vdd_monitored vss_a PWL(...)

``vdd_monitored`` is the positive supply node observed by the frontend and
``vss_a`` is its local return node.  Keeping this port map explicit makes each
include directly reusable by later ARCH0 and ARCH1 decks without copying any
detector circuitry into the benchmark files.

All internal times are integer picoseconds.  This avoids accumulated binary
floating-point error while constructing a piecewise-linear waveform.  Values
are converted to SI seconds only when serialized for CSV/HSPICE output.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np


SCRIPT_VERSION = "bfe7_droop12_generator_v1"
SEED = 7301
T_STOP_PS = 65000
V_NOM = 1.10
TEMP_C = 25.0
SLOW_SPACING_PS = 2500
FAST_SPACING_PS = 250
SLOW_LIMIT_V = 0.005
FAST_LIMIT_V = 0.003
BACKGROUND_LIMIT_V = 0.008
MONITORED_SOURCE = "V_VDD_MONITORED vdd_monitored vss_a"
EDGE_PS = {"T_E": 21000, "T_E1": 31000, "T_E2": 41000, "T_E3": 51000}

# These records are the sole source of truth for the twelve elemental attacks.
# ``attack_breakpoints_ps`` is filled by ``attack_points`` below and stores
# (time_ps, depth_v) pairs, where depth is a non-negative drop from the noisy
# instantaneous baseline.  No clock or capture signal is represented here.
SCENARIO_DEFINITIONS = (
    ("D01", "SHALLOW_CANONICAL", "A", "shallow single-event canonical challenge", "rect", 0.030, 3000, 21000),
    ("D02", "MEDIUM_CANONICAL", "A", "medium single-event control", "rect", 0.060, 3000, 21000),
    ("D03", "STRONG_CANONICAL", "A", "strong positive-control attack", "rect", 0.140, 3000, 21000),
    ("D04", "SHORT_MEDIUM", "B", "same medium depth with short exposure", "rect", 0.060, 600, 21000),
    ("D05", "DEEP_V_SHAPE", "B", "deep transient with no low-voltage dwell", "v", 0.140, 1500, 21000),
    ("D06", "SLOW_FALL_FAST_RECOVERY", "B", "slow sag crossing the meaningful edge", "slow", 0.060, 0, 21000),
    ("D07", "DOUBLE_SHALLOW", "C", "two weak events on consecutive edges", "double", 0.030, 800, 21000),
    ("D08", "FOUR_PULSE_SHALLOW_BURST", "C", "four weak events across four edges", "burst", 0.030, 800, 21000),
    ("D09", "STAIRCASE_SAG", "C", "four cumulative finite-ramp depth steps", "staircase", 0.040, 0, 21000),
    ("D10", "PRE_EDGE_MEDIUM", "D", "medium droop concentrated before the edge", "pre", 0.060, 3000, 21000),
    ("D11", "POST_EDGE_MEDIUM", "D", "medium droop concentrated after the edge", "post", 0.060, 3000, 21000),
    ("D12", "DUAL_EDGE_SHALLOW_SPAN", "D", "one shallow event spanning two edges", "span", 0.030, 12000, 21000),
)


def _rect_points(depth_v, plateau_ps, center_ps):
    """Return a finite-slew 10 ps-fall/plateau/10 ps-rise attack."""

    plateau_start = center_ps - plateau_ps // 2
    plateau_end = plateau_start + plateau_ps
    return [(plateau_start - 10, 0.0), (plateau_start, depth_v),
            (plateau_end, depth_v), (plateau_end + 10, 0.0)]


def attack_points(kind, depth_v, width_ps, center_ps):
    """Construct one immutable attack envelope from a W2 scenario definition."""

    if kind == "rect":
        return _rect_points(depth_v, width_ps, center_ps)
    if kind == "v":
        return [(center_ps - 750, 0.0), (center_ps, depth_v), (center_ps + 750, 0.0)]
    if kind == "slow":
        return [(center_ps - 2500, 0.0), (center_ps - 100, depth_v),
                (center_ps + 100, depth_v), (center_ps + 110, 0.0)]
    if kind in ("double", "burst"):
        count = 2 if kind == "double" else 4
        points = []
        for index in range(count):
            points.extend(_rect_points(depth_v, width_ps, center_ps + index * 10000))
        return points
    if kind == "staircase":
        return [(0, 0.0), (21000, 0.0), (21010, 0.010),
                (31000, 0.010), (31010, 0.020), (41000, 0.020),
                (41010, 0.030), (51000, 0.030), (51010, 0.040),
                (58000, 0.040), (58010, 0.0)]
    if kind == "pre":
        return [(center_ps - 3010, 0.0), (center_ps - 3000, depth_v),
                (center_ps, depth_v), (center_ps + 10, 0.0)]
    if kind == "post":
        return [(center_ps - 10, 0.0), (center_ps, depth_v),
                (center_ps + 3000, depth_v), (center_ps + 3010, 0.0)]
    if kind == "span":
        return [(center_ps - 1010, 0.0), (center_ps - 1000, depth_v),
                (center_ps + 11000, depth_v), (center_ps + 11010, 0.0)]
    raise ValueError("unknown DROOP12 attack kind: {}".format(kind))


def scenario_records():
    """Expand compact definitions into contract records with explicit points."""

    records = []
    for identifier, name, group, purpose, kind, depth, width, center in SCENARIO_DEFINITIONS:
        points = attack_points(kind, depth, width, center)
        if any(time < 0 or time > T_STOP_PS for time, _ in points):
            raise ValueError("{} attack point is outside canonical frame".format(identifier))
        if any(right[0] <= left[0] for left, right in zip(points, points[1:])):
            raise ValueError("{} attack points are not strictly increasing".format(identifier))
        records.append({
            "scenario_id": identifier,
            "short_name": name,
            "group": group,
            "purpose": purpose,
            "attack_kind": kind,
            "nominal_depth_v": depth,
            "attack_breakpoints_ps": [[int(time), float(value)] for time, value in points],
            "reference_edges_ps": dict(EDGE_PS),
        })
    return records


def write_scenario_contract(records, csv_path, json_path, background_metadata):
    """Write the reviewable W2 CSV/JSON contract without waveform generation."""

    csv_path = Path(csv_path)
    json_path = Path(json_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["scenario_id", "short_name", "group", "attack_kind", "nominal_depth_v",
              "attack_breakpoints_ps", "reference_edges_ps", "purpose"]
    with csv_path.open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({
                "scenario_id": record["scenario_id"], "short_name": record["short_name"],
                "group": record["group"], "attack_kind": record["attack_kind"],
                "nominal_depth_v": _format_si(record["nominal_depth_v"]),
                "attack_breakpoints_ps": json.dumps(record["attack_breakpoints_ps"], separators=(",", ":")),
                "reference_edges_ps": json.dumps(record["reference_edges_ps"], sort_keys=True, separators=(",", ":")),
                "purpose": record["purpose"],
            })
    contract = {
        "schema_version": 1, "study": "B-FE7-DROOP12-WAVEFORM-CONTRACT",
        "generator_version": SCRIPT_VERSION, "baseline_commit": "9794e960374a0e8b881a6c936ddbc69816d87cba",
        "frozen": False, "nominal_vdd_v": V_NOM, "temperature_c": TEMP_C,
        "time_frame": {"stop_s": T_STOP_PS * 1.0e-12, "reference_edges_s": {key: value * 1.0e-12 for key, value in EDGE_PS.items()}},
        "background": background_metadata, "scenarios": records,
        "finite_slope_slew_ps": 10, "waveform_formula": "vdd_v = 1.10 + noise_v - attack_depth_v",
        "source_contract": MONITORED_SOURCE,
        "scope": ["stimulus definitions only", "no ARCH0/ARCH1 result implication", "no simulator noise source"],
    }
    json_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="ascii")


def read_background(csv_path):
    """Read the frozen background CSV and return integer-ps interpolation knots."""

    rows = []
    with Path(csv_path).open(newline="", encoding="ascii") as stream:
        for raw in csv.DictReader(stream):
            time_s = float(raw["time_s"])
            time_ps = int(round(time_s * 1.0e12))
            if abs(time_s - time_ps * 1.0e-12) > 1.0e-18:
                raise ValueError("background time is not an integer ps")
            rows.append({"time_ps": time_ps, "noise_v": float(raw["n_bg_v"])})
    if not rows or rows[0]["time_ps"] != 0 or rows[-1]["time_ps"] != T_STOP_PS:
        raise ValueError("background CSV has invalid endpoints")
    if any(right["time_ps"] <= left["time_ps"] for left, right in zip(rows, rows[1:])):
        raise ValueError("background CSV time is not strictly increasing")
    return rows


def interpolate_noise(rows, time_ps):
    """Linearly evaluate the shared background at one integer-ps breakpoint."""

    times = [row["time_ps"] for row in rows]
    values = [row["noise_v"] for row in rows]
    return float(np.interp(int(time_ps), times, values))


def write_waveform(record, background_rows, csv_path, inc_path):
    """Merge one attack envelope with background knots and serialize both views."""

    attack = [(int(time), float(depth)) for time, depth in record["attack_breakpoints_ps"]]
    times = sorted(set([0, T_STOP_PS] + [row["time_ps"] for row in background_rows] + [time for time, _ in attack]))
    attack_times = [time for time, _ in attack]
    attack_values = [depth for _, depth in attack]
    rows = []
    for time_ps in times:
        depth = float(np.interp(time_ps, attack_times, attack_values)) if time_ps >= attack_times[0] else 0.0
        if time_ps > attack_times[-1]:
            depth = 0.0
        noise = interpolate_noise(background_rows, time_ps)
        vdd = V_NOM + noise - depth
        rows.append({"time_ps": time_ps, "noise_v": noise, "attack_depth_v": depth, "vdd_v": vdd})
    if any(right["time_ps"] <= left["time_ps"] for left, right in zip(rows, rows[1:])):
        raise ValueError("merged waveform timestamps are not strictly increasing")
    csv_path = Path(csv_path)
    inc_path = Path(inc_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="ascii") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["time_s", "noise_v", "attack_depth_v", "vdd_v"])
        for row in rows:
            writer.writerow([_format_si(row["time_ps"] * 1.0e-12), _format_si(row["noise_v"]),
                             _format_si(row["attack_depth_v"]), _format_si(row["vdd_v"])])
    lines = [
        "* BFE7 {} {}; deterministic supply stimulus only.".format(record["scenario_id"], record["short_name"]),
        "* Port map: positive monitored rail=vdd_monitored; local return=vss_a.",
        "* No detector, sensor, clock, LATQ, DFF, backend, ARCH0, or ARCH1 logic.",
        "{} PWL(".format(MONITORED_SOURCE),
    ]
    for index, row in enumerate(rows):
        suffix = ")" if index == len(rows) - 1 else ""
        lines.append("+ {} {}{}".format(_format_si(row["time_ps"] * 1.0e-12), _format_si(row["vdd_v"]), suffix))
    inc_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return rows


def generate_all_waveforms(contract_path, background_csv, output_dir):
    """Consume only frozen W2 contract/background inputs and emit 24 artifacts."""

    contract = json.loads(Path(contract_path).read_text(encoding="ascii"))
    if contract.get("frozen") is not True:
        raise ValueError("waveform generation requires frozen=true contract")
    background_rows = read_background(background_csv)
    output_dir = Path(output_dir)
    results = []
    for record in contract["scenarios"]:
        stem = "{}_{}".format(record["scenario_id"], record["short_name"])
        csv_path = output_dir / "waveforms" / (stem + ".csv")
        inc_path = output_dir / "waveforms" / (stem + ".inc")
        rows = write_waveform(record, background_rows, csv_path, inc_path)
        results.append({"scenario_id": record["scenario_id"], "csv": str(csv_path), "inc": str(inc_path), "point_count": len(rows)})
    return results


def sha256_file(path):
    """Return a streaming SHA256 digest for reproducibility manifests."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _center_and_bound(samples, limit):
    """Center seeded samples while retaining the declared per-component bound."""

    values = np.asarray(samples, dtype=np.float64)
    values = values - float(np.mean(values))
    # The source distribution is already narrow; clipping is a defensive
    # contract guard for future changes to the sampling implementation.
    return np.clip(values, -limit, limit)


def _time_grid(step_ps):
    """Return inclusive integer-ps knots from zero through the 65 ns stop."""

    if T_STOP_PS % step_ps:
        raise ValueError("stop time must be divisible by knot spacing")
    return np.arange(0, T_STOP_PS + step_ps, step_ps, dtype=np.int64)


def generate_background(seed=SEED):
    """Construct the shared normal background on the canonical 250 ps grid.

    ``PCG64`` is named explicitly instead of relying on NumPy's
    ``default_rng`` alias, so a future NumPy default change cannot silently
    replace the paper-facing realization.  Slow samples are generated first,
    followed by fast samples, making the random draw order part of the frozen
    metadata contract.
    """

    if int(seed) != SEED:
        raise ValueError("DROOP12 canonical background seed is {}".format(SEED))
    rng = np.random.Generator(np.random.PCG64(int(seed)))
    slow_times = _time_grid(SLOW_SPACING_PS)
    fast_times = _time_grid(FAST_SPACING_PS)
    slow_samples = _center_and_bound(
        rng.uniform(-SLOW_LIMIT_V, SLOW_LIMIT_V, len(slow_times)), SLOW_LIMIT_V
    )
    fast_samples = _center_and_bound(
        rng.uniform(-FAST_LIMIT_V, FAST_LIMIT_V, len(fast_times)), FAST_LIMIT_V
    )
    # The exported grid is the fast grid.  Slow knots are exact members of it,
    # so np.interp introduces no additional time points or ambiguity.
    slow_on_fast = np.interp(fast_times, slow_times, slow_samples)
    n_bg = np.clip(slow_on_fast + fast_samples, -BACKGROUND_LIMIT_V, BACKGROUND_LIMIT_V)
    healthy = V_NOM + n_bg
    rows = []
    for time_ps, slow_v, fast_v, bg_v, healthy_v in zip(
            fast_times, slow_on_fast, fast_samples, n_bg, healthy):
        values = (int(time_ps), float(slow_v), float(fast_v), float(bg_v), float(healthy_v))
        if not all(math.isfinite(value) for value in values[1:]):
            raise ValueError("background contains a non-finite value")
        rows.append({
            "time_ps": values[0],
            "n_slow_v": values[1],
            "n_fast_v": values[2],
            "n_bg_v": values[3],
            "vdd_healthy_v": values[4],
        })
    return rows


def _format_si(value):
    """Render one finite SI value using locale-independent scientific notation."""

    number = float(value)
    if not math.isfinite(number):
        raise ValueError("cannot serialize non-finite value")
    return "{:.12e}".format(number)


def write_background(rows, csv_path, inc_path):
    """Write the shared background CSV and its one-port HSPICE PWL include."""

    csv_path = Path(csv_path)
    inc_path = Path(inc_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    inc_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="ascii") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["time_s", "n_slow_v", "n_fast_v", "n_bg_v", "vdd_healthy_v"])
        for row in rows:
            writer.writerow([
                _format_si(row["time_ps"] * 1.0e-12),
                _format_si(row["n_slow_v"]),
                _format_si(row["n_fast_v"]),
                _format_si(row["n_bg_v"]),
                _format_si(row["vdd_healthy_v"]),
            ])
    lines = [
        "* BFE7 W1 deterministic healthy background; seed={} PCG64.".format(SEED),
        "* Port map: positive monitored rail=vdd_monitored; local return=vss_a.",
        "* This include contains one supply source and no detector circuitry.",
        "{} PWL(".format(MONITORED_SOURCE),
    ]
    for index, row in enumerate(rows):
        suffix = ")" if index == len(rows) - 1 else ""
        lines.append("+ {} {}{}".format(
            _format_si(row["time_ps"] * 1.0e-12),
            _format_si(row["vdd_healthy_v"]),
            suffix,
        ))
    inc_path.write_text("\n".join(lines) + "\n", encoding="ascii")


def validate_background(rows):
    """Apply all W1 offline assertions before a background gate is published."""

    if not rows or rows[0]["time_ps"] != 0 or rows[-1]["time_ps"] != T_STOP_PS:
        raise ValueError("background must start at 0 ps and end at 65000 ps")
    times = [row["time_ps"] for row in rows]
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError("background times are not strictly increasing")
    for row in rows:
        for key in ("n_slow_v", "n_fast_v", "n_bg_v", "vdd_healthy_v"):
            if not math.isfinite(float(row[key])):
                raise ValueError("non-finite background field {}".format(key))
        if abs(float(row["n_bg_v"])) > BACKGROUND_LIMIT_V + 1.0e-15:
            raise ValueError("background exceeds +/-8 mV")
        if not (V_NOM - BACKGROUND_LIMIT_V - 1.0e-15 <= float(row["vdd_healthy_v"]) <=
                V_NOM + BACKGROUND_LIMIT_V + 1.0e-15):
            raise ValueError("healthy rail is outside the 1.092..1.108 V contract")


def main(argv=None):
    """Generate W1, or W3 when an explicitly frozen contract is supplied."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--contract", type=Path, help="frozen W2 contract for W3 scenario generation")
    args = parser.parse_args(argv)
    rows = generate_background(args.seed)
    validate_background(rows)
    background = args.output_dir / "normal_background"
    csv_path = background / "NBG_7301.csv"
    inc_path = background / "NBG_7301.inc"
    write_background(rows, csv_path, inc_path)
    metadata = {
        "schema_version": 1,
        "generator_version": SCRIPT_VERSION,
        "seed": SEED,
        "rng": "numpy.random.Generator(numpy.random.PCG64(7301))",
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "nominal_vdd_v": V_NOM,
        "temperature_c": TEMP_C,
        "stop_time_s": T_STOP_PS * 1.0e-12,
        "slow_knot_spacing_s": SLOW_SPACING_PS * 1.0e-12,
        "fast_knot_spacing_s": FAST_SPACING_PS * 1.0e-12,
        "background_limit_v": BACKGROUND_LIMIT_V,
        "csv_sha256": sha256_file(csv_path),
        "inc_sha256": sha256_file(inc_path),
        "simulation_accounting": {"hspice_runs": 0, "vcs_runs": 0, "dc_runs": 0, "primesim_runs": 0},
    }
    (background / "NBG_7301_METADATA.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    if args.contract is not None:
        results = generate_all_waveforms(args.contract, csv_path, args.output_dir)
        print("BFE7_W3_WAVEFORMS_PASS scenarios={} points={}".format(
            len(results), sum(item["point_count"] for item in results)))
        return 0
    print("BFE7_W1_BACKGROUND_PASS rows={} csv_sha256={} inc_sha256={}".format(
        len(rows), metadata["csv_sha256"], metadata["inc_sha256"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
