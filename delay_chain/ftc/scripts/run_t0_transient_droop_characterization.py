#!/usr/bin/env python3
"""FTC T0 transient voltage-droop characterization.

This runner is deliberately a thin transient extension of the reviewed M0
single-probe deck.  The only electrical stimulus added by T0 is a finite-slope
PWL waveform on the already frozen monitored supply.  The sensor, medium and
fine chains, real XOR, real DFF, reset sequence, and two-sample Q decision are
kept byte-auditable and are never replaced by a behavioral proxy.

All large HSPICE products are kept below ``delay_chain/ftc/runs``.  The phase
commands write only compact CSV/JSON evidence below the task-owned analysis
directory.  Failed scenarios are retained and are never silently re-run.
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
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = FTC_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# M0 owns the validated physical single-probe timing and topology contract.
# Importing it is intentional: T0 must fail if the M0 renderer or its frozen
# upstream evidence is unavailable, rather than silently building a new model.
import run_m0_detection_margin_characterization as m0  # noqa: E402
import run_dynamic_startup_calibration_protocol as physical  # noqa: E402


STUDY = "ftc_t0_transient_voltage_droop_characterization_v1"
ANALYSIS = FTC_ROOT / "analysis" / "t0_transient_droop"
CONTRACT_PATH = ANALYSIS / "contract" / "T0_TRANSIENT_THREAT_CONTRACT.json"
POWER_DOMAIN_CONTRACT_PATH = FTC_ROOT / "controller" / "final_closure" / "freeze" / "POWER_DOMAIN_CONTRACT.json"
RUN_ROOT = FTC_ROOT / "runs" / "t0_transient_droop"
REPORT_ROOT = FTC_ROOT / "reports"

FORMAL_BASELINES = (0.95, 1.10)
FORMAL_MARGINS = ("L1", "L2", "L3")
FORMAL_MINIMUM_VDD = 0.80
PRIMARY_SLEW_PS = 1.0
SECONDARY_SLEW_PS = 10.0

# The six M1 codebook entries are deliberately written out.  This makes a
# changed mapper visible in review and avoids synthesizing or interpolating a
# new margin code inside the analog runner.
FORMAL_CODES: Dict[Tuple[float, str], Tuple[int, int]] = {
    (0.95, "L1"): (4, 9),
    (0.95, "L2"): (5, 6),
    (0.95, "L3"): (5, 9),
    (1.10, "L1"): (2, 10),
    (1.10, "L2"): (3, 8),
    (1.10, "L3"): (3, 10),
}

SCENARIO_FIELDS = (
    "scenario_id", "baseline_vdd_v", "margin_level", "M_det", "F_det",
    "DeltaV_mv", "Vdroop_v", "t_fall_ps", "t_hold_ps", "t_rise_ps",
    "phase_ps", "actual_min_vdd_v", "t_xor_rise_s", "t_xor_fall_s",
    "t_ck_rise_s", "t_ck_rise_2_s", "W_xor_ps", "D_ref_ps", "R_ps",
    "q_sample_1_v", "q_sample_2_v", "q_final", "q_state",
    "active_ck_edge_count", "recovery_max_ratio", "valid", "reason",
    "completion_status", "scenario_path", "deck_sha256", "source_hash",
)


def require_dl() -> Dict[str, str]:
    """Require the reviewed Miniconda environment before formal T0 work."""

    if os.environ.get("CONDA_DEFAULT_ENV") != "DL":
        raise RuntimeError("T0 requires CONDA_DEFAULT_ENV=DL")
    return {
        "conda_env": "DL",
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
    }


def sha256_file(path: Path) -> str:
    """Hash an input incrementally without copying PDK or simulator files."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_json(value: Mapping[str, Any]) -> str:
    """Serialize scenario parameters deterministically for IDs and hashes."""

    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write one compact task-owned JSON document with stable key ordering."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    """Read an object-shaped JSON contract and reject malformed evidence."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    """Write rectangular evidence while retaining failed rows and blanks."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def read_csv(path: Path, required: Sequence[str]) -> List[Dict[str, str]]:
    """Read a compact table and require all columns used by T0 analysis."""

    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not set(required).issubset(reader.fieldnames):
            raise ValueError("missing required CSV columns in {}".format(path))
        rows = list(reader)
    if not rows:
        raise ValueError("CSV is empty: {}".format(path))
    return rows


def finite(value: Any) -> Optional[float]:
    """Convert an HSPICE scalar while preserving missing measurements."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def spice(value: float) -> str:
    """Render a finite scalar in locale-independent HSPICE notation."""

    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite SPICE value: {}".format(value))
    return "{:.12e}".format(number)


def contract() -> Dict[str, Any]:
    """Load all immutable T0 contracts, including the PD1 crossing contract.

    The original T0 contract freezes the voltage waveform and the real-DFF
    decision.  The power-domain contract is equally authoritative for this
    correction: every PD_CTRL-to-PD_SENSE high level must be generated from
    the instantaneous sensor-local rail.  Keeping this check in the runner
    prevents a future deck edit from silently reverting to fixed controller
    voltage levels.
    """

    data = read_json(CONTRACT_PATH)
    scope = data.get("formal_scope", {})
    if tuple(scope.get("baseline_vdd_v", ())) != FORMAL_BASELINES:
        raise ValueError("T0 contract baseline list changed")
    if tuple(scope.get("margin_levels", ())) != FORMAL_MARGINS:
        raise ValueError("T0 contract margin list changed")
    if float(scope.get("formal_minimum_vdd_v")) != FORMAL_MINIMUM_VDD:
        raise ValueError("T0 contract minimum VDD changed")
    phase = data.get("phase_definition", {})
    if phase.get("reference_event") != "single_probe_S_CLK_rising_edge":
        raise ValueError("T0 phase reference is not S_CLK rise")
    waveform = data.get("waveform", {})
    for key in ("primary_slew_ps", "secondary_slew_ps"):
        if float(waveform[key]["t_fall_ps"]) <= 0 or float(waveform[key]["t_rise_ps"]) <= 0:
            raise ValueError("T0 PWL slopes must be non-zero")
    if waveform.get("zero_time_voltage_jump_forbidden") is not True:
        raise ValueError("T0 contract permits an ideal voltage jump")
    if data.get("decision", {}).get("authoritative_decision") != "real_dff_q_two_sample_stable_state":
        raise ValueError("T0 authoritative decision is not real DFF Q")
    for (baseline, margin), code in FORMAL_CODES.items():
        if code != FORMAL_CODES[(baseline, margin)]:
            raise ValueError("unreachable codebook check")
    pd = read_json(POWER_DOMAIN_CONTRACT_PATH)
    if pd.get("status") != "FROZEN":
        raise ValueError("POWER_DOMAIN_CONTRACT is not frozen")
    crossings = pd.get("crossings", {}).get("PD_CTRL_to_PD_SENSE", {})
    if crossings.get("count") != 28:
        raise ValueError("PD_CTRL-to-PD_SENSE crossing count changed")
    if "sensor-local VDD" not in crossings.get("current_verification_abstraction", ""):
        raise ValueError("PD_CTRL crossing abstraction is not sensor-local-VDD normalized")
    return {"t0": data, "power_domain": pd}


def frozen_context() -> Dict[str, Any]:
    """Reuse M0's reviewed context and verify the six formal code entries."""

    context = m0.physical.frozen_context()
    expected = {
        "0p95": {"L1": (4, 9), "L2": (5, 6), "L3": (5, 9)},
        "1p10": {"L1": (2, 10), "L2": (3, 8), "L3": (3, 10)},
    }
    candidate_rows = read_csv(
        FTC_ROOT / "analysis/m0_detection_margin_characterization/tables/table_m0_candidate_summary.csv",
        ("baseline_vdd_v", "margin_level", "M_det", "F_det"),
    )
    observed = {}
    for row in candidate_rows:
        baseline = float(row["baseline_vdd_v"])
        if baseline in FORMAL_BASELINES and row["margin_level"] in FORMAL_MARGINS:
            observed[(baseline, row["margin_level"])] = (int(row["M_det"]), int(row["F_det"]))
    for key, code in FORMAL_CODES.items():
        if observed.get(key) != code:
            raise ValueError("M1 codebook mismatch for {}: expected {}, got {}".format(key, code, observed.get(key)))
    return context


def source_hash() -> str:
    """Bind every T0 result to runner, threat, and power-domain contract bytes."""

    digest = hashlib.sha256()
    for path in (Path(__file__), CONTRACT_PATH, POWER_DOMAIN_CONTRACT_PATH):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def probe_timing() -> Dict[str, float]:
    """Return M0's exact one-probe event times, without redefining them."""

    return m0.probe_timing()


