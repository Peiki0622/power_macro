"""Pure-logic tests for Stage-1B candidate ranking helpers."""

from __future__ import print_function

import unittest

from power_macro.tcn_detection.bnn.evaluate_nofc import (
    _representative_seed,
    _selection_key,
)


class BnnEvaluationContractTests(unittest.TestCase):
    """Lock the frozen ordering rule before running any real selection."""

    def test_selection_key_prefers_low_far_then_high_recall_then_low_p95(self):
        """The comparator must rank a FAR-qualified higher-recall candidate first."""

        better = _selection_key({"safe_window_false_alarm_rate": 0.02,
                                 "matthews_correlation_coefficient": 0.90},
                                {"event_recall": 0.95, "p95_ttd_ns": 2.0}, 8, 3)
        worse = _selection_key({"safe_window_false_alarm_rate": 0.06,
                                "matthews_correlation_coefficient": 0.99},
                               {"event_recall": 1.0, "p95_ttd_ns": 0.0}, 8, 1)
        self.assertLess(better, worse)

    def test_representative_seed_tracks_median_pr_auc(self):
        """The chosen seed should sit closest to the median validation PR-AUC."""

        candidate = _representative_seed([
            {"seed": 11, "window": {"critical_pr_auc": 0.8,
                                      "matthews_correlation_coefficient": 0.6},
             "events": {"p95_ttd_ns": 4.0}},
            {"seed": 22, "window": {"critical_pr_auc": 0.9,
                                      "matthews_correlation_coefficient": 0.7},
             "events": {"p95_ttd_ns": 3.0}},
            {"seed": 33, "window": {"critical_pr_auc": 1.0,
                                      "matthews_correlation_coefficient": 0.5},
             "events": {"p95_ttd_ns": 2.0}},
        ])
        self.assertEqual(candidate["seed"], 22)


if __name__ == "__main__":
    unittest.main()
