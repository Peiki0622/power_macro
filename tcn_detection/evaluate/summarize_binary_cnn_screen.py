#!/usr/bin/env python3
"""Select a CNN architecture/history from the frozen validation-only screen."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.evaluate.binary_metrics import binary_window_metrics


EXPECTED_SEEDS = (20260725, 20260726, 20260727)


def sha256_file(path):
    """Hash an immutable screen input using bounded memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_validation_metrics(path):
    """Recompute complete metrics from one validation prediction artifact."""

    labels, predictions, probabilities = [], [], []
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["split"] != "validation":
                raise ValueError("CNN screen predictions must be validation-only")
            labels.append(int(row["target_label"]))
            predictions.append(int(row["prediction"]))
            probabilities.append([float(row["prob_safe"]),
                                  float(row["prob_critical"])])
    return binary_window_metrics(
        np.asarray(labels), np.asarray(predictions), np.asarray(probabilities))


def gate_checks(candidate, gates):
    """Evaluate the predeclared quality floor without rounded values."""

    return {
        "critical_pr_auc": candidate["median_critical_pr_auc"]
        >= float(gates["median_critical_pr_auc_min"]),
        "accuracy": candidate["median_accuracy"]
        >= float(gates["median_accuracy_min"]),
        "balanced_accuracy": candidate["median_balanced_accuracy"]
        >= float(gates["median_balanced_accuracy_min"]),
        "macro_f1": candidate["median_macro_f1"]
        >= float(gates["median_macro_f1_min"]),
        "critical_recall": candidate["worst_seed_critical_recall"]
        >= float(gates["worst_seed_critical_recall_min"]),
        "safe_far": candidate["median_safe_window_false_alarm_rate"]
        <= float(gates["median_safe_window_false_alarm_rate_max"]),
    }


def select_candidate(candidates):
    """Apply the frozen feasible/fallback order and return selection metadata.

    MAC and parameter count are deterministic architecture properties.  Median
    latency is measured independently per seed and is used only after MAC and
    parameters, limiting host jitter's influence.  If no candidate preserves
    the quality floor, the user-approved mandatory replacement policy selects
    the best CNN by validation quality rather than reverting to TCN.
    """

    feasible = [candidate for candidate in candidates if candidate["feasible"]]
    if feasible:
        selected = min(feasible, key=lambda item: (
            item["estimated_macs_per_window"], item["parameter_count"],
            item["median_cpu_latency_ms"], -item["median_critical_pr_auc"],
            item["name"]))
        return selected, "lowest_complexity_within_quality_floor"
    selected = min(candidates, key=lambda item: (
        -item["median_critical_pr_auc"],
        -item["worst_seed_critical_recall"],
        item["median_safe_window_false_alarm_rate"],
        item["estimated_macs_per_window"], item["name"]))
    return selected, "mandatory_cnn_quality_fallback"


def markdown_report(report):
    """Render the complete nine-candidate decision table."""

    lines = ["# Binary CNN Architecture/History Selection", "",
             "This report uses train/validation artifacts only. IID metrics "
             "were not computed.", "",
             "| Candidate | Parameters | MACs | CPU ms | Critical PR-AUC | "
             "Accuracy | Balanced accuracy | Macro-F1 | Worst recall | Safe FAR | Feasible |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for item in sorted(report["candidates"], key=lambda value: (
            value["window_length"], value["architecture"])):
        lines.append(
            "| {name} | {parameter_count} | {estimated_macs_per_window} | "
            "{median_cpu_latency_ms:.6f} | {median_critical_pr_auc:.6f} | "
            "{median_accuracy:.6f} | {median_balanced_accuracy:.6f} | "
            "{median_macro_f1:.6f} | {worst_seed_critical_recall:.6f} | "
            "{median_safe_window_false_alarm_rate:.6f} | {feasible} |".format(
                **dict(item, feasible="yes" if item["feasible"] else "no")))
    selected = report["selected"]
    lines.extend(["", "Selected `{}` using `{}`.".format(
        selected["name"], report["selection_mode"]), ""])
    return "\n".join(lines)


