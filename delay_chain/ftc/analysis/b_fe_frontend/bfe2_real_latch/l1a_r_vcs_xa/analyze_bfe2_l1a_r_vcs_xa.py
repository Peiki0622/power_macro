#!/usr/bin/env python3
"""Analyze B-FE2-L1A-R capture causality and publish the stopping Gate.

The analyzer treats the source-derived crossing ledger as the authoritative
safe-domain stimulus contract and the XA boundary CSV as the latch response.
It therefore distinguishes an allowed in-flight Q resolution (a pre-close
``safe_d`` crossing followed by one Q event) from a genuine source-free
post-close re-flip or a Q event caused by a post-close ``safe_d`` change.
"""

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Set


ROOT = Path(__file__).resolve().parent
# ROOT.parents[3] is the delay_chain/ftc project root because ROOT itself is
# already the l1a_r_vcs_xa directory (the old analyzer indexed from __file__).
RUN_ROOT = ROOT.parents[3] / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "l1a_r_vcs_xa"
MANIFEST_PATH = ROOT / "BFE2_L1AR_SCENARIO_MANIFEST.json"
SCENARIOS = ("bfe2l_095_n", "bfe2l_095_l2")
DISPLAY = {"bfe2l_095_n": "BFE2L-095-N", "bfe2l_095_l2": "BFE2L-095-L2"}
SAMPLE_CLOSE_PS = 534.524618567
G_CLOSE_PS = 1534.524618567
VDD_SAFE = 0.95
THRESHOLD_V = 0.5 * VDD_SAFE
RAIL_LOW = 0.1 * VDD_SAFE
RAIL_HIGH = 0.9 * VDD_SAFE
MAX_DQ_PS = 100.0
EPS_PS = 1.0e-6


def sha256(path: Path) -> str:
    """Hash a retained artifact for the independent evidence chain."""

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
    """Parse typed XA boundary evidence and retain every event row."""

    rows: List[Dict[str, Any]] = []
    with path.open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            row["tap"] = int(row["tap"])
            for key in ("time_ps", "safe_d_v", "q_v", "vdd_sense_v", "vdd_safe_v", "g_v"):
                row[key] = float(row[key])
            rows.append(row)
    return rows


def classify_q_event(event: Mapping[str, Any], crossings: Sequence[Mapping[str, Any]], used: Set[int]) -> Dict[str, Any]:
    """Correlate one post-close Q transition with the frozen safe_d ledger."""

    # The bridge sample is taken at the Q threshold crossing.  Its safe_d
    # value is consequently the post-transition logic level and supplies the
    # direction without inventing a second analog threshold or delay model.
    direction = "rise" if event["safe_d_v"] > THRESHOLD_V else "fall"
    prior = [(index, source) for index, source in enumerate(crossings) if index not in used and source["direction"] == direction and source["time_ps"] <= event["time_ps"] + EPS_PS]
    post_close = [(index, source) for index, source in prior if source["time_ps"] > G_CLOSE_PS + EPS_PS]
    if post_close:
        index, source = min(post_close, key=lambda item: event["time_ps"] - item[1]["time_ps"])
        used.add(index)
        return {"classification": "post-close-source-change", "direction": direction, "source_event": dict(source), "delay_ps": event["time_ps"] - source["time_ps"]}
    pre_close = [(index, source) for index, source in prior if source["time_ps"] <= G_CLOSE_PS + EPS_PS and event["time_ps"] - source["time_ps"] <= MAX_DQ_PS]
    if pre_close:
        index, source = min(pre_close, key=lambda item: event["time_ps"] - item[1]["time_ps"])
        used.add(index)
        return {"classification": "source-backed", "direction": direction, "source_event": dict(source), "delay_ps": event["time_ps"] - source["time_ps"]}
    return {"classification": "source-free", "direction": direction, "source_event": None, "delay_ps": None}


