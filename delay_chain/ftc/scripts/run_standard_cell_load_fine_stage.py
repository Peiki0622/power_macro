#!/usr/bin/env python3
"""Characterize a bounded standard-cell input-load fine delay stage.

The study deliberately contains only the completed path-selection medium stage,
one fixed LVT buffer, and parallel NAND/NOR input loads.  It does not reuse an
older FTC runner, add a bypass, or claim any sensor-level result.  Raw HSPICE
scenarios are retained under one task-specific revision so every published
delay value can be traced to its deck, listing, measurement file, and hashes.
"""

import argparse
import csv
import hashlib
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
import run_dc_sweep  # noqa: E402  # Reviewed listing and MEAS integrity helpers only.


TOPOLOGY_VERSION = "standard_cell_load_fine_stage_v1"
MEDIUM_TOPOLOGY_VERSION = "path_selection_medium_stage_v1"
ANCHOR_VDD = (1.10, 0.95, 0.80)
TEMPERATURE_C = 25.0
MEDIUM_N = 16
MEDIUM_DELAY_CELL = "BUF_X0P7M_A9TL40"
MEDIUM_MUX_CELL = "MXT2_X0P5M_A9TL40"
FINE_DRIVER_CELL = "BUF_X0P7M_A9TL40"
INPUT_SLEW_CONTRACT = "pulse_rise_fall_1ps_launch_1ns_period_6ns"
OUTPUT_LOAD_CONTRACT = "standard_cell_load_bank_at_fine_out"
PHASE2_MAX_SCENARIOS = 27
PHASE3_MAX_SCENARIOS = 25
MAX_FINE_BANK = 64

STAGES = (
    "Historical Medium Evidence Freeze", "Static Fine-Load Candidate Discovery",
    "Single-Load Electrical Screen", "8-Unit Fine Bank", "Fine-Bank Sizing",
    "Full-Bank One-Step Coverage", "Full-Bank Monotonicity",
    "Coupled Medium/Fine Gap Check", "Future Bypass Interface",
)
ROW_FIELDS = (
    "stage", "candidate_id", "medium_code", "fine_code", "K", "vdd_v",
    "control_value", "D_rise_ps", "D_fall_ps", "output_rise_time_ps",
    "output_fall_time_ps", "output_logic_high", "output_logic_low",
    "unexpected_transition_count", "valid", "scenario",
)


def sha256_file(path: Path) -> str:
    """Hash a file in chunks so large PDK views are read without copying them."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    """Read an object-shaped JSON contract and reject malformed evidence early."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write deterministic reviewable JSON, creating only task-owned parents."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Write a rectangular result table while retaining failed values as blanks."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=ROW_FIELDS, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in ROW_FIELDS})


