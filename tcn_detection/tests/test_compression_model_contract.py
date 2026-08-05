#!/usr/bin/env python3
"""Step 1 contracts for the configurable multistat compression CNN.

These tests intentionally stay at the model boundary.  They use deterministic
synthetic inputs and the frozen Teacher checkpoint only to prove that adding
configuration and optional intermediate outputs did not alter the historical
graph.  No validation, IID, or OOD samples are loaded here.
"""

from __future__ import print_function

import unittest
from pathlib import Path

import torch
from torch import nn

from power_macro.tcn_detection.models.cnn1d import CNN1D
from power_macro.tcn_detection.train.common import estimate_macs, parameter_count


# ``parents[2]`` is the repository root (``power_macro``); run artifacts are
# intentionally kept below the existing ``tcn_detection/runs`` namespace.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TEACHER_CHECKPOINT = (REPOSITORY_ROOT / "tcn_detection" / "runs" /
                      "formal_v1_20260727_r1" /
                      "models" / "state_code_binary_multistat_training_v1_20260731_r1" /
                      "stage2" / "lr4em3_b256_seed20260727" /
                      "best_checkpoint.pt")


class _HistoricalMultistatCNN(nn.Module):
    """Reference implementation of the pre-compression Teacher graph.

    Keeping this tiny reference in the test makes the compatibility check
    independent of the new constructor.  Its three Conv/ReLU/Dropout stages,
    same padding, and Average/Maximum/Endpoint concatenation match the frozen
    ``multistat_w18_k5`` contract exactly.
    """

    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv1d(1, 18, kernel_size=5, padding=2), nn.ReLU(), nn.Dropout(0.1),
            nn.Conv1d(18, 18, kernel_size=5, padding=2), nn.ReLU(), nn.Dropout(0.1),
            nn.Conv1d(18, 18, kernel_size=5, padding=2), nn.ReLU(), nn.Dropout(0.1),
        )
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.max_pool = nn.AdaptiveMaxPool1d(1)
        self.classifier = nn.Linear(54, 2)

    def forward(self, inputs):
        """Return logits using the historical pooling order."""

        features = self.features(inputs)
        summary = torch.cat((self.pool(features).squeeze(-1),
                             self.max_pool(features).squeeze(-1),
                             features[:, :, -1]), dim=1)
        return self.classifier(summary)


class CompressionModelContractTests(unittest.TestCase):
    """Verify Step 1 behavior before any physical channel deletion."""

    def test_teacher_state_dict_strict_load_and_logits_are_unchanged(self):
        """The configurable model must reproduce the frozen historical graph."""

        checkpoint = torch.load(TEACHER_CHECKPOINT, map_location="cpu",
                                weights_only=False)
        config = checkpoint["model_config"]
        model = CNN1D(input_channels=1, class_count=2, channels=config["cnn_channels"],
                      kernel_size=config["kernel_size"], dropout=config["dropout"],
                      pooling_contract=config["pooling_contract"])
        model.load_state_dict(checkpoint["state_dict"], strict=True)
        reference = _HistoricalMultistatCNN()
        reference.load_state_dict(checkpoint["state_dict"], strict=True)
        model.eval()
        reference.eval()
        torch.manual_seed(20260805)
        inputs = torch.randn(7, 1, 32)
        with torch.no_grad():
            actual = model(inputs)
            expected = reference(inputs)
        # Evaluation mode disables Dropout, so exact tensor equality is a
        # meaningful regression check rather than a tolerance-based smoke test.
        self.assertTrue(torch.equal(actual, expected))

    def test_variable_channels_and_intermediate_contract(self):
        """All planned widths expose the same two-logit and feature contracts."""

        for channels in ([16, 16, 16], [12, 12, 12], [8, 12, 12]):
            model = CNN1D(input_channels=1, class_count=2, channels=channels,
                          kernel_sizes=[5, 5, 5], dropout=0.0,
                          pooling_contract="multistat_average_max_endpoint")
            model.eval()
            with torch.no_grad():
                outputs = model(torch.randn(3, 1, 32), return_intermediates=True)
            self.assertEqual(tuple(outputs["logits"].shape), (3, 2))
            for key in ("conv1_activation", "conv2_activation", "conv3_activation"):
                self.assertEqual(tuple(outputs[key].shape), (3, channels[int(key[4]) - 1], 32))
            for key in ("average_feature", "maximum_feature", "endpoint_feature"):
                self.assertEqual(tuple(outputs[key].shape), (3, channels[-1]))
            self.assertEqual(model.classifier.in_features, 3 * channels[-1])

    def test_pooling_order_is_average_then_maximum_then_endpoint(self):
        """The summary columns preserve the hardware-facing three-block order."""

        model = CNN1D(input_channels=1, class_count=2, channels=[2, 2, 2],
                      kernel_sizes=[3, 3, 3], dropout=0.0,
                      pooling_contract="multistat_average_max_endpoint")
        features = torch.tensor([[[1.0, 3.0, 2.0], [4.0, 0.0, 5.0]]])
        summary = model._summary(features)
        expected = torch.tensor([[2.0, 3.0, 3.0, 5.0, 2.0, 5.0]])
        self.assertTrue(torch.equal(summary, expected))

    def test_complexity_is_derived_from_the_configured_graph(self):
        """Changing widths or kernels must change measured cost automatically."""

        small = CNN1D(input_channels=1, class_count=2, channels=[8, 12, 12],
                      kernel_sizes=[5, 5, 5], dropout=0.0,
                      pooling_contract="multistat_average_max_endpoint")
        wide = CNN1D(input_channels=1, class_count=2, channels=[12, 12, 12],
                     kernel_sizes=[5, 5, 5], dropout=0.0,
                     pooling_contract="multistat_average_max_endpoint")
        short_kernel = CNN1D(input_channels=1, class_count=2, channels=[12, 12, 12],
                             kernel_sizes=[5, 3, 3], dropout=0.0,
                             pooling_contract="multistat_average_max_endpoint")
        self.assertLess(parameter_count(small), parameter_count(wide))
        self.assertLess(estimate_macs(small, 32, 1), estimate_macs(wide, 32, 1))
        self.assertLess(estimate_macs(short_kernel, 32, 1),
                        estimate_macs(wide, 32, 1))


if __name__ == "__main__":
    unittest.main()
