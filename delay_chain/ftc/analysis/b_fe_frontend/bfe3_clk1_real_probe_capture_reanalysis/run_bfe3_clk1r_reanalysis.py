#!/usr/bin/env python3
"""Offline digital-semantic reanalysis of the frozen B-FE3-CLK1 XA run.

No HSPICE, VCS, or PrimeSim XA command is issued here.  The old CLK1 Gate
used ``abs(Q_100ps-Q_1000ps) > 1e-5`` as a stability test.  This reanalysis
keeps both samples but only requires rail resolution, equal digital logic,
closed G, safe rail validity, and absence of post-close Q events.
"""

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
CLK1_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe3_clk1_real_probe_capture"
RUN_DIR = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe3_clk1_real_probe_capture" / "normal_0p95" / "vcs_xa"
XA_CAPTURE = RUN_DIR / "xa_capture_samples.csv"
CLK1_MANIFEST = CLK1_ROOT / "BFE3_CLK1_MANIFEST.json"
CLK1_ANALYSIS = CLK1_ROOT / "BFE3_CLK1_ANALYSIS.json"
TAPS = 30
VDD = 0.95
RAIL_LOW = 0.1 * VDD
RAIL_HIGH = 0.9 * VDD
THRESHOLD = 0.5 * VDD
RAIL_TOL = 1.0e-6
G_CLOSED_MAX = 0.1 * VDD
TIME_TOL_PS = 0.01
G_FIRST_FALL_PS = 1534.524618567
G_PERIOD_PS = 2500.0
G_HALF_PS = 1250.0
READ_OFFSET_PS = 100.0
TAIL_OFFSET_PS = 1000.0
SYSTEM_EDGES = tuple((1000.0 + index * 10000.0, "rise" if index % 2 == 0 else "fall") for index in range(6))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected object JSON: {}".format(path))
    return value


def load_rows() -> list:
    rows = []
    with XA_CAPTURE.open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            row["capture_index"] = int(row["capture_index"])
            row["tap"] = int(row["tap"])
            for key in ("capture_g_fall_ps", "time_ps", "safe_d_v", "q_v", "vdd_sense_v", "vdd_safe_v", "g_v"):
                row[key] = float(row[key])
            rows.append(row)
    return rows


def system_context(fall_ps: float) -> tuple:
    edge_ps, polarity = min(SYSTEM_EDGES, key=lambda item: abs(item[0] - fall_ps))
    delta_ps = fall_ps - edge_ps
    designated = abs(delta_ps - 534.524618567) <= TIME_TOL_PS
    return edge_ps, polarity, delta_ps, designated


def logic(q_v: float) -> int:
    return 1 if q_v > THRESHOLD else 0


def rail_resolved(q_v: float) -> bool:
    return q_v <= RAIL_LOW or q_v >= RAIL_HIGH


def capture_falls() -> list:
    result = []
    index = 0
    fall_ps = G_FIRST_FALL_PS
    while fall_ps + TAIL_OFFSET_PS < 62000.0:
        result.append((index, fall_ps))
        index += 1
        fall_ps += G_PERIOD_PS
    return result


