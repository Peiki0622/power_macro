#!/usr/bin/env python3
"""Shared deterministic CPU-training utilities for CNN, TCN, and CAE."""

from __future__ import print_function

import json
import os
import random
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset, WeightedRandomSampler

from power_macro.tcn_detection.models.cnn1d import CNN1D
from power_macro.tcn_detection.models.ordinal_tcn1d import OrdinalTCN1D, OrdinalTimeTCN1D
from power_macro.tcn_detection.models.tcn1d import TCN1D


def read_json(path):
    """Read one versioned configuration without applying implicit defaults."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def configure_cpu(seed, threads):
    """Set deterministic seeds and bound each concurrent CPU training process.

    The project deliberately launches several small models concurrently.  A
    per-process cap prevents each BLAS/PyTorch worker from claiming all 96 host
    cores, which would increase contention and make reported latency unstable.
    """

    seed = int(seed)
    thread_count = int(threads)
    os.environ["OMP_NUM_THREADS"] = str(thread_count)
    os.environ["MKL_NUM_THREADS"] = str(thread_count)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(thread_count)
    torch.use_deterministic_algorithms(True, warn_only=True)


def make_loader(features, labels, batch_size, shuffle=False, sampler=None, seed=None):
    """Create a deterministic CPU tensor loader with no worker processes.

    Natural-distribution training uses ``shuffle=True`` and therefore needs an
    explicit generator seed.  Validation/prediction loaders do not shuffle and
    may omit it.  A sampler owns its own generator, so DataLoader's generator is
    deliberately unused in that branch.
    """

    dataset = TensorDataset(torch.from_numpy(features.astype(np.float32)), torch.from_numpy(labels.astype(np.int64)))
    generator = None
    if sampler is None and bool(shuffle):
        if seed is None:
            raise ValueError("shuffled training loaders require an explicit seed")
        generator = torch.Generator()
        generator.manual_seed(int(seed))
    return DataLoader(dataset, batch_size=int(batch_size), shuffle=bool(shuffle) if sampler is None else False,
                      sampler=sampler, num_workers=0, pin_memory=False, generator=generator)


def make_class_balanced_sampler(labels, target_ratio, seed, class_ids=(0, 1, 2)):
    """Sample training classes near one explicitly configured target ratio.

    Each example receives ``target_probability / observed_class_count``.  The
    resulting replacement sampler preserves trace-level split membership while
    preventing the abundant Safe windows from overwhelming Warning/Critical
    gradients.  Its generator seed is stored in the run manifest.
    """

    class_ids = tuple(int(class_id) for class_id in class_ids)
    if not class_ids or class_ids != tuple(range(len(class_ids))):
        raise ValueError("class_ids must be contiguous and start at zero")
    counts = {class_id: int(np.sum(labels == class_id)) for class_id in class_ids}
    if any(counts[class_id] == 0 for class_id in counts):
        raise ValueError("all three classes are required for balanced supervised training")
    weights = np.asarray([float(target_ratio[str(label)]) / counts[int(label)] for label in labels], dtype=np.float64)
    generator = torch.Generator()
    generator.manual_seed(int(seed))
    return WeightedRandomSampler(torch.from_numpy(weights), num_samples=len(labels), replacement=True, generator=generator), counts


class FocalLoss(nn.Module):
    """Class-weighted focal cross entropy for severe Pilot label imbalance."""

    def __init__(self, class_weights, gamma=2.0):
        super().__init__()
        self.register_buffer("class_weights", torch.as_tensor(class_weights, dtype=torch.float32))
        self.gamma = float(gamma)

    def forward(self, logits, targets):
        """Return mean focal loss while preserving gradient through all logits."""

        log_probabilities = nn.functional.log_softmax(logits, dim=1)
        probabilities = log_probabilities.exp()
        selected_log_probabilities = log_probabilities.gather(1, targets.unsqueeze(1)).squeeze(1)
        selected_probabilities = probabilities.gather(1, targets.unsqueeze(1)).squeeze(1)
        weights = self.class_weights.gather(0, targets)
        return (-weights * (1.0 - selected_probabilities).pow(self.gamma) * selected_log_probabilities).mean()


class OrdinalRiskCriticalLoss(nn.Module):
    """Train nested Risk/Critical heads with a soft ordering constraint."""

    def __init__(self, consistency_weight=0.1, positive_weights=(1.0, 1.0)):
        super().__init__()
        self.consistency_weight = float(consistency_weight)
        weights = torch.as_tensor(positive_weights, dtype=torch.float32)
        if weights.shape != (2,) or torch.any(weights < 1.0) or torch.any(weights > 4.0):
            raise ValueError("ordinal positive weights must contain two values in [1,4]")
        self.register_buffer("positive_weights", weights)

    def forward(self, logits, targets):
        """Return BCE(Risk)+BCE(Critical)+penalty(Pcritical>Prisk).

        Risk truth is one for Warning or Critical labels; Critical truth is one
        only for class 2.  The squared ReLU term has zero cost for ordered head
        probabilities and a smooth positive cost only when the Critical head
        exceeds the broader Risk head.
        """

        risk_targets = (targets >= 1).to(dtype=logits.dtype)
        critical_targets = (targets == 2).to(dtype=logits.dtype)
        # ``pos_weight`` multiplies positive examples only.  This is the mild
        # head-specific compensation approved for the imbalanced state task;
        # negative examples retain unit weight and natural sampling remains
        # untouched.
        risk_loss = nn.functional.binary_cross_entropy_with_logits(
            logits[:, 0], risk_targets, pos_weight=self.positive_weights[0])
        critical_loss = nn.functional.binary_cross_entropy_with_logits(
            logits[:, 1], critical_targets, pos_weight=self.positive_weights[1])
        probabilities = torch.sigmoid(logits)
        consistency = torch.relu(probabilities[:, 1] - probabilities[:, 0]).pow(2).mean()
        return risk_loss + critical_loss + self.consistency_weight * consistency


class OrdinalTimeLoss(nn.Module):
    """Combine ordinal classification with weighted time-bucket supervision."""

    def __init__(self, consistency_weight=0.1, auxiliary_weight=0.5,
                 bucket_weights=(1.0, 1.0, 1.5, 2.0)):
        super().__init__()
        self.ordinal = OrdinalRiskCriticalLoss(consistency_weight)
        self.auxiliary_weight = float(auxiliary_weight)
        self.register_buffer("bucket_weights", torch.as_tensor(bucket_weights, dtype=torch.float32))

    def forward(self, logits, encoded_targets):
        """Decode ``class*4+bucket`` and apply the approved loss formula.

        Bucket zero (none) and the nearest positive bucket have unit weight;
        3-4 and 5-8 sample positives receive 1.5 and 2.0 respectively.  The
        weights apply inside the auxiliary term only, preserving the exact
        unweighted ordinal Risk/Critical objective from the preceding stage.
        """

        class_targets = torch.div(encoded_targets, 4, rounding_mode="floor")
        bucket_targets = torch.remainder(encoded_targets, 4)
        ordinal_loss = self.ordinal(logits[:, :2], class_targets)
        time_losses = nn.functional.cross_entropy(logits[:, 2:6], bucket_targets, reduction="none")
        weighted_time_loss = (time_losses * self.bucket_weights.gather(0, bucket_targets)).mean()
        return ordinal_loss + self.auxiliary_weight * weighted_time_loss


def class_weights(labels, strategy="inverse", class_ids=(0, 1, 2)):
    """Return explicit class weights for one configured class schema.

    ``inverse`` preserves the historical v1 behavior.  ``sqrt_inverse`` is the
    v2 mild-compensation arm: sqrt(N/(3*n_c)), clipped to [0.5,2.0], then
    normalized to mean one.  ``none`` returns unit weights and is used by
    unweighted focal loss as well as objective provenance.
    """

    class_ids = tuple(int(class_id) for class_id in class_ids)
    if not class_ids or class_ids != tuple(range(len(class_ids))):
        raise ValueError("class_ids must be contiguous and start at zero")
    counts = np.asarray([np.sum(labels == class_id) for class_id in class_ids],
                        dtype=np.float64)
    if np.any(counts == 0):
        raise ValueError("cannot construct class weights with an absent class")
    if strategy == "none":
        return np.ones(3, dtype=np.float64)
    if strategy == "inverse":
        values = 1.0 / counts
    elif strategy == "sqrt_inverse":
        # Dividing by the active class count makes the formula correct for both
        # the historical three-state task and the binary Safe/Critical task.
        values = np.sqrt(float(np.sum(counts)) / (len(class_ids) * counts))
        values = np.clip(values, 0.5, 2.0)
    else:
        raise ValueError("unknown class weight strategy: {}".format(strategy))
    return values / values.mean()


def configure_training_objective(labels, training_config, seed,
                                 class_ids=(0, 1, 2)):
    """Build sampler, shuffle policy, loss, and auditable strategy metadata.

    New v2 configs must name all three strategy axes.  Old v1 configs omit
    them and are mapped exactly to weighted sampling + inverse-weighted focal
    loss for reproducibility.  Weighted sampling plus non-unit loss weights is
    rejected for v2 because that combination was the diagnosed source of
    excessive Warning predictions; compatibility does not make it valid for a
    new experiment.
    """

    explicit = any(key in training_config for key in
                   ("sampling_strategy", "loss_type", "class_weight_strategy"))
    if explicit and not all(key in training_config for key in
                            ("sampling_strategy", "loss_type", "class_weight_strategy")):
        raise ValueError("v2 training configs must explicitly define sampling, loss, and class weights")
    sampling = training_config.get("sampling_strategy", "weighted_sampler")
    loss_type = training_config.get("loss_type", "focal")
    weight_strategy = training_config.get("class_weight_strategy", "inverse")
    if sampling not in {"natural", "weighted_sampler"}:
        raise ValueError("unknown sampling strategy: {}".format(sampling))
    if loss_type not in {"cross_entropy", "focal", "ordinal_bce", "ordinal_time"}:
        raise ValueError("unknown loss type: {}".format(loss_type))
    if explicit and sampling == "weighted_sampler" and weight_strategy != "none":
        raise ValueError("weighted sampling cannot be combined with non-unit class weights")
    ordinal_weight_strategy = training_config.get("ordinal_positive_weight_strategy", "none")
    if ordinal_weight_strategy not in {"none", "sqrt_negative_positive"}:
        raise ValueError("unknown ordinal positive-weight strategy")
    if loss_type not in {"ordinal_bce", "ordinal_time"} and ordinal_weight_strategy != "none":
        raise ValueError("ordinal positive weights require an ordinal objective")
    if sampling != "natural" and ordinal_weight_strategy != "none":
        raise ValueError("ordinal positive weights cannot be combined with a sampler")
    if loss_type in {"ordinal_bce", "ordinal_time"} and (sampling != "natural" or weight_strategy != "none"):
        raise ValueError("ordinal objectives require natural sampling and no class weights")

    class_ids = tuple(int(class_id) for class_id in class_ids)
    if not class_ids or class_ids != tuple(range(len(class_ids))):
        raise ValueError("class_ids must be contiguous and start at zero")
    if loss_type in {"ordinal_bce", "ordinal_time"} and class_ids != (0, 1, 2):
        raise ValueError("ordinal objectives require the three-state class schema")
    counts = {class_id: int(np.sum(labels == class_id)) for class_id in class_ids}
    if any(value == 0 for value in counts.values()):
        raise ValueError("all configured classes are required for supervised training")
    sampler = None
    shuffle = sampling == "natural"
    if sampling == "weighted_sampler":
        sampler, _ = make_class_balanced_sampler(
            labels, training_config["train_class_ratio"], seed, class_ids)
    weights = class_weights(labels, weight_strategy, class_ids)
    # Compute each binary head's compensation from the actual train split.
    # Risk positives are labels 1/2; Critical positives are label 2 only.  The
    # square root tempers the imbalance and [1,4] clipping bounds gradients.
    ordinal_positive_weights = np.ones(2, dtype=np.float64)
    if ordinal_weight_strategy == "sqrt_negative_positive":
        risk_positive = float(np.sum(labels >= 1))
        critical_positive = float(np.sum(labels == 2))
        ordinal_positive_weights = np.asarray([
            np.sqrt((len(labels) - risk_positive) / risk_positive),
            np.sqrt((len(labels) - critical_positive) / critical_positive),
        ])
        ordinal_positive_weights = np.clip(ordinal_positive_weights, 1.0, 4.0)
    # Loss construction is one mutually exclusive chain.  Keeping the direct
    # and ordinal branches together prevents a later ordinal default from
    # accidentally overwriting a previously constructed CE/Focal criterion.
    if loss_type == "cross_entropy":
        criterion_weights = None if weight_strategy == "none" else torch.as_tensor(weights, dtype=torch.float32)
        criterion = nn.CrossEntropyLoss(weight=criterion_weights)
    elif loss_type == "focal":
        criterion = FocalLoss(weights, training_config["focal_gamma"])
    elif loss_type == "ordinal_bce":
        criterion = OrdinalRiskCriticalLoss(
            training_config.get("ordinal_consistency_weight", 0.1),
            ordinal_positive_weights)
    elif loss_type == "ordinal_time":
        criterion = OrdinalTimeLoss(
            training_config.get("ordinal_consistency_weight", 0.1),
            training_config.get("time_auxiliary_weight", 0.5),
            training_config.get("time_bucket_weights", (1.0, 1.0, 1.5, 2.0)))
    metadata = {"sampling_strategy": sampling, "loss_type": loss_type,
                "class_weight_strategy": weight_strategy,
                "resolved_class_weights": [float(value) for value in weights],
                "ordinal_positive_weight_strategy": ordinal_weight_strategy,
                "resolved_ordinal_positive_weights": [float(value) for value in ordinal_positive_weights],
                "observed_class_counts": {str(key): value for key, value in counts.items()},
                "seed": int(seed), "legacy_implicit_strategy": not explicit}
    return sampler, shuffle, criterion, metadata


def build_classifier(name, model_config):
    """Construct one requested neural classifier from the versioned config."""

    common = {"input_channels": model_config["input_channels"], "class_count": model_config["class_count"],
              "kernel_size": model_config["kernel_size"], "dropout": model_config["dropout"]}
    if name == "tcn":
        return TCN1D(hidden_channels=model_config["hidden_channels"], dilations=model_config["dilations"], **common)
    if name == "ordinal_tcn":
        # OrdinalTCN1D always exposes two nested heads; ``class_count`` belongs
        # to the mapped public probability space and is intentionally omitted.
        return OrdinalTCN1D(input_channels=model_config["input_channels"],
                            hidden_channels=model_config["hidden_channels"],
                            kernel_size=model_config["kernel_size"],
                            dilations=model_config["dilations"], dropout=model_config["dropout"])
    if name == "ordinal_time_tcn":
        return OrdinalTimeTCN1D(input_channels=model_config["input_channels"],
                                hidden_channels=model_config["hidden_channels"],
                                kernel_size=model_config["kernel_size"],
                                dilations=model_config["dilations"], dropout=model_config["dropout"])
    if name == "cnn":
        return CNN1D(
            channels=model_config["cnn_channels"],
            pooling_contract=model_config.get(
                "pooling_contract", "adaptive_average_over_past_window"),
            dilations=model_config.get("cnn_dilations"),
            kernel_sizes=model_config.get("kernel_sizes"), **common)
    raise ValueError("unknown classifier: {}".format(name))


def parameter_count(model):
    """Return trainable parameter count for comparable model-complexity reporting."""

    return int(sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad))


def estimate_macs(model, length, input_channels=5):
    """Estimate Conv1d/Linear multiply-accumulates with forward hooks.

    The estimate is intentionally architecture-local rather than a hardware
    benchmark: each Conv1d output element costs ``in_channels/groups * kernel``
    MACs and each Linear output costs ``in_features`` MACs.  This is sufficient
    to compare compact Pilot models reproducibly across CPU hosts.
    """

    total = [0]
    handles = []

    def hook(module, inputs, outputs):
        if isinstance(module, nn.Conv1d):
            total[0] += int(outputs.shape[0] * outputs.shape[1] * outputs.shape[2] * (module.in_channels // module.groups) * module.kernel_size[0])
        elif isinstance(module, nn.Linear):
            total[0] += int(outputs.shape[0] * module.in_features * module.out_features)

    for module in model.modules():
        if isinstance(module, (nn.Conv1d, nn.Linear)):
            handles.append(module.register_forward_hook(hook))
    model.eval()
    with torch.no_grad():
        model(torch.zeros(1, int(input_channels), int(length)))
    for handle in handles:
        handle.remove()
    return int(total[0])


def benchmark_latency_ms(model, length, input_channels=5, repetitions=1000, warmup=100):
    """Measure median CPU single-window inference latency after warmup."""

    model.eval()
    inputs = torch.zeros(1, int(input_channels), int(length))
    with torch.no_grad():
        for _ in range(int(warmup)):
            model(inputs)
        samples = []
        for _ in range(int(repetitions)):
            start = time.perf_counter_ns()
            model(inputs)
            samples.append((time.perf_counter_ns() - start) / 1.0e6)
    return float(np.median(samples))
