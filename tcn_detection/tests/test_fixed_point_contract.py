#!/usr/bin/env python3
"""Contract tests for the frozen multistat CNN fixed-point boundary."""

from __future__ import print_function

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch

from power_macro.tcn_detection.fixed_point import bittrue
from power_macro.tcn_detection.fixed_point import export_package
from power_macro.tcn_detection.fixed_point import float_reference
from power_macro.tcn_detection.fixed_point import normalization
from power_macro.tcn_detection.fixed_point import provenance
from power_macro.tcn_detection.fixed_point import quality


POWER_MACRO_ROOT = Path(__file__).resolve().parents[2]
MODEL_CONFIG = (POWER_MACRO_ROOT / "tcn_detection" / "config" /
                "model_cnn_state_code_binary_multistat_w18_k5_v1.json")
FIXED_CONFIG = (POWER_MACRO_ROOT / "tcn_detection" / "config" /
                "fixed_point_cnn_multistat_w18_k5_v1.json")
CHECKPOINT = (POWER_MACRO_ROOT / "tcn_detection" / "runs" /
              "formal_v1_20260727_r1" / "models" /
              "state_code_binary_multistat_training_v1_20260731_r1" /
              "stage2" / "lr4em3_b256_seed20260727" /
              "best_checkpoint.pt")
WINDOWS = (POWER_MACRO_ROOT / "tcn_detection" / "runs" /
           "formal_v1_20260727_r1" / "windows" /
           "state_code_binary_iid_v1_20260730_r1" / "windows_L32.csv")


