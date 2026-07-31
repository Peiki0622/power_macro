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
from power_macro.tcn_detection.evaluate.summarize_binary_cnn_screen import (
    select_candidate as select_binary_cnn_candidate)
from power_macro.tcn_detection.evaluate.summarize_binary_cnn_objectives import (
    rank_arms as rank_binary_cnn_arms)
from power_macro.tcn_detection.evaluate.summarize_binary_cnn_hparam_search import (
    rank_arms as rank_binary_cnn_hparam_arms)
from power_macro.tcn_detection.evaluate.summarize_binary_cnn_structure_search import (
    rank_candidates as rank_binary_cnn_structures)
from power_macro.tcn_detection.evaluate.freeze_binary_cnn_candidate import (
    select_representative as select_binary_cnn_representative)
from power_macro.tcn_detection.evaluate.frozen_binary_cnn_evaluation import (
    validate_checkpoint as validate_frozen_binary_cnn_checkpoint)
from power_macro.tcn_detection.evaluate.finalize_binary_cnn_hparam_search import (
    feasibility as binary_cnn_hparam_feasibility)
from power_macro.tcn_detection.evaluate.postprocess import apply_detector, causal_filter
from power_macro.tcn_detection.evaluate.state_metrics import state_event_metrics
from power_macro.tcn_detection.evaluate.summarize_ablation import rank_arms
from power_macro.tcn_detection.evaluate.tune_state_postprocess import make_trace_folds
from power_macro.tcn_detection.models.tcn1d import TCN1D
from power_macro.tcn_detection.models.cnn1d import CNN1D
from power_macro.tcn_detection.models.ordinal_tcn1d import OrdinalTCN1D, OrdinalTimeTCN1D
from power_macro.tcn_detection.models.threshold_baseline import calibrate_thresholds
from power_macro.tcn_detection.train.launch_parallel_training import aggregate_status, command_matrix
from power_macro.tcn_detection.train.launch_binary_cnn_screen import (
    build_jobs as build_binary_cnn_screen_jobs)
from power_macro.tcn_detection.train.launch_binary_cnn_hparam_search import (
    build_jobs as build_binary_cnn_hparam_jobs)
from power_macro.tcn_detection.train.launch_binary_cnn_structure_search import (
    build_jobs as build_binary_cnn_structure_jobs)
from power_macro.tcn_detection.train.common import (OrdinalRiskCriticalLoss, OrdinalTimeLoss,
                                                      class_weights,
                                                     configure_training_objective, estimate_macs,
                                                     make_loader, parameter_count)
