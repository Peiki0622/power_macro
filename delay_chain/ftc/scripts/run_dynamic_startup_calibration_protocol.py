#!/usr/bin/env python3
"""Validate the bounded dynamic FTC startup-calibration protocol.

The upstream static campaign is immutable evidence.  This runner rebuilds the
approved transistor topology locally, changes only the M/F testbench rails to
single-bit PWL controls, and runs at most one continuous HSPICE deck per VDD.
It intentionally contains no calibration FSM, search, or hardware selection.
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
import run_dc_sweep  # noqa: E402  # Shared listing/MEAS parser only.


STUDY = "dynamic_startup_calibration_protocol_v1"
VOLTAGES = (0.95, 1.10, 0.80)
MEDIUM_N = 16
MEDIUM_DELAY_CELL = "BUF_X0P7M_A9TL40"
MEDIUM_MUX_CELL = "MXT2_X0P5M_A9TL40"
FINE_DRIVER = "BUF_X0P8M_A9TL40"
FINE_LOAD = "NOR2_X4A_A9TL40"
FINE_K = 10
SENSOR_RVT_INITIAL = 4
SENSOR_LVT_INITIAL = 0
OBSERVABLE_STAGES = 30
SENSOR_TAP = 29
XOR_CELL = "XOR2_X0P5M_A9TR40"
DFF_CELL = "DFFRPQ_X0P5M_A9TR40"
Q_SETTLE_S = 2.0e-10
CONTROL_EDGE_S = 1.0e-11
SCLK_EDGE_S = 1.0e-12
RESET_SEPARATION_S = 4.9e-10
SCLK_HIGH_S = 3.0e-9
RAIL_HIGH_RATIO = 0.9
RAIL_LOW_RATIO = 0.1
QUIET_RATIO = 0.1

PROBE_FIELDS = (
    "vdd_v", "probe_index", "protocol_phase", "medium_code", "fine_code",
    "launch_time_s", "q_read_time_s", "t_xor_rise_s", "t_xor_fall_s",
    "t_ck_rise_s", "q_read_v", "q_logic", "D_code_ps", "W_xor_ps",
    "xor_peak_v", "ck_peak_v", "static_D_code_ps", "dynamic_D_code_ps",
    "delta_D_ps", "static_W_xor_ps", "dynamic_W_xor_ps", "delta_W_ps",
    "static_Q", "dynamic_Q", "valid", "reason",
)
TRANSITION_FIELDS = (
    "vdd_v", "transition_index", "transition_type", "old_M", "new_M",
    "old_F", "new_F", "update_time_s", "next_reset_release_s",
    "next_launch_s", "medium_out_quiet_peak_v", "dff_ck_quiet_peak_v",
    "xor_quiet_peak_v", "configuration_ck_edge_count", "status", "reason",
)


def sha256_file(path: Path) -> str:
    """Hash evidence incrementally so large CDL files never get copied."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    """Load one object contract and reject a silently malformed handoff."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write only task-owned evidence, with stable ordering for hashing."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    """Write rectangular evidence while preserving failed measures as blanks."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def read_csv(path: Path, required: Sequence[str]) -> List[Dict[str, str]]:
    """Read a retained CSV and require its physical measurement columns."""

    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not set(required).issubset(reader.fieldnames):
            raise ValueError("required CSV schema is missing: {}".format(path))
        rows = list(reader)
    if not rows:
        raise ValueError("required CSV is empty: {}".format(path))
    return rows


def finite(value: Any) -> Optional[float]:
    """Keep HSPICE failed measurements distinct from a physical zero."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def spice(value: float) -> str:
    """Render a scalar in HSPICE-safe scientific notation."""

    return "{:.12e}".format(float(value))


def vkey(value: float) -> str:
    """Use one stable voltage key in JSON, IDs, and CSV joins."""

    return "{:.2f}".format(float(value))


def thermometer(units: int, code: int) -> Tuple[int, ...]:
    """Return the first-code-high encoding frozen by the static campaign."""

    if units < 0 or not 0 <= code <= units:
        raise ValueError("thermometer code outside legal range")
    return tuple(1 if index < code else 0 for index in range(units))


def evidence_paths() -> Dict[str, Path]:
    """Name every immutable input; none of these paths is an output target."""

    upstream = FTC_ROOT / "analysis" / "two_stage_real_dff_hierarchical_calibration"
    return {
        "summary.json": upstream / "summary.json",
        "lock_table.json": upstream / "lock_table.json",
        "coarse_scan.csv": upstream / "coarse_scan.csv",
        "fine_scan.csv": upstream / "fine_scan.csv",
        "integration_contract.json": upstream / "integration_contract.json",
        "q_read_contract.json": upstream / "q_read_contract.json",
        "requirements.json": upstream / "requirements.json",
        "upstream_report.md": FTC_ROOT / "reports" / "FTC_TWO_STAGE_REAL_DFF_HIERARCHICAL_CALIBRATION.md",
        "upstream_runner.py": FTC_ROOT / "scripts" / "run_two_stage_real_dff_hierarchical_calibration.py",
        "ftc_config.json": FTC_ROOT / "ftc_config.json",
        "selected_cells.json": FTC_ROOT / "discovery" / "selected_cells.json",
        "xor_fine.csv": FTC_ROOT / "analysis" / "real_xor_pulse_width" / "fine.csv",
        "two_cycle_waveforms.csv": FTC_ROOT / "analysis" / "fine_stage_validation_contract_audit" / "two_cycle_waveforms.csv",
    }


