#!/usr/bin/env python3
"""Run real HSPICE arrival experiments for the no-DFF Vernier topology.

Each physical point is identified by ``(M, dummy_load_count, VDD_A)`` and is
simulated once with simultaneous launches.  The analysis later evaluates all
legal launch offsets by translating the measured sense timestamps; no circuit
element changes when a calibration tap changes, so repeating the same physical
transient would add runtime without adding evidence.
"""

import argparse
import csv
import json
import shutil
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PHASE1_SCRIPTS = REPOSITORY_ROOT / "power_macro" / "delay_chain" / "phase1" / "scripts"
SCRIPT_DIR = Path(__file__).resolve().parent
for import_path in (PHASE1_SCRIPTS, SCRIPT_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))
import generate_delay_chain  # noqa: E402  # Phase 1 supplies checked HSPICE executable and parser helpers.
import generate_vernier_deck  # noqa: E402  # Local module owns the actual standard-cell deck rendering.
import run_dc_sweep  # noqa: E402  # Reuse reviewed listing and MEASFORM=3 validation.


FIXED_FIELDS = [
    "scenario_id",
    "m_stages",
    "dummy_load_count",
    "vdd_a_v",
    "vdd_ref_v",
    "start_ref_cross_s",
    "start_sense_cross_s",
    "sense_avg_current_a",
    "ref_avg_current_a",
    "sense_peak_current_a",
    "ref_peak_current_a",
    "warning_count",
    "measurement_file",
]


def load_json(path: Path) -> Dict[str, Any]:
    """Read a required JSON object with no implicit default configuration."""

    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def resolve_repo_path(value: str) -> Path:
    """Resolve inherited Phase 1 paths independently of the caller CWD."""

    path = Path(value)
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def parse_int_list(value: str, allowed: Sequence[int], name: str) -> List[int]:
    """Parse a comma-separated subset and reject values outside the configuration."""

    if value == "all":
        return list(allowed)
    result = []
    for token in value.split(","):
        parsed = int(token)
        if parsed not in allowed:
            raise ValueError("{} {} is not configured".format(name, parsed))
        result.append(parsed)
    if not result or len(set(result)) != len(result):
        raise ValueError("{} must be a nonempty duplicate-free list".format(name))
    return result


def voltage_points(config: Dict[str, Any], voltage_set: str) -> List[float]:
    """Build exact Decimal-grid points and insert non-grid 35/40-bank anchors."""

    if voltage_set == "anchors":
        return [float(value) for value in config["phase1_anchor_voltages_v"]]
    if voltage_set != "fine":
        raise ValueError("unknown voltage set: {}".format(voltage_set))
    start = Decimal(str(config["fine_vdd_start_v"]))
    stop = Decimal(str(config["fine_vdd_stop_v"]))
    step = Decimal(str(config["fine_vdd_step_v"]))
    values = []
    current = start
    while current <= stop:
        values.append(float(current))
        current += step
    for anchor in config["phase1_anchor_voltages_v"]:
        anchor_value = float(anchor)
        if not any(abs(anchor_value - value) <= 1.0e-12 for value in values):
            values.append(anchor_value)
    return sorted(values, reverse=True)


def scenario_id(m_stages: int, dummy_load_count: int, vdd_a_v: float) -> str:
    """Create a readable, filesystem-safe identity retaining voltage precision."""

    return "m_{:02d}/dummy_{:02d}/v{:0.12f}".format(m_stages, dummy_load_count, vdd_a_v).replace(".", "p")


def require_arrival_measurements(measurements: Dict[str, Any], m_stages: int) -> None:
    """Require every arrival because a missing middle tap invalidates Vernier code."""

    required = [
        "start_ref_cross",
        "start_sense_cross",
        "sense_avg_current_a",
        "ref_avg_current_a",
        "sense_peak_current_a",
        "ref_peak_current_a",
    ]
    for index in range(m_stages):
        required.extend(["sense_{:03d}_cross".format(index), "ref_{:03d}_cross".format(index)])
    missing = [name for name in required if measurements.get(name) is None]
    if missing:
        raise ValueError("required arrival measures are missing or failed: {}".format(missing))


