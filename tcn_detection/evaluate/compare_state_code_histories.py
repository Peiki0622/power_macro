#!/usr/bin/env python3
"""Compare validation history lengths and freeze one code-state checkpoint."""

from __future__ import print_function

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.evaluate.metrics import window_metrics
from power_macro.tcn_detection.evaluate.summarize_state_code_ablation import (
    RAW_GATES, gate_checks, read_validation_predictions)


SEEDS = (20260725, 20260726, 20260727)
SELECTED_ARM = "b_direct_sqrt"


def sha256_file(path):
    """Hash one immutable model, input, or prediction artifact."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def selected_jobs(directory, length):
    """Return exactly three successful B-arm jobs for one history length."""

    manifest_path = Path(directory) / "ablation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    jobs = [job for job in manifest["jobs"] if job["arm"] == SELECTED_ARM]
    if (manifest.get("status") != "PASS" or len(jobs) != 3
            or {int(job["seed"]) for job in jobs} != set(SEEDS)
            or any(job["status"] != "PASS" for job in jobs)):
        raise ValueError("L{} does not have three successful selected-arm seeds".format(length))
    return manifest_path, sorted(jobs, key=lambda job: int(job["seed"]))


def score_run(run_dir, job, length):
    """Recompute one run's validation metrics from persisted probabilities."""

    summary_path = run_dir / job["output_dir"] / "training_summary.json"
    checkpoint_path = run_dir / job["output_dir"] / "best_checkpoint.pt"
    prediction_path = run_dir / job["output_dir"] / "validation_predictions.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if int(summary["window_length"]) != int(length):
        raise ValueError("training summary history length mismatch")
    rows = read_validation_predictions(prediction_path)
    labels = np.asarray([int(row["target_label"]) for row in rows])
    predictions = np.asarray([int(row["prediction"]) for row in rows])
    probabilities = np.asarray([[float(row["prob_safe"]), float(row["prob_warning"]),
                                 float(row["prob_critical"])] for row in rows])
    report = window_metrics(labels, predictions, probabilities)
    risk_mask = labels >= 1
    metrics = {
        "accuracy": report["accuracy"],
        "balanced_accuracy": report["balanced_accuracy"],
        "macro_f1": report["macro_f1"],
        "weighted_f1": report["weighted_f1"],
        "risk_recall": float(np.mean(predictions[risk_mask] >= 1)),
        "warning_recall": report["per_class"]["1"]["recall"],
        "critical_recall": report["per_class"]["2"]["recall"],
        "safe_recall": report["per_class"]["0"]["recall"],
        "safe_window_false_alarm_rate": report["safe_window_false_alarm_rate"],
        "macro_pr_auc_ovr": report["macro_pr_auc_ovr"],
        "macro_roc_auc_ovr": report["macro_roc_auc_ovr"],
        "log_loss": report["log_loss"],
        "multiclass_brier_score": report["multiclass_brier_score"],
    }
    checks = gate_checks(metrics)
    return {
        "seed": int(job["seed"]), "length": int(length),
        "prediction_count": len(rows), "metrics": metrics,
        "gate_checks": checks, "passes_all_raw_gates": all(checks.values()),
        "run_dir": str((run_dir / job["output_dir"]).resolve()),
        "checkpoint": str(checkpoint_path.resolve()),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "training_summary": str(summary_path.resolve()),
        "training_summary_sha256": sha256_file(summary_path),
        "validation_predictions": str(prediction_path.resolve()),
        "validation_predictions_sha256": sha256_file(prediction_path),
    }


def aggregate(runs):
    """Aggregate all scalar metrics with population mean/std and worst seed."""

    names = tuple(runs[0]["metrics"])
    return {
        "metrics": {
            name: {"mean": float(np.mean([run["metrics"][name] for run in runs])),
                   "std": float(np.std([run["metrics"][name] for run in runs]))}
            for name in names
        },
        "all_seeds_pass_raw_gates": all(run["passes_all_raw_gates"] for run in runs),
    }


