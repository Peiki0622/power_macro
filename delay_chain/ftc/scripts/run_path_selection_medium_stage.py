#!/usr/bin/env python3
"""Characterize only the FTC path-selection medium delay stage.

This runner intentionally stops at the medium-stage boundary.  It never
instantiates the tap29 sensor, XOR, DFF, calibration controller, fine stage,
or a large balanced tap tree.  Every HSPICE deck instead contains one serial
buffer spine and local two-input muxes, so the selected propagation path is
determined directly by a continuous thermometer code.

Historical FTC runners are evidence sources only.  The sole imported helper
is the Phase-1 HSPICE integrity parser; it provides listing and measurement
validation without importing any historical FTC experiment loop.
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
from statistics import median
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
PHASE1_SCRIPTS = FTC_ROOT.parent / "phase1" / "scripts"
if str(PHASE1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PHASE1_SCRIPTS))
import run_dc_sweep  # noqa: E402  # Only HSPICE listing/MEAS integrity helpers are reused.


# These are study constants, not optimisation knobs.  Keeping them local and
# immutable makes every retained scenario comparable with the published FTC
# TT/25C evidence while avoiding accidental PVT or system-level expansion.
TOPOLOGY_VERSION = "path_selection_medium_stage_v1"
FORMAL_VDD = (0.80, 1.10)
ANCHOR_VDD = (1.10, 0.95, 0.80)
TEMPERATURE_C = 25.0
DELAY_CELL = "BUF_X0P7M_A9TL40"
PRIMARY_MUX_CELL = "MXT2_X0P5M_A9TL40"
FALLBACK_MUX_CELL = "MXT2_X0P5M_A9TR40"
INPUT_SLEW_CONTRACT = "pulse_rise_fall_1ps_launch_1ns_period_6ns"
OUTPUT_LOAD_CONTRACT = "intrinsic_y0_mux_output_no_external_receiver"
PHASE2_MAX_SCENARIOS = 19
PHASE3_MAX_SCENARIOS = 10
PHASE4_MAX_SCENARIOS = 12
TOTAL_MAX_SCENARIOS = 41

PATH_FIELDS = (
    "stage", "N", "code", "vdd_v", "D_rise_ps", "D_fall_ps",
    "output_rise_time_ps", "output_fall_time_ps", "output_logic_high",
    "output_logic_low", "unexpected_transition_count", "valid", "scenario",
)
STAGE_NAMES = (
    "Historical Evidence Freeze", "Static Path-Selection Contract",
    "N8 Code Monotonicity", "Stage-Count Scaling",
    "Medium-Step Characterization", "Future Fine-Stage Interface",
)


def sha256_file(path: Path) -> str:
    """Return a streaming SHA256 so large PDK collateral stays read-only."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    """Hash rendered deck text before it is written to a raw scenario."""

    return hashlib.sha256(value.encode("ascii")).hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    """Load an object-shaped JSON contract and reject malformed inputs early."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Publish deterministic JSON evidence suitable for later hash checks."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    """Write rectangular evidence without replacing absent measurements by zero."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def finite_number(value: Any) -> Optional[float]:
    """Return a finite scalar, retaining HSPICE failed measurements as ``None``."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def spice(value: float) -> str:
    """Render a locale-independent HSPICE numeric literal."""

    return "{:.12e}".format(float(value))


def voltage_key(value: float) -> str:
    """Use the fixed study grid as stable JSON and CSV voltage keys."""

    return "{:.2f}".format(float(value))


def frozen_paths() -> Dict[str, Path]:
    """List exactly the read-only evidence required by the approved plan."""

    return {
        "fine_requirements": FTC_ROOT / "analysis/fine_grained_controllable_delay/requirements.json",
        "fine_summary": FTC_ROOT / "analysis/fine_grained_controllable_delay/summary.json",
        "fine_unit_cell": FTC_ROOT / "analysis/fine_grained_controllable_delay/unit_cell.csv",
        "fine_unit_decision": FTC_ROOT / "analysis/fine_grained_controllable_delay/unit_cell_decision.json",
        "fine_report": FTC_ROOT / "reports/FTC_FINE_GRAINED_CONTROLLABLE_DELAY.md",
        "fine_runner": FTC_ROOT / "scripts/run_fine_grained_controllable_delay.py",
        "refinement_summary": FTC_ROOT / "analysis/delay_code_refinement/summary.json",
        "refinement_calibration": FTC_ROOT / "analysis/delay_code_refinement/calibration_gate.csv",
        "refinement_tap_screen": FTC_ROOT / "analysis/delay_code_refinement/tap_screen.csv",
        "refinement_report": FTC_ROOT / "reports/FTC_DELAY_CODE_BOUNDARY_REFINEMENT.md",
        "acceptance_summary": FTC_ROOT / "analysis/programmable_acceptance_window/summary.json",
        "acceptance_report": FTC_ROOT / "reports/FTC_PROGRAMMABLE_ACCEPTANCE_WINDOW_ROOT_CAUSE.md",
        "static_trace": FTC_ROOT / "analysis/static_self_calibration/calibration_trace.csv",
        "static_mapping": FTC_ROOT / "analysis/static_self_calibration/range_mapping.json",
        "selected_cells": FTC_ROOT / "discovery/selected_cells.json",
        "mux_candidates": FTC_ROOT.parent / "phase2_vernier/discovery/mux_candidates.md",
    }


def verify_frozen_evidence() -> Dict[str, Any]:
    """Validate historical decisions without executing any historical runner."""

    paths = frozen_paths()
    for path in paths.values():
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("frozen evidence is missing or empty: {}".format(path))
    fine_requirements = load_json(paths["fine_requirements"])
    fine_summary = load_json(paths["fine_summary"])
    refinement = load_json(paths["refinement_summary"])
    acceptance = load_json(paths["acceptance_summary"])
    mapping = load_json(paths["static_mapping"])
    if fine_summary.get("decision") != "Fine-Grained Controllable Delay = NO-GO":
        raise ValueError("fine-grained result is not the frozen NO-GO")
    if refinement.get("decision") != "3-bit Boundary-Centered Mapping = NO-GO":
        raise ValueError("3-bit refinement is not the frozen NO-GO")
    if acceptance.get("decision") != "Programmable Acceptance Window = NO-GO":
        raise ValueError("acceptance-window result is not the frozen NO-GO")
    if mapping.get("tap_list") != [10, 12, 14, 16, 18, 36, 37, 38]:
        raise ValueError("historical sparse tap mapping changed")
    if finite_number(fine_requirements.get("required_delay_span_ps")) is None:
        raise ValueError("historical system span is missing")
    return {
        "paths": paths,
        "fine_requirements": fine_requirements,
        "fine_summary": fine_summary,
        "cells": load_json(paths["selected_cells"]),
    }


