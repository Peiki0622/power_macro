#!/usr/bin/env python3
"""Publish the RF7 active timing handoff only after RF6 electrical closure.

The historical Phase-1 handoff is read and hashed but never edited.  This
script consumes the frozen RF4 contract and the retained three-voltage RF6
evidence, then writes the one task-owned JSON document that active RTL timing
constants must match.
"""

import hashlib
import json
from pathlib import Path


# Script-relative paths ensure this publisher cannot write into a historical
# Phase-1 directory when started from an arbitrary working directory.
CONTROLLER_ROOT = Path(__file__).resolve().parents[2]
REFREQUENCY_ROOT = CONTROLLER_ROOT / "refrequency"
CONTRACT_ROOT = REFREQUENCY_ROOT / "timing_contract"
HSPICE_ROOT = REFREQUENCY_ROOT / "hspice"
HANDOFF_PATH = REFREQUENCY_ROOT / "handoff" / "phase1_timing_handoff_refrequency.json"
HISTORICAL_HANDOFF = CONTROLLER_ROOT / "spec" / "phase1_timing_handoff.json"
EXACT_EVENT_ORDER = CONTROLLER_ROOT / "analysis" / "cycle_protocol_event_order_v2" / "exact_path_event_order_audit.json"
VOLTAGES = ("0p80", "0p95", "1p10")


def sha256_file(path):
    """Return a content hash used to bind a handoff to immutable evidence."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Load a required object and diagnose malformed evidence precisely."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def relative(path):
    """Express all evidence locations relative to the controller root."""

    return str(path.relative_to(CONTROLLER_ROOT))


def main():
    """Validate RF6 success and write the immutable-input RF7 handoff."""

    if HANDOFF_PATH.exists():
        raise RuntimeError("RF7 handoff already exists; refusing to overwrite it")
    contract_path = CONTRACT_ROOT / "cycle_timing_contract_refrequency.json"
    contract = read_json(contract_path)
    rf6_summary_path = HSPICE_ROOT / "summary.json"
    rf6_summary = read_json(rf6_summary_path)
    if rf6_summary.get("decision") != "Re-Frequency Transistor Sensor Protocol = GO":
        raise ValueError("RF7 requires an RF6 three-voltage GO result")
    if rf6_summary.get("measurement_evidence_source") != "infrastructure_retry":
        raise ValueError("RF7 must identify the retained RF6 evidence source")
    if contract.get("cal_clk_hz") != 400000000 or contract.get("period_ns") != 2.5:
        raise ValueError("RF7 contract is not the selected 400 MHz / 2.5 ns clock")
    # RF4's contract names this implementation field ``config_settle_cycles``;
    # RF7 exposes the more explicit handoff name ``configuration_settle_cycles``.
    if contract.get("config_settle_cycles") != 1:
        raise ValueError("RF7 contract does not carry the derived one-cycle settle")

    expected_cycles = {
        "RESET_RELEASE": 0, "S_CLK_RISE": 1, "Q_SAMPLE_1": 2,
        "Q_SAMPLE_2": 3, "RESET_ASSERT": 4, "S_CLK_FALL": 5,
        "RECOVERY_DONE": 7,
    }
    if contract.get("local_probe_action_cycles") != expected_cycles:
        raise ValueError("RF7 refuses an unreviewed local event schedule")

    scenario_evidence = []
    summary_by_scenario = {entry["scenario"]: entry for entry in rf6_summary.get("results", [])}
    for voltage in VOLTAGES:
        scenario = "cycle_path_refreq_{}".format(voltage)
        directory = HSPICE_ROOT / scenario / "infrastructure_retry"
        acceptance = directory / "scenario_acceptance.json"
        run_manifest = directory / "run_manifest.json"
        # This HSPICE release emits measure-form 3 output as CSV.  The full
        # suffix is intentional: accepting a guessed ``.mt0`` name would make
        # the handoff omit the exact electrical measurements it claims to bind.
        measurement = directory / "cycle_bridge_v2.mt0.csv"
        retry_deck = directory / "cycle_bridge_v2.sp"
        result = summary_by_scenario.get(scenario, {})
        if not all(path.is_file() for path in (acceptance, run_manifest, measurement, retry_deck)):
            raise ValueError("RF7 missing retained RF6 evidence: {}".format(scenario))
        if result.get("decision", "").endswith("= GO") is False:
            raise ValueError("RF7 scenario is not electrically accepted: {}".format(scenario))
        scenario_evidence.append({
            "scenario": scenario,
            "retry_deck": relative(retry_deck),
            "retry_deck_sha256": sha256_file(retry_deck),
            "hspice_measurement": relative(measurement),
            "hspice_measurement_sha256": sha256_file(measurement),
            "hspice_run_manifest": relative(run_manifest),
            "hspice_run_manifest_sha256": sha256_file(run_manifest),
            "acceptance": relative(acceptance),
            "acceptance_sha256": sha256_file(acceptance),
        })

    handoff = {
        "schema_version": 1,
        "decision": "Re-Frequency Controller Timing Handoff = GO",
        "active_controller_timing_source": True,
        "supersession": {
            "historical_1ghz_handoff": {
                "path": relative(HISTORICAL_HANDOFF),
                "sha256": sha256_file(HISTORICAL_HANDOFF),
                "status": "retained_historical_evidence_superseded_for_active_rtl_timing",
            },
            "new_refrequency_handoff": "active_controller_timing_source",
        },
        "cal_clk_hz": contract["cal_clk_hz"],
        "period_ns": contract["period_ns"],
        "configuration_settle_cycles": contract["config_settle_cycles"],
        "local_probe_action_cycles": expected_cycles,
        "probe_sclk_high_cycles": expected_cycles["S_CLK_FALL"] - expected_cycles["S_CLK_RISE"],
        "timing_contract": {
            "path": relative(contract_path),
            "sha256": sha256_file(contract_path),
        },
        "source_exact_event_order": {
            "path": relative(EXACT_EVENT_ORDER),
            "sha256": sha256_file(EXACT_EVENT_ORDER),
        },
        "rf6_summary": {
            "path": relative(rf6_summary_path),
            "sha256": sha256_file(rf6_summary_path),
        },
        "rf6_scenario_evidence": scenario_evidence,
        "rtl_drift_prevention": "refrequency/scripts/audit_rtl_timing_contract.py must report GO before synthesis",
        "algorithm_change": "none; only timing quantization and configuration settle duration changed",
    }
    HANDOFF_PATH.parent.mkdir(parents=True, exist_ok=True)
    HANDOFF_PATH.write_text(json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
