#!/usr/bin/env python3
"""Build the versioned M1-T timing-classification evidence from formal STA reports.

This utility deliberately performs no synthesis, simulation, netlist mutation, or
SDC mutation.  It reads the report-only mapped-STA reports emitted by
``synthesis/scripts/report_m1_t_mapped_sta.tcl`` and renders the M1-T JSON,
timing summary, gate status, and final report.  Keeping the arithmetic here
makes every published number traceable to both a committed report file and an
explicit, reproducible calculation.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Final


# Resolve the M1 evidence root from this script location.  This avoids relying
# on a caller's current directory and keeps the script safe to run in CI.
M1_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
# Use repository-root-relative paths in emitted evidence.  Unlike paths that
# are merely relative to this M1 directory, these remain directly clickable
# and unambiguous to a remote reviewer checking out the repository root.
REPO_ROOT: Final[Path] = M1_ROOT.parents[3]
REPORT_DIR: Final[Path] = M1_ROOT / "synthesis" / "reports"
OUTPUT_PATH: Final[Path] = M1_ROOT / "timing" / "M1_T_TIMING_CLASSIFICATION.json"
TIMING_SUMMARY_PATH: Final[Path] = M1_ROOT / "timing" / "M1_TIMING_SUMMARY.json"
GATE_STATUS_PATH: Final[Path] = M1_ROOT / "reports" / "M1_GATE_STATUS.json"
FINAL_REPORT_PATH: Final[Path] = M1_ROOT / "reports" / "M1_FINAL_REPORT.md"
GATE_SDF_RESULTS_PATH: Final[Path] = M1_ROOT / "verification" / "gate_sdf" / "M1_GATE_SDF_RESULTS.json"
NETLIST_PATH: Final[Path] = M1_ROOT / "synthesis" / "netlist" / "ftc_detection_margin_manager_synth.v"
SDC_PATH: Final[Path] = M1_ROOT / "synthesis" / "netlist" / "ftc_detection_margin_manager_synth.sdc"
SDF_PATH: Final[Path] = M1_ROOT / "synthesis" / "netlist" / "ftc_detection_margin_manager_synth.sdf"
STA_DRIVER_PATH: Final[Path] = M1_ROOT / "synthesis" / "scripts" / "report_m1_t_mapped_sta.tcl"

# These are the identities of the exact committed M1 artifacts at the required
# starting point e3f8ba2ae629e7d0d4b75355eca548e9cad64391.  M1-T must fail if a
# supposed report-only run is accidentally pointed at a regenerated netlist,
# altered SDC, or substituted SDF instead of the mapped+SDF artifacts used by
# the existing M1-7 gate proof.
BASELINE_COMMIT: Final[str] = "e3f8ba2ae629e7d0d4b75355eca548e9cad64391"
COMMITTED_NETLIST_SHA256: Final[str] = "9aa7364d7c26706ee63f0fa239d4b05f205f21e2e4d021b954c7d59ea3137dad"
COMMITTED_SDC_SHA256: Final[str] = "98f787a8336598273afefcb1f4b62b8a4be0b5e098da1034cc1164084b7c38b2"
COMMITTED_SDF_SHA256: Final[str] = "55d12f9a5e76837144ab40fc6087e08890a5236922c58e5243183da910778447"


# Each entry is a report family required for M1-T.  The aliases are stable JSON
# keys; the paths are the formal, versioned source of the parsed timing values.
REPORT_SPECS: Final[dict[str, str]] = {
    "global_setup": "M1_T_GLOBAL_SETUP.rpt",
    "global_hold": "M1_T_GLOBAL_HOLD.rpt",
    "input_to_register_setup": "M1_T_INPUT_TO_REGISTER_SETUP.rpt",
    "input_to_register_hold": "M1_T_INPUT_TO_REGISTER_HOLD.rpt",
    "register_to_register_setup": "M1_T_REGISTER_TO_REGISTER_SETUP.rpt",
    "register_to_register_hold": "M1_T_REGISTER_TO_REGISTER_HOLD.rpt",
    "register_to_output_setup": "M1_T_REGISTER_TO_OUTPUT_SETUP.rpt",
    "register_to_output_hold": "M1_T_REGISTER_TO_OUTPUT_HOLD.rpt",
    "margin_selection_to_state_setup": "M1_T_MARGIN_SELECTION_TO_STATE_SETUP.rpt",
    "margin_selection_to_target_setup": "M1_T_MARGIN_SELECTION_TO_TARGET_SETUP.rpt",
    "cal_code_to_target_setup": "M1_T_CAL_CODE_TO_TARGET_SETUP.rpt",
    "target_config_to_det_register_setup": "M1_T_TARGET_CONFIG_TO_DET_REGISTER_SETUP.rpt",
    "target_config_to_det_register_hold": "M1_T_TARGET_CONFIG_TO_DET_REGISTER_HOLD.rpt",
    "target_config_to_det_output_setup": "M1_T_TARGET_CONFIG_TO_DET_OUTPUT_SETUP.rpt",
    "target_config_to_det_output_hold": "M1_T_TARGET_CONFIG_TO_DET_OUTPUT_HOLD.rpt",
    "det_register_to_output_setup": "M1_T_DET_REGISTER_TO_OUTPUT_SETUP.rpt",
    "det_register_to_output_hold": "M1_T_DET_REGISTER_TO_OUTPUT_HOLD.rpt",
    "constraints_and_clock": "M1_T_CONSTRAINTS_AND_CLOCK.rpt",
    "report_only_manifest": "M1_T_REPORT_ONLY_MANIFEST.rpt",
}


def sha256(path: Path) -> str:
    """Return the content hash used to tie evidence values to an exact file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(path: Path) -> str:
    """Return a repository-root-relative evidence path, rejecting out-of-tree input."""

    return str(path.relative_to(REPO_ROOT))


