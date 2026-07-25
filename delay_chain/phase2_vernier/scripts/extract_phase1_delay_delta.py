#!/usr/bin/env python3
"""Extract measured sensing-stage delay shifts at the 765 MHz timing anchors.

The source CSV is produced by ``run_phase1_anchor_sweep.py`` and therefore
contains direct HSPICE measurements, not values recovered from a plot.  This
script treats every missing, duplicate, non-finite, or voltage-mismatched row
as an error because a fabricated sensitivity would corrupt the Vernier design
choice that follows.
"""

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List


ANCHOR_KINDS = (
    "anchor_nominal",
    "anchor_last_passing",
    "anchor_first_violation",
)


def finite_float(row: Dict[str, str], field: str, context: str) -> float:
    """Read one required measured scalar without converting absent data to zero."""

    value = row.get(field, "").strip()
    if not value:
        raise ValueError("{} lacks {}".format(context, field))
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError("{} has nonnumeric {}={!r}".format(context, field, value)) from error
    if not math.isfinite(parsed):
        raise ValueError("{} has non-finite {}={!r}".format(context, field, value))
    return parsed


def read_rows(path: Path) -> List[Dict[str, str]]:
    """Load the rectangular anchor CSV and reject an empty execution result."""

    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("anchor CSV is empty: {}".format(path))
    return rows


def summarize_chain(rows: List[Dict[str, str]], expected_voltages: List[float], chain_units: int) -> Dict[str, Any]:
    """Produce one traceable delay summary for one serial-chain loading context.

    ``stage_delay_s`` is the first non-inverting stage's measured propagation
    time.  It is the appropriate sensing-unit metric because every interior
    stage drives the same inverter input topology; full-chain delay is retained
    as corroborating evidence, rather than being divided and thereby mixing in
    endpoint loading.
    """

    selected = [row for row in rows if int(row.get("chain_units", "0")) == chain_units]
    by_kind: Dict[str, Dict[str, str]] = {}
    for row in selected:
        kind = row.get("scenario_kind", "")
        if kind in ANCHOR_KINDS:
            if kind in by_kind:
                raise ValueError("chain {} has duplicate {} row".format(chain_units, kind))
            by_kind[kind] = row
    if set(by_kind) != set(ANCHOR_KINDS):
        raise ValueError("chain {} is missing one or more anchor rows".format(chain_units))

    measurements: Dict[str, Dict[str, float]] = {}
    for index, kind in enumerate(ANCHOR_KINDS):
        row = by_kind[kind]
        context = "chain {} {}".format(chain_units, kind)
        voltage = finite_float(row, "vdd_v", context)
        if abs(voltage - expected_voltages[index]) > 1.0e-12:
            raise ValueError("{} voltage {} does not match configured anchor {}".format(context, voltage, expected_voltages[index]))
        measurements[kind] = {
            "vdd_v": voltage,
            "stage_delay_s": finite_float(row, "stage_delay_s", context),
            "chain_delay_s": finite_float(row, "chain_delay_s", context),
            "avg_power_w": finite_float(row, "power_avg_w", context),
            "peak_current_a": finite_float(row, "i_peak_a", context),
        }

    nominal = measurements["anchor_nominal"]
    last_passing = measurements["anchor_last_passing"]
    failing = measurements["anchor_first_violation"]
    epsilon = failing["stage_delay_s"] - nominal["stage_delay_s"]
    return {
        "chain_units": chain_units,
        "anchors": measurements,
        "epsilon_nominal_to_first_violation_s": epsilon,
        "relative_delay_change_percent": 100.0 * epsilon / nominal["stage_delay_s"],
        "last_passing_delay_delta_s": last_passing["stage_delay_s"] - nominal["stage_delay_s"],
        "last_passing_relative_delay_change_percent": 100.0
        * (last_passing["stage_delay_s"] - nominal["stage_delay_s"])
        / nominal["stage_delay_s"],
    }


def write_report(path: Path, summary: Dict[str, Any], source_csv: Path) -> None:
    """Write a concise, human-reviewable report without rounding source evidence."""

    lines = [
        "# 765 MHz Phase-1 Delay Delta",
        "",
        "Source CSV: `{}`".format(source_csv),
        "",
        "The values below are direct HSPICE measures of the first non-inverting",
        "sensing stage.  No image measurement, interpolation, or analytical delay",
        "model is used.",
        "",
        "| Chain units | Vnom stage delay (s) | V35 stage delay (s) | V40 stage delay (s) | epsilon Vnom->V40 (s) | change (%) |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for chain in summary["chains"]:
        anchors = chain["anchors"]
        lines.append(
            "| {chain_units} | {nominal:.12e} | {last:.12e} | {failing:.12e} | {epsilon:.12e} | {percent:.9f} |".format(
                chain_units=chain["chain_units"],
                nominal=anchors["anchor_nominal"]["stage_delay_s"],
                last=anchors["anchor_last_passing"]["stage_delay_s"],
                failing=anchors["anchor_first_violation"]["stage_delay_s"],
                epsilon=chain["epsilon_nominal_to_first_violation_s"],
                percent=chain["relative_delay_change_percent"],
            )
        )
    lines.extend(
        [
            "",
            "## Vernier reference",
            "",
            "The 16-unit first-stage result is selected as the nominal unloaded",
            "sensing-stage reference for the first Vernier sweep.  The next step",
            "measures each reference-stage dummy-load variant directly before any",
            "candidate is accepted.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_argument_parser() -> argparse.ArgumentParser:
    """Define input and output paths explicitly to make result provenance visible."""

    parser = argparse.ArgumentParser(description="extract 765 MHz phase-1 delay sensitivity")
    parser.add_argument("--config", required=True, type=Path, help="Phase 2 configuration")
    parser.add_argument("--input-csv", required=True, type=Path, help="raw 3x3 HSPICE anchor CSV")
    parser.add_argument("--output-json", required=True, type=Path, help="structured sensitivity output")
    parser.add_argument("--output-report", required=True, type=Path, help="Markdown sensitivity report")
    return parser


def main(argv: Iterable[str] = None) -> int:
    """Extract all chain contexts and publish JSON plus a reviewable table."""

    args = build_argument_parser().parse_args(argv)
    with args.config.open(encoding="utf-8") as stream:
        config = json.load(stream)
    expected_voltages = [float(value) for value in config["phase1_anchor_voltages_v"]]
    rows = read_rows(args.input_csv)
    chain_units = sorted({int(row["chain_units"]) for row in rows})
    chains = [summarize_chain(rows, expected_voltages, units) for units in chain_units]
    selected = next((chain for chain in chains if chain["chain_units"] == 16), None)
    if selected is None:
        raise ValueError("anchor CSV lacks the required 16-unit stage reference")
    summary = {
        "schema_version": 1,
        "source_csv": str(args.input_csv.resolve()),
        "selected_sense_stage_reference": selected,
        "chains": chains,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(args.output_report, summary, args.input_csv.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
