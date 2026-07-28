#!/usr/bin/env python3
"""Window-level and chronological event-level metrics for frozen TCN splits."""

from __future__ import print_function

from collections import defaultdict

import numpy as np
from sklearn.metrics import (average_precision_score, confusion_matrix, f1_score, precision_recall_fscore_support,
                             precision_score, recall_score)


SAMPLE_PERIOD_NS = 4.0


def window_metrics(labels, predictions, probabilities=None):
    """Return fixed three-class classification metrics without dropping absent labels."""

    precision, recall, f1, support = precision_recall_fscore_support(labels, predictions, labels=[0, 1, 2], zero_division=0)
    report = {"macro_f1": float(f1_score(labels, predictions, labels=[0, 1, 2], average="macro", zero_division=0)),
              "accuracy": float(np.mean(np.asarray(labels) == np.asarray(predictions))),
              "confusion_matrix": confusion_matrix(labels, predictions, labels=[0, 1, 2]).tolist(),
              "per_class": {str(class_id): {"precision": float(precision[class_id]), "recall": float(recall[class_id]),
                                             "f1": float(f1[class_id]), "support": int(support[class_id])}
                            for class_id in (0, 1, 2)}}
    if probabilities is not None:
        binary = np.eye(3, dtype=np.int64)[np.asarray(labels, dtype=np.int64)]
        report["pr_auc_ovr"] = {str(class_id): float(average_precision_score(binary[:, class_id], probabilities[:, class_id]))
                                for class_id in (0, 1, 2)}
    return report


def confirmed_alarm_indices(predictions, confirm_count):
    """Return alarm-episode start endpoints for consecutive non-Safe predictions.

    A confirmed episode begins only once after ``confirm_count`` consecutive
    Warning/Critical decisions.  A Safe decision clears the state, allowing a
    later episode to count independently as an event detection or false alarm.
    """

    active = False
    streak = 0
    alarms = []
    for endpoint, prediction in predictions:
        if int(prediction) == 0:
            streak = 0
            active = False
            continue
        streak += 1
        if not active and streak >= int(confirm_count):
            alarms.append(int(endpoint))
            active = True
    return alarms


def risk_events(label_rows):
    """Extract contiguous non-Safe label intervals and their first real violation.

    The event start/end live in label endpoint coordinates, not physical PWL
    time.  A Critical interval's physical first violation is recovered from
    ``time_to_violation_samples`` at its first raw-Critical endpoint, retaining
    the exact future horizon used for the dataset truth label.
    """

    eligible = [row for row in label_rows if row["label_eligible"].lower() == "true"]
    events = []
    index = 0
    while index < len(eligible):
        if int(eligible[index]["hysteresis_label"]) == 0:
            index += 1
            continue
        start = int(eligible[index]["sample_index"])
        segment = []
        while index < len(eligible) and int(eligible[index]["hysteresis_label"]) != 0:
            segment.append(eligible[index])
            index += 1
        end = int(segment[-1]["sample_index"])
        critical_rows = [row for row in segment if row["raw_label"] == "2" and row["time_to_violation_samples"]]
        first_violation = None
        if critical_rows:
            first = critical_rows[0]
            first_violation = int(first["sample_index"]) + int(first["time_to_violation_samples"])
        events.append({"start_index": start, "end_index": end, "first_violation_index": first_violation,
                       "critical": first_violation is not None})
    return events


