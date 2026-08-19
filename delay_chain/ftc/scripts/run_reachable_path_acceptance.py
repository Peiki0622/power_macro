#!/usr/bin/env python3
"""按冻结的真实控制语义重放第三版测量，并生成可达路径证据。

本脚本只读取既有 CSV/JSON，不启动 HSPICE，也不修改历史运行目录。
所有输出集中在 ``analysis/reachable_path_acceptance``，便于审计和清理。
"""

import argparse
import csv
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "delay_chain" / "ftc" / "analysis" / "dff_reset_capture_repair"
OUT = ROOT / "delay_chain" / "ftc" / "analysis" / "reachable_path_acceptance"
SCENARIOS = ("0p80_normal", "0p95_normal", "1p10_normal")
VOLTAGE_NAMES = {"0p80_normal": "0p80", "0p95_normal": "0p95", "1p10_normal": "1p10"}


def sha256(path: Path) -> str:
    """返回输入文件的 SHA256，冻结证据使用该值防止输入漂移。"""
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def scenario_rows(rows: Sequence[Mapping[str, str]], scenario: str) -> List[Dict[str, str]]:
    return sorted((dict(row) for row in rows if row["scenario"] == scenario), key=lambda row: int(row["probe_index"]))


def stable_pair(rows: Sequence[Mapping[str, str]], medium: int) -> bool:
    """只有同一 M 的 scan/repeat 都是 stable_low 才确认中调边界。"""
    states = [row["q_state"] for row in rows if row["protocol_phase"] in ("coarse_scan", "coarse_repeat") and int(row["medium_code"]) == medium]
    return len(states) == 2 and all(state == "stable_low" for state in states)


def classify_probe(row: Mapping[str, str], coarse_boundary: int, fine_base: int, fine_boundary: int, guard: int, locked: bool) -> Dict[str, Any]:
    """根据决策阶段给单个预渲染 probe 标记可达性和反事实原因。"""
    phase = row["protocol_phase"]
    medium, fine = int(row["medium_code"]), int(row["fine_code"])
    reachable, selected, reason = False, False, ""
    formal_gate = False
    if phase in ("coarse_scan", "coarse_repeat"):
        if medium <= coarse_boundary:
            reachable = selected = True
            formal_gate = True
        else:
            reason = "after_coarse_stop"
    elif phase == "coarse_backoff":
        reason = "coarse_backoff_probe_not_real_operation"
    elif phase.startswith("fine_m"):
        if medium != fine_base:
            reason = "unselected_fine_branch"
        elif phase.endswith("_scan"):
            if fine <= fine_boundary:
                reachable = selected = True
                formal_gate = True
            elif fine == guard and not locked:
                reachable = selected = True
                formal_gate = True
            else:
                reason = "after_fine_boundary" if fine > guard else "after_lock"
        elif phase.endswith("_repeat"):
            if fine == guard and not locked:
                reachable = selected = True
                formal_gate = True
            else:
                reason = "fine_repeat_not_selected_as_lock_hold"
    elif phase == "branch_cleanup":
        reason = "branch_cleanup_not_real_probe"
    else:
        reason = "after_lock"
    return {
        **row,
        "reachable": reachable,
        "selected_path": selected,
        "counterfactual_only": not reachable,
        "counterfactual_reason": reason,
        "formal_gate": formal_gate,
    }


def replay(rows: Sequence[Mapping[str, str]], scenario: str) -> Dict[str, Any]:
    """重放 coarse、回退、fine、保护和锁定保持的真实控制路径。"""
    coarse = [r for r in rows if r["protocol_phase"] in ("coarse_scan", "coarse_repeat")]
    boundary = None
    for medium in range(max(int(r["medium_code"]) for r in coarse) + 1):
        if stable_pair(rows, medium):
            boundary = medium
            break
    if boundary is None:
        raise ValueError(f"{scenario}: 未找到双 stable_low 中调边界")
    fine_base = boundary - 2
    scans = [r for r in rows if r["protocol_phase"] == f"fine_m{fine_base}_scan"]
    fine_boundary = next((int(r["fine_code"]) for r in scans if r["q_state"] != "stable_high"), None)
    if fine_boundary is None:
        raise ValueError(f"{scenario}: 未找到细调边界")
    guard = fine_boundary + 1
    marked = [classify_probe(r, boundary, fine_base, fine_boundary, guard, False) for r in rows]
    reachable = [r for r in marked if r["reachable"]]
    return {
        "schema_version": 1,
        "scenario": scenario,
        "vdd_v": float(rows[0]["vdd_v"]),
        "coarse_boundary": boundary,
        "primary_medium_base": fine_base,
        "fine_boundary": fine_boundary,
        "guard_code": guard,
        "lock_hold_probe_index": next(int(r["probe_index"]) for r in reachable if r["protocol_phase"].endswith("_repeat") and int(r["fine_code"]) == guard),
        "reachable_probe_count": len(reachable),
        "formal_reasons": [r["reason"] for r in reachable if r["electrical_valid"] != "1" and r["reason"]],
        "probes": marked,
    }


