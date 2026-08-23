"""Read-only regression checks for the M1 F10 and exact-codebook contracts."""

import json
import unittest
from pathlib import Path


# This file is delay_chain/ftc/tests/<file>; parents[3] is the repository
# root, while parents[2] is only delay_chain and would duplicate that segment.
ROOT = Path(__file__).resolve().parents[3]
M1_ROOT = ROOT / "delay_chain/ftc/controller/m1_detection_margin"


class M1DetectionMarginContractTest(unittest.TestCase):
    """Verify M1-generated data still exactly reflects the frozen M0 scope."""

    @classmethod
    def setUpClass(cls):
        """Load task-owned M1 contracts and their immutable M0 source table."""

        cls.f10 = json.loads((M1_ROOT / "contract/F10_DETECTION_ENCODING_CONTRACT.json").read_text())
        cls.codebook = json.loads((M1_ROOT / "contract/M1_MARGIN_CODEBOOK.json").read_text())
        cls.m0_candidates = json.loads((
            ROOT / "delay_chain/ftc/analysis/m0_detection_margin_characterization/"
            "local_surface/candidate_selection_summary.json"
        ).read_text())

    def test_f10_encoding_is_contiguous_and_detection_only(self):
        """F0..F10 must be unique active-low prefixes, ending in all zeroes."""

        entries = self.f10["entries"]
        self.assertEqual(self.f10["decision"], "GO")
        self.assertEqual([entry["fine_code"] for entry in entries], list(range(11)))
        vectors = [entry["fine_therm_vector_bits_msb_to_lsb"] for entry in entries]
        self.assertEqual(len(vectors), len(set(vectors)))
        self.assertEqual(vectors[0], "1111111111")
        self.assertEqual(vectors[-1], "0000000000")
        self.assertFalse(entries[-1]["calibration_reachable"])
        self.assertTrue(entries[-1]["physical_legal"])
        self.assertTrue(entries[-1]["detection_reachable"])
        for old, new in zip(vectors, vectors[1:]):
            self.assertEqual(sum(a != b for a, b in zip(old, new)), 1)

    def test_all_twelve_entries_exactly_match_m0_candidates(self):
        """M1 may transform vectors but may not alter any M0 codebook code."""

        source = {
            (item["M_cal"], item["F_cal"], item["margin_level"]):
            (item["M_det"], item["F_det"])
            for item in self.m0_candidates["candidates"]
        }
        actual = {
            (item["M_cal"], item["F_cal"], item["margin_level"]):
            (item["M_det"], item["F_det"])
            for item in self.codebook["entries"]
        }
        self.assertEqual(len(actual), 12)
        self.assertEqual(actual, source)

    def test_qualification_scope_and_f10_entries_are_exact(self):
        """Mapping support and trip proof remain deliberately distinct facts."""

        entries = {
            (item["M_cal"], item["F_cal"], item["margin_level"]): item
            for item in self.codebook["entries"]
        }
        for level in ("L0", "L1", "L2", "L3"):
            self.assertFalse(entries[(7, 6, level)]["trip_qualified"])
        self.assertFalse(entries[(4, 6, "L0")]["trip_qualified"])
        self.assertFalse(entries[(2, 9, "L0")]["trip_qualified"])
        for key in ((4, 6, "L1"), (4, 6, "L2"), (4, 6, "L3"),
                    (2, 9, "L1"), (2, 9, "L2"), (2, 9, "L3")):
            self.assertTrue(entries[key]["trip_qualified"])
        self.assertEqual(entries[(2, 9, "L1")]["F_det"], 10)
        self.assertEqual(entries[(2, 9, "L1")]["fine_therm_bits_msb_to_lsb"], "0000000000")
        self.assertEqual(entries[(2, 9, "L3")]["F_det"], 10)
        self.assertEqual(entries[(2, 9, "L3")]["fine_therm_bits_msb_to_lsb"], "0000000000")


if __name__ == "__main__":
    unittest.main()
