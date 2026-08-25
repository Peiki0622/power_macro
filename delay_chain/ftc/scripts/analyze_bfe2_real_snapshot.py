#!/usr/bin/env python3
"""Perform zero-HSPICE B-FE2.2 real-snapshot stability analysis.

The saved HSPICE traces are the sole electrical authority. This script neither
creates decks nor launches a simulator; it checks each physical latch Q after
the common G falling edge and publishes the compact B-FE2.2 Gate.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_bfe1_spatial as spatial  # noqa: E402  # Frozen local-rail logic convention.
import bfe1_frontend  # noqa: E402  # Reviewed ASCII .tr0 reader and labels.


RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "real_snapshot"
OUTPUT_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "real_snapshot"
FIRST_MANIFEST = OUTPUT_ROOT / "BFE2_2_SCENARIO_MANIFEST.json"
RETRY_MANIFEST = OUTPUT_ROOT / "BFE2_2_RETRY_MANIFEST.json"


def read_json(path: Path) -> Dict[str, Any]:
    """Read one required object-shaped B-FE2 evidence artifact."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def trace_path(item: Mapping[str, Any], is_retry: bool) -> Path:
    """Resolve the exact raw trace without guessing between first/retry runs."""

    stem = item["scenario_id"].lower().replace("-", "_")
    if is_retry:
        return RUN_ROOT / "scenarios" / (stem + "_retry_320p334ps") / "bfe2s_retry.tr0"
    return RUN_ROOT / "scenarios" / stem / "bfe2s.tr0"


def q_code(trace: Mapping[str, Any], sample_ps: float) -> Dict[str, Any]:
    """Classify all 30 Q ports against instantaneous local VDD/2.

    Q is a real latch output, not an ideal digital value. Its classification
    retains the B-FE1 moving local-rail rule, so a drooping supply is never
    judged against an invalid fixed absolute threshold.
    """

    absolute_s = (1000.0 + sample_ps) * 1.0e-12
    times = trace["columns"]["time"]
    rail = spatial.interpolate(times, trace["columns"][bfe1_frontend.label_for("vdd_monitored")], absolute_s)
    bits, margins = [], []
    for index in range(30):
        voltage = spatial.interpolate(times, trace["columns"][bfe1_frontend.label_for("q_{}".format(index))], absolute_s)
        bits.append(1 if voltage > 0.5 * rail else 0)
        margins.append(abs(voltage - 0.5 * rail))
    result = spatial.code_metrics(bits)
    result["minimum_bit_margin_v"] = min(margins)
    return result


def q_transition_diagnostics(trace: Mapping[str, Any], close_ps: float) -> Dict[str, Any]:
    """Report post-close Q crossings and declare any re-flip a failure.

    A first post-close crossing can be latch-intrinsic resolution. More than
    one crossing on the same Q means the captured state changes again after G
    has closed, which violates the B-FE2.2 stable-snapshot requirement.
    """

    per_tap, reflip_taps, events = [], [], []
    for index in range(30):
        crossings = spatial.crossing_events(trace, "q_{}".format(index))
        post = sorted(value for value in crossings["rise_ps"] + crossings["fall_ps"] if value > close_ps + spatial.EPSILON_PS)
        per_tap.append({"tap": index, "post_close_crossings_ps": post, "post_close_crossing_count": len(post), "final_resolution_ps": None if not post else post[-1] - close_ps})
        if len(post) > 1:
            reflip_taps.append(index)
        events.extend((value, index) for value in post)
    first = min(events) if events else None
    return {"per_tap": per_tap, "reflip_taps": reflip_taps,
            "first_post_close_event": None if first is None else {"tap": first[1], "after_close_ps": first[0] - close_ps},
            "max_final_resolution_ps": max([record["final_resolution_ps"] or 0.0 for record in per_tap])}


def observed_g_close_ps(trace: Mapping[str, Any]) -> float:
    """Return the one measured local-rail G falling crossing in a snapshot trace.

    ``close_ps`` in a deck is the requested centre of the one-picosecond PWL
    edge.  The physical latch sees the local-threshold G crossing, which can
    differ slightly because HSPICE uses adaptive timesteps and G is judged
    against VDD_MONITORED/2.  Post-close diagnostics must use this measured
    edge, otherwise an event close to G may be assigned to the wrong side.
    """

    falls = spatial.crossing_events(trace, "latch_g")["fall_ps"]
    if len(falls) != 1:
        raise ValueError("B-FE2.2 snapshot requires exactly one measured G falling crossing")
    return falls[0]


