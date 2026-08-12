#!/usr/bin/env python3
"""Analyze compact FTC phase-diverse evidence without launching a simulator.

The physical runner writes one row per real-cell HSPICE scenario.  This module
keeps all candidate qualification, baseline construction, blind-window
extraction, phase-set ranking, and jitter re-scoring in deterministic Python
data processing so unit tests cannot accidentally substitute an inferred model
for electrical evidence.
"""

import argparse
import csv
import itertools
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


def read_csv(path: Path) -> List[Dict[str, str]]:
    """Read a nonempty compact CSV and fail loudly on missing evidence."""

    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("empty FTC phase-diverse evidence: {}".format(path))
    return rows


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Write stable compact evidence with a deterministic first-seen column order."""

    if not rows:
        raise ValueError("refusing to write empty phase-diverse evidence: {}".format(path))
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def write_json(path: Path, value: Any) -> None:
    """Write reviewable JSON only after all values have been reduced to builtins."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def number(row: Mapping[str, Any], key: str) -> float:
    """Convert one CSV scalar while keeping malformed physical evidence visible."""

    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("missing/non-numeric {} in phase-diverse row".format(key)) from error


def integer(row: Mapping[str, Any], key: str) -> int:
    """Convert an integer contract field from either CSV text or JSON data."""

    return int(round(number(row, key)))


def phase_key(row: Mapping[str, Any]) -> str:
    """Return the stable phase identifier required by all downstream joins."""

    value = str(row.get("phase_id", ""))
    if not value:
        raise ValueError("phase-diverse row lacks phase_id")
    return value