def event_metrics(prediction_rows, truth_by_trace, corpus_by_trace, confirm_count, trace_ids=None):
    """Calculate chronological detection, false alarm, delay, lead, and recovery metrics.

    Args:
        prediction_rows: Dictionaries containing ``trace_id``, ``end_index``,
            and integer ``prediction``.  They must be chronological after the
            internal sort and must all share the requested frozen split.
        truth_by_trace: Full labelled CSV rows keyed by trace ID.
        corpus_by_trace: Authoritative corpus metadata keyed by trace ID.  The
            optional event's physical ``start_index`` enables attack-to-alarm
            delay without reading configured droop as a model feature.
        confirm_count: K consecutive non-Safe decisions required to alarm.
        trace_ids: Optional trace subset for a severity, duty, family, or mode
            stratum.  No sample is resampled or redistributed.
    """

    grouped = defaultdict(list)
    for row in prediction_rows:
        if trace_ids is None or row["trace_id"] in trace_ids:
            grouped[row["trace_id"]].append((int(row["end_index"]), int(row["prediction"])))
    detected = 0
    total_events = 0
    critical_detected = 0
    total_critical = 0
    false_alarm_count = 0
    lead_times = []
    attack_delays = []
    recovery_persistence = []
    for trace_id, trace_predictions in grouped.items():
        trace_predictions.sort()
        alarms = confirmed_alarm_indices(trace_predictions, confirm_count)
        events = risk_events(truth_by_trace[trace_id])
        total_events += len(events)
        total_critical += sum(event["critical"] for event in events)
        matched_alarms = set()
        for event in events:
            in_event = [alarm for alarm in alarms if event["start_index"] <= alarm <= event["end_index"]]
            if not in_event:
                continue
            alarm = in_event[0]
            matched_alarms.add(alarm)
            detected += 1
            if event["critical"]:
                critical_detected += 1
                lead_times.append((event["first_violation_index"] - alarm) * SAMPLE_PERIOD_NS)
            corpus_event = corpus_by_trace[trace_id].get("event")
            if corpus_event:
                attack_delays.append((alarm - int(corpus_event["start_index"])) * SAMPLE_PERIOD_NS)
        false_alarm_count += sum(alarm not in matched_alarms for alarm in alarms)
        if events:
            last_end = events[-1]["end_index"]
            recovery_persistence.append(sum(prediction != 0 for endpoint, prediction in trace_predictions if endpoint > last_end))
    duration_us = len(grouped) * 500 * SAMPLE_PERIOD_NS / 1000.0
    return {"confirm_count": int(confirm_count), "trace_count": len(grouped), "event_count": total_events,
            "event_detection_rate": float(detected / total_events) if total_events else None,
            "critical_event_count": total_critical,
            "critical_event_detection_rate": float(critical_detected / total_critical) if total_critical else None,
            "critical_event_miss_rate": float(1.0 - critical_detected / total_critical) if total_critical else None,
            "false_alarms": int(false_alarm_count), "false_alarms_per_trace": float(false_alarm_count / len(grouped)) if grouped else None,
            "false_alarms_per_us": float(false_alarm_count / duration_us) if duration_us else None,
            "lead_times_ns": lead_times, "median_lead_time_ns": float(np.median(lead_times)) if lead_times else None,
            "attack_to_alarm_delays_ns": attack_delays, "median_attack_to_alarm_delay_ns": float(np.median(attack_delays)) if attack_delays else None,
            "mean_recovery_persistence_samples": float(np.mean(recovery_persistence)) if recovery_persistence else None}


def choose_confirmation(validation_rows, truth_by_trace, corpus_by_trace, candidates):
    """Select K on validation only, requiring at least one positive Critical lead.

    Candidates with a Critical detection and positive median lead satisfy the
    plan's timing-safety constraint.  Among those, false alarms per microsecond
    are minimized; ties favor Critical detection rate, macro-F1-neutral smaller
    K, and then less confirmation delay.  If no K preserves positive lead, K=1
    is returned only as a diagnostic and the explicit failure flag remains set.
    """

    scanned = [event_metrics(validation_rows, truth_by_trace, corpus_by_trace, candidate) for candidate in candidates]
    valid = [item for item in scanned if item["critical_event_detection_rate"] and item["median_lead_time_ns"] and item["median_lead_time_ns"] > 0.0]
    if not valid:
        return {"selected_confirm_count": 1, "positive_lead_available": False, "scan": scanned}
    selected = min(valid, key=lambda item: (item["false_alarms_per_us"], -item["critical_event_detection_rate"], item["confirm_count"]))
    return {"selected_confirm_count": selected["confirm_count"], "positive_lead_available": True, "scan": scanned}


def hard_pair_metrics(prediction_rows, corpus_by_trace):
    """Score paired decisions at the first post-decision endpoint with divergent truth.

    Both members of a hard pair share observable prefix samples before the
    recorded decision index.  The score waits for the first endpoint at or
    after that index whose truth labels differ, then requires both predictions
    to match their own labels.  This exposes whether a detector reacts to the
    diverging temporal development rather than a single common prefix code.
    """

    by_trace = defaultdict(dict)
    labels = defaultdict(dict)
    for row in prediction_rows:
        by_trace[row["trace_id"]][int(row["end_index"])] = int(row["prediction"])
        labels[row["trace_id"]][int(row["end_index"])] = int(row["target_label"])
    pairs = defaultdict(list)
    for trace_id, metadata in corpus_by_trace.items():
        if metadata.get("hard_pair_id"):
            pairs[metadata["hard_pair_id"]].append(trace_id)
    outcomes = []
    for pair_id, members in sorted(pairs.items()):
        if len(members) != 2:
            continue
        left, right = members
        decision = int(corpus_by_trace[left]["hard_pair_decision_index"])
        candidates = sorted(set(labels[left]) & set(labels[right]))
        endpoint = next((value for value in candidates if value >= decision and labels[left][value] != labels[right][value]), None)
        if endpoint is None:
            outcomes.append({"hard_pair_id": pair_id, "scorable": False})
            continue
        correct = by_trace[left].get(endpoint) == labels[left][endpoint] and by_trace[right].get(endpoint) == labels[right][endpoint]
        outcomes.append({"hard_pair_id": pair_id, "scorable": True, "end_index": endpoint, "pair_correct": bool(correct),
                         "left_label": labels[left][endpoint], "right_label": labels[right][endpoint]})
    scored = [item for item in outcomes if item["scorable"]]
    return {"pair_count": len(outcomes), "scorable_pair_count": len(scored),
            "pair_accuracy": float(np.mean([item["pair_correct"] for item in scored])) if scored else None, "pairs": outcomes}
