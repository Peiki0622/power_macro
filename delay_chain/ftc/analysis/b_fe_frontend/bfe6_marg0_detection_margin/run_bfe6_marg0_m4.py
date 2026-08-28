#!/usr/bin/env python3
"""B-FE6-MARG0 M4 offline margin selection.

This module consumes only the retained M1/M2 RISE tables and the newly
closed M3 FALL tables.  It deliberately contains no simulator invocation:
M4 is an integer analysis stage and must not create a second physical-run
campaign.  The two polarities are represented by separate dictionaries all
the way through the calculation so that a RISE margin can never accidentally
be selected from FALL data (or vice versa).
"""

from __future__ import print_function

import csv
import json
from pathlib import Path


# All M4 products live beside the earlier stage products.  Raw HSPICE/VCS
# outputs remain under the task-scoped m3 run root and are never copied here.
STAGE_ROOT = Path(__file__).resolve().parent
MARGIN_MAX = 435
VOLTAGES = (0.92, 0.89, 0.86)


def read_csv(name):
    """Read one stage CSV and return ordinary dictionaries for auditability."""

    with (STAGE_ROOT / name).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def integer_values(rows, field):
    """Convert an integer D_M column while rejecting malformed evidence."""

    values = [int(row[field]) for row in rows]
    if any(value < 0 or value > MARGIN_MAX for value in values):
        raise ValueError("{} contains a value outside the 9-bit margin range".format(field))
    return values


def quantile(values, fraction):
    """Return the nearest-rank empirical quantile without interpolation."""

    ordered = sorted(values)
    index = int((len(ordered) - 1) * fraction)
    return ordered[index]


def stats(values):
    """Summarize one finite population using deterministic integer ranks."""

    ordered = sorted(values)
    return {
        "count": len(values),
        "min": ordered[0],
        "p05": quantile(values, 0.05),
        "median": quantile(values, 0.50),
        "p95": quantile(values, 0.95),
        "p99": quantile(values, 0.99),
        "max": ordered[-1],
        "mean": sum(values) / float(len(values)),
    }


def build_datasets():
    """Load paired RISE/FALL normal and droop populations with provenance checks."""

    m1 = read_csv("M1_PER_SEED_DM.csv")
    m2 = read_csv("M2_PER_SEED_DM.csv")
    m3_normal = read_csv("M3_FALL_HEALTHY_REUSED.csv")
    m3_droop = read_csv("M3_FALL_DROOP_CASES.csv")

    seeds = {int(row["seed"]) for row in m1}
    if len(seeds) != 30:
        raise ValueError("M1 must contain exactly 30 RISE seeds")
    if {int(row["seed"]) for row in m3_normal} != seeds:
        raise ValueError("M3 FALL normal seed set is not paired with M1")
    if len(m2) != 60 or len(m3_droop) != 90:
        raise ValueError("M2/M3 droop populations are incomplete")

    # Verify the retained/new identity contract before any aggregate is made.
    signatures = {int(row["seed"]): row["mc_random_signature"] for row in m1}
    for row in m2 + m3_droop:
        if signatures[int(row["seed"])] != row["mc_random_signature"]:
            raise ValueError("seed/signature mismatch in M4 input")

    rise_normal = integer_values(m1, "D_NORMAL")
    rise_droop = {0.92: integer_values(m1, "D_DROOP_092")}
    for voltage in (0.89, 0.86):
        rows = [row for row in m2 if abs(float(row["voltage_v"]) - voltage) < 1e-9]
        if len(rows) != 30:
            raise ValueError("M2 is missing the paired {:.2f} V population".format(voltage))
        rise_droop[voltage] = integer_values(rows, "D_M")

    fall_normal = integer_values(m3_normal, "D_NORMAL_FALL")
    fall_droop = {}
    for voltage in VOLTAGES:
        rows = [row for row in m3_droop if abs(float(row["voltage_v"]) - voltage) < 1e-9]
        if len(rows) != 30:
            raise ValueError("M3 is missing the paired {:.2f} V population".format(voltage))
        fall_droop[voltage] = integer_values(rows, "D_M_FALL")

    return {
        "RISE": {"normal": rise_normal, "droop": rise_droop},
        "FALL": {"normal": fall_normal, "droop": fall_droop},
    }


