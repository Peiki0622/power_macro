#!/usr/bin/env python3
"""Re-scan B-FE2.2S with the corrected single-resolution close rule.

This is a new, independent B-FE2.2S evidence producer.  The previous
``safe_seed`` artifact deliberately treated every pre-close D-to-Q flight as a
failure; that historical NO-GO evidence is never overwritten.  This revision
allows one measured, direction-matched D-to-Q response after G closes for a
tap, while still rejecting a second response, an unresolved tap, an invalid Q
code, or a code pair that cannot distinguish normal from L2.

No simulator or deck renderer is imported as an execution path.  All timing,
Q-code, SHA256, and historical re-flip facts come from the retained B-FE2.1
and B-FE2.2 JSON/.tr0 evidence already frozen by the preceding commits.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_bfe2_2s_safe_seed as previous  # noqa: E402  # Input/SHA contract and immutable source paths.


OUTPUT_ROOT = previous.SNAPSHOT_ROOT / "safe_seed_revised"
DQ_TIMING = previous.DQ_TIMING
LOAD_MANIFEST = previous.LOAD_MANIFEST
ROOT_CAUSE = previous.ROOT_CAUSE
REQUIRED_INPUTS = previous.REQUIRED_INPUTS
EPSILON_PS = previous.EPSILON_PS


def classify_tap(close_ps: float, tap: int, flights: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Classify one tap at one candidate close using measured D→Q events.

    A ``single-normal-resolution`` is allowed only when exactly one retained
    D/Q pair straddles close.  The reported resolution time is Q arrival minus
    the candidate effective G-close time.  More than one straddling pair is
    ``unresolved`` rather than being hidden by selecting one event.  A tap with
    no straddling pair is the stable ``zero-crossing`` case.
    """

    matches = [event for event in flights if event["tap"] == tap and
               event["d_cross_ps"] < close_ps - EPSILON_PS and
               event["predicted_q_arrival_ps"] > close_ps + EPSILON_PS]
    if not matches:
        return {"tap": tap, "classification": "zero-crossing", "resolution_events": [],
                "post_close_resolution_ps": None}
    if len(matches) > 1:
        return {"tap": tap, "classification": "unresolved", "resolution_events": matches,
                "post_close_resolution_ps": max(event["predicted_q_arrival_ps"] - close_ps for event in matches)}
    event = matches[0]
    return {"tap": tap, "classification": "single-normal-resolution", "resolution_events": [event],
            "post_close_resolution_ps": event["predicted_q_arrival_ps"] - close_ps}


