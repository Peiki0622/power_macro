#!/usr/bin/env python3
"""Render, freeze, and audit the three RF6 transistor-sensor scenarios.

The established Phase-1 v2 bridge renderer already owns the frozen sensor
topology, HSPICE measures, physical ``dff_ck`` checks, and Q classification
rules.  This wrapper deliberately reuses that renderer rather than copying
or modifying the sensor circuit.  It redirects every output to
``controller/refrequency/hspice`` and substitutes only the newly generated
RF4 contracts.

HSPICE execution itself is intentionally performed by the companion remote
shell script.  Keeping render/freeze/audit separate prevents a deck from being
changed after any of the three electrical results is observed.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


# ``controller/refrequency/scripts`` -> controller root.  All historical
# inputs remain outside the RF6 output root and are read only by the legacy
# renderer.
CONTROLLER_ROOT = Path(__file__).resolve().parents[2]
REFREQUENCY_ROOT = CONTROLLER_ROOT / "refrequency"
CONTRACT_ROOT = REFREQUENCY_ROOT / "timing_contract"
HSPICE_ROOT = REFREQUENCY_ROOT / "hspice"
LEGACY_RUNNER = CONTROLLER_ROOT / "analysis" / "cycle_protocol_event_order_v2" / "run_cycle_bridge_event_order_v2.py"
VOLTAGES = (("0p80", 0.80), ("0p95", 0.95), ("1p10", 1.10))

# These are the three stale absolute paths emitted by the established dynamic
# deck renderer.  They are infrastructure locations only: none is a timing
# number, a PWL event, an instance, or a sensor topology definition.  The
# replacement paths were checked readably on the mandated host before this
# list was added.  Keeping the mapping explicit (rather than using a broad
# string rewrite) makes the retry reviewable and prevents accidental changes
# to similarly named circuit content.
STALE_TO_HOST_PATH = {
    "/home/zhupl25/chiplet_side_channel/chiplet_gds_data/chiplets/FIR/syn/runs/fir_smic40ll_tt_1310ps_spice_20260722_r1/spice/sc9mc_logic0040ll_base_rvt_c40.hspice.cdl": "/home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/cdl/sc9mc_logic0040ll_base_rvt_c40.cdl",
    "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/cdl/sc9mc_logic0040ll_base_lvt_c40.cdl": "/home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/cdl/sc9mc_logic0040ll_base_lvt_c40.cdl",
    "/host/data/libtech/SMIC_40LL/PDK/SPDK40LL_1125_2TM_OA_CDS_V1.4/smic40ll_1125_2tm_oa_cds_1P7M_2012_10_11_v1.4/models/hspice/l0040ll_v1p4_1r.lib": "/home/yangz/virtuoso/SMIC40TXRX/smic40ll_1125_2tm_oa_cds_1P9M_2012_10_11_v1.4/models/hspice/l0040ll_v1p4_1r.lib",
}


def sha256_file(path):
    """Return a stable SHA-256 for a frozen deck or generated run artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Read a required JSON object and fail clearly on malformed evidence."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path, value):
    """Write deterministic machine-readable evidence below RF6 only."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_legacy_renderer(use_infrastructure_retry=False):
    """Load the accepted renderer, then redirect its mutable output globals.

    The legacy module is imported by file path so the repository does not need
    package installation.  Only the contract and output-routing functions are
    replaced; its sensor/deck rendering and physical acceptance logic remain
    exactly the established code.
    """

    spec = importlib.util.spec_from_file_location("ftc_phase1_v2_renderer", str(LEGACY_RUNNER))
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load established Phase-1 renderer")
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)

    def contract_path(voltage):
        return CONTRACT_ROOT / "cycle_path_refreq_{}_contract.json".format(voltage)

    def scenario_dir(voltage):
        """Route physical result reads to the explicitly selected evidence set."""

        directory = HSPICE_ROOT / "cycle_path_refreq_{}".format(voltage)
        # The original decks and their failed logs remain at the scenario root.
        # Only the evaluator for a declared infrastructure retry descends into
        # its child directory, so a failed original run can never be hidden.
        if use_infrastructure_retry:
            directory = directory / "infrastructure_retry"
        return directory

    renderer.contract_path = contract_path
    renderer.scenario_dir = scenario_dir
    renderer.RUN_ROOT = HSPICE_ROOT
    renderer.SCENARIO_NAMES = tuple("cycle_path_refreq_{}".format(voltage) for voltage, _ in VOLTAGES)
    renderer.VOLTAGES = VOLTAGES
    return renderer


def render_and_freeze():
    """Render all three new decks before any remote HSPICE execution starts."""

    if (HSPICE_ROOT / "summary.json").exists():
        raise RuntimeError("RF6 already has aggregate evidence; refusing deck re-render")
    renderer = load_legacy_renderer()
    manifests = []
    for voltage, vdd in VOLTAGES:
        manifest = renderer.render_one(voltage, vdd)
        # The reused renderer labels its historical mode ``cycle_path_v2``.
        # Rename only the new task-owned metadata so RF6 evidence cannot be
        # mistaken for a historical Phase-1 result; the deck bytes are intact.
        manifest["scenario"] = "cycle_path_refreq_{}".format(voltage)
        directory = HSPICE_ROOT / "cycle_path_refreq_{}".format(voltage)
        write_json(directory / "render_manifest.json", manifest)
        write_json(directory / "scenario_acceptance.json", {
            "schema_version": 1,
            "scenario": manifest["scenario"],
            "decision": "NOT_RUN",
            "simulator_invoked": False,
        })
        manifests.append(manifest)
    freeze = {
        "schema_version": 1,
        "decision": "Re-Frequency HSPICE Deck Freeze = GO",
        "scenario_budget": 3,
        "scenario_order": ["cycle_path_refreq_{}".format(voltage) for voltage, _ in VOLTAGES],
        "contracts_and_decks": manifests,
        "single_clock_period_ns": read_json(CONTRACT_ROOT / "cycle_timing_contract_refrequency.json")["period_ns"],
        "single_common_template": read_json(CONTRACT_ROOT / "cycle_timing_contract_refrequency.json")["local_probe_action_cycles"],
        "simulator_invoked": False,
    }
    write_json(HSPICE_ROOT / "pre_run_freeze.json", freeze)


def verify_frozen_inputs():
    """Verify every deck and contract hash before accepting remote results."""

    freeze = read_json(HSPICE_ROOT / "pre_run_freeze.json")
    if freeze.get("decision") != "Re-Frequency HSPICE Deck Freeze = GO":
        raise ValueError("RF6 deck freeze is not GO")
    if freeze.get("scenario_budget") != 3:
        raise ValueError("RF6 scenario budget is not exactly three")
    entries = {entry["voltage"]: entry for entry in freeze.get("contracts_and_decks", [])}
    if set(entries) != {voltage for voltage, _ in VOLTAGES}:
        raise ValueError("RF6 freeze voltage set is incomplete")
    for voltage, _ in VOLTAGES:
        entry = entries[voltage]
        contract = CONTRACT_ROOT / "cycle_path_refreq_{}_contract.json".format(voltage)
        deck = HSPICE_ROOT / "cycle_path_refreq_{}".format(voltage) / "cycle_bridge_v2.sp"
        if sha256_file(contract) != entry["cycle_contract_sha256"]:
            raise ValueError("RF6 contract changed after freeze: {}".format(voltage))
        if sha256_file(deck) != entry["deck_sha256"]:
            raise ValueError("RF6 deck changed after freeze: {}".format(voltage))


def prepare_infrastructure_retry():
    """Freeze replacement-only retry decks after proving the first failure.

    RF6 permits no voltage-by-voltage timing adaptation.  This helper therefore
    creates all three retry decks before any retry simulation begins and applies
    exactly the same three host-path substitutions to each source deck.  The
    unchanged source-deck hash, changed retry-deck hash, and every individual
    replacement are recorded.  Original failed listings are deliberately not
    moved, edited, or reclassified as electrical results.
    """

    verify_frozen_inputs()
    freeze_path = HSPICE_ROOT / "infrastructure_retry_freeze.json"
    if freeze_path.exists():
        raise RuntimeError("RF6 infrastructure retry is already frozen")
    scenarios = []
    for voltage, _ in VOLTAGES:
        source_dir = HSPICE_ROOT / "cycle_path_refreq_{}".format(voltage)
        source_deck = source_dir / "cycle_bridge_v2.sp"
        source_run = read_json(source_dir / "run_manifest.json")
        source_listing = source_dir / "cycle_bridge_v2.lis"
        if source_run.get("returncode") == 0:
            raise ValueError("successful RF6 source run is not retryable: {}".format(voltage))
        if not source_listing.is_file() or "unable to open file" not in source_listing.read_text(encoding="utf-8", errors="replace"):
            raise ValueError("source failure is not the verified missing-path infrastructure error: {}".format(voltage))

        retry_dir = source_dir / "infrastructure_retry"
        if retry_dir.exists():
            raise RuntimeError("retry directory already exists: {}".format(voltage))
        source_text = source_deck.read_text(encoding="ascii")
        retry_text = source_text
        replacements = []
        for stale_path, host_path in STALE_TO_HOST_PATH.items():
            occurrences = retry_text.count(stale_path)
            if occurrences != 1:
                raise ValueError("expected one stale path in {}: {}".format(voltage, stale_path))
            retry_text = retry_text.replace(stale_path, host_path)
            replacements.append({
                "stale_absolute_path": stale_path,
                "verified_host_path": host_path,
                "occurrences_replaced": occurrences,
            })
        retry_dir.mkdir(parents=True)
        retry_deck = retry_dir / "cycle_bridge_v2.sp"
        retry_deck.write_text(retry_text, encoding="ascii")
        scenarios.append({
            "scenario": "cycle_path_refreq_{}".format(voltage),
            "original_returncode": source_run.get("returncode"),
            "original_deck_sha256": sha256_file(source_deck),
            "retry_deck_sha256": sha256_file(retry_deck),
            "cycle_contract_sha256": sha256_file(CONTRACT_ROOT / "cycle_path_refreq_{}_contract.json".format(voltage)),
            "path_replacements": replacements,
        })
    write_json(freeze_path, {
        "schema_version": 1,
        "decision": "RF6 Infrastructure-Only Retry Deck Freeze = GO",
        "reason": "all three original RF6 HSPICE decks terminated before circuit simulation because inherited absolute library paths were absent on the EDA host",
        "retry_scope": "three verified include/model path substitutions only",
        "clock_period_ns_unchanged": read_json(CONTRACT_ROOT / "cycle_timing_contract_refrequency.json")["period_ns"],
        "common_local_template_unchanged": read_json(CONTRACT_ROOT / "cycle_timing_contract_refrequency.json")["local_probe_action_cycles"],
        "scenarios": scenarios,
        "simulator_invoked": False,
    })


def verify_infrastructure_retry_freeze():
    """Prove retry decks differ from their frozen parents only at library paths."""

    document = read_json(HSPICE_ROOT / "infrastructure_retry_freeze.json")
    if document.get("decision") != "RF6 Infrastructure-Only Retry Deck Freeze = GO":
        raise ValueError("RF6 infrastructure retry freeze is not GO")
    entries = {entry["scenario"]: entry for entry in document.get("scenarios", [])}
    if set(entries) != {"cycle_path_refreq_{}".format(voltage) for voltage, _ in VOLTAGES}:
        raise ValueError("RF6 infrastructure retry must freeze exactly three scenarios")
    for voltage, _ in VOLTAGES:
        scenario = "cycle_path_refreq_{}".format(voltage)
        source_dir = HSPICE_ROOT / scenario
        source_deck = source_dir / "cycle_bridge_v2.sp"
        retry_deck = source_dir / "infrastructure_retry" / "cycle_bridge_v2.sp"
        entry = entries[scenario]
        if sha256_file(source_deck) != entry["original_deck_sha256"]:
            raise ValueError("original RF6 deck drifted after retry freeze: {}".format(voltage))
        if sha256_file(retry_deck) != entry["retry_deck_sha256"]:
            raise ValueError("retry RF6 deck drifted after retry freeze: {}".format(voltage))
        expected = source_deck.read_text(encoding="ascii")
        for replacement in entry["path_replacements"]:
            expected = expected.replace(replacement["stale_absolute_path"], replacement["verified_host_path"])
        if expected != retry_deck.read_text(encoding="ascii"):
            raise ValueError("retry deck contains non-path changes: {}".format(voltage))


def record_remote_runs(use_infrastructure_retry=False):
    """Convert remote HSPICE status files into immutable run manifests.

    The remote script writes only its return code and tool version.  This
    local step verifies that each status belongs to an unchanged frozen deck
    and records hashes for the raw listing/measure files before RF6 audit.
    """

    if use_infrastructure_retry:
        verify_infrastructure_retry_freeze()
    else:
        verify_frozen_inputs()
    for voltage, _ in VOLTAGES:
        directory = HSPICE_ROOT / "cycle_path_refreq_{}".format(voltage)
        if use_infrastructure_retry:
            directory = directory / "infrastructure_retry"
        returncode_path = directory / "hspice_returncode.txt"
        if not returncode_path.is_file():
            raise ValueError("missing remote HSPICE return code: {}".format(voltage))
        returncode = int(returncode_path.read_text(encoding="utf-8").strip())
        output_files = {}
        for name in ("cycle_bridge_v2.lis", "cycle_bridge_v2.mt0", "hspice_command.log", "hspice_returncode.txt"):
            path = directory / name
            if path.is_file():
                output_files[name] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
        write_json(directory / "run_manifest.json", {
            "schema_version": 1,
            "scenario": "cycle_path_refreq_{}".format(voltage),
            "hspice": "/home/soft/synopsys/hspice/P-2019.06-SP2/hspice/linux64/hspice",
            "hspice_version": "captured in cycle_bridge_v2.lis",
            "command": ["hspice", "cycle_bridge_v2.sp", "-o", "cycle_bridge_v2"],
            "returncode": returncode,
            "deck_sha256": sha256_file(directory / "cycle_bridge_v2.sp"),
            "cycle_contract_sha256": sha256_file(CONTRACT_ROOT / "cycle_path_refreq_{}_contract.json".format(voltage)),
            "output_files": output_files,
            "infrastructure_retry": use_infrastructure_retry,
        })


def evaluate(use_infrastructure_retry=False):
    """Run the established physical RF6 audit against the retained results."""

    record_remote_runs(use_infrastructure_retry)
    renderer = load_legacy_renderer(use_infrastructure_retry)
    results = [renderer.evaluate_one(voltage, vdd) for voltage, vdd in VOLTAGES]
    # The reused Phase-1 evaluator reports its historical ``cycle_path_v2``
    # scenario label.  Correct only the task-owned result metadata after the
    # electrical audit: measure values, acceptance checks, and deck contents
    # are already frozen and are not regenerated here.
    for item, (voltage, _) in zip(results, VOLTAGES):
        scenario = "cycle_path_refreq_{}".format(voltage)
        item["scenario"] = scenario
        acceptance_dir = HSPICE_ROOT / scenario
        if use_infrastructure_retry:
            acceptance_dir = acceptance_dir / "infrastructure_retry"
        acceptance = read_json(acceptance_dir / "scenario_acceptance.json")
        acceptance["scenario"] = scenario
        write_json(acceptance_dir / "scenario_acceptance.json", acceptance)
    passed = all(item["decision"].endswith("= GO") for item in results)
    infrastructure_failed = any("hspice_infrastructure_failure" in item["errors"] for item in results)
    summary = {
        "schema_version": 1,
        "decision": "Re-Frequency Transistor Sensor Protocol = GO" if passed else ("RF6 Infrastructure Failure = NO-GO" if infrastructure_failed else "Single-Rate Re-Frequency = NO-GO"),
        "scenario_count": 3,
        "results": [{
            "scenario": item["scenario"],
            "decision": item["decision"],
            "errors": item["errors"],
            "final_locked_code": item["final_locked_code"],
            "probe_count": item["probe_count"],
            "config_update_count": item["config_update_count"],
        } for item in results],
        "measurement_evidence_source": "infrastructure_retry" if use_infrastructure_retry else "original_frozen_run",
        "timing_template_changed_after_execution": False,
    }
    write_json(HSPICE_ROOT / "summary.json", summary)
    if not passed:
        raise SystemExit("RF6 single-rate transistor protocol is NO-GO")


def main():
    """Dispatch exactly one RF6 stage; execution remains a remote-only action."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("render", "verify-freeze", "evaluate", "render-infrastructure-retry", "verify-retry-freeze", "evaluate-retry"))
    args = parser.parse_args()
    if args.command == "render":
        render_and_freeze()
    elif args.command == "verify-freeze":
        verify_frozen_inputs()
    elif args.command == "render-infrastructure-retry":
        prepare_infrastructure_retry()
    elif args.command == "verify-retry-freeze":
        verify_infrastructure_retry_freeze()
    elif args.command == "evaluate-retry":
        evaluate(True)
    else:
        evaluate()


if __name__ == "__main__":
    main()
