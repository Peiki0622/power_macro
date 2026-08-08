#!/usr/bin/env python3
"""Render the minimal same-rail Phase 3 single-stage HSPICE deck.

This first renderer deliberately stops at two inverter stages.  Keeping it
separate from the later Vernier/DFF renderer makes the Step-3 evidence easy to
audit and prevents an accidental comparator or second power domain from
changing the device-sensitivity experiment.
"""

import math
from pathlib import Path
from typing import Any, Dict, List, Optional


EXPECTED_CDL_PORTS = ["Y", "VDD", "VNW", "VPW", "VSS", "A"]


def finite(value: float, name: str) -> float:
    """Validate one positive physical scalar before placing it in a deck."""

    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError("{} must be finite and positive".format(name))
    return number


def spice(value: float) -> str:
    """Use scientific notation so sub-picosecond values are not rounded away."""

    return "{:.12e}".format(float(value))


def render_cell_instance(instance: str, output: str, input_node: str, cell: str) -> str:
    """Render a positional CDL instance with every well connection explained.

    The CDL contract is ``Y VDD VNW VPW VSS A``.  Both n-well and p-well are
    tied to the same local rails as VDD/VSS, matching the Phase-1 convention and
    ensuring RVT and LVT see identical well bias during the comparison.
    """

    return "\n".join(
        [
            "* {}: Y={} VDD=vdd_a VNW=vdd_a VPW=vss_a VSS=vss_a A={}.".format(instance, output, input_node),
            "{} {} vdd_a vdd_a vss_a vss_a {} {}".format(instance, output, input_node, cell),
        ]
    )


def render_stage(prefix: str, cell: str) -> str:
    """Render two inverters, preserving a non-inverting stage output."""

    middle = "{}_mid".format(prefix)
    output = "{}_out".format(prefix)
    return "\n".join(
        [
            "* {} stage: start -> INV -> {} -> INV -> {}.".format(prefix.upper(), middle, output),
            render_cell_instance("X{}_INV_A".format(prefix.upper()), middle, "start", cell),
            render_cell_instance("X{}_INV_B".format(prefix.upper()), output, middle, cell),
            "* Identical explicit load for RVT/LVT output comparison.",
            "C{}_LOAD {} vss_a 1.000000000000e-15".format(prefix.upper(), output),
        ]
    )


def render_sensitivity_deck(
    rvt_cdl: Path,
    lvt_cdl: Path,
    model_library: Path,
    corner: str,
    temperature_c: float,
    vdd_v: float,
    rvt_cell: str,
    lvt_cell: str,
) -> str:
    """Create one transient containing identical RVT and LVT measurements."""

    vdd_v = finite(vdd_v, "VDD")
    if not rvt_cdl.is_file() or not lvt_cdl.is_file() or not model_library.is_file():
        raise ValueError("RVT CDL, LVT CDL, and model library must all exist")
    lines = [
        "* Auto-generated Phase-3 RVT/LVT single-stage sensitivity deck.",
        "* Both stages use only VDD_A/VSS_A; no reference supply exists in this experiment.",
        # HSPICE otherwise rounds .measure output to approximately picosecond
        # precision.  Phase 3 must resolve the sub-picosecond RVT/LVT
        # differential change that accumulates across 32 stages, so retain ten
        # significant digits in every MEASFORM=3 CSV result.
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(temperature_c)),
        '.include "{}"'.format(rvt_cdl.resolve()),
        '.include "{}"'.format(lvt_cdl.resolve()),
        '.lib "{}" {}'.format(model_library.resolve(), corner),
        ".param VDD_VALUE={}".format(spice(vdd_v)),
        "",
        "* Differential local supply: every cell and both well pairs use these rails.",
        "V_VDD_A vdd_a vss_a DC='VDD_VALUE'",
        "V_VSS_A vss_a 0 DC=0",
        "* One common input waveform gives both stages identical slew and timing origin.",
        "V_START start vss_a PULSE(0 'VDD_VALUE' 1.000000000000e-09 1.000000000000e-11 1.000000000000e-11 4.000000000000e-10 2.000000000000e-09)",
        "",
        render_stage("rvt", rvt_cell),
        "",
        render_stage("lvt", lvt_cell),
        "",
        "* The threshold is the common local-rail midpoint for both directions.",
        ".measure tran rvt_rise_s TRIG v(start,vss_a) VAL='VDD_VALUE/2' RISE=1 TARG v(rvt_out,vss_a) VAL='VDD_VALUE/2' RISE=1",
        ".measure tran rvt_fall_s TRIG v(start,vss_a) VAL='VDD_VALUE/2' FALL=1 TARG v(rvt_out,vss_a) VAL='VDD_VALUE/2' FALL=1",
        ".measure tran lvt_rise_s TRIG v(start,vss_a) VAL='VDD_VALUE/2' RISE=1 TARG v(lvt_out,vss_a) VAL='VDD_VALUE/2' RISE=1",
        ".measure tran lvt_fall_s TRIG v(start,vss_a) VAL='VDD_VALUE/2' FALL=1 TARG v(lvt_out,vss_a) VAL='VDD_VALUE/2' FALL=1",
        ".measure tran rvt_stage_s PARAM='(rvt_rise_s+rvt_fall_s)/2'",
        ".measure tran lvt_stage_s PARAM='(lvt_rise_s+lvt_fall_s)/2'",
        ".tran 1.000000000000e-12 2.000000000000e-09",
        ".end",
        "",
    ]
    return "\n".join(lines)


