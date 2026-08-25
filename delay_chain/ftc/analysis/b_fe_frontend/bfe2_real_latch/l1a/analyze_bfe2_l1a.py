#!/usr/bin/env python3
"""Analyze the two B-FE2-L1A real-safe-domain-latch waveforms.

The analyzer never runs a simulator.  It reads only the two L1A ``.tr0``
products and publishes compact, reviewable evidence.  Every tap keeps its
complete safe_d/Q crossing ledger so a final code cannot hide a transient
failure.  A post-close Q crossing is considered source-backed only when a
same-direction safe_d transition can explain it within the measured
transparent-latch delay envelope; otherwise it is a source-free re-flip.
"""

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import bfe1_frontend  # noqa: E402  # Shared frozen .tr0 parser and constants.


L1A_ROOT = Path(__file__).resolve().parent
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "l1a"
SOURCE_MANIFEST = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "real_snapshot" / "BFE2_2C_SCENARIO_MANIFEST.json"
L1A_MANIFEST = L1A_ROOT / "BFE2_L1A_SCENARIO_MANIFEST.json"
SCENARIOS = ("BFE2L-095-N", "BFE2L-095-L2")
FIXED_CLOSE_PS = 534.524618567
PD_SAFE_V = 0.95
THRESHOLD_V = 0.5 * PD_SAFE_V
RAIL_LOW_V = 0.1 * PD_SAFE_V
RAIL_HIGH_V = 0.9 * PD_SAFE_V
MAX_TRANSPARENT_DQ_PS = 100.0
EPSILON_PS = 1.0e-6


def sha256_file(path: Path) -> str:
    """Hash one generated or immutable input artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    """Read one object-shaped JSON artifact."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def column(trace: Mapping[str, Any], node: str) -> List[float]:
    """Resolve one HSPICE probe column despite its fixed-width label truncation."""

    wanted = "v({}".format(node.lower())
    for label, values in trace["columns"].items():
        if label.lower() == wanted:
            return values
    raise KeyError("missing L1A probe column: {}".format(node))


def crossing_events(times_s: Sequence[float], values: Sequence[float], threshold: float) -> List[Dict[str, float]]:
    """Return linearly interpolated threshold events with absolute ps times."""

    delta = [value - threshold for value in values]
    events: List[Dict[str, float]] = []
    for index in range(1, len(delta)):
        left, right = delta[index - 1], delta[index]
        if left == 0.0:
            crossing_s = times_s[index - 1]
        elif left * right > 0.0 or left == right:
            continue
        else:
            crossing_s = times_s[index - 1] + (-left / (right - left)) * (times_s[index] - times_s[index - 1])
        events.append({
            "time_ps": crossing_s * 1.0e12,
            "direction": "rise" if right >= left else "fall",
        })
    return events


def pair_source_event(q_event: Mapping[str, float], d_events: Sequence[Mapping[str, float]], used: set) -> Dict[str, Any]:
    """Find one causal same-direction safe_d event for a Q transition.

    The 100-ps bound is intentionally wider than the completed BFE2.1
    transparent D-to-Q measurements (approximately 41--63 ps at the relevant
    operating points).  It avoids falsely calling a normal in-flight
    resolution a re-flip while remaining tight enough to reject an unrelated
    later Q transition.
    """

    candidates = []
    for index, d_event in enumerate(d_events):
        if index in used or d_event["direction"] != q_event["direction"]:
            continue
        delay = q_event["time_ps"] - d_event["time_ps"]
        if -EPSILON_PS <= delay <= MAX_TRANSPARENT_DQ_PS:
            candidates.append((delay, index, d_event))
    if not candidates:
        return {"classification": "source-free", "source_event": None, "delay_ps": None}
    delay, index, d_event = min(candidates, key=lambda item: item[0])
    used.add(index)
    return {"classification": "source-backed", "source_event": dict(d_event), "delay_ps": delay}


def code_at(values_by_tap: Sequence[Sequence[float]], index: int) -> str:
    """Encode one sampled Q row using the fixed PD_SAFE/2 threshold."""

    return "".join("1" if values[index] > THRESHOLD_V else "0" for values in values_by_tap)


