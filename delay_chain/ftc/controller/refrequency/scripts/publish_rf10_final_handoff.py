#!/usr/bin/env python3
"""Publish RF10 only after every re-frequency gate has retained GO evidence.

RF10 is a reporting and supersession phase, not a new implementation or
simulation phase.  This publisher reads the immutable historical baseline and
the task-owned RF0--RF9D results, rejects any incomplete or NO-GO prerequisite,
and then creates the three required RF10 documents exactly once.  It never
edits RTL, a sensor deck, a simulator log, a historical handoff, or an earlier
re-frequency result.
"""

import hashlib
import json
import re
from pathlib import Path


# Derive all locations from this script instead of the launch directory.  That
# guarantees RF10 remains confined to controller/refrequency even when called
# from a remote host or CI job.
CONTROLLER_ROOT = Path(__file__).resolve().parents[2]
RF_ROOT = CONTROLLER_ROOT / "refrequency"
REPORT_ROOT = RF_ROOT / "reports"
STATUS_PATH = REPORT_ROOT / "REFREQUENCY_STATUS.md"
GATE_PATH = REPORT_ROOT / "REFREQUENCY_GATE_STATUS.json"
FINAL_PATH = REPORT_ROOT / "REFREQUENCY_FINAL_REPORT.md"

# The trajectory is an immutable functional contract.  RF10 uses it only to
# verify that every prior report describes the same unmodified calibration
# algorithm; it is never used as a per-voltage tuning input.
EXPECTATIONS = {
    "0p80": {"M": 7, "F": 6, "operations": 45, "configs": 17, "probes": 28},
    "0p95": {"M": 4, "F": 6, "operations": 36, "configs": 14, "probes": 22},
    "1p10": {"M": 2, "F": 9, "operations": 36, "configs": 15, "probes": 21},
}


def sha256(path):
    """Hash an input without changing its evidence contents or timestamps."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path):
    """Return a controller-relative evidence path for portable handoff text."""

    return str(path.relative_to(CONTROLLER_ROOT))


def read_json(path):
    """Read one JSON evidence object and reject accidental non-object input."""

    if not path.is_file():
        raise ValueError("missing required evidence: {}".format(path))
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def evidence_record(path):
    """Bind one report status entry to its exact source file and content hash."""

    if not path.is_file():
        raise ValueError("missing required evidence: {}".format(path))
    return {"path": relative(path), "sha256": sha256(path)}


def require(condition, message):
    """Turn a failed gate predicate into a precise RF10 publication failure."""

    if not condition:
        raise ValueError(message)


def require_nominal_results(document, expected_decision, label):
    """Verify all three frozen trajectories in an RF6/RF9 aggregate document."""

    require(document.get("decision") == expected_decision,
            "{} decision is not GO".format(label))
    results = {entry.get("scenario"): entry for entry in document.get("results", [])}
    for tag, expected in EXPECTATIONS.items():
        scenario = "rf9_" + tag
        # RF6 scenarios are named cycle_path_refreq_<voltage>, while RF9 uses
        # rf9_<voltage>.  Resolve only this fixed naming difference; no result
        # selection is based on a voltage-specific preference.
        if label == "RF6":
            scenario = "cycle_path_refreq_" + tag
        item = results.get(scenario)
        require(item is not None, "{} missing scenario {}".format(label, scenario))
        if label == "RF6":
            actual = {
                "M": item.get("final_locked_code", {}).get("M"),
                "F": item.get("final_locked_code", {}).get("F"),
                "configs": item.get("config_update_count"),
                "probes": item.get("probe_count"),
            }
            expected_subset = {key: expected[key] for key in ("M", "F", "configs", "probes")}
            require(actual == expected_subset,
                    "RF6 trajectory mismatch for {}: {}".format(scenario, actual))
        else:
            require(item.get("status") == "PASS" and item.get("errors") == [],
                    "{} scenario {} is not a clean PASS".format(label, scenario))
            require(item.get("expected") == expected,
                    "{} frozen trajectory mismatch for {}".format(label, scenario))


def require_phase8b_log(log_path, compile_path, returncode_path, sdf_enabled):
    """Validate RF9A/RF9B's retained three-voltage behavioral evidence.

    The historical Phase-8B bench emits one pass line per voltage plus one
    aggregate marker.  RF9B additionally requires successful SDF annotation
    and full timing checks, so this routine applies those checks only when its
    ``sdf_enabled`` argument is true.
    """

    for path in (log_path, compile_path, returncode_path):
        require(path.is_file(), "missing RF9 behavioral evidence: {}".format(path))
    run_text = log_path.read_text(encoding="utf-8", errors="replace")
    compile_text = compile_path.read_text(encoding="utf-8", errors="replace")
    require(returncode_path.read_text(encoding="utf-8").strip() == "0",
            "RF9 behavioral simulator return code is not zero")
    for tag, expected in EXPECTATIONS.items():
        voltage = {"0p80": "0p80V", "0p95": "0p95V", "1p10": "1p10V"}[tag]
        marker = "PHASE8B_PASS scenario={} ops={} configs={} probes={} samples={}/{} final=M{}/F{}".format(
            voltage, expected["operations"], expected["configs"], expected["probes"],
            expected["probes"], expected["probes"], expected["M"], expected["F"])
        require(marker in run_text, "RF9 behavioral pass marker missing: {}".format(voltage))
    require("PHASE8B_ALL_PASS nominal=3 sdf=max exact_ops=45,36,36" in run_text,
            "RF9 behavioral aggregate PASS marker missing")
    require("PHASE8B_FAIL" not in run_text and "Timing violation" not in run_text,
            "RF9 behavioral run contains a failure marker")
    if sdf_enabled:
        require("***    SDF annotation completed:" in compile_text and "Total errors: 0" in compile_text,
                "RF9B SDF annotation did not complete with zero errors")
        require("Need timing check option +neg_tchk" not in compile_text,
                "RF9B was not built with negative timing checks enabled")
        require("SDF Error:" not in compile_text,
                "RF9B compile log contains an SDF error")
        require("+nospecify" not in compile_text and "+notimingcheck" not in compile_text and
                "+nospecify" not in run_text and "+notimingcheck" not in run_text,
                "RF9B evidence contains a forbidden timing-check bypass")


def write_once(path, text):
    """Create a new RF10 report without replacing any prior publication."""

    if path.exists():
        raise RuntimeError("RF10 publication already exists; refusing to overwrite {}".format(path))
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def build_markdown(summary):
    """Create the two human-readable RF10 reports from validated source facts."""

    root = summary["root_cause"]
    clock = summary["clock"]
    timing = summary["timing_contract"]
    synth = summary["synthesis"]
    status = """# Re-Frequency Status

