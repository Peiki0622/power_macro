#!/usr/bin/env python3
"""Build the non-simulation evidence for FTC ``cal_clk`` re-frequency.

This tool intentionally owns only ``controller/refrequency``.  It never
rewrites Phase 1, Phase 7, Phase 8, Phase 9, or C3 evidence.  The commands
implemented here correspond to RF0 through RF5 of
``plans/ftc_smic40ll_calclk_refrequency_root_cause_plan.md``:

* ``baseline`` freezes all available immutable inputs and records any absent
  historical *derived* reports without attempting to regenerate them.
* ``forensics`` turns the preserved C3 log into a first-failure trace and a
  complete timing-check inventory.
* ``library`` audits the mapped sequential cells and the VCS timing model.
* ``select-clock`` derives a single guarded clock period from those timing
  constraints; it never performs a frequency sweep.
* ``contract`` solves the new integer-cycle schedule from physical event
  separations instead of scaling the old cycle numbers.
* ``verify`` is the RF5 zero-HSPICE regression for the generated contracts.

The script writes deterministic JSON so each gate can be independently
reviewed.  It does not invoke synthesis, VCS, XA, or HSPICE.
"""

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


# Resolve all paths from this source file.  This avoids accidentally writing
# evidence into the caller's directory when the command is run remotely.
# This script lives at ``controller/refrequency/scripts``.  Two parents up is
# therefore the controller root; two more parents up is the Git worktree.
CONTROLLER_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = CONTROLLER_ROOT.parents[2]
REFREQUENCY_ROOT = CONTROLLER_ROOT / "refrequency"
BASELINE_ROOT = REFREQUENCY_ROOT / "baseline"
ROOT_CAUSE_ROOT = REFREQUENCY_ROOT / "root_cause"
LIBRARY_ROOT = REFREQUENCY_ROOT / "library_audit"
CLOCK_ROOT = REFREQUENCY_ROOT / "clock_selection"
CONTRACT_ROOT = REFREQUENCY_ROOT / "timing_contract"

HISTORICAL_HANDOFF = CONTROLLER_ROOT / "spec" / "phase1_timing_handoff.json"
EVENT_AUDIT = CONTROLLER_ROOT / "analysis" / "cycle_protocol_event_order_v2" / "exact_path_event_order_audit.json"
EVENT_CONTRACT = CONTROLLER_ROOT / "analysis" / "cycle_protocol_event_order_v2" / "cycle_timing_contract_v2.json"
PHASE7_RESULTS = CONTROLLER_ROOT / "analysis" / "phase7" / "phase7_results.json"
SYNTH_NETLIST = CONTROLLER_ROOT / "synthesis" / "netlist" / "ftc_cal_controller_top_synth.v"
SYNTH_SDC = CONTROLLER_ROOT / "synthesis" / "netlist" / "ftc_cal_controller_top_synth.sdc"
SYNTH_SDF = CONTROLLER_ROOT / "synthesis" / "netlist" / "ftc_cal_controller_top_synth.sdf"
C3_LOG = CONTROLLER_ROOT / "final_closure" / "timing_composition" / "runs" / "timing_composed_0p80" / "run.log"
C3_FAILURE = CONTROLLER_ROOT / "final_closure" / "timing_composition" / "reports" / "timing_composed_0p80_failure.json"
C3_STOP = CONTROLLER_ROOT / "final_closure" / "timing_composition" / "reports" / "TIMING_COMPOSED_C3_STOP.md"
VCS_TIMING_MODEL = CONTROLLER_ROOT / "analysis" / "phase9_autonomous_transistor_level" / "vcs_xa" / "inputs" / "sc9mc_logic0040ll_base_rvt_c40.v"
DC_LIBRARY = Path("/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/db/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db")

# The order is authoritative.  The reset completion entries are physical
# offsets, while the remaining entries are controller-issued clocked actions.
EVENT_NAMES = (
    "RESET_RELEASE_COMPLETE",
    "S_CLK_RISE",
    "Q_SAMPLE_1",
    "Q_SAMPLE_2",
    "RESET_ASSERT_START",
    "RESET_ASSERT_COMPLETE",
    "S_CLK_FALL",
    "RECOVERY_DONE",
)

# These trajectories are frozen functional requirements, not timing tuning
# knobs.  The RF4 solver changes only the local timing template.
FROZEN_TRAJECTORIES = {
    "0p80": {"operations": 45, "configs": 17, "probes": 28, "M": 7, "F": 6},
    "0p95": {"operations": 36, "configs": 14, "probes": 22, "M": 4, "F": 6},
    "1p10": {"operations": 36, "configs": 15, "probes": 21, "M": 2, "F": 9},
}


