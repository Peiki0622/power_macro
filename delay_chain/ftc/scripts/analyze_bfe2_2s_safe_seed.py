#!/usr/bin/env python3
"""Rebuild B-FE2.2 safe-close seeds from retained latch timing evidence only.

B-FE2.2S is intentionally a zero-HSPICE stage.  It never renders a deck and
never invokes a simulator.  Instead, it intersects the measured B-FE2.1 Q
code stability intervals for a normal/L2 pair, then rejects every time covered
by an individual measured transparent-latch D-to-Q flight interval.  This is
the physical rule that the former XOR-RAW_CODE midpoint rule omitted.

The Liberty audit identifies setup_falling/hold_falling constraint tables, but
the audited library is the 1.10-V typical-max view.  It supplies no directly
applicable numeric 0.95-V constraint in the retained evidence, so this script
does not invent one.  Its provisional research boundary is explicitly limited
to measured transistor-level Q stability and per-tap D-to-Q completion; it is
only capable of authorizing the one B-FE2.2C confirmation pair if a positive
common region actually survives.
"""

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_bfe2_2r_root_cause as root_cause  # noqa: E402  # Shared immutable snapshot provenance convention.


ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch"
LOAD_ROOT = ANALYSIS_ROOT / "latch_load"
SNAPSHOT_ROOT = ANALYSIS_ROOT / "real_snapshot"
ROOT_CAUSE_ROOT = SNAPSHOT_ROOT / "root_cause"
OUTPUT_ROOT = SNAPSHOT_ROOT / "safe_seed"

LOAD_MANIFEST = LOAD_ROOT / "BFE2_1_SCENARIO_MANIFEST.json"
DQ_TIMING = LOAD_ROOT / "BFE2_1_TRANSPARENT_DQ_TIMING.json"
LOAD_GATE = LOAD_ROOT / "BFE2_1_GATE_STATUS.json"
FIRST_MANIFEST = SNAPSHOT_ROOT / "BFE2_2_SCENARIO_MANIFEST.json"
RETRY_MANIFEST = SNAPSHOT_ROOT / "BFE2_2_RETRY_MANIFEST.json"
SNAPSHOT_GATE = SNAPSHOT_ROOT / "BFE2_2_GATE_STATUS.json"
ROOT_CAUSE = ROOT_CAUSE_ROOT / "BFE2_2R_ROOT_CAUSE.json"
ROOT_LEDGER = ROOT_CAUSE_ROOT / "BFE2_2R_EVIDENCE_LEDGER.json"
LATCH_AUDIT = ANALYSIS_ROOT / "BFE2_0_LATCH_CELL_AUDIT.json"

REQUIRED_INPUTS = (LOAD_MANIFEST, DQ_TIMING, LOAD_GATE, FIRST_MANIFEST,
                   RETRY_MANIFEST, SNAPSHOT_GATE, ROOT_CAUSE, ROOT_LEDGER,
                   LATCH_AUDIT)
EPSILON_PS = 1.0e-6


def read_json(path: Path) -> Dict[str, Any]:
    """Read one object evidence artifact and reject a malformed replacement."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def sha256_file(path: Path) -> str:
    """Hash an immutable input or raw waveform in bounded memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def interval_record(left: float, right: float, normal: Mapping[str, Any], l2: Mapping[str, Any]) -> Dict[str, Any]:
    """Describe one pair-common Q interval without changing either raw code."""

    hamming = sum(a != b for a, b in zip(normal["raw_code"], l2["raw_code"]))
    return {
        "interval_start_ps": left, "interval_end_ps": right,
        "interval_width_ps": right - left,
        "normal_q_code": normal, "l2_q_code": l2,
        "hamming_distance": hamming,
        "normal_l2_distinguishable": hamming > 0,
    }


