#!/usr/bin/env python3
"""Pure NumPy integer inference for the frozen multistat w18/k5 CNN.

The reference intentionally avoids PyTorch's quantization runtime.  PyTorch is
used only to collect train-split float activation ranges before this module is
called.  All deployed operations below are explicit integer multiply, add,
ties-to-even power-of-two shift, saturation, ReLU, pooling, and comparison.
"""

from __future__ import print_function

import math

import numpy as np
import torch

from power_macro.tcn_detection.evaluate.binary_metrics import binary_window_metrics
from power_macro.tcn_detection.fixed_point.normalization import (
    derive_folded_first_layer)
from power_macro.tcn_detection.fixed_point.quality import (
    choose_candidate, evaluate_quality_gates, validate_fixed_point_config)


def signed_limits(bits):
    """Return the two's-complement interval for one explicit signed width."""

    bits = int(bits)
    if bits < 2 or bits > 63:
        raise ValueError("signed integer width must be in [2,63]")
    return -(1 << (bits - 1)), (1 << (bits - 1)) - 1


def power_of_two_exponent(maximum_absolute_value, positive_limit):
    """Choose the smallest power-of-two scale that cannot clip calibration.

    A real value is represented as ``integer * 2**exponent``.  Rounding the
    ideal scale upward to a power of two trades at most one precision bit for a
    multiplier-free requantization path.  Zero tensors use exponent zero and
    remain exactly zero.
    """

    maximum_absolute_value = float(maximum_absolute_value)
    positive_limit = int(positive_limit)
    if not math.isfinite(maximum_absolute_value) or maximum_absolute_value < 0.0:
        raise ValueError("quantization range must be finite and non-negative")
    if maximum_absolute_value == 0.0:
        return 0
    return int(math.ceil(math.log(maximum_absolute_value / positive_limit, 2.0)))


def quantize_with_exponent(values, exponent, bits):
    """Round to nearest-even and saturate a float tensor to signed integers."""

    lower, upper = signed_limits(bits)
    scaled = np.ldexp(np.asarray(values, dtype=np.float64), -int(exponent))
    # NumPy rint implements IEEE round-to-nearest, ties-to-even.  Casting only
    # happens after clipping, so an out-of-range float can never wrap around.
    return np.clip(np.rint(scaled), lower, upper).astype(np.int64)


def round_right_shift_ties_even(values, shift):
    """Divide signed int64 values by 2**shift using ties-to-even rounding.

    Python and NumPy right shift negative integers toward negative infinity.
    That is not a complete rounding rule.  Floor quotient plus a non-negative
    remainder gives one definition that works for both signs: increment when
    the remainder exceeds half, or equals half while the floor quotient is
    odd.  The result is the nearest integer with even tie selection.
    """

    values = np.asarray(values, dtype=np.int64)
    shift = int(shift)
    if shift < 0 or shift > 62:
        raise ValueError("right shift must be in [0,62]")
    if shift == 0:
        return values.copy()
    denominator = np.int64(1 << shift)
    quotient = np.floor_divide(values, denominator)
    remainder = values - quotient * denominator
    half = denominator // np.int64(2)
    increment = (remainder > half) | ((remainder == half) & ((quotient & 1) != 0))
    return quotient + increment.astype(np.int64)


def requantize_channels(accumulators, source_exponents, target_exponent,
                        bits, relu):
    """Align per-output-channel accumulator scales and apply one truncation."""

    accumulators = np.asarray(accumulators, dtype=np.int64)
    source_exponents = np.asarray(source_exponents, dtype=np.int64)
    if accumulators.ndim not in (2, 3) or accumulators.shape[1] != len(source_exponents):
        raise ValueError("requantization channel shape mismatch")
    output = np.empty_like(accumulators)
    for channel, source_exponent in enumerate(source_exponents):
        index = ((slice(None), channel) if accumulators.ndim == 2
                 else (slice(None), channel, slice(None)))
        shift = int(target_exponent) - int(source_exponent)
        if shift >= 0:
            aligned = round_right_shift_ties_even(accumulators[index], shift)
        else:
            # Every candidate's analytical bound is checked below 63 bits
            # before inference, so this exact left shift cannot overflow int64.
            aligned = np.left_shift(accumulators[index], -shift)
        output[index] = aligned
    lower, upper = signed_limits(bits)
    if relu:
        # Negative aligned values are ordinary ReLU activity, not numeric
        # overflow.  Report only values exceeding the positive format limit as
        # saturation so the audit distinguishes expected nonlinearity from an
        # insufficient activation range.
        saturation_count = int(np.count_nonzero(output > upper))
        lower = 0
    else:
        saturation_count = int(np.count_nonzero(
            (output < lower) | (output > upper)))
    saturated = np.clip(output, lower, upper)
    return saturated.astype(np.int64, copy=False), saturation_count


