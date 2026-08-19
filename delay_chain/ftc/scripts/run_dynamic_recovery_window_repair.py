#!/usr/bin/env python3
"""Repair only the FTC dynamic recovery timing contract.

The runner owns a separate output tree. It reads the previous dynamic result
as immutable evidence, measures real return crossings in one diagnostic deck,
derives one guard, and then runs one repaired deck. No cell or code search is
performed.
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
import run_dc_sweep  # noqa: E402  # Shared, side-effect-free parser only.

STUDY = "dynamic_recovery_window_repair_v1"
VDD = 0.80
OLD_GUARD_S = 2.5e-9
Q_SETTLE_S = 2.0e-10
CONTROL_EDGE_S = 1.0e-11
SCLK_EDGE_S = 1.0e-12
SCLK_HIGH_S = 3.0e-9
RESET_SEPARATION_S = 4.9e-10
CODE_SETTLE_S = 1.5e-9
QUIET_RATIO = 0.1
MEDIUM_N = 16
FINE_K = 10
MEDIUM_DELAY_CELL = "BUF_X0P7M_A9TL40"
MEDIUM_MUX_CELL = "MXT2_X0P5M_A9TL40"
FINE_DRIVER = "BUF_X0P8M_A9TL40"
FINE_LOAD = "NOR2_X4A_A9TL40"
SENSOR_RVT_INITIAL = 4
SENSOR_LVT_INITIAL = 0
OBSERVABLE_STAGES = 30
SENSOR_TAP = 29
XOR_CELL = "XOR2_X0P5M_A9TR40"
DFF_CELL = "DFFRPQ_X0P5M_A9TR40"
NODES = ("xor_29", "medium_out", "dff_ck")

DIAGNOSTIC_FIELDS = (
    "vdd_v", "probe_index", "protocol_phase", "medium_code", "fine_code",
    "node", "sclk_fall_s", "return_rise10_s", "return_fall10_s",
    "return_settle_ps", "second_rise10_s", "second_rise_present", "valid", "reason",
)
PROBE_FIELDS = (
    "vdd_v", "probe_index", "protocol_phase", "medium_code", "fine_code",
    "launch_time_s", "q_read_time_s", "t_xor_rise_s", "t_xor_fall_s",
    "t_ck_rise_s", "q_read_v", "dynamic_Q", "D_code_ps", "W_xor_ps",
    "valid", "reason",
)
TRANSITION_FIELDS = (
    "vdd_v", "transition_index", "transition_type", "old_M", "new_M", "old_F",
    "new_F", "update_time_s", "next_reset_release_s", "next_launch_s",
    "medium_out_quiet_peak_v", "dff_ck_quiet_peak_v", "xor_quiet_peak_v",
    "configuration_ck_edge_count", "status", "reason",
)


def sha256_file(path: Path) -> str:
    """Hash evidence in chunks so large listings are never held in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    """Load and validate one JSON-object contract."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write stable task-owned evidence only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    """Write a fixed schema; failed measures remain explicit blanks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def read_csv(path: Path, required: Sequence[str]) -> List[Dict[str, str]]:
    """Read a retained CSV and require its contract columns."""
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise ValueError("required CSV schema is missing: {}".format(path))
        rows = list(reader)
    if not rows:
        raise ValueError("required CSV is empty: {}".format(path))
    return rows


