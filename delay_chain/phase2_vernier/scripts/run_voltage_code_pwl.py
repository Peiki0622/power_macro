#!/usr/bin/env python3
"""Validate the calibrated real-DFF code under three direct VDD_A PWL slopes.

The static voltage sweep is the authoritative droop-to-code transfer curve.
This companion runner does not replace it with an ambiguous one-shot dynamic
trace.  Instead, it runs slow, medium, and fast drops to the same 765 MHz
40-bank voltage, records the electrical supply at the actual capture instant,
and compares each valid dynamic code with the nearest static characterization
point at that measured voltage.
"""

import argparse
import csv
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


# Reuse the exact static-runner interpretation of calibration, raw DFF bits,
# decoder fields, and HSPICE validation.  This prevents a dynamic comparison
# from silently using a different M/dummy/CAL_SEL definition than the curve it
# claims to validate.
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PHASE1_SCRIPTS = REPOSITORY_ROOT / "power_macro" / "delay_chain" / "phase1" / "scripts"
SCRIPT_DIR = Path(__file__).resolve().parent
for import_path in (PHASE1_SCRIPTS, SCRIPT_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))
import generate_vernier_deck  # noqa: E402  # Renders the dynamic real-DFF electrical deck.
import run_dc_sweep  # noqa: E402  # Performs HSPICE completion and MEASFORM validation.
import run_dff_sweep  # noqa: E402  # Decodes actual DFF/reset/crossing evidence.
import run_voltage_code_sweep  # noqa: E402  # Shares calibrated topology and corrected-code definition.


