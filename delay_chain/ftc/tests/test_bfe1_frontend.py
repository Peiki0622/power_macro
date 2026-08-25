"""Static B-FE1 deck tests; no HSPICE is started by this module."""

import json
import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import bfe1_frontend  # noqa: E402


class Bfe1FrontendTest(unittest.TestCase):
    """Check topology, port contracts, and the four-scenario budget."""

    def setUp(self):
        self.cells = json.loads((FTC_ROOT / "discovery/selected_cells.json").read_text())

    def test_each_deck_has_only_the_new_xor_load(self):
        """Every deck has 30 TL40 XORs and no capture/control structure."""

        for scenario in bfe1_frontend.SCENARIOS:
            deck = bfe1_frontend.render_deck(self.cells, scenario)
            bfe1_frontend.validate_static_deck(deck)
            self.assertEqual(deck.count("XXOR_"), 30)
            self.assertNotIn("DFFRPQ", deck)
            self.assertNotIn("LATQ", deck)
            self.assertNotIn("capture_ck", deck)

    def test_probe_contains_all_92_required_waveforms(self):
        """Time, rail, S_CLK, 30+30 taps, and 30 XOR nodes are all probed."""

        deck = bfe1_frontend.render_deck(self.cells, bfe1_frontend.SCENARIOS[0])
        probe = next(line for line in deck.splitlines() if line.startswith(".probe tran"))
        self.assertEqual(len(probe.split()) - 2, 92)
        for node in ("vdd_monitored", "s_clk", "rvt_0", "rvt_29", "lvt_0", "lvt_29", "xor_0", "xor_29"):
            self.assertIn("v({0})".format(node), probe)
        self.assertIn(".option post=2 probe", deck)

    def test_l2_waveform_uses_formal_representative_phases(self):
        """Only the two authority-validated representative L2 points are used."""

        l2 = [item for item in bfe1_frontend.SCENARIOS if item["droop_v"] is not None]
        self.assertEqual([(item["baseline_v"], item["droop_v"], item["phase_ps"]) for item in l2], [(0.95, 0.86, 75.0), (1.10, 0.96, 25.0)])
        self.assertEqual([item["authority_scenario_key"] for item in l2], ["t0_5a_0p95_l2_long", "t0_5a_1p10_l2_long"])

    def test_single_rising_sclk_is_pwl(self):
        """The S_CLK source has one transition and no falling edge."""

        deck = bfe1_frontend.render_deck(self.cells, bfe1_frontend.SCENARIOS[0])
        source = next(line for line in deck.splitlines() if line.startswith("V_SCLK"))
        self.assertIn("PWL", source)
        self.assertNotIn("PULSE", source)
        self.assertEqual(source.count("'VDD_VALUE'"), 2)


if __name__ == "__main__":
    unittest.main()
