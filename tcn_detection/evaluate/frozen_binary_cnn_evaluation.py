#!/usr/bin/env python3
"""Run the single authorized IID evaluation for the frozen binary 1D-CNN.

This evaluator is deliberately release-specific.  Its embedded digests bind
the command to the exact validation-selected CNN candidate, postprocessor, and
corpus.  IID rows are not loaded until every selection artifact has passed its
integrity and validation-only checks, and the output directory is published by
one atomic rename so a partial evaluation cannot look like a completed release.
"""

from __future__ import print_function

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.dataset.model_data import (
    apply_normalizer, load_window_table)
from power_macro.tcn_detection.evaluate.binary_postprocess import apply_detector
from power_macro.tcn_detection.evaluate.frozen_binary_state_evaluation import (
    benchmark_detector, load_iid_corpus, prediction_rows, read_json, score_rows,
    sha256_file, write_predictions)
from power_macro.tcn_detection.evaluate.metrics import hard_pair_metrics
from power_macro.tcn_detection.train.common import build_classifier, configure_cpu
from power_macro.tcn_detection.train.train_classifier import predict


# These four digests form the top-level release boundary.  The candidate
# manifest recursively binds the checkpoint and all model-selection evidence;
# the remaining constants bind the independently produced postprocessor and
# the unchanged 240-trace corpus.
RELEASE_DIGESTS = {
    "candidate_manifest": "1753347ce4c9755204fb7c13c7763efbc937d6bc759730a6ae71cd37e8308476",
    "postprocess_report": "f5c3a504775fd8edf039a8f48585fd8d9c88373fef78fb0e9189ee32d00edacc",
    "postprocess_config": "a235b0406e0f7c4620e837ccd342d8d560199c3a8b18933c6a193cbf8ea5b4fe",
    "corpus": "029ad57b410210b1f5b27ca75aa70569634c82a6791113b52affe7a10a686875",
}
EXPECTED_TRACE_COUNT = 48
EXPECTED_WINDOW_COUNT = 22512


def verify_frozen_inputs(args):
    """Verify every validation-frozen artifact before parsing any IID feature.

    The candidate owns hashes for both executable inputs and selection
    evidence.  Rechecking all of them matters because an unchanged checkpoint
    alone would not prove that the architecture, objective, and detector were
    selected without consulting IID results.
    """

    release_paths = {
        "candidate_manifest": args.candidate_manifest,
        "postprocess_report": args.postprocess_report,
        "postprocess_config": args.postprocess_config,
        "corpus": args.corpus,
    }
    for name, path in release_paths.items():
        if sha256_file(path) != RELEASE_DIGESTS[name]:
            raise ValueError("frozen CNN release digest mismatch: {}".format(name))

    candidate = read_json(args.candidate_manifest)
    report = read_json(args.postprocess_report)
    detector = read_json(args.postprocess_config)

    # Each command-line path is paired with the digest recorded at freeze time.
    # Explicit paths keep the invocation reproducible, while digest comparison
    # prevents a caller from substituting a same-named file in another folder.
    candidate_artifacts = {
        "checkpoint": (args.checkpoint, "checkpoint_sha256"),
        "windows": (args.windows, "windows_sha256"),
        "training_config": (args.training_config, "training_config_sha256"),
        "model_config": (args.model_config, "model_config_sha256"),
        "training_summary": (args.training_summary, "training_summary_sha256"),
        "validation_predictions": (
            args.validation_predictions, "validation_predictions_sha256"),
        "policy_config": (args.policy_config, "policy_config_sha256"),
        "architecture_selection": (
            args.architecture_selection, "architecture_selection_sha256"),
        "objective_selection": (
            args.objective_selection, "objective_selection_sha256"),
    }
    for name, (path, digest_key) in candidate_artifacts.items():
        if sha256_file(path) != candidate.get(digest_key):
            raise ValueError("candidate-owned digest mismatch: {}".format(name))

    architecture = read_json(args.architecture_selection)
    objective = read_json(args.objective_selection)
    validation_only_reports = (architecture, objective, report)
    if any(item.get("scope") != "validation_only"
           or item.get("iid_metrics_computed") is not False
           or item.get("parameters_tuned_on_test") is not False
           for item in validation_only_reports):
        raise ValueError("selection evidence crossed the validation-only boundary")

    # These exact choices were frozen before IID.  Checking both candidate and
    # source reports catches a manifest/report mismatch even when each file is
    # independently well-formed.
    if (candidate.get("status") != "FROZEN_VALIDATION_CANDIDATE"
            or candidate.get("task") != "safe_critical_binary"
            or candidate.get("model") != "cnn"
            or candidate.get("selected_architecture") != "large"
            or candidate.get("selected_arm") != "a_natural_ce"
            or candidate.get("replacement_decision_frozen_before_iid") is not True
            or candidate.get("replaces_model") != "tcn"
            or candidate.get("iid_metrics_computed") is not False
            or candidate.get("parameters_tuned_on_test") is not False
            or candidate.get("rerun_authorized") is not False
            or objective.get("selected_candidate") != "large_L32"
            or objective.get("selected_arm") != "a_natural_ce"):
        raise ValueError("CNN candidate differs from the pre-IID replacement decision")
    if (report.get("candidate_manifest_sha256")
            != RELEASE_DIGESTS["candidate_manifest"]
            or report.get("final_config") != detector):
        raise ValueError("postprocessor is not bound to the frozen CNN candidate")
    return candidate, report, detector


