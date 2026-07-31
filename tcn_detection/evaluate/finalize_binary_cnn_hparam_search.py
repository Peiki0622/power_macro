#!/usr/bin/env python3
"""Finalize validation-only CNN tuning against the pre-existing quality gates."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.evaluate.binary_metrics import binary_window_metrics


def sha256_file(path):
    """Return a bounded-memory digest for one immutable input report."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Load one JSON object and reject an unexpected top-level type."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return payload


def validation_metrics(path, expected_digest):
    """Recompute full window metrics from stored validation predictions only.

    Training summaries intentionally store a compact checkpoint key and omit
    Accuracy.  The original quality contract includes an Accuracy gate, so this
    function reconstructs it from the already-published validation CSV rather
    than loading feature windows or running a model.  Strict split and digest
    checks prevent an IID file from being substituted as validation evidence.
    """

    if sha256_file(path) != expected_digest:
        raise ValueError("validation prediction digest changed")
    labels, predictions, probabilities = [], [], []
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row.get("split") != "validation":
                raise ValueError("final tuning report accepts validation rows only")
            labels.append(int(row["target_label"]))
            predictions.append(int(row["prediction"]))
            probabilities.append([float(row["prob_safe"]),
                                  float(row["prob_critical"])])
    if len(labels) != 22512:
        raise ValueError("final tuning report requires 22,512 validation rows")
    return binary_window_metrics(np.asarray(labels), np.asarray(predictions),
                                 np.asarray(probabilities))


def feasibility(arm, gates):
    """Apply every threshold frozen before the original CNN IID evaluation."""

    checks = {
        "critical_pr_auc": arm["median_critical_pr_auc"]
        >= gates["median_critical_pr_auc_min"],
        "accuracy": arm["median_accuracy"] >= gates["median_accuracy_min"],
        "balanced_accuracy": arm["median_balanced_accuracy"]
        >= gates["median_balanced_accuracy_min"],
        "macro_f1": arm["median_macro_f1"] >= gates["median_macro_f1_min"],
        "critical_recall": arm["worst_critical_recall"]
        >= gates["worst_seed_critical_recall_min"],
        "safe_far": arm["median_safe_far"]
        <= gates["median_safe_window_false_alarm_rate_max"],
    }
    return checks, all(checks.values())


def quality_order(arm):
    """Return the original objective-selection order for feasible candidates."""

    return (-arm["median_critical_pr_auc"], -arm["median_macro_f1"],
            -arm["median_balanced_accuracy"], -arm["worst_critical_recall"],
            arm["median_safe_far"], arm["name"])


def representative_run(arm):
    """Select an actual seed nearest median PR-AUC, never the best seed alone."""

    median_ap = arm["median_critical_pr_auc"]
    return min(arm["runs"], key=lambda run: (
        abs(run["critical_pr_auc"] - median_ap), -run["macro_f1"],
        -run["balanced_accuracy"], -run["critical_recall"],
        run["safe_far"], int(run["seed"])))


def enrich_arm(arm, gates):
    """Add full validation Accuracy and frozen quality-gate conclusions."""

    enriched = dict(arm)
    accuracies = []
    for run in arm["runs"]:
        metrics = validation_metrics(run["validation_predictions"],
                                     run["validation_predictions_sha256"])
        accuracies.append(float(metrics["accuracy"]))
    enriched["median_accuracy"] = float(np.median(accuracies))
    enriched["per_seed_accuracy"] = accuracies
    enriched["gate_checks"], enriched["feasible"] = feasibility(enriched, gates)
    return enriched


