#!/usr/bin/env python3
"""Measure the fixed FTC tap29 programmable pulse-width comparator.

This runner owns one intentionally small electrical experiment.  It retains
the frozen 4-RVT/0-LVT FTC sensor and its complete XOR observation bank, then
loads only ``xor_29`` with a 24-buffer LVT timing chain, a balanced three-level
LVT MUX tree, and one real DFF.  The script does not generate a reusable delay
macro, search the PDK, sweep PVT, or implement calibration logic.  Its sole
physical question is whether the fixed codes 0--7 create a monotonic sampling
threshold and whether the DFF follows the measured pulse-width comparison.
"""

import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

try:
    import matplotlib

    # The HSPICE execution environment has no display server.  Select the
    # deterministic file backend before pyplot is imported.
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as error:  # pragma: no cover - environment dependency guard.
    raise SystemExit("minimal pulse comparator requires Matplotlib: {}".format(error))


FTC_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
PHASE1_SCRIPTS = FTC_ROOT.parent / "phase1" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(PHASE1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PHASE1_SCRIPTS))
import run_dc_sweep  # noqa: E402  # Reuse only reviewed HSPICE checks and MEAS parsing.


# These constants are the task definition, deliberately not command-line
# knobs.  Changing any of them creates a different comparator experiment.
TAP_INDEX = 29
SENSOR_RVT_INITIAL_STAGES = 4
SENSOR_LVT_INITIAL_STAGES = 0
OBSERVABLE_STAGES = 30
VDD_POINTS = (1.10, 0.90)
CODES = tuple(range(8))
THRESHOLD_TAPS = (10, 12, 14, 16, 18, 20, 22, 24)
THRESHOLD_BUFFER_COUNT = 24
MUX_CELL = "MXT2_X0P5M_A9TL40"
MUX_CDL_PORTS = ("Y", "VDD", "VNW", "VPW", "VSS", "A", "B", "S0")
Q_SETTLE_S = 2.0e-10
Q_READ_TIME_S = 3.0e-9
LATEST_ALLOWED_CK_S = Q_READ_TIME_S - Q_SETTLE_S

RESULT_FIELDS = (
    "vdd_v", "code", "selected_tap", "scenario",
    "t_xor_rise_s", "t_xor_fall_s", "w_s_int_ps", "t_ck_rise_s", "d_code_ps",
    "q_final_v", "q_final", "w_s_frozen_ps", "delta_w_load_ps",
    "q_expected", "q_matches_expected", "valid",
)


def finite_number(value: Any) -> Optional[float]:
    """Return a finite scalar, retaining failed HSPICE measures as ``None``.

    A failed timing crossing is physical evidence and must never be converted
    to zero.  Keeping it absent lets the final gate distinguish incomplete
    simulation evidence from a valid zero-valued DFF decision.
    """

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def require_equal(actual: Any, expected: Any, description: str) -> None:
    """Reject a frozen-contract mismatch using exact numeric semantics."""

    if isinstance(expected, float):
        if finite_number(actual) != expected:
            raise ValueError("{} must remain {}".format(description, expected))
    elif actual != expected:
        raise ValueError("{} must remain {!r}".format(description, expected))


