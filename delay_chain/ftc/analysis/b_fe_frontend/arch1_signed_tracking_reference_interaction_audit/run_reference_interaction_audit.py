#!/usr/bin/env python3
"""Offline ARCH1 signed-comparator/reference-interaction audit.

Only retained BFE8/BFE9/BFE11/BFE12 CSV/JSON artifacts are read.  This script
does not invoke RTL, physical simulators, synthesis, or waveform generation.
For each hypothetical reference displacement DeltaR, it evaluates the signed
branch with the exact relation e_track = e_startup - DeltaR under three
reference-source policies.
"""

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
ANALYSIS_ROOT = HERE.parent
FTC_ROOT = ANALYSIS_ROOT.parents[2]
TASK_ROOT = HERE
BFE8 = ANALYSIS_ROOT / "bfe8_d02_arch0_pilot"
BFE9 = ANALYSIS_ROOT / "bfe9_d01_arch0_amplitude_sensitivity"
BFE11 = ANALYSIS_ROOT / "bfe11_d04_arch0_duration_sensitivity"
BFE12 = ANALYSIS_ROOT / "bfe12_arch1_sign0_signed_droop_rtl"

T_POS_VALUES = (18, 19)
POLICIES = ("A_TRACK_SOURCE", "B_STARTUP_ANCHOR_SOURCE", "C_TRACK_WITH_THRESHOLD_COMPENSATION")
DATASETS = ("healthy_signed_rise", "d01_target", "d02_target", "d04_target")


