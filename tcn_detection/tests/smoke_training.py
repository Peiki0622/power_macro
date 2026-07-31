#!/usr/bin/env python3
"""Run a bounded end-to-end TCN training smoke test in a temporary directory.

This script exercises the production launcher, classifier trainer, and artifact
validator together.  It intentionally uses synthetic development-only windows:
the goal is to verify orchestration and file contracts before a formal run, not
to estimate model quality or inspect frozen IID/OOD data.
"""

from __future__ import print_function

import csv
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import torch


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MODEL_CONFIG = REPOSITORY_ROOT / "power_macro" / "tcn_detection" / "config" / "model_tcn_v1.json"
BINARY_MODEL_CONFIG = (REPOSITORY_ROOT / "power_macro" / "tcn_detection" /
                       "config" / "model_tcn_state_code_binary_v1.json")
BINARY_CNN_MODEL_CONFIG = (REPOSITORY_ROOT / "power_macro" / "tcn_detection" /
                           "config" / "model_cnn_state_code_binary_small_v1.json")


def write_smoke_windows(path):
    """Create small L8 train/validation partitions containing all three labels.

    Each chronological sample has the same five online channels as the formal
    dataset.  Values vary by class, row, time, and channel so normalization and
    gradient code encounter non-zero variance.  IDs and endpoints are unique,
    allowing the validator to check prediction-to-window alignment exactly.
    """

    fields = ["window_id", "trace_id", "split", "end_index", "length",
              "target_label", "features_json"]
    rows = []
    for split, windows_per_class in (("train", 4), ("validation", 2)):
        for class_id in range(3):
            for occurrence in range(windows_per_class):
                features = []
                for time_index in range(8):
                    features.append([
                        float(class_id) + 0.01 * occurrence + 0.001 * time_index + 0.0001 * channel
                        for channel in range(5)
                    ])
                identifier = "{}_{}_{}".format(split, class_id, occurrence)
                rows.append({"window_id": identifier, "trace_id": "trace_" + identifier,
                             "split": split, "end_index": str(7 + occurrence), "length": "8",
                             "target_label": str(class_id), "features_json": json.dumps(features)})
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_smoke_training_config(path, use_v2=False):
    """Write a two-epoch CPU configuration for one requested contract version."""

    # Every field consumed by the production classifier remains explicit.  The
    # small batch and epoch limits bound runtime; the class ratio and optimizer
    # settings match the formal configuration closely enough to exercise the
    # same sampler, focal loss, early-stopping, and checkpoint branches.
    config = {
        "schema_version": 1,
        "seed": 20260725,
        "cpu_threads_per_process": 1,
        "batch_size": 6,
        "max_epochs": 2,
        "early_stopping_patience": 1,
        "learning_rate": 0.001,
        "weight_decay": 0.0001,
        "focal_gamma": 2.0,
        "train_class_ratio": {"0": 0.40, "1": 0.35, "2": 0.25},
    }
    if use_v2:
        # The v2 extension chooses the simplest ablation arm while exercising
        # every new configuration and artifact field.  Two epochs are enough
        # to verify weighted PR-AUC selection; this smoke run is deliberately
        # not interpreted as evidence about formal model quality.
        config.update({
            "schema_version": 2,
            "sampling_strategy": "natural",
            "loss_type": "cross_entropy",
            "class_weight_strategy": "none",
            "checkpoint_metric_weights": {"0": 0.30, "1": 0.20, "2": 0.50},
        })
    Path(path).write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_checked(command):
    """Run one production command and preserve captured diagnostics on failure."""

    completed = subprocess.run(command, cwd=REPOSITORY_ROOT, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if completed.returncode != 0:
        raise RuntimeError("command failed ({}):\n{}".format(completed.returncode, completed.stdout))
    return completed.stdout


def run_binary_smoke(root, model_name="tcn", use_scheduler=False):
    """Exercise a production binary trainer with tiny one-channel windows.

    ``model_name`` is intentionally passed through the same command-line
    interface used by formal jobs.  The smoke test therefore catches a common
    regression where CNN configuration exists but the launcher silently keeps
    constructing a TCN.  The synthetic table contains only development splits;
    no frozen formal window is read by this test.
    """

    windows_path = root / "windows_binary_L8.csv"
    fields = ["window_id", "trace_id", "split", "end_index", "length",
              "target_label", "source_state_label", "feature_channels",
              "features_json"]
    rows = []
    for split, count in (("train", 8), ("validation", 4)):
        for class_id in (0, 1):
            for occurrence in range(count):
                # Class-separated but non-constant histories exercise fitting,
                # normalization, probability writing, and two-logit inference.
                features = [[float(class_id) + occurrence * 0.01 + index * 0.001]
                            for index in range(8)]
                identifier = "{}_{}_{}".format(split, class_id, occurrence)
                rows.append({"window_id": identifier, "trace_id": "trace_" + identifier,
                             "split": split, "end_index": "7", "length": "8",
                             "target_label": str(class_id),
                             "source_state_label": "2" if class_id else "1",
                             "feature_channels": "1",
                             "features_json": json.dumps(features)})
    with windows_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    training_config = root / "binary_training_smoke.json"
    resolved_training = {
        "schema_version": 1, "cpu_threads_per_process": 1,
        "batch_size": 8, "max_epochs": 2, "early_stopping_patience": 1,
        "learning_rate": 0.001, "weight_decay": 0.0001,
        "sampling_strategy": "natural", "loss_type": "cross_entropy",
        "class_weight_strategy": "sqrt_inverse",
        "ordinal_positive_weight_strategy": "none",
        "checkpoint_selection_metric": "critical_pr_auc",
    }
    if use_scheduler:
        # Two epochs are sufficient to execute construction and scheduler.step;
        # this smoke test checks the production branch and persisted metadata,
        # not whether a tiny synthetic validation curve actually reaches a
        # plateau long enough to reduce the rate.
        resolved_training.update({
            "lr_scheduler": "reduce_on_plateau", "scheduler_factor": 0.5,
            "scheduler_patience": 1, "scheduler_min_lr": 0.00001})
    training_config.write_text(json.dumps(
        resolved_training, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output = root / ("binary_{}_model".format(model_name))
    model_config = (BINARY_CNN_MODEL_CONFIG if model_name == "cnn"
                    else BINARY_MODEL_CONFIG)
    command = [
        sys.executable, "-m",
        "power_macro.tcn_detection.train.train_binary_classifier",
        "--model", model_name,
        "--windows", str(windows_path), "--training-config", str(training_config),
        "--model-config", str(model_config), "--seed", "20260725",
        "--output-dir", str(output),
    ]
    run_checked(command)
    with (output / "validation_predictions.csv").open(
            newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        predictions = list(reader)
        prediction_fields = set(reader.fieldnames or [])
    if (len(predictions) != 8 or {row["split"] for row in predictions} != {"validation"}
            or "prob_warning" in prediction_fields
            or not {"prob_safe", "prob_critical"}.issubset(prediction_fields)):
        raise AssertionError("binary smoke prediction schema or membership failed")
    checkpoint = torch.load(output / "best_checkpoint.pt", map_location="cpu",
                            weights_only=False)
    from power_macro.tcn_detection.train.common import build_classifier
    model = build_classifier(checkpoint["model"], checkpoint["model_config"])
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    with torch.no_grad():
        logits = model(torch.zeros(2, 1, 8))
    if tuple(logits.shape) != (2, 2) or not bool(torch.isfinite(logits).all()):
        raise AssertionError("binary smoke checkpoint does not expose [N,2] logits")
    summary = json.loads((output / "training_summary.json").read_text(encoding="utf-8"))
    if (summary["checkpoint_selection_metric"] != "critical_pr_auc"
            or summary["iid_features_loaded"] is not False):
        raise AssertionError("binary smoke summary crossed selection/split contract")
    expected_scheduler = "reduce_on_plateau" if use_scheduler else "none"
    if (summary.get("lr_scheduler", {}).get("kind") != expected_scheduler
            or any("learning_rate" not in row for row in summary["history"])):
        raise AssertionError("binary smoke did not persist scheduler/rate history")
    print(json.dumps({"status": "PASS", "mode": "binary_{}".format(model_name),
                      "prediction_count": len(predictions)}, sort_keys=True))


def main():
    """Execute the smoke pipeline and assert every promised artifact contract."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v2", action="store_true",
                        help="Exercise explicit objective and weighted PR-AUC checkpoint contracts.")
    parser.add_argument("--binary", action="store_true",
                        help="Exercise the two-class Safe/Critical trainer and prediction schema.")
    parser.add_argument("--binary-cnn", action="store_true",
                        help="Exercise the two-class CNN trainer and prediction schema.")
    parser.add_argument("--binary-cnn-scheduler", action="store_true",
                        help="Exercise CNN training with validation-plateau LR scheduling.")
    args = parser.parse_args()
    if sum(bool(value) for value in (
            args.v2, args.binary, args.binary_cnn,
            args.binary_cnn_scheduler)) > 1:
        raise ValueError("smoke modes are mutually exclusive")

    with tempfile.TemporaryDirectory(prefix="tcn_training_smoke_") as temporary:
        root = Path(temporary)
        if args.binary:
            run_binary_smoke(root, "tcn")
            return
        if args.binary_cnn:
            run_binary_smoke(root, "cnn")
            return
        if args.binary_cnn_scheduler:
            run_binary_smoke(root, "cnn", use_scheduler=True)
            return
        windows_dir = root / "windows"
        labels_dir = root / "labels"
        models_dir = root / "models"
        windows_dir.mkdir()
        labels_dir.mkdir()
        windows_path = windows_dir / "windows_L8.csv"
        training_config = root / "training_smoke.json"
        write_smoke_windows(windows_path)
        write_smoke_training_config(training_config, use_v2=args.v2)

        # Invoke the production launcher even for one job.  This covers command
        # assembly, child log redirection, manifest state transitions, and the
        # immutable per-job output directory rather than bypassing orchestration.
        run_checked([
            sys.executable, "-m", "power_macro.tcn_detection.train.launch_parallel_training",
            "--jobs", "tcn_L8", "--windows-dir", str(windows_dir),
            "--label-dir", str(labels_dir), "--training-config", str(training_config),
            "--model-config", str(MODEL_CONFIG), "--output-dir", str(models_dir),
        ])

        validation_report = models_dir / "training_validation.json"
        run_checked([
            sys.executable, "-m", "power_macro.tcn_detection.train.validate_training",
            "--models-dir", str(models_dir), "--windows-dir", str(windows_dir),
            "--training-config", str(training_config), "--model-config", str(MODEL_CONFIG),
            "--jobs", "tcn_L8", "--output", str(validation_report),
        ])

        # Read every persisted surface independently.  These assertions ensure
        # a PASS cannot hide missing logs, test-split predictions, a corrupt
        # checkpoint, or a temporary file left by an interrupted atomic write.
        report = json.loads(validation_report.read_text(encoding="utf-8"))
        if report["status"] != "PASS" or report["failures"]:
            raise AssertionError("smoke artifact validator did not pass: {}".format(report))
        prediction_path = models_dir / "tcn_L8" / "validation_predictions.csv"
        with prediction_path.open(newline="", encoding="utf-8") as stream:
            predictions = list(csv.DictReader(stream))
        if len(predictions) != 6 or {row["split"] for row in predictions} != {"validation"}:
            raise AssertionError("smoke predictions are incomplete or expose a non-validation split")
        checkpoint_path = models_dir / "tcn_L8" / "best_checkpoint.pt"
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        if checkpoint.get("model") != "tcn" or checkpoint.get("window_length") != 8:
            raise AssertionError("smoke checkpoint metadata is inconsistent")
        summary = json.loads((models_dir / "tcn_L8" / "training_summary.json").read_text(encoding="utf-8"))
        expected_metric = "weighted_ovr_pr_auc" if args.v2 else "validation_macro_f1"
        if summary.get("checkpoint_selection_metric") != expected_metric:
            raise AssertionError("smoke summary selected checkpoint with the wrong metric")
        if list(models_dir.rglob("*.tmp")):
            raise AssertionError("smoke training left an unpublished temporary artifact")

        print(json.dumps({"status": "PASS", "prediction_count": len(predictions),
                          "validator_status": report["status"]}, sort_keys=True))


if __name__ == "__main__":
    main()
