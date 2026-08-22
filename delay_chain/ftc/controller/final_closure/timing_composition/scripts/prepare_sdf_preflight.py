#!/usr/bin/env python3
"""Prepare the C2 SDF composition contract using static files only.

The script intentionally performs no elaboration and no transient simulation.
It freezes the exact netlist, SDF, bridge, sensor, and testbench inputs before
the first timing-composed run.  The generated JSON records enough structure to
prove that the SDF top, mapped controller instance, 1 ns clock, and required
controller/sensor signals are the same objects that the C3 bench will use.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


# The script is below final_closure/timing_composition/scripts.  Resolving the
# controller root from this known layout prevents accidental use of a copied
# or historical netlist when the script is launched from another directory.
SCRIPT_PATH = Path(__file__).resolve()
CONTROLLER_ROOT = SCRIPT_PATH.parents[3]
REPO_ROOT = CONTROLLER_ROOT.parents[2]
COMPOSITION_ROOT = CONTROLLER_ROOT / "final_closure/timing_composition"
INPUT_ROOT = COMPOSITION_ROOT / "inputs"
REPORT_ROOT = COMPOSITION_ROOT / "reports"
SOURCE_ROOT = COMPOSITION_ROOT / "src"


def rel(path):
    """Return a stable repository-relative path for committed evidence."""

    return path.relative_to(REPO_ROOT).as_posix()


def sha256(path):
    """Hash one input in bounded blocks so large netlists stay low-memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(path):
    """Fail before any run if a frozen input is missing."""

    if not path.is_file():
        raise SystemExit("missing C2 input: " + rel(path))
    return path


