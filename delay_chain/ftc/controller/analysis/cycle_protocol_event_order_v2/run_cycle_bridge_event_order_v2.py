#!/usr/bin/env python3
"""Render, execute, and audit the frozen FTC event-order v2 bridge decks.

The v2 bridge consumes only contracts made by
``build_cycle_protocol_event_order_v2.py``.  It deliberately reuses the
accepted transistor-level deck renderer from the dynamic startup protocol; no
sensor, DFF, cell, M/F rail, or physical measurement topology is duplicated
or changed here.

The command modes map directly to the correction-plan gates:

* ``--render``: Phase 1R3 only.  Render and hash every deck before HSPICE.
* ``--execute``: Phase 1R4 only.  Read the frozen decks, run each once, and
  retain raw output below this task-owned ``hspice`` directory.
* ``--evaluate``: Phase 1R4 only.  Parse retained measurements and publish
  per-scenario plus aggregate acceptance evidence without starting HSPICE.

No mode adapts any timing after an electrical result.  In particular, execute
continues through all three pre-frozen scenarios even when an earlier scenario
is electrically NO-GO, because complete three-voltage evidence is required.
"""

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = FTC_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import run_dynamic_startup_calibration_protocol as dynamic  # noqa: E402


# All v2 outputs are intentionally confined to this one task-owned subtree.
PROTOCOL = Path(__file__).resolve().parent
RUN_ROOT = PROTOCOL / "hspice"
VOLTAGES = (("0p80", 0.80), ("0p95", 0.95), ("1p10", 1.10))
SCENARIO_NAMES = tuple("cycle_path_v2_{}".format(key) for key, _ in VOLTAGES)
V1_PROTOCOL = FTC_ROOT / "controller" / "analysis" / "cycle_protocol"


def read_json(path):
    """Read one object-shaped contract/evidence file with an explicit failure."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path, value):
    """Write deterministic task-owned JSON evidence with stable key ordering."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path, fields, rows):
    """Write LF-delimited tabular evidence without letting blanks become zeros."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def sha256_bytes(value):
    """Return SHA-256 for a deck text or already-read immutable byte sequence."""

    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    """Hash one file without rewriting or relocating immutable evidence."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_manifest(root):
    """Freeze a lightweight v1 content manifest to prove it was not modified.

    Only files are hashed; directory metadata is intentionally excluded because
    an unrelated read can update directory timestamps without altering evidence.
    """

    if not root.is_dir():
        raise ValueError("required historical v1 directory is missing: {}".format(root))
    return [
        {"path": str(path.relative_to(root)), "sha256": sha256_file(path)}
        for path in sorted(path for path in root.rglob("*") if path.is_file())
    ]


