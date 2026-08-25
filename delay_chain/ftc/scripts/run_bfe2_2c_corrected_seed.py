#!/usr/bin/env python3
"""Run the single plan-authorized B-FE2.2C corrected-seed pair.

B-FE2.2C is deliberately narrower than the historical B-FE2.2 retry.  The
offline B-FE2.2S revision selected one and only one 0.95-V close time after
using measured transparent-latch D-to-Q timing.  This runner therefore has no
close-time argument, no sweep loop, and no second-seed fallback: its only
legal physical cases are the normal and formal L2 supplies at that exact
common requested close.

The old six B-FE2.2 traces remain immutable.  New raw products are placed in a
task-scoped ``corrected_seed_534p525ps`` directory, and the compact manifest
records the complete electrical signature plus deck/.tr0 SHA256 values.  The
runner itself does not analyze Q behavior; that is an independent zero-HSPICE
stage so a simulator result can never silently become a Gate decision.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))

import bfe1_frontend  # noqa: E402  # Frozen 30-tap source, probe labels, and time constants.
import bfe2_latch_load  # noqa: E402  # Frozen 4/0 prefix, XOR bank, latch cells, and supply phases.
import bfe2_real_snapshot  # noqa: E402  # Existing finite-G renderer and topology guard.
import run_dc_sweep  # noqa: E402  # Project-standard HSPICE version/listing validation.


ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch"
SNAPSHOT_ROOT = ANALYSIS_ROOT / "real_snapshot"
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "real_snapshot" / "corrected_seed_534p525ps"
OUTPUT_MANIFEST = SNAPSHOT_ROOT / "BFE2_2C_SCENARIO_MANIFEST.json"
SEED_EVIDENCE = SNAPSHOT_ROOT / "safe_seed_revised" / "BFE2_2S_REVISED_SELECTED_SEED.json"
SEED_GATE = SNAPSHOT_ROOT / "safe_seed_revised" / "BFE2_2S_REVISED_GATE_STATUS.json"
FORMAL_GATE = SNAPSHOT_ROOT / "BFE2_2_GATE_STATUS.json"
LATCH_LOAD_MANIFEST = ANALYSIS_ROOT / "latch_load" / "BFE2_1_SCENARIO_MANIFEST.json"
OLD_SNAPSHOT_MANIFEST = SNAPSHOT_ROOT / "BFE2_2_SCENARIO_MANIFEST.json"
OLD_RETRY_MANIFEST = SNAPSHOT_ROOT / "BFE2_2_RETRY_MANIFEST.json"
ROOT_CAUSE = SNAPSHOT_ROOT / "root_cause" / "BFE2_2R_ROOT_CAUSE.json"

# This value is read from the committed B-FE2.2S selected-seed evidence and is
# checked again at runtime.  Keeping the literal here makes an accidental
# command-line override impossible; the JSON remains the authority for the
# interval and its provenance.
EXPECTED_CLOSE_PS = 534.5246185671714
EXPECTED_SCENARIO_IDS = ("BFE2L-095-N", "BFE2L-095-L2")
EXPECTED_RECORD_WIDTH = 124  # TIME + rail/G/SCLK + 30 RVT + 30 LVT + 30 XOR + 30 Q.
G_EDGE_WIDTH_PS = 1.0  # Same finite 1-ps edge used by the reviewed B-FE2.2 renderer.


def read_json(path: Path) -> Dict[str, Any]:
    """Read one object-shaped evidence artifact and reject malformed inputs."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def sha256_file(path: Path) -> str:
    """Hash a source, deck, or trace in bounded memory for immutable evidence."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_sha256() -> Sequence[Dict[str, str]]:
    """Return SHA256 provenance for every decision input consumed by this run.

    The physical deck and trace hashes are added per scenario after execution;
    these source hashes prove which corrected seed, old Gate, latch-load timing,
    and historical root-cause records authorized the new pair.
    """

    paths = (SEED_EVIDENCE, SEED_GATE, FORMAL_GATE, LATCH_LOAD_MANIFEST,
             OLD_SNAPSHOT_MANIFEST, OLD_RETRY_MANIFEST, ROOT_CAUSE)
    return [{"path": str(path.relative_to(FTC_ROOT)), "sha256": sha256_file(path)} for path in paths]


def corrected_seed_close_ps() -> float:
    """Validate and return the single immutable B-FE2.2S corrected midpoint."""

    gate = read_json(SEED_GATE)
    selected = read_json(SEED_EVIDENCE)
    if gate.get("gate") != "BFE2_2S_SAFE_SEED_READY":
        raise RuntimeError("B-FE2.2C requires BFE2_2S_SAFE_SEED_READY")
    seed = selected.get("selected_corrected_seed")
    if not isinstance(seed, dict):
        raise RuntimeError("B-FE2.2S selected seed is missing")
    if selected.get("gate") != gate.get("gate") or selected.get("new_hspice_scenarios") != 0:
        raise RuntimeError("B-FE2.2S selected-seed evidence is inconsistent")
    if abs(float(seed["midpoint_ps"]) - EXPECTED_CLOSE_PS) > 1.0e-9:
        raise RuntimeError("corrected seed midpoint differs from the frozen B-FE2.2S value")
    if float(seed["interval_end_ps"]) <= float(seed["interval_start_ps"]):
        raise RuntimeError("corrected seed does not have a positive-width interval")
    return float(seed["midpoint_ps"])


def scenarios() -> Tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Return exactly the formal 0.95-V normal/L2 pair in fixed order."""

    selected = tuple(item for item in bfe2_latch_load.SCENARIOS if item["scenario_id"] in EXPECTED_SCENARIO_IDS)
    if tuple(item["scenario_id"] for item in selected) != EXPECTED_SCENARIO_IDS:
        raise RuntimeError("B-FE2.2C must contain exactly the formal 0.95-V normal/L2 pair")
    if any(float(item["baseline_v"]) != 0.95 for item in selected):
        raise RuntimeError("B-FE2.2C corrected pair must remain at 0.95 V")
    return selected  # type: ignore