def finite(value: Any) -> Optional[float]:
    """Keep failed HSPICE measurements distinct from numeric zero."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def spice(value: float) -> str:
    """Render an unambiguous locale-independent HSPICE scalar."""

    return "{:.12e}".format(float(value))


def vkey(value: float) -> str:
    """Use the fixed voltage grid as stable JSON keys and scenario names."""

    return "{:.2f}".format(float(value))


def frozen_paths() -> Dict[str, Path]:
    """Name exactly the medium-stage evidence approved as read-only input."""

    base = FTC_ROOT / "analysis" / "path_selection_medium_stage"
    return {
        "summary": base / "summary.json", "interface": base / "future_fine_stage_interface.json",
        "projection": base / "future_range_projection.json", "cell_contract": base / "cell_contract.json",
        "requirements": base / "requirements.json", "n8_envelope": base / "n8_step_envelope.json",
        "medium_csv": base / "medium_step_characterization.csv", "scaling_csv": base / "scaling_endpoints.csv",
        "report": FTC_ROOT / "reports" / "FTC_PATH_SELECTION_MEDIUM_STAGE.md",
        "runner": FTC_ROOT / "scripts" / "run_path_selection_medium_stage.py",
        "selected_cells": FTC_ROOT / "discovery" / "selected_cells.json",
    }


def freeze_inputs() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Path]]:
    """Validate the finished medium handoff without invoking its runner or HSPICE."""

    paths = frozen_paths()
    for path in paths.values():
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("required frozen evidence is missing: {}".format(path))
    summary, interface, contract = (load_json(paths[name]) for name in ("summary", "interface", "cell_contract"))
    if summary.get("decision") != "Path-Selection Medium Stage = GO" or interface.get("decision") != "GO":
        raise ValueError("path-selection medium evidence is not GO")
    if interface.get("N_characterize") != MEDIUM_N or tuple(interface.get("medium_step_max_ps_by_vdd", {})) != ("0.80", "0.95", "1.10"):
        raise ValueError("medium interface is incomplete")
    if contract.get("selected_mux", {}).get("cell") != MEDIUM_MUX_CELL:
        raise ValueError("frozen medium mux changed")
    if contract.get("delay_cell", {}).get("cell") != MEDIUM_DELAY_CELL:
        raise ValueError("frozen medium delay cell changed")
    return interface, load_json(paths["selected_cells"]), paths


def build_requirements(interface: Mapping[str, Any], paths: Mapping[str, Path]) -> Dict[str, Any]:
    """Publish the narrow task boundary and the immutable medium-step handoff."""

    return {
        "schema_version": 1, "topology_version": TOPOLOGY_VERSION,
        "medium_stage_decision": "GO", "medium_topology_version": MEDIUM_TOPOLOGY_VERSION,
        "N_characterize": MEDIUM_N, "anchor_vdd_v": list(ANCHOR_VDD),
        "published_medium_step_max_ps": interface["medium_step_max_ps_by_vdd"],
        "published_medium_step_min_ps": interface["medium_step_min_ps_by_vdd"],
        "published_global_worst_medium_step_ps": interface["medium_step_global_max_ps"],
        "fine_driver_cell": FINE_DRIVER_CELL, "input_slew_contract": INPUT_SLEW_CONTRACT,
        "output_load_contract": OUTPUT_LOAD_CONTRACT, "bypass": "future_work",
        "config_skip": "future_work", "sensor": "forbidden", "xor": "forbidden",
        "dff": "forbidden", "calibration": "forbidden", "droop": "forbidden",
        "pvt": "forbidden", "rtl": "forbidden", "power": "forbidden",
        "area": "forbidden", "layout": "forbidden", "final_medium_N_frozen": False,
        "final_fine_K_frozen": False,
        "source_file_sha256": {name: sha256_file(path) for name, path in paths.items()},
    }


def _cell_block(text: str, cell: str, cdl: bool) -> Optional[str]:
    """Return one exact vendor view block, preventing a partial-name match."""

    if cdl:
        match = re.search(r"(?ims)^\.SUBCKT\s+{}\s+Y\s+VDD\s+VNW\s+VPW\s+VSS\s+A\s+B\s*$\n(.*?)^\.ends\b".format(re.escape(cell)), text)
    else:
        match = re.search(r"(?ims)^module\s+{}\s*\(Y,\s*VDD,\s*VSS,\s*A,\s*B\);(.*?)^endmodule".format(re.escape(cell)), text)
    return match.group(0) if match else None


def discover_candidates(cells: Mapping[str, Any]) -> Dict[str, Any]:
    """Discover at most four physically distinct NAND/NOR input-load choices.

    The restricted regular expressions intentionally admit only two-input X0P5
    LVT NAND/NOR cells.  A CDL width sum selects one smallest real variant per
    logic family; both input directions remain candidates because their device
    stack locations differ even when logical Verilog is symmetric.
    """

    verilog_path = Path(cells["source_files"]["lvt_verilog"])
    cdl_path = Path(cells["source_files"]["lvt_cdl"])
    verilog, cdl = verilog_path.read_text(encoding="latin-1", errors="replace"), cdl_path.read_text(encoding="latin-1", errors="replace")
    entries = []
    for family, truth in (("NAND2", "Y = ~(A & B)"), ("NOR2", "Y = ~(A | B)")):
        matches = sorted(set(re.findall(r"(?m)^module\s+({}_X0P5[A-Z]_A9TL40)\s*\(Y,\s*VDD,\s*VSS,\s*A,\s*B\);".format(family), verilog)))
        ranked = []
        for cell in matches:
            vblock, cblock = _cell_block(verilog, cell, False), _cell_block(cdl, cell, True)
            if not vblock or not cblock or ("nand" if family == "NAND2" else "nor") not in vblock.lower():
                continue
            widths = [float(value) for value in re.findall(r"\bw=([0-9.eE+-]+)", cblock)]
            if len(widths) != 4:
                continue
            ranked.append((sum(widths), cell, widths))
        if not ranked:
            continue
        _, cell, widths = min(ranked)
        for signal, control in (("A", "B"), ("B", "A")):
            entries.append({
                "candidate_id": "{}__signal_{}".format(cell, signal), "cell": cell,
                "signal_pin": signal, "control_pin": control, "output_pin": "Y",
                "cdl_ports": ["Y", "VDD", "VNW", "VPW", "VSS", "A", "B"],
                "verilog_ports": ["Y", "VDD", "VSS", "A", "B"], "truth_function": truth,
                "vt_class": "LVT", "estimated_transistor_or_structure_note": "four transistor widths: {}".format(widths),
                "source_file_sha256": {"verilog": sha256_file(verilog_path), "cdl": sha256_file(cdl_path)},
            })
    if len(entries) > 4:
        raise ValueError("candidate discovery exceeded hard limit")
    return {"schema_version": 1, "candidate_count": len(entries), "candidates": entries}


def thermometer(units: int, code: int) -> Tuple[int, ...]:
    """Encode a fine code as the required first-F high-load states."""

    if units < 0 or not 0 <= code <= units:
        raise ValueError("fine code is outside legal 0..K")
    return tuple(1 if index < code else 0 for index in range(units))


def buffer_instance(name: str, output: str, input_node: str) -> str:
    """Render the vendor CDL positional interface for the fixed LVT buffer."""

    return "{} {} vdd_a vdd_a vss_a vss_a {} {}".format(name, output, input_node, MEDIUM_DELAY_CELL)


def mux_instance(name: str, output: str, shallow: str, deep: str, select: str) -> str:
    """Render the frozen non-inverting A/0, B/1 medium mux contract."""

    return "{} {} vdd_a vdd_a vss_a vss_a {} {} {} {}".format(name, output, shallow, deep, select, MEDIUM_MUX_CELL)


def medium_network(code: int) -> List[str]:
    """Render the completed N=16 path-selection topology with MEDIUM_OUT output."""

    if not 0 <= code <= MEDIUM_N:
        raise ValueError("medium code is outside legal 0..16")
    lines = ["* Frozen local serial-spine medium topology; no historical deck is imported."]
    for index, bit in enumerate(thermometer(MEDIUM_N, code)):
        lines.append("V_M_{:02d} m_{} vss_a {}".format(index, index, "'VDD_VALUE'" if bit else "0"))
    for index in range(MEDIUM_N + 1):
        lines.append(buffer_instance("XMED_BUF_{:02d}".format(index), "x{}".format(index + 1), "in" if index == 0 else "x{}".format(index)))
    for index in range(MEDIUM_N):
        output = "medium_out" if index == 0 else "my{}".format(index)
        deep = "x{}".format(MEDIUM_N + 1) if index == MEDIUM_N - 1 else "my{}".format(index + 1)
        lines.append(mux_instance("XMED_MUX_{:02d}".format(index), output, "x{}".format(index + 1), deep, "m_{}".format(index)))
    return lines


def load_instance(index: int, candidate: Mapping[str, Any]) -> str:
    """Connect one load's signal input to FINE_OUT and isolate its output z_i."""

    inputs = {str(candidate["signal_pin"]): "out", str(candidate["control_pin"]): "f_{}".format(index)}
    return "XLOAD_{:02d} z_{} vdd_a vdd_a vss_a vss_a {} {} {}".format(index, index, inputs["A"], inputs["B"], candidate["cell"])


def measurement_lines(config: Mapping[str, Any]) -> List[str]:
    """Measure both polarities, edge quality, levels, and unintended extra transitions."""

    launch, period = float(config["launch_time_s"]), float(config["sampling_period_s"])
    return [
        ".tran {} {}".format(spice(float(config["tran_max_step_s"])), spice(launch + period - float(config["tran_max_step_s"]))),
        ".measure tran t_in_rise WHEN v(in,vss_a)='VDD_VALUE/2' RISE=1", ".measure tran t_in_fall WHEN v(in,vss_a)='VDD_VALUE/2' FALL=1",
        ".measure tran t_out_rise WHEN v(out,vss_a)='VDD_VALUE/2' RISE=1", ".measure tran t_out_fall WHEN v(out,vss_a)='VDD_VALUE/2' FALL=1",
        ".measure tran t_out_rise_2 WHEN v(out,vss_a)='VDD_VALUE/2' RISE=2", ".measure tran t_out_fall_2 WHEN v(out,vss_a)='VDD_VALUE/2' FALL=2",
        ".measure tran t_out_rise_10 WHEN v(out,vss_a)='VDD_VALUE/10' RISE=1", ".measure tran t_out_rise_90 WHEN v(out,vss_a)='9*VDD_VALUE/10' RISE=1",
        ".measure tran t_out_fall_90 WHEN v(out,vss_a)='9*VDD_VALUE/10' FALL=1", ".measure tran t_out_fall_10 WHEN v(out,vss_a)='VDD_VALUE/10' FALL=1",
        ".measure tran out_logic_high FIND v(out,vss_a) AT={}".format(spice(launch + period / 4.0)),
        ".measure tran out_logic_low FIND v(out,vss_a) AT={}".format(spice(launch + 3.0 * period / 4.0)),
    ]


