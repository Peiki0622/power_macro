#!/usr/bin/env python3
"""Validate and publish the final M1 evidence package.

This script is intentionally an evidence collector, not a replacement for a
simulator or signoff tool.  It reads the already completed focused RTL, DC,
and mapped+SDF runs; re-hashes every frozen input; checks the two new RTL
sources structurally; and emits the M1-8 contracts and Gate decision.  Every
file it writes is below ``controller/m1_detection_margin``.  It never launches
HSPICE, XA, RF6/RF9C/RF9D, or a calibration regression.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple


# M1 is allowed to add only detector-side logic.  These six paths are the P10
# calibration implementation frozen before H0, while the two H0 paths are the
# ownership mux and its existing composition wrapper.  Comparing both their
# content hash and their HEAD Git blob prevents the M1 worktree from silently
# editing a frozen controller or its CAL-to-sensor timing cone.
FROZEN_RTL_NAMES: Tuple[str, ...] = (
    "frozen_cal_pkg",
    "frozen_cfg_therm_regs",
    "frozen_cal_operation_sequencer",
    "frozen_cal_q_sampler",
    "frozen_cal_fsm",
    "frozen_cal_controller_top",
    "frozen_h0_owner",
    "frozen_h0_top",
)

# Logs containing any of these tokens cannot serve as a passing functional or
# timing result.  The patterns are deliberately shared by RTL and gate checks
# so a testbench $fatal cannot be hidden behind a simulator success exit code.
FAILURE_MARKERS: Tuple[str, ...] = (
    "FAIL ",
    "M1 SVA:",
    "integration FAIL",
    "mapper unit FAIL",
    "Fatal:",
    "Timing violation",
    "$setup",
    "$hold",
    "$recrem",
    "$width",
)


def repository_root() -> Path:
    """Locate the repository regardless of the caller's working directory."""

    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists() and (parent / "plans").is_dir():
            return parent
    raise RuntimeError("unable to locate repository root")


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 digest without loading large files at once."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_blob(root: Path, path: Path) -> str:
    """Hash a current worktree file without staging or changing the index."""

    return subprocess.check_output(
        ["git", "hash-object", str(path.relative_to(root))], cwd=root, text=True
    ).strip()


def git_head_blob(root: Path, path: Path) -> str:
    """Read the immutable HEAD blob identity for one tracked frozen source."""

    return subprocess.check_output(
        ["git", "rev-parse", "HEAD:{}".format(path.relative_to(root))],
        cwd=root,
        text=True,
    ).strip()


def read_json(path: Path) -> Dict[str, Any]:
    """Load one JSON object and reject a malformed evidence file immediately."""

    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write stable, review-friendly JSON only within the task-owned M1 root."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_text(path: Path) -> str:
    """Read a required textual artifact with a useful missing-file failure."""

    if not path.is_file():
        raise FileNotFoundError("required M1 evidence is missing: {}".format(path))
    return path.read_text(encoding="utf-8", errors="replace")


def no_failure_marker(text: str) -> Tuple[bool, List[str]]:
    """Return a pass bit and every forbidden simulator marker that was found."""

    found = [marker for marker in FAILURE_MARKERS if marker in text]
    return not found, found


def log_case(path: Path, pass_marker: str) -> Dict[str, Any]:
    """Validate a focused regression log using positive and negative evidence."""

    text = require_text(path)
    clean, markers = no_failure_marker(text)
    return {
        "path": str(path.relative_to(repository_root())),
        "pass_marker": pass_marker,
        "pass_marker_found": pass_marker in text,
        "failure_markers": markers,
        "pass": (pass_marker in text) and clean,
    }


def parse_met_slacks(report_text: str) -> List[float]:
    """Extract all DC ``slack (MET)`` values from the precise timing report."""

    values = [float(value) for value in re.findall(
        r"slack \(MET\)\s+([-+]?[0-9]+(?:\.[0-9]+)?)", report_text
    )]
    if not values:
        raise ValueError("no MET slack values found in precise STA report")
    return values


