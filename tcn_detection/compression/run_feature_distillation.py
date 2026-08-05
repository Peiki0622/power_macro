#!/usr/bin/env python3
"""Run bounded Average/Maximum/Endpoint feature distillation."""

from __future__ import print_function

import argparse
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.compression.distillation import (
    STATISTIC_KEYS, StatisticProjectors, freeze_teacher,
    logit_distillation_loss, state_dict_sha256, statistic_distillation_losses)
from power_macro.tcn_detection.compression.run_distillation import strict_single_seed_gate
from power_macro.tcn_detection.compression.run_iterative_pruning import _metrics
from power_macro.tcn_detection.compression.run_sensitivity_scan import TEACHER_SHA256
from power_macro.tcn_detection.compression.teacher_contract import sha256_file
from power_macro.tcn_detection.dataset.model_data import (
    apply_normalizer, filter_split, load_window_table, write_json)
from power_macro.tcn_detection.train.common import (
    build_classifier, configure_cpu, make_loader, read_json)
from power_macro.tcn_detection.train.train_binary_classifier import write_validation_predictions
from power_macro.tcn_detection.train.train_classifier import predict, save_checkpoint_atomic


def parse_args():
    """Parse one immutable feature-KD run."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--distillation-report", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report-dir", required=True, type=Path)
    return parser.parse_args()


def _resolve(root, value):
    """Resolve a configuration path under its declared repository root."""

    path = Path(value)
    return path if path.is_absolute() else Path(root) / path


def _quality_key(metrics):
    """Apply the fixed AP/Recall/F1/FAR validation ordering."""

    return (float(metrics["critical_pr_auc"]), float(metrics["critical_recall"]),
            float(metrics["macro_f1"]),
            -float(metrics["safe_window_false_alarm_rate"]))


def train_feature_arm(student, teacher, train, validation, seed, output_dir,
                      temperature, alpha_ce, lambda_stat, metadata,
                      max_epochs=60, patience=15):
    """Train Student plus three projections, exporting Student weights only."""

    projectors = StatisticProjectors(student.channels[-1], teacher.channels[-1])
    optimizer = torch.optim.AdamW(
        list(student.parameters()) + list(projectors.parameters()),
        lr=4.0e-4, weight_decay=1.0e-5)
    loader = make_loader(train.features, train.labels, 256, shuffle=True, seed=seed)
    checkpoint_path = output_dir / "best_checkpoint.pt"
    best_key, stale_epochs = None, 0
    history = []
    teacher_before = state_dict_sha256(teacher)
    for epoch in range(1, int(max_epochs) + 1):
        student.train()
        projectors.train()
        sums = {"total": 0.0, "ce": 0.0, "kd": 0.0,
                "average_feature": 0.0, "maximum_feature": 0.0,
                "endpoint_feature": 0.0}
        sample_count = 0
        for inputs, labels in loader:
            optimizer.zero_grad(set_to_none=True)
            with torch.no_grad():
                teacher_outputs = teacher(inputs, return_intermediates=True)
            student_outputs = student(inputs, return_intermediates=True)
            logit_losses = logit_distillation_loss(
                student_outputs["logits"], labels, teacher_outputs["logits"],
                temperature=temperature, alpha_ce=alpha_ce)
            stat_losses = statistic_distillation_losses(
                student_outputs, teacher_outputs, projectors)
            total = logit_losses["total"] + float(lambda_stat) * stat_losses["total"]
            total.backward()
            optimizer.step()
            count = int(labels.shape[0])
            sample_count += count
            sums["total"] += float(total.detach()) * count
            sums["ce"] += float(logit_losses["ce"].detach()) * count
            sums["kd"] += float(logit_losses["kd"].detach()) * count
            for key in STATISTIC_KEYS:
                sums[key] += float(stat_losses[key].detach()) * count
        _, probabilities = predict(student, validation.features, 256)
        metrics = _metrics(validation.labels, probabilities)
        key = tuple(float(value) for value in metrics.pop("selection_key"))
        improved = best_key is None or key > best_key
        if improved:
            best_key, stale_epochs = key, 0
            # Only Student deployment tensors are persisted.  Projectors are
            # training aids and are intentionally absent from this checkpoint.
            save_checkpoint_atomic(dict(
                metadata, state_dict=student.state_dict(), best_epoch=epoch,
                selection_key=list(key), lambda_stat=float(lambda_stat),
                train_only_projection=True), checkpoint_path)
        else:
            stale_epochs += 1
        history.append({"epoch": epoch, "loss_total": sums["total"] / sample_count,
                        "loss_ce": sums["ce"] / sample_count,
                        "loss_kd": sums["kd"] / sample_count,
                        "loss_average": sums["average_feature"] / sample_count,
                        "loss_maximum": sums["maximum_feature"] / sample_count,
                        "loss_endpoint": sums["endpoint_feature"] / sample_count,
                        "validation": metrics, "improved": improved})
        if stale_epochs >= int(patience):
            break
    if state_dict_sha256(teacher) != teacher_before:
        raise ValueError("Teacher changed during feature distillation")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if set(checkpoint["state_dict"]) != set(student.state_dict()) or any(
            "projection" in key for key in checkpoint["state_dict"]):
        raise ValueError("train-only projections leaked into deployment state")
    student.load_state_dict(checkpoint["state_dict"], strict=True)
    _, probabilities = predict(student, validation.features, 256)
    metrics = _metrics(validation.labels, probabilities)
    metrics.pop("selection_key")
    write_validation_predictions(output_dir / "validation_predictions.csv",
                                 validation, probabilities)
    summary = {
        "lambda_stat": float(lambda_stat), "temperature": float(temperature),
        "alpha_ce": float(alpha_ce), "epochs_completed": len(history),
        "best_epoch": checkpoint["best_epoch"], "history": history,
        "validation_metrics": metrics,
        "strict_single_seed_gate": strict_single_seed_gate(metrics),
        "statistic_branches": list(STATISTIC_KEYS),
        "train_only_projection": True,
        "projection_in_deployment_state_dict": False,
        "teacher_state_unchanged": True,
        "iid_features_loaded": False, "iid_metrics_computed": False,
    }
    write_json(output_dir / "feature_distillation_summary.json", summary)
    return summary, checkpoint_path


def _markdown(report):
    """Render feature-KD arms and explicit fallback decision."""

    lines = ["# Multistat Feature Distillation", "",
             "Average, Maximum, and Endpoint were aligned with independent train-only projections.", "",
             "| lambda stat | Epochs | Critical PR-AUC | Critical Recall | Macro-F1 | Safe FAR | Strict gate |",
             "| ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for arm in report["arms"]:
        metrics = arm["validation_metrics"]
        lines.append("| {value:g} | {epochs} | {ap:.6f} | {recall:.6f} | {f1:.6f} | {far:.6f} | {gate} |".format(
            value=arm["lambda_stat"], epochs=arm["epochs_completed"],
            ap=metrics["critical_pr_auc"], recall=metrics["critical_recall"],
            f1=metrics["macro_f1"], far=metrics["safe_window_false_alarm_rate"],
            gate="pass" if arm["strict_single_seed_gate"] else "fail"))
    lines.extend(["", "- Selection: {}".format(report["selection"])])
    return "\n".join(lines) + "\n"


def main():
    """Run up to three lambda values on the best low-MAC logit-KD Student."""

    args = parse_args()
    if args.output_dir.exists() or (args.report_dir / "FEATURE_DISTILLATION.md").exists():
        raise FileExistsError("refusing to overwrite feature-distillation evidence")
    config, distillation = read_json(args.config), read_json(args.distillation_report)
    # Select the lowest-MAC Student after Step 6, matching the compression goal.
    source_student = min(distillation["students"],
                         key=lambda item: item["estimated_macs_per_window"])
    source_path = Path(source_student["selected_checkpoint"])
    source = torch.load(source_path, map_location="cpu", weights_only=False)
    selected_arm = next(arm for arm in source_student["arms"]
                        if arm["checkpoint"] == source_student["selected_checkpoint"])
    baseline_metrics = selected_arm["validation_metrics"]
    root = Path(config["repository_root"]).resolve()
    teacher_path = _resolve(root, config["teacher"]["checkpoint"])
    windows_path = _resolve(root, config["data"]["windows"])
    if sha256_file(teacher_path) != TEACHER_SHA256:
        raise ValueError("Teacher checkpoint SHA256 changed before feature KD")
    configure_cpu(config["teacher"]["representative_seed"],
                  config["recovery"]["cpu_threads_per_process"])
    teacher_checkpoint = torch.load(teacher_path, map_location="cpu", weights_only=False)
    teacher = freeze_teacher(build_classifier("cnn", teacher_checkpoint["model_config"]))
    teacher.load_state_dict(teacher_checkpoint["state_dict"], strict=True)
    table = load_window_table(windows_path, splits={"train", "validation"})
    train = apply_normalizer(filter_split(table, "train"), teacher_checkpoint["normalizer"])
    validation = apply_normalizer(filter_split(table, "validation"), teacher_checkpoint["normalizer"])
    args.output_dir.mkdir(parents=True, exist_ok=False)
    arms = []
    for lambda_stat in (0.1, 0.2, 0.3):
        student = build_classifier("cnn", source["model_config"])
        student.load_state_dict(source["state_dict"], strict=True)
        arm_dir = args.output_dir / "lambda_{}".format(str(lambda_stat).replace(".", "p"))
        arm_dir.mkdir()
        summary, checkpoint_path = train_feature_arm(
            student, teacher, train, validation,
            config["teacher"]["representative_seed"], arm_dir,
            selected_arm["temperature"], selected_arm["alpha_ce"], lambda_stat,
            {"schema_version": 1, "task": "safe_critical_binary", "model": "cnn",
             "model_config": source["model_config"], "window_length": 32,
             "seed": int(config["teacher"]["representative_seed"]),
             "normalizer": teacher_checkpoint["normalizer"],
             "teacher_sha256": TEACHER_SHA256,
             "source_logit_kd_sha256": sha256_file(source_path)},
            max_epochs=config["recovery"]["distillation_max_epochs"],
            patience=config["recovery"]["distillation_patience"])
        summary["checkpoint"] = str(checkpoint_path)
        arms.append(summary)
        if summary["strict_single_seed_gate"]:
            break
    best_feature = max(arms, key=lambda arm: _quality_key(arm["validation_metrics"]))
    improved = _quality_key(best_feature["validation_metrics"]) > _quality_key(baseline_metrics)
    report = {
        "schema_version": 1, "step": 7,
        "source_student": source_student["student_id"],
        "source_logit_kd_checkpoint": str(source_path),
        "baseline_logit_kd_metrics": baseline_metrics, "arms": arms,
        "selection": "feature_kd" if improved else "fallback_logit_kd",
        "selected_checkpoint": (best_feature["checkpoint"] if improved else str(source_path)),
        "iid_features_loaded": False, "iid_metrics_computed": False,
    }
    write_json(args.output_dir / "feature_distillation_report.json", report)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "FEATURE_DISTILLATION.md").write_text(
        _markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