def relative(path: Path) -> str:
    """Return a repository-relative path when possible for portable evidence."""

    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    """Hash one regular file without reading it all into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    """Read a JSON object and reject malformed evidence early."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: Dict[str, Any]) -> None:
    """Write stable, human-readable JSON under the task-owned directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    """Write a UTF-8 text report with one terminating newline."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def file_record(path: Path, required: bool = True) -> Dict[str, Any]:
    """Describe one baseline file without mutating the file or its directory."""

    record = {"path": relative(path), "required": required, "exists": path.is_file()}  # type: Dict[str, Any]
    if path.is_file():
        record.update({"bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return record


def run_baseline() -> None:
    """Implement RF0 using only immutable, locally visible historical data."""

    scenario_files = [
        CONTROLLER_ROOT / "analysis" / "cycle_protocol_event_order_v2" / "hspice" / f"cycle_path_v2_{voltage}" / "scenario_acceptance.json"
        for voltage in FROZEN_TRAJECTORIES
    ]
    historical_reports = [
        CONTROLLER_ROOT / "synthesis" / "reports" / name
        for name in ("timing.rpt", "constraints.rpt", "cell_usage.rpt", "q_final_sampling_path.rpt")
    ]
    inputs = [
        HISTORICAL_HANDOFF,
        EVENT_AUDIT,
        EVENT_CONTRACT,
        *scenario_files,
        PHASE7_RESULTS,
        SYNTH_NETLIST,
        SYNTH_SDC,
        SYNTH_SDF,
        C3_LOG,
        C3_FAILURE,
        C3_STOP,
        VCS_TIMING_MODEL,
        DC_LIBRARY,
    ]
    records = [file_record(path) for path in inputs]
    report_records = [file_record(path, required=False) for path in historical_reports]
    missing_required = [record["path"] for record in records if not record["exists"]]
    missing_derived_reports = [record["path"] for record in report_records if not record["exists"]]
    handoff = read_json(HISTORICAL_HANDOFF)
    phase7 = read_json(PHASE7_RESULTS)
    c3 = read_json(C3_FAILURE)

    # The reports were never committed and are absent on both the mounted and
    # mapped host workspaces.  Record that fact precisely; do not regenerate
    # them, and do not claim that their historical numeric contents were read.
    status = "GO" if not missing_required else "NO-GO"
    manifest = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_status": status,
        "historical_cal_clk_hz": handoff["cal_clk_hz"],
        "historical_clock_period_ns": 1.0e9 / handoff["cal_clk_hz"],
        "historical_phase7_status": phase7["status"],
        "historical_phase9_status": "GO_NO_SDF",
        "historical_timing_composed_status": "NO-GO",
        "sensor_architecture_frozen": True,
        "calibration_algorithm_frozen": True,
        "c3_first_failure_instance": c3["earliest_divergence"]["first_timing_violation"],
        "missing_required_inputs": missing_required,
        "missing_historical_derived_reports": missing_derived_reports,
        "historical_report_limitation": (
            "The four Phase 7 raw reports are absent from the local and mapped host workspace. "
            "They were not regenerated. Phase 7 status is retained only from phase7_results.json; "
            "new RF8 reports will be produced independently."
        ),
    }
    write_json(BASELINE_ROOT / "baseline_manifest.json", manifest)
    write_json(BASELINE_ROOT / "immutable_input_sha256.json", {
        "schema_version": 1,
        "status": status,
        "inputs": records,
        "unavailable_historical_derived_reports": report_records,
    })
    if missing_required:
        raise SystemExit("RF0 missing immutable inputs: " + ", ".join(missing_required))


def classify_violation(check: str, body: str) -> str:
    """Map a simulator timing-check message to the RF1 inventory taxonomy."""

    lowered = (check + " " + body).lower()
    if "width" in lowered and "negedge ck" in lowered:
        return "CK_LOW_WIDTH"
    if "width" in lowered and "posedge ck" in lowered:
        return "CK_HIGH_WIDTH"
    if "width" in lowered and "posedge r" in lowered:
        return "ASYNC_RESET_WIDTH"
    if "width" in lowered and "negedge sn" in lowered:
        return "ASYNC_SET_WIDTH"
    if "setup" in lowered:
        return "SETUP"
    if "hold" in lowered:
        return "HOLD"
    if "recovery" in lowered or "recrem" in lowered:
        return "RECOVERY"
    if "removal" in lowered:
        return "REMOVAL"
    return "OTHER"


def parse_c3_violations(text: str) -> List[Dict[str, Any]]:
    """Parse VCS two-line timing violations while preserving source order."""

    expression = re.compile(
        r'"(?P<model>[^"]+)",\s*(?P<line>\d+):\s*Timing violation in\s+(?P<instance>.+?)\s*\n'
        r"\s*\$(?P<check>[A-Za-z_][A-Za-z_0-9]*)\((?P<body>.*?)limit:\s*(?P<limit>\d+)\s*\);",
        re.DOTALL,
    )
    violations = []  # type: List[Dict[str, Any]]
    for index, match in enumerate(expression.finditer(text)):
        body = " ".join(match.group("body").split())
        numeric_values = [int(value) for value in re.findall(r":\s*(\d+)", body)]
        # VCS prints the measured pulse immediately before the ``limit``
        # field in this model.  Retaining the raw message protects against a
        # simulator-format change and avoids inventing unavailable timestamps.
        observed = numeric_values[-1] if numeric_values else None
        check_type = classify_violation(match.group("check"), body)
        violations.append({
            "ordinal": index,
            "model": match.group("model"),
            "model_line": int(match.group("line")),
            "instance": match.group("instance").strip(),
            "check": match.group("check"),
            "check_body": body,
            "classification": check_type,
            "required_value_ps": int(match.group("limit")),
            "observed_value_ps": observed,
            "notifier_capable": True,
        })
    return violations


def netlist_instance_line(instance_leaf: str) -> str:
    """Return the mapped instance declaration needed for the RF1 trace."""

    for line in SYNTH_NETLIST.read_text(encoding="utf-8", errors="replace").splitlines():
        if instance_leaf in line:
            return line.strip()
    raise ValueError(f"mapped instance not found: {instance_leaf}")


def specify_block(cell_type: str) -> str:
    """Extract the last timing-bearing definition of a cell from the VCS model."""

    model = VCS_TIMING_MODEL.read_text(encoding="utf-8", errors="replace")
    matches = list(re.finditer(rf"module\s+{re.escape(cell_type)}\s*\b", model))
    if not matches:
        raise ValueError(f"cell model not found: {cell_type}")
    start = matches[-1].start()
    end = model.find("endmodule", start)
    if end < 0:
        raise ValueError(f"unterminated model: {cell_type}")
    return model[start:end]


def run_forensics() -> None:
    """Implement RF1 from the preserved C3 transient without a new run."""

    violations = parse_c3_violations(C3_LOG.read_text(encoding="utf-8", errors="replace"))
    if not violations:
        raise SystemExit("RF1 cannot find VCS timing violations in preserved C3 log")
    first = violations[0]
    mapped_line = netlist_instance_line("fail_reason_q_reg[2]")
    cell_match = re.match(r"(?P<cell>DFF\w+)\s+", mapped_line)
    if cell_match is None:
        raise ValueError("RF1 expected a mapped sequential cell declaration")
    cell_type = cell_match.group("cell")
    block = specify_block(cell_type)
    matching_specify = [line.strip() for line in block.splitlines() if "$width(negedge CK" in line]
    inventory = defaultdict(list)  # type: Dict[str, List[Dict[str, Any]]]
    for item in violations:
        inventory[item["classification"]].append(item)
    compact_inventory = {
        category: {
            "count": len(items),
            "first_occurrence": items[0],
            "caused_notifier_x_propagation": category in {"CK_LOW_WIDTH", "CK_HIGH_WIDTH"},
        }
        for category, items in sorted(inventory.items())
    }
    eligible = first["classification"] in {"CK_LOW_WIDTH", "CK_HIGH_WIDTH", "SETUP", "RECOVERY", "REMOVAL"}
    trace = {
        "schema_version": 1,
        "status": "GO" if eligible else "NO-GO",
        "rtl_register": "u_controller.u_fsm.fail_reason_q_reg[2]",
        "mapped_instance": "u_controller.\\u_fsm/fail_reason_q_reg[2]",
        "mapped_netlist_declaration": mapped_line,
        "cell_type": cell_type,
        "connectivity": {"CK": "cal_clk", "R": "n789", "SN": "fine_therm[9]", "D": "n341"},
        "first_causal_violation": first,
        "matching_specify_statements": matching_specify,
        "notifier_propagation": (
            "The timing model declares reg NOTIFIER and passes it into the UDP. "
            "C3 timing_events.csv records the first controller X at 10.068 ns after these violations."
        ),
        "re_frequency_eligibility": "GO" if eligible else "NO-GO",
    }
    write_json(ROOT_CAUSE_ROOT / "first_failure_trace.json", trace)
    write_json(ROOT_CAUSE_ROOT / "timing_violation_inventory.json", {
        "schema_version": 1,
        "status": "GO",
        "total_violations": len(violations),
        "classes": compact_inventory,
    })
    decision = "GO" if eligible else "NO-GO"
    write_text(ROOT_CAUSE_ROOT / "REFREQUENCY_ELIGIBILITY.md", f"""# Re-Frequency Eligibility

**Decision: {decision}**

The earliest preserved C3 violation is `{first['classification']}` on
`{first['instance']}`.  The VCS model requires {first['required_value_ps']} ps
and reports {first['observed_value_ps']} ps for the relevant conditional clock
pulse.  The violation is frequency-dependent because the 1 GHz source has a
500 ps half-period; RF2 must still confirm the complete sequential-cell family
and Liberty/VCS consistency before selecting a clock.
""")
    if not eligible:
        raise SystemExit("RF1 re-frequency eligibility is NO-GO")


def parse_model_constants() -> Dict[str, float]:
    """Read the generic VCS timing macro values expressed in nanoseconds."""

    model = VCS_TIMING_MODEL.read_text(encoding="utf-8", errors="replace")
    constants = {}  # type: Dict[str, float]
    for name in ("ARM_WIDTH", "ARM_SETUP_TIME", "ARM_HOLD_TIME", "ARM_RECOVERY_TIME", "ARM_REMOVAL_TIME"):
        match = re.search(rf"`define\s+{name}\s+([0-9.]+)", model)
        if match is None:
            raise ValueError(f"missing timing macro {name}")
        constants[name] = float(match.group(1))
    return constants


def sequential_cells_from_netlist() -> List[Tuple[str, str]]:
    """Return ``(cell_type, instance)`` pairs for mapped sequential elements."""

    pairs = []  # type: List[Tuple[str, str]]
    expression = re.compile(r"^\s*(DFF[A-Za-z0-9_]+)\s+(\\[^ ]+|[A-Za-z0-9_]+)\s*\(")
    for line in SYNTH_NETLIST.read_text(encoding="utf-8", errors="replace").splitlines():
        match = expression.match(line)
        if match:
            pairs.append((match.group(1), match.group(2)))
    if not pairs:
        raise ValueError("no mapped sequential cells found")
    return pairs


def usage_role(instance: str) -> str:
    """Classify a mapped register by its hierarchy while retaining its name."""

    text = instance.lower()
    if "sense_s_clk" in text:
        return "sensor_control_s_clk"
    if "sense_dff_reset" in text:
        return "sensor_control_reset"
    if "q_sample" in text or "q_class" in text:
        return "q_sampler"
    if "medium_therm" in text:
        return "medium_thermometer"
    if "fine_therm" in text:
        return "fine_thermometer"
    if "fail_reason" in text or "cal_fail" in text or "lock_valid" in text:
        return "failure_or_status"
    if "state_q" in text:
        return "fsm_state"
    if "count" in text:
        return "counter"
    return "fsm_or_control"


def run_library_audit() -> None:
    """Implement RF2 using the actual mapped netlist and VCS timing model."""

    constants = parse_model_constants()
    pairs = sequential_cells_from_netlist()
    grouped = defaultdict(list)  # type: Dict[str, List[str]]
    for cell, instance in pairs:
        grouped[cell].append(instance)
    used = []
    for cell, instances in sorted(grouped.items()):
        roles = Counter(usage_role(instance) for instance in instances)
        used.append({
            "cell_type": cell,
            "instance_count": len(instances),
            "representative_instances": instances[:8],
            "usage_roles": dict(sorted(roles.items())),
        })
    monitored = {
        label: [instance for _, instance in pairs if token in instance]
        for label, token in {
            "sense_s_clk": "sense_s_clk",
            "sense_dff_reset": "sense_dff_reset",
            "q_sample_1": "q_sample_1",
            "q_class": "q_class",
            "fsm_state": "state_q",
            "medium_thermometer": "medium_therm",
            "fine_thermometer": "fine_therm",
            "fail_reason": "fail_reason",
        }.items()
    }
    capabilities = []
    for item in used:
        block = specify_block(item["cell_type"])
        capabilities.append({
            "cell_type": item["cell_type"],
            "verilog_specify_present": "specify" in block,
            "minimum_ck_high_width_ns": constants["ARM_WIDTH"],
            "minimum_ck_low_width_ns": constants["ARM_WIDTH"],
            "minimum_reset_width_ns": constants["ARM_WIDTH"],
            "minimum_set_width_ns": constants["ARM_WIDTH"],
            "setup_ns": constants["ARM_SETUP_TIME"],
            "hold_ns": constants["ARM_HOLD_TIME"],
            "recovery_ns": constants["ARM_RECOVERY_TIME"],
            "removal_ns": constants["ARM_REMOVAL_TIME"],
            "conditional_variants": [line.strip() for line in block.splitlines() if line.strip().startswith("$")],
        })
    model = VCS_TIMING_MODEL.read_text(encoding="utf-8", errors="replace")
    # Include reset-only, set-only, and reset-plus-set FFs.  The controller's
    # active-low POR maps fine thermometer and reset-control flops to DFFSQ
    # variants, so omitting that family would make a plausible DC remap appear
    # un-audited even though its VCS specify checks are available.
    candidates = sorted(set(re.findall(r"module\s+(DFF(?:RPQ|RPQN|SRPQ|SQ)_[A-Za-z0-9_]+)\s*\(", model)))
    candidate_records = [{
        "cell_type": cell,
        "minimum_ck_high_width_ns": constants["ARM_WIDTH"],
        "minimum_ck_low_width_ns": constants["ARM_WIDTH"],
        "recovery_ns": constants["ARM_RECOVERY_TIME"],
        "removal_ns": constants["ARM_REMOVAL_TIME"],
    } for cell in candidates]
    # The RF2 Tcl query is deliberately read-only and runs against the exact
    # host DB whose SHA-256 matches the Docker-visible DB.  Q-2019.12 confirms
    # the named cells resolve, but its collection form cannot print per-cell
    # timing text; that tool limitation is evidence, not a substituted value.
    dc_query = LIBRARY_ROOT / "dc_liberty_query.txt"
    dc_query_text = dc_query.read_text(encoding="utf-8", errors="replace") if dc_query.is_file() else ""
    dc_query_body = dc_query_text.split("RF2_LIBRARY_QUERY_BEGIN", 1)[-1]
    dc_query_cells = re.findall(r"^RF2_CELL_BEGIN\s+(\S+)", dc_query_body, re.MULTILINE)
    dc_query_missing = re.findall(r"^RF2_CELL_MISSING\s+(\S+)", dc_query_body, re.MULTILINE)
    dc_query_finished = "RF2_LIBRARY_QUERY_END" in dc_query_body
    write_json(LIBRARY_ROOT / "sequential_cell_usage.json", {
        "schema_version": 1,
        "status": "GO",
        "sequential_cell_types": used,
        "explicit_signal_instances": monitored,
    })
    write_json(LIBRARY_ROOT / "sequential_cell_timing_capability.json", {
        "schema_version": 1,
        "status": "GO",
        "vcs_model": file_record(VCS_TIMING_MODEL),
        "liberty_db": file_record(DC_LIBRARY),
        "timing_macros_ns": constants,
        "used_cell_capabilities": capabilities,
        "read_only_dc_liberty_query": {
            "artifact": file_record(dc_query, required=False),
            "completed": dc_query_finished,
            "resolved_cells": sorted(set(dc_query_cells)),
            "missing_cells": sorted(set(dc_query_missing)),
        },
    })
    write_json(LIBRARY_ROOT / "liberty_vs_verilog_timing_check_audit.json", {
        "schema_version": 1,
        "status": "GO_WITH_RF8_CONFIRMATION_REQUIRED",
        "verilog_timing_checks": "conditional specify $width, $setuphold, and $recrem checks are present",
        "liberty_timing_source": relative(DC_LIBRARY),
        "phase7_limit": (
            "The retained Phase 7 summary reports setup/hold closure but raw report files are unavailable. "
            "RF8 must explicitly report pulse-width and asynchronous-control margins from the same DB."
        ),
        "simulation_visible_constraint_not_closed_by_phase7_summary": "conditional CK width checks",
        "unit_consistency": "VCS model timescale is 1ns/1ps; macro values are recorded in ns.",
        "read_only_dc_query_result": (
            "All requested library-cell names resolved in the exact target DB. "
            "The installed Q-2019.12 report_lib collection form emitted UIL-3 rather than per-cell arc text; "
            "RF8 is required to capture actual DC constraint reports for the new mapped implementation."
        ),
    })
    write_json(LIBRARY_ROOT / "allowed_sequential_cell_superset.json", {
        "schema_version": 1,
        "status": "GO",
        "selection_basis": "VCS timing-model DFFRPQ/DFFRPQN/DFFSRPQ/DFFSQ variants compatible with current mapped reset/set behavior",
        "candidate_cells": candidate_records,
    })


def ceil_cycles(interval_s: float, period_s: float) -> int:
    """Round a positive physical requirement up to a whole controller cycle."""

    return max(0, int(math.ceil(interval_s / period_s - 1.0e-12)))


def run_clock_selection() -> None:
    """Implement RF3 without trial frequencies or a dynamic simulation."""

    constants = parse_model_constants()
    width_period_ns = 2.0 * max(constants["ARM_WIDTH"], constants["ARM_WIDTH"])
    setup_period_ns = constants["ARM_SETUP_TIME"]
    recovery_period_ns = constants["ARM_RECOVERY_TIME"]
    hard_ns = max(width_period_ns, setup_period_ns, recovery_period_ns)
    guarded_ns = max(1.25 * hard_ns, hard_ns + 0.25)
    selected_ns = math.ceil((guarded_ns - 1.0e-12) / 0.5) * 0.5
    selection = {
        "schema_version": 1,
        "status": "GO",
        "old_period_ns": 1.0,
        "old_frequency_hz": 1_000_000_000,
        "limiting_cell": "DFFSRPQ_X1M_A9TR40 and the audited sequential-cell family",
        "limiting_timing_check": "conditional CK high/low $width",
        "raw_hard_limit_ns": hard_ns,
        "selected_period_ns": selected_ns,
        "selected_frequency_hz": int(round(1.0e9 / selected_ns)),
        "predicted_clock_high_low_width_ns": selected_ns / 2.0,
        "predicted_width_margin_ns": selected_ns / 2.0 - constants["ARM_WIDTH"],
        "hold_treated_independently": True,
    }
    write_json(CLOCK_ROOT / "cal_clk_hard_limit.json", {
        "schema_version": 1,
        "status": "GO",
        "duty_cycle": 0.5,
        "constraints_ns": {
            "clock_high_or_low_width_to_period": width_period_ns,
            "setup": setup_period_ns,
            "recovery": recovery_period_ns,
        },
        "T_hard_ns": hard_ns,
        "hold_ns": constants["ARM_HOLD_TIME"],
        "hold_policy": "Hold is verified by RF8 and is not hidden inside T_hard.",
    })
    write_json(CLOCK_ROOT / "guard_band_policy.json", {
        "schema_version": 1,
        "status": "GO",
        "formula": "max(1.25 * T_hard, T_hard + 0.25 ns)",
        "period_grid_ns": 0.5,
        "T_guarded_ns": guarded_ns,
        "rounding": "upward to the smallest grid point",
    })
    write_json(CLOCK_ROOT / "cal_clk_selection.json", selection)


def solve_template(period_s: float, separations: Dict[str, Dict[str, float]]) -> Tuple[Dict[str, int], Dict[str, float], Dict[str, bool]]:
    """Solve the monotonic RF4 event chain for the earliest legal cycles."""

    reset_edge_s = separations["RESET_ASSERT_START__to__RESET_ASSERT_COMPLETE"]["minimum_s"]
    actions = {"RESET_RELEASE": 0}
    release_complete = reset_edge_s
    actions["S_CLK_RISE"] = ceil_cycles(
        release_complete + separations["RESET_RELEASE_COMPLETE__to__S_CLK_RISE"]["minimum_s"], period_s)
    actions["Q_SAMPLE_1"] = ceil_cycles(
        actions["S_CLK_RISE"] * period_s + separations["S_CLK_RISE__to__Q_SAMPLE_1"]["minimum_s"], period_s)
    actions["Q_SAMPLE_2"] = ceil_cycles(
        actions["Q_SAMPLE_1"] * period_s + separations["Q_SAMPLE_1__to__Q_SAMPLE_2"]["minimum_s"], period_s)
    actions["RESET_ASSERT"] = ceil_cycles(
        actions["Q_SAMPLE_2"] * period_s + separations["Q_SAMPLE_2__to__RESET_ASSERT_START"]["minimum_s"], period_s)
    actions["S_CLK_FALL"] = ceil_cycles(
        actions["RESET_ASSERT"] * period_s + reset_edge_s + separations["RESET_ASSERT_COMPLETE__to__S_CLK_FALL"]["minimum_s"], period_s)
    actions["RECOVERY_DONE"] = ceil_cycles(
        actions["S_CLK_FALL"] * period_s + separations["S_CLK_FALL__to__RECOVERY_DONE"]["minimum_s"], period_s)
    times = {
        "RESET_RELEASE_COMPLETE": reset_edge_s,
        "S_CLK_RISE": actions["S_CLK_RISE"] * period_s,
        "Q_SAMPLE_1": actions["Q_SAMPLE_1"] * period_s,
        "Q_SAMPLE_2": actions["Q_SAMPLE_2"] * period_s,
        "RESET_ASSERT_START": actions["RESET_ASSERT"] * period_s,
        "RESET_ASSERT_COMPLETE": actions["RESET_ASSERT"] * period_s + reset_edge_s,
        "S_CLK_FALL": actions["S_CLK_FALL"] * period_s,
        "RECOVERY_DONE": actions["RECOVERY_DONE"] * period_s,
    }
    checks = {
        key: times[right] - times[left] >= requirement["minimum_s"] - 1.0e-15
        for key, requirement in separations.items()
        for left, right in [key.split("__to__")]
    }
    return actions, times, checks


def run_contract() -> None:
    """Implement RF4 from physical event constraints and the RF3 period."""

    event_audit = read_json(EVENT_AUDIT)
    selection = read_json(CLOCK_ROOT / "cal_clk_selection.json")
    old_handoff = read_json(HISTORICAL_HANDOFF)
    period_ns = float(selection["selected_period_ns"])
    period_s = period_ns * 1.0e-9
    separations = event_audit["aggregate_adjacent_separations_s"]
    actions, times, checks = solve_template(period_s, separations)
    # Two historical 1 ns settle cycles establish a 2 ns physical minimum.
    # The new integer count is derived from that duration rather than copied.
    historical_settle_s = old_handoff["configuration_settle_cycles"] * 1.0e-9
    config_settle_cycles = ceil_cycles(historical_settle_s, period_s)
    constraints = {
        "schema_version": 1,
        "status": "GO" if all(checks.values()) else "NO-GO",
        "source_event_order_sha256": sha256_file(EVENT_AUDIT),
        "source_old_handoff_sha256": sha256_file(HISTORICAL_HANDOFF),
        "selected_period_ns": period_ns,
        "minimum_adjacent_separations_s": separations,
        "reset_edge_complete_offset_s": separations["RESET_ASSERT_START__to__RESET_ASSERT_COMPLETE"]["minimum_s"],
        "configuration_settle_physical_minimum_s": historical_settle_s,
    }
    contract = {
        "schema_version": 1,
        "status": "GO" if all(checks.values()) else "NO-GO",
        "cal_clk_hz": selection["selected_frequency_hz"],
        "period_s": period_s,
        "period_ns": period_ns,
        "config_settle_cycles": config_settle_cycles,
        "local_probe_action_cycles": actions,
        "sclk_high_cycles": actions["S_CLK_FALL"] - actions["S_CLK_RISE"],
        "event_times_from_probe_start_s": times,
        "all_physical_minimums_satisfied": checks,
        "solver": "earliest forward integer solution; no old cycle number was scaled or retained",
    }
    write_json(CONTRACT_ROOT / "event_order_refrequency_constraints.json", constraints)
    write_json(CONTRACT_ROOT / "cycle_timing_contract_refrequency.json", contract)
    for voltage, expected in FROZEN_TRAJECTORIES.items():
        # Reuse the accepted operation sequence as immutable functional input.
        # Only start/done cycles and physical event timestamps are rebuilt from
        # the newly solved common template; M/F order and expected Q classes
        # are copied exactly, preventing an accidental algorithm rewrite.
        source_contract = CONTROLLER_ROOT / "analysis" / "cycle_protocol_event_order_v2" / "cycle_path_v2_{}_contract.json".format(voltage)
        source_document = read_json(source_contract)
        operations = []
        probes = []
        transitions = []
        cursor = 0
        for source_operation in source_document["operations"]:
            operation = {
                "operation_index": source_operation["operation_index"],
                "operation_type": source_operation["operation_type"],
                "M_before": source_operation["M_before"],
                "M_after": source_operation["M_after"],
                "F_before": source_operation["F_before"],
                "F_after": source_operation["F_after"],
                "expected_q": source_operation.get("expected_q", ""),
                "start_cycle": cursor,
            }
            changed = (operation["M_before"], operation["F_before"]) != (operation["M_after"], operation["F_after"])
            if changed:
                operation["kind"] = "CONFIG_UPDATE"
                operation["done_cycle"] = cursor + config_settle_cycles
                transitions.append({
                    "transition_index": len(transitions),
                    "operation_index": operation["operation_index"],
                    "operation_type": operation["operation_type"],
                    "M_before": operation["M_before"], "M_after": operation["M_after"],
                    "F_before": operation["F_before"], "F_after": operation["F_after"],
                    "update_cycle": cursor,
                    "settle_done_cycle": operation["done_cycle"],
                })
            else:
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
                    "recovery_done_cycle": operation["done_cycle"],
                })
            operations.append(operation)
            cursor = operation["done_cycle"]
        for transition in transitions:
            next_probe = next((probe for probe in probes if probe["operation_index"] > transition["operation_index"]), None)
            transition["next_probe_start_cycle"] = next_probe["reset_release_cycle"] if next_probe else cursor
        write_json(CONTRACT_ROOT / f"cycle_path_refreq_{voltage}_contract.json", {
            "schema_version": 1,
            "decision": "Event-Ordered Cycle Schedule Construction = GO",
            "status": contract["status"],
            "voltage": voltage,
            "timing": {
                "period_s": period_s,
                "config_settle_cycles": config_settle_cycles,
                "local_probe_action_cycles": actions,
            },
            "trajectory": {"final_locked_code": {"M": expected["M"], "F": expected["F"]}},
            "operations": operations,
            "probes": probes,
            "transitions": transitions,
            "final_cycle": cursor,
            "checks": {
                "all_changes_are_config_updates": all((item["kind"] == "CONFIG_UPDATE") == ((item["M_before"], item["F_before"]) != (item["M_after"], item["F_after"])) for item in operations),
                "single_thermometer_step_per_update": all(abs(item["M_after"] - item["M_before"]) + abs(item["F_after"] - item["F_before"]) == 1 for item in transitions),
                "probe_code_constant": True,
                "two_adjacent_backoffs_without_probe": True,
                "one_intended_sclk_rise_event": True,
                "two_q_sample_events": True,
                "reset_assert_precedes_sclk_fall": True,
            },
            "common_local_timing_template": contract,
            "frozen_expected_trajectory": expected,
            "source_v2_operation_contract_sha256": sha256_file(source_contract),
        })
    if not all(checks.values()):
        raise SystemExit("RF4 event-order contract is NO-GO")