def electrical_signature(cells: Mapping[str, Any], scenario: Mapping[str, Any], close_ps: float, hspice_version: str) -> Dict[str, Any]:
    """Describe every physical parameter that can change a corrected waveform.

    The signature intentionally includes the same topology and source facts as
    B-FE2.1, plus the corrected finite-G requested close.  It is used both to
    detect an existing reusable scenario and to make a future duplicate run
    fail closed rather than overwrite an immutable raw product.
    """

    config = read_json(FTC_ROOT / "ftc_config.json")
    return {
        "stage": "B-FE2.2C",
        "topology_version": "bfe2_real_latch_30tap_4over0_corrected_seed_v1",
        "rvt_lvt_buffer_cells": [cells["delay_rvt"]["cell"], cells["delay_lvt"]["cell"]],
        "xor_cell": bfe1_frontend.XOR_CELL,
        "latch_cell": bfe2_latch_load.LATCH_CELL,
        "observable_taps": 30,
        "rvt_initial_stages": bfe1_frontend.RVT_PREFIX,
        "lvt_initial_stages": bfe1_frontend.LVT_PREFIX,
        "baseline_v": scenario["baseline_v"],
        "droop_v": scenario["droop_v"],
        "phase_ps": scenario["phase_ps"],
        "s_clk_pwl": "one 1ps rising edge at 1ns",
        "g_pwl": "one finite 1ps falling edge at corrected requested close",
        "requested_close_ps": close_ps,
        "g_edge_width_ps": G_EDGE_WIDTH_PS,
        "model_sha256": sha256_file(Path(config["model_library"])),
        "hspice_version": hspice_version,
        "tran_step_ps": bfe1_frontend.TRAN_STEP_S * 1.0e12,
    }


