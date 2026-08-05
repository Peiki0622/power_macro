#!/usr/bin/env python3
"""Minimal loss and Teacher-freezing contracts for CNN distillation."""

from __future__ import print_function

import hashlib

import torch
import torch.nn.functional as F
from torch import nn


STATISTIC_KEYS = ("average_feature", "maximum_feature", "endpoint_feature")


class StatisticProjectors(nn.Module):
    """Three independent train-only projections into Teacher feature space."""

    def __init__(self, student_channels, teacher_channels):
        super().__init__()
        self.projections = nn.ModuleDict({
            key: nn.Linear(int(student_channels), int(teacher_channels))
            for key in STATISTIC_KEYS})
        if int(student_channels) == int(teacher_channels):
            # Identity is the least-assumptive starting point when shapes
            # already match; the three branches remain independently trainable.
            for projection in self.projections.values():
                nn.init.eye_(projection.weight)
                nn.init.zeros_(projection.bias)

    def forward(self, key, value):
        """Project one named branch and reject incomplete branch names."""

        if key not in self.projections:
            raise ValueError("unknown statistic branch: {}".format(key))
        return self.projections[key](value)


def freeze_teacher(model):
    """Put the frozen Teacher in eval mode and disable every parameter gradient."""

    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    return model


def state_dict_sha256(model):
    """Hash tensor names, dtypes, shapes, and bytes for mutation detection."""

    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        value = tensor.detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(str(tuple(value.shape)).encode("ascii"))
        digest.update(value.numpy().tobytes())
    return digest.hexdigest()


def logit_distillation_loss(student_logits, labels, teacher_logits,
                             temperature=4.0, alpha_ce=0.5):
    """Return total, CE, and temperature-scaled KL loss components.

    PyTorch's ``kl_div`` expects log-probabilities first, so Student is passed
    as ``log_softmax`` and frozen Teacher as the target ``softmax``.  The fixed
    ``T**2`` multiplier preserves gradient magnitude under temperature scaling.
    Setting ``alpha_ce=1`` exactly reduces the objective to ordinary CE.
    """

    temperature = float(temperature)
    alpha_ce = float(alpha_ce)
    if temperature <= 0.0 or not 0.0 <= alpha_ce <= 1.0:
        raise ValueError("invalid distillation temperature or CE weight")
    ce_loss = F.cross_entropy(student_logits, labels)
    kd_loss = F.kl_div(
        F.log_softmax(student_logits / temperature, dim=1),
        F.softmax(teacher_logits.detach() / temperature, dim=1),
        reduction="batchmean") * (temperature ** 2)
    total = ce_loss if alpha_ce == 1.0 else (
        alpha_ce * ce_loss + (1.0 - alpha_ce) * kd_loss)
    return {"total": total, "ce": ce_loss, "kd": kd_loss}


def statistic_distillation_losses(student_outputs, teacher_outputs, projectors):
    """Return all three SmoothL1 branch losses and their unweighted sum."""

    losses = {}
    for key in STATISTIC_KEYS:
        if key not in student_outputs or key not in teacher_outputs:
            raise ValueError("missing multistat feature: {}".format(key))
        losses[key] = F.smooth_l1_loss(
            projectors(key, student_outputs[key]), teacher_outputs[key].detach())
    losses["total"] = sum(losses[key] for key in STATISTIC_KEYS)
    return losses
