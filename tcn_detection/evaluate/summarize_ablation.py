#!/usr/bin/env python3
"""Recompute validation-only L32 ablation metrics and select two arms."""

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
    "macro_f1": 0.55,
    "macro_pr_auc_ovr": 0.60,
    "safe_recall": 0.60,
    "critical_recall": 0.50,
}


def sha256_file(path):
    """Hash one persisted artifact using bounded memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_validation_predictions(path):
    """Load exactly one development prediction file and reject split leakage."""

    rows = []
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for raw in csv.DictReader(stream):
            if raw["split"] != "validation":
                raise ValueError("ablation summary refuses non-validation predictions")
            rows.append(raw)
    if not rows:
        raise ValueError("validation prediction file is empty: {}".format(path))
    identifiers = [row["window_id"] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("validation prediction file contains duplicate IDs: {}".format(path))
    return rows


def rank_arms(aggregates):
    """Return arm names in the predeclared deterministic selection order.

    Primary selection uses median checkpoint score across the three seeds.
    Exact ties favor the strongest worst-seed Critical Recall, then median Safe
    Recall, median Macro-F1, and finally lower checkpoint-score variance.  The
    arm name is a final stable key only to make mathematically identical inputs
    reproducible; it does not encode model preference.
    """

    return sorted(aggregates, key=lambda arm: (
        -float(aggregates[arm]["median_checkpoint_score"]),
        -float(aggregates[arm]["worst_seed_critical_recall"]),
        -float(aggregates[arm]["median_safe_recall"]),
        -float(aggregates[arm]["median_macro_f1"]),
        float(aggregates[arm]["checkpoint_score_variance"]),
        arm,
    ))


def main():
    """Publish one immutable report computed only from validation artifacts."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ablation-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("refusing to overwrite ablation summary: {}".format(args.output))

    manifest_path = args.ablation_dir / "ablation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    jobs = manifest.get("jobs", [])
    # The original direct-classification matrix contains four arms, while a
    # conditional objective branch may intentionally contain one arm.  The
    # scientific invariant is three successful seeds per arm, checked below;
    # hard-coding twelve here would force duplicated summary implementations.
    if manifest.get("status") != "PASS" or not jobs or any(job.get("status") != "PASS" for job in jobs):
        raise ValueError("ablation manifest does not contain only completed PASS jobs")

    runs = {}
    grouped = defaultdict(list)
    for job in jobs:
        run_dir = args.ablation_dir / job["output_dir"]
        summary_path = run_dir / "training_summary.json"
        prediction_path = run_dir / "validation_predictions.csv"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        rows = read_validation_predictions(prediction_path)
        labels = np.asarray([int(row["target_label"]) for row in rows], dtype=np.int64)
        predictions = np.asarray([int(row["prediction"]) for row in rows], dtype=np.int64)
        probabilities = np.asarray([[float(row["prob_safe"]), float(row["prob_warning"]),
                                     float(row["prob_critical"])] for row in rows], dtype=np.float64)
        metrics = window_metrics(labels, predictions, probabilities)
        compact = {
            "checkpoint_score": float(summary["best_checkpoint_score"]),
            "macro_f1": metrics["macro_f1"],
            "macro_pr_auc_ovr": metrics["macro_pr_auc_ovr"],
            "safe_recall": metrics["per_class"]["0"]["recall"],
            "warning_precision": metrics["per_class"]["1"]["precision"],
            "critical_recall": metrics["per_class"]["2"]["recall"],
            "safe_window_false_alarm_rate": metrics["safe_window_false_alarm_rate"],
        }
        compact["gate_checks"] = {name: compact[name] >= threshold for name, threshold in RAW_GATES.items()}
        compact["passes_all_raw_gates"] = all(compact["gate_checks"].values())
        compact.update({
            "arm": job["arm"], "seed": int(job["seed"]),
            "prediction_count": len(rows),
            "predictions_sha256": sha256_file(prediction_path),
            "summary_sha256": sha256_file(summary_path),
        })
        runs[job["name"]] = compact
        grouped[job["arm"]].append(compact)

    arms = {}
    for arm, items in sorted(grouped.items()):
        if len(items) != 3 or len({item["seed"] for item in items}) != 3:
            raise ValueError("arm does not contain exactly three distinct seeds: {}".format(arm))
        scores = np.asarray([item["checkpoint_score"] for item in items], dtype=np.float64)
        arms[arm] = {
            "seeds": sorted(item["seed"] for item in items),
            "median_checkpoint_score": float(np.median(scores)),
            "checkpoint_score_variance": float(np.var(scores)),
            "worst_seed_critical_recall": float(min(item["critical_recall"] for item in items)),
            "median_safe_recall": float(np.median([item["safe_recall"] for item in items])),
            "median_macro_f1": float(np.median([item["macro_f1"] for item in items])),
            "median_macro_pr_auc_ovr": float(np.median([item["macro_pr_auc_ovr"] for item in items])),
            # A formal arm passes only if every seed clears every raw gate.  A
            # median-only pass could conceal an unstable seed, contradicting
            # the plan's later worst-seed robustness requirement.
            "all_seeds_pass_raw_gates": all(item["passes_all_raw_gates"] for item in items),
        }
    ranking = rank_arms(arms)
    report = {
        "schema_version": 1, "scope": "validation_only", "iid_ood_metrics_computed": False,
        "raw_gates": RAW_GATES, "manifest_sha256": sha256_file(manifest_path),
        "runs": runs, "arms": arms, "ranking": ranking, "selected_top_two": ranking[:2],
        "any_arm_passes_raw_gates": any(item["all_seeds_pass_raw_gates"] for item in arms.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
