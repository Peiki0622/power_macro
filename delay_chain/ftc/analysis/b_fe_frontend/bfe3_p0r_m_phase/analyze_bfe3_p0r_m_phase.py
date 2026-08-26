#!/usr/bin/env python3
"""Analyze B-FE3-P0R raw M only; do not create or rerun a simulator case."""

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe3_p0r_m_phase"
P0_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe3_p0_postprocess_features"
MANIFEST_PATH = ROOT / "BFE3_P0R_MANIFEST.json"
P0_ANALYSIS = P0_ROOT / "BFE3_P0_ANALYSIS.json"
P0_SAMPLES = P0_ROOT / "BFE3_P0_RAW_FEATURE_SAMPLES.csv"
TAP_COUNT = 30
VDD_SAFE_V = 0.95
THRESHOLD_V = 0.475
RAIL_LOW_V = 0.095
RAIL_HIGH_V = 0.855
TAIL_TOLERANCE_V = 1.0e-5


def sha256(path: Path) -> str:
    """Hash a retained analysis input or output in bounded memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    """Read one object-shaped manifest/analysis artifact."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def boundary_rows(path: Path) -> list:
    """Parse existing XA boundary samples; this function never launches XA."""

    rows = []
    with path.open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            row["tap"] = int(row["tap"])
            for key in ("time_ps", "safe_d_v", "q_v", "vdd_sense_v", "vdd_safe_v", "g_v"):
                row[key] = float(row[key])
            rows.append(row)
    return rows


def analyze_phase(meta: dict, envelope: dict) -> dict:
    """Validate final Q/tail resolution and compute M directly from q[i]."""

    directory = Path(meta["directory"])
    path = directory / "xa_boundary_samples.csv"
    rows = boundary_rows(path)
    final = {row["tap"]: row for row in rows if row["kind"] == "final"}
    tail = {row["tap"]: row for row in rows if row["kind"] == "tail_1ns"}
    if set(final) != set(range(TAP_COUNT)) or set(tail) != set(range(TAP_COUNT)):
        raise ValueError("missing final/tail rows for {}".format(meta["phase_label"]))
    mid = [tap for tap in range(TAP_COUNT) if RAIL_LOW_V < final[tap]["q_v"] < RAIL_HIGH_V]
    unstable = [tap for tap in range(TAP_COUNT) if abs(final[tap]["q_v"] - tail[tap]["q_v"]) > TAIL_TOLERANCE_V]
    safe_supply_bad = [tap for tap in range(TAP_COUNT) if abs(final[tap]["vdd_safe_v"] - VDD_SAFE_V) > 1.0e-6]
    bits = [1 if final[tap]["q_v"] > THRESHOLD_V else 0 for tap in range(TAP_COUNT)]
    m_value = sum(tap * bit for tap, bit in enumerate(bits))
    resolved_stable = not mid and not unstable and not safe_supply_bad
    # Contacting the normal envelope counts as overlap.  A valid positive
    # margin exists only outside its closed [min,max] interval.
    if m_value < envelope["min"]:
        margin = envelope["min"] - m_value
    elif m_value > envelope["max"]:
        margin = m_value - envelope["max"]
    else:
        margin = 0
    return {
        "phase_label": meta["phase_label"], "phase_ps": meta["phase_ps"], "run_directory": str(directory),
        "boundary_csv_sha256": sha256(path), "q_raw_29_to_0": "".join(str(bit) for bit in reversed(bits)),
        "q_raw_tap0_to_tap29": "".join(str(bit) for bit in bits), "M": m_value,
        "final_mid_rail_taps": mid, "unstable_tail_taps": unstable, "safe_supply_bad_taps": safe_supply_bad,
        "rail_resolved_and_tail_stable": resolved_stable, "outside_normal_m_envelope": resolved_stable and margin > 0,
        "m_margin": margin,
    }


