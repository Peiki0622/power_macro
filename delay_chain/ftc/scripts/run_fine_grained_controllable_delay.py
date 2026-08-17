#!/usr/bin/env python3
"""Run the bounded FTC fine-grained controllable-delay experiment.

The historical 3-bit tap-tree experiments are immutable inputs.  This runner
never imports their loops and never writes under their analysis or raw-run
directories.  It first derives a physical delay requirement from real-DFF
evidence, then advances through the unit-cell, short-chain, sizing, full-chain,
calibration, and acceptance gates in order.  A valid structural NO-GO is an
ordinary published result: downstream electrical work is marked ``NOT_RUN``.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
PHASE1_SCRIPTS = FTC_ROOT.parent / "phase1" / "scripts"
if str(PHASE1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PHASE1_SCRIPTS))
import run_dc_sweep  # noqa: E402  # Reuse only reviewed HSPICE integrity helpers.


# These constants are the experiment contract.  They are deliberately not
# command-line knobs because changing them would create a different study.
FORMAL_VDD = (0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10)
ANCHOR_VDD = (1.10, 0.95, 0.80)
FEASIBILITY_BASELINES = (0.85, 0.95, 1.10)
VDD_MIN = 0.80
VDD_MAX = 1.10
TAP_INDEX = 29
INITIAL_RVT_STAGES = 4
INITIAL_LVT_STAGES = 0
OBSERVABLE_STAGES = 30
LVT_BUFFER = "BUF_X0P7M_A9TL40"
MUX_CELL = "MXT2_X0P5M_A9TL40"
XOR_CELL = "XOR2_X0P5M_A9TR40"
DFF_CELL = "DFFRPQ_X0P5M_A9TR40"
Q_SETTLE_S = 2.0e-10
# The historical r2 comparator readout eliminates the previously documented
# r2/r1 readout discrepancy while retaining more than the required Q settling.
Q_READ_TIME_S = 3.376961280e-9
COARSE_STEP_V = 0.05
REFINEMENT_STEP_V = 0.01
UNIT_FINE_LIMIT_MULTIPLIER = 3.0
SHORT_CHAIN_MAX_STEP_RATIO = 2.0

UNIT_FIELDS = (
    "vdd_v", "t_fast_rise_ps", "t_slow_rise_ps", "Delta_unit_rise_ps",
    "slow_fast_ratio", "fast_rise_time_ps", "fast_fall_time_ps",
    "slow_rise_time_ps", "slow_fall_time_ps", "fast_output_logic_high",
    "fast_output_logic_low", "slow_output_logic_high", "slow_output_logic_low",
    "fast_valid", "slow_valid", "valid",
)
SHORT_FIELDS = (
    "vdd_v", "code", "D_code_ps", "Delta_D_ps", "output_rise_time_ps",
    "output_fall_time_ps", "output_logic_high", "output_logic_low", "logic_valid",
    "scenario", "valid",
)
FULL_FIELDS = SHORT_FIELDS
CALIBRATION_FIELDS = (
    "vdd_v", "predicted_k", "code", "t_xor_rise_s", "t_xor_fall_s",
    "W_S_int_ps", "t_ck_rise_s", "D_code_ps", "q_final_v", "Q",
    "readout_time_s", "scenario", "valid",
)
ACCEPTANCE_FIELDS = (
    "baseline_vdd_v", "attack_vdd_v", "margin_code", "lock_code",
    "alarm_code", "scan_phase", "scenario", "W_S_int_ps", "D_alarm_ps",
    "Q", "alarm", "valid",
)


def finite_number(value: Any) -> Optional[float]:
    """Return a finite scalar or ``None`` for failed HSPICE measurements."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def voltage_key(value: float) -> float:
    """Normalize the fixed 10 mV and 50 mV grids without broad rounding."""

    return round(float(value), 2)


def spice(value: float) -> str:
    """Render a scalar as a locale-independent HSPICE decimal literal."""

    return "{:.12e}".format(float(value))


def sha256_file(path: Path) -> str:
    """Hash a read-only input in chunks so large collateral remains safe."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    """Load one object-shaped JSON file and reject other top-level shapes."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def load_csv(path: Path, fields: Sequence[str]) -> List[Dict[str, str]]:
    """Load a nonempty CSV only after checking the consumed schema."""

    if not path.is_file():
        raise ValueError("required CSV is unavailable: {}".format(path))
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not set(fields).issubset(reader.fieldnames):
            raise ValueError("required CSV schema is incomplete: {}".format(path))
        rows = list(reader)
    if not rows:
        raise ValueError("required CSV is empty: {}".format(path))
    return rows


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write deterministic public evidence with a stable key order."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    """Write one rectangular evidence table while preserving failed values."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def require_equal(actual: Any, expected: Any, description: str) -> None:
    """Reject a frozen contract mismatch without silently coercing values."""

    if isinstance(expected, float):
        if finite_number(actual) != expected:
            raise ValueError("{} must remain {}".format(description, expected))
    elif actual != expected:
        raise ValueError("{} must remain {!r}".format(description, expected))


def validate_config(config: Mapping[str, Any]) -> None:
    """Confirm that the new evidence is comparable with frozen FTC evidence."""

    for field, expected in (
        ("technology", "SMIC40LL"), ("corner", "tt"), ("temperature_c", 25.0),
        ("observable_stages", OBSERVABLE_STAGES), ("launch_time_s", 1.0e-9),
        ("sampling_period_s", 6.0e-9), ("tran_max_step_s", 1.0e-12),
    ):
        require_equal(config.get(field), expected, "FTC config {}".format(field))
    selected = config.get("selected_operating_point")
    if not isinstance(selected, dict):
        raise ValueError("FTC selected operating point is missing")
    require_equal(selected.get("initial_rvt_stages"), INITIAL_RVT_STAGES, "initial RVT stages")
    require_equal(selected.get("initial_lvt_stages"), INITIAL_LVT_STAGES, "initial LVT stages")


def validate_cells(cells: Mapping[str, Any]) -> None:
    """Check the positional standard-cell contracts used by every new deck."""

    expected_cells = {
        "delay_lvt": LVT_BUFFER, "delay_rvt": "BUF_X0P7M_A9TR40",
        "xor2": XOR_CELL, "dff": DFF_CELL,
    }
    for role, cell in expected_cells.items():
        if cells.get(role, {}).get("cell") != cell:
            raise ValueError("selected {} cell must remain {}".format(role, cell))
    if tuple(cells["delay_lvt"].get("cdl_ports", ())) != ("Y", "VDD", "VNW", "VPW", "VSS", "A"):
        raise ValueError("LVT buffer CDL port order changed")
    if tuple(cells["dff"].get("cdl_ports", ())) != ("Q", "VDD", "VNW", "VPW", "VSS", "CK", "D", "R"):
        raise ValueError("DFF CDL port order changed")


def frozen_paths() -> Dict[str, Path]:
    """Return exactly the historical inputs frozen by the fine-grained plan."""

    return {
        "delay_refinement_summary": FTC_ROOT / "analysis/delay_code_refinement/summary.json",
        "delay_refinement_calibration": FTC_ROOT / "analysis/delay_code_refinement/calibration_gate.csv",
        "delay_refinement_tap_screen": FTC_ROOT / "analysis/delay_code_refinement/tap_screen.csv",
        "delay_refinement_report": FTC_ROOT / "reports/FTC_DELAY_CODE_BOUNDARY_REFINEMENT.md",
        "acceptance_summary": FTC_ROOT / "analysis/programmable_acceptance_window/summary.json",
        "acceptance_attack_sweep": FTC_ROOT / "analysis/programmable_acceptance_window/attack_sweep.csv",
        "acceptance_report": FTC_ROOT / "reports/FTC_PROGRAMMABLE_ACCEPTANCE_WINDOW_ROOT_CAUSE.md",
        "static_calibration_trace": FTC_ROOT / "analysis/static_self_calibration/calibration_trace.csv",
        "static_calibration_mapping": FTC_ROOT / "analysis/static_self_calibration/range_mapping.json",
        "comparator_architecture": FTC_ROOT / "analysis/minimal_pulse_comparator/architecture.json",
        "selected_cells": FTC_ROOT / "discovery/selected_cells.json",
    }


