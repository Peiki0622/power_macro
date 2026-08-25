#!/usr/bin/env python3
"""Build and run the B-FE1 real-cell multi-tap front-end experiment.

B-FE1 is deliberately independent from the legacy FTC capture deck.  The
generated circuit has only the two inherited delay paths and thirty real LVT
``XOR2_X0P5M_A9TL40`` observation cells.  There is no latch, DFF, M/F chain,
clock legalizer, or behavioral XOR in this file.  HSPICE therefore measures
the physical front-end itself, while the ideal snapshot and spatial-code
interpretation remain a later offline operation.

The runner writes raw solver products only below ``runs/b_fe_frontend`` and
compact, reviewable crossing evidence below
``analysis/b_fe_frontend/bfe1_spatial_observability``.  It refuses to overwrite
an existing run directory, limits the electrical matrix to the four scenarios
defined by the B-FE plan, and records every source/deck hash for auditability.
"""

import argparse
import bisect
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
REPO_ROOT = FTC_ROOT.parents[1]
SCRIPT_ROOT = FTC_ROOT / "scripts"
PHASE1_ROOT = REPO_ROOT / "delay_chain" / "phase1" / "scripts"
for import_path in (SCRIPT_ROOT, PHASE1_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))
import run_dc_sweep  # noqa: E402  # Shared HSPICE version/listing checks.


OBSERVABLE_TAPS = 30
RVT_PREFIX = 4
LVT_PREFIX = 0
XOR_CELL = "XOR2_X0P5M_A9TL40"
LAUNCH_S = 1.0e-9
SLEW_S = 1.0e-12
HOLD_S = 3000.0e-12
RISE_S = 1.0e-12
TRAN_STEP_S = 1.0e-12
STOP_S = 7.0e-9
TR0_FIELD_WIDTH = 13
TR0_MARKER = "$&%#"
T0_CONTRACT = FTC_ROOT / "analysis" / "t0_transient_droop" / "contract" / "T0_TRANSIENT_THREAT_CONTRACT.json"
T0_CADENCE = FTC_ROOT / "analysis" / "t0_transient_droop" / "cadence" / "cadence_summary.json"


def sha256_file(path: Path) -> str:
    """Hash one file in streaming mode without loading large traces in memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    """Read one object-shaped JSON input and reject malformed contracts early."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def authoritative_scenarios() -> Tuple[Dict[str, Any], ...]:
    """Build the bounded B-FE1 matrix from the frozen T0 authority files.

    The two L2 sample phases are not B-FE1 tuning knobs.  They are the T0
    2500-ps diagnostic worst phases recorded for the two formal L2-long
    threats.  Reading and validating them here prevents an unreviewed phase
    literal from drifting into the B-FE1 deck while retaining the plan's exact
    four electrically unique scenarios.
    """

    contract = load_json(T0_CONTRACT)
    cadence = load_json(T0_CADENCE)
    target = cadence.get("target_threat", {})
    if target.get("total_pulse_ps") != 3002.0:
        raise ValueError("B-FE1 requires the authoritative 3002-ps L2 threat")
    reference = cadence.get("target_reference_results", {}).get("control_clock_2500ps", {})
    expected = (
        ("BFE1-095-L2", "t0_5a_0p95_l2_long", 0.95, 0.86, 75.0),
        ("BFE1-110-L2", "t0_5a_1p10_l2_long", 1.10, 0.96, 25.0),
    )
    l2_scenarios = []
    for scenario_id, key, baseline_v, droop_v, expected_phase in expected:
        source = reference.get(key, {})
        if (source.get("baseline_vdd_v") != baseline_v or source.get("Vdroop_v") != droop_v or
                source.get("worst_attack_phase_ps") != expected_phase):
            raise ValueError("T0 authority does not match B-FE1 representative L2 point: {}".format(key))
        l2_scenarios.append({
            "scenario_id": scenario_id,
            "baseline_v": baseline_v,
            "droop_v": droop_v,
            "phase_ps": source["worst_attack_phase_ps"],
            "authority_scenario_key": key,
        })
    return (
        {"scenario_id": "BFE1-095-N", "baseline_v": 0.95, "droop_v": None, "phase_ps": None,
         "authority_scenario_key": None},
        l2_scenarios[0],
        {"scenario_id": "BFE1-110-N", "baseline_v": 1.10, "droop_v": None, "phase_ps": None,
         "authority_scenario_key": None},
        l2_scenarios[1],
    )