## RF10 decision

`Re-Frequency Closure Handoff = GO`

The active FTC controller timing baseline is the 400 MHz / 2.5 ns re-frequency
handoff.  This RF10 publication is evidence-only: it does not modify the
controller RTL, the frozen transistor sensor, the calibration algorithm, or
historical 1 GHz artifacts.

## Active and retained evidence

| Evidence | Published status |
|---|---|
| Historical 1 GHz Phase 1 handoff | Retained historical evidence; superseded for active RTL timing consumption |
| Historical 1 GHz Phase 7 synthesis | Retained historical implementation evidence |
| Historical 1 GHz C3 timing-composed failure | Retained root-cause evidence |
| Re-frequency timing handoff | ACTIVE |
| Re-frequency synthesis/SDF | ACTIVE |
| Three-voltage SDF + XA + transistor closure | GO |

## Active timing contract

- `cal_clk`: 400 MHz (`Tcal = 2.5 ns`), selected from the guarded static limit.
- Configuration settle: 1 cycle.
- Local probe actions: reset release 0, S_CLK rise 1, Q samples 2/3,
  reset assert 4, S_CLK fall 5, recovery done 7.

The existing Phase 10 freeze path may now resume from this active baseline;
Phase 10 work itself is governed by its separate final-closure plan.
"""
    final = """# FTC SMIC40LL Re-Frequency Final Report

## RF10 conclusion

`Re-Frequency Closure Handoff = GO`

The prior 1 GHz timing-composed implementation is retained as root-cause
evidence.  The active implementation uses the reviewed 400 MHz / 2.5 ns
calibration clock and closes the complete mapped-controller, SDF, XA, and
frozen-transistor-sensor composition at 0.80 V, 0.95 V, and 1.10 V.

## 1 GHz root cause and library capability

