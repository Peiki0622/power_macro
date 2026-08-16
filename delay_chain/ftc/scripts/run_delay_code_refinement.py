#!/usr/bin/env python3
"""Refine the FTC threshold-code placement around the real pulse boundary.

This runner is deliberately a new evidence producer.  The two historical FTC
runners remain replayable and are never imported for their experiment loops.
The runner has three electrical phases:

* three TT/25 C sizing probes measure physical tap arrivals only;
* a small set of real-MUX/real-DFF probes checks the predicted boundary;
* three representative static-droop baselines check acceptance feasibility.

Every HSPICE scenario is kept below one task-scoped raw-run directory.  The
public CSV/JSON/Markdown files contain derived evidence and provenance, while
the historical mapping is treated as read-only input.  This is intentionally
not an optimizer: at most one primary and one fallback mapping are attempted.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
PHASE1_SCRIPTS = FTC_ROOT.parent / "phase1" / "scripts"
if str(PHASE1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PHASE1_SCRIPTS))
import run_dc_sweep  # noqa: E402  # Reuse the reviewed HSPICE checks only.


# Electrical constants are fixed by the refinement plan.  They are kept here,
# instead of exposed as command-line tuning knobs, so a new run cannot silently
# become a different experiment.
VDD_POINTS = (0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10)
SCREEN_VDD_POINTS = (1.10, 0.95, 0.80)
FEASIBILITY_BASELINES = (0.85, 0.95, 1.10)
CODES = tuple(range(8))
MAX_CODE = 7
VDD_MIN_V = 0.80
VDD_MAX_V = 1.10
SCREEN_TAPS = tuple(range(14, 39))
MAX_TAP = 38
SIZING_TREE_TAPS = (10, 12, 14, 16, 18, 20, 22, 24)
SENSOR_TAP_INDEX = 29
SENSOR_RVT_INITIAL_STAGES = 4
SENSOR_LVT_INITIAL_STAGES = 0
OBSERVABLE_STAGES = 30
MUX_COUNT = 7
MUX_CELL = "MXT2_X0P5M_A9TL40"
THRESHOLD_BUFFER_CELL = "BUF_X0P7M_A9TL40"
SENSOR_XOR_CELL = "XOR2_X0P5M_A9TR40"
DFF_CELL = "DFFRPQ_X0P5M_A9TR40"
Q_SETTLE_S = 2.0e-10
SCREEN_Q_READ_TIME_S = 3.5e-9
COARSE_STEP_V = 0.05
REFINEMENT_STEP_V = 0.01
MAX_CANDIDATES = 2

TAP_SCREEN_FIELDS = (
    "vdd_v", "tap", "t_xor_rise_s", "t_xor_fall_s", "W_S_int_ps",
    "t_tap_rise_s", "D_raw_ps", "D_mux_est_ps", "D_est_ps", "valid",
)
CALIBRATION_FIELDS = (
    "candidate_id", "vdd_v", "predicted_k", "code", "selected_tap",
    "t_xor_rise_s", "t_xor_fall_s", "W_S_int_ps", "t_ck_rise_s",
    "D_code_ps", "q_final_v", "Q", "readout_time_s", "scenario", "valid",
)
FEASIBILITY_FIELDS = (
    "candidate_id", "baseline_vdd_v", "attack_vdd_v", "margin_code",
    "lock_code", "alarm_code", "selected_tap", "scan_phase", "scenario",
    "W_S_int_ps", "D_alarm_ps", "Q", "alarm", "valid",
)


def finite_number(value: Any) -> Optional[float]:
    """Return a finite scalar, preserving failed HSPICE values as ``None``."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def voltage_key(value: float) -> float:
    """Normalize the fixed 10 mV/50 mV voltage grids without broad rounding."""

    return round(float(value), 2)


def spice(value: float) -> str:
    """Render a finite scalar as an explicit HSPICE decimal literal."""

    return "{:.12e}".format(float(value))


def load_json(path: Path) -> Dict[str, Any]:
    """Load one object-shaped JSON evidence file and reject other shapes."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def load_csv(path: Path, fields: Sequence[str]) -> List[Dict[str, str]]:
    """Load a nonempty CSV after checking the narrow consumed schema."""

    if not path.is_file():
        raise ValueError("required CSV is unavailable: {}".format(path))
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not set(fields).issubset(reader.fieldnames):
            raise ValueError("required CSV schema is incomplete: {}".format(path))
        rows = list(reader)
    if not rows:
        raise ValueError("required CSV is empty: {}".format(path))
    return rows


def sha256_file(path: Path) -> str:
    """Hash one immutable input for the task manifest."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_regular_file(path: Path, description: str, executable: bool = False) -> Path:
    """Validate an executable or collateral path before creating raw output."""

    resolved = path.resolve()
    if not resolved.is_file() or resolved.stat().st_size == 0:
        raise ValueError("{} is missing or empty: {}".format(description, resolved))
    if executable and not os.access(str(resolved), os.X_OK):
        raise ValueError("{} is not executable: {}".format(description, resolved))
    return resolved


