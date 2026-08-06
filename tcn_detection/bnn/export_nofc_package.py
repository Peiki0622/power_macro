#!/usr/bin/env python3
"""Fold a W1A1 checkpoint into a packed XNOR/popcount deployment package."""

from __future__ import print_function

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.bnn.binary_layers import binary_weight_bits
from power_macro.tcn_detection.bnn.bittrue_nofc import load_package, run_bittrue
from power_macro.tcn_detection.bnn.input_encoding import encode_windows
from power_macro.tcn_detection.bnn.nofc_model import BinaryNoFCModel
from power_macro.tcn_detection.bnn.train_nofc_bnn import (
    load_training_arrays,
)


def sha256_file(path):
    """Hash one published package input or packed weight file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fold_batchnorm_threshold(weight, batch_norm):
    """Fold one bipolar convolution and BN into integer popcount compares.

    A logical XNOR popcount ``p`` represents bipolar convolution ``2*p-N``,
    where ``N`` is input_channels*kernel_size.  Solving the BN output >= 0
    inequality yields one integer threshold per output channel.  Negative BN
    scale is represented by an inversion flag, retaining exact equality for
    both normal and sign-reversed channels.
    """

    if weight.ndim != 3 or weight.shape[0] < 1:
        raise ValueError("convolution weight must have [O,C,K] shape")
    channels, kernel = int(weight.shape[1]), int(weight.shape[2])
    sample_count = channels * kernel
    gamma = batch_norm.weight.detach().cpu().numpy().astype(np.float64)
    beta = batch_norm.bias.detach().cpu().numpy().astype(np.float64)
    mean = batch_norm.running_mean.detach().cpu().numpy().astype(np.float64)
    variance = batch_norm.running_var.detach().cpu().numpy().astype(np.float64)
    epsilon = float(batch_norm.eps)
    if any(array.shape != (weight.shape[0],)
           for array in (gamma, beta, mean, variance)):
        raise ValueError("BatchNorm channel shape differs from convolution")
    thresholds = []
    inversion = []
    for scale, offset, running_mean, running_var in zip(
            gamma, beta, mean, variance):
        if running_var < 0.0 or not np.isfinite(running_var):
            raise ValueError("BatchNorm variance is invalid")
        normalized_scale = scale / math.sqrt(running_var + epsilon)
        if not np.isfinite(normalized_scale) or not np.isfinite(offset):
            raise ValueError("BatchNorm parameters are not finite")
        if abs(normalized_scale) < 1.0e-15:
            # A constant BN output is still expressible using a threshold just
            # outside [0,N] and the inversion bit; no floating state is stored.
            threshold = sample_count + 1
            invert = bool(offset >= 0.0)
        else:
            boundary = (sample_count + running_mean
                        - offset / normalized_scale) / 2.0
            if normalized_scale > 0.0:
                threshold = int(math.ceil(boundary))
                invert = False
            else:
                threshold = int(math.floor(boundary)) + 1
                invert = True
        thresholds.append(threshold)
        inversion.append(int(invert))
    return np.asarray(thresholds, dtype=np.int64), np.asarray(inversion, dtype=np.uint8)


def build_package(model, vote_k):
    """Build an in-memory deployment manifest and binary layer tensors."""

    if not isinstance(model, BinaryNoFCModel) or model.mode != "w1a1":
        raise ValueError("export requires a W1A1 BinaryNoFCModel")
    vote_k = int(vote_k)
    if not 1 <= vote_k <= 32:
        raise ValueError("vote K must be within 1..32")
    descriptions = []
    tensors = {}
    for name, convolution, batch_norm in (
            ("conv1", model.conv1, model.bn1),
            ("conv2", model.conv2, model.bn2),
            ("head", model.head, model.head_bn)):
        bits = binary_weight_bits(convolution.weight.detach().cpu()).numpy()
        thresholds, inversion = fold_batchnorm_threshold(
            convolution.weight, batch_norm)
        descriptions.append({"name": name, "shape": list(bits.shape),
                             "thresholds": thresholds.tolist(),
                             "inversion_flags": inversion.tolist()})
        tensors[name] = bits.astype(np.uint8, copy=False)
    return {
        "schema_version": 1,
        "architecture_id": "bnn_therm32_w1a1_nofc_l32",
        "model_name": "bnn_therm32_w1a1_nofc_l32",
        "width": int(model.width), "window_length": 32,
        "input_channels": 32, "weight_bits": 1, "activation_bits": 1,
        "classifier_present": False, "batchnorm_present": False,
        "input_encoding": "bit[j] = 1 if j < sensor_code else 0",
        "padding_bit": 0, "vote_k": vote_k, "layers": descriptions,
        "tensors": tensors,
    }


def write_package(package, output_dir):
    """Write packed weights and manifest once, refusing replacement."""

    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError("refusing to overwrite BNN deployment package")
    output_dir.mkdir(parents=True, exist_ok=False)
    weights_dir = output_dir / "weights"
    weights_dir.mkdir()
    manifest = {key: value for key, value in package.items() if key != "tensors"}
    for description in manifest["layers"]:
        name = description["name"]
        path = weights_dir / (name + ".bin")
        np.packbits(package["tensors"][name].reshape(-1), bitorder="big").tofile(str(path))
        description["weights_file"] = str(path.relative_to(output_dir))
        description["weights_sha256"] = sha256_file(path)
        description["entry_count"] = int(package["tensors"][name].size)
    (output_dir / "package.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify_model_equals_bittrue(model, package_root, codes, vote_k):
    """Compare all hard temporal bits and alarms against the deployment path."""

    model.eval()
    package = load_package(package_root)
    bits = []
    predictions = []
    with torch.no_grad():
        for start in range(0, len(codes), 512):
            batch = torch.from_numpy(
                encode_windows(codes[start:start + 512]).astype(np.float32))
            hard = model.hard_vote(batch, vote_k)
            bits.append(hard["temporal_bits"].cpu().numpy().astype(np.uint8))
            predictions.append(hard["alarm"].cpu().numpy().astype(np.uint8))
    training_bits = np.concatenate(bits)
    training_predictions = np.concatenate(predictions)
    bittrue = run_bittrue(codes, package, batch_size=512)
    if not np.array_equal(training_bits, bittrue["temporal_bits"]):
        raise ValueError("training binary temporal bits differ from bit-true output")
    if not np.array_equal(training_predictions, bittrue["predictions"]):
        raise ValueError("training binary alarms differ from bit-true output")
    return {"rows": int(len(codes)), "temporal_bits_equal": True,
            "alarms_equal": True, "vote_k": int(vote_k)}


def export_checkpoint(checkpoint_path, windows, output_dir, vote_k):
    """Load one W1A1 checkpoint, export it, and prove validation equality."""

    checkpoint = torch.load(checkpoint_path, map_location="cpu",
                            weights_only=False)
    if checkpoint.get("stage") != "w1a1" or checkpoint.get("mode") != "w1a1":
        raise ValueError("checkpoint is not a W1A1 deployment stage")
    model = BinaryNoFCModel(int(checkpoint["width"]), "w1a1")
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    arrays = load_training_arrays(windows)
    # ``validation_features`` are already thermometer bits, so recover codes
    # directly from their asserted-prefix population rather than re-reading IID.
    validation_codes = np.sum(arrays["validation_features"], axis=1).astype(np.int16)
    package = build_package(model, vote_k)
    manifest = write_package(package, output_dir)
    equality = verify_model_equals_bittrue(model, output_dir,
                                           validation_codes, vote_k)
    (Path(output_dir) / "validation_equality.json").write_text(
        json.dumps(equality, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest, equality


def parse_args():
    """Parse one immutable checkpoint/package conversion."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--vote-k", required=True, type=int)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    manifest, equality = export_checkpoint(
        args.checkpoint, args.windows, args.output_dir, args.vote_k)
    print(json.dumps({"status": "PASS", "width": manifest["width"],
                      "equality": equality}, sort_keys=True))
