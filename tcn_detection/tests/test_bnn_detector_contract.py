"""Causal interface tests for the exported full-binary detector."""

from __future__ import print_function

import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.bnn.bittrue_nofc import load_package, run_bittrue
from power_macro.tcn_detection.bnn.export_nofc_package import build_package, write_package
from power_macro.tcn_detection.bnn.input_encoding import encode_windows
from power_macro.tcn_detection.bnn.nofc_model import BinaryNoFCModel
from power_macro.tcn_detection.fast_detection.bnn_nofc_baseline import BnnNofcDetector
from power_macro.tcn_detection.fast_detection.detector_base import TraceMetadata


class BnnDetectorContractTests(unittest.TestCase):
    """Prove warmup, invalid-hold, and bit-true equivalence on a packed model."""

    def _package(self, vote_k=16):
        """Create one deterministic exported package in a private temp directory."""

        torch.manual_seed(23)
        model = BinaryNoFCModel(8, "w1a1")
        model.eval()
        package = build_package(model, vote_k)
        tempdir = tempfile.TemporaryDirectory()
        path = Path(tempdir.name) / "package"
        write_package(package, path)
        return tempdir, load_package(path)

    def test_invalid_captures_hold_state(self):
        """An invalid sample cannot advance the sample index or window fill."""

        tempdir, package = self._package()
        self.addCleanup(tempdir.cleanup)
        detector = BnnNofcDetector(package)
        detector.reset(TraceMetadata("t", "validation", "base", ""))
        self.assertFalse(detector.step(15, True))
        before = detector.snapshot()
        self.assertFalse(detector.step(0, False))
        after = detector.snapshot()
        self.assertEqual(before["sample_index"], after["sample_index"])
        self.assertEqual(before["window_fill"], after["window_fill"])

    def test_warmup_then_bittrue_equivalence(self):
        """Once 32 valid samples exist, online detector and bit-true package agree."""

        tempdir, package = self._package(vote_k=8)
        self.addCleanup(tempdir.cleanup)
        detector = BnnNofcDetector(package)
        detector.reset(TraceMetadata("t", "validation", "base", ""))
        codes = list(range(16)) + list(reversed(range(16)))
        outputs = [detector.step(code, True) for code in codes]
        expected = run_bittrue(np.asarray([codes], dtype=np.int16), package,
                               batch_size=1)
        self.assertEqual(outputs[:31], [False] * 31)
        self.assertEqual(outputs[31], bool(expected["predictions"][0]))
        self.assertTrue(np.array_equal(detector.temporal_bits,
                                       expected["temporal_bits"][0]))
        self.assertEqual(detector.vote_count, int(expected["vote_count"][0]))

    def test_prefix_invariance_is_preserved(self):
        """Later codes cannot revise already emitted detector outputs."""

        tempdir, package = self._package(vote_k=4)
        self.addCleanup(tempdir.cleanup)
        prefix = [15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18]
        future = [0, 1, 2, 3]
        detector = BnnNofcDetector(package)
        detector.reset(TraceMetadata("t", "validation", "base", ""))
        prefix_only = [detector.step(code, True) for code in prefix]
        detector.reset(TraceMetadata("t", "validation", "base", ""))
        with_future = [detector.step(code, True) for code in prefix + future]
        self.assertEqual(prefix_only, with_future[:len(prefix)])


if __name__ == "__main__":
    unittest.main()