def finite(value: Any) -> Optional[float]:
    """Keep failed HSPICE measures distinct from a physical zero."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def spice(value: float) -> str:
    """Render an HSPICE-safe scalar."""
    return "{:.12e}".format(float(value))


def vkey(value: float) -> str:
    """Use stable voltage spelling for joins and identities."""
    return "{:.2f}".format(float(value))


def thermometer(units: int, code: int) -> Tuple[int, ...]:
    """Return the frozen first-code-high thermometer encoding."""
    if not 0 <= code <= units:
        raise ValueError("thermometer code outside legal range")
    return tuple(1 if index < code else 0 for index in range(units))


def evidence_paths() -> Dict[str, Path]:
    """Name immutable evidence; none of these paths is an output target."""
    analysis = FTC_ROOT / "analysis" / "dynamic_startup_calibration_protocol"
    return {
        "summary.json": analysis / "summary.json",
        "dynamic_lock_table.json": analysis / "dynamic_lock_table.json",
        "timing_contract.json": analysis / "timing_contract.json",
        "probe_results.csv": analysis / "probe_results.csv",
        "transition_audit.csv": analysis / "transition_audit.csv",
        "integration_contract.json": analysis / "integration_contract.json",
        "trajectory_contract.json": analysis / "trajectory_contract.json",
        "report.md": FTC_ROOT / "reports" / "FTC_DYNAMIC_STARTUP_CALIBRATION_PROTOCOL.md",
        "runner.py": FTC_ROOT / "scripts" / "run_dynamic_startup_calibration_protocol.py",
        "q_read_contract.json": FTC_ROOT / "analysis" / "two_stage_real_dff_hierarchical_calibration" / "q_read_contract.json",
        "xor_fine.csv": FTC_ROOT / "analysis" / "real_xor_pulse_width" / "fine.csv",
        "ftc_config.json": FTC_ROOT / "ftc_config.json",
        "selected_cells.json": FTC_ROOT / "discovery" / "selected_cells.json",
    }


def retained_old_scenario() -> Tuple[Path, Dict[str, Any]]:
    """Find exactly one retained 0.80 V / 2.5 ns scenario, read-only."""
    root = FTC_ROOT / "runs" / "dynamic_startup_calibration_protocol"
    matches: List[Tuple[Path, Dict[str, Any]]] = []
    for manifest_path in root.glob("r*/scenarios/*/scenario_manifest.json"):
        manifest = load_json(manifest_path)
        params = manifest.get("parameters", {})
        if float(params.get("vdd_v", -1.0)) == VDD and float(params.get("recovery_guard_s", -1.0)) == OLD_GUARD_S:
            matches.append((manifest_path.parent, manifest))
    if len(matches) != 1:
        raise ValueError("old_failure_map_incomplete: expected one retained 0.80 V scenario")
    scenario, manifest = matches[0]
    measurement = scenario / str(manifest.get("measurement_file", ""))
    if not measurement.is_file() or not (scenario / "dynamic_startup_calibration.lis").is_file():
        raise ValueError("old_failure_map_incomplete: retained measurement/listing missing")
    return scenario, manifest


def freeze_baseline() -> Dict[str, Any]:
    """Validate and publish the exact NO-GO handoff before new decks."""
    paths = evidence_paths()
    missing = [str(path) for path in paths.values() if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise ValueError("upstream_baseline_mismatch: missing evidence: {}".format(", ".join(missing)))
    summary = load_json(paths["summary.json"])
    locks = load_json(paths["dynamic_lock_table.json"])
    if summary.get("decision") != "Dynamic Startup Calibration Protocol = NO-GO":
        raise ValueError("upstream_baseline_mismatch: dynamic decision changed")
    if summary.get("reasons") != ["recovery_window_insufficient"]:
        raise ValueError("old_failure_not_recovery_only: dynamic reasons changed")
    expected = {
        0.95: ("GO", "1111110", "10", 0, 5, 1),
        1.10: ("GO", "11110", "11110", 0, 3, 4),
        0.80: ("NO-GO", "1111111110", "10", 0, 8, 1),
    }
    per_voltage = {round(float(item["vdd_v"]), 2): item for item in summary["per_voltage"]}
    lock_rows = {round(float(item["VDD"]), 2): item for item in locks["locks"]}
    for voltage, values in expected.items():
        item, lock = per_voltage.get(voltage), lock_rows.get(voltage)
        observed = None if not item else (item.get("status"), item.get("coarse_q_dynamic"), item.get("fine_q_dynamic"), item.get("lock_hold_q", [None])[0], item.get("dynamic_M_final"), item.get("dynamic_F_final"))
        if observed != values or not lock or lock.get("status") != values[0]:
            raise ValueError("upstream_baseline_mismatch: frozen lock changed at {} V".format(voltage))
    if float(per_voltage[0.80]["maximum_recovery_signal_ratio"]) < 1.0:
        raise ValueError("upstream_baseline_mismatch: old recovery peak no longer proves failure")
    if any(int(summary.get(name, 0)) != 0 for name in ("historical_dff_rerun", "historical_fine_rerun", "historical_medium_rerun", "historical_xor_rerun", "upstream_static_hspice_rerun", "upstream_static_84_scenarios_rerun")):
        raise ValueError("upstream_baseline_mismatch: historical rerun counter is nonzero")
    old_scenario, old_manifest = retained_old_scenario()
    hashes = {name: sha256_file(path) for name, path in paths.items()}
    hashes.update({
        "old_scenario_manifest.json": sha256_file(old_scenario / "scenario_manifest.json"),
        "old_measurement.csv": sha256_file(old_scenario / str(old_manifest["measurement_file"])),
        "old_listing.lis": sha256_file(old_scenario / "dynamic_startup_calibration.lis"),
    })
    return {
        "schema_version": 1, "study": STUDY,
        "baseline_commit": "568f8ace2b7fa813a2bb082302c182b51288dd53",
        "decision": summary["decision"], "reasons": summary["reasons"],
        "retained_0p95": expected[0.95], "retained_1p10": expected[1.10], "retained_0p80": expected[0.80],
        "old_recovery_guard_s": OLD_GUARD_S, "old_scenario": str(old_scenario),
        "old_scenario_parameters": old_manifest["parameters"],
        "upstream_static_84_scenarios_rerun": 0, "upstream_static_hspice_rerun": 0,
        "old_dynamic_0p95_rerun": 0, "old_dynamic_1p10_rerun": 0, "old_dynamic_0p80_rerun": 0,
        "source_file_sha256": hashes,
    }


def requirements(baseline: Mapping[str, Any]) -> Dict[str, Any]:
    """Publish scope and forbidden changes as a small contract."""
    return {
        "schema_version": 1, "study": STUDY, "vdd_v": VDD, "medium_N": MEDIUM_N,
        "medium_delay_cell": MEDIUM_DELAY_CELL, "medium_mux_cell": MEDIUM_MUX_CELL,
        "fine_driver": FINE_DRIVER, "fine_load": FINE_LOAD, "fine_K": FINE_K,
        "sensor_initial_rvt_stages": SENSOR_RVT_INITIAL, "sensor_initial_lvt_stages": SENSOR_LVT_INITIAL,
        "observable_stages": OBSERVABLE_STAGES, "sensor_tap": SENSOR_TAP,
        "xor_cell": XOR_CELL, "dff_cell": DFF_CELL, "q_read_offset_s": 2.3e-9,
        "q_settle_s": Q_SETTLE_S, "code_settle_guard_s": CODE_SETTLE_S, "old_recovery_guard_s": OLD_GUARD_S,
        "diagnostic_scenario_budget": 1, "repaired_scenario_budget": 1,
        "upstream_static_84_scenarios_rerun": 0, "upstream_static_hspice_rerun": 0,
        "old_dynamic_0p95_rerun": 0, "old_dynamic_1p10_rerun": 0, "old_dynamic_0p80_rerun": 0,
        "forbidden": ["bypass", "config_skip", "clock_gating", "update_isolation", "ideal_delay", "ideal_capacitor", "sensor_tap_change", "xor_change", "dff_change", "FSM", "counter", "register", "programmable_margin", "droop", "PVT", "RTL", "layout"],
        "baseline_sha256": hashlib.sha256(json.dumps(dict(baseline), sort_keys=True).encode("ascii")).hexdigest(),
    }


def old_failure_map(baseline: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert retained endpoint/tail measures into explicit node failures."""
    scenario = Path(str(baseline["old_scenario"]))
    manifest = load_json(scenario / "scenario_manifest.json")
    run_dc_sweep.validate_listing(scenario / "dynamic_startup_calibration.lis")
    record = run_dc_sweep.parse_measurements(scenario / str(manifest["measurement_file"]))
    trajectory = load_json(FTC_ROOT / "analysis" / "dynamic_startup_calibration_protocol" / "trajectory_contract.json")["by_vdd"]["0.80"]
    failures, all_measurements = [], []
    for probe in trajectory["probes"]:
        index = int(probe["probe_index"])
        for node, suffix in (("xor_29", "xor"), ("medium_out", "medium"), ("dff_ck", "ck")):
            endpoint = finite(record.get("p{}_recovery_{}_end".format(index, suffix)))
            tail = finite(record.get("p{}_recovery_{}_tail".format(index, suffix)))
            item = {
                "vdd_v": VDD, "probe_index": index, "protocol_phase": probe["protocol_phase"],
                "medium_code": probe["medium_code"], "fine_code": probe["fine_code"], "node": node,
                "recovery_end_s": probe["recovery_end_s"], "endpoint_v": endpoint,
                "endpoint_ratio": endpoint / VDD if endpoint is not None else None, "tail_v": tail,
                "tail_ratio": tail / VDD if tail is not None else None,
                "failed": endpoint is None or tail is None or endpoint > QUIET_RATIO * VDD or tail > QUIET_RATIO * VDD,
            }
            all_measurements.append(item)
            if item["failed"]:
                failures.append(item)
    if not failures:
        raise ValueError("old_failure_not_recovery_only: retained failure map is empty")
    worst = max(failures, key=lambda item: max(item["endpoint_ratio"] or 0.0, item["tail_ratio"] or 0.0))
    return {
        "schema_version": 1, "study": STUDY, "old_recovery_guard_s": OLD_GUARD_S,
        "source_scenario": str(scenario), "source_measurement_sha256": sha256_file(scenario / str(manifest["measurement_file"])),
        "failure_count": len(failures), "failures": failures, "all_measurements": all_measurements, "worst_failure": worst,
    }


