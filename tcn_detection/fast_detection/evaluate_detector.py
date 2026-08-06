#!/usr/bin/env python3
"""Run the complete train/validation search for Stage-1 fast detectors.

This command intentionally stops before reading ``iid_test``.  The separate
one-shot evaluator consumes only the frozen configurations produced here.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier

from power_macro.tcn_detection.fast_detection.dataset_adapter import DatasetAdapter
from power_macro.tcn_detection.fast_detection.detectors import (
    AmplitudeSlopeDetector, CusumDetector, EwmaResidualDetector,
    Int8ScorecardDetector, MultiStatisticFSMDetector,
    ShallowTreeDetector, SingleThresholdDetector,
    ThresholdConfirmDetector, derive_feature_rows)
from power_macro.tcn_detection.fast_detection.evaluation import (
    evaluate_detector, selection_key)


FEATURE_ORDER = ("residual", "slope", "cusum", "max_residual", "threshold_count")


def sha256_file(path):
    """Hash a frozen input for the search manifest."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _factory_result(results, name, family, spec, factory, traces):
    """Evaluate one immutable candidate and retain JSON-compatible evidence."""

    detector = factory()
    result = evaluate_detector(factory, traces)
    record = {
        "name": name,
        "family": family,
        "spec": spec,
        "window": result["window"],
        "events": result["events"],
        "hardware_cost": detector.hardware_cost(),
    }
    results.append(record)


def _fsm_thresholds(scale):
    """Build one fixed FSM table; scaling keeps search bounded and reproducible."""

    scale = int(scale)
    names = ("residual", "slope", "acceleration", "cusum", "threshold_count")
    values = {
        "suspect": (1, 1, 1, 2, 1),
        "warning": (3, 2, 2, 4, 2),
        "critical": (6, 4, 4, 8, 4),
    }
    return {level: {name: value * scale for name, value in zip(names, row)}
            for level, row in values.items()}


def _training_features(traces, count_threshold=1):
    """Materialize only train endpoints needed by scorecard/tree fitting."""

    features = []
    labels = []
    for trace in traces:
        rows = derive_feature_rows(
            [sample.sensor_code for sample in trace.samples],
            trace.metadata.baseline_code, 0, count_threshold)
        for index in range(31, len(trace.samples)):
            features.append([rows[index][name] for name in FEATURE_ORDER])
            labels.append(trace.samples[index].target_label)
    if not features or len(set(labels)) != 2:
        raise ValueError("train feature fitting requires both binary classes")
    return np.asarray(features, dtype=np.float64), np.asarray(labels, dtype=np.int64)


def _candidate_thresholds(values):
    """Generate bounded integer score thresholds from validation quantiles."""

    values = np.asarray(values, dtype=np.float64)
    quantiles = np.unique(np.rint(np.quantile(values, np.linspace(0.0, 1.0, 101))))
    return [int(value) for value in quantiles]


def _scorecard_from_train(train_traces):
    """Fit and INT8-quantize one linear scorecard using train data only."""

    features, labels = _training_features(train_traces)
    model = LogisticRegression(max_iter=1000, solver="liblinear",
                               random_state=20260725)
    model.fit(features, labels)
    floating = model.coef_[0].astype(np.float64)
    scale = max(float(np.max(np.abs(floating))) / 127.0, 1.0e-9)
    weights = np.clip(np.rint(floating / scale), -127, 127).astype(np.int64)
    bias = int(np.rint(float(model.intercept_[0]) / scale))
    return tuple(int(value) for value in weights), bias, scale


def _tree_nodes(model):
    """Convert a sklearn tree into bounded comparator nodes and binary leaves."""

    tree = model.tree_
    nodes = []
    feature_names = FEATURE_ORDER
    for index in range(tree.node_count):
        left, right = int(tree.children_left[index]), int(tree.children_right[index])
        if left == right:
            values = tree.value[index][0]
            nodes.append({"leaf": int(np.argmax(values))})
        else:
            nodes.append({"feature": feature_names[int(tree.feature[index])],
                          "threshold": int(np.floor(tree.threshold[index])),
                          "left": left, "right": right})
    if len(nodes) > 31:
        raise ValueError("tree node count exceeds the fixed export bound")
    return tuple(nodes)