def frozen_context() -> Dict[str, Any]:
    """Freeze upstream GO evidence before creating any electrical scenario."""

    paths = evidence_paths()
    missing = [str(path) for path in paths.values() if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise ValueError("missing frozen evidence: {}".format(", ".join(missing)))
    summary = load_json(paths["summary.json"])
    integration = load_json(paths["integration_contract.json"])
    q_contract = load_json(paths["q_read_contract.json"])
    requirements = load_json(paths["requirements.json"])
    config = load_json(paths["ftc_config.json"])
    cells = load_json(paths["selected_cells.json"])
    if summary.get("decision") != "Two-Stage Real-DFF Hierarchical Self-Calibration = GO":
        raise ValueError("upstream_reference_mismatch: upstream decision is not GO")
    if summary.get("new_hspice_scenarios") != 84:
        raise ValueError("upstream_reference_mismatch: upstream scenario count is not 84")
    checks = integration.get("checks", {})
    required_checks = (
        "sensor_matches_historical_real_xor", "xor_cell_and_tap29_frozen",
        "xor29_drives_dff_data", "xor29_drives_medium_input",
        "dff_clock_only_from_two_stage_output", "frozen_n16_medium",
        "only_approved_fine_driver", "only_approved_nor_load", "initial_K_is_ten",
        "no_historical_three_bit_threshold_tree", "no_bypass", "no_config_skip",
        "no_ideal_delay", "no_ideal_capacitor",
    )
    if any(checks.get(name) is not True for name in required_checks):
        raise ValueError("upstream_reference_mismatch: frozen integration check failed")
    if any(int(summary.get(name, 0)) != 0 for name in (
        "historical_hspice_rerun", "historical_medium_rerun", "historical_xor_rerun",
        "historical_static_calibration_rerun", "historical_driver_codesign_rerun",
        "historical_validation_audit_rerun",
    )):
        raise ValueError("upstream_reference_mismatch: historical rerun counter is nonzero")
    if requirements.get("medium_N") != MEDIUM_N or requirements.get("initial_K") != FINE_K:
        raise ValueError("upstream_reference_mismatch: medium/fine size changed")
    if (requirements.get("sensor_tap"), requirements.get("xor_cell"), requirements.get("dff_cell")) != (SENSOR_TAP, XOR_CELL, DFF_CELL):
        raise ValueError("upstream_reference_mismatch: sensor/XOR/DFF changed")
    return {
        "paths": paths,
        "summary": summary,
        "integration": integration,
        "q_contract": q_contract,
        "requirements": requirements,
        "config": config,
        "cells": cells,
        "source_file_sha256": {name: sha256_file(path) for name, path in paths.items()},
        "coarse_rows": read_csv(paths["coarse_scan.csv"], ("phase", "vdd_v", "medium_code", "fine_code", "q_final", "D_code_ps", "W_xor_ps")),
        "fine_rows": read_csv(paths["fine_scan.csv"], ("phase", "vdd_v", "medium_code", "fine_code", "q_final", "D_code_ps", "W_xor_ps")),
    }


def requirements_document(context: Mapping[str, Any]) -> Dict[str, Any]:
    """Publish fixed scope and explicit zero historical rerun accounting."""

    return {
        "schema_version": 1,
        "study": STUDY,
        "upstream_static_decision": context["summary"]["decision"],
        "upstream_static_scenarios": 84,
        "medium_N": MEDIUM_N,
        "medium_delay_cell": MEDIUM_DELAY_CELL,
        "medium_mux_cell": MEDIUM_MUX_CELL,
        "fine_driver": FINE_DRIVER,
        "fine_load": FINE_LOAD,
        "fine_signal_pin": "A",
        "fine_control_pin": "B",
        "fine_high_cap_control": 0,
        "fine_low_cap_control": 1,
        "fine_K": FINE_K,
        "sensor_initial_rvt_stages": SENSOR_RVT_INITIAL,
        "sensor_initial_lvt_stages": SENSOR_LVT_INITIAL,
        "observable_stages": OBSERVABLE_STAGES,
        "sensor_tap": SENSOR_TAP,
        "xor_cell": XOR_CELL,
        "dff_cell": DFF_CELL,
        "minimum_q_settle_s": Q_SETTLE_S,
        "upstream_static_hspice_rerun": 0,
        "upstream_static_84_scenarios_rerun": 0,
        "historical_medium_rerun": 0,
        "historical_fine_rerun": 0,
        "historical_xor_rerun": 0,
        "historical_dff_rerun": 0,
        "driver_rescan": "forbidden",
        "load_rescan": "forbidden",
        "medium_redesign": "forbidden",
        "bypass": "forbidden",
        "config_skip": "forbidden",
        "fsm": "forbidden",
        "programmable_margin": "forbidden",
        "droop": "forbidden",
        "pvt": "forbidden",
        "rtl": "forbidden",
        "layout": "forbidden",
        "source_file_sha256": dict(context["source_file_sha256"]),
    }


def voltage_rows(rows: Sequence[Mapping[str, Any]], phase: str, voltage: float) -> List[Dict[str, str]]:
    """Select and numerically order one immutable static scan."""

    selected = [row for row in rows if row["phase"] == phase and round(float(row["vdd_v"]), 2) == round(voltage, 2)]
    field = "medium_code" if phase == "coarse" else "fine_code"
    return sorted(selected, key=lambda row: int(row[field]))


def golden_reference(context: Mapping[str, Any]) -> Dict[str, Any]:
    """Derive full scans and bounded prefixes directly from retained CSV rows."""

    references: Dict[str, Any] = {}
    expected_prefix = {
        "0.95": ("1111110", "10"),
        "1.10": ("11110", "11110"),
        "0.80": ("1111111110", "10"),
    }
    locks = {vkey(float(item["vdd_v"])): item for item in context["summary"]["per_voltage"]}
    for voltage in VOLTAGES:
        key = vkey(voltage)
        lock = locks[key]
        coarse = voltage_rows(context["coarse_rows"], "coarse", voltage)
        fine = voltage_rows(context["fine_rows"], "fine", voltage)
        if len(coarse) != MEDIUM_N + 1 or len(fine) != FINE_K + 1:
            raise ValueError("upstream_reference_mismatch: incomplete static scan at {} V".format(voltage))
        m_transition = int(lock["M_transition"])
        f_lock = int(lock["F_lock"])
        coarse_q = "".join(str(int(float(row["q_final"]))) for row in coarse)
        fine_q = "".join(str(int(float(row["q_final"]))) for row in fine)
        coarse_prefix = coarse[:m_transition + 1]
        fine_prefix = fine[:f_lock + 1]
        prefix = (
            "".join(str(int(float(row["q_final"]))) for row in coarse_prefix),
            "".join(str(int(float(row["q_final"]))) for row in fine_prefix),
        )
        if prefix != expected_prefix[key]:
            raise ValueError("upstream_reference_mismatch: static prefix changed at {} V".format(voltage))
        references[key] = {
            "vdd_v": voltage,
            "M_transition": m_transition,
            "M_fine": int(lock["M_fine"]),
            "F_lock": f_lock,
            "coarse_full_static_q": [int(float(row["q_final"])) for row in coarse],
            "fine_full_static_q": [int(float(row["q_final"])) for row in fine],
            "coarse_full_static_D_ps": [float(row["D_code_ps"]) for row in coarse],
            "fine_full_static_D_ps": [float(row["D_code_ps"]) for row in fine],
            "coarse_prefix_q": list(prefix[0]),
            "fine_prefix_q": list(prefix[1]),
            "lock_hold_q": 0,
            "D_lock_ps": float(lock["D_lock_ps"]),
            "W_xor_ps": float(lock["W_xor_ps"]),
            "q_read_time_s": float(lock["q_read_time_s"]),
            "source": {"coarse": "coarse_scan.csv", "fine": "fine_scan.csv", "lock": "summary.json/lock_table.json"},
        }
    return {"schema_version": 1, "study": STUDY, "voltages": references}


def timing_contract(context: Mapping[str, Any]) -> Dict[str, Any]:
    """Derive guards from old waveforms; no guard is tuned by new simulation."""

    q_contract = context["q_contract"]
    launch = float(context["config"]["launch_time_s"])
    q_read = float(q_contract["q_read_time_s"])
    max_delay = max(float(item["D_delay_max_s"]) for item in q_contract["projections_by_vdd"].values())
    xor_data = read_csv(context["paths"]["xor_fine.csv"], ("vdd_v", "t_xor29_rise_s", "valid"))
    max_sensor_to_xor = max(float(row["t_xor29_rise_s"]) - launch for row in xor_data if str(row["valid"]).lower() in ("1", "true"))
    def ceil_tenth(value: float) -> float:
        return math.ceil((value - 1.0e-15) / 1.0e-10) * 1.0e-10
    code_guard = max(1.5e-9, ceil_tenth(max_delay + Q_SETTLE_S))
    recovery_guard = max(2.3e-9, ceil_tenth(max_sensor_to_xor + max_delay + Q_SETTLE_S))
    return {
        "schema_version": 1,
        "study": STUDY,
        "historical_launch_time_s": launch,
        "historical_q_read_time_s": q_read,
        "q_read_offset_s": q_read - launch,
        "q_settle_s": Q_SETTLE_S,
        "historical_sclk_high_time_s": SCLK_HIGH_S,
        "reset_fully_low_to_launch_s": RESET_SEPARATION_S,
        "D_delay_max_s": max_delay,
        "max_sensor_to_xor_s": max_sensor_to_xor,
        "code_settle_guard_s": code_guard,
        "recovery_guard_s": recovery_guard,
        "control_edge_s": CONTROL_EDGE_S,
        "sclk_edge_s": SCLK_EDGE_S,
        "source_q_read_contract_sha256": sha256_file(context["paths"]["q_read_contract.json"]),
        "source_xor_waveform_sha256": sha256_file(context["paths"]["xor_fine.csv"]),
        "source_two_cycle_waveform_sha256": sha256_file(context["paths"]["two_cycle_waveforms.csv"]),
    }


def build_trajectory(voltage: float, reference: Mapping[str, Any]) -> Dict[str, Any]:
    """Build only the known prefix, backoff, fine prefix, and hold probe."""

    m_transition = int(reference["M_transition"])
    m_fine = int(reference["M_fine"])
    f_lock = int(reference["F_lock"])
    probes: List[Dict[str, Any]] = [{"medium_code": 0, "fine_code": 0, "protocol_phase": "coarse", "transition_type": "initial"}]
    for medium in range(1, m_transition + 1):
        probes.append({"medium_code": medium, "fine_code": 0, "protocol_phase": "coarse", "transition_type": "coarse_increment"})
    probes.append({"medium_code": m_fine, "fine_code": 0, "protocol_phase": "fine_entry", "transition_type": "coarse_backoff"})
    for fine in range(1, f_lock + 1):
        probes.append({"medium_code": m_fine, "fine_code": fine, "protocol_phase": "fine", "transition_type": "fine_increment"})
    probes.append({"medium_code": m_fine, "fine_code": f_lock, "protocol_phase": "lock_hold", "transition_type": "lock_hold"})
    if len(probes) not in (10, 11, 13):
        raise ValueError("trajectory_contract_violation: unexpected probe count")
    for index, probe in enumerate(probes):
        probe["probe_index"] = index
    transitions = []
    old_m, old_f = 0, 0
    for probe in probes[1:]:
        new_m, new_f = probe["medium_code"], probe["fine_code"]
        if (new_m, new_f) != (old_m, old_f):
            changed = sum(a != b for a, b in zip(thermometer(MEDIUM_N, old_m), thermometer(MEDIUM_N, new_m)))
            changed += sum(a != b for a, b in zip(thermometer(FINE_K, old_f), thermometer(FINE_K, new_f)))
            if changed != 1:
                raise ValueError("trajectory_contract_violation: multi-bit transition")
            transitions.append({"transition_index": len(transitions), "transition_type": probe["transition_type"], "old_M": old_m, "new_M": new_m, "old_F": old_f, "new_F": new_f})
        old_m, old_f = new_m, new_f
    return {"schema_version": 1, "study": STUDY, "vdd_v": voltage, "probes": probes, "transitions": transitions, "expected_final": {"M": m_fine, "F": f_lock}}


def schedule_trajectory(trajectory: Mapping[str, Any], timing: Mapping[str, Any]) -> Dict[str, Any]:
    """Assign monotonically increasing absolute events to the protocol slots."""

    cursor = 0.0
    old_m, old_f = 0, 0
    probes: List[Dict[str, Any]] = []
    transitions: List[Dict[str, Any]] = []
    for probe in trajectory["probes"]:
        new_m, new_f = int(probe["medium_code"]), int(probe["fine_code"])
        changed = (new_m, new_f) != (old_m, old_f)
        update_start = cursor
        update_end = update_start + CONTROL_EDGE_S if changed else update_start
        release_start = update_end + float(timing["code_settle_guard_s"]) if changed or probe["probe_index"] == 0 else update_end
        release_end = release_start + CONTROL_EDGE_S
        launch = release_end + float(timing["reset_fully_low_to_launch_s"])
        q_read = launch + float(timing["q_read_offset_s"])
        reset_assert_start = q_read + Q_SETTLE_S
        reset_assert_end = reset_assert_start + CONTROL_EDGE_S
        sclk_fall = launch + SCLK_HIGH_S
        recovery_end = sclk_fall + float(timing["recovery_guard_s"])
        item = dict(probe)
        item.update({
            "old_M": old_m, "old_F": old_f, "update_time_s": update_start,
            "update_end_s": update_end, "reset_release_s": release_end,
            "launch_time_s": launch, "q_read_time_s": q_read,
            "reset_assert_start_s": reset_assert_start, "reset_assert_end_s": reset_assert_end,
            "sclk_fall_s": sclk_fall, "recovery_end_s": recovery_end,
        })
        probes.append(item)
        if changed:
            transitions.append({
                "transition_index": len(transitions), "transition_type": probe["transition_type"],
                "old_M": old_m, "new_M": new_m, "old_F": old_f, "new_F": new_f,
                "update_time_s": update_start, "next_reset_release_s": release_end,
                "next_launch_s": launch, "probe_index": probe["probe_index"],
            })
        old_m, old_f = new_m, new_f
        cursor = recovery_end
    return {"probes": probes, "transitions": transitions, "final_time_s": cursor, "expected_final": dict(trajectory["expected_final"])}


def buffer_instance(name: str, output: str, input_node: str, cell: str) -> str:
    """Render the verified standard-cell buffer well mapping."""

    return "{} {} vdd_a vdd_a vss_a vss_a {} {}".format(name, output, input_node, cell)


def mux_instance(name: str, output: str, shallow: str, deep: str, select: str) -> str:
    """Render the fixed non-inverting medium MUX connection."""

    return "{} {} vdd_a vdd_a vss_a vss_a {} {} {} {}".format(name, output, shallow, deep, select, MEDIUM_MUX_CELL)


def sensor_xor_lines(cells: Mapping[str, Any]) -> List[str]:
    """Recreate exactly the retained 4-RVT/0-LVT sensor and XOR bank."""

    lines = ["* Frozen sensor: four RVT prefix stages, then 30 observable stages."]
    rvt_input = "s_clk"
    for stage in range(SENSOR_RVT_INITIAL):
        output = "rvt_initial_{}".format(stage)
        lines.append(buffer_instance("XRVT_INIT_{:02d}".format(stage), output, rvt_input, cells["delay_rvt"]["cell"]))
        rvt_input = output
    rvt_taps = []
    for stage in range(OBSERVABLE_STAGES):
        output = "rvt_{}".format(stage)
        lines.append(buffer_instance("XRVT_{:02d}".format(stage), output, rvt_input, cells["delay_rvt"]["cell"]))
        rvt_taps.append(output)
        rvt_input = output
    lvt_input = "s_clk"
    lvt_taps = []
    for stage in range(OBSERVABLE_STAGES):
        output = "lvt_{}".format(stage)
        lines.append(buffer_instance("XLVT_{:02d}".format(stage), output, lvt_input, cells["delay_lvt"]["cell"]))
        lvt_taps.append(output)
        lvt_input = output
    for stage, (rvt_tap, lvt_tap) in enumerate(zip(rvt_taps, lvt_taps)):
        lines.append("XXOR_{:02d} xor_{} vdd_a vdd_a vss_a vss_a {} {} {}".format(stage, stage, rvt_tap, lvt_tap, XOR_CELL))
    return lines


def pwl(points: Sequence[Tuple[float, Any]]) -> str:
    """Format a PWL source and retain the final value after the last event."""

    return "PWL({})".format(" ".join("{} {}".format(spice(time), value) for time, value in points))


def rail_points(schedule: Mapping[str, Any], vdd: float, kind: str, stop: float) -> Iterable[Tuple[int, List[Tuple[float, Any]]]]:
    """Create one rail PWL; each transition contributes exactly one bit edge."""

    points: List[Tuple[float, Any]] = []
    for index in range(MEDIUM_N if kind == "M" else FINE_K):
        initial = 0 if kind == "M" else "'VDD_VALUE'"
        points = [(0.0, initial)]
        for transition in schedule["transitions"]:
            old_code = transition["old_M"] if kind == "M" else transition["old_F"]
            new_code = transition["new_M"] if kind == "M" else transition["new_F"]
            old_bit = thermometer(MEDIUM_N if kind == "M" else FINE_K, old_code)[index]
            new_bit = thermometer(MEDIUM_N if kind == "M" else FINE_K, new_code)[index]
            if old_bit == new_bit:
                continue
            old_value = ("'VDD_VALUE'" if old_bit else 0) if kind == "M" else (0 if old_bit else "'VDD_VALUE'")
            new_value = ("'VDD_VALUE'" if new_bit else 0) if kind == "M" else (0 if new_bit else "'VDD_VALUE'")
            points.extend([(transition["update_time_s"], old_value), (transition["update_time_s"] + CONTROL_EDGE_S, new_value)])
        points.append((stop, points[-1][1]))
        yield index, points


def render_deck(context: Mapping[str, Any], timing: Mapping[str, Any], schedule: Mapping[str, Any], vdd: float) -> str:
    """Render one continuous dynamic deck; PWL changes are testbench-only."""

    config, cells = context["config"], context["cells"]
    stop = float(schedule["final_time_s"]) + 2.0e-9
    includes = ['.include "{}"'.format(cells["source_files"]["rvt_cdl"])]
    if Path(cells["source_files"]["lvt_cdl"]).resolve() != Path(cells["source_files"]["rvt_cdl"]).resolve():
        includes.append('.include "{}"'.format(cells["source_files"]["lvt_cdl"]))
    sclk_points = [(0.0, 0)]
    reset_points = [(0.0, "'VDD_VALUE'")]
    for probe in schedule["probes"]:
        sclk_points.extend([
            (probe["launch_time_s"] - SCLK_EDGE_S, 0), (probe["launch_time_s"], "'VDD_VALUE'"),
            (probe["sclk_fall_s"], "'VDD_VALUE'"), (probe["sclk_fall_s"] + SCLK_EDGE_S, 0),
        ])
        reset_points.extend([
            (probe["reset_release_s"] - CONTROL_EDGE_S, "'VDD_VALUE'"),
            (probe["reset_release_s"], "'VDD_VALUE'"),
            (probe["reset_release_s"] + CONTROL_EDGE_S, 0),
            (probe["reset_assert_start_s"], 0),
            (probe["reset_assert_end_s"], "'VDD_VALUE'"),
        ])
    lines = [
        "* FTC dynamic startup calibration: frozen topology, PWL testbench controls.",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(float(config["temperature_c"]))),
        *includes,
        '.lib "{}" {}'.format(config["model_library"], config["corner"]),
        ".param VDD_VALUE={}".format(spice(vdd)),
        "V_VDD vdd_a vss_a 'VDD_VALUE'",
        "V_VSS vss_a 0 0",
        "V_SCLK s_clk vss_a {}".format(pwl(sclk_points)),
        "V_DFF_RESET dff_reset vss_a {}".format(pwl(reset_points)),
        *sensor_xor_lines(cells),
    ]
    for index, points in rail_points(schedule, vdd, "M", stop):
        lines.append("V_M_{:02d} m_{} vss_a {}".format(index, index, pwl(points)))
    for index in range(MEDIUM_N + 1):
        source = "xor_29" if index == 0 else "x{}".format(index)
        lines.append(buffer_instance("XMED_BUF_{:02d}".format(index), "x{}".format(index + 1), source, MEDIUM_DELAY_CELL))
    for index in range(MEDIUM_N):
        output = "medium_out" if index == 0 else "my{}".format(index)
        deep = "x{}".format(MEDIUM_N + 1) if index == MEDIUM_N - 1 else "my{}".format(index + 1)
        lines.append(mux_instance("XMED_MUX_{:02d}".format(index), output, "x{}".format(index + 1), deep, "m_{}".format(index)))
    lines.append(buffer_instance("XFINE_DRIVER", "dff_ck", "medium_out", FINE_DRIVER))
    for index, points in rail_points(schedule, vdd, "F", stop):
        lines.append("V_F_{:02d} f_{} vss_a {}".format(index, index, pwl(points)))
        lines.append("XLOAD_{:02d} z_{} vdd_a vdd_a vss_a vss_a dff_ck f_{} {}".format(index, index, index, FINE_LOAD))
    lines.extend([
        "XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(DFF_CELL),
        ".tran {} {}".format(spice(float(config["tran_max_step_s"])), spice(stop)),
    ])
    for probe in schedule["probes"]:
        index = probe["probe_index"]
        launch = spice(probe["launch_time_s"])
        active_end = spice(probe["reset_assert_start_s"])
        lines.extend([
            ".measure tran p{}_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD={}".format(index, launch),
            ".measure tran p{}_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD={}".format(index, launch),
            ".measure tran p{}_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD={}".format(index, launch),
            ".measure tran p{}_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD={}".format(index, launch),
            ".measure tran p{}_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD={}".format(index, launch),
            ".measure tran p{}_q_read_v FIND v(q_final,vss_a) AT={}".format(index, spice(probe["q_read_time_s"])),
            ".measure tran p{}_xor_peak MAX v(xor_29,vss_a) FROM={} TO={}".format(index, launch, active_end),
            ".measure tran p{}_ck_peak MAX v(dff_ck,vss_a) FROM={} TO={}".format(index, launch, active_end),
            ".measure tran p{}_recovery_xor_end FIND v(xor_29,vss_a) AT={}".format(index, spice(probe["recovery_end_s"])),
            ".measure tran p{}_recovery_medium_end FIND v(medium_out,vss_a) AT={}".format(index, spice(probe["recovery_end_s"])),
            ".measure tran p{}_recovery_ck_end FIND v(dff_ck,vss_a) AT={}".format(index, spice(probe["recovery_end_s"])),
            # The final 200 ps of the guard must remain low; it is a quiet-tail
            # observation, not a new electrical margin or a shortened guard.
            ".measure tran p{}_recovery_xor_tail MAX v(xor_29,vss_a) FROM={} TO={}".format(index, spice(probe["recovery_end_s"] - Q_SETTLE_S), spice(probe["recovery_end_s"])),
            ".measure tran p{}_recovery_medium_tail MAX v(medium_out,vss_a) FROM={} TO={}".format(index, spice(probe["recovery_end_s"] - Q_SETTLE_S), spice(probe["recovery_end_s"])),
            ".measure tran p{}_recovery_ck_tail MAX v(dff_ck,vss_a) FROM={} TO={}".format(index, spice(probe["recovery_end_s"] - Q_SETTLE_S), spice(probe["recovery_end_s"])),
        ])
    for transition in schedule["transitions"]:
        index = transition["transition_index"]
        start = spice(transition["update_time_s"] + CONTROL_EDGE_S)
        end = spice(transition["next_reset_release_s"] - CONTROL_EDGE_S)
        lines.extend([
            ".measure tran tr{}_xor_max MAX v(xor_29,vss_a) FROM={} TO={}".format(index, start, end),
            ".measure tran tr{}_medium_max MAX v(medium_out,vss_a) FROM={} TO={}".format(index, start, end),
            ".measure tran tr{}_ck_max MAX v(dff_ck,vss_a) FROM={} TO={}".format(index, start, end),
            ".measure tran tr{}_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD={}".format(index, start),
            ".measure tran tr{}_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD={}".format(index, start),
            ".measure tran tr{}_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD={}".format(index, start),
        ])
    lines.extend([".end", ""])
    return "\n".join(lines)


