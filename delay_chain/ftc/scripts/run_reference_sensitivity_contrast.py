#!/usr/bin/env python3
"""Characterize same-rail reference delay units against frozen tap29 evidence.

This task owns only reference-cell HSPICE jobs.  The tap29 sensor is never
instantiated here: its committed CSV evidence is loaded and validated as
read-only input.  Keeping discovery, deck rendering, physical execution and
the small residual calculation in one script makes the experiment auditable
without introducing a new framework or modifying the completed FTC runner.
"""

import argparse
import csv
import itertools
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as error:  # pragma: no cover - runtime dependency check.
    raise SystemExit("reference contrast requires Matplotlib: {}".format(error))


FTC_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
PHASE1_SCRIPTS = FTC_ROOT.parent / "phase1" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(PHASE1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PHASE1_SCRIPTS))

import discover_ftc_cells  # noqa: E402  # Reuse only its CDL/Verilog parsers.
import run_dc_sweep  # noqa: E402  # Reuse HSPICE validation and MEASFORM parser.


V0S = (1.10, 0.90)
TT_TEMPERATURES = (-40.0, 25.0, 125.0)
PVT_TEMPERATURES = (-40.0, 25.0, 85.0, 125.0)
TT_VDDS = (1.10, 1.05, 1.00, 0.90, 0.85, 0.80)
PVT_CORNERS = ("tt", "ff", "ss")
MANIFEST_FIELDS = (
    "candidate_id", "candidate_kind", "vt_class", "cell_names", "logic_family",
    "stage_count", "overall_polarity", "cdl_ports", "fixed_logic_ties",
    "source_cdl", "source_verilog",
)
SCREEN_FIELDS = (
    "candidate_id", "candidate_kind", "v0_v", "d_r_25c_ps", "w_s_25c_ps",
    "equivalent_unit_count", "e_t_m40c_ps", "e_t_125c_ps", "e_t_max_ps",
    "raw_sensor_temperature_span_ps", "residual_temperature_span_ps",
    "e_v_50mv_ps", "e_v_100mv_ps", "m_50_ps", "m_100_ps",
    "sign_e_v_100mv",
)
PVT_FIELDS = (
    "candidate_id", "corner", "temperature_residual_1p10_ps",
    "sensor_temperature_span_1p10_ps", "temperature_reduced_1p10",
    "temperature_residual_0p90_ps", "sensor_temperature_span_0p90_ps",
    "temperature_reduced_0p90", "vdd_residual_1p10_to_0p90_ps",
    "vdd_contrast_nonzero",
)


def finite(value: Any, name: str) -> float:
    """Convert one scalar and reject failed HSPICE or CSV values."""

    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("{} is not numeric: {!r}".format(name, value)) from error
    if not math.isfinite(result):
        raise ValueError("{} is not finite: {!r}".format(name, value))
    return result


