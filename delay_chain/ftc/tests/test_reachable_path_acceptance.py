"""可达路径验收的零仿真合同测试。"""

import csv
import json
import unittest
from pathlib import Path


HERE = Path(__file__).resolve()
OUT = HERE.parents[1] / "analysis" / "reachable_path_acceptance"


def load(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


class ReachablePathAcceptanceTest(unittest.TestCase):
    """锁定决策顺序、计数、分支过滤和 HSPICE 预算。"""

    def test_frozen_baseline_and_semantics(self):
        frozen = load("frozen_evidence.json")
        self.assertEqual(frozen["baseline_commit"], "b822c0295c01348efb69eaa5b492ce4065786d7d")
        self.assertEqual(frozen["legacy_acceptance_semantics"], "all_prerendered_rows_are_global_gates")
        self.assertEqual(frozen["legacy_status"], {"0p80": "NO-GO", "0p95": "GO", "1p10": "GO"})
        self.assertEqual(frozen["hspice_scenarios_created"], 0)

    def test_replay_counts_and_boundaries(self):
        expected = {"0p80": (28, 9, 7, 5, 6), "0p95": (22, 6, 4, 5, 6), "1p10": (21, 4, 2, 8, 9)}
        for voltage, values in expected.items():
            data = load("reachable_replay_%s.json" % voltage)
            self.assertEqual((data["reachable_probe_count"], data["coarse_boundary"], data["primary_medium_base"], data["fine_boundary"], data["guard_code"]), values)

    def test_counterfactual_failures_never_formal_gate(self):
        audit = load("reachable_failure_audit.json")
        self.assertEqual(audit["all_prerendered_electrical_failure_count"], 19)
        self.assertEqual(audit["reachable_electrical_failure_count"], 0)
        with (OUT / "probe_reachability.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertTrue(all(not (r["counterfactual_only"] == "True" and r["formal_gate"] == "True") for r in rows))
        self.assertEqual(next(r for r in rows if r["scenario"] == "0p80_normal" and r["probe_index"] == "20")["counterfactual_reason"], "after_coarse_stop")

    def test_exact_path_operations(self):
        for voltage, expected_count in (("0p80", 30), ("0p95", 24), ("1p10", 23)):
            contract = load("exact_path_%s_contract.json" % voltage)
            operations = contract["operations"]
            self.assertEqual(len(operations), expected_count)
            self.assertEqual(sum(op["operation"] == "config_update" for op in operations), 2)
            self.assertEqual(sum(op["operation"] == "lock_hold_probe" for op in operations), 1)
            self.assertTrue(all(op.get("sclk_low", True) and op.get("changed_thermometer_bits", 1) == 1 for op in operations if op["operation"] == "config_update"))
        aggregate = load("exact_path_contract.json")
        self.assertEqual(aggregate["hspice_run_count"], 0)
        self.assertEqual(aggregate["hspice_scenario_budget"], 3)

    def test_guard_is_reachable_only_and_no_sweep(self):
        guard = load("reachable_guard_derivation.json")
        self.assertFalse(guard["sweep_performed"])
        self.assertTrue(guard["excluded_counterfactual_probe_109"])
        self.assertEqual(guard["frozen_functional_guard_s"], 2.7e-9)

    def test_no_old_rerun_and_pending_formal_result(self):
        summary = load("summary.json")
        self.assertEqual(summary["new_exact_path_hspice_scenarios"], 0)
        self.assertEqual(summary["formal_exact_path_decision"], "PENDING_HSPICE")
        self.assertEqual(summary["final_dynamic_protocol_decision"], "PENDING_HSPICE")
        self.assertEqual(summary["reachable_failure_count_by_vdd"]["0p80"], 0)


if __name__ == "__main__":
    unittest.main()
