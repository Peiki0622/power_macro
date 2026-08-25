"""Zero-HSPICE regressions for B-FE2.2S safe-close seed reconstruction."""

import json
import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_bfe2_2s_safe_seed as safe_seed  # noqa: E402


class Bfe22sSafeSeedTest(unittest.TestCase):
    """Protect the corrected Q/D-to-Q admission rule from XOR-only regression."""

    def setUp(self):
        """Regenerate derived B-FE2.2S evidence without creating a simulation."""

        self.assertEqual(safe_seed.main(), 0)
        self.result = json.loads((safe_seed.OUTPUT_ROOT / "BFE2_2S_SAFE_INTERVALS.json").read_text())

    def test_095_is_blocked_when_every_q_interval_has_an_inflight_tap(self):
        """A clean Q word alone cannot authorize close while any D→Q flight remains."""

        baseline = self.result["baselines"]["0.95"]
        self.assertEqual(self.result["gate"], "BFE2_2S_SAFE_SEED_BLOCKED")
        self.assertGreater(len(baseline["common_q_stable_intervals"]), 0)
        self.assertEqual(baseline["provisional_safe_intervals"], [])
        self.assertTrue(all(item["normal_inflight_risks"] or item["l2_inflight_risks"]
                            for item in baseline["examined_subintervals"]))
        self.assertIsNone(self.result["selected_corrected_seed"])
        self.assertEqual(self.result["new_hspice_scenarios"], 0)

    def test_110_historical_pair_is_not_silently_promoted(self):
        """The already-run 1.10-V pair must be audited, not rerun or accepted by fiat."""

        audit = self.result["historical_110_consistency"]
        self.assertTrue(audit["checked_without_rerun"])
        self.assertFalse(audit["consistent_with_corrected_rule"])
        self.assertTrue(any(item["post_close_inflight_events"] for item in audit["scenarios"]))

    def test_split_uses_physical_d_and_q_boundaries_not_a_time_grid(self):
        """One D-to-Q flight cuts only its retained crossing boundaries."""

        interval = {"interval_start_ps": 10.0, "interval_end_ps": 30.0}
        flights = [{"tap": 6, "direction": "fall", "d_cross_ps": 14.0,
                    "predicted_q_arrival_ps": 21.0, "measured_d_to_q_delay_ps": 7.0}]
        self.assertEqual(safe_seed.split_at_boundaries(interval, flights), [(10.0, 14.0), (14.0, 21.0), (21.0, 30.0)])
        self.assertEqual(safe_seed.flights_covering(17.0, flights)[0]["tap"], 6)
        self.assertEqual(safe_seed.flights_covering(10.0, flights), [])


if __name__ == "__main__":
    unittest.main()