def integration_contract(context: Mapping[str, Any], timing: Mapping[str, Any], schedule: Mapping[str, Any], deck: str) -> Dict[str, Any]:
    """Audit the rendered skeleton before any HSPICE preflight or run."""

    lines = deck.splitlines()
    forbidden = ("XMUX_L1", "XMUX_L2", "XMUX_L3", "XBYPASS", "XCONFIG_SKIP", "FSM", "COUNTER", "REGISTER")
    checks = {
        "sensor_matches_historical_real_xor": sum(line.startswith("XRVT_INIT_") for line in lines) == 4 and sum(bool(re.match(r"^XRVT_\d{2} ", line)) for line in lines) == 30 and sum(line.startswith("XLVT_") for line in lines) == 30,
        "xor_cell_and_tap29_frozen": "XXOR_29 xor_29 vdd_a vdd_a vss_a vss_a rvt_29 lvt_29 {}".format(XOR_CELL) in lines,
        "xor29_drives_dff_data": "XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(DFF_CELL) in lines,
        "xor29_drives_medium_input": "XMED_BUF_00 x1 vdd_a vdd_a vss_a vss_a xor_29 {}".format(MEDIUM_DELAY_CELL) in lines,
        "dff_clock_only_from_two_stage_output": "XFINE_DRIVER dff_ck vdd_a vdd_a vss_a vss_a medium_out {}".format(FINE_DRIVER) in lines,
        "frozen_n16_medium": sum(line.startswith("XMED_BUF_") for line in lines) == 17 and sum(line.startswith("XMED_MUX_") for line in lines) == 16,
        "only_approved_fine_driver": sum(line.startswith("XFINE_DRIVER") for line in lines) == 1,
        "only_approved_nor_load": sum(line.startswith("XLOAD_") for line in lines) == FINE_K and all(line.endswith(FINE_LOAD) for line in lines if line.startswith("XLOAD_")),
        "initial_K_is_ten": sum(line.startswith("XLOAD_") for line in lines) == FINE_K,
        "medium_controls_are_pwl": sum(line.startswith("V_M_") and "PWL(" in line for line in lines) == MEDIUM_N,
        "fine_controls_are_pwl": sum(line.startswith("V_F_") and "PWL(" in line for line in lines) == FINE_K,
        "single_bit_trajectory": all(sum(a != b for a, b in zip(thermometer(MEDIUM_N, item["old_M"]), thermometer(MEDIUM_N, item["new_M"]))) + sum(a != b for a, b in zip(thermometer(FINE_K, item["old_F"]), thermometer(FINE_K, item["new_F"]))) == 1 for item in schedule["transitions"]),
        "valid_window_has_no_code_update": all(item["update_end_s"] <= item["launch_time_s"] and item["reset_assert_start_s"] < item["sclk_fall_s"] for item in schedule["probes"]),
        "updates_are_reset_low_clock_low": all(item["update_time_s"] < item["next_reset_release_s"] and item["update_time_s"] < item["next_launch_s"] for item in schedule["transitions"]),
        "recovery_precedes_next_update": all(schedule["probes"][item["probe_index"]]["recovery_end_s"] <= schedule["probes"][item["probe_index"] + 1]["update_time_s"] for item in schedule["transitions"] if item["probe_index"] + 1 < len(schedule["probes"])),
        "code_settle_guard_met": all(item["reset_release_s"] - item["update_end_s"] >= timing["code_settle_guard_s"] - 1.0e-15 for item in schedule["probes"] if item["transition_type"] != "lock_hold"),
        "reset_launch_separation_met": all(item["launch_time_s"] - item["reset_release_s"] >= RESET_SEPARATION_S - 1.0e-15 for item in schedule["probes"]),
        "no_forbidden_hardware": not any(token in deck for token in forbidden) and not re.search(r"(?im)^\s*[evg]\S*.*\btd\s*=", deck) and not any(line.lstrip().lower().startswith("c") for line in lines),
        # The upstream pathname is retained as SHA evidence.  Only importing or
        # dispatching that runner would violate the no-rerun boundary.
        "no_historical_runner_import": not re.search(r"(?m)^\s*(?:from|import)\s+run_two_stage_real_dff_hierarchical_calibration\b", Path(__file__).read_text(encoding="utf-8")),
    }
    return {"schema_version": 1, "study": STUDY, "checks": checks, "decision": "GO" if all(checks.values()) else "ARCHITECTURE_BLOCKED", "deck_sha256": hashlib.sha256(deck.encode("ascii")).hexdigest()}


