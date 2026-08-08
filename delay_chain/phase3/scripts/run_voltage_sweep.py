#!/usr/bin/env python3
"""Run the final Phase-3 physical voltage-to-code characterization.

The runner is intentionally small and experiment-specific.  It executes the
already selected 32-stage physical deck once per VDD point, reads the real
SMIC40LL DFF output levels, and then applies the shared thermometer decoder.
No delay equation, fitted curve, or ideal comparator result is substituted for
the HSPICE measurements.  The same command also supports the single RVT/RVT
control required by Step 9 by replacing only the companion path cell/CDL.

All simulator products are kept below the caller-provided directory, normally
``delay_chain/phase3/runs/voltage_sweep`` or
``delay_chain/phase3/runs/voltage_sweep_rvt_rvt``.  This prevents HSPICE's
fixed-name listing and measurement files from colliding across voltage points
or scattering into the repository root.
"""

import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


# The Phase-3 scripts are executed directly, so import the reviewed Phase-1
# HSPICE parser and Phase-2 decoder through explicit task-local paths.
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
PHASE1_CONFIG = WORKSPACE_ROOT / "power_macro/delay_chain/phase1/phase1_config.json"
PHASE1_SCRIPTS = WORKSPACE_ROOT / "power_macro/delay_chain/phase1/scripts"
PHASE2_SCRIPTS = WORKSPACE_ROOT / "power_macro/delay_chain/phase2_vernier/scripts"
PHASE3_SCRIPTS = Path(__file__).resolve().parent
EMPTY_SUBCKT_INCLUDE = (
    WORKSPACE_ROOT / "power_macro/delay_chain/phase3/spice/includes/empty_subckt.sp_cal"
)
for import_path in (PHASE1_SCRIPTS, PHASE2_SCRIPTS, PHASE3_SCRIPTS):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import decode_vernier_code  # noqa: E402  # Shared 0*1* majority/transition decoder.
import generate_phase3_deck  # noqa: E402  # Real BUF/MXT2/INV/DFF deck renderer.
import run_dc_sweep  # noqa: E402  # Listing and MEASFORM=3 validation helpers.


# This CSV is the compact interchange contract for both the selected sensor
# and the same-rail control.  The raw and corrected words remain adjacent to
# every derived code so a report can always trace a code step to real Q levels.
CSV_FIELDS = [
    "mode",
    "point_kind",
    "vdd_v",
    "droop_mv",
    "raw_thermometer_word",
    "normalized_raw_word",
    "corrected_thermometer_word",
    "sensor_code",
    "raw_bubble_count",
    "bubble_count",
    "code_valid",
    "reset_failure_count",
    "rvt_031_cross_s",
    "lvt_031_cross_s",
    "rvt_lvt_diff_031_s",
    "final_taps_arrived",
    "residual_code",
    "measurement_file",
]


def load_json(path: Path) -> Dict[str, Any]:
    """Read a required JSON object and reject accidental list/scalar input."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def voltage_points(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build the exact 0.5 mV grid plus the two non-grid timing anchors.

    Decimal arithmetic preserves the requested endpoints exactly.  The grid
    contains 121 points from 1.1000 V down to 1.0400 V; the last-pass and
    first-violation anchors are then added when they do not coincide with a
    grid point.  Each point is tagged so the report can distinguish required
    grid coverage from anchor-only measurements.
    """

    low = Decimal(str(config["fine_vdd_start_v"]))
    high = Decimal(str(config["fine_vdd_stop_v"]))
    step = Decimal(str(config["fine_vdd_step_v"]))
    if step <= 0 or low > high:
        raise ValueError("fine VDD range must be ascending with a positive step")
    points: Dict[Decimal, str] = {}
    current = low
    while current <= high:
        points[current] = "grid"
        current += step
    if current - step != high:
        raise ValueError("fine VDD range does not land on its endpoint")

    # The anchor values are intentionally not rounded to the 0.5 mV grid.  A
    # direct HSPICE run at each exact voltage is required for the specified
    # delta_code_last and delta_code_crit quantities.
    anchors = (
        (Decimal(str(config["last_pass_v"])), "last_pass_anchor"),
        (Decimal(str(config["first_violation_v"])), "first_violation_anchor"),
    )
    for voltage, kind in anchors:
        if voltage < low or voltage > high:
            raise ValueError("timing anchor lies outside fine sweep: {}".format(voltage))
        points.setdefault(voltage, kind)
    return [
        {"vdd_v": float(voltage), "point_kind": kind}
        for voltage, kind in sorted(points.items())
    ]


