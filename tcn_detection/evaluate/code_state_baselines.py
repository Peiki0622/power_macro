#!/usr/bin/env python3
"""Fit train-only code baselines and report validation-only state metrics."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score

from power_macro.tcn_detection.evaluate.metrics import window_metrics
from power_macro.tcn_detection.evaluate.state_metrics import state_event_metrics


def sha256_file(path):
    """Hash every consumed immutable index for the baseline provenance."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_development_windows(path):
    """Read train/validation rows while rejecting any test-split exposure.

    The source CSV physically contains all splits.  This streaming reader
    checks the split name before parsing ``features_json`` and retains only
    train and validation arrays.  Therefore neither IID nor OOD feature values
    are materialized in the baseline fitting/evaluation process.
    """

    selected = {"train": [], "validation": []}
    with Path(path).open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            split = row["split"]
            if split not in selected:
                continue
            features = np.asarray(json.loads(row["features_json"]), dtype=np.float64)
            if features.shape != (int(row["length"]), 1):
                raise ValueError("baseline input must have shape [L,1]")
            selected[split].append({
                "window_id": row["window_id"], "trace_id": row["trace_id"],
                "split": split, "end_index": int(row["end_index"]),
                "target_label": int(row["target_label"]),
                "features": features[:, 0],
            })
    if not selected["train"] or not selected["validation"]:
        raise ValueError("both train and validation windows are required")
    return selected


def fit_code_thresholds(train_rows):
    """Exhaustively fit integer endpoint-code cutoffs on train Macro-F1.

    Normalized code is monotonic with integer code, so the 19 boundary values
    from 15 through 33 cover every distinct ordinal decision rule.  The tie
    break favors lower thresholds, yielding deterministic results.
    """

    labels = np.asarray([row["target_label"] for row in train_rows])
    endpoint_codes = np.rint(np.asarray([row["features"][-1] for row in train_rows]) * 17 + 15).astype(int)
    best = None
    for warning in range(15, 34):
        for critical in range(warning, 34):
            prediction = np.zeros(len(labels), dtype=np.int64)
            prediction[endpoint_codes >= warning] = 1
            prediction[endpoint_codes >= critical] = 2
            score = f1_score(labels, prediction, labels=[0, 1, 2],
                             average="macro", zero_division=0)
            key = (float(score), -warning, -critical)
            if best is None or key > best[0]:
                best = (key, warning, critical)
    return {"warning_code": best[1], "critical_code": best[2],
            "train_macro_f1": best[0][0]}


def threshold_predictions(rows, thresholds):
    """Apply frozen integer thresholds to endpoint code values."""

    code = np.rint(np.asarray([row["features"][-1] for row in rows]) * 17 + 15).astype(int)
    prediction = np.zeros(len(rows), dtype=np.int64)
    prediction[code >= thresholds["warning_code"]] = 1
    prediction[code >= thresholds["critical_code"]] = 2
    return prediction


def downgrade_hysteresis(rows, raw_predictions, recover_samples=3):
    """Suppress isolated severity recovery using a causal per-trace state.

    Risk upgrades remain immediate for safety.  A lower raw state must persist
    for three consecutive endpoints before the deployed state drops by one
    level.  State and counters reset at every trace boundary.
    """

    output = np.empty(len(rows), dtype=np.int64)
    state = 0
    lower_streak = 0
    previous_trace = None
    for index, (row, raw) in enumerate(zip(rows, raw_predictions)):
        if row["trace_id"] != previous_trace:
            state = int(raw)
            lower_streak = 0
            previous_trace = row["trace_id"]
        elif int(raw) > state:
            state = int(raw)
            lower_streak = 0
        elif int(raw) < state:
            lower_streak += 1
            if lower_streak >= int(recover_samples):
                state -= 1
                lower_streak = 0
        else:
            lower_streak = 0
        output[index] = state
    return output


