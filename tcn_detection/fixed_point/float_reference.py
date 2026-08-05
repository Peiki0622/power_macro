#!/usr/bin/env python3
"""Freeze float intermediates and deterministic golden windows for the CNN."""

from __future__ import print_function

from dataclasses import dataclass

import numpy as np
import torch

from power_macro.tcn_detection.dataset.model_data import (
    apply_normalizer, filter_split, load_window_table)
from power_macro.tcn_detection.evaluate.binary_metrics import binary_window_metrics


ALLOWED_DEVELOPMENT_SPLITS = frozenset(("train", "validation"))
GOLDEN_CATEGORIES = (
    "safe_steady",
    "safe_slow_change",
    "near_decision_boundary",
    "critical_short_peak",
    "critical_sustained",
    "endpoint_dominant",
    "maximum_dominant",
    "average_dominant",
)


@dataclass(frozen=True)
class FloatInference:
    """Float outputs needed for metrics, branch analysis, and golden export."""

    logits: np.ndarray
    summaries: np.ndarray
    probabilities: np.ndarray
    predictions: np.ndarray


def load_development_windows(path, split):
    """Load one allowed split while filtering before ``features_json`` parsing.

    The underlying release stores train, validation, and IID rows in one CSV.
    ``load_window_table`` performs its split test before JSON decoding, so this
    wrapper is the narrow guarantee that an IID feature tensor is never formed
    in the fixed-point process.  The explicit allow-list also prevents a future
    caller from passing an arbitrary split name through the public API.
    """

    split = str(split)
    if split not in ALLOWED_DEVELOPMENT_SPLITS:
        raise ValueError("fixed-point development forbids split {}".format(split))
    table = load_window_table(path, splits={split})
    if any(row.get("split") != split for row in table.metadata):
        raise ValueError("window loader crossed requested split boundary")
    return filter_split(table, split)


def decode_sensor_codes(features, tolerance=2.0e-6):
    """Recover integer codes from the immutable first-stage normalization.

    The CSV stores ``(sensor_code-15)/17`` rather than raw integers.  Exporting
    raw code windows is useful for RTL, but silently rounding an arbitrary
    floating-point feature could hide data corruption.  Every reconstructed
    value is therefore checked against the exact approved affine mapping and
    against the legal 0..32 sensor range.
    """

    values = np.asarray(features, dtype=np.float64)
    if values.ndim != 3 or values.shape[1:] != (1, 32):
        raise ValueError("sensor windows must have shape [N,1,32]")
    reconstructed = values * 17.0 + 15.0
    codes = np.rint(reconstructed).astype(np.int16)
    encoded = (codes.astype(np.float64) - 15.0) / 17.0
    if (np.any(codes < 0) or np.any(codes > 32)
            or not np.allclose(values, encoded, rtol=0.0, atol=float(tolerance))):
        raise ValueError("window contains a value outside the sensor-code lattice")
    return codes


def checkpoint_inputs(table, normalizer):
    """Apply the checkpoint's second train-only normalization exactly once."""

    return apply_normalizer(table, normalizer).features.astype(np.float32,
                                                                copy=False)


def numpy_conv1d_same(inputs, weights, bias):
    """Evaluate stride-one odd-kernel cross-correlation with same padding.

    PyTorch ``Conv1d`` implements cross-correlation rather than reversing the
    kernel.  ``sliding_window_view`` exposes [N,C,L,K] neighborhoods, and the
    einsum below preserves the model's [out,in,kernel] weight order.  Explicit
    float32 operands keep this diagnostic close to the checkpoint execution;
    small accumulation-order differences are handled by the caller's float
    tolerance and never enter the later integer bit-true path.
    """

    inputs = np.asarray(inputs, dtype=np.float32)
    weights = np.asarray(weights, dtype=np.float32)
    bias = np.asarray(bias, dtype=np.float32)
    if inputs.ndim != 3 or weights.ndim != 3:
        raise ValueError("float convolution requires [N,C,L] and [O,C,K]")
    kernel = int(weights.shape[2])
    if kernel < 1 or kernel % 2 == 0:
        raise ValueError("float same convolution requires a positive odd kernel")
    if inputs.shape[1] != weights.shape[1] or bias.shape != (weights.shape[0],):
        raise ValueError("float convolution channel or bias mismatch")
    padding = kernel // 2
    padded = np.pad(inputs, ((0, 0), (0, 0), (padding, padding)),
                    mode="constant")
    windows = np.lib.stride_tricks.sliding_window_view(
        padded, window_shape=kernel, axis=2)
    return (np.einsum("nclk,ock->nol", windows, weights,
                      optimize=True).astype(np.float32)
            + bias.reshape(1, -1, 1))


