#!/usr/bin/env python3
"""Generate one real-standard-cell, no-DFF differential Vernier SPICE deck.

The generated deck is intentionally limited to ideal-arrival characterization:
it measures every sense/reference tap with both launches present but does not
instantiate the comparator DFF.  The companion analysis applies launch offset
and setup guard to the measured crossings, which is mathematically exact for a
pure launch-time translation and avoids re-simulating identical propagation.
"""

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PHASE2_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Dict[str, Any]:
    """Read a JSON object and make malformed configuration a hard failure."""

    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object: {}".format(path))
    return value


def resolve_repo_path(value: str) -> Path:
    """Resolve phase configuration collateral independently of process CWD."""

    path = Path(value)
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def spice_number(value: float) -> str:
    """Render one finite HSPICE literal in decimal scientific notation."""

    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite SPICE value: {}".format(value))
    return "{:.12e}".format(number)


def load_collateral(config: Dict[str, Any]) -> Dict[str, Any]:
    """Load Phase 1 paths and checked discovery output used by all Phase 2 decks."""

    phase1 = load_json(resolve_repo_path(str(config["phase1_config_path"])))
    discovery_path = PHASE2_ROOT / "discovery" / "selected_cells.json"
    discovery = load_json(discovery_path)
    required_files = [
        resolve_repo_path(str(phase1["cell_cdl"])),
        Path(phase1["model_library"]),
        discovery_path,
    ]
    missing = [str(path) for path in required_files if not path.is_file()]
    if missing:
        raise ValueError("missing Phase 2 collateral: {}".format(", ".join(missing)))
    if discovery["dff"]["cdl_ports"] != ["Q", "VDD", "VNW", "VPW", "VSS", "CK", "D", "R"]:
        raise ValueError("discovery DFF ports no longer match the comparator contract")
    return {"phase1": phase1, "discovery": discovery}


def stage_name(dummy_load_count: int) -> str:
    """Map the configured dummy count to one explicit reference-stage wrapper."""

    if dummy_load_count not in (0, 1, 2, 3):
        raise ValueError("dummy_load_count must be 0, 1, 2, or 3")
    return "PHASE2_REFERENCE_STAGE_D{}".format(dummy_load_count)


def validate_request(config: Dict[str, Any], m_stages: int, dummy_load_count: int, vdd_a_v: float) -> None:
    """Reject requests outside the documented characterization space."""

    if m_stages not in config["comparator_stages"]:
        raise ValueError("m_stages {} is not configured".format(m_stages))
    if dummy_load_count not in config["reference_dummy_load_counts"]:
        raise ValueError("dummy_load_count {} is not configured".format(dummy_load_count))
    if vdd_a_v <= 0.0 or vdd_a_v > float(config["vnom_v"]):
        raise ValueError("VDD_A must be positive and no greater than Vnom")


def render_stage_chain(prefix: str, stage_cell: str, m_stages: int, rail_vdd: str, rail_vss: str, start_node: str) -> List[str]:
    """Unroll one stage chain with a comment for every public stage connection.

    ``prefix`` is ``sense`` or ``ref`` and becomes the stable CSV/timing node
    namespace.  The parent deck is responsible for choosing the rail domain;
    this function never assumes that both chains share a supply.
    """

    lines: List[str] = []
    previous = start_node
    for index in range(m_stages):
        output = "{}_{:03d}".format(prefix, index)
        lines.append(
            "* {} stage {:03d} ports: Y={} VDD={} VSS={} A={}.".format(
                prefix, index, output, rail_vdd, rail_vss, previous
            )
        )
        lines.append(
            "X{}_STAGE_{:03d} {} {} {} {} {}".format(
                prefix.upper(), index, output, rail_vdd, rail_vss, previous, stage_cell
            )
        )
        previous = output
    return lines


