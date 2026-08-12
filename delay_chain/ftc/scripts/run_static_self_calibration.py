#!/usr/bin/env python3
"""Re-publish FTC static self-calibration from completed r2 HSPICE evidence.

The original experiment already produced complete raw HSPICE decks, listings,
and MEAS CSV files for 0.75--1.10 V.  The macro contract now begins at
0.80 V, so this runner deliberately *does not invoke HSPICE*.  It validates
the immutable r2 records, selects only the seven legal voltages, reconstructs
the public trace from measured values, and applies the same real-DFF gate.

This is intentionally a replay, not a new mapping optimization.  The frozen
3-bit/7-MUX/one-DFF implementation remains unchanged; the published mapping
is described only as verified over the new range, never as its minimum.
"""

import argparse
import csv
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
PHASE1_SCRIPTS = FTC_ROOT.parent / "phase1" / "scripts"
if str(PHASE1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PHASE1_SCRIPTS))
import run_dc_sweep  # noqa: E402  # Shared checked HSPICE version/listing/MEAS helpers.


# Electrical scope is intentionally fixed in source rather than exposed as
# command-line tuning knobs.  Changing one of these constants creates a
# different research experiment and must be reviewed as such.
# The formal range has seven 50 mV anchors.  Values remain ascending so the
# compact evidence table is easy to compare with the original r2 scan order.
VDD_POINTS = (0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10)
CODES = tuple(range(8))
MAX_CODE = 7
LOW_TAPS = (10, 12, 14, 16, 18)
SIZING_TAPS = (10, 12, 14, 16, 18, 20, 22, 24)
SENSOR_TAP_INDEX = 29
OBSERVABLE_STAGES = 30
SENSOR_RVT_INITIAL_STAGES = 4
SENSOR_LVT_INITIAL_STAGES = 0
MUX_CELL = "MXT2_X0P5M_A9TL40"
MUX_COUNT = 7
Q_SETTLE_S = 2.0e-10
Q_READ_TIME_S = 3.0e-9
CODE_SETTLE_S = 2.0e-10

# This mapping was electrically selected in r2 while covering the former
# 0.75 V endpoint.  Reusing it at 0.80--1.10 V avoids a new sizing search;
# it must not be interpreted as proof that no shorter new-range mapping exists.
REPLAY_TAPS = (10, 12, 14, 16, 18, 36, 37, 38)
SCENARIO_PATTERN = re.compile(r"^v(?P<vdd>\d+)p(?P<fraction>\d+)_step(?P<step>\d+)_code(?P<code>\d+)$")
Q_READ_PATTERN = re.compile(r"q_final_v\s+FIND\s+v\(q_final,vss_a\)\s+AT=(?P<time>[0-9.eE+-]+)")

TRACE_FIELDS = (
    "vdd_v", "step_index", "code", "selected_tap", "Q", "D_code_ps",
    "W_S_int_ps", "is_lock", "headroom_verified",
)


def finite_number(value: Any) -> Optional[float]:
    """Return a finite scalar, preserving failed HSPICE measurements as absent."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def load_json(path: Path) -> Dict[str, Any]:
    """Load one object-shaped evidence/configuration file without modifying it."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object: {}".format(path))
    return value


def load_csv(path: Path, fields: Sequence[str]) -> List[Dict[str, str]]:
    """Load a nonempty CSV after checking the narrow schema this task consumes."""

    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not set(fields).issubset(reader.fieldnames):
            raise ValueError("required evidence schema is incomplete: {}".format(path))
        rows = list(reader)
    if not rows:
        raise ValueError("required evidence is empty: {}".format(path))
    return rows


def parse_scenario_name(name: str) -> Optional[Dict[str, int]]:
    """Decode the fixed r2 scenario name without inferring physical values.

    r2 has one unrelated 0.75 V sizing directory whose name intentionally does
    not match this pattern.  Returning ``None`` for it makes the legal-range
    selection explicit and prevents a filename heuristic from treating sizing
    data as a calibration point.
    """

    match = SCENARIO_PATTERN.match(name)
    if match is None:
        return None
    fraction = match.group("fraction")
    return {
        "vdd_centi_v": int(match.group("vdd")) * 100 + int(fraction.ljust(2, "0")[:2]),
        "step_index": int(match.group("step")),
        "code": int(match.group("code")),
    }


def listing_is_complete(path: Path) -> bool:
    """Check the terminal HSPICE status without treating a CSV as sufficient.

    A MEAS CSV can exist after an interrupted run.  The listing is therefore
    required to contain HSPICE's normal completion marker and to exclude the
    fatal/parser/convergence signatures that invalidate electrical evidence.
    """

    text = path.read_text(encoding="utf-8", errors="replace").lower()
    bad_markers = ("fatal error", "syntax error", "convergence failed", "job aborted")
    return "job concluded" in text and not any(marker in text for marker in bad_markers)


