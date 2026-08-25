"""Offline B-FE2.2R regressions against immutable saved latch waveforms."""

import json
import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_bfe2_2r_root_cause as root_cause  # noqa: E402


class Bfe22rRootCauseTest(unittest.TestCase):
    """Ensure the close-time root-cause result remains evidence-driven."""

    def setUp(self):
        """Regenerate only derived JSON/Markdown; the test never invokes HSPICE."""

        self.assertEqual(root_cause.main(), 0)
        self.result = json.loads((root_cause.OUTPUT_ROOT / "BFE2_2R_ROOT_CAUSE.json").read_text())
        self.ledger = json.loads((root_cause.OUTPUT_ROOT / "BFE2_2R_EVIDENCE_LEDGER.json").read_text())

    def test_retry_tap6_separates_inflight_from_genuine_reflip(self):
        """The late Q rise must not be hidden by pairing it with an old D rise."""

        retry_normal = next(item for item in self.result["snapshots"] if item["attempt"] == "retry" and item["scenario_id"] == "BFE2L-095-N")
        tap6 = next(item for item in retry_normal["per_tap"] if item["tap"] == 6)
        events = tap6["post_close_event_classification"]
        self.assertEqual(self.result["verdict"]["gate"], "BFE2_2R_ROOT_CAUSE_CONFIRMED")
        self.assertEqual(events[0]["classification"], "normal_in_flight_data_event")
        self.assertLess(abs(events[0]["prediction_error_ps"]), 5.0)
        self.assertEqual(events[1]["classification"], "genuine_post_close_reflip")
        self.assertGreater(events[1]["after_observed_g_close_ps"], events[0]["after_observed_g_close_ps"])

    def test_ledger_preserves_both_attempts_and_true_run_counts(self):
        """Retry evidence is additive and physical HSPICE accounting stays exact."""

        self.assertEqual(self.ledger["this_stage_new_hspice_scenarios"], 0)
        self.assertEqual(self.ledger["executed_new_hspice_scenarios"]["B-FE2.1"], 4)
        self.assertEqual(self.ledger["executed_new_hspice_scenarios"]["B-FE2.2"], 6)
        self.assertEqual(len(self.ledger["first_attempt"]), 4)
        self.assertEqual(len(self.ledger["retry"]), 2)
        for item in self.ledger["first_attempt"] + self.ledger["retry"]:
            self.assertEqual(len(item["deck_sha256"]), 64)
            self.assertEqual(len(item["tr0_sha256"]), 64)
            self.assertEqual(len(item["electrical_signature_id"]), 64)


if __name__ == "__main__":
    unittest.main()
