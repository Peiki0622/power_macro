#!/usr/bin/env python3
"""Characterize the FTC programmable static-droop acceptance window.

This task intentionally reuses the completed static self-calibration evidence.
It never runs a calibration FSM or searches a new delay-code mapping.  Instead,
the runner programs the frozen ``C_lock + M`` code into the existing real-cell
sensor/threshold/DFF circuit and measures its response at a lower static rail.
Every newly generated electrical artifact remains below one task-specific run
directory; the public CSV/JSON/Markdown files are compact derived evidence.
"""

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


# The phase-1 utility owns the proven HSPICE listing and MEAS-file validation
# rules.  Adding that script directory explicitly keeps this runner executable
# as a stand-alone project script without creating a broad Python package.
FTC_ROOT = Path(__file__).resolve().parents[1]
PHASE1_SCRIPTS = FTC_ROOT.parent / "phase1" / "scripts"
if str(PHASE1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PHASE1_SCRIPTS))
import run_dc_sweep  # noqa: E402


# All electrical choices below are the frozen experiment contract, not command
# line knobs.  Altering one creates a different characterization and needs a
# separate reviewed plan instead of silently changing this evidence set.
VDD_MIN_V = 0.80
VDD_MAX_V = 1.10
BASELINES_V = (0.85, 0.90, 0.95, 1.00, 1.05, 1.10)
MARGINS = (1, 2)
FROZEN_TAPS = (10, 12, 14, 16, 18, 36, 37, 38)
FROZEN_LOCKS = {0.80: 5, 0.85: 5, 0.90: 5, 0.95: 5, 1.00: 5, 1.05: 4, 1.10: 4}
SENSOR_TAP_INDEX = 29
SENSOR_RVT_INITIAL_STAGES = 4
OBSERVABLE_STAGES = 30
Q_SETTLE_S = 2.0e-10
Q_READ_TIME_S = 3.0e-9
CODE_SETTLE_S = 2.0e-10
COARSE_STEP_V = 0.05
REFINEMENT_STEP_V = 0.01
MAX_CODE = 7
MUX_CELL = "MXT2_X0P5M_A9TL40"
ATTACK_FIELDS = (
    "baseline_vdd_v", "attack_vdd_v", "margin_code", "lock_code",
    "alarm_code", "selected_tap", "scan_phase", "scenario",
    "W_S_int_ps", "D_alarm_ps", "Q", "alarm", "valid",
)
TRIP_FIELDS = (
    "baseline_vdd_v", "lock_code", "margin_code", "alarm_code",
    "trip_status", "trip_vdd_v", "trip_depth_mv",
)


def load_json(path: Path) -> Dict[str, Any]:
    """Load one object-shaped immutable input and reject another JSON shape."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object: {}".format(path))
    return value


def load_csv(path: Path, fields: Sequence[str]) -> List[Dict[str, str]]:
    """Load nonempty CSV evidence only after checking its consumed columns."""

    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not set(fields).issubset(reader.fieldnames):
            raise ValueError("required evidence schema is incomplete: {}".format(path))
        rows = list(reader)
    if not rows:
        raise ValueError("required evidence is empty: {}".format(path))
    return rows


def finite_number(value: Any) -> Optional[float]:
    """Return a finite HSPICE value, preserving absent/failed measures as None."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def voltage_key(value: float) -> float:
    """Normalize only fixed 10 mV/50 mV grid values for dictionary lookup."""

    return round(float(value), 2)


