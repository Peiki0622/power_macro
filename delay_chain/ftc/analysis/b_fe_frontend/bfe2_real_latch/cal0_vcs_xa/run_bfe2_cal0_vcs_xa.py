#!/usr/bin/env python3
"""Execute the bounded B-FE2-CAL0 sample-close calibratability check.

CAL0 is deliberately not a calibration controller.  It first reconstructs a
small set of event-free close intervals from the already accepted normal
``safe_d`` crossing ledger.  Only three representative points (left, nominal
center, right) are then run through the existing VCS+PrimeSim XA bridge and
the unchanged real ``LATQ_X0P5M_A9TR40`` bank.  There is no L2 scenario, M/F
code table, FSM, dense close grid, or circuit modification in this stage.

Use ``--offline-only`` to perform the non-simulating interval reconstruction,
then ``--run`` to consume that frozen artifact and execute exactly three XA
scenarios.  The companion analyzer publishes the final Gate.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple


L1AR_ROOT = Path(__file__).resolve().parents[1] / "l1a_r_vcs_xa"
sys.path.insert(0, str(L1AR_ROOT))
import run_bfe2_l1a_r_vcs_xa as l1ar  # noqa: E402


FTC_ROOT = l1ar.FTC_ROOT
SOURCE_MANIFEST = l1ar.SOURCE_MANIFEST
CELLS = l1ar.CELLS
AUDIT = l1ar.AUDIT
SOURCE_ROOT = l1ar.SOURCE_ROOT
NORMAL_SCENARIO = "BFE2L-095-N"
NORMAL_KEY = "bfe2l_095_n"
STAGE = "B-FE2-CAL0"
LAUNCH_PS = 1000.0
NOMINAL_SAMPLE_CLOSE_PS = 534.524618567
NOMINAL_G_CLOSE_PS = 1534.524618567
VDD_SAFE_V = 0.95
EXPECTED_TAP_COUNT = 30
EXPECTED_XOR_CELL = "XOR2_X0P5M_A9TL40"
EXPECTED_RVT_LVT_PATH = ("BUF_X0P7M_A9TR40", "BUF_X0P7M_A9TL40")
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "cal0_vcs_xa"
REPORT_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "cal0_vcs_xa"
OFFLINE_PATH = REPORT_ROOT / "BFE2_CAL0_OFFLINE_INTERVALS.json"
MANIFEST_PATH = REPORT_ROOT / "BFE2_CAL0_SCENARIO_MANIFEST.json"
POINTS = ("LEFT", "CENTER", "RIGHT")


def sha256(path: Path) -> str:
    """Hash a retained input or generated artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    """Read one object-shaped JSON contract."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def source_path() -> Path:
    """Return the immutable B-FE2.2C normal trace only."""

    return SOURCE_ROOT / NORMAL_KEY / "bfe2c_corrected.tr0"


def source_deck_path() -> Path:
    """Return the immutable B-FE2.2C normal deck only."""

    return source_path().with_suffix(".sp")


def validate_frozen_inputs() -> Dict[str, Any]:
    """Reject L2, topology, voltage, or previously accepted L1A-R drift."""

    source_manifest = load_json(SOURCE_MANIFEST)
    entries = source_manifest.get("scenarios", [])
    normal = next((item for item in entries if item.get("scenario_id") == NORMAL_SCENARIO), None)
    if normal is None or len(entries) != 2:
        raise ValueError("B-FE2-CAL0 requires the existing B-FE2.2C pair for read-only source validation")
    if abs(float(source_manifest["requested_close_ps"]) - NOMINAL_SAMPLE_CLOSE_PS) > 1.0e-6:
        raise ValueError("nominal sample_close drifted")
    if float(normal["baseline_v"]) != 0.95 or normal.get("droop_v") is not None:
        raise ValueError("CAL0 normal source is not exactly 0.95 V normal")
    signature = normal.get("electrical_signature", {})
    if int(signature.get("observable_taps", -1)) != EXPECTED_TAP_COUNT:
        raise ValueError("frozen normal source is not a 30-tap sensing geometry")
    if signature.get("xor_cell") != EXPECTED_XOR_CELL:
        raise ValueError("frozen normal source XOR identity changed")
    if tuple(signature.get("rvt_lvt_buffer_cells", ())) != EXPECTED_RVT_LVT_PATH:
        raise ValueError("frozen normal source RVT/LVT path changed")
    if not source_path().is_file() or not source_deck_path().is_file():
        raise FileNotFoundError("missing immutable normal source waveform/deck")
    if sha256(source_path()) != normal["tr0_sha256"] or sha256(source_deck_path()) != normal["deck_sha256"]:
        raise ValueError("normal source SHA mismatch")
    cells = load_json(CELLS)
    if cells["latch"]["cell"] != "LATQ_X0P5M_A9TR40":
        raise ValueError("real latch identity changed")
    audit = load_json(AUDIT)
    if audit["cdl_ports"] != ["Q", "VDD", "VNW", "VPW", "VSS", "D", "G"]:
        raise ValueError("LATQ port contract changed")
    prior_analysis = load_json(L1AR_ROOT / "BFE2_L1AR_ANALYSIS.json")
    if prior_analysis.get("gate") != "BFE2_L1AR_REAL_SAFE_LATCH_PASS":
        raise ValueError("CAL0 requires the accepted L1A-R safe-latch evidence")
    return {"source_manifest": source_manifest, "normal_entry": normal, "signature": signature, "cells": cells, "audit": audit, "prior_analysis": prior_analysis}


def reconstruct_intervals() -> Dict[str, Any]:
    """Reconstruct three event-free close intervals without running a solver.

    The ledger contains absolute ``safe_d`` crossing times.  The selected
    intervals are the immediately preceding, nominal-containing, and
    immediately following crossing gaps around the accepted close.  Their
    midpoints (except the nominal center) are the only simulation points.  No
    interpolated dense grid or legacy M/F mapping is introduced.
    """

    frozen = validate_frozen_inputs()
    ledger_path = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "l1a_r_vcs_xa" / NORMAL_KEY / "safe_d_crossing_ledger.json"
    if not ledger_path.is_file():
        raise FileNotFoundError("accepted L1A-R normal safe_d ledger is missing")
    ledger = load_json(ledger_path)
    all_events: List[Dict[str, Any]] = []
    for tap in range(30):
        events = ledger.get("tap_{:02d}".format(tap), {}).get("crossings")
        if not isinstance(events, list):
            raise ValueError("normal safe_d ledger missing tap {}".format(tap))
        for event in events:
            all_events.append({"tap": tap, "time_ps": float(event["time_ps"]), "direction": event["direction"], "logic_state": int(event["logic_state"])})
    all_events.sort(key=lambda event: (event["time_ps"], event["tap"]))
    before = [event for event in all_events if event["time_ps"] < NOMINAL_G_CLOSE_PS]
    after = [event for event in all_events if event["time_ps"] > NOMINAL_G_CLOSE_PS]
    if len(before) < 2 or len(after) < 2:
        raise ValueError("insufficient local ledger events around nominal close")
    previous_event = before[-1]
    previous_previous = before[-2]
    next_event = after[0]
    next_next = after[1]
    if not (previous_event["time_ps"] < NOMINAL_G_CLOSE_PS < next_event["time_ps"]):
        raise ValueError("nominal close is not inside a positive-width ledger gap")
    interval_specs = [
        ("LEFT", previous_previous, previous_event, (previous_previous["time_ps"] + previous_event["time_ps"]) / 2.0),
        ("CENTER", previous_event, next_event, NOMINAL_G_CLOSE_PS),
        ("RIGHT", next_event, next_next, (next_event["time_ps"] + next_next["time_ps"]) / 2.0),
    ]
    intervals: List[Dict[str, Any]] = []
    for label, start_event, end_event, point_g_ps in interval_specs:
        start_g_ps = float(start_event["time_ps"])
        end_g_ps = float(end_event["time_ps"])
        if not (start_g_ps < point_g_ps < end_g_ps):
            raise ValueError("selected {} point is not strictly inside its ledger gap".format(label))
        start_sample = start_g_ps - LAUNCH_PS
        end_sample = end_g_ps - LAUNCH_PS
        # Preserve the frozen decimal nominal exactly instead of exposing a
        # binary subtraction artifact such as 534.5246185670001 ps.
        point_sample = NOMINAL_SAMPLE_CLOSE_PS if label == "CENTER" else point_g_ps - LAUNCH_PS
        intervals.append({
            "point": label,
            "scenario_id": "BFE2C0-095-N-{}".format(label),
            "start_ps": start_sample,
            "end_ps": end_sample,
            "len_ps": end_sample - start_sample,
            "center_ps": (start_sample + end_sample) / 2.0,
            "selected_sample_close_ps": point_sample,
            "selected_g_close_ps": point_g_ps,
            "left_headroom_ps": point_sample - start_sample,
            "right_headroom_ps": end_sample - point_sample,
            "start_g_ps": start_g_ps,
            "end_g_ps": end_g_ps,
            "start_event": start_event,
            "end_event": end_event,
            "event_free": True,
            "source_crossing_count_inside": sum(start_g_ps < event["time_ps"] < end_g_ps for event in all_events),
        })
    offline = {
        "schema_version": 1,
        "stage": STAGE,
        "mode": "offline safe_d crossing ledger reconstruction",
        "simulation_run": False,
        "dense_grid_scan": False,
        "source_scenario": NORMAL_SCENARIO,
        "source_manifest_sha256": sha256(SOURCE_MANIFEST),
        "source_trace_sha256": sha256(source_path()),
        "source_deck_sha256": sha256(source_deck_path()),
        "safe_d_ledger_sha256": sha256(ledger_path),
        "l1ar_analysis_sha256": sha256(L1AR_ROOT / "BFE2_L1AR_ANALYSIS.json"),
        "sensing_geometry_id": frozen["signature"]["topology_version"],
        "tap_count": EXPECTED_TAP_COUNT,
        "xor_cell": EXPECTED_XOR_CELL,
        "rvt_lvt_path_cells": list(EXPECTED_RVT_LVT_PATH),
        "latch_cell": "LATQ_X0P5M_A9TR40",
        "vdd_safe_v": VDD_SAFE_V,
        "vnw_v": VDD_SAFE_V,
        "vpw_v": 0.0,
        "vss_v": 0.0,
        "nominal_sample_close_ps": NOMINAL_SAMPLE_CLOSE_PS,
        "nominal_g_close_ps": NOMINAL_G_CLOSE_PS,
        "launch_ps": LAUNCH_PS,
        "reconstruction_rule": "event-free gaps between adjacent normal safe_d crossings; no dense scan",
        "local_events": [previous_previous, previous_event, next_event, next_next],
        "selected_intervals": intervals,
        "selected_points": [item["selected_sample_close_ps"] for item in intervals],
        "next_step_authorized": "exactly three representative normal VCS-XA points",
        "stop_after_stage": True,
    }
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    OFFLINE_PATH.write_text(json.dumps(offline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return offline


def load_offline() -> Dict[str, Any]:
    """Load and revalidate the non-simulating interval artifact."""

    if not OFFLINE_PATH.is_file():
        raise FileNotFoundError("run --offline-only before --run")
    offline = load_json(OFFLINE_PATH)
    validate_frozen_inputs()
    if offline.get("source_scenario") != NORMAL_SCENARIO or offline.get("dense_grid_scan") is not False or len(offline.get("selected_intervals", [])) != 3:
        raise ValueError("offline CAL0 artifact is not exactly the three-point normal contract")
    if sha256(source_path()) != offline["source_trace_sha256"] or sha256(source_deck_path()) != offline["source_deck_sha256"]:
        raise ValueError("offline source identity changed")
    return offline


def render_tb_for_close(schedules: Mapping[int, Sequence[Tuple[float, int, str]]], initial_states: Mapping[int, int], initial_values: Mapping[int, Mapping[str, float]], close_ps: float) -> str:
    """Reuse the accepted bridge TB with only the authorized G close changed."""

    # The L1A-R generator already contains the audited per-tap initialization,
    # q-event logging, tail sample, and final sample schedule.  Rewriting only
    # its decimal close constants prevents CAL0 from introducing a second
    # stimulus implementation or changing any source-domain behavior.
    text = l1ar.render_tb(schedules, initial_states, initial_values)
    replacements = {
        "1534.524618567000": "{:.12f}".format(close_ps),
        "1634.524618567000": "{:.12f}".format(close_ps + 100.0),
        "4364.475381433000": "{:.12f}".format(7000.0 - (close_ps + 100.0 + 1000.0) - 1.0),
    }
    for old, new in replacements.items():
        if old not in text:
            raise ValueError("L1A-R TB close token missing during CAL0 rendering: {}".format(old))
        text = text.replace(old, new)
    return text.replace("B-FE2-L1A-R", "B-FE2-CAL0")


def prepare_scenario(interval: Mapping[str, Any]) -> Dict[str, Any]:
    """Generate one normal-only task directory for a selected close point."""

    label = str(interval["point"])
    directory = RUN_ROOT / label.lower()
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    trace = l1ar.previous.bfe1_frontend.parse_ascii_tr0(source_path())
    times = trace["columns"]["time"]
    columns = trace["columns"]
    vdd_sense = columns[l1ar.previous.bfe1_frontend.label_for("vdd_monitored")]
    schedules: Dict[int, List[Tuple[float, int, str]]] = {}
    initial_states: Dict[int, int] = {}
    initial_values: Dict[int, Dict[str, float]] = {}
    for tap in range(30):
        xor = columns[l1ar.previous.bfe1_frontend.label_for("xor_{}".format(tap))]
        initial, events = l1ar.threshold_schedule(times, xor, vdd_sense)
        schedules[tap] = events
        initial_states[tap] = initial
        initial_values[tap] = {"xor_v": float(xor[0]), "vdd_sense_v": float(vdd_sense[0]), "threshold_v": 0.5 * float(vdd_sense[0]), "safe_d_v": 0.95 if initial else 0.0}
    # Retain an independent copy of the immutable normal ledger in every
    # point directory so post-close causality can be audited without reaching
    # back into the prior L1A-R run directory.
    source_ledger = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "l1a_r_vcs_xa" / NORMAL_KEY / "safe_d_crossing_ledger.json"
    shutil.copyfile(source_ledger, directory / "safe_d_crossing_ledger.json")
    wrapper = l1ar.render_wrapper(interval["scenario_id"], columns, times).replace("B-FE2-L1A-R", "B-FE2-CAL0")
    (directory / "bfe2_cal0_ams_wrapper.sp").write_text(wrapper, encoding="ascii")
    (directory / "tb_bfe2_cal0_vcs_xa.sv").write_text(render_tb_for_close(schedules, initial_states, initial_values, float(interval["selected_g_close_ps"])), encoding="ascii")
    (directory / "xa.cfg").write_text("set_sim_level 7\nset_waveform -format fsdb\n" + "\n".join(["probe_waveform_voltage vdd_sense", "probe_waveform_voltage vdd_safe", "probe_waveform_voltage latch_g_r"] + ["probe_waveform_voltage safe_d_r_{:02d}".format(tap) for tap in range(30)] + ["probe_waveform_voltage q_{:02d}".format(tap) for tap in range(30)]) + "\n", encoding="ascii")
    (directory / "vcsAD.init").write_text("bus_format [%d];\nuse_spice -cell bfe2_l1a_r_ams;\nchoose xa -hspice {} -c {} -o {}/xa;\n".format(directory / "bfe2_cal0_ams.sp", directory / "xa.cfg", directory), encoding="utf-8")
    deck = l1ar.render_top_deck(directory).replace("bfe2_l1a_r_ams_wrapper.sp", "bfe2_cal0_ams_wrapper.sp").replace("B-FE2-L1A-R", "B-FE2-CAL0")
    (directory / "bfe2_cal0_ams.sp").write_text(deck, encoding="ascii")
    return {"point": label, "scenario_id": interval["scenario_id"], "directory": str(directory), "selected_sample_close_ps": interval["selected_sample_close_ps"], "selected_g_close_ps": interval["selected_g_close_ps"], "ledger_sha256": sha256(directory / "safe_d_crossing_ledger.json"), "interval": dict(interval)}


def run_scenario(meta: Mapping[str, Any]) -> Dict[str, Any]:
    """Compile and execute one selected normal point, reusing complete evidence."""

    directory = Path(meta["directory"])
    boundary = directory / "xa_boundary_samples.csv"
    if boundary.is_file() and "final," in boundary.read_text(encoding="ascii", errors="replace") and (directory / "compile.log").is_file() and (directory / "run.log").is_file():
        run_text = (directory / "run.log").read_text(encoding="utf-8", errors="replace")
        return {**meta, "run_disposition": "reused-completed", "compile_returncode": 0, "run_returncode": 0, "cosim_marker": "Start Cosim VCS-Analog Processing" in run_text, "xa_version_marker": "PrimeSim XA" in run_text, "boundary_csv_sha256": sha256(boundary)}
    vcs = shutil.which("vcs")
    if not vcs:
        raise RuntimeError("VCS is unavailable")
    command = [vcs, "-full64", "-sverilog", "-timescale=1ps/1ps", "-ad=vcsAD.init", "-debug_access+all", "-o", "simv", "tb_bfe2_cal0_vcs_xa.sv"]
    compile_result = subprocess.run(command, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=900)
    (directory / "compile.log").write_text(compile_result.stdout, encoding="utf-8", errors="replace")
    if compile_result.returncode != 0:
        return {**meta, "run_disposition": "compile-failed", "compile_returncode": compile_result.returncode, "run_returncode": None, "cosim_marker": False, "xa_version_marker": False}
    run_result = subprocess.run(["./simv"], cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=1800)
    (directory / "run.log").write_text(run_result.stdout, encoding="utf-8", errors="replace")
    return {**meta, "run_disposition": "new", "compile_returncode": 0, "run_returncode": run_result.returncode, "cosim_marker": "Start Cosim VCS-Analog Processing" in run_result.stdout, "xa_version_marker": "PrimeSim XA" in run_result.stdout, "boundary_csv_sha256": sha256(boundary) if boundary.is_file() else None}


def run_three_points() -> Dict[str, Any]:
    """Consume the frozen offline artifact and run exactly LEFT/CENTER/RIGHT."""

    offline = load_offline()
    intervals = offline["selected_intervals"]
    if tuple(item["point"] for item in intervals) != POINTS:
        raise ValueError("CAL0 point order changed")
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    metadata = [prepare_scenario(interval) for interval in intervals]
    results = [run_scenario(item) for item in metadata]
    cells = load_json(CELLS)
    frozen = validate_frozen_inputs()
    manifest = {
        "schema_version": 1,
        "stage": STAGE,
        "verification_mode": "VCS-XA mixed-signal latch-boundary validation of offline close intervals",
        "source_waveform": NORMAL_SCENARIO,
        "l2_used": False,
        "m_f_code_table_used": False,
        "fsm_added": False,
        "sensing_geometry_modified": False,
        "gate_pending_analysis": True,
        "source_manifest_sha256": sha256(SOURCE_MANIFEST),
        "source_trace_sha256": sha256(source_path()),
        "source_deck_sha256": sha256(source_deck_path()),
        "offline_intervals_sha256": sha256(OFFLINE_PATH),
        "l1ar_analysis_sha256": sha256(L1AR_ROOT / "BFE2_L1AR_ANALYSIS.json"),
        "latch_cell": "LATQ_X0P5M_A9TR40",
        "sensing_geometry_id": frozen["signature"]["topology_version"],
        "tap_count": EXPECTED_TAP_COUNT,
        "xor_cell": EXPECTED_XOR_CELL,
        "rvt_lvt_path_cells": list(EXPECTED_RVT_LVT_PATH),
        "latch_cdl_sha256": cells["latch"].get("cdl_sha256", load_json(AUDIT)["cdl"]["sha256"]),
        "vdd_safe_v": VDD_SAFE_V,
        "vnw_v": VDD_SAFE_V,
        "vpw_v": 0.0,
        "vss_v": 0.0,
        "safe_d_rule": "xor > 0.5*VDD_SENSE ? 0.95 V : 0 V",
        "additional_delay_ps": 0.0,
        "additional_slew": "none",
        "hysteresis": "none",
        "x_region": "none",
        "launch_ps": LAUNCH_PS,
        "nominal_sample_close_ps": NOMINAL_SAMPLE_CLOSE_PS,
        "nominal_g_close_ps": NOMINAL_G_CLOSE_PS,
        "offline_selected_intervals": intervals,
        "scenarios": results,
        "new_physical_scenarios": 3,
        "stop_after_stage": True,
        "next_stage_authorized": False,
        "container_tools": {"vcs": os.environ.get("VCS_HOME", "unknown"), "xa": os.environ.get("PRIMESIM_XA_HOME", os.environ.get("XA_HOME", "unknown"))},
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def main() -> int:
    """Dispatch the explicitly separated offline and three-point phases."""

    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--offline-only", action="store_true", help="reconstruct ledger intervals without simulation")
    group.add_argument("--run", action="store_true", help="run exactly the frozen three normal XA points")
    args = parser.parse_args()
    if args.offline_only:
        print(json.dumps(reconstruct_intervals(), indent=2, sort_keys=True))
        return 0
    run_three_points()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
