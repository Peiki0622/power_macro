#!/usr/bin/env python3
"""Convert phase-1 HSPICE crossings into calibration data and a chain choice.

The input is the raw CSV emitted by ``run_dc_sweep.py``.  The analysis does not
re-run SPICE and does not infer unavailable waveforms: for each candidate it
derives one fixed sample time from the nominal tap crossings, then compares the
already measured crossings to that time.  This exactly models a later sampler
at a fixed instant while keeping phase 1 free of DFF loading.

The public calibration row exposes ``VDD_A -> propagation_code`` together with
the measured delay and current values.  A code is valid only when it is a
contiguous prefix of ones followed by zeros; a later one after an earlier zero
is a bubble and causes the candidate to fail rather than being silently
"corrected" in this pre-digital-backend stage.
"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import generate_delay_chain  # noqa: E402  # Direct-script import is deliberate.


CALIBRATION_FIELDS = [
    "scenario_id",
    "scenario_kind",
    "chain_units",
    "inverter_count",
    "vdd_v",
    "sample_time_s",
    "stage_delay_s",
    "chain_delay_s",
    "propagation_code",
    "thermometer_bits",
    "is_thermometer",
    "crossings_strictly_ordered",
    "avg_power_w",
    "peak_current_a",
]


def required_float(row: Dict[str, str], field: str) -> float:
    """Read one finite CSV scalar; raw execution output must never be guessed."""

    value = row.get(field, "").strip()
    if not value:
        raise ValueError("raw row lacks required field {}".format(field))
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError("raw row has nonnumeric {}={!r}".format(field, value)) from error
    if not math.isfinite(parsed):
        raise ValueError("raw row has non-finite {}={!r}".format(field, value))
    return parsed


def optional_float(row: Dict[str, str], field: str) -> Optional[float]:
    """Preserve a late/failed tap crossing as None instead of fabricating time."""

    value = row.get(field, "").strip()
    if not value:
        return None
    parsed = required_float(row, field)
    return parsed


def tap_crossings(row: Dict[str, str], chain_units: int) -> List[Optional[float]]:
    """Return observed first crossings in physical tap order 0 through N-1."""

    return [optional_float(row, "tap_{:03d}_cross_s".format(index)) for index in range(chain_units)]


def strictly_ordered(crossings: Sequence[Optional[float]]) -> bool:
    """Check propagation order while accepting only a missing suffix, never a hole.

    A physical delay chain may not have reached its final taps by transient
    stop.  Those absent crossings are valid only as a suffix; an observed tap
    after an absent predecessor would contradict the serial connectivity and is
    treated as invalid raw evidence.
    """

    previous = None
    missing_seen = False
    for crossing in crossings:
        if crossing is None:
            missing_seen = True
            continue
        if missing_seen or (previous is not None and crossing <= previous):
            return False
        previous = crossing
    return True


def thermometer_code(crossings: Sequence[Optional[float]], sample_time_s: float) -> Tuple[int, str, bool]:
    """Decode a fixed-time prefix code and report bubbles without correcting them."""

    bits = [1 if crossing is not None and crossing <= sample_time_s else 0 for crossing in crossings]
    zero_seen = False
    is_thermometer = True
    for bit in bits:
        if bit == 0:
            zero_seen = True
        elif zero_seen:
            is_thermometer = False
            break
    return sum(bits), "".join(str(bit) for bit in bits), is_thermometer


def nominal_sample_time(rows: Sequence[Dict[str, str]], chain_units: int) -> float:
    """Place Tsample between the two middle nominal taps to force K=N/2 exactly.

    For even N, taps ``N/2-1`` and ``N/2`` bracket the desired boundary.  The
    arithmetic midpoint is fixed for all voltage points of this candidate; it
    is never recalculated from a drooped result, because that would hide the
    voltage-induced delay shift the sensor is intended to expose.
    """

    nominal_rows = [row for row in rows if row["scenario_kind"] == "canonical_000mv"]
    if len(nominal_rows) != 1:
        raise ValueError("chain {} needs exactly one nominal raw row".format(chain_units))
    crossings = tap_crossings(nominal_rows[0], chain_units)
    left = crossings[chain_units // 2 - 1]
    right = crossings[chain_units // 2]
    if left is None or right is None or right <= left:
        raise ValueError("nominal middle taps cannot define fixed sample time for chain {}".format(chain_units))
    return (left + right) / 2.0


def analyze_chain(rows: Sequence[Dict[str, str]], first_violation_v: float) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Analyze one chain length and return calibration rows plus deterministic status.

    The selection rules are intentionally mechanical:

    * nominal code must equal the chain midpoint;
    * every row must be a bubble-free thermometer code with serially ordered taps;
    * canonical code must not increase as VDD decreases;
    * 0.95 V must remain strictly inside the code range;
    * the exact first-violation point must differ from nominal by at least two.

    If no 16/32/64 candidate passes, the resulting study is complete but its
    status is ``NO_FEASIBLE_CANDIDATE``.  The script does not add an unplanned
    chain length or conceal the shortfall.
    """

    if not rows:
        raise ValueError("cannot analyze an empty chain row set")
    chain_units = int(rows[0]["chain_units"])
    if any(int(row["chain_units"]) != chain_units for row in rows):
        raise ValueError("mixed chain lengths passed to analyze_chain")
    sample_time_s = nominal_sample_time(rows, chain_units)
    calibrated = []
    for row in rows:
        crossings = tap_crossings(row, chain_units)
        code, bits, is_thermometer = thermometer_code(crossings, sample_time_s)
        calibrated.append(
            {
                "scenario_id": row["scenario_id"],
                "scenario_kind": row["scenario_kind"],
                "chain_units": chain_units,
                "inverter_count": int(row["inverter_count"]),
                "vdd_v": required_float(row, "vdd_v"),
                "sample_time_s": sample_time_s,
                "stage_delay_s": optional_float(row, "stage_delay_s"),
                "chain_delay_s": optional_float(row, "chain_delay_s"),
                "propagation_code": code,
                "thermometer_bits": bits,
                "is_thermometer": is_thermometer,
                "crossings_strictly_ordered": strictly_ordered(crossings),
                "avg_power_w": required_float(row, "power_avg_w"),
                "peak_current_a": required_float(row, "i_peak_a"),
            }
        )

    by_kind = {row["scenario_kind"]: row for row in calibrated}
    nominal = by_kind.get("canonical_000mv")
    violation = by_kind.get("first_violation")
    target_min = [row for row in calibrated if abs(row["vdd_v"] - 0.95) <= 1.0e-12]
    if nominal is None or violation is None or len(target_min) != 1:
        raise ValueError("chain {} is missing nominal, first-violation, or 0.95 V result".format(chain_units))
    canonical = sorted(
        [row for row in calibrated if row["scenario_kind"].startswith("canonical_")],
        key=lambda row: row["vdd_v"],
        reverse=True,
    )
    monotonic = all(
        canonical[index + 1]["propagation_code"] <= canonical[index]["propagation_code"]
        for index in range(len(canonical) - 1)
    )
    all_thermometer = all(row["is_thermometer"] for row in calibrated)
    all_ordered = all(row["crossings_strictly_ordered"] for row in calibrated)
    code_delta = nominal["propagation_code"] - violation["propagation_code"]
    max_drop_code = target_min[0]["propagation_code"]
    feasibility_checks = {
        "nominal_midpoint": nominal["propagation_code"] == chain_units // 2,
        "bubble_free_thermometer": all_thermometer,
        "ordered_serial_crossings": all_ordered,
        "monotonic_code_vs_vdd": monotonic,
        "max_drop_resolvable": 1 <= max_drop_code <= chain_units - 1,
        "first_violation_code_delta_at_least_2": code_delta >= 2,
    }
    feasible = all(feasibility_checks.values())
    return calibrated, {
        "chain_units": chain_units,
        "inverter_count": chain_units * 2,
        "sample_time_s": sample_time_s,
        "first_violation_voltage_v": first_violation_v,
        "first_violation_code_delta": code_delta,
        "max_drop_code": max_drop_code,
        "nominal_avg_power_w": nominal["avg_power_w"],
        "nominal_peak_current_a": nominal["peak_current_a"],
        "feasibility_checks": feasibility_checks,
        "feasible": feasible,
    }