def sha256(path):
    """Hash each authority so the audit remains reproducible and traceable."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    """Read an ASCII retained CSV without changing or copying its source."""
    with path.open(newline="", encoding="ascii") as stream:
        return list(csv.DictReader(stream))


def load_rows():
    """Load the exact retained samples requested by the audit."""
    manifest_path = BFE12 / "P3_REPLAY_MANIFEST.csv"
    manifest = read_csv(manifest_path)
    selected = {name: [] for name in DATASETS}
    for row in manifest:
        if row["dataset"] in selected:
            selected[row["dataset"]].append({
                "seed": int(row["seed"]),
                "e_startup": int(row["signed_e"]),
                "m_ref_startup": int(row["m_ref"]),
                "m_ff": int(row["m_ff"]),
                "source": row["source_artifact"],
            })
    expected_counts = {"healthy_signed_rise": 360, "d01_target": 30,
                       "d02_target": 30, "d04_target": 30}
    for name in DATASETS:
        if len(selected[name]) != expected_counts[name]:
            raise AssertionError("{} count mismatch".format(name))
        if name != "healthy_signed_rise" and any(item["e_startup"] <= 0 for item in selected[name]):
            raise AssertionError("{} contains non-positive RISE signed error".format(name))
    # Cross-check the BFE12 retained manifest against the original BFE8/BFE9/
    # BFE11 per-seed authorities.  This catches accidental field remapping
    # without modifying any retained source artifact.
    healthy_per_seed = {int(row["seed"]): row for row in read_csv(BFE8 / "BFE8_HEALTHY_PER_SEED.csv")}
    if len(read_csv(BFE8 / "BFE8_D02_HEALTHY_FPR.csv")) != 240:
        raise AssertionError("BFE8 healthy FPR row count changed")
    attack_sources = {
        "d01_target": (BFE9 / "BFE9_D01_PER_SEED.csv", "M_FF_target", "M_REF_RISE"),
        "d02_target": (BFE8 / "BFE8_D02_PER_SEED.csv", "M_FF_target", "M_REF_RISE"),
        "d04_target": (BFE11 / "BFE11_D04_PER_SEED.csv", "M_FF_target", "M_REF_RISE"),
    }
    for name, (path, m_field, ref_field) in attack_sources.items():
        source_by_seed = {int(row["seed"]): row for row in read_csv(path)}
        for item in selected[name]:
            source = source_by_seed[item["seed"]]
            direct_e = int(source[m_field]) - int(source[ref_field])
            if direct_e != item["e_startup"]:
                raise AssertionError("{} seed {} does not match direct source".format(name, item["seed"]))
            if item["seed"] not in healthy_per_seed:
                raise AssertionError("{} seed {} missing BFE8 startup reference".format(name, item["seed"]))
    return selected, manifest_path


def common_reference_delta_bounds(rows):
    """Return the common integer DeltaR range representable by a 9-bit M_REF."""
    refs = [item["m_ref_startup"] for name in DATASETS for item in rows[name]]
    # Every retained seed has M_REF_TRACK=M_REF_STARTUP+DeltaR in [0,435].
    return -min(refs), 435 - max(refs)


def transform(e_startup, delta_r, policy, threshold):
    """Apply one policy; C compensates threshold by the same DeltaR exactly."""
    if policy == "A_TRACK_SOURCE":
        return e_startup - delta_r, threshold
    if policy == "B_STARTUP_ANCHOR_SOURCE":
        return e_startup, threshold
    if policy == "C_TRACK_WITH_THRESHOLD_COMPENSATION":
        return e_startup - delta_r, threshold - delta_r
    raise ValueError(policy)


def measure(rows, delta_r, policy, threshold):
    """Measure signed-only alarms, coverage and weakest signed headroom."""
    result = {}
    for name in DATASETS:
        values = []
        for item in rows[name]:
            e_track, effective_t = transform(item["e_startup"], delta_r, policy, threshold)
            values.append((e_track, effective_t, e_track - effective_t))
        alarms = [value[0] > value[1] for value in values]
        result[name] = {
            "total": len(values),
            "alarms": sum(alarms),
            "coverage": sum(alarms) / float(len(values)),
            "min_signed_headroom": min(value[2] for value in values),
            "max_signed_error": max(value[0] for value in values),
            "effective_threshold_min": min(value[1] for value in values),
            "effective_threshold_max": max(value[1] for value in values),
        }
    return result


def safe(measurement, policy, threshold):
    """Require zero healthy positive FAs and 30/30 detection for each attack."""
    healthy = measurement["healthy_signed_rise"]
    attacks = [measurement[name] for name in ("d01_target", "d02_target", "d04_target")]
    threshold_representable = all(0 <= item["effective_threshold_min"] <= 435 and
                                  0 <= item["effective_threshold_max"] <= 435
                                  for item in measurement.values())
    # C's threshold is a 9-bit candidate input in the eventual implementation;
    # A/B do not alter the threshold source in this audit.
    return (healthy["alarms"] == 0 and all(item["alarms"] == item["total"] for item in attacks)
            and (policy != "C_TRACK_WITH_THRESHOLD_COMPENSATION" or threshold_representable))


def contiguous(values):
    """Summarize a sorted integer set as inclusive contiguous intervals."""
    if not values:
        return []
    values = sorted(values)
    result = []
    start = previous = values[0]
    for value in values[1:]:
        if value != previous + 1:
            result.append([start, previous])
            start = value
        previous = value
    result.append([start, previous])
    return result


def interval_text(intervals):
    """Render integer intervals compactly for the human report."""
    if not intervals:
        return "empty"
    return ", ".join("[{}, {}]".format(left, right) for left, right in intervals)


def main():
    rows, manifest_path = load_rows()
    delta_min, delta_max = common_reference_delta_bounds(rows)
    source_paths = {
        "BFE8_D02_PER_SEED.csv": BFE8 / "BFE8_D02_PER_SEED.csv",
        "BFE8_D02_HEALTHY_FPR.csv": BFE8 / "BFE8_D02_HEALTHY_FPR.csv",
        "BFE9_D01_PER_SEED.csv": BFE9 / "BFE9_D01_PER_SEED.csv",
        "BFE11_D04_PER_SEED.csv": BFE11 / "BFE11_D04_PER_SEED.csv",
        "BFE11_D04_SIGNED_SHADOW.json": BFE11 / "BFE11_D04_SIGNED_SHADOW.json",
        "BFE12_P3_REPLAY_MANIFEST.csv": manifest_path,
        "BFE12_SIGN0_GATE.json": BFE12 / "BFE12_SIGN0_GATE.json",
    }
    all_rows = []
    summary = {"policies": {}}
    for policy in POLICIES:
        summary["policies"][policy] = {}
        for threshold in T_POS_VALUES:
            safe_offsets = []
            baseline = None
            for delta_r in range(delta_min, delta_max + 1):
                measured = measure(rows, delta_r, policy, threshold)
                is_safe = safe(measured, policy, threshold)
                if delta_r == 0:
                    baseline = measured
                if is_safe:
                    safe_offsets.append(delta_r)
                all_rows.append({
                    "policy": policy,
                    "t_pos_rise": threshold,
                    "delta_r": delta_r,
                    "healthy_positive_false_alarms": measured["healthy_signed_rise"]["alarms"],
                    "d01_coverage": "{}/30".format(measured["d01_target"]["alarms"]),
                    "d02_coverage": "{}/30".format(measured["d02_target"]["alarms"]),
                    "d04_coverage": "{}/30".format(measured["d04_target"]["alarms"]),
                    "d01_min_signed_headroom": measured["d01_target"]["min_signed_headroom"],
                    "d02_min_signed_headroom": measured["d02_target"]["min_signed_headroom"],
                    "d04_min_signed_headroom": measured["d04_target"]["min_signed_headroom"],
                    "effective_threshold_min": min(item["effective_threshold_min"] for item in measured.values()),
                    "effective_threshold_max": max(item["effective_threshold_max"] for item in measured.values()),
                    "safe_combined_criterion": int(is_safe),
                })
            summary["policies"][policy][str(threshold)] = {
                "safe_delta_r_integer_intervals": contiguous(safe_offsets),
                "safe_delta_r_continuous_interpretation": "see report; strict comparator boundaries are open where applicable",
                "representable_delta_r_common_range": [delta_min, delta_max],
                "baseline_delta_r_0": baseline,
                "positive_safe_delta_r": [value for value in safe_offsets if value > 0],
                "negative_safe_delta_r": [value for value in safe_offsets if value < 0],
            }

    # Policy B is algebraically invariant; C is invariant while its compensated
    # threshold remains representable.  These statements are checked explicitly.
    if summary["policies"]["B_STARTUP_ANCHOR_SOURCE"]["18"]["safe_delta_r_integer_intervals"] != [[delta_min, delta_max]]:
        raise AssertionError("policy B is not invariant over common range")
    if summary["policies"]["C_TRACK_WITH_THRESHOLD_COMPENSATION"]["18"]["safe_delta_r_integer_intervals"] != [[delta_min, 18]]:
        raise AssertionError("policy C T18 range mismatch")
    if summary["policies"]["C_TRACK_WITH_THRESHOLD_COMPENSATION"]["19"]["safe_delta_r_integer_intervals"] != [[delta_min, 19]]:
        raise AssertionError("policy C T19 range mismatch")
    if summary["policies"]["A_TRACK_SOURCE"]["18"]["safe_delta_r_integer_intervals"] != [[0, 1]]:
        raise AssertionError("policy A T18 range mismatch")
    if summary["policies"]["A_TRACK_SOURCE"]["19"]["safe_delta_r_integer_intervals"] != [[-1, 0]]:
        raise AssertionError("policy A T19 range mismatch")

    csv_path = TASK_ROOT / "REFERENCE_INTERACTION_SWEEP.csv"
    fields = ["policy", "t_pos_rise", "delta_r", "healthy_positive_false_alarms",
              "d01_coverage", "d02_coverage", "d04_coverage",
              "d01_min_signed_headroom", "d02_min_signed_headroom",
              "d04_min_signed_headroom", "effective_threshold_min",
              "effective_threshold_max", "safe_combined_criterion"]
    with csv_path.open("w", newline="", encoding="ascii") as stream:
        # Emit LF-only CSV so the generated evidence passes repository whitespace checks.
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(all_rows)

    summary["gate"] = "ARCH1_SIGNED_TRACKING_REFERENCE_INTERACTION_AUDIT_FROZEN"
    summary["status"] = "PASS"
    summary["scope"] = {
        "healthy_signed_rise": 360,
        "d01_target": 30,
        "d02_target": 30,
        "d04_target": 30,
        "signed_branch_only": True,
        "absolute_branch_recomputed": False,
        "delta_r_common_9bit_reference_range": [delta_min, delta_max],
    }
    summary["frozen_parameters"] = {
        "m_margin_rise": 22,
        "m_margin_fall": 24,
        "t_pos_rise_candidates": [18, 19],
        "formula": "e_track=e_startup-DeltaR",
        "policy_c_threshold": "T_comp=T_pos_rise-DeltaR",
    }
    summary["source_artifact_sha256"] = {name: sha256(path) for name, path in source_paths.items()}
    summary["simulation_accounting"] = {"HSPICE": 0, "VCS": 0, "PrimeSim": 0, "DC": 0}
    summary["recommendation"] = {
        "policy": "B_STARTUP_ANCHOR_SOURCE",
        "reason": "It preserves the signed separation for the full common representable DeltaR range without moving the signed threshold or adding compensation arithmetic; policy C is numerically equivalent only with exact, representable threshold compensation, while A has a narrow retained-population safe interval."
    }
    (TASK_ROOT / "REFERENCE_INTERACTION_SUMMARY.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")

    report = [
        "# ARCH1 Signed Tracking Reference-Interaction Audit",
        "",
        "Gate: `ARCH1_SIGNED_TRACKING_REFERENCE_INTERACTION_AUDIT_FROZEN`",
        "",
        "This is a retained-data-only offline audit.  It reads BFE8/BFE9/BFE11/BFE12 artifacts and evaluates the signed comparator branch only; it does not rerun or alter the absolute comparator.",
        "",
        "## Scope and formula",
        "",
        "The audit uses 360 healthy RISE samples, 30 D01 targets, 30 D02 targets, and 30 D04 targets.  For a hypothetical `DeltaR=M_REF_TRACK-M_REF_STARTUP`, it applies `e_track=e_startup-DeltaR` and strict `e>T_POS_RISE` at 18 and 19.  The common retained 9-bit reference-code range is `[{}, {}]` because startup references span 153..235.".format(delta_min, delta_max),
        "",
        "The safe interval criterion is zero healthy positive false alarms plus 30/30 signed detection for D01, D02, and D04.  Intervals below are inclusive integer DeltaR values; strict-comparator continuous bounds are stated separately.",
        "",
        "## Policy comparison",
        "",
        "| Policy | T | Integer safe DeltaR | Continuous interpretation | Weakest attack headroom at DeltaR=0 |",
        "|---|---:|---|---|---:|",
    ]
    continuous = {
        ("A_TRACK_SOURCE", 18): "[0, 2)",
        ("A_TRACK_SOURCE", 19): "[-1, 1)",
        ("B_STARTUP_ANCHOR_SOURCE", 18): "[-153, 200] (representability bound)",
        ("B_STARTUP_ANCHOR_SOURCE", 19): "[-153, 200] (representability bound)",
        ("C_TRACK_WITH_THRESHOLD_COMPENSATION", 18): "[-153, 18] (threshold-code bound)",
        ("C_TRACK_WITH_THRESHOLD_COMPENSATION", 19): "[-153, 19] (threshold-code bound)",
    }
    for policy in POLICIES:
        for threshold in T_POS_VALUES:
            item = summary["policies"][policy][str(threshold)]
            headroom = min(item["baseline_delta_r_0"][name]["min_signed_headroom"] for name in ("d01_target", "d02_target", "d04_target"))
            report.append("| {} | {} | {} | {} | {} |".format(policy, threshold, interval_text(item["safe_delta_r_integer_intervals"]), continuous[(policy, threshold)], headroom))
    report += [
        "",
        "## Baseline and headroom",
        "",
        "At DeltaR=0, the weakest signed headroom is D01/D04 `+2` M-codes at T=18 and `+1` M-code at T=19; D02 is `+23` and `+22` respectively.  Under policy A, every additional reference displacement subtracts directly from these headrooms.  Under B and exact C compensation, they remain unchanged.",
        "",
        "Policy A therefore has only `[0,1]` integer safety at T=18 and `[-1,0]` at T=19.  Positive displacement beyond that loses the weakest D01/D04 detections; negative displacement eventually creates healthy positive false alarms.",
        "",
        "Policy B keeps the signed comparator on the startup/trusted anchor, so all retained metrics are invariant over the common representable range `[-153,200]`.",
        "",
        "Policy C uses `T_comp=T_POS_RISE-DeltaR`; it is algebraically equivalent to B, but its practical interval is limited by the 9-bit threshold range to `[-153,18]` at T=18 and `[-153,19]` at T=19.",
        "",
        "## Evidence conclusion",
        "",
        "Policy B is the strongest candidate for the next TRACK0 RTL stage: it preserves the frozen signed-error separation without making the signed threshold track mutable reference state and without adding threshold-compensation arithmetic.  Policy C is a valid offline control but should remain a fallback comparison because exact compensation, threshold encoding, and saturation behavior would become new RTL contracts.  Policy A should not be the default signed-comparator source because its retained-population safe interval is narrow.",
        "",
        "No new T_POS was selected.  No tracker, waveform, process population, frontend, production ARCH0 RTL, SIGN0 RTL, or physical simulation was modified or executed.",
        "",
        "Artifacts: `REFERENCE_INTERACTION_SWEEP.csv`, `REFERENCE_INTERACTION_SUMMARY.json`, and `REFERENCE_INTERACTION_RUN_LEDGER.json`.",
    ]
    (TASK_ROOT / "REFERENCE_INTERACTION_REPORT.md").write_text("\n".join(report) + "\n", encoding="ascii")

    ledger = {
        "gate": "ARCH1_SIGNED_TRACKING_REFERENCE_INTERACTION_AUDIT_FROZEN",
        "status": "PASS",
        "analysis_script": "run_reference_interaction_audit.py",
        "sweep_csv": str(csv_path),
        "simulation_accounting": {"HSPICE": 0, "VCS": 0, "PrimeSim": 0, "DC": 0},
        "modified_authorities": [],
        "population_or_waveform_regeneration": False,
        "source_artifact_sha256": summary["source_artifact_sha256"],
        "recommendation": summary["recommendation"],
    }
    (TASK_ROOT / "REFERENCE_INTERACTION_RUN_LEDGER.json").write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print("ARCH1_SIGNED_TRACKING_REFERENCE_INTERACTION_AUDIT_FROZEN")


if __name__ == "__main__":
    main()
