#!/usr/bin/env python3
"""Close the D0-A fast-path architecture question without altering T0 evidence.

The completed T0 study proved a *coverage* requirement of 2075 ps, while
D0-0 proved that the historical one-shot schedule cannot be repeated that
quickly.  This runner deliberately does not reinterpret either conclusion.
It first binds their immutable inputs, then separates scalar transistor-level
evidence from old protocol delays, and finally chooses the smallest permitted
architecture-review outcome.  Its only HSPICE work is the two explicitly
authorized single-probe observability diagnostics; all generated simulator
products live under the ignored task-owned run directory.
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


# The D0-A runner reuses the reviewed M0/T0 deck renderer but never changes it.
# Keeping the script directory as the sole import root makes that dependency
# explicit and prevents accidentally selecting unrelated historic sensor RTL.
FTC_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = FTC_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import run_t0_transient_droop_characterization as t0  # noqa: E402


STUDY = "ftc_d0_runtime_fastpath_architecture_closure_v1"
ANALYSIS = FTC_ROOT / "analysis" / "d0_runtime_fastpath"
RUN_ROOT = FTC_ROOT / "runs" / "d0_runtime_fastpath"
REPORT = FTC_ROOT / "reports" / "FTC_D0_RUNTIME_FASTPATH_ARCHITECTURE_CLOSURE.md"
# A5 must hand off an escalation plan, rather than silently treating the
# guarded two-lane arithmetic as an implementation authorization.  D0-A only
# links this document; it never executes any of its future phases.
NEXT_ARCHITECTURE_PLAN = FTC_ROOT.parent.parent / "plans" / "ftc_d0b_interleaved_capture_architecture_plan.md"

# D0-A0 binds every input named by the approved plan, plus the plan itself.
# Entries are repository-relative so the published baseline remains portable.
INPUTS = {
    "d0_0_timing_budget": "analysis/d0_runtime_timing/contract/D0_0_RUNTIME_TIMING_BUDGET.json",
    "d0_0_report": "reports/FTC_D0_RUNTIME_TIMING_FEASIBILITY.md",
    "t0_downstream_contract": "analysis/t0_transient_droop/contract/T0_DOWNSTREAM_D0_TIMING_CONTRACT.json",
    "t0_cadence_summary": "analysis/t0_transient_droop/cadence/cadence_summary.json",
    "m0_single_probe_contract": "analysis/m0_detection_margin_characterization/probe_contract/single_probe_contract.json",
    "m1_handoff": "controller/m1_detection_margin/contract/M1_DOWNSTREAM_T0_D0_HANDOFF.json",
    "pd1_sclk_crossing": "controller/pd1_power_domain_interface/crossings/sclk_crossing_contract.json",
    "pd1_reset_crossing": "controller/pd1_power_domain_interface/crossings/reset_crossing_contract.json",
    "pd1_qfinal_return": "controller/pd1_power_domain_interface/crossings/qfinal_return_contract.json",
    "refrequency_final_report": "controller/refrequency/reports/REFREQUENCY_FINAL_REPORT.md",
    "refrequency_sequential_timing": "controller/refrequency/library_audit/sequential_cell_timing_capability.json",
    "d0a_plan": "../../plans/ftc_d0a_runtime_fastpath_architecture_closure_plan.md",
}

# The two inputs exactly preserve T0-5A's formal electrical parameters.  The
# selected phases are the last CLEAN_Q1 points before the right Q0 boundary,
# so they are conservative target observations without initiating a new phase
# scan.  ``hold_ps=3000`` plus the frozen 1 ps fall/rise is the formal 3002 ps
# total pulse, not a changed threat definition.
DIAGNOSTIC_SPECS = (
    {
        "scenario_key": "d0a1_0p95_l2_long_right_clean",
        "baseline_vdd_v": 0.95,
        "margin_level": "L2",
        "M_det": 5,
        "F_det": 6,
        "Vdroop_v": 0.86,
        "hold_ps": 3000.0,
        "phase_ps": 75.0,
    },
    {
        "scenario_key": "d0a1_1p10_l2_long_right_clean",
        "baseline_vdd_v": 1.10,
        "margin_level": "L2",
        "M_det": 3,
        "F_det": 8,
        "Vdroop_v": 0.96,
        "hold_ps": 3000.0,
        "phase_ps": 25.0,
    },
)

# RF's approved standard-cell timing checks are a model constraint, not a new
# device characterization.  The historical 2.5 ns RF cadence preserved 250 ps
# on each clock half-cycle.  Retaining that guard as a comparison threshold is
# conservative: D0-A may report a hard-minimum possibility, but never calls a
# 75 ps total residual "robust".
RUNTIME_PERIOD_PS = 2075.0
CAPTURE_CK_HIGH_MIN_PS = 1000.0
CAPTURE_CK_LOW_MIN_PS = 1000.0
RF_HALF_CYCLE_GUARD_PS = 250.0


def sha256_file(path: Path) -> str:
    """Hash an immutable input or rendered deck without copying large PDK data."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    """Load one object-valued contract and fail closed on malformed evidence."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("{} must contain one JSON object".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Publish a deterministic compact evidence object at one explicit path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def relative_input_path(raw: str) -> Path:
    """Resolve a D0-A0 input while preserving the unusual plan path safely."""

    if raw.startswith("../../"):
        return FTC_ROOT.parent.parent / raw[6:]
    return FTC_ROOT / raw


def require_dl() -> Dict[str, str]:
    """Require the reviewed local environment before any D0-A HSPICE action."""

    if os.environ.get("CONDA_DEFAULT_ENV") != "DL":
        raise RuntimeError("D0-A HSPICE requires CONDA_DEFAULT_ENV=DL")
    return {
        "conda_env": os.environ["CONDA_DEFAULT_ENV"],
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
    }


