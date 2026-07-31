#!/usr/bin/env python3
"""Strictly validate and rank the binary CNN structure search."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.evaluate.binary_metrics import binary_window_metrics
from power_macro.tcn_detection.train.common import build_classifier


def sha256_file(path):
    """Hash one evidence artifact using bounded memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_validation_metrics(path):
    """Recompute complete metrics and reject any non-validation prediction."""

    labels, predictions, probabilities = [], [], []
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row.get("split") != "validation":
                raise ValueError("structure search predictions are not validation-only")
            labels.append(int(row["target_label"]))
            predictions.append(int(row["prediction"]))
            probabilities.append([float(row["prob_safe"]),
                                  float(row["prob_critical"])])
    if len(labels) != 22512:
        raise ValueError("structure search requires 22,512 validation predictions")
    return binary_window_metrics(np.asarray(labels), np.asarray(predictions),
                                 np.asarray(probabilities))


def read_run(job):
    """Verify hashes, restore one exact CNN, and extract validation metrics."""

    run_dir = Path(job["output_dir"])
    summary_path = run_dir / "training_summary.json"
    checkpoint_path = run_dir / "best_checkpoint.pt"
    predictions_path = run_dir / "validation_predictions.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if (summary.get("model") != "cnn"
            or summary.get("iid_features_loaded") is not False
            or summary.get("windows_sha256") != job["windows_sha256"]
            or summary.get("training_config_sha256")
            != job["training_config_sha256"]
            or summary.get("model_config_sha256") != job["model_config_sha256"]
            or int(summary.get("parameter_count", -1)) != job["parameter_count"]
            or int(summary.get("estimated_macs_per_window", -1))
            != job["estimated_macs_per_window"]):
        raise ValueError("structure training summary differs from manifest")
    model_config = json.loads(Path(job["model_config"]).read_text(encoding="utf-8"))
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model = build_classifier("cnn", model_config)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    metrics = load_validation_metrics(predictions_path)
    return {
        "seed": int(job["seed"]), "best_epoch": int(summary["best_epoch"]),
        "accuracy": metrics["accuracy"],
        "balanced_accuracy": metrics["balanced_accuracy"],
        "macro_f1": metrics["macro_f1"],
        "critical_pr_auc": metrics["critical_pr_auc"],
        "critical_precision": metrics["critical_precision"],
        "critical_recall": metrics["critical_recall"],
        "safe_far": metrics["safe_window_false_alarm_rate"],
        "checkpoint": str(checkpoint_path.resolve()),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "validation_predictions": str(predictions_path.resolve()),
        "validation_predictions_sha256": sha256_file(predictions_path),
        "training_summary": str(summary_path.resolve()),
        "training_summary_sha256": sha256_file(summary_path),
    }


def aggregate(name, jobs, gates):
    """Aggregate three seeds and apply all pre-existing quality gates."""

    runs = [read_run(job) for job in jobs]
    if len(runs) != 3 or len({run["seed"] for run in runs}) != 3:
        raise ValueError("each structure requires three unique seeds")
    values = lambda field: np.asarray([run[field] for run in runs], dtype=float)
    first = jobs[0]
    result = {
        "name": name, "receptive_field": first["receptive_field"],
        "parameter_count": first["parameter_count"],
        "estimated_macs_per_window": first["estimated_macs_per_window"],
        "median_accuracy": float(np.median(values("accuracy"))),
        "median_balanced_accuracy": float(np.median(values("balanced_accuracy"))),
        "median_macro_f1": float(np.median(values("macro_f1"))),
        "median_critical_pr_auc": float(np.median(values("critical_pr_auc"))),
        "critical_pr_auc_std": float(np.std(values("critical_pr_auc"))),
        "worst_critical_recall": float(np.min(values("critical_recall"))),
        "median_critical_recall": float(np.median(values("critical_recall"))),
        "median_critical_precision": float(np.median(values("critical_precision"))),
        "median_safe_far": float(np.median(values("safe_far"))), "runs": runs,
    }
    result["gate_checks"] = {
        "critical_pr_auc": result["median_critical_pr_auc"]
        >= gates["median_critical_pr_auc_min"],
        "accuracy": result["median_accuracy"] >= gates["median_accuracy_min"],
        "balanced_accuracy": result["median_balanced_accuracy"]
        >= gates["median_balanced_accuracy_min"],
        "macro_f1": result["median_macro_f1"] >= gates["median_macro_f1_min"],
        "critical_recall": result["worst_critical_recall"]
        >= gates["worst_seed_critical_recall_min"],
        "safe_far": result["median_safe_far"]
        <= gates["median_safe_window_false_alarm_rate_max"],
    }
    result["feasible"] = all(result["gate_checks"].values())
    return result