def margin_rows(datasets):
    """Generate the exact strict-``D_M > margin`` decision table."""

    rows = []
    for polarity, dataset in datasets.items():
        normal = dataset["normal"]
        for voltage in VOLTAGES:
            droop = dataset["droop"][voltage]
            for margin in range(MARGIN_MAX + 1):
                normal_alarm = sum(value > margin for value in normal)
                droop_alarm = sum(value > margin for value in droop)
                tpr = droop_alarm / float(len(droop))
                rows.append({
                    "polarity": polarity,
                    "voltage_v": voltage,
                    "margin": margin,
                    "rule": "D_M > margin",
                    "normal_count": len(normal),
                    "normal_alarm_count": normal_alarm,
                    "fpr": normal_alarm / float(len(normal)),
                    "droop_count": len(droop),
                    "droop_alarm_count": droop_alarm,
                    "tpr": tpr,
                    "fnr": 1.0 - tpr,
                })
    return rows


def choose_candidate(dataset):
    """Select the smallest zero-empirical-FPR margin.

    Once the margin reaches the observed healthy maximum, every larger value
    has the same measured FPR (zero) but can only reduce TPR.  The smallest
    zero-FPR value is therefore the useful point on this empirical Pareto
    frontier.  It remains a characterization candidate, not a silicon
    guardband.
    """

    normal = dataset["normal"]
    zero_fpr_margins = [margin for margin in range(MARGIN_MAX + 1)
                        if not any(value > margin for value in normal)]
    # The first such margin is the least restrictive threshold that is quiet
    # on every observed healthy seed.  Higher margins cannot improve the
    # already-zero empirical FPR and would unnecessarily suppress alarms.
    candidate = min(zero_fpr_margins)
    by_voltage = {}
    for voltage, values in dataset["droop"].items():
        alarms = sum(value > candidate for value in values)
        by_voltage["{:.2f}".format(voltage)] = {
            "tpr": alarms / float(len(values)),
            "fnr": 1.0 - alarms / float(len(values)),
            "droop_alarm_count": alarms,
            "droop_count": len(values),
        }
    return {
        "margin": candidate,
        "criterion": "smallest integer margin with zero observed healthy FPR",
        "normal_max": max(normal),
        "normal_fpr": 0.0,
        "droop": by_voltage,
    }


