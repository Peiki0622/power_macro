#!/usr/bin/env python3
"""Causal probability filtering and hysteretic three-state event detection."""

from __future__ import print_function

from collections import defaultdict, deque

import numpy as np


def causal_filter(values, kind, window=1, alpha=1.0):
    """Filter one scalar trace using only the current and preceding values.

    Args:
        values: Chronological scalar scores for exactly one trace.
        kind: ``raw``, ``mean``, ``median``, or ``ewma``.
        window: Trailing-window width for mean/median.  At trace startup the
            filter uses all currently available values instead of padding with
            zeros, which would introduce an artificial Safe bias.
        alpha: EWMA weight assigned to the current observation.

    Returns:
        Float64 array with one output per input.  No centered or future sample
        is consulted, preserving the online detector's causal contract.
    """

    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("causal filter expects one finite scalar sequence")
    if kind == "raw":
        return values.copy()
    if kind == "ewma":
        if not 0.0 < float(alpha) <= 1.0:
            raise ValueError("EWMA alpha must be in (0,1]")
        output = np.empty_like(values)
        if not len(values):
            return output
        output[0] = values[0]
        for index in range(1, len(values)):
            output[index] = float(alpha) * values[index] + (1.0 - float(alpha)) * output[index - 1]
        return output
    if kind not in {"mean", "median"} or int(window) < 1:
        raise ValueError("unknown filter or invalid trailing window")

    # A deque makes the causal boundary explicit and avoids repeatedly slicing
    # an ever-growing prefix.  The formal traces contain fewer than 500 eligible
    # endpoints, so median recomputation over at most nine values is bounded.
    history = deque(maxlen=int(window))
    output = np.empty_like(values)
    for index, value in enumerate(values):
        history.append(float(value))
        output[index] = float(np.mean(history) if kind == "mean" else np.median(history))
    return output


def filter_trace_scores(rows, config):
    """Return filtered Risk and Critical scores for one chronological trace."""

    ordered = sorted(rows, key=lambda row: int(row["end_index"]))
    probabilities = np.asarray([[float(row["prob_safe"]), float(row["prob_warning"]),
                                 float(row["prob_critical"])] for row in ordered], dtype=np.float64)
    if probabilities.shape != (len(ordered), 3) or not np.all(np.isfinite(probabilities)):
        raise ValueError("trace probabilities must be finite [N,3] values")
    sums = probabilities.sum(axis=1, keepdims=True)
    if np.any(probabilities < 0.0) or np.any(sums <= 0.0) or not np.allclose(sums, 1.0, atol=1.0e-5):
        raise ValueError("trace probabilities are outside the persisted precision contract")
    probabilities = probabilities / sums
    risk = probabilities[:, 1] + probabilities[:, 2]
    critical = probabilities[:, 2]
    filter_config = config["filter"]
    return (ordered,
            causal_filter(risk, filter_config["kind"], filter_config.get("window", 1), filter_config.get("alpha", 1.0)),
            causal_filter(critical, filter_config["kind"], filter_config.get("window", 1), filter_config.get("alpha", 1.0)))


def detect_trace(rows, config):
    """Apply one hysteretic detector to exactly one trace.

    State 0 is Safe, state 1 is Warning, and state 2 is Critical.  Entering the
    active region requires ``k_on`` consecutive filtered Risk scores above the
    on-threshold.  Recovery requires ``k_off`` consecutive scores below the
    lower off-threshold.  Warning/Critical transitions occur only while active
    and use their own 0.1-wide hysteresis, preventing severity chatter without
    changing whether an alarm episode exists.
    """

    ordered, risk_scores, critical_scores = filter_trace_scores(rows, config)
    risk_on = float(config["risk_on"])
    risk_off = float(config["risk_off"])
    critical_on = float(config["critical_on"])
    critical_off = float(config.get("critical_off", max(0.05, critical_on - 0.10)))
    k_on = int(config["k_on"])
    k_off = int(config["k_off"])
    if not 0.0 <= risk_off < risk_on <= 1.0:
        raise ValueError("risk hysteresis requires 0 <= off < on <= 1")
    if not 0.0 <= critical_off < critical_on <= 1.0 or k_on < 1 or k_off < 1:
        raise ValueError("invalid Critical hysteresis or confirmation count")

    state = 0
    activation_streak = 0
    recovery_streak = 0
    output = []
    for row, risk_score, critical_score in zip(ordered, risk_scores, critical_scores):
        if state == 0:
            activation_streak = activation_streak + 1 if risk_score >= risk_on else 0
            if activation_streak >= k_on:
                state = 2 if critical_score >= critical_on else 1
                activation_streak = 0
                recovery_streak = 0
        else:
            recovery_streak = recovery_streak + 1 if risk_score <= risk_off else 0
            if recovery_streak >= k_off:
                state = 0
                activation_streak = 0
                recovery_streak = 0
            elif state == 1 and critical_score >= critical_on:
                state = 2
            elif state == 2 and critical_score <= critical_off:
                state = 1
        output.append({**row, "raw_prediction": int(row["prediction"]), "prediction": int(state),
                       "filtered_risk_score": float(risk_score),
                       "filtered_critical_score": float(critical_score)})
    return output


