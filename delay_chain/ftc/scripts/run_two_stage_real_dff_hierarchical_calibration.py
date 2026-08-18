#!/usr/bin/env python3
"""Run the bounded FTC two-stage delay line plus real-DFF calibration study.

This task owns only the new integrated topology.  Earlier medium, fine, XOR,
and DFF campaigns are immutable evidence: their runners are never imported or
executed here.  The small local netlist helpers deliberately spell out the
approved topology so ``xor_29`` is both DFF data and the input of the N=16
medium stage, which is the physical question this study must answer.
"""

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
PHASE1_SCRIPTS = FTC_ROOT.parent / "phase1" / "scripts"
if str(PHASE1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PHASE1_SCRIPTS))
import run_dc_sweep  # noqa: E402  # Shared only for HSPICE listing/MEAS validation.


STUDY = "two_stage_real_dff_hierarchical_calibration_v1"
ANCHOR_VDD = (0.95, 1.10, 0.80)  # The mandatory early-stop order.
MEDIUM_N = 16
MEDIUM_DELAY_CELL = "BUF_X0P7M_A9TL40"
MEDIUM_MUX_CELL = "MXT2_X0P5M_A9TL40"
FINE_DRIVER = "BUF_X0P8M_A9TL40"
FINE_LOAD = "NOR2_X4A_A9TL40__signal_A"
FINE_LOAD_CELL = "NOR2_X4A_A9TL40"
FINE_K = 10
SENSOR_RVT_INITIAL = 4
SENSOR_LVT_INITIAL = 0
OBSERVABLE_STAGES = 30
SENSOR_TAP = 29
XOR_CELL = "XOR2_X0P5M_A9TR40"
DFF_CELL = "DFFRPQ_X0P5M_A9TR40"
Q_SETTLE_S = 2.0e-10
Q_READ_TIME_S = 3.3e-9
TOTAL_SCENARIO_LIMIT = 84

SCAN_FIELDS = (
    "phase", "vdd_v", "medium_code", "fine_code", "K", "scenario",
    "t_xor_rise_s", "t_xor_fall_s", "t_ck_rise_s", "q_final_v", "q_final",
    "D_code_ps", "W_xor_ps", "valid", "reason",
)


def sha256_file(path: Path) -> str:
    """Hash a read-only input without copying large PDK collateral."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    """Load one object contract and reject silently malformed evidence."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write deterministic task-owned evidence only under the requested path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Publish completed scan rows while preserving failed values as blanks."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=SCAN_FIELDS, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in SCAN_FIELDS})


def read_csv(path: Path, required: Sequence[str]) -> List[Dict[str, str]]:
    """Read nonempty retained evidence with its required schema intact."""

    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not set(required).issubset(reader.fieldnames):
            raise ValueError("required CSV schema is missing: {}".format(path))
        rows = list(reader)
    if not rows:
        raise ValueError("required CSV is empty: {}".format(path))
    return rows


