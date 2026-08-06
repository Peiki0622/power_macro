#!/usr/bin/env python3
"""Non-smoke regression tests for the complete Stage-1 detector contract.

Run this file with the project's DL interpreter because the fixed-point CNN
loader and shared metric implementation use NumPy.  The tests use deterministic
directed traces and the frozen package, while the IID acceptance numbers remain
in the separately generated one-shot report.
"""

from __future__ import print_function

import json
import tempfile
import unittest
from pathlib import Path

from power_macro.tcn_detection.fast_detection.cnn_baseline import (
    CnnBaselineDetector, load_w8_a8_package)
from power_macro.tcn_detection.fast_detection.detector_base import TraceMetadata
from power_macro.tcn_detection.fast_detection.detectors import (
    AmplitudeSlopeDetector, CusumDetector, EwmaResidualDetector,
    Int8ScorecardDetector, MultiStatisticFSMDetector, ShallowTreeDetector,
    SingleThresholdDetector, ThresholdConfirmDetector)
from power_macro.tcn_detection.fast_detection.evaluation import event_metrics
from power_macro.tcn_detection.fast_detection.frozen_evaluation import (
    detector_from_spec, evaluate_iid_once)


ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = ROOT / "tcn_detection" / "runs" / "formal_v1_20260727_r1"
LABEL_ROOT = RUN_ROOT / "labels" / "state_code_binary_iid_v1_20260730_r1"
PACKAGE_ROOT = (RUN_ROOT / "models" /
                "state_code_binary_cnn_compression_v1_20260805_r1" /
                "final_w18_8_18_20260805_r1" /
                "fixed_point_quantized_20260805_r1")
FROZEN_CONFIG = (RUN_ROOT / "fast_detection_stage1_v1" / "artifacts" /
                 "frozen_detector_config.json")


def _metadata():
    """Return a legal trace context with the calibrated code baseline."""

    return TraceMetadata("regression", "validation", "base_regression", "")


def _all_detector_factories():
    """Construct one representative instance from every eight detector family."""

    features = ("residual", "slope", "acceleration", "cusum", "threshold_count")
    thresholds = {level: {name: value for name, value in zip(features, values)}
                  for level, values in {
                      "suspect": (1, 1, 1, 2, 1),
                      "warning": (3, 2, 2, 4, 2),
                      "critical": (6, 4, 4, 8, 4),
                  }.items()}
    return [
        lambda: SingleThresholdDetector(20),
        lambda: ThresholdConfirmDetector(20, 2),
        lambda: AmplitudeSlopeDetector(2, 1),
        lambda: EwmaResidualDetector(4, 2),
        lambda: CusumDetector(1, 8),
        lambda: MultiStatisticFSMDetector(thresholds, 2),
        lambda: Int8ScorecardDetector((1, 1, 1, 1, 1), 0, 8),
        lambda: ShallowTreeDetector((
            {"feature": "residual", "threshold": 1, "left": 1, "right": 2},
            {"leaf": 0}, {"leaf": 1})),
    ]


class FastDetectionRegressionTests(unittest.TestCase):
    """Check deterministic numeric and causal properties beyond smoke tests."""

    def test_fixed_point_loader_golden_vector(self):
        """The hashed W8/A8 package must reproduce a known 32-code output."""

        package = load_w8_a8_package(PACKAGE_ROOT)
        detector = CnnBaselineDetector(package)
        detector.reset(_metadata())
        for code in [15] * 16 + [32] * 16:
            detector.step(code, True)
        self.assertTrue(detector.alarm)
        self.assertEqual(detector.integer_logits.tolist(), [-339607552, 539885568])

    def test_event_metrics_delay_maximum_and_occupancy(self):
        """Known intervals exercise event recall, max TTD, false alarm and occupancy."""

        truth = [0, 0, 1, 1, 0, 0, 1, 1, 0]
        # Endpoint 4 is an isolated Safe alarm; endpoints 2 and 7 detect the
        # two Critical intervals without merging with that false-alarm episode.
        prediction = [0, 0, 1, 0, 1, 0, 0, 1, 0]
        rows = [{"trace_id": "known", "end_index": index,
                 "target_label": label, "prediction": alarm}
                for index, (label, alarm) in enumerate(zip(truth, prediction))]
        result = event_metrics(rows)
        self.assertEqual(result["critical_event_count"], 2)
        self.assertEqual(result["detected_event_count"], 2)
        self.assertEqual(result["false_alarms"], 1)
        self.assertEqual(result["maximum_ttd_ns"], 4.0)
        self.assertAlmostEqual(result["median_ttd_ns"], 2.0)
        self.assertAlmostEqual(result["alarm_occupancy"], 3.0 / 9.0)

    def test_every_detector_is_future_prefix_invariant(self):
        """Appending samples after a prefix cannot alter earlier alarm outputs."""

        prefix = [15, 15, 17, 19, 22, 25, 18]
        future = [15, 32, 0, 32, 15]
        factories = _all_detector_factories()
        # The reference CNN is causal too: its first legal decision arrives
        # after 32 accepted codes, and future codes must not revise it.
        factories.append(lambda: CnnBaselineDetector(load_w8_a8_package(PACKAGE_ROOT)))
        for factory in factories:
            detector = factory()
            detector.reset(_metadata())
            prefix_only = [detector.step(code, True) for code in prefix]
            detector.reset(_metadata())
            with_future = [detector.step(code, True) for code in prefix + future]
            self.assertEqual(prefix_only, with_future[:len(prefix)], detector.name)

    def test_frozen_specs_reconstruct_and_preserve_outputs(self):
        """Each selected JSON spec rebuilds the exact validation detector behavior."""

        config = json.loads(FROZEN_CONFIG.read_text(encoding="utf-8"))
        copied_candidates = json.loads((FROZEN_CONFIG.parent / "detector_candidates.json").read_text(
            encoding="utf-8"))
        copied_by_name = {item["name"]: item for item in copied_candidates["frozen_candidates"]}
        sequence = [15, 15, 18, 22, 25, 15, 20, 32]
        for candidate in config["selected_candidates"]:
            self.assertEqual(candidate, copied_by_name[candidate["name"]])
            first = detector_from_spec(candidate["family"], candidate["spec"])
            second = detector_from_spec(candidate["family"], candidate["spec"])
            self.assertEqual(first.hardware_cost(), candidate["hardware_cost"])
            first.reset(_metadata())
            second.reset(_metadata())
            self.assertEqual([first.step(value, True) for value in sequence],
                             [second.step(value, True) for value in sequence],
                             candidate["name"])

    def test_iid_evaluator_refuses_reused_output_directory(self):
        """A pre-existing result directory is rejected before IID data access."""

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "already_used"
            output.mkdir()
            with self.assertRaisesRegex(FileExistsError, "reuse IID"):
                evaluate_iid_once(FROZEN_CONFIG, LABEL_ROOT, PACKAGE_ROOT, output)


if __name__ == "__main__":
    unittest.main()
