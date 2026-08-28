#!/usr/bin/env python3
"""B-FE6-MARG0 retained-evidence analysis and margin characterization.

This module intentionally contains only offline analysis.  It reads the
immutable BFE3/BFE4/BFE5 evidence products, verifies their provenance, and
derives the ARCH0 calibrated decision variable:

    D_M = abs(M_FF - M_REF)

No simulator, RTL compiler, or source-artifact writer is invoked here.  New
physical runs, when authorized by the staged plan, are expected to place
their raw files in a separate task-scoped run directory and to be merged only
after their provenance has been checked.
"""

from __future__ import print_function

import csv
import hashlib
import json
import math
import sys
from pathlib import Path


# This file lives beside the BFE6 outputs.  Keeping every derived artifact
# below this directory prevents intermediate tables and plots from spreading
# into the historical BFE3/BFE4 directories.
STAGE_ROOT = Path(__file__).resolve().parent
FRONTEND_ROOT = STAGE_ROOT.parent
FTC_ROOT = FRONTEND_ROOT.parent.parent

CALN0_ROOT = FRONTEND_ROOT / "bfe4_caln0_self_calibration"
VD1_ROOT = FRONTEND_ROOT / "bfe3_vd1_droop_amplitude_response"
VD0_ROOT = FRONTEND_ROOT / "bfe3_vd0_l2_end_to_end_droop"
CLK0_ROOT = FRONTEND_ROOT / "bfe3_clk0_periodic"
CLK1_ROOT = FRONTEND_ROOT / "bfe3_clk1_real_probe_capture"
CLK2_ROOT = FRONTEND_ROOT / "bfe3_clk2_ftc_latch_dff_capture"
BFE5_ROOT = FTC_ROOT / "backend" / "reports"
RTL_ROOT = FTC_ROOT / "rtl"

VOLTAGES = (0.95, 0.92, 0.89, 0.86)
TAPS = 30
MAX_M = sum(range(TAPS))
CALN0_SEEDS = tuple(range(41001, 41031))


