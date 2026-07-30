#!/usr/bin/env python3
"""Unit contracts for causal TCN, train-only normalization, and event logic."""

from __future__ import print_function

import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from power_macro.tcn_detection.dataset.model_data import (WindowTable, apply_normalizer, fit_normalizer,
                                                          load_window_table)
from power_macro.tcn_detection.dataset.add_time_buckets import time_bucket_from_offset
from power_macro.tcn_detection.evaluate.metrics import confirmed_alarm_indices, risk_events, window_metrics
from power_macro.tcn_detection.evaluate.binary_metrics import (binary_event_metrics,
                                                               binary_window_metrics)
from power_macro.tcn_detection.evaluate.binary_postprocess import (
    apply_detector as apply_binary_detector)
from power_macro.tcn_detection.evaluate.frozen_binary_state_evaluation import (
    prediction_rows as frozen_binary_prediction_rows,
    validate_checkpoint as validate_frozen_binary_checkpoint)
from power_macro.tcn_detection.evaluate.compare_frozen_binary_iid import (
    paired_disagreements as binary_paired_disagreements)
from power_macro.tcn_detection.evaluate.postprocess import apply_detector, causal_filter
from power_macro.tcn_detection.evaluate.state_metrics import state_event_metrics
from power_macro.tcn_detection.evaluate.summarize_ablation import rank_arms
from power_macro.tcn_detection.evaluate.tune_state_postprocess import make_trace_folds
from power_macro.tcn_detection.models.tcn1d import TCN1D
from power_macro.tcn_detection.models.ordinal_tcn1d import OrdinalTCN1D, OrdinalTimeTCN1D
from power_macro.tcn_detection.models.threshold_baseline import calibrate_thresholds
from power_macro.tcn_detection.train.launch_parallel_training import aggregate_status, command_matrix
from power_macro.tcn_detection.train.common import (OrdinalRiskCriticalLoss, OrdinalTimeLoss,
                                                     class_weights,
                                                     configure_training_objective, make_loader)
from power_macro.tcn_detection.train.train_binary_classifier import (
    checkpoint_metrics as binary_checkpoint_metrics)