def integer_conv1d_same(inputs, weights, bias):
    """Compute same-padded k=5 integer cross-correlation in RTL tensor order."""

    inputs = np.asarray(inputs, dtype=np.int64)
    weights = np.asarray(weights, dtype=np.int64)
    bias = np.asarray(bias, dtype=np.int64)
    if (inputs.ndim != 3 or weights.ndim != 3 or weights.shape[2] != 5
            or inputs.shape[1] != weights.shape[1]):
        raise ValueError("integer convolution tensor shape mismatch")
    padded = np.pad(inputs, ((0, 0), (0, 0), (2, 2)), mode="constant")
    windows = np.lib.stride_tricks.sliding_window_view(
        padded, window_shape=5, axis=2)
    # Flattening [C,K] makes matrix multiplication follow the exported
    # [out][in][kernel] weight order.  NumPy int64 matmul performs integer MACs;
    # no floating point or hidden requantization occurs in this path.
    flat_windows = windows.transpose(0, 2, 1, 3).reshape(
        inputs.shape[0] * inputs.shape[2], -1)
    flat_weights = weights.reshape(weights.shape[0], -1)
    accumulators = (flat_windows @ flat_weights.T).reshape(
        inputs.shape[0], inputs.shape[2], weights.shape[0]).transpose(0, 2, 1)
    if bias.shape == (weights.shape[0],):
        accumulators = accumulators + bias.reshape(1, -1, 1)
    elif bias.shape == (weights.shape[0], inputs.shape[2]):
        accumulators = accumulators + bias.reshape(1, weights.shape[0],
                                                   inputs.shape[2])
    else:
        raise ValueError("integer convolution bias shape mismatch")
    return accumulators.astype(np.int64, copy=False)


def _required_signed_bits(bounds):
    """Return one signed width covering every non-negative magnitude bound."""

    maximum = int(np.max(np.asarray(bounds, dtype=np.int64)))
    return max(2, int(math.ceil(math.log(maximum + 1, 2.0))) + 1)


def _quantize_per_output(weights, bits):
    """Quantize [O,I,K] or [O,I] weights with one scale per output."""

    values = np.asarray(weights, dtype=np.float64)
    axes = tuple(range(1, values.ndim))
    _, positive_limit = signed_limits(bits)
    maxima = np.max(np.abs(values), axis=axes)
    exponents = np.asarray([
        power_of_two_exponent(value, positive_limit) for value in maxima
    ], dtype=np.int64)
    quantized = np.empty(values.shape, dtype=np.int64)
    for output, exponent in enumerate(exponents):
        quantized[output] = quantize_with_exponent(
            values[output], int(exponent), bits)
    return quantized, exponents


def calibrate_float_ranges(model, train_inputs, batch_size=512):
    """Collect full-range train-only maxima for three ReLUs and float logits."""

    train_inputs = np.asarray(train_inputs, dtype=np.float32)
    maxima = {"relu1": 0.0, "relu2": 0.0, "relu3": 0.0, "logits": 0.0}
    model.eval()
    with torch.no_grad():
        for start in range(0, len(train_inputs), int(batch_size)):
            current = torch.from_numpy(train_inputs[start:start + int(batch_size)])
            for layer_index, module_index in enumerate((0, 3, 6), 1):
                current = torch.relu(model.features[module_index](current))
                name = "relu{}".format(layer_index)
                maxima[name] = max(maxima[name], float(current.abs().max().item()))
            summary = torch.cat((current.mean(dim=2), current.amax(dim=2),
                                 current[:, :, -1]), dim=1)
            logits = model.classifier(summary)
            maxima["logits"] = max(maxima["logits"],
                                    float(logits.abs().max().item()))
    if any(value <= 0.0 or not math.isfinite(value) for value in maxima.values()):
        raise ValueError("train calibration produced an invalid activation range")
    return maxima


def _quantize_bias(values, source_exponents):
    """Align float biases exactly to each channel's accumulator scale."""

    values = np.asarray(values, dtype=np.float64)
    source_exponents = np.asarray(source_exponents, dtype=np.int64)
    output = np.empty(values.shape, dtype=np.int64)
    for channel, exponent in enumerate(source_exponents):
        output[channel] = np.rint(np.ldexp(values[channel], -int(exponent))).astype(
            np.int64)
    return output


