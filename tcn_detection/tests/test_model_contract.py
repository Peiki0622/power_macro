#!/usr/bin/env python3
"""Unit contracts for causal TCN, train-only normalization, and event logic."""

from __future__ import print_function

import unittest

import numpy as np
import torch

from power_macro.tcn_detection.dataset.model_data import WindowTable, apply_normalizer, fit_normalizer
from power_macro.tcn_detection.evaluate.metrics import confirmed_alarm_indices, risk_events
from power_macro.tcn_detection.models.tcn1d import TCN1D
from power_macro.tcn_detection.models.threshold_baseline import calibrate_thresholds


class ModelContractTests(unittest.TestCase):
    """Exercise contracts that do not need HSPICE or a long model run."""

    def test_tcn_future_mutation_cannot_change_past_sequence_logits(self):
        """Left-only causal padding must isolate all outputs through time t."""

        torch.manual_seed(11)
        model = TCN1D(dropout=0.0)
        model.eval()
        original = torch.randn(2, 5, 16)
        changed = original.clone()
        changed[:, :, 9:] += 123.0
        with torch.no_grad():
            original_logits = model.forward_sequence(original)
            changed_logits = model.forward_sequence(changed)
        self.assertTrue(torch.equal(original_logits[:, :, :9], changed_logits[:, :, :9]))

    def test_normalizer_is_fit_from_train_table_only(self):
        """Adding extreme validation values must not alter frozen train statistics."""

        train = WindowTable(np.zeros((3, 5, 8), dtype=np.float32), np.array([0, 1, 2]), tuple({} for _ in range(3)), 8)
        validation = WindowTable(np.full((1, 5, 8), 999.0, dtype=np.float32), np.array([2]), ({},), 8)
        normalizer = fit_normalizer(train)
        transformed = apply_normalizer(validation, normalizer)
        self.assertEqual(normalizer["mean"], [0.0] * 5)
        self.assertTrue(np.all(transformed.features == 999.0))

    def test_threshold_calibration_never_requires_test_features(self):
        """The calibration API accepts only validation features and labels."""

        features = np.zeros((6, 5, 8), dtype=np.float32)
        features[:, 0, -1] = np.arange(6)
        result = calibrate_thresholds(features, np.array([0, 0, 1, 1, 2, 2]), "sensor_code")
        self.assertEqual(result["rule"], "sensor_code")
        self.assertLessEqual(result["warning_threshold"], result["critical_threshold"])

    def test_confirmation_requires_consecutive_non_safe_predictions(self):
        """An isolated Warning does not trigger K=3, while a three-sample run does."""

        sequence = list(enumerate([0, 1, 0, 2, 1, 2, 0, 1, 1, 1]))
        self.assertEqual(confirmed_alarm_indices(sequence, 3), [5, 9])

    def test_risk_events_recover_exact_first_violation_from_future_offset(self):
        """Event lead time must use raw Critical future offset, not label endpoint alone."""

        rows = [{"label_eligible": "True", "hysteresis_label": "0", "sample_index": "0", "raw_label": "0", "time_to_violation_samples": ""},
                {"label_eligible": "True", "hysteresis_label": "1", "sample_index": "1", "raw_label": "1", "time_to_violation_samples": ""},
                {"label_eligible": "True", "hysteresis_label": "2", "sample_index": "2", "raw_label": "2", "time_to_violation_samples": "3"},
                {"label_eligible": "True", "hysteresis_label": "0", "sample_index": "3", "raw_label": "0", "time_to_violation_samples": ""}]
        self.assertEqual(risk_events(rows), [{"start_index": 1, "end_index": 2, "first_violation_index": 5, "critical": True}])


if __name__ == "__main__":
    unittest.main()
