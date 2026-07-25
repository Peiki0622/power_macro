#!/usr/bin/env python3
"""Decode HSPICE arrival crossings and select ideal Vernier candidates.

The physical sweep provides simultaneous-launch ``S_i`` and ``R_i`` crossings.
For a programmed launch offset ``delta``, the sense arrival is exactly
``S_i + delta`` while the reference arrival is unchanged.  This analysis uses
that relationship to evaluate all calibration choices without replacing real
cell propagation with a mathematical delay model.
"""

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


ANCHOR_FIELDS = {
    "nominal": "vnom_v",
    "last_passing": "last_passing_voltage_v",
    "first_violation": "first_violation_voltage_v",
}


def load_json(path: Path) -> Dict[str, Any]:
    """Read a JSON object; missing selection constraints are never inferred."""

    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def finite_float(row: Dict[str, str], field: str, context: str) -> float:
    """Parse a required HSPICE CSV number while rejecting late or failed taps."""

    value = row.get(field, "").strip()
    if not value:
        raise ValueError("{} lacks {}".format(context, field))
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError("{} has nonnumeric {}={!r}".format(context, field, value)) from error
    if not math.isfinite(parsed):
        raise ValueError("{} has non-finite {}={!r}".format(context, field, value))
    return parsed


def read_rows(path: Path) -> List[Dict[str, str]]:
    """Read the rectangular arrival evidence table and reject an empty run."""

    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("arrival CSV is empty: {}".format(path))
    return rows


def closest_row(rows: Sequence[Dict[str, str]], voltage_v: float, context: str) -> Dict[str, str]:
    """Find one exact configured anchor row, never a nearest rounded point."""

    matches = [row for row in rows if abs(finite_float(row, "vdd_a_v", context) - voltage_v) <= 1.0e-12]
    if len(matches) != 1:
        raise ValueError("{} needs exactly one row at {} V, found {}".format(context, voltage_v, len(matches)))
    return matches[0]


def arrivals(row: Dict[str, str], m_stages: int) -> Tuple[List[float], List[float]]:
    """Return ordered real-cell sense and reference crossings for one scenario."""

    context = row["scenario_id"]
    sense = [finite_float(row, "sense_{:03d}_cross_s".format(index), context) for index in range(m_stages)]
    reference = [finite_float(row, "ref_{:03d}_cross_s".format(index), context) for index in range(m_stages)]
    if any(sense[index + 1] <= sense[index] for index in range(m_stages - 1)):
        raise ValueError("sense crossings are not strictly ordered: {}".format(context))
    if any(reference[index + 1] <= reference[index] for index in range(m_stages - 1)):
        raise ValueError("reference crossings are not strictly ordered: {}".format(context))
    return sense, reference


def launch_offsets(nominal_row: Dict[str, str], m_stages: int, configured_offsets: Sequence[float]) -> List[Tuple[float, float]]:
    """Derive target-midpoint launch offsets from measured nominal arrival gaps.

    With simultaneous launches, ``reference[i] - sense[i]`` is the maximum
    allowed extra sense delay for bit ``i`` to remain one.  The midpoint between
    the two middle gaps places the nominal 0-to-1 transition at ``M/2``.  The
    configured multipliers step by the measured per-stage Vernier gap, rather
    than by an arbitrary picosecond value.
    """

    sense, reference = arrivals(nominal_row, m_stages)
    target = m_stages // 2
    gaps = [reference[index] - sense[index] for index in range(m_stages)]
    unit_gap = gaps[target] - gaps[target - 1]
    if unit_gap <= 0.0:
        raise ValueError("M={} nominal reference chain is not slower than sense chain".format(m_stages))
    base = (gaps[target - 1] + gaps[target]) / 2.0
    return [(float(multiplier), base + float(multiplier) * unit_gap) for multiplier in configured_offsets]


def decode_one(sense: Sequence[float], reference: Sequence[float], launch_offset_s: float, guard_s: float) -> Dict[str, Any]:
    """Decode one 0*1* thermometer code from physical edge-comparison timing.

    A DFF clocked by ``R_i`` sees a one only if the delayed sense edge arrived
    before ``R_i - guard``.  The ideal architecture expects zeroes first and
    ones later; every later zero after a one is retained as a non-monotonic
    bubble rather than silently repaired in this pre-DFF analysis.
    """

    bits = [1 if sense_time + launch_offset_s <= ref_time - guard_s else 0 for sense_time, ref_time in zip(sense, reference)]
    first_one = next((index for index, bit in enumerate(bits) if bit == 1), len(bits))
    bubble_count = sum(1 for bit in bits[first_one:] if bit == 0)
    transition_count = sum(1 for index in range(1, len(bits)) if bits[index] != bits[index - 1])
    return {
        "raw_code": "".join(str(bit) for bit in bits),
        "sensor_code": first_one,
        "bubble_count": bubble_count,
        "transition_count": transition_count,
        "code_valid": bubble_count == 0 and transition_count <= 1,
    }


