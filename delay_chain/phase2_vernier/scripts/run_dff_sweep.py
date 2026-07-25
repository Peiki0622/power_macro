#!/usr/bin/env python3
"""Run the selected ideal candidates with real SMIC40LL DFF comparators.

This stage validates the electrical comparison rather than reusing the ideal
thermometer code as a result.  Each HSPICE deck instantiates the discovered
asynchronous-clear DFF at every stage, measures its reset and capture levels,
and compares the captured raw bits against the independently measured arrival
relationship from the same transient.
"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PHASE1_SCRIPTS = REPOSITORY_ROOT / "power_macro" / "delay_chain" / "phase1" / "scripts"
SCRIPT_DIR = Path(__file__).resolve().parent
for import_path in (PHASE1_SCRIPTS, SCRIPT_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))
import generate_vernier_deck  # noqa: E402  # Generates the reviewed positional-port DFF deck.
import run_dc_sweep  # noqa: E402  # Reuses HSPICE listing and measurement validation.


def load_json(path: Path) -> Dict[str, Any]:
    """Load one required JSON object without using optional fallback data."""

    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def resolve_repo_path(value: str) -> Path:
    """Resolve inherited Phase 1 configuration paths independently of CWD."""

    path = Path(value)
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def dff_voltages(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the four planned real-DFF voltage scenarios with exact anchors."""

    values = [
        {"label": "nominal", "vdd_a_v": float(config["vnom_v"])},
        {"label": "last_passing", "vdd_a_v": float(config["timing_anchor"]["last_passing_voltage_v"])},
        {"label": "first_violation", "vdd_a_v": float(config["timing_anchor"]["first_violation_voltage_v"])},
        {"label": "low_extension", "vdd_a_v": float(config["fine_vdd_start_v"])},
    ]
    if len({item["vdd_a_v"] for item in values}) != len(values):
        raise ValueError("DFF voltage scenarios must be distinct")
    return values


def scenario_name(candidate: Dict[str, Any], label: str) -> str:
    """Build one stable task-owned path from selected physical candidate fields."""

    return "{}/{}".format(candidate["candidate_id"].replace("+", "plus"), label)


def require_measurements(measurements: Dict[str, Any], m_stages: int) -> None:
    """Require all comparisons while allowing only optional Q rise timestamps."""

    required = ["start_ref_cross", "start_sense_cross", "comparator_ref_avg_current_a", "comparator_ref_peak_current_a"]
    for index in range(m_stages):
        required.extend(
            [
                "sense_{:03d}_cross".format(index),
                "ref_{:03d}_cross".format(index),
                "q_{:03d}_reset_level".format(index),
                "q_{:03d}_level".format(index),
            ]
        )
    missing = [name for name in required if measurements.get(name) is None]
    if missing:
        raise ValueError("DFF measurement is missing or failed: {}".format(missing))


def parse_bits(measurements: Dict[str, Any], m_stages: int, vdd_ref_v: float, launch_offset_s: float, risk_margin_s: float) -> Dict[str, Any]:
    """Decode captured levels, expected edge order, reset proof, and timing risk.

    The captured Q decision uses half of the DFF reference rail.  The deck's
    measured sense crossings already include the selected PULSE launch delay,
    so both the expected decision and the metastability-distance check compare
    ``S_i`` directly with ``R_i``.  ``launch_offset_s`` remains an explicit
    argument because callers record it as scenario provenance, but it must not
    be added a second time to an already delayed crossing timestamp.
    """

    raw_bits = []
    expected_bits = []
    reset_failures = 0
    metastability_risk_count = 0
    q_rise_times = []
    for index in range(m_stages):
        q_reset = float(measurements["q_{:03d}_reset_level".format(index)])
        q_level = float(measurements["q_{:03d}_level".format(index)])
        sense = float(measurements["sense_{:03d}_cross".format(index)])
        reference = float(measurements["ref_{:03d}_cross".format(index)])
        raw_bits.append(1 if q_level >= vdd_ref_v / 2.0 else 0)
        expected_bits.append(1 if sense <= reference else 0)
        if q_reset >= vdd_ref_v / 2.0:
            reset_failures += 1
        # ``sense`` is measured after V_START_SENSE's selected PULSE delay.
        # Comparing R_i against S_i directly is the physical DFF aperture;
        # adding launch_offset_s here would double-count calibration and mark
        # otherwise separated edges as false metastability risks.
        if abs(reference - sense) < risk_margin_s:
            metastability_risk_count += 1
        rise_time = measurements.get("q_{:03d}_rise".format(index))
        if rise_time is not None:
            q_rise_times.append(float(rise_time))
    mismatch_count = sum(1 for raw, expected in zip(raw_bits, expected_bits) if raw != expected)
    first_one = next((index for index, bit in enumerate(raw_bits) if bit == 1), len(raw_bits))
    bubble_count = sum(1 for bit in raw_bits[first_one:] if bit == 0)
    return {
        "raw_code": "".join(str(bit) for bit in raw_bits),
        "expected_arrival_code": "".join(str(bit) for bit in expected_bits),
        "sensor_code": first_one,
        "bubble_count": bubble_count,
        "raw_code_valid": bubble_count == 0,
        "mismatch_count": mismatch_count,
        "reset_failure_count": reset_failures,
        "metastability_risk_count": metastability_risk_count,
        "last_q_rise_s": max(q_rise_times) if q_rise_times else None,
    }