def main():
    """Write the comparison and immutable selected-checkpoint manifest."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--l8-dir", required=True, type=Path)
    parser.add_argument("--l16-dir", required=True, type=Path)
    parser.add_argument("--l32-dir", required=True, type=Path)
    parser.add_argument("--windows-dir", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--frozen-candidate", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.frozen_candidate.exists():
        raise ValueError("refusing to overwrite history comparison or frozen candidate")

    directories = {8: args.l8_dir, 16: args.l16_dir, 32: args.l32_dir}
    runs_by_length = {}
    manifest_hashes = {}
    for length, directory in directories.items():
        manifest_path, jobs = selected_jobs(directory, length)
        runs_by_length[length] = [score_run(directory, job, length) for job in jobs]
        manifest_hashes[str(length)] = sha256_file(manifest_path)
    aggregates = {str(length): aggregate(runs)
                  for length, runs in runs_by_length.items()}
    ranking = sorted((8, 16, 32), key=lambda length: (
        -aggregates[str(length)]["metrics"]["macro_f1"]["mean"],
        -aggregates[str(length)]["metrics"]["balanced_accuracy"]["mean"],
        -aggregates[str(length)]["metrics"]["risk_recall"]["mean"],
        aggregates[str(length)]["metrics"]["safe_window_false_alarm_rate"]["mean"],
        length))
    selected_length = ranking[0]
    selected_runs = runs_by_length[selected_length]
    median_f1 = float(np.median([run["metrics"]["macro_f1"] for run in selected_runs]))
    # Select the seed closest to the median validation outcome.  This yields a
    # real deployable checkpoint while avoiding best-seed cherry-picking.
    representative = min(selected_runs, key=lambda run: (
        abs(run["metrics"]["macro_f1"] - median_f1),
        -run["metrics"]["balanced_accuracy"], run["seed"]))

    report = {
        "schema_version": 1, "scope": "validation_only",
        "iid_ood_metrics_computed": False, "selected_arm": SELECTED_ARM,
        "raw_gates": {name: {"operator": value[0], "threshold": value[1]}
                      for name, value in RAW_GATES.items()},
        "source_manifest_sha256": manifest_hashes,
        "runs": {str(length): runs for length, runs in runs_by_length.items()},
        "lengths": aggregates, "ranking": ranking,
        "selected_length": selected_length,
        "representative_seed_rule": "closest_to_median_macro_f1",
        "selected_seed": representative["seed"],
    }
    frozen = {
        "schema_version": 1, "status": "FROZEN_VALIDATION_CANDIDATE",
        "task": "same_sample_current_state_monitoring",
        "iid_ood_metrics_computed": False,
        "selection_report": str(args.output.resolve()),
        "selected_arm": SELECTED_ARM, "window_length": selected_length,
        "seed": representative["seed"],
        "selection_metrics": representative["metrics"],
        "selection_gate_checks": representative["gate_checks"],
        "checkpoint": representative["checkpoint"],
        "checkpoint_sha256": representative["checkpoint_sha256"],
        "training_summary": representative["training_summary"],
        "training_summary_sha256": representative["training_summary_sha256"],
        "validation_predictions_sha256": representative["validation_predictions_sha256"],
        "windows": str((args.windows_dir / "windows_L{}.csv".format(selected_length)).resolve()),
        "windows_sha256": sha256_file(args.windows_dir / "windows_L{}.csv".format(selected_length)),
        "training_config": str(args.training_config.resolve()),
        "training_config_sha256": sha256_file(args.training_config),
        "model_config": str(args.model_config.resolve()),
        "model_config_sha256": sha256_file(args.model_config),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for path, payload in ((args.output, report), (args.frozen_candidate, frozen)):
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
        temporary.replace(path)


if __name__ == "__main__":
    main()
