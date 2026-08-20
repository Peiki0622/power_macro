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


def probe_evidence_key(scenario: str, probe_index: int) -> str:
    """为旧 probe 行生成稳定键；该键仅指向证据，绝不决定控制流。"""
    return f"probe:{scenario}:{probe_index}"


def transition_evidence_key(row: Mapping[str, str]) -> str:
    """为旧转换行生成完整身份键，避免同一 M/F 转换被不同历史上下文混用。"""
    return "transition:{scenario}:{transition_type}:{old_M}:{new_M}:{old_F}:{new_F}".format(**row)


def unique_probe(rows: Sequence[Mapping[str, str]], scenario: str, phase: str, medium: int, fine: int) -> Mapping[str, str]:
    """按完整旧 probe 身份取唯一行；缺失或重复均表示不能可靠复用金证据。"""
    matches = [row for row in rows if row["protocol_phase"] == phase and int(row["medium_code"]) == medium and int(row["fine_code"]) == fine]
    if len(matches) != 1:
        raise ValueError(f"{scenario}: probe 证据不唯一: phase={phase}, M={medium}, F={fine}, count={len(matches)}")
    return matches[0]


def build_operations(rows: Sequence[Mapping[str, str]], scenario: str, boundary: int, fine_base: int, fine_boundary: int) -> List[Dict[str, Any]]:
    """由冻结控制协议生成唯一操作序列，而不是从旧标签反推可达性。

    ``initial_state`` 是起始元数据，保留在序列中以便以后 deck 调度检查，
    但不属于计划定义的可执行操作计数。其余每个状态变化或 probe 都是独立
    操作，因此一个 probe 永远不会隐式修改 M/F 配置。
    """
    guard = fine_boundary + 1
    operations: List[Dict[str, Any]] = []

    def add(operation_type: str, medium_before: int, medium_after: int, fine_before: int, fine_after: int,
            probe_kind: str = "", evidence: str = "", reason: str = "replayed_frozen_protocol") -> None:
        """集中填写所有操作的共同字段，确保后续审计无需猜测默认值。"""
        operations.append({
            "scenario": scenario,
            "operation_index": len(operations),
            "operation_type": operation_type,
            "M_before": medium_before,
            "M_after": medium_after,
            "F_before": fine_before,
            "F_after": fine_after,
            "probe_kind": probe_kind,
            "reachable": True,
            "formal_gate": operation_type != "initial_state",
            "legacy_evidence_key": evidence,
            "reason": reason,
            "counted_operation": operation_type != "initial_state",
        })

    # 起始态只描述控制器开始位置；45/36/36 的验收计数明确排除它。
    add("initial_state", 0, 0, 0, 0, reason="frozen_controller_initial_state")
    for medium in range(boundary + 1):
        scan = unique_probe(rows, scenario, "coarse_scan", medium, 0)
        repeat = unique_probe(rows, scenario, "coarse_repeat", medium, 0)
        add("coarse_probe_a", medium, medium, 0, 0, "coarse_probe_a", probe_evidence_key(scenario, int(scan["probe_index"])))
        add("coarse_probe_b", medium, medium, 0, 0, "coarse_probe_b", probe_evidence_key(scenario, int(repeat["probe_index"])))
        if medium < boundary:
            add("coarse_increment", medium, medium + 1, 0, 0)

    # 两次回退连续发生，协议在其间没有 comparison probe。
    add("coarse_backoff_step_1", boundary, boundary - 1, 0, 0)
    add("coarse_backoff_step_2", boundary - 1, fine_base, 0, 0)
    for fine in range(fine_boundary + 1):
        scan = unique_probe(rows, scenario, f"fine_m{fine_base}_scan", fine_base, fine)
        add("fine_probe", fine_base, fine_base, fine, fine, "fine_probe", probe_evidence_key(scenario, int(scan["probe_index"])))
        if fine < fine_boundary:
            add("fine_increment", fine_base, fine_base, fine, fine + 1)

    # fine boundary 不是 stable-high，仍必须以独立更新进入 boundary + 1 保护码。
    add("fine_increment", fine_base, fine_base, fine_boundary, guard, reason="frozen_guard_code_update")
    guard_probe = unique_probe(rows, scenario, f"fine_m{fine_base}_scan", fine_base, guard)
    hold_probe = unique_probe(rows, scenario, f"fine_m{fine_base}_repeat", fine_base, guard)
    add("guard_probe", fine_base, fine_base, guard, guard, "guard_probe", probe_evidence_key(scenario, int(guard_probe["probe_index"])))
    add("lock_hold_probe", fine_base, fine_base, guard, guard, "lock_hold_probe", probe_evidence_key(scenario, int(hold_probe["probe_index"])))
    return operations


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
    operations = build_operations(rows, scenario, boundary, fine_base, fine_boundary)
    reachable_keys = {operation["legacy_evidence_key"] for operation in operations if operation["legacy_evidence_key"]}
    marked = []
    for row in rows:
        evidence = probe_evidence_key(scenario, int(row["probe_index"]))
        reachable = evidence in reachable_keys
        marked.append({
            **row,
            "reachable": reachable,
            "selected_path": reachable,
            "counterfactual_only": not reachable,
            "counterfactual_reason": "" if reachable else "not_in_replayed_operation_sequence",
            "formal_gate": reachable,
        })
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
        "operations": operations,
        "probes": marked,
    }


