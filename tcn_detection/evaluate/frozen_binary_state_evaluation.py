#!/usr/bin/env python3
"""Run the single authorized IID evaluation for the frozen binary state TCN.

This module is deliberately release-specific.  The embedded digests bind the
one-shot command to the exact validation-selected candidate and postprocessor;
making those values command-line options would let an accidental substitution
look like an approved test.  The evaluator never tunes a threshold, changes a
split, or writes back into any model/data artifact.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.dataset.model_data import (
    apply_normalizer, load_window_table)
from power_macro.tcn_detection.evaluate.binary_metrics import (
    binary_event_metrics, binary_window_metrics)
from power_macro.tcn_detection.evaluate.binary_postprocess import apply_detector
from power_macro.tcn_detection.evaluate.metrics import hard_pair_metrics
from power_macro.tcn_detection.train.common import build_classifier, configure_cpu
from power_macro.tcn_detection.train.train_classifier import predict


# These digests are the validation-frozen release boundary.  Candidate-owned
# files (checkpoint, windows, training/model configs) are checked against the
# signed manifest below as well, while these constants protect the manifest,
# postprocessing choice, and corpus that otherwise have no parent manifest.
RELEASE_DIGESTS = {
    "candidate_manifest": "3761e984bca8baf7f922d5b8b796c5a1aeb6564b52514ff21fb96e81e16e96f0",
    "postprocess_report": "e0c00974a7108be90d34d911e7ab93805685f95b1394effa02e34aefdb255994",
    "postprocess_config": "08796898c65f0e0fc6d1466146d3ef6879a2f819bc3e70a20f3b61dbb607b72f",
    "corpus": "029ad57b410210b1f5b27ca75aa70569634c82a6791113b52affe7a10a686875",
}
EXPECTED_TRACE_COUNT = 48
EXPECTED_WINDOW_COUNT = 22512


def sha256_file(path):
    """Return a bounded-memory SHA-256 digest for one immutable artifact."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Read one UTF-8 JSON object and reject non-object top-level values."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected a JSON object: {}".format(path))
    return payload


def verify_frozen_inputs(args):
    """Verify the complete validation-frozen boundary before loading IID data.

    Verification is intentionally completed before ``load_window_table`` is
    called.  If any model-selection or postprocessing artifact drifted, no IID
    feature is even parsed, which prevents a malformed run from consuming the
    one authorized test access.
    """

    release_paths = {
        "candidate_manifest": args.candidate_manifest,
        "postprocess_report": args.postprocess_report,
        "postprocess_config": args.postprocess_config,
        "corpus": args.corpus,
    }
    for name, path in release_paths.items():
        if sha256_file(path) != RELEASE_DIGESTS[name]:
            raise ValueError("frozen release digest mismatch: {}".format(name))

    candidate = read_json(args.candidate_manifest)
    postprocess_report = read_json(args.postprocess_report)
    postprocess_config = read_json(args.postprocess_config)
    candidate_checks = {
        "checkpoint": (args.checkpoint, candidate["checkpoint_sha256"]),
        "windows": (args.windows, candidate["windows_sha256"]),
        "training_config": (args.training_config,
                            candidate["training_config_sha256"]),
        "model_config": (args.model_config, candidate["model_config_sha256"]),
    }
    for name, (path, expected_digest) in candidate_checks.items():
        if sha256_file(path) != expected_digest:
            raise ValueError("candidate-owned digest mismatch: {}".format(name))

    # The following flags prove that model, epoch, and detector parameters were
    # fixed using validation only.  The spelling differs from the historical
    # three-class manifest, so checking the exact binary key is important.
    if (candidate.get("task") != "safe_critical_binary"
            or candidate.get("iid_metrics_computed") is not False
            or candidate.get("parameters_tuned_on_test") is not False
            or postprocess_report.get("scope") != "validation_only"
            or postprocess_report.get("iid_metrics_computed") is not False
            or postprocess_report.get("parameters_tuned_on_test") is not False):
        raise ValueError("an input crossed the validation-only freeze boundary")
    if postprocess_report.get("final_config") != postprocess_config:
        raise ValueError("postprocess config differs from validation selection")
    return candidate, postprocess_report, postprocess_config