def analyze_scenario(scenario_id: str) -> Dict[str, Any]:
    """Analyze every required signal and every tap for one L1A scenario."""

    directory = RUN_ROOT / scenario_id.lower().replace("-", "_")
    trace_path = directory / "bfe2_l1a.tr0"
    trace = bfe1_frontend.parse_ascii_tr0(trace_path)
    if trace["record_width"] != 94:
        raise ValueError("L1A trace width changed for {}".format(scenario_id))
    times_s = trace["columns"]["time"]
    g_events = crossing_events(times_s, column(trace, "latch_g"), THRESHOLD_V)
    observed_close_ps = next((event["time_ps"] for event in g_events if event["direction"] == "fall"), None)
    if observed_close_ps is None:
        raise ValueError("missing safe-domain G falling edge for {}".format(scenario_id))
    xor_values = [column(trace, "xor_{:02d}".format(tap)) for tap in range(30)]
    safe_values = [column(trace, "safe_d_{:02d}".format(tap)) for tap in range(30)]
    q_values = [column(trace, "q_{:02d}".format(tap)) for tap in range(30)]
    taps: List[Dict[str, Any]] = []
    for tap in range(30):
        safe_events = crossing_events(times_s, safe_values[tap], THRESHOLD_V)
        q_events = crossing_events(times_s, q_values[tap], THRESHOLD_V)
        post_close = [event for event in q_events if event["time_ps"] > observed_close_ps + EPSILON_PS]
        used = set()
        classifications = []
        for q_event in post_close:
            cause = pair_source_event(q_event, safe_events, used)
            classifications.append({"q_event": q_event, **cause})
        source_free = [item for item in classifications if item["classification"] == "source-free"]
        if source_free:
            classification = "genuine-reflip"
        elif len(post_close) > 1:
            classification = "unresolved"
        elif classifications:
            classification = "single-source-backed-resolution"
        else:
            classification = "zero-crossing"
        final_q = q_values[tap][-1]
        tail_indices = range(max(0, len(times_s) - 3), len(times_s))
        tail_values = [q_values[tap][index] for index in tail_indices]
        taps.append({
            "tap": tap,
            "xor_crossings": crossing_events(times_s, xor_values[tap], THRESHOLD_V),
            "safe_d_crossings": safe_events,
            "q_crossings": q_events,
            "post_close_q_events": classifications,
            "classification": classification,
            "source_free_reflip": bool(source_free),
            "unresolved": classification == "unresolved",
            "final_q_v": final_q,
            "final_mid_rail": not (final_q <= RAIL_LOW_V or final_q >= RAIL_HIGH_V),
            "tail_stable": max(tail_values) - min(tail_values) <= 1.0e-6,
            "tail_values_v": tail_values,
        })
    final_code = code_at(q_values, len(times_s) - 1)
    tail_codes = [code_at(q_values, index) for index in range(max(0, len(times_s) - 3), len(times_s))]
    return {
        "scenario_id": scenario_id,
        "trace_sha256": sha256_file(trace_path),
        "record_count": trace["record_count"],
        "record_width": trace["record_width"],
        "fixed_sample_close_ps": FIXED_CLOSE_PS,
        "observed_g_close_ps": observed_close_ps,
        "g_crossing_minus_requested_ps": observed_close_ps - (bfe1_frontend.LAUNCH_S * 1.0e12 + FIXED_CLOSE_PS),
        "final_q_code": final_code,
        "tail_codes": tail_codes,
        "tail_stable": len(set(tail_codes)) == 1,
        "source_free_reflip_taps": [item["tap"] for item in taps if item["source_free_reflip"]],
        "unresolved_taps": [item["tap"] for item in taps if item["unresolved"]],
        "mid_rail_taps": [item["tap"] for item in taps if item["final_mid_rail"]],
        "unstable_tail_taps": [item["tap"] for item in taps if not item["tail_stable"]],
        "taps": taps,
        "tap27": taps[27],
    }


