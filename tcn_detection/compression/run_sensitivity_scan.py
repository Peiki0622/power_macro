#!/usr/bin/env python3
"""Run the formal one-layer-at-a-time CNN sensitivity scan.

This entry point is intentionally narrow: it accepts the frozen compression
configuration, loads only train/validation rows, ranks channels once on the
fixed train calibration subset, and runs the 15 predeclared five-epoch
candidates.  Validation selects checkpoints but never contributes gradients.
"""

from __future__ import print_function

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from power_macro.tcn_detection.compression.channel_importance import (
    compute_conv3_statistic_audit, compute_taylor_scores, filter_norm_scores,
    rank_channels)
from power_macro.tcn_detection.compression.channel_surgery import (
    compact_model, surgery_metadata)
from power_macro.tcn_detection.compression.teacher_contract import sha256_file
from power_macro.tcn_detection.dataset.model_data import (
    WindowTable, apply_normalizer, filter_split, load_window_table, write_json)
from power_macro.tcn_detection.train.common import (
    configure_cpu, estimate_macs, make_loader, parameter_count, read_json)
from power_macro.tcn_detection.train.train_binary_classifier import checkpoint_metrics
from power_macro.tcn_detection.train.train_classifier import predict, save_checkpoint_atomic


TEACHER_SHA256 = "b6741281203fc4593b6434df584ace44cffa5daed23ece8745d1b14215a64814"
TEACHER_METRICS = {
    "accuracy": 0.9872512437810945,
    "balanced_accuracy": 0.986778355191051,
    "macro_f1": 0.9510605963616082,
    "critical_pr_auc": 0.9003906868709534,
    "critical_recall": 0.9862353750860289,
    "safe_window_false_alarm_rate": 0.012678664703927062,
}


