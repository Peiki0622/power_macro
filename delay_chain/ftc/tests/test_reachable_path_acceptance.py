"""FTC 精确可达路径的零 HSPICE 合同测试。

这些测试只检查状态机重放、操作合同和离线审计产物；它们不会启动 HSPICE，
也不会把历史预渲染分支误当成正式验收路径。
"""

import csv
import json
import re
import unittest
from pathlib import Path


HERE = Path(__file__).resolve()
OUT = HERE.parents[1] / "analysis" / "reachable_path_acceptance"
SCRIPT = HERE.parents[1] / "scripts" / "run_reachable_path_acceptance.py"


def load(name):
    """读取一个已生成的 JSON 证据文件。"""
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def operations(voltage):
    """返回合同中的可执行操作，排除只描述起始态的元数据。"""
    return [row for row in load(f"exact_path_{voltage}_contract.json")["operations"] if row["counted_operation"]]


class ReachablePathAcceptanceTest(unittest.TestCase):
    """锁定 Phase 1-4 的状态机语义、合同计数和正式门控边界。"""

    def test_frozen_baseline_and_zero_hspice_budget(self):
        frozen = load("frozen_evidence.json")
        self.assertRegex(frozen["baseline_commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(frozen["legacy_acceptance_semantics"], "all_prerendered_rows_are_global_gates")
        self.assertEqual(frozen["hspice_scenarios_created"], 0)
        aggregate = load("exact_path_contract.json")
        self.assertLessEqual(aggregate["hspice_scenario_budget"], 3)
        self.assertEqual(aggregate["hspice_run_count"], 0)

    def test_replay_counts_and_boundaries(self):
        expected = {"0p80": (28, 9, 7, 5, 6), "0p95": (22, 6, 4, 5, 6), "1p10": (21, 4, 2, 8, 9)}
        for voltage, values in expected.items():
            data = load(f"reachable_replay_{voltage}.json")
            self.assertEqual((data["reachable_probe_count"], data["coarse_boundary"], data["primary_medium_base"], data["fine_boundary"], data["guard_code"]), values)

    def test_no_implicit_medium_or_fine_jump(self):
        for voltage in ("0p80", "0p95", "1p10"):
            rows = operations(voltage)
            for previous, current in zip(rows, rows[1:]):
                medium_jump = (previous["M_after"], current["M_before"]) != (current["M_before"], current["M_before"])
                fine_jump = (previous["F_after"], current["F_before"]) != (current["F_before"], current["F_before"])
                if medium_jump or fine_jump:
                    self.assertEqual(current["operation"], "config_update")

    def test_backoff_is_two_updates_without_intervening_probe(self):
        for voltage in ("0p80", "0p95", "1p10"):
            rows = operations(voltage)
            indexes = [index for index, row in enumerate(rows) if row["operation_type"] in ("coarse_backoff_step_1", "coarse_backoff_step_2")]
            self.assertEqual(len(indexes), 2)
            self.assertEqual(rows[indexes[0]]["operation_type"], "coarse_backoff_step_1")
            self.assertEqual(rows[indexes[1]]["operation_type"], "coarse_backoff_step_2")
            between = rows[indexes[0] + 1:indexes[1]]
            self.assertEqual(sum(row["operation"] in ("compare_probe", "lock_hold_probe") for row in between), 0)
            for index in indexes:
                row = rows[index]
                self.assertEqual(row["operation"], "config_update")
                self.assertEqual(row["changed_thermometer_bits"], 1)

    def test_selected_fine_updates_and_final_lock_hold(self):
        for voltage in ("0p80", "0p95", "1p10"):
            rows = operations(voltage)
            fine_updates = [row for row in rows if row["operation_type"] == "fine_increment"]
            self.assertTrue(fine_updates)
            self.assertTrue(all(row["reachable"] and row["formal_gate"] and row["changed_thermometer_bits"] == 1 for row in fine_updates))
            self.assertEqual(sum(row["operation"] == "lock_hold_probe" for row in rows), 1)
            self.assertEqual(sum(row["operation_type"] == "guard_probe" for row in rows), 1)

    def test_080_m9_to_m10_and_legacy_m10_to_m9_are_counterfactual(self):
        with (OUT / "transition_reachability.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        for old_m, new_m in (("9", "10"), ("10", "9")):
            row = next(row for row in rows if row["scenario"] == "0p80_normal" and row["M_before"] == old_m and row["M_after"] == new_m)
            self.assertEqual(row["reachable"], "False")
            self.assertEqual(row["formal_gate"], "False")
            self.assertEqual(row["counterfactual_only"], "True")

    def test_counterfactual_failures_never_formal_gate(self):
        audit = load("reachable_failure_audit.json")
        self.assertEqual(audit["all_prerendered_electrical_failure_count"], 19)
        self.assertEqual(audit["reachable_electrical_failure_count"], 0)
        with (OUT / "probe_reachability.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertTrue(all(not (row["counterfactual_only"] == "True" and row["formal_gate"] == "True") for row in rows))

    def test_all_reachable_operations_gate_and_updates_are_one_bit(self):
        for voltage in ("0p80", "0p95", "1p10"):
            rows = operations(voltage)
            self.assertTrue(all(row["formal_gate"] for row in rows))
            updates = [row for row in rows if row["operation"] == "config_update"]
            self.assertTrue(all(row["changed_thermometer_bits"] == 1 and row["reset_asserted"] and row["sclk_low"] for row in updates))

    def test_exact_operation_counts_and_timing_contract(self):
        expected = {"0p80": (45, 28), "0p95": (36, 22), "1p10": (36, 21)}
        for voltage, (total, compares) in expected.items():
            contract = load(f"exact_path_{voltage}_contract.json")
            rows = operations(voltage)
            self.assertEqual(len(rows), total)
            self.assertEqual(sum(row["operation"] in ("compare_probe", "lock_hold_probe") for row in rows), compares)
            self.assertEqual(sum(row["operation"] == "config_update" for row in rows), total - compares)
            self.assertTrue(all(row["settle_s"] == 1.5e-9 and row["configuration_edge_s"] == 1e-11 for row in rows if row["operation"] == "config_update"))
            self.assertTrue(all(row["code_constant_during_probe"] and row["q_sample_count"] == 2 and row["recovery_guard_s"] == 2.7e-9 for row in rows if row["operation"] in ("compare_probe", "lock_hold_probe")))
            self.assertEqual(contract["expected_executable_operation_count"], total)

    def test_recovery_count_report_and_json_are_consistent(self):
        recovery = load("reachable_recovery_audit.json")
        summary = load("summary.json")
        self.assertEqual(recovery["reachable_probe_count"], 28)
        self.assertEqual(summary["reachable_probe_count_by_vdd"]["0p80"], recovery["reachable_probe_count"])
        self.assertEqual(summary["reachable_probe_count_by_vdd"], {"0p80": 28, "0p95": 22, "1p10": 21})
        report = (HERE.parents[1] / "reports" / "FTC_REACHABLE_PATH_ACCEPTANCE.md").read_text(encoding="utf-8")
        self.assertIn("三电压真实探测数为 28、22、21", report)

    def test_decisions_are_derived_from_completed_hspice_audits(self):
        summary = load("summary.json")
        audit = load("reachable_failure_audit.json")
        expected_reachability = "GO" if audit["replay_consistency"] and audit["reachable_electrical_failure_count"] == 0 else "NO-GO"
        self.assertEqual(summary["reachability_semantics_decision"], expected_reachability)
        self.assertEqual(summary["formal_exact_path_decision"], "Exact Reachable-Path Dynamic Startup Calibration = GO")
        self.assertEqual(summary["final_dynamic_protocol_decision"], "Dynamic Startup Calibration Protocol = GO")
        self.assertEqual(summary["new_exact_path_hspice_scenarios"], 3)
        self.assertTrue(all(item["status"] == "GO" for item in summary["exact_path_hspice_results"].values()))
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn('"reachable_failure_count_by_vdd": {VOLTAGE_NAMES[s]: 0', source)

    def test_all_contracts_exist_and_no_historical_rerun(self):
        aggregate = load("exact_path_contract.json")
        self.assertEqual(set(aggregate["scenarios"]), {"0p80", "0p95", "1p10"})
        self.assertEqual(aggregate["hspice_run_count"], 0)
        summary = load("summary.json")
        self.assertEqual(summary["new_exact_path_hspice_scenarios"], 3)
        self.assertTrue(all(value == 0 for value in summary["all_old_rerun_counters"].values()))
        for voltage in aggregate["scenarios"]:
            self.assertTrue((OUT / f"exact_path_{voltage}_contract.json").exists())


if __name__ == "__main__":
    unittest.main()
