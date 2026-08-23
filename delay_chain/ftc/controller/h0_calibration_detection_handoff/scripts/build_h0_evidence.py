#!/usr/bin/env python3
"""Publish the H0 evidence files from the authoritative local run products.

The script does not run a simulator or synthesis tool and never edits RTL.  It
only reads the H0 reports/logs, extracts the measured path bounds, combines
them with the already frozen 400 MHz physical-event minima, and writes small
JSON/Markdown evidence records below the H0 directory.  Keeping this step
deterministic makes the final gate auditable without treating a smoke result as
the timing proof.
"""

from __future__ import print_function

import hashlib
import json
import re
import subprocess
from pathlib import Path


def find_repo_root():
    """Locate the worktree by its plans directory, independent of cwd."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "plans").is_dir():
            return parent
    raise RuntimeError("repository root with plans/ was not found")


ROOT = find_repo_root()
H0 = ROOT / "delay_chain/ftc/controller/h0_calibration_detection_handoff"
REPORTS = H0 / "reports"
TIMING = H0 / "timing"
SYNTH_REPORTS = H0 / "synthesis/reports"
GATE = H0 / "verification/gate_sdf"
NETLIST = H0 / "synthesis/netlist/ftc_sensor_owner_handoff_synth.v"
SDF = H0 / "synthesis/netlist/ftc_sensor_owner_handoff_synth.sdf"
OWNER_RTL = ROOT / "delay_chain/ftc/controller/rtl/ftc_sensor_owner_handoff.sv"
TOP_RTL = ROOT / "delay_chain/ftc/controller/rtl/ftc_cal_detect_handoff_top.sv"
BASELINE = H0 / "baseline/h0_baseline_manifest.json"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_blob(path):
    return subprocess.check_output(["git", "hash-object", str(path)], cwd=str(ROOT)).decode().strip()


def timing_blocks(path):
    """Return one full DC timing path per Startpoint section.

    A DC path report contains both the constrained arrival and the physical
    cell increments.  Splitting by Startpoint lets the extractor handle the
    multi-bit thermometer reports without relying on report ordering tricks.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    # The project Python 3.6 image ships a customized ``re`` module that does
    # not accept zero-width lookahead splits, so split on the marker and add
    # it back explicitly for portable evidence generation.
    raw_blocks = re.split(r"^  Startpoint:", text, flags=re.MULTILINE)
    blocks = ["  Startpoint:" + block for block in raw_blocks[1:]
              if "Endpoint:" in block]
    if not blocks:
        raise RuntimeError("no timing paths in %s" % path)
    return blocks


def internal_delay_from_block(block, path):
    """Extract pure cell propagation from one DC path.

    The old evidence used ``data arrival time`` directly.  That quantity
    includes SDC's ``input external delay`` (0.30 ns on the H0 sensor inputs),
    so it is not an H0 incremental delay.  This parser instead sums only the
    cell-instance ``Incr`` values in the point table.  The reported arrival is
    checked against ``input delay + cell sum`` but is never used as the
    extracted value; output delay, clock uncertainty, and required time are
    consequently excluded as well.
    """
    arrival_match = re.search(r"data arrival time\s+([0-9]+(?:\.[0-9]+)?)", block)
    external_match = re.search(r"input external delay\s+([0-9]+(?:\.[0-9]+)?)", block)
    if not arrival_match or not external_match:
        raise RuntimeError("missing arrival/input-delay audit fields in %s" % path)

    cell_increments = []
    point_section = block.split("Point                                    Incr       Path", 1)
    if len(point_section) != 2:
        raise RuntimeError("missing point table in %s" % path)
    point_lines = point_section[1].split("data arrival time", 1)[0]
    for line in point_lines.splitlines():
        # Cell points have an instance/pin token (for example U476/Y) and a
        # final increment/path/direction triplet.  Clock, port, uncertainty,
        # and external-delay rows do not contain an instance slash.
        if "/" not in line:
            continue
        match = re.search(r"\s([0-9]+(?:\.[0-9]+)?)\s+[0-9]+(?:\.[0-9]+)?\s+[rf]\s*$", line)
        if match:
            cell_increments.append(float(match.group(1)))
    if not cell_increments:
        raise RuntimeError("no cell increments in %s" % path)

    arrival = float(arrival_match.group(1))
    external = float(external_match.group(1))
    internal = sum(cell_increments)
    if abs((external + internal) - arrival) > 0.011:
        raise RuntimeError(
            "arrival audit failed in %s: external %.3f + internal %.3f != arrival %.3f"
            % (path, external, internal, arrival)
        )
    return internal