def frozen_inputs() -> Dict[str, Any]:
    """Read and validate exactly the evidence frozen by the refinement plan.

    The root-cause report, old attack evidence, and old calibration evidence are
    inputs only.  The function deliberately checks their terminal conclusions
    and schemas instead of invoking either historical HSPICE runner.
    """

    report_path = FTC_ROOT / "reports/FTC_PROGRAMMABLE_ACCEPTANCE_WINDOW_ROOT_CAUSE.md"
    report = report_path.read_text(encoding="utf-8")
    if "Programmable Acceptance Window = NO-GO" not in report:
        raise ValueError("frozen root-cause report is not the required NO-GO evidence")
    attack_path = FTC_ROOT / "analysis/programmable_acceptance_window/attack_sweep.csv"
    attack = load_csv(attack_path, ("baseline_vdd_v", "attack_vdd_v", "Q", "valid"))
    if len(attack) != 42 or any(int(row["Q"]) != 0 or row["valid"].lower() != "true" for row in attack):
        raise ValueError("frozen attack sweep is not the completed 42-row NO-GO evidence")
    trip_path = FTC_ROOT / "analysis/programmable_acceptance_window/trip_map.csv"
    trip = load_csv(trip_path, ("trip_status",))
    if len(trip) != 12 or any(row["trip_status"] != "NO_IN_RANGE_TRIP" for row in trip):
        raise ValueError("frozen trip map is not the completed NO-GO evidence")
    acceptance_summary_path = FTC_ROOT / "analysis/programmable_acceptance_window/summary.json"
    acceptance_summary = load_json(acceptance_summary_path)
    if acceptance_summary.get("decision") != "Programmable Acceptance Window = NO-GO":
        raise ValueError("frozen acceptance summary is not the required NO-GO")

    trace_path = FTC_ROOT / "analysis/static_self_calibration/calibration_trace.csv"
    trace = load_csv(trace_path, ("vdd_v", "code", "selected_tap", "D_code_ps", "W_S_int_ps", "Q"))
    mapping_path = FTC_ROOT / "analysis/static_self_calibration/range_mapping.json"
    mapping = load_json(mapping_path)
    if mapping.get("tap_list") != [10, 12, 14, 16, 18, 36, 37, 38]:
        raise ValueError("historical mapping is not the frozen root-cause mapping")
    old_tap18: Dict[float, Dict[str, str]] = {}
    for row in trace:
        if int(row["selected_tap"]) == 18:
            vdd = voltage_key(float(row["vdd_v"]))
            if vdd in old_tap18:
                raise ValueError("duplicate frozen tap18 row at {} V".format(vdd))
            old_tap18[vdd] = row
    if set(old_tap18) != set(VDD_POINTS):
        raise ValueError("frozen calibration trace lacks tap18 at every VDD anchor")

    architecture_path = FTC_ROOT / "analysis/minimal_pulse_comparator/architecture.json"
    architecture = load_json(architecture_path)
    threshold = architecture.get("threshold", {})
    if threshold.get("buffer_cell") != THRESHOLD_BUFFER_CELL or threshold.get("mux_cell") != MUX_CELL:
        raise ValueError("frozen threshold cell contract changed")
    if threshold.get("mux_count") != MUX_COUNT:
        raise ValueError("frozen MUX count changed")
    if architecture.get("sensor", {}).get("tap_index") != SENSOR_TAP_INDEX:
        raise ValueError("frozen sensor tap changed")
    if architecture.get("sensor", {}).get("initial_rvt_stages") != SENSOR_RVT_INITIAL_STAGES:
        raise ValueError("frozen sensor RVT initial stages changed")
    if architecture.get("sensor", {}).get("initial_lvt_stages") != SENSOR_LVT_INITIAL_STAGES:
        raise ValueError("frozen sensor LVT initial stages changed")
    if architecture.get("dff", {}).get("cell") != DFF_CELL:
        raise ValueError("frozen DFF cell changed")

    cells_path = FTC_ROOT / "discovery/selected_cells.json"
    cells = load_json(cells_path)
    if cells.get("delay_lvt", {}).get("cell") != THRESHOLD_BUFFER_CELL:
        raise ValueError("selected LVT BUF changed")
    if cells.get("xor2", {}).get("cell") != SENSOR_XOR_CELL:
        raise ValueError("selected XOR cell changed")
    if cells.get("dff", {}).get("cell") != DFF_CELL:
        raise ValueError("selected DFF cell changed")

    return {
        "root_cause_report": report_path,
        "attack_path": attack_path,
        "trip_path": trip_path,
        "acceptance_summary_path": acceptance_summary_path,
        "trace_path": trace_path,
        "mapping_path": mapping_path,
        "architecture_path": architecture_path,
        "cells_path": cells_path,
        "trace": trace,
        "mapping": mapping,
        "architecture": architecture,
        "cells": cells,
        "old_tap18": old_tap18,
    }


def validate_config(config: Mapping[str, Any]) -> None:
    """Enforce the fixed TT/25 C sensor and transient configuration."""

    expected = {
        "technology": "SMIC40LL",
        "corner": "tt",
        "temperature_c": 25.0,
        "observable_stages": OBSERVABLE_STAGES,
        "launch_time_s": 1.0e-9,
        "sampling_period_s": 6.0e-9,
        "tran_max_step_s": 1.0e-12,
    }
    for name, value in expected.items():
        actual = config.get(name)
        if isinstance(value, float):
            if finite_number(actual) != value:
                raise ValueError("FTC config {} must remain {}".format(name, value))
        elif actual != value:
            raise ValueError("FTC config {} must remain {!r}".format(name, value))
    selected = config.get("selected_operating_point")
    if not isinstance(selected, dict):
        raise ValueError("selected FTC operating point is missing")
    if selected.get("initial_rvt_stages") != SENSOR_RVT_INITIAL_STAGES:
        raise ValueError("selected RVT initial stages changed")
    if selected.get("initial_lvt_stages") != SENSOR_LVT_INITIAL_STAGES:
        raise ValueError("selected LVT initial stages changed")


def buffer_instance(name: str, output_node: str, input_node: str, cell: str) -> str:
    """Render a BUF with its six positional CDL ports explicitly connected.

    The port order is ``Y VDD VNW VPW VSS A``.  Both power pins and the N-well
    use ``vdd_a``; both ground pins and the P-well use ``vss_a``.  Keeping this
    connection in one helper prevents a hidden unpowered-well change between
    sizing and real-DFF probes.
    """

    return "{} {} vdd_a vdd_a vss_a vss_a {} {}".format(name, output_node, input_node, cell)


def mux_instance(name: str, output_node: str, input_a: str, input_b: str, select_node: str) -> str:
    """Render an MXT2 using verified A/B/S0 positional ports.

    The port order is ``Y VDD VNW VPW VSS A B S0``.  The selected-cell truth
    table is A for S0=0 and B for S0=1, so lower taps are always connected to A
    and higher taps to B at every balanced tree level.
    """

    return "{} {} vdd_a vdd_a vss_a vss_a {} {} {} {}".format(
        name, output_node, input_a, input_b, select_node, MUX_CELL
    )


def mux_tree_lines(taps: Sequence[int]) -> List[str]:
    """Render the fixed balanced 8:1 tree for exactly eight sorted taps."""

    if len(taps) != len(CODES) or any(right <= left for left, right in zip(taps, taps[1:])):
        raise ValueError("mapping must contain eight strictly increasing taps")
    lines = ["* Balanced 8:1 tree: code0 leaf, code1 middle, code2 root."]
    for group in range(4):
        lines.append(mux_instance(
            "XMUX_L1_{}".format(group), "mux_l1_{}".format(group),
            "thr_tap_{}".format(taps[2 * group]),
            "thr_tap_{}".format(taps[2 * group + 1]),
            "code0",
        ))
    for group in range(2):
        lines.append(mux_instance(
            "XMUX_L2_{}".format(group), "mux_l2_{}".format(group),
            "mux_l1_{}".format(2 * group),
            "mux_l1_{}".format(2 * group + 1),
            "code1",
        ))
    lines.append(mux_instance("XMUX_L3", "dff_ck", "mux_l2_0", "mux_l2_1", "code2"))
    return lines


