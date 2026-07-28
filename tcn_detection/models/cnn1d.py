#!/usr/bin/env python3
"""Ordinary 1D-CNN classifier used as a non-causal neural baseline."""

from __future__ import print_function

from torch import nn


class CNN1D(nn.Module):
    """Classify a complete past-only window with conventional same-padding CNNs.

    Port contract:
        inputs: ``[batch, 5, L]`` normalized sensor histories containing no
            samples after the decision endpoint.
        output: ``[batch, 3]`` class logits.  Symmetric convolution is valid
            for this baseline because all L positions are already historical;
            only the proposed TCN additionally enforces within-window causality.
    """

    def __init__(self, input_channels=5, class_count=3, channels=(16, 16, 16), kernel_size=3, dropout=0.1):
        super().__init__()
        layers = []
        current = int(input_channels)
        for width in channels:
            layers.extend([nn.Conv1d(current, int(width), kernel_size=int(kernel_size), padding=int(kernel_size) // 2),
                           nn.ReLU(), nn.Dropout(float(dropout))])
            current = int(width)
        self.features = nn.Sequential(*layers)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.classifier = nn.Linear(current, int(class_count))

    def forward(self, inputs):
        """Return one three-class logit vector for each complete history window."""

        return self.classifier(self.pool(self.features(inputs)).squeeze(-1))
