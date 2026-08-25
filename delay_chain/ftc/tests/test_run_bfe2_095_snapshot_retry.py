"""Static checks for the one permitted B-FE2.2 0.95-V replacement pair."""

import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_bfe2_095_snapshot_retry as retry  # noqa: E402


class Bfe2RetryTest(unittest.TestCase):
    """Ensure the retry cannot become a generic close-time scan."""

    def test_only_formal_095_normal_l2_pair_is_authorized(self):
        """The replacement must be exactly two matching-close electrical cases."""

        scenarios = retry.retry_scenarios()
        self.assertEqual([item["scenario_id"] for item in scenarios], ["BFE2L-095-N", "BFE2L-095-L2"])
        self.assertTrue(all(item["baseline_v"] == 0.95 for item in scenarios))
        self.assertEqual(retry.RETRY_CLOSE_PS, 320.333956)


if __name__ == "__main__":
    unittest.main()