def wide_voltage_points(config: Dict[str, Any], kind: str) -> List[Dict[str, Any]]:
    """Build only the three voltage sets specified for the wide-range task.

    This deliberately is not a generic sweep language.  ``baseline`` uses the
    10 mV range-limit grid, ``screen`` uses the five fixed decision points, and
    ``final`` uses the 5 mV characterization grid plus the two retained timing
    anchors.  Decimal construction makes the evidence set exact and stable.
    """

    wide = config["wide_range"]
    if kind == "screen":
        return [{"vdd_v": float(value), "point_kind": "screen"} for value in wide["screen_vdd_points_v"]]
    if kind not in ("baseline", "final"):
        raise ValueError("wide-range kind must be baseline, screen, or final")
    low = Decimal(str(wide["vdd_min_v"]))
    high = Decimal(str(wide["vdd_max_v"]))
    step = Decimal(str(wide["coarse_step_v"] if kind == "baseline" else wide["final_step_v"]))
    points: Dict[Decimal, str] = {}
    current = low
    while current <= high:
        points[current] = "grid"
        current += step
    if current - step != high:
        raise ValueError("wide-range VDD grid does not land on its endpoint")
    if kind == "final":
        for voltage, label in ((Decimal(str(config["last_pass_v"])), "last_pass_anchor"), (Decimal(str(config["first_violation_v"])), "first_violation_anchor")):
            points.setdefault(voltage, label)
    return [{"vdd_v": float(voltage), "point_kind": label} for voltage, label in sorted(points.items())]


def scenario_label(vdd_v: float) -> str:
    """Make a stable directory label without losing the twelve-digit voltage."""

    return "v{:0.12f}".format(float(vdd_v)).replace(".", "p")


def finite_or_none(value: Optional[float], name: str) -> Optional[float]:
    """Keep failed optional crossing measures explicit while rejecting NaN."""

    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("{} is not finite".format(name))
    return number


def selected_path_inputs(
    selected: Dict[str, Any], config: Dict[str, Any], mode: str
) -> Dict[str, Any]:
    """Return the companion CDL/cell for the selected sensor or RVT control.

    The control deliberately keeps the final sensor's one-input dummy load,
    DFF bank, and calibration topology.  Only the LVT companion inverter and
    its source CDL are replaced with the already characterized RVT inverter;
    this isolates voltage sensitivity without introducing a second control
    architecture.
    """

    if mode not in ("rvt_lvt", "rvt_rvt"):
        raise ValueError("mode must be rvt_lvt or rvt_rvt")
    if mode == "rvt_lvt":
        return {
            "lvt_cdl": Path(selected["source_files"]["lvt_cdl"]),
            "lvt_cell": str(config["selected_lvt_cell"]),
        }
    return {
        "lvt_cdl": Path(selected["source_files"]["rvt_cdl"]),
        "lvt_cell": str(config["rvt_inverter_cell"]),
    }


