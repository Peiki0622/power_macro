#!/usr/bin/env python3
"""Execute the gate-driven FTC D0-BR interleaved-capture study.

The D0-A study stopped at ``ARCHITECTURE_ESCALATION_REQUIRED`` because the
frozen capture DFF receives a physically real, but formally illegal, narrow
clock pulse.  D0-BR is deliberately not a runtime-controller implementation:
it first asks whether one *shared* analogue sensing path can accept the T0
cadence at all.  A failing answer terminates the capture-bank route before a
pulse legalizer, extra DFF, RTL, or broad HSPICE campaign can be introduced.

BR1 first records the result for one physically derived fixed S_CLK duty.  A
fixed-duty failure is deliberately not treated as proof that every source
high/low allocation fails: BR1R then evaluates three bounded, data-derived
fall retimings with the same 2075 ps launch period and frozen topology.  Only
BR1R may call the shared path physically blocked.  Neither path implements a
pulse legalizer, capture bank, RTL, or a copied sensor lane.  All generated
electrical products are confined to the task-owned ``runs`` directory; compact
JSON/CSV/report evidence is confined to the D0-BR analysis directory.
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
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


# D0-BR must retain exactly the real-cell electrical construction approved by
# M0/T0.  Importing the T0 renderer rather than copying its sensor topology
# prevents this study from silently selecting a historical RTL/Vernier sensor.
FTC_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = FTC_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import run_t0_transient_droop_characterization as t0  # noqa: E402


STUDY = "ftc_d0b_interleaved_capture_architecture_closure_v1"
ANALYSIS = FTC_ROOT / "analysis" / "d0_interleaved_capture"
RUN_ROOT = FTC_ROOT / "runs" / "d0_interleaved_capture"
REPORT = FTC_ROOT / "reports" / "FTC_D0_INTERLEAVED_CAPTURE_ARCHITECTURE_CLOSURE.md"
PLAN = FTC_ROOT.parent.parent / "plans" / "ftc_d0b_interleaved_capture_architecture_plan.md"

# T0's downstream guarantee is an aggregate probe cadence.  It is not the
# 400 MHz calibration clock, and no D0-BR calculation is allowed to change it.
RUNTIME_PERIOD_PS = 2075.0
EDGE_GUARD_PS = 25.0
LOW_RATIO_LIMIT = 0.10

# BR1R samples a deliberately small source-high-time bracket, not a duty-cycle
# sweep.  The values are reproduced from retained BR1 propagation evidence:
# 750 ps is 100 ps after the slowest initial XOR rise, 1250 ps is 100 ps after
# the slowest initial raw-CK rise, and 1000 ps is their one midpoint.  The
# runner re-derives and verifies this rationale before it can create a deck.
BR1R_FALL_OFFSETS_PS: Tuple[float, ...] = (750.0, 1000.0, 1250.0)
BR1R_SOURCE_SETTLE_PS = 100.0
BR1R_MEASURED_EDGE_LIMIT = 6
BR1R_DREF_DISTORTION_LIMIT_PS = 25.0

# These are the two and only BR1 electrical identities.  Their codes, depth,
# waveform and phase are the formal T0 L2 / 3002 ps target values used by D0-A.
BR1_SPECS: Tuple[Mapping[str, Any], ...] = (
    {
        "scenario_key": "br1_0p95_l2_repeated_sensor",
        "baseline_vdd_v": 0.95,
        "margin_level": "L2",
        "Vdroop_v": 0.86,
        "hold_ps": 3000.0,
        "phase_ps": 75.0,
    },
    {
        "scenario_key": "br1_1p10_l2_repeated_sensor",
        "baseline_vdd_v": 1.10,
        "margin_level": "L2",
        "Vdroop_v": 0.96,
        "hold_ps": 3000.0,
        "phase_ps": 25.0,
    },
)

# Every BR0 input is repository-relative.  Listing the individual crossing
# files, rather than hashing their directory wholesale, makes a future PD1
# contract addition or removal visible in review.
INPUTS: Mapping[str, str] = {
    "d0a_physical_timing_budget": "analysis/d0_runtime_fastpath/a1_physical_budget/physical_timing_budget.json",
    "d0a_candidate_timing_contract": "analysis/d0_runtime_fastpath/a2_single_path_candidate/candidate_timing_contract.json",
    "d0a_lane_count_analysis": "analysis/d0_runtime_fastpath/a5_interleave_review/lane_count_analysis.json",
    "d0a_gate": "analysis/d0_runtime_fastpath/reports/D0_A_GATE_STATUS.json",
    "t0_downstream_contract": "analysis/t0_transient_droop/contract/T0_DOWNSTREAM_D0_TIMING_CONTRACT.json",
    "m0_single_probe_contract": "analysis/m0_detection_margin_characterization/probe_contract/single_probe_contract.json",
    "rf_sequential_timing": "controller/refrequency/library_audit/sequential_cell_timing_capability.json",
    "pd1_configuration_crossing": "controller/pd1_power_domain_interface/crossings/configuration_crossing_contract.json",
    "pd1_crossing_inventory": "controller/pd1_power_domain_interface/crossings/crossing_inventory.json",
    "pd1_qfinal_return": "controller/pd1_power_domain_interface/crossings/qfinal_return_contract.json",
    "pd1_reset_crossing": "controller/pd1_power_domain_interface/crossings/reset_crossing_contract.json",
    "pd1_sclk_crossing": "controller/pd1_power_domain_interface/crossings/sclk_crossing_contract.json",
    "m1_downstream_handoff": "controller/m1_detection_margin/contract/M1_DOWNSTREAM_T0_D0_HANDOFF.json",
    "h0_downstream_handoff": "controller/h0_calibration_detection_handoff/contract/downstream_detection_handoff.json",
    "d0br_plan": "../../plans/ftc_d0b_interleaved_capture_architecture_plan.md",
}


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 without copying PDK or listing data."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    """Read one object-shaped evidence file and fail closed on malformed JSON."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Publish compact deterministic evidence at one explicit task-owned path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    """Write rectangular scalar evidence while preserving missing measures as blank."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: "" if row.get(name) is None else row.get(name) for name in fields})


def input_path(raw: str) -> Path:
    """Resolve the one plan path outside ``delay_chain/ftc`` without ambiguity."""

    return FTC_ROOT.parent.parent / raw[6:] if raw.startswith("../../") else FTC_ROOT / raw


def accounting(new: int = 0, reused: int = 0, reparsed: int = 0, equivalent: int = 0) -> Dict[str, int]:
    """Use the plan's mandatory HSPICE ledger schema in every stage artifact."""

    return {
        "new_hspice_scenarios": int(new),
        "reused_hspice_scenarios": int(reused),
        "reparsed_hspice_scenarios": int(reparsed),
        "electrically_equivalent_reuse_scenarios": int(equivalent),
        "forbidden_flow_runs": 0,
    }


def baseline_path() -> Path:
    """Return BR0's sole published baseline record."""

    return ANALYSIS / "baseline" / "frozen_input_sha256.json"


def br1_root() -> Path:
    """Return the compact evidence directory owned exclusively by BR1."""

    return ANALYSIS / "br1_shared_sensor_cadence"


def br1r_root() -> Path:
    """Return BR1R's compact retiming evidence directory, never a run root."""

    return ANALYSIS / "br1r_fall_retiming"


