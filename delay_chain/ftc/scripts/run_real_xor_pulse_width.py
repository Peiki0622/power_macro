#!/usr/bin/env python3
"""Physically validate the first real XOR output pulse at FTC tap29.

This task-owned runner is deliberately narrower than the historical FTC
characterization command.  It fixes the approved 4-RVT/0-LVT operating point,
keeps the complete 30-cell XOR observation bank, measures only xor_29, and
runs a five-point anchor gate before it can request the 36-point VDD sweep.
It neither changes the sensor topology nor proposes a pulse readout circuit.
"""

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    import matplotlib

    # The runner is intended for batch HSPICE hosts as well as interactive
    # shells, so select a display-independent backend before importing pyplot.
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as error:  # pragma: no cover - exercised only without Matplotlib.
    raise SystemExit("real XOR pulse-width validation requires Matplotlib: {}".format(error))


FTC_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import run_ftc_characterization as characterization  # noqa: E402  # Reuse reviewed HSPICE isolation and parsing.


TAP_INDEX = 29
ANCHOR_VDDS = (1.10, 1.00, 0.90, 0.80, 0.75)
FINE_VDDS = tuple(round(1.10 - 0.01 * index, 2) for index in range(36))
RESULT_FIELDS = (
    "vdd_v",
    "t_rvt29_s",
    "t_lvt29_s",
    "t_xor29_rise_s",
    "t_xor29_fall_s",
    "W_proxy_ps",
    "W_real_ps",
    "start_shift_ps",
    "end_shift_ps",
    "width_error_ps",
    "width_ratio",
    "xor29_peak_v",
    "xor29_peak_ratio",
    "valid",
)


