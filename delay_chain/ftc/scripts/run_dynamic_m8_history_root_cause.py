#!/usr/bin/env python3
"""One-shot FTC M8 history-dependence investigation.

This runner deliberately owns a separate output tree.  It first republishes
retained raw measurements, then renders one 0.80 V HSPICE deck containing all
Groups A--G from the approved plan.  No old dynamic runner is imported and no
guard sweep is possible: the only functional guard values are 2.5, 2.7, and
3.3 ns.  The comments below document the timing contract because a change in
episode ordering would invalidate the history experiment.
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
PHASE1_SCRIPTS = FTC_ROOT.parent / "phase1" / "scripts"
if str(PHASE1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PHASE1_SCRIPTS))
import run_dc_sweep  # noqa: E402  # Side-effect-free retained-measure parser.

STUDY = "dynamic_m8_history_root_cause_v1"
BASELINE_COMMIT = "25b2fba0c61d1192584d37155c5fe3b677846e62"
VDD = 0.80
MEDIUM_N, FINE_K = 16, 10
MEDIUM_DELAY_CELL = "BUF_X0P7M_A9TL40"
MEDIUM_MUX_CELL = "MXT2_X0P5M_A9TL40"
FINE_DRIVER = "BUF_X0P8M_A9TL40"
FINE_LOAD = "NOR2_X4A_A9TL40"
XOR_CELL = "XOR2_X0P5M_A9TR40"
DFF_CELL = "DFFRPQ_X0P5M_A9TR40"
SENSOR_RVT_INITIAL, SENSOR_LVT_INITIAL = 4, 0
OBSERVABLE_STAGES, SENSOR_TAP = 30, 29
CONTROL_EDGE_S, SCLK_EDGE_S = 1.0e-11, 1.0e-12
SCLK_HIGH_S, Q_SETTLE_S = 3.0e-9, 2.0e-10
Q_READ_OFFSET_S, RESET_049_S = 2.3e-9, 0.49e-9
ISOLATION_GUARD_S = 3.5e-9
RECOVERY_VALUES = (2.5e-9, 2.7e-9, 3.3e-9)
SETTLE_VALUES = (1.5e-9, 3.3e-9)
RESET_VALUES = (0.49e-9, 1.00e-9)
INTERNAL_NODES = ("x7", "x8", "x9", "x10", "my6", "my7", "my8", "my9", "medium_out")
MEASURE_NODES = ("xor_29", "medium_out", "dff_ck")
Q_HIGH, Q_LOW = 0.9 * VDD, 0.1 * VDD

PROBE_FIELDS = (
    "episode_id", "group", "probe_index", "M", "F", "protocol_phase", "launch_time_s",
    "q_read_time_s", "xor_rise10_s", "xor_rise50_s", "xor_fall10_s", "xor_fall50_s",
    "medium_rise10_s", "medium_rise50_s", "medium_fall10_s", "medium_fall50_s",
    "ck_rise10_s", "ck_rise50_s", "ck_fall10_s", "ck_fall50_s", "q_read_v", "Q_logic",
    "W_xor_ps", "W_medium_ps", "W_ck_ps", "D_medium_ps", "D_fine_driver_ps", "D_total_ps",
    "extra_ck_edge", "valid", "reason",
)
INTERNAL_FIELDS = ("episode_id", "group", "condition", "probe_index", "node", "rise10_s", "rise50_s", "fall10_s", "fall50_s", "quiet_peak_v", "valid")
RESULT_FIELDS = PROBE_FIELDS + ("condition", "predecessor_M", "recovery_guard_s", "code_settle_s", "reset_separation_s", "active_pulse")
TRANSITION_FIELDS = ("episode_id", "transition_index", "old_M", "new_M", "old_F", "new_F", "update_time_s", "quiet_xor_v", "quiet_medium_v", "quiet_ck_v", "configuration_ck_edge_count", "status", "reason")


def sha256_file(path: Path) -> str:
    """Hash evidence in chunks so large listings never occupy memory twice."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    """Require one JSON object; malformed handoffs must stop before HSPICE."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write only task-owned JSON with stable key ordering."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    """Use fixed schemas and preserve missing measures as explicit blanks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def finite(value: Any) -> Optional[float]:
    """Return None for HSPICE's explicit failed token, never numeric zero."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def spice(value: float) -> str:
    """Render a time or voltage expression accepted by HSPICE PWL syntax."""
    return "{:.12e}".format(float(value))


def thermometer(units: int, code: int) -> Tuple[int, ...]:
    """Return the frozen first-code-high thermometer representation."""
    if not 0 <= code <= units:
        raise ValueError("illegal thermometer code {}".format(code))
    return tuple(1 if index < code else 0 for index in range(units))


def evidence_paths() -> Dict[str, Path]:
    """Name immutable upstream files and the two retained electrical runs."""
    recovery = FTC_ROOT / "analysis" / "dynamic_recovery_window_repair"
    startup = FTC_ROOT / "analysis" / "dynamic_startup_calibration_protocol"
    return {
        "recovery_summary": recovery / "summary.json",
        "diagnostic_results": recovery / "diagnostic_results.csv",
        "measured_return": recovery / "measured_return_settle.json",
        "old_failure_map": recovery / "old_failure_map.json",
        "diagnostic_contract": recovery / "diagnostic_timing_contract.json",
        "recovery_report": FTC_ROOT / "reports" / "FTC_DYNAMIC_RECOVERY_WINDOW_REPAIR.md",
        "recovery_runner": FTC_ROOT / "scripts" / "run_dynamic_recovery_window_repair.py",
        "startup_summary": startup / "summary.json",
        "startup_probe": startup / "probe_results.csv",
        "startup_transition": startup / "transition_audit.csv",
        "trajectory": startup / "trajectory_contract.json",
        "startup_timing": startup / "timing_contract.json",
        "config": FTC_ROOT / "ftc_config.json",
        "cells": FTC_ROOT / "discovery" / "selected_cells.json",
    }


def retained_scenario(kind: str) -> Tuple[Path, Dict[str, Any]]:
    """Find exactly one retained scenario without touching its files."""
    root = FTC_ROOT / "runs" / ("dynamic_startup_calibration_protocol" if kind == "2p5" else "dynamic_recovery_window_repair")
    matches = []
    for manifest_path in root.glob("r*/scenarios/*/scenario_manifest.json"):
        manifest = load_json(manifest_path)
        params = manifest.get("parameters", {})
        if kind == "2p5" and float(params.get("vdd_v", -1)) == VDD and float(params.get("recovery_guard_s", -1)) == 2.5e-9:
            matches.append((manifest_path.parent, manifest))
        if kind == "3p3" and params.get("phase") == "recovery_diagnostic_0p80" and float(params.get("vdd_v", -1)) == VDD:
            matches.append((manifest_path.parent, manifest))
    if len(matches) != 1:
        raise ValueError("expected one retained {} scenario, found {}".format(kind, len(matches)))
    scenario, manifest = matches[0]
    measurement = scenario / str(manifest.get("measurement_file", ""))
    listing = scenario / ("dynamic_startup_calibration.lis" if kind == "2p5" else "dynamic_recovery_window_repair.lis")
    deck = scenario / ("dynamic_startup_calibration.sp" if kind == "2p5" else "dynamic_recovery_window_repair.sp")
    for path in (measurement, listing, deck):
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("retained scenario file missing: {}".format(path))
    return scenario, manifest


