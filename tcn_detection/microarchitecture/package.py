#!/usr/bin/env python3
"""Authenticate the frozen ``[18,8,18]`` W8/A8 package for Stage 1.

The legacy ``rtl/cnn_monitor/model/parameter_package.py`` intentionally binds
the older ``[18,18,18]`` release.  Reusing it here would silently accept wrong
shapes and wrong accumulator widths, so this loader has an independent,
explicit contract for the Stage 0 compression handoff.
"""

from __future__ import print_function

import hashlib
import json
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PACKAGE_ROOT = (REPO_ROOT / "power_macro" / "tcn_detection" / "runs"
                        / "formal_v1_20260727_r1" / "models"
                        / "state_code_binary_cnn_compression_v1_20260805_r1"
                        / "final_w18_8_18_20260805_r1"
                        / "fixed_point_quantized_20260805_r1")
FIXED_POINT_CONFIG = (REPO_ROOT / "power_macro" / "tcn_detection" / "config"
                      / "fixed_point_cnn_multistat_w18_8_18_k5_v1.json")


EXPECTED_MODEL = {
    "input_channels": 1,
    "window_length": 32,
    "channels": [18, 8, 18],
    "kernel_sizes": [5, 5, 5],
    "pooling_contract": "multistat_average_max_endpoint",
    "classifier_features": 54,
    "sensor_code_min": 0,
    "sensor_code_max": 32,
}

EXPECTED_TENSORS = {
    "conv1.weights": ((18, 1, 5), 8, "out_channel,in_channel,kernel"),
    "conv1.bias": ((18, 32), 14, "out_channel,output_position"),
    "conv2.weights": ((8, 18, 5), 8, "out_channel,in_channel,kernel"),
    "conv2.bias": ((8,), 20, "out_channel"),
    "conv3.weights": ((18, 8, 5), 8, "out_channel,in_channel,kernel"),
    "conv3.bias": ((18,), 19, "out_channel"),
    "classifier.weights": ((2, 54), 8, "output_class,summary_feature"),
    "classifier.bias": ((2,), 19, "output_class"),
}


def sha256_file(path):
    """Return the byte-level SHA256 without normalizing text or line endings."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_mem(path, shape, bits):
    """Decode the package's C-order signed two's-complement memory words."""

    values = []
    for line in Path(path).read_text(encoding="ascii").splitlines():
        text = line.strip()
        if not text or text.startswith("//"):
            continue
        value = int(text, 16)
        if value >= (1 << (int(bits) - 1)):
            value -= 1 << int(bits)
        values.append(value)
    expected = int(np.prod(shape))
    if len(values) != expected:
        raise ValueError("{} has {} words, expected {}".format(
            path, len(values), expected))
    return np.asarray(values, dtype=np.int64).reshape(tuple(shape), order="C")


def _verify_tensor(root, record, expected):
    """Verify metadata, digest, entry count, and decoded values for one tensor."""

    expected_shape, expected_bits, expected_order = expected
    if tuple(record["shape"]) != expected_shape:
        raise ValueError("{} shape differs from Stage 1 contract".format(
            record["tensor_name"]))
    if int(record["signed_bits"]) != expected_bits:
        raise ValueError("{} width differs from Stage 1 contract".format(
            record["tensor_name"]))
    if record["flatten_order"] != expected_order:
        raise ValueError("{} flatten order differs from Stage 1 contract".format(
            record["tensor_name"]))
    if int(record["entry_count"]) != int(np.prod(expected_shape)):
        raise ValueError("{} entry count differs from shape".format(
            record["tensor_name"]))
    path = root / "weights" / record["path"]
    if sha256_file(path) != record["sha256"]:
        raise ValueError("{} SHA256 mismatch".format(path))
    return _read_mem(path, expected_shape, expected_bits)


def load_package(package_root=None):
    """Load and authenticate the frozen package as a NumPy-backed contract.

    The returned mapping contains only data needed by software scheduling and
    dependency analysis.  It does not expose a mutable model or any RTL path,
    which keeps Stage 1 independent from the legacy implementation.
    """

    root = Path(package_root or DEFAULT_PACKAGE_ROOT).resolve()
    manifest_path = root / "manifest.json"
    quantization_path = root / "quantization_config.json"
    config = json.loads(FIXED_POINT_CONFIG.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    quantization = json.loads(quantization_path.read_text(encoding="utf-8"))

    if manifest.get("status") != "PASS":
        raise ValueError("Stage 0 package status is not PASS")
    if manifest.get("selected_candidate") != "w8_a8":
        raise ValueError("Stage 1 requires the selected W8/A8 package")
    if sha256_file(quantization_path) != manifest["quantization_config_sha256"]:
        raise ValueError("manifest does not authenticate quantization config")
    if config.get("expected_checkpoint_sha256") != manifest.get(
            "checkpoint_sha256"):
        raise ValueError("checkpoint SHA differs from fixed-point contract")
    model = config["model_contract"]
    for key, expected in EXPECTED_MODEL.items():
        observed = model.get(key)
        if observed != expected:
            raise ValueError("model contract {} differs: {} != {}".format(
                key, observed, expected))

    selected = quantization["selected_numeric_package"]
    records = {}
    for layer in selected["layers"]:
        records[layer["weight_file"]["tensor_name"]] = layer["weight_file"]
        records[layer["bias_file"]["tensor_name"]] = layer["bias_file"]
    records[selected["classifier"]["weight_file"]["tensor_name"]] = \
        selected["classifier"]["weight_file"]
    records[selected["classifier"]["bias_file"]["tensor_name"]] = \
        selected["classifier"]["bias_file"]
    if set(records) != set(EXPECTED_TENSORS):
        raise ValueError("package tensor set differs from Stage 1 contract")

    tensors = {name: _verify_tensor(root, records[name], expected)
               for name, expected in EXPECTED_TENSORS.items()}
    layer_metadata = []
    for layer in selected["layers"]:
        layer_metadata.append({
            "name": layer["name"],
            "weights": tensors[layer["weight_file"]["tensor_name"]],
            "bias": tensors[layer["bias_file"]["tensor_name"]],
            "weight_exponents": list(layer["weight_exponents"]),
            "accumulator_exponents": list(layer["accumulator_exponents"]),
            "output_exponent": int(layer["output_exponent"]),
            "accumulator_bounds": list(layer["accumulator_bounds"]),
            "accumulator_width": int(layer["accumulator_width"]),
        })
    classifier = selected["classifier"]
    return {
        "root": str(root),
        "source_binding": {
            "manifest_sha256": sha256_file(manifest_path),
            "quantization_config_sha256": sha256_file(quantization_path),
            "checkpoint_sha256": manifest["checkpoint_sha256"],
            "fixed_point_config_sha256": sha256_file(FIXED_POINT_CONFIG),
        },
        "model": dict(EXPECTED_MODEL),
        # Keep numeric widths alongside the decoded tensors.  The Stage 1
        # dependency replay needs these immutable values to reproduce the
        # existing bit-true truncation points without importing PyTorch.
        "activation_bits": int(selected["activation_bits"]),
        "classifier_output_bits": int(selected["classifier_output_bits"]),
        "layers": layer_metadata,
        "classifier": {
            "weights": tensors["classifier.weights"],
            "bias": tensors["classifier.bias"],
            "weight_exponents": list(classifier["weight_exponents"]),
            "accumulator_exponents": list(classifier["accumulator_exponents"]),
            "output_exponent": int(selected["classifier_output_exponent"]),
            "accumulator_bounds": list(classifier["accumulator_bounds"]),
            "accumulator_width": int(classifier["accumulator_width"]),
        },
    }