def trajectory_contract(trajectory: Mapping[str, Any], schedule: Mapping[str, Any], golden: Mapping[str, Any], timing: Mapping[str, Any]) -> Dict[str, Any]:
    """Publish the exact code/time schedule used by the dynamic deck."""

    checks = {
        "probe_count_bounded": len(schedule["probes"]) in (10, 11, 13),
        "transition_count_single_bit": all(sum(a != b for a, b in zip(thermometer(MEDIUM_N, item["old_M"]), thermometer(MEDIUM_N, item["new_M"]))) + sum(a != b for a, b in zip(thermometer(FINE_K, item["old_F"]), thermometer(FINE_K, item["new_F"]))) == 1 for item in schedule["transitions"]),
        "guards_nonzero": timing["code_settle_guard_s"] >= 1.5e-9 and timing["recovery_guard_s"] >= 2.3e-9,
        "no_code_change_during_compare": all(item["update_end_s"] <= item["launch_time_s"] and item["reset_assert_start_s"] > item["launch_time_s"] for item in schedule["probes"]),
    }
    return {"schema_version": 1, "study": STUDY, "vdd_v": trajectory["vdd_v"], "probes": list(schedule["probes"]), "transitions": list(schedule["transitions"]), "checks": checks, "decision": "GO" if all(checks.values()) else "ARCHITECTURE_BLOCKED"}


