#!/usr/bin/env python3
"""Bit-true replay and sliding-window dependency evidence for Stage 1.

The frozen model uses symmetric same padding and a position-specific Conv1
bias after normalizer folding.  Those facts make generic "update only the
newest point" reasoning unsafe.  This module first derives a conservative
structural mask, then checks the integer replay against the exported golden
traces and representative legal sliding windows.
"""

from __future__ import print_function

import json
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.microarchitecture.package import (
    DEFAULT_PACKAGE_ROOT)


def round_right_shift_ties_even(values, shift):
    """Divide signed values by ``2**shift`` with the frozen nearest-even rule."""

    values = np.asarray(values, dtype=np.int64)
    shift = int(shift)
    if shift < 0:
        raise ValueError("right shift must be non-negative")
    if shift == 0:
        return values.copy()
    denominator = np.int64(1 << shift)
    quotient = np.floor_divide(values, denominator)
    remainder = values - quotient * denominator
    half = denominator // np.int64(2)
    increment = ((remainder > half)
                 | ((remainder == half) & ((quotient & 1) != 0)))
    return quotient + increment.astype(np.int64)


def _requantize(accumulators, source_exponents, output_exponent, bits, relu):
    """Apply one per-output requantization and the package's saturation rule."""

    values = np.asarray(accumulators, dtype=np.int64)
    output = np.empty_like(values)
    for channel, source_exponent in enumerate(source_exponents):
        shift = int(output_exponent) - int(source_exponent)
        current = values[channel]
        output[channel] = (round_right_shift_ties_even(current, shift)
                           if shift >= 0 else np.left_shift(current, -shift))
    if relu:
        return np.clip(output, 0, (1 << (int(bits) - 1)) - 1).astype(np.int64)
    lower = -(1 << (int(bits) - 1))
    upper = (1 << (int(bits) - 1)) - 1
    return np.clip(output, lower, upper).astype(np.int64)


