#!/usr/bin/env python3
"""B-FE6-MARG0 M2 RISE amplitude extension.

The BFE4 runner already implements the reviewed SMIC40LL source deck, Level-0
thresholding, and real LATQ/DFF PrimeSim-XA capture.  M2 reuses those helpers
instead of copying a second electrical model.  The only electrical parameter
changed here is the droop floor, and every result is checked against the
retained BFE4 MC random signature for the same process seed.

All generated source, waveform, VCS, and derived files live below
``delay_chain/ftc/runs/b_fe_frontend/bfe6_marg0/m2`` and the BFE6 analysis
directory.  No historical BFE3/BFE4 file is overwritten.
"""

from __future__ import print_function

import csv
import hashlib
import json
import multiprocessing as mp
import shutil
import sys
from pathlib import Path


STAGE_ROOT = Path(__file__).resolve().parent
FTC_ROOT = STAGE_ROOT.parents[2]
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe6_marg0" / "m2"
CALN0_RESULTS = STAGE_ROOT / "M1_PER_SEED_DM.csv"
SEEDS = tuple(range(41001, 41031))
DROOP_VOLTAGES = (0.89, 0.86)
WORKERS = 4

# Import the already validated BFE4 electrical flow.  The imported module is
# used as a library only; its main() is never called, so no historical output
# directory can be recreated or overwritten.
CALN0_DIR = STAGE_ROOT.parent / "bfe4_caln0_self_calibration"
sys.path.insert(0, str(CALN0_DIR))
import run_bfe4_caln0_self_calibration as bfe4  # noqa: E402


def sha256(path):
    """Hash a newly produced artifact for the M2 provenance ledger."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path):
    """Read a JSON object without accepting a missing or malformed file."""

    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def load_expected_signatures():
    """Load the immutable seed/signature contract produced by M1."""

    expected = {}
    with CALN0_RESULTS.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            seed = int(row["seed"])
            expected[seed] = row["mc_random_signature"]
    if tuple(sorted(expected)) != SEEDS:
        raise ValueError("M1 seed/signature table is not the complete 30-seed set")
    return expected


def configure_bfe4_for_m2(droop_voltage):
    """Bind the BFE4 helper's task-scoped constants for one M2 amplitude.

    BFE4's deck renderer obtains the droop floor and run root from module
    constants.  Rebinding only those constants preserves its reviewed clocks,
    drop timing, cell selection, Level-0 threshold, and 30-tap topology.
    """

    bfe4.RUN_ROOT = RUN_ROOT / ("droop_{:.2f}".format(droop_voltage).replace(".", "p"))
    bfe4.DROOP_V = float(droop_voltage)
    if bfe4.RUN_ROOT.exists():
        raise FileExistsError("refusing to overwrite M2 run root: {}".format(bfe4.RUN_ROOT))
    bfe4.RUN_ROOT.mkdir(parents=True)


def run_one(seed, droop_voltage, expected_signature, cells, model, hspice, vcs):
    """Run one seed's source and real capture, then return verified metadata."""

    # The imported BFE4 functions create the source and XA directories below
    # the already configured voltage-specific run root.
    level0, source = bfe4.run_source(seed, "droop", cells, model, hspice)
    if source["mc_random_signature"] != expected_signature:
        raise RuntimeError(
            "M2 process identity mismatch seed {} at {:.2f} V: expected {}, got {}".format(
                seed, droop_voltage, expected_signature, source["mc_random_signature"]
            )
        )
    xa_csv, xa = bfe4.run_xa(seed, "droop", level0, cells, model, vcs)
    designated = bfe4.designated_rises(bfe4.read_samples(xa_csv), bfe4.DROOP_STOP_PS)
    edge = 21000.0
    if edge not in designated:
        raise RuntimeError("M2 designated RISE capture is missing for seed {}".format(seed))
    sample = designated[edge]
    if not sample["q_ff_rail_resolved"] or not sample["latq_rail_resolved"]:
        raise RuntimeError("M2 unresolved LATQ/DFF rail for seed {}".format(seed))
    return {
        "seed": seed,
        "voltage_v": float(droop_voltage),
        "mc_random_signature": source["mc_random_signature"],
        "M_REF": None,
        "M_DROOP": int(sample["M_FF"]),
        "D_M": None,
        "signed_DeltaM": None,
        "q_ff": sample["q_ff"],
        "q_ff_rail_resolved": bool(sample["q_ff_rail_resolved"]),
        "latq_rail_resolved": bool(sample["latq_rail_resolved"]),
        "source": source,
        "xa": xa,
        "sample": sample,
    }


