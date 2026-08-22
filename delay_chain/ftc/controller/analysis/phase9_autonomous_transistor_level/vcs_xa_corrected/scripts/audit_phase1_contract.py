#!/usr/bin/env python3
"""Mechanically audit the canonical Phase 1 timing handoff.

This audit is intentionally independent of RTL parsing.  It verifies that the
single JSON source of truth contains the required 1 GHz period, the frozen
configuration settle interval, and the strictly ordered probe events.  The
corrected Phase 9 testbench can consume the resulting JSON, but this script
never edits synthesizable RTL or creates a simulator run.
"""

import json
from pathlib import Path


SCRIPT = Path(__file__).resolve()
FLOW_ROOT = SCRIPT.parents[1]
FTC_ROOT = FLOW_ROOT.parents[3]
TIMING = FTC_ROOT / "controller" / "spec" / "phase1_timing_handoff.json"
OUTPUT = FLOW_ROOT / "inputs" / "phase1_contract_audit.json"


def main() -> int:
    """Validate and publish the extracted timing values."""

    document = json.loads(TIMING.read_text(encoding="utf-8"))
    local = document["local_probe_event_cycles"]
    expected = {
        "cal_clk_hz": 1_000_000_000,
        "period_ns": 1.0,
        "configuration_settle_cycles": 2,
        "events": {
            "RESET_RELEASE": 0,
            "S_CLK_RISE": 1,
            "Q_SAMPLE_1": 4,
            "Q_SAMPLE_2": 5,
            "RESET_ASSERT": 6,
            "S_CLK_FALL": 7,
            "RECOVERY_DONE": 10,
        },
    }
    observed = {
        "cal_clk_hz": document["cal_clk_hz"],
        "period_ns": 1.0e9 / document["cal_clk_hz"],
        "configuration_settle_cycles": document["configuration_settle_cycles"],
        "events": {name: local[name] for name in expected["events"]},
    }
    errors = []
    if observed["cal_clk_hz"] != expected["cal_clk_hz"]:
        errors.append("cal_clk_hz is not 1 GHz")
    if observed["period_ns"] != expected["period_ns"]:
        errors.append("cal_clk period is not 1 ns")
    if observed["configuration_settle_cycles"] != expected["configuration_settle_cycles"]:
        errors.append("configuration settle interval is not two cycles")
    if observed["events"] != expected["events"]:
        errors.append("local probe event cycles differ from frozen contract")
    if list(observed["events"].values()) != sorted(observed["events"].values()):
        errors.append("local probe events are not monotonically ordered")
    result = {"schema_version": 1, "source": str(TIMING), "expected": expected, "observed": observed, "errors": errors, "status": "PASS" if not errors else "FAIL"}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
