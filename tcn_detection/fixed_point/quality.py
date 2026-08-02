"""Predeclared quantization-candidate validation and quality gates."""

from __future__ import print_function

import math


HIGHER_IS_BETTER = (
    "accuracy", "balanced_accuracy", "macro_f1", "critical_pr_auc",
    "critical_recall",
)
LOWER_IS_BETTER = ("safe_window_false_alarm_rate",)


def validate_fixed_point_config(config):
    """Validate every policy field that can affect candidate selection.

    The purpose is not generic JSON-schema replacement.  These exact checks
    bind this release to four required width combinations, train-only range
    calibration, validation-only selection, deterministic rounding, and a
    fixed quality policy.  A missing key must fail rather than acquire a Python
    default after quantization results are visible.
    """

    candidates = config.get("candidates")
    expected = [
        ("w8_a8", 8, 8), ("w16_a8", 16, 8),
        ("w8_a16", 8, 16), ("w16_a16", 16, 16),
    ]
    observed = [(item.get("candidate_id"), item.get("weight_bits"),
                 item.get("activation_bits")) for item in candidates or []]
    if observed != expected or config.get("candidate_priority") != [
            item[0] for item in expected]:
        raise ValueError("fixed-point candidate matrix or priority changed")
    data = config.get("data_policy", {})
    if (data.get("calibration_split") != "train"
            or data.get("selection_split") != "validation"
            or set(data.get("forbidden_splits", [])) != {"iid_test", "ood_test"}
            or data.get("calibration_statistic") != "full_range_max_abs"):
        raise ValueError("fixed-point data policy crossed development boundary")
    policy = config.get("quantization_policy", {})
    required_policy = {
        "scheme": "signed_symmetric",
        "zero_point": 0,
        "weight_granularity": "per_output_channel",
        "activation_granularity": "per_layer",
        "rounding": "round_to_nearest_ties_to_even",
        "saturation": "clamp_to_signed_range_after_each_requantization",
        "average_pool": "sum_32_then_round_to_nearest_ties_to_even_divide_by_32",
        "scale_rounding": "ceil_to_power_of_two",
        "classifier_output_bits": 32,
        "tie_decision": "safe",
    }
    if any(policy.get(key) != value for key, value in required_policy.items()):
        raise ValueError("fixed-point numeric policy is incomplete")

    relative = config.get("relative_degradation_limits", {})
    absolute = config.get("absolute_quality_floors", {})
    required_relative = set(HIGHER_IS_BETTER) | {
        "safe_window_false_alarm_rate_increase"}
    required_absolute = {
        "accuracy_min", "balanced_accuracy_min", "macro_f1_min",
        "critical_pr_auc_min", "critical_recall_min",
        "safe_window_false_alarm_rate_max",
    }
    if set(relative) != required_relative or set(absolute) != required_absolute:
        raise ValueError("quality gate keys differ from frozen contract")
    values = list(relative.values()) + list(absolute.values())
    if any(not math.isfinite(float(value)) or float(value) < 0.0
           for value in values):
        raise ValueError("quality gates must be finite and non-negative")
    return config


def evaluate_quality_gates(float_metrics, quantized_metrics, config):
    """Apply relative degradation limits and absolute floors to one candidate."""

    validate_fixed_point_config(config)
    relative = config["relative_degradation_limits"]
    absolute = config["absolute_quality_floors"]
    checks = {}
    for metric in HIGHER_IS_BETTER:
        float_value = float(float_metrics[metric])
        quantized_value = float(quantized_metrics[metric])
        # A negative degradation means quantization improved the observed
        # validation metric.  It passes naturally and is retained in the report
        # rather than clipped to zero, preserving the complete comparison.
        degradation = float_value - quantized_value
        checks["relative_{}".format(metric)] = {
            "passed": degradation <= float(relative[metric]) + 1.0e-15,
            "float": float_value,
            "quantized": quantized_value,
            "degradation": degradation,
            "limit": float(relative[metric]),
        }
        floor_key = "{}_min".format(metric)
        checks["absolute_{}".format(metric)] = {
            "passed": quantized_value >= float(absolute[floor_key]),
            "quantized": quantized_value,
            "minimum": float(absolute[floor_key]),
        }

    far_metric = LOWER_IS_BETTER[0]
    increase = (float(quantized_metrics[far_metric])
                - float(float_metrics[far_metric]))
    checks["relative_{}".format(far_metric)] = {
        "passed": increase <= float(
            relative["safe_window_false_alarm_rate_increase"]) + 1.0e-15,
        "float": float(float_metrics[far_metric]),
        "quantized": float(quantized_metrics[far_metric]),
        "increase": increase,
        "limit": float(relative["safe_window_false_alarm_rate_increase"]),
    }
    checks["absolute_{}".format(far_metric)] = {
        "passed": float(quantized_metrics[far_metric]) <= float(
            absolute["safe_window_false_alarm_rate_max"]),
        "quantized": float(quantized_metrics[far_metric]),
        "maximum": float(absolute["safe_window_false_alarm_rate_max"]),
    }
    return {"passed": all(item["passed"] for item in checks.values()),
            "checks": checks}


def choose_candidate(candidate_reports, config):
    """Choose the first passing candidate in the frozen hardware-cost order."""

    validate_fixed_point_config(config)
    by_name = {item["candidate_id"]: item for item in candidate_reports}
    expected = set(config["candidate_priority"])
    if set(by_name) != expected:
        raise ValueError("quantization report does not contain every candidate")
    for candidate_id in config["candidate_priority"]:
        if by_name[candidate_id].get("quality_gates", {}).get("passed") is True:
            return candidate_id
    return None