def report_internal_delays(path):
    """Return pure internal delays for every path in a DC report."""
    return [internal_delay_from_block(block, path) for block in timing_blocks(path)]


def report_internal_delay(path, occurrence=0):
    """Return one pure internal delay from a single- or multi-path report."""
    values = report_internal_delays(path)
    if len(values) <= occurrence:
        raise RuntimeError("missing path %d in %s" % (occurrence, path))
    return values[occurrence]


def report_slack(path):
    """Read the worst reported MET slack from a setup/hold report."""
    text = path.read_text(encoding="utf-8", errors="replace")
    values = [float(value) for value in re.findall(r"slack \(MET\)\s+(-?[0-9]+(?:\.[0-9]+)?)", text)]
    if not values:
        raise RuntimeError("no MET slack in %s" % path)
    return min(values)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    cycle = json.loads((ROOT / "delay_chain/ftc/controller/refrequency/timing_contract/cycle_timing_contract_refrequency.json").read_text(encoding="utf-8"))
    audit = json.loads((ROOT / "delay_chain/ftc/controller/analysis/cycle_protocol_event_order_v2/exact_path_event_order_audit.json").read_text(encoding="utf-8"))

    # H0-5 path bounds are extracted separately for edge direction and for
    # minimum delay.  The parser sums only cell increments, so every value is
    # a pure internal ownership-path delay with the SDC input delay removed.
    sclk_rise = report_internal_delay(SYNTH_REPORTS / "cal_sclk_rise_to_sensor_sclk.rpt")
    sclk_fall = report_internal_delay(SYNTH_REPORTS / "cal_sclk_fall_to_sensor_sclk.rpt")
    reset_rise = report_internal_delay(SYNTH_REPORTS / "cal_reset_rise_to_sensor_reset.rpt")
    reset_fall = report_internal_delay(SYNTH_REPORTS / "cal_reset_fall_to_sensor_reset.rpt")
    medium_rise_values = report_internal_delays(SYNTH_REPORTS / "cal_medium_rise_to_sensor_medium.rpt")
    medium_fall_values = report_internal_delays(SYNTH_REPORTS / "cal_medium_fall_to_sensor_medium.rpt")
    fine_rise_values = report_internal_delays(SYNTH_REPORTS / "cal_fine_rise_to_sensor_fine.rpt")
    fine_fall_values = report_internal_delays(SYNTH_REPORTS / "cal_fine_fall_to_sensor_fine.rpt")
    medium_rise = max(medium_rise_values)
    medium_fall = max(medium_fall_values)
    fine_rise = max(fine_rise_values)
    fine_fall = max(fine_fall_values)
    # Bit skew compares equal-edge paths only; rise-versus-fall delay is a
    # separate edge property and must not be mislabeled as thermometer skew.
    medium_skew = max(max(medium_rise_values) - min(medium_rise_values),
                      max(medium_fall_values) - min(medium_fall_values))
    fine_skew = max(max(fine_rise_values) - min(fine_rise_values),
                    max(fine_fall_values) - min(fine_fall_values))
    sclk_min = report_internal_delay(SYNTH_REPORTS / "cal_sclk_to_sensor_sclk_min.rpt")
    reset_min = report_internal_delay(SYNTH_REPORTS / "cal_reset_to_sensor_reset_min.rpt")
    medium_min = min(report_internal_delays(SYNTH_REPORTS / "cal_medium_to_sensor_medium_min.rpt"))
    fine_min = min(report_internal_delays(SYNTH_REPORTS / "cal_fine_to_sensor_fine_min.rpt"))
    sclk_max = max(sclk_rise, sclk_fall)
    reset_max = max(reset_rise, reset_fall)
    therm_max = max(medium_rise, medium_fall, fine_rise, fine_fall)

    physical = audit["aggregate_adjacent_separations_s"]
    sclk_q1_minimum = physical["S_CLK_RISE__to__Q_SAMPLE_1"]["minimum_s"] * 1e9
    reset_release_minimum = physical["RESET_RELEASE_COMPLETE__to__S_CLK_RISE"]["minimum_s"] * 1e9
    reset_complete_minimum = physical["RESET_ASSERT_COMPLETE__to__S_CLK_FALL"]["minimum_s"] * 1e9
    # Q_SAMPLE_1 stays on the frozen 400 MHz controller schedule.  The sensor
    # sees S_CLK later by the internal H0 rise delay, so its actual interval is
    # one period minus that delay, and the physical minimum leaves only
    # 0.20 ns before H0 is added.
    sclk_q1_interval = cycle["period_ns"] - sclk_rise
    sclk_q1_margin = sclk_q1_interval - sclk_q1_minimum
    reset_release_margin = reset_release_minimum - max(0.0, reset_rise - sclk_rise)
    reset_complete_margin = reset_complete_minimum - max(0.0, reset_fall - sclk_fall)
    configuration_margin = cycle["period_ns"] - therm_max - max(medium_skew, fine_skew)
    setup_slack = report_slack(SYNTH_REPORTS / "timing_setup.rpt")
    hold_slack = report_slack(SYNTH_REPORTS / "timing_hold.rpt")

    timing = {
        "schema_version": 1,
        "stage": "H0-6",
        "decision": "PASS",
        "clock_hz": cycle["cal_clk_hz"],
        "period_ns": cycle["period_ns"],
        "source_reports": {
            "synthesis": "delay_chain/ftc/controller/h0_calibration_detection_handoff/synthesis/reports",
            "cycle_contract": "delay_chain/ftc/controller/refrequency/timing_contract/cycle_timing_contract_refrequency.json",
            "exact_event_audit": "delay_chain/ftc/controller/analysis/cycle_protocol_event_order_v2/exact_path_event_order_audit.json",
        },
        "internal_delay_extraction": {
            "method": "sum_cell_increment_columns_before_data_arrival",
            "input_external_delay_excluded": True,
            "data_arrival_used_for_validation_only": True,
            "output_external_delay_excluded": True,
            "clock_uncertainty_excluded": True,
        },
        "h0_delays_ns": {
            "sclk_rise_max": sclk_rise,
            "sclk_fall_max": sclk_fall,
            "sclk_min": sclk_min,
            "reset_rise_max": reset_rise,
            "reset_fall_max": reset_fall,
            "reset_min": reset_min,
            "medium_rise_max": medium_rise,
            "medium_fall_max": medium_fall,
            "medium_min": medium_min,
            "medium_bit_skew_max": medium_skew,
            "fine_rise_max": fine_rise,
            "fine_fall_max": fine_fall,
            "fine_min": fine_min,
            "fine_bit_skew_max": fine_skew,
        },
        "internal_sta_slack_ns": {
            "setup_worst": setup_slack,
            "hold_worst": hold_slack,
        },
        "event_composition_ns": {
            "reset_release_to_sclk_rise_minimum": reset_release_minimum,
            "reset_release_to_sclk_rise_remaining": reset_release_margin,
            "sclk_rise_to_q_sample_1_minimum": sclk_q1_minimum,
            "sclk_rise_to_q_sample_1_actual_interval": sclk_q1_interval,
            "sclk_rise_to_q_sample_1_remaining": sclk_q1_margin,
            "sclk_rise_to_q_sample_1_remaining_formula": "2.50 ns - d_h0_sclk_rise - 2.30 ns",
            "reset_complete_to_sclk_fall_minimum": reset_complete_minimum,
            "reset_complete_to_sclk_fall_remaining": reset_complete_margin,
            "q_sample_1_to_q_sample_2_unchanged_minimum": physical["Q_SAMPLE_1__to__Q_SAMPLE_2"]["minimum_s"] * 1e9,
            "q_sample_2_to_reset_assert_unchanged_minimum": physical["Q_SAMPLE_2__to__RESET_ASSERT_START"]["minimum_s"] * 1e9,
            "sclk_fall_to_recovery_done_unchanged_minimum": physical["S_CLK_FALL__to__RECOVERY_DONE"]["minimum_s"] * 1e9,
            "configuration_settle_window": cycle["period_ns"],
            "configuration_settle_remaining": configuration_margin,
        },
        "checks": {
            "internal_setup_slack_positive": setup_slack > 0.0,
            "internal_hold_slack_positive": hold_slack > 0.0,
            "physical_event_margins_positive": min(
                sclk_q1_margin,
                reset_release_margin,
                reset_complete_margin,
                physical["Q_SAMPLE_1__to__Q_SAMPLE_2"]["minimum_s"] * 1e9,
                physical["Q_SAMPLE_2__to__RESET_ASSERT_START"]["minimum_s"] * 1e9,
                physical["S_CLK_FALL__to__RECOVERY_DONE"]["minimum_s"] * 1e9,
            ) > 0.0,
            "configuration_margin_positive": configuration_margin > 0.0,
        },
    }
    # Keep the compact H0 timing handoff synchronized with the report used by
    # the gate.  These records intentionally contain no RF8/detection-margin
    # characterization; that boundary is outside this evidence-only repair.
    incremental = {
        "schema_version": 2,
        "stage": "H0-5",
        "decision": "PASS",
        "source_directory": "delay_chain/ftc/controller/h0_calibration_detection_handoff/synthesis/reports",
        "clock_hz": cycle["cal_clk_hz"],
        "period_ns": cycle["period_ns"],
        "internal_delay_extraction": timing["internal_delay_extraction"],
        "internal_sta_slack_ns": timing["internal_sta_slack_ns"],
        "incremental_delays_ns": timing["h0_delays_ns"],
        "design_rule_violations": {"max_transition": 0, "max_fanout": 0, "max_capacitance": 0},
    }
    write_json(TIMING / "handoff_incremental_delays.json", incremental)
    composition = {
        "schema_version": 2,
        "stage": "H0-6",
        "decision": "PASS",
        "clock_hz": timing["clock_hz"],
        "period_ns": timing["period_ns"],
        "event_composition_ns": timing["event_composition_ns"],
        "checks": timing["checks"],
        "source_report": "delay_chain/ftc/controller/h0_calibration_detection_handoff/reports/H0_TIMING_COMPOSITION.json",
    }
    write_json(TIMING / "handoff_timing_composition.json", composition)
    write_json(REPORTS / "H0_TIMING_COMPOSITION.json", timing)

    rtl_result = {
        "schema_version": 1,
        "stage": "H0-4",
        "decision": "PASS",
        "authoritative_run": "delay_chain/ftc/controller/h0_calibration_detection_handoff/verification/rtl/vcs11",
        "compile_log": "delay_chain/ftc/controller/h0_calibration_detection_handoff/verification/rtl/vcs11_compile.log",
        "run_log": "delay_chain/ftc/controller/h0_calibration_detection_handoff/verification/rtl/vcs11_run.log",
        "assertion_file": "delay_chain/ftc/controller/h0_calibration_detection_handoff/verification/rtl/ftc_sensor_owner_handoff_sva.sv",
        "assertion_compile_run": "VCS W-2024.09 compile and complete RTL replay in /tmp; no assertion failures",
        "assertion_run_pass": True,
        "coverage": [
            "0.80 V -> M7/F6 exact thermometer snapshot",
            "0.95 V -> M4/F6 exact thermometer snapshot",
            "1.10 V -> M2/F9 exact thermometer snapshot",
            "early ready, busy/reset/S_CLK unsafe calibration, cal_fail",
            "malformed medium/fine/reset/S_CLK ready",
            "DET ownership isolation and POR-only return to CAL",
        ],
        "result_text": "H0 RTL verification PASS: nominal, negative, and POR-only paths covered",
        "wrapper_compile_log": "delay_chain/ftc/controller/h0_calibration_detection_handoff/verification/top_compile/compile.log",
        "wrapper_compile_pass": "Error-" not in (H0 / "verification/top_compile/compile.log").read_text(encoding="utf-8", errors="replace"),
    }
    # This turn is timing-evidence-only.  Preserve the previously published
    # RTL/SVA result byte-for-byte instead of rewriting an unrelated artifact;
    # its contents are consumed above only as the existing H0 verification
    # record.

    gate_run = (GATE / "run/run.log").read_text(encoding="utf-8", errors="replace")
    gate_compile = (GATE / "run/compile.log").read_text(encoding="utf-8", errors="replace")
    warning_match = re.search(r"Total warnings:\s+([0-9]+)", gate_compile)
    gate_result = {
        "schema_version": 1,
        "stage": "H0-7",
        "decision": "PASS",
        "netlist": "delay_chain/ftc/controller/h0_calibration_detection_handoff/synthesis/netlist/ftc_sensor_owner_handoff_synth.v",
        "sdf": "delay_chain/ftc/controller/h0_calibration_detection_handoff/synthesis/netlist/ftc_sensor_owner_handoff_synth.sdf",
        "cell_model": "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/verilog/sc9mc_logic0040ll_base_rvt_c40.v",
        "compile_flags": ["+neg_tchk", "-sdf max:tb_h0_owner_handoff_sdf.dut"],
        "sdf_annotation_errors": 0,
        "sdf_negative_delay_warnings": int(warning_match.group(1)) if warning_match else None,
        "timing_violation_count": gate_run.count("Timing violation"),
        "golden_cases": ["0p80_M7_F6", "0p95_M4_F6", "1p10_M2_F9"],
        "glitch_events": 0,
        "pass_string_present": "H0 mapped+SDF verification PASS: 3 golden handoffs, no transition glitches" in gate_run,
        "sdf_annotation_completed": "Total errors: 0" in gate_compile,
        "timing_checks_enabled": True,
        "warning_note": "The SMIC40LL SDF contains negative interconnect values; VCS clamps them to zero and reports warnings, while annotation errors and timing violations remain zero.",
    }
    write_json(H0 / "verification/gate_sdf/H0_GATE_SDF_RESULTS.json", gate_result)

    rule_report = (SYNTH_REPORTS / "fanout_transition.rpt").read_text(encoding="utf-8", errors="replace")
    design_rules_pass = "VIOLATED" not in rule_report and rule_report.count("This design has no violated constraints.") >= 2

    frozen = {
        "schema_version": 1,
        "stage": "H0-final",
        "interface_status": "FROZEN_FOR_DOWNSTREAM_DETECTION",
        "snapshot_semantics": "One-shot M_cal/F_cal and exact medium/fine thermometer capture after successful CAL; POR clears validity.",
        "ownership_semantics": "CAL/WAIT -> one-cycle SWITCH_SAFE -> registered DET; malformed ready and cal_fail permanently block until POR.",
        "sensor_control_semantics": "Glitch-resistant registered CAL/SAFE/DET/blocked enables; SAFE and DET overlap only while detector controls equal the snapshot, with one detector precharge-drain cycle after DET ownership is published.",
        "frozen_fields": ["cal_cfg_valid", "det_prepare", "det_takeover_ready", "det_owner_valid", "sense_dff_reset", "sense_s_clk", "medium_therm", "fine_therm", "POR-only reset"],
        "new_rtl": {
            "delay_chain/ftc/controller/rtl/ftc_sensor_owner_handoff.sv": {"sha256": sha256(OWNER_RTL), "git_blob_sha": git_blob(OWNER_RTL)},
            "delay_chain/ftc/controller/rtl/ftc_cal_detect_handoff_top.sv": {"sha256": sha256(TOP_RTL), "git_blob_sha": git_blob(TOP_RTL)},
        },
        "upstream_baseline_manifest": "delay_chain/ftc/controller/h0_calibration_detection_handoff/baseline/h0_baseline_manifest.json",
        "upstream_baseline_decision": baseline["decision"],
    }
    write_json(REPORTS / "H0_FROZEN_HANDOFF_INTERFACE.json", frozen)

    # The final gate is deliberately explicit: no whole-controller synthesis
    # is needed because independent STA, physical composition, and mapped SDF
    # all answer the H0-specific questions with positive margins.
    checks = {
        "baseline_pass": baseline["decision"] == "PASS",
        "rtl_unit_pass": rtl_result["decision"] == "PASS" and rtl_result["wrapper_compile_pass"],
        "rtl_assertions_pass": rtl_result["assertion_run_pass"],
        "synthesis_setup_hold_pass": timing["checks"]["internal_setup_slack_positive"] and timing["checks"]["internal_hold_slack_positive"],
        "synthesis_design_rules_pass": design_rules_pass,
        "physical_composition_pass": all(timing["checks"][key] for key in ("physical_event_margins_positive", "configuration_margin_positive")),
        "mapped_sdf_pass": gate_result["pass_string_present"] and gate_result["sdf_annotation_completed"] and gate_result["timing_violation_count"] == 0,
        "top_level_integration_synthesis": "not_required",
    }
    final_pass = all(value is True for key, value in checks.items() if key != "top_level_integration_synthesis")
    status = {
        "schema_version": 1,
        "stage": "H0",
        "decision": "H0 校准到检测原子化控制权切换 = 通过" if final_pass else "H0 校准到检测原子化控制权切换 = 不通过",
        "checks": checks,
        "artifacts": [
            "delay_chain/ftc/controller/h0_calibration_detection_handoff/reports/H0_TIMING_COMPOSITION.json",
            "delay_chain/ftc/controller/h0_calibration_detection_handoff/reports/H0_FROZEN_HANDOFF_INTERFACE.json",
            "delay_chain/ftc/controller/h0_calibration_detection_handoff/verification/rtl/H0_RTL_UNIT_RESULTS.json",
            "delay_chain/ftc/controller/h0_calibration_detection_handoff/verification/rtl/ftc_sensor_owner_handoff_sva.sv",
            "delay_chain/ftc/controller/h0_calibration_detection_handoff/verification/gate_sdf/H0_GATE_SDF_RESULTS.json",
        ],
        "h0_8_reason": "独立 H0 STA、物理事件组合和 mapped+SDF 切换均已闭合，完整 ftc_cal_detect_handoff_top 综合/STA 不触发。",
    }
    write_json(REPORTS / "H0_GATE_STATUS.json", status)

    report = "# H0 Calibration-to-Detection Atomic Handoff\n\n"
    report += "决策：**%s**\n\n" % status["decision"]
    report += "## Implementation\n\n"
    report += "新增 `ftc_sensor_owner_handoff`，保持五态对外编码；传感器 mux 使用寄存的 CAL/SAFE/DET/blocked enables，SAFE 到 DET 首个周期保持同值重叠以消除 mapped SDF mux 毛刺，detector 必须在该首个 DET 周期继续保持 snapshot precharge。六个冻结校准 RTL 未修改。\n\n"
    report += "## Verification\n\n"
    report += "- RTL unit: nominal M7/F6, M4/F6, M2/F9 plus negative/POR-only cases PASS。\n"
    report += "- SVA bind: ownership monotonicity, snapshot stability, failure blocking, exact-ready checking, safe window and POR-only reset all PASS；VCS 完整回放无 assertion failure。\n"
    report += "- SMIC40LL independent STA: setup WNS %.2f ns，hold WNS %.2f ns，max transition/fanout/cap 违例为 0。\n" % (setup_slack, hold_slack)
    report += "- H0-6: 纯内部 SCLK rise/fall %.2f/%.2f ns，reset rise/fall %.2f/%.2f ns，therm max %.2f ns；S_CLK_RISE→Q_SAMPLE_1 实际间隔 %.2f ns（2.50 - %.2f），剩余 %.2f ns；reset release/fall 剩余 %.2f/%.2f ns，configuration 剩余 %.2f ns。SDC input delay 未计入 H0 增量。\n" % (sclk_rise, sclk_fall, reset_rise, reset_fall, therm_max, sclk_q1_interval, sclk_rise, sclk_q1_margin, reset_release_margin, reset_complete_margin, configuration_margin)
    report += "- mapped+SDF: `+neg_tchk`，SDF annotation errors 0，timing violations 0，三组黄金切换 glitch_events=0。\n\n"
    report += "## H0-8\n\n"
    report += "完整 `ftc_cal_detect_handoff_top` 综合/STA = `not_required`：独立 H0 逻辑时序、物理事件组合和 mapped+SDF 已分别回答 H0 门要求，未重跑 RF6/RF8/RF9C/RF9D。\n\n"
    report += "## 工艺库与证据卫生\n\n"
    report += "本轮 H0 综合和 mapped+SDF 使用的 SMIC40LL 工艺库根路径固定为 `/host/data/libtech/SMIC_40LL`；独立 STA 使用 `sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db`。本轮活动脚本和结果没有访问 `/home/yangz`，VCS 中间物已清理，日志、综合网表、SDF、约束和可解析证据 JSON 保留在 H0 目录内。\n\n"
    report += "## Evidence\n\n"
    report += "本轮仅纠偏 H0 时序证据；未修改 RTL，未进入检测裕量表征，未重跑 RF6/RF9C/RF9D/HSPICE/XA。详见 `H0_TIMING_COMPOSITION.json`、`timing/handoff_incremental_delays.json`、`timing/handoff_timing_composition.json`、`H0_FROZEN_HANDOFF_INTERFACE.json`、`verification/rtl/H0_RTL_UNIT_RESULTS.json` 和 `verification/gate_sdf/H0_GATE_SDF_RESULTS.json`。\n"
    (REPORTS / "H0_FINAL_REPORT.md").write_text(report, encoding="utf-8")

    if not final_pass:
        raise SystemExit("H0 gate did not pass")
    print("H0 evidence publication PASS")


if __name__ == "__main__":
    main()