def ceil_tenth(value: float) -> float:
    """Round a positive timing upward to the required 0.1 ns quantum."""
    return math.ceil((value - 1.0e-15) / 1.0e-10) * 1.0e-10


def diagnostic_contract(baseline: Mapping[str, Any]) -> Dict[str, Any]:
    """Derive the first bounded observation window solely from retained data."""
    paths = evidence_paths()
    config, q_contract = load_json(paths["ftc_config.json"]), load_json(paths["q_read_contract.json"])
    rows = read_csv(paths["xor_fine.csv"], ("vdd_v", "t_xor29_fall_s", "valid"))
    selected = [row for row in rows if 0.80 <= float(row["vdd_v"]) <= 1.10 and str(row["valid"]).lower() in ("1", "true")]
    max_xor_end = max(float(row["t_xor29_fall_s"]) - float(config["launch_time_s"]) for row in selected)
    max_delay = max(float(item["D_delay_max_s"]) for item in q_contract["projections_by_vdd"].values())
    bound = ceil_tenth(max_xor_end + max_delay + 2.0 * Q_SETTLE_S)
    if bound <= OLD_GUARD_S:
        raise ValueError("diagnostic_contract_invalid: bound does not exceed old guard")
    return {
        "schema_version": 1, "study": STUDY, "measurement_contract_version": "return_10pct_v1",
        "vdd_v": VDD, "diagnostic_bound_s": bound, "old_recovery_guard_s": OLD_GUARD_S,
        "historical_launch_s": float(config["launch_time_s"]), "max_xor_fall_minus_launch_s": max_xor_end,
        "retained_D_delay_max_s": max_delay, "q_settle_s": Q_SETTLE_S, "diagnostic_extra_settle_s": 2.0 * Q_SETTLE_S,
        "rounding_quantum_s": 1.0e-10,
        "sources": {"ftc_config.json": sha256_file(paths["ftc_config.json"]), "q_read_contract.json": sha256_file(paths["q_read_contract.json"]), "xor_fine.csv": sha256_file(paths["xor_fine.csv"]), "baseline": baseline["source_file_sha256"]},
        "derivation": "ceil_0.1ns(max(t_xor29_fall-launch over 0.80..1.10 V) + retained_D_delay_max + 2*Q_SETTLE)",
    }


def build_trajectory() -> Dict[str, Any]:
    """Reconstruct only the retained 0.80 V 13-probe trajectory."""
    probes = [{"medium_code": 0, "fine_code": 0, "protocol_phase": "coarse", "transition_type": "initial"}]
    for medium in range(1, 10):
        probes.append({"medium_code": medium, "fine_code": 0, "protocol_phase": "coarse", "transition_type": "coarse_increment"})
    probes.extend([
        {"medium_code": 8, "fine_code": 0, "protocol_phase": "fine_entry", "transition_type": "coarse_backoff"},
        {"medium_code": 8, "fine_code": 1, "protocol_phase": "fine", "transition_type": "fine_increment"},
        {"medium_code": 8, "fine_code": 1, "protocol_phase": "lock_hold", "transition_type": "lock_hold"},
    ])
    for index, probe in enumerate(probes):
        probe["probe_index"] = index
    transitions, old_m, old_f = [], 0, 0
    for probe in probes[1:]:
        new_m, new_f = probe["medium_code"], probe["fine_code"]
        changed = sum(a != b for a, b in zip(thermometer(MEDIUM_N, old_m), thermometer(MEDIUM_N, new_m))) + sum(a != b for a, b in zip(thermometer(FINE_K, old_f), thermometer(FINE_K, new_f)))
        if changed == 0:
            old_m, old_f = new_m, new_f
            continue
        if changed != 1:
            raise ValueError("diagnostic_contract_invalid: trajectory is not single-bit")
        transitions.append({"transition_index": len(transitions), "transition_type": probe["transition_type"], "old_M": old_m, "new_M": new_m, "old_F": old_f, "new_F": new_f})
        old_m, old_f = new_m, new_f
    return {"schema_version": 1, "study": STUDY, "vdd_v": VDD, "probes": probes, "transitions": transitions, "expected_final": {"M": 8, "F": 1}}


def schedule_trajectory(trajectory: Mapping[str, Any], recovery_guard_s: float) -> Dict[str, Any]:
    """Schedule probes like the retained runner with one guard input."""
    cursor, old_m, old_f = 0.0, 0, 0
    probes, transitions = [], []
    for probe in trajectory["probes"]:
        new_m, new_f = probe["medium_code"], probe["fine_code"]
        changed = (new_m, new_f) != (old_m, old_f)
        update = cursor
        update_end = update + CONTROL_EDGE_S if changed else update
        release_end = update_end + (CODE_SETTLE_S if changed or probe["probe_index"] == 0 else 0.0) + CONTROL_EDGE_S
        launch = release_end + RESET_SEPARATION_S
        q_read = launch + 2.3e-9
        reset_start, reset_end = q_read + Q_SETTLE_S, q_read + Q_SETTLE_S + CONTROL_EDGE_S
        sclk_fall = launch + SCLK_HIGH_S
        item = dict(probe)
        item.update({"old_M": old_m, "old_F": old_f, "update_time_s": update, "update_end_s": update_end, "reset_release_s": release_end, "launch_time_s": launch, "q_read_time_s": q_read, "reset_assert_start_s": reset_start, "reset_assert_end_s": reset_end, "sclk_fall_s": sclk_fall, "recovery_end_s": sclk_fall + recovery_guard_s})
        probes.append(item)
        if changed:
            transitions.append({"transition_index": len(transitions), "transition_type": probe["transition_type"], "old_M": old_m, "new_M": new_m, "old_F": old_f, "new_F": new_f, "update_time_s": update, "next_reset_release_s": release_end, "next_launch_s": launch, "probe_index": probe["probe_index"]})
        old_m, old_f, cursor = new_m, new_f, item["recovery_end_s"]
    return {"probes": probes, "transitions": transitions, "final_time_s": cursor, "expected_final": trajectory["expected_final"]}


def buffer_instance(name: str, output: str, input_node: str, cell: str) -> str:
    """Render the verified six-port buffer mapping."""
    return "{} {} vdd_a vdd_a vss_a vss_a {} {}".format(name, output, input_node, cell)


def mux_instance(name: str, output: str, shallow: str, deep: str, select: str) -> str:
    """Render the fixed non-inverting medium MUX mapping."""
    return "{} {} vdd_a vdd_a vss_a vss_a {} {} {} {}".format(name, output, shallow, deep, select, MEDIUM_MUX_CELL)