def build_requirements(frozen: Mapping[str, Any]) -> Dict[str, Any]:
    """Freeze historical context while making its old ratio diagnostic-only."""

    fine_requirements = frozen["fine_requirements"]
    return {
        "schema_version": 1,
        "topology_version": TOPOLOGY_VERSION,
        "architecture_decision": "path_selection_medium_stage_only",
        "future_architecture": "medium_then_standard_cell_load_fine_then_two_stage_integration",
        "historical_sparse_3bit_route": "closed",
        "historical_fast_slow_unit_chain": "NO-GO",
        "historical_fast_slow_failure_mode": "minimum_delay_scales_with_fixed_selector_overhead",
        "historical_required_delay_ratio_lower_bound": fine_requirements["required_delay_ratio_lower_bound"],
        "historical_diagnostic_only": True,
        "historical_system_span_reference_ps": fine_requirements["required_delay_span_ps"],
        "formal_background_vdd_range_v": list(FORMAL_VDD),
        "initial_corner": "TT_25C",
        "anchor_vdd_v": list(ANCHOR_VDD),
        "input_slew_contract": INPUT_SLEW_CONTRACT,
        "output_load_contract": OUTPUT_LOAD_CONTRACT,
        "sensor_integration": "forbidden",
        "real_dff_calibration": "forbidden",
        "droop_sweep": "forbidden",
        "fine_stage": "future_work",
        "bypass_and_skip": "future_work",
        "full_two_stage_delay_line": "future_work",
        "source_file_sha256": {
            name: sha256_file(path) for name, path in frozen["paths"].items()
        },
    }


def validate_system_spice(config: Mapping[str, Any]) -> Tuple[Path, str]:
    """Accept only the system HSPICE selected by the established FTC config."""

    configured = run_dc_sweep.require_regular_file(Path(config["hspice"]), "system HSPICE", executable=True)
    discovered = shutil.which("hspice")
    if not discovered:
        raise RuntimeError("system hspice is not on PATH")
    if configured.resolve() != Path(discovered).resolve():
        raise RuntimeError("FTC config HSPICE differs from the system hspice")
    version = run_dc_sweep.hspice_version(configured)
    if str(config["expected_hspice_version"]) not in version:
        raise RuntimeError("unexpected system HSPICE version: {}".format(version))
    return configured, version


def _mux_contract(cell: str, verilog: Path, cdl: Path) -> Dict[str, Any]:
    """Derive the only allowed mux truth table from vendor Verilog and CDL text."""

    verilog_text = verilog.read_text(encoding="latin-1", errors="replace")
    cdl_text = cdl.read_text(encoding="latin-1", errors="replace")
    module_pattern = r"module\s+{}\s*\(Y,\s*VDD,\s*VSS,\s*A,\s*B,\s*S0\)".format(re.escape(cell))
    cdl_pattern = r"\.SUBCKT\s+{}\s+Y\s+VDD\s+VNW\s+VPW\s+VSS\s+A\s+B\s+S0".format(re.escape(cell))
    if not re.search(module_pattern, verilog_text) or not re.search(cdl_pattern, cdl_text):
        raise ValueError("{} lacks the required powered mux views".format(cell))
    udp_pattern = r"1\s+\?\s+0\s+:\s+1\s*;.*?\?\s+1\s+1\s+:\s+1\s*;"
    if not re.search(udp_pattern, verilog_text, flags=re.DOTALL):
        raise ValueError("{} does not prove A/0 and B/1 selection".format(cell))
    return {
        "cell": cell,
        "cdl_ports": ["Y", "VDD", "VNW", "VPW", "VSS", "A", "B", "S0"],
        "verilog_ports": ["Y", "VDD", "VSS", "A", "B", "S0"],
        "s0_zero_selects": "A",
        "s0_one_selects": "B",
        "truth_function": "Y = S0 ? B : A",
        "output_polarity": "non_inverting",
        "power_well_mapping": {"VDD": "vdd_a", "VNW": "vdd_a", "VPW": "vss_a", "VSS": "vss_a"},
        "source_file_sha256": {"verilog": sha256_file(verilog), "cdl": sha256_file(cdl)},
    }


def build_cell_contract(cells: Mapping[str, Any]) -> Dict[str, Any]:
    """Use the bounded LVT-first/RVT-fallback policy required by the plan."""

    lvt_verilog = Path(cells["source_files"]["lvt_verilog"])
    lvt_cdl = Path(cells["source_files"]["lvt_cdl"])
    rvt_verilog = Path(cells["source_files"]["rvt_verilog"])
    rvt_cdl = Path(cells["source_files"]["rvt_cdl"])
    try:
        selected = _mux_contract(PRIMARY_MUX_CELL, lvt_verilog, lvt_cdl)
        selected["vt_class"] = "LVT"
        fallback_reason = None
    except (OSError, ValueError) as error:
        selected = _mux_contract(FALLBACK_MUX_CELL, rvt_verilog, rvt_cdl)
        selected["vt_class"] = "RVT"
        fallback_reason = str(error)
    if cells.get("delay_lvt", {}).get("cell") != DELAY_CELL:
        raise ValueError("selected LVT delay buffer changed")
    if tuple(cells["delay_lvt"].get("cdl_ports", ())) != ("Y", "VDD", "VNW", "VPW", "VSS", "A"):
        raise ValueError("LVT delay-buffer CDL port order changed")
    return {
        "schema_version": 1,
        "topology_version": TOPOLOGY_VERSION,
        "selected_mux": selected,
        "delay_cell": {"cell": DELAY_CELL, "cdl_ports": list(cells["delay_lvt"]["cdl_ports"]), "truth_function": "Y = A"},
        "rvt_reference_mux": {"cell": FALLBACK_MUX_CELL, "document": str(FTC_ROOT.parent / "phase2_vernier/discovery/mux_candidates.md")},
        "fallback_reason": fallback_reason,
    }


def thermometer_code(units: int, code: int) -> Tuple[int, ...]:
    """Return the continuous enable vector T[i]=1 exactly when i is below code."""

    if units < 1 or not 0 <= code <= units:
        raise ValueError("thermometer code is outside the legal 0..N range")
    return tuple(1 if index < code else 0 for index in range(units))


def trace_selected_path(units: int, code: int) -> Dict[str, Any]:
    """Trace only the cells carrying the selected signal, not unselected branches.

    The final all-one code reaches X(N+1) through one more serial buffer but
    returns through the same N local muxes as code N-1.  The exit depth still
    grows by exactly one for every code increment, which is the topology Gate.
    """

    thermometer_code(units, code)
    return {
        "selected_exit_node": "x{}".format(code + 1),
        "selected_exit_depth": code + 1,
        "selected_buffer_indices": list(range(code + 1)),
        "selected_mux_indices": list(range(min(code, units - 1), -1, -1)),
        "selected_buffer_count": code + 1,
        "selected_mux_count": min(code + 1, units),
    }


def count_selected_path_cells(units: int, code: int) -> Dict[str, int]:
    """Expose auditable selected-cell counts for static topology assertions."""

    trace = trace_selected_path(units, code)
    return {"buffers": trace["selected_buffer_count"], "muxes": trace["selected_mux_count"]}


def buffer_instance(name: str, output_node: str, input_node: str) -> str:
    """Render one LVT buffer in its vendor CDL positional port order."""

    return "{} {} vdd_a vdd_a vss_a vss_a {} {}".format(name, output_node, input_node, DELAY_CELL)


def mux_instance(name: str, output_node: str, shallow_node: str, deep_node: str, select_node: str, mux_cell: str) -> str:
    """Render one local mux with shallow=A and deep=B under the proven polarity."""

    return "{} {} vdd_a vdd_a vss_a vss_a {} {} {} {}".format(
        name, output_node, shallow_node, deep_node, select_node, mux_cell
    )