def voltage_key(value: Any) -> float:
    """Use the two-decimal grid used by the committed sensor fine curve."""

    return round(finite(value, "VDD"), 2)


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write deterministic compact evidence outside the ignored raw-run tree."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    """Write a nonempty, explicit-schema compact evidence table."""

    if not rows:
        raise ValueError("refusing to write empty evidence: {}".format(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def parse_module(text: str, cell: str) -> Tuple[List[str], str]:
    """Return one functional module's ports and body, rejecting ambiguity.

    The vendor file contains several views of each cell.  The first plain
    functional view is intentionally used for logic recognition; powered
    views are checked separately by ``powered_module_ports``.
    """

    pattern = re.compile(
        r"\bmodule\s+{}\s*\(([^;]+)\);(.*?)\bendmodule\b".format(re.escape(cell)),
        re.IGNORECASE | re.DOTALL,
    )
    matches = list(pattern.finditer(text))
    if not matches:
        raise ValueError("functional Verilog module is unavailable: {}".format(cell))
    for match in matches:
        ports = [item.strip() for item in match.group(1).replace("\n", " ").split(",") if item.strip()]
        if "VDD" not in ports and "VSS" not in ports:
            return ports, match.group(2)
    raise ValueError("unpowered functional Verilog view is unavailable: {}".format(cell))


def drive_value(cell: str) -> float:
    """Extract the numeric drive token used only to choose the smallest cell."""

    match = re.search(r"_X(\d+)(?:P(\d+))?[ABM]_", cell)
    if match is None:
        return float("inf")
    fraction = match.group(2) or "0"
    return float("{}.{}".format(match.group(1), fraction))


def candidate_cell(cdl: Mapping[str, Sequence[str]], verilog: str, family: str, vt: str) -> Dict[str, Any]:
    """Find and functionally validate one lowest-drive family/Vt cell.

    The family filters are deliberately narrow.  They avoid BUF variants with
    enables and avoid enumerating every library strength while still deriving
    the exact selected name from the installed CDL.
    """

    suffix = "A9TR40" if vt == "RVT" else "A9TL40"
    prefixes = {"BUF": "BUF_X", "INV": "INV_X", "NAND2": "NAND2_X", "NOR2": "NOR2_X", "MUX": "MXT2_X"}
    prefix = prefixes[family]
    names = [
        name for name in cdl
        if name.startswith(prefix) and name.endswith(suffix)
        and re.search(r"_X[^_]*M_", name) is not None
    ]
    if not names:
        raise ValueError("no {} {} cell found in installed CDL".format(vt, family))
    cell = sorted(names, key=lambda item: (drive_value(item), item))[0]
    ports, body = parse_module(verilog, cell)
    expected = {
        "BUF": ["Y", "A"], "INV": ["Y", "A"],
        "NAND2": ["Y", "A", "B"], "NOR2": ["Y", "A", "B"],
        "MUX": ["Y", "A", "B", "S0"],
    }[family]
    if ports != expected:
        raise ValueError("{} functional ports {} do not match {}".format(cell, ports, expected))
    # The primitive token is the direct proof for ordinary gates.  A MUX's
    # vendor UDP is accepted only with both data pins driven by the same input;
    # this removes any dependence on undocumented select truth-table polarity.
    token = {"BUF": r"\bbuf\b", "INV": r"\bnot\b", "NAND2": r"\bnand\b", "NOR2": r"\bnor\b", "MUX": r"udp_mux2"}[family]
    if re.search(token, body, re.IGNORECASE) is None:
        raise ValueError("{} functional primitive proof is absent".format(cell))
    return {
        "cell": cell, "vt_class": vt, "family": family,
        "cdl_ports": list(cdl[cell]), "verilog_ports": ports,
        "source_cell": cell,
    }


def make_candidates(cells: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Build the small, non-inverting candidate set from actual library views."""

    result: List[Dict[str, Any]] = []
    for vt, cdl_key, verilog_key in (
        ("RVT", "rvt_cdl", "rvt_verilog"), ("LVT", "lvt_cdl", "lvt_verilog"),
    ):
        cdl_path = Path(cells["source_files"][cdl_key])
        verilog_path = Path(cells["source_files"][verilog_key])
        cdl = discover_ftc_cells.parse_subckts(cdl_path)
        verilog = verilog_path.read_text(encoding="latin-1", errors="replace")
        for family in ("BUF", "MUX", "INV", "NAND2", "NOR2"):
            try:
                primitive = candidate_cell(cdl, verilog, family, vt)
            except ValueError:
                # A missing or semantically ambiguous family is excluded; the
                # task must never infer a pin tie from a guessed library name.
                continue
            if family in ("BUF", "MUX"):
                stages = [primitive]
                ties = {"S0": "VSS_A"} if family == "MUX" else {}
                dynamic = ["A", "B"] if family == "MUX" else ["A"]
            else:
                stages = [primitive, primitive]
                ties = {"B": "VDD_A" if family == "NAND2" else "VSS_A"}
                dynamic = ["A"]
            for stage in stages:
                stage["dynamic_pins"] = list(dynamic)
                stage["ties"] = dict(ties)
            result.append({
                "candidate_id": "{}_{}".format(family.lower(), vt.lower()),
                "candidate_kind": "simple",
                "vt_class": vt,
                "cell_names": [item["cell"] for item in stages],
                "logic_family": family,
                "stage_count": len(stages),
                "overall_polarity": "non_inverting",
                "cdl_ports": "|".join(primitive["cdl_ports"]),
                "fixed_logic_ties": json.dumps(ties, sort_keys=True),
                "source_cdl": str(cdl_path),
                "source_verilog": str(verilog_path),
                "source_cdls": [str(cdl_path)],
                "stages": stages,
                "dynamic_pins": dynamic,
                "ties": ties,
            })
    if not result:
        raise RuntimeError("no functionally verified reference candidate was discovered")
    return result


