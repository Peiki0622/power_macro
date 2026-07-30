#!/usr/bin/env python3
"""Run the single frozen IID-holdout evaluation for code-state monitoring."""

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
from power_macro.tcn_detection.evaluate.metrics import hard_pair_metrics, window_metrics
from power_macro.tcn_detection.evaluate.postprocess import apply_detector
from power_macro.tcn_detection.evaluate.state_metrics import state_event_metrics
from power_macro.tcn_detection.evaluate.summarize_state_code_ablation import (
    RAW_GATES, gate_checks)
from power_macro.tcn_detection.evaluate.tune_state_postprocess import acceptance
from power_macro.tcn_detection.train.common import build_classifier, configure_cpu
from power_macro.tcn_detection.train.train_classifier import predict


def sha256_file(path):
    """Hash one frozen input or published result using bounded memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_frozen_inputs(args):
    """Fail before test loading if any validation-frozen artifact changed."""

    candidate = json.loads(args.candidate_manifest.read_text(encoding="utf-8"))
    postprocess_report = json.loads(args.postprocess_report.read_text(encoding="utf-8"))
    postprocess_config = json.loads(args.postprocess_config.read_text(encoding="utf-8"))
    checks = {
        "checkpoint": (args.checkpoint, candidate["checkpoint_sha256"]),
        "windows": (args.windows, candidate["windows_sha256"]),
        "training_config": (args.training_config, candidate["training_config_sha256"]),
        "model_config": (args.model_config, candidate["model_config_sha256"]),
    }
    for name, (path, expected) in checks.items():
        if sha256_file(path) != expected:
            raise ValueError("frozen {} digest mismatch".format(name))
    if (candidate.get("iid_ood_metrics_computed") is not False
            or postprocess_report.get("iid_ood_metrics_computed") is not False
            or postprocess_report.get("parameters_tuned_on_test") is not False
            or postprocess_report.get("scope") != "validation_only"):
        raise ValueError("candidate or postprocess artifact crossed the blind-test boundary")
    if postprocess_config != postprocess_report["final_config"]:
        raise ValueError("postprocess config differs from the validation-frozen selection")
    return candidate, postprocess_report, postprocess_config


def prediction_rows(table, probabilities):
    """Join frozen probabilities to non-feature window metadata."""

    rows = []
    for metadata, probability in zip(table.metadata, probabilities):
        rows.append({
            "window_id": metadata["window_id"], "trace_id": metadata["trace_id"],
            "split": metadata["split"], "end_index": int(metadata["end_index"]),
            "target_label": int(metadata["target_label"]),
            "prediction": int(np.argmax(probability)),
            "prob_safe": float(probability[0]),
            "prob_warning": float(probability[1]),
            "prob_critical": float(probability[2]),
        })
    return rows


def load_test_corpus(path, trace_ids):
    """Load corpus metadata only for requested frozen IID traces."""

    requested = set(trace_ids)
    records = {}
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["trace_id"] in requested:
                if row["split"] != "iid_test":
                    raise ValueError("IID prediction has non-IID corpus membership")
                records[row["trace_id"]] = row
    if set(records) != requested:
        raise ValueError("corpus is missing frozen test traces")
    return records


def raw_gate_metrics(labels, predictions, report):
    """Construct the exact Step 6 gate fields for one frozen split."""

    risk = labels >= 1
    return {
        "accuracy": report["accuracy"],
        "balanced_accuracy": report["balanced_accuracy"],
        "macro_f1": report["macro_f1"],
        "risk_recall": float(np.mean(predictions[risk] >= 1)),
        "critical_recall": report["per_class"]["2"]["recall"],
        "warning_recall": report["per_class"]["1"]["recall"],
        "safe_window_false_alarm_rate": report["safe_window_false_alarm_rate"],
    }


def score_split(raw_rows, processed_rows, split, latency):
    """Report raw and deployed metrics without selecting any new parameter."""

    raw = [row for row in raw_rows if row["split"] == split]
    processed = [row for row in processed_rows if row["split"] == split]
    if [row["window_id"] for row in raw] != [row["window_id"] for row in processed]:
        raise ValueError("postprocessing changed frozen row alignment")
    labels = np.asarray([row["target_label"] for row in raw])
    raw_predictions = np.asarray([row["prediction"] for row in raw])
    deployed_predictions = np.asarray([row["prediction"] for row in processed])
    probabilities = np.asarray([[row["prob_safe"], row["prob_warning"],
                                 row["prob_critical"]] for row in raw])
    raw_window = window_metrics(labels, raw_predictions, probabilities)
    deployed_window = window_metrics(labels, deployed_predictions, probabilities)
    raw_gates = raw_gate_metrics(labels, raw_predictions, raw_window)
    deployed_gates = raw_gate_metrics(labels, deployed_predictions, deployed_window)
    raw_events = state_event_metrics(raw)
    deployed_events = state_event_metrics(processed)
    return {
        "trace_count": len({row["trace_id"] for row in raw}),
        "prediction_count": len(raw),
        "raw_window": raw_window, "raw_events": raw_events,
        "raw_gate_values": raw_gates, "raw_gate_checks": gate_checks(raw_gates),
        "raw_passes_all_gates": all(gate_checks(raw_gates).values()),
        "postprocessed_window": deployed_window,
        "postprocessed_events": deployed_events,
        "postprocessed_gate_values": deployed_gates,
        "postprocessed_raw_gate_checks": gate_checks(deployed_gates),
        "postprocessed_event_acceptance": acceptance(
            deployed_window, deployed_events, latency),
    }


def benchmark_detector(rows, config, repetitions=30):
    """Measure frozen state-machine latency per test window without tuning."""

    samples = []
    for _ in range(int(repetitions)):
        started = time.perf_counter_ns()
        apply_detector(rows, config)
        samples.append((time.perf_counter_ns() - started) / 1.0e6 / len(rows))
    return float(np.median(samples))


def write_predictions(path, rows):
    """Persist bounded model outputs and filtered states, never input tensors."""

    fields = ["window_id", "trace_id", "split", "end_index", "target_label",
              "raw_prediction", "prediction", "prob_safe", "prob_warning",
              "prob_critical", "filtered_risk_score", "filtered_critical_score"]
    temporary = Path(path).with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: (
                item["split"], item["trace_id"], int(item["end_index"]))):
            writer.writerow({field: row[field] for field in fields})
    temporary.replace(path)


def main():
    """Perform the one authorized frozen test evaluation and publish evidence."""

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
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite one-shot state evaluation")
    candidate, postprocess_report, postprocess_config = verify_frozen_inputs(args)
    training_config = json.loads(args.training_config.read_text(encoding="utf-8"))
    configure_cpu(candidate["seed"], training_config["cpu_threads_per_process"])
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    if (checkpoint.get("model") != "tcn"
            or int(checkpoint.get("window_length", -1)) != candidate["window_length"]
            or checkpoint.get("model_config") != json.loads(
                args.model_config.read_text(encoding="utf-8"))):
        raise ValueError("checkpoint architecture differs from frozen candidate")
    model = build_classifier("tcn", checkpoint["model_config"])
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()

    # This is the only point in the workflow where frozen IID features are
    # materialized.  The singleton split filter is intentional: it rejects the
    # former OOD contract structurally and excludes train/validation tensors
    # from this final process.  Exact count gates bind the run to the approved
    # 48-trace, L32 release rather than any similarly named window file.
    test = load_window_table(args.windows, splits={"iid_test"})
    if len(test.labels) != 22512 or {row["split"] for row in test.metadata} != {"iid_test"}:
        raise ValueError("frozen evaluator requires exactly 22,512 IID windows")
    if len({row["trace_id"] for row in test.metadata}) != 48:
        raise ValueError("frozen evaluator requires exactly 48 IID traces")
    normalized = apply_normalizer(test, checkpoint["normalizer"])
    _, probabilities = predict(model, normalized.features,
                               training_config["batch_size"])
    raw_rows = prediction_rows(test, probabilities)
    processed_rows = apply_detector(raw_rows, postprocess_config)
    latency = benchmark_detector(raw_rows, postprocess_config)
    corpus = load_test_corpus(args.corpus, {row["trace_id"] for row in raw_rows})
    iid_report = score_split(raw_rows, processed_rows, "iid_test", latency)
    report = {
        "schema_version": 1, "scope": "frozen_iid_holdout_exactly_once",
        "parameters_tuned_on_test": False, "rerun_authorized": False,
        # Earlier iterations exposed per-trace outcomes before this repartition,
        # so the holdout is frozen and IID but must not be marketed as pristine.
        "pristine_blind_test": False,
        "window_length": candidate["window_length"], "seed": candidate["seed"],
        "postprocess_latency_ms_per_window": latency,
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
        "validation_postprocess_acceptance": postprocess_report["acceptance"],
        "splits": {"iid_test": iid_report},
        "hard_pairs": hard_pair_metrics(processed_rows, corpus),
        "overall_event_acceptance_pass": iid_report[
            "postprocessed_event_acceptance"]["pass"],
    }
    # Stage both outputs under a private sibling directory and publish them
    # together.  A crash cannot expose a report without its exact prediction
    # evidence, and the absent-target preflight prevents rerunning over the
    # first result.
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = Path(tempfile.mkdtemp(
        prefix=".{}.tmp.".format(args.output_dir.name),
        dir=str(args.output_dir.parent)))
    try:
        (temporary_output / "frozen_evaluation.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_predictions(temporary_output / "predictions.csv", processed_rows)
        os.rename(str(temporary_output), str(args.output_dir))
    finally:
        if temporary_output.exists():
            shutil.rmtree(str(temporary_output))


if __name__ == "__main__":
    main()