# This module-level value is derived rather than hand-maintained so tests,
# rendering, and the persisted manifest all share the same audited matrix.
SCENARIOS = authoritative_scenarios()


def spice(value: float) -> str:
    """Render a finite SI value in a locale-independent HSPICE literal."""

    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite SPICE value: {}".format(value))
    return "{:.12e}".format(number)


def buffer_line(instance: str, output: str, input_node: str, cell: str) -> str:
    """Render one powered six-pin buffer instance with an explanatory port map."""

    return "{name} {out} vdd_monitored vdd_monitored vss_a vss_a {inp} {cell}".format(
        name=instance, out=output, inp=input_node, cell=cell
    )


def delay_path(prefix: str, cell: str, initial_stages: int) -> Tuple[List[str], List[str]]:
    """Create one complete serial path and return its lines and 30 tap names.

    ``prefix`` identifies the physical VT path.  Initial stages are ordinary
    buffers, not masks or controls; every observable tap is retained as a
    named electrical node so the later crossing analysis can audit ordering.
    """

    lines = []
    previous = "s_clk"
    for index in range(initial_stages):
        output = "{}_initial_{:02d}".format(prefix, index)
        lines.append("* {} initial stage: Y={} A={} VDD/VNW=vdd_monitored VPW/VSS=vss_a".format(index, output, previous))
        lines.append(buffer_line("X{}_INIT_{:02d}".format(prefix.upper(), index), output, previous, cell))
        previous = output
    taps = []
    for index in range(OBSERVABLE_TAPS):
        output = "{}_{}".format(prefix, index)
        lines.append("* {} observable tap {:02d}: Y={} A={} VDD/VNW=vdd_monitored VPW/VSS=vss_a".format(prefix.upper(), index, output, previous))
        lines.append(buffer_line("X{}_TAP_{:02d}".format(prefix.upper(), index), output, previous, cell))
        taps.append(output)
        previous = output
    return lines, taps


def xor_bank(rvt_taps: Sequence[str], lvt_taps: Sequence[str]) -> Tuple[List[str], List[str]]:
    """Render exactly one real TL40 XOR for each corresponding tap pair."""

    if len(rvt_taps) != OBSERVABLE_TAPS or len(lvt_taps) != OBSERVABLE_TAPS:
        raise ValueError("B-FE1 requires exactly 30 RVT and 30 LVT taps")
    lines = []
    outputs = []
    for index, (rvt, lvt) in enumerate(zip(rvt_taps, lvt_taps)):
        output = "xor_{}".format(index)
        lines.append("* Real XOR {:02d}: Y={} A=RVT({}) B=LVT({}); no latch load is present.".format(index, output, rvt, lvt))
        # TL40 is an LVT library cell.  Its complete CDL positional order is
        # Y VDD VNW VPW VSS A B; all five power/well ports are explicit.
        lines.append("XXOR_{:02d} {} vdd_monitored vdd_monitored vss_a vss_a {} {} {}".format(index, output, rvt, lvt, XOR_CELL))
        outputs.append(output)
    return lines, outputs


def render_supply(baseline_v: float, droop_v: Optional[float], phase_ps: Optional[float]) -> List[str]:
    """Render the single monitored rail, optionally with the formal L2 PWL.

    The threat is the T0 finite-slope trapezoid: a one-ps fall, a 3000-ps
    hold, and a one-ps recovery.  ``phase_ps`` is relative to the one S_CLK
    rising edge and is used only for the representative L2 response.
    """

    if droop_v is None:
        return [
            "* Normal condition: the monitored rail is constant after t=0.",
            "V_VDD_MONITORED vdd_monitored vss_a DC={}".format(spice(baseline_v)),
        ]
    if phase_ps is None or droop_v >= baseline_v or droop_v <= 0.0:
        raise ValueError("L2 scenario requires a lower droop rail and a phase")
    start = LAUNCH_S + float(phase_ps) * 1.0e-12
    fall_end = start + SLEW_S
    hold_end = fall_end + HOLD_S
    rise_end = hold_end + RISE_S
    return [
        "* Formal T0 L2 representative: VDD_MONITORED uses 1-ps/3000-ps/1-ps PWL.",
        "* The phase is launch-relative; no fixed-voltage reference rail is added.",
        "V_VDD_MONITORED vdd_monitored vss_a PWL(0 {} {} {} {} {} {} {} {} {} {})".format(
            spice(baseline_v), spice(start), spice(baseline_v), spice(fall_end), spice(droop_v),
            spice(hold_end), spice(droop_v), spice(rise_end), spice(baseline_v), spice(STOP_S),
            spice(baseline_v)
        ),
    ]


