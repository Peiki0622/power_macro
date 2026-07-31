#!/usr/bin/env python3
"""Compare the frozen binary CNN and TCN without rerunning either model.

Both inputs are already-published one-shot IID prediction files.  This script
performs reporting only: it validates their immutable boundaries, aligns every
endpoint, recomputes like-for-like metrics from the stored probabilities and
decisions, and publishes a new comparison directory atomically.
"""

from __future__ import print_function

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.evaluate.compare_frozen_binary_iid import (
    align_rows, paired_disagreements, read_binary, score, sha256_file)


EXPECTED_DIGESTS = {
    "tcn_candidate": "3761e984bca8baf7f922d5b8b796c5a1aeb6564b52514ff21fb96e81e16e96f0",
    "tcn_checkpoint": "6135a38c3e6e720ec569d4fa3ce26a2597c8a76489381fe0919e7fe5e087e069",
    "tcn_predictions": "739786d5b2298d4f4081f0f093fbc5124f77ef08a4298320bdcd4334feb9a62a",
    "cnn_candidate": "1753347ce4c9755204fb7c13c7763efbc937d6bc759730a6ae71cd37e8308476",
    "cnn_checkpoint": "21b5181ef5a8ad05bb5088cf087ed9805e4e1b2c662616412b4dd4d93bce4e98",
    "cnn_predictions": "1a0d8487887320e850698e39035830b3d7ecd88f2dc33e12bf5d7ac85b753554",
}