def render_pair_matching_deck(
    rvt_cdl: Path,
    lvt_cdl: Path,
    model_library: Path,
    corner: str,
    temperature_c: float,
    vdd_v: float,
    rvt_cell: str,
    lvt_cell: str,
    dummy_load_count: int,
) -> str:
    """Render the Step-4 deck with only LVT output-input dummy loads added.

    A dummy is a real LVT inverter whose ``A`` input is tied to the companion
    stage output.  Its ``Y`` output is private and never drives the signal path;
    the cell therefore contributes its physical input capacitance without
    changing the measured logical function.  RVT remains exactly two fixed
    inverters, as required by the matching experiment.
    """

    if int(dummy_load_count) not in range(4):
        raise ValueError("dummy_load_count must be 0, 1, 2, or 3")
    text = render_sensitivity_deck(
        rvt_cdl=rvt_cdl,
        lvt_cdl=lvt_cdl,
        model_library=model_library,
        corner=corner,
        temperature_c=temperature_c,
        vdd_v=vdd_v,
        rvt_cell=rvt_cell,
        lvt_cell=lvt_cell,
    )
    marker = "* The threshold is the common local-rail midpoint for both directions."
    dummy_lines = [
        "* LVT dummy input loads: outputs are private and do not participate in timing."
    ]
    for index in range(int(dummy_load_count)):
        dummy_lines.extend(
            [
                "* Dummy {:02d}: Y=lvt_dummy_{:02d}_y VDD=vdd_a VNW=vdd_a VPW=vss_a VSS=vss_a A=lvt_out.".format(index, index),
                "XLVT_DUMMY_{:02d} lvt_dummy_{:02d}_y vdd_a vdd_a vss_a vss_a lvt_out {}".format(index, index, lvt_cell),
            ]
        )
    return text.replace(marker, "\n".join(dummy_lines + [marker]), 1)


def render_vernier_chain(prefix: str, cell: str, stages: int, dummy_cell: str = "", dummy_load_count: int = 0, start_node: str = "start") -> str:
    """Render one non-inverting chain with one named arrival tap per stage.

    ``dummy_cell`` and ``dummy_load_count`` describe only the deliberate LVT
    input loading selected in Step 4.  Each dummy is a real standard-cell input
    tied to the stage tap; its output is private and never feeds a later stage.
    This preserves the selected companion-path load without inserting an
    unsynthesizable capacitor or a behavioral delay into the Vernier path.
    """

    if int(stages) <= 0:
        raise ValueError("Vernier chain must contain at least one stage")
    if int(dummy_load_count) < 0:
        raise ValueError("dummy_load_count must not be negative")
    if int(dummy_load_count) and not dummy_cell:
        raise ValueError("dummy_cell is required when dummy_load_count is nonzero")
    lines = ["* {} chain: every tap is the output after two real inverters; launch input={}.".format(prefix.upper(), start_node)]
    previous = start_node
    for index in range(int(stages)):
        middle = "{}_mid_{:03d}".format(prefix, index)
        tap = "{}_tap_{:03d}".format(prefix, index)
        lines.extend(
            [
                "* {} stage {:03d}: input={} output={} cell={}.".format(prefix.upper(), index, previous, tap, cell),
                render_cell_instance("X{}_STAGE_{:03d}_A".format(prefix.upper(), index), middle, previous, cell),
                render_cell_instance("X{}_STAGE_{:03d}_B".format(prefix.upper(), index), tap, middle, cell),
            ]
        )
        for dummy_index in range(int(dummy_load_count)):
            # CDL order is intentionally written in the surrounding comment:
            # Y VDD VNW VPW VSS A.  The private Y node proves that the dummy is
            # a capacitive input load only and cannot create a logic feedback.
            lines.extend(
                [
                    "* {} stage {:03d} dummy {:02d}: Y={}_dummy_{:03d}_{:02d}_y VDD=vdd_a VNW=vdd_a VPW=vss_a VSS=vss_a A={}.".format(
                        prefix.upper(), index, dummy_index, prefix, index, dummy_index, tap
                    ),
                    "X{}_STAGE_{:03d}_DUMMY_{:02d} {}_dummy_{:03d}_{:02d}_y vdd_a vdd_a vss_a vss_a {} {}".format(
                        prefix.upper(), index, dummy_index, prefix, index, dummy_index, tap, dummy_cell
                    ),
                ]
            )
        previous = tap
    return "\n".join(lines)