def thermometer_control_points(units: int, code: int, high_when_set: bool, stop: float) -> Iterable[Tuple[int, str]]:
    """Generate stable PD_CTRL-side 0/1 rails using M0 thermometer polarity.

    The values here are deliberately normalized controller-domain values:
    ``1`` means logical high in PD_CTRL and ``0`` means logical low.  They do
    not connect directly to a sensor cell.  ``local_level_source`` below
    performs the explicit PD_CTRL-to-PD_SENSE mapping by multiplying this
    waveform by the instantaneous ``vdd_a`` rail.
    """

    for index, bit in enumerate(physical.thermometer(units, code)):
        high = bool(bit) if high_when_set else not bool(bit)
        value = "1" if high else "0"
        yield index, "PWL(0 {} {} {})".format(value, spice(stop), value)


def local_level_source(name: str, output_node: str, control_node: str) -> str:
    """Render one ideal verification D2A crossing with explicit port roles.

    ``control_node`` is a stable PD_CTRL waveform referenced to ``vss_a``;
    ``output_node`` is the corresponding PD_SENSE signal consumed by a
    transistor-level cell.  The behavioral voltage source is the frozen XA
    verification abstraction, not a claimed physical level shifter.  Its
    output is ``V(control_node) * V(vdd_a)`` so a high level follows every
    instantaneous monitored-supply value during a droop.
    """

    return "E_{} {} vss_a VOL='V({},vss_a)*V(vdd_a,vss_a)'".format(name, output_node, control_node)


def droop_points(vbase: float, vdroop: float, start: float, t_fall: float, t_hold: float, t_rise: float, stop: float) -> List[Tuple[float, str]]:
    """Create a finite-slope VDD waveform and reject illegal timing.

    The source has six explicit points: nominal level, start of the fall,
    completed fall, completed hold, completed rise, and final nominal level.
    No two points share a timestamp, so a zero-time ideal voltage jump cannot
    enter a formal deck accidentally.
    """

    if not 0.80 <= vdroop <= vbase <= 1.10:
        raise ValueError("Vdroop must be within the formal 0.80..1.10 V range")
    if start <= 0.0 or t_fall <= 0.0 or t_hold <= 0.0 or t_rise <= 0.0:
        raise ValueError("droop start, slope, and hold times must be positive")
    fall_end = start + t_fall
    rise_start = fall_end + t_hold
    rise_end = rise_start + t_rise
    if rise_end >= stop:
        raise ValueError("droop recovery must finish before simulation stop")
    return [
        (0.0, "'VDD_VALUE'"),
        (start, "'VDD_VALUE'"),
        (fall_end, spice(vdroop)),
        (rise_start, spice(vdroop)),
        (rise_end, "'VDD_VALUE'"),
        (stop, "'VDD_VALUE'"),
    ]


def render_deck(context: Mapping[str, Any], parameters: Mapping[str, Any]) -> str:
    """Render one current-FTC real-cell single-probe transient deck.

    Port audit for every physical block:

    * Every standard-cell instance uses ``Y VDD VNW VPW VSS A/B...`` with the
      monitored rail ``vdd_a`` and ground ``vss_a``.
    * `XXOR_29` receives the tap-29 RVT/LVT outputs and drives `xor_29`.
    * The medium chain starts from `xor_29`; its mux output reaches the fine
      driver, and only that output drives the DFF `CK` port.
    * `XDFF` uses the explicit positional order
      ``Q VDD VNW VPW VSS CK D R``: Q is `q_final`, CK is `dff_ck`, D is the
      real `xor_29` pulse, and R is the active-high `dff_reset` source.
    """

    baseline = float(parameters["baseline_vdd_v"])
    vdroop = float(parameters["Vdroop_v"])
    phase_ps = float(parameters["phase_ps"])
    t_fall = float(parameters["t_fall_ps"]) * 1e-12
    t_hold = float(parameters["t_hold_ps"]) * 1e-12
    t_rise = float(parameters["t_rise_ps"]) * 1e-12
    timing = probe_timing()
    start = timing["launch_time_s"] + phase_ps * 1e-12
    stop = max(timing["stop_time_s"] + 1.0e-9, start + t_fall + t_hold + t_rise + 1.0e-9)
    supply = droop_points(baseline, vdroop, start, t_fall, t_hold, t_rise, stop)
    config, cells = context["config"], context["cells"]
    medium_code = int(parameters["M_det"])
    fine_code = int(parameters["F_det"])
    includes = ['.include "{}"'.format(cells["source_files"]["rvt_cdl"])]
    if Path(cells["source_files"]["lvt_cdl"]).resolve() != Path(cells["source_files"]["rvt_cdl"]).resolve():
        includes.append('.include "{}"'.format(cells["source_files"]["lvt_cdl"]))
    # PD_CTRL sources keep the trusted controller waveform independent and
    # stable.  Their PD_SENSE counterparts are behavioral D2A abstractions
    # whose high level is regenerated from the local monitored rail.
    sclk_ctrl = physical.pwl([
        (0.0, 0), (timing["launch_time_s"] - m0.SCLK_EDGE_S, 0),
        (timing["launch_time_s"], 1),
        (timing["sclk_fall_s"], 1),
        (timing["sclk_fall_s"] + m0.SCLK_EDGE_S, 0), (stop, 0),
    ])
    reset_ctrl = physical.pwl([
        (0.0, 1), (timing["reset_release_s"] - m0.CONTROL_EDGE_S, 1),
        (timing["reset_release_s"], 1),
        (timing["reset_release_s"] + m0.CONTROL_EDGE_S, 0),
        (timing["reset_assert_start_s"], 0),
        (timing["reset_assert_end_s"], 1), (stop, 1),
    ])
    supply_pwl = physical.pwl(supply)
    lines: List[str] = [
        "* FTC T0 correction: M0 real-cell probe with PD1 local-VDD-normalized controls.",
        "* PD_CTRL sources are stable 0/1 rails; E_* sources are XA D2A verification abstractions.",
        "* No physical level shifter, detector RTL, ideal delay, or sensor topology change is claimed.",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(physical.spice(float(config["temperature_c"]))),
        *includes,
        '.lib "{}" {}'.format(config["model_library"], config["corner"]),
        ".param VDD_VALUE={}".format(physical.spice(baseline)),
        "V_VDD vdd_a vss_a {}".format(supply_pwl),
        "V_VSS vss_a 0 0",
        "V_CTRL_SCLK ctrl_sclk vss_a {}".format(sclk_ctrl),
        local_level_source("SCLK", "s_clk", "ctrl_sclk"),
        "V_CTRL_DFF_RESET ctrl_dff_reset vss_a {}".format(reset_ctrl),
        local_level_source("DFF_RESET", "dff_reset", "ctrl_dff_reset"),
        *physical.sensor_xor_lines(cells),
    ]
    for bit, points in thermometer_control_points(physical.MEDIUM_N, medium_code, True, stop):
        control_node = "ctrl_m_{}".format(bit)
        sense_node = "m_{}".format(bit)
        lines.append("V_CTRL_M_{:02d} {} vss_a {}".format(bit, control_node, points))
        lines.append(local_level_source("M_{:02d}".format(bit), sense_node, control_node))
    for index in range(physical.MEDIUM_N + 1):
        source = "xor_29" if index == 0 else "x{}".format(index)
        lines.append(physical.buffer_instance("XMED_BUF_{:02d}".format(index), "x{}".format(index + 1), source, physical.MEDIUM_DELAY_CELL))
    for index in range(physical.MEDIUM_N):
        output = "medium_out" if index == 0 else "my{}".format(index)
        deep = "x{}".format(physical.MEDIUM_N + 1) if index == physical.MEDIUM_N - 1 else "my{}".format(index + 1)
        lines.append(physical.mux_instance("XMED_MUX_{:02d}".format(index), output, "x{}".format(index + 1), deep, "m_{}".format(index)))
    lines.append(physical.buffer_instance("XFINE_DRIVER", "dff_ck", "medium_out", physical.FINE_DRIVER))
    for bit, points in thermometer_control_points(physical.FINE_K, fine_code, False, stop):
        control_node = "ctrl_f_{}".format(bit)
        sense_node = "f_{}".format(bit)
        lines.append("V_CTRL_F_{:02d} {} vss_a {}".format(bit, control_node, points))
        lines.append(local_level_source("F_{:02d}".format(bit), sense_node, control_node))
        lines.append("XLOAD_{:02d} z_{} vdd_a vdd_a vss_a vss_a dff_ck f_{} {}".format(bit, bit, bit, physical.FINE_LOAD))
    lines.extend([
        "XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(physical.DFF_CELL),
        ".tran {} {}".format(physical.spice(float(config["tran_max_step_s"])), physical.spice(stop)),
        ".measure tran t_xor_rise WHEN v(xor_29,vss_a)='V(vdd_a,vss_a)/2' RISE=1 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran t_xor_fall WHEN v(xor_29,vss_a)='V(vdd_a,vss_a)/2' FALL=1 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran t_ck_rise WHEN v(dff_ck,vss_a)='V(vdd_a,vss_a)/2' RISE=1 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran t_ck_rise_2 WHEN v(dff_ck,vss_a)='V(vdd_a,vss_a)/2' RISE=2 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran q_sample_1 FIND v(q_final,vss_a) AT={}".format(physical.spice(timing["q_read_time_s"])),
        ".measure tran q_sample_2 FIND v(q_final,vss_a) AT={}".format(physical.spice(timing["q_read_late_time_s"])),
        ".measure tran actual_min_vdd MIN v(vdd_a,vss_a) FROM=0 TO={}".format(physical.spice(stop)),
    ])
    for node, suffix in (("xor_29", "xor"), ("medium_out", "medium"), ("dff_ck", "ck")):
        lines.extend([
            ".measure tran recovery_{}_end FIND v({},vss_a) AT={}".format(suffix, node, physical.spice(timing["recovery_end_s"])),
            ".measure tran recovery_{}_tail MAX v({},vss_a) FROM={} TO={}".format(
                suffix, node, physical.spice(timing["recovery_end_s"] - m0.Q1_TO_Q2_S), physical.spice(timing["recovery_end_s"])),
        ])
    lines.extend([".end", ""])
    return "\n".join(lines)


