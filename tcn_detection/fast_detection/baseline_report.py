#!/usr/bin/env python3
"""Generate the validation-only streaming report for the frozen CNN baseline."""

from __future__ import print_function

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.evaluate.binary_metrics import (
    binary_event_metrics, binary_window_metrics)
from power_macro.tcn_detection.fast_detection.cnn_baseline import (
    CnnBaselineDetector, load_w8_a8_package)
from power_macro.tcn_detection.fast_detection.dataset_adapter import DatasetAdapter


def sha256_file(path):
    """Hash one frozen input so a report cannot be detached from its data."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def evaluate_trace(detector, trace):
    """Replay every sample in one trace and retain only endpoint evidence."""

    detector.reset(trace.metadata)
    rows = []
    for sample in trace.samples:
        started = time.perf_counter_ns()
        alarm = detector.step(sample.sensor_code, sample.valid)
        elapsed_ns = time.perf_counter_ns() - started
        if sample.sample_index < 31:
            continue
        rows.append({
            "trace_id": trace.metadata.trace_id,
            "split": trace.metadata.split,
            "end_index": sample.sample_index,
            "target_label": sample.target_label,
            "prediction": int(bool(alarm)),
            "step_latency_ns": int(elapsed_ns),
        })
    return rows


def build_report(adapter, traces, detector, package_root, output_path):
    """Compute complete validation metrics and atomically publish JSON evidence."""

    rows = []
    for trace in traces:
        rows.extend(evaluate_trace(detector, trace))
    if len(rows) != 48 * (500 - 31):
        raise ValueError("validation endpoint count is not 22,512")
    labels = np.asarray([row["target_label"] for row in rows], dtype=np.int64)
    predictions = np.asarray([row["prediction"] for row in rows], dtype=np.int64)
    window = binary_window_metrics(labels, predictions)
    events = binary_event_metrics(rows)
    latency = np.asarray([row["step_latency_ns"] for row in rows], dtype=np.float64)
    package_root = Path(package_root)
    report = {
        "schema_version": 1,
        "scope": "validation_only_streaming_cnn_baseline",
        "model": "cnn_w8_a8_l32",
        "split": "validation",
        "trace_count": len(traces),
        "endpoint_count": len(rows),
        "warmup_samples_per_trace": 31,
        "window_length": 32,
        "input_contract": {
            "feature": "sensor_code",
            "sensor_code_range": [0, 32],
            "baseline_code": 15,
            "forbidden_features": ["measured_vdd_a_v", "configured_droop_mv"],
        },
        "threshold": "critical_logit > safe_logit; ties are Safe",
        "window": window,
        "events": events,
        "stream_step_latency_ns": {
            "median": float(np.median(latency)),
            "p95": float(np.percentile(latency, 95)),
            "maximum": float(np.max(latency)),
        },
        "hardware_cost": detector.hardware_cost(),
        "inputs": {
            "label_provenance_sha256": sha256_file(adapter.label_root / "provenance.json"),
            "quantization_config_sha256": sha256_file(package_root / "quantization_config.json"),
            "package_manifest_sha256": sha256_file(package_root / "manifest.json"),
            "package_model_provenance_sha256": sha256_file(package_root / "model_provenance.json"),
        },
        "iid_features_loaded": False,
        "iid_metrics_computed": False,
        "parameters_tuned_on_test": False,
    }
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError("refusing to overwrite CNN baseline report")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(output_path)
    return report


def main():
    """Run the complete validation replay from explicit immutable paths."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-root", required=True, type=Path)
    parser.add_argument("--package-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    adapter = DatasetAdapter(args.label_root)
    traces = adapter.iter_traces({"validation"})
    detector = CnnBaselineDetector(load_w8_a8_package(args.package_root))
    report = build_report(adapter, traces, detector, args.package_root, args.output)
    print(json.dumps({"status": "PASS", "endpoint_count": report["endpoint_count"],
                      "event_recall": report["events"]["critical_event_detection_rate"]},
                     sort_keys=True))


if __name__ == "__main__":
    main()