def finite(value: Any) -> Optional[float]:
    """Keep HSPICE's failed measurements distinct from a physical zero."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def spice(value: float) -> str:
    """Format one scalar in HSPICE-safe scientific notation."""

    return "{:.12e}".format(float(value))


def vkey(value: float) -> str:
    """Keep voltage keys stable across JSON, CSV, and scenario identities."""

    return "{:.2f}".format(float(value))


def evidence_paths() -> Dict[str, Path]:
    """Name every historical file read by this task; none is an output target."""

    return {
        "ftc_config.json": FTC_ROOT / "ftc_config.json",
        "discovery/selected_cells.json": FTC_ROOT / "discovery/selected_cells.json",
        "reports/FTC_FINE_STAGE_VALIDATION_CONTRACT_AUDIT.md": FTC_ROOT / "reports/FTC_FINE_STAGE_VALIDATION_CONTRACT_AUDIT.md",
        "analysis/fine_stage_validation_contract_audit/summary.json": FTC_ROOT / "analysis/fine_stage_validation_contract_audit/summary.json",
        "analysis/fine_stage_validation_contract_audit/future_capture_contract.json": FTC_ROOT / "analysis/fine_stage_validation_contract_audit/future_capture_contract.json",
        "analysis/fine_stage_validation_contract_audit/two_cycle_waveforms.csv": FTC_ROOT / "analysis/fine_stage_validation_contract_audit/two_cycle_waveforms.csv",
        "scripts/run_fine_stage_validation_contract_audit.py": FTC_ROOT / "scripts/run_fine_stage_validation_contract_audit.py",
        "reports/FTC_PATH_SELECTION_MEDIUM_STAGE.md": FTC_ROOT / "reports/FTC_PATH_SELECTION_MEDIUM_STAGE.md",
        "analysis/path_selection_medium_stage/summary.json": FTC_ROOT / "analysis/path_selection_medium_stage/summary.json",
        "analysis/path_selection_medium_stage/cell_contract.json": FTC_ROOT / "analysis/path_selection_medium_stage/cell_contract.json",
        "analysis/path_selection_medium_stage/future_fine_stage_interface.json": FTC_ROOT / "analysis/path_selection_medium_stage/future_fine_stage_interface.json",
        "analysis/path_selection_medium_stage/medium_step_characterization.csv": FTC_ROOT / "analysis/path_selection_medium_stage/medium_step_characterization.csv",
        "scripts/run_path_selection_medium_stage.py": FTC_ROOT / "scripts/run_path_selection_medium_stage.py",
        "analysis/minimal_pulse_comparator/architecture.json": FTC_ROOT / "analysis/minimal_pulse_comparator/architecture.json",
        "analysis/minimal_pulse_comparator/summary.json": FTC_ROOT / "analysis/minimal_pulse_comparator/summary.json",
        "reports/FTC_MINIMAL_PROGRAMMABLE_THRESHOLD_PULSE_COMPARATOR.md": FTC_ROOT / "reports/FTC_MINIMAL_PROGRAMMABLE_THRESHOLD_PULSE_COMPARATOR.md",
        "scripts/run_minimal_pulse_comparator.py": FTC_ROOT / "scripts/run_minimal_pulse_comparator.py",
        "analysis/real_xor_pulse_width/fine.csv": FTC_ROOT / "analysis/real_xor_pulse_width/fine.csv",
        "scripts/run_real_xor_pulse_width.py": FTC_ROOT / "scripts/run_real_xor_pulse_width.py",
        "scripts/run_static_self_calibration.py": FTC_ROOT / "scripts/run_static_self_calibration.py",
        "analysis/standard_cell_load_size_sweep/fallback_1/selected_size_contract.json": FTC_ROOT / "analysis/standard_cell_load_size_sweep/fallback_1/selected_size_contract.json",
    }


def frozen_context() -> Dict[str, Any]:
    """Validate the immutable handoff before creating a new task artifact.

    The checks intentionally contain no discovery or selection logic.  A drift
    in any upstream decision is an architecture block, never authorization to
    substitute a different standard cell or historical experiment.
    """

    paths = evidence_paths()
    for path in paths.values():
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("required frozen evidence is missing: {}".format(path))
    config = load_json(paths["ftc_config.json"])
    cells = load_json(paths["discovery/selected_cells.json"])
    fine = load_json(paths["analysis/fine_stage_validation_contract_audit/summary.json"])
    capture = load_json(paths["analysis/fine_stage_validation_contract_audit/future_capture_contract.json"])
    medium = load_json(paths["analysis/path_selection_medium_stage/summary.json"])
    medium_cells = load_json(paths["analysis/path_selection_medium_stage/cell_contract.json"])
    dff_architecture = load_json(paths["analysis/minimal_pulse_comparator/architecture.json"])
    dff_summary = load_json(paths["analysis/minimal_pulse_comparator/summary.json"])
    load_contract = load_json(paths["analysis/standard_cell_load_size_sweep/fallback_1/selected_size_contract.json"])

    if fine.get("decision") != "Fine-Stage Delay-Line Waveform Contract = GO":
        raise ValueError("fine waveform decision is not GO")
    if (fine.get("selected_provisional_fine_driver"), fine.get("selected_provisional_fine_load"), fine.get("provisional_K")) != (FINE_DRIVER, FINE_LOAD, FINE_K):
        raise ValueError("frozen fine driver/load/K changed")
    if capture.get("fixed_absolute_sample_not_a_fine_stage_hard_gate") is not True:
        raise ValueError("fine waveform contract reintroduced absolute sample gating")
    if medium.get("decision") != "Path-Selection Medium Stage = GO":
        raise ValueError("medium-stage decision is not GO")
    if medium_cells.get("delay_cell", {}).get("cell") != MEDIUM_DELAY_CELL or medium_cells.get("selected_mux", {}).get("cell") != MEDIUM_MUX_CELL:
        raise ValueError("frozen medium cell contract changed")
    if dff_summary.get("decision") != "GO":
        raise ValueError("historical real-DFF comparator is not GO")
    sensor = dff_architecture.get("sensor", {})
    dff = dff_architecture.get("dff", {})
    if (sensor.get("tap_index"), sensor.get("initial_rvt_stages"), sensor.get("initial_lvt_stages"), sensor.get("observable_stages"), sensor.get("xor_cell")) != (SENSOR_TAP, SENSOR_RVT_INITIAL, SENSOR_LVT_INITIAL, OBSERVABLE_STAGES, XOR_CELL):
        raise ValueError("frozen sensor/XOR contract changed")
    if (dff.get("cell"), dff.get("minimum_q_settle_s")) != (DFF_CELL, Q_SETTLE_S):
        raise ValueError("frozen DFF contract changed")
    if tuple(cells.get("dff", {}).get("cdl_ports", ())) != ("Q", "VDD", "VNW", "VPW", "VSS", "CK", "D", "R"):
        raise ValueError("DFF CDL port order changed")
    if (cells.get("delay_lvt", {}).get("cell"), cells.get("delay_rvt", {}).get("cell"), cells.get("xor2", {}).get("cell"), cells.get("dff", {}).get("cell")) != (MEDIUM_DELAY_CELL, "BUF_X0P7M_A9TR40", XOR_CELL, DFF_CELL):
        raise ValueError("selected standard-cell contract changed")
    if (load_contract.get("candidate_id"), load_contract.get("cell"), load_contract.get("signal_pin"), load_contract.get("control_pin"), load_contract.get("high_cap_control_value"), load_contract.get("low_cap_control_value")) != (FINE_LOAD, FINE_LOAD_CELL, "A", "B", 0, 1):
        raise ValueError("frozen NOR load pin/control contract changed")
    if (config.get("temperature_c"), config.get("launch_time_s"), config.get("sampling_period_s"), config.get("tran_max_step_s")) != (25.0, 1.0e-9, 6.0e-9, 1.0e-12):
        raise ValueError("frozen stimulus contract changed")

    return {
        "config": config,
        "cells": cells,
        "load": {"cell": FINE_LOAD_CELL, "signal_pin": "A", "control_pin": "B"},
        "source_file_sha256": {name: sha256_file(path) for name, path in paths.items()},
    }


def requirements_document(context: Mapping[str, Any]) -> Dict[str, Any]:
    """Publish the plan's fixed electrical scope before any HSPICE preflight."""

    return {
        "schema_version": 1,
        "study": STUDY,
        "upstream_fine_waveform_decision": "GO",
        "upstream_commit": "818ad2786d79dad3c66db9bf27e182427be10a28",
        "medium_N": MEDIUM_N,
        "medium_delay_cell": MEDIUM_DELAY_CELL,
        "medium_mux_cell": MEDIUM_MUX_CELL,
        "fine_driver": FINE_DRIVER,
        "fine_load": FINE_LOAD,
        "initial_K": FINE_K,
        "sensor_tap": SENSOR_TAP,
        "sensor_initial_rvt_stages": SENSOR_RVT_INITIAL,
        "sensor_initial_lvt_stages": SENSOR_LVT_INITIAL,
        "xor_cell": XOR_CELL,
        "dff_cell": DFF_CELL,
        "minimum_q_settle_s": Q_SETTLE_S,
        "anchor_vdd_v": [1.10, 0.95, 0.80],
        "historical_hspice_rerun": 0,
        "load_rescan": "forbidden",
        "driver_rescan": "forbidden",
        "medium_redesign": "forbidden",
        "bypass": "future_work",
        "config_skip": "future_work",
        "programmable_margin": "future_work",
        "droop": "forbidden",
        "pvt": "forbidden",
        "rtl": "forbidden",
        "layout": "forbidden",
        "source_file_sha256": dict(context["source_file_sha256"]),
    }


