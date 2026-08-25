"""Static B-FE2.1 deck tests; these tests never start HSPICE."""

import json
import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import bfe2_latch_load  # noqa: E402


class Bfe2LatchLoadTest(unittest.TestCase):
    """Protect the exact 30-real-latch transparent-load topology."""

    def test_each_authorized_deck_has_only_transparent_latch_loads(self):
        """Every formal case must keep G high and omit legacy capture logic."""

        cells = json.loads((FTC_ROOT / "discovery" / "selected_cells.json").read_text())
        for scenario in bfe2_latch_load.SCENARIOS:
            deck = bfe2_latch_load.render_deck(cells, scenario)
            bfe2_latch_load.validate_static_deck(deck)
            self.assertEqual(deck.count("XXOR_"), 30)
            self.assertEqual(deck.count("XLATCH_"), 30)
            self.assertNotIn("DFFRPQ", deck)
            self.assertIn("V_LATCH_G latch_g vss_a DC='VDD_VALUE'", deck)

    def test_signature_changes_with_electrical_droop_condition(self):
        """Normal and L2 cannot share a signature merely because VDD is equal."""

        cells = json.loads((FTC_ROOT / "discovery" / "selected_cells.json").read_text())
        normal = bfe2_latch_load.electrical_signature(cells, bfe2_latch_load.SCENARIOS[0], "W-2024.09")
        l2 = bfe2_latch_load.electrical_signature(cells, bfe2_latch_load.SCENARIOS[1], "W-2024.09")
        self.assertNotEqual(bfe2_latch_load.signature_id(normal), bfe2_latch_load.signature_id(l2))
        self.assertEqual(normal["g_pwl"], "constant high from t=0 through stop")


if __name__ == "__main__":
    unittest.main()