def candidate_metrics(
    group_rows: Sequence[Dict[str, str]], config: Dict[str, Any], m_stages: int, dummy_load_count: int
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Evaluate every configured offset and guard for one physical topology."""

    anchors = {
        "nominal": float(config["vnom_v"]),
        "last_passing": float(config["timing_anchor"]["last_passing_voltage_v"]),
        "first_violation": float(config["timing_anchor"]["first_violation_voltage_v"]),
    }
    nominal_row = closest_row(group_rows, anchors["nominal"], "M{} dummy{} nominal".format(m_stages, dummy_load_count))
    offset_pairs = launch_offsets(nominal_row, m_stages, config["ideal_launch_code_offsets"])
    guard_values = [float(value) * 1.0e-12 for value in config["ideal_setup_guards_ps"]]
    detailed = []
    candidates = []
    ordered_rows = sorted(group_rows, key=lambda row: finite_float(row, "vdd_a_v", row["scenario_id"]), reverse=True)
    for multiplier, launch_offset_s in offset_pairs:
        by_guard: Dict[float, List[Dict[str, Any]]] = {}
        for guard_s in guard_values:
            decoded_rows = []
            for row in ordered_rows:
                sense, reference = arrivals(row, m_stages)
                decoded = decode_one(sense, reference, launch_offset_s, guard_s)
                decoded.update(
                    {
                        "scenario_id": row["scenario_id"],
                        "m_stages": m_stages,
                        "dummy_load_count": dummy_load_count,
                        "vdd_a_v": finite_float(row, "vdd_a_v", row["scenario_id"]),
                        "launch_offset_multiplier": multiplier,
                        "launch_offset_s": launch_offset_s,
                        "setup_guard_ps": guard_s * 1.0e12,
                    }
                )
                decoded_rows.append(decoded)
            detailed.extend(decoded_rows)
            by_guard[guard_s] = decoded_rows
        zero_guard = by_guard[0.0]
        def anchor_metric(name: str) -> Dict[str, Any]:
            matches = [item for item in zero_guard if abs(item["vdd_a_v"] - anchors[name]) <= 1.0e-12]
            if len(matches) != 1:
                raise ValueError("missing zero-guard {} metric".format(name))
            return matches[0]
        nominal = anchor_metric("nominal")
        last_passing = anchor_metric("last_passing")
        failing = anchor_metric("first_violation")
        monotonic = all(
            zero_guard[index + 1]["sensor_code"] >= zero_guard[index]["sensor_code"]
            for index in range(len(zero_guard) - 1)
        )
        all_valid = all(item["code_valid"] for item in zero_guard)
        code_delta = failing["sensor_code"] - nominal["sensor_code"]
        center_margin = min(nominal["sensor_code"], m_stages - nominal["sensor_code"])
        total_avg_current = finite_float(nominal_row, "sense_avg_current_a", nominal_row["scenario_id"]) + finite_float(nominal_row, "ref_avg_current_a", nominal_row["scenario_id"])
        total_peak_current = finite_float(nominal_row, "sense_peak_current_a", nominal_row["scenario_id"]) + finite_float(nominal_row, "ref_peak_current_a", nominal_row["scenario_id"])
        checks = {
            "nominal_midpoint": abs(nominal["sensor_code"] - m_stages // 2) <= 1,
            "center_margin_at_least_quarter_scale": center_margin >= m_stages * 0.25,
            "code_monotonic_vs_decreasing_vdd": monotonic,
            "all_zero_guard_codes_valid": all_valid,
            "first_violation_delta_at_least_minimum": code_delta >= int(config["minimum_fail_code_delta"]),
        }
        candidates.append(
            {
                "candidate_id": "m{:02d}_d{}_offset_{:+.1f}".format(m_stages, dummy_load_count, multiplier),
                "m_stages": m_stages,
                "dummy_load_count": dummy_load_count,
                "launch_offset_multiplier": multiplier,
                "launch_offset_s": launch_offset_s,
                "nominal_code": nominal["sensor_code"],
                "last_passing_code": last_passing["sensor_code"],
                "first_violation_code": failing["sensor_code"],
                "first_violation_code_delta": code_delta,
                "center_margin": center_margin,
                "total_nominal_avg_current_a": total_avg_current,
                "total_nominal_peak_current_a": total_peak_current,
                "checks": checks,
                "feasible": all(checks.values()),
                "guard_sensitivity": {
                    "guard_5ps_first_violation_code": anchor_from_rows(by_guard.get(5.0e-12), anchors["first_violation"]),
                    "guard_10ps_first_violation_code": anchor_from_rows(by_guard.get(10.0e-12), anchors["first_violation"]),
                },
            }
        )
    return detailed, candidates


def anchor_from_rows(rows: Sequence[Dict[str, Any]], voltage_v: float) -> int:
    """Return one guard-sensitivity anchor code and reject an incomplete table."""

    if rows is None:
        return -1
    matches = [row for row in rows if abs(row["vdd_a_v"] - voltage_v) <= 1.0e-12]
    if len(matches) != 1:
        raise ValueError("guard sensitivity table lacks exact voltage {}".format(voltage_v))
    return int(matches[0]["sensor_code"])


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    """Export all ideal-code decisions for review and later plot generation."""

    fields = [
        "scenario_id", "m_stages", "dummy_load_count", "vdd_a_v", "launch_offset_multiplier", "launch_offset_s",
        "setup_guard_ps", "raw_code", "sensor_code", "bubble_count", "transition_count", "code_valid",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})


def rank_key(candidate: Dict[str, Any], target_delta: int) -> Tuple[Any, ...]:
    """Apply the specified ranking: separation, margin, simpler topology, power."""

    return (
        0 if candidate["first_violation_code_delta"] >= target_delta else 1,
        -candidate["center_margin"],
        candidate["dummy_load_count"],
        candidate["m_stages"],
        candidate["total_nominal_avg_current_a"],
        candidate["total_nominal_peak_current_a"],
        abs(candidate["first_violation_code_delta"] - target_delta),
    )


def write_report(path: Path, result: Dict[str, Any]) -> None:
    """Write the candidate decision and every acceptance predicate in Markdown."""

    lines = [
        "# 765 MHz Ideal Vernier Candidate Selection",
        "",
        "status={}".format(result["status"]),
        "",
        "| Candidate | M | Dummy | Offset (ps) | C0 | C35 | C40 | Delta C40-C0 | Margin | Feasible |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for candidate in result["candidates"]:
        lines.append(
            "| {candidate_id} | {m_stages} | {dummy_load_count} | {offset:.6f} | {nominal_code} | "
            "{last_passing_code} | {first_violation_code} | {first_violation_code_delta} | {center_margin} | {feasible} |".format(
                offset=candidate["launch_offset_s"] * 1.0e12, **candidate
            )
        )
    lines.extend(["", "## Selected candidates", ""])
    for candidate in result["selected_candidates"]:
        lines.append("- `{}`".format(candidate["candidate_id"]))
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_argument_parser() -> argparse.ArgumentParser:
    """Define explicit raw-evidence and compact-output paths."""

    parser = argparse.ArgumentParser(description="analyze Phase-2 ideal Vernier arrivals")
    parser.add_argument("--config", required=True, type=Path, help="Phase 2 configuration")
    parser.add_argument("--input-csv", required=True, type=Path, help="raw HSPICE arrival CSV")
    parser.add_argument("--output-csv", required=True, type=Path, help="expanded ideal-code CSV")
    parser.add_argument("--selection-json", required=True, type=Path, help="candidate-selection JSON")
    parser.add_argument("--selection-report", required=True, type=Path, help="candidate-selection Markdown")
    return parser


def main(argv: Iterable[str] = None) -> int:
    """Decode every actual arrival point and retain the best three candidates."""

    args = build_argument_parser().parse_args(argv)
    config = load_json(args.config)
    rows = read_rows(args.input_csv)
    groups: Dict[Tuple[int, int], List[Dict[str, str]]] = {}
    for row in rows:
        key = (int(row["m_stages"]), int(row["dummy_load_count"]))
        groups.setdefault(key, []).append(row)
    detailed: List[Dict[str, Any]] = []
    candidates: List[Dict[str, Any]] = []
    for (m_stages, dummy_load_count), group_rows in sorted(groups.items()):
        group_detailed, group_candidates = candidate_metrics(group_rows, config, m_stages, dummy_load_count)
        detailed.extend(group_detailed)
        candidates.extend(group_candidates)
    feasible = [candidate for candidate in candidates if candidate["feasible"]]
    selected = sorted(feasible, key=lambda candidate: rank_key(candidate, int(config["target_fail_code_delta"])))[:3]
    result = {
        "schema_version": 1,
        "source_csv": str(args.input_csv.resolve()),
        "status": "PASS" if len(selected) == 3 else "NO_FEASIBLE_IDEAL_CANDIDATE",
        "selected_candidates": selected,
        "candidates": candidates,
    }
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_csv, detailed)
    args.selection_json.parent.mkdir(parents=True, exist_ok=True)
    args.selection_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(args.selection_report, result)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