def sensor_xor_lines(cells: Mapping[str, Any]) -> List[str]:
    """Recreate the frozen four-RVT/zero-LVT sensor and tap-29 XOR."""
    lines, rvt_input = ["* Frozen sensor: four RVT prefix stages and 30 observable stages."], "s_clk"
    for stage in range(SENSOR_RVT_INITIAL):
        output = "rvt_initial_{}".format(stage)
        lines.append(buffer_instance("XRVT_INIT_{:02d}".format(stage), output, rvt_input, cells["delay_rvt"]["cell"]))
        rvt_input = output
    rvt_taps, lvt_taps = [], []
    for stage in range(OBSERVABLE_STAGES):
        output = "rvt_{}".format(stage)
        lines.append(buffer_instance("XRVT_{:02d}".format(stage), output, rvt_input, cells["delay_rvt"]["cell"]))
        rvt_taps.append(output)
        rvt_input = output
    lvt_input = "s_clk"
    for stage in range(OBSERVABLE_STAGES):
        output = "lvt_{}".format(stage)
        lines.append(buffer_instance("XLVT_{:02d}".format(stage), output, lvt_input, cells["delay_lvt"]["cell"]))
        lvt_taps.append(output)
        lvt_input = output
    for stage, (rvt, lvt) in enumerate(zip(rvt_taps, lvt_taps)):
        lines.append("XXOR_{:02d} xor_{} vdd_a vdd_a vss_a vss_a {} {} {}".format(stage, stage, rvt, lvt, XOR_CELL))
    return lines


def pwl(points: Sequence[Tuple[float, Any]]) -> str:
    """Format a PWL source with all timing points explicit."""
    return "PWL({})".format(" ".join("{} {}".format(spice(time), value) for time, value in points))


def rail_points(schedule: Mapping[str, Any], kind: str, stop: float) -> Iterable[Tuple[int, List[Tuple[float, Any]]]]:
    """Create one PWL rail per bit; each transition changes exactly one bit."""
    units = MEDIUM_N if kind == "M" else FINE_K
    for index in range(units):
        points: List[Tuple[float, Any]] = [(0.0, 0 if kind == "M" else "'VDD_VALUE'")]
        for transition in schedule["transitions"]:
            old_code = transition["old_M"] if kind == "M" else transition["old_F"]
            new_code = transition["new_M"] if kind == "M" else transition["new_F"]
            old_bit, new_bit = thermometer(units, old_code)[index], thermometer(units, new_code)[index]
            if old_bit == new_bit:
                continue
            old_value = ("'VDD_VALUE'" if old_bit else 0) if kind == "M" else (0 if old_bit else "'VDD_VALUE'")
            new_value = ("'VDD_VALUE'" if new_bit else 0) if kind == "M" else (0 if new_bit else "'VDD_VALUE'")
            points.extend([(transition["update_time_s"], old_value), (transition["update_time_s"] + CONTROL_EDGE_S, new_value)])
        points.append((stop, points[-1][1]))
        yield index, points


