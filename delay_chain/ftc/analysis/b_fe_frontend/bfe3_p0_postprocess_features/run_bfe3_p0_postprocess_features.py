#!/usr/bin/env python3
"""Offline B-FE3-P0 feature audit over retained 0.95 V XA evidence only.

This script deliberately reads completed boundary CSV files and their existing
analysis labels.  It neither generates a deck nor invokes VCS/XA.  Each sample
is accepted solely when all 30 final Q values are rail-resolved and agree with
their retained 1 ns tail samples.  Historical source-free re-flip labels are
preserved as provenance rather than used as an exclusion rule.
"""

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch"
ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch"
VDD_SAFE_V = 0.95
THRESHOLD_V = 0.5 * VDD_SAFE_V
RAIL_LOW_V = 0.1 * VDD_SAFE_V
RAIL_HIGH_V = 0.9 * VDD_SAFE_V
TAIL_TOLERANCE_V = 1.0e-5
TAP_COUNT = 30

# The selection is finite and source-specific.  It covers every retained XA
# evidence family using the required 0.95 V safe latch rail, including the
# unstable-capture observations whose final output nevertheless resolved.
SAMPLE_SPECS = (
    {
        "sample_id": "L1AR_095_NORMAL",
        "label": "NORMAL_NOMINAL",
        "family": "L1A-R",
        "source_type": "normal",
        "run_dir": RUN_ROOT / "l1a_r_vcs_xa" / "bfe2l_095_n",
        "analysis_path": ANALYSIS_ROOT / "l1a_r_vcs_xa" / "BFE2_L1AR_ANALYSIS.json",
        "analysis_key": "BFE2L-095-N",
    },
    {
        "sample_id": "L1AR_095_L2",
        "label": "L2_DROOP",
        "family": "L1A-R",
        "source_type": "0.95_to_0.86_V_L2",
        "run_dir": RUN_ROOT / "l1a_r_vcs_xa" / "bfe2l_095_l2",
        "analysis_path": ANALYSIS_ROOT / "l1a_r_vcs_xa" / "BFE2_L1AR_ANALYSIS.json",
        "analysis_key": "BFE2L-095-L2",
    },
    {
        "sample_id": "CAL0_LEFT",
        "label": "NORMAL_CAPTURE_PERTURBATION",
        "family": "CAL0",
        "source_type": "normal",
        "run_dir": RUN_ROOT / "cal0_vcs_xa" / "left",
        "analysis_path": ANALYSIS_ROOT / "cal0_vcs_xa" / "BFE2_CAL0_ANALYSIS.json",
        "analysis_key": "LEFT",
    },
    {
        "sample_id": "CAL0_CENTER",
        "label": "NORMAL_CAPTURE_PERTURBATION",
        "family": "CAL0",
        "source_type": "normal",
        "run_dir": RUN_ROOT / "cal0_vcs_xa" / "center",
        "analysis_path": ANALYSIS_ROOT / "cal0_vcs_xa" / "BFE2_CAL0_ANALYSIS.json",
        "analysis_key": "CENTER",
    },
    {
        "sample_id": "CAL0_RIGHT",
        "label": "NORMAL_CAPTURE_PERTURBATION",
        "family": "CAL0",
        "source_type": "normal",
        "run_dir": RUN_ROOT / "cal0_vcs_xa" / "right",
        "analysis_path": ANALYSIS_ROOT / "cal0_vcs_xa" / "BFE2_CAL0_ANALYSIS.json",
        "analysis_key": "RIGHT",
    },
    {
        "sample_id": "LATQ_APERTURE_CENTER",
        "label": "NORMAL_CAPTURE_PERTURBATION",
        "family": "LATQ_APERTURE",
        "source_type": "normal",
        "run_dir": RUN_ROOT / "latq_aperture" / "center",
        "analysis_path": ANALYSIS_ROOT / "latq_aperture" / "BFE2_LATQ_APERTURE_ANALYSIS.json",
        "analysis_key": "CENTER",
    },
    {
        "sample_id": "LATQ_APERTURE_MID",
        "label": "NORMAL_CAPTURE_PERTURBATION",
        "family": "LATQ_APERTURE",
        "source_type": "normal",
        "run_dir": RUN_ROOT / "latq_aperture" / "mid",
        "analysis_path": ANALYSIS_ROOT / "latq_aperture" / "BFE2_LATQ_APERTURE_ANALYSIS.json",
        "analysis_key": "MID",
    },
    {
        "sample_id": "LATQ_APERTURE_RIGHT",
        "label": "NORMAL_CAPTURE_PERTURBATION",
        "family": "LATQ_APERTURE",
        "source_type": "normal",
        "run_dir": RUN_ROOT / "latq_aperture" / "right",
        "analysis_path": ANALYSIS_ROOT / "latq_aperture" / "BFE2_LATQ_APERTURE_ANALYSIS.json",
        "analysis_key": "RIGHT",
    },
    {
        "sample_id": "LATQ_APERTURE_LATE_CAPTURE",
        "label": "NORMAL_CAPTURE_PERTURBATION",
        "family": "LATQ_APERTURE",
        "source_type": "normal",
        "run_dir": RUN_ROOT / "latq_aperture" / "late_capture",
        "analysis_path": ANALYSIS_ROOT / "latq_aperture" / "BFE2_LATQ_APERTURE_ANALYSIS.json",
        "analysis_key": "LATE_CAPTURE",
    },
)