def render_ideal_deck(config: Dict[str, Any], m_stages: int, dummy_load_count: int, vdd_a_v: float) -> str:
    """Render the no-DFF arrival deck for one physical M/dummy/voltage point."""

    validate_request(config, m_stages, dummy_load_count, vdd_a_v)
    collateral = load_collateral(config)
    phase1 = collateral["phase1"]
    timing = config["measurement_timing"]
    start_ref_s = float(timing["start_ref_s"])
    tran_stop_s = float(timing.get("tran_stop_s", 4.0e-9))
    if tran_stop_s <= start_ref_s:
        raise ValueError("transient stop must follow the reference launch")

    include_dir = PHASE2_ROOT / "spice"
    sense_include = include_dir / "sense_stage.inc"
    reference_include = include_dir / "reference_stage.inc"
    if not sense_include.is_file() or not reference_include.is_file():
        raise ValueError("required Phase 2 stage include is missing")

    lines = [
        "* Auto-generated SMIC40LL Phase-2 ideal-arrival Vernier deck.",
        "* M={} dummy_load_count={} VDD_A={} V; VDD_REF={} V.".format(
            m_stages, dummy_load_count, spice_number(vdd_a_v), spice_number(float(config["vdd_ref_v"]))
        ),
        "* Arrival experiment: START_SENSE and START_REF launch simultaneously.",
        "* Analysis applies calibrated sense launch offset and setup guard after measured crossing extraction.",
        ".option post=0 nomod measform=3 runlvl=3",
        ".temp {}".format(spice_number(float(config["temperature_c"]))),
        '.include "{}"'.format(resolve_repo_path(str(phase1["cell_cdl"]))),
        '.lib "{}" {}'.format(Path(phase1["model_library"]), str(config["corner"])),
        '.include "{}"'.format(sense_include),
        '.include "{}"'.format(reference_include),
        ".param VDD_A_VALUE={}".format(spice_number(vdd_a_v)),
        ".param VDD_REF_VALUE={}".format(spice_number(float(config["vdd_ref_v"]))),
        "",
        "* Sense rail: local chiplet-A differential domain; no reference source shares this node.",
        "V_VDD_A vdd_a vss_a DC='VDD_A_VALUE'",
        "V_VSS_A vss_a 0 DC=0",
        "* Reference rail: ideal island for this feasibility phase; RC isolation is a later experiment.",
        "V_VDD_REF vdd_ref vss_ref DC='VDD_REF_VALUE'",
        "V_VSS_REF vss_ref 0 DC=0",
        "* Both launches start together so raw crossing differences exclude programmable calibration offset.",
        "V_START_REF start_ref vss_ref PULSE(0 'VDD_REF_VALUE' {} {} {} 1.000000000000e-07 2.000000000000e-07)".format(
            spice_number(start_ref_s), spice_number(float(timing["start_rise_s"])), spice_number(float(timing["start_rise_s"]))
        ),
        "V_START_SENSE start_sense vss_a PULSE(0 'VDD_A_VALUE' {} {} {} 1.000000000000e-07 2.000000000000e-07)".format(
            spice_number(start_ref_s), spice_number(float(timing["start_rise_s"])), spice_number(float(timing["start_rise_s"]))
        ),
        "",
        "* Sense chain is powered only by VDD_A/VSS_A; every output is S_i evidence.",
    ]
    lines.extend(render_stage_chain("sense", "PHASE2_SENSE_STAGE", m_stages, "vdd_a", "vss_a", "start_sense"))
    lines.append("* Reference chain uses the selected standard-cell dummy-input loading at every R_i output.")
    lines.extend(render_stage_chain("ref", stage_name(dummy_load_count), m_stages, "vdd_ref", "vss_ref", "start_ref"))
    lines.extend(
        [
            "",
            ".tran {} {}".format(spice_number(float(timing["tran_max_step_s"])), spice_number(tran_stop_s)),
            "* Crossing thresholds use each chain's own local supply midpoint.",
            ".measure tran start_ref_cross WHEN v(start_ref,vss_ref)='VDD_REF_VALUE/2' RISE=1",
            ".measure tran start_sense_cross WHEN v(start_sense,vss_a)='VDD_A_VALUE/2' RISE=1",
        ]
    )
    for index in range(m_stages):
        lines.append(".measure tran sense_{:03d}_cross WHEN v(sense_{:03d},vss_a)='VDD_A_VALUE/2' RISE=1".format(index, index))
        lines.append(".measure tran ref_{:03d}_cross WHEN v(ref_{:03d},vss_ref)='VDD_REF_VALUE/2' RISE=1".format(index, index))
    lines.extend(
        [
            "* Report each rail separately; the candidate ranking sums these measured supplies.",
            ".measure tran sense_avg_current_a AVG par('-i(V_VDD_A)') FROM={} TO={}".format(spice_number(start_ref_s), spice_number(tran_stop_s)),
            ".measure tran ref_avg_current_a AVG par('-i(V_VDD_REF)') FROM={} TO={}".format(spice_number(start_ref_s), spice_number(tran_stop_s)),
            ".measure tran sense_peak_current_a MAX par('-i(V_VDD_A)') FROM={} TO={}".format(spice_number(start_ref_s), spice_number(tran_stop_s)),
            ".measure tran ref_peak_current_a MAX par('-i(V_VDD_REF)') FROM={} TO={}".format(spice_number(start_ref_s), spice_number(tran_stop_s)),
            ".end",
            "",
        ]
    )
    return "\n".join(lines)