def finite_number(value: Any) -> Optional[float]:
    """Return a finite scalar or ``None`` without converting failed MEAS to zero.

    HSPICE writes a failed .measure as an empty/failed field, which the shared
    parser represents as ``None``.  Preserving that state is essential here:
    a missing XOR crossing is the physical NO-GO condition under study, not a
    numerical value that downstream arithmetic may conceal.
    """

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def format_value(value: Any) -> Any:
    """Render finite floats compactly while leaving failed measurements blank."""

    return "{:.12g}".format(float(value)) if isinstance(value, float) else ("" if value is None else value)


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Write one deterministic task evidence table with the fixed public schema."""

    if not rows:
        raise ValueError("refusing to write an empty real-XOR evidence table: {}".format(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: format_value(row.get(field)) for field in RESULT_FIELDS})


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write compact human-reviewable summary metadata outside ignored runs."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_fixed_experiment(config: Mapping[str, Any], cells: Mapping[str, Any]) -> Dict[str, Any]:
    """Reject a config drift before it can produce incomparable physical evidence.

    These are the already approved conditions from the proxy GO.  The check is
    intentionally a fixed contract, not a new parameter-selection interface:
    allowing an alternate cell, chain length, launch timing, or VDD range here
    would turn this validation into a different experiment.
    """

    point = config.get("selected_operating_point")
    if not isinstance(point, dict):
        raise ValueError("FTC selected operating point is unavailable")
    required_config = (
        ("technology", "SMIC40LL"),
        ("corner", "tt"),
        ("temperature_c", 25.0),
        ("observable_stages", 30),
        ("launch_time_s", 1.0e-9),
        ("tran_max_step_s", 1.0e-12),
        ("minimum_vdd_v", 0.75),
        ("nominal_vdd_v", 1.10),
    )
    for field, expected in required_config:
        actual = config.get(field)
        if isinstance(expected, float):
            if finite_number(actual) != expected:
                raise ValueError("FTC config {} must remain {}".format(field, expected))
        elif actual != expected:
            raise ValueError("FTC config {} must remain {}".format(field, expected))
    if int(point.get("initial_rvt_stages", -1)) != 4 or int(point.get("initial_lvt_stages", -1)) != 0:
        raise ValueError("real XOR pulse-width validation requires the selected 4-RVT/0-LVT point")
    if finite_number(point.get("capture_phase_s")) != 3.0e-10:
        raise ValueError("real XOR pulse-width validation requires the selected 300 ps capture phase")
    if cells.get("delay_rvt", {}).get("cell") != "BUF_X0P7M_A9TR40":
        raise ValueError("real XOR pulse-width validation requires BUF_X0P7M_A9TR40")
    if cells.get("delay_lvt", {}).get("cell") != "BUF_X0P7M_A9TL40":
        raise ValueError("real XOR pulse-width validation requires BUF_X0P7M_A9TL40")
    if cells.get("xor2", {}).get("cell") != "XOR2_X0P5M_A9TR40":
        raise ValueError("real XOR pulse-width validation requires XOR2_X0P5M_A9TR40")
    return point


def row_from_record(vdd_v: float, record: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert one same-run HSPICE record into the requested tap29 evidence row.

    The two input crossings and the real XOR output crossings are all read
    from one deck/MEAS file.  This makes the shift decomposition an observed
    cell effect at a single VDD, rather than a comparison between separately
    simulated runs that might have changed loading or numerical conditions.
    """

    row: Dict[str, Any] = {field: None for field in RESULT_FIELDS}
    row["vdd_v"] = float(vdd_v)
    row["valid"] = 0
    rvt_crossings = record.get("rvt_crossings_s")
    lvt_crossings = record.get("lvt_crossings_s")
    measures = record.get("pulse_width_measurements")
    if not isinstance(rvt_crossings, list) or not isinstance(lvt_crossings, list):
        raise ValueError("shared FTC runner did not return crossing vectors")
    if len(rvt_crossings) != 30 or len(lvt_crossings) != 30:
        raise ValueError("real XOR runner requires all 30 physical tap crossings")
    if not isinstance(measures, list) or len(measures) != 1 or int(measures[0].get("tap_index", -1)) != TAP_INDEX:
        raise ValueError("shared FTC runner did not return the requested tap29 pulse measures")

    row["t_rvt29_s"] = finite_number(rvt_crossings[TAP_INDEX])
    row["t_lvt29_s"] = finite_number(lvt_crossings[TAP_INDEX])
    row["t_xor29_rise_s"] = finite_number(measures[0].get("xor_rise_s"))
    row["t_xor29_fall_s"] = finite_number(measures[0].get("xor_fall_s"))
    row["xor29_peak_v"] = finite_number(measures[0].get("xor_peak_v"))
    if row["xor29_peak_v"] is not None:
        row["xor29_peak_ratio"] = float(row["xor29_peak_v"]) / float(vdd_v)

    required = ("t_rvt29_s", "t_lvt29_s", "t_xor29_rise_s", "t_xor29_fall_s")
    if any(row[field] is None for field in required):
        return row
    lead_input = min(float(row["t_rvt29_s"]), float(row["t_lvt29_s"]))
    lag_input = max(float(row["t_rvt29_s"]), float(row["t_lvt29_s"]))
    real_width_s = float(row["t_xor29_fall_s"]) - float(row["t_xor29_rise_s"])
    proxy_width_s = lag_input - lead_input
    if real_width_s <= 0.0 or proxy_width_s <= 0.0:
        return row

    # Keep the direct physical decomposition in ps.  No curve fitting or
    # proxy calibration is applied: the final equality is merely the measured
    # timing identity W_real = W_proxy + end_shift - start_shift.
    row["W_proxy_ps"] = proxy_width_s * 1.0e12
    row["W_real_ps"] = real_width_s * 1.0e12
    row["start_shift_ps"] = (float(row["t_xor29_rise_s"]) - lead_input) * 1.0e12
    row["end_shift_ps"] = (float(row["t_xor29_fall_s"]) - lag_input) * 1.0e12
    row["width_error_ps"] = float(row["W_real_ps"]) - float(row["W_proxy_ps"])
    row["width_ratio"] = float(row["W_real_ps"]) / float(row["W_proxy_ps"])
    row["valid"] = 1
    return row


def monotonic_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Classify measured real widths in the prescribed descending-VDD order.

    Exact adjacent comparisons deliberately expose a plateau or reverse step.
    The task does not permit smoothing, fitted transfer functions, or an
    arbitrary voltage-resolution tolerance that could hide a physical result.
    """

    widths = [finite_number(row.get("W_real_ps")) for row in rows]
    if len(widths) < 2 or any(width is None for width in widths):
        return {
            "monotonic_class": "not_evaluable",
            "monotonic_violation_count": None,
            "plateau_count": None,
            "step_deltas_ps": [],
        }
    steps = [float(later) - float(earlier) for earlier, later in zip(widths, widths[1:])]
    negative = sum(step < 0.0 for step in steps)
    plateau = sum(step == 0.0 for step in steps)
    if all(step > 0.0 for step in steps):
        label = "strict_increasing"
    elif all(step >= 0.0 for step in steps):
        label = "nondecreasing_with_plateau"
    else:
        label = "nonmonotonic"
    return {
        "monotonic_class": label,
        "monotonic_violation_count": negative,
        "plateau_count": plateau,
        "step_deltas_ps": steps,
    }


def complete_pulse_rows(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Require both crossing validity and a recorded peak above VDD/2.

    The peak check is not a library-independent VIH/VIL rule.  It only
    corroborates the same VDD/2 crossing already used to define pulse width;
    no 0.8/0.9-VDD digital-amplitude gate is introduced.
    """

    return all(
        int(row.get("valid", 0)) == 1
        and (finite_number(row.get("xor29_peak_ratio")) or 0.0) > 0.5
        for row in rows
    )


