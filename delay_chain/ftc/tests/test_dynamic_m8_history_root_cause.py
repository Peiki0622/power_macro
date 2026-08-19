"""No-HSPICE contract tests for the FTC M8 history investigation.

The electrical matrix is intentionally not executed by this test module.  It
protects the retained evidence, factor limits, episode isolation, measurement
contract, and one-scenario budget before the runner is allowed to launch
HSPICE.
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
import run_dynamic_m8_history_root_cause as study  # noqa: E402


class DynamicM8HistoryRootCauseTests(unittest.TestCase):
    """Verify every non-electrical gate required before the single run."""

    @classmethod
    def setUpClass(cls):
        cls.baseline = study.freeze_baseline()
        cls.contract = study.matrix_contract()
        cls.analysis = FTC_ROOT / "analysis" / "dynamic_m8_history_dependence_root_cause"

    def test_frozen_handoff_and_retained_q_sequences(self):
        """The known diagnostic Q flip is preserved as an input fact."""
        self.assertEqual(self.baseline["baseline_commit"], study.BASELINE_COMMIT)
        recovery = json.loads((self.analysis / "../dynamic_recovery_window_repair/summary.json").resolve().read_text())
        self.assertEqual(recovery["decision"], "Dynamic Recovery Window Repair = NO-GO")
        self.assertEqual(recovery["reasons"], ["diagnostic_q_sequence_changed"])
        rows, _, publication_ok = study.retained_rows(self.baseline)
        self.assertTrue(publication_ok)
        self.assertEqual("".join(str(row["Q_2p5"]) for row in rows), "1111111110100")
        self.assertEqual("".join(str(row["Q_3p3"]) for row in rows), "1111111100100")
        self.assertEqual((rows[8]["M"], rows[8]["F"], rows[8]["Q_changed"]), (8, 0, True))
        self.assertEqual((rows[10]["M"], rows[10]["F"], rows[10]["Q_3p3"]), (8, 0, 1))
        self.assertAlmostEqual(self.baseline["candidate_functional_guard_s"], 2.7e-9)
        self.assertEqual(self.baseline["diagnostic_bound_s"], 3.3e-9)

    def test_matrix_contains_only_approved_factors_and_groups(self):
        """All A--G controls live in one contract with no extra sweep value."""
        self.assertEqual(set(self.contract["required_groups"]), set("ABCDEFG"))
        self.assertEqual(tuple(self.contract["recovery_guards_s"]), study.RECOVERY_VALUES)
        self.assertEqual(tuple(self.contract["code_settle_guards_s"]), study.SETTLE_VALUES)
        self.assertEqual(tuple(self.contract["reset_separations_s"]), study.RESET_VALUES)
        self.assertEqual(self.contract["isolation_guard_s"], study.ISOLATION_GUARD_S)
        self.assertEqual(self.contract["episode_count"], 29)
        conditions = {episode["condition"] for episode in self.contract["episodes"]}
        for condition in ("m7_to_m8_2p7", "m9_to_m8_2p7", "m8_to_m8_2p7", "config_only_m7", "config_only_m9", "ascending", "descending", "isolated_m8"):
            self.assertIn(condition, conditions)
        self.assertEqual(self.contract["required_groups"], list("ABCDEFG"))

    def test_schedule_is_single_bit_and_returns_to_known_state(self):
        """Every episode resets M serially to zero and never changes F."""
        schedule = study.build_schedule(self.contract)
        self.assertTrue(all(transition["new_F"] == 0 for transition in schedule["transitions"]))
        self.assertTrue(all(sum(a != b for a, b in zip(study.thermometer(study.MEDIUM_N, transition["old_M"]), study.thermometer(study.MEDIUM_N, transition["new_M"]))) == 1 for transition in schedule["transitions"]))
        self.assertEqual(len([episode for episode in schedule["episodes"] if episode["episode_id"] == "A4"]), 1)
        self.assertEqual(self.contract["episode_count"], len(schedule["episodes"]))

    def test_measurement_and_forbidden_scope_are_explicit(self):
        """The generated deck measures internal nodes and second CK edges."""
        schedule = study.build_schedule(self.contract)
        deck = study.render_deck(study.context(), schedule, self.contract)
        checks = study.topology_checks(deck, self.contract, schedule)
        self.assertTrue(all(checks.values()), checks)
        for node in study.INTERNAL_NODES:
            self.assertIn(node, deck)
        self.assertIn("_rise_50_2", deck)
        source = inspect.getsource(study)
        self.assertNotRegex(source, r"(?m)^\s*(?:from|import)\s+run_dynamic_(?:startup_calibration_protocol|recovery_window_repair)\b")
        self.assertNotRegex(source, r"84\s+static|0\.95|1\.10")
        self.assertNotIn("ConfigSkip", deck)

    def test_read_only_phases_never_call_hspice(self):
        """Phase0 and retained-analysis must remain zero-HSPICE paths."""
        with tempfile.TemporaryDirectory(prefix="ftc_m8_history_contract_") as temporary:
            root = Path(temporary)
            with mock.patch.object(study, "validate_hspice", side_effect=AssertionError("read-only phase launched HSPICE")), mock.patch.object(study, "execute_scenario", side_effect=AssertionError("read-only phase launched HSPICE")):
                self.assertEqual(study.main(["--phase", "phase0", "--analysis-dir", str(root / "analysis"), "--run-root", str(root / "runs")]), 0)
                self.assertEqual(study.main(["--phase", "retained-analysis", "--analysis-dir", str(root / "analysis2"), "--run-root", str(root / "runs2")]), 0)
            self.assertFalse((root / "runs").exists())
            self.assertFalse((root / "runs2").exists())

    def test_repaired_phase_requires_schedule_only_gate(self):
        """A missing classification gate cannot create a second scenario."""
        with tempfile.TemporaryDirectory(prefix="ftc_m8_history_repaired_") as temporary:
            with self.assertRaisesRegex(RuntimeError, "not authorized"):
                study.main(["--phase", "repaired", "--analysis-dir", str(Path(temporary) / "analysis"), "--run-root", str(Path(temporary) / "runs")])


if __name__ == "__main__":
    unittest.main()