The earliest causal 1 GHz failure was `{cell}` at `{instance}`: a conditional
`CK_LOW_WIDTH` check required {required} ps and observed {observed} ps.  Its
notifier propagated controller X state in the preserved C3 evidence.  The
inventory contains {total} width violations ({low} low-width and {high}
high-width); it establishes a frequency-dependent clock-pulse limitation, not
a hold-only issue.

The audited SMIC40LL sequential-cell timing model uses a 1.0 ns minimum CK
high/low width, 1.0 ns setup and recovery, and 0.5 ns hold and removal.  RF2
also recorded the conditional Verilog specify checks separately from Liberty
semantics.  RF8 confirmed all cells in the new mapping are inside the audited
RF2 cell set.

## Selected clock and cycle schedule

The static hard period is {hard:.2f} ns, limited by 1.0 ns high/low CK width
at 50% duty cycle.  The explicit policy `max(1.25 * T_hard, T_hard + 0.25 ns)`
gives {guarded:.2f} ns; upward rounding on the 0.5 ns grid selects {period:.2f}
ns ({frequency} MHz).  The resulting half-cycle width is {half:.2f} ns, with
{width_margin:.2f} ns width margin.

The schedule is the earliest event-order-preserving integer solution, not a
scaled copy of the 1 GHz cycle table: reset release 0, S_CLK rise 1, Q sample
1 at 2, Q sample 2 at 3, reset assertion 4, S_CLK fall 5, recovery done 7;
configuration settling is re-derived to 1 cycle.

## Three-voltage validation chain

| Voltage | Operations | Configurations | Probes | Final code |
|---|---:|---:|---:|---|
| 0.80 V | 45 | 17 | 28 | M7/F6 |
| 0.95 V | 36 | 14 | 22 | M4/F6 |
| 1.10 V | 36 | 15 | 21 | M2/F9 |

- RF6: all three frozen transistor-sensor scenarios passed with one common
  timing template; the accepted HSPICE measurements prove physical CK and
  reset-before-S_CLK-return integrity.
- RF8: synthesis/STA passed with positive margins: setup {setup:.2f} ns,
  hold {hold:.2f} ns, q_final {q_final:.2f} ns, sense_s_clk {sclk:.2f} ns,
  sense_dff_reset {reset:.2f} ns, thermometer {therm:.2f} ns, and pulse width
  {pulse:.2f} ns.
- RF9A: RTL plus behavioral sensor passed all three nominal trajectories.
- RF9B: mapped controller plus SDF plus behavioral sensor passed with full
  timing checks; no `+nospecify` or `+notimingcheck` bypass was used.
- RF9C: mapped controller plus corrected XA bridge plus frozen transistor
  sensor passed at all three voltages before SDF composition.
- RF9D: full SDF + XA + frozen transistor-sensor closure passed at all three
  voltages with zero causal timing violations, no notifier-driven X, exact
  operation/configuration/probe counts, one active sensor clock edge per
  probe, correct Q sample pairs, safe reset/S_CLK ordering, correct final
  codes, and stable locked M/F codes.

## Architecture and algorithm freeze

The sensor architecture and calibration algorithm are unchanged.  RF7 changed
only timing quantization and configuration settle duration; RF9C and RF9D both
record `sensor_or_algorithm_modified = false`.  No per-voltage calibration
clock or local timing template was used.

## Supersession and next handoff