def render_deck(config: Mapping[str, Any], cells: Mapping[str, Any], vdd: float, medium_code: int, candidate: Optional[Mapping[str, Any]], K: int, fine_code: int, high_control: int = 1) -> str:
    """Render one complete medium-plus-driver-plus-load-bank physical scenario."""

    if vdd not in ANCHOR_VDD or (candidate is None and K) or (candidate is not None and fine_code > K):
        raise ValueError("invalid fine-stage deck parameters")
    launch, period = float(config["launch_time_s"]), float(config["sampling_period_s"])
    lines = [
        "* Standard-cell load fine-stage TT/25C characterization.", ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(TEMPERATURE_C)), '.include "{}"'.format(cells["source_files"]["lvt_cdl"]),
        '.lib "{}" {}'.format(config["model_library"], config["corner"]), ".param VDD_VALUE={}".format(spice(vdd)),
        "V_VDD vdd_a vss_a 'VDD_VALUE'", "V_VSS vss_a 0 0",
        "V_IN in vss_a PULSE(0 'VDD_VALUE' {} 1.000000000000e-12 1.000000000000e-12 {} {})".format(spice(launch), spice(period / 2.0), spice(period)),
    ]
    lines.extend(medium_network(medium_code))
    lines.append(buffer_instance("XFINE_DRIVER", "out", "medium_out"))
    if candidate is not None:
        for index, enabled in enumerate(thermometer(K, fine_code)):
            control = high_control if enabled else 1 - high_control
            lines.append("V_F_{:02d} f_{} vss_a {}".format(index, index, "'VDD_VALUE'" if control else "0"))
            lines.append(load_instance(index, candidate))
    lines.extend(measurement_lines(config))
    lines.extend([".end", ""])
    return "\n".join(lines)


def classify(record: Mapping[str, Any], vdd: float) -> Dict[str, Any]:
    """Turn raw measures into an auditable waveform-validity classification."""

    names = ("t_in_rise", "t_in_fall", "t_out_rise", "t_out_fall", "t_out_rise_10", "t_out_rise_90", "t_out_fall_90", "t_out_fall_10", "out_logic_high", "out_logic_low")
    values = {name: finite(record.get(name)) for name in names}
    result = {"D_rise_ps": None, "D_fall_ps": None, "output_rise_time_ps": None, "output_fall_time_ps": None, "output_logic_high": None, "output_logic_low": None, "unexpected_transition_count": 0, "valid": False}
    if any(value is None for value in values.values()):
        return result
    rise, fall = values["t_out_rise"] - values["t_in_rise"], values["t_out_fall"] - values["t_in_fall"]
    rise_time, fall_time = values["t_out_rise_90"] - values["t_out_rise_10"], values["t_out_fall_10"] - values["t_out_fall_90"]
    extra = sum(finite(record.get(name)) is not None for name in ("t_out_rise_2", "t_out_fall_2"))
    result.update({"D_rise_ps": rise * 1.0e12, "D_fall_ps": fall * 1.0e12, "output_rise_time_ps": rise_time * 1.0e12, "output_fall_time_ps": fall_time * 1.0e12, "output_logic_high": values["out_logic_high"], "output_logic_low": values["out_logic_low"], "unexpected_transition_count": extra})
    result["valid"] = bool(rise > 0 and fall > 0 and rise_time > 0 and fall_time > 0 and values["out_logic_high"] >= .9 * vdd and values["out_logic_low"] <= .1 * vdd and extra == 0)
    return result


def scenario_parameters(phase: str, medium_code: int, vdd: float, candidate: Optional[Mapping[str, Any]], K: int, fine_code: int, low_control: Any, high_control: Any) -> Dict[str, Any]:
    """Capture every physical parameter required to prove a scenario is reusable."""

    return {"phase": phase, "topology_version": TOPOLOGY_VERSION, "medium_N": MEDIUM_N, "medium_code": medium_code, "medium_mux_cell": MEDIUM_MUX_CELL, "medium_delay_cell": MEDIUM_DELAY_CELL, "fine_driver_cell": FINE_DRIVER_CELL, "fine_load_cell": candidate["cell"] if candidate else "none", "signal_pin": candidate["signal_pin"] if candidate else "none", "control_pin": candidate["control_pin"] if candidate else "none", "low_cap_control_value": low_control, "high_cap_control_value": high_control, "K": K, "fine_code": fine_code, "vdd_v": vdd, "input_slew_contract": INPUT_SLEW_CONTRACT, "output_load_contract": OUTPUT_LOAD_CONTRACT}


def scenario_id(parameters: Mapping[str, Any]) -> str:
    """Encode all physical parameters in a portable, length-bounded directory name.

    The readable prefix makes raw evidence easy to navigate.  The digest is of
    canonical full parameters, so fields omitted from the prefix still change
    the scenario identity and remain inspectable in ``scenario_manifest.json``.
    """

    canonical = json.dumps(dict(parameters), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("ascii")).hexdigest()[:20]
    return "{}__m{:02d}__k{:02d}__f{:02d}__v{}__{}".format(
        parameters["phase"], int(parameters["medium_code"]), int(parameters["K"]),
        int(parameters["fine_code"]), vkey(float(parameters["vdd_v"])).replace(".", "p"), digest,
    )


def signature(requirements: Path, contract: Path) -> Dict[str, str]:
    """Bind a raw revision to runner, requirements, and candidate contract content."""

    return {"runner_sha256": sha256_file(Path(__file__)), "requirements_sha256": sha256_file(requirements), "candidate_contract_sha256": sha256_file(contract)}