def q_read_time_from_deck(path: Path) -> Optional[float]:
    """Read the actual DFF observation time from a retained r2 deck.

    The read time was increased by the original physical sizing flow for the
    longest selected threshold path.  Recovering it from each deck keeps the
    replay tied to recorded conditions rather than duplicating an unstated
    timing constant in this publication script.
    """

    match = Q_READ_PATTERN.search(path.read_text(encoding="ascii"))
    return None if match is None else finite_number(match.group("time"))


def replay_r2_trace(raw_run_dir: Path) -> List[Dict[str, Any]]:
    """Reconstruct the seven-voltage calibration trace from raw r2 evidence.

    Each scenario is independently checked for deck, listing and MEAS data.
    The measured timing values are classified with the original DFF read time;
    this makes a malformed or incomplete physical probe a publication error,
    rather than silently carrying over the earlier processed CSV value.
    """

    scenario_root = raw_run_dir / "scenarios"
    if not scenario_root.is_dir():
        raise ValueError("r2 scenario root is unavailable: {}".format(scenario_root))
    rows: List[Dict[str, Any]] = []
    legal_centivolts = {int(round(vdd * 100.0)) for vdd in VDD_POINTS}
    for scenario in sorted(path for path in scenario_root.iterdir() if path.is_dir()):
        identity = parse_scenario_name(scenario.name)
        if identity is None or identity["vdd_centi_v"] not in legal_centivolts:
            continue
        deck = scenario / "static_self_calibration.sp"
        listing = scenario / "static_self_calibration.lis"
        if not deck.is_file() or not listing.is_file() or not listing_is_complete(listing):
            raise ValueError("r2 physical scenario is incomplete: {}".format(scenario))
        q_read_time_s = q_read_time_from_deck(deck)
        if q_read_time_s is None:
            raise ValueError("r2 scenario has no DFF read time: {}".format(deck))
        values = run_dc_sweep.parse_measurements(
            run_dc_sweep.find_measurement_file(scenario, "static_self_calibration")
        )
        vdd_v = identity["vdd_centi_v"] / 100.0
        value = classify_probe({
            "vdd_v": vdd_v,
            "t_xor_rise_s": values.get("t_xor_rise"),
            "t_xor_fall_s": values.get("t_xor_fall"),
            "t_ck_rise_s": values.get("t_ck_rise"),
            "q_final_v": values.get("q_final_v"),
            "q_read_time_s": q_read_time_s,
        }, REPLAY_TAPS[identity["code"]])
        rows.append({
            "vdd_v": vdd_v,
            "step_index": identity["step_index"],
            "code": identity["code"],
            "selected_tap": REPLAY_TAPS[identity["code"]],
            "Q": value["Q"],
            "D_code_ps": value["D_code_ps"],
            "W_S_int_ps": value["W_S_int_ps"],
            "is_lock": 0,
            "headroom_verified": 0,
            "valid": value["valid"],
        })

    rows.sort(key=lambda row: int(row["step_index"]))
    if len(rows) != 54:
        raise ValueError("r2 must provide exactly 54 legal-range probes, found {}".format(len(rows)))
    for vdd_v in VDD_POINTS:
        local = [row for row in rows if math.isclose(float(row["vdd_v"]), vdd_v, abs_tol=1.0e-12)]
        if not local or any(not row["valid"] for row in local):
            raise ValueError("r2 has incomplete legal-range trace at {:.2f} V".format(vdd_v))
        first_zero = next((row for row in local if int(row["Q"]) == 0), None)
        if first_zero is None or int(first_zero["code"]) > MAX_CODE - 2:
            raise ValueError("r2 cannot establish two-code headroom at {:.2f} V".format(vdd_v))
        first_zero["is_lock"] = 1
        headroom_code = int(first_zero["code"]) + 2
        headroom_rows = [row for row in local if int(row["code"]) == headroom_code]
        if len(headroom_rows) != 1:
            raise ValueError("r2 lacks the second headroom probe at {:.2f} V".format(vdd_v))
        headroom_rows[0]["headroom_verified"] = 1
    return rows


def replay_mapping() -> Dict[str, Any]:
    """Describe the frozen r2 mapping without re-running its old 0.75 V sizing.

    The metadata deliberately separates an observed seven-point electrical
    coverage claim from a minimum-area claim.  A future optimization requires
    a new 0.80 V sizing experiment and cannot be inferred from this replay.
    """

    return {
        "decision": "VERIFIED_FOR_0P80_TO_1P10",
        "tap_list": list(REPLAY_TAPS),
        "code_to_tap": {str(code): REPLAY_TAPS[code] for code in CODES},
        "validated_vdd_range_v": [0.80, 1.10],
        "selection_basis": "reused_r2_verified_mapping",
        "minimum_mapping_not_claimed": True,
        "reason": "r2 real-DFF probes pass the seven current legal VDD anchors; no new sizing search was run",
    }


