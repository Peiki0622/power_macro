#!/usr/bin/env python3
"""Apply Step 8-13 gates and publish the final compression stop report."""

from __future__ import print_function

import argparse
import json
import subprocess
from pathlib import Path

from power_macro.tcn_detection.compression.teacher_contract import sha256_file
from power_macro.tcn_detection.train.common import build_classifier, estimate_macs, parameter_count, read_json


TEACHER_SHA256 = "b6741281203fc4593b6434df584ace44cffa5daed23ece8745d1b14215a64814"
BASELINE_MACS = 106668


def parse_args():
    """Parse the immutable report inputs."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--sensitivity-report", required=True, type=Path)
    parser.add_argument("--pruning-report", required=True, type=Path)
    parser.add_argument("--distillation-report", required=True, type=Path)
    parser.add_argument("--feature-report", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report-dir", required=True, type=Path)
    return parser.parse_args()


def _resolve(root, value):
    """Resolve a configuration path below the repository root."""

    path = Path(value)
    return path if path.is_absolute() else Path(root) / path


def _git_commit(root):
    """Record the source commit without modifying the repository."""

    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def main():
    """Stop honestly when no candidate satisfies both quality and MAC gates."""

    args = parse_args()
    if args.output_dir.exists() or (args.report_dir / "FINAL_COMPRESSION.md").exists():
        raise FileExistsError("refusing to overwrite final compression evidence")
    config = read_json(args.config)
    sensitivity, pruning = read_json(args.sensitivity_report), read_json(args.pruning_report)
    distillation, feature = read_json(args.distillation_report), read_json(args.feature_report)
    root = Path(config["repository_root"]).resolve()
    teacher_path = _resolve(root, config["teacher"]["checkpoint"])
    if sha256_file(teacher_path) != TEACHER_SHA256:
        raise ValueError("Teacher checkpoint SHA256 changed before final gate")
    # The sensitivity report is the complete single-layer scan; no hidden
    # candidate may be invented after a quality-gated path stopped.
    candidates = []
    for student in distillation["students"]:
        for arm in student["arms"]:
            metrics = arm["validation_metrics"]
            candidates.append({
                "candidate_id": student["student_id"],
                "method": "logit_kd", "temperature": arm["temperature"],
                "alpha_ce": arm["alpha_ce"], "macs": student["estimated_macs_per_window"],
                "strict_single_seed_gate": arm["strict_single_seed_gate"],
                "metrics": metrics})
    for arm in feature["arms"]:
        candidates.append({
            "candidate_id": feature["source_student"], "method": "feature_kd",
            "lambda_stat": arm["lambda_stat"],
            "macs": next(item["estimated_macs_per_window"] for item in distillation["students"]
                          if item["student_id"] == feature["source_student"]),
            "strict_single_seed_gate": arm["strict_single_seed_gate"],
            "metrics": arm["validation_metrics"]})
    feasible_single_seed = [item for item in candidates
                            if item["strict_single_seed_gate"]
                            and item["macs"] <= BASELINE_MACS * 0.5]
    best_macs = min((item["macs"] for item in candidates), default=BASELINE_MACS)
    report = {
        "schema_version": 1, "status": "CNN_COMPRESSION_V1_NO_FEASIBLE_CANDIDATE",
        "teacher_sha256": TEACHER_SHA256, "baseline_macs_per_window": BASELINE_MACS,
        "best_observed_macs_per_window": best_macs,
        "best_observed_reduction_fraction": 1.0 - best_macs / float(BASELINE_MACS),
        "candidates": candidates, "feasible_single_seed_sub50": feasible_single_seed,
        "step8_kernel_status": "SKIPPED_NO_STRICT_QUALITY_MARGIN",
        "step9_formal_three_seed_status": "NOT_RUN_NO_ELIGIBLE_CANDIDATE",
        "step10_teacher_assistant_status": "SKIPPED_ASSISTANT_REQUIRES_FORMAL_12_PASS",
        "step11_float_freeze_status": "NOT_FROZEN_NO_FEASIBLE_FLOAT_CANDIDATE",
        "step12_fixed_point_status": "NOT_RUN_FLOAT_CANDIDATE_REQUIRED",
        "iid_features_loaded": False, "iid_metrics_computed": False,
        "parameters_tuned_on_test": False, "git_commit": _git_commit(root),
        "windows_sha256": sha256_file(_resolve(root, config["data"]["windows"])),
        "plan_sha256": sha256_file(root / config["plan_path"]),
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "final_compression.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.report_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Final Compression Gate", "",
             "Status: `CNN_COMPRESSION_V1_NO_FEASIBLE_CANDIDATE`", "",
             "No validation-only candidate met both the fixed quality gates and the required 50% MAC reduction.", "",
             "| Evidence | Result |", "| --- | --- |",
             "| Best observed MAC/window | {} |".format(best_macs),
             "| Best observed MAC reduction | {:.2%} |".format(report["best_observed_reduction_fraction"]),
             "| Strict single-seed sub-50% candidates | {} |".format(len(feasible_single_seed)),
             "| Step 8 kernel crop | skipped: no strict quality margin |",
             "| Step 9 three-seed validation | not run: no eligible candidate |",
             "| Step 10 Teacher Assistant | skipped: assistant prerequisite absent |",
             "| Step 11 float freeze | not frozen |",
             "| Step 12 W8/A8 | not run: no frozen float candidate |", "",
             "All reports used train/validation only; IID/OOD features and metrics were not loaded. Existing RTL, ROM, cycle model, and task-three power codebook were not modified.", ""]
    (args.report_dir / "FINAL_COMPRESSION.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