def run_point(
    config: Dict[str, Any],
    hspice: Path,
    output_dir: Path,
    m_stages: int,
    dummy_load_count: int,
    vdd_a_v: float,
    timeout_s: int,
) -> Dict[str, Any]:
    """Generate, execute, validate, and preserve one independent HSPICE point."""

    point_dir = output_dir / "scenarios" / scenario_id(m_stages, dummy_load_count, vdd_a_v)
    point_dir.mkdir(parents=True, exist_ok=False)
    deck_path = point_dir / "vernier_ideal.sp"
    generate_vernier_deck.write_deck(config, m_stages, dummy_load_count, vdd_a_v, deck_path)
    result = run_dc_sweep.subprocess.run(
        [str(hspice), deck_path.name, "-o", "vernier_ideal"],
        cwd=str(point_dir),
        stdout=run_dc_sweep.subprocess.PIPE,
        stderr=run_dc_sweep.subprocess.PIPE,
        universal_newlines=True,
        check=False,
        timeout=timeout_s,
    )
    (point_dir / "hspice_command.log").write_text(
        "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            " ".join([str(hspice), deck_path.name, "-o", "vernier_ideal"]),
            result.returncode,
            result.stdout,
            result.stderr,
        ),
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, point_dir))
    return row_from_completed_point(config, output_dir, point_dir, m_stages, dummy_load_count, vdd_a_v)


def row_from_completed_point(
    config: Dict[str, Any],
    output_dir: Path,
    point_dir: Path,
    m_stages: int,
    dummy_load_count: int,
    vdd_a_v: float,
) -> Dict[str, Any]:
    """Reparse one validated point so a long physical sweep can resume safely.

    A resumed run never trusts directory existence alone.  It rechecks the
    HSPICE completion marker, rejected-error signatures, one unambiguous
    measurement file, and every required arrival before retaining prior work.
    """

    warning_count = run_dc_sweep.validate_listing(point_dir / "vernier_ideal.lis")
    measurement_path = run_dc_sweep.find_measurement_file(point_dir, "vernier_ideal")
    measurements = run_dc_sweep.parse_measurements(measurement_path)
    require_arrival_measurements(measurements, m_stages)
    row: Dict[str, Any] = {
        "scenario_id": scenario_id(m_stages, dummy_load_count, vdd_a_v),
        "m_stages": m_stages,
        "dummy_load_count": dummy_load_count,
        "vdd_a_v": vdd_a_v,
        "vdd_ref_v": float(config["vdd_ref_v"]),
        "start_ref_cross_s": measurements["start_ref_cross"],
        "start_sense_cross_s": measurements["start_sense_cross"],
        "sense_avg_current_a": measurements["sense_avg_current_a"],
        "ref_avg_current_a": measurements["ref_avg_current_a"],
        "sense_peak_current_a": measurements["sense_peak_current_a"],
        "ref_peak_current_a": measurements["ref_peak_current_a"],
        "warning_count": warning_count,
        "measurement_file": str(measurement_path.relative_to(output_dir)),
    }
    for index in range(m_stages):
        row["sense_{:03d}_cross_s".format(index)] = measurements["sense_{:03d}_cross".format(index)]
        row["ref_{:03d}_cross_s".format(index)] = measurements["ref_{:03d}_cross".format(index)]
    return row


def restart_incomplete_point(point_dir: Path) -> None:
    """Remove only an interrupted task-owned point that has no completion listing.

    HSPICE writes a nonempty listing only after it has materialized diagnostics
    consumed by ``validate_listing``.  A missing or zero-byte listing denotes
    an interrupted launch and leaves only an input deck or solver scratch, so
    that exact task-owned point is safe to recreate.  Any nonempty listing is
    preserved for investigation and must pass normal validation instead.
    """

    listing = point_dir / "vernier_ideal.lis"
    if listing.is_file() and listing.stat().st_size > 0:
        raise RuntimeError("refusing to discard a point that has a HSPICE listing: {}".format(point_dir))
    shutil.rmtree(point_dir)


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    """Write one rectangular evidence table capable of carrying up to 32 stages."""

    arrival_fields = []
    for index in range(32):
        arrival_fields.extend(["sense_{:03d}_cross_s".format(index), "ref_{:03d}_cross_s".format(index)])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIXED_FIELDS + arrival_fields, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            rendered = {}
            for field in FIXED_FIELDS + arrival_fields:
                value = row.get(field)
                rendered[field] = "" if value is None else "{:.12e}".format(value) if isinstance(value, float) else str(value)
            writer.writerow(rendered)