def verify_frozen_evidence() -> Dict[str, Any]:
    """Read the immutable NO-GO evidence without running historical scripts."""

    paths = frozen_paths()
    for path in paths.values():
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("frozen evidence is missing or empty: {}".format(path))
    refinement = load_json(paths["delay_refinement_summary"])
    if refinement.get("decision") != "3-bit Boundary-Centered Mapping = NO-GO":
        raise ValueError("delay-code refinement is not the frozen NO-GO result")
    report = paths["delay_refinement_report"].read_text(encoding="utf-8")
    if "3-bit Boundary-Centered Mapping = NO-GO" not in report:
        raise ValueError("delay-code refinement report is incompatible")
    acceptance = load_json(paths["acceptance_summary"])
    if acceptance.get("decision") != "Programmable Acceptance Window = NO-GO":
        raise ValueError("acceptance-window result is not the frozen NO-GO")
    attack = load_csv(paths["acceptance_attack_sweep"], ("baseline_vdd_v", "attack_vdd_v", "Q", "valid"))
    if len(attack) != 42 or any(row["Q"] != "0" or row["valid"].lower() != "true" for row in attack):
        raise ValueError("frozen acceptance attack sweep is not the completed 42-row NO-GO evidence")
    acceptance_report = paths["acceptance_report"].read_text(encoding="utf-8")
    if "Programmable Acceptance Window = NO-GO" not in acceptance_report:
        raise ValueError("acceptance root-cause report is incompatible")
    mapping = load_json(paths["static_calibration_mapping"])
    if mapping.get("tap_list") != [10, 12, 14, 16, 18, 36, 37, 38]:
        raise ValueError("historical calibration mapping is not the frozen root-cause mapping")
    trace = load_csv(paths["static_calibration_trace"], ("vdd_v", "code", "D_code_ps", "W_S_int_ps", "Q"))
    architecture = load_json(paths["comparator_architecture"])
    if architecture.get("sensor", {}).get("tap_index") != TAP_INDEX:
        raise ValueError("frozen sensor tap is not tap29")
    if architecture.get("dff", {}).get("cell") != DFF_CELL:
        raise ValueError("frozen comparator DFF changed")
    cells = load_json(paths["selected_cells"])
    validate_cells(cells)
    return {
        "paths": paths, "calibration": load_csv(
            paths["delay_refinement_calibration"], ("vdd_v", "D_code_ps", "Q", "valid")
        ), "tap_screen": load_csv(
            paths["delay_refinement_tap_screen"], ("vdd_v", "tap", "D_raw_ps", "valid")
        ), "trace": trace, "architecture": architecture, "cells": cells,
    }


def build_requirements(frozen: Mapping[str, Any]) -> Dict[str, Any]:
    """Derive the physical delay corridor exclusively from real-DFF rows.

    Candidate mappings differ, but all valid rows measure the same physical
    DFF boundary.  Pooling their true Q observations by voltage creates the
    narrowest observed [last-Q=1, first-Q=0] bracket without using D_est.
    """

    brackets: Dict[float, Dict[str, Any]] = {}
    for row in frozen["calibration"]:
        if row["valid"] != "1" or row["Q"] not in ("0", "1"):
            continue
        delay = finite_number(row["D_code_ps"])
        if delay is None:
            continue
        vdd = voltage_key(float(row["vdd_v"]))
        bracket = brackets.setdefault(vdd, {"q1": [], "q0": []})
        bracket["q1" if row["Q"] == "1" else "q0"].append(delay)
    output_brackets: Dict[str, Dict[str, float]] = {}
    for vdd in FORMAL_VDD:
        local = brackets.get(vdd, {})
        if not local.get("q1") or not local.get("q0"):
            raise ValueError("real-DFF evidence lacks a complete Q boundary at {:.2f} V".format(vdd))
        last_q1 = max(local["q1"])
        first_q0 = min(local["q0"])
        if not last_q1 < first_q0:
            raise ValueError("real-DFF boundary is not ordered at {:.2f} V".format(vdd))
        output_brackets["{:.2f}".format(vdd)] = {
            "D_last_Q1_ps": last_q1, "D_first_Q0_ps": first_q0,
        }

    reference_steps: Dict[str, Dict[str, float]] = {}
    per_vdd_taps: Dict[float, Dict[int, float]] = {}
    for row in frozen["tap_screen"]:
        if row["valid"] != "1":
            continue
        per_vdd_taps.setdefault(voltage_key(float(row["vdd_v"])), {})[int(row["tap"])] = float(row["D_raw_ps"])
    for vdd in ANCHOR_VDD:
        taps = per_vdd_taps.get(vdd, {})
        steps = [taps[tap + 1] - taps[tap] for tap in sorted(taps) if tap + 1 in taps]
        if not steps or any(step <= 0.0 for step in steps):
            raise ValueError("tap-screen steps are incomplete at {:.2f} V".format(vdd))
        reference_steps["{:.2f}".format(vdd)] = {
            "min_ps": min(steps), "median_ps": float(median(steps)), "max_ps": max(steps),
        }

    high = output_brackets["1.10"]
    low = output_brackets["0.80"]
    ratio_lower = low["D_last_Q1_ps"] / high["D_first_Q0_ps"]
    return {
        "schema_version": 1,
        "formal_vdd_range_v": [VDD_MIN, VDD_MAX],
        "real_boundary_brackets_by_vdd": output_brackets,
        "high_vdd_boundary_bracket": high,
        "low_vdd_boundary_bracket": low,
        # The conservative span covers every observed endpoint, while the
        # ratio lower bound is sufficient to reject a unit that cannot span
        # even the most favorable high/low boundary combination.
        "required_delay_span_ps": low["D_first_Q0_ps"] - high["D_last_Q1_ps"],
        "required_delay_ratio_lower_bound": ratio_lower,
        "reference_adjacent_lvt_step_ps_by_vdd": reference_steps,
        "source_file_sha256": {
            name: sha256_file(path) for name, path in frozen["paths"].items()
        },
    }


def validate_requirements(requirements: Mapping[str, Any], frozen: Mapping[str, Any]) -> None:
    """Ensure Phase 1 consumes exactly the Phase 0 evidence it records."""

    if requirements.get("formal_vdd_range_v") != [VDD_MIN, VDD_MAX]:
        raise ValueError("requirements formal voltage range changed")
    if finite_number(requirements.get("required_delay_ratio_lower_bound")) is None:
        raise ValueError("requirements delay-ratio lower bound is missing")
    expected_hashes = {name: sha256_file(path) for name, path in frozen["paths"].items()}
    if requirements.get("source_file_sha256") != expected_hashes:
        raise ValueError("frozen source evidence changed after Phase 0")


def buffer_instance(name: str, output_node: str, input_node: str, cell: str = LVT_BUFFER) -> str:
    """Render a powered BUF using the vendor CDL order ``Y VDD VNW VPW VSS A``."""

    return "{} {} vdd_a vdd_a vss_a vss_a {} {}".format(name, output_node, input_node, cell)


def mux_instance(name: str, output_node: str, fast_node: str, slow_node: str, select_node: str) -> str:
    """Render the non-inverting MUX with FAST on A and SLOW on B.

    The frozen vendor truth table selects A for S0=0 and B for S0=1.  Keeping
    the connection in one helper makes the thermometer-code polarity auditable.
    """

    return "{} {} vdd_a vdd_a vss_a vss_a {} {} {} {}".format(
        name, output_node, fast_node, slow_node, select_node, MUX_CELL
    )


def include_lines(cells: Mapping[str, Any], include_rvt: bool) -> List[str]:
    """Include only the standard-cell collateral required by the deck type."""

    includes = ['.include "{}"'.format(cells["source_files"]["lvt_cdl"])]
    if include_rvt:
        includes.insert(0, '.include "{}"'.format(cells["source_files"]["rvt_cdl"]))
    return includes


