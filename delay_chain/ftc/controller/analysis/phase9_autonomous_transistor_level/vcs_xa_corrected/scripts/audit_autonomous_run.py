#!/usr/bin/env python3
"""Audit one completed corrected Phase 9 autonomous XA run.

The audit is deliberately read-only: it checks the compact runner report,
the event CSV terminal snapshot, and the XA log for comparison errors.  It
does not infer physical edge counts from CSV rows; the event counters printed
by the verification-only testbench are the authoritative edge/sample totals.
"""
import csv
import json
import re
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: audit_autonomous_run.py RUN_DIR", file=sys.stderr)
        return 2
    run = Path(sys.argv[1])
    audit_path = next(run.glob("*_audit.json"), None)
    if audit_path is None:
        raise SystemExit("missing runner audit JSON")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    log = (run / "run.log").read_text(encoding="utf-8", errors="replace")
    rows = list(csv.DictReader((run / "controller_events.csv").open(newline="")))
    if not rows:
        raise SystemExit("event CSV has no snapshots")
    terminal = rows[-1]
    expected = audit["expected"]
    errors = []
    if audit.get("status") != "PASS" or not audit.get("r6_pass_marker"):
        errors.append("runner audit is not PASS")
    if "Total number of comparison errors = 0" not in log:
        errors.append("XA comparison error summary is missing or nonzero")
    checks = {
        "operation_count": expected["operations"],
        "config_count": expected["configs"],
        "probe_count": expected["probes"],
        "sclk_rise_count": expected["sclk_rising_edges"],
        "sample1_count": expected["sample1"],
        # sample2_count is intentionally not a CSV column in the existing
        # compact schema; its event-driven counter is printed in R6_PASS.
    }
    for field, value in checks.items():
        if int(terminal[field]) != value:
            errors.append(f"terminal {field}={terminal[field]} expected {value}")
    marker = re.search(r"samples=(\d+)/(\d+)", log)
    if not marker or tuple(map(int, marker.groups())) != (expected["sample1"], expected["sample2"]):
        errors.append("PASS marker sample pair mismatch")
    if terminal["cal_done"] != "1" or terminal["cal_fail"] != "0" or terminal["lock_valid"] != "1":
        errors.append("terminal done/lock/fail status is inconsistent")
    if int(terminal["medium_code"], 16) != expected["final_medium"]:
        errors.append("terminal medium code mismatch")
    if int(terminal["fine_code"], 16) != expected["final_fine"]:
        errors.append("terminal fine code mismatch")
    if abs(float(terminal["analog_vdd"]) - audit["supply_v"]) > 0.001:
        errors.append("analog VDD does not match scenario supply")
    result = {
        "schema_version": 1,
        "scenario": audit["scenario"],
        "status": "PASS" if not errors else "FAIL",
        "comparison_errors_zero": "Total number of comparison errors = 0" in log,
        "terminal_snapshot": terminal,
        "errors": errors,
    }
    out = run / (audit["scenario"] + "_independent_audit.json")
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
