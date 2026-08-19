"""Static contract tests for the FTC recovery-window repair.

The tests intentionally never call HSPICE.  Electrical acceptance is performed
only by the two bounded scenarios in the task-owned run directory; these tests
protect the phase boundaries, formulas, topology, and rerun budget beforehand.
"""

import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_dynamic_recovery_window_repair as repair  # noqa: E402


class RecoveryWindowRepairTests(unittest.TestCase):
    """Verify every non-electrical gate before allowing a new deck to run."""

    @classmethod
    def setUpClass(cls):
        cls.baseline = repair.freeze_baseline()
        cls.requirements = repair.requirements(cls.baseline)
        cls.diagnostic = repair.diagnostic_contract(cls.baseline)
        cls.trajectory = repair.build_trajectory()

    def test_frozen_baseline_is_the_recovery_only_entry(self):
        """The retained decision and all three voltage handoffs are mandatory."""
        self.assertEqual(self.baseline["decision"], "Dynamic Startup Calibration Protocol = NO-GO")
        self.assertEqual(self.baseline["reasons"], ["recovery_window_insufficient"])
        self.assertEqual(self.baseline["retained_0p95"], ("GO", "1111110", "10", 0, 5, 1))
        self.assertEqual(self.baseline["retained_1p10"], ("GO", "11110", "11110", 0, 3, 4))
        self.assertEqual(self.baseline["retained_0p80"], ("NO-GO", "1111111110", "10", 0, 8, 1))

    def test_old_failure_map_is_complete_and_dff_is_worst(self):
        """The publication gap is repaired from retained raw measurement only."""
        failure_map = repair.old_failure_map(self.baseline)
        self.assertGreater(failure_map["failure_count"], 0)
        self.assertEqual(failure_map["worst_failure"]["node"], "dff_ck")
        self.assertEqual(sorted({row["probe_index"] for row in failure_map["failures"]}), [7, 8, 9, 10, 11, 12])

    def test_diagnostic_bound_is_evidence_derived(self):
        """The current retained inputs produce the bounded 3.3 ns observation."""
        self.assertEqual(self.diagnostic["diagnostic_bound_s"], 3.3e-9)
        self.assertGreater(self.diagnostic["diagnostic_bound_s"], repair.OLD_GUARD_S)
        self.assertEqual(self.diagnostic["retained_D_delay_max_s"], 1.269042997e-9)
        self.assertEqual(self.diagnostic["max_xor_fall_minus_launch_s"], 1.5751873509999997e-9)

    def test_new_guard_formula_and_bounds(self):
        """Guard is measured fall time plus exactly the frozen 200 ps tail."""
        measured = {"worst_return_settle_ns": 3.01}
        contract = repair.repaired_contract(measured, self.diagnostic)
        self.assertEqual(contract["new_recovery_guard_s"], 3.3e-9)
        self.assertAlmostEqual(contract["added_guard_s"], 0.8e-9, places=21)
        self.assertEqual(contract["safety_tail_s"], repair.Q_SETTLE_S)
        self.assertEqual(contract["derivation"], "measured_return_fall10_plus_200ps")
        with self.assertRaisesRegex(ValueError, "measured_guard_not_greater"):
            repair.repaired_contract({"worst_return_settle_ns": 2.2}, self.diagnostic)

    def test_trajectory_and_topology_are_frozen(self):
        """The repair retains 13 probes and one thermometer-bit transition."""
        self.assertEqual(len(self.trajectory["probes"]), 13)
        for transition in self.trajectory["transitions"]:
            medium = sum(a != b for a, b in zip(repair.thermometer(repair.MEDIUM_N, transition["old_M"]), repair.thermometer(repair.MEDIUM_N, transition["new_M"])))
            fine = sum(a != b for a, b in zip(repair.thermometer(repair.FINE_K, transition["old_F"]), repair.thermometer(repair.FINE_K, transition["new_F"])))
            self.assertEqual(medium + fine, 1)
        schedule = repair.schedule_trajectory(self.trajectory, self.diagnostic["diagnostic_bound_s"])
        deck = repair.render_deck(repair.context_from_baseline(), schedule, "diagnostic")
        checks = repair.topology_checks(deck, schedule)
        self.assertTrue(all(checks.values()), checks)
        source = inspect.getsource(repair)
        self.assertNotRegex(source, r"(?m)^\s*(?:from|import)\s+run_dynamic_startup_calibration_protocol\b")
        self.assertNotRegex(source, r"(?m)^\s*(?:from|import)\s+run_two_stage_real_dff_hierarchical_calibration\b")

    def test_phase0_never_launches_hspice(self):
        """Phase 0 writes only task-owned contracts and cannot execute a deck."""
        with tempfile.TemporaryDirectory(prefix="ftc_repair_phase0_") as temporary:
            root = Path(temporary)
            with mock.patch.object(repair.subprocess, "run", side_effect=AssertionError("phase0 launched HSPICE")):
                self.assertEqual(repair.main(["--phase", "phase0", "--analysis-dir", str(root / "analysis"), "--run-root", str(root / "runs"), "--report-output", str(root / "report.md")]), 0)
            self.assertTrue((root / "analysis" / "frozen_baseline.json").is_file())
            self.assertFalse((root / "runs").exists())

    def test_budget_and_forbidden_scope(self):
        """The contract allows exactly one diagnostic and one repaired scenario."""
        self.assertEqual(self.requirements["diagnostic_scenario_budget"], 1)
        self.assertEqual(self.requirements["repaired_scenario_budget"], 1)
        self.assertEqual(self.requirements["upstream_static_84_scenarios_rerun"], 0)
        self.assertEqual(self.requirements["old_dynamic_0p95_rerun"], 0)
        self.assertEqual(self.requirements["old_dynamic_1p10_rerun"], 0)
        self.assertEqual(self.requirements["old_dynamic_0p80_rerun"], 0)
        self.assertIn("FSM", self.requirements["forbidden"])
        self.assertIn("programmable_margin", self.requirements["forbidden"])


if __name__ == "__main__":
    unittest.main()
