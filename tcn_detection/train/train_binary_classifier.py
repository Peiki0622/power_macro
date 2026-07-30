#!/usr/bin/env python3
"""Train one causal TCN for Safe/Critical current-state classification."""

from __future__ import print_function

import argparse
import csv
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.dataset.model_data import (
    apply_normalizer, filter_split, fit_normalizer, load_window_table,
    sha256_file, write_json)
from power_macro.tcn_detection.evaluate.binary_metrics import binary_window_metrics
from power_macro.tcn_detection.train.common import (
    benchmark_latency_ms, build_classifier, configure_cpu,
    configure_training_objective, estimate_macs, make_loader, parameter_count,
    read_json)
from power_macro.tcn_detection.train.train_classifier import (
    log_event, predict, save_checkpoint_atomic)


BINARY_CLASS_IDS = (0, 1)


def checkpoint_metrics(labels, probabilities):
    """Return validation diagnostics and the exact checkpoint ordering key.

    Critical PR-AUC is primary because Critical occupies only about six percent
    of windows.  The remaining fields implement the predeclared deterministic
    tie-breaks; Safe FAR is negated so larger tuple values always rank better.
    """

    predictions = np.asarray(probabilities).argmax(axis=1)
    report = binary_window_metrics(labels, predictions, probabilities)
    compact = {
        "validation_critical_pr_auc": report["critical_pr_auc"],
        "validation_macro_f1": report["macro_f1"],
        "validation_balanced_accuracy": report["balanced_accuracy"],
        "validation_critical_recall": report["critical_recall"],
        "validation_critical_precision": report["critical_precision"],
        "validation_safe_recall": report["per_class"]["0"]["recall"],
        "validation_safe_window_false_alarm_rate": report[
            "safe_window_false_alarm_rate"],
        "validation_critical_roc_auc": report["critical_roc_auc"],
        "validation_log_loss": report["log_loss"],
        "checkpoint_selection_metric": "critical_pr_auc",
        "checkpoint_score": report["critical_pr_auc"],
    }
    compact["selection_key"] = [
        compact["validation_critical_pr_auc"],
        compact["validation_macro_f1"],
        compact["validation_balanced_accuracy"],
        compact["validation_critical_recall"],
        -compact["validation_safe_window_false_alarm_rate"],
    ]
    return compact


def write_validation_predictions(path, table, probabilities):
    """Persist only binary validation probabilities and non-feature metadata."""

    fields = ["window_id", "trace_id", "split", "end_index", "target_label",
              "source_state_label", "prediction", "prob_safe", "prob_critical"]
    temporary = Path(path).with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row, probability in zip(table.metadata, probabilities):
            if row["split"] != "validation":
                raise ValueError("binary prediction writer accepts validation rows only")
            writer.writerow({
                "window_id": row["window_id"], "trace_id": row["trace_id"],
                "split": row["split"], "end_index": row["end_index"],
                "target_label": row["target_label"],
                "source_state_label": row["source_state_label"],
                "prediction": int(np.argmax(probability)),
                "prob_safe": "{:.9g}".format(probability[0]),
                "prob_critical": "{:.9g}".format(probability[1]),
            })
    temporary.replace(path)


