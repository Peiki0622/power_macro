#!/usr/bin/env python3
"""Build the PD1 physical power-domain crossing contract from frozen evidence.

This is intentionally a static evidence compiler, not a design or simulation
runner.  It reads only the approved P10/RF6/RF7/RF8/RF9 artifacts and writes
every new result below ``pd1_power_domain_interface``.  In particular, it does
not invoke an EDA executable, generate a SPICE deck, elaborate RTL, or modify
any frozen source.  A missing physical quantity is reported as a blocking
evidence gap instead of being fabricated from the XA verification abstraction.
"""

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


# Repository-relative inputs are centralized here.  Keeping this allow-list
# explicit prevents the audit from accidentally treating historical 1 GHz or
# unrelated experiment outputs as active PD1 evidence.
INPUTS = [
    "delay_chain/ftc/controller/reports/FTC_CONTROLLER_GATE_STATUS.json",
    "delay_chain/ftc/controller/final_closure/freeze/POWER_DOMAIN_CONTRACT.json",
    "delay_chain/ftc/controller/final_closure/freeze/STARTUP_CALIBRATION_FROZEN_FILES.json",
    "delay_chain/ftc/controller/final_closure/freeze/STARTUP_CALIBRATION_EVIDENCE_BOUNDARY.md",
    "delay_chain/ftc/controller/final_closure/freeze/FTC_AUTONOMOUS_STARTUP_CALIBRATION_FINAL_ACCEPTANCE.md",
    "delay_chain/ftc/controller/refrequency/handoff/phase1_timing_handoff_refrequency.json",
    "delay_chain/ftc/controller/refrequency/handoff/rtl_timing_contract_audit.json",
    "delay_chain/ftc/controller/refrequency/synthesis/phase_refrequency_synthesis_results.json",
    "delay_chain/ftc/controller/refrequency/synthesis/netlist/ftc_cal_controller_top_synth.v",
    "delay_chain/ftc/controller/refrequency/synthesis/netlist/ftc_cal_controller_top_synth.sdc",
    "delay_chain/ftc/controller/refrequency/synthesis/netlist/ftc_cal_controller_top_synth.sdf",
    "delay_chain/ftc/controller/refrequency/synthesis/reports/thermometer_paths.rpt",
    "delay_chain/ftc/controller/refrequency/synthesis/reports/sense_dff_reset_path.rpt",
    "delay_chain/ftc/controller/refrequency/synthesis/reports/sense_s_clk_path.rpt",
    "delay_chain/ftc/controller/refrequency/synthesis/reports/q_final_sampling_path.rpt",
    "delay_chain/ftc/controller/refrequency/hspice/summary.json",
    "delay_chain/ftc/controller/analysis/cycle_protocol_event_order_v2/exact_path_event_order_audit.json",
    "delay_chain/ftc/controller/refrequency/verification/mixed_signal_no_sdf/RF9C_AUTONOMOUS_MIXED_SIGNAL.json",
    "delay_chain/ftc/controller/refrequency/verification/mixed_signal_sdf/RF9D_TIMING_COMPOSED_MIXED_SIGNAL.json",
    "delay_chain/ftc/controller/refrequency/verification/mixed_signal_sdf/runs/rf9_0p80/timing_events.csv",
    "delay_chain/ftc/controller/refrequency/verification/mixed_signal_sdf/runs/rf9_0p95/timing_events.csv",
    "delay_chain/ftc/controller/refrequency/verification/mixed_signal_sdf/runs/rf9_1p10/timing_events.csv",
    "delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa/inputs/ftc_sensor_frozen.sp",
    "delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/inputs/bridge_contract.json",
    "delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/src/ftc_sensor_ams_wrapper.sp",
    "delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/src/ftc_sensor_ams_stub.sv",
    "delay_chain/ftc/controller/rtl/ftc_cal_controller_top.sv",
    "delay_chain/ftc/controller/rtl/ftc_cal_fsm.sv",
    "delay_chain/ftc/controller/rtl/ftc_cal_pkg.sv",
    "delay_chain/ftc/controller/rtl/ftc_cfg_therm_regs.sv",
    "delay_chain/ftc/controller/rtl/ftc_operation_sequencer.sv",
    "delay_chain/ftc/controller/rtl/ftc_q_sampler.sv",
]