def qualify_candidates(anchor_rows: Sequence[Mapping[str, Any]], coarse_rows: Sequence[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Apply the fixed physical qualification gate to anchor and coarse rows."""

    # Qualification is restricted to the current formal range.  Historical
    # 0.75 V rows are retained in their original raw run but are deliberately
    # excluded from any new phase-diverse eligibility conclusion.
    anchors = {1.10, 0.90, 0.80}
    anchor_by_phase: Dict[str, List[Mapping[str, Any]]] = {}
    coarse_by_phase: Dict[str, List[Mapping[str, Any]]] = {}
    for row in anchor_rows:
        anchor_by_phase.setdefault(phase_key(row), []).append(row)
    for row in coarse_rows:
        coarse_by_phase.setdefault(phase_key(row), []).append(row)
    phases = sorted(set(anchor_by_phase) | set(coarse_by_phase))
    qualified: List[Dict[str, Any]] = []
    details: List[Dict[str, Any]] = []
    for phase_id in phases:
        arows = sorted(anchor_by_phase.get(phase_id, []), key=lambda row: number(row, "vdd_v"), reverse=True)
        crows = sorted(coarse_by_phase.get(phase_id, []), key=lambda row: number(row, "vdd_v"), reverse=True)
        anchor_valid = len(arows) == len(anchors) and {round(number(row, "vdd_v"), 2) for row in arows} == anchors and all(integer(row, "valid") == 1 for row in arows)
        # The current coarse qualification grid contains seven legal 50 mV
        # points from 1.10 V through 0.80 V.  Historical 0.75 V phase rows are
        # intentionally not eligible for a current-range phase conclusion.
        coarse_valid = len(crows) == 7 and all(integer(row, "valid") == 1 for row in crows)
        states = {(integer(row, "start_index"), integer(row, "end_index")) for row in crows if integer(row, "valid") == 1}
        direction_ok = True
        if crows:
            starts = [integer(row, "start_index") for row in crows]
            ends = [integer(row, "end_index") for row in crows]
            direction_ok = all(left >= right for left, right in zip(starts, starts[1:])) and all(left >= right for left, right in zip(ends, ends[1:]))
        boundary_points = sum(int(integer(row, "touches_left_boundary") or integer(row, "touches_right_boundary")) for row in crows)
        adjacent_jumps = [abs(integer(left, "start_index") - integer(right, "start_index")) + abs(integer(left, "end_index") - integer(right, "end_index")) for left, right in zip(crows, crows[1:])]
        eligible = bool(anchor_valid and coarse_valid and direction_ok and len(states) >= 2)
        reason = "eligible" if eligible else ";".join(
            label for label, passed in ((
                ("anchor_invalid", not anchor_valid), ("coarse_invalid", not coarse_valid),
                ("voltage_direction_inconsistent", not direction_ok), ("constant_or_empty_state", len(states) < 2),
            )) if passed
        )
        details.append({
            "phase_id": phase_id, "anchor_valid": int(anchor_valid), "coarse_valid": int(coarse_valid),
            "direction_consistent": int(direction_ok), "valid_coarse_points": sum(integer(row, "valid") for row in crows),
            "distinct_start_end_states": len(states), "largest_adjacent_encoded_jump": max(adjacent_jumps) if adjacent_jumps else 0,
            "boundary_points": boundary_points, "eligible": int(eligible), "reason": reason,
        })
        if eligible:
            phase_meta = dict(arows[0])
            phase_meta.update({"phase_id": phase_id, "capture_phase_s": number(arows[0], "capture_phase_s"), "phase_multiplier": integer(arows[0], "phase_multiplier")})
            qualified.append(phase_meta)
    return qualified, {"candidate_count": len(phases), "eligible_phase_ids": [item["phase_id"] for item in qualified], "candidates": details}


def build_baselines(coarse_rows: Sequence[Mapping[str, Any]], phase_ids: Iterable[str]) -> Dict[str, Any]:
    """Create one independent nominal word and encoded state per eligible phase."""

    selected = set(phase_ids)
    result: List[Dict[str, Any]] = []
    for phase_id in sorted(selected):
        rows = [row for row in coarse_rows if phase_key(row) == phase_id and math.isclose(number(row, "vdd_v"), 1.10, abs_tol=1.0e-9)]
        if len(rows) != 1 or integer(rows[0], "valid") != 1:
            raise ValueError("phase {} lacks one valid 1.10 V nominal baseline".format(phase_id))
        row = rows[0]
        result.append({
            "phase_id": phase_id, "capture_phase_s": number(row, "capture_phase_s"),
            "captured_xor_word": str(row["captured_xor_word"]), "nominal_start": integer(row, "start_index"),
            "nominal_end": integer(row, "end_index"), "nominal_length": integer(row, "one_run_length"),
            "start_index": integer(row, "start_index"), "end_index": integer(row, "end_index"),
        })
    if len(result) < 2:
        raise ValueError("phase diversity requires at least two qualified phase baselines")
    return {"schema_version": 1, "phases": result}


def baseline_map(baselines: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    """Index baseline JSON while rejecting duplicate phase records."""

    result: Dict[str, Mapping[str, Any]] = {}
    for item in baselines.get("phases", []):
        phase_id = str(item["phase_id"])
        if phase_id in result:
            raise ValueError("duplicate phase baseline: {}".format(phase_id))
        result[phase_id] = item
    return result


def blind_intervals(onsets: Sequence[float], detected: Sequence[bool]) -> List[Dict[str, float]]:
    """Extract measured blind runs without smoothing or hiding quantization bins."""

    if len(onsets) != len(detected) or not onsets:
        raise ValueError("blind interval input must be nonempty and aligned")
    # Keep every boolean paired with its own onset before sorting.  Refinement
    # runs may be supplied out of order, and sorting only the timing vector
    # would silently attach a blind/detected flag to the wrong physical event.
    ordered = sorted(zip((float(value) for value in onsets), (bool(value) for value in detected)), key=lambda pair: pair[0])
    deltas = [ordered[index + 1][0] - ordered[index][0] for index in range(len(ordered) - 1) if ordered[index + 1][0] > ordered[index][0]]
    default_step = min(deltas) if deltas else 0.0
    intervals: List[Dict[str, float]] = []
    index = 0
    while index < len(ordered):
        if ordered[index][1]:
            index += 1
            continue
        begin = index
        while index + 1 < len(ordered) and not ordered[index + 1][1]:
            index += 1
        end = index
        end_width = (ordered[end + 1][0] - ordered[end][0]) if end + 1 < len(ordered) else default_step
        intervals.append({"start_s": ordered[begin][0], "end_s": ordered[end][0] + end_width, "duration_s": ordered[end][0] + end_width - ordered[begin][0]})
        index += 1
    return intervals


def map_summary(rows: Sequence[Mapping[str, Any]], detection_field: str = "encoded_state_changed") -> Dict[str, Any]:
    """Summarize per-phase and per-family detection and blind windows."""

    groups: Dict[Tuple[str, str], List[Mapping[str, Any]]] = {}
    for row in rows:
        groups.setdefault((str(row["case_id"]), phase_key(row)), []).append(row)
    summary: Dict[str, Any] = {"groups": []}
    for (case_id, phase_id), group in sorted(groups.items()):
        ordered = sorted(group, key=lambda row: number(row, "glitch_onset_rel_s"))
        onsets = [number(row, "glitch_onset_rel_s") for row in ordered]
        detected = [bool(integer(row, detection_field)) for row in ordered]
        intervals = blind_intervals(onsets, detected)
        summary["groups"].append({
            "case_id": case_id, "phase_id": phase_id, "detection_field": detection_field,
            "detection_fraction": sum(detected) / len(detected), "sample_count": len(detected),
            "blind_intervals": intervals,
            "longest_blind_interval_s": max((item["duration_s"] for item in intervals), default=0.0),
            "minimum_detected_boundary_distance": min((integer(row, "boundary_distance") for row in ordered if integer(row, detection_field)), default=0),
            "maximum_detected_boundary_distance": max((integer(row, "boundary_distance") for row in ordered if integer(row, detection_field)), default=0),
        })
    return summary


def set_detection(rows: Sequence[Mapping[str, Any]], phase_ids: Sequence[str], detection_field: str) -> Dict[Tuple[str, float], bool]:
    """Build one same-onset OR result for a phase set, preserving family keys."""

    selected = set(phase_ids)
    result: Dict[Tuple[str, float], bool] = {}
    for row in rows:
        if phase_key(row) not in selected:
            continue
        key = (str(row["case_id"]), number(row, "glitch_onset_rel_s"))
        result[key] = result.get(key, False) or bool(integer(row, detection_field))
    return result


def rank_phase_sets(rows: Sequence[Mapping[str, Any]], phase_ids: Sequence[str], detection_field: str) -> List[Dict[str, Any]]:
    """Rank one-, two-, and three-phase sets by common blind-window priority."""

    result: List[Dict[str, Any]] = []
    maximum_size = min(3, len(phase_ids))
    for size in range(1, maximum_size + 1):
        for combination in itertools.combinations(sorted(phase_ids), size):
            detections = set_detection(rows, combination, detection_field)
            by_case: Dict[str, List[Tuple[float, bool]]] = {}
            for (case_id, onset), detected in detections.items():
                by_case.setdefault(case_id, []).append((onset, detected))
            case_summaries = []
            for case_id, values in sorted(by_case.items()):
                values.sort(key=lambda item: item[0])
                intervals = blind_intervals([item[0] for item in values], [item[1] for item in values])
                case_summaries.append({
                    "case_id": case_id,
                    "detection_fraction": sum(item[1] for item in values) / len(values),
                    "blind_intervals": intervals,
                    "longest_common_blind_interval_s": max((item["duration_s"] for item in intervals), default=0.0),
                    "total_common_blind_duration_s": sum(item["duration_s"] for item in intervals),
                })
            result.append({
                "phase_ids": list(combination), "phase_count": size, "detection_field": detection_field,
                "case_summaries": case_summaries,
                "worst_longest_common_blind_s": max((item["longest_common_blind_interval_s"] for item in case_summaries), default=float("inf")),
                "worst_detection_fraction": min((item["detection_fraction"] for item in case_summaries), default=0.0),
            })
    return sorted(result, key=lambda item: (item["worst_longest_common_blind_s"], -item["worst_detection_fraction"], item["phase_count"], item["phase_ids"]))


def jitter_summary(jitter_rows: Sequence[Mapping[str, Any]], baselines: Mapping[str, Any]) -> Dict[str, Any]:
    """Compute a no-glitch encoded movement envelope independently of attacks.

    A phase perturbation at 0.80 or 0.90 V must be compared with the zero-
    offset capture at that same voltage.  Comparing it to the 1.10 V startup
    baseline would measure the intended static voltage response and falsely
    inflate the phase-jitter tolerance.
    """

    groups: Dict[Tuple[str, float], List[Mapping[str, Any]]] = {}
    for row in jitter_rows:
        phase_id = phase_key(row)
        # Confirm the row names a known phase baseline even though the local
        # same-VDD zero-offset state is the envelope reference below.
        if phase_id not in baseline_map(baselines):
            raise ValueError("jitter row references an unknown phase baseline: {}".format(phase_id))
        groups.setdefault((phase_id, number(row, "vdd_v")), []).append(row)
    result = []
    for (phase_id, vdd), group in sorted(groups.items()):
        nominal_rows = [item for item in group if math.isclose(number(item, "phase_offset_s"), 0.0, abs_tol=1.0e-18)]
        if len(nominal_rows) != 1:
            raise ValueError("jitter group needs exactly one zero-offset state: {} at {} V".format(phase_id, vdd))
        nominal = nominal_rows[0]
        enriched = []
        for item in group:
            row = dict(item)
            row["boundary_distance"] = abs(integer(item, "start_index") - integer(nominal, "start_index")) + abs(integer(item, "end_index") - integer(nominal, "end_index"))
            enriched.append(row)
        result.append({
            "phase_id": phase_id, "vdd_v": vdd,
            "nominal_start_index": integer(nominal, "start_index"), "nominal_end_index": integer(nominal, "end_index"),
            "maximum_boundary_distance": max(integer(item, "boundary_distance") for item in enriched),
            "accepted_states": sorted({(integer(item, "start_index"), integer(item, "end_index")) for item in enriched}),
            "sample_count": len(enriched),
        })
    return {"schema_version": 1, "groups": result}


def apply_jitter_envelope(rows: Sequence[Mapping[str, Any]], baselines: Mapping[str, Any], envelope: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Re-score glitch rows so normal measured phase movement is not an alarm."""

    by_phase = baseline_map(baselines)
    limits = {(str(item["phase_id"]), round(float(item["vdd_v"]), 2)): int(item["maximum_boundary_distance"]) for item in envelope["groups"]}
    result = []
    for row in rows:
        phase_id = phase_key(row)
        base = by_phase[phase_id]
        distance = abs(integer(row, "start_index") - int(base["start_index"])) + abs(integer(row, "end_index") - int(base["end_index"]))
        key = (phase_id, round(number(row, "vdd_v"), 2))
        if key not in limits:
            # A missing no-glitch envelope is unknown behavior, not a zero
            # tolerance.  Excluding it from jitter-aware ranking prevents an
            # unmeasured candidate from receiving an artificial advantage.
            continue
        limit = limits[key]
        enriched = dict(row)
        enriched["jitter_boundary_distance"] = distance
        enriched["jitter_envelope"] = limit
        enriched["jitter_aware_detected"] = int(integer(row, "valid") == 0 or distance > limit)
        result.append(enriched)
    return result


def sequential_schedule_summary(rows: Sequence[Mapping[str, Any]], phase_ids: Sequence[str], sampling_period_s: float) -> Dict[str, Any]:
    """Report deterministic A/B semantics without substituting same-launch OR.

    A one-shot event belongs to exactly one sampling cycle and therefore sees
    only the phase assigned to that cycle.  For uniformly unknown A/B parity,
    the reported single-event coverage is the arithmetic mean of the two
    *individual* observations, while the worst-case figure is their minimum.
    Persistent-event coverage is intentionally marked unavailable here because
    the bounded 200 ps physical campaign does not span the 6 ns cadence.
    """

    if len(phase_ids) != 2 or phase_ids[0] == phase_ids[1]:
        raise ValueError("sequential A/B analysis requires exactly two distinct phase IDs")
    selected = set(phase_ids)
    by_case_onset: Dict[Tuple[str, float], Dict[str, Mapping[str, Any]]] = {}
    for row in rows:
        if phase_key(row) in selected:
            by_case_onset.setdefault((str(row["case_id"]), number(row, "glitch_onset_rel_s")), {})[phase_key(row)] = row
    cases: Dict[str, List[Tuple[float, bool, bool]]] = {}
    for (case_id, onset), values in by_case_onset.items():
        if set(values) != selected:
            raise ValueError("sequential A/B map has mismatched phase samples at one onset")
        cases.setdefault(case_id, []).append((onset, bool(integer(values[phase_ids[0]], "jitter_aware_detected")), bool(integer(values[phase_ids[1]], "jitter_aware_detected"))))
    results = []
    for case_id, values in sorted(cases.items()):
        values.sort(key=lambda item: item[0])
        a_fraction = sum(item[1] for item in values) / len(values)
        b_fraction = sum(item[2] for item in values) / len(values)
        last_measured_onset = max(item[0] for item in values)
        # The campaign maps only the launch-adjacent aperture.  Every onset
        # after that aperture until the next launch remains unobserved and is
        # reported explicitly as a cadence blind lower bound.
        off_aperture_lower_bound = max(0.0, float(sampling_period_s) - max(0.0, last_measured_onset))
        results.append({
            "case_id": case_id, "schedule": list(phase_ids),
            "single_event_detection_fraction_unknown_parity": (a_fraction + b_fraction) / 2.0,
            "single_event_worst_phase_detection_fraction": min(a_fraction, b_fraction),
            "per_phase_detection_fraction": {phase_ids[0]: a_fraction, phase_ids[1]: b_fraction},
            "same_launch_union_not_used": True,
            "persistent_two_cycle_coverage": None,
            "persistent_two_cycle_reason": "not_measured: mapped glitch width is shorter than sampling period",
            "full_cycle_unobserved_interval_lower_bound_s": off_aperture_lower_bound,
        })
    return {"schema_version": 1, "sampling_period_s": float(sampling_period_s), "results": results}


def main_analysis(argv: Iterable[str] = None) -> int:
    """Run only explicit evidence transformations; no command here invokes HSPICE."""

    parser = argparse.ArgumentParser(description="analyze compact FTC phase-diverse evidence")
    parser.add_argument("stage", choices=("screen", "baseline", "map", "score", "schedule"))
    parser.add_argument("--anchor", type=Path)
    parser.add_argument("--coarse", type=Path)
    parser.add_argument("--baselines", type=Path)
    parser.add_argument("--glitch-map", type=Path)
    parser.add_argument("--jitter", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--phase-ids")
    parser.add_argument("--sampling-period-s", type=float)
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    if args.stage == "screen":
        qualified, summary = qualify_candidates(read_csv(args.anchor), read_csv(args.coarse))
        write_json(output / "phase_candidate_summary.json", summary)
        write_json(output / "qualified_phases.json", {"phases": qualified})
    elif args.stage == "baseline":
        baselines = build_baselines(read_csv(args.coarse), args.phase_ids.split(","))
        write_json(output / "phase_baselines.json", baselines)
    elif args.stage == "map":
        rows = read_csv(args.glitch_map)
        summary = map_summary(rows)
        write_json(output / "glitch_phase_map_summary.json", summary)
        phase_ids = sorted({phase_key(row) for row in rows})
        ranked = rank_phase_sets(rows, phase_ids, "encoded_state_changed")
        write_csv(output / "phase_set_candidates.csv", [
            {"phase_ids": "+".join(item["phase_ids"]), "phase_count": item["phase_count"], "worst_longest_common_blind_s": item["worst_longest_common_blind_s"], "worst_detection_fraction": item["worst_detection_fraction"], "detection_field": item["detection_field"]}
            for item in ranked
        ])
        write_json(output / "phase_set_selection.json", {"ranking": ranked, "best": ranked[0] if ranked else None})
    elif args.stage == "score":
        baselines = json.loads(args.baselines.read_text(encoding="utf-8"))
        envelope = jitter_summary(read_csv(args.jitter), baselines)
        write_json(output / "phase_jitter_summary.json", envelope)
        scored = apply_jitter_envelope(read_csv(args.glitch_map), baselines, envelope)
        if not scored:
            raise ValueError("no glitch rows have a measured jitter envelope at their VDD")
        write_csv(output / "glitch_phase_map_jitter_aware.csv", scored)
        phase_ids = sorted({phase_key(row) for row in scored})
        ranked = rank_phase_sets(scored, phase_ids, "jitter_aware_detected")
        write_json(output / "phase_set_selection_jitter_aware.json", {"ranking": ranked, "best": ranked[0] if ranked else None})
    else:
        if args.phase_ids is None or args.sampling_period_s is None or args.sampling_period_s <= 0.0:
            parser.error("schedule requires --phase-ids and positive --sampling-period-s")
        rows = read_csv(args.glitch_map)
        # Sequential semantics must use the jitter-aware detector, because a
        # normal phase excursion must not be counted as an attack in either
        # A or B sample.
        write_json(output / "sequential_schedule_summary.json", sequential_schedule_summary(rows, args.phase_ids.split(","), args.sampling_period_s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_analysis())
