#!/usr/bin/env python3
"""Analyze the retained B-FE2.2C corrected-seed pair without simulation.

The runner has already produced exactly two 0.95-V traces.  This stage keeps
the physical evidence immutable and performs the Gate decision offline.  A
post-close Q crossing is not automatically rejected: the first crossing may
be a normal transparent-latch resolution when a pre-close same-direction D
event and the measured B-FE2.1 D-to-Q delay predict it.  A second crossing on
the same tap with no time-consistent D source remains a genuine re-flip, even
when the final Q code later settles.  That distinction is the central reason
for this separate analysis stage.
"""

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))

import analyze_bfe1_spatial as spatial  # noqa: E402  # Frozen local-rail thresholds and crossings.
import analyze_bfe2_2r_root_cause as root_cause  # noqa: E402  # Reviewed D/Q causal pairing rule.
import analyze_bfe2_real_snapshot as snapshot  # noqa: E402  # Q-code metrics against local VDD/2.
import bfe1_frontend  # noqa: E402  # Frozen .tr0 parser and probe labels.


ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch"
SNAPSHOT_ROOT = ANALYSIS_ROOT / "real_snapshot"
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "real_snapshot" / "corrected_seed_534p525ps"
OUTPUT_ROOT = SNAPSHOT_ROOT / "corrected_seed"
CORRECTED_MANIFEST = SNAPSHOT_ROOT / "BFE2_2C_SCENARIO_MANIFEST.json"
TRANSPARENT_TIMING = ANALYSIS_ROOT / "latch_load" / "BFE2_1_TRANSPARENT_DQ_TIMING.json"
SEED_EVIDENCE = SNAPSHOT_ROOT / "safe_seed_revised" / "BFE2_2S_REVISED_SELECTED_SEED.json"
FORMAL_GATE = SNAPSHOT_ROOT / "BFE2_2_GATE_STATUS.json"
ROOT_CAUSE = SNAPSHOT_ROOT / "root_cause" / "BFE2_2R_ROOT_CAUSE.json"
ROOT_LEDGER = SNAPSHOT_ROOT / "root_cause" / "BFE2_2R_EVIDENCE_LEDGER.json"
SCENARIO_IDS = ("BFE2L-095-N", "BFE2L-095-L2")
TAIL_SAMPLE_OFFSETS_PS = (100.0, 500.0, 5000.0)


def read_json(path: Path) -> Dict[str, Any]:
    """Read one object-shaped evidence artifact and reject malformed input."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def sha256_file(path: Path) -> str:
    """Hash a source or raw waveform in bounded memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def input_sha256() -> List[Dict[str, str]]:
    """Record the immutable JSON inputs that control this offline decision."""

    paths = (CORRECTED_MANIFEST, TRANSPARENT_TIMING, SEED_EVIDENCE,
             FORMAL_GATE, ROOT_CAUSE, ROOT_LEDGER)
    return [{"path": str(path.relative_to(FTC_ROOT)), "sha256": sha256_file(path)} for path in paths]


def scenario_trace(scenario_id: str) -> Path:
    """Resolve one corrected trace without falling back to historical paths."""

    return RUN_ROOT / scenario_id.lower().replace("-", "_") / "bfe2c_corrected.tr0"


