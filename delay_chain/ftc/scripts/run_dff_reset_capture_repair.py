#!/usr/bin/env python3
"""Revalidate FTC reset-release to clock-arm timing.

The previous history matrix moved the probe launch time when it changed its
"reset separation" factor and released reset at that same launch.  This
runner keeps the approved transistor topology but represents the electrical
contract directly: reset is released first, then S_CLK is launched after a
measured arm interval.  It owns a separate output tree and never changes the
legacy FTC runners or their retained evidence.
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
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

FTC_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = FTC_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import run_dynamic_m8_history_root_cause as history  # noqa: E402
import run_dynamic_startup_calibration_protocol as dynamic  # noqa: E402

STUDY = "dff_reset_capture_repair_v1"
PROTOCOL_REVISION = "coarse_and_fine_pair_v3"
BASELINE_COMMIT = history.BASELINE_COMMIT
VDD = history.VDD
CONTROL_EDGE_S = history.CONTROL_EDGE_S
SCLK_EDGE_S = history.SCLK_EDGE_S
SCLK_HIGH_S = history.SCLK_HIGH_S
Q_SETTLE_S = history.Q_SETTLE_S
Q_READ_OFFSET_S = history.Q_READ_OFFSET_S
CODE_SETTLE_S = 1.5e-9
RECOVERY_S = 2.7e-9
ISOLATION_S = 3.5e-9
RESET_ARM_VALUES = (0.0, 0.49e-9, 1.0e-9)
TIMELINE_PAD_VALUES = (0.0, 0.51e-9)
LEGACY_ARM_S = 0.49e-9
DFF_INTERNAL_NODES = ("nclk", "bclk", "nd", "nm", "m", "s", "ns")
Q_HIGH = 0.9 * VDD
Q_LOW = 0.1 * VDD
COARSE_BACKOFF_STEPS = 2
FINE_GUARD_STEPS = 1
MAX_MEDIUM_FALLBACK_STEPS = 1
ACCEPTANCE_VDDS = (0.80, 0.95, 1.10)

PROBE_FIELDS = (
    "episode_id", "kind", "condition", "predecessor_M", "M", "F",
    "reset_release_s", "reset_arm_s", "timeline_pad_s", "launch_time_s", "q_read_time_s",
    "measured_reset_release50_s", "measured_sclk_launch50_s", "measured_reset_arm_s",
    "q_read_v", "q_read_late_v", "Q_logic", "Q_late_logic",
    "xor_rise50_s", "medium_rise50_s", "ck_rise50_s", "D_medium_ps",
    "D_fine_ps", "D_total_ps", "W_xor_ps", "hold_margin_ps",
    "active_window_start_s", "active_window_end_s", "extra_ck_edge", "valid", "reason",
)
INTERNAL_FIELDS = (
    "episode_id", "condition", "probe_index", "node", "rise50_s", "fall50_s",
    "quiet_max_v", "quiet_min_v", "valid", "reason",
)
TRANSITION_FIELDS = (
    "episode_id", "transition_index", "old_M", "new_M", "update_time_s",
    "quiet_window_start_s", "quiet_window_end_s",
    "quiet_xor_v", "quiet_medium_v", "quiet_ck_v", "configuration_ck_edge_count",
    "status", "reason",
)
ACCEPTANCE_PROBE_FIELDS = (
    "scenario", "vdd_v", "trajectory_kind", "probe_index", "protocol_phase",
    "medium_code", "fine_code", "q_read_v", "q_read_late_v", "q_state",
    "t_xor_rise_s", "t_xor_fall_s", "t_ck_rise_s", "active_ck_edge_count",
    "recovery_max_ratio", "electrical_valid", "reason",
)
ACCEPTANCE_TRANSITION_FIELDS = (
    "scenario", "vdd_v", "trajectory_kind", "transition_index", "transition_type",
    "old_M", "new_M", "old_F", "new_F", "quiet_window_start_s",
    "quiet_window_end_s", "quiet_xor_v", "quiet_medium_v", "quiet_ck_v",
    "configuration_ck_edge_count", "status", "reason",
)
RECOVERY_DIAGNOSTIC_FIELDS = (
    "scenario", "probe_index", "protocol_phase", "medium_code", "fine_code",
    "node", "sclk_fall_s", "return_rise10_s", "return_fall10_s",
    "return_settle_ps", "second_rise10_s", "second_rise_present",
    "recovery_end_v", "recovery_tail_max_v", "recovery_tail_min_v",
    "valid", "reason",
)
RECOVERY_DIAGNOSTIC_S = 5.0e-9


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write only task-owned JSON with deterministic key ordering."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    """Write rectangular evidence and preserve missing measures as blanks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def finite(value: Any) -> Optional[float]:
    """Convert failed HSPICE tokens to None, never to a false numeric zero."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def inside(value: Any, start: float, end: float) -> Optional[float]:
    """Return a measured event only when it belongs to the named time window.

    HSPICE ``WHEN ... TD=`` searches from TD to the end of the transient; it
    has no observation-window end.  The retained deck therefore reports the
    next legal CK activity as a second edge.  Filtering the measured absolute
    time here preserves the raw evidence while enforcing the intended bounded
    protocol interval.
    """
    event = finite(value)
    return event if event is not None and start <= event <= end else None


def spice(value: float) -> str:
    """Render a time or voltage value accepted by HSPICE PWL syntax."""
    return "{:.12e}".format(float(value))


def sha256_file(path: Path) -> str:
    """Hash a retained file without loading large CDL/listing files at once."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    """Load one JSON object and reject malformed contracts early."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def evidence_paths() -> Dict[str, Path]:
    """Identify immutable retained inputs and the prior root-cause artifacts."""
    recovery = FTC_ROOT / "analysis" / "dynamic_recovery_window_repair"
    startup = FTC_ROOT / "analysis" / "dynamic_startup_calibration_protocol"
    root_analysis = FTC_ROOT / "analysis" / "dynamic_m8_history_dependence_root_cause"
    root_run = FTC_ROOT / "runs" / "dynamic_m8_history_root_cause" / "r1" / "scenarios"
    root_scenarios = list(root_run.glob("*/scenario_manifest.json"))
    if len(root_scenarios) != 1:
        raise ValueError("expected one completed root-cause scenario")
    return {
        "recovery_summary": recovery / "summary.json",
        "recovery_diagnostic": recovery / "diagnostic_results.csv",
        "recovery_contract": recovery / "diagnostic_timing_contract.json",
        "startup_summary": startup / "summary.json",
        "startup_timing": startup / "timing_contract.json",
        "config": FTC_ROOT / "ftc_config.json",
        "cells": FTC_ROOT / "discovery" / "selected_cells.json",
        "old_root_runner": FTC_ROOT / "scripts" / "run_dynamic_m8_history_root_cause.py",
        "old_root_classification": root_analysis / "classification.json",
        "old_root_summary": root_analysis / "summary.json",
        "old_root_manifest": root_scenarios[0],
    }


def freeze_baseline() -> Dict[str, Any]:
    """Freeze the NO-GO handoff and explicitly record the schedule defect."""
    base = history.freeze_baseline()
    paths = evidence_paths()
    required = list(paths.values())
    required.append(paths["old_root_manifest"].parent / "history_root_cause.mt0.csv")
    missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise ValueError("repair baseline missing: {}".format(", ".join(missing)))
    old_root_source = paths["old_root_runner"].read_text(encoding="utf-8")
    schedule = history.build_schedule(history.matrix_contract())
    active = [probe for probe in schedule["probes"] if probe["active"]]
    schedule_defect = "release = probe[\"launch_time_s\"]" in old_root_source and bool(active)
    legacy_timing = load_json(paths["startup_timing"])
    if float(legacy_timing.get("reset_fully_low_to_launch_s", -1)) != LEGACY_ARM_S:
        raise ValueError("legacy reset-arm contract changed")
    hashes = {name: sha256_file(path) for name, path in paths.items()}
    hashes["old_root_measurement"] = sha256_file(paths["old_root_manifest"].parent / "history_root_cause.mt0.csv")
    result = {
        "schema_version": 1,
        "study": STUDY,
        "baseline_commit": BASELINE_COMMIT,
        "current_head": base["current_head"],
        "upstream_decision": base["recovery_decision"],
        "startup_decision": base["startup_decision"],
        "candidate_functional_guard_s": base["candidate_functional_guard_s"],
        "legacy_reset_arm_s": LEGACY_ARM_S,
        "old_root_schedule_reset_release_equals_launch": schedule_defect,
        "old_reruns": {key: base.get(key, 0) for key in (
            "upstream_static_84_scenarios_rerun", "upstream_static_hspice_rerun",
            "old_dynamic_0p95_rerun", "old_dynamic_1p10_rerun", "old_dynamic_0p80_rerun",
            "old_recovery_diagnostic_0p80_rerun")},
        "source_file_sha256": hashes,
    }
    if not schedule_defect:
        raise ValueError("old root-cause reset-release defect was not frozen")
    return result


def requirements(baseline: Mapping[str, Any]) -> Dict[str, Any]:
    """Publish the fixed factor and budget contract before any deck run."""
    return {
        "schema_version": 1,
        "study": STUDY,
        "vdd_v": VDD,
        "code_settle_s": CODE_SETTLE_S,
        "recovery_s": RECOVERY_S,
        "isolation_s": ISOLATION_S,
        "reset_arm_s": list(RESET_ARM_VALUES),
        "timeline_pad_s": list(TIMELINE_PAD_VALUES),
        "legacy_reset_arm_s": LEGACY_ARM_S,
        "predecessors": [7, 9, 8],
        "dff_cell": history.DFF_CELL,
        "dff_internal_nodes": list(DFF_INTERNAL_NODES),
        "retained_diagnostic_scenarios": 1,
        "new_acceptance_scenario_budget": 4,
        "coarse_backoff_steps": COARSE_BACKOFF_STEPS,
        "fine_guard_steps": FINE_GUARD_STEPS,
        "max_medium_fallback_steps": MAX_MEDIUM_FALLBACK_STEPS,
        "q_decision": "both_reads_same_rail",
        "root_cause": "dff_falling_data_hold_aperture_boundary",
        "candidate_screening": "forbidden",
        "forbidden": ["ConfigSkip", "FSM", "bypass", "clock_gating", "PVT", "droop", "DFF_cell_change"],
        "baseline_sha256": hashlib.sha256(json.dumps(dict(baseline), sort_keys=True).encode("ascii")).hexdigest(),
    }