def run_point(
    config: Dict[str, Any],
    selected: Dict[str, Any],
    phase1: Dict[str, Any],
    hspice: Path,
    output_dir: Path,
    point: Dict[str, Any],
    mode: str,
    timeout_s: int,
    active_mask: Optional[int] = None,
    q_read_time_ns: float = 2.5,
    stop_time_ns: float = 4.0,
    baseline_code: Optional[int] = None,
) -> Dict[str, Any]:
    """Generate, execute, validate, and decode one physical voltage point."""

    voltage = float(point["vdd_v"])
    point_dir = output_dir / "scenarios" / scenario_label(voltage)
    point_dir.mkdir(parents=True, exist_ok=False)
    if not EMPTY_SUBCKT_INCLUDE.is_file():
        raise ValueError("missing task-owned empty_subckt.sp_cal placeholder")
    # The installed LVT CDL has a historical relative include.  Copying the
    # harmless placeholder beside this deck satisfies that dependency without
    # modifying the immutable PDK or writing files into its source directory.
    shutil.copyfile(EMPTY_SUBCKT_INCLUDE, point_dir / "empty_subckt.sp_cal")

    companion = selected_path_inputs(selected, config, mode)
    deck_path = point_dir / "phase3_voltage_code.sp"
    generate_phase3_deck.write_real_dff_vernier_deck(
        output_path=deck_path,
        rvt_cdl=Path(selected["source_files"]["rvt_cdl"]),
        lvt_cdl=companion["lvt_cdl"],
        model_library=Path(phase1["model_library"]),
        corner=str(config["corner"]),
        temperature_c=float(config["temperature_c"]),
        vdd_v=voltage,
        rvt_cell=str(config["rvt_inverter_cell"]),
        lvt_cell=companion["lvt_cell"],
        dff_cell=str(config["rvt_dff_cell"]),
        stages=int(config["stages"]),
        lvt_dummy_load_count=int(config["selected_dummy_load_count"]),
        launch_offset_ps=0.0,
        launch_delayed_path=str(config["ideal_launch_delayed_path"]),
        cal_sel=int(config["selected_cal_sel"]),
        buffer_cell=str(config["rvt_buffer_cell"]),
        mux_cell=str(config["rvt_mux_cell"]),
        active_stage_mask=active_mask,
        q_read_time_ns=q_read_time_ns,
        stop_time_ns=stop_time_ns,
    )
    prefix = "phase3_voltage_code"
    result = subprocess.run(
        [str(hspice), deck_path.name, "-o", prefix],
        cwd=str(point_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        timeout=timeout_s,
    )
    (point_dir / "hspice_command.log").write_text(
        "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            " ".join([str(hspice), deck_path.name, "-o", prefix]),
            result.returncode,
            result.stdout,
            result.stderr,
        ),
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, point_dir))

    run_dc_sweep.validate_listing(point_dir / (prefix + ".lis"))
    measurement = run_dc_sweep.find_measurement_file(point_dir, prefix)
    values = run_dc_sweep.parse_measurements(measurement)
    raw_bits: List[str] = []
    reset_failures = 0
    for index in range(int(config["stages"])):
        reset_level = values.get("q_{:03d}_reset_level".format(index))
        q_level = values.get("q_{:03d}_level".format(index))
        if reset_level is None or q_level is None:
            raise ValueError("missing q_{:03d} reset/capture measurement".format(index))
        if float(reset_level) > 0.1 * voltage:
            reset_failures += 1
        raw_bits.append("1" if float(q_level) >= 0.5 * voltage else "0")
    raw_word = "".join(raw_bits)
    normalized_word = raw_word
    if bool(config.get("thermometer_invert", False)):
        normalized_word = "".join("1" if bit == "0" else "0" for bit in raw_word)
    decoded = decode_vernier_code.decode_word(normalized_word)
    rvt_cross = finite_or_none(values.get("rvt_031_cross"), "RVT final crossing")
    lvt_cross = finite_or_none(values.get("lvt_031_cross"), "LVT final crossing")
    differential = finite_or_none(values.get("rvt_lvt_diff_031"), "RVT/LVT final differential")
    final_taps_arrived = int(
        rvt_cross is not None and lvt_cross is not None and differential is not None
        and rvt_cross <= q_read_time_ns * 1.0e-09 and lvt_cross <= q_read_time_ns * 1.0e-09
    )
    baseline = int(config["baseline_code"] if baseline_code is None else baseline_code)
    polarity = int(config["code_polarity"])
    return {
        "mode": mode,
        "point_kind": str(point["point_kind"]),
        "vdd_v": voltage,
        "droop_mv": (float(config["vnom_v"]) - voltage) * 1000.0,
        "raw_thermometer_word": raw_word,
        "normalized_raw_word": decoded["raw_code"],
        "corrected_thermometer_word": decoded["corrected_code"],
        "sensor_code": int(decoded["sensor_code"]),
        "raw_bubble_count": int(decoded["raw_bubble_count"]),
        "bubble_count": int(decoded["bubble_count"]),
        "code_valid": int(bool(decoded["code_valid"])),
        "reset_failure_count": reset_failures,
        "rvt_031_cross_s": rvt_cross,
        "lvt_031_cross_s": lvt_cross,
        "rvt_lvt_diff_031_s": differential,
        "final_taps_arrived": final_taps_arrived,
        "residual_code": polarity * (int(decoded["sensor_code"]) - baseline),
        "measurement_file": str(measurement.relative_to(output_dir)),
    }


def render_value(value: Any) -> str:
    """Render finite numerical values deterministically for CSV evidence."""

    if value is None:
        return ""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("refusing to write non-finite CSV value")
        return "{:.12e}".format(value)
    return str(value)


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    """Write all measured fields while rejecting accidental schema drift."""

    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: render_value(row[field]) for field in CSV_FIELDS})


