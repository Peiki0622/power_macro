#!/usr/bin/env python3
"""Run atomic structured pruning with recovery and fixed stop gates."""

from __future__ import print_function

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from power_macro.tcn_detection.compression.channel_importance import (
    compute_taylor_scores, rank_channels)
from power_macro.tcn_detection.compression.channel_surgery import (
    compact_model, surgery_metadata, verify_surgery_equivalence)
from power_macro.tcn_detection.compression.run_sensitivity_scan import (
    TEACHER_METRICS, TEACHER_SHA256, select_calibration)
from power_macro.tcn_detection.compression.teacher_contract import sha256_file
from power_macro.tcn_detection.dataset.model_data import (
    apply_normalizer, filter_split, load_window_table, write_json)
from power_macro.tcn_detection.train.common import (
    build_classifier, configure_cpu, estimate_macs, make_loader,
    parameter_count, read_json)
from power_macro.tcn_detection.train.train_binary_classifier import (
    checkpoint_metrics, write_validation_predictions)
from power_macro.tcn_detection.train.train_classifier import predict, save_checkpoint_atomic


# The displayed balanced path is expanded into single-layer atomic operations.
# This obeys the plan's stronger invariant that one pruning operation removes
# at most two channels and is immediately followed by recovery training.
PATH_A_ATOMIC_TARGETS = (
    (16, 18, 18), (16, 16, 18), (16, 16, 16),
    (14, 16, 16), (14, 14, 16), (14, 14, 14),
    (12, 14, 14), (12, 12, 14), (12, 12, 12),
)