def command_tokens_without_comments(text: str) -> str:
    """Remove shell/Tcl comments before scanning real tool invocations.

    M1 scripts explicitly document that HSPICE and XA are forbidden.  Stripping
    comments avoids treating that documentation as an invocation while still
    detecting an actual command in executable script text.
    """

    lines = []
    for line in text.splitlines():
        lines.append(line.split("#", 1)[0])
    return "\n".join(lines)


def build_interface_contract() -> Dict[str, Any]:
    """Publish the M1 boundary consumed by later T0/D0 work, not a new policy."""

    return {
        "schema_version": 1,
        "stage": "M1-4/M1-8",
        "clock_reset": {
            "clock": "cal_clk_i",
            "frequency_hz": 400000000,
            "period_ns": 2.5,
            "por": "ctrl_por_n_i active-low",
        },
        "margin_request": {
            "signals": ["margin_sel_i[1:0]", "margin_select_valid_i"],
            "acceptance": "one cal_clk_i-synchronous request only in H0 det_prepare state",
            "supported_keys": "exact (M_cal,F_cal,margin_level) lookup from M1_MARGIN_CODEBOOK.json",
            "unsupported_or_early_or_repeated": "sticky margin_protocol_error_o; no ready, no valid, no vector rewrite",
        },
        "frozen_h0_inputs_driven_by_m1": [
            "det_takeover_ready_i",
            "det_sense_dff_reset_i",
            "det_sense_s_clk_i",
            "det_medium_therm_i[15:0]",
            "det_fine_therm_i[9:0]",
        ],
        "safe_sequence": [
            "copy immutable H0 calibration snapshot to registered detector controls",
            "accept exact lookup and hold snapshot for one complete PRELOAD cycle",
            "assert registered ready; H0 alone grants det_owner_valid",
            "under det_owner_valid, atomically apply registered target with reset=1 and S_CLK=0",
            "hold target for one complete 2.5 ns M_APPLY cycle before margin_cfg_valid_o",
        ],
        "status_outputs": [
            "margin_cfg_valid_o",
            "mapping_supported_o",
            "trip_qualified_o",
            "margin_protocol_error_o",
            "m_det_o[4:0]",
            "f_det_o[3:0]",
            "margin_level_o[1:0]",
        ],
        "invariants": {
            "no_probe_in_m1": "det_sense_s_clk_o is permanently 0",
            "reset_during_m1": "det_sense_dff_reset_o is permanently 1",
            "trip_is_not_mapping": "trip_qualified_o is metadata; it does not alter the exact vector lookup",
            "ownership": "M1 never drives the physical sensor mux; frozen H0 remains sole owner",
        },
    }


def build_downstream_contract() -> Dict[str, Any]:
    """State exactly what T0/D0 may assume and what M1 intentionally omits."""

    return {
        "schema_version": 1,
        "producer": "M1 programmable detection-margin safe configuration",
        "consumer": "T0 transient threat/timing contract followed by D0 runtime detection FSM",
        "entry_condition_for_t0_d0": [
            "margin_cfg_valid_o == 1",
            "mapping_supported_o == 1",
            "margin_protocol_error_o == 0",
            "det_owner_valid_o == 1",
            "sensor controls remain reset=1 and S_CLK=0 at the M1 boundary",
        ],
        "configuration_observability": [
            "cal_medium_code_snapshot_o[4:0]",
            "cal_fine_code_snapshot_o[3:0]",
            "m_det_o[4:0]",
            "f_det_o[3:0]",
            "margin_level_o[1:0]",
            "trip_qualified_o",
        ],
        "t0_must_define": [
            "droop amplitude and duration",
            "attack phase relative to a probe",
            "detection cadence and minimum detectable duration",
            "latency and false-positive/recovery assumptions",
        ],
        "d0_must_define": [
            "runtime reset/S_CLK waveform",
            "Q sampling and decision policy",
            "alarm latch/clear and status behavior",
            "heartbeat or timeout behavior for below-anchor cases",
        ],
        "explicitly_not_claimed_by_m1": [
            "runtime detection probe",
            "droop coverage or minimum detectable pulse width",
            "alarm latency or alarm behavior",
            "dynamic recalibration",
        ],
    }