def render_dff_deck(
    config: Dict[str, Any], m_stages: int, dummy_load_count: int, vdd_a_v: float, launch_offset_s: float
) -> str:
    """Render a complete reset/launch/capture deck with real DFF comparators.

    Port ownership is intentionally visible in every generated instance:
    ``S_i`` drives the D terminal across the tested voltage-domain boundary,
    ``R_i`` drives the positive-edge CK terminal, and all DFF supply/well pins
    remain on the reference domain.  The launch offset is a positive delay on
    the sense PULSE, matching the calibrated Vernier definition.
    """

    validate_request(config, m_stages, dummy_load_count, vdd_a_v)
    if launch_offset_s < 0.0:
        raise ValueError("real DFF deck requires a nonnegative sense launch offset")
    collateral = load_collateral(config)
    phase1 = collateral["phase1"]
    timing = config["measurement_timing"]
    start_ref_s = float(timing["start_ref_s"])
    start_sense_s = start_ref_s + launch_offset_s
    capture_time_s = float(timing["dff_capture_time_s"])
    tran_stop_s = float(timing["tran_stop_s"])
    if capture_time_s <= start_sense_s or tran_stop_s <= capture_time_s:
        raise ValueError("DFF capture and transient-stop times must follow the sense launch")
    include_dir = PHASE2_ROOT / "spice"
    required_includes = [include_dir / "sense_stage.inc", include_dir / "reference_stage.inc", include_dir / "comparator_bank.inc"]
    if any(not path.is_file() for path in required_includes):
        raise ValueError("required Phase 2 DFF include is missing")

    lines = [
        "* Auto-generated SMIC40LL Phase-2 real-DFF Vernier deck.",
        "* M={} dummy_load_count={} VDD_A={} V launch_offset={} s.".format(
            m_stages, dummy_load_count, spice_number(vdd_a_v), spice_number(launch_offset_s)
        ),
        "* DFF port contract is declared in comparator_bank.inc and verified by discovery output.",
        ".option post=0 nomod measform=3 runlvl=3",
        ".temp {}".format(spice_number(float(config["temperature_c"]))),
        '.include "{}"'.format(resolve_repo_path(str(phase1["cell_cdl"]))),
        '.lib "{}" {}'.format(Path(phase1["model_library"]), str(config["corner"])),
        '.include "{}"'.format(required_includes[0]),
        '.include "{}"'.format(required_includes[1]),
        '.include "{}"'.format(required_includes[2]),
        ".param VDD_A_VALUE={}".format(spice_number(vdd_a_v)),
        ".param VDD_REF_VALUE={}".format(spice_number(float(config["vdd_ref_v"]))),
        "",
        "* Independent local sense and reference rails; only tested D inputs cross between them.",
        "V_VDD_A vdd_a vss_a DC='VDD_A_VALUE'",
        "V_VSS_A vss_a 0 DC=0",
        "V_VDD_REF vdd_ref vss_ref DC='VDD_REF_VALUE'",
        "V_VSS_REF vss_ref 0 DC=0",
        "* Active-high reset holds every DFF clear through ARM, then releases before either launch.",
        "V_SENSOR_RESET sensor_reset vss_ref PWL(0 'VDD_REF_VALUE' {} 'VDD_REF_VALUE' {} 0 {} 0)".format(
            spice_number(float(timing["dff_reset_release_s"])),
            spice_number(float(timing["dff_reset_release_s"]) + float(timing["start_rise_s"])),
            spice_number(tran_stop_s),
        ),
        "* Reference launch defines R_i timing; sense launch is delayed by the selected calibration offset.",
        "V_START_REF start_ref vss_ref PULSE(0 'VDD_REF_VALUE' {} {} {} 1.000000000000e-07 2.000000000000e-07)".format(
            spice_number(start_ref_s), spice_number(float(timing["start_rise_s"])), spice_number(float(timing["start_rise_s"]))
        ),
        "V_START_SENSE start_sense vss_a PULSE(0 'VDD_A_VALUE' {} {} {} 1.000000000000e-07 2.000000000000e-07)".format(
            spice_number(start_sense_s), spice_number(float(timing["start_rise_s"])), spice_number(float(timing["start_rise_s"]))
        ),
        "",
        "* S_i chain: each stage uses chiplet-A rails exclusively.",
    ]
    lines.extend(render_stage_chain("sense", "PHASE2_SENSE_STAGE", m_stages, "vdd_a", "vss_a", "start_sense"))
    lines.append("* R_i chain: each stage and dummy input load uses reference rails exclusively.")
    lines.extend(render_stage_chain("ref", stage_name(dummy_load_count), m_stages, "vdd_ref", "vss_ref", "start_ref"))
    lines.append("* Comparator bank: D=S_i, CK=R_i, R=sensor_reset, Q=raw_q_i.")
    for index in range(m_stages):
        lines.append(
            "XCOMP_{:03d} raw_q_{:03d} vdd_ref vss_ref sense_{:03d} ref_{:03d} sensor_reset PHASE2_COMPARATOR".format(
                index, index, index, index
            )
        )
    lines.extend(
        [
            "",
            ".tran {} {}".format(spice_number(float(timing["tran_max_step_s"])), spice_number(tran_stop_s)),
            ".measure tran start_ref_cross WHEN v(start_ref,vss_ref)='VDD_REF_VALUE/2' RISE=1",
            ".measure tran start_sense_cross WHEN v(start_sense,vss_a)='VDD_A_VALUE/2' RISE=1",
        ]
    )
    for index in range(m_stages):
        lines.extend(
            [
                ".measure tran sense_{:03d}_cross WHEN v(sense_{:03d},vss_a)='VDD_A_VALUE/2' RISE=1".format(index, index),
                ".measure tran ref_{:03d}_cross WHEN v(ref_{:03d},vss_ref)='VDD_REF_VALUE/2' RISE=1".format(index, index),
                "* Reset sample proves the selected active-high clear holds Q low before ARM release.",
                ".measure tran q_{:03d}_reset_level FIND v(raw_q_{:03d},vss_ref) AT={}".format(
                    index, index, spice_number(float(timing["dff_reset_release_s"]) / 2.0)
                ),
                "* Q level at CAPTURE is the raw comparator bit; a missing rise is valid for bit zero.",
                ".measure tran q_{:03d}_level FIND v(raw_q_{:03d},vss_ref) AT={}".format(index, index, spice_number(capture_time_s)),
                ".measure tran q_{:03d}_rise WHEN v(raw_q_{:03d},vss_ref)='VDD_REF_VALUE/2' RISE=1".format(index, index),
            ]
        )
    lines.extend(
        [
            "* Reference supply includes reference chain and all simultaneous comparator DFF switching.",
            ".measure tran comparator_ref_avg_current_a AVG par('-i(V_VDD_REF)') FROM={} TO={}".format(spice_number(start_ref_s), spice_number(capture_time_s)),
            ".measure tran comparator_ref_peak_current_a MAX par('-i(V_VDD_REF)') FROM={} TO={}".format(spice_number(start_ref_s), spice_number(capture_time_s)),
            ".end",
            "",
        ]
    )
    return "\n".join(lines)


