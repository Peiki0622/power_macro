#!/usr/bin/env python3
"""Analyze the three B-FE2-CAL0 close points and publish the stopping Gate."""

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Set


ROOT = Path(__file__).resolve().parent
RUN_ROOT = ROOT.parents[3] / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "cal0_vcs_xa"
MANIFEST_PATH = ROOT / "BFE2_CAL0_SCENARIO_MANIFEST.json"
OFFLINE_PATH = ROOT / "BFE2_CAL0_OFFLINE_INTERVALS.json"
POINTS = ("LEFT", "CENTER", "RIGHT")
G_CLOSE_NOMINAL_PS = 1534.524618567
VDD_SAFE = 0.95
THRESHOLD_V = 0.475
RAIL_LOW = 0.095
RAIL_HIGH = 0.855
MAX_DQ_PS = 100.0
EPS_PS = 1.0e-6


def sha256(path: Path) -> str:
    """Hash one retained evidence artifact."""

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
    """Parse the typed XA boundary CSV."""

    rows: List[Dict[str, Any]] = []
    with path.open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            row["tap"] = int(row["tap"])
            for key in ("time_ps", "safe_d_v", "q_v", "vdd_sense_v", "vdd_safe_v", "g_v"):
                row[key] = float(row[key])
            rows.append(row)
    return rows


def classify_q_event(event: Mapping[str, Any], crossings: Sequence[Mapping[str, Any]], close_ps: float, used: Set[int]) -> Dict[str, Any]:
    """Classify a post-close Q event against pre/post-close safe_d causes."""

    direction = "rise" if event["safe_d_v"] > THRESHOLD_V else "fall"
    prior = [(index, source) for index, source in enumerate(crossings) if index not in used and source["direction"] == direction and source["time_ps"] <= event["time_ps"] + EPS_PS]
    post_close = [(index, source) for index, source in prior if source["time_ps"] > close_ps + EPS_PS]
    if post_close:
        index, source = min(post_close, key=lambda item: event["time_ps"] - item[1]["time_ps"])
        used.add(index)
        return {"classification": "post-close-source-change", "direction": direction, "source_event": dict(source), "delay_ps": event["time_ps"] - source["time_ps"]}
    pre_close = [(index, source) for index, source in prior if source["time_ps"] <= close_ps + EPS_PS and event["time_ps"] - source["time_ps"] <= MAX_DQ_PS]
    if pre_close:
        index, source = min(pre_close, key=lambda item: event["time_ps"] - item[1]["time_ps"])
        used.add(index)
        return {"classification": "source-backed", "direction": direction, "source_event": dict(source), "delay_ps": event["time_ps"] - source["time_ps"]}
    return {"classification": "source-free", "direction": direction, "source_event": None, "delay_ps": None}


