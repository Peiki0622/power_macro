#!/usr/bin/env python3
"""Step 6 mathematical and frozen-Teacher distillation contracts."""

from __future__ import print_function

import unittest

import torch
import torch.nn.functional as F

from power_macro.tcn_detection.compression.distillation import (
    StatisticProjectors, freeze_teacher, logit_distillation_loss,
    state_dict_sha256, statistic_distillation_losses)
from power_macro.tcn_detection.models.cnn1d import CNN1D


class DistillationContractTests(unittest.TestCase):
    """Verify CE fallback, KL scaling, and immutable Teacher behavior."""

    def test_ce_only_mode_is_exact_cross_entropy(self):
        """Disabling KD through alpha=1 must reproduce ordinary CE exactly."""

        student = torch.tensor([[1.0, -0.5], [0.2, 0.4]], requires_grad=True)
        teacher = torch.tensor([[0.1, 0.2], [0.3, -0.1]])
        labels = torch.tensor([0, 1])
        losses = logit_distillation_loss(student, labels, teacher,
                                         temperature=4.0, alpha_ce=1.0)
        self.assertTrue(torch.equal(losses["total"], F.cross_entropy(student, labels)))

    def test_temperature_and_t_squared_scaling_are_correct(self):
        """The helper must match the reviewed soft-target KL expression."""

        student = torch.tensor([[1.0, -0.5], [0.2, 0.4]], requires_grad=True)
        teacher = torch.tensor([[0.1, 0.2], [0.3, -0.1]])
        labels = torch.tensor([0, 1])
        temperature, alpha = 2.0, 0.7
        losses = logit_distillation_loss(student, labels, teacher,
                                         temperature=temperature, alpha_ce=alpha)
        expected_kd = F.kl_div(
            F.log_softmax(student / temperature, dim=1),
            F.softmax(teacher / temperature, dim=1), reduction="batchmean") * 4.0
        expected = alpha * F.cross_entropy(student, labels) + (1.0 - alpha) * expected_kd
        self.assertTrue(torch.allclose(losses["kd"], expected_kd, rtol=0.0, atol=0.0))
        self.assertTrue(torch.allclose(losses["total"], expected, rtol=0.0, atol=0.0))

    def test_teacher_is_frozen_and_online_logits_repeat_exactly(self):
        """Teacher state and logits remain unchanged across Student updates."""

        torch.manual_seed(43)
        teacher = freeze_teacher(CNN1D(
            input_channels=1, class_count=2, channels=[4, 4, 4],
            kernel_sizes=[5, 5, 5], dropout=0.1,
            pooling_contract="multistat_average_max_endpoint"))
        student = CNN1D(input_channels=1, class_count=2, channels=[3, 3, 3],
                        kernel_sizes=[5, 5, 5], dropout=0.0,
                        pooling_contract="multistat_average_max_endpoint")
        before = state_dict_sha256(teacher)
        inputs, labels = torch.randn(5, 1, 32), torch.tensor([0, 1, 0, 1, 0])
        with torch.no_grad():
            first = teacher(inputs)
            second = teacher(inputs)
        self.assertTrue(torch.equal(first, second))
        optimizer = torch.optim.AdamW(student.parameters(), lr=1.0e-3)
        optimizer.zero_grad(set_to_none=True)
        losses = logit_distillation_loss(student(inputs), labels, first)
        losses["total"].backward()
        optimizer.step()
        self.assertEqual(before, state_dict_sha256(teacher))
        self.assertFalse(teacher.training)
        self.assertTrue(all(parameter.grad is None and not parameter.requires_grad
                            for parameter in teacher.parameters()))

    def test_three_statistic_losses_use_train_only_projectors(self):
        """All branches are aligned while Student deployment keys stay clean."""

        projectors = StatisticProjectors(3, 4)
        student_outputs = {
            "average_feature": torch.randn(2, 3),
            "maximum_feature": torch.randn(2, 3),
            "endpoint_feature": torch.randn(2, 3),
        }
        teacher_outputs = {key: torch.randn(2, 4) for key in student_outputs}
        losses = statistic_distillation_losses(
            student_outputs, teacher_outputs, projectors)
        self.assertEqual(set(losses), {
            "average_feature", "maximum_feature", "endpoint_feature", "total"})
        self.assertTrue(torch.equal(
            losses["total"], losses["average_feature"]
            + losses["maximum_feature"] + losses["endpoint_feature"]))
        student = CNN1D(input_channels=1, class_count=2, channels=[3, 3, 3],
                        kernel_sizes=[5, 5, 5], dropout=0.0,
                        pooling_contract="multistat_average_max_endpoint")
        self.assertFalse(any("projection" in key for key in student.state_dict()))
        self.assertTrue(any("projection" in key for key in projectors.state_dict()))


if __name__ == "__main__":
    unittest.main()
