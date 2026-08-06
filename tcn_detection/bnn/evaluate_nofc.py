#!/usr/bin/env python3
"""Freeze, export, and compare the Stage-1B full-binary no-FC candidates."""

from __future__ import print_function

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.bnn.bittrue_nofc import load_package
from power_macro.tcn_detection.bnn.export_nofc_package import export_checkpoint
from power_macro.tcn_detection.bnn.nofc_model import BinaryNoFCModel, FPNoFCModel
from power_macro.tcn_detection.bnn.train_nofc_bnn import (
    load_training_arrays,
    probabilities_from_scores,
)
from power_macro.tcn_detection.evaluate.binary_metrics import binary_window_metrics
from power_macro.tcn_detection.fast_detection.bnn_nofc_baseline import BnnNofcDetector
from power_macro.tcn_detection.fast_detection.dataset_adapter import DatasetAdapter
from power_macro.tcn_detection.fast_detection.evaluation import event_metrics, replay_detector
from power_macro.tcn_detection.fast_detection.cnn_baseline import load_w8_a8_package
from power_macro.tcn_detection.fast_detection.dataset_adapter import DatasetAdapter
from power_macro.tcn_detection.fast_detection.evaluation import evaluate_detector


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def _run_dir(run_root, width, seed):
    prefix = "bnn_s_w8_seed{}".format(int(seed)) if int(width) == 8 else "bnn_m_w16_seed{}".format(int(seed))
    return Path(run_root) / "models" / "bnn_stage1b_v1_20260806_r1" / prefix


def _load_model_from_checkpoint(checkpoint_path):
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if checkpoint["stage"] == "fp_pretrain":
        model = FPNoFCModel(int(checkpoint["width"]))
    else:
        model = BinaryNoFCModel(int(checkpoint["width"]), checkpoint["mode"])
    model.load_state_dict(checkpoint["state_dict"], strict=True)
    model.eval()
    return checkpoint, model


def _forward_batches(model, features, batch_size=512):
    """Collect temporal head bits, vote counts, and scalar scores for windows."""

    features = np.asarray(features, dtype=np.float32)
    bits = []
    votes = []
    scores = []
    with torch.no_grad():
        for start in range(0, len(features), int(batch_size)):
            batch = torch.from_numpy(features[start:start + int(batch_size)])
            output = model(batch)
            temporal_bits = output.get("temporal_bits")
            if temporal_bits is None:
                # The FP control stage does not store hard bits, so the common
                # threshold rule is reconstructed here from its temporal logits.
                temporal_bits = (output["temporal_logits"] >= 0.0).to(dtype=torch.uint8)
            temporal_bits = temporal_bits.cpu().numpy().astype(np.uint8)
            bits.append(temporal_bits)
            votes.append(temporal_bits[:, 0, :].sum(axis=1).astype(np.int64))
            scores.append(output["score"].cpu().numpy().astype(np.float64))
    return {
        "temporal_bits": np.concatenate(bits),
        "vote_count": np.concatenate(votes),
        "score": np.concatenate(scores),
    }


def _window_rows(metadata, labels, predictions):
    return [{"trace_id": row["trace_id"], "split": row["split"],
             "end_index": int(row["end_index"]), "target_label": int(label),
             "prediction": int(prediction)}
            for row, label, prediction in zip(metadata, labels, predictions)]


def _evaluate_k_grid(bits, score, labels, metadata):
    """Evaluate all K choices for one model/seed on the validation split."""

    metrics = {}
    probabilities = probabilities_from_scores(score)
    for k in range(1, 33):
        predictions = (bits >= k).astype(np.uint8)
        window = binary_window_metrics(labels, predictions, probabilities)
        rows = _window_rows(metadata, labels, predictions)
        events = event_metrics(rows)
        metrics[k] = {"window": window, "events": events,
                      "predictions": predictions, "rows": rows}
    return metrics