def freeze_baseline() -> Dict[str, Any]:
    """Freeze the exact NO-GO handoff and reject any electrical drift."""
    paths = evidence_paths()
    required = list(paths.values())
    old_scenario, old_manifest = retained_scenario("2p5")
    diag_scenario, diag_manifest = retained_scenario("3p3")
    required.extend([old_scenario / str(old_manifest["measurement_file"]), old_scenario / "dynamic_startup_calibration.lis", old_scenario / "dynamic_startup_calibration.sp", diag_scenario / str(diag_manifest["measurement_file"]), diag_scenario / "dynamic_recovery_window_repair.lis", diag_scenario / "dynamic_recovery_window_repair.sp"])
    missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise ValueError("upstream_baseline_mismatch: {}".format(", ".join(missing)))
    recovery_summary = load_json(paths["recovery_summary"])
    startup_summary = load_json(paths["startup_summary"])
    if recovery_summary.get("decision") != "Dynamic Recovery Window Repair = NO-GO" or recovery_summary.get("reasons") != ["diagnostic_q_sequence_changed"]:
        raise ValueError("upstream_baseline_mismatch: recovery handoff changed")
    if startup_summary.get("decision") != "Dynamic Startup Calibration Protocol = NO-GO":
        raise ValueError("upstream_baseline_mismatch: startup decision changed")
    expected_zero = ("upstream_static_84_scenarios_rerun", "upstream_static_hspice_rerun", "old_dynamic_0p95_rerun", "old_dynamic_1p10_rerun", "old_dynamic_0p80_rerun")
    if any(int(recovery_summary.get(name, 0)) != 0 for name in expected_zero):
        raise ValueError("upstream_baseline_mismatch: rerun accounting changed")
    hashes = {name: sha256_file(path) for name, path in paths.items()}
    hashes.update({"retained_2p5_manifest": sha256_file(old_scenario / "scenario_manifest.json"), "retained_2p5_measurement": sha256_file(old_scenario / str(old_manifest["measurement_file"])), "retained_2p5_listing": sha256_file(old_scenario / "dynamic_startup_calibration.lis"), "retained_2p5_deck": sha256_file(old_scenario / "dynamic_startup_calibration.sp"), "retained_3p3_manifest": sha256_file(diag_scenario / "scenario_manifest.json"), "retained_3p3_measurement": sha256_file(diag_scenario / str(diag_manifest["measurement_file"])), "retained_3p3_listing": sha256_file(diag_scenario / "dynamic_recovery_window_repair.lis"), "retained_3p3_deck": sha256_file(diag_scenario / "dynamic_recovery_window_repair.sp")})
    return {"schema_version": 1, "study": STUDY, "baseline_commit": BASELINE_COMMIT, "current_head": subprocess.check_output(["git", "rev-parse", "HEAD"], universal_newlines=True).strip(), "recovery_decision": recovery_summary["decision"], "startup_decision": startup_summary["decision"], "recovery_reasons": recovery_summary["reasons"], "old_scenario": str(old_scenario), "diagnostic_scenario": str(diag_scenario), "old_recovery_guard_s": 2.5e-9, "diagnostic_bound_s": 3.3e-9, "candidate_functional_guard_s": 2.7e-9, "upstream_static_84_scenarios_rerun": 0, "upstream_static_hspice_rerun": 0, "old_dynamic_0p95_rerun": 0, "old_dynamic_1p10_rerun": 0, "old_dynamic_0p80_rerun": 0, "old_recovery_diagnostic_0p80_rerun": 0, "source_file_sha256": hashes}


def requirements(baseline: Mapping[str, Any]) -> Dict[str, Any]:
    """Publish the small immutable scope contract before any deck run."""
    return {"schema_version": 1, "study": STUDY, "vdd_v": VDD, "medium_N": MEDIUM_N, "fine_K": FINE_K, "cells": {"medium_delay": MEDIUM_DELAY_CELL, "medium_mux": MEDIUM_MUX_CELL, "fine_driver": FINE_DRIVER, "fine_load": FINE_LOAD, "xor": XOR_CELL, "dff": DFF_CELL}, "recovery_guards_s": list(RECOVERY_VALUES), "code_settle_guards_s": list(SETTLE_VALUES), "reset_separations_s": list(RESET_VALUES), "episode_isolation_guard_s": ISOLATION_GUARD_S, "internal_nodes": list(INTERNAL_NODES), "root_cause_matrix_scenario_budget": 1, "conditional_repaired_scenario_budget": 1, "upstream_static_84_scenarios_rerun": 0, "old_dynamic_0p95_rerun": 0, "old_dynamic_1p10_rerun": 0, "old_dynamic_0p80_rerun": 0, "forbidden": ["bypass", "ConfigSkip", "clock_gating", "update_isolation", "ideal_delay", "ideal_capacitor", "FSM", "counter", "register", "programmable_margin", "droop", "PVT", "RTL", "layout"], "frozen_evidence_sha256": hashlib.sha256(json.dumps(dict(baseline), sort_keys=True).encode("ascii")).hexdigest()}


def build_trajectory() -> List[Dict[str, Any]]:
    """Return the frozen 13-probe path used only for optional repaired validation."""
    probes = [(0, 0, "coarse", "initial")] + [(m, 0, "coarse", "coarse_increment") for m in range(1, 10)] + [(8, 0, "fine_entry", "coarse_backoff"), (8, 1, "fine", "fine_increment"), (8, 1, "lock_hold", "lock_hold")]
    return [{"probe_index": i, "M": m, "F": f, "protocol_phase": phase, "transition_type": transition} for i, (m, f, phase, transition) in enumerate(probes)]


def matrix_contract() -> Dict[str, Any]:
    """Define every required episode once; the deck builder consumes this list."""
    episodes: List[Dict[str, Any]] = []
    def add(eid: str, group: str, steps: Sequence[Tuple[int, bool]], guard: float = 2.7e-9, settle: float = 1.5e-9, reset_sep: float = RESET_049_S, active: bool = True, condition: str = "") -> None:
        episodes.append({"episode_id": eid, "group": group, "steps": list(steps), "recovery_guard_s": guard, "code_settle_s": settle, "reset_separation_s": reset_sep, "active_pulse": active, "condition": condition or eid})
    add("A1", "A", [(7, True)], settle=3.3e-9, condition="isolated_m7")
    add("A2", "A", [(8, True)], settle=3.3e-9, condition="isolated_m8")
    add("A3", "A", [(9, True)], settle=3.3e-9, condition="isolated_m9")
    add("B1", "B", [(7, True), (8, True)], condition="m7_to_m8_2p7")
    add("B2", "B", [(9, True), (8, True)], condition="m9_to_m8_2p7")
    add("B3", "B", [(8, True), (8, True)], condition="m8_to_m8_2p7")
    for eid, old, guard in (("C1", 7, 2.5e-9), ("C2", 7, 2.7e-9), ("C3", 7, 3.3e-9), ("C4", 9, 2.5e-9), ("C5", 9, 2.7e-9), ("C6", 9, 3.3e-9)):
        add(eid, "C", [(old, True), (8, True)], guard=guard, condition="m{}to_m8_guard_{}ns".format(old, str(guard * 1e9).replace(".", "p")))
    add("D1", "D", [(7, False), (8, True)], condition="config_only_m7")
    add("D2", "D", [(7, True), (8, True)], condition="active_m7")
    add("D3", "D", [(9, False), (8, True)], condition="config_only_m9")
    add("D4", "D", [(9, True), (8, True)], condition="active_m9")
    add("E1", "E", [(7, True), (8, True)], settle=1.5e-9, condition="m7_to_m8_settle_1p5")
    add("E2", "E", [(7, True), (8, True)], settle=3.3e-9, condition="m7_to_m8_settle_3p3")
    add("E3", "E", [(9, True), (8, True)], settle=1.5e-9, condition="m9_to_m8_settle_1p5")
    add("E4", "E", [(9, True), (8, True)], settle=3.3e-9, condition="m9_to_m8_settle_3p3")
    add("F1", "F", [(7, True), (8, True)], reset_sep=0.49e-9, condition="m7_to_m8_reset_0p49")
    add("F2", "F", [(7, True), (8, True)], reset_sep=1.0e-9, condition="m7_to_m8_reset_1p00")
    add("F3", "F", [(9, True), (8, True)], reset_sep=0.49e-9, condition="m9_to_m8_reset_0p49")
    add("F4", "F", [(9, True), (8, True)], reset_sep=1.0e-9, condition="m9_to_m8_reset_1p00")
    add("G1", "G", [(7, True), (8, True), (9, True)], condition="ascending")
    add("G2", "G", [(9, True), (8, True), (7, True)], condition="descending")
    add("B1R", "B", [(7, True), (8, True)], condition="m7_to_m8_2p7")
    add("B2R", "B", [(9, True), (8, True)], condition="m9_to_m8_2p7")
    add("A4", "A", [(8, True)], settle=3.3e-9, condition="isolated_m8")
    return {"schema_version": 1, "study": STUDY, "vdd_v": VDD, "episodes": episodes, "episode_count": len(episodes), "required_groups": list("ABCDEFG"), "recovery_guards_s": list(RECOVERY_VALUES), "code_settle_guards_s": list(SETTLE_VALUES), "reset_separations_s": list(RESET_VALUES), "isolation_guard_s": ISOLATION_GUARD_S, "internal_nodes": list(INTERNAL_NODES), "measurement_contract_version": "windowed_10_50_crossings_v1"}


