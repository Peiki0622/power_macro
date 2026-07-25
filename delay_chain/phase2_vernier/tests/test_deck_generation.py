#!/usr/bin/env python3
"""Check generated SPICE topology before expensive HSPICE execution."""

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import generate_vernier_deck  # noqa: E402  # Test the same deck renderer used by runners.


class DeckGenerationTests(unittest.TestCase):
    """Verify differential rail ownership and D/CK connection direction."""

    @classmethod
    def setUpClass(cls):
        """Load the reviewed 765 MHz configuration once for deterministic decks."""

        with (ROOT / "power_macro/delay_chain/phase2_vernier/phase2_config.json").open() as stream:
            cls.config = json.load(stream)

    def test_ideal_deck_keeps_sense_and_reference_rails_distinct(self):
        """Sense stages must not accidentally use the ideal reference rail."""

        deck = generate_vernier_deck.render_ideal_deck(self.config, 8, 1, 1.1)
        self.assertIn("XSENSE_STAGE_000 sense_000 vdd_a vss_a start_sense PHASE2_SENSE_STAGE", deck)
        self.assertIn("XREF_STAGE_000 ref_000 vdd_ref vss_ref start_ref PHASE2_REFERENCE_STAGE_D1", deck)

    def test_dff_deck_uses_sense_as_d_and_reference_as_clock(self):
        """The positional comparator wrapper must implement D=S_i and CK=R_i."""

        deck = generate_vernier_deck.render_dff_deck(self.config, 8, 1, 1.1, 20e-12)
        self.assertIn("XCOMP_000 raw_q_000 vdd_ref vss_ref sense_000 ref_000 sensor_reset PHASE2_COMPARATOR", deck)
        self.assertIn("V_SENSOR_RESET sensor_reset vss_ref", deck)


if __name__ == "__main__":
    unittest.main()