def filter_rows(rows, filter_config):
    """Filter every trace once and attach reusable causal score columns.

    Threshold tuning evaluates hundreds of hysteresis settings for the same
    filter.  Materializing the two filtered scalar columns once per filter is
    both faster and semantically cleaner than recomputing median/EWMA histories
    for every threshold combination.
    """

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["trace_id"]].append(row)
    output = []
    score_config = {"filter": filter_config}
    for trace_id in sorted(grouped):
        ordered, risk_scores, critical_scores = filter_trace_scores(grouped[trace_id], score_config)
        for row, risk_score, critical_score in zip(ordered, risk_scores, critical_scores):
            output.append({**row, "filtered_risk_score": float(risk_score),
                           "filtered_critical_score": float(critical_score)})
    return output


def detect_filtered_trace(rows, config):
    """Run only the hysteretic state machine on prefiltered rows from one trace."""

    ordered = sorted(rows, key=lambda row: int(row["end_index"]))
    risk_on = float(config["risk_on"])
    risk_off = float(config["risk_off"])
    critical_on = float(config["critical_on"])
    critical_off = float(config.get("critical_off", max(0.05, critical_on - 0.10)))
    k_on = int(config["k_on"])
    k_off = int(config["k_off"])
    if not 0.0 <= risk_off < risk_on <= 1.0:
        raise ValueError("risk hysteresis requires 0 <= off < on <= 1")
    if not 0.0 <= critical_off < critical_on <= 1.0 or k_on < 1 or k_off < 1:
        raise ValueError("invalid Critical hysteresis or confirmation count")

    state = 0
    activation_streak = 0
    recovery_streak = 0
    output = []
    for row in ordered:
        risk_score = float(row["filtered_risk_score"])
        critical_score = float(row["filtered_critical_score"])
        if state == 0:
            activation_streak = activation_streak + 1 if risk_score >= risk_on else 0
            if activation_streak >= k_on:
                state = 2 if critical_score >= critical_on else 1
                activation_streak = 0
                recovery_streak = 0
        else:
            recovery_streak = recovery_streak + 1 if risk_score <= risk_off else 0
            if recovery_streak >= k_off:
                state = 0
                activation_streak = 0
                recovery_streak = 0
            elif state == 1 and critical_score >= critical_on:
                state = 2
            elif state == 2 and critical_score <= critical_off:
                state = 1
        output.append({**row, "raw_prediction": int(row["prediction"]), "prediction": int(state)})
    return output


def apply_hysteresis(rows, config):
    """Apply state transitions to rows already processed by ``filter_rows``."""

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["trace_id"]].append(row)
    output = []
    for trace_id in sorted(grouped):
        output.extend(detect_filtered_trace(grouped[trace_id], config))
    return output


def apply_detector(rows, config):
    """Apply the detector independently to every trace and return stable order."""

    # ``filter_rows`` and ``apply_hysteresis`` each group by trace, creating two
    # explicit reset boundaries: neither numerical filter history nor detector
    # state can leak between independent physical traces.
    return apply_hysteresis(filter_rows(rows, config["filter"]), config)


def filter_complexity(config):
    """Return a deterministic simplicity key used only after metric tie-breaks."""

    kind_rank = {"raw": 0, "mean": 1, "median": 2, "ewma": 3}[config["filter"]["kind"]]
    memory = int(config["filter"].get("window", 1))
    return kind_rank, memory, int(config["k_on"]), int(config["k_off"])