def _integer_conv_same(source, layer):
    """Execute one exported odd-kernel convolution in package flattening order."""

    source = np.asarray(source, dtype=np.int64)
    weights = np.asarray(layer["weights"], dtype=np.int64)
    bias = np.asarray(layer["bias"], dtype=np.int64)
    output_channels, input_channels, kernel_size = weights.shape
    length = source.shape[1]
    if source.shape != (input_channels, length) or kernel_size % 2 != 1:
        raise ValueError("invalid source or odd-kernel layer shape")
    padded = np.pad(source, ((0, 0), (kernel_size // 2, kernel_size // 2)),
                    mode="constant")
    output = np.zeros((output_channels, length), dtype=np.int64)
    for output_channel in range(output_channels):
        for position in range(length):
            # Conv1 carries [out,position] bias because raw-code normalization
            # was folded through the zero-padding boundary.  Later layers use
            # one bias per output channel; both are part of the W8/A8 contract.
            total = int(bias[output_channel, position] if bias.ndim == 2
                        else bias[output_channel])
            for input_channel in range(input_channels):
                for tap in range(kernel_size):
                    total += (int(padded[input_channel, position + tap])
                              * int(weights[output_channel, input_channel, tap]))
            output[output_channel, position] = total
    return output


def run_integer_replay(package, sensor_codes):
    """Replay the complete frozen inference using only exported integers.

    The function is intentionally small and not a new numerical contract.  It
    mirrors the existing package operation order solely to prove that Stage 1
    dependency conclusions are based on real W8/A8 traces even on hosts where
    the training-only PyTorch dependency is unavailable.
    """

    codes = np.asarray(sensor_codes, dtype=np.int64)
    if codes.shape != (32,) or np.any(codes < 0) or np.any(codes > 32):
        raise ValueError("one legal L32 sensor-code window is required")
    current = (codes - 15).reshape(1, 32)
    trace = {"centered_codes": current.copy()}
    for index, layer in enumerate(package["layers"], 1):
        accumulator = _integer_conv_same(current, layer)
        current = _requantize(accumulator, layer["accumulator_exponents"],
                              layer["output_exponent"],
                              package["activation_bits"], relu=True)
        trace["conv{}_accumulator".format(index)] = accumulator
        trace["relu{}".format(index)] = current.copy()
    average_sum = current.sum(axis=1, dtype=np.int64)
    average = round_right_shift_ties_even(average_sum, 5)
    maximum = current.max(axis=1)
    endpoint = current[:, -1]
    summary = np.concatenate((average, maximum, endpoint))
    classifier = package["classifier"]
    accumulator = (classifier["weights"] @ summary
                   + classifier["bias"])
    logits = _requantize(accumulator.reshape(2, 1),
                         classifier["accumulator_exponents"],
                         classifier["output_exponent"],
                         package["classifier_output_bits"], relu=False).reshape(2)
    trace.update({
        "average_sum": average_sum,
        "average": average,
        "maximum": maximum,
        "endpoint": endpoint,
        "summary": summary,
        "classifier_accumulator": accumulator,
        "logits": logits,
        "decision": int(logits[1] > logits[0]),
    })
    return trace


def _propagate_same_padding(changed_positions, kernel_size, length):
    """Return output positions whose receptive field intersects a changed input."""

    radius = int(kernel_size) // 2
    changed = set(int(value) for value in changed_positions)
    return [position for position in range(int(length))
            if any((position + offset) in changed
                   for offset in range(-radius, radius + 1))]


def analyze_dependencies(package):
    """Derive a conservative exact-update mask for one sliding L32 step.

    Every logical input position changes identity after a window shift.  The
    Conv1 folded bias additionally prevents reusing an old Conv1 value at the
    neighbouring logical position.  Consequently all later feature positions
    and both global pooling branches must be recomputed for bit-exactness.
    """

    length = int(package["model"]["window_length"])
    all_positions = list(range(length))
    conv1 = package["layers"][0]
    position_bias = np.asarray(conv1["bias"]).ndim == 2
    conv1_affected = all_positions if position_bias else _propagate_same_padding(
        all_positions, int(conv1["weights"].shape[2]), length)
    conv2_affected = _propagate_same_padding(
        conv1_affected, int(package["layers"][1]["weights"].shape[2]), length)
    conv3_affected = _propagate_same_padding(
        conv2_affected, int(package["layers"][2]["weights"].shape[2]), length)
    return {
        "window_shift": "new[p]=old[p+1] for p<31; new[31]=incoming_code",
        "conv1_position_dependent_bias": bool(position_bias),
        "affected_positions": {
            "conv1": conv1_affected,
            "conv2": conv2_affected,
            "conv3": conv3_affected,
        },
        "affected_position_counts": {
            "conv1": len(conv1_affected),
            "conv2": len(conv2_affected),
            "conv3": len(conv3_affected),
            "pool": len(conv3_affected),
        },
        "pooling": {
            "average": "recompute all affected Conv3 positions before sum",
            "maximum": "recompute all affected Conv3 positions; cached max is unsafe after deletion",
            "endpoint": "recompute logical position 31",
        },
        "mode_b_exact": True,
        "mode_b_reduces_work": len(conv3_affected) < length,
        "conclusion": ("same-padding plus folded position-dependent Conv1 bias "
                       "requires all 32 positions; incremental mode is exact "
                       "only when it performs the full-window work"),
    }


def validate_replay_and_shift(package, package_root=None):
    """Compare the NumPy replay to golden traces and validate its change mask."""

    root = Path(package_root or package["root"] or DEFAULT_PACKAGE_ROOT)
    golden = np.load(str(root / "golden" / "expected_layer_outputs.npz"))
    windows = [json.loads(line) for line in (root / "golden" / "windows.jsonl").read_text(
        encoding="utf-8").splitlines()]
    golden_keys = {
        "centered_codes": "integer_centered_codes",
        "relu1": "integer_relu1",
        "relu2": "integer_relu2",
        "relu3": "integer_relu3",
        "average_sum": "integer_average_sum",
        "average": "integer_average",
        "maximum": "integer_maximum",
        "endpoint": "integer_endpoint",
        "summary": "integer_summary",
        "classifier_accumulator": "integer_classifier_accumulator",
        "logits": "integer_logits",
    }
    for index, window in enumerate(windows):
        trace = run_integer_replay(package, window["sensor_codes"])
        for key, golden_key in golden_keys.items():
            if not np.array_equal(trace[key], golden[golden_key][index]):
                raise AssertionError("{} differs for {}".format(
                    key, window["window_id"]))

    dependency = analyze_dependencies(package)
    legal_windows = [
        np.zeros(32, dtype=np.int64),
        np.full(32, 15, dtype=np.int64),
        np.full(32, 32, dtype=np.int64),
        np.arange(32, dtype=np.int64) % 33,
    ]
    observed = {"conv1": set(), "conv2": set(), "conv3": set()}
    for prior in legal_windows:
        incoming = int((int(prior[-1]) + 1) % 33)
        current = np.concatenate((prior[1:], np.asarray([incoming], dtype=np.int64)))
        old_trace = run_integer_replay(package, prior)
        new_trace = run_integer_replay(package, current)
        for layer_index, name in enumerate(("conv1", "conv2", "conv3"), 1):
            changed = np.nonzero(np.any(old_trace["relu{}".format(layer_index)]
                                        != new_trace["relu{}".format(layer_index)],
                                        axis=0))[0]
            observed[name].update(int(value) for value in changed)
            declared = set(dependency["affected_positions"][name])
            if not set(int(value) for value in changed).issubset(declared):
                raise AssertionError("dependency mask misses {} positions".format(name))
    dependency["golden_windows_verified"] = len(windows)
    dependency["observed_changed_positions"] = {
        name: sorted(values) for name, values in observed.items()}
    return dependency

