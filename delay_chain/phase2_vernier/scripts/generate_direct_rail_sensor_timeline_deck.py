#!/usr/bin/env python3
"""Generate the direct-chiplet-A, multi-capture Vernier HSPICE deck.

This generator owns one intentionally narrow electrical experiment.  It does
not model an RO, a package/interposer PDN, a second chiplet, or a workload
current.  Instead, it applies a reviewed, deterministic PWL directly between
the chiplet-A sense-domain rails and captures the response of the real
SMIC40LL 32-stage Vernier sensor five hundred times in one transient simulation.

The output code is never generated in this module.  The generated deck retains
the actual standard-cell sense/reference chains and one asynchronous-clear DFF
per stage.  A later runner reads only HSPICE's DFF measurements and passes the
result through the existing thermometer decoder.
"""

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PHASE2_ROOT = Path(__file__).resolve().parents[1]

Point = Tuple[float, float]


def load_json(path: Path) -> Dict[str, Any]:
    """Load one nonempty JSON object used as experiment provenance."""

    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def resolve_repo_path(value: str) -> Path:
    """Resolve a configuration path independently of the command CWD."""

    path = Path(value)
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def spice_number(value: float) -> str:
    """Render one finite scalar in unambiguous HSPICE scientific notation."""

    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite SPICE literal: {}".format(value))
    return "{:.12e}".format(number)