def anchor_decision(rows: Sequence[Mapping[str, Any]]) -> Tuple[str, List[str], Dict[str, Any]]:
    """Apply the five-point gate without launching a corrective circuit search."""

    monotonic = monotonic_summary(rows)
    if len(rows) != len(ANCHOR_VDDS) or not complete_pulse_rows(rows):
        return "NO-GO", ["At least one anchor lacks a complete VDD/2 real-XOR pulse or peak evidence."], monotonic
    if monotonic["monotonic_class"] == "strict_increasing":
        return "GO", ["All five anchors have complete pulses and strictly increase as VDD decreases."], monotonic
    endpoint_increases = float(rows[-1]["W_real_ps"]) > float(rows[0]["W_real_ps"])
    if endpoint_increases and (
        monotonic["monotonic_class"] == "nondecreasing_with_plateau"
        or int(monotonic["monotonic_violation_count"] or 0) == 1
    ):
        return "CONDITIONAL", ["All five pulses exist and the endpoint trend is positive, but strict anchor monotonicity is not met."], monotonic
    return "NO-GO", ["Anchor real widths do not retain the required rising trend as VDD decreases."], monotonic


def fine_vdds_after_anchor(decision: str) -> Tuple[float, ...]:
    """Return the fine grid only for an explicit anchor GO.

    Keeping this one-line gate as a named helper makes the no-fine-on-failure
    contract directly testable without simulating HSPICE.  It has no retry or
    fallback path: a CONDITIONAL or NO-GO anchor stops this task as planned.
    """

    return FINE_VDDS if decision == "GO" else ()


def fine_decision(rows: Sequence[Mapping[str, Any]]) -> Tuple[str, List[str], Dict[str, Any]]:
    """Classify the 36-point transfer using the agreed conservative exception.

    A plateau, or exactly one reverse 10 mV step with a positive endpoint span,
    is CONDITIONAL for manual review.  Two or more reverse steps are treated
    as strong nonmonotonicity and close this single-tap route without trying a
    new XOR cell, tap, or pulse stretcher.
    """

    monotonic = monotonic_summary(rows)
    if len(rows) != len(FINE_VDDS) or not complete_pulse_rows(rows):
        return "NO-GO", ["One or more fine VDD points lacks a complete VDD/2 real-XOR pulse or peak evidence."], monotonic
    if monotonic["monotonic_class"] == "strict_increasing":
        return "GO", ["All 36 points have complete pulses and strictly increase as VDD decreases."], monotonic
    endpoint_increases = float(rows[-1]["W_real_ps"]) > float(rows[0]["W_real_ps"])
    if endpoint_increases and (
        monotonic["monotonic_class"] == "nondecreasing_with_plateau"
        or int(monotonic["monotonic_violation_count"] or 0) == 1
    ):
        return "CONDITIONAL", ["All pulses exist and the endpoint trend is positive, but a plateau or one local reverse step prevents GO."], monotonic
    return "NO-GO", ["Fine real widths are strongly nonmonotonic or no longer increase across the VDD range."], monotonic


