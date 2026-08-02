#!/usr/bin/env python3
"""Validate the authoritative CNN checkpoint and describe its numeric graph.

This module is the fail-closed boundary for every later fixed-point operation.
Callers receive a model only after the report-selected digest, checkpoint
metadata, explicit architecture contract, state-dict keys, and tensor shapes
have all matched.  Keeping these checks in one place prevents a later export
script from accidentally accepting a similarly named historical CNN.
"""

from __future__ import print_function

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.models.cnn1d import CNN1D


EXPECTED_PARAMETER_SHAPES = {
    "features.0.weight": (18, 1, 5),
    "features.0.bias": (18,),
    "features.3.weight": (18, 18, 5),
    "features.3.bias": (18,),
    "features.6.weight": (18, 18, 5),
    "features.6.bias": (18,),
    "classifier.weight": (2, 54),
    "classifier.bias": (2,),
}


def sha256_file(path):
    """Hash one artifact without loading a large checkpoint into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Read a versioned JSON contract and require an object at its root."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON contract root must be an object: {}".format(path))
    return payload


def source_commit(repository_root):
    """Return the exact Git commit that owns the executable source tree.

    Reproducibility metadata must not use the caller's current directory: this
    workspace contains several neighboring repositories, while ``power_macro``
    is the repository that owns the CNN implementation.  Failure to resolve a
    commit is fatal because ``unknown`` would not satisfy the phase-one audit
    contract.
    """

    try:
        return subprocess.check_output(
            ["git", "-C", str(Path(repository_root)), "rev-parse", "HEAD"],
            text=True).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("cannot resolve source commit: {}".format(error))


def _validate_model_contract(model_config, fixed_config):
    """Reject any architecture that differs from the frozen w18/k5 graph."""

    contract = fixed_config.get("model_contract", {})
    exact_fields = {
        "architecture_id": fixed_config.get("architecture_id"),
        "input_channels": contract.get("input_channels"),
        "class_count": contract.get("class_count"),
        "class_names": contract.get("class_names"),
        "cnn_channels": contract.get("channels"),
        "kernel_size": contract.get("kernel_size"),
        "pooling_contract": contract.get("pooling_contract"),
    }
    for field, expected in exact_fields.items():
        if model_config.get(field) != expected:
            raise ValueError("model contract mismatch for {}".format(field))
    if (contract.get("dilations") != [1, 1, 1]
            or int(contract.get("same_padding", -1)) != 2
            or int(contract.get("classifier_features", -1)) != 54
            or int(contract.get("window_length", -1)) != 32):
        raise ValueError("fixed-point config omits an explicit graph dimension")


def _validate_checkpoint_metadata(checkpoint, model_config, fixed_config):
    """Validate non-tensor metadata before constructing the executable model."""

    if (checkpoint.get("model") != "cnn"
            or checkpoint.get("task") != "safe_critical_binary"
            or checkpoint.get("model_config") != model_config
            or int(checkpoint.get("window_length", -1)) != 32
            or int(checkpoint.get("seed", -1)) != 20260727):
        raise ValueError("checkpoint metadata differs from authoritative model")

    # The CSV feature is already (sensor_code-15)/17, but training then fitted
    # and applied this second, train-only standardizer.  Hardware export must
    # retain both affine transforms.  Treating the documented sensor-code
    # normalization as the complete preprocessing path would silently change
    # every first-layer activation and materially degrade validation quality.
    normalizer = checkpoint.get("normalizer", {})
    means = normalizer.get("mean", [])
    standard_deviations = normalizer.get("std", [])
    if (normalizer.get("source_split") != "train"
            or int(normalizer.get("window_length", -1)) != 32
            or len(means) != 1 or len(standard_deviations) != 1
            or not np.isfinite(float(means[0]))
            or not np.isfinite(float(standard_deviations[0]))
            or float(standard_deviations[0]) <= 0.0):
        raise ValueError("checkpoint train-only normalizer is invalid")

    expected_digest = fixed_config.get("expected_checkpoint_sha256")
    if not isinstance(expected_digest, str) or len(expected_digest) != 64:
        raise ValueError("fixed-point config lacks authoritative checkpoint digest")


def build_validated_model(model_config_path, checkpoint_path,
                          fixed_config_path):
    """Return an eval-mode model and audit metadata after strict validation."""

    model_config_path = Path(model_config_path)
    checkpoint_path = Path(checkpoint_path)
    fixed_config_path = Path(fixed_config_path)
    model_config = read_json(model_config_path)
    fixed_config = read_json(fixed_config_path)
    _validate_model_contract(model_config, fixed_config)
    actual_digest = sha256_file(checkpoint_path)
    if actual_digest != fixed_config["expected_checkpoint_sha256"]:
        raise ValueError("authoritative checkpoint SHA256 mismatch")

    checkpoint = torch.load(checkpoint_path, map_location="cpu",
                            weights_only=False)
    _validate_checkpoint_metadata(checkpoint, model_config, fixed_config)
    state_dict = checkpoint.get("state_dict")
    if not isinstance(state_dict, dict):
        raise ValueError("checkpoint state_dict is missing")
    observed_shapes = {name: tuple(tensor.shape)
                       for name, tensor in state_dict.items()}
    if observed_shapes != EXPECTED_PARAMETER_SHAPES:
        raise ValueError("checkpoint parameter names or shapes differ from contract")

    contract = fixed_config["model_contract"]
    # Construct CNN1D directly with every behavior-affecting argument instead
    # of relying on build_classifier defaults.  This makes dilation=1 and the
    # multistat pooling order explicit in the exported contract.
    model = CNN1D(
        input_channels=contract["input_channels"],
        class_count=contract["class_count"],
        channels=contract["channels"],
        kernel_size=contract["kernel_size"],
        dropout=model_config["dropout"],
        pooling_contract=contract["pooling_contract"],
        dilations=contract["dilations"])
    model.load_state_dict(state_dict, strict=True)
    model.eval()

    inventory = []
    for name, tensor in model.state_dict().items():
        # Hash a canonical little-endian float32 byte stream, not PyTorch's
        # container serialization.  The digest therefore describes numeric
        # content and remains stable across checkpoint archive implementations.
        values = tensor.detach().cpu().numpy().astype("<f4", copy=False)
        inventory.append({
            "name": name,
            "shape": list(values.shape),
            "dtype": "float32",
            "numeric_sha256": hashlib.sha256(values.tobytes(order="C")).hexdigest(),
        })
    metadata = {
        "schema_version": 1,
        "architecture_id": fixed_config["architecture_id"],
        "checkpoint_sha256": actual_digest,
        "checkpoint_seed": int(checkpoint["seed"]),
        "window_length": int(checkpoint["window_length"]),
        "model_config_sha256": sha256_file(model_config_path),
        "fixed_point_contract_sha256": sha256_file(fixed_config_path),
        "normalizer": checkpoint["normalizer"],
        "parameter_inventory": inventory,
        "layer_order": ["conv1", "relu1", "conv2", "relu2", "conv3",
                        "relu3", "global_average", "global_maximum",
                        "endpoint", "concatenate_average_max_endpoint",
                        "linear_classifier"],
        "pooling_feature_order": ["average[0:18]", "maximum[18:36]",
                                  "endpoint[36:54]"],
        "iid_features_loaded": False,
        "iid_metrics_computed": False,
    }
    return model, checkpoint, metadata


def main():
    """Validate one checkpoint and write a small provenance inventory."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--fixed-point-config", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("refusing to overwrite provenance inventory")
    _, _, metadata = build_validated_model(
        args.model_config, args.checkpoint, args.fixed_point_config)
    metadata["source_commit_sha"] = source_commit(args.repository_root)
    metadata["checkpoint_path"] = str(args.checkpoint.resolve())
    metadata["model_config_path"] = str(args.model_config.resolve())
    metadata["fixed_point_config_path"] = str(
        args.fixed_point_config.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")


if __name__ == "__main__":
    main()
