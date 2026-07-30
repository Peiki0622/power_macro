#!/usr/bin/env python3
"""Causal filtering and hysteresis for binary Critical probabilities."""

from __future__ import print_function

from collections import defaultdict

from power_macro.tcn_detection.evaluate.postprocess import causal_filter


def filter_rows(rows, filter_config):
    """Attach one causal filtered Critical score to every chronological row."""

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["trace_id"]].append(row)
    output = []
    for trace_id in sorted(grouped):
        ordered = sorted(grouped[trace_id], key=lambda row: int(row["end_index"]))
        raw = [float(row["prob_critical"]) for row in ordered]
        filtered = causal_filter(raw, filter_config["kind"],
                                 filter_config.get("window", 1),
                                 filter_config.get("alpha", 1.0))
        for row, score in zip(ordered, filtered):
            output.append({**row, "filtered_critical_score": float(score)})
    return output


def detect_filtered_rows(rows, config):
    """Apply a two-state hysteretic detector with state reset per trace.

    Safe-to-Critical activation requires ``k_on`` consecutive scores at or
    above ``critical_on``.  Critical-to-Safe recovery requires ``k_off``
    consecutive scores at or below the lower ``critical_off`` threshold.  No
    Warning state or Risk probability exists in this binary contract.
    """

    on = float(config["critical_on"])
    off = float(config["critical_off"])
    k_on, k_off = int(config["k_on"]), int(config["k_off"])
    if not 0.0 <= off < on <= 1.0 or k_on < 1 or k_off < 1:
        raise ValueError("binary hysteresis requires 0<=off<on<=1 and positive K")
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["trace_id"]].append(row)
    output = []
    for trace_id in sorted(grouped):
        state = 0
        activation_streak = recovery_streak = 0
        ordered = sorted(grouped[trace_id], key=lambda row: int(row["end_index"]))
        for row in ordered:
            score = float(row["filtered_critical_score"])
            if state == 0:
                activation_streak = activation_streak + 1 if score >= on else 0
                if activation_streak >= k_on:
                    state = 1
                    activation_streak = recovery_streak = 0
            else:
                recovery_streak = recovery_streak + 1 if score <= off else 0
                if recovery_streak >= k_off:
                    state = 0
                    activation_streak = recovery_streak = 0
            output.append({**row, "raw_prediction": int(row["prediction"]),
                           "prediction": int(state)})
    return output


def apply_detector(rows, config):
    """Filter and detect complete traces using one frozen binary config."""

    return detect_filtered_rows(filter_rows(rows, config["filter"]), config)
