#!/usr/bin/env python3
"""Train a normal-only L=16 convolutional autoencoder baseline."""

from __future__ import print_function

import argparse
import platform
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.dataset.model_data import (apply_normalizer, filter_split, fit_normalizer, load_safe_stride_one_windows,
                                                          load_window_table, sha256_file, write_json)
from power_macro.tcn_detection.models.conv_autoencoder import ConvAutoencoder
from power_macro.tcn_detection.train.common import configure_cpu, make_loader, read_json


def reconstruction_errors(model, features, batch_size):
    """Return mean squared reconstruction error for every normal or test window."""

    loader = make_loader(features, np.zeros(len(features), dtype=np.int64), batch_size)
    values = []
    model.eval()
    with torch.no_grad():
        for inputs, _ in loader:
            reconstruction = model(inputs)
            values.append(((reconstruction - inputs).pow(2).mean(dim=(1, 2))).cpu().numpy())
    return np.concatenate(values, axis=0)


def main():
    """Fit normal-only CAE and freeze normal-quantile ordinal thresholds."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", required=True, type=Path, help="Existing L=16 supervised window index for train-only normalization.")
    parser.add_argument("--label-dir", required=True, type=Path, help="Derived label directory used to build Safe stride-one CAE windows.")
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite CAE output directory: {}".format(args.output_dir))
    training_config = read_json(args.training_config)
    model_config = read_json(args.model_config)
    configure_cpu(training_config["seed"], training_config["cpu_threads_per_process"])
    supervised = load_window_table(args.windows)
    if supervised.length != 16:
        raise ValueError("CAE baseline is defined only for L=16")
    # Fit common scaling from all train windows, not from validation/test and
    # not from an anomalous target label.  CAE inputs below are then restricted
    # to Safe windows as required by the literature-style normal-only baseline.
    normalizer = fit_normalizer(filter_split(supervised, "train"))
    train_safe = apply_normalizer(load_safe_stride_one_windows(args.label_dir, "train"), normalizer)
    validation_safe = apply_normalizer(load_safe_stride_one_windows(args.label_dir, "validation"), normalizer)
    train_loader = make_loader(train_safe.features, train_safe.labels, training_config["batch_size"], shuffle=True)
    model = ConvAutoencoder(input_channels=model_config["input_channels"], channels=model_config["cae_channels"], kernel_size=model_config["kernel_size"])
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(training_config["learning_rate"]), weight_decay=float(training_config["weight_decay"]))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    checkpoint_path = args.output_dir / "best_checkpoint.pt"
    best_loss = float("inf")
    best_epoch = 0
    stale_epochs = 0
    history = []
    for epoch in range(1, int(training_config["max_epochs"]) + 1):
        model.train()
        losses = []
        for inputs, _ in train_loader:
            optimizer.zero_grad(set_to_none=True)
            loss = (model(inputs) - inputs).pow(2).mean()
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        validation_loss = float(np.mean(reconstruction_errors(model, validation_safe.features, training_config["batch_size"])))
        history.append({"epoch": epoch, "train_mse": float(np.mean(losses)), "validation_safe_mse": validation_loss})
        if validation_loss < best_loss - 1.0e-12:
            best_loss = validation_loss
            best_epoch = epoch
            stale_epochs = 0
            torch.save({"model": "cae", "model_config": model_config, "window_length": 16, "normalizer": normalizer,
                        "state_dict": model.state_dict(), "best_epoch": epoch, "validation_safe_mse": validation_loss}, checkpoint_path)
        else:
            stale_epochs += 1
            if stale_epochs >= int(training_config["early_stopping_patience"]):
                break
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["state_dict"])
    normal_errors = np.concatenate([reconstruction_errors(model, train_safe.features, training_config["batch_size"]),
                                    reconstruction_errors(model, validation_safe.features, training_config["batch_size"])])
    thresholds = {"warning": float(np.quantile(normal_errors, model_config["cae_normal_warning_quantile"])),
                  "critical": float(np.quantile(normal_errors, model_config["cae_normal_critical_quantile"])),
                  "normal_window_count": int(len(normal_errors)), "normal_source_splits": ["train", "validation"]}
    write_json(args.output_dir / "thresholds.json", thresholds)
    write_json(args.output_dir / "training_summary.json", {"schema_version": 1, "model": "cae", "window_length": 16,
              "best_epoch": best_epoch, "best_validation_safe_mse": best_loss, "epochs_completed": len(history), "history": history,
              "normalizer": normalizer, "thresholds": thresholds, "windows_sha256": sha256_file(args.windows),
              "training_config_sha256": sha256_file(args.training_config), "model_config_sha256": sha256_file(args.model_config),
              "runtime": {"torch": torch.__version__, "python": platform.python_version(), "cpu_threads": torch.get_num_threads()}})


if __name__ == "__main__":
    main()