def projected_q_read_contract(context: Mapping[str, Any]) -> Dict[str, Any]:
    """Derive the fixed 3.3 ns read time from retained, not newly simulated, data."""

    xor_rows = read_csv(FTC_ROOT / "analysis/real_xor_pulse_width/fine.csv", ("vdd_v", "t_xor29_rise_s", "valid"))
    delay_rows = read_csv(FTC_ROOT / "analysis/fine_stage_validation_contract_audit/two_cycle_waveforms.csv", ("vdd_v", "D_rise_ps", "valid"))
    projections: Dict[str, Dict[str, float]] = {}
    for voltage in (1.10, 0.95, 0.80):
        xor_matches = [row for row in xor_rows if round(float(row["vdd_v"]), 2) == voltage and str(row["valid"]).lower() in ("1", "true")]
        delay_matches = [row for row in delay_rows if round(float(row["vdd_v"]), 2) == voltage and str(row["valid"]).lower() in ("1", "true")]
        if len(xor_matches) != 1 or not delay_matches:
            raise ValueError("historical Q-read evidence is incomplete at {} V".format(voltage))
        xor_rise = finite(xor_matches[0]["t_xor29_rise_s"])
        delay_ps = max(finite(row["D_rise_ps"]) or float("-inf") for row in delay_matches)
        if xor_rise is None or not math.isfinite(delay_ps):
            raise ValueError("historical Q-read evidence is non-numeric at {} V".format(voltage))
        projected_ck = xor_rise + delay_ps * 1.0e-12
        projections[vkey(voltage)] = {
            "t_xor29_rise_s": xor_rise,
            "D_delay_max_s": delay_ps * 1.0e-12,
            "t_CK_projected_max_s": projected_ck,
            "minimum_safe_q_read_s": projected_ck + Q_SETTLE_S,
        }
    next_event = float(context["config"]["launch_time_s"]) + float(context["config"]["sampling_period_s"])
    if any(Q_READ_TIME_S < item["minimum_safe_q_read_s"] for item in projections.values()) or Q_READ_TIME_S >= next_event:
        raise ValueError("fixed Q read time has no safe settle window")
    return {
        "schema_version": 1,
        "q_read_time_s": Q_READ_TIME_S,
        "q_settle_s": Q_SETTLE_S,
        "next_sensor_xor_event_s": next_event,
        "input_period_s": float(context["config"]["sampling_period_s"]),
        "projections_by_vdd": projections,
    }


def buffer_instance(name: str, output: str, input_node: str, cell: str) -> str:
    """Render a BUF with the verified CDL order and same-rail well mapping."""

    return "{} {} vdd_a vdd_a vss_a vss_a {} {}".format(name, output, input_node, cell)


def mux_instance(name: str, output: str, shallow: str, deep: str, select: str) -> str:
    """Render the fixed non-inverting medium MUX (A for 0, B for 1)."""

    return "{} {} vdd_a vdd_a vss_a vss_a {} {} {} {}".format(name, output, shallow, deep, select, MEDIUM_MUX_CELL)


def thermometer(units: int, code: int) -> Tuple[int, ...]:
    """Return the first-code-high encoding used by both frozen delay stages."""

    if units < 0 or not 0 <= code <= units:
        raise ValueError("thermometer code outside legal range")
    return tuple(1 if index < code else 0 for index in range(units))


def sensor_xor_lines(cells: Mapping[str, Any]) -> List[str]:
    """Recreate the frozen 4-RVT/0-LVT sensor and all thirty XOR loads.

    Keeping the full XOR bank, rather than only tap29, preserves the exact
    sensor-side loading used in the historical real-XOR and DFF evidence.
    """

    lines = ["* Frozen four-stage RVT prefix."]
    rvt_input = "s_clk"
    for stage in range(SENSOR_RVT_INITIAL):
        output = "rvt_initial_{}".format(stage)
        lines.append(buffer_instance("XRVT_INIT_{:02d}".format(stage), output, rvt_input, cells["delay_rvt"]["cell"]))
        rvt_input = output
    lines.append("* Frozen 30-stage RVT observable path.")
    rvt_taps: List[str] = []
    for stage in range(OBSERVABLE_STAGES):
        output = "rvt_{}".format(stage)
        lines.append(buffer_instance("XRVT_{:02d}".format(stage), output, rvt_input, cells["delay_rvt"]["cell"]))
        rvt_taps.append(output)
        rvt_input = output
    lines.append("* Frozen zero-stage LVT prefix and 30-stage observable path.")
    lvt_input = "s_clk"
    lvt_taps: List[str] = []
    for stage in range(OBSERVABLE_STAGES):
        output = "lvt_{}".format(stage)
        lines.append(buffer_instance("XLVT_{:02d}".format(stage), output, lvt_input, cells["delay_lvt"]["cell"]))
        lvt_taps.append(output)
        lvt_input = output
    lines.append("* Full retained XOR observation bank; tap29 is the sole comparator input.")
    for stage, (rvt_tap, lvt_tap) in enumerate(zip(rvt_taps, lvt_taps)):
        lines.append("XXOR_{:02d} xor_{} vdd_a vdd_a vss_a vss_a {} {} {}".format(stage, stage, rvt_tap, lvt_tap, cells["xor2"]["cell"]))
    return lines


def medium_lines(medium_code: int) -> List[str]:
    """Render the fixed N=16 path-selection stage with ``xor_29`` as input."""

    if not 0 <= medium_code <= MEDIUM_N:
        raise ValueError("medium code outside legal 0..16")
    lines = ["* Frozen N=16 path-selection medium stage driven directly by xor_29."]
    for index, bit in enumerate(thermometer(MEDIUM_N, medium_code)):
        lines.append("V_M_{:02d} m_{} vss_a {}".format(index, index, "'VDD_VALUE'" if bit else "0"))
    for index in range(MEDIUM_N + 1):
        source = "xor_29" if index == 0 else "x{}".format(index)
        lines.append(buffer_instance("XMED_BUF_{:02d}".format(index), "x{}".format(index + 1), source, MEDIUM_DELAY_CELL))
    for index in range(MEDIUM_N):
        output = "medium_out" if index == 0 else "my{}".format(index)
        deep = "x{}".format(MEDIUM_N + 1) if index == MEDIUM_N - 1 else "my{}".format(index + 1)
        lines.append(mux_instance("XMED_MUX_{:02d}".format(index), output, "x{}".format(index + 1), deep, "m_{}".format(index)))
    return lines


