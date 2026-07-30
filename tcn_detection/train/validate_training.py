#!/usr/bin/env python3
"""Validate completed TCN training artifacts without scoring frozen test data.

This acceptance step checks reproducibility, checkpoint loadability, validation
predictions, and training-control invariants.  It deliberately does not compute
IID or OOD metrics: those partitions remain reserved for a separately reviewed
frozen evaluation after the model version has been accepted.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.train.common import build_classifier, estimate_macs, parameter_count, read_json


TCN_JOBS = ("tcn_L8", "tcn_L16", "tcn_L32")


def sha256_file(path):
    """Hash one potentially large artifact with bounded memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add_failure(report, message):
    """Accumulate independent failures so one audit exposes every defect."""

    report["failures"].append(message)


def read_validation_window_ids(path):
    """Return validation IDs without parsing any feature tensor or test metric.

    The immutable aggregate CSV contains every split.  For artifact alignment
    we inspect only the split and ID metadata and never deserialize
    ``features_json``.  Model inference below uses a synthetic shape probe, so
    this validator cannot accidentally turn IID/OOD rows into a tuning signal.
    """

    identifiers = set()
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["split"] != "validation":
                continue
            if not row["window_id"] or row["window_id"] in identifiers:
                raise ValueError("validation window IDs are empty or duplicated in {}".format(path))
            identifiers.add(row["window_id"])
    return identifiers


def validate_prediction_csv(path, expected_ids, report, job_name):
    """Validate persisted development predictions and probability semantics."""

    seen = set()
    classes = set()
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            window_id = row.get("window_id", "")
            if window_id in seen:
                add_failure(report, "{} validation predictions contain duplicate window IDs".format(job_name))
                continue
            seen.add(window_id)
            if row.get("split") != "validation":
                add_failure(report, "{} predictions expose a non-validation split".format(job_name))
            if row.get("target_label") not in {"0", "1", "2"} or row.get("prediction") not in {"0", "1", "2"}:
                add_failure(report, "{} predictions contain an invalid class ID".format(job_name))
                continue
            classes.add(row["target_label"])
            try:
                probabilities = [float(row[name]) for name in ("prob_safe", "prob_warning", "prob_critical")]
            except (KeyError, ValueError):
                add_failure(report, "{} predictions contain malformed probabilities".format(job_name))
                continue
            if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in probabilities):
                add_failure(report, "{} predictions contain non-finite or out-of-range probabilities".format(job_name))
            elif abs(sum(probabilities) - 1.0) > 1.0e-5:
                add_failure(report, "{} prediction probabilities do not sum to one".format(job_name))
    if seen != set(expected_ids):
        add_failure(report, "{} prediction IDs do not match the complete validation split".format(job_name))
    if classes != {"0", "1", "2"}:
        add_failure(report, "{} validation predictions do not cover all target classes".format(job_name))
    return len(seen)


