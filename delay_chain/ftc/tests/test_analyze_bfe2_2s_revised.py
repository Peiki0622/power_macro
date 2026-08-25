"""Regression tests for the revised B-FE2.2S single-resolution rule."""

import json
import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_bfe2_2s_revised as revised  # noqa: E402


class Bfe22sRevisedTest(unittest.TestCase):
    """Ensure the revised offline Gate admits only a physically described seed."""

    def setUp(self):
        """Regenerate revised JSON/report only; no simulator is reachable here."""

        self.assertEqual(revised.main(), 0)
        self.result = json.loads((revised.OUTPUT_ROOT / "BFE2_2S_REVISED_SAFE_INTERVALS.json").read_text())

    def test_ready_seed_has_single_or_zero_per_tap_and_is_distinguishable(self):
        """The selected 0.95-V interval has no unresolved tap and positive Hamming distance."""

        self.assertEqual(self.result["gate"], "BFE2_2S_SAFE_SEED_READY")
        selected = self.result["selected_corrected_seed"]
        self.assertIsNotNone(selected)
        self.assertGreater(selected["interval_end_ps"], selected["interval_start_ps"])
        self.assertGreater(selected["hamming_distance"], 0)
        self.assertEqual(selected["unresolved_taps"], [])
        self.assertEqual(selected["reflip_taps"], [])
        for item in selected["normal_tap_classification"] + selected["l2_tap_classification"]:
            self.assertIn(item["classification"], ("zero-crossing", "single-normal-resolution"))

    def test_historical_reflip_points_are_not_overwritten(self):
        """Old 0.95-V genuine re-flips remain visible as historical evidence."""

        old = json.loads((revised.previous.SNAPSHOT_ROOT / "BFE2_2_GATE_STATUS.json").read_text())
        self.assertEqual(old["gate"], "BFE2_2_REAL_SNAPSHOT_CONDITIONAL")
        points = self.result["historical_0p95_reflip_points"]
        self.assertTrue(any(point["genuine_reflip_taps"] for point in points))
        self.assertTrue((revised.previous.ROOT_CAUSE).is_file())

    def test_run_budget_remains_zero(self):
        """Revision is purely offline and retains historical 4/6 accounting."""

        self.assertEqual(self.result["new_hspice_scenarios"], 0)
        self.assertEqual(self.result["executed_new_hspice_scenarios"]["B-FE2.1"], 4)
        self.assertEqual(self.result["executed_new_hspice_scenarios"]["B-FE2.2"], 6)
        self.assertEqual(self.result["executed_new_hspice_scenarios"]["B-FE2.2S"], 0)

    def test_classification_helper_distinguishes_zero_single_and_unresolved(self):
        """The tap classifier has explicit one-event and multi-event branches."""

        flight = {"tap": 3, "direction": "rise", "d_cross_ps": 10.0,
                  "predicted_q_arrival_ps": 20.0, "measured_d_to_q_delay_ps": 10.0}
        self.assertEqual(revised.classify_tap(5.0, 3, [flight])["classification"], "zero-crossing")
        self.assertEqual(revised.classify_tap(15.0, 3, [flight])["classification"], "single-normal-resolution")
        self.assertEqual(revised.classify_tap(15.0, 3, [flight, dict(flight, d_cross_ps=11.0, predicted_q_arrival_ps=21.0)])["classification"], "unresolved")


if __name__ == "__main__":
    unittest.main()
