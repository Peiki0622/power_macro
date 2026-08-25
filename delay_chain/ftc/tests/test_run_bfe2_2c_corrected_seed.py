"""Static contract tests for the bounded B-FE2.2C corrected-seed runner.

These tests deliberately do not invoke ``main`` or HSPICE.  They validate the
authorization and deck-shape guards that must pass before a physical run, so a
future refactor cannot accidentally turn the one-pair experiment into a close
time sweep or a second corrected seed.
"""

import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import bfe2_latch_load  # noqa: E402
import bfe2_real_snapshot  # noqa: E402
import run_bfe2_2c_corrected_seed as corrected  # noqa: E402


class Bfe22cCorrectedSeedTest(unittest.TestCase):
    """Check the fixed B-FE2.2C input and topology contract."""

    def test_gate_and_seed_are_ready_and_unique(self):
        """Only the committed READY seed and its positive-width interval qualify."""

        self.assertEqual(corrected.corrected_seed_close_ps(), corrected.EXPECTED_CLOSE_PS)
        selected = corrected.scenarios()
        self.assertEqual([item["scenario_id"] for item in selected], list(corrected.EXPECTED_SCENARIO_IDS))
        self.assertEqual(len(selected), 2)
        self.assertTrue(all(float(item["baseline_v"]) == 0.95 for item in selected))
        self.assertEqual(selected[0]["droop_v"], None)
        self.assertEqual(selected[1]["droop_v"], 0.86)

    def test_rendered_deck_preserves_30_latch_topology_and_common_close(self):
        """The corrected pair retains the audited 30-XOR/30-LATQ topology."""

        cells = corrected.read_json(FTC_ROOT / "discovery" / "selected_cells.json")
        scenario = corrected.scenarios()[0]
        deck = bfe2_real_snapshot.render(cells, scenario, corrected.EXPECTED_CLOSE_PS)
        bfe2_real_snapshot.validate(deck)
        netlist = "\n".join(line.split("*", 1)[0] for line in deck.splitlines())
        self.assertEqual(netlist.count("XLATCH_"), 30)
        self.assertEqual(netlist.count("XXOR_"), 30)
        self.assertIn("V_LATCH_G latch_g vss_a PWL", netlist)
        self.assertNotIn("DFF", netlist.upper())
        self.assertNotIn("M/F", netlist)

    def test_electrical_signature_contains_corrected_close_and_source_facts(self):
        """Duplicate detection includes the close and all physical signature fields."""

        cells = corrected.read_json(FTC_ROOT / "discovery" / "selected_cells.json")
        scenario = bfe2_latch_load.SCENARIOS[0]
        signature = corrected.electrical_signature(cells, scenario, corrected.EXPECTED_CLOSE_PS, "W-2024.09")
        self.assertEqual(signature["observable_taps"], 30)
        self.assertEqual(signature["rvt_initial_stages"], 4)
        self.assertEqual(signature["lvt_initial_stages"], 0)
        self.assertEqual(signature["requested_close_ps"], corrected.EXPECTED_CLOSE_PS)
        self.assertIn("model_sha256", signature)
        self.assertEqual(len(corrected.signature_id(signature)), 64)


if __name__ == "__main__":
    unittest.main()