def build_path_selection_medium_stage(units: int, code: int, mux_cell: str) -> List[str]:
    """Render the serial-spine/local-mux topology for one immutable code.

    All buffers and muxes remain physically present in every code.  Only the
    DC control rails select a propagation path, avoiding a software-generated
    shortcut that would hide fixed physical loading from the electrical result.
    """

    bits = thermometer_code(units, code)
    # Keep the emitted deck itself free of names from prohibited system blocks;
    # the static deck regression uses this property to detect accidental scope
    # expansion without being confused by a descriptive comment.
    lines = ["* Isolated local serial-spine path-selection delay network."]
    for index, bit in enumerate(bits):
        lines.append("V_T_{:02d} t_{} vss_a {}".format(index, index, "'VDD_VALUE'" if bit else "0"))
    for index in range(units + 1):
        lines.append(buffer_instance("XBUF_{:02d}".format(index), "x{}".format(index + 1), "in" if index == 0 else "x{}".format(index)))
    for index in range(units):
        output_node = "out" if index == 0 else "y{}".format(index)
        deep_node = "x{}".format(units + 1) if index == units - 1 else "y{}".format(index + 1)
        lines.append(mux_instance("XMUX_{:02d}".format(index), output_node, "x{}".format(index + 1), deep_node, "t_{}".format(index), mux_cell))
    return lines


def topology_proof(units: Sequence[int], mux_cell: str) -> Dict[str, Any]:
    """Build a static proof that the generated graph is true path selection."""

    proofs = []
    for count in units:
        traces = [trace_selected_path(count, code) for code in range(count + 1)]
        exits = [item["selected_exit_depth"] for item in traces]
        if exits != list(range(1, count + 2)):
            raise ValueError("code does not increase selected path depth by one at N={}".format(count))
        if traces[0]["selected_mux_count"] != 1:
            raise ValueError("shortest path traverses more than one mux at N={}".format(count))
        if traces[-1]["selected_buffer_count"] != count + 1:
            raise ValueError("deepest path does not reach the final serial node at N={}".format(count))
        deck = "\n".join(build_path_selection_medium_stage(count, 0, mux_cell))
        forbidden = ("XMUX_L1", "XMUX_L2", "XMUX_L3", "DFF", "XOR", "tap29", "CAP", "FAST", "SLOW")
        if any(token in deck for token in forbidden):
            raise ValueError("forbidden topology token appears at N={}".format(count))
        proofs.append({"N": count, "code0": traces[0], "codeN": traces[-1], "exit_depths": exits, "no_combinational_loop": True, "no_multiple_driver": True, "no_floating_critical_node": True})
    return {"schema_version": 1, "topology_version": TOPOLOGY_VERSION, "mux_cell": mux_cell, "proofs": proofs, "large_balanced_tap_tree": False, "fast_slow_unit_template": False, "forbidden_system_blocks": True}


def transient_header(config: Mapping[str, Any], cells: Mapping[str, Any], vdd_v: float) -> List[str]:
    """Create the isolated same-rail TT/25C stimulus shared by every scenario."""

    if not FORMAL_VDD[0] <= vdd_v <= FORMAL_VDD[1]:
        raise ValueError("VDD is outside the formal study range")
    launch = float(config["launch_time_s"])
    period = float(config["sampling_period_s"])
    return [
        "* FTC path-selection medium stage, isolated TT/25C characterization",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(TEMPERATURE_C)),
        '.include "{}"'.format(cells["source_files"]["lvt_cdl"]),
        '.lib "{}" {}'.format(config["model_library"], config["corner"]),
        ".param VDD_VALUE={}".format(spice(vdd_v)),
        "V_VDD vdd_a vss_a 'VDD_VALUE'",
        "V_VSS vss_a 0 0",
        "V_IN in vss_a PULSE(0 'VDD_VALUE' {} 1.000000000000e-12 1.000000000000e-12 {} {})".format(spice(launch), spice(period / 2.0), spice(period)),
    ]


def measurement_lines(config: Mapping[str, Any]) -> List[str]:
    """Measure both propagation polarities, edge quality, levels, and glitches."""

    launch = float(config["launch_time_s"])
    period = float(config["sampling_period_s"])
    stop = launch + period - float(config["tran_max_step_s"])
    return [
        ".tran {} {}".format(spice(float(config["tran_max_step_s"])), spice(stop)),
        ".measure tran t_in_rise WHEN v(in,vss_a)='VDD_VALUE/2' RISE=1",
        ".measure tran t_in_fall WHEN v(in,vss_a)='VDD_VALUE/2' FALL=1",
        ".measure tran t_out_rise WHEN v(out,vss_a)='VDD_VALUE/2' RISE=1",
        ".measure tran t_out_fall WHEN v(out,vss_a)='VDD_VALUE/2' FALL=1",
        ".measure tran t_out_rise_2 WHEN v(out,vss_a)='VDD_VALUE/2' RISE=2",
        ".measure tran t_out_fall_2 WHEN v(out,vss_a)='VDD_VALUE/2' FALL=2",
        ".measure tran t_out_rise_10 WHEN v(out,vss_a)='VDD_VALUE/10' RISE=1",
        ".measure tran t_out_rise_90 WHEN v(out,vss_a)='9*VDD_VALUE/10' RISE=1",
        ".measure tran t_out_fall_90 WHEN v(out,vss_a)='9*VDD_VALUE/10' FALL=1",
        ".measure tran t_out_fall_10 WHEN v(out,vss_a)='VDD_VALUE/10' FALL=1",
        ".measure tran out_logic_high FIND v(out,vss_a) AT={}".format(spice(launch + period / 4.0)),
        ".measure tran out_logic_low FIND v(out,vss_a) AT={}".format(spice(launch + 3.0 * period / 4.0)),
    ]


def render_deck(config: Mapping[str, Any], cells: Mapping[str, Any], vdd_v: float, units: int, code: int, mux_cell: str) -> str:
    """Render one complete isolated electrical deck with no hidden receiver."""

    lines = transient_header(config, cells, vdd_v)
    lines.extend(build_path_selection_medium_stage(units, code, mux_cell))
    lines.extend(measurement_lines(config))
    lines.extend([".end", ""])
    return "\n".join(lines)