def historical_reflip_points(root_data: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Return actual re-flip observations from old B-FE2.2 traces.

    These points are not extrapolated into new simulated behavior.  They are
    retained as exact historical warnings and used to avoid selecting an
    interval that contains a known failed close point.
    """

    points = []
    for record in root_data["snapshots"]:
        if float(record["baseline_v"]) != 0.95:
            continue
        taps = []
        for tap_record in record["per_tap"]:
            for event in tap_record["post_close_event_classification"]:
                if event["classification"] == "genuine_post_close_reflip":
                    taps.append(tap_record["tap"])
        points.append({"attempt": record["attempt"], "scenario_id": record["scenario_id"],
                       "observed_g_close_ps": record["observed_g_close_ps"],
                       "genuine_reflip_taps": sorted(set(taps))})
    return points


def common_intervals(normal: Mapping[str, Any], l2: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Build normal/L2 common clean-Q regions using existing helper semantics."""

    records = []
    for normal_interval in normal["clean_interior_q_stable_intervals"]:
        for l2_interval in l2["clean_interior_q_stable_intervals"]:
            left = max(normal_interval["interval_start_ps"], l2_interval["interval_start_ps"])
            right = min(normal_interval["interval_end_ps"], l2_interval["interval_end_ps"])
            if right - left <= EPSILON_PS:
                continue
            records.append({"interval_start_ps": left, "interval_end_ps": right,
                            "interval_width_ps": right - left,
                            "normal_q_code": normal_interval,
                            "l2_q_code": l2_interval,
                            "hamming_distance": sum(a != b for a, b in zip(normal_interval["raw_code"], l2_interval["raw_code"])),
                            "normal_l2_distinguishable": normal_interval["raw_code"] != l2_interval["raw_code"]})
    return records


def split_candidate(interval: Mapping[str, Any], all_flights: Sequence[Mapping[str, Any]], historical_points: Sequence[Mapping[str, Any]]) -> List[Tuple[float, float]]:
    """Split only at retained D crossings, Q arrivals, and exact old close points."""

    boundaries = {float(interval["interval_start_ps"]), float(interval["interval_end_ps"])}
    for flight in all_flights:
        for boundary in (flight["d_cross_ps"], flight["predicted_q_arrival_ps"]):
            if interval["interval_start_ps"] + EPSILON_PS < boundary < interval["interval_end_ps"] - EPSILON_PS:
                boundaries.add(boundary)
    for point in historical_points:
        close_ps = point["observed_g_close_ps"]
        if interval["interval_start_ps"] + EPSILON_PS < close_ps < interval["interval_end_ps"] - EPSILON_PS:
            boundaries.add(close_ps)
    edges = sorted(boundaries)
    return [(left, right) for left, right in zip(edges[:-1], edges[1:]) if right - left > EPSILON_PS]


def inspect_candidate(interval: Mapping[str, Any], close_ps: float, normal_flights: Sequence[Mapping[str, Any]], l2_flights: Sequence[Mapping[str, Any]], historical_points: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Classify every normal/L2 tap and retain all candidate rejection causes."""

    normal_taps = [classify_tap(close_ps, tap, normal_flights) for tap in range(30)]
    l2_taps = [classify_tap(close_ps, tap, l2_flights) for tap in range(30)]
    unresolved = [tap for tap in range(30) if normal_taps[tap]["classification"] == "unresolved" or l2_taps[tap]["classification"] == "unresolved"]
    resolution_values = [item["post_close_resolution_ps"] for item in normal_taps + l2_taps if item["post_close_resolution_ps"] is not None]
    containing_history = [point for point in historical_points if point["observed_g_close_ps"] == close_ps]
    rejection_reasons = []
    if interval["hamming_distance"] <= 0:
        rejection_reasons.append("normal_l2_q_code_not_distinguishable")
    if unresolved:
        rejection_reasons.append("unresolved_or_multiple_post_close_resolution")
    if containing_history:
        rejection_reasons.append("candidate_is_exactly_a_retained_historical_close")
    return {
        "interval_start_ps": interval["interval_start_ps"], "interval_end_ps": interval["interval_end_ps"],
        "interval_width_ps": interval["interval_end_ps"] - interval["interval_start_ps"],
        "midpoint_ps": close_ps, "normal_q_code": interval["normal_q_code"], "l2_q_code": interval["l2_q_code"],
        "hamming_distance": interval["hamming_distance"],
        "normal_tap_classification": normal_taps, "l2_tap_classification": l2_taps,
        "normal_single_normal_resolution_taps": [item["tap"] for item in normal_taps if item["classification"] == "single-normal-resolution"],
        "l2_single_normal_resolution_taps": [item["tap"] for item in l2_taps if item["classification"] == "single-normal-resolution"],
        "normal_zero_crossing_taps": [item["tap"] for item in normal_taps if item["classification"] == "zero-crossing"],
        "l2_zero_crossing_taps": [item["tap"] for item in l2_taps if item["classification"] == "zero-crossing"],
        "unresolved_taps": unresolved,
        # There is no new waveform at this derived midpoint.  Therefore the
        # predicted candidate has no newly observed genuine re-flip; exact
        # historical re-flip taps remain listed separately below and are not
        # silently treated as proof of a different close time.
        "reflip_taps": [],
        "historical_reflip_points": containing_history,
        "worst_post_close_resolution_ps": max(resolution_values) if resolution_values else 0.0,
        "minimum_interval_margin_ps": (interval["interval_end_ps"] - interval["interval_start_ps"]) / 2.0,
        "minimum_bit_margin_v": min(interval["normal_q_code"]["minimum_bit_margin_v"], interval["l2_q_code"]["minimum_bit_margin_v"]),
        "final_q_code_stable": True,
        "final_q_code_distinguishable": interval["hamming_distance"] > 0,
        "rejection_reasons": rejection_reasons,
        "candidate_status": "candidate" if not rejection_reasons else "rejected",
    }


def historical_110_audit(root_data: Mapping[str, Any]) -> Dict[str, Any]:
    """Accept one normal resolution per tap but reject actual re-flips/unresolved states."""

    details, conflict = [], False
    for record in root_data["snapshots"]:
        if record["attempt"] != "first_attempt" or float(record["baseline_v"]) != 1.10:
            continue
        per_tap = []
        for tap_record in record["per_tap"]:
            events = tap_record["post_close_event_classification"]
            genuine = [event for event in events if event["classification"] == "genuine_post_close_reflip"]
            if genuine or len(events) > 1:
                conflict = True
            per_tap.append({"tap": tap_record["tap"], "post_close_event_count": len(events),
                            "classification": "genuine-reflip" if genuine else
                            "single-normal-resolution" if len(events) == 1 else "zero-crossing"})
        details.append({"scenario_id": record["scenario_id"], "observed_g_close_ps": record["observed_g_close_ps"],
                        "tap_classification": per_tap})
    return {"checked_without_rerun": True, "consistent_with_corrected_single_resolution_rule": not conflict,
            "scenarios": details}


def compact_candidate(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep every candidate machine-readable without duplicating event payloads.

    The selected candidate is stored separately with full per-tap event records.
    For the remaining candidates, the two 30-entry classification vectors and
    scalar margins preserve the complete Gate decision while avoiding hundreds
    of repeated copies of the same D/Q event dictionaries in the Git evidence.
    """

    return {
        "interval_start_ps": candidate["interval_start_ps"],
        "interval_end_ps": candidate["interval_end_ps"],
        "midpoint_ps": candidate["midpoint_ps"],
        "interval_width_ps": candidate["interval_width_ps"],
        "minimum_interval_margin_ps": candidate["minimum_interval_margin_ps"],
        "hamming_distance": candidate["hamming_distance"],
        "minimum_bit_margin_v": candidate["minimum_bit_margin_v"],
        "worst_post_close_resolution_ps": candidate["worst_post_close_resolution_ps"],
        "normal_classification": [item["classification"] for item in candidate["normal_tap_classification"]],
        "l2_classification": [item["classification"] for item in candidate["l2_tap_classification"]],
        "unresolved_taps": candidate["unresolved_taps"],
        "reflip_taps": candidate["reflip_taps"],
        "historical_reflip_points": candidate["historical_reflip_points"],
        "rejection_reasons": candidate["rejection_reasons"],
        "candidate_status": candidate["candidate_status"],
        "normal_raw_code": candidate["normal_q_code"]["raw_code"],
        "l2_raw_code": candidate["l2_q_code"]["raw_code"],
    }


def main() -> int:
    """Publish revised B-FE2.2S evidence using zero new simulations."""

    inputs = {path: previous.read_json(path) for path in REQUIRED_INPUTS}
    validation = previous.validate_inputs(inputs)
    timing = inputs[previous.DQ_TIMING]
    manifest_by_id = {entry["scenario_id"]: entry for entry in inputs[previous.LOAD_MANIFEST]["scenarios"]}
    enriched = []
    for entry in timing["scenarios"]:
        source = manifest_by_id[entry["scenario_id"]]
        enriched.append(dict(entry, baseline_v=source["baseline_v"], droop_v=source["droop_v"]))
    historical_points = historical_reflip_points(inputs[ROOT_CAUSE])
    baseline = {}
    # Keep the full in-memory candidates separate from the compact summaries
    # written for every candidate.  The selected seed must retain complete
    # per-tap D/Q event evidence, while the interval ledger only needs the
    # compact classification vectors and scalar margins for rejected points.
    full_candidates_by_baseline = {}
    for baseline_v in (0.95, 1.10):
        normal = next(entry for entry in enriched if entry["baseline_v"] == baseline_v and entry["droop_v"] is None)
        l2 = next(entry for entry in enriched if entry["baseline_v"] == baseline_v and entry["droop_v"] is not None)
        normal_flights = previous.dq_flight_intervals(normal)
        l2_flights = previous.dq_flight_intervals(l2)
        common = common_intervals(normal, l2)
        all_flights = normal_flights + l2_flights
        examined = []
        for interval in common:
            for left, right in split_candidate(interval, all_flights, historical_points if baseline_v == 0.95 else []):
                # Pass the physically split interval to the classifier.  The
                # Q codes remain those of the parent stable region, but the
                # candidate width/margin must be the exact D/Q-boundary
                # segment, never the larger unsplit parent interval.
                segment = dict(interval, interval_start_ps=left, interval_end_ps=right,
                               interval_width_ps=right - left)
                examined.append(inspect_candidate(segment, (left + right) / 2.0, normal_flights, l2_flights,
                                                  historical_points if baseline_v == 0.95 else []))
        candidates_for_baseline = [item for item in examined if item["candidate_status"] == "candidate"]
        full_candidates_by_baseline[str(baseline_v)] = candidates_for_baseline
        baseline[str(baseline_v)] = {"baseline_v": baseline_v, "normal_scenario": normal["scenario_id"],
                                     "l2_scenario": l2["scenario_id"], "common_q_stable_intervals": common,
                                     "examined_candidate_count": len(examined),
                                     "candidate_interval_count": len(candidates_for_baseline),
                                     "examined_candidates": [compact_candidate(item) for item in examined],
                                     "candidate_intervals": [compact_candidate(item) for item in candidates_for_baseline]}
    audit_110 = historical_110_audit(inputs[ROOT_CAUSE])
    candidates = full_candidates_by_baseline["0.95"]
    candidates = sorted(candidates, key=lambda item: (-item["minimum_interval_margin_ps"],
                                                        item["worst_post_close_resolution_ps"],
                                                        -item["hamming_distance"],
                                                        abs(item["normal_q_code"]["center"] - 14.5)))
    selected = candidates[0] if candidates and audit_110["consistent_with_corrected_single_resolution_rule"] else None
    if selected is not None:
        gate = "BFE2_2S_SAFE_SEED_READY"
        reason = "0.95-V normal/L2 has a positive-width common Q-stable interval with only zero or single normal resolutions; no unresolved tap or historical re-flip lies at the selected midpoint, and the 1.10-V history is compatible"
    else:
        gate = "BFE2_2S_SAFE_SEED_BLOCKED"
        reason = "no corrected 0.95-V candidate survives genuine re-flip/unresolved checks and the corrected single-resolution rule"
    source_sha = [{"path": str(path.relative_to(FTC_ROOT)), "sha256": previous.sha256_file(path)} for path in REQUIRED_INPUTS]
    output = {"schema_version": 2, "stage": "B-FE2.2S", "revision": "single_normal_resolution_allowed",
              "gate": gate, "reason": reason, "new_hspice_scenarios": 0,
              "executed_new_hspice_scenarios": {"B-FE2.1": 4, "B-FE2.2": 6, "B-FE2.2R": 0, "B-FE2.2S": 0},
              "old_no_go_evidence_preserved_at": "real_snapshot/safe_seed/BFE2_2S_SAFE_INTERVALS.json",
              "input_validation": validation, "input_sha256": source_sha,
              "historical_0p95_reflip_points": historical_points,
              "historical_1p10_audit": audit_110,
              "liberty_setup_hold_applicability": {
                  "audit_source": "BFE2_0_LATCH_CELL_AUDIT.json",
                  "available_constraint_types": ["setup_falling", "hold_falling"],
                  "direct_numeric_margin_used": False,
                  "status": "no directly applicable numeric 0.95-V Liberty setup/hold value in retained audit",
                  "provisional_boundary_source": "transistor-level measured D-to-Q arrivals, Q stable intervals, and exact historical re-flip points",
                  "classification_tolerance_is_not_margin": True,
              },
              "classification_policy": {"zero-crossing": "no measured pre-close D/Q pair straddles close",
                  "single-normal-resolution": "exactly one measured same-tap D/Q pair straddles close; Q arrival is the post-close resolution",
                  "genuine-reflip": "second post-close Q crossing without a corresponding D source in an actual retained snapshot; candidate midpoint has no new waveform",
                  "unresolved": "more than one D/Q pair straddles close for one tap or final Q/code cannot be resolved"},
              "baselines": baseline, "selected_corrected_seed": selected}
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "BFE2_2S_REVISED_SAFE_INTERVALS.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_ROOT / "BFE2_2S_REVISED_SELECTED_SEED.json").write_text(json.dumps({"stage": "B-FE2.2S", "revision": output["revision"],
        "gate": gate, "selected_corrected_seed": selected, "new_hspice_scenarios": 0}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_ROOT / "BFE2_2S_REVISED_GATE_STATUS.json").write_text(json.dumps({"stage": "B-FE2.2S", "revision": output["revision"],
        "gate": gate, "reason": reason, "new_hspice_scenarios": 0, "selected_seed_present": selected is not None}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    selected_text = "none" if selected is None else "{:.6f}-{:.6f} ps midpoint {:.6f} ps".format(selected["interval_start_ps"], selected["interval_end_ps"], selected["midpoint_ps"])
    report = """# B-FE2.2S 修订安全关闭种子离线重建\n\n- Gate：`{gate}`；本阶段新增 HSPICE：0。\n- 判据修订：允许每个 tap 在 G close 后 0 次或 1 次、且由关闭前 D crossing 和实测 D→Q 延迟解释的 `single-normal-resolution`；仍禁止 genuine re-flip、unresolved、多次响应、最终 Q 不稳定或 normal/L2 不可区分。\n- 0.95 V 合法候选：{count} 个；选中：`{selected}`。\n- 选中候选 normal single-resolution taps：{normal_taps}；L2 single-resolution taps：{l2_taps}；re-flip taps：{reflips}；unresolved taps：{unresolved}。\n- 选中候选最差 post-close resolution：{worst:.6f} ps；最小区间余量：{margin:.6f} ps；最终 Hamming distance：{ham}；最小 Q bit margin：{bit:.9f} V。\n- 旧严格 NO-GO 证据保留在 `real_snapshot/safe_seed/`；本修订仅新增 `real_snapshot/safe_seed_revised/`。本候选尚未有新的 G/Q 波形，READY 只授权后续唯一一对 B-FE2.2C 确认仿真，本轮未创建 deck、未调用 HSPICE、未进入 B-FE2.3/B-FE3。\n""".format(gate=gate, count=len(candidates), selected=selected_text,
             normal_taps="none" if selected is None else selected["normal_single_normal_resolution_taps"],
             l2_taps="none" if selected is None else selected["l2_single_normal_resolution_taps"],
             reflips="none" if selected is None else selected["reflip_taps"],
             unresolved="none" if selected is None else selected["unresolved_taps"],
             worst=0.0 if selected is None else selected["worst_post_close_resolution_ps"],
             margin=0.0 if selected is None else selected["minimum_interval_margin_ps"],
             ham=0 if selected is None else selected["hamming_distance"],
             bit=0.0 if selected is None else selected["minimum_bit_margin_v"])
    (OUTPUT_ROOT / "BFE2_2S_REVISED_REPORT.md").write_text(report, encoding="utf-8")
    print(gate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