def parse_args():
    """Parse one immutable binary training run."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main():
    """Train from scratch and retain the validation-selected checkpoint only."""

    args = parse_args()
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite binary model run")
    training_config = read_json(args.training_config)
    model_config = read_json(args.model_config)
    if (int(model_config.get("class_count", -1)) != 2
            or model_config.get("class_names") != {"0": "Safe", "1": "Critical"}):
        raise ValueError("binary trainer requires a two-class Safe/Critical model config")
    if training_config.get("checkpoint_selection_metric") != "critical_pr_auc":
        raise ValueError("binary checkpoint selection must be Critical PR-AUC")
    configure_cpu(args.seed, training_config["cpu_threads_per_process"])

    # Streaming split filtering occurs before features_json parsing.  This is
    # the structural guarantee that frozen IID features never enter a process
    # capable of updating weights or selecting an epoch.
    table = load_window_table(args.windows, splits={"train", "validation"})
    if set(np.unique(table.labels)) != {0, 1}:
        raise ValueError("binary training windows must contain both classes only")
    train_raw = filter_split(table, "train")
    validation_raw = filter_split(table, "validation")
    normalizer = fit_normalizer(train_raw)
    train = apply_normalizer(train_raw, normalizer)
    validation = apply_normalizer(validation_raw, normalizer)
    sampler, shuffle, criterion, strategy = configure_training_objective(
        train.labels, training_config, args.seed, class_ids=BINARY_CLASS_IDS)
    if strategy["loss_type"] not in {"cross_entropy", "focal"}:
        raise ValueError("binary experiment supports direct CE or focal objectives only")
    train_loader = make_loader(
        train.features, train.labels, training_config["batch_size"],
        shuffle=shuffle, sampler=sampler, seed=args.seed)
    model = build_classifier("tcn", model_config)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=float(training_config["learning_rate"]),
        weight_decay=float(training_config["weight_decay"]))

    args.output_dir.mkdir(parents=True, exist_ok=False)
    checkpoint_path = args.output_dir / "best_checkpoint.pt"
    best_key = None
    best_epoch = 0
    stale_epochs = 0
    history = []
    started = time.perf_counter()
    log_event("training_start", task="safe_critical_binary", seed=args.seed,
              window_length=table.length, train_windows=len(train.labels),
              validation_windows=len(validation.labels),
              training_strategy=strategy)
    for epoch in range(1, int(training_config["max_epochs"]) + 1):
        epoch_started = time.perf_counter()
        model.train()
        losses = []
        for inputs, targets in train_loader:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(inputs), targets)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        _, probabilities = predict(
            model, validation.features, training_config["batch_size"])
        if probabilities.shape != (len(validation.labels), 2):
            raise ValueError("binary TCN did not emit [N,2] probabilities")
        metrics = checkpoint_metrics(validation.labels, probabilities)
        selection_key = tuple(float(value) for value in metrics.pop("selection_key"))
        record = {"epoch": epoch, "train_loss": float(np.mean(losses))}
        record.update(metrics)
        history.append(record)
        improved = best_key is None or selection_key > best_key
        if improved:
            best_key = selection_key
            best_epoch = epoch
            stale_epochs = 0
            save_checkpoint_atomic({
                "schema_version": 1, "task": "safe_critical_binary",
                "model": "tcn", "model_config": model_config,
                "window_length": table.length, "seed": int(args.seed),
                "normalizer": normalizer, "state_dict": model.state_dict(),
                "best_epoch": epoch, "selection_key": list(selection_key),
                "validation_metrics": metrics,
            }, checkpoint_path)
        else:
            stale_epochs += 1
        log_event("epoch", epoch=epoch, train_loss=record["train_loss"],
                  validation_critical_pr_auc=metrics["validation_critical_pr_auc"],
                  validation_macro_f1=metrics["validation_macro_f1"],
                  best_epoch=best_epoch, stale_epochs=stale_epochs,
                  improved=improved,
                  epoch_seconds=time.perf_counter() - epoch_started)
        if stale_epochs >= int(training_config["early_stopping_patience"]):
            log_event("early_stopping", epoch=epoch, best_epoch=best_epoch,
                      patience=int(training_config["early_stopping_patience"]))
            break

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    _, probabilities = predict(model, validation.features,
                               training_config["batch_size"])
    write_validation_predictions(
        args.output_dir / "validation_predictions.csv", validation, probabilities)
    final_metrics = checkpoint_metrics(validation.labels, probabilities)
    final_metrics.pop("selection_key")
    summary = {
        "schema_version": 1, "task": "safe_critical_binary",
        "model": "tcn", "seed": int(args.seed),
        "window_length": table.length, "best_epoch": best_epoch,
        "epochs_completed": len(history), "history": history,
        "checkpoint_selection_metric": "critical_pr_auc",
        "best_checkpoint_score": final_metrics["checkpoint_score"],
        "best_validation_metrics": final_metrics,
        "train_observed_class_counts": strategy["observed_class_counts"],
        "training_strategy": strategy, "normalizer": normalizer,
        "iid_features_loaded": False,
        "parameter_count": parameter_count(model),
        "estimated_macs_per_window": estimate_macs(
            model, table.length, model_config["input_channels"]),
        "median_cpu_latency_ms": benchmark_latency_ms(
            model, table.length, model_config["input_channels"]),
        "windows_sha256": sha256_file(args.windows),
        "training_config_sha256": sha256_file(args.training_config),
        "model_config_sha256": sha256_file(args.model_config),
        "runtime": {"torch": torch.__version__,
                    "python": platform.python_version(),
                    "cpu_threads": torch.get_num_threads()},
        "training_wall_seconds": time.perf_counter() - started,
    }
    write_json(args.output_dir / "training_summary.json", summary)
    log_event("training_complete", best_epoch=best_epoch,
              best_checkpoint_score=summary["best_checkpoint_score"],
              epochs_completed=len(history),
              training_wall_seconds=summary["training_wall_seconds"])


if __name__ == "__main__":
    main()
