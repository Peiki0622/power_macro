"""Pure-Python decision tests for B-FE2.1 real-latch-load analysis."""

import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_bfe2_latch_load as analysis  # noqa: E402


def scenario(monotonic=True):
    """Build the minimal propagation diagnostic required by the Gate helper."""

    return {"rvt_monotonicity": {"strictly_monotonic": monotonic}, "lvt_monotonicity": {"strictly_monotonic": monotonic}}


class AnalyzeBfe2LatchLoadTest(unittest.TestCase):
    """Verify that the load screen cannot promote incomplete physical evidence."""

    def test_go_requires_two_clean_pairs_and_monotonic_paths(self):
        """Both formal baselines must pass before B-FE2.2 is allowed."""

        gate = analysis.decide_gate([{"candidate_platforms": [object()]}, {"candidate_platforms": [object()]}], [scenario(), scenario()])
        self.assertEqual(gate["gate"], "BFE2_1_LATCH_LOAD_GO")

    def test_missing_pair_is_conditional_or_blocked_not_go(self):
        """A single surviving baseline cannot silently authorize real close tests."""

        gate = analysis.decide_gate([{"candidate_platforms": [object()]}, {"candidate_platforms": []}], [scenario(), scenario()])
        self.assertEqual(gate["gate"], "BFE2_1_LATCH_LOAD_CONDITIONAL")
        gate = analysis.decide_gate([{"candidate_platforms": []}, {"candidate_platforms": []}], [scenario(), scenario(False)])
        self.assertEqual(gate["gate"], "BFE2_1_LATCH_LOAD_BLOCKED")

    def test_gate_reports_physical_runs_separately_from_offline_analysis(self):
        """A zero-HSPICE parser invocation must not erase the four source runs."""

        gate = analysis.decide_gate([{"candidate_platforms": [object()]}, {"candidate_platforms": [object()]}], [scenario(), scenario()])
        self.assertEqual(gate["executed_new_hspice_scenarios"], 4)
        self.assertEqual(gate["this_analysis_new_hspice_scenarios"], 0)


if __name__ == "__main__":
    unittest.main()