def fine_metrics(rows: Sequence[Mapping[str, Any]], monotonic: Mapping[str, Any]) -> Dict[str, Any]:
    """Calculate only the direct 10 mV and distortion statistics requested."""

    result: Dict[str, Any] = {
        "monotonic_class": monotonic["monotonic_class"],
        "monotonic_violation_count": monotonic["monotonic_violation_count"],
        "plateau_count": monotonic["plateau_count"],
    }
    required_fields = ("W_real_ps", "width_error_ps", "width_ratio")
    if any(any(finite_number(row.get(field)) is None for field in required_fields) for row in rows):
        # A failed output pulse is already a decisive physical result.  Leave
        # derived range/sensitivity statistics unavailable rather than
        # calculating them from a subset that would imply 36-point coverage.
        return {
            **result,
            "real_span_ps": None,
            "min_abs_step_ps": None,
            "median_abs_step_ps": None,
            "max_abs_step_ps": None,
            "min_abs_sensitivity_ps_per_100mV": None,
            "median_abs_sensitivity_ps_per_100mV": None,
            "max_abs_sensitivity_ps_per_100mV": None,
            "min_width_error_ps": None,
            "median_width_error_ps": None,
            "max_width_error_ps": None,
            "min_width_ratio": None,
            "median_width_ratio": None,
            "max_width_ratio": None,
        }
    widths = [float(row["W_real_ps"]) for row in rows]
    steps = [abs(float(step)) for step in monotonic["step_deltas_ps"]]
    sensitivities = [step / 0.01 * 0.1 for step in steps]
    errors = [float(row["width_error_ps"]) for row in rows]
    ratios = [float(row["width_ratio"]) for row in rows]
    return {
        **result,
        "real_span_ps": widths[-1] - widths[0],
        "min_abs_step_ps": min(steps),
        "median_abs_step_ps": statistics.median(steps),
        "max_abs_step_ps": max(steps),
        "min_abs_sensitivity_ps_per_100mV": min(sensitivities),
        "median_abs_sensitivity_ps_per_100mV": statistics.median(sensitivities),
        "max_abs_sensitivity_ps_per_100mV": max(sensitivities),
        "min_width_error_ps": min(errors),
        "median_width_error_ps": statistics.median(errors),
        "max_width_error_ps": max(errors),
        "min_width_ratio": min(ratios),
        "median_width_ratio": statistics.median(ratios),
        "max_width_ratio": max(ratios),
    }


def run_grid(hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any],
             point: Mapping[str, Any], label: str, vdds: Sequence[float]) -> List[Dict[str, Any]]:
    """Run exactly one isolated normal-launch scenario per requested VDD."""

    rows: List[Dict[str, Any]] = []
    for index, voltage in enumerate(vdds):
        record = characterization.run_scenario(
            hspice, run_dir, dict(config), dict(cells), index, label, float(voltage), "xor",
            int(point["initial_rvt_stages"]), int(point["initial_lvt_stages"]), float(point["capture_phase_s"]),
            pulse_width_taps=[TAP_INDEX],
        )
        rows.append(row_from_record(float(voltage), record))
    return rows


