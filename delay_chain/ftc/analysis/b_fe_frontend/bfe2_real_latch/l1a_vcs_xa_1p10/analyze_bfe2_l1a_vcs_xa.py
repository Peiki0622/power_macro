#!/usr/bin/env python3
"""Analyze the two completed container VCS-XA L1A scenarios.

The analyzer is intentionally deterministic and does not invoke a simulator.
It correlates the frozen safe_d crossing ledger with the XA boundary CSV,
classifies every post-close Q event, checks the two sampled tail points, and
publishes a machine-readable Gate plus a concise review report.  The final
Gate is allowed to fail on the measured Hamming distance even when the real
latch itself is stable; this keeps capture-cell and spatial-code failures
distinct.
"""

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

ROOT = Path(__file__).resolve().parents[4]
RUN_ROOT = ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "l1a_vcs_xa_1p10"
OUT_ROOT = ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "l1a_vcs_xa_1p10"
SCENARIOS = ("bfe2l_095_n", "bfe2l_095_l2")
DISPLAY = {"bfe2l_095_n": "BFE2L-095-N", "bfe2l_095_l2": "BFE2L-095-L2"}
CLOSE_PS = 1534.524618567  # launch=1000 ps + frozen sample_close
VDD_SAFE = 1.10
SAFE_HIGH = 0.95
RAIL_LOW = 0.1 * VDD_SAFE
RAIL_HIGH = 0.9 * VDD_SAFE


def sha256(path: Path) -> str:
    """Hash a retained evidence file."""

    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_rows(path: Path) -> List[Dict[str, Any]]:
    """Parse the typed XA boundary CSV and reject malformed rows."""

    rows: List[Dict[str, Any]] = []
    with path.open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            row["tap"] = int(row["tap"])
            for key in ("time_ps", "safe_d_v", "q_v", "vdd_sense_v", "vdd_safe_v", "g_v"):
                row[key] = float(row[key])
            rows.append(row)
    return rows


def load_ledger(path: Path) -> Dict[str, List[Mapping[str, Any]]]:
    """Load the exact source-domain threshold crossing ledger."""

    value = json.loads(path.read_text(encoding="utf-8"))
    return value


def analyze_scenario(scenario: str) -> Dict[str, Any]:
    """Return complete per-tap evidence for one fixed physical scenario."""

    directory = RUN_ROOT / scenario
    rows = load_rows(directory / "xa_boundary_samples.csv")
    ledger = load_ledger(directory / "safe_d_crossing_ledger.json")
    post_samples = {r["tap"]: r for r in rows if r["kind"] == "post_close"}
    tail_samples = {r["tap"]: r for r in rows if r["kind"] == "tail_1ns"}
    final_samples = {r["tap"]: r for r in rows if r["kind"] == "final"}
    q_events = [r for r in rows if r["kind"] == "q_event" and r["time_ps"] > CLOSE_PS]
    event_by_tap: Dict[int, List[Dict[str, Any]]] = {tap: [] for tap in range(30)}
    for event in q_events:
        # XA emits the Q threshold transition at approximately VDD_SAFE/2.
        # A post-close event is source-backed if a same-tap safe_d fall occurred
        # within 100 ps before it; otherwise it is a genuine source-free event.
        source_events = [e for e in ledger["tap_{:02d}".format(event["tap"])] if e["logic_state"] == 0 and e["time_ps"] <= event["time_ps"]]
        source = max(source_events, key=lambda item: item["time_ps"]) if source_events else None
        delay = event["time_ps"] - source["time_ps"] if source else None
        classification = "source-backed" if source is not None and delay <= 100.0 else "source-free"
        event_by_tap[event["tap"]].append({
            "time_ps": event["time_ps"],
            "q_v": event["q_v"],
            "safe_d_v": event["safe_d_v"],
            "classification": classification,
            "source_safe_d_time_ps": source["time_ps"] if source else None,
            "delay_ps": delay,
        })
    taps: List[Dict[str, Any]] = []
    for tap in range(30):
        final = final_samples[tap]
        tail = tail_samples[tap]
        events = event_by_tap[tap]
        source_free = [e for e in events if e["classification"] == "source-free"]
        final_code_bit = 1 if final["q_v"] >= 0.5 * VDD_SAFE else 0
        tail_stable = abs(final["q_v"] - tail["q_v"]) <= 1.0e-5
        taps.append({
            "tap": tap,
            "safe_d_crossings": ledger["tap_{:02d}".format(tap)],
            "post_close_q_events": events,
            "source_free_reflip": bool(source_free),
            "unresolved": len(events) > 1,
            "post_close_mid_rail": any(RAIL_LOW < event["q_v"] < RAIL_HIGH for event in events),
            "final_q_v": final["q_v"],
            "final_code_bit": final_code_bit,
            "final_mid_rail": RAIL_LOW < final["q_v"] < RAIL_HIGH,
            "tail_q_v": tail["q_v"],
            "tail_stable": tail_stable,
            "vdd_sense_v": final["vdd_sense_v"],
            "vdd_safe_v": final["vdd_safe_v"],
            "g_v_final": final["g_v"],
        })
    code = "".join(str(tap["final_code_bit"]) for tap in taps)
    return {
        "scenario_id": DISPLAY[scenario],
        "run_directory": str(directory),
        "csv_sha256": sha256(directory / "xa_boundary_samples.csv"),
        "ledger_sha256": sha256(directory / "safe_d_crossing_ledger.json"),
        "observed_close_ps": CLOSE_PS,
        "final_code": code,
        "final_ones": code.count("1"),
        "source_free_reflip_taps": [tap["tap"] for tap in taps if tap["source_free_reflip"]],
        "unresolved_taps": [tap["tap"] for tap in taps if tap["unresolved"]],
        # A source-backed Q transition is expected to pass VDD_SAFE/2; only a
        # persistent final mid-rail state is a Gate failure.  Keep transient
        # post-close midpoint observations separately for review.
        "mid_rail_taps": [tap["tap"] for tap in taps if tap["final_mid_rail"]],
        "post_close_transition_mid_rail_taps": [tap["tap"] for tap in taps if tap["post_close_mid_rail"]],
        "tail_unstable_taps": [tap["tap"] for tap in taps if not tap["tail_stable"]],
        "tap27": next(tap for tap in taps if tap["tap"] == 27),
        "taps": taps,
    }


