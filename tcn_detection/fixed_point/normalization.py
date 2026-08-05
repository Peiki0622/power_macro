"""Fold both sensor-code normalization stages into the first convolution."""

from __future__ import print_function

from dataclasses import dataclass

import numpy as np

from power_macro.tcn_detection.fixed_point.float_reference import numpy_conv1d_same


@dataclass(frozen=True)
class FoldedFirstLayer:
    """Float affine form consumed by later fixed-point coefficient quantization.

    ``weights`` multiply centered integer codes ``sensor_code-15``.  ``biases``
    has one column per L32 output position because same-padding is applied after
    the checkpoint's train-only standardization.  At an edge, padded model
    inputs are exact zero and therefore must not contribute the standardizer's
    beta term; a single interior bias would incorrectly include those missing
    taps.
    """

    weights: np.ndarray
    biases: np.ndarray
    alpha: float
    beta: float


def derive_folded_first_layer(model, normalizer, baseline=15,
                              denominator=17, length=32):
    """Derive ``Conv(alpha*(code-baseline)+beta)`` without runtime division."""

    mean = float(normalizer["mean"][0])
    standard_deviation = float(normalizer["std"][0])
    if (normalizer.get("source_split") != "train"
            or standard_deviation <= 0.0
            or int(normalizer.get("window_length", -1)) != int(length)):
        raise ValueError("cannot fold an invalid checkpoint normalizer")
    alpha = 1.0 / (float(denominator) * standard_deviation)
    beta = -mean / standard_deviation
    convolution = model.features[0]
    original_weights = convolution.weight.detach().cpu().numpy().astype(
        np.float64)
    original_bias = convolution.bias.detach().cpu().numpy().astype(np.float64)
    kernel = int(original_weights.shape[2])
    if kernel < 1 or kernel % 2 == 0:
        raise ValueError("folding requires a positive odd Conv1d kernel")
    padding = kernel // 2
    folded_weights = original_weights * alpha

    biases = np.empty((original_weights.shape[0], int(length)), dtype=np.float64)
    for output_position in range(int(length)):
        # For output p and same padding, kernel tap k reads input p+k-padding. Only
        # in-range taps see beta.  Padding taps are zero in model-input space,
        # so adding beta for them would change the original Conv1d semantics.
        valid_taps = [kernel_index for kernel_index in range(kernel)
                      if 0 <= output_position + kernel_index - padding < int(length)]
        beta_contribution = beta * original_weights[:, 0, valid_taps].sum(axis=1)
        biases[:, output_position] = original_bias + beta_contribution
    return FoldedFirstLayer(folded_weights, biases, alpha, beta)


def folded_first_layer_float(sensor_codes, folded, baseline=15):
    """Evaluate the folded affine using centered raw integers and no division."""

    codes = np.asarray(sensor_codes)
    if codes.ndim != 3 or codes.shape[1:] != (1, 32):
        raise ValueError("folded first layer requires [N,1,32] sensor codes")
    if np.any(codes < 0) or np.any(codes > 32):
        raise ValueError("folded first layer received an illegal sensor code")
    centered = codes.astype(np.float64) - float(baseline)
    kernel = int(folded.weights.shape[2])
    if kernel < 1 or kernel % 2 == 0:
        raise ValueError("folded convolution requires a positive odd kernel")
    padding = kernel // 2
    padded = np.pad(centered, ((0, 0), (0, 0), (padding, padding)),
                    mode="constant")
    windows = np.lib.stride_tricks.sliding_window_view(
        padded, window_shape=kernel, axis=2)
    convolution = np.einsum(
        "nclk,ock->nol", windows, folded.weights, optimize=True)
    return convolution + folded.biases.reshape(
        1, folded.biases.shape[0], folded.biases.shape[1])


def original_first_layer_float(sensor_codes, model, normalizer,
                               baseline=15, denominator=17):
    """Evaluate the unfused two-stage normalization and original Conv1d."""

    codes = np.asarray(sensor_codes, dtype=np.float32)
    normalized_code = ((codes - np.float32(baseline))
                       / np.float32(denominator))
    model_input = ((normalized_code - np.float32(normalizer["mean"][0]))
                   / np.float32(normalizer["std"][0]))
    state = model.state_dict()
    return numpy_conv1d_same(
        model_input,
        state["features.0.weight"].detach().cpu().numpy(),
        state["features.0.bias"].detach().cpu().numpy())


def exhaustive_fold_error(model, normalizer):
    """Measure all 33 constant-code windows, including every edge position."""

    folded = derive_folded_first_layer(model, normalizer)
    codes = np.repeat(np.arange(33, dtype=np.int16)[:, None, None],
                      32, axis=2)
    original = original_first_layer_float(codes, model, normalizer)
    fused = folded_first_layer_float(codes, folded)
    differences = np.abs(original.astype(np.float64) - fused)
    location = np.unravel_index(int(np.argmax(differences)), differences.shape)
    return {
        "max_abs_error": float(differences[location]),
        "worst_sensor_code": int(codes[location[0], 0, 0]),
        "worst_output_channel": int(location[1]),
        "worst_output_position": int(location[2]),
        "alpha": folded.alpha,
        "beta": folded.beta,
        "edge_bias_variants": 4,
        "interior_bias_columns_identical": bool(np.allclose(
            folded.biases[:, 2:30], folded.biases[:, 2:3],
            rtol=0.0, atol=0.0)),
    }
