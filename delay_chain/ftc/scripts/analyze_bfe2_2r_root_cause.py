#!/usr/bin/env python3
"""Close B-FE2.2R's timing root cause from retained B-FE2.1/B-FE2.2 traces.

This is deliberately an offline evidence stage.  It creates neither a deck nor
a simulator subprocess: every conclusion is reconstructed from the four
B-FE2.1 transparent-latch traces and the six immutable B-FE2.2 snapshot
traces that already exist below ``runs/b_fe_frontend/bfe2_real_latch``.

The key distinction is electrical rather than terminological.  A D event may
cross before G closes while its transparent-latch Q response crosses after G.
That is an in-flight data event, not automatically a second captured state.
Conversely, a later Q crossing with no matching D event cannot be explained as
ordinary transparent D-to-Q propagation and is retained as a genuine
post-close re-flip.  Internal LATQ nodes are not probed, so the script does not
claim to observe a particular feedback transistor; it labels that mechanism
as waveform-consistent closing-feedback recovery with its evidence boundary.
"""

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_bfe1_spatial as spatial  # noqa: E402  # Frozen local-rail threshold definition.
import analyze_bfe2_latch_load as load_analysis  # noqa: E402  # Transparent D→Q pairing authority.
import analyze_bfe2_real_snapshot as snapshot_analysis  # noqa: E402  # Reviewed snapshot trace resolution.
import bfe1_frontend  # noqa: E402  # Reviewed .tr0 parser and probe labels.
import bfe2_latch_load as latch_load  # noqa: E402  # Frozen electrical topology constants.


ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch"
LOAD_ROOT = ANALYSIS_ROOT / "latch_load"
SNAPSHOT_ROOT = ANALYSIS_ROOT / "real_snapshot"
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch"
OUTPUT_ROOT = SNAPSHOT_ROOT / "root_cause"
FIRST_MANIFEST = SNAPSHOT_ROOT / "BFE2_2_SCENARIO_MANIFEST.json"
RETRY_MANIFEST = SNAPSHOT_ROOT / "BFE2_2_RETRY_MANIFEST.json"
LOAD_MANIFEST = LOAD_ROOT / "BFE2_1_SCENARIO_MANIFEST.json"
LATCH_AUDIT = ANALYSIS_ROOT / "BFE2_0_LATCH_CELL_AUDIT.json"


def read_json(path: Path) -> Dict[str, Any]:
    """Read one required object evidence file without modifying its contents."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def sha256_file(path: Path) -> str:
    """Hash a retained source in bounded memory for provenance verification."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot_directory(item: Mapping[str, Any], attempt: str) -> Path:
    """Resolve an immutable first-attempt or retry folder without fallback.

    A retry is intentionally in its task-specific suffix, never in the first
    attempt's directory.  Missing input therefore stops the analysis instead
    of silently substituting a later waveform for historical failure evidence.
    """

    stem = str(item["scenario_id"]).lower().replace("-", "_")
    if attempt == "retry":
        return RUN_ROOT / "real_snapshot" / "scenarios" / (stem + "_retry_320p334ps")
    if attempt == "first_attempt":
        return RUN_ROOT / "real_snapshot" / "scenarios" / stem
    raise ValueError("unknown B-FE2.2 attempt identity: {}".format(attempt))


def snapshot_files(item: Mapping[str, Any], attempt: str) -> Tuple[Path, Path]:
    """Return the exact deck and .tr0 names for one immutable snapshot case."""

    directory = snapshot_directory(item, attempt)
    stem = "bfe2s_retry" if attempt == "retry" else "bfe2s"
    deck, trace = directory / (stem + ".sp"), directory / (stem + ".tr0")
    if not deck.is_file() or not trace.is_file():
        raise FileNotFoundError("missing retained B-FE2.2 {} evidence: {}".format(attempt, directory))
    return deck, trace


def deck_g_pwl(deck: Path) -> str:
    """Extract the one common G source line as a signature-bearing parameter."""

    lines = [line.strip() for line in deck.read_text(encoding="ascii").splitlines()
             if line.strip().startswith("V_LATCH_G latch_g vss_a PWL")]
    if len(lines) != 1:
        raise ValueError("expected exactly one finite latch-G PWL source: {}".format(deck))
    return lines[0]


