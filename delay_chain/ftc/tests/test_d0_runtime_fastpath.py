"""Zero-HSPICE regression checks for the D0-A runtime fast-path closure.

These tests validate published compact evidence and runner arithmetic only.
They never invoke the diagnostic deck runner, so they cannot consume the
strict two-scenario HSPICE allowance established by D0-A1.
"""

import json
import sys
import unittest
from pathlib import Path


# The test imports the study's pure post-processing helpers from the local FTC
# script directory.  No environment activation or simulator process is needed
# for that import; HSPICE remains exclusively under the task-owned run root.
FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_d0_runtime_fastpath as study  # noqa: E402


class D0RuntimeFastpathTests(unittest.TestCase):
    """Protect the terminal escalation and forbid accidental false fast-path GO."""

    def test_diagnostic_summary_keeps_widths_and_post_reset_edge_distinct(self):
        """A second CK edge must not be recast as a legal next probe capture.

        The synthetic numbers use seconds because that is HSPICE's scalar
        output unit.  The expected values prove the helper converts to ps,
        validates the independently reported width, and counts only rises in
        the reset-release-to-assert capture window.
        """

        result = {
            "spec": {"scenario_key": "unit", "baseline_vdd_v": 0.95, "Vdroop_v": 0.86,
                     "M_det": 5, "F_det": 6, "phase_ps": 75.0},
            "scenario_path": "task-owned/unit",
            "measurements": {
                "a1_sclk_rise": 1.0e-9,
                "a1_sclk_fall": 4.0e-9,
                "a1_reset_release": 0.5e-9,
                "a1_reset_assert": 3.5e-9,
                "a1_xor_fall": 2.0e-9,
                "a1_medium_fall": 2.1e-9,
                "a1_ck_rise": 1.5e-9,
                "a1_ck_fall": 2.0e-9,
                "a1_ck_rise_2": 4.0e-9,
                "a1_ck_high_width": 0.5e-9,
                "a1_q_high_10": 1.7e-9,
                "a1_q_high_90": 1.8e-9,
                "a1_q_reset_low_10": 3.6e-9,
            },
        }
        summary = study.diagnostic_summary(result)
        self.assertEqual(summary["sclk_high_width_ps"], 3000.0)
        self.assertEqual(summary["dff_ck_high_width_ps"], 500.0)
        self.assertEqual(summary["dff_ck_low_width_to_second_edge_ps"], 2000.0)
        self.assertTrue(summary["dff_ck_high_width_measure_consistent"])
        self.assertEqual(summary["capture_edges_between_release_and_assert"], 1)
        self.assertTrue(summary["second_ck_rise_after_reset_assert"])

    def test_a1_budget_is_limited_to_the_two_authorized_target_diagnostics(self):
        """Require physical CK evidence without allowing a hidden campaign rerun."""

        budget = json.loads((FTC_ROOT / "analysis/d0_runtime_fastpath/a1_physical_budget/physical_timing_budget.json").read_text())
        accounting = budget["simulation_accounting"]
        self.assertEqual(budget["gate"], "SINGLE_LANE_PHYSICAL_BUDGET_READY")
        self.assertEqual(accounting["new_hspice_scenarios"], 2)
        self.assertEqual(accounting["forbidden_flow_runs"], 0)
        self.assertEqual(len(budget["physical_diagnostics"]), 2)
        self.assertEqual(
            {item["scenario_key"] for item in budget["physical_diagnostics"]},
            {"d0a1_0p95_l2_long_right_clean", "d0a1_1p10_l2_long_right_clean"},
        )
        for item in budget["physical_diagnostics"]:
            self.assertTrue(item["dff_ck_high_width_measure_consistent"])
            self.assertLess(item["dff_ck_high_width_ps"], study.CAPTURE_CK_HIGH_MIN_PS)
            self.assertEqual(item["capture_edges_between_release_and_assert"], 1)
            self.assertTrue(item["second_ck_rise_after_reset_assert"])

    def test_a2_routes_root_ck_violation_away_from_a3_and_a4(self):
        """A Q-side structure cannot be used to mask an illegal capture clock."""

        contract = json.loads((FTC_ROOT / "analysis/d0_runtime_fastpath/a2_single_path_candidate/candidate_timing_contract.json").read_text())
        timing = contract["capture_ck_timing"]
        self.assertEqual(contract["classification"], "SENSOR_CLOCK_OR_RECOVERY_LIMITED")
        self.assertEqual(contract["root_cause"], "measured_dff_ck_high_width_violates_formal_cell_minimum")
        self.assertFalse(contract["routing"]["a3_multi_probe_authorized"])
        self.assertFalse(contract["routing"]["a4_q_local_hold_authorized"])
        self.assertTrue(contract["routing"]["a5_interleave_review_required"])
        self.assertEqual(timing["formal_hard_total_ps"], 2000.0)
        self.assertEqual(timing["hard_residual_at_2075ps"], 75.0)
        self.assertLess(timing["minimum_measured_target_ck_high_width_ps"], timing["formal_high_min_ps"])

    def test_a5_and_final_gate_do_not_claim_an_unverified_lane_or_runtime_rtl(self):
        """The terminal result must be an escalation, not an inferred two-lane GO."""

        lanes = json.loads((FTC_ROOT / "analysis/d0_runtime_fastpath/a5_interleave_review/lane_count_analysis.json").read_text())
        gate = json.loads((FTC_ROOT / "analysis/d0_runtime_fastpath/reports/D0_A_GATE_STATUS.json").read_text())
        comparison = (FTC_ROOT / "analysis/d0_runtime_fastpath/a5_interleave_review/architecture_comparison.md").read_text()
        self.assertEqual(lanes["decision"], "ARCHITECTURE_ESCALATION_REQUIRED")
        self.assertIsNone(lanes["P_lane_verified_ps"])
        self.assertEqual(lanes["N_min_model_guarded"], 2)
        # The published wording may evolve, but it must retain the material
        # guardrail: the 2500 ps value cannot be presented as verified silicon
        # or transistor-level lane cadence.
        self.assertIn("not a claim", lanes["important_limit"])
        self.assertEqual(gate["decision"], "ARCHITECTURE_ESCALATION_REQUIRED")
        self.assertEqual(gate["simulation_accounting"]["new_hspice_scenarios"], 2)
        self.assertIn("d0_runtime_fsm", gate["forbidden_in_this_stage"])
        # An escalation is actionable only when it links a separate plan.  The
        # presence check prevents future edits from silently turning the
        # terminal D0-A result into an unbounded implementation request.
        self.assertEqual(gate["next_architecture_plan"], "plans/ftc_d0b_interleaved_capture_architecture_plan.md")
        self.assertTrue((FTC_ROOT.parent.parent / gate["next_architecture_plan"]).is_file())
        for candidate in ("A. 单 capture", "B. 两个交错", "C. 独立 sensor"):
            self.assertIn(candidate, comparison)


if __name__ == "__main__":
    unittest.main()