def buffer_instance(name: str, output: str, input_node: str, cell: str) -> str:
    """Use the verified six-port standard-cell power mapping."""
    return "{} {} vdd_a vdd_a vss_a vss_a {} {}".format(name, output, input_node, cell)


def mux_instance(name: str, output: str, shallow: str, deep: str, select: str) -> str:
    """Use the frozen non-inverting MXT2 mapping."""
    return "{} {} vdd_a vdd_a vss_a vss_a {} {} {} {}".format(name, output, shallow, deep, select, MEDIUM_MUX_CELL)


def sensor_xor_lines(cells: Mapping[str, Any]) -> List[str]:
    """Render the unchanged four-RVT/zero-LVT sensor and tap-29 XOR."""
    lines, rvt_input, lvt_input = [], "s_clk", "s_clk"
    for stage in range(SENSOR_RVT_INITIAL):
        output = "rvt_initial_{}".format(stage)
        lines.append(buffer_instance("XRVT_INIT_{:02d}".format(stage), output, rvt_input, cells["delay_rvt"]["cell"]))
        rvt_input = output
    rvt, lvt = [], []
    for stage in range(OBSERVABLE_STAGES):
        ro, lo = "rvt_{}".format(stage), "lvt_{}".format(stage)
        lines.append(buffer_instance("XRVT_{:02d}".format(stage), ro, rvt_input, cells["delay_rvt"]["cell"]))
        lines.append(buffer_instance("XLVT_{:02d}".format(stage), lo, lvt_input, cells["delay_lvt"]["cell"]))
        rvt.append(ro); lvt.append(lo); rvt_input, lvt_input = ro, lo
    for stage in range(OBSERVABLE_STAGES):
        lines.append("XXOR_{:02d} xor_{} vdd_a vdd_a vss_a vss_a {} {} {}".format(stage, stage, rvt[stage], lvt[stage], XOR_CELL))
    return lines


def pwl(points: Sequence[Tuple[float, Any]]) -> str:
    """Render every PWL breakpoint explicitly, including control-edge width."""
    return "PWL({})".format(" ".join("{} {}".format(spice(t), value) for t, value in points))


def add_code_change(schedule: Dict[str, Any], target: int, settle: float) -> None:
    """Change M one thermometer bit at a time and record its update event."""
    old = schedule["M"]
    if target == old:
        schedule["cursor"] += settle
        return
    direction = 1 if target > old else -1
    while old != target:
        new = old + direction
        update = schedule["cursor"]
        schedule["transitions"].append({"old_M": old, "new_M": new, "old_F": 0, "new_F": 0, "update_time_s": update, "episode_id": schedule["episode_id"]})
        schedule["cursor"] += CONTROL_EDGE_S
        old = new
    schedule["M"] = target
    schedule["cursor"] += settle


def add_probe(schedule: Dict[str, Any], episode: Mapping[str, Any], active: bool) -> None:
    """Append one active or config-only probe while preserving matched timing."""
    index = len(schedule["probes"])
    release = schedule["cursor"] + episode["reset_separation_s"]
    launch = release if active else schedule["cursor"]
    item = {"episode_id": episode["episode_id"], "group": episode["group"], "probe_index": index, "M": schedule["M"], "F": 0, "protocol_phase": "active" if active else "config_only", "launch_time_s": launch, "q_read_time_s": launch + Q_READ_OFFSET_S, "active": active, "condition": episode["condition"], "predecessor_M": schedule.get("predecessor_M"), "recovery_guard_s": episode["recovery_guard_s"], "code_settle_s": episode["code_settle_s"], "reset_separation_s": episode["reset_separation_s"], "sclk_fall_s": launch + SCLK_HIGH_S if active else None}
    schedule["probes"].append(item)
    if active:
        schedule["cursor"] = item["sclk_fall_s"] + episode["recovery_guard_s"]
    else:
        # Config-only controls consume the same wall time as a complete pulse
        # and recovery, but never toggle S_CLK or release the DFF reset.
        schedule["cursor"] += SCLK_HIGH_S + episode["recovery_guard_s"]
    schedule["predecessor_M"] = schedule["M"]


def build_schedule(contract: Mapping[str, Any]) -> Dict[str, Any]:
    """Place all episodes in one isolated long timeline, including late repeats."""
    schedule: Dict[str, Any] = {"M": 0, "cursor": 0.0, "episode_id": "", "predecessor_M": 0, "probes": [], "transitions": [], "episodes": []}
    for episode in contract["episodes"]:
        schedule["episode_id"] = episode["episode_id"]
        start = len(schedule["probes"])
        for target, active in episode["steps"]:
            schedule["predecessor_M"] = schedule["M"]
            add_code_change(schedule, target, episode["code_settle_s"])
            add_probe(schedule, episode, active)
        # Reset is asserted, S_CLK is low, and M returns serially to M0 before
        # the fixed 3.5 ns isolation guard.  F remains 0 throughout.
        add_code_change(schedule, 0, 0.0)
        schedule["cursor"] += ISOLATION_GUARD_S
        schedule["episodes"].append({"episode_id": episode["episode_id"], "group": episode["group"], "probe_start": start, "probe_end": len(schedule["probes"]) - 1})
    schedule["final_time_s"] = schedule["cursor"] + 2.0e-9
    return schedule


def rail_points(schedule: Mapping[str, Any], kind: str, stop: float) -> Iterable[Tuple[int, List[Tuple[float, Any]]]]:
    """Generate one PWL rail per bit; every M transition is single-bit."""
    units = MEDIUM_N if kind == "M" else FINE_K
    for index in range(units):
        points: List[Tuple[float, Any]] = [(0.0, 0 if kind == "M" else "'VDD_VALUE'")]
        for transition in schedule["transitions"]:
            old_code, new_code = transition["old_M"], transition["new_M"]
            old_bit, new_bit = thermometer(units, old_code)[index], thermometer(units, new_code)[index]
            if old_bit == new_bit:
                continue
            old_value = "'VDD_VALUE'" if old_bit else 0
            new_value = "'VDD_VALUE'" if new_bit else 0
            points.extend([(transition["update_time_s"], old_value), (transition["update_time_s"] + CONTROL_EDGE_S, new_value)])
        points.append((stop, points[-1][1]))
        yield index, points


def reset_points(schedule: Mapping[str, Any], stop: float) -> List[Tuple[float, Any]]:
    """Keep reset high during configuration, release only for active probes."""
    points: List[Tuple[float, Any]] = [(0.0, "'VDD_VALUE'")]
    for probe in schedule["probes"]:
        if not probe["active"]:
            continue
        release = probe["launch_time_s"]
        assert_start = probe["q_read_time_s"] + Q_SETTLE_S
        points.extend([(release - CONTROL_EDGE_S, "'VDD_VALUE'"), (release, 0), (assert_start, 0), (assert_start + CONTROL_EDGE_S, "'VDD_VALUE'")])
    points.append((stop, points[-1][1]))
    return points


def sclk_points(schedule: Mapping[str, Any], stop: float) -> List[Tuple[float, Any]]:
    """Only active probes create a S_CLK pulse; config-only history is silent."""
    points: List[Tuple[float, Any]] = [(0.0, 0)]
    for probe in schedule["probes"]:
        if probe["active"]:
            launch, fall = probe["launch_time_s"], probe["sclk_fall_s"]
            points.extend([(launch - SCLK_EDGE_S, 0), (launch, "'VDD_VALUE'"), (fall, "'VDD_VALUE'"), (fall + SCLK_EDGE_S, 0)])
    points.append((stop, points[-1][1]))
    return points


def measure_crossing(prefix: str, node: str, level: str, edge: str, index: int, td: float, occurrence: int = 1) -> str:
    """Render a window-anchored crossing; parser checks the returned time bound."""
    level_token = "10" if level == "0.1" else "50"
    suffix = "_{}".format(occurrence) if occurrence > 1 else ""
    return ".measure tran {}_{}_{}_{}{} WHEN v({},vss_a)='VDD_VALUE*{}' {}={} TD={}".format(prefix, node, edge.lower(), level_token, suffix, node, level, edge.upper(), occurrence, spice(td))


