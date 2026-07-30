#!/usr/bin/env python3
"""Tune causal TCN postprocessing with trace-level validation cross-validation."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.evaluate.metrics import event_metrics, risk_events, window_metrics
from power_macro.tcn_detection.evaluate.postprocess import (apply_detector, apply_hysteresis, filter_complexity,
                                                            filter_rows)
from power_macro.tcn_detection.evaluate.validation_metrics import (read_prediction_rows, read_validation_corpus,
                                                                    read_validation_truth)


def sha256_file(path):
    """Hash one immutable input with bounded memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def filter_grid():
    """Return the fixed causal filter family from the approved plan."""

    result = [{"kind": "raw", "window": 1}]
    result.extend({"kind": "mean", "window": window} for window in (3, 5, 9))
    result.extend({"kind": "median", "window": window} for window in (3, 5, 9))
    result.extend({"kind": "ewma", "alpha": alpha, "window": 1} for alpha in (0.25, 0.50, 0.75))
    return result


def alarm_grid(filter_config):
    """Yield every filter/Risk-hysteresis/confirmation combination.

    Critical severity does not affect whether a state is Safe or active, hence
    it cannot change event detection, event false alarms, lead time, or Safe
    window false alarms.  Searching the alarm layer first and the six Critical
    thresholds second is therefore exactly equivalent to the relevant full
    Cartesian search while avoiding redundant event calculations.
    """

    for risk_on in (0.30, 0.40, 0.50, 0.60, 0.70, 0.80):
        for delta in (0.05, 0.10, 0.20):
            risk_off = max(0.0, risk_on - delta)
            for k_on in (1, 3, 5, 9):
                for k_off in (1, 3, 5):
                    yield {"filter": filter_config, "risk_on": risk_on, "risk_off": risk_off,
                           "critical_on": 0.50, "critical_off": 0.40,
                           "k_on": k_on, "k_off": k_off}


def subset_rows(rows, trace_ids):
    """Select complete traces without changing chronological row order."""

    allowed = set(trace_ids)
    return [row for row in rows if row["trace_id"] in allowed]


def score_processed(processed, truth, corpus, trace_ids):
    """Calculate the metrics used by the constrained selection rule."""

    labels = np.asarray([row["target_label"] for row in processed], dtype=np.int64)
    predictions = np.asarray([row["prediction"] for row in processed], dtype=np.int64)
    window = window_metrics(labels, predictions)
    events = event_metrics(processed, truth, corpus, confirm_count=1, trace_ids=set(trace_ids))
    return window, events


def alarm_selection_key(config, window, events):
    """Implement the safety-balanced lexicographic operating objective."""

    recall = events["critical_event_detection_rate"] or 0.0
    lead = events["median_lead_time_ns"]
    feasible = recall >= 0.90 and lead is not None and lead > 0.0
    if feasible:
        return (0, events["false_alarms_per_trace"], window["safe_window_false_alarm_rate"],
                -window["balanced_accuracy"], filter_complexity(config))
    # If a fold contains too few critical events for any configuration to meet
    # the hard constraint, retain the safest high-recall diagnostic candidate.
    # The aggregate OOF gate remains strict and cannot pass through this fallback.
    return (1, -recall, -(lead if lead is not None else -1.0e9),
            events["false_alarms_per_trace"], window["safe_window_false_alarm_rate"],
            filter_complexity(config))


def tune_on_traces(rows, truth, corpus, trace_ids):
    """Search one training-fold subset and return its selected detector config."""

    selected_rows = subset_rows(rows, trace_ids)
    best = None
    candidates_evaluated = 0
    for filter_config in filter_grid():
        # Filtering is independent of thresholds.  Reusing these columns turns
        # the expensive median/EWMA work from 216 repetitions per filter into a
        # single pass while preserving every point in the approved search grid.
        filtered_rows = filter_rows(selected_rows, filter_config)
        for config in alarm_grid(filter_config):
            processed = apply_hysteresis(filtered_rows, config)
            window, events = score_processed(processed, truth, corpus, trace_ids)
            key = alarm_selection_key(config, window, events)
            candidates_evaluated += 1
            if best is None or key < best[0]:
                best = (key, config, window, events)

    # Severity tuning cannot change active/Safe episodes.  Choose the threshold
    # that maximizes balanced three-class behavior after the alarm layer is fixed.
    severity_best = None
    for critical_on in (0.30, 0.40, 0.50, 0.60, 0.70, 0.80):
        config = {**best[1], "critical_on": critical_on,
                  "critical_off": max(0.05, critical_on - 0.10)}
        # Recompute only the selected filter once; severity candidates reuse it
        # because changing Critical thresholds does not alter filtered scores.
        selected_filtered = filter_rows(selected_rows, config["filter"])
        processed = apply_hysteresis(selected_filtered, config)
        window, events = score_processed(processed, truth, corpus, trace_ids)
        key = (-window["balanced_accuracy"], -window["macro_f1"], -window["critical_recall"], critical_on)
        if severity_best is None or key < severity_best[0]:
            severity_best = (key, config, window, events)
    return {"config": severity_best[1], "window": severity_best[2], "events": severity_best[3],
            "alarm_candidates_evaluated": candidates_evaluated, "severity_candidates_evaluated": 6}