def analyze_point(point: Mapping[str, Any]) -> Dict[str, Any]:
    """Analyze all taps and preserve the interval headroom contract."""

    label = str(point["point"])
    interval = point.get("interval", point)
    directory = RUN_ROOT / label.lower()
    rows = load_rows(directory / "xa_boundary_samples.csv")
    ledger = load_json(directory / "safe_d_crossing_ledger.json") if (directory / "safe_d_crossing_ledger.json").is_file() else None
    # The CAL0 runner reuses the source-derived ledger generation.  Recreate
    # the path if an old runner revision did not retain it in the point dir.
    if ledger is None:
        source_ledger = ROOT.parents[3] / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "l1a_r_vcs_xa" / "bfe2l_095_n" / "safe_d_crossing_ledger.json"
        ledger = load_json(source_ledger)
    close_ps = float(point["selected_g_close_ps"])
    final_rows = {row["tap"]: row for row in rows if row["kind"] == "final"}
    tail_rows = {row["tap"]: row for row in rows if row["kind"] == "tail_1ns"}
    if set(final_rows) != set(range(30)) or set(tail_rows) != set(range(30)):
        raise ValueError("{} is missing final/tail rows".format(label))
    taps: List[Dict[str, Any]] = []
    for tap in range(30):
        entry = ledger["tap_{:02d}".format(tap)]
        initial = entry["initial"]
        expected_initial = int(initial["xor_v"] > 0.5 * initial["vdd_sense_v"])
        initial_bad = int(initial["logic_state"]) != expected_initial or abs(float(initial["safe_d_v"]) - (VDD_SAFE if expected_initial else 0.0)) > 1.0e-9
        crossings = list(entry["crossings"])
        preclose = [event for event in crossings if event["time_ps"] <= close_ps + EPS_PS]
        postclose = [event for event in crossings if event["time_ps"] > close_ps + EPS_PS]
        q_events = [row for row in rows if row["kind"] == "q_event" and row["tap"] == tap and row["time_ps"] > close_ps + EPS_PS]
        used: Set[int] = set()
        classified = [{"time_ps": row["time_ps"], "q_v": row["q_v"], **classify_q_event(row, crossings, close_ps, used)} for row in q_events]
        source_free = [event for event in classified if event["classification"] == "source-free"]
        postclose_caused = [event for event in classified if event["classification"] == "post-close-source-change"]
        final = final_rows[tap]
        tail = tail_rows[tap]
        taps.append({
            "tap": tap,
            "initialization": initial,
            "initialization_mismatch": initial_bad,
            "pre_close_safe_d_crossings": preclose,
            "post_close_safe_d_crossings": postclose,
            "post_close_q_events": classified,
            "source_free_reflip": bool(source_free),
            "post_close_safe_d_changed_q": bool(postclose_caused),
            "unresolved": len(classified) > 1,
            "final_q_v": final["q_v"],
            "final_mid_rail": RAIL_LOW < final["q_v"] < RAIL_HIGH,
            "tail_q_v": tail["q_v"],
            "tail_stable": abs(final["q_v"] - tail["q_v"]) <= 1.0e-5,
            "vdd_safe_v": final["vdd_safe_v"],
            "g_v_final": final["g_v"],
        })
    code = "".join("1" if tap["final_q_v"] > THRESHOLD_V else "0" for tap in taps)
    return {
        "point": label,
        "scenario_id": point["scenario_id"],
        "run_directory": str(directory),
        "selected_sample_close_ps": point["selected_sample_close_ps"],
        "selected_g_close_ps": close_ps,
        "START": interval["start_ps"],
        "END": interval["end_ps"],
        "LEN": interval["len_ps"],
        "CENTER": interval["center_ps"],
        "LEFT_HEADROOM": interval["left_headroom_ps"],
        "RIGHT_HEADROOM": interval["right_headroom_ps"],
        "boundary_csv_sha256": sha256(directory / "xa_boundary_samples.csv"),
        "safe_d_ledger_sha256": sha256(directory / "safe_d_crossing_ledger.json"),
        "final_q_code": code,
        "final_ones": code.count("1"),
        "initialization_mismatch_taps": [tap["tap"] for tap in taps if tap["initialization_mismatch"]],
        "source_free_reflip_taps": [tap["tap"] for tap in taps if tap["source_free_reflip"]],
        "post_close_safe_d_changed_q_taps": [tap["tap"] for tap in taps if tap["post_close_safe_d_changed_q"]],
        "unresolved_taps": [tap["tap"] for tap in taps if tap["unresolved"]],
        "mid_rail_taps": [tap["tap"] for tap in taps if tap["final_mid_rail"]],
        "unstable_tail_taps": [tap["tap"] for tap in taps if not tap["tail_stable"]],
        "final_q_stable": not any(not tap["tail_stable"] for tap in taps),
        "capture_semantics_pass": not any(tap["initialization_mismatch"] or tap["source_free_reflip"] or tap["post_close_safe_d_changed_q"] or tap["unresolved"] or tap["final_mid_rail"] or not tap["tail_stable"] for tap in taps),
        "tap27": taps[27],
        "taps24_29": taps[24:30],
        "taps": taps,
    }