def spice(value: float) -> str:
    """Format a finite value using an unambiguous HSPICE decimal literal."""

    return "{:.12e}".format(float(value))


def buffer_instance(name: str, output_node: str, input_node: str, cell: str) -> str:
    """Render one BUF CDL instance with all supply and well terminals connected.

    The foundry positional order is Y, VDD, VNW, VPW, VSS, A.  Keeping this in
    one helper makes every sensor and threshold cell explicitly use the same
    local VDD_A/VSS_A pair, including the well ties.
    """

    return "{} {} vdd_a vdd_a vss_a vss_a {} {}".format(name, output_node, input_node, cell)


def mux_instance(name: str, output_node: str, input_a: str, input_b: str, select_node: str) -> str:
    """Render one verified LVT 2:1 MUX with static binary-code selection."""

    return "{} {} vdd_a vdd_a vss_a vss_a {} {} {} {}".format(
        name, output_node, input_a, input_b, select_node, MUX_CELL
    )


def mux_tree_lines(taps: Sequence[int]) -> List[str]:
    """Render the fixed balanced seven-cell 8:1 tree for one increasing mapping."""

    if len(taps) != len(CODES) or any(later <= earlier for earlier, later in zip(taps, taps[1:])):
        raise ValueError("the 3-bit mapping must contain eight strictly increasing taps")
    lines = ["* Balanced 8:1 MUX tree: C[0] leaf, C[1] middle, C[2] root."]
    for group in range(4):
        lines.append(mux_instance(
            "XMUX_L1_{}".format(group), "mux_l1_{}".format(group),
            "thr_tap_{}".format(taps[2 * group]), "thr_tap_{}".format(taps[2 * group + 1]), "code0",
        ))
    for group in range(2):
        lines.append(mux_instance(
            "XMUX_L2_{}".format(group), "mux_l2_{}".format(group),
            "mux_l1_{}".format(2 * group), "mux_l1_{}".format(2 * group + 1), "code1",
        ))
    lines.append(mux_instance("XMUX_L3", "dff_ck", "mux_l2_0", "mux_l2_1", "code2"))
    return lines


def frozen_inputs() -> Dict[str, Any]:
    """Read exactly the approved historical evidence and verify its fixed contract."""

    architecture = load_json(FTC_ROOT / "analysis/minimal_pulse_comparator/architecture.json")
    old_rows = load_csv(
        FTC_ROOT / "analysis/minimal_pulse_comparator/code_sweep.csv",
        ("vdd_v", "code", "selected_tap", "d_code_ps", "w_s_int_ps", "q_final", "valid"),
    )
    old_summary = load_json(FTC_ROOT / "analysis/minimal_pulse_comparator/summary.json")
    report = (FTC_ROOT / "reports/FTC_MINIMAL_PROGRAMMABLE_THRESHOLD_PULSE_COMPARATOR.md").read_text(encoding="utf-8")
    fine_rows = load_csv(FTC_ROOT / "analysis/real_xor_pulse_width/fine.csv", ("vdd_v", "W_real_ps", "valid"))
    cells = load_json(FTC_ROOT / "discovery/selected_cells.json")
    if old_summary.get("decision") != "GO" or "**GO**" not in report:
        raise ValueError("the frozen minimal comparator GO evidence is unavailable")
    threshold = architecture.get("threshold", {})
    if threshold.get("buffer_cell") != "BUF_X0P7M_A9TL40" or threshold.get("mux_cell") != MUX_CELL:
        raise ValueError("the frozen threshold cells do not match this task")
    if threshold.get("mux_count") != MUX_COUNT or threshold.get("tap_list") != list(SIZING_TAPS):
        raise ValueError("the frozen threshold topology is not the approved 3-bit tree")
    if architecture.get("dff", {}).get("cell") != "DFFRPQ_X0P5M_A9TR40":
        raise ValueError("the frozen comparator DFF does not match this task")
    if cells.get("xor2", {}).get("cell") != "XOR2_X0P5M_A9TR40":
        raise ValueError("the frozen sensor XOR does not match this task")
    return {"architecture": architecture, "old_rows": old_rows, "fine_rows": fine_rows, "cells": cells}


def frozen_widths(fine_rows: Sequence[Mapping[str, str]]) -> Dict[float, float]:
    """Return the frozen real tap29 pulse width at every required VDD anchor."""

    widths: Dict[float, float] = {}
    for row in fine_rows:
        vdd = round(float(row["vdd_v"]), 2)
        if vdd in VDD_POINTS:
            if int(row["valid"]) != 1:
                raise ValueError("frozen real XOR pulse is invalid at {} V".format(vdd))
            widths[vdd] = float(row["W_real_ps"])
    if set(widths) != set(VDD_POINTS):
        raise ValueError("frozen real XOR data does not cover every calibration anchor")
    return widths