def load_json(path: Path) -> Dict[str, Any]:
    """Read one object-shaped task input without modifying it."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def load_csv(path: Path, required_fields: Sequence[str]) -> List[Dict[str, str]]:
    """Load a nonempty CSV only after verifying its required schema."""

    if not path.is_file():
        raise ValueError("required evidence is unavailable: {}".format(path))
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not set(required_fields).issubset(reader.fieldnames):
            raise ValueError("required evidence schema is incomplete: {}".format(path))
        rows = list(reader)
    if not rows:
        raise ValueError("required evidence is empty: {}".format(path))
    return rows


def parse_manifest_mux(manifest: Path, cells: Mapping[str, Any]) -> Dict[str, Any]:
    """Recover exactly the prior verified LVT MUX, never searching alternatives.

    The manifest is the approved provenance for this one MUX.  Its source CDL
    and functional Verilog must agree with the selected FTC source paths; a
    mismatch is an audit failure, not permission to select a different cell.
    """

    rows = load_csv(manifest, ("candidate_id", "cell_names", "cdl_ports", "source_cdl", "source_verilog"))
    matches = [row for row in rows if row["candidate_id"] == "mux_lvt"]
    if len(matches) != 1:
        raise ValueError("candidate manifest must contain exactly one mux_lvt row")
    row = matches[0]
    if row["cell_names"] != "['{}']".format(MUX_CELL):
        raise ValueError("candidate manifest mux_lvt cell does not match {}".format(MUX_CELL))
    if tuple(row["cdl_ports"].split("|")) != MUX_CDL_PORTS:
        raise ValueError("candidate manifest mux_lvt CDL ports are incompatible")
    source_files = cells.get("source_files", {})
    if row["source_cdl"] != source_files.get("lvt_cdl") or row["source_verilog"] != source_files.get("lvt_verilog"):
        raise ValueError("candidate manifest mux_lvt source collateral disagrees with selected cells")
    return {
        "cell": MUX_CELL,
        "cdl_ports": list(MUX_CDL_PORTS),
        "source_cdl": row["source_cdl"],
        "source_verilog": row["source_verilog"],
        "select_truth": {"0": "A", "1": "B"},
    }


def verify_mux_collateral(mux: Mapping[str, Any]) -> None:
    """Cross-check the manifest MUX against its installed CDL and Verilog views.

    This is intentionally a narrow textual contract, not a new cell-discovery
    pass.  The expected subcircuit declaration establishes physical positional
    ports, while the exact vendor UDP truth-table rows establish that A is
    selected for S0=0 and B is selected for S0=1.  Any drift stops the task
    before a deck is created rather than silently choosing another family.
    """

    cdl_text = Path(mux["source_cdl"]).read_text(encoding="latin-1", errors="replace")
    expected_subckt = ".SUBCKT {} {}".format(MUX_CELL, " ".join(MUX_CDL_PORTS))
    if expected_subckt.upper() not in cdl_text.upper():
        raise ValueError("verified LVT MUX CDL declaration is incompatible")
    verilog_text = Path(mux["source_verilog"]).read_text(encoding="latin-1", errors="replace")
    primitive = "primitive udp_mux2_sc9mc_logic0040ll_base_lvt_c40 (out, in0, in1, sel);"
    required_rows = (
        "1  ?   0  :  1 ;",
        "0  ?   0  :  0 ;",
        "?  1   1  :  1 ;",
        "?  0   1  :  0 ;",
    )
    if primitive not in verilog_text or any(row not in verilog_text for row in required_rows):
        raise ValueError("verified LVT MUX Verilog select truth table is incompatible")


def verify_frozen_provenance() -> None:
    """Read each task-mandated historical artifact without rerunning it.

    Only their presence, schema, and prior terminal conclusion are checked.
    These values never feed a threshold choice, preserving the plan's rule that
    tap count and code range remain fixed rather than re-optimized from prior
    analyses.
    """

    load_csv(
        FTC_ROOT / "analysis" / "reference_sensitivity_contrast" / "simple_candidate_screen.csv",
        ("candidate_id", "v0_v", "d_r_25c_ps"),
    )
    report = FTC_ROOT / "reports" / "FTC_COMPOSITE_REFERENCE_SENSITIVITY_SHAPING.md"
    if not report.is_file() or "Passive Sensitivity-Contrast Reference = NO-GO" not in report.read_text(encoding="utf-8"):
        raise ValueError("frozen composite-reference NO-GO report is unavailable or incompatible")


def verify_frozen_inputs(config: Mapping[str, Any], cells: Mapping[str, Any], mux: Mapping[str, Any]) -> None:
    """Enforce the exact sensor, cell, and environment contract before a run.

    This check makes the new evidence comparable with the frozen tap29 data.
    It does not expose tunable architecture choices because this task is a
    fixed primitive validation rather than a macro exploration framework.
    """

    for field, expected in (
        ("technology", "SMIC40LL"), ("corner", "tt"), ("temperature_c", 25.0),
        ("observable_stages", OBSERVABLE_STAGES), ("launch_time_s", 1.0e-9),
        ("tran_max_step_s", 1.0e-12), ("sampling_period_s", 6.0e-9),
    ):
        require_equal(config.get(field), expected, "FTC config {}".format(field))
    point = config.get("selected_operating_point")
    if not isinstance(point, dict):
        raise ValueError("FTC selected operating point is unavailable")
    require_equal(point.get("initial_rvt_stages"), SENSOR_RVT_INITIAL_STAGES, "selected initial RVT stages")
    require_equal(point.get("initial_lvt_stages"), SENSOR_LVT_INITIAL_STAGES, "selected initial LVT stages")
    for role, expected_cell in (
        ("delay_lvt", "BUF_X0P7M_A9TL40"), ("delay_rvt", "BUF_X0P7M_A9TR40"),
        ("xor2", "XOR2_X0P5M_A9TR40"), ("dff", "DFFRPQ_X0P5M_A9TR40"),
    ):
        if cells.get(role, {}).get("cell") != expected_cell:
            raise ValueError("selected {} cell must remain {}".format(role, expected_cell))
    dff = cells["dff"]
    if dff.get("clock_polarity") != "positive_edge" or dff.get("reset_polarity") != "active_high_async_clear":
        raise ValueError("selected DFF polarity contract is incompatible")
    if tuple(dff.get("cdl_ports", ())) != ("Q", "VDD", "VNW", "VPW", "VSS", "CK", "D", "R"):
        raise ValueError("selected DFF CDL ports are incompatible")
    if mux.get("cell") != MUX_CELL or tuple(mux.get("cdl_ports", ())) != MUX_CDL_PORTS:
        raise ValueError("verified LVT MUX contract is incompatible")


def frozen_widths(fine_csv: Path) -> Dict[float, float]:
    """Index the two immutable real-XOR widths used solely for load deltas."""

    rows = load_csv(fine_csv, ("vdd_v", "W_real_ps", "valid"))
    values: Dict[float, float] = {}
    for row in rows:
        voltage = round(float(row["vdd_v"]), 2)
        if voltage in VDD_POINTS:
            if int(row["valid"]) != 1:
                raise ValueError("frozen tap29 width is invalid at {} V".format(voltage))
            if voltage in values:
                raise ValueError("duplicate frozen tap29 width at {} V".format(voltage))
            values[voltage] = float(row["W_real_ps"])
    if set(values) != set(VDD_POINTS):
        raise ValueError("frozen tap29 widths do not cover {}".format(VDD_POINTS))
    return values


def spice(value: float) -> str:
    """Format one scalar in an HSPICE-safe decimal scientific notation."""

    return "{:.12e}".format(float(value))


def buffer_instance(name: str, output_node: str, input_node: str, cell: str) -> str:
    """Render one positional BUF instance with every power and well pin mapped.

    BUF CDL port order is ``Y VDD VNW VPW VSS A``.  The threshold and sensor
    are intentionally on the same rail pair, so VDD/VNW use ``vdd_a`` and
    VPW/VSS use ``vss_a``.  Keeping this mapping in one helper prevents an
    unpowered-well error from being repeated across the 84 buffers per deck.
    """

    return "{} {} vdd_a vdd_a vss_a vss_a {} {}".format(name, output_node, input_node, cell)


def mux_instance(name: str, output_node: str, input_a: str, input_b: str, select_node: str) -> str:
    """Render one positional LVT MUX with documented A/B and select ports.

    MXT2 CDL order is ``Y VDD VNW VPW VSS A B S0`` and vendor UDP evidence
    establishes S0=0 selects A while S0=1 selects B.  The caller therefore
    wires low-code input to A and high-code input to B at every tree level.
    """

    return "{} {} vdd_a vdd_a vss_a vss_a {} {} {} {}".format(
        name, output_node, input_a, input_b, select_node, MUX_CELL
    )


def threshold_tree_lines() -> List[str]:
    """Render the seven-MUX balanced tree for codes 0..7 in tap order.

    Leaf pairs use C[0], the two middle nodes use C[1], and the root uses C[2].
    With the verified A/B select semantics this realizes binary code ordering
    without select inversions, added delay cells, or dynamic configuration.
    """

    lines = ["* Balanced 8:1 LVT MUX tree: C[0]/C[1]/C[2] select low to high taps."]
    for group in range(4):
        low_tap = THRESHOLD_TAPS[2 * group]
        high_tap = THRESHOLD_TAPS[2 * group + 1]
        lines.append(mux_instance("XMUX_L1_{}".format(group), "mux_l1_{}".format(group), "thr_tap_{}".format(low_tap), "thr_tap_{}".format(high_tap), "code0"))
    for group in range(2):
        lines.append(mux_instance("XMUX_L2_{}".format(group), "mux_l2_{}".format(group), "mux_l1_{}".format(2 * group), "mux_l1_{}".format(2 * group + 1), "code1"))
    lines.append(mux_instance("XMUX_L3", "dff_ck", "mux_l2_0", "mux_l2_1", "code2"))
    return lines


def render_integrated_deck(config: Mapping[str, Any], cells: Mapping[str, Any], vdd_v: float, code: int) -> str:
    """Render one complete frozen-sensor plus fixed-comparator HSPICE deck.

    The sensor wiring mirrors the frozen real-XOR experiment: a common source
    drives a 4-RVT/0-LVT initial delay and two 30-stage observable chains.
    All thirty physical XOR cells remain present, preserving tap29 fanout and
    bank loading.  Only ``xor_29`` additionally drives the timing chain and
    DFF.  Code rails are static from t=0, and the DFF reset releases at 510 ps,
    well before the one-nanosecond launch edge.
    """

    if code not in CODES:
        raise ValueError("code must be one of {}".format(CODES))
    includes = ['.include "{}"'.format(cells["source_files"]["rvt_cdl"])]
    if Path(cells["source_files"]["lvt_cdl"]).resolve() != Path(cells["source_files"]["rvt_cdl"]).resolve():
        includes.append('.include "{}"'.format(cells["source_files"]["lvt_cdl"]))
    launch = float(config["launch_time_s"])
    period = float(config["sampling_period_s"])
    stop = launch + period - float(config["tran_max_step_s"])
    bits = tuple((code >> index) & 1 for index in range(3))
    lines = [
        "* Fixed FTC tap29 programmable threshold pulse comparator.",
        "* Scope: TT/25C, 4-RVT/0-LVT sensor, one static 3-bit code, one DFF.",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(float(config["temperature_c"]))),
        *includes,
        '.lib "{}" {}'.format(config["model_library"], config["corner"]),
        ".param VDD_VALUE={}".format(spice(vdd_v)),
        "V_VDD vdd_a vss_a 'VDD_VALUE'",
        "V_VSS vss_a 0 0",
        "V_SCLK s_clk vss_a PULSE(0 'VDD_VALUE' {} 1.000000000000e-12 1.000000000000e-12 {} {})".format(spice(launch), spice(period / 2.0), spice(period)),
        "* Static code supplies: code0 is least significant, code2 most significant.",
        "V_CODE0 code0 vss_a {}".format("'VDD_VALUE'" if bits[0] else "0"),
        "V_CODE1 code1 vss_a {}".format("'VDD_VALUE'" if bits[1] else "0"),
        "V_CODE2 code2 vss_a {}".format("'VDD_VALUE'" if bits[2] else "0"),
        "* Active-high asynchronous DFF clear; release before the one launch edge.",
        "V_DFF_RESET dff_reset vss_a PWL(0 'VDD_VALUE' 5.000000000000e-10 'VDD_VALUE' 5.100000000000e-10 0 {} 0)".format(spice(stop)),
        "",
        "* Frozen 4-stage RVT initial chain.",
    ]
    rvt_input = "s_clk"
    for stage in range(SENSOR_RVT_INITIAL_STAGES):
        output = "rvt_initial_{}".format(stage)
        lines.append(buffer_instance("XRVT_INIT_{:02d}".format(stage), output, rvt_input, cells["delay_rvt"]["cell"]))
        rvt_input = output
    lines.extend(["", "* Frozen 30-stage RVT observable chain."])
    rvt_taps: List[str] = []
    for stage in range(OBSERVABLE_STAGES):
        output = "rvt_{}".format(stage)
        lines.append(buffer_instance("XRVT_{:02d}".format(stage), output, rvt_input, cells["delay_rvt"]["cell"]))
        rvt_taps.append(output)
        rvt_input = output
    lines.extend(["", "* Frozen 0-stage LVT initial chain followed by 30 observable stages."])
    lvt_input = "s_clk"
    lvt_taps: List[str] = []
    for stage in range(OBSERVABLE_STAGES):
        output = "lvt_{}".format(stage)
        lines.append(buffer_instance("XLVT_{:02d}".format(stage), output, lvt_input, cells["delay_lvt"]["cell"]))
        lvt_taps.append(output)
        lvt_input = output
    lines.extend(["", "* Full 30-cell real XOR observation bank retained from frozen sensor."])
    for stage, (rvt_tap, lvt_tap) in enumerate(zip(rvt_taps, lvt_taps)):
        lines.append("XXOR_{:02d} xor_{} vdd_a vdd_a vss_a vss_a {} {} {}".format(stage, stage, rvt_tap, lvt_tap, cells["xor2"]["cell"]))
    lines.extend(["", "* Dedicated 24-stage LVT threshold chain driven only by xor_29."])
    threshold_input = "xor_29"
    for stage in range(1, THRESHOLD_BUFFER_COUNT + 1):
        output = "thr_tap_{}".format(stage)
        lines.append(buffer_instance("XTHR_BUF_{:02d}".format(stage), output, threshold_input, cells["delay_lvt"]["cell"]))
        threshold_input = output
    lines.extend(["", *threshold_tree_lines(), "", "* DFF ports: Q VDD VNW VPW VSS CK D R; CK is delayed xor_29, D is xor_29."])
    lines.append("XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(cells["dff"]["cell"]))
    lines.extend([
        "",
        ".tran {} {}".format(spice(float(config["tran_max_step_s"])), spice(stop)),
        "* All timing values are first 50%-VDD crossings of the integrated circuit.",
        ".measure tran t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1",
        ".measure tran t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1",
        ".measure tran t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1",
        ".measure tran q_final_v FIND v(q_final,vss_a) AT={}".format(spice(Q_READ_TIME_S)),
        ".measure tran vdd_a_min_v MIN v(vdd_a,vss_a) FROM=0 TO={}".format(spice(stop)),
        ".end",
        "",
    ])
    return "\n".join(lines)


def scenario_name(vdd_v: float, code: int, index: int) -> str:
    """Return a stable raw-run directory name for one of exactly 16 cases."""

    return "{:03d}_tt25_v{:0.2f}_code{}".format(index, vdd_v, code).replace(".", "p")


def prepare_run(run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any], mux: Mapping[str, Any]) -> Path:
    """Preflight collateral and create one non-overwritable raw run root."""

    if run_dir.exists():
        raise ValueError("refusing to overwrite existing comparator run directory: {}".format(run_dir))
    hspice = run_dc_sweep.require_regular_file(Path(config["hspice"]), "HSPICE", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if str(config["expected_hspice_version"]) not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    for path in list(cells["source_files"].values()) + [config["model_library"]]:
        run_dc_sweep.require_regular_file(Path(path), "FTC source collateral")
    run_dc_sweep.require_regular_file(Path(mux["source_cdl"]), "verified LVT MUX CDL")
    run_dc_sweep.require_regular_file(Path(mux["source_verilog"]), "verified LVT MUX Verilog")
    compatibility = FTC_ROOT / "spice" / "empty_subckt.sp_cal"
    run_dc_sweep.require_regular_file(compatibility, "FTC LVT compatibility include")
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({
        "study": "ftc_minimal_programmable_threshold_pulse_comparator",
        "hspice": str(hspice), "hspice_version": version,
        "config": dict(config), "selected_cells": dict(cells), "mux": dict(mux),
        "vdd_points": list(VDD_POINTS), "codes": list(CODES), "scenario_count": len(VDD_POINTS) * len(CODES),
        "scope": "TT/25C frozen tap29 sensor plus fixed LVT threshold and one DFF comparator",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return hspice


def run_one(hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any], index: int, vdd_v: float, code: int) -> Dict[str, Any]:
    """Execute one isolated integrated scenario and retain its raw evidence.

    The raw directory contains the deck, HSPICE listing, measurement file and
    command record together.  No generated file is written outside ``run_dir``.
    Parsing retains failed measures as absent values; classification happens
    later so one electrical failure becomes an explicit NO-GO record.
    """

    scenario = run_dir / "scenarios" / scenario_name(vdd_v, code, index)
    scenario.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", scenario / "empty_subckt.sp_cal")
    deck_path = scenario / "minimal_pulse_comparator.sp"
    deck_path.write_text(render_integrated_deck(config, cells, vdd_v, code), encoding="ascii")
    result = subprocess.run(
        [str(hspice), deck_path.name, "-o", "minimal_pulse_comparator"], cwd=str(scenario),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=300,
    )
    (scenario / "hspice_command.log").write_text(
        "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            " ".join([str(hspice), deck_path.name, "-o", "minimal_pulse_comparator"]), result.returncode, result.stdout, result.stderr
        ), encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, scenario))
    warnings = run_dc_sweep.validate_listing(scenario / "minimal_pulse_comparator.lis")
    values = run_dc_sweep.parse_measurements(run_dc_sweep.find_measurement_file(scenario, "minimal_pulse_comparator"))
    return {
        "vdd_v": float(vdd_v), "code": int(code), "selected_tap": THRESHOLD_TAPS[code],
        "scenario": str(scenario.relative_to(run_dir)), "warnings": warnings,
        "t_xor_rise_s": values.get("t_xor_rise"), "t_xor_fall_s": values.get("t_xor_fall"),
        "t_ck_rise_s": values.get("t_ck_rise"), "q_final_v": values.get("q_final_v"),
        "vdd_a_min_v": values.get("vdd_a_min_v"),
    }


def row_from_record(record: Mapping[str, Any], widths: Mapping[float, float]) -> Dict[str, Any]:
    """Derive one auditable code-sweep row from raw HSPICE measurements."""

    row: Dict[str, Any] = {field: None for field in RESULT_FIELDS}
    vdd_v = round(float(record["vdd_v"]), 2)
    code = int(record["code"])
    row.update({"vdd_v": vdd_v, "code": code, "selected_tap": THRESHOLD_TAPS[code], "scenario": record["scenario"], "valid": 0})
    for field in ("t_xor_rise_s", "t_xor_fall_s", "t_ck_rise_s", "q_final_v"):
        row[field] = finite_number(record.get(field))
    row["w_s_frozen_ps"] = float(widths[vdd_v])
    required = ("t_xor_rise_s", "t_xor_fall_s", "t_ck_rise_s", "q_final_v")
    if any(row[field] is None for field in required):
        return row
    width_s = float(row["t_xor_fall_s"]) - float(row["t_xor_rise_s"])
    delay_s = float(row["t_ck_rise_s"]) - float(row["t_xor_rise_s"])
    if width_s <= 0.0 or delay_s <= 0.0 or float(row["t_ck_rise_s"]) > LATEST_ALLOWED_CK_S:
        return row
    row["w_s_int_ps"] = width_s * 1.0e12
    row["d_code_ps"] = delay_s * 1.0e12
    row["delta_w_load_ps"] = float(row["w_s_int_ps"]) - float(row["w_s_frozen_ps"])
    row["q_final"] = 1 if float(row["q_final_v"]) >= vdd_v / 2.0 else 0
    row["q_expected"] = 1 if width_s > delay_s else 0
    row["q_matches_expected"] = int(row["q_final"] == row["q_expected"])
    row["valid"] = 1
    return row


def evaluate_voltage(rows: Sequence[Mapping[str, Any]], vdd_v: float) -> Dict[str, Any]:
    """Apply only the required monotonicity, bracket, and DFF-compare gates."""

    ordered = sorted([row for row in rows if round(float(row["vdd_v"]), 2) == vdd_v], key=lambda row: int(row["code"]))
    if len(ordered) != len(CODES) or [int(row["code"]) for row in ordered] != list(CODES):
        return {"vdd_v": vdd_v, "complete": False, "monotonic": False, "bracketed": False, "transition_count": None, "q_match_outside_boundary": False, "boundary_code_pairs": [], "decision_reasons": ["missing code-sweep rows"]}
    if any(int(row.get("valid", 0)) != 1 for row in ordered):
        return {"vdd_v": vdd_v, "complete": False, "monotonic": False, "bracketed": False, "transition_count": None, "q_match_outside_boundary": False, "boundary_code_pairs": [], "decision_reasons": ["one or more HSPICE measurements are incomplete or nonphysical"]}
    delays = [float(row["d_code_ps"]) for row in ordered]
    width = float(ordered[0]["w_s_int_ps"])
    monotonic = all(later > earlier for earlier, later in zip(delays, delays[1:]))
    bracketed = min(delays) < width < max(delays)
    q_values = [int(row["q_final"]) for row in ordered]
    # The aperture exception is defined by measured time ordering, never by
    # observed Q.  Otherwise an erroneous Q transition could falsely declare
    # itself a boundary and hide an error in the final physical comparison.
    boundary_pairs = [
        [index, index + 1]
        for index, (earlier, later) in enumerate(zip(delays, delays[1:]))
        if earlier < width < later
    ]
    q_transitions = [index for index, (left, right) in enumerate(zip(q_values, q_values[1:])) if left != right]
    boundary_codes = {code for pair in boundary_pairs for code in pair}
    q_match_outside = all(int(row["q_matches_expected"]) == 1 for row in ordered if int(row["code"]) not in boundary_codes)
    reasons: List[str] = []
    if not monotonic:
        reasons.append("D(code) is not strictly increasing")
    if not bracketed:
        reasons.append("eight codes do not bracket W_S_int")
    if not q_transitions:
        reasons.append("DFF output has no code transition")
    if not q_match_outside:
        reasons.append("DFF disagrees with time comparison outside adjacent transition codes")
    return {
        "vdd_v": vdd_v, "complete": True, "monotonic": monotonic, "bracketed": bracketed,
        "transition_count": len(q_transitions), "boundary_code_pairs": boundary_pairs,
        "q_match_outside_boundary": q_match_outside,
        "w_s_int_ps": width, "d_code_ps": delays, "q_final": q_values, "decision_reasons": reasons,
    }


def evaluate(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Combine two voltage-local gates into the task's single GO/NO-GO result."""

    per_voltage = [evaluate_voltage(rows, voltage) for voltage in VDD_POINTS]
    passed = all(
        item["complete"] and item["monotonic"] and item["bracketed"]
        and int(item["transition_count"] or 0) >= 1 and item["q_match_outside_boundary"]
        for item in per_voltage
    )
    reasons = ["all two-VDD monotonic threshold and DFF comparison gates passed"] if passed else []
    if not passed:
        for item in per_voltage:
            for reason in item["decision_reasons"]:
                reasons.append("{} V: {}".format(item["vdd_v"], reason))
    return {"decision": "GO" if passed else "NO-GO", "decision_reason": reasons, "per_voltage": per_voltage}


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Write the fixed compact evidence schema outside the ignored raw run."""

    if len(rows) != len(VDD_POINTS) * len(CODES):
        raise ValueError("refusing to publish an incomplete 16-row code sweep")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in RESULT_FIELDS})


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write deterministic, compact JSON evidence with stable key ordering."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def architecture(cells: Mapping[str, Any], mux: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the complete fixed hardware description required for audit."""

    return {
        "schema_version": 1,
        "study": "ftc_minimal_programmable_threshold_pulse_comparator",
        "sensor": {"tap_index": TAP_INDEX, "initial_rvt_stages": SENSOR_RVT_INITIAL_STAGES, "initial_lvt_stages": SENSOR_LVT_INITIAL_STAGES, "observable_stages": OBSERVABLE_STAGES, "xor_cell": cells["xor2"]["cell"]},
        "threshold": {"buffer_cell": cells["delay_lvt"]["cell"], "buffer_count": THRESHOLD_BUFFER_COUNT, "tap_list": list(THRESHOLD_TAPS), "code_to_tap": {str(code): THRESHOLD_TAPS[code] for code in CODES}, "mux_cell": mux["cell"], "mux_count": 7, "mux_levels": ["C[0]", "C[1]", "C[2]"], "mux_select_truth": mux["select_truth"]},
        "dff": {"cell": cells["dff"]["cell"], "clock_pin": "CK", "data_pin": "D", "reset_pin": "R", "reset_behavior": "active_high_async_clear released at 0.51 ns", "q_read_time_s": Q_READ_TIME_S, "minimum_q_settle_s": Q_SETTLE_S},
        "same_rail_mapping": {"VDD": "VDD_A", "VNW": "VDD_A", "VPW": "VSS_A", "VSS": "VSS_A"},
    }