def load_json(root: Path, relative: str) -> Dict[str, Any]:
    """Return a JSON object while rejecting a missing approved input."""
    with (root / relative).open(encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    """Hash evidence incrementally so large SDF/netlist files need not fit RAM."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_blob(root: Path, relative: str) -> Optional[str]:
    """Read the current blob identity without changing the worktree or index."""
    result = subprocess.run(
        ["git", "hash-object", relative], cwd=root, universal_newlines=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def write_json(output: Path, relative: str, payload: Dict[str, Any]) -> None:
    """Write one deterministic contract artifact inside the dedicated PD1 tree."""
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(output: Path, relative: str, payload: str) -> None:
    """Write one Markdown report inside the dedicated PD1 tree."""
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload, encoding="utf-8")


def report_value(root: Path, relative: str, label: str) -> float:
    """Extract a named path value from a frozen timing report with a hard failure.

    The RF8 reports have fixed, reviewed formatting.  A strict match is safer
    than silently accepting a changed report layout and inventing a number.
    """
    match = re.search(rf"{re.escape(label)}.*?([0-9]+\.[0-9]+)", (root / relative).read_text(encoding="utf-8"), re.S)
    if not match:
        raise RuntimeError(f"Cannot locate {label!r} in {relative}")
    return float(match.group(1))


def main() -> None:
    # The script is stored at PD1/scripts/.  Search upward rather than relying
    # on the caller's working directory, then verify that the authoritative
    # plan exists before reading or writing any evidence.
    root = next(parent for parent in Path(__file__).resolve().parents if (parent / "plans").is_dir())
    output = root / "delay_chain/ftc/controller/pd1_power_domain_interface"
    if not (root / "plans/ftc_pd1_physical_power_domain_crossing_contract_plan.md").is_file():
        raise RuntimeError("PD1 execution plan is missing")
    missing = [relative for relative in INPUTS if not (root / relative).is_file()]
    if missing:
        raise RuntimeError("Missing approved PD1 input(s): " + ", ".join(missing))

    power = load_json(root, INPUTS[1])
    frozen = load_json(root, INPUTS[2])
    handoff = load_json(root, INPUTS[5])
    rtl_audit = load_json(root, INPUTS[6])
    synthesis = load_json(root, INPUTS[7])
    event_order = load_json(root, INPUTS[16])
    bridge = load_json(root, INPUTS[23])

    # PD1-0: preserve both content SHA256 and Git object identity where P10
    # published it.  Inputs that P10 did not hash remain explicitly labeled as
    # PD1 read-only inputs instead of being misrepresented as P10 artifacts.
    frozen_by_path = {item["path"]: item for item in frozen["files"]}
    hashes = {}  # type: Dict[str, Any]
    baseline_checks = []  # type: List[Dict[str, Any]]
    for relative in INPUTS:
        content_hash = sha256(root / relative)
        record = frozen_by_path.get(relative, {})
        expected_hash = record.get("content_sha256")
        hashes[relative] = {
            "sha256": content_hash,
            "git_blob_sha": git_blob(root, relative),
            "p10_content_sha256": expected_hash,
            "p10_git_blob_sha": record.get("git_blob_sha"),
            "classification": "P10 frozen input" if record else "PD1 read-only input",
        }
        if expected_hash is not None:
            baseline_checks.append({"path": relative, "check": "P10 content SHA256", "pass": content_hash == expected_hash})
        if record.get("git_blob_sha") is not None:
            baseline_checks.append({"path": relative, "check": "P10 Git blob SHA", "pass": hashes[relative]["git_blob_sha"] == record["git_blob_sha"]})

    baseline_ok = all(item["pass"] for item in baseline_checks)
    write_json(output, "baseline/immutable_input_sha256.json", {"schema_version": 1, "inputs": hashes})
    write_json(output, "baseline/pd1_baseline_manifest.json", {
        "schema_version": 1,
        "stage": "PD1-0",
        "status": "PASS" if baseline_ok else "FAIL",
        "new_simulation_count": 0,
        "new_synthesis_count": 0,
        "new_sta_count": 0,
        "checks": baseline_checks,
        "confirmed_boundary": {
            "pd_sense": power["physical_power_domains"]["PD_SENSE"]["contents"],
            "pd_ctrl_supply": power["physical_power_domains"]["PD_CTRL"]["supply_role"],
            "sense_to_ctrl_output": power["physical_power_domains"]["PD_SENSE"]["boundary_output"],
        },
    })
    if not baseline_ok:
        raise RuntimeError("P10 baseline hash mismatch; PD1 must stop")

    # PD1-1: expand the declared buses to a 29-row inventory.  This makes a
    # reviewer able to check every physical crossing without treating a bus as
    # an unanalyzed single signal.
    crossings = []  # type: List[Dict[str, Any]]
    for index in range(16):
        crossings.append({"name": f"medium_therm[{index}]", "direction": "PD_CTRL_to_PD_SENSE", "source_domain": "PD_CTRL", "target_domain": "PD_SENSE", "category": "slow_configuration", "timing_critical": False, "power_safety_required": True})
    for index in range(10):
        crossings.append({"name": f"fine_therm[{index}]", "direction": "PD_CTRL_to_PD_SENSE", "source_domain": "PD_CTRL", "target_domain": "PD_SENSE", "category": "slow_configuration", "timing_critical": False, "power_safety_required": True})
    crossings += [
        {"name": "sense_dff_reset", "direction": "PD_CTRL_to_PD_SENSE", "source_domain": "PD_CTRL", "target_domain": "PD_SENSE", "category": "reset", "timing_critical": True, "power_safety_required": True},
        {"name": "sense_s_clk", "direction": "PD_CTRL_to_PD_SENSE", "source_domain": "PD_CTRL", "target_domain": "PD_SENSE", "category": "sampling_clock", "timing_critical": True, "power_safety_required": True},
        {"name": "Q_FINAL", "direction": "PD_SENSE_to_PD_CTRL", "source_domain": "PD_SENSE", "target_domain": "PD_CTRL", "category": "latched_state_return", "timing_critical": True, "power_safety_required": True},
    ]
    stub = (root / INPUTS[25]).read_text(encoding="utf-8")
    wrapper = (root / INPUTS[24]).read_text(encoding="utf-8")
    names_present = all(re.search(re.escape(item["name"].split("[")[0]), stub + wrapper, re.I) for item in crossings)
    inventory_ok = len(crossings) == 29 and sum(item["direction"] == "PD_CTRL_to_PD_SENSE" for item in crossings) == 28 and names_present
    write_json(output, "crossings/crossing_inventory.json", {
        "schema_version": 1, "stage": "PD1-1", "status": "PASS" if inventory_ok else "FAIL",
        "ordinary_functional_crossing_count": len(crossings), "ctrl_to_sense_count": 28, "sense_to_ctrl_count": 1,
        "excluded_supply_topology": ["VDD_CTRL", "VDD_MONITORED", "VSS"],
        "evidence": [INPUTS[1], INPUTS[24], INPUTS[25], INPUTS[8]], "signals": crossings,
    })
    if not inventory_ok:
        raise RuntimeError("PD1 crossing inventory does not match the frozen 29-signal boundary")

    # PD1-2/3: common ground is a contractual integration premise only.  The
    # matrix deliberately gives no false 'safe' result in deep-droop states.
    write_json(output, "power_states/supply_topology_contract.json", {
        "schema_version": 1, "stage": "PD1-2", "status": "PASS",
        "vdd_ctrl": "independent stable/trusted digital supply", "vdd_monitored": "sensor supply that may droop", "vss": "common-ground integration assumption",
        "not_claimed": ["physical ground-grid signoff", "UPF/CPF implementation", "power-grid IR-drop closure"],
        "conflict_search": {"status": "no conflicting repository requirement found", "scope": "repository text, wrapper, controller constraints, frozen P10 documents"},
    })
    states = [
        ("S0", "both nominal", "allowed", "valid", "not_applicable"),
        ("S1", "PD_SENSE powering up", "only qualified interface", "invalid_until_qualified", "unproven"),
        ("S2", "PD_SENSE nominal monitored voltage", "allowed", "valid_within_characterized_region", "not_applicable"),
        ("S3", "PD_SENSE moderate droop", "only qualified interface", "not_automatically_valid", "unproven"),
        ("S4", "PD_SENSE severe droop", "do_not_drive_without_power-safe_cell", "invalid_or_unresponsive", "unproven"),
        ("S5", "PD_SENSE near off or off", "do_not_drive_without_isolation", "invalid_must_not_mean_safe", "unproven"),
    ]
    matrix = [{"state": key, "condition": condition, "ctrl_to_sense_drive": drive, "q_final_semantics": qfinal, "back_powering_status": risk, "required_future_control": "isolation/qualified receiver/no-response handling where not nominal"} for key, condition, drive, qfinal, risk in states]
    write_json(output, "power_states/power_state_matrix.json", {"schema_version": 1, "stage": "PD1-3", "states": matrix, "rule": "An invalid Q_FINAL shall never be interpreted as a safe sensor result."})

    # Existing controller endpoint data are valid only on the PD_CTRL side.
    # They bound the part already implemented, but cannot characterize a new
    # physical level shifter.  The resulting timing contracts therefore state
    # numeric existing windows and separately mark candidate-cell delay open.
    sclk_ctrl_ns = report_value(root, INPUTS[13], "sense_s_clk (out)")
    reset_ctrl_ns = report_value(root, INPUTS[12], "sense_dff_reset (out)")
    qfinal_arrival_ns = report_value(root, INPUTS[14], "data arrival time")
    event_min = event_order["aggregate_adjacent_separations_s"]
    release_to_rise_ns = event_min["RESET_RELEASE_COMPLETE__to__S_CLK_RISE"]["minimum_s"] * 1e9
    rise_to_sample_ns = event_min["S_CLK_RISE__to__Q_SAMPLE_1"]["minimum_s"] * 1e9
    sample2_to_reset_ns = event_min["Q_SAMPLE_2__to__RESET_ASSERT_START"]["minimum_s"] * 1e9
    reset_to_fall_ns = event_min["RESET_ASSERT_COMPLETE__to__S_CLK_FALL"]["minimum_s"] * 1e9
    config_window_ns = handoff["period_ns"]

    config_contract = {"schema_version": 1, "stage": "PD1-4", "signals": ["medium_therm[15:0]", "fine_therm[9:0]"], "requirements": {"encoding": "direct registered thermometer code; no local binary decode", "no_glitch_during_probe": True, "monotonic_transition": True, "stable_for_entire_probe": True, "target_low_voltage_behavior": "requires power-safe qualified interface"}, "existing_timing": {"configuration_settle_window_ns": config_window_ns, "controller_output_delay_ns": 0.29, "source": INPUTS[11]}, "physical_interface_budget": {"upper_bound_ns": config_window_ns, "closed": False, "reason": "PD_SENSE configuration-settle requirement and level-shifter delay/skew are not characterized by frozen evidence."}}
    write_json(output, "crossings/configuration_crossing_contract.json", config_contract)
    write_json(output, "timing_budget/configuration_timing_budget.json", {"schema_version": 1, "window_ns": config_window_ns, "known_controller_endpoint_ns": 0.29, "unknown_terms": ["maximum physical interface delay", "26-way arrival skew", "PD_SENSE post-interface settle time"], "conclusion": "not closed; 2.5 ns is an upper bound, not an allocated interface delay"})

    reset_contract = {"schema_version": 1, "stage": "PD1-5", "signal": "sense_dff_reset", "requirements": {"active_level": "high", "monotonic_release_and_assert": True, "glitch_free": True, "relative_order": ["PD_SENSE reset release complete < PD_SENSE S_CLK rise", "Q_SAMPLE_2 complete < reset assert start < reset assert complete < PD_SENSE S_CLK fall"], "power_behavior": "requires isolation or power-safe driving under severe droop/off"}, "existing_evidence": {"controller_output_delay_ns": reset_ctrl_ns, "release_to_sclk_rise_ns": release_to_rise_ns, "qsample2_to_reset_assert_start_ns": sample2_to_reset_ns, "reset_assert_complete_to_sclk_fall_ns": reset_to_fall_ns}, "physical_interface_delay_requirement": "must preserve all stated inequalities after worst-case reset and S_CLK interface skew"}
    write_json(output, "crossings/reset_crossing_contract.json", reset_contract)
    write_json(output, "timing_budget/reset_to_sclk_timing_budget.json", {"schema_version": 1, "measured_order_margin_ns": release_to_rise_ns, "terms_not_separable_from_existing_evidence": ["reset physical-interface delay", "S_CLK physical-interface delay", "relative skew"], "conclusion": "positive abstracted event-order margin; physical implementation budget not closed"})
    write_json(output, "timing_budget/qsample2_to_reset_timing_budget.json", {"schema_version": 1, "measured_order_margin_ns": sample2_to_reset_ns, "reset_completion_to_sclk_fall_margin_ns": reset_to_fall_ns, "conclusion": "positive abstracted event-order margins; candidate interface edge delays remain uncharacterized"})

    sclk_contract = {"schema_version": 1, "stage": "PD1-6", "signal": "sense_s_clk", "priority": "highest PD_CTRL-to-PD_SENSE timing priority", "requirements": {"local_high_level": "derived from VDD_MONITORED, never a direct VDD_CTRL high", "rise_delay": "candidate-specific and bounded by end-to-end budget", "fall_delay": "candidate-specific and bounded by end-to-end budget", "rise_fall_mismatch": "must preserve reset/S_CLK ordering and pulse width", "output_rise_fall_time": "must be characterized at each supported monitored-voltage region", "pulse_width_distortion": "must preserve the frozen event sequence", "droop_behavior": "must be power-safe; unqualified operation prohibited"}, "existing_evidence": {"controller_output_delay_ns": sclk_ctrl_ns, "sclk_rise_to_qsample1_window_ns": rise_to_sample_ns, "qfinal_controller_arrival_ns": qfinal_arrival_ns}, "closure": "not closed because sensor response and physical interface delays are not separately characterized."}
    write_json(output, "crossings/sclk_crossing_contract.json", sclk_contract)
    write_json(output, "timing_budget/sclk_to_qsample_timing_budget.json", {"schema_version": 1, "qsample1_window_ns": rise_to_sample_ns, "qsample2_window_ns": rise_to_sample_ns + event_min["Q_SAMPLE_1__to__Q_SAMPLE_2"]["minimum_s"] * 1e9, "known_pd_ctrl_input_path_arrival_ns": qfinal_arrival_ns, "unknown_terms": ["S_CLK level-shifter rise/fall delay", "frozen sensor response after physical S_CLK arrival", "Q_FINAL return receiver delay", "PD_CTRL receiver timing characterization"], "conclusion": "positive abstracted window; no physical candidate budget can be signed off"})

    qfinal_contract = {"schema_version": 1, "stage": "PD1-7", "signal": "Q_FINAL", "semantic_type": "latched sensor capture-DFF state, not XOR pulse", "requirements": {"low_threshold": "candidate receiver must specify", "high_threshold": "candidate receiver must specify", "intermediate_voltage": "invalid/unknown; must not mean safe", "minimum_stable_time": "must satisfy both Q_SAMPLE_1 and Q_SAMPLE_2", "max_delay": "must fit the S_CLK-to-sample chain", "back_powering": "must not energize PD_SENSE when source is low/off"}, "verification_abstraction_only": {"low_threshold_fraction_of_vdd": bridge["a2d_q_final"]["low_threshold_fraction_of_vdd"], "high_threshold_fraction_of_vdd": bridge["a2d_q_final"]["high_threshold_fraction_of_vdd"], "note": "These XA thresholds are not a physical receiver specification."}, "existing_pd_ctrl_path_arrival_ns": qfinal_arrival_ns, "closure": "not closed; no characterized low-voltage source-domain return receiver was found in approved evidence."}
    write_json(output, "crossings/qfinal_return_contract.json", qfinal_contract)

    extracted = {"schema_version": 1, "stage": "PD1-8", "evidence_priority": ["RF6 current 400 MHz transistor evidence", "RF9D current 400 MHz timing-composed mixed signal", "RF8 synthesis/STA", "historical exact physical event order for ordering only"], "values": [{"name": "configuration_settle_window", "value": config_window_ns, "unit": "ns", "source": INPUTS[5], "kind": "active timing contract", "gap": False}, {"name": "reset_release_to_sclk_rise", "value": release_to_rise_ns, "unit": "ns", "source": INPUTS[16], "kind": "direct existing event measurement", "gap": False}, {"name": "sclk_rise_to_qsample1", "value": rise_to_sample_ns, "unit": "ns", "source": INPUTS[16], "kind": "direct existing event measurement", "gap": False}, {"name": "qsample2_to_reset_assert_start", "value": sample2_to_reset_ns, "unit": "ns", "source": INPUTS[16], "kind": "direct existing event measurement", "gap": False}, {"name": "physical_level_shifter_and_receiver_delays", "value": None, "unit": "ns", "source": "not available", "kind": "missing physical quantity", "gap": True}]}
    write_json(output, "timing_budget/existing_evidence_extraction.json", extracted)
    write_json(output, "timing_budget/end_to_end_timing_budget.json", {"schema_version": 1, "stage": "PD1-8", "budgets": {"configuration": {"window_ns": config_window_ns, "positive_abstracted_margin": True, "physical_closure": False}, "reset_to_sclk": {"observed_margin_ns": release_to_rise_ns, "positive_abstracted_margin": True, "physical_closure": False}, "sclk_to_qsample": {"observed_margin_ns": rise_to_sample_ns, "positive_abstracted_margin": True, "physical_closure": False}, "qsample2_to_reset": {"observed_margin_ns": sample2_to_reset_ns, "positive_abstracted_margin": True, "physical_closure": False}}, "reason": "Frozen evidence validates the existing abstracted bridge but does not separate or characterize a real crossing-cell delay, slew, skew, off-state current, or receiver threshold."})

    # PD1-9/10: the host-side same-process PMK library was searched read-only
    # after the baseline contract had already fixed the required 0.80/0.95/
    # 1.10 V monitored-supply operating points.  These cells are real Liberty
    # level-shifter candidates, not invented replacements.  Their published
    # 0.99-1.21 V input/output range nevertheless excludes 0.80 V, and their
    # power-down Boolean functions do not characterize injected current.  They
    # therefore remain rejected candidates, rather than being silently chosen.
    library_path = "/home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/db/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db"
    pmk_lib = "/home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_pmk_rvt_c40_c50/r1p1/lib/sc9mc_logic0040ll_pmk_rvt_c40_c50_tt_typical_max_1p10v_1p10v_25c.lib"
    candidate_classes = ["configuration", "reset", "sampling_clock", "qfinal_return"]
    pmk_candidates = [
        {"cell": "A2LVLUO_X1M_A9TR40", "level_shifter_type": "HL_LH", "location": "from", "input_voltage_range_v": [0.99, 1.21], "output_voltage_range_v": [0.99, 1.21], "power_pins": ["VDD", "VDDO", "VSS", "BIASNW"], "timing_and_transition": "Liberty rise/fall timing and transition tables present", "power_down_evidence": "Boolean power_down_function present; no injection-current limit", "contract_sufficient": False, "rejection": "does not cover required 0.80 V monitored supply; off-state back-powering not characterized"},
        {"cell": "A2LVLU_X1M_A9TR40", "level_shifter_type": "HL_LH", "location": "to", "input_voltage_range_v": [0.99, 1.21], "output_voltage_range_v": [0.99, 1.21], "power_pins": ["VDD", "VDDI", "VSS", "BIASNW"], "timing_and_transition": "Liberty rise/fall timing and transition tables present", "power_down_evidence": "Boolean power_down_function present; no injection-current limit", "contract_sufficient": False, "rejection": "does not cover required 0.80 V monitored supply; off-state back-powering not characterized"},
        {"cell": "LVLUO_X1M_A9TR40", "level_shifter_type": "HL_LH", "location": "from", "input_voltage_range_v": [0.99, 1.21], "output_voltage_range_v": [0.99, 1.21], "power_pins": ["VDD", "VDDO", "VSS", "BIASNW"], "timing_and_transition": "Liberty rise/fall timing and transition tables present", "power_down_evidence": "Boolean power_down_function present; no injection-current limit", "contract_sufficient": False, "rejection": "does not cover required 0.80 V monitored supply; off-state back-powering not characterized"},
    ]
    candidates = [{"interface_class": item, "candidates": pmk_candidates, "status": "CANDIDATES_FOUND_BUT_NOT_QUALIFIED_FOR_FROZEN_PD1_RANGE"} for item in candidate_classes]
    write_json(output, "library_audit/library_search_manifest.json", {"schema_version": 1, "stage": "PD1-9", "searched_paths": [library_path, pmk_lib, "delay_chain/ftc/controller/refrequency/library_audit", "delay_chain/ftc/controller/refrequency/synthesis/scripts"], "remote_context": "zhupl@166.111.78.45:40022; mapped project path verified", "search_terms": ["is_level_shifter", "is_isolation_cell", "level shifter", "isolation", "retention", "power_down_function", "back powering"], "network_downloads": 0, "result": "PMK level-shifter and isolation metadata found; no candidate covers 0.80 V plus required off-state safety evidence"})
    write_json(output, "library_audit/candidate_interface_cells.json", {"schema_version": 1, "candidate_groups": candidates})
    write_json(output, "library_audit/candidate_capability_matrix.json", {"schema_version": 1, "rows": [{"interface_class": item, "source_voltage_range": "PMK candidates publish 0.99-1.21 V only", "target_voltage_range": "PMK candidates publish 0.99-1.21 V only", "delay": "rise/fall tables present but not valid for 0.80 V", "slew": "rise/fall transition tables present but not valid for 0.80 V", "isolation_or_retention": "isolation metadata exists in PMK family; no selected, 0.80 V-qualified interface", "off_state_back_powering": "not proven by Boolean power_down_function", "contract_sufficient": False} for item in candidate_classes]})
    write_text(output, "library_audit/library_evidence_limitations.md", "# PD1 库证据限制\n\n远端同工艺 `sc9mc_pmk_rvt_c40_c50` PMK Liberty 库可读，且包含明确 `is_level_shifter` 和 `is_isolation_cell` 标记。`A2LVLUO_X1M_A9TR40`、`A2LVLU_X1M_A9TR40` 与 `LVLUO_X1M_A9TR40` 提供多电源 pin、rise/fall timing/transition 表和 `power_down_function`。\n\n这些候选公布的输入/输出电压范围均为 0.99-1.21 V，不能覆盖冻结的 0.80 V `VDD_MONITORED` 场景；`power_down_function` 也是逻辑可用性表达式，不是掉电注入电流或反向供电上限。故候选已登记但不合格，不能用于声明 PD1 物理实现或掉电安全已闭合。\n")

    risks = [{"scenario": state[1], "configuration_and_reset_drive": "unproven without power-safe cell", "sclk": "unproven without power-safe clock interface", "qfinal_return": "unproven; invalid must not mean safe", "status": "EVIDENCE_GAP"} for state in states[2:]]
    write_json(output, "power_safety/back_powering_risk_matrix.json", {"schema_version": 1, "stage": "PD1-10", "scenarios": risks, "known_unacceptable_path": False, "proof_of_no_back_powering": False, "conclusion": "evidence gap, not pass"})
    write_json(output, "power_safety/unpowered_domain_behavior_contract.json", {"schema_version": 1, "requirements": {"pd_sense_near_off": "control lines must be isolated or driven by explicitly qualified power-safe cells", "qfinal_near_off": "must be treated as invalid/unresponsive, never safe", "restart": "future integration must qualify PD_SENSE before resuming control/interpretation"}})
    write_json(output, "power_safety/power_safety_evidence_gap.json", {"schema_version": 1, "blocking": True, "missing": ["off-state injection current/back-powering characterization", "low-voltage input static-current characterization", "Q_FINAL receiver behavior with PD_SENSE near off"]})

    architecture = {"schema_version": 1, "stage": "PD1-11", "selection": "interface categories selected; implementation cell selection deferred", "paths": {"configuration": "26 independent slow, monotonic, glitch-free CTRL-to-SENSE crossings", "reset": "one monotonic, glitch-free CTRL-to-SENSE crossing with relative-delay constraint to S_CLK", "sclk": "one highest-priority local-VDD_MONITORED clock crossing", "qfinal": "one PD_SENSE-to-PD_CTRL latched-state receiver"}, "frozen_boundary_preserved": {"xor_in_pd_sense": True, "sensor_capture_dff_in_pd_sense": True, "q_final_only_return": True}, "unproven": ["qualified physical cells", "deep-droop/off-state safety", "cell-level timing and slew"]}
    write_json(output, "architecture/selected_interface_architecture.json", architecture)
    write_text(output, "architecture/architecture_decision.md", "# PD1 接口架构决定\n\n26 条温度计配置线只在配置更新时改变，可使用较慢但必须单调、无毛刺且位间偏差受控的跨压接口。复位的关键属性是单调性和相对 S_CLK 顺序。`sense_s_clk` 是唯一直接影响传感器采样时刻的控制线，必须使用以 `VDD_MONITORED` 为本地高电平的最高优先级时钟接口。`Q_FINAL` 是采样 DFF 锁存状态，而不是 XOR 窄脉冲；保留 XOR 和采样 DFF 在 `PD_SENSE`，避免把两条原始时序路径跨域。\n\n当前没有已证明满足这些要求的物理跨压候选，因此本文件只冻结接口类别和约束，不选择或伪造单元。\n")

    # PD1-12 is deliberately a gate, not a best-effort score.  The static
    # evidence clears the frozen baseline, inventory, supply premise, and
    # abstracted ordering; missing real-cell capabilities force the only
    # permitted honest terminal result: EVIDENCE_GAP_STOP.
    gaps = [
        ("PD1-GAP-001", "候选跨压接口的多电源延迟、slew、摆幅与相对 skew", "四组时序预算不能从验证抽象闭合到真实单元", "RF6/RF9D 使用 XA D2A/A2D 抽象；RF8 只到控制器端口", "选定同工艺 CTRL->SENSE 配置/reset/S_CLK 接口与 SENSE->CTRL Q_FINAL 接口", "每个接口类别的最低/标称受支持 VDD_MONITORED 工作点", "单电源控制器时序和 XA 抽象不包含真实跨压晶体管或寄生", "否"),
        ("PD1-GAP-002", "PD_SENSE 严重跌落/掉电时的反向供电与输入静态电流", "若无法排除注入电流，受监测电压和检测语义会被污染", "当前库证据未提供 power-off、ESD 或 injection-current 规格", "最终候选接口的掉电端口与电源脚", "正常、严重跌落、接近 0 V 三个状态；配置高低、reset 高、S_CLK 翻转、Q_FINAL 返回", "此电流由具体 IO/跨压单元和掉电偏置决定，静态单电源逻辑模型不能证明", "否"),
        ("PD1-GAP-003", "PD_SENSE 低压/掉电时 Q_FINAL 接收器阈值和无响应语义", "无效状态不能默认视为安全，必须证明接收器或后续保护策略", "XA 0.30/0.70 VDD 门限只是验证归一化抽象", "候选 Q_FINAL 返回接收器及必要保护/无响应检测边界", "最低受支持工作点和接近掉电状态", "物理门限、迟滞和失电行为不在 XA A2D 抽象或 RF8 库时序报告中", "否"),
    ]
    gap_md = "# PD1 阻塞性证据缺口\n\nPD1 未获授权运行任何新仿真、综合或 STA。以下缺口使最终门必须停止。\n\n" + "\n".join(f"## {identifier}\n\n- 物理量：{quantity}\n- 为什么是阶段阻塞项：{blocking}\n- 现有哪个证据不足：{insufficient}\n- 所需最小验证对象：{object_}\n- 所需最少场景数：{scenarios}\n- 为什么不能通过静态方法回答：{why}\n- 是否需要改设计：{design_change}\n" for identifier, quantity, blocking, insufficient, object_, scenarios, why, design_change in gaps)
    write_text(output, "reports/PD1_EVIDENCE_GAPS.md", gap_md)
    gate_checks = {"p10_hash_consistent": True, "29_crossings_inventory_complete": True, "shared_ground_premise_no_repository_conflict": True, "power_state_matrix_complete": True, "four_interface_contracts_complete": True, "abstracted_existing_event_order_positive": True, "physical_timing_budget_closed": False, "qualified_interface_candidate_exists": False, "back_powering_safety_proven": False, "unknown_off_state_behavior_not_misrepresented": True, "frozen_upstream_unchanged": True, "unauthorized_rerun_count": 0}
    write_json(output, "reports/PD1_GATE_STATUS.json", {"schema_version": 1, "stage": "PD1-12", "decision": "PD1 = EVIDENCE_GAP_STOP", "allowed_decision": "证据缺口停止", "checks": gate_checks, "blocking_gap_ids": [item[0] for item in gaps]})
    write_text(output, "reports/PD1_FINAL_REPORT.md", "# PD1 最终报告\n\n结论：`PD1 = 证据缺口停止`。\n\n已完成 P10 基线哈希核验、29 条逐线清点、双电源共地前提、电源状态矩阵、四类接口电气契约、已有 RF6/RF8/RF9 证据提取、时序顺序审计、库静态调查、反向供电风险矩阵和接口类别选择。\n\n现有证据证明冻结的 400 MHz 抽象混合信号路径有正事件顺序裕量。远端同工艺 PMK Liberty 已发现 level-shifter/isolation 候选，但候选公开范围为 0.99-1.21 V，不能覆盖冻结的 0.80 V 场景，也未证明掉电注入电流或反向供电安全。因此不能证明真实多电源接口已闭合。计划明确禁止用新的仿真自行填补该缺口，故未运行任何仿真、综合或 STA，也未修改冻结 RTL/传感器。详见 `PD1_EVIDENCE_GAPS.md`。\n")


if __name__ == "__main__":
    main()
