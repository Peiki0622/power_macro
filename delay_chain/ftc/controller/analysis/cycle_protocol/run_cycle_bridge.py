#!/usr/bin/env python3
"""Render, run, and audit the three frozen synchronous FTC bridge decks.

Only the 1 GHz cycle contracts produced by ``build_cycle_protocol.py`` are
accepted as input.  The script never changes an operation sequence after a
result is observed and never creates a fourth diagnostic scenario.
"""

import csv
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = FTC_ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import run_dynamic_startup_calibration_protocol as dynamic  # noqa: E402


PROTOCOL = FTC_ROOT / "controller" / "analysis" / "cycle_protocol"
RUN_ROOT = PROTOCOL / "hspice"
VOLTAGES = {"0p80": 0.80, "0p95": 0.95, "1p10": 1.10}


def write_json(path, value):
    """Write one structured audit record below the task-owned run root."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def finite(value):
    """Keep failed HSPICE measurements distinct from numerical zero."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def bridge_schedule(document):
    """Translate integer cycles to the existing physical deck renderer schema."""

    period = float(document["timing"]["period_s"])
    probes = []
    for probe in document["probes"]:
        item = dict(probe)
        item.update({
            "medium_code": item.pop("M"), "fine_code": item.pop("F"),
            "reset_release_s": item["reset_release_cycle"] * period,
            "launch_time_s": item["sclk_rise_cycle"] * period,
            "sclk_fall_s": item["sclk_fall_cycle"] * period,
            "q_read_time_s": item["sample_1_cycle"] * period,
            "q_read_late_time_s": item["sample_2_cycle"] * period,
            "reset_assert_start_s": item["reset_assert_cycle"] * period,
            "reset_assert_end_s": item["reset_assert_cycle"] * period + dynamic.CONTROL_EDGE_S,
            "recovery_end_s": item["recovery_done_cycle"] * period,
        })
        probes.append(item)
    transitions = []
    for transition in document["transitions"]:
        item = dict(transition)
        item.update({
            "old_M": item.pop("M_before"), "new_M": item.pop("M_after"),
            "old_F": item.pop("F_before"), "new_F": item.pop("F_after"),
            "transition_index": len(transitions),
            "update_time_s": item["update_cycle"] * period,
            "next_reset_release_s": item["settle_done_cycle"] * period,
            "next_launch_s": None,
        })
        transitions.append(item)
    for transition in transitions:
        next_probe = next((probe for probe in probes if probe["operation_index"] > transition["operation_index"]), None)
        transition["next_launch_s"] = next_probe["launch_time_s"] if next_probe else float(document["final_cycle"]) * period
    return {"probes": probes, "transitions": transitions, "final_time_s": float(document["final_cycle"]) * period, "expected_final": document["trajectory"]["final_locked_code"]}


def render_one(voltage):
    """Render one deck and add the second physical Q read required by Phase 1."""

    source = PROTOCOL / "cycle_path_{}_contract.json".format(voltage)
    document = json.loads(source.read_text(encoding="utf-8"))
    schedule = bridge_schedule(document)
    context = dynamic.frozen_context()
    deck = dynamic.render_deck(context, {"code_settle_guard_s": 2.0e-9}, schedule, VOLTAGES[voltage])
    extra = []
    for probe in schedule["probes"]:
        extra.append(".measure tran p{}_q_read_late_v FIND v(q_final,vss_a) AT={:.12e}".format(probe["probe_index"], probe["q_read_late_time_s"]))
    deck = deck.replace(".end\n", "\n".join(extra) + "\n.end\n")
    directory = RUN_ROOT / "cycle_path_{}".format(voltage)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "cycle_bridge.sp").write_text(deck, encoding="ascii")
    write_json(directory / "render_manifest.json", {"voltage": voltage, "cycle_contract": str(source), "cycle_contract_sha256": __import__("hashlib").sha256(source.read_bytes()).hexdigest(), "deck_sha256": __import__("hashlib").sha256(deck.encode("ascii")).hexdigest(), "simulator_invoked": False})
    return document, schedule, directory