def main() -> int:
    """Publish analysis/report/Gate, then stop regardless of result."""

    manifest = load_json(MANIFEST_PATH)
    if manifest.get("source_waveform") != "BFE2L-095-N" or manifest.get("l2_used") is not False or manifest.get("new_physical_scenarios") != 3:
        raise ValueError("CAL0 manifest is not normal-only three-point evidence")
    offline = load_json(OFFLINE_PATH)
    if sha256(OFFLINE_PATH) != manifest.get("offline_intervals_sha256"):
        raise ValueError("offline interval artifact changed after XA run")
    points = manifest.get("scenarios", [])
    if tuple(item.get("point") for item in points) != POINTS:
        raise ValueError("CAL0 requires LEFT/CENTER/RIGHT only")
    results = [analyze_point(point) for point in points]
    ones = [result["final_ones"] for result in results]
    codes = [result["final_q_code"] for result in results]
    monotonic_nondec = all(a <= b for a, b in zip(ones, ones[1:]))
    monotonic_noninc = all(a >= b for a, b in zip(ones, ones[1:]))
    local_monotonic = (monotonic_nondec or monotonic_noninc) and len(set(ones)) > 1
    positive_window = all(result["LEN"] > 0.0 and result["LEFT_HEADROOM"] > 0.0 and result["RIGHT_HEADROOM"] > 0.0 for result in results)
    capture_pass = all(result["capture_semantics_pass"] for result in results)
    if capture_pass and local_monotonic and positive_window:
        gate = "BFE2_CAL0_SAMPLE_CLOSE_CALIBRATABLE"
    else:
        gate = "BFE2_CAL0_SAMPLE_CLOSE_NOT_CALIBRATABLE"
    failure_class = None
    if not capture_pass:
        failure_class = "CAPTURE_SEMANTICS_FAIL"
    elif not (local_monotonic and positive_window):
        failure_class = "SPATIAL_DISCRIMINATION_FAIL"
    analysis = {
        "schema_version": 1,
        "stage": "B-FE2-CAL0",
        "gate": gate,
        "failure_class": failure_class,
        "verification_mode": manifest["verification_mode"],
        "source_waveform": "BFE2L-095-N",
        "l2_used": False,
        "fixed_nominal_sample_close_ps": 534.524618567,
        "fixed_nominal_g_close_ps": G_CLOSE_NOMINAL_PS,
        "vdd_safe_v": VDD_SAFE,
        "vnw_v": VDD_SAFE,
        "vpw_v": 0.0,
        "vss_v": 0.0,
        "capture_semantics_pass": capture_pass,
        "local_monotonic_feature": local_monotonic,
        "positive_width_stable_window": positive_window,
        "ones_sequence": ones,
        "codes_sequence": codes,
        "source_manifest_sha256": manifest["source_manifest_sha256"],
        "manifest_sha256": sha256(MANIFEST_PATH),
        "offline_intervals_sha256": sha256(OFFLINE_PATH),
        "results": results,
        "stop_after_stage": True,
        "next_stage_authorized": False,
    }
    analysis_path = ROOT / "BFE2_CAL0_ANALYSIS.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_lines = [
        "# B-FE2-CAL0 report",
        "",
        "Gate: `{}`".format(gate),
        "",
        "Normal-only VCS W-2024.09 + PrimeSim XA W-2024.09 validation. No L2, M/F code table, FSM, circuit, or sensing-geometry change.",
        "The offline stage used only the accepted normal safe_d crossing ledger and selected three event-free intervals; no dense close grid was simulated.",
        "",
        "| Point | sample_close (ps) | G close (ps) | START | END | LEN | CENTER | LEFT_HEADROOM | RIGHT_HEADROOM | Q[29:0] | Ones | source-free | unresolved | mid-rail | tail | post-close safe_d→Q |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|---|---|",
    ]
    for result in results:
        report_lines.append("| {} | {:.9f} | {:.9f} | {:.9f} | {:.9f} | {:.9f} | {:.9f} | {:.9f} | {:.9f} | `{}` | {} | {} | {} | {} | {} | {} |".format(result["point"], result["selected_sample_close_ps"], result["selected_g_close_ps"], result["START"], result["END"], result["LEN"], result["CENTER"], result["LEFT_HEADROOM"], result["RIGHT_HEADROOM"], result["final_q_code"], result["final_ones"], result["source_free_reflip_taps"], result["unresolved_taps"], result["mid_rail_taps"], result["unstable_tail_taps"], result["post_close_safe_d_changed_q_taps"]))
    report_lines += [
        "",
        "Ordered ones sequence LEFT/CENTER/RIGHT: `{}`; local monotonic feature: `{}`.".format(ones, local_monotonic),
        "Positive-width stable-window candidates: `{}`.".format(positive_window),
        "Failure classification: `{}` (capture semantics is evaluated separately from spatial discrimination).".format(failure_class or "NONE"),
        "",
        "LEFT tap27 post-close Q events: `{}`.".format(results[0]["tap27"]["post_close_q_events"]),
        "CENTER tap27 post-close Q events: `{}`.".format(results[1]["tap27"]["post_close_q_events"]),
        "RIGHT tap27 post-close Q events: `{}`.".format(results[2]["tap27"]["post_close_q_events"]),
        "RIGHT tap29 post-close Q events: `{}`.".format(next(result["taps"][29]["post_close_q_events"] for result in results if result["point"] == "RIGHT")),
        "",
        "Tap24-29 post-close safe_d/Q evidence is retained in the JSON analysis for every point; all post-close safe_d→Q tap lists are expected empty for a capture-semantics pass.",
        "",
        "This CAL0 stage stops here regardless of Gate; no self-calibration controller, old M/F reuse, runtime detection, or later phase is authorized.",
    ]
    report_path = ROOT / "BFE2_CAL0_REPORT.md"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    gate_doc = {
        "stage": "B-FE2-CAL0",
        "gate": gate,
        "failure_class": failure_class,
        "capture_semantics_pass": capture_pass,
        "local_monotonic_feature": local_monotonic,
        "positive_width_stable_window": positive_window,
        "ones_sequence": ones,
        "analysis_sha256": sha256(analysis_path),
        "report_sha256": sha256(report_path),
        "stop_after_stage": True,
        "next_stage_authorized": False,
    }
    (ROOT / "BFE2_CAL0_GATE.json").write_text(json.dumps(gate_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(gate_doc, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
