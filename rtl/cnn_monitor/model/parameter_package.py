#!/usr/bin/env python3
"""Load and authenticate the task-one fixed-point parameter package.

The RTL generator and the cycle model share this module so that neither can
silently invent a tensor shape, flattening order, signed width, or scale.  The
loader verifies the outer manifest first and then verifies every coefficient
record in ``quantization_config.json`` before exposing NumPy arrays.
"""

from __future__ import print_function

import hashlib
import json
from pathlib import Path

import numpy as np


EXPECTED_TENSORS = {
    "conv1.weights": ((18, 1, 5), 8, "out_channel,in_channel,kernel"),
    "conv1.bias": ((18, 32), 14, "out_channel,output_position"),
    "conv2.weights": ((18, 18, 5), 8, "out_channel,in_channel,kernel"),
    "conv2.bias": ((18,), 20, "out_channel"),
    "conv3.weights": ((18, 18, 5), 8, "out_channel,in_channel,kernel"),
    "conv3.bias": ((18,), 20, "out_channel"),
    "classifier.weights": ((2, 54), 8, "output_class,summary_feature"),
    "classifier.bias": ((2,), 20, "output_class"),
}


def sha256_file(path):
    """Return the SHA-256 digest of one file without normalizing its bytes."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_mem(path, shape, bits):
    """Decode fixed-width hexadecimal two's-complement words in C order."""

    words = []
    for line in Path(path).read_text(encoding="ascii").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        unsigned = int(stripped, 16)
        if unsigned >= (1 << (int(bits) - 1)):
            unsigned -= 1 << int(bits)
        words.append(unsigned)
    expected = int(np.prod(shape))
    if len(words) != expected:
        raise ValueError("{} has {} entries, expected {}".format(
            path, len(words), expected))
    return np.asarray(words, dtype=np.int64).reshape(tuple(shape), order="C")


def _verify_record(package_root, record, expected):
    """Validate one tensor's metadata, digest, entry count, and signed values."""

    expected_shape, expected_bits, expected_order = expected
    if tuple(record["shape"]) != expected_shape:
        raise ValueError("{} shape differs from RTL contract".format(
            record["tensor_name"]))
    if int(record["signed_bits"]) != expected_bits:
        raise ValueError("{} width differs from RTL contract".format(
            record["tensor_name"]))
    if record["flatten_order"] != expected_order:
        raise ValueError("{} order differs from RTL contract".format(
            record["tensor_name"]))
    if int(record["entry_count"]) != int(np.prod(expected_shape)):
        raise ValueError("{} entry count differs from shape".format(
            record["tensor_name"]))
    path = package_root / "weights" / record["path"]
    if sha256_file(path) != record["sha256"]:
        raise ValueError("{} digest mismatch".format(path))
    return _read_mem(path, expected_shape, expected_bits)


def load_parameter_package(package_root, expected_manifest_sha256=None,
                           expected_quantization_sha256=None):
    """Authenticate and load all constants needed by the RTL and cycle model.

    ``expected_*`` values bind the caller to the exact accepted task-one
    package.  Passing them is mandatory for the generator; optional arguments
    are retained only so negative unit tests can isolate inner-file failures.
    """

    root = Path(package_root).resolve()
    manifest_path = root / "manifest.json"
    quantization_path = root / "quantization_config.json"
    if (expected_manifest_sha256 is not None
            and sha256_file(manifest_path) != expected_manifest_sha256):
        raise ValueError("task-one manifest digest mismatch")
    if (expected_quantization_sha256 is not None
            and sha256_file(quantization_path) != expected_quantization_sha256):
        raise ValueError("task-one quantization digest mismatch")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    quantization = json.loads(quantization_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS" or manifest.get("selected_candidate") != "w8_a8":
        raise ValueError("task-one package is not the accepted W8/A8 result")
    if sha256_file(quantization_path) != manifest["quantization_config_sha256"]:
        raise ValueError("manifest does not authenticate quantization config")

    selected = quantization["selected_numeric_package"]
    records = {}
    for layer in selected["layers"]:
        records[layer["weight_file"]["tensor_name"]] = layer["weight_file"]
        records[layer["bias_file"]["tensor_name"]] = layer["bias_file"]
    classifier = selected["classifier"]
    records[classifier["weight_file"]["tensor_name"]] = classifier["weight_file"]
    records[classifier["bias_file"]["tensor_name"]] = classifier["bias_file"]
    if set(records) != set(EXPECTED_TENSORS):
        raise ValueError("task-one tensor set differs from RTL contract")

    tensors = {
        name: _verify_record(root, records[name], expected)
        for name, expected in EXPECTED_TENSORS.items()
    }
    return {
        "root": root,
        "manifest": manifest,
        "quantization": quantization,
        "selected": selected,
        "tensors": tensors,
    }
