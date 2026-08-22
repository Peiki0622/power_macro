#!/usr/bin/env python3
"""Audit the complete three-voltage RF9D SDF/XA timing-composed evidence.

RF9D is deliberately the first re-frequency gate that combines all timing
elements at once: the mapped controller, its SDF, enabled standard-cell
timing checks, the corrected XA boundary, the frozen transistor sensor, and
the sensor's real q_final feedback.  This script never changes those inputs
or raw simulator outputs.  It reads the three task-owned run directories and
writes one compact, hash-addressed GO/NO-GO record only after checking every
required RF9D acceptance item.
"""

import csv
import hashlib
import json
import re
from pathlib import Path


# All paths are derived from this file so that the audit is reproducible from
# any current working directory and does not rely on a host-specific shell
# variable.  The run root contains only RF9D's three frozen voltage scenarios.
CONTROLLER_ROOT = Path(__file__).resolve().parents[2]
RF_ROOT = CONTROLLER_ROOT / "refrequency"
RUN_ROOT = RF_ROOT / "verification" / "mixed_signal_sdf" / "runs"
RESULT_PATH = RF_ROOT / "verification" / "mixed_signal_sdf" / "RF9D_TIMING_COMPOSED_MIXED_SIGNAL.json"
PRE_RUN_MANIFEST = RF_ROOT / "verification" / "mixed_signal_sdf" / "pre_run_manifest.json"
SENSOR_PROTOCOL_SUMMARY = RF_ROOT / "hspice" / "summary.json"

# The expected trajectories are frozen by RF6/RF9A/RF9B/RF9C.  Their tuple
# fields are M code, F code, operation count, configuration count, and probe
# count respectively.  No value varies with any simulator result at audit
# time, which prevents a passing trace from redefining its own target.
EXPECTATIONS = {
    "0p80": (7, 6, 45, 17, 28),
    "0p95": (4, 6, 36, 14, 22),
    "1p10": (2, 9, 36, 15, 21),
}