def build_argument_parser() -> argparse.ArgumentParser:
    """Expose bounded sweep controls; every output directory must be new."""

    parser = argparse.ArgumentParser(description="run Phase-2 no-DFF Vernier arrival sweep")
    parser.add_argument("--config", required=True, type=Path, help="Phase 2 configuration")
    parser.add_argument("--output-dir", required=True, type=Path, help="new task-owned run directory")
    parser.add_argument("--m-stages", default="all", help="all or comma-separated configured M values")
    parser.add_argument("--dummy-load-counts", default="all", help="all or comma-separated configured dummy counts")
    parser.add_argument("--voltage-set", choices=("anchors", "fine"), required=True, help="three anchors or full 0.5 mV scan")
    parser.add_argument("--timeout-s", type=int, default=180, help="per-deck HSPICE timeout")
    parser.add_argument("--resume", action="store_true", help="continue only a compatible interrupted task-owned run directory")
    return parser


def main(argv: Iterable[str] = None) -> int:
    """Run the selected actual-arrival cases and publish raw CSV plus manifest."""

    args = build_argument_parser().parse_args(argv)
    config = load_json(args.config)
    phase1_config = load_json(resolve_repo_path(str(config["phase1_config_path"])))
    m_values = parse_int_list(args.m_stages, config["comparator_stages"], "m_stages")
    dummy_values = parse_int_list(args.dummy_load_counts, config["reference_dummy_load_counts"], "dummy_load_counts")
    points = voltage_points(config, args.voltage_set)
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and not args.resume:
        raise ValueError("refusing to overwrite existing run directory: {}".format(output_dir))
    if args.resume and not output_dir.is_dir():
        raise ValueError("--resume requires an existing task-owned run directory: {}".format(output_dir))
    output_dir.mkdir(parents=True, exist_ok=args.resume)
    hspice = run_dc_sweep.require_regular_file(Path(phase1_config["hspice"]), "HSPICE", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if phase1_config["expected_hspice_version"] not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    manifest = {
        "study_name": "phase2_ideal_arrival_sweep",
        "voltage_set": args.voltage_set,
        "m_stages": m_values,
        "dummy_load_counts": dummy_values,
        "voltage_point_count": len(points),
        "hspice": {"executable": str(hspice), "version": version},
    }
    manifest_path = output_dir / "manifest.json"
    if args.resume:
        prior = load_json(manifest_path)
        for key in ("study_name", "voltage_set", "m_stages", "dummy_load_counts", "voltage_point_count"):
            if prior.get(key) != manifest.get(key):
                raise ValueError("resume manifest mismatch for {}".format(key))
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = []
    for m_stages in m_values:
        for dummy_load_count in dummy_values:
            for vdd_a_v in points:
                point_dir = output_dir / "scenarios" / scenario_id(m_stages, dummy_load_count, vdd_a_v)
                if point_dir.exists():
                    if not args.resume:
                        raise ValueError("unexpected pre-existing point directory: {}".format(point_dir))
                    try:
                        rows.append(row_from_completed_point(config, output_dir, point_dir, m_stages, dummy_load_count, vdd_a_v))
                    except ValueError:
                        restart_incomplete_point(point_dir)
                        rows.append(run_point(config, hspice, output_dir, m_stages, dummy_load_count, vdd_a_v, args.timeout_s))
                else:
                    rows.append(run_point(config, hspice, output_dir, m_stages, dummy_load_count, vdd_a_v, args.timeout_s))
    write_csv(output_dir / "arrival_raw.csv", rows)
    (output_dir / "completion.rpt").write_text("status=PASS\nscenario_count={}\n".format(len(rows)), encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