def scenario_analysis(scenario: str) -> Dict[str, Any]:
    """Analyze all thirty taps, including tap24--29 and historical tap27."""

    directory = RUN_ROOT / scenario
    rows = load_rows(directory / "xa_boundary_samples.csv")
    ledger = load_json(directory / "safe_d_crossing_ledger.json")
    final_rows = {row["tap"]: row for row in rows if row["kind"] == "final"}
    tail_rows = {row["tap"]: row for row in rows if row["kind"] == "tail_1ns"}
    if set(final_rows) != set(range(30)) or set(tail_rows) != set(range(30)):
        raise ValueError("L1A-R boundary evidence is missing final/tail tap rows for {}".format(scenario))
    taps: List[Dict[str, Any]] = []
    for tap in range(30):
        entry = ledger["tap_{:02d}".format(tap)]
        initial = entry["initial"]
        expected_initial = 1 if initial["xor_v"] > 0.5 * initial["vdd_sense_v"] else 0
        initial_mismatch = int(initial["logic_state"]) != expected_initial or abs(float(initial["safe_d_v"]) - (VDD_SAFE if expected_initial else 0.0)) > 1.0e-9
        crossings = list(entry["crossings"])
        preclose = [event for event in crossings if event["time_ps"] <= G_CLOSE_PS + EPS_PS]
        postclose = [event for event in crossings if event["time_ps"] > G_CLOSE_PS + EPS_PS]
        q_events = [row for row in rows if row["kind"] == "q_event" and row["tap"] == tap and row["time_ps"] > G_CLOSE_PS + EPS_PS]
        used: Set[int] = set()
        classified = [{"time_ps": event["time_ps"], "q_v": event["q_v"], **classify_q_event(event, crossings, used)} for event in q_events]
        source_free = [event for event in classified if event["classification"] == "source-free"]
        postclose_caused = [event for event in classified if event["classification"] == "post-close-source-change"]
        final = final_rows[tap]
        tail = tail_rows[tap]
        final_mid_rail = RAIL_LOW < final["q_v"] < RAIL_HIGH
        taps.append({
            "tap": tap,
            "initialization": initial,
            "initialization_mismatch": initial_mismatch,
            "safe_d_crossings": crossings,
            "pre_close_safe_d_crossings": preclose,
            "post_close_safe_d_crossings": postclose,
            "post_close_q_events": classified,
            "source_free_reflip": bool(source_free),
            "post_close_safe_d_changed_q": bool(postclose_caused),
            "unresolved": len(classified) > 1,
            "final_q_v": final["q_v"],
            "final_mid_rail": final_mid_rail,
            "tail_q_v": tail["q_v"],
            "tail_stable": abs(final["q_v"] - tail["q_v"]) <= 1.0e-5,
            "vdd_safe_v": final["vdd_safe_v"],
            "g_v_final": final["g_v"],
        })
    final_code = "".join("1" if tap["final_q_v"] > THRESHOLD_V else "0" for tap in taps)
    return {
        "scenario_id": DISPLAY[scenario],
        "run_directory": str(directory),
        "boundary_csv_sha256": sha256(directory / "xa_boundary_samples.csv"),
        "ledger_sha256": sha256(directory / "safe_d_crossing_ledger.json"),
        "sample_close_ps": SAMPLE_CLOSE_PS,
        "observed_g_close_ps": G_CLOSE_PS,
        "final_q_code": final_code,
        "final_ones": final_code.count("1"),
        "initialization_mismatch_taps": [tap["tap"] for tap in taps if tap["initialization_mismatch"]],
        "source_free_reflip_taps": [tap["tap"] for tap in taps if tap["source_free_reflip"]],
        "post_close_safe_d_changed_q_taps": [tap["tap"] for tap in taps if tap["post_close_safe_d_changed_q"]],
        "unresolved_taps": [tap["tap"] for tap in taps if tap["unresolved"]],
        "mid_rail_taps": [tap["tap"] for tap in taps if tap["final_mid_rail"]],
        "unstable_tail_taps": [tap["tap"] for tap in taps if not tap["tail_stable"]],
        "tail_stable": all(tap["tail_stable"] for tap in taps),
        "tap27": taps[27],
        "taps24_29": taps[24:30],
        "taps": taps,
    }