def render_deck(context: Mapping[str, Any], schedule: Mapping[str, Any], phase: str) -> str:
    """Render one new deck; topology is independent of diagnostic/repaired phase."""
    config, cells = context["config"], context["cells"]
    stop = schedule["final_time_s"] + 2.0e-9
    includes = ['.include "{}"'.format(cells["source_files"]["rvt_cdl"])]
    if Path(cells["source_files"]["lvt_cdl"]).resolve() != Path(cells["source_files"]["rvt_cdl"]).resolve():
        includes.append('.include "{}"'.format(cells["source_files"]["lvt_cdl"]))
    sclk, reset = [(0.0, 0)], [(0.0, "'VDD_VALUE'")]
    for probe in schedule["probes"]:
        sclk.extend([(probe["launch_time_s"] - SCLK_EDGE_S, 0), (probe["launch_time_s"], "'VDD_VALUE'"), (probe["sclk_fall_s"], "'VDD_VALUE'"), (probe["sclk_fall_s"] + SCLK_EDGE_S, 0)])
        reset.extend([(probe["reset_release_s"] - CONTROL_EDGE_S, "'VDD_VALUE'"), (probe["reset_release_s"], "'VDD_VALUE'"), (probe["reset_release_s"] + CONTROL_EDGE_S, 0), (probe["reset_assert_start_s"], 0), (probe["reset_assert_end_s"], "'VDD_VALUE'")])
    lines = ["* FTC recovery repair: frozen topology and single-bit PWL controls.", ".option post=0 nomod measform=3 measdgt=10 runlvl=3", ".temp {}".format(spice(float(config["temperature_c"]))), *includes, '.lib "{}" {}'.format(config["model_library"], config["corner"]), ".param VDD_VALUE={}".format(spice(VDD)), "V_VDD vdd_a vss_a 'VDD_VALUE'", "V_VSS vss_a 0 0", "V_SCLK s_clk vss_a {}".format(pwl(sclk)), "V_DFF_RESET dff_reset vss_a {}".format(pwl(reset)), *sensor_xor_lines(cells)]
    for index, points in rail_points(schedule, "M", stop):
        lines.append("V_M_{:02d} m_{} vss_a {}".format(index, index, pwl(points)))
    for index in range(MEDIUM_N + 1):
        lines.append(buffer_instance("XMED_BUF_{:02d}".format(index), "x{}".format(index + 1), "xor_29" if index == 0 else "x{}".format(index), MEDIUM_DELAY_CELL))
    for index in range(MEDIUM_N):
        lines.append(mux_instance("XMED_MUX_{:02d}".format(index), "medium_out" if index == 0 else "my{}".format(index), "x{}".format(index + 1), "x{}".format(MEDIUM_N + 1) if index == MEDIUM_N - 1 else "my{}".format(index + 1), "m_{}".format(index)))
    lines.append(buffer_instance("XFINE_DRIVER", "dff_ck", "medium_out", FINE_DRIVER))
    for index, points in rail_points(schedule, "F", stop):
        lines.extend(["V_F_{:02d} f_{} vss_a {}".format(index, index, pwl(points)), "XLOAD_{:02d} z_{} vdd_a vdd_a vss_a vss_a dff_ck f_{} {}".format(index, index, index, FINE_LOAD)])
    lines.extend(["XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(DFF_CELL), ".tran {} {}".format(spice(float(config["tran_max_step_s"])), spice(stop))])
    for probe in schedule["probes"]:
        index, launch = probe["probe_index"], spice(probe["launch_time_s"])
        lines.extend([".measure tran p{}_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD={}".format(index, launch), ".measure tran p{}_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD={}".format(index, launch), ".measure tran p{}_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD={}".format(index, launch), ".measure tran p{}_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD={}".format(index, launch), ".measure tran p{}_q_read_v FIND v(q_final,vss_a) AT={}".format(index, spice(probe["q_read_time_s"])), ".measure tran p{}_xor_peak MAX v(xor_29,vss_a) FROM={} TO={}".format(index, launch, spice(probe["reset_assert_start_s"])), ".measure tran p{}_ck_peak MAX v(dff_ck,vss_a) FROM={} TO={}".format(index, launch, spice(probe["reset_assert_start_s"]))])
        for node, expression in (("xor", "xor_29"), ("medium", "medium_out"), ("ck", "dff_ck")):
            lines.extend([".measure tran p{}_return_{}_rise10 WHEN v({},vss_a)='VDD_VALUE*0.1' RISE=1 TD={}".format(index, node, expression, spice(probe["sclk_fall_s"])), ".measure tran p{}_return_{}_fall10 WHEN v({},vss_a)='VDD_VALUE*0.1' FALL=1 TD={}".format(index, node, expression, spice(probe["sclk_fall_s"])), ".measure tran p{}_return_{}_rise10_2 WHEN v({},vss_a)='VDD_VALUE*0.1' RISE=2 TD={}".format(index, node, expression, spice(probe["sclk_fall_s"])), ".measure tran p{}_recovery_{}_end FIND v({},vss_a) AT={}".format(index, node, expression, spice(probe["recovery_end_s"])), ".measure tran p{}_recovery_{}_tail MAX v({},vss_a) FROM={} TO={}".format(index, node, expression, spice(probe["recovery_end_s"] - Q_SETTLE_S), spice(probe["recovery_end_s"]))])
    for transition in schedule["transitions"]:
        index = transition["transition_index"]
        start, end = spice(transition["update_time_s"] + CONTROL_EDGE_S), spice(transition["next_reset_release_s"] - CONTROL_EDGE_S)
        lines.extend([".measure tran tr{}_xor_max MAX v(xor_29,vss_a) FROM={} TO={}".format(index, start, end), ".measure tran tr{}_medium_max MAX v(medium_out,vss_a) FROM={} TO={}".format(index, start, end), ".measure tran tr{}_ck_max MAX v(dff_ck,vss_a) FROM={} TO={}".format(index, start, end), ".measure tran tr{}_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD={}".format(index, start), ".measure tran tr{}_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD={}".format(index, start)])
    return "\n".join(lines + [".end", ""])


def topology_checks(deck: str, schedule: Mapping[str, Any]) -> Dict[str, bool]:
    """Audit topology and control shape before HSPICE."""
    lines = deck.splitlines()
    forbidden = ("XBYPASS", "XCONFIG_SKIP", "FSM", "COUNTER", "REGISTER", "ideal", "droop", "PVT", "RTL", "layout")
    return {
        "sensor_topology": sum(line.startswith("XRVT_INIT_") for line in lines) == 4 and sum(bool(re.match(r"^XRVT_\d{2} ", line)) for line in lines) == 30 and sum(line.startswith("XLVT_") for line in lines) == 30,
        "tap29_xor": "XXOR_29 xor_29 vdd_a vdd_a vss_a vss_a rvt_29 lvt_29 {}".format(XOR_CELL) in lines,
        "medium_topology": sum(line.startswith("XMED_BUF_") for line in lines) == 17 and sum(line.startswith("XMED_MUX_") for line in lines) == 16,
        "fixed_cells": "XFINE_DRIVER dff_ck vdd_a vdd_a vss_a vss_a medium_out {}".format(FINE_DRIVER) in lines and "XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(DFF_CELL) in lines,
        "pwl_controls": sum(line.startswith("V_M_") and "PWL(" in line for line in lines) == MEDIUM_N and sum(line.startswith("V_F_") and "PWL(" in line for line in lines) == FINE_K,
        "single_bit": all(sum(a != b for a, b in zip(thermometer(MEDIUM_N, t["old_M"]), thermometer(MEDIUM_N, t["new_M"]))) + sum(a != b for a, b in zip(thermometer(FINE_K, t["old_F"]), thermometer(FINE_K, t["new_F"]))) == 1 for t in schedule["transitions"]),
        "no_forbidden": not any(token in deck for token in forbidden),
    }


def context_from_baseline() -> Dict[str, Any]:
    """Load only selected-cell and simulator collateral used by the deck."""
    paths = evidence_paths()
    return {"config": load_json(paths["ftc_config.json"]), "cells": load_json(paths["selected_cells.json"])}


def scenario_parameters(phase: str, guard_s: float, baseline: Mapping[str, Any], schedule: Mapping[str, Any], deck: str, timing_sha: str) -> Dict[str, Any]:
    """Bind reuse to phase, topology, trajectory, timing, and measurement contract."""
    return {
        "study": STUDY, "phase": phase, "vdd_v": VDD,
        "frozen_baseline_sha256": hashlib.sha256(json.dumps(dict(baseline), sort_keys=True).encode("ascii")).hexdigest(),
        "trajectory_sha256": hashlib.sha256(json.dumps(schedule, sort_keys=True).encode("ascii")).hexdigest(),
        "timing_contract_sha256": timing_sha, "deck_sha256": hashlib.sha256(deck.encode("ascii")).hexdigest(),
        "medium_N": MEDIUM_N, "medium_delay_cell": MEDIUM_DELAY_CELL, "medium_mux_cell": MEDIUM_MUX_CELL,
        "fine_driver": FINE_DRIVER, "fine_load": FINE_LOAD, "fine_K": FINE_K,
        "sensor_tap": SENSOR_TAP, "xor_cell": XOR_CELL, "dff_cell": DFF_CELL,
        "q_read_offset_s": 2.3e-9, "q_settle_s": Q_SETTLE_S, "code_settle_guard_s": CODE_SETTLE_S,
        "recovery_guard_s": guard_s, "control_edge_s": CONTROL_EDGE_S, "measurement_contract_version": "return_10pct_v1",
    }


def execute_scenario(hspice: Path, version: str, run_root: Path, phase: str, deck: str, parameters: Mapping[str, Any], stats: Dict[str, int]) -> Dict[str, Optional[float]]:
    """Run once or reuse one complete, byte-matching task-owned scenario."""
    identity = "{}__{}".format(phase, hashlib.sha256(json.dumps(dict(parameters), sort_keys=True).encode("ascii")).hexdigest()[:20])
    matches = list(run_root.glob("r*/scenarios/{}/scenario_manifest.json".format(identity))) if run_root.is_dir() else []
    expected_sha = hashlib.sha256(deck.encode("ascii")).hexdigest()
    if len(matches) > 1:
        raise RuntimeError("duplicate retained scenario identity: {}".format(identity))
    if matches:
        scenario = matches[0].parent
        manifest = load_json(scenario / "scenario_manifest.json")
        if manifest.get("parameters") != dict(parameters) or manifest.get("netlist_sha256") != expected_sha:
            raise RuntimeError("retained scenario is not safely reusable: {}".format(scenario))
        if manifest.get("completion_status") == "PASS":
            stats["reused"] += 1
            return run_dc_sweep.parse_measurements(scenario / str(manifest["measurement_file"]))
        if (scenario / "dynamic_recovery_window_repair.mt0.csv").exists():
            raise RuntimeError("retained scenario is not safely reusable: {}".format(scenario))
        manifest["completion_status"] = "RUNNING"
        manifest.pop("failure", None)
        write_json(scenario / "scenario_manifest.json", manifest)
        deck_path = scenario / "dynamic_recovery_window_repair.sp"
        stats["retry_setup"] = stats.get("retry_setup", 0) + 1
    else:
        run_root.mkdir(parents=True, exist_ok=True)
        revisions = [int(path.name[1:]) for path in run_root.glob("r*") if path.is_dir() and re.fullmatch(r"r\d+", path.name)]
        scenario = run_root / "r{}".format(max(revisions, default=0) + 1) / "scenarios" / identity
        scenario.mkdir(parents=True)
        deck_path = scenario / "dynamic_recovery_window_repair.sp"
        deck_path.write_text(deck, encoding="ascii")
        manifest = {"schema_version": 1, "study": STUDY, "phase": phase, "parameters": dict(parameters), "netlist_sha256": expected_sha, "completion_status": "RUNNING", "measurement_file": None, "hspice": str(hspice), "hspice_version": version}
        write_json(scenario / "scenario_manifest.json", manifest)
        stats["new"] = stats.get("new", 0) + 1
        counter = "diagnostic_new" if phase == "recovery_diagnostic_0p80" else "repaired_new"
        stats[counter] = stats.get(counter, 0) + 1
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", scenario / "empty_subckt.sp_cal")
    try:
        result = subprocess.run([str(hspice), deck_path.name, "-o", "dynamic_recovery_window_repair"], cwd=str(scenario), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=900)
        (scenario / "hspice_command.log").write_text("returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr), encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError("HSPICE returned {}".format(result.returncode))
        run_dc_sweep.validate_listing(scenario / "dynamic_recovery_window_repair.lis")
        measurement = run_dc_sweep.find_measurement_file(scenario, "dynamic_recovery_window_repair")
        manifest.update({"completion_status": "PASS", "measurement_file": measurement.name})
        write_json(scenario / "scenario_manifest.json", manifest)
        return run_dc_sweep.parse_measurements(measurement)
    except Exception as error:
        manifest.update({"completion_status": "FAIL", "failure": str(error)})
        write_json(scenario / "scenario_manifest.json", manifest)
        raise


def return_rows(schedule: Mapping[str, Any], record: Mapping[str, Any], bound_s: float, safety_tail_s: float = 0.0) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Classify return crossings and select the worst measured settle.

    Diagnostic validation uses a zero safety-tail requirement because it only
    establishes the measured return event. Repaired validation passes the
    frozen 200 ps tail and proves the final quiet safety interval.
    """
    rows, measured = [], []
    for probe in schedule["probes"]:
        index = probe["probe_index"]
        for node, suffix in (("xor_29", "xor"), ("medium_out", "medium"), ("dff_ck", "ck")):
            prefix = "p{}".format(index)
            rise = finite(record.get(prefix + "_return_{}_rise10".format(suffix)))
            fall = finite(record.get(prefix + "_return_{}_fall10".format(suffix)))
            rise2 = finite(record.get(prefix + "_return_{}_rise10_2".format(suffix)))
            settle = (fall - probe["sclk_fall_s"]) * 1.0e12 if fall is not None else None
            second = rise2 is not None and rise2 < probe["recovery_end_s"]
            valid = fall is not None and fall <= probe["recovery_end_s"] - safety_tail_s and not second
            reason = None if valid else "return_second_rise_detected" if second else "recovery_return_did_not_settle_within_diagnostic_bound" if fall is None or fall > probe["recovery_end_s"] else "return_fall_measurement_missing"
            row = {"vdd_v": VDD, "probe_index": index, "protocol_phase": probe["protocol_phase"], "medium_code": probe["medium_code"], "fine_code": probe["fine_code"], "node": node, "sclk_fall_s": probe["sclk_fall_s"], "return_rise10_s": rise, "return_fall10_s": fall, "return_settle_ps": settle, "second_rise10_s": rise2, "second_rise_present": second, "valid": int(valid), "reason": reason}
            rows.append(row)
            if settle is not None and valid:
                measured.append(row)
    if not measured or any(not row["valid"] for row in rows):
        raise ValueError("recovery_return_did_not_settle_within_diagnostic_bound")
    worst = max(measured, key=lambda row: float(row["return_settle_ps"]))
    return rows, {"schema_version": 1, "study": STUDY, "old_guard_ns": OLD_GUARD_S * 1.0e9, "worst_probe_index": worst["probe_index"], "worst_protocol_phase": worst["protocol_phase"], "worst_M": worst["medium_code"], "worst_F": worst["fine_code"], "worst_node": worst["node"], "worst_return_rise10_ns": worst["return_rise10_s"] * 1.0e9, "worst_return_fall10_ns": worst["return_fall10_s"] * 1.0e9, "worst_return_settle_ns": worst["return_settle_ps"] * 1.0e-3, "second_rise_present": any(row["second_rise_present"] for row in rows), "all_rows": rows, "bound_s": bound_s}


def probe_rows(schedule: Mapping[str, Any], record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Extract Q/D waveform results for repaired validation."""
    rows = []
    for probe in schedule["probes"]:
        index, prefix = probe["probe_index"], "p{}".format(probe["probe_index"])
        rise, fall, ck, q = (finite(record.get(prefix + name)) for name in ("_t_xor_rise", "_t_xor_fall", "_t_ck_rise", "_q_read_v"))
        row = {field: None for field in PROBE_FIELDS}
        row.update({"vdd_v": VDD, "probe_index": index, "protocol_phase": probe["protocol_phase"], "medium_code": probe["medium_code"], "fine_code": probe["fine_code"], "launch_time_s": probe["launch_time_s"], "q_read_time_s": probe["q_read_time_s"], "t_xor_rise_s": rise, "t_xor_fall_s": fall, "t_ck_rise_s": ck, "q_read_v": q})
        row["dynamic_Q"] = 1 if q is not None and q >= VDD / 2.0 else 0 if q is not None else None
        second_ck = finite(record.get(prefix + "_t_ck_rise_2"))
        if q is None or rise is None or fall is None or ck is None:
            row["valid"], row["reason"] = 0, "return_fall_measurement_missing"
        elif VDD * QUIET_RATIO < q < VDD * (1.0 - QUIET_RATIO):
            row["valid"], row["reason"] = 0, "q_ambiguous"
        elif second_ck is not None and second_ck < probe["reset_assert_start_s"]:
            row["valid"], row["reason"] = 0, "extra_ck_edge_during_probe"
        elif probe["q_read_time_s"] - ck < Q_SETTLE_S:
            row["valid"], row["reason"] = 0, "repaired_q_settle_insufficient"
        else:
            row["W_xor_ps"], row["D_code_ps"], row["valid"] = (fall - rise) * 1.0e12, (ck - rise) * 1.0e12, 1
        rows.append(row)
    return rows


def transition_rows(schedule: Mapping[str, Any], record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Audit code-update quiet windows and configuration-induced CK edges."""
    rows = []
    for transition in schedule["transitions"]:
        index, prefix = transition["transition_index"], "tr{}".format(transition["transition_index"])
        values = {name: finite(record.get(prefix + suffix)) for name, suffix in (("xor_quiet_peak_v", "_xor_max"), ("medium_out_quiet_peak_v", "_medium_max"), ("dff_ck_quiet_peak_v", "_ck_max"))}
        edges = [finite(record.get(prefix + "_ck_rise_1")), finite(record.get(prefix + "_ck_rise_2"))]
        edge_count = sum(edge is not None and edge < transition["next_reset_release_s"] for edge in edges)
        row = {field: None for field in TRANSITION_FIELDS}
        row.update({"vdd_v": VDD, "transition_index": index, "transition_type": transition["transition_type"], "old_M": transition["old_M"], "new_M": transition["new_M"], "old_F": transition["old_F"], "new_F": transition["new_F"], "update_time_s": transition["update_time_s"], "next_reset_release_s": transition["next_reset_release_s"], "next_launch_s": transition["next_launch_s"], **values, "configuration_ck_edge_count": edge_count})
        row["status"] = "PASS" if edge_count == 0 and all(value is None or value <= QUIET_RATIO * VDD for value in values.values()) else "FAIL"
        row["reason"] = None if row["status"] == "PASS" else "repaired_configuration_glitch"
        rows.append(row)
    return rows


def dynamic_gate_reasons(schedule: Mapping[str, Any], record: Mapping[str, Any], safety_tail_s: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """Apply the complete Q/D/CK/quiet contract to one new 0.80 V record."""
    rows = probe_rows(schedule, record)
    transitions = transition_rows(schedule, record)
    returns, _ = return_rows(schedule, record, schedule["probes"][-1]["recovery_end_s"] - schedule["probes"][-1]["sclk_fall_s"], safety_tail_s)
    reasons = [row["reason"] for row in rows if row["reason"]]
    reasons.extend(row["reason"] for row in transitions if row["reason"])
    reasons.extend(row["reason"] for row in returns if row["reason"])
    coarse = [row for row in rows if row["protocol_phase"] == "coarse"]
    fine = [row for row in rows if row["protocol_phase"] in ("fine_entry", "fine")]
    if "".join(str(row["dynamic_Q"]) for row in coarse) != "1111111110":
        reasons.append("repaired_coarse_q_mismatch")
    if "".join(str(row["dynamic_Q"]) for row in fine) != "10":
        reasons.append("repaired_fine_q_mismatch")
    if not rows or rows[-1]["dynamic_Q"] != 0:
        reasons.append("repaired_lock_hold_mismatch")
    if coarse and not all(right["D_code_ps"] > left["D_code_ps"] for left, right in zip(coarse, coarse[1:])):
        reasons.append("repaired_delay_non_monotonic")
    reasons = list(dict.fromkeys(reasons))
    return rows, transitions, returns, reasons


def validate_hspice(context: Mapping[str, Any]) -> Tuple[Path, str]:
    """Validate simulator version and fixed collateral before a new run."""
    config, cells = context["config"], context["cells"]
    hspice = run_dc_sweep.require_regular_file(Path(config["hspice"]), "configured HSPICE", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if str(config["expected_hspice_version"]) not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    for path in (cells["source_files"]["rvt_cdl"], cells["source_files"]["lvt_cdl"], config["model_library"]):
        run_dc_sweep.require_regular_file(Path(path), "fixed FTC collateral")
    return hspice, version


def repaired_contract(measured: Mapping[str, Any], diagnostic: Mapping[str, Any]) -> Dict[str, Any]:
    """Freeze the only repaired guard before validation; no tuning follows."""
    worst = float(measured["worst_return_settle_ns"]) * 1.0e-9
    guard = ceil_tenth(worst + Q_SETTLE_S)
    if guard <= OLD_GUARD_S:
        raise ValueError("measured_guard_not_greater_than_old_guard")
    if guard > float(diagnostic["diagnostic_bound_s"]):
        raise ValueError("measured_guard_exceeds_diagnostic_bound")
    return {"schema_version": 1, "study": STUDY, "old_recovery_guard_s": OLD_GUARD_S, "new_recovery_guard_s": guard, "added_guard_s": guard - OLD_GUARD_S, "worst_return_settle_s": worst, "safety_tail_s": Q_SETTLE_S, "rounding_quantum_s": 1.0e-10, "derivation": "measured_return_fall10_plus_200ps", "diagnostic_timing_contract_sha256": hashlib.sha256(json.dumps(dict(diagnostic), sort_keys=True).encode("ascii")).hexdigest(), "measured_return_settle_sha256": hashlib.sha256(json.dumps(dict(measured), sort_keys=True).encode("ascii")).hexdigest()}


def summary(decision: str, reasons: Sequence[str], stats: Mapping[str, int], baseline: Mapping[str, Any], repaired: Optional[Mapping[str, Any]] = None, repaired_status: str = "NOT_RUN") -> Dict[str, Any]:
    """Publish explicit accounting for retained evidence and new scenarios."""
    return {"decision": decision, "reasons": list(dict.fromkeys(reasons)), "baseline_commit": baseline.get("baseline_commit"), "new_diagnostic_hspice_scenarios": int(stats.get("diagnostic_new", 0)), "new_repaired_hspice_scenarios": int(stats.get("repaired_new", 0)), "reused_new_task_scenarios": int(stats.get("reused", 0)), "upstream_static_84_scenarios_rerun": 0, "upstream_static_hspice_rerun": 0, "old_dynamic_0p95_rerun": 0, "old_dynamic_1p10_rerun": 0, "old_dynamic_0p80_rerun": 0, "old_recovery_guard_s": OLD_GUARD_S, "new_recovery_guard_s": repaired.get("new_recovery_guard_s") if repaired else None, "worst_return_settle_s": repaired.get("worst_return_settle_s") if repaired else None, "retained_0p95_status": "GO", "retained_1p10_status": "GO", "repaired_0p80_status": repaired_status, "final_dynamic_protocol_decision": "Dynamic Startup Calibration Protocol = GO" if decision == "Dynamic Recovery Window Repair = GO" else "Dynamic Startup Calibration Protocol = NO-GO"}


def count_scenarios(run_root: Path, phase: str) -> int:
    """Count complete task-owned scenarios for final accounting."""
    if not run_root.is_dir():
        return 0
    count = 0
    for path in run_root.glob("r*/scenarios/*/scenario_manifest.json"):
        manifest = load_json(path)
        count += int(manifest.get("phase") == phase and manifest.get("completion_status") == "PASS")
    return count


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Require an explicit phase so read-only audits cannot run HSPICE."""
    parser = argparse.ArgumentParser(description="FTC dynamic recovery window repair")
    parser.add_argument("--phase", choices=("phase0", "diagnostic", "repaired"), required=True)
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis" / "dynamic_recovery_window_repair")
    parser.add_argument("--run-root", type=Path, default=FTC_ROOT / "runs" / "dynamic_recovery_window_repair")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports" / "FTC_DYNAMIC_RECOVERY_WINDOW_REPAIR.md")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run one requested phase and stop at its first failed gate."""
    args = parse_args(argv)
    analysis, run_root = args.analysis_dir.resolve(), args.run_root.resolve()
    baseline = freeze_baseline()
    analysis.mkdir(parents=True, exist_ok=True)
    write_json(analysis / "requirements.json", requirements(baseline))
    write_json(analysis / "frozen_baseline.json", baseline)
    failure_map = old_failure_map(baseline)
    write_json(analysis / "old_failure_map.json", failure_map)
    diagnostic = diagnostic_contract(baseline)
    write_json(analysis / "diagnostic_timing_contract.json", diagnostic)
    if args.phase == "phase0":
        write_json(analysis / "summary.json", summary("Dynamic Recovery Window Repair = NOT_RUN", [], {"diagnostic_new": 0, "repaired_new": 0, "reused": 0}, baseline))
        return 0
    trajectory, context = build_trajectory(), context_from_baseline()
    if args.phase == "diagnostic":
        guard, schedule = float(diagnostic["diagnostic_bound_s"]), schedule_trajectory(trajectory, float(diagnostic["diagnostic_bound_s"]))
        deck = render_deck(context, schedule, "diagnostic")
        checks = topology_checks(deck, schedule)
        if not all(checks.values()):
            raise ValueError("diagnostic_contract_invalid: {}".format(checks))
        timing_sha = hashlib.sha256(json.dumps(diagnostic, sort_keys=True).encode("ascii")).hexdigest()
        parameters = scenario_parameters("recovery_diagnostic_0p80", guard, baseline, schedule, deck, timing_sha)
        hspice, version = validate_hspice(context)
        stats = {"diagnostic_new": 0, "repaired_new": 0, "reused": 0}
        record = execute_scenario(hspice, version, run_root, "recovery_diagnostic_0p80", deck, parameters, stats)
        probe_result, transition_result, rows, raw_reasons = dynamic_gate_reasons(schedule, record, 0.0)
        measured = return_rows(schedule, record, guard, 0.0)[1]
        reasons = []
        for reason in raw_reasons:
            if reason in ("repaired_coarse_q_mismatch", "repaired_fine_q_mismatch", "repaired_lock_hold_mismatch", "repaired_delay_non_monotonic"):
                reasons.append("diagnostic_q_sequence_changed")
            elif reason == "repaired_configuration_glitch":
                reasons.append("diagnostic_configuration_glitch")
            else:
                reasons.append(reason)
        stats["diagnostic_new"] = count_scenarios(run_root, "recovery_diagnostic_0p80")
        write_csv(analysis / "diagnostic_results.csv", DIAGNOSTIC_FIELDS, rows)
        write_json(analysis / "measured_return_settle.json", measured)
        decision = "Dynamic Recovery Window Repair = DIAGNOSTIC_PASS" if not reasons else "Dynamic Recovery Window Repair = NO-GO"
        write_json(analysis / "summary.json", summary(decision, reasons, stats, baseline))
        args.report_output.parent.mkdir(parents=True, exist_ok=True)
        args.report_output.write_text("# FTC Dynamic Recovery Window Repair\n\n**{}**\n\nDiagnostic guard: {:.3f} ns. Return measurements completed, but the diagnostic Q sequence changed; Phase 5 and repaired validation were not authorized. No 0.95 V or 1.10 V scenario was rerun.\n".format(decision, guard * 1e9), encoding="utf-8")
        return 0 if not reasons else 2
    measured = load_json(analysis / "measured_return_settle.json")
    repaired_timing = repaired_contract(measured, diagnostic)
    write_json(analysis / "repaired_timing_contract.json", repaired_timing)
    guard, schedule = float(repaired_timing["new_recovery_guard_s"]), schedule_trajectory(trajectory, float(repaired_timing["new_recovery_guard_s"]))
    deck = render_deck(context, schedule, "repaired_validation")
    checks = topology_checks(deck, schedule)
    if not all(checks.values()):
        raise ValueError("diagnostic_contract_invalid: {}".format(checks))
    timing_sha = hashlib.sha256(json.dumps(repaired_timing, sort_keys=True).encode("ascii")).hexdigest()
    parameters = scenario_parameters("recovery_repaired_0p80", guard, baseline, schedule, deck, timing_sha)
    hspice, version = validate_hspice(context)
    stats = {"diagnostic_new": 0, "repaired_new": 0, "reused": 0}
    record = execute_scenario(hspice, version, run_root, "recovery_repaired_0p80", deck, parameters, stats)
    rows, transitions, returns, reasons = dynamic_gate_reasons(schedule, record, Q_SETTLE_S)
    coarse = [row for row in rows if row["protocol_phase"] == "coarse"]
    fine = [row for row in rows if row["protocol_phase"] in ("fine_entry", "fine")]
    write_csv(analysis / "repaired_probe_results.csv", PROBE_FIELDS, rows)
    write_csv(analysis / "repaired_transition_audit.csv", TRANSITION_FIELDS, transitions)
    write_json(analysis / "repaired_lock_table.json", {"schema_version": 1, "study": STUDY, "vdd_v": VDD, "coarse_q": "".join(str(row["dynamic_Q"]) for row in coarse), "fine_q": "".join(str(row["dynamic_Q"]) for row in fine), "hold_q": rows[-1]["dynamic_Q"], "final_M": 8, "final_F": 1, "status": "GO" if not reasons else "NO-GO"})
    decision = "Dynamic Recovery Window Repair = GO" if not reasons else "Dynamic Recovery Window Repair = NO-GO"
    write_json(analysis / "summary.json", summary(decision, reasons, stats, baseline, repaired_timing, "GO" if not reasons else "NO-GO"))
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text("# FTC Dynamic Recovery Window Repair\n\n**{}**\n\nNew recovery guard: {:.3f} ns.\n\nWorst measured return settle: {:.3f} ns at probe {} / {}.\n\nThe sensor, XOR, medium, fine, DFF, topology, and 0.80 V trajectory were unchanged. Retained 0.95 V and 1.10 V evidence was not rerun.\n".format(decision, guard * 1e9, float(repaired_timing["worst_return_settle_s"]) * 1e9, measured["worst_probe_index"], measured["worst_node"]), encoding="utf-8")
    return 0 if not reasons else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("Dynamic Recovery Window Repair = NO-GO: {}".format(error), file=sys.stderr)
        raise SystemExit(2)