def main() -> int:
    """Publish analysis, report, and the mandatory L1A Gate."""

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    scenarios = [analyze_scenario(scenario) for scenario in SCENARIOS]
    hamming = sum(a != b for a, b in zip(scenarios[0]["final_code"], scenarios[1]["final_code"]))
    all_stable = all(not item["source_free_reflip_taps"] and not item["unresolved_taps"] and not item["mid_rail_taps"] and not item["tail_unstable_taps"] for item in scenarios)
    gate = "BFE2_L1A_REAL_SAFE_LATCH_PASS" if all_stable and hamming >= 9 else "BFE2_L1A_REAL_SAFE_LATCH_FAIL"
    analysis = {
        "schema_version": 1,
        "stage": "B-FE2-L1A",
        "verification_mode": "VCS-XA mixed-signal latch-boundary co-simulation",
        "vdd_safe_v": VDD_SAFE,
        "safe_d_high_v": SAFE_HIGH,
        "sample_close_ps": 534.524618567,
        "observed_latch_close_ps": CLOSE_PS,
        "hamming_distance": hamming,
        "all_capture_stability_checks_pass": all_stable,
        "gate": gate,
        "capture_cell_review_required": gate.endswith("FAIL"),
        "scenarios": scenarios,
    }
    (OUT_ROOT / "BFE2_L1A_VCS_XA_ANALYSIS.json").write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_lines = [
        "# B-FE2-L1A VCS-XA 1.10 V Report",
        "",
        "Verification mode: VCS W-2024.09 + PrimeSim XA W-2024.09 mixed-signal latch-boundary co-simulation.",
        "Frozen source: B-FE2.2C 0.95 V normal and 0.95->0.86 V L2; sample_close=534.524618567 ps.",
        "safe_d rule: xor > 0.5*VDD_SENSE ? 0.95 V : 0 V; VDD_SAFE/VNW=1.10 V, VPW/VSS=0 V.",
        "",
        "| Scenario | Final code | Ones | Source-free re-flip | Unresolved | Mid-rail | Tail unstable |",
        "|---|---|---:|---|---|---|---|",
    ]
    for item in scenarios:
        report_lines.append("| {} | `{}` | {} | {} | {} | {} | {} |".format(item["scenario_id"], item["final_code"], item["final_ones"], item["source_free_reflip_taps"], item["unresolved_taps"], item["mid_rail_taps"], item["tail_unstable_taps"]))
    report_lines += [
        "",
        "Hamming distance: {} (required >=9).".format(hamming),
        "tap27 normal: final={} V, post-close events={}; tap27 L2: final={} V, post-close events={}.".format(scenarios[0]["tap27"]["final_q_v"], scenarios[0]["tap27"]["post_close_q_events"], scenarios[1]["tap27"]["final_q_v"], scenarios[1]["tap27"]["post_close_q_events"]),
        "",
        "Gate: **{}**".format(gate),
    ]
    (OUT_ROOT / "BFE2_L1A_VCS_XA_REPORT.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    gate_doc = {
        "stage": "B-FE2-L1A",
        "gate": gate,
        "review_gate": "BFE2_CAPTURE_CELL_REVIEW_REQUIRED" if gate.endswith("FAIL") else None,
        "analysis_sha256": sha256(OUT_ROOT / "BFE2_L1A_VCS_XA_ANALYSIS.json"),
        "report_sha256": sha256(OUT_ROOT / "BFE2_L1A_VCS_XA_REPORT.md"),
        "reason": "Hamming distance {} < required 9".format(hamming) if gate.endswith("FAIL") else "all criteria pass",
    }
    (OUT_ROOT / "BFE2_L1A_VCS_XA_GATE.json").write_text(json.dumps(gate_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(gate_doc, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