def sha256(path):
    """Return an evidence hash without modifying the simulator artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv_rows(path, errors):
    """Load event rows and report malformed evidence instead of throwing it away.

    The monitor writes one row for each physical/event boundary after SDF.
    Keeping each row as a dictionary lets the checks below cite only recorded
    signals; no periodic waveform sampling is used to infer edge ordering.
    """

    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, csv.Error) as exc:
        errors.append("cannot read timing event CSV: {}".format(exc))
        return []
    if not rows:
        errors.append("timing event CSV has no event rows")
        return []
    for index, row in enumerate(rows):
        try:
            row["_time"] = float(row["time_ns"])
        except (KeyError, TypeError, ValueError):
            errors.append("timing event CSV row {} has invalid time_ns".format(index + 2))
            return []
    return rows


def rows_for(rows, event):
    """Return rows for one explicit monitor event in their recorded order."""

    return [row for row in rows if row.get("event") == event]


def is_known_bit(value):
    """Accept only a fully resolved scalar digital value from an event row."""

    return value in ("0", "1")


def check_trace(rows, expected, errors):
    """Check RF9D's post-SDF physical event contract for one voltage.

    Each probe must start, release reset, generate exactly one controller
    S_CLK rising edge into the transistor-sensor boundary, collect two
    resolved and equal q_final samples, reassert reset, and then return S_CLK
    low.  The explicit SCLK_FALL extension is observation-only and makes the
    reset-before-return proof an event-order assertion rather than an
    assumption based on generated clock cycles.
    """

    probe_count = expected[4]
    # The monitor also records harmless initialization transitions before POR.
    # RF9D's acceptance is about active calibration transactions, exactly as
    # the autonomous bench's edge counters are scoped by cal_busy.
    probes = [row for row in rows_for(rows, "PROBE_START") if row.get("cal_busy") == "1"]
    rises = [row for row in rows_for(rows, "SCLK_RISE") if row.get("cal_busy") == "1"]
    falls = [row for row in rows_for(rows, "SCLK_FALL") if row.get("cal_busy") == "1"]
    sample1 = [row for row in rows_for(rows, "Q_SAMPLE_1") if row.get("cal_busy") == "1"]
    sample2 = [row for row in rows_for(rows, "Q_SAMPLE_2") if row.get("cal_busy") == "1"]
    configs = [row for row in rows_for(rows, "CONFIG_UPDATE") if row.get("cal_busy") == "1"]
    therm_changes = rows_for(rows, "THERM_CHANGE")
    reset_changes = rows_for(rows, "RESET_CHANGE")
    terminals = rows_for(rows, "TERMINAL")

    # Exact counts are required by RF9D.  The testbench independently checks
    # these counters; this second check ties the result to post-SDF timestamps.
    required_counts = {
        "PROBE_START": (len(probes), probe_count),
        "SCLK_RISE": (len(rises), probe_count),
        "SCLK_FALL": (len(falls), probe_count),
        "Q_SAMPLE_1": (len(sample1), probe_count),
        "Q_SAMPLE_2": (len(sample2), probe_count),
        "CONFIG_UPDATE": (len(configs), expected[3]),
    }
    for name, pair in required_counts.items():
        if pair[0] != pair[1]:
            errors.append("{} count {} does not equal expected {}".format(name, pair[0], pair[1]))

    # The original bench already asserts one-bit thermometer movement inside
    # its active window.  The bound trace additionally confirms its observable
    # transaction count agrees with configuration updates after SDF delays.
    active_therm_changes = [row for row in therm_changes if row.get("cal_busy") == "1"]
    if len(active_therm_changes) != expected[3]:
        errors.append("active THERM_CHANGE count {} does not equal config count {}".format(
            len(active_therm_changes), expected[3]))

    # No event that constitutes an active transaction may contain an unknown
    # controller/sensor status.  Initial power-up rows are intentionally not
    # judged here, since they precede POR and do not represent notifier fallout.
    active_events = probes + rises + falls + sample1 + sample2 + configs + terminals
    for row in active_events:
        for field in ("cal_busy", "cal_done", "cal_fail", "lock_valid", "reset", "sclk"):
            value = row.get(field, "")
            if not is_known_bit(value):
                errors.append("{} at {:.6f} ns has unresolved {}={}".format(
                    row.get("event"), row.get("_time", -1.0), field, value))
                break

    # Pair q_final at the physical sample events.  Equality is the redundant
    # classification requirement: a disagreement is an aperture/classification
    # failure even if a later terminal code happens to be correct.
    for index in range(min(len(sample1), len(sample2))):
        first = sample1[index]
        second = sample2[index]
        q_first = first.get("q_final", "")
        q_second = second.get("q_final", "")
        if not is_known_bit(q_first) or not is_known_bit(q_second):
            errors.append("probe {} has unresolved q_final sample pair {}/{}".format(
                index + 1, q_first, q_second))
        elif q_first != q_second:
            errors.append("probe {} q_final sample pair disagrees: {}/{}".format(
                index + 1, q_first, q_second))

    # One loop correlates the i-th records of each event class.  Explicit
    # timestamps and reset values provide a physical ordering proof across the
    # mapped controller, SDF, and XA boundary for every individual probe.
    for index in range(min(len(probes), len(rises), len(falls), len(sample1), len(sample2))):
        start = probes[index]
        rise = rises[index]
        first = sample1[index]
        second = sample2[index]
        fall = falls[index]
        if not (start["_time"] < rise["_time"] < first["_time"] < second["_time"] < fall["_time"]):
            errors.append("probe {} event order is not start<rise<sample1<sample2<fall".format(index + 1))
        if rise.get("reset") != "0":
            errors.append("probe {} SCLK rise did not occur with reset released".format(index + 1))
        if fall.get("reset") != "1":
            errors.append("probe {} SCLK fall did not occur with reset asserted".format(index + 1))
        released = any(change.get("reset") == "0" and start["_time"] <= change["_time"] < rise["_time"]
                       for change in reset_changes)
        reasserted = any(change.get("reset") == "1" and second["_time"] < change["_time"] < fall["_time"]
                         for change in reset_changes)
        if not released:
            errors.append("probe {} has no recorded reset release before SCLK rise".format(index + 1))
        if not reasserted:
            errors.append("probe {} has no recorded reset reassertion before SCLK fall".format(index + 1))

    # A terminal row is emitted by a real cal_done, cal_fail, or lock_valid
    # transition.  At least one must show the required final status; the bench
    # itself then observes additional clock edges and rejects any later M/F
    # movement before it prints R6_PASS.
    terminal_ok = any(row.get("cal_done") == "1" and row.get("lock_valid") == "1" and
                      row.get("cal_fail") == "0" for row in terminals)
    if not terminal_ok:
        errors.append("no terminal event has cal_done=1, lock_valid=1, cal_fail=0")

    return {
        "probe_start_count": len(probes),
        "sclk_rise_count": len(rises),
        "sclk_fall_count": len(falls),
        "q_sample_1_count": len(sample1),
        "q_sample_2_count": len(sample2),
        "config_update_count": len(configs),
        "active_therm_change_count": len(active_therm_changes),
        "terminal_event_count": len(terminals),
    }


def check_sensor_protocol_summary(expected, errors):
    """Tie each dynamic S_CLK edge to the frozen RF6 transistor CK proof."""

    if not SENSOR_PROTOCOL_SUMMARY.is_file():
        errors.append("RF6 transistor sensor protocol summary is missing")
        return False
    try:
        summary = json.loads(SENSOR_PROTOCOL_SUMMARY.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append("cannot parse RF6 transistor sensor protocol summary: {}".format(exc))
        return False
    if summary.get("decision") != "Re-Frequency Transistor Sensor Protocol = GO":
        errors.append("RF6 transistor sensor protocol summary is not GO")
        return False
    expected_by_scenario = {
        "cycle_path_refreq_" + tag: values for tag, values in EXPECTATIONS.items()
    }
    results = {entry.get("scenario"): entry for entry in summary.get("results", [])}
    for scenario, values in expected_by_scenario.items():
        record = results.get(scenario, {})
        final_code = record.get("final_locked_code", {})
        if (record.get("config_update_count") != values[3] or
                record.get("probe_count") != values[4] or
                final_code.get("M") != values[0] or final_code.get("F") != values[1]):
            errors.append("RF6 frozen sensor contract mismatch for {}".format(scenario))
    return True


def audit_scenario(tag, expected, shared_errors):
    """Audit one voltage without allowing a single missing file to hide others."""

    directory = RUN_ROOT / ("rf9_" + tag)
    compile_log = directory / "compile.log"
    run_log = directory / "run.log"
    returncode = directory / "returncode.txt"
    events = directory / "timing_events.csv"
    extension_freeze = directory / "rf9d_observation_extension_freeze.json"
    evidence_paths = (compile_log, run_log, returncode, events, extension_freeze)
    errors = []
    missing = [str(path) for path in evidence_paths if not path.is_file()]
    trace_summary = {}

    if missing:
        errors.append("missing evidence: " + ", ".join(missing))
    else:
        compile_text = compile_log.read_text(encoding="utf-8", errors="replace")
        run_text = run_log.read_text(encoding="utf-8", errors="replace")
        if returncode.read_text(encoding="utf-8").strip() != "0":
            errors.append("simulator return code is not zero")
        if "Started analog simulator for mixed signal simulation" not in run_text:
            errors.append("XA analog simulator start marker missing")
        if "***    SDF annotation completed:" not in compile_text or "Total errors: 0" not in compile_text:
            errors.append("SDF annotation did not complete with zero annotation errors")
        if "Need timing check option +neg_tchk" in compile_text:
            errors.append("negative timing checks were not enabled")
        if "SDF Error:" in compile_text:
            errors.append("SDF annotation reported an error")
        for forbidden in ("+nospecify", "+notimingcheck"):
            if forbidden in compile_text or forbidden in run_text:
                errors.append("forbidden timing-check bypass {} appears in simulator evidence".format(forbidden))
        for marker in ("Timing violation", "TIMING VIOLATION", "R6_FAIL", "notifier", "Notifier"):
            if marker in run_text:
                errors.append("run log contains failure marker: {}".format(marker))
        final_pattern = (
            r"R6_PASS supply=.* operations={ops} configs={cfgs} probes={probes} "
            r"sclk_edges={probes} samples={probes}/{probes} final=M{m}/F{f}"
        ).format(ops=expected[2], cfgs=expected[3], probes=expected[4], m=expected[0], f=expected[1])
        if re.search(final_pattern, run_text) is None:
            errors.append("R6_PASS exact count/final-code marker missing")
        rows = read_csv_rows(events, errors)
        if rows:
            trace_summary = check_trace(rows, expected, errors)
        try:
            extension = json.loads(extension_freeze.read_text(encoding="utf-8"))
            if extension.get("observation_only") is not True or extension.get("only_added_event") != "SCLK_FALL post-SDF timestamp":
                errors.append("RF9D observation extension is not the frozen input-only SCLK_FALL monitor")
        except (OSError, ValueError) as exc:
            errors.append("cannot parse RF9D observation extension freeze: {}".format(exc))

    # A shared RF6 summary is independently checked once by main; repeat its
    # boolean here only as a scenario-visible item in the final evidence JSON.
    result = {
        "scenario": "rf9_" + tag,
        "expected": {"M": expected[0], "F": expected[1], "operations": expected[2],
                     "configs": expected[3], "probes": expected[4]},
        "post_sdf_event_summary": trace_summary,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "evidence_sha256": {path.name: sha256(path) for path in evidence_paths if path.is_file()},
    }
    shared_errors.extend(errors)
    return result


def main():
    """Write RF9D's single gate record and exit nonzero on any failed scenario."""

    shared_errors = []
    if not PRE_RUN_MANIFEST.is_file():
        shared_errors.append("RF9D pre-run manifest is missing")
    else:
        manifest = json.loads(PRE_RUN_MANIFEST.read_text(encoding="utf-8"))
        if (manifest.get("clock_period_ns") != 2.5 or manifest.get("sdf_enabled") is not True or
                manifest.get("timing_checks_disabled") is not False):
            shared_errors.append("RF9D pre-run manifest does not preserve the frozen 2.5 ns SDF timing-check configuration")

    sensor_protocol_ok = check_sensor_protocol_summary(EXPECTATIONS, shared_errors)
    results = [audit_scenario(tag, expected, shared_errors) for tag, expected in EXPECTATIONS.items()]
    all_pass = not shared_errors and all(result["status"] == "PASS" for result in results)
    report = {
        "schema_version": 1,
        "decision": "Re-Frequency Timing-Composed Startup Calibration = GO" if all_pass else "Re-Frequency Timing-Composed Startup Calibration = NO-GO",
        "clock_period_ns": 2.5,
        "configuration": "mapped controller + refrequency SDF + full standard-cell timing checks (+neg_tchk) + corrected XA bridge + frozen transistor sensor + real q_final feedback",
        "timing_check_bypass": {"nospecify": False, "notimingcheck": False},
        "sensor_or_algorithm_modified": False,
        "rf6_frozen_transistor_sensor_contract_go": sensor_protocol_ok,
        "shared_errors": shared_errors,
        "results": results,
    }
    RESULT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not all_pass:
        raise SystemExit("RF9D timing-composed mixed-signal gate failed")


if __name__ == "__main__":
    main()
