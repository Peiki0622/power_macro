#!/usr/bin/env python3
"""Run one immutable IID/OOD evaluation with a frozen TCN and postprocessor."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.dataset.model_data import apply_normalizer, filter_split, load_window_table
from power_macro.tcn_detection.evaluate.metrics import event_metrics, hard_pair_metrics, window_metrics
from power_macro.tcn_detection.evaluate.postprocess import apply_detector
from power_macro.tcn_detection.train.common import build_classifier, configure_cpu, read_json
from power_macro.tcn_detection.train.train_classifier import predict


def sha256_file(path):
    """Hash one frozen input or published result with bounded memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_test_truth(label_dir, trace_ids):
    """Read complete truth timelines only for the frozen test traces."""

    truth = {}
    for trace_id in sorted(trace_ids):
        path = Path(label_dir) / (trace_id + ".csv")
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        if not rows or rows[0]["split"] not in {"iid_test", "ood_test"}:
            raise ValueError("missing or non-test truth timeline: {}".format(trace_id))
        truth[trace_id] = rows
    return truth


def read_test_corpus(path, trace_ids):
    """Stream corpus authority and retain exactly the requested test traces."""

    requested = set(trace_ids)
    selected = {}
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["trace_id"] in requested:
                if row["split"] not in {"iid_test", "ood_test"}:
                    raise ValueError("requested test trace has non-test corpus membership")
                selected[row["trace_id"]] = row
    if set(selected) != requested:
        raise ValueError("corpus is missing one or more requested test traces")
    return selected


def prediction_rows(table, probabilities):
    """Join frozen inference probabilities to immutable window metadata."""

    rows = []
    for metadata, probability in zip(table.metadata, probabilities):
        rows.append({"window_id": metadata["window_id"], "trace_id": metadata["trace_id"],
                     "split": metadata["split"], "end_index": int(metadata["end_index"]),
                     "target_label": int(metadata["target_label"]), "prediction": int(np.argmax(probability)),
                     "prob_safe": float(probability[0]), "prob_warning": float(probability[1]),
                     "prob_critical": float(probability[2])})
    return rows


def score_split(raw_rows, processed_rows, truth, corpus, split, raw_confirm_count):
    """Score one frozen split without selecting any threshold or confirmation K."""

    raw = [row for row in raw_rows if row["split"] == split]
    processed = [row for row in processed_rows if row["split"] == split]
    trace_ids = {row["trace_id"] for row in raw}
    labels = np.asarray([row["target_label"] for row in raw], dtype=np.int64)
    raw_predictions = np.asarray([row["prediction"] for row in raw], dtype=np.int64)
    probabilities = np.asarray([[row["prob_safe"], row["prob_warning"], row["prob_critical"]]
                                for row in raw], dtype=np.float64)
    processed_predictions = np.asarray([row["prediction"] for row in processed], dtype=np.int64)
    if [row["window_id"] for row in raw] != [row["window_id"] for row in processed]:
        raise ValueError("postprocessing changed frozen prediction row alignment")

    # The raw comparison retains K=9 selected before test access.  The detector
    # output already contains hysteretic episodes, so event_metrics receives
    # K=1 and must not add a second confirmation delay.
    raw_events = event_metrics(raw, truth, corpus, int(raw_confirm_count), trace_ids=trace_ids)
    processed_events = event_metrics(processed, truth, corpus, 1, trace_ids=trace_ids)
    processed_window = window_metrics(labels, processed_predictions)
    acceptance = {
        "critical_event_detection_rate_ge_0_90": (processed_events["critical_event_detection_rate"] or 0.0) >= 0.90,
        "median_lead_time_ns_gt_0": processed_events["median_lead_time_ns"] is not None
        and processed_events["median_lead_time_ns"] > 0.0,
        "false_alarms_per_trace_le_2_0": processed_events["false_alarms_per_trace"] <= 2.0,
        "safe_window_false_alarm_rate_le_0_35": processed_window["safe_window_false_alarm_rate"] <= 0.35,
    }
    acceptance["pass"] = all(acceptance.values())
    return {"trace_count": len(trace_ids), "prediction_count": len(raw),
            "raw_window": window_metrics(labels, raw_predictions, probabilities),
            "raw_events_k{}".format(raw_confirm_count): raw_events,
            "postprocessed_window": processed_window, "postprocessed_events": processed_events,
            "acceptance": acceptance}


def write_predictions(path, rows):
    """Persist bounded test outputs without raw tensors or electrical features."""

    fields = ["window_id", "trace_id", "split", "end_index", "target_label", "raw_prediction",
              "prediction", "prob_safe", "prob_warning", "prob_critical",
              "filtered_risk_score", "filtered_critical_score"]
    temporary = Path(path).with_suffix(Path(path).suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: (item["split"], item["trace_id"], int(item["end_index"]))):
            writer.writerow({field: row[field] for field in fields})
    temporary.replace(path)


def main():
    """Evaluate the frozen detector exactly once and publish immutable evidence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--postprocess-config", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--label-dir", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--raw-confirm-count", type=int, default=9)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite frozen evaluation directory: {}".format(args.output_dir))

    training_config = read_json(args.training_config)
    configure_cpu(training_config["seed"], training_config["cpu_threads_per_process"])
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    if checkpoint.get("model") != "tcn" or int(checkpoint.get("window_length", -1)) != 32:
        raise ValueError("frozen evaluator requires the accepted L32 TCN checkpoint")
    model = build_classifier("tcn", checkpoint["model_config"])
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()

    # Parse only the two frozen test partitions.  Validation probabilities are
    # not reopened here, preventing accidental post-freeze parameter changes.
    test_table = load_window_table(args.windows, splits={"iid_test", "ood_test"})
    normalized = apply_normalizer(test_table, checkpoint["normalizer"])
    _, probabilities = predict(model, normalized.features, training_config["batch_size"])
    raw_rows = prediction_rows(test_table, probabilities)
    postprocess_config = read_json(args.postprocess_config)
    processed_rows = apply_detector(raw_rows, postprocess_config)
    trace_ids = {row["trace_id"] for row in raw_rows}
    truth = read_test_truth(args.label_dir, trace_ids)
    corpus = read_test_corpus(args.corpus, trace_ids)

    split_reports = {split: score_split(raw_rows, processed_rows, truth, corpus, split, args.raw_confirm_count)
                     for split in ("iid_test", "ood_test")}
    report = {"schema_version": 1, "scope": "frozen_iid_ood_once",
              "parameters_tuned_on_test": False, "window_length": 32,
              "raw_confirm_count": int(args.raw_confirm_count),
              "inputs": {"windows_sha256": sha256_file(args.windows),
                         "checkpoint_sha256": sha256_file(args.checkpoint),
                         "postprocess_config_sha256": sha256_file(args.postprocess_config),
                         "training_config_sha256": sha256_file(args.training_config),
                         "corpus_sha256": sha256_file(args.corpus)},
              "splits": split_reports,
              "hard_pairs": hard_pair_metrics(processed_rows, corpus),
              "overall_acceptance_pass": all(item["acceptance"]["pass"] for item in split_reports.values())}

    args.output_dir.mkdir(parents=True, exist_ok=False)
    report_temporary = args.output_dir / "frozen_evaluation.json.tmp"
    report_temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_temporary.replace(args.output_dir / "frozen_evaluation.json")
    write_predictions(args.output_dir / "predictions.csv", processed_rows)
    if not report["overall_acceptance_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