def render_deck(
    config: Mapping[str, Any], cells: Mapping[str, Any], vdd_v: float,
    taps: Sequence[int], code: int, q_read_time_s: float,
    sizing: bool = False,
) -> str:
    """Render one complete same-rail FTC sensor/threshold/DFF deck.

    The long netlist block is intentionally explicit rather than generated from
    an abstract circuit graph.  That makes every physical port and every sensor
    load auditable in a retained deck.  A sizing probe selects the historical
    tap18 through a fixed eight-tap tree only to provide a realistic physical
    MUX load; its per-tap arrivals are screening data, not DFF conclusions.
    """

    if not (VDD_MIN_V <= vdd_v <= VDD_MAX_V):
        raise ValueError("VDD is outside the formal 0.80--1.10 V range")
    if code not in CODES:
        raise ValueError("code is outside the fixed 3-bit range")
    if not taps or any(tap < 1 or tap > MAX_TAP for tap in taps):
        raise ValueError("physical taps are outside the available chain")

    includes = ['.include "{}"'.format(cells["source_files"]["rvt_cdl"])]
    if Path(cells["source_files"]["lvt_cdl"]).resolve() != Path(cells["source_files"]["rvt_cdl"]).resolve():
        includes.append('.include "{}"'.format(cells["source_files"]["lvt_cdl"]))
    launch = float(config["launch_time_s"])
    stop = launch + float(config["sampling_period_s"]) - float(config["tran_max_step_s"])
    bits = tuple((code >> bit) & 1 for bit in range(3))
    lines = [
        "* FTC delay-code boundary refinement physical probe.",
        "* TT/25C; frozen tap29 sensor; one LVT threshold chain; real MUX and DFF.",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(float(config["temperature_c"]))),
        *includes,
        '.lib "{}" {}'.format(config["model_library"], config["corner"]),
        ".param VDD_VALUE={}".format(spice(vdd_v)),
        "V_VDD vdd_a vss_a 'VDD_VALUE'",
        "V_VSS vss_a 0 0",
        "V_SCLK s_clk vss_a PULSE(0 'VDD_VALUE' {} 1.000000000000e-12 1.000000000000e-12 {} {})".format(
            spice(launch), spice(float(config["sampling_period_s"]) / 2.0), spice(float(config["sampling_period_s"]))
        ),
        "* Static 3-bit code rails: code0 is least significant; code2 is most significant.",
        "V_CODE0 code0 vss_a {}".format("'VDD_VALUE'" if bits[0] else "0"),
        "V_CODE1 code1 vss_a {}".format("'VDD_VALUE'" if bits[1] else "0"),
        "V_CODE2 code2 vss_a {}".format("'VDD_VALUE'" if bits[2] else "0"),
        "* Active-high reset is held during code settling and released before launch.",
        "V_DFF_RESET dff_reset vss_a PWL(0 'VDD_VALUE' {} 'VDD_VALUE' {} 0 {} 0)".format(
            spice(launch - 2.0e-10), spice(launch - 2.0e-10 + 1.0e-11), spice(stop)
        ),
        "",
        "* Frozen four-stage RVT sensor initial path.",
    ]

    rvt_input = "s_clk"
    for stage in range(SENSOR_RVT_INITIAL_STAGES):
        output = "rvt_initial_{}".format(stage)
        lines.append(buffer_instance("XRVT_INIT_{:02d}".format(stage), output, rvt_input, cells["delay_rvt"]["cell"]))
        rvt_input = output

    lines.append("* Thirty observable RVT/LVT stages and all real XOR loads are retained.")
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

    lines.append("* LVT threshold chain extends to the highest physical tap in this probe.")
    threshold_input = "xor_29"
    for tap in range(1, max(taps) + 1):
        output = "thr_tap_{}".format(tap)
        lines.append(buffer_instance("XTHR_BUF_{:02d}".format(tap), output, threshold_input, cells["delay_lvt"]["cell"]))
        threshold_input = output

    tree_taps = SIZING_TREE_TAPS if sizing else tuple(taps)
    lines.extend(["", *mux_tree_lines(tree_taps), "", "* DFF ports: Q VDD VNW VPW VSS CK D R."])
    # DFF positional ports are explicitly documented here: Q is the observed
    # state, CK is the selected threshold clock, D is xor_29, and R is the
    # active-high asynchronous reset.  This is the real comparator boundary.
    lines.append("XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(cells["dff"]["cell"]))
    lines.extend([
        "",
        ".tran {} {}".format(spice(float(config["tran_max_step_s"])), spice(stop)),
        ".measure tran t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1",
        ".measure tran t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1",
        ".measure tran t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1",
        ".measure tran q_final_v FIND v(q_final,vss_a) AT={}".format(spice(q_read_time_s)),
        ".measure tran vdd_a_min_v MIN v(vdd_a,vss_a) FROM=0 TO {}".format(spice(stop)),
    ])
    if sizing:
        for tap in SCREEN_TAPS:
            lines.append(".measure tran t_thr_tap_{:02d}_rise WHEN v(thr_tap_{},vss_a)='VDD_VALUE/2' RISE=1".format(tap, tap))
    lines.extend([".end", ""])
    return "\n".join(lines)


def execute_probe(
    hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any],
    label: str, vdd_v: float, taps: Sequence[int], code: int,
    q_read_time_s: float, sizing: bool = False,
) -> Dict[str, Any]:
    """Run one isolated deck and retain command, listing, and MEAS evidence."""

    scenario = run_dir / "scenarios" / label
    scenario.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(FTC_ROOT / "spice/empty_subckt.sp_cal", scenario / "empty_subckt.sp_cal")
    deck = scenario / "delay_code_refinement.sp"
    deck.write_text(render_deck(config, cells, vdd_v, taps, code, q_read_time_s, sizing), encoding="ascii")
    command = [str(hspice), deck.name, "-o", "delay_code_refinement"]
    result = subprocess.run(
        command, cwd=str(scenario), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True, check=False, timeout=300,
    )
    (scenario / "hspice_command.log").write_text(
        "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            " ".join(command), result.returncode, result.stdout, result.stderr
        ), encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, scenario))
    warnings = run_dc_sweep.validate_listing(scenario / "delay_code_refinement.lis")
    values = run_dc_sweep.parse_measurements(run_dc_sweep.find_measurement_file(scenario, "delay_code_refinement"))
    return {
        "scenario": str(scenario.relative_to(run_dir)), "warnings": warnings,
        "vdd_v": float(vdd_v), "code": int(code), "t_xor_rise_s": values.get("t_xor_rise"),
        "t_xor_fall_s": values.get("t_xor_fall"), "t_ck_rise_s": values.get("t_ck_rise"),
        "q_final_v": values.get("q_final_v"), "vdd_a_min_v": values.get("vdd_a_min_v"),
        "q_read_time_s": q_read_time_s,
        "tap_arrivals_s": {
            tap: values.get("t_thr_tap_{:02d}_rise".format(tap)) for tap in SCREEN_TAPS
        } if sizing else {},
    }


