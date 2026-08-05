#!/usr/bin/env python3
"""Deterministic Critical-aware channel importance for the multistat CNN.

Importance is computed only from the caller-provided loader.  The production
runner must therefore pass a train-only calibration loader; this module does
not know how to discover validation or test files and cannot silently cross
that boundary.  Per-class Taylor contributions are collected as individual
samples and reduced with ``math.fsum`` so changing batch/order does not change
the accumulated ranking through floating-point summation order.
"""

from __future__ import print_function

import math

import numpy as np
import torch
import torch.nn.functional as F


_ACTIVATION_KEYS = ("conv1_activation", "conv2_activation", "conv3_activation")
_STATISTIC_KEYS = ("average_feature", "maximum_feature", "endpoint_feature")


def _sum_columns(contributions, width):
    """Reduce ``[sample, channel, ...]`` arrays with order-stable fsum."""

    if not contributions:
        return np.zeros(int(width), dtype=np.float64), 0
    arrays = [np.asarray(value, dtype=np.float64) for value in contributions]
    merged = np.concatenate(arrays, axis=0)
    values = np.empty(int(width), dtype=np.float64)
    for channel in range(int(width)):
        values[channel] = math.fsum(float(value) for value in merged[:, channel].reshape(-1))
    return values, int(merged.shape[0])


def normalize_scores(scores):
    """Normalize one layer's scores by its maximum, preserving all zeros."""

    values = np.asarray(scores, dtype=np.float64)
    maximum = float(np.max(values)) if values.size else 0.0
    if maximum <= 0.0 or not np.isfinite(maximum):
        return np.zeros_like(values)
    return values / maximum


def critical_aware_scores(safe_scores, critical_scores):
    """Apply the fixed per-class normalization and elementwise-max rule."""

    if len(safe_scores) != len(critical_scores):
        raise ValueError("Safe/Critical score stage counts differ")
    safe = [normalize_scores(value) for value in safe_scores]
    critical = [normalize_scores(value) for value in critical_scores]
    final = [np.maximum(left, right) for left, right in zip(safe, critical)]
    return {"safe": safe, "critical": critical, "final": final}


def _conv_modules(model):
    """Return the three convolution modules in graph order."""

    modules = [model.features[index] for index in (0, 3, 6)]
    if len(modules) != 3 or any(not hasattr(module, "out_channels") for module in modules):
        raise ValueError("importance requires a three-stage CNN")
    return modules


def compute_taylor_scores(model, loader, device="cpu"):
    """Accumulate Safe/Critical first-order Taylor scores from one loader.

    ``loader`` is deliberately treated as opaque; labels are used only to
    separate the two classes and no split metadata is inferred or loaded.
    Scores are mean ``abs(activation * d(loss)/d(activation))`` over selected
    samples and temporal positions, independently for every stage.
    """

    modules = _conv_modules(model)
    widths = [int(module.out_channels) for module in modules]
    contributions = {0: [[] for _ in widths], 1: [[] for _ in widths]}
    counts = {0: 0, 1: 0}
    was_training = model.training
    model.eval()
    try:
        for inputs, labels in loader:
            inputs = inputs.to(device)
            labels = labels.to(device).long()
            for class_id in (0, 1):
                selected = labels == int(class_id)
                if not bool(torch.any(selected)):
                    continue
                model.zero_grad(set_to_none=True)
                outputs = model(inputs, return_intermediates=True)
                activations = [outputs[key] for key in _ACTIVATION_KEYS]
                for activation in activations:
                    activation.retain_grad()
                loss = F.cross_entropy(outputs["logits"][selected],
                                       labels[selected], reduction="sum")
                loss.backward()
                for stage, activation in enumerate(activations):
                    contribution = (activation[selected].detach() *
                                    activation.grad[selected].detach()).abs().cpu().numpy()
                    contributions[class_id][stage].append(contribution)
                counts[class_id] += int(torch.sum(selected).item())
    finally:
        model.train(was_training)

    safe_scores = []
    critical_scores = []
    for stage, width in enumerate(widths):
        safe_total, safe_count = _sum_columns(contributions[0][stage], width)
        critical_total, critical_count = _sum_columns(contributions[1][stage], width)
        safe_scores.append(safe_total / float(max(1, safe_count)))
        critical_scores.append(critical_total / float(max(1, critical_count)))
    merged = critical_aware_scores(safe_scores, critical_scores)
    merged.update({"safe_raw": safe_scores, "critical_raw": critical_scores,
                   "sample_counts": {"safe": counts[0], "critical": counts[1]}})
    return merged


def filter_norm_scores(model):
    """Return L1 and L2 filter norms as audit-only comparison rankings."""

    l1 = []
    l2 = []
    for module in _conv_modules(model):
        weights = module.weight.detach().reshape(module.out_channels, -1)
        l1.append(weights.abs().sum(dim=1).cpu().numpy().astype(np.float64))
        l2.append(torch.sqrt((weights * weights).sum(dim=1)).cpu().numpy().astype(np.float64))
    return {"l1": l1, "l2": l2}


def compute_conv3_statistic_audit(model, loader, device="cpu"):
    """Measure Conv3 contribution separately for Average/Maximum/Endpoint."""

    modules = _conv_modules(model)
    width = int(modules[-1].out_channels)
    contributions = {class_id: {key: [] for key in _STATISTIC_KEYS}
                     for class_id in (0, 1)}
    was_training = model.training
    model.eval()
    try:
        for inputs, labels in loader:
            inputs, labels = inputs.to(device), labels.to(device).long()
            for class_id in (0, 1):
                selected = labels == int(class_id)
                if not bool(torch.any(selected)):
                    continue
                model.zero_grad(set_to_none=True)
                outputs = model(inputs, return_intermediates=True)
                branch_values = {key: outputs[key] for key in _STATISTIC_KEYS}
                for value in branch_values.values():
                    value.retain_grad()
                # The public model computes an equivalent pooling expression
                # internally for logits and returns a second expression for
                # diagnostics.  Build each branch's classifier contribution
                # explicitly so the diagnostic tensor remains connected to a
                # meaningful loss and receives a real gradient.
                width_range = int(model.classifier.in_features // 3)
                for branch_index, key in enumerate(_STATISTIC_KEYS):
                    model.zero_grad(set_to_none=True)
                    start = branch_index * width_range
                    branch_logits = torch.matmul(
                        branch_values[key], model.classifier.weight[:, start:start + width_range].t())
                    branch_logits = branch_logits + model.classifier.bias
                    loss = F.cross_entropy(branch_logits[selected],
                                           labels[selected], reduction="sum")
                    loss.backward(retain_graph=branch_index < len(_STATISTIC_KEYS) - 1)
                    value = branch_values[key]
                    contribution = (value[selected].detach() *
                                    value.grad[selected].detach()).abs().cpu().numpy()
                    contributions[class_id][key].append(contribution)
    finally:
        model.train(was_training)
    report = {}
    for class_id in (0, 1):
        report[str(class_id)] = {}
        for key in _STATISTIC_KEYS:
            total, count = _sum_columns(contributions[class_id][key], width)
            report[str(class_id)][key] = total / float(max(1, count))
    return report


def rank_channels(scores):
    """Return deterministic low-to-high channel rankings for each stage."""

    return [sorted(range(len(values)), key=lambda index: (float(values[index]), index))
            for values in scores]
