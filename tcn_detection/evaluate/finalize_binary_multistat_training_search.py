#!/usr/bin/env python3
"""Finalize validation-only training tuning for the selected multistat CNN."""

from __future__ import print_function

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.evaluate.finalize_binary_cnn_hparam_search import (
    feasibility, representative_run, validation_metrics)


def sha256_file(path):
    """Return a bounded-memory digest for one immutable report input."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Load one JSON object and reject arrays/scalars at the top level."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return payload


def validate_boundary(name, report):
    """Require validation-only evidence with no IID feature or metric access."""

    if (report.get("scope") != "validation_only"
            or report.get("iid_features_loaded") is not False
            or report.get("iid_metrics_computed") is not False
            or report.get("parameters_tuned_on_test") is not False):
        raise ValueError("{} crossed the validation-only boundary".format(name))


def enrich_arm(arm, gates):
    """Add omitted Accuracy, gate results, and recorded latency to one arm.

    The search summary stores ranking metrics but not Accuracy.  Recomputing it
    from digest-bound validation CSVs completes the original six-gate contract
    without loading feature windows or invoking a model.  Training summaries
    are separately verified before using their diagnostic CPU latency.
    """

    enriched = dict(arm)
    accuracies, latencies = [], []
    for run in enriched["runs"]:
        metrics = validation_metrics(run["validation_predictions"],
                                     run["validation_predictions_sha256"])
        accuracies.append(float(metrics["accuracy"]))
        summary_path = Path(run["training_summary"])
        if sha256_file(summary_path) != run["training_summary_sha256"]:
            raise ValueError("selected training summary digest changed")
        latencies.append(float(read_json(summary_path)["median_cpu_latency_ms"]))
    enriched["median_accuracy"] = float(np.median(accuracies))
    enriched["per_seed_accuracy"] = accuracies
    enriched["median_cpu_latency_ms"] = float(np.median(latencies))
    enriched["gate_checks"], enriched["feasible"] = feasibility(enriched, gates)
    return enriched


def final_order(arm):
    """Apply feasibility first and then the predeclared quality ordering."""

    return (not arm["feasible"], -arm["median_critical_pr_auc"],
            -arm["median_macro_f1"], -arm["worst_critical_recall"],
            -arm["median_balanced_accuracy"], arm["median_safe_far"],
            arm["critical_pr_auc_std"], arm["name"])


def markdown(report):
    """Render aggregate, per-seed, parameter, and complexity comparisons."""

    models = (("Before retuning", report["before_retuning"]),
              ("After retuning", report["selected_training"]),
              ("TCN", report["tcn"]))
    lines = ["# Final Multistat CNN Training Tuning", "",
             "All quality metrics are validation-only three-seed aggregates. "
             "No IID feature, prediction, or metric was loaded.", "",
             "## Aggregate Validation Metrics", "",
             "| Metric | Before retuning | After retuning | TCN |",
             "| --- | ---: | ---: | ---: |"]
    for label, field in (
            ("Median Accuracy", "median_accuracy"),
            ("Median balanced accuracy", "median_balanced_accuracy"),
            ("Median Macro-F1", "median_macro_f1"),
            ("Median Critical PR-AUC", "median_critical_pr_auc"),
            ("Worst-seed Critical recall", "worst_critical_recall"),
            ("Median Safe FAR", "median_safe_far")):
        lines.append("| {} | {} |".format(
            label, " | ".join("{:.6f}".format(item[field])
                              for _, item in models)))
    selected = report["selected_training"]
    lines.extend(["", "## Selected Training Parameters", "",
                  "| Parameter | Value |", "| --- | ---: |"])
    for key in ("learning_rate", "weight_decay", "batch_size", "max_epochs",
                "early_stopping_patience", "lr_scheduler"):
        lines.append("| {} | {} |".format(
            key, selected["training_parameters"].get(key)))
    lines.extend(["", "## Selected CNN Per Seed", "",
                  "| Seed | Best epoch | Accuracy | Balanced acc. | Macro-F1 | "
                  "Critical PR-AUC | Critical precision | Critical recall | Safe FAR |",
                  "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for run, accuracy in zip(selected["runs"], selected["per_seed_accuracy"]):
        lines.append("| {} | {} | {:.6f} | {:.6f} | {:.6f} | {:.6f} | {:.6f} | "
                     "{:.6f} | {:.6f} |".format(
                         run["seed"], run["best_epoch"], accuracy,
                         run["balanced_accuracy"], run["macro_f1"],
                         run["critical_pr_auc"], run["critical_precision"],
                         run["critical_recall"], run["safe_far"]))
    lines.extend(["", "## Complexity", "",
                  "| Metric | Selected CNN | TCN |", "| --- | ---: | ---: |",
                  "| Parameters | 3494 | 4050 |",
                  "| Estimated MAC/window | 106668 | 125952 |",
                  "| Recorded CPU ms/window | {:.6f} | {:.6f} |".format(
                      selected["median_cpu_latency_ms"],
                      report["tcn"]["median_cpu_latency_ms"]), "",
                  "Representative seed: `{}`; checkpoint SHA256: `{}`.".format(
                      report["representative_run"]["seed"],
                      report["representative_run"]["checkpoint_sha256"]), "",
                  "This remains a validation-selected next-release candidate. "
                  "The existing IID evaluation is unchanged and must not be rerun.", ""])
    return "\n".join(lines)


def main():
    """Combine both searches with the prior structure/TCN comparison."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage1", required=True, type=Path)
    parser.add_argument("--stage2", required=True, type=Path)
    parser.add_argument("--stage2-config", required=True, type=Path)
    parser.add_argument("--prior-structure", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite final multistat tuning report")
    stage1, stage2 = read_json(args.stage1), read_json(args.stage2)
    contract, prior = read_json(args.stage2_config), read_json(args.prior_structure)
    validate_boundary("stage1", stage1)
    validate_boundary("stage2", stage2)
    validate_boundary("prior structure", prior)
    gates = contract["quality_feasibility"]
    candidates = sorted([enrich_arm(arm, gates) for arm in stage2["ranking"]],
                        key=final_order)
    selected = candidates[0]
    if not selected["feasible"]:
        raise ValueError("training search produced no quality-feasible candidate")
    report = {
        "schema_version": 1, "scope": "validation_only",
        "task": "safe_critical_binary", "model": "cnn",
        "architecture": "multistat_w18_k5",
        "iid_features_loaded": False, "iid_metrics_computed": False,
        "parameters_tuned_on_test": False, "iid_evaluation_performed": False,
        "quality_gates": gates, "ranking": candidates,
        "selected_arm": selected["name"], "selected_training": selected,
        "before_retuning": prior["selected_cnn"], "tcn": prior["tcn"],
        "representative_run": representative_run(selected),
        "inputs": {name + "_sha256": sha256_file(getattr(args, name))
                   for name in ("stage1", "stage2", "stage2_config",
                                "prior_structure")},
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "final_training.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "FINAL_TRAINING.md").write_text(markdown(report),
                                                       encoding="utf-8")


if __name__ == "__main__":
    main()