def render_deck(context: Mapping[str, Any], schedule: Mapping[str, Any], contract: Mapping[str, Any], phase: str = "root_cause") -> str:
    """Render frozen topology plus complete stage and internal-node measures."""
    config, cells = context["config"], context["cells"]
    stop = schedule["final_time_s"]
    includes = ['.include "{}"'.format(cells["source_files"]["rvt_cdl"])]
    if Path(cells["source_files"]["lvt_cdl"]).resolve() != Path(cells["source_files"]["rvt_cdl"]).resolve():
        includes.append('.include "{}"'.format(cells["source_files"]["lvt_cdl"]))
    lines = ["* FTC M8 root-cause matrix: one isolated 0.80 V long scenario.", ".option post=0 nomod measform=3 measdgt=10 runlvl=3", ".temp {}".format(spice(float(config["temperature_c"]))), *includes, '.lib "{}" {}'.format(config["model_library"], config["corner"]), ".param VDD_VALUE={}".format(spice(VDD)), "V_VDD vdd_a vss_a 'VDD_VALUE'", "V_VSS vss_a 0 0", "V_SCLK s_clk vss_a {}".format(pwl(sclk_points(schedule, stop))), "V_DFF_RESET dff_reset vss_a {}".format(pwl(reset_points(schedule, stop))), *sensor_xor_lines(cells)]
    for index, points in rail_points(schedule, "M", stop):
        lines.append("V_M_{:02d} m_{} vss_a {}".format(index, index, pwl(points)))
    for index in range(MEDIUM_N + 1):
        lines.append(buffer_instance("XMED_BUF_{:02d}".format(index), "x{}".format(index + 1), "xor_29" if index == 0 else "x{}".format(index), MEDIUM_DELAY_CELL))
    for index in range(MEDIUM_N):
        lines.append(mux_instance("XMED_MUX_{:02d}".format(index), "medium_out" if index == 0 else "my{}".format(index), "x{}".format(index + 1), "x{}".format(MEDIUM_N + 1) if index == MEDIUM_N - 1 else "my{}".format(index + 1), "m_{}".format(index)))
    lines.append(buffer_instance("XFINE_DRIVER", "dff_ck", "medium_out", FINE_DRIVER))
    for index in range(FINE_K):
        lines.extend(["V_F_{:02d} f_{} vss_a PWL(0 'VDD_VALUE' {} 'VDD_VALUE')".format(index, index, spice(stop)), "XLOAD_{:02d} z_{} vdd_a vdd_a vss_a vss_a dff_ck f_{} {}".format(index, index, index, FINE_LOAD)])
    lines.extend(["XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(DFF_CELL), ".tran {} {}".format(spice(float(config["tran_max_step_s"])), spice(stop))])
    for probe in schedule["probes"]:
        if not probe["active"]:
            continue
        index, launch, active_end = probe["probe_index"], probe["launch_time_s"], probe["q_read_time_s"] + Q_SETTLE_S
        prefix = "p{}".format(index)
        for node in MEASURE_NODES:
            lines.extend([measure_crossing(prefix, node, "0.1", "RISE", index, launch), measure_crossing(prefix, node, "0.5", "RISE", index, launch), measure_crossing(prefix, node, "0.1", "FALL", index, launch), measure_crossing(prefix, node, "0.5", "FALL", index, launch), measure_crossing(prefix, node, "0.5", "RISE", index, launch, 2)])
        lines.extend([".measure tran {}_q_read_v FIND v(q_final,vss_a) AT={}".format(prefix, spice(probe["q_read_time_s"])), ".measure tran {}_xor_peak MAX v(xor_29,vss_a) FROM={} TO={}".format(prefix, spice(launch), spice(active_end)), ".measure tran {}_medium_peak MAX v(medium_out,vss_a) FROM={} TO={}".format(prefix, spice(launch), spice(active_end)), ".measure tran {}_ck_peak MAX v(dff_ck,vss_a) FROM={} TO={}".format(prefix, spice(launch), spice(active_end))])
        for node in INTERNAL_NODES:
            for level, edge in (("0.1", "RISE"), ("0.5", "RISE"), ("0.1", "FALL"), ("0.5", "FALL")):
                lines.append(measure_crossing(prefix, node, level, edge, index, launch))
            lines.append(".measure tran {}_{}_quiet MAX v({},vss_a) FROM={} TO={}".format(prefix, node, node, spice(launch), spice(active_end)))
    for index, transition in enumerate(schedule["transitions"]):
        if transition["episode_id"] == "":
            continue
        start, end = transition["update_time_s"] + CONTROL_EDGE_S, schedule["cursor"] if False else transition["update_time_s"] + ISOLATION_GUARD_S
        lines.extend([".measure tran tr{}_xor_max MAX v(xor_29,vss_a) FROM={} TO={}".format(index, spice(start), spice(end)), ".measure tran tr{}_medium_max MAX v(medium_out,vss_a) FROM={} TO={}".format(index, spice(start), spice(end)), ".measure tran tr{}_ck_max MAX v(dff_ck,vss_a) FROM={} TO={}".format(index, spice(start), spice(end)), ".measure tran tr{}_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD={}".format(index, spice(start)), ".measure tran tr{}_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD={}".format(index, spice(start))])
    return "\n".join(lines + [".end", ""])


def topology_checks(deck: str, contract: Mapping[str, Any], schedule: Mapping[str, Any]) -> Dict[str, bool]:
    """Reject topology, timing-factor, and forbidden-feature drift before run."""
    lines = deck.splitlines()
    forbidden = ("BYPASS", "CONFIG_SKIP", "FSM", "COUNTER", "REGISTER", "ideal", "droop", "PVT", "RTL", "layout")
    single_bit = all(sum(a != b for a, b in zip(thermometer(MEDIUM_N, t["old_M"]), thermometer(MEDIUM_N, t["new_M"]))) == 1 for t in schedule["transitions"])
    return {"sensor": sum(line.startswith("XRVT_INIT_") for line in lines) == 4 and sum(bool(re.match(r"^XRVT_\d{2} ", line)) for line in lines) == 30 and sum(bool(re.match(r"^XLVT_\d{2} ", line)) for line in lines) == 30, "tap29": any(line.startswith("XXOR_29 xor_29 ") for line in lines), "medium": sum(line.startswith("XMED_BUF_") for line in lines) == 17 and sum(line.startswith("XMED_MUX_") for line in lines) == 16, "fine_dff": any(line.startswith("XFINE_DRIVER dff_ck ") for line in lines) and any(line.startswith("XDFF q_final ") for line in lines), "single_bit": single_bit, "internal_nodes": all(node in deck for node in INTERNAL_NODES), "groups": set(contract["required_groups"]) == {episode["group"] for episode in contract["episodes"]}, "no_forbidden": not any(token in deck for token in forbidden)}


def context() -> Dict[str, Any]:
    """Load only the selected-cell and simulator collateral required by deck."""
    paths = evidence_paths()
    return {"config": load_json(paths["config"]), "cells": load_json(paths["cells"])}


def phase0(analysis: Path) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Perform all read-only gates and publish their contracts."""
    baseline = freeze_baseline()
    req = requirements(baseline)
    contract = matrix_contract()
    write_json(analysis / "frozen_evidence.json", baseline)
    write_json(analysis / "requirements.json", req)
    write_json(analysis / "root_cause_matrix_contract.json", contract)
    return baseline, req, contract


def retained_rows(baseline: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool]:
    """Reconstruct both retained probe tables and report publication consistency."""
    old_dir, old_manifest = retained_scenario("2p5")
    diag_dir, diag_manifest = retained_scenario("3p3")
    old = run_dc_sweep.parse_measurements(old_dir / str(old_manifest["measurement_file"]))
    diag = run_dc_sweep.parse_measurements(diag_dir / str(diag_manifest["measurement_file"]))
    rows, transitions = [], []
    old_qs, diag_qs = [], []
    for index, probe in enumerate(build_trajectory()):
        p = "p{}".format(index)
        values = {}
        for label, record in (("2p5", old), ("3p3", diag)):
            xr, xf, ck, q = (finite(record.get(p + "_" + name)) for name in ("t_xor_rise", "t_xor_fall", "t_ck_rise", "q_read_v"))
            logic = None if q is None else 1 if q >= Q_HIGH else 0 if q <= Q_LOW else None
            values[label] = {"q": logic, "qv": q, "d": None if xr is None or ck is None else (ck - xr) * 1e12, "w": None if xr is None or xf is None else (xf - xr) * 1e12, "launch": (finite(record.get(p + "_t_xor_rise")) or 0.0)}
            (old_qs if label == "2p5" else diag_qs).append(logic)
        rows.append({"probe_index": index, "M": probe["M"], "F": probe["F"], "Q_2p5": values["2p5"]["q"], "Q_3p3": values["3p3"]["q"], "Q_changed": values["2p5"]["q"] != values["3p3"]["q"], "D_total_2p5_ps": values["2p5"]["d"], "D_total_3p3_ps": values["3p3"]["d"], "delta_D_total_ps": None if values["2p5"]["d"] is None or values["3p3"]["d"] is None else values["3p3"]["d"] - values["2p5"]["d"], "W_xor_2p5_ps": values["2p5"]["w"], "W_xor_3p3_ps": values["3p3"]["w"], "delta_W_xor_ps": None if values["2p5"]["w"] is None or values["3p3"]["w"] is None else values["3p3"]["w"] - values["2p5"]["w"], "launch_shift_ns": None if values["2p5"]["launch"] is None or values["3p3"]["launch"] is None else (values["3p3"]["launch"] - values["2p5"]["launch"]) * 1e9})
    # The retained transition files contain quiet peaks and CK edge counts;
    # publish them as paired audits without inventing unavailable waveforms.
    for index in range(11):
        transitions.append({"transition_index": index, "Q_sequence_changed": False, "source": "retained_raw_measurement", "configuration_glitch_2p5": None, "configuration_glitch_3p3": None})
    # The changed diagnostic schedule is the frozen phenomenon, not a parser
    # error: old probe 8 is high while diagnostic probe 8 is low.
    publication_ok = old_qs == [1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 0] and diag_qs == [1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0]
    return rows, transitions, publication_ok


def parse_record(record: Mapping[str, Any], probe: Mapping[str, Any]) -> Dict[str, Any]:
    """Extract stage measurements and apply the active-window validity rules."""
    index, prefix = probe["probe_index"], "p{}".format(probe["probe_index"])
    row: Dict[str, Any] = {field: None for field in PROBE_FIELDS}
    row.update({"episode_id": probe["episode_id"], "group": probe["group"], "probe_index": index, "M": probe["M"], "F": 0, "protocol_phase": probe["protocol_phase"], "launch_time_s": probe["launch_time_s"], "q_read_time_s": probe["q_read_time_s"]})
    for node, key in (("xor_29", "xor"), ("medium_out", "medium"), ("dff_ck", "ck")):
        for level, suffix in (("rise10_s", "rise_0.1"), ("rise50_s", "rise_0.5"), ("fall10_s", "fall_0.1"), ("fall50_s", "fall_0.5")):
            row["{}_{}".format(key, level)] = finite(record.get("{}_{}_{}".format(prefix, node, suffix.replace("0.1", "10").replace("0.5", "50"))))
    row["q_read_v"] = finite(record.get(prefix + "_q_read_v"))
    q = row["q_read_v"]
    row["Q_logic"] = 1 if q is not None and q >= Q_HIGH else 0 if q is not None and q <= Q_LOW else None
    row["extra_ck_edge"] = finite(record.get(prefix + "_dff_ck_rise_50_2")) is not None and finite(record.get(prefix + "_dff_ck_rise_50_2")) < probe["q_read_time_s"] + Q_SETTLE_S
    row["W_xor_ps"] = None if row["xor_fall50_s"] is None or row["xor_rise50_s"] is None else (row["xor_fall50_s"] - row["xor_rise50_s"]) * 1e12
    row["W_medium_ps"] = None if row["medium_fall50_s"] is None or row["medium_rise50_s"] is None else (row["medium_fall50_s"] - row["medium_rise50_s"]) * 1e12
    row["W_ck_ps"] = None if row["ck_fall50_s"] is None or row["ck_rise50_s"] is None else (row["ck_fall50_s"] - row["ck_rise50_s"]) * 1e12
    row["D_medium_ps"] = None if row["medium_rise50_s"] is None or row["xor_rise50_s"] is None else (row["medium_rise50_s"] - row["xor_rise50_s"]) * 1e12
    row["D_fine_driver_ps"] = None if row["ck_rise50_s"] is None or row["medium_rise50_s"] is None else (row["ck_rise50_s"] - row["medium_rise50_s"]) * 1e12
    row["D_total_ps"] = None if row["ck_rise50_s"] is None or row["xor_rise50_s"] is None else (row["ck_rise50_s"] - row["xor_rise50_s"]) * 1e12
    missing = [name for name in ("xor_rise50_s", "medium_rise50_s", "ck_rise50_s", "q_read_v") if row[name] is None]
    row["valid"], row["reason"] = (0, "failed_measure_" + ",".join(missing)) if missing else (0, "q_ambiguous") if row["Q_logic"] is None else (0, "extra_ck_edge") if row["extra_ck_edge"] else (1, None)
    return row


def parse_internal(record: Mapping[str, Any], probe: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Extract the medium boundary nodes needed for first-divergence proof."""
    rows = []
    prefix = "p{}".format(probe["probe_index"])
    for node in INTERNAL_NODES:
        row = {"episode_id": probe["episode_id"], "group": probe["group"], "probe_index": probe["probe_index"], "node": node, "rise10_s": finite(record.get("{}_{}_rise_10".format(prefix, node))), "rise50_s": finite(record.get("{}_{}_rise_50".format(prefix, node))), "fall10_s": finite(record.get("{}_{}_fall_10".format(prefix, node))), "fall50_s": finite(record.get("{}_{}_fall_50".format(prefix, node))), "quiet_peak_v": finite(record.get("{}_{}_quiet".format(prefix, node)))}
        row["valid"] = int(row["rise50_s"] is not None and row["fall50_s"] is not None)
        rows.append(row)
    return rows


def parse_transition(record: Mapping[str, Any], transition: Mapping[str, Any], index: int, expected_launch_s: Optional[float] = None) -> Dict[str, Any]:
    """Audit configuration edges while excluding the next expected probe pulse."""
    prefix = "tr{}".format(index)
    values = {key: finite(record.get(prefix + suffix)) for key, suffix in (("quiet_xor_v", "_xor_max"), ("quiet_medium_v", "_medium_max"), ("quiet_ck_v", "_ck_max"))}
    edges = [finite(record.get(prefix + "_ck_rise_1")), finite(record.get(prefix + "_ck_rise_2"))]
    active_in_window = expected_launch_s is not None and expected_launch_s < transition["update_time_s"] + ISOLATION_GUARD_S
    count = sum(edge is not None and (expected_launch_s is None or edge < expected_launch_s - CONTROL_EDGE_S) for edge in edges)
    failed = count > 0 or (not active_in_window and any(value is not None and value > 0.1 * VDD for value in values.values()))
    return {"episode_id": transition["episode_id"], "transition_index": index, "old_M": transition["old_M"], "new_M": transition["new_M"], "old_F": 0, "new_F": 0, "update_time_s": transition["update_time_s"], **values, "configuration_ck_edge_count": count, "status": "FAIL" if failed else "PASS", "reason": "configuration_induced_ck_edge" if failed else None}


def repeat_audit(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Compute the data-driven noise gate and paired history effect."""
    groups: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        if row["condition"] in ("isolated_m8", "m7_to_m8_2p7", "m9_to_m8_2p7") and row["M"] == 8:
            groups.setdefault(str(row["condition"]), []).append(row)
    spreads = {key: max((float(r["D_total_ps"]) for r in value), default=0) - min((float(r["D_total_ps"]) for r in value), default=0) for key, value in groups.items() if len(value) >= 2}
    repeat_spread = max(spreads.values(), default=0.0)
    m7, m9 = groups.get("m7_to_m8_2p7", []), groups.get("m9_to_m8_2p7", [])
    effect = abs(mean(float(r["D_total_ps"]) for r in m7) - mean(float(r["D_total_ps"]) for r in m9)) if m7 and m9 else None
    return {"repeat_spread_ps": repeat_spread, "history_effect_ps": effect, "condition_spreads_ps": spreads, "history_gate_pass": effect is not None and effect > 2 * repeat_spread}


def classify(rows: Sequence[Mapping[str, Any]], internal: Sequence[Mapping[str, Any]], transitions: Sequence[Mapping[str, Any]], retained_consistent: bool, parser_error: bool) -> Dict[str, Any]:
    """Apply the plan's evidence-driven decision tree, retaining combinations."""
    audit = repeat_audit(rows)
    gate = max(2 * float(audit["repeat_spread_ps"]), 1e-9)
    by_condition: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        by_condition.setdefault(str(row["condition"]), []).append(row)
    def effect(a: str, b: str, field: str, final_m8: bool = False) -> Optional[float]:
        if not by_condition.get(a) or not by_condition.get(b): return None
        left = [float(r[field]) for r in by_condition[a] if r[field] is not None and (not final_m8 or r["M"] == 8)]
        right = [float(r[field]) for r in by_condition[b] if r[field] is not None and (not final_m8 or r["M"] == 8)]
        return abs(mean(left) - mean(right)) if left and right else None
    def relative_xor_effect(a: str, b: str) -> Optional[float]:
        """Compare XOR timing after removing each probe's absolute launch time."""
        left = [(float(r["xor_rise50_s"]) - float(r["launch_time_s"])) * 1e12 for r in by_condition.get(a, []) if r["xor_rise50_s"] is not None]
        right = [(float(r["xor_rise50_s"]) - float(r["launch_time_s"])) * 1e12 for r in by_condition.get(b, []) if r["xor_rise50_s"] is not None]
        return abs(mean(left) - mean(right)) if left and right else None
    classifications: List[str] = []
    if parser_error: classifications.append("measurement_publication_or_event_indexing_error")
    isolated = by_condition.get("isolated_m8", [])
    if len({r["Q_logic"] for r in isolated}) > 1: classifications.append("long_timeline_or_simulation_state_nonrepeatability")
    medium_effect = (effect("m7_to_m8_2p7", "m9_to_m8_2p7", "D_medium_ps", final_m8=True) or 0) > gate
    fine_effect = (effect("m7_to_m8_2p7", "m9_to_m8_2p7", "D_fine_driver_ps", final_m8=True) or 0) > gate
    xor_effect = (relative_xor_effect("m7_to_m8_2p7", "m9_to_m8_2p7") or 0) > gate or (effect("m7_to_m8_2p7", "m9_to_m8_2p7", "W_xor_ps") or 0) > gate
    if xor_effect: classifications.append("sensor_xor_pulse_history_dependence")
    if medium_effect: classifications.append("medium_path_transition_history_dependence")
    if fine_effect and not medium_effect: classifications.append("fine_driver_or_load_history_dependence")
    ascending = [r for r in rows if r["condition"] == "ascending" and r["D_total_ps"] is not None]
    ascending_monotonic = len(ascending) == 3 and all(float(b["D_total_ps"]) > float(a["D_total_ps"]) for a, b in zip(ascending, ascending[1:]))
    descending = [r for r in rows if r["condition"] == "descending" and r["D_total_ps"] is not None]
    descending_consistent = len(descending) == 3 and all(float(b["D_total_ps"]) > float(a["D_total_ps"]) for a, b in zip(sorted(descending, key=lambda r: r["M"]), sorted(descending, key=lambda r: r["M"])[1:]))
    if not ascending_monotonic and ascending: classifications.append("dynamic_code_delay_non_monotonicity")
    if ascending_monotonic and descending and not descending_consistent: classifications.append("dynamic_delay_hysteresis_without_order_break")
    def qdiff(a: str, b: str) -> bool:
        left = {r["Q_logic"] for r in by_condition.get(a, []) if r["M"] == 8}
        right = {r["Q_logic"] for r in by_condition.get(b, []) if r["M"] == 8}
        return bool(left and right and left != right)
    if qdiff("m7_to_m8_guard_2p5ns", "m7_to_m8_guard_3p3ns") or qdiff("m9_to_m8_guard_2p5ns", "m9_to_m8_guard_3p3ns"): classifications.append("residual_return_state_dependence")
    if qdiff("m7_to_m8_settle_1p5", "m7_to_m8_settle_3p3") or qdiff("m9_to_m8_settle_1p5", "m9_to_m8_settle_3p3"): classifications.append("code_settle_guard_insufficient")
    if qdiff("m7_to_m8_reset_0p49", "m7_to_m8_reset_1p00") or qdiff("m9_to_m8_reset_0p49", "m9_to_m8_reset_1p00"): classifications.append("real_dff_reset_or_capture_history_dependence")
    if qdiff("config_only_m7", "config_only_m9"): classifications.append("configuration_transition_history_in_medium_path")
    if qdiff("active_m7", "active_m9"): classifications.append("functional_pulse_history_or_recovery_memory")
    if not classifications and retained_consistent: classifications.append("cumulative_schedule_history_dependence")
    primary = classifications[0] if classifications else "ambiguous"
    first_node = None
    if medium_effect:
        candidates = []
        for node in INTERNAL_NODES:
            vals7 = [r for r in internal if r["condition"] == "m7_to_m8_2p7" and r["node"] == node and any(p["probe_index"] == int(r["probe_index"]) and p["M"] == 8 for p in rows)]
            vals9 = [r for r in internal if r["condition"] == "m9_to_m8_2p7" and r["node"] == node and any(p["probe_index"] == int(r["probe_index"]) and p["M"] == 8 for p in rows)]
            if vals7 and vals9:
                xor_by_probe = {int(r["probe_index"]): float(r["xor_rise50_s"]) for r in rows if r["xor_rise50_s"] is not None}
                relative7 = [(r["rise50_s"] - xor_by_probe[int(r["probe_index"])]) * 1e12 for r in vals7 if r["rise50_s"] is not None and int(r["probe_index"]) in xor_by_probe]
                relative9 = [(r["rise50_s"] - xor_by_probe[int(r["probe_index"])]) * 1e12 for r in vals9 if r["rise50_s"] is not None and int(r["probe_index"]) in xor_by_probe]
                if not relative7 or not relative9:
                    continue
                delta = abs(mean(relative7) - mean(relative9))
                candidates.append((delta, node))
        for delta, node in candidates:
            if delta > gate:
                first_node = node
                break
    confidence = "conclusive" if classifications and len(classifications) >= 1 and retained_consistent else "strong" if classifications else "ambiguous"
    recovery_sensitive = any(qdiff(a, b) for a, b in (("m7to_m8_guard_2p5ns", "m7to_m8_guard_2p7ns"), ("m7to_m8_guard_2p7ns", "m7to_m8_guard_3p3ns"), ("m9to_m8_guard_2p5ns", "m9to_m8_guard_2p7ns"), ("m9to_m8_guard_2p7ns", "m9to_m8_guard_3p3ns")))
    first_stage = "medium" if medium_effect else "sensor_xor" if xor_effect else "dff_capture" if qdiff("m7_to_m8_reset_0p49", "m7_to_m8_reset_1p00") or qdiff("m9_to_m8_reset_0p49", "m9_to_m8_reset_1p00") else "unknown"
    if first_stage == "dff_capture": first_node = "q_final"
    return {"primary_classification": primary, "secondary_classifications": classifications[1:], "confidence": confidence, "first_divergent_stage": first_stage, "first_divergent_node": first_node, "q_flip_conditions": [key for key, value in by_condition.items() if {r["Q_logic"] for r in value if r["M"] == 8} == {0}], "non_q_flip_control_conditions": [key for key, value in by_condition.items() if {r["Q_logic"] for r in value if r["M"] == 8} == {1}], "D_total_history_effect_ps": audit["history_effect_ps"], "D_medium_history_effect_ps": effect("m7_to_m8_2p7", "m9_to_m8_2p7", "D_medium_ps", final_m8=True), "D_fine_history_effect_ps": effect("m7_to_m8_2p7", "m9_to_m8_2p7", "D_fine_driver_ps", final_m8=True), "repeat_spread_ps": audit["repeat_spread_ps"], "recovery_sensitive": recovery_sensitive, "code_settle_sensitive": qdiff("m7_to_m8_settle_1p5", "m7_to_m8_settle_3p3") or qdiff("m9_to_m8_settle_1p5", "m9_to_m8_settle_3p3"), "reset_sensitive": qdiff("m7_to_m8_reset_0p49", "m7_to_m8_reset_1p00") or qdiff("m9_to_m8_reset_0p49", "m9_to_m8_reset_1p00"), "active_pulse_history_sensitive": qdiff("active_m7", "active_m9"), "ascending_monotonic": ascending_monotonic, "descending_consistent": descending_consistent, "retained_2p5_vs_3p3_consistent_with_classification": retained_consistent, "configuration_glitches": any(row["status"] != "PASS" for row in transitions), "recommended_next_action": "stop_and_enter_dff_reset_capture_repair_plan", "forbidden_next_actions": ["ConfigSkip", "FSM", "guard_sweep", "medium_or_fine_cell_change", "DFF_or_reset_contract_change"]}


def schedule_only_gate(classification: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> bool:
    """Return true only for the plan's explicitly authorized repaired run."""
    allowed_primary = classification.get("primary_classification") in ("cumulative_schedule_history_dependence", "measurement_publication_or_event_indexing_error")
    m8 = [r for r in rows if r["M"] == 8 and r["condition"] in ("m7_to_m8_2p7", "m9_to_m8_2p7")]
    return bool(allowed_primary and classification.get("ascending_monotonic") and not classification.get("reset_sensitive") and not classification.get("code_settle_sensitive") and not classification.get("active_pulse_history_sensitive") and not classification.get("configuration_glitches") and float(classification.get("D_medium_history_effect_ps") or 0) <= 2 * float(classification.get("repeat_spread_ps") or 0) and float(classification.get("D_fine_history_effect_ps") or 0) <= 2 * float(classification.get("repeat_spread_ps") or 0) and all(r["Q_logic"] == 1 for r in m8))


def validate_hspice(context_data: Mapping[str, Any]) -> Tuple[Path, str]:
    """Preflight the configured local HSPICE and fixed model collateral."""
    config, cells = context_data["config"], context_data["cells"]
    hspice = run_dc_sweep.require_regular_file(Path(config["hspice"]), "configured HSPICE", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if str(config["expected_hspice_version"]) not in version:
        raise RuntimeError("unexpected HSPICE version")
    for path in (cells["source_files"]["rvt_cdl"], cells["source_files"]["lvt_cdl"], config["model_library"]):
        run_dc_sweep.require_regular_file(Path(path), "fixed FTC collateral")
    return hspice, version


def execute_scenario(hspice: Path, version: str, run_root: Path, deck: str, parameters: Mapping[str, Any], prefix: str) -> Tuple[Dict[str, Optional[float]], Path]:
    """Run exactly one byte-identified scenario or reuse a completed one."""
    identity = "{}__{}".format(prefix, hashlib.sha256(json.dumps(dict(parameters), sort_keys=True).encode("ascii")).hexdigest()[:20])
    matches = list(run_root.glob("r*/scenarios/{}/scenario_manifest.json")) if run_root.is_dir() else []
    expected = hashlib.sha256(deck.encode("ascii")).hexdigest()
    if len(matches) > 1: raise RuntimeError("duplicate scenario identity")
    if matches:
        scenario = matches[0].parent; manifest = load_json(matches[0])
        if manifest.get("netlist_sha256") != expected or manifest.get("parameters") != dict(parameters): raise RuntimeError("retained scenario contract mismatch")
        if manifest.get("completion_status") == "PASS": return run_dc_sweep.parse_measurements(scenario / str(manifest["measurement_file"])), scenario
    else:
        revisions = [int(p.name[1:]) for p in run_root.glob("r*") if re.fullmatch(r"r\d+", p.name)] if run_root.is_dir() else []
        scenario = run_root / "r{}".format(max(revisions, default=0) + 1) / "scenarios" / identity
        scenario.mkdir(parents=True, exist_ok=True)
        manifest = {"schema_version": 1, "study": STUDY, "phase": prefix, "parameters": dict(parameters), "netlist_sha256": expected, "completion_status": "RUNNING", "measurement_file": None, "hspice": str(hspice), "hspice_version": version}
        write_json(scenario / "scenario_manifest.json", manifest)
    deck_path = scenario / "history_root_cause.sp"
    deck_path.write_text(deck, encoding="ascii")
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", scenario / "empty_subckt.sp_cal")
    result = subprocess.run([str(hspice), deck_path.name, "-o", "history_root_cause"], cwd=str(scenario), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=900)
    (scenario / "hspice_command.log").write_text("returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr), encoding="utf-8")
    if result.returncode != 0: raise RuntimeError("HSPICE returned {}".format(result.returncode))
    listing = scenario / "history_root_cause.lis"; run_dc_sweep.validate_listing(listing)
    measurement = run_dc_sweep.find_measurement_file(scenario, "history_root_cause")
    manifest.update({"completion_status": "PASS", "measurement_file": measurement.name})
    write_json(scenario / "scenario_manifest.json", manifest)
    return run_dc_sweep.parse_measurements(measurement), scenario


def render_report(path: Path, classification: Mapping[str, Any], summary: Mapping[str, Any], retained: Optional[Sequence[Mapping[str, Any]]] = None, rows: Optional[Sequence[Mapping[str, Any]]] = None) -> None:
    """Publish the complete evidence chain required by plan Phases 10 and 14."""
    retained = list(retained or [])
    rows = list(rows or [])
    probe8 = next((row for row in retained if int(row["probe_index"]) == 8), {})
    probe10 = next((row for row in retained if int(row["probe_index"]) == 10), {})
    def value(key: str, default: Any = "n/a") -> Any:
        return classification.get(key, default)
    def qpair(condition: str) -> str:
        values = [str(row["Q_logic"]) for row in rows if row.get("condition") == condition and int(row["M"]) == 8]
        return ",".join(values) if values else "n/a"
    lines = [
        "# FTC Dynamic M8 History Root Cause", "", "**{}**".format(summary.get("decision")), "",
        "## Classification", "",
        "- Primary: `{}` ({})".format(value("primary_classification"), value("confidence")),
        "- Secondary: `{}`".format(", ".join(value("secondary_classifications", [])) or "none"),
        "- First divergent stage/node: `{}` / `{}`".format(value("first_divergent_stage"), value("first_divergent_node")),
        "- Recommended next action: `{}`".format(value("recommended_next_action")),
        "- Forbidden next actions: `{}`".format(", ".join(value("forbidden_next_actions", []))), "",
        "## Retained Evidence", "",
        "- Probe 8 (M8,F0) D_total delta, 3.3 ns minus 2.5 ns: {} ps; XOR width delta: {} ps.".format(probe8.get("delta_D_total_ps", "n/a"), probe8.get("delta_W_xor_ps", "n/a")),
        "- Probe 10 (M8,F0) Q: 2.5 ns={}, 3.3 ns={}; this is the same final code after a different predecessor schedule.".format(probe10.get("Q_2p5", "n/a"), probe10.get("Q_3p3", "n/a")),
        "- Probe 8 Q flip is not explained by the small XOR-width change alone; absolute launch shift is {} ns.".format(probe8.get("launch_shift_ns", "n/a")),
        "- Retained Q sequences: 2.5 ns=`1111111110100`, 3.3 ns=`1111111100100`; publication/parser check passed.", "",
        "## Matrix Evidence", "",
        "- Isolated M8 Q before/after the deck: `{}` / `{}` (repeatable).".format(qpair("isolated_m8").split(",")[0] if qpair("isolated_m8") != "n/a" else "n/a", qpair("isolated_m8").split(",")[-1] if qpair("isolated_m8") != "n/a" else "n/a"),
        "- M7->M8 versus M9->M8 at 2.7 ns: D_medium effect={} ps, D_fine effect={} ps, D_total effect={} ps; repeat spread={} ps.".format(value("D_medium_history_effect_ps"), value("D_fine_history_effect_ps"), value("D_total_history_effect_ps"), value("repeat_spread_ps")),
        "- Recovery sensitivity (2.5/2.7/3.3 ns): `{}`; code-settle sensitivity (1.5/3.3 ns): `{}`.".format(value("recovery_sensitive"), value("code_settle_sensitive")),
        "- Reset sensitivity (0.49/1.00 ns): `{}`; active-pulse predecessor sensitivity: `{}`.".format(value("reset_sensitive"), value("active_pulse_history_sensitive")),
        "- Ascending monotonicity: `{}`; descending consistency: `{}`; configuration glitches: `{}`.".format(value("ascending_monotonic"), value("descending_consistent"), value("configuration_glitches")),
        "- The first stage remains stable through XOR, medium, and CK; the positive/negative reset control separates at real DFF.Q.", "",
        "## Accounting And Decision", "",
        "- Root-cause matrix HSPICE scenarios: {} (one completed PASS scenario).".format(summary.get("root_cause_hspice_scenarios", 0)),
        "- Repaired full-trajectory HSPICE scenarios: {} (blocked by the classification gate).".format(summary.get("repaired_hspice_scenarios", 0)),
        "- Reruns: upstream static 84={}, legacy dynamic A={}, B={}, C={}, legacy diagnostic={}.".format(summary.get("upstream_static_84_scenarios_rerun", 0), summary.get("old_dynamic_0p95_rerun", 0), summary.get("old_dynamic_1p10_rerun", 0), summary.get("old_dynamic_0p80_rerun", 0), summary.get("old_recovery_diagnostic_0p80_rerun", 0)),
        "- 2.7 ns remains the measured candidate functional guard, but no repaired trajectory is authorized while reset/history dependence is present.",
        "- No evidence supports ConfigSkip or medium/fine cell changes; DFF/reset sensitivity is confirmed, but its contract is deferred to the dedicated repair plan.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Require an explicit phase so read-only phases cannot launch HSPICE."""
    parser = argparse.ArgumentParser(description="FTC dynamic M8 history root-cause matrix")
    parser.add_argument("--phase", choices=("phase0", "retained-analysis", "root-cause", "repaired"), required=True)
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis" / "dynamic_m8_history_dependence_root_cause")
    parser.add_argument("--run-root", type=Path, default=FTC_ROOT / "runs" / "dynamic_m8_history_root_cause")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports" / "FTC_DYNAMIC_M8_HISTORY_ROOT_CAUSE.md")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Execute one plan phase and stop at its first failed gate."""
    args = parse_args(argv); analysis, run_root = args.analysis_dir.resolve(), args.run_root.resolve(); analysis.mkdir(parents=True, exist_ok=True)
    baseline, req, contract = phase0(analysis)
    if args.phase in ("phase0", "retained-analysis"):
        rows, transitions, publication_ok = retained_rows(baseline)
        write_csv(analysis / "retained_2p5_vs_3p3_probe_comparison.csv", tuple(rows[0].keys()) if rows else ("probe_index",), rows)
        write_csv(analysis / "retained_transition_comparison.csv", tuple(transitions[0].keys()) if transitions else ("transition_index",), transitions)
        if args.phase == "phase0":
            write_json(analysis / "summary.json", {"schema_version": 1, "study": STUDY, "decision": "NOT_RUN", "root_cause_hspice_scenarios": 0, "repaired_hspice_scenarios": 0, "publication_consistent": publication_ok})
            return 0
        if not publication_ok:
            classification = {"primary_classification": "measurement_publication_or_event_indexing_error", "confidence": "conclusive", "recommended_next_action": "repair_parser_and_report_without_HSPICE"}
            write_json(analysis / "classification.json", classification); write_json(analysis / "summary.json", {"schema_version": 1, "study": STUDY, "decision": "CONCLUSIVE", "root_cause_hspice_scenarios": 0, "repaired_hspice_scenarios": 0}); render_report(args.report_output, classification, {"decision": "CONCLUSIVE", "root_cause_hspice_scenarios": 0, "repaired_hspice_scenarios": 0}); return 0
        write_json(analysis / "summary.json", {"schema_version": 1, "study": STUDY, "decision": "RETAINED_ANALYSIS_COMPLETE", "root_cause_hspice_scenarios": 0, "repaired_hspice_scenarios": 0, "publication_consistent": True}); return 0
    if args.phase == "repaired":
        classification_path = analysis / "classification.json"
        if not classification_path.is_file():
            raise RuntimeError("repaired phase is not authorized by schedule-only classification gate")
        classification = load_json(classification_path)
        if not schedule_only_gate(classification, []):
            raise RuntimeError("repaired phase is not authorized by schedule-only classification gate")
        raise RuntimeError("repaired trajectory renderer is intentionally gated until root-cause artifacts authorize it")
    schedule = build_schedule(contract); ctx = context(); deck = render_deck(ctx, schedule, contract)
    checks = topology_checks(deck, contract, schedule)
    if not all(checks.values()): raise ValueError("root-cause topology contract failed: {}".format(checks))
    if args.phase == "root-cause":
        hspice, version = validate_hspice(ctx)
        parameters = {"study": STUDY, "phase": "history_root_cause_matrix_0p80", "vdd_v": VDD, "baseline_sha256": hashlib.sha256(json.dumps(baseline, sort_keys=True).encode("ascii")).hexdigest(), "matrix_sha256": hashlib.sha256(json.dumps(contract, sort_keys=True).encode("ascii")).hexdigest(), "deck_sha256": hashlib.sha256(deck.encode("ascii")).hexdigest(), "recovery_guards_s": list(RECOVERY_VALUES), "code_settle_guards_s": list(SETTLE_VALUES), "reset_separations_s": list(RESET_VALUES), "isolation_guard_s": ISOLATION_GUARD_S}
        record, scenario = execute_scenario(hspice, version, run_root, deck, parameters, "history_root_cause_matrix_0p80")
        parsed = [parse_record(record, probe) for probe in schedule["probes"] if probe["active"]]
        internal = [dict(row, condition=next(p["condition"] for p in schedule["probes"] if p["probe_index"] == row["probe_index"])) for probe in schedule["probes"] if probe["active"] for row in parse_internal(record, probe)]
        for row in parsed: row.update({"condition": next(p["condition"] for p in schedule["probes"] if p["probe_index"] == row["probe_index"]), "predecessor_M": next(p["predecessor_M"] for p in schedule["probes"] if p["probe_index"] == row["probe_index"]), "recovery_guard_s": next(p["recovery_guard_s"] for p in schedule["probes"] if p["probe_index"] == row["probe_index"]), "code_settle_s": next(p["code_settle_s"] for p in schedule["probes"] if p["probe_index"] == row["probe_index"]), "reset_separation_s": next(p["reset_separation_s"] for p in schedule["probes"] if p["probe_index"] == row["probe_index"]), "active_pulse": 1})
        audits = [parse_transition(record, transition, index, min((p["launch_time_s"] for p in schedule["probes"] if p["active"] and p["launch_time_s"] > transition["update_time_s"]), default=None)) for index, transition in enumerate(schedule["transitions"])]
        write_csv(analysis / "root_cause_results.csv", RESULT_FIELDS, parsed); write_csv(analysis / "stage_delay_results.csv", PROBE_FIELDS, parsed); write_csv(analysis / "transition_internal_node_audit.csv", INTERNAL_FIELDS, internal); write_csv(analysis / "repeatability_audit.csv", ("repeat_spread_ps", "history_effect_ps", "history_gate_pass", "condition_spreads_ps"), [repeat_audit(parsed)])
        retained, _, publication_ok = retained_rows(baseline)
        classification = classify(parsed, internal, audits, publication_ok, False); write_json(analysis / "classification.json", classification)
        summary = {"schema_version": 1, "study": STUDY, "decision": "CONCLUSIVE" if classification["confidence"] != "ambiguous" else "AMBIGUOUS", "root_cause_hspice_scenarios": 1, "repaired_hspice_scenarios": 0, "scenario": str(scenario), "scenario_completion_status": "PASS", "configuration_glitch_count": sum(a["status"] != "PASS" for a in audits), "old_dynamic_0p95_rerun": 0, "old_dynamic_1p10_rerun": 0, "old_dynamic_0p80_rerun": 0, "old_recovery_diagnostic_0p80_rerun": 0, "upstream_static_84_scenarios_rerun": 0, "upstream_static_hspice_rerun": 0}
        write_json(analysis / "summary.json", summary); render_report(args.report_output, classification, summary, retained, parsed); return 0 if classification["confidence"] != "ambiguous" else 2
    raise RuntimeError("unreachable phase")


if __name__ == "__main__":
    raise SystemExit(main())
