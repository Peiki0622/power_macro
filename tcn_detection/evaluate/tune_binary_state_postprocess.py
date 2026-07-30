#!/usr/bin/env python3
"""Five-fold component-grouped tuning for binary Critical postprocessing."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.evaluate.binary_metrics import (
    binary_event_metrics, binary_window_metrics)
from power_macro.tcn_detection.evaluate.binary_postprocess import (
    apply_detector, detect_filtered_rows, filter_rows)
from power_macro.tcn_detection.evaluate.tune_state_postprocess import make_trace_folds


def sha256_file(path):
    """Hash frozen tuning inputs and outputs in bounded memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_predictions(path):
    """Load only the frozen candidate's complete validation predictions."""

    with Path(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = []
        for raw in reader:
            if raw["split"] != "validation" or raw["target_label"] not in {"0", "1"}:
                raise ValueError("binary tuner accepts validation Safe/Critical rows only")
            rows.append({**raw, "end_index": int(raw["end_index"]),
                         "target_label": int(raw["target_label"]),
                         "prediction": int(raw["prediction"]),
                         "prob_safe": float(raw["prob_safe"]),
                         "prob_critical": float(raw["prob_critical"])})
    if len(rows) != 22512 or len({row["window_id"] for row in rows}) != len(rows):
        raise ValueError("binary tuner requires 22,512 unique validation predictions")
    return rows


def candidate_grid(config):
    """Yield exactly the predeclared 1,215 binary detector candidates."""

    for filter_config in config["postprocess"]["filters"]:
        for on in config["postprocess"]["critical_on_values"]:
            for delta in config["postprocess"]["off_deltas"]:
                off = max(0.0, float(on) - float(delta))
                for k_on in config["postprocess"]["k_on_values"]:
                    for k_off in config["postprocess"]["k_off_values"]:
                        yield {"filter": filter_config,
                               "critical_on": float(on), "critical_off": off,
                               "k_on": int(k_on), "k_off": int(k_off)}


def subset_rows(rows, trace_ids):
    """Select whole traces without changing their chronological rows."""

    allowed = set(trace_ids)
    return [row for row in rows if row["trace_id"] in allowed]


def fast_window(rows):
    """Compute decision metrics needed during grid ranking."""

    labels = np.asarray([row["target_label"] for row in rows])
    predictions = np.asarray([row["prediction"] for row in rows])
    report = binary_window_metrics(labels, predictions)
    return {key: report[key] for key in (
        "accuracy", "balanced_accuracy", "macro_f1", "critical_recall",
        "safe_window_false_alarm_rate")}


def safe_value(value, default):
    """Map undefined event values only inside deterministic ranking."""

    return default if value is None else float(value)


def acceptance(window, events, latency, gates):
    """Evaluate all frozen event gates without rounding."""

    checks = {
        "critical_event_detection_rate": safe_value(
            events["critical_event_detection_rate"], 0.0)
        >= float(gates["critical_event_detection_rate_min"]),
        "median_critical_delay_ns": safe_value(
            events["median_critical_delay_ns"], 1.0e9)
        <= float(gates["median_critical_delay_ns_max"]),
        "p95_critical_delay_ns": safe_value(
            events["p95_critical_delay_ns"], 1.0e9)
        <= float(gates["p95_critical_delay_ns_max"]),
        "false_alarms_per_trace": events["false_alarms_per_trace"]
        <= float(gates["false_alarms_per_trace_max"]),
        "safe_window_false_alarm_rate": window["safe_window_false_alarm_rate"]
        <= float(gates["safe_window_false_alarm_rate_max"]),
        "mean_recovery_delay_samples": safe_value(
            events["mean_recovery_delay_samples"], 1.0e9)
        <= float(gates["mean_recovery_delay_samples_max"]),
        "postprocess_latency": latency
        < float(gates["postprocess_latency_ms_per_window_max_exclusive"]),
    }
    checks["pass"] = all(checks.values())
    return checks


def ranking_key(candidate, window, events, gates):
    """Rank feasible candidates by quality, delay, recovery, and complexity."""

    checks = acceptance(window, events, 0.0, gates)
    feasible = all(value for key, value in checks.items()
                   if key not in {"pass", "postprocess_latency"})
    filter_rank = {"raw": 0, "mean": 1, "median": 2, "ewma": 3}[
        candidate["filter"]["kind"]]
    complexity = (filter_rank, candidate["filter"].get("window", 1),
                  candidate["k_on"], candidate["k_off"])
    return ((0 if feasible else 1),
            -safe_value(events["critical_event_detection_rate"], 0.0),
            -window["balanced_accuracy"],
            events["false_alarms_per_trace"],
            window["safe_window_false_alarm_rate"],
            safe_value(events["p95_critical_delay_ns"], 1.0e9),
            safe_value(events["mean_recovery_delay_samples"], 1.0e9),
            complexity, candidate["critical_on"], candidate["critical_off"])


def tune(rows, config):
    """Search one trace subset while caching each filter's causal scores."""

    best = None
    evaluated = 0
    gates = config["postprocess"]["event_gates"]
    for filter_config in config["postprocess"]["filters"]:
        filtered = filter_rows(rows, filter_config)
        candidates = [candidate for candidate in candidate_grid(config)
                      if candidate["filter"] == filter_config]
        for candidate in candidates:
            processed = detect_filtered_rows(filtered, candidate)
            window = fast_window(processed)
            events = binary_event_metrics(processed)
            key = ranking_key(candidate, window, events, gates)
            evaluated += 1
            if best is None or key < best[0]:
                best = (key, candidate, window, events)
    if evaluated != 1215:
        raise ValueError("binary detector candidate count changed from 1,215")
    return {"config": best[1], "window": best[2], "events": best[3],
            "candidates_evaluated": evaluated}


def tune_fold(index, holdout_ids, all_ids, rows, config):
    """Tune without one component holdout and return its OOF predictions."""

    training_ids = set(all_ids) - set(holdout_ids)
    selected = tune(subset_rows(rows, training_ids), config)
    holdout = apply_detector(subset_rows(rows, holdout_ids), selected["config"])
    return index, holdout, {
        "fold": index, "training_trace_ids": sorted(training_ids),
        "holdout_trace_ids": list(holdout_ids),
        "selected_config": selected["config"],
        "training_window": selected["window"],
        "training_events": selected["events"],
        "holdout_window": fast_window(holdout),
        "holdout_events": binary_event_metrics(holdout),
        "candidates_evaluated": selected["candidates_evaluated"],
    }


def benchmark(rows, config, repetitions=30):
    """Measure median Python detector latency per validation window."""

    samples = []
    for _ in range(int(repetitions)):
        started = time.perf_counter_ns()
        apply_detector(rows, config)
        samples.append((time.perf_counter_ns() - started) / 1.0e6 / len(rows))
    return float(np.median(samples))


def write_oof(path, rows, fold_by_trace):
    """Persist bounded OOF decisions without feature tensors."""

    fields = ["window_id", "trace_id", "split", "fold", "end_index",
              "target_label", "raw_prediction", "prediction", "prob_safe",
              "prob_critical", "filtered_critical_score"]
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: (item["trace_id"], item["end_index"])):
            writer.writerow({field: fold_by_trace[row["trace_id"]]
                             if field == "fold" else row[field] for field in fields})