def rank_candidates(candidates):
    """Rank feasibility first, then the quality order frozen before training."""

    return sorted(candidates, key=lambda item: (
        not item["feasible"], -item["median_critical_pr_auc"],
        -item["median_macro_f1"], -item["worst_critical_recall"],
        -item["median_balanced_accuracy"], item["median_safe_far"],
        item["estimated_macs_per_window"], item["name"]))


def markdown(report):
    """Render all structure aggregates and the TCN quality/complexity targets."""

    lines = ["# Binary CNN Structure Search", "",
             "All metrics are validation-only three-seed aggregates. No IID "
             "feature or metric was loaded.", "",
             "| Rank | Structure | RF | Params | MAC | Median PR-AUC | "
             "Median Accuracy | Median Macro-F1 | Worst Critical recall | "
             "Median Safe FAR | Feasible |",
             "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for index, item in enumerate(report["ranking"], 1):
        lines.append("| {} | {} | {} | {} | {} | {:.6f} | {:.6f} | {:.6f} | "
                     "{:.6f} | {:.6f} | {} |".format(
                         index, item["name"], item["receptive_field"],
                         item["parameter_count"], item["estimated_macs_per_window"],
                         item["median_critical_pr_auc"], item["median_accuracy"],
                         item["median_macro_f1"], item["worst_critical_recall"],
                         item["median_safe_far"], item["feasible"]))
    tcn = report["tcn_comparison"]
    lines.extend(["", "TCN validation Critical PR-AUC: `{:.6f}`; parameters: "
                  "`{}`; MAC/window: `{}`.".format(
                      tcn["validation_critical_pr_auc"], tcn["parameter_count"],
                      tcn["estimated_macs_per_window"]), "",
                  "Selected structure: `{}`.".format(report["selected_candidate"]), ""])
    return "\n".join(lines)


def main():
    """Validate all 18 runs and atomically publish the structure ranking."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--search-config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite structure summary")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    contract = json.loads(args.search_config.read_text(encoding="utf-8"))
    jobs = manifest.get("jobs", [])
    if (manifest.get("status") != "PASS" or len(jobs) != 18
            or manifest.get("iid_features_loaded") is not False
            or manifest.get("iid_metrics_computed") is not False
            or any(job.get("status") != "PASS" for job in jobs)
            or manifest.get("search_config_sha256") != sha256_file(args.search_config)):
        raise ValueError("structure manifest is incomplete or crossed into IID")
    names = [item["name"] for item in contract["candidates"]]
    candidates = [aggregate(
        name, [job for job in jobs if job["candidate"] == name],
        contract["quality_feasibility"]) for name in names]
    ranking = rank_candidates(candidates)
    report = {
        "schema_version": 1, "scope": "validation_only",
        "task": "safe_critical_binary", "model": "cnn",
        "iid_features_loaded": False, "iid_metrics_computed": False,
        "parameters_tuned_on_test": False,
        "quality_feasibility": contract["quality_feasibility"],
        "tcn_comparison": contract["tcn_comparison"],
        "selected_candidate": ranking[0]["name"], "ranking": ranking,
        "manifest_sha256": sha256_file(args.manifest),
        "search_config_sha256": sha256_file(args.search_config),
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "selection.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "SELECTION.md").write_text(markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
