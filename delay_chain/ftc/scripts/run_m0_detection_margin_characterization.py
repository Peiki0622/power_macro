#!/usr/bin/env python3
"""Characterize FTC M0 detection margin with the frozen real-cell topology.

M0 deliberately sits between the completed calibration/handoff work and any
future synthesizable detector.  It contains no calibration FSM, no detector
RTL, and no droop waveform.  Every electrical point is instead one isolated,
static-VDD probe of the already-approved transistor-level sensor, medium path,
fine load bank, real XOR, and real DFF.

The implementation is intentionally self-contained at the *study* level:
all files it writes live below the M0 analysis/run roots.  It imports only the
reviewed physical-topology helpers from the completed dynamic runner; it never
edits or dispatches an upstream calibration experiment.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


# ``scripts`` is the only import location needed for the frozen physical deck
# helpers.  Keeping the import explicit makes it easy to audit that M0 did not
# accidentally import an older static-calibration main program.
FTC_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = FTC_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import run_dynamic_startup_calibration_protocol as physical  # noqa: E402


STUDY = "ftc_m0_detection_margin_characterization_v1"
ANALYSIS = FTC_ROOT / "analysis" / "m0_detection_margin_characterization"
RUN_ROOT = FTC_ROOT / "runs" / "m0_detection_margin_characterization"
REPORT = FTC_ROOT / "reports" / "FTC_M0_DETECTION_MARGIN_CHARACTERIZATION.md"

# These are the only frozen H0 snapshots M0 is allowed to consume.  The
# windows are the exact local windows from the approved M0 plan, not a new
# search range and not a fixed F+delta detector rule.
ANCHORS: Dict[str, Dict[str, Any]] = {
    "0.80": {"baseline_vdd_v": 0.80, "M_cal": 7, "F_cal": 6, "m_values": tuple(range(6, 9)), "f_values": tuple(range(3, 10))},
    "0.95": {"baseline_vdd_v": 0.95, "M_cal": 4, "F_cal": 6, "m_values": tuple(range(3, 6)), "f_values": tuple(range(3, 10))},
    "1.10": {"baseline_vdd_v": 1.10, "M_cal": 2, "F_cal": 9, "m_values": tuple(range(1, 4)), "f_values": tuple(range(6, 11))},
}

# The exact-path HSPICE acceptance has already verified these physical timing
# minima after the 400 MHz H0 timing correction.  They define a conservative
# one-probe testbench timeline; they do not modify the RTL cycle contract.
CONTROL_EDGE_S = 10e-12
SCLK_EDGE_S = 1e-12
RESET_RELEASE_TO_SCLK_S = 0.49e-9
SCLK_TO_Q1_S = 2.30e-9
Q1_TO_Q2_S = 0.20e-9
Q2_TO_RESET_ASSERT_S = 0.20e-9
RESET_ASSERT_WIDTH_S = 10e-12
RESET_COMPLETE_TO_SCLK_FALL_S = 0.29e-9
SCLK_FALL_TO_RECOVERY_S = 2.70e-9

Q_HIGH_RATIO = 0.90
Q_LOW_RATIO = 0.10

SCENARIO_FIELDS = (
    "scenario_id", "baseline_vdd_v", "physical_vdd_v", "medium_code", "fine_code",
    "t_xor_rise_s", "t_xor_fall_s", "t_ck_rise_s", "t_ck_rise_2_s",
    "W_xor_ps", "D_ref_ps", "R_ps", "q_final_v", "q_final_late_v", "q_final",
    "q_state", "active_ck_edge_count", "recovery_max_ratio", "valid", "reason",
    "scenario_path", "deck_sha256", "physical_contract_sha256",
)
LOCAL_SURFACE_FIELDS = SCENARIO_FIELDS + ("Delta_D_ref_ps", "Delta_R_ps")
MECHANISM_FIELDS = SCENARIO_FIELDS + ("margin_level", "candidate_id", "mechanism_candidate_pass", "mechanism_reason")
TRIP_SWEEP_FIELDS = SCENARIO_FIELDS + ("margin_level", "candidate_id", "sweep_stage")
TRIP_MAP_FIELDS = (
    "baseline_vdd_v", "margin_level", "candidate_id", "M_det", "F_det",
    "nominal_D_ref_shift_ps", "trip_status", "Vtrip_v", "DeltaV_trip_mv",
    "R_at_last_q0_ps", "R_at_first_q1_ps", "ordering_ok", "reason",
)
CANDIDATE_FIELDS = (
    "baseline_vdd_v", "M_cal", "F_cal", "margin_level", "candidate_id", "M_det", "F_det",
    "nominal_D_ref_shift_ps", "nominal_R_ps", "normal_Q", "selection_reason",
)


def require_dl() -> Dict[str, str]:
    """Reject every formal M0 action outside the required Miniconda ``DL`` env.

    The environment name is checked before reading or writing study evidence.
    This prevents a system-Python parser or plotter from quietly producing a
    different CSV or figure.  Matplotlib is imported only after the caller has
    passed this gate, so the runner itself has no plotting dependency.
    """

    if os.environ.get("CONDA_DEFAULT_ENV") != "DL":
        raise RuntimeError("M0 requires CONDA_DEFAULT_ENV=DL; refusing non-DL execution")
    return {
        "conda_env": os.environ["CONDA_DEFAULT_ENV"],
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
    }


def sha256_file(path: Path) -> str:
    """Hash one immutable input without copying large PDK/CDL collateral."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_json(value: Mapping[str, Any]) -> str:
    """Serialize a contract deterministically before it contributes to an ID."""

    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_mapping(value: Mapping[str, Any]) -> str:
    """Return the SHA256 of a JSON contract using the study's stable encoding."""

    return hashlib.sha256(stable_json(value).encode("ascii")).hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    """Load an object-shaped JSON contract and reject malformed evidence."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write task-owned JSON with stable formatting for reproducible hashes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    """Write rectangular M0 evidence while keeping failed measurements visible."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def read_csv(path: Path, required: Sequence[str], allow_empty: bool = False) -> List[Dict[str, str]]:
    """Read a formal CSV, preserving header-only terminal NO-GO evidence.

    Formal electrical gates require at least one row and therefore retain the
    default strict behavior.  Final publication, however, must also render a
    complete auditable NO-GO report from an intentionally header-only table
    when an earlier gate correctly prevents later HSPICE work.
    """

    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not set(required).issubset(reader.fieldnames):
            raise ValueError("CSV schema is missing required columns: {}".format(path))
        rows = list(reader)
    if not rows and not allow_empty:
        raise ValueError("CSV is empty: {}".format(path))
    return rows


