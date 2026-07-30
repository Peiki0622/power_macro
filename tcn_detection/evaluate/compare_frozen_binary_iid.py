#!/usr/bin/env python3
"""Compare frozen binary IID predictions with projected three-class outputs.

The script is reporting-only: it reads two already-published prediction CSVs,
projects the old three-state result to the agreed binary ontology, and refuses
to overwrite its report directory.  No model, checkpoint, threshold, or
dataset split is loaded or modified.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.evaluate.binary_metrics import (
    binary_event_metrics, binary_window_metrics)


EXPECTED_ENDPOINTS = 22512
# The old evaluator predated prediction hashing inside its JSON report.  This
# release-specific digest closes that provenance gap without rerunning it.
EXPECTED_OLD_PREDICTIONS_SHA256 = (
    "5112840d62125586fa3d94c3969823ab5e7117a5805512fd6a767714884f4315")


def sha256_file(path):
    """Hash one frozen prediction/report input using bounded memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Load one report and require an object at the top level."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return payload


def validate_report_boundary(old_report, binary_report, old_predictions,
                             binary_predictions):
    """Prove both inputs are immutable one-shot IID outputs, not tuning data."""

    for name, report in (("old", old_report), ("binary", binary_report)):
        if (report.get("parameters_tuned_on_test") is not False
                or report.get("pristine_blind_test") is not False
                or report.get("rerun_authorized") is not False):
            raise ValueError("{} report violates frozen IID boundary".format(name))
    if sha256_file(old_predictions) != EXPECTED_OLD_PREDICTIONS_SHA256:
        raise ValueError("old frozen predictions digest mismatch")
    if sha256_file(binary_predictions) != binary_report.get("predictions_sha256"):
        raise ValueError("binary frozen predictions digest mismatch")


def read_old_projected(path):
    """Read old three-class rows and project 0/1 vs 2 without information loss."""

    rows = {}
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for source in csv.DictReader(stream):
            if source["split"] != "iid_test":
                raise ValueError("old prediction CSV contains a non-IID row")
            key = (source["trace_id"], int(source["end_index"]))
            if key in rows:
                raise ValueError("duplicate endpoint in old predictions")
            source_target = int(source["target_label"])
            probabilities = np.asarray([
                float(source["prob_safe"]) + float(source["prob_warning"]),
                float(source["prob_critical"]),
            ], dtype=np.float64)
            # Summing Safe and Warning is the probability-preserving projection
            # of the old softmax.  A tiny normalization handles decimal CSV
            # precision while the explicit tolerance rejects malformed scores.
            if (not np.all(np.isfinite(probabilities))
                    or np.any(probabilities < 0.0)
                    or not np.isclose(probabilities.sum(), 1.0, atol=1.0e-5)):
                raise ValueError("invalid projected old probability at {}".format(key))
            probabilities /= probabilities.sum()
            rows[key] = {
                "trace_id": key[0], "end_index": key[1],
                "source_state_label": source_target,
                "target_label": 1 if source_target == 2 else 0,
                "raw_prediction": 1 if int(source["raw_prediction"]) == 2 else 0,
                "prediction": 1 if int(source["prediction"]) == 2 else 0,
                "probabilities": probabilities,
            }
    return rows


def read_binary(path):
    """Read the new Safe/Critical evidence with strict label/probability checks."""

    rows = {}
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for source in csv.DictReader(stream):
            if source["split"] != "iid_test":
                raise ValueError("binary prediction CSV contains a non-IID row")
            key = (source["trace_id"], int(source["end_index"]))
            if key in rows:
                raise ValueError("duplicate endpoint in binary predictions")
            target = int(source["target_label"])
            state_target = int(source["source_state_label"])
            if target != (1 if state_target == 2 else 0):
                raise ValueError("binary prediction source mapping changed")
            probabilities = np.asarray(
                [float(source["prob_safe"]), float(source["prob_critical"])],
                dtype=np.float64)
            if (not np.all(np.isfinite(probabilities))
                    or np.any(probabilities < 0.0)
                    or not np.isclose(probabilities.sum(), 1.0, atol=1.0e-5)):
                raise ValueError("invalid binary probability at {}".format(key))
            probabilities /= probabilities.sum()
            rows[key] = {
                "trace_id": key[0], "end_index": key[1],
                "source_state_label": state_target, "target_label": target,
                "raw_prediction": int(source["raw_prediction"]),
                "prediction": int(source["prediction"]),
                "probabilities": probabilities,
            }
    return rows


def align_rows(old_rows, binary_rows):
    """Require a complete one-to-one endpoint join and identical projected truth."""

    if (len(old_rows) != EXPECTED_ENDPOINTS or len(binary_rows) != EXPECTED_ENDPOINTS
            or set(old_rows) != set(binary_rows)):
        raise ValueError("comparison requires exactly 22,512 aligned IID endpoints")
    keys = sorted(old_rows)
    for key in keys:
        old, binary = old_rows[key], binary_rows[key]
        if (old["source_state_label"] != binary["source_state_label"]
                or old["target_label"] != binary["target_label"]):
            raise ValueError("truth mismatch at aligned endpoint {}".format(key))
    return keys


