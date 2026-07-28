#!/usr/bin/env python3
"""Causal residual blocks used exclusively by the online TCN classifier."""

from __future__ import print_function

import torch
from torch import nn


class CausalConv1d(nn.Module):
    """One-dimensional convolution whose output at t cannot read input after t.

    Port contract:
        input: ``[batch, in_channels, sequence_length]`` chronological tensor.
        output: ``[batch, out_channels, sequence_length]`` tensor aligned with
            the input.  Left-only padding is inserted before the convolution;
            unlike symmetric ``padding=...``, no right-side zero padding can
            turn a future sample into an apparent past sample.
    """

    def __init__(self, in_channels, out_channels, kernel_size, dilation=1, bias=True):
        super().__init__()
        self.left_padding = (int(kernel_size) - 1) * int(dilation)
        self.convolution = nn.Conv1d(in_channels, out_channels, kernel_size, dilation=dilation, padding=0, bias=bias)

    def forward(self, inputs):
        """Apply explicit left padding and preserve the original time length."""

        return self.convolution(nn.functional.pad(inputs, (self.left_padding, 0)))


class CausalResidualBlock(nn.Module):
    """Two causal convolutions, residual projection, ReLU, and dropout.

    The residual path uses a pointwise projection only when channel counts
    differ.  A pointwise operation has no temporal receptive field, so it does
    not weaken the causal guarantee established by :class:`CausalConv1d`.
    """

    def __init__(self, in_channels, out_channels, kernel_size, dilation, dropout):
        super().__init__()
        self.first = CausalConv1d(in_channels, out_channels, kernel_size, dilation)
        self.second = CausalConv1d(out_channels, out_channels, kernel_size, dilation)
        self.activation = nn.ReLU()
        self.dropout = nn.Dropout(float(dropout))
        self.residual = nn.Identity() if in_channels == out_channels else nn.Conv1d(in_channels, out_channels, kernel_size=1)

    def forward(self, inputs):
        """Return a causal sequence with the same length as ``inputs``."""

        hidden = self.dropout(self.activation(self.first(inputs)))
        hidden = self.dropout(self.activation(self.second(hidden)))
        return self.activation(hidden + self.residual(inputs))