def render_dff_pwl_deck(
    config: Dict[str, Any],
    m_stages: int,
    dummy_load_count: int,
    launch_offset_s: float,
    pwl_points: Sequence[Tuple[float, float]],
) -> str:
    """Render one real-DFF deck with a time-varying sense-domain supply.

    Port and rail ownership remains identical to ``render_dff_deck``: every
    sense-stage supply and well pin use ``vdd_a/vss_a``; every reference stage,
    DFF supply, DFF well, DFF clock, and reset pin use ``vdd_ref/vss_ref``.
    Only ``V_VDD_A`` changes from a DC source to the supplied PWL waveform.

    The PWL must begin at 0 s and at the configured nominal voltage.  This is
    required because START_SENSE is a real source on the sense domain and must
    launch from the same nominal high level as the calibrated static circuit.
    The generated crossing measures intentionally retain the initial 0.55 V
    threshold (VDD_REF/2) so the dynamic sense and reference crossing times
    are compared at the DFF receiver-domain threshold, rather than at a
    moving local half-supply threshold.
    """

    if len(pwl_points) < 2:
        raise ValueError("PWL supply needs at least two time-voltage points")
    normalized = [(float(time_s), float(voltage_v)) for time_s, voltage_v in pwl_points]
    if abs(normalized[0][0]) > 1.0e-18:
        raise ValueError("PWL supply must begin at t=0")
    if abs(normalized[0][1] - float(config["vnom_v"])) > 1.0e-12:
        raise ValueError("PWL supply must begin at configured Vnom")
    for index, (time_s, voltage_v) in enumerate(normalized):
        if time_s < 0.0 or voltage_v <= 0.0 or voltage_v > float(config["vnom_v"]):
            raise ValueError("PWL point {} is outside the supported supply range".format(index))
        if index and time_s <= normalized[index - 1][0]:
            raise ValueError("PWL times must be strictly increasing")

    timing = config["measurement_timing"]
    tran_stop_s = float(timing["tran_stop_s"])
    if normalized[-1][0] < tran_stop_s:
        raise ValueError("PWL waveform must define VDD_A through transient stop")

    # Reuse the reviewed real-DFF topology first, then replace only the supply
    # source.  Keeping all chain, comparator, RESET, launch, and capture lines
    # byte-for-byte aligned with the static deck prevents a dynamic experiment
    # from accidentally becoming a different electrical circuit.
    deck = render_dff_deck(
        config,
        m_stages,
        dummy_load_count,
        normalized[0][1],
        launch_offset_s,
    )
    source_line = "V_VDD_A vdd_a vss_a DC='VDD_A_VALUE'"
    pwl_literal = " ".join("{} {}".format(spice_number(time_s), spice_number(voltage_v)) for time_s, voltage_v in normalized)
    replacement = (
        "* VDD_A PWL is the only dynamic rail; VDD_REF remains the independent 1.1 V DFF/reference rail.\n"
        "V_VDD_A vdd_a vss_a PWL({})".format(pwl_literal)
    )
    if deck.count(source_line) != 1:
        raise ValueError("static DFF source contract changed; cannot render PWL deck safely")
    deck = deck.replace(source_line, replacement)

    # A fixed 1.1 V START_SENSE pulse would overdrive the input after VDD_A
    # droops.  Build a PWL launch source that stays low until the calibrated
    # sense launch, rises with the configured finite edge, then follows the
    # same sense-domain supply waveform.  This keeps the testbench launch
    # driver electrically consistent with a local VDD_A-powered buffer while
    # leaving START_REF and every reference/DFF port on VDD_REF unchanged.
    start_sense_s = float(timing["start_ref_s"]) + launch_offset_s
    rise_s = float(timing["start_rise_s"])
    rise_end_s = start_sense_s + rise_s
    if normalized[-1][0] < rise_end_s:
        raise ValueError("PWL waveform ends before START_SENSE can rise")

    def value_at_time(time_s: float) -> float:
        """Linearly evaluate the declared VDD_A PWL at one in-range time."""

        for (left_time, left_voltage), (right_time, right_voltage) in zip(normalized, normalized[1:]):
            if left_time <= time_s <= right_time:
                if right_time == left_time:
                    return right_voltage
                fraction = (time_s - left_time) / (right_time - left_time)
                return left_voltage + fraction * (right_voltage - left_voltage)
        if abs(time_s - normalized[-1][0]) <= 1.0e-18:
            return normalized[-1][1]
        raise ValueError("PWL launch time lies outside VDD_A waveform")

    launch_points = [(0.0, 0.0), (start_sense_s, 0.0), (rise_end_s, value_at_time(rise_end_s))]
    for time_s, voltage_v in normalized:
        if time_s > rise_end_s:
            launch_points.append((time_s, voltage_v))
    launch_literal = " ".join(
        "{} {}".format(spice_number(time_s), spice_number(voltage_v)) for time_s, voltage_v in launch_points
    )
    static_launch_line = (
        "V_START_SENSE start_sense vss_a PULSE(0 'VDD_A_VALUE' {} {} {} 1.000000000000e-07 2.000000000000e-07)".format(
            spice_number(start_sense_s), spice_number(rise_s), spice_number(rise_s)
        )
    )
    dynamic_launch_lines = (
        "* START_SENSE rises after calibrated offset, then follows the local PWL VDD_A rail.\n"
        "V_START_SENSE start_sense vss_a PWL({})".format(launch_literal)
    )
    if deck.count(static_launch_line) != 1:
        raise ValueError("static START_SENSE contract changed; cannot render PWL deck safely")
    deck = deck.replace(static_launch_line, dynamic_launch_lines)

    # The electrical launch and capture instants are exported alongside the
    # thermometer bits.  Downstream analysis uses these measured voltages as
    # the dynamic x-axis and never assumes that PWL endpoints equal capture.
    measurements = [
        ".measure tran vdd_a_at_launch_v FIND v(vdd_a,vss_a) AT={}".format(
            spice_number(float(timing["start_ref_s"]))
        ),
        ".measure tran vdd_a_at_capture_v FIND v(vdd_a,vss_a) AT={}".format(
            spice_number(float(timing["dff_capture_time_s"]))
        ),
        ".measure tran vdd_a_min_v MIN v(vdd_a,vss_a) FROM=0 TO={}".format(spice_number(tran_stop_s)),
    ]
    end_marker = ".end\n"
    if deck.count(end_marker) != 1:
        raise ValueError("static DFF end-marker contract changed; cannot append PWL measures safely")
    return deck.replace(end_marker, "\n".join(measurements) + "\n.end\n")


