"""Small straight-through binary operators for the no-FC BNN.

The training representation uses float tensors so PyTorch can optimize real
shadow weights.  Every deployment-relevant forward value is nevertheless
binary: a stored bit zero represents bipolar -1 and a stored bit one represents
bipolar +1.  The later NumPy package uses precisely this convention for XNOR.
"""

from __future__ import print_function

import torch
import torch.nn.functional as functional
from torch import nn


def ste_bipolar(values):
    """Return forward +/-1 signs while passing an identity STE gradient.

    Zero maps to +1.  The tie rule is intentionally explicit because export
    serializes the same ``>= 0`` rule into the packed one-bit weight payload.
    """

    hard = torch.where(values >= 0.0, torch.ones_like(values),
                       -torch.ones_like(values))
    return values + (hard - values).detach()


def ste_binary_bits(values):
    """Return forward 0/1 bits while retaining a straight-through gradient."""

    hard = (values >= 0.0).to(dtype=values.dtype)
    return values + (hard - values).detach()


def fake_quantize_int8(values):
    """Use symmetric signed 8-bit fake quantization in the W1A8 stage.

    BatchNorm output is clipped to [-1,1], rounded to one of 255 signed levels,
    and evaluated with an STE.  It is strictly a training transition format;
    final W1A1 export never stores this tensor or its scale.
    """

    clipped = torch.clamp(values, -1.0, 1.0)
    hard = torch.round(clipped * 127.0) / 127.0
    return values + (hard - values).detach()


def binary_weight_bits(weight):
    """Return the exact 0/1 storage bits corresponding to a shadow weight."""

    if not isinstance(weight, torch.Tensor):
        raise TypeError("binary weight must be a torch tensor")
    return (weight >= 0.0).to(dtype=torch.uint8)


class BinaryConv1d(nn.Module):
    """Bias-free convolution with binary shadow-weight forward semantics.

    ``input_is_bits=True`` implements the first/W1A1 layers.  Padding happens
    while values are still logical bits, so padded zero becomes bipolar -1;
    this is exactly the fixed padding convention used by bit-true XNOR.  The
    W1A8 transition uses signed fake-quantized activations instead and retains
    numeric zero padding, because it is never exported as a one-bit package.
    """

    def __init__(self, input_channels, output_channels, kernel_size, padding=0):
        super().__init__()
        self.input_channels = int(input_channels)
        self.output_channels = int(output_channels)
        self.kernel_size = int(kernel_size)
        self.padding = int(padding)
        if (self.input_channels < 1 or self.output_channels < 1
                or self.kernel_size < 1 or self.padding < 0):
            raise ValueError("BinaryConv1d dimensions must be positive")
        self.weight = nn.Parameter(torch.empty(
            self.output_channels, self.input_channels, self.kernel_size))
        nn.init.kaiming_uniform_(self.weight, a=5 ** 0.5)

    def forward(self, inputs, input_is_bits):
        """Convolve a bit or W1A8 activation tensor with signed binary weights."""

        if inputs.ndim != 3 or inputs.shape[1] != self.input_channels:
            raise ValueError("BinaryConv1d input channel count differs from weights")
        if bool(input_is_bits):
            if torch.any(inputs < 0.0) or torch.any(inputs > 1.0):
                raise ValueError("binary activations must be logical bits in [0,1]")
            padded = functional.pad(inputs, (self.padding, self.padding), value=0.0)
            activations = padded * 2.0 - 1.0
            padding = 0
        else:
            activations = inputs
            padding = self.padding
        return functional.conv1d(activations, ste_bipolar(self.weight),
                                 bias=None, stride=1, padding=padding)
