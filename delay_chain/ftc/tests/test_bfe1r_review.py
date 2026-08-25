"""Zero-HSPICE regression for the B-FE1R review package."""

import json
import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import review_bfe1r  # noqa: E402


class Bfe1rReviewTest(unittest.TestCase):
    """Check cell evidence, full candidate ranking, and compact provenance."""

    def test_xor_sources_are_equivalent_and_lvt_is_formal_choice(self):
        """Static CDL/Liberty comparison must retain the selected LVT cell."""

        review = review_bfe1r.compare_xor_cells()
        self.assertEqual(review["decision"], "retain_lvt_formal_selection")
        self.assertEqual(review["cells"]["LVT"]["cdl"]["ports"], review["cells"]["RVT"]["cdl"]["ports"])
        self.assertEqual(review["cells"]["LVT"]["cdl"]["device_count"], 10)
        self.assertEqual(review["cells"]["RVT"]["cdl"]["device_count"], 10)
        self.assertEqual(review["cells"]["LVT"]["cdl"]["lengths"], ["4e-08"])
        self.assertEqual(review["cells"]["RVT"]["cdl"]["lengths"], ["4e-08"])
        self.assertEqual(review["cells"]["LVT"]["cdl"]["models"], ["nlvt11ll_ckt", "plvt11ll_ckt"])
        self.assertEqual(review["cells"]["RVT"]["cdl"]["models"], ["n11ll_ckt", "p11ll_ckt"])
        self.assertGreater(review["input_capacitance_mean_delta_percent"], 0.0)
        self.assertIn("A|negative_unate", review["timing_mean_delta_percent_lvt_vs_rvt"])

    def test_reparse_ranks_all_candidates_and_finds_095_central_priority(self):
        """The review must retain all 134 candidates and prefer a central 0.95-V window."""

        pairwise = review_bfe1r.read_json(review_bfe1r.PAIRWISE_JSON)
        review = review_bfe1r.review_candidates(pairwise)
        self.assertEqual([item["candidate_count"] for item in review["pairs"]], [65, 69])
        first = review["pairs"][0]
        self.assertTrue(first["central_region_beats_previous_report_largest"])
        self.assertTrue(first["priority_candidates"][0]["central_tap_region"])
        self.assertGreater(first["priority_candidates"][0]["minimum_headroom_taps"], first["previous_report_largest_platform"]["minimum_headroom_taps"])

    def test_evidence_manifest_has_four_scenarios_and_no_trace_copy(self):
        """Only compact SHA/metadata evidence is allowed in the review output."""

        evidence = review_bfe1r.read_json(review_bfe1r.EVIDENCE_JSON)
        self.assertEqual(evidence["scenario_evidence"]["hspice_scenario_count"], 4)
        self.assertFalse(evidence["large_tr0_copied"])
        for scenario in evidence["scenario_evidence"]["scenarios"]:
            self.assertEqual(scenario["record_width"], 93)
            self.assertTrue(len(scenario["deck_sha256"]) == 64)
            self.assertTrue(len(scenario["tr0_sha256"]) == 64)
        self.assertEqual(evidence["scenario_evidence"]["scenarios"][1]["authority_scenario_key"], "t0_5a_0p95_l2_long")
        self.assertEqual(len(evidence["generated_review_artifact_sha256"]["BFE1R_REVIEW_STATUS.json"]), 64)


if __name__ == "__main__":
    unittest.main()
