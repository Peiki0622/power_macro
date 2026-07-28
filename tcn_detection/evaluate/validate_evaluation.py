#!/usr/bin/env python3
"""Perform a full artifact-level acceptance audit for TCN model evaluation."""

from __future__ import print_function

import argparse
import csv
import json
from pathlib import Path


EXPECTED_PRIMARY_METHODS = {"cae", "cnn", "tcn", "threshold_sensor_code", "threshold_delta_code", "threshold_short_history"}
EXPECTED_MODEL_JOBS = {"cae_L16", "cnn_L16", "tcn_L8", "tcn_L16", "tcn_L32"}
EXPECTED_FIGURE_STEMS = {"{:02d}_{}".format(index, name) for index, name in enumerate((
    "dataset_flow", "background_examples", "known_and_ood_waveforms", "sensor_code_timeseries", "label_timeline",
    "class_distribution", "split_audit", "confusion_matrix", "pr_curves", "event_timeline", "confirmation_tradeoff",
    "lead_time_distribution", "hard_pair_comparison", "model_comparison"), start=1)}


def fail(failures, message):
    """Collect all violations so a final audit reports every missing artifact at once."""

    failures.append(message)


def main():
    """Check model provenance, frozen evaluation content, predictions, and all figures."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", required=True, type=Path)
    parser.add_argument("--evaluation-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    failures = []
    manifest_path = args.models_dir / "parallel_training_manifest.json"
    if not manifest_path.is_file():
        fail(failures, "missing parallel training manifest")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        jobs = {job["name"]: job for job in manifest.get("jobs", [])}
        if set(jobs) != EXPECTED_MODEL_JOBS:
            fail(failures, "parallel training jobs differ from required model matrix")
        for name, job in jobs.items():
            if job.get("exit_code") != 0 or not (args.models_dir / name / "training_summary.json").is_file() or not (args.models_dir / name / "best_checkpoint.pt").is_file():
                fail(failures, "model job is incomplete: {}".format(name))
    report_path = args.evaluation_dir / "evaluation_report.json"
    if not report_path.is_file():
        fail(failures, "missing evaluation report")
        report = {}
    else:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        methods = report.get("methods", {})
        if not EXPECTED_PRIMARY_METHODS.issubset(methods):
            fail(failures, "evaluation report is missing a primary detector")
        for name in EXPECTED_PRIMARY_METHODS:
            if name not in methods:
                continue
            method = methods[name]
            if "iid_test" not in method.get("window", {}) or "ood_test" not in method.get("window", {}):
                fail(failures, "method lacks frozen IID/OOD window metrics: {}".format(name))
            if "confirmation" not in method or method["confirmation"].get("selected_confirm_count") not in {1, 3, 5, 9}:
                fail(failures, "method lacks a validation-only confirmation selection: {}".format(name))
    prediction_path = args.evaluation_dir / "predictions_L16.csv"
    if not prediction_path.is_file():
        fail(failures, "missing consolidated predictions")
    else:
        with prediction_path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        by_method = {name: 0 for name in EXPECTED_PRIMARY_METHODS}
        for row in rows:
            if row["method"] in by_method:
                by_method[row["method"]] += 1
            if row["split"] not in {"validation", "iid_test", "ood_test"} or row["target_label"] not in {"0", "1", "2"} or row["prediction"] not in {"0", "1", "2"}:
                fail(failures, "prediction CSV contains an invalid frozen record")
                break
        if any(count == 0 for count in by_method.values()):
            fail(failures, "a primary method has no persisted predictions")
    figures = args.evaluation_dir / "figures"
    figure_manifest = figures / "figure_manifest.json"
    if not figure_manifest.is_file():
        fail(failures, "missing figure manifest")
    else:
        manifest = json.loads(figure_manifest.read_text(encoding="utf-8"))
        if manifest.get("figure_count") != 14:
            fail(failures, "figure manifest does not declare fourteen figures")
    for stem in EXPECTED_FIGURE_STEMS:
        if not (figures / (stem + ".pdf")).is_file() or not (figures / (stem + ".png")).is_file():
            fail(failures, "missing PDF or PNG for {}".format(stem))
    result = {"schema_version": 1, "status": "PASS" if not failures else "FAIL", "failures": failures,
              "pilot_gate": report.get("pilot_gate", {}), "primary_methods": sorted(EXPECTED_PRIMARY_METHODS)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
