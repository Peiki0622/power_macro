#!/usr/bin/env python3
"""Comprehensive metrics for Safe/Critical binary state monitoring."""

from __future__ import print_function

from collections import defaultdict

import numpy as np
from sklearn.metrics import (average_precision_score, balanced_accuracy_score,
                             confusion_matrix, f1_score, log_loss,
                             matthews_corrcoef, precision_recall_fscore_support,
                             roc_auc_score)


SAMPLE_PERIOD_NS = 4.0


def calibration_error(labels, critical_probabilities, bin_count=15):
    """Return equal-width expected calibration error for Critical probability.

    Each bin compares mean predicted Critical probability with the observed
    Critical frequency.  Empty bins contribute zero weight.  This definition
    is persisted in reports so calibration results remain reproducible rather
    than depending on an unstated library default.
    """

    labels = np.asarray(labels, dtype=np.int64)
    probabilities = np.asarray(critical_probabilities, dtype=np.float64)
    edges = np.linspace(0.0, 1.0, int(bin_count) + 1)
    error = 0.0
    bins = []
    for index in range(int(bin_count)):
        lower, upper = edges[index], edges[index + 1]
        mask = ((probabilities >= lower) & (probabilities < upper)
                if index + 1 < int(bin_count)
                else (probabilities >= lower) & (probabilities <= upper))
        count = int(np.sum(mask))
        if count:
            confidence = float(np.mean(probabilities[mask]))
            frequency = float(np.mean(labels[mask] == 1))
            error += count / float(len(labels)) * abs(confidence - frequency)
        else:
            confidence = frequency = None
        bins.append({"lower": float(lower), "upper": float(upper),
                     "count": count, "mean_probability": confidence,
                     "critical_frequency": frequency})
    return {"ece": float(error), "bin_count": int(bin_count), "bins": bins}


