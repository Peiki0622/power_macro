#!/usr/bin/env python3
"""Build and validate the B-FE0 front-end architecture contract.

This module is intentionally limited to immutable-file inspection.  B-FE0 is
the zero-HSPICE boundary of the study: it records exactly which legacy sensor
inputs are inherited, what the new B-FE1 observation interface will mean, and
which old capture assumptions are explicitly out of scope.  No simulator,
deck renderer, or generated electrical result is touched here.

The contract is kept separate from ``selected_cells.json`` because the legacy
FTC reproduction uses the RVT ``TR40`` XOR cell, while the new B-FE1 plan
deliberately selects the LVT ``TL40`` XOR cell.  Keeping this selection in a
task-owned contract prevents the historical evidence from being silently
relabelled and prevents the legacy source files from being edited.
"""

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Mapping


FTC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = FTC_ROOT.parents[1]
ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend"

# These are the exact source files whose byte identity defines the inherited
# sensor.  They include wrappers and configuration, not generated simulator
# products.  Any future topology edit must change this audit deliberately.
LEGACY_FILES = (
    "delay_chain/ftc/rtl/ftc_sensor.sv",
    "delay_chain/ftc/rtl/ftc_config_pkg.sv",
    "delay_chain/ftc/rtl/ftc_rvt_delay_stage_struct.sv",
    "delay_chain/ftc/rtl/ftc_lvt_delay_stage_struct.sv",
    "delay_chain/ftc/rtl/ftc_xor_stage_struct.sv",
    "delay_chain/ftc/rtl/ftc_capture_struct.sv",
    "delay_chain/ftc/scripts/generate_ftc_deck.py",
    "delay_chain/ftc/ftc_config.json",
    "delay_chain/ftc/discovery/selected_cells.json",
)

# The T0 contract is an input authority only.  B-FE1 reads its threat values;
# it never rewrites the T0 output or claims T0's DFF result as its own proof.
AUTHORITY_FILES = (
    "delay_chain/ftc/analysis/t0_transient_droop/contract/T0_TRANSIENT_THREAT_CONTRACT.json",
    "delay_chain/ftc/analysis/t0_transient_droop/cadence/cadence_summary.json",
)


