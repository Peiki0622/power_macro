#!/usr/bin/env python3
"""Publish the only Phase-1 timing handoff that later FTC RTL may consume.

The correction plan prohibits entering controller RTL phases until the three
pre-frozen v2 HSPICE scenarios are electrically accepted.  This publisher is
therefore intentionally a read/validate/write utility: it does not render a
deck, invoke HSPICE, alter a timing contract, or regenerate a historical v1
artefact.  Its one output is the controller-spec handoff JSON.
"""

import hashlib
import json
import sys
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = Path(__file__).resolve().parent
RUN_ROOT = PROTOCOL / "hspice"
SPEC_DIR = FTC_ROOT / "controller" / "spec"
HANDOFF = SPEC_DIR / "phase1_timing_handoff.json"
VOLTAGES = ("0p80", "0p95", "1p10")
EXPECTED_FINAL_CODES = {
    "0p80": {"M": 7, "F": 6},
    "0p95": {"M": 4, "F": 6},
    "1p10": {"M": 2, "F": 9},
}


def read_json(path):
    """Read one non-empty JSON object and fail before producing a handoff."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def sha256_file(path):
    """Hash an input or result file without copying it into the handoff."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    """Write stable, machine-readable spec evidence after all checks pass."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def relative(path):
    """Keep published references workspace-relative and portable across hosts."""

    return str(path.relative_to(FTC_ROOT))