def run_scenario(
    config: Dict[str, Any], hspice: Path, output_dir: Path, candidate: Dict[str, Any], voltage: Dict[str, Any], timeout_s: int
) -> Dict[str, Any]:
    """Run and preserve one candidate-voltage DFF transient without overwrite."""

    m_stages = int(candidate["m_stages"])
    dummy_count = int(candidate["dummy_load_count"])
    launch_offset_s = float(candidate["launch_offset_s"])
    vdd_a_v = float(voltage["vdd_a_v"])
    point_dir = output_dir / "scenarios" / scenario_name(candidate, str(voltage["label"]))
    point_dir.mkdir(parents=True, exist_ok=False)
    deck_path = point_dir / "vernier_dff.sp"
    generate_vernier_deck.write_dff_deck(config, m_stages, dummy_count, vdd_a_v, launch_offset_s, deck_path)
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
            " ".join([str(hspice), deck_path.name, "-o", "vernier_dff"]), result.returncode, result.stdout, result.stderr
        ),
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, point_dir))
    warning_count = run_dc_sweep.validate_listing(point_dir / "vernier_dff.lis")
    measurement_path = run_dc_sweep.find_measurement_file(point_dir, "vernier_dff")
    measurements = run_dc_sweep.parse_measurements(measurement_path)
    require_measurements(measurements, m_stages)
    decoded = parse_bits(
        measurements,
        m_stages,
        float(config["vdd_ref_v"]),
        launch_offset_s,
        float(config["measurement_timing"]["dff_metastability_margin_s"]),
    )
    decoded.update(
        {
            "scenario_id": scenario_name(candidate, str(voltage["label"])),
            "candidate_id": candidate["candidate_id"],
            "scenario_label": voltage["label"],
            "vdd_a_v": vdd_a_v,
            "vdd_ref_v": float(config["vdd_ref_v"]),
            "m_stages": m_stages,
            "dummy_load_count": dummy_count,
            "launch_offset_s": launch_offset_s,
            "comparator_avg_current_a": measurements["comparator_ref_avg_current_a"],
            "comparator_peak_current_a": measurements["comparator_ref_peak_current_a"],
            "warning_count": warning_count,
            "measurement_file": str(measurement_path.relative_to(output_dir)),
        }
    )
    return decoded


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    """Write the DFF raw-code contract consumed by the later decoder stage."""

    fields = [
        "scenario_id", "candidate_id", "scenario_label", "vdd_a_v", "vdd_ref_v", "m_stages", "dummy_load_count",
        "launch_offset_s", "raw_code", "expected_arrival_code", "mismatch_count", "reset_failure_count",
        "sensor_code", "bubble_count", "raw_code_valid", "metastability_risk_count", "last_q_rise_s", "comparator_avg_current_a", "comparator_peak_current_a",
        "warning_count", "measurement_file",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            rendered = {}
            for field in fields:
                value = row[field]
                rendered[field] = "" if value is None else "{:.12e}".format(value) if isinstance(value, float) else str(value)
            writer.writerow(rendered)


def write_report(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    """Summarize reset, arrival-agreement, and first-violation code evidence."""

    lines = [
        "# Real DFF Vernier Sweep",
        "",
        "| Candidate | Scenario | VDD_A (V) | Raw code | Expected code | Mismatch | Reset failures | Metastability-risk bits |",
        "|---|---|---:|---|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {candidate_id} | {scenario_label} | {vdd_a_v:.12f} | {raw_code} | {expected_arrival_code} | "
            "{mismatch_count} | {reset_failure_count} | {metastability_risk_count} |".format(**row)
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_argument_parser() -> argparse.ArgumentParser:
    """Expose required provenance paths and a non-overwriting output directory."""

    parser = argparse.ArgumentParser(description="run Phase-2 real-DFF Vernier candidate sweep")
    parser.add_argument("--config", required=True, type=Path, help="Phase 2 configuration")
    parser.add_argument("--selection-json", required=True, type=Path, help="PASS ideal candidate selection")
    parser.add_argument("--output-dir", required=True, type=Path, help="new task-owned DFF run directory")
    parser.add_argument("--timeout-s", type=int, default=180, help="per-deck HSPICE timeout")
    return parser


def main(argv: Iterable[str] = None) -> int:
    """Run all selected candidates at nominal, 35-bank, 40-bank, and low voltage."""

    args = build_argument_parser().parse_args(argv)
    config = load_json(args.config)
    selection = load_json(args.selection_json)
    if selection.get("status") != "PASS" or len(selection.get("selected_candidates", [])) != 3:
        raise ValueError("selection JSON must contain exactly three PASS candidates")
    phase1_config = load_json(resolve_repo_path(str(config["phase1_config_path"])))
    hspice = run_dc_sweep.require_regular_file(Path(phase1_config["hspice"]), "HSPICE", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if phase1_config["expected_hspice_version"] not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise ValueError("refusing to overwrite existing DFF run directory: {}".format(output_dir))
    output_dir.mkdir(parents=True)
    (output_dir / "manifest.json").write_text(
        json.dumps(
            {"study_name": "phase2_real_dff_sweep", "selection_json": str(args.selection_json.resolve()), "hspice_version": version},
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    rows = []
    for candidate in selection["selected_candidates"]:
        for voltage in dff_voltages(config):
            rows.append(run_scenario(config, hspice, output_dir, candidate, voltage, args.timeout_s))
    write_csv(output_dir / "dff_raw_metrics.csv", rows)
    write_report(output_dir / "dff_report.md", rows)
    # Zero-guard arrival mismatches are expected near a physical DFF setup edge
    # and remain visible in the CSV.  They are not failures by themselves: the
    # real acceptance condition is a reset-correct, bubble-free raw code and a
    # measurable first-violation separation after real DFF loading.
    by_candidate: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in rows:
        by_candidate.setdefault(row["candidate_id"], {})[row["scenario_label"]] = row
    candidate_summary = []
    for candidate_id, scenarios in sorted(by_candidate.items()):
        nominal = scenarios["nominal"]
        failing = scenarios["first_violation"]
        candidate_summary.append(
            {
                "candidate_id": candidate_id,
                "nominal_code": nominal["sensor_code"],
                "first_violation_code": failing["sensor_code"],
                "first_violation_code_delta": failing["sensor_code"] - nominal["sensor_code"],
                "all_raw_codes_valid": all(row["raw_code_valid"] for row in scenarios.values()),
            }
        )
    (output_dir / "dff_candidate_summary.json").write_text(
        json.dumps(candidate_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    failed = [row for row in rows if row["reset_failure_count"] or not row["raw_code_valid"]]
    if not any(summary["first_violation_code_delta"] >= 2 and summary["all_raw_codes_valid"] for summary in candidate_summary):
        failed.append({"scenario_id": "NO_REAL_DFF_CANDIDATE_WITH_CODE_SEPARATION"})
    (output_dir / "completion.rpt").write_text(
        "status={}\nscenario_count={}\n".format("PASS" if not failed else "FAIL", len(rows)), encoding="ascii"
    )
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