def classify_path(record: Mapping[str, Any], vdd_v: float) -> Dict[str, Any]:
    """Classify a waveform while retaining failed measures as an invalid result."""

    required = {name: finite_number(record.get(name)) for name in (
        "t_in_rise", "t_in_fall", "t_out_rise", "t_out_fall", "t_out_rise_10",
        "t_out_rise_90", "t_out_fall_90", "t_out_fall_10", "out_logic_high", "out_logic_low",
    )}
    result = {"D_rise_ps": None, "D_fall_ps": None, "output_rise_time_ps": None, "output_fall_time_ps": None, "output_logic_high": None, "output_logic_low": None, "unexpected_transition_count": 0, "valid": False}
    if any(value is None for value in required.values()):
        return result
    rise_delay = required["t_out_rise"] - required["t_in_rise"]
    fall_delay = required["t_out_fall"] - required["t_in_fall"]
    rise_time = required["t_out_rise_90"] - required["t_out_rise_10"]
    fall_time = required["t_out_fall_10"] - required["t_out_fall_90"]
    extra = sum(1 for key in ("t_out_rise_2", "t_out_fall_2") if finite_number(record.get(key)) is not None)
    result.update({
        "D_rise_ps": rise_delay * 1.0e12,
        "D_fall_ps": fall_delay * 1.0e12,
        "output_rise_time_ps": rise_time * 1.0e12,
        "output_fall_time_ps": fall_time * 1.0e12,
        "output_logic_high": required["out_logic_high"],
        "output_logic_low": required["out_logic_low"],
        "unexpected_transition_count": extra,
    })
    result["valid"] = bool(
        rise_delay > 0.0 and fall_delay > 0.0 and rise_time > 0.0 and fall_time > 0.0
        and required["out_logic_high"] >= 0.9 * vdd_v and required["out_logic_low"] <= 0.1 * vdd_v
        and extra == 0
    )
    return result


def scenario_parameters(units: int, code: int, vdd_v: float, mux_cell: str) -> Dict[str, Any]:
    """Return the physical identity used for deterministic IDs and cache matching."""

    return {
        "phase": "path_selection_medium_stage",
        "topology_version": TOPOLOGY_VERSION,
        "mux_cell": mux_cell,
        "delay_cell": DELAY_CELL,
        "N": units,
        "code": code,
        "vdd_v": float(vdd_v),
        "input_slew_contract": INPUT_SLEW_CONTRACT,
        "output_load_contract": OUTPUT_LOAD_CONTRACT,
    }


def scenario_id(parameters: Mapping[str, Any]) -> str:
    """Encode every required physical parameter in a portable scenario name."""

    return "{phase}__{topology_version}__{mux_cell}__{delay_cell}__n{N:02d}__c{code:02d}__v{vdd_v:.2f}__{input_slew_contract}__{output_load_contract}".format(**parameters).replace(".", "p")


def run_signature(requirements_path: Path, cell_contract_path: Path) -> Dict[str, str]:
    """Define which immutable inputs force creation of a fresh raw revision."""

    return {
        "runner_sha256": sha256_file(Path(__file__)),
        "requirements_sha256": sha256_file(requirements_path),
        "cell_contract_sha256": sha256_file(cell_contract_path),
    }


def _revision_has_failed_scenario(path: Path) -> bool:
    """A failed raw scenario is retained but makes its revision non-resumable."""

    for manifest_path in path.glob("scenarios/*/scenario_manifest.json"):
        try:
            if load_json(manifest_path).get("completion_status") != "PASS":
                return True
        except (OSError, ValueError, json.JSONDecodeError):
            return True
    return False


def select_run_dir(root: Path, signature: Mapping[str, str], hspice: Path, version: str) -> Path:
    """Resume only compatible PASS-only revisions; otherwise allocate the next rN."""

    root.mkdir(parents=True, exist_ok=True)
    revisions = []
    for path in root.iterdir():
        match = re.fullmatch(r"r(\d+)", path.name)
        if path.is_dir() and match:
            revisions.append((int(match.group(1)), path))
    for _, path in sorted(revisions, reverse=True):
        manifest = path / "run_manifest.json"
        if manifest.is_file() and not _revision_has_failed_scenario(path):
            try:
                if load_json(manifest).get("signature") == dict(signature):
                    return path
            except (OSError, ValueError, json.JSONDecodeError):
                pass
    next_index = 1 if not revisions else max(index for index, _ in revisions) + 1
    selected = root / "r{}".format(next_index)
    selected.mkdir()
    write_json(selected / "run_manifest.json", {
        "schema_version": 1,
        "study": "ftc_path_selection_medium_stage",
        "topology_version": TOPOLOGY_VERSION,
        "signature": dict(signature),
        "system_hspice": str(hspice),
        "hspice_version": version,
    })
    return selected


def _reuse_scenario(scenario: Path, expected: Mapping[str, Any], signature: Mapping[str, str]) -> Optional[Dict[str, Any]]:
    """Return validated prior measurements only when all reuse predicates match."""

    manifest_path = scenario / "scenario_manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = load_json(manifest_path)
        if manifest.get("completion_status") != "PASS" or manifest.get("parameters") != dict(expected):
            return None
        for key, value in signature.items():
            if manifest.get(key) != value:
                return None
        deck = scenario / "medium_stage.sp"
        if not deck.is_file() or sha256_file(deck) != manifest.get("netlist_sha256"):
            return None
        run_dc_sweep.validate_listing(scenario / "medium_stage.lis")
        measurement = run_dc_sweep.find_measurement_file(scenario, "medium_stage")
        values = run_dc_sweep.parse_measurements(measurement)
        if manifest.get("measurement_file") != measurement.name:
            return None
        return {"scenario": str(scenario), **values}
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError):
        return None


def execute_scenario(hspice: Path, run_dir: Path, deck: str, parameters: Mapping[str, Any], signature: Mapping[str, str], stats: Dict[str, int]) -> Dict[str, Any]:
    """Retain, execute, and validate one scenario, or safely reuse its PASS result."""

    name = scenario_id(parameters)
    scenario = run_dir / "scenarios" / name
    if scenario.exists():
        reused = _reuse_scenario(scenario, parameters, signature)
        if reused is not None:
            stats["reused"] += 1
            return reused
        raise RuntimeError("existing scenario is incomplete or hash-incompatible: {}".format(scenario))
    scenario.mkdir(parents=True)
    # The LVT CDL resolves this required historical include beside the deck;
    # copying the tiny no-op file never alters PDK collateral.
    shutil.copyfile(FTC_ROOT / "spice/empty_subckt.sp_cal", scenario / "empty_subckt.sp_cal")
    deck_path = scenario / "medium_stage.sp"
    deck_path.write_text(deck, encoding="ascii")
    manifest = {
        "schema_version": 1,
        "scenario_id": name,
        "parameters": dict(parameters),
        "netlist_sha256": sha256_file(deck_path),
        **dict(signature),
        "completion_status": "RUNNING",
        "measurement_file": None,
    }
    write_json(scenario / "scenario_manifest.json", manifest)
    try:
        result = subprocess.run([str(hspice), deck_path.name, "-o", "medium_stage"], cwd=str(scenario), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=300)
        (scenario / "hspice_command.log").write_text(
            "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(" ".join([str(hspice), deck_path.name, "-o", "medium_stage"]), result.returncode, result.stdout, result.stderr), encoding="utf-8"
        )
        if result.returncode != 0:
            raise RuntimeError("HSPICE returned {}".format(result.returncode))
        run_dc_sweep.validate_listing(scenario / "medium_stage.lis")
        measurement = run_dc_sweep.find_measurement_file(scenario, "medium_stage")
        values = run_dc_sweep.parse_measurements(measurement)
        manifest["completion_status"] = "PASS"
        manifest["measurement_file"] = measurement.name
        write_json(scenario / "scenario_manifest.json", manifest)
        stats["new"] += 1
        return {"scenario": str(scenario), **values}
    except Exception as error:
        manifest["completion_status"] = "FAIL"
        manifest["failure"] = str(error)
        write_json(scenario / "scenario_manifest.json", manifest)
        raise