def render_deck(cells: Mapping[str, Any], scenario: Mapping[str, Any], model_library: Optional[str] = None) -> str:
    """Render one independent B-FE1 HSPICE deck with no capture circuitry."""

    if cells.get("delay_rvt", {}).get("cell") != "BUF_X0P7M_A9TR40":
        raise ValueError("B-FE1 inherited RVT cell changed")
    if cells.get("delay_lvt", {}).get("cell") != "BUF_X0P7M_A9TL40":
        raise ValueError("B-FE1 inherited LVT cell changed")
    source_files = cells.get("source_files", {})
    rvt_cdl = str(source_files.get("rvt_cdl"))
    lvt_cdl = str(source_files.get("lvt_cdl"))
    if not Path(rvt_cdl).is_file() or not Path(lvt_cdl).is_file():
        raise FileNotFoundError("B-FE1 cell CDL source is unavailable")
    # The same TT HSPICE model library as the legacy FTC flow supplies the
    # primitive n/p subcircuits referenced internally by both CDL files.
    # A cell CDL alone is structural netlisting, not a runnable transistor
    # model; rejecting a missing library prevents a misleading empty run.
    resolved_model = str(model_library) if model_library is not None else str(load_json(FTC_ROOT / "ftc_config.json")["model_library"])
    if not Path(resolved_model).is_file():
        raise FileNotFoundError("B-FE1 HSPICE model library is unavailable")
    baseline_v = float(scenario["baseline_v"])
    droop_v = scenario.get("droop_v")
    phase_ps = scenario.get("phase_ps")
    rvt_lines, rvt_taps = delay_path("rvt", cells["delay_rvt"]["cell"], RVT_PREFIX)
    lvt_lines, lvt_taps = delay_path("lvt", cells["delay_lvt"]["cell"], LVT_PREFIX)
    xor_lines, xor_outputs = xor_bank(rvt_taps, lvt_taps)
    lines = [
        "* B-FE1 independent multi-tap transistor front-end; scenario={}.".format(scenario["scenario_id"]),
        "* Only inherited RVT/LVT paths and 30 real XOR2_X0P5M_A9TL40 cells are present.",
        "* There is intentionally no latch, DFF, M/F, legalizer, controller, or behavioral XOR.",
        # ``probe`` is essential: POST=2 otherwise exports every transistor
        # internal node before requested probes, reaches the .tr0 column
        # limit, and can silently truncate the 92 B-FE1 observables.  This
        # option retains only the declared .probe vectors plus TIME.
        ".option post=2 probe nomod measform=3 measdgt=10 runlvl=3",
        ".temp 2.500000000000e+01",
        '.include "{}"'.format(rvt_cdl),
        '.include "{}"'.format(lvt_cdl),
        # The vendor LVT CDL references a small compatibility subcircuit by
        # filename.  The runner copies this no-op include into each task-owned
        # scenario, so the immutable vendor directory is never modified.
        '.include "empty_subckt.sp_cal"',
        '.lib "{}" tt'.format(resolved_model),
        ".param VDD_VALUE={}".format(spice(baseline_v)),
        "",
        "* Port contract: vdd_monitored is the sole PD_SENSE/VDD_MONITORED rail; vss_a is its return.",
        "* No VDD_REF, VSS_REF, PD_CTRL, or independent reference supply exists in this deck.",
    ]
    lines.extend(render_supply(baseline_v, droop_v, phase_ps))
    lines.extend([
        "V_VSS_A vss_a 0 DC=0",
        "* S_CLK port: one 1-ps rising edge at 1 ns, then a constant high level through STOP_S.",
        "V_SCLK s_clk vss_a PWL(0 0 {} 0 {} 'VDD_VALUE' {} 'VDD_VALUE')".format(
            spice(LAUNCH_S - SLEW_S / 2.0), spice(LAUNCH_S + SLEW_S / 2.0), spice(STOP_S)
        ),
        "",
        "* Inherited RVT path: four fixed prefix stages followed by 30 observable taps.",
    ])
    lines.extend(rvt_lines)
    lines.extend(["", "* Inherited LVT path: zero prefix stages followed by 30 observable taps."])
    lines.extend(lvt_lines)
    lines.extend(["", "* New B-FE1 load: one real TL40 XOR per corresponding tap pair."])
    lines.extend(xor_lines)
    lines.extend([
        "",
        "* Complete waveform retention for zero-HSPICE offline crossing reconstruction.",
        # ``vss_a`` is driven by the explicit 0-V source below, so a one-node
        # expression is electrically the required local-rail measurement and
        # has a unique, non-continuation HSPICE label for deterministic parse.
        ".probe tran v(vdd_monitored) v(s_clk) {}".format(" ".join(
            ["v({})".format(node) for node in rvt_taps + lvt_taps + xor_outputs]
        )),
        ".tran {} {}".format(spice(TRAN_STEP_S), spice(STOP_S)),
    ])
    lines.extend([
        # B-FE1.5 deliberately derives every XOR crossing from the retained
        # waveform.  Do not add .measure expressions here: HSPICE writes
        # their requested voltages into .tr0 as extra columns, which weakens
        # the exact TIME + 92-probe retention contract.
        ".end",
        "",
    ])
    return "\n".join(lines)


