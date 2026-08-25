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
    return {"schema_version": 1, "stage": "B-FE2.1", "gate": gate, "reason": reason, "new_hspice_scenarios": 0, "all_path_monotonic": monotonic, "clean_pair_count": len(clean), "pair_count": len(pairs), "real_latch_d_input_load": True}


def main() -> int:
    """Generate B-FE2.1 results entirely from the completed four traces."""

    manifest = read_json(OUTPUT_ROOT / "BFE2_1_SCENARIO_MANIFEST.json")
    if len(manifest.get("scenarios", [])) != 4:
        raise ValueError("B-FE2.1 analysis requires exactly four retained scenarios")
    scenarios, traces = [], {}
    for source in manifest["scenarios"]:
        result, trace = scenario_analysis(source)
        scenarios.append(result); traces[result["scenario_id"]] = trace
    by_id = {item["scenario_id"]: item for item in scenarios}
    pairs = [pairwise(by_id["BFE2L-095-N"], traces["BFE2L-095-N"], by_id["BFE2L-095-L2"], traces["BFE2L-095-L2"]), pairwise(by_id["BFE2L-110-N"], traces["BFE2L-110-N"], by_id["BFE2L-110-L2"], traces["BFE2L-110-L2"])]
    shifts = [load_shift(pair, read_json(BFE1_PAIRWISE)) for pair in pairs]
    gate = decide_gate(pairs, scenarios)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "BFE2_1_SPATIAL_INTERVALS.json").write_text(json.dumps({"scenarios": scenarios}, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    (OUTPUT_ROOT / "BFE2_1_PAIRWISE_DISCRIMINATION.json").write_text(json.dumps({"pairs": pairs, "load_shifts": shifts}, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    (OUTPUT_ROOT / "BFE2_1_GATE_STATUS.json").write_text(json.dumps(gate, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(gate["gate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