def build_candidate(model, checkpoint, candidate_spec, calibration, config):
    """Quantize all coefficients and derive no-overflow accumulator contracts."""

    validate_fixed_point_config(config)
    weight_bits = int(candidate_spec["weight_bits"])
    activation_bits = int(candidate_spec["activation_bits"])
    _, activation_limit = signed_limits(activation_bits)
    state = {name: tensor.detach().cpu().numpy().astype(np.float64)
             for name, tensor in model.state_dict().items()}
    activation_exponents = {
        name: power_of_two_exponent(calibration[name], activation_limit)
        for name in ("relu1", "relu2", "relu3")
    }
    _, logit_limit = signed_limits(config["quantization_policy"][
        "classifier_output_bits"])
    logit_exponent = power_of_two_exponent(calibration["logits"], logit_limit)

    folded = derive_folded_first_layer(model, checkpoint["normalizer"])
    first_weights, first_weight_exponents = _quantize_per_output(
        folded.weights, weight_bits)
    # Centered raw sensor code is an integer with scale 2**0.  The first bias
    # therefore uses the same per-output scale as the folded weight.
    first_bias = _quantize_bias(folded.biases, first_weight_exponents)
    layers = [{
        "name": "conv1", "weights": first_weights, "bias": first_bias,
        "weight_exponents": first_weight_exponents,
        "input_exponent": 0,
        "accumulator_exponents": first_weight_exponents.copy(),
        "output_exponent": activation_exponents["relu1"],
    }]

    previous_exponent = activation_exponents["relu1"]
    for layer_name, module_index, output_name in (
            ("conv2", 3, "relu2"), ("conv3", 6, "relu3")):
        weights, weight_exponents = _quantize_per_output(
            state["features.{}.weight".format(module_index)], weight_bits)
        accumulator_exponents = weight_exponents + int(previous_exponent)
        bias = _quantize_bias(
            state["features.{}.bias".format(module_index)],
            accumulator_exponents)
        layers.append({
            "name": layer_name, "weights": weights, "bias": bias,
            "weight_exponents": weight_exponents,
            "input_exponent": int(previous_exponent),
            "accumulator_exponents": accumulator_exponents,
            "output_exponent": activation_exponents[output_name],
        })
        previous_exponent = activation_exponents[output_name]

    classifier_weights, classifier_weight_exponents = _quantize_per_output(
        state["classifier.weight"], weight_bits)
    classifier_accumulator_exponents = (
        classifier_weight_exponents + activation_exponents["relu3"])
    classifier_bias = _quantize_bias(
        state["classifier.bias"], classifier_accumulator_exponents)
    classifier = {
        "name": "classifier", "weights": classifier_weights,
        "bias": classifier_bias,
        "weight_exponents": classifier_weight_exponents,
        "input_exponent": activation_exponents["relu3"],
        "accumulator_exponents": classifier_accumulator_exponents,
        "output_exponent": logit_exponent,
        "output_bits": int(config["quantization_policy"][
            "classifier_output_bits"]),
    }

    # Derive a conservative magnitude bound from legal input ranges and the
    # actual quantized coefficient magnitudes.  Bias is included before the
    # requantization point, matching the runtime operation order exactly.
    first_bound = (17 * np.sum(np.abs(first_weights), axis=(1, 2))
                   + np.max(np.abs(first_bias), axis=1))
    layers[0]["accumulator_bounds"] = first_bound.astype(np.int64)
    for layer in layers[1:]:
        bound = (activation_limit * np.sum(np.abs(layer["weights"]), axis=(1, 2))
                 + np.abs(layer["bias"]))
        layer["accumulator_bounds"] = bound.astype(np.int64)
    classifier_bound = (
        activation_limit * np.sum(np.abs(classifier_weights), axis=1)
        + np.abs(classifier_bias))
    classifier["accumulator_bounds"] = classifier_bound.astype(np.int64)
    accumulator_widths = {
        layer["name"]: _required_signed_bits(layer["accumulator_bounds"])
        for layer in layers
    }
    accumulator_widths["classifier"] = _required_signed_bits(
        classifier["accumulator_bounds"])
    if max(accumulator_widths.values()) > 63:
        raise OverflowError("candidate requires an accumulator wider than int64")
    return {
        "candidate_id": candidate_spec["candidate_id"],
        "weight_bits": weight_bits,
        "activation_bits": activation_bits,
        "activation_exponents": activation_exponents,
        "layers": layers,
        "classifier": classifier,
        "accumulator_widths": accumulator_widths,
        "calibration_ranges": dict(calibration),
        "normalization_fold": {
            "alpha": folded.alpha, "beta": folded.beta,
            "bias_shape": list(first_bias.shape),
            "padding_contract": "zero_model_input_with_position_dependent_bias",
        },
    }