def numpy_float_forward(inputs, model):
    """Return a NumPy layer trace independent of ``CNN1D.forward``."""

    state = {name: tensor.detach().cpu().numpy()
             for name, tensor in model.state_dict().items()}
    trace = {"input": np.asarray(inputs, dtype=np.float32)}
    current = trace["input"]
    for layer_index, module_index in enumerate((0, 3, 6), 1):
        convolution = numpy_conv1d_same(
            current, state["features.{}.weight".format(module_index)],
            state["features.{}.bias".format(module_index)])
        current = np.maximum(convolution, np.float32(0.0)).astype(np.float32)
        trace["conv{}".format(layer_index)] = convolution
        trace["relu{}".format(layer_index)] = current
    average = current.mean(axis=2, dtype=np.float32)
    maximum = current.max(axis=2)
    endpoint = current[:, :, -1]
    summary = np.concatenate((average, maximum, endpoint), axis=1)
    logits = (summary @ state["classifier.weight"].T
              + state["classifier.bias"].reshape(1, 2))
    trace.update({"average": average, "maximum": maximum,
                  "endpoint": endpoint, "summary": summary,
                  "logits": logits.astype(np.float32)})
    return trace


def torch_float_inference(inputs, model, batch_size=512):
    """Run deterministic eval inference and retain the configured summary."""

    inputs = np.asarray(inputs, dtype=np.float32)
    logits_batches = []
    summary_batches = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(inputs), int(batch_size)):
            batch = torch.from_numpy(inputs[start:start + int(batch_size)])
            # Calling convolution/ReLU modules explicitly avoids retaining all
            # Avoid retaining all [N,C,32] intermediates for the full validation
            # set; C is taken from the model rather than a legacy width.
            # Dropout modules are skipped deliberately in eval mode; selected
            # golden windows receive the full trace from numpy_float_forward.
            features = batch
            for module_index in (0, 3, 6):
                features = torch.relu(model.features[module_index](features))
            summary = torch.cat((features.mean(dim=2), features.amax(dim=2),
                                 features[:, :, -1]), dim=1)
            logits = model.classifier(summary)
            summary_batches.append(summary.cpu().numpy())
            logits_batches.append(logits.cpu().numpy())
    logits = np.concatenate(logits_batches).astype(np.float32, copy=False)
    summaries = np.concatenate(summary_batches).astype(np.float32, copy=False)
    # Stable softmax avoids overflow even if a future checkpoint produces much
    # larger raw logits.  Probability metrics use float64 after this boundary.
    shifted = logits.astype(np.float64) - logits.max(axis=1, keepdims=True)
    exponentials = np.exp(shifted)
    probabilities = exponentials / exponentials.sum(axis=1, keepdims=True)
    predictions = np.argmax(logits, axis=1).astype(np.int64)
    return FloatInference(logits, summaries, probabilities, predictions)


def float_metrics(labels, inference):
    """Return the project's existing validation-only binary metric schema."""

    return binary_window_metrics(labels, inference.predictions,
                                 inference.probabilities)


