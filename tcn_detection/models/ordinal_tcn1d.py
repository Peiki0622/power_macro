#!/usr/bin/env python3
"""Causal shared-backbone TCN with ordered Risk and Critical heads."""

from __future__ import print_function

import torch
from torch import nn

from power_macro.tcn_detection.models.causal_blocks import CausalResidualBlock


class OrdinalTCN1D(nn.Module):
    """Predict nested Risk and Critical events from one causal representation.

    The two logits mean ``P(y >= Warning)`` and ``P(y == Critical)``.  They use
    one residual TCN backbone so both decisions learn the same chronological
    evidence, while separate 1x1 heads retain enough freedom for severity.
    ``forward_sequence`` exists for the same future-mutation audit as TCN1D.
    """

    output_semantics = "ordinal_risk_critical"

    def __init__(self, input_channels=5, hidden_channels=16, kernel_size=3,
                 dilations=(1, 2, 4), dropout=0.1):
        super().__init__()
        blocks = []
        channels = int(input_channels)
        for dilation in dilations:
            blocks.append(CausalResidualBlock(channels, int(hidden_channels), int(kernel_size),
                                              int(dilation), float(dropout)))
            channels = int(hidden_channels)
        self.network = nn.Sequential(*blocks)
        self.ordinal_heads = nn.Conv1d(channels, 2, kernel_size=1)

    def forward_sequence(self, inputs):
        """Return [Risk,Critical] logits at every causal time point."""

        return self.ordinal_heads(self.network(inputs))

    def forward(self, inputs):
        """Return endpoint logits consumed by the ordinal BCE objective."""

        return self.forward_sequence(inputs)[:, :, -1]

    @staticmethod
    def probabilities_from_logits(logits):
        """Map nested binary heads to valid Safe/Warning/Critical probabilities.

        Independent sigmoid heads can produce ``Pcritical > Prisk``.  Clamping
        Critical to Risk enforces the set inclusion ``Critical subset Risk``;
        Warning is the remaining Risk mass and Safe is its complement.  Every
        component is therefore non-negative and rows sum exactly to one, while
        the consistency penalty in training discourages frequent clamping.
        """

        head_probabilities = torch.sigmoid(logits)
        risk = head_probabilities[:, 0]
        critical = torch.minimum(risk, head_probabilities[:, 1])
        return torch.stack((1.0 - risk, risk - critical, critical), dim=1)


class OrdinalTimeTCN1D(OrdinalTCN1D):
    """Add a four-way time-to-violation head to the shared ordinal backbone."""

    output_semantics = "ordinal_risk_critical_time"

    def __init__(self, input_channels=5, hidden_channels=16, kernel_size=3,
                 dilations=(1, 2, 4), dropout=0.1):
        super().__init__(input_channels=input_channels, hidden_channels=hidden_channels,
                         kernel_size=kernel_size, dilations=dilations, dropout=dropout)
        # Channels 0:2 retain the Risk/Critical endpoint contract.  Channels
        # 2:6 classify none, 1-2, 3-4, and 5-8 samples to first violation.
        # All six heads observe the same causal representation, so auxiliary
        # timing supervision cannot introduce an inference-only feature.
        self.ordinal_heads = nn.Conv1d(int(hidden_channels), 6, kernel_size=1)

    @staticmethod
    def probabilities_from_logits(logits):
        """Expose only mapped three-class probabilities to public evaluators."""

        return OrdinalTCN1D.probabilities_from_logits(logits[:, :2])