def write_text_atomic(path, text):
    """Write one report through a sibling temporary file."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def main():
    """Validate all 27 jobs, aggregate nine cells, and publish the decision."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen-dir", required=True, type=Path)
    parser.add_argument("--policy-config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.markdown_output.exists():
        raise FileExistsError("refusing to overwrite CNN screen selection")
    policy = json.loads(args.policy_config.read_text(encoding="utf-8"))
    manifest_path = args.screen_dir / "screen_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("status") != "PASS"
            or manifest.get("iid_metrics_computed") is not False
            or len(manifest.get("jobs", [])) != 27
            or manifest.get("policy_config_sha256") != sha256_file(args.policy_config)):
        raise ValueError("CNN screen manifest is incomplete or crossed IID boundary")

    grouped = defaultdict(list)
    for job in manifest["jobs"]:
        if job.get("status") != "PASS" or job.get("training_arm") != "b_sqrt_ce":
            raise ValueError("CNN screen contains a failed or unexpected job")
        run_dir = args.screen_dir / job["output_dir"]
        summary = json.loads((run_dir / "training_summary.json").read_text(
            encoding="utf-8"))
        if (summary.get("model") != "cnn"
                or summary.get("iid_features_loaded") is not False
                or summary.get("windows_sha256") != job["windows_sha256"]
                or summary.get("model_config_sha256") != job["model_config_sha256"]
                or summary.get("training_config_sha256")
                != job["training_config_sha256"]):
            raise ValueError("CNN job summary differs from screen manifest")
        metrics = read_validation_metrics(run_dir / "validation_predictions.csv")
        grouped[(job["architecture"], int(job["window_length"]))].append({
            "seed": int(job["seed"]), "metrics": metrics,
            "parameter_count": int(summary["parameter_count"]),
            "estimated_macs_per_window": int(summary["estimated_macs_per_window"]),
            "median_cpu_latency_ms": float(summary["median_cpu_latency_ms"]),
            "run_dir": str(run_dir.resolve()),
            "checkpoint_sha256": sha256_file(run_dir / "best_checkpoint.pt"),
        })

    candidates = []
    gates = policy["quality_feasibility"]
    for (architecture, length), runs in sorted(grouped.items()):
        if tuple(sorted(run["seed"] for run in runs)) != EXPECTED_SEEDS:
            raise ValueError("CNN candidate does not contain the three frozen seeds")
        parameters = {run["parameter_count"] for run in runs}
        macs = {run["estimated_macs_per_window"] for run in runs}
        if len(parameters) != 1 or len(macs) != 1:
            raise ValueError("complexity changed across seeds for one CNN candidate")
        candidate = {
            "name": "{}_L{}".format(architecture, length),
            "architecture": architecture, "window_length": length,
            "parameter_count": parameters.pop(),
            "estimated_macs_per_window": macs.pop(),
            "median_cpu_latency_ms": float(np.median(
                [run["median_cpu_latency_ms"] for run in runs])),
            "median_critical_pr_auc": float(np.median(
                [run["metrics"]["critical_pr_auc"] for run in runs])),
            "critical_pr_auc_variance": float(np.var(
                [run["metrics"]["critical_pr_auc"] for run in runs])),
            "median_accuracy": float(np.median(
                [run["metrics"]["accuracy"] for run in runs])),
            "median_balanced_accuracy": float(np.median(
                [run["metrics"]["balanced_accuracy"] for run in runs])),
            "median_macro_f1": float(np.median(
                [run["metrics"]["macro_f1"] for run in runs])),
            "worst_seed_critical_recall": float(min(
                run["metrics"]["critical_recall"] for run in runs)),
            "median_safe_window_false_alarm_rate": float(np.median(
                [run["metrics"]["safe_window_false_alarm_rate"] for run in runs])),
            "runs": sorted(runs, key=lambda item: item["seed"]),
        }
        candidate["gate_checks"] = gate_checks(candidate, gates)
        candidate["feasible"] = all(candidate["gate_checks"].values())
        candidates.append(candidate)
    if len(candidates) != 9:
        raise ValueError("CNN screen must aggregate exactly nine candidates")
    selected, selection_mode = select_candidate(candidates)
    report = {
        "schema_version": 1, "task": "safe_critical_binary",
        "model": "cnn", "scope": "validation_only",
        "iid_metrics_computed": False, "parameters_tuned_on_test": False,
        "policy_config_sha256": sha256_file(args.policy_config),
        "screen_manifest_sha256": sha256_file(manifest_path),
        "quality_feasibility": gates, "selection_mode": selection_mode,
        "candidates": candidates, "selected": selected,
    }
    write_text_atomic(args.output, json.dumps(report, indent=2, sort_keys=True) + "\n")
    write_text_atomic(args.markdown_output, markdown_report(report))


if __name__ == "__main__":
    main()