def validate_history(summary, training_config, report, job_name):
    """Check best-epoch and early-stopping claims against the complete history."""

    history = summary.get("history", [])
    if not history or len(history) != int(summary.get("epochs_completed", -1)):
        add_failure(report, "{} has missing or inconsistent training history".format(job_name))
        return
    epochs = [int(row["epoch"]) for row in history]
    if epochs != list(range(1, len(history) + 1)):
        add_failure(report, "{} history epochs are not contiguous".format(job_name))
    selection_metric = summary.get("checkpoint_selection_metric", "validation_macro_f1")
    # v2 histories carry the full diagnostic surface and select by weighted
    # PR-AUC.  v1 histories lack these keys and retain their historical
    # Macro-F1 validation, allowing old immutable runs to remain auditable.
    if selection_metric == "weighted_ovr_pr_auc":
        required = {"checkpoint_score", "validation_macro_f1", "validation_balanced_accuracy",
                    "validation_safe_recall", "validation_warning_precision",
                    "validation_critical_recall", "validation_safe_window_false_alarm_rate",
                    "validation_pr_auc_safe", "validation_pr_auc_warning",
                    "validation_pr_auc_critical", "validation_macro_pr_auc"}
        if any(not required.issubset(row) for row in history):
            add_failure(report, "{} v2 history is missing checkpoint diagnostics".format(job_name))
            return
        values = [float(row["checkpoint_score"]) for row in history]
    elif selection_metric == "validation_macro_f1":
        values = [float(row["validation_macro_f1"]) for row in history]
    else:
        add_failure(report, "{} declares an unknown checkpoint selection metric".format(job_name))
        return
    losses = [float(row["train_focal_loss"]) for row in history]
    if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in values) or not all(math.isfinite(loss) and loss >= 0.0 for loss in losses):
        add_failure(report, "{} history contains non-finite loss or F1".format(job_name))
        return
    best_value = max(values)
    best_epoch = values.index(best_value) + 1
    declared_best = (summary.get("best_checkpoint_score") if selection_metric == "weighted_ovr_pr_auc"
                     else summary.get("best_validation_macro_f1"))
    if int(summary.get("best_epoch", -1)) != best_epoch or abs(float(declared_best) - best_value) > 1.0e-12:
        add_failure(report, "{} best epoch/selection score disagrees with its history".format(job_name))
    max_epochs = int(training_config["max_epochs"])
    patience = int(training_config["early_stopping_patience"])
    if len(history) > max_epochs:
        add_failure(report, "{} exceeded the configured maximum epoch count".format(job_name))
    elif len(history) < max_epochs and len(history) != best_epoch + patience:
        add_failure(report, "{} stopped before or after the configured stale-epoch patience".format(job_name))


