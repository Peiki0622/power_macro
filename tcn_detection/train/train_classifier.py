#!/usr/bin/env python3
"""Train one CNN or causal TCN from immutable causal-window CSV indexes."""

from __future__ import print_function

import argparse
import csv
import platform
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import f1_score

from power_macro.tcn_detection.dataset.model_data import apply_normalizer, filter_split, fit_normalizer, load_window_table, sha256_file, write_json
from power_macro.tcn_detection.train.common import (FocalLoss, benchmark_latency_ms, build_classifier, class_weights,
                                                     configure_cpu, estimate_macs, make_class_balanced_sampler,
                                                     make_loader, parameter_count, read_json)


def predict(model, features, batch_size):
    """Return endpoint logits and probabilities without mutating model state."""

    loader = make_loader(features, np.zeros(len(features), dtype=np.int64), batch_size)
    model.eval()
    logits = []
    with torch.no_grad():
        for inputs, _ in loader:
            logits.append(model(inputs).cpu().numpy())
    values = np.concatenate(logits, axis=0)
    shifted = values - values.max(axis=1, keepdims=True)
    probabilities = np.exp(shifted) / np.exp(shifted).sum(axis=1, keepdims=True)
    return values, probabilities


def write_validation_predictions(path, table, probabilities):
    """Persist validation outputs for audit, never as an input to later test tuning."""

    fields = ["window_id", "trace_id", "split", "end_index", "target_label", "prediction", "prob_safe", "prob_warning", "prob_critical"]
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row, probability in zip(table.metadata, probabilities):
            writer.writerow({"window_id": row["window_id"], "trace_id": row["trace_id"], "split": row["split"],
                             "end_index": row["end_index"], "target_label": row["target_label"],
                             "prediction": int(np.argmax(probability)), "prob_safe": "{:.9g}".format(probability[0]),
                             "prob_warning": "{:.9g}".format(probability[1]), "prob_critical": "{:.9g}".format(probability[2])})


def main():
    """Run deterministic supervised training and publish only the best checkpoint."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("cnn", "tcn"), required=True)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite model output directory: {}".format(args.output_dir))
    training_config = read_json(args.training_config)
    model_config = read_json(args.model_config)
    configure_cpu(training_config["seed"], training_config["cpu_threads_per_process"])
    table = load_window_table(args.windows)
    train_raw = filter_split(table, "train")
    validation_raw = filter_split(table, "validation")
    normalizer = fit_normalizer(train_raw)
    train = apply_normalizer(train_raw, normalizer)
    validation = apply_normalizer(validation_raw, normalizer)
    sampler, observed_counts = make_class_balanced_sampler(train.labels, training_config["train_class_ratio"], training_config["seed"])
    train_loader = make_loader(train.features, train.labels, training_config["batch_size"], sampler=sampler)
    model = build_classifier(args.model, model_config)
    criterion = FocalLoss(class_weights(train.labels), training_config["focal_gamma"])
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(training_config["learning_rate"]), weight_decay=float(training_config["weight_decay"]))
    best_f1 = -1.0
    best_epoch = 0
    stale_epochs = 0
    history = []
    args.output_dir.mkdir(parents=True, exist_ok=False)
    checkpoint_path = args.output_dir / "best_checkpoint.pt"
    for epoch in range(1, int(training_config["max_epochs"]) + 1):
        model.train()
        losses = []
        for inputs, targets in train_loader:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(inputs), targets)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        _, validation_probabilities = predict(model, validation.features, training_config["batch_size"])
        validation_predictions = validation_probabilities.argmax(axis=1)
        validation_f1 = float(f1_score(validation.labels, validation_predictions, labels=[0, 1, 2], average="macro", zero_division=0))
        history.append({"epoch": epoch, "train_focal_loss": float(np.mean(losses)), "validation_macro_f1": validation_f1})
        if validation_f1 > best_f1 + 1.0e-12:
            best_f1 = validation_f1
            best_epoch = epoch
            stale_epochs = 0
            # The checkpoint is deliberately self-contained: a future evaluator
            # cannot accidentally fit a different normalizer from test windows.
            torch.save({"model": args.model, "model_config": model_config, "window_length": table.length,
                        "normalizer": normalizer, "state_dict": model.state_dict(), "best_epoch": epoch,
                        "validation_macro_f1": validation_f1}, checkpoint_path)
        else:
            stale_epochs += 1
            if stale_epochs >= int(training_config["early_stopping_patience"]):
                break
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["state_dict"])
    _, validation_probabilities = predict(model, validation.features, training_config["batch_size"])
    write_validation_predictions(args.output_dir / "validation_predictions.csv", validation, validation_probabilities)
    summary = {"schema_version": 1, "model": args.model, "window_length": table.length, "best_epoch": best_epoch,
               "best_validation_macro_f1": best_f1, "epochs_completed": len(history), "history": history,
               "train_observed_class_counts": {str(key): value for key, value in observed_counts.items()},
               "normalizer": normalizer, "parameter_count": parameter_count(model), "estimated_macs_per_window": estimate_macs(model, table.length),
               "median_cpu_latency_ms": benchmark_latency_ms(model, table.length), "windows_sha256": sha256_file(args.windows),
               "training_config_sha256": sha256_file(args.training_config), "model_config_sha256": sha256_file(args.model_config),
               "runtime": {"torch": torch.__version__, "python": platform.python_version(), "cpu_threads": torch.get_num_threads()}}
    write_json(args.output_dir / "training_summary.json", summary)


if __name__ == "__main__":
    main()