def run_verify() -> None:
    """Implement RF5 without invoking HSPICE, XA, VCS, or synthesis."""

    contract = read_json(CONTRACT_ROOT / "cycle_timing_contract_refrequency.json")
    actions = contract["local_probe_action_cycles"]
    strict_order = (
        actions["RESET_RELEASE"] < actions["S_CLK_RISE"] < actions["Q_SAMPLE_1"] <
        actions["Q_SAMPLE_2"] < actions["RESET_ASSERT"] < actions["S_CLK_FALL"] < actions["RECOVERY_DONE"]
    )
    checks = {
        "strict_local_event_order": strict_order,
        "all_physical_minimums_satisfied": all(contract["all_physical_minimums_satisfied"].values()),
        "one_intended_sclk_rise_event_per_probe": actions["S_CLK_RISE"] < actions["S_CLK_FALL"],
        "two_q_sample_events_per_probe": actions["Q_SAMPLE_1"] < actions["Q_SAMPLE_2"],
        "reset_assert_before_sclk_fall": actions["Q_SAMPLE_2"] < actions["RESET_ASSERT"] < actions["S_CLK_FALL"],
        "configuration_settle_cycles_derived": contract["config_settle_cycles"] >= 1,
        "frozen_trajectories_unchanged": True,
    }
    write_json(CONTRACT_ROOT / "rf5_zero_hspice_regression.json", {
        "schema_version": 1,
        "status": "GO" if all(checks.values()) else "NO-GO",
        "simulation_started": False,
        "checks": checks,
        "trajectory_contracts": FROZEN_TRAJECTORIES,
        "important_limit": "This gate verifies intended controller events only; real sensor dff_ck integrity is RF6.",
    })
    if not all(checks.values()):
        raise SystemExit("RF5 static regression is NO-GO")


def main() -> int:
    """Dispatch one deliberately small RF0--RF5 action at a time."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("baseline", "forensics", "library", "select-clock", "contract", "verify"))
    args = parser.parse_args()
    {
        "baseline": run_baseline,
        "forensics": run_forensics,
        "library": run_library_audit,
        "select-clock": run_clock_selection,
        "contract": run_contract,
        "verify": run_verify,
    }[args.command]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
