#!/usr/bin/env python3
"""Validate and rank a completed validation-only CNN hyperparameter search."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.train.common import build_classifier


EXPECTED_VALIDATION_WINDOWS = 22512


def sha256_file(path):
    """Hash one evidence file without loading it all into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rank_arms(arms):
    """Return the deterministic best-first order frozen before training.

    The first two terms reward typical ranking and classification quality.  A
    worst-seed recall term then penalizes fragile optimizer settings.  Remaining
    terms prefer balanced decisions, fewer Safe false alarms, and less seed
    variance.  Arm name is the final stable tie-break and has no quality claim.
    """

    return sorted(arms, key=lambda arm: (
        -arm["median_critical_pr_auc"], -arm["median_macro_f1"],
        -arm["worst_critical_recall"], -arm["median_balanced_accuracy"],
        arm["median_safe_far"], arm["critical_pr_auc_std"], arm["name"]))


def validate_predictions(path):
    """Require exactly the validation split and no train/IID prediction rows."""

    count = 0
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row.get("split") != "validation":
                raise ValueError("hyperparameter predictions are not validation-only")
            count += 1
    if count != EXPECTED_VALIDATION_WINDOWS:
        raise ValueError("unexpected validation prediction count")
    return count


def read_run(job):
    """Strictly validate one completed child and return its ranking metrics."""

    run_dir = Path(job["output_dir"])
    summary_path = run_dir / "training_summary.json"
    checkpoint_path = run_dir / "best_checkpoint.pt"
    predictions_path = run_dir / "validation_predictions.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if (summary.get("model") != "cnn"
            or summary.get("task") != "safe_critical_binary"
            or summary.get("iid_features_loaded") is not False
            or int(summary.get("seed", -1)) != int(job["seed"])
            or int(summary.get("window_length", -1)) != 32
            or summary.get("windows_sha256") != job["windows_sha256"]
            or summary.get("training_config_sha256")
            != job["training_config_sha256"]
            or summary.get("model_config_sha256") != job["model_config_sha256"]):
        raise ValueError("training summary violates search manifest: {}".format(
            job["name"]))
    model_config = json.loads(Path(job["model_config"]).read_text(encoding="utf-8"))
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model = build_classifier("cnn", model_config)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    validate_predictions(predictions_path)
    metrics = summary["best_validation_metrics"]
    training_config = json.loads(Path(job["training_config"]).read_text(
        encoding="utf-8"))
    return {
        "name": job["name"], "arm": job["arm"], "seed": int(job["seed"]),
        "learning_rate": float(job["learning_rate"]),
        "weight_decay": float(job["weight_decay"]),
        "training_parameters": {
            key: training_config.get(key) for key in (
                "learning_rate", "weight_decay", "batch_size", "max_epochs",
                "early_stopping_patience", "lr_scheduler", "scheduler_factor",
                "scheduler_patience", "scheduler_min_lr")
        },
        "best_epoch": int(summary["best_epoch"]),
        "critical_pr_auc": float(metrics["validation_critical_pr_auc"]),
        "macro_f1": float(metrics["validation_macro_f1"]),
        "balanced_accuracy": float(metrics["validation_balanced_accuracy"]),
        "critical_recall": float(metrics["validation_critical_recall"]),
        "critical_precision": float(metrics["validation_critical_precision"]),
        "safe_far": float(metrics["validation_safe_window_false_alarm_rate"]),
        "checkpoint": str(checkpoint_path.resolve()),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "training_summary": str(summary_path.resolve()),
        "training_summary_sha256": sha256_file(summary_path),
        "validation_predictions": str(predictions_path.resolve()),
        "validation_predictions_sha256": sha256_file(predictions_path),
    }


def aggregate_arm(name, runs):
    """Aggregate three seeds without selecting the best individual run."""

    if len(runs) != 3 or len({run["seed"] for run in runs}) != 3:
        raise ValueError("each hyperparameter arm requires three unique seeds")
    values = lambda field: np.asarray([run[field] for run in runs], dtype=float)
    return {
        "name": name, "learning_rate": runs[0]["learning_rate"],
        "weight_decay": runs[0]["weight_decay"],
        "training_parameters": runs[0]["training_parameters"],
        "median_critical_pr_auc": float(np.median(values("critical_pr_auc"))),
        "critical_pr_auc_std": float(np.std(values("critical_pr_auc"))),
        "median_macro_f1": float(np.median(values("macro_f1"))),
        "median_balanced_accuracy": float(np.median(values("balanced_accuracy"))),
        "worst_critical_recall": float(np.min(values("critical_recall"))),
        "median_critical_recall": float(np.median(values("critical_recall"))),
        "median_critical_precision": float(np.median(values("critical_precision"))),
        "median_safe_far": float(np.median(values("safe_far"))), "runs": runs,
    }


def markdown(report):
    """Render the complete arm ranking for direct review."""

    lines = ["# Binary CNN Hyperparameter Search", "",
             "All values are validation-only aggregates over three seeds. IID "
             "features and metrics were not loaded.", "",
             "| Rank | Arm | LR | Weight decay | Median Critical PR-AUC | "
             "Median Macro-F1 | Worst Critical recall | Median balanced acc. | "
             "Median Safe FAR | PR-AUC std |",
             "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for index, arm in enumerate(report["ranking"], 1):
        lines.append("| {} | {} | {:.6g} | {:.6g} | {:.6f} | {:.6f} | {:.6f} | "
                     "{:.6f} | {:.6f} | {:.6f} |".format(
                         index, arm["name"], arm["learning_rate"], arm["weight_decay"],
                         arm["median_critical_pr_auc"], arm["median_macro_f1"],
                         arm["worst_critical_recall"], arm["median_balanced_accuracy"],
                         arm["median_safe_far"], arm["critical_pr_auc_std"]))
    lines.extend(["", "Selected arm: `{}`.".format(report["selected_arm"]), ""])
    return "\n".join(lines)


def main():
    """Validate all 27 runs, rank nine arms, and publish validation evidence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite hyperparameter summary")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    jobs = manifest.get("jobs", [])
    expected_jobs = int(manifest.get("expected_job_count", -1))
    if (manifest.get("status") != "PASS"
            or manifest.get("scope") != "train_validation_only"
            or manifest.get("iid_features_loaded") is not False
            or manifest.get("iid_metrics_computed") is not False
            or expected_jobs < 1 or len(jobs) != expected_jobs
            or any(job.get("status") != "PASS" for job in jobs)):
        raise ValueError("search manifest is incomplete or crossed into IID")
    runs = [read_run(job) for job in jobs]
    arm_names = sorted({run["arm"] for run in runs})
    aggregates = [aggregate_arm(
        name, [run for run in runs if run["arm"] == name]) for name in arm_names]
    ranking = rank_arms(aggregates)
    report = {
        "schema_version": 1, "scope": "validation_only",
        "task": "safe_critical_binary", "model": "cnn",
        "iid_features_loaded": False, "iid_metrics_computed": False,
        "parameters_tuned_on_test": False,
        "selection_order": [
            "median_critical_pr_auc", "median_macro_f1",
            "worst_critical_recall", "median_balanced_accuracy",
            "lower_median_safe_far", "lower_critical_pr_auc_std", "arm_name"],
        "manifest_sha256": sha256_file(args.manifest),
        "selected_arm": ranking[0]["name"], "ranking": ranking,
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "selection.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "SELECTION.md").write_text(markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
