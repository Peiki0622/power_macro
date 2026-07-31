#!/usr/bin/env python3
"""Rank four objectives for the validation-selected binary CNN architecture."""

from __future__ import print_function

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.evaluate.summarize_binary_cnn_screen import gate_checks
from power_macro.tcn_detection.evaluate.summarize_binary_state_ablation import (
    score_predictions)


ARMS = ("a_natural_ce", "b_sqrt_ce", "c_sqrt_focal",
        "d_balanced_sampler_ce")
SEEDS = (20260725, 20260726, 20260727)


def sha256_file(path):
    """Hash one immutable objective-selection input."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rank_arms(arms):
    """Rank feasible arms first, then apply the frozen quality ordering.

    Architecture complexity is identical across objective arms, so it is not a
    tie-break here.  When every arm misses at least one quality floor, mandatory
    CNN replacement still selects the highest validation Critical PR-AUC and
    records the fallback instead of silently returning to the TCN.
    """

    feasible = [name for name, metrics in arms.items() if metrics["feasible"]]
    pool = feasible if feasible else list(arms)
    ranking = sorted(pool, key=lambda name: (
        -arms[name]["median_critical_pr_auc"],
        -arms[name]["median_macro_f1"],
        -arms[name]["median_balanced_accuracy"],
        -arms[name]["worst_seed_critical_recall"],
        arms[name]["median_safe_window_false_alarm_rate"], name))
    return ranking, ("quality_feasible_arm" if feasible
                     else "mandatory_cnn_quality_fallback")


def collect_run(run_dir, arm, seed, expected_length):
    """Validate and score one persisted development-only CNN run."""

    summary_path = run_dir / "training_summary.json"
    predictions_path = run_dir / "validation_predictions.csv"
    checkpoint_path = run_dir / "best_checkpoint.pt"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows, metrics = score_predictions(predictions_path)
    if (summary.get("model") != "cnn"
            or int(summary.get("window_length", -1)) != int(expected_length)
            or summary.get("iid_features_loaded") is not False
            or summary.get("checkpoint_selection_metric") != "critical_pr_auc"):
        raise ValueError("objective run crossed model/history/IID contract")
    return {
        "arm": arm, "seed": int(seed), "prediction_count": len(rows),
        "metrics": metrics, "run_dir": str(run_dir.resolve()),
        "best_epoch": int(summary["best_epoch"]),
        "parameter_count": int(summary["parameter_count"]),
        "estimated_macs_per_window": int(summary["estimated_macs_per_window"]),
        "median_cpu_latency_ms": float(summary["median_cpu_latency_ms"]),
        "checkpoint": str(checkpoint_path.resolve()),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "training_summary": str(summary_path.resolve()),
        "training_summary_sha256": sha256_file(summary_path),
        "validation_predictions": str(predictions_path.resolve()),
        "validation_predictions_sha256": sha256_file(predictions_path),
        "windows_sha256": summary["windows_sha256"],
        "training_config_sha256": summary["training_config_sha256"],
        "model_config_sha256": summary["model_config_sha256"],
    }


def markdown_report(report):
    """Render one compact but complete objective comparison table."""

    lines = ["# Binary CNN Objective Selection", "",
             "Architecture/history: `{}`. This report is validation-only.".format(
                 report["selected_candidate"]), "",
             "| Arm | Critical PR-AUC | Accuracy | Balanced accuracy | Macro-F1 | "
             "Worst recall | Safe FAR | Feasible |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for name in ARMS:
        item = report["arms"][name]
        display = dict(item)
        display["feasible"] = "yes" if item["feasible"] else "no"
        lines.append(
            "| {name} | {median_critical_pr_auc:.6f} | {median_accuracy:.6f} | "
            "{median_balanced_accuracy:.6f} | {median_macro_f1:.6f} | "
            "{worst_seed_critical_recall:.6f} | "
            "{median_safe_window_false_alarm_rate:.6f} | {feasible} |".format(
                name=name, **display))
    lines.extend(["", "Selected `{}` using `{}`.".format(
        report["selected_arm"], report["selection_mode"]), ""])
    return "\n".join(lines)


def write_atomic(path, text):
    """Atomically publish one objective report."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def main():
    """Merge three reused and nine new runs into the frozen four-arm decision."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen-dir", required=True, type=Path)
    parser.add_argument("--ablation-dir", required=True, type=Path)
    parser.add_argument("--architecture-selection", required=True, type=Path)
    parser.add_argument("--policy-config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.markdown_output.exists():
        raise FileExistsError("refusing to overwrite CNN objective selection")
    architecture = json.loads(args.architecture_selection.read_text(encoding="utf-8"))
    policy = json.loads(args.policy_config.read_text(encoding="utf-8"))
    selected = architecture["selected"]
    selected_architecture = selected["architecture"]
    selected_length = int(selected["window_length"])
    if (architecture.get("iid_metrics_computed") is not False
            or selected["name"] != "large_L32"):
        raise ValueError("objective stage requires the frozen large_L32 selection")

    screen_manifest_path = args.screen_dir / "screen_manifest.json"
    objective_manifest_path = args.ablation_dir / "ablation_manifest.json"
    screen_manifest = json.loads(screen_manifest_path.read_text(encoding="utf-8"))
    objective_manifest = json.loads(objective_manifest_path.read_text(encoding="utf-8"))
    if (screen_manifest.get("status") != "PASS"
            or screen_manifest.get("iid_metrics_computed") is not False
            or objective_manifest.get("status") != "PASS"
            or objective_manifest.get("iid_metrics_computed") is not False
            or objective_manifest.get("model") != "cnn"):
        raise ValueError("objective inputs are not complete validation-only CNN runs")

    grouped = defaultdict(list)
    screen_jobs = [job for job in screen_manifest["jobs"]
                   if job["architecture"] == selected_architecture
                   and int(job["window_length"]) == selected_length]
    if len(screen_jobs) != 3:
        raise ValueError("selected CNN screen cell lacks three sqrt-CE seeds")
    for job in screen_jobs:
        grouped["b_sqrt_ce"].append(collect_run(
            args.screen_dir / job["output_dir"], "b_sqrt_ce", job["seed"],
            selected_length))
    if len(objective_manifest.get("jobs", [])) != 9:
        raise ValueError("objective supplement must contain exactly nine jobs")
    for job in objective_manifest["jobs"]:
        if job["arm"] == "b_sqrt_ce" or job["status"] != "PASS":
            raise ValueError("objective supplement contains an unexpected arm")
        grouped[job["arm"]].append(collect_run(
            args.ablation_dir / job["output_dir"], job["arm"], job["seed"],
            selected_length))

    arms = {}
    for arm in ARMS:
        runs = sorted(grouped[arm], key=lambda item: item["seed"])
        if tuple(run["seed"] for run in runs) != SEEDS:
            raise ValueError("each CNN objective must contain the three frozen seeds")
        candidate = {
            "median_critical_pr_auc": float(np.median([
                run["metrics"]["critical_pr_auc"] for run in runs])),
            "critical_pr_auc_variance": float(np.var([
                run["metrics"]["critical_pr_auc"] for run in runs])),
            "median_accuracy": float(np.median([
                run["metrics"]["accuracy"] for run in runs])),
            "median_balanced_accuracy": float(np.median([
                run["metrics"]["balanced_accuracy"] for run in runs])),
            "median_macro_f1": float(np.median([
                run["metrics"]["macro_f1"] for run in runs])),
            "worst_seed_critical_recall": float(min(
                run["metrics"]["critical_recall"] for run in runs)),
            "median_safe_window_false_alarm_rate": float(np.median([
                run["metrics"]["safe_window_false_alarm_rate"] for run in runs])),
            "runs": runs,
        }
        candidate["gate_checks"] = gate_checks(
            candidate, policy["quality_feasibility"])
        candidate["feasible"] = all(candidate["gate_checks"].values())
        arms[arm] = candidate
    ranking, selection_mode = rank_arms(arms)
    report = {
        "schema_version": 1, "task": "safe_critical_binary",
        "model": "cnn", "scope": "validation_only",
        "iid_metrics_computed": False, "parameters_tuned_on_test": False,
        "selected_candidate": selected["name"],
        "quality_feasibility": policy["quality_feasibility"],
        "architecture_selection_sha256": sha256_file(args.architecture_selection),
        "screen_manifest_sha256": sha256_file(screen_manifest_path),
        "objective_manifest_sha256": sha256_file(objective_manifest_path),
        "arms": arms, "ranking": ranking,
        "selection_mode": selection_mode, "selected_arm": ranking[0],
    }
    # Fully render both serializations before publishing either path.  A schema
    # or formatting error must not expose a machine report without its required
    # human-readable decision table.
    json_text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown_text = markdown_report(report)
    write_atomic(args.output, json_text)
    write_atomic(args.markdown_output, markdown_text)


if __name__ == "__main__":
    main()
