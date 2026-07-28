#!/usr/bin/env python3
"""Generate the fourteen required publication-style figures from frozen reports."""

from __future__ import print_function

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from sklearn.metrics import precision_recall_curve


COLORS = {"vdd": "#007C91", "code": "#354A5A", "safe": "#D9E2E8", "warning": "#E9B949", "critical": "#C8483E",
          "tcn": "#007C91", "cnn": "#6C757D", "cae": "#9B5DE5", "threshold": "#E76F51"}
CLASS_NAMES = ["Safe", "Warning", "Critical"]


def read_json(path):
    """Read one immutable JSON report or corpus without implicit defaults."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_label_trace(label_dir, trace_id):
    """Load one complete label trace for figure-only physical analysis."""

    with (Path(label_dir) / (trace_id + ".csv")).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def save_figure(figure, output_dir, stem):
    """Write only one vector PDF and one 300 dpi PNG per required figure."""

    figure.tight_layout()
    figure.savefig(Path(output_dir) / (stem + ".pdf"), bbox_inches="tight")
    figure.savefig(Path(output_dir) / (stem + ".png"), dpi=300, bbox_inches="tight")
    plt.close(figure)


def trace_series(rows):
    """Return chronological time, measured VDD, sensor code, and risk labels."""

    return (np.asarray([float(row["sample_time_s"]) * 1.0e9 for row in rows]),
            np.asarray([float(row["measured_vdd_a_v"]) * 1.0e3 for row in rows]),
            np.asarray([int(row["sensor_code"]) for row in rows]),
            np.asarray([int(row["hysteresis_label"]) if row["hysteresis_label"] else -1 for row in rows]))


def label_spans(axis, times, labels):
    """Paint transparent Safe/Warning/Critical intervals, excluding ineligible tail."""

    start = 0
    while start < len(labels):
        label = labels[start]
        end = start + 1
        while end < len(labels) and labels[end] == label:
            end += 1
        if label >= 0:
            axis.axvspan(times[start], times[end - 1] + 4.0, color=(COLORS["safe"], COLORS["warning"], COLORS["critical"])[label], alpha=0.25, linewidth=0)
        start = end


def main():
    """Build figures 01--14 with fixed trace selection from the authoritative corpus."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-dir", required=True, type=Path)
    parser.add_argument("--label-dir", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--split-audit", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite figure directory: {}".format(args.output_dir))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5, "axes.linewidth": 0.75, "pdf.fonttype": 42, "ps.fonttype": 42})
    report = read_json(args.evaluation_dir / "evaluation_report.json")
    audit = read_json(args.split_audit)
    corpus_rows = [json.loads(line) for line in args.corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    corpus = {row["trace_id"]: row for row in corpus_rows}
    predictions = defaultdict(list)
    with (args.evaluation_dir / "predictions_L16.csv").open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            predictions[row["method"]].append(row)

    # 01: direct-rail sensing and causal prediction flow.
    figure, axis = plt.subplots(figsize=(10.5, 2.4)); axis.axis("off")
    boxes = [(0.03, "Direct VDD_A\nwaveform"), (0.25, "Vernier DFF\nsensor"), (0.47, "5 online\nfeatures"), (0.69, "Causal\nTCN"), (0.89, "Future risk\nSafe/Warn/Crit")]
    for x, text in boxes:
        axis.add_patch(FancyBboxPatch((x, 0.32), 0.12, 0.34, boxstyle="round,pad=0.02", facecolor="#EAF2F5", edgecolor=COLORS["vdd"]))
        axis.text(x + 0.06, 0.49, text, ha="center", va="center", fontweight="semibold")
    for (left, _), (right, _) in zip(boxes, boxes[1:]):
        axis.add_patch(FancyArrowPatch((left + 0.125, 0.49), (right - 0.01, 0.49), arrowstyle="->", mutation_scale=12, color="#4D5B66"))
    axis.text(0.5, 0.08, "Electrical VDD and slack are retained for labeling/analysis only; online inference consumes sensor-derived digital channels.", ha="center", fontsize=8)
    save_figure(figure, args.output_dir, "01_dataset_flow")

    # Choose deterministic traces by sorted trace ID to make every figure reproducible.
    by_mode = {mode: next(row for row in sorted(corpus_rows, key=lambda item: item["trace_id"]) if row["background_mode"] == mode and row["event"] is None)
               for mode in ("busy", "bursty", "mixed", "randomizer_like")}
    figure, axes = plt.subplots(2, 2, figsize=(10, 5.5), sharex=True)
    for axis, (mode, metadata) in zip(axes.flat, by_mode.items()):
        times, vdd, code, labels = trace_series(read_label_trace(args.label_dir, metadata["trace_id"]))
        axis.plot(times, vdd, color=COLORS["vdd"], lw=1.0); axis.set_title(mode.replace("_", " "))
        axis.set_ylabel("VDD_A (mV)"); axis.grid(axis="y", alpha=0.25)
    for axis in axes[-1]: axis.set_xlabel("Time (ns)")
    save_figure(figure, args.output_dir, "02_background_examples")

    known = next(row for row in corpus_rows if row["split"] == "train" and row["event"] and row["waveform_family_id"] == "trapezoid")
    ood = next(row for row in corpus_rows if row["split"] == "ood_test" and row["event"])
    figure, axes = plt.subplots(1, 2, figsize=(10, 3.2), sharey=True)
    for axis, metadata, title in zip(axes, (known, ood), ("Known training waveform", "OOD waveform")):
        times, vdd, _, labels = trace_series(read_label_trace(args.label_dir, metadata["trace_id"]))
        label_spans(axis, times, labels); axis.plot(times, vdd, color=COLORS["vdd"], lw=1.1)
        axis.set_title("{}: {}".format(title, metadata["waveform_family_id"])); axis.set_xlabel("Time (ns)"); axis.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Measured VDD_A (mV)"); save_figure(figure, args.output_dir, "03_known_and_ood_waveforms")

    selected = ood; rows = read_label_trace(args.label_dir, selected["trace_id"]); times, vdd, code, labels = trace_series(rows)
    figure, axis = plt.subplots(figsize=(10, 3.2)); axis.step(times, code, where="mid", color=COLORS["code"], lw=1.0); axis.set_ylim(-0.5, 32.5)
    axis.set_xlabel("Time (ns)"); axis.set_ylabel("Vernier sensor code"); axis.set_title("Sensor-code trajectory: {}".format(selected["waveform_family_id"])); axis.grid(axis="y", alpha=0.25)
    save_figure(figure, args.output_dir, "04_sensor_code_timeseries")

    figure, axis = plt.subplots(figsize=(10, 3.2)); label_spans(axis, times, labels); axis.step(times, labels, where="mid", color="#27313A", lw=1.0)
    axis.set_ylim(-0.2, 2.3); axis.set_yticks((0, 1, 2), CLASS_NAMES); axis.set_xlabel("Decision endpoint time (ns)"); axis.set_ylabel("Future risk label")
    axis.set_title("Slack-derived future-risk timeline"); save_figure(figure, args.output_dir, "05_label_timeline")

    class_counts = read_json(args.evaluation_dir.parent / "reports" / "v1" / "dataset_validation_v1.json") if False else None
    # The evaluation report has raw supports for each test split; the source
    # validation report is outside this directory, so derive full Pilot class
    # counts directly from label CSVs rather than relying on an implicit path.
    counts = Counter()
    for source in Path(args.label_dir).glob("*.csv"):
        for row in read_label_trace(args.label_dir, source.stem):
            if row["label_eligible"] == "True": counts[int(row["hysteresis_label"])] += 1
    figure, axis = plt.subplots(figsize=(5.4, 3.4)); axis.bar(CLASS_NAMES, [counts[index] for index in range(3)], color=[COLORS["safe"], COLORS["warning"], COLORS["critical"]])
    axis.set_ylabel("Eligible samples"); axis.set_title("Pilot class distribution"); save_figure(figure, args.output_dir, "06_class_distribution")

    split_counts = audit["split_counts"]
    figure, axis = plt.subplots(figsize=(5.8, 3.4)); names = list(split_counts); axis.bar(names, [split_counts[name] for name in names], color="#5B8C85")
    axis.set_ylabel("Complete traces"); axis.set_title("Strict base-waveform split audit"); save_figure(figure, args.output_dir, "07_split_audit")

    matrix = np.asarray(report["methods"]["tcn"]["window"]["ood_test"]["confusion_matrix"])
    figure, axis = plt.subplots(figsize=(4.2, 3.8)); image = axis.imshow(matrix, cmap="Blues")
    for row in range(3):
        for column in range(3): axis.text(column, row, str(matrix[row, column]), ha="center", va="center")
    axis.set_xticks(range(3), CLASS_NAMES); axis.set_yticks(range(3), CLASS_NAMES); axis.set_xlabel("Predicted"); axis.set_ylabel("Truth"); axis.set_title("TCN OOD confusion matrix"); figure.colorbar(image, ax=axis)
    save_figure(figure, args.output_dir, "08_confusion_matrix")

    figure, axes = plt.subplots(1, 3, figsize=(10.5, 3.1), sharey=True)
    for class_id, axis in enumerate(axes):
        for method in ("cnn", "tcn"):
            rows_method = [row for row in predictions[method] if row["split"] == "ood_test"]
            labels_method = np.asarray([int(row["target_label"]) == class_id for row in rows_method])
            scores = np.asarray([float(row["prob_safe" if class_id == 0 else "prob_warning" if class_id == 1 else "prob_critical"]) for row in rows_method])
            precision, recall, _ = precision_recall_curve(labels_method, scores); axis.plot(recall, precision, label=method.upper(), color=COLORS[method])
        axis.set_title(CLASS_NAMES[class_id]); axis.set_xlabel("Recall"); axis.grid(alpha=0.25)
    axes[0].set_ylabel("Precision"); axes[0].legend(frameon=False); save_figure(figure, args.output_dir, "09_pr_curves")

    event_trace = next(row for row in corpus_rows if row["split"] == "ood_test" and row["event"] and row["event"]["amplitude_mv"] > 50)
    event_rows = read_label_trace(args.label_dir, event_trace["trace_id"]); event_times, event_vdd, _, event_labels = trace_series(event_rows)
    tcn_trace = [row for row in predictions["tcn"] if row["trace_id"] == event_trace["trace_id"]]
    figure, axis = plt.subplots(figsize=(10, 3.5)); label_spans(axis, event_times, event_labels); axis.plot(event_times, event_vdd, color=COLORS["vdd"], label="Measured VDD_A")
    second = axis.twinx(); second.step([float(row["end_index"]) * 4.0 + 2.5 for row in tcn_trace], [int(row["prediction"]) for row in tcn_trace], where="mid", color=COLORS["tcn"], label="TCN prediction")
    axis.set_xlabel("Time (ns)"); axis.set_ylabel("VDD_A (mV)"); second.set_ylabel("Predicted risk"); axis.set_title("OOD event detection timeline"); save_figure(figure, args.output_dir, "10_event_timeline")

    figure, axis = plt.subplots(figsize=(5.5, 3.5))
    scan = report["methods"]["tcn"]["confirmation"]["scan"]; axis.plot([item["confirm_count"] for item in scan], [item["false_alarms_per_us"] for item in scan], marker="o", color=COLORS["tcn"])
    axis.set_xlabel("K_confirm"); axis.set_ylabel("False alarms / us"); axis.set_title("Validation confirmation trade-off"); axis.grid(alpha=0.25); save_figure(figure, args.output_dir, "11_confirmation_tradeoff")

    figure, axis = plt.subplots(figsize=(7.3, 3.5)); lead_data = []; lead_names = []
    for method in ("cae", "cnn", "tcn", "threshold_sensor_code"):
        values = report["methods"][method]["events"]["ood_test"]["lead_times_ns"]
        if values: lead_data.append(values); lead_names.append(method.replace("threshold_sensor_code", "threshold"))
    axis.boxplot(lead_data, tick_labels=lead_names, showfliers=False); axis.axhline(0, color="#555555", lw=0.8); axis.set_ylabel("Alarm-to-violation lead (ns)"); axis.set_title("OOD Critical-event lead time"); save_figure(figure, args.output_dir, "12_lead_time_distribution")

    pair_id = "hard_pair_00"; pair_members = [row for row in corpus_rows if row.get("hard_pair_id") == pair_id]
    figure, axes = plt.subplots(2, 1, figsize=(10, 4.4), sharex=True)
    for axis, metadata in zip(axes, pair_members):
        pair_rows = read_label_trace(args.label_dir, metadata["trace_id"]); pair_times, _, pair_code, _ = trace_series(pair_rows)
        axis.step(pair_times, pair_code, where="mid", color=COLORS["code"], label="sensor code")
        pair_prediction = [row for row in predictions["tcn"] if row["trace_id"] == metadata["trace_id"]]
        axis.step([int(row["end_index"]) * 4.0 + 2.5 for row in pair_prediction], [int(row["prediction"]) * 10 for row in pair_prediction], where="mid", color=COLORS["tcn"], label="TCN risk x10")
        axis.axvline(metadata["hard_pair_decision_index"] * 4.0 + 2.5, color=COLORS["critical"], ls="--", lw=0.9); axis.set_ylabel(metadata["waveform_family_id"])
    axes[0].legend(frameon=False, ncol=2); axes[-1].set_xlabel("Time (ns)"); figure.suptitle("Hard pair {}".format(pair_id)); save_figure(figure, args.output_dir, "13_hard_pair_comparison")

    methods = ["threshold_sensor_code", "cae", "cnn", "tcn"]
    labels = ["Threshold", "CAE", "CNN", "TCN"]
    figure, axes = plt.subplots(1, 2, figsize=(8.3, 3.5), sharey=True)
    for axis, split in zip(axes, ("iid_test", "ood_test")):
        axis.bar(labels, [report["methods"][method]["window"][split]["macro_f1"] for method in methods], color=[COLORS["threshold"], COLORS["cae"], COLORS["cnn"], COLORS["tcn"]])
        axis.set_title(split.replace("_", " ")); axis.set_ylim(0, 1); axis.set_ylabel("Window macro-F1")
    save_figure(figure, args.output_dir, "14_model_comparison")

    (args.output_dir / "figure_manifest.json").write_text(json.dumps({"schema_version": 1, "figure_count": 14,
        "corpus": str(args.corpus.resolve()), "evaluation_report": str((args.evaluation_dir / "evaluation_report.json").resolve()),
        "background_limit": report["background_generalization_limit"]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
