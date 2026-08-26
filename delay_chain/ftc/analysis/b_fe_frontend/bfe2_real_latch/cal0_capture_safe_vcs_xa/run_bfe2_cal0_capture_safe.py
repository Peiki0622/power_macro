#!/usr/bin/env python3
"""Rebuild B-FE2-CAL0 close windows using measured Q-flight evidence.

This repair stage is intentionally offline-only for the present evidence set.
It reads the existing L1A-R and CAL0 XA boundary data, derives Q transition
direction from Q's own state sequence, extracts measured D-to-Q flight ranges,
and subtracts those in-flight windows from the old event-free intervals.  If
no legal capture-safe interval remains, no new physical scenario is launched.
"""

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set, Tuple


ROOT = Path(__file__).resolve().parent
CAL0_ROOT = ROOT.parent / "cal0_vcs_xa"
L1AR_ROOT = ROOT.parent / "l1a_r_vcs_xa"
FTC_ROOT = ROOT.parents[3]
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch"
SOURCE_LEDGER_PATH = RUN_ROOT / "l1a_r_vcs_xa" / "bfe2l_095_n" / "safe_d_crossing_ledger.json"
CAL0_MANIFEST_PATH = CAL0_ROOT / "BFE2_CAL0_SCENARIO_MANIFEST.json"
CAL0_ANALYSIS_PATH = CAL0_ROOT / "BFE2_CAL0_ANALYSIS.json"
OFFLINE_PATH = ROOT / "BFE2_CAL0_CAPTURE_SAFE_OFFLINE.json"
MANIFEST_PATH = ROOT / "BFE2_CAL0_CAPTURE_SAFE_MANIFEST.json"
NORMAL_SCENARIO = "BFE2L-095-N"
STAGE = "B-FE2-CAL0-CAPTURE-SAFE"
NOMINAL_SAMPLE_CLOSE_PS = 534.524618567
NOMINAL_G_CLOSE_PS = 1534.524618567
VDD_SAFE = 0.95
THRESHOLD_V = 0.5 * VDD_SAFE
EPS_PS = 1.0e-6
MAX_DQ_PS = 100.0
TAP_COUNT = 30
POINTS = ("LEFT", "CENTER", "RIGHT")


def sha256(path: Path) -> str:
    """Hash a retained evidence artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    """Read one object-shaped JSON artifact."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def load_rows(path: Path) -> List[Dict[str, Any]]:
    """Parse one retained XA boundary CSV."""

    rows: List[Dict[str, Any]] = []
    with path.open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            row["tap"] = int(row["tap"])
            for key in ("time_ps", "safe_d_v", "q_v", "vdd_sense_v", "vdd_safe_v", "g_v"):
                row[key] = float(row[key])
            rows.append(row)
    return rows


def validate_frozen_inputs() -> Dict[str, Any]:
    """Validate that CAL0-CAPTURE-SAFE consumes only frozen normal evidence."""

    manifest = load_json(CAL0_MANIFEST_PATH)
    if manifest.get("source_waveform") != NORMAL_SCENARIO or manifest.get("l2_used") is not False:
        raise ValueError("capture-safe repair requires normal-only CAL0 evidence")
    if abs(float(manifest.get("nominal_sample_close_ps")) - NOMINAL_SAMPLE_CLOSE_PS) > EPS_PS:
        raise ValueError("nominal sample_close drifted")
    if abs(float(manifest.get("nominal_g_close_ps")) - NOMINAL_G_CLOSE_PS) > EPS_PS:
        raise ValueError("nominal G close drifted")
    if manifest.get("tap_count") != TAP_COUNT or manifest.get("latch_cell") != "LATQ_X0P5M_A9TR40":
        raise ValueError("CAL0 frozen latch/tap contract changed")
    if manifest.get("sensing_geometry_modified") is not False:
        raise ValueError("CAL0 sensing geometry is not frozen")
    if not SOURCE_LEDGER_PATH.is_file():
        raise FileNotFoundError("accepted normal safe_d ledger is missing")
    return manifest