from power_macro.tcn_detection.train.train_classifier import save_checkpoint_atomic, validation_checkpoint_metrics


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

    def test_one_channel_state_tcns_preserve_shape_and_causality(self):
        """Code-only direct and ordinal TCNs must accept exactly [N,1,L]."""

        torch.manual_seed(19)
        original = torch.randn(2, 1, 32)
        changed = original.clone()
        changed[:, :, 20:] += 91.0
        for model, output_channels in ((TCN1D(input_channels=1, dropout=0.0), 3),
                                       (OrdinalTCN1D(input_channels=1, dropout=0.0), 2)):
            model.eval()
            with torch.no_grad():
                first = model.forward_sequence(original)
                second = model.forward_sequence(changed)
            self.assertEqual(tuple(first.shape), (2, output_channels, 32))
            self.assertTrue(torch.equal(first[:, :, :20], second[:, :, :20]))

    def test_binary_tcn_preserves_two_logit_shape_and_causality(self):
        """Safe/Critical TCN must expose exactly two causal output channels."""

        torch.manual_seed(29)
        model = TCN1D(input_channels=1, class_count=2, dropout=0.0)
        model.eval()
        original = torch.randn(2, 1, 32)
        changed = original.clone()
        changed[:, :, 21:] += 50.0
        with torch.no_grad():
            first = model.forward_sequence(original)
            second = model.forward_sequence(changed)
        self.assertEqual(tuple(first.shape), (2, 2, 32))
        self.assertTrue(torch.equal(first[:, :, :21], second[:, :, :21]))

    def test_one_channel_window_loader_and_normalizer_are_shape_generic(self):
        """The data/model boundary must retain state_code_v1's sole channel."""

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "windows_L8.csv"
            fields = ["window_id", "trace_id", "split", "end_index", "target_label",
                      "length", "feature_channels", "features_json"]
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for index in range(6):
                    writer.writerow({"window_id": "w{}".format(index), "trace_id": "t",
                                     "split": "train", "end_index": index + 7,
                                     "target_label": index % 3, "length": 8,
                                     "feature_channels": 1,
                                     "features_json": json.dumps([[float(index)]] * 8)})
            table = load_window_table(path)
            self.assertEqual(table.features.shape, (6, 1, 8))
            normalizer = fit_normalizer(table)
            normalized = apply_normalizer(table, normalizer)
            self.assertEqual(normalized.features.shape, (6, 1, 8))

    def test_ordinal_tcn_is_causal_and_maps_nested_probabilities(self):
        """Ordinal heads must remain causal and yield a valid three-class simplex."""

        torch.manual_seed(13)
        model = OrdinalTCN1D(dropout=0.0)
        model.eval()
        original = torch.randn(2, 5, 16)
        changed = original.clone()
        changed[:, :, 10:] -= 77.0
        with torch.no_grad():
            first = model.forward_sequence(original)
            second = model.forward_sequence(changed)
            probabilities = model.probabilities_from_logits(torch.tensor([[0.0, 2.0], [2.0, -2.0]]))
        self.assertTrue(torch.equal(first[:, :, :10], second[:, :, :10]))
        self.assertTrue(torch.all(probabilities >= 0.0))
        self.assertTrue(torch.allclose(probabilities.sum(dim=1), torch.ones(2)))
        self.assertTrue(torch.all(probabilities[:, 2] <= probabilities[:, 1] + probabilities[:, 2]))

    def test_ordinal_loss_matches_two_bces_and_consistency_penalty(self):
        """The implementation must exactly match the approved ordinal formula."""

        logits = torch.tensor([[0.0, 1.0], [2.0, -1.0], [-2.0, 2.0]], dtype=torch.float32)
        targets = torch.tensor([0, 1, 2], dtype=torch.int64)
        criterion = OrdinalRiskCriticalLoss(consistency_weight=0.1)
        risk_truth = torch.tensor([0.0, 1.0, 1.0])
        critical_truth = torch.tensor([0.0, 0.0, 1.0])
        heads = torch.sigmoid(logits)
        expected = (torch.nn.functional.binary_cross_entropy_with_logits(logits[:, 0], risk_truth)
                    + torch.nn.functional.binary_cross_entropy_with_logits(logits[:, 1], critical_truth)
                    + 0.1 * torch.relu(heads[:, 1] - heads[:, 0]).pow(2).mean())
        self.assertTrue(torch.allclose(criterion(logits, targets), expected))

    def test_ordinal_positive_weights_use_clipped_sqrt_imbalance(self):
        """Natural ordinal training resolves separate Risk and Critical weights."""

        labels = np.asarray([0] * 90 + [1] * 8 + [2] * 2, dtype=np.int64)
        config = {"sampling_strategy": "natural", "loss_type": "ordinal_bce",
                  "class_weight_strategy": "none",
                  "ordinal_positive_weight_strategy": "sqrt_negative_positive"}
        sampler, shuffle, _, strategy = configure_training_objective(labels, config, 7)
        self.assertIsNone(sampler)
        self.assertTrue(shuffle)
        self.assertAlmostEqual(strategy["resolved_ordinal_positive_weights"][0], 3.0)
        self.assertEqual(strategy["resolved_ordinal_positive_weights"][1], 4.0)
        invalid = dict(config, sampling_strategy="weighted_sampler",
                       train_class_ratio={"0": 0.5, "1": 0.25, "2": 0.25})
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            configure_training_objective(labels, invalid, 7)

    def test_direct_state_objectives_remain_cross_entropy(self):
        """Adding ordinal compensation must not replace either direct CE arm."""

        labels = np.asarray([0] * 90 + [1] * 8 + [2] * 2, dtype=np.int64)
        for weight_strategy in ("none", "sqrt_inverse"):
            config = {"sampling_strategy": "natural",
                      "loss_type": "cross_entropy",
                      "class_weight_strategy": weight_strategy}
            _, _, criterion, strategy = configure_training_objective(labels, config, 11)
            self.assertIsInstance(criterion, torch.nn.CrossEntropyLoss)
            self.assertEqual(strategy["loss_type"], "cross_entropy")

    def test_binary_sqrt_weights_use_two_class_formula(self):
        """Binary compensation must not retain the former three-class divisor."""

        labels = np.asarray([0] * 94 + [1] * 6, dtype=np.int64)
        weights = class_weights(labels, "sqrt_inverse", class_ids=(0, 1))
        raw = np.sqrt(100.0 / (2.0 * np.asarray([94.0, 6.0])))
        raw = np.clip(raw, 0.5, 2.0)
        expected = raw / raw.mean()
        self.assertTrue(np.allclose(weights, expected))
        config = {"sampling_strategy": "natural", "loss_type": "ordinal_bce",
                  "class_weight_strategy": "none",
                  "ordinal_positive_weight_strategy": "none"}
        with self.assertRaisesRegex(ValueError, "three-state"):
            configure_training_objective(labels, config, 3, class_ids=(0, 1))

    def test_binary_metrics_cover_probability_and_operating_point_quality(self):
        """Binary reports must expose Critical AP, calibration, MCC, and FAR."""

        labels = np.asarray([0, 0, 1, 1], dtype=np.int64)
        probabilities = np.asarray([[0.9, 0.1], [0.4, 0.6],
                                    [0.7, 0.3], [0.1, 0.9]])
        predictions = probabilities.argmax(axis=1)
        report = binary_window_metrics(labels, predictions, probabilities)
        self.assertEqual(report["confusion_matrix"], [[1, 1], [1, 1]])
        self.assertAlmostEqual(report["safe_window_false_alarm_rate"], 0.5)
        self.assertAlmostEqual(report["critical_false_negative_rate"], 0.5)
        self.assertIn("critical_pr_auc", report)
        self.assertIn("binary_brier_score", report)
        self.assertIn("ece", report["calibration"])
        checkpoint = binary_checkpoint_metrics(labels, probabilities)
        self.assertEqual(checkpoint["checkpoint_selection_metric"], "critical_pr_auc")
        self.assertEqual(checkpoint["checkpoint_score"], report["critical_pr_auc"])

    def test_binary_events_use_only_critical_truth_intervals(self):
        """Warning-merged truth must measure delay from actual Critical onset."""

        truth = [0, 0, 1, 1, 0, 0]
        prediction = [0, 1, 0, 1, 1, 0]
        rows = [{"trace_id": "trace_binary", "end_index": index,
                 "target_label": target, "prediction": predicted}
                for index, (target, predicted) in enumerate(zip(truth, prediction))]
        report = binary_event_metrics(rows)
        self.assertEqual(report["critical_event_count"], 1)
        self.assertEqual(report["critical_event_detection_rate"], 1.0)
        self.assertEqual(report["median_critical_delay_ns"], 4.0)
        self.assertEqual(report["false_alarm_episodes"], 1)
        self.assertEqual(report["mean_recovery_delay_samples"], 1.0)

    def test_binary_detector_is_causal_and_resets_each_trace(self):
        """Future scores and a previous trace cannot alter an earlier decision."""

        rows = []
        for trace_id, scores in (("a", (0.9, 0.9, 0.9)),
                                 ("b", (0.1, 0.1, 0.1))):
            for index, score in enumerate(scores):
                rows.append({"window_id": "{}_{}".format(trace_id, index),
                             "trace_id": trace_id, "split": "validation",
                             "end_index": index, "target_label": 0,
                             "prediction": int(score >= 0.5),
                             "prob_safe": 1.0 - score,
                             "prob_critical": score})
        config = {"filter": {"kind": "ewma", "alpha": 0.5, "window": 1},
                  "critical_on": 0.6, "critical_off": 0.3,
                  "k_on": 2, "k_off": 2}
        processed = apply_binary_detector(rows, config)
        by_id = {(row["trace_id"], row["end_index"]): row for row in processed}
        self.assertEqual(by_id[("a", 1)]["prediction"], 1)
        self.assertEqual(by_id[("b", 0)]["prediction"], 0)
        self.assertAlmostEqual(by_id[("b", 0)]["filtered_critical_score"], 0.1)

        changed = [dict(row) for row in rows]
        changed[2]["prob_critical"] = 0.0
        changed[2]["prob_safe"] = 1.0
        changed_rows = apply_binary_detector(changed, config)
        original_prefix = [row["prediction"] for row in processed
                           if row["trace_id"] == "a" and row["end_index"] < 2]
        changed_prefix = [row["prediction"] for row in changed_rows
                          if row["trace_id"] == "a" and row["end_index"] < 2]
        self.assertEqual(original_prefix, changed_prefix)

    def test_frozen_binary_evaluator_enforces_mapping_and_checkpoint_schema(self):
        """One-shot IID code must reject label drift and non-binary checkpoints."""

        # Construct a minimal metadata-only view matching the released mapping:
        # former Warning is binary Safe, whereas former Critical is binary
        # Critical.  Feature values are irrelevant to this evidence-join helper
        # but a correctly shaped WindowTable keeps the test contract realistic.
        metadata = (
            {"window_id": "warning", "trace_id": "t", "split": "iid_test",
             "end_index": "31", "target_label": "0", "source_state_label": "1"},
            {"window_id": "critical", "trace_id": "t", "split": "iid_test",
             "end_index": "32", "target_label": "1", "source_state_label": "2"},
        )
        table = WindowTable(np.zeros((2, 1, 32), dtype=np.float32),
                            np.asarray([0, 1]), metadata, 32)
        probabilities = np.asarray([[0.8, 0.2], [0.1, 0.9]])
        rows = frozen_binary_prediction_rows(table, probabilities)
        self.assertEqual([row["source_state_label"] for row in rows], [1, 2])
        self.assertEqual([row["prediction"] for row in rows], [0, 1])

        invalid_metadata = (dict(metadata[0], target_label="1"), metadata[1])
        invalid_table = WindowTable(table.features, table.labels,
                                    invalid_metadata, table.length)
        with self.assertRaisesRegex(ValueError, "mapping changed"):
            frozen_binary_prediction_rows(invalid_table, probabilities)

        model_config = {"class_count": 2,
                        "class_names": {"0": "Safe", "1": "Critical"}}
        candidate = {"window_length": 32, "seed": 7}
        checkpoint = {
            "task": "safe_critical_binary", "model": "tcn",
            "model_config": model_config, "window_length": 32, "seed": 7,
            "normalizer": {"source_split": "train", "window_length": 32},
        }
        validate_frozen_binary_checkpoint(checkpoint, candidate, model_config)
        with self.assertRaisesRegex(ValueError, "two-class"):
            validate_frozen_binary_checkpoint(
                dict(checkpoint, task="three_class"), candidate, model_config)

    def test_binary_comparison_counts_paired_direction_and_correctness(self):
        """Paired reporting must distinguish which frozen model wins each row."""

        keys = [("trace", index) for index in range(4)]
        truth = [0, 0, 1, 1]
        old_predictions = [0, 1, 0, 1]
        binary_predictions = [0, 0, 1, 0]
        old_rows = {key: {"target_label": target, "raw_prediction": prediction}
                    for key, target, prediction in zip(keys, truth, old_predictions)}
        binary_rows = {
            key: {"target_label": target, "raw_prediction": prediction}
            for key, target, prediction in zip(keys, truth, binary_predictions)}
        counts = binary_paired_disagreements(
            old_rows, binary_rows, keys, "raw_prediction")
        self.assertEqual(counts["agreement"], 1)
        self.assertEqual(counts["disagreement"], 3)
        self.assertEqual(counts["old_safe_binary_critical"], 1)
        self.assertEqual(counts["old_critical_binary_safe"], 2)
        self.assertEqual(counts["old_only_correct"], 1)
        self.assertEqual(counts["binary_only_correct"], 2)

    def test_ordinal_time_loss_adds_weighted_auxiliary_cross_entropy(self):
        """Time supervision must use class*4+bucket decoding and planned weights."""

        logits = torch.tensor([[0.0, 1.0, 2.0, 0.0, -1.0, -2.0],
                               [1.0, -1.0, -2.0, -1.0, 0.0, 2.0]], dtype=torch.float32)
        encoded = torch.tensor([0 * 4 + 0, 2 * 4 + 3], dtype=torch.int64)
        criterion = OrdinalTimeLoss(consistency_weight=0.1, auxiliary_weight=0.5,
                                    bucket_weights=(1.0, 1.0, 1.5, 2.0))
        ordinal = OrdinalRiskCriticalLoss(0.1)(logits[:, :2], torch.tensor([0, 2]))
        time = torch.nn.functional.cross_entropy(logits[:, 2:6], torch.tensor([0, 3]), reduction="none")
        expected = ordinal + 0.5 * (time * torch.tensor([1.0, 2.0])).mean()
        self.assertTrue(torch.allclose(criterion(logits, encoded), expected))

        probabilities = OrdinalTimeTCN1D.probabilities_from_logits(logits)
        self.assertEqual(tuple(probabilities.shape), (2, 3))
        self.assertTrue(torch.allclose(probabilities.sum(dim=1), torch.ones(2)))

    def test_normalizer_is_fit_from_train_table_only(self):
        """Adding extreme validation values must not alter frozen train statistics."""

        train = WindowTable(np.zeros((3, 5, 8), dtype=np.float32), np.array([0, 1, 2]), tuple({} for _ in range(3)), 8)
        validation = WindowTable(np.full((1, 5, 8), 999.0, dtype=np.float32), np.array([2]), ({},), 8)
        normalizer = fit_normalizer(train)
        transformed = apply_normalizer(validation, normalizer)
        self.assertEqual(normalizer["mean"], [0.0] * 5)
        self.assertTrue(np.all(transformed.features == 999.0))

    def test_time_bucket_mapping_covers_exact_label_horizon(self):
        """Auxiliary buckets must partition none and offsets 1..8 exactly."""

        self.assertEqual(time_bucket_from_offset(""), 0)
        self.assertEqual([time_bucket_from_offset(str(value)) for value in range(1, 9)],
                         [1, 1, 2, 2, 3, 3, 3, 3])
        with self.assertRaisesRegex(ValueError, "outside"):
            time_bucket_from_offset("9")

    def test_training_split_filter_skips_frozen_feature_deserialization(self):
        """Malformed IID/OOD features must be invisible to the training loader.

        This is stronger than checking the returned split names: an invalid
        test payload proves that filtering happens before ``features_json`` is
        parsed.  The unfiltered compatibility path must still reject the same
        malformed row, preserving strict whole-dataset audit behavior.
        """

        with tempfile.TemporaryDirectory() as temporary:
            window_path = Path(temporary) / "windows_L8.csv"
            fields = ["window_id", "split", "length", "target_label", "features_json"]
            valid_features = json.dumps([[float(channel) for channel in range(5)] for _ in range(8)])
            rows = [
                {"window_id": "train_0", "split": "train", "length": "8", "target_label": "0",
                 "features_json": valid_features},
                {"window_id": "validation_0", "split": "validation", "length": "8", "target_label": "1",
                 "features_json": valid_features},
                # Deliberately invalid JSON represents a frozen feature tensor
                # that a training process is neither allowed nor required to
                # deserialize.  Its metadata remains structurally sufficient
                # for the split decision made by the streaming loader.
                {"window_id": "iid_0", "split": "iid_test", "length": "8", "target_label": "2",
                 "features_json": "not-json"},
            ]
            with window_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

            filtered = load_window_table(window_path, splits={"train", "validation"})
            self.assertEqual(filtered.features.shape, (2, 5, 8))
            self.assertEqual([row["split"] for row in filtered.metadata], ["train", "validation"])
            with self.assertRaisesRegex(ValueError, "invalid features_json"):
                load_window_table(window_path)

    def test_parallel_command_matrix_preserves_default_and_tcn_subset(self):
        """The enhanced launcher remains compatible while allowing TCN-only runs."""

        args = SimpleNamespace(training_config=Path("training.json"), model_config=Path("model.json"),
                               windows_dir=Path("windows"), label_dir=Path("labels"))
        default_names = [name for name, _ in command_matrix(args)]
        selected_names = [name for name, _ in command_matrix(args, ("tcn_L8", "tcn_L16", "tcn_L32"))]
        self.assertEqual(default_names, ["cae_L16", "cnn_L16", "tcn_L8", "tcn_L16", "tcn_L32"])
        self.assertEqual(selected_names, ["tcn_L8", "tcn_L16", "tcn_L32"])

        # Duplicate or misspelled jobs must fail before the immutable output
        # directory can contain an ambiguous process manifest.
        with self.assertRaisesRegex(ValueError, "duplicates"):
            command_matrix(args, ("tcn_L8", "tcn_L8"))
        with self.assertRaisesRegex(ValueError, "unknown training jobs"):
            command_matrix(args, ("tcn_L64",))

    def test_parallel_manifest_status_transitions_are_conservative(self):
        """Aggregate PASS/FAIL is published only after every child terminates."""

        self.assertEqual(aggregate_status([{"status": "PENDING"}, {"status": "PENDING"}]), "RUNNING")
        self.assertEqual(aggregate_status([{"status": "PASS"}, {"status": "RUNNING"}]), "RUNNING")
        self.assertEqual(aggregate_status([{"status": "PASS"}, {"status": "FAIL"}]), "FAIL")
        self.assertEqual(aggregate_status([{"status": "PASS"}, {"status": "PASS"}]), "PASS")

    def test_checkpoint_publish_is_atomic_and_loadable(self):
        """A successful save exposes one loadable checkpoint and no temp file."""

        with tempfile.TemporaryDirectory() as temporary:
            checkpoint_path = Path(temporary) / "best_checkpoint.pt"
            payload = {"epoch": 3, "state_dict": {"weight": torch.arange(4)}}
            save_checkpoint_atomic(payload, checkpoint_path)
            restored = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
            self.assertEqual(restored["epoch"], 3)
            self.assertTrue(torch.equal(restored["state_dict"]["weight"], payload["state_dict"]["weight"]))
            self.assertFalse(checkpoint_path.with_suffix(".pt.tmp").exists())

    def test_v2_training_strategies_are_explicit_and_nonduplicative(self):
        """All planned objectives construct, while duplicate compensation fails."""

        labels = np.asarray([0] * 12 + [1] * 4 + [2] * 6, dtype=np.int64)
        common = {"focal_gamma": 2.0, "train_class_ratio": {"0": 0.55, "1": 0.20, "2": 0.25}}
        strategies = [
            {"sampling_strategy": "natural", "loss_type": "cross_entropy", "class_weight_strategy": "none"},
            {"sampling_strategy": "natural", "loss_type": "focal", "class_weight_strategy": "none"},
            {"sampling_strategy": "natural", "loss_type": "cross_entropy", "class_weight_strategy": "sqrt_inverse"},
            {"sampling_strategy": "weighted_sampler", "loss_type": "cross_entropy", "class_weight_strategy": "none"},
        ]
        for strategy in strategies:
            sampler, shuffle, criterion, metadata = configure_training_objective(
                labels, {**common, **strategy}, seed=17)
            self.assertEqual(metadata["sampling_strategy"], strategy["sampling_strategy"])
            self.assertEqual(shuffle, strategy["sampling_strategy"] == "natural")
            self.assertEqual(sampler is None, strategy["sampling_strategy"] == "natural")
            self.assertIsNotNone(criterion)
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            configure_training_objective(labels, {**common, "sampling_strategy": "weighted_sampler",
                                                   "loss_type": "focal",
                                                   "class_weight_strategy": "sqrt_inverse"}, seed=17)

    def test_natural_shuffle_is_reproducible_from_explicit_seed(self):
        """Natural-distribution batches must repeat exactly for the same seed."""

        features = np.arange(20 * 5 * 8, dtype=np.float32).reshape(20, 5, 8)
        labels = np.arange(20, dtype=np.int64) % 3
        first = [targets.tolist() for _, targets in make_loader(features, labels, 4, shuffle=True, seed=23)]
        second = [targets.tolist() for _, targets in make_loader(features, labels, 4, shuffle=True, seed=23)]
        self.assertEqual(first, second)

    def test_weighted_pr_auc_checkpoint_score_uses_configured_class_priority(self):
        """The v2 score must equal the declared Safe/Warning/Critical mixture.

        This synthetic case intentionally gives the three one-vs-rest rankings
        different quality.  Recomputing the scalar from persisted components
        proves that Critical receives 50%, Safe 30%, and Warning 20%, rather
        than accidentally selecting an epoch by Macro-F1 or class order.
        """

        labels = np.asarray([0, 0, 1, 1, 2, 2], dtype=np.int64)
        probabilities = np.asarray([
            [0.90, 0.05, 0.05], [0.35, 0.55, 0.10],
            [0.40, 0.50, 0.10], [0.10, 0.75, 0.15],
            [0.20, 0.10, 0.70], [0.05, 0.60, 0.35],
        ])
        metrics = validation_checkpoint_metrics(
            labels, probabilities, {"0": 0.30, "1": 0.20, "2": 0.50})
        expected = (0.30 * metrics["validation_pr_auc_safe"]
                    + 0.20 * metrics["validation_pr_auc_warning"]
                    + 0.50 * metrics["validation_pr_auc_critical"])
        self.assertEqual(metrics["checkpoint_selection_metric"], "weighted_ovr_pr_auc")
        self.assertAlmostEqual(metrics["checkpoint_score"], expected)
        self.assertNotAlmostEqual(metrics["checkpoint_score"], metrics["validation_macro_f1"])

    def test_checkpoint_metric_weights_reject_ambiguous_configuration(self):
        """Missing classes and non-unit sums must fail before training starts."""

        labels = np.asarray([0, 0, 1, 1, 2, 2], dtype=np.int64)
        probabilities = np.eye(3, dtype=np.float64)[labels]
        with self.assertRaisesRegex(ValueError, "exactly classes"):
            validation_checkpoint_metrics(labels, probabilities, {"0": 0.5, "2": 0.5})
        with self.assertRaisesRegex(ValueError, "sum to one"):
            validation_checkpoint_metrics(labels, probabilities, {"0": 0.3, "1": 0.3, "2": 0.3})

    def test_ablation_ranking_applies_documented_tie_breaks(self):
        """Equal median scores must favor robust Critical recall before variance."""

        common = {"median_checkpoint_score": 0.7, "median_safe_recall": 0.8,
                  "median_macro_f1": 0.6, "checkpoint_score_variance": 0.01}
        aggregates = {
            "strong_critical": {**common, "worst_seed_critical_recall": 0.55},
            "low_variance": {**common, "worst_seed_critical_recall": 0.50,
                             "checkpoint_score_variance": 0.001},
            "lower_score": {**common, "median_checkpoint_score": 0.69,
                            "worst_seed_critical_recall": 0.90},
        }
        self.assertEqual(rank_arms(aggregates), ["strong_critical", "low_variance", "lower_score"])

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

    def test_comprehensive_window_metrics_use_fixed_three_class_semantics(self):
        """Classification and probability scores must use the documented formulas."""

        labels = np.asarray([0, 0, 1, 1, 2, 2])
        predictions = np.asarray([0, 1, 1, 1, 0, 2])
        probabilities = np.asarray([[0.8, 0.1, 0.1], [0.2, 0.7, 0.1],
                                    [0.1, 0.8, 0.1], [0.1, 0.7, 0.2],
                                    [0.6, 0.1, 0.3], [0.1, 0.2, 0.7]])
        report = window_metrics(labels, predictions, probabilities)
        self.assertAlmostEqual(report["accuracy"], 4.0 / 6.0)
        self.assertAlmostEqual(report["balanced_accuracy"], 4.0 / 6.0)
        self.assertAlmostEqual(report["safe_window_false_alarm_rate"], 0.5)
        self.assertAlmostEqual(report["critical_recall"], 0.5)
        self.assertEqual(report["confusion_matrix"], [[1, 1, 0], [0, 2, 0], [1, 0, 1]])
        self.assertEqual(report["per_class"]["2"]["support"], 2)
        self.assertTrue(0.0 <= report["macro_pr_auc_ovr"] <= 1.0)
        self.assertTrue(0.0 <= report["macro_roc_auc_ovr"] <= 1.0)
        self.assertGreaterEqual(report["log_loss"], 0.0)
        self.assertGreaterEqual(report["multiclass_brier_score"], 0.0)

    def test_causal_filters_cannot_observe_future_scores(self):
        """Changing future probabilities must leave every preceding output exact."""

        original = np.asarray([0.1, 0.3, 0.2, 0.8, 0.7, 0.4])
        changed = original.copy()
        changed[4:] = 1.0
        for kind, options in (("mean", {"window": 3}), ("median", {"window": 3}),
                              ("ewma", {"alpha": 0.5})):
            first = causal_filter(original, kind, **options)
            second = causal_filter(changed, kind, **options)
            self.assertTrue(np.array_equal(first[:4], second[:4]))

    def test_state_postprocess_folds_preserve_transitive_components(self):
        """Base and hard-pair links must remain closed across tuning folds."""

        trace_ids = ["t{}".format(index) for index in range(10)]
        prediction_rows = []
        for trace_id in trace_ids:
            # Two chronological Safe rows are sufficient for fold stratum
            # construction; features and probabilities are irrelevant here.
            prediction_rows.extend([
                {"trace_id": trace_id, "end_index": "0", "target_label": 0},
                {"trace_id": trace_id, "end_index": "1", "target_label": 0},
            ])
        corpus_rows = []
        for index, trace_id in enumerate(trace_ids):
            corpus_rows.append({
                "trace_id": trace_id,
                "split": "validation",
                # t0--t1 share a base, while t1--t2 share a hard-pair.  The
                # mixed-link chain must close into one three-trace component.
                "base_waveform_id": ("base_chain" if index in (0, 1)
                                     else "base_{}".format(index)),
                "hard_pair_id": "pair_chain" if index in (1, 2) else "",
            })
        folds, components = make_trace_folds(prediction_rows, corpus_rows, fold_count=5)
        fold_by_trace = {trace_id: fold_index for fold_index, fold in enumerate(folds)
                         for trace_id in fold}
        self.assertEqual(len(fold_by_trace), len(trace_ids))
        self.assertEqual({fold_by_trace[trace_id] for trace_id in ("t0", "t1", "t2")},
                         {fold_by_trace["t0"]})
        self.assertIn(["t0", "t1", "t2"],
                      [component["trace_ids"] for component in components])

    def test_postprocess_resets_filter_and_detector_state_per_trace(self):
        """A preceding active trace cannot cause the next trace to start alarmed."""

        rows = []
        for trace_id, risks in (("a", (0.9, 0.9, 0.9)), ("b", (0.1, 0.1, 0.1))):
            for index, risk in enumerate(risks):
                rows.append({"window_id": "{}_{}".format(trace_id, index), "trace_id": trace_id,
                             "split": "validation", "end_index": index, "target_label": 0,
                             "prediction": int(risk >= 0.5), "prob_safe": 1.0 - risk,
                             "prob_warning": risk, "prob_critical": 0.0})
        config = {"filter": {"kind": "ewma", "alpha": 0.5, "window": 1},
                  "risk_on": 0.6, "risk_off": 0.3, "critical_on": 0.7,
                  "critical_off": 0.6, "k_on": 2, "k_off": 2}
        processed = apply_detector(rows, config)
        by_id = {(row["trace_id"], row["end_index"]): row for row in processed}
        self.assertEqual(by_id[("a", 1)]["prediction"], 1)
        self.assertEqual(by_id[("b", 0)]["prediction"], 0)
        self.assertAlmostEqual(by_id[("b", 0)]["filtered_risk_score"], 0.1)

    def test_risk_events_recover_exact_first_violation_from_future_offset(self):
        """Event lead time must use raw Critical future offset, not label endpoint alone."""

        rows = [{"label_eligible": "True", "hysteresis_label": "0", "sample_index": "0", "raw_label": "0", "time_to_violation_samples": ""},
                {"label_eligible": "True", "hysteresis_label": "1", "sample_index": "1", "raw_label": "1", "time_to_violation_samples": ""},
                {"label_eligible": "True", "hysteresis_label": "2", "sample_index": "2", "raw_label": "2", "time_to_violation_samples": "3"},
                {"label_eligible": "True", "hysteresis_label": "0", "sample_index": "3", "raw_label": "0", "time_to_violation_samples": ""}]
        self.assertEqual(risk_events(rows), [{"start_index": 1, "end_index": 2, "first_violation_index": 5, "critical": True}])

    def test_current_state_events_measure_delay_false_alarm_and_recovery(self):
        """Present-state metrics must not reuse future-prediction lead semantics."""

        truth = [0, 1, 1, 2, 2, 0, 0, 0]
        prediction = [1, 0, 1, 1, 2, 1, 0, 0]
        rows = [{"trace_id": "trace_state", "end_index": index,
                 "target_label": target, "prediction": predicted}
                for index, (target, predicted) in enumerate(zip(truth, prediction))]
        report = state_event_metrics(rows)
        self.assertEqual(report["risk_event_count"], 1)
        self.assertEqual(report["critical_event_count"], 1)
        self.assertEqual(report["risk_event_detection_rate"], 1.0)
        self.assertEqual(report["critical_event_detection_rate"], 1.0)
        self.assertEqual(report["median_risk_delay_ns"], 4.0)
        self.assertEqual(report["median_critical_delay_ns"], 4.0)
        self.assertEqual(report["false_alarm_episodes"], 1)
        self.assertEqual(report["mean_recovery_delay_samples"], 1.0)


if __name__ == "__main__":
    unittest.main()