def dff_margin_ps(old_rows: Sequence[Mapping[str, str]]) -> float:
    """Derive the conservative real-DFF late-sampling margin from frozen results.

    The physical comparator, rather than a 50 percent crossing equation,
    determines the lock bit.  At each prior VDD this function finds the first
    measured Q=0 and records D(code)-W_S_int.  The largest value is the least
    optimistic margin used to size the new 0.75 V code-5 threshold.
    """

    margins: List[float] = []
    for vdd in (0.90, 1.10):
        local = sorted(
            [row for row in old_rows if round(float(row["vdd_v"]), 2) == vdd and int(row["valid"]) == 1],
            key=lambda row: int(row["code"]),
        )
        first_zero = next((row for row in local if int(row["q_final"]) == 0), None)
        if first_zero is None:
            raise ValueError("frozen comparator has no Q=0 boundary at {} V".format(vdd))
        margins.append(float(first_zero["d_code_ps"]) - float(first_zero["w_s_int_ps"]))
    margin = max(margins)
    if not math.isfinite(margin) or margin <= 0.0:
        raise ValueError("frozen DFF boundary margin is not physically usable")
    return margin


def render_deck(
    config: Mapping[str, Any], cells: Mapping[str, Any], vdd_v: float,
    taps: Sequence[int], code: int, sizing: bool, q_read_time_s: float = Q_READ_TIME_S,
) -> str:
    """Render one complete same-rail physical comparator probe.

    ``sizing`` adds arrival measurements at the historical high-end taps while
    retaining the exact real-DFF code-7 path.  A normal probe has one static
    code supply from time zero through readout; the constant interval before
    reset release/launch is the required code-settle separation.  The readout
    time is a testbench observation point, not a circuit parameter.  After
    range sizing it may move later only far enough to retain the documented
    200 ps Q-settle interval for the newly longest physical threshold path.
    """

    if code not in CODES:
        raise ValueError("code is outside the fixed 3-bit range")
    if max(taps) < 1:
        raise ValueError("at least one physical threshold buffer is required")
    includes = ['.include "{}"'.format(cells["source_files"]["rvt_cdl"])]
    if Path(cells["source_files"]["lvt_cdl"]).resolve() != Path(cells["source_files"]["rvt_cdl"]).resolve():
        includes.append('.include "{}"'.format(cells["source_files"]["lvt_cdl"]))
    launch = float(config["launch_time_s"])
    stop = launch + float(config["sampling_period_s"]) - float(config["tran_max_step_s"])
    bits = tuple((code >> bit) & 1 for bit in range(3))
    lines = [
        "* FTC static self-calibration physical comparator probe.",
        "* TT/25C only; 4-RVT/0-LVT tap29 sensor; 3-bit 7-MUX threshold; one real DFF.",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(float(config["temperature_c"]))),
        *includes,
        '.lib "{}" {}'.format(config["model_library"], config["corner"]),
        ".param VDD_VALUE={}".format(spice(vdd_v)),
        "V_VDD vdd_a vss_a 'VDD_VALUE'",
        "V_VSS vss_a 0 0",
        "V_SCLK s_clk vss_a PULSE(0 'VDD_VALUE' {} 1.000000000000e-12 1.000000000000e-12 {} {})".format(
            spice(launch), spice(float(config["sampling_period_s"]) / 2.0), spice(float(config["sampling_period_s"]))
        ),
        "* Code rails are static before reset release and remain static through probe/readout.",
        "V_CODE0 code0 vss_a {}".format("'VDD_VALUE'" if bits[0] else "0"),
        "V_CODE1 code1 vss_a {}".format("'VDD_VALUE'" if bits[1] else "0"),
        "V_CODE2 code2 vss_a {}".format("'VDD_VALUE'" if bits[2] else "0"),
        "* Active-high asynchronous clear is held during code settling and released before the isolated launch.",
        "V_DFF_RESET dff_reset vss_a PWL(0 'VDD_VALUE' {} 'VDD_VALUE' {} 0 {} 0)".format(
            spice(launch - CODE_SETTLE_S), spice(launch - CODE_SETTLE_S + 1.0e-11), spice(stop)
        ),
        "",
        "* Frozen four-stage RVT initial path.",
    ]
    rvt_input = "s_clk"
    for stage in range(SENSOR_RVT_INITIAL_STAGES):
        output = "rvt_initial_{}".format(stage)
        lines.append(buffer_instance("XRVT_INIT_{:02d}".format(stage), output, rvt_input, cells["delay_rvt"]["cell"]))
        rvt_input = output
    lines.append("* Frozen 30-stage RVT and LVT observable paths plus every real XOR load.")
    rvt_taps: List[str] = []
    lvt_taps: List[str] = []
    lvt_input = "s_clk"
    for stage in range(OBSERVABLE_STAGES):
        rvt_output = "rvt_{}".format(stage)
        lvt_output = "lvt_{}".format(stage)
        lines.append(buffer_instance("XRVT_{:02d}".format(stage), rvt_output, rvt_input, cells["delay_rvt"]["cell"]))
        lines.append(buffer_instance("XLVT_{:02d}".format(stage), lvt_output, lvt_input, cells["delay_lvt"]["cell"]))
        rvt_taps.append(rvt_output)
        lvt_taps.append(lvt_output)
        rvt_input = rvt_output
        lvt_input = lvt_output
    for stage, (rvt_tap, lvt_tap) in enumerate(zip(rvt_taps, lvt_taps)):
        lines.append("XXOR_{:02d} xor_{} vdd_a vdd_a vss_a vss_a {} {} {}".format(
            stage, stage, rvt_tap, lvt_tap, cells["xor2"]["cell"]
        ))
    lines.append("* The LVT threshold chain is extended only to the frozen mapping's maximum tap.")
    threshold_input = "xor_29"
    for tap in range(1, max(taps) + 1):
        output = "thr_tap_{}".format(tap)
        lines.append(buffer_instance("XTHR_BUF_{:02d}".format(tap), output, threshold_input, cells["delay_lvt"]["cell"]))
        threshold_input = output
    lines.extend(["", *mux_tree_lines(taps), "", "* DFF ports: Q VDD VNW VPW VSS CK D R."])
    lines.append("XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(cells["dff"]["cell"]))
    lines.extend([
        "",
        ".tran {} {}".format(spice(float(config["tran_max_step_s"])), spice(stop)),
        ".measure tran t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1",
        ".measure tran t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1",
        ".measure tran t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1",
        ".measure tran q_final_v FIND v(q_final,vss_a) AT={}".format(spice(q_read_time_s)),
        ".measure tran vdd_a_min_v MIN v(vdd_a,vss_a) FROM=0 TO={}".format(spice(stop)),
    ])
    if sizing:
        for tap in SIZING_TAPS:
            lines.append(".measure tran t_thr_tap_{:02d}_rise WHEN v(thr_tap_{},vss_a)='VDD_VALUE/2' RISE=1".format(tap, tap))
    lines.extend([".end", ""])
    return "\n".join(lines)


def execute_probe(
    hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any],
    label: str, vdd_v: float, taps: Sequence[int], code: int, sizing: bool,
    q_read_time_s: float = Q_READ_TIME_S,
) -> Dict[str, Any]:
    """Run one isolated physical probe and retain its complete raw evidence together."""

    scenario = run_dir / "scenarios" / label
    scenario.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(FTC_ROOT / "spice/empty_subckt.sp_cal", scenario / "empty_subckt.sp_cal")
    deck = scenario / "static_self_calibration.sp"
    deck.write_text(render_deck(config, cells, vdd_v, taps, code, sizing, q_read_time_s), encoding="ascii")
    result = subprocess.run(
        [str(hspice), deck.name, "-o", "static_self_calibration"], cwd=str(scenario),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=300,
    )
    (scenario / "hspice_command.log").write_text(
        "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            " ".join([str(hspice), deck.name, "-o", "static_self_calibration"]), result.returncode, result.stdout, result.stderr
        ), encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, scenario))
    warnings = run_dc_sweep.validate_listing(scenario / "static_self_calibration.lis")
    values = run_dc_sweep.parse_measurements(run_dc_sweep.find_measurement_file(scenario, "static_self_calibration"))
    return {
        "scenario": str(scenario.relative_to(run_dir)), "warnings": warnings, "vdd_v": vdd_v,
        "code": code, "t_xor_rise_s": values.get("t_xor_rise"), "t_xor_fall_s": values.get("t_xor_fall"),
        "t_ck_rise_s": values.get("t_ck_rise"), "q_final_v": values.get("q_final_v"),
        "vdd_a_min_v": values.get("vdd_a_min_v"), "q_read_time_s": q_read_time_s,
        "tap_arrivals_s": {tap: values.get("t_thr_tap_{:02d}_rise".format(tap)) for tap in SIZING_TAPS} if sizing else {},
    }


