#!/usr/bin/env python3
"""Analyze saved B-FE2.1 transparent-latch load waveforms without HSPICE."""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_bfe1_spatial as spatial  # noqa: E402  # Retain the frozen local-rail RAW_CODE definition.
import bfe1_frontend  # noqa: E402
import bfe2_latch_load  # noqa: E402


RUN_ROOT = bfe2_latch_load.RUN_ROOT
OUTPUT_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "latch_load"
BFE1_PAIRWISE = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe1_spatial_observability" / "normal_l2_pairwise_discrimination.json"


def read_json(path: Path) -> Dict[str, Any]:
    """Read one compact JSON source and reject unexpected shapes."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def scenario_trace(scenario_id: str) -> Mapping[str, Any]:
    """Load the one immutable transient trace for a formal B-FE2.1 scenario."""

    return bfe1_frontend.parse_ascii_tr0(bfe2_latch_load.scenario_dir(RUN_ROOT, scenario_id) / "bfe2l.tr0")


def node_events(trace: Mapping[str, Any], node: str) -> List[Dict[str, Any]]:
    """Return one chronologically ordered local-rail crossing list for ``node``.

    The B-FE2 latch is powered from the monitored rail, so a data or Q event
    is defined against the same instantaneous VDD/2 threshold as the frozen
    spatial-code analysis.  Keeping the direction together with the time is
    important here: a falling D event may only be paired to a falling Q
    event, never to a merely nearby rising event.
    """

    crossings = spatial.crossing_events(trace, node)
    events = [{"time_ps": time_ps, "direction": "rise"} for time_ps in crossings["rise_ps"]]
    events.extend({"time_ps": time_ps, "direction": "fall"} for time_ps in crossings["fall_ps"])
    return sorted(events, key=lambda item: item["time_ps"])


def pair_transparent_d_to_q(trace: Mapping[str, Any], tap: int) -> Dict[str, Any]:
    """Measure transparent-mode D→Q propagation for one physical latch tap.

    B-FE2.1 holds G high for the entire observation.  Its saved trace is thus
    the only valid measurement of this exact latch bank's transparent D→Q
    delay; no Liberty number is fabricated when a table is unavailable at the
    required 0.95-V condition.  Events are greedily paired in time order with
    the first later Q crossing of the same direction.  That deliberately
    conservative rule leaves an ambiguous event unpaired instead of claiming
    a causal delay that the waveform cannot support.
    """

    d_events = node_events(trace, "xor_{}".format(tap))
    q_events = node_events(trace, "q_{}".format(tap))
    consumed_q = set()
    pairs, unmatched_d = [], []
    for d_index, d_event in enumerate(d_events):
        match_index = next((q_index for q_index, q_event in enumerate(q_events)
                            if q_index not in consumed_q and
                            q_event["direction"] == d_event["direction"] and
                            q_event["time_ps"] >= d_event["time_ps"] - spatial.EPSILON_PS), None)
        if match_index is None:
            unmatched_d.append({"event_index": d_index, **d_event})
            continue
        q_event = q_events[match_index]
        consumed_q.add(match_index)
        pairs.append({
            "d_event_index": d_index,
            "q_event_index": match_index,
            "direction": d_event["direction"],
            "d_cross_ps": d_event["time_ps"],
            "q_cross_ps": q_event["time_ps"],
            "d_to_q_delay_ps": q_event["time_ps"] - d_event["time_ps"],
        })
    unmatched_q = [{"event_index": index, **event} for index, event in enumerate(q_events)
                   if index not in consumed_q]
    return {"tap": tap, "d_events": d_events, "q_events": q_events,
            "matched_d_to_q_events": pairs, "unmatched_d_events": unmatched_d,
            "unmatched_q_events": unmatched_q}


def q_snapshot(trace: Mapping[str, Any], sample_ps: float) -> Dict[str, Any]:
    """Classify the complete physical Q word at one launch-relative time.

    This mirrors the XOR RAW_CODE convention but intentionally reads latch Q.
    It makes a Q-code interval auditable without confusing transparent D data
    with the stable word that a later G-close experiment needs to preserve.
    """

    absolute_s = (spatial.LAUNCH_PS + sample_ps) * 1.0e-12
    times = trace["columns"]["time"]
    rail = spatial.interpolate(times, trace["columns"][bfe1_frontend.label_for("vdd_monitored")], absolute_s)
    bits, margins = [], []
    for index in range(30):
        voltage = spatial.interpolate(times, trace["columns"][bfe1_frontend.label_for("q_{}".format(index))], absolute_s)
        bits.append(1 if voltage > 0.5 * rail else 0)
        margins.append(abs(voltage - 0.5 * rail))
    result = spatial.code_metrics(bits)
    result.update({"sample_ps": sample_ps, "minimum_bit_margin_v": min(margins),
                   "undefined_bit_count": sum(margin <= spatial.UNDEFINED_MARGIN_V for margin in margins)})
    return result


def q_code_intervals(trace: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Return all piecewise-constant Q-code regions in the transparent trace.

    A region is called stable only in the literal waveform sense: no measured
    Q threshold crossing occurs inside its open interval.  The interval list
    retains empty and fragmented words as evidence; consumers select only
    clean interior regions rather than repairing a spatial code.
    """

    boundaries = [0.0, spatial.STOP_PS - spatial.LAUNCH_PS]
    for index in range(30):
        events = spatial.crossing_events(trace, "q_{}".format(index))
        boundaries.extend(events["rise_ps"] + events["fall_ps"])
    edges = spatial.unique_boundaries(boundaries)
    intervals = []
    for left, right in zip(edges[:-1], edges[1:]):
        if right - left <= spatial.EPSILON_PS:
            continue
        code = q_snapshot(trace, (left + right) / 2.0)
        code.update({"interval_start_ps": left, "interval_end_ps": right,
                     "interval_width_ps": right - left, "q_crossings_inside": 0})
        intervals.append(code)
    return intervals


