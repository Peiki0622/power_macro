#!/usr/bin/env python3
"""Five-fold validation tuning for causal current-state postprocessing."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.evaluate.metrics import window_metrics
from power_macro.tcn_detection.evaluate.postprocess import (
    apply_detector, apply_hysteresis, filter_complexity, filter_rows)
from power_macro.tcn_detection.evaluate.state_metrics import (
    contiguous_intervals, state_event_metrics)
from power_macro.tcn_detection.evaluate.validation_metrics import read_prediction_rows
from power_macro.tcn_detection.dataset.repartition_state_iid import DisjointSet


def sha256_file(path):
    """Hash a frozen candidate input or derived report with bounded memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def filter_grid():
    """Return exactly five predeclared causal smoothing alternatives."""

    return [
        {"kind": "raw", "window": 1},
        {"kind": "mean", "window": 3},
        {"kind": "median", "window": 3},
        {"kind": "median", "window": 5},
        {"kind": "ewma", "alpha": 0.5, "window": 1},
    ]


def alarm_grid(filter_config):
    """Yield the fixed Risk activation/recovery search grid.

    Critical severity is held at 0.5 during this stage because it cannot alter
    Safe versus active state transitions.  A second small search selects the
    Critical threshold after the alarm episode behavior is fixed.
    """

    for risk_on in (0.25, 0.35, 0.45, 0.55, 0.65, 0.75):
        for delta in (0.10, 0.20):
            risk_off = max(0.0, risk_on - delta)
            for k_on in (1, 2, 3):
                for k_off in (1, 2, 3):
                    yield {"filter": filter_config, "risk_on": risk_on,
                           "risk_off": risk_off, "critical_on": 0.5,
                           "critical_off": 0.4, "k_on": k_on, "k_off": k_off}


def subset_rows(rows, trace_ids):
    """Select whole traces while retaining original row order."""

    allowed = set(trace_ids)
    return [row for row in rows if row["trace_id"] in allowed]


def fast_window_metrics(rows):
    """Compute selection-time confusion metrics without probability scoring."""

    labels = np.asarray([int(row["target_label"]) for row in rows])
    predictions = np.asarray([int(row["prediction"]) for row in rows])
    recalls = []
    for label in range(3):
        mask = labels == label
        recalls.append(float(np.mean(predictions[mask] == label)) if np.any(mask) else 0.0)
    safe = labels == 0
    return {"accuracy": float(np.mean(labels == predictions)),
            "balanced_accuracy": float(np.mean(recalls)),
            "safe_window_false_alarm_rate": float(np.mean(predictions[safe] != 0))}


def safe_value(value, default):
    """Replace undefined event statistics only inside deterministic ranking."""

    return default if value is None else float(value)


def alarm_selection_key(config, window, events):
    """Rank alarm-layer candidates against current-state operational gates."""

    risk_detection = safe_value(events["risk_event_detection_rate"], 0.0)
    recovery = safe_value(events["mean_recovery_delay_samples"], 1.0e9)
    feasible = (risk_detection >= 0.98
                and events["false_alarms_per_trace"] <= 0.10
                and window["safe_window_false_alarm_rate"] <= 0.05
                and recovery <= 3.0)
    if feasible:
        return (0, -window["balanced_accuracy"], events["false_alarms_per_trace"],
                window["safe_window_false_alarm_rate"], recovery,
                filter_complexity(config))
    # Infeasible folds retain the highest-risk-recall diagnostic configuration
    # with bounded false alarms; the aggregate OOF gates still report failure.
    return (1, -risk_detection, events["false_alarms_per_trace"],
            window["safe_window_false_alarm_rate"], recovery,
            -window["balanced_accuracy"], filter_complexity(config))


