#!/usr/bin/env python3
"""Causal dilated residual TCN for three-level future timing-risk prediction."""

from __future__ import print_function

from torch import nn

from power_macro.tcn_detection.models.causal_blocks import CausalResidualBlock


class TCN1D(nn.Module):
    """Map five online Vernier channels to Safe/Warning/Critical logits.

    Port contract:
        inputs: ``[batch, 5, L]`` normalized causal sensor history.
        sequence logits: ``[batch, 3, L]`` where output time t depends only on
            input samples up to t.  This public method exists specifically for
            the causality test; deployment consumes only its final time point.
        final logits: ``[batch, 3]`` classification at the current window end.
    """

    def __init__(self, input_channels=5, class_count=3, hidden_channels=16, kernel_size=3, dilations=(1, 2, 4), dropout=0.1):
        super().__init__()
        blocks = []
        channels = int(input_channels)
        for dilation in dilations:
            blocks.append(CausalResidualBlock(channels, int(hidden_channels), int(kernel_size), int(dilation), float(dropout)))
            channels = int(hidden_channels)
        self.network = nn.Sequential(*blocks)
        self.classifier = nn.Conv1d(channels, int(class_count), kernel_size=1)

    def forward_sequence(self, inputs):
        """Return causal logits at every history time step for audit tests."""

        return self.classifier(self.network(inputs))

    def forward(self, inputs):
        """Return only the current endpoint logits used by the classifier loss."""

        return self.forward_sequence(inputs)[:, :, -1]