def transparent_latch_timing(trace: Mapping[str, Any], scenario_id: str) -> Dict[str, Any]:
    """Publish per-tap propagation and the Q-code stability regions for B-FE2.2R.

    The output is purposefully a separate artifact from XOR intervals.  An
    XOR RAW_CODE platform can begin before its last associated Q transition,
    which is exactly the root-cause distinction being checked in B-FE2.2R.
    """

    per_tap = [pair_transparent_d_to_q(trace, tap) for tap in range(30)]
    intervals = q_code_intervals(trace)
    clean = [item for item in intervals if item["undefined_bit_count"] == 0 and
             not item["empty"] and not item["fragmented"] and
             not item["touches_left"] and not item["touches_right"]]
    return {"scenario_id": scenario_id,
            "threshold": "instantaneous VDD_MONITORED/2",
            "g_mode": "continuously high; transparent latch reference",
            "per_tap": per_tap,
            "q_code_intervals": intervals,
            "clean_interior_q_stable_intervals": clean}


def scenario_analysis(scenario: Mapping[str, Any]) -> Tuple[Dict[str, Any], Mapping[str, Any]]:
    """Reconstruct crossings and RAW_CODE intervals from one saved load trace."""

    trace = scenario_trace(scenario["scenario_id"])
    crossings, boundaries = {}, [0.0, spatial.STOP_PS - spatial.LAUNCH_PS]
    for index in range(30):
        node = "xor_{}".format(index)
        crossings[node] = spatial.crossing_events(trace, node)
        boundaries.extend(crossings[node]["rise_ps"] + crossings[node]["fall_ps"])
    intervals = []
    for left, right in zip(spatial.unique_boundaries(boundaries)[:-1], spatial.unique_boundaries(boundaries)[1:]):
        if right - left <= spatial.EPSILON_PS:
            continue
        item = spatial.snapshot(trace, (left + right) / 2.0)
        item.update({"interval_start_ps": left, "interval_end_ps": right, "interval_width_ps": right - left})
        intervals.append(item)
    return {"scenario_id": scenario["scenario_id"], "baseline_v": scenario["baseline_v"], "droop_v": scenario["droop_v"], "phase_ps": scenario["phase_ps"], "xor_crossings": crossings, "rvt_monotonicity": spatial.path_monotonicity(trace, "rvt"), "lvt_monotonicity": spatial.path_monotonicity(trace, "lvt"), "intervals": intervals}, trace


def pairwise(normal: Mapping[str, Any], normal_trace: Mapping[str, Any], l2: Mapping[str, Any], l2_trace: Mapping[str, Any]) -> Dict[str, Any]:
    """Compare normal/L2 only at common physical XOR-boundary segments."""

    boundaries = [0.0, spatial.STOP_PS - spatial.LAUNCH_PS]
    for scenario in (normal, l2):
        for event in scenario["xor_crossings"].values():
            boundaries.extend(event["rise_ps"] + event["fall_ps"])
    candidates, records = [], []
    edges = spatial.unique_boundaries(boundaries)
    for left, right in zip(edges[:-1], edges[1:]):
        if right - left <= spatial.EPSILON_PS:
            continue
        sample = (left + right) / 2.0
        ncode, lcode = spatial.snapshot(normal_trace, sample), spatial.snapshot(l2_trace, sample)
        item = {"interval_start_ps": left, "interval_end_ps": right, "interval_width_ps": right-left, "normal": ncode, "l2": lcode,
                "hamming_distance": sum(a != b for a, b in zip(ncode["raw_code"], lcode["raw_code"])),
                "delta_start": None if ncode["start"] is None or lcode["start"] is None else lcode["start"]-ncode["start"],
                "delta_end": None if ncode["end"] is None or lcode["end"] is None else lcode["end"]-ncode["end"],
                "delta_len": lcode["len"]-ncode["len"], "delta_center": None if ncode["center"] is None or lcode["center"] is None else lcode["center"]-ncode["center"]}
        item["common_discrimination_platform"] = (ncode["undefined_bit_count"] == 0 and lcode["undefined_bit_count"] == 0 and not ncode["empty"] and not lcode["empty"] and not ncode["touches_left"] and not ncode["touches_right"] and not lcode["touches_left"] and not lcode["touches_right"] and not ncode["fragmented"] and not lcode["fragmented"] and item["hamming_distance"] > 0)
        records.append(item)
        if item["common_discrimination_platform"]:
            candidates.append(item)
    return {"baseline_v": normal["baseline_v"], "normal_scenario": normal["scenario_id"], "l2_scenario": l2["scenario_id"], "common_segments": records, "candidate_platforms": candidates, "largest_platform": max(candidates, key=lambda item: item["interval_width_ps"]) if candidates else None}


