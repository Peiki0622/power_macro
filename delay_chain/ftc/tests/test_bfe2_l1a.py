"""Static and evidence-contract tests for the bounded B-FE2-L1A stage.

These tests never invoke HSPICE.  They protect the fixed two-scenario input,
the safe-domain power boundary, the real latch identity, and the explicit
stop condition that prevents an L1A artifact from authorizing later stages.
"""

import json
import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_bfe2_l1a as l1a  # noqa: E402


class Bfe2L1aContractTest(unittest.TestCase):
    """Check L1A source, topology, and Gate contracts without simulation."""

    def test_inputs_are_exactly_the_frozen_bfe2c_pair(self):
        entries = l1a.validate_inputs()
        self.assertEqual([item["scenario_id"] for item in entries], list(l1a.SCENARIO_IDS))
        self.assertEqual(l1a.FIXED_CLOSE_PS, 534.524618567)
        self.assertTrue(all(float(item["baseline_v"]) == 0.95 for item in entries))
        self.assertEqual(float(entries[1]["droop_v"]), 0.86)

    def test_rendered_deck_has_real_safe_domain_latches_only(self):
        entries = l1a.validate_inputs()
        config = l1a.read_json(l1a.CONFIG_PATH)
        cells = l1a.read_json(l1a.CELLS_PATH)
        deck = l1a.render_deck(entries[0], config["model_library"], cells)
        l1a.validate_deck(deck)
        net = "\n".join(line.split("*", 1)[0] for line in deck.splitlines())
        self.assertEqual(net.count("XLATCH_"), 30)
        self.assertEqual(net.count("LATQ_X0P5M_A9TR40"), 30)
        self.assertEqual(net.count("V_LATCH_G latch_g vss_safe PWL"), 1)
        self.assertNotIn("VDD_MONITORED", net)
        self.assertNotIn("DFF", net.upper())
        self.assertEqual(net.count("safe_d_"), 90)  # source + LATQ D pin + probe per tap

    def test_pwl_threshold_restoration_is_full_swing_and_zero_delay(self):
        times = [0.0, 1.0, 2.0, 3.0]
        values = [0.0, 0.0, 0.95, 0.95]
        rail = [0.95, 0.95, 0.95, 0.95]
        self.assertEqual(l1a.binary_pwl(times, values, rail, 0.95), [(0.0, 0.0), (1.5, 0.95), (3.0, 0.95)])

    def test_published_gate_cannot_authorize_next_stage(self):
        root = l1a.L1A_ROOT
        if not (root / "BFE2_L1A_ANALYSIS.json").is_file():
            self.skipTest("physical L1A evidence not generated yet")
        analysis = json.loads((root / "BFE2_L1A_ANALYSIS.json").read_text())
        self.assertTrue(analysis["stop_after_l1a"])
        self.assertFalse(analysis["next_stage_authorized"])


if __name__ == "__main__":
    unittest.main()
