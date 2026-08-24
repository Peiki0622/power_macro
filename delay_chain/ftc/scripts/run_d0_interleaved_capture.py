#!/usr/bin/env python3
"""Execute the gate-driven FTC D0-BR interleaved-capture study.

The D0-A study stopped at ``ARCHITECTURE_ESCALATION_REQUIRED`` because the
frozen capture DFF receives a physically real, but formally illegal, narrow
clock pulse.  D0-BR is deliberately not a runtime-controller implementation:
it first asks whether one *shared* analogue sensing path can accept the T0
cadence at all.  A failing answer terminates the capture-bank route before a
pulse legalizer, extra DFF, RTL, or broad HSPICE campaign can be introduced.

Only BR0 and BR1 are executable until BR1 supplies ``SHARED_SENSOR_CADENCE_GO``.
That is intentional fail-closed sequencing rather than an incomplete digital
implementation: the governing plan explicitly prohibits all capture-bank work
when the shared RVT/LVT/XOR/medium/fine path itself cannot re-arm in 2075 ps.
All generated electrical products are confined to the task-owned ``runs``
directory; compact JSON/CSV/report evidence is confined to the D0-BR analysis
directory.
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


def classify_br1(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Classify one repeated-sensor result without granting capture-bank credit.

    A GO is deliberately strict: each sensitive node must have exactly two
    rising events in the diagnostic interval, be low immediately before the
    second launch, and deliver a positive second-launch raw D-ref.  A third
    rising event is the falling-edge-induced event that D0-A warned about and
    makes a capture-bank-only route invalid even though the DFF is reset here.
    """

    values, timing = result["measurements"], result["timing"]
    launch1 = float(timing["launch1_s"])
    node_summary: Dict[str, Dict[str, Any]] = {}
    structural_failures: List[str] = []
    fragile_reasons: List[str] = []
    for short in ("xor", "medium", "raw_ck"):
        rises = [values.get("b1_{}_rise{}".format(short, index)) for index in (1, 2, 3)]
        falls = [values.get("b1_{}_fall{}".format(short, index)) for index in (1, 2)]
        pre_value, pre_vdd = values.get("b1_{}_prelaunch".format(short)), values.get("b1_{}_vdd_prelaunch".format(short))
        pre_ratio = None if pre_value is None or pre_vdd is None or pre_vdd <= 0.0 else pre_value / pre_vdd
        rise_count = sum(edge is not None for edge in rises)
        first_fall = falls[0]
        rearm_margin = ps_difference(launch1, first_fall)
        node_summary[short] = {
            "rise_times_s": rises,
            "fall_times_s": falls,
            "rise_count_observed": rise_count,
            "prelaunch_ratio": None if pre_ratio is None else round(pre_ratio, 9),
            "rearm_margin_ps": rearm_margin,
        }
        if rise_count != 2:
            structural_failures.append("{}_rise_count_is_{}_not_2".format(short, rise_count))
        if rises[1] is None or rises[1] <= launch1:
            structural_failures.append("{}_second_rise_not_after_second_launch".format(short))
        if first_fall is None or first_fall >= launch1:
            structural_failures.append("{}_first_event_not_complete_before_second_launch".format(short))
        if pre_ratio is None or pre_ratio > LOW_RATIO_LIMIT:
            structural_failures.append("{}_not_low_before_second_launch".format(short))
        if rearm_margin is not None and 0.0 < rearm_margin < EDGE_GUARD_PS:
            fragile_reasons.append("{}_rearm_margin_below_{}ps".format(short, EDGE_GUARD_PS))

    dref0 = ps_difference(values.get("b1_raw_ck_rise1"), values.get("b1_xor_rise1"))
    dref1 = ps_difference(values.get("b1_raw_ck_rise2"), values.get("b1_xor_rise2"))
    if dref0 is None or dref0 <= 0.0:
        structural_failures.append("first_probe_D_ref_is_not_positive")
    if dref1 is None or dref1 <= 0.0:
        structural_failures.append("second_probe_D_ref_is_not_positive")
    if structural_failures:
        gate = "SHARED_SENSOR_CADENCE_FAIL"
    elif fragile_reasons:
        gate = "SHARED_SENSOR_TIMING_FRAGILE"
    else:
        gate = "SHARED_SENSOR_CADENCE_GO"
    return {
        "scenario_key": result["spec"]["scenario_key"],
        "baseline_vdd_v": result["spec"]["baseline_vdd_v"],
        "Vdroop_v": result["spec"]["Vdroop_v"],
        "M_det": result["parameters"]["M_det"],
        "F_det": result["parameters"]["F_det"],
        "scenario_path": result["scenario_path"],
        "deck_sha256": result["deck_sha256"],
        "timing": timing,
        "nodes": node_summary,
        "d_ref_ps": {"probe0": dref0, "probe1": dref1},
        "structural_failures": structural_failures,
        "fragile_reasons": fragile_reasons,
        "gate": gate,
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
        gate = "SHARED_SENSOR_CADENCE_GO"
    elif "SHARED_SENSOR_CADENCE_FAIL" in gates:
        gate = "SHARED_SENSOR_CADENCE_FAIL"
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
        "next_action": "continue_to_BR2" if gate == "SHARED_SENSOR_CADENCE_GO" else "publish_multi_sensor_lane_escalation_only",
        "simulation_accounting": accounting(new=historical_new, reused=reused, reparsed=0),
    }
    write_json(br1_root() / "retained_timing_inventory.json", inventory)
    write_json(br1_root() / "diagnostic_manifest.json", {
        "schema_version": 1, "study": STUDY, "stage": "D0-BR1", "authorized_scenarios": [item["scenario_key"] for item in BR1_SPECS],
        "scenario_limit": 2, "sclk_fall_offset_ps": fall_offset, "forbidden_flow_runs": ["T0_campaign", "M0_campaign", "capture_bank"],
    })
    write_json(br1_root() / "shared_sensor_cadence_contract.json", record)
    return record


