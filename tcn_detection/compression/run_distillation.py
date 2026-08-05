#!/usr/bin/env python3
"""Run bounded validation-only logit KD for Step 5 Pareto students."""

from __future__ import print_function

import argparse
import time
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.compression.distillation import (
    freeze_teacher, logit_distillation_loss, state_dict_sha256)
from power_macro.tcn_detection.compression.run_iterative_pruning import _metrics
from power_macro.tcn_detection.compression.run_sensitivity_scan import (
    TEACHER_METRICS, TEACHER_SHA256)
from power_macro.tcn_detection.compression.teacher_contract import sha256_file
from power_macro.tcn_detection.dataset.model_data import (
    apply_normalizer, filter_split, load_window_table, write_json)
from power_macro.tcn_detection.train.common import (
    build_classifier, configure_cpu, estimate_macs, make_loader,
    parameter_count, read_json)
from power_macro.tcn_detection.train.train_binary_classifier import write_validation_predictions
from power_macro.tcn_detection.train.train_classifier import predict, save_checkpoint_atomic


def parse_args():
    """Parse one immutable bounded KD run."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--pruning-report", required=True, type=Path)
    parser.add_argument("--pruning-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report-dir", required=True, type=Path)
    return parser.parse_args()


def _resolve(root, value):
    """Resolve one configuration path under its repository root."""

    path = Path(value)
    return path if path.is_absolute() else Path(root) / path


def strict_single_seed_gate(metrics):
    """Apply final quality deltas to the representative validation seed."""

    return bool(
        metrics["critical_pr_auc"] >= TEACHER_METRICS["critical_pr_auc"] - 0.005
        and metrics["critical_recall"] >= TEACHER_METRICS["critical_recall"] - 0.010
        and metrics["macro_f1"] >= TEACHER_METRICS["macro_f1"] - 0.005
        and metrics["balanced_accuracy"] >= TEACHER_METRICS["balanced_accuracy"] - 0.010
        and metrics["safe_window_false_alarm_rate"]
        <= TEACHER_METRICS["safe_window_false_alarm_rate"] + 0.003)


def train_kd_arm(student, teacher, train, validation, seed, output_dir,
                 temperature, alpha_ce, metadata, max_epochs=60, patience=15):
    """Train one bounded online-KD arm and preserve its best validation epoch."""

    loader = make_loader(train.features, train.labels, 256, shuffle=True, seed=seed)
    optimizer = torch.optim.AdamW(student.parameters(), lr=4.0e-4, weight_decay=1.0e-5)
    checkpoint_path = output_dir / "best_checkpoint.pt"
    best_key, stale_epochs = None, 0
    history = []
    teacher_before = state_dict_sha256(teacher)
    for epoch in range(1, int(max_epochs) + 1):
        student.train()
        sums = {"total": 0.0, "ce": 0.0, "kd": 0.0}
        sample_count = 0
        for inputs, labels in loader:
            optimizer.zero_grad(set_to_none=True)
            with torch.no_grad():
                teacher_logits = teacher(inputs)
            losses = logit_distillation_loss(
                student(inputs), labels, teacher_logits,
                temperature=temperature, alpha_ce=alpha_ce)
            losses["total"].backward()
            optimizer.step()
            count = int(labels.shape[0])
            sample_count += count
            for key in sums:
                sums[key] += float(losses[key].detach()) * count
        _, probabilities = predict(student, validation.features, 256)
        metrics = _metrics(validation.labels, probabilities)
        key = tuple(float(value) for value in metrics.pop("selection_key"))
        improved = best_key is None or key > best_key
        if improved:
            best_key, stale_epochs = key, 0
            save_checkpoint_atomic(dict(
                metadata, state_dict=student.state_dict(), best_epoch=epoch,
                selection_key=list(key), temperature=float(temperature),
                alpha_ce=float(alpha_ce)), checkpoint_path)
        else:
            stale_epochs += 1
        history.append({"epoch": epoch,
                        "loss_total": sums["total"] / sample_count,
                        "loss_ce": sums["ce"] / sample_count,
                        "loss_kd": sums["kd"] / sample_count,
                        "validation": metrics, "improved": improved})
        if stale_epochs >= int(patience):
            break
    teacher_after = state_dict_sha256(teacher)
    if teacher_before != teacher_after or any(parameter.grad is not None
                                              for parameter in teacher.parameters()):
        raise ValueError("Teacher changed during distillation")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    student.load_state_dict(checkpoint["state_dict"], strict=True)
    _, probabilities = predict(student, validation.features, 256)
    metrics = _metrics(validation.labels, probabilities)
    metrics.pop("selection_key")
    write_validation_predictions(output_dir / "validation_predictions.csv",
                                 validation, probabilities)
    summary = {
        "temperature": float(temperature), "alpha_ce": float(alpha_ce),
        "epochs_completed": len(history), "best_epoch": checkpoint["best_epoch"],
        "history": history, "validation_metrics": metrics,
        "strict_single_seed_gate": strict_single_seed_gate(metrics),
        "teacher_state_sha256_before": teacher_before,
        "teacher_state_sha256_after": teacher_after,
        "teacher_requires_grad": False, "teacher_mode": "eval",
        "iid_features_loaded": False, "iid_metrics_computed": False,
    }
    write_json(output_dir / "distillation_summary.json", summary)
    return summary, checkpoint_path


def _markdown(report):
    """Render the bounded KD search and selected arm per Student."""

    lines = ["# CNN Distillation Ablation", "",
             "Teacher remained frozen at the authoritative SHA256; only train/validation were loaded.", "",
             "| Student | T | alpha CE | Epochs | Critical PR-AUC | Critical Recall | Macro-F1 | Safe FAR | Strict gate |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for student in report["students"]:
        for arm in student["arms"]:
            metrics = arm["validation_metrics"]
            lines.append("| {student} | {temperature:g} | {alpha:g} | {epochs} | {ap:.6f} | {recall:.6f} | {f1:.6f} | {far:.6f} | {gate} |".format(
                student=student["student_id"], temperature=arm["temperature"],
                alpha=arm["alpha_ce"], epochs=arm["epochs_completed"],
                ap=metrics["critical_pr_auc"], recall=metrics["critical_recall"],
                f1=metrics["macro_f1"], far=metrics["safe_window_false_alarm_rate"],
                gate="pass" if arm["strict_single_seed_gate"] else "fail"))
    return "\n".join(lines) + "\n"


def main():
    """Distill no more than the two observed Step 5 Pareto students."""

    args = parse_args()
    if args.output_dir.exists() or (args.report_dir / "DISTILLATION_ABLATION.md").exists():
        raise FileExistsError("refusing to overwrite distillation evidence")
    config = read_json(args.config)
    pruning = read_json(args.pruning_report)
    steps = pruning.get("path_a", {}).get("steps", [])
    if not steps or len(steps) > 3:
        raise ValueError("Step 5 did not provide one to three Pareto students")
    root = Path(config["repository_root"]).resolve()
    teacher_path = _resolve(root, config["teacher"]["checkpoint"])
    windows_path = _resolve(root, config["data"]["windows"])
    if sha256_file(teacher_path) != TEACHER_SHA256:
        raise ValueError("Teacher checkpoint SHA256 changed before KD")
    configure_cpu(config["teacher"]["representative_seed"],
                  config["recovery"]["cpu_threads_per_process"])
    teacher_checkpoint = torch.load(teacher_path, map_location="cpu", weights_only=False)
    teacher = freeze_teacher(build_classifier("cnn", teacher_checkpoint["model_config"]))
    teacher.load_state_dict(teacher_checkpoint["state_dict"], strict=True)
    table = load_window_table(windows_path, splits={"train", "validation"})
    train = apply_normalizer(filter_split(table, "train"), teacher_checkpoint["normalizer"])
    validation = apply_normalizer(filter_split(table, "validation"), teacher_checkpoint["normalizer"])
    args.output_dir.mkdir(parents=True, exist_ok=False)
    student_reports = []
    combinations = ((4.0, 0.5), (2.0, 0.5), (2.0, 0.7), (4.0, 0.7))
    for step in steps:
        student_id = "path_a_step_{:02d}_{}".format(
            step["step"], "x".join(map(str, step["target_channels"])))
        source_path = args.pruning_dir / student_id / "best_checkpoint.pt"
        source = torch.load(source_path, map_location="cpu", weights_only=False)
        arms = []
        selected_path = None
        for arm_index, (temperature, alpha_ce) in enumerate(combinations):
            # The first fixed arm is mandatory.  Remaining combinations run
            # only if it did not recover the strict representative-seed gate.
            if arm_index > 0 and arms[0]["strict_single_seed_gate"]:
                break
            student = build_classifier("cnn", source["model_config"])
            student.load_state_dict(source["state_dict"], strict=True)
            arm_id = "t{}_a{}".format(int(temperature), str(alpha_ce).replace(".", "p"))
            arm_dir = args.output_dir / student_id / arm_id
            arm_dir.mkdir(parents=True)
            started = time.perf_counter()
            summary, checkpoint_path = train_kd_arm(
                student, teacher, train, validation,
                config["teacher"]["representative_seed"], arm_dir,
                temperature, alpha_ce,
                {"schema_version": 1, "task": "safe_critical_binary",
                 "model": "cnn", "model_config": source["model_config"],
                 "window_length": 32,
                 "seed": int(config["teacher"]["representative_seed"]),
                 "normalizer": teacher_checkpoint["normalizer"],
                 "teacher_sha256": TEACHER_SHA256,
                 "source_student_sha256": sha256_file(source_path)},
                max_epochs=config["recovery"]["distillation_max_epochs"],
                patience=config["recovery"]["distillation_patience"])
            summary["training_wall_seconds"] = time.perf_counter() - started
            summary["checkpoint"] = str(checkpoint_path)
            arms.append(summary)
        selected = max(arms, key=lambda arm: (
            arm["validation_metrics"]["critical_pr_auc"],
            arm["validation_metrics"]["critical_recall"],
            arm["validation_metrics"]["macro_f1"],
            -arm["validation_metrics"]["safe_window_false_alarm_rate"]))
        selected_path = selected["checkpoint"]
        student_reports.append({
            "student_id": student_id, "source_checkpoint": str(source_path),
            "channels": step["target_channels"],
            "parameter_count": step["parameter_count"],
            "estimated_macs_per_window": step["estimated_macs_per_window"],
            "arms": arms, "selected_checkpoint": selected_path,
            "selected_temperature": selected["temperature"],
            "selected_alpha_ce": selected["alpha_ce"],
        })
    report = {"schema_version": 1, "step": 6, "students": student_reports,
              "teacher_sha256": TEACHER_SHA256,
              "iid_features_loaded": False, "iid_metrics_computed": False}
    write_json(args.output_dir / "distillation_report.json", report)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "DISTILLATION_ABLATION.md").write_text(
        _markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
