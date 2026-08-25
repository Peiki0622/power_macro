"""Regression checks for the actual B-FE2.2C corrected-seed evidence.

The test intentionally exercises the retained pair through the offline
analysis entry point.  It does not run HSPICE.  The important assertion is not
just the failed Gate: normal tap 27 must retain its first measured in-flight
resolution as allowed evidence, while its second source-free crossing must be
reported separately as the failure mechanism.
"""

import json
import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_bfe2_2c_corrected_seed as corrected  # noqa: E402


class Bfe22cCorrectedSeedAnalysisTest(unittest.TestCase):
    """Validate the complete offline Gate and causal event distinction."""

    @classmethod
    def setUpClass(cls):
        """Regenerate only compact analysis artifacts; no simulator is called."""

        if corrected.main() != 0:
            raise AssertionError("B-FE2.2C offline analysis did not complete")
        cls.result = json.loads((corrected.OUTPUT_ROOT / "BFE2_2C_ANALYSIS.json").read_text())

    def test_single_normal_event_is_retained_before_reflip_failure(self):
        """Tap 27 keeps normal in-flight evidence and the later genuine re-flip."""

        self.assertEqual(self.result["gate"], "BFE2_2C_CORRECTED_SEED_FAILED")
        self.assertEqual(self.result["normal_inflight_resolution_taps"]["normal"], [27])
        self.assertEqual(self.result["normal_inflight_resolution_taps"]["l2"], [])
        self.assertEqual(self.result["genuine_reflip_taps"], [27])
        normal = self.result["scenarios"][0]
        tap27 = next(item for item in normal["per_tap"] if item["tap"] == 27)
        self.assertEqual(tap27["classification"], "genuine-reflip")
        self.assertEqual([item["classification"] for item in tap27["post_close_event_classification"]],
                         ["normal_in_flight_data_event", "genuine_post_close_reflip"])
        self.assertLess(abs(tap27["post_close_event_classification"][0]["prediction_error_ps"]), 5.0)

    def test_l2_is_stable_and_pair_remains_distinguishable(self):
        """The failure is localized to normal tap 27, not a blanket pair rejection."""

        self.assertTrue(self.result["scenarios"][0]["final_q_stable"])
        self.assertTrue(self.result["scenarios"][1]["final_q_stable"])
        self.assertEqual(self.result["scenarios"][1]["genuine_reflip_taps"], [])
        self.assertEqual(self.result["normal_l2_hamming_distance"], 9)
        self.assertEqual(self.result["new_hspice_scenarios"], 0)

    def test_bfe2_3_is_not_authorized_after_failure(self):
        """A corrected-seed failure stops the chain before any aperture search."""

        self.assertFalse(self.result["bfe2_3_authorized"])
        self.assertIn("stop before B-FE2.3", self.result["reason"])


if __name__ == "__main__":
    unittest.main()
