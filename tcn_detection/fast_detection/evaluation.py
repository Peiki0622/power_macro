#!/usr/bin/env python3
"""Shared chronological metrics and deterministic candidate selection."""

from __future__ import print_function

from collections import defaultdict

import numpy as np

from power_macro.tcn_detection.evaluate.binary_metrics import binary_window_metrics


SAMPLE_PERIOD_NS = 4.0


def replay_detector(detector, trace):
    """Replay one complete trace and retain every causal endpoint decision."""

    detector.reset(trace.metadata)
    rows = []
    previous_alarm = False
    first_alarm = None
    for sample in trace.samples:
        alarm = bool(detector.step(sample.sensor_code, sample.valid))
        rising = alarm and not previous_alarm
        if rising and first_alarm is None:
            first_alarm = int(sample.sample_index)
        rows.append({
            "trace_id": trace.metadata.trace_id,
            "split": trace.metadata.split,
            "end_index": int(sample.sample_index),
            "target_label": int(sample.target_label),
            "prediction": int(alarm),
            "alarm_start": bool(rising),
            "first_alarm_index": first_alarm,
            "valid": bool(sample.valid),
        })
        previous_alarm = alarm
    return rows


def _intervals(rows, field):
    """Extract contiguous one-valued intervals from a chronological row list."""

    intervals = []
    start = None
    previous = None
    for row in sorted(rows, key=lambda item: int(item["end_index"])):
        endpoint = int(row["end_index"])
        active = int(row[field]) == 1
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


def event_metrics(rows):
    """Compute event recall, delay distribution, false alarms and occupancy.

    A critical event is a contiguous current-state Critical interval.  An alarm
    is counted as detecting it when any alarm endpoint lies inside the interval.
    A false-alarm episode is an alarm interval wholly contained in Safe truth;
    this is the same episode convention used by the existing binary metrics.
    """

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["trace_id"]].append(row)
    delays = []
    false_alarms = 0
    event_count = 0
    detected = 0
    for trace_rows in grouped.values():
        ordered = sorted(trace_rows, key=lambda item: int(item["end_index"]))
        truth_events = _intervals(ordered, "target_label")
        alarm_events = _intervals(ordered, "prediction")
        event_count += len(truth_events)
        for start, end in truth_events:
            alarm = next((int(row["end_index"]) for row in ordered
                          if start <= int(row["end_index"]) <= end
                          and int(row["prediction"]) == 1), None)
            if alarm is not None:
                detected += 1
                delays.append(alarm - start)
        truth_by_endpoint = {int(row["end_index"]): int(row["target_label"])
                             for row in ordered}
        for start, end in alarm_events:
            if all(truth_by_endpoint.get(endpoint, 0) == 0
                   for endpoint in range(start, end + 1)):
                false_alarms += 1
    delay_ns = [float(value) * SAMPLE_PERIOD_NS for value in delays]
    alarm_count = sum(int(row["prediction"]) for row in rows)
    return {
        "trace_count": len(grouped),
        "critical_event_count": event_count,
        "event_recall": float(detected / event_count) if event_count else None,
        "median_ttd_ns": float(np.median(delay_ns)) if delay_ns else None,
        "p95_ttd_ns": float(np.percentile(delay_ns, 95)) if delay_ns else None,
        "maximum_ttd_ns": float(max(delay_ns)) if delay_ns else None,
        "false_alarms": int(false_alarms),
        "false_alarms_per_trace": float(false_alarms / len(grouped)) if grouped else None,
        "alarm_occupancy": float(alarm_count / len(rows)) if rows else None,
        "detected_event_count": int(detected),
    }


def evaluate_detector(detector_factory, traces, common_window_start=31):
    """Return common-window and full-stream metrics for one frozen factory."""

    rows = []
    for trace in traces:
        rows.extend(replay_detector(detector_factory(), trace))
    common = [row for row in rows if int(row["end_index"]) >= int(common_window_start)]
    labels = np.asarray([row["target_label"] for row in common], dtype=np.int64)
    predictions = np.asarray([row["prediction"] for row in common], dtype=np.int64)
    return {"window": binary_window_metrics(labels, predictions),
            "events": event_metrics(rows), "rows": rows}


def selection_key(result, name):
    """Sort validation candidates by FAR gate, recall, latency and stable name."""

    window = result["window"]
    events = result["events"]
    far_pass = float(window["safe_window_false_alarm_rate"]) <= 0.05
    return (0 if far_pass else 1,
            -(float(events["event_recall"]) if events["event_recall"] is not None else -1.0),
            float(events["p95_ttd_ns"] if events["p95_ttd_ns"] is not None else float("inf")),
            str(name))
