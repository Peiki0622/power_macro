#!/usr/bin/env python3
"""Freeze and audit the authoritative CNN compression inputs.

This module is the only Step 0 entry point.  It hashes every executable input
before deserializing the Teacher, loads only the requested development split,
and publishes a self-contained contract plus human-readable baseline audit.
The strict ordering is deliberate: a substituted checkpoint or window file
must fail before PyTorch or the data loader can observe its contents.
"""

from __future__ import print_function

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.dataset.model_data import (
    apply_normalizer, load_window_table)
from power_macro.tcn_detection.evaluate.binary_metrics import binary_window_metrics
from power_macro.tcn_detection.train.common import (
    build_classifier, configure_cpu, estimate_macs, parameter_count)
from power_macro.tcn_detection.train.train_classifier import predict


EXPECTED_CHECKPOINT = (
    "b6741281203fc4593b6434df584ace44cffa5daed23ece8745d1b14215a64814")
EXPECTED_THREE_SEED = {
    "median_accuracy": 0.987873,
    "median_balanced_accuracy": 0.981712,
    "median_macro_f1": 0.952356,
    "median_critical_pr_auc": 0.900391,
    "worst_seed_critical_recall": 0.964212,
    "median_safe_far": 0.011112,
}
EXPECTED_REPRESENTATIVE = {
    "accuracy": 0.9872512437810945,
    "balanced_accuracy": 0.986778355191051,
    "macro_f1": 0.9510605963616082,
    "critical_pr_auc": 0.9003906868709534,
    "critical_recall": 0.9862353750860289,
    "safe_window_false_alarm_rate": 0.012678664703927062,
}


