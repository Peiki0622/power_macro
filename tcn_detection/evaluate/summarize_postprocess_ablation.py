#!/usr/bin/env python3
"""Aggregate validation OOF postprocessing gates across selected seeds."""

from __future__ import print_function

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


def sha256_file(path):
    """Hash one report with bounded memory for summary provenance."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    """Publish seed-level evidence, robustness gates, and arm ordering."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postprocess-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("refusing to overwrite postprocess summary: {}".format(args.output))

    manifest_path = args.postprocess_dir / "postprocess_ablation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "COMPLETE" or len(manifest.get("jobs", [])) != 6:
        raise ValueError("postprocess manifest is not a complete six-job result")

    runs = {}
    grouped = defaultdict(list)
    for job in manifest["jobs"]:
        report_path = args.postprocess_dir / job["output_dir"] / "postprocess_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("scope") != "validation_only" or report.get("iid_ood_metrics_computed") is not False:
            raise ValueError("postprocess report violates the blind-test boundary")
        events = report["oof_events"]
        window = report["oof_window"]
        compact = {
            "arm": job["arm"], "seed": int(job["seed"]),
            "critical_event_detection_rate": float(events["critical_event_detection_rate"]),
            "median_lead_time_ns": float(events["median_lead_time_ns"]),
            "false_alarms_per_trace": float(events["false_alarms_per_trace"]),
            "safe_window_false_alarm_rate": float(window["safe_window_false_alarm_rate"]),
            "acceptance_pass": bool(report["acceptance"]["pass"]),
            "final_config": report["final_config"], "report_sha256": sha256_file(report_path),
        }
        runs[job["name"]] = compact
        grouped[job["arm"]].append(compact)

    arms = {}
    for arm, items in sorted(grouped.items()):
        if len(items) != 3:
            raise ValueError("postprocessed arm must contain three seeds: {}".format(arm))
        worst_detection = min(item["critical_event_detection_rate"] for item in items)
        arms[arm] = {
            "all_seed_acceptance_pass": all(item["acceptance_pass"] for item in items),
            "worst_seed_critical_event_detection_rate": float(worst_detection),
            "worst_seed_gate_ge_0_85": bool(worst_detection >= 0.85),
            "median_critical_event_detection_rate": float(np.median(
                [item["critical_event_detection_rate"] for item in items])),
            "median_lead_time_ns": float(np.median([item["median_lead_time_ns"] for item in items])),
            "median_false_alarms_per_trace": float(np.median(
                [item["false_alarms_per_trace"] for item in items])),
            "median_safe_window_false_alarm_rate": float(np.median(
                [item["safe_window_false_alarm_rate"] for item in items])),
        }
        arms[arm]["passes_all_postprocess_gates"] = bool(
            arms[arm]["all_seed_acceptance_pass"] and arms[arm]["worst_seed_gate_ge_0_85"])

    # Both arms can saturate event detection.  The remaining ordering rewards
    # positive timing margin, then operationally cheaper false alarms and Safe
    # window activations.  The name is only a deterministic final tie-break.
    ranking = sorted(arms, key=lambda arm: (
        -arms[arm]["worst_seed_critical_event_detection_rate"],
        -arms[arm]["median_lead_time_ns"],
        arms[arm]["median_false_alarms_per_trace"],
        arms[arm]["median_safe_window_false_alarm_rate"],
        arm,
    ))
    report = {
        "schema_version": 1, "scope": "validation_only", "iid_ood_metrics_computed": False,
        "manifest_sha256": sha256_file(manifest_path), "runs": runs, "arms": arms,
        "ranking": ranking, "selected_postprocess_arm": ranking[0],
        "all_selected_arms_pass": all(item["passes_all_postprocess_gates"] for item in arms.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
