#!/usr/bin/env python3
"""Publish the corrected-direction CAL0 capture-safe-window Gate."""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Set

from run_bfe2_cal0_capture_safe import (  # noqa: E402
    CAL0_ROOT,
    EPS_PS,
    MANIFEST_PATH,
    NOMINAL_G_CLOSE_PS,
    NORMAL_SCENARIO,
    OFFLINE_PATH,
    POINTS,
    ROOT,
    RUN_ROOT,
    SOURCE_LEDGER_PATH,
    TAP_COUNT,
    THRESHOLD_V,
    VDD_SAFE,
    load_json,
    load_rows,
    pair_q_events,
    q_event_stream,
    sha256,
)


def analyze_point(label: str, close_ps: float, interval: Dict[str, Any], ledger: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze one existing CAL0 XA point with Q-derived event direction."""

    directory = RUN_ROOT / "cal0_vcs_xa" / label.lower()
    rows = load_rows(directory / "xa_boundary_samples.csv")
    taps: List[Dict[str, Any]] = []
    for tap in range(TAP_COUNT):
        crossings = list(ledger["tap_{:02d}".format(tap)]["crossings"])
        events = pair_q_events(q_event_stream(rows, tap), crossings)
        postclose = [event for event in events if event["time_ps"] > close_ps + EPS_PS]
        source_free = [event for event in postclose if event["classification"] == "source-free"]
        postclose_source = [event for event in postclose if event["source_event"] is not None and event["source_event"]["time_ps"] > close_ps + EPS_PS]
        final = next(row for row in rows if row["kind"] == "final" and row["tap"] == tap)
        tail = next(row for row in rows if row["kind"] == "tail_1ns" and row["tap"] == tap)
        taps.append({
            "tap": tap,
            "post_close_q_events": postclose,
            "source_free_reflip": bool(source_free),
            "post_close_safe_d_changed_q": bool(postclose_source),
            "unresolved": len(postclose) > 1,
            "final_q_v": final["q_v"],
            "final_mid_rail": 0.095 < final["q_v"] < 0.855,
            "tail_q_v": tail["q_v"],
            "tail_stable": abs(final["q_v"] - tail["q_v"]) <= 1.0e-5,
        })
    code = "".join("1" if tap["final_q_v"] > THRESHOLD_V else "0" for tap in taps)
    return {
        "point": label,
        "selected_sample_close_ps": float(interval["selected_sample_close_ps"]),
        "selected_g_close_ps": close_ps,
        "START": float(interval["start_ps"]),
        "END": float(interval["end_ps"]),
        "LEN": float(interval["len_ps"]),
        "CENTER": float(interval["center_ps"]),
        "LEFT_HEADROOM": float(interval["left_headroom_ps"]),
        "RIGHT_HEADROOM": float(interval["right_headroom_ps"]),
        "final_q_code": code,
        "final_ones": code.count("1"),
        "source_free_reflip_taps": [tap["tap"] for tap in taps if tap["source_free_reflip"]],
        "unresolved_taps": [tap["tap"] for tap in taps if tap["unresolved"]],
        "mid_rail_taps": [tap["tap"] for tap in taps if tap["final_mid_rail"]],
        "unstable_tail_taps": [tap["tap"] for tap in taps if not tap["tail_stable"]],
        "post_close_safe_d_changed_q_taps": [tap["tap"] for tap in taps if tap["post_close_safe_d_changed_q"]],
        "final_q_stable": all(tap["tail_stable"] for tap in taps),
        "capture_semantics_pass": not any(tap["source_free_reflip"] or tap["unresolved"] or tap["final_mid_rail"] or tap["post_close_safe_d_changed_q"] or not tap["tail_stable"] for tap in taps),
        "tap27": taps[27],
        "taps24_29": taps[24:30],
        "taps": taps,
        "boundary_csv_sha256": sha256(directory / "xa_boundary_samples.csv"),
    }


def main() -> int:
    """Publish analysis/report/Gate and stop without launching simulation."""

    manifest = load_json(MANIFEST_PATH)
    offline = load_json(OFFLINE_PATH)
    if manifest.get("source_waveform") != NORMAL_SCENARIO or manifest.get("l2_used") is not False or manifest.get("new_physical_scenarios") != 0:
        raise ValueError("capture-safe manifest is not normal-only offline evidence")
    if sha256(OFFLINE_PATH) != manifest.get("offline_sha256"):
        raise ValueError("capture-safe offline artifact changed")
    ledger = load_json(SOURCE_LEDGER_PATH)
    old_manifest = load_json(CAL0_ROOT / "BFE2_CAL0_SCENARIO_MANIFEST.json")
    point_map = {item["point"]: item for item in old_manifest["scenarios"]}
    old_offline = load_json(CAL0_ROOT / "BFE2_CAL0_OFFLINE_INTERVALS.json")
    results = [analyze_point(label, float(point_map[label]["selected_g_close_ps"]), old_offline["selected_intervals"][index], ledger) for index, label in enumerate(POINTS)]
    safe_intervals = offline.get("capture_safe_intervals", [])
    selected_points = offline.get("selected_capture_safe_points", [])
    safe_results: List[Dict[str, Any]] = []
    safe_ones = [result["final_ones"] for result in safe_results]
    local_monotonic = len(safe_ones) >= 2 and (all(a <= b for a, b in zip(safe_ones, safe_ones[1:])) or all(a >= b for a, b in zip(safe_ones, safe_ones[1:]))) and len(set(safe_ones)) > 1
    capture_safe_verified = len(selected_points) >= 2 and all(result["capture_semantics_pass"] for result in safe_results)
    gate = "BFE2_CAL0_CAPTURE_SAFE_WINDOW_READY" if capture_safe_verified and local_monotonic else "BFE2_CAL0_CAPTURE_SAFE_WINDOW_BLOCKED"
    if not safe_intervals:
        blocking_reason = "NO_CAPTURE_SAFE_INTERVALS_NEAR_NOMINAL"
    elif len(selected_points) < 2:
        blocking_reason = "FEWER_THAN_TWO_CAPTURE_SAFE_POINTS"
    elif not capture_safe_verified:
        blocking_reason = "CAPTURE_SEMANTICS_FAIL_ON_SELECTED_POINTS"
    else:
        blocking_reason = "NO_LOCAL_MONOTONIC_FEATURE"
    analysis = {
        "schema_version": 1,
        "stage": manifest["stage"],
        "gate": gate,
        "blocking_reason": blocking_reason,
        "source_waveform": NORMAL_SCENARIO,
        "l2_used": False,
        "fixed_nominal_sample_close_ps": 534.524618567,
        "fixed_nominal_g_close_ps": NOMINAL_G_CLOSE_PS,
        "q_event_direction_rule": "Q state before/after; safe_d_v is not used",
        "capture_safe_intervals": safe_intervals,
        "selected_capture_safe_points": selected_points,
        "new_physical_scenarios": 0,
        "simulation_run": False,
        "capture_safe_verified": capture_safe_verified,
        "local_monotonic_feature": local_monotonic,
        "results": results,
        "corrected_direction_examples": {
            "LEFT_tap27": results[0]["tap27"]["post_close_q_events"],
            "RIGHT_tap29": results[2]["taps"][29]["post_close_q_events"],
        },
        "flight_evidence": offline["flight_evidence"],
        "source_ledger_sha256": sha256(SOURCE_LEDGER_PATH),
        "offline_sha256": sha256(OFFLINE_PATH),
        "manifest_sha256": sha256(MANIFEST_PATH),
        "stop_after_stage": True,
        "next_stage_authorized": False,
    }
    analysis_path = ROOT / "BFE2_CAL0_CAPTURE_SAFE_ANALYSIS.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# B-FE2-CAL0 capture-safe repair report",
        "",
        "Gate: `{}`".format(gate),
        "Blocking reason: `{}`.".format(blocking_reason),
        "",
        "Normal-only 0.95 V evidence; no L2, no dense sweep, no circuit/geometry/control change.",
        "The old event-free intervals were re-evaluated by subtracting measured per-tap D→Q in-flight windows.",
        "Q event direction is derived from Q state before/after each event; safe_d_v is not used for direction.",
        "",
        "| Legacy point | sample_close (ps) | G close (ps) | START | END | LEN | CENTER | LEFT/RIGHT_HEADROOM | Q[29:0] | Ones | Corrected source-free | Corrected unresolved | mid-rail | tail | post-close safe_d→Q |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|---:|---|---|---|---|---|",
    ]
    for result in results:
        lines.append("| {} | {:.9f} | {:.9f} | {:.9f} | {:.9f} | {:.9f} | {:.9f} | {:.9f}/{:.9f} | `{}` | {} | {} | {} | {} | {} | {} |".format(result["point"], result["selected_sample_close_ps"], result["selected_g_close_ps"], result["START"], result["END"], result["LEN"], result["CENTER"], result["LEFT_HEADROOM"], result["RIGHT_HEADROOM"], result["final_q_code"], result["final_ones"], result["source_free_reflip_taps"], result["unresolved_taps"], result["mid_rail_taps"], result["unstable_tail_taps"], result["post_close_safe_d_changed_q_taps"]))
    lines += [
        "",
        "Capture-safe intervals in the old LEFT/CENTER/RIGHT local envelope: `{}`.".format(safe_intervals),
        "Selected capture-safe points: `{}`; new VCS+XA scenarios launched: `0`.".format(selected_points),
        "",
        "Corrected LEFT tap27 events: `{}`.".format(results[0]["tap27"]["post_close_q_events"]),
        "Corrected RIGHT tap29 events: `{}`.".format(results[2]["taps"][29]["post_close_q_events"]),
        "",
        "The in-flight windows overlap across the nominal neighborhood, so no representative point was eligible for a new XA run. This repair stage stops here; no self-calibration, runtime detection, FSM, M/F reuse, or later phase is authorized.",
    ]
    report_path = ROOT / "BFE2_CAL0_CAPTURE_SAFE_REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    gate_doc = {
        "stage": manifest["stage"],
        "gate": gate,
        "blocking_reason": blocking_reason,
        "capture_safe_verified": capture_safe_verified,
        "local_monotonic_feature": local_monotonic,
        "new_physical_scenarios": 0,
        "analysis_sha256": sha256(analysis_path),
        "report_sha256": sha256(report_path),
        "stop_after_stage": True,
        "next_stage_authorized": False,
    }
    gate_path = ROOT / "BFE2_CAL0_CAPTURE_SAFE_GATE.json"
    gate_path.write_text(json.dumps(gate_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(gate_doc, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
