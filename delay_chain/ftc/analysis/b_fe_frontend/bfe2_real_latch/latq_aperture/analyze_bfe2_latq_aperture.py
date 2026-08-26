#!/usr/bin/env python3
"""Classify the retained XA points by tap29's own Q trajectory."""

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "cal0_capture_safe_vcs_xa"))
from run_bfe2_cal0_capture_safe import pair_q_events, q_event_stream  # noqa: E402

OUT_ROOT = ROOT
MANIFEST_PATH = OUT_ROOT / "BFE2_LATQ_APERTURE_MANIFEST.json"
THRESHOLD_V = 0.475
TAP = 29
EPS_PS = 1.0e-6


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_rows(path: Path):
    rows = []
    with path.open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            row["tap"] = int(row["tap"])
            for key in ("time_ps", "safe_d_v", "q_v", "vdd_sense_v", "vdd_safe_v", "g_v"):
                row[key] = float(row[key])
            rows.append(row)
    return rows


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def classify_point(point):
    directory = Path(point["directory"])
    rows = load_rows(directory / "xa_boundary_samples.csv")
    ledger = load_json(directory / "safe_d_crossing_ledger.json")
    crossings = ledger["tap_{:02d}".format(TAP)]["crossings"]
    events = pair_q_events(q_event_stream(rows, TAP), crossings)
    close_ps = float(point["g_close_ps"])
    postclose = [event for event in events if event["time_ps"] > close_ps + EPS_PS]
    source_free = [event for event in postclose if event["classification"] == "source-free"]
    final_row = next(row for row in rows if row["kind"] == "final" and row["tap"] == TAP)
    tail_row = next(row for row in rows if row["kind"] == "tail_1ns" and row["tap"] == TAP)
    final_q_v = final_row["q_v"]
    final_q = 1 if final_q_v > THRESHOLD_V else 0
    final_mid_rail = 0.095 < final_q_v < 0.855
    unresolved = len(postclose) > 1
    tail_stable = abs(final_q_v - tail_row["q_v"]) <= 1.0e-5
    if source_free or unresolved or final_mid_rail:
        classification = "UNSAFE_APERTURE"
    elif final_q == 0 and tail_stable:
        classification = "SAFE_REJECT"
    elif final_q == 1 and tail_stable:
        classification = "SAFE_CAPTURE"
    else:
        classification = "UNSAFE_APERTURE"
    return {
        **point,
        "q_crossings_ps": [event["time_ps"] for event in events],
        "q_events": events,
        "post_close_q_events": postclose,
        "source_free_reflip": bool(source_free),
        "unresolved": unresolved,
        "mid_rail": final_mid_rail,
        "final_q_v": final_q_v,
        "final_q": final_q,
        "tail_q_v": tail_row["q_v"],
        "tail_stable": tail_stable,
        "classification": classification,
        "boundary_csv_sha256": sha256(directory / "xa_boundary_samples.csv"),
        "safe_d_ledger_sha256": sha256(directory / "safe_d_crossing_ledger.json"),
    }


def main() -> int:
    manifest = load_json(MANIFEST_PATH)
    results = [classify_point(point) for point in manifest["points"]]
    results.sort(key=lambda item: item["delta_t_ps"])
    labels = [item["classification"] for item in results]
    reject = [item for item in results if item["classification"] == "SAFE_REJECT"]
    unsafe = [item for item in results if item["classification"] == "UNSAFE_APERTURE"]
    capture = [item for item in results if item["classification"] == "SAFE_CAPTURE"]
    ordered = bool(reject and unsafe and capture and max(item["delta_t_ps"] for item in reject) < min(item["delta_t_ps"] for item in unsafe) < max(item["delta_t_ps"] for item in capture))
    gate = "BFE2_LATQ_DG_APERTURE_READY" if ordered else "BFE2_LATQ_DG_APERTURE_UNRESOLVED"
    analysis = {
        "schema_version": 1,
        "stage": manifest["stage"],
        "gate": gate,
        "tap": TAP,
        "d_crossing_ps": manifest["frozen_d_crossing_ps"],
        "delta_t_definition": manifest["delta_t_definition"],
        "results": results,
        "classification_sequence": labels,
        "ordered_safe_reject_unsafe_safe_capture": ordered,
        "uses_d_to_q_delay_as_window": False,
        "uses_direction_global_fallback": False,
        "new_hspice_scenarios": 0,
        "stop_after_stage": True,
        "next_stage_authorized": False,
        "manifest_sha256": sha256(MANIFEST_PATH),
    }
    analysis_path = OUT_ROOT / "BFE2_LATQ_APERTURE_ANALYSIS.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# B-FE2-LATQ-APERTURE",
        "",
        "Gate: `{}`".format(gate),
        "",
        "Tap29 only; frozen `D_crossing = {:.12f} ps`; `Delta t = G_close - D_crossing`.".format(manifest["frozen_d_crossing_ps"]),
        "The 0.95 V normal source, 30 taps, 4/0 geometry, ideal Level-0 restoration, and real `LATQ_X0P5M_A9TR40` are unchanged.",
        "Classification uses Q's own state sequence and final/tail state. D-to-Q delay is retained only as observed event evidence, never as a capture-safe-window definition.",
        "",
        "| Point | Delta t (ps) | D crossing (ps) | G close (ps) | Q crossing(s) (ps) | Final Q | Final Q (V) | Source-free re-flip | Unresolved | Mid-rail | Classification |",
        "|---|---:|---:|---:|---|---:|---:|---|---|---|---|",
    ]
    for result in results:
        lines.append("| {} | {:.9f} | {:.12f} | {:.12f} | {} | {} | {:.9f} | {} | {} | {} | `{}` |".format(
            result["point"], result["delta_t_ps"], result["d_crossing_ps"], result["g_close_ps"],
            [round(value, 6) for value in result["q_crossings_ps"]], result["final_q"], result["final_q_v"],
            result["source_free_reflip"], result["unresolved"], result["mid_rail"], result["classification"],
        ))
    lines += [
        "",
        "Ordered-boundary check: `{}` (at least one SAFE_REJECT, then UNSAFE_APERTURE, then SAFE_CAPTURE in increasing Delta t).".format(ordered),
        "",
        "This stage stops immediately; no self-calibration, M/F, FSM, detection, dense sweep, or later phase is authorized.",
    ]
    report_path = OUT_ROOT / "BFE2_LATQ_APERTURE_REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    gate_path = OUT_ROOT / "BFE2_LATQ_APERTURE_GATE.json"
    gate_path.write_text(json.dumps({
        "stage": manifest["stage"], "gate": gate, "tap": TAP,
        "ordered_safe_reject_unsafe_safe_capture": ordered,
        "analysis_sha256": sha256(analysis_path), "report_sha256": sha256(report_path),
        "stop_after_stage": True, "next_stage_authorized": False,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"gate": gate, "ordered": ordered, "classifications": labels}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
