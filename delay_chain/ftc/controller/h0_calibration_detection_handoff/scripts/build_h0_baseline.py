#!/usr/bin/env python3
"""Build the H0 read-only baseline manifest.

The H0 handoff logic is allowed to consume the frozen startup-calibration
controller, but it is not allowed to silently redefine that controller's
clock, sensor boundary, or algorithm.  This small utility therefore records
the content hash and Git blob for every approved input and fails closed when a
P10-protected input has drifted.  It intentionally performs no synthesis,
simulation, netlist generation, or source-file rewriting.
"""

from __future__ import print_function

import hashlib
import json
import subprocess
from pathlib import Path


FROZEN_LIST = "delay_chain/ftc/controller/final_closure/freeze/STARTUP_CALIBRATION_FROZEN_FILES.json"

READ_ONLY_INPUTS = [
    "delay_chain/ftc/controller/final_closure/freeze/POWER_DOMAIN_CONTRACT.json",
    "delay_chain/ftc/controller/final_closure/freeze/STARTUP_CALIBRATION_EVIDENCE_BOUNDARY.md",
    "delay_chain/ftc/controller/final_closure/freeze/FTC_AUTONOMOUS_STARTUP_CALIBRATION_FINAL_ACCEPTANCE.md",
    "delay_chain/ftc/controller/refrequency/handoff/phase1_timing_handoff_refrequency.json",
    "delay_chain/ftc/controller/refrequency/handoff/rtl_timing_contract_audit.json",
    "delay_chain/ftc/controller/refrequency/timing_contract/cycle_timing_contract_refrequency.json",
    "delay_chain/ftc/controller/refrequency/synthesis/phase_refrequency_synthesis_results.json",
    "delay_chain/ftc/controller/refrequency/synthesis/reports/sense_s_clk_path.rpt",
    "delay_chain/ftc/controller/refrequency/synthesis/reports/sense_dff_reset_path.rpt",
    "delay_chain/ftc/controller/refrequency/synthesis/reports/thermometer_paths.rpt",
    "delay_chain/ftc/controller/refrequency/synthesis/reports/q_final_sampling_path.rpt",
    "delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa/inputs/ftc_sensor_frozen.sp",
    "delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/inputs/bridge_contract.json",
    "delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/src/ftc_sensor_ams_wrapper.sp",
    "delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/src/ftc_sensor_ams_stub.sv",
]


def sha256(path):
    """Hash a file incrementally so large frozen artifacts stay bounded."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_blob(root, relative):
    """Return the worktree blob identity without changing the index."""
    result = subprocess.Popen(
        ["git", "hash-object", relative],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, _ = result.communicate()
    if result.returncode != 0:
        return None
    return stdout.decode("utf-8").strip()


def load_json(root, relative):
    with (root / relative).open(encoding="utf-8") as stream:
        return json.load(stream)


def main():
    root = next(parent for parent in Path(__file__).resolve().parents if (parent / "plans").is_dir())
    frozen = load_json(root, FROZEN_LIST)
    frozen_by_path = {item["path"]: item for item in frozen["files"]}
    paths = []
    for item in frozen["files"]:
        paths.append(item["path"])
    for relative in READ_ONLY_INPUTS:
        if relative not in paths:
            paths.append(relative)

    records = []
    checks = []
    for relative in paths:
        path = root / relative
        if not path.is_file():
            checks.append({"path": relative, "pass": False, "reason": "missing"})
            continue
        frozen_record = frozen_by_path.get(relative, {})
        digest = sha256(path)
        blob = git_blob(root, relative)
        content_ok = frozen_record.get("content_sha256") in (None, digest)
        blob_ok = frozen_record.get("git_blob_sha") in (None, blob)
        checks.append({
            "path": relative,
            "content_sha256_matches_p10": content_ok,
            "git_blob_matches_p10": blob_ok,
            "pass": content_ok and blob_ok,
        })
        records.append({
            "path": relative,
            "classification": "P10 frozen input" if frozen_record else "H0 read-only input",
            "sha256": digest,
            "git_blob_sha": blob,
            "p10_content_sha256": frozen_record.get("content_sha256"),
            "p10_git_blob_sha": frozen_record.get("git_blob_sha"),
        })

    passed = all(item["pass"] for item in checks)
    output = root / "delay_chain/ftc/controller/h0_calibration_detection_handoff/baseline/h0_baseline_manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "schema_version": 1,
        "stage": "H0-0",
        "decision": "PASS" if passed else "STOP_BASELINE_DRIFT",
        "remote_main_commit": subprocess.check_output(
            ["git", "rev-parse", "origin/main"], cwd=str(root)
        ).decode("utf-8").strip(),
        "current_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(root)
        ).decode("utf-8").strip(),
        "new_simulation_count": 0,
        "new_synthesis_count": 0,
        "new_sta_count": 0,
        "checks": checks,
        "inputs": records,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not passed:
        raise SystemExit("H0-0 baseline drift detected; refusing to continue")
    print("H0-0 baseline PASS: %d approved inputs checked" % len(records))


if __name__ == "__main__":
    main()