def main() -> int:
    """Publish P0R sample table, analysis/report/Gate, and stop at the phase audit."""

    manifest = load_json(MANIFEST_PATH)
    p0 = load_json(P0_ANALYSIS)
    envelope = p0["normal_feature_envelope"]["M"]
    if manifest["frozen_normal_m_envelope"] != envelope or envelope != {"min": 260, "max": 315}:
        raise ValueError("P0R normal M envelope does not match frozen P0 evidence")
    if manifest["new_phase_points"] not in (3, 4) or manifest["dense_phase_scan"]:
        raise ValueError("P0R phase count is not the bounded representative matrix")
    results = [analyze_phase(item, envelope) for item in manifest["xa_scenarios"]]
    robust = bool(results) and all(item["rail_resolved_and_tail_stable"] and item["outside_normal_m_envelope"] for item in results)
    gate = "BFE3_P0R_M_PHASE_ROBUST" if robust else "BFE3_P0R_M_PHASE_OVERLAP"
    worst = min(results, key=lambda item: item["m_margin"])
    with P0_SAMPLES.open(newline="", encoding="ascii") as stream:
        prior_l2 = next(row for row in csv.DictReader(stream) if row["sample_id"] == "L1AR_095_L2")
    prior_reference = {"phase_ps": 75.0, "sample_id": "L1AR_095_L2", "q_raw_29_to_0": prior_l2["q_raw_29_to_0"], "M": int(prior_l2["M"]), "m_margin": envelope["min"] - int(prior_l2["M"])}
    csv_path = ROOT / "BFE3_P0R_M_PHASE_SAMPLES.csv"
    with csv_path.open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=["phase_label", "phase_ps", "q_raw_29_to_0", "q_raw_tap0_to_tap29", "M", "outside_normal_m_envelope", "m_margin", "rail_resolved_and_tail_stable", "final_mid_rail_taps", "unstable_tail_taps", "safe_supply_bad_taps", "boundary_csv_sha256", "run_directory"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)
    analysis = {
        "schema_version": 1, "stage": "B-FE3-P0R", "gate": gate, "normal_m_envelope": envelope,
        "existing_l2_phase_reference": prior_reference, "results": results, "worst_phase": worst,
        "minimum_positive_margin": min(item["m_margin"] for item in results) if robust else 0,
        "uses_M_only": True, "uses_N_or_T": False, "uses_lookup_table": False, "uses_filter": False, "uses_bubble_repair": False,
        "new_vcs_xa_scenarios": manifest["new_vcs_xa_scenarios"], "manifest_sha256": sha256(MANIFEST_PATH), "p0_analysis_sha256": sha256(P0_ANALYSIS),
        "sample_csv_sha256": sha256(csv_path), "stop_after_stage": True, "next_stage_authorized": False,
    }
    analysis_path = ROOT / "BFE3_P0R_ANALYSIS.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# B-FE3-P0R M phase-representative audit", "", "Gate: `{}`".format(gate), "",
        "Three newly simulated discrete L2 phases use the frozen 30-tap 4/0 source, Level-0 restoration, real `LATQ_X0P5M_A9TR40`, `VDD_SAFE=0.95 V`, and common `G_close=1534.524618567 ps`.",
        "Only `M=sum(i*q[i]), i=0..29` is evaluated. No N/T decision, RTL, calibration, lookup table, filtering, bubble repair, or multi-feature fusion is used.", "",
        "Frozen normal/capture-perturbation M envelope: `{}..{}`.".format(envelope["min"], envelope["max"]),
        "Existing P0 L2 phase reference: phase `75 ps`, q_raw[29:0]=`{}`, M=`{}`, margin=`{}`.".format(prior_reference["q_raw_29_to_0"], prior_reference["M"], prior_reference["m_margin"]), "",
        "| Phase | Phase (ps) | q_raw[29:0] | M | Final/tail valid | Outside normal envelope | Margin |", "|---|---:|---|---:|---|---|---:|",
    ]
    for item in results:
        lines.append("| {} | {:.3f} | `{}` | {} | {} | {} | {} |".format(item["phase_label"], item["phase_ps"], item["q_raw_29_to_0"], item["M"], item["rail_resolved_and_tail_stable"], item["outside_normal_m_envelope"], item["m_margin"]))
    lines += [
        "", "Worst phase: `{}` at `{:.3f} ps`, q_raw[29:0]=`{}`, M=`{}`, margin=`{}`.".format(worst["phase_label"], worst["phase_ps"], worst["q_raw_29_to_0"], worst["M"], worst["m_margin"]),
        "Minimum margin: `{}`.".format(analysis["minimum_positive_margin"]),
        "", "The Gate is robust only if every new representative phase is rail-resolved/tail-stable and lies strictly outside the closed normal M envelope. This stage stops here regardless of outcome.",
    ]
    report_path = ROOT / "BFE3_P0R_REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    gate_path = ROOT / "BFE3_P0R_GATE.json"
    gate_path.write_text(json.dumps({"stage": "B-FE3-P0R", "gate": gate, "normal_m_envelope": envelope, "worst_phase": worst, "minimum_positive_margin": analysis["minimum_positive_margin"], "analysis_sha256": sha256(analysis_path), "report_sha256": sha256(report_path), "stop_after_stage": True, "next_stage_authorized": False}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"gate": gate, "worst_phase": worst, "minimum_positive_margin": analysis["minimum_positive_margin"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
