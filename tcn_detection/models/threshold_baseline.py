#!/usr/bin/env python3
"""Transparent sensor-code threshold baselines for the frozen TCN task."""

from __future__ import print_function

import numpy as np
from sklearn.metrics import f1_score


def scores_from_features(features, rule):
    """Return one causal scalar score for each ``[N,5,L]`` input window.

    Args:
        features: Existing online-only sensor tensor.  This function does not
            receive measured VDD, slack, configured droop, or any metadata.
        rule: ``sensor_code`` for the endpoint normalized code, ``delta_code``
            for the endpoint code change, or ``short_history`` for the maximum
            endpoint-or-earlier normalized code over the causal history.

    Returns:
        A length-N Float64 score where larger values imply higher risk.
    """

    if rule == "sensor_code":
        return features[:, 0, -1].astype(np.float64)
    if rule == "delta_code":
        return features[:, 1, -1].astype(np.float64)
    if rule == "short_history":
        return features[:, 0, :].max(axis=1).astype(np.float64)
    raise ValueError("unknown threshold rule: {}".format(rule))


def predict_from_thresholds(scores, warning_threshold, critical_threshold):
    """Map one monotonic score into Safe/Warning/Critical ordinal predictions."""

    if warning_threshold > critical_threshold:
        raise ValueError("warning threshold must not exceed critical threshold")
    result = np.zeros(len(scores), dtype=np.int64)
    result[scores >= warning_threshold] = 1
    result[scores >= critical_threshold] = 2
    return result


def candidate_thresholds(scores, quantile_count=41):
    """Generate bounded validation-only thresholds including always-safe/risk ends."""

    quantiles = np.linspace(0.0, 1.0, int(quantile_count))
    values = np.unique(np.quantile(scores, quantiles))
    margin = max(1.0e-9, float(np.max(values) - np.min(values)) * 1.0e-6)
    return np.concatenate(([values[0] - margin], values, [values[-1] + margin]))


def calibrate_thresholds(validation_features, validation_labels, rule):
    """Select two ordinal thresholds exclusively by validation macro-F1.

    The deterministic tie break prefers lower Warning then lower Critical
    thresholds.  It is intentionally fixed before any test data is read,
    preventing an apparently simple baseline from being tuned on IID or OOD
    results after the fact.
    """

    scores = scores_from_features(validation_features, rule)
    candidates = candidate_thresholds(scores)
    best = None
    for warning_index, warning_threshold in enumerate(candidates):
        for critical_threshold in candidates[warning_index:]:
            predictions = predict_from_thresholds(scores, warning_threshold, critical_threshold)
            macro_f1 = float(f1_score(validation_labels, predictions, labels=[0, 1, 2], average="macro", zero_division=0))
            key = (macro_f1, -float(warning_threshold), -float(critical_threshold))
            if best is None or key > best[0]:
                best = (key, float(warning_threshold), float(critical_threshold))
    return {"rule": rule, "warning_threshold": best[1], "critical_threshold": best[2],
            "validation_macro_f1": best[0][0], "candidate_count": int(len(candidates))}