def sha256_file(path: Path) -> str:
    """Return a streaming digest for one immutable input/collateral file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def frozen_inputs() -> Dict[str, Any]:
    """Read and strictly validate the six plan-approved frozen inputs.

    The calibration trace is used only to prove normal headroom for each
    programmed alarm code.  No row is replayed as a new attack simulation.
    """

    mapping = load_json(FTC_ROOT / "analysis/static_self_calibration/range_mapping.json")
    trace = load_csv(
        FTC_ROOT / "analysis/static_self_calibration/calibration_trace.csv",
        ("vdd_v", "code", "selected_tap", "Q", "D_code_ps", "W_S_int_ps", "is_lock", "headroom_verified"),
    )
    calibration_summary = load_json(FTC_ROOT / "analysis/static_self_calibration/summary.json")
    architecture = load_json(FTC_ROOT / "analysis/minimal_pulse_comparator/architecture.json")
    cells = load_json(FTC_ROOT / "discovery/selected_cells.json")
    report_path = FTC_ROOT / "reports/FTC_STATIC_SELF_CALIBRATION_FULL_RANGE_HEADROOM.md"
    report = report_path.read_text(encoding="utf-8")

    expected_mapping = {str(code): tap for code, tap in enumerate(FROZEN_TAPS)}
    if mapping.get("code_to_tap") != expected_mapping or mapping.get("tap_list") != list(FROZEN_TAPS):
        raise ValueError("frozen mapping does not equal the approved 3-bit tap list")
    if mapping.get("validated_vdd_range_v") != [VDD_MIN_V, VDD_MAX_V]:
        raise ValueError("frozen mapping does not cover exactly 0.80--1.10 V")
    if calibration_summary.get("decision") != "Static Self Calibration + Full-Range Code Headroom = GO":
        raise ValueError("frozen static calibration GO evidence is unavailable")
    if "**Static Self Calibration + Full-Range Code Headroom = GO**" not in report:
        raise ValueError("frozen static calibration report is not a GO report")

    threshold = architecture.get("threshold", {})
    sensor = architecture.get("sensor", {})
    if threshold.get("buffer_cell") != "BUF_X0P7M_A9TL40" or threshold.get("mux_cell") != MUX_CELL:
        raise ValueError("frozen threshold cells do not match the approved physical circuit")
    if threshold.get("mux_count") != 7 or sensor.get("tap_index") != SENSOR_TAP_INDEX:
        raise ValueError("frozen physical topology is not the approved 7-MUX/tap29 circuit")
    if sensor.get("initial_rvt_stages") != SENSOR_RVT_INITIAL_STAGES or sensor.get("initial_lvt_stages") != 0:
        raise ValueError("frozen sensor initial delay composition is not 4-RVT/0-LVT")
    if architecture.get("dff", {}).get("cell") != "DFFRPQ_X0P5M_A9TR40":
        raise ValueError("frozen comparator DFF does not match this task")
    if cells.get("delay_lvt", {}).get("cell") != "BUF_X0P7M_A9TL40":
        raise ValueError("selected LVT threshold buffer does not match this task")
    if cells.get("xor2", {}).get("cell") != "XOR2_X0P5M_A9TR40":
        raise ValueError("selected sensor XOR does not match this task")

    observed_locks: Dict[float, int] = {}
    trace_by_point: Dict[Tuple[float, int], Dict[str, str]] = {}
    for row in trace:
        vdd_v = voltage_key(float(row["vdd_v"]))
        code = int(row["code"])
        if vdd_v not in FROZEN_LOCKS or code < 0 or code > MAX_CODE:
            raise ValueError("calibration trace contains an out-of-contract row")
        trace_by_point[(vdd_v, code)] = row
        if int(row["is_lock"]) == 1:
            if vdd_v in observed_locks:
                raise ValueError("calibration trace contains two locks at {} V".format(vdd_v))
            observed_locks[vdd_v] = code
    if observed_locks != FROZEN_LOCKS:
        raise ValueError("calibration trace lock codes differ from the frozen seven-point result")

    # Every future baseline alarm code must already have a normal Q=0 physical
    # observation at its own V0.  This is a no-false-alarm prerequisite, not a
    # substitute for the new lower-rail static-droop probes.
    for vdd_v in BASELINES_V:
        lock_code = FROZEN_LOCKS[vdd_v]
        for margin_code in MARGINS:
            alarm_code = lock_code + margin_code
            normal = trace_by_point.get((vdd_v, alarm_code))
            if normal is None or int(normal["Q"]) != 0:
                raise ValueError("normal Q=0 headroom is absent at {:.2f} V code {}".format(vdd_v, alarm_code))
    return {
        "mapping": mapping,
        "trace": trace,
        "calibration_summary": calibration_summary,
        "architecture": architecture,
        "cells": cells,
        "report_path": report_path,
    }


def spice(value: float) -> str:
    """Format one finite scalar as an explicit HSPICE decimal literal."""

    return "{:.12e}".format(float(value))


def buffer_instance(name: str, output_node: str, input_node: str, cell: str) -> str:
    """Render BUF positional ports: Y, VDD, VNW, VPW, VSS, A on local rails."""

    return "{} {} vdd_a vdd_a vss_a vss_a {} {}".format(name, output_node, input_node, cell)


def mux_instance(name: str, output_node: str, input_a: str, input_b: str, select_node: str) -> str:
    """Render the verified LVT 2:1 MUX with its static binary select rail."""

    return "{} {} vdd_a vdd_a vss_a vss_a {} {} {} {}".format(
        name, output_node, input_a, input_b, select_node, MUX_CELL
    )


def mux_tree_lines(taps: Sequence[int]) -> List[str]:
    """Render the fixed balanced seven-MUX 8:1 tree for an increasing tap map."""

    if tuple(taps) != FROZEN_TAPS:
        raise ValueError("acceptance window must use exactly the frozen tap mapping")
    lines = ["* Balanced 8:1 MUX tree: code[0] leaf, code[1] middle, code[2] root."]
    for group in range(4):
        lines.append(mux_instance(
            "XMUX_L1_{}".format(group), "mux_l1_{}".format(group),
            "thr_tap_{}".format(taps[2 * group]), "thr_tap_{}".format(taps[2 * group + 1]), "code0",
        ))
    for group in range(2):
        lines.append(mux_instance(
            "XMUX_L2_{}".format(group), "mux_l2_{}".format(group),
            "mux_l1_{}".format(2 * group), "mux_l1_{}".format(2 * group + 1), "code1",
        ))
    lines.append(mux_instance("XMUX_L3", "dff_ck", "mux_l2_0", "mux_l2_1", "code2"))
    return lines


def render_deck(config: Mapping[str, Any], cells: Mapping[str, Any], attack_vdd_v: float, alarm_code: int) -> str:
    """Render one complete same-rail static-droop probe using the frozen circuit.

    The physical rail has the attack voltage from time zero through readout.
    The three MUX select rails are static before reset release, so this probe
    measures one settled alarm code rather than a code-switching transient.
    """

    if not (VDD_MIN_V <= attack_vdd_v <= VDD_MAX_V):
        raise ValueError("attack VDD is outside the formal 0.80--1.10 V range")
    if alarm_code < 0 or alarm_code > MAX_CODE:
        raise ValueError("alarm code is outside the fixed 3-bit range")
    includes = ['.include "{}"'.format(cells["source_files"]["rvt_cdl"])]
    if Path(cells["source_files"]["lvt_cdl"]).resolve() != Path(cells["source_files"]["rvt_cdl"]).resolve():
        includes.append('.include "{}"'.format(cells["source_files"]["lvt_cdl"]))
    launch_s = float(config["launch_time_s"])
    stop_s = launch_s + float(config["sampling_period_s"]) - float(config["tran_max_step_s"])
    bits = tuple((alarm_code >> bit) & 1 for bit in range(3))
    lines = [
        "* FTC programmable acceptance-window physical static-droop probe.",
        "* TT/25C; frozen 4-RVT/0-LVT tap29 sensor; 38 LVT threshold BUFs; 7 MUXes; one real DFF.",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(float(config["temperature_c"]))),
        *includes,
        '.lib "{}" {}'.format(config["model_library"], config["corner"]),
        ".param VDD_VALUE={}".format(spice(attack_vdd_v)),
        "V_VDD vdd_a vss_a 'VDD_VALUE'",
        "V_VSS vss_a 0 0",
        "V_SCLK s_clk vss_a PULSE(0 'VDD_VALUE' {} 1.000000000000e-12 1.000000000000e-12 {} {})".format(
            spice(launch_s), spice(float(config["sampling_period_s"]) / 2.0), spice(float(config["sampling_period_s"]))
        ),
        "* These code sources remain fixed through settle, launch, capture and DFF readout.",
        "V_CODE0 code0 vss_a {}".format("'VDD_VALUE'" if bits[0] else "0"),
        "V_CODE1 code1 vss_a {}".format("'VDD_VALUE'" if bits[1] else "0"),
        "V_CODE2 code2 vss_a {}".format("'VDD_VALUE'" if bits[2] else "0"),
        "* The active-high DFF clear covers all code settling, then releases before the isolated sensor launch.",
        "V_DFF_RESET dff_reset vss_a PWL(0 'VDD_VALUE' {} 'VDD_VALUE' {} 0 {} 0)".format(
            spice(launch_s - CODE_SETTLE_S), spice(launch_s - CODE_SETTLE_S + 1.0e-11), spice(stop_s)
        ),
        "",
        "* Frozen four-stage RVT initial sensor delay path.",
    ]
    rvt_input = "s_clk"
    for stage in range(SENSOR_RVT_INITIAL_STAGES):
        output = "rvt_initial_{}".format(stage)
        lines.append(buffer_instance("XRVT_INIT_{:02d}".format(stage), output, rvt_input, cells["delay_rvt"]["cell"]))
        rvt_input = output
    lines.append("* Thirty RVT/LVT observable stages and all thirty real XOR loads preserve the frozen sensor topology.")
    rvt_taps: List[str] = []
    lvt_taps: List[str] = []
    lvt_input = "s_clk"
    for stage in range(OBSERVABLE_STAGES):
        rvt_output = "rvt_{}".format(stage)
        lvt_output = "lvt_{}".format(stage)
        lines.append(buffer_instance("XRVT_{:02d}".format(stage), rvt_output, rvt_input, cells["delay_rvt"]["cell"]))
        lines.append(buffer_instance("XLVT_{:02d}".format(stage), lvt_output, lvt_input, cells["delay_lvt"]["cell"]))
        rvt_taps.append(rvt_output)
        lvt_taps.append(lvt_output)
        rvt_input = rvt_output
        lvt_input = lvt_output
    for stage, (rvt_tap, lvt_tap) in enumerate(zip(rvt_taps, lvt_taps)):
        lines.append("XXOR_{:02d} xor_{} vdd_a vdd_a vss_a vss_a {} {} {}".format(
            stage, stage, rvt_tap, lvt_tap, cells["xor2"]["cell"]
        ))
    lines.append("* The threshold chain reaches tap38, the physical endpoint of the frozen mapping.")
    threshold_input = "xor_29"
    for tap in range(1, max(FROZEN_TAPS) + 1):
        output = "thr_tap_{}".format(tap)
        lines.append(buffer_instance("XTHR_BUF_{:02d}".format(tap), output, threshold_input, cells["delay_lvt"]["cell"]))
        threshold_input = output
    lines.extend(["", *mux_tree_lines(FROZEN_TAPS), "", "* DFF positional ports: Q VDD VNW VPW VSS CK D R."])
    lines.append("XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(cells["dff"]["cell"]))
    lines.extend([
        "",
        ".tran {} {}".format(spice(float(config["tran_max_step_s"])), spice(stop_s)),
        ".measure tran t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1",
        ".measure tran t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1",
        ".measure tran t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1",
        ".measure tran q_final_v FIND v(q_final,vss_a) AT={}".format(spice(Q_READ_TIME_S)),
        ".measure tran vdd_a_min_v MIN v(vdd_a,vss_a) FROM=0 TO={}".format(spice(stop_s)),
        ".end",
        "",
    ])
    return "\n".join(lines)


def classify_probe(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert complete raw measures to Q, pulse width and alarm-delay evidence."""

    values = {name: finite_number(record.get(name)) for name in ("t_xor_rise_s", "t_xor_fall_s", "t_ck_rise_s", "q_final_v")}
    result: Dict[str, Any] = {"valid": False, "Q": None, "W_S_int_ps": None, "D_alarm_ps": None}
    if any(value is None for value in values.values()):
        return result
    width_s = values["t_xor_fall_s"] - values["t_xor_rise_s"]
    delay_s = values["t_ck_rise_s"] - values["t_xor_rise_s"]
    if width_s is None or delay_s is None or width_s <= 0.0 or delay_s <= 0.0:
        return result
    # A DFF output sampled before the clock-to-Q settling interval is invalid
    # evidence even if HSPICE returned a numeric voltage.
    if values["t_ck_rise_s"] > Q_READ_TIME_S - Q_SETTLE_S:
        return result
    result.update({
        "valid": True,
        "Q": 1 if values["q_final_v"] >= float(record["attack_vdd_v"]) / 2.0 else 0,
        "W_S_int_ps": width_s * 1.0e12,
        "D_alarm_ps": delay_s * 1.0e12,
    })
    return result


