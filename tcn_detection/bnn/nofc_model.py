"""No-FC thermometer models shared by the FP control and binary stages.

The floating-point control deliberately keeps the exact three-convolution graph
of the target BNN.  It is an analysis model only: its BatchNorm state is useful
while training, but it is never accepted as a deployment package.
"""

from __future__ import print_function

import torch
from torch import nn

from power_macro.tcn_detection.bnn.binary_layers import (
    BinaryConv1d,
    fake_quantize_int8,
    ste_binary_bits,
)


WINDOW_LENGTH = 32
THERMOMETER_CHANNELS = 32
ALLOWED_WIDTHS = (8, 16)


def validate_width(width):
    """Return one of the two explicitly approved Stage-1B channel widths."""

    width = int(width)
    if width not in ALLOWED_WIDTHS:
        raise ValueError("Stage-1B width must be 8 or 16")
    return width


def _validate_input(inputs):
    """Fail closed on a tensor that could violate the binary input contract."""

    if not isinstance(inputs, torch.Tensor) or inputs.ndim != 3:
        raise ValueError("thermometer input must have shape [N,32,32]")
    if tuple(inputs.shape[1:]) != (THERMOMETER_CHANNELS, WINDOW_LENGTH):
        raise ValueError("thermometer input must have shape [N,32,32]")
    if inputs.shape[0] < 1 or not torch.is_floating_point(inputs):
        raise ValueError("thermometer input must be a non-empty floating tensor")
    if torch.any(inputs < 0.0) or torch.any(inputs > 1.0):
        raise ValueError("thermometer input bits must be in [0,1]")


def temporal_bits(temporal_logits):
    """Apply the frozen head sign convention and return uint-like torch bits."""

    if temporal_logits.ndim != 3 or temporal_logits.shape[1] != 1:
        raise ValueError("temporal head must have shape [N,1,L]")
    # ``>=`` is the single tie rule shared with package threshold folding and
    # NumPy bit-true inference.  Converting to the logits dtype keeps the hard
    # result differentiable only when a caller wraps it in an STE explicitly.
    return (temporal_logits >= 0.0).to(dtype=temporal_logits.dtype)


def vote_from_logits(temporal_logits, k):
    """Return K-of-L alarms and counts from temporal head logits."""

    k = int(k)
    length = int(temporal_logits.shape[-1])
    if not 1 <= k <= length:
        raise ValueError("vote K must be within the temporal head length")
    bits = temporal_bits(temporal_logits)
    counts = bits[:, 0, :].sum(dim=1)
    return counts.to(dtype=torch.int64) >= k, counts.to(dtype=torch.int64)


class FPNoFCModel(nn.Module):
    """FP control graph with no classifier and a 32-position detection head.

    Inputs are deterministic 0/1 thermometer channels in ``[N,32,32]``.  The
    first two stages use same-padded Conv1d/BatchNorm/ReLU blocks; the 1x1 head
    retains a real logit at every temporal position so the exact same K-of-32
    decision can be applied when comparing against a binary checkpoint.
    """

    architecture_id = "fp_therm32_nofc_l32"

    def __init__(self, width, window_length=WINDOW_LENGTH):
        super().__init__()
        self.width = validate_width(width)
        if int(window_length) != WINDOW_LENGTH:
            raise ValueError("Stage-1B requires an L32 window")
        self.window_length = WINDOW_LENGTH
        self.conv1 = nn.Conv1d(THERMOMETER_CHANNELS, self.width, 3,
                               padding=1, bias=False)
        self.bn1 = nn.BatchNorm1d(self.width)
        self.conv2 = nn.Conv1d(self.width, self.width, 3,
                               padding=1, bias=False)
        self.bn2 = nn.BatchNorm1d(self.width)
        self.head = nn.Conv1d(self.width, 1, 1, padding=0, bias=False)
        self.head_bn = nn.BatchNorm1d(1)

    def forward(self, inputs):
        """Return temporal logits and their mean training score."""

        _validate_input(inputs)
        features = torch.relu(self.bn1(self.conv1(inputs)))
        features = torch.relu(self.bn2(self.conv2(features)))
        temporal_logits = self.head_bn(self.head(features))
        return {
            "temporal_logits": temporal_logits,
            "score": temporal_logits.mean(dim=(1, 2)),
        }

    def hard_vote(self, inputs, k):
        """Evaluate the FP head with the common deterministic K-of-32 rule."""

        output = self.forward(inputs)
        alarm, counts = vote_from_logits(output["temporal_logits"], k)
        return {"alarm": alarm, "vote_count": counts,
                "temporal_logits": output["temporal_logits"]}