class FixedPointContractTest(unittest.TestCase):
    """Exercise success and fail-closed paths before numeric export begins."""

    def test_authoritative_checkpoint_and_graph_are_exact(self):
        """The only accepted model has the documented digest and layer shapes."""

        model, checkpoint, metadata = provenance.build_validated_model(
            MODEL_CONFIG, CHECKPOINT, FIXED_CONFIG)
        self.assertFalse(model.training)
        self.assertEqual(checkpoint["seed"], 20260727)
        self.assertEqual(metadata["checkpoint_sha256"],
                         "b6741281203fc4593b6434df584ace44cffa5daed23ece8745d1b14215a64814")
        self.assertEqual([item["name"] for item in metadata["parameter_inventory"]],
                         list(provenance.EXPECTED_PARAMETER_SHAPES))
        self.assertEqual(metadata["pooling_feature_order"],
                         ["average[0:18]", "maximum[18:36]", "endpoint[36:54]"])

    def test_wrong_digest_is_rejected_before_torch_load(self):
        """A config digest mismatch must stop before deserializing the archive."""

        with tempfile.TemporaryDirectory() as temporary:
            changed = json.loads(FIXED_CONFIG.read_text(encoding="utf-8"))
            changed["expected_checkpoint_sha256"] = "0" * 64
            path = Path(temporary) / "fixed.json"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with mock.patch.object(torch, "load") as loader:
                with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                    provenance.build_validated_model(MODEL_CONFIG, CHECKPOINT, path)
                loader.assert_not_called()

    def test_missing_extra_and_wrong_shape_parameters_are_rejected(self):
        """Strict shape inventory catches all common checkpoint substitutions."""

        checkpoint = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
        variants = []
        missing = copy.deepcopy(checkpoint)
        del missing["state_dict"]["features.0.bias"]
        variants.append(missing)
        extra = copy.deepcopy(checkpoint)
        extra["state_dict"]["unexpected.weight"] = torch.zeros(1)
        variants.append(extra)
        wrong_shape = copy.deepcopy(checkpoint)
        wrong_shape["state_dict"]["classifier.weight"] = torch.zeros(2, 53)
        variants.append(wrong_shape)

        # The digest check is intentionally mocked here: these in-memory
        # variants test the independent state inventory gate, not archive I/O.
        for variant in variants:
            with self.subTest(keys=list(variant["state_dict"])):
                with mock.patch.object(provenance, "sha256_file",
                                       return_value=json.loads(
                                           FIXED_CONFIG.read_text(encoding="utf-8"))[
                                               "expected_checkpoint_sha256"]), \
                        mock.patch.object(torch, "load", return_value=variant):
                    with self.assertRaisesRegex(
                            ValueError, "parameter names or shapes"):
                        provenance.build_validated_model(
                            MODEL_CONFIG, CHECKPOINT, FIXED_CONFIG)

    def test_float_reference_matches_pytorch_layer_by_layer(self):
        """Independent NumPy float math reproduces the checkpoint graph."""

        model, checkpoint, _ = provenance.build_validated_model(
            MODEL_CONFIG, CHECKPOINT, FIXED_CONFIG)
        table = float_reference.load_development_windows(WINDOWS, "validation")
        inputs = float_reference.checkpoint_inputs(table, checkpoint["normalizer"])
        torch_result = float_reference.torch_float_inference(inputs[:4], model)
        numpy_trace = float_reference.numpy_float_forward(inputs[:4], model)
        self.assertTrue(torch.allclose(
            torch.from_numpy(numpy_trace["logits"]),
            torch.from_numpy(torch_result.logits), rtol=1.0e-5, atol=2.0e-6))
        self.assertEqual(numpy_trace["relu1"].shape, (4, 18, 32))
        self.assertEqual(numpy_trace["relu2"].shape, (4, 18, 32))
        self.assertEqual(numpy_trace["relu3"].shape, (4, 18, 32))
        self.assertEqual(numpy_trace["summary"].shape, (4, 54))

    def test_sensor_code_decode_and_forbidden_split_gate(self):
        """Only exact 0..32 lattice values from development splits are legal."""

        codes = torch.arange(33, dtype=torch.float64).numpy()
        encoded = ((codes - 15.0) / 17.0).reshape(1, 1, 33)
        # The deployment contract fixes L32, so exercise the first 32 codes as
        # one legal window and the final code in a second constant window.
        first = float_reference.decode_sensor_codes(encoded[:, :, :32])
        last = float_reference.decode_sensor_codes(
            torch.full((1, 1, 32), encoded[0, 0, 32]).numpy())
        self.assertEqual(first[0, 0].tolist(), list(range(32)))
        self.assertTrue((last == 32).all())
        with self.assertRaisesRegex(ValueError, "forbids split"):
            float_reference.load_development_windows(WINDOWS, "iid_test")

    def test_golden_selection_covers_categories_and_unique_traces(self):
        """Golden selection covers all required behaviors without trace reuse."""

        model, checkpoint, _ = provenance.build_validated_model(
            MODEL_CONFIG, CHECKPOINT, FIXED_CONFIG)
        table = float_reference.load_development_windows(WINDOWS, "validation")
        codes = float_reference.decode_sensor_codes(table.features)
        inputs = float_reference.checkpoint_inputs(table, checkpoint["normalizer"])
        inference = float_reference.torch_float_inference(inputs, model)
        selected = float_reference.select_golden_windows(
            table, codes, inference, model)
        self.assertEqual([item["category"] for item in selected],
                         list(float_reference.GOLDEN_CATEGORIES))
        self.assertEqual(len({item["trace_id"] for item in selected}), 8)
        self.assertTrue(all(item["split"] == "validation" for item in selected))

    def test_quality_gates_are_frozen_and_directionally_correct(self):
        """Metric drops and FAR increases use their intended inequality."""

        config = json.loads(FIXED_CONFIG.read_text(encoding="utf-8"))
        quality.validate_fixed_point_config(config)
        baseline = {
            "accuracy": 0.9872512437810945,
            "balanced_accuracy": 0.986778355191051,
            "macro_f1": 0.9510605963616082,
            "critical_pr_auc": 0.9003906868709534,
            "critical_recall": 0.9862353750860289,
            "safe_window_false_alarm_rate": 0.012678664703927062,
        }
        passing = dict(baseline)
        passing["accuracy"] -= config["relative_degradation_limits"]["accuracy"]
        passing["safe_window_false_alarm_rate"] += config[
            "relative_degradation_limits"][
                "safe_window_false_alarm_rate_increase"]
        self.assertTrue(quality.evaluate_quality_gates(
            baseline, passing, config)["passed"])
        failing = dict(baseline)
        failing["critical_recall"] -= (
            config["relative_degradation_limits"]["critical_recall"] + 1.0e-4)
        self.assertFalse(quality.evaluate_quality_gates(
            baseline, failing, config)["passed"])

    def test_candidate_choice_preserves_predeclared_priority(self):
        """A wider candidate is selected only after cheaper candidates fail."""

        config = json.loads(FIXED_CONFIG.read_text(encoding="utf-8"))
        reports = [{"candidate_id": candidate,
                    "quality_gates": {"passed": candidate == "w8_a16"}}
                   for candidate in config["candidate_priority"]]
        self.assertEqual(quality.choose_candidate(reports, config), "w8_a16")

    def test_normalization_fold_covers_all_codes_and_padding_positions(self):
        """The fused first layer reproduces 0..32 and edge padding semantics."""

        model, checkpoint, _ = provenance.build_validated_model(
            MODEL_CONFIG, CHECKPOINT, FIXED_CONFIG)
        report = normalization.exhaustive_fold_error(
            model, checkpoint["normalizer"])
        self.assertLess(report["max_abs_error"], 3.0e-6)
        self.assertTrue(report["interior_bias_columns_identical"])
        self.assertAlmostEqual(report["alpha"], 0.20001902386860476,
                               places=14)
        self.assertAlmostEqual(report["beta"], -0.4388770714698241,
                               places=14)

    def test_normalization_fold_handles_nonconstant_extreme_windows(self):
        """Alternating and edge impulses catch incorrect virtual padding codes."""

        model, checkpoint, _ = provenance.build_validated_model(
            MODEL_CONFIG, CHECKPOINT, FIXED_CONFIG)
        folded = normalization.derive_folded_first_layer(
            model, checkpoint["normalizer"])
        windows = torch.full((4, 1, 32), 15, dtype=torch.int16).numpy()
        windows[0, 0, ::2] = 0
        windows[0, 0, 1::2] = 32
        windows[1, 0, 0] = 0
        windows[2, 0, -1] = 32
        windows[3, 0] = torch.arange(32, dtype=torch.int16).numpy()
        original = normalization.original_first_layer_float(
            windows, model, checkpoint["normalizer"])
        fused = normalization.folded_first_layer_float(windows, folded)
        self.assertLess(float(abs(original.astype("float64") - fused).max()),
                        3.0e-6)

    def test_ties_to_even_shift_is_defined_for_both_signs(self):
        """Signed midpoint behavior cannot depend on host right-shift rules."""

        values = torch.tensor([-7, -6, -5, -3, -2, -1, 1, 2, 3, 5, 6, 7],
                              dtype=torch.int64).numpy()
        observed = bittrue.round_right_shift_ties_even(values, 1)
        expected = torch.tensor([-4, -3, -2, -2, -1, 0, 0, 1, 2, 2, 3, 4],
                                dtype=torch.int64).numpy()
        self.assertTrue((observed == expected).all())

    def test_bittrue_candidate_has_explicit_bounds_and_stable_decision(self):
        """A small directed batch executes every integer truncation point."""

        model, checkpoint, _ = provenance.build_validated_model(
            MODEL_CONFIG, CHECKPOINT, FIXED_CONFIG)
        config = json.loads(FIXED_CONFIG.read_text(encoding="utf-8"))
        # Calibration ranges in this unit test are conservative synthetic
        # values; the full train-only ranges are measured by the search flow.
        calibration = {"relu1": 32.0, "relu2": 32.0,
                       "relu3": 32.0, "logits": 32.0}
        package = bittrue.build_candidate(
            model, checkpoint, config["candidates"][0], calibration, config)
        windows = torch.full((3, 1, 32), 15, dtype=torch.int16).numpy()
        windows[1, 0] = 0
        windows[2, 0] = 32
        first = bittrue.run_bittrue(
            windows, package, capture_intermediates=True)
        second = bittrue.run_bittrue(
            windows, package, capture_intermediates=True)
        self.assertTrue((first["integer_logits"] == second["integer_logits"]).all())
        self.assertTrue((first["predictions"] ==
                         (first["integer_logits"][:, 1]
                          > first["integer_logits"][:, 0])).all())
        self.assertEqual(set(first["accumulator_statistics"]),
                         {"conv1", "conv2", "conv3", "classifier"})
        self.assertLessEqual(max(package["accumulator_widths"].values()), 63)

    def test_neutral_memory_format_round_trips_signed_values(self):
        """Hex serialization preserves shape, sign, limits, and stable digest."""

        values = torch.tensor([[-128, -1, 0], [1, 126, 127]],
                              dtype=torch.int64).numpy()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "weights.mem"
            first = export_package.write_mem(
                path, values, 8, "test.weights", "row,column")
            restored = export_package.read_mem(path, values.shape, 8)
            self.assertTrue((restored == values).all())
            self.assertEqual(first["entry_count"], 6)
            self.assertEqual(first["sha256"], provenance.sha256_file(path))


if __name__ == "__main__":
    unittest.main()