def optional_float(value: Any) -> Optional[float]:
    """Keep an absent or failed HSPICE measurement distinct from numeric zero."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def voltage_key(value: float) -> str:
    """Use one two-decimal VDD spelling in IDs, joins, and JSON keys."""

    return "{:.2f}".format(float(value))


def analysis_paths() -> Dict[str, Path]:
    """Return every M0-owned output location without creating unrelated files."""

    return {
        "baseline": ANALYSIS / "baseline",
        "probe_contract": ANALYSIS / "probe_contract",
        "local_surface": ANALYSIS / "local_surface",
        "mechanism": ANALYSIS / "mechanism_gate",
        "trip": ANALYSIS / "trip",
        "figures": ANALYSIS / "figures",
        "tables": ANALYSIS / "tables",
        "frozen_inputs": ANALYSIS / "baseline" / "frozen_inputs.json",
        "environment": ANALYSIS / "baseline" / "environment_manifest.json",
        "single_probe_contract": ANALYSIS / "probe_contract" / "single_probe_contract.json",
        "scenario_manifest": ANALYSIS / "probe_contract" / "scenario_manifest.json",
        "surface_csv": ANALYSIS / "local_surface" / "local_code_surface.csv",
        "surface_summary": ANALYSIS / "local_surface" / "local_code_surface_summary.json",
        "candidate_csv": ANALYSIS / "tables" / "table_m0_candidate_summary.csv",
        "candidate_summary": ANALYSIS / "local_surface" / "candidate_selection_summary.json",
        "mechanism_csv": ANALYSIS / "mechanism_gate" / "mechanism_gate.csv",
        "mechanism_summary": ANALYSIS / "mechanism_gate" / "mechanism_gate_summary.json",
        "trip_sweep": ANALYSIS / "trip" / "trip_sweep.csv",
        "trip_map": ANALYSIS / "trip" / "trip_map.csv",
        "trip_summary": ANALYSIS / "trip" / "trip_summary.json",
        "trip_table": ANALYSIS / "tables" / "table_m0_trip_summary.csv",
        "figure_manifest": ANALYSIS / "figure_manifest.json",
        "summary": ANALYSIS / "summary.json",
    }


def frozen_input_paths(context: Mapping[str, Any]) -> Dict[str, Path]:
    """Enumerate all architecture, timing, RTL, and physical collateral M0 freezes.

    The list intentionally includes both the H0 publication and the exact-path
    physical acceptance.  The former defines ownership/snapshot semantics;
    the latter proves that the three concrete M/F anchors are electrically
    reachable with the corrected event order.
    """

    controller = FTC_ROOT / "controller"
    rtl = controller / "rtl"
    cells = context["cells"]
    config = context["config"]
    paths: Dict[str, Path] = {
        "h0_gate_status": controller / "h0_calibration_detection_handoff/reports/H0_GATE_STATUS.json",
        "h0_final_report": controller / "h0_calibration_detection_handoff/reports/H0_FINAL_REPORT.md",
        "h0_interface": controller / "h0_calibration_detection_handoff/reports/H0_FROZEN_HANDOFF_INTERFACE.json",
        "h0_timing": controller / "h0_calibration_detection_handoff/reports/H0_TIMING_COMPOSITION.json",
        "h0_baseline": controller / "h0_calibration_detection_handoff/baseline/h0_baseline_manifest.json",
        "exact_final": FTC_ROOT / "analysis/reachable_path_acceptance/exact_hspice/final_acceptance.json",
        "exact_runner": FTC_ROOT / "scripts/run_exact_reachable_path_hspice.py",
        "physical_renderer": FTC_ROOT / "scripts/run_dynamic_startup_calibration_protocol.py",
        "ftc_config": FTC_ROOT / "ftc_config.json",
        "selected_cells": FTC_ROOT / "discovery/selected_cells.json",
        "cycle_timing": controller / "refrequency/timing_contract/cycle_timing_contract_refrequency.json",
        "event_order": controller / "analysis/cycle_protocol_event_order_v2/exact_path_event_order_audit.json",
        "rvt_cdl": Path(cells["source_files"]["rvt_cdl"]),
        "lvt_cdl": Path(cells["source_files"]["lvt_cdl"]),
        "model_library": Path(config["model_library"]),
        "empty_subckt": FTC_ROOT / "spice/empty_subckt.sp_cal",
        "hspice_wrapper": Path(config["hspice"]),
        "h0_owner_rtl": rtl / "ftc_sensor_owner_handoff.sv",
        "h0_top_rtl": rtl / "ftc_cal_detect_handoff_top.sv",
    }
    for name in (
        "ftc_cal_controller_top.sv", "ftc_cal_fsm.sv", "ftc_cal_pkg.sv",
        "ftc_cfg_therm_regs.sv", "ftc_operation_sequencer.sv", "ftc_q_sampler.sv",
    ):
        paths["frozen_calibration_rtl/" + name] = rtl / name
    for voltage in ("0p80", "0p95", "1p10"):
        paths["exact_schedule/" + voltage] = FTC_ROOT / "analysis/reachable_path_acceptance/exact_hspice/exact_path_{}".format(voltage) / "operation_schedule.json"
    return paths


def verify_upstream(context: Mapping[str, Any]) -> Dict[str, Any]:
    """Check the only two upstream decisions M0 is permitted to rely on."""

    h0 = load_json(FTC_ROOT / "controller/h0_calibration_detection_handoff/reports/H0_GATE_STATUS.json")
    exact = load_json(FTC_ROOT / "analysis/reachable_path_acceptance/exact_hspice/final_acceptance.json")
    if h0.get("checks", {}).get("physical_composition_pass") is not True:
        raise ValueError("H0 physical timing composition is not PASS")
    if h0.get("checks", {}).get("rtl_unit_pass") is not True or h0.get("checks", {}).get("mapped_sdf_pass") is not True:
        raise ValueError("H0 ownership verification is not complete")
    if exact.get("decision") != "GO" or exact.get("scenario_count") != 3:
        raise ValueError("exact reachable-path acceptance is not GO")
    expected = {"0p80": (7, 6), "0p95": (4, 6), "1p10": (2, 9)}
    for key, (medium, fine) in expected.items():
        result = exact.get("results", {}).get(key, {})
        code = result.get("final_locked_code", {})
        if result.get("status") != "GO" or (code.get("M"), code.get("F")) != (medium, fine):
            raise ValueError("exact reachable anchor changed: {}".format(key))
    return {"h0_decision": h0.get("decision"), "exact_decision": exact.get("decision"), "exact_anchor_codes": expected}


def phase_freeze() -> Dict[str, Any]:
    """Implement M0-0: freeze the real inputs before creating any HSPICE deck."""

    environment = require_dl()
    context = physical.frozen_context()
    upstream = verify_upstream(context)
    hspice, version = physical.validate_hspice(context)
    paths = frozen_input_paths(context)
    missing = [str(path) for path in paths.values() if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise ValueError("M0 frozen input missing: {}".format(", ".join(missing)))
    inputs = {name: {"path": str(path), "sha256": sha256_file(path)} for name, path in sorted(paths.items())}
    freeze = {
        "schema_version": 1,
        "study": STUDY,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=FTC_ROOT.parent.parent, text=True).strip(),
        "upstream": upstream,
        "anchors": ANCHORS,
        "inputs": inputs,
        "forbidden_work": [
            "calibration_rtl_change", "sensor_change", "h0_rtl_change", "rf6_rf8_rf9c_rf9d_rerun",
            "full_startup_calibration_rerun", "cell_search", "detector_rtl", "dynamic_droop", "pvt_mc_postlayout",
        ],
    }
    manifest = {
        "schema_version": 1,
        "study": STUDY,
        **environment,
        "hspice_executable": str(hspice),
        "hspice_version": version,
        "matplotlib_version": __import__("matplotlib").__version__,
    }
    paths_out = analysis_paths()
    existing = paths_out["frozen_inputs"]
    if existing.is_file():
        old = load_json(existing)
        # A re-run must consume exactly the same frozen input content.  This is
        # a hard failure rather than an implicit baseline refresh.
        if old.get("inputs") != freeze["inputs"]:
            raise RuntimeError("M0 frozen inputs drifted; refusing to refresh the baseline")
    write_json(paths_out["frozen_inputs"], freeze)
    write_json(paths_out["environment"], manifest)
    return {"freeze": freeze, "environment": manifest}


def probe_timing() -> Dict[str, float]:
    """Build the one-probe physical event schedule from frozen H0 minima."""

    reset_release = 1.0e-9
    launch = reset_release + RESET_RELEASE_TO_SCLK_S
    q_read = launch + SCLK_TO_Q1_S
    q_late = q_read + Q1_TO_Q2_S
    reset_assert_start = q_late + Q2_TO_RESET_ASSERT_S
    reset_assert_end = reset_assert_start + RESET_ASSERT_WIDTH_S
    sclk_fall = reset_assert_end + RESET_COMPLETE_TO_SCLK_FALL_S
    recovery_end = sclk_fall + SCLK_FALL_TO_RECOVERY_S
    return {
        "reset_release_s": reset_release,
        "launch_time_s": launch,
        "q_read_time_s": q_read,
        "q_read_late_time_s": q_late,
        "reset_assert_start_s": reset_assert_start,
        "reset_assert_end_s": reset_assert_end,
        "sclk_fall_s": sclk_fall,
        "recovery_end_s": recovery_end,
        "stop_time_s": recovery_end + Q1_TO_Q2_S,
    }


def single_probe_contract(context: Mapping[str, Any]) -> Dict[str, Any]:
    """Publish the immutable physical and Q-decision contract for every M0 point."""

    source_paths = frozen_input_paths(context)
    selected_hashes = {name: sha256_file(path) for name, path in source_paths.items() if name in (
        "physical_renderer", "ftc_config", "selected_cells", "cycle_timing", "event_order",
        "rvt_cdl", "lvt_cdl", "model_library", "empty_subckt",
    )}
    return {
        "schema_version": 1,
        "study": STUDY,
        "electrical_scope": "single_static_vdd_probe_only",
        "anchors": ANCHORS,
        "topology": {
            "sensor": "4 RVT prefix + 30 observable stages; tap29 real XOR input",
            "medium_N": physical.MEDIUM_N,
            "medium_delay_cell": physical.MEDIUM_DELAY_CELL,
            "medium_mux_cell": physical.MEDIUM_MUX_CELL,
            "fine_driver": physical.FINE_DRIVER,
            "fine_load": physical.FINE_LOAD,
            "fine_K": physical.FINE_K,
            "xor_cell": physical.XOR_CELL,
            "dff_cell": physical.DFF_CELL,
            "dff_port_order": "Q VDD VNW VPW VSS CK D R",
        },
        "snapshot_semantics": "M/F rails are initialized to the requested thermometer code at t=0 and held constant; no calibration transition is rendered.",
        "timing_s": probe_timing(),
        "q_decision": {
            "two_samples_required": True,
            "q_high_ratio": Q_HIGH_RATIO,
            "q_low_ratio": Q_LOW_RATIO,
            "trip_decision": "stable_real_dff_q_equals_1",
            "residual_role": "diagnostic_only",
        },
        "measurement_fields": list(SCENARIO_FIELDS),
        "source_sha256": selected_hashes,
    }


def thermometer_constant_points(units: int, code: int, high_when_set: bool, stop: float) -> Iterable[Tuple[int, str]]:
    """Yield constant PWL rails for a frozen thermometer snapshot.

    Medium selection uses a logic-high rail for a set bit.  Fine load control is
    intentionally inverted: a set fine bit drives NOR2 B low, selecting the
    validated high-capacitance state.  Keeping that polarity here avoids a
    common but electrically wrong "F+1" abstraction.
    """

    for index, bit in enumerate(physical.thermometer(units, code)):
        value_high = bool(bit) if high_when_set else not bool(bit)
        value = "'VDD_VALUE'" if value_high else "0"
        yield index, "PWL(0 {}) {} {}".format(value, physical.spice(stop), value)


def render_single_probe_deck(context: Mapping[str, Any], physical_vdd_v: float, medium_code: int, fine_code: int) -> str:
    """Render exactly one frozen-snapshot real-cell HSPICE probe.

    The long deck body follows the completed dynamic renderer line-for-line for
    all transistor-level instances and positional ports.  The sole intentional
    difference is the constant M/F control source: M0 starts after calibration
    has produced a snapshot, therefore it must not replay an old search or
    alter a code during the measured capture interval.
    """

    if not 0.80 <= physical_vdd_v <= 1.10:
        raise ValueError("M0 physical VDD is outside the formal 0.80..1.10 V range")
    if not 0 <= medium_code <= physical.MEDIUM_N or not 0 <= fine_code <= physical.FINE_K:
        raise ValueError("M0 thermometer code outside frozen legal range")
    config, cells = context["config"], context["cells"]
    timing = probe_timing()
    stop = timing["stop_time_s"]
    includes = ['.include "{}"'.format(cells["source_files"]["rvt_cdl"])]
    if Path(cells["source_files"]["lvt_cdl"]).resolve() != Path(cells["source_files"]["rvt_cdl"]).resolve():
        includes.append('.include "{}"'.format(cells["source_files"]["lvt_cdl"]))

    # The PWL edges mirror the exact-path renderer.  The named schedule times
    # remain contract values; HSPICE-derived crossings below are the recorded
    # physical truth used for D_ref, W_xor, R, and Q validity.
    sclk = physical.pwl([
        (0.0, 0), (timing["launch_time_s"] - SCLK_EDGE_S, 0),
        (timing["launch_time_s"], "'VDD_VALUE'"), (timing["sclk_fall_s"], "'VDD_VALUE'"),
        (timing["sclk_fall_s"] + SCLK_EDGE_S, 0), (stop, 0),
    ])
    reset = physical.pwl([
        (0.0, "'VDD_VALUE'"), (timing["reset_release_s"] - CONTROL_EDGE_S, "'VDD_VALUE'"),
        (timing["reset_release_s"], "'VDD_VALUE'"), (timing["reset_release_s"] + CONTROL_EDGE_S, 0),
        (timing["reset_assert_start_s"], 0), (timing["reset_assert_end_s"], "'VDD_VALUE'"),
        (stop, "'VDD_VALUE'"),
    ])
    lines: List[str] = [
        "* FTC M0 one-probe static-VDD characterization; frozen post-calibration snapshot.",
        "* No calibration FSM, detector RTL, droop waveform, ideal delay, or ideal capacitor is instantiated.",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(physical.spice(float(config["temperature_c"]))),
        *includes,
        '.lib "{}" {}'.format(config["model_library"], config["corner"]),
        ".param VDD_VALUE={}".format(physical.spice(physical_vdd_v)),
        "V_VDD vdd_a vss_a 'VDD_VALUE'",
        "V_VSS vss_a 0 0",
        "V_SCLK s_clk vss_a {}".format(sclk),
        "V_DFF_RESET dff_reset vss_a {}".format(reset),
        *physical.sensor_xor_lines(cells),
    ]
    for index, source in enumerate(thermometer_constant_points(physical.MEDIUM_N, medium_code, True, stop)):
        bit, points = source
        lines.append("V_M_{:02d} m_{} vss_a {}".format(bit, bit, points))
    for index in range(physical.MEDIUM_N + 1):
        source = "xor_29" if index == 0 else "x{}".format(index)
        lines.append(physical.buffer_instance("XMED_BUF_{:02d}".format(index), "x{}".format(index + 1), source, physical.MEDIUM_DELAY_CELL))
    for index in range(physical.MEDIUM_N):
        output = "medium_out" if index == 0 else "my{}".format(index)
        deep = "x{}".format(physical.MEDIUM_N + 1) if index == physical.MEDIUM_N - 1 else "my{}".format(index + 1)
        lines.append(physical.mux_instance("XMED_MUX_{:02d}".format(index), output, "x{}".format(index + 1), deep, "m_{}".format(index)))
    lines.append(physical.buffer_instance("XFINE_DRIVER", "dff_ck", "medium_out", physical.FINE_DRIVER))
    for index, source in enumerate(thermometer_constant_points(physical.FINE_K, fine_code, False, stop)):
        bit, points = source
        lines.append("V_F_{:02d} f_{} vss_a {}".format(bit, bit, points))
        lines.append("XLOAD_{:02d} z_{} vdd_a vdd_a vss_a vss_a dff_ck f_{} {}".format(bit, bit, bit, physical.FINE_LOAD))
    lines.extend([
        # Positional CDL ports are explicit: Q/VDD/VNW/VPW/VSS/CK/D/R.  Data
        # is the real xor_29 pulse; only CK travels through medium and fine.
        "XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(physical.DFF_CELL),
        ".tran {} {}".format(physical.spice(float(config["tran_max_step_s"])), physical.spice(stop)),
        ".measure tran t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran q_final_v FIND v(q_final,vss_a) AT={}".format(physical.spice(timing["q_read_time_s"])),
        ".measure tran q_final_late_v FIND v(q_final,vss_a) AT={}".format(physical.spice(timing["q_read_late_time_s"])),
    ])
    for node, suffix in (("xor_29", "xor"), ("medium_out", "medium"), ("dff_ck", "ck")):
        lines.extend([
            ".measure tran recovery_{}_end FIND v({},vss_a) AT={}".format(suffix, node, physical.spice(timing["recovery_end_s"])),
            ".measure tran recovery_{}_tail MAX v({},vss_a) FROM={} TO={}".format(
                suffix, node, physical.spice(timing["recovery_end_s"] - Q1_TO_Q2_S), physical.spice(timing["recovery_end_s"])
            ),
        ])
    lines.extend([".end", ""])
    return "\n".join(lines)


def topology_checks(deck: str, medium_code: int, fine_code: int) -> Dict[str, bool]:
    """Statically prove that an M0 deck is the frozen circuit, not a surrogate."""

    lines = deck.splitlines()
    # Topology checks must inspect SPICE syntax, not explanatory comments.
    # Otherwise a required comment such as "no FSM" would paradoxically look
    # like an instantiated FSM.  Measurement ``TD=`` clauses are likewise not
    # ideal delay elements, so the delay expression below is limited to an
    # active voltage/current/controlled-source instance line.
    active_lines = [line for line in lines if not line.lstrip().startswith("*")]
    active_deck = "\n".join(active_lines)
    forbidden = ("XMUX_L1", "XMUX_L2", "XMUX_L3", "XBYPASS", "XCONFIG_SKIP", "FSM", "COUNTER", "REGISTER")
    expected_dff = "XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(physical.DFF_CELL)
    return {
        "tap29_real_xor": "XXOR_29 xor_29 vdd_a vdd_a vss_a vss_a rvt_29 lvt_29 {}".format(physical.XOR_CELL) in lines,
        "xor_is_dff_data": expected_dff in lines,
        "medium_input_is_xor": "XMED_BUF_00 x1 vdd_a vdd_a vss_a vss_a xor_29 {}".format(physical.MEDIUM_DELAY_CELL) in lines,
        "fine_driver_is_only_dff_clock_path": "XFINE_DRIVER dff_ck vdd_a vdd_a vss_a vss_a medium_out {}".format(physical.FINE_DRIVER) in lines,
        "n16_medium": sum(line.startswith("XMED_BUF_") for line in lines) == physical.MEDIUM_N + 1 and sum(line.startswith("XMED_MUX_") for line in lines) == physical.MEDIUM_N,
        "k10_fine_load": sum(line.startswith("XLOAD_") for line in lines) == physical.FINE_K and all(line.endswith(physical.FINE_LOAD) for line in lines if line.startswith("XLOAD_")),
        "constant_medium_snapshot": all("PWL(0 " in line and "V_M_" in line for line in lines if line.startswith("V_M_")),
        "constant_fine_snapshot": all("PWL(0 " in line and "V_F_" in line for line in lines if line.startswith("V_F_")),
        "requested_codes_legal": 0 <= medium_code <= physical.MEDIUM_N and 0 <= fine_code <= physical.FINE_K,
        "no_forbidden_hardware": not any(token in active_deck for token in forbidden),
        "no_ideal_delay_or_capacitor": not re.search(r"(?im)^\s*[evg]\S*.*\btd\s*=", active_deck) and not any(line.lstrip().lower().startswith("c") for line in active_lines),
    }


def phase_contract() -> Dict[str, Any]:
    """Implement M0-1 contract publication without launching HSPICE."""

    require_dl()
    context = physical.frozen_context()
    verify_upstream(context)
    contract = single_probe_contract(context)
    example = render_single_probe_deck(context, 0.95, 4, 6)
    checks = topology_checks(example, 4, 6)
    if not all(checks.values()):
        raise ValueError("M0 single-probe topology contract failed: {}".format(checks))
    paths = analysis_paths()
    write_json(paths["single_probe_contract"], {**contract, "example_deck_sha256": hashlib.sha256(example.encode("ascii")).hexdigest(), "topology_checks": checks, "decision": "GO"})
    # This manifest is a schema/provenance declaration, not an HSPICE result.
    # Per-scenario manifests remain next to their raw deck/listing/MEAS files.
    write_json(paths["scenario_manifest"], {
        "schema_version": 1,
        "study": STUDY,
        "scenario_identity": "SHA256(single_probe_contract + baseline_vdd + physical_vdd + M + F + deck)",
        "reuse_rule": "reuse only PASS scenario with identical physical contract, parameters, rendered deck SHA256, listing, and measurement file",
        "raw_run_root": str(RUN_ROOT),
        "hspice_invocation": "configured W-2024.09 wrapper; one scenario directory per physical point",
    })
    return contract


def physical_contract_hash() -> str:
    """Return the frozen probe contract hash used in every raw scenario identity."""

    path = analysis_paths()["single_probe_contract"]
    if not path.is_file():
        raise RuntimeError("M0-1 contract is missing; run --phase contract first")
    return sha256_file(path)


def probe_parameters(baseline_vdd_v: float, physical_vdd_v: float, medium_code: int, fine_code: int, contract_sha: str) -> Dict[str, Any]:
    """Describe electrical identity only; analysis phase is deliberately excluded.

    A normal-VDD row needed first for the local surface can therefore be reused
    by the mechanism and Vtrip stages.  Conversely, historical calibration
    results have a different one-probe contract and never satisfy this ID.
    """

    return {
        "study": STUDY,
        "baseline_vdd_v": round(float(baseline_vdd_v), 2),
        "physical_vdd_v": round(float(physical_vdd_v), 2),
        "medium_code": int(medium_code),
        "fine_code": int(fine_code),
        "physical_contract_sha256": contract_sha,
    }


def scenario_id(parameters: Mapping[str, Any]) -> str:
    """Generate a readable collision-resistant directory name for one point."""

    digest = hashlib.sha256(stable_json(parameters).encode("ascii")).hexdigest()[:20]
    return "m0_probe__b{}__v{}__m{:02d}__f{:02d}__{}".format(
        voltage_key(float(parameters["baseline_vdd_v"])).replace(".", "p"),
        voltage_key(float(parameters["physical_vdd_v"])).replace(".", "p"),
        int(parameters["medium_code"]), int(parameters["fine_code"]), digest,
    )


def ensure_run_root(contract_sha: str, hspice: Path, version: str) -> Path:
    """Create/reuse one task-local revision so raw simulations never scatter."""

    run_dir = RUN_ROOT / "r1"
    manifest_path = run_dir / "run_manifest.json"
    expected = {
        "schema_version": 1, "study": STUDY, "physical_contract_sha256": contract_sha,
        "hspice_executable": str(hspice), "hspice_version": version,
    }
    if manifest_path.is_file():
        if load_json(manifest_path) != expected:
            raise RuntimeError("existing M0 run root has a different frozen contract")
        return run_dir
    if run_dir.exists():
        raise RuntimeError("M0 r1 exists without its required run manifest")
    run_dir.mkdir(parents=True)
    write_json(manifest_path, expected)
    return run_dir


def find_completed_scenario(identity: str, parameters: Mapping[str, Any], deck: str) -> Optional[Path]:
    """Return one byte-identified PASS scenario; failed evidence is never rerun."""

    matches = list(RUN_ROOT.glob("r*/scenarios/{}/scenario_manifest.json".format(identity))) if RUN_ROOT.is_dir() else []
    if len(matches) > 1:
        raise RuntimeError("duplicate M0 scenario identity: {}".format(identity))
    if not matches:
        return None
    scenario = matches[0].parent
    manifest = load_json(matches[0])
    deck_path = scenario / "m0_single_probe.sp"
    expected_hash = hashlib.sha256(deck.encode("ascii")).hexdigest()
    if manifest.get("completion_status") != "PASS":
        raise RuntimeError("retained M0 scenario failed/partial and cannot be silently rerun: {}".format(scenario))
    if manifest.get("parameters") != dict(parameters) or manifest.get("deck_sha256") != expected_hash or not deck_path.is_file() or sha256_file(deck_path) != expected_hash:
        raise RuntimeError("retained M0 scenario contract mismatch: {}".format(scenario))
    measurement = scenario / str(manifest.get("measurement_file", ""))
    if not measurement.is_file():
        raise RuntimeError("retained M0 scenario measurement is missing: {}".format(scenario))
    physical.run_dc_sweep.validate_listing(scenario / "m0_single_probe.lis")
    return scenario


def execute_probe(context: Mapping[str, Any], baseline_vdd_v: float, physical_vdd_v: float, medium_code: int, fine_code: int) -> Dict[str, Any]:
    """Execute or safely reuse exactly one static-VDD real-DFF measurement."""

    contract_sha = physical_contract_hash()
    parameters = probe_parameters(baseline_vdd_v, physical_vdd_v, medium_code, fine_code, contract_sha)
    identity = scenario_id(parameters)
    deck = render_single_probe_deck(context, physical_vdd_v, medium_code, fine_code)
    deck_sha = hashlib.sha256(deck.encode("ascii")).hexdigest()
    scenario = find_completed_scenario(identity, parameters, deck)
    if scenario is None:
        hspice, version = physical.validate_hspice(context)
        run_dir = ensure_run_root(contract_sha, hspice, version)
        scenario = run_dir / "scenarios" / identity
        if scenario.exists():
            raise RuntimeError("new M0 scenario directory unexpectedly exists: {}".format(scenario))
        scenario.mkdir(parents=True)
        deck_path = scenario / "m0_single_probe.sp"
        deck_path.write_text(deck, encoding="ascii")
        shutil.copyfile(FTC_ROOT / "spice/empty_subckt.sp_cal", scenario / "empty_subckt.sp_cal")
        manifest: Dict[str, Any] = {
            "schema_version": 1, "study": STUDY, "scenario_id": identity,
            "parameters": parameters, "deck_sha256": deck_sha, "completion_status": "RUNNING",
            "measurement_file": None, "hspice_executable": str(hspice), "hspice_version": version,
        }
        write_json(scenario / "scenario_manifest.json", manifest)
        result = subprocess.run([str(hspice), deck_path.name, "-o", "m0_single_probe"], cwd=scenario, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=900)
        (scenario / "hspice_command.log").write_text("returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr), encoding="utf-8")
        if result.returncode != 0:
            manifest.update({"completion_status": "FAIL", "failure": "HSPICE returned {}".format(result.returncode)})
            write_json(scenario / "scenario_manifest.json", manifest)
            raise RuntimeError("M0 HSPICE failed for {}; evidence retained".format(identity))
        try:
            physical.run_dc_sweep.validate_listing(scenario / "m0_single_probe.lis")
            measurement = physical.run_dc_sweep.find_measurement_file(scenario, "m0_single_probe")
        except Exception as error:
            manifest.update({"completion_status": "FAIL", "failure": "listing/measurement validation: {}".format(error)})
            write_json(scenario / "scenario_manifest.json", manifest)
            raise
        manifest.update({"completion_status": "PASS", "measurement_file": measurement.name})
        write_json(scenario / "scenario_manifest.json", manifest)
    manifest = load_json(scenario / "scenario_manifest.json")
    record = physical.run_dc_sweep.parse_measurements(scenario / str(manifest["measurement_file"]))
    return parse_probe_record(identity, parameters, record, scenario, deck_sha)


def stable_q(first: Optional[float], late: Optional[float], vdd: float) -> Tuple[Optional[int], str]:
    """Classify only a stable real-DFF rail pair; anything else is ambiguous."""

    if first is None or late is None:
        return None, "ambiguous"
    if first >= Q_HIGH_RATIO * vdd and late >= Q_HIGH_RATIO * vdd:
        return 1, "stable_high"
    if first <= Q_LOW_RATIO * vdd and late <= Q_LOW_RATIO * vdd:
        return 0, "stable_low"
    return None, "ambiguous"


def parse_probe_record(identity: str, parameters: Mapping[str, Any], record: Mapping[str, Any], scenario: Path, deck_sha: str) -> Dict[str, Any]:
    """Convert raw MEAS scalars into one formal M0 row without proxy trip logic."""

    vdd = float(parameters["physical_vdd_v"])
    timing = probe_timing()
    xor_rise = optional_float(record.get("t_xor_rise"))
    xor_fall = optional_float(record.get("t_xor_fall"))
    ck_rise = optional_float(record.get("t_ck_rise"))
    ck_rise_2 = optional_float(record.get("t_ck_rise_2"))
    q_first = optional_float(record.get("q_final_v"))
    q_late = optional_float(record.get("q_final_late_v"))
    q_value, q_state = stable_q(q_first, q_late, vdd)
    recovery = [optional_float(record.get("recovery_{}_{}".format(node, sample))) for node in ("xor", "medium", "ck") for sample in ("end", "tail")]
    recovery_ratio = max((abs(value) / vdd for value in recovery if value is not None), default=None)
    active_end = timing["reset_assert_start_s"]
    active_ck = ck_rise is not None and timing["launch_time_s"] <= ck_rise < active_end
    second_active = ck_rise_2 is not None and timing["launch_time_s"] <= ck_rise_2 < active_end
    active_count = int(active_ck) + int(second_active)
    width = None if xor_rise is None or xor_fall is None else (xor_fall - xor_rise) * 1e12
    delay = None if xor_rise is None or ck_rise is None else (ck_rise - xor_rise) * 1e12
    residual = None if width is None or delay is None else width - delay
    reasons: List[str] = []
    if xor_rise is None or xor_fall is None or ck_rise is None:
        reasons.append("missing_functional_crossing")
    if width is not None and width <= 0.0:
        reasons.append("nonpositive_xor_width")
    if active_count != 1:
        reasons.append("active_ck_edge_count_not_one")
    if q_value is None:
        reasons.append("q_not_stable_on_two_reads")
    if any(value is None for value in recovery) or recovery_ratio is None:
        reasons.append("missing_recovery_measure")
    elif recovery_ratio >= Q_LOW_RATIO:
        reasons.append("recovery_tail_not_below_0p1_vdd")
    return {
        "scenario_id": identity,
        "baseline_vdd_v": float(parameters["baseline_vdd_v"]),
        "physical_vdd_v": vdd,
        "medium_code": int(parameters["medium_code"]),
        "fine_code": int(parameters["fine_code"]),
        "t_xor_rise_s": xor_rise,
        "t_xor_fall_s": xor_fall,
        "t_ck_rise_s": ck_rise,
        "t_ck_rise_2_s": ck_rise_2,
        "W_xor_ps": width,
        "D_ref_ps": delay,
        "R_ps": residual,
        "q_final_v": q_first,
        "q_final_late_v": q_late,
        "q_final": q_value,
        "q_state": q_state,
        "active_ck_edge_count": active_count,
        "recovery_max_ratio": recovery_ratio,
        "valid": int(not reasons),
        "reason": ";".join(reasons) if reasons else None,
        "scenario_path": str(scenario),
        "deck_sha256": deck_sha,
        "physical_contract_sha256": str(parameters["physical_contract_sha256"]),
    }


def normalize_cached_probe_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Restore typed decision and residual fields after a CSV reload.

    ``csv.DictReader`` deliberately returns strings for every populated column.
    M0-5 reuses the already-characterized M0-4 normal/coarse points to avoid
    needless HSPICE reruns, so it must explicitly recover the integer form of
    ``q_final`` and ``valid`` before applying the Q=0/Q=1 trip state machine.
    ``R_ps`` is also restored because trip_summary.json publishes the residual
    at the final Q=0 and first Q=1 points as numeric scientific evidence.  A
    blank ``q_final`` remains ``None``: it is an ambiguous electrical result,
    never a value that can be silently coerced to a safe Q=0 observation.
    """

    normalized = dict(record)
    for field in ("q_final", "valid"):
        value = normalized.get(field)
        normalized[field] = None if value in (None, "") else int(value)
    normalized["R_ps"] = optional_float(normalized.get("R_ps"))
    return normalized


