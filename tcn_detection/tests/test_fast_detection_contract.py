#!/usr/bin/env python3
"""Full contract tests for the Stage-1 causal interface and data boundary."""

from __future__ import print_function

import unittest
from pathlib import Path

from power_macro.tcn_detection.fast_detection.dataset_adapter import DatasetAdapter
from power_macro.tcn_detection.fast_detection.detector_base import TraceMetadata
from power_macro.tcn_detection.fast_detection.detectors import (
    AmplitudeSlopeDetector, CusumDetector, EwmaResidualDetector,
    Int8ScorecardDetector, MultiStatisticFSMDetector,
    ShallowTreeDetector, SingleThresholdDetector,
    ThresholdConfirmDetector)


ROOT = Path(__file__).resolve().parents[3]
LABEL_ROOT = ROOT / "power_macro" / "tcn_detection" / "runs" / "formal_v1_20260727_r1" / "labels" / "state_code_binary_iid_v1_20260730_r1"


def metadata():
    """Return one ordinary trace context used by pure online unit tests."""

    return TraceMetadata("trace_test", "validation", "base_test", "")


class FastDetectionContractTests(unittest.TestCase):
    """Exercise every detector family and the complete released trace set."""

    def test_adapter_reads_all_release_traces_and_samples(self):
        """The adapter must validate every row, not just a smoke prefix."""

        traces = DatasetAdapter(LABEL_ROOT).iter_traces({"train", "validation", "iid_test"})
        self.assertEqual(len(traces), 240)
        self.assertEqual(sum(len(trace.samples) for trace in traces), 120000)
        self.assertEqual({trace.metadata.split for trace in traces},
                         {"train", "validation", "iid_test"})

    def test_invalid_capture_holds_state(self):
        """An invalid sample cannot clear a prior alarm or increment history."""

        detector = ThresholdConfirmDetector(20, 2)
        detector.reset(metadata())
        self.assertFalse(detector.step(21, True))
        before = detector.snapshot()
        self.assertFalse(detector.step(0, False))
        self.assertEqual(before["sample_index"], detector.snapshot()["sample_index"])
        self.assertTrue(detector.step(21, True))

    def test_reset_removes_all_cross_trace_state(self):
        """Two identical traces must produce identical outputs after reset."""

        detectors = [
            SingleThresholdDetector(20), ThresholdConfirmDetector(20, 2),
            AmplitudeSlopeDetector(2, 1), EwmaResidualDetector(4, 2),
            CusumDetector(1, 8),
            MultiStatisticFSMDetector({
                "suspect": {name: 1 for name in ("residual", "slope", "acceleration", "cusum", "threshold_count")},
                "warning": {name: 2 for name in ("residual", "slope", "acceleration", "cusum", "threshold_count")},
                "critical": {name: 3 for name in ("residual", "slope", "acceleration", "cusum", "threshold_count")},
            }),
            Int8ScorecardDetector((1, 1, 1, 1, 1), 0, 8),
            ShallowTreeDetector(({"feature": "residual", "threshold": 1, "left": 1, "right": 2}, {"leaf": 0}, {"leaf": 1})),
        ]
        sequence = (15, 16, 18, 22, 15, 15)
        for detector in detectors:
            detector.reset(metadata())
            first = [detector.step(code, True) for code in sequence]
            detector.reset(metadata())
            second = [detector.step(code, True) for code in sequence]
            self.assertEqual(first, second, detector.name)

    def test_no_detector_accepts_measured_voltage_as_runtime_input(self):
        """The public step signature is exactly sensor_code plus valid."""

        for detector in (SingleThresholdDetector(20), CusumDetector(1, 8)):
            detector.reset(metadata())
            with self.assertRaises(TypeError):
                detector.step(20, True, 1.05)


if __name__ == "__main__":
    unittest.main()