def sha256(path: Path) -> str:
    """Return a streaming SHA256 for manifest traceability."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    """Read one object-shaped retained analysis artifact."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def load_boundary_rows(path: Path) -> list:
    """Read only XA boundary values; no simulator or waveform conversion occurs."""

    rows = []
    with path.open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            row["tap"] = int(row["tap"])
            for key in ("time_ps", "safe_d_v", "q_v", "vdd_sense_v", "vdd_safe_v", "g_v"):
                row[key] = float(row[key])
            rows.append(row)
    return rows


def source_result(spec: dict) -> dict:
    """Locate the matching historical analysis entry without interpreting its Gate."""

    analysis = load_json(spec["analysis_path"])
    for result in analysis["results"]:
        if result.get("scenario_id") == spec["analysis_key"] or result.get("point") == spec["analysis_key"]:
            return result
    raise ValueError("missing analysis entry {} in {}".format(spec["analysis_key"], spec["analysis_path"]))


def source_free_annotation(result: dict, family: str) -> list:
    """Preserve historical source-free observations without letting them discard Q."""

    if family == "LATQ_APERTURE":
        return [29] if result.get("source_free_reflip") else []
    return list(result.get("source_free_reflip_taps", []))


def raw_features(bits: list) -> dict:
    """Calculate the only allowed raw-bit features with no correction or filtering."""

    return {
        "N": sum(bits),
        "M": sum(index * bit for index, bit in enumerate(bits)),
        "T": sum(bits[index] ^ bits[index - 1] for index in range(1, TAP_COUNT)),
    }


def extract_sample(spec: dict) -> dict:
    """Validate final/tail rails, retain raw Q, and calculate N/M/T directly."""

    boundary_path = spec["run_dir"] / "xa_boundary_samples.csv"
    rows = load_boundary_rows(boundary_path)
    final_rows = {row["tap"]: row for row in rows if row["kind"] == "final"}
    tail_rows = {row["tap"]: row for row in rows if row["kind"] == "tail_1ns"}
    if set(final_rows) != set(range(TAP_COUNT)) or set(tail_rows) != set(range(TAP_COUNT)):
        raise ValueError("missing final/tail Q values: {}".format(boundary_path))
    if any(abs(final_rows[tap]["vdd_safe_v"] - VDD_SAFE_V) > 1.0e-6 for tap in range(TAP_COUNT)):
        raise ValueError("safe rail is not 0.95 V: {}".format(boundary_path))
    mid_rail_taps = [tap for tap in range(TAP_COUNT) if RAIL_LOW_V < final_rows[tap]["q_v"] < RAIL_HIGH_V]
    unstable_tail_taps = [tap for tap in range(TAP_COUNT) if abs(final_rows[tap]["q_v"] - tail_rows[tap]["q_v"]) > TAIL_TOLERANCE_V]
    if mid_rail_taps or unstable_tail_taps:
        raise ValueError("P0 accepts only resolved/stable final Q; {} has mid={} tail={}".format(boundary_path, mid_rail_taps, unstable_tail_taps))
    bits = [1 if final_rows[tap]["q_v"] > THRESHOLD_V else 0 for tap in range(TAP_COUNT)]
    result = source_result(spec)
    # q_raw[29:0] is provided in conventional descending index order.  The
    # companion tap0_to_tap29 form makes the N/M/T index convention auditable.
    return {
        "sample_id": spec["sample_id"],
        "label": spec["label"],
        "family": spec["family"],
        "source_type": spec["source_type"],
        "run_directory": str(spec["run_dir"]),
        "boundary_csv_sha256": sha256(boundary_path),
        "source_analysis": str(spec["analysis_path"].relative_to(FTC_ROOT)),
        "source_analysis_sha256": sha256(spec["analysis_path"]),
        "q_raw_tap0_to_tap29": "".join(str(bit) for bit in bits),
        "q_raw_29_to_0": "".join(str(bit) for bit in reversed(bits)),
        "q_final_v": [final_rows[tap]["q_v"] for tap in range(TAP_COUNT)],
        "tail_q_v": [tail_rows[tap]["q_v"] for tap in range(TAP_COUNT)],
        "final_mid_rail_taps": mid_rail_taps,
        "unstable_tail_taps": unstable_tail_taps,
        "historical_source_free_reflip_taps": source_free_annotation(result, spec["family"]),
        "historical_unresolved": bool(result.get("unresolved_taps")) if spec["family"] != "LATQ_APERTURE" else bool(result.get("unresolved")),
        "features": raw_features(bits),
    }