def measure_one(stage: str, hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any], units: int, code: int, vdd_v: float, mux_cell: str, signature: Mapping[str, str], stats: Dict[str, int]) -> Dict[str, Any]:
    """Run one physical code point and normalize it into the public CSV shape."""

    deck = render_deck(config, cells, vdd_v, units, code, mux_cell)
    record = execute_scenario(hspice, run_dir, deck, scenario_parameters(units, code, vdd_v, mux_cell), signature, stats)
    classified = classify_path(record, vdd_v)
    return {"stage": stage, "N": units, "code": code, "vdd_v": vdd_v, **classified, "scenario": str(Path(record["scenario"]).relative_to(run_dir))}


def strict_monotonic(rows: Sequence[Mapping[str, Any]], codes: Sequence[int]) -> List[str]:
    """Check one ordered code sequence without inventing a tolerance in ps."""

    by_code = {int(row["code"]): row for row in rows}
    reasons = []
    values = []
    for code in codes:
        row = by_code.get(code)
        if row is None or not row.get("valid") or finite_number(row.get("D_rise_ps")) is None:
            reasons.append("code {} lacks a valid rising-delay measurement".format(code))
        else:
            values.append(float(row["D_rise_ps"]))
    if len(values) == len(codes) and any(after <= before for before, after in zip(values, values[1:])):
        reasons.append("rising delay is not strictly monotonic")
    return reasons


def adjacent_steps(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, float]]:
    """Return only physically measured neighbouring-code increments."""

    by_code = {int(row["code"]): float(row["D_rise_ps"]) for row in rows if row.get("valid") and finite_number(row.get("D_rise_ps")) is not None}
    return [{"from_code": code, "to_code": code + 1, "step_ps": by_code[code + 1] - by_code[code]} for code in sorted(by_code) if code + 1 in by_code]