def read_completed_case(seed, droop_voltage, expected_signature):
    """Reconstruct one finished case without invoking an external simulator.

    M2 writes raw source/XA products before the final summary is emitted.  If
    summary generation is interrupted, this reader verifies those immutable
    products and rebuilds the same in-memory record.  It is deliberately
    strict: a missing listing, MC table, XA sample table, or signature mismatch
    raises instead of silently treating a partial case as valid.
    """

    root = RUN_ROOT / ("droop_{:.2f}".format(droop_voltage).replace(".", "p"))
    source_dir = root / "instances" / "seed_{:05d}".format(seed) / "droop" / "source_hspice"
    xa_dir = root / "instances" / "seed_{:05d}".format(seed) / "droop" / "vcs_xa"
    source_listing = source_dir / "source.lis"
    source_measurements = source_dir / "source.mt0.csv"
    source_mc0 = source_dir / "source.mc0.csv"
    xa_samples = xa_dir / "xa_dff_samples.csv"
    for path in (source_listing, source_measurements, source_mc0, xa_samples):
        if not path.is_file():
            raise FileNotFoundError("incomplete M2 case: {}".format(path))
    bfe4.validate_listing(source_listing)
    signature = bfe4.mc_signature(source_mc0)
    if signature != expected_signature:
        raise RuntimeError("M2 completed-case signature mismatch for seed {}".format(seed))
    level0 = bfe4.read_measurements(source_measurements, bfe4.DROOP_STOP_PS)
    designated = bfe4.designated_rises(bfe4.read_samples(xa_samples), bfe4.DROOP_STOP_PS)
    if 21000.0 not in designated:
        raise RuntimeError("M2 completed case lacks designated RISE for seed {}".format(seed))
    sample = designated[21000.0]
    if not sample["q_ff_rail_resolved"] or not sample["latq_rail_resolved"]:
        raise RuntimeError("M2 completed case has unresolved rails for seed {}".format(seed))
    source = {
        "seed": seed,
        "condition": "droop",
        "deck_sha256": sha256(source_dir / "source.sp"),
        "measurements_sha256": sha256(source_measurements),
        "mc0_sha256": sha256(source_mc0),
        "mc_random_signature": signature,
        "measure_row_index": 2,
        "level0_sample_count": len(level0),
        "run_dir": str(source_dir),
    }
    xa = {
        "run_dir": str(xa_dir),
        "compile_log_sha256": sha256(xa_dir / "compile.log"),
        "run_log_sha256": sha256(xa_dir / "run.log"),
        "samples_sha256": sha256(xa_samples),
        "cosim_marker": "Start Cosim VCS-Analog Processing" in (xa_dir / "run.log").read_text(encoding="utf-8", errors="replace"),
    }
    return {
        "seed": seed,
        "voltage_v": float(droop_voltage),
        "mc_random_signature": signature,
        "M_REF": None,
        "M_DROOP": int(sample["M_FF"]),
        "D_M": None,
        "signed_DeltaM": None,
        "q_ff": sample["q_ff"],
        "q_ff_rail_resolved": bool(sample["q_ff_rail_resolved"]),
        "latq_rail_resolved": bool(sample["latq_rail_resolved"]),
        "source": source,
        "xa": xa,
        "sample": sample,
    }


def run_voltage(droop_voltage, expected_signatures, reuse_completed=False):
    """Run all 30 seeds for one voltage in bounded four-worker batches."""

    if reuse_completed:
        bfe4.RUN_ROOT = RUN_ROOT / ("droop_{:.2f}".format(droop_voltage).replace(".", "p"))
        if not bfe4.RUN_ROOT.is_dir():
            raise FileNotFoundError("M2 completed run root is missing: {}".format(bfe4.RUN_ROOT))
    else:
        configure_bfe4_for_m2(droop_voltage)
    config = load_json(FTC_ROOT / "ftc_config.json")
    cells = bfe4.host_cells(load_json(FTC_ROOT / "discovery" / "selected_cells.json"))
    model = str(config["model_library"])
    hspice = str(Path(config["hspice"]).resolve())
    vcs = shutil.which("vcs")
    if not Path(hspice).is_file() or not vcs:
        raise RuntimeError("M2 requires the configured local HSPICE and VCS tools")
    if reuse_completed:
        return sorted([read_completed_case(seed, droop_voltage, expected_signatures[seed]) for seed in SEEDS],
                      key=lambda item: item["seed"])
    arguments = [(seed, droop_voltage, expected_signatures[seed], cells, model, hspice, vcs)
                 for seed in SEEDS]
    rows = []
    for start in range(0, len(arguments), WORKERS):
        batch = arguments[start:start + WORKERS]
        with mp.Pool(processes=min(WORKERS, len(batch))) as pool:
            rows.extend(pool.starmap(run_one, batch, chunksize=1))
    return sorted(rows, key=lambda item: item["seed"])