def container_hspice() -> Tuple[Path, str]:
    """Return only the container-local HSPICE mandated for this study.

    This rejects a host path even when one happens to be available.  The
    version text is retained in the task-owned manifest so the two permitted
    diagnostics are independently auditable without checking a shell history.
    """

    executable = Path("/home/zhupl25/.local/bin/hspice")
    if not executable.is_file() or not os.access(str(executable), os.X_OK):
        raise RuntimeError("container-local HSPICE wrapper is unavailable: {}".format(executable))
    result = subprocess.run([str(executable), "-v"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True, check=False, timeout=60)
    if result.returncode != 0:
        raise RuntimeError("container-local HSPICE version query failed: {}".format(result.stderr.strip()))
    return executable, (result.stdout + result.stderr).strip()


def baseline_path() -> Path:
    """Return D0-A0's immutable-input record location."""

    return ANALYSIS / "baseline" / "frozen_input_sha256.json"


def a1_paths() -> Dict[str, Path]:
    """Keep all A1 review evidence inside its dedicated analysis directory."""

    root = ANALYSIS / "a1_physical_budget"
    return {
        "inventory": root / "physical_timing_inventory.csv",
        "budget": root / "physical_timing_budget.json",
        "manifest": root / "evidence_reuse_manifest.json",
    }


def a2_paths() -> Dict[str, Path]:
    """Return the two machine-readable outputs of the A2 arithmetic gate."""

    root = ANALYSIS / "a2_single_path_candidate"
    return {
        "contract": root / "candidate_timing_contract.json",
        "summary": root / "feasibility_summary.json",
    }


def a5_paths() -> Dict[str, Path]:
    """Return the architecture-review outputs used only after A2 routes here."""

    root = ANALYSIS / "a5_interleave_review"
    return {
        "lanes": root / "lane_count_analysis.json",
        "comparison": root / "architecture_comparison.md",
    }


def verify_baseline_state() -> Dict[str, Any]:
    """Check the specific D0-0/T0/M0/M1 states required before D0-A work."""

    d0 = read_json(FTC_ROOT / INPUTS["d0_0_timing_budget"])
    t0_contract = read_json(FTC_ROOT / INPUTS["t0_downstream_contract"])
    t0_cadence = read_json(FTC_ROOT / INPUTS["t0_cadence_summary"])
    m0 = read_json(FTC_ROOT / INPUTS["m0_single_probe_contract"])
    m1 = read_json(FTC_ROOT / INPUTS["m1_handoff"])
    if d0.get("decision") != "ARCHITECTURE_REVIEW":
        raise RuntimeError("D0-A must preserve D0-0 ARCHITECTURE_REVIEW")
    if float(t0_contract["runtime_probe_period"]["maximum_period_ps"]) != RUNTIME_PERIOD_PS:
        raise RuntimeError("T0 runtime period changed from 2075 ps")
    if t0_contract.get("decision") != "CONDITIONAL_GO" or t0_cadence.get("decision") != "CONDITIONAL_GO":
        raise RuntimeError("T0 downstream cadence authority is not CONDITIONAL_GO")
    if m0.get("q_decision", {}).get("two_samples_required") is not True:
        raise RuntimeError("M0 two-Q observation rule is missing")
    if "sensor controls remain reset=1 and S_CLK=0 at the M1 boundary" not in m1.get("entry_condition_for_t0_d0", []):
        raise RuntimeError("M1 safe detection boundary changed")
    return {
        "d0_0_decision": d0["decision"],
        "t0_decision": t0_contract["decision"],
        "t0_runtime_period_ps": RUNTIME_PERIOD_PS,
        "m0_two_samples_required": True,
        "m1_static_configuration_required": True,
    }


def run_a0() -> Dict[str, Any]:
    """Bind all D0-A inputs and publish the no-RTL/no-rerun scope statement."""

    hashes: Dict[str, Dict[str, str]] = {}
    for name, raw in INPUTS.items():
        path = relative_input_path(raw)
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError("D0-A0 required input is missing: {}".format(path))
        hashes[name] = {"path": raw, "sha256": sha256_file(path)}
    record = {
        "schema_version": 1,
        "study": STUDY,
        "stage": "D0-A0",
        "gate": "D0_A0_READY",
        "authority_state": verify_baseline_state(),
        "inputs": hashes,
        "scope": {
            "d0_0_architecture_review_preserved": True,
            "t0_pmax_coverage_ps_preserved": RUNTIME_PERIOD_PS,
            "h0_m1_t0_reruns_forbidden": True,
            "runtime_rtl_implemented": False,
            "sensor_core_modification_authorized": False,
            "detection_only_fastpath_study_authorized": True,
        },
        "simulation_accounting": {
            "new_hspice_scenarios": 0,
            "reused_hspice_scenarios": 0,
            "reparsed_hspice_scenarios": 0,
            "electrically_equivalent_reuse_scenarios": 0,
            "forbidden_flow_runs": 0,
        },
    }
    write_json(baseline_path(), record)
    return record


def measurement_header(path: Path) -> List[str]:
    """Read the one HSPICE MEASFORM=3 CSV header without trusting its values."""

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("$") and "," in stripped:
            return [item.strip() for item in stripped.split(",")]
    raise RuntimeError("measurement CSV has no header: {}".format(path))


def parse_measurement_csv(path: Path) -> Dict[str, Optional[float]]:
    """Parse the first scalar row and keep HSPICE ``failed`` values explicit.

    A failed optional measure is never coerced to zero: zero could falsely
    describe a valid timing crossing.  The caller decides whether that missing
    quantity is an acceptable optional diagnostic or a gate-blocking unknown.
    """

    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
             if line.strip() and not line.lstrip().startswith("$")]
    header_index = next((index for index, line in enumerate(lines) if "," in line), None)
    if header_index is None or header_index + 1 >= len(lines):
        raise RuntimeError("measurement CSV is incomplete: {}".format(path))
    names = [item.strip() for item in lines[header_index].split(",")]
    values = [item.strip() for item in lines[header_index + 1].split(",")]
    if len(names) != len(values):
        raise RuntimeError("measurement CSV column mismatch: {}".format(path))
    parsed: Dict[str, Optional[float]] = {}
    for name, raw in zip(names, values):
        try:
            parsed[name] = float(raw)
        except ValueError:
            parsed[name] = None
    return parsed


def retained_observability() -> Dict[str, Any]:
    """Audit all retained scalar campaigns before allowing any new simulation."""

    m0_root = FTC_ROOT / "runs" / "m0_detection_margin_characterization"
    t0_root = FTC_ROOT / "runs" / "t0_transient_droop"
    m0_listings = sorted(m0_root.rglob("*.lis"))
    t0_listings = sorted(t0_root.rglob("*.lis"))
    m0_measurements = sorted(m0_root.rglob("*.mt0.csv"))
    t0_measurements = sorted(t0_root.rglob("*.mt0.csv"))
    if len(m0_listings) != 91 or len(t0_listings) != 515:
        raise RuntimeError("retained M0/T0 listing inventory drifted")
    if len(m0_measurements) != 91 or len(t0_measurements) != 514:
        raise RuntimeError("retained M0/T0 measurement inventory drifted")
    headers = set()
    for path in m0_measurements + t0_measurements:
        headers.update(measurement_header(path))
    return {
        "m0_listing_count": len(m0_listings),
        "m0_measurement_count": len(m0_measurements),
        "t0_listing_count": len(t0_listings),
        "t0_measurement_count": len(t0_measurements),
        "m0_tr0_count": len(list(m0_root.rglob("*.tr0"))),
        "t0_tr0_count": len(list(t0_root.rglob("*.tr0"))),
        "measurement_headers": sorted(headers),
    }