def validate_job(job_name, models_dir, windows_dir, training_config_path, model_config_path, report):
    """Validate one length-specific TCN directory and return audit metadata."""

    length = int(job_name.split("L")[-1])
    job_dir = Path(models_dir) / job_name
    summary_path = job_dir / "training_summary.json"
    checkpoint_path = job_dir / "best_checkpoint.pt"
    prediction_path = job_dir / "validation_predictions.csv"
    log_path = Path(models_dir) / (job_name + ".log")
    required = (summary_path, checkpoint_path, prediction_path, log_path)
    if any(not path.is_file() or path.stat().st_size == 0 for path in required):
        add_failure(report, "{} is missing a non-empty checkpoint, summary, predictions, or log".format(job_name))
        return {}

    training_config = read_json(training_config_path)
    model_config = read_json(model_config_path)
    summary = read_json(summary_path)
    windows_path = Path(windows_dir) / ("windows_L{}.csv".format(length))
    expected_hashes = {"windows_sha256": sha256_file(windows_path),
                       "training_config_sha256": sha256_file(training_config_path),
                       "model_config_sha256": sha256_file(model_config_path)}
    for field, expected in expected_hashes.items():
        if summary.get(field) != expected:
            add_failure(report, "{} summary has a mismatched {}".format(job_name, field))
    if summary.get("model") != "tcn" or int(summary.get("window_length", -1)) != length:
        add_failure(report, "{} summary model or window length is inconsistent".format(job_name))
    validate_history(summary, training_config, report, job_name)

    normalizer = summary.get("normalizer", {})
    if (normalizer.get("source_split") != "train" or int(normalizer.get("window_length", -1)) != length
            or len(normalizer.get("mean", [])) != 5 or len(normalizer.get("std", [])) != 5):
        add_failure(report, "{} normalizer is not a five-channel train-only transform".format(job_name))

    # Strict reconstruction proves that the retained state dict, configuration,
    # and public [batch,5,L] -> [batch,3] port still agree.  A synthetic zero
    # probe checks numerical loadability without consulting frozen test inputs.
    try:
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        if checkpoint.get("model") != "tcn" or int(checkpoint.get("window_length", -1)) != length:
            raise ValueError("checkpoint metadata mismatch")
        if checkpoint.get("model_config") != model_config:
            raise ValueError("checkpoint model configuration mismatch")
        model = build_classifier("tcn", model_config)
        model.load_state_dict(checkpoint["state_dict"], strict=True)
        model.eval()
        with torch.no_grad():
            logits = model(torch.zeros(1, 5, length))
        if tuple(logits.shape) != (1, 3) or not bool(torch.isfinite(logits).all()):
            raise ValueError("checkpoint inference is non-finite or has the wrong shape")
    except Exception as error:
        add_failure(report, "{} checkpoint cannot be reconstructed: {}".format(job_name, error))
        model = build_classifier("tcn", model_config)

    expected_parameters = parameter_count(model)
    expected_macs = estimate_macs(model, length)
    if int(summary.get("parameter_count", -1)) != expected_parameters or int(summary.get("estimated_macs_per_window", -1)) != expected_macs:
        add_failure(report, "{} parameter or MAC count differs from the configured TCN".format(job_name))

    expected_ids = read_validation_window_ids(windows_path)
    prediction_count = validate_prediction_csv(prediction_path, expected_ids, report, job_name)
    events = []
    with log_path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                add_failure(report, "{} log contains a non-JSON progress line".format(job_name))
    epoch_events = [event for event in events if event.get("event") == "epoch"]
    if len(epoch_events) != int(summary.get("epochs_completed", -1)) or not events or events[-1].get("event") != "training_complete":
        add_failure(report, "{} log does not match the completed epoch history".format(job_name))

    return {"window_length": length, "prediction_count": prediction_count,
            "best_epoch": summary.get("best_epoch"), "best_validation_macro_f1": summary.get("best_validation_macro_f1"),
            "checkpoint_selection_metric": summary.get("checkpoint_selection_metric", "validation_macro_f1"),
            "best_checkpoint_score": summary.get("best_checkpoint_score", summary.get("best_validation_macro_f1")),
            "epochs_completed": summary.get("epochs_completed"), "parameter_count": expected_parameters,
            "estimated_macs_per_window": expected_macs, "median_cpu_latency_ms": summary.get("median_cpu_latency_ms"),
            "training_wall_seconds": summary.get("training_wall_seconds"),
            "checkpoint_sha256": sha256_file(checkpoint_path), "summary_sha256": sha256_file(summary_path),
            "predictions_sha256": sha256_file(prediction_path), "log_sha256": sha256_file(log_path)}


def main():
    """Run the selected-job acceptance audit and publish one JSON result."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", required=True, type=Path)
    parser.add_argument("--windows-dir", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--jobs", nargs="+", choices=TCN_JOBS, default=list(TCN_JOBS))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("refusing to overwrite training validation report: {}".format(args.output))

    report = {"schema_version": 1, "status": "FAIL", "failures": [], "jobs": {}}
    manifest_path = args.models_dir / "parallel_training_manifest.json"
    if not manifest_path.is_file():
        add_failure(report, "missing parallel training manifest")
        manifest = {}
    else:
        manifest = read_json(manifest_path)
        manifest_jobs = {job.get("name"): job for job in manifest.get("jobs", [])}
        if manifest.get("status") != "PASS" or set(manifest_jobs) != set(args.jobs):
            add_failure(report, "launcher manifest is not PASS or does not match selected TCN jobs")
        for name in args.jobs:
            job = manifest_jobs.get(name, {})
            if job.get("status") != "PASS" or job.get("exit_code") != 0:
                add_failure(report, "launcher job did not complete successfully: {}".format(name))

    for name in args.jobs:
        report["jobs"][name] = validate_job(name, args.models_dir, args.windows_dir,
                                                args.training_config, args.model_config, report)
    report["manifest_sha256"] = sha256_file(manifest_path) if manifest_path.is_file() else ""
    report["status"] = "PASS" if not report["failures"] else "FAIL"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    if report["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