def fine_lines(fine_code: int) -> List[str]:
    """Attach only the approved X0P8 driver and ten NOR input capacitances."""

    lines = ["* Approved fine driver and NOR2_X4A(A-signal/B-control) load bank."]
    lines.append(buffer_instance("XFINE_DRIVER", "dff_ck", "medium_out", FINE_DRIVER))
    for index, enabled in enumerate(thermometer(FINE_K, fine_code)):
        # NOR B=0 presents the selected high-capacitance state; B=1 is low load.
        control = 0 if enabled else 1
        lines.append("V_F_{:02d} f_{} vss_a {}".format(index, index, "'VDD_VALUE'" if control else "0"))
        lines.append("XLOAD_{:02d} z_{} vdd_a vdd_a vss_a vss_a dff_ck f_{} {}".format(index, index, index, FINE_LOAD_CELL))
    return lines


def render_deck(context: Mapping[str, Any], vdd_v: float, medium_code: int, fine_code: int) -> str:
    """Render one complete real-sensor, two-stage, real-DFF HSPICE scenario."""

    if vdd_v not in ANCHOR_VDD or not 0 <= fine_code <= FINE_K:
        raise ValueError("invalid fixed study scenario")
    config, cells = context["config"], context["cells"]
    launch, period, step = (float(config[key]) for key in ("launch_time_s", "sampling_period_s", "tran_max_step_s"))
    stop = launch + period - step
    includes = ['.include "{}"'.format(cells["source_files"]["rvt_cdl"])]
    if Path(cells["source_files"]["lvt_cdl"]).resolve() != Path(cells["source_files"]["rvt_cdl"]).resolve():
        includes.append('.include "{}"'.format(cells["source_files"]["lvt_cdl"]))
    lines = [
        "* FTC two-stage delay line plus real-DFF hierarchical calibration.",
        "* Scope is fixed to TT/25C, tap29, N16, X0P8, NOR2_X4A(A), K10.",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(float(config["temperature_c"]))),
        *includes,
        '.lib "{}" {}'.format(config["model_library"], config["corner"]),
        ".param VDD_VALUE={}".format(spice(vdd_v)),
        "V_VDD vdd_a vss_a 'VDD_VALUE'",
        "V_VSS vss_a 0 0",
        "V_SCLK s_clk vss_a PULSE(0 'VDD_VALUE' {} 1.000000000000e-12 1.000000000000e-12 {} {})".format(spice(launch), spice(period / 2.0), spice(period)),
        "* Historical active-high DFF clear is released before the 1 ns launch.",
        "V_DFF_RESET dff_reset vss_a PWL(0 'VDD_VALUE' 5.000000000000e-10 'VDD_VALUE' 5.100000000000e-10 0 {} 0)".format(spice(stop)),
        "",
        *sensor_xor_lines(cells),
        "",
        *medium_lines(medium_code),
        "",
        *fine_lines(fine_code),
        "",
        "* DFF CDL ports: Q VDD VNW VPW VSS CK D R.  D is undelayed xor_29.",
        "XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(DFF_CELL),
        "",
        ".tran {} {}".format(spice(step), spice(stop)),
        ".measure tran t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1",
        ".measure tran t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1",
        ".measure tran t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1",
        ".measure tran q_final_v FIND v(q_final,vss_a) AT={}".format(spice(Q_READ_TIME_S)),
        ".end",
        "",
    ]
    return "\n".join(lines)


def integration_contract(context: Mapping[str, Any]) -> Dict[str, Any]:
    """Statically prove the plan's topology before any licensed simulation."""

    deck = render_deck(context, 0.95, 0, 0)
    lines = deck.splitlines()
    forbidden_tokens = ("XMUX_L1", "XMUX_L2", "XMUX_L3", "XBYPASS", "XCONFIG_SKIP")
    checks = {
        # The observable RVT prefix also matches ``XRVT_INIT_`` textually, so
        # require the two-digit observable instance form rather than counting
        # every line beginning with ``XRVT_``.
        "sensor_matches_historical_real_xor": sum(line.startswith("XRVT_INIT_") for line in lines) == SENSOR_RVT_INITIAL and sum(bool(re.match(r"^XRVT_\d{2} ", line)) for line in lines) == OBSERVABLE_STAGES and sum(line.startswith("XLVT_") for line in lines) == OBSERVABLE_STAGES,
        "xor_cell_and_tap29_frozen": sum(line.startswith("XXOR_") for line in lines) == OBSERVABLE_STAGES and "XXOR_29 xor_29 vdd_a vdd_a vss_a vss_a rvt_29 lvt_29 {}".format(XOR_CELL) in lines,
        "xor29_drives_dff_data": "XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(DFF_CELL) in lines,
        "xor29_drives_medium_input": "XMED_BUF_00 x1 vdd_a vdd_a vss_a vss_a xor_29 {}".format(MEDIUM_DELAY_CELL) in lines,
        "dff_clock_only_from_two_stage_output": "XFINE_DRIVER dff_ck vdd_a vdd_a vss_a vss_a medium_out {}".format(FINE_DRIVER) in lines,
        "frozen_n16_medium": sum(line.startswith("XMED_BUF_") for line in lines) == MEDIUM_N + 1 and sum(line.startswith("XMED_MUX_") for line in lines) == MEDIUM_N,
        "only_approved_fine_driver": sum(line.startswith("XFINE_DRIVER") for line in lines) == 1 and FINE_DRIVER in deck,
        "only_approved_nor_load": sum(line.startswith("XLOAD_") for line in lines) == FINE_K and all(" dff_ck f_" in line and line.endswith(FINE_LOAD_CELL) for line in lines if line.startswith("XLOAD_")),
        "initial_K_is_ten": sum(line.startswith("XLOAD_") for line in lines) == FINE_K,
        "no_historical_three_bit_threshold_tree": not any(token in deck for token in ("XMUX_L1", "XMUX_L2", "XMUX_L3")),
        "no_bypass": "XBYPASS" not in deck,
        "no_config_skip": "XCONFIG_SKIP" not in deck,
        "no_ideal_delay": not re.search(r"(?im)^\s*[evg]\S*.*\btd\s*=", deck),
        "no_ideal_capacitor": not any(line.lstrip().lower().startswith("c") for line in lines),
    }
    return {
        "schema_version": 1,
        "study": STUDY,
        "static_vdd_v": 0.95,
        "static_medium_code": 0,
        "static_fine_code": 0,
        "deck_sha256": hashlib.sha256(deck.encode("ascii")).hexdigest(),
        "checks": checks,
        "decision": "GO" if all(checks.values()) else "ARCHITECTURE_BLOCKED",
    }


