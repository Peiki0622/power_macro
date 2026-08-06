"""Structural and deterministic tests for the FP no-FC control graph."""

from __future__ import print_function

import unittest

import torch
from torch import nn

from power_macro.tcn_detection.bnn.nofc_model import (
    BinaryNoFCModel,
    FPNoFCModel,
    vote_from_logits,
)


class BnnModelContractTests(unittest.TestCase):
    """Bind the two reviewed widths before binary layers are introduced."""

    def test_fp_control_has_fixed_temporal_head_and_no_fc(self):
        """Both widths preserve L32 and expose one head channel per position."""

        for width in (8, 16):
            model = FPNoFCModel(width)
            modules = list(model.modules())
            self.assertFalse(any(isinstance(module, nn.Linear)
                                for module in modules))
            output = model(torch.zeros(2, 32, 32))
            self.assertEqual(tuple(output["temporal_logits"].shape), (2, 1, 32))
            self.assertEqual(tuple(output["score"].shape), (2,))

    def test_wrong_shapes_and_widths_fail_closed(self):
        """A model cannot silently accept scalar code or a third architecture."""

        with self.assertRaises(ValueError):
            FPNoFCModel(4)
        model = FPNoFCModel(8)
        with self.assertRaises(ValueError):
            model(torch.zeros(2, 1, 32))
        with self.assertRaises(ValueError):
            model(torch.zeros(2, 32, 31))
        with self.assertRaises(ValueError):
            model(torch.full((2, 32, 32), 2.0))

    def test_vote_ties_and_boundaries_are_deterministic(self):
        """K=1/K=32 and a zero-logit tie obey the deployment convention."""

        logits = torch.tensor([[[0.0, -1.0, 1.0, 0.0]]])
        alarm, counts = vote_from_logits(logits, 3)
        self.assertEqual(counts.tolist(), [3])
        self.assertEqual(alarm.tolist(), [True])
        self.assertEqual(vote_from_logits(logits, 4)[0].tolist(), [False])
        self.assertEqual(vote_from_logits(logits, 1)[0].tolist(), [True])
        with self.assertRaises(ValueError):
            vote_from_logits(logits, 0)
        with self.assertRaises(ValueError):
            vote_from_logits(logits, 5)

    def test_eval_forward_is_reproducible(self):
        """Dropout-free FP control outputs are stable under repeated evaluation."""

        torch.manual_seed(11)
        model = FPNoFCModel(8)
        model.eval()
        inputs = torch.arange(2 * 32 * 32, dtype=torch.float32).reshape(2, 32, 32)
        inputs = inputs.remainder(2.0)
        with torch.no_grad():
            first = model(inputs)["temporal_logits"]
            second = model(inputs)["temporal_logits"]
        self.assertTrue(torch.equal(first, second))

    def test_binary_stages_have_shadow_gradients_and_reviewed_bit_outputs(self):
        """W1A8/W1A1 retain trainable shadows without creating a classifier."""

        inputs = torch.zeros(3, 32, 32)
        labels = torch.tensor([0.0, 1.0, 0.0])
        w1a8 = BinaryNoFCModel(8, "w1a8")
        output_a8 = w1a8(inputs)
        self.assertEqual(tuple(output_a8["temporal_logits"].shape), (3, 1, 32))
        self.assertTrue(torch.all((output_a8["temporal_bits"] == 0)
                                  | (output_a8["temporal_bits"] == 1)))
        loss = torch.nn.functional.binary_cross_entropy_with_logits(
            output_a8["score"], labels)
        loss.backward()
        self.assertIsNotNone(w1a8.conv1.weight.grad)

        w1a1 = BinaryNoFCModel(8, "w1a1")
        w1a1.initialize_from_binary(w1a8)
        output_a1 = w1a1(inputs)
        self.assertTrue(torch.all((output_a1["temporal_bits"] == 0)
                                  | (output_a1["temporal_bits"] == 1)))
        self.assertEqual(tuple(w1a1.hard_vote(inputs, 1)["alarm"].shape), (3,))


if __name__ == "__main__":
    unittest.main()
