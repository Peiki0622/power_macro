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


def make_loader(features, labels, batch_size, shuffle=False, sampler=None):
    """Create a CPU tensor loader with no hidden worker-process randomness."""

    dataset = TensorDataset(torch.from_numpy(features.astype(np.float32)), torch.from_numpy(labels.astype(np.int64)))
    return DataLoader(dataset, batch_size=int(batch_size), shuffle=bool(shuffle) if sampler is None else False,
                      sampler=sampler, num_workers=0, pin_memory=False)


def make_class_balanced_sampler(labels, target_ratio, seed):
    """Sample training classes near the configured Safe/Warning/Critical ratio.

    Each example receives ``target_probability / observed_class_count``.  The
    resulting replacement sampler preserves trace-level split membership while
    preventing the abundant Safe windows from overwhelming Warning/Critical
    gradients.  Its generator seed is stored in the run manifest.
    """

    counts = {class_id: int(np.sum(labels == class_id)) for class_id in (0, 1, 2)}
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


def class_weights(labels):
    """Return inverse-frequency weights normalized to a mean of one."""

    counts = np.asarray([np.sum(labels == class_id) for class_id in (0, 1, 2)], dtype=np.float64)
    if np.any(counts == 0):
        raise ValueError("cannot construct class weights with an absent class")
    values = 1.0 / counts
    return values / values.mean()


def build_classifier(name, model_config):
    """Construct one requested neural classifier from the versioned config."""

    common = {"input_channels": model_config["input_channels"], "class_count": model_config["class_count"],
              "kernel_size": model_config["kernel_size"], "dropout": model_config["dropout"]}
    if name == "tcn":
        return TCN1D(hidden_channels=model_config["hidden_channels"], dilations=model_config["dilations"], **common)
    if name == "cnn":
        return CNN1D(channels=model_config["cnn_channels"], **common)
    raise ValueError("unknown classifier: {}".format(name))


def parameter_count(model):
    """Return trainable parameter count for comparable model-complexity reporting."""

    return int(sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad))


def estimate_macs(model, length):
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
        model(torch.zeros(1, 5, int(length)))
    for handle in handles:
        handle.remove()
    return int(total[0])


def benchmark_latency_ms(model, length, repetitions=1000, warmup=100):
    """Measure median CPU single-window inference latency after warmup."""

    model.eval()
    inputs = torch.zeros(1, 5, int(length))
    with torch.no_grad():
        for _ in range(int(warmup)):
            model(inputs)
        samples = []
        for _ in range(int(repetitions)):
            start = time.perf_counter_ns()
            model(inputs)
            samples.append((time.perf_counter_ns() - start) / 1.0e6)
    return float(np.median(samples))