def plot_threshold(rows: Sequence[Mapping[str, Any]], output: Path) -> None:
    """Draw the sole requested two-workpoint threshold-versus-pulse figure."""

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "svg.fonttype": "none"})
    figure, axes = plt.subplots(1, 2, figsize=(8.6, 3.6), sharey=False)
    for axis, voltage in zip(axes, VDD_POINTS):
        selected = sorted([row for row in rows if round(float(row["vdd_v"]), 2) == voltage], key=lambda row: int(row["code"]))
        codes = [int(row["code"]) for row in selected]
        delays = [float(row["d_code_ps"]) if row.get("d_code_ps") is not None else math.nan for row in selected]
        width = float(selected[0]["w_s_int_ps"]) if selected and selected[0].get("w_s_int_ps") is not None else math.nan
        q_values = [int(row["q_final"]) if row.get("q_final") is not None else math.nan for row in selected]
        axis.plot(codes, delays, marker="o", color="#1f4e79", label="D(code)")
        axis.axhline(width, color="#b54a2d", linewidth=1.4, label="W_S_int")
        axis.set_title("VDD = {:.2f} V".format(voltage))
        axis.set_xlabel("code")
        axis.set_ylabel("time (ps)")
        axis.set_xticks(list(CODES))
        axis.grid(True, axis="y", alpha=0.25)
        q_axis = axis.twinx()
        q_axis.step(codes, q_values, where="mid", color="#2f7d4a", marker="s", label="Q")
        q_axis.set_ylim(-0.15, 1.15)
        q_axis.set_yticks([0, 1])
        q_axis.set_ylabel("Q")
        handles, labels = axis.get_legend_handles_labels()
        q_handles, q_labels = q_axis.get_legend_handles_labels()
        axis.legend(handles + q_handles, labels + q_labels, loc="best")
    figure.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, format="svg")
    plt.close(figure)