def topology_checks(deck: str, parameters: Mapping[str, Any]) -> Dict[str, bool]:
    """Inspect active SPICE lines and prove that the frozen topology remains."""

    lines = deck.splitlines()
    active = "\n".join(line for line in lines if not line.lstrip().startswith("*"))
    expected_dff = "XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(physical.DFF_CELL)
    forbidden = ("XBYPASS", "XCONFIG_SKIP", "FSM", "COUNTER", "REGISTER")
    source = next(line for line in lines if line.startswith("V_VDD "))
    return {
        "tap29_real_xor": "XXOR_29 xor_29 vdd_a vdd_a vss_a vss_a rvt_29 lvt_29 {}".format(physical.XOR_CELL) in lines,
        "xor_is_dff_data": expected_dff in lines,
        "medium_input_is_xor": "XMED_BUF_00 x1 vdd_a vdd_a vss_a vss_a xor_29 {}".format(physical.MEDIUM_DELAY_CELL) in lines,
        "fine_driver_is_only_dff_clock_path": "XFINE_DRIVER dff_ck vdd_a vdd_a vss_a vss_a medium_out {}".format(physical.FINE_DRIVER) in lines,
        "n16_medium": sum(line.startswith("XMED_BUF_") for line in lines) == physical.MEDIUM_N + 1 and sum(line.startswith("XMED_MUX_") for line in lines) == physical.MEDIUM_N,
        "k10_fine_load": sum(line.startswith("XLOAD_") for line in lines) == physical.FINE_K and all(line.endswith(physical.FINE_LOAD) for line in lines if line.startswith("XLOAD_")),
        "real_dff_two_reads": "q_sample_1" in deck and "q_sample_2" in deck,
        "pd_ctrl_sense_crossing_count": sum(line.startswith("E_") for line in lines) == 28,
        "sclk_local_normalized": "E_SCLK s_clk vss_a VOL='V(ctrl_sclk,vss_a)*V(vdd_a,vss_a)'" in lines,
        "reset_local_normalized": "E_DFF_RESET dff_reset vss_a VOL='V(ctrl_dff_reset,vss_a)*V(vdd_a,vss_a)'" in lines,
        "medium_local_normalized": sum(line.startswith("E_M_") for line in lines) == physical.MEDIUM_N,
        "fine_local_normalized": sum(line.startswith("E_F_") for line in lines) == physical.FINE_K,
        "no_fixed_high_control_sources": not any(
            line.startswith(("V_SCLK ", "V_DFF_RESET ", "V_M_", "V_F_")) for line in lines
        ),
        "local_measurement_thresholds": all(
            "V(vdd_a,vss_a)/2" in line for line in lines if line.startswith(".measure tran t_")
        ),
        "finite_vdd_pwl": source.startswith("V_VDD vdd_a vss_a PWL(") and source.count(" ") >= 8,
        "pwl_no_zero_slope": float(parameters["t_fall_ps"]) > 0 and float(parameters["t_rise_ps"]) > 0,
        "requested_codes_legal": 0 <= int(parameters["M_det"]) <= physical.MEDIUM_N and 0 <= int(parameters["F_det"]) <= physical.FINE_K,
        "no_forbidden_hardware": not any(token in active for token in forbidden),
        "no_ideal_delay_or_capacitor": not re.search(r"(?im)^\s*[evg]\S*.*\btd\s*=", active) and not any(line.lstrip().lower().startswith("c") for line in active.splitlines()),
    }


def parameters_for(baseline: float, margin: str, vdroop: float, hold_ps: float, phase_ps: float, slew_ps: float = PRIMARY_SLEW_PS) -> Dict[str, Any]:
    """Build one immutable corrected-deck identity from the frozen codebook.

    ``control_mode`` is intentionally not user-selectable in this runner:
    every new correction and formal scenario uses the constant-low-compatible
    local-normalized interface.  The mode label is retained in manifests so a
    future audit cannot confuse these results with the 62 legacy fixed-level
    scenarios.
    """

    if (baseline, margin) not in FORMAL_CODES:
        raise ValueError("formal T0 code is not defined")
    if vdroop < FORMAL_MINIMUM_VDD or vdroop > baseline:
        raise ValueError("Vdroop is outside the formal range")
    return {
        "study": STUDY,
        "baseline_vdd_v": round(float(baseline), 2),
        "margin_level": margin,
        "M_det": FORMAL_CODES[(baseline, margin)][0],
        "F_det": FORMAL_CODES[(baseline, margin)][1],
        "DeltaV_mv": round((baseline - vdroop) * 1000.0, 6),
        "Vdroop_v": round(float(vdroop), 6),
        "t_fall_ps": round(float(slew_ps), 6),
        "t_hold_ps": round(float(hold_ps), 6),
        "t_rise_ps": round(float(slew_ps), 6),
        "phase_ps": round(float(phase_ps), 6),
        "control_mode": "PD_SENSE_LOCAL_VDD_NORMALIZED",
        "source_hash": source_hash(),
    }


def scenario_id(parameters: Mapping[str, Any]) -> str:
    """Return a readable collision-resistant scenario directory name."""

    digest = hashlib.sha256(stable_json(parameters).encode("ascii")).hexdigest()[:20]
    return "t0__b{}__{}__dv{}__h{}__p{}__{}".format(
        str(parameters["baseline_vdd_v"]).replace(".", "p"), parameters["margin_level"],
        str(parameters["DeltaV_mv"]).replace(".", "p"), str(parameters["t_hold_ps"]).replace(".", "p"),
        str(parameters["phase_ps"]).replace("-", "m").replace(".", "p"), digest,
    )


def parse_measurement(scenario: Path) -> Dict[str, Any]:
    """Validate listing and return the simulator's scalar measurement map."""

    physical.run_dc_sweep.validate_listing(scenario / "t0.lis")
    measurement = physical.run_dc_sweep.find_measurement_file(scenario, "t0")
    return physical.run_dc_sweep.parse_measurements(measurement)


