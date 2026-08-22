#!/usr/bin/env python3
"""Classify the preserved first C3 failure without launching another run.

The final-closure plan requires the first failing timing-composed run to be
retained and the sequence to stop.  This utility extracts only deterministic
failure evidence: SDF annotation status, the first timing violation, the
terminal R6 marker, and the first event where controller-visible state became
unknown.  It does not alter the run directory or attempt recovery simulation.
"""

import hashlib
import json
import csv
import re
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: classify_c3_failure.py RUN_DIR")
    run = Path(sys.argv[1])
    compile_log = run / "compile.log"
    run_log = run / "run.log"
    event_csv = run / "timing_events.csv"
    compile_text = compile_log.read_text(encoding="utf-8", errors="replace")
    run_text = run_log.read_text(encoding="utf-8", errors="replace")
    timing_match = re.search(r'^.*Timing violation.*$', run_text, re.MULTILINE)
    r6_match = re.search(r'^R6_FAIL.*$', run_text, re.MULTILINE)
    fatal_match = re.search(r'^Fatal:.*$', run_text, re.MULTILINE)
    first_unknown = None
    with event_csv.open(newline="", encoding="utf-8", errors="replace") as stream:
        for line_number, row in enumerate(csv.DictReader(stream), 2):
            # Ignore expected power-up X states.  The first meaningful
            # divergence is the post-reset controller state becoming unknown
            # after the first 1 GHz transaction window.
            if int(row.get("cal_edge", "0")) >= 10 and re.search(r"x", ",".join(row.values()), re.I):
                first_unknown = {"line": line_number, "event": row.get("event"), "time_ns": row.get("time_ns"), "text": ",".join(row.values())}
                break
    result = {
        "schema_version": 1,
        "scenario": "timing_composed_0p80",
        "status": "STOPPED_ON_TECHNICAL_FAILURE",
        "failure_class": "controller_output_clock_to_q_and_standard_cell_timing_check_failure",
        "tool_pair": "VCS P-2019.06-SP2_Full64 + PrimeSim XA S-2021.09-SP2",
        "clock_period_ns": 1.0,
        "timing_bypass_flags_used": [],
        "earliest_divergence": {
            "first_timing_violation": timing_match.group(0) if timing_match else None,
            "first_unknown_event_row": first_unknown,
            "fatal_marker": fatal_match.group(0) if fatal_match else None,
            "r6_marker": r6_match.group(0) if r6_match else None,
        },
        "sdf_annotation": {
            "completed": "SDF annotation completed" in compile_text,
            "total_errors_zero": "Total errors: 0" in compile_text,
            "total_warnings_line": next((line.strip() for line in compile_text.splitlines() if "Total warnings:" in line), None),
        },
        "evidence_boundary": "This is gate-timed mapped-controller plus SDF plus transistor sensor evidence, not full-transistor controller SPICE.",
        "rerun_performed_after_failure": False,
        "c4_started": False,
        "c5_started": False,
        "c6_started": False,
        "run_files": {
            "compile_log": {"path": str(compile_log), "sha256": hashlib.sha256(compile_log.read_bytes()).hexdigest()},
            "run_log": {"path": str(run_log), "sha256": hashlib.sha256(run_log.read_bytes()).hexdigest()},
            "timing_events": {"path": str(event_csv), "sha256": hashlib.sha256(event_csv.read_bytes()).hexdigest()},
        },
        "disposition": "Per C3 failure rule, preserve the first failing run and stop. Do not run 1.10 V and do not alter calibration algorithm or sensor architecture in this plan.",
    }
    output = run.parent.parent / "reports" / "timing_composed_0p80_failure.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
