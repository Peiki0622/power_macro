#!/usr/bin/env python3
"""Summarize validation-only metrics for the code-state L32 ablation."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.evaluate.metrics import window_metrics


RAW_GATES = {
    "accuracy": (">=", 0.95),
    "balanced_accuracy": (">=", 0.90),
    "macro_f1": (">=", 0.80),
    "risk_recall": (">=", 0.95),
    "critical_recall": (">=", 0.95),
    "warning_recall": (">=", 0.70),
    "safe_window_false_alarm_rate": ("<=", 0.05),
}


def sha256_file(path):
    """Hash one persisted artifact using bounded memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_validation_predictions(path):
    """Load a development prediction file and reject test-split leakage."""

    rows = []
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["split"] != "validation":
                raise ValueError("ablation summary refuses non-validation rows")
            rows.append(row)
    identifiers = [row["window_id"] for row in rows]
    if not rows or len(identifiers) != len(set(identifiers)):
        raise ValueError("empty or duplicate validation predictions")
    return rows


def gate_checks(metrics):
    """Evaluate all predeclared operating gates without rounding metrics."""

    checks = {}
    for name, (operator, threshold) in RAW_GATES.items():
        checks[name] = (metrics[name] >= threshold if operator == ">="
                        else metrics[name] <= threshold)
    return checks


def mean_std(items, name):
    """Return population mean/std across the three fixed seeds."""

    values = np.asarray([item[name] for item in items], dtype=np.float64)
    return {"mean": float(np.mean(values)), "std": float(np.std(values))}


def main():
    """Recompute run metrics and atomically publish a validation report."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ablation-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("refusing to overwrite state ablation summary")
    manifest_path = args.ablation_dir / "ablation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    jobs = manifest.get("jobs", [])
    if (manifest.get("status") != "PASS" or len(jobs) != 12
            or any(job.get("status") != "PASS" for job in jobs)):
        raise ValueError("state ablation is not a complete 12-job PASS matrix")

    runs = {}
    grouped = defaultdict(list)
    for job in jobs:
        run_dir = args.ablation_dir / job["output_dir"]
        summary_path = run_dir / "training_summary.json"
        predictions_path = run_dir / "validation_predictions.csv"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        rows = read_validation_predictions(predictions_path)
        labels = np.asarray([int(row["target_label"]) for row in rows])
        predictions = np.asarray([int(row["prediction"]) for row in rows])
        probabilities = np.asarray([[float(row["prob_safe"]),
                                     float(row["prob_warning"]),
                                     float(row["prob_critical"])] for row in rows])
        report = window_metrics(labels, predictions, probabilities)
        risk_mask = labels >= 1
        compact = {
            "accuracy": report["accuracy"],
            "balanced_accuracy": report["balanced_accuracy"],
            "macro_f1": report["macro_f1"],
            "weighted_f1": report["weighted_f1"],
            "risk_recall": float(np.mean(predictions[risk_mask] >= 1)),
            "critical_recall": report["per_class"]["2"]["recall"],
            "warning_recall": report["per_class"]["1"]["recall"],
            "safe_recall": report["per_class"]["0"]["recall"],
            "safe_window_false_alarm_rate": report["safe_window_false_alarm_rate"],
            "macro_pr_auc_ovr": report["macro_pr_auc_ovr"],
            "macro_roc_auc_ovr": report["macro_roc_auc_ovr"],
            "log_loss": report["log_loss"],
            "multiclass_brier_score": report["multiclass_brier_score"],
            "per_class": report["per_class"],
            "confusion_matrix": report["confusion_matrix"],
            "checkpoint_score": float(summary["best_checkpoint_score"]),
            "best_epoch": int(summary["best_epoch"]),
            "arm": job["arm"], "seed": int(job["seed"]),
            "prediction_count": len(rows),
            "predictions_sha256": sha256_file(predictions_path),
            "summary_sha256": sha256_file(summary_path),
        }
        compact["gate_checks"] = gate_checks(compact)
        compact["passes_all_raw_gates"] = all(compact["gate_checks"].values())
        runs[job["name"]] = compact
        grouped[job["arm"]].append(compact)

    aggregate_names = ("accuracy", "balanced_accuracy", "macro_f1", "weighted_f1",
                       "risk_recall", "critical_recall", "warning_recall",
                       "safe_recall", "safe_window_false_alarm_rate",
                       "macro_pr_auc_ovr", "macro_roc_auc_ovr", "log_loss",
                       "multiclass_brier_score", "checkpoint_score")
    arms = {}
    for arm, items in sorted(grouped.items()):
        if len(items) != 3 or len({item["seed"] for item in items}) != 3:
            raise ValueError("each arm must contain three distinct seeds")
        arms[arm] = {
            "seeds": sorted(item["seed"] for item in items),
            "metrics": {name: mean_std(items, name) for name in aggregate_names},
            "worst_seed": {name: (max(item[name] for item in items)
                                   if RAW_GATES[name][0] == "<="
                                   else min(item[name] for item in items))
                           for name in RAW_GATES},
            "all_seeds_pass_raw_gates": all(item["passes_all_raw_gates"]
                                             for item in items),
        }
    # Ranking uses mean Macro-F1 first, then mean balanced accuracy, risk
    # recall, lower Safe FAR, and stable arm name.  This is validation-only and
    # frozen before any IID/OOD evaluation.
    ranking = sorted(arms, key=lambda arm: (
        -arms[arm]["metrics"]["macro_f1"]["mean"],
        -arms[arm]["metrics"]["balanced_accuracy"]["mean"],
        -arms[arm]["metrics"]["risk_recall"]["mean"],
        arms[arm]["metrics"]["safe_window_false_alarm_rate"]["mean"], arm))
    report = {
        "schema_version": 1, "scope": "validation_only",
        "iid_ood_metrics_computed": False,
        "raw_gates": {name: {"operator": value[0], "threshold": value[1]}
                      for name, value in RAW_GATES.items()},
        "manifest_sha256": sha256_file(manifest_path),
        "runs": runs, "arms": arms, "ranking": ranking,
        "selected_arm": ranking[0],
        "any_arm_all_seeds_pass": any(
            item["all_seeds_pass_raw_gates"] for item in arms.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
