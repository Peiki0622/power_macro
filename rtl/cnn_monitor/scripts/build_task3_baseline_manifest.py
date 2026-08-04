#!/usr/bin/env python3
"""Create the immutable input manifest for task-three gate power work.

The task-three flow must measure one known mapped design, one known ROM macro,
and one known L32 window library.  This script deliberately performs no
generation, synthesis, or copying of those inputs.  It only records their
identity and rejects a missing or structurally inconsistent baseline before a
later activity run can consume it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict


# This is the final 16-lane mapped implementation accepted by the stage-89
# timing run.  Keeping the location explicit prevents a later driver from
# silently choosing an older four-lane, debug, or partially-pipelined netlist.
MAPPED_RUN = (
    "rtl/cnn_monitor/runs/stage89_20260801_r2/"
    "step11_dc_500mhz_operand_prefetch_static_lanes"
)

# The ROM outputs are authenticated compiler delivery views, not a behavioral
# replacement.  The RCF digest is fixed here because it is the direct content
# contract checked by the exhaustive ROM readback regression.
ROM_RUN = "rtl/cnn_monitor/runs/stage89_20260801_r1/rom_compiler/output"
EXPECTED_ROM_RCF_SHA256 = (
    "4c7ab67f8fb68846f098f866d91e02540a4a535343d6dbb4c157373381c85334"
)


def _sha256(path: Path) -> str:
    """Return the binary SHA256 of one immutable input without loading it all."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _entry(root: Path, relative: str) -> Dict[str, object]:
    """Validate one required file and return its portable manifest entry."""
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError("required task-three input is missing: {}".format(path))
    return {
        "path": relative,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _validate_structure(root: Path, entries: Dict[str, Dict[str, object]]) -> None:
    """Check the semantic contracts that a hash alone cannot express.

    The mapped Verilog must be the released 16-lane top and must contain one
    physical ROM macro.  The task-one and window manifests are parsed so a
    correctly hashed but wrong-kind input cannot enter the gate power flow.
    """
    netlist = (root / entries["mapped_verilog"]["path"]).read_text(
        encoding="ascii", errors="replace"
    )
    if "module cnn_monitor_MAC_LANES16" not in netlist:
        raise ValueError("mapped netlist is not the frozen 16-lane design")
    if netlist.count("CNNW384X128 u_weight_rom") != 1:
        raise ValueError("mapped netlist does not contain exactly one ROM macro")

    if entries["rom_rcf"]["sha256"] != EXPECTED_ROM_RCF_SHA256:
        raise ValueError("ROM RCF digest differs from the authenticated delivery")

    task1 = json.loads(
        (root / entries["task1_manifest"]["path"]).read_text(encoding="utf-8")
    )
    if task1.get("status") != "PASS" or task1.get("selected_candidate") != "w8_a8":
        raise ValueError("task-one package is not the accepted W8/A8 package")
    if not task1.get("files", {}).get("weights/conv3_weights.mem", {}).get("sha256"):
        raise ValueError("task-one manifest does not bind the frozen weights")

    windows = json.loads(
        (root / entries["window_manifest"]["path"]).read_text(encoding="utf-8")
    )
    if windows.get("record_count") != 36:
        raise ValueError("task-three window manifest does not contain 36 records")
    expected_families = {
        "control": 5,
        "endpoint_dominant": 6,
        "mean_dominant": 7,
        "mixed_statistic": 8,
        "peak_dominant": 10,
    }
    if windows.get("families") != expected_families:
        raise ValueError("task-three window families differ from the frozen library")


def main() -> None:
    """Write one non-overwriteable manifest and a compact check log."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-directory", required=True, type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[3]
    run = args.run_directory.resolve()
    inputs = run / "inputs"
    evidence = run / "evidence"
    manifest_path = inputs / "baseline_manifest.json"
    log_path = evidence / "baseline_manifest_check.log"
    if manifest_path.exists() or log_path.exists():
        raise FileExistsError("refusing to overwrite baseline evidence in {}".format(run))
    inputs.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)

    required = {
        "cnn_monitor_rtl": "rtl/cnn_monitor/rtl/cnn_monitor.sv",
        "cnn_convolution_engine_rtl": "rtl/cnn_monitor/rtl/cnn_convolution_engine.sv",
        "cnn_pool_classifier_rtl": "rtl/cnn_monitor/rtl/cnn_pool_classifier.sv",
        "cnn_weight_rom_rtl": "rtl/cnn_monitor/rtl/cnn_weight_rom.sv",
        "cnn_window_buffer_rtl": "rtl/cnn_monitor/rtl/cnn_window_buffer.sv",
        "rtl_config": "rtl/cnn_monitor/config/cnn_rtl_config_v1.json",
        "activity_config": "rtl/cnn_monitor/config/cnn_activity_config_v1.json",
        "task1_manifest": (
            "tcn_detection/runs/formal_v1_20260727_r1/fixed_point/"
            "multistat_w18_k5_v1_20260801_r1/manifest.json"
        ),
        "rom_rcf": ROM_RUN + "/CNNW384X128_verilog.rcf",
        "rom_verilog": ROM_RUN + "/CNNW384X128.v",
        "rom_db": ROM_RUN + "/CNNW384X128_tt_1p10v_1p10v_25c.db",
        "mapped_ddc": MAPPED_RUN + "/cnn_monitor_mapped.ddc",
        "mapped_verilog": MAPPED_RUN + "/cnn_monitor_mapped.v",
        "mapped_sdf": MAPPED_RUN + "/cnn_monitor_mapped.sdf",
        "mapped_sdc": MAPPED_RUN + "/cnn_monitor_mapped.sdc",
        "window_manifest": (
            "rtl/cnn_monitor/runs/activity_codebook_20260802_r1/"
            "rtl_characterization/inputs/windows/manifest.json"
        ),
    }
    entries = {name: _entry(root, relative) for name, relative in required.items()}
    _validate_structure(root, entries)

    payload = {
        "schema_version": 1,
        "design_baseline_commit": "25366d29c970436f9addc5faddad86500bb338dc",
        "entries": entries,
    }
    manifest_path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="ascii")
    log_path.write_text(
        "status=PASS\nrequired_inputs={}\nrom_macro_count=1\nwindow_record_count=36\n".format(
            len(entries)
        ),
        encoding="ascii",
    )


if __name__ == "__main__":
    main()
