#!/usr/bin/env python3
"""Render and run the bounded B-FE2 real-transparent-latch load experiment.

The B-FE2 front end is independent from the historical latch-plus-DFF sensor:
every XOR output drives the D input of one real LATQ cell, and the common G
source stays high for the entire transient.  Consequently this script measures
only the real D-input load; it deliberately contains no closing edge, DFF,
encoder, M/F code, or control state machine.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import bfe1_frontend  # noqa: E402  # Reuse the frozen B-FE1 topology and T0 source reader.
import run_dc_sweep  # noqa: E402  # Reuse the project listing/version validation.


RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "latch_load"
ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "latch_load"
CONTRACT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "BFE2_0_CONTRACT.json"
LATCH_CELL = "LATQ_X0P5M_A9TR40"
SCENARIOS = (
    {"scenario_id": "BFE2L-095-N", "baseline_v": 0.95, "droop_v": None, "phase_ps": None, "authority_scenario_key": None},
    {"scenario_id": "BFE2L-095-L2", "baseline_v": 0.95, "droop_v": 0.86, "phase_ps": 75.0, "authority_scenario_key": "t0_5a_0p95_l2_long"},
    {"scenario_id": "BFE2L-110-N", "baseline_v": 1.10, "droop_v": None, "phase_ps": None, "authority_scenario_key": None},
    {"scenario_id": "BFE2L-110-L2", "baseline_v": 1.10, "droop_v": 0.96, "phase_ps": 25.0, "authority_scenario_key": "t0_5a_1p10_l2_long"},
)


def sha256_file(path: Path) -> str:
    """Hash an input/deck/trace in bounded memory for immutable evidence."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    """Read one required object-shaped contract or manifest."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def latch_bank(xor_outputs: Iterable[str]) -> List[str]:
    """Render the 30 physical latch instances with explicit positional ports.

    Port order follows the audited CDL declaration exactly:
    Q, VDD, VNW, VPW, VSS, D, G.  All power/well ports use the monitored
    sensor rail, while G is the one ideal experiment-control net shared by
    the complete bank.  Q has no artificial load and is only probed.
    """

    lines = []
    for index, xor_node in enumerate(xor_outputs):
        q_node = "q_{}".format(index)
        lines.append("* Latch {:02d}: Q={} VDD/VNW=vdd_monitored VPW/VSS=vss_a D={} G=latch_g.".format(index, q_node, xor_node))
        lines.append("XLATCH_{:02d} {} vdd_monitored vdd_monitored vss_a vss_a {} latch_g {}".format(index, q_node, xor_node, LATCH_CELL))
    return lines


def electrical_signature(cells: Mapping[str, Any], scenario: Mapping[str, Any], hspice_version: str) -> Dict[str, Any]:
    """Return all parameters that can alter this transparent-load waveform."""

    config = read_json(FTC_ROOT / "ftc_config.json")
    return {
        "topology_version": "bfe2_1_30_xor_30_real_latq_g_high_v1",
        "rvt_lvt_buffer_cells": [cells["delay_rvt"]["cell"], cells["delay_lvt"]["cell"]],
        "xor_cell": bfe1_frontend.XOR_CELL, "latch_cell": LATCH_CELL,
        "baseline_v": scenario["baseline_v"], "droop_v": scenario["droop_v"], "phase_ps": scenario["phase_ps"],
        "s_clk_pwl": "one 1ps rising edge at 1ns", "g_pwl": "constant high from t=0 through stop", "close_ps": None,
        "model_sha256": sha256_file(Path(config["model_library"])), "hspice_version": hspice_version,
        "tran_step_ps": bfe1_frontend.TRAN_STEP_S * 1.0e12,
    }