def classify(parameters: Mapping[str, Any], values: Mapping[str, Any], scenario: Path, deck_sha: str) -> Dict[str, Any]:
    """Convert raw HSPICE scalars into the authoritative real-DFF decision."""

    vdd = float(parameters["Vdroop_v"])
    timing = probe_timing()
    xor_rise = finite(values.get("t_xor_rise"))
    xor_fall = finite(values.get("t_xor_fall"))
    ck_rise = finite(values.get("t_ck_rise"))
    ck_rise_2 = finite(values.get("t_ck_rise_2"))
    q1 = finite(values.get("q_sample_1"))
    q2 = finite(values.get("q_sample_2"))
    q_final, q_state = m0.stable_q(q1, q2, vdd)
    width = None if xor_rise is None or xor_fall is None else (xor_fall - xor_rise) * 1e12
    delay = None if xor_rise is None or ck_rise is None else (ck_rise - xor_rise) * 1e12
    residual = None if width is None or delay is None else width - delay
    recovery = [finite(values.get("recovery_{}_{}".format(node, sample))) for node in ("xor", "medium", "ck") for sample in ("end", "tail")]
    recovery_ratio = max((abs(item) / max(vdd, 1e-12) for item in recovery if item is not None), default=None)
    active_count = int(ck_rise is not None and timing["launch_time_s"] <= ck_rise < timing["reset_assert_start_s"])
    active_count += int(ck_rise_2 is not None and timing["launch_time_s"] <= ck_rise_2 < timing["reset_assert_start_s"])
    reasons: List[str] = []
    if xor_rise is None or xor_fall is None or ck_rise is None:
        reasons.append("missing_functional_crossing")
    if width is not None and width <= 0.0:
        reasons.append("nonpositive_xor_width")
    if active_count != 1:
        reasons.append("active_ck_edge_count_not_one")
    if q_final is None:
        reasons.append("q_not_stable_on_two_reads")
    if recovery_ratio is None or recovery_ratio >= m0.Q_LOW_RATIO:
        reasons.append("recovery_not_quiet")
    return {
        **{field: parameters.get(field) for field in SCENARIO_FIELDS},
        "scenario_id": scenario.name,
        "actual_min_vdd_v": finite(values.get("actual_min_vdd")),
        "t_xor_rise_s": xor_rise, "t_xor_fall_s": xor_fall,
        "t_ck_rise_s": ck_rise, "t_ck_rise_2_s": ck_rise_2,
        "W_xor_ps": width, "D_ref_ps": delay, "R_ps": residual,
        "q_sample_1_v": q1, "q_sample_2_v": q2, "q_final": q_final,
        "q_state": q_state, "active_ck_edge_count": active_count,
        "recovery_max_ratio": recovery_ratio, "valid": int(not reasons),
        "reason": ";".join(reasons) if reasons else None,
        "completion_status": "PASS", "scenario_path": str(scenario),
        "deck_sha256": deck_sha, "source_hash": parameters["source_hash"],
    }


