"""Full-binary package folding and XNOR/popcount equality tests."""

from __future__ import print_function

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.bnn.bittrue_nofc import load_package, run_bittrue
from power_macro.tcn_detection.bnn.export_nofc_package import (
    build_package,
    fold_batchnorm_threshold,
    write_package,
)
from power_macro.tcn_detection.bnn.input_encoding import encode_windows
from power_macro.tcn_detection.bnn.nofc_model import BinaryNoFCModel


class BnnExportBittrueTests(unittest.TestCase):
    """Use a real W1A1 graph so equality covers all three folded layers."""

    def test_negative_bn_scale_uses_inversion_threshold(self):
        """A negative BN scale must reverse the integer comparison exactly."""

        model = BinaryNoFCModel(8, "w1a1")
        with torch.no_grad():
            model.conv1.weight.zero_()
            model.bn1.weight.fill_(-1.0)
            model.bn1.bias.zero_()
            model.bn1.running_mean.zero_()
            model.bn1.running_var.fill_(1.0)
        thresholds, inversion = fold_batchnorm_threshold(
            model.conv1.weight, model.bn1)
        # Conv1 has 32*3=96 comparisons: p<=48 is equivalent to
        # ``not(p>=49)`` for the frozen >= threshold rule.
        self.assertTrue(np.all(thresholds == 49))
        self.assertTrue(np.all(inversion == 1))

    def test_packed_package_matches_training_binary_forward(self):
        """All directed code windows must match XNOR/popcount deployment bits."""

        torch.manual_seed(17)
        model = BinaryNoFCModel(8, "w1a1")
        model.eval()
        codes = np.asarray([
            [0] * 32,
            [32] * 32,
            list(range(32)),
            list(reversed(range(32))),
        ], dtype=np.int16)
        vote_k = 16
        package = build_package(model, vote_k)
        with tempfile.TemporaryDirectory() as temporary:
            package_root = Path(temporary) / "package"
            manifest = write_package(package, package_root)
            loaded = load_package(package_root)
            bittrue = run_bittrue(codes, loaded, batch_size=2,
                                  capture_intermediates=True)
            with torch.no_grad():
                hard = model.hard_vote(
                    torch.from_numpy(encode_windows(codes).astype(np.float32)),
                    vote_k)
            expected_bits = hard["temporal_bits"].numpy().astype(np.uint8)
            expected_alarm = hard["alarm"].numpy().astype(np.uint8)
            self.assertTrue(np.array_equal(expected_bits,
                                           bittrue["temporal_bits"]))
            self.assertTrue(np.array_equal(expected_alarm,
                                           bittrue["predictions"]))
            self.assertEqual(bittrue["trace"]["conv1_bits"].shape,
                             (4, 8, 32))
            self.assertEqual(manifest["classifier_present"], False)
            self.assertEqual(manifest["batchnorm_present"], False)
            self.assertEqual(manifest["weight_bits"], 1)
            self.assertNotIn("tensors", json.loads(
                (package_root / "package.json").read_text(encoding="utf-8")))

    def test_bittrue_rejects_illegal_code_window(self):
        """The deployment boundary rejects code values before any layer runs."""

        model = BinaryNoFCModel(8, "w1a1")
        package = build_package(model, 1)
        with self.assertRaises(ValueError):
            run_bittrue(np.full((1, 32), 33, dtype=np.int16), package)


if __name__ == "__main__":
    unittest.main()
