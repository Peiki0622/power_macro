#!/usr/bin/env python3
"""Run the one authorized B-FE2.2 replacement close-time pair at 0.95 V.

This runner intentionally has no sweep interface.  B-FE2.2 permits one
replacement close time only after a failed paired first attempt; encoding that
rule directly prevents an accidental timing scan.  The two scenarios share
the exact same finite G falling edge, while their normal/L2 supply waveforms
remain the frozen formal inputs from B-FE2.1.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Mapping


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import bfe1_frontend  # noqa: E402  # Frozen S_CLK, rail, delay-path, and trace conventions.
import bfe2_latch_load  # noqa: E402  # Frozen 30-XOR/30-LATQ topology and formal scenarios.
import bfe2_real_snapshot  # noqa: E402  # Reviewed finite-G deck transform and static guard.
import run_dc_sweep  # noqa: E402  # Project-standard HSPICE listing/version validation.


RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "real_snapshot"
OUTPUT_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "real_snapshot"
FIRST_GATE = OUTPUT_ROOT / "BFE2_2_GATE_STATUS.json"
LOAD_PAIRWISE = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "latch_load" / "BFE2_1_PAIRWISE_DISCRIMINATION.json"

# The retry comes from the third-ranked-by-width clean, central B-FE2.1
# platform at 0.95 V: 312.251653--328.416258 ps.  Its midpoint is retained at
# full measured precision.  It is distinct from the failed 404.941916-ps seed
# and not a constant copied from B-FE1R.
RETRY_CLOSE_PS = 320.333956
RETRY_SCENARIO_IDS = ("BFE2L-095-N", "BFE2L-095-L2")


def read_json(path: Path) -> Dict[str, Any]:
    """Read one required compact decision/evidence object."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def sha256_file(path: Path) -> str:
    """Hash deck and trace evidence without loading raw waveforms into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def retry_scenarios() -> tuple:
    """Return only the failed 0.95-V normal/L2 pair in formal ordering."""

    selected = tuple(item for item in bfe2_latch_load.SCENARIOS if item["scenario_id"] in RETRY_SCENARIO_IDS)
    if len(selected) != 2 or any(float(item["baseline_v"]) != 0.95 for item in selected):
        raise ValueError("retry must contain exactly the formal 0.95-V normal/L2 pair")
    return selected


def validate_retry_authorization() -> None:
    """Enforce the Gate, single-retry budget, and B-FE2.1-derived time source."""

    first_gate = read_json(FIRST_GATE)
    if first_gate.get("gate") != "BFE2_2_REAL_SNAPSHOT_CONDITIONAL":
        raise RuntimeError("retry is allowed only after the first B-FE2.2 attempt is conditional")
    failing = [pair for pair in first_gate.get("pairs", []) if pair.get("baseline_v") == 0.95]
    if len(failing) != 1 or all(failing[0][side].get("stable") for side in ("normal", "l2")):
        raise RuntimeError("0.95-V retry requires observed first-attempt Q instability")
    pairwise = read_json(LOAD_PAIRWISE)
    pair = next(item for item in pairwise["pairs"] if item["baseline_v"] == 0.95)
    candidate_midpoints = [(item["interval_start_ps"] + item["interval_end_ps"]) / 2.0 for item in pair["candidate_platforms"]]
    if not any(abs(midpoint - RETRY_CLOSE_PS) < 1.0e-5 for midpoint in candidate_midpoints):
        raise RuntimeError("retry close time is not derived from a B-FE2.1 candidate platform")


def run_one(hspice: Path, cells: Mapping[str, Any], model_library: str, version: str, scenario: Mapping[str, Any]) -> Dict[str, Any]:
    """Render and run one half of the paired retry in its dedicated directory.

    The task-specific suffix prevents overwriting the first-close evidence.
    A pre-existing directory is rejected, because B-FE2.2 permits a single
    replacement pair and must never silently overwrite or add another retry.
    """

    directory = RUN_ROOT / "scenarios" / (scenario["scenario_id"].lower().replace("-", "_") + "_retry_320p334ps")
    if directory.exists():
        raise FileExistsError("replacement snapshot directory already exists: {}".format(directory))
    directory.mkdir(parents=True)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    deck_text = bfe2_real_snapshot.render(cells, scenario, RETRY_CLOSE_PS)
    bfe2_real_snapshot.validate(deck_text)
    deck = directory / "bfe2s_retry.sp"
    deck.write_text(deck_text, encoding="ascii")
    result = subprocess.run([str(hspice), deck.name, "-o", "bfe2s_retry"], cwd=str(directory), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=600)
    (directory / "hspice_command.log").write_text("command={} {} -o bfe2s_retry\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(hspice, deck.name, result.returncode, result.stdout, result.stderr), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError("B-FE2.2 replacement HSPICE failed: {}".format(scenario["scenario_id"]))
    run_dc_sweep.validate_listing(directory / "bfe2s_retry.lis")
    trace = bfe1_frontend.parse_ascii_tr0(directory / "bfe2s_retry.tr0")
    if trace["record_width"] != 124:
        raise ValueError("replacement trace violates the 124-column waveform contract")
    return {"scenario_id": scenario["scenario_id"], "baseline_v": scenario["baseline_v"], "droop_v": scenario["droop_v"], "phase_ps": scenario["phase_ps"], "close_ps": RETRY_CLOSE_PS, "close_source": "B-FE2.1 312.251653--328.416258 ps platform midpoint", "deck_sha256": sha256_file(deck), "tr0_sha256": sha256_file(directory / "bfe2s_retry.tr0"), "hspice_version": version, "record_width": trace["record_width"], "record_count": trace["record_count"], "run_disposition": "new"}


def main() -> int:
    """Execute the only authorized replacement pair and publish compact evidence."""

    validate_retry_authorization()
    config = read_json(FTC_ROOT / "ftc_config.json")
    cells = read_json(FTC_ROOT / "discovery" / "selected_cells.json")
    hspice = Path(config["hspice"])
    version = run_dc_sweep.hspice_version(hspice)
    if config["expected_hspice_version"] not in version:
        raise RuntimeError("unexpected HSPICE version for B-FE2.2 retry")
    results = [run_one(hspice, cells, config["model_library"], version, scenario) for scenario in retry_scenarios()]
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "BFE2_2_RETRY_MANIFEST.json").write_text(json.dumps({"stage": "B-FE2.2", "retry_reason": "0.95-V first seed had post-close Q evolution", "new_hspice_scenarios": 2, "total_bfe2_2_new_hspice_scenarios": 6, "scenarios": results}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("BFE2_2_REAL_SNAPSHOT_RETRY_COMPLETE new=2 close_ps={:.6f}".format(RETRY_CLOSE_PS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
