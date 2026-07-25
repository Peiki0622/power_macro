#!/usr/bin/env python3
"""Render direct HSPICE voltage-droop-to-code evidence without interpolation.

The static CSV is the authority for the transfer curve.  This script only
sorts measured rows by droop, computes presentation metrics from those rows,
and renders raw/corrected observations.  It deliberately does not fit a
continuous model, repair an invalid code, or infer an omitted voltage point.
"""

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import matplotlib


# A noninteractive backend makes report generation deterministic on the EDA
# worker and avoids relying on an X server.  The import order is intentional:
# pyplot must be imported only after the backend is selected.
matplotlib.use("Agg")
import matplotlib.pyplot as pyplot  # noqa: E402


REQUIRED_STATIC_FIELDS = [
    "scenario_id",
    "vdd_a_v",
    "droop_mv",
    "raw_code",
    "raw_sensor_code",
    "corrected_code",
    "sensor_code",
    "bubble_count",
    "raw_bubble_count",
    "code_valid",
    "reset_failure_count",
    "metastability_risk_count",
]


def finite_float(row: Dict[str, str], field: str) -> float:
    """Parse one required finite CSV scalar with scenario context in errors."""

    text = row.get(field, "").strip()
    if not text:
        raise ValueError("{} lacks {}".format(row.get("scenario_id", "<unknown>"), field))
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("{} has non-finite {}".format(row.get("scenario_id", "<unknown>"), field))
    return value


def bool_field(row: Dict[str, str], field: str) -> bool:
    """Parse the explicit Python CSV boolean spelling emitted by the runner."""

    value = row.get(field, "").strip()
    if value not in ("True", "False"):
        raise ValueError("{} has invalid {}={!r}".format(row.get("scenario_id", "<unknown>"), field, value))
    return value == "True"


def load_static_rows(path: Path) -> List[Dict[str, Any]]:
    """Load every static result and retain invalid rows for visible diagnostics."""

    with path.open(newline="", encoding="utf-8") as stream:
        source_rows = list(csv.DictReader(stream))
    if not source_rows:
        raise ValueError("static voltage-code CSV is empty: {}".format(path))
    missing = [field for field in REQUIRED_STATIC_FIELDS if field not in source_rows[0]]
    if missing:
        raise ValueError("static voltage-code CSV lacks fields: {}".format(", ".join(missing)))
    rows = []
    for source in source_rows:
        raw_code = source["raw_code"].strip()
        corrected_code = source["corrected_code"].strip()
        if not raw_code or len(raw_code) != len(corrected_code) or any(bit not in "01" for bit in raw_code + corrected_code):
            raise ValueError("{} has malformed thermometer code".format(source["scenario_id"]))
        row = dict(source)
        row.update(
            {
                "vdd_a_v": finite_float(source, "vdd_a_v"),
                "droop_mv": finite_float(source, "droop_mv"),
                "raw_sensor_code": int(source["raw_sensor_code"]),
                "sensor_code": int(source["sensor_code"]),
                "raw_bubble_count": int(source["raw_bubble_count"]),
                "bubble_count": int(source["bubble_count"]),
                "reset_failure_count": int(source["reset_failure_count"]),
                "metastability_risk_count": int(source["metastability_risk_count"]),
                "code_valid": bool_field(source, "code_valid"),
            }
        )
        rows.append(row)
    if len({row["scenario_id"] for row in rows}) != len(rows):
        raise ValueError("static voltage-code CSV has duplicate scenario IDs")
    return sorted(rows, key=lambda row: row["droop_mv"])


def load_pwl_rows(path: Optional[Path]) -> List[Dict[str, Any]]:
    """Load optional PWL comparison points without making them part of the curve."""

    if path is None:
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        source_rows = list(csv.DictReader(stream))
    rows = []
    for source in source_rows:
        required = ["case_id", "droop_at_capture_mv", "sensor_code", "static_reference_code", "dynamic_static_code_delta"]
        missing = [field for field in required if not source.get(field, "").strip()]
        if missing:
            raise ValueError("PWL row lacks fields: {}".format(", ".join(missing)))
        rows.append(
            {
                "case_id": source["case_id"],
                "droop_at_capture_mv": finite_float(source, "droop_at_capture_mv"),
                "sensor_code": int(source["sensor_code"]),
                "static_reference_code": int(source["static_reference_code"]),
                "dynamic_static_code_delta": int(source["dynamic_static_code_delta"]),
            }
        )
    return rows


def exact_row(rows: Sequence[Dict[str, Any]], vdd_a_v: float, description: str) -> Dict[str, Any]:
    """Find one exact timing-anchor row; do not round to its neighboring grid bin."""

    matches = [row for row in rows if abs(row["vdd_a_v"] - vdd_a_v) <= 1.0e-12]
    if len(matches) != 1:
        raise ValueError("{} needs exactly one row at {} V".format(description, vdd_a_v))
    return matches[0]