def score(rows, keys, decision_field):
    """Compute complete binary window/event metrics for one frozen decision."""

    labels = np.asarray([rows[key]["target_label"] for key in keys])
    predictions = np.asarray([rows[key][decision_field] for key in keys])
    probabilities = np.stack([rows[key]["probabilities"] for key in keys])
    event_rows = [{"trace_id": key[0], "end_index": key[1],
                   "target_label": rows[key]["target_label"],
                   "prediction": rows[key][decision_field]}
                  for key in keys]
    return {"window": binary_window_metrics(labels, predictions, probabilities),
            "events": binary_event_metrics(event_rows)}


def paired_disagreements(old_rows, binary_rows, keys, decision_field):
    """Return paired correctness and directional decision disagreements."""

    counts = {"agreement": 0, "disagreement": 0,
              "old_safe_binary_critical": 0,
              "old_critical_binary_safe": 0,
              "both_correct": 0, "both_wrong": 0,
              "old_only_correct": 0, "binary_only_correct": 0}
    for key in keys:
        truth = old_rows[key]["target_label"]
        old_prediction = old_rows[key][decision_field]
        binary_prediction = binary_rows[key][decision_field]
        if old_prediction == binary_prediction:
            counts["agreement"] += 1
        else:
            counts["disagreement"] += 1
            direction = ("old_safe_binary_critical" if old_prediction == 0
                         else "old_critical_binary_safe")
            counts[direction] += 1
        old_correct = old_prediction == truth
        binary_correct = binary_prediction == truth
        correctness = ("both_correct" if old_correct and binary_correct
                       else "both_wrong" if not old_correct and not binary_correct
                       else "old_only_correct" if old_correct
                       else "binary_only_correct")
        counts[correctness] += 1
    return counts


def format_value(value):
    """Format report values consistently without hiding full JSON precision."""

    if value is None:
        return "N/A"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    return "{:.6f}".format(float(value))


def markdown_report(report):
    """Render complete scalar comparison tables for human review."""

    models = report["models"]
    variants = [("Old 3-class projected, raw", models["old_projected"]["raw"]),
                ("Binary, raw", models["binary"]["raw"]),
                ("Old 3-class projected, post", models["old_projected"]["postprocessed"]),
                ("Binary, post", models["binary"]["postprocessed"])]
    lines = ["# Frozen IID Safe/Critical Comparison", "",
             "This report projects the already-frozen three-class output as "
             "Safe/Warning -> non-Critical and Critical -> Critical. No model "
             "was rerun and no parameter was tuned on IID.", "",
             "## Window Metrics", "",
             "| Metric | Old raw | Binary raw | Old post | Binary post |",
             "| --- | ---: | ---: | ---: | ---: |"]
    window_fields = [
        ("Accuracy", "accuracy"), ("Balanced accuracy", "balanced_accuracy"),
        ("Macro-F1", "macro_f1"), ("Weighted F1", "weighted_f1"),
        ("MCC", "matthews_correlation_coefficient"),
        ("Safe FAR", "safe_window_false_alarm_rate"),
        ("Critical false-negative rate", "critical_false_negative_rate"),
        ("Specificity", "specificity"),
        ("Negative predictive value", "negative_predictive_value"),
        ("Critical precision", "critical_precision"),
        ("Critical recall", "critical_recall"),
        ("Safe precision", ("per_class", "0", "precision")),
        ("Safe recall", ("per_class", "0", "recall")),
        ("Safe F1", ("per_class", "0", "f1")),
        ("Critical F1", ("per_class", "1", "f1")),
    ]
    for label, field in window_fields:
        path = (field,) if isinstance(field, str) else field
        values = []
        for _, metrics in variants:
            value = metrics["window"]
            for part in path:
                value = value[part]
            values.append(format_value(value))
        lines.append("| {} | {} |".format(label, " | ".join(values)))

    lines.extend(["", "## Probability Metrics", "",
                  "Probability metrics are operating-point independent, so raw "
                  "and postprocessed values are identical within each model.", "",
                  "| Metric | Old projected | Binary |", "| --- | ---: | ---: |"])
    probability_fields = [
        ("Critical PR-AUC", "critical_pr_auc"),
        ("Safe PR-AUC", ("pr_auc_ovr", "0")),
        ("Macro PR-AUC", "macro_pr_auc_ovr"),
        ("Critical ROC-AUC", "critical_roc_auc"),
        ("Safe ROC-AUC", ("roc_auc_ovr", "0")),
        ("Macro ROC-AUC", "macro_roc_auc_ovr"),
        ("Log loss", "log_loss"), ("Binary Brier score", "binary_brier_score"),
        ("ECE (15 bins)", ("calibration", "ece")),
    ]
    for label, field in probability_fields:
        path = (field,) if isinstance(field, str) else field
        values = []
        for model_name in ("old_projected", "binary"):
            value = models[model_name]["raw"]["window"]
            for part in path:
                value = value[part]
            values.append(format_value(value))
        lines.append("| {} | {} |".format(label, " | ".join(values)))

    lines.extend(["", "## Confusion Matrices", "",
                  "| Variant | TN | FP | FN | TP |",
                  "| --- | ---: | ---: | ---: | ---: |"])
    for label, metrics in variants:
        matrix = metrics["window"]["confusion_matrix"]
        lines.append("| {} | {} | {} | {} | {} |".format(
            label, matrix[0][0], matrix[0][1], matrix[1][0], matrix[1][1]))

    lines.extend(["", "## Event Metrics", "",
                  "| Metric | Old raw | Binary raw | Old post | Binary post |",
                  "| --- | ---: | ---: | ---: | ---: |"])
    event_fields = [
        ("Critical events", "critical_event_count"),
        ("Critical event detection", "critical_event_detection_rate"),
        ("Median Critical delay (ns)", "median_critical_delay_ns"),
        ("P95 Critical delay (ns)", "p95_critical_delay_ns"),
        ("False-alarm episodes", "false_alarm_episodes"),
        ("False alarms / trace", "false_alarms_per_trace"),
        ("Mean recovery delay (samples)", "mean_recovery_delay_samples"),
    ]
    for label, field in event_fields:
        values = [format_value(metrics["events"][field]) for _, metrics in variants]
        lines.append("| {} | {} |".format(label, " | ".join(values)))

    lines.extend(["", "## Paired Disagreements", "",
                  "| Count | Raw | Postprocessed |", "| --- | ---: | ---: |"])
    for field in ("agreement", "disagreement", "old_safe_binary_critical",
                  "old_critical_binary_safe", "both_correct", "both_wrong",
                  "old_only_correct", "binary_only_correct"):
        lines.append("| {} | {} | {} |".format(
            field, report["paired_disagreements"]["raw"][field],
            report["paired_disagreements"]["postprocessed"][field]))
    lines.extend(["", "## Integrity", "",
                  "- Aligned IID endpoints: {}".format(report["aligned_endpoint_count"]),
                  "- `parameters_tuned_on_test=false`",
                  "- `pristine_blind_test=false`",
                  "- `rerun_authorized=false`", ""])
    return "\n".join(lines)