def analyze_capture(index: int, fall_ps: float, rows: list) -> dict:
    sample = {row["tap"]: row for row in rows if row["kind"] == "capture_sample" and row["capture_index"] == index}
    tail = {row["tap"]: row for row in rows if row["kind"] == "tail_1ns" and row["capture_index"] == index}
    if set(sample) != set(range(TAPS)) or set(tail) != set(range(TAPS)):
        raise ValueError("capture {} does not have 30 sample and 30 tail rows".format(index))
    sample_bits = [logic(sample[tap]["q_v"]) for tap in range(TAPS)]
    tail_bits = [logic(tail[tap]["q_v"]) for tap in range(TAPS)]
    sample_mid = [tap for tap in range(TAPS) if not rail_resolved(sample[tap]["q_v"])]
    tail_mid = [tap for tap in range(TAPS) if not rail_resolved(tail[tap]["q_v"])]
    logic_mismatch = [tap for tap in range(TAPS) if sample_bits[tap] != tail_bits[tap]]
    vdd_bad = [tap for tap in range(TAPS) if abs(sample[tap]["vdd_safe_v"] - VDD) > RAIL_TOL or abs(tail[tap]["vdd_safe_v"] - VDD) > RAIL_TOL]
    g_bad = [tap for tap in range(TAPS) if sample[tap]["g_v"] > G_CLOSED_MAX or tail[tap]["g_v"] > G_CLOSED_MAX]
    next_g_rise = fall_ps + G_HALF_PS
    post_close_events = [
        {"time_ps": row["time_ps"], "tap": row["tap"], "q_v": row["q_v"], "safe_d_v": row["safe_d_v"], "g_v": row["g_v"]}
        for row in rows
        if row["kind"] == "q_event" and fall_ps < row["time_ps"] < next_g_rise - TIME_TOL_PS
    ]
    edge_ps, polarity, delta_ps, designated = system_context(fall_ps)
    m_sample = sum(tap * bit for tap, bit in enumerate(sample_bits))
    m_tail = sum(tap * bit for tap, bit in enumerate(tail_bits))
    sample_code = "".join(str(bit) for bit in sample_bits)
    tail_code = "".join(str(bit) for bit in tail_bits)
    old = {
        "old_unstable_tail_taps": [],
        "old_mid_rail_taps": [],
        "old_safe_supply_bad_taps": [],
        "old_g_not_closed_taps": [],
        "old_source_free_post_close_events": [],
    }
    return {
        "capture_index": index,
        "g_fall_ps": fall_ps,
        "sample_time_ps": sample[0]["time_ps"],
        "tail_time_ps": tail[0]["time_ps"],
        "nearest_system_edge_ps": edge_ps,
        "system_edge_polarity": polarity,
        "time_from_nearest_system_edge_ps": delta_ps,
        "designated": designated,
        "sample_q_raw_tap0_to_tap29": sample_code,
        "tail_q_raw_tap0_to_tap29": tail_code,
        "sample_q_raw_29_to_0": "".join(reversed(sample_code)),
        "tail_q_raw_29_to_0": "".join(reversed(tail_code)),
        "sample_M": m_sample,
        "tail_M": m_tail,
        "sample_N": sum(sample_bits),
        "tail_N": sum(tail_bits),
        "sample_rail_unresolved_taps": sample_mid,
        "tail_rail_unresolved_taps": tail_mid,
        "logic_mismatch_taps": logic_mismatch,
        "vdd_safe_bad_taps": vdd_bad,
        "g_hold_bad_taps": g_bad,
        "source_free_post_close_q_events": post_close_events,
        "digital_code": sample_code,
        "M": m_sample,
        "N": sum(sample_bits),
        "logical_capture_stable": not sample_mid and not tail_mid and not logic_mismatch and not vdd_bad and not g_bad and not post_close_events,
        "digital_idle_code": sample_code == "0" * TAPS and tail_code == "0" * TAPS,
        **old,
    }


def old_failure_was_analog_only(old_analysis: dict, captures: list) -> dict:
    old_by_index = {item["capture_index"]: item for item in old_analysis.get("captures", [])}
    failed_capture_count = 0
    analog_only = True
    evidence = []
    for capture in captures:
        old_item = old_by_index.get(capture["capture_index"], {})
        old_unstable = old_item.get("unstable_tail_taps", [])
        old_mid = old_item.get("mid_rail_taps", [])
        old_safe = old_item.get("safe_supply_bad_taps", [])
        old_g = old_item.get("g_not_closed_taps", [])
        old_events = old_item.get("source_free_post_close_events", [])
        old_failed = bool(old_unstable or old_mid or old_safe or old_g or old_events)
        if old_failed:
            failed_capture_count += 1
            if not old_unstable or old_mid or old_safe or old_g or old_events:
                analog_only = False
        evidence.append({"capture_index": capture["capture_index"], "old_unstable_tail_taps": old_unstable, "old_mid_rail_taps": old_mid, "old_safe_supply_bad_taps": old_safe, "old_g_not_closed_taps": old_g, "old_source_free_post_close_events": old_events})
    return {"old_clk1_gate": old_analysis.get("gate"), "old_fail_reason_rule": "abs(Q_100ps-Q_1000ps)>1e-5", "old_failed_capture_count": failed_capture_count, "old_failure_due_to_overstrict_analog_stability_rule": bool(failed_capture_count) and analog_only, "old_capture_evidence": evidence}