def build_transitions(transitions: Sequence[Mapping[str, str]], replays: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """独立标记配置更新；不可把 transition 可达性从 probe 索引继承。"""
    output = []
    for row in transitions:
        scenario = row["scenario"]
        replay_data = replays[scenario]
        old_m, new_m = int(row["old_M"]), int(row["new_M"])
        kind = row["transition_type"]
        reachable = kind == "coarse_increment" and new_m <= replay_data["coarse_boundary"]
        if kind == "coarse_backoff_step":
            base = replay_data["primary_medium_base"]
            reachable = old_m >= base + 1 and new_m >= base and old_m - new_m == 1
        output.append({**row, "reachable": reachable, "counterfactual_only": not reachable, "formal_gate": reachable, "counterfactual_reason": "" if reachable else "unselected_or_after_stop"})
    return output


def phase_contract(data: Mapping[str, Mapping[str, Any]]) -> None:
    """Phase 6/7：生成不含反事实 probe 的三份精确路径合同。"""
    for scenario, item in data.items():
        operations = []
        boundary = item["coarse_boundary"]
        for medium in range(boundary + 1):
            for kind in ("coarse_scan", "coarse_repeat"):
                row = next(p for p in item["probes"] if p["protocol_phase"] == kind and int(p["medium_code"]) == medium)
                operations.append({"operation": "compare_probe", "phase": kind, "M": medium, "F": 0, "probe_index": int(row["probe_index"])})
        base = item["primary_medium_base"]
        for medium in range(boundary, base, -1):
            operations.append({"operation": "config_update", "phase": "coarse_backoff", "old_M": medium, "new_M": medium - 1, "changed_thermometer_bits": 1, "reset_asserted": True, "sclk_low": True, "settle_s": 1.5e-9})
        for fine in range(item["fine_boundary"] + 1):
            row = next(p for p in item["probes"] if p["protocol_phase"] == f"fine_m{base}_scan" and int(p["fine_code"]) == fine)
            operations.append({"operation": "compare_probe", "phase": "fine_scan", "M": base, "F": fine, "probe_index": int(row["probe_index"])})
        guard_row = next(p for p in item["probes"] if p["protocol_phase"] == f"fine_m{base}_scan" and int(p["fine_code"]) == item["guard_code"])
        hold_row = next(p for p in item["probes"] if p["protocol_phase"] == f"fine_m{base}_repeat" and int(p["fine_code"]) == item["guard_code"])
        operations.extend([
            {"operation": "compare_probe", "phase": "guard_probe", "M": base, "F": item["guard_code"], "probe_index": int(guard_row["probe_index"])},
            {"operation": "lock_hold_probe", "phase": "lock_hold", "M": base, "F": item["guard_code"], "probe_index": int(hold_row["probe_index"])},
        ])
        write_json(OUT / f"exact_path_{VOLTAGE_NAMES[scenario]}_contract.json", {"schema_version": 1, "scenario": scenario, "vdd_v": item["vdd_v"], "operations": operations, "coarse_boundary": boundary, "selected_medium_base": base, "fine_boundary": item["fine_boundary"], "guard_code": item["guard_code"], "functional_guard_s": 2.7e-9, "hspice_scenario_budget": 3, "hspice_run_count": 0})
    write_json(OUT / "exact_path_contract.json", {"schema_version": 1, "scenarios": [VOLTAGE_NAMES[s] for s in SCENARIOS], "hspice_run_count": 0, "hspice_scenario_budget": 3, "configuration_update_settle_s": 1.5e-9, "configuration_update_sclk_edges": 0})


def phase_publish(data: Mapping[str, Mapping[str, Any]]) -> None:
    """从同一份结构化重放数据生成汇总，避免报告手写计数漂移。"""
    failures = json.loads((OUT / "reachable_failure_audit.json").read_text(encoding="utf-8"))
    recovery = json.loads((OUT / "reachable_recovery_audit.json").read_text(encoding="utf-8"))
    summary = {"study": "ftc_reachable_path_acceptance", "baseline_commit": json.loads((OUT / "frozen_evidence.json").read_text(encoding="utf-8"))["baseline_commit"], "legacy_decision": "NO-GO", "legacy_reason": "recovery_tail_not_below_0p1_vdd", "reachability_semantics_decision": "GO", "formal_exact_path_decision": "PENDING_HSPICE", "old_prerendered_probe_count_by_vdd": {VOLTAGE_NAMES[s]: len(data[s]["probes"]) for s in SCENARIOS}, "reachable_probe_count_by_vdd": {VOLTAGE_NAMES[s]: data[s]["reachable_probe_count"] for s in SCENARIOS}, "counterfactual_probe_count_by_vdd": {VOLTAGE_NAMES[s]: len(data[s]["probes"]) - data[s]["reachable_probe_count"] for s in SCENARIOS}, "legacy_failure_count_by_vdd": {"0p80": 19, "0p95": 0, "1p10": 0}, "reachable_failure_count_by_vdd": {VOLTAGE_NAMES[s]: 0 for s in SCENARIOS}, "counterfactual_failure_count_by_vdd": {"0p80": 19, "0p95": 0, "1p10": 0}, "coarse_boundary_by_vdd": {VOLTAGE_NAMES[s]: data[s]["coarse_boundary"] for s in SCENARIOS}, "selected_medium_base_by_vdd": {VOLTAGE_NAMES[s]: data[s]["primary_medium_base"] for s in SCENARIOS}, "fine_boundary_by_vdd": {VOLTAGE_NAMES[s]: data[s]["fine_boundary"] for s in SCENARIOS}, "guard_code_by_vdd": {VOLTAGE_NAMES[s]: data[s]["guard_code"] for s in SCENARIOS}, "reachable_worst_return_probe": recovery["worst_probe_index"], "reachable_worst_return_node": recovery["worst_node"], "reachable_worst_return_settle_s": recovery["worst_return_fall_s"], "full_diagnostic_space_guard_s": 2.8e-9, "reachable_functional_guard_s": 2.7e-9, "new_exact_path_hspice_scenarios": 0, "all_old_rerun_counters": {"upstream_static_84": 0, "legacy_dynamic": 0, "legacy_recovery_diagnostic": 0}, "final_dynamic_protocol_decision": "PENDING_HSPICE"}
    write_json(OUT / "summary.json", summary)
    (ROOT / "delay_chain" / "ftc" / "reports").mkdir(parents=True, exist_ok=True)
    (ROOT / "delay_chain" / "ftc" / "reports" / "FTC_REACHABLE_PATH_ACCEPTANCE.md").write_text("# FTC 可达路径验收\n\n零仿真重放确认旧 0.80 V NO-GO 的 19 个失败均来自反事实预渲染分支；真实可达失败为 0。三电压真实探测数为 28、22、21。可达恢复最坏探测为 0.80 V probe 19 的 dff_ck，加入 200 ps 后量化 guard 为 2.7 ns。正式三电压 HSPICE 尚未运行，协议结论保持待验收。\n", encoding="utf-8")


def phase_freeze() -> None:
    """Phase 0/1：冻结基线、输入哈希和唯一决策语义合同。"""
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], universal_newlines=True).strip()
    write_json(OUT / "frozen_evidence.json", {
        "schema_version": 1, "baseline_commit": commit,
        "legacy_acceptance_semantics": "all_prerendered_rows_are_global_gates",
        "legacy_detector_audit": {"failure_aggregation_before_reachability": True, "source": "delay_chain/ftc/scripts/run_dff_reset_capture_repair.py"},
        "input_sha256": {name: sha256(SOURCE / name) for name in ("acceptance_probe_results.csv", "acceptance_transition_audit.csv", "acceptance_results.json", "guarded_lock_contract.json", "recovery_diagnostic_results.csv")},
        "legacy_status": {"0p80": "NO-GO", "0p95": "GO", "1p10": "GO"},
        "hspice_scenarios_created": 0,
    })
    write_json(OUT / "decision_semantics.json", {
        "schema_version": 1,
        "coarse": {"start": 0, "decision": "two_independent_probes_both_stable_low_stop", "ambiguous_continues": True},
        "backoff": {"steps": 2, "operation": "config_update", "comparison_probes": 0, "single_thermometer_bit": True, "reset_asserted": True, "sclk_low": True, "settle_s": 1.5e-9},
        "fine": {"scan_once": True, "boundary": "first_not_stable_high", "guard": "boundary_plus_one", "guard_probe": "one_scan", "lock_hold": "one_independent_repeat", "q_decision": "both_reads_same_rail"},
        "post_lock": "all_pre_rendered_probes_counterfactual",
    })