def binary_window_metrics(labels, predictions, probabilities=None):
    """Compute fixed Safe/Critical operating-point and probability metrics."""

    labels = np.asarray(labels, dtype=np.int64)
    predictions = np.asarray(predictions, dtype=np.int64)
    if (labels.shape != predictions.shape or labels.ndim != 1 or not len(labels)
            or set(np.unique(labels)) - {0, 1}
            or set(np.unique(predictions)) - {0, 1}):
        raise ValueError("binary metrics require aligned non-empty labels in {0,1}")
    precision, recall, f1, support = precision_recall_fscore_support(
        labels, predictions, labels=[0, 1], zero_division=0)
    matrix = confusion_matrix(labels, predictions, labels=[0, 1])
    true_safe, false_critical, false_safe, true_critical = matrix.ravel()
    specificity = true_safe / float(true_safe + false_critical)
    negative_predictive_value = (true_safe / float(true_safe + false_safe)
                                 if true_safe + false_safe else 0.0)
    report = {
        "accuracy": float(np.mean(labels == predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(labels, predictions)),
        "macro_f1": float(f1_score(labels, predictions, labels=[0, 1],
                                    average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(labels, predictions, labels=[0, 1],
                                       average="weighted", zero_division=0)),
        "matthews_correlation_coefficient": float(matthews_corrcoef(labels, predictions)),
        "safe_window_false_alarm_rate": float(false_critical / (true_safe + false_critical)),
        "critical_false_negative_rate": float(false_safe / (false_safe + true_critical)),
        "specificity": float(specificity),
        "negative_predictive_value": float(negative_predictive_value),
        "critical_precision": float(precision[1]),
        "critical_recall": float(recall[1]),
        "confusion_matrix": matrix.tolist(),
        "per_class": {
            str(class_id): {"precision": float(precision[class_id]),
                            "recall": float(recall[class_id]),
                            "f1": float(f1[class_id]),
                            "support": int(support[class_id])}
            for class_id in (0, 1)
        },
    }
    if probabilities is None:
        return report

    probabilities = np.asarray(probabilities, dtype=np.float64)
    if (probabilities.shape != (len(labels), 2)
            or not np.all(np.isfinite(probabilities))
            or np.any(probabilities < 0.0) or np.any(probabilities > 1.0)
            or not np.allclose(probabilities.sum(axis=1), 1.0, atol=1.0e-5)):
        raise ValueError("binary probabilities must be finite [N,2] rows summing to one")
    probabilities = probabilities / probabilities.sum(axis=1, keepdims=True)
    binary = np.eye(2, dtype=np.int64)[labels]
    report["pr_auc_ovr"] = {
        str(class_id): float(average_precision_score(
            binary[:, class_id], probabilities[:, class_id]))
        for class_id in (0, 1)
    }
    report["critical_pr_auc"] = report["pr_auc_ovr"]["1"]
    report["macro_pr_auc_ovr"] = float(np.mean(list(report["pr_auc_ovr"].values())))
    report["roc_auc_ovr"] = {
        str(class_id): float(roc_auc_score(binary[:, class_id], probabilities[:, class_id]))
        for class_id in (0, 1)
    }
    report["critical_roc_auc"] = report["roc_auc_ovr"]["1"]
    report["macro_roc_auc_ovr"] = float(np.mean(list(report["roc_auc_ovr"].values())))
    report["log_loss"] = float(log_loss(labels, probabilities, labels=[0, 1]))
    critical_errors = (probabilities[:, 1] - labels.astype(np.float64)) ** 2
    report["binary_brier_score"] = float(np.mean(critical_errors))
    report["calibration"] = calibration_error(labels, probabilities[:, 1])
    return report


def _intervals(endpoint_values, active_value=1):
    """Return contiguous inclusive intervals equal to one active class."""

    ordered = sorted((int(endpoint), int(value))
                     for endpoint, value in endpoint_values)
    intervals = []
    start = previous = None
    for endpoint, value in ordered:
        active = value == int(active_value)
        if active and (start is None or endpoint != previous + 1):
            if start is not None:
                intervals.append((start, previous))
            start = endpoint
        elif not active and start is not None:
            intervals.append((start, previous))
            start = None
        previous = endpoint
    if start is not None:
        intervals.append((start, previous))
    return intervals


def binary_event_metrics(rows):
    """Score Critical episodes, causal delay, false alarms, and recovery.

    Warning has already been mapped to Safe, so a truth event begins exactly
    when current slack first becomes Critical.  A false alarm is a contiguous
    predicted-Critical episode wholly contained in the binary Safe truth.
    """

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["trace_id"]].append((int(row["end_index"]),
                                          int(row["target_label"]),
                                          int(row["prediction"])))
    event_count = detected = false_alarms = 0
    delays = []
    recovery_delays = []
    for trace_rows in grouped.values():
        trace_rows.sort()
        truth = [(endpoint, label) for endpoint, label, _ in trace_rows]
        predictions = [(endpoint, prediction) for endpoint, _, prediction in trace_rows]
        truth_by_endpoint = dict(truth)
        events = _intervals(truth)
        event_count += len(events)
        for start, end in events:
            alarm = next((endpoint for endpoint, prediction in predictions
                          if start <= endpoint <= end and prediction == 1), None)
            if alarm is not None:
                detected += 1
                delays.append(alarm - start)
            safe_after = next((endpoint for endpoint, prediction in predictions
                               if endpoint > end and prediction == 0), None)
            if safe_after is not None:
                recovery_delays.append(max(0, safe_after - end - 1))
        for start, end in _intervals(predictions):
            if all(truth_by_endpoint.get(endpoint, 0) == 0
                   for endpoint in range(start, end + 1)):
                false_alarms += 1
    delay_ns = np.asarray(delays, dtype=np.float64) * SAMPLE_PERIOD_NS
    trace_count = len(grouped)
    return {
        "trace_count": trace_count,
        "critical_event_count": event_count,
        "critical_event_detection_rate": detected / event_count if event_count else None,
        "median_critical_delay_ns": float(np.median(delay_ns)) if len(delay_ns) else None,
        "p95_critical_delay_ns": float(np.percentile(delay_ns, 95)) if len(delay_ns) else None,
        "false_alarm_episodes": int(false_alarms),
        "false_alarms_per_trace": false_alarms / trace_count if trace_count else None,
        "mean_recovery_delay_samples": (float(np.mean(recovery_delays))
                                         if recovery_delays else None),
    }