def write_dff_deck(
    config: Dict[str, Any], m_stages: int, dummy_load_count: int, vdd_a_v: float, launch_offset_s: float, output_path: Path
) -> None:
    """Write one real-comparator deck into its task-owned scenario directory."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_dff_deck(config, m_stages, dummy_load_count, vdd_a_v, launch_offset_s), encoding="ascii")


def write_dff_pwl_deck(
    config: Dict[str, Any],
    m_stages: int,
    dummy_load_count: int,
    launch_offset_s: float,
    pwl_points: Sequence[Tuple[float, float]],
    output_path: Path,
) -> None:
    """Write one task-owned dynamic-supply real-DFF deck without overwriting callers.

    ``output_path`` is owned by a run-directory scenario.  The runner performs
    its existence and resume checks before invoking this writer; the writer is
    deliberately limited to deterministic deck rendering and parent creation.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_dff_pwl_deck(config, m_stages, dummy_load_count, launch_offset_s, pwl_points),
        encoding="ascii",
    )


def write_deck(config: Dict[str, Any], m_stages: int, dummy_load_count: int, vdd_a_v: float, output_path: Path) -> None:
    """Render one deck and create only the explicitly requested parent directory."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_ideal_deck(config, m_stages, dummy_load_count, vdd_a_v), encoding="ascii")


def build_argument_parser() -> argparse.ArgumentParser:
    """Expose a narrow CLI for auditable manual deck review and runner use."""

    parser = argparse.ArgumentParser(description="generate one Phase-2 ideal Vernier HSPICE deck")
    parser.add_argument("--config", required=True, type=Path, help="Phase 2 configuration")
    parser.add_argument("--m-stages", required=True, type=int, help="number of sense/reference stages")
    parser.add_argument("--dummy-load-count", required=True, type=int, help="reference dummy inverter inputs per stage")
    parser.add_argument("--vdd-a-v", required=True, type=float, help="constant local sense voltage")
    parser.add_argument("--output", required=True, type=Path, help="output deck path")
    return parser


def main(argv: Iterable[str] = None) -> int:
    """Generate one deck; HSPICE execution is intentionally delegated to the runner."""

    args = build_argument_parser().parse_args(argv)
    config = load_json(args.config)
    write_deck(config, args.m_stages, args.dummy_load_count, args.vdd_a_v, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