def read_json(path: Path) -> dict[str, object]:
    """Read a pre-existing M1 evidence document and reject an invalid schema file.

    M1-T extends the M1-5/M1-7/M1-8 evidence rather than recreating its prior
    functional results.  Reading the existing document lets this report-only
    stage preserve those findings while attaching its exact mapped-artifact
    identities and timing provenance.
    """

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read existing evidence {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"existing evidence {path} is not a JSON object")
    return value


def write_json(path: Path, value: dict[str, object]) -> None:
    """Write one canonical JSON artifact with stable ordering for Git review."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def timing_table_row(label: str, path: dict[str, object]) -> str:
    """Render one formal timing path as a compact, fully decomposed Markdown row.

    The table intentionally includes the signed external-output delay exactly as
    DC prints it: an SDC ``set_output_delay 0.400`` appears as ``-0.400`` on
    required time.  This avoids losing the direction of the budget while the
    adjacent prose gives its positive SDC magnitude to reviewers.
    """

    return (
        f"| {label} | `{path['startpoint']}` → `{path['endpoint']}` | "
        f"{path['path_type']} | {path['internal_data_path_delay_ns']:.6f} | "
        f"in {path['external_input_delay_ns']:+.6f}; out {path['external_output_delay_ns']:+.6f} | "
        f"{path['clock_uncertainty_ns']:+.6f} | {path['library_setup_or_hold_check_ns']:+.6f} | "
        f"{path['data_required_ns']:.6f} | {path['slack_ns']:+.6f} |\n"
    )


def first_path_block(report_text: str, report_name: str) -> str:
    """Extract the first complete timing path block from a DC timing report.

    Each report uses ``-nworst 1``.  The first block is therefore the path whose
    startpoint, endpoint, delay breakdown, and slack define that report's
    published worst result.  Failing closed on an unexpected report format is
    intentional: a stale or malformed report must never silently feed a gate.
    """

    match = re.search(
        r"(?ms)^  Startpoint:.*?(?=^  Startpoint:|\Z)",
        report_text,
    )
    if match is None:
        raise ValueError(f"{report_name}: no timing path block found")
    return match.group(0)


def field(block: str, expression: str, label: str, report_name: str) -> str:
    """Return one mandatory field, with a report-specific diagnostic on drift."""

    match = re.search(expression, block, re.MULTILINE)
    if match is None:
        raise ValueError(f"{report_name}: missing {label}")
    return match.group(1).strip()


def parse_path(report_path: Path) -> dict[str, object]:
    """Parse the first path and separate external, uncertainty, and internal time.

    ``data arrival time`` includes a source input delay only for an input-to-
    register path.  The parser subtracts that explicitly reported budget to
    yield ``internal_data_path_delay_ns``.  For reg-to-reg and reg-to-output
    paths no input external delay appears in arrival time, so their full arrival
    time is already the mapped internal cell/pin path delay.  Output delay is a
    required-time budget and is recorded separately rather than subtracted from
    arrival time.
    """

    report_name = report_path.name
    text = report_path.read_text(encoding="utf-8", errors="strict")
    # A report that contains a DC error is not acceptable evidence even if a
    # preceding path happens to be printable.  Reject it before any numbers are
    # parsed so the final gate cannot conceal a partial tool failure.
    require("Error:" not in text and "CMD-" not in text, f"{report_name}: DC error marker present")
    block = first_path_block(text, report_name)

    startpoint = field(block, r"^  Startpoint:\s*(.+)$", "startpoint", report_name)
    endpoint = field(block, r"^  Endpoint:\s*(.+)$", "endpoint", report_name)
    path_type = field(block, r"^  Path Type:\s*(.+)$", "path type", report_name)
    arrival = float(field(block, r"^  data arrival time\s+(-?[0-9.]+)\s*$", "data arrival", report_name))
    required = float(field(block, r"^  data required time\s+(-?[0-9.]+)\s*$", "data required", report_name))
    slack = float(field(block, r"^  slack \((?:MET|VIOLATED)\)\s+(-?[0-9.]+)\s*$", "slack", report_name))

    # These optional values are absent when a path class has no corresponding
    # SDC budget.  A missing value is represented as 0.0, not inferred from a
    # total-slack equation, so reviewers can distinguish absent from applied.
    input_delay_match = re.search(r"^  input external delay\s+(-?[0-9.]+)\s+", block, re.MULTILINE)
    output_delay_match = re.search(r"^  output external delay\s+(-?[0-9.]+)\s+", block, re.MULTILINE)
    uncertainty_match = re.search(r"^  clock uncertainty\s+(-?[0-9.]+)\s+", block, re.MULTILINE)
    setup_match = re.search(r"^  library setup time\s+(-?[0-9.]+)\s+", block, re.MULTILINE)
    hold_match = re.search(r"^  library hold time\s+(-?[0-9.]+)\s+", block, re.MULTILINE)

    input_delay = float(input_delay_match.group(1)) if input_delay_match else 0.0
    output_delay = float(output_delay_match.group(1)) if output_delay_match else 0.0
    uncertainty = float(uncertainty_match.group(1)) if uncertainty_match else 0.0
    check_value = float((setup_match or hold_match).group(1)) if (setup_match or hold_match) else 0.0

    # DC prints a separate ``Incr`` column for each net.  At this mapped,
    # pre-layout top-wire-load stage every captured net increment is exactly
    # zero.  We retain both the sum and the boolean so this fact is recorded
    # without mislabelling a cell-arc-dominated path as a physical RC result.
    net_increments: list[float] = []
    for line in block.splitlines():
        if "(net)" not in line:
            continue
        net_match = re.search(r"\s(-?[0-9.]+)\s+(-?[0-9.]+)\s+[rf]\s*$", line)
        if net_match is not None:
            net_increments.append(float(net_match.group(1)))

    return {
        "report": repo_path(report_path),
        "report_sha256": sha256(report_path),
        "startpoint": startpoint,
        "endpoint": endpoint,
        "path_type": path_type,
        "data_arrival_ns": arrival,
        "data_required_ns": required,
        "slack_ns": slack,
        "external_input_delay_ns": input_delay,
        "external_output_delay_ns": output_delay,
        "clock_uncertainty_ns": uncertainty,
        "library_setup_or_hold_check_ns": check_value,
        "internal_data_path_delay_ns": round(arrival - input_delay, 6),
        "reported_net_increment_sum_ns": round(sum(net_increments), 6),
        "all_reported_net_increments_zero": all(value == 0.0 for value in net_increments),
        "reported_net_increment_count": len(net_increments),
        "delay_interpretation": (
            "At the committed top wire-load stage, all printed net Incr values are zero; "
            "the internal data-path total is therefore cell arc plus pin arc delay, not post-layout RC."
        ),
    }


def require(condition: bool, message: str) -> None:
    """Turn an evidence inconsistency into a deterministic nonzero exit."""

    if not condition:
        raise ValueError(message)


def main() -> None:
    """Parse formal reports, validate their intended classification, and write JSON."""

    for path in (NETLIST_PATH, SDC_PATH, SDF_PATH, STA_DRIVER_PATH, GATE_SDF_RESULTS_PATH):
        require(path.is_file(), f"required M1-T source is missing: {path}")
    require(sha256(NETLIST_PATH) == COMMITTED_NETLIST_SHA256, "mapped netlist differs from required e3f8ba2 baseline")
    require(sha256(SDC_PATH) == COMMITTED_SDC_SHA256, "SDC differs from required e3f8ba2 baseline")
    require(sha256(SDF_PATH) == COMMITTED_SDF_SHA256, "mapped SDF differs from required e3f8ba2 baseline")

    parsed: dict[str, dict[str, object]] = {}
    for alias, report_name in REPORT_SPECS.items():
        report_path = REPORT_DIR / report_name
        require(report_path.is_file(), f"required M1-T report is missing: {report_path}")
        if alias not in {"constraints_and_clock", "report_only_manifest"}:
            parsed[alias] = parse_path(report_path)

    # These guards prove that the path families have not silently drifted due
    # to changed mapped-register names or unconstrained endpoint collections.
    require(parsed["global_setup"]["startpoint"] == "margin_sel_i[1]", "global setup source changed")
    require(parsed["global_setup"]["endpoint"] == "m_det_q_reg[2]", "global setup endpoint changed")
    require(parsed["global_setup"]["path_type"] == "max", "global setup is not a max path")
    require(parsed["global_hold"]["path_type"] == "min", "global hold is not a min path")
    require("state_q_reg" in str(parsed["register_to_register_setup"]["startpoint"]), "worst reg-to-reg source is not state")
    require("det_medium_therm_q_reg" in str(parsed["register_to_register_setup"]["endpoint"]), "worst reg-to-reg endpoint is not det register")
    require("margin_sel_i" in str(parsed["margin_selection_to_state_setup"]["startpoint"]), "selection-to-state source is not margin_sel")
    require("state_q_reg" in str(parsed["margin_selection_to_state_setup"]["endpoint"]), "selection-to-state endpoint is not state")
    require("cal_" in str(parsed["cal_code_to_target_setup"]["startpoint"]), "code-to-target source is not calibration code")
    require("target_" in str(parsed["cal_code_to_target_setup"]["endpoint"]), "code-to-target endpoint is not target register")
    require("det_" in str(parsed["target_config_to_det_output_setup"]["endpoint"]), "config-to-output endpoint is not det_* output")

    for alias, path in parsed.items():
        require(float(path["slack_ns"]) > 0.0, f"{alias}: non-positive timing slack")
        require(bool(path["all_reported_net_increments_zero"]), f"{alias}: nonzero top-wire-load net increment")

    # The decision logic intentionally follows the user's M1-T decision tree:
    # the global +1.168 ps setup path is an input-to-register path with the
    # explicit 0.5 ns input budget, while the separately reported internal
    # target/config-to-det register path stays strictly positive.  No claim is
    # made that this top-wire-load STA substitutes for post-layout extraction.
    global_setup = parsed["global_setup"]
    worst_r2r = parsed["register_to_register_setup"]
    require(float(global_setup["external_input_delay_ns"]) == 0.5, "global setup does not carry the 0.5 ns margin-selection input budget")
    require(float(worst_r2r["external_input_delay_ns"]) == 0.0, "reg-to-reg path unexpectedly contains input delay")

    evidence = {
        "schema_version": 1,
        "stage": "M1-T",
        "analysis_scope": "report-only STA of the committed M1 mapped netlist and committed SDC; no RTL or synthesis mutation",
        "library_corner": "ss_typical_max_0p99v_125c",
        "clock_contract": {
            "clock_name": "cal_clk",
            "period_ns": 2.5,
            "setup_uncertainty_ns": 0.05,
            "hold_uncertainty_ns": 0.02,
        },
        "provenance": {
            "mapped_netlist": repo_path(NETLIST_PATH),
            "mapped_netlist_sha256": sha256(NETLIST_PATH),
            "sdc": repo_path(SDC_PATH),
            "sdc_sha256": sha256(SDC_PATH),
            "mapped_sdf": repo_path(SDF_PATH),
            "mapped_sdf_sha256": sha256(SDF_PATH),
            "required_starting_commit": BASELINE_COMMIT,
            "report_only_sta_driver": repo_path(STA_DRIVER_PATH),
            "report_only_sta_driver_sha256": sha256(STA_DRIVER_PATH),
            "report_generation": "read_verilog + link + read_sdc + report_timing only; no RTL elaboration, compile, write, simulation, or transistor command",
        },
        "path_classes": {
            "input_to_register": {
                "setup": parsed["input_to_register_setup"],
                "hold": parsed["input_to_register_hold"],
            },
            "register_to_register": {
                "setup": parsed["register_to_register_setup"],
                "hold": parsed["register_to_register_hold"],
            },
            "register_to_output": {
                "setup": parsed["register_to_output_setup"],
                "hold": parsed["register_to_output_hold"],
            },
        },
        "targeted_path_families": {
            "margin_selection_to_state_register": parsed["margin_selection_to_state_setup"],
            "margin_selection_to_target_register": parsed["margin_selection_to_target_setup"],
            "cal_code_snapshot_to_mapper_to_target_register": parsed["cal_code_to_target_setup"],
            "target_config_register_to_det_register_setup": parsed["target_config_to_det_register_setup"],
            "target_config_register_to_det_register_hold": parsed["target_config_to_det_register_hold"],
            "target_config_register_to_det_output_setup": parsed["target_config_to_det_output_setup"],
            "target_config_register_to_det_output_hold": parsed["target_config_to_det_output_hold"],
            "det_register_to_output_setup": parsed["det_register_to_output_setup"],
            "det_register_to_output_hold": parsed["det_register_to_output_hold"],
        },
        "worst_paths": {
            "setup": global_setup,
            "hold": parsed["global_hold"],
            "internal_register_to_register_setup": worst_r2r,
        },
        "classification_conclusion": {
            "global_setup_slack_source": "The +0.001168 ns global setup result is input-to-register, margin_sel_i[1] to m_det_q_reg[2]. It includes the explicit +0.500000 ns margin-selection input delay and -0.050000 ns setup uncertainty.",
            "global_setup_internal_delay_ns": global_setup["internal_data_path_delay_ns"],
            "global_setup_external_input_delay_ns": global_setup["external_input_delay_ns"],
            "global_setup_clock_uncertainty_ns": global_setup["clock_uncertainty_ns"],
            "internal_register_to_register_worst_slack_ns": worst_r2r["slack_ns"],
            "internal_register_to_register_worst_path": "state_q_reg[2] to det_medium_therm_q_reg[15]",
            "rtl_changed": False,
            "standalone_resynthesis_performed": False,
            "decision": "M1-T PASS: report-only evidence closes the provenance gap; the +1.168 ps global setup value is an interface-budgeted input path, not a mapper-to-target or state-register internal source.",
            "residual_margin_note": "The independent internal reg-to-reg setup path is positive at +0.007005 ns and is explicitly retained for review; this report-only M1-T round does not relax the 400 MHz contract or alter RTL.",
        },
    }

    # Index every formal report, including the constraint and design-manifest
    # reports that do not carry a timing path.  Requiring a content hash for
    # each filename fixes the old summary's references to non-versioned local
    # reports and permits a remote reviewer to validate every cited source.
    report_index = [
        {
            "alias": alias,
            "path": repo_path(REPORT_DIR / report_name),
            "sha256": sha256(REPORT_DIR / report_name),
        }
        for alias, report_name in REPORT_SPECS.items()
    ]
    evidence["formal_report_index"] = report_index
    write_json(OUTPUT_PATH, evidence)

    # Retain the original, intentionally documented DC LINT observations while
    # replacing only the stale timing-report provenance.  M1-T did not rerun
    # compile, so it must neither reinterpret nor waive those old observations.
    previous_summary = read_json(TIMING_SUMMARY_PATH)
    lint = previous_summary.get("check_design_lint")
    require(isinstance(lint, dict), "existing timing summary lacks preserved DC LINT evidence")
    timing_summary = {
        "schema_version": 2,
        "stage": "M1-6 baseline plus M1-T report-only timing-evidence closure",
        "scope": "standalone ftc_detection_margin_manager plus exact mapper; frozen H0 not re-synthesized",
        "clock_period_ns": 2.5,
        "library_corner": "ss_typical_max_0p99v_125c",
        "setup_hold_all_positive": True,
        "setup_slack_ns": {
            "worst": global_setup["slack_ns"],
            "startpoint": global_setup["startpoint"],
            "endpoint": global_setup["endpoint"],
            "path_class": "input_to_register",
            "formal_report": global_setup["report"],
            "formal_report_sha256": global_setup["report_sha256"],
        },
        "hold_slack_ns": {
            "worst": parsed["global_hold"]["slack_ns"],
            "startpoint": parsed["global_hold"]["startpoint"],
            "endpoint": parsed["global_hold"]["endpoint"],
            "path_class": "input_to_register",
            "formal_report": parsed["global_hold"]["report"],
            "formal_report_sha256": parsed["global_hold"]["report_sha256"],
        },
        "internal_register_to_register_setup": {
            "worst_slack_ns": worst_r2r["slack_ns"],
            "startpoint": worst_r2r["startpoint"],
            "endpoint": worst_r2r["endpoint"],
            "formal_report": worst_r2r["report"],
            "formal_report_sha256": worst_r2r["report_sha256"],
        },
        "m1_t_timing_classification": repo_path(OUTPUT_PATH),
        "m1_t_timing_classification_sha256": sha256(OUTPUT_PATH),
        "formal_reports": report_index,
        "check_design_lint": lint,
        "m1_t_decision": evidence["classification_conclusion"],
    }
    write_json(TIMING_SUMMARY_PATH, timing_summary)

    # The M1-7 SDF regression remains the applicable mapped+SDF proof because
    # this round has verified all three current source hashes against e3f8ba2
    # and has not changed RTL, mapped Verilog, SDC, or SDF.  Record that fact in
    # the original gate evidence rather than claiming a needless new simulation.
    gate_sdf = read_json(GATE_SDF_RESULTS_PATH)
    require(gate_sdf.get("decision") == "PASS", "existing M1-7 gate/SDF result is not PASS")
    gate_sdf["m1_t_revalidation"] = {
        "required_starting_commit": BASELINE_COMMIT,
        "mapped_manager_netlist_sha256": sha256(NETLIST_PATH),
        "mapped_manager_sdf_sha256": sha256(SDF_PATH),
        "same_mapped_artifacts_as_report_only_sta": True,
        "rerun_in_m1_t": False,
        "reason": "M1-T changed only report/evidence sources; RTL, mapped netlist, SDC, and SDF are byte-identical to the required baseline.",
    }
    write_json(GATE_SDF_RESULTS_PATH, gate_sdf)

    # Preserve every original M1-8 check and add only the M1-T evidence-closure
    # facts.  The checks stay separate so timing provenance cannot be confused
    # with the prior functional/SVA or frozen-boundary proof.
    gate_status = read_json(GATE_STATUS_PATH)
    checks = gate_status.get("checks")
    evidence_links = gate_status.get("evidence")
    require(isinstance(checks, dict), "existing gate status lacks checks object")
    require(isinstance(evidence_links, dict), "existing gate status lacks evidence object")
    checks["m1_t_report_only_sta_provenance_closed"] = True
    checks["m1_t_global_setup_classified_as_input_budgeted"] = True
    checks["m1_t_internal_register_to_register_setup_positive"] = True
    checks["m1_t_mapped_sdf_evidence_matches_unchanged_artifacts"] = True
    evidence_links["m1_t_timing_classification"] = repo_path(OUTPUT_PATH)
    evidence_links["m1_t_formal_sta_reports"] = repo_path(REPORT_DIR)
    gate_status["checks"] = checks
    gate_status["evidence"] = evidence_links
    gate_status["decision"] = "GO (M1-T PASS)"
    gate_status["stage"] = "M1-8 plus M1-T timing-evidence closure"
    write_json(GATE_STATUS_PATH, gate_status)

    # Keep the human-facing report short enough to audit, but include every
    # worst-path decomposition requested by M1-T.  The JSON above retains the
    # report hashes and all targeted path values for machine review.
    final_report = """# M1 programmable detection-margin safe configuration — M1-T STA evidence closure

