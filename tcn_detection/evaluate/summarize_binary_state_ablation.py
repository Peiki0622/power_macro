#!/usr/bin/env python3
"""Summarize validation-only Safe/Critical ablation metrics."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.evaluate.binary_metrics import binary_window_metrics


def sha256_file(path):
    """Hash persisted ablation evidence in bounded memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def score_predictions(path):
    """Recompute one run and reject any non-validation prediction row."""

    with Path(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        fields = set(reader.fieldnames or [])
    if (not rows or {row["split"] for row in rows} != {"validation"}
            or len({row["window_id"] for row in rows}) != len(rows)
            or "prob_warning" in fields):
        raise ValueError("binary predictions are empty, duplicate, or cross split/schema")
    labels = np.asarray([int(row["target_label"]) for row in rows])
    predictions = np.asarray([int(row["prediction"]) for row in rows])
    probabilities = np.asarray([[float(row["prob_safe"]),
                                 float(row["prob_critical"])] for row in rows])
    return rows, binary_window_metrics(labels, predictions, probabilities)


def main():
    """Rank four complete arms by predeclared robust validation criteria."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ablation-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("refusing to overwrite binary ablation summary")
    manifest_path = args.ablation_dir / "ablation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    jobs = manifest.get("jobs", [])
    if (manifest.get("status") != "PASS" or manifest.get("iid_metrics_computed") is not False
            or len(jobs) != 12 or any(job["status"] != "PASS" for job in jobs)):
        raise ValueError("binary ablation is not a complete development-only matrix")
    runs, grouped = {}, defaultdict(list)
    for job in jobs:
        run_dir = args.ablation_dir / job["output_dir"]
        summary_path = run_dir / "training_summary.json"
        prediction_path = run_dir / "validation_predictions.csv"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        rows, metrics = score_predictions(prediction_path)
        compact = {
            "arm": job["arm"], "seed": int(job["seed"]),
            "prediction_count": len(rows), "metrics": metrics,
            "best_epoch": int(summary["best_epoch"]),
            "checkpoint_score": float(summary["best_checkpoint_score"]),
            "summary_sha256": sha256_file(summary_path),
            "predictions_sha256": sha256_file(prediction_path),
            "checkpoint_sha256": sha256_file(run_dir / "best_checkpoint.pt"),
        }
        runs[job["name"]] = compact
        grouped[job["arm"]].append(compact)
    arms = {}
    for arm, items in sorted(grouped.items()):
        if len(items) != 3:
            raise ValueError("each binary arm must contain exactly three seeds")
        critical_ap = np.asarray([item["metrics"]["critical_pr_auc"] for item in items])
        macro_f1 = np.asarray([item["metrics"]["macro_f1"] for item in items])
        arms[arm] = {
            "seeds": sorted(item["seed"] for item in items),
            "median_critical_pr_auc": float(np.median(critical_ap)),
            "critical_pr_auc_variance": float(np.var(critical_ap)),
            "worst_seed_critical_recall": float(min(
                item["metrics"]["critical_recall"] for item in items)),
            "median_macro_f1": float(np.median(macro_f1)),
            "median_balanced_accuracy": float(np.median([
                item["metrics"]["balanced_accuracy"] for item in items])),
            "median_safe_window_false_alarm_rate": float(np.median([
                item["metrics"]["safe_window_false_alarm_rate"] for item in items])),
        }
    ranking = sorted(arms, key=lambda arm: (
        -arms[arm]["median_critical_pr_auc"],
        -arms[arm]["worst_seed_critical_recall"],
        -arms[arm]["median_macro_f1"],
        arms[arm]["critical_pr_auc_variance"],
        arms[arm]["median_safe_window_false_alarm_rate"], arm))
    report = {
        "schema_version": 1, "scope": "validation_only",
        "iid_metrics_computed": False,
        "selection_primary": "median_critical_pr_auc",
        "manifest_sha256": sha256_file(manifest_path),
        "runs": runs, "arms": arms, "ranking": ranking,
        "selected_arm": ranking[0],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
