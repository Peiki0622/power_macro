"""Pure-data contracts for the reference sensitivity-contrast study.

These tests deliberately do not invoke HSPICE.  They protect the candidate
manifest, deck topology, frozen sensor lookup, residual arithmetic and gate
ordering; the separate full runner invocation remains the electrical proof.
"""

import json
import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_reference_sensitivity_contrast as study  # noqa: E402


class ReferenceSensitivityContrastTest(unittest.TestCase):
    """Protect the minimum physical and analysis contracts without simulation."""

    @classmethod
    def setUpClass(cls):
        """Load immutable discovery/config inputs once for deterministic tests."""

        cls.cells = json.loads((FTC_ROOT / "discovery" / "selected_cells.json").read_text(encoding="utf-8"))
        cls.config = json.loads((FTC_ROOT / "ftc_config.json").read_text(encoding="utf-8"))
        cls.config["source_files"] = cls.cells["source_files"]
        cls.candidates = study.make_candidates(cls.cells)

    def test_discovery_returns_small_noninverting_set(self):
        """Actual installed views produce one lowest-drive family/Vt candidate."""

        self.assertEqual(len(self.candidates), 10)
        self.assertTrue(all(item["overall_polarity"] == "non_inverting" for item in self.candidates))
        self.assertEqual(
            {item["logic_family"] for item in self.candidates},
            {"BUF", "MUX", "INV", "NAND2", "NOR2"},
        )
        self.assertEqual(
            {item["stage_count"] for item in self.candidates if item["logic_family"] in ("INV", "NAND2", "NOR2")},
            {2},
        )

    def test_reference_deck_has_three_units_and_middle_delay_measures(self):
        """The generated deck measures the middle unit, not a synthetic load."""

        text = study.render_deck(self.config, self.candidates[0], 1.10, "tt", 25.0)
        self.assertEqual(text.count("Xbuf_rvt_u"), 3)
        self.assertEqual(text.count(".measure tran d_ref"), 1)
        self.assertIn("unit1_input_cross", text)
        self.assertIn("unit1_output_cross", text)
        self.assertNotIn("VREF", text.upper())
        self.assertNotIn("VDD_REF", text.upper())

    def test_mixed_vt_composite_includes_both_real_cdls(self):
        """A mixed macro retains every source view required by its stages."""

        left = self.candidates[0]
        right = next(item for item in self.candidates if item["candidate_id"] == "inv_lvt")
        composite = dict(left)
        composite.update({
            "candidate_id": "comp_test",
            "candidate_kind": "composite",
            "stages": left["stages"] + right["stages"],
            "stage_count": 3,
            "source_cdls": sorted(set(left["source_cdls"] + right["source_cdls"])),
        })
        text = study.render_deck(self.config, composite, 1.10, "tt", 25.0)
        self.assertIn(self.cells["source_files"]["rvt_cdl"], text)
        self.assertIn(self.cells["source_files"]["lvt_cdl"], text)
        self.assertEqual(text.count("Xcomp_test_u"), 9)

    def test_frozen_sensor_evidence_is_complete_and_reused(self):
        """All required sensor dimensions are available without a new deck."""

        sensor = study.validate_sensor_evidence()
        self.assertEqual(len(sensor["fine"]), 36)
        self.assertEqual(len(sensor["temperature"]), 12)
        self.assertEqual(len(sensor["pvt"]), 36)
        self.assertEqual(sensor["baseline_summary"]["measured_tap"], 29)

    def test_shortlist_requires_both_local_workpoints(self):
        """A positive margin at only one V0 cannot enter PVT confirmation."""

        rows = [
            {"candidate_id": "a", "v0_v": 1.10, "m_100_ps": 2.0, "m_50_ps": 1.0, "sign_e_v_100mv": 1},
            {"candidate_id": "a", "v0_v": 0.90, "m_100_ps": -1.0, "m_50_ps": 1.0, "sign_e_v_100mv": 1},
            {"candidate_id": "b", "v0_v": 1.10, "m_100_ps": 3.0, "m_50_ps": 1.0, "sign_e_v_100mv": 1},
            {"candidate_id": "b", "v0_v": 0.90, "m_100_ps": 4.0, "m_50_ps": 2.0, "sign_e_v_100mv": -1},
        ]
        self.assertEqual(study.shortlist(rows), ["b"])


if __name__ == "__main__":
    unittest.main()