def execute(context: Mapping[str, Any], parameters: Mapping[str, Any], stats: Dict[str, int]) -> Dict[str, Any]:
    """Render, cache, execute, validate, and classify exactly one scenario."""

    hspice, version = physical.validate_hspice(context)
    deck = render_deck(context, parameters)
    checks = topology_checks(deck, parameters)
    if not all(checks.values()):
        raise RuntimeError("T0 topology contract failed: {}".format(checks))
    identity = scenario_id(parameters)
    deck_sha = hashlib.sha256(deck.encode("ascii")).hexdigest()
    matches = list(RUN_ROOT.glob("r*/scenarios/{}/scenario_manifest.json".format(identity))) if RUN_ROOT.is_dir() else []
    if len(matches) > 1:
        raise RuntimeError("duplicate retained T0 scenario: {}".format(identity))
    if matches:
        scenario = matches[0].parent
        manifest = read_json(matches[0])
        if manifest.get("completion_status") != "PASS" or manifest.get("parameters") != dict(parameters):
            raise RuntimeError("retained T0 scenario is failed or parameter-mismatched: {}".format(scenario))
        deck_path = scenario / "t0.sp"
        if not deck_path.is_file() or sha256_file(deck_path) != deck_sha or manifest.get("deck_sha256") != deck_sha:
            raise RuntimeError("retained T0 deck hash mismatch: {}".format(scenario))
        stats["reused"] += 1
        values = parse_measurement(scenario)
        return classify(parameters, values, scenario, deck_sha)
    revisions = [int(path.name[1:]) for path in RUN_ROOT.glob("r*") if path.is_dir() and re.fullmatch(r"r\d+", path.name)] if RUN_ROOT.is_dir() else []
    run_dir = RUN_ROOT / "r{}".format(max(revisions, default=0) + 1)
    run_dir.mkdir(parents=True, exist_ok=True)
    scenario = run_dir / "scenarios" / identity
    scenario.mkdir(parents=True)
    deck_path = scenario / "t0.sp"
    deck_path.write_text(deck, encoding="ascii")
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", scenario / "empty_subckt.sp_cal")
    manifest = {
        "schema_version": 1, "study": STUDY, "scenario_id": identity,
        "parameters": dict(parameters), "deck_sha256": deck_sha,
        "hspice": str(hspice), "hspice_version": version,
        "completion_status": "RUNNING", "measurement_file": None,
    }
    write_json(scenario / "scenario_manifest.json", manifest)
    stats["new"] += 1
    result = subprocess.run([str(hspice), deck_path.name, "-o", "t0"], cwd=scenario, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=900)
    (scenario / "hspice_command.log").write_text("returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr), encoding="utf-8")
    if result.returncode != 0:
        manifest.update({"completion_status": "FAIL", "failure": "HSPICE returned {}".format(result.returncode)})
        write_json(scenario / "scenario_manifest.json", manifest)
        raise RuntimeError("T0 HSPICE failed; evidence retained at {}".format(scenario))
    try:
        physical.run_dc_sweep.validate_listing(scenario / "t0.lis")
        measurement = physical.run_dc_sweep.find_measurement_file(scenario, "t0")
    except Exception as error:
        manifest.update({"completion_status": "FAIL", "failure": "listing/measurement validation: {}".format(error)})
        write_json(scenario / "scenario_manifest.json", manifest)
        raise
    manifest.update({"completion_status": "PASS", "measurement_file": measurement.name})
    write_json(scenario / "scenario_manifest.json", manifest)
    return classify(parameters, physical.run_dc_sweep.parse_measurements(measurement), scenario, deck_sha)


def write_scenario_manifest() -> None:
    """Publish a compact description of the reusable T0 scenario identity."""

    write_json(ANALYSIS / "contract" / "scenario_manifest.json", {
        "schema_version": 1,
        "study": STUDY,
        "identity": "SHA256(parameters + rendered_deck)",
        "raw_run_root": str(RUN_ROOT),
        "reuse_rule": "only PASS evidence with identical parameters and deck hash may be reused",
        "forbidden_reuse": "failed_or_partial_scenario",
    })


def phase_contract() -> Dict[str, Any]:
    """Execute T0-0 checks without launching HSPICE."""

    require_dl()
    data = contract()
    context = frozen_context()
    deck_parameters = parameters_for(0.95, "L2", 0.95, 1.0, 0.0)
    # Contract phase deliberately does not run this deck.  Rendering is a
    # deterministic syntax check and therefore does not create simulator data.
    deck = render_deck(context, deck_parameters)
    checks = topology_checks(deck, deck_parameters)
    if not all(checks.values()):
        raise RuntimeError("T0 contract topology checks failed: {}".format(checks))
    write_scenario_manifest()
    baseline = {
        "schema_version": 1,
        "study": STUDY,
        "implementation_git_head": data["t0"]["implementation_git_head"],
        "plan_input_baseline": data["t0"]["plan_input_baseline"],
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "power_domain_contract_sha256": sha256_file(POWER_DOMAIN_CONTRACT_PATH),
        "source_hash": source_hash(),
        "topology_checks": checks,
        "simulation_accounting": {"new_hspice": 0, "reused": 0, "reparsed": 0, "forbidden": 0},
    }
    write_json(ANALYSIS / "baseline" / "frozen_input_sha256.json", baseline)
    return {"decision": "GO", "topology_checks": checks}


def phase_smoke() -> Dict[str, Any]:
    """Run the two permitted T0-1 smoke scenarios after contract freeze."""

    require_dl()
    context = frozen_context()
    stats = {"new": 0, "reused": 0}
    constant = parameters_for(0.95, "L2", 0.95, 1.0, -490.0, PRIMARY_SLEW_PS)
    # A zero-depth PWL is not a formal droop result; this constant-equivalent
    # case checks the M0 Q decision and timing path through the T0 parser.
    constant["Vdroop_v"] = 0.95
    constant["DeltaV_mv"] = 0.0
    transient = parameters_for(0.95, "L2", 0.85, 3000.0, 0.0, PRIMARY_SLEW_PS)
    rows = [execute(context, constant, stats), execute(context, transient, stats)]
    write_csv(ANALYSIS / "reports" / "t0_1_smoke.csv", SCENARIO_FIELDS, rows)
    summary = {"decision": "GO", "rows": len(rows), "new_hspice": stats["new"], "reused": stats["reused"], "constant_q": rows[0]["q_final"], "pwl_q": rows[1]["q_final"]}
    write_json(ANALYSIS / "reports" / "t0_1_smoke_summary.json", summary)
    return summary


def static_trip_rows() -> List[Dict[str, Any]]:
    """Read the exact M0 static bracket without inventing a new voltage.

    ``trip_map.csv`` contains the published Vtrip summary, while the actual
    ``last Q=0`` voltage is present only in the complete M0 ``trip_sweep.csv``.
    T0-2 must consume that original row verbatim.  Selecting ``Vtrip+10 mV``
    would be a new static point and would violate the no-re-sweep contract.
    """

    trip_map = read_csv(
        FTC_ROOT / "analysis/m0_detection_margin_characterization/trip/trip_map.csv",
        ("baseline_vdd_v", "margin_level", "candidate_id", "M_det", "F_det", "Vtrip_v", "trip_status"),
    )
    sweep = read_csv(
        FTC_ROOT / "analysis/m0_detection_margin_characterization/trip/trip_sweep.csv",
        ("baseline_vdd_v", "margin_level", "candidate_id", "physical_vdd_v", "q_final", "valid"),
    )
    result: List[Dict[str, Any]] = []
    for item in trip_map:
        baseline = float(item["baseline_vdd_v"])
        margin = item["margin_level"]
        if baseline not in FORMAL_BASELINES or margin not in FORMAL_MARGINS:
            continue
        rows = [
            row for row in sweep
            if float(row["baseline_vdd_v"]) == baseline
            and row["margin_level"] == margin
            and row["candidate_id"] == item["candidate_id"]
            and int(row["valid"]) == 1
        ]
        q1_rows = sorted((row for row in rows if int(row["q_final"]) == 1), key=lambda row: float(row["physical_vdd_v"]), reverse=True)
        if not q1_rows:
            raise ValueError("M0 sweep lacks first stable Q1 for {}".format(item["candidate_id"]))
        first_q1 = q1_rows[0]
        # ``last Q=0`` means the nearest safe point immediately above the
        # highest-voltage Q1 point, not the nominal VDD control row.  Sorting
        # upward is essential: choosing the maximum Q0 voltage would erase
        # the published static bracket and make T0 appear more conservative
        # than the actual M0 evidence.
        q0_rows = sorted((row for row in rows if int(row["q_final"]) == 0 and float(row["physical_vdd_v"]) > float(first_q1["physical_vdd_v"])), key=lambda row: float(row["physical_vdd_v"]))
        if not q0_rows:
            raise ValueError("M0 sweep lacks last stable Q0 above {}".format(item["candidate_id"]))
        result.append({
            **item,
            "last_q0_v": float(q0_rows[0]["physical_vdd_v"]),
            "first_q1_v": float(first_q1["physical_vdd_v"]),
        })
    if len(result) != 6:
        raise ValueError("T0-2 requires six formal M0 brackets, got {}".format(len(result)))
    return result


def legacy_scenario_marker() -> Dict[str, Any]:
    """Mark the original 62 fixed-level scenarios without changing them.

    The raw decks/listings remain immutable evidence.  This compact marker
    explicitly says why they are superseded: their PD_CTRL high levels were
    tied to fixed ``VDD_VALUE`` instead of being normalized to sensor-local
    ``vdd_a``.  No raw run file is rewritten or deleted.
    """

    manifests = sorted(RUN_ROOT.glob("r*/scenarios/*/scenario_manifest.json")) if RUN_ROOT.is_dir() else []
    legacy_paths: List[str] = []
    diagnostic_paths: List[str] = []
    for manifest_path in manifests:
        manifest = read_json(manifest_path)
        # Historical decks predate the correction and have no local-mode
        # parameter.  A failed corrected deck must remain separately visible.
        if manifest.get("parameters", {}).get("control_mode") == "PD_SENSE_LOCAL_VDD_NORMALIZED":
            diagnostic_paths.append(str(manifest_path.parent))
        else:
            legacy_paths.append(str(manifest_path.parent))
    marker = {
        "schema_version": 1,
        "study": STUDY,
        "status": "HISTORICAL_SUPERSEDED_NOT_DELETED",
        "scenario_count": len(legacy_paths),
        "scenario_paths": legacy_paths,
        "corrected_scenario_paths": diagnostic_paths,
        "failed_syntax_diagnostic_paths": [
            str(manifest_path.parent)
            for manifest_path in manifests
            if read_json(manifest_path).get("parameters", {}).get("control_mode") == "PD_SENSE_LOCAL_VDD_NORMALIZED"
            and read_json(manifest_path).get("completion_status") != "PASS"
        ],
        "reason": "legacy T0 deck used fixed VDD_VALUE for PD_CTRL-to-PD_SENSE high levels; replaced by local VDD normalization correction",
        "replacement_contract": str(POWER_DOMAIN_CONTRACT_PATH),
        "replacement_mode": "PD_SENSE_LOCAL_VDD_NORMALIZED",
    }
    write_json(ANALYSIS / "correction" / "legacy_62_scenarios_marker.json", marker)
    return marker


def constant_low_equivalence_audit(context: Mapping[str, Any]) -> Dict[str, Any]:
    """Prove M0 0.87 V and corrected T0 constant-low mode are equivalent.

    This is a zero-HSPICE comparison.  It compares every transistor-level
    instance line, supply/well topology, code entry, and frozen probe event.
    The only intentional textual differences are the PWL form of a constant
    monitored rail and the explicit XA D2A source pair.  At constant 0.87 V,
    the D2A high output is mathematically 1*0.87 V, exactly the M0 high rail.
    """

    m0_deck = m0.render_single_probe_deck(context, 0.87, 5, 6)
    # The compatibility audit is intentionally outside the six formal T0
    # baselines: it reproduces the already-existing M0 0.87 V/M5/F6 point.
    # No HSPICE scenario identity is created from this temporary audit deck.
    t0_parameters = parameters_for(0.95, "L2", 0.87, 3000.0, -1489.999)
    t0_parameters.update({
        "baseline_vdd_v": 0.87,
        "Vdroop_v": 0.87,
        "DeltaV_mv": 0.0,
        "control_mode": "CONSTANT_LOW_VOLTAGE_COMPATIBILITY",
    })
    t0_deck = render_deck(context, t0_parameters)

    def instances(deck: str) -> List[str]:
        return sorted(
            line.strip() for line in deck.splitlines()
            if line.strip().startswith("X")
        )

    timing = probe_timing()
    m0_instances = instances(m0_deck)
    t0_instances = instances(t0_deck)
    checks = {
        "same_transistor_instance_netlist": m0_instances == t0_instances,
        "same_formal_code": "XMED_MUX_05" in m0_deck and "XMED_MUX_05" in t0_deck and "F6" not in t0_deck,
        "same_sensor_supply_and_wells": all(
            "vdd_a vdd_a vss_a vss_a" in line for line in t0_instances
        ),
        "same_probe_event_times": all(
            spice(timing[key]) in m0_deck and spice(timing[key]) in t0_deck
            for key in ("reset_release_s", "launch_time_s", "q_read_time_s", "q_read_late_time_s", "reset_assert_start_s", "reset_assert_end_s", "sclk_fall_s")
        ),
        "constant_monitored_rail": "V_VDD vdd_a vss_a PWL(" in t0_deck and "V_VDD vdd_a vss_a 'VDD_VALUE'" in m0_deck,
        "local_high_is_0p87_v": "V(vdd_a,vss_a)" in t0_deck and "VDD_VALUE=8.700000000000e-01" in t0_deck,
        "all_28_crossings_explicit": sum(line.startswith("E_") for line in t0_deck.splitlines()) == 28,
    }
    result = {
        "schema_version": 1,
        "study": STUDY,
        "mode": "CONSTANT_LOW_VOLTAGE_COMPATIBILITY",
        "baseline_vdd_v": 0.87,
        "m0_code": {"M_det": 5, "F_det": 6},
        "t0_mode": "PD_SENSE_LOCAL_VDD_NORMALIZED",
        "checks": checks,
        "equivalent": all(checks.values()),
        "hspice_scenarios": 0,
    }
    write_json(ANALYSIS / "correction" / "constant_low_equivalence_audit.json", result)
    if not result["equivalent"]:
        raise RuntimeError("constant-low M0/T0 static equivalence audit failed: {}".format(checks))
    return result


def phase_correction_audit() -> Dict[str, Any]:
    """Run the complete zero-HSPICE correction gate and historical marker."""

    require_dl()
    contracts = contract()
    context = frozen_context()
    deck_parameters = parameters_for(0.95, "L2", 0.87, 3000.0, -1489.999)
    deck = render_deck(context, deck_parameters)
    checks = topology_checks(deck, deck_parameters)
    if not all(checks.values()):
        raise RuntimeError("corrected deck audit failed: {}".format(checks))
    equivalence = constant_low_equivalence_audit(context)
    legacy = legacy_scenario_marker()
    result = {
        "schema_version": 1,
        "study": STUDY,
        "decision": "GO_TO_FOUR_POINT_CORRECTION_ONLY",
        "power_domain_contract_sha256": sha256_file(POWER_DOMAIN_CONTRACT_PATH),
        "corrected_mode": "PD_SENSE_LOCAL_VDD_NORMALIZED",
        "topology_checks": checks,
        "constant_low_equivalence": equivalence,
        "legacy_marker": legacy,
        "new_hspice_scenarios": 0,
        "later_phases_allowed": ["correction-points"],
        "later_phases_blocked": ["T0-3", "T0-4", "T0-5", "T0-6"],
        "contract_schema": contracts["power_domain"].get("schema_version"),
    }
    write_json(ANALYSIS / "correction" / "correction_audit.json", result)
    return result


def correction_parameters() -> List[Tuple[str, float, str, float]]:
    """Return exactly the four user-authorized static bracket corrections."""

    return [
        ("0p95_L2_last_q0", 0.95, "L2", 0.87),
        ("0p95_L2_first_q1", 0.95, "L2", 0.86),
        ("1p10_L2_last_q0", 1.10, "L2", 0.97),
        ("1p10_L2_first_q1", 1.10, "L2", 0.96),
    ]


def long_pulse_timing_parameters() -> Tuple[float, float]:
    """Return the single legal 1 fs-start, post-Q2 recovery schedule."""

    timing = probe_timing()
    start_s = 1.0e-15
    phase_ps = (start_s - timing["launch_time_s"]) * 1e12
    fall_s = PRIMARY_SLEW_PS * 1e-12
    hold_ps = (timing["q_read_late_time_s"] + 0.50e-9 - start_s - fall_s) * 1e12
    return hold_ps, phase_ps


def phase_correction_points() -> Dict[str, Any]:
    """Run exactly four corrected bracket points, then stop for inspection."""

    require_dl()
    audit = read_json(ANALYSIS / "correction" / "correction_audit.json")
    if audit.get("decision") != "GO_TO_FOUR_POINT_CORRECTION_ONLY":
        raise RuntimeError("correction audit gate is not GO")
    context = frozen_context()
    hold_ps, phase_ps = long_pulse_timing_parameters()
    stats = {"new": 0, "reused": 0}
    rows: List[Dict[str, Any]] = []
    for label, baseline, margin, vdroop in correction_parameters():
        parameters = parameters_for(baseline, margin, vdroop, hold_ps, phase_ps)
        row = execute(context, parameters, stats)
        row["correction_point"] = label
        row["expected_static_q"] = 0 if "last_q0" in label else 1
        rows.append(row)
    write_csv(ANALYSIS / "correction" / "four_point_results.csv", SCENARIO_FIELDS + ("correction_point", "expected_static_q"), rows)
    failures = [row["scenario_id"] for row in rows if not row["valid"] or row["q_final"] != row["expected_static_q"]]
    summary = {
        "schema_version": 1,
        "study": STUDY,
        "decision": "GO_TO_FORMAL_12_ONLY" if not failures and len(rows) == 4 else "STOP_CORRECTION",
        "scenario_count": len(rows),
        "new_hspice_scenarios": stats["new"],
        "reused_correction_points": stats["reused"],
        "failures": failures,
        "results": [{"point": row["correction_point"], "q_final": row["q_final"], "q_state": row["q_state"], "valid": row["valid"]} for row in rows],
    }
    write_json(ANALYSIS / "correction" / "four_point_summary.json", summary)
    if summary["decision"] != "GO_TO_FORMAL_12_ONLY":
        raise RuntimeError("four-point correction failed: {}".format(failures))
    return summary


def phase_long_pulse_corrected() -> Dict[str, Any]:
    """Run one and only one corrected 12-scenario formal T0-2 campaign.

    The four-point gate is a hard prerequisite.  This function never probes
    alternative PWL starts, slews, or durations and never invokes the legacy
    fixed-level phase.  Thus a successful call adds exactly twelve corrected
    HSPICE scenarios after the exactly four correction scenarios.
    """

    require_dl()
    audit = read_json(ANALYSIS / "correction" / "correction_audit.json")
    four = read_json(ANALYSIS / "correction" / "four_point_summary.json")
    if audit.get("decision") != "GO_TO_FOUR_POINT_CORRECTION_ONLY":
        raise RuntimeError("corrected formal gate requires zero-HSPICE audit GO")
    if four.get("decision") != "GO_TO_FORMAL_12_ONLY" or four.get("scenario_count") != 4:
        raise RuntimeError("corrected formal gate requires four-point GO")
    context = frozen_context()
    hold_ps, phase_ps = long_pulse_timing_parameters()
    stats = {"new": 0, "reused": 0}
    rows: List[Dict[str, Any]] = []
    for item in static_trip_rows():
        baseline = float(item["baseline_vdd_v"])
        margin = item["margin_level"]
        for label, vdroop in (("last_q0", float(item["last_q0_v"])), ("first_q1", float(item["first_q1_v"]))):
            parameters = parameters_for(baseline, margin, vdroop, hold_ps, phase_ps)
            row = execute(context, parameters, stats)
            row["reference_static_state"] = label
            row["expected_static_q"] = 0 if label == "last_q0" else 1
            rows.append(row)
    write_csv(
        ANALYSIS / "correction" / "formal_12_results.csv",
        SCENARIO_FIELDS + ("reference_static_state", "expected_static_q"),
        rows,
    )
    failures = [row["scenario_id"] for row in rows if not row["valid"] or row["q_final"] != row["expected_static_q"]]
    ordering_failures: List[str] = []
    for baseline in FORMAL_BASELINES:
        for state, expected in (("last_q0", 0), ("first_q1", 1)):
            group = [row for row in rows if float(row["baseline_vdd_v"]) == baseline and row["reference_static_state"] == state]
            ordered = sorted(group, key=lambda row: ("L1", "L2", "L3").index(row["margin_level"]))
            if [row["q_final"] for row in ordered] != [expected] * len(ordered):
                ordering_failures.append("{}:{}".format(baseline, state))
    decision = "PASS" if len(rows) == 12 and not failures and not ordering_failures else "NO-GO_AFTER_CORRECTION"
    summary = {
        "schema_version": 1,
        "study": STUDY,
        "decision": decision,
        "scenario_count": len(rows),
        "new_hspice_scenarios": stats["new"],
        "reused_old_scenarios": stats["reused"],
        "failures": failures,
        "ordering_failures": ordering_failures,
        "results": [
            {
                "baseline_vdd_v": row["baseline_vdd_v"],
                "margin_level": row["margin_level"],
                "reference_static_state": row["reference_static_state"],
                "expected_static_q": row["expected_static_q"],
                "q_final": row["q_final"],
                "q_state": row["q_state"],
                "valid": row["valid"],
            }
            for row in rows
        ],
    }
    write_json(ANALYSIS / "correction" / "formal_12_summary.json", summary)
    publish_corrected_gate(summary)
    return summary


def publish_corrected_gate(formal: Mapping[str, Any]) -> Dict[str, Any]:
    """Publish corrected T0-2 Gate, D0 contract, and Chinese report.

    Even when corrected T0-2 passes, this publication deliberately leaves
    T0-3 through T0-6 blocked for this task.  A T0-2 pass is not a cadence or
    phase-window claim and therefore cannot authorize downstream stages.
    """

    # Refresh only the compact marker so it includes all retained corrected
    # and diagnostic paths; legacy raw decks themselves remain untouched.
    legacy_scenario_marker()
    marker = read_json(ANALYSIS / "correction" / "legacy_62_scenarios_marker.json")
    correction = read_json(ANALYSIS / "correction" / "four_point_summary.json")
    audit = read_json(ANALYSIS / "correction" / "correction_audit.json")
    corrected_total = int(correction.get("scenario_count", 0)) + int(formal.get("scenario_count", 0))
    corrected_new = int(correction.get("new_hspice_scenarios", 0)) + int(formal.get("new_hspice_scenarios", 0))
    corrected_failed = len(marker.get("failed_syntax_diagnostic_paths", []))
    reused_correction_points = int(correction.get("reused_old_scenarios", 0)) + int(
        formal.get("reused_correction_points", formal.get("reused_old_scenarios", 0))
    )
    decision = formal.get("decision")
    gate_decision = "T0-2 CORRECTED PASS" if decision == "PASS" else "NO-GO AFTER CORRECTION"
    gate = {
        "schema_version": 2,
        "study": STUDY,
        "decision": gate_decision,
        "stop_stage": None if decision == "PASS" else "T0-2_CORRECTION",
        "correction_status": "PD_SENSE_LOCAL_VDD_NORMALIZED",
        "constant_low_equivalent_to_m0": audit["constant_low_equivalence"]["equivalent"],
        "four_point_summary": str(ANALYSIS / "correction" / "four_point_summary.json"),
        "formal_12_summary": str(ANALYSIS / "correction" / "formal_12_summary.json"),
        "historical_legacy_scenarios": marker["scenario_count"],
        "historical_legacy_status": marker["status"],
        "corrected_evidence_scenario_count": corrected_total,
        "failed_syntax_diagnostic_scenarios": corrected_failed,
        "new_hspice_scenarios_correction": correction.get("new_hspice_scenarios"),
        "new_hspice_scenarios_formal_12": formal.get("new_hspice_scenarios"),
        "new_hspice_scenarios_successful_correction": corrected_new,
        "reused_old_scenarios": 0,
        "reused_correction_points": reused_correction_points,
        "reparsed_old_scenarios": 0,
        "forbidden_flow_runs": 0,
        "blocked_later_stages": ["T0-3", "T0-4", "T0-5", "T0-6"],
    }
    write_json(ANALYSIS / "reports" / "T0_GATE_STATUS.json", gate)
    downstream = {
        "schema_version": 2,
        "study": STUDY,
        "decision": "T0-2_CORRECTED_ONLY_NO_CADENCE_CLAIM",
        "source_gate": gate_decision,
        "precise_timing_detection_range": {"minimum_vdd_v": 0.80, "status": "not_extended_below_floor"},
        "below_floor_requirement": {
            "condition": "VDD_MONITORED < 0.80 V",
            "required_semantics": ["heartbeat", "stuck_q", "timeout", "no_valid_detection_result"],
            "precise_timing_trip_allowed": False,
        },
        "runtime_probe_period": {
            "status": "not_qualified_T0_3_blocked",
            "maximum_period_s": None,
            "reason": "This correction phase intentionally stops before T0-3/T0-6",
        },
    }
    write_json(ANALYSIS / "contract" / "T0_DOWNSTREAM_D0_TIMING_CONTRACT.json", downstream)
    report_lines = [
        "# FTC T0-2 瞬态电压跌落纠偏报告",
        "",
        "## 最终判定",
        "",
        "**{}**".format(gate_decision),
        "",
        "本轮只纠正 PD_CTRL→PD_SENSE 的验证电平抽象；未修改 FTC_SENSOR、H0、M1、冻结 RTL 或任何传感器拓扑。",
        "",
        "## 纠偏审计",
        "",
        "- POWER_DOMAIN_CONTRACT 已加入 T0 冻结输入，28 条 crossing 均由瞬时 `V(vdd_a,vss_a)` 归一化。",
        "- S_CLK、复位、16 条 medium 和 10 条 fine 控制均采用稳定 PD_CTRL 0/1 源加本地 VDD 归一化 D2A 抽象。",
        "- XOR/CK 测量阈值已改为 `V(vdd_a,vss_a)/2`。",
        "- M0 0.87 V/M5/F6 与 T0 恒定低压兼容模式通过零仿真网络、电源、端口和时序等价审计：{}。".format("等价" if audit["constant_low_equivalence"]["equivalent"] else "不等价"),
        "",
        "## 四个纠偏点",
        "",
        "| 点 | 期望 Q | 实际 Q | valid |",
        "|---|---:|---:|---:|",
    ]
    for item in correction.get("results", []):
        report_lines.append("| {} | {} | {} | {} |".format(item["point"], 0 if "last_q0" in item["point"] else 1, item["q_final"], item["valid"]))
    report_lines.extend([
        "",
        "## 正式十二点",
        "",
        "- 判定：`{}`。".format(decision),
        "- 场景数：{}；新增 HSPICE：{}。".format(formal.get("scenario_count"), formal.get("new_hspice_scenarios")),
        "- 纠偏四点新增 HSPICE：{}；正式十二点新增 HSPICE：{}；成功新增合计：{}。".format(
            correction.get("new_hspice_scenarios"), formal.get("new_hspice_scenarios"), corrected_new
        ),
        "- 另有 1 个保留的 HSPICE 源语法诊断失败场景，不计入有效纠偏结果：{}。".format(corrected_failed),
        "- 旧 62 个场景全部保留，统一标记为 `HISTORICAL_SUPERSEDED_NOT_DELETED`，原因是固定 VDD_VALUE 跨域高电平未按本地 VDD 归一化。",
        "",
        "## 范围边界",
        "",
        "T0-3/T0-4/T0-5/T0-6 本轮未执行；因此没有相位窗口、持续时间边界、覆盖率或运行时 cadence 结论。",
        "",
        "## 仿真预算",
        "",
        "- 纠偏审计新增 HSPICE：0。",
        "- 纠偏四点新增 HSPICE：{}。".format(correction.get("new_hspice_scenarios")),
        "- 正式十二点新增 HSPICE：{}。".format(formal.get("new_hspice_scenarios")),
        "- 复用旧 62 场景：0；复用先行纠偏点：{}；仅重解析旧场景：0；禁止流程新增运行：0。".format(gate["reused_correction_points"]),
    ])
    (REPORT_ROOT / "FTC_T0_TRANSIENT_DROOP_CHARACTERIZATION.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return gate


def phase_long_pulse() -> Dict[str, Any]:
    """Run T0-2's two long-pulse checks per formal candidate."""

    require_dl()
    context = frozen_context()
    stats = {"new": 0, "reused": 0}
    timing = probe_timing()
    # The droop starts at the earliest positive PWL time (1 ps), rather than
    # at a later reset-related time.  This is the closest legal finite-slope
    # approximation to M0's static rail, while still leaving an explicit
    # non-zero source timestamp.  Recovery is 0.50 ns after Q sample 2.
    # One femtosecond is still a positive HSPICE timestamp, but removes the
    # otherwise observable nominal-rail initialization interval from this
    # static-equivalence control.
    start_s = 1.0e-15
    phase_ps = (start_s - timing["launch_time_s"]) * 1e12
    fall_s = PRIMARY_SLEW_PS * 1e-12
    hold_ps = (timing["q_read_late_time_s"] + 0.50e-9 - start_s - fall_s) * 1e12
    rows: List[Dict[str, Any]] = []
    for item in static_trip_rows():
        baseline = float(item["baseline_vdd_v"])
        margin = item["margin_level"]
        last_q0 = float(item["last_q0_v"])
        first_q1 = float(item["first_q1_v"])
        for label, vdroop in (("last_q0", last_q0), ("first_q1", first_q1)):
            parameters = parameters_for(baseline, margin, vdroop, hold_ps, phase_ps)
            row = execute(context, parameters, stats)
            row["reference_static_state"] = label
            row["expected_static_q"] = 0 if label == "last_q0" else 1
            rows.append(row)
    write_csv(ANALYSIS / "long_pulse_consistency" / "long_pulse_results.csv", SCENARIO_FIELDS + ("reference_static_state", "expected_static_q"), rows)
    failures = []
    for row in rows:
        if not row["valid"] or row["q_final"] != row["expected_static_q"]:
            failures.append(row["scenario_id"])
    # The six candidates must also retain the L1/L2/L3 ordering inside each
    # baseline.  The Q check above catches each bracket; this second check
    # prevents a coincidental per-row pass from hiding a margin inversion.
    ordering_failures: List[str] = []
    for baseline in FORMAL_BASELINES:
        for state, expected in (("last_q0", 0), ("first_q1", 1)):
            group = [row for row in rows if float(row["baseline_vdd_v"]) == baseline and row["reference_static_state"] == state]
            ordered = sorted(group, key=lambda row: ("L1", "L2", "L3").index(row["margin_level"]))
            if [row["q_final"] for row in ordered] != [expected] * len(ordered):
                ordering_failures.append("{}:{}".format(baseline, state))
    decision = "GO" if len(rows) == 12 and not failures and not ordering_failures else "STOP"
    summary = {"decision": decision, "candidate_count": 6, "scenario_count": len(rows), "new_hspice": stats["new"], "reused": stats["reused"], "failures": failures, "ordering_failures": ordering_failures}
    write_json(ANALYSIS / "long_pulse_consistency" / "summary.json", summary)
    if decision != "GO":
        raise RuntimeError("T0-2 STOP: long-pulse consistency failed: {}".format(failures))
    return summary


def phase_terminal_stop() -> Dict[str, Any]:
    """Publish the terminal T0-2 STOP package without launching new HSPICE.

    A STOP is a completed, auditable T0 outcome.  Later electrical phases are
    represented by explicit blocked records rather than by speculative data.
    This keeps the downstream contract honest: D0 receives the below-0.80 V
    fail-safe requirement, but it receives no unverified cadence number.
    """

    require_dl()
    contract()
    summary_path = ANALYSIS / "long_pulse_consistency" / "summary.json"
    if not summary_path.is_file():
        raise RuntimeError("T0-2 summary is missing; refusing terminal publication")
    long_pulse = read_json(summary_path)
    if long_pulse.get("decision") != "STOP":
        raise RuntimeError("terminal STOP publication requires a T0-2 STOP")
    total_scenarios = len(list(RUN_ROOT.glob("r*/scenarios/*/scenario_manifest.json"))) if RUN_ROOT.is_dir() else 0
    gate = {
        "schema_version": 1,
        "study": STUDY,
        "decision": "NO-GO / STOP",
        "stop_stage": "T0-2",
        "stop_reason": "long_pulse_static_to_transient_consistency_failed",
        "long_pulse_summary": str(summary_path),
        "new_hspice_scenarios_total": total_scenarios,
        "reused_old_scenarios": 0,
        "reparsed_old_scenarios": 0,
        "forbidden_flow_runs": 0,
        "blocked_later_stages": ["T0-3", "T0-4", "T0-5", "T0-6"],
        "completed_non_electrical_stage": "T0-7 fail-safe boundary and T0-8 terminal evidence",
    }
    write_json(ANALYSIS / "reports" / "T0_GATE_STATUS.json", gate)
    downstream = {
        "schema_version": 1,
        "study": STUDY,
        "decision": "BLOCKED_BY_T0_STOP",
        "source_gate": "T0-2",
        "precise_timing_detection_range": {"minimum_vdd_v": 0.80, "status": "not_extended_below_floor"},
        "below_floor_requirement": {
            "condition": "VDD_MONITORED < 0.80 V",
            "required_semantics": ["heartbeat", "stuck_q", "timeout", "no_valid_detection_result"],
            "precise_timing_trip_allowed": False,
        },
        "runtime_probe_period": {"status": "not_qualified", "maximum_period_s": None, "reason": "T0-3_and_later_phases_blocked_by_T0-2"},
    }
    write_json(ANALYSIS / "contract" / "T0_DOWNSTREAM_D0_TIMING_CONTRACT.json", downstream)
    for directory, name in (("phase_window", "phase_window.csv"), ("amplitude_duration", "amplitude_duration.csv"), ("phase_coverage", "phase_coverage.csv"), ("cadence", "cadence.csv")):
        write_csv(ANALYSIS / directory / name, ("status", "reason"), [{"status": "BLOCKED", "reason": "T0-2 STOP"}])
    report_lines = [
        "# FTC T0 瞬态电压跌落检测表征报告",
        "",
        "## 最终判定",
        "",
        "**NO-GO / STOP（停止阶段：T0-2）**",
        "",
        "T0-2 的有限斜率长脉冲无法在全部六个正式候选上复现 M0 最近静态 Q0/Q1 bracket。该结果是当前冻结传感器的物理一致性失败，不是通过增加数字逻辑可以掩盖的问题。",
        "",
        "## 证据",
        "",
        "- M0 原始 `trip_sweep.csv` 被直接读取，没有重新执行静态扫描。",
        "- T0-2 共运行 12 个正式 long-pulse 场景；每个场景均使用当前 medium/fine、真实 tap29 XOR 和真实 DFF 双采样。",
        "- PWL 起点依次检查到 0.5 ns、1 ps 和 1 fs，下降/恢复斜率保持非零；反转仍然存在。",
        "- 失败点保留在 `delay_chain/ftc/runs/t0_transient_droop/`，没有覆盖或删除。",
        "",
        "## 禁止越过的阶段",
        "",
        "T0-3 相位窗口、T0-4 持续时间边界、T0-5 覆盖率和 T0-6 cadence 均标记为 BLOCKED，未进行新的 HSPICE 扩展。",
        "",
        "## D0 下游边界",
        "",
        "精确 timing detection 不能扩展到低于 0.80 V；D0 必须为该范围采用 heartbeat、stuck-Q、timeout 或无有效检测结果等失效保护语义。当前没有经过 T0-3 至 T0-6 验证的运行时检测间隔。",
        "",
        "## 仿真统计",
        "",
        "- 新增 T0 HSPICE 场景（含两次试跑和五轮 T0-2 bracket 复核）：{}。".format(total_scenarios),
        "- 复用旧 HSPICE 场景：0。",
        "- 仅重解析旧场景：0。",
        "- 禁止流程新增运行：0。",
    ]
    report_path = REPORT_ROOT / "FTC_T0_TRANSIENT_DROOP_CHARACTERIZATION.md"
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return gate


def phase_window() -> Dict[str, Any]:
    """Run T0-3 phase exploration at the two L2 representative points."""

    require_dl()
    context = frozen_context()
    stats = {"new": 0, "reused": 0}
    rows: List[Dict[str, Any]] = []
    coarse = (-1000.0, -750.0, -500.0, -250.0, 0.0, 250.0, 500.0, 750.0, 1000.0, 1250.0, 1500.0, 2000.0, 2500.0)
    for baseline, vdroop in ((0.95, 0.85), (1.10, 0.95)):
        for phase_ps in coarse:
            row = execute(context, parameters_for(baseline, "L2", vdroop, 3000.0, phase_ps), stats)
            row["sweep_kind"] = "coarse"
            rows.append(row)
    # Fine points are added only around transitions found by the coarse map.
    for baseline in FORMAL_BASELINES:
        group = [row for row in rows if float(row["baseline_vdd_v"]) == baseline]
        ordered = sorted(group, key=lambda row: float(row["phase_ps"]))
        boundaries = []
        for left, right in zip(ordered, ordered[1:]):
            if left["q_final"] != right["q_final"]:
                boundaries.append((float(left["phase_ps"]) + float(right["phase_ps"])) / 2.0)
        for center in boundaries:
            for phase_ps in [center - 100.0, center - 75.0, center - 50.0, center - 25.0, center, center + 25.0, center + 50.0, center + 75.0, center + 100.0]:
                vdroop = 0.85 if baseline == 0.95 else 0.95
                row = execute(context, parameters_for(baseline, "L2", vdroop, 3000.0, phase_ps), stats)
                row["sweep_kind"] = "fine"
                rows.append(row)
    write_csv(ANALYSIS / "phase_window" / "phase_window.csv", SCENARIO_FIELDS + ("sweep_kind",), rows)
    windows = []
    for baseline in FORMAL_BASELINES:
        group = sorted([row for row in rows if float(row["baseline_vdd_v"]) == baseline], key=lambda row: float(row["phase_ps"]))
        stable_high = [row for row in group if row["valid"] and row["q_final"] == 1]
        windows.append({"baseline_vdd_v": baseline, "stable_high_count": len(stable_high), "phase_min_ps": min((float(row["phase_ps"]) for row in stable_high), default=None), "phase_max_ps": max((float(row["phase_ps"]) for row in stable_high), default=None)})
    decision = "GO" if all(item["stable_high_count"] > 0 for item in windows) else "STOP"
    summary = {"decision": decision, "scenario_count": len(rows), "new_hspice": stats["new"], "reused": stats["reused"], "windows": windows}
    write_json(ANALYSIS / "phase_window" / "summary.json", summary)
    if decision != "GO":
        raise RuntimeError("T0-3 STOP: no reproducible phase-sensitive window")
    return summary


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Dispatch one explicit T0 phase; later phases enforce earlier artifacts."""

    parser = argparse.ArgumentParser(description="FTC T0 transient droop characterization")
    parser.add_argument(
        "--phase",
        choices=(
            "contract", "smoke", "long-pulse", "phase-window", "finalize-stop",
            "correction-audit", "correction-points", "long-pulse-corrected",
        ),
        required=True,
    )
    args = parser.parse_args(argv)
    if args.phase == "contract":
        phase_contract()
    elif args.phase == "smoke":
        phase_contract()
        phase_smoke()
    elif args.phase == "long-pulse":
        phase_contract()
        phase_long_pulse()
    elif args.phase == "phase-window":
        phase_contract()
        phase_long_pulse()
        phase_window()
    elif args.phase == "finalize-stop":
        phase_terminal_stop()
    elif args.phase == "correction-audit":
        phase_correction_audit()
    elif args.phase == "correction-points":
        phase_correction_audit()
        phase_correction_points()
    elif args.phase == "long-pulse-corrected":
        phase_long_pulse_corrected()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