def signature_id(signature: Mapping[str, Any]) -> str:
    """Return a stable identity for duplicate-scenario protection."""

    payload = json.dumps(signature, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def scenario_directory(scenario_id: str) -> Path:
    """Map a formal scenario ID into the isolated corrected-seed run root."""

    return RUN_ROOT / scenario_id.lower().replace("-", "_")


def run_one(hspice: Path, cells: Mapping[str, Any], model_library: str, version: str,
            scenario: Mapping[str, Any], close_ps: float) -> Dict[str, Any]:
    """Render, validate, execute, and fingerprint one corrected-seed scenario.

    Existing directories are reusable only when their saved signature, deck,
    and `.tr0` are all present and consistent.  A mismatched directory is a
    hard error: overwriting it would destroy evidence of a different physical
    experiment and could silently exceed the two-scenario B-FE2.2C budget.
    """

    directory = scenario_directory(scenario["scenario_id"])
    signature = electrical_signature(cells, scenario, close_ps, version)
    sig_id = signature_id(signature)
    evidence_path = directory / "scenario_evidence.json"
    deck_path = directory / "bfe2c_corrected.sp"
    trace_path = directory / "bfe2c_corrected.tr0"
    if directory.exists():
        if not evidence_path.is_file() or not deck_path.is_file() or not trace_path.is_file():
            raise FileExistsError("existing corrected-seed directory lacks reusable evidence: {}".format(directory))
        existing = read_json(evidence_path)
        if existing.get("electrical_signature_id") != sig_id:
            raise FileExistsError("existing corrected-seed directory has a different electrical signature")
        existing["run_disposition"] = "reused"
        return existing

    directory.mkdir(parents=True)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    deck_text = bfe2_real_snapshot.render(cells, scenario, close_ps)
    bfe2_real_snapshot.validate(deck_text)
    deck_path.write_text(deck_text, encoding="ascii")
    result = subprocess.run([str(hspice), deck_path.name, "-o", "bfe2c_corrected"], cwd=str(directory),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                            check=False, timeout=600)
    (directory / "hspice_command.log").write_text(
        "command={} {} -o bfe2c_corrected\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            hspice, deck_path.name, result.returncode, result.stdout, result.stderr),
        encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError("B-FE2.2C HSPICE failed: {}".format(scenario["scenario_id"]))
    run_dc_sweep.validate_listing(directory / "bfe2c_corrected.lis")
    trace = bfe1_frontend.parse_ascii_tr0(trace_path)
    if trace["record_width"] != EXPECTED_RECORD_WIDTH:
        raise ValueError("B-FE2.2C trace violates the 124-column waveform contract")
    evidence = {
        "stage": "B-FE2.2C",
        "scenario_id": scenario["scenario_id"],
        "baseline_v": scenario["baseline_v"],
        "droop_v": scenario["droop_v"],
        "phase_ps": scenario["phase_ps"],
        "requested_close_ps": close_ps,
        "electrical_signature": signature,
        "electrical_signature_id": sig_id,
        "deck_sha256": sha256_file(deck_path),
        "tr0_sha256": sha256_file(trace_path),
        "hspice_version": version,
        "record_width": trace["record_width"],
        "record_count": trace["record_count"],
        "run_disposition": "new",
    }
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def main() -> int:
    """Execute exactly two corrected-seed cases and publish compact evidence."""

    close_ps = corrected_seed_close_ps()
    formal_gate = read_json(FORMAL_GATE)
    if formal_gate.get("gate") not in ("BFE2_2_REAL_SNAPSHOT_CONDITIONAL", "BFE2_2_CORRECTED_SEED_FAILED"):
        raise RuntimeError("B-FE2.2C is not authorized from the current formal B-FE2.2 Gate")
    config = read_json(FTC_ROOT / "ftc_config.json")
    cells = read_json(FTC_ROOT / "discovery" / "selected_cells.json")
    hspice = Path(config["hspice"])
    version = run_dc_sweep.hspice_version(hspice)
    if config["expected_hspice_version"] not in version:
        raise RuntimeError("unexpected HSPICE version for B-FE2.2C")
    pair = scenarios()
    if len(pair) != 2 or any(float(item["baseline_v"]) != 0.95 for item in pair):
        raise RuntimeError("B-FE2.2C authorization must resolve to two 0.95-V scenarios")
    results = [run_one(hspice, cells, config["model_library"], version, item, close_ps) for item in pair]
    new_count = sum(item.get("run_disposition") == "new" for item in results)
    if new_count > 2:
        raise RuntimeError("B-FE2.2C exceeded its two-scenario HSPICE budget")
    OUTPUT_MANIFEST.write_text(json.dumps({
        "schema_version": 1,
        "stage": "B-FE2.2C",
        "authorization_gate": "BFE2_2S_SAFE_SEED_READY",
        "corrected_seed_interval_ps": [
            read_json(SEED_EVIDENCE)["selected_corrected_seed"]["interval_start_ps"],
            read_json(SEED_EVIDENCE)["selected_corrected_seed"]["interval_end_ps"],
        ],
        "requested_close_ps": close_ps,
        "scenario_ids": list(EXPECTED_SCENARIO_IDS),
        "authorized_new_scenarios": 2,
        "new_hspice_scenarios": new_count,
        "total_bfe2_2_new_hspice_scenarios": 6 + new_count,
        "input_sha256": list(source_sha256()),
        "scenarios": results,
        "historical_evidence_preserved": {
            "first_attempt_manifest": str(OLD_SNAPSHOT_MANIFEST.relative_to(FTC_ROOT)),
            "retry_manifest": str(OLD_RETRY_MANIFEST.relative_to(FTC_ROOT)),
            "root_cause": str(ROOT_CAUSE.relative_to(FTC_ROOT)),
        },
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("BFE2_2C_CORRECTED_SEED_PAIR_COMPLETE new={} close_ps={:.9f}".format(new_count, close_ps))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
