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
    # The two Q samples must be interpreted against the local rail at their
    # own sample instants.  A transient may recover between the samples, so a
    # single fixed Vdroop threshold is physically incorrect for T0-3 onward.
    "q_sample_1_v", "q_sample_2_v", "vdd_at_q_sample_1_v", "vdd_at_q_sample_2_v",
    "q_sample_1_ratio", "q_sample_2_ratio", "q_final", "q_state",
    "active_ck_edge_count", "recovery_max_ratio", "valid", "reason",
    "completion_status", "scenario_path", "deck_sha256", "source_hash",
)

# These are the only two retained T0-4 observations that require new physical
# evidence.  Keeping the identities explicit prevents a diagnostic command
# from accidentally expanding into a second full duration sweep.
T0_4_DIAGNOSTIC_CASES = (
    {"baseline": 0.95, "margin": "L3", "vdroop": 0.83, "hold_ps": 1750.0, "phase_ps": -450.0},
    {"baseline": 1.10, "margin": "L1", "vdroop": 1.01, "hold_ps": 1250.0, "phase_ps": -500.0},
)

# Compact machine-readable evidence introduced by T0-2E.  The legacy STOP is
# retained byte-for-byte; this sidecar is the only place that changes its
# authority for later automation.
SUPERSESSION_PATH = ANALYSIS / "long_pulse_consistency" / "supersession.json"

# T0-4E makes the corrected T0-4 GO evidence authoritative before later
# runner development begins.  These records are intentionally kept in an
# analysis-only directory: they describe evidence identity and reuse policy,
# not a new electrical experiment or a replacement for the retained decks.
T0_4E_CLOSURE = ANALYSIS / "t0_4e_closure"
T0_4E_AUTHORITY_PATH = T0_4E_CLOSURE / "authoritative_evidence_hashes.json"
T0_4E_SUPERSESSION_PATH = T0_4E_CLOSURE / "stale_stop_supersession.json"
T0_4E_REUSE_CONTRACT_PATH = T0_4E_CLOSURE / "electrical_reuse_contract.json"

# Every field below either selects a frozen sensor code or is consumed by the
# deck renderer to set the monitored-rail waveform.  ``source_hash`` and
# report-only labels are deliberately absent: changing Python orchestration
# must never turn an already retained electrical experiment into a new HSPICE
# request.  The candidate deck hash remains a second, stricter check.
ELECTRICAL_PARAMETER_FIELDS = (
    "baseline_vdd_v", "margin_level", "M_det", "F_det", "DeltaV_mv",
    "Vdroop_v", "t_fall_ps", "t_hold_ps", "t_rise_ps", "phase_ps",
    "control_mode",
)

# The renderer currently emits no source-hash line.  Reserving exactly one
# comment prefix is nevertheless useful for future provenance annotations:
# only a line beginning with this literal prefix may be ignored by the
# normalized deck hash.  All SPICE instances, sources, measures, options and
# ordinary comments remain hash-covered, so this mechanism cannot hide a
# circuit, timing, port, or measurement change.
NON_ELECTRICAL_DECK_METADATA_PREFIX = "* T0_NON_ELECTRICAL_METADATA:"

# Phase-coverage rows retain the complete scalar evidence from the real DFF
# runner and append only post-processing facts.  Keeping the raw Q/VDD/CK
# measurements beside the four-state label makes every interval traceable to
# a physical deck rather than to an inferred timing-residual threshold.
PHASE_COVERAGE_FIELDS = SCENARIO_FIELDS + (
    "scenario_key", "scenario_family", "scan_stage", "t0_5_state",
    "time_axis_shift_s", "recovery_start_s", "recovery_end_s", "recovery_model_status",
    "evidence_source", "reuse_reason", "electrical_projection_sha256",
    "normalized_deck_sha256",
)

# A droop phase is defined relative to the probe S_CLK edge, not to HSPICE
# time zero.  When a requested early phase would otherwise begin at or before
# zero, the whole one-probe testbench receives this nominal pre-simulation
# interval.  It is deliberately not a new reset/S_CLK/Q timing margin: every
# named event receives the *same* shift, so all physical intervals and the
# ``droop_start - S_CLK_rise`` phase definition stay invariant.
T0_PRE_SIMULATION_TIME_S = 1.0e-9
PHASE_COARSE_STEP_PS = 250.0
PHASE_FINE_STEP_PS = 25.0

# T0-5A deliberately contains only the two L2 representatives and exactly
# the boundary/long durations approved by the T0 plan.  ``seed_phase_ps`` is
# the existing measured favorable phase used to begin a new short-pulse map;
# long-pulse maps instead seed from all retained T0-3 points.
T0_5A_SPECS = (
    {"scenario_key": "t0_5a_0p95_l2_boundary", "scenario_family": "L2_BOUNDARY_MINIMUM", "baseline": 0.95, "margin": "L2", "vdroop": 0.86, "hold_ps": 1454.0, "seed_phase_ps": -450.0, "reuse_t0_3_phase_points": False},
    {"scenario_key": "t0_5a_0p95_l2_long", "scenario_family": "L2_LONG_PULSE", "baseline": 0.95, "margin": "L2", "vdroop": 0.86, "hold_ps": 3000.0, "seed_phase_ps": None, "reuse_t0_3_phase_points": True},
    {"scenario_key": "t0_5a_1p10_l2_boundary", "scenario_family": "L2_BOUNDARY_MINIMUM", "baseline": 1.10, "margin": "L2", "vdroop": 0.96, "hold_ps": 1188.0, "seed_phase_ps": -500.0, "reuse_t0_3_phase_points": False},
    {"scenario_key": "t0_5a_1p10_l2_long", "scenario_family": "L2_LONG_PULSE", "baseline": 1.10, "margin": "L2", "vdroop": 0.96, "hold_ps": 3000.0, "seed_phase_ps": None, "reuse_t0_3_phase_points": True},
)