def classify_probe(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Classify real timing and Q while enforcing the 200 ps Q-settle rule."""

    names = ("t_xor_rise_s", "t_xor_fall_s", "t_ck_rise_s", "q_final_v")
    values = {name: finite_number(record.get(name)) for name in names}
    result: Dict[str, Any] = {"valid": False, "Q": None, "W_S_int_ps": None, "D_code_ps": None}
    if any(values[name] is None for name in names):
        return result
    width_s = float(values["t_xor_fall_s"]) - float(values["t_xor_rise_s"])
    delay_s = float(values["t_ck_rise_s"]) - float(values["t_xor_rise_s"])
    readout = float(record["q_read_time_s"])
    if width_s <= 0.0 or delay_s <= 0.0 or float(values["t_ck_rise_s"]) > readout - Q_SETTLE_S:
        return result
    vdd_v = float(record["vdd_v"])
    result.update({
        "valid": True,
        "Q": 1 if float(values["q_final_v"]) >= vdd_v / 2.0 else 0,
        "W_S_int_ps": width_s * 1.0e12,
        "D_code_ps": delay_s * 1.0e12,
    })
    return result


def build_screen_rows(records: Sequence[Mapping[str, Any]], frozen: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Convert the three sizing scenarios into raw and estimated tap delays."""

    old_tap18 = frozen["old_tap18"]
    rows: List[Dict[str, Any]] = []
    for record in records:
        vdd_v = voltage_key(float(record["vdd_v"]))
        xor_rise = finite_number(record.get("t_xor_rise_s"))
        xor_fall = finite_number(record.get("t_xor_fall_s"))
        tap18_arrival = finite_number(record.get("tap_arrivals_s", {}).get(18))
        old_d = finite_number(old_tap18[vdd_v].get("D_code_ps"))
        width_ps = None if xor_rise is None or xor_fall is None else (xor_fall - xor_rise) * 1.0e12
        mux_est = None if tap18_arrival is None or xor_rise is None or old_d is None else old_d - (tap18_arrival - xor_rise) * 1.0e12
        for tap in SCREEN_TAPS:
            arrival = finite_number(record.get("tap_arrivals_s", {}).get(tap))
            raw = None if arrival is None or xor_rise is None else (arrival - xor_rise) * 1.0e12
            estimated = None if raw is None or mux_est is None else raw + mux_est
            valid = int(width_ps is not None and raw is not None and estimated is not None and math.isfinite(estimated))
            rows.append({
                "vdd_v": vdd_v, "tap": tap, "t_xor_rise_s": xor_rise,
                "t_xor_fall_s": xor_fall, "W_S_int_ps": width_ps,
                "t_tap_rise_s": arrival, "D_raw_ps": raw,
                "D_mux_est_ps": mux_est, "D_est_ps": estimated, "valid": valid,
            })
    if len(rows) != len(SCREEN_VDD_POINTS) * len(SCREEN_TAPS):
        raise ValueError("sizing did not produce all screen tap rows")
    return rows


def screen_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[float, Dict[str, Any]]:
    """Validate sizing monotonicity and index one summary per screening VDD."""

    result: Dict[float, Dict[str, Any]] = {}
    for vdd_v in SCREEN_VDD_POINTS:
        local = sorted([row for row in rows if voltage_key(float(row["vdd_v"])) == vdd_v], key=lambda row: int(row["tap"]))
        if len(local) != len(SCREEN_TAPS) or any(int(row["valid"]) != 1 for row in local):
            raise ValueError("invalid sizing data at {:.2f} V".format(vdd_v))
        delays = [float(row["D_est_ps"]) for row in local]
        if any(right <= left for left, right in zip(delays, delays[1:])):
            raise ValueError("estimated tap delays are not strictly increasing at {:.2f} V".format(vdd_v))
        result[vdd_v] = {
            "W_S_int_ps": float(local[0]["W_S_int_ps"]),
            "taps": [int(row["tap"]) for row in local],
            "D_est_ps": delays,
        }
    return result


def interpolate(value_low: float, value_high: float, low_v: float, high_v: float, vdd_v: float) -> float:
    """Linearly interpolate only between the three measured screening anchors."""

    fraction = (vdd_v - low_v) / (high_v - low_v)
    return value_low + fraction * (value_high - value_low)


def interpolated_screen(summary: Mapping[float, Mapping[str, Any]], vdd_v: float, tap: int) -> Tuple[float, float]:
    """Return screening ``(D_est, W)`` for a legal VDD using piecewise interpolation."""

    if vdd_v <= 0.95:
        low_v, high_v = 0.80, 0.95
    else:
        low_v, high_v = 0.95, 1.10
    index = tap - SCREEN_TAPS[0]
    low_d = float(summary[low_v]["D_est_ps"][index])
    high_d = float(summary[high_v]["D_est_ps"][index])
    low_w = float(summary[low_v]["W_S_int_ps"])
    high_w = float(summary[high_v]["W_S_int_ps"])
    return interpolate(low_d, high_d, low_v, high_v, vdd_v), interpolate(low_w, high_w, low_v, high_v, vdd_v)


def boundary_tap(summary: Mapping[float, Mapping[str, Any]], vdd_v: float) -> int:
    """Find the first physical tap whose screening delay reaches the pulse."""

    for tap in SCREEN_TAPS:
        d_est, width = interpolated_screen(summary, vdd_v, tap)
        if d_est >= width:
            return tap
    raise ValueError("screening boundary is beyond tap38 at {:.2f} V".format(vdd_v))


def half_up(value: float) -> int:
    """Round a positive midpoint deterministically without banker rounding."""

    return int(math.floor(value + 0.5))


def mapping_is_valid(taps: Sequence[int]) -> bool:
    """Check the fixed 3-bit physical mapping contract."""

    return (
        len(taps) == len(CODES)
        and all(1 <= int(tap) <= MAX_TAP for tap in taps)
        and all(right > left for left, right in zip(taps, taps[1:]))
    )


def make_candidate(summary: Mapping[float, Mapping[str, Any]], guard: int) -> Dict[str, Any]:
    """Construct one small boundary-centered mapping from three anchor taps.

    ``guard=1`` is the primary placement.  It leaves two shorter choices before
    the high-VDD corridor, places the next code just beyond the estimated high
    boundary, uses the midpoint to cover the 0.95 V corridor, and reserves
    three consecutive long choices at the low-VDD end.  ``guard=2`` is the sole
    fallback variant and changes only this local physical guard; it is not a
    combinatorial search.
    """

    high = boundary_tap(summary, 1.10)
    middle = boundary_tap(summary, 0.95)
    low = boundary_tap(summary, 0.80)
    taps = (
        high - 2,
        high - 1,
        high + guard,
        middle + guard,
        half_up((middle + low) / 2.0) + guard - 1,
        low + guard,
        low + guard + 1,
        low + guard + 2,
    )
    if not mapping_is_valid(taps):
        raise ValueError("boundary corridor cannot form a valid 8-tap mapping")
    predicted: Dict[str, int] = {}
    for vdd_v in VDD_POINTS:
        first_code = None
        for code, tap in enumerate(taps):
            d_est, width = interpolated_screen(summary, vdd_v, int(tap))
            if d_est >= width:
                first_code = code
                break
        if first_code is None or not (1 <= first_code <= 5):
            raise ValueError("screening predicts an invalid first-zero code at {:.2f} V".format(vdd_v))
        predicted["{:.2f}".format(vdd_v)] = first_code
    return {
        "tap_list": list(taps),
        "code_to_tap": {str(code): int(taps[code]) for code in CODES},
        "boundary_taps": {"1.10": high, "0.95": middle, "0.80": low},
        "guard": guard,
        "predicted_first_zero_code": predicted,
    }


def classify_screen_q(record: Mapping[str, Any]) -> bool:
    """Check only that the sizing probe produced a usable pulse measurement."""

    xor_rise = finite_number(record.get("t_xor_rise_s"))
    xor_fall = finite_number(record.get("t_xor_fall_s"))
    if xor_rise is None or xor_fall is None or xor_fall <= xor_rise:
        return False
    return all(finite_number(value) is not None for value in record.get("tap_arrivals_s", {}).values())


def candidate_prediction(candidate: Mapping[str, Any], vdd_v: float) -> int:
    """Return the precomputed screening first-zero code for one legal VDD."""

    return int(candidate["predicted_first_zero_code"]["{:.2f}".format(vdd_v)])


def run_calibration(
    hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any],
    candidate_id: str, candidate: Mapping[str, Any], q_read_time_s: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run exactly four real-DFF probes around each predicted boundary."""

    taps = tuple(int(tap) for tap in candidate["tap_list"])
    rows: List[Dict[str, Any]] = []
    per_voltage: List[Dict[str, Any]] = []
    for vdd_v in VDD_POINTS:
        predicted_k = candidate_prediction(candidate, vdd_v)
        codes = tuple(range(predicted_k - 1, predicted_k + 3)) if 1 <= predicted_k <= 5 else tuple()
        local: List[Dict[str, Any]] = []
        if not codes:
            per_voltage.append({"vdd_v": vdd_v, "predicted_k": predicted_k, "decision": "NO-GO", "reasons": ["predicted k is outside 1..5"]})
            continue
        for code in codes:
            label = "cal_{}_v{:03d}mv_k{}_code{}".format(candidate_id, int(round(vdd_v * 1000.0)), predicted_k, code)
            record = execute_probe(hspice, run_dir, config, cells, label, vdd_v, taps, code, q_read_time_s)
            classified = classify_probe(record)
            row = {
                "candidate_id": candidate_id, "vdd_v": vdd_v, "predicted_k": predicted_k,
                "code": code, "selected_tap": taps[code],
                "t_xor_rise_s": record.get("t_xor_rise_s"), "t_xor_fall_s": record.get("t_xor_fall_s"),
                "W_S_int_ps": classified["W_S_int_ps"], "t_ck_rise_s": record.get("t_ck_rise_s"),
                "D_code_ps": classified["D_code_ps"], "q_final_v": record.get("q_final_v"),
                "Q": classified["Q"], "readout_time_s": q_read_time_s,
                "scenario": record["scenario"], "valid": int(classified["valid"]),
                "scenario": record["scenario"],
            }
            rows.append(row)
            local.append(row)
        reasons: List[str] = []
        if len(local) != 4 or any(int(row["valid"]) != 1 for row in local):
            reasons.append("one or more real-DFF probes are invalid")
        q_values = [int(row["Q"]) for row in local if row["Q"] is not None]
        delays = [float(row["D_code_ps"]) for row in local if row["D_code_ps"] is not None]
        if q_values != [1, 0, 0, 0]:
            reasons.append("Q(k-1..k+2) is not [1,0,0,0]")
        if len(delays) != 4 or any(right <= left for left, right in zip(delays, delays[1:])):
            reasons.append("D(k-1..k+2) is not strictly increasing")
        per_voltage.append({
            "vdd_v": vdd_v, "predicted_k": predicted_k,
            "decision": "GO" if not reasons else "NO-GO", "reasons": reasons,
            "q_sequence": q_values, "d_code_ps": delays,
            "lock_code": predicted_k if not reasons else None,
        })
    passed = len(per_voltage) == len(VDD_POINTS) and all(item["decision"] == "GO" for item in per_voltage)
    locks = {"{:.2f}".format(item["vdd_v"]): item["lock_code"] for item in per_voltage if item.get("lock_code") is not None}
    return rows, {
        "candidate_id": candidate_id, "decision": "GO" if passed else "NO-GO",
        "per_voltage": per_voltage, "locks": locks,
        "reasons": [reason for item in per_voltage for reason in item.get("reasons", [])],
    }


def coarse_points(baseline_vdd_v: float) -> List[float]:
    """Build the descending legal 50 mV attack schedule."""

    current = voltage_key(baseline_vdd_v - COARSE_STEP_V)
    points: List[float] = []
    while current >= VDD_MIN_V - 1.0e-12:
        points.append(current)
        current = voltage_key(current - COARSE_STEP_V)
    if not points or points[-1] < VDD_MIN_V:
        raise ValueError("coarse schedule does not reach the legal lower rail")
    return points


def refinement_points(last_zero_v: float, first_one_v: float) -> List[float]:
    """Return only interior 10 mV points between the final coarse bracket."""

    if not last_zero_v > first_one_v >= VDD_MIN_V:
        raise ValueError("invalid Q=0/Q=1 refinement bracket")
    result: List[float] = []
    current = voltage_key(last_zero_v - REFINEMENT_STEP_V)
    while current > first_one_v + 1.0e-12:
        result.append(current)
        current = voltage_key(current - REFINEMENT_STEP_V)
    return result


def run_feasibility(
    hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any],
    candidate_id: str, candidate: Mapping[str, Any], calibration: Mapping[str, Any], q_read_time_s: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run the three-baseline M=1/M=2 adaptive static-droop Gate."""

    taps = tuple(int(tap) for tap in candidate["tap_list"])
    rows: List[Dict[str, Any]] = []
    trip_rows: List[Dict[str, Any]] = []
    q_reversions: List[str] = []
    lock_by_v = {float(key): int(value) for key, value in calibration["locks"].items()}
    for baseline_vdd_v in FEASIBILITY_BASELINES:
        if baseline_vdd_v not in lock_by_v:
            return rows, {"candidate_id": candidate_id, "decision": "NO-GO", "trip_rows": trip_rows, "reasons": ["missing calibration lock at {:.2f} V".format(baseline_vdd_v)]}
        lock_code = lock_by_v[baseline_vdd_v]
        for margin_code in (1, 2):
            alarm_code = lock_code + margin_code
            if alarm_code > MAX_CODE:
                trip_rows.append({"baseline_vdd_v": baseline_vdd_v, "margin_code": margin_code, "trip_status": "INVALID", "reason": "alarm code outside 3-bit range"})
                continue
            group: List[Dict[str, Any]] = []
            last_zero: Optional[float] = None
            first_one: Optional[float] = None
            for attack_vdd_v in coarse_points(baseline_vdd_v):
                label = "feas_{}_v{:03d}mv_m{}_attack_{:03d}mv_coarse".format(
                    candidate_id, int(round(baseline_vdd_v * 1000.0)), margin_code, int(round(attack_vdd_v * 1000.0))
                )
                record = execute_probe(hspice, run_dir, config, cells, label, attack_vdd_v, taps, alarm_code, q_read_time_s)
                classified = classify_probe({**record, "vdd_v": attack_vdd_v})
                row = {
                    "candidate_id": candidate_id, "baseline_vdd_v": baseline_vdd_v, "attack_vdd_v": attack_vdd_v,
                    "margin_code": margin_code, "lock_code": lock_code, "alarm_code": alarm_code,
                    "selected_tap": taps[alarm_code], "scan_phase": "coarse", "scenario": record["scenario"],
                    "W_S_int_ps": classified["W_S_int_ps"], "D_alarm_ps": classified["D_code_ps"],
                    "Q": classified["Q"], "alarm": classified["Q"], "valid": int(classified["valid"]),
                }
                rows.append(row)
                group.append(row)
                if not classified["valid"]:
                    break
                if int(classified["Q"]) == 1:
                    first_one = attack_vdd_v
                    break
                last_zero = attack_vdd_v
            if last_zero is not None and first_one is not None:
                for attack_vdd_v in refinement_points(last_zero, first_one):
                    label = "feas_{}_v{:03d}mv_m{}_attack_{:03d}mv_refinement".format(
                        candidate_id, int(round(baseline_vdd_v * 1000.0)), margin_code, int(round(attack_vdd_v * 1000.0))
                    )
                    record = execute_probe(hspice, run_dir, config, cells, label, attack_vdd_v, taps, alarm_code, q_read_time_s)
                    classified = classify_probe({**record, "vdd_v": attack_vdd_v})
                    row = {
                        "candidate_id": candidate_id, "baseline_vdd_v": baseline_vdd_v, "attack_vdd_v": attack_vdd_v,
                        "margin_code": margin_code, "lock_code": lock_code, "alarm_code": alarm_code,
                        "selected_tap": taps[alarm_code], "scan_phase": "refinement", "scenario": record["scenario"],
                        "W_S_int_ps": classified["W_S_int_ps"], "D_alarm_ps": classified["D_code_ps"],
                        "Q": classified["Q"], "alarm": classified["Q"], "valid": int(classified["valid"]),
                    }
                    rows.append(row)
                    group.append(row)
                    if not classified["valid"] or int(classified["Q"]) == 1:
                        break
            ordered = sorted(group, key=lambda row: float(row["attack_vdd_v"]), reverse=True)
            status = "NO_IN_RANGE_TRIP"
            trip_vdd: Optional[float] = None
            depth: Optional[float] = None
            reasons: List[str] = []
            if not ordered or any(int(row["valid"]) != 1 for row in ordered):
                status = "INVALID"
                reasons.append("invalid physical droop measurement")
            else:
                q_values = [int(row["Q"]) for row in ordered]
                if any(right < left for left, right in zip(q_values, q_values[1:])):
                    q_reversions.append("{:.2f}V/M{}".format(baseline_vdd_v, margin_code))
                high_rows = [row for row in ordered if int(row["Q"]) == 1]
                if high_rows:
                    trip_vdd = max(float(row["attack_vdd_v"]) for row in high_rows)
                    depth = (baseline_vdd_v - trip_vdd) * 1000.0
                    status = "TRIP"
            trip_rows.append({
                "baseline_vdd_v": baseline_vdd_v, "lock_code": lock_code,
                "margin_code": margin_code, "alarm_code": alarm_code,
                "trip_status": status, "trip_vdd_v": trip_vdd, "trip_depth_mv": depth,
                "reasons": reasons,
            })

    by_key = {(float(row["baseline_vdd_v"]), int(row["margin_code"])): row for row in trip_rows}
    reasons: List[str] = []
    for baseline_vdd_v in FEASIBILITY_BASELINES:
        m1 = by_key.get((baseline_vdd_v, 1), {})
        m2 = by_key.get((baseline_vdd_v, 2), {})
        if m1.get("trip_status") != "TRIP":
            reasons.append("M=1 has no legal trip at {:.2f} V".format(baseline_vdd_v))
        if m2.get("trip_status") != "TRIP":
            reasons.append("M=2 has no legal trip at {:.2f} V".format(baseline_vdd_v))
        if m1.get("trip_status") == "TRIP" and m2.get("trip_status") == "TRIP" and float(m2["trip_depth_mv"]) + 1.0e-9 < float(m1["trip_depth_mv"]):
            reasons.append("M=2 is shallower than M=1 at {:.2f} V".format(baseline_vdd_v))
    if q_reversions:
        reasons.append("Q reversion at {}".format(", ".join(q_reversions)))
    distinct = []
    if not reasons:
        for baseline_vdd_v in FEASIBILITY_BASELINES:
            m1 = by_key[(baseline_vdd_v, 1)]
            m2 = by_key[(baseline_vdd_v, 2)]
            if float(m2["trip_depth_mv"]) - float(m1["trip_depth_mv"]) >= 10.0 - 1.0e-9:
                distinct.append(baseline_vdd_v)
        if not distinct:
            reasons.append("no 10 mV-grid distinction between M=1 and M=2")
    return rows, {
        "candidate_id": candidate_id, "decision": "GO" if not reasons else "NO-GO",
        "trip_rows": trip_rows, "distinct_boundary_baselines_v": distinct,
        "q_reversions": q_reversions, "reasons": reasons,
    }


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    """Write a deterministic public CSV, leaving absent measures blank."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write stable, human-readable JSON evidence."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prepare_run(run_dir: Path, config: Mapping[str, Any], frozen: Mapping[str, Any]) -> Path:
    """Preflight HSPICE/collateral and create one non-overwritable raw root."""

    if run_dir.exists():
        raise ValueError("refusing to overwrite existing refinement run: {}".format(run_dir))
    hspice = require_regular_file(Path(config["hspice"]), "HSPICE executable", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if str(config["expected_hspice_version"]) not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    collateral = list(frozen["cells"]["source_files"].values()) + [config["model_library"], FTC_ROOT / "spice/empty_subckt.sp_cal"]
    checked = [require_regular_file(Path(path), "FTC collateral") for path in collateral]
    run_dir.mkdir(parents=True)
    frozen_paths = [
        frozen["root_cause_report"], frozen["attack_path"], frozen["trip_path"],
        frozen["acceptance_summary_path"], frozen["trace_path"], frozen["mapping_path"],
        frozen["architecture_path"], frozen["cells_path"],
    ]
    manifest = {
        "study": "ftc_delay_code_boundary_refinement",
        "scope": "TT/25C sizing, real-DFF calibration Gate, three-baseline static droop only",
        "hspice": str(hspice), "hspice_version": version,
        "formal_vdd_range_v": [VDD_MIN_V, VDD_MAX_V],
        "screen_vdd_v": list(SCREEN_VDD_POINTS),
        "calibration_vdd_v": list(VDD_POINTS),
        "feasibility_baselines_v": list(FEASIBILITY_BASELINES),
        "max_candidates": MAX_CANDIDATES,
        "source_sha256": {str(path): sha256_file(path) for path in checked},
        "frozen_input_sha256": {str(path): sha256_file(Path(path)) for path in frozen_paths},
    }
    write_json(run_dir / "manifest.json", manifest)
    return hspice


def render_report(path: Path, summary: Mapping[str, Any]) -> None:
    """Publish the final bounded decision without claiming full characterization."""

    decision = summary["decision"]
    lines = [
        "# FTC Delay-Code Boundary Refinement", "",
        "## Decision", "", "**{}**".format(decision), "",
        "## Scope", "",
        "- 保持 tap29 sensor、真实 XOR/DFF、3-bit、7-MUX 和 0.80--1.10 V 不变。",
        "- 只执行 3 个 sizing、最小 calibration Gate 和 3 个 baseline 的 feasibility Gate。",
        "- 不重跑旧 42 个 acceptance-window 或旧 54 个 static-calibration probes。", "",
        "## Candidate Attempts", "",
        "| Candidate | Calibration | Feasibility | Taps |", "|---|---|---|---|",
    ]
    for attempt in summary.get("candidate_attempts", []):
        lines.append("| {} | {} | {} | `{}` |".format(
            attempt["candidate_id"], attempt["calibration"]["decision"],
            attempt.get("feasibility", {}).get("decision", "NOT_RUN"),
            ",".join(str(tap) for tap in attempt["mapping"]["tap_list"]),
        ))
    lines.extend(["", "## Gate Evidence", ""])
    reasons = summary.get("decision_reasons", [])
    if reasons:
        lines.extend(["- {}".format(reason) for reason in reasons])
    else:
        lines.append("- 七个正常 VDD、三个代表 baseline 和 M=1/M=2 ordering 均通过。")
    lines.extend([
        "", "## Next Step", "",
        "- {}".format(summary.get("next_step", "stop")),
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def refined_mapping_allowed(summary: Mapping[str, Any]) -> bool:
    """Return the single publication predicate for ``refined_mapping.json``."""

    return summary.get("decision") == "Delay-Code Boundary Refinement = GO" and bool(summary.get("candidate_attempts"))


def final_decision(final_go: bool) -> Tuple[str, str]:
    """Translate the two physical Gates into the task's only terminal actions."""

    if final_go:
        return (
            "Delay-Code Boundary Refinement = GO",
            "READY_FOR_FULL_ACCEPTANCE_WINDOW_CHARACTERIZATION",
        )
    return (
        "3-bit Boundary-Centered Mapping = NO-GO",
        "stop; do not add monitor RTL, expand bit-width, or enter PVT",
    )


def build_summary(
    run_dir: Path, q_read_time_s: float, screen_scenarios: int,
    attempts: Sequence[Mapping[str, Any]], final_go: bool,
) -> Dict[str, Any]:
    """Build the final public decision from retained candidate Gate records.

    Keeping this publication-only transformation separate from HSPICE execution
    makes the terminal evidence auditable and testable.  It never reclassifies
    a waveform: every reason comes from an already-recorded calibration or
    feasibility Gate result.
    """

    decision, next_step = final_decision(final_go)
    reasons: List[str] = []
    for attempt in attempts:
        candidate_id = str(attempt["candidate_id"])
        calibration = attempt["calibration"]
        per_voltage = list(calibration.get("per_voltage", []))
        if per_voltage:
            for item in per_voltage:
                for reason in item.get("reasons", []):
                    reasons.append("{} / {:.2f} V: {}".format(candidate_id, float(item["vdd_v"]), reason))
        else:
            for reason in calibration.get("reasons", []):
                reasons.append("{} / calibration: {}".format(candidate_id, reason))
        for reason in attempt.get("feasibility", {}).get("reasons", []):
            reasons.append("{} / feasibility: {}".format(candidate_id, reason))
    return {
        "schema_version": 1, "study": "ftc_delay_code_boundary_refinement",
        "decision": decision, "next_step": next_step,
        "formal_vdd_range_v": [VDD_MIN_V, VDD_MAX_V], "q_read_time_s": q_read_time_s,
        "screen_scenarios": screen_scenarios, "candidate_count": len(attempts),
        "candidate_attempts": list(attempts), "decision_reasons": reasons,
        "raw_run": str(run_dir),
    }


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Expose only output locations; electrical choices remain fixed constants."""

    parser = argparse.ArgumentParser(description="run FTC delay-code boundary refinement")
    parser.add_argument("--config", type=Path, default=FTC_ROOT / "ftc_config.json")
    parser.add_argument("--run-dir", type=Path, default=FTC_ROOT / "runs/delay_code_refinement/r1")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis/delay_code_refinement")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports/FTC_DELAY_CODE_BOUNDARY_REFINEMENT.md")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Execute every bounded phase and publish only validated new evidence."""

    args = parse_args(argv)
    config = load_json(args.config.resolve())
    validate_config(config)
    frozen = frozen_inputs()
    run_dir = args.run_dir.resolve()
    analysis_dir = args.analysis_dir.resolve()
    report_output = args.report_output.resolve()
    hspice = prepare_run(run_dir, config, frozen)

    # Step 1: exactly three sizing scenarios, one per mandated screening VDD.
    sizing_records: List[Dict[str, Any]] = []
    for vdd_v in SCREEN_VDD_POINTS:
        label = "sizing_tt25_v{:03d}mv".format(int(round(vdd_v * 1000.0)))
        record = execute_probe(
            hspice, run_dir, config, frozen["cells"], label, vdd_v,
            tuple(range(1, MAX_TAP + 1)), 4, SCREEN_Q_READ_TIME_S, sizing=True,
        )
        if not classify_screen_q(record):
            raise RuntimeError("sizing probe is incomplete at {:.2f} V".format(vdd_v))
        sizing_records.append(record)
    screen_rows = build_screen_rows(sizing_records, frozen)
    screen = screen_summary(screen_rows)
    write_csv(analysis_dir / "tap_screen.csv", TAP_SCREEN_FIELDS, screen_rows)

    # Step 2: one deterministic primary map.  A second map is constructed only
    # after a real physical Gate rejects the primary; no broad search is hidden.
    primary = make_candidate(screen, guard=1)
    candidate_file = analysis_dir / "candidate_mapping.json"
    candidate_payload: Dict[str, Any] = {
        "schema_version": 1, "screen_vdd_v": list(SCREEN_VDD_POINTS),
        "candidate_count": 1, "selected_candidate": None,
        "candidates": [{"candidate_id": "primary", **primary}],
    }
    write_json(candidate_file, candidate_payload)
    q_read_time_s = max(
        SCREEN_Q_READ_TIME_S,
        max(
            float(record["t_xor_rise_s"]) + float(screen[vdd_v]["D_est_ps"][-1]) * 1.0e-12 + Q_SETTLE_S
            for record, vdd_v in zip(sizing_records, SCREEN_VDD_POINTS)
        ),
    )
    if q_read_time_s >= float(config["launch_time_s"]) + float(config["sampling_period_s"]):
        raise RuntimeError("derived Q readout is outside the transient window")

    attempts: List[Dict[str, Any]] = []
    all_calibration_rows: List[Dict[str, Any]] = []
    all_feasibility_rows: List[Dict[str, Any]] = []
    candidates_to_try: List[Tuple[str, Dict[str, Any]]] = [("primary", primary)]
    final_go = False
    for candidate_index, (candidate_id, candidate) in enumerate(candidates_to_try):
        calibration_rows, calibration = run_calibration(
            hspice, run_dir, config, frozen["cells"], candidate_id, candidate, q_read_time_s
        )
        all_calibration_rows.extend(calibration_rows)
        feasibility: Dict[str, Any] = {"decision": "NOT_RUN", "reasons": []}
        feasibility_rows: List[Dict[str, Any]] = []
        if calibration["decision"] == "GO":
            feasibility_rows, feasibility = run_feasibility(
                hspice, run_dir, config, frozen["cells"], candidate_id, candidate, calibration, q_read_time_s
            )
            all_feasibility_rows.extend(feasibility_rows)
        attempts.append({"candidate_id": candidate_id, "mapping": candidate, "calibration": calibration, "feasibility": feasibility})
        if calibration["decision"] == "GO" and feasibility["decision"] == "GO":
            final_go = True
            candidate_payload["selected_candidate"] = candidate_id
            break
        if candidate_index == 0:
            # The only permitted fallback is generated after primary physical
            # failure, and it is still derived solely from the same screen.
            try:
                fallback = make_candidate(screen, guard=2)
            except ValueError:
                fallback = None
            if fallback is not None:
                candidates_to_try.append(("fallback", fallback))
                candidate_payload["candidates"].append({"candidate_id": "fallback", **fallback})
                candidate_payload["candidate_count"] = 2
                write_json(candidate_file, candidate_payload)

    candidate_payload["candidate_count"] = len(attempts)
    candidate_payload["attempts"] = attempts
    if final_go:
        candidate_payload["selected_candidate"] = attempts[-1]["candidate_id"]
    write_json(candidate_file, candidate_payload)
    write_csv(analysis_dir / "calibration_gate.csv", CALIBRATION_FIELDS, all_calibration_rows)
    write_csv(analysis_dir / "acceptance_feasibility.csv", FEASIBILITY_FIELDS, all_feasibility_rows)

    summary = build_summary(run_dir, q_read_time_s, len(sizing_records), attempts, final_go)
    write_json(analysis_dir / "summary.json", summary)
    if refined_mapping_allowed(summary):
        selected = attempts[-1]["mapping"]
        write_json(analysis_dir / "refined_mapping.json", {
            "schema_version": 1, "decision": "READY_FOR_FULL_ACCEPTANCE_WINDOW_CHARACTERIZATION",
            "tap_list": selected["tap_list"], "code_to_tap": selected["code_to_tap"],
            "validated_vdd_range_v": [VDD_MIN_V, VDD_MAX_V],
            "selection_basis": "boundary-centered refinement with real-DFF and droop feasibility Gates",
        })
    render_report(report_output, summary)
    print("FTC_DELAY_CODE_BOUNDARY_REFINEMENT decision={} candidates={}".format(decision, len(attempts)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