def main():
    """Tune five OOF folds, freeze full-validation config, and publish evidence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--candidate-manifest", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite binary postprocess release")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate_manifest.read_text(encoding="utf-8"))
    if (candidate.get("iid_metrics_computed") is not False
            or sha256_file(args.predictions) != candidate["validation_predictions_sha256"]):
        raise ValueError("binary tuning predictions differ from frozen candidate")
    rows = read_predictions(args.predictions)
    corpus_rows = [json.loads(line) for line in args.corpus.read_text(
        encoding="utf-8").splitlines() if line.strip()]
    trace_ids = sorted({row["trace_id"] for row in rows})
    folds, components = make_trace_folds(rows, corpus_rows, fold_count=5)
    fold_by_trace = {trace_id: index for index, fold in enumerate(folds)
                     for trace_id in fold}
    oof_rows, fold_reports = [], []
    with ProcessPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(tune_fold, index, holdout, trace_ids, rows, config)
                   for index, holdout in enumerate(folds)]
        for future in as_completed(futures):
            index, holdout, report = future.result()
            oof_rows.extend(holdout)
            fold_reports.append(report)
            print("completed binary postprocess fold {} of 5".format(index + 1), flush=True)
    fold_reports.sort(key=lambda report: report["fold"])
    if len(oof_rows) != len(rows):
        raise ValueError("binary OOF predictions do not cover validation exactly once")
    oof_labels = np.asarray([row["target_label"] for row in oof_rows])
    oof_predictions = np.asarray([row["prediction"] for row in oof_rows])
    oof_window = binary_window_metrics(oof_labels, oof_predictions)
    oof_events = binary_event_metrics(oof_rows)
    final = tune(rows, config)
    latency = benchmark(rows, final["config"])
    checks = acceptance(oof_window, oof_events, latency,
                        config["postprocess"]["event_gates"])
    report = {
        "schema_version": 1, "scope": "validation_only",
        "iid_metrics_computed": False, "parameters_tuned_on_test": False,
        "candidate_manifest_sha256": sha256_file(args.candidate_manifest),
        "predictions_sha256": sha256_file(args.predictions),
        "corpus_sha256": sha256_file(args.corpus),
        "candidate_count": 1215,
        "filter_candidates": config["postprocess"]["filters"],
        "trace_folds": folds, "fold_components": components,
        "fold_component_integrity": True, "folds": fold_reports,
        "oof_window": oof_window, "oof_events": oof_events,
        "final_config": final["config"],
        "final_training_window": final["window"],
        "final_training_events": final["events"],
        "postprocess_latency_ms_per_window": latency,
        "acceptance": checks,
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "postprocess_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "postprocess_config.json").write_text(
        json.dumps(final["config"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_oof(args.output_dir / "oof_predictions.csv", oof_rows, fold_by_trace)


if __name__ == "__main__":
    main()