# Dynamic rows retain the complete thermometer and comparator evidence from the
# static curve, followed by PWL timing/voltage observations and the chosen
# static reference.  No field derives a dynamic code from an analytical model.
CSV_FIELDS = [
    "scenario_id",
    "case_id",
    "candidate_id",
    "cal_sel",
    "droop_start_s",
    "droop_end_s",
    "vdd_a_at_launch_v",
    "vdd_a_at_capture_v",
    "vdd_a_min_v",
    "droop_at_capture_mv",
    "static_reference_vdd_a_v",
    "static_reference_code",
    "dynamic_static_code_delta",
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
    """Read one required JSON object and reject malformed provenance."""

    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def load_static_rows(path: Path, config: Dict[str, Any]) -> List[Dict[str, str]]:
    """Load only a completed, compatible static curve for dynamic comparison.

    Requiring the neighboring summary to report PASS avoids presenting a PWL
    comparison against an incomplete or non-monotonic static characterization.
    The row-level topology checks guard against accidentally comparing a PWL
    M=32/dummy=1/CAL_SEL=2 experiment to a prior candidate sweep.
    """

    if not path.is_file():
        raise ValueError("static voltage-code CSV is missing: {}".format(path))
    summary_path = path.parent / "voltage_code_summary.json"
    summary = load_json(summary_path)
    if summary.get("status") != "PASS":
        raise ValueError("dynamic PWL requires a PASS static curve: {}".format(summary_path))
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("static voltage-code CSV is empty")
    point_candidate = run_voltage_code_sweep.candidate(config)
    cal_sel = str(run_voltage_code_sweep.characterization(config)["cal_sel"])
    for row in rows:
        if row.get("candidate_id") != point_candidate["candidate_id"]:
            raise ValueError("static CSV candidate does not match PWL configuration")
        if row.get("cal_sel") != cal_sel or row.get("code_valid") != "True":
            raise ValueError("static CSV is not a valid calibrated reference curve")
    return rows


def pwl_cases(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Validate and materialize the three configured direct-droop waveforms.

    Every waveform holds VDD_A at Vnom through the reference launch time, then
    linearly falls to the exact 40-bank voltage.  The slow case reaches that
    voltage at capture; medium and fast cases hold it before capture.  This
    isolates slope sensitivity while keeping the final voltage identical.
    """

    study = run_voltage_code_sweep.characterization(config)
    required = ["pwl_droop_start_s", "pwl_final_vdd_a_v", "pwl_cases"]
    missing = [name for name in required if name not in study]
    if missing:
        raise ValueError("voltage-code PWL configuration lacks: {}".format(", ".join(missing)))
    start_s = float(study["pwl_droop_start_s"])
    final_v = float(study["pwl_final_vdd_a_v"])
    capture_s = float(config["measurement_timing"]["dff_capture_time_s"])
    stop_s = float(config["measurement_timing"]["tran_stop_s"])
    launch_s = float(config["measurement_timing"]["start_ref_s"]) + float(study["launch_offset_s"])
    if abs(start_s - float(config["measurement_timing"]["start_ref_s"])) > 1.0e-18:
        raise ValueError("PWL droop must begin at the reference launch instant")
    if final_v <= 0.0 or final_v > float(config["vnom_v"]):
        raise ValueError("PWL final VDD_A is outside supported range")
    if abs(final_v - float(config["timing_anchor"]["first_violation_voltage_v"])) > 1.0e-12:
        raise ValueError("PWL final VDD_A must equal the exact 765 MHz first-violation anchor")
    cases = study["pwl_cases"]
    if not isinstance(cases, list) or len(cases) != 3:
        raise ValueError("PWL validation requires exactly slow, medium, and fast cases")
    materialized = []
    case_ids = set()
    for item in cases:
        if not isinstance(item, dict) or "case_id" not in item or "droop_end_s" not in item:
            raise ValueError("each PWL case needs case_id and droop_end_s")
        case_id = str(item["case_id"])
        end_s = float(item["droop_end_s"])
        if case_id in case_ids:
            raise ValueError("PWL case IDs must be unique")
        if end_s <= launch_s or end_s > capture_s or end_s >= stop_s:
            raise ValueError("PWL droop end must follow sense launch and not exceed capture")
        case_ids.add(case_id)
        materialized.append(
            {
                "case_id": case_id,
                "droop_start_s": start_s,
                "droop_end_s": end_s,
                # JSON-native nested lists are intentional.  These values are
                # copied into manifest.json and must compare equal after a
                # resume reload; Python tuples would serialize as lists and
                # create a false manifest mismatch despite identical waveforms.
                "pwl_points": [
                    [0.0, float(config["vnom_v"])],
                    [start_s, float(config["vnom_v"])],
                    [end_s, final_v],
                    [stop_s, final_v],
                ],
            }
        )
    return materialized


def nearest_static_reference(rows: Sequence[Dict[str, str]], vdd_a_v: float) -> Tuple[float, int]:
    """Return the nearest measured static point; never interpolate a code bin."""

    selected = min(rows, key=lambda row: abs(float(row["vdd_a_v"]) - vdd_a_v))
    return float(selected["vdd_a_v"]), int(selected["sensor_code"])


def parse_completed_point(
    config: Dict[str, Any],
    output_dir: Path,
    point_candidate: Dict[str, Any],
    pwl_case: Dict[str, Any],
    static_rows: Sequence[Dict[str, str]],
) -> Dict[str, Any]:
    """Rebuild and validate one completed dynamic PWL scenario from HSPICE files."""

    case_id = str(pwl_case["case_id"])
    point_dir = output_dir / "scenarios" / case_id
    warning_count = run_dc_sweep.validate_listing(point_dir / "vernier_dff.lis")
    measurement_path = run_dc_sweep.find_measurement_file(point_dir, "vernier_dff")
    measurements = run_dc_sweep.parse_measurements(measurement_path)
    run_dff_sweep.require_measurements(measurements, int(point_candidate["m_stages"]))
    required_dynamic = ["vdd_a_at_launch_v", "vdd_a_at_capture_v", "vdd_a_min_v"]
    missing = [name for name in required_dynamic if measurements.get(name) is None]
    if missing:
        raise ValueError("PWL scenario lacks dynamic supply measures: {}".format(missing))
    electrical = run_dff_sweep.parse_bits(
        measurements,
        int(point_candidate["m_stages"]),
        float(config["vdd_ref_v"]),
        float(point_candidate["launch_offset_s"]),
        float(config["measurement_timing"]["dff_metastability_margin_s"]),
    )
    capture_v = float(measurements["vdd_a_at_capture_v"])
    reference_v, reference_code = nearest_static_reference(static_rows, capture_v)
    electrical.update(
        {
            "scenario_id": "pwl_{}".format(case_id),
            "candidate_id": point_candidate["candidate_id"],
            "vdd_a_v": capture_v,
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
    row = run_voltage_code_sweep.decode_row(config, electrical, int(run_voltage_code_sweep.characterization(config)["cal_sel"]))
    row.update(
        {
            "case_id": case_id,
            "droop_start_s": float(pwl_case["droop_start_s"]),
            "droop_end_s": float(pwl_case["droop_end_s"]),
            "vdd_a_at_launch_v": float(measurements["vdd_a_at_launch_v"]),
            "vdd_a_at_capture_v": capture_v,
            "vdd_a_min_v": float(measurements["vdd_a_min_v"]),
            "droop_at_capture_mv": (float(config["vnom_v"]) - capture_v) * 1000.0,
            "static_reference_vdd_a_v": reference_v,
            "static_reference_code": reference_code,
            "dynamic_static_code_delta": int(row["sensor_code"]) - reference_code,
        }
    )
    return row


def run_new_point(
    config: Dict[str, Any],
    hspice: Path,
    output_dir: Path,
    point_candidate: Dict[str, Any],
    pwl_case: Dict[str, Any],
    static_rows: Sequence[Dict[str, str]],
    timeout_s: int,
) -> Dict[str, Any]:
    """Render, execute, preserve, and reparse one new real-DFF PWL deck."""

    case_id = str(pwl_case["case_id"])
    point_dir = output_dir / "scenarios" / case_id
    point_dir.mkdir(parents=True, exist_ok=False)
    deck_path = point_dir / "vernier_dff.sp"
    generate_vernier_deck.write_dff_pwl_deck(
        config,
        int(point_candidate["m_stages"]),
        int(point_candidate["dummy_load_count"]),
        float(point_candidate["launch_offset_s"]),
        pwl_case["pwl_points"],
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
        raise RuntimeError("HSPICE returned {} for PWL case {}".format(result.returncode, case_id))
    return parse_completed_point(config, output_dir, point_candidate, pwl_case, static_rows)


def restart_incomplete_point(point_dir: Path) -> None:
    """Delete only an interrupted PWL point that has no inspectable listing evidence."""

    listing = point_dir / "vernier_dff.lis"
    if listing.is_file() and listing.stat().st_size > 0:
        raise RuntimeError("refusing to discard nonempty PWL listing: {}".format(point_dir))
    shutil.rmtree(point_dir)


def render_value(value: Any) -> str:
    """Render finite floats and preserve absent optional timing values as blank CSV cells."""

    if value is None:
        return ""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("refusing to write non-finite dynamic CSV value")
        return "{:.12e}".format(value)
    return str(value)


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    """Write all dynamic raw/corrected codes and supply observations deterministically."""

    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: render_value(row[field]) for field in CSV_FIELDS})


def validate_rows(config: Dict[str, Any], rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply dynamic publication gates while leaving every measured row visible."""

    cases = pwl_cases(config)
    if len(rows) != len(cases) or {row["case_id"] for row in rows} != {item["case_id"] for item in cases}:
        raise ValueError("dynamic run does not contain exactly the configured PWL cases")
    final_v = float(run_voltage_code_sweep.characterization(config)["pwl_final_vdd_a_v"])
    # MEASFORM=3 prints this source measurement at approximately four decimal
    # volts on the configured HSPICE release.  The exact PWL endpoint remains
    # in the generated deck and manifest, while a 0.1 mV parser tolerance
    # accepts that documented output rounding without masking a meaningful
    # millivolt-scale supply-waveform error.
    tolerance_v = 1.0e-4
    invalid = [row["scenario_id"] for row in rows if not bool(row["code_valid"])]
    reset_failures = [row["scenario_id"] for row in rows if int(row["reset_failure_count"]) != 0]
    # A Vernier transition can intentionally place one comparison close to the
    # DFF aperture.  Preserve these scenarios in the dynamic report, but do
    # not reject an otherwise valid PWL experiment solely for observing the
    # physical edge proximity that the sensor is designed to encode.
    risks = [row["scenario_id"] for row in rows if int(row["metastability_risk_count"]) != 0]
    supply_mismatch = [
        row["scenario_id"]
        for row in rows
        if abs(float(row["vdd_a_at_launch_v"]) - float(config["vnom_v"])) > tolerance_v
        or abs(float(row["vdd_a_at_capture_v"]) - final_v) > tolerance_v
        or abs(float(row["vdd_a_min_v"]) - final_v) > tolerance_v
    ]
    gates = {
        "all_codes_valid": not invalid,
        "all_resets_pass": not reset_failures,
        "measured_supply_matches_pwl_contract": not supply_mismatch,
        "metastability_risk_reported": True,
    }
    return {
        "status": "PASS" if all(gates.values()) else "FAIL",
        "scenario_count": len(rows),
        "gates": gates,
        "invalid_scenarios": invalid,
        "reset_failure_scenarios": reset_failures,
        "metastability_risk_scenarios": risks,
        "supply_mismatch_scenarios": supply_mismatch,
        "rows": [
            {
                "case_id": row["case_id"],
                "sensor_code": row["sensor_code"],
                "static_reference_code": row["static_reference_code"],
                "dynamic_static_code_delta": row["dynamic_static_code_delta"],
            }
            for row in rows
        ],
    }


def build_argument_parser() -> argparse.ArgumentParser:
    """Expose explicit static evidence and safe dynamic output ownership."""

    parser = argparse.ArgumentParser(description="run three real-DFF PWL voltage-code validation scenarios")
    parser.add_argument("--config", required=True, type=Path, help="Phase 2 configuration JSON")
    parser.add_argument("--static-csv", required=True, type=Path, help="PASS static voltage-code metrics CSV")
    parser.add_argument("--output-dir", required=True, type=Path, help="new task-owned PWL output directory")
    parser.add_argument("--timeout-s", type=int, default=180, help="per-deck HSPICE timeout")
    parser.add_argument("--resume", action="store_true", help="revalidate and continue only compatible task-owned cases")
    return parser


def main(argv: Iterable[str] = None) -> int:
    """Execute slow/medium/fast PWL scenarios and publish an auditable comparison."""

    args = build_argument_parser().parse_args(argv)
    if args.timeout_s <= 0:
        raise ValueError("timeout-s must be positive")
    config = load_json(args.config)
    static_rows = load_static_rows(args.static_csv.resolve(), config)
    cases = pwl_cases(config)
    point_candidate = run_voltage_code_sweep.candidate(config)
    phase1 = load_json(run_voltage_code_sweep.resolve_repo_path(str(config["phase1_config_path"])))
    hspice = run_dc_sweep.require_regular_file(Path(phase1["hspice"]), "HSPICE", executable=True)
    hspice_version = run_dc_sweep.hspice_version(hspice)
    if str(phase1["expected_hspice_version"]) not in hspice_version:
        raise RuntimeError("unexpected HSPICE version: {}".format(hspice_version))

    output_dir = args.output_dir.resolve()
    if output_dir.exists() and not args.resume:
        raise ValueError("refusing to overwrite PWL voltage-code run: {}".format(output_dir))
    if args.resume and not output_dir.is_dir():
        raise ValueError("--resume requires an existing PWL voltage-code directory")
    output_dir.mkdir(parents=True, exist_ok=args.resume)
    manifest = {
        "study_name": "phase2_pwl_voltage_code_validation",
        "candidate": point_candidate,
        "pwl_cases": cases,
        "static_csv": str(args.static_csv.resolve()),
        "hspice": {"executable": str(hspice), "version": hspice_version},
    }
    manifest_path = output_dir / "manifest.json"
    if args.resume:
        if load_json(manifest_path) != manifest:
            raise ValueError("PWL voltage-code resume manifest mismatch")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    rows = []
    for pwl_case in cases:
        point_dir = output_dir / "scenarios" / str(pwl_case["case_id"])
        if point_dir.exists():
            try:
                row = parse_completed_point(config, output_dir, point_candidate, pwl_case, static_rows)
            except ValueError:
                restart_incomplete_point(point_dir)
                row = run_new_point(config, hspice, output_dir, point_candidate, pwl_case, static_rows, args.timeout_s)
        else:
            row = run_new_point(config, hspice, output_dir, point_candidate, pwl_case, static_rows, args.timeout_s)
        rows.append(row)

    summary = validate_rows(config, rows)
    write_csv(output_dir / "pwl_code_metrics.csv", rows)
    (output_dir / "pwl_code_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "completion.rpt").write_text(
        "status={}\nscenario_count={}\n".format(summary["status"], len(rows)), encoding="ascii"
    )
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