def _check_accumulator(name, accumulators, bounds, statistics):
    """Assert runtime values remain within the precomputed per-channel bound."""

    accumulators = np.asarray(accumulators, dtype=np.int64)
    axes = (0, 2) if accumulators.ndim == 3 else (0,)
    observed = np.max(np.abs(accumulators), axis=axes)
    if np.any(observed > np.asarray(bounds, dtype=np.int64)):
        raise OverflowError("{} accumulator exceeded analytical bound".format(name))
    prior = statistics.setdefault(name, {
        "minimum": int(accumulators.min()),
        "maximum": int(accumulators.max()),
        "maximum_absolute": int(observed.max()),
    })
    prior["minimum"] = min(prior["minimum"], int(accumulators.min()))
    prior["maximum"] = max(prior["maximum"], int(accumulators.max()))
    prior["maximum_absolute"] = max(prior["maximum_absolute"],
                                    int(observed.max()))


def _run_batch(sensor_codes, package, capture_intermediates):
    """Execute one batch and optionally retain every RTL-visible tensor."""

    codes = np.asarray(sensor_codes, dtype=np.int64)
    if codes.ndim != 3 or codes.shape[1:] != (1, 32):
        raise ValueError("bit-true input must have shape [N,1,32]")
    if np.any(codes < 0) or np.any(codes > 32):
        raise ValueError("bit-true input contains an illegal sensor code")
    current = codes - 15
    statistics = {}
    saturation_counts = {}
    trace = {"sensor_codes": codes.copy(), "centered_codes": current.copy()}
    for layer_index, layer in enumerate(package["layers"], 1):
        accumulator = integer_conv1d_same(
            current, layer["weights"], layer["bias"])
        _check_accumulator(layer["name"], accumulator,
                           layer["accumulator_bounds"], statistics)
        current, saturated = requantize_channels(
            accumulator, layer["accumulator_exponents"],
            layer["output_exponent"], package["activation_bits"], relu=True)
        saturation_counts["relu{}".format(layer_index)] = saturated
        if capture_intermediates:
            trace["conv{}_accumulator".format(layer_index)] = accumulator
            trace["relu{}".format(layer_index)] = current.copy()

    # All three summary branches retain relu3's scale.  Average pooling divides
    # the integer sum by exactly 32 with the same ties-to-even rule used by
    # convolution requantization; maximum and endpoint need no arithmetic.
    average_sum = current.sum(axis=2, dtype=np.int64)
    average = round_right_shift_ties_even(average_sum, 5)
    maximum = current.max(axis=2)
    endpoint = current[:, :, -1]
    summary = np.concatenate((average, maximum, endpoint), axis=1)
    classifier = package["classifier"]
    classifier_accumulator = (summary @ classifier["weights"].T
                              + classifier["bias"].reshape(1, 2))
    _check_accumulator("classifier", classifier_accumulator,
                       classifier["accumulator_bounds"], statistics)
    logits, logit_saturation = requantize_channels(
        classifier_accumulator, classifier["accumulator_exponents"],
        classifier["output_exponent"], classifier["output_bits"], relu=False)
    saturation_counts["logits"] = logit_saturation
    decisions = np.argmax(logits, axis=1).astype(np.int64)
    if capture_intermediates:
        trace.update({
            "average_sum": average_sum, "average": average,
            "maximum": maximum, "endpoint": endpoint, "summary": summary,
            "classifier_accumulator": classifier_accumulator,
            "logits": logits, "logit_difference": logits[:, 1] - logits[:, 0],
            "decision": decisions,
        })
    return logits, decisions, statistics, saturation_counts, trace


