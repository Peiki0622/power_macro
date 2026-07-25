#!/usr/bin/env python3
"""Run the calibrated real-DFF voltage-droop-to-code characterization.

Every static point owns an independent HSPICE deck.  This intentionally uses
the real SMIC40LL sense stages, reference stages, and DFF comparators instead
of deriving a code from a fitted delay equation.  The 0.5 mV grid is augmented
with the exact 765 MHz 35-bank and 40-bank timing anchors when they do not lie
on that grid, so the report can place timing evidence on the measured code
curve without rounding either voltage.
"""

import argparse
import csv
import json
import math
import shutil
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


# Phase 1 owns the checked HSPICE executable, listing validator, and MEASFORM
# parser.  Phase 2 owns the real comparator deck renderer and thermometer
# decoder.  Explicit path insertion keeps these scripts executable directly
# from any working directory without introducing a package-install dependency.
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PHASE1_SCRIPTS = REPOSITORY_ROOT / "power_macro" / "delay_chain" / "phase1" / "scripts"
SCRIPT_DIR = Path(__file__).resolve().parent
for import_path in (PHASE1_SCRIPTS, SCRIPT_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))
import decode_vernier_code  # noqa: E402  # Preserves raw/corrected thermometer evidence.
import generate_vernier_deck  # noqa: E402  # Renders the reviewed standard-cell DFF topology.
import run_dc_sweep  # noqa: E402  # Validates HSPICE listings and measurement files.
import run_dff_sweep  # noqa: E402  # Reuses DFF bit and reset interpretation.


# This rectangular CSV contract is the sole static input to plotting and PWL
# comparison.  Raw bits, corrected bits, and electrical measurements remain in
# one row so a plotted sensor_code can always be traced back to the DFF levels
# and exact generated deck that produced it.
CSV_FIELDS = [
    "scenario_id",
    "candidate_id",
    "cal_sel",
    "vdd_a_v",
    "droop_mv",
    "vdd_ref_v",
    "m_stages",
    "dummy_load_count",
    "launch_offset_s",
    "raw_code",
    "raw_sensor_code",
    "corrected_code",
    "sensor_code",
    "raw_bubble_count",
    "bubble_count",
    "raw_transition_count",
    "transition_count",
    "code_valid",
    "expected_arrival_code",
    "mismatch_count",
    "reset_failure_count",
    "metastability_risk_count",
    "last_q_rise_s",
    "comparator_avg_current_a",
    "comparator_peak_current_a",
    "warning_count",
    "measurement_file",
]


