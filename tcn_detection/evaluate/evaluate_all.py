#!/usr/bin/env python3
"""Freeze validation-selected detector settings and evaluate all Pilot methods."""

from __future__ import print_function

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import torch

from power_macro.tcn_detection.dataset.model_data import apply_normalizer, filter_split, load_window_table, write_json
from power_macro.tcn_detection.evaluate.metrics import choose_confirmation, event_metrics, hard_pair_metrics, window_metrics
from power_macro.tcn_detection.models.conv_autoencoder import ConvAutoencoder
from power_macro.tcn_detection.models.threshold_baseline import calibrate_thresholds, predict_from_thresholds, scores_from_features
from power_macro.tcn_detection.train.common import build_classifier, configure_cpu, make_loader, read_json
from power_macro.tcn_detection.train.train_autoencoder import reconstruction_errors
from power_macro.tcn_detection.train.train_classifier import predict


def read_truth(label_dir):
    """Load complete labelled rows for event truth; model inputs remain windows only."""

    truth = {}
    for path in sorted(Path(label_dir).glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        truth[rows[0]["trace_id"]] = rows
    return truth


def load_corpus(path):
    """Read the authority for family, duty, severity, and hard-pair strata."""

    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["trace_id"]: row for row in rows}


def prediction_rows(table, predictions, probabilities=None):
    """Join frozen predictions with endpoint metadata for metrics and audit CSVs."""

    rows = []
    for index, (metadata, prediction) in enumerate(zip(table.metadata, predictions)):
        row = {"window_id": metadata["window_id"], "trace_id": metadata["trace_id"], "split": metadata["split"],
               "end_index": int(metadata["end_index"]), "target_label": int(metadata["target_label"]), "prediction": int(prediction)}
        if probabilities is not None:
            row.update({"prob_safe": float(probabilities[index, 0]), "prob_warning": float(probabilities[index, 1]),
                        "prob_critical": float(probabilities[index, 2])})
        rows.append(row)
    return rows


def classifier_predictions(checkpoint_path, table, batch_size):
    """Reload an endpoint classifier and apply only its saved train normalizer."""

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model = build_classifier(checkpoint["model"], checkpoint["model_config"])
    model.load_state_dict(checkpoint["state_dict"])
    normalized = apply_normalizer(table, checkpoint["normalizer"])
    _, probabilities = predict(model, normalized.features, batch_size)
    return probabilities.argmax(axis=1), probabilities


def cae_predictions(checkpoint_path, thresholds_path, table, batch_size):
    """Reload normal-only CAE and map its frozen reconstruction thresholds to labels."""

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    model = ConvAutoencoder(input_channels=checkpoint["model_config"]["input_channels"], channels=checkpoint["model_config"]["cae_channels"],
                            kernel_size=checkpoint["model_config"]["kernel_size"])
    model.load_state_dict(checkpoint["state_dict"])
    normalized = apply_normalizer(table, checkpoint["normalizer"])
    errors = reconstruction_errors(model, normalized.features, batch_size)
    thresholds = json.loads(Path(thresholds_path).read_text(encoding="utf-8"))
    return predict_from_thresholds(errors, thresholds["warning"], thresholds["critical"]), errors


def subsets(corpus_by_trace, severity_limit):
    """Return immutable trace-ID subsets used by every detector identically."""

    test = {trace_id for trace_id, row in corpus_by_trace.items() if row["split"] in {"iid_test", "ood_test"}}
    output = {"iid_test": {trace_id for trace_id in test if corpus_by_trace[trace_id]["split"] == "iid_test"},
              "ood_test": {trace_id for trace_id in test if corpus_by_trace[trace_id]["split"] == "ood_test"},
              "ood_waveform": {trace_id for trace_id in test if corpus_by_trace[trace_id]["split"] == "ood_test" and corpus_by_trace[trace_id]["waveform_family_id"] != "background"},
              "unseen_base_waveform_seed_realization": test}
    output["low_severity_amplitude_le_{}mv".format(severity_limit)] = {trace_id for trace_id in test if corpus_by_trace[trace_id].get("event") and corpus_by_trace[trace_id]["event"]["amplitude_mv"] <= severity_limit}
    output["low_duty_1pct_5pct"] = {trace_id for trace_id in test if corpus_by_trace[trace_id].get("event_duty_cycle") in {0.01, 0.05}}
    for mode in ("busy", "bursty", "mixed", "randomizer_like"):
        output["background_{}".format(mode)] = {trace_id for trace_id in test if corpus_by_trace[trace_id]["background_mode"] == mode}
    return output