def parse_args():
    """Parse frozen evidence paths and a new, absent report directory."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-predictions", required=True, type=Path)
    parser.add_argument("--old-report", required=True, type=Path)
    parser.add_argument("--binary-predictions", required=True, type=Path)
    parser.add_argument("--binary-report", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main():
    """Build and atomically publish the frozen, non-tuning comparison."""

    args = parse_args()
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite frozen IID comparison")
    old_report = read_json(args.old_report)
    binary_report = read_json(args.binary_report)
    validate_report_boundary(old_report, binary_report,
                             args.old_predictions, args.binary_predictions)
    old_rows = read_old_projected(args.old_predictions)
    binary_rows = read_binary(args.binary_predictions)
    keys = align_rows(old_rows, binary_rows)
    report = {
        "schema_version": 1,
        "scope": "frozen_iid_reporting_only",
        "projection": {"source_0": 0, "source_1": 0, "source_2": 1},
        "parameters_tuned_on_test": False,
        "pristine_blind_test": False,
        "rerun_authorized": False,
        "aligned_endpoint_count": len(keys),
        "trace_count": len({key[0] for key in keys}),
        "models": {
            "old_projected": {
                "raw": score(old_rows, keys, "raw_prediction"),
                "postprocessed": score(old_rows, keys, "prediction"),
            },
            "binary": {
                "raw": score(binary_rows, keys, "raw_prediction"),
                "postprocessed": score(binary_rows, keys, "prediction"),
            },
        },
        "paired_disagreements": {
            "raw": paired_disagreements(
                old_rows, binary_rows, keys, "raw_prediction"),
            "postprocessed": paired_disagreements(
                old_rows, binary_rows, keys, "prediction"),
        },
        "inputs": {
            "old_predictions_sha256": sha256_file(args.old_predictions),
            "old_report_sha256": sha256_file(args.old_report),
            "binary_predictions_sha256": sha256_file(args.binary_predictions),
            "binary_report_sha256": sha256_file(args.binary_report),
        },
    }

    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = Path(tempfile.mkdtemp(
        prefix=".{}.tmp.".format(args.output_dir.name),
        dir=str(args.output_dir.parent)))
    try:
        (temporary_output / "comparison.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (temporary_output / "FINAL_REPORT.md").write_text(
            markdown_report(report), encoding="utf-8")
        os.rename(str(temporary_output), str(args.output_dir))
    finally:
        if temporary_output.exists():
            shutil.rmtree(str(temporary_output))


if __name__ == "__main__":
    main()