def t0_parameters(spec: Mapping[str, Any]) -> Dict[str, Any]:
    """Recreate exactly one approved T0-5A electrical identity for A1."""

    parameters = t0.parameters_for(
        float(spec["baseline_vdd_v"]), str(spec["margin_level"]),
        float(spec["Vdroop_v"]), float(spec["hold_ps"]), float(spec["phase_ps"]),
    )
    if (parameters["M_det"], parameters["F_det"]) != (int(spec["M_det"]), int(spec["F_det"])):
        raise RuntimeError("D0-A1 formal M/F code drifted for {}".format(spec["scenario_key"]))
    return parameters


def diagnostic_identity(spec: Mapping[str, Any], parameters: Mapping[str, Any]) -> str:
    """Derive a stable task-local directory name from immutable parameters."""

    payload = json.dumps({"spec": dict(spec), "parameters": dict(parameters)}, sort_keys=True,
                         separators=(",", ":"), ensure_ascii=True)
    return "{}__{}".format(spec["scenario_key"], hashlib.sha256(payload.encode("ascii")).hexdigest()[:20])


def render_a1_deck(context: Mapping[str, Any], parameters: Mapping[str, Any]) -> str:
    """Add scalar observability to the unmodified corrected T0 single-probe deck.

    The base deck is T0's local-VDD-normalized real-cell topology, including
    unchanged M/F controls, droop waveform, DFF positional ports and original
    measurements.  Only named `.measure` commands are appended.  No waveform
    database is enabled, which keeps diagnostics small and avoids introducing
    a second interpretation of the transistor-level circuit.
    """

    base = t0.render_deck(context, parameters).rstrip()
    if not base.endswith(".end"):
        raise RuntimeError("T0 renderer did not produce a valid deck terminator")
    body = base[:-len(".end")].rstrip()
    timing = t0.shifted_probe_timing(parameters)
    launch = t0.physical.spice(timing["launch_time_s"])
    reset_assert = t0.physical.spice(timing["reset_assert_start_s"])
    measures = [
        "* D0-A1 observability only: no topology, stimulus, or control change.",
        ".measure tran a1_sclk_rise WHEN v(s_clk,vss_a)='V(vdd_a,vss_a)/2' RISE=1",
        ".measure tran a1_sclk_fall WHEN v(s_clk,vss_a)='V(vdd_a,vss_a)/2' FALL=1",
        ".measure tran a1_reset_release WHEN v(dff_reset,vss_a)='V(vdd_a,vss_a)/2' FALL=1",
        ".measure tran a1_reset_assert WHEN v(dff_reset,vss_a)='V(vdd_a,vss_a)/2' RISE=1",
        ".measure tran a1_xor_rise WHEN v(xor_29,vss_a)='V(vdd_a,vss_a)/2' RISE=1 TD={}".format(launch),
        ".measure tran a1_xor_fall WHEN v(xor_29,vss_a)='V(vdd_a,vss_a)/2' FALL=1 TD={}".format(launch),
        ".measure tran a1_medium_fall WHEN v(medium_out,vss_a)='V(vdd_a,vss_a)/2' FALL=1 TD={}".format(launch),
        ".measure tran a1_ck_rise WHEN v(dff_ck,vss_a)='V(vdd_a,vss_a)/2' RISE=1 TD={}".format(launch),
        ".measure tran a1_ck_fall WHEN v(dff_ck,vss_a)='V(vdd_a,vss_a)/2' FALL=1 TD={}".format(launch),
        ".measure tran a1_ck_rise_2 WHEN v(dff_ck,vss_a)='V(vdd_a,vss_a)/2' RISE=2 TD={}".format(launch),
        ".measure tran a1_ck_high_width PARAM='a1_ck_fall-a1_ck_rise'",
        ".measure tran a1_q_high_10 WHEN v(q_final,vss_a)='V(vdd_a,vss_a)/10' RISE=1 TD={}".format(launch),
        ".measure tran a1_q_high_90 WHEN v(q_final,vss_a)='9*V(vdd_a,vss_a)/10' RISE=1 TD={}".format(launch),
        ".measure tran a1_q_reset_low_10 WHEN v(q_final,vss_a)='V(vdd_a,vss_a)/10' FALL=1 TD={}".format(reset_assert),
        ".measure tran a1_vdd_at_q_high_90 FIND v(vdd_a,vss_a) AT='a1_q_high_90'",
        ".measure tran a1_vdd_at_q_reset_low_10 FIND v(vdd_a,vss_a) AT='a1_q_reset_low_10'",
        ".end",
    ]
    return body + "\n" + "\n".join(measures) + "\n"