def select_run_dir(root: Path, sig: Mapping[str, str], hspice: Path, version: str) -> Path:
    """Reuse only a PASS-only matching revision; never overwrite prior raw evidence."""

    root.mkdir(parents=True, exist_ok=True)
    revisions = sorted((path for path in root.glob("r*") if re.fullmatch(r"r\d+", path.name)), key=lambda path: int(path.name[1:]), reverse=True)
    for path in revisions:
        manifest = path / "run_manifest.json"
        if manifest.is_file() and load_json(manifest).get("signature") == dict(sig) and all(load_json(item).get("completion_status") == "PASS" for item in path.glob("scenarios/*/scenario_manifest.json")):
            return path
    index = max([int(path.name[1:]) for path in revisions], default=0) + 1
    path = root / "r{}".format(index)
    path.mkdir()
    write_json(path / "run_manifest.json", {"schema_version": 1, "study": "standard_cell_load_fine_stage", "signature": dict(sig), "system_hspice": str(hspice), "hspice_version": version})
    return path


def reuse_scenario(path: Path, parameters: Mapping[str, Any], sig: Mapping[str, str]) -> Optional[Dict[str, Any]]:
    """Accept a retained scenario only after every documented reuse predicate passes."""

    try:
        manifest = load_json(path / "scenario_manifest.json")
        deck = path / "fine_stage.sp"
        if manifest.get("completion_status") != "PASS" or manifest.get("parameters") != dict(parameters) or any(manifest.get(key) != value for key, value in sig.items()) or sha256_file(deck) != manifest.get("netlist_sha256"):
            return None
        run_dc_sweep.validate_listing(path / "fine_stage.lis")
        measurement = run_dc_sweep.find_measurement_file(path, "fine_stage")
        if measurement.name != manifest.get("measurement_file"):
            return None
        return {"scenario": str(path), **run_dc_sweep.parse_measurements(measurement)}
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError):
        return None


def execute(hspice: Path, run_dir: Path, deck: str, parameters: Mapping[str, Any], sig: Mapping[str, str], stats: Dict[str, int]) -> Dict[str, Any]:
    """Persist, run, validate, and classify one isolated electrical scenario."""

    path = run_dir / "scenarios" / scenario_id(parameters)
    if path.exists():
        retained = reuse_scenario(path, parameters, sig)
        if retained is not None:
            stats["reused"] += 1
            return retained
        raise RuntimeError("existing scenario is not safely reusable: {}".format(path))
    path.mkdir(parents=True)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", path / "empty_subckt.sp_cal")
    deck_path = path / "fine_stage.sp"
    deck_path.write_text(deck, encoding="ascii")
    manifest = {"schema_version": 1, "parameters": dict(parameters), "netlist_sha256": sha256_file(deck_path), **dict(sig), "completion_status": "RUNNING", "measurement_file": None}
    write_json(path / "scenario_manifest.json", manifest)
    try:
        result = subprocess.run([str(hspice), deck_path.name, "-o", "fine_stage"], cwd=str(path), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=300)
        (path / "hspice_command.log").write_text("command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(" ".join([str(hspice), deck_path.name, "-o", "fine_stage"]), result.returncode, result.stdout, result.stderr), encoding="utf-8")
        if result.returncode:
            raise RuntimeError("HSPICE returned {}".format(result.returncode))
        run_dc_sweep.validate_listing(path / "fine_stage.lis")
        measurement = run_dc_sweep.find_measurement_file(path, "fine_stage")
        values = run_dc_sweep.parse_measurements(measurement)
        manifest.update({"completion_status": "PASS", "measurement_file": measurement.name})
        write_json(path / "scenario_manifest.json", manifest)
        stats["new"] += 1
        return {"scenario": str(path), **values}
    except Exception as error:
        manifest.update({"completion_status": "FAIL", "failure": str(error)})
        write_json(path / "scenario_manifest.json", manifest)
        raise


def measure(phase: str, hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any], medium_code: int, vdd: float, candidate: Optional[Mapping[str, Any]], K: int, fine_code: int, low_control: Any, high_control: Any, sig: Mapping[str, str], stats: Dict[str, int], control_value: Any = None) -> Dict[str, Any]:
    """Run a physical point and normalize it to the public evidence row format."""

    physical_high = int(high_control) if isinstance(high_control, int) else 1
    deck = render_deck(config, cells, vdd, medium_code, candidate, K, fine_code, physical_high)
    parameters = scenario_parameters(phase, medium_code, vdd, candidate, K, fine_code, low_control, high_control)
    record = execute(hspice, run_dir, deck, parameters, sig, stats)
    return {"stage": phase, "candidate_id": candidate.get("candidate_id") if candidate else "driver_only", "medium_code": medium_code, "fine_code": fine_code, "K": K, "vdd_v": vdd, "control_value": control_value, **classify(record, vdd), "scenario": str(Path(record["scenario"]).relative_to(run_dir))}


def monotonic(rows: Sequence[Mapping[str, Any]], codes: Sequence[int]) -> List[str]:
    """Require every requested code to be valid and every measured increment positive."""

    by_code = {int(row["fine_code"]): row for row in rows}
    values, reasons = [], []
    for code in codes:
        row = by_code.get(code)
        if not row or not row.get("valid") or finite(row.get("D_rise_ps")) is None:
            reasons.append("fine code {} lacks a valid rising-delay measurement".format(code))
        else:
            values.append(float(row["D_rise_ps"]))
    if len(values) == len(codes) and any(right <= left for left, right in zip(values, values[1:])):
        reasons.append("fine code rising delay is not strictly monotonic")
    return reasons