def active_stage_indices(stages: int, active_stage_count: int) -> List[int]:
    """Return a deterministic, approximately uniform sparse-stage placement.

    Stage zero is the earliest comparator tap and also mask bit zero.  The
    integer-floor rule is intentionally simple and reproducible: it spreads
    ``active_stage_count`` positions over the fixed stage count without any
    fitted delay model or candidate search.  For example, 16 active stages in
    a 32-stage chain are exactly the even stage indices.
    """

    if int(stages) <= 0:
        raise ValueError("stages must be positive")
    if int(active_stage_count) <= 0 or int(active_stage_count) > int(stages):
        raise ValueError("active_stage_count must be in [1, stages]")
    return [(ordinal * int(stages)) // int(active_stage_count) for ordinal in range(int(active_stage_count))]


def active_stage_mask(stages: int, active_stage_count: int) -> int:
    """Encode the ordered sparse-stage placement with bit ``i`` for stage ``i``."""

    mask = 0
    for index in active_stage_indices(stages, active_stage_count):
        mask |= 1 << index
    return mask


def render_sparse_companion_chain(
    rvt_cell: str, lvt_cell: str, stages: int, active_mask: int, start_node: str,
) -> str:
    """Render the wide-range companion without dummy loads or runtime choices.

    A zero mask bit emits RVT->RVT, while a one bit emits LVT->RVT.  The
    static Python integer is resolved while the deck is rendered, so HSPICE
    receives only real inverter instances and never a topology-selecting mux.
    The RVT second inverter makes every companion tap present an RVT driver to
    the real DFF bank.
    """

    if int(active_mask) < 0 or int(active_mask) >= (1 << int(stages)):
        raise ValueError("active_mask must fit the stage count")
    lines = ["* Wide-range sparse companion: mask bit i selects LVT->RVT at stage i; no dummy load exists."]
    previous = start_node
    for index in range(int(stages)):
        middle = "companion_mid_{:03d}".format(index)
        tap = "lvt_tap_{:03d}".format(index)
        first_cell = lvt_cell if ((int(active_mask) >> index) & 1) else rvt_cell
        kind = "active LVT->RVT" if first_cell == lvt_cell else "neutral RVT->RVT"
        lines.extend([
            "* Companion stage {:03d}: {}.".format(index, kind),
            render_cell_instance("XCOMPANION_STAGE_{:03d}_A".format(index), middle, previous, first_cell),
            render_cell_instance("XCOMPANION_STAGE_{:03d}_B".format(index), tap, middle, rvt_cell),
        ])
        previous = tap
    return "\n".join(lines)


def render_ideal_vernier_deck(
    rvt_cdl: Path,
    lvt_cdl: Path,
    model_library: Path,
    corner: str,
    temperature_c: float,
    vdd_v: float,
    rvt_cell: str,
    lvt_cell: str,
    stages: int,
    lvt_dummy_load_count: int = 0,
) -> str:
    """Render the no-DFF, same-rail 32-stage arrival experiment.

    The LVT dummy count is propagated from the Step-4 pair selection.  The
    selected load must remain in this ideal-arrival deck so its measured
    crossing location is a valid input to the real-DFF and physical-CAL_SEL
    stages that follow.
    """

    vdd_v = finite(vdd_v, "VDD")
    if not rvt_cdl.is_file() or not lvt_cdl.is_file() or not model_library.is_file():
        raise ValueError("RVT CDL, LVT CDL, and model library must all exist")
    lines = [
        "* Auto-generated Phase-3 ideal RVT/LVT Vernier arrival deck.",
        "* No DFF or separate reference rail exists; both physical chains use VDD_A/VSS_A.",
        # Keep arrival timestamps at the same precision as the Step-3/4
        # measurements.  A coarser exported timestamp would quantize the
        # ideal thermometer selection before any physical DFF is introduced.
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(temperature_c)),
        '.include "{}"'.format(rvt_cdl.resolve()),
        '.include "{}"'.format(lvt_cdl.resolve()),
        '.lib "{}" {}'.format(model_library.resolve(), corner),
        ".param VDD_VALUE={}".format(spice(vdd_v)),
        "V_VDD_A vdd_a vss_a DC='VDD_VALUE'",
        "V_VSS_A vss_a 0 DC=0",
        "* Simultaneous launches make the measured RVT-LVT difference explicit.",
        "V_START start vss_a PULSE(0 'VDD_VALUE' 1.000000000000e-09 1.000000000000e-11 1.000000000000e-11 1.000000000000e-09 3.000000000000e-09)",
        "",
        render_vernier_chain("rvt", rvt_cell, stages),
        "",
        render_vernier_chain("lvt", lvt_cell, stages, dummy_cell=lvt_cell, dummy_load_count=lvt_dummy_load_count),
        "",
        "* Every comparison uses the same instantaneous local-rail midpoint.",
    ]
    for index in range(int(stages)):
        lines.append(
            ".measure tran rvt_{:03d}_cross_s WHEN v(rvt_tap_{:03d},vss_a) VAL='VDD_VALUE/2' RISE=1".format(index, index)
        )
        lines.append(
            ".measure tran lvt_{:03d}_cross_s WHEN v(lvt_tap_{:03d},vss_a) VAL='VDD_VALUE/2' RISE=1".format(index, index)
        )
    lines.extend([".tran 1.000000000000e-12 4.000000000000e-09", ".end", ""])
    return "\n".join(lines)