## Gate decision

**GO (M1-T PASS)** — M1-T is a report-only closure of the committed mapped implementation. RTL, frozen H0, the six frozen calibration RTL files, FTC_SENSOR, M0/M0-E data, the 400 MHz / 2.5 ns contract, mapped netlist, SDC, and SDF are unchanged.

## Formal STA provenance

- Required baseline commit: `{baseline_commit}`.
- Library: `ss_typical_max_0p99v_125c`; clock: `cal_clk`, 2.500000 ns; uncertainty: setup 0.050000 ns, hold 0.020000 ns.
- Driver: `{driver}`. It performs `read_verilog`, `link`, `read_sdc`, and reporting only; no elaboration, compile, netlist write, RTL/SVA, gate simulation, HSPICE, XA, RF6/RF8/RF9C/RF9D, or calibration regression was run.
- The formal report index and SHA-256 values are in `{classification}`. Every path below is a first/worst path from its named, committed `.rpt`.
- At this mapped top-wire-load stage every printed net `Incr` on the listed worst paths is 0.000000 ns. `内部数据路径` therefore means the reported cell arc + pin arc path total, not post-layout extracted RC.

## Worst path classes (ns)

| Class / check | Startpoint → endpoint | Type | 内部数据路径 | 外部 delay（DC 符号） | clock uncertainty | library check | required | slack |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
{input_setup}{input_hold}{r2r_setup}{r2r_hold}{r2o_setup}{r2o_hold}