def signature_id(signature: Mapping[str, Any]) -> str:
    """Return a canonical SHA256 ID for a fully explicit electrical signature."""

    payload = json.dumps(signature, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def snapshot_signature(item: Mapping[str, Any], attempt: str, load_entry: Mapping[str, Any], deck: Path) -> Dict[str, Any]:
    """Build a reproducible snapshot signature from retained deck and B-FE2.1 facts.

    The first B-FE2.2 runner predated signature recording, so this function
    reconstructs—not guesses—the missing signature.  Inherited topology,
    cells, model SHA, rail waveform and solver version come from the matching
    B-FE2.1 manifest; the concrete finite G PWL and requested close come from
    the exact B-FE2.2 deck/manifest.  The deck SHA remains separately stored
    so the signature is not a substitute for byte-level provenance.
    """

    inherited = load_entry["electrical_signature"]
    return {
        "topology_version": "bfe2_2_30_xor_30_real_latq_single_finite_g_close_v1",
        "attempt": attempt,
        "rvt_lvt_buffer_cells": inherited["rvt_lvt_buffer_cells"],
        "xor_cell": inherited["xor_cell"],
        "latch_cell": inherited["latch_cell"],
        "power_semantics": "all XOR/LATQ cells use VDD_MONITORED/vss_a; external ideal G research source",
        "baseline_v": item["baseline_v"], "droop_v": item["droop_v"],
        "phase_ps": load_entry["phase_ps"], "authority_scenario_key": load_entry["authority_scenario_key"],
        "s_clk_pwl": inherited["s_clk_pwl"], "g_pwl": deck_g_pwl(deck),
        "requested_close_ps": item["close_ps"], "model_sha256": inherited["model_sha256"],
        "hspice_version": item["hspice_version"], "tran_step_ps": inherited["tran_step_ps"],
    }


def event_list(trace: Mapping[str, Any], node: str) -> List[Dict[str, Any]]:
    """Return local-rail threshold crossings in a one-list direction-aware form."""

    crossings = spatial.crossing_events(trace, node)
    events = [{"time_ps": time_ps, "direction": "rise"} for time_ps in crossings["rise_ps"]]
    events.extend({"time_ps": time_ps, "direction": "fall"} for time_ps in crossings["fall_ps"])
    return sorted(events, key=lambda event: event["time_ps"])


def closest_matching_delay(d_event: Mapping[str, Any], pairs: Iterable[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """Find the same-direction transparent D→Q measurement nearest a D event."""

    candidates = [pair for pair in pairs if pair["direction"] == d_event["direction"]]
    if not candidates:
        return None
    return min(candidates, key=lambda pair: abs(pair["d_cross_ps"] - d_event["time_ps"]))


def q_voltage_and_rail(trace: Mapping[str, Any], tap: int, time_ps: float) -> Dict[str, float]:
    """Sample Q and VDD at an event time to retain the shared threshold basis."""

    absolute_s = (spatial.LAUNCH_PS + time_ps) * 1.0e-12
    columns, times = trace["columns"], trace["columns"]["time"]
    rail = spatial.interpolate(times, columns[bfe1_frontend.label_for("vdd_monitored")], absolute_s)
    q = spatial.interpolate(times, columns[bfe1_frontend.label_for("q_{}".format(tap))], absolute_s)
    return {"q_v": q, "vdd_monitored_v": rail, "local_threshold_v": 0.5 * rail}


IN_FLIGHT_MATCH_TOLERANCE_PS = 5.0


def classify_post_close_event(event: Mapping[str, Any], d_events: List[Mapping[str, Any]], transparent_pairs: List[Mapping[str, Any]], observed_close_ps: float) -> Dict[str, Any]:
    """Classify one post-G Q crossing without claiming unprobed internal state.

    ``in_flight_data_event`` requires a pre-close same-direction D event, an
    exact transparent-reference pair, *and* agreement with the predicted Q
    time inside ``IN_FLIGHT_MATCH_TOLERANCE_PS``.  This last guard prevents a
    much later Q crossing from being incorrectly paired to an old D event
    merely because its direction happens to match.  A Q event without a
    time-consistent D source is a genuine post-close re-flip at external Q.
    If it follows an in-flight event, the topology and missing D transition
    make it consistent with closing-feedback recovery; this is intentionally
    not elevated to direct proof of an unprobed internal feedback node.
    """

    preceding = [d_event for d_event in d_events if d_event["direction"] == event["direction"] and
                 d_event["time_ps"] <= observed_close_ps + spatial.EPSILON_PS]
    if preceding:
        d_event = preceding[-1]
        reference = closest_matching_delay(d_event, transparent_pairs)
        if reference is not None:
            expected_q = d_event["time_ps"] + reference["d_to_q_delay_ps"]
            prediction_error = event["time_ps"] - expected_q
            if abs(prediction_error) <= IN_FLIGHT_MATCH_TOLERANCE_PS:
                return {"classification": "normal_in_flight_data_event", "q_event": event,
                        "source_d_event": d_event, "transparent_reference": reference,
                        "expected_q_cross_ps": expected_q,
                        "prediction_error_ps": prediction_error,
                        "after_observed_g_close_ps": event["time_ps"] - observed_close_ps,
                        "interpretation": "D crossed before G; its measured transparent D-to-Q response completed after G"}
    same_direction_d = [d_event for d_event in d_events if d_event["direction"] == event["direction"]]
    return {"classification": "genuine_post_close_reflip", "q_event": event,
            "same_direction_d_events": same_direction_d,
            "after_observed_g_close_ps": event["time_ps"] - observed_close_ps,
            "mechanism_assessment": "consistent_with_closing_feedback_recovery" if not same_direction_d else "not_explained_by_time_consistent_preclose_inflight_event",
            "internal_mechanism_proof": "not_directly_observable_without_internal_LATQ_nodes",
            "interpretation": "Q crossed after G without a same-direction D threshold crossing; this is not normal transparent D-to-Q propagation"}


def analyze_snapshot(item: Mapping[str, Any], attempt: str, load_entry: Mapping[str, Any], transparent: Mapping[str, Any]) -> Dict[str, Any]:
    """Analyze G/D/Q/VDD causality for every tap of one saved snapshot trace."""

    deck, trace_path = snapshot_files(item, attempt)
    trace = bfe1_frontend.parse_ascii_tr0(trace_path)
    observed_close_ps = snapshot_analysis.observed_g_close_ps(trace)
    transparent_by_tap = {entry["tap"]: entry for entry in transparent["per_tap"]}
    per_tap, all_reflips = [], []
    for tap in range(30):
        d_events, q_events = event_list(trace, "xor_{}".format(tap)), event_list(trace, "q_{}".format(tap))
        post_q_events = [event for event in q_events if event["time_ps"] > observed_close_ps + spatial.EPSILON_PS]
        classified = [classify_post_close_event(event, d_events, transparent_by_tap[tap]["matched_d_to_q_events"], observed_close_ps)
                      for event in post_q_events]
        for record in classified:
            record["q_and_vdd_at_crossing"] = q_voltage_and_rail(trace, tap, record["q_event"]["time_ps"])
            if record["classification"] == "genuine_post_close_reflip":
                all_reflips.append(tap)
        per_tap.append({"tap": tap, "d_events": d_events, "q_events": q_events,
                        "post_close_event_classification": classified})
    signature = snapshot_signature(item, attempt, load_entry, deck)
    return {"attempt": attempt, "scenario_id": item["scenario_id"], "baseline_v": item["baseline_v"],
            "droop_v": item["droop_v"], "requested_close_ps": item["close_ps"],
            "observed_g_close_ps": observed_close_ps,
            "deck_path": str(deck.relative_to(FTC_ROOT)), "deck_sha256": sha256_file(deck),
            "tr0_path": str(trace_path.relative_to(FTC_ROOT)), "tr0_sha256": sha256_file(trace_path),
            "electrical_signature": signature, "electrical_signature_id": signature_id(signature),
            "source_bfe2_1_scenario": load_entry["scenario_id"],
            "source_transparent_dq_artifact": "latch_load/BFE2_1_TRANSPARENT_DQ_TIMING.json",
            "reflip_taps": sorted(set(all_reflips)), "per_tap": per_tap}


def root_cause_verdict(records: List[Mapping[str, Any]]) -> Dict[str, Any]:
    """Apply the narrow B-FE2.2R verdict from the observed 0.95-V retry.

    The gate is CONFIRMED only if the specified tap has both signatures: its
    post-close fall predicts from the matching pre-close D event using the
    transparent reference, and a later Q rise has no corresponding D rise.
    The tolerance is deliberately 5 ps, five saved transient steps, and is a
    classification tolerance rather than a claimed design margin.
    """

    retry_normal = next(record for record in records if record["attempt"] == "retry" and
                        float(record["baseline_v"]) == 0.95 and record["droop_v"] is None)
    tap6 = next(record for record in retry_normal["per_tap"] if record["tap"] == 6)
    events = tap6["post_close_event_classification"]
    inflight = [event for event in events if event["classification"] == "normal_in_flight_data_event"]
    reflips = [event for event in events if event["classification"] == "genuine_post_close_reflip"]
    if inflight and reflips and abs(inflight[0]["prediction_error_ps"]) <= 5.0:
        gate = "BFE2_2R_ROOT_CAUSE_CONFIRMED"
        reason = "0.95-V normal retry tap 6 has a pre-close D fall whose transparent D-to-Q delay predicts the first post-G Q fall, followed by a Q rise with no D-rise source"
    elif inflight or reflips:
        gate = "BFE2_2R_ROOT_CAUSE_INCONCLUSIVE"
        reason = "some post-close behavior is observed, but the retained waveforms do not establish both in-flight propagation and later source-free Q re-flip"
    else:
        gate = "BFE2_2R_ROOT_CAUSE_DISPROVED"
        reason = "the retained retry waveform does not contain the claimed tap-6 post-close sequence"
    return {"gate": gate, "reason": reason, "focus_scenario": "retry BFE2L-095-N", "focus_tap": 6,
            "classification_tolerance_ps": IN_FLIGHT_MATCH_TOLERANCE_PS,
            "no_new_hspice_scenarios": True,
            "root_cause": "XOR-only RAW_CODE platform selection omitted real transparent-latch D-to-Q propagation and closing setup/hold behavior",
            "closing_feedback_boundary": "source-free Q re-flip is proven at Q; a specific internal feedback node is not probed, so feedback recovery is waveform-consistent rather than directly observed"}


def ledger(manifests: Mapping[str, Mapping[str, Any]], records: List[Mapping[str, Any]]) -> Dict[str, Any]:
    """Retain immutable first/retry lineage and reconcile physical-run counts."""

    return {"schema_version": 1, "stage": "B-FE2.2R", "this_stage_new_hspice_scenarios": 0,
            "executed_new_hspice_scenarios": {"B-FE2.1": 4, "B-FE2.2": 6, "B-FE2.2R": 0},
            "source_manifests": [{"path": str(path.relative_to(FTC_ROOT)), "sha256": sha256_file(path)}
                                 for path in (LOAD_MANIFEST, FIRST_MANIFEST, RETRY_MANIFEST, LATCH_AUDIT)],
            "attempt_policy": "first_attempt and retry are separate immutable evidence sets; retry never overwrites first_attempt",
            "first_attempt": [record for record in records if record["attempt"] == "first_attempt"],
            "retry": [record for record in records if record["attempt"] == "retry"]}


def report(verdict: Mapping[str, Any], records: List[Mapping[str, Any]]) -> str:
    """Render the concise human review that points back to machine evidence."""

    focus = next(record for record in records if record["attempt"] == "retry" and
                 float(record["baseline_v"]) == 0.95 and record["droop_v"] is None)
    tap6 = next(record for record in focus["per_tap"] if record["tap"] == 6)
    events = tap6["post_close_event_classification"]
    inflight = next(event for event in events if event["classification"] == "normal_in_flight_data_event")
    reflip = next(event for event in events if event["classification"] == "genuine_post_close_reflip")
    return """# B-FE2.2R 根因闭合\n\n- Gate：`{gate}`；本阶段新增 HSPICE：0。\n- 0.95 V normal retry 的实测 G 关闭为 {g:.6f} ps。tap 6 的 XOR/D 在 {d:.6f} ps 下穿；透明态 B-FE2.1 同方向实测 D→Q 延迟为 {delay:.6f} ps，预测 Q 下穿 {expected:.6f} ps，而快照实测为 {actual:.6f} ps（误差 {error:.6f} ps）。因此这是关闭前已进入锁存器、关闭后完成的正常 in-flight 数据响应。\n- 同一 tap 的 Q 随后在 {rise:.6f} ps 上穿；不存在可在透明态实测 D→Q 延迟内预测该上穿的 XOR/D 上穿。因此这是外部 Q 端真正关闭后再翻转，不能归为正常透明态 D→Q 传播。闭锁反馈恢复与此一致；内部 LATQ 节点未探测，故不声称已直接观测到具体反馈晶体管。\n- 新规则：不得再把 XOR `RAW_CODE` 平台中点直接作为 G 关闭时刻。未来真实关闭仿真前，normal/L2 成对候选必须位于 Q 空间码稳定区，并证明相关 pre-close D 事件已按实测透明态 D→Q 延迟传播完成；还必须留出 Liberty setup/hold 或晶体管级等效余量。该规则不是新的关闭点，本轮未运行 HSPICE，也未进入 B-FE2.3/B-FE3。\n\n机器证据：`real_snapshot/root_cause/BFE2_2R_ROOT_CAUSE.json` 与 `BFE2_2R_EVIDENCE_LEDGER.json`。\n""".format(g=focus["observed_g_close_ps"], d=inflight["source_d_event"]["time_ps"],
             delay=inflight["transparent_reference"]["d_to_q_delay_ps"], expected=inflight["expected_q_cross_ps"],
             actual=inflight["q_event"]["time_ps"], error=inflight["prediction_error_ps"],
             rise=reflip["q_event"]["time_ps"], gate=verdict["gate"])


def main() -> int:
    """Generate B-FE2.2R evidence entirely by rereading immutable HSPICE outputs."""

    load_manifest, first_manifest, retry_manifest = read_json(LOAD_MANIFEST), read_json(FIRST_MANIFEST), read_json(RETRY_MANIFEST)
    if len(load_manifest.get("scenarios", [])) != 4 or len(first_manifest.get("scenarios", [])) != 4 or len(retry_manifest.get("scenarios", [])) != 2:
        raise ValueError("B-FE2.2R requires retained 4/4/2 B-FE2 evidence cardinalities")
    transparent = read_json(LOAD_ROOT / "BFE2_1_TRANSPARENT_DQ_TIMING.json")
    load_by_id = {entry["scenario_id"]: entry for entry in load_manifest["scenarios"]}
    records = []
    for item in first_manifest["scenarios"]:
        records.append(analyze_snapshot(item, "first_attempt", load_by_id[item["scenario_id"]],
                                        next(entry for entry in transparent["scenarios"] if entry["scenario_id"] == item["scenario_id"])))
    for item in retry_manifest["scenarios"]:
        records.append(analyze_snapshot(item, "retry", load_by_id[item["scenario_id"]],
                                        next(entry for entry in transparent["scenarios"] if entry["scenario_id"] == item["scenario_id"])))
    verdict = root_cause_verdict(records)
    root_cause = {"schema_version": 1, "stage": "B-FE2.2R", "new_hspice_scenarios": 0,
                  "executed_new_hspice_scenarios": {"B-FE2.1": 4, "B-FE2.2": 6},
                  "verdict": verdict, "future_close_seed_rule": {
                      "prohibited": "do not use an XOR RAW_CODE platform midpoint directly as G close",
                      "required": ["normal/L2 pair shares one candidate close", "candidate lies in clean Q spatial-code stable intervals", "all relevant pre-close D events have completed measured transparent D-to-Q propagation before G", "apply available Liberty setup/hold constraints or a transistor-level equivalent margin", "retain first-attempt and retry evidence independently"],
                      "this_stage_actions": "offline analysis only; no new close time and no HSPICE"},
                  "snapshots": records}
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "BFE2_2R_ROOT_CAUSE.json").write_text(json.dumps(root_cause, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_ROOT / "BFE2_2R_EVIDENCE_LEDGER.json").write_text(json.dumps(ledger(
        {"load": load_manifest, "first": first_manifest, "retry": retry_manifest}, records), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_ROOT / "BFE2_2R_REPORT.md").write_text(report(verdict, records), encoding="utf-8")
    print(verdict["gate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