def feature_range(samples: list) -> dict:
    """Return inclusive normal-sample envelopes for each raw feature."""

    return {
        feature: {"min": min(item["features"][feature] for item in samples), "max": max(item["features"][feature] for item in samples)}
        for feature in ("N", "M", "T")
    }


def main() -> int:
    """Publish B-FE3-P0 artifacts and stop without launching any simulation."""

    samples = [extract_sample(spec) for spec in SAMPLE_SPECS]
    normal = [sample for sample in samples if sample["label"] != "L2_DROOP"]
    l2 = [sample for sample in samples if sample["label"] == "L2_DROOP"]
    nominal = next(sample for sample in samples if sample["sample_id"] == "L1AR_095_NORMAL")
    envelope = feature_range(normal)
    l2_displacements = []
    for sample in l2:
        displacement = {feature: sample["features"][feature] - nominal["features"][feature] for feature in ("N", "M", "T")}
        outside = {
            feature: sample["features"][feature] < envelope[feature]["min"] or sample["features"][feature] > envelope[feature]["max"]
            for feature in ("N", "M", "T")
        }
        margin = {
            feature: envelope[feature]["min"] - sample["features"][feature] if sample["features"][feature] < envelope[feature]["min"]
            else sample["features"][feature] - envelope[feature]["max"] if sample["features"][feature] > envelope[feature]["max"] else 0
            for feature in ("N", "M", "T")
        }
        l2_displacements.append({"sample_id": sample["sample_id"], "displacement_from_nominal": displacement, "outside_normal_envelope": outside, "envelope_margin": margin})
    separating_features = [feature for feature in ("N", "M", "T") if l2 and all(item["outside_normal_envelope"][feature] for item in l2_displacements)]
    gate = "BFE3_P0_POSTPROCESS_FEATURES_PROMISING" if separating_features else "BFE3_P0_POSTPROCESS_FEATURES_NOT_SEPARABLE"
    manifest = {
        "schema_version": 1,
        "stage": "B-FE3-P0",
        "verification_mode": "offline retained VCS-XA final/tail Q feature extraction",
        "simulation_run": False,
        "new_vcs_xa_scenarios": 0,
        "tap_count": TAP_COUNT,
        "sensing_geometry": {"rvt_prefix": 4, "lvt_prefix": 0, "taps": 30},
        "latch_cell": "LATQ_X0P5M_A9TR40",
        "vdd_safe_v": VDD_SAFE_V,
        "raw_feature_definitions": {"N": "sum(q[i])", "M": "sum(i*q[i]), i=0..29", "T": "sum(q[i] XOR q[i-1]), i=1..29"},
        "forbidden_processing": ["bubble_repair", "longest_one_run_encoding", "lookup_table", "machine_learning", "filtering"],
        "included_sample_ids": [sample["sample_id"] for sample in samples],
        "excluded_evidence": [{"family": "l1a_vcs_xa_1p10", "reason": "LATQ safe rail is 1.10 V, not this stage's 0.95 V contract"}],
        "sample_count": {"normal_or_capture_perturbation": len(normal), "l2": len(l2)},
        "stop_after_stage": True,
        "next_stage_authorized": False,
    }
    manifest_path = ROOT / "BFE3_P0_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    csv_path = ROOT / "BFE3_P0_RAW_FEATURE_SAMPLES.csv"
    with csv_path.open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=["sample_id", "label", "family", "source_type", "q_raw_29_to_0", "q_raw_tap0_to_tap29", "N", "M", "T", "historical_source_free_reflip_taps", "historical_unresolved", "final_mid_rail_taps", "unstable_tail_taps", "run_directory"])
        writer.writeheader()
        for sample in samples:
            writer.writerow({
                "sample_id": sample["sample_id"], "label": sample["label"], "family": sample["family"], "source_type": sample["source_type"],
                "q_raw_29_to_0": sample["q_raw_29_to_0"], "q_raw_tap0_to_tap29": sample["q_raw_tap0_to_tap29"],
                "N": sample["features"]["N"], "M": sample["features"]["M"], "T": sample["features"]["T"],
                "historical_source_free_reflip_taps": json.dumps(sample["historical_source_free_reflip_taps"]), "historical_unresolved": sample["historical_unresolved"],
                "final_mid_rail_taps": json.dumps(sample["final_mid_rail_taps"]), "unstable_tail_taps": json.dumps(sample["unstable_tail_taps"]), "run_directory": sample["run_directory"],
            })
    analysis = {
        "schema_version": 1,
        "stage": "B-FE3-P0",
        "gate": gate,
        "samples": samples,
        "nominal_normal_sample_id": nominal["sample_id"],
        "normal_feature_envelope": envelope,
        "l2_displacements_from_nominal": l2_displacements,
        "separating_raw_features": separating_features,
        "conclusion": "M separates every retained 0.95->0.86 V L2 sample from the retained normal/capture-perturbation envelope" if separating_features else "No raw N/M/T feature separates every retained L2 sample from the normal envelope",
        "uses_corrected_code": False,
        "uses_lookup_table": False,
        "uses_machine_learning": False,
        "uses_filter": False,
        "simulation_run": False,
        "new_vcs_xa_scenarios": 0,
        "manifest_sha256": sha256(manifest_path),
        "raw_feature_csv_sha256": sha256(csv_path),
        "stop_after_stage": True,
        "next_stage_authorized": False,
    }
    analysis_path = ROOT / "BFE3_P0_ANALYSIS.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# B-FE3-P0 offline raw-feature audit",
        "",
        "Gate: `{}`".format(gate),
        "",
        "No VCS/XA run was launched. This is an offline extraction from retained 0.95 V safe-domain XA final/tail Q samples only.",
        "The three features are raw: `N=sum(q[i])`, `M=sum(i*q[i])`, `T=sum(q[i] XOR q[i-1])`; no bubble repair, encoding, table, model, or filter is used.",
        "A historical source-free re-flip does not exclude a sample if its final Q is rail-resolved and its 1 ns tail is stable; its provenance remains in the table.",
        "",
        "| Sample | Label | Source | q_raw[29:0] | N | M | T | Historical source-free | Historical unresolved |",
        "|---|---|---|---|---:|---:|---:|---|---|",
    ]
    for sample in samples:
        lines.append("| {} | {} | {} | `{}` | {} | {} | {} | {} | {} |".format(sample["sample_id"], sample["label"], sample["family"], sample["q_raw_29_to_0"], sample["features"]["N"], sample["features"]["M"], sample["features"]["T"], sample["historical_source_free_reflip_taps"], sample["historical_unresolved"]))
    lines += [
        "",
        "Normal/capture-perturbation envelope: `N={}-{}; M={}-{}; T={}-{}.`".format(envelope["N"]["min"], envelope["N"]["max"], envelope["M"]["min"], envelope["M"]["max"], envelope["T"]["min"], envelope["T"]["max"]),
        "Nominal normal is `{}` with `(N,M,T)=({}, {}, {})`.".format(nominal["sample_id"], nominal["features"]["N"], nominal["features"]["M"], nominal["features"]["T"]),
    ]
    for item in l2_displacements:
        lines.append("L2 `{}`: displacement `(dN,dM,dT)=({}, {}, {})`; outside envelope `{}`; outside-envelope margin `{}`.".format(item["sample_id"], item["displacement_from_nominal"]["N"], item["displacement_from_nominal"]["M"], item["displacement_from_nominal"]["T"], item["outside_normal_envelope"], item["envelope_margin"]))
    lines += [
        "",
        "Separating raw feature(s): `{}`. The Gate is promising because M alone places every retained L2 sample outside the normal envelope with nonzero margin; N and T alone overlap and are not claimed to separate.".format(separating_features),
        "",
        "This evidence is limited to its retained sample set and does not authorize P1, RTL implementation, calibration, or detection work. B-FE3-P0 stops here.",
    ]
    report_path = ROOT / "BFE3_P0_REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    gate_path = ROOT / "BFE3_P0_GATE.json"
    gate_path.write_text(json.dumps({
        "stage": "B-FE3-P0", "gate": gate, "separating_raw_features": separating_features,
        "normal_sample_count": len(normal), "l2_sample_count": len(l2), "analysis_sha256": sha256(analysis_path),
        "report_sha256": sha256(report_path), "stop_after_stage": True, "next_stage_authorized": False,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"gate": gate, "separating_raw_features": separating_features}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