def write_sensitivity_deck(**kwargs: Any) -> str:
    """Write a requested deck and return its rendered text for topology tests."""

    output_path = Path(kwargs.pop("output_path"))
    text = render_sensitivity_deck(**kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="ascii")
    return text


def write_pair_matching_deck(**kwargs: Any) -> str:
    """Write one matching deck while keeping generation inspectable in tests."""

    output_path = Path(kwargs.pop("output_path"))
    text = render_pair_matching_deck(**kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="ascii")
    return text


def write_ideal_vernier_deck(**kwargs: Any) -> str:
    """Write one ideal-arrival deck for a task-owned HSPICE scenario."""

    output_path = Path(kwargs.pop("output_path"))
    text = render_ideal_vernier_deck(**kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="ascii")
    return text


def render_calibration_network(
    buffer_cell: str, mux_cell: str, cal_sel: int, launch_balance_load_count: int = 2,
    rvt_launch_load_count: int = 0,
) -> List[str]:
    """Render the physical eight-tap, same-rail launch calibration network.

    The first two RVT tap increments are fine-grained real
    ``MXT2_X0P5M_A9TR40`` delays (A and B tied together); the following five
    increments are coarse real ``BUF_X0P7M_A9TR40`` delays.  Three balanced
    ``MXT2_X0P5M_A9TR40`` levels then select one of those eight taps with
    ``CAL_SEL[2:0]``.  The LVT branch traverses an identically deep MUX tree
    whose eight leaves are the un-delayed request; this makes the MUX
    propagation common-mode and leaves the RVT tap delay as the intentional
    launch difference.  Every positional instance uses the documented
    SMIC40LL order:

    * BUF: ``Y VDD VNW VPW VSS A``;
    * MXT2: ``Y VDD VNW VPW VSS A B S0``.

    ``cal_sel`` is emitted as static same-rail voltage sources in the deck,
    matching the eventual RTL selector bits without using a behavioral mux.
    """

    if int(cal_sel) < 0 or int(cal_sel) > 7:
        raise ValueError("cal_sel must be in [0, 7]")
    if int(launch_balance_load_count) not in (0, 1, 2):
        raise ValueError("launch_balance_load_count must be 0, 1, or 2")
    # The companion-side inherited count stays constrained to its historical
    # 0/1/2 A/B study.  CK-side reuse/extension is separately bounded at six:
    # two reused cells plus at most five measured fine-delay additions.  The
    # seventh case is a one-point aperture-edge diagnostic, not a sweep axis.
    if int(rvt_launch_load_count) < 0 or int(rvt_launch_load_count) > 7:
        raise ValueError("rvt_launch_load_count must be in [0, 7]")
    lines: List[str] = [
        "* Physical launch calibration: eight RVT BUF taps and two equal-depth MUX trees.",
        "* BUF/MXT2 supply and well pins all use vdd_a/vss_a; no separate rail exists.",
        "V_CAL_SEL_0 cal_sel_0 vss_a DC={}".format("'VDD_VALUE'" if (int(cal_sel) & 1) else "0"),
        "V_CAL_SEL_1 cal_sel_1 vss_a DC={}".format("'VDD_VALUE'" if (int(cal_sel) & 2) else "0"),
        "V_CAL_SEL_2 cal_sel_2 vss_a DC={}".format("'VDD_VALUE'" if (int(cal_sel) & 4) else "0"),
        "* The common request source drives the LVT leaves and the RVT tap-0 leaf.",
        "* CAL_SEL bit sources are static before the launch event and stay on VDD_A/VSS_A.",
    ]
    rvt_taps = ["start_req"]
    # A full BUF step is intentionally too coarse for the DFF setup aperture.
    # The first two tap increments therefore use a real MXT2 with A=B, which
    # acts as a smaller physical non-inverting delay.  Its select is tied to
    # the local return so CAL_SEL cannot alter the chosen tap's delay.
    for index in range(1, 3):
        previous = rvt_taps[-1]
        tap = "cal_rvt_tap_{:d}".format(index)
        lines.extend(
            [
                "* RVT fine tap {:d}: MXT2 ports Y VDD VNW VPW VSS A B S0 = {} vdd_a vdd_a vss_a vss_a {} {} vss_a.".format(index, tap, previous, previous),
                "XCAL_RVT_FINE_{:d} {} vdd_a vdd_a vss_a vss_a {} {} vss_a {}".format(index, tap, previous, previous, mux_cell),
            ]
        )
        rvt_taps.append(tap)
    for index in range(3, 8):
        previous = rvt_taps[-1]
        tap = "cal_rvt_tap_{:d}".format(index)
        lines.extend(
            [
                "* RVT coarse tap {:d}: BUF ports Y VDD VNW VPW VSS A = {} vdd_a vdd_a vss_a vss_a {}.".format(index, tap, previous),
                "XCAL_RVT_BUF_{:d} {} vdd_a vdd_a vss_a vss_a {} {}".format(index, tap, previous, buffer_cell),
            ]
        )
        rvt_taps.append(tap)

    def mux_level(prefix: str, left_nodes: List[str], select_node: str) -> List[str]:
        """Unroll one two-input MUX level with explicit positional port comments."""

        rendered: List[str] = []
        next_nodes: List[str] = []
        for pair_index in range(0, len(left_nodes), 2):
            output = "{}_{}".format(prefix, pair_index // 2)
            rendered.extend(
                [
                    "* {} MUX {:d}: Y VDD VNW VPW VSS A B S0 = {} vdd_a vdd_a vss_a vss_a {} {} {}.".format(
                        prefix, pair_index // 2, output, left_nodes[pair_index], left_nodes[pair_index + 1], select_node
                    ),
                    "X{}_{} {} vdd_a vdd_a vss_a vss_a {} {} {} {}".format(
                        prefix.upper(), pair_index // 2, output, left_nodes[pair_index], left_nodes[pair_index + 1], select_node, mux_cell
                    ),
                ]
            )
            next_nodes.append(output)
        return rendered + ["* {} level output nodes: {}.".format(prefix, ", ".join(next_nodes))] + next_nodes

    rvt_level0 = mux_level("CAL_RVT_MUX_L0", rvt_taps, "cal_sel_0")
    rvt_nodes0 = rvt_level0[-4:]
    lines.extend(rvt_level0[:-4])
    rvt_level1 = mux_level("CAL_RVT_MUX_L1", rvt_nodes0, "cal_sel_1")
    rvt_nodes1 = rvt_level1[-2:]
    lines.extend(rvt_level1[:-2])
    rvt_level2 = mux_level("CAL_RVT_MUX_L2", rvt_nodes1, "cal_sel_2")
    # ``mux_level`` returns the output node names after a comment.  The names
    # are useful to the caller only when extracting the previous level; the
    # final level's single node is already known as CAL_RVT_MUX_L2_0.  Writing
    # that node as a standalone line would be parsed by HSPICE as a malformed
    # device, so emit the generated devices and explanatory comment only.
    lines.extend(rvt_level2[:-1])
    lines.append("* Selected RVT launch node is CAL_RVT_MUX_L2_0.")
    lines.append(
        "* RVT launch input-load count={}: reused private BUF inputs delay CK without adding a series cell.".format(
            int(rvt_launch_load_count)
        )
    )
    for index in range(int(rvt_launch_load_count)):
        lines.extend(
            [
                "* RVT load {} ports Y VDD VNW VPW VSS A = cal_rvt_balance_y{} vdd_a vdd_a vss_a vss_a CAL_RVT_MUX_L2_0.".format(index, index),
                "XCAL_RVT_BALANCE_LOAD_{} cal_rvt_balance_y{} vdd_a vdd_a vss_a vss_a CAL_RVT_MUX_L2_0 {}".format(index, index, buffer_cell),
            ]
        )

    # LVT leaves intentionally all name the same request node.  The same three
    # MUX levels therefore add the same common launch delay as the RVT branch,
    # while no LVT BUF tap is selected.
    lvt_level0 = mux_level("CAL_LVT_MUX_L0", ["start_req"] * 8, "cal_sel_0")
    lvt_nodes0 = lvt_level0[-4:]
    lines.extend(lvt_level0[:-4])
    lvt_level1 = mux_level("CAL_LVT_MUX_L1", lvt_nodes0, "cal_sel_1")
    lvt_nodes1 = lvt_level1[-2:]
    lines.extend(lvt_level1[:-2])
    lvt_level2 = mux_level("CAL_LVT_MUX_L2", lvt_nodes1, "cal_sel_2")
    # Apply the same final-level rule to the common-mode LVT tree; the final
    # output node is referenced by name below and must not be emitted alone.
    lines.extend(lvt_level2[:-1])
    lines.append(
        "* LVT balance input-load count={}: private BUF outputs never feed the chain or a DFF.".format(
            int(launch_balance_load_count)
        )
    )
    for index in range(int(launch_balance_load_count)):
        # This is a real standard-cell input capacitance, not an ideal C.
        # The loop is resolved while generating the deck, leaving HSPICE a
        # static physical topology for each diagnostic load-count experiment.
        lines.extend(
            [
                "* Load {} ports Y VDD VNW VPW VSS A = cal_lvt_balance_y{} vdd_a vdd_a vss_a vss_a CAL_LVT_MUX_L2_0.".format(index, index),
                "XCAL_LVT_BALANCE_LOAD_{} cal_lvt_balance_y{} vdd_a vdd_a vss_a vss_a CAL_LVT_MUX_L2_0 {}".format(index, index, buffer_cell),
            ]
        )
    lines.append("* Selected LVT launch node remains CAL_LVT_MUX_L2_0; private Y nodes cannot add series delay.")
    return lines


def render_real_dff_vernier_deck(
    rvt_cdl: Path,
    lvt_cdl: Path,
    model_library: Path,
    corner: str,
    temperature_c: float,
    vdd_v: float,
    rvt_cell: str,
    lvt_cell: str,
    dff_cell: str,
    stages: int,
    lvt_dummy_load_count: int,
    launch_offset_ps: float,
    launch_delayed_path: str,
    cal_sel: Optional[int] = None,
    buffer_cell: str = "",
    mux_cell: str = "",
    active_stage_mask: Optional[int] = None,
    q_read_time_ns: float = 2.5,
    stop_time_ns: float = 4.0,
    launch_balance_load_count: int = 2,
    rvt_launch_load_count: int = 0,
    timing_probe_stages: Optional[List[int]] = None,
) -> str:
    """Render the Step-6 same-rail chain plus 32 real comparator DFFs.

    The DFF positional CDL contract is ``Q VDD VNW VPW VSS CK D R``.  Every
    rail and well pin in every instance is tied to ``vdd_a``/``vss_a``; CK is
    the RVT tap, D is the LVT tap, and R is the shared active-high reset.  The
    selected launch branch is delayed with a real source timestamp only for
    this Step-6 isolation experiment.  Step 7 replaces that timestamp with the
    physical BUF/MXT2 calibration network.
    """

    vdd_v = finite(vdd_v, "VDD")
    if launch_delayed_path not in ("rvt", "lvt"):
        raise ValueError("launch_delayed_path must be 'rvt' or 'lvt'")
    if float(launch_offset_ps) < 0.0:
        raise ValueError("launch_offset_ps must not be negative")
    if cal_sel is not None and (int(cal_sel) < 0 or int(cal_sel) > 7):
        raise ValueError("cal_sel must be in [0, 7]")
    if cal_sel is not None and (not buffer_cell or not mux_cell):
        raise ValueError("physical CAL_SEL deck requires both BUF and MXT2 cell names")
    if float(q_read_time_ns) <= 0.0 or float(stop_time_ns) <= float(q_read_time_ns):
        raise ValueError("stop_time_ns must be greater than positive q_read_time_ns")
    if active_stage_mask is not None and (int(active_stage_mask) < 0 or int(active_stage_mask) >= (1 << int(stages))):
        raise ValueError("active_stage_mask must fit stages")
    if int(launch_balance_load_count) not in (0, 1, 2):
        raise ValueError("launch_balance_load_count must be 0, 1, or 2")
    if int(rvt_launch_load_count) < 0 or int(rvt_launch_load_count) > 7:
        raise ValueError("rvt_launch_load_count must be in [0, 7]")
    if timing_probe_stages is not None and any(int(index) < 0 or int(index) >= int(stages) for index in timing_probe_stages):
        raise ValueError("timing_probe_stages must fit stages")
    if not rvt_cdl.is_file() or not lvt_cdl.is_file() or not model_library.is_file():
        raise ValueError("RVT CDL, LVT CDL, and model library must all exist")
    launch_rvt_s = 1.000000000000e-09 + (float(launch_offset_ps) * 1.0e-12 if launch_delayed_path == "rvt" else 0.0)
    launch_lvt_s = 1.000000000000e-09 + (float(launch_offset_ps) * 1.0e-12 if launch_delayed_path == "lvt" else 0.0)
    include_lines = ['.include "{}"'.format(rvt_cdl.resolve())]
    # The Step-9 RVT/RVT control intentionally uses the RVT CDL on both
    # branches.  HSPICE needs one definition of each .SUBCKT, so avoid a
    # duplicate include while preserving separate cell instances below.
    if lvt_cdl.resolve() != rvt_cdl.resolve():
        include_lines.append('.include "{}"'.format(lvt_cdl.resolve()))
    lines = [
        "* Auto-generated Phase-3 Step-6 real-DFF Vernier deck.",
        "* All physical cells use one local same-rail domain: VDD_A=vdd_a and VSS_A=vss_a.",
        "* There is deliberately no separate reference supply source, node, or interface.",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3",
        ".temp {}".format(spice(temperature_c)),
        *include_lines,
        '.lib "{}" {}'.format(model_library.resolve(), corner),
        ".param VDD_VALUE={}".format(spice(vdd_v)),
        "",
        "* Common local supply for both chains, all wells, and the comparator bank.",
        "V_VDD_A vdd_a vss_a DC='VDD_VALUE'",
        "V_VSS_A vss_a 0 DC=0",
        "",
    ]
    if cal_sel is None:
        # Step 6 uses source delays only to determine the setup aperture of the
        # actual DFF bank.  The later physical calibration path follows the
        # other branch below and does not retain these behavioral timestamps.
        lines.extend(
            [
                "* The two launches differ only by the selected ideal Step-5 offset.",
                "* RVT launch delay = {:.12e} s; LVT launch delay = {:.12e} s.".format(launch_rvt_s, launch_lvt_s),
                "V_START_RVT start_rvt vss_a PULSE(0 'VDD_VALUE' {} 1.000000000000e-12 1.000000000000e-12 3.000000000000e-09 4.000000000000e-09)".format(spice(launch_rvt_s)),
                "V_START_LVT start_lvt vss_a PULSE(0 'VDD_VALUE' {} 1.000000000000e-12 1.000000000000e-12 3.000000000000e-09 4.000000000000e-09)".format(spice(launch_lvt_s)),
            ]
        )
        rvt_start_node = "start_rvt"
        lvt_start_node = "start_lvt"
    else:
        # CAL_SEL is held as a static rail-valid value before START_REQ rises.
        # This models a registered calibration setting and avoids selector
        # switching during the sensitive Vernier launch event.
        lines.extend(
            [
                "* Physical CAL_SEL={} launch network: all BUF/MXT2 cells use the local rails.".format(int(cal_sel)),
                "V_START_REQ start_req vss_a PULSE(0 'VDD_VALUE' 1.000000000000e-09 1.000000000000e-12 1.000000000000e-12 3.000000000000e-09 4.000000000000e-09)",
            ]
        )
        lines.extend(
            render_calibration_network(
                buffer_cell, mux_cell, int(cal_sel), int(launch_balance_load_count), int(rvt_launch_load_count)
            )
        )
        rvt_start_node = "CAL_RVT_MUX_L2_0"
        lvt_start_node = "CAL_LVT_MUX_L2_0"
    lines.extend(
        [
            "* Active-high asynchronous reset: hold Q low through startup, then release before launch.",
            "V_SENSOR_RESET sensor_reset vss_a PWL(0 'VDD_VALUE' 5.000000000000e-10 'VDD_VALUE' 5.100000000000e-10 0 {} 0)".format(spice(float(stop_time_ns) * 1.0e-09)),
            "",
            "* RVT path: every stage uses two real RVT inverters and common local wells.",
            render_vernier_chain("rvt", rvt_cell, stages, start_node=rvt_start_node),
            "",
            "* Companion path is either the preserved LVT+d1 topology or the static wide-range sparse topology.",
            render_vernier_chain("lvt", lvt_cell, stages, dummy_cell=lvt_cell, dummy_load_count=lvt_dummy_load_count, start_node=lvt_start_node)
            if active_stage_mask is None else render_sparse_companion_chain(rvt_cell, lvt_cell, stages, int(active_stage_mask), lvt_start_node),
            "",
            "* DFF port mapping: Q VDD VNW VPW VSS CK D R = raw_q vdd_a vdd_a vss_a vss_a rvt_tap lvt_tap sensor_reset.",
        ]
    )
    for index in range(int(stages)):
        lines.extend(
            [
                "* Comparator {:03d}: D=LVT tap, CK=RVT tap, all supply/well pins on VDD_A/VSS_A.".format(index),
                "XCOMP_{:03d} raw_q_{:03d} vdd_a vdd_a vss_a vss_a rvt_tap_{:03d} lvt_tap_{:03d} sensor_reset {}".format(
                    index, index, index, index, dff_cell
                ),
            ]
        )
    lines.extend(
        [
            "",
            ".tran 1.000000000000e-13 {}".format(spice(float(stop_time_ns) * 1.0e-09)),
            "* Read reset while asserted and Q after all stage clocks have arrived.",
            "* These four tap probes prove that the launch sources reach both chain ends under DFF loading.",
            ".measure tran rvt_000_probe FIND v(rvt_tap_000,vss_a) AT={}".format(spice(float(q_read_time_ns) * 1.0e-09)),
            ".measure tran rvt_031_probe FIND v(rvt_tap_031,vss_a) AT={}".format(spice(float(q_read_time_ns) * 1.0e-09)),
            ".measure tran lvt_000_probe FIND v(lvt_tap_000,vss_a) AT={}".format(spice(float(q_read_time_ns) * 1.0e-09)),
            ".measure tran lvt_031_probe FIND v(lvt_tap_031,vss_a) AT={}".format(spice(float(q_read_time_ns) * 1.0e-09)),
            "* Final-tap arrival measurements expose the accumulated physical RVT/LVT delay difference.",
            ".measure tran rvt_031_cross WHEN v(rvt_tap_031,vss_a) VAL='VDD_VALUE/2' RISE=1",
            ".measure tran lvt_031_cross WHEN v(lvt_tap_031,vss_a) VAL='VDD_VALUE/2' RISE=1",
            ".measure tran rvt_lvt_diff_031 PARAM='lvt_031_cross-rvt_031_cross'",
        ]
    )
    if timing_probe_stages:
        # Debug probes are .measure statements only: they neither connect a
        # new electrical load nor change CK/D wiring.  Naming follows the
        # exported CSV contract (CK=RVT, D=companion) for direct aperture
        # inspection at five representative locations.
        lines.extend(
            [
                "* Calibration timing probes: launch crossings and selected D/CK tap skews are read-only diagnostics.",
                ".measure tran rvt_launch_cross WHEN v({},vss_a) VAL='VDD_VALUE/2' RISE=1".format(rvt_start_node),
                ".measure tran companion_launch_cross WHEN v({},vss_a) VAL='VDD_VALUE/2' RISE=1".format(lvt_start_node),
                ".measure tran launch_d_minus_ck PARAM='companion_launch_cross-rvt_launch_cross'",
            ]
        )
        for index in timing_probe_stages:
            lines.extend(
                [
                    ".measure tran ck_{:03d}_cross WHEN v(rvt_tap_{:03d},vss_a) VAL='VDD_VALUE/2' RISE=1".format(index, index),
                    ".measure tran d_{:03d}_cross WHEN v(lvt_tap_{:03d},vss_a) VAL='VDD_VALUE/2' RISE=1".format(index, index),
                    ".measure tran d_minus_ck_{:03d} PARAM='d_{:03d}_cross-ck_{:03d}_cross'".format(index, index, index),
                ]
            )
    for index in range(int(stages)):
        lines.extend(
            [
                ".measure tran q_{:03d}_reset_level FIND v(raw_q_{:03d},vss_a) AT=2.500000000000e-10".format(index, index),
                ".measure tran q_{:03d}_level FIND v(raw_q_{:03d},vss_a) AT={}".format(index, index, spice(float(q_read_time_ns) * 1.0e-09)),
            ]
        )
    lines.extend([".end", ""])
    return "\n".join(lines)


def write_real_dff_vernier_deck(**kwargs: Any) -> str:
    """Write one task-owned Step-6 deck and return its rendered text."""

    output_path = Path(kwargs.pop("output_path"))
    text = render_real_dff_vernier_deck(**kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="ascii")
    return text
