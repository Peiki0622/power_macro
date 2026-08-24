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
    """Load and validate the immutable T0-0 threat contract."""

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
    return data


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
    """Bind every T0 result to the runner and immutable contract bytes."""

    digest = hashlib.sha256()
    for path in (Path(__file__), CONTRACT_PATH):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def probe_timing() -> Dict[str, float]:
    """Return M0's exact one-probe event times, without redefining them."""

    return m0.probe_timing()


def thermometer_constant_points(units: int, code: int, high_when_set: bool, stop: float) -> Iterable[Tuple[int, str]]:
    """Generate fixed M/F rails using the validated M0 thermometer polarity."""

    for index, bit in enumerate(physical.thermometer(units, code)):
        high = bool(bit) if high_when_set else not bool(bit)
        value = "'VDD_VALUE'" if high else "0"
        yield index, "PWL(0 {} {} {})".format(value, spice(stop), value)


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
    sclk = physical.pwl([
        (0.0, 0), (timing["launch_time_s"] - m0.SCLK_EDGE_S, 0),
        (timing["launch_time_s"], "'VDD_VALUE'"),
        (timing["sclk_fall_s"], "'VDD_VALUE'"),
        (timing["sclk_fall_s"] + m0.SCLK_EDGE_S, 0), (stop, 0),
    ])
    reset = physical.pwl([
        (0.0, "'VDD_VALUE'"), (timing["reset_release_s"] - m0.CONTROL_EDGE_S, "'VDD_VALUE'"),
        (timing["reset_release_s"], "'VDD_VALUE'"),
        (timing["reset_release_s"] + m0.CONTROL_EDGE_S, 0),
        (timing["reset_assert_start_s"], 0),
        (timing["reset_assert_end_s"], "'VDD_VALUE'"), (stop, "'VDD_VALUE'"),
    ])
    supply_pwl = physical.pwl(supply)
    lines: List[str] = [
        "* FTC T0: current M0 real-cell single-probe transient droop deck.",
        "* VDD_MONITORED is the only new physical variable; no detector RTL or ideal delay is present.",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(physical.spice(float(config["temperature_c"]))),
        *includes,
        '.lib "{}" {}'.format(config["model_library"], config["corner"]),
        ".param VDD_VALUE={}".format(physical.spice(baseline)),
        "V_VDD vdd_a vss_a {}".format(supply_pwl),
        "V_VSS vss_a 0 0",
        "V_SCLK s_clk vss_a {}".format(sclk),
        "V_DFF_RESET dff_reset vss_a {}".format(reset),
        *physical.sensor_xor_lines(cells),
    ]
    for bit, points in thermometer_constant_points(physical.MEDIUM_N, medium_code, True, stop):
        lines.append("V_M_{:02d} m_{} vss_a {}".format(bit, bit, points))
    for index in range(physical.MEDIUM_N + 1):
        source = "xor_29" if index == 0 else "x{}".format(index)
        lines.append(physical.buffer_instance("XMED_BUF_{:02d}".format(index), "x{}".format(index + 1), source, physical.MEDIUM_DELAY_CELL))
    for index in range(physical.MEDIUM_N):
        output = "medium_out" if index == 0 else "my{}".format(index)
        deep = "x{}".format(physical.MEDIUM_N + 1) if index == physical.MEDIUM_N - 1 else "my{}".format(index + 1)
        lines.append(physical.mux_instance("XMED_MUX_{:02d}".format(index), output, "x{}".format(index + 1), deep, "m_{}".format(index)))
    lines.append(physical.buffer_instance("XFINE_DRIVER", "dff_ck", "medium_out", physical.FINE_DRIVER))
    for bit, points in thermometer_constant_points(physical.FINE_K, fine_code, False, stop):
        lines.append("V_F_{:02d} f_{} vss_a {}".format(bit, bit, points))
        lines.append("XLOAD_{:02d} z_{} vdd_a vdd_a vss_a vss_a dff_ck f_{} {}".format(bit, bit, bit, physical.FINE_LOAD))
    lines.extend([
        "XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset {}".format(physical.DFF_CELL),
        ".tran {} {}".format(physical.spice(float(config["tran_max_step_s"])), physical.spice(stop)),
        ".measure tran t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD={}".format(physical.spice(timing["launch_time_s"])),
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
        "finite_vdd_pwl": source.startswith("V_VDD vdd_a vss_a PWL(") and source.count(" ") >= 8,
        "pwl_no_zero_slope": float(parameters["t_fall_ps"]) > 0 and float(parameters["t_rise_ps"]) > 0,
        "requested_codes_legal": 0 <= int(parameters["M_det"]) <= physical.MEDIUM_N and 0 <= int(parameters["F_det"]) <= physical.FINE_K,
        "no_forbidden_hardware": not any(token in active for token in forbidden),
        "no_ideal_delay_or_capacitor": not re.search(r"(?im)^\s*[evg]\S*.*\btd\s*=", active) and not any(line.lstrip().lower().startswith("c") for line in active.splitlines()),
    }


def parameters_for(baseline: float, margin: str, vdroop: float, hold_ps: float, phase_ps: float, slew_ps: float = PRIMARY_SLEW_PS) -> Dict[str, Any]:
    """Build one immutable electrical identity from the frozen codebook."""

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
        "implementation_git_head": data["implementation_git_head"],
        "plan_input_baseline": data["plan_input_baseline"],
        "contract_sha256": sha256_file(CONTRACT_PATH),
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
    parser.add_argument("--phase", choices=("contract", "smoke", "long-pulse", "phase-window", "finalize-stop"), required=True)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
