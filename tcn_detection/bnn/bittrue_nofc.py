"""Pure NumPy XNOR/popcount/threshold inference for exported no-FC BNNs.

This module intentionally has no torch dependency.  The deployment path accepts
raw integer code windows, creates thermometer bits, and evaluates each layer
with logical equality plus integer reductions.  A normal floating convolution
cannot enter this function without violating the exported package contract.
"""

from __future__ import print_function

import hashlib
import json
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.bnn.input_encoding import encode_windows


def _sha256(path):
    """Hash one packed binary weight file before accepting its contents."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_package_json(root):
    """Read and validate the small deployment manifest."""

    root = Path(root)
    payload = json.loads((root / "package.json").read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported BNN package schema")
    if payload.get("architecture_id") != "bnn_therm32_w1a1_nofc_l32":
        raise ValueError("package is not the Stage-1B full-binary architecture")
    if payload.get("activation_bits") != 1 or payload.get("weight_bits") != 1:
        raise ValueError("deployment package is not W1A1")
    if payload.get("classifier_present") is not False:
        raise ValueError("BNN package must not contain a classifier")
    if int(payload.get("vote_k", 0)) not in range(1, 33):
        raise ValueError("package vote K must be within 1..32")
    if payload.get("padding_bit") != 0:
        raise ValueError("bit-true padding convention differs from training")
    return payload


def load_package(root):
    """Load packed bits and integer thresholds after manifest/hash checks."""

    root = Path(root)
    payload = _read_package_json(root)
    layers = []
    for description in payload.get("layers", []):
        shape = tuple(int(value) for value in description["shape"])
        if len(shape) != 3 or any(value < 1 for value in shape):
            raise ValueError("invalid packed weight shape")
        path = root / description["weights_file"]
        if _sha256(path) != description["weights_sha256"]:
            raise ValueError("packed weight digest mismatch: {}".format(path))
        packed = np.fromfile(str(path), dtype=np.uint8)
        bits = np.unpackbits(packed, bitorder="big")[:int(np.prod(shape))]
        weights = bits.reshape(shape).astype(np.uint8, copy=False)
        thresholds = np.asarray(description["thresholds"], dtype=np.int64)
        inversion = np.asarray(description["inversion_flags"], dtype=np.uint8)
        if thresholds.shape != (shape[0],) or inversion.shape != (shape[0],):
            raise ValueError("threshold/channel shape mismatch")
        if np.any(thresholds < 0) or np.any(thresholds > shape[1] * shape[2] + 1):
            raise ValueError("threshold lies outside a popcount range")
        if np.any((inversion != 0) & (inversion != 1)):
            raise ValueError("inversion flags must be one bit")
        layers.append({"name": description["name"], "weights": weights,
                       "thresholds": thresholds,
                       "inversion_flags": inversion,
                       "kernel_size": int(shape[2])})
    if len(layers) != 3 or [layer["name"] for layer in layers] != [
            "conv1", "conv2", "head"]:
        raise ValueError("package must contain conv1, conv2, and head only")
    result = dict(payload)
    result["root"] = root
    result["layers"] = layers
    return result


def _binary_conv(bits, layer, capture=False):
    """Run one logical convolution as XNOR, popcount, and integer compare."""

    if bits.ndim != 3 or bits.dtype != np.uint8:
        raise ValueError("bit-true layer input must be uint8 [N,C,L]")
    weights = layer["weights"]
    batch, channels, length = bits.shape
    output_channels, input_channels, kernel = weights.shape
    if channels != input_channels:
        raise ValueError("bit-true channel count differs from package weights")
    padded = np.pad(bits, ((0, 0), (0, 0), (kernel // 2, kernel // 2)),
                    mode="constant", constant_values=0)
    windows = np.lib.stride_tricks.sliding_window_view(
        padded, window_shape=kernel, axis=2)
    # Shape is [batch, output, input, time, kernel].  Equality is XNOR because
    # both operands are logical bits; summing the last two axes is popcount.
    equal = windows[:, None, :, :, :] == weights[None, :, :, None, :]
    counts = np.sum(equal, axis=(2, 4), dtype=np.int32)
    threshold = layer["thresholds"].reshape(1, output_channels, 1)
    output = (counts >= threshold).astype(np.uint8)
    inverted = layer["inversion_flags"].reshape(1, output_channels, 1)
    output = np.where(inverted != 0, 1 - output, output).astype(np.uint8)
    return output, counts if capture else None


def _run_batch(codes, package, capture_intermediates):
    """Evaluate one bounded batch so the XNOR intermediate stays memory-safe."""

    bits = encode_windows(codes).astype(np.uint8, copy=False)
    traces = {}
    for layer in package["layers"]:
        bits, counts = _binary_conv(bits, layer, capture=capture_intermediates)
        if capture_intermediates:
            traces[layer["name"] + "_bits"] = bits.copy()
            traces[layer["name"] + "_popcount"] = counts.copy()
    vote_count = bits[:, 0, :].sum(axis=1, dtype=np.int32)
    predictions = (vote_count >= int(package["vote_k"])).astype(np.uint8)
    result = {"temporal_bits": bits, "vote_count": vote_count,
              "predictions": predictions}
    if capture_intermediates:
        result["trace"] = traces
    return result


def run_bittrue(codes, package, batch_size=512, capture_intermediates=False):
    """Run the exported package on ``[N,32]`` or one ``[32]`` code windows."""

    values = np.asarray(codes)
    if values.ndim == 1:
        values = values.reshape(1, -1)
    if values.ndim != 2 or values.shape[1] != 32:
        raise ValueError("bit-true code windows must have shape [N,32]")
    if int(batch_size) < 1:
        raise ValueError("bit-true batch size must be positive")
    # Encoding validates the full code lattice before any batch is processed.
    # This prevents a partially evaluated result when a later row is corrupt.
    encode_windows(values)
    batches = []
    traces = []
    for start in range(0, len(values), int(batch_size)):
        result = _run_batch(values[start:start + int(batch_size)], package,
                            capture_intermediates)
        batches.append(result)
        if capture_intermediates:
            traces.append(result["trace"])
    output = {
        "temporal_bits": np.concatenate([item["temporal_bits"] for item in batches]),
        "vote_count": np.concatenate([item["vote_count"] for item in batches]),
        "predictions": np.concatenate([item["predictions"] for item in batches]),
    }
    if capture_intermediates:
        output["trace"] = {
            name: np.concatenate([trace[name] for trace in traces])
            for name in traces[0]
        }
    return output