def load_json(path: Path) -> Dict[str, Any]:
    """Load one required JSON object and reject malformed configuration early."""

    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def resolve_repo_path(value: str) -> Path:
    """Resolve a Phase 1 relative path against the repository, never caller CWD."""

    path = Path(value)
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def characterization(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return and validate the dedicated calibrated voltage-code study section.

    The voltage-code experiment must not accidentally inherit the older ideal
    arrival sweep defaults.  It therefore requires a complete explicit block
    describing the real-DFF topology, selected calibration tap, and static
    voltage grid before a simulator directory can be created.
    """

    value = config.get("voltage_code_characterization")
    if not isinstance(value, dict):
        raise ValueError("phase2_config.json lacks voltage_code_characterization")
    required = [
        "m_stages",
        "dummy_load_count",
        "cal_sel",
        "launch_offset_s",
        "static_vdd_start_v",
        "static_vdd_stop_v",
        "static_vdd_step_v",
        "include_phase1_anchor_voltages",
    ]
    missing = [key for key in required if key not in value]
    if missing:
        raise ValueError("voltage-code configuration lacks: {}".format(", ".join(missing)))
    if int(value["m_stages"]) not in config["comparator_stages"]:
        raise ValueError("voltage-code M is not an allowed Phase 2 stage count")
    if int(value["dummy_load_count"]) not in config["reference_dummy_load_counts"]:
        raise ValueError("voltage-code dummy load is not an allowed Phase 2 value")
    if int(value["cal_sel"]) < 0 or int(value["cal_sel"]) >= len(config["calibration_launch_offsets_s"]):
        raise ValueError("voltage-code CAL_SEL is outside configured calibration taps")
    if abs(float(value["launch_offset_s"]) - float(config["calibration_launch_offsets_s"][int(value["cal_sel"])])) > 1.0e-18:
        raise ValueError("voltage-code launch offset does not match its CAL_SEL tap")
    start = Decimal(str(value["static_vdd_start_v"]))
    stop = Decimal(str(value["static_vdd_stop_v"]))
    step = Decimal(str(value["static_vdd_step_v"]))
    if start != Decimal(str(config["vnom_v"])) or stop <= 0 or step <= 0 or start < stop:
        raise ValueError("voltage-code static range must descend from Vnom with a positive step")
    return value


def voltage_points(config: Dict[str, Any]) -> List[float]:
    """Build the exact grid plus non-grid 765 MHz anchors in descending voltage order.

    Decimal arithmetic avoids binary rounding creating duplicate directories or
    omitting an endpoint.  The configured 1.10-to-0.95 V, 0.5 mV grid contains
    301 points.  The 35-bank and 40-bank anchors are added only when not
    exactly represented, yielding 303 scenarios for the current configuration.
    """

    study = characterization(config)
    start = Decimal(str(study["static_vdd_start_v"]))
    stop = Decimal(str(study["static_vdd_stop_v"]))
    step = Decimal(str(study["static_vdd_step_v"]))
    values: List[Decimal] = []
    current = start
    while current >= stop:
        values.append(current)
        current -= step
    if values[-1] != stop:
        raise ValueError("static voltage grid does not land on its configured endpoint")
    if bool(study["include_phase1_anchor_voltages"]):
        for anchor in config["phase1_anchor_voltages_v"]:
            decimal_anchor = Decimal(str(anchor))
            if decimal_anchor < stop or decimal_anchor > start:
                raise ValueError("timing anchor lies outside voltage-code range: {}".format(anchor))
            if decimal_anchor not in values:
                values.append(decimal_anchor)
    return [float(value) for value in sorted(values, reverse=True)]


def candidate(config: Dict[str, Any]) -> Dict[str, Any]:
    """Describe the one calibrated physical topology used at every static point."""

    study = characterization(config)
    return {
        "candidate_id": "m{:02d}_d{}_cal_sel_{:03d}".format(
            int(study["m_stages"]), int(study["dummy_load_count"]), int(study["cal_sel"])
        ),
        "m_stages": int(study["m_stages"]),
        "dummy_load_count": int(study["dummy_load_count"]),
        "launch_offset_s": float(study["launch_offset_s"]),
    }


def scenario_label(vdd_a_v: float) -> str:
    """Create a stable per-voltage scenario label without losing anchor precision."""

    return "v{:0.12f}".format(vdd_a_v).replace(".", "p")


def decode_row(config: Dict[str, Any], raw_row: Dict[str, Any], cal_sel: int) -> Dict[str, Any]:
    """Attach auditable corrected-code fields to one electrically decoded DFF row.

    ``run_dff_sweep.parse_bits`` records the physical DFF capture and reset
    facts.  This function deliberately invokes the standalone thermometer
    decoder on that raw word rather than reimplementing majority filtering, so
    static curves and controller-facing decoder tests share one definition.
    """

    decoded = decode_vernier_code.decode_word(str(raw_row["raw_code"]))
    if decoded["raw_code"] != str(raw_row["raw_code"]):
        raise ValueError("shared decoder altered the measured raw DFF word")
    row = dict(raw_row)
    # ``run_dff_sweep`` reports the first-one position of the physical DFF
    # word.  The shared decoder may intentionally change that position when a
    # majority filter repairs an interior bubble, so both values are retained
    # instead of rejecting or concealing the abnormal physical observation.
    row["raw_sensor_code"] = int(raw_row["sensor_code"])
    row.update(decoded)
    row["cal_sel"] = cal_sel
    row["droop_mv"] = (float(config["vnom_v"]) - float(row["vdd_a_v"])) * 1000.0
    return row


def parse_completed_point(
    config: Dict[str, Any], output_dir: Path, point_candidate: Dict[str, Any], vdd_a_v: float
) -> Dict[str, Any]:
    """Reparse a completed task-owned HSPICE point before a run may resume it.

    Directory existence is not treated as proof of completion.  The listing,
    exact measurement file, all real-DFF fields, and thermometer decoding are
    independently revalidated so an interrupted point cannot silently enter a
    303-point plot as a stale or partial result.
    """

    label = scenario_label(vdd_a_v)
    point_dir = output_dir / "scenarios" / label
    warning_count = run_dc_sweep.validate_listing(point_dir / "vernier_dff.lis")
    measurement_path = run_dc_sweep.find_measurement_file(point_dir, "vernier_dff")
    measurements = run_dc_sweep.parse_measurements(measurement_path)
    run_dff_sweep.require_measurements(measurements, int(point_candidate["m_stages"]))
    electrical = run_dff_sweep.parse_bits(
        measurements,
        int(point_candidate["m_stages"]),
        float(config["vdd_ref_v"]),
        float(point_candidate["launch_offset_s"]),
        float(config["measurement_timing"]["dff_metastability_margin_s"]),
    )
    electrical.update(
        {
            "scenario_id": label,
            "candidate_id": point_candidate["candidate_id"],
            "vdd_a_v": vdd_a_v,
            "vdd_ref_v": float(config["vdd_ref_v"]),
            "m_stages": int(point_candidate["m_stages"]),
            "dummy_load_count": int(point_candidate["dummy_load_count"]),
            "launch_offset_s": float(point_candidate["launch_offset_s"]),
            "comparator_avg_current_a": measurements["comparator_ref_avg_current_a"],
            "comparator_peak_current_a": measurements["comparator_ref_peak_current_a"],
            "warning_count": warning_count,
            "measurement_file": str(measurement_path.relative_to(output_dir)),
        }
    )
    return decode_row(config, electrical, int(characterization(config)["cal_sel"]))


def run_new_point(
    config: Dict[str, Any], hspice: Path, output_dir: Path, point_candidate: Dict[str, Any], vdd_a_v: float, timeout_s: int
) -> Dict[str, Any]:
    """Generate and execute one new static point, then parse it through the resume path.

    The generated deck keeps the reference domain at the independent 1.1 V
    rail.  The only swept source is VDD_A, so each output code represents the
    requested direct local supply voltage rather than a shared-PDN waveform.
    """

    label = scenario_label(vdd_a_v)
    point_dir = output_dir / "scenarios" / label
    point_dir.mkdir(parents=True, exist_ok=False)
    deck_path = point_dir / "vernier_dff.sp"
    generate_vernier_deck.write_dff_deck(
        config,
        int(point_candidate["m_stages"]),
        int(point_candidate["dummy_load_count"]),
        vdd_a_v,
        float(point_candidate["launch_offset_s"]),
        deck_path,
    )
    result = run_dc_sweep.subprocess.run(
        [str(hspice), deck_path.name, "-o", "vernier_dff"],
        cwd=str(point_dir),
        stdout=run_dc_sweep.subprocess.PIPE,
        stderr=run_dc_sweep.subprocess.PIPE,
        universal_newlines=True,
        check=False,
        timeout=timeout_s,
    )
    (point_dir / "hspice_command.log").write_text(
        "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            " ".join([str(hspice), deck_path.name, "-o", "vernier_dff"]),
            result.returncode,
            result.stdout,
            result.stderr,
        ),
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, point_dir))
    return parse_completed_point(config, output_dir, point_candidate, vdd_a_v)


def restart_incomplete_point(point_dir: Path) -> None:
    """Remove only an interrupted task-owned point with no nonempty HSPICE listing.

    A nonempty listing can contain simulator diagnostics and is preserved for
    inspection.  An absent or empty listing means HSPICE did not materialize
    usable evidence, so deleting that exact new-run point is safe and permits a
    deterministic rerun without overwriting any completed scenario.
    """

    listing = point_dir / "vernier_dff.lis"
    if listing.is_file() and listing.stat().st_size > 0:
        raise RuntimeError("refusing to discard nonempty HSPICE listing: {}".format(point_dir))
    shutil.rmtree(point_dir)


def render_value(value: Any) -> str:
    """Render CSV values without converting absent optional timing values to zero."""

    if value is None:
        return ""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("refusing to write non-finite CSV value")
        return "{:.12e}".format(value)
    return str(value)


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    """Write the complete static code/electrical contract in deterministic order."""

    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: render_value(row[field]) for field in CSV_FIELDS})


def validate_rows(config: Dict[str, Any], rows: Sequence[Dict[str, Any]], expected_count: int) -> Dict[str, Any]:
    """Apply publication gates without altering any raw result.

    The curve is valid only when every planned voltage produced one electrical
    result, every DFF reset cleared, every decoded word is monotonic after the
    declared majority filter, the calibrated nominal point remains centered,
    and code does not decrease as direct VDD_A droop increases.  A crossing
    within the 2 ps aperture is retained as a metastability-risk diagnostic,
    not a global failure: one such near-equality is inherent near a Vernier
    transition and is the physical source of the code step.  A failure is
    reported in the summary and completion file; no outlier is dropped or
    interpolated to make the plotted curve appear cleaner.
    """

    if len(rows) != expected_count:
        raise ValueError("expected {} voltage-code rows, found {}".format(expected_count, len(rows)))
    scenario_ids = [str(row["scenario_id"]) for row in rows]
    if len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError("voltage-code CSV would contain duplicate scenario IDs")
    sorted_rows = sorted(rows, key=lambda row: float(row["vdd_a_v"]), reverse=True)
    baseline_rows = [row for row in sorted_rows if abs(float(row["vdd_a_v"]) - float(config["vnom_v"])) <= 1.0e-12]
    if len(baseline_rows) != 1:
        raise ValueError("voltage-code run needs exactly one nominal point")
    first_violation_v = float(config["timing_anchor"]["first_violation_voltage_v"])
    violation_rows = [row for row in sorted_rows if abs(float(row["vdd_a_v"]) - first_violation_v) <= 1.0e-12]
    if len(violation_rows) != 1:
        raise ValueError("voltage-code run needs exact first-violation anchor")

    baseline_code = int(baseline_rows[0]["sensor_code"])
    violation_code = int(violation_rows[0]["sensor_code"])
    monotonic_violations = []
    for previous, current in zip(sorted_rows, sorted_rows[1:]):
        if int(current["sensor_code"]) < int(previous["sensor_code"]):
            monotonic_violations.append(
                {
                    "higher_vdd_a_v": float(previous["vdd_a_v"]),
                    "higher_vdd_code": int(previous["sensor_code"]),
                    "lower_vdd_a_v": float(current["vdd_a_v"]),
                    "lower_vdd_code": int(current["sensor_code"]),
                }
            )
    invalid_scenarios = [str(row["scenario_id"]) for row in sorted_rows if not bool(row["code_valid"])]
    reset_failures = [str(row["scenario_id"]) for row in sorted_rows if int(row["reset_failure_count"]) != 0]
    metastability_risk_scenarios = [
        str(row["scenario_id"]) for row in sorted_rows if int(row["metastability_risk_count"]) != 0
    ]
    gates = {
        "baseline_centered": 15 <= baseline_code <= 17,
        "first_violation_delta_at_least_two": violation_code - baseline_code >= 2,
        "all_codes_valid": not invalid_scenarios,
        "all_resets_pass": not reset_failures,
        "monotonic_with_droop": not monotonic_violations,
        "metastability_risk_reported": True,
    }
    return {
        "status": "PASS" if all(gates.values()) else "FAIL",
        "scenario_count": len(sorted_rows),
        "baseline_code": baseline_code,
        "first_violation_code": violation_code,
        "first_violation_code_delta": violation_code - baseline_code,
        "invalid_scenarios": invalid_scenarios,
        "reset_failure_scenarios": reset_failures,
        "metastability_risk_scenarios": metastability_risk_scenarios,
        "monotonicity_violations": monotonic_violations,
        "gates": gates,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    """Expose only reproducible run ownership, timeout, and safe-resume controls."""

    parser = argparse.ArgumentParser(description="run calibrated Phase-2 static voltage-to-code HSPICE sweep")
    parser.add_argument("--config", required=True, type=Path, help="Phase 2 configuration JSON")
    parser.add_argument("--output-dir", required=True, type=Path, help="new task-owned output directory")
    parser.add_argument("--timeout-s", type=int, default=180, help="per-deck HSPICE timeout")
    parser.add_argument("--resume", action="store_true", help="revalidate and continue only compatible task-owned points")
    return parser


def main(argv: Iterable[str] = None) -> int:
    """Execute all static points, publish CSV/summary, and fail loudly on any gate."""

    args = build_argument_parser().parse_args(argv)
    if args.timeout_s <= 0:
        raise ValueError("timeout-s must be positive")
    config = load_json(args.config)
    study = characterization(config)
    points = voltage_points(config)
    point_candidate = candidate(config)
    phase1 = load_json(resolve_repo_path(str(config["phase1_config_path"])))
    hspice = run_dc_sweep.require_regular_file(Path(phase1["hspice"]), "HSPICE", executable=True)
    hspice_version = run_dc_sweep.hspice_version(hspice)
    if str(phase1["expected_hspice_version"]) not in hspice_version:
        raise RuntimeError("unexpected HSPICE version: {}".format(hspice_version))

    output_dir = args.output_dir.resolve()
    if output_dir.exists() and not args.resume:
        raise ValueError("refusing to overwrite voltage-code run: {}".format(output_dir))
    if args.resume and not output_dir.is_dir():
        raise ValueError("--resume requires an existing voltage-code directory")
    output_dir.mkdir(parents=True, exist_ok=args.resume)
    manifest = {
        "study_name": "phase2_static_voltage_code_sweep",
        "voltage_point_count": len(points),
        "vdd_a_points_v": points,
        "characterization": study,
        "candidate": point_candidate,
        "hspice": {"executable": str(hspice), "version": hspice_version},
    }
    manifest_path = output_dir / "manifest.json"
    if args.resume:
        if load_json(manifest_path) != manifest:
            raise ValueError("voltage-code resume manifest mismatch")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    rows = []
    for vdd_a_v in points:
        point_dir = output_dir / "scenarios" / scenario_label(vdd_a_v)
        if point_dir.exists():
            try:
                row = parse_completed_point(config, output_dir, point_candidate, vdd_a_v)
            except ValueError:
                restart_incomplete_point(point_dir)
                row = run_new_point(config, hspice, output_dir, point_candidate, vdd_a_v, args.timeout_s)
        else:
            row = run_new_point(config, hspice, output_dir, point_candidate, vdd_a_v, args.timeout_s)
        rows.append(row)

    summary = validate_rows(config, rows, len(points))
    write_csv(output_dir / "voltage_code_metrics.csv", rows)
    (output_dir / "voltage_code_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "completion.rpt").write_text(
        "status={}\nscenario_count={}\n".format(summary["status"], len(rows)), encoding="ascii"
    )
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