def scenario_parameters(phase: str, vdd_v: float, medium_code: int, fine_code: int, context: Mapping[str, Any]) -> Dict[str, Any]:
    """Capture every physical setting required to safely reuse a scenario."""

    return {
        "study": STUDY,
        "phase": phase,
        "vdd_v": float(vdd_v),
        "medium_code": int(medium_code),
        "fine_code": int(fine_code),
        "medium_N": MEDIUM_N,
        "medium_delay_cell": MEDIUM_DELAY_CELL,
        "medium_mux_cell": MEDIUM_MUX_CELL,
        "fine_driver_cell": FINE_DRIVER,
        "fine_load_cell": FINE_LOAD_CELL,
        "fine_load_signal_pin": "A",
        "fine_load_control_pin": "B",
        "fine_K": FINE_K,
        "sensor_tap": SENSOR_TAP,
        "sensor_rvt_initial_stages": SENSOR_RVT_INITIAL,
        "sensor_lvt_initial_stages": SENSOR_LVT_INITIAL,
        "xor_cell": XOR_CELL,
        "dff_cell": DFF_CELL,
        "q_read_time_s": Q_READ_TIME_S,
        "q_settle_s": Q_SETTLE_S,
        "input_period_s": float(context["config"]["sampling_period_s"]),
    }


def scenario_id(parameters: Mapping[str, Any]) -> str:
    """Produce a readable, collision-resistant identity for one new topology."""

    encoded = json.dumps(dict(parameters), sort_keys=True, separators=(",", ":")).encode("ascii")
    digest = hashlib.sha256(encoded).hexdigest()[:20]
    return "{}__m{:02d}__f{:02d}__v{}__{}".format(parameters["phase"], parameters["medium_code"], parameters["fine_code"], vkey(parameters["vdd_v"]).replace(".", "p"), digest)


def run_signature(requirements: Path, integration: Path, q_read: Path) -> Dict[str, str]:
    """Bind raw evidence to the exact runner and static contracts that produced it."""

    return {
        "runner_sha256": sha256_file(Path(__file__)),
        "requirements_sha256": sha256_file(requirements),
        "integration_contract_sha256": sha256_file(integration),
        "q_read_contract_sha256": sha256_file(q_read),
    }


def validated_reuse(path: Path, parameters: Mapping[str, Any], deck_text: str) -> Optional[Dict[str, Any]]:
    """Reuse only a PASS deck with matching physical identity and raw evidence.

    The runner hash is intentionally not a reuse predicate: a parser/comment
    correction must not rerun an already completed electrical scenario.  The
    freshly rendered deck SHA and complete HSPICE listing/MEAS instead prove
    that the retained transistor-level experiment is precisely the same one.
    """

    try:
        manifest = load_json(path / "scenario_manifest.json")
        deck = path / "two_stage_real_dff.sp"
        expected_sha = hashlib.sha256(deck_text.encode("ascii")).hexdigest()
        if manifest.get("completion_status") != "PASS" or manifest.get("parameters") != dict(parameters) or manifest.get("netlist_sha256") != expected_sha or sha256_file(deck) != expected_sha:
            return None
        run_dc_sweep.validate_listing(path / "two_stage_real_dff.lis")
        measurement = run_dc_sweep.find_measurement_file(path, "two_stage_real_dff")
        if measurement.name != manifest.get("measurement_file"):
            return None
        return {"scenario": str(path), **run_dc_sweep.parse_measurements(measurement)}
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError):
        return None


def find_retained_scenario(run_root: Path, identity: str) -> Optional[Path]:
    """Find a prior task scenario globally so an interrupted case is never rerun."""

    matches = [path for path in run_root.glob("r*/scenarios/{}".format(identity)) if path.is_dir()]
    if len(matches) > 1:
        raise RuntimeError("duplicate task scenario identity: {}".format(identity))
    return matches[0] if matches else None


def allocate_run_dir(run_root: Path, signature: Mapping[str, str], hspice: Path, version: str) -> Path:
    """Create one new revision only when a previously unseen scenario must run."""

    run_root.mkdir(parents=True, exist_ok=True)
    indices = [int(path.name[1:]) for path in run_root.glob("r*") if path.is_dir() and re.fullmatch(r"r\d+", path.name)]
    run_dir = run_root / "r{}".format(max(indices, default=0) + 1)
    run_dir.mkdir()
    write_json(run_dir / "run_manifest.json", {"schema_version": 1, "study": STUDY, "signature": dict(signature), "system_hspice": str(hspice), "hspice_version": version})
    return run_dir