def run_validation_search(adapter, output_dir):
    """Run every bounded detector family on all train/validation traces."""

    train = adapter.iter_traces({"train"})
    validation = adapter.iter_traces({"validation"})
    results = []

    for threshold in range(1, 33):
        _factory_result(results, "single_threshold_T{:02d}".format(threshold),
                        "single_threshold", {"threshold": threshold},
                        lambda threshold=threshold: SingleThresholdDetector(threshold),
                        validation)
    for threshold in range(1, 33):
        for confirm in (1, 2, 3, 4, 8):
            _factory_result(results, "threshold_confirm_T{:02d}_K{:02d}".format(threshold, confirm),
                            "threshold_confirm", {"threshold": threshold, "K": confirm},
                            lambda threshold=threshold, confirm=confirm: ThresholdConfirmDetector(threshold, confirm),
                            validation)
    for amplitude in range(18):
        for slope in range(33):
            _factory_result(results, "amplitude_slope_A{:02d}_S{:02d}".format(amplitude, slope),
                            "amplitude_slope", {"amplitude_threshold": amplitude, "slope_threshold": slope},
                            lambda amplitude=amplitude, slope=slope: AmplitudeSlopeDetector(amplitude, slope),
                            validation)
    for q in (3, 4, 5, 6):
        for threshold in range(18):
            _factory_result(results, "ewma_q{}_T{:02d}".format(q, threshold),
                            "ewma_residual", {"q": q, "threshold": threshold},
                            lambda q=q, threshold=threshold: EwmaResidualDetector(q, threshold),
                            validation)
    for drift in range(9):
        for threshold in range(1, 129):
            _factory_result(results, "cusum_V{:02d}_H{:03d}".format(drift, threshold),
                            "cusum", {"drift": drift, "threshold": threshold},
                            lambda drift=drift, threshold=threshold: CusumDetector(drift, threshold),
                            validation)
    for scale in (1, 2, 3):
        thresholds = _fsm_thresholds(scale)
        _factory_result(results, "multistat_fsm_scale{}".format(scale),
                        "multistat_fsm", {"thresholds": thresholds, "clear_count": 2},
                        lambda thresholds=thresholds: MultiStatisticFSMDetector(thresholds, 2),
                        validation)

    weights, bias, weight_scale = _scorecard_from_train(train)
    validation_features, _ = _training_features(validation)
    score_values = validation_features @ np.asarray(weights, dtype=np.float64) + bias
    for threshold in _candidate_thresholds(score_values):
        spec = {"weights": list(weights), "bias": bias,
                "score_threshold": threshold, "weight_scale": weight_scale,
                "cusum_drift": 0, "threshold_count_threshold": 1}
        _factory_result(results, "int8_scorecard_T{}".format(threshold),
                        "int8_scorecard", spec,
                        lambda spec=spec: Int8ScorecardDetector(
                            spec["weights"], spec["bias"], spec["score_threshold"]),
                        validation)

    train_features, train_labels = _training_features(train)
    for depth in range(1, 5):
        for leaves in (2, 4, 8, 16):
            model = DecisionTreeClassifier(max_depth=depth, max_leaf_nodes=leaves,
                                           random_state=20260725)
            model.fit(train_features, train_labels)
            nodes = _tree_nodes(model)
            spec = {"depth": depth, "leaf_limit": leaves,
                    "nodes": list(nodes), "cusum_drift": 0,
                    "threshold_count_threshold": 1}
            _factory_result(results, "shallow_tree_D{}_L{}".format(depth, leaves),
                            "shallow_tree", spec,
                            lambda spec=spec: ShallowTreeDetector(spec["nodes"]),
                            validation)

    results.sort(key=lambda item: selection_key(item, item["name"]))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "detector_search_results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fields = ["name", "family", "safe_window_far", "event_recall",
              "median_ttd_ns", "p95_ttd_ns", "maximum_ttd_ns",
              "false_alarms_per_trace", "alarm_occupancy"]
    with (output_dir / "detector_search_results.csv").open(
            "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in results:
            writer.writerow({
                "name": item["name"], "family": item["family"],
                "safe_window_far": item["window"]["safe_window_false_alarm_rate"],
                "event_recall": item["events"]["event_recall"],
                "median_ttd_ns": item["events"]["median_ttd_ns"],
                "p95_ttd_ns": item["events"]["p95_ttd_ns"],
                "maximum_ttd_ns": item["events"]["maximum_ttd_ns"],
                "false_alarms_per_trace": item["events"]["false_alarms_per_trace"],
                "alarm_occupancy": item["events"]["alarm_occupancy"],
            })
    families = sorted({item["family"] for item in results})
    candidates = [item for item in results if item["window"]["safe_window_false_alarm_rate"] <= 0.05]
    frozen = candidates[:2]
    manifest = {
        "schema_version": 1,
        "scope": "validation_only_fast_detector_search",
        "trace_counts": {"train": len(train), "validation": len(validation)},
        "candidate_count": len(results),
        "family_count": len(families),
        "families": families,
        "safe_far_budget": 0.05,
        "frozen_candidates": frozen,
        "iid_features_loaded": False,
        "iid_metrics_computed": False,
        "parameters_tuned_on_test": False,
        "inputs": {"label_provenance_sha256": sha256_file(adapter.label_root / "provenance.json")},
    }
    (output_dir / "detector_candidates.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main():
    """Run validation search and publish only a new output directory."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite detector search directory")
    manifest = run_validation_search(DatasetAdapter(args.label_root), args.output_dir)
    print(json.dumps({key: manifest[key] for key in
                      ("candidate_count", "family_count", "families")}, sort_keys=True))


if __name__ == "__main__":
    main()
