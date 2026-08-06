#!/usr/bin/env python3
"""Freeze validation-selected detectors and score them once on IID traces.

The two commands in this module are deliberately separated.  ``freeze`` reads
only validation-search evidence and makes parameters immutable.  ``iid-test``
accepts only that immutable JSON file and refuses to reuse an output directory,
which makes a later IID result unable to influence the detector selection.
"""

from __future__ import print_function

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from power_macro.tcn_detection.fast_detection.cnn_baseline import (
    CnnBaselineDetector, load_w8_a8_package)
from power_macro.tcn_detection.fast_detection.dataset_adapter import DatasetAdapter
from power_macro.tcn_detection.fast_detection.detectors import (
    AmplitudeSlopeDetector, CusumDetector, EwmaResidualDetector,
    Int8ScorecardDetector, MultiStatisticFSMDetector, ShallowTreeDetector,
    SingleThresholdDetector, ThresholdConfirmDetector)
from power_macro.tcn_detection.fast_detection.evaluation import evaluate_detector


def sha256_file(path):
    """Return the digest recorded beside every frozen external input."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path):
    """Read an object JSON artifact and reject malformed top-level content."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("frozen artifact must contain a JSON object")
    return payload


def _write_new_json(path, payload):
    """Publish one JSON file without overwriting a previously frozen result."""

    path = Path(path)
    if path.exists():
        raise FileExistsError("refusing to overwrite immutable artifact: {}".format(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def detector_from_spec(family, spec):
    """Rebuild exactly one detector from a validation-frozen family and spec.

    This is intentionally a small explicit dispatch table.  It prevents test
    evaluation from accepting arbitrary constructors or silently applying a
    default parameter different from the validation search configuration.
    """

    if family == "single_threshold":
        return SingleThresholdDetector(spec["threshold"])
    if family == "threshold_confirm":
        return ThresholdConfirmDetector(spec["threshold"], spec["K"])
    if family == "amplitude_slope":
        return AmplitudeSlopeDetector(spec["amplitude_threshold"],
                                      spec["slope_threshold"])
    if family == "ewma_residual":
        return EwmaResidualDetector(spec["q"], spec["threshold"])
    if family == "cusum":
        return CusumDetector(spec["drift"], spec["threshold"])
    if family == "multistat_fsm":
        return MultiStatisticFSMDetector(spec["thresholds"], spec["clear_count"])
    if family == "int8_scorecard":
        return Int8ScorecardDetector(spec["weights"], spec["bias"],
                                     spec["score_threshold"], spec["cusum_drift"],
                                     spec["threshold_count_threshold"])
    if family == "shallow_tree":
        return ShallowTreeDetector(spec["nodes"], spec["cusum_drift"],
                                   spec["threshold_count_threshold"])
    raise ValueError("unknown frozen detector family: {}".format(family))


def _validate_selected_candidates(manifest):
    """Check that exactly two already-ranked candidates meet the FAR budget."""

    candidates = manifest.get("frozen_candidates")
    budget = float(manifest.get("safe_far_budget", -1.0))
    if manifest.get("scope") != "validation_only_fast_detector_search":
        raise ValueError("candidate manifest is not validation-only evidence")
    if manifest.get("iid_features_loaded") or manifest.get("iid_metrics_computed"):
        raise ValueError("candidate manifest must not contain IID evaluation")
    if not isinstance(candidates, list) or len(candidates) != 2:
        raise ValueError("exactly two validation-selected candidates are required")
    names = set()
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("name") in names:
            raise ValueError("candidate names must be unique")
        names.add(candidate["name"])
        if float(candidate["window"]["safe_window_false_alarm_rate"]) > budget:
            raise ValueError("frozen candidate violates validation FAR budget")
        # Construction performs family-specific type, range, and tree checks.
        detector_from_spec(candidate["family"], candidate["spec"])
    return candidates, budget


def freeze_configuration(candidate_manifest_path, search_csv_path,
                         cnn_report_path, package_root, output_path):
    """Copy validation evidence and emit a top-two immutable test contract.

    The copied CSV and manifest are stored beside the contract because the
    final Stage-1 directory must retain its selection evidence.  Neither file
    is regenerated here, so their original validation-only byte stream remains
    independently hashable.
    """

    candidate_manifest_path = Path(candidate_manifest_path)
    search_csv_path = Path(search_csv_path)
    cnn_report_path = Path(cnn_report_path)
    package_root = Path(package_root)
    manifest = _read_json(candidate_manifest_path)
    candidates, budget = _validate_selected_candidates(manifest)
    baseline = _read_json(cnn_report_path)
    provenance = _read_json(package_root / "model_provenance.json")
    if baseline.get("scope") != "validation_only_streaming_cnn_baseline":
        raise ValueError("CNN report is not the frozen validation baseline")
    artifact_dir = Path(output_path).parent
    copied_manifest = artifact_dir / "detector_candidates.json"
    copied_csv = artifact_dir / "detector_search_results.csv"
    for source, destination in ((candidate_manifest_path, copied_manifest),
                                (search_csv_path, copied_csv)):
        if destination.exists():
            raise FileExistsError("refusing to overwrite validation evidence: {}".format(destination))
        if not source.is_file():
            raise FileNotFoundError("missing validation evidence: {}".format(source))
    payload = {
        "schema_version": 1,
        "scope": "frozen_fast_detector_configuration_before_iid_test",
        "selection_rule": "validation FAR <= 0.05, then maximum event recall, then minimum p95 TTD, then name",
        "safe_far_budget": budget,
        "selected_candidates": candidates,
        "cnn_reference": {
            "model": baseline["model"],
            "window_length": baseline["window_length"],
            "threshold": baseline["threshold"],
            "normalizer": provenance["normalizer"],
            "model_config_sha256": provenance["model_config_sha256"],
            "checkpoint_sha256": provenance["checkpoint_sha256"],
            "quantization_config_sha256": sha256_file(package_root / "quantization_config.json"),
            "package_manifest_sha256": sha256_file(package_root / "manifest.json"),
        },
        "inputs": {
            "label_provenance_sha256": manifest["inputs"]["label_provenance_sha256"],
            "validation_candidate_manifest_sha256": sha256_file(candidate_manifest_path),
            "validation_search_csv_sha256": sha256_file(search_csv_path),
            "cnn_baseline_report_sha256": sha256_file(cnn_report_path),
        },
        "iid_features_loaded": False,
        "iid_metrics_computed": False,
        "parameters_tuned_on_test": False,
    }
    _write_new_json(output_path, payload)
    # Copy only after every input and destination has been checked, avoiding a
    # partly published freeze directory when a prerequisite is missing.
    shutil.copyfile(candidate_manifest_path, copied_manifest)
    shutil.copyfile(search_csv_path, copied_csv)
    return payload


def evaluate_iid_once(config_path, label_root, package_root, output_dir):
    """Evaluate the frozen CNN and candidates on IID exactly once.

    ``output_dir`` must not exist before any IID CSV is opened.  A successful
    run writes summary metrics only: it deliberately omits endpoint predictions
    and makes this directory the durable record of the single test evaluation.
    """

    config_path = Path(config_path)
    package_root = Path(package_root)
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError("refusing to reuse IID test output directory: {}".format(output_dir))
    config = _read_json(config_path)
    if config.get("scope") != "frozen_fast_detector_configuration_before_iid_test":
        raise ValueError("IID evaluation requires a frozen detector configuration")
    selected = config.get("selected_candidates")
    if not isinstance(selected, list) or len(selected) != 2:
        raise ValueError("frozen configuration must contain exactly two candidates")
    quantization_hash = sha256_file(package_root / "quantization_config.json")
    manifest_hash = sha256_file(package_root / "manifest.json")
    if quantization_hash != config["cnn_reference"]["quantization_config_sha256"]:
        raise ValueError("CNN quantization package differs from frozen configuration")
    if manifest_hash != config["cnn_reference"]["package_manifest_sha256"]:
        raise ValueError("CNN package manifest differs from frozen configuration")
    expected_provenance = config["inputs"]["label_provenance_sha256"]
    adapter = DatasetAdapter(label_root)
    if sha256_file(adapter.label_root / "provenance.json") != expected_provenance:
        raise ValueError("label provenance differs from frozen configuration")
    # IID rows are first materialized only after all output/configuration guards
    # pass.  No detector creation or metric can mutate the frozen parameters.
    iid_traces = adapter.iter_traces({"iid_test"})
    cnn = CnnBaselineDetector(load_w8_a8_package(package_root))
    cnn_result = evaluate_detector(lambda: CnnBaselineDetector(cnn.package), iid_traces)
    fast_results = []
    for candidate in selected:
        factory = lambda candidate=candidate: detector_from_spec(
            candidate["family"], candidate["spec"])
        result = evaluate_detector(factory, iid_traces)
        fast_results.append({"name": candidate["name"], "family": candidate["family"],
                             "spec": candidate["spec"], "window": result["window"],
                             "events": result["events"],
                             "hardware_cost": factory().hardware_cost()})
    report = {
        "schema_version": 1,
        "scope": "iid_test_once_frozen_fast_detector_evaluation",
        "split": "iid_test",
        "trace_count": len(iid_traces),
        "common_window_start": 31,
        "cnn": {"name": cnn.name, "window": cnn_result["window"],
                "events": cnn_result["events"], "hardware_cost": cnn.hardware_cost()},
        "fast_detectors": fast_results,
        "inputs": {"frozen_detector_config_sha256": sha256_file(config_path),
                   "label_provenance_sha256": expected_provenance,
                   "quantization_config_sha256": quantization_hash,
                   "package_manifest_sha256": manifest_hash},
        "parameters_tuned_on_test": False,
    }
    output_dir.mkdir(parents=True)
    _write_new_json(output_dir / "IID_TEST_EVALUATION.json", report)
    return report


def main():
    """Expose explicit freeze and one-shot-IID commands for reproducible use."""

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--candidate-manifest", required=True, type=Path)
    freeze.add_argument("--search-csv", required=True, type=Path)
    freeze.add_argument("--cnn-report", required=True, type=Path)
    freeze.add_argument("--package-root", required=True, type=Path)
    freeze.add_argument("--output", required=True, type=Path)
    iid = commands.add_parser("iid-test")
    iid.add_argument("--config", required=True, type=Path)
    iid.add_argument("--label-root", required=True, type=Path)
    iid.add_argument("--package-root", required=True, type=Path)
    iid.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        payload = freeze_configuration(args.candidate_manifest, args.search_csv,
                                       args.cnn_report, args.package_root, args.output)
        print(json.dumps({"status": "FROZEN", "candidates": [item["name"] for item in
                           payload["selected_candidates"]]}, sort_keys=True))
    else:
        report = evaluate_iid_once(args.config, args.label_root, args.package_root,
                                   args.output_dir)
        print(json.dumps({"status": "PASS", "trace_count": report["trace_count"],
                          "fast_detectors": [item["name"] for item in
                                             report["fast_detectors"]]}, sort_keys=True))


if __name__ == "__main__":
    main()
