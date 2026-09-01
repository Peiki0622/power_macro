#!/usr/bin/env python3
"""Independently validate the completed BFE12 P4 controller replay."""

import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
TASK_ROOT = HERE.parent


def rows(path):
    with path.open(newline="", encoding="ascii") as stream:
        return list(csv.DictReader(stream))


def key(dataset, seed, polarity, m_ff, m_ref, margin):
    return (dataset, seed, polarity, m_ff, m_ref, margin)


def main():
    manifest = rows(TASK_ROOT / "P3_REPLAY_MANIFEST.csv")
    replay = rows(HERE / "P4_EVENT_RESULTS.csv")
    # Build queues because healthy FPR contains repeated identical rows.
    expected = defaultdict(list)
    dataset_code = {"healthy_fpr": 1, "healthy_signed_rise": 2,
                    "d01_target": 3, "d02_target": 4, "d04_target": 5}
    for row in manifest:
        code = dataset_code[row["dataset"]]
        p = 0 if row["polarity"] == "RISE" else 1
        expected[key(code, int(row["seed"]), p, int(row["m_ff"]),
                    int(row["m_ref"]), int(row["arch0_margin"]))].append(row)

    equivalence_mismatches = []
    fall_mismatches = []
    result_rows = []
    coverage = defaultdict(lambda: {"arch0": 0, "sign0_18": 0, "sign0_19": 0, "total": 0})
    healthy_fpr = {"arch0": 0, "sign0_18": 0, "sign0_19": 0, "total": 0}
    signed_healthy = {"sign0_18": 0, "sign0_19": 0, "total": 0}
    recovered = {"d01": {"arch0": [], "sign0_18": [], "sign0_19": []},
                 "d04": {"arch0": [], "sign0_18": [], "sign0_19": []}}

    for raw in replay:
        code = int(raw["dataset_code"])
        if code == 0:
            if any(int(raw[name]) for name in ("arch0", "sign0_off", "sign0_18", "sign0_19")):
                raise AssertionError("calibration event produced an alarm")
            continue
        lookup = key(code, int(raw["seed"]), int(raw["polarity"]), int(raw["m_ff"]),
                     int(raw["m_ref"]), int(raw["margin"]))
        if not expected[lookup]:
            raise AssertionError("unmatched replay row: {}".format(lookup))
        source = expected[lookup].pop(0)
        a = int(raw["arch0"])
        b = int(raw["sign0_off"])
        c = int(raw["sign0_18"])
        d = int(raw["sign0_19"])
        source_a = int(source["expected_arch0_alarm"])
        # The replay output is the combined ABS OR signed alarm.  The manifest
        # also stores signed-branch-only expectations, but those must not be
        # used as the total C/D alarm expectation for FALL ABS hits.
        source_c = int(int(source["abs_e"]) > int(source["arch0_margin"]) or
                       (source["polarity"] == "RISE" and int(source["signed_e"]) > 18))
        source_d = int(int(source["abs_e"]) > int(source["arch0_margin"]) or
                       (source["polarity"] == "RISE" and int(source["signed_e"]) > 19))
        if a != source_a or b != a:
            equivalence_mismatches.append((code, raw["seed"], a, b, source_a))
        if int(raw["polarity"]) == 1 and (c != a or d != a):
            fall_mismatches.append((code, raw["seed"], a, c, d))
        if c != source_c or d != source_d:
            equivalence_mismatches.append((code, raw["seed"], c, d, source_c, source_d))
        result_rows.append(raw)
        if code == 1:
            healthy_fpr["total"] += 1
            healthy_fpr["arch0"] += a
            healthy_fpr["sign0_18"] += c
            healthy_fpr["sign0_19"] += d
        elif code == 2:
            signed_healthy["total"] += 1
            signed_healthy["sign0_18"] += int(raw["signed_term_18"])
            signed_healthy["sign0_19"] += int(raw["signed_term_19"])
        else:
            name = {3: "d01", 4: "d02", 5: "d04"}[code]
            coverage[name]["total"] += 1
            coverage[name]["arch0"] += a
            coverage[name]["sign0_18"] += c
            coverage[name]["sign0_19"] += d
            if name in recovered and not a:
                if c: recovered[name]["sign0_18"].append(int(raw["seed"]))
                if d: recovered[name]["sign0_19"].append(int(raw["seed"]))

    if any(expected.values()):
        raise AssertionError("manifest events missing from replay")
    expected_recovered_d01 = [41005, 41007, 41012, 41015, 41016, 41022, 41025, 41028]
    expected_recovered_d04 = [41007, 41012, 41015, 41016, 41022, 41025]
    if equivalence_mismatches or fall_mismatches:
        raise AssertionError("A/B or FALL equivalence mismatch")
    if healthy_fpr != {"arch0": 1, "sign0_18": 1, "sign0_19": 1, "total": 240}:
        raise AssertionError("healthy FPR mismatch: {}".format(healthy_fpr))
    if signed_healthy != {"sign0_18": 0, "sign0_19": 0, "total": 360}:
        raise AssertionError("healthy signed audit mismatch: {}".format(signed_healthy))
    if coverage != {
        "d01": {"arch0": 22, "sign0_18": 30, "sign0_19": 30, "total": 30},
        "d02": {"arch0": 30, "sign0_18": 30, "sign0_19": 30, "total": 30},
        "d04": {"arch0": 24, "sign0_18": 30, "sign0_19": 30, "total": 30},
    }:
        raise AssertionError("attack coverage mismatch: {}".format(dict(coverage)))
    if recovered["d01"]["sign0_18"] != expected_recovered_d01 or recovered["d01"]["sign0_19"] != expected_recovered_d01:
        raise AssertionError("D01 recovered seed mismatch")
    if recovered["d04"]["sign0_18"] != expected_recovered_d04 or recovered["d04"]["sign0_19"] != expected_recovered_d04:
        raise AssertionError("D04 recovered seed mismatch")

    shutil.copyfile(HERE / "P4_EVENT_RESULTS.csv", TASK_ROOT / "P4_EVENT_RESULTS.csv")
    summary = {
        "gate": "BFE12_SIGN0_P4_RETAINED_AB_RTL_CHARACTERIZED",
        "status": "PASS",
        "classification": "RTL_REPRODUCES_FROZEN_SHADOW",
        "event_rows_checked": len(result_rows),
        "healthy_fpr": healthy_fpr,
        "healthy_signed_rise": signed_healthy,
        "coverage": dict(coverage),
        "recovered_seed_lists": recovered,
        "fall_equivalence_checked": True,
        "physical_simulation_calls": 0,
    }
    (TASK_ROOT / "P4_COVERAGE_SUMMARY.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    (TASK_ROOT / "P4_EQUIVALENCE_SUMMARY.json").write_text(json.dumps({
        "gate": "BFE12_SIGN0_P4_RETAINED_AB_RTL_CHARACTERIZED",
        "status": "PASS",
        "classification": "RTL_REPRODUCES_FROZEN_SHADOW",
        "dut_b_event_equivalent_to_arch0": True,
        "dut_c_d_fall_event_equivalent_to_arch0": True,
        "event_context_alignment_checked": True,
        "mismatches": 0,
    }, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print("BFE12_SIGN0_P4_RETAINED_AB_RTL_CHARACTERIZED")


if __name__ == "__main__":
    main()