def tune_on_traces(rows, trace_ids):
    """Search one training-fold trace subset and return its selected config."""

    selected = subset_rows(rows, trace_ids)
    best = None
    candidates = 0
    for filter_config in filter_grid():
        filtered = filter_rows(selected, filter_config)
        for config in alarm_grid(filter_config):
            processed = apply_hysteresis(filtered, config)
            window = fast_window_metrics(processed)
            events = state_event_metrics(processed)
            key = alarm_selection_key(config, window, events)
            candidates += 1
            if best is None or key < best[0]:
                best = (key, config, window, events)

    # Severity search optimizes Critical event detection and delay while the
    # already selected risk episode boundaries remain unchanged.
    filtered = filter_rows(selected, best[1]["filter"])
    severity_best = None
    for critical_on in (0.20, 0.30, 0.40, 0.50, 0.60, 0.70):
        config = {**best[1], "critical_on": critical_on,
                  "critical_off": max(0.05, critical_on - 0.10)}
        processed = apply_hysteresis(filtered, config)
        window = fast_window_metrics(processed)
        events = state_event_metrics(processed)
        detection = safe_value(events["critical_event_detection_rate"], 0.0)
        median_delay = safe_value(events["median_critical_delay_ns"], 1.0e9)
        p95_delay = safe_value(events["p95_critical_delay_ns"], 1.0e9)
        feasible = detection >= 0.98 and median_delay <= 4.0 and p95_delay <= 12.0
        key = ((0 if feasible else 1), -detection, median_delay, p95_delay,
               -window["balanced_accuracy"], critical_on)
        if severity_best is None or key < severity_best[0]:
            severity_best = (key, config, window, events)
    return {"config": severity_best[1], "window": severity_best[2],
            "events": severity_best[3], "alarm_candidates_evaluated": candidates,
            "severity_candidates_evaluated": 6}


def trace_stratum(trace_rows):
    """Classify a trace by its strongest present-state event for fold balance."""

    labels = [(int(row["end_index"]), int(row["target_label"])) for row in trace_rows]
    if contiguous_intervals(labels, lambda value: value == 2):
        return "critical"
    if contiguous_intervals(labels, lambda value: value != 0):
        return "risk"
    return "safe"


def make_trace_folds(rows, corpus_rows, fold_count=5):
    """Build deterministic, severity-stratified component holdouts.

    A fold must not split either a shared ``base_waveform_id`` or a shared
    ``hard_pair_id``.  Because those two relations can connect indirectly, the
    implementation computes their joint transitive closure rather than giving
    either identifier priority.  Components are then placed greedily by trace
    count within each severity stratum, with total fold size and fold index as
    deterministic tie-breaks.  This retains useful fold balance while treating
    every leakage relationship as indivisible.
    """

    grouped_rows = defaultdict(list)
    for row in rows:
        grouped_rows[row["trace_id"]].append(row)
    trace_ids = set(grouped_rows)
    corpus_by_id = {row["trace_id"]: row for row in corpus_rows
                    if row["trace_id"] in trace_ids}
    if set(corpus_by_id) != trace_ids:
        raise ValueError("validation predictions and corpus membership differ")
    if any(row["split"] != "validation" for row in corpus_by_id.values()):
        raise ValueError("postprocess folds may use validation traces only")

    disjoint = DisjointSet(sorted(trace_ids))
    for field in ("base_waveform_id", "hard_pair_id"):
        buckets = defaultdict(list)
        for trace_id, corpus_row in corpus_by_id.items():
            value = corpus_row.get(field)
            if value:
                buckets[value].append(trace_id)
        for members in buckets.values():
            for member in members[1:]:
                disjoint.union(members[0], member)

    members_by_root = defaultdict(list)
    for trace_id in sorted(trace_ids):
        members_by_root[disjoint.find(trace_id)].append(trace_id)
    components = []
    severity_order = {"safe": 0, "risk": 1, "critical": 2}
    for members in members_by_root.values():
        # A component's strongest trace determines its stratum.  This avoids
        # labeling a mixed Safe/Critical pair as Safe merely because its first
        # lexical trace happens to be benign.
        component_stratum = max(
            (trace_stratum(grouped_rows[trace_id]) for trace_id in members),
            key=lambda name: severity_order[name])
        components.append({"trace_ids": sorted(members),
                           "stratum": component_stratum})
    components.sort(key=lambda item: (item["stratum"], item["trace_ids"]))

    folds = [[] for _ in range(int(fold_count))]
    stratum_counts = [Counter() for _ in folds]
    for stratum in ("critical", "risk", "safe"):
        # Largest components are placed first because they are hardest to
        # balance later.  Lexical trace IDs make equal-size placement stable.
        candidates = sorted(
            (item for item in components if item["stratum"] == stratum),
            key=lambda item: (-len(item["trace_ids"]), item["trace_ids"]))
        for component in candidates:
            fold_index = min(range(len(folds)), key=lambda index: (
                stratum_counts[index][stratum], len(folds[index]), index))
            folds[fold_index].extend(component["trace_ids"])
            stratum_counts[fold_index][stratum] += len(component["trace_ids"])
    folds = [sorted(fold) for fold in folds]
    if any(not fold for fold in folds):
        raise ValueError("five-fold component stratification produced an empty fold")

    fold_by_trace = {trace_id: fold_index for fold_index, fold in enumerate(folds)
                     for trace_id in fold}
    for component in components:
        if len({fold_by_trace[trace_id] for trace_id in component["trace_ids"]}) != 1:
            raise ValueError("base/hard-pair component crosses postprocess folds")
    return folds, components


