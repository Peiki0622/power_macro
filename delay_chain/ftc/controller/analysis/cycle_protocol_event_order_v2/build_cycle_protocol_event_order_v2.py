#!/usr/bin/env python3
"""Build the FTC Phase-1 v2 timing contracts from accepted event evidence.

This program intentionally owns only the corrected v2 evidence directory.  It
never writes into the rejected v1 ``cycle_protocol`` directory and it never
starts HSPICE.  The two supported stages are deliberately small:

* ``--audit-only`` performs Phase 1R0 and freezes the source event ordering.
* the default mode reruns that audit, then performs Phase 1R1 only when the
  audit is GO and writes the three v2 cycle contracts.

The physical deck renderer uses a 10 ps analogue reset edge.  That edge is an
offset inside a controller cycle, not a new controller clock interval.  The
solver below therefore has integer variables only for controller actions and
derives reset-complete time from the reset-assert action plus the frozen edge
duration.  This is what yields the earliest legal 0/1/4/5/6/7/10 template.
"""

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path


# Keep every source path explicit.  The accepted exact-path artefacts are
# immutable evidence; this file only reads and hashes them.
FTC_ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
EXACT_ROOT = FTC_ROOT / "analysis" / "reachable_path_acceptance" / "exact_hspice"
PHASE0_CONTRACT = FTC_ROOT / "controller" / "spec" / "ftc_calibration_controller_contract.json"
V1_SUMMARY = FTC_ROOT / "controller" / "analysis" / "cycle_protocol" / "hspice" / "summary.json"
V1_REPORT = FTC_ROOT / "controller" / "reports" / "FTC_CYCLE_QUANTIZATION_NO_GO.md"
EXACT_RUNNER = FTC_ROOT / "scripts" / "run_exact_reachable_path_hspice.py"

VOLTAGES = ("0p80", "0p95", "1p10")
PERIOD_S = 1.0e-9
SCENARIO_BUDGET = 3

# The ordered names are the public vocabulary for v2 contracts and tests.
# ``operation_schedule.json`` stores the complete Q-sample record in
# ``operations``; its compact ``probes`` list intentionally omits the late
# sample field, so the audit must use the operation records below.
EVENT_FIELDS = (
    ("RESET_RELEASE_COMPLETE", "reset_release_s"),
    ("S_CLK_RISE", "launch_time_s"),
    ("Q_SAMPLE_1", "q_read_time_s"),
    ("Q_SAMPLE_2", "q_read_late_time_s"),
    ("RESET_ASSERT_START", "reset_assert_start_s"),
    ("RESET_ASSERT_COMPLETE", "reset_assert_end_s"),
    ("S_CLK_FALL", "sclk_fall_s"),
    ("RECOVERY_DONE", "recovery_end_s"),
)
EVENT_NAMES = tuple(name for name, _ in EVENT_FIELDS)