def tune_fold(fold_index, holdout_ids, all_trace_ids, rows, truth, corpus):
    """Tune one fold in an isolated worker and return its complete OOF evidence."""

    training_ids = set(all_trace_ids) - set(holdout_ids)
    tuned = tune_on_traces(rows, truth, corpus, training_ids)
    holdout_processed = apply_detector(subset_rows(rows, holdout_ids), tuned["config"])
    holdout_window, holdout_events = score_processed(holdout_processed, truth, corpus, holdout_ids)
    report = {"fold": fold_index, "training_trace_ids": sorted(training_ids),
              "holdout_trace_ids": holdout_ids, "selected_config": tuned["config"],
              "training_window": tuned["window"], "training_events": tuned["events"],
              "holdout_window": holdout_window, "holdout_events": holdout_events,
              "alarm_candidates_evaluated": tuned["alarm_candidates_evaluated"],
              "severity_candidates_evaluated": tuned["severity_candidates_evaluated"]}
    return fold_index, holdout_processed, report


def make_trace_folds(truth, fold_count=5):
    """Create deterministic severity-stratified trace folds.

    Stratification uses label truth, never model output: traces are grouped as
    Safe-only, non-Critical risk, or containing a Critical event.  Sorted IDs
    are distributed round-robin so repeated runs produce byte-identical folds.
    """

    groups = defaultdict(list)
    for trace_id, rows in truth.items():
        events = risk_events(rows)
        group = "critical" if any(event["critical"] for event in events) else "risk" if events else "safe"
        groups[group].append(trace_id)
    folds = [[] for _ in range(int(fold_count))]
    for group in ("critical", "risk", "safe"):
        for index, trace_id in enumerate(sorted(groups[group])):
            folds[index % int(fold_count)].append(trace_id)
    return [sorted(fold) for fold in folds]


def bootstrap_metrics(rows, truth, corpus, repetitions=1000, seed=20260725):
    """Return trace-resampled confidence intervals for the four gate metrics."""

    trace_ids = sorted({row["trace_id"] for row in rows})
    by_trace = {trace_id: subset_rows(rows, {trace_id}) for trace_id in trace_ids}
    contributions = {}
    for trace_id in trace_ids:
        trace_rows = by_trace[trace_id]
        events = event_metrics(trace_rows, truth, corpus, confirm_count=1, trace_ids={trace_id})
        safe = [row for row in trace_rows if int(row["target_label"]) == 0]
        contributions[trace_id] = {
            "events": events["event_count"],
            "detected": events["event_detection_rate"] * events["event_count"] if events["event_count"] else 0.0,
            "critical": events["critical_event_count"],
            "critical_detected": events["critical_event_detection_rate"] * events["critical_event_count"]
            if events["critical_event_count"] else 0.0,
            "false_alarms": events["false_alarms"], "lead_times": events["lead_times_ns"],
            "safe_windows": len(safe),
            "safe_false": sum(int(row["prediction"]) != 0 for row in safe),
        }
    generator = np.random.default_rng(int(seed))
    samples = defaultdict(list)
    for _ in range(int(repetitions)):
        chosen = generator.choice(trace_ids, size=len(trace_ids), replace=True)
        values = [contributions[trace_id] for trace_id in chosen]
        critical = sum(item["critical"] for item in values)
        leads = [lead for item in values for lead in item["lead_times"]]
        safe_windows = sum(item["safe_windows"] for item in values)
        samples["critical_event_detection_rate"].append(
            sum(item["critical_detected"] for item in values) / critical if critical else np.nan)
        samples["false_alarms_per_trace"].append(sum(item["false_alarms"] for item in values) / len(values))
        samples["median_lead_time_ns"].append(float(np.median(leads)) if leads else np.nan)
        samples["safe_window_false_alarm_rate"].append(
            sum(item["safe_false"] for item in values) / safe_windows if safe_windows else np.nan)
    return {name: {"lower_95": float(np.nanpercentile(values, 2.5)),
                   "median": float(np.nanpercentile(values, 50.0)),
                   "upper_95": float(np.nanpercentile(values, 97.5))}
            for name, values in samples.items()}