def sha256_file(path: Path) -> str:
    """Return a streaming SHA256 digest for one existing regular file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_file(relative_path: str) -> Path:
    """Resolve a repository-relative input and reject missing/non-files."""

    path = REPO_ROOT / relative_path
    if not path.is_file():
        raise FileNotFoundError("B-FE0 input is not a regular file: {}".format(path))
    return path


def read_json(relative_path: str) -> Mapping[str, object]:
    """Read one object-shaped JSON authority without changing it."""

    value = json.loads(require_file(relative_path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("B-FE0 JSON input must be an object: {}".format(relative_path))
    return value


def git_head() -> str:
    """Return the current branch commit for provenance, without mutating Git."""

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
    )
    return result.stdout.strip()


def git_branch() -> str:
    """Return the checked-out branch and make the planned branch explicit."""

    result = subprocess.run(
        ["git", "branch", "--show-current"], cwd=str(REPO_ROOT), check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
    )
    branch = result.stdout.strip()
    if branch != "bfe-multitap-latched-frontend":
        raise ValueError("B-FE0 must run on bfe-multitap-latched-frontend, got {}".format(branch))
    return branch


def legacy_inventory() -> Dict[str, Dict[str, str]]:
    """Hash each inherited source using stable repository-relative names."""

    return {
        relative: {
            "path": relative,
            "sha256": sha256_file(require_file(relative)),
        }
        for relative in LEGACY_FILES
    }


def authority_inventory() -> Dict[str, Dict[str, str]]:
    """Hash only the external authority files needed by B-FE1."""

    return {
        relative: {
            "path": relative,
            "sha256": sha256_file(require_file(relative)),
        }
        for relative in AUTHORITY_FILES
    }


def validate_library_contract(cells: Mapping[str, object]) -> Dict[str, object]:
    """Validate that the planned TL40 XOR has real LVT CDL/Verilog evidence.

    The selected legacy cell record is deliberately not changed.  Instead this
    check resolves the already-discovered LVT source paths and proves that the
    planned cell name and powered CDL pin order are present in those sources.
    """

    source_files = cells.get("source_files")
    if not isinstance(source_files, dict):
        raise ValueError("selected_cells.json lacks source_files")
    lvt_cdl = Path(str(source_files["lvt_cdl"]))
    lvt_verilog = Path(str(source_files["lvt_verilog"]))
    if not lvt_cdl.is_file() or not lvt_verilog.is_file():
        raise FileNotFoundError("B-FE0 TL40 source path is unavailable")
    cdl_text = lvt_cdl.read_text(encoding="utf-8", errors="replace")
    verilog_text = lvt_verilog.read_text(encoding="utf-8", errors="replace")
    cell_name = "XOR2_X0P5M_A9TL40"
    cdl_match = re.search(r"\.SUBCKT\s+{}\s+([^\n]+)".format(cell_name), cdl_text)
    if cdl_match is None:
        raise ValueError("TL40 XOR CDL subckt is absent from {}".format(lvt_cdl))
    expected_ports = ["Y", "VDD", "VNW", "VPW", "VSS", "A", "B"]
    actual_ports = cdl_match.group(1).split()
    if actual_ports != expected_ports:
        raise ValueError("TL40 XOR CDL ports changed: {}".format(actual_ports))
    if "module {}".format(cell_name) not in verilog_text:
        raise ValueError("TL40 XOR powered Verilog module is absent from {}".format(lvt_verilog))
    return {
        "cell": cell_name,
        "vt_class": "LVT",
        "cdl_ports": expected_ports,
        "cdl_path": str(lvt_cdl),
        "cdl_sha256": sha256_file(lvt_cdl),
        "verilog_path": str(lvt_verilog),
        "verilog_sha256": sha256_file(lvt_verilog),
        "power_mapping": {"VDD": "VDD_MONITORED", "VNW": "VDD_MONITORED", "VPW": "VSS", "VSS": "VSS"},
    }


def build_contracts() -> Dict[str, object]:
    """Build all B-FE0 JSON values after validating immutable inputs."""

    branch = git_branch()
    head = git_head()
    cells = read_json("delay_chain/ftc/discovery/selected_cells.json")
    config = read_json("delay_chain/ftc/ftc_config.json")
    threat = read_json(AUTHORITY_FILES[0])
    if int(config.get("observable_stages", -1)) != 30:
        raise ValueError("legacy config observable_stages is not 30")
    if float(config.get("selected_operating_point", {}).get("initial_rvt_stages", -1)) != 4:
        raise ValueError("legacy selected RVT prefix is not 4")
    if float(config.get("selected_operating_point", {}).get("initial_lvt_stages", -1)) != 0:
        raise ValueError("legacy selected LVT prefix is not 0")
    if threat.get("waveform", {}).get("minimum_hold_ps") != 1.0:
        raise ValueError("T0 threat contract is not the expected finite-slope contract")
    inventory = legacy_inventory()
    authority = authority_inventory()
    return {
        "architecture": {
            "schema_version": 1,
            "stage": "B-FE0",
            "branch": branch,
            "baseline_commit": "725855dc71ce16362a2b84bd7f4d45fe7389d7cb",
            "observed_at_commit": head,
            "observable_taps": 30,
            "tap_indices": list(range(30)),
            "rvt_prefix": 4,
            "lvt_prefix": 0,
            "xor_count": 30,
            "xor_cell": "XOR2_X0P5M_A9TL40",
            "snapshot_model": "ideal_offline_threshold_snapshot",
            "threshold": "V(xor_i,t) > 0.5 * V(VDD_MONITORED,t)",
            "raw_code_preserved": True,
            "real_latch_instantiated": False,
            "real_mf_sample_generator": False,
            "legacy_sensor_modified": False,
            "new_hspice_scenarios": 0,
            "gate": "BFE0_FRONTEND_CONTRACT_READY",
        },
        "legacy": {
            "schema_version": 1,
            "stage": "B-FE0",
            "baseline_commit": "725855dc71ce16362a2b84bd7f4d45fe7389d7cb",
            "current_commit": head,
            "files": inventory,
            "authority_files": authority,
            "legacy_xor_cell": str(cells.get("xor2", {}).get("cell")),
            "legacy_xor_is_not_bfe1_evidence": True,
            "byte_identity_required": True,
        },
        "observable": {
            "schema_version": 1,
            "stage": "B-FE0",
            "tap_index_range": [0, 29],
            "bit_definition": "1 iff V(xor_i,t) > 0.5 * V(VDD_MONITORED,t); otherwise 0",
            "derived_fields": [
                "raw_code", "start", "end", "len", "center", "run_count",
                "bubble_count", "left_headroom", "right_headroom",
            ],
            "main_run_tie_policy": "record_all_equal_length_maximum_runs; do_not_repair_raw_code",
            "undefined_level_policy": "exclude_interval_and_record_diagnostic",
            "threshold_follows_instantaneous_local_supply": True,
        },
    }


def write_contracts(contracts: Mapping[str, object]) -> None:
    """Write the three compact, reviewable B-FE0 artifacts."""

    ANALYSIS_ROOT.mkdir(parents=True, exist_ok=True)
    names = {
        "architecture": "bfe0_architecture_contract.json",
        "legacy": "bfe0_legacy_baseline_sha256.json",
        "observable": "bfe0_observable_definition.json",
    }
    for key, filename in names.items():
        (ANALYSIS_ROOT / filename).write_text(
            json.dumps(contracts[key], indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def main() -> int:
    """Validate and write B-FE0 contracts; return zero only on full success."""

    contracts = build_contracts()
    write_contracts(contracts)
    print("BFE0_FRONTEND_CONTRACT_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