def render_report(path: Path, result: Mapping[str, Any]) -> None:
    """Write only the three requested questions and the final physical gate."""

    decision = result["decision"]
    monotonic = all(item["monotonic"] for item in result["per_voltage"])
    compare = all(item["q_match_outside_boundary"] for item in result["per_voltage"])
    lines = [
        "# FTC Minimal Programmable Threshold Pulse Comparator", "",
        "## Decision", "", "**{}**".format(decision), "",
        "## Required Answers", "",
        "1. 真实标准单元可编程 delay 是否产生单调 `D(code)`？{}。".format("是" if monotonic else "否"),
        "2. 真实 DFF 是否实现 `W_S_int > D(code)` 的 1-bit 脉宽比较？{}。".format("是，除相邻翻转 code 外均与时间关系一致" if compare else "否，存在 boundary 外不一致"),
        "3. 这个硬件 primitive 是否足以进入下一阶段的 static self-calibration？{}。".format("是" if decision == "GO" else "否"),
        "", "## Per-VDD Evidence", "", "| VDD (V) | D 单调 | 脉宽 bracket | 时间边界对 | Boundary 外 Q 一致 |", "|---:|---:|---:|---|---:|",
    ]
    for item in result["per_voltage"]:
        pairs = ", ".join("{}->{}".format(pair[0], pair[1]) for pair in item["boundary_code_pairs"]) or "none"
        lines.append("| {:.2f} | {} | {} | {} | {} |".format(item["vdd_v"], int(item["monotonic"]), int(item["bracketed"]), pairs, int(item["q_match_outside_boundary"])))
    lines.extend(["", "## Gate Reason", ""])
    lines.extend(["- {}".format(reason) for reason in result["decision_reason"]])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Expose output locations only; all electrical conditions remain fixed."""

    parser = argparse.ArgumentParser(description="run the fixed FTC minimal programmable pulse comparator")
    parser.add_argument("--config", type=Path, default=FTC_ROOT / "ftc_config.json", help="frozen FTC configuration")
    parser.add_argument("--run-dir", type=Path, default=FTC_ROOT / "runs" / "minimal_pulse_comparator", help="ignored raw HSPICE run root")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis" / "minimal_pulse_comparator", help="compact evidence output")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports" / "FTC_MINIMAL_PROGRAMMABLE_THRESHOLD_PULSE_COMPARATOR.md", help="final report output")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run exactly sixteen integrated scenarios and publish the required evidence."""

    args = parse_args(argv)
    config = load_json(args.config.resolve())
    cells = load_json(FTC_ROOT / "discovery" / "selected_cells.json")
    mux = parse_manifest_mux(FTC_ROOT / "analysis" / "reference_sensitivity_contrast" / "candidate_manifest.csv", cells)
    verify_frozen_inputs(config, cells, mux)
    verify_mux_collateral(mux)
    verify_frozen_provenance()
    widths = frozen_widths(FTC_ROOT / "analysis" / "real_xor_pulse_width" / "fine.csv")
    run_dir = args.run_dir.resolve()
    analysis_dir = args.analysis_dir.resolve()
    report_output = args.report_output.resolve()
    hspice = prepare_run(run_dir, config, cells, mux)
    records: List[Dict[str, Any]] = []
    index = 0
    for voltage in VDD_POINTS:
        for code in CODES:
            records.append(run_one(hspice, run_dir, config, cells, index, voltage, code))
            index += 1
    rows = [row_from_record(record, widths) for record in records]
    result = evaluate(rows)
    write_json(analysis_dir / "architecture.json", architecture(cells, mux))
    write_csv(analysis_dir / "code_sweep.csv", rows)
    write_json(analysis_dir / "summary.json", {"schema_version": 1, "scenario_count": len(rows), "vdd_points": list(VDD_POINTS), "codes": list(CODES), **result})
    plot_threshold(rows, analysis_dir / "threshold_vs_pulse.svg")
    render_report(report_output, result)
    print("FTC_MINIMAL_PULSE_COMPARATOR decision={}".format(result["decision"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