def run_one(voltage):
    """Run exactly one freshly rendered contract deck and retain raw evidence."""

    document, schedule, directory = render_one(voltage)
    context = dynamic.frozen_context()
    hspice, version = dynamic.validate_hspice(context)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    result = subprocess.run([str(hspice), "cycle_bridge.sp", "-o", "cycle_bridge"], cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=900)
    (directory / "hspice_command.log").write_text("returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError("{} HSPICE failed with {}".format(voltage, result.returncode))
    record = dynamic.run_dc_sweep.parse_measurements(dynamic.run_dc_sweep.find_measurement_file(directory, "cycle_bridge"))
    rows = []
    errors = []
    vdd = VOLTAGES[voltage]
    for probe in schedule["probes"]:
        index = probe["probe_index"]
        first = finite(record.get("p{}_q_read_v".format(index)))
        second = finite(record.get("p{}_q_read_late_v".format(index)))
        observed = "STABLE_HIGH" if first is not None and second is not None and first >= .9 * vdd and second >= .9 * vdd else "STABLE_LOW" if first is not None and second is not None and first <= .1 * vdd and second <= .1 * vdd else "AMBIGUOUS"
        ck1 = finite(record.get("p{}_t_ck_rise".format(index)))
        ck2 = finite(record.get("p{}_t_ck_rise_2".format(index)))
        one_ck = ck1 is not None and (ck2 is None or ck2 >= probe["reset_assert_start_s"])
        recovery = [finite(record.get("p{}_recovery_{}_{}".format(index, node, suffix))) for node in ("xor", "medium", "ck") for suffix in ("end", "tail")]
        recovery_ok = all(value is not None and abs(value) <= .1 * vdd for value in recovery)
        passed = observed == probe["expected_q"] and one_ck and recovery_ok
        rows.append({"probe_index": index, "M": probe["medium_code"], "F": probe["fine_code"], "expected_q": probe["expected_q"], "observed_q": observed, "q_sample_1_v": first, "q_sample_2_v": second, "one_ck": one_ck, "recovery_ok": recovery_ok, "status": "PASS" if passed else "FAIL"})
        if not passed:
            errors.append("probe_{}_failure".format(index))
    with (directory / "probe_audit.csv").open("w", newline="", encoding="utf-8") as stream:
        # Use LF explicitly so committed evidence is byte-stable across hosts
        # and does not produce carriage-return-only Git whitespace changes.
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    decision = "Cycle-Quantized Startup Protocol = GO" if not errors else "Cycle-Quantized Startup Protocol = NO-GO"
    audit = {"schema_version": 1, "voltage": voltage, "decision": decision, "errors": errors, "final_locked_code": schedule["expected_final"], "probes": rows, "hspice_version": version}
    write_json(directory / "scenario_acceptance.json", audit)
    if errors:
        raise RuntimeError("{} cycle bridge failed".format(voltage))
    return audit


def main():
    """Freeze all rendered decks, then execute and summarize exactly three runs."""

    rendered = [render_one(voltage) for voltage in ("0p80", "0p95", "1p10")]
    write_json(RUN_ROOT / "pre_run_freeze.json", {"schema_version": 1, "scenario_budget": 3, "scenario_order": ["cycle_path_0p80", "cycle_path_0p95", "cycle_path_1p10"], "simulator_invoked": False})
    if not all(item[0]["checks"].values() for item in rendered):
        raise SystemExit("cycle schedule structural check failed before HSPICE")
    results = [run_one(voltage) for voltage in ("0p80", "0p95", "1p10")]
    write_json(RUN_ROOT / "summary.json", {"schema_version": 1, "decision": "Cycle-Quantized Startup Protocol = GO", "results": results, "scenario_count": 3})


if __name__ == "__main__":
    main()