def manifest_rows(candidates: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Remove internal stage metadata from the committed candidate manifest."""

    return [{field: candidate.get(field, "") for field in MANIFEST_FIELDS} for candidate in candidates]


def spice(value: float) -> str:
    """Render a locale-independent HSPICE scalar."""

    return "{:.12e}".format(float(value))


def stage_instance(candidate: Mapping[str, Any], unit: int, stage: int, input_node: str, output_node: str) -> str:
    """Render one positional CDL instance with all supplies on the sensor rails."""

    meta = candidate["stages"][stage]
    ties = meta["ties"]
    dynamic = set(meta["dynamic_pins"])
    pins: List[str] = []
    for pin in meta["cdl_ports"]:
        if pin == meta["cdl_ports"][0]:
            pins.append(output_node)
        elif pin in ("VDD", "VNW"):
            pins.append("vdd_a")
        elif pin in ("VSS", "VPW"):
            pins.append("vss_a")
        elif pin in dynamic:
            pins.append(input_node)
        elif pin in ties:
            pins.append(ties[pin].lower())
        else:
            raise ValueError("unconnected candidate pin {} in {}".format(pin, candidate["candidate_id"]))
    return "X{}_u{}_s{} {}".format(candidate["candidate_id"], unit, stage, " ".join(pins)) + " " + meta["cell"]


def render_deck(config: Mapping[str, Any], candidate: Mapping[str, Any], vdd_v: float, corner: str, temperature: float) -> str:
    """Render the isolated three-unit reference delay experiment."""

    includes = ['.include "{}"'.format(path) for path in candidate["source_cdls"]]
    lines = [
        "* Reference-only deck; tap29 sensor is intentionally absent.",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(temperature)),
        *includes,
        '.lib "{}" {}'.format(config["model_library"], corner),
        ".param VDD_VALUE={}".format(spice(vdd_v)),
        "V_VDD vdd_a vss_a 'VDD_VALUE'",
        "V_VSS vss_a 0 0",
        "V_INPUT ref_in vss_a PULSE(0 'VDD_VALUE' 1.000000000000e-09 1.000000000000e-12 1.000000000000e-12 3.000000000000e-09 6.000000000000e-09)",
    ]
    stage_count = int(candidate["stage_count"])
    unit_inputs: List[str] = []
    unit_outputs: List[str] = []
    for unit in range(3):
        current = "ref_in" if unit == 0 else "u{}_out".format(unit - 1)
        unit_inputs.append(current)
        for stage in range(stage_count):
            output = "u{}_out".format(unit) if stage == stage_count - 1 else "u{}_s{}_out".format(unit, stage)
            lines.append(stage_instance(candidate, unit, stage, current, output))
            current = output
        unit_outputs.append(current)
    middle_in = unit_inputs[1]
    middle_out = unit_outputs[1]
    lines.extend([
        ".tran 1.000000000000e-12 5.000000000000e-09",
        ".measure tran unit1_input_cross WHEN v({},vss_a)='VDD_VALUE/2' RISE=1".format(middle_in),
        ".measure tran unit1_output_cross WHEN v({},vss_a)='VDD_VALUE/2' RISE=1".format(middle_out),
        ".measure tran d_ref TRIG v({},vss_a) VAL='VDD_VALUE/2' RISE=1 TARG v({},vss_a) VAL='VDD_VALUE/2' RISE=1".format(middle_in, middle_out),
        ".measure tran vdd_a_min_v MIN v(vdd_a,vss_a) FROM=0 TO=5.000000000000e-09",
        ".end",
        "",
    ])
    return "\n".join(lines)


def load_json(path: Path) -> Dict[str, Any]:
    """Load an object-shaped JSON file and reject malformed evidence early."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def load_rows(path: Path) -> List[Dict[str, str]]:
    """Load a nonempty CSV table without changing its source values."""

    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("empty sensor evidence: {}".format(path))
    return rows


def validate_sensor_evidence() -> Dict[str, Any]:
    """Read and validate every frozen sensor artifact required by the plan."""

    analysis = FTC_ROOT / "analysis" / "real_xor_pvt_baseline"
    fine_rows = load_rows(FTC_ROOT / "analysis" / "real_xor_pulse_width" / "fine.csv")
    if len(fine_rows) != 36:
        raise ValueError("fine.csv must contain exactly 36 rows")
    fine: Dict[float, Dict[str, Any]] = {}
    expected = [round(1.10 - 0.01 * index, 2) for index in range(36)]
    for row, expected_vdd in zip(fine_rows, expected):
        vdd = voltage_key(row["vdd_v"])
        if vdd != expected_vdd or int(row["valid"]) != 1:
            raise ValueError("invalid fine.csv row at {} V".format(expected_vdd))
        fine[vdd] = {"W_real_ps": finite(row["W_real_ps"], "fine W_real")}
    process_rows = load_rows(analysis / "process_screen.csv")
    temperature_rows = load_rows(analysis / "temperature_screen.csv")
    pvt_rows = load_rows(analysis / "pvt_matrix.csv")
    process_corners = load_json(analysis / "process_corners.json")
    baseline_summary = load_json(analysis / "summary.json")
    report = (FTC_ROOT / "reports" / "FTC_TAP29_PVT_BASELINE_CHARACTERIZATION.md").read_text(encoding="utf-8")
    if "tap29" not in report or baseline_summary.get("measured_tap") != 29:
        raise ValueError("frozen tap29 baseline provenance is invalid")

    def index(rows: Sequence[Mapping[str, str]]) -> Dict[Tuple[str, float, float], Dict[str, Any]]:
        indexed: Dict[Tuple[str, float, float], Dict[str, Any]] = {}
        for row in rows:
            key = (str(row["corner"]).lower(), voltage_key(row["vdd_v"]), finite(row["temperature_c"], "temperature"))
            if key in indexed:
                raise ValueError("duplicate sensor key: {}".format(key))
            if int(row["valid"]) != 1:
                raise ValueError("invalid sensor row: {}".format(key))
            indexed[key] = {"W_real_ps": finite(row["W_real_ps"], "sensor W_real")}
        return indexed

    temperature = index(temperature_rows)
    pvt = index(pvt_rows)
    for corner in PVT_CORNERS:
        for vdd in V0S:
            for temp in PVT_TEMPERATURES:
                if (corner, vdd, temp) not in pvt:
                    raise ValueError("missing PVT sensor evidence: {} {} {}".format(corner, vdd, temp))
    for vdd in V0S:
        for temp in TT_TEMPERATURES:
            if ("tt", vdd, temp) not in temperature:
                raise ValueError("missing TT temperature sensor evidence: {} {}".format(vdd, temp))
        if abs(temperature[("tt", vdd, 25.0)]["W_real_ps"] - fine[vdd]["W_real_ps"]) > 1.0e-9:
            raise ValueError("temperature/fine sensor evidence disagrees at {} V".format(vdd))
    return {
        "fine": fine, "temperature": temperature, "pvt": pvt,
        "process_rows": len(process_rows), "process_corners": process_corners,
        "baseline_summary": baseline_summary,
        "sources": [str(FTC_ROOT / "analysis" / "real_xor_pulse_width" / "fine.csv"), str(analysis / "temperature_screen.csv"), str(analysis / "pvt_matrix.csv")],
    }


def task_output(run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]) -> Path:
    """Preflight local HSPICE and create one non-overwritable raw-run root."""

    if run_dir.exists():
        raise ValueError("refusing to overwrite reference run directory: {}".format(run_dir))
    hspice = run_dc_sweep.require_regular_file(Path(config["hspice"]), "local HSPICE", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if str(config["expected_hspice_version"]) not in version:
        raise RuntimeError("unexpected local HSPICE version: {}".format(version))
    for source in list(cells["source_files"].values()) + [config["model_library"]]:
        run_dc_sweep.require_regular_file(Path(source), "reference source collateral")
    compatibility = FTC_ROOT / "spice" / "empty_subckt.sp_cal"
    run_dc_sweep.require_regular_file(compatibility, "reference compatibility include")
    run_dir.mkdir(parents=True)
    write_json(run_dir / "manifest.json", {
        "study": "ftc_reference_sensitivity_contrast",
        "hspice": str(hspice), "hspice_version": version,
        "config": dict(config), "selected_cells": dict(cells),
        "candidate_ids": [candidate["candidate_id"] for candidate in candidates],
        "scope": "reference-only; frozen tap29 sensor evidence is read-only",
    })
    return hspice


def run_one(hspice: Path, run_dir: Path, config: Mapping[str, Any], candidate: Mapping[str, Any], index: int, vdd: float, corner: str, temperature: float) -> Dict[str, Any]:
    """Run and validate exactly one isolated reference-only HSPICE deck."""

    label = "{}_{}_{}".format(candidate["candidate_id"], corner, str(temperature).replace("-", "m").replace(".", "p"))
    scenario = run_dir / "scenarios" / "{:04d}_{}_v{}_t{}".format(index, label, str(vdd).replace(".", "p"), str(temperature).replace("-", "m").replace(".", "p"))
    scenario.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", scenario / "empty_subckt.sp_cal")
    deck_path = scenario / "reference.sp"
    local_config = dict(config)
    local_config["lvt_cdl"] = config["source_files"]["lvt_cdl"] if "source_files" in config else config.get("lvt_cdl", "")
    deck_path.write_text(render_deck(local_config, candidate, vdd, corner, temperature), encoding="ascii")
    result = subprocess.run([str(hspice), deck_path.name, "-o", "reference"], cwd=str(scenario), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=300)
    (scenario / "hspice_command.log").write_text("returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, scenario))
    warnings = run_dc_sweep.validate_listing(scenario / "reference.lis")
    measurement = run_dc_sweep.parse_measurements(run_dc_sweep.find_measurement_file(scenario, "reference"))
    required = ["unit1_input_cross", "unit1_output_cross", "d_ref"]
    missing = [name for name in required if measurement.get(name) is None]
    if missing:
        raise RuntimeError("reference measure failure {}: {}".format(scenario, missing))
    delay = finite(measurement["d_ref"], "D_R") * 1.0e12
    if delay <= 0.0:
        raise RuntimeError("non-positive reference delay in {}".format(scenario))
    return {
        "candidate_id": candidate["candidate_id"], "candidate_kind": candidate["candidate_kind"],
        "vdd_v": round(vdd, 2), "corner": corner, "temperature_c": float(temperature),
        "d_r_ps": delay, "unit1_input_cross_s": finite(measurement["unit1_input_cross"], "unit input crossing"),
        "unit1_output_cross_s": finite(measurement["unit1_output_cross"], "unit output crossing"),
        "warnings": warnings, "scenario": str(scenario.relative_to(run_dir)),
    }


def condition_list(candidates: Sequence[Mapping[str, Any]], corners: Sequence[str], temperatures: Sequence[float], vdds: Sequence[float], existing: Mapping[Tuple[str, str, float, float], Mapping[str, Any]]) -> List[Tuple[Mapping[str, Any], str, float, float]]:
    """Return only missing reference conditions, preserving deterministic order."""

    result = []
    for candidate in candidates:
        for corner in corners:
            for temperature in temperatures:
                for vdd in vdds:
                    key = (candidate["candidate_id"], corner, float(temperature), voltage_key(vdd))
                    if key not in existing:
                        result.append((candidate, corner, float(temperature), voltage_key(vdd)))
    return result


def run_grid(hspice: Path, run_dir: Path, config: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]], existing: Dict[Tuple[str, str, float, float], Dict[str, Any]], corners: Sequence[str], temperatures: Sequence[float], vdds: Sequence[float], start_index: int) -> int:
    """Execute a complete requested reference grid, with exact-key reuse only."""

    index = start_index
    for candidate, corner, temperature, vdd in condition_list(candidates, corners, temperatures, vdds, existing):
        row = run_one(hspice, run_dir, config, candidate, index, vdd, corner, temperature)
        existing[(candidate["candidate_id"], corner, temperature, vdd)] = row
        index += 1
    return index