def validate_checkpoint(checkpoint, candidate, model_config):
    """Reject any checkpoint that is not the exact two-logit frozen TCN."""

    if (checkpoint.get("task") != "safe_critical_binary"
            or checkpoint.get("model") != "tcn"
            or checkpoint.get("model_config") != model_config
            or int(model_config.get("class_count", -1)) != 2
            or model_config.get("class_names") != {"0": "Safe", "1": "Critical"}
            or int(checkpoint.get("window_length", -1))
            != int(candidate["window_length"])
            or int(checkpoint.get("seed", -1)) != int(candidate["seed"])):
        raise ValueError("checkpoint is not the frozen two-class TCN")
    normalizer = checkpoint.get("normalizer", {})
    if (normalizer.get("source_split") != "train"
            or int(normalizer.get("window_length", -1))
            != int(candidate["window_length"])):
        raise ValueError("checkpoint does not contain the train-only normalizer")


def prediction_rows(table, probabilities):
    """Join two-class probabilities with auditable non-feature metadata."""

    if probabilities.shape != (len(table.labels), 2):
        raise ValueError("binary TCN must emit exactly two probabilities per window")
    rows = []
    for metadata, probability in zip(table.metadata, probabilities):
        target = int(metadata["target_label"])
        source = int(metadata["source_state_label"])
        # The released task maps both former Safe(0) and Warning(1) to binary
        # Safe(0), while Critical(2) alone maps to binary Critical(1).  Checking
        # this row by row prevents a mislabeled IID file from being scored.
        if target != (1 if source == 2 else 0) or source not in {0, 1, 2}:
            raise ValueError("source-to-binary label mapping changed")
        rows.append({
            "window_id": metadata["window_id"],
            "trace_id": metadata["trace_id"],
            "split": metadata["split"],
            "end_index": int(metadata["end_index"]),
            "target_label": target,
            "source_state_label": source,
            "prediction": int(np.argmax(probability)),
            "prob_safe": float(probability[0]),
            "prob_critical": float(probability[1]),
        })
    return rows


def load_iid_corpus(path, trace_ids):
    """Load metadata for exactly the 48 requested IID traces and nothing else."""

    requested = set(trace_ids)
    records = {}
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("trace_id") in requested:
                if row.get("split") != "iid_test":
                    raise ValueError("prediction trace has non-IID corpus membership")
                if row["trace_id"] in records:
                    raise ValueError("duplicate trace in frozen corpus")
                records[row["trace_id"]] = row
    if set(records) != requested or len(records) != EXPECTED_TRACE_COUNT:
        raise ValueError("corpus does not contain exactly the requested IID traces")
    return records


def score_rows(rows, probabilities):
    """Compute all window and chronological metrics at one operating point."""

    labels = np.asarray([row["target_label"] for row in rows], dtype=np.int64)
    predictions = np.asarray([row["prediction"] for row in rows], dtype=np.int64)
    return {
        "window": binary_window_metrics(labels, predictions, probabilities),
        "events": binary_event_metrics(rows),
    }


def benchmark_detector(rows, config, repetitions=30):
    """Measure median frozen detector latency without changing its outputs."""

    samples = []
    for _ in range(int(repetitions)):
        started = time.perf_counter_ns()
        apply_detector(rows, config)
        samples.append((time.perf_counter_ns() - started) / 1.0e6 / len(rows))
    return float(np.median(samples))


def write_predictions(path, rows):
    """Persist the exact raw/deployed decisions used by the final report."""

    fields = ["window_id", "trace_id", "split", "end_index", "target_label",
              "source_state_label", "raw_prediction", "prediction",
              "prob_safe", "prob_critical", "filtered_critical_score"]
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        # Stable ordering makes the CSV hash reproducible and provides a direct
        # join key for the old three-class projected comparison in Step 10.
        for row in sorted(rows, key=lambda item: (
                item["trace_id"], int(item["end_index"]))):
            writer.writerow({field: row[field] for field in fields})