def read_json(path):
    """Read one required JSON object and reject malformed evidence early."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def sha256_file(path):
    """Hash a file without copying immutable source evidence."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    """Write deterministic machine-readable evidence in the v2 directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path, fields, rows):
    """Write stable LF-delimited CSV so hashes do not vary by host platform."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def source_paths():
    """Return all R0 inputs, including v1 failure evidence for provenance."""

    result = {
        "exact_final_acceptance": EXACT_ROOT / "final_acceptance.json",
        "exact_path_runner": EXACT_RUNNER,
        "phase0_controller_contract": PHASE0_CONTRACT,
        "rejected_v1_summary": V1_SUMMARY,
        "rejected_v1_report": V1_REPORT,
    }
    for voltage in VOLTAGES:
        result["exact_schedule_{}".format(voltage)] = EXACT_ROOT / "exact_path_{}".format(voltage) / "operation_schedule.json"
    return result


def require_sources():
    """Confirm every immutable input exists before computing any audit value."""

    paths = source_paths()
    missing = [str(path) for path in paths.values() if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise ValueError("required Phase-1 evidence is missing: {}".format(", ".join(missing)))
    return paths


def operation_probes(schedule):
    """Return only exact-path operations that carry a complete probe timeline."""

    rows = []
    for row in schedule.get("operations", []):
        # Initial/configuration rows use an empty probe index and do not carry
        # the eight event timestamps.  A numeric index identifies a real probe.
        if isinstance(row.get("probe_index"), int):
            if any(field not in row for _, field in EVENT_FIELDS):
                raise ValueError("probe {} is missing an ordered event".format(row.get("probe_index")))
            rows.append(row)
    if not rows:
        raise ValueError("exact-path schedule contains no complete probe operations")
    return rows


def adjacent_key(left, right):
    """Use one readable, stable key for adjacent event-pair measurements."""

    return "{}__to__{}".format(left, right)


def audit_exact_paths():
    """Extract R0 ordering and minimum separations from all accepted schedules."""

    paths = require_sources()
    final = read_json(paths["exact_final_acceptance"])
    phase0 = read_json(paths["phase0_controller_contract"])
    v1_summary = read_json(paths["rejected_v1_summary"])
    checks = {
        "accepted_exact_path_go": final.get("decision") == "GO",
        "phase0_contract_go": phase0.get("decision") == "Controller Functional Contract = GO",
        "rejected_v1_is_no_go": v1_summary.get("decision") == "Cycle-Quantized Startup Protocol = NO-GO",
    }
    per_voltage = {}
    aggregate = {adjacent_key(EVENT_NAMES[index - 1], name): [] for index, name in enumerate(EVENT_NAMES) if index}
    csv_rows = []

    for voltage in VOLTAGES:
        schedule = read_json(paths["exact_schedule_{}".format(voltage)])
        probes = operation_probes(schedule)
        order_ok = True
        pair_values = {key: [] for key in aggregate}
        for probe in probes:
            times = [float(probe[field]) for _, field in EVENT_FIELDS]
            order_ok = order_ok and all(left < right for left, right in zip(times, times[1:]))
            for index in range(1, len(EVENT_NAMES)):
                key = adjacent_key(EVENT_NAMES[index - 1], EVENT_NAMES[index])
                pair_values[key].append(times[index] - times[index - 1])
                aggregate[key].append(times[index] - times[index - 1])
        separations = {
            key: {"minimum_s": min(values), "maximum_s": max(values)}
            for key, values in pair_values.items()
        }
        per_voltage[voltage] = {
            "probe_count": len(probes),
            "strict_event_order": order_ok,
            "adjacent_separations_s": separations,
        }
        checks["{}_strict_event_order".format(voltage)] = order_ok
        for key, values in separations.items():
            csv_rows.append({
                "voltage": voltage,
                "event_pair": key,
                "probe_count": len(probes),
                "strict_event_order": order_ok,
                "minimum_separation_s": values["minimum_s"],
                "maximum_separation_s": values["maximum_s"],
            })

    aggregate_separations = {
        key: {"minimum_s": min(values), "maximum_s": max(values)}
        for key, values in aggregate.items()
    }
    # The exact evidence establishes every pair as positive.  This guard keeps
    # a corrupted source schedule from silently becoming a zero-cycle contract.
    checks["all_adjacent_separations_positive"] = all(item["minimum_s"] > 0.0 for item in aggregate_separations.values())
    decision = "Exact-Path Event Order Extraction = GO" if all(checks.values()) else "Exact-Path Event Order Extraction = NO-GO"
    audit = {
        "schema_version": 1,
        "decision": decision,
        "canonical_events": [{"name": name, "source_field": field} for name, field in EVENT_FIELDS],
        "checks": checks,
        "per_voltage": per_voltage,
        "aggregate_adjacent_separations_s": aggregate_separations,
    }
    manifest = {
        "schema_version": 1,
        "inputs": [
            {"name": name, "path": str(path.relative_to(FTC_ROOT)), "sha256": sha256_file(path)}
            for name, path in sorted(paths.items())
        ],
    }
    return audit, csv_rows, manifest


def publish_audit():
    """Write all R0 artefacts and return the in-memory audit for R1."""

    audit, csv_rows, manifest = audit_exact_paths()
    write_json(OUT / "exact_path_event_order_audit.json", audit)
    write_csv(
        OUT / "exact_path_event_order_audit.csv",
        ("voltage", "event_pair", "probe_count", "strict_event_order", "minimum_separation_s", "maximum_separation_s"),
        csv_rows,
    )
    write_json(OUT / "source_manifest.json", manifest)
    return audit, manifest


def ceil_cycle(value_s):
    """Round a positive physical requirement up to a whole 1 GHz interval."""

    # A small numerical tolerance prevents a binary representation of exactly
    # 3.0 ns from becoming 3.0000000000000004 cycles and rounding to four.
    return max(0, int(math.ceil(value_s / PERIOD_S - 1.0e-12)))


def solve_local_template(audit):
    """Solve the earliest action-cycle chain while retaining reset edge offsets.

    ``RESET_ASSERT_COMPLETE`` is not a separately clocked command: it is the
    physical completion of the reset PWL edge.  Treating it as a new cycle was
    the subtle over-quantisation error this correction must avoid.  The greedy
    cumulative solution is earliest feasible because the constraints form one
    forward chain and every lower bound is monotonic.
    """

    pairs = audit["aggregate_adjacent_separations_s"]
    control_edge_s = pairs[adjacent_key("RESET_ASSERT_START", "RESET_ASSERT_COMPLETE")]["minimum_s"]
    actions = {"RESET_RELEASE": 0}

    # Actual release completion occurs after the fixed PWL edge.  The source
    # schedule's release timestamp is the historical anchor; the candidate is
    # conservative because it waits a full cycle after physical completion.
    release_complete_s = actions["RESET_RELEASE"] * PERIOD_S + control_edge_s
    rise_need_s = release_complete_s + pairs[adjacent_key("RESET_RELEASE_COMPLETE", "S_CLK_RISE")]["minimum_s"]
    actions["S_CLK_RISE"] = ceil_cycle(rise_need_s)

    q1_need_s = actions["S_CLK_RISE"] * PERIOD_S + pairs[adjacent_key("S_CLK_RISE", "Q_SAMPLE_1")]["minimum_s"]
    actions["Q_SAMPLE_1"] = ceil_cycle(q1_need_s)
    q2_need_s = actions["Q_SAMPLE_1"] * PERIOD_S + pairs[adjacent_key("Q_SAMPLE_1", "Q_SAMPLE_2")]["minimum_s"]
    actions["Q_SAMPLE_2"] = ceil_cycle(q2_need_s)
    assert_need_s = actions["Q_SAMPLE_2"] * PERIOD_S + pairs[adjacent_key("Q_SAMPLE_2", "RESET_ASSERT_START")]["minimum_s"]
    actions["RESET_ASSERT"] = ceil_cycle(assert_need_s)

    # Reset assertion completes at ``RESET_ASSERT`` plus the frozen control
    # edge; S_CLK fall is the next independently clocked action.
    fall_need_s = (
        actions["RESET_ASSERT"] * PERIOD_S
        + control_edge_s
        + pairs[adjacent_key("RESET_ASSERT_COMPLETE", "S_CLK_FALL")]["minimum_s"]
    )
    actions["S_CLK_FALL"] = ceil_cycle(fall_need_s)
    recovery_need_s = actions["S_CLK_FALL"] * PERIOD_S + pairs[adjacent_key("S_CLK_FALL", "RECOVERY_DONE")]["minimum_s"]
    actions["RECOVERY_DONE"] = ceil_cycle(recovery_need_s)

    event_times = {
        "RESET_RELEASE_COMPLETE": actions["RESET_RELEASE"] * PERIOD_S + control_edge_s,
        "S_CLK_RISE": actions["S_CLK_RISE"] * PERIOD_S,
        "Q_SAMPLE_1": actions["Q_SAMPLE_1"] * PERIOD_S,
        "Q_SAMPLE_2": actions["Q_SAMPLE_2"] * PERIOD_S,
        "RESET_ASSERT_START": actions["RESET_ASSERT"] * PERIOD_S,
        "RESET_ASSERT_COMPLETE": actions["RESET_ASSERT"] * PERIOD_S + control_edge_s,
        "S_CLK_FALL": actions["S_CLK_FALL"] * PERIOD_S,
        "RECOVERY_DONE": actions["RECOVERY_DONE"] * PERIOD_S,
    }
    constraints_satisfied = {
        key: event_times[right] - event_times[left] >= value["minimum_s"] - 1.0e-15
        for key, value in pairs.items()
        for left, right in [key.split("__to__")]
    }
    # The expected vector documents the established result, while equality is
    # a verification of the algorithm rather than a source of timing values.
    expected_actions = {
        "RESET_RELEASE": 0,
        "S_CLK_RISE": 1,
        "Q_SAMPLE_1": 4,
        "Q_SAMPLE_2": 5,
        "RESET_ASSERT": 6,
        "S_CLK_FALL": 7,
        "RECOVERY_DONE": 10,
    }
    return {
        "controller_action_cycles": actions,
        "event_time_offsets_s": {"reset_edge_complete_s": control_edge_s},
        "event_times_from_probe_start_s": event_times,
        "constraints_satisfied": constraints_satisfied,
        "earliest_solution_matches_expected": actions == expected_actions,
    }


def add_operation(operations, name, before_m, after_m, before_f, after_f, expected=""):
    """Append one high-level operation inherited unchanged from Phase 0."""

    operations.append({
        "operation_index": len(operations),
        "operation_type": name,
        "M_before": before_m,
        "M_after": after_m,
        "F_before": before_f,
        "F_after": after_f,
        "expected_q": expected,
    })


def build_operations(trajectory):
    """Recreate the frozen coarse/fine operation sequence without retuning it."""

    boundary = trajectory["coarse_boundary"]
    base = trajectory["selected_medium_base"]
    fine_boundary = trajectory["fine_boundary"]
    guard = trajectory["guard_code"]
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
        expected = "STABLE_HIGH" if fine < fine_boundary else "STABLE_LOW"
        add_operation(operations, "FINE_PROBE", base, base, fine, fine, expected)
        if fine != fine_boundary:
            add_operation(operations, "FINE_INCREMENT", base, base, fine, fine + 1)
    add_operation(operations, "FINE_INCREMENT_GUARD", base, base, fine_boundary, guard)
    add_operation(operations, "GUARD_PROBE", base, base, guard, guard, "STABLE_LOW")
    add_operation(operations, "HOLD_PROBE", base, base, guard, guard, "STABLE_LOW")
    return operations


def build_schedule(trajectory, template, audit):
    """Apply the single solved local template to one frozen voltage trajectory."""

    actions = template["controller_action_cycles"]
    operations = build_operations(trajectory)
    cursor = 0
    probes = []
    transitions = []
    for operation in operations:
        operation["start_cycle"] = cursor
        changed = (operation["M_before"], operation["F_before"]) != (operation["M_after"], operation["F_after"])
        if changed:
            operation["kind"] = "CONFIG_UPDATE"
            operation["done_cycle"] = cursor + 2
            transitions.append({
                "operation_index": operation["operation_index"],
                "operation_type": operation["operation_type"],
                "M_before": operation["M_before"], "M_after": operation["M_after"],
                "F_before": operation["F_before"], "F_after": operation["F_after"],
                "update_cycle": cursor, "settle_done_cycle": cursor + 2,
            })
            cursor += 2
            continue

        operation["kind"] = "PROBE"
        operation["done_cycle"] = cursor + actions["RECOVERY_DONE"]
        probes.append({
            "probe_index": len(probes),
            "operation_index": operation["operation_index"],
            "operation_type": operation["operation_type"],
            "M": operation["M_before"], "F": operation["F_before"],
            "expected_q": operation["expected_q"],
            "reset_release_cycle": cursor + actions["RESET_RELEASE"],
            "sclk_rise_cycle": cursor + actions["S_CLK_RISE"],
            "sample_1_cycle": cursor + actions["Q_SAMPLE_1"],
            "sample_2_cycle": cursor + actions["Q_SAMPLE_2"],
            "reset_assert_cycle": cursor + actions["RESET_ASSERT"],
            "sclk_fall_cycle": cursor + actions["S_CLK_FALL"],
            "recovery_done_cycle": cursor + actions["RECOVERY_DONE"],
        })
        cursor += actions["RECOVERY_DONE"]

    backoffs = [item["operation_index"] for item in operations if item["operation_type"].startswith("MEDIUM_DECREMENT_BACKOFF")]
    pairs = audit["aggregate_adjacent_separations_s"]
    checks = {
        "all_changes_are_config_updates": all((item["kind"] == "CONFIG_UPDATE") == ((item["M_before"], item["F_before"]) != (item["M_after"], item["F_after"])) for item in operations),
        "single_thermometer_step_per_update": all(abs(item["M_after"] - item["M_before"]) + abs(item["F_after"] - item["F_before"]) == 1 for item in transitions),
        "probe_code_constant": all(item["M"] == operations[item["operation_index"]]["M_before"] and item["F"] == operations[item["operation_index"]]["F_before"] for item in probes),
        "two_adjacent_backoffs_without_probe": len(backoffs) == 2 and backoffs[1] == backoffs[0] + 1,
        "one_intended_sclk_rise_event": all(item["sclk_rise_cycle"] < item["sclk_fall_cycle"] for item in probes),
        "two_q_sample_events": all(item["sample_1_cycle"] < item["sample_2_cycle"] for item in probes),
        "reset_assert_precedes_sclk_fall": all(item["sample_2_cycle"] < item["reset_assert_cycle"] < item["sclk_fall_cycle"] for item in probes),
        "launch_to_sample_1_interval_met": all((item["sample_1_cycle"] - item["sclk_rise_cycle"]) * PERIOD_S >= pairs[adjacent_key("S_CLK_RISE", "Q_SAMPLE_1")]["minimum_s"] - 1.0e-15 for item in probes),
        "config_settle_two_cycles": all(item["settle_done_cycle"] - item["update_cycle"] == 2 for item in transitions),
    }
    return {"operations": operations, "probes": probes, "transitions": transitions, "final_cycle": cursor, "checks": checks}


def build_contracts(audit, manifest):
    """Perform R1 only after a successful R0 audit and publish all schedules."""

    if audit.get("decision") != "Exact-Path Event Order Extraction = GO":
        raise ValueError("R0 is not GO; refusing to construct v2 timing")
    phase0 = read_json(PHASE0_CONTRACT)
    if phase0.get("decision") != "Controller Functional Contract = GO":
        raise ValueError("Phase 0 functional contract is not GO")
    template = solve_local_template(audit)
    if not all(template["constraints_satisfied"].values()) or not template["earliest_solution_matches_expected"]:
        raise ValueError("ordered difference-constraint solver did not produce the earliest feasible template")
    timing = {
        "cal_clk_hz": 1_000_000_000,
        "period_s": PERIOD_S,
        "config_settle_cycles": 2,
        "local_probe_action_cycles": template["controller_action_cycles"],
        "sclk_high_cycles": template["controller_action_cycles"]["S_CLK_FALL"] - template["controller_action_cycles"]["S_CLK_RISE"],
        "event_time_offsets_s": template["event_time_offsets_s"],
    }
    rendered = []
    expected_counts = {"0p80": 45, "0p95": 36, "1p10": 36}
    for voltage in VOLTAGES:
        schedule = build_schedule(phase0["scenarios"][voltage], template, audit)
        if not all(schedule["checks"].values()):
            raise ValueError("v2 structural timing check failed: {}".format(voltage))
        if len(schedule["operations"]) != expected_counts[voltage]:
            raise ValueError("v2 operation count changed: {}".format(voltage))
        document = {
            "schema_version": 2,
            "decision": "Event-Ordered Cycle Schedule Construction = GO",
            "voltage": voltage,
            "timing": timing,
            "trajectory": phase0["scenarios"][voltage],
            "event_order_contract_sha256": sha256_file(OUT / "exact_path_event_order_audit.json"),
            "source_manifest_sha256": sha256_file(OUT / "source_manifest.json"),
            **schedule,
        }
        path = OUT / "cycle_path_v2_{}_contract.json".format(voltage)
        write_json(path, document)
        rendered.append({"voltage": voltage, "path": str(path), "sha256": sha256_file(path)})
    timing_contract = {
        "schema_version": 2,
        "decision": "Event-Ordered Cycle Schedule Construction = GO",
        "timing": timing,
        "constraints": audit["aggregate_adjacent_separations_s"],
        "solver": template,
        "phase0_contract_sha256": sha256_file(PHASE0_CONTRACT),
        "source_manifest_sha256": sha256_file(OUT / "source_manifest.json"),
    }
    write_json(OUT / "ordered_timing_constraints.json", {
        "schema_version": 1,
        "decision": "Event-Ordered Cycle Schedule Construction = GO",
        "canonical_events": list(EVENT_NAMES),
        "minimum_adjacent_separations_s": audit["aggregate_adjacent_separations_s"],
        "solver": template,
    })
    write_json(OUT / "cycle_timing_contract_v2.json", timing_contract)
    write_json(OUT / "pre_run_freeze.json", {
        "schema_version": 2,
        "decision": "NOT_RUN",
        "scenario_budget": SCENARIO_BUDGET,
        "scenarios": rendered,
        "source_manifest_sha256": sha256_file(OUT / "source_manifest.json"),
        "cycle_timing_contract_sha256": sha256_file(OUT / "cycle_timing_contract_v2.json"),
        "simulator_invoked": False,
    })


def parse_args(argv=None):
    """Expose only the two non-simulation builder stages required by R0/R1."""

    parser = argparse.ArgumentParser(description="build FTC event-ordered v2 timing contracts")
    parser.add_argument("--audit-only", action="store_true", help="run only Phase 1R0; do not create cycle contracts")
    return parser.parse_args(argv)


def main(argv=None):
    """Publish R0, and optionally R1, with nonzero status on a failed gate."""

    args = parse_args(argv)
    try:
        audit, manifest = publish_audit()
        if audit["decision"] != "Exact-Path Event Order Extraction = GO":
            return 2
        if not args.audit_only:
            build_contracts(audit, manifest)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print("event-order v2 build failed: {}".format(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