def parse_args():
    """Parse one immutable sensitivity run."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report-dir", required=True, type=Path)
    return parser.parse_args()


def _resolve(root, value):
    """Resolve a configuration path against its declared repository root."""

    path = Path(value)
    return path if path.is_absolute() else Path(root) / path


def select_calibration(train, seed, per_class_count):
    """Select a deterministic balanced subset using only train metadata.

    Sorting ``sha256(seed:window_id)`` avoids dependence on CSV row order while
    retaining stable, auditable window identities.  Any non-train row fails
    before feature tensors are returned.
    """

    if any(row.get("split") != "train" for row in train.metadata):
        raise ValueError("calibration selection accepts train rows only")
    selected = []
    for class_id in (0, 1):
        candidates = [index for index, label in enumerate(train.labels)
                      if int(label) == class_id]
        if len(candidates) < int(per_class_count):
            raise ValueError("insufficient class {} calibration windows".format(class_id))
        candidates.sort(key=lambda index: (
            hashlib.sha256("{}:{}".format(seed, train.metadata[index]["window_id"])
                           .encode("utf-8")).hexdigest(),
            train.metadata[index]["window_id"]))
        selected.extend(candidates[:int(per_class_count)])
    selected.sort(key=lambda index: train.metadata[index]["window_id"])
    indices = np.asarray(selected, dtype=np.int64)
    return WindowTable(train.features[indices], train.labels[indices],
                       tuple(train.metadata[index] for index in indices), train.length)


def _jsonable_scores(scores):
    """Convert NumPy score arrays into stable JSON lists."""

    result = {}
    for key, value in scores.items():
        if isinstance(value, list):
            result[key] = [np.asarray(item, dtype=np.float64).tolist() for item in value]
        else:
            result[key] = value
    return result


def _candidate_metrics(labels, probabilities):
    """Translate the shared checkpoint metrics into report field names."""

    raw = checkpoint_metrics(labels, probabilities)
    selection_key = raw.pop("selection_key")
    return {
        "accuracy": float(np.mean(np.argmax(probabilities, axis=1) == labels)),
        "balanced_accuracy": raw["validation_balanced_accuracy"],
        "macro_f1": raw["validation_macro_f1"],
        "critical_pr_auc": raw["validation_critical_pr_auc"],
        "critical_recall": raw["validation_critical_recall"],
        "safe_window_false_alarm_rate": raw["validation_safe_window_false_alarm_rate"],
        "selection_key": selection_key,
    }


def _safe(metrics):
    """Apply the four fixed Step 4 short-recovery quality gates."""

    return bool(
        TEACHER_METRICS["critical_pr_auc"] - metrics["critical_pr_auc"] <= 0.010
        and TEACHER_METRICS["critical_recall"] - metrics["critical_recall"] <= 0.010
        and metrics["safe_window_false_alarm_rate"]
        - TEACHER_METRICS["safe_window_false_alarm_rate"] <= 0.005
        and TEACHER_METRICS["macro_f1"] - metrics["macro_f1"] <= 0.010)


def train_candidate(model, train, validation, seed, output_dir, metadata):
    """Recover one inherited compact model for exactly five natural-CE epochs."""

    loader = make_loader(train.features, train.labels, 256, shuffle=True, seed=seed)
    optimizer = torch.optim.AdamW(model.parameters(), lr=4.0e-4, weight_decay=1.0e-5)
    criterion = nn.CrossEntropyLoss()
    checkpoint_path = output_dir / "best_checkpoint.pt"
    best_key = None
    history = []
    for epoch in range(1, 6):
        model.train()
        losses = []
        for inputs, labels in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(inputs), labels)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach()))
        _, probabilities = predict(model, validation.features, 256)
        metrics = _candidate_metrics(validation.labels, probabilities)
        selection_key = tuple(float(value) for value in metrics.pop("selection_key"))
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)),
                        "validation": metrics})
        if best_key is None or selection_key > best_key:
            best_key = selection_key
            save_checkpoint_atomic({
                "schema_version": 1,
                "task": "safe_critical_binary",
                "model": "cnn",
                "model_config": metadata["model_config"],
                "window_length": 32,
                "seed": int(seed),
                "normalizer": metadata["normalizer"],
                "state_dict": model.state_dict(),
                "best_epoch": epoch,
                "selection_key": list(selection_key),
                "surgery": metadata["surgery"],
            }, checkpoint_path)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    _, probabilities = predict(model, validation.features, 256)
    metrics = _candidate_metrics(validation.labels, probabilities)
    metrics.pop("selection_key")
    write_json(output_dir / "training_summary.json", {
        "epochs_completed": 5, "history": history,
        "best_epoch": checkpoint["best_epoch"], "validation_metrics": metrics,
        "training": {"optimizer": "AdamW", "learning_rate": 4.0e-4,
                     "weight_decay": 1.0e-5, "batch_size": 256,
                     "sampling": "natural", "loss": "unweighted_cross_entropy"},
        "iid_features_loaded": False, "iid_metrics_computed": False,
    })
    return metrics


def _markdown(report):
    """Render the compact sensitivity evidence table."""

    lines = ["# CNN Layer Sensitivity", "",
             "Selection used only train/validation; IID/OOD features and metrics were not loaded.", "",
             "| Layer | Channels | MAC/window | Critical PR-AUC | Critical Recall | Macro-F1 | Safe FAR | Safe width gate |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for candidate in report["candidates"]:
        metrics = candidate["metrics"]
        lines.append("| {layer} | {width} | {macs} | {ap:.6f} | {recall:.6f} | {f1:.6f} | {far:.6f} | {safe} |".format(
            layer=candidate["layer"], width=candidate["target_width"],
            macs=candidate["estimated_macs_per_window"],
            ap=metrics["critical_pr_auc"], recall=metrics["critical_recall"],
            f1=metrics["macro_f1"], far=metrics["safe_window_false_alarm_rate"],
            safe="pass" if candidate["safe_width_gate"] else "fail"))
    lines.extend(["", "## Minimum Safe Widths", ""])
    for layer, width in report["minimum_safe_widths"].items():
        lines.append("- {}: {}".format(layer, width if width is not None else "none"))
    return "\n".join(lines) + "\n"


def main():
    """Execute all 15 predeclared candidates and publish immutable evidence."""

    args = parse_args()
    if args.output_dir.exists() or (args.report_dir / "LAYER_SENSITIVITY.md").exists():
        raise FileExistsError("refusing to overwrite sensitivity evidence")
    config = read_json(args.config)
    root = Path(config["repository_root"]).resolve()
    teacher_path = _resolve(root, config["teacher"]["checkpoint"])
    windows_path = _resolve(root, config["data"]["windows"])
    if sha256_file(teacher_path) != TEACHER_SHA256:
        raise ValueError("Teacher checkpoint SHA256 changed before sensitivity scan")
    configure_cpu(config["teacher"]["representative_seed"],
                  config["recovery"]["cpu_threads_per_process"])
    table = load_window_table(windows_path, splits={"train", "validation"})
    train_raw, validation_raw = filter_split(table, "train"), filter_split(table, "validation")
    checkpoint = torch.load(teacher_path, map_location="cpu", weights_only=False)
    train = apply_normalizer(train_raw, checkpoint["normalizer"])
    validation = apply_normalizer(validation_raw, checkpoint["normalizer"])
    from power_macro.tcn_detection.train.common import build_classifier
    teacher = build_classifier("cnn", checkpoint["model_config"])
    teacher.load_state_dict(checkpoint["state_dict"], strict=True)
    teacher.eval()

    calibration = select_calibration(
        train, config["calibration"]["seed"], config["calibration"]["safe_count"])
    calibration_loader = make_loader(calibration.features, calibration.labels, 256, shuffle=False)
    taylor = compute_taylor_scores(teacher, calibration_loader)
    rankings = rank_channels(taylor["final"])
    importance = {
        "calibration_seed": config["calibration"]["seed"],
        "window_ids": [row["window_id"] for row in calibration.metadata],
        "window_id_sha256": hashlib.sha256("\n".join(
            row["window_id"] for row in calibration.metadata).encode("utf-8")).hexdigest(),
        "split": "train", "class_counts": taylor["sample_counts"],
        "taylor": _jsonable_scores(taylor),
        "rank_low_to_high": rankings,
        "filter_norms": _jsonable_scores(filter_norm_scores(teacher)),
        "conv3_statistic_audit": {
            class_id: {key: values.tolist() for key, values in branch.items()}
            for class_id, branch in compute_conv3_statistic_audit(
                teacher, calibration_loader).items()},
        "iid_features_loaded": False, "iid_metrics_computed": False,
    }

    args.output_dir.mkdir(parents=True, exist_ok=False)
    write_json(args.output_dir / "channel_importance.json", importance)
    candidates = []
    seed = int(config["teacher"]["representative_seed"])
    for layer_index, layer_name in enumerate(("conv1", "conv2", "conv3")):
        for target_width in (16, 14, 12, 10, 8):
            candidate_id = "{}_w{}".format(layer_name, target_width)
            candidate_dir = args.output_dir / candidate_id
            candidate_dir.mkdir()
            keep = [list(range(18)) for _ in range(3)]
            keep[layer_index] = sorted(rankings[layer_index][-target_width:])
            model = compact_model(teacher, keep)
            model_config = dict(checkpoint["model_config"])
            model_config["cnn_channels"] = list(model.channels)
            model_config["kernel_sizes"] = list(model.kernel_sizes)
            model_config["architecture_id"] = "sensitivity_{}".format(candidate_id)
            surgery = surgery_metadata(TEACHER_SHA256, [18, 18, 18], keep)
            started = time.perf_counter()
            metrics = train_candidate(model, train, validation, seed, candidate_dir, {
                "model_config": model_config, "normalizer": checkpoint["normalizer"],
                "surgery": surgery})
            deltas = {key: metrics[key] - TEACHER_METRICS[key]
                      for key in TEACHER_METRICS}
            candidate = {
                "candidate_id": candidate_id, "layer": layer_name,
                "target_width": target_width, "channels": list(model.channels),
                "keep_indices": keep, "metrics": metrics, "teacher_deltas": deltas,
                "safe_width_gate": _safe(metrics),
                "parameter_count": parameter_count(model),
                "estimated_macs_per_window": estimate_macs(model, 32, 1),
                "training_wall_seconds": time.perf_counter() - started,
            }
            candidates.append(candidate)
            write_json(candidate_dir / "candidate_summary.json", candidate)

    minimum_safe = {}
    for layer_name in ("conv1", "conv2", "conv3"):
        # Widths are scanned from 16 downward.  Freeze at the last consecutive
        # passing width when a narrower candidate first crosses a quality gate.
        last_safe = 18
        for candidate in [value for value in candidates if value["layer"] == layer_name]:
            if not candidate["safe_width_gate"]:
                break
            last_safe = candidate["target_width"]
        minimum_safe[layer_name] = last_safe
    report = {
        "schema_version": 1, "step": 4, "status": "COMPLETE",
        "teacher_sha256": TEACHER_SHA256, "teacher_metrics": TEACHER_METRICS,
        "candidates": candidates, "minimum_safe_widths": minimum_safe,
        "windows_sha256": sha256_file(windows_path),
        "iid_features_loaded": False, "iid_metrics_computed": False,
    }
    write_json(args.output_dir / "sensitivity_report.json", report)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "LAYER_SENSITIVITY.md").write_text(
        _markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
