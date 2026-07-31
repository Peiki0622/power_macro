#!/usr/bin/env python3
"""Compact 1D-CNN for classifying complete past-only sensor histories."""

from __future__ import print_function

import torch
from torch import nn

from power_macro.tcn_detection.models.causal_blocks import CausalConv1d


class CNN1D(nn.Module):
    """Classify a complete past-only window with conventional same-padding CNNs.

    Port contract:
        inputs: ``[batch, C, L]`` normalized sensor histories containing no
            samples after the decision endpoint.  The final binary state model
            uses C=1 raw code; legacy future-risk experiments use C=5 channels.
        output: ``[batch, class_count]`` logits.  Symmetric convolution remains
            temporally valid because every real sample in the complete window
            is at or before the decision endpoint.  Unlike the TCN, this model
            does not promise meaningful logits at intermediate positions.

    The global average head deliberately makes parameter count independent of
    L, allowing L8/L16/L32 to share one architecture definition.  It also keeps
    the deployment graph to Conv1d/ReLU/Dropout/average-pool/Linear operations,
    avoiding residual projections and dilated double-convolution blocks.
    """

    def __init__(self, input_channels=5, class_count=3, channels=(16, 16, 16),
                 kernel_size=3, dropout=0.1,
                 pooling_contract="adaptive_average_over_past_window",
                 dilations=None):
        super().__init__()
        self.pooling_contract = str(pooling_contract)
        widths = tuple(int(width) for width in channels)
        resolved_dilations = (tuple(1 for _ in widths) if dilations is None
                              else tuple(int(value) for value in dilations))
        if len(resolved_dilations) != len(widths):
            raise ValueError("CNN dilation count must match channel-stage count")
        if any(value < 1 for value in resolved_dilations):
            raise ValueError("CNN dilations must be positive")
        endpoint_mode = self.pooling_contract == "causal_endpoint"
        layers = []
        current = int(input_channels)
        for width, dilation in zip(widths, resolved_dilations):
            # The historical average/multistat branches use conventional same
            # padding because their output summarizes a complete past-only
            # window.  The endpoint branch instead uses explicit left padding:
            # its final feature must cover earlier samples without injecting
            # right-side zeros at every layer.  It remains a compact CNN with
            # one convolution per stage, unlike the TCN's two-convolution
            # residual blocks and projection paths.
            convolution = (CausalConv1d(
                current, width, int(kernel_size), dilation=dilation)
                if endpoint_mode else nn.Conv1d(
                    current, width, kernel_size=int(kernel_size),
                    dilation=dilation,
                    padding=((int(kernel_size) - 1) * dilation) // 2))
            layers.extend([convolution,
                           nn.ReLU(), nn.Dropout(float(dropout))])
            current = width
        self.features = nn.Sequential(*layers)
        if self.pooling_contract == "adaptive_average_over_past_window":
            # Preserve the exact module names and dimensions used by historical
            # checkpoints; adding new variants must not invalidate the frozen
            # one-shot CNN release.
            self.pool = nn.AdaptiveAvgPool1d(1)
            classifier_inputs = current
        elif self.pooling_contract == "multistat_average_max_endpoint":
            self.pool = nn.AdaptiveAvgPool1d(1)
            self.max_pool = nn.AdaptiveMaxPool1d(1)
            classifier_inputs = current * 3
        elif self.pooling_contract == "causal_endpoint":
            self.pool = None
            classifier_inputs = current
        else:
            raise ValueError("unknown CNN pooling contract: {}".format(
                self.pooling_contract))
        self.classifier = nn.Linear(classifier_inputs, int(class_count))

    def forward(self, inputs):
        """Return one configured-class logit vector per complete history."""

        features = self.features(inputs)
        if self.pooling_contract == "adaptive_average_over_past_window":
            summary = self.pool(features).squeeze(-1)
        elif self.pooling_contract == "multistat_average_max_endpoint":
            # Average describes sustained level, maximum preserves short peaks,
            # and the final position explicitly represents the current sample.
            # Concatenating all three prevents global pooling from erasing the
            # endpoint semantics that distinguish current-state monitoring.
            summary = torch.cat((
                self.pool(features).squeeze(-1),
                self.max_pool(features).squeeze(-1), features[:, :, -1]), dim=1)
        else:
            summary = features[:, :, -1]
        return self.classifier(summary)
