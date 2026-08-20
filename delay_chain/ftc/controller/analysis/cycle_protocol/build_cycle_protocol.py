#!/usr/bin/env python3
"""Generate the frozen 1 GHz operation schedules for the FTC controller.

The module emits data only.  It does not start a simulator and does not alter
the accepted physical evidence.  Its output is the sole timing input for the
Phase 1B open-loop decks and for the RTL operation sequencer tests.
"""

import hashlib
import json
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[3]
SPEC = FTC_ROOT / "controller" / "spec" / "ftc_calibration_controller_contract.json"
OUT = FTC_ROOT / "controller" / "analysis" / "cycle_protocol"
PERIOD_S = 1.0e-9


def write_json(path, value):
    """Write deterministically ordered JSON to the controller-owned area."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def add_operation(operations, name, before_m, after_m, before_f, after_f, expected=""):
    """Append one externally observable controller operation.

    The records mirror the accepted protocol: a probe never changes code, and
    a configuration update never contains a probe.  Keeping both before and
    after values makes single-bit transition audits independent of the RTL.
    """

    operations.append({
        "operation_index": len(operations),
        "operation_type": name,
        "M_before": before_m,
        "M_after": after_m,
        "F_before": before_f,
        "F_after": after_f,
        "expected_q": expected,
    })


def build_operations(item):
    """Construct the exact high-level protocol from one frozen trajectory."""

    boundary = item["coarse_boundary"]
    base = item["selected_medium_base"]
    fine_boundary = item["fine_boundary"]
    guard = item["guard_code"]
    operations = []
    for medium in range(boundary + 1):
        expected = "STABLE_LOW" if medium == boundary else "STABLE_HIGH"
        add_operation(operations, "COARSE_PROBE_A", medium, medium, 0, 0, expected)
        add_operation(operations, "COARSE_PROBE_B", medium, medium, 0, 0, expected)
        if medium != boundary:
            add_operation(operations, "MEDIUM_INCREMENT", medium, medium + 1, 0, 0)
    add_operation(operations, "MEDIUM_DECREMENT_BACKOFF_1", boundary, boundary - 1, 0, 0)
    add_operation(operations, "MEDIUM_DECREMENT_BACKOFF_2", boundary - 1, base, 0, 0)
    for fine in range(fine_boundary + 1):
        add_operation(operations, "FINE_PROBE", base, base, fine, fine, "STABLE_HIGH" if fine < fine_boundary else "STABLE_LOW")
        if fine != fine_boundary:
            add_operation(operations, "FINE_INCREMENT", base, base, fine, fine + 1)
    add_operation(operations, "FINE_INCREMENT_GUARD", base, base, fine_boundary, guard)
    add_operation(operations, "GUARD_PROBE", base, base, guard, guard, "STABLE_LOW")
    add_operation(operations, "HOLD_PROBE", base, base, guard, guard, "STABLE_LOW")
    return operations


def build_schedule(item):
    """Assign the one frozen conservative timing sequence to every operation.

    A configuration update changes one registered control at cycle zero and
    completes after two full cycles.  A probe releases reset at cycle zero,
    launches at cycle one, samples at cycles four and five, asserts reset at
    cycle five, and completes after three full reset-recovery cycles.
    """

    operations = build_operations(item)
    cursor = 0
    probes = []
    transitions = []
    for operation in operations:
        operation["start_cycle"] = cursor
        changed = (operation["M_before"], operation["F_before"]) != (operation["M_after"], operation["F_after"])
        if changed:
            operation["done_cycle"] = cursor + 2
            operation["kind"] = "CONFIG_UPDATE"
            transitions.append({
                "operation_index": operation["operation_index"],
                "operation_type": operation["operation_type"],
                "M_before": operation["M_before"], "M_after": operation["M_after"],
                "F_before": operation["F_before"], "F_after": operation["F_after"],
                "update_cycle": cursor, "settle_done_cycle": cursor + 2,
            })
            cursor += 2
        else:
            operation["done_cycle"] = cursor + 8
            operation["kind"] = "PROBE"
            probes.append({
                "probe_index": len(probes),
                "operation_index": operation["operation_index"],
                "operation_type": operation["operation_type"],
                "M": operation["M_before"], "F": operation["F_before"],
                "expected_q": operation["expected_q"],
                "reset_release_cycle": cursor,
                "sclk_rise_cycle": cursor + 1,
                "sclk_fall_cycle": cursor + 4,
                "sample_1_cycle": cursor + 4,
                "sample_2_cycle": cursor + 5,
                "reset_assert_cycle": cursor + 5,
                "recovery_done_cycle": cursor + 8,
            })
            cursor += 8
    backoffs = [op["operation_index"] for op in operations if op["operation_type"].startswith("MEDIUM_DECREMENT_BACKOFF")]
    checks = {
        "all_changes_are_config_updates": all((op["kind"] == "CONFIG_UPDATE") == ((op["M_before"], op["F_before"]) != (op["M_after"], op["F_after"])) for op in operations),
        "single_code_step_per_update": all(abs(row["M_after"] - row["M_before"]) + abs(row["F_after"] - row["F_before"]) == 1 for row in transitions),
        "probe_code_constant": all(row["M"] == operations[row["operation_index"]]["M_after"] and row["F"] == operations[row["operation_index"]]["F_after"] for row in probes),
        "two_adjacent_backoffs": len(backoffs) == 2 and backoffs[1] == backoffs[0] + 1,
        "one_sclk_rise_per_probe": all(row["sclk_rise_cycle"] < row["sclk_fall_cycle"] for row in probes),
        "two_samples_per_probe": all(row["sample_2_cycle"] == row["sample_1_cycle"] + 1 for row in probes),
    }
    return {"operations": operations, "probes": probes, "transitions": transitions, "final_cycle": cursor, "checks": checks}


def main():
    """Publish all three schedules before any Phase 1B simulator execution."""

    source = json.loads(SPEC.read_text(encoding="utf-8"))
    if source.get("decision") != "Controller Functional Contract = GO":
        raise SystemExit("phase 0 contract is not GO")
    timing = {
        "cal_clk_hz": 1_000_000_000,
        "period_s": PERIOD_S,
        "config_settle_cycles": 2,
        "reset_arm_cycles": 1,
        "sclk_high_cycles": 3,
        "launch_to_sample_1_cycles": 3,
        "sample_separation_cycles": 1,
        "recovery_cycles": 3,
    }
    rendered = []
    for voltage in ("0p80", "0p95", "1p10"):
        schedule = build_schedule(source["scenarios"][voltage])
        document = {"schema_version": 1, "voltage": voltage, "timing": timing, "trajectory": source["scenarios"][voltage], **schedule}
        if not all(schedule["checks"].values()):
            raise SystemExit("cycle protocol structural check failed: {}".format(voltage))
        path = OUT / "cycle_path_{}_contract.json".format(voltage)
        write_json(path, document)
        rendered.append({"voltage": voltage, "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write_json(OUT / "cycle_timing_contract.json", {"schema_version": 1, "decision": "Cycle Schedule Construction = GO", "timing": timing, "source_contract_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest()})
    write_json(OUT / "pre_run_freeze.json", {"schema_version": 1, "decision": "NOT_RUN", "scenario_budget": 3, "scenarios": rendered, "simulator_invoked": False})


if __name__ == "__main__":
    main()
