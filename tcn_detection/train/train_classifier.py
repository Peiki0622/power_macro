#!/usr/bin/env python3
"""Train one CNN or causal TCN from immutable causal-window CSV indexes."""

from __future__ import print_function

import argparse
import csv
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch
from power_macro.tcn_detection.dataset.model_data import apply_normalizer, filter_split, fit_normalizer, load_window_table, sha256_file, write_json
from power_macro.tcn_detection.evaluate.metrics import window_metrics
from power_macro.tcn_detection.train.common import (benchmark_latency_ms, build_classifier, configure_cpu,
                                                     configure_training_objective, estimate_macs, make_loader,
                                                     parameter_count, read_json)


def predict(model, features, batch_size):
    """Return endpoint logits and public three-class probabilities."""

    loader = make_loader(features, np.zeros(len(features), dtype=np.int64), batch_size)
    model.eval()
    logits = []
    with torch.no_grad():
        for inputs, _ in loader:
            logits.append(model(inputs).cpu().numpy())
    values = np.concatenate(logits, axis=0)
    if str(getattr(model, "output_semantics", "")).startswith("ordinal_risk_critical"):
        # Use the model's audited nested-head mapping rather than duplicating
        # clamp arithmetic in NumPy.  This keeps training validation, frozen
        # evaluation, and unit tests on exactly one probability definition.
        probabilities = model.probabilities_from_logits(torch.from_numpy(values)).numpy()
    else:
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