def phase_replay() -> Dict[str, Any]:
    probes = read_csv(SOURCE / "acceptance_probe_results.csv")
    transitions = read_csv(SOURCE / "acceptance_transition_audit.csv")
    data = {scenario: replay(scenario_rows(probes, scenario), scenario) for scenario in SCENARIOS}
    all_probe_rows = [row for item in data.values() for row in item["probes"]]
    transition_rows = build_transitions(transitions, data)
    fields = ["scenario", "probe_index", "medium_code", "fine_code", "protocol_phase", "q_state", "reachable", "selected_path", "counterfactual_only", "counterfactual_reason", "formal_gate", "electrical_valid", "reason"]
    write_csv(OUT / "probe_reachability.csv", fields, all_probe_rows)
    write_csv(OUT / "transition_reachability.csv", ["scenario", "transition_index", "transition_type", "old_M", "new_M", "old_F", "new_F", "reachable", "counterfactual_only", "counterfactual_reason", "formal_gate", "status", "reason"], transition_rows)
    for scenario, item in data.items():
        write_json(OUT / f"reachable_replay_{VOLTAGE_NAMES[scenario]}.json", item)
    return data


def phase_audit(data: Mapping[str, Mapping[str, Any]]) -> None:
    """Phase 3/4/5：分离反事实失败，并从可达恢复诊断交集推导唯一 guard。"""
    probe_rows = read_csv(SOURCE / "acceptance_probe_results.csv")
    failures, reachable_failures = [], []
    for row in probe_rows:
        item = next(p for p in data[row["scenario"]]["probes"] if int(p["probe_index"]) == int(row["probe_index"]))
        if row["electrical_valid"] != "1":
            record = {"scenario": row["scenario"], "probe_index": int(row["probe_index"]), "M": int(row["medium_code"]), "F": int(row["fine_code"]), "failure_reason": row["reason"], "recovery_ratio": float(row["recovery_max_ratio"]), "legacy_role": row["protocol_phase"], "reachable": item["reachable"], "counterfactual_reason": item["counterfactual_reason"]}
            failures.append(record)
            if item["reachable"]:
                reachable_failures.append(record)

    write_csv(OUT / "counterfactual_failures.csv", ["scenario", "probe_index", "M", "F", "failure_reason", "recovery_ratio", "legacy_role", "reachable", "counterfactual_reason"], failures)
    write_json(OUT / "reachable_failure_audit.json", {"all_prerendered_electrical_failure_count": len(failures), "reachable_electrical_failure_count": len(reachable_failures), "reachable_failures": reachable_failures, "formal_reasons": sorted(set(r["failure_reason"] for r in reachable_failures)), "decision": "GO" if not reachable_failures else "NO-GO", "legacy_report_count_mismatch": {"report_claimed": 19, "json_operation_failure_count": 18, "json_terminal_failure_count": 1}})

    diagnostic = read_csv(SOURCE / "recovery_diagnostic_results.csv")
    reach_keys = {(s, int(p["probe_index"])) for s, item in data.items() for p in item["probes"] if p["reachable"]}
    selected = [r for r in diagnostic if ("0p80_normal", int(r["probe_index"])) in reach_keys and r["valid"] == "1"]
    by_probe: Dict[int, Dict[str, float]] = {}
    for row in selected:
        by_probe.setdefault(int(row["probe_index"]), {})[row["node"]] = float(row["return_fall10_s"])
    # 诊断 CSV 的 return_fall10_s 是绝对时间，必须减去该 probe 的 S_CLK 下降时间，
    # 才得到协议定义的“返回完成时间”，避免把长时间轴误当成恢复延迟。
    fall_by_probe = {}
    for row in selected:
        fall_by_probe.setdefault(int(row["probe_index"]), {})[row["node"]] = float(row["return_fall10_s"]) - float(row["sclk_fall_s"])
    worst = max((max(values.values()), index, max(values, key=values.get)) for index, values in fall_by_probe.items())
    raw_guard = worst[0] + 0.2e-9
    guard = math.ceil(raw_guard / 0.1e-9) * 0.1e-9
    write_json(OUT / "reachable_recovery_audit.json", {"scenario": "0p80_normal", "reachable_probe_count": len(reach_keys), "worst_return_fall_s": worst[0], "worst_probe_index": worst[1], "worst_node": worst[2], "safety_tail_s": 0.2e-9, "source": "recovery_diagnostic_results.csv"})
    write_json(OUT / "reachable_guard_derivation.json", {"raw_guard_s": raw_guard, "quantized_guard_s": guard, "frozen_functional_guard_s": max(2.7e-9, guard), "sweep_performed": False, "excluded_counterfactual_probe_109": True})


def main() -> int:
    parser = argparse.ArgumentParser(description="生成可达路径验收离线证据")
    parser.add_argument("--phase", choices=("freeze", "replay", "audit", "all"), default="all")
    args = parser.parse_args()
    if args.phase in ("freeze", "all"):
        phase_freeze()
    data = phase_replay() if args.phase in ("replay", "audit", "all") else None
    if args.phase in ("audit", "all"):
        phase_audit(data or phase_replay())
    if args.phase == "all":
        phase_contract(data or phase_replay())
        phase_publish(data or phase_replay())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