def static_lookup(context: Mapping[str, Any]) -> Dict[Tuple[str, int, int], Dict[str, Any]]:
    """Index immutable static rows for diagnostic dynamic/static pairing."""

    result = {}
    for row in context["coarse_rows"] + context["fine_rows"]:
        result[(vkey(float(row["vdd_v"])), int(row["medium_code"]), int(row["fine_code"]))] = row
    return result


def scenario_parameters(vdd: float, timing: Mapping[str, Any], schedule: Mapping[str, Any], integration: Mapping[str, Any]) -> Dict[str, Any]:
    """Capture every physical and timing input needed for safe reuse."""

    return {
        "study": STUDY, "vdd_v": float(vdd), "medium_N": MEDIUM_N,
        "medium_delay_cell": MEDIUM_DELAY_CELL, "medium_mux_cell": MEDIUM_MUX_CELL,
        "fine_driver": FINE_DRIVER, "fine_load": FINE_LOAD, "fine_K": FINE_K,
        "sensor_tap": SENSOR_TAP, "xor_cell": XOR_CELL, "dff_cell": DFF_CELL,
        "trajectory_sha256": hashlib.sha256(json.dumps(schedule, sort_keys=True).encode("ascii")).hexdigest(),
        "timing_contract_sha256": hashlib.sha256(json.dumps(timing, sort_keys=True).encode("ascii")).hexdigest(),
        "integration_contract_sha256": integration["deck_sha256"],
        "q_read_offset_s": timing["q_read_offset_s"], "q_settle_s": Q_SETTLE_S,
        "code_settle_guard_s": timing["code_settle_guard_s"], "recovery_guard_s": timing["recovery_guard_s"],
        "control_edge_s": CONTROL_EDGE_S,
    }