def build_transitions(transitions: Sequence[Mapping[str, str]], replays: Mapping[str, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """将旧转换证据附着到已重放的更新操作，并保留全部未映射历史分支。

    可达性来自 ``operations``，而非 ``transition_type``。旧行只有在场景、前后
    M/F 和操作上下文均唯一一致时才能成为证据；例如遗留 M10->M9 虽然标签看似
    backoff，却不在真实状态机中，因此始终是反事实记录。
    """
    legacy_context = {
        "coarse_increment": "coarse_increment",
        "coarse_backoff_step_1": "coarse_backoff_step",
        "coarse_backoff_step_2": "coarse_backoff_step",
        "fine_increment": "fine_increment",
    }
    by_identity: Dict[tuple, List[Mapping[str, str]]] = {}
    for row in transitions:
        key = (row["scenario"], row["transition_type"], int(row["old_M"]), int(row["new_M"]), int(row["old_F"]), int(row["new_F"]))
        by_identity.setdefault(key, []).append(row)

    replayed_rows: List[Dict[str, Any]] = []
    consumed_keys = set()
    for item in replays.values():
        for operation in item["operations"]:
            context = legacy_context.get(operation["operation_type"])
            if context is None:
                continue
            key = (operation["scenario"], context, operation["M_before"], operation["M_after"], operation["F_before"], operation["F_after"])
            matches = by_identity.get(key, [])
            if len(matches) > 1:
                raise ValueError(f"{operation['scenario']}: 转换证据不唯一: {key}")
            evidence = transition_evidence_key(matches[0]) if matches else ""
            status = matches[0]["status"] if matches else "REQUIRES_EXACT_PATH_HSPICE"
            reason = matches[0]["reason"] if matches else "no_legacy_row_with_matching_complete_transition_identity"
            operation["legacy_evidence_key"] = evidence
            operation["legacy_evidence_status"] = status
            operation["legacy_evidence_reason"] = reason
            if evidence:
                consumed_keys.add(evidence)
            replayed_rows.append({
                **operation,
                "transition_index": matches[0]["transition_index"] if matches else "",
                "status": status,
                "counterfactual_only": False,
                "counterfactual_reason": "",
            })

    # 未被真实操作消耗的旧行仍输出，以便审计旧 M10 与未选 fine 分支。
    for row in transitions:
        evidence = transition_evidence_key(row)
        if evidence in consumed_keys:
            continue
        replayed_rows.append({
            **row,
            "operation_index": "",
            "operation_type": "legacy_unmapped_transition",
            "M_before": int(row["old_M"]), "M_after": int(row["new_M"]),
            "F_before": int(row["old_F"]), "F_after": int(row["new_F"]),
            "probe_kind": "", "reachable": False, "formal_gate": False,
            "legacy_evidence_key": evidence, "legacy_evidence_status": row["status"],
            "legacy_evidence_reason": row["reason"], "reason": "legacy_transition_not_in_replayed_operation_sequence",
            "counted_operation": False, "transition_index": row["transition_index"],
            "counterfactual_only": True, "counterfactual_reason": "not_in_replayed_operation_sequence",
        })
    return replayed_rows


def phase_contract(data: Mapping[str, Mapping[str, Any]]) -> None:
    """按 Phase 1 操作清单生成完整、确定性的精确路径合同。

    合同中的 ``operation`` 表示调度类别，``operation_type`` 保留协议语义；
    因而所有配置变化都明确是 ``config_update``，不会被 compare 操作隐式携带。
    """
    expected_counts = {"0p80_normal": 45, "0p95_normal": 36, "1p10_normal": 36}
    all_rows: List[Dict[str, Any]] = []
    summary_rows: Dict[str, Any] = {}
    for scenario, item in data.items():
        operations: List[Dict[str, Any]] = []
        for source in item["operations"]:
            operation_type = source["operation_type"]
            is_initial = operation_type == "initial_state"
            is_update = operation_type in {"coarse_increment", "coarse_backoff_step_1", "coarse_backoff_step_2", "fine_increment"}
            is_probe = not is_initial and not is_update
            is_lock_hold = operation_type == "lock_hold_probe"
            operation = {
                **source,
                "operation": "initial_state" if is_initial else "config_update" if is_update else "lock_hold_probe" if is_lock_hold else "compare_probe",
                "phase": operation_type,
                "probe_index": "",
                "changed_thermometer_bits": 0,
                "reset_asserted": False,
                "reset_release_timing": "",
                "sclk_low": False,
                "configuration_edge_s": 0.0,
                "settle_s": 0.0,
                "configuration_ck_edge_count": 0,
                "code_constant_during_probe": False,
                "intended_active_ck_edge_count": 0,
                "q_sample_count": 0,
                "q_samples_same_rail": False,
                "recovery_guard_s": 0.0,
            }
            if is_update:
                operation.update({
                    "changed_thermometer_bits": abs(source["M_after"] - source["M_before"]) + abs(source["F_after"] - source["F_before"]),
                    "reset_asserted": True,
                    "sclk_low": True,
                    "configuration_edge_s": 10e-12,
                    "settle_s": 1.5e-9,
                })
            elif is_probe:
                operation.update({
                    "probe_index": int(source["legacy_evidence_key"].rsplit(":", 1)[1]),
                    "code_constant_during_probe": True,
                    "reset_release_timing": "frozen_reset_arm",
                    "intended_active_ck_edge_count": 1,
                    "q_sample_count": 2,
                    "q_samples_same_rail": True,
                    "recovery_guard_s": 2.7e-9,
                })
            operations.append(operation)
            if not is_initial:
                all_rows.append(operation)

        executable = [row for row in operations if row["counted_operation"]]
        if len(executable) != expected_counts[scenario]:
            raise AssertionError(f"{scenario}: 操作数 {len(executable)} != 计划值 {expected_counts[scenario]}")
        if any(row["operation"] == "config_update" and row["changed_thermometer_bits"] != 1 for row in executable):
            raise AssertionError(f"{scenario}: 存在非单比特配置更新")
        if any(row["operation"] == "compare_probe" and (row["M_before"] != row["M_after"] or row["F_before"] != row["F_after"]) for row in executable):
            raise AssertionError(f"{scenario}: compare 操作改变了配置")
        contract = {
            "schema_version": 2,
            "scenario": scenario,
            "vdd_v": item["vdd_v"],
            "operations": operations,
            "coarse_boundary": item["coarse_boundary"],
            "selected_medium_base": item["primary_medium_base"],
            "fine_boundary": item["fine_boundary"],
            "guard_code": item["guard_code"],
            "functional_guard_s": 2.7e-9,
            "initial_state_excluded_from_operation_count": True,
            "expected_executable_operation_count": expected_counts[scenario],
            "hspice_scenario_budget": 3,
            "hspice_run_count": 0,
        }
        write_json(OUT / f"exact_path_{VOLTAGE_NAMES[scenario]}_contract.json", contract)
        summary_rows[VOLTAGE_NAMES[scenario]] = {
            "scenario": scenario,
            "executable_operation_count": len(executable),
            "compare_operation_count": sum(row["operation"] == "compare_probe" for row in executable),
            "config_update_count": sum(row["operation"] == "config_update" for row in executable),
            "hspice_run_count": 0,
        }
    write_csv(OUT / "exact_path_operations.csv", list(all_rows[0]), all_rows)
    write_json(OUT / "exact_path_contract_summary.json", {"schema_version": 2, "scenarios": summary_rows, "hspice_scenario_budget": 3, "hspice_run_count": 0})
    write_json(OUT / "exact_path_contract.json", {"schema_version": 2, "scenarios": [VOLTAGE_NAMES[s] for s in SCENARIOS], "hspice_run_count": 0, "hspice_scenario_budget": 3, "configuration_update_settle_s": 1.5e-9, "configuration_update_edge_s": 10e-12, "configuration_update_sclk_edges": 0})


def phase_publish(data: Mapping[str, Mapping[str, Any]]) -> None:
    """从同一份结构化重放数据生成汇总，避免报告手写计数漂移。"""
    failures = json.loads((OUT / "reachable_failure_audit.json").read_text(encoding="utf-8"))
    recovery = json.loads((OUT / "reachable_recovery_audit.json").read_text(encoding="utf-8"))
    per_voltage = failures["per_voltage"]
    old_probe_count = {VOLTAGE_NAMES[s]: len(data[s]["probes"]) for s in SCENARIOS}
    reachable_probe_count = {VOLTAGE_NAMES[s]: data[s]["reachable_probe_count"] for s in SCENARIOS}
    counterfactual_probe_count = {voltage: old_probe_count[voltage] - reachable_probe_count[voltage] for voltage in old_probe_count}
    legacy_failure_count = {voltage: per_voltage[voltage]["all_prerendered_failure_count"] for voltage in per_voltage}
    reachable_failure_count = {voltage: per_voltage[voltage]["formal_failure_count"] for voltage in per_voltage}
    counterfactual_failure_count = {voltage: per_voltage[voltage]["counterfactual_probe_failure_count"] for voltage in per_voltage}
    replay_consistent = failures["replay_consistency"]
    summary = {
        "study": "ftc_reachable_path_acceptance",
        "baseline_commit": json.loads((OUT / "frozen_evidence.json").read_text(encoding="utf-8"))["baseline_commit"],
        "legacy_decision": "NO-GO" if sum(legacy_failure_count.values()) else "GO",
        "legacy_reason": "historical_prerendered_failure_exists" if sum(legacy_failure_count.values()) else "none",
        "reachability_semantics_decision": "GO" if replay_consistent and not sum(reachable_failure_count.values()) else "NO-GO",
        "formal_exact_path_decision": "PENDING_HSPICE",
        "old_prerendered_probe_count_by_vdd": old_probe_count,
        "reachable_probe_count_by_vdd": reachable_probe_count,
        "counterfactual_probe_count_by_vdd": counterfactual_probe_count,
        "legacy_failure_count_by_vdd": legacy_failure_count,
        "reachable_failure_count_by_vdd": reachable_failure_count,
        "counterfactual_failure_count_by_vdd": counterfactual_failure_count,
        "coarse_boundary_by_vdd": {VOLTAGE_NAMES[s]: data[s]["coarse_boundary"] for s in SCENARIOS},
        "selected_medium_base_by_vdd": {VOLTAGE_NAMES[s]: data[s]["primary_medium_base"] for s in SCENARIOS},
        "fine_boundary_by_vdd": {VOLTAGE_NAMES[s]: data[s]["fine_boundary"] for s in SCENARIOS},
        "guard_code_by_vdd": {VOLTAGE_NAMES[s]: data[s]["guard_code"] for s in SCENARIOS},
        "reachable_worst_return_probe": recovery["worst_probe_index"],
        "reachable_worst_return_node": recovery["worst_node"],
        "reachable_worst_return_settle_s": recovery["worst_return_fall_s"],
        "full_diagnostic_space_guard_s": 2.8e-9,
        "reachable_functional_guard_s": 2.7e-9,
        "new_exact_path_hspice_scenarios": 0,
        "all_old_rerun_counters": {"upstream_static_84": 0, "legacy_dynamic": 0, "legacy_recovery_diagnostic": 0},
        "final_dynamic_protocol_decision": "PENDING_HSPICE",
    }
    write_json(OUT / "summary.json", summary)
    (ROOT / "delay_chain" / "ftc" / "reports").mkdir(parents=True, exist_ok=True)
    (ROOT / "delay_chain" / "ftc" / "reports" / "FTC_REACHABLE_PATH_ACCEPTANCE.md").write_text(
        "# FTC 可达路径验收\n\n"
        f"零仿真重放记录历史预渲染失败 {sum(legacy_failure_count.values())} 项，其中正式可达失败 {sum(reachable_failure_count.values())} 项。"
        f"三电压真实探测数为 {reachable_probe_count['0p80']}、{reachable_probe_count['0p95']}、{reachable_probe_count['1p10']}。"
        f"可达恢复最坏探测为 0.80 V probe {recovery['worst_probe_index']} 的 {recovery['worst_node']}，"
        "加入 200 ps 后量化 guard 为 2.7 ns。正式三电压 HSPICE 尚未运行，协议结论保持待验收。\n",
        encoding="utf-8",
    )


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
    """生成 Phase 1 的状态机操作与旧证据映射，不调用任何模拟器。"""
    probes = read_csv(SOURCE / "acceptance_probe_results.csv")
    transitions = read_csv(SOURCE / "acceptance_transition_audit.csv")
    data = {scenario: replay(scenario_rows(probes, scenario), scenario) for scenario in SCENARIOS}
    all_probe_rows = [row for item in data.values() for row in item["probes"]]
    transition_rows = build_transitions(transitions, data)
    operation_rows = [operation for item in data.values() for operation in item["operations"]]
    fields = ["scenario", "probe_index", "medium_code", "fine_code", "protocol_phase", "q_state", "reachable", "selected_path", "counterfactual_only", "counterfactual_reason", "formal_gate", "electrical_valid", "reason"]
    write_csv(OUT / "probe_reachability.csv", fields, all_probe_rows)
    operation_fields = ["scenario", "operation_index", "operation_type", "M_before", "M_after", "F_before", "F_after", "probe_kind", "reachable", "formal_gate", "legacy_evidence_key", "legacy_evidence_status", "legacy_evidence_reason", "reason", "counted_operation"]
    write_csv(OUT / "replayed_operations.csv", operation_fields, operation_rows)
    # 此 CSV 同时保留真实重放更新与未映射的历史转换，便于证明旧分支不能门控。
    transition_fields = operation_fields + ["transition_index", "counterfactual_only", "counterfactual_reason"]
    write_csv(OUT / "transition_reachability.csv", transition_fields, transition_rows)
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
    per_voltage: Dict[str, Dict[str, Any]] = {}
    for scenario in SCENARIOS:
        scenario_failures = [row for row in failures if row["scenario"] == scenario]
        scenario_reachable = [row for row in reachable_failures if row["scenario"] == scenario]
        scenario_ops = [op for op in data[scenario]["operations"] if op["counted_operation"] and op["operation_type"] in {"coarse_increment", "coarse_backoff_step_1", "coarse_backoff_step_2", "fine_increment"}]
        config_failures = [op for op in scenario_ops if op.get("legacy_evidence_status") not in ("PASS", "REQUIRES_EXACT_PATH_HSPICE", "")]
        unverified_updates = [op for op in scenario_ops if op.get("legacy_evidence_status") == "REQUIRES_EXACT_PATH_HSPICE"]
        per_voltage[VOLTAGE_NAMES[scenario]] = {
            "all_prerendered_failure_count": len(scenario_failures),
            "reachable_probe_failure_count": len(scenario_reachable),
            "counterfactual_probe_failure_count": len(scenario_failures) - len(scenario_reachable),
            "reachable_config_update_failure_count": len(config_failures),
            "reachable_config_update_unverified_count": len(unverified_updates),
            "formal_failure_count": len(scenario_reachable) + len(config_failures),
            "reachable_failures": scenario_reachable + [{"operation_type": op["operation_type"], "M_before": op["M_before"], "M_after": op["M_after"], "F_before": op["F_before"], "F_after": op["F_after"], "failure_reason": op.get("legacy_evidence_reason", "")} for op in config_failures],
        }
    replay_consistency = all(
        item["reachable_probe_count"] == sum(op["operation_type"] in {"coarse_probe_a", "coarse_probe_b", "fine_probe", "guard_probe", "lock_hold_probe"} for op in item["operations"])
        and all(op["formal_gate"] for op in item["operations"] if op["counted_operation"])
        for item in data.values()
    )
    write_json(OUT / "reachable_failure_audit.json", {
        "all_prerendered_electrical_failure_count": len(failures),
        "reachable_electrical_failure_count": len(reachable_failures),
        "reachable_failures": reachable_failures,
        "formal_reasons": sorted(set(r["failure_reason"] for r in reachable_failures)),
        "decision": "GO" if not reachable_failures else "NO-GO",
        "replay_consistency": replay_consistency,
        "per_voltage": per_voltage,
        "legacy_report_count_mismatch": {"report_claimed": len(failures), "json_operation_failure_count": len(failures), "json_terminal_failure_count": 0},
    })

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
    reachable_080_count = sum(1 for scenario, _ in reach_keys if scenario == "0p80_normal")
    write_json(OUT / "reachable_recovery_audit.json", {"scenario": "0p80_normal", "reachable_probe_count": reachable_080_count, "worst_return_fall_s": worst[0], "worst_probe_index": worst[1], "worst_node": worst[2], "safety_tail_s": 0.2e-9, "source": "recovery_diagnostic_results.csv"})
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