def read_raw_rows(path: Path) -> List[Dict[str, str]]:
    """Read raw runner evidence and require it to have at least one scenario."""

    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("raw sweep CSV is empty: {}".format(path))
    return rows


def write_calibration_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    """Write the public, phase-1 voltage-to-code calibration interface."""

    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CALIBRATION_FIELDS, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            rendered = {}
            for field in CALIBRATION_FIELDS:
                value = row[field]
                if value is None:
                    rendered[field] = ""
                elif isinstance(value, float):
                    rendered[field] = "{:.12e}".format(value)
                else:
                    rendered[field] = str(value)
            writer.writerow(rendered)


def choose_candidate(summaries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply the declared deterministic ranking without subjective adjustment."""

    feasible = [summary for summary in summaries if summary["feasible"]]
    if not feasible:
        return {"status": "NO_FEASIBLE_CANDIDATE", "selected_chain_units": None}
    selected = min(
        feasible,
        key=lambda summary: (
            abs(summary["first_violation_code_delta"] - 2.5),
            summary["nominal_peak_current_a"],
            summary["nominal_avg_power_w"],
            summary["chain_units"],
        ),
    )
    return {
        "status": "PASS",
        "selected_chain_units": selected["chain_units"],
        "selected_sample_time_s": selected["sample_time_s"],
    }


def write_selection_report(path: Path, summaries: Sequence[Dict[str, Any]], decision: Dict[str, Any]) -> None:
    """Publish a human-readable report that exposes every acceptance predicate."""

    lines = [
        "# Phase-1 Delay-Chain Selection",
        "",
        "This report covers constant-VDD TT/1.10 V/25 C characterization only.",
        "Package RLC self-disturbance and timing-margin impact are intentionally deferred to phase 3.",
        "",
        "## Decision",
        "",
        "status={}".format(decision["status"]),
        "selected_chain_units={}".format(decision.get("selected_chain_units")),
        "",
        "## Candidate Evidence",
        "",
        "| units | Tsample (s) | delta K at Vfail | K at 0.95 V | Pavg nominal (W) | Ipeak nominal (A) | feasible |",
        "|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for summary in sorted(summaries, key=lambda item: item["chain_units"]):
        lines.append(
            "| {chain_units} | {sample_time_s:.12e} | {first_violation_code_delta} | {max_drop_code} | "
            "{nominal_avg_power_w:.12e} | {nominal_peak_current_a:.12e} | {feasible} |".format(**summary)
        )
        for name, value in summary["feasibility_checks"].items():
            lines.append("  - chain_{} {}={}".format(summary["chain_units"], name, value))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_phase_summary(path: Path, manifest: Dict[str, Any], summaries: Sequence[Dict[str, Any]], decision: Dict[str, Any]) -> None:
    """Write the concise phase boundary and outcome needed by the next stage.

    This is deliberately a summary rather than another data source.  The raw
    CSV remains the authoritative per-scenario evidence, while this file makes
    the one valid conclusion explicit: whether the specified 16/32/64 search
    has selected a chain under the first-violation sensitivity rule.
    """

    lines = [
        "# Phase-1 Constant-VDD Summary",
        "",
        "## Scope",
        "",
        "TT corner at 25 C; ideal constant VDD_A/VSS_A source; no RLC, DFF, encoder, or PVT sweep.",
        "",
        "## Result",
        "",
        "status={}".format(decision["status"]),
        "selected_chain_units={}".format(decision.get("selected_chain_units")),
        "first_violation_voltage_v={:.12e}".format(float(manifest["scan"]["first_violation_voltage_v"])),
        "",
        "## Candidate Metrics",
        "",
    ]
    for summary in sorted(summaries, key=lambda item: item["chain_units"]):
        lines.extend(
            [
                "chain_units={}".format(summary["chain_units"]),
                "sample_time_s={:.12e}".format(summary["sample_time_s"]),
                "first_violation_code_delta={}".format(summary["first_violation_code_delta"]),
                "max_drop_code={}".format(summary["max_drop_code"]),
                "nominal_avg_power_w={:.12e}".format(summary["nominal_avg_power_w"]),
                "nominal_peak_current_a={:.12e}".format(summary["nominal_peak_current_a"]),
                "feasible={}".format(summary["feasible"]),
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation Boundary",
            "",
            "Ideal-source current is only a phase-1 sensor-load proxy.  Shared-PDN voltage perturbation,",
            "timing slack, attack-bank coupling, and dynamic droop response require later phases.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_plots(run_dir: Path, rows: Sequence[Dict[str, Any]]) -> None:
    """Render three compact figures from measured CSV values using matplotlib.

    Plot generation stays in this final analysis stage so a failed HSPICE run
    cannot leave graphics that appear to represent a complete characterization.
    The function has no effect on source collateral or raw EDA evidence.
    """

    import matplotlib.pyplot as plt

    figures = run_dir / "figures"
    figures.mkdir(exist_ok=True)
    chains = sorted(set(row["chain_units"] for row in rows))

    figure, axis = plt.subplots(figsize=(7, 4.5))
    for chain_units in chains:
        points = sorted(
            [row for row in rows if row["chain_units"] == chain_units and row["scenario_kind"].startswith("canonical_")],
            key=lambda row: row["vdd_v"],
        )
        axis.plot([row["vdd_v"] for row in points], [row["propagation_code"] for row in points], marker="o", label="{} units".format(chain_units))
    axis.set_xlabel("VDD_A - VSS_A (V)")
    axis.set_ylabel("Propagation code K")
    axis.grid(True)
    axis.legend()
    figure.tight_layout()
    figure.savefig(str(figures / "code_vs_voltage.png"), dpi=160)
    plt.close(figure)

    figure, axes = plt.subplots(2, 1, figsize=(7, 7), sharex=True)
    for chain_units in chains:
        points = sorted(
            [row for row in rows if row["chain_units"] == chain_units and row["scenario_kind"].startswith("canonical_")],
            key=lambda row: row["vdd_v"],
        )
        # A late final tap can make a delay measure unavailable.  Plot only
        # finite measured points; the selection report still marks that chain
        # infeasible through ordered-crossing checks instead of hiding it.
        stage_points = [row for row in points if row["stage_delay_s"] is not None]
        chain_points = [row for row in points if row["chain_delay_s"] is not None]
        axes[0].plot([row["vdd_v"] for row in stage_points], [row["stage_delay_s"] * 1.0e12 for row in stage_points], marker="o", label="{} units".format(chain_units))
        axes[1].plot([row["vdd_v"] for row in chain_points], [row["chain_delay_s"] * 1.0e9 for row in chain_points], marker="o", label="{} units".format(chain_units))
    axes[0].set_ylabel("Single-unit delay (ps)")
    axes[1].set_ylabel("Full-chain delay (ns)")
    axes[1].set_xlabel("VDD_A - VSS_A (V)")
    for axis in axes:
        axis.grid(True)
        axis.legend()
    figure.tight_layout()
    figure.savefig(str(figures / "delay_vs_voltage.png"), dpi=160)
    plt.close(figure)

    nominal = sorted([row for row in rows if row["scenario_kind"] == "canonical_000mv"], key=lambda row: row["chain_units"])
    figure, axis_power = plt.subplots(figsize=(7, 4.5))
    positions = list(range(len(nominal)))
    axis_power.bar([position - 0.2 for position in positions], [row["avg_power_w"] * 1.0e6 for row in nominal], width=0.4, label="Average power (uW)")
    axis_current = axis_power.twinx()
    axis_current.bar([position + 0.2 for position in positions], [row["peak_current_a"] * 1.0e6 for row in nominal], width=0.4, color="tab:orange", label="Peak current (uA)")
    axis_power.set_xticks(positions)
    axis_power.set_xticklabels([str(row["chain_units"]) for row in nominal])
    axis_power.set_xlabel("Non-inverting delay units")
    axis_power.set_ylabel("Average power (uW)")
    axis_current.set_ylabel("Peak current (uA)")
    figure.tight_layout()
    figure.savefig(str(figures / "nominal_power_current.png"), dpi=160)
    plt.close(figure)


def build_argument_parser() -> argparse.ArgumentParser:
    """Define the small derived-artifact command line; raw evidence is immutable."""

    parser = argparse.ArgumentParser(description="Analyze a completed phase-1 DC delay-chain sweep")
    parser.add_argument("--run-dir", required=True, type=Path, help="completed run_dc_sweep.py output directory")
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Analyze all candidates, publish calibration/figures, and never alter raw decks."""

    args = build_argument_parser().parse_args(argv)
    run_dir = args.run_dir.resolve()
    manifest_path = run_dir / "manifest.json"
    raw_path = run_dir / "raw_sweep_metrics.csv"
    if not manifest_path.is_file() or not raw_path.is_file():
        raise ValueError("run directory lacks manifest.json or raw_sweep_metrics.csv: {}".format(run_dir))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first_violation_v = float(manifest["scan"]["first_violation_voltage_v"])
    raw_rows = read_raw_rows(raw_path)

    all_calibration = []
    summaries = []
    for chain_units in sorted(set(int(row["chain_units"]) for row in raw_rows)):
        chain_rows = [row for row in raw_rows if int(row["chain_units"]) == chain_units]
        calibration, summary = analyze_chain(chain_rows, first_violation_v)
        all_calibration.extend(calibration)
        summaries.append(summary)
    all_calibration.sort(key=lambda row: (row["chain_units"], -row["vdd_v"], row["scenario_kind"]))
    decision = choose_candidate(summaries)
    decision["candidates"] = summaries
    write_calibration_csv(run_dir / "sweep_metrics.csv", all_calibration)
    (run_dir / "selection.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_selection_report(run_dir / "selection_report.md", summaries, decision)
    write_phase_summary(run_dir / "phase1_summary.md", manifest, summaries, decision)
    write_plots(run_dir, all_calibration)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