def run_conditions(hspice: Path, run_dir: Path, config: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]], existing: Dict[Tuple[str, str, float, float], Dict[str, Any]], conditions: Sequence[Tuple[str, float, float]], start_index: int) -> int:
    """Run an explicit small condition list without a rectangular over-sweep."""

    index = start_index
    for candidate in candidates:
        for corner, temperature, vdd in conditions:
            key = (candidate["candidate_id"], corner, float(temperature), voltage_key(vdd))
            if key in existing:
                continue
            row = run_one(hspice, run_dir, config, candidate, index, voltage_key(vdd), corner, float(temperature))
            existing[key] = row
            index += 1
    return index


def load_reference_run(run_dir: Path) -> Dict[Tuple[str, str, float, float], Dict[str, Any]]:
    """Reload completed reference measurements without invoking HSPICE.

    A failed post-processing step must be recoverable from the task-owned raw
    evidence.  Scenario names carry the candidate, corner, VDD and temperature;
    the measurement parser then revalidates every stored listing/measure file.
    """

    result: Dict[Tuple[str, str, float, float], Dict[str, Any]] = {}
    pattern = re.compile(r"^\d+_(?P<candidate>.+)_(?P<corner>tt|ff|ss)_(?P<temp>m?\d+p\d+)_v(?P<vdd>\d+p\d+)_t(?P=temp)$")
    scenarios = sorted((run_dir / "scenarios").iterdir()) if (run_dir / "scenarios").is_dir() else []
    if not scenarios:
        raise ValueError("reference raw run contains no scenarios: {}".format(run_dir))
    for scenario in scenarios:
        if not scenario.is_dir():
            continue
        match = pattern.match(scenario.name)
        if match is None:
            raise ValueError("unrecognized reference scenario name: {}".format(scenario.name))
        def decode(token: str) -> float:
            return float(token.replace("m", "-").replace("p", "."))
        corner = match.group("corner")
        temperature = decode(match.group("temp"))
        vdd = decode(match.group("vdd"))
        measurement = run_dc_sweep.parse_measurements(run_dc_sweep.find_measurement_file(scenario, "reference"))
        run_dc_sweep.validate_listing(scenario / "reference.lis")
        if measurement.get("d_ref") is None:
            raise ValueError("reference measure is incomplete: {}".format(scenario))
        key = (match.group("candidate"), corner, temperature, voltage_key(vdd))
        if key in result:
            raise ValueError("duplicate raw reference condition: {}".format(key))
        result[key] = {
            "candidate_id": match.group("candidate"), "candidate_kind": "composite" if match.group("candidate").startswith("comp_") else "simple",
            "vdd_v": voltage_key(vdd), "corner": corner, "temperature_c": temperature,
            "d_r_ps": finite(measurement["d_ref"], "D_R") * 1.0e12,
            "unit1_input_cross_s": finite(measurement["unit1_input_cross"], "unit input crossing"),
            "unit1_output_cross_s": finite(measurement["unit1_output_cross"], "unit output crossing"),
            "scenario": str(scenario.relative_to(run_dir)),
        }
    return result