def validate_hspice(context: Mapping[str, Any]) -> Tuple[Path, str]:
    """Preflight the configured local simulator and all fixed source collateral."""

    config, cells = context["config"], context["cells"]
    hspice = run_dc_sweep.require_regular_file(Path(config["hspice"]), "configured HSPICE", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if str(config["expected_hspice_version"]) not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    for path in (cells["source_files"]["rvt_cdl"], cells["source_files"]["lvt_cdl"], config["model_library"], FTC_ROOT / "spice" / "empty_subckt.sp_cal"):
        run_dc_sweep.require_regular_file(Path(path), "fixed FTC collateral")
    return hspice, version


def execute_scenario(hspice: Path, version: str, run_root: Path, run_dir: Optional[Path], deck: str, parameters: Mapping[str, Any], signature: Mapping[str, str], stats: Dict[str, int]) -> Tuple[Dict[str, Any], Optional[Path]]:
    """Run one new scenario once, or return only fully validated retained evidence.

    A failed or partial retained directory intentionally blocks a retry.  This
    preserves the plan's one-run-per-scenario rule and keeps failure evidence
    auditable instead of hiding it behind a fresh invocation.
    """

    identity = scenario_id(parameters)
    retained_path = find_retained_scenario(run_root, identity)
    if retained_path is not None:
        retained = validated_reuse(retained_path, parameters, deck)
        if retained is None:
            raise RuntimeError("retained scenario is not safely reusable: {}".format(retained_path))
        stats["reused"] += 1
        return retained, run_dir
    if run_dir is None:
        run_dir = allocate_run_dir(run_root, signature, hspice, version)
    scenario = run_dir / "scenarios" / identity
    scenario.mkdir(parents=True)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", scenario / "empty_subckt.sp_cal")
    deck_path = scenario / "two_stage_real_dff.sp"
    deck_path.write_text(deck, encoding="ascii")
    manifest: Dict[str, Any] = {"schema_version": 1, "parameters": dict(parameters), "netlist_sha256": sha256_file(deck_path), "completion_status": "RUNNING", "measurement_file": None, **dict(signature)}
    write_json(scenario / "scenario_manifest.json", manifest)
    stats["new"] += 1
    try:
        result = subprocess.run([str(hspice), deck_path.name, "-o", "two_stage_real_dff"], cwd=str(scenario), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=300)
        (scenario / "hspice_command.log").write_text("command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(" ".join([str(hspice), deck_path.name, "-o", "two_stage_real_dff"]), result.returncode, result.stdout, result.stderr), encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError("HSPICE returned {}".format(result.returncode))
        run_dc_sweep.validate_listing(scenario / "two_stage_real_dff.lis")
        measurement = run_dc_sweep.find_measurement_file(scenario, "two_stage_real_dff")
        values = run_dc_sweep.parse_measurements(measurement)
        manifest.update({"completion_status": "PASS", "measurement_file": measurement.name})
        write_json(scenario / "scenario_manifest.json", manifest)
        return {"scenario": str(scenario), **values}, run_dir
    except Exception as error:
        manifest.update({"completion_status": "FAIL", "failure": str(error)})
        write_json(scenario / "scenario_manifest.json", manifest)
        raise


def row_from_record(phase: str, vdd_v: float, medium_code: int, fine_code: int, record: Mapping[str, Any], run_root: Path) -> Dict[str, Any]:
    """Convert raw measures into one classification-ready, no-inferred-data row."""

    scenario = Path(str(record["scenario"])).relative_to(run_root)
    row: Dict[str, Any] = {field: None for field in SCAN_FIELDS}
    row.update({"phase": phase, "vdd_v": vdd_v, "medium_code": medium_code, "fine_code": fine_code, "K": FINE_K, "scenario": str(scenario), "valid": 0})
    # HSPICE measurement labels are the deck labels without the CSV ``_s``
    # convention used by task-owned analysis rows.  Preserve that distinction
    # here rather than changing the physical deck or inventing a value.
    for row_field, measure_field in (("t_xor_rise_s", "t_xor_rise"), ("t_xor_fall_s", "t_xor_fall"), ("t_ck_rise_s", "t_ck_rise"), ("q_final_v", "q_final_v")):
        row[row_field] = finite(record.get(measure_field))
    if row["q_final_v"] is None:
        row["reason"] = "q_ambiguous"
        return row
    if row["t_xor_rise_s"] is None or row["t_xor_fall_s"] is None:
        row["reason"] = "xor_pulse_invalid"
        return row
    if row["t_ck_rise_s"] is None:
        row["reason"] = "dff_capture_invalid"
        return row
    width = row["t_xor_fall_s"] - row["t_xor_rise_s"]
    delay = row["t_ck_rise_s"] - row["t_xor_rise_s"]
    row.update({"W_xor_ps": width * 1.0e12, "D_code_ps": delay * 1.0e12})
    if width <= 0.0:
        row["reason"] = "xor_pulse_invalid"
    elif delay <= 0.0:
        row["reason"] = "dff_capture_invalid"
    elif row["t_ck_rise_s"] > Q_READ_TIME_S - Q_SETTLE_S:
        row["reason"] = "q_settle_window_insufficient"
    else:
        row["q_final"] = 1 if row["q_final_v"] >= vdd_v / 2.0 else 0
        row["valid"] = 1
    return row


def evaluate_scan(rows: Sequence[Mapping[str, Any]], phase: str) -> Dict[str, Any]:
    """Apply the exact one-dimensional coarse or fine search gate without repair."""

    expected_codes = list(range(MEDIUM_N + 1 if phase == "coarse" else FINE_K + 1))
    code_field = "medium_code" if phase == "coarse" else "fine_code"
    ordered = sorted(rows, key=lambda row: int(row[code_field]))
    if [int(row[code_field]) for row in ordered] != expected_codes:
        return {"status": "NO-GO", "reason": "hspice_execution_failure"}
    invalid = next((row for row in ordered if int(row.get("valid", 0)) != 1), None)
    if invalid is not None:
        return {"status": "NO-GO", "reason": str(invalid.get("reason") or "hspice_execution_failure")}
    delays = [float(row["D_code_ps"]) for row in ordered]
    if not all(right > left for left, right in zip(delays, delays[1:])):
        return {"status": "NO-GO", "reason": "{}_delay_non_monotonic".format(phase)}
    q_values = [int(row["q_final"]) for row in ordered]
    if q_values[0] == 0:
        return {"status": "NO-GO", "reason": "coarse_range_too_long_at_M0" if phase == "coarse" else "fine_entry_already_late"}
    if q_values[-1] == 1:
        return {"status": "NO-GO", "reason": "coarse_range_too_short_at_M16" if phase == "coarse" else "fine_range_insufficient_after_dff_load"}
    transitions = [index for index, pair in enumerate(zip(q_values, q_values[1:])) if pair == (1, 0)]
    if len(transitions) != 1 or any(pair == (0, 1) for pair in zip(q_values, q_values[1:])):
        return {"status": "NO-GO", "reason": "{}_q_non_monotonic".format(phase)}
    transition = transitions[0] + 1
    return {"status": "GO", "transition": transition, "q_sequence": q_values, "delays_ps": delays}


def run_one(context: Mapping[str, Any], hspice: Path, version: str, run_root: Path, run_dir: Optional[Path], phase: str, vdd_v: float, medium_code: int, fine_code: int, signature: Mapping[str, str], stats: Dict[str, int]) -> Tuple[Dict[str, Any], Optional[Path]]:
    """Run one new electrical point and convert it immediately for early stopping."""

    parameters = scenario_parameters(phase, vdd_v, medium_code, fine_code, context)
    record, run_dir = execute_scenario(hspice, version, run_root, run_dir, render_deck(context, vdd_v, medium_code, fine_code), parameters, signature, stats)
    return row_from_record(phase, vdd_v, medium_code, fine_code, record, run_root), run_dir


def run_voltage(context: Mapping[str, Any], hspice: Path, version: str, run_root: Path, run_dir: Optional[Path], vdd_v: float, signature: Mapping[str, str], stats: Dict[str, int]) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], Optional[Path]]:
    """Run the mandatory coarse-then-fine flow for one voltage, stopping on failure."""

    coarse: List[Dict[str, Any]] = []
    fine: List[Dict[str, Any]] = []
    try:
        for medium_code in range(MEDIUM_N + 1):
            row, run_dir = run_one(context, hspice, version, run_root, run_dir, "coarse", vdd_v, medium_code, 0, signature, stats)
            coarse.append(row)
            if not row["valid"]:
                return {"vdd_v": vdd_v, "status": "NO-GO", "reason": row["reason"], "fine_status": "NOT_RUN"}, coarse, fine, run_dir
    except Exception as error:
        return {"vdd_v": vdd_v, "status": "NO-GO", "reason": "hspice_execution_failure", "detail": str(error), "fine_status": "NOT_RUN"}, coarse, fine, run_dir
    coarse_result = evaluate_scan(coarse, "coarse")
    if coarse_result["status"] != "GO":
        return {"vdd_v": vdd_v, "status": "NO-GO", "reason": coarse_result["reason"], "coarse": coarse_result, "fine_status": "NOT_RUN"}, coarse, fine, run_dir
    medium_fine = int(coarse_result["transition"]) - 1
    try:
        for fine_code in range(FINE_K + 1):
            row, run_dir = run_one(context, hspice, version, run_root, run_dir, "fine", vdd_v, medium_fine, fine_code, signature, stats)
            fine.append(row)
            if not row["valid"]:
                return {"vdd_v": vdd_v, "status": "NO-GO", "reason": row["reason"], "coarse": coarse_result}, coarse, fine, run_dir
    except Exception as error:
        return {"vdd_v": vdd_v, "status": "NO-GO", "reason": "hspice_execution_failure", "detail": str(error), "coarse": coarse_result}, coarse, fine, run_dir
    fine_result = evaluate_scan(fine, "fine")
    if fine_result["status"] != "GO":
        return {"vdd_v": vdd_v, "status": "NO-GO", "reason": fine_result["reason"], "coarse": coarse_result, "fine": fine_result}, coarse, fine, run_dir
    lock = fine[int(fine_result["transition"])]
    return {
        "vdd_v": vdd_v,
        "status": "GO",
        "M_transition": coarse_result["transition"],
        "M_fine": medium_fine,
        "F_lock": fine_result["transition"],
        "D_lock_ps": lock["D_code_ps"],
        "W_xor_ps": lock["W_xor_ps"],
        "D_minus_W_ps": lock["D_code_ps"] - lock["W_xor_ps"],
        "q_read_time_s": Q_READ_TIME_S,
        "coarse": coarse_result,
        "fine": fine_result,
    }, coarse, fine, run_dir


