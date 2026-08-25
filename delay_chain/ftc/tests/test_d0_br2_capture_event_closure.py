"""Regression checks for the zero-HSPICE BR2 event/legalizer screen."""

import json
import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_d0_br2_capture_event_closure as br2  # noqa: E402


class D0BR2CaptureEventTests(unittest.TestCase):
    """Keep the shared-sensor GO distinct from a fixed-delay legalizer block."""

    def test_all_retained_events_leave_no_fixed_falling_delay_intersection(self):
        """A legalizer must satisfy every E0/E1, not a favourite target."""

        br1r = json.loads((FTC_ROOT / "analysis/d0_interleaved_capture/br1r_fall_retiming/retiming_search_contract.json").read_text())
        rows = br2.retained_events(br1r)
        self.assertEqual(len(rows), 12)
        self.assertAlmostEqual(max(row["extension_min_for_ck_high_ps"] for row in rows), 743.391464)
        self.assertAlmostEqual(min(row["extension_max_for_next_ck_low_ps"] for row in rows), 544.622663)
        self.assertGreater(max(row["extension_min_for_ck_high_ps"] for row in rows),
                           min(row["extension_max_for_next_ck_low_ps"] for row in rows))

    def test_published_primary_preserves_xor_before_medium_event_causality(self):
        """The direct polarity form is not allowed to launch CK before D=xor."""

        artifact = json.loads((FTC_ROOT / "analysis/d0_interleaved_capture/br2_capture_event_legalizer/br2_static_closure.json").read_text())
        selector = artifact["direction_selector"]
        self.assertEqual(selector["primary"], "xor_29_and_lvt_29_with_AND2_X0P5M_A9TR40")
        self.assertIn("before xor_29", selector["candidate_a_direct_polarity"]["rejected_reason"])
        self.assertEqual(artifact["decision"], "CAPTURE_EVENT_ARCHITECTURE_BLOCKED")
        self.assertEqual(artifact["shared_sensor_conclusion"], "PRESERVED_RETIMING_GO_NOT_PHYSICALLY_BLOCKED")
        self.assertEqual(artifact["simulation_accounting"]["new_hspice_scenarios"], 0)
        self.assertTrue(artifact["capture_context"]["continuous_overwrite"]["selected_semantics"])
        self.assertFalse(artifact["capture_context"]["per_probe_reset"]["selected_semantics"])


if __name__ == "__main__":
    unittest.main()