def tune_fold(fold_index, holdout_ids, all_ids, rows):
    """Fit one fold without its holdout and return out-of-fold predictions."""

    training_ids = set(all_ids) - set(holdout_ids)
    tuned = tune_on_traces(rows, training_ids)
    holdout = apply_detector(subset_rows(rows, holdout_ids), tuned["config"])
    return fold_index, holdout, {
        "fold": fold_index, "training_trace_ids": sorted(training_ids),
        "holdout_trace_ids": list(holdout_ids),
        "selected_config": tuned["config"],
        "training_window": tuned["window"], "training_events": tuned["events"],
        "holdout_window": fast_window_metrics(holdout),
        "holdout_events": state_event_metrics(holdout),
        "alarm_candidates_evaluated": tuned["alarm_candidates_evaluated"],
        "severity_candidates_evaluated": tuned["severity_candidates_evaluated"],
    }


def benchmark_postprocess(rows, config, repetitions=30):
    """Measure median Python postprocess latency per validation window."""

    samples = []
    for _ in range(int(repetitions)):
        started = time.perf_counter_ns()
        apply_detector(rows, config)
        samples.append((time.perf_counter_ns() - started) / 1.0e6 / len(rows))
    return float(np.median(samples))


def acceptance(window, events, latency):
    """Evaluate every frozen Step 8 gate without rounded comparisons."""

    checks = {
        "critical_event_detection_rate_ge_0_98": safe_value(
            events["critical_event_detection_rate"], 0.0) >= 0.98,
        "risk_event_detection_rate_ge_0_98": safe_value(
            events["risk_event_detection_rate"], 0.0) >= 0.98,
        "median_critical_delay_ns_le_4": safe_value(
            events["median_critical_delay_ns"], 1.0e9) <= 4.0,
        "p95_critical_delay_ns_le_12": safe_value(
            events["p95_critical_delay_ns"], 1.0e9) <= 12.0,
        "false_alarms_per_trace_le_0_10": events["false_alarms_per_trace"] <= 0.10,
        "safe_window_false_alarm_rate_le_0_05": window["safe_window_false_alarm_rate"] <= 0.05,
        "mean_recovery_delay_samples_le_3": safe_value(
            events["mean_recovery_delay_samples"], 1.0e9) <= 3.0,
        "postprocess_latency_ms_per_window_lt_0_1": latency < 0.1,
    }
    checks["pass"] = all(checks.values())
    return checks