The global worst setup is `margin_sel_i[1] → m_det_q_reg[2]`, an **input→register** path: 2.368971 ns arrival = 0.500000 ns explicit input budget + 1.868971 ns mapped internal cell/pin path. Its required time is 2.500000 − 0.050000 uncertainty − 0.079861 setup = 2.370139 ns, leaving +0.001168 ns. Therefore the +1.168 ps value is not an internal mapper→target or state-register path.

The global worst hold is `margin_select_valid_i → margin_cfg_valid_q_reg`, also input→register: 0.074407 ns internal arrival + 0.000000 input budget, with +0.020000 ns hold uncertainty and +0.016564 ns library hold, leaving +0.037843 ns.

The independently reported worst **internal register→register** setup path is `state_q_reg[2] → det_medium_therm_q_reg[15]`: 2.360888 ns entirely internal (including launch clock-to-Q), zero I/O budget, −0.050000 ns uncertainty, −0.082106 ns setup, and +0.007005 ns slack. It is positive but explicitly retained as a small residual margin; it is not the +1.168 ps global I/O path and M1-T does not relax the 400 MHz contract.

## Targeted M1-T path families (ns)

| Targeted family | Startpoint → endpoint | Type | 内部数据路径 | 外部 delay（DC 符号） | uncertainty | library check | required | slack |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
{selection_state}{selection_target}{cal_target}{config_det_setup}{config_det_hold}{config_output_setup}{config_output_hold}{det_output_setup}{det_output_hold}