from power_macro.tcn_detection.train.train_binary_classifier import (
    checkpoint_metrics as binary_checkpoint_metrics,
    validate_binary_model_config)
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

    def test_binary_cnn_candidates_have_stable_shapes_and_lower_complexity(self):
        """Every planned CNN length is two-class and cheaper than the TCN.

        The exact parameter/MAC values are checked at L32 so a future change to
        channel widths, pooling, or kernel accounting cannot silently invalidate
        the Pareto-selection assumptions encoded in the experiment contract.
        """

        tcn_config = {"input_channels": 1, "class_count": 2,
                      "hidden_channels": 16, "kernel_size": 3,
                      "dilations": [1, 2, 4], "dropout": 0.1}
        tcn = TCN1D(**tcn_config)
        tcn_macs = estimate_macs(tcn, 32, 1)
        tcn_parameters = parameter_count(tcn)
        expected = {
            "small": ([8, 8], 250, 6928),
            "medium": ([8, 8, 8], 450, 13072),
            "large": ([16, 16, 16], 1666, 50720),
        }
        for name, (channels, parameters, macs) in expected.items():
            # CNN1D names its width argument ``channels``; keeping this
            # explicit in the test makes the versioned JSON-to-constructor
            # translation visible instead of relying on a hidden adapter.
            model = CNN1D(input_channels=1, class_count=2, channels=channels,
                          kernel_size=3, dropout=0.1)
            self.assertEqual(parameter_count(model), parameters)
            self.assertEqual(estimate_macs(model, 32, 1), macs)
            self.assertLess(macs, tcn_macs)
            self.assertLess(parameters, tcn_parameters)
            for length in (8, 16, 32):
                with torch.no_grad():
                    logits = model(torch.zeros(2, 1, length))
                self.assertEqual(tuple(logits.shape), (2, 2))

    def test_binary_cnn_structure_variants_preserve_shape_causality_and_budget(self):
        """Endpoint and multistat variants must remain cheaper than the TCN.

        Exact complexity values bind the implemented graph to the reviewed
        search contract.  The feature-prefix assertion separately proves that
        a causal endpoint candidate cannot leak a later sample into an earlier
        hidden position, even though deployment consumes only the final one.
        """

        variants = {
            "multistat_k3": ({"channels": [16, 16, 16], "kernel_size": 3,
                                "pooling_contract": "multistat_average_max_endpoint"},
                               1730, 50784),
            "multistat_k5": ({"channels": [16, 16, 16], "kernel_size": 5,
                                "pooling_contract": "multistat_average_max_endpoint"},
                               2786, 84576),
            "dilated_k3": ({"channels": [16, 16, 16, 16], "kernel_size": 3,
                              "pooling_contract": "causal_endpoint",
                              "dilations": [1, 2, 4, 8]}, 2450, 75296),
            "dilated_k5": ({"channels": [16, 16, 16], "kernel_size": 5,
                              "pooling_contract": "causal_endpoint",
                              "dilations": [1, 2, 4]}, 2722, 84512),
            "dilated_w24": ({"channels": [24, 24, 24], "kernel_size": 3,
                               "pooling_contract": "causal_endpoint",
                               "dilations": [1, 2, 4]}, 3650, 112944),
        }
        for name, (config, parameters, macs) in variants.items():
            model = CNN1D(input_channels=1, class_count=2, dropout=0.1, **config)
            with torch.no_grad():
                logits = model(torch.zeros(2, 1, 32))
            self.assertEqual(tuple(logits.shape), (2, 2), name)
            self.assertEqual(parameter_count(model), parameters, name)
            self.assertEqual(estimate_macs(model, 32, 1), macs, name)
            self.assertLess(parameters, 4050, name)
            self.assertLess(macs, 125952, name)
        causal = CNN1D(input_channels=1, class_count=2, channels=[16] * 4,
                       kernel_size=3, dropout=0.0,
                       pooling_contract="causal_endpoint",
                       dilations=[1, 2, 4, 8])
        causal.eval()
        original = torch.randn(1, 1, 32)
        changed = original.clone()
        changed[:, :, 20:] += 100.0
        with torch.no_grad():
            first = causal.features(original)
            second = causal.features(changed)
        self.assertTrue(torch.equal(first[:, :, :20], second[:, :, :20]))

    def test_binary_cnn_structure_ranking_prefers_feasible_quality(self):
        """A feasible structure must outrank a higher-AP recall failure."""

        def candidate(name, feasible, ap, recall, macs):
            return {"name": name, "feasible": feasible,
                    "median_critical_pr_auc": ap, "median_macro_f1": 0.93,
                    "worst_critical_recall": recall,
                    "median_balanced_accuracy": 0.96,
                    "median_safe_far": 0.02,
                    "estimated_macs_per_window": macs}

        ranking = rank_binary_cnn_structures([
            candidate("fragile", False, 0.90, 0.80, 50000),
            candidate("feasible", True, 0.86, 0.96, 90000),
        ])
        self.assertEqual(ranking[0]["name"], "feasible")

    def test_binary_model_config_rejects_wrong_family_contract(self):
        """CNN training must fail closed on legacy three-class configurations."""

        valid = {"input_channels": 1, "class_count": 2,
                 "class_names": {"0": "Safe", "1": "Critical"},
                 "feature_contract": "normalized_sensor_code_only",
                 "target_contract": "warning_merged_into_safe",
                 "cnn_channels": [8, 8],
                 "pooling_contract": "adaptive_average_over_past_window"}
        validate_binary_model_config("cnn", valid)
        with self.assertRaisesRegex(ValueError, "one-channel"):
            validate_binary_model_config("cnn", dict(valid, input_channels=5))
        with self.assertRaisesRegex(ValueError, "two-class"):
            validate_binary_model_config("cnn", dict(valid, class_count=3))
        with self.assertRaisesRegex(ValueError, "pooling contract"):
            validate_binary_model_config("cnn", dict(valid, pooling_contract="none"))

    def test_frozen_binary_cnn_checkpoint_contract_rejects_family_and_normalizer_drift(self):
        """One-shot CNN evaluation must fail closed before reading IID windows.

        The positive case mirrors the frozen release schema.  The two negative
        cases cover the highest-risk substitutions: loading a TCN checkpoint
        through the CNN command and accepting normalization fitted outside the
        training partition.
        """

        model_config = {
            "input_channels": 1, "class_count": 2,
            "class_names": {"0": "Safe", "1": "Critical"},
            "feature_contract": "normalized_sensor_code_only",
            "target_contract": "warning_merged_into_safe",
            "cnn_channels": [16, 16, 16],
        }
        candidate = {"window_length": 32, "seed": 20260725}
        checkpoint = {
            "task": "safe_critical_binary", "model": "cnn",
            "model_config": model_config, "window_length": 32,
            "seed": 20260725,
            "normalizer": {"source_split": "train", "window_length": 32,
                           "mean": [0.12], "std": [0.29]},
        }
        validate_frozen_binary_cnn_checkpoint(
            checkpoint, candidate, model_config)
        with self.assertRaisesRegex(ValueError, "binary CNN"):
            validate_frozen_binary_cnn_checkpoint(
                dict(checkpoint, model="tcn"), candidate, model_config)
        invalid_normalizer = dict(checkpoint)
        invalid_normalizer["normalizer"] = dict(
            checkpoint["normalizer"], source_split="validation")
        with self.assertRaisesRegex(ValueError, "train-only"):
            validate_frozen_binary_cnn_checkpoint(
                invalid_normalizer, candidate, model_config)

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

    def test_binary_cnn_selection_uses_frozen_feasible_and_fallback_orders(self):
        """CNN selection must prefer low MAC only after quality feasibility."""

        def candidate(name, macs, pr_auc, feasible, recall=0.96, far=0.02):
            return {"name": name, "estimated_macs_per_window": macs,
                    "parameter_count": macs // 10,
                    "median_cpu_latency_ms": macs / 100000.0,
                    "median_critical_pr_auc": pr_auc,
                    "worst_seed_critical_recall": recall,
                    "median_safe_window_false_alarm_rate": far,
                    "feasible": feasible}

        candidates = [candidate("small", 1000, 0.85, True),
                      candidate("large", 5000, 0.91, True)]
        selected, mode = select_binary_cnn_candidate(candidates)
        self.assertEqual(selected["name"], "small")
        self.assertEqual(mode, "lowest_complexity_within_quality_floor")

        fallback = [candidate("small", 1000, 0.80, False),
                    candidate("large", 5000, 0.83, False)]
        selected, mode = select_binary_cnn_candidate(fallback)
        self.assertEqual(selected["name"], "large")
        self.assertEqual(mode, "mandatory_cnn_quality_fallback")

    def test_binary_cnn_objective_ranking_prefers_feasible_then_quality(self):
        """Objective selection must never rank an infeasible high AP arm first."""

        def arm(ap, feasible, macro=0.9, balanced=0.95, recall=0.96, far=0.02):
            return {"median_critical_pr_auc": ap, "median_macro_f1": macro,
                    "median_balanced_accuracy": balanced,
                    "worst_seed_critical_recall": recall,
                    "median_safe_window_false_alarm_rate": far,
                    "feasible": feasible}

        arms = {"a": arm(0.91, False), "b": arm(0.86, True),
                "c": arm(0.85, True)}
        ranking, mode = rank_binary_cnn_arms(arms)
        self.assertEqual(ranking[0], "b")
        self.assertEqual(mode, "quality_feasible_arm")
        fallback = {"a": arm(0.81, False), "b": arm(0.83, False)}
        ranking, mode = rank_binary_cnn_arms(fallback)
        self.assertEqual(ranking[0], "b")
        self.assertEqual(mode, "mandatory_cnn_quality_fallback")

    def test_binary_cnn_hparam_ranking_prioritizes_median_ap_then_robustness(self):
        """Optimizer selection must follow the predeclared validation order."""

        def arm(name, ap, macro=0.88, worst_recall=0.80, balanced=0.90,
                far=0.02, deviation=0.01):
            return {"name": name, "median_critical_pr_auc": ap,
                    "median_macro_f1": macro,
                    "worst_critical_recall": worst_recall,
                    "median_balanced_accuracy": balanced,
                    "median_safe_far": far,
                    "critical_pr_auc_std": deviation}

        # A lower AP arm cannot win through better recall.  When AP and Macro-F1
        # tie, the worse-seed recall term chooses the more stable optimizer.
        arms = [arm("lower_ap", 0.84, worst_recall=0.99),
                arm("fragile", 0.85, worst_recall=0.70),
                arm("robust", 0.85, worst_recall=0.82)]
        ranking = rank_binary_cnn_hparam_arms(arms)
        self.assertEqual([item["name"] for item in ranking],
                         ["robust", "fragile", "lower_ap"])

    def test_binary_cnn_hparam_feasibility_requires_all_frozen_gates(self):
        """High validation PR-AUC cannot compensate for failed robust recall."""

        gates = {"median_critical_pr_auc_min": 0.84,
                 "median_accuracy_min": 0.95,
                 "median_balanced_accuracy_min": 0.90,
                 "median_macro_f1_min": 0.80,
                 "worst_seed_critical_recall_min": 0.95,
                 "median_safe_window_false_alarm_rate_max": 0.05}
        candidate = {"median_critical_pr_auc": 0.86, "median_accuracy": 0.98,
                     "median_balanced_accuracy": 0.96, "median_macro_f1": 0.93,
                     "worst_critical_recall": 0.96, "median_safe_far": 0.02}
        checks, feasible = binary_cnn_hparam_feasibility(candidate, gates)
        self.assertTrue(feasible)
        self.assertTrue(all(checks.values()))
        checks, feasible = binary_cnn_hparam_feasibility(
            dict(candidate, worst_critical_recall=0.94), gates)
        self.assertFalse(feasible)
        self.assertFalse(checks["critical_recall"])

    def test_binary_cnn_representative_is_median_seed_not_best_seed(self):
        """Frozen CNN checkpoint must represent the three-seed median AP."""

        runs = [
            {"seed": 1, "metrics": {"critical_pr_auc": 0.80, "macro_f1": 0.90,
                                      "balanced_accuracy": 0.91,
                                      "critical_recall": 0.92,
                                      "safe_window_false_alarm_rate": 0.03}},
            {"seed": 2, "metrics": {"critical_pr_auc": 0.84, "macro_f1": 0.88,
                                      "balanced_accuracy": 0.90,
                                      "critical_recall": 0.95,
                                      "safe_window_false_alarm_rate": 0.02}},
            {"seed": 3, "metrics": {"critical_pr_auc": 0.90, "macro_f1": 0.95,
                                      "balanced_accuracy": 0.96,
                                      "critical_recall": 0.97,
                                      "safe_window_false_alarm_rate": 0.01}},
        ]
        representative, median_ap = select_binary_cnn_representative(runs)
        self.assertEqual(representative["seed"], 2)
        self.assertEqual(median_ap, 0.84)

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

    def test_binary_cnn_screen_matrix_is_exact_and_iid_free(self):
        """The frozen architecture screen must build all and only 27 CNN jobs."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_dir = root / "config"
            windows_dir = root / "windows"
            output_dir = root / "output"
            config_dir.mkdir()
            windows_dir.mkdir()
            required_configs = [
                "training_state_code_binary_b_sqrt_ce.json",
                "model_cnn_state_code_binary_small_v1.json",
                "model_cnn_state_code_binary_medium_v1.json",
                "model_cnn_state_code_binary_large_v1.json",
            ]
            for name in required_configs:
                (config_dir / name).write_text("{}\n", encoding="utf-8")
            for length in (8, 16, 32):
                (windows_dir / "windows_L{}.csv".format(length)).write_text(
                    "placeholder\n", encoding="utf-8")
            args = SimpleNamespace(config_dir=config_dir, windows_dir=windows_dir,
                                   output_dir=output_dir)
            jobs = build_binary_cnn_screen_jobs(args)
        self.assertEqual(len(jobs), 27)
        self.assertEqual(len({job["name"] for job in jobs}), 27)
        self.assertEqual({job["training_arm"] for job in jobs}, {"b_sqrt_ce"})
        self.assertEqual({job["window_length"] for job in jobs}, {8, 16, 32})
        self.assertTrue(all("--model" in job["command"]
                            and "cnn" in job["command"] for job in jobs))
        self.assertTrue(all("iid_test" not in " ".join(job["command"])
                            for job in jobs))

    def test_binary_cnn_hparam_matrix_is_exact_and_iid_free(self):
        """Stage one must resolve nine optimizer arms across exactly three seeds."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            windows = root / "windows_L32.csv"
            model_config = root / "model.json"
            output = root / "search"
            windows.write_text("placeholder\n", encoding="utf-8")
            model_config.write_text("{}\n", encoding="utf-8")
            output.mkdir()
            fixed = {"schema_version": 1, "cpu_threads_per_process": 8,
                     "batch_size": 256, "max_epochs": 80,
                     "early_stopping_patience": 12,
                     "sampling_strategy": "natural", "loss_type": "cross_entropy",
                     "class_weight_strategy": "none",
                     "ordinal_positive_weight_strategy": "none",
                     "checkpoint_selection_metric": "critical_pr_auc"}
            arms = [{"name": "lr{}_wd{}".format(left, right),
                     "learning_rate": left, "weight_decay": right}
                    for left in (0.0003, 0.001, 0.003)
                    for right in (0.0, 0.0001, 0.001)]
            contract = {"scope": "train_validation_only", "model": "cnn",
                        "task": "safe_critical_binary", "window_length": 32,
                        "seeds": [20260725, 20260726, 20260727],
                        "iid_policy": {"features_loaded": False,
                                       "metrics_computed": False,
                                       "selection_allowed": False},
                        "fixed_training": fixed, "arms": arms}
            jobs = build_binary_cnn_hparam_jobs(
                contract, windows, model_config, output, "python")
        self.assertEqual(len(jobs), 27)
        self.assertEqual(len({job["name"] for job in jobs}), 27)
        self.assertEqual(len({job["training_config_sha256"] for job in jobs}), 9)
        self.assertTrue(all("--model" in job["command"]
                            and "cnn" in job["command"] for job in jobs))
        self.assertTrue(all("iid" not in " ".join(job["command"]).lower()
                            for job in jobs))

    def test_multistat_cnn_scheduler_search_matrix_is_exact_and_iid_free(self):
        """The new structure search must resolve 3 LRs x 3 schedulers x 3 seeds."""

        project = Path(__file__).resolve().parents[1]
        contract = json.loads((project / "config" /
            "state_code_binary_cnn_multistat_training_stage1_v1_20260731_r1.json"
        ).read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            windows = root / "windows_L32.csv"
            windows.write_text("placeholder\n", encoding="utf-8")
            output = root / "output"
            output.mkdir()
            jobs = build_binary_cnn_hparam_jobs(
                contract, windows,
                project / "config" /
                "model_cnn_state_code_binary_multistat_w18_k5_v1.json",
                output, "python")
            resolved = [json.loads(Path(job["training_config"]).read_text(
                encoding="utf-8")) for job in jobs]
        self.assertEqual(len(jobs), 27)
        self.assertEqual(len({job["name"] for job in jobs}), 27)
        self.assertEqual({item["learning_rate"] for item in resolved},
                         {0.002, 0.003, 0.004})
        self.assertEqual({item["lr_scheduler"] for item in resolved},
                         {"none", "reduce_on_plateau"})
        self.assertEqual({item["scheduler_patience"] for item in resolved},
                         {6, 10})
        self.assertTrue(all(item["loss_type"] == "cross_entropy"
                            and item["sampling_strategy"] == "natural"
                            for item in resolved))
        self.assertTrue(all("iid_test" not in " ".join(job["command"])
                            for job in jobs))

    def test_binary_cnn_structure_matrix_is_exact_and_below_tcn(self):
        """The frozen structure contract must build 18 validation-only jobs."""

        project = Path(__file__).resolve().parents[1]
        config_dir = project / "config"
        contract = json.loads((
            config_dir / "state_code_binary_cnn_structure_v1_20260731_r1.json"
        ).read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            windows = root / "windows_L32.csv"
            windows.write_text("placeholder\n", encoding="utf-8")
            jobs = build_binary_cnn_structure_jobs(
                contract, config_dir, windows, root / "output", "python")
        self.assertEqual(len(jobs), 18)
        self.assertEqual(len({job["name"] for job in jobs}), 18)
        self.assertEqual(len({job["candidate"] for job in jobs}), 6)
        self.assertTrue(all(job["parameter_count"] < 4050 for job in jobs))
        self.assertTrue(all(job["estimated_macs_per_window"] < 125952
                            for job in jobs))
        self.assertTrue(all("iid_test" not in " ".join(job["command"])
                            for job in jobs))

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