def coarse_points(baseline_vdd_v: float) -> List[float]:
    """Return the prescribed descending 50 mV attack grid, never below 0.80 V."""

    start_v = voltage_key(baseline_vdd_v - COARSE_STEP_V)
    points: List[float] = []
    current_v = start_v
    while current_v >= VDD_MIN_V - 1.0e-12:
        points.append(voltage_key(current_v))
        current_v = voltage_key(current_v - COARSE_STEP_V)
    if not points or points[0] != start_v or points[-1] < VDD_MIN_V - 1.0e-12:
        raise ValueError("invalid coarse schedule")
    return points


def refinement_points(last_zero_v: float, first_one_v: float) -> List[float]:
    """Return all 10 mV interior candidates from a valid 50 mV Q=0/Q=1 bracket."""

    if not (last_zero_v > first_one_v >= VDD_MIN_V):
        raise ValueError("refinement bracket is outside the legal descending range")
    points: List[float] = []
    candidate_v = voltage_key(last_zero_v - REFINEMENT_STEP_V)
    while candidate_v > first_one_v + 1.0e-12:
        points.append(candidate_v)
        candidate_v = voltage_key(candidate_v - REFINEMENT_STEP_V)
    return points


def scenario_label(baseline_vdd_v: float, margin_code: int, attack_vdd_v: float, phase: str) -> str:
    """Produce a deterministic unique raw-directory name without floating-point dots."""

    return "v0_{:03d}mv_m{}_attack_{:03d}mv_{}".format(
        int(round(baseline_vdd_v * 1000.0)), margin_code, int(round(attack_vdd_v * 1000.0)), phase
    )