def metrics_for_rows(rows, probabilities=None):
    """Compute window metrics for a selected trace subset, returning None if empty."""

    if not rows:
        return None
    labels = np.asarray([row["target_label"] for row in rows], dtype=np.int64)
    predictions = np.asarray([row["prediction"] for row in rows], dtype=np.int64)
    return window_metrics(labels, predictions, probabilities)


def write_predictions(path, all_predictions):
    """Write one bounded audit CSV for all detectors and frozen evaluation windows."""

    fields = ["method", "window_id", "trace_id", "split", "end_index", "target_label", "prediction", "prob_safe", "prob_warning", "prob_critical"]
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for method, rows in sorted(all_predictions.items()):
            for row in rows:
                writer.writerow({"method": method, **row})


def main():
    """Evaluate threshold, CAE, CNN, and TCN models without test-time tuning."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows-dir", required=True, type=Path)
    parser.add_argument("--label-dir", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--models-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite evaluation directory: {}".format(args.output_dir))
    config = read_json(args.training_config)
    configure_cpu(config["seed"], config["cpu_threads_per_process"])
    primary = load_window_table(args.windows_dir / "windows_L16.csv")
    validation = filter_split(primary, "validation")
    evaluated_splits = [filter_split(primary, split) for split in ("validation", "iid_test", "ood_test")]
    combined_metadata = tuple(item for table in evaluated_splits for item in table.metadata)
    combined_features = np.concatenate([table.features for table in evaluated_splits])
    combined_labels = np.concatenate([table.labels for table in evaluated_splits])
    from power_macro.tcn_detection.dataset.model_data import WindowTable
    evaluation_table = WindowTable(combined_features, combined_labels, combined_metadata, primary.length)
    truth = read_truth(args.label_dir)
    corpus = load_corpus(args.corpus)
    all_predictions = {}
    # Threshold calibration is deliberately performed before any IID/OOD rows
    # are scored.  Each rule receives exactly the same validation windows.
    for rule in ("sensor_code", "delta_code", "short_history"):
        calibration = calibrate_thresholds(validation.features, validation.labels, rule)
        scores = scores_from_features(evaluation_table.features, rule)
        predictions = predict_from_thresholds(scores, calibration["warning_threshold"], calibration["critical_threshold"])
        all_predictions["threshold_{}".format(rule)] = prediction_rows(evaluation_table, predictions)
        calibration["score_direction"] = "higher_is_riskier"
        calibration["validation_window_count"] = int(len(validation.labels))
        all_predictions["threshold_{}".format(rule) + "__calibration"] = calibration
    cae_dir = args.models_dir / "cae_L16"
    cae_labels, _ = cae_predictions(cae_dir / "best_checkpoint.pt", cae_dir / "thresholds.json", evaluation_table, config["batch_size"])
    all_predictions["cae"] = prediction_rows(evaluation_table, cae_labels)
    for name in ("cnn", "tcn"):
        model_dir = args.models_dir / (name + "_L16")
        predictions, probabilities = classifier_predictions(model_dir / "best_checkpoint.pt", evaluation_table, config["batch_size"])
        all_predictions[name] = prediction_rows(evaluation_table, predictions, probabilities)
    # TCN history-length ablations are evaluated with their own L-specific
    # indexes and reported separately.  They do not alter the L16 comparison.
    ablations = {}
    for length in (8, 32):
        table = load_window_table(args.windows_dir / "windows_L{}.csv".format(length))
        parts = [filter_split(table, split) for split in ("validation", "iid_test", "ood_test")]
        joined = WindowTable(np.concatenate([part.features for part in parts]), np.concatenate([part.labels for part in parts]),
                             tuple(item for part in parts for item in part.metadata), length)
        predictions, probabilities = classifier_predictions(args.models_dir / "tcn_L{}".format(length) / "best_checkpoint.pt", joined, config["batch_size"])
        ablations["tcn_L{}".format(length)] = {"rows": prediction_rows(joined, predictions, probabilities), "length": length}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    method_reports = {}
    strata = subsets(corpus, float(config["low_severity_amplitude_mv_max"]))
    primary_methods = [name for name in all_predictions if not name.endswith("__calibration")]
    for method in primary_methods:
        rows = all_predictions[method]
        validation_rows = [row for row in rows if row["split"] == "validation"]
        confirmation = choose_confirmation(validation_rows, truth, corpus, config["confirmation_candidates"])
        selected_k = confirmation["selected_confirm_count"]
        probabilities = None
        if method in {"cnn", "tcn"}:
            probabilities = np.asarray([[row["prob_safe"], row["prob_warning"], row["prob_critical"]] for row in rows], dtype=np.float64)
        window_reports = {}
        event_reports = {}
        for name, trace_ids in strata.items():
            selected_rows = [row for row in rows if row["trace_id"] in trace_ids]
            selected_probabilities = None
            if probabilities is not None:
                selected_indices = [index for index, row in enumerate(rows) if row["trace_id"] in trace_ids]
                selected_probabilities = probabilities[selected_indices]
            window_reports[name] = metrics_for_rows(selected_rows, selected_probabilities)
            event_reports[name] = event_metrics(selected_rows, truth, corpus, selected_k, trace_ids)
        ood_rows = [row for row in rows if row["split"] == "ood_test"]
        method_reports[method] = {"confirmation": confirmation, "window": window_reports, "events": event_reports,
                                  "hard_pair": hard_pair_metrics(ood_rows, corpus)}
    for name, ablation in ablations.items():
        rows = ablation["rows"]
        method_reports[name] = {"window": {"iid_test": metrics_for_rows([row for row in rows if row["split"] == "iid_test"],
                                                                            np.asarray([[row["prob_safe"], row["prob_warning"], row["prob_critical"]] for row in rows if row["split"] == "iid_test"])),
                                             "ood_test": metrics_for_rows([row for row in rows if row["split"] == "ood_test"],
                                                                            np.asarray([[row["prob_safe"], row["prob_warning"], row["prob_critical"]] for row in rows if row["split"] == "ood_test"]))},
                                "ablation_only": True}
    # Separate calibration objects from predictions before serializing.  This
    # avoids mixed record shapes in the audit CSV and makes validation-only
    # threshold provenance immediately visible in the top-level report.
    calibrations = {name: all_predictions.pop(name) for name in list(all_predictions) if name.endswith("__calibration")}
    write_predictions(args.output_dir / "predictions_L16.csv", all_predictions)
    tcn_ood = method_reports["tcn"]["window"]["ood_test"]
    competitor_ood = max(method_reports["cnn"]["window"]["ood_test"]["macro_f1"],
                         *(method_reports[name]["window"]["ood_test"]["macro_f1"] for name in method_reports if name.startswith("threshold_")))
    pilot_gate = {"threshold_near_perfect": all(method_reports[name]["window"]["iid_test"]["macro_f1"] >= 0.98 and method_reports[name]["window"]["ood_test"]["macro_f1"] >= 0.98 and method_reports[name]["window"]["iid_test"]["per_class"]["2"]["recall"] >= 0.98 and method_reports[name]["window"]["ood_test"]["per_class"]["2"]["recall"] >= 0.98 for name in method_reports if name.startswith("threshold_")),
                  "tcn_ood_macro_f1_advantage_vs_cnn_or_threshold": float(tcn_ood["macro_f1"] - competitor_ood),
                  "tcn_confirmation_positive_lead": method_reports["tcn"]["confirmation"]["positive_lead_available"]}
    report = {"schema_version": 1, "source": {"windows_dir": str(args.windows_dir.resolve()), "label_dir": str(args.label_dir.resolve()),
                                                 "corpus": str(args.corpus.resolve())}, "threshold_calibrations": calibrations,
              "methods": method_reports, "pilot_gate": pilot_gate,
              "background_generalization_limit": "All four background modes appear in train; results report held-out base-waveform/seed realizations, not unseen background categories."}
    write_json(args.output_dir / "evaluation_report.json", report)
    Path(args.output_dir / "evaluation_report.md").write_text("# Frozen Pilot Evaluation V1\n\n"
        "- Methods: {}\n- Threshold calibration: validation only\n- Background limit: all modes were seen in train; no unseen-category claim is made.\n"
        "- TCN OOD macro-F1 advantage versus best CNN/threshold: {:.6f}\n- TCN positive confirmation lead available: {}\n".format(
            ", ".join(sorted(method_reports)), pilot_gate["tcn_ood_macro_f1_advantage_vs_cnn_or_threshold"], pilot_gate["tcn_confirmation_positive_lead"]), encoding="utf-8")


if __name__ == "__main__":
    main()