def select_golden_windows(table, codes, inference, model):
    """Select eight deterministic, trace-distinct validation windows.

    The first five categories use label, sensor-code shape, and decision margin
    only.  The final three use the absolute contribution of each configured
    classifier segment to the Critical-minus-Safe logit.  This makes the words
    average/max/endpoint "dominant" numerically auditable without consulting
    VDD, slack, waveform family, or any future sample.
    """

    if len(table.labels) != len(codes) or len(codes) != len(inference.logits):
        raise ValueError("golden selection arrays are not row-aligned")
    if any(row.get("split") != "validation" for row in table.metadata):
        raise ValueError("golden windows must be validation-only")
    code_rows = codes[:, 0, :].astype(np.float64)
    differences = np.diff(code_rows, axis=1)
    ranges = np.ptp(code_rows, axis=1)
    standard_deviations = np.std(code_rows, axis=1)
    transition_counts = np.sum(differences != 0.0, axis=1)
    max_steps = np.max(np.abs(differences), axis=1)
    medians = np.median(code_rows, axis=1)
    residuals = np.abs(code_rows - medians[:, None])
    peak_scores = residuals.max(axis=1) / (residuals.mean(axis=1) + 1.0e-9)
    margins = inference.logits[:, 1] - inference.logits[:, 0]

    classifier = model.classifier.weight.detach().cpu().numpy()
    if classifier.shape[1] % 3 != 0:
        raise ValueError("multistat classifier width must be divisible by three")
    branch_width = classifier.shape[1] // 3
    if inference.summaries.shape[1] != 3 * branch_width:
        raise ValueError("summary width does not match classifier contract")
    difference_weights = classifier[1] - classifier[0]
    branch_contributions = np.stack((
        np.sum(inference.summaries[:, 0:branch_width]
               * difference_weights[0:branch_width], axis=1),
        np.sum(inference.summaries[:, branch_width:2 * branch_width]
               * difference_weights[branch_width:2 * branch_width], axis=1),
        np.sum(inference.summaries[:, 2 * branch_width:3 * branch_width]
               * difference_weights[2 * branch_width:3 * branch_width], axis=1),
    ), axis=1)
    absolute_contributions = np.abs(branch_contributions)
    branch_fraction = absolute_contributions / np.maximum(
        absolute_contributions.sum(axis=1, keepdims=True), 1.0e-12)

    all_indices = np.arange(len(table.labels), dtype=np.int64)
    safe = table.labels == 0
    critical = table.labels == 1
    selectors = {
        "safe_steady": (safe, ranges * 100.0 + transition_counts),
        "safe_slow_change": (
            safe & (ranges > 0.0),
            max_steps * 10.0 + transition_counts - ranges * 0.01),
        "near_decision_boundary": (
            np.ones(len(table.labels), dtype=bool), np.abs(margins)),
        "critical_short_peak": (critical, -peak_scores),
        "critical_sustained": (
            critical, standard_deviations - inference.probabilities[:, 1]),
        "endpoint_dominant": (
            np.ones(len(table.labels), dtype=bool), -branch_fraction[:, 2]),
        "maximum_dominant": (
            np.ones(len(table.labels), dtype=bool), -branch_fraction[:, 1]),
        "average_dominant": (
            np.ones(len(table.labels), dtype=bool), -branch_fraction[:, 0]),
    }

    selected = []
    used_traces = set()
    for category in GOLDEN_CATEGORIES:
        mask, score = selectors[category]
        candidates = all_indices[mask]
        # Window ID is a stable final tie-breaker independent of CSV row order.
        candidates = sorted(candidates, key=lambda index: (
            float(score[index]), table.metadata[index]["window_id"]))
        chosen = next((index for index in candidates
                       if table.metadata[index]["trace_id"] not in used_traces),
                      None)
        if chosen is None:
            raise ValueError("cannot select trace-distinct {} window".format(category))
        row = table.metadata[chosen]
        used_traces.add(row["trace_id"])
        selected.append({
            "category": category,
            "row_index": int(chosen),
            "window_id": row["window_id"],
            "trace_id": row["trace_id"],
            "split": row["split"],
            "end_index": int(row["end_index"]),
            "target_label": int(table.labels[chosen]),
            "float_logit_safe": float(inference.logits[chosen, 0]),
            "float_logit_critical": float(inference.logits[chosen, 1]),
            "float_logit_difference": float(margins[chosen]),
            "code_range": int(ranges[chosen]),
            "code_standard_deviation": float(standard_deviations[chosen]),
            "branch_contribution_fraction": {
                "average": float(branch_fraction[chosen, 0]),
                "maximum": float(branch_fraction[chosen, 1]),
                "endpoint": float(branch_fraction[chosen, 2]),
            },
        })
    return selected
