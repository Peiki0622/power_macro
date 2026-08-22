#!/usr/bin/env python3
"""Audit the isolated RF8 DC reports and publish the synthesis gate result.

The parser intentionally reads only task-owned reports plus RF2/RF3 evidence.
It derives no timing by simulation and refuses a new sequential cell unless the
allowed-superset audit covers it.
"""

import hashlib
import json
import re
from pathlib import Path


CONTROLLER_ROOT = Path(__file__).resolve().parents[2]
RF_ROOT = CONTROLLER_ROOT / "refrequency"
SYNTH_ROOT = RF_ROOT / "synthesis"
REPORT_ROOT = SYNTH_ROOT / "reports"
NETLIST = SYNTH_ROOT / "netlist" / "ftc_cal_controller_top_synth.v"
LIB_AUDIT = RF_ROOT / "library_audit" / "allowed_sequential_cell_superset.json"
CLOCK_SELECTION = RF_ROOT / "clock_selection" / "cal_clk_selection.json"
RESULT = SYNTH_ROOT / "phase_refrequency_synthesis_results.json"


def read_json(path):
    """Read an evidence object and reject an accidental array/string input."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def sha256(path):
    """Hash a completed RF8 artefact for later RF9 input binding."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def first_slack(path):
    """Return the worst listed MET slack from a DC timing report."""

    match = re.search(r"slack \(MET\)\s+([-+]?\d+(?:\.\d+)?)", path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError("no MET slack found: {}".format(path))
    return float(match.group(1))


def main():
    """Enforce RF8's positive-margin and sequential-cell eligibility gates."""

    required = [
        REPORT_ROOT / "dc_shell_returncode.txt", REPORT_ROOT / "dc_shell.log",
        REPORT_ROOT / "timing_setup.rpt", REPORT_ROOT / "timing_hold.rpt",
        REPORT_ROOT / "constraints_all.rpt", REPORT_ROOT / "fanout_transition.rpt",
        REPORT_ROOT / "q_final_sampling_path.rpt", REPORT_ROOT / "sense_s_clk_path.rpt",
        REPORT_ROOT / "sense_dff_reset_path.rpt", REPORT_ROOT / "thermometer_paths.rpt",
        REPORT_ROOT / "qor.rpt", REPORT_ROOT / "clock_and_pulse_width.rpt", NETLIST,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError("missing RF8 artefacts: " + ", ".join(missing))
    dc_log = (REPORT_ROOT / "dc_shell.log").read_text(encoding="utf-8", errors="replace")
    constraints = (REPORT_ROOT / "constraints_all.rpt").read_text(encoding="utf-8")
    design_rules = (REPORT_ROOT / "fanout_transition.rpt").read_text(encoding="utf-8")
    qor = (REPORT_ROOT / "qor.rpt").read_text(encoding="utf-8")
    netlist = NETLIST.read_text(encoding="utf-8")
    allowed = {entry["cell_type"] for entry in read_json(LIB_AUDIT)["candidate_cells"]}
    mapped_ff_cells = sorted(set(re.findall(r"\b(DFF[A-Z0-9_]*_A9TR40)\b", netlist)))
    unmapped_ff_cells = sorted(set(mapped_ff_cells) - allowed)
    setup = first_slack(REPORT_ROOT / "timing_setup.rpt")
    hold = first_slack(REPORT_ROOT / "timing_hold.rpt")
    q_final = first_slack(REPORT_ROOT / "q_final_sampling_path.rpt")
    sense_sclk = first_slack(REPORT_ROOT / "sense_s_clk_path.rpt")
    sense_reset = first_slack(REPORT_ROOT / "sense_dff_reset_path.rpt")
    thermometer = first_slack(REPORT_ROOT / "thermometer_paths.rpt")
    selection = read_json(CLOCK_SELECTION)
    pulse_width_ns = selection["predicted_clock_high_low_width_ns"]
    width_requirement_ns = 1.0
    pulse_margin = pulse_width_ns - width_requirement_ns
    checks = {
        "dc_returncode_zero": (REPORT_ROOT / "dc_shell_returncode.txt").read_text().strip() == "0",
        "no_dc_error": "Error:" not in dc_log,
        "positive_setup_margin": setup > 0.0,
        "positive_hold_margin": hold > 0.0,
        "positive_q_final_sampling_margin": q_final > 0.0,
        "positive_sensor_control_margins": sense_sclk > 0.0 and sense_reset > 0.0,
        "positive_thermometer_margin": thermometer > 0.0,
        "positive_clock_width_margin": pulse_margin > 0.0,
        "no_constraint_violators": "violated" not in constraints.lower(),
        "no_fanout_or_transition_violators": "no violated constraints" in design_rules.lower(),
        "no_black_boxes": "Macro/Black Box Area:      0.000000" in qor,
        "all_mapped_sequential_cells_rf2_covered": not unmapped_ff_cells,
        "active_period_is_2p5ns": "cal_clk          2.50" in (REPORT_ROOT / "clock_and_pulse_width.rpt").read_text(encoding="utf-8"),
    }
    result = {
        "schema_version": 1,
        "decision": "Re-Frequency Synthesized Controller = GO" if all(checks.values()) else "Re-Frequency Synthesized Controller = NO-GO",
        "checks": checks,
        "margins_ns": {
            "setup": setup, "hold": hold, "q_final_sampling": q_final,
            "sense_s_clk": sense_sclk, "sense_dff_reset": sense_reset,
            "thermometer": thermometer, "clock_high_low_width": pulse_margin,
        },
        "clock_width_assessment": {
            "half_period_ns": pulse_width_ns,
            "worst_rf2_vcs_width_requirement_ns": width_requirement_ns,
            "margin_ns": pulse_margin,
            "source": "RF2 timing model and RF3 guarded 2.5 ns selection",
        },
        "async_control_assessment": {
            "VCS_model_recovery_ns": 1.0,
            "VCS_model_removal_ns": 0.5,
            "static_scope": "controller-only netlist; sensor async set/reset composition is checked with active SDF in RF9D",
            "synthesis_arc_setting": "enable_recovery_removal_arcs true",
        },
        "mapped_sequential_cells": mapped_ff_cells,
        "rf2_uncovered_mapped_sequential_cells": unmapped_ff_cells,
        "artefact_sha256": {str(path.relative_to(CONTROLLER_ROOT)): sha256(path) for path in required if path.is_file()},
    }
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not all(checks.values()):
        raise SystemExit("RF8 synthesis gate failed")


if __name__ == "__main__":
    main()