def finite(value):
    """Keep missing/failed HSPICE measures distinct from physical zero volts."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def classify_q(first, second, vdd):
    """Apply the frozen double-sample stable-rail classification contract."""

    if first is None or second is None:
        return "AMBIGUOUS"
    if first >= 0.9 * vdd and second >= 0.9 * vdd:
        return "STABLE_HIGH"
    if first <= 0.1 * vdd and second <= 0.1 * vdd:
        return "STABLE_LOW"
    return "AMBIGUOUS"


def contract_path(voltage):
    """Map a fixed voltage key to its only accepted v2 input contract."""

    return PROTOCOL / "cycle_path_v2_{}_contract.json".format(voltage)


def scenario_dir(voltage):
    """Keep one pre-rendered deck and its raw run evidence in one directory."""

    return RUN_ROOT / "cycle_path_v2_{}".format(voltage)


def bridge_schedule(document):
    """Translate frozen cycle events into the accepted physical renderer schema.

    The controller only schedules integer actions.  The shared physical
    renderer adds the existing 10 ps PWL reset edge, which is recorded in the
    v2 timing contract as a physical edge completion offset.  No synthetic
    digital delay primitive is introduced.
    """

    period = float(document["timing"]["period_s"])
    probes = []
    for probe in document["probes"]:
        item = dict(probe)
        item.update({
            "medium_code": item.pop("M"),
            "fine_code": item.pop("F"),
            "reset_release_s": item["reset_release_cycle"] * period,
            "launch_time_s": item["sclk_rise_cycle"] * period,
            "q_read_time_s": item["sample_1_cycle"] * period,
            "q_read_late_time_s": item["sample_2_cycle"] * period,
            "reset_assert_start_s": item["reset_assert_cycle"] * period,
            "reset_assert_end_s": item["reset_assert_cycle"] * period + dynamic.CONTROL_EDGE_S,
            "sclk_fall_s": item["sclk_fall_cycle"] * period,
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
    return {
        "probes": probes,
        "transitions": transitions,
        "final_time_s": float(document["final_cycle"]) * period,
        "expected_final": document["trajectory"]["final_locked_code"],
    }


def schedule_checks(document, schedule):
    """Validate every v2 structural prerequisite before a deck is rendered."""

    checks = dict(document.get("checks", {}))
    checks.update({
        "v2_contract_decision_go": document.get("decision") == "Event-Ordered Cycle Schedule Construction = GO",
        "reset_assert_physically_precedes_sclk_fall": all(
            probe["reset_assert_end_s"] < probe["sclk_fall_s"] for probe in schedule["probes"]
        ),
        "two_samples_rendered_per_probe": all(
            probe["q_read_time_s"] < probe["q_read_late_time_s"] for probe in schedule["probes"]
        ),
        "configuration_settle_precedes_dependent_release": all(
            transition["next_reset_release_s"] - transition["update_time_s"] >= 2.0e-9 - 1.0e-15
            for transition in schedule["transitions"]
        ),
    })
    return checks


def render_one(voltage, vdd):
    """Render a single deck from a frozen contract without invoking HSPICE."""

    source = contract_path(voltage)
    document = read_json(source)
    schedule = bridge_schedule(document)
    checks = schedule_checks(document, schedule)
    if not all(checks.values()):
        raise ValueError("{} v2 deck structural precondition failed".format(voltage))
    context = dynamic.frozen_context()
    deck = dynamic.render_deck(context, {"code_settle_guard_s": 2.0e-9}, schedule, vdd)
    # The established renderer owns the first read and all physical CK/recovery
    # measures.  Add only the Phase-1-required second Q read before ``.end``.
    late_reads = [
        ".measure tran p{}_q_read_late_v FIND v(q_final,vss_a) AT={:.12e}".format(
            probe["probe_index"], probe["q_read_late_time_s"]
        )
        for probe in schedule["probes"]
    ]
    deck = deck.replace(".end\n", "\n".join(late_reads) + "\n.end\n")
    directory = scenario_dir(voltage)
    directory.mkdir(parents=True, exist_ok=True)
    deck_path = directory / "cycle_bridge_v2.sp"
    deck_path.write_text(deck, encoding="ascii")
    manifest = {
        "schema_version": 2,
        "scenario": "cycle_path_v2_{}".format(voltage),
        "voltage": voltage,
        "cycle_contract": str(source.relative_to(FTC_ROOT)),
        "cycle_contract_sha256": sha256_file(source),
        "deck": str(deck_path.relative_to(FTC_ROOT)),
        "deck_sha256": sha256_bytes(deck.encode("ascii")),
        "structural_checks": checks,
        "simulator_invoked": False,
    }
    write_json(directory / "render_manifest.json", manifest)
    # This placeholder makes a pre-run result distinguishable from a missing
    # scenario directory while never claiming an electrical acceptance result.
    write_json(directory / "scenario_acceptance.json", {
        "schema_version": 2,
        "scenario": manifest["scenario"],
        "decision": "NOT_RUN",
        "simulator_invoked": False,
    })
    return manifest


def render_all():
    """Complete R3 atomically enough for review: all decks precede the freeze."""

    # A normal re-render after any run would invalidate the no-adaptation audit.
    if (RUN_ROOT / "summary.json").exists():
        raise RuntimeError("refusing to render after v2 execution evidence exists")
    v1_before = tree_manifest(V1_PROTOCOL)
    rendered = [render_one(voltage, vdd) for voltage, vdd in VOLTAGES]
    v1_after = tree_manifest(V1_PROTOCOL)
    if v1_before != v1_after:
        raise RuntimeError("historical v1 evidence changed during v2 rendering")
    freeze = {
        "schema_version": 2,
        "decision": "Event-Ordered HSPICE Deck Freeze = GO",
        "scenario_budget": 3,
        "scenario_order": list(SCENARIO_NAMES),
        "contracts_and_decks": rendered,
        "historical_v1_tree_before": v1_before,
        "historical_v1_tree_after": v1_after,
        "historical_v1_unchanged": True,
        "simulator_invoked": False,
    }
    write_json(RUN_ROOT / "pre_run_freeze.json", freeze)
    return freeze


def load_frozen_scenarios():
    """Verify the R3 freeze still exactly matches every on-disk v2 deck."""

    freeze = read_json(RUN_ROOT / "pre_run_freeze.json")
    if freeze.get("decision") != "Event-Ordered HSPICE Deck Freeze = GO":
        raise ValueError("R3 deck freeze is not GO")
    if freeze.get("scenario_budget") != 3 or tuple(freeze.get("scenario_order", ())) != SCENARIO_NAMES:
        raise ValueError("frozen v2 scenario budget/order is invalid")
    entries = freeze.get("contracts_and_decks", [])
    if len(entries) != 3:
        raise ValueError("deck freeze does not contain exactly three scenarios")
    entry_by_voltage = {item["voltage"]: item for item in entries}
    if set(entry_by_voltage) != {voltage for voltage, _ in VOLTAGES}:
        raise ValueError("deck freeze voltage set is invalid")
    for voltage, _ in VOLTAGES:
        entry = entry_by_voltage[voltage]
        source = contract_path(voltage)
        deck = scenario_dir(voltage) / "cycle_bridge_v2.sp"
        manifest = read_json(scenario_dir(voltage) / "render_manifest.json")
        if sha256_file(source) != entry["cycle_contract_sha256"]:
            raise ValueError("{} contract hash changed after freeze".format(voltage))
        if not deck.is_file() or sha256_file(deck) != entry["deck_sha256"]:
            raise ValueError("{} deck hash changed after freeze".format(voltage))
        if manifest.get("deck_sha256") != entry["deck_sha256"] or manifest.get("cycle_contract_sha256") != entry["cycle_contract_sha256"]:
            raise ValueError("{} render manifest differs from freeze".format(voltage))
    if tree_manifest(V1_PROTOCOL) != freeze.get("historical_v1_tree_after"):
        raise ValueError("historical v1 evidence changed after v2 deck freeze")
    return freeze


def invoke_one(voltage, vdd, retry_reason=""):
    """Run exactly one already-frozen deck, preserving logs and raw measures.

    A normal invocation refuses an existing run manifest.  An infrastructure
    retry is explicit, stored in a child directory, and allowed only after the
    frozen hashes have been independently revalidated by ``load_frozen_scenarios``.
    """

    directory = scenario_dir(voltage)
    existing = directory / "run_manifest.json"
    if existing.exists() and not retry_reason:
        raise RuntimeError("{} already has a run manifest; refusing a second normal run".format(voltage))
    workdir = directory
    if retry_reason:
        previous = read_json(existing)
        if previous.get("returncode") == 0:
            raise RuntimeError("{} completed normally and is not retryable infrastructure evidence".format(voltage))
        workdir = directory / "infrastructure_retry"
        if workdir.exists():
            raise RuntimeError("{} already has an infrastructure retry".format(voltage))
        workdir.mkdir()
        write_json(directory / "infrastructure_retry_reason.json", {
            "schema_version": 2,
            "reason": retry_reason,
            "original_returncode": previous.get("returncode"),
            "contract_and_deck_hashes_revalidated": True,
        })
    context = dynamic.frozen_context()
    hspice, version = dynamic.validate_hspice(context)
    deck_source = directory / "cycle_bridge_v2.sp"
    deck_path = workdir / "cycle_bridge_v2.sp"
    if workdir != directory:
        shutil.copyfile(deck_source, deck_path)
    # The LVT CDL references this collateral by a relative name; retaining it
    # beside each scenario is required by the established physical flow.
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", workdir / "empty_subckt.sp_cal")
    command = [str(hspice), deck_path.name, "-o", "cycle_bridge_v2"]
    result = subprocess.run(
        command,
        cwd=workdir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        timeout=900,
    )
    (workdir / "hspice_command.log").write_text(
        "returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 2,
        "scenario": "cycle_path_v2_{}".format(voltage),
        "hspice": str(hspice),
        "hspice_version": version,
        "command": command,
        "returncode": result.returncode,
        "deck_sha256": sha256_file(deck_source),
        "cycle_contract_sha256": sha256_file(contract_path(voltage)),
        "retry": bool(retry_reason),
    }
    write_json(workdir / "run_manifest.json", manifest)
    if workdir == directory:
        write_json(existing, manifest)
    return {"voltage": voltage, "vdd": vdd, "returncode": result.returncode, "workdir": workdir, "manifest": manifest}


def execute_all(retry_voltage="", retry_reason=""):
    """Run all pre-frozen scenarios once without early stopping on NO-GO."""

    load_frozen_scenarios()
    if retry_voltage and not retry_reason:
        raise ValueError("an infrastructure retry requires a recorded reason")
    results = []
    for voltage, vdd in VOLTAGES:
        if retry_voltage and voltage != retry_voltage:
            continue
        results.append(invoke_one(voltage, vdd, retry_reason if voltage == retry_voltage else ""))
    return results


def measurement_workdir(voltage):
    """Select the retained retry output only when one was explicitly created."""

    retry = scenario_dir(voltage) / "infrastructure_retry"
    return retry if retry.is_dir() else scenario_dir(voltage)


def evaluate_one(voltage, vdd):
    """Apply the complete R4 probe and configuration acceptance rules."""

    directory = scenario_dir(voltage)
    workdir = measurement_workdir(voltage)
    run = read_json(workdir / "run_manifest.json")
    document = read_json(contract_path(voltage))
    schedule = bridge_schedule(document)
    errors = []
    rows = []
    transition_rows = []
    if run.get("returncode") != 0:
        errors.append("hspice_infrastructure_failure")
    else:
        dynamic.run_dc_sweep.validate_listing(workdir / "cycle_bridge_v2.lis")
        record = dynamic.run_dc_sweep.parse_measurements(dynamic.run_dc_sweep.find_measurement_file(workdir, "cycle_bridge_v2"))
        for probe in schedule["probes"]:
            index = probe["probe_index"]
            first = finite(record.get("p{}_q_read_v".format(index)))
            second = finite(record.get("p{}_q_read_late_v".format(index)))
            observed = classify_q(first, second, vdd)
            ck_first = finite(record.get("p{}_t_ck_rise".format(index)))
            ck_second = finite(record.get("p{}_t_ck_rise_2".format(index)))
            # This is deliberately physical: measured CK times are compared to
            # the generated physical reset assertion time.  The controller
            # event list alone cannot establish CK-edge integrity.
            physical_active_ck_ok = (
                ck_first is not None
                and probe["launch_time_s"] <= ck_first < probe["reset_assert_start_s"]
                and (ck_second is None or ck_second >= probe["reset_assert_start_s"])
            )
            recovery = [
                finite(record.get("p{}_recovery_{}_{}".format(index, node, suffix)))
                for node in ("xor", "medium", "ck")
                for suffix in ("end", "tail")
            ]
            recovery_ok = all(value is not None and abs(value) <= 0.1 * vdd for value in recovery)
            reset_before_fall = probe["reset_assert_end_s"] < probe["sclk_fall_s"]
            code_constant = document["operations"][probe["operation_index"]]["M_before"] == probe["medium_code"] and document["operations"][probe["operation_index"]]["F_before"] == probe["fine_code"]
            passed = (
                observed == probe["expected_q"]
                and physical_active_ck_ok
                and recovery_ok
                and reset_before_fall
                and code_constant
            )
            if not passed:
                errors.append("probe_{}_failure".format(index))
            rows.append({
                "probe_index": index,
                "M": probe["medium_code"], "F": probe["fine_code"],
                "expected_q": probe["expected_q"], "observed_q": observed,
                "q_sample_1_v": first, "q_sample_2_v": second,
                "measured_first_ck_rise_s": ck_first, "measured_second_ck_rise_s": ck_second,
                "physical_active_ck_ok": physical_active_ck_ok,
                "reset_assert_end_s": probe["reset_assert_end_s"], "sclk_fall_s": probe["sclk_fall_s"],
                "reset_assert_physically_precedes_sclk_fall": reset_before_fall,
                "recovery_ok": recovery_ok, "mf_constant_during_probe": code_constant,
                "status": "PASS" if passed else "FAIL",
            })
        for transition in schedule["transitions"]:
            index = transition["transition_index"]
            edges = [finite(record.get("tr{}_ck_rise_{}".format(index, ordinal))) for ordinal in (1, 2)]
            quiet_edges = sum(edge is not None and edge < transition["next_reset_release_s"] for edge in edges)
            peaks = [finite(record.get("tr{}_{}_max".format(index, node))) for node in ("xor", "medium", "ck")]
            one_thermometer_step = abs(transition["new_M"] - transition["old_M"]) + abs(transition["new_F"] - transition["old_F"]) == 1
            settle_ok = transition["next_reset_release_s"] - transition["update_time_s"] >= 2.0e-9 - 1.0e-15
            quiet_ok = quiet_edges == 0 and all(value is not None and abs(value) <= 0.1 * vdd for value in peaks)
            passed = one_thermometer_step and settle_ok and quiet_ok
            if not passed:
                errors.append("config_update_{}_failure".format(index))
            transition_rows.append({
                "transition_index": index, "operation_index": transition["operation_index"],
                "M_before": transition["old_M"], "M_after": transition["new_M"],
                "F_before": transition["old_F"], "F_after": transition["new_F"],
                "reset_asserted": True, "sclk_low": True,
                "one_thermometer_step": one_thermometer_step,
                "settle_two_cycles_ok": settle_ok,
                "configuration_ck_edge_count": quiet_edges,
                "quiet_window_ok": quiet_ok,
                "status": "PASS" if passed else "FAIL",
            })
    decision = "Cycle-Quantized Startup Protocol = GO" if not errors else "Cycle-Quantized Startup Protocol = NO-GO"
    audit = {
        "schema_version": 2,
        "scenario": "cycle_path_v2_{}".format(voltage),
        "voltage": voltage,
        "decision": decision,
        "errors": list(dict.fromkeys(errors)),
        "final_locked_code": schedule["expected_final"],
        "probe_count": len(schedule["probes"]),
        "config_update_count": len(schedule["transitions"]),
        "probes": rows,
        "config_updates": transition_rows,
        "hspice_version": run.get("hspice_version"),
        "deck_sha256": run.get("deck_sha256"),
        "cycle_contract_sha256": run.get("cycle_contract_sha256"),
    }
    write_csv(directory / "probe_audit.csv", tuple(rows[0]) if rows else ("probe_index", "status"), rows)
    write_csv(directory / "config_update_audit.csv", tuple(transition_rows[0]) if transition_rows else ("transition_index", "status"), transition_rows)
    write_json(directory / "scenario_acceptance.json", audit)
    return audit


def evaluate_all():
    """Read all three retained results and publish the aggregate R4 decision."""

    load_frozen_scenarios()
    results = [evaluate_one(voltage, vdd) for voltage, vdd in VOLTAGES]
    decision = "Cycle-Quantized Startup Protocol = GO" if all(item["decision"].endswith("= GO") for item in results) else "Cycle-Quantized Startup Protocol = NO-GO"
    first_failure = next(({
        "scenario": item["scenario"], "reason": item["errors"][0] if item["errors"] else "unknown"
    } for item in results if item["errors"]), None)
    summary = {
        "schema_version": 2,
        "decision": decision,
        "scenario_budget": 3,
        "scenario_order": list(SCENARIO_NAMES),
        "scenario_count": len(results),
        "results": [{
            "scenario": item["scenario"], "decision": item["decision"], "errors": item["errors"],
            "final_locked_code": item["final_locked_code"], "probe_count": item["probe_count"],
            "config_update_count": item["config_update_count"], "deck_sha256": item["deck_sha256"],
            "cycle_contract_sha256": item["cycle_contract_sha256"],
        } for item in results],
        "first_real_failure": first_failure,
        "timing_template_changed_after_execution": False,
    }
    write_json(RUN_ROOT / "summary.json", summary)
    return summary


def parse_args(argv=None):
    """Keep stage actions explicit so rendering and simulation cannot mix."""

    parser = argparse.ArgumentParser(description="run FTC event-order v2 HSPICE bridge")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--render", action="store_true", help="render/freeze all three v2 decks without HSPICE")
    actions.add_argument("--execute", action="store_true", help="execute frozen v2 decks once; no evaluation")
    actions.add_argument("--evaluate", action="store_true", help="evaluate retained HSPICE results without execution")
    parser.add_argument("--infrastructure-retry", choices=[key for key, _ in VOLTAGES], default="", help="retry one retained nonzero-return scenario")
    parser.add_argument("--retry-reason", default="", help="required provenance text for an infrastructure retry")
    return parser.parse_args(argv)


def main(argv=None):
    """Dispatch one stage and return a nonzero status for a failed gate."""

    args = parse_args(argv)
    try:
        if args.render:
            render_all()
            return 0
        if args.execute:
            execute_all(args.infrastructure_retry, args.retry_reason)
            return 0
        summary = evaluate_all()
        return 0 if summary["decision"] == "Cycle-Quantized Startup Protocol = GO" else 2
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        print("event-order v2 bridge failed: {}".format(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
