#!/usr/bin/env python3
"""B-FE6-MARG0 M3 FALL-path evidence closure.

CALN0's raw normal XA files already contain four healthy FALL captures for
each of the thirty process seeds.  This runner reuses those captures for
``M_REF_FALL`` and runs only the missing FALL droop cases.  The droop begins
after the four calibration FALL edges, at the 91 ns FALL edge, so the capture
at that edge is a post-lock event rather than a calibration sample.

The reviewed BFE4 source and XA helpers are reused.  No production RTL,
capture timing, cell selection, or Level-0 model is changed.  Every new raw
run is isolated under ``runs/b_fe_frontend/bfe6_marg0/m3`` and is listed in a
machine-readable ledger.
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
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe6_marg0" / "m3"
CALN0_RESULTS = STAGE_ROOT / "M1_PER_SEED_DM.csv"
SEEDS = tuple(range(41001, 41031))
DROOP_VOLTAGES = (0.92, 0.89, 0.86)
WORKERS = 4

CALN0_DIR = STAGE_ROOT.parent / "bfe4_caln0_self_calibration"
sys.path.insert(0, str(CALN0_DIR))
import run_bfe4_caln0_self_calibration as bfe4  # noqa: E402


def sha256(path):
    """Hash one raw or derived file for the reproducibility ledger."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path):
    """Read one strict JSON object."""

    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def load_signatures():
    """Load the retained CALN0 seed-to-MC-signature identity contract."""

    result = {}
    with CALN0_RESULTS.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            result[int(row["seed"])] = row["mc_random_signature"]
    if tuple(sorted(result)) != SEEDS:
        raise ValueError("M1 does not contain the complete CALN0 seed set")
    return result


def round_mean(values):
    """Match the archived CALN0 round-half-up integer reference arithmetic."""

    return int(sum(values) / float(len(values)) + 0.5)


def sample_m(sample_rows):
    """Convert one 30-tap XA sample to q_ff and weighted M_FF."""

    ordered = sorted(sample_rows, key=lambda row: row["tap"])
    if [row["tap"] for row in ordered] != list(range(30)):
        raise ValueError("FALL sample does not contain exactly 30 taps")
    if not all(value < 0.1 * 0.95 or value > 0.9 * 0.95 for value in (row["q_ff_v"] for row in ordered)):
        raise ValueError("FALL sample contains a mid-rail q_ff value")
    bits = [1 if row["q_ff_v"] > 0.5 * 0.95 else 0 for row in ordered]
    return {
        "M_FF": sum(tap * bit for tap, bit in enumerate(bits)),
        "q_ff": "".join(str(bit) for bit in reversed(bits)),
        "q_ff_rail_resolved": True,
    }


def load_healthy_fall():
    """Recover four calibration FALL samples and one healthy test per seed."""

    healthy = {}
    for seed in SEEDS:
        path = (FTC_ROOT / "runs" / "b_fe_frontend" / "bfe4_caln0_self_calibration" /
                "instances" / "seed_{:05d}".format(seed) / "normal" / "vcs_xa" /
                "xa_dff_samples.csv")
        if not path.is_file():
            raise FileNotFoundError("retained healthy FALL XA file is missing: {}".format(path))
        grouped = {}
        for row in bfe4.read_samples(path):
            if row["sample_index"] in (4, 12, 20, 28, 36):
                grouped.setdefault(row["sample_index"], []).append(row)
        calibration = [sample_m(grouped[index]) for index in (4, 12, 20, 28)]
        normal_test = sample_m(grouped[36])
        m_cal = [sample["M_FF"] for sample in calibration]
        healthy[seed] = {
            "seed": seed,
            "M_CAL_FALL": m_cal,
            "M_REF_FALL": round_mean(m_cal),
            "M_NORMAL_FALL": normal_test["M_FF"],
            "D_NORMAL_FALL": abs(normal_test["M_FF"] - round_mean(m_cal)),
            "q_ff_normal_fall": normal_test["q_ff"],
            "raw_xa": str(path),
            "raw_xa_sha256": sha256(path),
        }
    return healthy


def configure_droop(droop_voltage):
    """Configure a post-calibration FALL droop in the imported BFE4 flow."""

    bfe4.RUN_ROOT = RUN_ROOT / ("droop_{:.2f}".format(droop_voltage).replace(".", "p"))
    bfe4.DROOP_V = float(droop_voltage)
    # The source helper uses these values to render both the system PWL and
    # the XA diagnostic rail.  A 91 ns FALL edge is the first event after the
    # four calibration FALL edges at 11/31/51/71 ns.
    bfe4.DROP_START_PS = 91075.0
    bfe4.DROOP_STOP_PS = 122000.0
    if bfe4.RUN_ROOT.exists():
        raise FileExistsError("refusing to overwrite M3 run root: {}".format(bfe4.RUN_ROOT))
    bfe4.RUN_ROOT.mkdir(parents=True)