def sha256(path):
    """Return the content hash used as the evidence identity.

    Hashing is performed in fixed-size blocks so that large waveform or
    report files do not need to be loaded into memory.  The hash is recorded
    in the M0 matrix and final package rather than modifying the source file.
    """

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Read one JSON object/list using strict UTF-8 decoding."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    """Write one deterministic, human-readable derived JSON artifact."""

    Path(path).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def round_mean(values):
    """Implement the BFE4/ARCH0 round-half-up four-sample mean.

    The production controller realizes division by four with a right shift
    after accumulation.  BFE4 used ``floor(mean + 0.5)`` for its integer
    reference, so MARG0 repeats that exact arithmetic from the four retained
    calibration values instead of trusting a previously derived M_REF field.
    """

    if not values:
        raise ValueError("cannot calculate a reference from zero samples")
    return int(math.floor(sum(values) / float(len(values)) + 0.5))


def weighted_m(q_ff):
    """Calculate the frozen 30-tap ARCH0 feature from a q_ff string.

    Published q_ff strings are stored in tap-29-to-tap-0 display order.  The
    reverse is therefore used before applying the physical tap index.  The
    function validates both binary content and width so malformed evidence
    cannot silently enter a margin distribution.
    """

    if not isinstance(q_ff, str) or len(q_ff) != TAPS:
        raise ValueError("q_ff must contain exactly 30 bits")
    if any(bit not in "01" for bit in q_ff):
        raise ValueError("q_ff contains a non-binary character")
    bits_tap0_to_29 = [int(bit) for bit in reversed(q_ff)]
    return sum(index * bit for index, bit in enumerate(bits_tap0_to_29))


def required_artifacts():
    """Return the immutable files that form the M0 audit input set."""

    names = (
        (CALN0_ROOT, ("BFE4_CALN0_REPORT.md", "BFE4_CALN0_ANALYSIS.json",
                      "BFE4_CALN0_RESULTS.csv", "BFE4_CALN0_RESULTS.json",
                      "BFE4_CALN0_MANIFEST.json", "BFE4_CALN0_GATE.json")),
        (VD1_ROOT, ("BFE3_VD1_REPORT.md", "BFE3_VD1_ANALYSIS.json",
                    "BFE3_VD1_DFF_SAMPLES.csv", "BFE3_VD1_DFF_SAMPLES.json",
                    "BFE3_VD1_MANIFEST.json", "BFE3_VD1_GATE.json")),
        (VD0_ROOT, ("BFE3_VD0_REPORT.md", "BFE3_VD0_ANALYSIS.json",
                    "BFE3_VD0_DFF_SAMPLES.csv", "BFE3_VD0_MANIFEST.json",
                    "BFE3_VD0_GATE.json")),
        (CLK0_ROOT, ("BFE3_CLK0_REPORT.md", "BFE3_CLK0_ANALYSIS.json",
                     "BFE3_CLK0_MANIFEST.json", "BFE3_CLK0_GATE.json")),
        (CLK1_ROOT, ("BFE3_CLK1_REPORT.md", "BFE3_CLK1_ANALYSIS.json",
                     "BFE3_CLK1_MANIFEST.json", "BFE3_CLK1_GATE.json")),
        (CLK2_ROOT, ("BFE3_CLK2_REPORT.md", "BFE3_CLK2_ANALYSIS.json",
                     "BFE3_CLK2_MANIFEST.json", "BFE3_CLK2_GATE.json")),
        (BFE5_ROOT, ("BFE5_TIM0_PIPELINE_CONTRACT.md", "BFE5_GATE_SUMMARY.md")),
        (RTL_ROOT, ("bfe_backend_top.sv", "bfe_backend_ctrl.sv",
                     "bfe_m_feature.sv", "bfe_capture_bank.sv")),
    )
    return [directory / name for directory, files in names for name in files]


def artifact_inventory():
    """Hash every authoritative input and fail closed on missing files."""

    inventory = []
    for path in required_artifacts():
        if not path.is_file():
            raise FileNotFoundError("required evidence is missing: {}".format(path))
        inventory.append({
            "path": str(path.relative_to(FTC_ROOT.parent)),
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
        })
    return inventory


def q_record(item, field, condition, voltage, seed=None):
    """Normalize one retained q/M record for the availability matrix."""

    q_ff = item.get(field)
    if q_ff is None:
        return {
            "available": False,
            "q_ff": None,
            "M_FF": None,
            "rail_resolved": False,
            "seed": seed,
            "condition": condition,
            "voltage_v": voltage,
        }
    calculated = weighted_m(q_ff)
    recorded = item.get("M_FF")
    if recorded is not None and int(recorded) != calculated:
        raise ValueError("retained M_FF disagrees with q_ff: {}".format(item))
    return {
        "available": True,
        "q_ff": q_ff,
        "M_FF": calculated,
        "rail_resolved": bool(item.get("q_ff_rail_resolved", True)),
        "seed": seed,
        "condition": condition,
        "voltage_v": voltage,
    }


def load_caln0():
    """Load and validate the complete 30-seed CALN0 population."""

    analysis = read_json(CALN0_ROOT / "BFE4_CALN0_ANALYSIS.json")
    instances = analysis.get("instances", [])
    if len(instances) != len(CALN0_SEEDS):
        raise ValueError("CALN0 instance count is not 30")
    by_seed = {}
    for instance in instances:
        seed = int(instance["seed"])
        if seed in by_seed:
            raise ValueError("duplicate CALN0 seed {}".format(seed))
        if seed not in CALN0_SEEDS:
            raise ValueError("unexpected CALN0 seed {}".format(seed))
        calibration = [int(value) for value in instance["M_CAL"]]
        if len(calibration) != 4 or any(value < 0 or value > MAX_M for value in calibration):
            raise ValueError("invalid four-sample calibration for seed {}".format(seed))
        reference = round_mean(calibration)
        normal = q_record(instance["normal_test"], "q_ff", "normal", 0.95, seed)
        droop = q_record(instance["droop_test"], "q_ff", "droop", 0.92, seed)
        for record in (normal, droop):
            if not record["rail_resolved"]:
                raise ValueError("unresolved retained q_ff for seed {}".format(seed))
        by_seed[seed] = {
            "seed": seed,
            "mc_random_signature": instance["mc_random_signature"],
            "M_CAL": calibration,
            "M_REF_recomputed": reference,
            "M_REF_published": int(instance["M_REF"]),
            "normal": normal,
            "droop_092": droop,
            "source": instance.get("source", {}),
        }
    if tuple(sorted(by_seed)) != CALN0_SEEDS:
        raise ValueError("CALN0 seed list is incomplete")
    return [by_seed[seed] for seed in CALN0_SEEDS]


def retained_fall_summary():
    """Summarize retained FALL evidence without treating it as population data."""

    sources = []
    for directory, filename in (
        (CLK0_ROOT, "BFE3_CLK0_ANALYSIS.json"),
        (CLK1_ROOT, "BFE3_CLK1_ANALYSIS.json"),
        (CLK2_ROOT, "BFE3_CLK2_ANALYSIS.json"),
        (VD0_ROOT, "BFE3_VD0_ANALYSIS.json"),
        (VD1_ROOT, "BFE3_VD1_ANALYSIS.json"),
    ):
        data = read_json(directory / filename)
        sources.append({
            "artifact": str((directory / filename).relative_to(FTC_ROOT.parent)),
            "sha256": sha256(directory / filename),
            "gate": data.get("gate"),
            "has_fall_fields": any(key in data for key in ("designated_fall", "fall_M_values")),
        })
    return sources


def availability_cell(edge, voltage, caln0_rows, fall_sources):
    """Build one explicit availability cell for the M0 matrix.

    The matrix distinguishes a single-instance waveform from a paired
    process-population datum.  This is important for preventing the retained
    VD1 single-instance FALL code from being mistaken for a 30-seed FALL
    population.
    """

    if edge == "RISE":
        paired = voltage in (0.95, 0.92)
        single = True  # VD1 contains one designated RISE point at all four VDDs.
        return {
            "edge": edge,
            "voltage_v": voltage,
            "source_artifacts": [
                str((CALN0_ROOT / "BFE4_CALN0_RESULTS.json").relative_to(FTC_ROOT.parent))
                if paired else str((VD1_ROOT / "BFE3_VD1_ANALYSIS.json").relative_to(FTC_ROOT.parent))
            ],
            "process_seed_count": len(caln0_rows) if paired else 1,
            "calibration_availability": "population_30_seed" if paired else "single_instance_only",
            "normal_validation_availability": "population_30_seed" if paired else "single_instance_only",
            "droop_availability": "population_30_seed" if paired else "single_instance_only",
            "q_ff_M_FF_availability": True,
            "seed_identity_proof": "mc_random_signature_pair" if paired else "single_run_only",
            "per_chip_D_M_derivable_without_rerun": paired,
            "retained_single_instance": single,
        }
    return {
        "edge": edge,
        "voltage_v": voltage,
        "source_artifacts": [item["artifact"] for item in fall_sources],
        "process_seed_count": 1,
        "calibration_availability": "single_instance_only" if voltage == 0.95 else "absent",
        "normal_validation_availability": "single_instance_only",
        "droop_availability": "absent",
        "q_ff_M_FF_availability": True,
        "seed_identity_proof": "single_instance_no_population_pairing",
        "per_chip_D_M_derivable_without_rerun": False,
        "retained_single_instance": True,
    }


def run_m0():
    """Create the M0 evidence matrix and its immutable-input inventory."""

    inventory = artifact_inventory()
    caln0_rows = load_caln0()
    fall_sources = retained_fall_summary()
    cells = [availability_cell(edge, voltage, caln0_rows, fall_sources)
             for edge in ("RISE", "FALL") for voltage in VOLTAGES]
    matrix = {
        "schema_version": 1,
        "stage": "B-FE6-MARG0-M0",
        "gate": "BFE6_MARG0_M0_EVIDENCE_AUDIT_READY",
        "new_simulations": 0,
        "inventory": inventory,
        "caln0": {
            "artifact": str((CALN0_ROOT / "BFE4_CALN0_RESULTS.json").relative_to(FTC_ROOT.parent)),
            "seed_count": len(caln0_rows),
            "seed_list": list(CALN0_SEEDS),
            "paired_conditions": ["0.95 V healthy", "0.95->0.92 V droop"],
            "reference_arithmetic": "floor(sum(M_CAL)/4 + 0.5)",
        },
        "retained_fall_sources": fall_sources,
        "availability": cells,
        "reuse_ledger": [{
            "datum": "BFE3/BFE4/BFE5 retained evidence",
            "disposition": "reused",
            "new_physical_simulations": 0,
            "reason": "M0 is an offline evidence audit",
        }],
        "stop_after_stage": True,
        "next_stage_authorized": True,
    }
    report_lines = [
        "# B-FE6-MARG0 M0 evidence matrix",
        "",
        "Gate: `BFE6_MARG0_M0_EVIDENCE_AUDIT_READY`",
        "",
        "No HSPICE, PrimeSim, VCS, or DC invocation was made. Historical source artifacts were only read and hashed.",
        "",
        "CALN0 provides 30 paired RISE process instances at healthy 0.95 V and droop 0.92 V. VD1 provides single-instance RISE amplitude points at 0.95/0.92/0.89/0.86 V.",
        "",
        "Retained CLK/VD products provide single-instance FALL observations, but no same-seed FALL droop population; FALL per-chip D_M therefore remains unavailable without new evidence.",
        "",
        "| Edge | VDD (V) | Seeds | Calibration | Normal | Droop | Per-chip D_M without rerun |",
        "|---|---:|---:|---|---|---|---|",
    ]
    for cell in cells:
        report_lines.append("| {edge} | {voltage_v:.2f} | {process_seed_count} | {calibration_availability} | {normal_validation_availability} | {droop_availability} | {per_chip_D_M_derivable_without_rerun} |".format(**cell))
    report_lines.extend(["", "The full immutable-input inventory and SHA-256 values are in `M0_EVIDENCE_MATRIX.json`.", ""])
    (STAGE_ROOT / "M0_EVIDENCE_MATRIX.md").write_text("\n".join(report_lines), encoding="utf-8")
    write_json(STAGE_ROOT / "M0_EVIDENCE_MATRIX.json", matrix)
    return matrix


def percentile(values, fraction):
    """Use the same linear interpolation convention as BFE4 statistics."""

    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    low = int(math.floor(position))
    high = int(math.ceil(position))
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def margin_rows(normal, droop):
    """Return the complete 9-bit strict-greater-than threshold sweep."""

    rows = []
    for margin in range(MAX_M + 1):
        normal_alarms = sum(value > margin for value in normal)
        droop_alarms = sum(value > margin for value in droop)
        rows.append({
            "margin": margin,
            "rule": "D_M > margin",
            "normal_count": len(normal),
            "normal_alarm_count": normal_alarms,
            "fpr": normal_alarms / float(len(normal)) if normal else None,
            "droop_count": len(droop),
            "droop_alarm_count": droop_alarms,
            "tpr": droop_alarms / float(len(droop)) if droop else None,
            "fnr": 1.0 - droop_alarms / float(len(droop)) if droop else None,
        })
    return rows


def write_csv(path, rows, fields):
    """Write a derived CSV with a fixed header and stable row order."""

    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def plot_distributions(normal, droop):
    """Emit one compact empirical CDF figure for the M1 screen."""

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    figure, axis = plt.subplots(figsize=(6.8, 4.4), dpi=180)
    for values, label, color in ((normal, "Normal 0.95 V", "#2878B5"),
                                 (droop, "Droop 0.92 V", "#C64E39")):
        ordered = sorted(values)
        axis.step(ordered, [(index + 1) / float(len(ordered))
                            for index in range(len(ordered))], where="post",
                  label=label, color=color, linewidth=1.8)
    axis.set_xlabel("D_M = abs(M_FF - M_REF)")
    axis.set_ylabel("Empirical CDF")
    axis.set_title("B-FE6-MARG0 M1 calibrated residuals")
    axis.grid(axis="both", alpha=0.25)
    axis.legend(loc="lower right")
    figure.tight_layout()
    figure.savefig(STAGE_ROOT / "M1_DM_DISTRIBUTION.png")
    figure.savefig(STAGE_ROOT / "M1_DM_DISTRIBUTION.pdf")
    plt.close(figure)
    return True


def run_m1():
    """Recompute the retained 30-seed calibrated shallow-droop screen."""

    rows = load_caln0()
    per_seed = []
    for item in rows:
        reference = item["M_REF_recomputed"]
        normal_m = item["normal"]["M_FF"]
        droop_m = item["droop_092"]["M_FF"]
        per_seed.append({
            "seed": item["seed"],
            "mc_random_signature": item["mc_random_signature"],
            "M_CAL_0": item["M_CAL"][0],
            "M_CAL_1": item["M_CAL"][1],
            "M_CAL_2": item["M_CAL"][2],
            "M_CAL_3": item["M_CAL"][3],
            "M_REF_recomputed": reference,
            "M_REF_published": item["M_REF_published"],
            "M_NORMAL": normal_m,
            "M_DROOP_092": droop_m,
            "D_NORMAL": abs(normal_m - reference),
            "D_DROOP_092": abs(droop_m - reference),
            "signed_DeltaM_DROOP": reference - droop_m,
            "q_ff_normal": item["normal"]["q_ff"],
            "q_ff_droop_092": item["droop_092"]["q_ff"],
            "normal_q_ff_rail_resolved": item["normal"]["rail_resolved"],
            "droop_q_ff_rail_resolved": item["droop_092"]["rail_resolved"],
        })
    normal = [row["D_NORMAL"] for row in per_seed]
    droop = [row["D_DROOP_092"] for row in per_seed]
    sweep = margin_rows(normal, droop)
    summary = {
        "stage": "B-FE6-MARG0-M1",
        "gate": "BFE6_MARG0_M1_RETAINED_SHALLOW_MARGIN_CHARACTERIZED",
        "new_simulations": 0,
        "sample_count": {"normal": len(normal), "droop_092": len(droop)},
        "normal": {
            "min": min(normal), "max": max(normal), "mean": sum(normal) / float(len(normal)),
            "p95": percentile(normal, 0.95), "p99": percentile(normal, 0.99),
        },
        "droop_092": {
            "min": min(droop), "max": max(droop), "mean": sum(droop) / float(len(droop)),
            "p05": percentile(droop, 0.05), "median": percentile(droop, 0.50),
        },
        "separation_gap": min(droop) - max(normal),
        "reverse_response_seed_count": sum(row["signed_DeltaM_DROOP"] < 0 for row in per_seed),
        "no_response_seed_count": sum(row["D_DROOP_092"] == 0 for row in per_seed),
        "historical_absolute_M_ablation": {
            "status": "not_reproducible",
            "reason": "CALN0 retains overlap and spread metrics but no exact historical absolute-threshold decision rule",
        },
        "reuse_ledger": [{
            "datum": "CALN0 30-seed calibration/normal/0.92 droop",
            "disposition": "reused",
            "new_physical_simulations": 0,
        }],
        "stop_after_stage": True,
        "next_stage_authorized": True,
    }
    write_csv(STAGE_ROOT / "M1_PER_SEED_DM.csv", per_seed, list(per_seed[0]))
    write_csv(STAGE_ROOT / "M1_MARGIN_SWEEP.csv", sweep, list(sweep[0]))
    write_json(STAGE_ROOT / "M1_DISTRIBUTION_SUMMARY.json", summary)
    write_json(STAGE_ROOT / "M1_RUN_LEDGER.json", summary["reuse_ledger"])
    figure_written = plot_distributions(normal, droop)
    summary["distribution_figure"] = figure_written
    write_json(STAGE_ROOT / "M1_DISTRIBUTION_SUMMARY.json", summary)
    report = [
        "# B-FE6-MARG0 M1 retained shallow-droop screen",
        "",
        "Gate: `BFE6_MARG0_M1_RETAINED_SHALLOW_MARGIN_CHARACTERIZED`",
        "",
        "The 30 CALN0 process instances were recomputed offline. No HSPICE, PrimeSim, VCS, or DC invocation was made.",
        "",
        "| Quantity | Normal | 0.92 V droop |",
        "|---|---:|---:|",
        "| Count | {} | {} |".format(len(normal), len(droop)),
        "| Range | {}..{} | {}..{} |".format(min(normal), max(normal), min(droop), max(droop)),
        "| Mean | {:.3f} | {:.3f} |".format(summary["normal"]["mean"], summary["droop_092"]["mean"]),
        "| p95/p05 | {:.3f} | {:.3f} |".format(summary["normal"]["p95"], summary["droop_092"]["p05"]),
        "",
        "Separation gap `G=min(D_droop)-max(D_normal) = {:.3f}`. Reverse-response seeds: {}. No-response droop seeds: {}.".format(summary["separation_gap"], summary["reverse_response_seed_count"], summary["no_response_seed_count"]),
        "",
        "The signed CALN0 DeltaM field is retained for provenance only; all detector statistics use absolute `D_M`.",
        "The historical absolute-M ablation rule is not recoverable from retained artifacts and is therefore not invented.",
        "",
        "Full per-seed values, all 436 strict-threshold rows, and the reused-only ledger are stored beside this report.",
        "",
    ]
    (STAGE_ROOT / "M1_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    return summary


def main(argv):
    """Run one explicitly selected offline stage; refuse accidental mixing."""

    if len(argv) != 2 or argv[1] not in ("m0", "m1"):
        raise SystemExit("usage: run_bfe6_marg0.py m0|m1")
    STAGE_ROOT.mkdir(parents=True, exist_ok=True)
    if argv[1] == "m0":
        run_m0()
    else:
        # M1 repeats the M0 source checks through load_caln0 and is safe to
        # invoke after M0 without copying or rewriting historical evidence.
        run_m1()
    print("BFE6_MARG0_{}_OFFLINE_PASS".format(argv[1].upper()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