def parse_ascii_tr0(path: Path) -> Dict[str, Any]:
    """Parse HSPICE W-2024.09 ASCII POST=2 output into named columns.

    HSPICE stores a four-digit record width, sixteen-character labels, and
    thirteen-character numeric fields.  The parser keeps duplicate rounded
    timestamps but rejects true time reversal and malformed records, because
    either condition would invalidate crossing interpolation.
    """

    raw = path.read_text(encoding="ascii", errors="strict")
    width_match = re.match(r"^(\d{4})", raw)
    if width_match is None:
        raise ValueError("B-FE1 .tr0 lacks record width: {}".format(path))
    record_width = int(width_match.group(1))
    label_offset = raw.find("TIME")
    marker_offset = raw.find(TR0_MARKER)
    if label_offset < 0 or marker_offset < 0 or marker_offset <= label_offset:
        raise ValueError("B-FE1 .tr0 lacks ordered TIME/header marker")
    header = raw[label_offset:marker_offset].replace("\r", "").replace("\n", "")
    labels = [header[index * 16:(index + 1) * 16].strip().lower() for index in range(record_width)]
    marker_newline = raw.find("\n", marker_offset)
    payload = re.sub(r"[\s\r\n]", "", raw[marker_newline + 1:])
    if not payload or len(payload) % TR0_FIELD_WIDTH:
        raise ValueError("B-FE1 .tr0 payload is not aligned to 13-character fields")
    token_count = len(payload) // TR0_FIELD_WIDTH
    if token_count % record_width != 1:
        raise ValueError("B-FE1 .tr0 terminal field contract changed")
    record_count = (token_count - 1) // record_width
    columns = {label: [] for label in labels}
    previous_time = -math.inf
    for record_index in range(record_count):
        start = record_index * record_width * TR0_FIELD_WIDTH
        values = []
        for column_index in range(record_width):
            token = payload[start + column_index * TR0_FIELD_WIDTH:start + (column_index + 1) * TR0_FIELD_WIDTH]
            value = float(token)
            if not math.isfinite(value):
                raise ValueError("B-FE1 .tr0 contains a non-finite value")
            values.append(value)
        for label, value in zip(labels, values):
            columns[label].append(value)
        current_time = values[0]
        if current_time < previous_time:
            raise ValueError("B-FE1 .tr0 time decreases at record {}".format(record_index))
        previous_time = current_time
    return {"record_width": record_width, "record_count": record_count, "labels": labels, "columns": columns}


def label_for(node: str) -> str:
    """Return the HSPICE-truncated lower-case label used by the parser."""

    return "v({}".format(node.lower())