def _selection_key(window, events, width, k):
    """Rank a candidate with the frozen validation ordering used here."""

    far = float(window["safe_window_false_alarm_rate"])
    recall = float(events["event_recall"] if events["event_recall"] is not None else 0.0)
    mcc = float(window["matthews_correlation_coefficient"])
    p95 = float(events["p95_ttd_ns"] if events["p95_ttd_ns"] is not None else float("inf"))
    return (0 if far <= 0.05 else 1, -recall, -mcc, p95, int(width), int(k))


def _representative_seed(candidate_metrics):
    """Pick the seed nearest the median PR-AUC after the width/K are frozen."""

    pr_aucs = np.asarray([item["window"]["critical_pr_auc"] for item in candidate_metrics], dtype=np.float64)
    median = float(np.median(pr_aucs))
    return min(candidate_metrics, key=lambda item: (
        abs(float(item["window"]["critical_pr_auc"]) - median),
        -float(item["window"]["matthews_correlation_coefficient"]),
        float(item["events"]["p95_ttd_ns"] if item["events"]["p95_ttd_ns"] is not None else float("inf")),
        int(item["seed"]),
    ))


def _load_validation_arrays(windows):
    arrays = load_training_arrays(windows)
    return arrays["validation_features"], arrays["validation_labels"], arrays["validation_metadata"]


def _load_candidate(run_root, width, seed, stage):
    checkpoint_path = _run_dir(run_root, width, seed) / stage / "best_checkpoint.pt"
    if not checkpoint_path.is_file():
        raise FileNotFoundError("missing checkpoint: {}".format(checkpoint_path))
    checkpoint, model = _load_model_from_checkpoint(checkpoint_path)
    return checkpoint, model, checkpoint_path