def validate_and_build():
    """Validate all R0-R4 boundaries and construct, but do not yet write, R5.

    The returned data contains only hashes and stable timing metadata.  Raw
    HSPICE logs and measurements remain in their single task-owned run tree,
    avoiding evidence duplication and avoiding intermediate-file scatter.
    """

    event_audit_path = PROTOCOL / "exact_path_event_order_audit.json"
    source_manifest_path = PROTOCOL / "source_manifest.json"
    timing_path = PROTOCOL / "cycle_timing_contract_v2.json"
    freeze_path = RUN_ROOT / "pre_run_freeze.json"
    summary_path = RUN_ROOT / "summary.json"
    event_audit = read_json(event_audit_path)
    sources = read_json(source_manifest_path)
    timing = read_json(timing_path)
    freeze = read_json(freeze_path)
    summary = read_json(summary_path)

    if event_audit.get("decision") != "Exact-Path Event Order Extraction = GO":
        raise ValueError("R0 event-order audit is not GO")
    if timing.get("decision") != "Event-Ordered Cycle Schedule Construction = GO":
        raise ValueError("R1 cycle timing contract is not GO")
    if freeze.get("decision") != "Event-Ordered HSPICE Deck Freeze = GO":
        raise ValueError("R3 deck freeze is not GO")
    if summary.get("decision") != "Cycle-Quantized Startup Protocol = GO":
        raise ValueError("R4 aggregate HSPICE decision is not GO")
    if summary.get("scenario_budget") != 3 or summary.get("scenario_count") != 3:
        raise ValueError("R4 does not contain the required three scenarios")

    source_hashes = {
        item["name"]: item["sha256"]
        for item in sources.get("inputs", [])
        if item["name"].startswith("exact_")
    }
    if {"exact_final_acceptance", "exact_schedule_0p80", "exact_schedule_0p95", "exact_schedule_1p10"} - set(source_hashes):
        raise ValueError("source exact-path acceptance hashes are incomplete")

    frozen = {item["voltage"]: item for item in freeze.get("contracts_and_decks", [])}
    # The configured EDA Python is 3.6, which predates ``str.removeprefix``.
    # Keep the required scenario naming validation explicit and portable.
    summarized = {}
    for item in summary.get("results", []):
        scenario = item.get("scenario", "")
        prefix = "cycle_path_v2_"
        if not scenario.startswith(prefix):
            raise ValueError("R4 summary contains a non-v2 scenario name")
        summarized[scenario[len(prefix):]] = item
    if set(frozen) != set(VOLTAGES) or set(summarized) != set(VOLTAGES):
        raise ValueError("frozen and evaluated voltage sets must both be exactly three")

    successful = []
    for voltage in VOLTAGES:
        scenario_dir = RUN_ROOT / "cycle_path_v2_{}".format(voltage)
        contract_path = PROTOCOL / "cycle_path_v2_{}_contract.json".format(voltage)
        deck_path = scenario_dir / "cycle_bridge_v2.sp"
        acceptance_path = scenario_dir / "scenario_acceptance.json"
        run_path = scenario_dir / "run_manifest.json"
        acceptance = read_json(acceptance_path)
        run = read_json(run_path)
        frozen_item = frozen[voltage]
        summary_item = summarized[voltage]
        if acceptance.get("decision") != "Cycle-Quantized Startup Protocol = GO":
            raise ValueError("{} scenario acceptance is not GO".format(voltage))
        if acceptance.get("final_locked_code") != EXPECTED_FINAL_CODES[voltage]:
            raise ValueError("{} final code differs from the frozen trajectory".format(voltage))
        if run.get("returncode") != 0:
            raise ValueError("{} HSPICE process did not complete normally".format(voltage))
        contract_hash = sha256_file(contract_path)
        deck_hash = sha256_file(deck_path)
        result_hash = sha256_file(acceptance_path)
        if contract_hash != frozen_item.get("cycle_contract_sha256"):
            raise ValueError("{} cycle contract hash changed after R3".format(voltage))
        if deck_hash != frozen_item.get("deck_sha256"):
            raise ValueError("{} deck hash changed after R3".format(voltage))
        if summary_item.get("cycle_contract_sha256") != contract_hash or summary_item.get("deck_sha256") != deck_hash:
            raise ValueError("{} R4 summary hash disagrees with retained artefacts".format(voltage))
        successful.append({
            "scenario": "cycle_path_v2_{}".format(voltage),
            "voltage": voltage,
            "cycle_contract": relative(contract_path),
            "cycle_contract_sha256": contract_hash,
            "deck": relative(deck_path),
            "deck_sha256": deck_hash,
            "scenario_acceptance": relative(acceptance_path),
            "scenario_acceptance_sha256": result_hash,
            "hspice_version": run.get("hspice_version"),
        })

    timing_values = timing.get("timing", {})
    action_cycles = timing_values.get("local_probe_action_cycles", {})
    if timing_values.get("cal_clk_hz") != 1_000_000_000:
        raise ValueError("v2 timing contract does not retain the fixed 1 GHz clock")
    required_actions = {"RESET_RELEASE", "S_CLK_RISE", "Q_SAMPLE_1", "Q_SAMPLE_2", "RESET_ASSERT", "S_CLK_FALL", "RECOVERY_DONE"}
    if set(action_cycles) != required_actions:
        raise ValueError("v2 timing contract is missing a local probe action")

    return {
        "schema_version": 1,
        # Keep the exact decision string required by the correction plan.
        "decision": "Cycle-Quantized Startup Protocol = GO",
        "handoff_gate": "Corrected Phase 1 Timing Handoff = GO",
        "cal_clk_hz": 1_000_000_000,
        "local_probe_event_cycles": action_cycles,
        "configuration_settle_cycles": timing_values.get("config_settle_cycles"),
        "sclk_high_cycles": timing_values.get("sclk_high_cycles"),
        "source_exact_path_acceptance_sha256": source_hashes,
        "corrected_event_order_contract": {
            "path": relative(event_audit_path),
            "sha256": sha256_file(event_audit_path),
        },
        "corrected_cycle_timing_contract": {
            "path": relative(timing_path),
            "sha256": sha256_file(timing_path),
        },
        "successful_v2_hspice_scenarios": successful,
        "supersession": {
            "historical_v1_path": "controller/analysis/cycle_protocol/",
            "historical_v1_timing_contract": "controller/analysis/cycle_protocol/cycle_timing_contract.json",
            "statement": "The rejected v1 cycle timing candidate is superseded historical evidence and MUST NOT be consumed by RTL.",
        },
    }


def main():
    """Publish R5 only if all upstream validation gates are still GO."""

    try:
        handoff = validate_and_build()
        write_json(HANDOFF, handoff)
        # Read it back and verify its byte-level references one final time.  A
        # later RTL phase may use this exact file as its timing authority.
        if read_json(HANDOFF) != handoff:
            raise RuntimeError("published handoff readback differs from generated data")
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print("phase1 timing handoff publication failed: {}".format(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