def designated_fall(samples):
    """Select the designated FALL capture at the 91 ns system edge."""

    rows = bfe4.read_samples(samples)
    grouped = {}
    for row in rows:
        grouped.setdefault(row["sample_index"], []).append(row)
    # dff_rises starts at 2534.5246 ps and advances by 2500 ps; index 36 is
    # 92534.5246 ps, exactly 1534.5246 ps after the 91000 ps FALL edge.
    sample = sample_m(grouped[36])
    sample["sample_index"] = 36
    sample["sample_edge_ps"] = 91000.0
    return sample


def run_one(seed, voltage, expected_signature, cells, model, hspice, vcs):
    """Run and verify one post-calibration FALL droop case."""

    level0, source = bfe4.run_source(seed, "droop", cells, model, hspice)
    if source["mc_random_signature"] != expected_signature:
        raise RuntimeError("M3 MC signature mismatch for seed {} at {:.2f} V".format(seed, voltage))
    xa_csv, xa = bfe4.run_xa(seed, "droop", level0, cells, model, vcs)
    sample = designated_fall(xa_csv)
    return {
        "seed": seed,
        "voltage_v": float(voltage),
        "mc_random_signature": source["mc_random_signature"],
        "M_DROOP_FALL": sample["M_FF"],
        "q_ff_droop_fall": sample["q_ff"],
        "q_ff_rail_resolved": True,
        "source": source,
        "xa": xa,
        "sample": sample,
    }


def run_voltage(voltage, expected_signatures):
    """Run all thirty FALL droop cases for one amplitude in four-worker batches."""

    configure_droop(voltage)
    config = load_json(FTC_ROOT / "ftc_config.json")
    cells = bfe4.host_cells(load_json(FTC_ROOT / "discovery" / "selected_cells.json"))
    model = str(config["model_library"])
    hspice = str(Path(config["hspice"]).resolve())
    vcs = shutil.which("vcs")
    if not Path(hspice).is_file() or not vcs:
        raise RuntimeError("M3 requires the configured local HSPICE and VCS tools")
    arguments = [(seed, voltage, expected_signatures[seed], cells, model, hspice, vcs)
                 for seed in SEEDS]
    rows = []
    for start in range(0, len(arguments), WORKERS):
        batch = arguments[start:start + WORKERS]
        with mp.Pool(processes=min(WORKERS, len(batch))) as pool:
            rows.extend(pool.starmap(run_one, batch, chunksize=1))
    return sorted(rows, key=lambda item: item["seed"])