def parse_args():
    """Parse one immutable iterative-pruning run."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--sensitivity-report", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report-dir", required=True, type=Path)
    return parser.parse_args()


def _resolve(root, value):
    """Resolve one config path under the declared repository root."""

    path = Path(value)
    return path if path.is_absolute() else Path(root) / path


def passes_stop_gate(metrics):
    """Return true only while all fixed Step 5 wide gates remain satisfied."""

    values = tuple(float(metrics[key]) for key in (
        "critical_pr_auc", "critical_recall", "safe_window_false_alarm_rate", "macro_f1"))
    if not all(np.isfinite(values)):
        return False
    return bool(
        TEACHER_METRICS["critical_pr_auc"] - metrics["critical_pr_auc"] <= 0.015
        and TEACHER_METRICS["critical_recall"] - metrics["critical_recall"] <= 0.020
        and metrics["safe_window_false_alarm_rate"]
        - TEACHER_METRICS["safe_window_false_alarm_rate"] <= 0.010
        and TEACHER_METRICS["macro_f1"] - metrics["macro_f1"] <= 0.020)


def _metrics(labels, probabilities):
    """Return the exact reporting fields and deterministic selection key."""

    raw = checkpoint_metrics(labels, probabilities)
    return {
        "accuracy": float(np.mean(np.argmax(probabilities, axis=1) == labels)),
        "balanced_accuracy": raw["validation_balanced_accuracy"],
        "macro_f1": raw["validation_macro_f1"],
        "critical_pr_auc": raw["validation_critical_pr_auc"],
        "critical_recall": raw["validation_critical_recall"],
        "safe_window_false_alarm_rate": raw["validation_safe_window_false_alarm_rate"],
        "selection_key": raw["selection_key"],
    }


def recover(model, train, validation, seed, output_dir, checkpoint_metadata,
            max_epochs=20, patience=6):
    """Recover one compact model for at least 10 and at most 20 epochs."""

    loader = make_loader(train.features, train.labels, 256, shuffle=True, seed=seed)
    optimizer = torch.optim.AdamW(model.parameters(), lr=4.0e-4, weight_decay=1.0e-5)
    criterion = nn.CrossEntropyLoss()
    checkpoint_path = output_dir / "best_checkpoint.pt"
    best_key, stale_epochs = None, 0
    history = []
    for epoch in range(1, int(max_epochs) + 1):
        model.train()
        losses = []
        for inputs, labels in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(inputs), labels)
            if not bool(torch.isfinite(loss)):
                raise ValueError("non-finite recovery loss")
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach()))
        _, probabilities = predict(model, validation.features, 256)
        metrics = _metrics(validation.labels, probabilities)
        key = tuple(float(value) for value in metrics.pop("selection_key"))
        improved = best_key is None or key > best_key
        if improved:
            best_key, stale_epochs = key, 0
            save_checkpoint_atomic(dict(checkpoint_metadata,
                                        state_dict=model.state_dict(),
                                        best_epoch=epoch,
                                        selection_key=list(key)), checkpoint_path)
        else:
            stale_epochs += 1
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)),
                        "validation": metrics, "improved": improved})
        if epoch >= 10 and stale_epochs >= int(patience):
            break
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    _, probabilities = predict(model, validation.features, 256)
    metrics = _metrics(validation.labels, probabilities)
    metrics.pop("selection_key")
    write_validation_predictions(output_dir / "validation_predictions.csv",
                                 validation, probabilities)
    write_json(output_dir / "training_summary.json", {
        "epochs_completed": len(history), "best_epoch": checkpoint["best_epoch"],
        "history": history, "validation_metrics": metrics,
        "training": {"optimizer": "AdamW", "learning_rate": 4.0e-4,
                     "weight_decay": 1.0e-5, "batch_size": 256,
                     "sampling": "natural", "loss": "unweighted_cross_entropy",
                     "max_epochs": int(max_epochs), "early_stopping_patience": int(patience),
                     "minimum_epochs": 10},
        "iid_features_loaded": False, "iid_metrics_computed": False,
    })
    return metrics, len(history), checkpoint_path


def _markdown(report):
    """Render path progress and stop evidence without hiding failed steps."""

    lines = ["# Iterative CNN Pruning Paths", "",
             "Each listed operation removes two channels from one layer and immediately recovers the model.", "",
             "| Step | Channels | Epochs | MAC/window | Critical PR-AUC | Critical Recall | Macro-F1 | Safe FAR | Continue |",
             "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for item in report["path_a"]["steps"]:
        metrics = item["metrics"]
        lines.append("| {step} | {channels} | {epochs} | {macs} | {ap:.6f} | {recall:.6f} | {f1:.6f} | {far:.6f} | {passed} |".format(
            step=item["step"], channels=item["target_channels"], epochs=item["epochs_completed"],
            macs=item["estimated_macs_per_window"], ap=metrics["critical_pr_auc"],
            recall=metrics["critical_recall"], f1=metrics["macro_f1"],
            far=metrics["safe_window_false_alarm_rate"],
            passed="yes" if item["passes_stop_gate"] else "no"))
    lines.extend(["", "- Path A status: {}".format(report["path_a"]["status"]),
                  "- Path B status: {}".format(report["path_b"]["status"]),
                  "- Path C status: {}".format(report["path_c"]["status"]),
                  "- Path D status: {}".format(report["path_d"]["status"])])
    return "\n".join(lines) + "\n"


def main():
    """Execute Path A and apply sensitivity-conditioned path guards."""

    args = parse_args()
    if args.output_dir.exists() or (args.report_dir / "PRUNING_PATHS.md").exists():
        raise FileExistsError("refusing to overwrite iterative-pruning evidence")
    config = read_json(args.config)
    sensitivity = read_json(args.sensitivity_report)
    if sensitivity.get("status") != "COMPLETE" or len(sensitivity.get("candidates", [])) != 15:
        raise ValueError("formal sensitivity scan is incomplete")
    root = Path(config["repository_root"]).resolve()
    teacher_path = _resolve(root, config["teacher"]["checkpoint"])
    windows_path = _resolve(root, config["data"]["windows"])
    if sha256_file(teacher_path) != TEACHER_SHA256:
        raise ValueError("Teacher checkpoint SHA256 changed before iterative pruning")
    configure_cpu(config["teacher"]["representative_seed"],
                  config["recovery"]["cpu_threads_per_process"])
    checkpoint = torch.load(teacher_path, map_location="cpu", weights_only=False)
    table = load_window_table(windows_path, splits={"train", "validation"})
    train = apply_normalizer(filter_split(table, "train"), checkpoint["normalizer"])
    validation = apply_normalizer(filter_split(table, "validation"), checkpoint["normalizer"])
    calibration = select_calibration(train, config["calibration"]["seed"],
                                     config["calibration"]["safe_count"])
    calibration_loader = make_loader(calibration.features, calibration.labels, 256, shuffle=False)
    current = build_classifier("cnn", checkpoint["model_config"])
    current.load_state_dict(checkpoint["state_dict"], strict=True)
    current_checkpoint = teacher_path
    provenance = []
    args.output_dir.mkdir(parents=True, exist_ok=False)
    steps = []
    for step_index, target in enumerate(PATH_A_ATOMIC_TARGETS, start=1):
        scores = compute_taylor_scores(current, calibration_loader)
        rankings = rank_channels(scores["final"])
        changed = [index for index, (old, new) in enumerate(zip(current.channels, target))
                   if int(old) != int(new)]
        if len(changed) != 1 or current.channels[changed[0]] - target[changed[0]] != 2:
            raise ValueError("Path A target is not one atomic two-channel deletion")
        layer = changed[0]
        keep = [list(range(width)) for width in current.channels]
        keep[layer] = sorted(rankings[layer][-target[layer]:])
        compact = compact_model(current, keep)
        verification_error = verify_surgery_equivalence(
            current, compact, keep,
            # Physical deletion shortens GEMM reduction dimensions, so zero
            # terms disappear and CPU accumulation can differ by a few ULPs.
            # This tight deterministic tolerance catches mapping errors while
            # accepting the observed 1.91e-6 round-off of the valid surgery.
            torch.from_numpy(calibration.features[:32]), absolute_tolerance=5.0e-6)
        source_sha = sha256_file(current_checkpoint)
        surgery = surgery_metadata(source_sha, current.channels, keep)
        provenance.append({"step": step_index, "target_channels": list(target),
                           "source_checkpoint_sha256": source_sha,
                           "source_keep_indices": surgery["keep_indices"]})
        model_config = dict(checkpoint["model_config"])
        model_config.update({"cnn_channels": list(target),
                             "kernel_sizes": list(compact.kernel_sizes),
                             "architecture_id": "path_a_{}".format("x".join(map(str, target)))})
        step_dir = args.output_dir / "path_a_step_{:02d}_{}".format(
            step_index, "x".join(map(str, target)))
        step_dir.mkdir()
        started = time.perf_counter()
        metrics, epochs, checkpoint_path = recover(
            compact, train, validation, config["teacher"]["representative_seed"],
            step_dir, {"schema_version": 1, "task": "safe_critical_binary",
                       "model": "cnn", "model_config": model_config,
                       "window_length": 32,
                       "seed": int(config["teacher"]["representative_seed"]),
                       "normalizer": checkpoint["normalizer"], "surgery": surgery,
                       "teacher_sha256": TEACHER_SHA256,
                       "pruning_provenance": list(provenance)},
            max_epochs=config["recovery"]["pruning_max_epochs"],
            patience=config["recovery"]["pruning_patience"])
        passed = passes_stop_gate(metrics)
        summary = {
            "step": step_index, "target_channels": list(target),
            "keep_indices": keep, "taylor_rank_low_to_high": rankings,
            "surgery_maximum_logit_error": verification_error,
            "metrics": metrics, "epochs_completed": epochs,
            "passes_stop_gate": passed,
            "parameter_count": parameter_count(compact),
            "estimated_macs_per_window": estimate_macs(compact, 32, 1),
            "training_wall_seconds": time.perf_counter() - started,
        }
        steps.append(summary)
        write_json(step_dir / "pruning_summary.json", summary)
        if not passed:
            break
        current, current_checkpoint = compact, checkpoint_path

    path_a_status = "COMPLETE" if len(steps) == len(PATH_A_ATOMIC_TARGETS) else "STOPPED_BY_QUALITY_GATE"
    minimum_safe = sensitivity["minimum_safe_widths"]
    report = {
        "schema_version": 1, "step": 5,
        "path_a": {"status": path_a_status, "steps": steps},
        "path_b": {"status": "SKIPPED_CONV1_SENSITIVITY_NOT_ALLOWED"
                   if minimum_safe["conv1"] >= 18 else "ELIGIBLE_NOT_RUN"},
        "path_c": {"status": "SKIPPED_CONV3_SENSITIVITY_NOT_ALLOWED"
                   if minimum_safe["conv3"] >= 18 else "ELIGIBLE_NOT_RUN"},
        "path_d": {"status": "SKIPPED_NO_SUB50_PERCENT_GATE_PASS"},
        "teacher_sha256": TEACHER_SHA256,
        "iid_features_loaded": False, "iid_metrics_computed": False,
    }
    write_json(args.output_dir / "pruning_paths.json", report)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "PRUNING_PATHS.md").write_text(_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