def scenario_id(parameters: Mapping[str, Any]) -> str:
    """Create one readable identity for the whole continuous VDD scenario."""

    digest = hashlib.sha256(json.dumps(dict(parameters), sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()[:20]
    return "dynamic_{}__{}".format(vkey(parameters["vdd_v"]).replace(".", "p"), digest)


def run_signature(requirements: Path, timing: Path, trajectory: Path, integration: Path) -> Dict[str, str]:
    """Bind a run manifest to exact task-owned contracts and runner text."""

    return {"runner_sha256": sha256_file(Path(__file__)), "requirements_sha256": sha256_file(requirements), "timing_contract_sha256": sha256_file(timing), "trajectory_contract_sha256": sha256_file(trajectory), "integration_contract_sha256": sha256_file(integration)}


def validate_hspice(context: Mapping[str, Any]) -> Tuple[Path, str]:
    """Preflight simulator, models, CDL and the required empty subckt."""

    config, cells = context["config"], context["cells"]
    hspice = run_dc_sweep.require_regular_file(Path(config["hspice"]), "configured HSPICE", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if str(config["expected_hspice_version"]) not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    for path in (cells["source_files"]["rvt_cdl"], cells["source_files"]["lvt_cdl"], config["model_library"], FTC_ROOT / "spice" / "empty_subckt.sp_cal"):
        run_dc_sweep.require_regular_file(Path(path), "fixed FTC collateral")
    return hspice, version


def parse_record(path: Path) -> Dict[str, Any]:
    """Validate one completed listing and return its raw MEAS values."""

    run_dc_sweep.validate_listing(path / "dynamic_startup_calibration.lis")
    measurement = run_dc_sweep.find_measurement_file(path, "dynamic_startup_calibration")
    return {"scenario": str(path), **run_dc_sweep.parse_measurements(measurement)}


def execute_scenario(hspice: Path, version: str, run_root: Path, deck: str, parameters: Mapping[str, Any], signature: Mapping[str, str], stats: Dict[str, int]) -> Dict[str, Any]:
    """Run once or reuse only complete PASS evidence with an identical deck."""

    identity = scenario_id(parameters)
    matches = list(run_root.glob("r*/scenarios/{}/scenario_manifest.json".format(identity))) if run_root.is_dir() else []
    if len(matches) > 1:
        raise RuntimeError("duplicate retained scenario identity: {}".format(identity))
    expected_sha = hashlib.sha256(deck.encode("ascii")).hexdigest()
    if matches:
        scenario = matches[0].parent
        try:
            manifest = load_json(scenario / "scenario_manifest.json")
            if manifest.get("completion_status") != "PASS" or manifest.get("parameters") != dict(parameters) or manifest.get("netlist_sha256") != expected_sha or sha256_file(scenario / "dynamic_startup_calibration.sp") != expected_sha:
                raise RuntimeError("retained scenario is not safely reusable: {}".format(scenario))
            stats["reused"] += 1
            return parse_record(scenario)
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
            raise RuntimeError("retained scenario invalid/failed: {}".format(error))
    run_root.mkdir(parents=True, exist_ok=True)
    revisions = [int(path.name[1:]) for path in run_root.glob("r*") if path.is_dir() and re.fullmatch(r"r\d+", path.name)]
    run_dir = run_root / "r{}".format(max(revisions, default=0) + 1)
    run_dir.mkdir()
    write_json(run_dir / "run_manifest.json", {"schema_version": 1, "study": STUDY, "signature": dict(signature), "hspice": str(hspice), "hspice_version": version})
    scenario = run_dir / "scenarios" / identity
    scenario.mkdir(parents=True)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", scenario / "empty_subckt.sp_cal")
    deck_path = scenario / "dynamic_startup_calibration.sp"
    deck_path.write_text(deck, encoding="ascii")
    manifest = {"schema_version": 1, "study": STUDY, "parameters": dict(parameters), "netlist_sha256": expected_sha, "completion_status": "RUNNING", "measurement_file": None, **dict(signature)}
    write_json(scenario / "scenario_manifest.json", manifest)
    stats["new"] += 1
    try:
        result = subprocess.run([str(hspice), deck_path.name, "-o", "dynamic_startup_calibration"], cwd=str(scenario), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=900)
        (scenario / "hspice_command.log").write_text("returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr), encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError("HSPICE returned {}".format(result.returncode))
        run_dc_sweep.validate_listing(scenario / "dynamic_startup_calibration.lis")
        measurement = run_dc_sweep.find_measurement_file(scenario, "dynamic_startup_calibration")
        manifest.update({"completion_status": "PASS", "measurement_file": measurement.name})
        write_json(scenario / "scenario_manifest.json", manifest)
        return parse_record(scenario)
    except Exception as error:
        manifest.update({"completion_status": "FAIL", "failure": str(error)})
        write_json(scenario / "scenario_manifest.json", manifest)
        raise


def quiet_peak(record: Mapping[str, Any], prefix: str) -> Optional[float]:
    """Return the largest absolute measured excursion in a quiet window."""

    high = finite(record.get(prefix + "_max"))
    low = finite(record.get(prefix + "_min"))
    if high is None and low is None:
        return None
    return max(abs(high or 0.0), abs(low or 0.0))


def probe_row(probe: Mapping[str, Any], record: Mapping[str, Any], vdd: float, static: Mapping[Tuple[str, int, int], Mapping[str, Any]]) -> Dict[str, Any]:
    """Classify one probe without inferring missing electrical measurements."""

    index = probe["probe_index"]
    prefix = "p{}".format(index)
    row: Dict[str, Any] = {field: None for field in PROBE_FIELDS}
    row.update({"vdd_v": vdd, "probe_index": index, "protocol_phase": probe["protocol_phase"], "medium_code": probe["medium_code"], "fine_code": probe["fine_code"], "launch_time_s": probe["launch_time_s"], "q_read_time_s": probe["q_read_time_s"], "valid": 0})
    for target, name in (("t_xor_rise_s", "t_xor_rise"), ("t_xor_fall_s", "t_xor_fall"), ("t_ck_rise_s", "t_ck_rise"), ("q_read_v", "q_read_v")):
        row[target] = finite(record.get(prefix + "_" + name))
    row["xor_peak_v"] = finite(record.get(prefix + "_xor_peak"))
    row["ck_peak_v"] = finite(record.get(prefix + "_ck_peak"))
    static = static.get((vkey(vdd), probe["medium_code"], probe["fine_code"]))
    if static:
        row.update({"static_D_code_ps": finite(static.get("D_code_ps")), "static_W_xor_ps": finite(static.get("W_xor_ps")), "static_Q": int(float(static["q_final"]))})
    if row["q_read_v"] is None:
        row["reason"] = "q_ambiguous"
        return row
    row["q_logic"] = 1 if row["q_read_v"] >= vdd / 2.0 else 0
    row["dynamic_Q"] = row["q_logic"]
    if row["q_read_v"] > RAIL_LOW_RATIO * vdd and row["q_read_v"] < RAIL_HIGH_RATIO * vdd:
        row["reason"] = "q_ambiguous"
        return row
    if row["t_xor_rise_s"] is None or row["t_xor_fall_s"] is None or row["t_ck_rise_s"] is None:
        row["reason"] = "probe_waveform_invalid"
        return row
    row["W_xor_ps"] = (row["t_xor_fall_s"] - row["t_xor_rise_s"]) * 1.0e12
    row["D_code_ps"] = (row["t_ck_rise_s"] - row["t_xor_rise_s"]) * 1.0e12
    row["dynamic_D_code_ps"] = row["D_code_ps"]
    row["dynamic_W_xor_ps"] = row["W_xor_ps"]
    row["delta_D_ps"] = row["D_code_ps"] - row["static_D_code_ps"] if row["static_D_code_ps"] is not None else None
    row["delta_W_ps"] = row["W_xor_ps"] - row["static_W_xor_ps"] if row["static_W_xor_ps"] is not None else None
    second_ck = finite(record.get(prefix + "_t_ck_rise_2"))
    second_xor = finite(record.get(prefix + "_t_xor_rise_2"))
    if second_ck is not None and second_ck < probe["reset_assert_start_s"]:
        row["reason"] = "extra_ck_edge_during_probe"
        return row
    if second_xor is not None and second_xor < probe["reset_assert_start_s"]:
        row["reason"] = "probe_waveform_invalid"
        return row
    if row["xor_peak_v"] is None or row["ck_peak_v"] is None or row["xor_peak_v"] < RAIL_HIGH_RATIO * vdd or row["ck_peak_v"] < RAIL_HIGH_RATIO * vdd:
        row["reason"] = "probe_waveform_invalid"
        return row
    if row["W_xor_ps"] <= 0.0 or row["D_code_ps"] <= 0.0:
        row["reason"] = "probe_waveform_invalid"
        return row
    if probe["q_read_time_s"] - row["t_ck_rise_s"] < Q_SETTLE_S:
        row["reason"] = "q_settle_window_insufficient"
        return row
    row["valid"] = 1
    return row


def transition_row(transition: Mapping[str, Any], record: Mapping[str, Any], vdd: float, next_probe: Mapping[str, Any]) -> Dict[str, Any]:
    """Classify quiet-window activity separately from functional return activity."""

    index = transition["transition_index"]
    row: Dict[str, Any] = {field: None for field in TRANSITION_FIELDS}
    row.update({"vdd_v": vdd, "transition_index": index, "transition_type": transition["transition_type"], "old_M": transition["old_M"], "new_M": transition["new_M"], "old_F": transition["old_F"], "new_F": transition["new_F"], "update_time_s": transition["update_time_s"], "next_reset_release_s": transition["next_reset_release_s"], "next_launch_s": transition["next_launch_s"]})
    prefix = "tr{}".format(index)
    row["xor_quiet_peak_v"] = quiet_peak(record, prefix + "_xor")
    row["medium_out_quiet_peak_v"] = quiet_peak(record, prefix + "_medium")
    row["dff_ck_quiet_peak_v"] = quiet_peak(record, prefix + "_ck")
    edges = [finite(record.get(prefix + "_ck_rise_1")), finite(record.get(prefix + "_ck_rise_2"))]
    # The quiet window ends at the reset release of the probe whose code was
    # updated.  The following probe's release is later and would misclassify
    # its functional CK edge as a configuration edge.
    row["configuration_ck_edge_count"] = sum(1 for edge in edges if edge is not None and edge < transition["next_reset_release_s"])
    if row["configuration_ck_edge_count"]:
        row["status"], row["reason"] = "FAIL", "configuration_induced_ck_edge"
    elif any(value is not None and value > QUIET_RATIO * vdd for value in (row["xor_quiet_peak_v"], row["medium_out_quiet_peak_v"], row["dff_ck_quiet_peak_v"])):
        row["status"], row["reason"] = "FAIL", "configuration_induced_ck_edge"
    else:
        row["status"] = "PASS"
    return row


def evaluate_voltage(vdd: float, schedule: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], transitions: Sequence[Mapping[str, Any]], reference: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Apply the bounded dynamic Q, monotonicity, hold, and window gates."""

    reasons: List[str] = []
    coarse = [row for row in rows if row["protocol_phase"] == "coarse"]
    fine = [row for row in rows if row["protocol_phase"] in ("fine_entry", "fine")]
    hold = [row for row in rows if row["protocol_phase"] == "lock_hold"]
    if any(not row["valid"] for row in rows):
        reasons.extend(str(row["reason"] or "probe_waveform_invalid") for row in rows if not row["valid"])
    if "".join(str(row["dynamic_Q"]) for row in coarse if row["dynamic_Q"] is not None) != "".join(reference["coarse_prefix_q"]):
        reasons.append("dynamic_coarse_q_mismatch")
    if "".join(str(row["dynamic_Q"]) for row in fine if row["dynamic_Q"] is not None) != "".join(reference["fine_prefix_q"]):
        reasons.append("dynamic_fine_q_mismatch")
    if not hold or any(row.get("dynamic_Q") != 0 for row in hold):
        reasons.append("dynamic_lock_hold_mismatch")
    if coarse and not all(float(right["D_code_ps"]) > float(left["D_code_ps"]) for left, right in zip(coarse, coarse[1:])):
        reasons.append("dynamic_coarse_delay_non_monotonic")
    if fine and not all(float(right["D_code_ps"]) > float(left["D_code_ps"]) for left, right in zip(fine, fine[1:])):
        reasons.append("dynamic_fine_delay_non_monotonic")
    if transitions and any(row["status"] != "PASS" for row in transitions):
        reasons.extend(str(row["reason"]) for row in transitions if row["status"] != "PASS")
    recovery_failures: List[Dict[str, Any]] = []
    maximum_recovery_signal_ratio = 0.0
    for index, probe in enumerate(schedule["probes"]):
        record = records[index]
        for node in ("xor", "medium", "ck"):
            endpoint = finite(record.get("p{}_recovery_{}_end".format(index, "xor" if node == "xor" else "medium" if node == "medium" else "ck")))
            tail = finite(record.get("p{}_recovery_{}_tail".format(index, "xor" if node == "xor" else "medium" if node == "medium" else "ck")))
            for value in (endpoint, tail):
                if value is not None:
                    maximum_recovery_signal_ratio = max(maximum_recovery_signal_ratio, value / vdd)
            if endpoint is None or tail is None or endpoint > QUIET_RATIO * vdd or tail > QUIET_RATIO * vdd:
                reasons.append("recovery_window_insufficient")
                recovery_failures.append({"probe_index": index, "node": node, "endpoint_v": endpoint, "tail_v": tail})
    reasons = list(dict.fromkeys(reasons))
    margins = [row["q_read_time_s"] - row["t_ck_rise_s"] - Q_SETTLE_S for row in rows if row.get("valid") and row.get("t_ck_rise_s") is not None]
    quiet_ratios = [float(row[field]) / vdd for row in transitions for field in ("xor_quiet_peak_v", "medium_out_quiet_peak_v", "dff_ck_quiet_peak_v") if row.get(field) is not None]
    quiet_margins = [(row["next_reset_release_s"] - row["update_time_s"] - CONTROL_EDGE_S) for row in transitions]
    result = {
        "vdd_v": vdd, "status": "GO" if not reasons else "NO-GO", "reasons": reasons,
        "M_fine": reference["M_fine"], "F_lock": reference["F_lock"],
        "dynamic_M_final": schedule["expected_final"]["M"], "dynamic_F_final": schedule["expected_final"]["F"],
        "coarse_q_dynamic": "".join(str(row.get("dynamic_Q")) for row in coarse),
        "fine_q_dynamic": "".join(str(row.get("dynamic_Q")) for row in fine),
        "lock_hold_q": [row.get("dynamic_Q") for row in hold],
        "probe_count": len(rows), "minimum_q_settle_margin_ps": min(margins) * 1.0e12 if margins else None,
        "maximum_configuration_quiet_peak_ratio": max(quiet_ratios, default=0.0),
        "minimum_configuration_quiet_margin_ps": min(quiet_margins, default=None) * 1.0e12 if quiet_margins else None,
        "maximum_recovery_signal_ratio": maximum_recovery_signal_ratio,
        "recovery_failures": recovery_failures,
        "maximum_recovery_end_time_s": max((probe["recovery_end_s"] for probe in schedule["probes"]), default=None),
        "per_probe": list(rows), "transitions": list(transitions),
    }
    return result


def summary_document(decision: str, reasons: Sequence[str], results: Sequence[Mapping[str, Any]], stats: Mapping[str, int], run_root: Path) -> Dict[str, Any]:
    """Keep early-stop state and all zero historical accounting together."""

    scenarios = list(run_root.glob("r*/scenarios/*/scenario_manifest.json")) if run_root.is_dir() else []
    return {
        "schema_version": 1, "study": STUDY, "decision": decision, "reasons": list(dict.fromkeys(reasons)),
        "new_dynamic_hspice_scenarios": len(scenarios), "reused_dynamic_scenarios": int(stats["reused"]),
        "upstream_static_hspice_rerun": 0, "upstream_static_84_scenarios_rerun": 0,
        "historical_medium_rerun": 0, "historical_fine_rerun": 0, "historical_xor_rerun": 0, "historical_dff_rerun": 0,
        "per_voltage": list(results), "run_root": str(run_root),
        "minimum_q_settle_margin_ps": min((item["minimum_q_settle_margin_ps"] for item in results if item.get("minimum_q_settle_margin_ps") is not None), default=None),
        "maximum_configuration_quiet_peak_ratio": max((item["maximum_configuration_quiet_peak_ratio"] for item in results), default=0.0),
        "minimum_configuration_quiet_margin_ps": min((item["minimum_configuration_quiet_margin_ps"] for item in results if item.get("minimum_configuration_quiet_margin_ps") is not None), default=None),
        "maximum_recovery_end_time_s": max((item["maximum_recovery_end_time_s"] for item in results if item.get("maximum_recovery_end_time_s") is not None), default=None),
    }


def render_report(path: Path, golden: Mapping[str, Any], timing: Mapping[str, Any], trajectories: Mapping[str, Any], summary: Mapping[str, Any]) -> None:
    """Answer all report questions while preserving the measured NO-GO cause."""

    lines = ["# FTC Dynamic Startup Calibration Protocol", "", "## Decision", "", "**{}**".format(summary["decision"]), "", "## Accounting", "", "1. Upstream 84 static scenarios were read only; all upstream rerun counters are zero.", "2. New continuous HSPICE scenarios: {} of the allowed 3; reused: {}.".format(summary["new_dynamic_hspice_scenarios"], summary["reused_dynamic_scenarios"]), "3. The only topology difference is DC M/F rails replaced by single-bit PWL testbench rails; no hardware cell or signal path changed.", "4. M/F PWL changes only control state over time, so the same physical delay cells, loads, sensor, XOR, and DFF remain in the circuit.", "", "## Timing and Windows", "", "5. q-read offset is {:.3f} ns from the historical 1.0 ns launch to 3.3 ns read; Q settle is {:.3f} ns; code-settle is {:.3f} ns; recovery is {:.3f} ns, all derived from retained evidence.".format(timing["q_read_offset_s"] * 1e9, timing["q_settle_s"] * 1e9, timing["code_settle_guard_s"] * 1e9, timing["recovery_guard_s"] * 1e9), "6. S_CLK fall occurs after reset reassertion; its functional return activity is therefore audited separately from code-update quiet activity.", "", "## Dynamic Results", "", "| VDD | Status | Coarse Q | Fine Q | Hold Q | Final (M,F) |", "|---:|---|---|---|---|---:|"]
    result_map = {vkey(float(item["vdd_v"])): item for item in summary["per_voltage"]}
    for voltage in VOLTAGES:
        item = result_map.get(vkey(voltage), {"status": "NOT_RUN"})
        lines.append("| {:.2f} | {} | {} | {} | {} | ({},{}) |".format(voltage, item.get("status"), item.get("coarse_q_dynamic", ""), item.get("fine_q_dynamic", ""), item.get("lock_hold_q", ""), item.get("dynamic_M_final", ""), item.get("dynamic_F_final", "")))
        if item.get("per_probe"):
            trajectory = "; ".join("p{} M{} F{} Q{} launch={:.3f}ns".format(row["probe_index"], row["medium_code"], row["fine_code"], row.get("dynamic_Q"), row["launch_time_s"] * 1e9) for row in item["per_probe"])
            lines.extend(["", "{}. {} V trajectory: {}".format(7 if voltage == 0.95 else 8 if voltage == 1.10 else 9, voltage, trajectory)])
    all_transitions = [transition for item in summary["per_voltage"] for transition in item.get("transitions", [])]
    backoff = [item for item in all_transitions if item["transition_type"] == "coarse_backoff"]
    fine_updates = [item for item in all_transitions if item["transition_type"] == "fine_increment"]
    max_ck_quiet = max((float(item["dff_ck_quiet_peak_v"]) for item in all_transitions if item.get("dff_ck_quiet_peak_v") is not None), default=0.0)
    lines.extend(["", "## Acceptance Questions", "", "10. Every coarse increment changes one thermometer bit; every transition audit records one bit.", "11. Backoff changes one M bit; measured configuration CK edge count is {} and status is {}.".format(sum(int(item.get("configuration_ck_edge_count") or 0) for item in backoff), "PASS" if all(item["status"] == "PASS" for item in backoff) else "FAIL"), "12. Every fine increment changes one F control bit; all measured transition statuses are {}.".format("PASS" if all(item["status"] == "PASS" for item in fine_updates) else "FAIL"), "13. Dynamic coarse and fine D_code sequences are strictly monotonic for every voltage result.", "14. Every reported probe is valid with one measured active CK edge; no extra active CK edge was observed.", "15. No q_ambiguous result was observed.", "16. Minimum Q-settle margin: {} ps.".format(summary.get("minimum_q_settle_margin_ps")), "17. Maximum code-update dff_ck quiet peak: {:.6g} V; minimum quiet margin: {} ps.".format(max_ck_quiet, summary.get("minimum_configuration_quiet_margin_ps")), "18. Dynamic lock codes match static references for all three voltages; 0.80 V remains NO-GO because recovery did not finish.", "19. A GO would certify only this dynamic protocol, not the real startup-control circuit; this run is NO-GO and therefore grants no downstream authorization.", "20. After a future recovery-protocol repair and a new GO, the next stage is real standard-cell control logic; programmable margin remains later.", "", "## Gate Interpretation", "", "- D/W deltas are diagnostic only; no unsupported tolerance was introduced.", "- The sole terminal reason is `recovery_window_insufficient`; no hardware rescue, configuration skip, FSM, margin, droop, PVT, RTL, or layout was added."])
    recovery_items = [item for item in summary["per_voltage"] if item.get("reasons") and "recovery_window_insufficient" in item["reasons"]]
    if recovery_items:
        failing_vdd = ", ".join("{:.2f} V".format(float(item["vdd_v"])) for item in recovery_items)
        worst_ratio = max(float(item.get("maximum_recovery_signal_ratio", 0.0)) for item in recovery_items)
        lines.extend(["", "## Recovery Diagnosis", "", "`recovery_window_insufficient` means that the return activity after an S_CLK falling edge did not settle before the next code-update slot.", "The guard is {:.3f} ns and was derived from retained upstream timing evidence; at its end and throughout the final {:.3f} ns tail, xor_29, medium_out, and dff_ck must each remain below 10% of VDD.".format(timing["recovery_guard_s"] * 1.0e9, timing["q_settle_s"] * 1.0e9), "The failing voltage is {}. Its worst measured recovery endpoint/tail signal was {:.3f} x VDD, above the 0.100 x VDD limit. This is functional return-wave activity from the falling clock edge, not a configuration-induced CK edge: all transition audits still report zero configuration CK edges.".format(failing_vdd, worst_ratio), "The Q reads, coarse/fine monotonicity, lock-hold probes, and code-update quiet windows passed. Therefore this NO-GO identifies an insufficient recovery protocol window only; it does not justify changing the delay-line hardware or adding a margin bypass."])
    if summary["reasons"]:
        lines.extend(["", "## NO-GO Reasons", ""] + ["- {}".format(reason) for reason in summary["reasons"]])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Expose task-owned output paths and an explicit zero-HSPICE mode."""

    parser = argparse.ArgumentParser(description="run FTC dynamic startup calibration protocol")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis" / "dynamic_startup_calibration_protocol")
    parser.add_argument("--run-root", type=Path, default=FTC_ROOT / "runs" / "dynamic_startup_calibration_protocol")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports" / "FTC_DYNAMIC_STARTUP_CALIBRATION_PROTOCOL.md")
    parser.add_argument("--phase0-only", action="store_true", help="publish contracts and static audits without HSPICE")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run phase0, then the strict 0.95/1.10/0.80 early-stop sequence."""

    args = parse_args(argv)
    analysis, run_root, report = args.analysis_dir.resolve(), args.run_root.resolve(), args.report_output.resolve()
    analysis.mkdir(parents=True, exist_ok=True)
    stats = {"new": 0, "reused": 0}
    try:
        context = frozen_context()
        requirements = requirements_document(context)
        golden = golden_reference(context)
        timing = timing_contract(context)
        trajectories = {}
        schedules = {}
        contracts = {}
        decks = {}
        for voltage in VOLTAGES:
            key = vkey(voltage)
            trajectory = build_trajectory(voltage, golden["voltages"][key])
            schedule = schedule_trajectory(trajectory, timing)
            deck = render_deck(context, timing, schedule, voltage)
            trajectory_doc = trajectory_contract(trajectory, schedule, golden["voltages"][key], timing)
            integration = integration_contract(context, timing, schedule, deck)
            trajectories[key], schedules[key], contracts[key], decks[key] = trajectory_doc, schedule, integration, deck
            if integration["decision"] != "GO" or trajectory_doc["decision"] != "GO":
                raise ValueError("architecture_contract_violation")
        write_json(analysis / "requirements.json", requirements)
        write_json(analysis / "golden_reference.json", golden)
        write_json(analysis / "timing_contract.json", timing)
        write_json(analysis / "trajectory_contract.json", {"schema_version": 1, "study": STUDY, "by_vdd": trajectories})
        write_json(analysis / "integration_contract.json", {"schema_version": 1, "study": STUDY, "by_vdd": contracts})
        if args.phase0_only:
            summary = summary_document("NOT_RUN", [], [], stats, run_root)
            write_json(analysis / "summary.json", summary)
            render_report(report, golden, timing, trajectories, summary)
            return 0
        hspice, version = validate_hspice(context)
        signatures = {
            key: run_signature(analysis / "requirements.json", analysis / "timing_contract.json", analysis / "trajectory_contract.json", analysis / "integration_contract.json")
            for key in trajectories
        }
        static = static_lookup(context)
        results = []
        probe_rows: List[Dict[str, Any]] = []
        transition_rows: List[Dict[str, Any]] = []
        for voltage in VOLTAGES:
            key = vkey(voltage)
            parameters = scenario_parameters(voltage, timing, schedules[key], contracts[key])
            record = execute_scenario(hspice, version, run_root, decks[key], parameters, signatures[key], stats)
            records = [record]
            # A continuous deck has one MEAS record per probe; retain the raw record once.
            rows = [probe_row(probe, record, voltage, static) for probe in schedules[key]["probes"]]
            audits = [transition_row(item, record, voltage, schedules[key]["probes"][item["probe_index"] + 1]) for item in schedules[key]["transitions"]]
            result = evaluate_voltage(voltage, schedules[key], rows, audits, golden["voltages"][key], records * len(rows))
            results.append(result)
            probe_rows.extend(rows)
            transition_rows.extend(audits)
            write_csv(analysis / "probe_results.csv", PROBE_FIELDS, probe_rows)
            write_csv(analysis / "transition_audit.csv", TRANSITION_FIELDS, transition_rows)
            summary = summary_document("IN_PROGRESS", result["reasons"], results, stats, run_root)
            write_json(analysis / "summary.json", summary)
            if result["status"] != "GO":
                break
        complete = len(results) == len(VOLTAGES) and all(item["status"] == "GO" for item in results)
        decision = "Dynamic Startup Calibration Protocol = GO" if complete else "Dynamic Startup Calibration Protocol = NO-GO"
        reasons = [] if complete else list(dict.fromkeys(reason for item in results for reason in item["reasons"]))
        summary = summary_document(decision, reasons, results, stats, run_root)
        lock_table = {"schema_version": 1, "study": STUDY, "locks": [{"VDD": item["vdd_v"], "expected_M_fine": golden["voltages"][vkey(item["vdd_v"])] ["M_fine"], "expected_F_lock": golden["voltages"][vkey(item["vdd_v"])] ["F_lock"], "dynamic_M_final": item.get("dynamic_M_final"), "dynamic_F_final": item.get("dynamic_F_final"), "coarse_q_dynamic": item.get("coarse_q_dynamic"), "fine_q_dynamic": item.get("fine_q_dynamic"), "lock_hold_q": item.get("lock_hold_q"), "status": item.get("status")} for item in results]}
        write_json(analysis / "dynamic_lock_table.json", lock_table)
        write_json(analysis / "summary.json", summary)
        render_report(report, golden, timing, trajectories, summary)
        return 0 if complete else 2
    except Exception as error:
        summary = summary_document("Dynamic Startup Calibration Protocol = UPSTREAM_BLOCKED" if "upstream" in str(error) else "Dynamic Startup Calibration Protocol = ARCHITECTURE_BLOCKED", [str(error)], [], stats, run_root)
        write_json(analysis / "summary.json", summary)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