def clean_q_intervals(scenario: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """Return only Q regions already proven clean by B-FE2.1's frozen parser."""

    return list(scenario["clean_interior_q_stable_intervals"])


def common_q_intervals(normal: Mapping[str, Any], l2: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Intersect normal/L2 clean Q stability regions using exact measured edges."""

    records = []
    for normal_interval in clean_q_intervals(normal):
        for l2_interval in clean_q_intervals(l2):
            left = max(normal_interval["interval_start_ps"], l2_interval["interval_start_ps"])
            right = min(normal_interval["interval_end_ps"], l2_interval["interval_end_ps"])
            if right - left > EPSILON_PS:
                records.append(interval_record(left, right, normal_interval, l2_interval))
    return sorted(records, key=lambda item: (item["interval_start_ps"], item["interval_end_ps"]))


def dq_flight_intervals(scenario: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Return one per-tap, per-direction measured D-to-Q in-flight interval.

    The interval is open at both threshold crossings.  At any interior close
    time, D has already crossed but the measured transparent Q arrival has not
    completed, which is precisely the forbidden B-FE2.2S condition.  No global
    average delay is used: each record retains its tap, direction, and actual
    launch-relative crossing pair.
    """

    flights = []
    for tap_record in scenario["per_tap"]:
        for event in tap_record["matched_d_to_q_events"]:
            if event["q_cross_ps"] - event["d_cross_ps"] <= EPSILON_PS:
                raise ValueError("non-positive transparent D-to-Q delay at tap {}".format(tap_record["tap"]))
            flights.append({"tap": tap_record["tap"], "direction": event["direction"],
                            "d_cross_ps": event["d_cross_ps"], "predicted_q_arrival_ps": event["q_cross_ps"],
                            "measured_d_to_q_delay_ps": event["d_to_q_delay_ps"]})
    return sorted(flights, key=lambda item: (item["d_cross_ps"], item["predicted_q_arrival_ps"], item["tap"]))


def split_at_boundaries(interval: Mapping[str, Any], flights: Sequence[Mapping[str, Any]]) -> List[Tuple[float, float]]:
    """Split a Q-stable interval at all measured D/Q arrival boundaries.

    Splitting before classification exposes every rejected subinterval and its
    responsible tap rather than hiding a large interval behind one aggregate
    boolean.  It is not a time sweep: all boundaries originate from retained
    physical crossings, not a synthetic grid.
    """

    boundaries = {float(interval["interval_start_ps"]), float(interval["interval_end_ps"])}
    for flight in flights:
        for boundary in (flight["d_cross_ps"], flight["predicted_q_arrival_ps"]):
            if interval["interval_start_ps"] + EPSILON_PS < boundary < interval["interval_end_ps"] - EPSILON_PS:
                boundaries.add(boundary)
    ordered = sorted(boundaries)
    return [(left, right) for left, right in zip(ordered[:-1], ordered[1:]) if right - left > EPSILON_PS]


def flights_covering(time_ps: float, flights: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """Return all D events already launched but not yet at Q at ``time_ps``."""

    return [flight for flight in flights if flight["d_cross_ps"] + EPSILON_PS < time_ps and
            flight["predicted_q_arrival_ps"] > time_ps + EPSILON_PS]


def next_d_distance(time_ps: float, flights: Iterable[Mapping[str, Any]]) -> Tuple[Optional[float], Optional[Mapping[str, Any]]]:
    """Measure distance to the next D crossing for provisional hold-risk evidence.

    No numeric hold constraint is invented.  This distance is retained so a
    positive candidate can be reviewed against an appropriate Liberty table or
    a later transistor-level closing experiment; it is not independently used
    as a signoff pass/fail threshold.
    """

    future = [flight for flight in flights if flight["d_cross_ps"] > time_ps + EPSILON_PS]
    if not future:
        return None, None
    nearest = min(future, key=lambda flight: flight["d_cross_ps"])
    return nearest["d_cross_ps"] - time_ps, nearest


def classify_common_intervals(common: Sequence[Mapping[str, Any]], normal_flights: Sequence[Mapping[str, Any]], l2_flights: Sequence[Mapping[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Classify each Q-common segment against all normal and L2 D-to-Q flights."""

    all_flights = list(normal_flights) + list(l2_flights)
    accepted, examined = [], []
    for record in common:
        for left, right in split_at_boundaries(record, all_flights):
            midpoint = (left + right) / 2.0
            normal_risks = flights_covering(midpoint, normal_flights)
            l2_risks = flights_covering(midpoint, l2_flights)
            next_normal_distance, next_normal = next_d_distance(midpoint, normal_flights)
            next_l2_distance, next_l2 = next_d_distance(midpoint, l2_flights)
            segment = dict(record)
            segment.update({"interval_start_ps": left, "interval_end_ps": right, "interval_width_ps": right - left,
                            "midpoint_ps": midpoint, "normal_inflight_risks": normal_risks,
                            "l2_inflight_risks": l2_risks,
                            "next_normal_d_distance_ps": next_normal_distance,
                            "next_l2_d_distance_ps": next_l2_distance,
                            "next_normal_d_event": next_normal, "next_l2_d_event": next_l2})
            if not segment["normal_l2_distinguishable"]:
                segment["rejection_reasons"] = ["normal_l2_q_codes_not_distinguishable"]
            elif normal_risks or l2_risks:
                segment["rejection_reasons"] = ["preclose_d_to_q_inflight_normal" if normal_risks else None,
                                                "preclose_d_to_q_inflight_l2" if l2_risks else None]
                segment["rejection_reasons"] = [reason for reason in segment["rejection_reasons"] if reason]
            else:
                segment["rejection_reasons"] = []
                accepted.append(segment)
            examined.append(segment)
    return accepted, examined


def historical_110_consistency(root_data: Mapping[str, Any]) -> Dict[str, Any]:
    """Check the retained 1.10-V pair against the corrected no-inflight rule.

    B-FE2.2S cannot rerun 1.10 V.  The only allowed check is whether the two
    immutable first-attempt snapshots already show a normal in-flight event or
    genuine re-flip after their measured G close.  Either behavior conflicts
    with the corrected seed rule and must be reported, never fixed by picking
    a new 1.10-V time.
    """

    records = [record for record in root_data["snapshots"] if record["attempt"] == "first_attempt" and
               float(record["baseline_v"]) == 1.10]
    if len(records) != 2:
        raise ValueError("B-FE2.2S requires exactly two immutable 1.10-V first-attempt records")
    details, conflict = [], False
    for record in records:
        inflight, reflip = [], []
        for tap in record["per_tap"]:
            for event in tap["post_close_event_classification"]:
                tagged = {"tap": tap["tap"], **event}
                if event["classification"] == "normal_in_flight_data_event":
                    inflight.append(tagged)
                elif event["classification"] == "genuine_post_close_reflip":
                    reflip.append(tagged)
        conflict = conflict or bool(inflight or reflip)
        details.append({"scenario_id": record["scenario_id"], "droop_v": record["droop_v"],
                        "observed_g_close_ps": record["observed_g_close_ps"],
                        "post_close_inflight_events": inflight,
                        "genuine_post_close_reflips": reflip,
                        "consistent_with_corrected_rule": not inflight and not reflip})
    return {"checked_without_rerun": True, "consistent_with_corrected_rule": not conflict,
            "reason": "historical 1.10-V pair has no post-close in-flight or re-flip evidence" if not conflict else
                      "historical 1.10-V pair contains post-close in-flight data evidence; it cannot be promoted under the corrected rule without a new plan",
            "scenarios": details}


def validate_inputs(inputs: Mapping[Path, Mapping[str, Any]]) -> Dict[str, Any]:
    """Validate all B-FE2.2S authorities, scenario identities, and raw hashes."""

    load_manifest, load_gate = inputs[LOAD_MANIFEST], inputs[LOAD_GATE]
    first_manifest, retry_manifest = inputs[FIRST_MANIFEST], inputs[RETRY_MANIFEST]
    snapshot_gate, root_data, ledger, audit = inputs[SNAPSHOT_GATE], inputs[ROOT_CAUSE], inputs[ROOT_LEDGER], inputs[LATCH_AUDIT]
    if load_gate.get("gate") != "BFE2_1_LATCH_LOAD_GO":
        raise ValueError("B-FE2.1 Gate is not GO")
    if snapshot_gate.get("gate") != "BFE2_2_REAL_SNAPSHOT_CONDITIONAL":
        raise ValueError("B-FE2.2 historical Gate is not CONDITIONAL")
    if root_data.get("verdict", {}).get("gate") != "BFE2_2R_ROOT_CAUSE_CONFIRMED":
        raise ValueError("B-FE2.2R root cause is not confirmed")
    if audit.get("cell") != "LATQ_X0P5M_A9TR40":
        raise ValueError("unexpected latch cell in audit")
    if len(load_manifest.get("scenarios", [])) != 4 or len(first_manifest.get("scenarios", [])) != 4 or len(retry_manifest.get("scenarios", [])) != 2:
        raise ValueError("B-FE2.2S requires retained 4/4/2 scenario cardinalities")
    expected_load_ids = {"BFE2L-095-N", "BFE2L-095-L2", "BFE2L-110-N", "BFE2L-110-L2"}
    if {entry["scenario_id"] for entry in load_manifest["scenarios"]} != expected_load_ids:
        raise ValueError("B-FE2.1 scenario identity set changed")
    if any(entry.get("baseline_v") not in (0.95, 1.1) for entry in load_manifest["scenarios"]):
        raise ValueError("unexpected B-FE2 baseline voltage")
    # The B-FE2.2R ledger is the compact immutable binding between historical
    # manifests and raw deck/.tr0 bytes.  Recompute every stored raw SHA so a
    # later changed waveform cannot silently produce a new safe seed.
    ledger_records = ledger.get("first_attempt", []) + ledger.get("retry", [])
    if len(ledger_records) != 6:
        raise ValueError("B-FE2.2R ledger does not preserve all six snapshot cases")
    for record in ledger_records:
        deck, trace = FTC_ROOT / record["deck_path"], FTC_ROOT / record["tr0_path"]
        if sha256_file(deck) != record["deck_sha256"] or sha256_file(trace) != record["tr0_sha256"]:
            raise ValueError("snapshot raw SHA mismatch: {} {}".format(record["attempt"], record["scenario_id"]))
    for entry in load_manifest["scenarios"]:
        directory = root_cause.RUN_ROOT / "latch_load" / "scenarios" / entry["scenario_id"].lower().replace("-", "_")
        if sha256_file(directory / "bfe2l.sp") != entry["deck_sha256"] or sha256_file(directory / "bfe2l.tr0") != entry["tr0_sha256"]:
            raise ValueError("B-FE2.1 raw SHA mismatch: {}".format(entry["scenario_id"]))
    return {"all_required_inputs_present": True, "bfe2_1_gate": load_gate["gate"],
            "bfe2_2_gate": snapshot_gate["gate"], "bfe2_2r_gate": root_data["verdict"]["gate"],
            "raw_sha_validation": "all four B-FE2.1 and all six B-FE2.2 deck/.tr0 pairs match retained evidence"}


def baseline_analysis(baseline_v: float, timing: Mapping[str, Any], load_manifest: Mapping[str, Any]) -> Dict[str, Any]:
    """Build all common-Q and D-to-Q-safe intervals for one formal baseline."""

    # The D→Q artifact intentionally concentrates waveform-derived timing and
    # therefore keys records by scenario_id.  Baseline and droop identity are
    # inherited from the separately hashed B-FE2.1 scenario manifest rather
    # than reconstructed from an ID string.
    manifest_by_id = {entry["scenario_id"]: entry for entry in load_manifest["scenarios"]}
    enriched = []
    for entry in timing["scenarios"]:
        source = manifest_by_id.get(entry["scenario_id"])
        if source is None:
            raise ValueError("D-to-Q timing scenario is absent from B-FE2.1 manifest: {}".format(entry["scenario_id"]))
        enriched.append(dict(entry, baseline_v=source["baseline_v"], droop_v=source["droop_v"]))
    normal = next(entry for entry in enriched if float(entry["baseline_v"]) == baseline_v and entry["droop_v"] is None)
    l2 = next(entry for entry in enriched if float(entry["baseline_v"]) == baseline_v and entry["droop_v"] is not None)
    normal_flights, l2_flights = dq_flight_intervals(normal), dq_flight_intervals(l2)
    common = common_q_intervals(normal, l2)
    accepted, examined = classify_common_intervals(common, normal_flights, l2_flights)
    return {"baseline_v": baseline_v, "normal_scenario": normal["scenario_id"], "l2_scenario": l2["scenario_id"],
            "normal_q_stable_intervals": clean_q_intervals(normal), "l2_q_stable_intervals": clean_q_intervals(l2),
            "normal_dq_flights": normal_flights, "l2_dq_flights": l2_flights,
            "common_q_stable_intervals": common, "examined_subintervals": examined,
            "provisional_safe_intervals": accepted,
            "provisional_margin_method": "measured per-tap transistor-level D-to-Q completion plus Q-stable intervals; no numeric 0.95-V Liberty setup/hold table is available"}


def choose_seed(intervals: Sequence[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Choose one legal 0.95-V point only after all safety filters passed.

    The ranking follows the plan rather than old XOR-window heuristics.  The
    smallest endpoint margin is maximized first; midpoint is only a derived
    requested-close command corresponding to an intended effective G-close
    time.  Because a finite G edge has shown small PWL-to-threshold offsets,
    B-FE2.2C must record its measured G crossing again rather than assuming
    this requested value is exact.
    """

    if not intervals:
        return None
    ranked = sorted(intervals, key=lambda item: (-item["interval_width_ps"], -item["hamming_distance"],
                                                   abs(item["normal_q_code"]["center"] - 14.5)))
    chosen = dict(ranked[0])
    chosen.update({"effective_g_close_seed_ps": (chosen["interval_start_ps"] + chosen["interval_end_ps"]) / 2.0,
                   "requested_close_ps": (chosen["interval_start_ps"] + chosen["interval_end_ps"]) / 2.0,
                   "selection_rule": "maximise positive common physical interval width, then Hamming distance, then spatial centrality after Q/D-to-Q filters",
                   "requested_vs_effective_g_note": "B-FE2.2C must measure G VDD/2 crossing; this request is not assumed equal to the effective close"})
    return chosen


def gate_status(baseline_095: Mapping[str, Any], historical_110: Mapping[str, Any]) -> Tuple[str, str]:
    """Apply B-FE2.2S READY/INCONCLUSIVE/BLOCKED in prescribed priority order."""

    if not baseline_095["provisional_safe_intervals"]:
        return "BFE2_2S_SAFE_SEED_BLOCKED", "0.95-V normal/L2 has no positive-width common Q-stable interval free of every measured pre-close D-to-Q flight"
    if not historical_110["consistent_with_corrected_rule"]:
        return "BFE2_2S_SAFE_SEED_INCONCLUSIVE", "0.95-V has a provisional candidate but the immutable 1.10-V historical pair conflicts with the corrected no-inflight rule"
    return "BFE2_2S_SAFE_SEED_READY", "0.95-V has a positive-width common Q/D-to-Q-safe interval and the 1.10-V historical pair is consistent"


def report(output: Mapping[str, Any]) -> str:
    """Render a short review with explicit no-run and no-B-FE2.2C conclusion."""

    baseline = output["baselines"]["0.95"]
    rejected = sum(1 for item in baseline["examined_subintervals"] if item["rejection_reasons"])
    return """# B-FE2.2S 安全关闭种子离线重建\n\n- Gate：`{gate}`；本阶段新增 HSPICE：0。\n- 0.95 V：normal/L2 共有 {common} 个干净 Q 稳定交集，经逐 tap、逐方向透明态 D→Q in-flight 检查后，保留 {safe} 个正宽度 provisional 安全区，拒绝 {rejected} 个子区间。\n- Liberty 审计仅证明 1.10 V typical-max 库中存在 `setup_falling`/`hold_falling` 约束表；没有可直接用于本 0.95 V 研究的数值，故未编造 setup/hold margin。采用的 provisional 边界仅为实测 Q 稳定区和每路 D→Q 完成。\n- 1.10 V 历史 pair 的新规则一致性：{one_ten}。不重跑 1.10 V。\n- 结论：{reason}。{next_step}\n\n未来关闭点不得由 XOR `RAW_CODE` 平台中点生成；只有 Q 稳定、所有相关 D→Q 已完成且有明确 setup/hold 或 provisional 等效风险处理时，才允许进入一次确认仿真。\n""".format(
        gate=output["gate"], common=len(baseline["common_q_stable_intervals"]),
        safe=len(baseline["provisional_safe_intervals"]), rejected=rejected,
        one_ten="通过" if output["historical_110_consistency"]["consistent_with_corrected_rule"] else "存在 post-close in-flight 冲突",
        reason=output["reason"],
        next_step="B-FE2.2C 未获授权，未创建或运行新 deck。" if output["gate"] != "BFE2_2S_SAFE_SEED_READY" else
                  "允许按计划仅运行一对 0.95 V corrected seed 确认。")


def main() -> int:
    """Publish B-FE2.2S safe-seed evidence without starting HSPICE."""

    inputs = {path: read_json(path) for path in REQUIRED_INPUTS}
    validation = validate_inputs(inputs)
    timing = inputs[DQ_TIMING]
    baseline_095 = baseline_analysis(0.95, timing, inputs[LOAD_MANIFEST])
    baseline_110 = baseline_analysis(1.10, timing, inputs[LOAD_MANIFEST])
    historical_110 = historical_110_consistency(inputs[ROOT_CAUSE])
    gate, reason = gate_status(baseline_095, historical_110)
    selected = choose_seed(baseline_095["provisional_safe_intervals"]) if gate == "BFE2_2S_SAFE_SEED_READY" else None
    source_sha = [{"path": str(path.relative_to(FTC_ROOT)), "sha256": sha256_file(path)} for path in REQUIRED_INPUTS]
    output = {"schema_version": 1, "stage": "B-FE2.2S", "gate": gate, "reason": reason,
              "new_hspice_scenarios": 0, "executed_new_hspice_scenarios": {"B-FE2.1": 4, "B-FE2.2": 6, "B-FE2.2R": 0, "B-FE2.2S": 0},
              "stage_actions": ["read retained evidence", "derive Q/D-to-Q safe intervals", "did not create a deck", "did not run HSPICE", "did not enter B-FE2.3 or B-FE3"],
              "input_validation": validation, "input_sha256": source_sha,
              "liberty_constraint_applicability": {"audit_source": str(LATCH_AUDIT.relative_to(FTC_ROOT)),
                  "available_constraint_types": inputs[LATCH_AUDIT]["liberty"]["inputs"]["D"]["timing_constraints"],
                  "direct_numeric_constraint_used": False,
                  "reason": "audited Liberty is 1.10-V typical-max and retained audit has no directly applicable numeric 0.95-V constraint"},
              "baselines": {"0.95": baseline_095, "1.10": baseline_110},
              "historical_110_consistency": historical_110, "selected_corrected_seed": selected}
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "BFE2_2S_SAFE_INTERVALS.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_ROOT / "BFE2_2S_SELECTED_SEED.json").write_text(json.dumps({"stage": "B-FE2.2S", "gate": gate,
        "selected_corrected_seed": selected, "new_hspice_scenarios": 0}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_ROOT / "BFE2_2S_GATE_STATUS.json").write_text(json.dumps({"stage": "B-FE2.2S", "gate": gate,
        "reason": reason, "new_hspice_scenarios": 0, "historical_hspice_scenarios": {"B-FE2.1": 4, "B-FE2.2": 6},
        "selected_seed_present": selected is not None}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_ROOT / "BFE2_2S_REPORT.md").write_text(report(output), encoding="utf-8")
    print(gate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