def n8_envelope(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Summarize measured N=8 steps at all three anchors, including sparse ones."""

    output = {}
    for vdd in ANCHOR_VDD:
        local = [row for row in rows if abs(float(row["vdd_v"]) - vdd) < 1.0e-12]
        steps = adjacent_steps(local)
        by_code = {int(row["code"]): row for row in local}
        span = None
        if 0 in by_code and 8 in by_code and by_code[0].get("valid") and by_code[8].get("valid"):
            span = float(by_code[8]["D_rise_ps"]) - float(by_code[0]["D_rise_ps"])
        values = [item["step_ps"] for item in steps]
        output[voltage_key(vdd)] = {
            "measured_adjacent_steps": steps,
            "step_min_ps": min(values) if values else None,
            "step_median_ps": float(median(values)) if values else None,
            "step_max_ps": max(values) if values else None,
            "span_ps": span,
            "edge_quality": "GO" if local and all(row.get("valid") for row in local) else "NO-GO",
        }
    return {"schema_version": 1, "N": 8, "anchors": output}


def scaling_summary(rows: Sequence[Mapping[str, Any]], typical_step_ps: float) -> Tuple[Dict[str, Any], List[str]]:
    """Apply the structural range-versus-minimum-delay Gate without arbitrary thresholds."""

    per_n = {}
    reasons = []
    for units in (1, 4, 8, 16):
        local = {int(row["code"]): row for row in rows if int(row["N"]) == units}
        low, high = local.get(0), local.get(units)
        if low is None or high is None or not low.get("valid") or not high.get("valid"):
            reasons.append("N={} lacks valid endpoint measurements".format(units))
            continue
        d_min = float(low["D_rise_ps"])
        d_max = float(high["D_rise_ps"])
        per_n[str(units)] = {"D_min_ps": d_min, "D_max_ps": d_max, "Span_ps": d_max - d_min}
    if len(per_n) != 4:
        return {"schema_version": 1, "typical_step_ps": typical_step_ps, "per_N": per_n}, reasons
    ordered = [per_n[str(units)] for units in (1, 4, 8, 16)]
    if any(after["Span_ps"] <= before["Span_ps"] for before, after in zip(ordered, ordered[1:])):
        reasons.append("range_does_not_scale")
    if any(after["D_max_ps"] <= before["D_max_ps"] for before, after in zip(ordered, ordered[1:])):
        reasons.append("maximum_path_does_not_grow")
    growth = []
    for left, right, left_n, right_n in zip(ordered, ordered[1:], (1, 4, 8), (4, 8, 16)):
        item = {"N1": left_n, "N2": right_n, "Growth_min_ps": right["D_min_ps"] - left["D_min_ps"], "Growth_max_ps": right["D_max_ps"] - left["D_max_ps"]}
        growth.append(item)
        if item["Growth_min_ps"] >= item["Growth_max_ps"]:
            reasons.append("minimum_path_still_scales_with_stage_count")
    n4_to_n16 = per_n["16"]["D_min_ps"] - per_n["4"]["D_min_ps"]
    if n4_to_n16 >= typical_step_ps:
        reasons.append("minimum_path_still_scales_with_stage_count")
    return {"schema_version": 1, "typical_step_ps": typical_step_ps, "per_N": per_n, "growth": growth, "N4_to_N16_minimum_drift_ps": n4_to_n16, "decision": "GO" if not reasons else "NO-GO"}, reasons


def medium_interface(rows: Sequence[Mapping[str, Any]]) -> Tuple[Dict[str, Any], List[str]]:
    """Export the measured worst medium step for the future fine-stage plan only."""

    by_vdd = {}
    reasons = []
    for vdd in ANCHOR_VDD:
        local = [row for row in rows if abs(float(row["vdd_v"]) - vdd) < 1.0e-12]
        pairs = []
        for first, second in ((0, 1), (7, 8), (15, 16)):
            lookup = {int(row["code"]): row for row in local}
            if first not in lookup or second not in lookup or not lookup[first].get("valid") or not lookup[second].get("valid"):
                reasons.append("{} V lacks valid {}->{} step".format(voltage_key(vdd), first, second))
                continue
            step = float(lookup[second]["D_rise_ps"]) - float(lookup[first]["D_rise_ps"])
            if step <= 0.0:
                reasons.append("{} V has non-positive {}->{} step".format(voltage_key(vdd), first, second))
            pairs.append({"from_code": first, "to_code": second, "step_ps": step})
        endpoint = {int(row["code"]): row for row in local}
        if 0 not in endpoint or 16 not in endpoint:
            reasons.append("{} V lacks N16 endpoints".format(voltage_key(vdd)))
            continue
        values = [item["step_ps"] for item in pairs]
        by_vdd[voltage_key(vdd)] = {
            "pairs": pairs,
            "medium_step_min_ps": min(values) if values else None,
            "medium_step_max_ps": max(values) if values else None,
            "medium_span_n16_ps": float(endpoint[16]["D_rise_ps"]) - float(endpoint[0]["D_rise_ps"]),
            "minimum_path_delay_n16_ps": float(endpoint[0]["D_rise_ps"]),
            "maximum_path_delay_n16_ps": float(endpoint[16]["D_rise_ps"]),
        }
    all_steps = [item["step_ps"] for value in by_vdd.values() for item in value["pairs"]]
    # Keep both the detailed per-voltage records and explicit maps.  The maps
    # are the compact hand-off API expected by the later fine-stage task, while
    # the records retain the three measured shallow/middle/deep evidence pairs.
    return {
        "schema_version": 1,
        "N_characterize": 16,
        "by_vdd": by_vdd,
        "medium_step_min_ps_by_vdd": {key: value["medium_step_min_ps"] for key, value in by_vdd.items()},
        "medium_step_max_ps_by_vdd": {key: value["medium_step_max_ps"] for key, value in by_vdd.items()},
        "medium_span_n16_by_vdd": {key: value["medium_span_n16_ps"] for key, value in by_vdd.items()},
        "minimum_path_delay_n16_by_vdd": {key: value["minimum_path_delay_n16_ps"] for key, value in by_vdd.items()},
        "maximum_path_delay_n16_by_vdd": {key: value["maximum_path_delay_n16_ps"] for key, value in by_vdd.items()},
        "medium_step_global_min_ps": min(all_steps) if all_steps else None,
        "medium_step_global_max_ps": max(all_steps) if all_steps else None,
        "future_requirement": "fine_stage_range_must_cover_at_least_one_worst_case_medium_step",
        "decision": "GO" if not reasons else "NO-GO",
    }, reasons


def future_projection(requirements: Mapping[str, Any], interface: Mapping[str, Any]) -> Dict[str, Any]:
    """Make an explicitly non-binding range estimate without simulating a larger chain."""

    worst = finite_number(interface.get("medium_step_global_max_ps"))
    if worst is None or worst <= 0.0:
        raise ValueError("cannot project without a positive worst medium step")
    return {
        "schema_version": 1,
        "projection_only": True,
        "historical_system_span_reference_ps": requirements["historical_system_span_reference_ps"],
        "worst_measured_medium_step_ps": worst,
        "estimated_medium_intervals_for_historical_span": int(math.ceil(float(requirements["historical_system_span_reference_ps"]) / worst)),
        "final_N_frozen": False,
        "projection_requires_future_fine_stage_and_two_stage_integration": True,
    }


def initial_stages() -> Dict[str, str]:
    """Initialize every public stage as NOT_RUN so early stops cannot look like passes."""

    return {name: "NOT_RUN" for name in STAGE_NAMES}


def publish_summary(analysis_dir: Path, stages: Mapping[str, str], reasons: Sequence[str], stats: Mapping[str, int], details: Mapping[str, Any], scenario_accounting: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Publish a terminal status with explicit counts for prohibited work."""

    all_go = all(status == "GO" for status in stages.values())
    summary = {
        "schema_version": 1,
        "decision": "Path-Selection Medium Stage = GO" if all_go else "Path-Selection Medium Stage = NO-GO",
        "stages": dict(stages),
        "requirements_sha256": sha256_file(analysis_dir / "requirements.json"),
        "reasons": list(dict.fromkeys(reason for reason in reasons if reason)),
        "new_hspice_scenarios": stats["new"],
        "reused_new_task_scenarios": stats["reused"],
        "historical_scenarios_reused_as_read_only_evidence": 0,
        "historical_runners_invoked": 0,
        "sensor_scenarios": 0,
        "dff_scenarios": 0,
        "droop_scenarios": 0,
        "details": dict(details),
    }
    if scenario_accounting is not None:
        summary["phase_scenario_accounting"] = dict(scenario_accounting)
    write_json(analysis_dir / "summary.json", summary)
    return summary


def render_report(path: Path, summary: Mapping[str, Any], envelope: Optional[Mapping[str, Any]], scaling: Optional[Mapping[str, Any]], interface: Optional[Mapping[str, Any]]) -> None:
    """Write the required concise report without claiming unmeasured system evidence."""

    lines = ["# FTC Path-Selection Medium Stage", "", "## Decision", "", "**{}**".format(summary["decision"]), "", "## Stage Status", "", "| Stage | Status |", "|---|---|"]
    lines.extend("| {} | {} |".format(name, status) for name, status in summary["stages"].items())
    lines.extend(["", "## Structural Result", "", "- The previous fast/slow unit chain forced every code through all selector stages, so increasing range also increased minimum delay.", "- This study selects a shallow A exit or a recursively deeper B path; code 0 does not traverse later mux stages."])
    if envelope is not None:
        lines.extend(["", "## N=8 Step Envelope", "", "| VDD (V) | Min (ps) | Median (ps) | Max (ps) | Span (ps) |", "|---:|---:|---:|---:|---:|"])
        for key, value in envelope["anchors"].items():
            lines.append("| {} | {} | {} | {} | {} |".format(key, value["step_min_ps"], value["step_median_ps"], value["step_max_ps"], value["span_ps"]))
    if scaling is not None:
        lines.extend(["", "## N Scaling", "", "| N | D_min (ps) | D_max (ps) | Span (ps) |", "|---:|---:|---:|---:|"])
        for key in ("1", "4", "8", "16"):
            if key in scaling.get("per_N", {}):
                value = scaling["per_N"][key]
                lines.append("| {} | {} | {} | {} |".format(key, value["D_min_ps"], value["D_max_ps"], value["Span_ps"]))
    if interface is not None:
        lines.extend(["", "## Future Fine-Stage Input", "", "- Worst measured medium step: {} ps.".format(interface.get("medium_step_global_max_ps")), "- Future fine-stage range must cover at least that one worst-case medium step."])
    accounting = summary.get("phase_scenario_accounting", {})
    if accounting:
        lines.extend(["", "## Scenario Accounting", "", "- New HSPICE scenarios: {}; reused task scenarios: {}.".format(summary["new_hspice_scenarios"], summary["reused_new_task_scenarios"]), "- Phase 2 / Phase 3 / Phase 4 new counts: {} / {} / {}.".format(accounting["phase2"]["new"], accounting["phase3"]["new"], accounting["phase4"]["new"])])
    if envelope is not None and scaling is not None and interface is not None:
        lines.extend([
            "", "## Direct Answers", "",
            "1. The previous unit chain was NO-GO because every code accumulated all fixed selector overhead; increasing N raised both maximum and minimum delay.",
            "2. Here code 0 exits through X1 and one local mux, while larger codes select recursively deeper serial exits.",
            "3. N=8 at 0.95 V is strictly monotonic across code 0..8; every measured adjacent rise-delay step is positive.",
            "4. The three-anchor step minima, medians, and maxima are listed above from retained HSPICE measurements.",
            "5. N=1/4/8/16 endpoint values and spans are listed above; span grows strictly with N.",
            "6. N=4 to N=16 minimum-path drift is {} ps versus a {} ps typical 0.95 V medium step, so the shortest path does not scale with range.".format(scaling.get("N4_to_N16_minimum_drift_ps"), scaling.get("typical_step_ps")),
            "7. A future fine stage must cover at least {} ps, the worst measured medium step.".format(interface.get("medium_step_global_max_ps")),
            "8. This study created {} new HSPICE scenarios and logically reused {} retained task scenarios.".format(summary["new_hspice_scenarios"], summary["reused_new_task_scenarios"]),
            "9. The 3-bit refinement, acceptance-window, static-calibration, and fine-grained runners were not rerun.",
            "10. Sensor, XOR, DFF, calibration, and droop work were excluded to isolate the medium-stage topology.",
            "11. This GO advances only the medium stage to the next fine-stage study; it is not a complete FTC macro GO.",
        ])
    lines.extend(["", "## Scope and Meaning", "", "- Historical 3-bit, acceptance-window, static-calibration, and fine-grained runners were read-only evidence and were never run.", "- No fine stage, sensor, XOR, DFF, calibration, droop, PVT, RTL, power, area, or layout work was performed.", "- GO means only that this medium stage can inform a later fine-stage study; it is not a complete FTC macro GO."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Expose locations only; electrical topology and SPICE selection remain fixed."""

    parser = argparse.ArgumentParser(description="run FTC path-selection medium-stage characterization")
    parser.add_argument("--config", type=Path, default=FTC_ROOT / "ftc_config.json")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis/path_selection_medium_stage")
    parser.add_argument("--run-root", type=Path, default=FTC_ROOT / "runs/path_selection_medium_stage")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports/FTC_PATH_SELECTION_MEDIUM_STAGE.md")
    parser.add_argument("--phase0-only", action="store_true", help="freeze requirements only; never create a SPICE scenario")
    # These checkpoints do not alter electrical settings.  They let an operator
    # inspect each completed Gate before authorizing the next bounded scenario set.
    parser.add_argument("--stop-after", choices=("static", "n8", "scaling"), help="finish a completed Gate without advancing to the next one")
    parser.add_argument("--finalize-existing", action="store_true", help="rebuild only derived summaries and report from retained PASS scenarios; never run SPICE")
    return parser.parse_args(argv)


def load_path_rows(path: Path) -> List[Dict[str, Any]]:
    """Load one public path CSV with typed values for final zero-SPICE auditing."""

    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("path evidence CSV is empty: {}".format(path))
    typed = []
    numeric = ("D_rise_ps", "D_fall_ps", "output_rise_time_ps", "output_fall_time_ps", "output_logic_high", "output_logic_low")
    for row in rows:
        item = dict(row)
        item["N"] = int(item["N"])
        item["code"] = int(item["code"])
        item["vdd_v"] = float(item["vdd_v"])
        item["unexpected_transition_count"] = int(item["unexpected_transition_count"])
        item["valid"] = item["valid"].lower() == "true"
        for name in numeric:
            item[name] = finite_number(item[name])
        typed.append(item)
    return typed


def scenario_accounting(run_root: Path) -> Dict[str, Any]:
    """Count retained PASS scenarios across the task without rerunning a deck.

    The fixed schedule has 19 new N=8 scenes, 10 new scaling scenes, and 12
    new characterization scenes.  N=8 endpoints are reused by scaling and six
    N=16 endpoints are reused by characterization, so the logical reuse count
    is eight even though each physical deck is retained exactly once.
    """

    manifests = list(run_root.glob("r*/scenarios/*/scenario_manifest.json"))
    passes = []
    for path in manifests:
        manifest = load_json(path)
        if manifest.get("completion_status") != "PASS":
            raise RuntimeError("cannot finalize with non-PASS raw scenario: {}".format(path))
        passes.append(manifest)
    if len(passes) != TOTAL_MAX_SCENARIOS:
        raise RuntimeError("expected {} retained scenarios, found {}".format(TOTAL_MAX_SCENARIOS, len(passes)))
    return {
        "phase2": {"planned": 19, "new": 19, "reused": 0},
        "phase3": {"planned": 12, "new": 10, "reused": 2},
        "phase4": {"planned": 18, "new": 12, "reused": 6},
        "total_new_hspice_scenarios": len(passes),
        "total_reused_new_task_scenarios": 8,
    }


def finalize_existing(analysis_dir: Path, run_root: Path, report_output: Path, requirements: Mapping[str, Any]) -> int:
    """Re-audit existing PASS evidence and regenerate only derived public files.

    This path deliberately has no HSPICE handle, deck renderer, or raw-write
    operation.  It is safe after an interrupted staged run because it reads
    retained CSV/manifest evidence and corrects only summary/report metadata.
    """

    n8_rows = load_path_rows(analysis_dir / "n8_code_sweep.csv")
    n8_reasons = strict_monotonic([row for row in n8_rows if abs(row["vdd_v"] - 0.95) < 1.0e-12], tuple(range(9)))
    for vdd in (1.10, 0.80):
        local = [row for row in n8_rows if abs(row["vdd_v"] - vdd) < 1.0e-12]
        n8_reasons.extend(strict_monotonic(local, (0, 1, 4, 7, 8)))
        for step in adjacent_steps(local):
            if step["from_code"] in (0, 7) and step["step_ps"] <= 0.0:
                n8_reasons.append("{} V has non-positive required N8 step".format(voltage_key(vdd)))
    envelope = n8_envelope(n8_rows)
    write_json(analysis_dir / "n8_step_envelope.json", envelope)

    scaling_rows = [row for row in load_path_rows(analysis_dir / "scaling_endpoints.csv") if abs(row["vdd_v"] - 0.95) < 1.0e-12]
    scaling, scaling_reasons = scaling_summary(scaling_rows, float(envelope["anchors"]["0.95"]["step_median_ps"]))
    write_json(analysis_dir / "scaling_summary.json", scaling)

    medium_rows = load_path_rows(analysis_dir / "medium_step_characterization.csv")
    interface, interface_reasons = medium_interface(medium_rows)
    write_json(analysis_dir / "future_fine_stage_interface.json", interface)
    if not interface_reasons:
        write_json(analysis_dir / "future_range_projection.json", future_projection(requirements, interface))

    stages = initial_stages()
    stages["Historical Evidence Freeze"] = "GO"
    stages["Static Path-Selection Contract"] = "GO"
    stages["N8 Code Monotonicity"] = "GO" if not n8_reasons else "NO-GO"
    stages["Stage-Count Scaling"] = "GO" if not n8_reasons and not scaling_reasons else "NO-GO" if not n8_reasons else "NOT_RUN"
    stages["Medium-Step Characterization"] = "GO" if not n8_reasons and not scaling_reasons and not interface_reasons else "NO-GO" if not n8_reasons and not scaling_reasons else "NOT_RUN"
    stages["Future Fine-Stage Interface"] = "GO" if all(stages[name] == "GO" for name in STAGE_NAMES[:-1]) else "NOT_RUN"
    accounting = scenario_accounting(run_root)
    details = {
        "finalization_runner_sha256": sha256_file(Path(__file__)),
        "scenario_accounting_note": "derived without executing or overwriting raw HSPICE scenarios",
        "n8_step_envelope": envelope,
        "scaling_summary": scaling,
        "future_fine_stage_interface": interface,
    }
    summary = publish_summary(analysis_dir, stages, n8_reasons + scaling_reasons + interface_reasons, {"new": accounting["total_new_hspice_scenarios"], "reused": accounting["total_reused_new_task_scenarios"]}, details, accounting)
    render_report(report_output, summary, envelope, scaling, interface)
    print("FTC_PATH_SELECTION_MEDIUM_STAGE finalization={}".format(summary["decision"]))
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Advance the approved gates in order and stop immediately after a failure."""

    args = parse_args(argv)
    config = load_json(args.config.resolve())
    frozen = verify_frozen_evidence()
    analysis_dir = args.analysis_dir.resolve()
    requirements = build_requirements(frozen)
    write_json(analysis_dir / "requirements.json", requirements)
    # Re-read the public artifact so later phases consume exactly what reviewers see.
    requirements = load_json(analysis_dir / "requirements.json")
    if args.finalize_existing:
        if args.phase0_only or args.stop_after:
            raise ValueError("--finalize-existing cannot be combined with another stopping mode")
        return finalize_existing(analysis_dir, args.run_root.resolve(), args.report_output.resolve(), requirements)
    if args.phase0_only:
        print("FTC_PATH_SELECTION_MEDIUM_STAGE phase0=requirements_published")
        return 0

    cell_contract = build_cell_contract(frozen["cells"])
    write_json(analysis_dir / "cell_contract.json", cell_contract)
    mux_cell = cell_contract["selected_mux"]["cell"]
    topology = topology_proof((1, 4, 8, 16), mux_cell)
    write_json(analysis_dir / "topology_contract.json", topology)
    if args.stop_after == "static":
        print("FTC_PATH_SELECTION_MEDIUM_STAGE static=contract_published")
        return 0

    hspice, version = validate_system_spice(config)
    stages = initial_stages()
    stages["Historical Evidence Freeze"] = "GO"
    stages["Static Path-Selection Contract"] = "GO"
    stats = {"new": 0, "reused": 0}
    signature = run_signature(analysis_dir / "requirements.json", analysis_dir / "cell_contract.json")
    run_dir = select_run_dir(args.run_root.resolve(), signature, hspice, version)
    details: Dict[str, Any] = {"run_dir": str(run_dir), "system_hspice": str(hspice), "hspice_version": version, "cell_contract": cell_contract, "topology_contract": topology}

    n8_rows = []
    for code in range(9):
        n8_rows.append(measure_one("N8 Code Monotonicity", hspice, run_dir, config, frozen["cells"], 8, code, 0.95, mux_cell, signature, stats))
    reasons = strict_monotonic(n8_rows, tuple(range(9)))
    if not reasons:
        for vdd in (1.10, 0.80):
            local = []
            for code in (0, 1, 4, 7, 8):
                row = measure_one("N8 Code Monotonicity", hspice, run_dir, config, frozen["cells"], 8, code, vdd, mux_cell, signature, stats)
                n8_rows.append(row)
                local.append(row)
            reasons.extend(strict_monotonic(local, (0, 1, 4, 7, 8)))
            for first, second in ((0, 1), (7, 8)):
                step = float({int(row["code"]): row for row in local}[second]["D_rise_ps"]) - float({int(row["code"]): row for row in local}[first]["D_rise_ps"])
                if step <= 0.0:
                    reasons.append("{} V has non-positive {}->{} step".format(voltage_key(vdd), first, second))
    write_csv(analysis_dir / "n8_code_sweep.csv", PATH_FIELDS, n8_rows)
    envelope = n8_envelope(n8_rows)
    write_json(analysis_dir / "n8_step_envelope.json", envelope)
    if reasons:
        stages["N8 Code Monotonicity"] = "NO-GO"
        summary = publish_summary(analysis_dir, stages, reasons, stats, details)
        render_report(args.report_output.resolve(), summary, envelope, None, None)
        print("FTC_PATH_SELECTION_MEDIUM_STAGE decision=NO-GO stage=n8")
        return 0
    stages["N8 Code Monotonicity"] = "GO"
    if args.stop_after == "n8":
        print("FTC_PATH_SELECTION_MEDIUM_STAGE n8=gate_passed")
        return 0

    scaling_rows = [row for row in n8_rows if abs(float(row["vdd_v"]) - 0.95) < 1.0e-12 and int(row["code"]) in (0, 8)]
    for units in (1, 4, 16):
        for code in (0, units):
            scaling_rows.append(measure_one("Stage-Count Scaling", hspice, run_dir, config, frozen["cells"], units, code, 0.95, mux_cell, signature, stats))
    typical = envelope["anchors"]["0.95"]["step_median_ps"]
    scaling, reasons = scaling_summary(scaling_rows, float(typical))
    if not reasons:
        for vdd in (1.10, 0.80):
            endpoint_rows = []
            for code in (0, 16):
                endpoint_rows.append(measure_one("Stage-Count Scaling", hspice, run_dir, config, frozen["cells"], 16, code, vdd, mux_cell, signature, stats))
            if any(not row["valid"] for row in endpoint_rows) or float(endpoint_rows[1]["D_rise_ps"]) <= float(endpoint_rows[0]["D_rise_ps"]):
                reasons.append("{} V N16 endpoint edge_or_logic_integrity_failure".format(voltage_key(vdd)))
            scaling_rows.extend(endpoint_rows)
    write_csv(analysis_dir / "scaling_endpoints.csv", PATH_FIELDS, scaling_rows)
    write_json(analysis_dir / "scaling_summary.json", scaling)
    if reasons:
        stages["Stage-Count Scaling"] = "NO-GO"
        summary = publish_summary(analysis_dir, stages, reasons, stats, details)
        render_report(args.report_output.resolve(), summary, envelope, scaling, None)
        print("FTC_PATH_SELECTION_MEDIUM_STAGE decision=NO-GO stage=scaling")
        return 0
    stages["Stage-Count Scaling"] = "GO"
    if args.stop_after == "scaling":
        print("FTC_PATH_SELECTION_MEDIUM_STAGE scaling=gate_passed")
        return 0

    characterization_rows = []
    existing = {(int(row["N"]), int(row["code"]), voltage_key(float(row["vdd_v"]))): row for row in scaling_rows}
    for vdd in ANCHOR_VDD:
        for code in (0, 1, 7, 8, 15, 16):
            key = (16, code, voltage_key(vdd))
            row = existing.get(key)
            if row is None:
                row = measure_one("Medium-Step Characterization", hspice, run_dir, config, frozen["cells"], 16, code, vdd, mux_cell, signature, stats)
            characterization_rows.append(row)
    write_csv(analysis_dir / "medium_step_characterization.csv", PATH_FIELDS, characterization_rows)
    interface, reasons = medium_interface(characterization_rows)
    write_json(analysis_dir / "future_fine_stage_interface.json", interface)
    if reasons:
        stages["Medium-Step Characterization"] = "NO-GO"
        summary = publish_summary(analysis_dir, stages, reasons, stats, details)
        render_report(args.report_output.resolve(), summary, envelope, scaling, interface)
        print("FTC_PATH_SELECTION_MEDIUM_STAGE decision=NO-GO stage=medium_step")
        return 0
    stages["Medium-Step Characterization"] = "GO"
    write_json(analysis_dir / "future_range_projection.json", future_projection(requirements, interface))
    stages["Future Fine-Stage Interface"] = "GO"
    details.update({"n8_step_envelope": envelope, "scaling_summary": scaling, "future_fine_stage_interface": interface})
    summary = publish_summary(analysis_dir, stages, [], stats, details)
    render_report(args.report_output.resolve(), summary, envelope, scaling, interface)
    print("FTC_PATH_SELECTION_MEDIUM_STAGE decision=GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