def _validation_summary(run_root, windows):
    """Select width/K/seed, export final packages, and write validation evidence."""

    validation_features, validation_labels, validation_metadata = _load_validation_arrays(windows)
    seeds = (11, 22, 33)
    widths = (8, 16)
    selected = []
    per_width = {}
    for width in widths:
        seed_metrics = []
        for seed in seeds:
            fp_checkpoint, fp_model, _ = _load_candidate(run_root, width, seed, "fp_pretrain")
            a8_checkpoint, a8_model, _ = _load_candidate(run_root, width, seed, "w1a8")
            a1_checkpoint, a1_model, checkpoint_path = _load_candidate(run_root, width, seed, "w1a1")
            outputs = _forward_batches(a1_model, validation_features)
            k_metrics = _evaluate_k_grid(outputs["vote_count"], outputs["score"],
                                         validation_labels, validation_metadata)
            selected_k, selected_metrics = min(
                k_metrics.items(), key=lambda item: _selection_key(
                    item[1]["window"], item[1]["events"], width, item[0]))
            seed_metrics.append({
                "seed": seed, "width": width, "checkpoint_path": str(checkpoint_path),
                "selected_k": int(selected_k),
                "selected_window": selected_metrics["window"],
                "selected_events": selected_metrics["events"],
                "k_metrics": k_metrics,
            })
        per_width[width] = seed_metrics
        selected.append({
            "width": width,
            "selected_k": int(min(seed_metrics, key=lambda item: _selection_key(
                item["selected_window"], item["selected_events"], width, item["selected_k"]))["selected_k"]),
        })

    final_candidates = []
    for width in widths:
        seed_metrics = per_width[width]
        # Freeze K using the median aggregate of the seed-specific selected-K
        # winners.  This avoids choosing a seed before the width has been ranked.
        candidate_by_k = {}
        for seed_item in seed_metrics:
            k = seed_item["selected_k"]
            candidate_by_k.setdefault(k, []).append(seed_item)
        # Determine the best width-wide K using medians across seeds.
        per_k = []
        for k in range(1, 33):
            samples = [item["k_metrics"][k] for item in seed_metrics]
            window = {key: float(np.median([sample["window"][key] for sample in samples]))
                      for key in samples[0]["window"] if isinstance(samples[0]["window"][key], (int, float, np.floating))}
            events = {key: float(np.median([
                sample["events"][key] if sample["events"][key] is not None else np.nan
                for sample in samples]))
                      for key in samples[0]["events"]
                      if isinstance(samples[0]["events"][key], (int, float, np.floating)) or samples[0]["events"][key] is None}
            per_k.append({"k": k, "window": window, "events": events})
        width_selected = min(per_k, key=lambda item: _selection_key(item["window"], item["events"], width, item["k"]))
        selected_k = int(width_selected["k"])
        chosen_seed = _representative_seed([
            {"seed": item["seed"], "window": item["k_metrics"][selected_k]["window"],
             "events": item["k_metrics"][selected_k]["events"], "checkpoint_path": item["checkpoint_path"],
             "selected_k": selected_k}
            for item in seed_metrics
        ])
        final_candidates.append({
            "width": int(width), "selected_k": selected_k,
            "representative_seed": int(chosen_seed["seed"]),
            "validation_window": chosen_seed["window"],
            "validation_events": chosen_seed["events"],
            "checkpoint_path": chosen_seed["checkpoint_path"],
        })

    primary = min(final_candidates, key=lambda item: _selection_key(
        item["validation_window"], item["validation_events"], item["width"], item["selected_k"]))

    freeze_root = Path(run_root) / "models" / "bnn_stage1b_v1_20260806_r5"
    frozen_dir = freeze_root / "artifacts"
    frozen_dir.mkdir(parents=True, exist_ok=True)
    package_root = freeze_root / "packages" / "final"
    package_root.mkdir(parents=True, exist_ok=True)
    final_packages = []
    for candidate in final_candidates:
        width = candidate["width"]
        seed = candidate["representative_seed"]
        checkpoint_path = _run_dir(run_root, width, seed) / "w1a1" / "best_checkpoint.pt"
        export_dir = package_root / ("bnn_{}{}_k{}_seed{}".format(
            "s_w8" if width == 8 else "m_w16", "", candidate["selected_k"], seed))
        manifest, equality = export_checkpoint(
            checkpoint_path, windows, export_dir, candidate["selected_k"])
        fp_checkpoint, fp_model, _ = _load_candidate(run_root, width, seed, "fp_pretrain")
        a8_checkpoint, a8_model, _ = _load_candidate(run_root, width, seed, "w1a8")
        validation_features, validation_labels, validation_metadata = _load_validation_arrays(windows)
        fp_outputs = _forward_batches(fp_model, validation_features)
        a8_outputs = _forward_batches(a8_model, validation_features)
        # Re-load the W1A1 model so the final report can compare all three stages
        # on the same representative seed and frozen K without using the test set.
        _, bnn_model, _ = _load_candidate(run_root, width, seed, "w1a1")
        bnn_outputs = _forward_batches(bnn_model, validation_features)
        fp_k_metrics = _evaluate_k_grid(fp_outputs["vote_count"], fp_outputs["score"], validation_labels, validation_metadata)[candidate["selected_k"]]
        a8_k_metrics = _evaluate_k_grid(a8_outputs["vote_count"], a8_outputs["score"], validation_labels, validation_metadata)[candidate["selected_k"]]
        bnn_k_metrics = _evaluate_k_grid(bnn_outputs["vote_count"], bnn_outputs["score"], validation_labels, validation_metadata)[candidate["selected_k"]]
        final_packages.append({
            "width": width, "seed": seed, "selected_k": candidate["selected_k"],
            "package_root": str(export_dir), "package_manifest": manifest,
            "fp_validation": {"window": fp_k_metrics["window"], "events": fp_k_metrics["events"]},
            "w1a8_validation": {"window": a8_k_metrics["window"], "events": a8_k_metrics["events"]},
            "bnn_validation": {"window": bnn_k_metrics["window"], "events": bnn_k_metrics["events"]},
            "validation_equality": equality,
        })

    freeze = {
        "schema_version": 1,
        "scope": "frozen_full_binary_bnn_before_iid_test",
        "task": "safe_critical_binary",
        "window_length": 32,
        "selected_primary": primary,
        "candidates": final_candidates,
        "final_packages": final_packages,
        "validation_features_loaded": True,
        "iid_metrics_computed": False,
    }
    _write_json(frozen_dir / "frozen_bnn_config.json", freeze)
    return freeze


