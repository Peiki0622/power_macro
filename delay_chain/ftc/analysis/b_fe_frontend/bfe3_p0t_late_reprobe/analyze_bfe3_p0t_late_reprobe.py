#!/usr/bin/env python3
"""Analyze B-FE3-P0T final/tail Q evidence using raw M only."""

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
P0T_MANIFEST = ROOT / "BFE3_P0T_MANIFEST.json"
P0R_ANALYSIS = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe3_p0r_m_phase" / "BFE3_P0R_ANALYSIS.json"
TAP_COUNT = 30
THRESHOLD_V = 0.475
RAIL_LOW_V = 0.095
RAIL_HIGH_V = 0.855
TAIL_TOLERANCE_V = 1.0e-5


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def rows(path: Path) -> list:
    values = []
    with path.open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            for key in ("time_ps", "tap", "safe_d_v", "q_v", "vdd_sense_v", "vdd_safe_v", "g_v"):
                row[key] = float(row[key])
            row["tap"] = int(row["tap"])
            values.append(row)
    return values


def analyze_sample(meta: dict, envelope: dict) -> dict:
    directory = Path(meta["directory"])
    boundary = directory / "xa_boundary_samples.csv"
    data = rows(boundary)
    final = {row["tap"]: row for row in data if row["kind"] == "final"}
    tail = {row["tap"]: row for row in data if row["kind"] == "tail_1ns"}
    if set(final) != set(range(TAP_COUNT)) or set(tail) != set(range(TAP_COUNT)):
        raise ValueError("missing final/tail rows for {}".format(meta["phase_label"]))
    mid = [tap for tap in range(TAP_COUNT) if RAIL_LOW_V < final[tap]["q_v"] < RAIL_HIGH_V]
    unstable = [tap for tap in range(TAP_COUNT) if abs(final[tap]["q_v"] - tail[tap]["q_v"]) > TAIL_TOLERANCE_V]
    bad_safe = [tap for tap in range(TAP_COUNT) if abs(final[tap]["vdd_safe_v"] - 0.95) > 1.0e-6]
    bits = [1 if final[tap]["q_v"] > THRESHOLD_V else 0 for tap in range(TAP_COUNT)]
    m_value = sum(tap * bit for tap, bit in enumerate(bits))
    margin = envelope["min"] - m_value if m_value < envelope["min"] else (m_value - envelope["max"] if m_value > envelope["max"] else 0)
    resolved = not mid and not unstable and not bad_safe
    return {
        "phase_label": meta["phase_label"], "probe_role": "diagnostic re-probe", "launch_ps": meta["launch_ps"], "g_close_ps": meta["g_close_ps"],
        "droop_onset_ps": 1500.0, "droop_duration_at_g_close_ps": meta["g_close_ps"] - 1500.0,
        "q_raw_29_to_0": "".join(str(bit) for bit in reversed(bits)), "q_raw_tap0_to_tap29": "".join(str(bit) for bit in bits),
        "M": m_value, "outside_normal_m_envelope": resolved and margin > 0, "m_margin": margin,
        "rail_resolved_and_tail_stable": resolved, "final_mid_rail_taps": mid, "unstable_tail_taps": unstable, "safe_supply_bad_taps": bad_safe,
        "boundary_csv_sha256": sha256(boundary), "run_directory": str(directory),
    }


