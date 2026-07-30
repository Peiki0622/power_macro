#!/usr/bin/env python3
"""Compute comprehensive TCN metrics from persisted validation predictions only."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.evaluate.metrics import choose_confirmation, event_metrics, window_metrics


TCN_JOBS = ("tcn_L8", "tcn_L16", "tcn_L32")


def sha256_file(path):
    """Hash one input artifact with bounded memory for report provenance."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_prediction_rows(path):
    """Load and strictly validate one model's development predictions.

    The persisted training artifact is deliberately limited to validation.
    Rejecting any other split here prevents this convenience command from
    silently becoming a frozen IID/OOD evaluation.  Probability validation is
    repeated in ``window_metrics`` before any score is computed.
    """

    rows = []
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for raw in csv.DictReader(stream):
            if raw["split"] != "validation":
                raise ValueError("prediction report contains a non-validation row")
            rows.append({"window_id": raw["window_id"], "trace_id": raw["trace_id"],
                         "split": raw["split"], "end_index": int(raw["end_index"]),
                         "target_label": int(raw["target_label"]), "prediction": int(raw["prediction"]),
                         "prob_safe": float(raw["prob_safe"]), "prob_warning": float(raw["prob_warning"]),
                         "prob_critical": float(raw["prob_critical"])})
    if not rows:
        raise ValueError("prediction report is empty")
    identifiers = [row["window_id"] for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("prediction report contains duplicate window IDs")
    return rows


def read_validation_truth(label_dir, trace_ids):
    """Read full label timelines only for validation traces used by predictions."""

    truth = {}
    for trace_id in sorted(trace_ids):
        path = Path(label_dir) / (trace_id + ".csv")
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        if not rows or rows[0]["split"] != "validation":
            raise ValueError("missing or non-validation truth timeline: {}".format(trace_id))
        truth[trace_id] = rows
    return truth


def read_validation_corpus(path, trace_ids):
    """Stream corpus metadata and retain only requested validation trace IDs."""

    requested = set(trace_ids)
    selected = {}
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["trace_id"] in requested:
                if row["split"] != "validation":
                    raise ValueError("prediction trace is not assigned to validation in the corpus")
                selected[row["trace_id"]] = row
    if set(selected) != requested:
        raise ValueError("corpus is missing validation prediction traces")
    return selected


def metrics_for_job(job_name, models_dir, label_dir, corpus, confirmation_candidates):
    """Calculate window, probability, and chronological event metrics for one TCN."""

    prediction_path = Path(models_dir) / job_name / "validation_predictions.csv"
    rows = read_prediction_rows(prediction_path)
    labels = np.asarray([row["target_label"] for row in rows], dtype=np.int64)
    predictions = np.asarray([row["prediction"] for row in rows], dtype=np.int64)
    probabilities = np.asarray([[row["prob_safe"], row["prob_warning"], row["prob_critical"]]
                                for row in rows], dtype=np.float64)
    trace_ids = {row["trace_id"] for row in rows}
    truth = read_validation_truth(label_dir, trace_ids)
    corpus_by_trace = read_validation_corpus(corpus, trace_ids)

    # Confirmation K is selected independently for each history length using
    # validation only.  The complete scan remains in the report so the selected
    # event result can be audited against its false-alarm/lead-time trade-off.
    confirmation = choose_confirmation(rows, truth, corpus_by_trace, confirmation_candidates)
    selected_k = int(confirmation["selected_confirm_count"])
    events = event_metrics(rows, truth, corpus_by_trace, selected_k)
    return {"window_length": int(job_name.split("L")[-1]), "prediction_count": len(rows),
            "trace_count": len(trace_ids), "window": window_metrics(labels, predictions, probabilities),
            "confirmation": confirmation, "selected_event_metrics": events,
            "predictions_sha256": sha256_file(prediction_path)}


def main():
    """Build one immutable JSON report for all requested Formal TCN jobs."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", required=True, type=Path)
    parser.add_argument("--label-dir", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--jobs", nargs="+", choices=TCN_JOBS, default=list(TCN_JOBS))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("refusing to overwrite validation metrics report: {}".format(args.output))

    training_config = json.loads(args.training_config.read_text(encoding="utf-8"))
    candidates = [int(value) for value in training_config["confirmation_candidates"]]
    if len(args.jobs) != len(set(args.jobs)):
        raise ValueError("validation metric jobs contain duplicates")
    report = {"schema_version": 1, "scope": "validation_only",
              "iid_ood_metrics_computed": False,
              "confirmation_candidates": candidates,
              "training_config_sha256": sha256_file(args.training_config),
              "corpus_sha256": sha256_file(args.corpus), "jobs": {}}
    for job_name in args.jobs:
        report["jobs"][job_name] = metrics_for_job(
            job_name, args.models_dir, args.label_dir, args.corpus, candidates)

    # Publish atomically so interruption cannot leave a syntactically valid but
    # incomplete report.  The parent may be a new versioned evaluation folder;
    # existing reports are never overwritten by this command.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