def validate_rows(
    config: Dict[str, Any], rows: Sequence[Dict[str, Any]], points: Sequence[Dict[str, Any]], mode: str
) -> Dict[str, Any]:
    """Compute Step-8 metrics and a strict physical-data completion gate.

    A code response is considered generally monotonic when normalized code is
    nondecreasing as droop increases, except for at most one isolated one-code
    local reversal across the full 123-point characterization.  That explicit
    tolerance matches the plan's "generally monotonic" criterion while still
    rejecting repeated reversals or any multi-code regression.  No row is
    removed to satisfy this gate; every reversal is published verbatim in the
    summary.  The RVT/RVT control is measured with the same checks but is not
    required to have the selected sensor's minimum three-code anchor movement.
    """

    expected_voltages = [float(point["vdd_v"]) for point in points]
    measured_voltages = [float(row["vdd_v"]) for row in rows]
    if len(rows) != len(points) or sorted(expected_voltages) != sorted(measured_voltages):
        raise ValueError("voltage sweep row count or voltage set does not match the plan")
    ordered = sorted(rows, key=lambda row: float(row["droop_mv"]))
    monotonic_violations = []
    maximum_reversal_codes = 0
    for previous, current in zip(ordered, ordered[1:]):
        if int(current["residual_code"]) < int(previous["residual_code"]):
            reversal_codes = int(previous["residual_code"]) - int(current["residual_code"])
            maximum_reversal_codes = max(maximum_reversal_codes, reversal_codes)
            monotonic_violations.append(
                {
                    "previous_vdd_v": float(previous["vdd_v"]),
                    "previous_residual": int(previous["residual_code"]),
                    "current_vdd_v": float(current["vdd_v"]),
                    "current_residual": int(current["residual_code"]),
                    "reversal_codes": reversal_codes,
                }
            )

    def exact_row(voltage: float) -> Dict[str, Any]:
        matches = [row for row in rows if abs(float(row["vdd_v"]) - voltage) <= 1.0e-12]
        if len(matches) != 1:
            raise ValueError("expected one exact voltage row for {} V".format(voltage))
        return matches[0]

    nominal = exact_row(float(config["vnom_v"]))
    last_pass = exact_row(float(config["last_pass_v"]))
    critical = exact_row(float(config["first_violation_v"]))
    delta_last = int(last_pass["sensor_code"]) - int(config["baseline_code"])
    delta_critical = int(critical["sensor_code"]) - int(config["baseline_code"])
    invalid = [row for row in rows if not int(row["code_valid"])]
    reset_failures = [row for row in rows if int(row["reset_failure_count"]) != 0]
    gates = {
        "all_code_words_valid": not invalid,
        "all_resets_pass": not reset_failures,
        "generally_monotonic_with_droop": len(monotonic_violations) <= 1 and maximum_reversal_codes <= 1,
    }
    if mode == "rvt_lvt":
        # Only the selected sensor is required to land on the configured
        # center code.  The RVT/RVT control is intentionally allowed to sit at
        # an endpoint; that endpoint lock is the sensitivity result being
        # compared, not a calibration failure.
        gates.update(
            {
                "nominal_matches_config_baseline": int(nominal["sensor_code"]) == int(config["baseline_code"]),
                "nominal_centered": int(config["acceptable_nominal_code_min"]) <= int(nominal["sensor_code"]) <= int(config["acceptable_nominal_code_max"]),
            }
        )
        gates["critical_anchor_moves_at_least_three_codes"] = delta_critical >= 3
    return {
        "status": "PASS" if all(gates.values()) else "FAIL",
        "mode": mode,
        "scenario_count": len(rows),
        "grid_point_count": sum(1 for point in points if point["point_kind"] == "grid"),
        "anchor_point_count": sum(1 for point in points if point["point_kind"] != "grid"),
        "baseline_code": int(config["baseline_code"]),
        "nominal_code": int(nominal["sensor_code"]),
        "delta_code_last": delta_last,
        "delta_code_crit": delta_critical,
        "monotonicity_violation_count": len(monotonic_violations),
        "maximum_reversal_codes": maximum_reversal_codes,
        "monotonicity_violations": monotonic_violations,
        "invalid_scenarios": [str(row["vdd_v"]) for row in invalid],
        "reset_failure_scenarios": [str(row["vdd_v"]) for row in reset_failures],
        "gates": gates,
    }