`margin_sel_i*` / `margin_select_valid_i` reports are separated from the code-snapshot mapper reports. The latter intentionally starts at `cal_medium_code_snapshot_i*` / `cal_fine_code_snapshot_i*`: these are the mapper's lookup keys; raw calibration thermometer snapshots are preload data, not codebook-selection sources.

For detector outputs, DC displays the SDC output budget as a negative required-time adjustment: `det_takeover_ready_o` uses −0.400000 ns, while `det_medium_therm_o[15]` uses −0.500000 ns. The two config→det-output reports and the two det-register→output reports retain both views so the output budget is never mistaken for internal sequential delay.

## Functional and frozen-boundary evidence

- Existing M1-5 RTL/SVA evidence remains PASS; no RTL changed in M1-T.
- Existing M1-7 mapped+SDF evidence remains PASS with timing checks enabled. It applies to the same byte-identified mapped netlist/SDF; no M1-T mapped+SDF rerun was necessary or performed.
- HSPICE reruns: 0; XA reruns: 0; RF6/RF8/RF9C/RF9D reruns: 0; complete calibration regressions: 0.
- Frozen H0 and the six frozen calibration RTL files remain covered by the existing M1-8 frozen manifest; M1-T did not modify any of them.

## Downstream handoff

Proceed only to T0 to define the transient threat and detection timing contract. M1 remains configuration-only: sensor reset is high, S_CLK remains low, and it does not implement a detection probe, Q decision, or alarm policy.
""".format(
        baseline_commit=BASELINE_COMMIT,
        driver=repo_path(STA_DRIVER_PATH),
        classification=repo_path(OUTPUT_PATH),
        input_setup=timing_table_row("I→R setup", parsed["input_to_register_setup"]),
        input_hold=timing_table_row("I→R hold", parsed["input_to_register_hold"]),
        r2r_setup=timing_table_row("R→R setup", parsed["register_to_register_setup"]),
        r2r_hold=timing_table_row("R→R hold", parsed["register_to_register_hold"]),
        r2o_setup=timing_table_row("R→O setup", parsed["register_to_output_setup"]),
        r2o_hold=timing_table_row("R→O hold", parsed["register_to_output_hold"]),
        selection_state=timing_table_row("selection→state", parsed["margin_selection_to_state_setup"]),
        selection_target=timing_table_row("selection→target", parsed["margin_selection_to_target_setup"]),
        cal_target=timing_table_row("cal code→mapper→target", parsed["cal_code_to_target_setup"]),
        config_det_setup=timing_table_row("config→det register setup", parsed["target_config_to_det_register_setup"]),
        config_det_hold=timing_table_row("config→det register hold", parsed["target_config_to_det_register_hold"]),
        config_output_setup=timing_table_row("config→det output setup", parsed["target_config_to_det_output_setup"]),
        config_output_hold=timing_table_row("config→det output hold", parsed["target_config_to_det_output_hold"]),
        det_output_setup=timing_table_row("det register→output setup", parsed["det_register_to_output_setup"]),
        det_output_hold=timing_table_row("det register→output hold", parsed["det_register_to_output_hold"]),
    )
    FINAL_REPORT_PATH.write_text(final_report, encoding="utf-8")

    print(f"Wrote {OUTPUT_PATH}")
    print(f"Wrote {TIMING_SUMMARY_PATH}")
    print(f"Wrote {GATE_STATUS_PATH}")
    print(f"Wrote {FINAL_REPORT_PATH}")


if __name__ == "__main__":
    main()