def transient_header(config: Mapping[str, Any], cells: Mapping[str, Any], vdd_v: float, title: str, include_rvt: bool) -> List[str]:
    """Create the same-rail transient setup shared by all deck families."""

    if not VDD_MIN <= vdd_v <= VDD_MAX:
        raise ValueError("VDD is outside the formal 0.80--1.10 V range")
    launch = float(config["launch_time_s"])
    period = float(config["sampling_period_s"])
    stop = launch + period - float(config["tran_max_step_s"])
    return [
        "* {}".format(title),
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(float(config["temperature_c"]))),
        *include_lines(cells, include_rvt),
        '.lib "{}" {}'.format(config["model_library"], config["corner"]),
        ".param VDD_VALUE={}".format(spice(vdd_v)),
        "V_VDD vdd_a vss_a 'VDD_VALUE'",
        "V_VSS vss_a 0 0",
        "V_IN in vss_a PULSE(0 'VDD_VALUE' {} 1.000000000000e-12 1.000000000000e-12 {} {})".format(
            spice(launch), spice(period / 2.0), spice(period)
        ),
    ]


def measurement_lines(config: Mapping[str, Any], input_node: str, output_node: str) -> List[str]:
    """Measure delay, slew, stable levels, and extra crossings for one path.

    A second 50% crossing is expected to fail in HSPICE for a clean one-pulse
    waveform.  ``parse_measurements`` exposes that failed measure as ``None``;
    a finite value is therefore direct glitch evidence rather than ignored data.
    """

    launch = float(config["launch_time_s"])
    period = float(config["sampling_period_s"])
    stop = launch + period - float(config["tran_max_step_s"])
    return [
        ".tran {} {}".format(spice(float(config["tran_max_step_s"])), spice(stop)),
        ".measure tran t_in_rise WHEN v({},vss_a)='VDD_VALUE/2' RISE=1".format(input_node),
        ".measure tran t_out_rise WHEN v({},vss_a)='VDD_VALUE/2' RISE=1".format(output_node),
        ".measure tran t_out_fall WHEN v({},vss_a)='VDD_VALUE/2' FALL=1".format(output_node),
        ".measure tran t_out_rise_2 WHEN v({},vss_a)='VDD_VALUE/2' RISE=2".format(output_node),
        ".measure tran t_out_fall_2 WHEN v({},vss_a)='VDD_VALUE/2' FALL=2".format(output_node),
        ".measure tran t_out_rise_10 WHEN v({},vss_a)='VDD_VALUE/10' RISE=1".format(output_node),
        ".measure tran t_out_rise_90 WHEN v({},vss_a)='9*VDD_VALUE/10' RISE=1".format(output_node),
        ".measure tran t_out_fall_90 WHEN v({},vss_a)='9*VDD_VALUE/10' FALL=1".format(output_node),
        ".measure tran t_out_fall_10 WHEN v({},vss_a)='VDD_VALUE/10' FALL=1".format(output_node),
        ".measure tran out_logic_high FIND v({},vss_a) AT={}".format(output_node, spice(launch + period / 4.0)),
        ".measure tran out_logic_low FIND v({},vss_a) AT={}".format(output_node, spice(launch + 3.0 * period / 4.0)),
        ".measure tran vdd_a_min_v MIN v(vdd_a,vss_a) FROM=0 TO {}".format(spice(stop)),
    ]


def thermometer_bits(units: int, code: int) -> Tuple[int, ...]:
    """Return the continuous-enable vector where code+1 flips one FAST unit."""

    if units < 1 or not 0 <= code <= units:
        raise ValueError("thermometer code is outside the chain range")
    return tuple(1 if index < code else 0 for index in range(units))


def controllable_units(input_node: str, output_node: str, units: int, code: int) -> List[str]:
    """Render a cascaded chain with a physical buffer in every SLOW branch.

    Every unit retains both branches at every code.  This avoids treating a
    software-selected netlist topology as a physical timing improvement.
    """

    bits = thermometer_bits(units, code)
    lines = ["* Continuous thermometer code; each selected unit is SLOW."]
    current = input_node
    for index, bit in enumerate(bits):
        slow = "u{}_slow".format(index)
        next_node = output_node if index == units - 1 else "u{}_out".format(index)
        lines.append("V_EN_{} en_{} vss_a {}".format(index, index, "'VDD_VALUE'" if bit else "0"))
        lines.append(buffer_instance("XU{}_BUF".format(index), slow, current))
        lines.append(mux_instance("XU{}_MUX".format(index), next_node, current, slow, "en_{}".format(index)))
        current = next_node
    return lines


def render_unit_deck(config: Mapping[str, Any], cells: Mapping[str, Any], vdd_v: float, state: str) -> str:
    """Render the six-scenario candidate-A unit cell with no hidden receiver."""

    if state not in ("FAST", "SLOW"):
        raise ValueError("unit state must be FAST or SLOW")
    lines = transient_header(config, cells, vdd_v, "FTC fine-grained candidate-A unit cell", include_rvt=False)
    lines.extend([
        "* FAST is direct A input; SLOW passes one LVT BUF into B.",
        "V_EN en vss_a {}".format("'VDD_VALUE'" if state == "SLOW" else "0"),
        buffer_instance("XUNIT_BUF", "slow", "in"),
        mux_instance("XUNIT_MUX", "out", "in", "slow", "en"),
        *measurement_lines(config, "in", "out"),
        ".end", "",
    ])
    return "\n".join(lines)


def render_chain_deck(
    config: Mapping[str, Any], cells: Mapping[str, Any], vdd_v: float, units: int,
    code: int, dff_load: bool,
) -> str:
    """Render an isolated chain; Phase 4 optionally restores only CK loading."""

    lines = transient_header(config, cells, vdd_v, "FTC fine-grained controllable delay chain", include_rvt=dff_load)
    lines.extend(controllable_units("in", "out", units, code))
    if dff_load:
        # Holding reset high prevents Q activity while retaining the real CK pin
        # capacitance and transistor loading used by the final comparator.
        lines.extend([
            "V_DFF_RESET dff_reset vss_a 'VDD_VALUE'",
            "XDFF q_dummy vdd_a vdd_a vss_a vss_a out vss_a dff_reset {}".format(cells["dff"]["cell"]),
        ])
    lines.extend([*measurement_lines(config, "in", "out"), ".end", ""])
    return "\n".join(lines)


def render_system_deck(
    config: Mapping[str, Any], cells: Mapping[str, Any], vdd_v: float, units: int, code: int,
) -> str:
    """Render the frozen tap29/XOR/DFF path with only its threshold chain changed."""

    if not 0 <= code <= units:
        raise ValueError("system code is outside the selected chain range")
    launch = float(config["launch_time_s"])
    period = float(config["sampling_period_s"])
    stop = launch + period - float(config["tran_max_step_s"])
    lines = [
        "* FTC complete fine-grained comparator: frozen tap29 sensor and real DFF.",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(float(config["temperature_c"]))),
        *include_lines(cells, include_rvt=True),
        '.lib "{}" {}'.format(config["model_library"], config["corner"]),
        ".param VDD_VALUE={}".format(spice(vdd_v)),
        "V_VDD vdd_a vss_a 'VDD_VALUE'", "V_VSS vss_a 0 0",
        "V_SCLK s_clk vss_a PULSE(0 'VDD_VALUE' {} 1.000000000000e-12 1.000000000000e-12 {} {})".format(
            spice(launch), spice(period / 2.0), spice(period)
        ),
        "* Active-high asynchronous clear settles before the isolated launch edge.",
        "V_DFF_RESET dff_reset vss_a PWL(0 'VDD_VALUE' {} 'VDD_VALUE' {} 0 {} 0)".format(
            spice(launch - Q_SETTLE_S), spice(launch - Q_SETTLE_S + 1.0e-11), spice(stop)
        ),
        "* Frozen 4-RVT/0-LVT initial paths and the complete 30-cell XOR bank.",
    ]
    rvt_input = "s_clk"
    for stage in range(INITIAL_RVT_STAGES):
        node = "rvt_initial_{}".format(stage)
        lines.append(buffer_instance("XRVT_INIT_{:02d}".format(stage), node, rvt_input, cells["delay_rvt"]["cell"]))
        rvt_input = node
    lvt_input = "s_clk"
    rvt_taps: List[str] = []
    lvt_taps: List[str] = []
    for stage in range(OBSERVABLE_STAGES):
        rvt = "rvt_{}".format(stage)
        lvt = "lvt_{}".format(stage)
        lines.append(buffer_instance("XRVT_{:02d}".format(stage), rvt, rvt_input, cells["delay_rvt"]["cell"]))
        lines.append(buffer_instance("XLVT_{:02d}".format(stage), lvt, lvt_input, cells["delay_lvt"]["cell"]))
        rvt_input, lvt_input = rvt, lvt
        rvt_taps.append(rvt)
        lvt_taps.append(lvt)
    for stage, (rvt, lvt) in enumerate(zip(rvt_taps, lvt_taps)):
        lines.append("XXOR_{:02d} xor_{} vdd_a vdd_a vss_a vss_a {} {} {}".format(
            stage, stage, rvt, lvt, cells["xor2"]["cell"]
        ))
    lines.extend(controllable_units("xor_29", "dff_ck", units, code))
    lines.extend([
        "* DFF ports: Q VDD VNW VPW VSS CK D R; CK is the new delay chain.",
        "XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(cells["dff"]["cell"]),
        ".tran {} {}".format(spice(float(config["tran_max_step_s"])), spice(stop)),
        ".measure tran t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1",
        ".measure tran t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1",
        ".measure tran t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1",
        ".measure tran q_final_v FIND v(q_final,vss_a) AT={}".format(spice(Q_READ_TIME_S)),
        ".measure tran vdd_a_min_v MIN v(vdd_a,vss_a) FROM=0 TO {}".format(spice(stop)),
        ".end", "",
    ])
    return "\n".join(lines)