def main() -> int:
    """Publish the L1A Gate and report, then stop without authorizing L1B."""

    manifest = read_json(L1A_MANIFEST)
    if tuple(manifest.get("scenario_ids", ())) != SCENARIOS or manifest.get("new_hspice_scenarios") != 2:
        raise ValueError("L1A manifest is not the fixed two-scenario physical pair")
    analyses = [analyze_scenario(scenario_id) for scenario_id in SCENARIOS]
    hamming = sum(left != right for left, right in zip(analyses[0]["final_q_code"], analyses[1]["final_q_code"]))
    pass_gate = all(
        not item["source_free_reflip_taps"]
        and not item["unresolved_taps"]
        and not item["mid_rail_taps"]
        and not item["unstable_tail_taps"]
        and item["tail_stable"]
        for item in analyses
    ) and hamming >= 9
    gate = "BFE2_L1A_REAL_SAFE_LATCH_PASS" if pass_gate else "BFE2_L1A_REAL_SAFE_LATCH_FAIL"
    analysis = {
        "schema_version": 1,
        "stage": "B-FE2-L1A",
        "gate": gate,
        "verification_mode": "equivalent causal isolation",
        "fixed_sample_close_ps": FIXED_CLOSE_PS,
        "fixed_pd_safe_v": PD_SAFE_V,
        "final_q_hamming_distance": hamming,
        "source_manifest_sha256": sha256_file(SOURCE_MANIFEST),
        "l1a_manifest_sha256": sha256_file(L1A_MANIFEST),
        "transparent_dq_bound_ps": MAX_TRANSPARENT_DQ_PS,
        "results": analyses,
        "stop_after_l1a": True,
        "next_stage_authorized": False,
    }
    (L1A_ROOT / "BFE2_L1A_ANALYSIS.json").write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    gate_status = {
        "gate": gate,
        "stage": "B-FE2-L1A",
        "capture_cell_review_required": gate == "BFE2_L1A_REAL_SAFE_LATCH_FAIL",
        "failure_follow_up": "BFE2_CAPTURE_CELL_REVIEW_REQUIRED" if gate == "BFE2_L1A_REAL_SAFE_LATCH_FAIL" else None,
        "new_hspice_scenarios": 2,
        "source_free_reflip_taps": sorted({tap for item in analyses for tap in item["source_free_reflip_taps"]}),
        "unresolved_taps": sorted({tap for item in analyses for tap in item["unresolved_taps"]}),
        "mid_rail_taps": sorted({tap for item in analyses for tap in item["mid_rail_taps"]}),
        "final_q_hamming_distance": hamming,
        "stop_after_l1a": True,
        "next_stage_authorized": False,
    }
    (L1A_ROOT / "BFE2_L1A_GATE_STATUS.json").write_text(json.dumps(gate_status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = [
        "# B-FE2-L1A report",
        "",
        "Gate: `{}`".format(gate),
        "",
        "Verification mode: `equivalent causal isolation`.",
        "",
        "The frozen B-FE2.2C 0.95 V normal/L2 XOR waveforms drive zero-delay, full-swing safe_d PWL sources. Thirty real `LATQ_X0P5M_A9TR40` cells are powered only from stable `PD_SAFE=0.95 V`; this is not a complete AMS co-simulation and does not prove a physical level shifter.",
        "",
        "Normal final Q: `{}`".format(analyses[0]["final_q_code"]),
        "",
        "L2 final Q: `{}`".format(analyses[1]["final_q_code"]),
        "",
        "Hamming distance: `{}`".format(hamming),
        "",
        "Normal source-free re-flips: `{}`; L2 source-free re-flips: `{}`.".format(analyses[0]["source_free_reflip_taps"], analyses[1]["source_free_reflip_taps"]),
        "",
        "Normal unresolved taps: `{}`; L2 unresolved taps: `{}`.".format(analyses[0]["unresolved_taps"], analyses[1]["unresolved_taps"]),
        "",
        "Historical tap27 normal classification: `{}`.".format(analyses[0]["tap27"]["classification"]),
        "",
        "Failure follow-up: `BFE2_CAPTURE_CELL_REVIEW_REQUIRED` (no close change, no L1B/L2 entry)." if not pass_gate else "",
        "",
        "No subsequent L1B/L2 stage is authorized by this artifact.",
        "",
    ]
    (L1A_ROOT / "BFE2_L1A_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print(gate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