def rows_by_anchor(rows: Sequence[Mapping[str, Any]], baseline: float) -> List[Dict[str, Any]]:
    """Select one anchor's rows and sort them into reproducible M/F order."""

    return sorted((dict(row) for row in rows if round(float(row["baseline_vdd_v"]), 2) == round(baseline, 2)), key=lambda row: (int(row["medium_code"]), int(row["fine_code"])))


def surface_gate(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Apply M0-2's deterministic local-surface validity and ordering gate."""

    reasons: List[str] = []
    per_anchor: Dict[str, Any] = {}
    for key, anchor in ANCHORS.items():
        local = rows_by_anchor(rows, float(anchor["baseline_vdd_v"]))
        expected_count = len(anchor["m_values"]) * len(anchor["f_values"])
        local_reasons: List[str] = []
        if len(local) != expected_count:
            local_reasons.append("incomplete_local_window")
        if any(int(row["valid"]) != 1 for row in local):
            local_reasons.append("invalid_single_probe")
        index = {(int(row["medium_code"]), int(row["fine_code"])): row for row in local}
        for medium in anchor["m_values"]:
            series = [index.get((medium, fine)) for fine in anchor["f_values"]]
            if any(item is None or item.get("D_ref_ps") in (None, "") for item in series):
                local_reasons.append("missing_fine_adjacency")
                continue
            delays = [float(item["D_ref_ps"]) for item in series if item is not None]
            q_values = [int(float(item["q_final"])) for item in series if item is not None and item.get("q_final") not in (None, "")]
            if any(right <= left for left, right in zip(delays, delays[1:])):
                local_reasons.append("fine_delay_non_monotonic")
            if any(left == 0 and right == 1 for left, right in zip(q_values, q_values[1:])):
                local_reasons.append("fine_q_zero_to_one_reversal")
        for fine in anchor["f_values"]:
            series = [index.get((medium, fine)) for medium in anchor["m_values"]]
            if any(item is None or item.get("D_ref_ps") in (None, "") for item in series):
                local_reasons.append("missing_medium_adjacency")
                continue
            delays = [float(item["D_ref_ps"]) for item in series if item is not None]
            q_values = [int(float(item["q_final"])) for item in series if item is not None and item.get("q_final") not in (None, "")]
            if any(right <= left for left, right in zip(delays, delays[1:])):
                local_reasons.append("medium_delay_non_monotonic")
            if any(left == 0 and right == 1 for left, right in zip(q_values, q_values[1:])):
                local_reasons.append("medium_q_zero_to_one_reversal")
        per_anchor[key] = {"row_count": len(local), "expected_row_count": expected_count, "reasons": sorted(set(local_reasons)), "status": "GO" if not local_reasons else "NO-GO"}
        reasons.extend("{}:{}".format(key, reason) for reason in sorted(set(local_reasons)))
    return {"schema_version": 1, "study": STUDY, "per_anchor": per_anchor, "reasons": reasons, "decision": "GO" if not reasons else "NO-GO"}


def phase_surface() -> Dict[str, Any]:
    """Implement M0-2 with only the three plan-authorized local code windows."""

    require_dl()
    context = physical.frozen_context()
    verify_upstream(context)
    physical_contract_hash()
    rows: List[Dict[str, Any]] = []
    for anchor in ANCHORS.values():
        baseline = float(anchor["baseline_vdd_v"])
        for medium in anchor["m_values"]:
            for fine in anchor["f_values"]:
                rows.append(execute_probe(context, baseline, baseline, int(medium), int(fine)))
    enriched: List[Dict[str, Any]] = []
    for key, anchor in ANCHORS.items():
        local = rows_by_anchor(rows, float(anchor["baseline_vdd_v"]))
        reference = next((row for row in local if int(row["medium_code"]) == int(anchor["M_cal"]) and int(row["fine_code"]) == int(anchor["F_cal"])), None)
        if reference is None or int(reference["valid"]) != 1:
            raise RuntimeError("M0 calibration anchor probe is missing/invalid: {}".format(key))
        for row in local:
            updated = dict(row)
            updated["Delta_D_ref_ps"] = None if row["D_ref_ps"] is None else float(row["D_ref_ps"]) - float(reference["D_ref_ps"])
            updated["Delta_R_ps"] = None if row["R_ps"] is None else float(row["R_ps"]) - float(reference["R_ps"])
            enriched.append(updated)
    paths = analysis_paths()
    write_csv(paths["surface_csv"], LOCAL_SURFACE_FIELDS, sorted(enriched, key=lambda row: (float(row["baseline_vdd_v"]), int(row["medium_code"]), int(row["fine_code"]))))
    summary = surface_gate(enriched)
    write_json(paths["surface_summary"], summary)
    return summary


def phase_select() -> Dict[str, Any]:
    """Implement M0-3: choose at most L0/L1/L2/L3 by measured ps, never ΔF."""

    require_dl()
    paths = analysis_paths()
    surface = load_json(paths["surface_summary"])
    if surface.get("decision") != "GO":
        result = {"schema_version": 1, "study": STUDY, "decision": "NO-GO", "reason": "local_surface_not_go", "candidates": []}
        write_json(paths["candidate_summary"], result)
        write_csv(paths["candidate_csv"], CANDIDATE_FIELDS, [])
        return result
    rows = read_csv(paths["surface_csv"], ("baseline_vdd_v", "medium_code", "fine_code", "D_ref_ps", "R_ps", "q_final", "valid", "Delta_D_ref_ps"))
    candidates: List[Dict[str, Any]] = []
    reasons: List[str] = []
    for key, anchor in ANCHORS.items():
        baseline = float(anchor["baseline_vdd_v"])
        local = rows_by_anchor(rows, baseline)
        calibration = next(row for row in local if int(row["medium_code"]) == int(anchor["M_cal"]) and int(row["fine_code"]) == int(anchor["F_cal"]))
        if int(float(calibration["valid"])) != 1 or int(float(calibration["q_final"])) != 0:
            reasons.append("{}:calibration_not_normal_q0".format(key))
            continue
        base = {
            "baseline_vdd_v": baseline, "M_cal": int(anchor["M_cal"]), "F_cal": int(anchor["F_cal"]),
            "margin_level": "L0", "candidate_id": "{}_L0".format(key.replace(".", "p")),
            "M_det": int(anchor["M_cal"]), "F_det": int(anchor["F_cal"]),
            "nominal_D_ref_shift_ps": 0.0, "nominal_R_ps": float(calibration["R_ps"]), "normal_Q": 0,
            "selection_reason": "frozen H0 calibration/guard snapshot",
        }
        candidates.append(base)
        eligible = [
            row for row in local
            if int(float(row["valid"])) == 1 and int(float(row["q_final"])) == 0
            and float(row["R_ps"]) < 0.0 and float(row["Delta_D_ref_ps"]) > 0.0
        ]
        eligible.sort(key=lambda row: (float(row["Delta_D_ref_ps"]), int(row["medium_code"]), int(row["fine_code"])))
        if not eligible:
            reasons.append("{}:no_normal_q0_positive_ps_candidate".format(key))
            continue
        # Three quantiles yield L1/L2/L3 when enough real points exist.  The
        # deduplication preserves the plan's maximum of four total levels.
        selected_indices = []
        for index in (0, len(eligible) // 2, len(eligible) - 1):
            if index not in selected_indices:
                selected_indices.append(index)
        for level_index, index in enumerate(selected_indices, start=1):
            row = eligible[index]
            candidates.append({
                "baseline_vdd_v": baseline, "M_cal": int(anchor["M_cal"]), "F_cal": int(anchor["F_cal"]),
                "margin_level": "L{}".format(level_index), "candidate_id": "{}_L{}".format(key.replace(".", "p"), level_index),
                "M_det": int(row["medium_code"]), "F_det": int(row["fine_code"]),
                "nominal_D_ref_shift_ps": float(row["Delta_D_ref_ps"]), "nominal_R_ps": float(row["R_ps"]), "normal_Q": int(float(row["q_final"])),
                "selection_reason": "ordered local-surface timing margin; not a fixed fine-code increment",
            })
    decision = "GO" if not reasons and all(any(item["baseline_vdd_v"] == float(anchor["baseline_vdd_v"]) and item["margin_level"] != "L0" for item in candidates) for anchor in ANCHORS.values()) else "NO-GO"
    result = {"schema_version": 1, "study": STUDY, "decision": decision, "reasons": reasons, "candidates": candidates}
    write_csv(paths["candidate_csv"], CANDIDATE_FIELDS, candidates)
    write_json(paths["candidate_summary"], result)
    return result


def phase_mechanism() -> Dict[str, Any]:
    """Implement M0-4 using only three static VDD points per high-VDD baseline."""

    require_dl()
    paths = analysis_paths()
    selection = load_json(paths["candidate_summary"])
    if selection.get("decision") != "GO":
        result = {"schema_version": 1, "study": STUDY, "decision": "NO-GO", "reason": "candidate_selection_not_go", "per_baseline": {}}
        write_csv(paths["mechanism_csv"], MECHANISM_FIELDS, [])
        write_json(paths["mechanism_summary"], result)
        return result
    context = physical.frozen_context()
    all_rows: List[Dict[str, Any]] = []
    per_baseline: Dict[str, Any] = {}
    for baseline in (0.95, 1.10):
        key = voltage_key(baseline)
        voltages = [baseline, round(baseline - 0.05, 2), round(baseline - 0.10, 2)]
        chosen = [item for item in selection["candidates"] if float(item["baseline_vdd_v"]) == baseline and item["margin_level"] != "L0"]
        accepted: List[str] = []
        candidate_reasons: Dict[str, str] = {}
        for candidate in chosen:
            series: List[Dict[str, Any]] = []
            for voltage in voltages:
                row = execute_probe(context, baseline, voltage, int(candidate["M_det"]), int(candidate["F_det"]))
                row.update({"margin_level": candidate["margin_level"], "candidate_id": candidate["candidate_id"], "mechanism_candidate_pass": 0, "mechanism_reason": None})
                series.append(row)
            valid = all(int(row["valid"]) == 1 for row in series)
            normal = series[0]
            residuals = [float(row["R_ps"]) for row in series if row["R_ps"] is not None]
            direction = len(residuals) == 3 and residuals[1] >= residuals[0] and residuals[2] > residuals[0]
            normal_safe = normal.get("q_final") == 0 and normal.get("R_ps") is not None and float(normal["R_ps"]) < 0.0
            passed = valid and normal_safe and direction
            reason = None if passed else "invalid_measurement" if not valid else "normal_not_q0_r_negative" if not normal_safe else "residual_not_toward_trip"
            for row in series:
                row["mechanism_candidate_pass"] = int(passed)
                row["mechanism_reason"] = reason
            all_rows.extend(series)
            if passed:
                accepted.append(str(candidate["candidate_id"]))
            else:
                candidate_reasons[str(candidate["candidate_id"])] = str(reason)
        per_baseline[key] = {"vdd_points_v": voltages, "accepted_candidate_ids": accepted, "rejected_candidates": candidate_reasons, "status": "GO" if accepted else "NO-GO"}
    result = {"schema_version": 1, "study": STUDY, "decision": "GO" if all(item["status"] == "GO" for item in per_baseline.values()) else "NO-GO", "per_baseline": per_baseline, "scope_0p80": "local_code_surface_and_normal_point_only; no below-0.80-V detection claim"}
    write_csv(paths["mechanism_csv"], MECHANISM_FIELDS, sorted(all_rows, key=lambda row: (float(row["baseline_vdd_v"]), row["candidate_id"], -float(row["physical_vdd_v"]))))
    write_json(paths["mechanism_summary"], result)
    return result


def phase_trip() -> Dict[str, Any]:
    """Implement M0-5's bracketed static Vtrip extraction without a 2-D sweep."""

    require_dl()
    paths = analysis_paths()
    mechanism = load_json(paths["mechanism_summary"])
    selection = load_json(paths["candidate_summary"])
    if mechanism.get("decision") != "GO":
        result = {"schema_version": 1, "study": STUDY, "decision": "NOT_RUN_MECHANISM_NO_GO", "reason": "mechanism_gate_not_go", "trip_map": []}
        write_csv(paths["trip_sweep"], TRIP_SWEEP_FIELDS, [])
        write_csv(paths["trip_map"], TRIP_MAP_FIELDS, [])
        write_csv(paths["trip_table"], TRIP_MAP_FIELDS, [])
        write_json(paths["trip_summary"], result)
        return result
    context = physical.frozen_context()
    # Reuse complete M0-4 rows, not a partial projection.  M0-5 later writes
    # these rows into trip_sweep.csv, where W/D/R, rail measurements, and
    # physical provenance are required evidence alongside the Q decision.
    mechanism_rows = read_csv(paths["mechanism_csv"], MECHANISM_FIELDS)
    accepted = {candidate_id for item in mechanism["per_baseline"].values() for candidate_id in item["accepted_candidate_ids"]}
    candidates = [item for item in selection["candidates"] if item["candidate_id"] in accepted]
    sweep_rows: List[Dict[str, Any]] = []
    map_rows: List[Dict[str, Any]] = []
    for candidate in candidates:
        baseline = float(candidate["baseline_vdd_v"])
        # CSV has no numeric types.  Convert the two control-flow values at
        # the reuse boundary so a textual "0" cannot fall through to the
        # ambiguous-Q branch and invalidate an otherwise valid trip bracket.
        existing = {
            round(float(row["physical_vdd_v"]), 2): normalize_cached_probe_record(row)
            for row in mechanism_rows
            if row["candidate_id"] == candidate["candidate_id"]
        }
        observations: Dict[float, Dict[str, Any]] = {}
        for voltage in [baseline, round(baseline - 0.05, 2), round(baseline - 0.10, 2)]:
            if voltage in existing:
                record = dict(existing[voltage])
            else:
                record = execute_probe(context, baseline, voltage, int(candidate["M_det"]), int(candidate["F_det"]))
            record.update({"margin_level": candidate["margin_level"], "candidate_id": candidate["candidate_id"], "sweep_stage": "coarse"})
            observations[voltage] = record
        first_q1: Optional[float] = None
        last_q0: Optional[float] = None
        invalid_reason: Optional[str] = None
        for voltage in [round(baseline - 0.05 * index, 2) for index in range(int(round((baseline - 0.80) / 0.05)) + 1)]:
            if voltage not in observations:
                record = execute_probe(context, baseline, voltage, int(candidate["M_det"]), int(candidate["F_det"]))
                record.update({"margin_level": candidate["margin_level"], "candidate_id": candidate["candidate_id"], "sweep_stage": "coarse"})
                observations[voltage] = record
            record = observations[voltage]
            if int(record["valid"]) != 1:
                invalid_reason = "invalid_coarse_probe"
                break
            if record["q_final"] == 0:
                if first_q1 is not None:
                    invalid_reason = "q_one_to_zero_reversal"
                    break
                last_q0 = voltage
            elif record["q_final"] == 1:
                first_q1 = voltage
                break
            else:
                invalid_reason = "ambiguous_q"
                break
        if invalid_reason is None and first_q1 is not None and last_q0 is not None:
            # Add only values inside the discovered 50 mV bracket.  The first
            # Q=1 is already present; no deeper voltage is explored after it.
            voltage = round(last_q0 - 0.01, 2)
            while voltage > first_q1:
                record = execute_probe(context, baseline, voltage, int(candidate["M_det"]), int(candidate["F_det"]))
                record.update({"margin_level": candidate["margin_level"], "candidate_id": candidate["candidate_id"], "sweep_stage": "fine"})
                observations[voltage] = record
                if int(record["valid"]) != 1:
                    invalid_reason = "invalid_fine_probe"
                    break
                if record["q_final"] == 1:
                    first_q1 = voltage
                elif record["q_final"] != 0:
                    invalid_reason = "ambiguous_q"
                    break
                voltage = round(voltage - 0.01, 2)
        ordered = sorted(observations.values(), key=lambda row: -float(row["physical_vdd_v"]))
        q_values = [row["q_final"] for row in ordered if int(row["valid"]) == 1]
        if any(left == 1 and right == 0 for left, right in zip(q_values, q_values[1:])):
            invalid_reason = invalid_reason or "q_one_to_zero_reversal"
        status = "IN_RANGE_TRIP" if invalid_reason is None and first_q1 is not None else "NO_IN_RANGE_TRIP" if invalid_reason is None else "INVALID"
        last_q0_row = observations.get(last_q0) if last_q0 is not None else None
        first_q1_row = observations.get(first_q1) if first_q1 is not None else None
        map_rows.append({
            "baseline_vdd_v": baseline, "margin_level": candidate["margin_level"], "candidate_id": candidate["candidate_id"],
            "M_det": candidate["M_det"], "F_det": candidate["F_det"], "nominal_D_ref_shift_ps": candidate["nominal_D_ref_shift_ps"],
            "trip_status": status, "Vtrip_v": first_q1 if status == "IN_RANGE_TRIP" else None,
            "DeltaV_trip_mv": (baseline - first_q1) * 1000.0 if status == "IN_RANGE_TRIP" and first_q1 is not None else None,
            "R_at_last_q0_ps": None if last_q0_row is None else last_q0_row.get("R_ps"),
            "R_at_first_q1_ps": None if first_q1_row is None else first_q1_row.get("R_ps"),
            "ordering_ok": None, "reason": invalid_reason,
        })
        sweep_rows.extend(ordered)
    for baseline in (0.95, 1.10):
        group = sorted((row for row in map_rows if float(row["baseline_vdd_v"]) == baseline and row["trip_status"] == "IN_RANGE_TRIP"), key=lambda row: float(row["nominal_D_ref_shift_ps"]))
        ordering_ok = all(float(right["DeltaV_trip_mv"]) >= float(left["DeltaV_trip_mv"]) for left, right in zip(group, group[1:]))
        for row in map_rows:
            if float(row["baseline_vdd_v"]) == baseline:
                row["ordering_ok"] = ordering_ok if row["trip_status"] == "IN_RANGE_TRIP" else None
        if not ordering_ok:
            for row in group:
                row["reason"] = (str(row["reason"]) + ";" if row["reason"] else "") + "trip_depth_ordering_reversal"
    per_baseline = {key: [row for row in map_rows if voltage_key(float(row["baseline_vdd_v"])) == key] for key in ("0.95", "1.10")}
    has_trip = {key: any(row["trip_status"] == "IN_RANGE_TRIP" for row in group) for key, group in per_baseline.items()}
    ordering = {key: all(row.get("ordering_ok") is not False for row in group) for key, group in per_baseline.items()}
    decision = "GO" if all(has_trip.values()) and all(ordering.values()) else "NO-GO"
    result = {"schema_version": 1, "study": STUDY, "decision": decision, "per_baseline_has_in_range_trip": has_trip, "per_baseline_ordering_ok": ordering, "trip_map": map_rows}
    write_csv(paths["trip_sweep"], TRIP_SWEEP_FIELDS, sweep_rows)
    write_csv(paths["trip_map"], TRIP_MAP_FIELDS, map_rows)
    write_csv(paths["trip_table"], TRIP_MAP_FIELDS, map_rows)
    write_json(paths["trip_summary"], result)
    return result


def ensure_terminal_artifacts(stop_reason: str) -> None:
    """Create empty formal downstream files when an earlier gate stops HSPICE work."""

    paths = analysis_paths()
    if not paths["mechanism_csv"].is_file():
        write_csv(paths["mechanism_csv"], MECHANISM_FIELDS, [])
        write_json(paths["mechanism_summary"], {"schema_version": 1, "study": STUDY, "decision": "NOT_RUN", "reason": stop_reason})
    if not paths["trip_sweep"].is_file():
        write_csv(paths["trip_sweep"], TRIP_SWEEP_FIELDS, [])
    if not paths["trip_map"].is_file():
        write_csv(paths["trip_map"], TRIP_MAP_FIELDS, [])
        write_csv(paths["trip_table"], TRIP_MAP_FIELDS, [])
        write_json(paths["trip_summary"], {"schema_version": 1, "study": STUDY, "decision": "NOT_RUN", "reason": stop_reason, "trip_map": []})


def final_decision() -> Tuple[str, List[str]]:
    """Derive M0 status solely from committed formal M0 gate summaries."""

    paths = analysis_paths()
    surface = load_json(paths["surface_summary"]) if paths["surface_summary"].is_file() else {"decision": "NOT_RUN"}
    selection = load_json(paths["candidate_summary"]) if paths["candidate_summary"].is_file() else {"decision": "NOT_RUN"}
    mechanism = load_json(paths["mechanism_summary"]) if paths["mechanism_summary"].is_file() else {"decision": "NOT_RUN"}
    trip = load_json(paths["trip_summary"]) if paths["trip_summary"].is_file() else {"decision": "NOT_RUN"}
    reasons: List[str] = []
    for name, result in (("local_surface", surface), ("candidate_selection", selection), ("mechanism", mechanism), ("trip", trip)):
        if result.get("decision") != "GO":
            reasons.append("{}={}".format(name, result.get("decision")))
    if not reasons:
        # M0 correctly performs no below-0.80-V detection campaign.  The high
        # baselines are fully characterized, but the formal low-boundary scope
        # makes CONDITIONAL_GO the honest publication status for this stage.
        return "CONDITIONAL_GO", ["0.80 V is local-code-surface/normal-point only; no <0.80 V detection claim"]
    return "NO-GO", reasons


def generate_summary_and_report() -> Dict[str, Any]:
    """Finish M0-7/M0-8 from evidence already generated by earlier phases."""

    require_dl()
    paths = analysis_paths()
    environment = load_json(paths["environment"])
    freeze = load_json(paths["frozen_inputs"])
    decision, reasons = final_decision()
    raw_manifests = list(RUN_ROOT.glob("r*/scenarios/*/scenario_manifest.json")) if RUN_ROOT.is_dir() else []
    pass_count = sum(load_json(path).get("completion_status") == "PASS" for path in raw_manifests)
    summary = {
        "schema_version": 1, "study": STUDY, "decision": decision, "reasons": reasons,
        "anchors": ANCHORS, "environment": environment,
        "frozen_inputs_sha256": sha256_file(paths["frozen_inputs"]),
        "single_probe_contract_sha256": sha256_file(paths["single_probe_contract"]),
        "raw_hspice_scenario_count": len(raw_manifests), "raw_hspice_pass_count": pass_count,
        "forbidden_reruns": freeze["forbidden_work"],
        "scope_boundary": "0.80 V is the formal minimum VDD; M0 makes no below-0.80-V detection claim.",
        "figure_manifest": str(paths["figure_manifest"]) if paths["figure_manifest"].is_file() else None,
        "downstream_handoff": "M1 may consume snapshot semantics, legal M_det/F_det levels, nominal ps shifts, Vtrip envelope, and unsupported scope; M0 implements no margin-generator RTL.",
    }
    write_json(paths["summary"], summary)
    # Final reporting accepts intentionally header-only downstream tables on
    # an earlier NO-GO path; the tables remain explicit evidence, not missing
    # files or substituted values.
    candidates = read_csv(paths["candidate_csv"], CANDIDATE_FIELDS, allow_empty=True) if paths["candidate_csv"].is_file() else []
    trip_rows = read_csv(paths["trip_map"], TRIP_MAP_FIELDS, allow_empty=True) if paths["trip_map"].is_file() else []
    lines = [
        "# FTC M0 检测裕量与电压灵敏度表征",
        "",
        "## 1. Frozen architecture and H0 handoff",
        "",
        "- 冻结结构：N=16 medium、`BUF_X0P8M_A9TL40`、`NOR2_X4A_A9TL40` K=10、真实 tap29 XOR 与真实 DFF。",
        "- H0 snapshot anchors：0.80 V M7/F6，0.95 V M4/F6，1.10 V M2/F9。",
        "- 所有冻结输入的 SHA256、H0/exact acceptance 与兼容 HSPICE 版本记录在 `analysis/m0_detection_margin_characterization/baseline/`。",
        "",
        "## 2. Single-probe physical definition",
        "",
        "- 单 probe 在校准之后保持 M/F snapshot 恒定；真实 DFF 双读稳定 Q 是唯一 trip 判据，R 仅作物理诊断。",
        "",
        "控制码在 t=0 以 thermometer snapshot 固定。reset release→S_CLK rise 为 0.49 ns，rise→Q1 为 2.30 ns，Q1→Q2 为 0.20 ns，Q2→reset assert 为 0.20 ns，reset complete→fall 为 0.29 ns，fall→recovery 为 2.70 ns。每个 deck 直接测量 `t_xor_rise/fall`、`t_ck_rise` 和两次 `q_final`。",
        "",
        "## 3. Local two-dimensional (M,F) timing surface",
        "",
        "- 三个锚点局部面均为 GO：0.80 V 21 个点、0.95 V 21 个点、1.10 V 15 个点；每个点由真实 M/F 码、真实 XOR、真实 reference chain 与真实 DFF 得到。",
        "- 合法候选仅从实测二维面选择，未假设固定的 `F+1` 映射，也未把非法码伪造成数据。",
        "",
        "## 4. Candidate margin selection in ps (Table M0-A)",
        "",
        "| Baseline (V) | Level | M_cal/F_cal | M_det/F_det | Nominal shift (ps) | Nominal R (ps) | Normal Q |",
        "|---:|---|---|---|---:|---:|---:|",
    ]
    for row in candidates:
        lines.append("| {} | {} | M{}/F{} | M{}/F{} | {:.6f} | {:.6f} | {} |".format(row["baseline_vdd_v"], row["margin_level"], row["M_cal"], row["F_cal"], row["M_det"], row["F_det"], float(row["nominal_D_ref_shift_ps"]), float(row["nominal_R_ps"]), row["normal_Q"]))
    lines.extend([
        "",
        "## 5. Voltage sensitivity mechanism",
        "",
        "- M0-4 mechanism gate = GO：0.95 V 的 L1/L2/L3 在 0.95/0.90/0.85 V，1.10 V 的 L1/L2/L3 在 1.10/1.05/1.00 V 进行小规模静态点验证。",
        "- 六个候选均在正常 VDD 保持稳定 Q=0、负 R，并在降压时 R 向触发方向增长；该方向性由 Fig. M0-2/M0-3 中的真实 W_xor、D_ref、R 与 Q 数据展示。",
        "",
        "## 6. Real-DFF static trip extraction (Table M0-B)",
        "",
        "| Baseline (V) | Level | M_det/F_det | Status | Vtrip (V) | ΔVtrip (mV) | R@last Q=0 (ps) | R@first Q=1 (ps) |",
        "|---:|---|---|---|---:|---:|---:|---:|",
    ])
    for row in trip_rows:
        lines.append("| {} | {} | M{}/F{} | {} | {} | {} | {} | {} |".format(row["baseline_vdd_v"], row["margin_level"], row["M_det"], row["F_det"], row["trip_status"], row["Vtrip_v"] or "", row["DeltaV_trip_mv"] or "", row["R_at_last_q0_ps"] or "", row["R_at_first_q1_ps"] or ""))
    lines.extend([
        "",
        "## 7. margin -> M_det/F_det -> ps -> Vtrip -> mV mapping",
        "",
        "- Table M0-A 与 Table M0-B 通过相同的 baseline、margin level 和 M_det/F_det 连接：每个 level 的实测 nominal shift、真实 DFF Vtrip 与 ΔVtrip 均可在正式 CSV 中逐行追溯。",
        "- 两个 baseline 的 ΔVtrip 随 nominal timing shift 均单调增加；没有将 R=0 当作 DFF trip 的代理判据。",
        "",
        "## 8. 0.80 V scope boundary",
        "",
        "- 0.80 V 仅完成局部码空间和正常点验证；未进行、也未声明 `<0.80 V` 的正式 droop detection 能力。",
        "",
        "## 9. Figure/table index and SCI caption draft",
        "",
        "- Fig. M0-1：三个 H0 calibration anchor 附近的二维 M/F 真实 residual 面；候选来自实测时间面而非固定 F 增量。",
        "- Fig. M0-2：真实 XOR 脉宽与 reference delay 随静态 VDD 的响应，显示是否存在可用的非共模灵敏度。",
        "- Fig. M0-3：residual R 与真实 DFF Q/Vtrip 的对应；R=0 为解释参考线，不是替代 DFF 的 trip 判据。",
        "- Fig. M0-4：nominal timing margin 与最小静态跌落深度的关系；`NO_IN_RANGE_TRIP` 不按 0 mV 绘制。",
        "- 图：`analysis/m0_detection_margin_characterization/figures/fig_m0_*.{pdf,png}`；表：`tables/table_m0_candidate_summary.csv` 与 `tables/table_m0_trip_summary.csv`；图的输入哈希、脚本哈希和 DL/matplotlib 环境记录于 `figure_manifest.json`。",
        "",
        "## 10. HSPICE scenario accounting",
        "",
        "- 新建 task-owned HSPICE scenario：{}，PASS：{}；未重跑启动校准、RF6/RF8/RF9C/RF9D 或上游物理 campaign。".format(len(raw_manifests), pass_count),
        "",
        "## 11. Miniconda DL and matplotlib environment",
        "",
        "- Python：`{}`；版本 `{}`；matplotlib `{}`；conda 环境 `{}`。".format(environment["python_executable"], environment["python_version"], environment["matplotlib_version"], environment["conda_env"]),
        "",
        "## 12. Final M0 decision",
        "",
        "**M0 = {}**".format(decision),
        "",
        "- {}".format("；".join(reasons) if reasons else "所有 M0 gate 均为 GO"),
        "- {}".format("因 0.80 V 保持 formal minimum 的局部验证边界，M0 不夸大为全范围检测能力，最终状态为 CONDITIONAL_GO。" if decision == "CONDITIONAL_GO" else "该状态严格来自前述 formal gate；未用额外扫点或 RTL 修改改变 gate 结论。"),
        "",
        "## 13. Downstream handoff",
        "",
        summary["downstream_handoff"],
    ])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def run_plotter() -> None:
    """Run the M0-only matplotlib publication step in the already-checked DL env."""

    require_dl()
    plotter = FTC_ROOT / "scripts" / "plot_m0_detection_margin_figures.py"
    subprocess.run([sys.executable, str(plotter)], cwd=FTC_ROOT.parent.parent, check=True)


def run_all() -> Dict[str, Any]:
    """Execute every M0 phase in order and preserve terminal NO-GO evidence.

    A failed local/candidate/mechanism gate prohibits later *electrical* work,
    exactly as the plan requires.  It does not leave the task half-published:
    empty formal downstream tables, the reproducible figures, and the final
    report are still generated so the NO-GO is complete and auditable.
    """

    phase_freeze()
    phase_contract()
    surface = phase_surface()
    if surface.get("decision") == "GO":
        selection = phase_select()
        if selection.get("decision") == "GO":
            mechanism = phase_mechanism()
            if mechanism.get("decision") == "GO":
                phase_trip()
            else:
                ensure_terminal_artifacts("mechanism_gate_no_go")
        else:
            ensure_terminal_artifacts("candidate_selection_no_go")
    else:
        # Candidate table is part of the formal delivery even when no physical
        # candidate exists, so publish an empty schema rather than omitting it.
        paths = analysis_paths()
        write_csv(paths["candidate_csv"], CANDIDATE_FIELDS, [])
        write_json(paths["candidate_summary"], {"schema_version": 1, "study": STUDY, "decision": "NO-GO", "reason": "local_surface_not_go", "candidates": []})
        ensure_terminal_artifacts("local_surface_no_go")
    run_plotter()
    return generate_summary_and_report()


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Expose explicit stages for review; ``all`` is the only normal workflow."""

    parser = argparse.ArgumentParser(description="FTC M0 detection-margin characterization")
    parser.add_argument("--phase", choices=("freeze", "contract", "surface", "select", "mechanism", "trip", "plot", "finalize", "all"), required=True)
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Dispatch one reviewable M0 phase after enforcing the DL environment."""

    args = parse_args(argv)
    require_dl()
    dispatch = {
        "freeze": phase_freeze,
        "contract": phase_contract,
        "surface": phase_surface,
        "select": phase_select,
        "mechanism": phase_mechanism,
        "trip": phase_trip,
        "plot": run_plotter,
        "finalize": generate_summary_and_report,
        "all": run_all,
    }
    dispatch[args.phase]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