class BinaryNoFCModel(nn.Module):
    """W1A8 or W1A1 no-FC model with the same reviewed convolution topology.

    Real parameters remain in the three ``BinaryConv1d.weight`` tensors.  In
    W1A8, hidden values use signed fake-int8 activations; in W1A1 every hidden
    and head activation has a 0/1 bit forward value.  The W1A1 ``score`` is a
    training-only STE surrogate for the deployed temporal vote count.
    """

    architecture_id = "bnn_therm32_w1a1_nofc_l32"

    def __init__(self, width, mode):
        super().__init__()
        self.width = validate_width(width)
        self.mode = str(mode)
        if self.mode not in ("w1a8", "w1a1"):
            raise ValueError("binary no-FC mode must be w1a8 or w1a1")
        self.window_length = WINDOW_LENGTH
        self.conv1 = BinaryConv1d(THERMOMETER_CHANNELS, self.width, 3, padding=1)
        self.bn1 = nn.BatchNorm1d(self.width)
        self.conv2 = BinaryConv1d(self.width, self.width, 3, padding=1)
        self.bn2 = nn.BatchNorm1d(self.width)
        self.head = BinaryConv1d(self.width, 1, 1, padding=0)
        self.head_bn = nn.BatchNorm1d(1)

    def initialize_from_fp(self, source):
        """Copy matching FP parameters, including BN running statistics.

        The FP and binary classes intentionally use the same state-dict names.
        Strict loading therefore proves that pretraining did not add a hidden
        classifier or a shape-changing operation before W1A8 begins.
        """

        if not isinstance(source, FPNoFCModel) or source.width != self.width:
            raise ValueError("binary stage requires an FP source with the same width")
        self.load_state_dict(source.state_dict(), strict=True)

    def initialize_from_binary(self, source):
        """Copy the preceding W1A8 shadow state before W1A1 fine tuning."""

        if (not isinstance(source, BinaryNoFCModel)
                or source.width != self.width or source.mode != "w1a8"):
            raise ValueError("W1A1 stage requires a same-width W1A8 source")
        self.load_state_dict(source.state_dict(), strict=True)

    def _activation(self, values):
        """Select the reviewed activation format for the current training stage."""

        return (fake_quantize_int8(values) if self.mode == "w1a8"
                else ste_binary_bits(values))

    def forward(self, inputs):
        """Return temporal head values and a scalar BCE training surrogate."""

        _validate_input(inputs)
        # The raw thermometer bits stay binary in both stages.  W1A8 becomes
        # signed only after the first BN, whereas W1A1 remains logical bits.
        features = self._activation(self.bn1(self.conv1(inputs, input_is_bits=True)))
        features = self._activation(self.bn2(self.conv2(
            features, input_is_bits=self.mode == "w1a1")))
        temporal_logits = self.head_bn(self.head(
            features, input_is_bits=self.mode == "w1a1"))
        if self.mode == "w1a8":
            temporal_bits = temporal_bits_from_logits(temporal_logits)
            score = temporal_logits.mean(dim=(1, 2))
        else:
            # The hard 0/1 values are emitted in forward execution.  Scaling
            # the mean into a logit is only for BCE gradients and is absent from
            # inference/export, which compares the raw vote count to K.
            temporal_bits = ste_binary_bits(temporal_logits)
            score = (temporal_bits.mean(dim=(1, 2)) - 0.5) * 16.0
        return {"temporal_logits": temporal_logits,
                "temporal_bits": temporal_bits,
                "score": score}

    def hard_vote(self, inputs, k):
        """Return final 0/1 head bits and the K-of-32 alarm during evaluation."""

        output = self.forward(inputs)
        if self.mode == "w1a8":
            bits = temporal_bits_from_logits(output["temporal_logits"])
        else:
            bits = output["temporal_bits"]
        k = int(k)
        if not 1 <= k <= self.window_length:
            raise ValueError("vote K must be within the temporal head length")
        counts = bits[:, 0, :].sum(dim=1).to(dtype=torch.int64)
        return {"alarm": counts >= k, "vote_count": counts,
                "temporal_bits": bits}


def temporal_bits_from_logits(temporal_logits):
    """Alias the common hard-head rule without conflating it with STE output."""

    return temporal_bits(temporal_logits)
