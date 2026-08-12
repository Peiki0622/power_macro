#!/usr/bin/env python3
"""Analyze completed FTC start/end evidence without rerunning electrical simulation.

The FTC front-end is intentionally outside this tool's scope.  This script
only consumes the compact CSVs produced by the completed HSPICE runs, derives
the documented C/W coordinates, and answers whether a single captured FTC
word has a voltage direction that is separable from sampling-phase movement.
It never imports deck-generation or simulation code, never edits the selected
operating point, and never interpolates a missing physical measurement.
"""

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    import matplotlib

    # The analysis runs in batch environments as well as developer shells.
    # Selecting Agg before pyplot import avoids requiring an X/Wayland display
    # while retaining deterministic SVG output for report review.
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError as error:  # pragma: no cover - exercised only without dependencies.
    raise SystemExit(
        "FTC 2-D analysis requires NumPy and Matplotlib. Install them with "
        "`python -m pip install numpy matplotlib`: {}".format(error)
    )


FTC_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATIC_INPUT = FTC_ROOT / "runs/static_fine/static_transfer.csv"
DEFAULT_PHASE_INPUT = FTC_ROOT / "runs/phase_sensitivity/phase_sensitivity.csv"
DEFAULT_OUTPUT_DIR = FTC_ROOT / "analysis/phase_voltage_2d"
DEFAULT_REPORT_OUTPUT = FTC_ROOT / "reports/FTC_PHASE_VOLTAGE_2D_SEPARABILITY.md"

ANCHORS = (1.10, 0.90, 0.80)
STATIC_EXPECTED_VDDS = tuple(round(1.10 - 0.01 * index, 2) for index in range(31))
FIT_WINDOWS = {
    1.10: (1.05, 1.10),  # High endpoint: one-sided 50 mV window.
    0.90: (0.87, 0.93),  # Interior anchor: centered 60 mV window.
    0.80: (0.80, 0.85),  # Low endpoint: one-sided 50 mV window.
}
AMBIGUITY_WINDOWS = {
    1.10: (1.10, 1.08),  # 20 mV one-sided interval at the high endpoint.
    0.90: (0.91, 0.89),  # 20 mV symmetric interval about the interior anchor.
    0.80: (0.82, 0.80),  # 20 mV one-sided interval at the low endpoint.
}
NEAR_COLLINEAR_DEGREES = 30.0
FLOAT_TOLERANCE = 1.0e-9


def vdd_key(value: float) -> float:
    """Normalize decimal VDD labels so CSV binary-float noise cannot split a bin."""

    return round(float(value), 9)


def format_number(value: Optional[float]) -> str:
    """Serialize numeric report/CSV values compactly without hiding precision."""

    return "" if value is None else "{:.12g}".format(float(value))