def sensor_width(sensor: Mapping[str, Any], corner: str, vdd: float, temperature: float, mode: str) -> float:
    """Read one exact frozen sensor width for TT or selected PVT evidence."""

    if mode == "fine":
        return finite(sensor["fine"][voltage_key(vdd)]["W_real_ps"], "fine W_real")
    table = sensor["temperature"] if mode == "temperature" else sensor["pvt"]
    return finite(table[(corner.lower(), voltage_key(vdd), float(temperature))]["W_real_ps"], "sensor W_real")


def reference_delay(ref: Mapping[Tuple[str, str, float, float], Mapping[str, Any]], candidate: str, corner: str, vdd: float, temperature: float) -> float:
    """Read one complete reference measure by its physical condition key."""

    return finite(ref[(candidate, corner, float(temperature), voltage_key(vdd))]["d_r_ps"], "D_R")


def residual_row(candidate: Mapping[str, Any], ref: Mapping[Tuple[str, str, float, float], Mapping[str, Any]], sensor: Mapping[str, Any], v0: float) -> Dict[str, Any]:
    """Calculate TT k, temperature residuals and 50/100 mV voltage margins."""

    cid = candidate["candidate_id"]
    ws25 = sensor_width(sensor, "tt", v0, 25.0, "fine")
    dr25 = reference_delay(ref, cid, "tt", v0, 25.0)
    k = ws25 / dr25
    et: Dict[float, float] = {}
    for temperature in TT_TEMPERATURES:
        ws = sensor_width(sensor, "tt", v0, temperature, "temperature")
        dr = reference_delay(ref, cid, "tt", v0, temperature)
        et[temperature] = (ws - ws25) - k * (dr - dr25)
    raw_span = max(abs(sensor_width(sensor, "tt", v0, temperature, "temperature") - ws25) for temperature in TT_TEMPERATURES)
    residual_span = max(abs(value) for value in et.values())
    targets = ((0.05, "50"), (0.10, "100"))
    voltage: Dict[str, float] = {}
    for drop, label in targets:
        ws_target = sensor_width(sensor, "tt", v0 - drop, 25.0, "fine")
        dr_target = reference_delay(ref, cid, "tt", v0 - drop, 25.0)
        voltage[label] = (ws_target - ws25) - k * (dr_target - dr25)
    return {
        "candidate_id": cid, "candidate_kind": candidate["candidate_kind"], "v0_v": v0,
        "d_r_25c_ps": dr25, "w_s_25c_ps": ws25, "equivalent_unit_count": k,
        "e_t_m40c_ps": et[-40.0], "e_t_125c_ps": et[125.0], "e_t_max_ps": residual_span,
        "raw_sensor_temperature_span_ps": raw_span, "residual_temperature_span_ps": residual_span,
        "e_v_50mv_ps": voltage["50"], "e_v_100mv_ps": voltage["100"],
        "m_50_ps": abs(voltage["50"]) - residual_span,
        "m_100_ps": abs(voltage["100"]) - residual_span,
        "sign_e_v_100mv": 1 if voltage["100"] > 0 else (-1 if voltage["100"] < 0 else 0),
        "_k": k, "_et": et,
    }


def screen(candidates: Sequence[Mapping[str, Any]], ref: Mapping[Tuple[str, str, float, float], Mapping[str, Any]], sensor: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Produce two local-workpoint rows per candidate."""

    return [residual_row(candidate, ref, sensor, v0) for candidate in candidates for v0 in V0S]


def shortlist(rows: Sequence[Mapping[str, Any]]) -> List[str]:
    """Apply the plan's strict two-anchor M100 gate and deterministic ranking."""

    grouped: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["candidate_id"]), []).append(row)
    qualified = []
    for cid, candidate_rows in grouped.items():
        if {float(row["v0_v"]) for row in candidate_rows} != set(V0S):
            continue
        if all(float(row["m_100_ps"]) > 0.0 and int(row["sign_e_v_100mv"]) != 0 for row in candidate_rows):
            qualified.append((cid, min(float(row["m_100_ps"]) for row in candidate_rows), min(float(row["m_50_ps"]) for row in candidate_rows)))
    qualified.sort(key=lambda item: (-item[1], -item[2], item[0]))
    return [item[0] for item in qualified[:3]]