def diagnostic_scenario(context: Mapping[str, Any], spec: Mapping[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Reuse or run one of the two authorized D0-A1 diagnostics exactly once."""

    parameters = t0_parameters(spec)
    identity = diagnostic_identity(spec, parameters)
    scenario = RUN_ROOT / "a1_physical_budget" / identity
    deck = render_a1_deck(context, parameters)
    deck_hash = hashlib.sha256(deck.encode("utf-8")).hexdigest()
    manifest_path = scenario / "scenario_manifest.json"
    measurement_path = scenario / "d0a1.mt0.csv"
    if manifest_path.is_file() and measurement_path.is_file() and (scenario / "d0a1.lis").is_file():
        manifest = read_json(manifest_path)
        if (manifest.get("parameters") != parameters or manifest.get("spec") != dict(spec) or
                manifest.get("deck_sha256") != deck_hash or manifest.get("completion_status") != "PASS"):
            raise RuntimeError("retained D0-A1 diagnostic does not match its frozen input: {}".format(scenario))
        t0.physical.run_dc_sweep.validate_listing(scenario / "d0a1.lis")
        return {"spec": dict(spec), "parameters": parameters, "scenario_path": str(scenario),
                "deck_sha256": deck_hash, "measurements": parse_measurement_csv(measurement_path)}, True

    environment = require_dl()
    hspice, version = container_hspice()
    scenario.mkdir(parents=True, exist_ok=True)
    (scenario / "d0a1.sp").write_text(deck, encoding="utf-8")
    # The immutable real-cell CDL refers to this empty parasitic placeholder by
    # its bare filename.  T0's approved runner therefore places the unchanged
    # file beside every task-local deck before HSPICE starts.  Copying it here
    # supplies that existing include dependency only; it does not alter a PDK,
    # a cell topology, a source waveform, or any electrical parameter.
    empty_subckt = FTC_ROOT / "spice" / "empty_subckt.sp_cal"
    if not empty_subckt.is_file():
        raise RuntimeError("D0-A1 required immutable CDL include is missing: {}".format(empty_subckt))
    shutil.copyfile(str(empty_subckt), str(scenario / "empty_subckt.sp_cal"))
    manifest = {
        "schema_version": 1,
        "study": STUDY,
        "stage": "D0-A1",
        "diagnostic_only": True,
        "spec": dict(spec),
        "parameters": parameters,
        "deck_sha256": deck_hash,
        "companion_include": {
            "path": "delay_chain/ftc/spice/empty_subckt.sp_cal",
            "sha256": sha256_file(empty_subckt),
            "purpose": "immutable_CDL_relative_include_runtime_copy",
        },
        "container_hspice": str(hspice),
        "hspice_version": version,
        "environment": environment,
        "completion_status": "RUNNING",
        "reason": "retained post=0 scalar evidence lacks CK width and earliest Q/reset measurements",
    }
    write_json(manifest_path, manifest)
    result = subprocess.run([str(hspice), "d0a1.sp", "-o", "d0a1"], cwd=str(scenario),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                            check=False, timeout=900)
    (scenario / "hspice_command.log").write_text(
        "returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr),
        encoding="utf-8")
    if result.returncode != 0:
        manifest["completion_status"] = "FAIL"
        manifest["failure"] = "HSPICE returned {}".format(result.returncode)
        write_json(manifest_path, manifest)
        raise RuntimeError("D0-A1 HSPICE failed: {}".format(scenario))
    t0.physical.run_dc_sweep.validate_listing(scenario / "d0a1.lis")
    if not measurement_path.is_file():
        raise RuntimeError("D0-A1 measurement CSV is missing: {}".format(scenario))
    manifest["completion_status"] = "PASS"
    manifest["measurement_file"] = measurement_path.name
    write_json(manifest_path, manifest)
    return {"spec": dict(spec), "parameters": parameters, "scenario_path": str(scenario),
            "deck_sha256": deck_hash, "measurements": parse_measurement_csv(measurement_path)}, False


def ps_difference(later: Optional[float], earlier: Optional[float]) -> Optional[float]:
    """Return a stable picosecond interval only when both crossings exist."""

    if later is None or earlier is None:
        return None
    return round((later - earlier) * 1.0e12, 6)


def diagnostic_summary(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert scalar crossings into physical intervals without inferring a schedule.

    The second CK rising crossing is deliberately retained even though it is
    after reset assertion in the frozen one-shot stimulus.  It establishes the
    actual return-to-low interval and exposes a post-reset CK edge; it is not
    relabelled as a legal second runtime capture edge.
    """

    values = result["measurements"]
    required = ("a1_sclk_rise", "a1_sclk_fall", "a1_reset_release", "a1_reset_assert",
                "a1_ck_rise", "a1_ck_fall", "a1_ck_rise_2", "a1_q_high_10",
                "a1_q_high_90", "a1_q_reset_low_10",
                "a1_xor_fall", "a1_medium_fall")
    missing = [name for name in required if values.get(name) is None]
    # A real high pulse is the first rising-to-falling interval.  The following
    # falling-to-second-rising interval is recorded as a physical low duration,
    # but it cannot qualify as an inter-probe low margin when the second edge
    # occurs after reset assertion or lacks a second independent S_CLK launch.
    ck_high_width = ps_difference(values.get("a1_ck_fall"), values.get("a1_ck_rise"))
    ck_low_width = ps_difference(values.get("a1_ck_rise_2"), values.get("a1_ck_fall"))
    reported_high_width = values.get("a1_ck_high_width")
    reported_high_width_ps = None if reported_high_width is None else round(reported_high_width * 1.0e12, 6)
    high_width_consistent = (ck_high_width is not None and reported_high_width_ps is not None and
                             abs(ck_high_width - reported_high_width_ps) <= 0.001)
    second_after_reset = (values.get("a1_ck_rise_2") is not None and
                          values.get("a1_reset_assert") is not None and
                          values["a1_ck_rise_2"] > values["a1_reset_assert"])
    return {
        "scenario_key": result["spec"]["scenario_key"],
        "baseline_vdd_v": result["spec"]["baseline_vdd_v"],
        "Vdroop_v": result["spec"]["Vdroop_v"],
        "M_det": result["spec"]["M_det"],
        "F_det": result["spec"]["F_det"],
        "phase_ps": result["spec"]["phase_ps"],
        "scenario_path": result["scenario_path"],
        "sclk_high_width_ps": ps_difference(values.get("a1_sclk_fall"), values.get("a1_sclk_rise")),
        "dff_ck_high_width_ps": ck_high_width,
        "dff_ck_low_width_to_second_edge_ps": ck_low_width,
        "dff_ck_high_width_reported_ps": reported_high_width_ps,
        "dff_ck_high_width_measure_consistent": high_width_consistent,
        "sclk_rise_to_ck_rise_ps": ps_difference(values.get("a1_ck_rise"), values.get("a1_sclk_rise")),
        "sclk_rise_to_ck_fall_ps": ps_difference(values.get("a1_ck_fall"), values.get("a1_sclk_rise")),
        "ck_rise_to_q_high_10_ps": ps_difference(values.get("a1_q_high_10"), values.get("a1_ck_rise")),
        "ck_rise_to_q_high_90_ps": ps_difference(values.get("a1_q_high_90"), values.get("a1_ck_rise")),
        "q_high_10_to_90_ps": ps_difference(values.get("a1_q_high_90"), values.get("a1_q_high_10")),
        "reset_assert_to_q_low_10_ps": ps_difference(values.get("a1_q_reset_low_10"), values.get("a1_reset_assert")),
        "reset_release_to_ck_rise_ps": ps_difference(values.get("a1_ck_rise"), values.get("a1_reset_release")),
        "sclk_fall_to_xor_fall_ps": ps_difference(values.get("a1_xor_fall"), values.get("a1_sclk_fall")),
        "sclk_fall_to_medium_fall_ps": ps_difference(values.get("a1_medium_fall"), values.get("a1_sclk_fall")),
        "sclk_fall_to_ck_fall_ps": ps_difference(values.get("a1_ck_fall"), values.get("a1_sclk_fall")),
        "extra_ck_rise_present": values.get("a1_ck_rise_2") is not None,
        "second_ck_rise_after_reset_assert": second_after_reset,
        "capture_edges_between_release_and_assert": int(
            values.get("a1_ck_rise") is not None and values.get("a1_reset_release") is not None and
            values.get("a1_reset_assert") is not None and
            values["a1_reset_release"] < values["a1_ck_rise"] < values["a1_reset_assert"]
        ) + int(
            values.get("a1_ck_rise_2") is not None and values.get("a1_reset_release") is not None and
            values.get("a1_reset_assert") is not None and
            values["a1_reset_release"] < values["a1_ck_rise_2"] < values["a1_reset_assert"]
        ),
        "missing_required_measurements": missing,
    }


def inventory_rows(diagnostics_complete: bool) -> List[Dict[str, str]]:
    """Classify the final A1 evidence, distinguishing old from new evidence.

    ``diagnostics_complete`` changes only the evidence classification written
    to the compact review CSV.  It never changes a deck, HSPICE scenario, or
    the formal M/F and droop identity that generated the evidence.
    """

    return [
        {"metric": "S_CLK_rise_to_dff_ck_first_rise", "classification": "PHYSICAL_MEASURED",
         "evidence": "retained M0/T0 t_ck_rise scalar measurements", "limitation": "value belongs to old one-probe stimulus"},
        {"metric": "active_capture_CK_edge_count", "classification": "PHYSICAL_MEASURED",
         "evidence": "retained exact-path CK audits and T0 t_ck_rise_2", "limitation": "only old active window is qualified"},
        {"metric": "Q_at_old_Q_SAMPLE_1_and_Q_SAMPLE_2", "classification": "PHYSICAL_MEASURED",
         "evidence": "retained M0/T0 Q scalar measurements", "limitation": "does not prove earliest Q response or stable dwell"},
        {"metric": "recovery_node_level_at_old_recovery_endpoint", "classification": "PHYSICAL_MEASURED",
         "evidence": "retained recovery end/tail measures", "limitation": "does not prove earliest repeatable next probe"},
        {"metric": "capture_CK_high_width_and_next_low_width",
         "classification": "PHYSICAL_MEASURED" if diagnostics_complete else "UNKNOWN",
         "evidence": "two authorized D0-A1 scalar diagnostics" if diagnostics_complete else "no retained fall-crossing or waveform",
         "limitation": "single-probe observability only; second CK edge is post-reset and not a legal next capture" if diagnostics_complete else "old decks use post=0"},
        {"metric": "capture_CK_high_low_hard_minimum", "classification": "MODEL_TIMING_CHECK",
         "evidence": "RF sequential_cell_timing_capability", "limitation": "1.0 ns high and 1.0 ns low model checks"},
        {"metric": "CK_to_Q_90_percent_and_Q_reset_clear",
         "classification": "PHYSICAL_MEASURED" if diagnostics_complete else "UNKNOWN",
         "evidence": "two authorized D0-A1 Q threshold/reset-clear measurements" if diagnostics_complete else "only scheduled Q values retained",
         "limitation": "does not establish two independent runtime observation instants" if diagnostics_complete else "no threshold-crossing measures or waveform"},
        {"metric": "Q_observation_1_to_observation_2_spacing", "classification": "PROTOCOL_SCHEDULED",
         "evidence": "old 200 ps observation spacing", "limitation": "not a physical lower bound and no runtime observer exists"},
        {"metric": "reset_release_to_rearm", "classification": "MODEL_TIMING_CHECK",
         "evidence": "RF recovery/removal timing", "limitation": "requires later continuous-probe validation if a candidate exists"},
        {"metric": "S_CLK_fall_to_path_low", "classification": "PHYSICAL_MEASURED" if diagnostics_complete else "UNKNOWN",
         "evidence": "two authorized D0-A1 XOR/medium/CK falling crossings" if diagnostics_complete else "only old fixed recovery tail samples",
         "limitation": "falling crossings precede S_CLK fall in the frozen one-shot; no multi-probe re-arm claim" if diagnostics_complete else "earliest falling crossings were not retained"},
    ]


def write_inventory(rows: Sequence[Mapping[str, str]]) -> None:
    """Write the small review table without creating per-scenario scratch files."""

    path = a1_paths()["inventory"]
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ("metric", "classification", "evidence", "limitation")
    with path.open("w", newline="", encoding="utf-8") as stream:
        # Keep committed evidence LF-terminated on every host.  ``csv`` uses
        # CRLF by default even on Linux, which makes Git whitespace validation
        # report an otherwise valid generated row as having a trailing CR.
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run_a1() -> Dict[str, Any]:
    """Complete A1's retained-data audit and the bounded two-point diagnostic."""

    if not baseline_path().is_file():
        raise RuntimeError("D0-A1 requires D0-A0 baseline")
    retained = retained_observability()
    # No retained waveform exists and the header union lacks every required
    # threshold/fall measurement.  This is the plan's explicit authorization
    # trigger for exactly two task-owned diagnostics, not a source-hash rerun.
    required_new_headers = {"a1_ck_fall", "a1_q_high_90", "a1_q_reset_low_10"}
    if required_new_headers.intersection(set(retained["measurement_headers"])):
        raise RuntimeError("A1 retained evidence unexpectedly contains diagnostic-only measurements")
    context = t0.frozen_context()
    results: List[Dict[str, Any]] = []
    new_count = 0
    reused_count = 0
    for spec in DIAGNOSTIC_SPECS:
        result, reused = diagnostic_scenario(context, spec)
        results.append(diagnostic_summary(result))
        if reused:
            reused_count += 1
        else:
            new_count += 1
    if any(item["missing_required_measurements"] for item in results):
        gate = "INSUFFICIENT_EVIDENCE"
    else:
        gate = "SINGLE_LANE_PHYSICAL_BUDGET_READY"
    rows = inventory_rows(not any(item["missing_required_measurements"] for item in results))
    write_inventory(rows)
    total_run_count = len(list((RUN_ROOT / "a1_physical_budget").glob("*/scenario_manifest.json")))
    budget = {
        "schema_version": 1,
        "study": STUDY,
        "stage": "D0-A1",
        "gate": gate,
        "retained_observability": retained,
        "physical_diagnostics": results,
        "physical_constraints": {
            "q_decision": "two_real_dff_Q_stable_observations_required",
            "old_q_sample_offsets_are_protocol_scheduled": True,
            "capture_ck_high_min_ps": CAPTURE_CK_HIGH_MIN_PS,
            "capture_ck_low_min_ps": CAPTURE_CK_LOW_MIN_PS,
            "reset_recovery_ps": CAPTURE_CK_HIGH_MIN_PS,
            "reset_removal_ps": 500.0,
        },
        "simulation_accounting": {
            "new_hspice_scenarios": total_run_count,
            "latest_invocation_new_hspice_scenarios": new_count,
            "reused_hspice_scenarios": reused_count,
            "reparsed_hspice_scenarios": retained["m0_measurement_count"] + retained["t0_measurement_count"],
            "electrically_equivalent_reuse_scenarios": 0,
            "forbidden_flow_runs": 0,
        },
    }
    manifest = {
        "schema_version": 1,
        "study": STUDY,
        "stage": "D0-A1",
        "reason_for_new_hspice": "retained M0/T0 decks have post=0 and no CK fall/Q threshold/reset-clear observability",
        "retained_listing_counts": {key: retained[key] for key in (
            "m0_listing_count", "m0_measurement_count", "t0_listing_count", "t0_measurement_count",
            "m0_tr0_count", "t0_tr0_count")},
        "authorized_scenarios": [item["scenario_key"] for item in DIAGNOSTIC_SPECS],
        "forbidden_work": ["M0/M1/H0/T0_campaign_rerun", "phase_sweep", "sensor_topology_change"],
    }
    write_json(a1_paths()["budget"], budget)
    write_json(a1_paths()["manifest"], manifest)
    if gate != "SINGLE_LANE_PHYSICAL_BUDGET_READY":
        raise RuntimeError("D0-A1 has insufficient physical evidence; refusing A2")
    return budget


def run_a2() -> Dict[str, Any]:
    """Use A1's worst real-cell measurements to classify the single lane.

    The result intentionally cannot call a one-lane fast path robust when the
    DFF model alone leaves only 75 ps for both CK phases.  This is a direct
    timing-check result, independent of the old 5.70 ns one-shot schedule.
    """

    budget_path = a1_paths()["budget"]
    if not budget_path.is_file():
        raise RuntimeError("D0-A2 requires completed D0-A1")
    a1 = read_json(budget_path)
    if a1.get("gate") != "SINGLE_LANE_PHYSICAL_BUDGET_READY":
        raise RuntimeError("D0-A2 cannot proceed after A1 gate {}".format(a1.get("gate")))
    diagnostics = a1["physical_diagnostics"]
    high_widths = [float(item["dff_ck_high_width_ps"]) for item in diagnostics
                   if item.get("dff_ck_high_width_ps") is not None]
    low_widths = [float(item["dff_ck_low_width_to_second_edge_ps"]) for item in diagnostics
                  if item.get("dff_ck_low_width_to_second_edge_ps") is not None]
    q90_delays = [float(item["ck_rise_to_q_high_90_ps"]) for item in diagnostics
                  if item.get("ck_rise_to_q_high_90_ps") is not None]
    reset_clear_delays = [float(item["reset_assert_to_q_low_10_ps"]) for item in diagnostics
                          if item.get("reset_assert_to_q_low_10_ps") is not None]
    if len(high_widths) != len(DIAGNOSTIC_SPECS):
        raise RuntimeError("A1 did not produce both CK high widths")
    if len(low_widths) != len(DIAGNOSTIC_SPECS):
        raise RuntimeError("A1 did not produce both CK low intervals")
    minimum_measured_high = min(high_widths)
    minimum_measured_low = min(low_widths)
    hard_total = CAPTURE_CK_HIGH_MIN_PS + CAPTURE_CK_LOW_MIN_PS
    hard_residual = RUNTIME_PERIOD_PS - hard_total
    guarded_total = 2.0 * (CAPTURE_CK_HIGH_MIN_PS + RF_HALF_CYCLE_GUARD_PS)
    guarded_shortfall = guarded_total - RUNTIME_PERIOD_PS
    high_width_shortfalls = [round(CAPTURE_CK_HIGH_MIN_PS - width, 6) for width in high_widths]
    # The attempted sequence has a zeroed reference only for the inequality
    # proof.  It is not a newly generated S_CLK waveform and does not replace
    # any frozen M0/T0 absolute stimulus coordinate.
    attempted_sequence = {
        "reference_event": "S_CLK_rise_at_0ps_for_budget_arithmetic_only",
        "required_first_capture_ck_high_end_no_earlier_than_ps": CAPTURE_CK_HIGH_MIN_PS,
        "measured_first_capture_ck_high_end_range_ps": [min(high_widths), max(high_widths)],
        "required_capture_ck_low_before_next_capture_ps": CAPTURE_CK_LOW_MIN_PS,
        "formal_ck_high_plus_low_ps": hard_total,
        "period_budget_ps": RUNTIME_PERIOD_PS,
        "residual_after_formal_ck_checks_ps": hard_residual,
        "first_failure": "measured_capture_CK_high_width_is_below_formal_minimum_before_Q_or_reset_can_close",
    }
    if minimum_measured_high < CAPTURE_CK_HIGH_MIN_PS:
        classification = "SENSOR_CLOCK_OR_RECOVERY_LIMITED"
        root_cause = "measured_dff_ck_high_width_violates_formal_cell_minimum"
    else:
        # Even a functional high pulse cannot provide the existing RF guard:
        # 2075 - (1000 + 1000) = 75 ps, far below 250 ps per half-cycle.
        classification = "TIMING_FRAGILE"
        root_cause = "capture_ck_high_low_model_margin_is_only_75ps_total"
    contract = {
        "schema_version": 1,
        "study": STUDY,
        "stage": "D0-A2",
        "classification": classification,
        "root_cause": root_cause,
        "runtime_requirement": {
            "probe_reference_event": "successive_S_CLK_rising_edges",
            "maximum_period_ps": RUNTIME_PERIOD_PS,
            "target_threat": "formal_T0_L2_3002ps_at_0p95_and_1p10",
            "full_phase_requirement": "100_percent_CLEAN_Q1",
        },
        "q_observation_contract": {
            "two_independent_real_dff_q_observations_required": True,
            "old_200ps_spacing_is_not_promoted_to_physical_minimum": True,
            "physical_q90_results": diagnostics,
            "runtime_observer_implemented": False,
        },
        "capture_ck_timing": {
            "formal_high_min_ps": CAPTURE_CK_HIGH_MIN_PS,
            "formal_low_min_ps": CAPTURE_CK_LOW_MIN_PS,
            "formal_hard_total_ps": hard_total,
            "hard_residual_at_2075ps": hard_residual,
            "rf_guard_per_half_cycle_ps": RF_HALF_CYCLE_GUARD_PS,
            "guarded_two_phase_requirement_ps": guarded_total,
            "guarded_shortfall_to_2075ps": guarded_shortfall,
            "minimum_measured_target_ck_high_width_ps": minimum_measured_high,
            "per_target_measured_ck_high_width_ps": high_widths,
            "per_target_ck_high_shortfall_to_formal_min_ps": high_width_shortfalls,
            "minimum_measured_ck_low_interval_to_post_reset_edge_ps": minimum_measured_low,
            "post_reset_second_ck_edge_present_in_each_target": all(
                bool(item.get("second_ck_rise_after_reset_assert")) for item in diagnostics),
            "all_measured_high_width_param_checks_consistent": all(
                bool(item.get("dff_ck_high_width_measure_consistent")) for item in diagnostics),
        },
        "three_bottleneck_assessment": {
            "capture_q_decision": {
                "max_measured_ck_rise_to_q90_ps": max(q90_delays) if q90_delays else None,
                "max_measured_reset_assert_to_q_low10_ps": max(reset_clear_delays) if reset_clear_delays else None,
                "two_independent_runtime_observation_minimum": "UNKNOWN_not_promoted_from_old_200ps_schedule",
                "assessment": "not_the_first_blocker; capture_CK_width_fails_before_Q_observation_timing_can_be_closed",
            },
            "reset_rearm": {
                "formal_recovery_ps": CAPTURE_CK_HIGH_MIN_PS,
                "formal_removal_ps": 500.0,
                "single_probe_reset_release_to_first_ck_ps": [
                    item.get("reset_release_to_ck_rise_ps") for item in diagnostics],
                "assessment": "continuous_probe_rearm_is_not_claimed; A3 is prohibited because the root CK width fails",
            },
            "sclk_ck_repeatability": {
                "single_probe_external_sclk_high_width_ps": [item.get("sclk_high_width_ps") for item in diagnostics],
                "one_capture_edge_before_reset_assert_in_each_target": all(
                    item.get("capture_edges_between_release_and_assert") == 1 for item in diagnostics),
                "extra_post_reset_ck_edge_in_each_target": all(
                    bool(item.get("second_ck_rise_after_reset_assert")) for item in diagnostics),
                "assessment": "root_limiter: a 3001ps frozen S_CLK high creates only 301.263ps/519.665ps DFF CK high pulses",
            },
        },
        "attempted_single_lane_microsequence_inequality_proof": attempted_sequence,
        "routing": {
            "a3_multi_probe_authorized": False,
            "a4_q_local_hold_authorized": False,
            "a5_interleave_review_required": True,
            "reason": "the root cause is capture CK width margin, which a Q-side hold cannot repair",
        },
        "simulation_accounting": {
            "new_hspice_scenarios": 0,
            "reused_hspice_scenarios": 0,
            "reparsed_hspice_scenarios": 0,
            "electrically_equivalent_reuse_scenarios": 0,
            "forbidden_flow_runs": 0,
        },
    }
    summary = {
        "schema_version": 1,
        "study": STUDY,
        "stage": "D0-A2",
        "decision": classification,
        "next_stage": "D0-A5",
        "reason": root_cause,
        "new_hspice_scenarios": 0,
    }
    write_json(a2_paths()["contract"], contract)
    write_json(a2_paths()["summary"], summary)
    return contract


def run_a5() -> Dict[str, Any]:
    """Publish the minimum interleave escalation without implementing it.

    The 2.50 ns guarded figure is a model-derived lower bound, explicitly not
    a verified lane cadence.  It is enough to prove that one lane cannot meet
    2075 ps with RF's existing guard and that any future architecture needs at
    least two capture opportunities.  A separate plan must perform physical
    multi-lane implementation and validation.
    """

    a2_path = a2_paths()["contract"]
    if not a2_path.is_file():
        raise RuntimeError("D0-A5 requires D0-A2")
    a2 = read_json(a2_path)
    if not a2["routing"].get("a5_interleave_review_required"):
        raise RuntimeError("A2 did not route this study to A5")
    model_guarded_lane_min = 2.0 * (CAPTURE_CK_HIGH_MIN_PS + RF_HALF_CYCLE_GUARD_PS)
    provisional_lane_count = int(math.ceil(model_guarded_lane_min / RUNTIME_PERIOD_PS))
    lanes = {
        "schema_version": 1,
        "study": STUDY,
        "stage": "D0-A5",
        "decision": "ARCHITECTURE_ESCALATION_REQUIRED",
        "single_lane_root_cause": a2["root_cause"],
        "P_lane_verified_ps": None,
        "P_lane_verified_status": "NOT_CLOSED_WITHOUT_MULTI_PROBE_PHYSICAL_EVIDENCE",
        "P_lane_model_guarded_min_ps": model_guarded_lane_min,
        "N_min_model_guarded": provisional_lane_count,
        "calculation": "ceil({:.1f} / {:.1f}) = {}".format(
            model_guarded_lane_min, RUNTIME_PERIOD_PS, provisional_lane_count),
        "important_limit": "N_min is a guarded-model architecture floor, not a claim that a lane is physically verified at 2500 ps.",
        "simulation_accounting": {
            "new_hspice_scenarios": 0,
            "reused_hspice_scenarios": 0,
            "reparsed_hspice_scenarios": 0,
            "electrically_equivalent_reuse_scenarios": 0,
            "forbidden_flow_runs": 0,
        },
    }
    comparison = """# D0-A5 交错架构评审

## 结论

**ARCHITECTURE_ESCALATION_REQUIRED**。D0-A2 的两条 target 诊断在外部 S_CLK 高电平为 3001 ps 时，量到的真实 capture `dff_ck` 高脉宽仅为 301.263 ps 与 519.665 ps，均低于冻结 cell 模型 1000 ps 下限；即使忽略此直接违例，2075 ps 周期扣除 1000 ps CK-high 与 1000 ps CK-low 也只剩 75 ps。Q 侧 result hold 不会改变这个 CK 根因，因此不进入 D0-A4。

`P_lane_verified` 仍未由连续多 probe 晶体管级证据闭合；不得把旧 5700 ps one-shot 参考伪装成物理下限。仅由正式 cell check 加既有 guard 得到的模型下界是 2500 ps，对应 `ceil(2500 / 2075) = 2` 个 capture opportunity。这是后续架构最小规模的保守起点，不是已实现两 lane 的结论。

| 候选 | XOR/D/CK 负载与 trip | 校准、M/F、VDD_MONITORED | ownership、相位及开销 | T0 继承与结论 |
|---|---|---|---|---|
| A. 单 capture DFF 后的 Q/result hold | 不增加 XOR/D/CK 负载，因此不改变 CK high/low 或原 trip。 | 不需独立校准；可共享 M/F 与同一 VDD_MONITORED。 | 仅 PD_SENSE DET ownership；aggregate phase 仍为原 `droop_start-S_CLK_rise`；面积/功耗最小。 | 单-probe T0 Q 判决可继承，但本结构不能修复实测 CK 高宽违例，排除。 |
| B. 两个交错 capture bank | 新 D/CK 支路可能加载原 capture 输入并改变 trip，必须先用最小物理负载预算；每 bank 还必须生成合规的 CK high/low。 | 倾向共享静态 M/F 和 VDD_MONITORED；bank 的 reset/re-arm 与是否共享校准须独立证明。 | DET 期间本地使用，CAL 完全旁路；aggregate phase 需要按被选 bank 的 S_CLK rise 定义；面积/动态功耗约增加 capture/reset 资源。 | 现有 T0 只能继承原 sensing threat，不继承新 bank 的 CK、负载或连续 reset 结论。作为最小后续研究对象，但不能预先声称可行。 |
| C. 独立 sensor lane interleave | 复制 sensing 路径与 capture，可能改变每 lane 负载与 trip，风险最大。 | 每 lane 原则上需独立校准；M/F 是否共享及共享 VDD_MONITORED 都须物理验证。 | H0/M1 ownership 影响最大；aggregate phase 必须分别引用各 lane launch；面积/功耗接近多份完整 sensor。 | 不继承原 T0 对新 lane 的所有结论，需新的最小 target/multi-probe 验证；仅在 B 无法闭合时考虑。 |

下一份独立计划必须先回答“在不破坏冻结原 sensor 证据的条件下，新增 capture bank 如何取得合规 CK high/low”这一根问题；不得把两个同样的窄 CK 脉冲简单交错后宣称解决。本阶段不实现任何 bank、wrapper、FSM、alarm、heartbeat、timeout 或跨电源域接收器，也不运行 A3/A4 HSPICE。
"""
    write_json(a5_paths()["lanes"], lanes)
    a5_paths()["comparison"].parent.mkdir(parents=True, exist_ok=True)
    a5_paths()["comparison"].write_text(comparison, encoding="utf-8")
    return lanes


def write_final_gate() -> Dict[str, Any]:
    """Publish D0-A's terminal escalation while preserving T0 and D0-0 history."""

    if not NEXT_ARCHITECTURE_PLAN.is_file():
        raise RuntimeError("D0-A escalation requires the separate D0-B plan: {}".format(NEXT_ARCHITECTURE_PLAN))
    baseline = read_json(baseline_path())
    a1 = read_json(a1_paths()["budget"])
    a2 = read_json(a2_paths()["contract"])
    a5 = read_json(a5_paths()["lanes"])
    gate = {
        "schema_version": 1,
        "study": STUDY,
        "decision": "ARCHITECTURE_ESCALATION_REQUIRED",
        "d0_0_decision_preserved": baseline["authority_state"]["d0_0_decision"],
        "t0_decision_preserved": baseline["authority_state"]["t0_decision"],
        "t0_runtime_period_ps": RUNTIME_PERIOD_PS,
        "a1_gate": a1["gate"],
        "a2_classification": a2["classification"],
        "a5_model_guarded_min_lane_count": a5["N_min_model_guarded"],
        "blocking_root_cause": a2["root_cause"],
        "next_authorized_work": "separate_two_capture_bank_or_interleave_architecture_plan",
        "next_architecture_plan": "plans/ftc_d0b_interleaved_capture_architecture_plan.md",
        "forbidden_in_this_stage": ["d0_runtime_fsm", "alarm", "heartbeat", "timeout", "sensor_core_change", "H0_M1_T0_rerun"],
        "simulation_accounting": {
            "new_hspice_scenarios": int(a1["simulation_accounting"]["new_hspice_scenarios"]),
            "reused_hspice_scenarios": int(a1["simulation_accounting"]["reused_hspice_scenarios"]),
            "reparsed_hspice_scenarios": int(a1["simulation_accounting"]["reparsed_hspice_scenarios"]),
            "electrically_equivalent_reuse_scenarios": 0,
            "forbidden_flow_runs": 0,
        },
    }
    gate_path = ANALYSIS / "reports" / "D0_A_GATE_STATUS.json"
    write_json(gate_path, gate)
    report = """# FTC D0-A 运行时快路径架构闭合

## 最终 Gate

**ARCHITECTURE_ESCALATION_REQUIRED**。D0-A 保留 D0-0 的 `ARCHITECTURE_REVIEW` 和 T0 的 `CONDITIONAL_GO`：T0 的 2075 ps、两个正式 L2/3002 ps 威胁及 100% CLEAN_Q1 全相位要求均未被修改。

## 已完成的最小取证

- A0 绑定 D0-0、T0、M0、M1、PD1 和 RF 权威输入；没有修改冻结合同或 runtime RTL。
- A1 重解析 91 个 M0 与 515 个 T0 retained listing，并确认没有 `.tr0` 波形；仅运行两点正式 target single-probe 诊断，补齐 CK fall/high-width、Q 90%、reset-clear 和路径 falling observability。
- A2 将真实 target CK 高宽与 RF cell timing check 合并。2075 ps 周期扣除 1.0 ns CK-high 与 1.0 ns CK-low 只余 75 ps，无法保留既有 250 ps/half-cycle guard，因此单通道为 `{classification}`，根因为 `{root_cause}`。
- A5 没有复制 sensor 或实现 bank；仅给出 2500 ps guarded-model lane 下界和 `N_min=2` 的后续评审起点。`P_lane_verified` 仍为未闭合，不能把这个模型数值写成物理完成结论。

本轮 HSPICE={hspice_count}，均为容器内 task-owned A1 诊断；没有重跑 T0-2/T0-3/T0-4/T0-5、M0、H0、M1、RF 或 XA。下一步已限定为[独立 D0-B 两 capture bank/交错架构计划](../../../plans/ftc_d0b_interleaved_capture_architecture_plan.md)：先量化新增 D/CK 负载、合法 capture 脉冲、独立 reset/re-arm 与 M/F 共享，再允许实现。
""".format(classification=a2["classification"], root_cause=a2["root_cause"],
           hspice_count=gate["simulation_accounting"]["new_hspice_scenarios"])
    REPORT.write_text(report, encoding="utf-8")
    return gate


def run_all() -> Dict[str, Any]:
    """Execute the approved D0-A path through its terminal A5 escalation."""

    run_a0()
    run_a1()
    a2 = run_a2()
    if not a2["routing"].get("a5_interleave_review_required"):
        raise RuntimeError("this D0-A runner only publishes the A5 route selected by A2")
    run_a5()
    return write_final_gate()


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Expose only approved phase entrypoints; no free-form simulator sweep exists."""

    parser = argparse.ArgumentParser(description="FTC D0-A runtime fastpath architecture closure")
    parser.add_argument("--phase", required=True,
                        choices=("a0", "a1", "a2", "a5", "finalize", "all"))
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Dispatch one Gate-aligned phase without silently running adjacent work."""

    args = parse_args(argv)
    if args.phase == "a0":
        run_a0()
    elif args.phase == "a1":
        run_a1()
    elif args.phase == "a2":
        run_a2()
    elif args.phase == "a5":
        run_a5()
    elif args.phase == "finalize":
        write_final_gate()
    else:
        run_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