def classify_probe(record: Mapping[str, Any], selected_tap: int) -> Dict[str, Any]:
    """Convert raw HSPICE measurements into the trace quantities and validity bit."""

    values = {name: finite_number(record.get(name)) for name in ("t_xor_rise_s", "t_xor_fall_s", "t_ck_rise_s", "q_final_v")}
    output: Dict[str, Any] = {"selected_tap": selected_tap, "valid": False, "Q": None, "D_code_ps": None, "W_S_int_ps": None}
    if any(value is None for value in values.values()):
        return output
    width_s = values["t_xor_fall_s"] - values["t_xor_rise_s"]
    delay_s = values["t_ck_rise_s"] - values["t_xor_rise_s"]
    latest_allowed_ck_s = float(record.get("q_read_time_s", Q_READ_TIME_S)) - Q_SETTLE_S
    if width_s is None or delay_s is None or width_s <= 0.0 or delay_s <= 0.0 or values["t_ck_rise_s"] > latest_allowed_ck_s:
        return output
    output.update({
        "valid": True,
        "Q": 1 if values["q_final_v"] >= float(record["vdd_v"]) / 2.0 else 0,
        "D_code_ps": delay_s * 1.0e12,
        "W_S_int_ps": width_s * 1.0e12,
    })
    return output