def main():
    """Create M4 tables, figures, candidate margins, report, and gate summary."""

    datasets = build_datasets()
    sweep = margin_rows(datasets)
    with (STAGE_ROOT / "M4_MARGIN_SWEEP.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(sweep[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(sweep)

    candidates = {polarity: choose_candidate(dataset)
                  for polarity, dataset in datasets.items()}
    summary = {
        "stage": "B-FE6-MARG0-M4",
        "gate": "BFE6_MARG0_M4_MARGIN_SWEEP_COMPLETE",
        "condition": "0.95 V / 25 C fixed-condition process-population characterization",
        "margin_rule": "D_M > margin",
        "margin_range": [0, MARGIN_MAX],
        "datasets": {
            polarity: {
                "normal": stats(dataset["normal"]),
                "droop": {"{:.2f}".format(v): {
                    **stats(values),
                    "separation_gap": min(values) - max(dataset["normal"]),
                } for v, values in dataset["droop"].items()},
            } for polarity, dataset in datasets.items()
        },
        "candidates": candidates,
        "calibration_ablation": {
            "historical_absolute_M_rule_recoverable": False,
            "claim": "Only observed calibrated spread and D_M distributions are reported; no absolute-M comparator is invented.",
        },
        "overlap_policy": "Observed overlap is retained; candidates are not universal silicon settings.",
        "next_stage_authorized": True,
        "stop_after_stage": True,
    }
    (STAGE_ROOT / "M4_DISTRIBUTION_SUMMARY.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (STAGE_ROOT / "M4_CANDIDATE_MARGINS.json").write_text(
        json.dumps(candidates, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    # Publish the two names used by the plan as tiny, review-friendly text
    # artifacts in addition to the structured JSON.  They are candidates only;
    # no RTL parameter or product default is modified by this analysis.
    for polarity in ("RISE", "FALL"):
        (STAGE_ROOT / "M_MARGIN_{}_CANDIDATE.txt".format(polarity)).write_text(
            "{}\ncriterion: {}\ncondition: {}\n".format(
                candidates[polarity]["margin"],
                candidates[polarity]["criterion"],
                "0.95 V / 25 C fixed-condition process-population characterization",
            ),
            encoding="utf-8",
        )

    # Produce independent figures for RISE and FALL.  Keeping separate image
    # files mirrors the separate numerical populations and prevents accidental
    # visual pooling during the later RTL replay review.
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for polarity, dataset in datasets.items():
            figure, axis = plt.subplots(figsize=(7.2, 4.6), dpi=180)
            curves = [(dataset["normal"], "Healthy {} 0.95 V".format(polarity), "#2878B5")]
            colors = ("#C64E39", "#4E9F3D", "#8B5FBF")
            for color, voltage in zip(colors, VOLTAGES):
                curves.append((dataset["droop"][voltage], "{} droop {:.2f} V".format(polarity, voltage), color))
            for values, label, color in curves:
                ordered = sorted(values)
                axis.step(ordered, [(i + 1) / float(len(ordered)) for i in range(len(ordered))],
                          where="post", label=label, color=color, linewidth=1.6)
            axis.set_xlabel("D_M = abs(M_FF - M_REF_{})".format(polarity))
            axis.set_ylabel("Empirical CDF")
            axis.set_title("B-FE6-MARG0 M4 {} distributions".format(polarity))
            axis.grid(axis="both", alpha=0.25)
            axis.legend(loc="lower right")
            figure.tight_layout()
            figure.savefig(STAGE_ROOT / "M4_{}_CDF.png".format(polarity))
            figure.savefig(STAGE_ROOT / "M4_{}_CDF.pdf".format(polarity))
            plt.close(figure)
    except ImportError:
        summary["cdf_figures"] = False

    report = [
        "# B-FE6-MARG0 M4 margin selection",
        "",
        "Gate: `BFE6_MARG0_M4_MARGIN_SWEEP_COMPLETE`",
        "",
        "Condition: 0.95 V / 25 C fixed-condition process-population characterization.",
        "The exact strict rule is `D_M > margin`; RISE and FALL are swept independently.",
        "",
        "| Polarity | Candidate | Healthy max | 0.92 V TPR | 0.89 V TPR | 0.86 V TPR |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for polarity in ("RISE", "FALL"):
        item = candidates[polarity]
        tpr = [item["droop"]["{:.2f}".format(v)]["tpr"] for v in VOLTAGES]
        report.append("| {} | {} | {} | {:.3f} | {:.3f} | {:.3f} |".format(
            polarity, item["margin"], item["normal_max"], *tpr))
    report.extend([
        "",
        "The candidate criterion is the smallest integer margin with zero observed healthy FPR, preserving the highest TPR under the zero-FPR constraint.",
        "The 0.92 V FALL distribution overlaps healthy FALL by one code; this overlap is retained.",
        "The historical CALN0 absolute-M ablation rule is not recoverable from retained artifacts, so no ablation claim is made.",
        "Candidates are characterization values, not final silicon settings or PVT guardbands.",
        "",
    ])
    (STAGE_ROOT / "M4_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print("BFE6_MARG0_M4_MARGIN_SWEEP_COMPLETE")


if __name__ == "__main__":
    main()