def timeline_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return the direct-rail configuration after enforcing all physical bounds.

    This validation intentionally describes the experiment contract in one
    place.  The deck renderer and runner can therefore rely on exact frame,
    rail, window, and calibrated-sensor values rather than adding independent
    fallback defaults that could cause a plot and an electrical simulation to
    describe different experiments.
    """

    if "direct_rail_sensor_timeline" not in config:
        raise ValueError("phase2 config has no direct_rail_sensor_timeline section")
    study = config["direct_rail_sensor_timeline"]
    if not isinstance(study, dict):
        raise ValueError("direct_rail_sensor_timeline must be an object")
    if int(study["m_stages"]) != 32:
        raise ValueError("direct rail timeline is qualified only for the calibrated 32-stage sensor")
    if int(study["dummy_load_count"]) != 1 or int(study["cal_sel"]) != 2:
        raise ValueError("direct rail timeline must retain dummy=1 and CAL_SEL=2")
    if abs(float(study["sense_launch_offset_s"]) - 2.0e-11) > 1.0e-18:
        raise ValueError("direct rail timeline must retain the calibrated 20 ps sense offset")

    sample_count = int(study["sample_count"])
    sample_period_s = float(study["sample_period_s"])
    stop_s = float(study["simulation_stop_s"])
    if sample_count != 500 or sample_period_s != 4.0e-9 or abs(sample_count * sample_period_s - stop_s) > 1.0e-18:
        raise ValueError("direct rail timeline requires five hundred 4 ns frames spanning 2 us")
    if float(study["tran_max_step_s"]) <= 0.0:
        raise ValueError("transient maximum step must be positive")

    reset_release_s = float(study["sample_reset_release_offset_s"])
    launch_s = float(study["sample_launch_offset_s"])
    pulse_s = float(study["sample_pulse_width_s"])
    q_read_s = float(study["sample_q_read_offset_s"])
    if not 0.0 < reset_release_s < launch_s < q_read_s < sample_period_s:
        raise ValueError("reset, launch, read, and frame offsets are not ordered")
    if launch_s + pulse_s >= sample_period_s:
        raise ValueError("launch pulse does not fit in one frame")

    change_start_s = float(study["rail_transition_start_offset_s"])
    change_end_s = float(study["rail_transition_end_offset_s"])
    if not 0.0 <= change_start_s < change_end_s < reset_release_s:
        raise ValueError("rail transition must finish while reset remains asserted")
    if launch_s - change_end_s < 8.0e-10:
        raise ValueError("rail must be stable for at least 800 ps before launch")

    sequence = study.get("capture_droop_sequence")
    if not isinstance(sequence, dict):
        raise ValueError("capture_droop_sequence must be an object")
    closed_cycle = [float(value) for value in sequence.get("closed_cycle_mv", [])]
    window_cycle = [float(value) for value in sequence.get("window_cycle_mv", [])]
    window_offsets = [int(value) for value in sequence.get("window_cycle_phase_offsets", [])]
    if len(closed_cycle) < 2 or any(value < 0.5 or value > 2.0 for value in closed_cycle):
        raise ValueError("closed_cycle_mv must contain 0.5--2.0 mV deterministic IR-drop values")
    if len(window_cycle) < 2 or any(value < 4.0 or value > 30.0 for value in window_cycle):
        raise ValueError("window_cycle_mv must contain 4--30 mV deterministic droop values")
    windows = [(float(item[0]), float(item[1])) for item in study["droop_windows_s"]]
    if len(windows) != 4:
        raise ValueError("direct rail timeline needs exactly four windows")
    for start_s, end_s in windows:
        if start_s < 0.0 or end_s <= start_s or end_s > stop_s:
            raise ValueError("direct rail window lies outside the transient")
        if abs((end_s - start_s) - 248.0e-9) > 1.0e-18:
            raise ValueError("each direct rail window must be 248 ns")
        if abs(start_s / sample_period_s - round(start_s / sample_period_s)) > 1.0e-9:
            raise ValueError("direct rail window start must align to a frame")
        if abs(end_s / sample_period_s - round(end_s / sample_period_s)) > 1.0e-9:
            raise ValueError("direct rail window end must align to a frame")
    if any(next_start < end for (_, end), (next_start, _) in zip(windows, windows[1:])):
        raise ValueError("direct rail windows overlap")
    if len(window_offsets) != len(windows) or any(offset < 0 or offset >= len(window_cycle) for offset in window_offsets):
        raise ValueError("window_cycle_phase_offsets must name one in-range offset per window")

    # A dataset request supplies one explicit droop target per frame.  This is
    # deliberately an opt-in extension rather than a replacement for the
    # reviewed fixed-window experiment: the historical Phase-2 configuration
    # contains no such key and therefore continues through its original range
    # checks unchanged.  The direct source remains connected only between the
    # sense-domain VDD_A/VSS_A ports; this branch never creates a voltage-to-
    # code model or changes comparator/reference-domain port ownership.
    explicit_droops = study.get("explicit_capture_droop_mv")
    if explicit_droops is not None:
        if not isinstance(explicit_droops, list) or len(explicit_droops) != sample_count:
            raise ValueError("explicit_capture_droop_mv must contain one value per capture frame")
        if any(not math.isfinite(float(value)) or float(value) <= 0.0 or float(value) >= 100.0 for value in explicit_droops):
            raise ValueError("explicit_capture_droop_mv must stay within the qualified 0--100 mV source envelope")
        return study

    # Expand the compact, reviewed cycles once for validation.  The expanded
    # values are also exactly the values later emitted into the VDD_A PWL, so
    # range checks cannot silently diverge from the simulated source.
    droops = [capture_droop_mv(study, index) for index in range(sample_count)]
    last_pass_drop_mv = (float(config["vnom_v"]) - float(config["timing_anchor"]["last_passing_voltage_v"])) * 1.0e3
    if any(value <= 0.0 or value >= last_pass_drop_mv for value in droops):
        raise ValueError("direct rail droop lies outside the qualified positive/last-pass range")
    for index in range(sample_count):
        droop_mv = droops[index]
        sample_time_s = index * sample_period_s + q_read_s
        in_window = any(start_s <= sample_time_s < end_s for start_s, end_s in windows)
        if in_window and not 4.0 <= droop_mv <= 30.0:
            raise ValueError("window frame {} must have 4--30 mV droop".format(index))
        if not in_window and not 0.5 <= droop_mv <= 2.0:
            raise ValueError("closed frame {} must have 0.5--2.0 mV droop".format(index))
    return study


def capture_droop_mv(study: Dict[str, Any], sample_index: int) -> float:
    """Return the fixed target droop for one real capture without randomisation.

    The configuration deliberately stores short reviewed cycles rather than a
    500-number literal.  Frame index and each window's explicit phase offset
    select one immutable element, so the full 500-point PWL is deterministic,
    inspectable, and reproducible across Python versions.  This helper is a
    voltage-source definition only; it does not compute or infer a sensor code.
    """

    explicit_droops = study.get("explicit_capture_droop_mv")
    if explicit_droops is not None:
        # Explicit values are generated by the TCN corpus builder and are
        # consumed solely as a PWL source definition.  Returning before the
        # historical window-cycle logic preserves every fixed-window capture
        # target used by the completed Phase-2 experiment.
        if sample_index < 0 or sample_index >= len(explicit_droops):
            raise ValueError("explicit capture index lies outside the dataset waveform")
        return float(explicit_droops[sample_index])

    sequence = study["capture_droop_sequence"]
    period_s = float(study["sample_period_s"])
    q_read_s = float(study["sample_q_read_offset_s"])
    capture_time_s = sample_index * period_s + q_read_s
    for window_index, (start_s, end_s) in enumerate(study["droop_windows_s"]):
        if float(start_s) <= capture_time_s < float(end_s):
            window_cycle = sequence["window_cycle_mv"]
            phase = int(sequence["window_cycle_phase_offsets"][window_index])
            # A window begins on a frame boundary whereas Q is read 2.5 ns
            # later.  Ceiling selects the first actual capture whose read time
            # lies inside the window; rounding could assign the preceding
            # closed-frame capture to the first high-droop cycle element.
            window_first_capture = int(math.ceil((float(start_s) - q_read_s) / period_s))
            local_frame = sample_index - window_first_capture
            return float(window_cycle[(local_frame + phase) % len(window_cycle)])
    closed_cycle = sequence["closed_cycle_mv"]
    return float(closed_cycle[sample_index % len(closed_cycle)])


def normalize_points(points: Sequence[Point]) -> List[Point]:
    """Validate strict PWL time order while coalescing identical repeat points."""

    normalized: List[Point] = []
    for time_s, value in points:
        if not math.isfinite(time_s) or not math.isfinite(value) or time_s < 0.0:
            raise ValueError("PWL has a non-finite or negative-time point")
        if normalized:
            previous_time, previous_value = normalized[-1]
            if time_s < previous_time - 1.0e-21:
                raise ValueError("PWL time order regressed")
            if abs(time_s - previous_time) <= 1.0e-21:
                if abs(value - previous_value) > 1.0e-15:
                    raise ValueError("PWL would create an ideal discontinuity at {}".format(time_s))
                continue
        normalized.append((time_s, value))
    if len(normalized) < 2:
        raise ValueError("PWL needs at least two unique points")
    return normalized


def frame_target_voltage_v(config: Dict[str, Any], study: Dict[str, Any], sample_index: int) -> float:
    """Return the configured capture rail voltage for one frame, not a code model."""

    return float(config["vnom_v"]) - capture_droop_mv(study, sample_index) * 1.0e-3


def build_vdd_a_pwl(config: Dict[str, Any], study: Dict[str, Any]) -> List[Point]:
    """Build the direct `VDD_A` waveform with reset-only finite transitions.

    The first rail value begins at nominal voltage for a valid DC operating
    point.  The rail then reaches frame zero's target during its asserted reset
    interval.  Every later frame retains the prior target until 20 ps after
    its boundary and completes a finite 180 ps transition by 200 ps.  Since
    launch is at 1 ns, each sense comparison sees a settled electrical rail.
    """

    period_s = float(study["sample_period_s"])
    start_offset_s = float(study["rail_transition_start_offset_s"])
    end_offset_s = float(study["rail_transition_end_offset_s"])
    points: List[Point] = [(0.0, float(config["vnom_v"]))]
    previous_v = float(config["vnom_v"])
    for sample_index in range(int(study["sample_count"])):
        target_v = frame_target_voltage_v(config, study, sample_index)
        slot_start_s = sample_index * period_s
        points.extend(
            [
                (slot_start_s + start_offset_s, previous_v),
                (slot_start_s + end_offset_s, target_v),
            ]
        )
        previous_v = target_v
    points.append((float(study["simulation_stop_s"]), previous_v))
    return normalize_points(points)


def build_reset_pwl(config: Dict[str, Any], study: Dict[str, Any]) -> List[Point]:
    """Build periodic active-high DFF reset, held low after the final capture.

    `sensor_reset` is connected only to the PHASE2_COMPARATOR `R` port and is
    powered by the fixed reference domain.  It is asserted at every frame
    boundary, before the direct sense rail changes, then released 10 ps after
    the configured 0.5 ns reset interval.  The final low hold prevents an
    unwanted long PWL ramp from clearing the last captured word.
    """

    high_v = float(config["vdd_ref_v"])
    period_s = float(study["sample_period_s"])
    release_s = float(study["sample_reset_release_offset_s"])
    edge_s = float(config["measurement_timing"]["start_rise_s"])
    points: List[Point] = [(0.0, high_v)]
    for sample_index in range(int(study["sample_count"])):
        slot_start_s = sample_index * period_s
        if sample_index:
            points.extend([(slot_start_s, 0.0), (slot_start_s + edge_s, high_v)])
        points.extend([(slot_start_s + release_s, high_v), (slot_start_s + release_s + edge_s, 0.0)])
    points.append((float(study["simulation_stop_s"]), 0.0))
    return normalize_points(points)


def build_launch_pwl(config: Dict[str, Any], study: Dict[str, Any], sense: bool) -> List[Point]:
    """Build one rail-consistent finite launch pulse source for all five hundred frames.

    For `sense=False`, `V_START_REF start_ref/vss_ref` uses the fixed 1.100 V
    reference rail.  For `sense=True`, `V_START_SENSE start_sense/a_vss` uses
    the settled target of the frame's local `VDD_A`; it is delayed by the
    calibrated 20 ps.  Both source cards connect only to their named delay
    chain inputs and never drive a DFF supply or well pin.
    """

    period_s = float(study["sample_period_s"])
    launch_offset_s = float(study["sample_launch_offset_s"])
    pulse_width_s = float(study["sample_pulse_width_s"])
    rise_s = float(config["measurement_timing"]["start_rise_s"])
    calibrated_offset_s = float(study["sense_launch_offset_s"]) if sense else 0.0
    points: List[Point] = [(0.0, 0.0)]
    for sample_index in range(int(study["sample_count"])):
        slot_start_s = sample_index * period_s
        high_v = frame_target_voltage_v(config, study, sample_index) if sense else float(config["vdd_ref_v"])
        start_s = slot_start_s + launch_offset_s + calibrated_offset_s
        high_s = start_s + rise_s
        fall_s = start_s + pulse_width_s
        low_s = fall_s + rise_s
        if low_s >= (sample_index + 1) * period_s:
            raise ValueError("launch pulse crosses its frame boundary")
        points.extend([(start_s, 0.0), (high_s, high_v), (fall_s, high_v), (low_s, 0.0)])
    points.append((float(study["simulation_stop_s"]), 0.0))
    return normalize_points(points)


def render_pwl_source(name: str, positive_node: str, negative_node: str, points: Sequence[Point]) -> List[str]:
    """Render a wrapped HSPICE PWL source with explicit terminal ownership."""

    if not points:
        raise ValueError("cannot render empty PWL")
    lines = ["{} {} {} PWL(".format(name, positive_node, negative_node)]
    for index, (time_s, value) in enumerate(points):
        prefix = "+ " if index else "+ "
        lines.append("{}{} {}".format(prefix, spice_number(time_s), spice_number(value)))
    lines.append(")")
    return lines


def render_stage_chain(prefix: str, stage_cell: str, m_stages: int, vdd_node: str, vss_node: str, start_node: str) -> List[str]:
    """Unroll a named non-inverting stage chain with rail/port comments."""

    lines: List[str] = []
    previous_node = start_node
    for stage_index in range(m_stages):
        output_node = "{}_{:03d}".format(prefix, stage_index)
        lines.extend(
            [
                "* {} stage {:03d} ports: Y={} VDD={} VSS={} A={}.".format(
                    prefix, stage_index, output_node, vdd_node, vss_node, previous_node
                ),
                "X{}_STAGE_{:03d} {} {} {} {} {}".format(
                    prefix.upper(), stage_index, output_node, vdd_node, vss_node, previous_node, stage_cell
                ),
            ]
        )
        previous_node = output_node
    return lines


def render_sensor_instances(study: Dict[str, Any]) -> List[str]:
    """Render all sense/reference stages and DFF comparators with port contracts."""

    m_stages = int(study["m_stages"])
    lines = [
        "* Sense chain ports: every stage VDD/VNW uses vdd_a and every VSS/VPW uses vss_a.",
    ]
    lines.extend(render_stage_chain("sense", "PHASE2_SENSE_STAGE", m_stages, "vdd_a", "vss_a", "start_sense"))
    lines.append("* Reference chain ports: every stage and dummy input load uses vdd_ref/vss_ref only.")
    lines.extend(render_stage_chain("ref", "PHASE2_REFERENCE_STAGE_D1", m_stages, "vdd_ref", "vss_ref", "start_ref"))
    lines.append("* Comparator ports: Q=raw_q_i, VDD/VSS=vdd_ref/vss_ref, D=sense_i, CK=ref_i, R=sensor_reset.")
    for stage_index in range(m_stages):
        lines.extend(
            [
                "* Comparator {:03d}: D crosses from chiplet-A sense domain; DFF supply and wells remain reference-domain.".format(stage_index),
                "XCOMP_{:03d} raw_q_{:03d} vdd_ref vss_ref sense_{:03d} ref_{:03d} sensor_reset PHASE2_COMPARATOR".format(
                    stage_index, stage_index, stage_index, stage_index
                ),
            ]
        )
    return lines


def render_sample_measures(study: Dict[str, Any]) -> List[str]:
    """Render every real-DFF/reset/arrival/rail measurement for all frames."""

    m_stages = int(study["m_stages"])
    period_s = float(study["sample_period_s"])
    reset_read_offset_s = float(study["sample_reset_release_offset_s"]) / 2.0
    q_read_offset_s = float(study["sample_q_read_offset_s"])
    lines: List[str] = []
    for sample_index in range(int(study["sample_count"])):
        slot_start_s = sample_index * period_s
        reset_read_s = slot_start_s + reset_read_offset_s
        q_read_s = slot_start_s + q_read_offset_s
        lines.extend(
            [
                "* Frame {:03d}: reset proof precedes ARM; Q/rail samples follow DFF settling.".format(sample_index),
                ".measure tran sample_{:03d}_a_vdd FIND v(vdd_a,vss_a) AT={}".format(sample_index, spice_number(q_read_s)),
                ".measure tran sample_{:03d}_vdd_ref FIND v(vdd_ref,vss_ref) AT={}".format(sample_index, spice_number(q_read_s)),
            ]
        )
        for stage_index in range(m_stages):
            # The DFF sees S_i at the reference-domain receiver threshold.  A
            # moving half-VDD_A threshold would not describe its actual input
            # aperture, so all dynamic crossings deliberately use fixed 0.55 V.
            lines.extend(
                [
                    ".measure tran sense_{:03d}_cross_{:03d} WHEN v(sense_{:03d},vss_a)=5.500000000000e-01 RISE={}".format(sample_index, stage_index, stage_index, sample_index + 1),
                    ".measure tran ref_{:03d}_cross_{:03d} WHEN v(ref_{:03d},vss_ref)=5.500000000000e-01 RISE={}".format(sample_index, stage_index, stage_index, sample_index + 1),
                    ".measure tran q_{:03d}_reset_level_{:03d} FIND v(raw_q_{:03d},vss_ref) AT={}".format(sample_index, stage_index, stage_index, spice_number(reset_read_s)),
                    ".measure tran q_{:03d}_level_{:03d} FIND v(raw_q_{:03d},vss_ref) AT={}".format(sample_index, stage_index, stage_index, spice_number(q_read_s)),
                ]
            )
    return lines


def render_direct_rail_deck(config: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Render the complete direct-rail 2 us deck and return review metadata."""

    study = timeline_config(config)
    phase1 = load_json(resolve_repo_path(str(config["phase1_config_path"])))
    include_dir = PHASE2_ROOT / "spice"
    required_includes = [include_dir / "sense_stage.inc", include_dir / "reference_stage.inc", include_dir / "comparator_bank.inc"]
    missing = [str(path) for path in required_includes if not path.is_file()]
    if missing:
        raise ValueError("missing Phase 2 SPICE includes: {}".format(", ".join(missing)))

    vdd_a_points = build_vdd_a_pwl(config, study)
    reset_points = build_reset_pwl(config, study)
    ref_points = build_launch_pwl(config, study, sense=False)
    sense_points = build_launch_pwl(config, study, sense=True)
    stop_s = float(study["simulation_stop_s"])
    lines = [
        "* Auto-generated direct-chiplet-A Vernier sensor timeline.",
        "* This deck directly drives only VDD_A/VSS_A; it contains no RO, PDN, B-side, or workload source.",
        "* Sensor contract: M=32, reference dummy=1, CAL_SEL=2, sense launch offset=20 ps.",
        ".option post=2 nomod measform=3 runlvl=3",
        ".temp {}".format(spice_number(float(config["temperature_c"]))),
        '.include "{}"'.format(resolve_repo_path(str(phase1["cell_cdl"]))),
        '.lib "{}" {}'.format(Path(phase1["model_library"]), str(config["corner"])),
        '.include "{}"'.format(required_includes[0]),
        '.include "{}"'.format(required_includes[1]),
        '.include "{}"'.format(required_includes[2]),
        "",
        "* Direct rail source ports: vdd_a/vss_a; this is the sole time-varying chiplet-A supply.",
    ]
    lines.extend(render_pwl_source("V_VDD_A", "vdd_a", "vss_a", vdd_a_points))
    lines.extend(
        [
            "* Chiplet-A return ports: vss_a/0; no package/interposer impedance is inserted.",
            "V_VSS_A vss_a 0 DC=0",
            "* Fixed reference ports: vdd_ref/vss_ref power reference stages, DFF supply, and DFF well pins.",
            "V_VDD_REF vdd_ref vss_ref DC={}".format(spice_number(float(config["vdd_ref_v"]))),
            "V_VSS_REF vss_ref 0 DC=0",
            "* Reset ports: sensor_reset/vss_ref drive only the active-high DFF R input.",
        ]
    )
    lines.extend(render_pwl_source("V_SENSOR_RESET", "sensor_reset", "vss_ref", reset_points))
    lines.append("* Reference launch ports: start_ref/vss_ref drive only the reference-chain first input.")
    lines.extend(render_pwl_source("V_START_REF", "start_ref", "vss_ref", ref_points))
    lines.append("* Sense launch ports: start_sense/vss_a drive only the sense-chain first input at local settled rail amplitude.")
    lines.extend(render_pwl_source("V_START_SENSE", "start_sense", "vss_a", sense_points))
    lines.append("")
    lines.extend(render_sensor_instances(study))
    lines.extend(
        [
            "",
            "* Save solved rails for plot evidence; all code bits remain .measure-derived DFF observations.",
            ".probe tran v(vdd_a) v(vss_a) v(vdd_ref) v(vss_ref) v(sensor_reset)",
            ".tran {} {}".format(spice_number(float(study["tran_max_step_s"])), spice_number(stop_s)),
        ]
    )
    lines.extend(render_sample_measures(study))
    lines.extend(
        [
            "* End rail extrema one picosecond before .tran endpoint for W-2024.09 endpoint compatibility.",
            ".measure tran a_vdd_min_v MIN v(vdd_a,vss_a) FROM=0 TO={}".format(spice_number(stop_s - 1.0e-12)),
            ".measure tran a_vdd_max_v MAX v(vdd_a,vss_a) FROM=0 TO={}".format(spice_number(stop_s - 1.0e-12)),
            ".end",
            "",
        ]
    )
    metadata = {
        "vdd_a_points": vdd_a_points,
        "reset_points": reset_points,
        "reference_launch_points": ref_points,
        "sense_launch_points": sense_points,
        "measurement_count": int(study["sample_count"]) * (2 + 4 * int(study["m_stages"])) + 2,
    }
    return "\n".join(lines), metadata


def write_direct_rail_deck(config: Dict[str, Any], output_path: Path) -> Dict[str, Any]:
    """Write one deterministic deck into the caller-owned run scenario directory."""

    deck, metadata = render_direct_rail_deck(config)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(deck, encoding="ascii")
    return metadata


if __name__ == "__main__":
    raise SystemExit("This module is imported by the direct-rail timeline runner.")