def choose_mapping(sizing_record: Mapping[str, Any], widths: Mapping[float, float], margin_ps: float) -> Dict[str, Any]:
    """Choose the unique minimum high-end extension from the one sizing run.

    Codes 0..4 stay at the approved low taps.  The existing code-7 physical
    delay anchors the extrapolation, while the 22->24 measured arrival slope
    projects only the additional BUF stages needed for 0.75 V code 5 to be at
    least one frozen real-DFF margin later than the measured/frozen pulse.
    Codes 6 and 7 are the immediately following physical taps, reserving two
    genuinely longer choices without adding unneeded spacing or circuitry.
    """

    current = classify_probe(sizing_record, SIZING_TAPS[7])
    arrivals: Dict[int, float] = {}
    xor_rise = finite_number(sizing_record.get("t_xor_rise_s"))
    if not current["valid"] or xor_rise is None:
        return {"decision": "3-bit range = insufficient", "reason": "0.75 V sizing comparator measurement is incomplete"}
    for tap, arrival in sizing_record.get("tap_arrivals_s", {}).items():
        arrival_value = finite_number(arrival)
        if arrival_value is None:
            return {"decision": "3-bit range = insufficient", "reason": "0.75 V sizing tap {} is missing".format(tap)}
        arrivals[int(tap)] = (arrival_value - xor_rise) * 1.0e12
    if set(arrivals) != set(SIZING_TAPS) or any(arrivals[right] <= arrivals[left] for left, right in zip(SIZING_TAPS, SIZING_TAPS[1:])):
        return {"decision": "3-bit range = insufficient", "reason": "0.75 V sizing threshold arrivals are not strictly increasing"}
    per_buffer_ps = (arrivals[24] - arrivals[22]) / 2.0
    target_width_ps = max(float(current["W_S_int_ps"]), float(widths[0.75]))
    target_delay_ps = target_width_ps + margin_ps
    estimated_code7_ps = float(current["D_code_ps"])
    required_extra = max(0, int(math.ceil((target_delay_ps - estimated_code7_ps) / per_buffer_ps)))
    tap5 = max(20, 24 + required_extra)
    taps = tuple(LOW_TAPS + (tap5, tap5 + 1, tap5 + 2))
    # The probe readout is an observation schedule, not delay-line hardware.
    # Keep the old 3 ns point whenever it already settles; otherwise advance it
    # only to the predicted longest new code-7 clock crossing plus the existing
    # DFF Q-settle requirement.  It remains inside the already-fixed 7 ns
    # transient window and never alters the physical comparator topology.
    estimated_max_delay_ps = estimated_code7_ps + (taps[-1] - 24) * per_buffer_ps
    q_read_time_s = max(
        Q_READ_TIME_S,
        float(sizing_record["t_xor_rise_s"]) + estimated_max_delay_ps * 1.0e-12 + Q_SETTLE_S,
    )
    return {
        "decision": "READY_FOR_FULL_RANGE", "tap_list": list(taps), "code_to_tap": {str(code): taps[code] for code in CODES},
        "sizing_vdd_v": 0.75, "sizing_q_code7": current["Q"], "sizing_d_code7_ps": current["D_code_ps"],
        "sizing_w_s_int_ps": current["W_S_int_ps"], "frozen_w_real_ps": widths[0.75],
        # Preserve every plan-required 0.75 V propagation observation in the
        # compact mapping evidence as delays relative to xor_29's rising edge.
        # The raw .mt0.csv remains below the task run root for full waveform
        # provenance, while reviewers can audit sizing without parsing HSPICE.
        "sizing_tap_arrival_ps": {str(tap): arrivals[tap] for tap in SIZING_TAPS},
        "dff_margin_ps": margin_ps, "measured_tail_buffer_delay_ps": per_buffer_ps,
        "target_delay_code5_ps": target_delay_ps, "estimated_delay_code7_ps": estimated_max_delay_ps,
        "q_read_time_s": q_read_time_s,
        "reason": "retained low taps and selected the shortest high-end extension with two following headroom taps",
    }