def load_shift(pair: Mapping[str, Any], bfe1_pairs: Mapping[str, Any]) -> Dict[str, Any]:
    """Report the movement relative to B-FE1 without requiring equal windows."""

    old = next(item for item in bfe1_pairs["pairs"] if item["baseline_v"] == pair["baseline_v"])["largest_platform"]
    new = pair["largest_platform"]
    return {"baseline_v": pair["baseline_v"], "bfe1_largest_platform": old, "bfe2_largest_platform": new,
            "platform_start_shift_ps": None if new is None else new["interval_start_ps"] - old["interval_start_ps"],
            "platform_end_shift_ps": None if new is None else new["interval_end_ps"] - old["interval_end_ps"]}


def decide_gate(pairs: List[Mapping[str, Any]], scenarios: List[Mapping[str, Any]]) -> Dict[str, Any]:
    """Apply the bounded B-FE2.1 GO/CONDITIONAL/BLOCKED decision."""

    monotonic = all(item["rvt_monotonicity"]["strictly_monotonic"] and item["lvt_monotonicity"]["strictly_monotonic"] for item in scenarios)
    clean = [item for item in pairs if item["candidate_platforms"]]
    if monotonic and len(clean) == 2:
        gate, reason = "BFE2_1_LATCH_LOAD_GO", "both formal baselines retain clean positive-width spatial discrimination under 30 real latch D loads"
    elif any(item["candidate_platforms"] for item in pairs):
        gate, reason = "BFE2_1_LATCH_LOAD_CONDITIONAL", "some spatial mechanism remains but at least one baseline lacks a clean common platform or monotonicity"
    else:
        gate, reason = "BFE2_1_LATCH_LOAD_BLOCKED", "real latch D-input loading removes clean distinguishable spatial codes"
    return {"schema_version": 2, "stage": "B-FE2.1", "gate": gate, "reason": reason,
            # Four HSPICE scenarios were executed to create the immutable
            # source traces.  This analyzer itself performs zero simulations;
            # retain both quantities so a derived-analysis rerun cannot erase
            # the physical-run accounting.
            "executed_new_hspice_scenarios": 4,
            "this_analysis_new_hspice_scenarios": 0,
            "all_path_monotonic": monotonic, "clean_pair_count": len(clean), "pair_count": len(pairs), "real_latch_d_input_load": True}


def main() -> int:
    """Generate B-FE2.1 results entirely from the completed four traces."""

    manifest = read_json(OUTPUT_ROOT / "BFE2_1_SCENARIO_MANIFEST.json")
    if len(manifest.get("scenarios", [])) != 4:
        raise ValueError("B-FE2.1 analysis requires exactly four retained scenarios")
    scenarios, traces, latch_timing = [], {}, []
    for source in manifest["scenarios"]:
        result, trace = scenario_analysis(source)
        scenarios.append(result); traces[result["scenario_id"]] = trace
        latch_timing.append(transparent_latch_timing(trace, result["scenario_id"]))
    by_id = {item["scenario_id"]: item for item in scenarios}
    pairs = [pairwise(by_id["BFE2L-095-N"], traces["BFE2L-095-N"], by_id["BFE2L-095-L2"], traces["BFE2L-095-L2"]), pairwise(by_id["BFE2L-110-N"], traces["BFE2L-110-N"], by_id["BFE2L-110-L2"], traces["BFE2L-110-L2"])]
    shifts = [load_shift(pair, read_json(BFE1_PAIRWISE)) for pair in pairs]
    gate = decide_gate(pairs, scenarios)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "BFE2_1_SPATIAL_INTERVALS.json").write_text(json.dumps({"scenarios": scenarios}, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    (OUTPUT_ROOT / "BFE2_1_PAIRWISE_DISCRIMINATION.json").write_text(json.dumps({"pairs": pairs, "load_shifts": shifts}, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    (OUTPUT_ROOT / "BFE2_1_TRANSPARENT_DQ_TIMING.json").write_text(json.dumps({
        "schema_version": 1, "stage": "B-FE2.1", "source": "four retained transparent-latch .tr0 traces",
        "new_hspice_scenarios": 0, "scenarios": latch_timing}, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    (OUTPUT_ROOT / "BFE2_1_GATE_STATUS.json").write_text(json.dumps(gate, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(gate["gate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