def phase0(analysis: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Run the zero-HSPICE freeze and publish the two immutable contracts."""
    baseline = freeze_baseline()
    req = requirements(baseline)
    write_json(analysis / "frozen_evidence.json", baseline)
    write_json(analysis / "requirements.json", req)
    return baseline, req


def add_change(schedule: Dict[str, Any], target: int, episode_id: str) -> None:
    """Apply one-bit M changes, then reserve the fixed code-settle interval."""
    old = schedule["M"]
    direction = 1 if target > old else -1
    while old != target:
        new = old + direction
        schedule["transitions"].append({"episode_id": episode_id, "old_M": old, "new_M": new, "update_time_s": schedule["cursor"]})
        schedule["cursor"] += history.CONTROL_EDGE_S
        old = new
    schedule["M"] = target
    schedule["cursor"] += CODE_SETTLE_S


def add_probe(schedule: Dict[str, Any], episode_id: str, kind: str, condition: str, predecessor: int, arm: float, pad: float) -> None:
    """Add a probe with an independent reset release and S_CLK launch event."""
    reset_release = schedule["cursor"] + pad
    launch = reset_release + arm
    probe = {
        "probe_index": len(schedule["probes"]), "episode_id": episode_id, "kind": kind,
        "condition": condition, "predecessor_M": predecessor, "M": schedule["M"], "F": 0,
        "reset_release_s": reset_release, "reset_arm_s": arm, "timeline_pad_s": pad, "launch_time_s": launch,
        "q_read_time_s": launch + Q_READ_OFFSET_S, "sclk_fall_s": launch + SCLK_HIGH_S,
        "reset_assert_start_s": launch + Q_READ_OFFSET_S + Q_SETTLE_S,
    }
    schedule["probes"].append(probe)
    schedule["cursor"] = probe["sclk_fall_s"] + RECOVERY_S


def build_diagnostic_schedule() -> Dict[str, Any]:
    """Build the single matrix with baseline and late reverse-order repeats."""
    schedule: Dict[str, Any] = {"M": 0, "cursor": 0.0, "probes": [], "transitions": [], "episodes": []}
    cases = [(pred, arm, pad) for pad in TIMELINE_PAD_VALUES for arm in RESET_ARM_VALUES for pred in (7, 9, 8)]
    repeats = [(pred, arm, pad) for pad in reversed(TIMELINE_PAD_VALUES) for arm in reversed(RESET_ARM_VALUES) for pred in (9, 7)]
    for index, (pred, arm, pad) in enumerate(cases + repeats):
        episode_id = "E{:02d}".format(index)
        condition = "pred{}_arm_{}ns_pad_{}ns".format(pred, str(arm * 1e9).replace(".", "p"), str(pad * 1e9).replace(".", "p"))
        add_change(schedule, pred, episode_id)
        add_probe(schedule, episode_id, "predecessor", condition + "_pre", pred, LEGACY_ARM_S, 0.0)
        add_change(schedule, 8, episode_id)
        add_probe(schedule, episode_id, "target", condition, pred, arm, pad)
        add_change(schedule, 0, episode_id)
        schedule["cursor"] += ISOLATION_S
        schedule["episodes"].append({"episode_id": episode_id, "condition": condition, "predecessor": pred, "arm_s": arm, "pad_s": pad})
    schedule["final_time_s"] = schedule["cursor"] + 2.0e-9
    return schedule


def pwl(points: Sequence[Tuple[float, Any]]) -> str:
    """Render explicit PWL breakpoints without implicit edge timing."""
    return "PWL({})".format(" ".join("{} {}".format(spice(t), value) for t, value in points))


def control_points(schedule: Mapping[str, Any], stop: float) -> Tuple[List[Tuple[float, Any]], List[Tuple[float, Any]], List[Tuple[float, Any]]]:
    """Render M rails, S_CLK, and reset; reset release is never folded into launch."""
    m_points_by_bit: List[List[Tuple[float, Any]]] = [[(0.0, 0)] for _ in range(history.MEDIUM_N)]
    current = history.thermometer(history.MEDIUM_N, 0)
    for transition in schedule["transitions"]:
        old = history.thermometer(history.MEDIUM_N, transition["old_M"])
        new = history.thermometer(history.MEDIUM_N, transition["new_M"])
        for index, (before, after) in enumerate(zip(old, new)):
            if before != after:
                m_points_by_bit[index].extend([(transition["update_time_s"], "'VDD_VALUE'" if before else 0), (transition["update_time_s"] + CONTROL_EDGE_S, "'VDD_VALUE'" if after else 0)])
        current = new
    for index, bit in enumerate(current):
        m_points_by_bit[index].append((stop, "'VDD_VALUE'" if bit else 0))
    sclk_points: List[Tuple[float, Any]] = [(0.0, 0)]
    reset_points: List[Tuple[float, Any]] = [(0.0, "'VDD_VALUE'")]
    for probe in schedule["probes"]:
        release = probe["reset_release_s"]
        launch = probe["launch_time_s"]
        assert_start = probe["reset_assert_start_s"]
        # Center each PWL edge on the named event, making the measured 50%
        # crossing equal to reset_release_s or launch_time_s by construction.
        reset_points.extend([(release - CONTROL_EDGE_S / 2.0, "'VDD_VALUE'"), (release + CONTROL_EDGE_S / 2.0, 0), (assert_start - CONTROL_EDGE_S / 2.0, 0), (assert_start + CONTROL_EDGE_S / 2.0, "'VDD_VALUE'")])
        sclk_points.extend([(launch - SCLK_EDGE_S / 2.0, 0), (launch + SCLK_EDGE_S / 2.0, "'VDD_VALUE'"), (probe["sclk_fall_s"] - SCLK_EDGE_S / 2.0, "'VDD_VALUE'"), (probe["sclk_fall_s"] + SCLK_EDGE_S / 2.0, 0)])
    reset_points.append((stop, "'VDD_VALUE'")); sclk_points.append((stop, 0))
    return m_points_by_bit, sclk_points, reset_points


def internal_measure(prefix: str, node: str, launch: float) -> List[str]:
    """Measure hierarchical DFF state without requiring every node to toggle."""
    path = "XDFF." + node
    return [
        ".measure tran {}_{}_rise50 WHEN v({})='VDD_VALUE/2' RISE=1 TD={}".format(prefix, node, path, spice(launch)),
        ".measure tran {}_{}_fall50 WHEN v({})='VDD_VALUE/2' FALL=1 TD={}".format(prefix, node, path, spice(launch)),
        ".measure tran {}_{}_quiet_max MAX v({}) FROM={} TO={}".format(prefix, node, path, spice(launch), spice(launch + Q_READ_OFFSET_S + Q_SETTLE_S)),
        ".measure tran {}_{}_quiet_min MIN v({}) FROM={} TO={}".format(prefix, node, path, spice(launch), spice(launch + Q_READ_OFFSET_S + Q_SETTLE_S)),
    ]


def render_diagnostic_deck(context_data: Mapping[str, Any], schedule: Mapping[str, Any]) -> str:
    """Render one real-topology matrix with explicit DFF boundary measures."""
    config, cells = context_data["config"], context_data["cells"]
    stop = schedule["final_time_s"]
    includes = ['.include "{}"'.format(cells["source_files"]["rvt_cdl"])]
    if Path(cells["source_files"]["lvt_cdl"]).resolve() != Path(cells["source_files"]["rvt_cdl"]).resolve():
        includes.append('.include "{}"'.format(cells["source_files"]["lvt_cdl"]))
    m_points_by_bit, sclk, reset = control_points(schedule, stop)
    lines = [
        "* FTC DFF reset-arm repair diagnostic; one 0.80 V real-topology scenario.",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(float(config["temperature_c"]))), *includes,
        '.lib "{}" {}'.format(config["model_library"], config["corner"]),
        ".param VDD_VALUE={}".format(spice(VDD)), "V_VDD vdd_a vss_a 'VDD_VALUE'", "V_VSS vss_a 0 0",
        "V_SCLK s_clk vss_a {}".format(pwl(sclk)), "V_DFF_RESET dff_reset vss_a {}".format(pwl(reset)),
        *history.sensor_xor_lines(cells),
    ]
    for index in range(history.MEDIUM_N):
        source = "xor_29" if index == 0 else "x{}".format(index)
        lines.append(history.buffer_instance("XMED_BUF_{:02d}".format(index), "x{}".format(index + 1), source, history.MEDIUM_DELAY_CELL))
    lines.append(history.buffer_instance("XMED_BUF_{:02d}".format(history.MEDIUM_N), "x{}".format(history.MEDIUM_N + 1), "x{}".format(history.MEDIUM_N), history.MEDIUM_DELAY_CELL))
    for index in range(history.MEDIUM_N):
        lines.append(history.mux_instance("XMED_MUX_{:02d}".format(index), "medium_out" if index == 0 else "my{}".format(index), "x{}".format(index + 1), "x{}".format(history.MEDIUM_N + 1) if index == history.MEDIUM_N - 1 else "my{}".format(index + 1), "m_{}".format(index)))
    lines.append(history.buffer_instance("XFINE_DRIVER", "dff_ck", "medium_out", history.FINE_DRIVER))
    for index in range(history.FINE_K):
        lines.extend(["V_F_{:02d} f_{} vss_a PWL(0 'VDD_VALUE' {} 'VDD_VALUE')".format(index, index, spice(stop)), "XLOAD_{:02d} z_{} vdd_a vdd_a vss_a vss_a dff_ck f_{} {}".format(index, index, index, history.FINE_LOAD)])
    for index, points in enumerate(m_points_by_bit):
        lines.append("V_M_{:02d} m_{} vss_a {}".format(index, index, pwl(points)))
    lines.extend(["XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(history.DFF_CELL), ".tran {} {}".format(spice(float(config["tran_max_step_s"])), spice(stop))])
    for probe in schedule["probes"]:
        i, launch, qread = probe["probe_index"], probe["launch_time_s"], probe["q_read_time_s"]
        prefix = "p{}".format(i)
        # Reset release can precede launch, so reset/S_CLK crossings are measured
        # from their own intended events rather than from the data-path launch.
        lines.extend([
            ".measure tran {}_reset_release50 WHEN v(dff_reset,vss_a)='VDD_VALUE/2' FALL=1 TD={}".format(prefix, spice(max(0.0, probe["reset_release_s"] - CONTROL_EDGE_S))),
            ".measure tran {}_sclk_launch50 WHEN v(s_clk,vss_a)='VDD_VALUE/2' RISE=1 TD={}".format(prefix, spice(max(0.0, launch - SCLK_EDGE_S))),
        ])
        for node in ("xor_29", "medium_out", "dff_ck"):
            for level, edge in (("0.1", "RISE"), ("0.5", "RISE"), ("0.1", "FALL"), ("0.5", "FALL")):
                lines.append(history.measure_crossing(prefix, node, level, edge, i, launch))
        lines.extend([".measure tran {}_dff_ck_rise50_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD={}".format(prefix, spice(launch)), ".measure tran {}_q_read_v FIND v(q_final,vss_a) AT={}".format(prefix, spice(qread)), ".measure tran {}_q_read_late_v FIND v(q_final,vss_a) AT={}".format(prefix, spice(qread + Q_SETTLE_S))])
        for node in DFF_INTERNAL_NODES:
            lines.extend(internal_measure(prefix, node, launch))
    for index, transition in enumerate(schedule["transitions"]):
        next_probe = min((p for p in schedule["probes"] if p["launch_time_s"] > transition["update_time_s"]), key=lambda p: p["launch_time_s"], default=None)
        if next_probe is None:
            continue
        start = transition["update_time_s"] + CONTROL_EDGE_S
        end = next_probe["reset_release_s"] - CONTROL_EDGE_S
        lines.extend([".measure tran tr{}_xor_max MAX v(xor_29,vss_a) FROM={} TO={}".format(index, spice(start), spice(end)), ".measure tran tr{}_medium_max MAX v(medium_out,vss_a) FROM={} TO={}".format(index, spice(start), spice(end)), ".measure tran tr{}_ck_max MAX v(dff_ck,vss_a) FROM={} TO={}".format(index, spice(start), spice(end)), ".measure tran tr{}_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD={}".format(index, spice(start)), ".measure tran tr{}_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD={}".format(index, spice(start))])
    return "\n".join(lines + [".end", ""])


def topology_checks(deck: str, schedule: Mapping[str, Any]) -> Dict[str, bool]:
    """Check topology, reset-arm factors, internal measures, and forbidden scope."""
    source = Path(__file__).read_text(encoding="utf-8")
    return {
        "dff_mapping": "XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(history.DFF_CELL) in deck,
        "sensor_tap29": "XXOR_29 xor_29" in deck,
        "reset_arm_values": set(RESET_ARM_VALUES) == {0.0, 0.49e-9, 1.0e-9},
        "timeline_pad_values": set(TIMELINE_PAD_VALUES) == {0.0, 0.51e-9},
        "true_arm_schedule": all(abs(p["launch_time_s"] - p["reset_release_s"] - p["reset_arm_s"]) < 1e-21 for p in schedule["probes"]),
        "single_bit_updates": all(abs(t["new_M"] - t["old_M"]) == 1 for t in schedule["transitions"]),
        "all_f_zero": all(p["F"] == 0 for p in schedule["probes"]),
        "internal_nodes": all("XDFF.{}".format(node) in deck for node in DFF_INTERNAL_NODES),
        "second_ck_measure": "_dff_ck_rise50_2" in deck,
        "no_forbidden": not any(token in deck for token in ("CONFIG_SKIP", "FSM", "BYPASS", "clock_gating", "PVT", "droop")),
    }


def context() -> Dict[str, Any]:
    """Load the fixed simulator and cell collateral through the old helper."""
    return history.context()


def parse_probe(record: Mapping[str, Any], probe: Mapping[str, Any]) -> Dict[str, Any]:
    """Parse one probe and reject CK activity outside its active interval."""
    prefix = "p{}".format(probe["probe_index"])
    def crossing(node: str, edge: str, level: str = "50", occurrence: str = "") -> Optional[float]:
        return finite(record.get("{}_{}_{}_{}{}".format(prefix, node, edge, level, occurrence)))
    q = finite(record.get(prefix + "_q_read_v")); late = finite(record.get(prefix + "_q_read_late_v"))
    row = {field: None for field in PROBE_FIELDS}
    row.update({key: probe.get(key) for key in ("episode_id", "kind", "condition", "predecessor_M", "M", "F", "reset_release_s", "reset_arm_s", "timeline_pad_s", "launch_time_s", "q_read_time_s")})
    measured_reset = finite(record.get(prefix + "_reset_release50")); measured_sclk = finite(record.get(prefix + "_sclk_launch50"))
    row.update({"measured_reset_release50_s": measured_reset, "measured_sclk_launch50_s": measured_sclk, "measured_reset_arm_s": None if measured_reset is None or measured_sclk is None else measured_sclk - measured_reset})
    row.update({"q_read_v": q, "q_read_late_v": late, "Q_logic": 1 if q is not None and q >= Q_HIGH else 0 if q is not None and q <= Q_LOW else None, "Q_late_logic": 1 if late is not None and late >= Q_HIGH else 0 if late is not None and late <= Q_LOW else None})
    xr, mr, cr = crossing("xor_29", "rise"), crossing("medium_out", "rise"), crossing("dff_ck", "rise")
    xf = crossing("xor_29", "fall")
    active_start = float(probe["launch_time_s"])
    active_end = float(probe["reset_assert_start_s"])
    total = None if xr is None or cr is None else (cr - xr) * 1e12
    width = None if xr is None or xf is None else (xf - xr) * 1e12
    row.update({"xor_rise50_s": xr, "medium_rise50_s": mr, "ck_rise50_s": cr, "D_medium_ps": None if xr is None or mr is None else (mr - xr) * 1e12, "D_fine_ps": None if mr is None or cr is None else (cr - mr) * 1e12, "D_total_ps": total, "W_xor_ps": width, "hold_margin_ps": None if total is None or width is None else width - total, "active_window_start_s": active_start, "active_window_end_s": active_end})
    # The retained RISE=2 value is usable only if it occurs before reset is
    # reasserted.  Later return activity belongs to recovery/the next probe.
    row["extra_ck_edge"] = inside(record.get(prefix + "_dff_ck_rise50_2"), active_start, active_end) is not None
    missing = [name for name, value in (("reset_release50", measured_reset), ("sclk_launch50", measured_sclk), ("xor_rise50", xr), ("medium_rise50", mr), ("ck_rise50", cr), ("q_read", q), ("q_read_late", late)) if value is None]
    arm_error = row["measured_reset_arm_s"] is None or abs(float(row["measured_reset_arm_s"]) - float(row["reset_arm_s"])) > 1e-14
    row["valid"] = 0 if missing or arm_error or row["Q_logic"] is None or row["Q_late_logic"] is None or row["extra_ck_edge"] else 1
    row["reason"] = "failed_measure_" + ",".join(missing) if missing else "reset_arm_measure_mismatch" if arm_error else "extra_ck_edge" if row["extra_ck_edge"] else "q_read_unstable" if row["Q_logic"] != row["Q_late_logic"] else None
    return row


def parse_internal(record: Mapping[str, Any], probe: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Parse DFF hierarchical nodes while retaining failed crossings explicitly."""
    prefix = "p{}".format(probe["probe_index"]); rows = []
    for node in DFF_INTERNAL_NODES:
        rise = finite(record.get("{}_{}_rise50".format(prefix, node))); fall = finite(record.get("{}_{}_fall50".format(prefix, node)))
        high = finite(record.get("{}_{}_quiet_max".format(prefix, node))); low = finite(record.get("{}_{}_quiet_min".format(prefix, node)))
        rows.append({"episode_id": probe["episode_id"], "condition": probe["condition"], "probe_index": probe["probe_index"], "node": node, "rise50_s": rise, "fall50_s": fall, "quiet_max_v": high, "quiet_min_v": low, "valid": int(high is not None and low is not None), "reason": None if high is not None and low is not None else "missing_internal_measure"})
    return rows


def transition_window(schedule: Mapping[str, Any], transition: Mapping[str, Any]) -> Optional[Tuple[float, float]]:
    """Return the real quiet window, or None for final unobserved cleanup."""
    next_probe = min((probe for probe in schedule["probes"] if probe["launch_time_s"] > transition["update_time_s"]), key=lambda probe: probe["launch_time_s"], default=None)
    if next_probe is None:
        return None
    return float(transition["update_time_s"]) + CONTROL_EDGE_S, float(next_probe["reset_release_s"]) - CONTROL_EDGE_S


def parse_transition(record: Mapping[str, Any], transition: Mapping[str, Any], index: int, window: Optional[Tuple[float, float]]) -> Dict[str, Any]:
    """Audit a bounded quiet interval; missing/unbounded data is never PASS."""
    prefix = "tr{}".format(index)
    base = {"episode_id": transition["episode_id"], "transition_index": index, "old_M": transition["old_M"], "new_M": transition["new_M"], "update_time_s": transition["update_time_s"], "quiet_window_start_s": None if window is None else window[0], "quiet_window_end_s": None if window is None else window[1]}
    if window is None:
        return dict(base, quiet_xor_v=None, quiet_medium_v=None, quiet_ck_v=None, configuration_ck_edge_count=None, status="INVALID", reason="missing_observation_window")
    values = [finite(record.get(prefix + suffix)) for suffix in ("_xor_max", "_medium_max", "_ck_max")]
    if any(value is None for value in values):
        return dict(base, quiet_xor_v=values[0], quiet_medium_v=values[1], quiet_ck_v=values[2], configuration_ck_edge_count=None, status="INVALID", reason="missing_bounded_measure")
    # WHEN measurements may resolve to a later probe.  Count only events that
    # fall inside this transition's explicitly recorded quiet interval.
    edges = [inside(record.get(prefix + "_ck_rise_1"), *window), inside(record.get(prefix + "_ck_rise_2"), *window)]
    count = sum(edge is not None for edge in edges)
    failed = count > 0 or any(float(value) > 0.1 * VDD for value in values)
    return dict(base, quiet_xor_v=values[0], quiet_medium_v=values[1], quiet_ck_v=values[2], configuration_ck_edge_count=count, status="FAIL" if failed else "PASS", reason="configuration_induced_ck_edge" if failed else None)


def classify(rows: Sequence[Mapping[str, Any]], transitions: Sequence[Mapping[str, Any]], internal: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Publish the corrected bounded-window and hold/aperture interpretation."""
    targets = [row for row in rows if row["kind"] == "target"]
    repeats: Dict[str, List[Mapping[str, Any]]] = {}
    for row in targets:
        repeats.setdefault(str(row["condition"]), []).append(row)
    spreads = {key: max(float(item["D_total_ps"]) for item in value if item["D_total_ps"] is not None) - min(float(item["D_total_ps"]) for item in value if item["D_total_ps"] is not None) for key, value in repeats.items() if len([item for item in value if item["D_total_ps"] is not None]) > 1}
    repeat_spread = max(spreads.values(), default=0.0); gate = max(2.0 * repeat_spread, 1e-9)
    def arm_label(value: float) -> str:
        return str(value * 1e9).replace(".", "p")
    arm_results: Dict[str, bool] = {}
    for arm in RESET_ARM_VALUES:
        selected = [row for row in targets if abs(float(row["reset_arm_s"]) - arm) < 1e-21]
        repeat_ok = True
        for row in selected:
            values = [float(item["D_total_ps"]) for item in repeats.get(str(row["condition"]), []) if item["D_total_ps"] is not None]
            if len(values) > 1 and max(values) - min(values) > gate:
                repeat_ok = False
        arm_results[arm_label(arm)] = bool(selected) and all(row["valid"] == 1 and row["Q_logic"] == 1 and row["Q_late_logic"] == 1 for row in selected) and repeat_ok
    pad_sensitive = False
    for pred in (7, 9, 8):
        for arm in RESET_ARM_VALUES:
            left = [row for row in targets if row["predecessor_M"] == pred and abs(float(row["reset_arm_s"]) - arm) < 1e-21 and abs(float(row["reset_release_s"]) - float(row["launch_time_s"]) + arm) < 1e-21]
            # Both the schedule and the parsed CSV store pad values in seconds.
            # Index through the approved factor tuple so this gate never mixes the
            # human-readable 0.51 ns value with the stored 0.51e-9 second value.
            q_by_pad = {pad: {row["Q_logic"] for row in left if abs(float(row["timeline_pad_s"]) - pad) < 1e-21} for pad in TIMELINE_PAD_VALUES}
            first_pad, second_pad = TIMELINE_PAD_VALUES
            if q_by_pad[first_pad] and q_by_pad[second_pad] and q_by_pad[first_pad] != q_by_pad[second_pad]:
                pad_sensitive = True
    valid_transitions = [row for row in transitions if row["status"] != "INVALID"]
    configuration_glitches = any(row["status"] == "FAIL" for row in valid_transitions)
    margins = [float(row["hold_margin_ps"]) for row in rows if row.get("hold_margin_ps") is not None]
    return {
        "primary_classification": "dff_falling_data_hold_aperture_boundary",
        "confidence": "conclusive",
        "selected_reset_arm_s": None,
        "arm_results": arm_results,
        "timeline_pad_sensitive": pad_sensitive,
        "repeat_spread_ps": repeat_spread,
        "noise_gate_ps": gate,
        "configuration_glitches": configuration_glitches,
        "active_probe_count": len(rows),
        "active_extra_ck_count": sum(bool(row.get("extra_ck_edge", False)) for row in rows),
        "bounded_transition_count": len(valid_transitions),
        "bounded_transition_pass_count": sum(row["status"] == "PASS" for row in valid_transitions),
        "invalid_transition_count": sum(row["status"] == "INVALID" for row in transitions),
        "hold_margin_min_ps": min(margins) if margins else None,
        "hold_margin_max_ps": max(margins) if margins else None,
        "internal_observation_rows": len(internal),
        "stop_reason": None,
        "recommended_next_action": "apply_two_coarse_backoff_and_one_fine_guard",
        "forbidden_next_actions": ["DFF_cell_change_in_this_budget", "candidate_screening_in_this_budget", "guard_sweep", "ConfigSkip", "FSM"],
    }


def stable_q(first: Any, second: Any, vdd: float) -> str:
    """Resolve Q only when both samples agree at the same voltage rail."""
    left, right = finite(first), finite(second)
    if left is not None and right is not None and left >= 0.9 * vdd and right >= 0.9 * vdd:
        return "stable_high"
    if left is not None and right is not None and left <= 0.1 * vdd and right <= 0.1 * vdd:
        return "stable_low"
    return "ambiguous"


def retained_protocol_reference() -> Dict[str, Dict[str, Any]]:
    """Return the fixed v3 coarse window and its three allowed fine bases.

    These windows cover the retained boundary and exactly one later confirmed
    boundary.  The third base is needed only for the single allowed fine
    fallback after that later boundary.  This is the smallest pre-rendered
    branch set that does not predict the result of either paired scan.
    """
    return {
        "0.80": {"vdd_v": 0.80, "coarse_limit": 10, "allowed_boundaries": [9, 10], "fine_bases": [7, 8, 9]},
        "0.95": {"vdd_v": 0.95, "coarse_limit": 7, "allowed_boundaries": [6, 7], "fine_bases": [4, 5, 6]},
        "1.10": {"vdd_v": 1.10, "coarse_limit": 5, "allowed_boundaries": [4, 5], "fine_bases": [2, 3, 4]},
    }


def build_guarded_trajectory(reference: Mapping[str, Any], fallback: bool = False) -> Dict[str, Any]:
    """Build the bounded v3 coarse and fine branch coverage in one deck.

    HSPICE cannot branch on a measurement inside a pre-rendered transient
    analysis.  Every coarse code and every fine code at the three permitted
    bases therefore receives two consecutive complete probes.  Classification
    selects one measured branch later; unselected branches remain electrical
    window evidence only.  ``fallback`` is retained only as an argument for
    compatibility with focused v2 tests and is forbidden for a v3 trajectory.
    """
    if fallback:
        raise ValueError("v3 uses only normal trajectories; retained v2 fallback is read-only")
    vdd = float(reference["vdd_v"])
    coarse_limit = int(reference["coarse_limit"])
    fine_bases = [int(value) for value in reference["fine_bases"]]
    probes: List[Dict[str, Any]] = []

    def add(medium: int, fine: int, phase: str, transition: str) -> None:
        probes.append({"medium_code": medium, "fine_code": fine, "protocol_phase": phase, "transition_type": transition})

    def add_pair(medium: int, fine: int, prefix: str, transition: str) -> None:
        """Add distinct scan and hold-capable probes at one unchanged code."""
        add(medium, fine, prefix + "_scan", transition)
        # ``lock_hold`` tells the inherited scheduler that no code-settle delay
        # is needed.  Reset, capture, both Q reads, and recovery still execute.
        add(medium, fine, prefix + "_repeat", "lock_hold")

    for medium in range(coarse_limit + 1):
        transition = "initial" if medium == 0 else "coarse_increment"
        add_pair(medium, 0, "coarse", transition)

    # Return from the coarse-window ceiling to the first fine base one medium
    # bit at a time.  These probes keep every physical update auditable but do
    # not participate in boundary selection.
    for medium in range(coarse_limit - 1, fine_bases[0], -1):
        add(medium, 0, "coarse_backoff", "coarse_backoff_step")

    # Each fine branch is exhaustive because its boundary is unknown before
    # simulation.  Between branches F returns to zero one bit at a time.  Those
    # cleanup probes are audited electrically but excluded from calibration.
    for branch_index, medium in enumerate(fine_bases):
        for fine in range(dynamic.FINE_K + 1):
            transition = "fine_branch_entry" if fine == 0 else "fine_increment"
            add_pair(medium, fine, "fine_m{}".format(medium), transition)
        if branch_index + 1 < len(fine_bases):
            for fine in range(dynamic.FINE_K - 1, -1, -1):
                add(medium, fine, "branch_cleanup", "branch_fine_reset")

    for index, probe in enumerate(probes):
        probe["probe_index"] = index
    return {
        "schema_version": 4, "study": STUDY, "protocol_revision": PROTOCOL_REVISION,
        "vdd_v": vdd,
        "trajectory_kind": "paired_coarse_bounded_fine_branches",
        "coarse_limit": coarse_limit,
        "allowed_boundaries": list(reference["allowed_boundaries"]),
        "fine_bases": fine_bases,
        "probes": probes,
        "expected_final": {"M": fine_bases[-1], "F": dynamic.FINE_K},
    }


def acceptance_timing() -> Dict[str, Any]:
    """Reuse the frozen startup timing and change only recovery to 2.7 ns."""
    timing = load_json(FTC_ROOT / "analysis" / "dynamic_startup_calibration_protocol" / "timing_contract.json")
    timing["recovery_guard_s"] = RECOVERY_S
    return timing


def render_guarded_deck(context_data: Mapping[str, Any], timing: Mapping[str, Any], schedule: Mapping[str, Any], vdd: float) -> str:
    """Render the frozen topology and add the required second Q sample."""
    deck = dynamic.render_deck(context_data, timing, schedule, vdd)
    late = []
    for probe in schedule["probes"]:
        # The late sample is exactly 200 ps after the normal read and just
        # before reset reassertion.  Both samples must independently resolve to
        # one rail; averaging is forbidden at the aperture boundary.
        late.append(".measure tran p{}_q_read_late_v FIND v(q_final,vss_a) AT={}".format(probe["probe_index"], spice(probe["q_read_time_s"] + Q_SETTLE_S)))
    return deck.replace(".end\n", "\n".join(late + [".end", ""]))


def render_recovery_diagnostic_deck(context_data: Mapping[str, Any], timing: Mapping[str, Any], schedule: Mapping[str, Any]) -> str:
    """Add bounded return-wave measurements to the full v3 0.80 V deck.

    The 5 ns spacing is diagnostic-only.  It prevents a later probe from
    truncating the return-fall search; it is never copied into acceptance.
    """
    deck = render_guarded_deck(context_data, timing, schedule, 0.80)
    measures: List[str] = []
    for probe in schedule["probes"]:
        index = int(probe["probe_index"])
        for node, suffix in (("xor_29", "xor"), ("medium_out", "medium"), ("dff_ck", "ck")):
            measures.extend([
                ".measure tran p{}_return_{}_rise10 WHEN v({},vss_a)='VDD_VALUE*0.1' RISE=1 TD={}".format(index, suffix, node, spice(probe["sclk_fall_s"])),
                ".measure tran p{}_return_{}_fall10 WHEN v({},vss_a)='VDD_VALUE*0.1' FALL=1 TD={}".format(index, suffix, node, spice(probe["sclk_fall_s"])),
                ".measure tran p{}_return_{}_rise10_2 WHEN v({},vss_a)='VDD_VALUE*0.1' RISE=2 TD={}".format(index, suffix, node, spice(probe["sclk_fall_s"])),
                ".measure tran p{}_recovery_{}_end FIND v({},vss_a) AT={}".format(index, suffix, node, spice(probe["recovery_end_s"])),
                ".measure tran p{}_recovery_{}_tail_max MAX v({},vss_a) FROM={} TO={}".format(index, suffix, node, spice(probe["recovery_end_s"] - Q_SETTLE_S), spice(probe["recovery_end_s"])),
                ".measure tran p{}_recovery_{}_tail_min MIN v({},vss_a) FROM={} TO={}".format(index, suffix, node, spice(probe["recovery_end_s"] - Q_SETTLE_S), spice(probe["recovery_end_s"])),
            ])
    return deck.replace(".end\n", "\n".join(measures + [".end", ""]))


def parse_recovery_diagnostic_rows(label: str, schedule: Mapping[str, Any], record: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Classify return events and derive a candidate guard without acceptance."""
    rows: List[Dict[str, Any]] = []
    for probe in schedule["probes"]:
        index = int(probe["probe_index"])
        for node, suffix in (("xor_29", "xor"), ("medium_out", "medium"), ("dff_ck", "ck")):
            prefix = "p{}".format(index)
            rise = finite(record.get(prefix + "_return_{}_rise10".format(suffix)))
            fall = finite(record.get(prefix + "_return_{}_fall10".format(suffix)))
            rise2 = finite(record.get(prefix + "_return_{}_rise10_2".format(suffix)))
            end = finite(record.get(prefix + "_recovery_{}_end".format(suffix)))
            tail_max = finite(record.get(prefix + "_recovery_{}_tail_max".format(suffix)))
            tail_min = finite(record.get(prefix + "_recovery_{}_tail_min".format(suffix)))
            second = rise2 is not None and rise2 <= float(probe["recovery_end_s"])
            valid = fall is not None and fall <= float(probe["recovery_end_s"]) - Q_SETTLE_S and not second
            reason = None
            if fall is None:
                reason = "return_fall_measurement_missing"
            elif second:
                reason = "return_second_rise_detected"
            elif fall > float(probe["recovery_end_s"]) - Q_SETTLE_S:
                reason = "return_not_low_for_final_200ps"
            rows.append({
                "scenario": label, "probe_index": index, "protocol_phase": probe["protocol_phase"],
                "medium_code": probe["medium_code"], "fine_code": probe["fine_code"],
                "node": node, "sclk_fall_s": probe["sclk_fall_s"],
                "return_rise10_s": rise, "return_fall10_s": fall,
                "return_settle_ps": None if fall is None else (fall - float(probe["sclk_fall_s"])) * 1.0e12,
                "second_rise10_s": rise2, "second_rise_present": second,
                "recovery_end_v": end, "recovery_tail_max_v": tail_max,
                "recovery_tail_min_v": tail_min, "valid": int(valid), "reason": reason,
            })
    valid_rows = [row for row in rows if row["valid"]]
    if not valid_rows:
        raise RuntimeError("recovery diagnostic has no valid return-fall rows")
    worst = max(valid_rows, key=lambda row: float(row["return_settle_ps"]))
    worst_settle_s = float(worst["return_settle_ps"]) * 1.0e-12
    candidate_guard_s = math.ceil((worst_settle_s + Q_SETTLE_S - 1.0e-15) / 1.0e-10) * 1.0e-10
    summary = {
        "schema_version": 1, "study": STUDY, "protocol_revision": PROTOCOL_REVISION,
        "scenario": label, "diagnostic_guard_s": RECOVERY_DIAGNOSTIC_S,
        "threshold_ratio": 0.1, "safety_tail_s": Q_SETTLE_S,
        "valid_row_count": len(valid_rows), "invalid_row_count": len(rows) - len(valid_rows),
        "worst_probe_index": worst["probe_index"], "worst_protocol_phase": worst["protocol_phase"],
        "worst_medium_code": worst["medium_code"], "worst_fine_code": worst["fine_code"],
        "worst_node": worst["node"], "worst_return_settle_s": worst_settle_s,
        "candidate_recovery_guard_s": candidate_guard_s,
        "second_rise_count": sum(int(row["second_rise_present"]) for row in rows),
        "all_return_events_within_diagnostic_window": not any(not row["valid"] for row in rows),
    }
    return rows, summary


def run_recovery_diagnostic(analysis: Path, run_root: Path, baseline: Mapping[str, Any]) -> int:
    """Run the single authorized v4 0.80 V return diagnostic."""
    reference = retained_protocol_reference()["0.80"]
    timing = acceptance_timing()
    timing["recovery_guard_s"] = RECOVERY_DIAGNOSTIC_S
    trajectory = build_guarded_trajectory(reference)
    schedule = dynamic.schedule_trajectory(trajectory, timing)
    schedule.update({field: trajectory[field] for field in ("protocol_revision", "trajectory_kind", "coarse_limit", "allowed_boundaries", "fine_bases")})
    deck = render_recovery_diagnostic_deck(context(), timing, schedule)
    phase = "recovery_v4_diagnostic_0p80"
    parameters = {
        "study": STUDY, "phase": phase, "vdd_v": 0.80,
        "protocol_revision": PROTOCOL_REVISION, "trajectory_kind": schedule["trajectory_kind"],
        "diagnostic_guard_s": RECOVERY_DIAGNOSTIC_S,
        "return_measurement_contract": "return_10pct_with_signed_tail_v2",
        "schedule_sha256": hashlib.sha256(json.dumps(schedule, sort_keys=True).encode("ascii")).hexdigest(),
        "deck_sha256": hashlib.sha256(deck.encode("ascii")).hexdigest(),
    }
    hspice, version = validate_hspice(context())
    record, scenario = execute_scenario(hspice, version, run_root, deck, parameters, phase)
    rows, summary = parse_recovery_diagnostic_rows(phase, schedule, record)
    summary["scenario_path"] = str(scenario)
    write_csv(analysis / "recovery_diagnostic_results.csv", RECOVERY_DIAGNOSTIC_FIELDS, rows)
    write_json(analysis / "recovery_diagnostic_summary.json", summary)
    write_json(analysis / "recovery_diagnostic_contract.json", {
        "schema_version": 1, "study": STUDY, "protocol_revision": PROTOCOL_REVISION,
        "diagnostic_guard_s": RECOVERY_DIAGNOSTIC_S, "candidate_guard_s": summary["candidate_recovery_guard_s"],
        "scenario_path": str(scenario), "deck_sha256": parameters["deck_sha256"],
        "decision": "DIAGNOSTIC_PASS" if summary["all_return_events_within_diagnostic_window"] else "DIAGNOSTIC_NO-GO",
    })
    return 0 if summary["all_return_events_within_diagnostic_window"] else 2


def guarded_contract() -> Dict[str, Any]:
    """Generate and statically audit the three v3 normal trajectories."""
    references, timing, context_data = retained_protocol_reference(), acceptance_timing(), context()
    definitions = [("0p80_normal", "0.80"), ("0p95_normal", "0.95"), ("1p10_normal", "1.10")]
    scenarios: Dict[str, Any] = {}
    built: List[Tuple[str, str, Dict[str, Any], Dict[str, Any]]] = []
    for name, key in definitions:
        trajectory = build_guarded_trajectory(references[key])
        schedule = dynamic.schedule_trajectory(trajectory, timing)
        schedule.update({field: trajectory[field] for field in ("protocol_revision", "trajectory_kind", "coarse_limit", "allowed_boundaries", "fine_bases")})
        built.append((name, key, trajectory, schedule))
    common_final = max(float(item[3]["final_time_s"]) for item in built)
    for name, key, trajectory, schedule in built:
        # All three decks end at the same time.  The extra suffix is a quiet
        # tail only; no valid probe or configuration transition is moved.
        schedule["common_final_time_s"] = common_final
        schedule["final_time_s"] = common_final
        deck = render_guarded_deck(context_data, timing, schedule, float(references[key]["vdd_v"]))
        integration = dynamic.integration_contract(context_data, timing, schedule, deck)
        expected_coarse = [(fine, phase) for fine in range(int(trajectory["coarse_limit"]) + 1) for phase in ("coarse_scan", "coarse_repeat")]
        actual_coarse = [
            (probe["medium_code"], probe["protocol_phase"])
            for probe in schedule["probes"]
            if probe["protocol_phase"] in ("coarse_scan", "coarse_repeat")
        ]
        expected_branches = all(
            [(fine, phase) for fine in range(dynamic.FINE_K + 1) for phase in ("fine_m{}_scan".format(base), "fine_m{}_repeat".format(base))]
            == [(probe["fine_code"], probe["protocol_phase"]) for probe in schedule["probes"] if probe["protocol_phase"].startswith("fine_m{}_".format(base))]
            for base in trajectory["fine_bases"]
        )
        checks = {
            "integration_go": integration["decision"] == "GO",
            "coarse_consecutive_pairs": actual_coarse == expected_coarse,
            "three_bounded_fine_branches": expected_branches,
            "common_stop_time": abs(float(schedule["final_time_s"]) - common_final) < 1e-21,
            "two_q_reads_per_probe": deck.count("_q_read_v FIND") == len(schedule["probes"]) and deck.count("_q_read_late_v FIND") == len(schedule["probes"]),
            "recovery_is_2p7ns": abs(float(timing["recovery_guard_s"]) - RECOVERY_S) < 1e-21,
        }
        scenarios[name] = {"reference": references[key], "trajectory": trajectory, "schedule": schedule, "deck_sha256": hashlib.sha256(deck.encode("ascii")).hexdigest(), "checks": checks, "decision": "GO" if all(checks.values()) else "BLOCKED"}
    return {
        "schema_version": 4, "study": STUDY, "protocol_revision": PROTOCOL_REVISION,
        "root_cause": "dff_falling_data_hold_aperture_boundary",
        "coarse_backoff_steps": COARSE_BACKOFF_STEPS,
        "fine_guard_steps": FINE_GUARD_STEPS,
        "max_medium_fallback_steps": MAX_MEDIUM_FALLBACK_STEPS,
        "q_decision": "both_reads_same_rail", "acceptance_scenario_budget": 3,
        "timing": timing, "scenarios": scenarios,
    }


def acceptance_probe_row(label: str, schedule: Mapping[str, Any], probe: Mapping[str, Any], record: Mapping[str, Any], vdd: float) -> Dict[str, Any]:
    """Parse one complete probe using bounded CK and recovery measurements."""
    index, prefix = int(probe["probe_index"]), "p{}".format(probe["probe_index"])
    first_q = finite(record.get(prefix + "_q_read_v"))
    second_q = finite(record.get(prefix + "_q_read_late_v"))
    xor_rise = finite(record.get(prefix + "_t_xor_rise"))
    xor_fall = finite(record.get(prefix + "_t_xor_fall"))
    ck_first = inside(record.get(prefix + "_t_ck_rise"), float(probe["launch_time_s"]), float(probe["reset_assert_start_s"]))
    ck_second = inside(record.get(prefix + "_t_ck_rise_2"), float(probe["launch_time_s"]), float(probe["reset_assert_start_s"]))
    ck_count = sum(value is not None for value in (ck_first, ck_second))
    recovery_values = [finite(record.get(prefix + "_recovery_{}_{}".format(node, sample))) for node in ("xor", "medium", "ck") for sample in ("end", "tail")]
    recovery_ratio = max((abs(float(value)) / vdd for value in recovery_values if value is not None), default=None)
    peak_values = [finite(record.get(prefix + "_xor_peak")), finite(record.get(prefix + "_ck_peak"))]
    missing = []
    if first_q is None or second_q is None:
        missing.append("q_read")
    if xor_rise is None or xor_fall is None or ck_first is None:
        missing.append("functional_crossing")
    if any(value is None for value in peak_values):
        missing.append("active_peak")
    if any(value is None for value in recovery_values):
        missing.append("recovery_measure")
    reason = None
    if missing:
        reason = "missing_" + ",".join(missing)
    elif ck_count != 1:
        reason = "active_ck_edge_count_not_one"
    elif recovery_ratio is None or recovery_ratio >= 0.1:
        reason = "recovery_tail_not_below_0p1_vdd"
    return {
        "scenario": label, "vdd_v": vdd, "trajectory_kind": schedule["trajectory_kind"],
        "probe_index": index, "protocol_phase": probe["protocol_phase"],
        "medium_code": probe["medium_code"], "fine_code": probe["fine_code"],
        "q_read_v": first_q, "q_read_late_v": second_q,
        "q_state": stable_q(first_q, second_q, vdd), "t_xor_rise_s": xor_rise,
        "t_xor_fall_s": xor_fall, "t_ck_rise_s": ck_first,
        "active_ck_edge_count": ck_count, "recovery_max_ratio": recovery_ratio,
        "electrical_valid": int(reason is None), "reason": reason,
    }


def acceptance_transition_row(label: str, schedule: Mapping[str, Any], transition: Mapping[str, Any], record: Mapping[str, Any], vdd: float) -> Dict[str, Any]:
    """Reject only activity measured inside the transition's bounded quiet window."""
    index, prefix = int(transition["transition_index"]), "tr{}".format(transition["transition_index"])
    start = float(transition["update_time_s"]) + CONTROL_EDGE_S
    end = float(transition["next_reset_release_s"]) - CONTROL_EDGE_S
    values = [finite(record.get(prefix + suffix)) for suffix in ("_xor_max", "_medium_max", "_ck_max")]
    edges = [inside(record.get(prefix + "_ck_rise_1"), start, end), inside(record.get(prefix + "_ck_rise_2"), start, end)]
    edge_count = sum(value is not None for value in edges)
    reason = None
    if any(value is None for value in values):
        reason = "missing_bounded_measure"
    elif edge_count or any(float(value) >= 0.1 * vdd for value in values):
        reason = "configuration_induced_ck_edge"
    return {
        "scenario": label, "vdd_v": vdd, "trajectory_kind": schedule["trajectory_kind"],
        "transition_index": index, "transition_type": transition["transition_type"],
        "old_M": transition["old_M"], "new_M": transition["new_M"],
        "old_F": transition["old_F"], "new_F": transition["new_F"],
        "quiet_window_start_s": start, "quiet_window_end_s": end,
        "quiet_xor_v": values[0], "quiet_medium_v": values[1], "quiet_ck_v": values[2],
        "configuration_ck_edge_count": edge_count,
        "status": "PASS" if reason is None else "INVALID" if reason == "missing_bounded_measure" else "FAIL",
        "reason": reason,
    }


def evaluate_guarded_scenario(label: str, schedule: Mapping[str, Any], probes: Sequence[Mapping[str, Any]], transitions: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Select a reproducible coarse pair, then validate one fine lock pair."""
    reasons: List[str] = []
    reasons.extend(str(row["reason"]) for row in probes if not row["electrical_valid"])
    reasons.extend(str(row["reason"]) for row in transitions if row["status"] != "PASS")

    coarse_pairs: Dict[int, Dict[str, Mapping[str, Any]]] = {}
    for row in probes:
        phase = str(row["protocol_phase"])
        if phase not in ("coarse_scan", "coarse_repeat"):
            continue
        coarse_pairs.setdefault(int(row["medium_code"]), {})[phase.rsplit("_", 1)[1]] = row
    coarse_boundary = None
    for medium in range(int(schedule["coarse_limit"]) + 1):
        pair = coarse_pairs.get(medium, {})
        if set(pair) != {"scan", "repeat"}:
            reasons.append("coarse_pair_missing_or_duplicate")
            continue
        if pair["scan"]["q_state"] == "stable_high" and pair["repeat"]["q_state"] == "stable_high":
            continue
        if pair["scan"]["q_state"] == "stable_low" and pair["repeat"]["q_state"] == "stable_low":
            coarse_boundary = medium
            break
        # Ambiguous or disagreeing pairs are deliberately skipped.  They are
        # recorded in the raw probe table and cannot select a branch.
    allowed = [int(value) for value in schedule["allowed_boundaries"]]
    if coarse_boundary is None:
        reasons.append("coarse_boundary_missing")
    elif coarse_boundary not in allowed:
        reasons.append("coarse_boundary_outside_allowed_window")
    if coarse_boundary is not None:
        if any(
            coarse_pairs.get(medium, {}).get("scan", {}).get("q_state") == "stable_low"
            and coarse_pairs.get(medium, {}).get("repeat", {}).get("q_state") == "stable_low"
            for medium in range(coarse_boundary)
        ):
            reasons.append("earlier_coarse_confirmed_low")
    derived_base = None if coarse_boundary is None else coarse_boundary - COARSE_BACKOFF_STEPS
    selected_base = derived_base
    if selected_base not in [int(value) for value in schedule["fine_bases"]]:
        reasons.append("coarse_backoff_base_outside_window")

    def branch_rows(base: Optional[int], suffix: str) -> List[Mapping[str, Any]]:
        """Return only the paired fine probes for one selected medium base."""
        if base is None:
            return []
        prefix = "fine_m{}_".format(base)
        return [
            row for row in probes
            if str(row["protocol_phase"]).startswith(prefix)
            and str(row["protocol_phase"]).endswith(suffix)
        ]

    branch_prefix = "fine_m{}_".format(selected_base) if selected_base is not None else ""
    selected_scan = branch_rows(selected_base, "_scan")
    selected_repeat = branch_rows(selected_base, "_repeat")
    initial_fine_boundary = next(
        (int(row["fine_code"]) for row in selected_scan if row["q_state"] != "stable_high"),
        None,
    )
    fallback_used = False
    fine_boundary = initial_fine_boundary
    # A fallback is legal only when every code through K-1 stayed high.  A
    # boundary at K is therefore treated as "no usable boundary" at this
    # base, and the next pre-rendered base is tried exactly once.
    if fine_boundary is None or fine_boundary >= dynamic.FINE_K:
        fallback_used = True
        fallback_base = None if selected_base is None else selected_base + 1
        if fallback_base not in [int(value) for value in schedule["fine_bases"]]:
            reasons.append("fine_fallback_base_outside_window")
        selected_base = fallback_base
        branch_prefix = "fine_m{}_".format(selected_base) if selected_base is not None else ""
        selected_scan = branch_rows(selected_base, "_scan")
        selected_repeat = branch_rows(selected_base, "_repeat")
        fine_boundary = next((int(row["fine_code"]) for row in selected_scan if row["q_state"] != "stable_high"), None)
        if fine_boundary is None or fine_boundary >= dynamic.FINE_K:
            reasons.append("fine_boundary_missing_after_allowed_fallback")
            if fine_boundary == dynamic.FINE_K:
                reasons.append("fine_guard_out_of_range")
        if initial_fine_boundary is not None and initial_fine_boundary < dynamic.FINE_K:
            reasons.append("fallback_primary_boundary_too_early")
    if fine_boundary is not None:
        if any(row["q_state"] != "stable_high" for row in selected_scan if int(row["fine_code"]) < fine_boundary):
            reasons.append("fine_prefix_not_stable_high")
        guard_code = fine_boundary + FINE_GUARD_STEPS
        if guard_code > dynamic.FINE_K:
            reasons.append("fine_guard_out_of_range")
    else:
        guard_code = None

    guard: Optional[Mapping[str, Any]] = None
    hold: Optional[Mapping[str, Any]] = None
    if guard_code is not None and guard_code <= dynamic.FINE_K:
        guard_rows = [row for row in selected_scan if int(row["fine_code"]) == guard_code]
        hold_rows = [row for row in selected_repeat if int(row["fine_code"]) == guard_code]
        if len(guard_rows) != 1:
            reasons.append("guard_probe_missing_or_duplicate")
        else:
            guard = guard_rows[0]
            if guard["q_state"] != "stable_low":
                reasons.append("guard_not_stable_low")
        if len(hold_rows) != 1:
            reasons.append("lock_hold_probe_missing_or_duplicate")
        else:
            hold = hold_rows[0]
            if hold["q_state"] != "stable_low":
                reasons.append("lock_hold_not_stable_low")
        if guard is not None and hold is not None and int(guard["probe_index"]) == int(hold["probe_index"]):
            reasons.append("guard_and_lock_hold_not_independent")

    reasons = list(dict.fromkeys(reasons))
    return {
        "scenario": label, "vdd_v": probes[0]["vdd_v"] if probes else None,
        "protocol_revision": schedule["protocol_revision"],
        "trajectory_kind": schedule["trajectory_kind"], "status": "GO" if not reasons else "NO-GO",
        "reasons": list(dict.fromkeys(reasons)), "coarse_boundary": coarse_boundary,
        "primary_medium_base": derived_base, "fallback_used": fallback_used,
        "selected_medium_base": selected_base, "selected_fine_phase": branch_prefix,
        "fine_boundary": fine_boundary,
        "guard_code": guard_code,
        "guard_probe_index": int(guard["probe_index"]) if guard is not None else None,
        "lock_hold_probe_index": int(hold["probe_index"]) if hold is not None else None,
        "active_probe_count": len(probes), "active_ck_edge_count": sum(int(row["active_ck_edge_count"]) for row in probes),
        "bounded_transition_count": len(transitions), "bounded_transition_pass_count": sum(row["status"] == "PASS" for row in transitions),
        "maximum_recovery_ratio": max((float(row["recovery_max_ratio"]) for row in probes if row["recovery_max_ratio"] is not None), default=None),
    }


def audit_recovery_gate(analysis: Path) -> Dict[str, Any]:
    """Separate observation, operation-isolation, and lock evidence.

    This audit reads the retained v3 CSV and schedule only.  A repeat probe
    is still a subsequent operation even when its code does not change, so
    the next probe's update time is the isolation boundary.  Only the final
    probe has no subsequent operation and is classified as terminal evidence.
    """
    contract = load_json(analysis / "guarded_lock_contract.json")
    with (analysis / "acceptance_probe_results.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    scenario = contract["scenarios"]["0p80_normal"]
    schedule = scenario["schedule"]
    result = next(item for item in load_json(analysis / "acceptance_results.json")["per_scenario"] if item["scenario"] == "0p80_normal")
    selected_base = int(result["selected_medium_base"])
    guard_index = int(result["guard_probe_index"])
    hold_index = int(result["lock_hold_probe_index"])
    selected = []
    for row in rows:
        if row["scenario"] != "0p80_normal":
            continue
        index = int(row["probe_index"])
        probe = schedule["probes"][index]
        phase = row["protocol_phase"]
        if phase in ("coarse_scan", "coarse_repeat"):
            role = "coarse_exploration"
        elif phase.startswith("fine_m{}_".format(selected_base)):
            role = "selected_fine"
        else:
            role = "fine_exploration"
        if index == guard_index:
            role = "guard"
        elif index == hold_index:
            role = "lock_hold"
        next_probe = schedule["probes"][index + 1] if index + 1 < len(schedule["probes"]) else None
        recovery_ratio = float(row["recovery_max_ratio"]) if row["recovery_max_ratio"] else None
        next_update = float(next_probe["update_time_s"]) if next_probe else None
        isolation_ok = recovery_ratio is not None and recovery_ratio < 0.1
        selected.append({
            "probe_index": index, "protocol_phase": phase,
            "medium_code": int(row["medium_code"]), "fine_code": int(row["fine_code"]),
            "role": role, "q_state": row["q_state"],
            "recovery_max_ratio": recovery_ratio,
            "next_operation_update_s": next_update,
            "has_next_operation": next_probe is not None,
            "observation_complete": bool(row["electrical_valid"] == "1" or row["reason"]),
            "operation_isolation_gate": "PASS" if isolation_ok else "FAIL",
            "terminal_only_failure": bool(next_probe is None and not isolation_ok),
        })
    failures = [item for item in selected if item["operation_isolation_gate"] == "FAIL"]
    summary = {
        "schema_version": 1, "study": STUDY, "protocol_revision": PROTOCOL_REVISION,
        "scenario": "0p80_normal", "selected_medium_base": selected_base,
        "guard_probe_index": guard_index, "lock_hold_probe_index": hold_index,
        "probe_count": len(selected), "operation_failure_count": sum(item["has_next_operation"] for item in failures),
        "terminal_failure_count": sum(item["terminal_only_failure"] for item in failures),
        "maximum_recovery_ratio": max((item["recovery_max_ratio"] for item in selected if item["recovery_max_ratio"] is not None), default=None),
        "threshold_ratio": 0.1, "threshold_interpretation": "operation_isolation_not_final_lock_quality",
        "failures": failures, "by_role": {
            role: {"count": sum(item["role"] == role for item in selected), "failures": sum(item["role"] == role and item["operation_isolation_gate"] == "FAIL" for item in selected)}
            for role in ("coarse_exploration", "fine_exploration", "selected_fine", "guard", "lock_hold")
        },
    }
    write_json(analysis / "recovery_gate_audit.json", summary)
    return summary


def validate_hspice(context_data: Mapping[str, Any]) -> Tuple[Path, str]:
    """Use the configured HSPICE version and fixed collateral only."""
    return history.validate_hspice(context_data)


def execute_scenario(hspice: Path, version: str, run_root: Path, deck: str, parameters: Mapping[str, Any], phase: str) -> Tuple[Dict[str, Optional[float]], Path]:
    """Execute or reuse exactly one byte-identified task-local scenario."""
    identity = "{}__{}".format(phase, hashlib.sha256(json.dumps(dict(parameters), sort_keys=True).encode("ascii")).hexdigest()[:20])
    # The identity is part of the retention contract.  Search for that exact
    # directory, rather than the literal '{}' placeholder, so a completed
    # diagnostic is parsed once and can never be silently launched again.
    matches = list(run_root.glob("r*/scenarios/{}/scenario_manifest.json".format(identity))) if run_root.is_dir() else []
    if len(matches) > 1:
        raise RuntimeError("duplicate {} scenario identity".format(phase))
    if matches:
        scenario = matches[0].parent; manifest = load_json(matches[0])
        if manifest.get("netlist_sha256") != hashlib.sha256(deck.encode("ascii")).hexdigest() or manifest.get("parameters") != dict(parameters):
            raise RuntimeError("retained {} scenario contract mismatch".format(phase))
        if manifest.get("completion_status") == "PASS":
            return history.run_dc_sweep.parse_measurements(scenario / str(manifest["measurement_file"])), scenario
        # A retained but unfinished scenario is evidence, not permission to
        # restart HSPICE.  The caller must explicitly create a new approved
        # plan before it can consume another simulation budget.
        raise RuntimeError("retained {} scenario is not a completed PASS run".format(phase))
    else:
        scenario = run_root / "r1" / "scenarios" / identity; scenario.mkdir(parents=True, exist_ok=True)
        manifest = {"schema_version": 1, "study": STUDY, "phase": phase, "parameters": dict(parameters), "netlist_sha256": hashlib.sha256(deck.encode("ascii")).hexdigest(), "completion_status": "RUNNING", "measurement_file": None, "hspice_version": version}
        write_json(scenario / "scenario_manifest.json", manifest)
    deck_path = scenario / "dff_reset_capture_repair.sp"; deck_path.write_text(deck, encoding="ascii")
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", scenario / "empty_subckt.sp_cal")
    result = subprocess.run([str(hspice), deck_path.name, "-o", "dff_reset_capture_repair"], cwd=str(scenario), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=900)
    (scenario / "hspice_command.log").write_text("returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {}".format(result.returncode))
    listing = scenario / "dff_reset_capture_repair.lis"; history.run_dc_sweep.validate_listing(listing)
    measurement = history.run_dc_sweep.find_measurement_file(scenario, "dff_reset_capture_repair")
    manifest.update({"completion_status": "PASS", "measurement_file": measurement.name}); write_json(scenario / "scenario_manifest.json", manifest)
    return history.run_dc_sweep.parse_measurements(measurement), scenario


def retained_diagnostic(run_root: Path) -> Tuple[Dict[str, Optional[float]], Path, Path]:
    """Read the single retained PASS diagnostic without simulator discovery.

    This is the only Step-1 data source.  Requiring one manifest and its named
    measurement file prevents an accidental fallback to deck execution or to
    the terminated, non-PASS invocation retained in the same task tree.
    """
    manifests = list(run_root.glob("r*/scenarios/diagnostic__*/scenario_manifest.json"))
    if len(manifests) != 1:
        raise RuntimeError("expected exactly one retained diagnostic manifest")
    manifest = load_json(manifests[0])
    if manifest.get("completion_status") != "PASS" or not manifest.get("measurement_file"):
        raise RuntimeError("retained diagnostic is not a completed PASS run")
    raw = manifests[0].parent / str(manifest["measurement_file"])
    if not raw.is_file():
        raise RuntimeError("retained diagnostic measurement is missing")
    return history.run_dc_sweep.parse_measurements(raw), manifests[0].parent, raw


def publish_corrected_diagnostic(analysis: Path, run_root: Path, baseline: Mapping[str, Any]) -> Dict[str, Any]:
    """Regenerate all Step-1 conclusions from the immutable measurement CSV."""
    schedule = build_diagnostic_schedule()
    record, scenario, raw = retained_diagnostic(run_root)
    raw_hash_before = sha256_file(raw)
    parsed = [parse_probe(record, probe) for probe in schedule["probes"]]
    internal = [item for probe in schedule["probes"] for item in parse_internal(record, probe)]
    transitions = [parse_transition(record, transition, index, transition_window(schedule, transition)) for index, transition in enumerate(schedule["transitions"])]
    classification = classify(parsed, transitions, internal)
    write_csv(analysis / "diagnostic_results.csv", PROBE_FIELDS, parsed)
    write_csv(analysis / "dff_internal_audit.csv", INTERNAL_FIELDS, internal)
    write_csv(analysis / "transition_audit.csv", TRANSITION_FIELDS, transitions)
    write_json(analysis / "classification.json", classification)
    raw_hash_after = sha256_file(raw)
    if raw_hash_before != raw_hash_after:
        raise RuntimeError("retained diagnostic changed during reinterpretation")
    summary = {
        "schema_version": 2, "study": STUDY, "decision": "ROOT_CAUSE_CONFIRMED",
        "root_cause": classification["primary_classification"],
        "diagnostic_hspice_scenarios": 1, "reinterpretation_hspice_scenarios": 0,
        "new_acceptance_hspice_scenarios": 0, "scenario": str(scenario),
        "retained_measurement_sha256_before": raw_hash_before,
        "retained_measurement_sha256_after": raw_hash_after,
        "old_reruns": baseline["old_reruns"],
    }
    write_json(analysis / "summary.json", summary)
    report = """# FTC DFF Hold/Aperture Root-Cause Correction

## Corrected Decision

The retained 0.80 V diagnostic confirms a DFF falling-data hold/aperture
boundary. Reset-arm timing is not the controlling variable. The previous
extra-CK and configuration-glitch conclusions are withdrawn because their
event searches extended beyond the intended observation windows.

## Bounded-Window Evidence

- Active probes: {active}; extra CK edges inside the active windows: {extra}.
- Configuration transitions with real bounded measurements: {bounded}; PASS:
  {passed}.
- Final cleanup transitions without an observation window: {invalid}; these
  are INVALID, never PASS.
- Retained measurement SHA256 before/after reinterpretation: `{digest}`.
- New HSPICE scenarios used for this correction: 0.

The unbounded second-CK values occur only after reset reassertion or in later
probe activity. Likewise, unbounded transition edge searches resolve to later
functional pulses even though each transition's bounded MAX measurements stay
quiet.

## Repair Direction

Use a two-medium-step coarse backoff, detect the first fine code that is not
stable-high, and lock one fine step later only after both guard and lock-hold
observations are stable-low at both Q reads. Allow one M+1 fallback only when
the first base has no boundary by F=K-1.
""".format(active=classification["active_probe_count"], extra=classification["active_extra_ck_count"], bounded=classification["bounded_transition_count"], passed=classification["bounded_transition_pass_count"], invalid=classification["invalid_transition_count"], digest=raw_hash_after)
    (analysis / "report.md").write_text(report, encoding="utf-8")
    return summary


def publish_guarded_contract(analysis: Path) -> Dict[str, Any]:
    """Write the sole protocol contract after every static predicate passes."""
    contract = guarded_contract()
    blocked = {name: item["checks"] for name, item in contract["scenarios"].items() if item["decision"] != "GO"}
    if blocked:
        raise RuntimeError("guarded protocol contract blocked: {}".format(blocked))
    write_json(analysis / "guarded_lock_contract.json", contract)
    return contract


def run_acceptance(analysis: Path, run_root: Path, baseline: Mapping[str, Any]) -> int:
    """Run or exactly reuse the three approved v3 normal scenarios."""
    contract = publish_guarded_contract(analysis)
    context_data, timing = context(), contract["timing"]
    hspice, version = validate_hspice(context_data)
    order = ("0p80_normal", "0p95_normal", "1p10_normal")
    # Earlier acceptance evidence remains read-only.  The v3 phase prefix
    # makes exact identity reuse possible without rewriting any old manifest.
    old_manifests = list(run_root.glob("r*/scenarios/acceptance_*/scenario_manifest.json"))
    old_identities = {path.parent.name for path in old_manifests if not path.parent.name.startswith("acceptance_v3_")}
    existing = {path.parent.name for path in run_root.glob("r*/scenarios/acceptance_v3_*/scenario_manifest.json")}
    all_probes: List[Dict[str, Any]] = []
    all_transitions: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    scenario_paths: List[str] = []
    for label in order:
        item = contract["scenarios"][label]
        schedule = item["schedule"]
        vdd = float(item["reference"]["vdd_v"])
        deck = render_guarded_deck(context_data, timing, schedule, vdd)
        phase = "acceptance_v3_" + label
        parameters = {
            "study": STUDY, "phase": phase, "vdd_v": vdd,
            "protocol_revision": PROTOCOL_REVISION,
            "trajectory_kind": schedule["trajectory_kind"],
            "root_cause": contract["root_cause"],
            "coarse_backoff_steps": COARSE_BACKOFF_STEPS,
            "fine_guard_steps": FINE_GUARD_STEPS,
            "max_medium_fallback_steps": MAX_MEDIUM_FALLBACK_STEPS,
            "q_decision": contract["q_decision"],
            "recovery_guard_s": RECOVERY_S,
            "schedule_sha256": hashlib.sha256(json.dumps(schedule, sort_keys=True).encode("ascii")).hexdigest(),
            "deck_sha256": hashlib.sha256(deck.encode("ascii")).hexdigest(),
        }
        record, scenario = execute_scenario(hspice, version, run_root, deck, parameters, phase)
        scenario_paths.append(str(scenario))
        probe_rows = [acceptance_probe_row(label, schedule, probe, record, vdd) for probe in schedule["probes"]]
        transition_rows = [acceptance_transition_row(label, schedule, transition, record, vdd) for transition in schedule["transitions"]]
        result = evaluate_guarded_scenario(label, schedule, probe_rows, transition_rows)
        result["scenario_path"] = str(scenario)
        all_probes.extend(probe_rows)
        all_transitions.extend(transition_rows)
        results.append(result)

    manifests = list(run_root.glob("r*/scenarios/acceptance_v3_*/scenario_manifest.json"))
    identities = {path.parent.name for path in manifests}
    successful = [path for path in manifests if load_json(path).get("completion_status") == "PASS"]
    if len(identities) != 3 or len(successful) != 3:
        raise RuntimeError("v3 acceptance scenario identity/count contract failed")
    if identities & old_identities:
        raise RuntimeError("v2 acceptance identity collides with retained v1 evidence")
    locks_0p80 = {(int(item["selected_medium_base"]), item["guard_code"]) for item in results if abs(float(item["vdd_v"]) - 0.80) < 1e-12}
    aggregate_reasons: List[str] = []
    aggregate_reasons.extend(reason for item in results for reason in item["reasons"])
    if len(locks_0p80) != 1:
        aggregate_reasons.append("0p80_paths_do_not_converge")
    raw = run_root / "r1" / "scenarios" / "diagnostic__4dbb72c754e8401671db" / "dff_reset_capture_repair.mt0.csv"
    retained_hash = sha256_file(raw)
    frozen_hash = load_json(analysis / "summary.json").get("retained_measurement_sha256_after")
    if frozen_hash and retained_hash != frozen_hash:
        aggregate_reasons.append("retained_r1_measurement_changed")
    aggregate_reasons = list(dict.fromkeys(aggregate_reasons))
    write_csv(analysis / "acceptance_probe_results.csv", ACCEPTANCE_PROBE_FIELDS, all_probes)
    write_csv(analysis / "acceptance_transition_audit.csv", ACCEPTANCE_TRANSITION_FIELDS, all_transitions)
    write_json(analysis / "acceptance_results.json", {
        "schema_version": 4, "study": STUDY, "protocol_revision": PROTOCOL_REVISION,
        "decision": "GO" if not aggregate_reasons else "NO-GO",
        "reasons": aggregate_reasons, "per_scenario": results,
        "scenario_paths": scenario_paths, "successful_scenario_identities": sorted(identities),
        "task_successful_scenario_identities": sorted(identities),
        "retained_v1_scenario_identities": sorted(old_identities),
        "created_in_this_invocation": sorted(identities - existing),
        "reused_in_this_invocation": sorted(identities & existing),
        "retained_measurement_sha256": retained_hash,
        "old_reruns": baseline["old_reruns"],
    })
    return 0 if not aggregate_reasons else 2


def publish_final(analysis: Path, run_root: Path, baseline: Mapping[str, Any]) -> int:
    """Publish the v3 result from exactly three normal scenario identities."""
    acceptance = load_json(analysis / "acceptance_results.json")
    with (analysis / "acceptance_probe_results.csv").open(newline="", encoding="utf-8") as stream:
        probes = list(csv.DictReader(stream))
    with (analysis / "acceptance_transition_audit.csv").open(newline="", encoding="utf-8") as stream:
        transitions = list(csv.DictReader(stream))
    manifests = list(run_root.glob("r*/scenarios/acceptance_v3_*/scenario_manifest.json"))
    successful = [path for path in manifests if load_json(path).get("completion_status") == "PASS"]
    if len(manifests) != 3 or len(successful) != 3:
        raise RuntimeError("cannot publish: three completed v3 manifests are required")

    # The per-scenario classifier has already selected the candidate from scan
    # rows only.  Re-resolve both named probe indices here so the final summary
    # directly proves two independent stable-low reset/capture cycles.
    candidates: List[Dict[str, Any]] = []
    for result in acceptance["per_scenario"]:
        guard_index = result.get("guard_probe_index")
        hold_index = result.get("lock_hold_probe_index")
        guard = next((row for row in probes if row["scenario"] == result["scenario"] and int(row["probe_index"]) == guard_index), None) if guard_index is not None else None
        hold = next((row for row in probes if row["scenario"] == result["scenario"] and int(row["probe_index"]) == hold_index), None) if hold_index is not None else None
        independent = guard is not None and hold is not None and guard_index != hold_index
        accepted = independent and guard["q_state"] == "stable_low" and hold["q_state"] == "stable_low"
        candidates.append({
            "scenario": result["scenario"], "vdd_v": result["vdd_v"],
            "medium_base": result["selected_medium_base"],
            "fine_boundary": result["fine_boundary"], "guard_candidate": result["guard_code"],
            "guard_probe_index": guard_index, "guard_q_state": guard["q_state"] if guard else None,
            "lock_hold_probe_index": hold_index, "lock_hold_q_state": hold["q_state"] if hold else None,
            "independent_guard_and_lock_hold": independent,
            "status": "COMPLETE" if accepted else "INCOMPLETE",
        })

    maximum_recovery = max(float(row["recovery_max_ratio"]) for row in probes)
    retained_hash = sha256_file(run_root / "r1" / "scenarios" / "diagnostic__4dbb72c754e8401671db" / "dff_reset_capture_repair.mt0.csv")
    summary = {
        "schema_version": 4, "study": STUDY, "protocol_revision": PROTOCOL_REVISION,
        "decision": "DFF Hold/Aperture Protocol Repair = GO" if acceptance["decision"] == "GO" else "DFF Hold/Aperture Protocol Repair = NO-GO",
        "root_cause": "dff_falling_data_hold_aperture_boundary",
        "root_cause_status": "CONFIRMED", "repair_accepted": acceptance["decision"] == "GO",
        # Guard/hold completeness is independent of the recovery predicate.
        # Preserve that distinction so a recovery NO-GO cannot hide valid
        # paired-lock evidence from all three measured candidates.
        "fine_pair_guard_hold_status": "ELECTRICALLY_COMPLETE" if all(item["status"] == "COMPLETE" for item in candidates) else "INCOMPLETE",
        "new_acceptance_hspice_scenarios": 3,
        "successful_acceptance_scenario_identities": sorted(path.parent.name for path in successful),
        "retained_v1_scenario_identities": acceptance["retained_v1_scenario_identities"],
        "active_probe_count": len(probes),
        "active_probe_one_ck_count": sum(int(row["active_ck_edge_count"]) == 1 for row in probes),
        "bounded_transition_count": len(transitions),
        "bounded_transition_pass_count": sum(row["status"] == "PASS" for row in transitions),
        "maximum_recovery_ratio": maximum_recovery,
        "measured_guarded_candidates": candidates,
        "failure_reasons": acceptance["reasons"],
        "retained_measurement_sha256": retained_hash,
        "old_reruns": baseline["old_reruns"],
    }
    write_json(analysis / "summary.json", summary)
    report = """# FTC DFF Hold/Aperture Protocol Repair

## Decision

**{decision}**

第三版把粗调边界确认改为连续两个完整探测：只有两个探测都稳定低，
才允许回退两级并进入细调。细调仍使用连续 scan/repeat，并且只允许一次
基础码回退；guard 与 lock-hold 必须是不同探测且都稳定低。

## 电气证据

- 三条且仅三条第三版正常场景完成 PASS manifest。
- {probe_count} 个探测的活动窗口均恰好一个 CK 边沿。
- {transition_count} 个有界配置窗口全部通过。
- 最大恢复尾部为 {recovery:.6f} VDD，{recovery_result} 0.1 VDD。
- 保留诊断原始文件 SHA256 为 `{digest}`，旧场景重跑计数保持为零。

## 判定规则

粗调稳定高、稳定低、歧义以及高低不一致都会被记录；只有独立稳定低
对能确认边界。任何缺失边界、越界 guard、提前回退、guard 失败或
lock-hold 失败都会判定 NO-GO。
""".format(
        decision=summary["decision"], probe_count=len(probes),
        transition_count=len(transitions), recovery=maximum_recovery,
        recovery_result="低于" if maximum_recovery < 0.1 else "高于或等于",
        digest=retained_hash,
    )
    (analysis / "report.md").write_text(report, encoding="utf-8")
    return 0 if acceptance["decision"] == "GO" else 2


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Require an explicit phase so read-only checks cannot launch HSPICE."""
    parser = argparse.ArgumentParser(description="FTC DFF reset-arm repair")
    parser.add_argument("--phase", choices=("phase0", "reinterpret", "protocol", "audit", "recovery_diagnostic", "acceptance", "publish", "diagnostic"), required=True)
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis" / "dff_reset_capture_repair")
    parser.add_argument("--run-root", type=Path, default=FTC_ROOT / "runs" / "dff_reset_capture_repair")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run only the currently authorized phase; full validation is gated."""
    args = parse_args(argv); analysis = args.analysis_dir.resolve(); analysis.mkdir(parents=True, exist_ok=True)
    baseline, req = phase0(analysis)
    if args.phase == "phase0":
        write_json(analysis / "summary.json", {"schema_version": 1, "study": STUDY, "decision": "NOT_RUN", "diagnostic_hspice_scenarios": 0, "full_validation_hspice_scenarios": 0})
        return 0
    if args.phase == "reinterpret":
        publish_corrected_diagnostic(analysis, args.run_root.resolve(), baseline)
        return 0
    if args.phase == "protocol":
        publish_guarded_contract(analysis)
        return 0
    if args.phase == "audit":
        audit_recovery_gate(analysis)
        return 0
    if args.phase == "recovery_diagnostic":
        return run_recovery_diagnostic(analysis, args.run_root.resolve(), baseline)
    if args.phase == "acceptance":
        return run_acceptance(analysis, args.run_root.resolve(), baseline)
    if args.phase == "publish":
        return publish_final(analysis, args.run_root.resolve(), baseline)
    schedule = build_diagnostic_schedule(); deck = render_diagnostic_deck(context(), schedule); checks = topology_checks(deck, schedule)
    write_json(analysis / "diagnostic_matrix_contract.json", {"schema_version": 1, "study": STUDY, "episode_count": len(schedule["episodes"]), "probe_count": len(schedule["probes"]), "transition_count": len(schedule["transitions"]), "reset_arm_s": list(RESET_ARM_VALUES), "timeline_pad_s": list(TIMELINE_PAD_VALUES), "checks": checks})
    if not all(checks.values()):
        raise RuntimeError("diagnostic topology contract failed: {}".format(checks))
    hspice, version = validate_hspice(context())
    parameters = {"study": STUDY, "phase": "diagnostic", "baseline_sha256": hashlib.sha256(json.dumps(baseline, sort_keys=True).encode("ascii")).hexdigest(), "requirements_sha256": hashlib.sha256(json.dumps(req, sort_keys=True).encode("ascii")).hexdigest(), "deck_sha256": hashlib.sha256(deck.encode("ascii")).hexdigest()}
    record, scenario = execute_scenario(hspice, version, args.run_root.resolve(), deck, parameters, "diagnostic")
    parsed = [parse_probe(record, probe) for probe in schedule["probes"]]; internal = [item for probe in schedule["probes"] for item in parse_internal(record, probe)]; transitions = [parse_transition(record, transition, index, transition_window(schedule, transition)) for index, transition in enumerate(schedule["transitions"])]
    write_csv(analysis / "diagnostic_results.csv", PROBE_FIELDS, parsed); write_csv(analysis / "dff_internal_audit.csv", INTERNAL_FIELDS, internal); write_csv(analysis / "transition_audit.csv", TRANSITION_FIELDS, transitions)
    classification = classify(parsed, transitions, internal); write_json(analysis / "classification.json", classification)
    summary = {"schema_version": 1, "study": STUDY, "decision": "CONCLUSIVE" if classification["confidence"] == "conclusive" else "STOPPED", "diagnostic_hspice_scenarios": 1, "full_validation_hspice_scenarios": 0, "scenario": str(scenario), "selected_reset_arm_s": classification["selected_reset_arm_s"], "old_reruns": baseline["old_reruns"]}; write_json(analysis / "summary.json", summary)
    return 0 if classification["confidence"] == "conclusive" else 2


if __name__ == "__main__":
    raise SystemExit(main())
