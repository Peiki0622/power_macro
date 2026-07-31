#!/usr/bin/env python3
"""Freeze the median-representative binary CNN before any IID evaluation."""

from __future__ import print_function

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256_file(path):
    """Return a bounded-memory digest for one frozen artifact."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def select_representative(runs):
    """Choose an actual seed nearest median AP with deterministic quality ties."""

    median_ap = float(np.median([
        run["metrics"]["critical_pr_auc"] for run in runs]))
    selected = min(runs, key=lambda run: (
        abs(run["metrics"]["critical_pr_auc"] - median_ap),
        -run["metrics"]["macro_f1"],
        -run["metrics"]["balanced_accuracy"],
        -run["metrics"]["critical_recall"],
        run["metrics"]["safe_window_false_alarm_rate"],
        int(run["seed"])))
    return selected, median_ap


def main():
    """Bind one deployable CNN and record mandatory replacement limitations."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objective-selection", required=True, type=Path)
    parser.add_argument("--architecture-selection", required=True, type=Path)
    parser.add_argument("--policy-config", required=True, type=Path)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("refusing to overwrite frozen CNN candidate")
    objectives = json.loads(args.objective_selection.read_text(encoding="utf-8"))
    architecture = json.loads(args.architecture_selection.read_text(encoding="utf-8"))
    policy = json.loads(args.policy_config.read_text(encoding="utf-8"))
    if (objectives.get("iid_metrics_computed") is not False
            or architecture.get("iid_metrics_computed") is not False
            or objectives.get("selected_candidate") != "large_L32"
            or objectives.get("selected_arm") != "a_natural_ce"
            or policy.get("replacement_policy")
            != "cnn_replaces_tcn_before_iid_evaluation"):
        raise ValueError("CNN candidate selection differs from frozen policy")
    runs = objectives["arms"][objectives["selected_arm"]]["runs"]
    if len(runs) != 3:
        raise ValueError("selected CNN objective lacks three seed runs")
    representative, median_ap = select_representative(runs)

    # Bind caller paths back to hashes already observed inside every selected
    # training run.  This prevents a same-named config or window from being
    # substituted between validation selection and the one-shot evaluator.
    expected_windows = {run["windows_sha256"] for run in runs}
    expected_training = {run["training_config_sha256"] for run in runs}
    expected_model = {run["model_config_sha256"] for run in runs}
    if ({sha256_file(args.windows)} != expected_windows
            or {sha256_file(args.training_config)} != expected_training
            or {sha256_file(args.model_config)} != expected_model):
        raise ValueError("frozen CNN path digest differs from selected runs")
    summary = json.loads(Path(representative["training_summary"]).read_text(
        encoding="utf-8"))
    if (summary.get("model") != "cnn"
            or summary.get("normalizer", {}).get("source_split") != "train"
            or int(summary.get("window_length", -1)) != 32
            or int(summary["parameter_count"])
            >= int(policy["tcn_baseline"]["parameter_count"])
            or int(summary["estimated_macs_per_window"])
            >= int(policy["tcn_baseline"]["estimated_macs_per_window_L32"])):
        raise ValueError("representative CNN violates model/normalizer/complexity contract")

    candidate = {
        "schema_version": 1, "status": "FROZEN_VALIDATION_CANDIDATE",
        "task": "safe_critical_binary", "model": "cnn",
        "policy_id": policy["policy_id"],
        "selected_architecture": "large", "selected_arm": "a_natural_ce",
        "window_length": 32, "seed": int(representative["seed"]),
        "representative_seed_rule": (
            "closest_to_median_critical_pr_auc_then_quality_then_seed"),
        "selected_arm_median_critical_pr_auc": median_ap,
        "selection_metrics": representative["metrics"],
        "quality_floor_passed": bool(
            objectives["arms"]["a_natural_ce"]["feasible"]),
        # The user explicitly chose mandatory CNN replacement.  Freezing this
        # flag before IID ensures later test observations cannot decide whether
        # the workflow returns to TCN.
        "replacement_decision_frozen_before_iid": True,
        "replaces_model": "tcn",
        "iid_metrics_computed": False,
        "parameters_tuned_on_test": False,
        "pristine_blind_test": False,
        "rerun_authorized": False,
        "parameter_count": int(summary["parameter_count"]),
        "estimated_macs_per_window": int(summary["estimated_macs_per_window"]),
        "median_cpu_latency_ms": float(summary["median_cpu_latency_ms"]),
        "tcn_baseline": policy["tcn_baseline"],
        "checkpoint": representative["checkpoint"],
        "checkpoint_sha256": representative["checkpoint_sha256"],
        "training_summary": representative["training_summary"],
        "training_summary_sha256": representative["training_summary_sha256"],
        "validation_predictions": representative["validation_predictions"],
        "validation_predictions_sha256": representative[
            "validation_predictions_sha256"],
        "windows": str(args.windows.resolve()),
        "windows_sha256": sha256_file(args.windows),
        "training_config": str(args.training_config.resolve()),
        "training_config_sha256": sha256_file(args.training_config),
        "model_config": str(args.model_config.resolve()),
        "model_config_sha256": sha256_file(args.model_config),
        "policy_config": str(args.policy_config.resolve()),
        "policy_config_sha256": sha256_file(args.policy_config),
        "architecture_selection": str(args.architecture_selection.resolve()),
        "architecture_selection_sha256": sha256_file(args.architecture_selection),
        "objective_selection": str(args.objective_selection.resolve()),
        "objective_selection_sha256": sha256_file(args.objective_selection),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