def parse_args():
    """Parse explicit paths so the one-shot invocation remains reproducible."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--candidate-manifest", required=True, type=Path)
    parser.add_argument("--postprocess-report", required=True, type=Path)
    parser.add_argument("--postprocess-config", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main():
    """Evaluate once and atomically publish report plus prediction evidence."""

    args = parse_args()
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite the one-shot IID result")
    candidate, postprocess_report, postprocess_config = verify_frozen_inputs(args)
    training_config = read_json(args.training_config)
    model_config = read_json(args.model_config)
    configure_cpu(candidate["seed"], training_config["cpu_threads_per_process"])
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    validate_checkpoint(checkpoint, candidate, model_config)
    model = build_classifier("tcn", model_config)
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()

    # This is the first and only IID feature access.  Filtering happens before
    # features_json parsing, structurally excluding train and validation rows.
    iid = load_window_table(args.windows, splits={"iid_test"})
    trace_ids = {row["trace_id"] for row in iid.metadata}
    if (len(iid.labels) != EXPECTED_WINDOW_COUNT
            or len(trace_ids) != EXPECTED_TRACE_COUNT
            or {row["split"] for row in iid.metadata} != {"iid_test"}
            or set(np.unique(iid.labels)) != {0, 1}):
        raise ValueError("IID release must contain 22,512 windows on 48 traces")
    corpus = load_iid_corpus(args.corpus, trace_ids)
    normalized = apply_normalizer(iid, checkpoint["normalizer"])
    _, probabilities = predict(
        model, normalized.features, int(training_config["batch_size"]))
    raw_rows = prediction_rows(iid, probabilities)
    processed_rows = apply_detector(raw_rows, postprocess_config)
    if [row["window_id"] for row in raw_rows] != [
            row["window_id"] for row in processed_rows]:
        raise ValueError("postprocessing changed IID row alignment")
    latency = benchmark_detector(raw_rows, postprocess_config)
    raw_metrics = score_rows(raw_rows, probabilities)
    postprocessed_metrics = score_rows(processed_rows, probabilities)
    # Both files are staged in a private sibling directory.  Only after the
    # predictions are complete and hashed is the report written; a single
    # directory rename then publishes a consistent evidence pair.
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = Path(tempfile.mkdtemp(
        prefix=".{}.tmp.".format(args.output_dir.name),
        dir=str(args.output_dir.parent)))
    try:
        predictions_path = temporary_output / "predictions.csv"
        write_predictions(predictions_path, processed_rows)
        report = {
            "schema_version": 1,
            "scope": "frozen_binary_iid_holdout_exactly_once",
            "task": "safe_critical_binary",
            "parameters_tuned_on_test": False,
            "pristine_blind_test": False,
            "rerun_authorized": False,
            "trace_count": EXPECTED_TRACE_COUNT,
            "prediction_count": EXPECTED_WINDOW_COUNT,
            "window_length": int(candidate["window_length"]),
            "seed": int(candidate["seed"]),
            "postprocess_config": postprocess_config,
            "postprocess_latency_ms_per_window": latency,
            "raw": raw_metrics,
            "postprocessed": postprocessed_metrics,
            # The postprocess report stores validation acceptance booleans but
            # not the underlying numeric gate definition.  Preserve those
            # frozen validation conclusions verbatim; do not import another
            # config or turn IID observations into a new selection decision.
            "validation_postprocess_acceptance": postprocess_report["acceptance"],
            "hard_pairs": hard_pair_metrics(processed_rows, corpus),
            "inputs": {
                "windows_sha256": sha256_file(args.windows),
                "checkpoint_sha256": sha256_file(args.checkpoint),
                "training_config_sha256": sha256_file(args.training_config),
                "model_config_sha256": sha256_file(args.model_config),
                "candidate_manifest_sha256": sha256_file(args.candidate_manifest),
                "postprocess_report_sha256": sha256_file(args.postprocess_report),
                "postprocess_config_sha256": sha256_file(args.postprocess_config),
                "corpus_sha256": sha256_file(args.corpus),
            },
            "predictions_sha256": sha256_file(predictions_path),
        }
        (temporary_output / "frozen_evaluation.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        os.rename(str(temporary_output), str(args.output_dir))
    finally:
        if temporary_output.exists():
            shutil.rmtree(str(temporary_output))


if __name__ == "__main__":
    main()