def sha256_file(path):
    """Hash one file with bounded memory so large CSVs remain streamable."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Read a JSON object and reject accidental scalar/array contracts."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return payload


def utc_now():
    """Return an explicit UTC timestamp for run evidence."""

    return datetime.now(timezone.utc).isoformat()


def source_commit(repository_root):
    """Resolve the owning repository commit, failing closed on Git errors."""

    try:
        return subprocess.check_output(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
            text=True).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("cannot resolve source commit: {}".format(error))


def _resolve(root, value):
    """Resolve a config-relative path without silently using another root."""

    path = Path(value)
    return path if path.is_absolute() else Path(root) / path


def _close(value, expected, tolerance=2.0e-6):
    """Compare floating report values with a deterministic print tolerance."""

    return abs(float(value) - float(expected)) <= float(tolerance)


def _report_metrics(final_training):
    """Extract the frozen three-seed aggregate from the reviewed report."""

    selected = final_training.get("selected_training", {})
    return {
        "median_accuracy": float(selected["median_accuracy"]),
        "median_balanced_accuracy": float(selected["median_balanced_accuracy"]),
        "median_macro_f1": float(selected["median_macro_f1"]),
        "median_critical_pr_auc": float(selected["median_critical_pr_auc"]),
        "worst_seed_critical_recall": float(
            selected["worst_critical_recall"]),
        "median_safe_far": float(selected["median_safe_far"]),
    }


def _verify_configuration(config, model_config, fixed_config, checkpoint):
    """Check architecture, task, and the immutable Teacher metadata."""

    teacher = config["teacher"]
    if (teacher["checkpoint_sha256"] != EXPECTED_CHECKPOINT
            or teacher["representative_seed"] != 20260727
            or teacher["channels"] != [18, 18, 18]
            or teacher["kernel_sizes"] != [5, 5, 5]
            or teacher["pooling_contract"]
            != "multistat_average_max_endpoint"):
        raise ValueError("compression config does not identify the frozen Teacher")
    if (model_config.get("architecture_id") != "multistat_w18_k5"
            or model_config.get("cnn_channels") != [18, 18, 18]
            or model_config.get("kernel_size") != 5
            or model_config.get("pooling_contract")
            != "multistat_average_max_endpoint"):
        raise ValueError("Teacher model config differs from the compression contract")
    fixed_model = fixed_config.get("model_contract", {})
    if (fixed_config.get("architecture_id") != "multistat_w18_k5"
            or fixed_config.get("expected_checkpoint_sha256")
            != EXPECTED_CHECKPOINT
            or fixed_model.get("channels") != [18, 18, 18]
            or fixed_model.get("kernel_size") != 5
            or fixed_model.get("window_length") != 32):
        raise ValueError("fixed-point config is not bound to the Teacher")
    if (checkpoint.get("model") != "cnn"
            or checkpoint.get("task") != "safe_critical_binary"
            or checkpoint.get("seed") != 20260727
            or checkpoint.get("window_length") != 32
            or checkpoint.get("model_config") != model_config):
        raise ValueError("checkpoint metadata differs from Teacher config")


def audit(config_path, repository_root, output_dir, report_dir):
    """Run the complete Step 0 audit and publish its evidence atomically."""

    config_path = Path(config_path)
    repository_root = Path(repository_root).resolve()
    output_dir = Path(output_dir)
    report_dir = Path(report_dir)
    if output_dir.exists() or report_dir.exists():
        raise FileExistsError("refusing to overwrite Step 0 run directory")
    config = read_json(config_path)
    plan = _resolve(repository_root, config["plan_path"])
    teacher = config["teacher"]
    data = config["data"]
    paths = {
        "plan": plan,
        "checkpoint": _resolve(repository_root, teacher["checkpoint"]),
        "model_config": _resolve(repository_root, teacher["model_config"]),
        "training_summary": _resolve(repository_root, teacher["training_summary"]),
        "final_training_report": _resolve(
            repository_root, teacher["final_training_report"]),
        "fixed_point_config": _resolve(
            repository_root, teacher["fixed_point_config"]),
        "windows": _resolve(repository_root, data["windows"]),
        "windows_manifest": _resolve(repository_root, data["windows_manifest"]),
    }
    for name, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError("missing {}: {}".format(name, path))
    if source_commit(repository_root) != "7a84f153643e6b5408edeb7c9472876ca51f0958":
        raise ValueError("Step 0 must start from the reviewed source commit")
    if sha256_file(paths["checkpoint"]) != EXPECTED_CHECKPOINT:
        raise ValueError("Teacher checkpoint SHA256 mismatch")
    model_config = read_json(paths["model_config"])
    fixed_config = read_json(paths["fixed_point_config"])
    checkpoint = torch.load(paths["checkpoint"], map_location="cpu",
                            weights_only=False)
    _verify_configuration(config, model_config, fixed_config, checkpoint)

    final_training = read_json(paths["final_training_report"])
    aggregate = _report_metrics(final_training)
    for name, expected in EXPECTED_THREE_SEED.items():
        if not _close(aggregate[name], expected, tolerance=2.0e-6):
            raise ValueError("three-seed baseline mismatch: {}".format(name))
    summary = read_json(paths["training_summary"])
    if summary.get("iid_features_loaded") is not False:
        raise ValueError("Teacher training summary crossed IID boundary")
    expected_window_sha = summary.get("windows_sha256")
    if sha256_file(paths["windows"]) != expected_window_sha:
        raise ValueError("training summary and windows digest differ")

    # The split filter runs before features_json parsing.  Only validation is
    # materialized here, so this audit cannot accidentally consume frozen test
    # features while checking the Teacher's published operating point.
    configure_cpu(teacher["representative_seed"], 8)
    validation = load_window_table(paths["windows"], splits={"validation"})
    if (len(validation.labels) != 22512
            or {row["split"] for row in validation.metadata} != {"validation"}
            or set(np.unique(validation.labels)) != {0, 1}):
        raise ValueError("validation split violates the binary L32 contract")
    normalized = apply_normalizer(validation, checkpoint["normalizer"])
    model = build_classifier("cnn", model_config)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()
    _, probabilities = predict(model, normalized.features, 256)
    metrics = binary_window_metrics(
        normalized.labels, probabilities.argmax(axis=1), probabilities)
    for name, expected in EXPECTED_REPRESENTATIVE.items():
        if not _close(metrics[name], expected):
            raise ValueError("representative validation mismatch: {}".format(name))
    if (parameter_count(model) != 3494
            or estimate_macs(model, 32, model_config["input_channels"]) != 106668):
        raise ValueError("Teacher complexity differs from frozen baseline")

    input_manifest = {
        name + "_sha256": sha256_file(path) for name, path in paths.items()
    }
    contract = {
        "schema_version": 1,
        "status": "BASELINE_AUDIT_PASS",
        "compression_id": config["compression_id"],
        "task": config["task"],
        "architecture_id": teacher["architecture_id"]
        if "architecture_id" in teacher else config["architecture_id"],
        "teacher": {
            "checkpoint": str(paths["checkpoint"].resolve()),
            "checkpoint_sha256": sha256_file(paths["checkpoint"]),
            "seed": int(checkpoint["seed"]),
            "channels": [18, 18, 18], "kernel_sizes": [5, 5, 5],
            "pooling_contract": teacher["pooling_contract"],
            "classifier_features": 54,
            "normalizer": checkpoint["normalizer"],
        },
        "data": {
            "windows": str(paths["windows"].resolve()),
            "windows_manifest": str(paths["windows_manifest"].resolve()),
            "allowed_training_splits": data["allowed_training_splits"],
            "selection_split": data["selection_split"],
            "forbidden_splits": data["forbidden_splits"],
            "normalization": data["normalization"],
            "validation_count": len(validation.labels),
            "validation_class_counts": {
                str(class_id): int(np.sum(validation.labels == class_id))
                for class_id in (0, 1)},
        },
        "representative_validation": metrics,
        "three_seed_baseline": aggregate,
        "complexity": {"parameters": parameter_count(model),
                        "estimated_macs_per_window": estimate_macs(
                            model, 32, model_config["input_channels"])},
        "runtime": {"python": platform.python_version(),
                    "torch": torch.__version__, "numpy": np.__version__},
        "input_manifest": input_manifest,
        "iid_features_loaded": False,
        "iid_metrics_computed": False,
        "parameters_tuned_on_test": False,
        "git_commit": source_commit(repository_root),
        "plan_sha256": sha256_file(plan),
        "utc": utc_now(),
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    report_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "teacher_contract.json").write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "input_manifest.json").write_text(
        json.dumps(input_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    (output_dir / "evidence" / "plan_reads.log").parent.mkdir(
        parents=True, exist_ok=False)
    (output_dir / "evidence" / "plan_reads.log").write_text(
        "step=0\nplan_sha256={}\ngit_commit={}\nutc={}\n".format(
            contract["plan_sha256"], contract["git_commit"], contract["utc"]),
        encoding="ascii")
    (report_dir / "BASELINE_AUDIT.md").write_text(
        "# CNN Compression Baseline Audit\n\n"
        "Status: **BASELINE_AUDIT_PASS**.\n\n"
        "Teacher SHA256: `{}`\n\n"
        "Validation metrics were recomputed from the validation split only; "
        "IID/OOD features and metrics were not loaded.\n\n"
        "| Metric | Value |\n| --- | ---: |\n"
        "| Accuracy | {:.9f} |\n| Balanced Accuracy | {:.9f} |\n"
        "| Macro-F1 | {:.9f} |\n| Critical PR-AUC | {:.9f} |\n"
        "| Critical Recall | {:.9f} |\n| Safe FAR | {:.9f} |\n"
        "| Parameters | {} |\n| Estimated MAC/window | {} |\n".format(
            contract["teacher"]["checkpoint_sha256"],
            metrics["accuracy"], metrics["balanced_accuracy"],
            metrics["macro_f1"], metrics["critical_pr_auc"],
            metrics["critical_recall"],
            metrics["safe_window_false_alarm_rate"],
            contract["complexity"]["parameters"],
            contract["complexity"]["estimated_macs_per_window"]),
        encoding="utf-8")
    return contract


def main():
    """CLI wrapper for the fail-closed Step 0 audit."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report-dir", required=True, type=Path)
    args = parser.parse_args()
    audit(args.config, args.repository_root, args.output_dir, args.report_dir)
    print(str(Path(args.output_dir).resolve()))


if __name__ == "__main__":
    main()