def trace_voltage(
    hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any],
    vdd_v: float, taps: Sequence[int], step_base: int, q_read_time_s: float,
) -> Tuple[List[Dict[str, Any]], int]:
    """Execute the prescribed linear scan and exactly two post-lock probes."""

    rows: List[Dict[str, Any]] = []
    lock_code: Optional[int] = None
    next_step = step_base
    for code in CODES:
        record = execute_probe(
            hspice, run_dir, config, cells, "v{:0.2f}_step{:02d}_code{}".format(vdd_v, next_step, code).replace(".", "p"),
            vdd_v, taps, code, False, q_read_time_s,
        )
        value = classify_probe(record, taps[code])
        row = {"vdd_v": vdd_v, "step_index": next_step, "code": code, "selected_tap": taps[code],
               "Q": value["Q"], "D_code_ps": value["D_code_ps"], "W_S_int_ps": value["W_S_int_ps"],
               "is_lock": 0, "headroom_verified": 0, "valid": value["valid"]}
        rows.append(row)
        next_step += 1
        if not value["valid"] or value["Q"] == 0:
            lock_code = code if value["valid"] and value["Q"] == 0 else None
            if lock_code is not None:
                rows[-1]["is_lock"] = 1
            break
    if lock_code is not None:
        for code in (lock_code + 1, lock_code + 2):
            if code > MAX_CODE:
                break
            record = execute_probe(
                hspice, run_dir, config, cells, "v{:0.2f}_step{:02d}_code{}".format(vdd_v, next_step, code).replace(".", "p"),
                vdd_v, taps, code, False, q_read_time_s,
            )
            value = classify_probe(record, taps[code])
            rows.append({"vdd_v": vdd_v, "step_index": next_step, "code": code, "selected_tap": taps[code],
                         "Q": value["Q"], "D_code_ps": value["D_code_ps"], "W_S_int_ps": value["W_S_int_ps"],
                         "is_lock": 0, "headroom_verified": 0, "valid": value["valid"]})
            next_step += 1
        if len(rows) >= 3 and all(row["code"] in (lock_code + 1, lock_code + 2) and row["valid"] and row["Q"] == 0 for row in rows[-2:]):
            rows[-1]["headroom_verified"] = 1
    return rows, next_step


def evaluate_voltage(rows: Sequence[Mapping[str, Any]], vdd_v: float) -> Dict[str, Any]:
    """Apply the static-calibration gate to one recorded linear scan."""

    local = sorted([row for row in rows if round(float(row["vdd_v"]), 2) == vdd_v], key=lambda row: int(row["step_index"]))
    reasons: List[str] = []
    if not local or any(not row["valid"] for row in local):
        return {"vdd_v": vdd_v, "decision": "NO-GO", "reasons": ["one or more physical probe measurements are incomplete"], "lock_code": None}
    q_values = [int(row["Q"]) for row in local]
    transitions = sum(left != right for left, right in zip(q_values, q_values[1:]))
    lock_rows = [row for row in local if int(row["is_lock"]) == 1]
    lock_code = int(lock_rows[0]["code"]) if len(lock_rows) == 1 else None
    delays = [float(row["D_code_ps"]) for row in local]
    monotonic = all(later > earlier for earlier, later in zip(delays, delays[1:]))
    q_monotonic = all(left >= right for left, right in zip(q_values, q_values[1:]))
    headroom_rows = [row for row in local if lock_code is not None and int(row["code"]) in (lock_code + 1, lock_code + 2)]
    headroom = lock_code is not None and lock_code <= MAX_CODE - 2 and len(headroom_rows) == 2 and all(
        int(row["Q"]) == 0 for row in headroom_rows
    ) and int(local[-1]["headroom_verified"]) == 1
    if transitions != 1:
        reasons.append("Q does not have exactly one 1-to-0 transition")
    if lock_code is None or not (1 <= lock_code <= MAX_CODE - 2):
        reasons.append("C_lock is outside the required 1..5 range")
    if not q_monotonic:
        reasons.append("Q returns to 1 after becoming 0")
    if not monotonic:
        reasons.append("measured D(code) is not strictly increasing")
    if not headroom:
        reasons.append("two real longer headroom codes were not verified")
    return {"vdd_v": vdd_v, "decision": "GO" if not reasons else "NO-GO", "reasons": reasons,
            "lock_code": lock_code, "headroom_codes": [] if lock_code is None else [lock_code + 1, lock_code + 2],
            "headroom_up": None if lock_code is None else MAX_CODE - lock_code, "q_sequence": q_values,
            "d_code_ps": delays, "monotonic": monotonic, "q_monotonic": q_monotonic, "headroom_verified": headroom}