def analyze_static_rows(config: Dict[str, Any], rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute only direct code-curve metrics used by the Markdown report."""

    baseline = exact_row(rows, float(config["vnom_v"]), "baseline")
    last_passing = exact_row(rows, float(config["timing_anchor"]["last_passing_voltage_v"]), "last-passing anchor")
    first_violation = exact_row(rows, float(config["timing_anchor"]["first_violation_voltage_v"]), "first-violation anchor")
    violations = []
    for previous, current in zip(rows, rows[1:]):
        if current["sensor_code"] < previous["sensor_code"]:
            violations.append(
                {
                    "lower_droop_mv": previous["droop_mv"],
                    "lower_droop_code": previous["sensor_code"],
                    "higher_droop_mv": current["droop_mv"],
                    "higher_droop_code": current["sensor_code"],
                }
            )
    invalid = [row["scenario_id"] for row in rows if not row["code_valid"]]
    return {
        "scenario_count": len(rows),
        "baseline_code": baseline["sensor_code"],
        "last_passing_code": last_passing["sensor_code"],
        "first_violation_code": first_violation["sensor_code"],
        "first_violation_code_delta": first_violation["sensor_code"] - baseline["sensor_code"],
        "last_to_first_violation_code_delta": first_violation["sensor_code"] - last_passing["sensor_code"],
        "bubble_scenario_count": sum(1 for row in rows if row["raw_bubble_count"] or row["bubble_count"]),
        "invalid_scenarios": invalid,
        "reset_failure_count": sum(row["reset_failure_count"] for row in rows),
        "metastability_risk_count": sum(row["metastability_risk_count"] for row in rows),
        "monotonicity_violations": violations,
        "last_passing_droop_mv": last_passing["droop_mv"],
        "first_violation_droop_mv": first_violation["droop_mv"],
    }


def plot_code_curve(config: Dict[str, Any], rows: Sequence[Dict[str, Any]], pwl_rows: Sequence[Dict[str, Any]], output_path: Path) -> None:
    """Draw the primary direct droop-to-code graph with all quality evidence visible."""

    droop = [row["droop_mv"] for row in rows]
    raw_code = [row["raw_sensor_code"] for row in rows]
    corrected_code = [row["sensor_code"] for row in rows]
    figure, axis = pyplot.subplots(figsize=(10.0, 5.5), constrained_layout=True)
    axis.step(droop, corrected_code, where="mid", color="#1f77b4", linewidth=1.4, label="corrected sensor_code")
    axis.scatter(droop, raw_code, s=10, color="#555555", alpha=0.7, label="raw leading-zero code", zorder=3)
    invalid = [row for row in rows if not row["code_valid"]]
    if invalid:
        axis.scatter(
            [row["droop_mv"] for row in invalid],
            [row["sensor_code"] for row in invalid],
            marker="x",
            s=50,
            linewidths=1.5,
            color="#d62728",
            label="invalid code",
            zorder=5,
        )
    last_drop = (float(config["vnom_v"]) - float(config["timing_anchor"]["last_passing_voltage_v"])) * 1000.0
    fail_drop = (float(config["vnom_v"]) - float(config["timing_anchor"]["first_violation_voltage_v"])) * 1000.0
    axis.axvline(last_drop, color="#2ca02c", linestyle="--", linewidth=1.0, label="35-bank last pass")
    axis.axvline(fail_drop, color="#d62728", linestyle="--", linewidth=1.0, label="40-bank first violation")
    for row in pwl_rows:
        axis.scatter(
            [row["droop_at_capture_mv"]],
            [row["sensor_code"]],
            marker="*",
            s=120,
            label="PWL {}".format(row["case_id"]),
            zorder=6,
        )
    axis.set_xlabel("Direct VDD_A droop from 1.100 V (mV)")
    axis.set_ylabel("Leading-zero sensor_code")
    axis.set_xlim(min(droop), max(droop))
    axis.set_ylim(-0.5, 32.5)
    axis.set_yticks(range(0, 33, 4))
    axis.grid(True, linewidth=0.4, alpha=0.5)
    axis.legend(loc="best", fontsize=8)
    figure.savefig(str(output_path), dpi=180)
    pyplot.close(figure)


def plot_raw_word_map(rows: Sequence[Dict[str, Any]], output_path: Path) -> None:
    """Draw raw thermometer bits by stage so bubble evidence is inspectable visually."""

    bit_count = len(rows[0]["raw_code"])
    if any(len(row["raw_code"]) != bit_count for row in rows):
        raise ValueError("raw-code widths differ across static rows")
    bitmap = [[int(bit) for bit in row["raw_code"]] for row in rows]
    droop = [row["droop_mv"] for row in rows]
    figure, axis = pyplot.subplots(figsize=(10.0, 5.5), constrained_layout=True)
    image = axis.imshow(
        list(zip(*bitmap)),
        aspect="auto",
        interpolation="nearest",
        origin="lower",
        cmap="viridis",
        vmin=0,
        vmax=1,
        extent=(min(droop), max(droop), -0.5, bit_count - 0.5),
    )
    axis.set_xlabel("Direct VDD_A droop from 1.100 V (mV)")
    axis.set_ylabel("Raw DFF stage index")
    colorbar = figure.colorbar(image, ax=axis, ticks=[0, 1])
    colorbar.set_label("raw_code bit")
    figure.savefig(str(output_path), dpi=180)
    pyplot.close(figure)


def write_report(path: Path, config: Dict[str, Any], metrics: Dict[str, Any], pwl_rows: Sequence[Dict[str, Any]]) -> None:
    """Write a compact, source-derived report without manually entered measurements."""

    lines = [
        "# Direct VDD_A Droop To Code Characterization",
        "",
        "The static curve uses the calibrated real-DFF topology: M=32, one reference dummy load, CAL_SEL=2, and a 20 ps sense launch offset.  VDD_REF remains 1.100 V while only VDD_A is stepped.",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Static scenarios | {} |".format(metrics["scenario_count"]),
        "| Baseline code at 1.100 V | {} |".format(metrics["baseline_code"]),
        "| 35-bank last-pass droop (mV) | {:.9f} |".format(metrics["last_passing_droop_mv"]),
        "| 35-bank last-pass code | {} |".format(metrics["last_passing_code"]),
        "| 40-bank first-violation droop (mV) | {:.9f} |".format(metrics["first_violation_droop_mv"]),
        "| 40-bank first-violation code | {} |".format(metrics["first_violation_code"]),
        "| First-violation minus baseline code | {} |".format(metrics["first_violation_code_delta"]),
        "| First-violation minus last-pass code | {} |".format(metrics["last_to_first_violation_code_delta"]),
        "| Raw/corrected bubble scenarios | {} |".format(metrics["bubble_scenario_count"]),
        "| Invalid code scenarios | {} |".format(len(metrics["invalid_scenarios"])),
        "| Reset failures | {} |".format(metrics["reset_failure_count"]),
        "| Metastability-risk bits | {} |".format(metrics["metastability_risk_count"]),
        "| Monotonicity violations | {} |".format(len(metrics["monotonicity_violations"])),
        "",
    ]
    if pwl_rows:
        lines.extend(
            [
                "## PWL Dynamic Comparison",
                "",
                "| Case | Capture droop (mV) | Dynamic code | Nearest static code | Dynamic-static delta |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for row in pwl_rows:
            lines.append(
                "| {case_id} | {droop_at_capture_mv:.9f} | {sensor_code} | {static_reference_code} | {dynamic_static_code_delta} |".format(
                    **row
                )
            )
        lines.append("")
    if metrics["invalid_scenarios"] or metrics["monotonicity_violations"]:
        lines.extend(
            [
                "## Diagnostic Failures",
                "",
                "Invalid-code scenarios: `{}`".format(", ".join(metrics["invalid_scenarios"]) or "none"),
                "",
                "Monotonicity evidence: `{}`".format(json.dumps(metrics["monotonicity_violations"], sort_keys=True)),
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_argument_parser() -> argparse.ArgumentParser:
    """Expose explicit evidence paths and a report-only output directory."""

    parser = argparse.ArgumentParser(description="plot measured Phase-2 voltage-droop-to-code evidence")
    parser.add_argument("--config", required=True, type=Path, help="Phase 2 configuration JSON")
    parser.add_argument("--static-csv", required=True, type=Path, help="static voltage-code metrics CSV")
    parser.add_argument("--pwl-csv", type=Path, help="optional PWL code metrics CSV")
    parser.add_argument("--output-dir", required=True, type=Path, help="report/figure output directory")
    return parser


def main(argv: Iterable[str] = None) -> int:
    """Render all voltage-code report artifacts from completed simulation CSVs."""

    args = build_argument_parser().parse_args(argv)
    with args.config.open(encoding="utf-8") as stream:
        config = json.load(stream)
    if not isinstance(config, dict):
        raise ValueError("Phase 2 configuration must be a JSON object")
    rows = load_static_rows(args.static_csv)
    pwl_rows = load_pwl_rows(args.pwl_csv)
    metrics = analyze_static_rows(config, rows)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_code_curve(config, rows, pwl_rows, output_dir / "voltage_code_vs_droop.png")
    plot_raw_word_map(rows, output_dir / "raw_code_vs_droop.png")
    write_report(output_dir / "voltage_code_curve.md", config, metrics, pwl_rows)
    (output_dir / "voltage_code_plot_metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
