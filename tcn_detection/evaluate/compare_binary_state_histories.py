#!/usr/bin/env python3
"""Compare binary validation histories and freeze one representative checkpoint."""

from __future__ import print_function

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.evaluate.summarize_binary_state_ablation import (
    score_predictions)


SEEDS = (20260725, 20260726, 20260727)


def sha256_file(path):
    """Hash one immutable selection input or model artifact."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def selected_jobs(directory, arm, length):
    """Return exactly three successful jobs for one selected arm and length."""

    manifest_path = Path(directory) / "ablation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    jobs = [job for job in manifest["jobs"] if job["arm"] == arm]
    if (manifest.get("status") != "PASS" or manifest.get("iid_metrics_computed") is not False
            or len(jobs) != 3 or {int(job["seed"]) for job in jobs} != set(SEEDS)
            or any(job["status"] != "PASS" for job in jobs)):
        raise ValueError("L{} lacks three successful selected-arm runs".format(length))
    return manifest_path, sorted(jobs, key=lambda job: int(job["seed"]))


def score_run(directory, job, length):
    """Recompute validation metrics and bind every deployable artifact hash."""

    run_dir = Path(directory) / job["output_dir"]
    summary_path = run_dir / "training_summary.json"
    prediction_path = run_dir / "validation_predictions.csv"
    checkpoint_path = run_dir / "best_checkpoint.pt"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if (int(summary["window_length"]) != int(length)
            or summary["checkpoint_selection_metric"] != "critical_pr_auc"
            or summary.get("iid_features_loaded") is not False):
        raise ValueError("binary training summary crossed history/split contract")
    rows, metrics = score_predictions(prediction_path)
    return {
        "seed": int(job["seed"]), "length": int(length),
        "prediction_count": len(rows), "metrics": metrics,
        "run_dir": str(run_dir.resolve()),
        "checkpoint": str(checkpoint_path.resolve()),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "training_summary": str(summary_path.resolve()),
        "training_summary_sha256": sha256_file(summary_path),
        "validation_predictions": str(prediction_path.resolve()),
        "validation_predictions_sha256": sha256_file(prediction_path),
    }


def aggregate(runs):
    """Return robust selection statistics across the three fixed seeds."""

    critical_ap = np.asarray([run["metrics"]["critical_pr_auc"] for run in runs])
    return {
        "median_critical_pr_auc": float(np.median(critical_ap)),
        "critical_pr_auc_variance": float(np.var(critical_ap)),
        "median_macro_f1": float(np.median([
            run["metrics"]["macro_f1"] for run in runs])),
        "median_balanced_accuracy": float(np.median([
            run["metrics"]["balanced_accuracy"] for run in runs])),
        "worst_seed_critical_recall": float(min(
            run["metrics"]["critical_recall"] for run in runs)),
        "median_safe_window_false_alarm_rate": float(np.median([
            run["metrics"]["safe_window_false_alarm_rate"] for run in runs])),
    }


def main():
    """Rank lengths and atomically freeze the median-representative model."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--l8-dir", required=True, type=Path)
    parser.add_argument("--l16-dir", required=True, type=Path)
    parser.add_argument("--l32-dir", required=True, type=Path)
    parser.add_argument("--l32-summary", required=True, type=Path)
    parser.add_argument("--windows-dir", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--frozen-candidate", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.frozen_candidate.exists():
        raise FileExistsError("refusing to overwrite binary history/frozen candidate")
    l32_summary = json.loads(args.l32_summary.read_text(encoding="utf-8"))
    selected_arm = l32_summary["selected_arm"]
    if l32_summary.get("iid_metrics_computed") is not False:
        raise ValueError("L32 arm selection crossed the IID boundary")
    directories = {8: args.l8_dir, 16: args.l16_dir, 32: args.l32_dir}
    runs_by_length, manifest_hashes = {}, {}
    for length, directory in directories.items():
        manifest_path, jobs = selected_jobs(directory, selected_arm, length)
        runs_by_length[length] = [score_run(directory, job, length) for job in jobs]
        manifest_hashes[str(length)] = sha256_file(manifest_path)
    aggregates = {str(length): aggregate(runs)
                  for length, runs in runs_by_length.items()}
    ranking = sorted((8, 16, 32), key=lambda length: (
        -aggregates[str(length)]["median_critical_pr_auc"],
        -aggregates[str(length)]["median_macro_f1"],
        -aggregates[str(length)]["worst_seed_critical_recall"],
        aggregates[str(length)]["median_safe_window_false_alarm_rate"],
        length))
    selected_length = ranking[0]
    selected_runs = runs_by_length[selected_length]
    median_ap = aggregates[str(selected_length)]["median_critical_pr_auc"]
    # Select an actual checkpoint nearest the median AP.  Subsequent tie-breaks
    # favor validation quality and stable seed order, never the best AP alone.
    representative = min(selected_runs, key=lambda run: (
        abs(run["metrics"]["critical_pr_auc"] - median_ap),
        -run["metrics"]["macro_f1"],
        -run["metrics"]["critical_recall"], run["seed"]))
    report = {
        "schema_version": 1, "scope": "validation_only",
        "iid_metrics_computed": False, "selected_arm": selected_arm,
        "source_manifest_sha256": manifest_hashes,
        "runs": {str(length): runs for length, runs in runs_by_length.items()},
        "lengths": aggregates, "ranking": ranking,
        "selected_length": selected_length,
        "representative_seed_rule": "closest_to_median_critical_pr_auc",
        "selected_seed": representative["seed"],
    }
    training_config = Path(next(
        job["training_config"] for job in json.loads(
            (directories[selected_length] / "ablation_manifest.json").read_text())["jobs"]
        if job["arm"] == selected_arm))
    window_path = args.windows_dir / "windows_L{}.csv".format(selected_length)
    frozen = {
        "schema_version": 1, "status": "FROZEN_VALIDATION_CANDIDATE",
        "task": "safe_critical_binary", "iid_metrics_computed": False,
        "parameters_tuned_on_test": False,
        "selection_report": str(args.output.resolve()),
        "selected_arm": selected_arm, "window_length": selected_length,
        "seed": representative["seed"],
        "selection_metrics": representative["metrics"],
        "checkpoint": representative["checkpoint"],
        "checkpoint_sha256": representative["checkpoint_sha256"],
        "training_summary": representative["training_summary"],
        "training_summary_sha256": representative["training_summary_sha256"],
        "validation_predictions": representative["validation_predictions"],
        "validation_predictions_sha256": representative["validation_predictions_sha256"],
        "windows": str(window_path.resolve()),
        "windows_sha256": sha256_file(window_path),
        "training_config": str(training_config.resolve()),
        "training_config_sha256": sha256_file(training_config),
        "model_config": str(args.model_config.resolve()),
        "model_config_sha256": sha256_file(args.model_config),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for path, payload in ((args.output, report), (args.frozen_candidate, frozen)):
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
        temporary.replace(path)


if __name__ == "__main__":
    main()