def save_checkpoint_atomic(payload, checkpoint_path):
    """Publish a checkpoint only after ``torch.save`` completes successfully.

    A killed process can leave a direct ``torch.save`` target truncated.  The
    temporary file remains private to this immutable model directory until the
    complete pickle/zip payload has been closed, then ``Path.replace`` exposes
    it atomically.  A failed run is retained for diagnosis and never resumed by
    overwriting the same version directory.
    """

    checkpoint_path = Path(checkpoint_path)
    temporary = checkpoint_path.with_suffix(checkpoint_path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(checkpoint_path)


def log_event(event, **fields):
    """Emit one machine-readable progress record and flush it to the job log."""

    payload = {"event": event}
    payload.update(fields)
    print(json.dumps(payload, sort_keys=True), flush=True)


def validation_checkpoint_metrics(labels, probabilities, checkpoint_metric_weights=None):
    """Compute epoch metrics and the explicitly configured selection score.

    The v2 checkpoint score is a weighted sum of one-vs-rest average precision:
    Safe=0.30, Warning=0.20, Critical=0.50 in the formal configs.  Average
    precision measures ranking quality across every possible threshold and is
    therefore a better training-selection signal than one argmax operating
    point.  Critical receives the largest weight because missing an imminent
    violation is the dominant safety risk, while retaining non-zero Safe and
    Warning weights prevents a one-class ranking from appearing acceptable.

    A missing weight mapping is the intentional v1 compatibility path: those
    immutable configurations historically selected Macro-F1.  New mappings
    are validated strictly so malformed or non-normalized weights cannot alter
    experiment selection silently.
    """

    probabilities = np.asarray(probabilities, dtype=np.float64)
    predictions = probabilities.argmax(axis=1)
    report = window_metrics(labels, predictions, probabilities)
    compact = {
        "validation_macro_f1": report["macro_f1"],
        "validation_balanced_accuracy": report["balanced_accuracy"],
        "validation_safe_recall": report["per_class"]["0"]["recall"],
        "validation_warning_precision": report["per_class"]["1"]["precision"],
        "validation_critical_recall": report["per_class"]["2"]["recall"],
        "validation_safe_window_false_alarm_rate": report["safe_window_false_alarm_rate"],
        "validation_pr_auc_safe": report["pr_auc_ovr"]["0"],
        "validation_pr_auc_warning": report["pr_auc_ovr"]["1"],
        "validation_pr_auc_critical": report["pr_auc_ovr"]["2"],
        "validation_macro_pr_auc": report["macro_pr_auc_ovr"],
    }
    if checkpoint_metric_weights is None:
        compact["checkpoint_selection_metric"] = "validation_macro_f1"
        compact["checkpoint_score"] = compact["validation_macro_f1"]
        return compact

    expected_keys = {"0", "1", "2"}
    if set(checkpoint_metric_weights) != expected_keys:
        raise ValueError("checkpoint_metric_weights must define exactly classes 0, 1, and 2")
    weights = {key: float(checkpoint_metric_weights[key]) for key in expected_keys}
    if any(not np.isfinite(value) or value < 0.0 for value in weights.values()):
        raise ValueError("checkpoint metric weights must be finite and non-negative")
    if abs(sum(weights.values()) - 1.0) > 1.0e-12:
        raise ValueError("checkpoint metric weights must sum to one")
    compact["checkpoint_selection_metric"] = "weighted_ovr_pr_auc"
    compact["checkpoint_score"] = float(
        weights["0"] * compact["validation_pr_auc_safe"]
        + weights["1"] * compact["validation_pr_auc_warning"]
        + weights["2"] * compact["validation_pr_auc_critical"])
    return compact


def main():
    """Run deterministic supervised training and publish only the best checkpoint."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("cnn", "tcn", "ordinal_tcn", "ordinal_time_tcn"), required=True)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--seed", type=int,
                        help="Explicit experiment seed; omitted uses the versioned config seed.")
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite model output directory: {}".format(args.output_dir))
    training_config = read_json(args.training_config)
    model_config = read_json(args.model_config)
    effective_seed = int(training_config["seed"] if args.seed is None else args.seed)
    configure_cpu(effective_seed, training_config["cpu_threads_per_process"])
    # Parse only the two development splits.  The full immutable file hash is
    # still recorded below, but IID/OOD tensors never enter a training process.
    table = load_window_table(args.windows, splits={"train", "validation"})
    train_raw = filter_split(table, "train")
    validation_raw = filter_split(table, "validation")
    normalizer = fit_normalizer(train_raw)
    train = apply_normalizer(train_raw, normalizer)
    validation = apply_normalizer(validation_raw, normalizer)
    sampler, shuffle, criterion, strategy = configure_training_objective(
        train.labels, training_config, effective_seed)
    if args.model == "ordinal_tcn" and strategy["loss_type"] != "ordinal_bce":
        raise ValueError("ordinal_tcn requires loss_type=ordinal_bce")
    if args.model != "ordinal_tcn" and strategy["loss_type"] == "ordinal_bce":
        raise ValueError("ordinal_bce requires model=ordinal_tcn")
    if args.model == "ordinal_time_tcn" and strategy["loss_type"] != "ordinal_time":
        raise ValueError("ordinal_time_tcn requires loss_type=ordinal_time")
    if args.model != "ordinal_time_tcn" and strategy["loss_type"] == "ordinal_time":
        raise ValueError("ordinal_time requires model=ordinal_time_tcn")

    training_targets = train.labels
    if strategy["loss_type"] == "ordinal_time":
        buckets = np.asarray([int(row.get("target_time_bucket", -1)) for row in train.metadata], dtype=np.int64)
        if np.any((buckets < 0) | (buckets > 3)):
            raise ValueError("ordinal-time windows require target_time_bucket values in 0..3")
        if np.any((buckets > 0) & (train.labels != 2)):
            raise ValueError("positive time buckets must belong to Critical class targets")
        # Encode two categorical targets in one TensorDataset label tensor.
        # The loss decodes ``class*4+bucket``; validation continues to use the
        # original class labels and therefore cannot consume future offsets.
        training_targets = train.labels * 4 + buckets
    train_loader = make_loader(train.features, training_targets, training_config["batch_size"],
                               shuffle=shuffle, sampler=sampler, seed=effective_seed)
    model = build_classifier(args.model, model_config)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(training_config["learning_rate"]), weight_decay=float(training_config["weight_decay"]))
    best_score = -1.0
    best_f1 = -1.0
    best_epoch = 0
    stale_epochs = 0
    history = []
    args.output_dir.mkdir(parents=True, exist_ok=False)
    checkpoint_path = args.output_dir / "best_checkpoint.pt"
    training_started = time.perf_counter()
    log_event("training_start", model=args.model, window_length=table.length,
              train_windows=len(train.labels), validation_windows=len(validation.labels),
              max_epochs=int(training_config["max_epochs"]), cpu_threads=torch.get_num_threads(),
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
        _, validation_probabilities = predict(model, validation.features, training_config["batch_size"])
        validation_metrics = validation_checkpoint_metrics(
            validation.labels, validation_probabilities,
            training_config.get("checkpoint_metric_weights"))
        # ``train_focal_loss`` remains as a compatibility alias consumed by the
        # v1 artifact validator.  ``train_loss`` is the truthful generic name
        # for v2 arms that may use either cross entropy or focal loss.
        mean_train_loss = float(np.mean(losses))
        epoch_record = {"epoch": epoch, "train_loss": mean_train_loss,
                        "train_focal_loss": mean_train_loss}
        epoch_record.update(validation_metrics)
        history.append(epoch_record)
        improved = validation_metrics["checkpoint_score"] > best_score + 1.0e-12
        if improved:
            best_score = validation_metrics["checkpoint_score"]
            best_f1 = validation_metrics["validation_macro_f1"]
            best_epoch = epoch
            stale_epochs = 0
            # The checkpoint is deliberately self-contained: a future evaluator
            # cannot accidentally fit a different normalizer from test windows.
            save_checkpoint_atomic({"model": args.model, "model_config": model_config, "window_length": table.length,
                                    "normalizer": normalizer, "state_dict": model.state_dict(), "best_epoch": epoch,
                                    "validation_macro_f1": best_f1,
                                    "checkpoint_selection_metric": validation_metrics["checkpoint_selection_metric"],
                                    "checkpoint_score": best_score,
                                    "validation_metrics": validation_metrics}, checkpoint_path)
        else:
            stale_epochs += 1
        log_event("epoch", epoch=epoch, train_loss=mean_train_loss,
                  validation_macro_f1=validation_metrics["validation_macro_f1"],
                  validation_macro_pr_auc=validation_metrics["validation_macro_pr_auc"],
                  checkpoint_selection_metric=validation_metrics["checkpoint_selection_metric"],
                  checkpoint_score=validation_metrics["checkpoint_score"], improved=improved,
                  best_epoch=best_epoch, best_checkpoint_score=best_score,
                  best_validation_macro_f1=best_f1, stale_epochs=stale_epochs,
                  epoch_seconds=time.perf_counter() - epoch_started)
        if not improved:
            if stale_epochs >= int(training_config["early_stopping_patience"]):
                log_event("early_stopping", epoch=epoch, patience=int(training_config["early_stopping_patience"]),
                          best_epoch=best_epoch, best_checkpoint_score=best_score,
                          checkpoint_selection_metric=validation_metrics["checkpoint_selection_metric"])
                break
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["state_dict"])
    _, validation_probabilities = predict(model, validation.features, training_config["batch_size"])
    write_validation_predictions(args.output_dir / "validation_predictions.csv", validation, validation_probabilities)
    summary = {"schema_version": 2 if "checkpoint_metric_weights" in training_config else 1,
               "model": args.model, "window_length": table.length, "best_epoch": best_epoch,
               "checkpoint_selection_metric": checkpoint["checkpoint_selection_metric"],
               "best_checkpoint_score": best_score, "best_validation_macro_f1": best_f1,
               "best_validation_metrics": checkpoint["validation_metrics"],
               "checkpoint_metric_weights": training_config.get("checkpoint_metric_weights"),
               "epochs_completed": len(history), "history": history,
               "train_observed_class_counts": strategy["observed_class_counts"], "training_strategy": strategy,
               "normalizer": normalizer, "parameter_count": parameter_count(model),
               "estimated_macs_per_window": estimate_macs(model, table.length, model_config["input_channels"]),
               "median_cpu_latency_ms": benchmark_latency_ms(model, table.length, model_config["input_channels"]),
               "windows_sha256": sha256_file(args.windows),
               "training_config_sha256": sha256_file(args.training_config), "model_config_sha256": sha256_file(args.model_config),
               "runtime": {"torch": torch.__version__, "python": platform.python_version(), "cpu_threads": torch.get_num_threads()},
               "training_wall_seconds": time.perf_counter() - training_started}
    write_json(args.output_dir / "training_summary.json", summary)
    log_event("training_complete", best_epoch=best_epoch, best_checkpoint_score=best_score,
              checkpoint_selection_metric=checkpoint["checkpoint_selection_metric"],
              best_validation_macro_f1=best_f1,
              epochs_completed=len(history), training_wall_seconds=summary["training_wall_seconds"])


if __name__ == "__main__":
    main()
