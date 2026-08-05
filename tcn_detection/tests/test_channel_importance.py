#!/usr/bin/env python3
"""Step 3 contracts for deterministic Critical-aware channel scores."""

from __future__ import print_function

import unittest

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

from power_macro.tcn_detection.compression.channel_importance import (
    compute_conv3_statistic_audit, compute_taylor_scores, critical_aware_scores,
    filter_norm_scores, rank_channels)
from power_macro.tcn_detection.models.cnn1d import CNN1D


class ChannelImportanceTests(unittest.TestCase):
    """Ensure scores are complete, finite, class-aware, and order-stable."""

    def _loader(self, order):
        torch.manual_seed(31)
        inputs = torch.randn(12, 1, 32)
        labels = torch.tensor([0, 1] * 6, dtype=torch.long)
        dataset = TensorDataset(inputs[order], labels[order])
        return DataLoader(dataset, batch_size=3, shuffle=False)

    def _model(self):
        torch.manual_seed(32)
        model = CNN1D(input_channels=1, class_count=2, channels=[4, 4, 4],
                      kernel_sizes=[5, 5, 5], dropout=0.0,
                      pooling_contract="multistat_average_max_endpoint")
        model.eval()
        return model

    def test_taylor_is_complete_finite_and_order_invariant(self):
        """Repeating with reversed sample order must preserve every score."""

        model = self._model()
        first = compute_taylor_scores(model, self._loader(torch.arange(12)))
        second = compute_taylor_scores(model, self._loader(torch.arange(11, -1, -1)))
        for key in ("safe_raw", "critical_raw", "safe", "critical", "final"):
            for left, right in zip(first[key], second[key]):
                self.assertTrue(np.array_equal(left, right), key)
                self.assertTrue(np.all(np.isfinite(left)), key)
        self.assertEqual(first["sample_counts"], {"safe": 6, "critical": 6})
        self.assertTrue(all(np.sum(value) > 0.0 for value in first["safe_raw"]))
        self.assertTrue(all(np.sum(value) > 0.0 for value in first["critical_raw"]))
        self.assertEqual([len(value) for value in first["final"]], [4, 4, 4])

    def test_critical_aware_score_is_elementwise_max_after_normalization(self):
        """The fixed synthesis rule protects a class-specific high scorer."""

        result = critical_aware_scores([np.array([1.0, 2.0]), np.array([0.0, 4.0])],
                                       [np.array([3.0, 1.0]), np.array([2.0, 0.0])])
        np.testing.assert_array_equal(result["safe"][0], [0.5, 1.0])
        np.testing.assert_array_equal(result["critical"][0], [1.0, 1.0 / 3.0])
        np.testing.assert_array_equal(result["final"][0], [1.0, 1.0])

    def test_filter_norms_and_statistic_audit_cover_all_conv3_branches(self):
        """Audit methods expose all channels and Average/Maximum/Endpoint."""

        model = self._model()
        norms = filter_norm_scores(model)
        self.assertEqual([len(values) for values in norms["l1"]], [4, 4, 4])
        self.assertEqual([len(values) for values in norms["l2"]], [4, 4, 4])
        audit = compute_conv3_statistic_audit(model, self._loader(torch.arange(12)))
        self.assertEqual(set(audit["0"]), {"average_feature", "maximum_feature", "endpoint_feature"})
        self.assertEqual(set(audit["1"]), {"average_feature", "maximum_feature", "endpoint_feature"})
        for class_report in audit.values():
            for values in class_report.values():
                self.assertEqual(values.shape, (4,))
                self.assertTrue(np.all(np.isfinite(values)))

    def test_rank_channels_has_stable_index_tie_break(self):
        """Equal scores are ordered by original channel index."""

        self.assertEqual(rank_channels([np.array([2.0, 1.0, 1.0])]), [[1, 2, 0]])


if __name__ == "__main__":
    unittest.main()