def read_json(path):
    """Load one JSON object and reject arrays or scalar top-level values."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return payload


def validate_inputs(args, tcn_report, cnn_report, tcn_candidate, cnn_candidate,
                    tcn_summary, cnn_summary):
    """Prove the comparison uses the two exact frozen one-shot releases."""

    paths = {
        "tcn_candidate": args.tcn_candidate,
        "tcn_predictions": args.tcn_predictions,
        "cnn_candidate": args.cnn_candidate,
        "cnn_predictions": args.cnn_predictions,
    }
    for name, path in paths.items():
        if sha256_file(path) != EXPECTED_DIGESTS[name]:
            raise ValueError("frozen comparison digest mismatch: {}".format(name))
    if (tcn_candidate.get("checkpoint_sha256") != EXPECTED_DIGESTS["tcn_checkpoint"]
            or cnn_candidate.get("checkpoint_sha256")
            != EXPECTED_DIGESTS["cnn_checkpoint"]
            or sha256_file(args.tcn_training_summary)
            != tcn_candidate.get("training_summary_sha256")
            or sha256_file(args.cnn_training_summary)
            != cnn_candidate.get("training_summary_sha256")):
        raise ValueError("candidate checkpoint or training-summary identity changed")

    # IID is non-pristine because it was viewed in earlier experiments, but it
    # was not used to tune either frozen release.  All three flags must remain
    # explicit so this report cannot be mistaken for a new blind evaluation.
    for name, report in (("TCN", tcn_report), ("CNN", cnn_report)):
        if (report.get("parameters_tuned_on_test") is not False
                or report.get("pristine_blind_test") is not False
                or report.get("rerun_authorized") is not False
                or report.get("prediction_count") != 22512
                or report.get("trace_count") != 48):
            raise ValueError("{} report violates frozen IID boundary".format(name))
    if (tcn_report.get("predictions_sha256") != EXPECTED_DIGESTS["tcn_predictions"]
            or cnn_report.get("predictions_sha256")
            != EXPECTED_DIGESTS["cnn_predictions"]):
        raise ValueError("one-shot report does not own the supplied predictions")
    if (tcn_summary.get("model") != "tcn" or cnn_summary.get("model") != "cnn"
            or int(tcn_summary.get("window_length", -1)) != 32
            or int(cnn_summary.get("window_length", -1)) != 32):
        raise ValueError("complexity summaries do not describe the frozen L32 models")


def complexity(summary):
    """Extract the common resource contract recorded by each training run."""

    return {
        "parameter_count": int(summary["parameter_count"]),
        "estimated_macs_per_window": int(summary["estimated_macs_per_window"]),
        "median_cpu_latency_ms_per_window": float(summary["median_cpu_latency_ms"]),
    }


def fmt(value):
    """Use stable human-readable precision while JSON retains full precision."""

    if value is None:
        return "N/A"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    return "{:.6f}".format(float(value))


def nested(payload, path):
    """Read a tuple path from a nested metric dictionary."""

    value = payload
    for key in path:
        value = value[key]
    return value


def markdown_report(report):
    """Render every scalar evaluation family as reviewable Markdown tables."""

    variants = [
        ("TCN raw", report["models"]["tcn"]["raw"]),
        ("CNN raw", report["models"]["cnn"]["raw"]),
        ("TCN post", report["models"]["tcn"]["postprocessed"]),
        ("CNN post", report["models"]["cnn"]["postprocessed"]),
    ]
    lines = [
        "# Frozen IID Binary CNN vs TCN", "",
        "This is a reporting-only comparison of existing one-shot IID outputs. "
        "Neither model was rerun and no IID result changed the frozen CNN "
        "replacement decision. The CNN remains the project default, but its "
        "quality and event gates do not support a deployment-readiness claim.", "",
        "## Window Metrics", "",
        "| Metric | TCN raw | CNN raw | TCN post | CNN post |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    fields = [
        ("Accuracy", ("accuracy",)),
        ("Balanced accuracy", ("balanced_accuracy",)),
        ("Macro-F1", ("macro_f1",)), ("Weighted F1", ("weighted_f1",)),
        ("MCC", ("matthews_correlation_coefficient",)),
        ("Safe FAR", ("safe_window_false_alarm_rate",)),
        ("Critical FNR", ("critical_false_negative_rate",)),
        ("Specificity", ("specificity",)),
        ("Negative predictive value", ("negative_predictive_value",)),
        ("Safe precision", ("per_class", "0", "precision")),
        ("Safe recall", ("per_class", "0", "recall")),
        ("Safe F1", ("per_class", "0", "f1")),
        ("Safe support", ("per_class", "0", "support")),
        ("Critical precision", ("critical_precision",)),
        ("Critical recall", ("critical_recall",)),
        ("Critical F1", ("per_class", "1", "f1")),
        ("Critical support", ("per_class", "1", "support")),
    ]
    for label, path in fields:
        lines.append("| {} | {} |".format(
            label, " | ".join(fmt(nested(metrics["window"], path))
                              for _, metrics in variants)))

    lines.extend(["", "## Probability Metrics", "",
                  "| Metric | TCN | CNN |", "| --- | ---: | ---: |"])
    probability_fields = [
        ("Critical PR-AUC", ("critical_pr_auc",)),
        ("Safe PR-AUC", ("pr_auc_ovr", "0")),
        ("Macro PR-AUC", ("macro_pr_auc_ovr",)),
        ("Critical ROC-AUC", ("critical_roc_auc",)),
        ("Safe ROC-AUC", ("roc_auc_ovr", "0")),
        ("Macro ROC-AUC", ("macro_roc_auc_ovr",)),
        ("Log loss", ("log_loss",)),
        ("Binary Brier score", ("binary_brier_score",)),
        ("ECE, 15 bins", ("calibration", "ece")),
    ]
    for label, path in probability_fields:
        values = [nested(report["models"][name]["raw"]["window"], path)
                  for name in ("tcn", "cnn")]
        lines.append("| {} | {} |".format(label, " | ".join(map(fmt, values))))

    lines.extend(["", "## Confusion Matrices", "",
                  "| Variant | TN | FP | FN | TP |",
                  "| --- | ---: | ---: | ---: | ---: |"])
    for label, metrics in variants:
        matrix = metrics["window"]["confusion_matrix"]
        lines.append("| {} | {} | {} | {} | {} |".format(
            label, matrix[0][0], matrix[0][1], matrix[1][0], matrix[1][1]))

    lines.extend(["", "## Event Metrics", "",
                  "| Metric | TCN raw | CNN raw | TCN post | CNN post |",
                  "| --- | ---: | ---: | ---: | ---: |"])
    event_fields = [
        ("Trace count", "trace_count"),
        ("Critical event count", "critical_event_count"),
        ("Critical event detection rate", "critical_event_detection_rate"),
        ("Median Critical delay (ns)", "median_critical_delay_ns"),
        ("P95 Critical delay (ns)", "p95_critical_delay_ns"),
        ("False-alarm episodes", "false_alarm_episodes"),
        ("False alarms / trace", "false_alarms_per_trace"),
        ("Mean recovery delay (samples)", "mean_recovery_delay_samples"),
    ]
    for label, field in event_fields:
        lines.append("| {} | {} |".format(
            label, " | ".join(fmt(metrics["events"][field])
                              for _, metrics in variants)))

    lines.extend(["", "## Hard Pairs", "",
                  "| Metric | TCN | CNN |", "| --- | ---: | ---: |"])
    for label, field in (("Pair count", "pair_count"),
                         ("Scorable pair count", "scorable_pair_count"),
                         ("Pair accuracy", "pair_accuracy")):
        lines.append("| {} | {} | {} |".format(
            label, fmt(report["hard_pairs"]["tcn"][field]),
            fmt(report["hard_pairs"]["cnn"][field])))

    lines.extend(["", "## Paired Decisions", "",
                  "| Count | Raw | Postprocessed |",
                  "| --- | ---: | ---: |"])
    for field in ("agreement", "disagreement", "old_safe_binary_critical",
                  "old_critical_binary_safe", "both_correct", "both_wrong",
                  "old_only_correct", "binary_only_correct"):
        # The imported helper uses historical old/binary key names.  In this
        # report, old means TCN and binary means CNN; the explicit note below
        # prevents the compatibility vocabulary from being misinterpreted.
        lines.append("| {} | {} | {} |".format(
            field, report["paired_disagreements"]["raw"][field],
            report["paired_disagreements"]["postprocessed"][field]))
    lines.extend(["", "Here `old` means TCN and `binary` means CNN in the "
                  "compatibility field names above.", "", "## Complexity", "",
                  "| Metric | TCN | CNN | CNN reduction |",
                  "| --- | ---: | ---: | ---: |"])
    for label, field in (("Parameters", "parameter_count"),
                         ("Estimated MAC/window", "estimated_macs_per_window"),
                         ("Median CPU ms/window", "median_cpu_latency_ms_per_window")):
        tcn = report["complexity"]["tcn"][field]
        cnn = report["complexity"]["cnn"][field]
        lines.append("| {} | {} | {} | {}% |".format(
            label, fmt(tcn), fmt(cnn), fmt(100.0 * (1.0 - cnn / tcn))))
    lines.extend(["", "## Decision", "",
                  "- Final default model: binary 1D-CNN.",
                  "- TCN status: frozen historical quality baseline.",
                  "- Deployment ready: no.",
                  "- Aligned IID endpoints: {}.".format(
                      report["aligned_endpoint_count"]),
                  "- `parameters_tuned_on_test=false`.",
                  "- `pristine_blind_test=false`.",
                  "- `rerun_authorized=false`.", ""])
    return "\n".join(lines)


def parse_args():
    """Parse frozen evidence paths and a new absent report directory."""

    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("tcn-predictions", "tcn-report", "tcn-candidate",
                   "tcn-training-summary", "cnn-predictions", "cnn-report",
                   "cnn-candidate", "cnn-training-summary", "output-dir"):
        parser.add_argument("--" + option, required=True, type=Path)
    return parser.parse_args()


def main():
    """Build the reporting-only comparison and publish it atomically."""

    args = parse_args()
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite frozen CNN/TCN comparison")
    tcn_report, cnn_report = read_json(args.tcn_report), read_json(args.cnn_report)
    tcn_candidate = read_json(args.tcn_candidate)
    cnn_candidate = read_json(args.cnn_candidate)
    tcn_summary = read_json(args.tcn_training_summary)
    cnn_summary = read_json(args.cnn_training_summary)
    validate_inputs(args, tcn_report, cnn_report, tcn_candidate, cnn_candidate,
                    tcn_summary, cnn_summary)
    tcn_rows, cnn_rows = read_binary(args.tcn_predictions), read_binary(args.cnn_predictions)
    keys = align_rows(tcn_rows, cnn_rows)
    report = {
        "schema_version": 1, "scope": "frozen_iid_reporting_only",
        "task": "safe_critical_binary", "final_default_model": "cnn",
        "deployment_ready": False, "parameters_tuned_on_test": False,
        "pristine_blind_test": False, "rerun_authorized": False,
        "aligned_endpoint_count": len(keys),
        "trace_count": len({key[0] for key in keys}),
        "models": {
            "tcn": {"raw": score(tcn_rows, keys, "raw_prediction"),
                    "postprocessed": score(tcn_rows, keys, "prediction")},
            "cnn": {"raw": score(cnn_rows, keys, "raw_prediction"),
                    "postprocessed": score(cnn_rows, keys, "prediction")},
        },
        "hard_pairs": {"tcn": tcn_report["hard_pairs"],
                       "cnn": cnn_report["hard_pairs"]},
        "paired_disagreements": {
            "raw": paired_disagreements(tcn_rows, cnn_rows, keys, "raw_prediction"),
            "postprocessed": paired_disagreements(
                tcn_rows, cnn_rows, keys, "prediction"),
        },
        "complexity": {"tcn": complexity(tcn_summary),
                       "cnn": complexity(cnn_summary)},
        "inputs": {name + "_sha256": sha256_file(getattr(args, name))
                   for name in ("tcn_predictions", "tcn_report", "tcn_candidate",
                                "tcn_training_summary", "cnn_predictions",
                                "cnn_report", "cnn_candidate",
                                "cnn_training_summary")},
    }
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(
        prefix=".{}.tmp.".format(args.output_dir.name),
        dir=str(args.output_dir.parent)))
    try:
        (temporary / "comparison.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (temporary / "FINAL_REPORT.md").write_text(
            markdown_report(report), encoding="utf-8")
        os.rename(str(temporary), str(args.output_dir))
    finally:
        if temporary.exists():
            shutil.rmtree(str(temporary))


if __name__ == "__main__":
    main()