def crossing_times(trace: Mapping[str, Any], node: str, rail: str) -> Dict[str, List[float]]:
    """Find rise/fall crossings of ``node - rail/2`` by linear interpolation."""

    time_values = trace["columns"]["time"]
    node_values = trace["columns"][label_for(node)]
    rail_values = trace["columns"][label_for(rail)]
    delta = [node_v - 0.5 * rail_v for node_v, rail_v in zip(node_values, rail_values)]
    result = {"rise_ps": [], "fall_ps": []}
    for index in range(1, len(delta)):
        left, right = delta[index - 1], delta[index]
        if left == 0.0:
            crossing = time_values[index - 1]
        elif left * right > 0.0:
            continue
        else:
            if right == left:
                continue
            fraction = -left / (right - left)
            crossing = time_values[index - 1] + fraction * (time_values[index] - time_values[index - 1])
        if right >= left:
            result["rise_ps"].append(crossing * 1.0e12)
        else:
            result["fall_ps"].append(crossing * 1.0e12)
    return result


def scenario_directory(run_root: Path, scenario_id: str) -> Path:
    """Return a collision-free scenario directory under the task-owned root."""

    return run_root / "scenarios" / scenario_id.lower().replace("-", "_")


def run_one(hspice: Path, cells: Mapping[str, Any], model_library: str, run_root: Path, scenario: Mapping[str, Any]) -> Dict[str, Any]:
    """Render, execute, parse, and retain one of the four B-FE1 scenarios."""

    directory = scenario_directory(run_root, str(scenario["scenario_id"]))
    if directory.exists():
        raise FileExistsError("refusing to overwrite B-FE1 scenario: {}".format(directory))
    directory.mkdir(parents=True)
    shutil.copyfile(FTC_ROOT / "spice/empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    deck = directory / "bfe1.sp"
    deck.write_text(render_deck(cells, scenario, model_library), encoding="ascii")
    result = subprocess.run(
        [str(hspice), deck.name, "-o", "bfe1"], cwd=str(directory),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=600,
    )
    (directory / "hspice_command.log").write_text(
        "command={} {} -o bfe1\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(hspice, deck.name, result.returncode, result.stdout, result.stderr),
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError("B-FE1 HSPICE failed for {}".format(scenario["scenario_id"]))
    listing = directory / "bfe1.lis"
    run_dc_sweep.validate_listing(listing)
    trace_path = directory / "bfe1.tr0"
    trace = parse_ascii_tr0(trace_path)
    expected_labels = ["time", label_for("vdd_monitored"), label_for("s_clk")]
    expected_labels.extend(label_for("rvt_{}".format(index)) for index in range(OBSERVABLE_TAPS))
    expected_labels.extend(label_for("lvt_{}".format(index)) for index in range(OBSERVABLE_TAPS))
    expected_labels.extend(label_for("xor_{}".format(index)) for index in range(OBSERVABLE_TAPS))
    missing = [label for label in expected_labels if label not in trace["columns"]]
    if missing:
        raise ValueError("B-FE1 .tr0 lacks required probes: {}".format(missing))
    if trace["record_width"] != len(expected_labels):
        raise ValueError("B-FE1 .tr0 has unexpected columns; require TIME plus exactly 92 probes")
    crossings = {}
    for index in range(OBSERVABLE_TAPS):
        crossings["xor_{}".format(index)] = crossing_times(trace, "xor_{}".format(index), "vdd_monitored")
    compact = {
        "scenario_id": scenario["scenario_id"],
        "baseline_v": scenario["baseline_v"],
        "droop_v": scenario["droop_v"],
        "phase_ps": scenario["phase_ps"],
        "deck_sha256": sha256_file(deck),
        "trace_sha256": sha256_file(trace_path),
        "hspice_version": run_dc_sweep.hspice_version(hspice),
        "record_count": trace["record_count"],
        "crossings": crossings,
        "required_probe_count": len(expected_labels),
        "tr0_record_width": trace["record_width"],
    }
    (directory / "crossings.json").write_text(json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return compact


def validate_static_deck(text: str) -> None:
    """Reject B-FE1 topology drift before any analog run is launched."""

    # Comments document the intentionally absent structures, so remove them
    # before searching for forbidden electrical tokens.  Instance and source
    # lines remain untouched and are checked below.
    structural_text = "\n".join(line.split("*", 1)[0] for line in text.splitlines())
    if structural_text.count("XXOR_") != OBSERVABLE_TAPS:
        raise ValueError("B-FE1 deck does not contain exactly 30 XOR instances")
    if structural_text.count(XOR_CELL) != OBSERVABLE_TAPS:
        raise ValueError("B-FE1 deck does not use the planned TL40 XOR cell")
    for forbidden in ("LATCH", "DFF", "capture_ck", "dff_ck", "M/F", "legalizer", "VDD_REF", "VSS_REF"):
        if forbidden.lower() in structural_text.lower():
            raise ValueError("B-FE1 deck contains forbidden token: {}".format(forbidden))
    if structural_text.count("V_SCLK") != 1 or "PULSE(" in structural_text:
        raise ValueError("B-FE1 must use exactly one one-rise PWL S_CLK source")
    if structural_text.count(".probe tran") != 1:
        raise ValueError("B-FE1 must have one complete waveform probe statement")
    if ".option post=2 probe" not in structural_text.lower():
        raise ValueError("B-FE1 must use probe-only POST=2 waveform retention")


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run the four-scenario B-FE1 matrix after contract and static checks."""

    parser = argparse.ArgumentParser(description="Run the bounded B-FE1 multi-tap front-end matrix")
    parser.add_argument("--run-dir", type=Path, default=FTC_ROOT / "runs" / "b_fe_frontend")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe1_spatial_observability")
    parser.add_argument("--scenario", choices=[item["scenario_id"] for item in SCENARIOS], action="append")
    args = parser.parse_args(list(argv) if argv is not None else None)
    config = load_json(FTC_ROOT / "ftc_config.json")
    cells = load_json(FTC_ROOT / "discovery/selected_cells.json")
    bfe0 = load_json(FTC_ROOT / "analysis/b_fe_frontend/bfe0_architecture_contract.json")
    if bfe0.get("gate") != "BFE0_FRONTEND_CONTRACT_READY":
        raise RuntimeError("B-FE0 gate is not ready")
    selected = [item for item in SCENARIOS if not args.scenario or item["scenario_id"] in args.scenario]
    if len(selected) != 4:
        raise ValueError("B-FE1 full matrix must contain all four scenarios")
    hspice = Path(config["hspice"])
    version = run_dc_sweep.hspice_version(hspice)
    if str(config["expected_hspice_version"]) not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    if args.run_dir.exists():
        raise FileExistsError("refusing to overwrite B-FE1 run root: {}".format(args.run_dir))
    args.run_dir.mkdir(parents=True)
    (args.run_dir / "manifest.json").write_text(json.dumps({
        "study": "ftc_bfe1_multitap_spatial_observability_v1",
        "hspice_version": version,
        "scenario_count": len(selected),
        "scenarios": selected,
        "bfe0_contract_sha256": sha256_file(FTC_ROOT / "analysis/b_fe_frontend/bfe0_architecture_contract.json"),
        "selected_cells_sha256": sha256_file(FTC_ROOT / "discovery/selected_cells.json"),
        "config_sha256": sha256_file(FTC_ROOT / "ftc_config.json"),
        "t0_contract_sha256": sha256_file(T0_CONTRACT),
        "t0_cadence_sha256": sha256_file(T0_CADENCE),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Static inspection is performed on every scenario deck before the first
    # HSPICE invocation, so an accidental latch/DFF insertion cannot consume a
    # scenario budget and be discovered only after simulation.
    for scenario in selected:
        validate_static_deck(render_deck(cells, scenario, str(config["model_library"])))
    results = [run_one(hspice, cells, str(config["model_library"]), args.run_dir, scenario) for scenario in selected]
    args.analysis_dir.mkdir(parents=True, exist_ok=True)
    (args.analysis_dir / "scenario_manifest.json").write_text(json.dumps({
        "study": "ftc_bfe1_multitap_spatial_observability_v1",
        "hspice_scenarios": len(results),
        "scenarios": results,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("BFE1_TRANSIENT_MATRIX_COMPLETE scenarios={}".format(len(results)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
