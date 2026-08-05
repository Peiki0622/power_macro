#!/usr/bin/env python3
"""Regression checks for the frozen [18,8,18] fixed-point interface.

These tests intentionally use a few validation windows only for tensor-shape
and determinism checks.  The acceptance metrics and golden replay are produced
by the separate full-validation export run; no IID/OOD rows are loaded here.
"""

from __future__ import print_function

import json
import unittest
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.fixed_point import bittrue
from power_macro.tcn_detection.fixed_point import float_reference
from power_macro.tcn_detection.fixed_point import provenance


POWER_MACRO_ROOT = Path(__file__).resolve().parents[2]
MODEL_ROOT = (POWER_MACRO_ROOT / "tcn_detection" / "runs" /
              "formal_v1_20260727_r1" / "models" /
              "state_code_binary_cnn_compression_v1_20260805_r1" /
              "final_w18_8_18_20260805_r1")
MODEL_CONFIG = MODEL_ROOT / "model_config.json"
CHECKPOINT = MODEL_ROOT / "checkpoint.pt"
FIXED_CONFIG = (POWER_MACRO_ROOT / "tcn_detection" / "config" /
                "fixed_point_cnn_multistat_w18_8_18_k5_v1.json")
WINDOWS = (POWER_MACRO_ROOT / "tcn_detection" / "runs" /
           "formal_v1_20260727_r1" / "windows" /
           "state_code_binary_iid_v1_20260730_r1" / "windows_L32.csv")


class CompressedFixedPointContractTest(unittest.TestCase):
    """Ensure reduced Conv2 width reaches every numeric stage."""

    def test_provenance_derives_reduced_shapes(self):
        """The physical checkpoint and classifier retain the three branch order."""

        model, _, metadata = provenance.build_validated_model(
            MODEL_CONFIG, CHECKPOINT, FIXED_CONFIG)
        self.assertEqual(tuple(model.channels), (18, 8, 18))
        self.assertEqual(tuple(model.classifier.weight.shape), (2, 54))
        self.assertEqual(metadata["pooling_feature_order"], [
            "average[0:18]", "maximum[18:36]", "endpoint[36:54]"])

    def test_reference_and_bittrue_are_deterministic_for_reduced_width(self):
        """A directed validation batch has stable float and integer shapes."""

        model, checkpoint, _ = provenance.build_validated_model(
            MODEL_CONFIG, CHECKPOINT, FIXED_CONFIG)
        config = json.loads(FIXED_CONFIG.read_text(encoding="utf-8"))
        table = float_reference.load_development_windows(WINDOWS, "validation")
        inputs = float_reference.checkpoint_inputs(table, checkpoint["normalizer"])
        codes = float_reference.decode_sensor_codes(table.features)
        float_trace = float_reference.numpy_float_forward(inputs[:8], model)
        self.assertEqual(float_trace["relu2"].shape, (8, 8, 32))
        self.assertEqual(float_trace["summary"].shape, (8, 54))

        # Synthetic positive ranges exercise package construction without
        # replacing the full train-only calibration used by the export run.
        calibration = {"relu1": 32.0, "relu2": 32.0,
                       "relu3": 32.0, "logits": 32.0}
        package = bittrue.build_candidate(
            model, checkpoint, config["candidates"][0], calibration, config)
        first = bittrue.run_bittrue(codes[:8], package)
        second = bittrue.run_bittrue(codes[:8], package)
        self.assertEqual(first["integer_logits"].shape, (8, 2))
        self.assertTrue(np.array_equal(first["integer_logits"],
                                       second["integer_logits"]))
        self.assertEqual(package["layers"][1]["weights"].shape, (8, 18, 5))

    def test_forbidden_split_is_rejected_before_feature_use(self):
        """The fixed-point loader cannot be pointed at IID/OOD selection data."""

        with self.assertRaisesRegex(ValueError, "forbids split"):
            float_reference.load_development_windows(WINDOWS, "iid_test")


if __name__ == "__main__":
    unittest.main()
