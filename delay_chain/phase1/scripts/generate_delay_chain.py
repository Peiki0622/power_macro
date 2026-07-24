#!/usr/bin/env python3
"""Render one SMIC40LL phase-1 delay-chain HSPICE deck.

This module owns only circuit rendering.  It deliberately does not launch
HSPICE or interpret a result file: separating those responsibilities lets the
runner make one auditable deck per voltage point and lets tests inspect the
electrical connectivity without needing an EDA license.

The electrical interface is positional because the foundry CDL is positional.
``INV_X0P5M_A9TR40`` has the public port order ``Y VDD VNW VPW VSS A``:

* ``Y`` is the inverter output.
* ``VDD`` and ``VNW`` are both connected to local ``VDD_A``.  ``VNW`` is the
  n-well tie and is an electrical terminal, not optional metadata.
* ``VPW`` and ``VSS`` are both connected to local ``VSS_A`` for the same
  reason on the p-well/ground side.
* ``A`` is the inverter input.

Two inverter instances form every observed delay unit.  This makes the unit
non-inverting, so a single rising START edge produces rising crossings at all
tap nodes and a fixed-time sample can be decoded as a thermometer code.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


# The expected order is frozen here as a second, executable guard against a
# future config accidentally treating an SPICE subcircuit like named-port RTL.
EXPECTED_INVERTER_PORTS = ["Y", "VDD", "VNW", "VPW", "VSS", "A"]


def repository_root() -> Path:
    """Return the workspace root from this script's stable source location.

    The source tree is ``power_macro/delay_chain/phase1/scripts`` below the
    workspace.  Resolving relative input paths against that root, instead of
    the caller's current directory, keeps generated decks reproducible when
    the command is launched by CI or from a task-owned run directory.
    """

    return Path(__file__).resolve().parents[4]


def require_config(config: Dict[str, Any], name: str) -> Any:
    """Return one required config value and reject absent/null values early."""

    value = config.get(name)
    if value is None:
        raise ValueError("phase-1 config is missing required key: {}".format(name))
    return value


def load_config(config_path: Path) -> Dict[str, Any]:
    """Load and validate the narrow electrical contract needed by this module.

    Validation intentionally checks only rendering prerequisites.  File
    existence, HSPICE version and output-directory ownership are runner-level
    concerns because rendering a deck should remain usable in unit tests.
    """

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError("phase-1 config does not exist: {}".format(config_path)) from error
    except json.JSONDecodeError as error:
        raise ValueError("phase-1 config is not valid JSON: {}".format(error)) from error

    if not isinstance(config, dict):
        raise ValueError("phase-1 config top level must be an object")
    for name in (
        "cell_cdl",
        "model_library",
        "inverter_cell",
        "inverter_ports",
        "start_edge_s",
        "start_rise_s",
        "tran_max_step_s",
        "tran_stop_s",
        "power_window_start_s",
        "power_window_stop_s",
        "temperature_c",
    ):
        require_config(config, name)
    if config["inverter_ports"] != EXPECTED_INVERTER_PORTS:
        raise ValueError(
            "inverter port contract must be {}; received {}".format(
                EXPECTED_INVERTER_PORTS, config["inverter_ports"]
            )
        )
    if float(config["tran_stop_s"]) <= float(config["start_edge_s"]):
        raise ValueError("transient stop time must be later than the START edge")
    if float(config["power_window_stop_s"]) <= float(config["power_window_start_s"]):
        raise ValueError("power measurement window must have positive duration")
    return config


def resolve_input_path(value: str) -> Path:
    """Resolve a config path without changing absolute PDK path semantics."""

    candidate = Path(value)
    return candidate if candidate.is_absolute() else repository_root() / candidate


def spice_number(value: float) -> str:
    """Format a finite numeric literal in an unambiguous HSPICE-safe form."""

    return "{:.12e}".format(float(value))


def tap_measure_names(chain_units: int) -> List[str]:
    """Return deterministic, HSPICE-safe first-crossing measure names."""

    if chain_units <= 0:
        raise ValueError("chain_units must be positive")
    return ["tap_{:03d}_cross".format(index) for index in range(chain_units)]


def render_inverter(instance_name: str, output_node: str, input_node: str, cell_name: str) -> List[str]:
    """Render one fully documented positional standard-cell SPICE instance.

    Returning a two-line block keeps the generated deck readable during manual
    review.  The comment directly names every positional port before the
    instance line, preventing a future maintainer from silently swapping a
    well terminal or assuming Verilog named-port behavior.
    """

    return [
        "* {} ports: Y={} VDD=VDD_A VNW=VDD_A VPW=VSS_A VSS=VSS_A A={}.".format(
            instance_name, output_node, input_node
        ),
        "{} {} vdd_a vdd_a vss_a vss_a {} {}".format(
            instance_name, output_node, input_node, cell_name
        ),
    ]


def render_delay_chain(chain_units: int, cell_name: str) -> List[str]:
    """Render exactly two inverters and one rising-polarity tap per delay unit."""

    if chain_units <= 0:
        raise ValueError("chain_units must be positive")

    lines = [
        "* Delay chain interface: START drives unit 0; TAP_i is the output after two inversions.",
        "* Each unit is non-inverting.  No DFF or artificial output load is present in phase 1.",
    ]
    previous_node = "start"
    for index in range(chain_units):
        midpoint = "unit_{:03d}_mid".format(index)
        tap = "tap_{:03d}".format(index)
        lines.append("* Delay unit {:03d}: {} -> inverter A -> {} -> inverter B -> {}.".format(index, previous_node, midpoint, tap))
        lines.extend(render_inverter("XINV_{:03d}_A".format(index), midpoint, previous_node, cell_name))
        lines.extend(render_inverter("XINV_{:03d}_B".format(index), tap, midpoint, cell_name))
        previous_node = tap
    return lines


def render_deck(config: Dict[str, Any], chain_units: int, vdd_v: float) -> str:
    """Create a complete constant-supply characterization deck.

    ``V_VDD`` is intentionally connected directly across ``VDD_A``/``VSS_A``
    in phase 1.  The names already match the later shared-PDN interface, while
    the ideal source isolates delay sensitivity from package impedance.  The
    later RLC phase must replace this source rather than interpreting phase-1
    current measurements as a local voltage-disturbance result.
    """

    if chain_units not in (16, 32, 64):
        raise ValueError("phase-1 chain_units must be one of 16, 32, 64")
    if vdd_v <= 0.0:
        raise ValueError("VDD must be positive")

    cdl_path = resolve_input_path(str(config["cell_cdl"]))
    model_path = resolve_input_path(str(config["model_library"]))
    cell_name = str(config["inverter_cell"])
    measures = tap_measure_names(chain_units)

    lines = [
        "* Auto-generated SMIC40LL phase-1 constant-VDD delay-chain deck.",
        "* chain_units={} inverter_count={} VDD_A-VSS_A={} V.".format(
            chain_units, chain_units * 2, spice_number(vdd_v)
        ),
        "* CDL and model remain read-only source collateral; this deck contains no copied PDK content.",
        ".option post=0 nomod measform=3 runlvl=3",
        ".temp {}".format(spice_number(float(config["temperature_c"]))),
        '.include "{}"'.format(cdl_path),
        '.lib "{}" {}'.format(model_path, str(config.get("corner", "tt"))),
        ".param VDD_VALUE={}".format(spice_number(vdd_v)),
        "",
        "* Local rail contract: V_VDD is the only phase-1 ideal source across VDD_A/VSS_A.",
        "* V_VSS defines the local return relative to global node 0 without bypassing the differential rail.",
        "V_VDD vdd_a vss_a DC='VDD_VALUE'",
        "V_VSS vss_a 0 DC=0",
        "* START is referenced to VSS_A, rises once after settling, and remains high past transient stop.",
        "V_START start vss_a PULSE(0 'VDD_VALUE' {} {} {} 1.000000000000e-07 2.000000000000e-07)".format(
            spice_number(float(config["start_edge_s"])),
            spice_number(float(config["start_rise_s"])),
            spice_number(float(config["start_rise_s"])),
        ),
        "",
    ]
    lines.extend(render_delay_chain(chain_units, cell_name))
    lines.extend(
        [
            "",
            "* One-picosecond maximum step resolves the 10 ps START edge and all standard-cell crossings.",
            ".tran {} {}".format(
                spice_number(float(config["tran_max_step_s"])), spice_number(float(config["tran_stop_s"]))
            ),
            "* All timing crossings use the instantaneous constant local-rail midpoint, VDD_VALUE/2.",
        ]
    )
    lines.append(".measure tran start_cross WHEN v(start,vss_a)='VDD_VALUE/2' RISE=1")
    for index, measure_name in enumerate(measures):
        lines.append(
            ".measure tran {} WHEN v(tap_{:03d},vss_a)='VDD_VALUE/2' RISE=1".format(measure_name, index)
        )
    lines.extend(
        [
            "* A delay unit is exactly the first pair of inverters; full-chain delay ends at the final observed tap.",
            ".measure tran stage_delay_s PARAM='tap_000_cross-start_cross'",
            ".measure tran chain_delay_s PARAM='{}-start_cross'".format(measures[-1]),
            "* HSPICE reports current entering V_VDD's positive terminal; negate it to report consumed rail current.",
            ".measure tran i_avg_a AVG par('-i(V_VDD)') FROM={} TO={}".format(
                spice_number(float(config["power_window_start_s"])),
                spice_number(float(config["power_window_stop_s"])),
            ),
            ".measure tran i_peak_a MAX par('-i(V_VDD)') FROM={} TO={}".format(
                spice_number(float(config["power_window_start_s"])),
                spice_number(float(config["power_window_stop_s"])),
            ),
            ".measure tran power_avg_w PARAM='VDD_VALUE*i_avg_a'",
            ".end",
            "",
        ]
    )
    return "\n".join(lines)


def write_deck(config: Dict[str, Any], chain_units: int, vdd_v: float, output_path: Path) -> None:
    """Render one deck and create only its explicitly requested parent directory."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_deck(config, chain_units, vdd_v), encoding="ascii")


def build_argument_parser() -> argparse.ArgumentParser:
    """Define the small CLI used by tests and by manual deck inspection."""

    parser = argparse.ArgumentParser(description="Generate one phase-1 SMIC40LL delay-chain HSPICE deck")
    parser.add_argument("--config", required=True, type=Path, help="phase1_config.json path")
    parser.add_argument("--chain-units", required=True, type=int, choices=(16, 32, 64))
    parser.add_argument("--vdd-v", required=True, type=float, help="constant VDD_A-VSS_A voltage in volts")
    parser.add_argument("--output", required=True, type=Path, help="new or replaceable deck file path")
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Render the requested deck; execution remains the runner's responsibility."""

    args = build_argument_parser().parse_args(argv)
    config = load_config(args.config)
    write_deck(config, args.chain_units, args.vdd_v, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