def execute_probe(hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any],
                  baseline_vdd_v: float, margin_code: int, attack_vdd_v: float, phase: str) -> Dict[str, Any]:
    """Execute, validate and retain one isolated static-droop physical scenario."""

    lock_code = FROZEN_LOCKS[baseline_vdd_v]
    alarm_code = lock_code + margin_code
    label = scenario_label(baseline_vdd_v, margin_code, attack_vdd_v, phase)
    scenario_dir = run_dir / "scenarios" / label
    scenario_dir.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(FTC_ROOT / "spice/empty_subckt.sp_cal", scenario_dir / "empty_subckt.sp_cal")
    deck_path = scenario_dir / "programmable_acceptance_window.sp"
    deck_path.write_text(render_deck(config, cells, attack_vdd_v, alarm_code), encoding="ascii")
    command = [str(hspice), deck_path.name, "-o", "programmable_acceptance_window"]
    result = subprocess.run(command, cwd=str(scenario_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True, check=False, timeout=300)
    (scenario_dir / "hspice_command.log").write_text(
        "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(" ".join(command), result.returncode, result.stdout, result.stderr),
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, scenario_dir))
    run_dc_sweep.validate_listing(scenario_dir / "programmable_acceptance_window.lis")
    values = run_dc_sweep.parse_measurements(run_dc_sweep.find_measurement_file(scenario_dir, "programmable_acceptance_window"))
    record: Dict[str, Any] = {
        "baseline_vdd_v": baseline_vdd_v,
        "attack_vdd_v": attack_vdd_v,
        "margin_code": margin_code,
        "lock_code": lock_code,
        "alarm_code": alarm_code,
        "selected_tap": FROZEN_TAPS[alarm_code],
        "scan_phase": phase,
        "scenario": str(scenario_dir.relative_to(run_dir)),
        "t_xor_rise_s": values.get("t_xor_rise"),
        "t_xor_fall_s": values.get("t_xor_fall"),
        "t_ck_rise_s": values.get("t_ck_rise"),
        "q_final_v": values.get("q_final_v"),
    }
    record.update(classify_probe(record))
    record["alarm"] = record["Q"] if record["valid"] else None
    return record