def composite_candidates(candidates: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]], ref: Mapping[Tuple[str, str, float, float], Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Predict a few legal two-unit combinations without topology search.

    Every simple candidate is already non-inverting, so concatenating two of
    them remains non-inverting and has at most four standard-cell stages.  The
    additive calculation is only a ranking aid; selected combinations are
    re-simulated as complete macro units before use.
    """

    by_id = {candidate["candidate_id"]: candidate for candidate in candidates}
    row_map = {(str(row["candidate_id"]), float(row["v0_v"])): row for row in rows}
    proposals: List[Tuple[float, float, str, Dict[str, Any]]] = []
    for left, right in itertools.combinations_with_replacement(candidates, 2):
        stage_count = int(left["stage_count"]) + int(right["stage_count"])
        if stage_count > 4:
            continue
        cid = "comp_{}_plus_{}".format(left["candidate_id"], right["candidate_id"])
        predicted: Dict[Tuple[str, str, float, float], Dict[str, Any]] = {}
        for corner in ("tt",):
            for temperature in TT_TEMPERATURES:
                for vdd in TT_VDDS:
                    predicted[(cid, corner, temperature, vdd)] = {
                        "d_r_ps": reference_delay(ref, left["candidate_id"], corner, vdd, temperature) + reference_delay(ref, right["candidate_id"], corner, vdd, temperature),
                    }
        composite = dict(left)
        composite.update({
            "candidate_id": cid, "candidate_kind": "composite", "cell_names": left["cell_names"] + right["cell_names"],
            "stage_count": stage_count, "logic_family": "{}+{}".format(left["logic_family"], right["logic_family"]),
            "fixed_logic_ties": "{} + {}".format(left["fixed_logic_ties"], right["fixed_logic_ties"]),
            "stages": left["stages"] + right["stages"], "dynamic_pins": left["dynamic_pins"],
            "ties": left["ties"],
            "source_cdls": sorted(set(left["source_cdls"] + right["source_cdls"])),
        })
        # The additive predictor uses the already measured parent residuals;
        # it never fabricates a sensor table or launches an extra simulation.
        predicted_rows = predicted_screen_rows(composite, left, right, rows, ref)
        if not predicted_rows:
            continue
        if all(float(item["m_100_ps"]) > 0.0 for item in predicted_rows):
            score = min(float(item["m_100_ps"]) for item in predicted_rows)
            temp_score = max(float(item["e_t_max_ps"]) for item in predicted_rows)
            proposals.append((score, temp_score, cid, composite))
    proposals.sort(key=lambda item: (-item[0], item[1], int(item[3]["stage_count"]), item[2]))
    return [item[3] for item in proposals[:3]]


def predicted_screen_rows(composite: Mapping[str, Any], left: Mapping[str, Any], right: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], ref: Mapping[Tuple[str, str, float, float], Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Estimate composite residuals by adding the measured parent movements."""

    parent = {(str(row["candidate_id"]), float(row["v0_v"])): row for row in rows}
    output = []
    for v0 in V0S:
        left_row = parent[(left["candidate_id"], v0)]
        right_row = parent[(right["candidate_id"], v0)]
        et = float(left_row["e_t_max_ps"]) + float(right_row["e_t_max_ps"])
        ev50 = float(left_row["e_v_50mv_ps"]) + float(right_row["e_v_50mv_ps"])
        ev100 = float(left_row["e_v_100mv_ps"]) + float(right_row["e_v_100mv_ps"])
        output.append({"candidate_id": composite["candidate_id"], "v0_v": v0, "e_t_max_ps": et, "m_100_ps": abs(ev100) - et, "e_v_100mv_ps": ev100, "m_50_ps": abs(ev50) - et})
    return output


def pvt_confirmation(finalists: Sequence[Mapping[str, Any]], ref: Mapping[Tuple[str, str, float, float], Mapping[str, Any]], sensor: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Compare calibrated temperature movement and one fixed-anchor VDD move."""

    output = []
    for candidate in finalists:
        cid = candidate["candidate_id"]
        for corner in PVT_CORNERS:
            values: Dict[str, Any] = {"candidate_id": cid, "corner": corner}
            for v0, label in ((1.10, "1p10"), (0.90, "0p90")):
                ws25 = sensor_width(sensor, corner, v0, 25.0, "pvt")
                dr25 = reference_delay(ref, cid, corner, v0, 25.0)
                k = ws25 / dr25
                residuals = []
                sensor_moves = []
                for temperature in PVT_TEMPERATURES:
                    ws = sensor_width(sensor, corner, v0, temperature, "pvt")
                    dr = reference_delay(ref, cid, corner, v0, temperature)
                    residuals.append((ws - ws25) - k * (dr - dr25))
                    sensor_moves.append(ws - ws25)
                values["temperature_residual_{}_ps".format(label)] = max(abs(item) for item in residuals)
                values["sensor_temperature_span_{}_ps".format(label)] = max(abs(item) for item in sensor_moves)
                values["temperature_reduced_{}".format(label)] = int(values["temperature_residual_{}_ps".format(label)] < values["sensor_temperature_span_{}_ps".format(label)])
            ws_high = sensor_width(sensor, corner, 1.10, 25.0, "pvt")
            ws_low = sensor_width(sensor, corner, 0.90, 25.0, "pvt")
            dr_high = reference_delay(ref, cid, corner, 1.10, 25.0)
            dr_low = reference_delay(ref, cid, corner, 0.90, 25.0)
            k_high = ws_high / dr_high
            values["vdd_residual_1p10_to_0p90_ps"] = (ws_low - ws_high) - k_high * (dr_low - dr_high)
            values["vdd_contrast_nonzero"] = int(values["vdd_residual_1p10_to_0p90_ps"] != 0.0)
            output.append(values)
    return output


def save_figures(screen_rows: Sequence[Mapping[str, Any]], finalists: Sequence[Mapping[str, Any]], pvt_rows: Sequence[Mapping[str, Any]], ref: Mapping[Tuple[str, str, float, float], Mapping[str, Any]], sensor: Mapping[str, Any], output: Path) -> None:
    """Render exactly the two requested compact figures."""

    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "svg.fonttype": "none"})
    figure, axes = plt.subplots(1, 2, figsize=(9.0, 4.0), sharex=False, sharey=False)
    for axis, field, title in zip(axes, ("m_50_ps", "m_100_ps"), ("50 mV residual margin", "100 mV residual margin")):
        for row in screen_rows:
            voltage_field = "e_v_50mv_ps" if field == "m_50_ps" else "e_v_100mv_ps"
            axis.scatter(float(row["residual_temperature_span_ps"]), abs(float(row[voltage_field])), label=str(row["candidate_id"]))
        axis.set_xlabel("Worst temperature residual (ps)")
        axis.set_ylabel("Voltage residual magnitude (ps)")
        axis.set_title(title)
        axis.grid(True, linewidth=0.5, alpha=0.35)
    handles, labels = axes[1].get_legend_handles_labels()
    if labels:
        axes[1].legend(handles, labels, fontsize=6, loc="best")
    figure.savefig(output / "fig1_temperature_residual_vs_voltage_residual.svg", format="svg", bbox_inches="tight", metadata={"Date": None})
    plt.close(figure)

    figure, axes = plt.subplots(max(1, len(finalists)), 1, figsize=(8.0, max(3.0, 2.8 * len(finalists))), squeeze=False)
    for axis, candidate in zip(axes[:, 0], finalists):
        cid = candidate["candidate_id"]
        for corner in PVT_CORNERS:
            for v0 in V0S:
                values = []
                for temperature in PVT_TEMPERATURES:
                    ws25 = sensor_width(sensor, corner, v0, 25.0, "pvt")
                    dr25 = reference_delay(ref, cid, corner, v0, 25.0)
                    k = ws25 / dr25
                    values.append((sensor_width(sensor, corner, v0, temperature, "pvt") - ws25) - k * (reference_delay(ref, cid, corner, v0, temperature) - dr25))
                axis.plot(PVT_TEMPERATURES, values, marker="o", label="{} @ {:.2f} V".format(corner, v0))
        axis.set_title(cid)
        axis.set_xlabel("Temperature (C)")
        axis.set_ylabel("Calibrated residual (ps)")
        axis.grid(True, linewidth=0.5, alpha=0.35)
        axis.legend(fontsize=6, loc="best")
    figure.savefig(output / "fig2_finalist_residual_across_pvt.svg", format="svg", bbox_inches="tight", metadata={"Date": None})
    plt.close(figure)


def render_report(path: Path, candidates: Sequence[Mapping[str, Any]], simple_rows: Sequence[Mapping[str, Any]], composite_rows: Sequence[Mapping[str, Any]], finalists: Sequence[Mapping[str, Any]], pvt_rows: Sequence[Mapping[str, Any]], decision: str) -> None:
    """Write the five required research answers and explicit evidence provenance."""

    by_candidate: Dict[str, List[Mapping[str, Any]]] = {}
    for row in list(simple_rows) + list(composite_rows):
        by_candidate.setdefault(str(row["candidate_id"]), []).append(row)
    lines = [
        "# FTC Reference Sensitivity Contrast Feasibility", "",
        "This report measures reference-only HSPICE paths with local HSPICE W-2024.09. Existing tap29 evidence is read-only and no sensor campaign is rerun.", "",
        "## Decision", "", "**{}**".format(decision), "",
        "## Candidate results", "", "| Candidate | V0 (V) | E_T max (ps) | E_V 50 mV (ps) | E_V 100 mV (ps) | M_50 (ps) | M_100 (ps) |", "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in list(simple_rows) + list(composite_rows):
        lines.append("| {} | {:.2f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} |".format(row["candidate_id"], float(row["v0_v"]), float(row["e_t_max_ps"]), float(row["e_v_50mv_ps"]), float(row["e_v_100mv_ps"]), float(row["m_50_ps"]), float(row["m_100_ps"])))
    lines.extend([
        "", "## Required answers", "",
        "1. **Single-cell reference quantum:** {}.".format("有 functionally verified single-cell candidate" if any(int(candidate["stage_count"]) == 1 for candidate in candidates) else "未形成合格 single-cell candidate"),
        "2. **Smallest composite:** {}.".format("; ".join(candidate["candidate_id"] for candidate in finalists if candidate["candidate_kind"] == "composite") or "不需要或未找到"),
        "3. **Local margins:** see the candidate table above for both 1.10 V and 0.90 V M_50/M_100.",
        "4. **Per-process temperature tracking:** see `finalist_pvt_confirmation.csv`; each row compares calibrated residual with raw sensor movement.",
        "5. **Next stage:** {}.".format("值得进入最小可编程参考延迟线" if decision == "GO" else "本阶段不支持直接进入最小可编程参考延迟线"),
        "", "## Provenance", "",
        "- Measured evidence: reference candidate HSPICE D_R rows under the task-owned run directory.",
        "- Reused evidence: frozen tap29 `fine.csv`, temperature screen, and TT/FF/SS PVT matrix.",
        "- Analysis-only: continuous k; it is not a hardware unit count and does not implement self-calibration.",
        "- Future inference: no bypass network, FSM, detector, or P&R is implemented here.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Expose paths only; physical coordinates remain fixed by the plan."""

    parser = argparse.ArgumentParser(description="run the FTC reference sensitivity-contrast study")
    parser.add_argument("--config", type=Path, default=FTC_ROOT / "ftc_config.json")
    parser.add_argument("--run-dir", type=Path, default=FTC_ROOT / "runs" / "reference_sensitivity_contrast")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis" / "reference_sensitivity_contrast")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports" / "FTC_REFERENCE_SENSITIVITY_CONTRAST_FEASIBILITY.md")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run discovery, complete TT screen, conditional fallback and PVT proof."""

    args = parse_args(argv)
    config = load_json(args.config.resolve())
    cells = load_json(FTC_ROOT / "discovery" / "selected_cells.json")
    sensor = validate_sensor_evidence()
    candidates = make_candidates(cells)
    analysis_dir = args.analysis_dir.resolve()
    write_csv(analysis_dir / "candidate_manifest.csv", MANIFEST_FIELDS, manifest_rows(candidates))
    config = dict(config)
    config["source_files"] = cells["source_files"]
    run_dir = args.run_dir.resolve()
    if run_dir.exists():
        # Recovery path for a completed physical campaign whose compact
        # post-processing was interrupted.  It revalidates stored HSPICE
        # outputs and never launches a replacement or duplicate scenario.
        hspice = run_dc_sweep.require_regular_file(Path(config["hspice"]), "local HSPICE", executable=True)
        version = run_dc_sweep.hspice_version(hspice)
        if str(config["expected_hspice_version"]) not in version:
            raise RuntimeError("unexpected local HSPICE version: {}".format(version))
        reference = load_reference_run(run_dir)
        next_index = len(reference)
    else:
        hspice = task_output(run_dir, config, cells, candidates)
        reference = {}
        tt_conditions = [("tt", 25.0, vdd) for vdd in TT_VDDS]
        tt_conditions.extend(("tt", temperature, vdd) for vdd in V0S for temperature in TT_TEMPERATURES if temperature != 25.0)
        next_index = run_conditions(hspice, run_dir, config, candidates, reference, tt_conditions, 0)
    simple_rows = screen(candidates, reference, sensor)
    finalists_ids = shortlist(simple_rows)
    composites: List[Dict[str, Any]] = []
    composite_rows: List[Dict[str, Any]] = []
    if not finalists_ids:
        composites = composite_candidates(candidates, simple_rows, reference)
        composite_conditions = [("tt", 25.0, vdd) for vdd in TT_VDDS]
        composite_conditions.extend(("tt", temperature, vdd) for vdd in V0S for temperature in TT_TEMPERATURES if temperature != 25.0)
        if composites:
            if not args.run_dir.resolve().exists():
                next_index = run_conditions(hspice, args.run_dir.resolve(), config, composites, reference, composite_conditions, next_index)
            else:
                # Existing raw runs are authoritative.  A missing composite
                # raw result means the prior physical campaign is incomplete,
                # so fail rather than silently replacing it during recovery.
                required = len(composites) * len(composite_conditions)
                present = sum(1 for candidate in composites for condition in composite_conditions if (candidate["candidate_id"], condition[0], condition[1], voltage_key(condition[2])) in reference)
                if present != required:
                    raise RuntimeError("existing reference run lacks completed composite evidence")
        composite_rows = screen(composites, reference, sensor)
        finalists_ids = shortlist(composite_rows)
    candidate_by_id = {candidate["candidate_id"]: candidate for candidate in candidates + composites}
    finalists = [candidate_by_id[cid] for cid in finalists_ids]
    if finalists:
        next_index = run_grid(hspice, args.run_dir.resolve(), config, finalists, reference, PVT_CORNERS, PVT_TEMPERATURES, TT_VDDS[:1] + TT_VDDS[3:4], next_index)
    pvt_rows = pvt_confirmation(finalists, reference, sensor) if finalists else []
    full_pvt = bool(pvt_rows) and all(int(row["temperature_reduced_1p10"]) and int(row["temperature_reduced_0p90"]) and int(row["vdd_contrast_nonzero"]) for row in pvt_rows)
    tt_gate = bool(finalists)
    decision = "GO" if tt_gate and full_pvt else ("CONDITIONAL" if tt_gate or any(float(row["m_100_ps"]) > 0.0 for row in simple_rows + composite_rows) else "NO-GO")
    write_csv(analysis_dir / "simple_candidate_screen.csv", SCREEN_FIELDS, simple_rows)
    if composite_rows:
        write_csv(analysis_dir / "composite_candidate_screen.csv", SCREEN_FIELDS, composite_rows)
    if pvt_rows:
        write_csv(analysis_dir / "finalist_pvt_confirmation.csv", PVT_FIELDS, pvt_rows)
    save_figures(simple_rows + composite_rows, finalists, pvt_rows, reference, sensor, analysis_dir)
    summary = {
        "decision": decision, "hspice": str(hspice), "hspice_version": run_dc_sweep.hspice_version(hspice),
        "candidate_count": len(candidates), "simple_rows": simple_rows, "composite_rows": composite_rows,
        "finalist_ids": finalists_ids, "pvt_rows": pvt_rows, "reference_measurement_count": len(reference),
        "hspice_scenario_count": next_index, "sensor_evidence": sensor["sources"],
        "scope": "reference-only; no prior sensor experiment rerun",
    }
    write_json(analysis_dir / "summary.json", summary)
    render_report(args.report_output.resolve(), candidates + composites, simple_rows, composite_rows, finalists, pvt_rows, decision)
    print("FTC_REFERENCE_SENSITIVITY_CONTRAST decision={} finalists={} hspice_scenarios={}".format(decision, ",".join(finalists_ids), next_index))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
