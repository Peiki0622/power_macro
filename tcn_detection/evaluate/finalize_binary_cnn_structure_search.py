#!/usr/bin/env python3
"""Finalize the validation-only CNN structure comparison with the frozen TCN."""

from __future__ import print_function

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256_file(path):
    """Return a bounded-memory digest for one immutable report input."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Load one JSON object and reject non-object top-level values."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return payload


def validate_validation_only(name, report):
    """Reject any structure/tuning report that accessed or tuned on IID."""

    if (report.get("scope") != "validation_only"
            or report.get("iid_features_loaded") is not False
            or report.get("iid_metrics_computed") is not False
            or report.get("parameters_tuned_on_test") is not False):
        raise ValueError("{} report crossed the validation-only boundary".format(name))


def representative_run(candidate):
    """Choose an actual seed nearest median PR-AUC with deterministic ties."""

    median_ap = candidate["median_critical_pr_auc"]
    return min(candidate["runs"], key=lambda run: (
        abs(run["critical_pr_auc"] - median_ap), -run["macro_f1"],
        -run["balanced_accuracy"], -run["critical_recall"],
        run["safe_far"], int(run["seed"])))


def median_recorded_latency(candidate):
    """Read run-recorded CPU latency only after verifying each summary digest."""

    values = []
    for run in candidate["runs"]:
        summary_path = Path(run["training_summary"])
        if sha256_file(summary_path) != run["training_summary_sha256"]:
            raise ValueError("selected structure training summary changed")
        summary = read_json(summary_path)
        values.append(float(summary["median_cpu_latency_ms"]))
    return float(np.median(values))


def normalize_original_cnn(tuning):
    """Map the prior tuned average-pool CNN into the common comparison schema."""

    arm = tuning["recommended_quality_feasible_arm"]
    return {
        "name": "original_avg_k3_tuned", "median_accuracy": arm["median_accuracy"],
        "median_balanced_accuracy": arm["median_balanced_accuracy"],
        "median_macro_f1": arm["median_macro_f1"],
        "median_critical_pr_auc": arm["median_critical_pr_auc"],
        "worst_critical_recall": arm["worst_critical_recall"],
        "median_safe_far": arm["median_safe_far"],
        "parameter_count": 1666, "estimated_macs_per_window": 50720,
        # This diagnostic belongs to the representative original CNN run and
        # is retained only for the same-host resource comparison.
        "median_cpu_latency_ms": 0.1942915,
    }


def normalize_tcn(report):
    """Extract the selected L32 TCN's three-seed validation aggregates."""

    arm = report["arms"]["b_sqrt_ce"]
    runs = [value for name, value in report["runs"].items()
            if name.startswith("b_sqrt_ce_seed")]
    if len(runs) != 3:
        raise ValueError("TCN comparison requires three L32 b_sqrt_ce seeds")
    return {
        "name": "tcn_l32_b_sqrt_ce",
        "median_accuracy": float(np.median([
            run["metrics"]["accuracy"] for run in runs])),
        "median_balanced_accuracy": arm["median_balanced_accuracy"],
        "median_macro_f1": arm["median_macro_f1"],
        "median_critical_pr_auc": arm["median_critical_pr_auc"],
        "worst_critical_recall": arm["worst_seed_critical_recall"],
        "median_safe_far": arm["median_safe_window_false_alarm_rate"],
        "parameter_count": 4050, "estimated_macs_per_window": 125952,
        "median_cpu_latency_ms": 0.6775075,
    }


def markdown(report):
    """Render quality, per-seed, and resource comparisons without cherry-picking."""

    models = (("Original tuned CNN", report["original_cnn"]),
              ("Selected multistat CNN", report["selected_cnn"]),
              ("TCN", report["tcn"]))
    lines = ["# Final Binary CNN Structure Comparison", "",
             "All quality metrics are validation-only three-seed aggregates. "
             "No IID inference or postprocessing was run.", "",
             "## Aggregate Validation Metrics", "",
             "| Metric | Original tuned CNN | Selected multistat CNN | TCN |",
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
    lines.extend(["", "## Selected CNN Per Seed", "",
                  "| Seed | Best epoch | Accuracy | Balanced acc. | Macro-F1 | "
                  "Critical PR-AUC | Critical precision | Critical recall | Safe FAR |",
                  "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for run in report["selected_cnn"]["runs"]:
        lines.append("| {} | {} | {:.6f} | {:.6f} | {:.6f} | {:.6f} | {:.6f} | "
                     "{:.6f} | {:.6f} |".format(
                         run["seed"], run["best_epoch"], run["accuracy"],
                         run["balanced_accuracy"], run["macro_f1"],
                         run["critical_pr_auc"], run["critical_precision"],
                         run["critical_recall"], run["safe_far"]))
    lines.extend(["", "## Complexity", "",
                  "| Metric | Original tuned CNN | Selected multistat CNN | TCN |",
                  "| --- | ---: | ---: | ---: |"])
    for label, field in (("Parameters", "parameter_count"),
                         ("Estimated MAC/window", "estimated_macs_per_window"),
                         ("Recorded CPU ms/window", "median_cpu_latency_ms")):
        lines.append("| {} | {} |".format(
            label, " | ".join("{:.6f}".format(item[field])
                              for _, item in models)))
    lines.extend(["", "Representative seed: `{}`; checkpoint SHA256: `{}`.".format(
        report["representative_run"]["seed"],
        report["representative_run"]["checkpoint_sha256"]), "",
        "This checkpoint is a validation-selected next-release candidate. The "
        "existing IID evaluation remains unchanged and must not be rerun.", ""])
    return "\n".join(lines)


def main():
    """Combine immutable validation reports and publish the final comparison."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage1", required=True, type=Path)
    parser.add_argument("--stage2", required=True, type=Path)
    parser.add_argument("--hparam-final", required=True, type=Path)
    parser.add_argument("--tcn-ablation", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite final structure report")
    stage1, stage2 = read_json(args.stage1), read_json(args.stage2)
    tuning, tcn_report = read_json(args.hparam_final), read_json(args.tcn_ablation)
    validate_validation_only("stage1", stage1)
    validate_validation_only("stage2", stage2)
    validate_validation_only("hyperparameter", tuning)
    if (tcn_report.get("scope") != "validation_only"
            or tcn_report.get("iid_metrics_computed") is not False):
        raise ValueError("TCN comparison is not validation-only")
    selected = next(item for item in stage2["ranking"]
                    if item["name"] == stage2["selected_candidate"])
    if not selected["feasible"]:
        raise ValueError("selected CNN structure does not pass frozen quality gates")
    selected = dict(selected)
    selected["median_cpu_latency_ms"] = median_recorded_latency(selected)
    report = {
        "schema_version": 1, "scope": "validation_only",
        "task": "safe_critical_binary", "model": "cnn",
        "iid_features_loaded": False, "iid_metrics_computed": False,
        "parameters_tuned_on_test": False, "iid_evaluation_performed": False,
        "selected_structure": selected["name"], "selected_cnn": selected,
        "original_cnn": normalize_original_cnn(tuning),
        "tcn": normalize_tcn(tcn_report),
        "representative_run": representative_run(selected),
        "inputs": {name + "_sha256": sha256_file(getattr(args, name))
                   for name in ("stage1", "stage2", "hparam_final", "tcn_ablation")},
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "final_structure.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "FINAL_STRUCTURE.md").write_text(markdown(report),
                                                        encoding="utf-8")


if __name__ == "__main__":
    main()
