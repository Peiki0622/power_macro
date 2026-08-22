#!/usr/bin/env python3
"""Mechanically prove active synthesizable timing constants match RF7 JSON.

This is a read-only drift guard: it does not generate RTL and it never edits
the handoff.  Keeping the timing constants hand-written but machine-audited is
the smallest synthesizable solution for this controller package.
"""

import json
import re
from pathlib import Path


CONTROLLER_ROOT = Path(__file__).resolve().parents[2]
REFREQUENCY_ROOT = CONTROLLER_ROOT / "refrequency"
HANDOFF_PATH = REFREQUENCY_ROOT / "handoff" / "phase1_timing_handoff_refrequency.json"
PACKAGE_PATH = CONTROLLER_ROOT / "rtl" / "ftc_cal_pkg.sv"
SEQUENCER_PATH = CONTROLLER_ROOT / "rtl" / "ftc_operation_sequencer.sv"
AUDIT_PATH = REFREQUENCY_ROOT / "handoff" / "rtl_timing_contract_audit.json"


def read_json(path):
    """Load an object from a handoff/audit file with a clear error."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def package_parameter(text, name):
    """Extract one integer package parameter without evaluating RTL code."""

    match = re.search(r"parameter\s+int\s+{}\s*=\s*(\d+)\s*;".format(re.escape(name)), text)
    if match is None:
        raise ValueError("missing integer package parameter: {}".format(name))
    return int(match.group(1))


def main():
    """Write a deterministic GO/NO-GO record for RF7 and later RF8 gates."""

    handoff = read_json(HANDOFF_PATH)
    if handoff.get("decision") != "Re-Frequency Controller Timing Handoff = GO":
        raise ValueError("active RF7 handoff is not GO")
    actions = handoff["local_probe_action_cycles"]
    expected = {
        "CONFIG_SETTLE_CYCLES": handoff["configuration_settle_cycles"],
        "PROBE_RESET_RELEASE_CYCLE": actions["RESET_RELEASE"],
        "PROBE_SCLK_RISE_CYCLE": actions["S_CLK_RISE"],
        "PROBE_Q_SAMPLE_1_CYCLE": actions["Q_SAMPLE_1"],
        "PROBE_Q_SAMPLE_2_CYCLE": actions["Q_SAMPLE_2"],
        "PROBE_RESET_ASSERT_CYCLE": actions["RESET_ASSERT"],
        "PROBE_SCLK_FALL_CYCLE": actions["S_CLK_FALL"],
        "PROBE_RECOVERY_DONE_CYCLE": actions["RECOVERY_DONE"],
        "PROBE_SCLK_HIGH_CYCLES": handoff["probe_sclk_high_cycles"],
    }
    package_text = PACKAGE_PATH.read_text(encoding="utf-8")
    observed = {name: package_parameter(package_text, name) for name in expected}
    # These symbol checks establish that the synthesizable sequencer consumes
    # the audited package constants rather than a hidden duplicate terminal
    # count.  They intentionally do not impose any new implementation style.
    sequencer_text = SEQUENCER_PATH.read_text(encoding="utf-8")
    # Reset release is the operation-acceptance edge, and S_CLK-high duration
    # is a derived handoff datum.  Neither has a separate runtime terminal
    # compare.  All remaining symbols drive live sequencer comparisons.
    required_symbols = tuple(
        name for name in expected
        if name not in ("PROBE_RESET_RELEASE_CYCLE", "PROBE_SCLK_HIGH_CYCLES")
    )
    symbol_usage = {name: (name in sequencer_text) for name in required_symbols}
    checks = {
        "handoff_is_active": handoff.get("active_controller_timing_source") is True,
        "all_package_constants_match": observed == expected,
        "sequencer_uses_all_runtime_event_constants": all(symbol_usage.values()),
        "derived_sclk_high_cycles_match": (
            expected["PROBE_SCLK_HIGH_CYCLES"] ==
            expected["PROBE_SCLK_FALL_CYCLE"] - expected["PROBE_SCLK_RISE_CYCLE"]
        ),
        "event_order_strict": (
            expected["PROBE_RESET_RELEASE_CYCLE"] < expected["PROBE_SCLK_RISE_CYCLE"] <
            expected["PROBE_Q_SAMPLE_1_CYCLE"] < expected["PROBE_Q_SAMPLE_2_CYCLE"] <
            expected["PROBE_RESET_ASSERT_CYCLE"] < expected["PROBE_SCLK_FALL_CYCLE"] <
            expected["PROBE_RECOVERY_DONE_CYCLE"]
        ),
    }
    result = {
        "schema_version": 1,
        "decision": "RTL Timing Contract Audit = GO" if all(checks.values()) else "RTL Timing Contract Audit = NO-GO",
        "checks": checks,
        "expected_parameters": expected,
        "observed_package_parameters": observed,
        "sequencer_symbol_usage": symbol_usage,
        "handoff": str(HANDOFF_PATH.relative_to(CONTROLLER_ROOT)),
        "package": str(PACKAGE_PATH.relative_to(CONTROLLER_ROOT)),
    }
    AUDIT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not all(checks.values()):
        raise SystemExit("RTL timing contract audit failed")


if __name__ == "__main__":
    main()