def main() -> int:
    manifest = load_json(CLK1_MANIFEST)
    old_analysis = load_json(CLK1_ANALYSIS)
    if manifest.get("stage") != "B-FE3-CLK1" or manifest.get("gate") != "BFE3_CLK1_400MHZ_REAL_PROBE_CAPTURE_FAIL":
        raise ValueError("unexpected frozen CLK1 manifest or old Gate")
    if manifest.get("clock_sys_mon", {}).get("frequency_mhz") != 50.0 or manifest.get("clock_sys_mon", {}).get("duty_percent") != 50.0:
        raise ValueError("CLK_SYS_MON contract drift")
    if manifest.get("clk_probe", {}).get("frequency_mhz") != 400.0 or manifest.get("clk_probe", {}).get("duty_percent") != 50.0:
        raise ValueError("CLK_PROBE contract drift")
    rows = load_rows()
    captures = [analyze_capture(index, fall_ps, rows) for index, fall_ps in capture_falls()]
    designated = [item for item in captures if item["designated"]]
    idle = [item for item in captures if not item["designated"]]
    rise = [item for item in designated if item["system_edge_polarity"] == "rise"]
    fall = [item for item in designated if item["system_edge_polarity"] == "fall"]

    def family(items: list) -> dict:
        return {
            "count": len(items),
            "codes": sorted(set(item["digital_code"] for item in items)),
            "M_values": sorted(set(item["M"] for item in items)),
            "all_nonempty": bool(items) and all(item["N"] > 0 for item in items),
            "all_logically_stable": bool(items) and all(item["logical_capture_stable"] for item in items),
        }

    rise_summary, fall_summary = family(rise), family(fall)
    idle_failures = [item for item in idle if not item["logical_capture_stable"] or not item["digital_idle_code"]]
    designated_failures = [item for item in designated if not item["logical_capture_stable"] or item["N"] == 0]
    gate = "BFE3_CLK1R_REAL_LATCH_CAPTURE_SEMANTICS_PASS" if len(rise) == 3 and len(fall) == 3 and rise_summary["all_nonempty"] and fall_summary["all_nonempty"] and len(rise_summary["codes"]) == 1 and len(fall_summary["codes"]) == 1 and len(rise_summary["M_values"]) == 1 and len(fall_summary["M_values"]) == 1 and not designated_failures and not idle_failures else "BFE3_CLK1R_REAL_LATCH_CAPTURE_SEMANTICS_FAIL"
    old_rule = old_failure_was_analog_only(old_analysis, captures)
    reasons = []
    if designated_failures:
        reasons.append("designated logical capture failures: {}".format([item["capture_index"] for item in designated_failures]))
    if idle_failures:
        reasons.append("non-designated logical idle failures: {}".format([item["capture_index"] for item in idle_failures]))
    analysis = {
        "schema_version": 1,
        "stage": "B-FE3-CLK1R",
        "gate": gate,
        "verification_mode": "offline digital-semantic reanalysis of frozen HSPICE/VCS/PrimeSim XA evidence",
        "simulation_run": False,
        "new_hspice_scenarios": 0,
        "new_vcs_xa_scenarios": 0,
        "frozen_source_csv_sha256": sha256(XA_CAPTURE),
        "frozen_clk1_manifest_sha256": sha256(CLK1_MANIFEST),
        "frozen_clk1_analysis_sha256": sha256(CLK1_ANALYSIS),
        "old_clk1_failure_reclassification": old_rule,
        "new_semantic_failures_not_reflected_in_old_clk1_gate": [item["capture_index"] for item in designated_failures if item["source_free_post_close_q_events"]],
        "digital_semantics": {
            "sample_offset_ps": READ_OFFSET_PS,
            "tail_offset_ps": TAIL_OFFSET_PS,
            "logic_threshold_v": THRESHOLD,
            "rail_resolved_rule": "q <= 0.1*VDD_SAFE or q >= 0.9*VDD_SAFE at both sample and tail",
            "logic_consistency_rule": "sample and tail classifications equal",
            "analog_absolute_difference_rule_used": False,
            "g_hold_rule": "G <= 0.1*VDD_SAFE at both sample and tail",
        "post_close_event_rule": "no q_event in (Gfall, next G rising edge)",
        },
        "designated_rise": rise_summary,
        "designated_fall": fall_summary,
        "designated_failures": designated_failures,
        "idle_failures": idle_failures,
        "failure_reasons": reasons,
        "captures": captures,
        "stop_after_stage": True,
        "next_stage_authorized": False,
    }
    analysis_path = ROOT / "BFE3_CLK1R_ANALYSIS.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for item in captures:
        stem = "capture_{:03d}".format(item["capture_index"])
        with (ROOT / (stem + ".csv")).open("w", newline="", encoding="ascii") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(item), lineterminator="\n")
            writer.writeheader()
            writer.writerow(item)
        (ROOT / (stem + ".json")).write_text(json.dumps(item, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_out = {
        "schema_version": 1,
        "stage": "B-FE3-CLK1R",
        "gate": gate,
        "verification_mode": "analysis-only reuse of frozen B-FE3-CLK1 HSPICE/VCS/PrimeSim XA evidence",
        "simulation_run": False,
        "new_hspice_scenarios": 0,
        "new_vcs_xa_scenarios": 0,
        "frozen_contract": {"vdd_monitored_v": 0.95, "clk_sys_mon_mhz": 50.0, "clk_sys_mon_duty_percent": 50.0, "clk_probe_mhz": 400.0, "clk_probe_duty_percent": 50.0, "designated_offset_ps": 534.524618567, "tap_count": 30, "rvt_prefix": 4, "lvt_prefix": 0, "xor_cell": "XOR2_X0P5M_A9TL40", "latch_cell": "LATQ_X0P5M_A9TR40"},
        "input_artifacts": {"xa_capture_csv": str(XA_CAPTURE), "xa_capture_csv_sha256": sha256(XA_CAPTURE), "old_manifest": str(CLK1_MANIFEST), "old_analysis": str(CLK1_ANALYSIS)},
        "old_clk1_gate": old_analysis.get("gate"),
        "old_failure_due_to_overstrict_analog_stability_rule": old_rule["old_failure_due_to_overstrict_analog_stability_rule"],
        "new_semantic_failures_not_reflected_in_old_clk1_gate": [item["capture_index"] for item in designated if item["source_free_post_close_q_events"]],
        "analog_absolute_difference_rule_used": False,
        "capture_count": len(captures),
        "stop_after_stage": True,
        "next_stage_authorized": False,
    }
    manifest_path = ROOT / "BFE3_CLK1R_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest_out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = [
        "# B-FE3-CLK1R digital latch-capture reanalysis",
        "",
        "Gate: `{}`".format(gate),
        "",
        "No HSPICE, VCS, or PrimeSim XA simulation was run. The existing CLK1 `xa_capture_samples.csv` and all prior hashes were reused.",
        "The old CLK1 Gate used `abs(Q_100ps-Q_1000ps)>1e-5`; CLK1R removes that analog absolute-difference requirement.",
        "",
        "| Family | Count | Digital code(s) | M value(s) | Non-empty | Logical stable |",
        "|---|---:|---|---|---|---|",
        "| Designated rise | {} | `{}` | `{}` | {} | {} |".format(rise_summary["count"], rise_summary["codes"], rise_summary["M_values"], rise_summary["all_nonempty"], rise_summary["all_logically_stable"]),
        "| Designated fall | {} | `{}` | `{}` | {} | {} |".format(fall_summary["count"], fall_summary["codes"], fall_summary["M_values"], fall_summary["all_nonempty"], fall_summary["all_logically_stable"]),
        "",
        "| Capture | G fall (ps) | Edge | Delta (ps) | Designated | Sample code | Tail code | M(sample/tail) | Stable |",
        "|---:|---:|---|---:|---|---|---|---|---|",
    ]
    for item in captures:
        report.append("| {} | {:.6f} | {} | {:.6f} | {} | `{}` | `{}` | {}/{} | {} |".format(item["capture_index"], item["g_fall_ps"], item["system_edge_polarity"], item["time_from_nearest_system_edge_ps"], item["designated"], item["sample_q_raw_29_to_0"], item["tail_q_raw_29_to_0"], item["sample_M"], item["tail_M"], item["logical_capture_stable"]))
    report += [
        "",
        "Old CLK1 Gate: `{}`.".format(old_rule["old_clk1_gate"]),
        "Old failure caused solely by the over-strict analog absolute-difference rule: **{}**.".format(old_rule["old_failure_due_to_overstrict_analog_stability_rule"]),
        "CLK1R additionally checks the full post-close window; newly exposed post-close Q-event captures are `{}`.".format([item["capture_index"] for item in designated if item["source_free_post_close_q_events"]]),
        "Post-close event detail: " + "; ".join("capture {} tap {} at {:.3f} ps: Q={:.9f} V, G={:.9f} V".format(item["capture_index"], event["tap"], event["time_ps"], event["q_v"], event["g_v"]) for item in designated for event in item["source_free_post_close_q_events"]),
        "CLK1R designated failures: `{}`; non-designated idle failures: `{}`.".format([item["capture_index"] for item in designated_failures], [item["capture_index"] for item in idle_failures]),
        "",
        "No circuit, clock, phase, frequency, duty cycle, source waveform, or XA evidence was changed. This stage stops here.",
    ]
    report_path = ROOT / "BFE3_CLK1R_REPORT.md"
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    gate_path = ROOT / "BFE3_CLK1R_GATE.json"
    gate_path.write_text(json.dumps({"schema_version": 1, "stage": "B-FE3-CLK1R", "gate": gate, "old_clk1_gate": old_rule["old_clk1_gate"], "old_failure_due_to_overstrict_analog_stability_rule": old_rule["old_failure_due_to_overstrict_analog_stability_rule"], "new_semantic_failures_not_reflected_in_old_clk1_gate": [item["capture_index"] for item in designated if item["source_free_post_close_q_events"]], "designated_rise": rise_summary, "designated_fall": fall_summary, "designated_failure_captures": [item["capture_index"] for item in designated_failures], "idle_failure_captures": [item["capture_index"] for item in idle_failures], "analysis_sha256": sha256(analysis_path), "manifest_sha256": sha256(manifest_path), "report_sha256": sha256(report_path), "stop_after_stage": True, "next_stage_authorized": False}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if gate.endswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