def verify_baseline_state() -> Dict[str, Any]:
    """Check each D0-A/T0/RF prerequisite before creating any new deck."""

    d0a_budget = read_json(input_path(INPUTS["d0a_physical_timing_budget"]))
    d0a_candidate = read_json(input_path(INPUTS["d0a_candidate_timing_contract"]))
    d0a_lanes = read_json(input_path(INPUTS["d0a_lane_count_analysis"]))
    d0a_gate = read_json(input_path(INPUTS["d0a_gate"]))
    t0_contract = read_json(input_path(INPUTS["t0_downstream_contract"]))
    m0 = read_json(input_path(INPUTS["m0_single_probe_contract"]))
    rf = read_json(input_path(INPUTS["rf_sequential_timing"]))

    if d0a_gate.get("decision") != "ARCHITECTURE_ESCALATION_REQUIRED":
        raise RuntimeError("D0-BR requires D0-A ARCHITECTURE_ESCALATION_REQUIRED")
    if d0a_candidate.get("root_cause") != "measured_dff_ck_high_width_violates_formal_cell_minimum":
        raise RuntimeError("D0-BR must retain D0-A's illegal raw-CK root cause")
    if d0a_lanes.get("P_lane_verified_ps") is not None:
        raise RuntimeError("D0-A lane cadence unexpectedly claims physical closure")
    if float(t0_contract["runtime_probe_period"]["maximum_period_ps"]) != RUNTIME_PERIOD_PS:
        raise RuntimeError("T0 runtime cadence drifted from 2075 ps")
    if t0_contract.get("decision") != "CONDITIONAL_GO":
        raise RuntimeError("D0-BR requires T0 CONDITIONAL_GO")
    if m0.get("q_decision", {}).get("two_samples_required") is not True:
        raise RuntimeError("M0 real-DFF two-observation contract is missing")

    capability = next(
        (row for row in rf.get("used_cell_capabilities", []) if row.get("cell_type") == "DFFRPQ_X0P5M_A9TR40"),
        None,
    )
    if capability is None:
        raise RuntimeError("RF timing audit lacks DFFRPQ_X0P5M_A9TR40")
    required = {
        "minimum_ck_high_width_ns": 1.0,
        "minimum_ck_low_width_ns": 1.0,
        "minimum_reset_width_ns": 1.0,
        "recovery_ns": 1.0,
        "removal_ns": 0.5,
    }
    for key, expected in required.items():
        if float(capability.get(key, -1.0)) != expected:
            raise RuntimeError("RF {} changed from {} ns".format(key, expected))
    if not all(item.get("dff_ck_high_width_ps", math.inf) < 1000.0 for item in d0a_budget.get("physical_diagnostics", [])):
        raise RuntimeError("D0-A physical narrow-CK evidence is incomplete")
    return {
        "d0a_decision": d0a_gate["decision"],
        "t0_pmax_coverage_ps": RUNTIME_PERIOD_PS,
        "p_lane_verified_ps": d0a_lanes["P_lane_verified_ps"],
        "blocking_root_cause": d0a_candidate["root_cause"],
        "dff_timing_checks_ns": required,
    }


def run_br0() -> Dict[str, Any]:
    """Freeze all D0-BR authority bytes; this phase never starts HSPICE."""

    if not PLAN.is_file():
        raise RuntimeError("D0-BR governing plan is missing: {}".format(PLAN))
    hashes: Dict[str, Dict[str, str]] = {}
    for name, raw in INPUTS.items():
        path = input_path(raw)
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError("D0-BR input is missing or empty: {}".format(path))
        hashes[name] = {"path": raw, "sha256": sha256_file(path)}
    record = {
        "schema_version": 1,
        "study": STUDY,
        "stage": "D0-BR0",
        "gate": "D0_BR_BASELINE_READY",
        "authority_state": verify_baseline_state(),
        "inputs": hashes,
        "scope": {
            "runtime_rtl_implemented": False,
            "sensor_core_modified": False,
            "h0_m1_t0_modified": False,
            "full_campaign_reruns_forbidden": True,
            "detection_only_capture_research_authorized": True,
        },
        "simulation_accounting": accounting(),
    }
    write_json(baseline_path(), record)
    return record