def validate_wide_rows(rows: Sequence[Dict[str, Any]], points: Sequence[Dict[str, Any]], baseline_code: int) -> Dict[str, Any]:
    """Apply the narrow, physical wide-range completion contract.

    Every point is retained, including an invalid word or a missing final-tap
    crossing.  The summary therefore diagnoses saturation separately from a
    low-voltage timing/settling limit instead of hiding either condition.
    """

    if len(rows) != len(points):
        raise ValueError("wide-range row count does not match requested points")
    ordered = sorted(rows, key=lambda row: float(row["droop_mv"]))
    reversals = []
    for previous, current in zip(ordered, ordered[1:]):
        if int(current["residual_code"]) < int(previous["residual_code"]):
            reversals.append(int(previous["residual_code"]) - int(current["residual_code"]))
    invalid = [float(row["vdd_v"]) for row in rows if not int(row["code_valid"])]
    resets = [float(row["vdd_v"]) for row in rows if int(row["reset_failure_count"]) != 0]
    late = [float(row["vdd_v"]) for row in rows if not int(row["final_taps_arrived"])]
    saturated = [float(row["vdd_v"]) for row in ordered if int(row["sensor_code"]) >= 32]
    max_arrival = max(
        [max(float(row["rvt_031_cross_s"]), float(row["lvt_031_cross_s"])) for row in rows if row["rvt_031_cross_s"] is not None and row["lvt_031_cross_s"] is not None] or [0.0]
    )
    gates = {
        "all_code_words_valid": not invalid,
        "all_resets_pass": not resets,
        "all_final_taps_arrive_before_read": not late,
        "no_pre_0p70_saturation": not [value for value in saturated if value > 0.700000000001],
        "generally_monotonic_with_droop": len(reversals) <= 1 and max(reversals or [0]) <= 1,
    }
    return {
        "status": "PASS" if all(gates.values()) else "FAIL",
        "scenario_count": len(rows),
        "baseline_code": int(baseline_code),
        "nominal_code": next(int(row["sensor_code"]) for row in rows if abs(float(row["vdd_v"]) - 1.1) <= 1.0e-12),
        "first_saturation_v": saturated[0] if saturated else None,
        "first_invalid_v": invalid[0] if invalid else None,
        "late_final_tap_v": late,
        "maximum_final_tap_arrival_s": max_arrival,
        "maximum_reversal_codes": max(reversals or [0]),
        "monotonicity_violation_count": len(reversals),
        "gates": gates,
    }