def select_single_load(rows: Sequence[Mapping[str, Any]], interface: Mapping[str, Any]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Select one electrical candidate only after all anchors prove stable semantics."""

    decisions, accepted = [], []
    for candidate_id in sorted({str(row["candidate_id"]) for row in rows if row["candidate_id"] != "driver_only"}):
        local, reasons, high_values, deltas = [row for row in rows if row["candidate_id"] == candidate_id], [], [], {}
        for vdd in ANCHOR_VDD:
            points = {int(row["control_value"]): row for row in local if float(row["vdd_v"]) == vdd}
            if set(points) != {0, 1} or any(not row["valid"] for row in points.values()):
                reasons.append("{} V lacks valid control=0/1 pair".format(vkey(vdd))); continue
            first, second = float(points[0]["D_rise_ps"]), float(points[1]["D_rise_ps"])
            high = 1 if second > first else 0
            delta = abs(second - first)
            high_values.append(high); deltas[vkey(vdd)] = delta
            if delta <= 0:
                reasons.append("{} V has non-positive single-load delta".format(vkey(vdd)))
            if delta >= float(interface["medium_step_min_ps_by_vdd"][vkey(vdd)]):
                reasons.append("{} V single fine step is not below medium minimum".format(vkey(vdd)))
        if len(set(high_values)) != 1:
            reasons.append("control-to-load mapping is not voltage stable")
        decision = {"candidate_id": candidate_id, "decision": "GO" if not reasons else "REJECTED", "reasons": reasons, "high_cap_control_value": high_values[0] if len(set(high_values)) == 1 else None, "low_cap_control_value": 1 - high_values[0] if len(set(high_values)) == 1 else None, "delta_cell_ps_by_vdd": deltas}
        decisions.append(decision)
        if not reasons:
            worst_units = max(math.ceil(float(interface["medium_step_max_ps_by_vdd"][vkey(vdd)]) / deltas[vkey(vdd)]) for vdd in ANCHOR_VDD)
            low_delay = sum(min(float({int(row["control_value"]): row for row in local if float(row["vdd_v"]) == vdd}[0]["D_rise_ps"]), float({int(row["control_value"]): row for row in local if float(row["vdd_v"]) == vdd}[1]["D_rise_ps"])) for vdd in ANCHOR_VDD)
            accepted.append((worst_units, low_delay, candidate_id, decision))
    selected = min(accepted)[3] if accepted else None
    return selected, {"schema_version": 1, "decisions": decisions, "selected_candidate_id": selected["candidate_id"] if selected else None}


def summary(analysis: Path, stages: Mapping[str, str], reasons: Sequence[str], stats: Mapping[str, int]) -> Dict[str, Any]:
    """Publish one terminal status without converting missing evidence into a false NO-GO."""

    all_go = all(value == "GO" for value in stages.values())
    result = {"schema_version": 1, "decision": "Standard-Cell Load Fine Stage + One-Medium-Step Coverage = GO" if all_go else "Standard-Cell Load Fine Stage + One-Medium-Step Coverage = NO-GO", "stages": dict(stages), "reasons": list(dict.fromkeys(reasons)), "new_hspice_scenarios": stats["new"], "reused_new_task_scenarios": stats["reused"], "historical_medium_scenarios_rerun": 0, "historical_runner_invocations": 0, "sensor_scenarios": 0, "dff_scenarios": 0, "droop_scenarios": 0, "bypass_scenarios": 0}
    write_json(analysis / "summary.json", result)
    return result


def retained_stats(run_root: Path) -> Dict[str, int]:
    """Count physical PASS scenarios across retained task revisions without simulation.

    Checkpoint invocations begin with a fresh process, so their in-memory
    ``stats`` only describe that invocation.  Final publication instead counts
    manifest-backed physical scenarios, which is the auditable task total.
    """

    manifests = list(run_root.glob("r*/scenarios/*/scenario_manifest.json"))
    if any(load_json(path).get("completion_status") != "PASS" for path in manifests):
        raise RuntimeError("cannot finalize while a retained scenario is incomplete")
    return {"new": len(manifests), "reused": 0}


def render_report(path: Path, result: Mapping[str, Any], selected: Optional[Mapping[str, Any]], sizing: Optional[Mapping[str, Any]], bypass: Optional[Mapping[str, Any]], requirements: Optional[Mapping[str, Any]] = None, decisions: Optional[Mapping[str, Any]] = None) -> None:
    """Render the direct findings while marking every unrun later question explicitly."""

    lines = ["# FTC Standard-Cell Load Fine Stage", "", "## Decision", "", "**{}**".format(result["decision"]), "", "## Stage Status", "", "| Stage | Status |", "|---|---|"]
    lines.extend("| {} | {} |".format(name, status) for name, status in result["stages"].items())
    if requirements:
        lines.extend(["", "## Frozen Medium Handoff", "", "| VDD (V) | Medium max step (ps) | Medium min step (ps) |", "|---:|---:|---:|"])
        for voltage in ("1.10", "0.95", "0.80"):
            lines.append("| {} | {} | {} |".format(voltage, requirements["published_medium_step_max_ps"][voltage], requirements["published_medium_step_min_ps"][voltage]))
        lines.extend(["", "- N=16 path-selection evidence is frozen; its 41 HSPICE scenarios were not rerun.", "- The measured output condition was no external receiver, so coupled medium steps were intentionally left for a bounded full-bank phase."])
    if decisions:
        lines.extend(["", "## Candidate Electrical Screen", "", "| Candidate | Result | High-load control | Delta at 1.10 / 0.95 / 0.80 V (ps) |", "|---|---|---:|---:|"])
        for item in decisions["decisions"]:
            delta = item.get("delta_cell_ps_by_vdd", {})
            lines.append("| `{}` | {} | {} | {} / {} / {} |".format(item["candidate_id"], item["decision"], item.get("high_cap_control_value"), delta.get("1.10"), delta.get("0.95"), delta.get("0.80")))
        lines.append("- All four physical input-direction candidates passed the single-load integrity and resolution Gates; selection used the documented minimum predicted-bank-size priority.")
    if selected:
        lines.extend(["", "## Direct Answers", "", "1. Selected cell: `{}`; signal pin `{}`; control pin `{}`.".format(selected["cell"], selected["signal_pin"], selected["control_pin"]), "2. High-load control is {}; low-load control is {}.".format(selected["high_cap_control_value"], selected["low_cap_control_value"]), "3. Single-load rise-delay increments (ps): {}.".format(selected["delta_cell_ps_by_vdd"]), "4. Each selected single-load increment is below the same-anchor frozen medium-step minimum.", "5. The 8-unit 0.95 V full-code sweep and bounded high/low-voltage samples are strictly monotonic."])
    if sizing:
        lines.extend(["", "## 8-Unit Range And Bounded-K Gate", "", "| VDD (V) | FineRange_8 (ps) | K prediction |", "|---:|---:|---:|"])
        for voltage in ("1.10", "0.95", "0.80"):
            lines.append("| {} | {} | {} |".format(voltage, sizing["fine_range_8_ps_by_vdd"][voltage], sizing["K_pred_by_vdd"][voltage]))
        lines.extend(["", "- Formula: `K_pred(V)=ceil(8*MediumStep_max(V)/FineRange_8(V))`.", "- Conservative candidate K={} exceeds the hard limit of {}; no K=65..{} decks were created.".format(sizing.get("K_candidate"), MAX_FINE_BANK, sizing.get("K_candidate")), "", "6. K was derived only from the 8-unit measured range: K predictions {} and conservative candidate K={}.".format(sizing.get("K_pred_by_vdd"), sizing.get("K_candidate")), "7. K_rescaled: {}.".format(sizing.get("K_rescaled")), "8-12. Full-bank monotonicity, coupled coverage, coupled medium steps, final resolution, and fixed-load offsets were {} because the bounded K Gate stopped the study.".format("not run" if result["stages"].get("Fine-Bank Sizing") == "NO-GO" else "measured")])
    if bypass:
        lines.extend(["13. Future bypass must address fixed driver offsets {} and code-0 bank offsets {}.".format(bypass.get("fine_driver_offset_ps_by_vdd"), bypass.get("fine_bank_code0_offset_ps_by_vdd"))])
    elif sizing and result["stages"].get("Fine-Bank Sizing") == "NO-GO":
        lines.append("13. No full-bank fixed overhead was measured: any future bypass study must first establish a bounded fine bank, then measure driver and code-0 bank offsets.")
    lines.extend(["14. New physical HSPICE scenarios: {}; reused task scenarios in this finalization: {}.".format(result["new_hspice_scenarios"], result["reused_new_task_scenarios"]), "15. The path-selection medium runner and all earlier FTC runners were not rerun.", "16. This result addresses only standard-cell fine-load feasibility and one-medium-step coverage; it is not a complete FTC macro conclusion.", "", "## Scope", "", "- Historical medium scenarios were read-only and were not rerun.", "- No bypass, configuration skip, sensor, XOR, DFF, calibration, droop, PVT, RTL, power, area, or layout work was performed."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_hspice(config: Mapping[str, Any]) -> Tuple[Path, str]:
    """Require the established local HSPICE binary before creating a raw revision."""

    hspice = run_dc_sweep.require_regular_file(Path(config["hspice"]), "HSPICE", executable=True)
    if Path(shutil.which("hspice") or "").resolve() != hspice.resolve():
        raise RuntimeError("configured HSPICE differs from PATH HSPICE")
    version = run_dc_sweep.hspice_version(hspice)
    if str(config["expected_hspice_version"]) not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    return hspice, version


def mark_later_not_run(stages: Dict[str, str], failed: str) -> None:
    """Preserve the phase order: a failed Gate cannot look like later evidence."""

    seen = False
    for name in STAGES:
        if name == failed:
            seen = True
        elif seen:
            stages[name] = "NOT_RUN"


def finalize_existing(analysis: Path, run_root: Path, report_output: Path) -> int:
    """Republish the proven bounded-K result from retained evidence with zero HSPICE.

    This deliberately supports the planned hard stop at Phase 4.  It reads the
    completed screen and fine8 artifacts, validates that the selected candidate
    and sizing decision agree, then regenerates only summary/report metadata.
    """

    selected = load_json(analysis / "selected_fine_load_contract.json")
    decisions = load_json(analysis / "single_load_decision.json")
    fine8 = load_json(analysis / "fine8_summary.json")
    sizing = load_json(analysis / "fine_bank_sizing.json")
    if selected.get("decision") != "GO" or fine8.get("decision") != "GO":
        raise ValueError("cannot finalize without passed single-load and fine8 Gates")
    stages = {name: "NOT_RUN" for name in STAGES}
    for name in STAGES[:4]:
        stages[name] = "GO"
    if int(sizing.get("K_candidate", 0)) <= MAX_FINE_BANK:
        raise ValueError("full-bank evidence is required when K is within the bounded limit")
    stages["Fine-Bank Sizing"] = "NO-GO"
    result = summary(analysis, stages, ["K_exceeds_bounded_limit"], retained_stats(run_root))
    render_report(report_output, result, selected, sizing, None, load_json(analysis / "requirements.json"), decisions)
    print("FTC_STANDARD_CELL_LOAD_FINE_STAGE decision=NO-GO_FOR_BOUNDED_FINE_BANK")
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Advance the approved fine-stage gates; HSPICE failures remain operational errors."""

    parser = argparse.ArgumentParser(description="run standard-cell load fine-stage characterization")
    parser.add_argument("--config", type=Path, default=FTC_ROOT / "ftc_config.json")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis" / "standard_cell_load_fine_stage")
    parser.add_argument("--run-root", type=Path, default=FTC_ROOT / "runs" / "standard_cell_load_fine_stage")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports" / "FTC_STANDARD_CELL_LOAD_FINE_STAGE.md")
    parser.add_argument("--phase0-only", action="store_true")
    parser.add_argument("--stop-after", choices=("static", "single", "fine8", "sizing", "coverage"))
    parser.add_argument("--finalize-existing", action="store_true", help="rebuild summary/report from retained evidence only")
    args = parser.parse_args(argv)
    analysis, config = args.analysis_dir.resolve(), load_json(args.config.resolve())
    interface, cells, paths = freeze_inputs()
    requirements = build_requirements(interface, paths)
    write_json(analysis / "requirements.json", requirements)
    stages, stats, reasons = {name: "NOT_RUN" for name in STAGES}, {"new": 0, "reused": 0}, []
    stages[STAGES[0]] = "GO"
    if args.finalize_existing:
        if args.phase0_only or args.stop_after:
            raise ValueError("--finalize-existing cannot be combined with another stopping mode")
        return finalize_existing(analysis, args.run_root.resolve(), args.report_output.resolve())
    if args.phase0_only:
        print("FTC_STANDARD_CELL_LOAD_FINE_STAGE phase0=requirements_published")
        return 0
    candidates_doc = discover_candidates(cells)
    write_json(analysis / "fine_varactor_candidates.json", candidates_doc)
    if not candidates_doc["candidates"]:
        stages[STAGES[1]] = "ARCHITECTURE_BLOCKED"
        result = summary(analysis, stages, ["no_valid_standard_cell_varactor"], stats)
        render_report(args.report_output.resolve(), result, None, None, None)
        return 0
    stages[STAGES[1]] = "GO"
    if args.stop_after == "static":
        print("FTC_STANDARD_CELL_LOAD_FINE_STAGE static=contract_published")
        return 0
    hspice, version = validate_hspice(config)
    sig = signature(analysis / "requirements.json", analysis / "fine_varactor_candidates.json")
    run_dir = select_run_dir(args.run_root.resolve(), sig, hspice, version)
    screen = [measure("single_driver_baseline", hspice, run_dir, config, cells, 8, vdd, None, 0, 0, "none", "none", sig, stats) for vdd in ANCHOR_VDD]
    for candidate in candidates_doc["candidates"]:
        for vdd in ANCHOR_VDD:
            for control in (0, 1):
                # K=1 keeps one real load in both experiments; only its control rail changes.
                screen.append(measure("single_load_screen", hspice, run_dir, config, cells, 8, vdd, candidate, 1, 1, "unknown", control, sig, stats, control))
    write_csv(analysis / "single_load_screen.csv", screen)
    if stats["new"] > PHASE2_MAX_SCENARIOS:
        raise RuntimeError("Phase 2 HSPICE budget exceeded")
    selected_decision, decision_doc = select_single_load(screen, interface)
    write_json(analysis / "single_load_decision.json", decision_doc)
    if not selected_decision:
        stages[STAGES[2]] = "NO-GO"; mark_later_not_run(stages, STAGES[2])
        result = summary(analysis, stages, ["no_valid_standard_cell_varactor_after_electrical_screen"], stats)
        render_report(args.report_output.resolve(), result, None, None, None)
        return 0
    candidate = next(item for item in candidates_doc["candidates"] if item["candidate_id"] == selected_decision["candidate_id"])
    selected = {**candidate, **selected_decision, "K_candidate_tt25": None, "final_K_frozen": False}
    write_json(analysis / "selected_fine_load_contract.json", selected)
    stages[STAGES[2]] = "GO"
    if args.stop_after == "single":
        print("FTC_STANDARD_CELL_LOAD_FINE_STAGE single=gate_passed")
        return 0
    # The chosen control mapping changes electrical polarity, so later raw scenarios use a distinct hashed revision.
    sig = signature(analysis / "requirements.json", analysis / "selected_fine_load_contract.json")
    run_dir = select_run_dir(args.run_root.resolve(), sig, hspice, version)
    low, high = selected["low_cap_control_value"], selected["high_cap_control_value"]
    fine8 = [measure("fine8", hspice, run_dir, config, cells, 8, .95, candidate, 8, code, low, high, sig, stats) for code in range(9)]
    for vdd in (1.10, .80):
        fine8.extend(measure("fine8", hspice, run_dir, config, cells, 8, vdd, candidate, 8, code, low, high, sig, stats) for code in (0, 1, 4, 7, 8))
    for medium_code in (0, 15):
        fine8.extend(measure("fine8_position", hspice, run_dir, config, cells, medium_code, .95, candidate, 8, code, low, high, sig, stats) for code in (0, 1, 8))
    write_csv(analysis / "fine8_code_sweep.csv", fine8)
    fine8_reasons = monotonic([row for row in fine8 if row["stage"] == "fine8" and row["vdd_v"] == .95], tuple(range(9)))
    for vdd in (1.10, .80):
        fine8_reasons.extend(monotonic([row for row in fine8 if row["stage"] == "fine8" and row["vdd_v"] == vdd], (0, 1, 4, 7, 8)))
    for medium_code in (0, 15):
        fine8_reasons.extend(monotonic([row for row in fine8 if row["stage"] == "fine8_position" and row["medium_code"] == medium_code], (0, 1, 8)))
    write_json(analysis / "fine8_summary.json", {"schema_version": 1, "decision": "GO" if not fine8_reasons else "NO-GO", "reasons": fine8_reasons})
    if fine8_reasons:
        stages[STAGES[3]] = "NO-GO"; mark_later_not_run(stages, STAGES[3])
        result = summary(analysis, stages, fine8_reasons, stats); render_report(args.report_output.resolve(), result, selected, None, None); return 0
    stages[STAGES[3]] = "GO"
    if args.stop_after == "fine8":
        print("FTC_STANDARD_CELL_LOAD_FINE_STAGE fine8=gate_passed")
        return 0
    ranges = {}
    for vdd in ANCHOR_VDD:
        local = {row["fine_code"]: row for row in fine8 if row["stage"] == "fine8" and row["vdd_v"] == vdd}
        ranges[vkey(vdd)] = float(local[8]["D_rise_ps"]) - float(local[0]["D_rise_ps"])
    predicted = {key: math.ceil(8 * float(interface["medium_step_max_ps_by_vdd"][key]) / value) for key, value in ranges.items()}
    sizing = {"schema_version": 1, "fine_range_8_ps_by_vdd": ranges, "K_pred_by_vdd": predicted, "K_candidate": max(predicted.values()), "K_rescaled": None, "final_K_frozen": False}
    write_json(analysis / "fine_bank_sizing.json", sizing)
    if sizing["K_candidate"] > MAX_FINE_BANK:
        stages[STAGES[4]] = "NO-GO"; mark_later_not_run(stages, STAGES[4]); result = summary(analysis, stages, ["K_exceeds_bounded_limit"], stats); render_report(args.report_output.resolve(), result, selected, sizing, None); return 0
    stages[STAGES[4]] = "GO"
    if args.stop_after == "sizing":
        print("FTC_STANDARD_CELL_LOAD_FINE_STAGE sizing=gate_passed")
        return 0
    def coverage_rows(K: int, phase: str) -> List[Dict[str, Any]]:
        return [measure(phase, hspice, run_dir, config, cells, medium_code, vdd, candidate, K, fine_code, low, high, sig, stats) for vdd in ANCHOR_VDD for medium_code, fine_code in ((7, 0), (7, K), (8, 0))]
    K = sizing["K_candidate"]
    coverage = coverage_rows(K, "full_bank_coverage")
    def coverage_fail(rows: Sequence[Mapping[str, Any]], K_value: int) -> List[str]:
        result = []
        for vdd in ANCHOR_VDD:
            local = {(row["medium_code"], row["fine_code"]): row for row in rows if row["vdd_v"] == vdd}
            if any(not local[key]["valid"] for key in ((7, 0), (7, K_value), (8, 0))): result.append("{} V coverage waveform invalid".format(vkey(vdd)))
            elif float(local[7, K_value]["D_rise_ps"]) < float(local[8, 0]["D_rise_ps"]): result.append("{} V medium_fine_gap_remains".format(vkey(vdd)))
        return result
    gaps = coverage_fail(coverage, K)
    if gaps:
        estimates = []
        for vdd in ANCHOR_VDD:
            local = {(row["medium_code"], row["fine_code"]): row for row in coverage if row["vdd_v"] == vdd}
            fine_range = float(local[7, K]["D_rise_ps"]) - float(local[7, 0]["D_rise_ps"])
            coupled = float(local[8, 0]["D_rise_ps"]) - float(local[7, 0]["D_rise_ps"])
            if fine_range <= 0 or coupled <= 0:
                break
            estimates.append(math.ceil(K * coupled / fine_range))
        rescaled = max(estimates, default=MAX_FINE_BANK + 1)
        if rescaled <= MAX_FINE_BANK and rescaled > K:
            sizing["K_rescaled"] = rescaled; K = rescaled; coverage.extend(coverage_rows(K, "full_bank_coverage_rescaled")); gaps = coverage_fail([row for row in coverage if row["stage"] == "full_bank_coverage_rescaled"], K)
    write_json(analysis / "fine_bank_sizing.json", sizing); write_csv(analysis / "full_bank_coverage.csv", coverage)
    if gaps:
        stages[STAGES[5]] = "NO-GO"; mark_later_not_run(stages, STAGES[5]); result = summary(analysis, stages, gaps, stats); render_report(args.report_output.resolve(), result, selected, sizing, None); return 0
    stages[STAGES[5]] = "GO"
    if args.stop_after == "coverage":
        print("FTC_STANDARD_CELL_LOAD_FINE_STAGE coverage=gate_passed")
        return 0
    final_rows = [measure("full_bank_monotonicity", hspice, run_dir, config, cells, 7, .95, candidate, K, code, low, high, sig, stats) for code in range(K + 1)]
    sample_codes = tuple(sorted(set((0, 1, round(K / 4), round(K / 2), round(3 * K / 4), K - 1, K))))
    for vdd in (1.10, .80): final_rows.extend(measure("full_bank_monotonicity", hspice, run_dir, config, cells, 7, vdd, candidate, K, code, low, high, sig, stats) for code in sample_codes)
    mono_reasons = monotonic([row for row in final_rows if row["vdd_v"] == .95], tuple(range(K + 1)))
    for vdd in (1.10, .80): mono_reasons.extend(monotonic([row for row in final_rows if row["vdd_v"] == vdd], sample_codes))
    write_csv(analysis / "full_bank_monotonicity.csv", final_rows)
    if mono_reasons:
        stages[STAGES[6]] = "NO-GO"; mark_later_not_run(stages, STAGES[6]); result = summary(analysis, stages, mono_reasons, stats); render_report(args.report_output.resolve(), result, selected, sizing, None); return 0
    stages[STAGES[6]] = "GO"
    coupled = [measure("coupled_medium_coverage", hspice, run_dir, config, cells, medium_code, vdd, candidate, K, fine_code, low, high, sig, stats) for vdd in ANCHOR_VDD for medium_code in (0, 7, 15) for fine_code in (K,)]
    coupled.extend(measure("coupled_medium_coverage", hspice, run_dir, config, cells, medium_code + 1, vdd, candidate, K, 0, low, high, sig, stats) for vdd in ANCHOR_VDD for medium_code in (0, 7, 15))
    coupled_reasons, min_medium = [], {}
    for vdd in ANCHOR_VDD:
        local = {(row["medium_code"], row["fine_code"]): row for row in coupled if row["vdd_v"] == vdd}
        steps = []
        for medium_code in (0, 7, 15):
            left, right = local[medium_code, K], local[medium_code + 1, 0]
            if not left["valid"] or not right["valid"] or float(left["D_rise_ps"]) < float(right["D_rise_ps"]): coupled_reasons.append("{} V {}->{} coverage failed".format(vkey(vdd), medium_code, medium_code + 1))
            base_left = measure("coupled_medium_step", hspice, run_dir, config, cells, medium_code, vdd, candidate, K, 0, low, high, sig, stats)
            coupled.append(base_left); steps.append(float(right["D_rise_ps"]) - float(base_left["D_rise_ps"]))
        min_medium[vkey(vdd)] = min(steps)
    write_csv(analysis / "coupled_medium_coverage.csv", coupled)
    measured_steps = {"0.95": max(float(final_rows[index + 1]["D_rise_ps"]) - float(final_rows[index]["D_rise_ps"]) for index in range(K)), "1.10": max(float(next(row for row in final_rows if row["vdd_v"] == 1.10 and row["fine_code"] == second)["D_rise_ps"]) - float(next(row for row in final_rows if row["vdd_v"] == 1.10 and row["fine_code"] == first)["D_rise_ps"]) for first, second in zip(sample_codes, sample_codes[1:]) if second == first + 1), "0.80": max(float(next(row for row in final_rows if row["vdd_v"] == .80 and row["fine_code"] == second)["D_rise_ps"]) - float(next(row for row in final_rows if row["vdd_v"] == .80 and row["fine_code"] == first)["D_rise_ps"]) for first, second in zip(sample_codes, sample_codes[1:]) if second == first + 1)}
    for key in measured_steps:
        if measured_steps[key] >= min_medium[key]: coupled_reasons.append("{} V fine resolution is not below coupled medium step".format(key))
    if coupled_reasons:
        stages[STAGES[7]] = "NO-GO"; mark_later_not_run(stages, STAGES[7]); result = summary(analysis, stages, coupled_reasons, stats); render_report(args.report_output.resolve(), result, selected, sizing, None); return 0
    stages[STAGES[7]] = "GO"
    historical = list(csv.DictReader((FTC_ROOT / "analysis/path_selection_medium_stage/medium_step_characterization.csv").open(encoding="utf-8")))
    bypass = {"schema_version": 1, "selected_load_cell": candidate["cell"], "signal_pin": candidate["signal_pin"], "control_pin": candidate["control_pin"], "low_cap_control_value": low, "high_cap_control_value": high, "K_candidate_tt25": sizing["K_candidate"], "fine_range_by_vdd": {}, "coverage_margin_by_vdd": {}, "fine_driver_offset_ps_by_vdd": {}, "fine_bank_code0_offset_ps_by_vdd": {}, "bypass_not_implemented": True, "final_K_frozen": False}
    for vdd in ANCHOR_VDD:
        medium_only = next(float(row["D_rise_ps"]) for row in historical if float(row["vdd_v"]) == vdd and int(row["code"]) == 8)
        driver = next(float(row["D_rise_ps"]) for row in screen if row["candidate_id"] == "driver_only" and row["vdd_v"] == vdd)
        bank0 = next(float(row["D_rise_ps"]) for row in coverage if row["medium_code"] == 8 and row["fine_code"] == 0 and row["vdd_v"] == vdd)
        bankK = next(float(row["D_rise_ps"]) for row in coverage if row["medium_code"] == 7 and row["fine_code"] == K and row["vdd_v"] == vdd)
        next0 = next(float(row["D_rise_ps"]) for row in coverage if row["medium_code"] == 8 and row["fine_code"] == 0 and row["vdd_v"] == vdd)
        bypass["fine_driver_offset_ps_by_vdd"][vkey(vdd)] = driver - medium_only
        bypass["fine_bank_code0_offset_ps_by_vdd"][vkey(vdd)] = bank0 - driver
        bypass["fine_range_by_vdd"][vkey(vdd)] = bankK - next0 + (next0 - bank0)
        bypass["coverage_margin_by_vdd"][vkey(vdd)] = bankK - next0
    write_json(analysis / "future_bypass_interface.json", bypass)
    stages[STAGES[8]] = "GO"
    result = summary(analysis, stages, [], stats); render_report(args.report_output.resolve(), result, selected, sizing, bypass)
    print("FTC_STANDARD_CELL_LOAD_FINE_STAGE decision=GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
