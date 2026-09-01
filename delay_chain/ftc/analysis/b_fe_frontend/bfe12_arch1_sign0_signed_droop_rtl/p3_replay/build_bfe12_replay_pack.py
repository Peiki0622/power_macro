#!/usr/bin/env python3
"""Build the BFE12 retained-data replay pack without running a simulator.

The script intentionally performs only deterministic CSV/JSON parsing and
integer rule evaluation.  It never imports or invokes VCS, HSPICE, PrimeSim,
DC, or any physical model.  The resulting manifest is the sole input contract
for the later controller-level A/B replay.
"""

import csv
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
TASK_ROOT = HERE.parent
FTC_ROOT = TASK_ROOT.parents[2]
ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend"
BFE8_ROOT = ANALYSIS_ROOT / "bfe8_d02_arch0_pilot"
BFE9_ROOT = ANALYSIS_ROOT / "bfe9_d01_arch0_amplitude_sensitivity"
BFE11_ROOT = ANALYSIS_ROOT / "bfe11_d04_arch0_duration_sensitivity"
SIGNED_ROOT = ANALYSIS_ROOT / "arch1_signed_error_separability_audit"


def sha256(path):
    """Return the content hash recorded beside every manifest source."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    """Read an ASCII retained CSV while preserving its original field names."""
    with path.open(newline="", encoding="ascii") as stream:
        return list(csv.DictReader(stream))


def int_value(row, *names):
    """Read the first available integer field from a retained row."""
    for name in names:
        if name in row and row[name] != "":
            return int(float(row[name]))
    raise KeyError("missing integer field: {}".format(names))


def calibration_payload():
    """Reconstruct both four-sample calibration epochs for all 30 seeds."""
    rows = read_csv(BFE8_ROOT / "BFE8_HEALTHY_PER_SEED.csv")
    if {int(row["seed"]) for row in rows} != set(range(41001, 41031)):
        raise AssertionError("BFE8 calibration seed set is not 41001..41030")
    result = []
    for row in sorted(rows, key=lambda item: int(item["seed"])):
        rise = [int(item) for item in row["M_CAL_RISE"].split(";")]
        fall = [int(item) for item in row["M_CAL_FALL"].split(";")]
        if len(rise) != 4 or len(fall) != 4:
            raise AssertionError("calibration epoch does not contain four samples")
        rise_ref = int(row["M_REF_RISE"])
        fall_ref = int(row["M_REF_FALL"])
        if (sum(rise) >> 2) != rise_ref or (sum(fall) >> 2) != fall_ref:
            raise AssertionError("sum4 >> 2 mismatch for seed {}".format(row["seed"]))
        result.append({
            "seed": int(row["seed"]),
            "rise_samples": rise,
            "fall_samples": fall,
            "m_ref_rise": rise_ref,
            "m_ref_fall": fall_ref,
        })
    return result


def event(dataset, seed, polarity, m_ff, m_ref, margin, arch0, source):
    """Construct one event and recompute both frozen signed candidates."""
    signed_e = m_ff - m_ref
    return {
        "dataset": dataset,
        "seed": seed,
        "polarity": polarity,
        "m_ff": m_ff,
        "m_ref": m_ref,
        "arch0_margin": margin,
        "signed_e": signed_e,
        "abs_e": abs(signed_e),
        "expected_arch0_alarm": int(bool(arch0)),
        "expected_sign0_t18_alarm": int(polarity == "RISE" and signed_e > 18),
        "expected_sign0_t19_alarm": int(polarity == "RISE" and signed_e > 19),
        "source_artifact": str(source),
        "source_sha256": sha256(source),
    }


def build_events():
    """Build the five required retained event sets in deterministic order."""
    events = []

    fpr_path = BFE8_ROOT / "BFE8_D02_HEALTHY_FPR.csv"
    for row in read_csv(fpr_path):
        events.append(event("healthy_fpr", int(row["seed"]), row["polarity"],
                            int(row["M_FF"]), int(row["M_REF"]), int(row["margin"]),
                            int(row["healthy_alarm"]), fpr_path))

    signed_path = SIGNED_ROOT / "ARCH1_SIGNED_ERROR_PER_SAMPLE.csv"
    for row in read_csv(signed_path):
        if row["dataset"] != "healthy_rise":
            continue
        events.append(event("healthy_signed_rise", int(row["seed"]), "RISE",
                            int(row["M_FF"]), int(row["M_REF_RISE"]), 22,
                            int(row["existing_abs_margin_alarm"]), signed_path))

    d01_path = BFE9_ROOT / "BFE9_D01_PER_SEED.csv"
    for row in read_csv(d01_path):
        events.append(event("d01_target", int(row["seed"]), "RISE",
                            int(row["M_FF_target"]), int(row["M_REF_RISE"]),
                            int(row["locked_rise_margin"]), int(row["D01_detected"]), d01_path))

    d02_path = BFE8_ROOT / "BFE8_D02_PER_SEED.csv"
    for row in read_csv(d02_path):
        events.append(event("d02_target", int(row["seed"]), "RISE",
                            int(row["M_FF_target"]), int(row["M_REF_RISE"]),
                            int(row["locked_rise_margin"]), int(row["detected"]), d02_path))

    d04_path = BFE11_ROOT / "BFE11_D04_PER_SEED.csv"
    for row in read_csv(d04_path):
        events.append(event("d04_target", int(row["seed"]), "RISE",
                            int(row["M_FF_target"]), int(row["M_REF_RISE"]),
                            int(row["locked_rise_margin"]), int(row["D04_detected"]), d04_path))
    return events


def main():
    """Validate frozen facts, then emit CSV and JSON replay contracts."""
    calibrations = calibration_payload()
    events = build_events()
    expected_counts = {
        "healthy_fpr": 240,
        "healthy_signed_rise": 360,
        "d01_target": 30,
        "d02_target": 30,
        "d04_target": 30,
    }
    counts = {name: sum(item["dataset"] == name for item in events)
              for name in expected_counts}
    if counts != expected_counts:
        raise AssertionError("retained event counts mismatch: {}".format(counts))

    healthy_fpr = [item for item in events if item["dataset"] == "healthy_fpr"]
    healthy_signed = [item for item in events if item["dataset"] == "healthy_signed_rise"]
    d01 = [item for item in events if item["dataset"] == "d01_target"]
    d02 = [item for item in events if item["dataset"] == "d02_target"]
    d04 = [item for item in events if item["dataset"] == "d04_target"]
    if sum(item["expected_arch0_alarm"] for item in healthy_fpr) != 1:
        raise AssertionError("healthy FPR is not 1/240")
    if max(item["signed_e"] for item in healthy_signed) != 18:
        raise AssertionError("healthy signed-e maximum is not +18")
    if sum(item["expected_arch0_alarm"] for item in d01) != 22:
        raise AssertionError("D01 ARCH0 coverage is not 22/30")
    if sum(item["expected_sign0_t18_alarm"] for item in d01) != 30 or sum(item["expected_sign0_t19_alarm"] for item in d01) != 30:
        raise AssertionError("D01 signed candidate coverage mismatch")
    if sum(item["expected_arch0_alarm"] for item in d02) != 30:
        raise AssertionError("D02 ARCH0 coverage is not 30/30")
    if sum(item["expected_arch0_alarm"] for item in d04) != 24:
        raise AssertionError("D04 ARCH0 coverage is not 24/30")
    if sum(item["expected_sign0_t18_alarm"] for item in d04) != 30 or sum(item["expected_sign0_t19_alarm"] for item in d04) != 30:
        raise AssertionError("D04 signed candidate coverage mismatch")

    d01_recovered = sorted(item["seed"] for item in d01
                           if not item["expected_arch0_alarm"] and item["expected_sign0_t18_alarm"])
    d04_recovered = sorted(item["seed"] for item in d04
                           if not item["expected_arch0_alarm"] and item["expected_sign0_t18_alarm"])
    if d01_recovered != [41005, 41007, 41012, 41015, 41016, 41022, 41025, 41028]:
        raise AssertionError("D01 recovered seed list mismatch")
    if d04_recovered != [41007, 41012, 41015, 41016, 41022, 41025]:
        raise AssertionError("D04 recovered seed list mismatch")

    fieldnames = ["dataset", "seed", "polarity", "m_ff", "m_ref", "arch0_margin",
                  "signed_e", "abs_e", "expected_arch0_alarm",
                  "expected_sign0_t18_alarm", "expected_sign0_t19_alarm",
                  "source_artifact", "source_sha256"]
    csv_path = TASK_ROOT / "P3_REPLAY_MANIFEST.csv"
    with csv_path.open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(events)

    summary = {
        "gate": "BFE12_SIGN0_P3_RETAINED_REPLAY_PACK_FROZEN",
        "status": "PASS",
        "calibration": calibrations,
        "event_counts": counts,
        "healthy_fpr": {"alarms": 1, "events": 240, "fraction": 1.0 / 240.0},
        "healthy_signed_rise_max": 18,
        "coverage": {
            "d01_arch0": "22/30", "d01_sign0_t18": "30/30", "d01_sign0_t19": "30/30",
            "d02_arch0": "30/30", "d04_arch0": "24/30",
            "d04_sign0_t18": "30/30", "d04_sign0_t19": "30/30",
        },
        "recovered_seed_lists": {"d01": d01_recovered, "d04": d04_recovered},
        "manifest_csv": str(csv_path),
        "physical_simulation_calls": 0,
    }
    (TASK_ROOT / "P3_REPLAY_MANIFEST.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print("BFE12_SIGN0_P3_RETAINED_REPLAY_PACK_FROZEN")


if __name__ == "__main__":
    main()