def fit_ordinal_logistic(train_rows, seed):
    """Fit two shallow L2 logistic heads on flattened code histories.

    The heads learn ``P(state>=Warning)`` and ``P(state=Critical)``.  Balanced
    class weights keep rare state gradients visible without resampling or
    duplicating windows.  The model is deliberately linear, making it a useful
    lower-capacity reference for the later nonlinear TCN.
    """

    features = np.stack([row["features"] for row in train_rows])
    labels = np.asarray([row["target_label"] for row in train_rows])
    risk = LogisticRegression(max_iter=1000, class_weight="balanced",
                              random_state=int(seed), solver="lbfgs")
    critical = LogisticRegression(max_iter=1000, class_weight="balanced",
                                  random_state=int(seed), solver="lbfgs")
    risk.fit(features, labels >= 1)
    critical.fit(features, labels == 2)
    return risk, critical


def ordinal_probabilities(models, rows):
    """Convert two binary head probabilities into a valid three-class simplex."""

    features = np.stack([row["features"] for row in rows])
    risk = models[0].predict_proba(features)[:, 1]
    critical = np.minimum(models[1].predict_proba(features)[:, 1], risk)
    probabilities = np.stack([1.0 - risk, risk - critical, critical], axis=1)
    probabilities = np.clip(probabilities, 1.0e-9, 1.0)
    return probabilities / probabilities.sum(axis=1, keepdims=True)


def score(name, rows, predictions, probabilities):
    """Return comprehensive window and chronological metrics for one baseline."""

    labels = np.asarray([row["target_label"] for row in rows], dtype=np.int64)
    event_rows = [{**row, "prediction": int(prediction)}
                  for row, prediction in zip(rows, predictions)]
    return {"name": name, "window": window_metrics(labels, predictions, probabilities),
            "events": state_event_metrics(event_rows)}


def main():
    """Write one immutable baseline report without reading frozen test data."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=20260725)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("refusing to overwrite baseline report: {}".format(args.output))
    tables = read_development_windows(args.windows)
    train, validation = tables["train"], tables["validation"]
    labels = np.asarray([row["target_label"] for row in validation], dtype=np.int64)

    majority = np.zeros(len(validation), dtype=np.int64)
    majority_probabilities = np.zeros((len(validation), 3), dtype=np.float64)
    majority_probabilities[:, 0] = 1.0
    thresholds = fit_code_thresholds(train)
    raw_threshold = threshold_predictions(validation, thresholds)
    raw_probabilities = np.eye(3)[raw_threshold]
    hysteretic = downgrade_hysteresis(validation, raw_threshold, recover_samples=3)
    hysteretic_probabilities = np.eye(3)[hysteretic]
    logistic_models = fit_ordinal_logistic(train, args.seed)
    logistic_probabilities = ordinal_probabilities(logistic_models, validation)
    logistic_prediction = np.argmax(logistic_probabilities, axis=1)

    report = {
        "schema_version": 1,
        "scope": "validation_only",
        "iid_ood_rows_materialized": False,
        "seed": args.seed,
        "windows": str(args.windows.resolve()),
        "windows_sha256": sha256_file(args.windows),
        "train_window_count": len(train),
        "validation_window_count": len(validation),
        "thresholds_fitted_on": "train",
        "thresholds": thresholds,
        "baselines": {
            "majority_safe": score("majority_safe", validation, majority,
                                   majority_probabilities),
            "current_code_threshold": score("current_code_threshold", validation,
                                            raw_threshold, raw_probabilities),
            "threshold_causal_hysteresis": score(
                "threshold_causal_hysteresis", validation, hysteretic,
                hysteretic_probabilities),
            "ordinal_logistic_L32": score("ordinal_logistic_L32", validation,
                                          logistic_prediction, logistic_probabilities),
        },
        "validation_label_count": {str(label): int(np.sum(labels == label))
                                   for label in range(3)},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