def execute_deck(hspice: Path, run_dir: Path, label: str, prefix: str, deck: str) -> Dict[str, Any]:
    """Run exactly one retained HSPICE scenario and parse its validated MEAS file."""

    scenario = run_dir / "scenarios" / label
    scenario.mkdir(parents=True, exist_ok=False)
    # The installed LVT CDL resolves this historical no-op include relative to
    # the scenario directory; copying it preserves PDK sources as read-only.
    shutil.copyfile(FTC_ROOT / "spice/empty_subckt.sp_cal", scenario / "empty_subckt.sp_cal")
    deck_path = scenario / (prefix + ".sp")
    deck_path.write_text(deck, encoding="ascii")
    command = [str(hspice), deck_path.name, "-o", prefix]
    result = subprocess.run(
        command, cwd=str(scenario), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True, check=False, timeout=300,
    )
    (scenario / "hspice_command.log").write_text(
        "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            " ".join(command), result.returncode, result.stdout, result.stderr
        ), encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, scenario))
    warnings = run_dc_sweep.validate_listing(scenario / (prefix + ".lis"))
    values = run_dc_sweep.parse_measurements(run_dc_sweep.find_measurement_file(scenario, prefix))
    return {"scenario": str(scenario.relative_to(run_dir)), "warnings": warnings, **values}


def classify_path(record: Mapping[str, Any], vdd_v: float) -> Dict[str, Any]:
    """Classify a path waveform without converting failed measures into zeros."""

    values = {name: finite_number(record.get(name)) for name in (
        "t_in_rise", "t_out_rise", "t_out_fall", "t_out_rise_10", "t_out_rise_90",
        "t_out_fall_90", "t_out_fall_10", "out_logic_high", "out_logic_low",
    )}
    result: Dict[str, Any] = {
        "valid": False, "delay_ps": None, "rise_time_ps": None, "fall_time_ps": None,
        "logic_high": None, "logic_low": None, "glitch_free": False,
    }
    if any(value is None for value in values.values()):
        return result
    delay = values["t_out_rise"] - values["t_in_rise"]
    rise = values["t_out_rise_90"] - values["t_out_rise_10"]
    fall = values["t_out_fall_10"] - values["t_out_fall_90"]
    high_ok = values["out_logic_high"] >= 0.9 * vdd_v
    low_ok = values["out_logic_low"] <= 0.1 * vdd_v
    # A missing RISE=2/FALL=2 measure is the expected clean waveform.  A
    # finite second crossing is a glitch; an explicit failed measure remains
    # distinct from missing required first crossings handled above.
    no_extra_crossing = finite_number(record.get("t_out_rise_2")) is None and finite_number(record.get("t_out_fall_2")) is None
    if delay <= 0.0 or rise <= 0.0 or fall <= 0.0:
        return result
    result.update({
        "valid": high_ok and low_ok and no_extra_crossing,
        "delay_ps": delay * 1.0e12, "rise_time_ps": rise * 1.0e12,
        "fall_time_ps": fall * 1.0e12, "logic_high": values["out_logic_high"],
        "logic_low": values["out_logic_low"], "glitch_free": no_extra_crossing,
    })
    return result


def classify_comparator(record: Mapping[str, Any], vdd_v: float) -> Dict[str, Any]:
    """Derive the real-DFF delay and Q bit while enforcing Q-settle timing."""

    values = {name: finite_number(record.get(name)) for name in (
        "t_xor_rise", "t_xor_fall", "t_ck_rise", "q_final_v",
    )}
    result: Dict[str, Any] = {"valid": False, "Q": None, "W_S_int_ps": None, "D_code_ps": None}
    if any(value is None for value in values.values()):
        return result
    width = values["t_xor_fall"] - values["t_xor_rise"]
    delay = values["t_ck_rise"] - values["t_xor_rise"]
    if width <= 0.0 or delay <= 0.0 or values["t_ck_rise"] > Q_READ_TIME_S - Q_SETTLE_S:
        return result
    result.update({
        "valid": True, "Q": 1 if values["q_final_v"] >= vdd_v / 2.0 else 0,
        "W_S_int_ps": width * 1.0e12, "D_code_ps": delay * 1.0e12,
    })
    return result