def q_event_stream(rows: Sequence[Mapping[str, Any]], tap: int) -> List[Dict[str, Any]]:
    """Return Q events with direction derived only from Q state before/after."""

    events = sorted((row for row in rows if row["kind"] == "q_event" and int(row["tap"]) == tap), key=lambda row: (row["time_ps"], row["q_v"]))
    time_zero = [row for row in events if row["time_ps"] <= EPS_PS]
    state = int(any(row["q_v"] > THRESHOLD_V for row in time_zero)) if time_zero else 0
    classified: List[Dict[str, Any]] = []
    for row in events:
        if row["time_ps"] <= EPS_PS:
            continue
        before = state
        after = 1 - before
        classified.append({
            "time_ps": row["time_ps"],
            "q_v": row["q_v"],
            "q_state_before": before,
            "q_state_after": after,
            "direction": "rise" if after > before else "fall",
        })
        state = after
    return classified


def pair_q_events(q_events: Sequence[Mapping[str, Any]], crossings: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Pair Q transitions with the nearest same-direction source crossing."""

    used: Set[int] = set()
    paired: List[Dict[str, Any]] = []
    for event in q_events:
        candidates = [
            (index, source)
            for index, source in enumerate(crossings)
            if index not in used
            and source["direction"] == event["direction"]
            and source["time_ps"] <= event["time_ps"] + EPS_PS
            and event["time_ps"] - source["time_ps"] <= MAX_DQ_PS
        ]
        if candidates:
            index, source = min(candidates, key=lambda item: event["time_ps"] - item[1]["time_ps"])
            used.add(index)
            paired.append({
                **event,
                "classification": "source-backed",
                "source_event": dict(source),
                "delay_ps": event["time_ps"] - source["time_ps"],
            })
        else:
            paired.append({
                **event,
                "classification": "source-free",
                "source_event": None,
                "delay_ps": None,
            })
    return paired


def collect_flight_evidence(ledger: Mapping[str, Any]) -> Tuple[Dict[Tuple[int, str], List[float]], List[Dict[str, Any]], Dict[str, Any]]:
    """Extract per-tap/direction D-to-Q flight observations from L1A-R and CAL0."""

    source_points = [
        ("L1A-R-NORMAL", RUN_ROOT / "l1a_r_vcs_xa" / "bfe2l_095_n" / "xa_boundary_samples.csv"),
        ("CAL0-LEFT", RUN_ROOT / "cal0_vcs_xa" / "left" / "xa_boundary_samples.csv"),
        ("CAL0-CENTER", RUN_ROOT / "cal0_vcs_xa" / "center" / "xa_boundary_samples.csv"),
        ("CAL0-RIGHT", RUN_ROOT / "cal0_vcs_xa" / "right" / "xa_boundary_samples.csv"),
    ]
    ranges: Dict[Tuple[int, str], List[float]] = {}
    observations: List[Dict[str, Any]] = []
    corrected_event_counts: Dict[str, int] = {}
    for point, csv_path in source_points:
        rows = load_rows(csv_path)
        count = 0
        for tap in range(TAP_COUNT):
            q_events = q_event_stream(rows, tap)
            paired = pair_q_events(q_events, ledger["tap_{:02d}".format(tap)]["crossings"])
            count += len(paired)
            for event in paired:
                if event["classification"] != "source-backed":
                    continue
                key = (tap, event["direction"])
                ranges.setdefault(key, []).append(float(event["delay_ps"]))
                observations.append({
                    "evidence_point": point,
                    "tap": tap,
                    "direction": event["direction"],
                    "q_time_ps": event["time_ps"],
                    "source_time_ps": event["source_event"]["time_ps"],
                    "delay_ps": event["delay_ps"],
                    "q_state_before": event["q_state_before"],
                    "q_state_after": event["q_state_after"],
                })
        corrected_event_counts[point] = count
    by_direction: Dict[str, List[float]] = {"rise": [], "fall": []}
    for (tap, direction), values in ranges.items():
        by_direction[direction].extend(values)
    global_max = {direction: max(values) for direction, values in by_direction.items() if values}
    summary: Dict[str, Any] = {
        "direction_source": "Q state before/after each q_event; safe_d_v is never used for direction",
        "q_event_counts_after_time_zero": corrected_event_counts,
        "global_direction_max_delay_ps": global_max,
        "per_tap_direction_ranges_ps": {
            "tap_{:02d}_{}".format(tap, direction): {
                "min": min(values),
                "max": max(values),
                "count": len(values),
            }
            for (tap, direction), values in sorted(ranges.items())
        },
    }
    return ranges, observations, summary


def flight_duration(ranges: Mapping[Tuple[int, str], Sequence[float]], global_max: Mapping[str, float], tap: int, direction: str) -> Tuple[float, str]:
    """Return measured per-tap max flight, or a measured direction fallback."""

    values = ranges.get((tap, direction), ())
    if values:
        return max(values), "per-tap-observed"
    return float(global_max[direction]), "direction-observed-fallback"


def merge_windows(windows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Merge overlapping in-flight windows while retaining their causes."""

    merged: List[Dict[str, Any]] = []
    for window in sorted(windows, key=lambda item: (item["start_ps"], item["end_ps"], item["tap"])):
        if merged and window["start_ps"] <= merged[-1]["end_ps"] + EPS_PS:
            merged[-1]["end_ps"] = max(merged[-1]["end_ps"], window["end_ps"])
            merged[-1]["causes"].append(window)
        else:
            merged.append({"start_ps": window["start_ps"], "end_ps": window["end_ps"], "causes": [window]})
    return merged


def subtract_forbidden(local_start: float, local_end: float, forbidden: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Subtract merged in-flight windows from the old local CAL0 envelope."""

    safe: List[Dict[str, Any]] = []
    cursor = local_start
    for window in forbidden:
        start = max(local_start, float(window["start_ps"]))
        end = min(local_end, float(window["end_ps"]))
        if end <= local_start or start >= local_end:
            continue
        if start > cursor + EPS_PS:
            safe.append({"start_ps": cursor, "end_ps": start, "len_ps": start - cursor, "center_ps": (cursor + start) / 2.0})
        cursor = max(cursor, end)
    if cursor < local_end - EPS_PS:
        safe.append({"start_ps": cursor, "end_ps": local_end, "len_ps": local_end - cursor, "center_ps": (cursor + local_end) / 2.0})
    return safe


def reconstruct() -> Dict[str, Any]:
    """Build the capture-safe ledger without launching VCS or XA."""

    cal0_manifest = validate_frozen_inputs()
    ledger = load_json(SOURCE_LEDGER_PATH)
    ranges, observations, flight_summary = collect_flight_evidence(ledger)
    global_max = flight_summary["global_direction_max_delay_ps"]
    old_offline = load_json(CAL0_ROOT / "BFE2_CAL0_OFFLINE_INTERVALS.json")
    old_intervals = old_offline["selected_intervals"]
    local_start = min(float(item["start_g_ps"]) for item in old_intervals)
    local_end = max(float(item["end_g_ps"]) for item in old_intervals)
    windows: List[Dict[str, Any]] = []
    for tap in range(TAP_COUNT):
        for event in ledger["tap_{:02d}".format(tap)]["crossings"]:
            start = float(event["time_ps"])
            duration, duration_source = flight_duration(ranges, global_max, tap, event["direction"])
            end = start + duration
            if end > local_start and start < local_end:
                windows.append({
                    "tap": tap,
                    "direction": event["direction"],
                    "source_crossing_ps": start,
                    "start_ps": start,
                    "end_ps": end,
                    "flight_ps": duration,
                    "flight_source": duration_source,
                })
    merged = merge_windows(windows)
    safe_intervals = subtract_forbidden(local_start, local_end, merged)
    old_interval_audit: List[Dict[str, Any]] = []
    for interval in old_intervals:
        start = float(interval["start_g_ps"])
        end = float(interval["end_g_ps"])
        blockers = [window for window in windows if window["start_ps"] < end and window["end_ps"] > start]
        old_interval_audit.append({
            "point": interval["point"],
            "start_g_ps": start,
            "end_g_ps": end,
            "event_free": interval["event_free"],
            "capture_safe": not blockers,
            "blocking_taps": sorted({item["tap"] for item in blockers}),
            "blocking_windows": blockers,
        })
    offline = {
        "schema_version": 1,
        "stage": STAGE,
        "simulation_run": False,
        "dense_grid_scan": False,
        "source_waveform": NORMAL_SCENARIO,
        "l2_used": False,
        "nominal_sample_close_ps": NOMINAL_SAMPLE_CLOSE_PS,
        "nominal_g_close_ps": NOMINAL_G_CLOSE_PS,
        "local_envelope_g_ps": {"start": local_start, "end": local_end, "len": local_end - local_start},
        "source_ledger_sha256": sha256(SOURCE_LEDGER_PATH),
        "cal0_manifest_sha256": sha256(CAL0_MANIFEST_PATH),
        "cal0_analysis_sha256": sha256(CAL0_ANALYSIS_PATH),
        "cal0_offline_sha256": sha256(CAL0_ROOT / "BFE2_CAL0_OFFLINE_INTERVALS.json"),
        "latch_cell": "LATQ_X0P5M_A9TR40",
        "vdd_safe_v": VDD_SAFE,
        "capture_safe_rule": "close is forbidden from each pre-close safe_d crossing until its measured Q threshold resolution endpoint",
        "q_event_direction_rule": "direction = Q state after minus Q state before; safe_d_v is not used",
        "flight_completion_proxy": "first XA q_event threshold crossing; no added delay margin",
        "flight_evidence": flight_summary,
        "flight_observations": observations,
        "legacy_event_free_intervals": old_interval_audit,
        "merged_forbidden_windows": merged,
        "capture_safe_intervals": safe_intervals,
        "selected_capture_safe_points": [],
        "new_physical_scenarios": 0,
        "next_step_authorized": False,
        "stop_after_stage": True,
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    OFFLINE_PATH.write_text(json.dumps(offline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "stage": STAGE,
        "verification_mode": "offline capture-safe window repair from existing L1A-R/CAL0 XA evidence",
        "source_waveform": NORMAL_SCENARIO,
        "l2_used": False,
        "new_physical_scenarios": 0,
        "simulation_run": False,
        "dense_grid_scan": False,
        "nominal_sample_close_ps": NOMINAL_SAMPLE_CLOSE_PS,
        "nominal_g_close_ps": NOMINAL_G_CLOSE_PS,
        "vdd_safe_v": VDD_SAFE,
        "vnw_v": VDD_SAFE,
        "vpw_v": 0.0,
        "vss_v": 0.0,
        "latch_cell": "LATQ_X0P5M_A9TR40",
        "tap_count": TAP_COUNT,
        "sensing_geometry_id": cal0_manifest["sensing_geometry_id"],
        "safe_d_rule": cal0_manifest["safe_d_rule"],
        "additional_delay_ps": 0.0,
        "additional_slew": "none",
        "hysteresis": "none",
        "x_region": "none",
        "offline_sha256": sha256(OFFLINE_PATH),
        "source_ledger_sha256": sha256(SOURCE_LEDGER_PATH),
        "selected_capture_safe_points": [],
        "gate_pending_analysis": True,
        "stop_after_stage": True,
        "next_stage_authorized": False,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"offline": offline, "manifest": manifest}, indent=2, sort_keys=True))
    return offline


if __name__ == "__main__":
    reconstruct()