def write_report(path: Path, summary: Dict[str, Any], rows: Sequence[Dict[str, Any]], mode: str) -> None:
    """Write a concise sweep report with exact anchor and decimated curve data."""

    ordered = sorted(rows, key=lambda row: float(row["vdd_v"]), reverse=True)
    selected = [row for index, row in enumerate(ordered) if index % 10 == 0]
    selected.extend(row for row in ordered if row["point_kind"] != "grid")
    selected = sorted({float(row["vdd_v"]): row for row in selected}.values(), key=lambda row: float(row["vdd_v"]), reverse=True)
    lines = [
        "# Phase-3 Physical Voltage Sweep",
        "",
        "Mode: `{}`; CAL_SEL={} ; all frontend cells use VDD_A/VSS_A.".format(mode, summary.get("cal_sel", "see phase3_config.json")),
        "",
        "The CSV contains every 0.5 mV grid point plus exact timing anchors. `residual_code` is `code_polarity * (sensor_code - baseline_code)`.",
        "",
        "## Summary",
        "",
        "- Status: `{}`".format(summary["status"]),
        "- Baseline code: `{}`; nominal observed code: `{}`".format(summary["baseline_code"], summary["nominal_code"]),
        "- `delta_code_last`: `{}`; `delta_code_crit`: `{}`".format(summary["delta_code_last"], summary["delta_code_crit"]),
        "- Local monotonicity reversals: `{}`; maximum reversal: `{}` code".format(
            summary["monotonicity_violation_count"], summary["maximum_reversal_codes"]
        ),
        "",
        "## Curve Samples",
        "",
        "| Point | VDD (V) | Droop (mV) | Code | Residual | RVT-LVT final delay (ps) | Valid |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in selected:
        diff_ps = float(row["rvt_lvt_diff_031_s"]) * 1.0e12
        lines.append(
            "| {} | {:.12f} | {:.3f} | {} | {} | {:.6f} | {} |".format(
                row["point_kind"], float(row["vdd_v"]), float(row["droop_mv"]), int(row["sensor_code"]),
                int(row["residual_code"]), diff_ps, int(row["code_valid"]),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_argument_parser() -> argparse.ArgumentParser:
    """Expose only explicit configuration, output, mode, and timeout controls."""

    parser = argparse.ArgumentParser(description="run the Phase-3 physical voltage/code sweep")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--mode", choices=("rvt_lvt", "rvt_rvt"), default="rvt_lvt")
    parser.add_argument("--wide-range-kind", choices=("baseline", "screen", "final"))
    parser.add_argument("--active-stage-count", type=int)
    parser.add_argument("--cal-sel", type=int)
    parser.add_argument("--baseline-code", type=int)
    parser.add_argument("--timeout-s", type=int, default=300)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Execute every planned point and publish CSV, summary, and completion gate."""

    args = build_argument_parser().parse_args(argv)
    if args.timeout_s <= 0:
        raise ValueError("timeout-s must be positive")
    config = load_json(args.config)
    selected = load_json(WORKSPACE_ROOT / "power_macro/delay_chain/phase3/discovery/selected_cells.json")
    phase1 = load_json(PHASE1_CONFIG)
    hspice = run_dc_sweep.require_regular_file(Path("/home/zhupl25/.local/bin/hspice"), "HSPICE", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if "W-2024.09" not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    wide_kind = args.wide_range_kind
    points = wide_voltage_points(config, wide_kind) if wide_kind else voltage_points(config)
    if wide_kind and (args.cal_sel is None or args.baseline_code is None):
        raise ValueError("wide-range runs require --cal-sel and --baseline-code")
    if args.active_stage_count is not None and not wide_kind:
        raise ValueError("--active-stage-count is only valid for wide-range runs")
    active_mask = None
    if args.active_stage_count is not None:
        active_mask = generate_phase3_deck.active_stage_mask(int(config["stages"]), args.active_stage_count)
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise ValueError("refusing to overwrite existing run directory: {}".format(output_dir))
    output_dir.mkdir(parents=True)
    manifest = {
        "study": "phase3_physical_voltage_sweep",
        "mode": args.mode,
        "points": points,
        "hspice_version": version,
        "selected_cal_sel": int(config["selected_cal_sel"] if args.cal_sel is None else args.cal_sel),
        "selected_lvt_cell": str(config["selected_lvt_cell"]),
        "selected_dummy_load_count": int(config["selected_dummy_load_count"] if active_mask is None else 0),
        "wide_range_kind": wide_kind,
        "active_stage_mask": active_mask,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run_config = dict(config)
    if args.cal_sel is not None:
        run_config["selected_cal_sel"] = int(args.cal_sel)
    rows = [run_point(run_config, selected, phase1, hspice, output_dir, point, args.mode, args.timeout_s, active_mask, float(config.get("wide_range", {}).get("characterization_read_time_ns", 2.5)) if wide_kind else 2.5, float(config.get("wide_range", {}).get("characterization_stop_time_ns", 4.0)) if wide_kind else 4.0, args.baseline_code) for point in points]
    write_csv(output_dir / "voltage_code.csv", rows)
    summary = validate_wide_rows(rows, points, int(args.baseline_code)) if wide_kind else validate_rows(config, rows, points, args.mode)
    summary["hspice_version"] = version
    summary["cal_sel"] = int(config["selected_cal_sel"] if args.cal_sel is None else args.cal_sel)
    summary["selected_lvt_cell"] = str(config["selected_lvt_cell"])
    if wide_kind:
        summary["wide_range_kind"] = wide_kind
        summary["active_stage_count"] = args.active_stage_count
        summary["active_stage_mask"] = active_mask
    (output_dir / "voltage_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not wide_kind:
        report_name = "VOLTAGE_SWEEP.md" if args.mode == "rvt_lvt" else "RVT_RVT_CONTROL_SWEEP.md"
        write_report(WORKSPACE_ROOT / "power_macro/delay_chain/phase3/reports" / report_name, summary, rows, args.mode)
    (output_dir / "completion.rpt").write_text(
        "status={}\nscenario_count={}\ndelta_code_last={}\ndelta_code_crit={}\n".format(
            summary["status"], len(rows), summary.get("delta_code_last", "n/a"), summary.get("delta_code_crit", "n/a")
        ),
        encoding="ascii",
    )
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
