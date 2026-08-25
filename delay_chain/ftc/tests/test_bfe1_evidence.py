"""Integration checks over the completed four-scenario B-FE1 evidence set.

These tests intentionally inspect the retained run and analysis products
rather than launching HSPICE.  They protect the review contract that B-FE1
conclusions use four complete transistor traces, the planned 92 waveforms per
trace, and the generated zero-HSPICE discrimination result.
"""

import json
import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import bfe1_frontend  # noqa: E402


class Bfe1EvidenceTest(unittest.TestCase):
    """Verify the final B-FE1 run matrix and its auditable derived products."""

    def setUp(self):
        """Locate the single task-owned run root and analysis output root."""

        self.run_root = FTC_ROOT / "runs" / "b_fe_frontend"
        self.analysis_root = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe1_spatial_observability"

    def test_all_four_traces_have_exactly_the_required_waveform_columns(self):
        """Every final trace must retain TIME plus all 92 declared B-FE1 probes.

        This guards the original POST=2 column-limit failure: a present `.tr0`
        is not accepted unless it contains exactly the rail, S_CLK, 30 RVT,
        30 LVT, and 30 XOR waveforms used by the offline snapshot definition.
        """

        expected = ["time", bfe1_frontend.label_for("vdd_monitored"), bfe1_frontend.label_for("s_clk")]
        expected.extend(bfe1_frontend.label_for("rvt_{}".format(index)) for index in range(30))
        expected.extend(bfe1_frontend.label_for("lvt_{}".format(index)) for index in range(30))
        expected.extend(bfe1_frontend.label_for("xor_{}".format(index)) for index in range(30))
        self.assertEqual(len(expected), 93)
        for scenario in bfe1_frontend.SCENARIOS:
            trace_path = bfe1_frontend.scenario_directory(self.run_root, scenario["scenario_id"]) / "bfe1.tr0"
            trace = bfe1_frontend.parse_ascii_tr0(trace_path)
            self.assertEqual(trace["record_width"], 93)
            self.assertEqual(trace["labels"], expected)
            self.assertGreater(trace["record_count"], 2)

    def test_manifest_and_gate_cover_only_the_formal_four_scenarios(self):
        """The evidence must name the four planned conditions and no expanded matrix."""

        manifest = json.loads((self.run_root / "manifest.json").read_text(encoding="utf-8"))
        gate = json.loads((self.analysis_root / "BFE1_GATE_STATUS.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["scenario_count"], 4)
        self.assertEqual([item["scenario_id"] for item in manifest["scenarios"]], [item["scenario_id"] for item in bfe1_frontend.SCENARIOS])
        self.assertTrue(manifest["t0_contract_sha256"])
        self.assertTrue(manifest["t0_cadence_sha256"])
        self.assertEqual(gate["new_hspice_scenarios"], 4)
        self.assertFalse(gate["forbidden_work_performed"])
        self.assertEqual(gate["gate"], "BFE1_SPATIAL_OBSERVABILITY_GO")

    def test_pairwise_results_preserve_all_candidates_and_clean_paths(self):
        """Both formal baselines need positive, interior, non-fragmented evidence."""

        crossings = json.loads((self.analysis_root / "waveform_crossings.json").read_text(encoding="utf-8"))
        pairs = json.loads((self.analysis_root / "normal_l2_pairwise_discrimination.json").read_text(encoding="utf-8"))["pairs"]
        self.assertEqual(len(crossings["scenarios"]), 4)
        for scenario in crossings["scenarios"]:
            self.assertTrue(scenario["rvt_monotonicity"]["strictly_monotonic"])
            self.assertTrue(scenario["lvt_monotonicity"]["strictly_monotonic"])
        self.assertEqual(len(pairs), 2)
        for pair in pairs:
            self.assertTrue(pair["candidate_platforms"])
            self.assertGreater(pair["largest_platform"]["interval_width_ps"], 0.0)
            self.assertFalse(pair["largest_platform"]["normal"]["touches_left"])
            self.assertFalse(pair["largest_platform"]["normal"]["touches_right"])
            self.assertFalse(pair["largest_platform"]["l2"]["touches_left"])
            self.assertFalse(pair["largest_platform"]["l2"]["touches_right"])


if __name__ == "__main__":
    unittest.main()