def assess(item: Mapping[str, Any], is_retry: bool) -> Dict[str, Any]:
    """Assess one scenario through transition evidence and final Q code."""

    trace = bfe1_frontend.parse_ascii_tr0(trace_path(item, is_retry))
    requested_close_ps = float(item["close_ps"])
    close_ps = observed_g_close_ps(trace)
    samples = [{"after_close_ps": offset, "code": q_code(trace, close_ps + offset)} for offset in (5.0, 20.0, 100.0, 500.0, 5000.0)]
    transitions = q_transition_diagnostics(trace, close_ps)
    final_code = samples[-1]["code"]
    stable = (not transitions["reflip_taps"] and not final_code["empty"] and not final_code["fragmented"] and final_code["minimum_bit_margin_v"] > 1.0e-6)
    return {"scenario_id": item["scenario_id"], "baseline_v": item["baseline_v"], "droop_v": item["droop_v"],
            # Keep both names: requested close identifies the deck, while the
            # observed crossing is the only valid origin for Q timing.
            "requested_close_ps": requested_close_ps, "observed_g_close_ps": close_ps,
            "g_crossing_minus_requested_ps": close_ps - requested_close_ps,
            "evidence_role": "replacement" if is_retry else "first_attempt", "q_samples": samples,
            "transition_diagnostics": transitions, "stable": stable, "final_code": final_code}


def choose_authoritative_scenarios() -> List[Tuple[Mapping[str, Any], bool]]:
    """Replace only failed 0.95-V first evidence; retain passing 1.10-V pair."""

    first = read_json(FIRST_MANIFEST)["scenarios"]
    retry = read_json(RETRY_MANIFEST)["scenarios"] if RETRY_MANIFEST.is_file() else []
    selected = [(item, False) for item in first if float(item["baseline_v"]) == 1.10]
    selected.extend((item, True) for item in retry if float(item["baseline_v"]) == 0.95)
    if len(selected) != 4:
        raise ValueError("B-FE2.2 needs the 1.10-V first pair and the 0.95-V replacement pair")
    return selected


def main() -> int:
    """Publish B-FE2.2 Gate using all authorized paired evidence."""

    assessments = [assess(item, is_retry) for item, is_retry in choose_authoritative_scenarios()]
    pairs = []
    for baseline in (0.95, 1.10):
        group = [item for item in assessments if float(item["baseline_v"]) == baseline]
        normal = next(item for item in group if item["droop_v"] is None)
        l2 = next(item for item in group if item["droop_v"] is not None)
        hamming = sum(left != right for left, right in zip(normal["final_code"]["raw_code"], l2["final_code"]["raw_code"]))
        pairs.append({"baseline_v": baseline, "normal": normal, "l2": l2, "hamming_distance": hamming, "distinguishable": hamming > 0})
    all_stable = all(pair[side]["stable"] for pair in pairs for side in ("normal", "l2"))
    all_distinguishable = all(pair["distinguishable"] for pair in pairs)
    gate = "BFE2_2_REAL_SNAPSHOT_GO" if all_stable and all_distinguishable else "BFE2_2_REAL_SNAPSHOT_CONDITIONAL"
    output = {"schema_version": 2, "stage": "B-FE2.2", "gate": gate,
              # Six distinct snapshot decks were physically simulated: four
              # first attempts plus the one plan-authorized 0.95-V pair.  The
              # script itself only rereads them, so expose both accounting
              # dimensions instead of incorrectly publishing zero runs.
              "executed_new_hspice_scenarios": 6,
              "this_analysis_new_hspice_scenarios": 0,
              "total_bfe2_2_new_hspice_scenarios": 6, "all_q_stable": all_stable, "all_pairs_distinguishable": all_distinguishable,
              "first_attempt_manifest": FIRST_MANIFEST.name, "retry_manifest": RETRY_MANIFEST.name,
              "selection_policy": "retain all first-attempt evidence; use the authorized retry only for the 0.95-V paired Gate decision",
              "pairs": pairs, "reason": "all paired snapshots stable and distinguishable" if gate.endswith("GO") else "at least one permitted-close scenario has a post-close Q re-flip or unresolved spatial code"}
    (OUTPUT_ROOT / "BFE2_2_GATE_STATUS.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(gate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