def run_bittrue(sensor_codes, package, batch_size=256,
                capture_intermediates=False):
    """Run one or many windows and return logits, metrics inputs, and audits."""

    sensor_codes = np.asarray(sensor_codes)
    logits_batches = []
    decision_batches = []
    aggregate_statistics = {}
    aggregate_saturation = {}
    trace_batches = []
    for start in range(0, len(sensor_codes), int(batch_size)):
        logits, decisions, statistics, saturation, trace = _run_batch(
            sensor_codes[start:start + int(batch_size)], package,
            capture_intermediates)
        logits_batches.append(logits)
        decision_batches.append(decisions)
        if capture_intermediates:
            trace_batches.append(trace)
        for name, current in statistics.items():
            previous = aggregate_statistics.setdefault(name, dict(current))
            previous["minimum"] = min(previous["minimum"], current["minimum"])
            previous["maximum"] = max(previous["maximum"], current["maximum"])
            previous["maximum_absolute"] = max(
                previous["maximum_absolute"], current["maximum_absolute"])
        for name, count in saturation.items():
            aggregate_saturation[name] = aggregate_saturation.get(name, 0) + int(count)
    integer_logits = np.concatenate(logits_batches, axis=0)
    decisions = np.concatenate(decision_batches, axis=0)
    exponent = int(package["classifier"]["output_exponent"])
    dequantized_logits = np.ldexp(integer_logits.astype(np.float64), exponent)
    shifted = dequantized_logits - dequantized_logits.max(axis=1, keepdims=True)
    exponentials = np.exp(shifted)
    probabilities = exponentials / exponentials.sum(axis=1, keepdims=True)
    result = {
        "integer_logits": integer_logits,
        "dequantized_logits": dequantized_logits,
        "probabilities": probabilities,
        "predictions": decisions,
        "accumulator_statistics": aggregate_statistics,
        "saturation_counts": aggregate_saturation,
    }
    if capture_intermediates:
        # Golden export uses a single small batch.  Reject multi-batch capture
        # instead of introducing a complex tensor concatenation convention.
        if len(trace_batches) != 1:
            raise ValueError("intermediate capture requires one batch")
        result["trace"] = trace_batches[0]
    return result


def evaluate_candidate(sensor_codes, labels, package, float_metric_report,
                       config, batch_size=256):
    """Run validation, calculate project metrics, and apply frozen gates."""

    result = run_bittrue(sensor_codes, package, batch_size=batch_size)
    metrics = binary_window_metrics(labels, result["predictions"],
                                    result["probabilities"])
    selected_metrics = {
        name: metrics[name] for name in (
            "accuracy", "balanced_accuracy", "macro_f1", "critical_pr_auc",
            "critical_recall", "safe_window_false_alarm_rate")
    }
    gates = evaluate_quality_gates(float_metric_report, selected_metrics, config)
    return result, selected_metrics, gates


def search_candidates(model, checkpoint, train_inputs, validation_codes,
                      validation_labels, float_metric_report, config,
                      batch_size=256):
    """Evaluate all frozen width combinations and retain complete evidence.

    Returning coefficient packages separately from the JSON-compatible report
    prevents large integer arrays from being accidentally embedded in a search
    summary.  Stage 6 exports only the chosen package, while the report keeps
    metrics, gates, ranges, saturation, and no-overflow evidence for all four
    candidates, including failed INT8 experiments.
    """

    validate_fixed_point_config(config)
    calibration = calibrate_float_ranges(model, train_inputs)
    packages = {}
    reports = []
    for specification in config["candidates"]:
        package = build_candidate(
            model, checkpoint, specification, calibration, config)
        result, metrics, gates = evaluate_candidate(
            validation_codes, validation_labels, package,
            float_metric_report, config, batch_size=batch_size)
        packages[specification["candidate_id"]] = package
        reports.append({
            "candidate_id": specification["candidate_id"],
            "weight_bits": int(specification["weight_bits"]),
            "activation_bits": int(specification["activation_bits"]),
            "classifier_output_bits": int(package["classifier"]["output_bits"]),
            "activation_exponents": dict(package["activation_exponents"]),
            "classifier_output_exponent": int(
                package["classifier"]["output_exponent"]),
            "accumulator_widths": dict(package["accumulator_widths"]),
            "accumulator_statistics": result["accumulator_statistics"],
            "saturation_counts": result["saturation_counts"],
            "validation_metrics": metrics,
            "quality_gates": gates,
        })
    selected = choose_candidate(reports, config)
    return packages, {
        "schema_version": 1,
        "scope": "train_calibration_validation_selection_only",
        "iid_features_loaded": False,
        "iid_metrics_computed": False,
        "calibration_ranges": calibration,
        "float_validation_metrics": dict(float_metric_report),
        "candidate_reports": reports,
        "selected_candidate": selected,
        "status": "PASS" if selected is not None else "NO_CANDIDATE_PASSED",
    }