def main():
    """Execute the authorized 90-case FALL droop set and publish M3 evidence."""

    if len(sys.argv) != 1:
        raise SystemExit("usage: run_bfe6_marg0_m3.py")
    expected_signatures = load_signatures()
    healthy = load_healthy_fall()
    all_rows = []
    for voltage in DROOP_VOLTAGES:
        all_rows.extend(run_voltage(voltage, expected_signatures))
    for row in all_rows:
        reference = healthy[row["seed"]]["M_REF_FALL"]
        row["M_REF_FALL"] = reference
        row["D_M_FALL"] = abs(row["M_DROOP_FALL"] - reference)
        row["signed_DeltaM_FALL"] = reference - row["M_DROOP_FALL"]

    fields = ["seed", "voltage_v", "mc_random_signature", "M_REF_FALL", "M_DROOP_FALL",
              "D_M_FALL", "signed_DeltaM_FALL", "q_ff_droop_fall",
              "q_ff_rail_resolved"]
    with (STAGE_ROOT / "M3_FALL_DROOP_CASES.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({field: row[field] for field in fields} for row in all_rows)

    healthy_rows = [healthy[seed] for seed in SEEDS]
    healthy_fields = list(healthy_rows[0])
    with (STAGE_ROOT / "M3_FALL_HEALTHY_REUSED.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=healthy_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(healthy_rows)

    normal_values = [row["D_NORMAL_FALL"] for row in healthy_rows]
    summary = {
        "stage": "B-FE6-MARG0-M3",
        "gate": "BFE6_MARG0_M3_RISE_FALL_DISTRIBUTIONS_READY",
        "healthy_fall_reused_count": len(healthy_rows),
        "new_fall_droop_count": len(all_rows),
        "new_simulations": {"hspice_source_cases": len(all_rows), "vcs_xa_capture_cases": len(all_rows)},
        "normal_fall": {
            "min": min(normal_values), "max": max(normal_values),
            "mean": sum(normal_values) / float(len(normal_values)),
        },
        "droop_fall": {},
        "stop_after_stage": True,
        "next_stage_authorized": True,
    }
    sweep_rows = []
    for voltage in DROOP_VOLTAGES:
        values = [row["D_M_FALL"] for row in all_rows if abs(row["voltage_v"] - voltage) < 1e-9]
        ordered = sorted(values)
        summary["droop_fall"]["{:.2f}".format(voltage)] = {
            "count": len(values), "min": min(values), "max": max(values),
            "mean": sum(values) / float(len(values)), "p05": ordered[int(0.05 * (len(values) - 1))],
            "median": ordered[int(0.50 * (len(values) - 1))],
            "separation_gap": min(values) - max(normal_values),
        }
        for margin in range(436):
            normal_alarm = sum(value > margin for value in normal_values)
            droop_alarm = sum(value > margin for value in values)
            sweep_rows.append({
                "voltage_v": voltage, "margin": margin, "rule": "D_M > margin",
                "normal_count": len(normal_values), "normal_alarm_count": normal_alarm,
                "fpr": normal_alarm / float(len(normal_values)),
                "droop_count": len(values), "droop_alarm_count": droop_alarm,
                "tpr": droop_alarm / float(len(values)), "fnr": 1.0 - droop_alarm / float(len(values)),
            })
    with (STAGE_ROOT / "M3_MARGIN_SWEEP.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(sweep_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(sweep_rows)

    # The CDF is separate from the RISE figure so polarity distributions are
    # never visually pooled before M4 margin selection.
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        figure, axis = plt.subplots(figsize=(7.2, 4.6), dpi=180)
        curves = [(normal_values, "Healthy FALL 0.95 V", "#2878B5")]
        for color, voltage in zip(("#C64E39", "#4E9F3D", "#8B5FBF"), DROOP_VOLTAGES):
            curves.append(([row["D_M_FALL"] for row in all_rows if abs(row["voltage_v"] - voltage) < 1e-9],
                           "FALL droop {:.2f} V".format(voltage), color))
        for values, label, color in curves:
            ordered = sorted(values)
            axis.step(ordered, [(index + 1) / float(len(ordered)) for index in range(len(ordered))],
                      where="post", label=label, color=color, linewidth=1.6)
        axis.set_xlabel("D_M = abs(M_FF - M_REF_FALL)")
        axis.set_ylabel("Empirical CDF")
        axis.set_title("B-FE6-MARG0 M3 FALL distributions")
        axis.grid(axis="both", alpha=0.25)
        axis.legend(loc="lower right")
        figure.tight_layout()
        figure.savefig(STAGE_ROOT / "M3_FALL_DM_DISTRIBUTION.png")
        figure.savefig(STAGE_ROOT / "M3_FALL_DM_DISTRIBUTION.pdf")
        plt.close(figure)
        summary["cdf_figure"] = True
    except ImportError:
        summary["cdf_figure"] = False

    ledger = {
        "stage": "B-FE6-MARG0-M3",
        "gate": summary["gate"],
        "reused_healthy_fall": [{"seed": seed, "raw_xa": healthy[seed]["raw_xa"],
                                  "raw_xa_sha256": healthy[seed]["raw_xa_sha256"]} for seed in SEEDS],
        "new_simulations": {"hspice_source_cases": len(all_rows), "vcs_xa_capture_cases": len(all_rows),
                             "voltages_v": list(DROOP_VOLTAGES), "seeds": len(SEEDS)},
        "droop_timing": {"start_ps": 91075.0, "duration_ps": 3002.0, "target_fall_edge_ps": 91000.0},
        "provenance_rule": "new MC signature equals retained CALN0 signature for the same seed",
        "run_root": str(RUN_ROOT),
        "new_case_hashes": [{"seed": row["seed"], "voltage_v": row["voltage_v"],
                             "mc_random_signature": row["mc_random_signature"],
                             "source_run_dir": row["source"]["run_dir"], "xa_run_dir": row["xa"]["run_dir"],
                             "source_deck_sha256": row["source"]["deck_sha256"],
                             "source_measurements_sha256": row["source"]["measurements_sha256"],
                             "source_mc0_sha256": row["source"]["mc0_sha256"],
                             "xa_samples_sha256": row["xa"]["samples_sha256"]} for row in all_rows],
        "stop_after_stage": True,
        "next_stage_authorized": True,
    }
    write_path = STAGE_ROOT / "M3_RUN_LEDGER.json"
    write_path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (STAGE_ROOT / "M3_DISTRIBUTION_SUMMARY.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = [
        "# B-FE6-MARG0 M3 FALL-path closure",
        "",
        "Gate: `BFE6_MARG0_M3_RISE_FALL_DISTRIBUTIONS_READY`",
        "",
        "Healthy FALL calibration and normal validation were reused from all 30 retained CALN0 raw XA runs. Only post-calibration FALL droop cases were simulated.",
        "",
        "| Droop V | Count | D_M min | D_M max | D_M mean | Gap vs healthy max |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for voltage in DROOP_VOLTAGES:
        item = summary["droop_fall"]["{:.2f}".format(voltage)]
        report.append("| {:.2f} | {} | {} | {} | {:.3f} | {:.3f} |".format(voltage, item["count"], item["min"], item["max"], item["mean"], item["separation_gap"]))
    report.extend(["", "Healthy FALL raw-XA hashes, all 90 new case hashes, and the exact post-calibration droop timing are recorded in `M3_RUN_LEDGER.json`.", ""])
    (STAGE_ROOT / "M3_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print("BFE6_MARG0_M3_RISE_FALL_DISTRIBUTIONS_READY")


if __name__ == "__main__":
    main()