def save_figure(figure: Any, path: Path) -> None:
    """Save one deterministic SVG and remove irrelevant trailing whitespace."""

    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, format="svg", bbox_inches="tight", metadata={"Date": None})
    plt.close(figure)
    path.write_text("\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()) + "\n", encoding="utf-8")


def configure_plot_style() -> None:
    """Use the compact established SVG style without adding a plotting framework."""

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.labelsize": 10, "axes.titlesize": 11, "svg.fonttype": "none"})


def plot_fine(rows: Sequence[Mapping[str, Any]], output_dir: Path) -> None:
    """Render the two required figures and no auxiliary diagnostic chart."""

    ordered = sorted(rows, key=lambda row: float(row["vdd_v"]))
    vdds = [float(row["vdd_v"]) for row in ordered]
    # Matplotlib renders a visible gap for a failed measurement.  That is more
    # honest than dropping the failed VDD point or drawing a zero-width pulse.
    def plotted(field: str) -> List[float]:
        values: List[float] = []
        for row in ordered:
            value = finite_number(row.get(field))
            values.append(float(value) if value is not None else math.nan)
        return values

    configure_plot_style()
    figure, axis = plt.subplots(figsize=(7.0, 4.0))
    axis.plot(vdds, plotted("W_proxy_ps"), "-o", markersize=3.0, label="W_proxy (same run)")
    axis.plot(vdds, plotted("W_real_ps"), "-o", markersize=3.0, label="W_real")
    axis.set_xlabel("VDD (V)")
    axis.set_ylabel("Pulse width (ps)")
    axis.set_title("Real XOR pulse width versus proxy at tap29")
    axis.grid(True, linewidth=0.5, alpha=0.35)
    axis.legend(loc="best")
    save_figure(figure, output_dir / "fig1_real_vs_proxy.svg")

    figure, axis = plt.subplots(figsize=(7.0, 4.0))
    axis.plot(vdds, plotted("width_error_ps"), "-o", color="#D55E00", markersize=3.0)
    axis.axhline(0.0, color="#555555", linewidth=0.8)
    axis.set_xlabel("VDD (V)")
    axis.set_ylabel("W_real - W_proxy (ps)")
    axis.set_title("XOR-cell pulse-width distortion at tap29")
    axis.grid(True, linewidth=0.5, alpha=0.35)
    save_figure(figure, output_dir / "fig2_width_error_vs_vdd.svg")


def cell(value: Any, digits: int = 3) -> str:
    """Render a report table value while keeping a failed measurement explicit."""

    number = finite_number(value)
    return "n/a" if number is None else "{:.{}f}".format(number, digits)


def render_report(path: Path, anchor_rows: Sequence[Mapping[str, Any]], anchor_result: Tuple[str, List[str], Mapping[str, Any]],
                  fine_rows: Optional[Sequence[Mapping[str, Any]]] = None,
                  fine_result: Optional[Tuple[str, List[str], Mapping[str, Any]]] = None,
                  metrics: Optional[Mapping[str, Any]] = None) -> None:
    """Write the final bounded research report from generated task artifacts."""

    final_decision = fine_result[0] if fine_result is not None else anchor_result[0]
    final_reasons = fine_result[1] if fine_result is not None else anchor_result[1]
    lines = [
        "# FTC Real XOR Pulse-Width Validation",
        "",
        "## A. Why this experiment",
        "",
        "The prior GO established `|t_RVT - t_LVT|` as a VDD feature, not the high-pulse width at a physical XOR output. This experiment measures that output directly at tap29.",
        "",
        "## B. Exact physical topology",
        "",
        "- SMIC40LL TT / 25 C; RVT `BUF_X0P7M_A9TR40`; LVT `BUF_X0P7M_A9TL40`.",
        "- 4 RVT initial stages, 0 LVT initial stages, 30 observable stages, and the full 30-real-XOR bank.",
        "- XOR cell `XOR2_X0P5M_A9TR40`; measured output `xor_29`; normal isolated rising launch; 1 ps transient maximum step.",
        "",
        "## C. Anchor result",
        "",
        "| VDD (V) | W_proxy (ps) | W_real (ps) | Width error (ps) | Peak/VDD | Valid |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in anchor_rows:
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            cell(row.get("vdd_v"), 2), cell(row.get("W_proxy_ps")), cell(row.get("W_real_ps")),
            cell(row.get("width_error_ps")), cell(row.get("xor29_peak_ratio")), int(row.get("valid", 0)),
        ))
    lines.extend(["", "Anchor decision: **{}**.".format(anchor_result[0])])
    lines.extend("- {}".format(reason) for reason in anchor_result[1])

    if fine_rows is not None and fine_result is not None and metrics is not None:
        lines.extend([
            "",
            "## D. Fine transfer",
            "",
            "![Real versus proxy](../analysis/real_xor_pulse_width/fig1_real_vs_proxy.svg)",
            "",
            "![Width distortion](../analysis/real_xor_pulse_width/fig2_width_error_vs_vdd.svg)",
            "",
            "- Monotonic class: `{}`; plateaus: {}; reverse steps: {}.".format(metrics["monotonic_class"], metrics["plateau_count"], metrics["monotonic_violation_count"]),
        ])
        if finite_number(metrics.get("real_span_ps")) is None:
            lines.append("At least one fine pulse measure is incomplete, so full-range span, step, sensitivity, and distortion statistics are intentionally not calculated from a partial subset.")
        else:
            lines.extend([
                "- Real span: {:.3f} ps; adjacent 10 mV movement min/median/max: {:.3f}/{:.3f}/{:.3f} ps.".format(metrics["real_span_ps"], metrics["min_abs_step_ps"], metrics["median_abs_step_ps"], metrics["max_abs_step_ps"]),
                "- |dW_real/dVDD| min/median/max: {:.3f}/{:.3f}/{:.3f} ps / 100 mV.".format(metrics["min_abs_sensitivity_ps_per_100mV"], metrics["median_abs_sensitivity_ps_per_100mV"], metrics["max_abs_sensitivity_ps_per_100mV"]),
                "- Width error min/median/max: {:.3f}/{:.3f}/{:.3f} ps; width ratio min/median/max: {:.3f}/{:.3f}/{:.3f}.".format(metrics["min_width_error_ps"], metrics["median_width_error_ps"], metrics["max_width_error_ps"], metrics["min_width_ratio"], metrics["median_width_ratio"], metrics["max_width_ratio"]),
            ])
        lines.extend([
            "",
            "## E. Physical interpretation",
            "",
        ])
        if finite_number(metrics.get("real_span_ps")) is None:
            lines.append("An incomplete pulse prevents a full-range interpretation; no alternate tap, XOR drive, or pulse-stretching workaround is considered.")
        else:
            lines.extend([
                "All 36 measured outputs retain complete VDD/2 rise/fall pulses. `W_real` preserves the proxy transfer direction without calibration.",
                "Width error changes from {:.3f} to {:.3f} ps across VDD, so the XOR contribution is VDD-dependent distortion rather than a constant offset; its measured ratio remains within {:.3f}--{:.3f}.".format(metrics["min_width_error_ps"], metrics["max_width_error_ps"], metrics["min_width_ratio"], metrics["max_width_ratio"]),
                "No threshold, TDC, PVT, or glitch architecture is inferred from this physical-transfer result.",
            ])
    else:
        lines.extend([
            "",
            "## D. Fine transfer",
            "",
            "Fine validation was not launched because the anchor gate did not return GO.",
            "",
            "## E. Physical interpretation",
            "",
            "The anchor result is insufficient to claim a full-range real-XOR pulse-width transfer. No alternate tap, XOR drive, or pulse-stretching workaround was tried.",
        ])
    lines.extend(["", "## F. Final decision", "", "**{}**".format(final_decision)])
    lines.extend("- {}".format(reason) for reason in final_reasons)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def anchor_summary(rows: Sequence[Mapping[str, Any]], result: Tuple[str, List[str], Mapping[str, Any]]) -> Dict[str, Any]:
    """Build the committed five-point gate record without inventing fine metrics."""

    decision, reasons, monotonic = result
    return {
        "decision": decision,
        "decision_reason": reasons,
        "monotonic_class": monotonic["monotonic_class"],
        "monotonic_violation_count": monotonic["monotonic_violation_count"],
        "plateau_count": monotonic["plateau_count"],
        "measured_tap": TAP_INDEX,
        "vdd_point_count": len(rows),
        "vdd_v": [float(row["vdd_v"]) for row in rows],
    }


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Expose paths only; physics choices are intentionally not CLI parameters."""

    parser = argparse.ArgumentParser(description="validate real FTC xor_29 pulse width with an anchor gate")
    parser.add_argument("--config", type=Path, default=FTC_ROOT / "ftc_config.json", help="frozen FTC configuration")
    parser.add_argument("--run-dir", type=Path, default=FTC_ROOT / "runs" / "real_xor_pulse_width", help="ignored raw HSPICE run root")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis" / "real_xor_pulse_width", help="committed compact evidence directory")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports" / "FTC_REAL_XOR_PULSE_WIDTH_VALIDATION.md", help="final research report")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run anchors, then run fine evidence only after an explicit physical GO."""

    args = parse_args(argv)
    config = characterization.load_json(args.config.resolve())
    cells = characterization.load_json(FTC_ROOT / "discovery" / "selected_cells.json")
    point = verify_fixed_experiment(config, cells)
    run_dir = args.run_dir.resolve()
    analysis_dir = args.analysis_dir.resolve()
    report_output = args.report_output.resolve()

    hspice = characterization.prepare_output(run_dir, config, cells)
    anchors = run_grid(hspice, run_dir, config, cells, point, "anchor", ANCHOR_VDDS)
    anchor_result = anchor_decision(anchors)
    write_csv(analysis_dir / "anchor.csv", anchors)
    write_json(analysis_dir / "anchor_summary.json", anchor_summary(anchors, anchor_result))
    if anchor_result[0] != "GO":
        render_report(report_output, anchors, anchor_result)
        print("FTC_REAL_XOR_PULSE_WIDTH anchor_decision={}".format(anchor_result[0]))
        return 0

    fine = run_grid(hspice, run_dir, config, cells, point, "fine", fine_vdds_after_anchor(anchor_result[0]))
    fine_result = fine_decision(fine)
    metrics = fine_metrics(fine, fine_result[2])
    write_csv(analysis_dir / "fine.csv", fine)
    summary = anchor_summary(anchors, anchor_result)
    anchor_vdds = summary.pop("vdd_v")
    write_json(analysis_dir / "summary.json", {
        **summary,
        **metrics,
        "anchor_vdd_point_count": len(anchors),
        "anchor_vdd_v": anchor_vdds,
        "vdd_point_count": len(fine),
        "fine_vdd_v": [float(row["vdd_v"]) for row in fine],
        "decision": fine_result[0],
        "decision_reason": fine_result[1],
    })
    plot_fine(fine, analysis_dir)
    render_report(report_output, anchors, anchor_result, fine, fine_result, metrics)
    print("FTC_REAL_XOR_PULSE_WIDTH decision={}".format(fine_result[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
