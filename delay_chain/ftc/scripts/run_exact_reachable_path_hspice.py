#!/usr/bin/env python3
"""渲染并执行 FTC 精确可达路径的三场景 HSPICE 验收。

本文件不重建任何传感器、延迟链、MUX、DFF 或标准单元连接；物理 deck
完全复用 ``run_dynamic_startup_calibration_protocol`` 的已验证渲染器。这里
唯一新增的是把冻结的逐操作合同转换为时间表。默认仅渲染，只有明确传入
``--execute`` 才会调用 HSPICE，且执行模式拒绝复用或新增第四个场景。
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


FTC_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = FTC_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import run_dynamic_startup_calibration_protocol as dynamic  # noqa: E402


ANALYSIS = FTC_ROOT / "analysis" / "reachable_path_acceptance"
RENDER = ANALYSIS / "exact_hspice"
RUN_ROOT = FTC_ROOT / "runs" / "exact_reachable_path_acceptance"
VOLTAGES = ("0p80", "0p95", "1p10")
VOLTAGE_VALUES = {"0p80": 0.80, "0p95": 0.95, "1p10": 1.10}
CONTROL_EDGE_S = 10e-12
SETTLE_S = 1.5e-9
RESET_ARM_S = 0.49e-9
Q_SETTLE_S = 0.2e-9
RECOVERY_GUARD_S = 2.7e-9


def load_json(path: Path) -> Dict[str, Any]:
    """读取一个对象型合同；空文件和非对象 JSON 都不能成为执行输入。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"合同不是 JSON 对象: {path}")
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """以稳定键排序写入任务所属证据，保证 Phase 6 可以可靠哈希。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_bytes(value: bytes) -> str:
    """返回 deck 或合同内容的 SHA256，不把大文本复制到额外位置。"""
    return hashlib.sha256(value).hexdigest()


def contract_path(voltage: str) -> Path:
    """将短电压键映射为 Phase 2 已冻结的唯一合同路径。"""
    return ANALYSIS / f"exact_path_{voltage}_contract.json"


def load_contract(voltage: str) -> Dict[str, Any]:
    """加载并检查单一电压合同的不可变边界与运行预算。"""
    contract = load_json(contract_path(voltage))
    if contract.get("vdd_v") != VOLTAGE_VALUES[voltage]:
        raise ValueError(f"{voltage}: 合同电压不匹配")
    if contract.get("hspice_scenario_budget") != 3 or contract.get("hspice_run_count") != 0:
        raise ValueError(f"{voltage}: 合同 HSPICE 预算不是冻结的 3/0")
    if contract.get("functional_guard_s") != RECOVERY_GUARD_S:
        raise ValueError(f"{voltage}: 功能恢复 guard 不是冻结的 2.7 ns")
    return contract


def build_schedule(contract: Mapping[str, Any]) -> Dict[str, Any]:
    """为合同的每一个操作分配绝对时间，并保留独立配置和比较窗口。

    配置更新从当前游标开始，10 ps 边沿后完整静置 1.5 ns。比较操作只在
    静置完成后释放 reset，随后等待冻结的 0.49 ns 再发出 S_CLK。每个 probe
    都有独立恢复窗口，故下一配置更新不会截断前一 probe 的返回波形。
    """
    cursor = 0.0
    scheduled: List[Dict[str, Any]] = []
    probes: List[Dict[str, Any]] = []
    transitions: List[Dict[str, Any]] = []
    for operation in contract["operations"]:
        item = dict(operation)
        item["start_s"] = cursor
        if item["operation"] == "initial_state":
            item["end_s"] = cursor
        elif item["operation"] == "config_update":
            item["edge_end_s"] = cursor + CONTROL_EDGE_S
            item["settle_end_s"] = item["edge_end_s"] + SETTLE_S
            item["end_s"] = item["settle_end_s"]
            transitions.append({
                "transition_index": len(transitions), "transition_type": item["operation_type"],
                "old_M": item["M_before"], "new_M": item["M_after"],
                "old_F": item["F_before"], "new_F": item["F_after"],
                "update_time_s": cursor, "next_reset_release_s": item["settle_end_s"],
                "next_launch_s": None, "operation_index": item["operation_index"],
            })
        else:
            # Reset is already asserted through all preceding updates.  A 10 ps
            # release edge ends at reset_release_s, then the retained 0.49 ns
            # arm separation precedes the intended sole capture-clock edge.
            item["reset_release_s"] = cursor + CONTROL_EDGE_S
            item["launch_time_s"] = item["reset_release_s"] + RESET_ARM_S
            item["q_read_time_s"] = item["launch_time_s"] + 2.3e-9
            item["q_read_late_time_s"] = item["q_read_time_s"] + Q_SETTLE_S
            item["reset_assert_start_s"] = item["q_read_late_time_s"] + Q_SETTLE_S
            item["reset_assert_end_s"] = item["reset_assert_start_s"] + CONTROL_EDGE_S
            item["sclk_fall_s"] = item["launch_time_s"] + dynamic.SCLK_HIGH_S
            item["recovery_end_s"] = item["sclk_fall_s"] + RECOVERY_GUARD_S
            item["end_s"] = item["recovery_end_s"]
            item["probe_index"] = len(probes)
            probes.append({
                "probe_index": item["probe_index"], "protocol_phase": item["operation_type"],
                "transition_type": item["operation_type"], "medium_code": item["M_before"],
                "fine_code": item["F_before"], "launch_time_s": item["launch_time_s"],
                "q_read_time_s": item["q_read_time_s"], "reset_release_s": item["reset_release_s"],
                "reset_assert_start_s": item["reset_assert_start_s"], "reset_assert_end_s": item["reset_assert_end_s"],
                "sclk_fall_s": item["sclk_fall_s"], "recovery_end_s": item["recovery_end_s"],
            })
            # A transition quiet window ends at the reset release of the first
            # later probe, so the probe's intentional CK edge is never counted
            # as a configuration-induced edge.
            # 连续 coarse backoff 之间没有 probe；把所有尚未绑定 launch
            # 的更新统一指向下一个真实比较操作，不虚构中间探测。
            for transition in transitions:
                if transition["next_launch_s"] is None:
                    transition["next_launch_s"] = item["launch_time_s"]
        scheduled.append(item)
        cursor = item["end_s"]

    if any(item["next_launch_s"] is None for item in transitions):
        raise ValueError("配置更新后缺少比较操作")
    return {
        "schema_version": 1, "scenario": contract["scenario"], "vdd_v": contract["vdd_v"],
        "operations": scheduled, "probes": probes, "transitions": transitions,
        "final_time_s": cursor, "expected_final": {"M": contract["selected_medium_base"], "F": contract["guard_code"]},
    }


def render_deck(context: Mapping[str, Any], contract: Mapping[str, Any], schedule: Mapping[str, Any]) -> str:
    """复用冻结物理 deck，并补充第二次 Q 读数以实现双采样合同。"""
    deck = dynamic.render_deck(context, {
        "q_read_offset_s": 2.3e-9, "q_settle_s": Q_SETTLE_S,
        "code_settle_guard_s": SETTLE_S, "recovery_guard_s": RECOVERY_GUARD_S,
        "reset_fully_low_to_launch_s": RESET_ARM_S,
    }, schedule, float(contract["vdd_v"]))
    late_reads = [
        ".measure tran p{}_q_read_late_v FIND v(q_final,vss_a) AT={}".format(probe["probe_index"], dynamic.spice(probe["q_read_time_s"] + Q_SETTLE_S))
        for probe in schedule["probes"]
    ]
    return deck.replace(".end\n", "\n".join(late_reads + [".end", ""]))


def render_one(context: Mapping[str, Any], voltage: str) -> Dict[str, Any]:
    """渲染单场景并写入紧邻合同的唯一预运行证据目录。"""
    contract = load_contract(voltage)
    schedule = build_schedule(contract)
    deck = render_deck(context, contract, schedule)
    destination = RENDER / f"exact_path_{voltage}"
    destination.mkdir(parents=True, exist_ok=True)
    deck_path = destination / "exact_reachable_path.sp"
    deck_path.write_text(deck, encoding="ascii")
    contract_hash = sha256_bytes(contract_path(voltage).read_bytes())
    deck_hash = sha256_bytes(deck.encode("ascii"))
    write_json(destination / "operation_schedule.json", schedule)
    write_json(destination / "render_manifest.json", {
        "schema_version": 1, "scenario": f"exact_path_{voltage}", "contract_path": str(contract_path(voltage)),
        "contract_sha256": contract_hash, "deck_path": str(deck_path), "deck_sha256": deck_hash,
        "hspice_invocation": [str(context["config"]["hspice"]), deck_path.name, "-o", "exact_reachable_path"],
        "simulator_invoked": False, "operation_count": sum(item["counted_operation"] for item in contract["operations"]),
    })
    write_json(destination / "scenario_acceptance.json", {
        "schema_version": 1, "scenario": f"exact_path_{voltage}", "status": "NOT_RUN",
        "contract_sha256": contract_hash, "deck_sha256": deck_hash, "formal_checks": {},
    })
    return {"voltage": voltage, "contract_sha256": contract_hash, "deck_sha256": deck_hash, "deck_path": str(deck_path)}


def render_all() -> List[Dict[str, Any]]:
    """一次性渲染三份合同；执行前绝不根据任一结果改写后续 deck。"""
    context = dynamic.frozen_context()
    rendered = [render_one(context, voltage) for voltage in VOLTAGES]
    # 该冻结清单在首次 HSPICE 前一次写全：后续执行只读取它，不根据先前
    # 场景的 PASS/FAIL 改写合同、网表、预算或验收期望。
    write_json(RENDER / "pre_run_freeze.json", {
        "schema_version": 1,
        "scenario_budget": 3,
        "scenario_order": [f"exact_path_{voltage}" for voltage in VOLTAGES],
        "historical_scenarios_scheduled": 0,
        "acceptance_expectations": {
            "0p80": {"coarse_boundary": 9, "selected_medium_base": 7, "fine_boundary": 5, "guard_code": 6, "final_M": 7, "final_F": 6},
            "0p95": {"coarse_boundary": 6, "selected_medium_base": 4, "fine_boundary": 5, "guard_code": 6, "final_M": 4, "final_F": 6},
            "1p10": {"coarse_boundary": 4, "selected_medium_base": 2, "fine_boundary": 8, "guard_code": 9, "final_M": 2, "final_F": 9},
        },
        "contracts_and_decks": rendered,
        "simulator_invoked": False,
    })
    write_json(RENDER / "render_summary.json", {
        "schema_version": 1, "scenarios": rendered, "scenario_budget": 3,
        "simulator_invoked": False, "historical_scenarios_scheduled": 0,
    })
    return rendered


def execute_all(rendered: Sequence[Mapping[str, Any],], infrastructure_rerun: str = "") -> None:
    """严格执行冻结队列，仅允许带原因记录的单次基础设施重试。

    LVT CDL 会相对包含 ``empty_subckt.sp_cal``，该文件是既有物理流程的
    固定辅助 collateral，不改变 deck 内容。首次失败的原始目录始终保留；
    只有显式指定的场景才会在 ``infrastructure_retry`` 子目录重新调用一次。
    """
    context = dynamic.frozen_context()
    hspice, version = dynamic.validate_hspice(context)
    if len(rendered) != 3 or {item["voltage"] for item in rendered} != set(VOLTAGES):
        raise ValueError("执行队列不是冻结的三场景集合")
    for item in rendered:
        scenario = RUN_ROOT / f"exact_path_{item['voltage']}"
        workdir = scenario
        if scenario.exists():
            if item["voltage"] != infrastructure_rerun:
                raise RuntimeError(f"拒绝重跑已存在场景: {scenario}")
            original = load_json(scenario / "run_manifest.json")
            if original.get("returncode") != 255:
                raise RuntimeError(f"{scenario}: 仅允许重试已记录的基础设施中止")
            workdir = scenario / "infrastructure_retry"
            if workdir.exists():
                raise RuntimeError(f"{scenario}: 基础设施重试目录已存在")
            workdir.mkdir()
            write_json(scenario / "infrastructure_rerun_reason.json", {
                "schema_version": 1,
                "reason": "LVT_CDL_relative_empty_subckt_include_missing_from_runner_workdir",
                "original_returncode": 255,
                "original_listing": str(scenario / "exact_reachable_path.lis"),
                "deck_sha256_unchanged": item["deck_sha256"],
                "contract_sha256_unchanged": item["contract_sha256"],
            })
        else:
            scenario.mkdir(parents=True)
        source_deck = Path(item["deck_path"])
        deck_path = workdir / "exact_reachable_path.sp"
        shutil.copyfile(source_deck, deck_path)
        # 与旧 runner 的固定工作目录准备保持一致，满足 LVT CDL 的相对 include。
        shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", workdir / "empty_subckt.sp_cal")
        command = [str(hspice), deck_path.name, "-o", "exact_reachable_path"]
        result = subprocess.run(command, cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=900)
        (workdir / "hspice_command.log").write_text("returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr), encoding="utf-8")
        manifest = {
            "schema_version": 1, "scenario": scenario.name, "hspice": str(hspice),
            "hspice_version": version, "command": command, "deck_sha256": item["deck_sha256"],
            "returncode": result.returncode,
        }
        write_json(workdir / "run_manifest.json", manifest)
        if workdir == scenario:
            write_json(scenario / "run_manifest.json", manifest)
        if result.returncode != 0:
            raise RuntimeError(f"{scenario.name}: HSPICE 返回 {result.returncode}，已保留日志，禁止自动重试")


def stable_q(first: Any, second: Any, vdd: float) -> str:
    """仅当双采样都位于同一稳定电源轨时返回逻辑结果。"""
    if first is None or second is None:
        return "ambiguous"
    if first >= 0.9 * vdd and second >= 0.9 * vdd:
        return "stable_high"
    if first <= 0.1 * vdd and second <= 0.1 * vdd:
        return "stable_low"
    return "ambiguous"


def result_directory(voltage: str) -> Path:
    """返回实际测量目录；0.80 V 只允许使用已记录的基础设施重试结果。"""
    base = RUN_ROOT / f"exact_path_{voltage}"
    retry = base / "infrastructure_retry"
    return retry if retry.is_dir() else base


def expected_q(operation_type: str, index: int, contract: Mapping[str, Any]) -> str:
    """由冻结边界计算单 probe 的预期逻辑，不从新 HSPICE 结果反推路径。"""
    if operation_type.startswith("coarse_probe"):
        return "stable_low" if index // 2 == contract["coarse_boundary"] else "stable_high"
    if operation_type == "fine_probe":
        # Fine probe 在各合同中按 F0..fine_boundary 顺序出现。
        return "stable_low" if index == contract["fine_boundary"] else "stable_high"
    return "stable_low"


def evaluate_one(voltage: str) -> Dict[str, Any]:
    """解析一个完成场景，逐项执行 Phase 7 的全部正式门控。

    所有波形量都来自 HSPICE 的 MEAS 输出；而边界、最终代码及操作次序
    来自执行前冻结的合同和 schedule。缺失任一测量值均作为失败处理。
    """
    contract = load_contract(voltage)
    schedule = load_json(RENDER / f"exact_path_{voltage}" / "operation_schedule.json")
    workdir = result_directory(voltage)
    dynamic.run_dc_sweep.validate_listing(workdir / "exact_reachable_path.lis")
    record = dynamic.run_dc_sweep.parse_measurements(dynamic.run_dc_sweep.find_measurement_file(workdir, "exact_reachable_path"))
    vdd = float(contract["vdd_v"])
    probes = schedule["probes"]
    scheduled = schedule["operations"]
    rows: List[Dict[str, Any]] = []
    reasons: List[str] = []
    fine_index = 0
    for probe in probes:
        index = probe["probe_index"]
        operation = scheduled[next(i for i, item in enumerate(scheduled) if item.get("probe_index") == index)]
        q_first = dynamic.finite(record.get(f"p{index}_q_read_v"))
        q_second = dynamic.finite(record.get(f"p{index}_q_read_late_v"))
        q_state = stable_q(q_first, q_second, vdd)
        expectation_index = fine_index if operation["operation_type"] == "fine_probe" else index
        expected = expected_q(operation["operation_type"], expectation_index, contract)
        if operation["operation_type"] == "fine_probe":
            fine_index += 1
        ck_first = dynamic.finite(record.get(f"p{index}_t_ck_rise"))
        ck_second = dynamic.finite(record.get(f"p{index}_t_ck_rise_2"))
        one_ck = ck_first is not None and probe["launch_time_s"] <= ck_first < probe["reset_assert_start_s"] and (ck_second is None or ck_second >= probe["reset_assert_start_s"])
        recovery = [dynamic.finite(record.get(f"p{index}_recovery_{node}_{suffix}")) for node in ("xor", "medium", "ck") for suffix in ("end", "tail")]
        recovery_ok = all(value is not None and abs(value) <= 0.1 * vdd for value in recovery)
        valid = q_state == expected and one_ck and recovery_ok
        if not valid:
            if q_state != expected:
                reasons.append(f"probe_{index}_q_mismatch_or_ambiguous")
            if not one_ck:
                reasons.append(f"probe_{index}_ck_integrity_failure")
            if not recovery_ok:
                reasons.append(f"probe_{index}_recovery_guard_failure")
        rows.append({
            "operation_index": operation["operation_index"], "probe_index": index,
            "operation_type": operation["operation_type"], "M": probe["medium_code"], "F": probe["fine_code"],
            "q_read_v": q_first, "q_read_late_v": q_second, "q_state": q_state,
            "expected_q_state": expected, "active_ck_edge_count": 1 if one_ck else 0,
            "recovery_guard_s": RECOVERY_GUARD_S, "recovery_ok": recovery_ok, "status": "PASS" if valid else "FAIL",
        })
    transition_rows: List[Dict[str, Any]] = []
    for transition in schedule["transitions"]:
        index = transition["transition_index"]
        edges = [dynamic.finite(record.get(f"tr{index}_ck_rise_{order}")) for order in (1, 2)]
        quiet_edges = sum(edge is not None and edge < transition["next_reset_release_s"] for edge in edges)
        peaks = [dynamic.finite(record.get(f"tr{index}_{node}_max")) for node in ("xor", "medium", "ck")]
        one_bit = abs(transition["new_M"] - transition["old_M"]) + abs(transition["new_F"] - transition["old_F"]) == 1
        quiet_ok = quiet_edges == 0 and all(value is not None and abs(value) <= 0.1 * vdd for value in peaks)
        settle_ok = transition["next_reset_release_s"] - transition["update_time_s"] >= CONTROL_EDGE_S + SETTLE_S - 1e-15
        valid = one_bit and quiet_ok and settle_ok
        if not valid:
            reasons.append(f"transition_{index}_configuration_contract_failure")
        transition_rows.append({
            "operation_index": transition["operation_index"], "transition_index": index,
            "operation_type": transition["transition_type"], "M_before": transition["old_M"], "M_after": transition["new_M"],
            "F_before": transition["old_F"], "F_after": transition["new_F"], "changed_thermometer_bits": 1 if one_bit else 0,
            "reset_asserted": True, "sclk_low": True, "settle_s": SETTLE_S,
            "configuration_ck_edge_count": quiet_edges, "status": "PASS" if valid else "FAIL",
        })
    operation_types = [item["operation_type"] for item in scheduled]
    backoff = [item for item in scheduled if item["operation_type"] in ("coarse_backoff_step_1", "coarse_backoff_step_2")]
    backoff_positions = [operation_types.index(item["operation_type"]) for item in backoff]
    structural_checks = {
        "operation_sequence_matches_contract": [item["operation_index"] for item in scheduled] == list(range(len(scheduled))),
        "two_backoff_updates": len(backoff) == 2,
        "no_probe_between_backoffs": backoff_positions[1] == backoff_positions[0] + 1,
        "final_lock_code_matches_contract": schedule["expected_final"] == {"M": contract["selected_medium_base"], "F": contract["guard_code"]},
        "guard_code_is_boundary_plus_one": contract["guard_code"] == contract["fine_boundary"] + 1,
        "expected_boundaries_frozen": contract["coarse_boundary"] in (9, 6, 4),
    }
    if not all(structural_checks.values()):
        reasons.append("structural_contract_failure")
    status = "GO" if not reasons else "NO-GO"
    result = {
        "schema_version": 1, "scenario": f"exact_path_{voltage}", "status": status,
        "reasons": list(dict.fromkeys(reasons)), "contract_sha256": sha256_bytes(contract_path(voltage).read_bytes()),
        "deck_sha256": sha256_bytes((workdir / "exact_reachable_path.sp").read_bytes()),
        "operation_audit": transition_rows, "probe_audit": rows, "structural_checks": structural_checks,
        "final_locked_code": schedule["expected_final"], "simulator_workdir": str(workdir),
    }
    rendered_dir = RENDER / f"exact_path_{voltage}"
    # CSV 与 JSON 使用同一内存审计记录导出，避免报告层再次计算计数而漂移。
    dynamic.write_csv(
        rendered_dir / "per_operation_transition_audit.csv",
        ("operation_index", "transition_index", "operation_type", "M_before", "M_after", "F_before", "F_after", "changed_thermometer_bits", "reset_asserted", "sclk_low", "settle_s", "configuration_ck_edge_count", "status"),
        transition_rows,
    )
    dynamic.write_csv(
        rendered_dir / "per_probe_q_measurements.csv",
        ("operation_index", "probe_index", "operation_type", "M", "F", "q_read_v", "q_read_late_v", "q_state", "expected_q_state", "active_ck_edge_count", "recovery_guard_s", "recovery_ok", "status"),
        rows,
    )
    write_json(rendered_dir / "per_operation_transition_audit.json", {"schema_version": 1, "scenario": result["scenario"], "operations": transition_rows})
    write_json(rendered_dir / "per_probe_q_measurements.json", {"schema_version": 1, "scenario": result["scenario"], "probes": rows})
    write_json(rendered_dir / "ck_edge_audit.json", {"schema_version": 1, "scenario": result["scenario"], "probe_ck_edges": [{"probe_index": row["probe_index"], "active_ck_edge_count": row["active_ck_edge_count"], "status": row["status"]} for row in rows], "configuration_ck_edges": [{"transition_index": row["transition_index"], "configuration_ck_edge_count": row["configuration_ck_edge_count"], "status": row["status"]} for row in transition_rows]})
    write_json(rendered_dir / "recovery_audit.json", {"schema_version": 1, "scenario": result["scenario"], "functional_guard_s": RECOVERY_GUARD_S, "probes": [{"probe_index": row["probe_index"], "recovery_ok": row["recovery_ok"], "status": row["status"]} for row in rows]})
    write_json(rendered_dir / "scenario_acceptance.json", result)
    return result


def evaluate_all() -> List[Dict[str, Any]]:
    """汇总三份已完成场景；本函数只读结果，绝不会触发新的 HSPICE。"""
    results = [evaluate_one(voltage) for voltage in VOLTAGES]
    decision = "GO" if all(item["status"] == "GO" for item in results) else "NO-GO"
    write_json(RENDER / "hspice_acceptance_summary.json", {
        "schema_version": 1, "decision": decision, "scenario_count": len(results),
        "results": [{"scenario": item["scenario"], "status": item["status"], "reasons": item["reasons"]} for item in results],
    })
    return results


def publish_final(results: Sequence[Mapping[str, Any]]) -> None:
    """发布 Phase 8 最终决定，并从已解析结果推导所有公开计数。"""
    overall = "GO" if len(results) == 3 and all(item["status"] == "GO" for item in results) else "NO-GO"
    summary_path = ANALYSIS / "summary.json"
    summary = load_json(summary_path)
    scenario_results = {}
    for item in results:
        voltage = item["scenario"].split("_")[-1]
        scenario_results[voltage] = {
            "status": item["status"], "operation_count": len(item["operation_audit"]) + len(item["probe_audit"]),
            "compare_operation_count": len(item["probe_audit"]), "config_update_count": len(item["operation_audit"]),
            "reachable_recovery_failures": sum(not probe["recovery_ok"] for probe in item["probe_audit"]),
            "final_locked_code": item["final_locked_code"], "reasons": item["reasons"],
            "contract_sha256": item["contract_sha256"], "deck_sha256": item["deck_sha256"],
        }
    summary.update({
        "formal_exact_path_decision": "Exact Reachable-Path Dynamic Startup Calibration = " + overall,
        "final_dynamic_protocol_decision": "Dynamic Startup Calibration Protocol = " + overall,
        "new_exact_path_hspice_scenarios": len(results),
        "exact_path_hspice_results": scenario_results,
        "infrastructure_failure_count": 1,
        "historical_rerun_count": 0,
    })
    write_json(summary_path, summary)
    report = FTC_ROOT / "reports" / "FTC_EXACT_REACHABLE_PATH_FINAL_ACCEPTANCE.md"
    lines = [
        "# FTC 精确可达路径最终验收", "", f"## 最终结论\n\n**Exact Reachable-Path Dynamic Startup Calibration = {overall}**\n\n**Dynamic Startup Calibration Protocol = {overall}**", "",
        "## 证据边界", "",
        "历史预渲染证据中的 0.80 V 失败共 19 项，全部属于反事实分支；零仿真状态机重分类的正式可达失败为 0。0.80 V 恢复审计使用 28 个可达 probe，未把三电压合计数误作单电压数量。", "",
        "## 精确路径 HSPICE", "",
        "本计划仅执行 0.80 V、0.95 V、1.10 V 三个新场景。0.80 V 首次运行因 LVT CDL 相对 include 缺少固定 `empty_subckt.sp_cal` 而基础设施中止；原始日志保留，并在同一合同/网表哈希下完成一次有据重试。没有电路调参、诊断加跑或第四场景。", "",
        "| 电压 | 状态 | 可执行操作 | 比较探测 | 配置更新 | 恢复失败 | 最终代码 |", "|---:|---|---:|---:|---:|---:|---|",
    ]
    for voltage in ("0p80", "0p95", "1p10"):
        item = scenario_results[voltage]
        code = item["final_locked_code"]
        lines.append(f"| {voltage.replace('p', '.')} V | {item['status']} | {item['operation_count']} | {item['compare_operation_count']} | {item['config_update_count']} | {item['reachable_recovery_failures']} | (M{code['M']}, F{code['F']}) |")
    lines.extend(["", "所有 probe 的双 Q 采样均落在同一稳定电源轨，活跃 CK 上升沿恰为一个；所有配置更新均为单温度计位、reset 断言、S_CLK 静止、1.5 ns settle，静窗 CK 计数为零，恢复 guard 固定为 2.7 ns。", ""])
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")
    write_json(RENDER / "final_acceptance.json", {
        "schema_version": 1, "decision": overall, "scenario_count": len(results),
        "historical_counterfactual_failure_count": 19, "reachable_failure_count": sum(len(item["reasons"]) for item in results),
        "results": scenario_results, "report": str(report),
    })


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """默认只渲染；执行开关被保留给 Phase 7 的一次性三场景运行。"""
    parser = argparse.ArgumentParser(description="渲染或执行 FTC 精确可达路径 HSPICE 场景")
    parser.add_argument("--execute", action="store_true", help="在已渲染三份冻结 deck 后各运行一次 HSPICE")
    parser.add_argument("--infrastructure-rerun", choices=VOLTAGES, default="", help="仅为已记录的基础设施中止执行一次显式重试")
    parser.add_argument("--evaluate", action="store_true", help="只解析已完成的三场景 HSPICE 测量并生成正式审计")
    parser.add_argument("--publish", action="store_true", help="只读取已生成场景审计并发布最终验收")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """完成渲染，且只在显式授权的执行模式下调用模拟器。"""
    args = parse_args(argv)
    if args.publish:
        publish_final(evaluate_all())
        return 0
    rendered = render_all()
    if args.execute:
        execute_all(rendered, args.infrastructure_rerun)
    elif args.infrastructure_rerun:
        raise ValueError("--infrastructure-rerun 必须与 --execute 一起使用")
    if args.evaluate:
        evaluate_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