def finite(value: Any) -> Optional[float]:
    """Convert an HSPICE scalar to a finite number without inventing zero."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_measurements(path: Path) -> Dict[str, Optional[float]]:
    """Read one HSPICE MEASFORM=3 row and retain every failed measure as None."""

    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
             if line.strip() and not line.lstrip().startswith("$")]
    header = next((index for index, line in enumerate(lines) if "," in line), None)
    if header is None or header + 1 >= len(lines):
        raise RuntimeError("HSPICE measurement CSV is incomplete: {}".format(path))
    names, values = lines[header].split(","), lines[header + 1].split(",")
    if len(names) != len(values):
        raise RuntimeError("HSPICE measurement column mismatch: {}".format(path))
    return {name.strip(): finite(value.strip()) for name, value in zip(names, values)}


def ps_difference(later: Optional[float], earlier: Optional[float]) -> Optional[float]:
    """Return one picosecond interval only when both measured crossings exist."""

    return None if later is None or earlier is None else round((later - earlier) * 1.0e12, 6)


def require_hspice() -> Tuple[Path, Dict[str, str], str]:
    """Require D0-A's reviewed container-local HSPICE environment before BR1."""

    if os.environ.get("CONDA_DEFAULT_ENV") != "DL":
        raise RuntimeError("D0-BR HSPICE requires CONDA_DEFAULT_ENV=DL")
    executable = Path("/home/zhupl25/.local/bin/hspice")
    if not executable.is_file() or not os.access(str(executable), os.X_OK):
        raise RuntimeError("container-local HSPICE is unavailable: {}".format(executable))
    version = subprocess.run([str(executable), "-v"], check=False, timeout=60,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if version.returncode != 0:
        raise RuntimeError("HSPICE version query failed: {}".format(version.stderr.strip()))
    environment = {
        "conda_env": os.environ["CONDA_DEFAULT_ENV"],
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
    }
    return executable, environment, (version.stdout + version.stderr).strip()


def retained_inventory() -> Dict[str, Any]:
    """Audit old scalar evidence before authorising BR1's two new diagnostics."""

    m0_root = FTC_ROOT / "runs" / "m0_detection_margin_characterization"
    t0_root = FTC_ROOT / "runs" / "t0_transient_droop"
    m0_listings, t0_listings = sorted(m0_root.rglob("*.lis")), sorted(t0_root.rglob("*.lis"))
    m0_measures, t0_measures = sorted(m0_root.rglob("*.mt0.csv")), sorted(t0_root.rglob("*.mt0.csv"))
    if (len(m0_listings), len(t0_listings), len(m0_measures), len(t0_measures)) != (91, 515, 91, 514):
        raise RuntimeError("retained M0/T0 evidence inventory drifted")
    return {
        "m0_listing_count": len(m0_listings),
        "t0_listing_count": len(t0_listings),
        "m0_measurement_count": len(m0_measures),
        "t0_measurement_count": len(t0_measures),
        "m0_tr0_count": len(list(m0_root.rglob("*.tr0"))),
        "t0_tr0_count": len(list(t0_root.rglob("*.tr0"))),
        "can_prove_repeated_sensor_rearm": False,
        "reason": "retained evidence is scalar single-probe data with no waveform and no second S_CLK launch",
    }


def br1_fall_offset_ps() -> float:
    """Derive the one permitted BR1 S_CLK fall time from D0-A physical edges.

    BR1 may not sweep pulse duty.  It therefore waits until the latest already
    measured primary raw-CK falling edge across the two formal target points,
    then adds exactly one retained T0 boundary-resolution quantum.  This is a
    deterministic construction from existing evidence, not a tuned parameter.
    """

    budget = read_json(input_path(INPUTS["d0a_physical_timing_budget"]))
    latest = max(float(item["sclk_rise_to_ck_fall_ps"]) for item in budget["physical_diagnostics"])
    return round(latest + EDGE_GUARD_PS, 6)


def replace_source_line(deck: str, prefix: str, replacement: str) -> str:
    """Replace exactly one known source line while rejecting renderer drift."""

    lines = deck.splitlines()
    indices = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(indices) != 1:
        raise RuntimeError("expected exactly one {} line in T0 deck".format(prefix.rstrip()))
    lines[indices[0]] = replacement
    return "\n".join(lines) + "\n"


def repeated_sclk_pwl(launch0_s: float, launch1_s: float, fall0_s: float, stop_s: float) -> str:
    """Render exactly two rising launches and one physically derived falling edge.

    The second level remains high through simulation end.  This intentionally
    prevents a second falling edge from creating an unrelated third event, so
    the BR1 edge-count gate attributes every extra edge to the first fall or
    the second rising launch only.
    """

    edge = 1.0e-12
    if not (0.0 < launch0_s < fall0_s < launch1_s < stop_s):
        raise ValueError("BR1 S_CLK event order is not strictly monotonic")
    return t0.physical.pwl([
        (0.0, 0),
        (launch0_s - edge, 0), (launch0_s, 1),
        (fall0_s, 1), (fall0_s + edge, 0),
        (launch1_s - edge, 0), (launch1_s, 1), (stop_s, 1),
    ])


def render_br1_deck(context: Mapping[str, Any], parameters: Mapping[str, Any], fall_offset_ps: float) -> Tuple[str, Dict[str, float]]:
    """Render a repeated-probe sensor-only deck from the exact T0 topology.

    The frozen DFF instance remains in the deck with its asynchronous reset
    held high.  That preserves its D and CK input capacitances while ensuring
    BR1 answers sensing-path re-arm rather than capture-context recovery.
    No sensor instance, M/F load, XOR topology, DFF family, or power-domain
    abstraction is changed; only the external S_CLK/reset waveforms and new
    scalar measures differ from the approved T0 source.
    """

    base = t0.render_deck(context, parameters).rstrip()
    if not base.endswith(".end"):
        raise RuntimeError("T0 renderer did not produce a deck terminator")
    timing = t0.shifted_probe_timing(parameters)
    launch0 = timing["launch_time_s"]
    launch1 = launch0 + RUNTIME_PERIOD_PS * 1.0e-12
    fall0 = launch0 + float(fall_offset_ps) * 1.0e-12
    # The source remains high after launch1.  Stop after the frozen droop has
    # fully recovered and after a full nominal 1 ns observation tail.
    droop_end = launch0 + (float(parameters["phase_ps"]) + float(parameters["t_fall_ps"]) +
                           float(parameters["t_hold_ps"]) + float(parameters["t_rise_ps"])) * 1.0e-12
    stop = max(launch1 + 1.5e-9, droop_end + 1.0e-9)
    source = repeated_sclk_pwl(launch0, launch1, fall0, stop)
    deck = replace_source_line(base, "V_CTRL_SCLK ", "V_CTRL_SCLK ctrl_sclk vss_a {}".format(source))
    deck = replace_source_line(deck, "V_CTRL_DFF_RESET ", "V_CTRL_DFF_RESET ctrl_dff_reset vss_a PWL(0 1 {} 1)".format(t0.physical.spice(stop)))
    # ``replace_source_line`` restores a trailing newline after the inherited
    # T0 terminator.  Strip that newline before removing the marker; removing
    # four bytes from ``.end\n`` would otherwise leave a standalone ``.`` that
    # HSPICE correctly rejects as an unknown control statement.
    deck = deck.rstrip()
    if not deck.endswith(".end"):
        raise RuntimeError("BR1 source replacement lost the T0 deck terminator")
    body = deck[:-len(".end")].rstrip()
    prelaunch = launch1 - 1.0e-12
    measures: List[str] = [
        "* D0-BR1: repeated shared-sensor diagnostic; capture DFF is held reset.",
        "* No pulse legalizer, capture bank, RTL, ideal delay, or topology rewrite is present.",
        ".measure tran b1_sclk_rise0 WHEN v(s_clk,vss_a)='V(vdd_a,vss_a)/2' RISE=1",
        ".measure tran b1_sclk_fall0 WHEN v(s_clk,vss_a)='V(vdd_a,vss_a)/2' FALL=1",
        ".measure tran b1_sclk_rise1 WHEN v(s_clk,vss_a)='V(vdd_a,vss_a)/2' RISE=2",
    ]
    # Three rising crossings expose exactly the failure BR1 must detect: two
    # intended launches plus at most one falling-edge-induced extra event.
    # Failed third-edge measures remain explicit ``None`` in the JSON report.
    for node, short in (("xor_29", "xor"), ("medium_out", "medium"), ("dff_ck", "raw_ck")):
        for edge_index in (1, 2, 3):
            measures.append(
                ".measure tran b1_{}_rise{} WHEN v({},vss_a)='V(vdd_a,vss_a)/2' RISE={} TD={}".format(
                    short, edge_index, node, edge_index, t0.physical.spice(launch0)))
        for edge_index in (1, 2):
            measures.append(
                ".measure tran b1_{}_fall{} WHEN v({},vss_a)='V(vdd_a,vss_a)/2' FALL={} TD={}".format(
                    short, edge_index, node, edge_index, t0.physical.spice(launch0)))
        measures.extend([
            ".measure tran b1_{}_prelaunch FIND v({},vss_a) AT={}".format(short, node, t0.physical.spice(prelaunch)),
            ".measure tran b1_{}_vdd_prelaunch FIND v(vdd_a,vss_a) AT={}".format(short, t0.physical.spice(prelaunch)),
        ])
    return body + "\n" + "\n".join(measures) + "\n.end\n", {
        "launch0_s": launch0,
        "fall0_s": fall0,
        "launch1_s": launch1,
        "prelaunch_s": prelaunch,
        "stop_s": stop,
        "fall_offset_ps": float(fall_offset_ps),
    }


def scenario_identity(spec: Mapping[str, Any], parameters: Mapping[str, Any], fall_offset_ps: float) -> str:
    """Derive a collision-resistant run directory from all electrical inputs."""

    payload = json.dumps({"spec": dict(spec), "parameters": dict(parameters), "fall_offset_ps": fall_offset_ps},
                         sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "{}__{}".format(spec["scenario_key"], hashlib.sha256(payload.encode("ascii")).hexdigest()[:20])


def run_br1_scenario(context: Mapping[str, Any], spec: Mapping[str, Any], fall_offset_ps: float) -> Tuple[Dict[str, Any], bool]:
    """Reuse or execute exactly one approved BR1 repeated-sensor diagnostic.

    The returned result always carries ``hspice_executed``.  It is a
    historical, scenario-identity property rather than an invocation-local
    counter: a later idempotent evidence rebuild must not erase the fact that
    this electrically unique deck was previously run.  ``was_reused`` still
    describes the current invocation, so reviewers can distinguish reuse from
    a new simulator launch without double-counting physical scenarios.
    """

    parameters = t0.parameters_for(float(spec["baseline_vdd_v"]), str(spec["margin_level"]),
                                   float(spec["Vdroop_v"]), float(spec["hold_ps"]), float(spec["phase_ps"]))
    deck, timing = render_br1_deck(context, parameters, fall_offset_ps)
    deck_sha = hashlib.sha256(deck.encode("utf-8")).hexdigest()
    scenario = RUN_ROOT / "br1_shared_sensor_cadence" / scenario_identity(spec, parameters, fall_offset_ps)
    manifest_path, measurement_path = scenario / "scenario_manifest.json", scenario / "br1.mt0.csv"
    if manifest_path.is_file() and measurement_path.is_file() and (scenario / "br1.lis").is_file():
        manifest = read_json(manifest_path)
        if (manifest.get("deck_sha256") != deck_sha or manifest.get("parameters") != parameters or
                manifest.get("spec") != dict(spec) or manifest.get("completion_status") != "PASS"):
            raise RuntimeError("retained BR1 run does not match its frozen identity: {}".format(scenario))
        t0.physical.run_dc_sweep.validate_listing(scenario / "br1.lis")
        # Version-1 manifests created before this field existed remain usable
        # only when their retained command log proves a successful physical
        # HSPICE launch.  Upgrade that small task-owned manifest in place so
        # all subsequent reports retain a deterministic execution ledger.
        historically_executed = manifest.get("hspice_executed")
        if historically_executed is None:
            command_log = scenario / "hspice_command.log"
            if not command_log.is_file() or "returncode=0" not in command_log.read_text(encoding="utf-8", errors="replace"):
                raise RuntimeError("retained BR1 result has no successful HSPICE execution evidence: {}".format(scenario))
            manifest["hspice_executed"] = True
            write_json(manifest_path, manifest)
            historically_executed = True
        if historically_executed is not True:
            raise RuntimeError("retained BR1 result was not physically executed: {}".format(scenario))
        return {"spec": dict(spec), "parameters": parameters, "timing": timing, "scenario_path": str(scenario),
                "deck_sha256": deck_sha, "hspice_executed": True,
                "measurements": parse_measurements(measurement_path)}, True

    hspice, environment, version = require_hspice()
    scenario.mkdir(parents=True, exist_ok=True)
    (scenario / "br1.sp").write_text(deck, encoding="utf-8")
    empty_subckt = FTC_ROOT / "spice" / "empty_subckt.sp_cal"
    if not empty_subckt.is_file():
        raise RuntimeError("required immutable empty_subckt include is missing")
    shutil.copyfile(str(empty_subckt), str(scenario / empty_subckt.name))
    manifest = {
        "schema_version": 1,
        "study": STUDY,
        "stage": "D0-BR1",
        "diagnostic_only": True,
        "spec": dict(spec),
        "parameters": parameters,
        "timing": timing,
        "deck_sha256": deck_sha,
        "container_hspice": str(hspice),
        "hspice_version": version,
        "environment": environment,
        "companion_include": {"path": "delay_chain/ftc/spice/empty_subckt.sp_cal", "sha256": sha256_file(empty_subckt)},
        "completion_status": "RUNNING",
        # This field starts false before subprocess.run and flips only after a
        # zero-return HSPICE process plus listing validation.  It makes the
        # compact BR1 ledger stable across later no-run evidence rebuilds.
        "hspice_executed": False,
        "reason": "retained one-probe scalar evidence cannot prove 2075 ps shared-sensor re-arm",
    }
    write_json(manifest_path, manifest)
    result = subprocess.run([str(hspice), "br1.sp", "-o", "br1"], cwd=str(scenario), check=False, timeout=900,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    (scenario / "hspice_command.log").write_text(
        "returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr),
        encoding="utf-8")
    if result.returncode != 0:
        manifest["completion_status"] = "FAIL"
        manifest["failure"] = "HSPICE returned {}".format(result.returncode)
        write_json(manifest_path, manifest)
        raise RuntimeError("BR1 HSPICE failed: {}".format(scenario))
    t0.physical.run_dc_sweep.validate_listing(scenario / "br1.lis")
    if not measurement_path.is_file():
        raise RuntimeError("BR1 measurement file is missing: {}".format(scenario))
    manifest["completion_status"] = "PASS"
    manifest["hspice_executed"] = True
    manifest["measurement_file"] = measurement_path.name
    write_json(manifest_path, manifest)
    return {"spec": dict(spec), "parameters": parameters, "timing": timing, "scenario_path": str(scenario),
            "deck_sha256": deck_sha, "hspice_executed": True,
            "measurements": parse_measurements(measurement_path)}, False


def measured_crossings(values: Mapping[str, Optional[float]], prefix: str, node: str,
                      direction: str, limit: int) -> List[float]:
    """Return all recorded crossings for one node without assigning a probe.

    HSPICE names crossings globally (``rise1``, ``rise2`` ...), but those
    ordinal names do *not* encode which S_CLK transition caused them.  This
    helper intentionally exposes only the chronological samples.  Causal
    ownership is assigned later by measured S_CLK time windows, never by a
    matching global suffix on XOR and raw-CK measures.
    """

    return [value for index in range(1, limit + 1)
            for value in (values.get("{}_{}_{}{}".format(prefix, node, direction, index)),)
            if value is not None]


def crossings_in_window(crossings: Sequence[float], start_s: float, end_s: float) -> List[float]:
    """Select crossings in a half-open source-causal interval ``[start, end)``."""

    return [crossing for crossing in crossings if start_s <= crossing < end_s]


def causal_window_analysis(result: Mapping[str, Any], prefix: str, rise_limit: int,
                           fall_limit: int, require_untruncated_measurement: bool) -> Dict[str, Any]:
    """Classify a repeated sensor trace by its three measured S_CLK causes.

    The source sequence is always ``rise0 -> fall0 -> rise1``.  A node edge is
    therefore attributable to probe0 only before measured ``fall0``, to the
    falling wave only before measured ``rise1``, and to probe1 only afterwards.
    This deliberately makes a late falling-wave edge a collision instead of
    silently relabelling it as probe1.  D_ref is calculated only when a window
    contains exactly one XOR and one raw-CK rising event, so no global edge
    ordinal can accidentally pair distinct physical causes.
    """

    values, timing = result["measurements"], result["timing"]
    source_edges = {
        "rise0_s": values.get("{}_sclk_rise0".format(prefix)),
        "fall0_s": values.get("{}_sclk_fall0".format(prefix)),
        "rise1_s": values.get("{}_sclk_rise1".format(prefix)),
    }
    source_failures: List[str] = []
    if any(value is None for value in source_edges.values()):
        source_failures.append("missing_measured_sclk_transition")
        # Timing values are retained only to produce an inspectable, bounded
        # record after a simulator measurement failure.  A missing measured
        # source edge remains a hard Gate failure and never becomes a pass.
        rise0 = float(timing["launch0_s"])
        fall0 = float(timing["fall0_s"])
        rise1 = float(timing["launch1_s"])
    else:
        rise0 = float(source_edges["rise0_s"])
        fall0 = float(source_edges["fall0_s"])
        rise1 = float(source_edges["rise1_s"])
    if not (rise0 < fall0 < rise1 < float(timing["stop_s"])):
        source_failures.append("sclk_causal_order_is_not_strict")

    windows = (
        ("probe0_rising", rise0, fall0, "S_CLK rise0"),
        ("falling_wave", fall0, rise1, "S_CLK fall0"),
        ("probe1_rising", rise1, float(timing["stop_s"]), "S_CLK rise1"),
    )
    all_edges = {
        node: {
            "rise": measured_crossings(values, prefix, node, "rise", rise_limit),
            "fall": measured_crossings(values, prefix, node, "fall", fall_limit),
        }
        for node in ("xor", "medium", "raw_ck")
    }
    failures: List[str] = list(source_failures)
    window_records: List[Dict[str, Any]] = []
    for window_name, start_s, end_s, source_cause in windows:
        nodes: Dict[str, Dict[str, Any]] = {}
        for node in ("xor", "medium", "raw_ck"):
            rises = crossings_in_window(all_edges[node]["rise"], start_s, end_s)
            falls = crossings_in_window(all_edges[node]["fall"], start_s, end_s)
            nodes[node] = {
                "rise_times_s": rises,
                "fall_times_s": falls,
                "rise_count": len(rises),
                "fall_count": len(falls),
            }
            if len(rises) != 1:
                failures.append("{}_{}_rise_count_is_{}_not_1".format(window_name, node, len(rises)))
            if len(falls) != 1:
                failures.append("{}_{}_fall_count_is_{}_not_1".format(window_name, node, len(falls)))
        xor_rises, raw_rises = nodes["xor"]["rise_times_s"], nodes["raw_ck"]["rise_times_s"]
        d_ref = ps_difference(raw_rises[0], xor_rises[0]) if len(xor_rises) == len(raw_rises) == 1 else None
        if d_ref is None:
            failures.append("{}_D_ref_is_ambiguous".format(window_name))
        elif d_ref <= 0.0:
            failures.append("{}_D_ref_is_not_positive".format(window_name))
        completion_s = max((nodes[node]["fall_times_s"][0] for node in nodes
                            if len(nodes[node]["fall_times_s"]) == 1), default=None)
        completion_margin = ps_difference(end_s, completion_s)
        if completion_margin is None or completion_margin < EDGE_GUARD_PS:
            failures.append("{}_completion_margin_below_{}ps".format(window_name, EDGE_GUARD_PS))
        window_records.append({
            "name": window_name,
            "source_cause": source_cause,
            "start_s": start_s,
            "end_s": end_s,
            "nodes": nodes,
            "d_ref_ps": d_ref,
            "completion_time_s": completion_s,
            "completion_margin_ps": completion_margin,
        })

    prelaunch_ratios: Dict[str, Optional[float]] = {}
    for node in ("xor", "medium", "raw_ck"):
        value = values.get("{}_{}_prelaunch".format(prefix, node))
        rail = values.get("{}_{}_vdd_prelaunch".format(prefix, node))
        ratio = None if value is None or rail is None or rail <= 0.0 else value / rail
        prelaunch_ratios[node] = None if ratio is None else round(ratio, 9)
        if ratio is None or ratio > LOW_RATIO_LIMIT:
            failures.append("{}_not_low_before_rise1".format(node))

    if require_untruncated_measurement:
        for node in ("xor", "medium", "raw_ck"):
            for direction, limit in (("rise", rise_limit), ("fall", fall_limit)):
                if len(all_edges[node][direction]) == limit:
                    failures.append("{}_{}_measurement_limit_reached".format(node, direction))
    probe0_dref, probe1_dref = window_records[0]["d_ref_ps"], window_records[2]["d_ref_ps"]
    if probe0_dref is not None and probe1_dref is not None:
        difference = round(abs(probe1_dref - probe0_dref), 6)
        if difference > BR1R_DREF_DISTORTION_LIMIT_PS:
            failures.append("probe1_D_ref_shift_exceeds_{}ps".format(BR1R_DREF_DISTORTION_LIMIT_PS))
    else:
        difference = None

    return {
        "measurement_prefix": prefix,
        "measured_source_edges_s": source_edges,
        "measurement_limits": {"rise": rise_limit, "fall": fall_limit},
        "event_windows": window_records,
        "prelaunch_ratios": prelaunch_ratios,
        "probe1_minus_probe0_d_ref_ps": difference,
        "failures": sorted(set(failures)),
        "gate": "CAUSAL_WINDOW_PASS" if not failures else "CAUSAL_WINDOW_FAIL",
    }


def classify_br1(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Reclassify the fixed-fall BR1 evidence by source-causal time windows.

    The retained BR1 deck measures only three rises and two falls per node, but
    it is still sufficient to show its late falling wave escapes into the
    probe1 window.  It cannot certify a passing schedule; BR1R adds six-edge
    observability before any retimed offset may be granted a pass.
    """

    causal = causal_window_analysis(result, "b1", 3, 2, False)
    return {
        "scenario_key": result["spec"]["scenario_key"],
        "baseline_vdd_v": result["spec"]["baseline_vdd_v"],
        "Vdroop_v": result["spec"]["Vdroop_v"],
        "M_det": result["parameters"]["M_det"],
        "F_det": result["parameters"]["F_det"],
        "scenario_path": result["scenario_path"],
        "deck_sha256": result["deck_sha256"],
        "timing": result["timing"],
        "causal_analysis": causal,
        "gate": "SHARED_SENSOR_CADENCE_GO" if causal["gate"] == "CAUSAL_WINDOW_PASS" else "SHARED_SENSOR_CADENCE_FAIL",
    }


def run_br1() -> Dict[str, Any]:
    """Run the BR1 hard gate, authorising exactly two HSPICE diagnostics.

    ``new_hspice_scenarios`` in the published contract is the count of unique
    BR1 identities proven to have run electrically in this study.  It remains
    two during an idempotent replay.  ``reused_hspice_scenarios`` is instead
    the number of those identities read without launching HSPICE this time.
    The fields therefore answer different audit questions and are intentionally
    not mutually exclusive on a repeat invocation.
    """

    baseline = read_json(baseline_path())
    if baseline.get("gate") != "D0_BR_BASELINE_READY":
        raise RuntimeError("BR1 requires D0_BR_BASELINE_READY")
    inventory = retained_inventory()
    fall_offset = br1_fall_offset_ps()
    context = t0.frozen_context()
    results: List[Dict[str, Any]] = []
    reused = 0
    historical_new = 0
    for spec in BR1_SPECS:
        result, was_reused = run_br1_scenario(context, spec, fall_offset)
        # Keep the physical-run ledger separate from the public diagnostic
        # result.  The latter intentionally exposes only electrical evidence,
        # while this counter proves every authorised deck has a retained run.
        historical_new += int(result.get("hspice_executed") is True)
        results.append(classify_br1(result))
        reused += int(was_reused)
    gates = {item["gate"] for item in results}
    if gates == {"SHARED_SENSOR_CADENCE_GO"}:
        gate = "SHARED_SENSOR_CADENCE_FIXED_FALL_GO"
    elif "SHARED_SENSOR_CADENCE_FAIL" in gates:
        gate = "SHARED_SENSOR_CADENCE_FIXED_FALL_FAIL"
    else:
        gate = "SHARED_SENSOR_TIMING_FRAGILE"
    if historical_new != len(BR1_SPECS):
        raise RuntimeError("BR1 did not retain execution evidence for every authorised scenario")
    record = {
        "schema_version": 1,
        "study": STUDY,
        "stage": "D0-BR1",
        "gate": gate,
        "probe_period_ps": RUNTIME_PERIOD_PS,
        "sclk_fall_offset_ps": fall_offset,
        "retained_timing_inventory": inventory,
        "diagnostics": results,
        # BR1 is now an intentionally limited fixed-duty observation.  Even a
        # fixed-duty failure proceeds only to BR1R's frozen-topology retiming,
        # never directly to a capture bank or a copied sensor lane.
        "next_action": "continue_to_BR1R_fall_retiming",
        "simulation_accounting": accounting(new=historical_new, reused=reused, reparsed=0),
    }
    write_json(br1_root() / "retained_timing_inventory.json", inventory)
    write_json(br1_root() / "diagnostic_manifest.json", {
        "schema_version": 1, "study": STUDY, "stage": "D0-BR1", "authorized_scenarios": [item["scenario_key"] for item in BR1_SPECS],
        "scenario_limit": 2, "sclk_fall_offset_ps": fall_offset, "forbidden_flow_runs": ["T0_campaign", "M0_campaign", "capture_bank"],
    })
    write_json(br1_root() / "shared_sensor_cadence_contract.json", record)
    return record


def round_up_to_grid(value_ps: float, grid_ps: float = EDGE_GUARD_PS) -> float:
    """Round one evidence-derived time upward without creating an extra sweep point."""

    return round(math.ceil(value_ps / grid_ps) * grid_ps, 6)


def br1r_offset_rationale(fixed_diagnostics: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Derive and verify the three BR1R offsets from retained fixed-fall data.

    The earliest retiming is not guessed: it follows the slowest measured
    probe0 XOR rise by 100 ps.  The latest follows the slowest measured
    probe0 raw-CK rise by the same guard.  Their single midpoint detects a
    non-monotonic collision corridor without becoming an unconstrained
    duty-cycle sweep.  A changed retained record must fail closed rather than
    silently move the search range.
    """

    xor_delays: List[float] = []
    raw_delays: List[float] = []
    for diagnostic in fixed_diagnostics:
        causal = diagnostic["causal_analysis"]
        rise0 = causal["measured_source_edges_s"]["rise0_s"]
        probe0 = causal["event_windows"][0]["nodes"]
        xor_rises, raw_rises = probe0["xor"]["rise_times_s"], probe0["raw_ck"]["rise_times_s"]
        if rise0 is None or len(xor_rises) != 1 or len(raw_rises) != 1:
            raise RuntimeError("BR1R cannot derive offsets from incomplete retained probe0 evidence")
        xor_delays.append((xor_rises[0] - float(rise0)) * 1.0e12)
        raw_delays.append((raw_rises[0] - float(rise0)) * 1.0e12)
    earliest = round_up_to_grid(max(xor_delays) + BR1R_SOURCE_SETTLE_PS)
    latest = round_up_to_grid(max(raw_delays) + BR1R_SOURCE_SETTLE_PS)
    midpoint = round((earliest + latest) / 2.0, 6)
    offsets = (earliest, midpoint, latest)
    if offsets != BR1R_FALL_OFFSETS_PS:
        raise RuntimeError("retained BR1 propagation no longer supports the approved BR1R offsets: {}".format(offsets))
    return {
        "source_settle_ps": BR1R_SOURCE_SETTLE_PS,
        "slowest_probe0_xor_rise_delay_ps": round(max(xor_delays), 6),
        "slowest_probe0_raw_ck_rise_delay_ps": round(max(raw_delays), 6),
        "retained_fixed_fall_offset_ps": br1_fall_offset_ps(),
        "approved_common_fall_offsets_ps": list(offsets),
    }


def render_br1r_deck(context: Mapping[str, Any], parameters: Mapping[str, Any],
                     fall_offset_ps: float) -> Tuple[str, Dict[str, float]]:
    """Render one BR1R deck with causal observability and frozen physical ports.

    The only electrical stimulus change relative to the T0 real-cell deck is
    the time of the first S_CLK falling transition.  The two S_CLK rises remain
    exactly one 2075 ps period apart.  All sensor ports, M/F local controls,
    monitored rail connections, fine load, XOR connection and the reset-held
    DFF input load are inherited unchanged from T0.  Six rise/fall measures
    per sensitive node expose any unaccounted fourth-or-later event.
    """

    base = t0.render_deck(context, parameters).rstrip()
    if not base.endswith(".end"):
        raise RuntimeError("T0 renderer did not produce a deck terminator")
    timing = t0.shifted_probe_timing(parameters)
    launch0 = timing["launch_time_s"]
    launch1 = launch0 + RUNTIME_PERIOD_PS * 1.0e-12
    fall0 = launch0 + float(fall_offset_ps) * 1.0e-12
    droop_end = launch0 + (float(parameters["phase_ps"]) + float(parameters["t_fall_ps"]) +
                           float(parameters["t_hold_ps"]) + float(parameters["t_rise_ps"])) * 1.0e-12
    stop = max(launch1 + 1.5e-9, droop_end + 1.0e-9)
    source = repeated_sclk_pwl(launch0, launch1, fall0, stop)
    deck = replace_source_line(base, "V_CTRL_SCLK ", "V_CTRL_SCLK ctrl_sclk vss_a {}".format(source))
    deck = replace_source_line(
        deck, "V_CTRL_DFF_RESET ",
        "V_CTRL_DFF_RESET ctrl_dff_reset vss_a PWL(0 1 {} 1)".format(t0.physical.spice(stop)))
    body = deck.rstrip()[:-len(".end")].rstrip()
    prelaunch = launch1 - 1.0e-12
    measures: List[str] = [
        "* D0-BR1R: fall-retiming-only repeated sensor diagnostic; DFF reset remains asserted.",
        "* Frozen ports/topology/M-F/period; no legalizer, bank, FSM, sensor copy, ideal delay or capacitor.",
        ".measure tran b1r_sclk_rise0 WHEN v(s_clk,vss_a)='V(vdd_a,vss_a)/2' RISE=1",
        ".measure tran b1r_sclk_fall0 WHEN v(s_clk,vss_a)='V(vdd_a,vss_a)/2' FALL=1",
        ".measure tran b1r_sclk_rise1 WHEN v(s_clk,vss_a)='V(vdd_a,vss_a)/2' RISE=2",
    ]
    for node, short in (("xor_29", "xor"), ("medium_out", "medium"), ("dff_ck", "raw_ck")):
        for edge_index in range(1, BR1R_MEASURED_EDGE_LIMIT + 1):
            measures.append(
                ".measure tran b1r_{}_rise{} WHEN v({},vss_a)='V(vdd_a,vss_a)/2' RISE={} TD={}".format(
                    short, edge_index, node, edge_index, t0.physical.spice(launch0)))
            measures.append(
                ".measure tran b1r_{}_fall{} WHEN v({},vss_a)='V(vdd_a,vss_a)/2' FALL={} TD={}".format(
                    short, edge_index, node, edge_index, t0.physical.spice(launch0)))
        measures.extend([
            ".measure tran b1r_{}_prelaunch FIND v({},vss_a) AT={}".format(short, node, t0.physical.spice(prelaunch)),
            ".measure tran b1r_{}_vdd_prelaunch FIND v(vdd_a,vss_a) AT={}".format(short, t0.physical.spice(prelaunch)),
        ])
    return body + "\n" + "\n".join(measures) + "\n.end\n", {
        "launch0_s": launch0,
        "fall0_s": fall0,
        "launch1_s": launch1,
        "prelaunch_s": prelaunch,
        "stop_s": stop,
        "fall_offset_ps": float(fall_offset_ps),
        "rise_fall_measurement_limit": float(BR1R_MEASURED_EDGE_LIMIT),
    }


def br1r_scenario_identity(spec: Mapping[str, Any], parameters: Mapping[str, Any], fall_offset_ps: float) -> str:
    """Name a BR1R directory from every electrical and observability input."""

    payload = {
        "stage": "D0-BR1R",
        "spec": dict(spec),
        "parameters": dict(parameters),
        "fall_offset_ps": float(fall_offset_ps),
        "causal_measurement_edge_limit": BR1R_MEASURED_EDGE_LIMIT,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()[:20]
    return "{}__fall{}ps__{}".format(spec["scenario_key"], int(fall_offset_ps), digest)


def run_br1r_scenario(context: Mapping[str, Any], spec: Mapping[str, Any],
                      fall_offset_ps: float) -> Tuple[Dict[str, Any], bool]:
    """Reuse or execute one of BR1R's six authorised causal-window decks.

    The reuse branch validates the complete deck identity, HSPICE listing and
    recorded physical-execution flag before parsing scalar measurements.  The
    execution branch writes every generated product under BR1R's task-owned
    run directory, so no deck, listing, measure, state or command transcript
    escapes into the workspace root.
    """

    parameters = t0.parameters_for(float(spec["baseline_vdd_v"]), str(spec["margin_level"]),
                                   float(spec["Vdroop_v"]), float(spec["hold_ps"]), float(spec["phase_ps"]))
    deck, timing = render_br1r_deck(context, parameters, fall_offset_ps)
    deck_sha = hashlib.sha256(deck.encode("utf-8")).hexdigest()
    scenario = RUN_ROOT / "br1r_fall_retiming" / br1r_scenario_identity(spec, parameters, fall_offset_ps)
    manifest_path, measurement_path = scenario / "scenario_manifest.json", scenario / "br1r.mt0.csv"
    if manifest_path.is_file() and measurement_path.is_file() and (scenario / "br1r.lis").is_file():
        manifest = read_json(manifest_path)
        expected = {
            "deck_sha256": deck_sha,
            "parameters": parameters,
            "spec": dict(spec),
            "fall_offset_ps": float(fall_offset_ps),
            "completion_status": "PASS",
            "hspice_executed": True,
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            raise RuntimeError("retained BR1R run does not match its frozen identity: {}".format(scenario))
        t0.physical.run_dc_sweep.validate_listing(scenario / "br1r.lis")
        return {"spec": dict(spec), "parameters": parameters, "timing": timing, "scenario_path": str(scenario),
                "deck_sha256": deck_sha, "fall_offset_ps": float(fall_offset_ps), "hspice_executed": True,
                "measurements": parse_measurements(measurement_path)}, True

    hspice, environment, version = require_hspice()
    scenario.mkdir(parents=True, exist_ok=True)
    (scenario / "br1r.sp").write_text(deck, encoding="utf-8")
    empty_subckt = FTC_ROOT / "spice" / "empty_subckt.sp_cal"
    if not empty_subckt.is_file():
        raise RuntimeError("required immutable empty_subckt include is missing")
    shutil.copyfile(str(empty_subckt), str(scenario / empty_subckt.name))
    manifest = {
        "schema_version": 1,
        "study": STUDY,
        "stage": "D0-BR1R",
        "diagnostic_only": True,
        "spec": dict(spec),
        "parameters": parameters,
        "timing": timing,
        "fall_offset_ps": float(fall_offset_ps),
        "deck_sha256": deck_sha,
        "container_hspice": str(hspice),
        "hspice_version": version,
        "environment": environment,
        "companion_include": {"path": "delay_chain/ftc/spice/empty_subckt.sp_cal", "sha256": sha256_file(empty_subckt)},
        "completion_status": "RUNNING",
        "hspice_executed": False,
        "scope": "only S_CLK fall0 is retimed; 2075 ps period, M/F and sensor topology are frozen",
    }
    write_json(manifest_path, manifest)
    process = subprocess.run([str(hspice), "br1r.sp", "-o", "br1r"], cwd=str(scenario), check=False, timeout=900,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    (scenario / "hspice_command.log").write_text(
        "returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(process.returncode, process.stdout, process.stderr),
        encoding="utf-8")
    if process.returncode != 0:
        manifest["completion_status"] = "FAIL"
        manifest["failure"] = "HSPICE returned {}".format(process.returncode)
        write_json(manifest_path, manifest)
        raise RuntimeError("BR1R HSPICE failed: {}".format(scenario))
    t0.physical.run_dc_sweep.validate_listing(scenario / "br1r.lis")
    if not measurement_path.is_file():
        raise RuntimeError("BR1R measurement file is missing: {}".format(scenario))
    manifest["completion_status"] = "PASS"
    manifest["hspice_executed"] = True
    manifest["measurement_file"] = measurement_path.name
    write_json(manifest_path, manifest)
    return {"spec": dict(spec), "parameters": parameters, "timing": timing, "scenario_path": str(scenario),
            "deck_sha256": deck_sha, "fall_offset_ps": float(fall_offset_ps), "hspice_executed": True,
            "measurements": parse_measurements(measurement_path)}, False


def classify_br1r(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Attach target provenance to BR1R's causal-window, not ordinal, result."""

    causal = causal_window_analysis(result, "b1r", BR1R_MEASURED_EDGE_LIMIT,
                                    BR1R_MEASURED_EDGE_LIMIT, True)
    return {
        "scenario_key": result["spec"]["scenario_key"],
        "baseline_vdd_v": result["spec"]["baseline_vdd_v"],
        "Vdroop_v": result["spec"]["Vdroop_v"],
        "M_det": result["parameters"]["M_det"],
        "F_det": result["parameters"]["F_det"],
        "fall_offset_ps": result["fall_offset_ps"],
        "scenario_path": result["scenario_path"],
        "deck_sha256": result["deck_sha256"],
        "timing": result["timing"],
        "causal_analysis": causal,
        "gate": causal["gate"],
    }


def run_br1r() -> Dict[str, Any]:
    """Run the finite common-fall search after re-parsing the fixed endpoint.

    The old BR1 listings are parsed as endpoint evidence only; their original
    HSPICE decks are never rerun.  Exactly three new fall offsets are then run
    at each of the two existing formal targets.  A common offset must pass at
    both voltages, which prevents per-corner duty tuning from being mistaken
    for a reusable shared-sensor cadence contract.
    """

    baseline = read_json(baseline_path())
    if baseline.get("gate") != "D0_BR_BASELINE_READY":
        raise RuntimeError("BR1R requires D0_BR_BASELINE_READY")
    br1 = read_json(br1_root() / "shared_sensor_cadence_contract.json")
    allowed_br1_gates = {"SHARED_SENSOR_CADENCE_FIXED_FALL_FAIL", "SHARED_SENSOR_TIMING_FRAGILE",
                         "SHARED_SENSOR_CADENCE_FAIL"}
    if br1.get("gate") not in allowed_br1_gates:
        raise RuntimeError("BR1R is only authorised after a fixed-fall non-GO result")
    fixed_offset = br1_fall_offset_ps()
    context = t0.frozen_context()
    fixed_diagnostics: List[Dict[str, Any]] = []
    for spec in BR1_SPECS:
        result, was_reused = run_br1_scenario(context, spec, fixed_offset)
        if not was_reused:
            raise RuntimeError("BR1R must reuse, not rerun, the retained BR1 endpoint")
        fixed_diagnostics.append(classify_br1(result))
    rationale = br1r_offset_rationale(fixed_diagnostics)
    diagnostics: List[Dict[str, Any]] = []
    reused_new = 0
    historical_new = 0
    for offset in BR1R_FALL_OFFSETS_PS:
        for spec in BR1_SPECS:
            result, was_reused = run_br1r_scenario(context, spec, offset)
            historical_new += int(result.get("hspice_executed") is True)
            reused_new += int(was_reused)
            diagnostics.append(classify_br1r(result))
    if historical_new != len(BR1R_FALL_OFFSETS_PS) * len(BR1_SPECS):
        raise RuntimeError("BR1R lacks physical execution evidence for an authorised retiming scenario")
    candidate_summary = []
    common_offsets: List[float] = []
    for offset in BR1R_FALL_OFFSETS_PS:
        rows = [row for row in diagnostics if row["fall_offset_ps"] == offset]
        candidate_gate = "CAUSAL_WINDOW_PASS" if all(row["gate"] == "CAUSAL_WINDOW_PASS" for row in rows) else "CAUSAL_WINDOW_FAIL"
        if candidate_gate == "CAUSAL_WINDOW_PASS":
            common_offsets.append(offset)
        candidate_summary.append({"fall_offset_ps": offset, "target_diagnostics": rows, "gate": candidate_gate})
    decision = "SHARED_SENSOR_CADENCE_RETIMING_GO" if common_offsets else "SHARED_SENSOR_CADENCE_PHYSICALLY_BLOCKED"
    record = {
        "schema_version": 1,
        "study": STUDY,
        "stage": "D0-BR1R",
        "decision": decision,
        "runtime_probe_period_ps": RUNTIME_PERIOD_PS,
        "fixed_fall_causal_reanalysis": fixed_diagnostics,
        "retiming_rationale": rationale,
        "candidate_summary": candidate_summary,
        "selected_common_fall_offset_ps": common_offsets[0] if common_offsets else None,
        "next_action": "continue_to_BR2_capture_event_research" if common_offsets else "publish_multi_sensor_lane_escalation_only",
        # ``new`` is the cumulative count of distinct BR1R decks with a
        # retained successful run; ``reused`` records only BR1R decks read on
        # this invocation.  The two old BR1 decks appear in ``reparsed``.
        "simulation_accounting": accounting(new=historical_new, reused=reused_new,
                                              reparsed=len(fixed_diagnostics)),
    }
    write_json(br1r_root() / "retained_fixed_fall_causal_reanalysis.json", {
        "schema_version": 1, "study": STUDY, "stage": "D0-BR1R", "source": "D0-BR1 retained listings",
        "fall_offset_ps": fixed_offset, "diagnostics": fixed_diagnostics,
        "simulation_accounting": accounting(reparsed=len(fixed_diagnostics)),
    })
    write_json(br1r_root() / "diagnostic_manifest.json", {
        "schema_version": 1,
        "study": STUDY,
        "stage": "D0-BR1R",
        "formal_targets": [item["scenario_key"] for item in BR1_SPECS],
        "approved_common_fall_offsets_ps": list(BR1R_FALL_OFFSETS_PS),
        "new_hspice_scenario_limit": len(BR1R_FALL_OFFSETS_PS) * len(BR1_SPECS),
        "reused_fixed_fall_scenarios": len(fixed_diagnostics),
        "frozen": ["probe_period_2075ps", "M_F_codes", "sensor_topology", "DFF_input_load"],
        "forbidden_flow_runs": ["M0_campaign", "T0_campaign", "H0", "M1", "RF", "XA", "capture_bank"],
    })
    write_json(br1r_root() / "retiming_search_contract.json", record)
    return record


def write_br1r_gate() -> Dict[str, Any]:
    """Publish the only two legal BR1R outcomes without creating a new circuit.

    A retiming GO grants *research entry* to BR2 only; it does not claim a
    legal DFF pulse, a capture bank, a controller or a completed D0-BR design.
    A physical block is terminal because the finite common-fall search has
    exhausted the sole stimulus freedom authorised by BR1R.
    """

    br1r = read_json(br1r_root() / "retiming_search_contract.json")
    is_go = br1r.get("decision") == "SHARED_SENSOR_CADENCE_RETIMING_GO"
    shared_cadence = {
        "verified_at_2075ps": is_go,
        "common_fall_offset_ps": br1r.get("selected_common_fall_offset_ps"),
        "p_sensor_verified_ps": RUNTIME_PERIOD_PS if is_go else None,
        "n_sensor_min": 1 if is_go else None,
        "n_sensor_min_status": "ONE_SHARED_SENSOR_AT_2075PS_CONFIRMED_BY_BR1R" if is_go else
                               "NOT_COMPUTABLE: BR1R did not search a longer safe P_sensor",
    }
    preserved = {
        "d0a_decision": "ARCHITECTURE_ESCALATION_REQUIRED",
        "t0_decision": "CONDITIONAL_GO",
        "t0_full_phase_requirement": "100_percent_CLEAN_Q1",
        "h0_m1_modified": False,
        "capture_event_legalizer_created": False,
        "capture_bank_created": False,
        "runtime_rtl_created": False,
    }
    contract = {
        "schema_version": 1,
        "study": STUDY,
        "decision": br1r["decision"],
        "current_stage": "D0-BR1R",
        "terminal_stage": None if is_go else "D0-BR1R",
        "runtime_probe_requirement_ps": RUNTIME_PERIOD_PS,
        "shared_sensor_cadence": shared_cadence,
        "preserved_contracts": preserved,
        "br1_fixed_fall_evidence": str(br1_root() / "shared_sensor_cadence_contract.json"),
        "br1r_evidence": str(br1r_root() / "retiming_search_contract.json"),
        "simulation_accounting": br1r["simulation_accounting"],
    }
    if is_go:
        gate = {
            "schema_version": 1,
            "study": STUDY,
            "decision": br1r["decision"],
            "current_stage": "D0-BR1R",
            "next_permitted_stage": "D0-BR2_capture_event_legalizer_research",
            "forbidden_before_BR2_gate": ["capture_bank", "runtime_fsm", "sensor_lane_copy"],
            "simulation_accounting": br1r["simulation_accounting"],
        }
    else:
        gate = {
            "schema_version": 1,
            "study": STUDY,
            "decision": br1r["decision"],
            "terminal_stage": "D0-BR1R",
            "reason": "no approved common fall timing separated probe0, falling-wave and probe1 events at 2075 ps",
            "required_next_plan": "multi_sensor_lane_interleave_architecture_plan",
            "forbidden_after_failure": ["capture_event_legalizer", "capture_bank", "runtime_fsm", "sensor_lane_copy_in_this_plan"],
            "simulation_accounting": br1r["simulation_accounting"],
        }
    write_json(ANALYSIS / "contract" / "D0_INTERLEAVED_CAPTURE_CONTRACT.json", contract)
    write_json(ANALYSIS / "reports" / "D0_BR_GATE_STATUS.json", gate)
    candidate_rows = []
    for candidate in br1r["candidate_summary"]:
        target_states = ", ".join("{}={}".format(row["scenario_key"], row["gate"])
                                  for row in candidate["target_diagnostics"])
        candidate_rows.append("- fall0 offset {} ps：{}；共同 Gate={}。".format(
            candidate["fall_offset_ps"], target_states, candidate["gate"]))
    report = """# FTC D0-BR 合法捕获与交错架构闭合

## BR1R Gate

**{decision}**。原 BR1 的 `1687.575705 ps` fixed-fall result被重新解释为单一 S_CLK 占空比证据；BR1R 在保持 2075 ps probe period、正式 M/F、真实 sensor/DFF input load 和所有既有 topology 不变的前提下，只重定时第一笔 S_CLK fall。

## 范围与方法

- 已重解析两个 retained BR1 listing，按测得的 `rise0 -> fall0 -> rise1` 三个因果窗口归属 XOR、medium、raw CK crossing；未按全局 `rise1/rise2/rise3` 序号配对 probe。
- 新运行只允许共同的 750、1000、1250 ps fall offset 与两个正式 L2/3002 ps target；没有 M0/T0/H0/M1/RF/XA campaign，也没有任何 legalizer、capture bank、runtime FSM 或 sensor copy。
- 单一 target 只有在三窗口各 node 均为一个完整 rise/fall、falling-wave 在 rise1 前清空、probe1 D_ref 完整且与 probe0 相差不超过 25 ps 时才通过。

## 有限 retiming 结果

{candidate_rows}

## 后续边界

{next_boundary}
""".format(
        decision=br1r["decision"],
        candidate_rows="\n".join(candidate_rows),
        next_boundary=("BR1R 仅授权进入 BR2 的合法 capture event/pulse legalizer 研究；尚未实现任何该结构。" if is_go else
                       "两个正式 target 在规定的共同 retiming 集合内均未闭合；后续必须另立 multi-sensor-lane 计划。`P_sensor_verified_ps` 与 `N_sensor_min` 保持 `null`。"))
    REPORT.write_text(report, encoding="utf-8")
    return gate


def run_all() -> Dict[str, Any]:
    """Execute BR0, fixed-fall BR1, bounded BR1R, then publish its Gate."""

    run_br0()
    run_br1()
    run_br1r()
    return write_br1r_gate()


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Expose explicit bounded phases; no user-supplied sweep argument exists."""

    parser = argparse.ArgumentParser(description="FTC D0-BR interleaved-capture architecture closure")
    parser.add_argument("--phase", required=True, choices=("br0", "br1", "br1r", "finalize", "all"))
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Dispatch one bounded study phase without launching adjacent campaigns."""

    phase = parse_args(argv).phase
    if phase == "br0":
        run_br0()
    elif phase == "br1":
        run_br1()
    elif phase == "br1r":
        run_br1r()
    elif phase == "finalize":
        write_br1r_gate()
    else:
        run_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