def prepare_run(run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any], requirements: Mapping[str, Any]) -> Path:
    """Preflight tool/collateral before creating the sole task-owned raw root."""

    if run_dir.exists():
        raise ValueError("refusing to overwrite existing fine-grained run: {}".format(run_dir))
    hspice = run_dc_sweep.require_regular_file(Path(config["hspice"]), "HSPICE", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if str(config["expected_hspice_version"]) not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    collateral = list(cells["source_files"].values()) + [config["model_library"], FTC_ROOT / "spice/empty_subckt.sp_cal"]
    checked = [run_dc_sweep.require_regular_file(Path(path), "FTC collateral") for path in collateral]
    run_dir.mkdir(parents=True)
    write_json(run_dir / "manifest.json", {
        "schema_version": 1, "study": "ftc_fine_grained_controllable_delay",
        "scope": "TT/25C only; staged fine-grained unit and chain validation",
        "hspice": str(hspice), "hspice_version": version,
        "requirements_sha256": sha256_file(FTC_ROOT / "analysis/fine_grained_controllable_delay/requirements.json"),
        "requirements": dict(requirements),
        "collateral": [{"path": str(path), "sha256": sha256_file(path)} for path in checked],
    })
    return hspice


def run_unit_phase(hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any], requirements: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run precisely six candidate-A unit-cell scenarios and apply its Gate."""

    by_vdd: Dict[float, Dict[str, Dict[str, Any]]] = {}
    for vdd_v in ANCHOR_VDD:
        for state in ("FAST", "SLOW"):
            record = execute_deck(
                hspice, run_dir, "unit_a_v{:03d}_{}".format(int(round(vdd_v * 1000.0)), state.lower()),
                "unit_cell", render_unit_deck(config, cells, vdd_v, state),
            )
            by_vdd.setdefault(vdd_v, {})[state] = {**record, **classify_path(record, vdd_v)}
    rows: List[Dict[str, Any]] = []
    reasons: List[str] = []
    ratio_required = float(requirements["required_delay_ratio_lower_bound"])
    reference = requirements["reference_adjacent_lvt_step_ps_by_vdd"]
    for vdd_v in ANCHOR_VDD:
        fast = by_vdd[vdd_v]["FAST"]
        slow = by_vdd[vdd_v]["SLOW"]
        delay_fast, delay_slow = fast["delay_ps"], slow["delay_ps"]
        delta = None if delay_fast is None or delay_slow is None else delay_slow - delay_fast
        ratio = None if delay_fast is None or delay_fast <= 0.0 or delay_slow is None else delay_slow / delay_fast
        valid = bool(fast["valid"] and slow["valid"] and delta is not None and delta > 0.0 and ratio is not None)
        local_reasons: List[str] = []
        if not valid:
            local_reasons.append("FAST/SLOW path is invalid or Delta_unit is non-positive")
        if delta is not None and delta > UNIT_FINE_LIMIT_MULTIPLIER * float(reference["{:.2f}".format(vdd_v)]["median_ps"]):
            valid = False
            local_reasons.append("unit increment exceeds the fine-step limit")
        if ratio is None or ratio < ratio_required:
            valid = False
            local_reasons.append("unit SLOW/FAST ratio is below the required full-range lower bound")
        reasons.extend(["{:.2f} V: {}".format(vdd_v, reason) for reason in local_reasons])
        rows.append({
            "vdd_v": vdd_v, "t_fast_rise_ps": delay_fast, "t_slow_rise_ps": delay_slow,
            "Delta_unit_rise_ps": delta, "slow_fast_ratio": ratio,
            "fast_rise_time_ps": fast["rise_time_ps"], "fast_fall_time_ps": fast["fall_time_ps"],
            "slow_rise_time_ps": slow["rise_time_ps"], "slow_fall_time_ps": slow["fall_time_ps"],
            "fast_output_logic_high": fast["logic_high"], "fast_output_logic_low": fast["logic_low"],
            "slow_output_logic_high": slow["logic_high"], "slow_output_logic_low": slow["logic_low"],
            "fast_valid": int(bool(fast["valid"])), "slow_valid": int(bool(slow["valid"])), "valid": int(valid),
        })
    return rows, {
        "decision": "GO" if not reasons else "NO-GO", "candidate_id": "A",
        "scenario_count": 6, "required_delay_ratio_lower_bound": ratio_required,
        "per_voltage": rows, "reasons": reasons,
    }


def review_candidate_b() -> Dict[str, Any]:
    """Perform the one permitted static candidate-B review without a cell sweep.

    The repository's only documented alternate 2:1 primitive is MXIT2.  Its
    Verilog has an explicit output inverter, so using it would violate the
    required same-polarity unit unless a new inverter were added.  Adding that
    fixed delay defeats the stated purpose of candidate B; therefore no
    reproducible low-overhead B exists in the bounded known inventory.
    """

    candidate_doc = FTC_ROOT.parent / "phase2_vernier/discovery/mux_candidates.md"
    rvt_verilog = Path(
        "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/"
        "arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/verilog/sc9mc_logic0040ll_base_rvt_c40.v"
    )
    valid_doc = candidate_doc.is_file() and "MXIT2_X0P5M_A9TR40" in candidate_doc.read_text(encoding="utf-8")
    inverted = rvt_verilog.is_file() and "module MXIT2_X0P5M_A9TR40" in rvt_verilog.read_text(encoding="latin-1", errors="replace")
    return {
        "decision": "ARCHITECTURE_BLOCKED", "candidate_count": 0,
        "known_inventory_document": str(candidate_doc), "alternate_verilog": str(rvt_verilog),
        "reason": "MXIT2 is output-inverting; no documented same-polarity low-overhead bypass primitive is available",
        "inventory_checked": bool(valid_doc and inverted),
    }


def run_short_chain_phase(hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any], requirements: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run the 3x9 isolated-chain matrix and enforce real code monotonicity."""

    rows: List[Dict[str, Any]] = []
    for vdd_v in ANCHOR_VDD:
        local: List[Dict[str, Any]] = []
        for code in range(9):
            record = execute_deck(
                hspice, run_dir, "short_v{:03d}_c{:02d}".format(int(round(vdd_v * 1000.0)), code),
                "short_chain", render_chain_deck(config, cells, vdd_v, 8, code, dff_load=False),
            )
            classified = classify_path(record, vdd_v)
            local.append({
                "vdd_v": vdd_v, "code": code, "D_code_ps": classified["delay_ps"], "Delta_D_ps": None,
                "output_rise_time_ps": classified["rise_time_ps"], "output_fall_time_ps": classified["fall_time_ps"],
                "output_logic_high": classified["logic_high"], "output_logic_low": classified["logic_low"],
                "logic_valid": int(bool(classified["valid"])), "scenario": record["scenario"],
                "valid": int(bool(classified["valid"])),
            })
        for index in range(1, len(local)):
            before, after = local[index - 1]["D_code_ps"], local[index]["D_code_ps"]
            local[index]["Delta_D_ps"] = None if before is None or after is None else after - before
        rows.extend(local)

    ratio_required = float(requirements["required_delay_ratio_lower_bound"])
    per_voltage: List[Dict[str, Any]] = []
    reasons: List[str] = []
    for vdd_v in ANCHOR_VDD:
        local = [row for row in rows if row["vdd_v"] == vdd_v]
        delays = [row["D_code_ps"] for row in local]
        steps = [row["Delta_D_ps"] for row in local[1:]]
        local_reasons: List[str] = []
        if any(not row["valid"] for row in local) or any(value is None for value in delays):
            local_reasons.append("one or more chain waveforms are invalid")
        elif any(value is None or value <= 0.0 for value in steps):
            local_reasons.append("D(C) is not strictly increasing")
        else:
            step_values = [float(value) for value in steps if value is not None]
            step_ratio = max(step_values) / min(step_values)
            full_ratio = float(delays[-1]) / float(delays[0]) if float(delays[0]) > 0.0 else None
            if step_ratio > SHORT_CHAIN_MAX_STEP_RATIO:
                local_reasons.append("adjacent step ratio exceeds the fine-chain limit")
            if full_ratio is None or full_ratio < ratio_required:
                local_reasons.append("8-stage adjustment ratio is below the required lower bound")
        per_voltage.append({
            "vdd_v": vdd_v, "decision": "GO" if not local_reasons else "NO-GO",
            "min_step_ps": None if not steps or any(value is None for value in steps) else min(steps),
            "median_step_ps": None if not steps or any(value is None for value in steps) else float(median(steps)),
            "max_step_ps": None if not steps or any(value is None for value in steps) else max(steps),
            "step_ratio": None if not steps or any(value is None or value <= 0.0 for value in steps) else max(steps) / min(steps),
            "full_adjustment_ratio": None if not delays or delays[0] in (None, 0.0) or delays[-1] is None else delays[-1] / delays[0],
            "reasons": local_reasons,
        })
        reasons.extend(["{:.2f} V: {}".format(vdd_v, reason) for reason in local_reasons])
    return rows, {"decision": "GO" if not reasons else "NO-GO", "scenario_count": 27, "per_voltage": per_voltage, "reasons": reasons}


def linear_slope(rows: Sequence[Mapping[str, Any]]) -> float:
    """Return the ordinary least-squares delay/code slope for one short chain."""

    xs = [float(row["code"]) for row in rows]
    ys = [float(row["D_code_ps"]) for row in rows]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    denominator = sum((value - mean_x) ** 2 for value in xs)
    if denominator == 0.0:
        raise ValueError("short-chain slope is undefined")
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator


def interpolate(values: Mapping[float, float], target: float) -> float:
    """Use only piecewise-linear interpolation between the three measured anchors."""

    if target in values:
        return values[target]
    points = sorted(values)
    for low, high in zip(points, points[1:]):
        if low < target < high:
            fraction = (target - low) / (high - low)
            return values[low] + fraction * (values[high] - values[low])
    raise ValueError("interpolation target is outside measured anchors")


def size_chain(unit_rows: Sequence[Mapping[str, Any]], short_rows: Sequence[Mapping[str, Any]], requirements: Mapping[str, Any]) -> Dict[str, Any]:
    """Fit the permitted model and select the smallest feasible identical chain."""

    coefficients: Dict[float, Dict[str, float]] = {}
    residuals: Dict[str, List[float]] = {}
    for vdd_v in ANCHOR_VDD:
        unit = next(row for row in unit_rows if float(row["vdd_v"]) == vdd_v)
        local = sorted([row for row in short_rows if float(row["vdd_v"]) == vdd_v], key=lambda row: int(row["code"]))
        if len(local) != 9 or unit["t_fast_rise_ps"] is None or any(row["D_code_ps"] is None for row in local):
            return {"decision": "NO-GO", "no_go_reason_if_any": "incomplete unit or short-chain data"}
        # The one-unit FAST point and C=0 eight-unit point identify the fixed
        # fixture term.  The OLS code slope identifies one SLOW-FAST increment.
        d_fast = (float(local[0]["D_code_ps"]) - float(unit["t_fast_rise_ps"])) / 7.0
        d_common = float(unit["t_fast_rise_ps"]) - d_fast
        increment = linear_slope(local)
        d_slow = d_fast + increment
        if d_fast <= 0.0 or d_slow <= d_fast:
            return {"decision": "NO-GO", "no_go_reason_if_any": "nonphysical fitted delay coefficients"}
        coefficients[vdd_v] = {"D_common_ps": d_common, "d_fast_eff_ps": d_fast, "d_slow_eff_ps": d_slow}
        residuals["{:.2f}".format(vdd_v)] = [
            float(row["D_code_ps"]) - (d_common + (8 - int(row["code"])) * d_fast + int(row["code"]) * d_slow)
            for row in local
        ]

    interpolated: Dict[float, Dict[str, float]] = {}
    for vdd_v in FORMAL_VDD:
        interpolated[vdd_v] = {
            name: interpolate({anchor: values[name] for anchor, values in coefficients.items()}, vdd_v)
            for name in ("D_common_ps", "d_fast_eff_ps", "d_slow_eff_ps")
        }
    brackets = requirements["real_boundary_brackets_by_vdd"]
    upper = min(
        math.floor((float(brackets["{:.2f}".format(vdd_v)]["D_last_Q1_ps"]) - interpolated[vdd_v]["D_common_ps"]) / interpolated[vdd_v]["d_fast_eff_ps"])
        for vdd_v in FORMAL_VDD
    )
    for units in range(3, upper + 1):
        predicted: Dict[str, Dict[str, Any]] = {}
        valid = True
        for vdd_v in FORMAL_VDD:
            model = interpolated[vdd_v]
            bracket = brackets["{:.2f}".format(vdd_v)]
            d_min = model["D_common_ps"] + units * model["d_fast_eff_ps"]
            d_max = model["D_common_ps"] + units * model["d_slow_eff_ps"]
            midpoint = (float(bracket["D_last_Q1_ps"]) + float(bracket["D_first_Q0_ps"])) / 2.0
            step = model["d_slow_eff_ps"] - model["d_fast_eff_ps"]
            k = int(math.ceil((midpoint - d_min) / step))
            predicted["{:.2f}".format(vdd_v)] = {
                "predicted_lock_code": k, "predicted_D_min_ps": d_min,
                "predicted_D_max_ps": d_max, "headroom_codes": units - k,
            }
            if d_min > float(bracket["D_last_Q1_ps"]) or d_max < float(bracket["D_first_Q0_ps"]) or not 1 <= k <= units - 2:
                valid = False
        if valid:
            return {
                "decision": "GO", "selected_N": units, "predicted_by_vdd": predicted,
                "model_coefficients_by_anchor_vdd": {"{:.2f}".format(key): value for key, value in coefficients.items()},
                "model_residuals_from_8_stage_chain": residuals, "no_go_reason_if_any": None,
            }
    return {
        "decision": "NO-GO", "selected_N": None, "predicted_lock_code_by_vdd": {},
        "predicted_D_min_by_vdd": {}, "predicted_D_max_by_vdd": {}, "headroom_codes_by_vdd": {},
        "model_coefficients_by_anchor_vdd": {"{:.2f}".format(key): value for key, value in coefficients.items()},
        "model_residuals_from_8_stage_chain": residuals,
        "no_go_reason_if_any": "no identical-series N satisfies range coverage and 1..N-2 headroom",
    }


def run_full_chain_phase(hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any], sizing: Mapping[str, Any], requirements: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Probe only extremes and predicted local boundaries of the selected chain."""

    units = int(sizing["selected_N"])
    rows: List[Dict[str, Any]] = []
    for vdd_v in ANCHOR_VDD:
        k = int(sizing["predicted_by_vdd"]["{:.2f}".format(vdd_v)]["predicted_lock_code"])
        for code in sorted({0, k - 1, k, k + 1, k + 2, units}):
            record = execute_deck(
                hspice, run_dir, "full_v{:03d}_c{:03d}".format(int(round(vdd_v * 1000.0)), code),
                "full_chain", render_chain_deck(config, cells, vdd_v, units, code, dff_load=True),
            )
            classified = classify_path(record, vdd_v)
            rows.append({
                "vdd_v": vdd_v, "code": code, "D_code_ps": classified["delay_ps"], "Delta_D_ps": None,
                "output_rise_time_ps": classified["rise_time_ps"], "output_fall_time_ps": classified["fall_time_ps"],
                "output_logic_high": classified["logic_high"], "output_logic_low": classified["logic_low"],
                "logic_valid": int(bool(classified["valid"])), "scenario": record["scenario"], "valid": int(bool(classified["valid"])),
            })
    for vdd_v in ANCHOR_VDD:
        local = sorted([row for row in rows if row["vdd_v"] == vdd_v], key=lambda row: int(row["code"]))
        for previous, current in zip(local, local[1:]):
            if current["code"] == previous["code"] + 1:
                current["Delta_D_ps"] = None if previous["D_code_ps"] is None or current["D_code_ps"] is None else current["D_code_ps"] - previous["D_code_ps"]
    brackets = requirements["real_boundary_brackets_by_vdd"]
    per_voltage: List[Dict[str, Any]] = []
    reasons: List[str] = []
    for vdd_v in ANCHOR_VDD:
        local = sorted([row for row in rows if row["vdd_v"] == vdd_v], key=lambda row: int(row["code"]))
        k = int(sizing["predicted_by_vdd"]["{:.2f}".format(vdd_v)]["predicted_lock_code"])
        by_code = {int(row["code"]): row for row in local}
        local_reasons: List[str] = []
        if any(not row["valid"] for row in local):
            local_reasons.append("one or more full-chain waveforms are invalid")
        bracket = brackets["{:.2f}".format(vdd_v)]
        if by_code[0]["D_code_ps"] is None or by_code[units]["D_code_ps"] is None or by_code[0]["D_code_ps"] > float(bracket["D_last_Q1_ps"]) or by_code[units]["D_code_ps"] < float(bracket["D_first_Q0_ps"]):
            local_reasons.append("full-chain extrema do not cover the real-DFF bracket")
        boundary = [by_code[code]["D_code_ps"] for code in range(k - 1, k + 3)]
        if any(value is None for value in boundary) or any(right <= left for left, right in zip(boundary, boundary[1:])):
            local_reasons.append("full-chain boundary neighbourhood is not strictly increasing")
        if k > units - 2:
            local_reasons.append("predicted lock lacks two longer codes")
        per_voltage.append({"vdd_v": vdd_v, "decision": "GO" if not local_reasons else "NO-GO", "reasons": local_reasons})
        reasons.extend(["{:.2f} V: {}".format(vdd_v, reason) for reason in local_reasons])
    return rows, {"decision": "GO" if not reasons else "NO-GO", "scenario_count": len(rows), "per_voltage": per_voltage, "reasons": reasons}


def calibration_rows_for_codes(hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any], vdd_v: float, units: int, predicted_k: int, codes: Sequence[int], label_prefix: str) -> List[Dict[str, Any]]:
    """Run a small, explicit real-DFF calibration neighbourhood at one VDD."""

    rows: List[Dict[str, Any]] = []
    for code in sorted(set(codes)):
        if not 0 <= code <= units:
            continue
        record = execute_deck(
            hspice, run_dir, "{}_v{:03d}_k{}_c{:03d}".format(label_prefix, int(round(vdd_v * 1000.0)), predicted_k, code),
            "calibration", render_system_deck(config, cells, vdd_v, units, code),
        )
        classified = classify_comparator(record, vdd_v)
        rows.append({
            "vdd_v": vdd_v, "predicted_k": predicted_k, "code": code,
            "t_xor_rise_s": record.get("t_xor_rise"), "t_xor_fall_s": record.get("t_xor_fall"),
            "W_S_int_ps": classified["W_S_int_ps"], "t_ck_rise_s": record.get("t_ck_rise"),
            "D_code_ps": classified["D_code_ps"], "q_final_v": record.get("q_final_v"),
            "Q": classified["Q"], "readout_time_s": Q_READ_TIME_S,
            "scenario": record["scenario"], "valid": int(bool(classified["valid"])),
        })
    return rows


def find_lock(rows: Sequence[Mapping[str, Any]], predicted_k: int, units: int) -> Optional[int]:
    """Find one first-zero pattern only within the allowed ±2-code window."""

    by_code = {int(row["code"]): row for row in rows}
    for lock in range(predicted_k - 2, predicted_k + 3):
        required = (lock - 1, lock, lock + 1, lock + 2)
        if not 1 <= lock <= units - 2 or any(code not in by_code for code in required):
            continue
        local = [by_code[code] for code in required]
        if any(int(row["valid"]) != 1 or row["Q"] is None for row in local):
            continue
        if [int(row["Q"]) for row in local] != [1, 0, 0, 0]:
            continue
        delays = [float(row["D_code_ps"]) for row in local]
        if all(right > left for left, right in zip(delays, delays[1:])):
            return lock
    return None


def run_calibration_phase(hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any], sizing: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Calibrate seven workpoints without falling back to a full code sweep."""

    units = int(sizing["selected_N"])
    rows: List[Dict[str, Any]] = []
    per_voltage: List[Dict[str, Any]] = []
    reasons: List[str] = []
    for vdd_v in FORMAL_VDD:
        predicted_k = int(sizing["predicted_by_vdd"]["{:.2f}".format(vdd_v)]["predicted_lock_code"])
        local = calibration_rows_for_codes(
            hspice, run_dir, config, cells, vdd_v, units, predicted_k,
            range(predicted_k - 1, predicted_k + 3), "cal_initial",
        )
        lock = find_lock(local, predicted_k, units)
        if lock is None:
            # The initial set already covers a lock at k-1 through k+2.  The
            # two lower probes are the only extra legal work needed to verify
            # a possible k-2 lock and its preceding Q=1 point.
            extra = calibration_rows_for_codes(
                hspice, run_dir, config, cells, vdd_v, units, predicted_k,
                (predicted_k - 3, predicted_k - 2), "cal_low_shift",
            )
            local.extend(extra)
            lock = find_lock(local, predicted_k, units)
        rows.extend(local)
        local_reasons: List[str] = []
        if lock is None:
            local_reasons.append("no valid first-Q=0 pattern within the allowed local calibration window")
        per_voltage.append({
            "vdd_v": vdd_v, "predicted_k": predicted_k, "lock_code": lock,
            "decision": "GO" if not local_reasons else "NO-GO", "reasons": local_reasons,
        })
        reasons.extend(["{:.2f} V: {}".format(vdd_v, reason) for reason in local_reasons])
    locks = {"{:.2f}".format(item["vdd_v"]): item["lock_code"] for item in per_voltage if item["lock_code"] is not None}
    return rows, {"decision": "GO" if not reasons else "NO-GO", "scenario_count": len(rows), "per_voltage": per_voltage, "locks": locks, "reasons": reasons}


def coarse_points(baseline_vdd_v: float) -> List[float]:
    """Return the required descending 50 mV attack sweep down to 0.80 V."""

    points: List[float] = []
    current = voltage_key(baseline_vdd_v - COARSE_STEP_V)
    while current >= VDD_MIN - 1.0e-12:
        points.append(current)
        current = voltage_key(current - COARSE_STEP_V)
    if not points or points[-1] != VDD_MIN:
        raise ValueError("coarse sweep does not reach the legal lower rail")
    return points


def refinement_points(last_zero_v: float, first_one_v: float) -> List[float]:
    """Return only unmeasured 10 mV points inside one observed coarse bracket."""

    if not last_zero_v > first_one_v >= VDD_MIN:
        raise ValueError("invalid acceptance refinement bracket")
    points: List[float] = []
    current = voltage_key(last_zero_v - REFINEMENT_STEP_V)
    while current > first_one_v + 1.0e-12:
        points.append(current)
        current = voltage_key(current - REFINEMENT_STEP_V)
    return points


def run_acceptance_phase(hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any], units: int, calibration: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run the bounded three-baseline M=1/M=2 static-droop feasibility gate."""

    rows: List[Dict[str, Any]] = []
    trip_map: List[Dict[str, Any]] = []
    reasons: List[str] = []
    locks = {float(key): int(value) for key, value in calibration["locks"].items()}
    for baseline in FEASIBILITY_BASELINES:
        lock = locks.get(baseline)
        if lock is None:
            reasons.append("missing calibration lock at {:.2f} V".format(baseline))
            continue
        for margin in (1, 2):
            alarm_code = lock + margin
            group: List[Dict[str, Any]] = []
            if alarm_code > units:
                trip_map.append({"baseline_vdd_v": baseline, "margin_code": margin, "trip_status": "INVALID", "trip_boundary_v": None})
                reasons.append("alarm code exceeds chain length at {:.2f} V M={}".format(baseline, margin))
                continue
            last_zero: Optional[float] = None
            first_one: Optional[float] = None
            for attack_vdd in coarse_points(baseline):
                record = execute_deck(
                    hspice, run_dir, "accept_v{:03d}_m{}_a{:03d}_coarse".format(int(round(baseline * 1000.0)), margin, int(round(attack_vdd * 1000.0))),
                    "acceptance", render_system_deck(config, cells, attack_vdd, units, alarm_code),
                )
                classified = classify_comparator(record, attack_vdd)
                row = {
                    "baseline_vdd_v": baseline, "attack_vdd_v": attack_vdd, "margin_code": margin,
                    "lock_code": lock, "alarm_code": alarm_code, "scan_phase": "coarse", "scenario": record["scenario"],
                    "W_S_int_ps": classified["W_S_int_ps"], "D_alarm_ps": classified["D_code_ps"],
                    "Q": classified["Q"], "alarm": classified["Q"], "valid": int(bool(classified["valid"])),
                }
                rows.append(row)
                group.append(row)
                if not classified["valid"]:
                    break
                if classified["Q"] == 1:
                    first_one = attack_vdd
                    break
                last_zero = attack_vdd
            if last_zero is not None and first_one is not None:
                for attack_vdd in refinement_points(last_zero, first_one):
                    record = execute_deck(
                        hspice, run_dir, "accept_v{:03d}_m{}_a{:03d}_fine".format(int(round(baseline * 1000.0)), margin, int(round(attack_vdd * 1000.0))),
                        "acceptance", render_system_deck(config, cells, attack_vdd, units, alarm_code),
                    )
                    classified = classify_comparator(record, attack_vdd)
                    row = {
                        "baseline_vdd_v": baseline, "attack_vdd_v": attack_vdd, "margin_code": margin,
                        "lock_code": lock, "alarm_code": alarm_code, "scan_phase": "refinement", "scenario": record["scenario"],
                        "W_S_int_ps": classified["W_S_int_ps"], "D_alarm_ps": classified["D_code_ps"],
                        "Q": classified["Q"], "alarm": classified["Q"], "valid": int(bool(classified["valid"])),
                    }
                    rows.append(row)
                    group.append(row)
            ordered = sorted(group, key=lambda row: float(row["attack_vdd_v"]), reverse=True)
            q_values = [row["Q"] for row in ordered if row["Q"] is not None]
            valid = bool(group) and all(int(row["valid"]) == 1 for row in group)
            no_reversion = all(left >= right for left, right in zip(q_values, q_values[1:]))
            trip_boundary = max((float(row["attack_vdd_v"]) for row in group if row["Q"] == 1), default=None)
            status = "TRIP" if valid and trip_boundary is not None and no_reversion else "NO_TRIP" if valid else "INVALID"
            trip_map.append({
                "baseline_vdd_v": baseline, "margin_code": margin, "trip_status": status,
                "trip_boundary_v": trip_boundary, "no_q_reversion": no_reversion,
            })
            if not valid:
                reasons.append("invalid acceptance measurement at {:.2f} V M={}".format(baseline, margin))
            if not no_reversion:
                reasons.append("Q reverts after asserting at {:.2f} V M={}".format(baseline, margin))

    by_baseline = {baseline: {item["margin_code"]: item for item in trip_map if item["baseline_vdd_v"] == baseline} for baseline in FEASIBILITY_BASELINES}
    for baseline in FEASIBILITY_BASELINES:
        m1 = by_baseline[baseline].get(1, {})
        m2 = by_baseline[baseline].get(2, {})
        if m1.get("trip_status") != "TRIP":
            reasons.append("M=1 has no legal-range trip at {:.2f} V".format(baseline))
        if m1.get("trip_status") == "TRIP" and m2.get("trip_status") == "TRIP" and float(m2["trip_boundary_v"]) > float(m1["trip_boundary_v"]):
            reasons.append("M=2 trips shallower than M=1 at {:.2f} V".format(baseline))
    distinguishable = any(
        by_baseline[baseline].get(1, {}).get("trip_status") == "TRIP" and
        by_baseline[baseline].get(2, {}).get("trip_status") == "TRIP" and
        by_baseline[baseline][1]["trip_boundary_v"] != by_baseline[baseline][2]["trip_boundary_v"]
        for baseline in FEASIBILITY_BASELINES
    )
    if not distinguishable:
        reasons.append("no baseline distinguishes M=1 and M=2 on the 10 mV grid")
    return rows, {"decision": "GO" if not reasons else "NO-GO", "scenario_count": len(rows), "trip_map": trip_map, "reasons": reasons}


def stage_summary(unit: Optional[Mapping[str, Any]] = None, short: Optional[Mapping[str, Any]] = None, sizing: Optional[Mapping[str, Any]] = None, full: Optional[Mapping[str, Any]] = None, calibration: Optional[Mapping[str, Any]] = None, acceptance: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Normalize six stage states so an early stop can never look like a pass."""

    values = {
        "Unit Cell": unit, "8-Stage Short Chain": short, "N Sizing": sizing,
        "Full Chain": full, "Real-DFF Calibration": calibration,
        "C_lock + M Feasibility": acceptance,
    }
    return {name: "NOT_RUN" if value is None else value["decision"] for name, value in values.items()}


def render_report(path: Path, summary: Mapping[str, Any]) -> None:
    """Publish a concise gate-by-gate report without claiming unrun evidence."""

    lines = ["# FTC Fine-Grained Controllable Delay", "", "## Decision", "", "**{}**".format(summary["decision"]), "", "## Stage Status", "", "| Stage | Status |", "|---|---|"]
    for name, status in summary["stages"].items():
        lines.append("| {} | {} |".format(name, status))
    lines.extend(["", "## Reasons", ""])
    reasons = summary.get("reasons", [])
    lines.extend(["- {}".format(reason) for reason in reasons] if reasons else ["- All required gates passed."])
    lines.extend(["", "## Scope", "", "- TT/25°C only; no PVT, RTL, power, area, or layout claim is made.", "- Historical 3-bit tap-tree runners and raw data were read-only inputs."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def publish_summary(analysis_dir: Path, report_output: Path, requirements: Mapping[str, Any], stages: Mapping[str, str], reasons: Sequence[str], details: Mapping[str, Any]) -> Dict[str, Any]:
    """Write the terminal public evidence after each allowed stopping point."""

    passed = all(status == "GO" for status in stages.values())
    summary = {
        "schema_version": 1,
        "decision": "Fine-Grained Controllable Delay = GO" if passed else "Fine-Grained Controllable Delay = NO-GO",
        "formal_vdd_range_v": [VDD_MIN, VDD_MAX], "stages": dict(stages),
        "requirements_sha256": sha256_file(analysis_dir / "requirements.json"),
        "reasons": list(reasons), "details": dict(details),
    }
    write_json(analysis_dir / "summary.json", summary)
    render_report(report_output, summary)
    return summary


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Expose locations only; all electrical choices remain fixed constants."""

    parser = argparse.ArgumentParser(description="run FTC fine-grained controllable-delay validation")
    parser.add_argument("--config", type=Path, default=FTC_ROOT / "ftc_config.json")
    parser.add_argument("--run-dir", type=Path, default=FTC_ROOT / "runs/fine_grained_controllable_delay/r1")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis/fine_grained_controllable_delay")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports/FTC_FINE_GRAINED_CONTROLLABLE_DELAY.md")
    parser.add_argument("--phase0-only", action="store_true", help="publish and validate requirements without creating a raw run")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Execute the fixed phase order, publishing a terminal decision on every Gate."""

    args = parse_args(argv)
    config = load_json(args.config.resolve())
    validate_config(config)
    frozen = verify_frozen_evidence()
    analysis_dir = args.analysis_dir.resolve()
    report_output = args.report_output.resolve()
    requirements = build_requirements(frozen)
    requirements_path = analysis_dir / "requirements.json"
    write_json(requirements_path, requirements)
    # Re-read the generated artifact before Phase 1 so all later work consumes
    # the same persisted evidence file that external reviewers inspect.
    requirements = load_json(requirements_path)
    validate_requirements(requirements, frozen)
    if args.phase0_only:
        print("FTC_FINE_GRAINED_CONTROLLABLE_DELAY phase0=requirements_published")
        return 0

    cells = frozen["cells"]
    hspice = prepare_run(args.run_dir.resolve(), config, cells, requirements)
    run_dir = args.run_dir.resolve()

    unit_rows, unit = run_unit_phase(hspice, run_dir, config, cells, requirements)
    write_csv(analysis_dir / "unit_cell.csv", UNIT_FIELDS, unit_rows)
    candidate_b = review_candidate_b() if unit["decision"] != "GO" else {"decision": "NOT_NEEDED"}
    unit_decision = {"unit_cell": unit, "candidate_b_review": candidate_b}
    write_json(analysis_dir / "unit_cell_decision.json", unit_decision)
    if unit["decision"] != "GO":
        stages = stage_summary(unit=unit)
        publish_summary(analysis_dir, report_output, requirements, stages, unit["reasons"] + [candidate_b.get("reason", "")], {"unit_cell": unit_decision})
        print("FTC_FINE_GRAINED_CONTROLLABLE_DELAY decision=NO-GO stage=unit")
        return 0

    short_rows, short = run_short_chain_phase(hspice, run_dir, config, cells, requirements)
    write_csv(analysis_dir / "short_chain.csv", SHORT_FIELDS, short_rows)
    write_json(analysis_dir / "short_chain_decision.json", short)
    if short["decision"] != "GO":
        stages = stage_summary(unit=unit, short=short)
        publish_summary(analysis_dir, report_output, requirements, stages, short["reasons"], {"unit_cell": unit, "short_chain": short})
        print("FTC_FINE_GRAINED_CONTROLLABLE_DELAY decision=NO-GO stage=short_chain")
        return 0

    sizing = size_chain(unit_rows, short_rows, requirements)
    write_json(analysis_dir / "chain_sizing.json", sizing)
    if sizing["decision"] != "GO":
        stages = stage_summary(unit=unit, short=short, sizing=sizing)
        publish_summary(analysis_dir, report_output, requirements, stages, [sizing["no_go_reason_if_any"]], {"unit_cell": unit, "short_chain": short, "sizing": sizing})
        print("FTC_FINE_GRAINED_CONTROLLABLE_DELAY decision=NO-GO stage=sizing")
        return 0

    full_rows, full = run_full_chain_phase(hspice, run_dir, config, cells, sizing, requirements)
    write_csv(analysis_dir / "full_chain_probe.csv", FULL_FIELDS, full_rows)
    if full["decision"] != "GO":
        stages = stage_summary(unit=unit, short=short, sizing=sizing, full=full)
        publish_summary(analysis_dir, report_output, requirements, stages, full["reasons"], {"sizing": sizing, "full_chain": full})
        print("FTC_FINE_GRAINED_CONTROLLABLE_DELAY decision=NO-GO stage=full_chain")
        return 0

    calibration_rows, calibration = run_calibration_phase(hspice, run_dir, config, cells, sizing)
    write_csv(analysis_dir / "calibration_gate.csv", CALIBRATION_FIELDS, calibration_rows)
    if calibration["decision"] != "GO":
        stages = stage_summary(unit=unit, short=short, sizing=sizing, full=full, calibration=calibration)
        publish_summary(analysis_dir, report_output, requirements, stages, calibration["reasons"], {"sizing": sizing, "calibration": calibration})
        print("FTC_FINE_GRAINED_CONTROLLABLE_DELAY decision=NO-GO stage=calibration")
        return 0

    acceptance_rows, acceptance = run_acceptance_phase(hspice, run_dir, config, cells, int(sizing["selected_N"]), calibration)
    write_csv(analysis_dir / "acceptance_feasibility.csv", ACCEPTANCE_FIELDS, acceptance_rows)
    stages = stage_summary(unit=unit, short=short, sizing=sizing, full=full, calibration=calibration, acceptance=acceptance)
    publish_summary(analysis_dir, report_output, requirements, stages, acceptance["reasons"], {"sizing": sizing, "acceptance": acceptance})
    print("FTC_FINE_GRAINED_CONTROLLABLE_DELAY decision={}".format(acceptance["decision"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