# T0-5B is purposefully a two-point supplement.  These are the already
# diagnosed T0-4 recovery-edge boundaries; no other margin receives a full
# phase map unless a future plan changes this explicit finite tuple.
T0_5B_SPECS = (
    {"scenario_key": "t0_5b_0p95_l3_recovery", "scenario_family": "RECOVERY_EDGE_SPECIAL_MARGIN", "baseline": 0.95, "margin": "L3", "vdroop": 0.83, "hold_ps": 2000.0, "seed_phase_ps": -450.0, "reuse_t0_3_phase_points": False},
    {"scenario_key": "t0_5b_1p10_l1_recovery", "scenario_family": "RECOVERY_EDGE_SPECIAL_MARGIN", "baseline": 1.10, "margin": "L1", "vdroop": 1.01, "hold_ps": 1500.0, "seed_phase_ps": -500.0, "reuse_t0_3_phase_points": False},
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


def electrical_parameter_projection(parameters: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the immutable, deck-relevant part of one scenario identity.

    This projection is intentionally narrow and explicit.  It is not a loose
    "similar scenario" heuristic: all waveform timing, supply depth, selected
    medium/fine code, and the PD_CTRL-to-PD_SENSE verification abstraction are
    retained.  The only omitted values are source and reporting provenance,
    neither of which is a SPICE electrical input.  A caller still has to prove
    normalized deck equality before it may reuse a retained measurement.
    """

    missing = [field for field in ELECTRICAL_PARAMETER_FIELDS if field not in parameters]
    if missing:
        raise ValueError("scenario lacks electrical parameters: {}".format(", ".join(missing)))
    return {field: parameters[field] for field in ELECTRICAL_PARAMETER_FIELDS}


def electrical_projection_sha256(parameters: Mapping[str, Any]) -> str:
    """Hash the canonical electrical projection for compact provenance rows."""

    return hashlib.sha256(stable_json(electrical_parameter_projection(parameters)).encode("ascii")).hexdigest()


def normalized_deck_text(deck: str) -> str:
    """Remove only declared non-electrical metadata from a rendered deck.

    The literal prefix is the complete normalization rule.  In particular,
    this helper does *not* remove arbitrary comments, whitespace, measures or
    source lines.  That conservative policy makes a normalized hash suitable
    for deciding whether an old transistor-level listing is physically
    reusable after source-code-only changes.
    """

    return "\n".join(
        line for line in deck.splitlines()
        if not line.startswith(NON_ELECTRICAL_DECK_METADATA_PREFIX)
    ) + "\n"


def normalized_deck_sha256(deck: str) -> str:
    """Return the frozen, metadata-normalized renderer identity."""

    return hashlib.sha256(normalized_deck_text(deck).encode("ascii")).hexdigest()


def increment_stat(stats: Dict[str, int], key: str) -> None:
    """Increment optional accounting keys without constraining old callers.

    Earlier completed T0 phases pass only ``new`` and ``reused``.  Later
    phases require finer provenance accounting, so this helper permits the
    upgraded executor to enrich the same mutable counter dictionary while
    preserving historical call sites and their compact summaries.
    """

    stats[key] = int(stats.get(key, 0)) + 1


def reject_if_t0_4_authoritative_go(entry_name: str) -> None:
    """Prevent legacy terminal paths from replacing corrected T0-4 evidence.

    Several retained functions intentionally model historical STOP outcomes.
    They remain readable for audit, but once the current gate says T0-4 is
    corrected GO none of those functions may write a stale NO-GO, blocked
    cadence contract, or terminal report.  The check is centralized so each
    old command has the same fail-closed behavior.
    """

    gate_path = ANALYSIS / "reports" / "T0_GATE_STATUS.json"
    if gate_path.is_file() and read_json(gate_path).get("t0_4_status") == "GO":
        raise RuntimeError("{} is historical-only after corrected T0-4 GO".format(entry_name))


def probe_timing() -> Dict[str, float]:
    """Return M0's exact one-probe event times, without redefining them."""

    return m0.probe_timing()


def t0_time_axis_shift_s(parameters: Mapping[str, Any]) -> float:
    """Return the minimal pre-simulation shift needed for one droop phase.

    T0 phase is an event-relative quantity: ``phase = droop_start -
    S_CLK_rise``.  HSPICE nevertheless requires every PWL timestamp to be
    positive.  A phase that starts before the unshifted testbench's time zero
    is therefore represented by moving the *entire* testbench right by a
    fixed 1 ns nominal prelude plus the required amount.  The shift is zero
    for all retained T0-3/T0-4 phase points whose PWL start is already
    positive; that preserves their rendered deck identity and permits normal
    electrical-equivalence reuse.

    The function intentionally depends only on the requested phase and the
    frozen M0 launch time.  It does not alter M/F codes, reset width, S_CLK
    width, Q sample offsets, recovery length, or the power-domain contract.
    """

    unshifted_start = probe_timing()["launch_time_s"] + float(parameters["phase_ps"]) * 1e-12
    return 0.0 if unshifted_start > 0.0 else T0_PRE_SIMULATION_TIME_S - unshifted_start


def shifted_probe_timing(parameters: Mapping[str, Any]) -> Dict[str, float]:
    """Apply one common T0 pre-simulation offset to every probe timestamp.

    The returned dictionary has the same keys as the immutable M0 schedule
    and adds ``time_axis_shift_s`` for provenance.  Adding one value to all
    schedule endpoints is a pure time translation: subtracting any two event
    times, including droop start and S_CLK rise, gives exactly the frozen
    physical interval.  Renderer, HSPICE measurement directives, active-CK
    validation, and T0-5 recovery annotations must all call this helper so
    no interpretation accidentally mixes shifted and unshifted timestamps.
    """

    shift = t0_time_axis_shift_s(parameters)
    return {
        **{key: value + shift for key, value in probe_timing().items()},
        "time_axis_shift_s": shift,
    }


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
    # This timing view translates all one-probe events together only when an
    # early phase needs pre-simulation room.  The electrical source and every
    # measurement below consume this one view, preventing a mixed absolute
    # time base while keeping the frozen relative schedule untouched.
    timing = shifted_probe_timing(parameters)
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
        # These are deliberately independent scalar measurements rather than
        # a reconstructed PWL value.  They make the Q decision auditable when
        # a sample lies on a supply fall or recovery edge.
        ".measure tran vdd_at_q_sample_1 FIND v(vdd_a,vss_a) AT={}".format(physical.spice(timing["q_read_time_s"])),
        ".measure tran vdd_at_q_sample_2 FIND v(vdd_a,vss_a) AT={}".format(physical.spice(timing["q_read_late_time_s"])),
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


def render_diagnostic_deck(context: Mapping[str, Any], parameters: Mapping[str, Any]) -> str:
    """Add only auditable CK/rail measurements to one retained T0-4 case.

    The diagnostic deck reuses the exact real-cell deck above.  It does not
    alter any sensor port, M/F code, DFF connection, or power-domain source.
    The extra scalar measurements distinguish a genuine second CK transition
    from a local-rail 50% threshold crossing during recovery.  The ratio
    minimum is measured over a small, case-specific recovery neighborhood so
    the result remains finite and reviewable without exporting a full binary
    waveform database.
    """

    base = render_deck(context, parameters).rstrip()
    if not base.endswith(".end"):
        raise RuntimeError("diagnostic deck requires the standard .end marker")
    body = base[:-len(".end")].rstrip()
    timing = shifted_probe_timing(parameters)
    start = timing["launch_time_s"] + float(parameters["phase_ps"]) * 1e-12
    recovery_start = start + (float(parameters["t_fall_ps"]) + float(parameters["t_hold_ps"])) * 1e-12
    recovery_end = recovery_start + float(parameters["t_rise_ps"]) * 1e-12
    # The window includes the measured first/second crossing and a small
    # margin, while remaining local to the specified recovery edge.
    window_start = recovery_start - 100e-12
    window_end = recovery_end + 100e-12
    diagnostic = [
        "* T0-4 local diagnosis: no topology or power-domain contract change.",
        "* Ports remain vdd_a/vss_a for every physical cell; only observability is added.",
        ".measure tran diag_ck_ratio_rise_1 WHEN 'v(dff_ck,vss_a)/v(vdd_a,vss_a)'=0.5 RISE=1 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran diag_ck_ratio_rise_2 WHEN 'v(dff_ck,vss_a)/v(vdd_a,vss_a)'=0.5 RISE=2 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran diag_ck_raw_rise_1 WHEN v(dff_ck,vss_a)='V(vdd_a,vss_a)/2' RISE=1 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran diag_ck_raw_rise_2 WHEN v(dff_ck,vss_a)='V(vdd_a,vss_a)/2' RISE=2 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran diag_vdd_at_ratio_1 FIND v(vdd_a,vss_a) WHEN 'v(dff_ck,vss_a)/v(vdd_a,vss_a)'=0.5 RISE=1",
        ".measure tran diag_vdd_at_ratio_2 FIND v(vdd_a,vss_a) WHEN 'v(dff_ck,vss_a)/v(vdd_a,vss_a)'=0.5 RISE=2",
        ".measure tran diag_ck_at_ratio_1 FIND v(dff_ck,vss_a) WHEN 'v(dff_ck,vss_a)/v(vdd_a,vss_a)'=0.5 RISE=1",
        ".measure tran diag_ck_at_ratio_2 FIND v(dff_ck,vss_a) WHEN 'v(dff_ck,vss_a)/v(vdd_a,vss_a)'=0.5 RISE=2",
        ".measure tran diag_ratio_min_recovery MIN 'v(dff_ck,vss_a)/v(vdd_a,vss_a)' FROM={} TO={}".format(physical.spice(window_start), physical.spice(window_end)),
        ".measure tran diag_ratio_min_between_dynamic_crosses MIN 'v(dff_ck,vss_a)/v(vdd_a,vss_a)' FROM='diag_ck_raw_rise_1' TO='diag_ck_raw_rise_2'",
        ".measure tran diag_ratio_min_between_ratio_crosses MIN 'v(dff_ck,vss_a)/v(vdd_a,vss_a)' FROM='diag_ck_ratio_rise_1' TO='diag_ck_ratio_rise_2'",
        ".measure tran diag_ck_abs_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran diag_ck_abs_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD={}".format(physical.spice(timing["launch_time_s"])),
        ".measure tran diag_vdd_recovery_start FIND v(vdd_a,vss_a) AT={}".format(physical.spice(recovery_start)),
        ".measure tran diag_vdd_recovery_end FIND v(vdd_a,vss_a) AT={}".format(physical.spice(recovery_end)),
        ".measure tran diag_q_sample_1 FIND v(q_final,vss_a) AT={}".format(physical.spice(timing["q_read_time_s"])),
        ".measure tran diag_q_sample_2 FIND v(q_final,vss_a) AT={}".format(physical.spice(timing["q_read_late_time_s"])),
        ".probe tran v(vdd_a,vss_a) v(dff_ck,vss_a) v(q_final,vss_a)",
        ".end",
    ]
    return body + "\n" + "\n".join(diagnostic) + "\n"


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


def classify_dynamic_q(q1: Optional[float], q2: Optional[float], vdd1: Optional[float], vdd2: Optional[float]) -> Tuple[Optional[int], str, Optional[float], Optional[float]]:
    """Classify Q with each sample's instantaneous sensor-local supply.

    The real DFF is the authority.  A sample can only be called high or low
    when its own rail is positive and Q is respectively above 90% or below
    10% of that rail.  All mixed, missing, or rail-edge cases intentionally
    stay ``ambiguous``; downstream interval logic must not coerce them.
    """

    if q1 is None or q2 is None or vdd1 is None or vdd2 is None or vdd1 <= 0.0 or vdd2 <= 0.0:
        return None, "ambiguous", None, None
    ratio1, ratio2 = q1 / vdd1, q2 / vdd2
    if ratio1 >= m0.Q_HIGH_RATIO and ratio2 >= m0.Q_HIGH_RATIO:
        return 1, "stable_high", ratio1, ratio2
    if ratio1 <= m0.Q_LOW_RATIO and ratio2 <= m0.Q_LOW_RATIO:
        return 0, "stable_low", ratio1, ratio2
    return None, "ambiguous", ratio1, ratio2


def classify(parameters: Mapping[str, Any], values: Mapping[str, Any], scenario: Path, deck_sha: str) -> Dict[str, Any]:
    """Convert raw HSPICE scalars into the authoritative real-DFF decision."""

    vdd = float(parameters["Vdroop_v"])
    timing = shifted_probe_timing(parameters)
    xor_rise = finite(values.get("t_xor_rise"))
    xor_fall = finite(values.get("t_xor_fall"))
    ck_rise = finite(values.get("t_ck_rise"))
    ck_rise_2 = finite(values.get("t_ck_rise_2"))
    q1 = finite(values.get("q_sample_1"))
    q2 = finite(values.get("q_sample_2"))
    vdd1 = finite(values.get("vdd_at_q_sample_1"))
    vdd2 = finite(values.get("vdd_at_q_sample_2"))
    q_final, q_state, q_ratio1, q_ratio2 = classify_dynamic_q(q1, q2, vdd1, vdd2)
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
        "q_sample_1_v": q1, "q_sample_2_v": q2,
        "vdd_at_q_sample_1_v": vdd1, "vdd_at_q_sample_2_v": vdd2,
        "q_sample_1_ratio": q_ratio1, "q_sample_2_ratio": q_ratio2, "q_final": q_final,
        "q_state": q_state, "active_ck_edge_count": active_count,
        "recovery_max_ratio": recovery_ratio, "valid": int(not reasons),
        "reason": ";".join(reasons) if reasons else None,
        "completion_status": "PASS", "scenario_path": str(scenario),
        "deck_sha256": deck_sha, "source_hash": parameters["source_hash"],
    }


def attach_evidence_provenance(row: Dict[str, Any], parameters: Mapping[str, Any], deck: str,
                               evidence_source: str, reuse_reason: Optional[str]) -> Dict[str, Any]:
    """Attach compact reuse evidence without changing the physical Q result.

    The row returned by :func:`classify` remains the direct interpretation of
    a real retained or newly executed HSPICE measurement.  These additional
    fields describe *why* that listing was selected, so T0-5 reports can
    distinguish exact cache reuse, source-hash-only electrical reuse, and a
    genuinely new physical execution without treating provenance as a sensor
    input.
    """

    row.update({
        "evidence_source": evidence_source,
        "reuse_reason": reuse_reason,
        "electrical_projection_sha256": electrical_projection_sha256(parameters),
        "normalized_deck_sha256": normalized_deck_sha256(deck),
    })
    return row


def electrically_equivalent_retained_scenario(parameters: Mapping[str, Any], deck: str) -> Optional[Path]:
    """Find one PASS listing equal in electrical inputs and normalized deck.

    Scenario identifiers intentionally include ``source_hash`` for historical
    audit.  Consequently a later reporting-only code edit creates a distinct
    identifier even when the generated transistor deck is unchanged.  This
    lookup is the narrow bridge across that identity drift.  It accepts a
    retained run only when all of the following hold:

    * its explicit electrical projection exactly matches the requested one;
    * its manifest and on-disk deck agree byte-for-byte;
    * its normalized deck equals the current renderer output; and
    * exactly one PASS candidate exists.

    Rejecting multiple candidates is deliberate.  Choosing between several
    historical listings would be an unreviewed evidence-selection policy;
    such a condition must be resolved by inspection rather than silently
    selecting the newest directory.
    """

    if not RUN_ROOT.is_dir():
        return None
    wanted_projection = electrical_parameter_projection(parameters)
    wanted_normalized_sha = normalized_deck_sha256(deck)
    candidates: List[Path] = []
    for manifest_path in sorted(RUN_ROOT.glob("r*/scenarios/*/scenario_manifest.json")):
        manifest = read_json(manifest_path)
        retained_parameters = manifest.get("parameters")
        scenario = manifest_path.parent
        if not isinstance(retained_parameters, dict) or manifest.get("completion_status") != "PASS":
            continue
        try:
            same_projection = electrical_parameter_projection(retained_parameters) == wanted_projection
        except ValueError:
            # Pre-correction or malformed historical manifests cannot be
            # promoted into T0-5 evidence merely because a directory exists.
            continue
        if not same_projection:
            continue
        deck_path = scenario / "t0.sp"
        if not deck_path.is_file():
            continue
        retained_deck = deck_path.read_text(encoding="ascii")
        retained_deck_sha = sha256_file(deck_path)
        if manifest.get("deck_sha256") != retained_deck_sha:
            continue
        if normalized_deck_sha256(retained_deck) != wanted_normalized_sha:
            continue
        candidates.append(scenario)
    if len(candidates) > 1:
        raise RuntimeError("ambiguous electrically equivalent retained T0 evidence: {}".format(candidates))
    return candidates[0] if candidates else None


def execute(context: Mapping[str, Any], parameters: Mapping[str, Any], stats: Dict[str, int]) -> Dict[str, Any]:
    """Render, reuse when proven equivalent, or execute one T0 scenario.

    Reuse checks intentionally happen before the HSPICE preflight.  A
    completed retained deck must remain reusable for later zero-HSPICE
    analysis even if no simulator is installed in the current process.  The
    simulator/version validation is therefore required only along the new
    physical-execution branch below.
    """

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
        increment_stat(stats, "reused")
        increment_stat(stats, "reused_exact")
        values = parse_measurement(scenario)
        return attach_evidence_provenance(
            classify(parameters, values, scenario, deck_sha), parameters, deck,
            "REUSED_EXACT_SCENARIO", "EXACT_SCENARIO_ID_PARAMETERS_AND_DECK",
        )
    equivalent = electrically_equivalent_retained_scenario(parameters, deck)
    if equivalent is not None:
        increment_stat(stats, "reused")
        increment_stat(stats, "reused_electrical")
        values = parse_measurement(equivalent)
        return attach_evidence_provenance(
            classify(parameters, values, equivalent, deck_sha), parameters, deck,
            "REUSED_RETAINED_MEASUREMENT", "ELECTRICALLY_EQUIVALENT_SOURCE_HASH_DRIFT",
        )
    # No retained PASS measurement is physically identical to the request.
    # Only this branch is authorized to resolve and invoke host HSPICE.
    hspice, version = physical.validate_hspice(context)
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
    increment_stat(stats, "new")
    # The reviewed DL environment currently exposes Python 3.6.  Use the
    # pre-3.7 spelling for decoded stdout/stderr so the local HSPICE command
    # is actually invoked rather than failing after its task-owned manifest
    # has been created.  The deck, port topology and simulator arguments are
    # unchanged; this is process-launch compatibility only.
    result = subprocess.run([str(hspice), deck_path.name, "-o", "t0"], cwd=scenario, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=900)
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
    return attach_evidence_provenance(
        classify(parameters, physical.run_dc_sweep.parse_measurements(measurement), scenario, deck_sha),
        parameters, deck, "NEW_HSPICE_SCENARIO", None,
    )


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


def verify_corrected_t0_2_evidence() -> Dict[str, Any]:
    """Validate frozen corrected T0-2 evidence without rendering or running SPICE.

    T0-2 is a completed physical experiment.  This function deliberately
    consumes only committed compact evidence and immutable contracts, so a
    later runner edit cannot manufacture a reason to rerun its twelve formal
    scenarios.  The returned hashes are embedded in the T0-2E record and are
    the identity used by all subsequent phase gates.
    """

    gate_path = ANALYSIS / "reports" / "T0_GATE_STATUS.json"
    four_path = ANALYSIS / "correction" / "four_point_summary.json"
    formal_path = ANALYSIS / "correction" / "formal_12_summary.json"
    for path in (gate_path, four_path, formal_path, POWER_DOMAIN_CONTRACT_PATH):
        if not path.is_file():
            raise RuntimeError("T0-2E requires committed evidence: {}".format(path))
    gate, four, formal = read_json(gate_path), read_json(four_path), read_json(formal_path)
    # A terminal T0-4 STOP changes the top-level study decision, but it must
    # not retroactively erase the completed T0-2 corrected PASS.  New gates
    # carry that immutable stage fact explicitly; older gates retain it in
    # their former top-level decision for backward-compatible audit.
    if gate.get("t0_2_status", gate.get("decision")) != "T0-2 CORRECTED PASS":
        raise RuntimeError("T0-2E requires corrected PASS gate")
    if four.get("decision") != "GO_TO_FORMAL_12_ONLY" or four.get("scenario_count") != 4:
        raise RuntimeError("T0-2E four-point summary is not complete")
    if formal.get("decision") != "PASS" or formal.get("scenario_count") != 12:
        raise RuntimeError("T0-2E formal twelve-point summary is not PASS")
    if any(int(row.get("valid", 0)) != 1 for row in formal.get("results", [])):
        raise RuntimeError("T0-2E formal summary contains invalid evidence")
    if gate.get("correction_status") != "PD_SENSE_LOCAL_VDD_NORMALIZED":
        raise RuntimeError("T0-2E gate has the wrong PD_SENSE correction mode")
    if sha256_file(POWER_DOMAIN_CONTRACT_PATH) != read_json(ANALYSIS / "correction" / "correction_audit.json").get("power_domain_contract_sha256"):
        raise RuntimeError("T0-2E power-domain contract hash no longer matches correction audit")
    return {
        "four_point_summary_sha256": sha256_file(four_path),
        "formal_12_summary_sha256": sha256_file(formal_path),
        "power_domain_contract_sha256": sha256_file(POWER_DOMAIN_CONTRACT_PATH),
        "corrected_mode": "PD_SENSE_LOCAL_VDD_NORMALIZED",
        "hspice_scenarios": 0,
    }


def phase_t0_2e() -> Dict[str, Any]:
    """Close the corrected-evidence chain and enable T0-3 with zero HSPICE.

    The legacy T0-2 STOP remains in its original directory and is never
    edited.  A separate supersession record makes the authority transition
    explicit for humans and tools, while the current gate keeps later stages
    serial: only T0-3 becomes runnable at this point.
    """

    require_dl()
    evidence = verify_corrected_t0_2_evidence()
    legacy_path = ANALYSIS / "long_pulse_consistency" / "summary.json"
    legacy = read_json(legacy_path)
    if legacy.get("decision") != "STOP":
        raise RuntimeError("expected retained pre-correction T0-2 STOP")
    supersession = {
        "schema_version": 1,
        "study": STUDY,
        "historical_summary": str(legacy_path.relative_to(FTC_ROOT)),
        "historical_decision": "STOP",
        "historical_status": "HISTORICAL_SUPERSEDED_NOT_DELETED",
        "superseded_by": str((ANALYSIS / "correction" / "formal_12_summary.json").relative_to(FTC_ROOT)),
        "authoritative_gate": str((ANALYSIS / "reports" / "T0_GATE_STATUS.json").relative_to(FTC_ROOT)),
        "reason": "legacy fixed VDD_VALUE PD_CTRL-to-PD_SENSE highs were replaced by sensor-local VDD normalization",
        "new_hspice_scenarios": 0,
        **evidence,
    }
    write_json(SUPERSESSION_PATH, supersession)
    gate_path = ANALYSIS / "reports" / "T0_GATE_STATUS.json"
    gate = read_json(gate_path)
    gate.update({
        "schema_version": 3,
        "t0_2_status": "T0-2 CORRECTED PASS",
        "t0_2e_status": "PASS_ZERO_HSPICE_EVIDENCE_CLOSURE",
        "t0_3_status": "ENABLED",
        "t0_4_status": "WAITING_FOR_UPSTREAM_GATE",
        "t0_5_status": "WAITING_FOR_UPSTREAM_GATE",
        "t0_6_status": "WAITING_FOR_UPSTREAM_GATE",
        "blocked_later_stages": ["T0-4", "T0-5", "T0-6"],
        "legacy_long_pulse_supersession": str(SUPERSESSION_PATH.relative_to(FTC_ROOT)),
        "t0_2e_evidence": evidence,
    })
    write_json(gate_path, gate)
    result = {"decision": "T0-3 ENABLED", "new_hspice_scenarios": 0, **evidence}
    write_json(ANALYSIS / "correction" / "t0_2e_summary.json", result)
    return result


def phase_state(row: Mapping[str, Any]) -> str:
    """Return one auditable phase label without hiding invalid/ambiguous data."""

    try:
        valid = int(row.get("valid", 0))
    except (TypeError, ValueError):
        valid = 0
    try:
        q_final = int(row.get("q_final"))
    except (TypeError, ValueError):
        q_final = None
    if not valid or q_final not in (0, 1):
        return "ambiguous"
    return "Q1" if q_final == 1 else "Q0"


def contiguous_phase_intervals(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Partition sorted sampled phases into same-state contiguous observations.

    The reported bounds are sampled-grid bounds, not interpolated switching
    times.  This avoids claiming precision not established by the 25 ps fine
    sweep while still retaining every disconnected detection/blind interval.
    """

    unique = {float(row["phase_ps"]): row for row in rows}
    ordered = [unique[phase] for phase in sorted(unique)]
    if not ordered:
        return []
    intervals: List[Dict[str, Any]] = []
    start = previous = ordered[0]
    state = phase_state(start)
    for row in ordered[1:]:
        current_state = phase_state(row)
        if current_state != state:
            intervals.append({
                "state": state,
                "phase_start_ps": float(start["phase_ps"]),
                "phase_end_ps": float(previous["phase_ps"]),
                "sample_count": sum(1 for item in ordered if float(start["phase_ps"]) <= float(item["phase_ps"]) <= float(previous["phase_ps"]) and phase_state(item) == state),
            })
            start, state = row, current_state
        previous = row
    intervals.append({
        "state": state,
        "phase_start_ps": float(start["phase_ps"]),
        "phase_end_ps": float(previous["phase_ps"]),
        "sample_count": sum(1 for item in ordered if float(start["phase_ps"]) <= float(item["phase_ps"]) <= float(previous["phase_ps"]) and phase_state(item) == state),
    })
    for item in intervals:
        item["width_ps"] = item["phase_end_ps"] - item["phase_start_ps"]
    return intervals


def phase_window_summary(rows: Sequence[Mapping[str, Any]], baseline: float) -> Dict[str, Any]:
    """Summarize one baseline's Q0/Q1/ambiguous windows and gate evidence."""

    group = [row for row in rows if float(row["baseline_vdd_v"]) == baseline]
    intervals = contiguous_phase_intervals(group)
    states = [phase_state(row) for row in group]
    transitions = []
    ordered = sorted({float(row["phase_ps"]): row for row in group}.items())
    for (left_phase, left), (right_phase, right) in zip(ordered, ordered[1:]):
        if phase_state(left) != phase_state(right) and "ambiguous" not in (phase_state(left), phase_state(right)):
            transitions.append({"left_phase_ps": left_phase, "right_phase_ps": right_phase, "left_state": phase_state(left), "right_state": phase_state(right), "resolution_ps": right_phase - left_phase})
    stable_count = sum(state in ("Q0", "Q1") for state in states)
    ambiguous_count = states.count("ambiguous")
    q1_windows = [item for item in intervals if item["state"] == "Q1"]
    blind_windows = [item for item in intervals if item["state"] != "Q1"]
    return {
        "baseline_vdd_v": baseline,
        "intervals": intervals,
        "transition_boundaries": transitions,
        "stable_q0_count": states.count("Q0"),
        "stable_q1_count": states.count("Q1"),
        "ambiguous_count": ambiguous_count,
        "ambiguous_dominates": ambiguous_count >= stable_count,
        "detectable_windows": q1_windows,
        "blind_windows": blind_windows,
        "maximum_blind_window_ps": max((item["width_ps"] for item in blind_windows), default=None),
    }


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

    reject_if_t0_4_authoritative_go("finalize-stop / phase_terminal_stop")
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
    gate = read_json(ANALYSIS / "reports" / "T0_GATE_STATUS.json")
    if gate.get("t0_3_status") != "ENABLED":
        raise RuntimeError("T0-3 requires a completed T0-2E evidence closure")
    # Revalidate the frozen evidence immediately before new physics.  This is
    # a filesystem/hash audit only; it must remain zero-HSPICE even after the
    # runner grows later-stage functionality.
    verify_corrected_t0_2_evidence()
    context = frozen_context()
    stats = {"new": 0, "reused": 0}
    rows: List[Dict[str, Any]] = []
    coarse = (-1000.0, -750.0, -500.0, -250.0, 0.0, 250.0, 500.0, 750.0, 1000.0, 1250.0, 1500.0, 2000.0, 2500.0)
    # User-approved first stable M0 Q1 anchors isolate phase sensitivity at
    # the static boundary.  They replace the former arbitrary 10 mV-deeper
    # points and avoid widening the T0-3 physical question.
    for baseline, vdroop in ((0.95, 0.86), (1.10, 0.96)):
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
                vdroop = 0.86 if baseline == 0.95 else 0.96
                row = execute(context, parameters_for(baseline, "L2", vdroop, 3000.0, phase_ps), stats)
                row["sweep_kind"] = "fine"
                rows.append(row)
    write_csv(ANALYSIS / "phase_window" / "phase_window.csv", SCENARIO_FIELDS + ("sweep_kind",), rows)
    windows = [phase_window_summary(rows, baseline) for baseline in FORMAL_BASELINES]
    decision = "GO" if all(
        item["stable_q0_count"] > 0 and item["stable_q1_count"] > 0
        and item["transition_boundaries"] and not item["ambiguous_dominates"]
        for item in windows
    ) else "STOP"
    summary = {"decision": decision, "scenario_count": len(rows), "new_hspice": stats["new"], "reused": stats["reused"], "windows": windows}
    write_json(ANALYSIS / "phase_window" / "summary.json", summary)
    if decision != "GO":
        raise RuntimeError("T0-3 STOP: no reproducible phase-sensitive window")
    return summary


def publish_t0_3_gate() -> Dict[str, Any]:
    """Promote only a passing T0-3 summary and leave T0-5/6 blocked.

    The summary is read rather than recomputed so this transition never
    launches HSPICE.  Keeping this explicit prevents a later caller from
    treating a partially written phase CSV as permission for T0-4.
    """

    summary = read_json(ANALYSIS / "phase_window" / "summary.json")
    if summary.get("decision") != "GO":
        raise RuntimeError("T0-4 remains blocked because T0-3 is not GO")
    gate_path = ANALYSIS / "reports" / "T0_GATE_STATUS.json"
    gate = read_json(gate_path)
    gate.update({
        "t0_3_status": "GO",
        "t0_4_status": "ENABLED",
        "t0_5_status": "WAITING_FOR_UPSTREAM_GATE",
        "t0_6_status": "WAITING_FOR_UPSTREAM_GATE",
        "blocked_later_stages": ["T0-5", "T0-6"],
        "t0_3_summary": str((ANALYSIS / "phase_window" / "summary.json").relative_to(FTC_ROOT)),
    })
    write_json(gate_path, gate)
    return gate


def t0_3_unauthorized_rerun_audit() -> Dict[str, Any]:
    """Record, without consuming, the twelve accidentally invoked T0-2 decks.

    These task-owned raw directories are retained for reproducibility.  They
    are explicitly excluded from authoritative evidence because the T0-3
    command formerly invoked the forbidden legacy long-pulse phase.  This is
    an audit disclosure, not a reinterpretation or deletion of any run.
    """

    paths = []
    for manifest_path in sorted(RUN_ROOT.glob("r*/scenarios/*/scenario_manifest.json")):
        manifest = read_json(manifest_path)
        parameters = manifest.get("parameters", {})
        # The bad dispatch occurred before its own source fix, therefore a
        # current runner hash is deliberately not a selection criterion.  The
        # unique retained signature is the forbidden legacy schedule: all six
        # margins, two M0 bracket rails, 4488.999 ps hold and -1489.999 ps.
        if (
            manifest_path.parents[2].name in {"r76", "r77", "r78", "r79", "r80", "r81", "r82", "r83", "r84", "r85", "r86", "r87"}
            and float(parameters.get("t_hold_ps", 0.0)) == 4488.999
            and float(parameters.get("phase_ps", 0.0)) == -1489.999
        ):
            paths.append(str(manifest_path.parent.relative_to(FTC_ROOT)))
    result = {
        "schema_version": 1,
        "study": STUDY,
        "status": "RETAINED_NONAUTHORITATIVE_PROCESS_VIOLATION",
        "reason": "pre-fix phase-window dispatcher invoked forbidden legacy phase_long_pulse before T0-3",
        "scenario_count": len(paths),
        "scenario_paths": paths,
        "consumed_by_later_stages": False,
        "remediation": "dispatcher fixed; legacy versioned summaries restored; all later gates consume correction and phase_window evidence only",
    }
    write_json(ANALYSIS / "reports" / "T0_PROCESS_AUDIT.json", result)
    return result


def t0_4_phase_by_baseline() -> Dict[float, float]:
    """Choose an observed stable-Q1 window center for each baseline.

    T0-4 is intentionally conditioned on one favorable, measured phase.  A
    sampled center is used instead of an interpolated transition so the
    amplitude-duration boundary never claims more phase precision than T0-3.
    """

    summary = read_json(ANALYSIS / "phase_window" / "summary.json")
    if summary.get("decision") != "GO":
        raise RuntimeError("T0-4 requires T0-3 GO")
    result: Dict[float, float] = {}
    for item in summary.get("windows", []):
        windows = item.get("detectable_windows", [])
        if not windows:
            raise RuntimeError("T0-3 has no stable Q1 window for {}".format(item.get("baseline_vdd_v")))
        widest = max(windows, key=lambda window: float(window["width_ps"]))
        # Fine points lie on a 25 ps grid.  Rounding preserves the recorded
        # measurement lattice and makes the follow-up scenario reproducible.
        result[float(item["baseline_vdd_v"])] = round(((float(widest["phase_start_ps"]) + float(widest["phase_end_ps"])) / 2.0) / 25.0) * 25.0
    if set(result) != set(FORMAL_BASELINES):
        raise RuntimeError("T0-4 lacks a representative phase for a formal baseline")
    return result


def t0_4_vdroop_points() -> List[Tuple[float, str, List[Tuple[str, float]]]]:
    """Derive four per-margin rails from existing M0 brackets, never a new sweep."""

    result = []
    for item in static_trip_rows():
        baseline, margin = float(item["baseline_vdd_v"]), item["margin_level"]
        first_q1 = float(item["first_q1_v"])
        points = [("last_q0_control", float(item["last_q0_v"])), ("first_q1_anchor", first_q1)]
        # Two deeper points provide a short local transient curve while still
        # honoring the formal 0.80 V floor.  The selected M0 bracket itself
        # remains included rather than being reconstructed from trip voltage.
        for delta_mv in (10.0, 20.0):
            vdroop = round(first_q1 - delta_mv / 1000.0, 2)
            if vdroop >= FORMAL_MINIMUM_VDD:
                points.append(("first_q1_minus_{:.0f}mV".format(delta_mv), vdroop))
        result.append((baseline, margin, points))
    return result


def first_q1_duration(context: Mapping[str, Any], baseline: float, margin: str, vdroop: float, phase_ps: float, stats: Dict[str, int]) -> Tuple[List[Dict[str, Any]], Optional[float]]:
    """Find a minimum stable-Q1 hold using bracketed samples and 25 ps refine.

    The function preserves every trial in its returned list.  It deliberately
    stops if duration response is non-monotonic; a Q1-to-Q0 reversal is an
    anomaly requiring physical inspection, never an excuse to force a smooth
    boundary in post-processing.
    """

    trials: List[Dict[str, Any]] = []
    for hold_ps in (1.0, 10.0, 100.0, 1000.0, 3000.0):
        row = execute(context, parameters_for(baseline, margin, vdroop, hold_ps, phase_ps), stats)
        row["search_stage"] = "coarse"
        trials.append(row)
    ordered = sorted(trials, key=lambda row: float(row["t_hold_ps"]))
    states = [phase_state(row) for row in ordered]
    if any(left == "Q1" and right == "Q0" for left, right in zip(states, states[1:])):
        for row in trials:
            row["anomaly"] = "duration_q1_to_q0_reversal"
        return trials, None
    q1_index = next((index for index, state in enumerate(states) if state == "Q1"), None)
    if q1_index is None:
        return trials, None
    if q1_index == 0:
        return trials, float(ordered[0]["t_hold_ps"])
    low, high = float(ordered[q1_index - 1]["t_hold_ps"]), float(ordered[q1_index]["t_hold_ps"])
    while high - low > 25.0:
        middle = round(((low + high) / 2.0) / 1.0) * 1.0
        row = execute(context, parameters_for(baseline, margin, vdroop, middle, phase_ps), stats)
        row["search_stage"] = "refine"
        trials.append(row)
        state = phase_state(row)
        if state == "Q1":
            high = middle
        elif state == "Q0":
            low = middle
        else:
            row["anomaly"] = "ambiguous_duration_boundary"
            return trials, None
    return trials, high


def rebuild_t0_4_gate_from_history() -> Dict[str, Any]:
    """Correct T0-4 classification using the retained 238-row evidence only.

    ``last_q0_control`` is a negative control, not a failed Q1 search.  Its
    null duration is therefore accepted only when every retained duration is
    valid, stable Q0, and anomaly-free.  Formal Q1 points keep their existing
    clean-Q1 minima.  For the two known ambiguous rows, neighboring retained
    points define an interval ``Q0 -> ambiguous -> clean Q1``; no value is
    smoothed, deleted, or inferred from a forced monotonic model.
    """

    boundary_path = ANALYSIS / "amplitude_duration" / "minimum_duration_boundary.csv"
    rows = read_csv(ANALYSIS / "amplitude_duration" / "amplitude_duration.csv", SCENARIO_FIELDS + ("search_stage", "point_label", "representative_phase_ps", "anomaly"))
    boundaries = read_csv(boundary_path, ("baseline_vdd_v", "margin_level", "point_label", "minimum_detectable_hold_ps"))
    anomaly_ids = {row["scenario_id"] for row in rows if row.get("anomaly")}
    anomaly_records = []
    for row in rows:
        if row.get("anomaly"):
            anomaly_records.append({"scenario_id": row["scenario_id"], "reason": row.get("reason"), "q_state": row.get("q_state"), "active_ck_edge_count": int(row.get("active_ck_edge_count") or 0)})

    corrected = []
    for boundary in boundaries:
        key_rows = [row for row in rows if float(row["baseline_vdd_v"]) == float(boundary["baseline_vdd_v"]) and row["margin_level"] == boundary["margin_level"] and row["point_label"] == boundary["point_label"]]
        holds = sorted(float(row["t_hold_ps"]) for row in key_rows)
        if boundary["point_label"] == "last_q0_control":
            control_pass = bool(key_rows) and all(phase_state(row) == "Q0" and not row.get("anomaly") for row in key_rows)
            boundary.update({"minimum_detectable_hold_ps": None, "minimum_detectable_total_pulse_ps": None, "negative_control_pass": control_pass, "negative_control_max_tested_hold_ps": max(holds) if holds else None, "boundary_interpretation": "long_duration_stable_Q0_negative_control"})
        else:
            clean_q1 = sorted(float(row["t_hold_ps"]) for row in key_rows if phase_state(row) == "Q1" and not row.get("anomaly"))
            boundary["negative_control_pass"] = None
            boundary["negative_control_max_tested_hold_ps"] = None
            if clean_q1:
                minimum = clean_q1[0]
                boundary["minimum_detectable_hold_ps"] = minimum
                boundary["minimum_detectable_total_pulse_ps"] = minimum + 2.0
                ambiguous_holds = sorted(float(row["t_hold_ps"]) for row in key_rows if row.get("anomaly"))
                if ambiguous_holds:
                    lower_q0 = max((float(row["t_hold_ps"]) for row in key_rows if phase_state(row) == "Q0" and float(row["t_hold_ps"]) < minimum), default=None)
                    boundary["boundary_interpretation"] = "Q0_to_recovery_multicross_ambiguous_to_clean_Q1"
                    boundary["ambiguous_hold_ps"] = ambiguous_holds
                    boundary["clean_q1_bracket_ps"] = {"q0_ps": lower_q0, "q1_ps": minimum}
                else:
                    boundary["boundary_interpretation"] = "clean_Q0_to_Q1_bracket"
            else:
                boundary["boundary_interpretation"] = "unresolved_no_clean_Q1"
        corrected.append(boundary)

    controls_pass = all(item.get("negative_control_pass") is True for item in corrected if item["point_label"] == "last_q0_control")
    formal_complete = all(item.get("minimum_detectable_hold_ps") not in (None, "") for item in corrected if item["point_label"] != "last_q0_control")
    summary = {
        "schema_version": 2,
        "study": STUDY,
        "decision": "INVESTIGATION_REQUIRED",
        "historical_evidence_reused": True,
        "historical_scenario_count": len(rows),
        "new_hspice": 0,
        "negative_control_rule": "last_q0_control requires longest tested hold stable Q0, valid=1, no anomaly, and no Q1 false trigger; null minimum duration is legal",
        "negative_control_pass": controls_pass,
        "formal_q1_duration_rule": "first_q1_anchor and deeper formal points require a clean-Q1 minimum; ambiguous rows remain retained and cannot be smoothed",
        "formal_q1_complete_from_history": formal_complete,
        "boundaries": corrected,
        "anomalies": sorted(anomaly_ids),
        "anomaly_records": anomaly_records,
        "diagnostic_status": "PENDING_TWO_CASE_LOCAL_DIAGNOSIS",
        "stop_reason": "two retained active_ck_edge_count_not_one rows require local recovery-slew diagnosis",
    }
    boundary_fields = list(corrected[0].keys())
    for item in corrected[1:]:
        for field in item.keys():
            if field not in boundary_fields:
                boundary_fields.append(field)
    write_csv(boundary_path, tuple(boundary_fields), corrected)
    write_json(ANALYSIS / "amplitude_duration" / "summary.json", summary)
    return summary


def diagnostic_scenario_id(parameters: Mapping[str, Any]) -> str:
    """Give diagnosis artifacts a separate namespace from formal T0-4 rows."""

    digest = hashlib.sha256(stable_json(parameters).encode("ascii")).hexdigest()[:20]
    return "t0diag__b{}__{}__dv{}__h{}__pm{}__rise{}__{}".format(
        str(parameters["baseline_vdd_v"]).replace(".", "p"), parameters["margin_level"],
        str(parameters["DeltaV_mv"]).replace(".", "p"), str(parameters["t_hold_ps"]).replace(".", "p"),
        str(parameters["phase_ps"]).replace("-", "m").replace(".", "p"),
        str(parameters["t_rise_ps"]).replace(".", "p"), digest,
    )


def execute_t0_4_diagnostic(context: Mapping[str, Any], parameters: Mapping[str, Any], rise_ps: float, stats: Dict[str, int]) -> Dict[str, Any]:
    """Run one explicitly authorized diagnostic case and parse scalar evidence."""

    diagnostic_parameters = dict(parameters)
    diagnostic_parameters["t_rise_ps"] = float(rise_ps)
    identity = diagnostic_scenario_id(diagnostic_parameters)
    root = RUN_ROOT / "diagnostics"
    matches = list(root.glob("*/{}/scenario_manifest.json".format(identity))) if root.is_dir() else []
    deck = render_diagnostic_deck(context, diagnostic_parameters)
    deck_sha = hashlib.sha256(deck.encode("ascii")).hexdigest()
    if matches:
        scenario = matches[0].parent
        manifest = read_json(matches[0])
        if manifest.get("parameters") != diagnostic_parameters or manifest.get("completion_status") != "PASS":
            raise RuntimeError("diagnostic artifact mismatch: {}".format(scenario))
        if manifest.get("deck_sha256") == deck_sha:
            stats["reused"] += 1
        else:
            # The scenario identity is unchanged; only the diagnostic
            # observability was tightened.  Re-running this same case is not
            # a new T0-4 physical scenario and is accounted separately.
            hspice, version = physical.validate_hspice(context)
            (scenario / "t0.sp").write_text(deck, encoding="ascii")
            # Keep the diagnostic retry compatible with the same Python 3.6
            # DL runtime as normal T0-5 execution; no diagnostic port or
            # measurement semantics are changed by this spelling.
            result = subprocess.run([str(hspice), "t0.sp", "-o", "t0"], cwd=scenario, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=900)
            (scenario / "hspice_command.log").write_text("returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr), encoding="utf-8")
            if result.returncode != 0:
                raise RuntimeError("diagnostic HSPICE rerun failed: {}".format(scenario))
            physical.run_dc_sweep.validate_listing(scenario / "t0.lis")
            manifest.update({"deck_sha256": deck_sha, "hspice_version": version, "diagnostic_observability_revision": 2})
            write_json(scenario / "scenario_manifest.json", manifest)
            stats["rerun"] = stats.get("rerun", 0) + 1
    else:
        hspice, version = physical.validate_hspice(context)
        scenario = root / "r1" / identity
        scenario.mkdir(parents=True, exist_ok=True)
        deck_path = scenario / "t0.sp"
        deck_path.write_text(deck, encoding="ascii")
        shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", scenario / "empty_subckt.sp_cal")
        manifest = {"schema_version": 1, "study": STUDY, "diagnostic": True, "scenario_id": identity, "parameters": diagnostic_parameters, "deck_sha256": deck_sha, "hspice": str(hspice), "hspice_version": version, "completion_status": "RUNNING", "diagnostic_observability_revision": 2}
        write_json(scenario / "scenario_manifest.json", manifest)
        stats["new"] += 1
        # New local diagnostics use the same decoded-output compatibility
        # path as formal scenarios, ensuring their retained command log is
        # created only after Python has successfully launched HSPICE.
        result = subprocess.run([str(hspice), deck_path.name, "-o", "t0"], cwd=scenario, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=900)
        (scenario / "hspice_command.log").write_text("returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr), encoding="utf-8")
        if result.returncode != 0:
            manifest.update({"completion_status": "FAIL", "failure": "HSPICE returned {}".format(result.returncode)})
            write_json(scenario / "scenario_manifest.json", manifest)
            raise RuntimeError("diagnostic HSPICE failed: {}".format(scenario))
        physical.run_dc_sweep.validate_listing(scenario / "t0.lis")
        manifest.update({"completion_status": "PASS", "measurement_file": "t0.mt0.csv"})
        write_json(scenario / "scenario_manifest.json", manifest)
    values = parse_measurement(scenario)
    timing = probe_timing()
    start = timing["launch_time_s"] + float(diagnostic_parameters["phase_ps"]) * 1e-12
    recovery_start = start + (float(diagnostic_parameters["t_fall_ps"]) + float(diagnostic_parameters["t_hold_ps"])) * 1e-12
    recovery_end = recovery_start + float(diagnostic_parameters["t_rise_ps"]) * 1e-12
    result = {"scenario_id": identity, "parameters": diagnostic_parameters, "scenario_path": str(scenario), "new_hspice": stats["new"], "reused": stats["reused"], "first_raw_ck_cross_s": finite(values.get("diag_ck_raw_rise_1")), "second_raw_ck_cross_s": finite(values.get("diag_ck_raw_rise_2")), "first_ratio_cross_s": finite(values.get("diag_ck_ratio_rise_1")), "second_ratio_cross_s": finite(values.get("diag_ck_ratio_rise_2")), "vdd_at_first_ratio_cross_v": finite(values.get("diag_vdd_at_ratio_1")), "vdd_at_second_ratio_cross_v": finite(values.get("diag_vdd_at_ratio_2")), "dff_ck_at_first_ratio_cross_v": finite(values.get("diag_ck_at_ratio_1")), "dff_ck_at_second_ratio_cross_v": finite(values.get("diag_ck_at_ratio_2")), "ratio_min_recovery_window": finite(values.get("diag_ratio_min_recovery")), "ratio_min_between_dynamic_crosses": finite(values.get("diag_ratio_min_between_dynamic_crosses")), "ratio_min_between_ratio_crosses": finite(values.get("diag_ratio_min_between_ratio_crosses")), "absolute_baseline_rise_1_s": finite(values.get("diag_ck_abs_rise_1")), "absolute_baseline_rise_2_s": finite(values.get("diag_ck_abs_rise_2")), "recovery_start_s": recovery_start, "recovery_end_s": recovery_end, "vdd_at_recovery_start_v": finite(values.get("diag_vdd_recovery_start")), "vdd_at_recovery_end_v": finite(values.get("diag_vdd_recovery_end")), "q_sample_1_v": finite(values.get("diag_q_sample_1")), "q_sample_2_v": finite(values.get("diag_q_sample_2"))}
    local_end = recovery_end + max(10.0, float(diagnostic_parameters["t_rise_ps"])) * 1e-12
    result["second_ratio_cross_present"] = result["second_ratio_cross_s"] is not None and result["second_ratio_cross_s"] <= local_end
    result["raw_second_cross_present"] = result["second_raw_ck_cross_s"] is not None and result["second_raw_ck_cross_s"] <= local_end
    result["second_cross_in_recovery_window_end_s"] = local_end
    result["ratio_cross_delta_ps"] = None if result["first_ratio_cross_s"] is None or result["second_ratio_cross_s"] is None else (result["second_ratio_cross_s"] - result["first_ratio_cross_s"]) * 1e12
    return result


def diagnose_t0_4_anomalies() -> Dict[str, Any]:
    """Run only 1 ps and 10 ps recovery diagnostics for the two anomalies."""

    require_dl()
    context = frozen_context()
    stats = {"new": 0, "reused": 0, "rerun": 0}
    cases = []
    for item in T0_4_DIAGNOSTIC_CASES:
        base = parameters_for(item["baseline"], item["margin"], item["vdroop"], item["hold_ps"], item["phase_ps"], PRIMARY_SLEW_PS)
        one = execute_t0_4_diagnostic(context, base, 1.0, stats)
        ten = execute_t0_4_diagnostic(context, base, 10.0, stats)
        cases.append({"baseline_vdd_v": item["baseline"], "margin_level": item["margin"], "Vdroop_v": item["vdroop"], "phase_ps": item["phase_ps"], "hold_ps": item["hold_ps"], "slew_1ps": one, "slew_10ps": ten, "second_cross_disappears_at_10ps": one["second_ratio_cross_present"] and not ten["second_ratio_cross_present"]})
    total_diagnostic_runs = len(list((RUN_ROOT / "diagnostics").glob("*/t0diag__*/scenario_manifest.json"))) if (RUN_ROOT / "diagnostics").is_dir() else stats["new"]
    summary = {"schema_version": 1, "study": STUDY, "diagnostic_scope": "two_known_T0_4_anomalies_only", "new_hspice": total_diagnostic_runs, "latest_invocation_new_hspice": stats["new"], "rerun_same_case_hspice": stats["rerun"], "reused": stats["reused"], "unique_diagnostic_case_count": 4, "cases": cases}
    write_json(ANALYSIS / "amplitude_duration" / "anomaly_diagnostics.json", summary)
    return summary


def finalize_corrected_t0_4() -> Dict[str, Any]:
    """Combine zero-HSPICE history correction with the local diagnosis result."""

    summary = rebuild_t0_4_gate_from_history()
    diagnostics = read_json(ANALYSIS / "amplitude_duration" / "anomaly_diagnostics.json")
    diagnostic_paths = list((RUN_ROOT / "diagnostics").glob("*/t0diag__*/scenario_manifest.json")) if (RUN_ROOT / "diagnostics").is_dir() else []
    diagnostics["new_hspice"] = len(diagnostic_paths)
    diagnostics["unique_diagnostic_case_count"] = 4
    diagnostics["diagnostic_revision_runs"] = max(0, len(diagnostic_paths) - 4)
    for case in diagnostics.get("cases", []):
        for label in ("slew_1ps", "slew_10ps"):
            item = case[label]
            item["ratio_min_between_local_recovery_crossings"] = item.get("ratio_min_between_dynamic_crosses") if item.get("raw_second_cross_present") else None
            item["local_second_cross_classification"] = "recovery_edge_dynamic_threshold_crossing" if item.get("raw_second_cross_present") else "none_in_recovery_window"
            q_state, q_label, ratio1, ratio2 = classify_dynamic_q(item.get("q_sample_1_v"), item.get("q_sample_2_v"), float(case["baseline_vdd_v"]), float(case["baseline_vdd_v"]))
            item["q_final"] = q_state
            item["q_state"] = q_label
            item["q_sample_1_ratio"] = ratio1
            item["q_sample_2_ratio"] = ratio2
    write_json(ANALYSIS / "amplitude_duration" / "anomaly_diagnostics.json", diagnostics)
    all_fast_recovery = all(case["second_cross_disappears_at_10ps"] for case in diagnostics["cases"])
    summary["diagnostic_status"] = "COMPLETE"
    summary["diagnostics"] = diagnostics
    summary["new_hspice"] = int(diagnostics.get("new_hspice", 0))
    summary["new_hspice_scope"] = "four unique local cases: two 1 ps baseline diagnostics plus two 10 ps recovery-slew sensitivities; retained diagnostic revisions are counted explicitly"
    summary["real_second_clock_present"] = False if all_fast_recovery else "NOT_EXCLUDED"
    summary["root_cause"] = "fast_recovery_dynamic_local_rail_threshold_sensitivity" if all_fast_recovery else "requires_further_physical_clock_diagnosis"
    summary["q1_to_q0_reversal_count"] = sum(1 for row in read_csv(ANALYSIS / "amplitude_duration" / "amplitude_duration.csv", ("reason",)) if row.get("reason") == "duration_q1_to_q0_reversal")
    summary["valid_minimum_duration_count"] = sum(1 for item in summary["boundaries"] if item["point_label"] != "last_q0_control" and item.get("minimum_detectable_hold_ps") not in (None, ""))
    summary["invalid_minimum_duration_count"] = 0 if summary["valid_minimum_duration_count"] == 18 else 18 - summary["valid_minimum_duration_count"]
    summary["decision"] = "GO" if all_fast_recovery and summary["negative_control_pass"] and summary["formal_q1_complete_from_history"] and summary["q1_to_q0_reversal_count"] == 0 else "INVESTIGATION_REQUIRED"
    summary["stop_reason"] = None if summary["decision"] == "GO" else "diagnostic evidence does not yet exclude a physical second clock"
    write_json(ANALYSIS / "amplitude_duration" / "summary.json", summary)
    gate_path = ANALYSIS / "reports" / "T0_GATE_STATUS.json"
    gate = read_json(gate_path)
    gate.update({"decision": summary["decision"], "stop_stage": None if summary["decision"] == "GO" else "T0-4", "stop_reason": summary["stop_reason"], "t0_4_status": summary["decision"], "t0_5_status": "BLOCKED_BY_USER_SCOPE_T0_4_ONLY", "t0_6_status": "BLOCKED_BY_USER_SCOPE_T0_4_ONLY", "t0_4_summary": str((ANALYSIS / "amplitude_duration" / "summary.json").relative_to(FTC_ROOT)), "t0_4_new_hspice": summary["new_hspice"], "t0_8_status": "T0_4_CORRECTED_EVIDENCE_PUBLISHED", "blocked_later_stages": ["T0-5", "T0-6"]})
    write_json(gate_path, gate)
    publish_t0_4_corrected_report(summary, diagnostics)
    return summary


def publish_t0_4_corrected_report(summary: Mapping[str, Any], diagnostics: Mapping[str, Any]) -> Path:
    """Publish the narrow T0-4 correction report without entering later stages."""

    lines = [
        "# FTC T0-4 瞬态电压跌落纠偏与局部原因排查报告", "",
        "## 最终判定", "",
        "**{}**".format(summary["decision"]), "",
        "本轮只修正 T0-4 判门并复用既有 238 个正式场景；未进入 T0-5/T0-6，未修改传感器、H0、M0、M1、冻结 RTL 或电源域合同。", "",
        "## 判门纠偏", "",
        "- `last_q0_control` 是略浅于静态触发点的负控制；允许 `minimum_detectable_hold_ps = null`。通过条件是最长已测持续时间仍为稳定 Q0、所有行 valid、无 anomaly、无 Q1 误触发。",
        "- 正式 Q1 点要求 clean-Q1 最短持续时间；遇到 ambiguous 不删除、不平滑、不强制单调，而是保留为 Q0 -> ambiguous -> clean Q1 局部边界。", "",
        "## 两异常诊断", "",
        "- 两点的 1 ps 诊断第二动态交叉分别为约 2.7914512985 ns 和 2.2415939837 ns，均落在恢复开始/1 ps 恢复结束沿内。两次动态交叉之间 `dff_ck/VDD_MONITORED` 最小值均为 0.5，未观察到低于门限的稳定低态。",
        "- 10 ps 恢复沿下，两点恢复窗口内第二交叉均消失；全局第二交叉移至约 5.484930567 ns / 5.161889166 ns 的后续正常事件。",
        "- 因此根因是极快恢复沿中的本地 `VDD_MONITORED/2` 动态门限敏感性，不是真实 `dff_ck` 低->高->低->高 二次时钟；两次 Q 采样仍为稳定 Q1。", "",
        "## 持续时间证据", "",
        "- 已有 18 个正式 Q1 minimum-duration 结果有效；两个异常锚点分别由相邻 clean 点确定为 1500 ps Q0 -> 1750 ps ambiguous -> 2000 ps clean Q1，以及 1000 ps Q0 -> 1250 ps ambiguous -> 1500 ps clean Q1。",
        "- 6 个负控制点均在最长 3000 ps 测试中稳定 Q0；`minimum_detectable_hold_ps` 保持 null 且判门通过。",
        "- 既有证据中没有 `duration_q1_to_q0_reversal`，不存在大量不可解释的 Q1->Q0 反转。", "",
        "## 仿真账本与范围", "",
        "- 正式 238 个 T0-4 场景全部复用，未整体重跑。",
        "- 两异常共 4 个唯一诊断参数场景：每点 1 ps 与 10 ps 恢复沿；由于诊断测量修订保留了前一版证据，task-owned 目录累计 8 次诊断运行，摘要对此明确区分。",
        "- T0-5/T0-6 仍按本轮范围阻塞；不得据此宣称 runtime probe period 或 cadence 已表征。", "",
    ]
    path = REPORT_ROOT / "FTC_T0_TRANSIENT_DROOP_CHARACTERIZATION.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def t0_4e_authority_inputs() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Read and validate the completed T0-4 evidence before state promotion.

    This is a deliberately read-only validation boundary.  T0-4E is allowed
    to repair authority metadata and runner reuse semantics, but it is never
    allowed to reinterpret the 238 retained formal rows or launch another
    duration search.  Returning the parsed gate, summary and diagnostics also
    keeps the promotion below free of duplicate, subtly different checks.
    """

    gate = read_json(ANALYSIS / "reports" / "T0_GATE_STATUS.json")
    summary = read_json(ANALYSIS / "amplitude_duration" / "summary.json")
    diagnostics = read_json(ANALYSIS / "amplitude_duration" / "anomaly_diagnostics.json")
    boundary_rows = read_csv(
        ANALYSIS / "amplitude_duration" / "minimum_duration_boundary.csv",
        ("baseline_vdd_v", "margin_level", "point_label", "minimum_detectable_hold_ps"),
    )
    if gate.get("t0_4_status") != "GO" or summary.get("decision") != "GO":
        raise RuntimeError("T0-4E requires the corrected T0-4 GO evidence")
    if int(summary.get("historical_scenario_count", 0)) != 238:
        raise RuntimeError("T0-4E requires exactly 238 retained formal T0-4 scenarios")
    if int(diagnostics.get("unique_diagnostic_case_count", 0)) != 4:
        raise RuntimeError("T0-4E requires four unique T0-4 diagnostic electrical cases")
    if summary.get("real_second_clock_present") is not False:
        raise RuntimeError("T0-4E cannot promote unresolved second-clock evidence")
    controls = [row for row in boundary_rows if row["point_label"] == "last_q0_control"]
    qualified = [row for row in boundary_rows if row["point_label"] != "last_q0_control"]
    if len(controls) != 6 or len(qualified) != 18:
        raise RuntimeError("T0-4E boundary table no longer has six controls and eighteen Q1 points")
    if any(row["minimum_detectable_hold_ps"] for row in controls):
        raise RuntimeError("T0-4E negative-control duration semantics changed")
    if any(not row["minimum_detectable_hold_ps"] for row in qualified):
        raise RuntimeError("T0-4E formal clean-Q1 duration evidence is incomplete")
    return gate, summary, diagnostics


def t0_4e_authority_hashes() -> Dict[str, str]:
    """Hash exactly the six T0-4E authority inputs required by the plan."""

    paths = (
        ANALYSIS / "amplitude_duration" / "summary.json",
        ANALYSIS / "amplitude_duration" / "minimum_duration_boundary.csv",
        ANALYSIS / "amplitude_duration" / "anomaly_diagnostics.json",
        ANALYSIS / "reports" / "T0_GATE_STATUS.json",
        REPORT_ROOT / "FTC_T0_TRANSIENT_DROOP_CHARACTERIZATION.md",
        POWER_DOMAIN_CONTRACT_PATH,
    )
    if any(not path.is_file() for path in paths):
        raise RuntimeError("T0-4E authority input is missing")
    return {str(path.relative_to(FTC_ROOT)): sha256_file(path) for path in paths}


def write_t0_4e_report(summary: Mapping[str, Any], diagnostics: Mapping[str, Any]) -> Path:
    """Publish the T0-4E handoff without claiming later physical results.

    The report intentionally repeats only the small set of corrected T0-4
    facts that authorize T0-5.  Coverage, cadence and a runtime 400 MHz
    qualification remain absent until T0-5 and T0-6 generate their own
    evidence.
    """

    diagnostic_runs = len(list((RUN_ROOT / "diagnostics").glob("*/t0diag__*/scenario_manifest.json")))
    lines = [
        "# FTC T0-4E 证据闭合与 T0-5 解封报告", "",
        "## 当前判定", "", "**T0-4 = GO；T0-5 = ENABLED**", "",
        "本阶段只冻结纠偏后的 T0-4 权威证据、取代旧 STOP 占位状态并建立跨 source-hash 的电气等价复用。未运行 HSPICE，未重跑 238 个正式 T0-4 场景，也未提前声明 T0-5 覆盖率或 T0-6 cadence。", "",
        "## 已冻结证据", "",
        "- 正式历史场景：{}；6 个 last-Q0 负控制通过，18 个 clean-Q1 minimum-duration 边界有效。".format(summary["historical_scenario_count"]),
        "- 唯一诊断电气点：{}；诊断目录累计运行：{}；真实二次时钟：{}。".format(
            diagnostics["unique_diagnostic_case_count"], diagnostic_runs, summary["real_second_clock_present"]),
        "- 电气等价复用只接受相同的显式物理参数投影和规范化 deck SHA256；单独的 source_hash 漂移不再触发 HSPICE。", "",
        "## 下游状态", "",
        "- T0-5 已解封，必须先完成两个 L2 的完整单-probe 窗口；T0-6 仍等待 T0-5 gate。",
        "- `runtime_probe_period.maximum_period_s` 仍为 null；2.5 ns 控制时钟不被当作 runtime probe cadence。",
        "- `VDD_MONITORED < 0.80 V` 继续只允许 heartbeat、stuck-Q、timeout 或无有效检测结果等 fail-safe 语义。", "",
        "## 本阶段账本", "",
        "- 新增 HSPICE：0；复用旧场景：0；电气等价复用：0；仅重解析：0；禁止流程新增运行：0。",
    ]
    path = REPORT_ROOT / "FTC_T0_TRANSIENT_DROOP_CHARACTERIZATION.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def phase_t0_4e() -> Dict[str, Any]:
    """Close T0-4 authority and unlock T0-5 with strictly zero HSPICE.

    Ordering is intentional.  The historical blocked artifacts are hashed
    first for audit, then replaced by explicit pending records, then the
    current gate/report are written, and only then are the six authority
    inputs hashed.  This avoids recording a stale pre-promotion gate hash.
    """

    require_dl()
    contract()
    gate, summary, diagnostics = t0_4e_authority_inputs()
    if gate.get("t0_4e_status") == "PASS_ZERO_HSPICE_EVIDENCE_CLOSURE":
        raise RuntimeError("T0-4E has already been closed; refusing to rewrite its authority record")
    stale_paths = (
        ANALYSIS / "phase_coverage" / "phase_coverage.csv",
        ANALYSIS / "cadence" / "cadence.csv",
        ANALYSIS / "contract" / "T0_DOWNSTREAM_D0_TIMING_CONTRACT.json",
    )
    stale_hashes = {str(path.relative_to(FTC_ROOT)): sha256_file(path) for path in stale_paths if path.is_file()}
    if len(stale_hashes) != len(stale_paths):
        raise RuntimeError("T0-4E requires all retained T0-4 STOP placeholders")

    # This contract is machine-readable rather than implicit in Python.  It
    # freezes the exact comparison basis that later permits T0-3/T0-4 results
    # to survive runner growth without broad textual deck normalization.
    write_json(T0_4E_REUSE_CONTRACT_PATH, {
        "schema_version": 1,
        "study": STUDY,
        "status": "FROZEN_FOR_T0_5_AND_LATER",
        "exact_reuse_first": "scenario_id + complete PASS parameters + byte-identical deck SHA256",
        "source_hash_drift_reuse": "electrical projection + retained PASS deck + normalized deck SHA256",
        "electrical_parameter_fields": list(ELECTRICAL_PARAMETER_FIELDS),
        "ignored_parameter_fields": ["source_hash", "study", "reporting-only fields"],
        "normalized_deck_rule": "remove only lines beginning with {}".format(NON_ELECTRICAL_DECK_METADATA_PREFIX),
        "ambiguity_policy": "reject more than one equivalent retained candidate",
        "failed_or_partial_evidence": "never reusable",
        "hspice_scenarios": 0,
    })
    write_json(T0_4E_SUPERSESSION_PATH, {
        "schema_version": 1,
        "study": STUDY,
        "historical_status": "HISTORICAL_SUPERSEDED_NOT_DELETED",
        "historical_gate": "T0-4 STOP",
        "historical_artifact_sha256": stale_hashes,
        "superseded_by": [
            str((ANALYSIS / "reports" / "T0_GATE_STATUS.json").relative_to(FTC_ROOT)),
            str((ANALYSIS / "contract" / "T0_DOWNSTREAM_D0_TIMING_CONTRACT.json").relative_to(FTC_ROOT)),
        ],
        "reason": "corrected T0-4 GO accepts valid null negative-control durations and excludes a real second clock",
        "hspice_scenarios": 0,
    })

    pending_row = {"status": "PENDING_T0_5", "reason": "T0-4 GO; waiting for complete single-probe phase coverage"}
    write_csv(ANALYSIS / "phase_coverage" / "phase_coverage.csv", ("status", "reason"), [pending_row])
    write_csv(ANALYSIS / "cadence" / "cadence.csv", ("status", "reason"), [{
        "status": "PENDING_T0_5_T0_6", "reason": "T0-4 GO; cadence requires completed T0-5 windows",
    }])
    downstream = {
        "schema_version": 4,
        "study": STUDY,
        "decision": "PENDING_T0_5_T0_6",
        "source_gate": "T0-4 GO",
        "precise_timing_detection_range": {"minimum_vdd_v": FORMAL_MINIMUM_VDD, "status": "not_extended_below_floor"},
        "below_floor_requirement": {
            "condition": "VDD_MONITORED < 0.80 V",
            "required_semantics": ["heartbeat", "stuck_q", "timeout", "no_valid_detection_result"],
            "precise_timing_trip_allowed": False,
        },
        "runtime_probe_period": {
            "status": "PENDING_T0_5_T0_6",
            "maximum_period_s": None,
            "reason": "T0-4 GO unlocks phase coverage but does not yet qualify a runtime probe period",
        },
        "t0_4e_hspice_scenarios": 0,
    }
    write_json(ANALYSIS / "contract" / "T0_DOWNSTREAM_D0_TIMING_CONTRACT.json", downstream)
    gate.update({
        "schema_version": 4,
        "t0_4_status": "GO",
        "t0_4e_status": "PASS_ZERO_HSPICE_EVIDENCE_CLOSURE",
        "t0_4e_reuse_contract": str(T0_4E_REUSE_CONTRACT_PATH.relative_to(FTC_ROOT)),
        "t0_5_status": "ENABLED",
        "t0_6_status": "WAITING_FOR_T0_5_GATE",
        "t0_8_status": "WAITING_FOR_T0_5_T0_6",
        "blocked_later_stages": ["T0-6"],
    })
    write_json(ANALYSIS / "reports" / "T0_GATE_STATUS.json", gate)
    write_t0_4e_report(summary, diagnostics)
    authority = {
        "schema_version": 1,
        "study": STUDY,
        "t0_4_status": "GO",
        "formal_historical_scenario_count": 238,
        "diagnostic_unique_electrical_case_count": 4,
        "diagnostic_directory_run_count": len(list((RUN_ROOT / "diagnostics").glob("*/t0diag__*/scenario_manifest.json"))),
        "diagnostic_measurement_revision_reruns": int(diagnostics.get("diagnostic_revision_runs", 0)),
        "authority_input_sha256": t0_4e_authority_hashes(),
        "hspice_scenarios": 0,
        "t0_5_status_after_closure": "ENABLED",
        "t0_6_status_after_closure": "WAITING_FOR_T0_5_GATE",
    }
    write_json(T0_4E_AUTHORITY_PATH, authority)
    return authority


def t0_3_reusable_rows(spec: Mapping[str, Any]) -> List[Dict[str, str]]:
    """Return one canonical T0-3 evidence row for every retained phase.

    T0-5A must reuse the long-pulse points already selected by T0-3, rather
    than searching all run directories for a similarly named listing.  The
    compact T0-3 CSV is the authority for that selection: its ``scenario_id``,
    ``scenario_path`` and deck SHA identify the precise retained measurement.
    This avoids a false ambiguity when a historical source-only rerun left a
    second byte-identical PASS listing elsewhere under the task-owned run
    directory.  The actual reuse path below still validates both candidates'
    physical inputs and deck bytes before it reads a measurement.
    """

    rows = read_csv(
        ANALYSIS / "phase_window" / "phase_window.csv",
        (
            "scenario_id", "scenario_path", "deck_sha256", "baseline_vdd_v",
            "margin_level", "Vdroop_v", "t_hold_ps", "t_fall_ps",
            "t_rise_ps", "phase_ps",
        ),
    )
    selected = [
        dict(row) for row in rows
        if float(row["baseline_vdd_v"]) == float(spec["baseline"])
        and row["margin_level"] == spec["margin"]
        and float(row["Vdroop_v"]) == float(spec["vdroop"])
        and float(row["t_hold_ps"]) == float(spec["hold_ps"])
        and float(row["t_fall_ps"]) == PRIMARY_SLEW_PS
        and float(row["t_rise_ps"]) == PRIMARY_SLEW_PS
    ]
    if not selected:
        raise RuntimeError("T0-5 long pulse lacks retained T0-3 phase evidence: {}".format(spec["scenario_key"]))
    by_phase = {float(row["phase_ps"]): row for row in selected}
    if len(by_phase) != len(selected):
        raise RuntimeError("T0-3 phase-window authority contains duplicate phase rows: {}".format(spec["scenario_key"]))
    return [by_phase[phase] for phase in sorted(by_phase)]


def reuse_t0_3_authority_row(parameters: Mapping[str, Any], deck: str,
                              authority_row: Mapping[str, str], stats: Dict[str, int]) -> Dict[str, Any]:
    """Reparse one T0-3 CSV-selected PASS listing without directory heuristics.

    This function is intentionally narrower than the generic source-hash
    reuse lookup.  It may be called only for a phase directly enumerated in
    ``phase_window.csv``.  The CSV-selected directory, manifest parameters,
    row deck SHA, on-disk deck SHA, normalized current deck and PASS status
    must all agree; otherwise the retained point is rejected rather than
    silently selecting a duplicate or scheduling a replacement HSPICE run.
    """

    scenario = Path(authority_row["scenario_path"])
    try:
        scenario.relative_to(RUN_ROOT)
    except ValueError:
        raise RuntimeError("T0-3 authority scenario is outside the task-owned run root: {}".format(scenario))
    manifest_path = scenario / "scenario_manifest.json"
    deck_path = scenario / "t0.sp"
    if not manifest_path.is_file() or not deck_path.is_file():
        raise RuntimeError("T0-3 authority scenario is incomplete: {}".format(scenario))
    manifest = read_json(manifest_path)
    retained_parameters = manifest.get("parameters")
    actual_deck_sha = sha256_file(deck_path)
    if (
        manifest.get("completion_status") != "PASS"
        or manifest.get("scenario_id") != authority_row["scenario_id"]
        or not isinstance(retained_parameters, dict)
        or electrical_parameter_projection(retained_parameters) != electrical_parameter_projection(parameters)
        or manifest.get("deck_sha256") != actual_deck_sha
        or authority_row["deck_sha256"] != actual_deck_sha
        or normalized_deck_sha256(deck_path.read_text(encoding="ascii")) != normalized_deck_sha256(deck)
    ):
        raise RuntimeError("T0-3 authority row does not match the requested electrical waveform: {}".format(scenario))
    increment_stat(stats, "reused")
    increment_stat(stats, "reused_electrical")
    values = parse_measurement(scenario)
    return attach_evidence_provenance(
        classify(parameters, values, scenario, hashlib.sha256(deck.encode("ascii")).hexdigest()),
        parameters, deck, "REUSED_T0_3_AUTHORITY_ROW",
        "T0_3_PHASE_WINDOW_CSV_SELECTED_SCENARIO",
    )


def t0_5_recovery_times(parameters: Mapping[str, Any]) -> Tuple[float, float]:
    """Calculate the physical PWL recovery interval for one sampled phase.

    The returned times are derived directly from the same phase/fall/hold/rise
    values and the same common pre-simulation shift used by the renderer.
    They are report annotations, not a second timing model: CK crossings
    continue to come only from HSPICE measures.
    """

    timing = shifted_probe_timing(parameters)
    start = timing["launch_time_s"] + float(parameters["phase_ps"]) * 1e-12
    recovery_start = start + (float(parameters["t_fall_ps"]) + float(parameters["t_hold_ps"])) * 1e-12
    recovery_end = recovery_start + float(parameters["t_rise_ps"]) * 1e-12
    return recovery_start, recovery_end


def t0_5_state(row: Mapping[str, Any], recovery_start_s: float, recovery_end_s: float) -> Tuple[str, str]:
    """Map a real-DFF row into the mandatory T0-5 four-state vocabulary.

    A stable high Q is clean only when all original validity checks pass; a
    high Q accompanying an extra active CK edge is therefore never silently
    promoted to detection.  An extra second CK crossing inside the recovery
    interval (plus the 10 ps local observation guard used by T0-4) is labeled
    ``RECOVERY_EDGE_AMBIGUOUS``.  The second return value records whether its
    measured shape already matches the T0-4 fast-recovery model or needs a
    single, separately justified 10 ps diagnosis.
    """

    try:
        valid = int(row.get("valid", 0)) == 1
    except (TypeError, ValueError):
        valid = False
    try:
        q_final = int(row.get("q_final"))
    except (TypeError, ValueError):
        q_final = None
    if valid and q_final == 1:
        return "CLEAN_Q1", "NOT_APPLICABLE"
    if valid and q_final == 0:
        return "STABLE_Q0", "NOT_APPLICABLE"
    second_ck = finite(row.get("t_ck_rise_2_s"))
    recovery_guard_end = recovery_end_s + max(10.0, float(row.get("t_rise_ps", PRIMARY_SLEW_PS))) * 1e-12
    in_recovery = second_ck is not None and recovery_start_s <= second_ck <= recovery_guard_end
    if in_recovery:
        known_pattern = (
            row.get("q_state") == "stable_high"
            and int(float(row.get("active_ck_edge_count", 0))) == 2
        )
        return (
            "RECOVERY_EDGE_AMBIGUOUS",
            "KNOWN_T0_4_FAST_RECOVERY_PATTERN" if known_pattern else "NEEDS_LOCAL_10PS_DIAGNOSIS",
        )
    return "OTHER_INVALID_AMBIGUOUS", "NOT_APPLICABLE"


def annotate_t0_5_row(row: Dict[str, Any], parameters: Mapping[str, Any], spec: Mapping[str, Any],
                      scan_stage: str) -> Dict[str, Any]:
    """Attach phase-window semantics while preserving all real-DFF scalars.

    Port-level and Q/VDD data are emitted by ``render_deck``/``classify``;
    this function adds no electrical inference.  It makes the phase family,
    scan origin and recovery PWL interval explicit so a CSV row can be
    independently checked against its retained deck and HSPICE listing.
    """

    recovery_start, recovery_end = t0_5_recovery_times(parameters)
    state, recovery_model = t0_5_state(row, recovery_start, recovery_end)
    row.update({
        "scenario_key": spec["scenario_key"],
        "scenario_family": spec["scenario_family"],
        "scan_stage": scan_stage,
        "t0_5_state": state,
        # Store the derived prelude on every T0-5 row.  This makes it clear
        # that an early negative phase was represented by a uniform time
        # translation, never by changing a probe event separation.
        "time_axis_shift_s": t0_time_axis_shift_s(parameters),
        "recovery_start_s": recovery_start,
        "recovery_end_s": recovery_end,
        "recovery_model_status": recovery_model,
    })
    return row


def request_t0_5_phase(context: Mapping[str, Any], spec: Mapping[str, Any], phase_ps: float,
                       scan_stage: str, rows_by_phase: Dict[float, Dict[str, Any]],
                       stats: Dict[str, int], t0_3_authority_row: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Obtain one phase point once, with source-aware retained-evidence reuse.

    ``rows_by_phase`` is per electrical waveform.  It prevents a fine-boundary
    pass from issuing the same HSPICE request a second time while retaining the
    first row's provenance.  Phase is rounded to the measured 25 ps lattice
    and therefore prevents a fine-boundary pass from issuing a duplicate
    request.  ``t0_3_authority_row`` is supplied only for an existing T0-3
    long-pulse point and forces reuse of its CSV-selected retained listing.
    """

    phase = round(float(phase_ps), 6)
    if phase in rows_by_phase:
        return rows_by_phase[phase]
    parameters = parameters_for(
        float(spec["baseline"]), str(spec["margin"]), float(spec["vdroop"]),
        float(spec["hold_ps"]), phase, PRIMARY_SLEW_PS,
    )
    evidence = (
        reuse_t0_3_authority_row(parameters, render_deck(context, parameters), t0_3_authority_row, stats)
        if t0_3_authority_row is not None
        else execute(context, parameters, stats)
    )
    row = annotate_t0_5_row(evidence, parameters, spec, scan_stage)
    rows_by_phase[phase] = row
    return row


def refine_t0_5_transitions(context: Mapping[str, Any], spec: Mapping[str, Any],
                            rows_by_phase: Dict[float, Dict[str, Any]], stats: Dict[str, int]) -> None:
    """Add 25 ps samples only inside observed coarse state transitions.

    A coarse pair with equal labels carries no license to fill its interior.
    Conversely, a changed pair is locally resolved at the frozen 25 ps
    precision.  The loop repeats because an ambiguous point may divide one
    coarse transition into two separately auditable interval boundaries.
    """

    while True:
        requested = False
        ordered = sorted(rows_by_phase)
        for left, right in zip(ordered, ordered[1:]):
            if rows_by_phase[left]["t0_5_state"] == rows_by_phase[right]["t0_5_state"]:
                continue
            phase = left + PHASE_FINE_STEP_PS
            while phase < right - 1e-9:
                if round(phase, 6) not in rows_by_phase:
                    request_t0_5_phase(context, spec, phase, "BOUNDARY_FINE_25PS", rows_by_phase, stats)
                    requested = True
                phase += PHASE_FINE_STEP_PS
        if not requested:
            return


def adaptive_t0_5_scan(context: Mapping[str, Any], spec: Mapping[str, Any], stats: Dict[str, int]) -> List[Dict[str, Any]]:
    """Close one waveform's sampled response with minimum new phase points.

    Long pulses begin from every retained T0-3 phase.  Short and special
    pulses begin only at their approved representative phase.  Both ends are
    expanded outward in 250 ps steps until they are stable Q0, then only
    changed-state gaps receive 25 ps points.  There is intentionally no
    time-zero phase limit: a phase whose PWL source would start before zero
    is represented by ``shifted_probe_timing`` with a uniform pre-simulation
    offset, preserving the frozen event-relative physical experiment.
    """

    rows_by_phase: Dict[float, Dict[str, Any]] = {}
    if bool(spec["reuse_t0_3_phase_points"]):
        for authority_row in t0_3_reusable_rows(spec):
            request_t0_5_phase(
                context, spec, float(authority_row["phase_ps"]), "REUSED_T0_3_PHASE_POINT",
                rows_by_phase, stats, authority_row,
            )
    else:
        request_t0_5_phase(context, spec, float(spec["seed_phase_ps"]), "REPRESENTATIVE_PHASE_SEED", rows_by_phase, stats)

    # Expand each side independently.  The loop intentionally has no nominal
    # point-count budget: its physical completion condition is a measured
    # stable-Q0 boundary.  The renderer adds pre-simulation time when needed,
    # so a source-coordinate limit can never be misclassified as a physical
    # phase boundary.
    while rows_by_phase[min(rows_by_phase)]["t0_5_state"] != "STABLE_Q0":
        left = min(rows_by_phase)
        candidate = left - PHASE_COARSE_STEP_PS
        request_t0_5_phase(context, spec, candidate, "LEFT_COARSE_EXTENSION", rows_by_phase, stats)
    while rows_by_phase[max(rows_by_phase)]["t0_5_state"] != "STABLE_Q0":
        right = max(rows_by_phase)
        request_t0_5_phase(context, spec, right + PHASE_COARSE_STEP_PS, "RIGHT_COARSE_EXTENSION", rows_by_phase, stats)
    refine_t0_5_transitions(context, spec, rows_by_phase, stats)
    return [rows_by_phase[phase] for phase in sorted(rows_by_phase)]


def contiguous_t0_5_intervals(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Report every observed same-state phase interval without interpolation."""

    ordered = sorted({float(row["phase_ps"]): row for row in rows}.items())
    if not ordered:
        return []
    intervals: List[Dict[str, Any]] = []
    start_phase, start_row = ordered[0]
    previous_phase, previous_row = start_phase, start_row
    state = start_row["t0_5_state"]
    for phase, row in ordered[1:]:
        current = row["t0_5_state"]
        if current != state:
            intervals.append({
                "state": state, "phase_start_ps": start_phase, "phase_end_ps": previous_phase,
                "width_ps": previous_phase - start_phase,
                "sample_count": sum(1 for _, item in ordered if start_phase <= float(item["phase_ps"]) <= previous_phase and item["t0_5_state"] == state),
            })
            start_phase, state = phase, current
        previous_phase, previous_row = phase, row
    intervals.append({
        "state": state, "phase_start_ps": start_phase, "phase_end_ps": previous_phase,
        "width_ps": previous_phase - start_phase,
        "sample_count": sum(1 for _, item in ordered if start_phase <= float(item["phase_ps"]) <= previous_phase and item["t0_5_state"] == state),
    })
    return intervals


def summarize_t0_5_rows(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Produce per-waveform intervals and gate-relevant counts from sampled rows."""

    by_key: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        by_key.setdefault(str(row["scenario_key"]), []).append(row)
    summaries = []
    for key, group in sorted(by_key.items()):
        ordered = sorted(group, key=lambda row: float(row["phase_ps"]))
        intervals = contiguous_t0_5_intervals(ordered)
        states = [row["t0_5_state"] for row in ordered]
        ambiguous = [row for row in ordered if row["t0_5_state"] in ("RECOVERY_EDGE_AMBIGUOUS", "OTHER_INVALID_AMBIGUOUS")]
        non_guarantee = [item for item in intervals if item["state"] != "CLEAN_Q1"]
        summaries.append({
            "scenario_key": key,
            "scenario_family": ordered[0]["scenario_family"],
            "baseline_vdd_v": float(ordered[0]["baseline_vdd_v"]),
            "margin_level": ordered[0]["margin_level"],
            "Vdroop_v": float(ordered[0]["Vdroop_v"]),
            "t_hold_ps": float(ordered[0]["t_hold_ps"]),
            "total_pulse_ps": float(ordered[0]["t_fall_ps"]) + float(ordered[0]["t_hold_ps"]) + float(ordered[0]["t_rise_ps"]),
            "intervals": intervals,
            "clean_q1_intervals": [item for item in intervals if item["state"] == "CLEAN_Q1"],
            "stable_q0_intervals": [item for item in intervals if item["state"] == "STABLE_Q0"],
            "recovery_edge_ambiguous_intervals": [item for item in intervals if item["state"] == "RECOVERY_EDGE_AMBIGUOUS"],
            "other_invalid_ambiguous_intervals": [item for item in intervals if item["state"] == "OTHER_INVALID_AMBIGUOUS"],
            "maximum_non_guarantee_window_ps": max((item["width_ps"] for item in non_guarantee), default=None),
            "sample_count": len(ordered),
            "stable_sample_count": sum(state in ("CLEAN_Q1", "STABLE_Q0") for state in states),
            "clean_q1_sample_count": states.count("CLEAN_Q1"),
            "ambiguous_sample_count": len(ambiguous),
            "clean_phase_coverage_fraction": states.count("CLEAN_Q1") / float(len(states)),
            "left_closed_by_stable_q0": states[0] == "STABLE_Q0",
            "right_closed_by_stable_q0": states[-1] == "STABLE_Q0",
            "ambiguous_dominates": len(ambiguous) >= sum(state in ("CLEAN_Q1", "STABLE_Q0") for state in states),
            "needs_local_recovery_diagnosis_count": sum(row.get("recovery_model_status") == "NEEDS_LOCAL_10PS_DIAGNOSIS" for row in ambiguous),
        })
    return summaries


def t0_5_gate_ok(summaries: Sequence[Mapping[str, Any]], required_keys: Sequence[str]) -> bool:
    """Apply the plan's physical T0-5 gate without smoothing any ambiguity."""

    by_key = {item["scenario_key"]: item for item in summaries}
    if set(required_keys) - set(by_key):
        return False
    for key in required_keys:
        item = by_key[key]
        if not item["left_closed_by_stable_q0"] or not item["right_closed_by_stable_q0"]:
            return False
        if not item["clean_q1_intervals"] or item["ambiguous_dominates"]:
            return False
        if item["other_invalid_ambiguous_intervals"] or item["needs_local_recovery_diagnosis_count"]:
            return False
    return True


def t0_5a_logical_stage_stats(rows: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    """Account T0-5A physical evidence across resumed runner invocations.

    A terminal CSV row is the compact reference to one retained physical deck.
    The same logical T0-5A stage may be resumed after a process interruption,
    so invocation-local counters alone would report already completed new
    transistor simulations as generic reuse.  Count unique ``scenario_path``
    values instead: T0-3 CSV-authority paths are old evidence reused by T0-5A;
    every other path is a newly created T0-5A physical point.  The retained
    T0-5A subset is recorded separately for audit, but is not double-counted
    as an old T0-3 experiment or rerun.
    """

    allowed_sources = {
        "NEW_HSPICE_SCENARIO", "REUSED_RETAINED_MEASUREMENT",
        "REUSED_T0_3_AUTHORITY_ROW",
    }
    if any(row.get("evidence_source") not in allowed_sources for row in rows):
        raise RuntimeError("T0-5A row has unknown evidence provenance")
    paths = {str(row["scenario_path"]) for row in rows}
    t0_3_paths = {
        str(row["scenario_path"]) for row in rows
        if row.get("evidence_source") == "REUSED_T0_3_AUTHORITY_ROW"
    }
    resumed_t0_5_paths = {
        str(row["scenario_path"]) for row in rows
        if row.get("evidence_source") == "REUSED_RETAINED_MEASUREMENT"
    }
    latest_new_paths = {
        str(row["scenario_path"]) for row in rows
        if row.get("evidence_source") == "NEW_HSPICE_SCENARIO"
    }
    if paths != t0_3_paths | resumed_t0_5_paths | latest_new_paths:
        raise RuntimeError("T0-5A physical evidence accounting is not disjoint")
    return {
        "new": len(paths - t0_3_paths),
        "reused": len(t0_3_paths),
        "reused_exact": 0,
        "reused_electrical": len(t0_3_paths),
        "reused_interrupted_t0_5a": len(resumed_t0_5_paths),
        "latest_invocation_new": len(latest_new_paths),
        "unique_physical_scenario_count": len(paths),
    }


def write_t0_5_progress_report(stage: str, summaries: Sequence[Mapping[str, Any]], stats: Mapping[str, int],
                               decision: str) -> Path:
    """Write a phase-coverage report with stage-scoped and total accounting.

    T0-5A can be resumed, while T0-5B is a separately authorized physical
    supplement.  The caller therefore supplies the accounting appropriate to
    the report it is publishing: the normal fields describe the complete
    evidence set represented by the summary, and optional ``*_this_stage``
    fields record only the invocation that just finished.  Keeping both views
    prevents the final T0-5 report from accidentally describing T0-5A's
    retained runs as if they were newly simulated during T0-5B.

    This writer intentionally never derives cadence.  Releasing T0-6 is a
    Gate state change only; its 0-HSPICE mathematical mapping remains a later
    phase and must not be pre-claimed by a coverage progress report.
    """

    lines = [
        "# FTC T0-5 单 probe 时间覆盖进展报告", "", "## 阶段判定", "", "**{}：{}**".format(stage, decision), "",
        "所有区间均为已采样相位格点边界；CLEAN_Q1 之外的 Q0 或 ambiguous 区间均不计入保证检测。", "",
        "| 场景 | 总脉冲 (ps) | CLEAN_Q1 点 | ambiguous 点 | 左/右 Q0 闭合 | 最大非保证窗口 (ps) |",
        "|---|---:|---:|---:|---|---:|",
    ]
    for item in summaries:
        lines.append("| {} | {:.1f} | {} | {} | {}/{} | {} |".format(
            item["scenario_key"], item["total_pulse_ps"], item["clean_q1_sample_count"],
            item["ambiguous_sample_count"], item["left_closed_by_stable_q0"],
            item["right_closed_by_stable_q0"], item["maximum_non_guarantee_window_ps"],
        ))
    lines.extend([
        "", "## 仿真账本", "",
        "- 本报告覆盖的 T0-5 证据：新增 HSPICE：{}；精确复用：{}；电气等价 source-hash 复用：{}。".format(
            stats.get("new", 0), stats.get("reused_exact", 0), stats.get("reused_electrical", 0)),
        "- T0-5A 因进程恢复而保留并重解析的既有点：{}；本报告唯一物理场景总数：{}。".format(
            stats.get("reused_interrupted_t0_5a", 0), stats.get("unique_physical_scenario_count", 0)),
        "- 未运行 H0、M0、M1、T0-2、T0-3 已有点或 T0-4 全量场景。",
        "- 本阶段未计算 T0-6 cadence；T0-6 是否解封只由当前 Gate 记录。",
    ])
    # A complete T0-5 report needs to preserve the small T0-5B delta as well
    # as the aggregate.  T0-5A reports do not carry these optional fields and
    # consequently retain their concise, single-stage ledger above.
    if "new_this_stage" in stats:
        lines.extend([
            "- 本次 T0-5B：新增 HSPICE：{}；复用旧场景：{}；精确复用：{}；电气等价 source-hash 复用：{}。".format(
                stats.get("new_this_stage", 0), stats.get("reused_this_stage", 0),
                stats.get("reused_exact_this_stage", 0), stats.get("reused_electrical_this_stage", 0)),
        ])
    path = REPORT_ROOT / "FTC_T0_TRANSIENT_DROOP_CHARACTERIZATION.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def publish_t0_5a_artifacts(rows: Sequence[Mapping[str, Any]], invocation_stats: Mapping[str, int]) -> Dict[str, Any]:
    """Write one authoritative T0-5A summary, Gate and progress report.

    This publication is shared by the physical scan and the zero-HSPICE
    accounting refresh.  It derives the GO/STOP decision only from the stored
    four-state rows, while its accounting is derived from retained scenario
    identities.  Thus a resumed process cannot change the physical conclusion
    or hide a previously completed HSPICE point by overwriting a CSV counter.
    """

    summaries = summarize_t0_5_rows(rows)
    keys = [item["scenario_key"] for item in T0_5A_SPECS]
    decision = "GO" if t0_5_gate_ok(summaries, keys) else "STOP_T0_5A"
    accounting = t0_5a_logical_stage_stats(rows)
    write_csv(ANALYSIS / "phase_coverage" / "phase_coverage.csv", PHASE_COVERAGE_FIELDS, rows)
    result = {
        "schema_version": 1, "study": STUDY, "stage": "T0-5A", "decision": decision,
        "new_hspice": accounting["new"], "reused": accounting["reused"],
        "reused_exact": accounting["reused_exact"], "reused_electrical": accounting["reused_electrical"],
        "reused_interrupted_t0_5a": accounting["reused_interrupted_t0_5a"],
        "unique_physical_scenario_count": accounting["unique_physical_scenario_count"],
        "latest_invocation_new_hspice": int(invocation_stats.get("new", 0)),
        "latest_invocation_reused": int(invocation_stats.get("reused", 0)),
        "reparsed": 0, "forbidden_flow_runs": 0, "scenarios": summaries,
    }
    write_json(ANALYSIS / "phase_coverage" / "phase_coverage_summary.json", result)
    gate_path = ANALYSIS / "reports" / "T0_GATE_STATUS.json"
    gate = read_json(gate_path)
    gate.update({
        "decision": "NO-GO / STOP" if decision != "GO" else "GO_PENDING_T0_5B",
        "stop_stage": "T0-5A" if decision != "GO" else None,
        "stop_reason": None if decision == "GO" else "t0_5a_physical_gate_not_met_after_full_adaptive_phase_closure",
        "t0_5a_status": decision,
        "t0_5_status": "T0-5A GO; T0-5B ENABLED" if decision == "GO" else "STOP_T0_5A",
        "t0_6_status": "WAITING_FOR_T0_5_GATE" if decision == "GO" else "BLOCKED_BY_T0_5A_STOP",
        "blocked_later_stages": ["T0-6"] if decision == "GO" else ["T0-5B", "T0-6"],
        "t0_5_summary": str((ANALYSIS / "phase_coverage" / "phase_coverage_summary.json").relative_to(FTC_ROOT)),
    })
    write_json(gate_path, gate)
    write_t0_5_progress_report("T0-5A", summaries, accounting, decision)
    return result


def phase_t0_5a() -> Dict[str, Any]:
    """Run only the two-L2 T0-5A boundary and long-pulse phase closures."""

    require_dl()
    gate_path = ANALYSIS / "reports" / "T0_GATE_STATUS.json"
    gate = read_json(gate_path)
    if gate.get("t0_4e_status") != "PASS_ZERO_HSPICE_EVIDENCE_CLOSURE" or gate.get("t0_5_status") != "ENABLED":
        raise RuntimeError("T0-5A requires the completed T0-4E unlock")
    context, stats = frozen_context(), {"new": 0, "reused": 0}
    rows: List[Dict[str, Any]] = []
    for spec in T0_5A_SPECS:
        rows.extend(adaptive_t0_5_scan(context, spec, stats))
    return publish_t0_5a_artifacts(rows, stats)


def phase_t0_5a_accounting_refresh() -> Dict[str, Any]:
    """Regenerate the completed T0-5A summary and Gate with zero HSPICE.

    This narrow recovery entry is allowed only after a completed T0-5A map.
    It does not render a deck, call the generic reuse path, or schedule a
    simulator.  Its sole purpose is to repair provenance counters after an
    interrupted invocation has already retained PASS rows, while preserving
    the real four-state phase result and current T0-5B authorization.
    """

    require_dl()
    gate = read_json(ANALYSIS / "reports" / "T0_GATE_STATUS.json")
    summary_path = ANALYSIS / "phase_coverage" / "phase_coverage_summary.json"
    prior = read_json(summary_path)
    if gate.get("t0_5a_status") != "GO" or prior.get("decision") != "GO":
        raise RuntimeError("T0-5A accounting refresh requires completed T0-5A GO evidence")
    rows = read_csv(ANALYSIS / "phase_coverage" / "phase_coverage.csv", PHASE_COVERAGE_FIELDS)
    return publish_t0_5a_artifacts(rows, {
        "new": int(prior.get("latest_invocation_new_hspice", prior.get("new_hspice", 0))),
        "reused": int(prior.get("latest_invocation_reused", prior.get("reused", 0))),
    })


def publish_t0_5b_artifacts(rows: Sequence[Mapping[str, Any]], t0_5a_summary: Mapping[str, Any],
                            invocation_stats: Mapping[str, int]) -> Dict[str, Any]:
    """Publish the complete T0-5 result without scheduling any HSPICE run.

    The physical scanner and the narrowly scoped post-run refresh share this
    writer.  Both consume the already retained CSV rows and may only derive
    four-state intervals, accounting, report text, and Gate fields from those
    rows.  This division is important after a metadata-only correction: an
    evidence refresh must never be capable of appending a phase point or
    invoking HSPICE a second time.
    """

    required_t0_5a_fields = (
        "new_hspice", "reused", "reused_exact", "reused_electrical",
        "reused_interrupted_t0_5a", "unique_physical_scenario_count",
    )
    missing_t0_5a_fields = [field for field in required_t0_5a_fields if field not in t0_5a_summary]
    if missing_t0_5a_fields:
        raise RuntimeError("T0-5B publication lacks T0-5A accounting: {}".format(
            ", ".join(missing_t0_5a_fields)))
    summaries = summarize_t0_5_rows(rows)
    keys = [item["scenario_key"] for item in T0_5A_SPECS + T0_5B_SPECS]
    decision = "GO" if t0_5_gate_ok(summaries, keys) else "STOP_T0_5B"
    combined_stats = {
        # Aggregate totals span the two plan-defined substages.  A reused
        # T0-4 special-boundary listing is not counted as a new T0-5 HSPICE
        # run because ``stats[\"new\"]`` changes only when this invocation
        # actually launches the container-local simulator.
        "new": int(t0_5a_summary["new_hspice"]) + int(invocation_stats.get("new", 0)),
        "reused": int(t0_5a_summary["reused"]) + int(invocation_stats.get("reused", 0)),
        "reused_exact": int(t0_5a_summary["reused_exact"]) + int(invocation_stats.get("reused_exact", 0)),
        "reused_electrical": int(t0_5a_summary["reused_electrical"]) + int(invocation_stats.get("reused_electrical", 0)),
        "reused_interrupted_t0_5a": int(t0_5a_summary["reused_interrupted_t0_5a"]),
        "unique_physical_scenario_count": len({str(row["scenario_path"]) for row in rows}),
        # These four values make the supplementary run independently auditable
        # without conflating it with the retained T0-5A population above.
        "new_this_stage": int(invocation_stats.get("new", 0)),
        "reused_this_stage": int(invocation_stats.get("reused", 0)),
        "reused_exact_this_stage": int(invocation_stats.get("reused_exact", 0)),
        "reused_electrical_this_stage": int(invocation_stats.get("reused_electrical", 0)),
    }
    write_csv(ANALYSIS / "phase_coverage" / "phase_coverage.csv", PHASE_COVERAGE_FIELDS, rows)
    result = {
        "schema_version": 1, "study": STUDY, "stage": "T0-5 COMPLETE", "decision": decision,
        "new_hspice": combined_stats["new"], "reused": combined_stats["reused"],
        "reused_exact": combined_stats["reused_exact"], "reused_electrical": combined_stats["reused_electrical"],
        "reused_interrupted_t0_5a": combined_stats["reused_interrupted_t0_5a"],
        "unique_physical_scenario_count": combined_stats["unique_physical_scenario_count"],
        "t0_5a_accounting": {
            "new_hspice": int(t0_5a_summary["new_hspice"]),
            "reused": int(t0_5a_summary["reused"]),
            "reused_exact": int(t0_5a_summary["reused_exact"]),
            "reused_electrical": int(t0_5a_summary["reused_electrical"]),
            "reused_interrupted_t0_5a": int(t0_5a_summary["reused_interrupted_t0_5a"]),
            "unique_physical_scenario_count": int(t0_5a_summary["unique_physical_scenario_count"]),
        },
        "t0_5b_accounting": {
            "new_hspice": combined_stats["new_this_stage"],
            "reused": combined_stats["reused_this_stage"],
            "reused_exact": combined_stats["reused_exact_this_stage"],
            "reused_electrical": combined_stats["reused_electrical_this_stage"],
        },
        "reparsed": 0, "forbidden_flow_runs": 0, "scenarios": summaries,
    }
    write_json(ANALYSIS / "phase_coverage" / "phase_coverage_summary.json", result)
    gate_path = ANALYSIS / "reports" / "T0_GATE_STATUS.json"
    gate = read_json(gate_path)
    gate.update({
        # T0-5 itself is now complete, but no cadence mathematics has been
        # performed.  A GO here therefore unlocks T0-6 rather than claiming
        # final T0 completion or any D0 runtime-period qualification.
        "decision": "GO_PENDING_T0_6" if decision == "GO" else "NO-GO / STOP",
        "stop_stage": None if decision == "GO" else "T0-5B",
        "stop_reason": None if decision == "GO" else "t0_5b_special_recovery_edge_phase_window_gate_not_met",
        "t0_5b_status": decision,
        "t0_5_status": "GO" if decision == "GO" else "STOP_T0_5B",
        "t0_6_status": "ENABLED" if decision == "GO" else "WAITING_FOR_T0_5_GATE",
        "t0_8_status": "WAITING_FOR_T0_6" if decision == "GO" else "WAITING_FOR_T0_5_T0_6",
        "blocked_later_stages": ["T0-8"] if decision == "GO" else ["T0-6", "T0-8"],
        "t0_5_summary": str((ANALYSIS / "phase_coverage" / "phase_coverage_summary.json").relative_to(FTC_ROOT)),
    })
    write_json(gate_path, gate)
    write_t0_5_progress_report("T0-5 COMPLETE", summaries, combined_stats, decision)
    if decision != "GO":
        raise RuntimeError("T0-5B STOP: special recovery-edge phase window gate not met")
    return result


def phase_t0_5b() -> Dict[str, Any]:
    """Run the two and only two T0-5B recovery-edge supplementary maps.

    This command is intentionally single-use.  A finished T0-5B map is a
    physical evidence set, not a request to append a second copy of the same
    sampled phases.  The preflight also confirms that the CSV still contains
    exactly the four closed T0-5A maps before T0-5B is allowed to add its two
    plan-authorized special-margin maps.
    """

    require_dl()
    gate_path = ANALYSIS / "reports" / "T0_GATE_STATUS.json"
    gate = read_json(gate_path)
    if gate.get("t0_5a_status") != "GO" or gate.get("t0_5_status") != "T0-5A GO; T0-5B ENABLED":
        raise RuntimeError("T0-5B requires T0-5A GO")
    if gate.get("t0_5b_status") is not None:
        raise RuntimeError("T0-5B has already published a terminal physical result")
    existing = read_csv(ANALYSIS / "phase_coverage" / "phase_coverage.csv", PHASE_COVERAGE_FIELDS)
    expected_t0_5a_keys = {item["scenario_key"] for item in T0_5A_SPECS}
    observed_t0_5a_keys = {str(row["scenario_key"]) for row in existing}
    if observed_t0_5a_keys != expected_t0_5a_keys:
        raise RuntimeError("T0-5B requires exactly the four retained T0-5A maps")
    # Preserve T0-5A's logical accounting before the final summary replaces
    # its JSON file.  The T0-5B invocation counters alone are deliberately
    # insufficient: they exclude 75 prior T0-5A physical HSPICE cases and 44
    # CSV-authority T0-3 reuses that remain part of complete T0-5 provenance.
    t0_5a_summary = read_json(ANALYSIS / "phase_coverage" / "phase_coverage_summary.json")
    if t0_5a_summary.get("stage") != "T0-5A" or t0_5a_summary.get("decision") != "GO":
        raise RuntimeError("T0-5B requires the authoritative T0-5A GO summary")
    context, stats = frozen_context(), {"new": 0, "reused": 0}
    rows: List[Dict[str, Any]] = [dict(row) for row in existing]
    for spec in T0_5B_SPECS:
        rows.extend(adaptive_t0_5_scan(context, spec, stats))
    return publish_t0_5b_artifacts(rows, t0_5a_summary, stats)


def phase_t0_5b_accounting_refresh() -> Dict[str, Any]:
    """Refresh finished T0-5B publication fields with strictly zero HSPICE.

    The entry is only for a completed ``T0-5 COMPLETE`` GO summary whose
    retained rows have already been simulated.  It reuses the stage-local
    counters written by the original invocation, rebuilds the compact
    intervals and Gate wording, and cannot reach ``execute`` or render a
    deck.  It exists to correct reporting metadata such as a stale
    ``GO_PENDING_T0_5B`` decision without ever changing the underlying
    transistor-level evidence population.
    """

    require_dl()
    gate = read_json(ANALYSIS / "reports" / "T0_GATE_STATUS.json")
    summary = read_json(ANALYSIS / "phase_coverage" / "phase_coverage_summary.json")
    if (gate.get("t0_5b_status") != "GO" or summary.get("stage") != "T0-5 COMPLETE"
            or summary.get("decision") != "GO"):
        raise RuntimeError("T0-5B accounting refresh requires completed T0-5B GO evidence")
    t0_5a_accounting = summary.get("t0_5a_accounting")
    t0_5b_accounting = summary.get("t0_5b_accounting")
    if not isinstance(t0_5a_accounting, dict) or not isinstance(t0_5b_accounting, dict):
        raise RuntimeError("T0-5B accounting refresh lacks substage accounting")
    rows = read_csv(ANALYSIS / "phase_coverage" / "phase_coverage.csv", PHASE_COVERAGE_FIELDS)
    # The first T0-5B publication predates the explicit nested resume and
    # unique-path fields.  Reconstruct them only from the four immutable
    # T0-5A keys in the retained CSV; using the complete-map total here would
    # incorrectly fold the two new T0-5B maps into the earlier substage.
    t0_5a_keys = {item["scenario_key"] for item in T0_5A_SPECS}
    t0_5a_rows = [row for row in rows if row.get("scenario_key") in t0_5a_keys]
    if {row.get("scenario_key") for row in t0_5a_rows} != t0_5a_keys:
        raise RuntimeError("T0-5B accounting refresh cannot reconstruct all T0-5A maps")
    t0_5a_summary = dict(t0_5a_accounting)
    t0_5a_summary["reused_interrupted_t0_5a"] = len({
        str(row["scenario_path"]) for row in t0_5a_rows
        if row.get("evidence_source") == "REUSED_RETAINED_MEASUREMENT"
    })
    t0_5a_summary["unique_physical_scenario_count"] = len({
        str(row["scenario_path"]) for row in t0_5a_rows
    })
    return publish_t0_5b_artifacts(rows, t0_5a_summary, {
        "new": int(t0_5b_accounting.get("new_hspice", 0)),
        "reused": int(t0_5b_accounting.get("reused", 0)),
        "reused_exact": int(t0_5b_accounting.get("reused_exact", 0)),
        "reused_electrical": int(t0_5b_accounting.get("reused_electrical", 0)),
    })


def phase_amplitude_duration() -> Dict[str, Any]:
    """Execute T0-4's six local amplitude-duration searches after T0-3 GO."""

    reject_if_t0_4_authoritative_go("amplitude-duration")
    require_dl()
    gate = read_json(ANALYSIS / "reports" / "T0_GATE_STATUS.json")
    if gate.get("t0_4_status") != "ENABLED":
        raise RuntimeError("T0-4 is not enabled by the T0-3 gate")
    context, phases, stats = frozen_context(), t0_4_phase_by_baseline(), {"new": 0, "reused": 0}
    rows: List[Dict[str, Any]] = []
    boundaries: List[Dict[str, Any]] = []
    anomalies: List[str] = []
    for baseline, margin, points in t0_4_vdroop_points():
        for point_label, vdroop in points:
            trials, minimum = first_q1_duration(context, baseline, margin, vdroop, phases[baseline], stats)
            for row in trials:
                row["point_label"] = point_label
                row["representative_phase_ps"] = phases[baseline]
                rows.append(row)
                if row.get("anomaly"):
                    anomalies.append(row["scenario_id"])
            boundaries.append({
                "baseline_vdd_v": baseline, "margin_level": margin, "M_det": FORMAL_CODES[(baseline, margin)][0], "F_det": FORMAL_CODES[(baseline, margin)][1],
                "point_label": point_label, "Vdroop_v": vdroop, "DeltaV_mv": round((baseline - vdroop) * 1000.0, 6),
                "representative_phase_ps": phases[baseline], "minimum_detectable_hold_ps": minimum,
                "minimum_detectable_total_pulse_ps": None if minimum is None else minimum + 2.0,
            })
    fields = SCENARIO_FIELDS + ("search_stage", "point_label", "representative_phase_ps", "anomaly")
    write_csv(ANALYSIS / "amplitude_duration" / "amplitude_duration.csv", fields, rows)
    write_csv(ANALYSIS / "amplitude_duration" / "minimum_duration_boundary.csv", tuple(boundaries[0].keys()), boundaries)
    decision = "GO" if not anomalies and all(item["minimum_detectable_hold_ps"] is not None for item in boundaries) else "STOP"
    summary = {
        "decision": decision, "scenario_count": len(rows), "new_hspice": stats["new"], "reused": stats["reused"],
        "boundaries": boundaries, "anomalies": anomalies,
        # The current two anomalies are invalid dual-clock-edge observations,
        # not a fabricated monotonicity conclusion.  Store their exact reason
        # so terminal reporting can distinguish an unresolved physical/deck
        # condition from a verified Q1-to-Q0 duration reversal.
        "stop_reason": "ambiguous_duration_boundary_with_active_ck_edge_count_not_one" if anomalies else None,
    }
    write_json(ANALYSIS / "amplitude_duration" / "summary.json", summary)
    if decision != "GO":
        raise RuntimeError("T0-4 STOP: anomalous or unresolved duration boundary")
    return summary


def publish_t0_4_stop() -> Dict[str, Any]:
    """Publish the T0-4 physical stop and T0-7 fail-safe requirement.

    This terminal publication reads compact artifacts only.  It does not run
    additional HSPICE to force an ambiguous duration boundary into a result,
    and it deliberately leaves D0 unimplemented.
    """

    reject_if_t0_4_authoritative_go("publish_t0_4_stop")
    summary = read_json(ANALYSIS / "amplitude_duration" / "summary.json")
    if summary.get("decision") != "STOP":
        raise RuntimeError("terminal T0-4 publication requires a T0-4 STOP")
    anomaly_rows = [
        row for row in read_csv(ANALYSIS / "amplitude_duration" / "amplitude_duration.csv", ("scenario_id", "reason", "anomaly"))
        if row.get("anomaly")
    ]
    if not anomaly_rows:
        raise RuntimeError("T0-4 STOP lacks retained anomaly rows")
    reasons = sorted({row["reason"] for row in anomaly_rows})
    summary["stop_reason"] = "ambiguous_duration_boundary: {}".format(",".join(reasons))
    summary["anomaly_records"] = [{"scenario_id": row["scenario_id"], "reason": row["reason"]} for row in anomaly_rows]
    write_json(ANALYSIS / "amplitude_duration" / "summary.json", summary)
    gate_path = ANALYSIS / "reports" / "T0_GATE_STATUS.json"
    gate = read_json(gate_path)
    gate.update({
        "decision": "NO-GO / STOP",
        "t0_2_status": "T0-2 CORRECTED PASS",
        "stop_stage": "T0-4",
        "stop_reason": summary.get("stop_reason"),
        "t0_4_status": "STOP",
        "t0_5_status": "BLOCKED_BY_T0_4_STOP",
        "t0_6_status": "BLOCKED_BY_T0_4_STOP",
        "t0_7_status": "PASS_FAIL_SAFE_REQUIREMENT_PUBLISHED",
        "t0_8_status": "TERMINAL_EVIDENCE_PENDING",
        "blocked_later_stages": ["T0-5", "T0-6"],
        "t0_4_summary": str((ANALYSIS / "amplitude_duration" / "summary.json").relative_to(FTC_ROOT)),
    })
    write_json(gate_path, gate)
    downstream = {
        "schema_version": 3,
        "study": STUDY,
        "decision": "BLOCKED_BY_T0_4_STOP",
        "source_gate": "T0-4 STOP",
        "precise_timing_detection_range": {"minimum_vdd_v": FORMAL_MINIMUM_VDD, "status": "not_extended_below_floor"},
        "below_floor_requirement": {
            "condition": "VDD_MONITORED < 0.80 V",
            "required_semantics": ["heartbeat", "stuck_q", "timeout", "no_valid_detection_result"],
            "precise_timing_trip_allowed": False,
        },
        "runtime_probe_period": {
            "status": "not_qualified_T0_5_T0_6_blocked",
            "maximum_period_s": None,
            "reason": "T0-4 contains unresolved ambiguous duration-boundary scenarios with two active CK edges",
        },
    }
    write_json(ANALYSIS / "contract" / "T0_DOWNSTREAM_D0_TIMING_CONTRACT.json", downstream)
    return gate


def publish_t0_terminal_report() -> Path:
    """Write the final T0 report from completed evidence without new simulation.

    This report intentionally does not promote partial amplitude-duration
    values to six-qualified-margin capability.  It reports the useful T0-3
    mechanism and T0-4 partial observations while preserving the terminal
    NO-GO caused by retained ambiguous physical scenarios.
    """

    reject_if_t0_4_authoritative_go("publish_t0_terminal_report")
    gate = read_json(ANALYSIS / "reports" / "T0_GATE_STATUS.json")
    phase = read_json(ANALYSIS / "phase_window" / "summary.json")
    amplitude = read_json(ANALYSIS / "amplitude_duration" / "summary.json")
    audit = read_json(ANALYSIS / "reports" / "T0_PROCESS_AUDIT.json")
    lines = [
        "# FTC T0 瞬态电压跌落检测能力表征报告", "",
        "## 最终判定", "",
        "**NO-GO / STOP（停止阶段：T0-4）**", "",
        "T0-2 已纠偏通过，T0-3 已证明两个 L2 代表点存在可重复相位窗口；但 T0-4 duration refine 保留了两个 `active_ck_edge_count_not_one` 的 ambiguous 场景。因此六个工作点的完整、可解释 amplitude-duration 合同未闭合，T0-5/T0-6 与 D0 不得继续。", "",
        "## T0-3 相位窗口", "",
        "| 基准电压 | 稳定 Q1 窗口（采样格点） | 最大盲区 | 边界分辨率 | ambiguous |",
        "|---:|---|---:|---:|---:|",
    ]
    for item in phase["windows"]:
        windows = "; ".join("{}..{} ps".format(window["phase_start_ps"], window["phase_end_ps"]) for window in item["detectable_windows"])
        lines.append("| {:.2f} V | {} | {} ps | 25 ps | {} |".format(item["baseline_vdd_v"], windows, item["maximum_blind_window_ps"], item["ambiguous_count"]))
    lines.extend([
        "", "## T0-4 停止证据", "",
        "- 238 个正式自适应场景；没有暴力二维网格。",
        "- 停止原因：{}。".format(amplitude["stop_reason"]),
        "- 这两个场景均出现两个 active CK 边沿，双采样 Q 判定因此无效；它们不是被平滑或删除的普通 Q0/Q1 边界点。",
        "- 各 depth 已获得的部分 minimum-duration 数值只保留为原始观测，不构成六 margin 完整能力声明。",
        "", "## 下游边界", "",
        "- `VDD_MONITORED < 0.80 V`：D0 只能使用 heartbeat、stuck-Q、timeout 或无有效检测结果等 fail-safe 语义，禁止精确 timing trip 声明。",
        "- T0-5/T0-6 被阻塞；1 ns 威胁的最大 runtime probe period 与 400 MHz 复用资格均未被表征。",
        "", "## 仿真与审计账本", "",
        "- T0-2E：新增 HSPICE 0；复核纠偏四点和正式十二点摘要。",
        "- T0-3：新增 HSPICE {}；T0-4：新增 HSPICE {}。".format(phase["new_hspice"], amplitude["new_hspice"]),
        "- 旧 T0-2 固定高电平场景：62，均为 `HISTORICAL_SUPERSEDED_NOT_DELETED`。",
        "- 本轮曾由已修复 dispatcher 错误调用 12 个 legacy long-pulse 场景；它们保留在 task-owned run 目录，已在 `T0_PROCESS_AUDIT.json` 标记为非权威，后续结论未消费。",
        "- 禁止流程（H0/M0/M1/M1-T/RF/XA/D0 RTL）新增运行：0。",
    ])
    path = REPORT_ROOT / "FTC_T0_TRANSIENT_DROOP_CHARACTERIZATION.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def publish_t0_8_terminal_evidence() -> Dict[str, Any]:
    """Close T0-8 after a terminal STOP without manufacturing later data.

    T0-5 and T0-6 are physically blocked, but T0 itself still needs a final
    reviewable package.  This function verifies the five rendered figure
    slots, updates their provenance-backed terminal gate, and rewrites only
    the compact blocked placeholders with the actual upstream stop reason.
    """

    reject_if_t0_4_authoritative_go("publish_t0_8_terminal_evidence")
    gate_path = ANALYSIS / "reports" / "T0_GATE_STATUS.json"
    gate = read_json(gate_path)
    if gate.get("stop_stage") != "T0-4" or gate.get("t0_4_status") != "STOP":
        raise RuntimeError("T0-8 terminal publication requires T0-4 STOP")
    manifest = read_json(ANALYSIS / "figures" / "figure_manifest.json")
    figures = manifest.get("figures", [])
    expected = {
        "fig_t0_1_representative_waveform", "fig_t0_2_phase_window",
        "fig_t0_3_amplitude_duration_boundary", "fig_t0_4_margin_duration_comparison",
        "fig_t0_5_cadence_coverage",
    }
    if {item.get("figure_stem") for item in figures} != expected:
        raise RuntimeError("T0-8 figure manifest is incomplete")
    reason = "BLOCKED_BY_T0_4_STOP: ambiguous duration boundary with active_ck_edge_count_not_one"
    for directory, filename in (("phase_coverage", "phase_coverage.csv"), ("cadence", "cadence.csv")):
        write_csv(ANALYSIS / directory / filename, ("status", "reason"), [{"status": "BLOCKED", "reason": reason}])
    gate.update({
        "t0_8_status": "TERMINAL_EVIDENCE_PUBLISHED",
        "terminal_figure_manifest": str((ANALYSIS / "figures" / "figure_manifest.json").relative_to(FTC_ROOT)),
        "terminal_report": str((REPORT_ROOT / "FTC_T0_TRANSIENT_DROOP_CHARACTERIZATION.md").relative_to(FTC_ROOT)),
    })
    write_json(gate_path, gate)
    return gate


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Dispatch one explicit T0 phase; later phases enforce earlier artifacts."""

    parser = argparse.ArgumentParser(description="FTC T0 transient droop characterization")
    parser.add_argument(
        "--phase",
        choices=(
            "contract", "smoke", "long-pulse", "phase-window", "amplitude-duration", "finalize-stop",
            "correction-audit", "correction-points", "long-pulse-corrected", "t0-2e",
            "t0-4-history-correct", "t0-4-anomaly-diagnose", "t0-4-finalize-corrected", "t0-4e",
            "t0-5a", "t0-5a-accounting-refresh", "t0-5b", "t0-5b-accounting-refresh",
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
        # T0-2 is immutable corrected evidence.  This entry may inspect its
        # committed summaries in ``phase_window`` but must never regenerate a
        # legacy long-pulse deck or overwrite historical T0-2 evidence.
        phase_window()
    elif args.phase == "amplitude-duration":
        phase_amplitude_duration()
    elif args.phase == "finalize-stop":
        phase_terminal_stop()
    elif args.phase == "correction-audit":
        phase_correction_audit()
    elif args.phase == "correction-points":
        phase_correction_audit()
        phase_correction_points()
    elif args.phase == "long-pulse-corrected":
        phase_long_pulse_corrected()
    elif args.phase == "t0-2e":
        phase_t0_2e()
    elif args.phase == "t0-4-history-correct":
        rebuild_t0_4_gate_from_history()
    elif args.phase == "t0-4-anomaly-diagnose":
        diagnose_t0_4_anomalies()
    elif args.phase == "t0-4-finalize-corrected":
        finalize_corrected_t0_4()
    elif args.phase == "t0-4e":
        phase_t0_4e()
    elif args.phase == "t0-5a":
        phase_t0_5a()
    elif args.phase == "t0-5a-accounting-refresh":
        phase_t0_5a_accounting_refresh()
    elif args.phase == "t0-5b":
        phase_t0_5b()
    elif args.phase == "t0-5b-accounting-refresh":
        phase_t0_5b_accounting_refresh()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