def signature_id(signature: Mapping[str, Any]) -> str:
    """Return the stable SHA256 identity used to reject duplicate simulation."""

    payload = json.dumps(signature, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def render_deck(cells: Mapping[str, Any], scenario: Mapping[str, Any], model_library: Optional[str] = None) -> str:
    """Render one B-FE2.1 transparent-load HSPICE deck without capture logic."""

    rvt_lines, rvt_taps = bfe1_frontend.delay_path("rvt", cells["delay_rvt"]["cell"], bfe1_frontend.RVT_PREFIX)
    lvt_lines, lvt_taps = bfe1_frontend.delay_path("lvt", cells["delay_lvt"]["cell"], bfe1_frontend.LVT_PREFIX)
    xor_lines, xor_outputs = bfe1_frontend.xor_bank(rvt_taps, lvt_taps)
    resolved_model = model_library or read_json(FTC_ROOT / "ftc_config.json")["model_library"]
    rvt_cdl = cells["source_files"]["rvt_cdl"]
    lvt_cdl = cells["source_files"]["lvt_cdl"]
    if not Path(rvt_cdl).is_file() or not Path(lvt_cdl).is_file() or not Path(resolved_model).is_file():
        raise FileNotFoundError("B-FE2.1 physical source is unavailable")
    lines = [
        "* B-FE2.1 real latch D-input-load screen; scenario={}.".format(scenario["scenario_id"]),
        "* Exactly 30 TL40 XOR cells and 30 real LATQ cells; G remains continuously high.",
        ".option post=2 probe nomod measform=3 measdgt=10 runlvl=3", ".temp 2.500000000000e+01",
        '.include "{}"'.format(rvt_cdl), '.include "{}"'.format(lvt_cdl), '.include "empty_subckt.sp_cal"',
        '.lib "{}" tt'.format(resolved_model), ".param VDD_VALUE={}".format(bfe1_frontend.spice(float(scenario["baseline_v"]))),
        "* All electrical cells use PD_SENSE VDD_MONITORED/vss_a; G is external ideal research control.",
    ]
    lines.extend(bfe1_frontend.render_supply(float(scenario["baseline_v"]), scenario.get("droop_v"), scenario.get("phase_ps")))
    lines.extend(["V_VSS_A vss_a 0 DC=0", "V_SCLK s_clk vss_a PWL(0 0 {} 0 {} 'VDD_VALUE' {} 'VDD_VALUE')".format(
        bfe1_frontend.spice(bfe1_frontend.LAUNCH_S - bfe1_frontend.SLEW_S / 2.0), bfe1_frontend.spice(bfe1_frontend.LAUNCH_S + bfe1_frontend.SLEW_S / 2.0), bfe1_frontend.spice(bfe1_frontend.STOP_S)),
        "* G is high before the launch and stays high: this stage excludes close-aperture effects.", "V_LATCH_G latch_g vss_a DC='VDD_VALUE'"])
    lines.extend(rvt_lines + lvt_lines + xor_lines + latch_bank(xor_outputs))
    probes = rvt_taps + lvt_taps + xor_outputs + ["q_{}".format(index) for index in range(30)]
    lines.extend([".probe tran v(vdd_monitored) v(s_clk) v(latch_g) {}".format(" ".join("v({})".format(node) for node in probes)),
                  ".tran {} {}".format(bfe1_frontend.spice(bfe1_frontend.TRAN_STEP_S), bfe1_frontend.spice(bfe1_frontend.STOP_S)), ".end", ""])
    return "\n".join(lines)


def validate_static_deck(text: str) -> None:
    """Reject topology drift before it can consume any B-FE2.1 run budget."""

    netlist = "\n".join(line.split("*", 1)[0] for line in text.splitlines())
    if netlist.count("XXOR_") != 30 or netlist.count("XLATCH_") != 30 or netlist.count(LATCH_CELL) != 30:
        raise ValueError("B-FE2.1 requires exactly 30 real XOR and 30 real latch instances")
    for forbidden in ("DFF", "capture_ck", "M/F", "legalizer", "encoder", "VDD_REF", "PD_CTRL"):
        if forbidden.lower() in netlist.lower():
            raise ValueError("B-FE2.1 contains forbidden topology token: {}".format(forbidden))
    if "V_LATCH_G latch_g vss_a DC='VDD_VALUE'" not in netlist:
        raise ValueError("B-FE2.1 latch G must remain continuously high")
    if ".probe tran" not in netlist:
        raise ValueError("B-FE2.1 requires a complete waveform probe")


def scenario_dir(root: Path, scenario_id: str) -> Path:
    """Map a formal scenario ID to its single task-scoped raw-product folder."""

    return root / "scenarios" / scenario_id.lower().replace("-", "_")


def run_one(hspice: Path, cells: Mapping[str, Any], model_library: str, version: str, root: Path, scenario: Mapping[str, Any]) -> Dict[str, Any]:
    """Run or explicitly reuse exactly one electrically unique B-FE2.1 case."""

    signature = electrical_signature(cells, scenario, version)
    sig_id = signature_id(signature)
    directory = scenario_dir(root, scenario["scenario_id"])
    if directory.exists():
        manifest_path = directory / "scenario_evidence.json"
        if not manifest_path.is_file():
            raise FileExistsError("existing B-FE2.1 directory lacks reusable evidence: {}".format(directory))
        existing = read_json(manifest_path)
        if existing.get("electrical_signature_id") != sig_id or not (directory / "bfe2l.tr0").is_file():
            raise FileExistsError("existing B-FE2.1 directory has a different electrical signature")
        existing["run_disposition"] = "reused"
        return existing
    directory.mkdir(parents=True)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    deck = directory / "bfe2l.sp"
    deck.write_text(render_deck(cells, scenario, model_library), encoding="ascii")
    result = subprocess.run([str(hspice), deck.name, "-o", "bfe2l"], cwd=str(directory), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=600)
    (directory / "hspice_command.log").write_text("command={} {} -o bfe2l\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(hspice, deck.name, result.returncode, result.stdout, result.stderr), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError("B-FE2.1 HSPICE failed: {}".format(scenario["scenario_id"]))
    run_dc_sweep.validate_listing(directory / "bfe2l.lis")
    trace = bfe1_frontend.parse_ascii_tr0(directory / "bfe2l.tr0")
    expected_width = 124  # TIME + rail/S_CLK/G + 30 RVT + 30 LVT + 30 XOR + 30 Q.
    if trace["record_width"] != expected_width:
        raise ValueError("B-FE2.1 trace probe contract changed: {}".format(trace["record_width"]))
    evidence = {"scenario_id": scenario["scenario_id"], "baseline_v": scenario["baseline_v"], "droop_v": scenario["droop_v"], "phase_ps": scenario["phase_ps"], "authority_scenario_key": scenario["authority_scenario_key"], "electrical_signature": signature, "electrical_signature_id": sig_id, "deck_sha256": sha256_file(deck), "tr0_sha256": sha256_file(directory / "bfe2l.tr0"), "hspice_version": version, "record_width": trace["record_width"], "record_count": trace["record_count"], "run_disposition": "new"}
    (directory / "scenario_evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run the fixed four-scenario load screen after static and budget checks."""

    if read_json(CONTRACT).get("gate") != "BFE2_0_LATCH_CONTRACT_READY":
        raise RuntimeError("B-FE2.0 contract is not ready")
    if len(SCENARIOS) != 4:
        raise ValueError("B-FE2.1 has exactly four authorized scenarios")
    config, cells = read_json(FTC_ROOT / "ftc_config.json"), read_json(FTC_ROOT / "discovery" / "selected_cells.json")
    hspice = Path(config["hspice"])
    version = run_dc_sweep.hspice_version(hspice)
    if config["expected_hspice_version"] not in version:
        raise RuntimeError("unexpected HSPICE version")
    for scenario in SCENARIOS:
        validate_static_deck(render_deck(cells, scenario, config["model_library"]))
    results = [run_one(hspice, cells, config["model_library"], version, RUN_ROOT, scenario) for scenario in SCENARIOS]
    ANALYSIS_ROOT.mkdir(parents=True, exist_ok=True)
    (ANALYSIS_ROOT / "BFE2_1_SCENARIO_MANIFEST.json").write_text(json.dumps({"stage": "B-FE2.1", "authorized_new_scenarios": 4, "scenarios": results}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("BFE2_1_LATCH_LOAD_MATRIX_COMPLETE new={} reused={}".format(sum(item["run_disposition"] == "new" for item in results), sum(item["run_disposition"] == "reused" for item in results)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