def validate_checkpoint(checkpoint, candidate, model_config):
    """Reject checkpoints outside the one-channel, two-class frozen CNN contract."""

    expected_names = {"0": "Safe", "1": "Critical"}
    if (checkpoint.get("task") != "safe_critical_binary"
            or checkpoint.get("model") != "cnn"
            or checkpoint.get("model_config") != model_config
            or int(model_config.get("input_channels", -1)) != 1
            or int(model_config.get("class_count", -1)) != 2
            or model_config.get("class_names") != expected_names
            or model_config.get("feature_contract")
            != "normalized_sensor_code_only"
            or model_config.get("target_contract") != "warning_merged_into_safe"
            or int(checkpoint.get("window_length", -1))
            != int(candidate["window_length"])
            or int(checkpoint.get("seed", -1)) != int(candidate["seed"])):
        raise ValueError("checkpoint is not the frozen one-channel binary CNN")
    normalizer = checkpoint.get("normalizer", {})
    means = normalizer.get("mean", [])
    standard_deviations = normalizer.get("std", [])
    if (normalizer.get("source_split") != "train"
            or int(normalizer.get("window_length", -1))
            != int(candidate["window_length"])
            # The persisted normalizer schema represents channel count through
            # vector length rather than a separate ``feature_channels`` key.
            # Requiring one finite mean and one finite positive deviation binds
            # it to the raw-code-only input without inventing a new field.
            or len(means) != 1 or len(standard_deviations) != 1
            or not np.isfinite(float(means[0]))
            or not np.isfinite(float(standard_deviations[0]))
            or float(standard_deviations[0]) <= 0.0):
        raise ValueError("checkpoint does not contain the train-only CNN normalizer")


def parse_args():
    """Parse all frozen paths explicitly so the release command is auditable."""

    parser = argparse.ArgumentParser(description=__doc__)
    for option in (
            "windows", "checkpoint", "training-config", "model-config",
            "training-summary", "validation-predictions", "policy-config",
            "architecture-selection", "objective-selection",
            "candidate-manifest", "postprocess-report", "postprocess-config",
            "corpus", "output-dir"):
        parser.add_argument("--" + option, required=True, type=Path)
    return parser.parse_args()