def run_group(hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any],
              baseline_vdd_v: float, margin_code: int) -> List[Dict[str, Any]]:
    """Run one adaptive group: coarse until Q=1, then only needed 10 mV probes."""

    rows: List[Dict[str, Any]] = []
    last_zero_v: Optional[float] = None
    first_one_v: Optional[float] = None
    for attack_vdd_v in coarse_points(baseline_vdd_v):
        row = execute_probe(hspice, run_dir, config, cells, baseline_vdd_v, margin_code, attack_vdd_v, "coarse")
        rows.append(row)
        if not row["valid"]:
            return rows
        if int(row["Q"]) == 1:
            first_one_v = attack_vdd_v
            break
        last_zero_v = attack_vdd_v
    if last_zero_v is None or first_one_v is None:
        return rows
    # Once a refinement point is high, lower points cannot improve the highest
    # trip voltage.  Ending there preserves the plan's minimal adaptive sweep.
    for attack_vdd_v in refinement_points(last_zero_v, first_one_v):
        row = execute_probe(hspice, run_dir, config, cells, baseline_vdd_v, margin_code, attack_vdd_v, "refinement")
        rows.append(row)
        if not row["valid"] or int(row["Q"]) == 1:
            break
    return rows


def analyze_rows(rows: Sequence[Mapping[str, Any]], normal_q0: Mapping[Tuple[float, int], bool]) -> Dict[str, Any]:
    """Classify trip boundaries, mechanism ordering and mapping resolution.

    Rows are grouped by baseline and margin.  No statistical interpolation is
    used: a trip is the highest *measured* Q=1 attack rail, as required by the
    10 mV refinement definition.
    """

    grouped: Dict[Tuple[float, int], List[Mapping[str, Any]]] = {}
    for row in rows:
        key = (voltage_key(float(row["baseline_vdd_v"])), int(row["margin_code"]))
        grouped.setdefault(key, []).append(row)
    trip_rows: List[Dict[str, Any]] = []
    q_reversions: List[str] = []
    invalid_groups: List[str] = []
    for baseline_vdd_v in BASELINES_V:
        lock_code = FROZEN_LOCKS[baseline_vdd_v]
        for margin_code in MARGINS:
            alarm_code = lock_code + margin_code
            group = sorted(grouped.get((baseline_vdd_v, margin_code), []), key=lambda row: float(row["attack_vdd_v"]), reverse=True)
            status = "NO_IN_RANGE_TRIP"
            trip_vdd_v: Optional[float] = None
            trip_depth_mv: Optional[float] = None
            if not group or any(not bool(row.get("valid")) for row in group):
                status = "INVALID"
                invalid_groups.append("{:.2f}V/M{}".format(baseline_vdd_v, margin_code))
            else:
                q_values = [int(row["Q"]) for row in group]
                if any(right < left for left, right in zip(q_values, q_values[1:])):
                    q_reversions.append("{:.2f}V/M{}".format(baseline_vdd_v, margin_code))
                high_rows = [row for row in group if int(row["Q"]) == 1]
                if high_rows:
                    trip_vdd_v = max(float(row["attack_vdd_v"]) for row in high_rows)
                    trip_depth_mv = (baseline_vdd_v - trip_vdd_v) * 1000.0
                    status = "TRIP"
            trip_rows.append({
                "baseline_vdd_v": baseline_vdd_v,
                "lock_code": lock_code,
                "margin_code": margin_code,
                "alarm_code": alarm_code,
                "trip_status": status,
                "trip_vdd_v": trip_vdd_v,
                "trip_depth_mv": trip_depth_mv,
            })

    by_trip = {(float(row["baseline_vdd_v"]), int(row["margin_code"])): row for row in trip_rows}
    normal_failures = []
    m1_failures = []
    ordering_failures = []
    for baseline_vdd_v in BASELINES_V:
        lock_code = FROZEN_LOCKS[baseline_vdd_v]
        if not all(normal_q0.get((baseline_vdd_v, lock_code + margin_code), False) for margin_code in MARGINS):
            normal_failures.append("{:.2f}V".format(baseline_vdd_v))
        m1 = by_trip[(baseline_vdd_v, 1)]
        m2 = by_trip[(baseline_vdd_v, 2)]
        if m1["trip_status"] != "TRIP":
            m1_failures.append("{:.2f}V".format(baseline_vdd_v))
        if m1["trip_status"] == "TRIP" and m2["trip_status"] == "TRIP" and float(m2["trip_depth_mv"]) + 1.0e-9 < float(m1["trip_depth_mv"]):
            ordering_failures.append("{:.2f}V".format(baseline_vdd_v))
    mechanism_reasons = []
    if normal_failures:
        mechanism_reasons.append("normal Q=0 headroom missing at {}".format(", ".join(normal_failures)))
    if m1_failures:
        mechanism_reasons.append("M=1 has no in-range trip at {}".format(", ".join(m1_failures)))
    if ordering_failures:
        mechanism_reasons.append("M=2 trips shallower than M=1 at {}".format(", ".join(ordering_failures)))
    if q_reversions:
        mechanism_reasons.append("Q reversion at {}".format(", ".join(q_reversions)))
    if invalid_groups:
        mechanism_reasons.append("invalid electrical measurements at {}".format(", ".join(invalid_groups)))
    mechanism_go = not mechanism_reasons

    sensitivity_failures = []
    distinct_boundaries = []
    if mechanism_go:
        for baseline_vdd_v in BASELINES_V:
            depth_mv = float(by_trip[(baseline_vdd_v, 1)]["trip_depth_mv"])
            limit_mv = 50.0 if math.isclose(baseline_vdd_v, 0.85, abs_tol=1.0e-12) else 100.0
            if depth_mv > limit_mv + 1.0e-9:
                sensitivity_failures.append("{:.2f}V/M1 {:.1f}mV > {:.1f}mV".format(baseline_vdd_v, depth_mv, limit_mv))
            m2 = by_trip[(baseline_vdd_v, 2)]
            if m2["trip_status"] == "TRIP" and float(m2["trip_depth_mv"]) >= depth_mv + 10.0 - 1.0e-9:
                distinct_boundaries.append(baseline_vdd_v)
    resolution_go = mechanism_go and not sensitivity_failures and bool(distinct_boundaries)
    if mechanism_go and not distinct_boundaries:
        sensitivity_failures.append("M=1 and M=2 have no distinct 10mV-grid trip boundary")

    if not mechanism_go:
        decision = "Programmable Acceptance Window = NO-GO"
        mapping_decision = "NOT_READY"
        next_step = "stop; do not add monitor RTL"
    elif resolution_go:
        decision = "Programmable Acceptance Window = GO"
        mapping_decision = "READY_FOR_PVT_DETECTOR_VERIFICATION"
        next_step = "enter PVT detector verification"
    else:
        decision = "Programmable Acceptance Window = GO"
        mapping_decision = "REFINEMENT_REQUIRED"
        next_step = "create a narrow delay-code refinement plan"
    return {
        "trip_rows": trip_rows,
        "mechanism_go": mechanism_go,
        "mechanism_reasons": mechanism_reasons,
        "mapping_decision": mapping_decision,
        "resolution_reasons": sensitivity_failures,
        "distinct_boundary_baselines_v": distinct_boundaries,
        "decision": decision,
        "next_step": next_step,
    }


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    """Write a deterministic public evidence table without raw simulator clutter."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write stable, readable derived evidence."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_report(path: Path, analysis: Mapping[str, Any]) -> None:
    """Write exactly the four plan-required answers from measured trip evidence."""

    trip_rows = analysis["trip_rows"]
    # The JSON field remains a compact machine-readable action token, while
    # the human-facing Chinese report states the corresponding planned action.
    next_step_text = {
        "stop; do not add monitor RTL": "本阶段停止，不增加 monitor RTL。",
        "enter PVT detector verification": "进入 PVT detector verification。",
        "create a narrow delay-code refinement plan": "先制定一次窄的 delay-code refinement 计划。",
    }[analysis["next_step"]]
    lines = [
        "# FTC Programmable Acceptance Window", "", "## Decision", "",
        "**{}**".format(analysis["decision"]), "",
        "- Current 3-bit Mapping: **{}**".format(analysis["mapping_decision"]), "",
        "## Required Answers", "",
        "1. `C_lock + M` 的真实 DFF acceptance-window 机制是否成立？{}。".format("是" if analysis["mechanism_go"] else "否"),
        "2. `M=1` 和 `M=2` 分别对应多大的静态 droop trip depth？见下表。",
        "3. 当前 `[10,12,14,16,18,36,37,38]` mapping 的安全分辨率是否足够？{}。".format(
            "是" if analysis["mapping_decision"] == "READY_FOR_PVT_DETECTOR_VERIFICATION" else "否"
        ),
        "4. 下一阶段是进入 PVT detector verification，还是先做一次窄的 delay-code refinement？{}".format(next_step_text),
        "", "## Trip Map", "", "| V0 (V) | C_lock | M | C_alarm | Status | V_trip (V) | Trip depth (mV) |",
        "|---:|---:|---:|---:|---|---:|---:|",
    ]
    for row in trip_rows:
        trip_vdd = "" if row["trip_vdd_v"] is None else "{:.2f}".format(float(row["trip_vdd_v"]))
        depth = "" if row["trip_depth_mv"] is None else "{:.1f}".format(float(row["trip_depth_mv"]))
        lines.append("| {:.2f} | {} | {} | {} | {} | {} | {} |".format(
            float(row["baseline_vdd_v"]), row["lock_code"], row["margin_code"], row["alarm_code"],
            row["trip_status"], trip_vdd, depth
        ))
    lines.extend(["", "## Gate Evidence", ""])
    reasons = list(analysis["mechanism_reasons"]) + list(analysis["resolution_reasons"])
    if reasons:
        lines.extend(["- {}".format(reason) for reason in reasons])
    else:
        lines.append("- normal Q=0 headroom, M=1 in-range trip, margin ordering, monotonic Q and required resolution all passed")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare_run(run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any], inputs: Mapping[str, Any]) -> Path:
    """Preflight tool/collateral and create the single raw-run root exactly once."""

    if run_dir.exists():
        raise ValueError("refusing to overwrite existing task run directory: {}".format(run_dir))
    hspice = run_dc_sweep.require_regular_file(Path(config["hspice"]), "HSPICE", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if str(config["expected_hspice_version"]) not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    collateral = list(cells["source_files"].values()) + [config["model_library"], FTC_ROOT / "spice/empty_subckt.sp_cal"]
    checked = [run_dc_sweep.require_regular_file(Path(item), "FTC source collateral") for item in collateral]
    # Coarse has 1+2+3+4+5+6 points per margin.  Each 50mV bracket may need
    # four interior 10mV probes, so the honest upper bound is 42+48=90;
    # adaptive stopping normally produces fewer scenarios.
    manifest = {
        "study": "ftc_programmable_acceptance_window",
        "scope": "TT/25C static droop only; no calibration replay or sub-0.80V attack",
        "hspice": str(hspice),
        "hspice_version": version,
        "baseline_vdd_v": list(BASELINES_V),
        "margins": list(MARGINS),
        "frozen_locks": {"{:.2f}".format(key): value for key, value in FROZEN_LOCKS.items()},
        "frozen_taps": list(FROZEN_TAPS),
        "maximum_possible_scenarios": 90,
        "source_sha256": {str(path): sha256_file(path) for path in checked},
        "frozen_input_sha256": {
            "range_mapping": sha256_file(FTC_ROOT / "analysis/static_self_calibration/range_mapping.json"),
            "calibration_trace": sha256_file(FTC_ROOT / "analysis/static_self_calibration/calibration_trace.csv"),
            "calibration_summary": sha256_file(FTC_ROOT / "analysis/static_self_calibration/summary.json"),
            "architecture": sha256_file(FTC_ROOT / "analysis/minimal_pulse_comparator/architecture.json"),
            "selected_cells": sha256_file(FTC_ROOT / "discovery/selected_cells.json"),
            "calibration_report": sha256_file(Path(inputs["report_path"])),
        },
    }
    run_dir.mkdir(parents=True)
    write_json(run_dir / "manifest.json", manifest)
    return hspice


def normal_q0_from_trace(trace: Sequence[Mapping[str, str]]) -> Dict[Tuple[float, int], bool]:
    """Extract only the frozen baseline Q=0 facts relevant to alarm programming."""

    result: Dict[Tuple[float, int], bool] = {}
    for row in trace:
        key = (voltage_key(float(row["vdd_v"])), int(row["code"]))
        result[key] = int(row["Q"]) == 0
    return result


def record_actual_scenario_count(run_dir: Path, scenario_count: int) -> None:
    """Finalize the preflight manifest with the actual adaptive-run evidence count.

    This update is deliberately limited to the task-owned manifest after every
    HSPICE scenario has passed listing/MEAS validation.  It makes the adaptive
    stopping decision auditable without changing frozen inputs or raw results.
    """

    manifest_path = run_dir / "manifest.json"
    manifest = load_json(manifest_path)
    manifest["actual_scenario_count"] = scenario_count
    write_json(manifest_path, manifest)


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Expose output locations without exposing electrical experiment parameters."""

    parser = argparse.ArgumentParser(description="run FTC programmable acceptance-window static-droop characterization")
    parser.add_argument("--run-dir", type=Path, default=FTC_ROOT / "runs/programmable_acceptance_window/r1")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis/programmable_acceptance_window")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports/FTC_PROGRAMMABLE_ACCEPTANCE_WINDOW.md")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Execute the complete task and publish only validated derived artifacts."""

    args = parse_args(argv)
    config = load_json(FTC_ROOT / "ftc_config.json")
    inputs = frozen_inputs()
    run_dir = args.run_dir.resolve()
    hspice = prepare_run(run_dir, config, inputs["cells"], inputs)
    rows: List[Dict[str, Any]] = []
    for baseline_vdd_v in BASELINES_V:
        for margin_code in MARGINS:
            rows.extend(run_group(hspice, run_dir, config, inputs["cells"], baseline_vdd_v, margin_code))
    record_actual_scenario_count(run_dir, len(rows))
    analysis = analyze_rows(rows, normal_q0_from_trace(inputs["trace"]))
    write_csv(args.analysis_dir.resolve() / "attack_sweep.csv", ATTACK_FIELDS, rows)
    write_csv(args.analysis_dir.resolve() / "trip_map.csv", TRIP_FIELDS, analysis["trip_rows"])
    summary = {
        "schema_version": 1,
        "study": "ftc_programmable_acceptance_window",
        "raw_run": str(run_dir),
        "scenario_count": len(rows),
        "formal_vdd_range_v": [VDD_MIN_V, VDD_MAX_V],
        "frozen_taps": list(FROZEN_TAPS),
        "frozen_locks": {"{:.2f}".format(key): value for key, value in FROZEN_LOCKS.items()},
        **{key: value for key, value in analysis.items() if key != "trip_rows"},
    }
    write_json(args.analysis_dir.resolve() / "summary.json", summary)
    render_report(args.report_output.resolve(), analysis)
    print("FTC_PROGRAMMABLE_ACCEPTANCE_WINDOW decision={} mapping={}".format(analysis["decision"], analysis["mapping_decision"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