def validate_manifest(manifest: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """Validate the two-scenario identity and byte-level raw evidence links."""

    entries = manifest.get("scenarios")
    if not isinstance(entries, list) or tuple(item.get("scenario_id") for item in entries) != SCENARIO_IDS:
        raise ValueError("B-FE2.2C manifest is not the fixed normal/L2 pair")
    if manifest.get("requested_close_ps") is None or manifest.get("new_hspice_scenarios") not in (0, 1, 2):
        raise ValueError("invalid B-FE2.2C manifest budget fields")
    for entry in entries:
        trace = scenario_trace(entry["scenario_id"])
        if not trace.is_file():
            raise FileNotFoundError("missing corrected-seed trace: {}".format(trace))
        if sha256_file(trace) != entry["tr0_sha256"]:
            raise ValueError("corrected-seed trace SHA mismatch: {}".format(trace))
    return entries


def classify_tap(close_ps: float, tap: int, trace: Mapping[str, Any], transparent_entry: Mapping[str, Any]) -> Dict[str, Any]:
    """Classify all post-close Q crossings for one tap.

    The first event can be ``normal-in-flight-resolution``.  If a second event
    lacks a D source that predicts it within the reviewed 5-ps causal matching
    tolerance, the tap is ``genuine-reflip``.  Multiple normal events are
    ``unresolved`` rather than being hidden by selecting one.  This keeps the
    revised single-resolution allowance while preserving the original safety
    prohibition against a source-free second Q transition.
    """

    d_events = root_cause.event_list(trace, "xor_{}".format(tap))
    q_events = root_cause.event_list(trace, "q_{}".format(tap))
    post_q = [event for event in q_events if event["time_ps"] > close_ps + spatial.EPSILON_PS]
    classified = [root_cause.classify_post_close_event(
        event, d_events, transparent_entry["matched_d_to_q_events"], close_ps) for event in post_q]
    normal = [item for item in classified if item["classification"] == "normal_in_flight_data_event"]
    genuine = [item for item in classified if item["classification"] == "genuine_post_close_reflip"]
    if genuine:
        classification = "genuine-reflip"
    elif len(normal) > 1:
        classification = "unresolved"
    elif normal:
        classification = "single-normal-resolution"
    else:
        classification = "zero-crossing"
    for item in classified:
        item["q_and_vdd_at_crossing"] = root_cause.q_voltage_and_rail(trace, tap, item["q_event"]["time_ps"])
    return {
        "tap": tap,
        "classification": classification,
        "d_events": d_events,
        "q_events": q_events,
        "post_close_event_classification": classified,
        "post_close_event_count": len(classified),
        "post_close_resolution_ps": max((event["q_event"]["time_ps"] - close_ps for event in classified), default=0.0),
    }


def analyze_scenario(entry: Mapping[str, Any], transparent_by_tap: Mapping[int, Mapping[str, Any]]) -> Dict[str, Any]:
    """Analyze G, D/XOR, Q and local VDD for all 30 taps in one trace."""

    trace_path = scenario_trace(entry["scenario_id"])
    trace = bfe1_frontend.parse_ascii_tr0(trace_path)
    if trace["record_width"] != 124:
        raise ValueError("corrected-seed trace violates the 124-column contract")
    observed_close_ps = snapshot.observed_g_close_ps(trace)
    samples = [{"after_close_ps": offset, "code": snapshot.q_code(trace, observed_close_ps + offset)}
               for offset in (5.0, 20.0, 100.0, 500.0, 5000.0)]
    tap_records = [classify_tap(observed_close_ps, tap, trace, transparent_by_tap[tap]) for tap in range(30)]
    final_code = samples[-1]["code"]
    tail_codes = [sample["code"]["raw_code"] for sample in samples if sample["after_close_ps"] in TAIL_SAMPLE_OFFSETS_PS]
    # ``analyze_bfe2_real_snapshot.q_code`` uses the established compact
    # ``code_metrics`` schema, which omits an undefined-bit counter because
    # interpolation always produces a binary comparison.  Preserve that
    # schema rather than inventing a second metric; ``empty``/``fragmented``
    # plus the positive local-rail margin are the authoritative validity test.
    final_q_stable = (len(set(tail_codes)) == 1 and not final_code["empty"] and
                      not final_code["fragmented"] and final_code["minimum_bit_margin_v"] > 1.0e-6)
    genuine = [item["tap"] for item in tap_records if item["classification"] == "genuine-reflip"]
    unresolved = [item["tap"] for item in tap_records if item["classification"] == "unresolved"]
    normal = [item["tap"] for item in tap_records if item["classification"] == "single-normal-resolution"]
    normal_inflight = [item["tap"] for item in tap_records
                       if any(event["classification"] == "normal_in_flight_data_event"
                              for event in item["post_close_event_classification"])]
    return {
        "scenario_id": entry["scenario_id"],
        "baseline_v": entry["baseline_v"],
        "droop_v": entry["droop_v"],
        "requested_close_ps": entry["requested_close_ps"],
        "observed_g_close_ps": observed_close_ps,
        "g_crossing_minus_requested_ps": observed_close_ps - float(entry["requested_close_ps"]),
        "deck_sha256": entry["deck_sha256"],
        "tr0_sha256": entry["tr0_sha256"],
        "electrical_signature_id": entry["electrical_signature_id"],
        "q_samples": samples,
        "per_tap": tap_records,
        "zero_crossing_taps": [item["tap"] for item in tap_records if item["classification"] == "zero-crossing"],
        "single_normal_resolution_taps": normal,
        # Keep this event-level view separate from the tap-level final
        # classification.  Tap 27 in the failed normal case has one permitted
        # normal in-flight event followed by a prohibited source-free re-flip;
        # collapsing it to only ``genuine-reflip`` would hide that distinction.
        "normal_inflight_resolution_taps": normal_inflight,
        "genuine_reflip_taps": genuine,
        "unresolved_taps": unresolved,
        "worst_post_close_resolution_ps": max((item["post_close_resolution_ps"] for item in tap_records), default=0.0),
        "final_q_code": final_code,
        "final_q_stable": final_q_stable,
        "normal_inflight_allowed_by_revised_rule": True,
    }


def main() -> int:
    """Publish B-FE2.2C analysis and stop the chain on a failed corrected seed."""

    manifest = read_json(CORRECTED_MANIFEST)
    entries = validate_manifest(manifest)
    timing = read_json(TRANSPARENT_TIMING)
    timing_by_id = {entry["scenario_id"]: entry for entry in timing["scenarios"]}
    transparent_by_scenario = {scenario_id: {entry["tap"]: entry for entry in timing_by_id[scenario_id]["per_tap"]}
                               for scenario_id in SCENARIO_IDS}
    analyses = [analyze_scenario(entry, transparent_by_scenario[entry["scenario_id"]]) for entry in entries]
    normal = analyses[0]
    l2 = analyses[1]
    hamming = sum(left != right for left, right in zip(normal["final_q_code"]["raw_code"], l2["final_q_code"]["raw_code"]))
    reflip_taps = sorted(set(normal["genuine_reflip_taps"] + l2["genuine_reflip_taps"]))
    unresolved_taps = sorted(set(normal["unresolved_taps"] + l2["unresolved_taps"]))
    normal_l2_stable = normal["final_q_stable"] and l2["final_q_stable"]
    gate = "BFE2_2_REAL_SNAPSHOT_GO" if (normal_l2_stable and not reflip_taps and not unresolved_taps and hamming > 0) else "BFE2_2C_CORRECTED_SEED_FAILED"
    reason = ("corrected 0.95-V normal/L2 pair is stable, distinguishable, and has no genuine re-flip"
              if gate == "BFE2_2_REAL_SNAPSHOT_GO" else
              "corrected seed has a genuine source-free post-close Q re-flip or unresolved tap; retain B-FE2.2 conditional and stop before B-FE2.3")
    output = {
        "schema_version": 1,
        "stage": "B-FE2.2C-analysis",
        "gate": gate,
        "reason": reason,
        "new_hspice_scenarios": 0,
        "executed_new_hspice_scenarios": {"B-FE2.1": 4, "B-FE2.2": 8, "B-FE2.2C-analysis": 0},
        "input_sha256": input_sha256(),
        "classification_tolerance_ps": root_cause.IN_FLIGHT_MATCH_TOLERANCE_PS,
        "classification_tolerance_is_not_safety_margin": True,
        "corrected_seed_interval_ps": [read_json(SEED_EVIDENCE)["selected_corrected_seed"]["interval_start_ps"],
                                       read_json(SEED_EVIDENCE)["selected_corrected_seed"]["interval_end_ps"]],
        "normal_l2_hamming_distance": hamming,
        "minimum_q_bit_margin_v": min(normal["final_q_code"]["minimum_bit_margin_v"], l2["final_q_code"]["minimum_bit_margin_v"]),
        "genuine_reflip_taps": reflip_taps,
        "unresolved_taps": unresolved_taps,
        "normal_inflight_resolution_taps": {
            "normal": normal["normal_inflight_resolution_taps"],
            "l2": l2["normal_inflight_resolution_taps"],
        },
        "normal_l2_final_q_stable": normal_l2_stable,
        "historical_evidence_preserved": {
            "formal_gate": str(FORMAL_GATE.relative_to(FTC_ROOT)),
            "root_cause": str(ROOT_CAUSE.relative_to(FTC_ROOT)),
            "root_cause_ledger": str(ROOT_LEDGER.relative_to(FTC_ROOT)),
        },
        "scenarios": analyses,
        "bfe2_3_authorized": gate == "BFE2_2_REAL_SNAPSHOT_GO",
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "BFE2_2C_ANALYSIS.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_ROOT / "BFE2_2C_GATE_STATUS.json").write_text(json.dumps({
        "stage": "B-FE2.2C-analysis", "gate": gate, "reason": reason,
        "new_hspice_scenarios": 0, "genuine_reflip_taps": reflip_taps,
        "unresolved_taps": unresolved_taps, "bfe2_3_authorized": gate == "BFE2_2_REAL_SNAPSHOT_GO",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    selected = "normal tap 27" if 27 in normal["genuine_reflip_taps"] else "none"
    report = """# B-FE2.2C corrected seed 离线分析

- Gate：`{gate}`；本分析新增 HSPICE：0；物理 pair 新增 HSPICE：2。
- corrected requested close：`{close:.9f} ps`；normal 实测 G：`{gn:.9f} ps`；L2 实测 G：`{gl:.9f} ps`。
- 修订判据审查：第一次由 pre-close D 和实测 D→Q 延迟解释的 post-close resolution 被保留为正常单次 resolution；只有同一 tap 的第二次无时间一致 D 源 Q crossing 才列为 genuine re-flip。
- normal single-resolution taps：{normal}; L2 single-resolution taps：{l2}；事件级 normal in-flight taps：normal {normal_inflight_n}、L2 {normal_inflight_l2}。
- genuine re-flip taps：{reflips}；unresolved taps：{unresolved}；重点证据：{selected}。
- normal/L2 最终 Hamming distance：`{ham}`；最小 Q bit margin：`{margin:.9f} V`；最差 post-close resolution：`{worst:.6f} ps`。
- 结论：{reason}。B-FE2.3 未授权；不得再尝试新的关闭时刻。旧 6 场景、首次失败、retry 和 B-FE2.2R root-cause evidence 均未覆盖。
    """.format(gate=gate, close=normal["requested_close_ps"], gn=normal["observed_g_close_ps"], gl=l2["observed_g_close_ps"],
           normal=normal["single_normal_resolution_taps"], l2=l2["single_normal_resolution_taps"],
           normal_inflight_n=normal["normal_inflight_resolution_taps"], normal_inflight_l2=l2["normal_inflight_resolution_taps"],
           reflips=reflip_taps,
           unresolved=unresolved_taps, selected=selected, ham=hamming,
           margin=output["minimum_q_bit_margin_v"], worst=max(normal["worst_post_close_resolution_ps"], l2["worst_post_close_resolution_ps"]), reason=reason)
    # Normalize the generated Markdown terminator so the evidence is stable
    # across Python indentation changes and passes repository whitespace checks.
    (OUTPUT_ROOT / "BFE2_2C_REPORT.md").write_text(report.rstrip() + "\n", encoding="utf-8")
    print(gate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
