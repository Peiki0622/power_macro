#!/usr/bin/env python3
"""Lightweight convolutional autoencoder trained only on Safe L=16 windows."""

from __future__ import print_function

from torch import nn


class ConvAutoencoder(nn.Module):
    """Reconstruct normal five-channel sensor histories for anomaly scoring.

    Port contract:
        inputs/output: ``[batch, 5, 16]`` normalized causal histories.  The
            model has no labels at its input or output; per-window mean squared
            reconstruction error is converted to risk only by frozen normal
            quantiles in the training/evaluation pipeline.
    """

    def __init__(self, input_channels=5, channels=(8, 16), kernel_size=3):
        super().__init__()
        padding = int(kernel_size) // 2
        first, second = (int(channels[0]), int(channels[1]))
        self.encoder = nn.Sequential(nn.Conv1d(int(input_channels), first, kernel_size, padding=padding), nn.ReLU(),
                                     nn.Conv1d(first, second, kernel_size, padding=padding), nn.ReLU())
        self.decoder = nn.Sequential(nn.Conv1d(second, first, kernel_size, padding=padding), nn.ReLU(),
                                     nn.Conv1d(first, int(input_channels), kernel_size, padding=padding))

    def forward(self, inputs):
        """Return a reconstruction aligned sample-for-sample with ``inputs``."""

        return self.decoder(self.encoder(inputs))