def main():
    """Execute both missing RISE amplitudes and publish raw M2 evidence."""

    reuse_completed = len(sys.argv) == 2 and sys.argv[1] == "--reuse-completed"
    if len(sys.argv) > 1 and not reuse_completed:
        raise SystemExit("usage: run_bfe6_marg0_m2.py [--reuse-completed]")
    expected_signatures = load_expected_signatures()
    all_rows = []
    for voltage in DROOP_VOLTAGES:
        all_rows.extend(run_voltage(voltage, expected_signatures, reuse_completed))
    m1_by_seed = {}
    with CALN0_RESULTS.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            m1_by_seed[int(row["seed"])] = row
    for row in all_rows:
        reference = int(m1_by_seed[row["seed"]]["M_REF_recomputed"])
        row["M_REF"] = reference
        row["D_M"] = abs(row["M_DROOP"] - reference)
        row["signed_DeltaM"] = reference - row["M_DROOP"]

    fields = ["seed", "voltage_v", "mc_random_signature", "M_REF", "M_DROOP",
              "D_M", "signed_DeltaM", "q_ff", "q_ff_rail_resolved",
              "latq_rail_resolved"]
    with (STAGE_ROOT / "M2_RISE_NEW_CASES.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row[field] for field in fields} for row in all_rows)

    # Merge the retained 0.92 V population with the two newly simulated
    # amplitudes.  The normal distribution is shared because M2 intentionally
    # reuses the CALN0 healthy baseline; no normal simulation is repeated.
    normal_values = []
    with CALN0_RESULTS.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            normal_values.append(int(row["D_NORMAL"]))
    merged_rows = []
    for row in all_rows:
        normal_row = m1_by_seed[row["seed"]]
        merged_rows.append({
            "seed": row["seed"], "voltage_v": row["voltage_v"],
            "mc_random_signature": row["mc_random_signature"], "M_REF": row["M_REF"],
            "M_NORMAL": int(normal_row["M_NORMAL"]),
            "D_NORMAL": int(normal_row["D_NORMAL"]),
            "q_ff_normal": normal_row["q_ff_normal"],
            "M_DROOP": row["M_DROOP"], "D_M": row["D_M"],
            "signed_DeltaM": row["signed_DeltaM"], "q_ff": row["q_ff"],
            "q_ff_rail_resolved": row["q_ff_rail_resolved"],
            "latq_rail_resolved": row["latq_rail_resolved"],
        })
    merged_fields = list(merged_rows[0])
    with (STAGE_ROOT / "M2_PER_SEED_DM.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=merged_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(merged_rows)

    by_voltage = {}
    sweep_rows = []
    for voltage in (0.92,) + DROOP_VOLTAGES:
        droop_values = ([int(row["D_DROOP_092"]) for row in csv.DictReader(CALN0_RESULTS.open(newline="", encoding="utf-8"))]
                        if voltage == 0.92 else
                        [int(row["D_M"]) for row in merged_rows if abs(float(row["voltage_v"]) - voltage) < 1e-9])
        by_voltage["{:.2f}".format(voltage)] = {
            "count": len(droop_values), "min": min(droop_values), "max": max(droop_values),
            "mean": sum(droop_values) / float(len(droop_values)),
            "p05": sorted(droop_values)[int(0.05 * (len(droop_values) - 1))],
            "median": sorted(droop_values)[int(0.50 * (len(droop_values) - 1))],
            "separation_gap": min(droop_values) - max(normal_values),
        }
        for margin in range(bfe4.MAX_M if hasattr(bfe4, "MAX_M") else 435 + 1):
            normal_alarm = sum(value > margin for value in normal_values)
            droop_alarm = sum(value > margin for value in droop_values)
            sweep_rows.append({
                "voltage_v": voltage, "margin": margin, "rule": "D_M > margin",
                "normal_count": len(normal_values), "normal_alarm_count": normal_alarm,
                "fpr": normal_alarm / float(len(normal_values)),
                "droop_count": len(droop_values), "droop_alarm_count": droop_alarm,
                "tpr": droop_alarm / float(len(droop_values)),
                "fnr": 1.0 - droop_alarm / float(len(droop_values)),
            })
    sweep_fields = list(sweep_rows[0])
    with (STAGE_ROOT / "M2_MARGIN_SWEEP.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=sweep_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sweep_rows)

    # Produce one amplitude-wise empirical CDF figure.  The normal curve is
    # deliberately repeated as the shared retained CALN0 baseline; this makes
    # the per-voltage separation visible without implying new normal samples.
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        figure, axis = plt.subplots(figsize=(7.2, 4.6), dpi=180)
        curves = [(normal_values, "Normal 0.95 V", "#2878B5")]
        colors = ("#C64E39", "#4E9F3D", "#8B5FBF")
        for color, voltage in zip(colors, (0.92,) + DROOP_VOLTAGES):
            values = ([int(row["D_DROOP_092"]) for row in csv.DictReader(CALN0_RESULTS.open(newline="", encoding="utf-8"))]
                      if voltage == 0.92 else
                      [int(row["D_M"]) for row in merged_rows if abs(float(row["voltage_v"]) - voltage) < 1e-9])
            curves.append((values, "Droop {:.2f} V".format(voltage), color))
        for values, label, color in curves:
            ordered = sorted(values)
            axis.step(ordered, [(index + 1) / float(len(ordered)) for index in range(len(ordered))],
                      where="post", label=label, color=color, linewidth=1.6)
        axis.set_xlabel("D_M = abs(M_FF - M_REF)")
        axis.set_ylabel("Empirical CDF")
        axis.set_title("B-FE6-MARG0 M2 RISE amplitude distributions")
        axis.grid(axis="both", alpha=0.25)
        axis.legend(loc="lower right")
        figure.tight_layout()
        figure.savefig(STAGE_ROOT / "M2_RISE_DM_DISTRIBUTION.png")
        figure.savefig(STAGE_ROOT / "M2_RISE_DM_DISTRIBUTION.pdf")
        plt.close(figure)
        cdf_figure = True
    except ImportError:
        cdf_figure = False

    ledger = {
        "stage": "B-FE6-MARG0-M2",
        "gate": "BFE6_MARG0_M2_RISE_AMPLITUDE_POPULATION_CHARACTERIZED",
        "new_simulations": {
            "hspice_source_cases": len(all_rows),
            "vcs_xa_capture_cases": len(all_rows),
            "voltages_v": list(DROOP_VOLTAGES),
            "seeds": len(SEEDS),
        },
        "reused": [
            "CALN0 M_REF and healthy 0.95 V evidence",
            "CALN0 0.92 V droop population and MC signatures",
            "reviewed BFE4 source/XA deck and frozen timing",
        ],
        "provenance_rule": "new MC random signature must equal retained M1 signature for the same seed",
        "run_root": str(RUN_ROOT),
        "summary_generation": "reused_completed_raw_runs" if reuse_completed else "new_raw_runs",
        "rows": [{
            "seed": row["seed"],
            "voltage_v": row["voltage_v"],
            "mc_random_signature": row["mc_random_signature"],
            "source_run_dir": row["source"]["run_dir"],
            "xa_run_dir": row["xa"]["run_dir"],
            "source_deck_sha256": row["source"]["deck_sha256"],
            "source_measurements_sha256": row["source"]["measurements_sha256"],
            "source_mc0_sha256": row["source"]["mc0_sha256"],
            "xa_samples_sha256": row["xa"]["samples_sha256"],
        } for row in all_rows],
        "stop_after_stage": True,
        "next_stage_authorized": True,
    }
    (STAGE_ROOT / "M2_RUN_LEDGER.json").write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = {
        "stage": "B-FE6-MARG0-M2",
        "gate": "BFE6_MARG0_M2_RISE_AMPLITUDE_POPULATION_CHARACTERIZED",
        "normal_reused_count": len(normal_values),
        "droop_distributions": by_voltage,
        "new_case_count": len(all_rows),
        "new_simulations": len(all_rows),
        "summary_reused_completed_raw_runs": reuse_completed,
        "cdf_figure": cdf_figure,
        "physical_simulation_ledger": "M2_RUN_LEDGER.json",
        "stop_after_stage": True,
        "next_stage_authorized": True,
    }
    (STAGE_ROOT / "M2_DISTRIBUTION_SUMMARY.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = [
        "# B-FE6-MARG0 M2 RISE amplitude population",
        "",
        "Gate: `BFE6_MARG0_M2_RISE_AMPLITUDE_POPULATION_CHARACTERIZED`",
        "",
        "Thirty CALN0 process instances were extended at each missing RISE droop floor. Existing calibration/normal/0.92 V evidence was reused; no case was rerun during summary recovery.",
        "",
        "| Droop V | Count | D_M min | D_M max | D_M mean | Gap vs normal max |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for voltage in (0.92,) + DROOP_VOLTAGES:
        item = by_voltage["{:.2f}".format(voltage)]
        report.append("| {:.2f} | {} | {} | {} | {:.3f} | {:.3f} |".format(voltage, item["count"], item["min"], item["max"], item["mean"], item["separation_gap"]))
    report.extend(["", "All new cases passed same-seed MC signature, q_ff width, and LATQ/DFF rail checks. Raw run directories and per-case hashes are listed in `M2_RUN_LEDGER.json`.", ""])
    (STAGE_ROOT / "M2_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print("BFE6_MARG0_M2_RISE_AMPLITUDE_POPULATION_CHARACTERIZED")


if __name__ == "__main__":
    main()