def json_ready(value: Any) -> Any:
    """Recursively convert NumPy scalars/arrays into stable JSON-native values."""

    if isinstance(value, np.ndarray):
        return [json_ready(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


def read_csv_rows(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    """Read one compact evidence CSV while rejecting absent headers or empty data.

    The raw CSV is retained as the physical source of truth.  Rows remain
    string-keyed until validation has established that the analysis-critical
    fields are present and numerically well formed.
    """

    if not path.is_file():
        raise ValueError("required completed FTC evidence is unavailable: {}".format(path))
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError("CSV has no header: {}".format(path))
        rows = list(reader)
        fields = list(reader.fieldnames)
    if not rows:
        raise ValueError("CSV has no physical samples: {}".format(path))
    return rows, fields


def required_float(row: Mapping[str, str], field: str, source: Path, row_number: int) -> float:
    """Return a required finite float with a source-row-specific error message."""

    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("{} row {} has invalid {}".format(source, row_number, field)) from error
    if not math.isfinite(value):
        raise ValueError("{} row {} has non-finite {}".format(source, row_number, field))
    return value


def required_int(row: Mapping[str, str], field: str, source: Path, row_number: int) -> int:
    """Return an integer-valued CSV field without silently rounding evidence."""

    value = required_float(row, field, source, row_number)
    if not value.is_integer():
        raise ValueError("{} row {} has non-integer {}".format(source, row_number, field))
    return int(value)


def validate_record(row: Mapping[str, str], source: Path, row_number: int, require_phase: bool) -> Dict[str, float]:
    """Validate the common FTC encoded-output contract for one physical sample."""

    required = ("vdd_v", "start_index", "end_index", "valid")
    missing = [field for field in required if field not in row]
    if require_phase and "phase_offset_s" not in row:
        missing.append("phase_offset_s")
    if missing:
        raise ValueError("{} is missing required columns: {}".format(source, ", ".join(missing)))
    vdd = required_float(row, "vdd_v", source, row_number)
    start = required_int(row, "start_index", source, row_number)
    end = required_int(row, "end_index", source, row_number)
    valid = required_int(row, "valid", source, row_number)
    if valid not in (0, 1):
        raise ValueError("{} row {} valid must be 0 or 1".format(source, row_number))
    if not 0 <= start <= 29 or not 0 <= end <= 29:
        raise ValueError("{} row {} start/end must lie in 0..29".format(source, row_number))
    if valid and end < start:
        raise ValueError("{} row {} has end before start for a valid capture".format(source, row_number))
    result = {"vdd": vdd, "start": float(start), "end": float(end), "valid": float(valid)}
    if require_phase:
        result["phase_offset_s"] = required_float(row, "phase_offset_s", source, row_number)
    return result


def validate_inputs(
    static_rows: Sequence[Mapping[str, str]],
    phase_rows: Sequence[Mapping[str, str]],
    static_path: Path,
    phase_path: Path,
) -> Dict[str, Any]:
    """Enforce the completed experiment's exact coverage before analysis begins.

    Exact 10 mV static coverage and exact three-point phase coverage prevent a
    visually plausible but physically incomplete result from being filled by
    interpolation, extrapolation, or accidental mixing of a different run.
    """

    validated_static = [validate_record(row, static_path, index + 2, False) for index, row in enumerate(static_rows)]
    if len(validated_static) != len(STATIC_EXPECTED_VDDS):
        raise ValueError("static transfer must contain 31 points, found {}".format(len(validated_static)))
    actual_vdds = tuple(vdd_key(item["vdd"]) for item in validated_static)
    if actual_vdds != STATIC_EXPECTED_VDDS:
        raise ValueError("static transfer must run from 1.10 V to 0.80 V in descending 10 mV steps")
    if any(not int(item["valid"]) for item in validated_static):
        raise ValueError("all static points used by this analysis must have valid=1")

    validated_phase = [validate_record(row, phase_path, index + 2, True) for index, row in enumerate(phase_rows)]
    phase_groups: Dict[float, List[Dict[str, float]]] = {}
    for item in validated_phase:
        phase_groups.setdefault(vdd_key(item["vdd"]), []).append(item)
    if set(phase_groups) != set(ANCHORS):
        raise ValueError("phase sensitivity must contain exactly the 1.10, 0.90, and 0.80 V anchors")
    for anchor in ANCHORS:
        group = phase_groups[anchor]
        if len(group) != 3:
            raise ValueError("phase anchor {:.2f} V must contain exactly three samples".format(anchor))
        if any(not int(item["valid"]) for item in group):
            raise ValueError("phase anchor {:.2f} V contains an invalid capture".format(anchor))
        offsets = [item["phase_offset_s"] for item in group]
        if not any(offset < 0.0 for offset in offsets) or not any(offset > 0.0 for offset in offsets):
            raise ValueError("phase anchor {:.2f} V lacks negative or positive phase evidence".format(anchor))
        if sum(math.isclose(offset, 0.0, abs_tol=1.0e-18) for offset in offsets) != 1:
            raise ValueError("phase anchor {:.2f} V must contain one nominal zero-offset sample".format(anchor))
    return {"static": validated_static, "phase": validated_phase}


def add_cw(rows: Sequence[Mapping[str, str]]) -> List[Dict[str, Any]]:
    """Retain all original evidence fields and append the analysis-only C/W fields."""

    result: List[Dict[str, Any]] = []
    for row in rows:
        enriched: Dict[str, Any] = dict(row)
        start = int(row["start_index"])
        end = int(row["end_index"])
        enriched["c"] = start + end
        enriched["w"] = end - start + 1
        result.append(enriched)
    return result


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    """Write deterministic CSV output without allowing rows to invent new columns."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            encoded = {}
            for field in fields:
                value = row.get(field, "")
                encoded[field] = format_number(value) if isinstance(value, (float, np.floating)) else value
            writer.writerow(encoded)


def write_json(path: Path, value: Any) -> None:
    """Write a reviewable, stable JSON artifact containing only builtin values."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    """Hash the exact local evidence used so later local replay can detect drift."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_static(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Return valid static C/W rows in descending VDD (increasing-droop) order."""

    result = [
        {"vdd": float(row["vdd_v"]), "start": int(row["start_index"]), "end": int(row["end_index"]), "c": int(row["c"]), "w": int(row["w"])}
        for row in rows
        if int(row["valid"]) == 1
    ]
    return sorted(result, key=lambda row: row["vdd"], reverse=True)


def canonical_phase(rows: Sequence[Mapping[str, Any]]) -> Dict[float, List[Dict[str, Any]]]:
    """Group valid phase C/W samples by anchor and sort each triplet by offset."""

    groups: Dict[float, List[Dict[str, Any]]] = {anchor: [] for anchor in ANCHORS}
    for row in rows:
        if int(row["valid"]) != 1:
            continue
        groups[vdd_key(float(row["vdd_v"]))].append(
            {
                "vdd": float(row["vdd_v"]),
                "phase_offset_s": float(row["phase_offset_s"]),
                "start": int(row["start_index"]),
                "end": int(row["end_index"]),
                "c": int(row["c"]),
                "w": int(row["w"]),
            }
        )
    return {anchor: sorted(groups[anchor], key=lambda row: row["phase_offset_s"]) for anchor in ANCHORS}


def plateau_summary(vdds: Sequence[float], states: Sequence[Any]) -> Dict[str, Any]:
    """Describe maximal adjacent plateaus without smoothing discrete FTC codes."""

    if len(vdds) != len(states) or not vdds:
        raise ValueError("plateau summary requires nonempty, equally sized VDD/state sequences")
    plateaus = []
    begin = 0
    for index in range(1, len(states) + 1):
        if index == len(states) or states[index] != states[begin]:
            high = float(vdds[begin])
            low = float(vdds[index - 1])
            state = states[begin]
            plateaus.append(
                {
                    "state": list(state) if isinstance(state, tuple) else state,
                    "vdd_high_v": high,
                    "vdd_low_v": low,
                    "width_v": abs(high - low),
                    "point_count": index - begin,
                }
            )
            begin = index
    maximum = max(plateaus, key=lambda item: (float(item["width_v"]), int(item["point_count"])))
    return {"plateaus": plateaus, "maximum": maximum}


def static_representation_summary(static: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Count representational states and plateaus before a projection discards information."""

    vdds = [float(row["vdd"]) for row in static]
    representations = {
        "start_end": [(int(row["start"]), int(row["end"])) for row in static],
        "c": [int(row["c"]) for row in static],
        "w": [int(row["w"]) for row in static],
        "c_w": [(int(row["c"]), int(row["w"])) for row in static],
    }
    return {
        name: {"unique_states": len(set(states)), "plateau": plateau_summary(vdds, states)}
        for name, states in representations.items()
    }


def local_fit(static: Sequence[Mapping[str, Any]], anchor: float) -> Dict[str, Any]:
    """Fit C(VDD) and W(VDD) in the prescribed 40--60 mV local neighborhood.

    The returned vector is the negative fitted VDD slope.  Its sign therefore
    always points toward increasing droop, even though endpoint neighborhoods
    use opposite raw VDD directions from the centered one.
    """

    lower, upper = FIT_WINDOWS[anchor]
    samples = [row for row in static if lower - FLOAT_TOLERANCE <= float(row["vdd"]) <= upper + FLOAT_TOLERANCE]
    expected_count = 7 if anchor == 0.90 else 6
    if len(samples) != expected_count:
        raise ValueError("local VDD fit at {:.2f} V has {} samples, expected {}".format(anchor, len(samples), expected_count))
    samples = sorted(samples, key=lambda row: float(row["vdd"]), reverse=True)
    x = np.asarray([float(row["vdd"]) for row in samples], dtype=float)
    design = np.column_stack((np.ones_like(x), x))

    def fit_field(field: str) -> Tuple[float, Optional[float]]:
        y = np.asarray([float(row[field]) for row in samples], dtype=float)
        coefficients, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
        predicted = design @ coefficients
        residual = float(np.sum((y - predicted) ** 2))
        total = float(np.sum((y - np.mean(y)) ** 2))
        r_squared = None if math.isclose(total, 0.0, abs_tol=FLOAT_TOLERANCE) else 1.0 - residual / total
        return float(coefficients[1]), r_squared

    slope_c, r2_c = fit_field("c")
    slope_w, r2_w = fit_field("w")
    high, low = samples[0], samples[-1]
    vector = np.asarray([-slope_c, -slope_w], dtype=float)
    endpoint = np.asarray([float(low["c"]) - float(high["c"]), float(low["w"]) - float(high["w"])], dtype=float)
    cosine = cosine_metrics(vector, endpoint)["cosine_similarity"]
    return {
        "anchor_vdd": anchor,
        "samples_used": [float(row["vdd"]) for row in samples],
        "vV_C": float(vector[0]),
        "vV_W": float(vector[1]),
        "r2_C": r2_c,
        "r2_W": r2_w,
        "endpoint_dC": float(endpoint[0]),
        "endpoint_dW": float(endpoint[1]),
        "fit_endpoint_cosine": cosine,
        # Opposite fitted/endpoint direction is the only unambiguous
        # disagreement signal for this deliberately small quantized dataset.
        "quantized_direction_disagreement": cosine is not None and cosine < 0.0,
    }


def phase_vector(anchor: float, rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Extract the measured minus/nominal/plus phase displacement at one VDD anchor."""

    negative = next(row for row in rows if float(row["phase_offset_s"]) < 0.0)
    nominal = next(row for row in rows if math.isclose(float(row["phase_offset_s"]), 0.0, abs_tol=1.0e-18))
    positive = next(row for row in rows if float(row["phase_offset_s"]) > 0.0)
    vector = np.asarray([float(positive["c"]) - float(negative["c"]), float(positive["w"]) - float(negative["w"])])
    return {
        "anchor_vdd": anchor,
        "phase_delta_s": max(abs(float(negative["phase_offset_s"])), abs(float(positive["phase_offset_s"]))),
        "C_minus": int(negative["c"]),
        "W_minus": int(negative["w"]),
        "C_nominal": int(nominal["c"]),
        "W_nominal": int(nominal["w"]),
        "C_plus": int(positive["c"]),
        "W_plus": int(positive["w"]),
        "vPhi_C": float(vector[0]),
        "vPhi_W": float(vector[1]),
        "phase_span_C": max(int(row["c"]) for row in rows) - min(int(row["c"]) for row in rows),
        "phase_span_W": max(int(row["w"]) for row in rows) - min(int(row["w"]) for row in rows),
        "phase_insensitive": bool(np.allclose(vector, 0.0)),
    }


def cosine_metrics(left: Sequence[float], right: Sequence[float]) -> Dict[str, Optional[float]]:
    """Return signed cosine and acute angle, preserving undefined zero-vector cases."""

    left_array = np.asarray(left, dtype=float)
    right_array = np.asarray(right, dtype=float)
    denominator = float(np.linalg.norm(left_array) * np.linalg.norm(right_array))
    if math.isclose(denominator, 0.0, abs_tol=FLOAT_TOLERANCE):
        return {"cosine_similarity": None, "absolute_cosine_similarity": None, "acute_angle_deg": None}
    cosine = float(np.clip(np.dot(left_array, right_array) / denominator, -1.0, 1.0))
    absolute = abs(cosine)
    # Normalized integer vectors can land one machine epsilon below one after
    # division.  Preserve the exact geometric result instead of reporting a
    # misleading micro-degree "separation" for a mathematically collinear pair.
    if math.isclose(absolute, 1.0, abs_tol=1.0e-12):
        absolute = 1.0
        cosine = math.copysign(1.0, cosine)
    return {
        "cosine_similarity": cosine,
        "absolute_cosine_similarity": absolute,
        "acute_angle_deg": float(math.degrees(math.acos(absolute))),
    }


def pooled_phase_direction(phase_vectors: Sequence[Mapping[str, Any]]) -> Tuple[Optional[List[float]], List[Dict[str, Any]]]:
    """Use the first right singular vector as the documented global phase approximation."""

    nonzero = [
        np.asarray([float(row["vPhi_C"]), float(row["vPhi_W"])], dtype=float)
        for row in phase_vectors
        if not bool(row["phase_insensitive"])
    ]
    if not nonzero:
        return None, []
    _, _, vh = np.linalg.svd(np.asarray(nonzero), full_matrices=False)
    direction = np.asarray(vh[0], dtype=float)
    # SVD is sign-ambiguous.  A deterministic positive-first-component rule
    # avoids output churn while preserving the one-dimensional nuisance axis.
    first_nonzero = next(value for value in direction if not math.isclose(float(value), 0.0, abs_tol=FLOAT_TOLERANCE))
    if first_nonzero < 0.0:
        direction = -direction
    variation = []
    for row in phase_vectors:
        vector = np.asarray([float(row["vPhi_C"]), float(row["vPhi_W"])] , dtype=float)
        metrics = cosine_metrics(vector, direction)
        variation.append({"anchor_vdd": row["anchor_vdd"], "angle_to_pooled_deg": metrics["acute_angle_deg"]})
    return [float(direction[0]), float(direction[1])], variation


def normalize_weight(a: int, b: int) -> Tuple[int, int]:
    """Collapse integer sign/scaling duplicates before hardware-cost ranking."""

    if a == 0 and b == 0:
        raise ValueError("the zero projection weight is not a candidate")
    divisor = math.gcd(abs(a), abs(b))
    normalized = (a // divisor, b // divisor)
    if normalized[0] < 0 or (normalized[0] == 0 and normalized[1] < 0):
        normalized = (-normalized[0], -normalized[1])
    return normalized


def score_values(rows: Sequence[Mapping[str, Any]], weight: Sequence[float], baseline: Mapping[str, Any]) -> List[float]:
    """Evaluate one baseline-relative linear score without changing physical codes."""

    return [
        float(weight[0]) * (float(row["c"]) - float(baseline["c"]))
        + float(weight[1]) * (float(row["w"]) - float(baseline["w"]))
        for row in rows
    ]


def score_summary(static: Sequence[Mapping[str, Any]], values: Sequence[float]) -> Dict[str, Any]:
    """Measure static observability, monotonicity, and plateaus for one score."""

    if len(static) != len(values):
        raise ValueError("score/static lengths differ")
    rounded = [round(float(value), 12) for value in values]
    return {
        "minimum": float(min(values)),
        "maximum": float(max(values)),
        "full_range": float(max(values) - min(values)),
        "distinct_states": len(set(rounded)),
        "monotonic_with_droop": all(later + FLOAT_TOLERANCE >= earlier for earlier, later in zip(values, values[1:])),
        "plateau": plateau_summary([float(row["vdd"]) for row in static], rounded),
    }


def phase_score_spans(phase_groups: Mapping[float, Sequence[Mapping[str, Any]]], weight: Sequence[float], baseline: Mapping[str, Any]) -> Dict[str, float]:
    """Return full measured phase spans in score units at the three anchors."""

    spans = {}
    for anchor, rows in phase_groups.items():
        values = score_values(rows, weight, baseline)
        spans["{:.2f}".format(anchor)] = float(max(values) - min(values))
    return spans


def raw_comparison(static: Sequence[Mapping[str, Any]], phase_groups: Mapping[float, Sequence[Mapping[str, Any]]], baseline: Mapping[str, Any]) -> Dict[str, Any]:
    """Establish raw start/end/C/W baselines so a projection cannot win by renaming a code."""

    comparison = {}
    for name in ("start", "end", "c", "w"):
        static_values = [float(row[name]) for row in static]
        phase_spans = {
            "{:.2f}".format(anchor): float(max(float(row[name]) for row in rows) - min(float(row[name]) for row in rows))
            for anchor, rows in phase_groups.items()
        }
        comparison[name] = {"static": score_summary(static, static_values), "phase_spans": phase_spans}
    return comparison


def evaluate_projection(
    static: Sequence[Mapping[str, Any]],
    phase_groups: Mapping[float, Sequence[Mapping[str, Any]],],
    metrics: Sequence[Mapping[str, Any]],
    pooled_direction: Optional[Sequence[float]],
) -> Dict[str, Any]:
    """Screen float and small integer phase-rejection scores only when justified.

    The 30-degree gate is intentionally simple and explicit: a global scalar
    projection is not a meaningful experiment when most measured movement is
    already nearly collinear.  It avoids spending effort tuning coefficients
    for a mechanism that the physical data does not support.
    """

    angles = [float(row["acute_angle_deg"]) for row in metrics if row["acute_angle_deg"] is not None]
    comparison = raw_comparison(static, phase_groups, static[0])
    result: Dict[str, Any] = {"raw_comparison": comparison, "candidates": []}
    if len(angles) < 2:
        result.update({"status": "skipped_insufficient_nonzero_vectors", "reason": "fewer than two nonzero voltage/phase vector pairs"})
        return result
    if float(np.median(np.asarray(angles))) < NEAR_COLLINEAR_DEGREES:
        result.update(
            {
                "status": "skipped_near_collinear",
                "reason": "median acute separation {:.3f} deg is below the {:.1f} deg screening gate".format(float(np.median(np.asarray(angles))), NEAR_COLLINEAR_DEGREES),
            }
        )
        return result
    if pooled_direction is None:
        result.update({"status": "skipped_no_pooled_phase_direction", "reason": "no nonzero phase direction is available"})
        return result

    baseline = static[0]  # Nominal selected 1.10 V state, as required by the task.
    floating_weight = np.asarray([float(pooled_direction[1]), -float(pooled_direction[0])], dtype=float)
    # Scores are reported with larger values for increasing droop.  Flipping a
    # perpendicular vector changes only score polarity, not phase rejection.
    floating_values = score_values(static, floating_weight, baseline)
    if floating_values[-1] < floating_values[0]:
        floating_weight = -floating_weight
        floating_values = score_values(static, floating_weight, baseline)
    floating = score_summary(static, floating_values)
    floating["weight"] = [float(floating_weight[0]), float(floating_weight[1])]
    floating["phase_spans"] = phase_score_spans(phase_groups, floating_weight, baseline)
    result["floating"] = floating
    if not floating["monotonic_with_droop"] or floating["distinct_states"] < 2 or floating["full_range"] <= 0.0:
        result.update({"status": "skipped_float_unusable", "reason": "floating projection does not retain a monotonic, nonconstant static response"})
        return result

    canonical_weights = sorted(
        {
            normalize_weight(a, b)
            for a in (-4, -2, -1, 0, 1, 2, 4)
            for b in (-4, -2, -1, 0, 1, 2, 4)
            if (a, b) != (0, 0)
        }
    )
    candidates = []
    for canonical in canonical_weights:
        oriented = canonical
        values = score_values(static, oriented, baseline)
        if values[-1] < values[0]:
            oriented = (-oriented[0], -oriented[1])
            values = score_values(static, oriented, baseline)
        summary = score_summary(static, values)
        spans = phase_score_spans(phase_groups, oriented, baseline)
        full_range = float(summary["full_range"])
        maximum_phase_span = max(spans.values())
        candidates.append(
            {
                "canonical_a": canonical[0],
                "canonical_b": canonical[1],
                "a": oriented[0],
                "b": oriented[1],
                "static_min": summary["minimum"],
                "static_max": summary["maximum"],
                "static_range": full_range,
                "distinct_static_states": summary["distinct_states"],
                "monotonic_with_droop": summary["monotonic_with_droop"],
                "maximum_plateau_v": summary["plateau"]["maximum"]["width_v"],
                "phase_span_1p10": spans["1.10"],
                "phase_span_0p90": spans["0.90"],
                "phase_span_0p80": spans["0.80"],
                "maximum_normalized_phase_span": None if math.isclose(full_range, 0.0, abs_tol=FLOAT_TOLERANCE) else maximum_phase_span / full_range,
                "arithmetic_cost": abs(oriented[0]) + abs(oriented[1]),
            }
        )
    candidates.sort(
        key=lambda item: (
            not bool(item["monotonic_with_droop"]),
            float("inf") if item["maximum_normalized_phase_span"] is None else float(item["maximum_normalized_phase_span"]),
            -int(item["distinct_static_states"]),
            float(item["maximum_plateau_v"]),
            int(item["arithmetic_cost"]),
            abs(int(item["a"])),
            abs(int(item["b"])),
        )
    )
    result["candidates"] = candidates
    result["selected"] = candidates[0]
    result["status"] = "selected"
    return result


def local_ambiguity(
    static: Sequence[Mapping[str, Any]],
    phase_groups: Mapping[float, Sequence[Mapping[str, Any]]],
    projection: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Compare phase span with local 20 mV voltage motion for every available score."""

    baseline = static[0]
    score_definitions: Dict[str, Tuple[Sequence[float], Dict[float, List[float]]]] = {}
    for name in ("C", "W"):
        field = name.lower()
        score_definitions[name] = (
            [float(row[field]) for row in static],
            {anchor: [float(row[field]) for row in rows] for anchor, rows in phase_groups.items()},
        )
    if projection.get("floating"):
        weight = projection["floating"]["weight"]
        score_definitions["S_float"] = (
            score_values(static, weight, baseline),
            {anchor: score_values(rows, weight, baseline) for anchor, rows in phase_groups.items()},
        )
    if projection.get("selected"):
        weight = [projection["selected"]["a"], projection["selected"]["b"]]
        score_definitions["S_hw"] = (
            score_values(static, weight, baseline),
            {anchor: score_values(rows, weight, baseline) for anchor, rows in phase_groups.items()},
        )

    by_vdd = {vdd_key(float(row["vdd"])): index for index, row in enumerate(static)}
    result = []
    for name, (static_scores, phase_scores) in score_definitions.items():
        for anchor, window in AMBIGUITY_WINDOWS.items():
            try:
                first = static_scores[by_vdd[vdd_key(window[0])]]
                second = static_scores[by_vdd[vdd_key(window[1])]]
            except KeyError as error:
                raise ValueError("missing required local ambiguity static sample: {}".format(window)) from error
            phase_span = float(max(phase_scores[anchor]) - min(phase_scores[anchor]))
            voltage_span = abs(float(second - first))
            result.append(
                {
                    "metric": name,
                    "anchor_vdd": anchor,
                    "static_samples_used": [window[0], window[1]],
                    "phase_span": phase_span,
                    "local_20mV_voltage_span": voltage_span,
                    "phase_to_voltage_ratio": None if math.isclose(voltage_span, 0.0, abs_tol=FLOAT_TOLERANCE) else phase_span / voltage_span,
                    "status": "local_plateau" if math.isclose(voltage_span, 0.0, abs_tol=FLOAT_TOLERANCE) else "defined",
                }
            )
    return result


def projection_decision(projection: Mapping[str, Any], metrics: Sequence[Mapping[str, Any]]) -> Tuple[str, List[str]]:
    """Map measured outcomes to exactly one task-defined architecture decision."""

    if projection.get("status") in ("skipped_near_collinear", "skipped_float_unusable", "skipped_insufficient_nonzero_vectors"):
        return (
            "NO-GO - move to phase-diverse sampling",
            [
                "Measured voltage and phase directions do not justify a global single-snapshot rejection axis.",
                "A low-complexity projection was not selected; tuning integer weights would not add physical evidence.",
                "Retain the existing FTC front-end and study phase-diverse / multi-phase sampling next.",
            ],
        )
    deviations = [item["angle_to_pooled_deg"] for item in metrics if item.get("angle_to_pooled_deg") is not None]
    if deviations and max(float(value) for value in deviations) > 20.0:
        return (
            "CONDITIONAL - retain 2-D information but do not use one global projection",
            [
                "A phase-rejected score exists, but the measured phase direction varies across VDD.",
                "Keep C/W information for a later region-aware or manifold-decoding study.",
                "Do not add analog hardware or claim global phase invariance from three anchors.",
            ],
        )
    return (
        "GO - pursue low-complexity single-snapshot 2-D phase-rejected readout",
        [
            "Measured directions support a common phase-rejection axis at the tested anchors.",
            "The selected low-cost score retains a monotonic static VDD response.",
            "Replay the completed physical evidence before any new electrical characterization.",
        ],
    )


def configure_plot_style() -> None:
    """Use one compact, color-safe plotting style for all publication-oriented figures."""

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.labelsize": 10,
            "axes.titlesize": 11,
            "legend.fontsize": 8,
            "svg.fonttype": "none",
        }
    )


def save_figure(figure: Any, path: Path) -> None:
    """Write SVG deterministically enough for review and always release plot resources."""

    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, format="svg", bbox_inches="tight", metadata={"Date": None})
    plt.close(figure)
    # Matplotlib wraps SVG path data with spaces before line breaks.  Those
    # spaces are harmless to SVG rendering but violate this repository's
    # whitespace check, so normalize only trailing whitespace after rendering;
    # the newline remains as the required token separator in path data.
    normalized = "\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()) + "\n"
    path.write_text(normalized, encoding="utf-8")


def plot_cw_trajectory(static: Sequence[Mapping[str, Any]], phase_groups: Mapping[float, Sequence[Mapping[str, Any]]], path: Path) -> None:
    """Plot the measured C-W trajectory and the three actual phase displacement arrows."""

    configure_plot_style()
    figure, axis = plt.subplots(figsize=(7.0, 5.1))
    c_values = [row["c"] for row in static]
    w_values = [row["w"] for row in static]
    axis.plot(c_values, w_values, "-o", color="#0072B2", markersize=3.5, label="Static 10 mV samples")
    for row in static:
        if round((1.10 - float(row["vdd"])) * 100) % 5 == 0:
            axis.annotate("{:.2f} V".format(float(row["vdd"])), (row["c"], row["w"]), xytext=(4, 5), textcoords="offset points", fontsize=7)
    axis.scatter([static[0]["c"]], [static[0]["w"]], marker="s", color="#009E73", zorder=4, label="1.10 V endpoint")
    axis.scatter([static[-1]["c"]], [static[-1]["w"]], marker="s", color="#D55E00", zorder=4, label="0.80 V endpoint")
    # Place the direction label in the open middle of the plane.  The high-VDD
    # endpoint and its phase triplet share the top-right corner, so labeling
    # the arrow at its tail would obscure exactly the evidence being compared.
    axis.annotate(
        "increasing droop",
        xy=(static[-1]["c"], static[-1]["w"]),
        xytext=(18.0, 6.2),
        arrowprops={"arrowstyle": "->", "color": "#4D4D4D"},
        fontsize=8,
    )
    colors = {1.10: "#CC79A7", 0.90: "#E69F00", 0.80: "#009E73"}
    phase_label_offsets = {1.10: (5, -25), 0.90: (4, -13), 0.80: (6, -12)}
    for anchor, rows in phase_groups.items():
        minus, nominal, plus = rows
        color = colors[anchor]
        axis.scatter([row["c"] for row in rows], [row["w"] for row in rows], color=color, marker="x", s=34, zorder=5)
        if (minus["c"], minus["w"]) != (plus["c"], plus["w"]):
            axis.annotate("", xy=(plus["c"], plus["w"]), xytext=(minus["c"], minus["w"]), arrowprops={"arrowstyle": "->", "lw": 1.5, "color": color})
        axis.annotate(
            "{:.2f} V phase".format(anchor),
            (nominal["c"], nominal["w"]),
            xytext=phase_label_offsets[anchor],
            textcoords="offset points",
            color=color,
            fontsize=7,
        )
    axis.set_xlabel("C = start + end")
    axis.set_ylabel("W = end - start + 1")
    axis.set_title("Fig. 1. FTC C-W trajectory with measured phase perturbations")
    axis.grid(True, linewidth=0.5, alpha=0.35)
    axis.legend(loc="best")
    save_figure(figure, path)


def plot_cw_vs_vdd(static: Sequence[Mapping[str, Any]], path: Path) -> None:
    """Keep C and W versus physical VDD in separate panels for interpretability."""

    configure_plot_style()
    rows = sorted(static, key=lambda row: float(row["vdd"]))
    figure, axes = plt.subplots(2, 1, figsize=(7.0, 5.4), sharex=True)
    for axis, field, color, label in ((axes[0], "c", "#0072B2", "C"), (axes[1], "w", "#D55E00", "W")):
        axis.plot([row["vdd"] for row in rows], [row[field] for row in rows], "-o", color=color, markersize=3.5)
        axis.set_ylabel(label)
        axis.grid(True, linewidth=0.5, alpha=0.35)
    axes[0].set_title("Fig. 2. Measured C and W versus VDD")
    axes[1].set_xlabel("VDD (V)")
    save_figure(figure, path)


def plot_phase_scores(
    phase_groups: Mapping[float, Sequence[Mapping[str, Any]]],
    projection: Mapping[str, Any],
    baseline: Mapping[str, Any],
    path: Path,
) -> None:
    """Show raw C/W phase sensitivity and a selected score, or an honest skip panel."""

    configure_plot_style()
    figure, axes = plt.subplots(3, 1, figsize=(7.0, 7.0), sharex=True)
    colors = {1.10: "#0072B2", 0.90: "#E69F00", 0.80: "#009E73"}
    for axis, field, label in ((axes[0], "c", "C"), (axes[1], "w", "W")):
        for anchor, rows in phase_groups.items():
            offsets_ps = [float(row["phase_offset_s"]) * 1.0e12 for row in rows]
            axis.plot(offsets_ps, [row[field] for row in rows], "-o", color=colors[anchor], label="{:.2f} V".format(anchor))
        axis.set_ylabel(label)
        axis.grid(True, linewidth=0.5, alpha=0.35)
    axes[0].legend(loc="best")
    if projection.get("selected"):
        weight = [projection["selected"]["a"], projection["selected"]["b"]]
        for anchor, rows in phase_groups.items():
            axes[2].plot([float(row["phase_offset_s"]) * 1.0e12 for row in rows], score_values(rows, weight, baseline), "-o", color=colors[anchor], label="{:.2f} V".format(anchor))
        axes[2].set_ylabel("Selected $S_{hw}$")
    else:
        axes[2].text(0.5, 0.5, "No selected phase-rejected score\n(measured directions are not separable)", ha="center", va="center", transform=axes[2].transAxes)
        axes[2].set_yticks([])
    axes[2].set_xlabel("Capture phase offset (ps)")
    axes[2].grid(True, linewidth=0.5, alpha=0.35)
    axes[0].set_title("Fig. 3. Raw C/W and selected phase-rejected score under phase perturbation")
    save_figure(figure, path)


def plot_selected_score(static: Sequence[Mapping[str, Any]], projection: Mapping[str, Any], path: Path) -> None:
    """Render selected hardware score versus VDD, retaining a visible NO-GO artifact."""

    configure_plot_style()
    figure, axis = plt.subplots(figsize=(7.0, 3.8))
    if projection.get("selected"):
        baseline = static[0]
        weight = [projection["selected"]["a"], projection["selected"]["b"]]
        rows = sorted(static, key=lambda row: float(row["vdd"]))
        axis.plot([row["vdd"] for row in rows], score_values(rows, weight, baseline), "-o", color="#0072B2", markersize=3.5)
        axis.set_ylabel("Selected $S_{hw}$")
        axis.grid(True, linewidth=0.5, alpha=0.35)
    else:
        axis.text(0.5, 0.5, "No selected score: single-snapshot projection is not supported", ha="center", va="center", transform=axis.transAxes)
        axis.set_xticks([])
        axis.set_yticks([])
    axis.set_xlabel("VDD (V)" if projection.get("selected") else "")
    axis.set_title("Fig. 4. Selected phase-rejected score versus VDD")
    save_figure(figure, path)


def markdown_table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> List[str]:
    """Build a compact Markdown table while keeping report construction readable."""

    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return lines


def render_report(
    path: Path,
    static_path: Path,
    phase_path: Path,
    static: Sequence[Mapping[str, Any]],
    phase_vectors: Sequence[Mapping[str, Any]],
    voltage_vectors: Sequence[Mapping[str, Any]],
    separability: Mapping[str, Any],
    projection: Mapping[str, Any],
    ambiguity: Sequence[Mapping[str, Any]],
    representation: Mapping[str, Any],
    decision: Tuple[str, Sequence[str]],
) -> None:
    """Write the required research-result report from calculated artifacts, not log text."""

    c_change = int(static[-1]["c"]) - int(static[0]["c"])
    w_change = int(static[-1]["w"]) - int(static[0]["w"])
    dominant = "window translation (C change)" if abs(c_change) > abs(w_change) else "a combination of translation and width change"
    figure_root = "../analysis/phase_voltage_2d/figures"
    lines = [
        "# FTC Phase/Voltage 2-D Separability",
        "",
        "## A. Research question",
        "",
        "This analysis asks whether the existing FTC `(start,end)` output contains a voltage-sensitive direction separable from sampling-phase motion, without changing the physical sensor.",
        "",
        "## B. Baseline and data provenance",
        "",
        "- Formal range: 0.80--1.10 V; TT/25 C completed FTC RVT/LVT reproduction.",
        "- Selected operating point: four RVT initial stages, zero LVT initial stages, 300 ps capture phase, 30 observable stages.",
        "- Static source: `{}` (31 valid 10 mV samples).".format(static_path),
        "- Phase source: `{}` (three offsets at 1.10, 0.90, and 0.80 V).".format(phase_path),
        "- No new HSPICE run, deck generation, or FTC structural change was performed.",
        "",
        "## C. Feature definition",
        "",
        "`C = start + end` represents the measured spatial position of the longest XOR window, and `W = end - start + 1` represents its measured width/path-separation information. These are working interpretations of this measured FTC output, not claims of invariant physical modes.",
        "",
        "## D. Static C-W trajectory",
        "",
        "![Fig. 1]({}/fig1_cw_trajectory.svg)".format(figure_root),
        "",
        "![Fig. 2]({}/fig2_cw_vs_vdd.svg)".format(figure_root),
        "",
        "Across the measured range, C changes from {} to {} (delta {}) and W changes from {} to {} (delta {}). The static response is primarily {}.".format(static[0]["c"], static[-1]["c"], c_change, static[0]["w"], static[-1]["w"], w_change, dominant),
        "",
        "Representation state counts: `(start,end)`={}, `C`={}, `W`={}, `(C,W)`={}.".format(
            representation["start_end"]["unique_states"], representation["c"]["unique_states"], representation["w"]["unique_states"], representation["c_w"]["unique_states"]
        ),
        "",
        "## E. Sampling-phase vectors",
        "",
    ]
    lines.extend(markdown_table(
        ["VDD", "C-/W-", "C0/W0", "C+/W+", "vPhi", "Status"],
        [
            [
                "{:.2f} V".format(row["anchor_vdd"]),
                "{}/{}".format(row["C_minus"], row["W_minus"]),
                "{}/{}".format(row["C_nominal"], row["W_nominal"]),
                "{}/{}".format(row["C_plus"], row["W_plus"]),
                "({:.3g}, {:.3g})".format(row["vPhi_C"], row["vPhi_W"]),
                "phase-insensitive" if row["phase_insensitive"] else "measured movement",
            ]
            for row in phase_vectors
        ],
    ))
    lines.extend(["", "## F. Separability metrics", ""])
    voltage_by_anchor = {float(row["anchor_vdd"]): row for row in voltage_vectors}
    # Separability JSON stores angular metrics separately from the measured
    # phase-vector table.  Rejoin them here by VDD so the report table shows
    # both the actual displacement and its derived collinearity measurement.
    phase_by_anchor = {float(row["anchor_vdd"]): row for row in phase_vectors}
    lines.extend(markdown_table(
        ["VDD", "vV (droop)", "vPhi", "|cos|", "Acute angle", "Interpretation"],
        [
            [
                "{:.2f} V".format(row["anchor_vdd"]),
                "({:.3g}, {:.3g})".format(voltage_by_anchor[row["anchor_vdd"]]["vV_C"], voltage_by_anchor[row["anchor_vdd"]]["vV_W"]),
                "({:.3g}, {:.3g})".format(phase_by_anchor[row["anchor_vdd"]]["vPhi_C"], phase_by_anchor[row["anchor_vdd"]]["vPhi_W"]),
                "undefined" if row["absolute_cosine_similarity"] is None else "{:.3f}".format(row["absolute_cosine_similarity"]),
                "undefined" if row["acute_angle_deg"] is None else "{:.2f} deg".format(row["acute_angle_deg"]),
                "near-collinear" if row["acute_angle_deg"] is not None and row["acute_angle_deg"] < NEAR_COLLINEAR_DEGREES else "non-collinear / unavailable",
            ]
            for row in separability["per_anchor"]
        ],
    ))
    lines.extend([
        "",
        "The pooled phase direction is `{}`. It is a derived global approximation only; per-anchor metrics above remain the decision evidence.".format(separability["pooled_phase_direction"]),
        "",
        "## G. Projection experiment",
        "",
        "![Fig. 3]({}/fig3_phase_perturbation.svg)".format(figure_root),
        "",
        "![Fig. 4]({}/fig4_selected_score_vs_vdd.svg)".format(figure_root),
        "",
    ])
    if projection["status"] == "selected":
        selected = projection["selected"]
        lines.extend([
            "The selected hardware-friendly score is `S_hw = {}*DeltaC + {}*DeltaW`.".format(selected["a"], selected["b"]),
            "",
        ])
        lines.extend(markdown_table(
            ["a", "b", "Static states", "Max plateau", "Max normalized phase span"],
            [
                [
                    candidate["a"],
                    candidate["b"],
                    candidate["distinct_static_states"],
                    "{:.3g} V".format(candidate["maximum_plateau_v"]),
                    "{:.3g}".format(candidate["maximum_normalized_phase_span"]),
                ]
                for candidate in projection["candidates"][:8]
            ],
        ))
    else:
        lines.extend(["No float or integer phase-rejected score was selected: `{}`. {}".format(projection["status"], projection["reason"]), ""])
        lines.extend(markdown_table(
            ["Candidate search status", "Reason"],
            [[projection["status"], projection["reason"]]],
        ))
    lines.extend(["", "## H. Local ambiguity analysis", ""])
    lines.extend(markdown_table(
        ["Metric", "VDD", "Phase span", "Local ~20 mV span", "Ratio", "Status"],
        [
            [
                row["metric"],
                "{:.2f} V".format(row["anchor_vdd"]),
                "{:.3g}".format(row["phase_span"]),
                "{:.3g}".format(row["local_20mV_voltage_span"]),
                "undefined" if row["phase_to_voltage_ratio"] is None else "{:.3g}".format(row["phase_to_voltage_ratio"]),
                row["status"],
            ]
            for row in ambiguity
        ],
    ))
    lines.extend([
        "",
        "## I. Limitations",
        "",
        "- Only already measured TT/25 C physical evidence is used.",
        "- Phase characterization exists at only three VDD anchors; this is not PVT robustness evidence.",
        "- Quantized start/end codes make local derivatives discrete and can expose plateaus.",
        "- No phase-invariance claim is made beyond the measured three-offset data.",
        "",
        "## J. {}".format(decision[0]),
        "",
    ])
    lines.extend("- {}".format(item) for item in decision[1])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_analysis(static_path: Path, phase_path: Path, output_dir: Path, report_path: Path) -> Dict[str, Any]:
    """Execute the complete deterministic post-processing flow and write task outputs."""

    static_rows, static_fields = read_csv_rows(static_path)
    phase_rows, phase_fields = read_csv_rows(phase_path)
    validate_inputs(static_rows, phase_rows, static_path, phase_path)
    static_cw = add_cw(static_rows)
    phase_cw = add_cw(phase_rows)
    static = canonical_static(static_cw)
    phase_groups = canonical_phase(phase_cw)
    representation = static_representation_summary(static)

    voltage_vectors = [local_fit(static, anchor) for anchor in ANCHORS]
    phase_vectors = [phase_vector(anchor, phase_groups[anchor]) for anchor in ANCHORS]
    voltage_by_anchor = {float(row["anchor_vdd"]): row for row in voltage_vectors}
    per_anchor = []
    for phase_row in phase_vectors:
        voltage_row = voltage_by_anchor[float(phase_row["anchor_vdd"])]
        metrics = cosine_metrics(
            [voltage_row["vV_C"], voltage_row["vV_W"]],
            [phase_row["vPhi_C"], phase_row["vPhi_W"]],
        )
        per_anchor.append({"anchor_vdd": phase_row["anchor_vdd"], **metrics})
    pooled, variation = pooled_phase_direction(phase_vectors)
    separability = {"per_anchor": per_anchor, "pooled_phase_direction": pooled, "phase_direction_variation": variation}
    projection = evaluate_projection(static, phase_groups, per_anchor, pooled)
    ambiguity = local_ambiguity(static, phase_groups, projection)
    decision = projection_decision(projection, variation)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "static_cw.csv", static_cw, list(static_fields) + ["c", "w"])
    write_csv(output_dir / "phase_cw.csv", phase_cw, list(phase_fields) + ["c", "w"])
    write_csv(
        output_dir / "local_voltage_vectors.csv",
        voltage_vectors,
        ["anchor_vdd", "samples_used", "vV_C", "vV_W", "r2_C", "r2_W", "endpoint_dC", "endpoint_dW", "fit_endpoint_cosine", "quantized_direction_disagreement"],
    )
    write_csv(
        output_dir / "phase_vectors.csv",
        phase_vectors,
        ["anchor_vdd", "phase_delta_s", "C_minus", "W_minus", "C_nominal", "W_nominal", "C_plus", "W_plus", "vPhi_C", "vPhi_W", "phase_span_C", "phase_span_W", "phase_insensitive"],
    )
    candidate_fields = ["canonical_a", "canonical_b", "a", "b", "static_min", "static_max", "static_range", "distinct_static_states", "monotonic_with_droop", "maximum_plateau_v", "phase_span_1p10", "phase_span_0p90", "phase_span_0p80", "maximum_normalized_phase_span", "arithmetic_cost"]
    write_csv(output_dir / "projection_candidates.csv", projection["candidates"], candidate_fields)
    write_csv(
        output_dir / "local_ambiguity.csv",
        ambiguity,
        ["metric", "anchor_vdd", "static_samples_used", "phase_span", "local_20mV_voltage_span", "phase_to_voltage_ratio", "status"],
    )
    audit = {
        "static_source": str(static_path),
        "static_sha256": sha256(static_path),
        "static_row_count": len(static_rows),
        "phase_source": str(phase_path),
        "phase_sha256": sha256(phase_path),
        "phase_row_count": len(phase_rows),
        "formal_vdd_range_v": [0.80, 1.10],
        "phase_anchors_v": list(ANCHORS),
        "python_version": sys.version.split()[0],
        "numpy_version": np.__version__,
        "matplotlib_version": matplotlib.__version__,
        "matplotlib_backend": matplotlib.get_backend(),
        "representation_summary": representation,
    }
    write_json(output_dir / "input_audit.json", audit)
    write_json(output_dir / "separability_metrics.json", {**separability, "local_ambiguity": ambiguity})
    write_json(output_dir / "projection_selection.json", projection)
    figures = output_dir / "figures"
    plot_cw_trajectory(static, phase_groups, figures / "fig1_cw_trajectory.svg")
    plot_cw_vs_vdd(static, figures / "fig2_cw_vs_vdd.svg")
    plot_phase_scores(phase_groups, projection, static[0], figures / "fig3_phase_perturbation.svg")
    plot_selected_score(static, projection, figures / "fig4_selected_score_vs_vdd.svg")
    render_report(report_path, static_path, phase_path, static, phase_vectors, voltage_vectors, separability, projection, ambiguity, representation, decision)
    return {"decision": decision[0], "projection_status": projection["status"], "output_dir": str(output_dir), "report": str(report_path)}


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Expose only file paths needed for deterministic post-processing and testing."""

    parser = argparse.ArgumentParser(description="analyze completed FTC phase/voltage C-W separability evidence")
    parser.add_argument("--static-input", type=Path, default=DEFAULT_STATIC_INPUT, help="completed static_transfer.csv input")
    parser.add_argument("--phase-input", type=Path, default=DEFAULT_PHASE_INPUT, help="completed phase_sensitivity.csv input")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="task-owned CSV/JSON/figure output directory")
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT_OUTPUT, help="research-result Markdown report path")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the analysis and print only the compact artifact handoff needed by callers."""

    args = parse_args(argv)
    result = run_analysis(args.static_input.resolve(), args.phase_input.resolve(), args.output_dir.resolve(), args.report_output.resolve())
    print("FTC_PHASE_VOLTAGE_2D decision={} projection_status={}".format(result["decision"], result["projection_status"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