def evaluate_all(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Combine all seven independently calibrated current-range VDD gates."""

    per_voltage = [evaluate_voltage(rows, vdd) for vdd in VDD_POINTS]
    passed = all(item["decision"] == "GO" for item in per_voltage)
    reasons = [reason for item in per_voltage for reason in item["reasons"]]
    return {"decision": "Static Self Calibration + Full-Range Code Headroom = GO" if passed else "NO-GO",
            "per_voltage": per_voltage, "decision_reasons": ["all seven normal VDD anchors passed"] if passed else reasons}


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Write the compact public trace, omitting internal runner-only validity state."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=TRACE_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in TRACE_FIELDS})


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write deterministic compact evidence with stable key order."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_report(path: Path, mapping: Mapping[str, Any], result: Mapping[str, Any]) -> None:
    """Write exactly the four required research answers and the final gate.

    A failing headroom gate does not erase a correctly observed hardware
    transition.  The four report answers are therefore derived independently:
    a run can truthfully report unique real-DFF locks at all anchors while
    still rejecting range coverage and next-stage admission because one lock
    consumes too much of the remaining code space.
    """

    per_voltage = result.get("per_voltage", [])
    passed = result["decision"] == "Static Self Calibration + Full-Range Code Headroom = GO"
    unique_locks = len(per_voltage) == len(VDD_POINTS) and all(
        item.get("lock_code") is not None and item.get("q_monotonic") for item in per_voltage
    )
    headroom_ok = len(per_voltage) == len(VDD_POINTS) and all(
        item.get("headroom_verified") for item in per_voltage
    )
    lines = [
        "# FTC Static Self Calibration + Full-Range Headroom", "",
        "## Decision", "", "**{}**".format(result["decision"]), "",
        "## Required Answers", "",
        "1. 冻结 3-bit tap mapping 是否覆盖 0.80--1.10 V 的正常工作范围？{}。".format("是" if passed else "否"),
        "2. 真实 DFF 驱动的静态自校准是否在每个 VDD 锚点自动找到唯一 C_lock？{}。".format("是" if unique_locks else "否"),
        "3. 每个工作点校准后是否至少保留两个更长延迟 code？{}。".format("是" if headroom_ok else "否"),
        "4. 是否可以进入下一阶段 Programmable Acceptance Window？{}。".format("可以" if passed else "不可以"), "",
        "## Mapping", "", "- decision: {}".format(mapping["decision"]),
        "- taps: {}".format(mapping.get("tap_list", "not published")),
        "- selection basis: {}".format(mapping.get("selection_basis", "not published")),
        "- new-range minimum mapping claimed: {}".format("no" if mapping.get("minimum_mapping_not_claimed") else "not stated"), "",
        "## Per-VDD Evidence", "", "| VDD (V) | C_lock | H_up | Decision |", "|---:|---:|---:|---|",
    ]
    for item in per_voltage:
        lines.append("| {:.2f} | {} | {} | {} |".format(item["vdd_v"], item.get("lock_code"), item.get("headroom_up"), item["decision"]))
    lines.extend(["", "## Gate Reason", ""])
    lines.extend(["- {}".format(reason) for reason in result.get("decision_reasons", [])])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare_run(run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any]) -> Path:
    """Validate the local EDA contract before creating the single raw-run root."""

    if run_dir.exists():
        raise ValueError("refusing to overwrite existing task run directory: {}".format(run_dir))
    hspice = run_dc_sweep.require_regular_file(Path(config["hspice"]), "HSPICE", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if str(config["expected_hspice_version"]) not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    for source in list(cells["source_files"].values()) + [config["model_library"], FTC_ROOT / "spice/empty_subckt.sp_cal"]:
        run_dc_sweep.require_regular_file(Path(source), "FTC source collateral")
    run_dir.mkdir(parents=True)
    write_json(run_dir / "manifest.json", {"study": "ftc_static_self_calibration_full_range_headroom", "hspice": str(hspice),
                                               "hspice_version": version, "scope": "TT/25C static calibration only"})
    return hspice


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Expose replay locations while keeping electrical choices immutable."""

    parser = argparse.ArgumentParser(description="re-publish FTC static self-calibration from completed r2 evidence")
    parser.add_argument("--raw-run-dir", type=Path, default=FTC_ROOT / "runs/static_self_calibration_full_range/r2")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis/static_self_calibration")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports/FTC_STATIC_SELF_CALIBRATION_FULL_RANGE_HEADROOM.md")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Validate completed r2 raw evidence and publish the current-range result."""

    args = parse_args(argv)
    raw_run_dir = args.raw_run_dir.resolve()
    analysis_dir = args.analysis_dir.resolve()
    report_output = args.report_output.resolve()
    rows = replay_r2_trace(raw_run_dir)
    mapping = replay_mapping()
    result = evaluate_all(rows)
    if result["decision"] != "Static Self Calibration + Full-Range Code Headroom = GO":
        raise RuntimeError("r2 replay did not pass the required current-range calibration gate")
    write_csv(analysis_dir / "calibration_trace.csv", rows)
    write_json(analysis_dir / "range_mapping.json", mapping)
    write_json(analysis_dir / "summary.json", {
        "schema_version": 2,
        "source_run": str(raw_run_dir),
        "new_hspice_runs": 0,
        "scenario_count": len(rows),
        "mapping": mapping,
        **result,
    })
    render_report(report_output, mapping, result)
    print("FTC_STATIC_SELF_CALIBRATION decision={}".format(result["decision"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
