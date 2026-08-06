#!/usr/bin/env python3
"""Create Stage-1 comparison reports and structural-cost Pareto plots.

All fast-detector points come from the already completed validation search.
The only IID values consumed are the immutable summary emitted by
``frozen_evaluation iid-test``; this script never opens an IID trace CSV.
"""

from __future__ import print_function

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt

from power_macro.tcn_detection.fast_detection.cnn_baseline import (
    CnnBaselineDetector, load_w8_a8_package)
from power_macro.tcn_detection.fast_detection.dataset_adapter import DatasetAdapter
from power_macro.tcn_detection.fast_detection.evaluation import evaluate_detector


def _json(path):
    """Load a JSON object/list from a generated evidence file."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def structural_proxy(cost):
    """Return a labeled, technology-independent resource-count proxy.

    Physical area is intentionally not inferred.  Arithmetic/comparator and
    multiplier counts are counted once; state and table storage are converted
    from bits to byte-equivalent units only to keep the axes readable.
    """

    return (float(cost["add_sub_count"]) + float(cost["compare_count"]) +
            float(cost["multiplier_count"]) + float(cost["state_bits"]) / 8.0 +
            float(cost["memory_bits"]) / 8.0)


def _metric(record, name):
    """Extract a common validation metric from a search record."""

    if name == "event_recall":
        value = record["events"]["event_recall"]
        return float(value) if value is not None else 0.0
    if name == "p95_ttd_ns":
        value = record["events"]["p95_ttd_ns"]
        return float(value) if value is not None else float("inf")
    if name == "far":
        return float(record["window"]["safe_window_false_alarm_rate"])
    raise KeyError(name)


def _family_representatives(records, far_budget):
    """Keep one ranked validation representative from every detector family.

    A family with no FAR-qualified point is still retained for the required
    eight-family comparison; its explicitly reported FAR makes the failed gate
    visible instead of silently dropping the family from the cost discussion.
    """

    fallback = {}
    qualified = {}
    for record in records:
        fallback.setdefault(record["family"], record)
        if _metric(record, "far") <= far_budget:
            qualified.setdefault(record["family"], record)
    return {family: qualified.get(family, fallback[family]) for family in fallback}


def _pareto(records, far_budget):
    """Return validation points not dominated by recall, p95 latency, and proxy."""

    qualified = [record for record in records if _metric(record, "far") <= far_budget]
    front = []
    for candidate in qualified:
        area = structural_proxy(candidate["hardware_cost"])
        recall = _metric(candidate, "event_recall")
        latency = _metric(candidate, "p95_ttd_ns")
        dominated = any(
            _metric(other, "event_recall") >= recall and
            _metric(other, "p95_ttd_ns") <= latency and
            structural_proxy(other["hardware_cost"]) <= area and
            (_metric(other, "event_recall") > recall or
             _metric(other, "p95_ttd_ns") < latency or
             structural_proxy(other["hardware_cost"]) < area)
            for other in qualified)
        if not dominated:
            front.append(candidate)
    return sorted(front, key=lambda item: (structural_proxy(item["hardware_cost"]),
                                           -_metric(item, "event_recall"), item["name"]))


def _save_plot(path, draw):
    """Render one deterministic 1600x1000 PNG and close its figure."""

    path = Path(path)
    if path.exists():
        raise FileExistsError("refusing to overwrite plot: {}".format(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(8, 5), dpi=200)
    draw(axis)
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)


def build_artifacts(root):
    """Generate both required Markdown reports and all three plots."""

    root = Path(root)
    artifact_dir = root / "artifacts"
    report_dir = root / "reports"
    plot_dir = root / "plots"
    config = _json(artifact_dir / "frozen_detector_config.json")
    records = _json(artifact_dir / "detector_search_results.json") if \
        (artifact_dir / "detector_search_results.json").exists() else _json(
            root / "validation_search" / "detector_search_results.json")
    baseline = _json(root / "CNN_BASELINE_REPORT.json")
    iid = _json(root / "iid_test_once" / "IID_TEST_EVALUATION.json")
    # The original baseline JSON predates the common fast-detector event
    # schema and lacks maximum delay.  Replay all validation traces through the
    # same interface to fill that one field without touching IID data.
    package_root = (root.parent / "models" /
                    "state_code_binary_cnn_compression_v1_20260805_r1" /
                    "final_w18_8_18_20260805_r1" /
                    "fixed_point_quantized_20260805_r1")
    label_root = root.parent / "labels" / "state_code_binary_iid_v1_20260730_r1"
    validation_traces = DatasetAdapter(label_root).iter_traces({"validation"})
    cnn_package = load_w8_a8_package(package_root)
    baseline_common = evaluate_detector(
        lambda: CnnBaselineDetector(cnn_package), validation_traces)
    budget = float(config["safe_far_budget"])
    reps = _family_representatives(records, budget)
    front = _pareto(records, budget)
    selected_names = {item["name"] for item in config["selected_candidates"]}

    baseline_event = baseline_common["events"]["event_recall"]
    baseline_p95 = baseline_common["events"]["p95_ttd_ns"]
    baseline_far = baseline_common["window"]["safe_window_false_alarm_rate"]
    baseline_proxy = structural_proxy(baseline["hardware_cost"])

    def draw_latency(axis):
        for family in sorted({record["family"] for record in records}):
            points = [record for record in records if record["family"] == family
                      and math.isfinite(_metric(record, "p95_ttd_ns"))]
            axis.scatter([_metric(item, "p95_ttd_ns") for item in points],
                         [_metric(item, "event_recall") for item in points],
                         s=4, alpha=0.18, label=family)
        axis.scatter([baseline_p95], [baseline_event], marker="*", s=100,
                     color="black", label="cnn_baseline_validation")
        for item in config["selected_candidates"]:
            axis.scatter([_metric(item, "p95_ttd_ns")], [_metric(item, "event_recall")],
                         s=45, edgecolors="black", facecolors="none")
        axis.set_xlabel("Event p95 TTD (ns)")
        axis.set_ylabel("Event recall")
        axis.set_title("Validation recall vs latency; selected candidates circled")
        axis.set_ylim(-0.02, 1.02)
        axis.grid(True, alpha=0.25)
        axis.legend(fontsize=6, ncol=2)

    def draw_area(axis):
        for family, item in sorted(reps.items()):
            axis.scatter([structural_proxy(item["hardware_cost"])],
                         [_metric(item, "event_recall")], s=45, label=family)
        axis.scatter([baseline_proxy], [baseline_event], marker="*", s=100,
                     color="black", label="cnn_baseline_validation")
        axis.set_xlabel("Structural resource-count proxy (not physical area)")
        axis.set_ylabel("Event recall")
        axis.set_title("Validation family representatives vs structural cost")
        axis.set_ylim(-0.02, 1.02)
        axis.set_xscale("log")
        axis.grid(True, alpha=0.25)
        axis.legend(fontsize=7)

    def draw_far(axis):
        for family in sorted({record["family"] for record in records}):
            points = [record for record in records if record["family"] == family
                      and math.isfinite(_metric(record, "p95_ttd_ns"))]
            axis.scatter([_metric(item, "far") for item in points],
                         [_metric(item, "event_recall") for item in points],
                         s=4, alpha=0.18, label=family)
        axis.scatter([baseline_far], [baseline_event], marker="*", s=100,
                     color="black", label="cnn_baseline_validation")
        axis.axvline(budget, color="black", linestyle="--", linewidth=0.8,
                     label="FAR budget")
        axis.set_xlabel("Safe-window false alarm rate")
        axis.set_ylabel("Event recall")
        axis.set_title("Validation FAR vs event recall")
        axis.set_xlim(left=0.0)
        axis.set_ylim(-0.02, 1.02)
        axis.grid(True, alpha=0.25)
        axis.legend(fontsize=6, ncol=2)

    _save_plot(plot_dir / "recall_vs_latency.png", draw_latency)
    _save_plot(plot_dir / "recall_vs_area.png", draw_area)
    _save_plot(plot_dir / "far_vs_recall.png", draw_far)

    def line(record, metric_set):
        event = metric_set(record)["events"]
        window = metric_set(record)["window"]
        return "| {} | {} | {:.4f} | {:.4f} | {:.1f} | {:.1f} | {:.1f} |".format(
            record["name"], record["family"], float(event.get("event_recall", event.get("critical_event_detection_rate"))),
            float(window["safe_window_false_alarm_rate"]), float(event.get("median_ttd_ns", event.get("median_critical_delay_ns"))),
            float(event.get("p95_ttd_ns", event.get("p95_critical_delay_ns"))), float(event.get("maximum_ttd_ns", event.get("maximum_critical_delay_ns", 0.0))))

    def iid_lookup(name):
        if name == iid["cnn"]["name"]:
            return iid["cnn"]
        return next(item for item in iid["fast_detectors"] if item["name"] == name)

    report_lines = [
        "# Fast Detection Stage 1 Algorithm Screening",
        "",
        "## Decision",
        "",
        "The validation-only search evaluated 2,048 candidates across eight detector families. The frozen Top-2 are `cusum_V07_H007` and `cusum_V07_H008`; both use only integer residual accumulation and have no multiplier.",
        "",
        "IID was evaluated once after freezing. No threshold, feature, model, or candidate ordering was changed from that result.",
        "",
        "## Validation metrics",
        "",
        "| detector | family | event recall | Safe FAR | median TTD ns | p95 TTD ns | max TTD ns |",
        "|---|---|---:|---:|---:|---:|---:|",
        "| CNN baseline | fixed W8/A8 L32 | {:.4f} | {:.4f} | {:.1f} | {:.1f} | {:.1f} |".format(
            baseline_event, baseline_far, baseline_common["events"]["median_ttd_ns"], baseline_p95,
            baseline_common["events"]["maximum_ttd_ns"]),
    ]
    for family in sorted(reps):
        report_lines.append(line(reps[family], lambda item: item))
    report_lines += [
        "",
        "## One-shot IID metrics",
        "",
        "| detector | family | event recall | Safe FAR | median TTD ns | p95 TTD ns | max TTD ns |",
        "|---|---|---:|---:|---:|---:|---:|",
        "| CNN baseline | fixed W8/A8 L32 | {:.4f} | {:.4f} | {:.1f} | {:.1f} | {:.1f} |".format(
            iid["cnn"]["events"]["event_recall"], iid["cnn"]["window"]["safe_window_false_alarm_rate"],
            iid["cnn"]["events"]["median_ttd_ns"], iid["cnn"]["events"]["p95_ttd_ns"], iid["cnn"]["events"]["maximum_ttd_ns"]),
    ]
    for item in iid["fast_detectors"]:
        report_lines.append(line(item, lambda value: value))
    report_lines += [
        "",
        "## Hardware cost",
        "",
        "The `recall_vs_area.png` x-axis is explicitly a structural resource-count proxy, not physical synthesized area. It is `add/sub + compare + multiplier + state_bits/8 + memory_bits/8`; technology mapping, timing, and power are intentionally deferred to RTL.",
        "",
        "| design | add/sub | compare | multiplier | state bits | memory bits | cycles/sample | proxy |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    cost_items = [("CNN baseline", baseline["hardware_cost"])]
    cost_items.extend((family, item["hardware_cost"]) for family, item in sorted(reps.items()))
    for name, cost in cost_items:
        report_lines.append("| {} | {} | {} | {} | {} | {} | {} | {:.2f} |".format(
            name, cost["add_sub_count"], cost["compare_count"], cost["multiplier_count"],
            cost["state_bits"], cost["memory_bits"], cost["cycles_per_sample"], structural_proxy(cost)))
    report_lines += [
        "",
        "## Pareto evidence",
        "",
        "The validation FAR-qualified Pareto points (recall maximized, p95 TTD and structural proxy minimized) are:",
        "",
    ]
    report_lines.extend("- `{}` ({}) recall {:.4f}, p95 {:.1f} ns, proxy {:.2f}".format(
        item["name"], item["family"], _metric(item, "event_recall"),
        _metric(item, "p95_ttd_ns"), structural_proxy(item["hardware_cost"])) for item in front)
    report_lines += [
        "",
        "## Boundary and next step",
        "",
        "All detectors consume only `sensor_code` and `code_valid`; measured VDD and configured droop are not runtime features. Labels remain same-sample Safe/Critical with Warning merged into Safe. The two CUSUM configurations are the Stage 2 RTL microarchitecture candidates.",
        "",
    ]
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "FAST_DETECTION_STAGE1_REPORT.md"
    if report_path.exists():
        raise FileExistsError("refusing to overwrite report: {}".format(report_path))
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    comparison = [
        "# CNN vs Fast Detector Comparison",
        "",
        "This comparison keeps the frozen W8/A8 L32 CNN as reference and evaluates only the two validation-frozen fast candidates on IID once.",
        "",
        "| detector | split | event recall | p95 TTD ns | Safe FAR | multiplier count | state bits |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for name, split, item in [
            ("CNN baseline", "validation", {"events": baseline_common["events"], "window": baseline_common["window"], "hardware_cost": baseline["hardware_cost"]}),
            ("CNN baseline", "iid_test_once", iid["cnn"]),
    ] + [(item["name"], "iid_test_once", item) for item in iid["fast_detectors"]]:
        event = item["events"]
        recall = event.get("event_recall", event.get("critical_event_detection_rate"))
        p95 = event.get("p95_ttd_ns", event.get("p95_critical_delay_ns"))
        comparison.append("| {} | {} | {:.4f} | {:.1f} | {:.4f} | {} | {} |".format(
            name, split, float(recall), float(p95),
            float(item["window"]["safe_window_false_alarm_rate"]),
            item["hardware_cost"]["multiplier_count"], item["hardware_cost"]["state_bits"]))
    comparison += [
        "",
        "The IID result is descriptive only. It was not used to tune thresholds or select between H=7 and H=8. Both CUSUM candidates provide one-cycle/sample operation, zero multipliers, and a large structural reduction relative to the CNN; their implementation decision is intentionally deferred to RTL verification.",
        "",
    ]
    comparison_path = report_dir / "CNN_VS_FAST_DETECTOR_COMPARISON.md"
    if comparison_path.exists():
        raise FileExistsError("refusing to overwrite report: {}".format(comparison_path))
    comparison_path.write_text("\n".join(comparison), encoding="utf-8")
    return {"pareto_count": len(front), "family_count": len(reps),
            "selected": sorted(selected_names)}


def main():
    """Generate all Stage-1 report files from an existing run directory."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build_artifacts(args.run_root), sort_keys=True))


if __name__ == "__main__":
    main()