def _evaluate_detector_package(package_root, label_root):
    """Replay the exported detector once through every IID trace."""

    package = load_package(package_root)
    detector = BnnNofcDetector(package)
    adapter = DatasetAdapter(label_root)
    traces = adapter.iter_traces({"iid_test"})
    rows = []
    for trace in traces:
        rows.extend(replay_detector(detector, trace))
    labels = np.asarray([row["target_label"] for row in rows], dtype=np.int64)
    predictions = np.asarray([row["prediction"] for row in rows], dtype=np.int64)
    window = binary_window_metrics(labels, predictions)
    events = event_metrics(rows)
    return {"rows": rows, "window": window, "events": events,
            "trace_count": len(traces)}


def _validation_report(run_root, freeze):
    cnn_validation = _json(Path(run_root) / "fast_detection_stage1_v1" / "CNN_BASELINE_REPORT.json")
    cusum_validation = _json(Path(run_root) / "fast_detection_stage1_v1" / "artifacts" / "frozen_detector_config.json")
    records = []
    for item in freeze["candidates"]:
        records.append({
            "name": "bnn_{}{}_k{}_seed{}".format("s_w8" if item["width"] == 8 else "m_w16", "", item["selected_k"], item["representative_seed"]),
            "family": "bnn_nofc",
            "width": item["width"], "seed": item["representative_seed"],
            "k": item["selected_k"],
            "window": item["validation_window"],
            "events": item["validation_events"],
        })
    lines = [
        "# BNN Stage 1-B Validation Comparison", "",
        "Stage 1-B is validation-frozen before IID.  The primary candidate is `{}` with K={} and seed {}.".format(
            freeze["selected_primary"]["width"], freeze["selected_primary"]["selected_k"], freeze["selected_primary"]["representative_seed"]),
        "",
        "| model | stage | width | seed | K | event recall | Safe FAR | p95 TTD ns | MCC |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        "| CNN W8/A8 | validation | 8 | - | - | {:.4f} | {:.4f} | {:.1f} | {:.4f} |".format(
            cnn_validation["events"]["critical_event_detection_rate"],
            cnn_validation["window"]["safe_window_false_alarm_rate"],
            cnn_validation["events"]["p95_critical_delay_ns"], cnn_validation["window"]["matthews_correlation_coefficient"]),
    ]
    for item in freeze["final_packages"]:
        for stage_name, stage_key in (("FP thermometer", "fp_validation"),
                                      ("W1A8 BNN", "w1a8_validation"),
                                      ("W1A1 BNN", "bnn_validation")):
            lines.append("| {} | validation | {} | {} | {} | {:.4f} | {:.4f} | {:.1f} | {:.4f} |".format(
                stage_name, item["width"], item["seed"], item["selected_k"],
                float(item[stage_key]["events"]["event_recall"]),
                float(item[stage_key]["window"]["safe_window_false_alarm_rate"]),
                float(item[stage_key]["events"]["p95_ttd_ns"]),
                float(item[stage_key]["window"]["matthews_correlation_coefficient"])))
    lines += [
        "",
        "## Frozen CNN reference", "",
        "| candidate | event recall | Safe FAR | p95 TTD ns | MCC |",
        "|---|---:|---:|---:|---:|",
        "| CNN frozen | {:.4f} | {:.4f} | {:.1f} | {:.4f} |".format(
            cnn_validation["events"]["critical_event_detection_rate"],
            cnn_validation["window"]["safe_window_false_alarm_rate"],
            cnn_validation["events"]["p95_critical_delay_ns"], cnn_validation["window"]["matthews_correlation_coefficient"]),
        "",
        "## Frozen CUSUM reference", "",
        "| candidate | event recall | Safe FAR | p95 TTD ns | MCC |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in cusum_validation["selected_candidates"]:
        lines.append("| {} | {:.4f} | {:.4f} | {:.1f} | {:.4f} |".format(
            item["name"], float(item["events"]["event_recall"]),
            float(item["window"]["safe_window_false_alarm_rate"]),
            float(item["events"]["p95_ttd_ns"]), float(item["window"]["matthews_correlation_coefficient"])))
    return "\n".join(lines) + "\n"


def _iid_report(run_root, freeze, iid_results):
    cnn_iid = _json(Path(run_root) / "fast_detection_stage1_v1" / "iid_test_once" / "IID_TEST_EVALUATION.json")
    cusum_iid = cnn_iid["fast_detectors"]
    lines = [
        "# BNN Stage 1-B IID Comparison", "",
        "The IID evaluation was run exactly once after freezing the BNN packages.", "",
        "| model | width | seed | K | event recall | Safe FAR | p95 TTD ns | MCC |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in freeze["final_packages"]:
        iid = iid_results[(item["width"], item["seed"]) ]
        lines.append("| BNN | {} | {} | {} | {:.4f} | {:.4f} | {:.1f} | {:.4f} |".format(
            item["width"], item["seed"], item["selected_k"],
            float(iid["events"]["event_recall"]), float(iid["window"]["safe_window_false_alarm_rate"]),
            float(iid["events"]["p95_ttd_ns"]), float(iid["window"]["matthews_correlation_coefficient"])))
    lines += [
        "",
        "## Frozen CNN IID reference", "",
        "| candidate | event recall | Safe FAR | p95 TTD ns | MCC |",
        "|---|---:|---:|---:|---:|",
        "| CNN frozen | {:.4f} | {:.4f} | {:.1f} | {:.4f} |".format(
            cnn_iid["cnn"]["events"]["event_recall"], cnn_iid["cnn"]["window"]["safe_window_false_alarm_rate"],
            cnn_iid["cnn"]["events"]["p95_ttd_ns"], cnn_iid["cnn"]["window"]["matthews_correlation_coefficient"]),
        "",
        "## Frozen CUSUM IID reference", "",
        "| candidate | event recall | Safe FAR | p95 TTD ns | MCC |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in cusum_iid:
        lines.append("| {} | {:.4f} | {:.4f} | {:.1f} | {:.4f} |".format(
            item["name"], float(item["events"]["event_recall"]),
            float(item["window"]["safe_window_false_alarm_rate"]),
            float(item["events"]["p95_ttd_ns"]), float(item["window"]["matthews_correlation_coefficient"])))
    return "\n".join(lines) + "\n"


def cmd_select(args):
    freeze = _validation_summary(args.run_root, args.windows)
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    (Path(args.output_dir) / "BNN_STAGE1B_VALIDATION.md").write_text(
        _validation_report(args.run_root, freeze), encoding="utf-8")
    return freeze


def cmd_iid_test(args):
    freeze = _json(Path(args.run_root) / "models" / "bnn_stage1b_v1_20260806_r5" / "artifacts" / "frozen_bnn_config.json")
    iid_results = {}
    for item in freeze["final_packages"]:
        iid = _evaluate_detector_package(item["package_root"], args.label_root)
        iid_results[(int(item["width"]), int(item["seed"]))] = iid
    payload = {"schema_version": 1, "scope": "frozen_full_binary_bnn_iid_test_once",
               "iid_metrics_computed": True, "results": {
                   str(key): {"window": value["window"], "events": value["events"],
                              "trace_count": value["trace_count"]}
                   for key, value in iid_results.items()}}
    out_dir = Path(args.run_root) / "models" / "bnn_stage1b_v1_20260806_r5" / "iid_test_once"
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "IID_TEST_EVALUATION.json", payload)
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    (Path(args.output_dir) / "BNN_STAGE1B_IID_COMPARISON.md").write_text(
        _iid_report(args.run_root, freeze, iid_results), encoding="utf-8")
    return payload


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    select = commands.add_parser("select")
    select.add_argument("--run-root", required=True, type=Path)
    select.add_argument("--windows", required=True, type=Path)
    select.add_argument("--output-dir", required=True, type=Path)
    iid = commands.add_parser("iid-test")
    iid.add_argument("--run-root", required=True, type=Path)
    iid.add_argument("--label-root", required=True, type=Path)
    iid.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main():
    args = parse_args()
    if args.command == "select":
        print(json.dumps({"status": "SELECTED", "freeze": cmd_select(args)}, sort_keys=True))
    else:
        print(json.dumps({"status": "PASS", "iid": cmd_iid_test(args)}, sort_keys=True))


if __name__ == "__main__":
    main()