def write_terminal_gate() -> Dict[str, Any]:
    """Publish BR1's terminal escalation only when the planned hard gate fails."""

    br1 = read_json(br1_root() / "shared_sensor_cadence_contract.json")
    if br1.get("gate") == "SHARED_SENSOR_CADENCE_GO":
        raise RuntimeError("BR1 GO requires BR2 onward; terminal escalation is forbidden")
    contract = {
        "schema_version": 1,
        "study": STUDY,
        "decision": br1["gate"],
        "terminal_stage": "D0-BR1",
        "runtime_probe_requirement_ps": RUNTIME_PERIOD_PS,
        "shared_sensor_cadence": {
            "verified_at_2075ps": False,
            "p_sensor_verified_ps": None,
            "n_sensor_min": None,
            "n_sensor_min_status": "NOT_COMPUTABLE: BR1 disproves 2075 ps but does not characterize a longer safe P_sensor",
        },
        "preserved_contracts": {
            "d0a_decision": "ARCHITECTURE_ESCALATION_REQUIRED",
            "t0_decision": "CONDITIONAL_GO",
            "t0_full_phase_requirement": "100_percent_CLEAN_Q1",
            "h0_m1_modified": False,
            "capture_event_legalizer_created": False,
            "capture_bank_created": False,
            "runtime_rtl_created": False,
        },
        "br1_evidence": str(br1_root() / "shared_sensor_cadence_contract.json"),
        "simulation_accounting": br1["simulation_accounting"],
    }
    gate = {
        "schema_version": 1,
        "study": STUDY,
        "decision": br1["gate"],
        "terminal_stage": "D0-BR1",
        "reason": "shared sensing path did not close 2075 ps re-arm before any capture-bank topology was authorised",
        "required_next_plan": "multi_sensor_lane_interleave_architecture_plan",
        "forbidden_after_failure": ["capture_event_legalizer", "capture_bank", "runtime_fsm", "sensor_lane_copy_in_this_plan"],
        "simulation_accounting": br1["simulation_accounting"],
    }
    write_json(ANALYSIS / "contract" / "D0_INTERLEAVED_CAPTURE_CONTRACT.json", contract)
    write_json(ANALYSIS / "reports" / "D0_BR_GATE_STATUS.json", gate)
    per_target = []
    for diagnostic in br1["diagnostics"]:
        node_counts = ", ".join("{}={}".format(name, node["rise_count_observed"])
                                for name, node in diagnostic["nodes"].items())
        per_target.append("- `{}`: {}; D_ref0/D_ref1={} / {} ps。".format(
            diagnostic["scenario_key"], node_counts, diagnostic["d_ref_ps"]["probe0"], diagnostic["d_ref_ps"]["probe1"]))
    report = """# FTC D0-BR 合法捕获与交错架构闭合

## 最终 Gate

**{decision}**。BR1 已在两个正式 T0 L2 / 3002 ps target 点直接检查共享 RVT/LVT/XOR/medium/fine sensing path 的 2075 ps re-arm；该 Gate 在任何 pulse legalizer、capture bank 或 D0 runtime RTL 之前执行。

## 结论边界

- D0-A 的窄 raw `dff_ck` 根因和 T0 的 2075 ps / 100% CLEAN_Q1 要求均未修改。
- 本轮只执行 BR1 允许的两项 task-owned sensor-only HSPICE diagnostics；未重跑 M0、T0、H0、M1、RF 或 XA。
- capture-bank-only 不能隐藏 sensing path 自身的 re-arm 限制，因此本计划在 BR1 正确终止；后续必须另立 multi-sensor-lane interleave 计划。

## BR1 物理观测

{target_rows}

`P_sensor_verified_ps` 仍为 `null`：本轮只证明 2075 ps 不可用，没有执行未经授权的更长周期搜索。因此也不能把 `N_sensor_min` 写成一个伪精确数字。
""".format(decision=br1["gate"], target_rows="\n".join(per_target))
    REPORT.write_text(report, encoding="utf-8")
    return gate


def run_all() -> Dict[str, Any]:
    """Execute the only legal path until BR1's architecture decision is known."""

    run_br0()
    br1 = run_br1()
    if br1["gate"] != "SHARED_SENSOR_CADENCE_GO":
        return write_terminal_gate()
    raise RuntimeError("BR1 passed; BR2 implementation is required before this runner may continue")


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Expose explicit gate entrypoints; no free-form sweep interface exists."""

    parser = argparse.ArgumentParser(description="FTC D0-BR interleaved-capture architecture closure")
    parser.add_argument("--phase", required=True, choices=("br0", "br1", "finalize", "all"))
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Dispatch one bounded study phase without running adjacent work implicitly."""

    phase = parse_args(argv).phase
    if phase == "br0":
        run_br0()
    elif phase == "br1":
        run_br1()
    elif phase == "finalize":
        write_terminal_gate()
    else:
        run_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
