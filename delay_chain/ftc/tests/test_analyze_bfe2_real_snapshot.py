"""Zero-HSPICE regressions for B-FE2.2 Q-transition stability diagnosis."""

import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_bfe2_real_snapshot as analysis  # noqa: E402


class Bfe2RealSnapshotAnalysisTest(unittest.TestCase):
    """Ensure retry evidence remains bounded to the failed baseline."""

    def test_selection_replaces_only_095_and_keeps_110_first_pair(self):
        """No passing 1.10-V scenario may be rerun or silently discarded."""

        selected = analysis.choose_authoritative_scenarios()
        self.assertEqual(len(selected), 4)
        self.assertEqual(sum(is_retry for _, is_retry in selected), 2)
        self.assertTrue(all(float(item["baseline_v"]) == 0.95 for item, is_retry in selected if is_retry))
        self.assertTrue(all(float(item["baseline_v"]) == 1.10 for item, is_retry in selected if not is_retry))

    def test_observed_g_close_is_used_for_transition_timing(self):
        """The finite G PWL must be measured at local VDD/2, not assumed ideal."""

        item, is_retry = next((item, retry) for item, retry in analysis.choose_authoritative_scenarios()
                              if retry and item["scenario_id"] == "BFE2L-095-N")
        result = analysis.assess(item, is_retry)
        self.assertIn("requested_close_ps", result)
        self.assertIn("observed_g_close_ps", result)
        self.assertNotEqual(result["requested_close_ps"], result["observed_g_close_ps"])


if __name__ == "__main__":
    unittest.main()
