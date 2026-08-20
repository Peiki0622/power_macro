"""精确路径 runner 的零 HSPICE 渲染与预算冻结测试。"""

import hashlib
import json
import unittest
from pathlib import Path


HERE = Path(__file__).resolve()
OUT = HERE.parents[1] / "analysis" / "reachable_path_acceptance" / "exact_hspice"


def load(name):
    """读取 runner 生成的冻结证据。"""
    return json.loads((OUT / name).read_text(encoding="utf-8"))


class ExactReachablePathRunnerTest(unittest.TestCase):
    """确认三份 deck 已完整渲染且尚未进入模拟阶段。"""

    def test_pre_run_freeze_has_exactly_three_immutable_scenarios(self):
        freeze = load("pre_run_freeze.json")
        self.assertEqual(freeze["scenario_budget"], 3)
        self.assertEqual(freeze["scenario_order"], ["exact_path_0p80", "exact_path_0p95", "exact_path_1p10"])
        self.assertEqual(freeze["historical_scenarios_scheduled"], 0)
        self.assertFalse(freeze["simulator_invoked"])
        self.assertEqual(len(freeze["contracts_and_decks"]), 3)

    def test_contract_and_deck_hashes_and_operation_schedules(self):
        freeze = load("pre_run_freeze.json")
        for item in freeze["contracts_and_decks"]:
            voltage = item["voltage"]
            directory = OUT / f"exact_path_{voltage}"
            contract = json.loads((HERE.parents[1] / "analysis" / "reachable_path_acceptance" / f"exact_path_{voltage}_contract.json").read_text())
            deck = directory / "exact_reachable_path.sp"
            manifest = json.loads((directory / "render_manifest.json").read_text())
            schedule = json.loads((directory / "operation_schedule.json").read_text())
            self.assertEqual(item["contract_sha256"], hashlib.sha256((HERE.parents[1] / "analysis" / "reachable_path_acceptance" / f"exact_path_{voltage}_contract.json").read_bytes()).hexdigest())
            self.assertEqual(item["deck_sha256"], hashlib.sha256(deck.read_bytes()).hexdigest())
            self.assertEqual(manifest["contract_sha256"], item["contract_sha256"])
            self.assertEqual(manifest["deck_sha256"], item["deck_sha256"])
            self.assertFalse(manifest["simulator_invoked"])
            self.assertEqual(sum(row["counted_operation"] for row in contract["operations"]), contract["expected_executable_operation_count"])
            self.assertEqual(len(schedule["probes"]), sum(row["operation"] in ("compare_probe", "lock_hold_probe") for row in contract["operations"]))
            self.assertIn("V_M_00", deck.read_text())
            self.assertIn("V_F_00", deck.read_text())

    def test_completed_hspice_audits_and_final_report_are_consistent(self):
        """交叉检查已完成三场景、逐操作审计、最终 JSON 与 Markdown 报告。"""
        final = load("final_acceptance.json")
        self.assertEqual(final["decision"], "GO")
        self.assertEqual(final["scenario_count"], 3)
        self.assertEqual(final["historical_counterfactual_failure_count"], 19)
        self.assertEqual(final["reachable_failure_count"], 0)
        expected = {"0p80": (45, 28, 17, {"M": 7, "F": 6}), "0p95": (36, 22, 14, {"M": 4, "F": 6}), "1p10": (36, 21, 15, {"M": 2, "F": 9})}
        for voltage, (operations, probes, updates, code) in expected.items():
            item = final["results"][voltage]
            audit = json.loads((OUT / f"exact_path_{voltage}" / "scenario_acceptance.json").read_text())
            self.assertEqual(item["status"], "GO")
            self.assertEqual((item["operation_count"], item["compare_operation_count"], item["config_update_count"], item["final_locked_code"]), (operations, probes, updates, code))
            self.assertEqual(len(audit["probe_audit"]), probes)
            self.assertEqual(len(audit["operation_audit"]), updates)
            self.assertTrue(all(row["status"] == "PASS" for row in audit["probe_audit"] + audit["operation_audit"]))
            self.assertTrue((OUT / f"exact_path_{voltage}" / "per_probe_q_measurements.csv").is_file())
            self.assertTrue((OUT / f"exact_path_{voltage}" / "per_operation_transition_audit.csv").is_file())
            self.assertTrue((OUT / f"exact_path_{voltage}" / "ck_edge_audit.json").is_file())
            self.assertTrue((OUT / f"exact_path_{voltage}" / "recovery_audit.json").is_file())
        report = Path(final["report"]).read_text(encoding="utf-8")
        self.assertIn("Exact Reachable-Path Dynamic Startup Calibration = GO", report)
        self.assertIn("Dynamic Startup Calibration Protocol = GO", report)


if __name__ == "__main__":
    unittest.main()