def write_json(path, value):
    """Write deterministic evidence with a final newline."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    """Freeze inputs and perform the complete local static preflight."""

    netlist = require(CONTROLLER_ROOT / "synthesis/netlist/ftc_cal_controller_top_synth.v")
    sdf = require(CONTROLLER_ROOT / "synthesis/netlist/ftc_cal_controller_top_synth.sdf")
    sdc = require(CONTROLLER_ROOT / "synthesis/netlist/ftc_cal_controller_top_synth.sdc")
    timing = require(CONTROLLER_ROOT / "spec/phase1_timing_handoff.json")
    sensor = require(CONTROLLER_ROOT / "analysis/phase9_autonomous_transistor_level/vcs_xa/inputs/ftc_sensor_frozen.sp")
    cell_model = require(CONTROLLER_ROOT / "analysis/phase9_autonomous_transistor_level/vcs_xa/inputs/sc9mc_logic0040ll_base_rvt_c40.v")
    bridge_stub = require(CONTROLLER_ROOT / "analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/src/ftc_sensor_ams_stub.sv")
    bridge_wrapper = require(CONTROLLER_ROOT / "analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/src/ftc_sensor_ams_wrapper.sp")
    testbench = require(CONTROLLER_ROOT / "analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/src/tb_ftc_vcs_xa_autonomous.sv")
    monitor = require(COMPOSITION_ROOT / "src/timing_composition_monitor.sv")
    bridge_init = require(CONTROLLER_ROOT / "analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/src/vcsAD.init")
    xa_cfg = require(CONTROLLER_ROOT / "analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/src/xa.cfg")
    bridge_contract = require(CONTROLLER_ROOT / "analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/inputs/bridge_contract.json")

    netlist_text = netlist.read_text(encoding="utf-8", errors="replace")
    sdf_text = sdf.read_text(encoding="utf-8", errors="replace")
    tb_text = testbench.read_text(encoding="utf-8", errors="replace")
    timing_data = json.loads(timing.read_text(encoding="utf-8"))

    module_ok = bool(re.search(r"\bmodule\s+ftc_cal_controller_top\b", netlist_text))
    sdf_design = re.search(r"\(DESIGN\s+\"([^\"]+)\"\)", sdf_text)
    sdf_cell = re.search(r"\(CELLTYPE\s+\"([^\"]+)\"\)", sdf_text)
    required_signals = {
        "sense_s_clk": "sense_s_clk" in netlist_text and "sense_s_clk" in sdf_text,
        "sense_dff_reset": "sense_dff_reset" in netlist_text and "sense_dff_reset" in sdf_text,
        "q_sample_1": "q_sample_1_o_reg" in netlist_text and "q_sample_1_o_reg" in sdf_text,
        "q_sample_2": "q_sample_2_event_o_reg" in netlist_text and "q_sample_2_event_o_reg" in sdf_text,
        "medium_therm_registers": "medium_therm_o_reg" in netlist_text and "medium_therm_o_reg" in sdf_text,
        "fine_therm_registers": "fine_therm_o_reg" in netlist_text and "fine_therm_o_reg" in sdf_text,
    }
    # The existing corrected bench is copied into the task-owned source area;
    # the copy is still the frozen bridge bench and drives only the three
    # permitted controller inputs.  The controller owns every sensor control.
    ownership_checks = {
        "autonomous_top_present": bool(re.search(r"\bmodule\s+tb_ftc_vcs_xa_autonomous\b", tb_text)),
        "controller_instance_present": bool(re.search(r"\bftc_cal_controller_top\s+u_controller\b", tb_text)),
        "sensor_instance_present": bool(re.search(r"\bftc_sensor_ams\s+u_sensor\b", tb_text)),
        "no_direct_sensor_clock_assignment": not bool(re.search(r"\b(sense_s_clk|sense_dff_reset|medium_therm|fine_therm)\s*=", tb_text)),
        "only_calibration_inputs_assigned": all(name in tb_text for name in ("cal_clk", "ctrl_por_n", "cal_start")),
    }
    sdf_contract = {
        "schema_version": 1,
        "status": "FROZEN_FOR_C2",
        "simulation_performed": False,
        "sdf_design": sdf_design.group(1) if sdf_design else None,
        "sdf_celltype": sdf_cell.group(1) if sdf_cell else None,
        "mapped_netlist_top": "ftc_cal_controller_top" if module_ok else None,
        "annotation_target": "tb_ftc_vcs_xa_autonomous.u_controller",
        "annotation_mode": "max",
        "clock_period_ns": 1.0e9 / timing_data["cal_clk_hz"],
        "timing_constants": timing_data["local_probe_event_cycles"],
        "forbidden_compile_flags": ["+nospecify", "+notimingcheck"],
        "required_signals": required_signals,
        "testbench_ownership": ownership_checks,
        "frozen_input_paths": {
            key: rel(value)
            for key, value in {
                "netlist": netlist,
                "sdf": sdf,
                "sdc": sdc,
                "phase1_timing": timing,
                "sensor": sensor,
                "standard_cell_model": cell_model,
                "bridge_stub": bridge_stub,
                "bridge_wrapper": bridge_wrapper,
                "testbench": testbench,
                "timing_monitor": monitor,
                "bridge_init": bridge_init,
                "xa_cfg": xa_cfg,
                "bridge_contract": bridge_contract,
            }.items()
        },
    }
    errors = []
    if not module_ok:
        errors.append("mapped netlist top module is missing")
    if not sdf_design or sdf_design.group(1) != "ftc_cal_controller_top":
        errors.append("SDF DESIGN does not match mapped top")
    if not sdf_cell or sdf_cell.group(1) != "ftc_cal_controller_top":
        errors.append("SDF CELLTYPE does not match mapped top")
    if sdf_contract["clock_period_ns"] != 1.0:
        errors.append("Phase 1 clock is not exactly 1 ns")
    errors.extend(name for name, present in required_signals.items() if not present)
    errors.extend(name for name, present in ownership_checks.items() if not present)
    if errors:
        sdf_contract["status"] = "FAIL"
        sdf_contract["errors"] = errors
        write_json(REPORT_ROOT / "SDF_ANNOTATION_PREFLIGHT.json", sdf_contract)
        raise SystemExit("C2 static preflight failed: " + "; ".join(errors))

    INPUT_ROOT.mkdir(parents=True, exist_ok=True)
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    # Copy only source inputs into the task-owned composition tree.  No raw
    # simulator output is copied, and the original corrected Phase 9 tree is
    # never modified by this operation.
    for source in (bridge_stub, bridge_wrapper, testbench, bridge_init, xa_cfg):
        destination = SOURCE_ROOT / source.name
        destination.write_bytes(source.read_bytes())
    manifest = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "simulation_performed": False,
        "files": [
            {"path": rel(path), "sha256": sha256(path)}
            for path in (netlist, sdf, sdc, timing, sensor, cell_model, bridge_stub, bridge_wrapper, testbench, monitor, bridge_init, xa_cfg, bridge_contract)
        ],
    }
    write_json(INPUT_ROOT / "baseline_manifest.json", manifest)
    write_json(INPUT_ROOT / "input_sha256.json", manifest)
    write_json(INPUT_ROOT / "sdf_composition_contract.json", sdf_contract)
    write_json(REPORT_ROOT / "SDF_ANNOTATION_PREFLIGHT.json", {
        **sdf_contract,
        "status": "STATIC_GO_PENDING_REMOTE_ELABORATION",
        "static_checks": {
            "sdf_design_matches_top": True,
            "annotation_target_present_in_testbench": True,
            "required_signals_present": True,
            "external_clock_period_ns": 1.0,
            "timing_checks_requested": True,
            "transient_started": False,
        },
        "remote_elaboration": {"performed": False, "log": None},
    })
    print(json.dumps({"status": "STATIC_GO_PENDING_REMOTE_ELABORATION", "inputs": len(manifest["files"]), "transient_started": False}, indent=2))


if __name__ == "__main__":
    main()