def main():
    """Evaluate the frozen CNN once and atomically publish complete evidence."""

    args = parse_args()
    # Refusing an existing path is the mechanical guard against accidentally
    # reusing IID observations or overwriting the successful one-shot result.
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite the one-shot CNN IID result")
    candidate, postprocess_report, postprocess_config = verify_frozen_inputs(args)
    training_config = read_json(args.training_config)
    model_config = read_json(args.model_config)
    configure_cpu(candidate["seed"], training_config["cpu_threads_per_process"])
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    validate_checkpoint(checkpoint, candidate, model_config)
    model = build_classifier("cnn", model_config)
    # Strict loading is essential here: missing or unexpected tensors would
    # mean the evaluated network is not the architecture frozen by validation.
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()

    # This call is intentionally after all selection checks and requests only
    # IID rows.  Train/validation features are therefore neither reparsed nor
    # mixed into the final score, while the split itself remains unchanged.
    iid = load_window_table(args.windows, splits={"iid_test"})
    trace_ids = {row["trace_id"] for row in iid.metadata}
    if (len(iid.labels) != EXPECTED_WINDOW_COUNT
            or len(trace_ids) != EXPECTED_TRACE_COUNT
            or {row["split"] for row in iid.metadata} != {"iid_test"}
            or set(np.unique(iid.labels)) != {0, 1}):
        raise ValueError("CNN IID release must contain 22,512 windows on 48 traces")
    corpus = load_iid_corpus(args.corpus, trace_ids)
    normalized = apply_normalizer(iid, checkpoint["normalizer"])
    _, probabilities = predict(
        model, normalized.features, int(training_config["batch_size"]))
    raw_rows = prediction_rows(iid, probabilities)
    processed_rows = apply_detector(raw_rows, postprocess_config)
    if [row["window_id"] for row in raw_rows] != [
            row["window_id"] for row in processed_rows]:
        raise ValueError("postprocessing changed CNN IID row alignment")

    raw_metrics = score_rows(raw_rows, probabilities)
    postprocessed_metrics = score_rows(processed_rows, probabilities)
    detector_latency = benchmark_detector(raw_rows, postprocess_config)
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = Path(tempfile.mkdtemp(
        prefix=".{}.tmp.".format(args.output_dir.name),
        dir=str(args.output_dir.parent)))
    try:
        predictions_path = temporary_output / "predictions.csv"
        write_predictions(predictions_path, processed_rows)
        # The report records every digest needed to reproduce the inference.
        # IID metrics are descriptive only: no acceptance gate or configuration
        # is altered after observing them, and reruns remain unauthorized.
        report = {
            "schema_version": 1,
            "scope": "frozen_binary_cnn_iid_holdout_exactly_once",
            "task": "safe_critical_binary", "model": "cnn",
            "parameters_tuned_on_test": False,
            "pristine_blind_test": False,
            "rerun_authorized": False,
            "trace_count": EXPECTED_TRACE_COUNT,
            "prediction_count": EXPECTED_WINDOW_COUNT,
            "window_length": int(candidate["window_length"]),
            "seed": int(candidate["seed"]),
            "parameter_count": int(candidate["parameter_count"]),
            "estimated_macs_per_window": int(
                candidate["estimated_macs_per_window"]),
            "training_recorded_median_cpu_latency_ms": float(
                candidate["median_cpu_latency_ms"]),
            "postprocess_config": postprocess_config,
            "postprocess_latency_ms_per_window": detector_latency,
            "raw": raw_metrics,
            "postprocessed": postprocessed_metrics,
            "validation_postprocess_acceptance": postprocess_report["acceptance"],
            "hard_pairs": hard_pair_metrics(processed_rows, corpus),
            "inputs": {
                name + "_sha256": sha256_file(getattr(args, name))
                for name in (
                    "windows", "checkpoint", "training_config", "model_config",
                    "training_summary", "validation_predictions", "policy_config",
                    "architecture_selection", "objective_selection",
                    "candidate_manifest", "postprocess_report",
                    "postprocess_config", "corpus")
            },
            "predictions_sha256": sha256_file(predictions_path),
        }
        (temporary_output / "frozen_evaluation.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        os.rename(str(temporary_output), str(args.output_dir))
    finally:
        # A failure leaves no report-shaped directory.  The private staging
        # directory is removed, while an already published result is untouched.
        if temporary_output.exists():
            shutil.rmtree(str(temporary_output))


if __name__ == "__main__":
    main()
