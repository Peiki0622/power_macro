#!/usr/bin/env python3
"""Render real-cell HSPICE decks for the standalone FTC-style sensor.

Three intentionally small modes cover the physical progression: ``mechanism``
measures unbuffered logical XOR evidence from two delay lines, ``xor`` adds
the 30 real observation gates, and ``capture`` additionally instantiates the
paper's latch-then-FF capture hierarchy.  No mode contains a Vernier D/CK
comparator, sparse stage selection, or a second voltage rail.
"""

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parents[4]
FTC_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Dict[str, Any]:
    """Load a required JSON object and reject non-object configuration files."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object: {}".format(path))
    return value


def spice(value: float) -> str:
    """Render a finite HSPICE literal without locale-dependent formatting."""

    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite SPICE value: {}".format(value))
    return "{:.12e}".format(number)


def require_mode(mode: str) -> None:
    """Restrict decks to the three planned physical characterization layers."""

    if mode not in ("mechanism", "xor", "capture"):
        raise ValueError("FTC mode must be mechanism, xor, or capture")


def buffer_instance(name: str, output: str, input_node: str, cell: str) -> List[str]:
    """Render one positional six-pin non-inverting SMIC40LL buffer instance."""

    return [
        "* {} ports: Y={} VDD/VNW=vdd_a VPW/VSS=vss_a A={}.".format(name, output, input_node),
        "{} {} vdd_a vdd_a vss_a vss_a {} {}".format(name, output, input_node, cell),
    ]


def render_delay_line(prefix: str, cell: str, initial_stages: int, observable_stages: int) -> Dict[str, Any]:
    """Create one same-polarity initial section and fixed observable buffer line.

    Both the initial and observable sections are ordinary full buffer chains.
    Their independent counts are characterization variables, never sparse
    masks or runtime controls, and every observable tap retains its stage ID.
    """

    if initial_stages < 0 or observable_stages <= 0:
        raise ValueError("initial stages must be nonnegative and observable stages positive")
    lines: List[str] = []
    previous = "s_clk"
    for index in range(initial_stages):
        output = "{}_initial_{:02d}".format(prefix, index)
        lines.extend(buffer_instance("X{}_INIT_{:02d}".format(prefix.upper(), index), output, previous, cell))
        previous = output
    taps: List[str] = []
    for index in range(observable_stages):
        output = "{}_tap_{:02d}".format(prefix, index)
        lines.extend(buffer_instance("X{}_OBS_{:02d}".format(prefix.upper(), index), output, previous, cell))
        taps.append(output)
        previous = output
    return {"lines": lines, "taps": taps}


def render_xor_bank(cells: Dict[str, Any], rvt_taps: List[str], lvt_taps: List[str]) -> Dict[str, Any]:
    """Connect only corresponding RVT/LVT observable stages to 30 real XORs."""

    if len(rvt_taps) != len(lvt_taps):
        raise ValueError("corresponding FTC delay lines must have identical observable length")
    cell = cells["xor2"]["cell"]
    lines: List[str] = []
    outputs: List[str] = []
    for index, (rvt_tap, lvt_tap) in enumerate(zip(rvt_taps, lvt_taps)):
        output = "xor_{:02d}".format(index)
        lines.extend([
            "* XOR {:02d} ports: Y={} VDD/VNW=vdd_a VPW/VSS=vss_a A=RVT({}) B=LVT({}).".format(index, output, rvt_tap, lvt_tap),
            "XXOR_{:02d} {} vdd_a vdd_a vss_a vss_a {} {} {}".format(index, output, rvt_tap, lvt_tap, cell),
        ])
        outputs.append(output)
    return {"lines": lines, "outputs": outputs}


def render_capture_bank(cells: Dict[str, Any], xor_outputs: List[str]) -> Dict[str, Any]:
    """Render the real latch-then-FF hierarchy required by the FTC paper.

    The selected latch is active high.  ``latch_g`` therefore opens before the
    observation interval and falls at the configured capture phase; each FF
    clocks later from ``capture_ck`` so it reads the already closed latch.
    """

    latch_cell = cells["latch"]["cell"]
    dff_cell = cells["dff"]["cell"]
    lines: List[str] = []
    latch_outputs: List[str] = []
    ff_outputs: List[str] = []
    for index, xor_output in enumerate(xor_outputs):
        latch_output = "latch_q_{:02d}".format(index)
        ff_output = "ff_q_{:02d}".format(index)
        lines.extend([
            "* Latch {:02d}: Q={} VDD/VNW=vdd_a VPW/VSS=vss_a D={} G=latch_g.".format(index, latch_output, xor_output),
            "XLATCH_{:02d} {} vdd_a vdd_a vss_a vss_a {} latch_g {}".format(index, latch_output, xor_output, latch_cell),
            "* FF {:02d}: Q={} VDD/VNW=vdd_a VPW/VSS=vss_a CK=capture_ck D={} R=sensor_reset.".format(index, ff_output, latch_output),
            "XFF_{:02d} {} vdd_a vdd_a vss_a vss_a capture_ck {} sensor_reset {}".format(index, ff_output, latch_output, dff_cell),
        ])
        latch_outputs.append(latch_output)
        ff_outputs.append(ff_output)
    return {"lines": lines, "latch_outputs": latch_outputs, "ff_outputs": ff_outputs}


def render_supply(vdd_v: float, stop_time_s: float, glitch: Optional[Dict[str, float]]) -> List[str]:
    """Render the sole local rail, optionally with one bounded voltage droop."""

    if glitch is None:
        return ["V_VDD_A vdd_a vss_a DC='VDD_VALUE'", "V_VSS_A vss_a 0 DC=0"]
    start = float(glitch["start_s"])
    width = float(glitch["width_s"])
    low = vdd_v - float(glitch["depth_v"])
    if low <= 0.0 or start <= 0.0 or width <= 0.0 or start + width >= stop_time_s:
        raise ValueError("invalid FTC glitch request")
    edge = min(1.0e-12, width / 10.0)
    return [
        "* One local VDD_A droop; there is no independent reference rail.",
        "V_VDD_A vdd_a vss_a PWL(0 'VDD_VALUE' {} 'VDD_VALUE' {} {} {} {} {} 'VDD_VALUE' {} 'VDD_VALUE')".format(
            spice(start), spice(start + edge), spice(low), spice(start + width), spice(low), spice(start + width + edge), spice(stop_time_s)
        ),
        "V_VSS_A vss_a 0 DC=0",
    ]


def render_deck(config: Dict[str, Any], cells: Dict[str, Any], vdd_v: float, mode: str,
                initial_rvt_stages: int, initial_lvt_stages: int, capture_phase_s: float,
                glitch: Optional[Dict[str, float]] = None) -> str:
    """Render one complete, task-owned real-cell FTC transient deck."""

    require_mode(mode)
    stages = int(config["observable_stages"])
    launch = float(config["launch_time_s"])
    phase = float(capture_phase_s)
    if phase <= 0.0 or phase >= float(config["sampling_period_s"]):
        raise ValueError("capture phase must lie inside one sampling period")
    absolute_close = launch + phase
    ff_capture = absolute_close + float(config["ff_capture_delay_s"])
    read_time = ff_capture + float(config["post_capture_read_delay_s"])
    # The capture read can occur early in a cycle, but mechanism-mode evidence
    # still requires all 30 taps to cross.  Retain nearly one full sample
    # period after launch so a slow initial-delay candidate is measured rather
    # than misclassified as a failed/zero tap because transient analysis ended.
    stop = max(
        read_time + float(config["post_capture_read_delay_s"]),
        launch + float(config["sampling_period_s"]) - float(config["tran_max_step_s"]),
    )
    # A long transient may intentionally continue after the capture read.  The
    # deck remains valid by retaining the measurement instant while extending
    # only the simulation tail far enough to close the requested PWL event.
    if glitch is not None:
        stop = max(stop, float(glitch["start_s"]) + float(glitch["width_s"]) + 2.0e-12)
    includes = ['.include "{}"'.format(cells["source_files"]["rvt_cdl"])]
    if Path(cells["source_files"]["lvt_cdl"]).resolve() != Path(cells["source_files"]["rvt_cdl"]).resolve():
        includes.append('.include "{}"'.format(cells["source_files"]["lvt_cdl"]))
    lines = [
        "* Auto-generated standalone FTC-style RVT/LVT deck; mode={}.".format(mode),
        "* HVT is represented only by the selected RVT delay path; no HVT cell is claimed.",
        "* One sampling source drives both chains; all cells use VDD_A/VSS_A.",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(float(config["temperature_c"]))),
        *includes,
        '.lib "{}" {}'.format(config["model_library"], config["corner"]),
        ".param VDD_VALUE={}".format(spice(vdd_v)),
        "",
        *render_supply(vdd_v, stop, glitch),
        "* s_clk is the one FTC sampling/launch source for both Vt paths.",
        "V_SCLK s_clk vss_a PULSE(0 'VDD_VALUE' {} 1.000000000000e-12 1.000000000000e-12 {} {})".format(
            spice(launch), spice(float(config["sampling_period_s"]) / 2.0), spice(float(config["sampling_period_s"]))
        ),
    ]
    if mode == "capture":
        latch_open = launch + float(config["latch_open_offset_s"])
        lines.extend([
            "* Active-high latch gate opens after launch and closes at the selected capture phase.",
            "V_LATCH_G latch_g vss_a PWL(0 0 {} 0 {} 'VDD_VALUE' {} 'VDD_VALUE' {} 0 {} 0)".format(
                spice(latch_open), spice(latch_open + 1.0e-12), spice(absolute_close), spice(absolute_close + 1.0e-12), spice(stop)
            ),
            "* Capture FF edge follows latch closure by the configured physical characterization offset.",
            "* Keep CK high for half a sample period: the real standard-cell FF needs a finite high pulse, unlike an ideal event model.",
            "V_CAPTURE_CK capture_ck vss_a PULSE(0 'VDD_VALUE' {} 1.000000000000e-12 1.000000000000e-12 {} {})".format(
                spice(ff_capture), spice(float(config["sampling_period_s"]) / 2.0), spice(float(config["sampling_period_s"]))
            ),
            "* Active-high asynchronous clear holds all post-latch FFs at zero before launch.",
            "V_SENSOR_RESET sensor_reset vss_a PWL(0 'VDD_VALUE' 5.000000000000e-10 'VDD_VALUE' 5.100000000000e-10 0 {} 0)".format(spice(stop)),
        ])
    rvt = render_delay_line("rvt", cells["delay_rvt"]["cell"], initial_rvt_stages, stages)
    lvt = render_delay_line("lvt", cells["delay_lvt"]["cell"], initial_lvt_stages, stages)
    lines.extend(["", "* Full RVT observable line.", *rvt["lines"], "", "* Full LVT observable line.", *lvt["lines"]])
    xor = None
    capture = None
    if mode in ("xor", "capture"):
        xor = render_xor_bank(cells, rvt["taps"], lvt["taps"])
        lines.extend(["", "* Corresponding-tap real XOR observation bank.", *xor["lines"]])
    if mode == "capture":
        capture = render_capture_bank(cells, xor["outputs"])
        lines.extend(["", "* Real FTC latch bank followed by real post-latch FF bank.", *capture["lines"]])
    lines.extend(["", ".tran {} {}".format(spice(float(config["tran_max_step_s"])), spice(stop))])
    for index, node in enumerate(rvt["taps"]):
        lines.append(".measure tran rvt_{:02d}_cross WHEN v({},vss_a)='VDD_VALUE/2' RISE=1".format(index, node))
    for index, node in enumerate(lvt["taps"]):
        lines.append(".measure tran lvt_{:02d}_cross WHEN v({},vss_a)='VDD_VALUE/2' RISE=1".format(index, node))
    if xor is not None:
        sample_time = absolute_close - 5.0e-13
        for index, node in enumerate(xor["outputs"]):
            lines.append(".measure tran xor_{:02d}_level FIND v({},vss_a) AT={}".format(index, node, spice(sample_time)))
    if capture is not None:
        for index, node in enumerate(capture["latch_outputs"]):
            lines.append(".measure tran latch_{:02d}_level FIND v({},vss_a) AT={}".format(index, node, spice(absolute_close + 5.0e-12)))
        for index, node in enumerate(capture["ff_outputs"]):
            lines.append(".measure tran ff_{:02d}_level FIND v({},vss_a) AT={}".format(index, node, spice(read_time)))
    lines.extend([".measure tran vdd_a_min_v MIN v(vdd_a,vss_a) FROM=0 TO={}".format(spice(stop)), ".end", ""])
    return "\n".join(lines)


def write_deck(output_path: Path, **kwargs: Any) -> str:
    """Write exactly one requested FTC deck and return its inspectable text."""

    text = render_deck(**kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="ascii")
    return text