def write_oof_predictions(path, rows, fold_by_trace):
    """Persist chronological OOF states without electrical inputs."""

    fields = ["window_id", "trace_id", "split", "fold", "end_index",
              "target_label", "raw_prediction", "prediction",
              "filtered_risk_score", "filtered_critical_score"]
    temporary = Path(path).with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: (item["trace_id"], int(item["end_index"]))):
            writer.writerow({field: fold_by_trace[row["trace_id"]]
                             if field == "fold" else row[field] for field in fields})
    temporary.replace(path)


def main():
    """Run five-fold OOF tuning, then freeze one full-validation config."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--candidate-manifest", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite state postprocess release")
    candidate = json.loads(args.candidate_manifest.read_text(encoding="utf-8"))
    if (candidate.get("iid_ood_metrics_computed") is not False
            or sha256_file(args.predictions) != candidate["validation_predictions_sha256"]):
        raise ValueError("predictions do not match the frozen validation candidate")
    rows = read_prediction_rows(args.predictions)
    trace_ids = sorted({row["trace_id"] for row in rows})
    corpus_rows = [json.loads(line) for line in args.corpus.read_text(
        encoding="utf-8").splitlines() if line.strip()]
    folds, fold_components = make_trace_folds(rows, corpus_rows, fold_count=5)
    fold_by_trace = {trace_id: index for index, fold in enumerate(folds)
                     for trace_id in fold}
    if set(fold_by_trace) != set(trace_ids):
        raise ValueError("trace folds do not cover validation exactly once")

    oof_rows = []
    fold_reports = []
    with ProcessPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(tune_fold, index, holdout, trace_ids, rows)
                   for index, holdout in enumerate(folds)]
        for future in as_completed(futures):
            index, holdout_rows, report = future.result()
            oof_rows.extend(holdout_rows)
            fold_reports.append(report)
            print("completed state postprocess fold {} of 5".format(index + 1), flush=True)
    fold_reports.sort(key=lambda item: item["fold"])

    oof_labels = np.asarray([row["target_label"] for row in oof_rows])
    oof_predictions = np.asarray([row["prediction"] for row in oof_rows])
    oof_window = window_metrics(oof_labels, oof_predictions)
    oof_events = state_event_metrics(oof_rows)
    final = tune_on_traces(rows, trace_ids)
    final_rows = apply_detector(rows, final["config"])
    final_labels = np.asarray([row["target_label"] for row in final_rows])
    final_predictions = np.asarray([row["prediction"] for row in final_rows])
    final_window = window_metrics(final_labels, final_predictions)
    final_events = state_event_metrics(final_rows)
    latency = benchmark_postprocess(rows, final["config"])
    checks = acceptance(oof_window, oof_events, latency)
    report = {
        "schema_version": 1, "scope": "validation_only",
        "iid_ood_metrics_computed": False,
        "parameters_tuned_on_test": False,
        "candidate_manifest_sha256": sha256_file(args.candidate_manifest),
        "predictions_sha256": sha256_file(args.predictions),
        "corpus_sha256": sha256_file(args.corpus),
        "filter_candidates": filter_grid(), "trace_folds": folds,
        "fold_components": fold_components,
        "fold_component_integrity": True,
        "folds": fold_reports, "oof_window": oof_window,
        "oof_events": oof_events, "final_config": final["config"],
        "final_window": final_window, "final_events": final_events,
        "postprocess_latency_ms_per_window": latency, "acceptance": checks,
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for name, payload in (("postprocess_report.json", report),
                          ("postprocess_config.json", final["config"])):
        path = args.output_dir / name
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
        temporary.replace(path)
    write_oof_predictions(args.output_dir / "oof_predictions.csv",
                          oof_rows, fold_by_trace)


if __name__ == "__main__":
    main()
