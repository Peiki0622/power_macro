#!/usr/bin/env python3
"""Chronological metrics for same-sample three-state monitoring."""

from __future__ import print_function

from collections import defaultdict

import numpy as np


SAMPLE_PERIOD_NS = 4.0


def contiguous_intervals(endpoint_labels, predicate):
    """Return inclusive intervals where ordered endpoint labels match a predicate.

    Endpoints need not begin at zero because a causal history of length L has
    no decision before L-1.  A gap in endpoint indices closes the interval,
    preventing accidentally joining events across missing predictions.
    """

    ordered = sorted((int(endpoint), int(label)) for endpoint, label in endpoint_labels)
    intervals = []
    start = previous = None
    for endpoint, label in ordered:
        active = bool(predicate(label))
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


def first_matching(endpoint_predictions, start, end, predicate):
    """Return the first matching prediction inside one inclusive truth event."""

    return next((endpoint for endpoint, prediction in endpoint_predictions
                 if start <= endpoint <= end and predicate(prediction)), None)


def state_event_metrics(rows):
    """Score present-state events, false alarms, delay, and recovery.

    Each row must contain ``trace_id``, ``end_index``, ``target_label``, and
    ``prediction``.  Risk events are contiguous truth labels 1/2; Critical
    events are contiguous truth label 2 intervals.  Detection delay is causal
    and non-negative because there is no future forecast or lead-time credit in
    this task.  False alarms are predicted non-Safe episodes wholly contained
    in Safe truth.  Recovery delay counts samples after a risk event ends until
    the first Safe prediction, with zero assigned when the very next endpoint
    is already Safe.
    """

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["trace_id"]].append((int(row["end_index"]),
                                          int(row["target_label"]),
                                          int(row["prediction"])))
    risk_delays = []
    critical_delays = []
    recovery_delays = []
    risk_total = risk_detected = 0
    critical_total = critical_detected = 0
    false_alarm_episodes = 0
    for trace_rows in grouped.values():
        trace_rows.sort()
        truth = [(endpoint, label) for endpoint, label, _ in trace_rows]
        predictions = [(endpoint, prediction) for endpoint, _, prediction in trace_rows]
        truth_by_endpoint = {endpoint: label for endpoint, label in truth}

        risk_events = contiguous_intervals(truth, lambda label: label != 0)
        critical_events = contiguous_intervals(truth, lambda label: label == 2)
        risk_total += len(risk_events)
        critical_total += len(critical_events)
        for start, end in risk_events:
            alarm = first_matching(predictions, start, end, lambda value: value != 0)
            if alarm is not None:
                risk_detected += 1
                risk_delays.append(alarm - start)
            following = [(endpoint, prediction) for endpoint, prediction in predictions
                         if endpoint > end]
            safe_endpoint = next((endpoint for endpoint, prediction in following
                                  if prediction == 0), None)
            if safe_endpoint is not None:
                recovery_delays.append(max(0, safe_endpoint - end - 1))
        for start, end in critical_events:
            alarm = first_matching(predictions, start, end, lambda value: value == 2)
            if alarm is not None:
                critical_detected += 1
                critical_delays.append(alarm - start)

        # Count each contiguous predicted alarm interval once only when no
        # endpoint in it overlaps true Warning/Critical state.
        predicted_events = contiguous_intervals(predictions, lambda value: value != 0)
        false_alarm_episodes += sum(
            all(truth_by_endpoint.get(endpoint, 0) == 0
                for endpoint in range(start, end + 1))
            for start, end in predicted_events)

    trace_count = len(grouped)
    critical_ns = np.asarray(critical_delays, dtype=np.float64) * SAMPLE_PERIOD_NS
    risk_ns = np.asarray(risk_delays, dtype=np.float64) * SAMPLE_PERIOD_NS
    return {
        "trace_count": trace_count,
        "risk_event_count": risk_total,
        "risk_event_detection_rate": risk_detected / risk_total if risk_total else None,
        "critical_event_count": critical_total,
        "critical_event_detection_rate": critical_detected / critical_total if critical_total else None,
        "median_risk_delay_ns": float(np.median(risk_ns)) if len(risk_ns) else None,
        "p95_risk_delay_ns": float(np.percentile(risk_ns, 95)) if len(risk_ns) else None,
        "median_critical_delay_ns": float(np.median(critical_ns)) if len(critical_ns) else None,
        "p95_critical_delay_ns": float(np.percentile(critical_ns, 95)) if len(critical_ns) else None,
        "false_alarm_episodes": int(false_alarm_episodes),
        "false_alarms_per_trace": false_alarm_episodes / trace_count if trace_count else None,
        "mean_recovery_delay_samples": float(np.mean(recovery_delays)) if recovery_delays else None,
    }