def main() -> int:
    manifest = load_json(P0T_MANIFEST)
    p0r = load_json(P0R_ANALYSIS)
    if manifest.get("normal_m_envelope") != {"min": 260, "max": 315}:
        raise ValueError("P0T normal M envelope drifted")
    if manifest.get("baseline_p0r_m") != 287 or p0r.get("gate") != "BFE3_P0R_M_PHASE_OVERLAP":
        raise ValueError("P0R LATE baseline evidence is not frozen")
    envelope = manifest["normal_m_envelope"]
    baseline = next(item for item in p0r["results"] if item["phase_label"] == "LATE")
    baseline_record = {
        "phase_label": "FIRST", "probe_role": "retained P0R LATE baseline", "launch_ps": 1000.0, "g_close_ps": 1534.524618567,
        "droop_onset_ps": 1500.0, "droop_duration_at_g_close_ps": 34.524618567, "q_raw_29_to_0": baseline["q_raw_29_to_0"],
        "q_raw_tap0_to_tap29": baseline["q_raw_tap0_to_tap29"], "M": baseline["M"], "outside_normal_m_envelope": baseline["outside_normal_m_envelope"],
        "m_margin": baseline["m_margin"], "rail_resolved_and_tail_stable": baseline["rail_resolved_and_tail_stable"],
        "final_mid_rail_taps": baseline["final_mid_rail_taps"], "unstable_tail_taps": baseline["unstable_tail_taps"], "safe_supply_bad_taps": baseline["safe_supply_bad_taps"],
        "boundary_csv_sha256": baseline["boundary_csv_sha256"], "run_directory": baseline["run_directory"],
    }
    new_results = [analyze_sample(item, envelope) for item in manifest["xa_scenarios"]]
    results = [baseline_record] + new_results
    robust = len(new_results) == 2 and all(item["rail_resolved_and_tail_stable"] and item["outside_normal_m_envelope"] for item in new_results)
    gate = "BFE3_P0T_LATE_DROOP_RECOVERED_BY_REPROBE" if robust else "BFE3_P0T_REPROBE_INSUFFICIENT"
    worst = min(new_results, key=lambda item: item["m_margin"])
    csv_path = ROOT / "BFE3_P0T_SAMPLES.csv"
    fields = ["phase_label", "probe_role", "launch_ps", "g_close_ps", "droop_onset_ps", "droop_duration_at_g_close_ps", "q_raw_29_to_0", "q_raw_tap0_to_tap29", "M", "outside_normal_m_envelope", "m_margin", "rail_resolved_and_tail_stable", "final_mid_rail_taps", "unstable_tail_taps", "safe_supply_bad_taps", "boundary_csv_sha256", "run_directory"]
    with csv_path.open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)
    analysis = {
        "schema_version": 1, "stage": "B-FE3-P0T", "gate": gate, "normal_m_envelope": envelope,
        "baseline": baseline_record, "results": results, "new_results": new_results, "worst_new_probe": worst,
        "minimum_new_probe_margin": min(item["m_margin"] for item in new_results), "uses_M_only": True, "uses_N_or_T": False,
        "p0t_manifest_sha256": sha256(P0T_MANIFEST), "sample_csv_sha256": sha256(csv_path), "stop_after_stage": True, "next_stage_authorized": False,
    }
    analysis_path = ROOT / "BFE3_P0T_ANALYSIS.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# B-FE3-P0T late-droop diagnostic re-probe", "", "Gate: `{}`".format(gate), "", "Frozen source: P0R LATE, phase=500 ps, 0.95->0.86 V L2, 3002 ps droop, 30 taps, 4/0 RVT/LVT, Level-0 restoration, real `LATQ_X0P5M_A9TR40` at `VDD_SAFE=0.95 V`.", "Only raw `M=sum(i*q[i])` is evaluated; no N/T, RTL, calibration, lookup table, filtering, bubble repair, or multi-feature fusion.", "", "Normal M envelope: `260..315`. Droop duration is measured from the 1500 ps falling-transition onset to each G close.", "", "| Probe | Launch (ps) | G close (ps) | Droop duration at G close (ps) | q_raw[29:0] | M | Rail/tail valid | Outside envelope | Margin |", "|---|---:|---:|---:|---|---:|---|---|---:|"]
    for item in results:
        lines.append("| {} | {:.9f} | {:.9f} | {:.9f} | `{}` | {} | {} | {} | {} |".format(item["phase_label"], item["launch_ps"], item["g_close_ps"], item["droop_duration_at_g_close_ps"], item["q_raw_29_to_0"], item["M"], item["rail_resolved_and_tail_stable"], item["outside_normal_m_envelope"], item["m_margin"]))
    lines += ["", "Worst new probe: `{}` at {:.9f} ps, q_raw[29:0]=`{}`, M={}, margin={}.".format(worst["phase_label"], worst["launch_ps"], worst["q_raw_29_to_0"], worst["M"], worst["m_margin"]), "", "The first P0R LATE point is retained as the M=287 blind-window baseline. This stage stops after the two diagnostic re-probes."]
    report_path = ROOT / "BFE3_P0T_REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    gate_path = ROOT / "BFE3_P0T_GATE.json"
    gate_path.write_text(json.dumps({"stage": "B-FE3-P0T", "gate": gate, "normal_m_envelope": envelope, "worst_new_probe": worst, "minimum_new_probe_margin": analysis["minimum_new_probe_margin"], "analysis_sha256": sha256(analysis_path), "report_sha256": sha256(report_path), "stop_after_stage": True, "next_stage_authorized": False}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"gate": gate, "results": [(item["phase_label"], item["M"], item["m_margin"]) for item in results], "worst_new_probe": worst}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