def main() -> int:
    """Publish analysis, explicit failure class, report, and stop Gate."""

    manifest = load_json(MANIFEST_PATH)
    if tuple(manifest.get("source_waveforms", ())) != ("BFE2L-095-N", "BFE2L-095-L2") or manifest.get("new_physical_scenarios") != 2:
        raise ValueError("L1A-R manifest is not the frozen two-scenario pair")
    results = [scenario_analysis(scenario) for scenario in SCENARIOS]
    hamming = sum(left != right for left, right in zip(results[0]["final_q_code"], results[1]["final_q_code"]))
    capture_failure = any(
        result["initialization_mismatch_taps"]
        or result["source_free_reflip_taps"]
        or result["post_close_safe_d_changed_q_taps"]
        or result["unresolved_taps"]
        or result["mid_rail_taps"]
        or result["unstable_tail_taps"]
        or not result["tail_stable"]
        for result in results
    )
    spatial_failure = hamming < 9
    if capture_failure:
        gate = "CAPTURE_SEMANTICS_FAIL"
        failure_class = "CAPTURE_SEMANTICS_FAIL"
    elif spatial_failure:
        gate = "SPATIAL_DISCRIMINATION_FAIL"
        failure_class = "SPATIAL_DISCRIMINATION_FAIL"
    else:
        gate = "BFE2_L1AR_REAL_SAFE_LATCH_PASS"
        failure_class = None
    analysis = {
        "schema_version": 1,
        "stage": "B-FE2-L1A-R",
        "gate": gate,
        "failure_class": failure_class,
        "verification_mode": manifest["verification_mode"],
        "fixed_sample_close_ps": SAMPLE_CLOSE_PS,
        "fixed_g_close_ps": G_CLOSE_PS,
        "vdd_safe_v": VDD_SAFE,
        "vnw_v": VDD_SAFE,
        "vpw_v": 0.0,
        "vss_v": 0.0,
        "hamming_distance": hamming,
        "capture_semantics_pass": not capture_failure,
        "spatial_discrimination_pass": not spatial_failure,
        "source_manifest_sha256": manifest["source_manifest_sha256"],
        "manifest_sha256": sha256(MANIFEST_PATH),
        "results": results,
        "stop_after_stage": True,
        "next_stage_authorized": False,
    }
    analysis_path = ROOT / "BFE2_L1AR_ANALYSIS.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_lines = [
        "# B-FE2-L1A-R report",
        "",
        "Gate: `{}`".format(gate),
        "",
        "VCS W-2024.09 + PrimeSim XA W-2024.09; frozen B-FE2.2C 0.95 V normal and 0.95->0.86 V L2 only.",
        "`sample_close=534.524618567 ps`, launch=1000 ps, therefore fixed `G close=1534.524618567 ps`.",
        "`VDD_SAFE=VNW=0.95 V`, `VPW=VSS=0 V`; latch=`LATQ_X0P5M_A9TR40`; Level-0 rule has no delay/slew/hysteresis/X-region.",
        "",
        "| Scenario | Final Q code | Ones | Source-free re-flip | Post-close safe_d changed Q | Unresolved | Mid-rail | Tail unstable |",
        "|---|---|---:|---|---|---|---|---|",
    ]
    for result in results:
        report_lines.append("| {} | `{}` | {} | {} | {} | {} | {} | {} |".format(result["scenario_id"], result["final_q_code"], result["final_ones"], result["source_free_reflip_taps"], result["post_close_safe_d_changed_q_taps"], result["unresolved_taps"], result["mid_rail_taps"], result["unstable_tail_taps"]))
    report_lines += [
        "",
        "Hamming distance: `{}` (required >=9).".format(hamming),
        "",
        "Initial-state audit: normal mismatches={}, L2 mismatches={}.".format(results[0]["initialization_mismatch_taps"], results[1]["initialization_mismatch_taps"]),
        "",
        "Normal tap27: final={:.9f} V, pre-close safe_d crossings={}, post-close safe_d crossings={}, post-close Q events={}.".format(results[0]["tap27"]["final_q_v"], results[0]["tap27"]["pre_close_safe_d_crossings"], results[0]["tap27"]["post_close_safe_d_crossings"], results[0]["tap27"]["post_close_q_events"]),
        "L2 tap27: final={:.9f} V, pre-close safe_d crossings={}, post-close safe_d crossings={}, post-close Q events={}.".format(results[1]["tap27"]["final_q_v"], results[1]["tap27"]["pre_close_safe_d_crossings"], results[1]["tap27"]["post_close_safe_d_crossings"], results[1]["tap27"]["post_close_q_events"]),
        "",
        "Tap24-29 normal post-close safe_d crossings: {}.".format([tap["post_close_safe_d_crossings"] for tap in results[0]["taps24_29"]]),
        "Tap24-29 L2 post-close safe_d crossings: {}.".format([tap["post_close_safe_d_crossings"] for tap in results[1]["taps24_29"]]),
        "",
        "Capture classification: `{}`; spatial classification: `{}`.".format("PASS" if not capture_failure else "FAIL", "PASS" if not spatial_failure else "FAIL"),
        "",
        "The independent L1A-R stage stops here regardless of Gate outcome; no close, geometry, or later-stage interface is authorized.",
    ]
    report_path = ROOT / "BFE2_L1AR_REPORT.md"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    gate_doc = {
        "stage": "B-FE2-L1A-R",
        "gate": gate,
        "failure_class": failure_class,
        "analysis_sha256": sha256(analysis_path),
        "report_sha256": sha256(report_path),
        "hamming_distance": hamming,
        "capture_semantics_pass": not capture_failure,
        "spatial_discrimination_pass": not spatial_failure,
        "stop_after_stage": True,
        "next_stage_authorized": False,
    }
    (ROOT / "BFE2_L1AR_GATE.json").write_text(json.dumps(gate_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(gate_doc, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