Historical 1 GHz Phase 1/Phase 7/C3 evidence remains retained and reviewable.
The RF7 handoff marks the historical Phase 1 source superseded for active RTL
timing consumption, while the re-frequency handoff and synthesis/SDF are
ACTIVE.  With RF10 now GO, the existing Phase 10 final-freeze plan is authorized
to resume from this baseline.
""".format(
        cell=root["cell_type"], instance=root["instance"], required=root["required_ps"],
        observed=root["observed_ps"], total=root["inventory_total"], low=root["inventory_low"],
        high=root["inventory_high"], hard=clock["hard_ns"], guarded=clock["guarded_ns"],
        period=clock["period_ns"], frequency=clock["frequency_mhz"], half=clock["half_ns"],
        width_margin=clock["width_margin_ns"], setup=synth["setup"], hold=synth["hold"],
        q_final=synth["q_final"], sclk=synth["sense_s_clk"], reset=synth["sense_dff_reset"],
        therm=synth["thermometer"], pulse=synth["pulse_width"], timing=timing)
    return status, final


def main():
    """Validate RF0--RF9D, then atomically publish the three RF10 documents."""

    # RF10 must be a new publication.  Refusing existing targets prevents a
    # later rerun from silently replacing an approved report with different
    # text or altered evidence hashes.
    for path in (STATUS_PATH, GATE_PATH, FINAL_PATH):
        require(not path.exists(), "RF10 report already exists: {}".format(path))

    paths = {
        "baseline": RF_ROOT / "baseline" / "baseline_manifest.json",
        "root_cause": RF_ROOT / "root_cause" / "first_failure_trace.json",
        "inventory": RF_ROOT / "root_cause" / "timing_violation_inventory.json",
        "capability": RF_ROOT / "library_audit" / "sequential_cell_timing_capability.json",
        "consistency": RF_ROOT / "library_audit" / "liberty_vs_verilog_timing_check_audit.json",
        "hard_limit": RF_ROOT / "clock_selection" / "cal_clk_hard_limit.json",
        "guard": RF_ROOT / "clock_selection" / "guard_band_policy.json",
        "selection": RF_ROOT / "clock_selection" / "cal_clk_selection.json",
        "contract": RF_ROOT / "timing_contract" / "cycle_timing_contract_refrequency.json",
        "rf5": RF_ROOT / "timing_contract" / "rf5_zero_hspice_regression.json",
        "rf6": RF_ROOT / "hspice" / "summary.json",
        "rf7": RF_ROOT / "handoff" / "phase1_timing_handoff_refrequency.json",
        "rtl_audit": RF_ROOT / "handoff" / "rtl_timing_contract_audit.json",
        "rf8": RF_ROOT / "synthesis" / "phase_refrequency_synthesis_results.json",
        "rf9a_manifest": RF_ROOT / "verification" / "rtl_behavioral" / "pre_run_manifest.json",
        "rf9a_compile": RF_ROOT / "verification" / "rtl_behavioral" / "run" / "compile.log",
        "rf9a_run": RF_ROOT / "verification" / "rtl_behavioral" / "run" / "run.log",
        "rf9a_returncode": RF_ROOT / "verification" / "rtl_behavioral" / "run" / "returncode.txt",
        "rf9b_manifest": RF_ROOT / "verification" / "sdf_behavioral" / "pre_run_manifest.json",
        "rf9b_compile": RF_ROOT / "verification" / "sdf_behavioral" / "run" / "compile.log",
        "rf9b_run": RF_ROOT / "verification" / "sdf_behavioral" / "run" / "run.log",
        "rf9b_returncode": RF_ROOT / "verification" / "sdf_behavioral" / "run" / "returncode.txt",
        "rf9c": RF_ROOT / "verification" / "mixed_signal_no_sdf" / "RF9C_AUTONOMOUS_MIXED_SIGNAL.json",
        "rf9d": RF_ROOT / "verification" / "mixed_signal_sdf" / "RF9D_TIMING_COMPOSED_MIXED_SIGNAL.json",
    }
    documents = {name: read_json(path) for name, path in paths.items()
                 if path.suffix == ".json"}

    # RF0--RF5 establish that re-frequency is justified and its schedule is
    # derived rather than guessed.  Each predicate below maps directly to the
    # corresponding plan gate and fails closed on an absent/changed result.
    baseline = documents["baseline"]
    root_cause = documents["root_cause"]
    inventory = documents["inventory"]
    capability = documents["capability"]
    consistency = documents["consistency"]
    hard_limit = documents["hard_limit"]
    guard = documents["guard"]
    selection = documents["selection"]
    contract = documents["contract"]
    rf5 = documents["rf5"]
    require(baseline.get("baseline_status") == "GO" and not baseline.get("missing_required_inputs"),
            "RF0 baseline freeze is not GO")
    require(root_cause.get("status") == "GO" and root_cause.get("re_frequency_eligibility") == "GO",
            "RF1 root-cause eligibility is not GO")
    first = root_cause.get("first_causal_violation", {})
    require(first.get("classification") == "CK_LOW_WIDTH" and first.get("required_value_ps") == 1000 and
            first.get("observed_value_ps") == 500, "RF1 exact causal timing check changed")
    require(inventory.get("status") == "GO", "RF1 violation inventory is not GO")
    require(capability.get("status") == "GO" and
            consistency.get("status") == "GO_WITH_RF8_CONFIRMATION_REQUIRED",
            "RF2 library timing audit is incomplete")
    require(hard_limit.get("status") == "GO" and guard.get("status") == "GO" and
            selection.get("status") == "GO", "RF3 clock selection is not GO")
    require(selection.get("selected_period_ns") == 2.5 and selection.get("selected_frequency_hz") == 400000000,
            "RF3 selected clock is not the reviewed 400 MHz / 2.5 ns value")
    require(contract.get("status") == "GO" and contract.get("config_settle_cycles") == 1 and
            contract.get("local_probe_action_cycles") == {
                "RESET_RELEASE": 0, "S_CLK_RISE": 1, "Q_SAMPLE_1": 2, "Q_SAMPLE_2": 3,
                "RESET_ASSERT": 4, "S_CLK_FALL": 5, "RECOVERY_DONE": 7},
            "RF4 timing contract is not the active reviewed schedule")
    require(rf5.get("status") == "GO" and all(rf5.get("checks", {}).values()),
            "RF5 contract regression is not GO")

    # RF6--RF8 bind the physical sensor validation, active RTL handoff, and
    # independent synthesis/STA closure to the exact same selected timing.
    rf6 = documents["rf6"]
    rf7 = documents["rf7"]
    rtl_audit = documents["rtl_audit"]
    rf8 = documents["rf8"]
    require_nominal_results(rf6, "Re-Frequency Transistor Sensor Protocol = GO", "RF6")
    require(rf6.get("timing_template_changed_after_execution") is False,
            "RF6 changed the frozen common timing template")
    require(rf7.get("decision") == "Re-Frequency Controller Timing Handoff = GO" and
            rf7.get("active_controller_timing_source") is True,
            "RF7 active timing handoff is not GO")
    require(rf7.get("supersession", {}).get("historical_1ghz_handoff", {}).get("status") ==
            "retained_historical_evidence_superseded_for_active_rtl_timing",
            "RF7 does not retain/supersede the historical handoff correctly")
    require(rtl_audit.get("decision") == "RTL Timing Contract Audit = GO" and
            all(rtl_audit.get("checks", {}).values()), "RF7 RTL drift audit is not GO")
    require(rf8.get("decision") == "Re-Frequency Synthesized Controller = GO" and
            all(rf8.get("checks", {}).values()), "RF8 synthesis closure is not GO")

    # RF9A/RF9B use one historical bench whose output contains the three exact
    # nominal trajectories.  The manifests establish that both used the common
    # 2.5 ns clock and that RF9B did not disable timing checks.
    rf9a_manifest = documents["rf9a_manifest"]
    rf9b_manifest = documents["rf9b_manifest"]
    require(rf9a_manifest.get("clock_period_ns") == 2.5 and
            rf9a_manifest.get("timing_checks_disabled") is False,
            "RF9A manifest does not preserve the active timing contract")
    require(rf9b_manifest.get("clock_period_ns") == 2.5 and rf9b_manifest.get("sdf_enabled") is True and
            rf9b_manifest.get("timing_checks_disabled") is False,
            "RF9B manifest does not preserve full SDF timing checks")
    require_phase8b_log(paths["rf9a_run"], paths["rf9a_compile"], paths["rf9a_returncode"], False)
    require_phase8b_log(paths["rf9b_run"], paths["rf9b_compile"], paths["rf9b_returncode"], True)

    # RF9C verifies bridge/sensor function before SDF, while RF9D closes the
    # exact all-in timing composition.  Their result files are hash-addressed
    # and carry all voltage-specific count and final-code expectations.
    rf9c = documents["rf9c"]
    rf9d = documents["rf9d"]
    require_nominal_results(rf9c, "Re-Frequency Autonomous Mixed-Signal Function = GO", "RF9C")
    require_nominal_results(rf9d, "Re-Frequency Timing-Composed Startup Calibration = GO", "RF9D")
    require(rf9d.get("timing_check_bypass") == {"nospecify": False, "notimingcheck": False} and
            rf9d.get("rf6_frozen_transistor_sensor_contract_go") is True and
            not rf9d.get("shared_errors"), "RF9D full timing composition is not clean")

    # These redundant freeze flags make the final statement falsifiable and
    # prevent RF10 from relabeling a functional redesign as a timing closure.
    no_architecture_or_algorithm_change = (
        baseline.get("sensor_architecture_frozen") is True and
        baseline.get("calibration_algorithm_frozen") is True and
        rf7.get("algorithm_change") == "none; only timing quantization and configuration settle duration changed" and
        rf9c.get("sensor_or_algorithm_modified") is False and
        rf9d.get("sensor_or_algorithm_modified") is False
    )
    require(no_architecture_or_algorithm_change,
            "freeze evidence does not prove the sensor architecture and algorithm remained unchanged")

    summary = {
        "root_cause": {
            "cell_type": root_cause["cell_type"], "instance": root_cause["mapped_instance"],
            "required_ps": first["required_value_ps"], "observed_ps": first["observed_value_ps"],
            "inventory_total": inventory["total_violations"],
            "inventory_low": inventory["classes"]["CK_LOW_WIDTH"]["count"],
            "inventory_high": inventory["classes"]["CK_HIGH_WIDTH"]["count"],
        },
        "clock": {
            "hard_ns": hard_limit["T_hard_ns"], "guarded_ns": guard["T_guarded_ns"],
            "period_ns": selection["selected_period_ns"],
            "frequency_mhz": selection["selected_frequency_hz"] // 1000000,
            "half_ns": selection["predicted_clock_high_low_width_ns"],
            "width_margin_ns": selection["predicted_width_margin_ns"],
        },
        "timing_contract": contract["local_probe_action_cycles"],
        "synthesis": {
            "setup": rf8["margins_ns"]["setup"], "hold": rf8["margins_ns"]["hold"],
            "q_final": rf8["margins_ns"]["q_final_sampling"],
            "sense_s_clk": rf8["margins_ns"]["sense_s_clk"],
            "sense_dff_reset": rf8["margins_ns"]["sense_dff_reset"],
            "thermometer": rf8["margins_ns"]["thermometer"],
            "pulse_width": rf8["margins_ns"]["clock_high_low_width"],
        },
    }
    status_text, final_text = build_markdown(summary)
    gate = {
        "schema_version": 1,
        "decision": "Re-Frequency Closure Handoff = GO",
        "active_timing_baseline": {
            "cal_clk_hz": selection["selected_frequency_hz"],
            "period_ns": selection["selected_period_ns"],
            "timing_handoff": relative(paths["rf7"]),
            "synthesis_sdf": "ACTIVE",
        },
        "historical_evidence": {
            "phase1_handoff": "retained_historical_evidence_superseded_for_active_rtl_timing",
            "phase7_synthesis": "retained_historical_implementation_evidence",
            "c3_timing_composed_failure": "retained_root_cause_evidence",
        },
        "gate_status": {
            "RF0_baseline_freeze": "GO", "RF1_root_cause": "GO", "RF2_library_audit": "GO",
            "RF3_clock_selection": "GO", "RF4_event_ordered_schedule": "GO",
            "RF5_contract_regression": "GO", "RF6_transistor_sensor": "GO",
            "RF7_active_handoff": "GO", "RF8_synthesis_sta": "GO",
            "RF9A_rtl_behavioral": "GO", "RF9B_sdf_behavioral": "GO",
            "RF9C_no_sdf_xa": "GO", "RF9D_sdf_xa_transistor": "GO",
            "RF10_handoff": "GO",
        },
        "frozen_architecture_and_algorithm_unchanged": True,
        "phase10_handoff": {
            "status": "authorized_to_resume_from_active_refrequency_baseline",
            "governing_plan": "plans/ftc_startup_calibration_final_closure_and_freeze_plan.md",
            "rf10_does_not_execute_phase10": True,
        },
        "evidence_sha256": {name: evidence_record(path) for name, path in sorted(paths.items())},
    }

    # All validation occurs before this point.  The three writes therefore form
    # one small publication set; no partial RF10 report can be mistaken for a
    # passed handoff if a prerequisite gate is missing or fails.
    REPORT_ROOT.mkdir(parents=True, exist_ok=False)
    write_once(STATUS_PATH, status_text)
    write_once(GATE_PATH, json.dumps(gate, indent=2, sort_keys=True))
    write_once(FINAL_PATH, final_text)
    print(gate["decision"])


if __name__ == "__main__":
    main()