def summary_document(decision: str, reasons: Sequence[str], voltage_results: Sequence[Mapping[str, Any]], stats: Mapping[str, int], run_root: Path) -> Dict[str, Any]:
    """Keep terminal status, early-stop state, and historical boundaries together."""

    # ``stats["new"]`` is invocation-local.  Count retained task manifests for
    # the published total so a safely reused interrupted scenario is not
    # accidentally omitted from the electrical-scenario budget.
    task_scenarios = list(run_root.glob("r*/scenarios/*/scenario_manifest.json")) if run_root.is_dir() else []
    return {
        "schema_version": 1,
        "study": STUDY,
        "decision": decision,
        "reasons": list(dict.fromkeys(reasons)),
        "per_voltage": list(voltage_results),
        "new_hspice_scenarios": len(task_scenarios),
        "reused_new_task_scenarios": int(stats["reused"]),
        "run_root": str(run_root),
        "historical_hspice_rerun": 0,
        "historical_medium_rerun": 0,
        "historical_driver_codesign_rerun": 0,
        "historical_validation_audit_rerun": 0,
        "historical_static_calibration_rerun": 0,
        "historical_xor_rerun": 0,
    }


def render_report(path: Path, requirements: Mapping[str, Any], integration: Mapping[str, Any], q_contract: Mapping[str, Any], summary: Mapping[str, Any]) -> None:
    """Write one compact report that remains informative after an early stop."""

    lines = [
        "# FTC Two-Stage Real-DFF Hierarchical Calibration",
        "",
        "## Decision",
        "",
        "**{}**".format(summary["decision"]),
        "",
        "## Frozen Inputs",
        "",
        "- Historical fine waveform, path-selection medium, real-XOR, minimal real-DFF, and static-calibration evidence was read only; none of their HSPICE campaigns was rerun.",
        "- Driver/load/K: `{}` / `{}` / `{}`; medium: N={} `{}` / `{}`.".format(requirements["fine_driver"], requirements["fine_load"], requirements["initial_K"], requirements["medium_N"], requirements["medium_delay_cell"], requirements["medium_mux_cell"]),
        "- Static integration is `{}`: tap29/XOR/DFF and the approved medium/fine cells are retained without threshold tree, bypass, config-skip, ideal delay, or ideal capacitor.".format(integration["decision"]),
        "- All historical rerun counters are zero.",
        "",
        "## Q Read Contract",
        "",
        "- `q_read_time_s = {}` and `q_settle_s = {}`; the next sensor/XOR event is at {} s.".format(q_contract["q_read_time_s"], q_contract["q_settle_s"], q_contract["next_sensor_xor_event_s"]),
        "- 3 ns was not reused because the retained 0.80 V projection needs {} s before the settled Q read.".format(q_contract["projections_by_vdd"]["0.80"]["minimum_safe_q_read_s"]),
        "",
        "## Per-Voltage Result",
        "",
        "| VDD (V) | Status | Coarse Q | M transition | Fine Q | F lock |",
        "|---:|---|---|---:|---|---:|",
    ]
    by_voltage = {vkey(float(item["vdd_v"])): item for item in summary["per_voltage"]}
    for voltage in (0.95, 1.10, 0.80):
        item = by_voltage.get(vkey(voltage), {"status": "NOT_RUN"})
        coarse_q = "".join(str(value) for value in item.get("coarse", {}).get("q_sequence", ()))
        fine_q = "".join(str(value) for value in item.get("fine", {}).get("q_sequence", ()))
        lines.append("| {:.2f} | {} | {} | {} (M fine {}) | {} | {} |".format(voltage, item.get("status", "NOT_RUN"), coarse_q, item.get("M_transition", ""), item.get("M_fine", ""), fine_q, item.get("F_lock", "")))
    if summary["decision"].endswith("= GO"):
        lines.extend([
            "",
            "All coarse and fine `D_code_ps` sequences are strictly increasing, each Q sequence has exactly one `1→0`, every CK satisfies the 200 ps settle rule, every `W_xor_ps` is positive, and no Q is ambiguous.",
            "K=10 remains sufficient because the three `F_lock` values are within 1..10. `D_minus_W_ps` is analysis-only and does not replace the real DFF Q decision.",
        ])
    lines.extend([
        "",
        "## Accounting and Scope",
        "",
        "- New integrated HSPICE scenarios: {}; reused new-task scenarios in this publication: {}.".format(summary["new_hspice_scenarios"], summary["reused_new_task_scenarios"]),
        "- This is not a complete FTC droop macro GO: bypass, configuration skip, programmable margin, droop detection, PVT, RTL, and layout remain outside this task.",
    ])
    if summary["reasons"]:
        lines.extend(["", "## NO-GO Reasons", ""] + ["- {}".format(reason) for reason in summary["reasons"]])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Expose only output locations and a zero-HSPICE static-audit mode."""

    parser = argparse.ArgumentParser(description="run FTC two-stage real-DFF hierarchical calibration")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis" / "two_stage_real_dff_hierarchical_calibration")
    parser.add_argument("--run-root", type=Path, default=FTC_ROOT / "runs" / "two_stage_real_dff_hierarchical_calibration")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports" / "FTC_TWO_STAGE_REAL_DFF_HIERARCHICAL_CALIBRATION.md")
    parser.add_argument("--phase0-only", action="store_true", help="publish frozen/static contracts without HSPICE")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Execute the fixed early-stop schedule, never an exploratory sweep."""

    args = parse_args(argv)
    context = frozen_context()
    analysis = args.analysis_dir.resolve()
    run_root = args.run_root.resolve()
    report = args.report_output.resolve()
    requirements_path = analysis / "requirements.json"
    integration_path = analysis / "integration_contract.json"
    q_read_path = analysis / "q_read_contract.json"
    requirements = requirements_document(context)
    contract = integration_contract(context)
    q_contract = projected_q_read_contract(context)
    write_json(requirements_path, requirements)
    write_json(integration_path, contract)
    write_json(q_read_path, q_contract)
    stats = {"new": 0, "reused": 0}
    if contract["decision"] != "GO":
        summary = summary_document("Two-Stage Real-DFF Integration = ARCHITECTURE_BLOCKED", ["static_integration_contract_failed"], [], stats, run_root)
        write_json(analysis / "summary.json", summary)
        render_report(report, requirements, contract, q_contract, summary)
        return 2
    if args.phase0_only:
        summary = summary_document("NOT_RUN", [], [], stats, run_root)
        write_json(analysis / "summary.json", summary)
        render_report(report, requirements, contract, q_contract, summary)
        return 0

    try:
        hspice, version = validate_hspice(context)
    except Exception as error:
        summary = summary_document("Two-Stage Real-DFF Hierarchical Self-Calibration = NO-GO", ["hspice_execution_failure: {}".format(error)], [], stats, run_root)
        write_json(analysis / "summary.json", summary)
        render_report(report, requirements, contract, q_contract, summary)
        return 2
    signature = run_signature(requirements_path, integration_path, q_read_path)
    run_dir: Optional[Path] = None
    coarse_rows: List[Dict[str, Any]] = []
    fine_rows: List[Dict[str, Any]] = []
    voltage_results: List[Dict[str, Any]] = []
    for voltage in ANCHOR_VDD:
        result, coarse, fine, run_dir = run_voltage(context, hspice, version, run_root, run_dir, voltage, signature, stats)
        coarse_rows.extend(coarse)
        fine_rows.extend(fine)
        voltage_results.append(result)
        if result["status"] != "GO":
            break
    if coarse_rows:
        write_csv(analysis / "coarse_scan.csv", coarse_rows)
    if fine_rows:
        write_csv(analysis / "fine_scan.csv", fine_rows)
    complete = len(voltage_results) == len(ANCHOR_VDD) and all(item["status"] == "GO" for item in voltage_results)
    decision = "Two-Stage Real-DFF Hierarchical Self-Calibration = GO" if complete else "Two-Stage Real-DFF Hierarchical Self-Calibration = NO-GO"
    reasons = [] if complete else [str(voltage_results[-1].get("reason", "not_run"))] if voltage_results else ["hspice_execution_failure"]
    summary = summary_document(decision, reasons, voltage_results, stats, run_root)
    if complete:
        write_json(analysis / "lock_table.json", {"schema_version": 1, "study": STUDY, "locks": voltage_results})
    write_json(analysis / "summary.json", summary)
    render_report(report, requirements, contract, q_contract, summary)
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
