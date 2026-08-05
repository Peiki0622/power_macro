#!/usr/bin/env python3
"""Step 2 contracts for physical channel migration."""

from __future__ import print_function

import unittest

import torch

from power_macro.tcn_detection.compression.channel_surgery import (
    compact_model, surgery_metadata, validate_keep_indices,
    verify_surgery_equivalence)
from power_macro.tcn_detection.models.cnn1d import CNN1D
from power_macro.tcn_detection.train.common import parameter_count


class ChannelSurgeryTests(unittest.TestCase):
    """Check inherited weights, dimensions, and failure-closed validation."""

    @staticmethod
    def _teacher():
        """Build a deterministic small teacher for isolated tensor checks."""

        torch.manual_seed(17)
        model = CNN1D(input_channels=1, class_count=2, channels=[4, 4, 4],
                      kernel_sizes=[5, 5, 5], dropout=0.0,
                      pooling_contract="multistat_average_max_endpoint")
        model.eval()
        return model

    def test_no_pruning_preserves_parameters_and_logits(self):
        """An identity keep map must be an exact state-preserving operation."""

        teacher = self._teacher()
        student = compact_model(teacher, [[0, 1, 2, 3]] * 3)
        inputs = torch.randn(5, 1, 32)
        with torch.no_grad():
            self.assertTrue(torch.equal(teacher(inputs), student(inputs)))
        self.assertEqual(parameter_count(teacher), parameter_count(student))

    def test_random_keep_map_matches_explicit_zeroed_reference(self):
        """Surgery output equals the original graph with removed channels zeroed."""

        teacher = self._teacher()
        keep = [[0, 2], [1, 3], [0, 2]]
        student = compact_model(teacher, keep)
        inputs = torch.randn(4, 1, 32)
        features = inputs
        masks = []
        for stage, keep_stage in enumerate(keep):
            start = stage * 3
            features = teacher.features[start](features)
            features = teacher.features[start + 1](features)
            features = teacher.features[start + 2](features)
            mask = torch.zeros(features.shape[1])
            mask[keep_stage] = 1.0
            masks.append(mask.view(1, -1, 1))
            features = features * masks[-1]
        reference_summary = teacher._summary(features)
        with torch.no_grad():
            reference_logits = teacher.classifier(reference_summary)
            student_logits = student(inputs)
        self.assertTrue(torch.equal(reference_logits, student_logits))
        self.assertEqual(tuple(student.features[0].weight.shape), (2, 1, 5))
        self.assertEqual(tuple(student.features[3].weight.shape), (2, 2, 5))
        self.assertEqual(tuple(student.features[6].weight.shape), (2, 2, 5))
        self.assertEqual(tuple(student.classifier.weight.shape), (2, 6))
        self.assertLessEqual(
            verify_surgery_equivalence(teacher, student, keep, inputs), 1.0e-6)

    def test_metadata_records_source_and_physical_target(self):
        """Export metadata binds source digest, map, dimensions, and ordering."""

        metadata = surgery_metadata("teacher-sha", [4, 4, 4], [[0, 2], [1, 3], [0, 2]])
        self.assertEqual(metadata["source_teacher_sha256"], "teacher-sha")
        self.assertEqual(metadata["target_channels"], [2, 2, 2])
        self.assertTrue(metadata["physical_channel_deletion"])
        self.assertEqual(metadata["pooling_order"], ["average", "maximum", "endpoint"])

    def test_invalid_maps_fail_closed(self):
        """Empty, duplicate, unordered, and out-of-range indices are rejected."""

        invalid_maps = (
            [[0, 1], [0, 1], []],
            [[0, 0], [0, 1], [0, 1]],
            [[1, 0], [0, 1], [0, 1]],
            [[0, 4], [0, 1], [0, 1]],
        )
        for keep in invalid_maps:
            with self.assertRaises(ValueError):
                validate_keep_indices([4, 4, 4], keep)


if __name__ == "__main__":
    unittest.main()
