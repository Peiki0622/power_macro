"""Zero-HSPICE regression coverage for the D0-0 timing feasibility decision.

These tests do not launch a simulator.  They recompute the published budget
from the frozen M0/T0/M1 contracts and protect the exact arithmetic that makes
the D0-0 ARCHITECTURE_REVIEW conclusion reproducible.
"""

import inspect
import json
import sys
import unittest
from pathlib import Path


# Add only the FTC script directory.  The tested module is a local JSON
# post-processor, so importing it cannot invoke the HSPICE wrapper or produce
# a simulation run directory.
FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_d0_runtime_timing as study  # noqa: E402


class D0RuntimeTimingTests(unittest.TestCase):
    """Verify the published D0-0 lower bound and its strict scope boundary."""

    @classmethod
    def setUpClass(cls):
        """Load the committed artifact once without rewriting generated files."""

        cls.published = json.loads(study.OUTPUT_CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.recomputed = study.build_budget()

    def test_published_contract_is_the_deterministic_zero_hspice_budget(self):
        """Reject stale output, input-hash drift, or an accidental simulator path."""

        self.assertEqual(self.published, self.recomputed)
        self.assertEqual(self.published["decision"], "ARCHITECTURE_REVIEW")
        self.assertEqual(self.published["decision_basis"], "zero_hspice_frozen_contract_timing_budget")
        self.assertEqual(self.published["simulation_accounting"]["hspice_scenarios"], 0)
        self.assertEqual(self.published["simulation_accounting"]["new_hspice_scenarios"], 0)
        source = inspect.getsource(study).lower()
        self.assertNotIn("subprocess", source)
        # The analysis may document the word "HSPICE" to state its scope, but
        # it must never contain a simulator-dispatch helper or wrapper path.
        self.assertNotIn("run_hspice", source)
        self.assertNotIn("hspice_wrapper", source)

    def test_two_q_samples_complete_after_the_required_runtime_deadline(self):
        """Keep the 2.50 ns Q2 lower bound distinct from the 2.075 ns target."""

        requirement = self.published["runtime_requirement"]
        offsets = self.published["frozen_single_probe_evidence"]["event_offsets_from_sclk_rise_ps"]
        timing = self.published["timing_budget"]
        self.assertAlmostEqual(requirement["maximum_period_ps"], 2075.0)
        self.assertFalse(requirement["control_clock_is_runtime_probe_cadence"])
        self.assertAlmostEqual(offsets["q_sample_1"], 2300.0)
        self.assertAlmostEqual(offsets["q_sample_2"], 2500.0)
        self.assertAlmostEqual(timing["q2_completion_shortfall_to_requirement_ps"], 425.0)
        self.assertTrue(self.published["frozen_single_probe_evidence"]["q_decision"]["two_samples_required"])

    def test_reset_cycle_and_sclk_level_make_the_conflict_stronger(self):
        """Verify every later current-probe event remains after a 2075 ps rise."""

        timing = self.published["timing_budget"]
        unfinished = timing["unfinished_current_probe_events_at_required_next_rise_ps"]
        self.assertAlmostEqual(timing["sclk_high_width_lower_bound_ps"], 3000.0)
        self.assertAlmostEqual(timing["optimistic_serial_reset_to_next_rise_lower_bound_ps"], 3200.0)
        self.assertAlmostEqual(timing["serial_reset_shortfall_to_requirement_ps"], 1125.0)
        self.assertAlmostEqual(timing["full_recovery_nonoverlap_reference_ps"], 5700.0)
        self.assertTrue(all(value > 0.0 for value in unfinished.values()))

    def test_scope_keeps_m1_static_and_does_not_substitute_new_digital_logic(self):
        """Prevent an infeasible capture cadence from being hidden by D0 features."""

        scope = self.published["scope"]
        candidate = self.published["candidate_microsequence"]
        review = self.published["architecture_review"]
        self.assertEqual(scope["frozen_contracts_modified"], [])
        self.assertEqual(scope["m1_output_configuration"], "STATIC_UNMODIFIED")
        self.assertFalse(candidate["available"])
        self.assertTrue(review["not_a_digital_logic_fix"])
        self.assertIn("d0_fsm", scope["forbidden_implementations"])


if __name__ == "__main__":
    unittest.main()
