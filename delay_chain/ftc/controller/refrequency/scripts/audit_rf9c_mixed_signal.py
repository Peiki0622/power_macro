#!/usr/bin/env python3
"""Audit the retained three-voltage RF9C no-SDF XA functional evidence.

RF9C intentionally verifies the corrected transistor bridge and autonomous
algorithm before adding SDF delays.  It is therefore not an SDF timing-check
substitute: RF9B and RF9D own those timing-check gates.  This script is
read-only with respect to raw simulator products and writes one compact gate
record only after all three frozen scenarios complete.
"""

import hashlib
import json
import re
from pathlib import Path


CONTROLLER_ROOT = Path(__file__).resolve().parents[2]
RF_ROOT = CONTROLLER_ROOT / "refrequency"
RUN_ROOT = RF_ROOT / "verification" / "mixed_signal_no_sdf" / "runs"
RESULT_PATH = RF_ROOT / "verification" / "mixed_signal_no_sdf" / "RF9C_AUTONOMOUS_MIXED_SIGNAL.json"
EXPECTATIONS = {
    "0p80": (7, 6, 45, 17, 28),
    "0p95": (4, 6, 36, 14, 22),
    "1p10": (2, 9, 36, 15, 21),
}


def sha256(path):
    """Return a stable evidence hash without changing a simulator artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    """Require all scenario contracts before declaring the RF9C gate GO."""

    results = []
    all_pass = True
    for tag, expected in EXPECTATIONS.items():
        directory = RUN_ROOT / ("rf9_" + tag) / "infrastructure_retry_locale" / "functional_no_sdf"
        compile_log = directory / "compile.log"
        run_log = directory / "run.log"
        returncode = directory / "returncode.txt"
        freeze = directory / "retry_freeze.json"
        missing = [str(path) for path in (compile_log, run_log, returncode, freeze) if not path.is_file()]
        errors = []
        if missing:
            errors.append("missing evidence: " + ", ".join(missing))
            compile_text = ""
            run_text = ""
        else:
            compile_text = compile_log.read_text(encoding="utf-8", errors="replace")
            run_text = run_log.read_text(encoding="utf-8", errors="replace")
            if returncode.read_text(encoding="utf-8").strip() != "0":
                errors.append("simulator return code is not zero")
            if "Started analog simulator for mixed signal simulation" not in run_text:
                errors.append("XA analog simulator start marker missing")
            marker = "R6_PASS supply="
            if marker not in run_text or "R6_FAIL" in run_text:
                errors.append("autonomous bench is not a clean R6_PASS")
            final_pattern = r"operations={ops} configs={cfgs} probes={probes} sclk_edges={probes} samples={probes}/{probes} final=M{m}/F{f}".format(
                ops=expected[2], cfgs=expected[3], probes=expected[4], m=expected[0], f=expected[1])
            if re.search(final_pattern, run_text) is None:
                errors.append("frozen count/final-code marker missing")
            if "monitor_errors count=0" in run_text:
                errors.append("unexpected failure text in monitor output")
            # VCS does not echo its complete invocation in compile.log.  The
            # pre-run retry freeze is therefore the authoritative record for
            # RF9C's two intentionally enabled no-SDF functional-mode flags.
            freeze_document = json.loads(freeze.read_text(encoding="utf-8"))
            mode_flags = freeze_document.get("only_simulator_mode_change", [])
            if sorted(mode_flags) != ["+nospecify", "+notimingcheck"]:
                errors.append("RF9C no-SDF functional mode flags are not recorded in retry freeze")
        result = {
            "scenario": "rf9_" + tag,
            "expected": {"M": expected[0], "F": expected[1], "operations": expected[2], "configs": expected[3], "probes": expected[4]},
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "evidence_sha256": {path.name: sha256(path) for path in (compile_log, run_log, returncode, freeze) if path.is_file()},
        }
        results.append(result)
        all_pass = all_pass and not errors
    report = {
        "schema_version": 1,
        "decision": "Re-Frequency Autonomous Mixed-Signal Function = GO" if all_pass else "Re-Frequency Autonomous Mixed-Signal Function = NO-GO",
        "clock_period_ns": 2.5,
        "configuration": "mapped controller + corrected XA bridge + frozen transistor sensor + no SDF",
        "timing_check_scope": "RF9C intentionally uses +nospecify/+notimingcheck; full SDF timing checks are independently required by RF9B and RF9D",
        "sensor_or_algorithm_modified": False,
        "results": results,
    }
    RESULT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not all_pass:
        raise SystemExit("RF9C mixed-signal gate failed")


if __name__ == "__main__":
    main()