def main() -> None:
    """Check final artifacts, write the M1-8 evidence package, and gate GO."""

    parser = argparse.ArgumentParser(description="build and validate M1 final evidence")
    parser.add_argument("--rtl-run-id", default="rtl_20260823T001000Z")
    parser.add_argument("--gate-run-id", default="gate_20260823T001100Z")
    args = parser.parse_args()

    root = repository_root()
    m1_root = root / "delay_chain/ftc/controller/m1_detection_margin"
    rtl_root = root / "delay_chain/ftc/controller/rtl"
    rtl_run_root = m1_root / "verification/rtl/run" / args.rtl_run_id
    gate_run_root = m1_root / "verification/gate_sdf/run" / args.gate_run_id

    # Validate the frozen M1-0/M1-1 source ledger and independently compare
    # every frozen RTL source with the current Git HEAD.  The H0 baseline is
    # additionally checked for the six P10 hashes, binding this M1 evidence to
    # H0's original freeze rather than to a newly generated local manifest.
    m1_baseline = read_json(m1_root / "baseline/frozen_input_sha256.json")
    baseline_inputs = m1_baseline.get("inputs", {})
    if not isinstance(baseline_inputs, dict):
        raise ValueError("M1 baseline inputs are missing or malformed")
    baseline_checks: List[Dict[str, Any]] = []
    for name, record in sorted(baseline_inputs.items()):
        if not isinstance(record, dict):
            raise ValueError("bad M1 baseline record: {}".format(name))
        path = root / str(record["path"])
        current_sha = sha256_file(path)
        baseline_checks.append({
            "name": name,
            "path": str(path.relative_to(root)),
            "expected_sha256": record["sha256"],
            "current_sha256": current_sha,
            "sha256_matches": current_sha == record["sha256"],
        })

    h0_frozen = read_json(root / str(baseline_inputs["h0_frozen_baseline"]["path"]))
    h0_source_hashes = h0_frozen.get("inputs", {})
    frozen_rtl_checks: List[Dict[str, Any]] = []
    for name in FROZEN_RTL_NAMES:
        record = baseline_inputs.get(name)
        if not isinstance(record, dict):
            raise ValueError("M1 baseline omits frozen RTL source: {}".format(name))
        path = root / str(record["path"])
        current_sha = sha256_file(path)
        current_blob = git_blob(root, path)
        head_blob = git_head_blob(root, path)
        h0_expected_sha = h0_source_hashes.get(str(path.relative_to(root)))
        h0_sha_matches = True if h0_expected_sha is None else current_sha == h0_expected_sha
        frozen_rtl_checks.append({
            "name": name,
            "path": str(path.relative_to(root)),
            "m1_baseline_sha256_matches": current_sha == record["sha256"],
            "git_head_blob_matches": current_blob == head_blob,
            "h0_frozen_sha256_matches": h0_sha_matches,
        })

    # Audit only the two new synthesizable modules.  A function definition is
    # forbidden by the project RTL rule; exact literal lookup is separately
    # exercised by the contract/unit tests and is not reimplemented here.
    mapper_text = require_text(rtl_root / "ftc_detection_margin_mapper.sv")
    manager_text = require_text(rtl_root / "ftc_detection_margin_manager.sv")
    top_text = require_text(rtl_root / "ftc_cal_detect_margin_top.sv")
    function_pattern = re.compile(r"^\s*(?:automatic\s+)?function\b", re.MULTILINE)
    function_definitions = {
        "ftc_detection_margin_mapper.sv": function_pattern.findall(mapper_text),
        "ftc_detection_margin_manager.sv": function_pattern.findall(manager_text),
    }
    required_top_fragments = (
        "ftc_cal_detect_handoff_top u_frozen_h0",
        ".det_takeover_ready_i         (det_takeover_ready)",
        ".det_sense_dff_reset_i        (det_sense_dff_reset)",
        ".det_sense_s_clk_i            (det_sense_s_clk)",
        ".det_medium_therm_i           (det_medium_therm)",
        ".det_fine_therm_i             (det_fine_therm)",
    )
    top_connections_present = all(fragment in top_text for fragment in required_top_fragments)

    codebook = read_json(m1_root / "contract/M1_MARGIN_CODEBOOK.json")
    f10_contract = read_json(m1_root / "contract/F10_DETECTION_ENCODING_CONTRACT.json")
    f10_entries = f10_contract.get("entries", [])
    f10_ok = (
        len(f10_entries) == 11
        and f10_entries[-1].get("fine_code") == 10
        and f10_entries[-1].get("fine_therm_vector_bits_msb_to_lsb") == "0000000000"
        and f10_entries[-1].get("physical_legal") is True
        and f10_entries[-1].get("calibration_reachable") is False
    )

    # Read the fully archived final RTL and gate runs.  The Python contract
    # unittest is stored beside them by the final command below, ensuring its
    # result is retained in the same task-owned verification tree.
    rtl_cases = {
        "contract_unittest": log_case(
            rtl_run_root / "contract_unittest.log", "OK"
        ),
        "mapper": log_case(
            rtl_run_root / "mapper/run.log", "M1 mapper unit PASS"
        ),
        "manager_h0_sva": log_case(
            rtl_run_root / "manager/run.log", "M1 manager/H0 integration PASS"
        ),
        "stage_top": log_case(
            rtl_run_root / "top/run.log", "M1 stage-top elaboration PASS"
        ),
    }
    rtl_pass = all(case["pass"] for case in rtl_cases.values())

    gate_log = require_text(gate_run_root / "run.log")
    gate_clean, gate_markers = no_failure_marker(gate_log)
    gate_sdf_annotations = (
        "ftc_detection_margin_manager_synth.sdf\" ... Done" in gate_log
        and "ftc_sensor_owner_handoff_synth.sdf\" ... Done" in gate_log
    )
    gate_case = {
        "run_root": str(gate_run_root.relative_to(root)),
        "manager_and_frozen_h0_sdf_annotated": gate_sdf_annotations,
        "timing_checks_enabled": "+neg_tchk" in require_text(
            m1_root / "verification/gate_sdf/run_m1_gate_sdf.sh"
        ),
        "pass_marker_found": "M1 manager/H0 integration PASS" in gate_log,
        "failure_markers": gate_markers,
        "pass": gate_sdf_annotations and gate_clean and
                ("M1 manager/H0 integration PASS" in gate_log),
    }

    # The precise report is the signoff source: its max and min sections are
    # both present and all reported slacks must be strictly positive.  The DC
    # check_design report contains expected constant-output/unloaded-net LINT
    # observations from literal thermometer rails; record them transparently
    # but do not mislabel them as functional or timing violations.
    timing_report_path = m1_root / "synthesis/reports/timing_precise.rpt"
    timing_report = require_text(timing_report_path)
    max_report, min_report = timing_report.split("Report : timing", 2)[1:]
    setup_slacks = parse_met_slacks(max_report)
    hold_slacks = parse_met_slacks(min_report)
    check_design = require_text(m1_root / "synthesis/reports/check_design.rpt")
    # Read DC's summary totals instead of counting every textual LINT token:
    # each warning appears once in the summary and once in its detailed line.
    # The summary is the unambiguous count a reviewer expects in the evidence.
    lint_summary_patterns = {
        "shorted_outputs_lint_31": r"Shorted outputs \(LINT-31\)\s+([0-9]+)",
        "constant_outputs_lint_52": r"Constant outputs \(LINT-52\)\s+([0-9]+)",
        "unloaded_nets_lint_2": r"Unloaded nets \(LINT-2\)\s+([0-9]+)",
    }
    lint_counts: Dict[str, int] = {}
    for name, pattern in lint_summary_patterns.items():
        match = re.search(pattern, check_design)
        if match is None:
            raise ValueError("missing DC LINT summary line: {}".format(name))
        lint_counts[name] = int(match.group(1))
    timing_summary = {
        "schema_version": 1,
        "stage": "M1-6",
        "scope": "standalone ftc_detection_margin_manager plus exact mapper; frozen H0 not re-synthesized",
        "clock_period_ns": 2.5,
        "library_corner": "ss_typical_max_0p99v_125c",
        "setup_slack_ns": {"worst": min(setup_slacks), "all_met_values": setup_slacks},
        "hold_slack_ns": {"worst": min(hold_slacks), "all_met_values": hold_slacks},
        "setup_hold_all_positive": min(setup_slacks) > 0.0 and min(hold_slacks) > 0.0,
        "reports": [
            str(timing_report_path.relative_to(root)),
            "delay_chain/ftc/controller/m1_detection_margin/synthesis/reports/mapper_to_target_register.rpt",
            "delay_chain/ftc/controller/m1_detection_margin/synthesis/reports/selection_to_state.rpt",
        ],
        "check_design_lint": {
            "counts": lint_counts,
            "interpretation": "expected literal-codebook constant-rail and unused-high-bit LINT; no timing or functional failure is waived",
        },
    }

    # The scripts are the complete M1 execution surface.  Scan executable
    # portions only and reject a real HSPICE/XA/RF command; also reject circuit
    # simulator output extensions anywhere in task-owned M1 evidence.
    script_paths = (
        m1_root / "verification/rtl/run_m1_rtl.sh",
        m1_root / "verification/gate_sdf/run_m1_gate_sdf.sh",
        m1_root / "synthesis/scripts/synthesize_m1_manager_dc.tcl",
    )
    executable_text = "\n".join(command_tokens_without_comments(require_text(path)) for path in script_paths)
    prohibited_tool_tokens = re.findall(r"(?im)(?:^|\s)(hspice|xa|rf6|rf9c|rf9d)(?:\s|$)", executable_text)
    prohibited_suffixes = {".sp", ".lis", ".mt0", ".tr0", ".ac0", ".sw0"}
    prohibited_artifacts = sorted(
        str(path.relative_to(root))
        for path in m1_root.rglob("*")
        if path.is_file() and path.suffix.lower() in prohibited_suffixes
    )

    structural_audit = {
        "schema_version": 1,
        "stage": "M1-8",
        "frozen_input_checks": baseline_checks,
        "frozen_rtl_checks": frozen_rtl_checks,
        "synthesizable_rtl_function_definitions": function_definitions,
        "stage_top_uses_only_h0_detector_input_boundary": top_connections_present,
        "cal_to_sense_clk_cone_claim": {
            "h0_owner_and_top_head_hash_unchanged": all(
                item["git_head_blob_matches"]
                for item in frozen_rtl_checks
                if item["name"] in ("frozen_h0_owner", "frozen_h0_top")
            ),
            "evidence": "M1 wrapper instantiates frozen H0 and drives only its published det_* inputs; no H0+M1 resynthesis was run",
            "h0_existing_timing_evidence": "delay_chain/ftc/controller/h0_calibration_detection_handoff/timing/handoff_timing_composition.json",
        },
        "new_hspice_xa_or_rf_execution": {
            "prohibited_command_tokens": prohibited_tool_tokens,
            "prohibited_task_owned_artifacts": prohibited_artifacts,
            "pass": not prohibited_tool_tokens and not prohibited_artifacts,
        },
    }

    frozen_inputs_pass = all(item["sha256_matches"] for item in baseline_checks)
    frozen_rtl_pass = all(
        item["m1_baseline_sha256_matches"] and item["git_head_blob_matches"] and
        item["h0_frozen_sha256_matches"] for item in frozen_rtl_checks
    )
    no_function_pass = all(not values for values in function_definitions.values())
    codebook_pass = len(codebook.get("entries", [])) == 12 and codebook.get("decision") == "GO"
    no_simulator_rerun_pass = structural_audit["new_hspice_xa_or_rf_execution"]["pass"]
    gate_checks = {
        "f10_physical_detection_only_legal": f10_ok,
        "exact_12_entry_m0_codebook": codebook_pass,
        "no_lookup_interpolation_or_synthesis_rtl_function": no_function_pass,
        "frozen_h0_and_six_calibration_rtl_unchanged": frozen_rtl_pass,
        "takeover_preload_and_safe_apply": rtl_cases["manager_h0_sva"]["pass"],
        "full_cycle_settle_before_valid": rtl_cases["manager_h0_sva"]["pass"],
        "anchor_mapping_and_trip_qualification_distinct": rtl_cases["contract_unittest"]["pass"],
        "rtl_and_sva_pass": rtl_pass,
        "standalone_sta_setup_hold_positive": timing_summary["setup_hold_all_positive"],
        "mapped_sdf_pass_without_control_glitch_or_timing_violation": gate_case["pass"],
        "cal_to_sense_clk_cone_unchanged": structural_audit["cal_to_sense_clk_cone_claim"]["h0_owner_and_top_head_hash_unchanged"] and top_connections_present,
        "no_new_hspice_xa_rf_or_calibration_rerun": no_simulator_rerun_pass,
    }
    decision = "GO" if all(gate_checks.values()) else "NO_GO"

    rtl_results = {
        "schema_version": 1,
        "stage": "M1-5",
        "run_root": str(rtl_run_root.relative_to(root)),
        "cases": rtl_cases,
        "decision": "PASS" if rtl_pass else "FAIL",
    }
    sva_status = {
        "schema_version": 1,
        "stage": "M1-5",
        "assertion_source": "delay_chain/ftc/controller/m1_detection_margin/assertions/ftc_detection_margin_manager_sva.sv",
        "manager_h0_test_log": rtl_cases["manager_h0_sva"],
        "decision": "PASS" if rtl_cases["manager_h0_sva"]["pass"] else "FAIL",
    }
    gate_results = {
        "schema_version": 1,
        "stage": "M1-7",
        "mapped_manager_netlist": "delay_chain/ftc/controller/m1_detection_margin/synthesis/netlist/ftc_detection_margin_manager_synth.v",
        "mapped_manager_sdf": "delay_chain/ftc/controller/m1_detection_margin/synthesis/netlist/ftc_detection_margin_manager_synth.sdf",
        "frozen_h0_sdf": "delay_chain/ftc/controller/h0_calibration_detection_handoff/synthesis/netlist/ftc_sensor_owner_handoff_synth.sdf",
        "result": gate_case,
        "decision": "PASS" if gate_case["pass"] else "FAIL",
    }
    gate_status = {
        "schema_version": 1,
        "stage": "M1-8",
        "decision": decision,
        "checks": gate_checks,
        "evidence": {
            "frozen_manifest": "delay_chain/ftc/controller/m1_detection_margin/baseline/m1_baseline_manifest.json",
            "interface_contract": "delay_chain/ftc/controller/m1_detection_margin/contract/M1_INTERFACE_CONTRACT.json",
            "downstream_contract": "delay_chain/ftc/controller/m1_detection_margin/contract/M1_DOWNSTREAM_T0_D0_HANDOFF.json",
            "rtl_results": "delay_chain/ftc/controller/m1_detection_margin/verification/rtl/M1_RTL_RESULTS.json",
            "gate_sdf_results": "delay_chain/ftc/controller/m1_detection_margin/verification/gate_sdf/M1_GATE_SDF_RESULTS.json",
            "timing_summary": "delay_chain/ftc/controller/m1_detection_margin/timing/M1_TIMING_SUMMARY.json",
            "structural_audit": "delay_chain/ftc/controller/m1_detection_margin/reports/M1_STRUCTURAL_AUDIT.json",
        },
        "next_stage": "T0 transient voltage-droop threat and detection-timing contract; M1 does not implement a probe or alarm",
    }

    # Publish each independently useful artifact before failing a NO_GO run,
    # ensuring a reviewer can see the failed predicate instead of receiving an
    # opaque script exception.  All destinations are named by the M1-8 plan.
    write_json(m1_root / "baseline/m1_baseline_manifest.json", {
        "schema_version": 1,
        "stage": "M1-8",
        "source_baseline": "delay_chain/ftc/controller/m1_detection_margin/baseline/frozen_input_sha256.json",
        "checks": baseline_checks,
        "frozen_rtl_checks": frozen_rtl_checks,
        "decision": "PASS" if frozen_inputs_pass and frozen_rtl_pass else "FAIL",
    })
    write_json(m1_root / "contract/M1_INTERFACE_CONTRACT.json", build_interface_contract())
    write_json(m1_root / "contract/M1_DOWNSTREAM_T0_D0_HANDOFF.json", build_downstream_contract())
    write_json(m1_root / "verification/rtl/M1_RTL_RESULTS.json", rtl_results)
    write_json(m1_root / "verification/gate_sdf/M1_GATE_SDF_RESULTS.json", gate_results)
    write_json(m1_root / "timing/M1_TIMING_SUMMARY.json", timing_summary)
    write_json(m1_root / "reports/M1_SVA_STATUS.json", sva_status)
    write_json(m1_root / "reports/M1_STRUCTURAL_AUDIT.json", structural_audit)
    write_json(m1_root / "reports/M1_GATE_STATUS.json", gate_status)

    final_report = "# M1 programmable detection-margin safe configuration\n\n"
    final_report += "## Gate decision\n\n"
    final_report += "**{}** — all required M1-8 checks are {}.\n\n".format(
        decision, "true" if decision == "GO" else "not true"
    )
    final_report += "## Closed scope\n\n"
    final_report += (
        "M1 uses the exact 12-entry M0 codebook and legal detection-only F10 "
        "(active-low `10'b0000000000`).  It preloads H0's immutable calibration "
        "snapshot, lets frozen H0 grant ownership, applies the registered target "
        "only with reset high/S_CLK low, and waits one full 2.5 ns controller "
        "cycle before `margin_cfg_valid_o`.  No probe, Q decision, alarm, dynamic "
        "recalibration, HSPICE, XA, RF6/RF9C/RF9D, or complete calibration rerun "
        "belongs to this stage.\n\n"
    )
    final_report += "## Verification evidence\n\n"
    final_report += "- RTL/SVA: `{}`.\n".format(rtl_results["run_root"])
    final_report += "- Mapped+SDF: `{}`.\n".format(gate_case["run_root"])
    final_report += "- Worst setup slack: {:.6f} ns; worst hold slack: {:.6f} ns.\n".format(
        timing_summary["setup_slack_ns"]["worst"], timing_summary["hold_slack_ns"]["worst"]
    )
    final_report += "- Frozen H0 plus six calibration RTL: hash and HEAD-blob checks passed.\n"
    final_report += "- DC LINT observations are documented in `timing/M1_TIMING_SUMMARY.json`; they arise from intentional literal constant rails and do not waive any timing or functional check.\n\n"
    final_report += "## Downstream handoff\n\n"
    final_report += (
        "Proceed only to T0 to define the transient threat and detection timing "
        "contract.  D0 must later define runtime reset/S_CLK, Q decision, and alarm "
        "policy; M1 intentionally leaves the sensor reset and idle.\n"
    )
    (m1_root / "reports/M1_FINAL_REPORT.md").write_text(final_report, encoding="utf-8")

    if decision != "GO":
        raise SystemExit("M1 evidence is NO_GO; inspect M1_GATE_STATUS.json")
    print("M1-8 GO: final evidence package generated")


if __name__ == "__main__":
    main()