def markdown(report):
    """Render baseline, rank winner, and quality-feasible recommendation."""

    baseline = report["baseline"]
    rank_winner = report["ranking_winner"]
    recommendation = report["recommended_quality_feasible_arm"]
    columns = (("Original", baseline), ("Rank winner", rank_winner),
               ("Recommended", recommendation))
    lines = [
        "# Binary CNN Training Hyperparameter Tuning", "",
        "This report uses train/validation artifacts only. It does not load, "
        "score, or rerun IID and therefore does not replace the existing "
        "one-shot release evaluation.", "", "## Aggregate Validation Metrics", "",
        "| Metric | Original lr=1e-3/wd=1e-4 | PR-AUC rank winner | "
        "Quality-feasible recommendation |", "| --- | ---: | ---: | ---: |",
    ]
    fields = [
        ("Median Critical PR-AUC", "median_critical_pr_auc"),
        ("Median Accuracy", "median_accuracy"),
        ("Median balanced accuracy", "median_balanced_accuracy"),
        ("Median Macro-F1", "median_macro_f1"),
        ("Worst-seed Critical recall", "worst_critical_recall"),
        ("Median Safe FAR", "median_safe_far"),
    ]
    for label, field in fields:
        lines.append("| {} | {} |".format(
            label, " | ".join("{:.6f}".format(item[field])
                              for _, item in columns)))
    lines.extend(["| Pass all frozen validation gates | {} | {} | {} |".format(
        baseline["feasible"], rank_winner["feasible"], recommendation["feasible"]),
        "", "## Recommendation", "",
        "- Optimizer: AdamW, learning rate `{:.6g}`, weight decay `{:.6g}`.".format(
            recommendation["learning_rate"], recommendation["weight_decay"]),
        "- Unchanged: batch 256, max epochs 80, patience 12, natural CE.",
        "- Representative seed: `{}`; best epoch: `{}`.".format(
            report["representative_run"]["seed"],
            report["representative_run"]["best_epoch"]),
        "- Representative checkpoint SHA256: `{}`.".format(
            report["representative_run"]["checkpoint_sha256"]),
        "- IID features loaded: `false`; IID metrics computed: `false`.",
        "- This is a next-release validation candidate, not a new IID result.", ""])
    return "\n".join(lines)


def main():
    """Combine both tuning stages and publish the quality-aware recommendation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage1", required=True, type=Path)
    parser.add_argument("--stage2", required=True, type=Path)
    parser.add_argument("--baseline-objectives", required=True, type=Path)
    parser.add_argument("--policy-config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite final hyperparameter report")
    stage1, stage2 = read_json(args.stage1), read_json(args.stage2)
    baseline_report = read_json(args.baseline_objectives)
    policy = read_json(args.policy_config)
    for name, report in (("stage1", stage1), ("stage2", stage2)):
        if (report.get("scope") != "validation_only"
                or report.get("iid_features_loaded") is not False
                or report.get("iid_metrics_computed") is not False
                or report.get("parameters_tuned_on_test") is not False):
            raise ValueError("{} report crossed the IID boundary".format(name))
    gates = policy["quality_feasibility"]
    enriched = [enrich_arm(arm, gates) for arm in stage2["ranking"]]
    ranking_winner = next(arm for arm in enriched
                          if arm["name"] == stage2["selected_arm"])
    feasible = sorted([arm for arm in enriched if arm["feasible"]],
                      key=quality_order)
    if not feasible:
        raise ValueError("local tuning produced no quality-feasible arm")
    recommended = feasible[0]

    # The original objective report already evaluated the same six gates.  It
    # is copied as the historical reference without opening its checkpoints or
    # touching the old IID output.
    original_source = baseline_report["arms"]["a_natural_ce"]
    original = {
        "name": "original_lr1em3_wd1em4",
        "learning_rate": 0.001, "weight_decay": 0.0001,
        "median_critical_pr_auc": original_source["median_critical_pr_auc"],
        "median_accuracy": original_source["median_accuracy"],
        "median_balanced_accuracy": original_source["median_balanced_accuracy"],
        "median_macro_f1": original_source["median_macro_f1"],
        "worst_critical_recall": original_source["worst_seed_critical_recall"],
        "median_safe_far": original_source[
            "median_safe_window_false_alarm_rate"],
        "gate_checks": original_source["gate_checks"],
        "feasible": original_source["feasible"],
    }
    report = {
        "schema_version": 1, "scope": "validation_only",
        "task": "safe_critical_binary", "model": "cnn",
        "iid_features_loaded": False, "iid_metrics_computed": False,
        "parameters_tuned_on_test": False,
        "existing_iid_evaluation_reused": False,
        "quality_gates": gates, "baseline": original,
        "ranking_winner": ranking_winner,
        "quality_feasible_arm_count": len(feasible),
        "recommended_quality_feasible_arm": recommended,
        "representative_run": representative_run(recommended),
        "stage1_sha256": sha256_file(args.stage1),
        "stage2_sha256": sha256_file(args.stage2),
        "baseline_objectives_sha256": sha256_file(args.baseline_objectives),
        "policy_config_sha256": sha256_file(args.policy_config),
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "final_tuning.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "FINAL_TUNING.md").write_text(markdown(report),
                                                     encoding="utf-8")


if __name__ == "__main__":
    main()