def benchmark_postprocess(rows, config, repetitions=50):
    """Measure median Python postprocessing time per persisted window."""

    timings = []
    for _ in range(int(repetitions)):
        started = time.perf_counter_ns()
        apply_detector(rows, config)
        timings.append((time.perf_counter_ns() - started) / 1.0e6 / len(rows))
    return float(np.median(timings))


def write_predictions(path, rows, fold_by_trace):
    """Persist OOF detector states and filtered scores for audit."""

    fields = ["window_id", "trace_id", "split", "fold", "end_index", "target_label",
              "raw_prediction", "prediction", "filtered_risk_score", "filtered_critical_score"]
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: (item["trace_id"], int(item["end_index"]))):
            writer.writerow({field: fold_by_trace[row["trace_id"]] if field == "fold" else row[field]
                             for field in fields})


def main():
    """Tune with five-fold OOF evaluation, then fit one final validation config."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--label-dir", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite postprocess version directory: {}".format(args.output_dir))

    rows = read_prediction_rows(args.predictions)
    trace_ids = {row["trace_id"] for row in rows}
    truth = read_validation_truth(args.label_dir, trace_ids)
    corpus = read_validation_corpus(args.corpus, trace_ids)
    folds = make_trace_folds(truth)
    fold_by_trace = {trace_id: fold_index for fold_index, fold in enumerate(folds) for trace_id in fold}
    if set(fold_by_trace) != trace_ids or any(not fold for fold in folds):
        raise ValueError("trace fold construction is incomplete")

    oof_rows = []
    fold_reports = []
    # Folds share no fitted state and are safe to evaluate concurrently.  Five
    # workers use a small fraction of the 96-core host while avoiding nested
    # numerical threading; results are sorted by fold before publication.
    with ProcessPoolExecutor(max_workers=len(folds)) as executor:
        futures = [executor.submit(tune_fold, fold_index, holdout_ids, trace_ids, rows, truth, corpus)
                   for fold_index, holdout_ids in enumerate(folds)]
        for future in as_completed(futures):
            fold_index, holdout_processed, fold_report = future.result()
            oof_rows.extend(holdout_processed)
            fold_reports.append(fold_report)
            print("completed postprocess fold {} of {}".format(fold_index + 1, len(folds)), flush=True)
    fold_reports.sort(key=lambda item: item["fold"])

    oof_window, oof_events = score_processed(oof_rows, truth, corpus, trace_ids)
    final = tune_on_traces(rows, truth, corpus, trace_ids)
    final_rows = apply_detector(rows, final["config"])
    final_window, final_events = score_processed(final_rows, truth, corpus, trace_ids)
    latency = benchmark_postprocess(rows, final["config"])
    acceptance = {
        "critical_event_detection_rate_ge_0_90": oof_events["critical_event_detection_rate"] >= 0.90,
        "median_lead_time_ns_gt_0": oof_events["median_lead_time_ns"] is not None and oof_events["median_lead_time_ns"] > 0.0,
        "false_alarms_per_trace_le_2_0": oof_events["false_alarms_per_trace"] <= 2.0,
        "safe_window_false_alarm_rate_le_0_35": oof_window["safe_window_false_alarm_rate"] <= 0.35,
        "postprocess_latency_ms_per_window_lt_0_1": latency < 0.1,
    }
    acceptance["pass"] = all(acceptance.values())
    report = {"schema_version": 1, "scope": "validation_only", "iid_ood_metrics_computed": False,
              "predictions_sha256": sha256_file(args.predictions), "trace_folds": folds,
              "folds": fold_reports, "oof_window": oof_window, "oof_events": oof_events,
              "oof_bootstrap_95": bootstrap_metrics(oof_rows, truth, corpus),
              "final_config": final["config"], "final_window": final_window,
              "final_events": final_events, "postprocess_latency_ms_per_window": latency,
              "acceptance": acceptance}

    args.output_dir.mkdir(parents=True, exist_ok=False)
    temporary_report = args.output_dir / "postprocess_report.json.tmp"
    temporary_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary_report.replace(args.output_dir / "postprocess_report.json")
    temporary_config = args.output_dir / "postprocess_config.json.tmp"
    temporary_config.write_text(json.dumps(final["config"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary_config.replace(args.output_dir / "postprocess_config.json")
    write_predictions(args.output_dir / "oof_predictions.csv", oof_rows, fold_by_trace)
    if not acceptance["pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
