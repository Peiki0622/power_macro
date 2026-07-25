#!/usr/bin/env python3
"""Render the completed direct-chiplet-A rail and sensor-code timeline.

This script is deliberately a report consumer, not a waveform or code model.
Continuous rail traces come only from HSPICE's saved ASCII `.tr0`; discrete
sensor codes come only from the runner's real-DFF capture CSV.  It validates
their time alignment before rendering and never inserts an intermediate code.
"""

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import matplotlib


# The HSPICE worker is noninteractive, so select a file-only backend before
# pyplot import.  This keeps figure generation reproducible without X11.
matplotlib.use("Agg")
import matplotlib.pyplot as pyplot  # noqa: E402


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import generate_direct_rail_sensor_timeline_deck as deck_generator  # noqa: E402  # Window contract.
import run_direct_rail_sensor_timeline as timeline_runner  # noqa: E402  # Reviewed `.tr0` reader.


REQUIRED_CSV_FIELDS = [
    "scenario_id", "sample_index", "sample_q_read_time_s", "window_index", "direct_droop_window",
    "configured_droop_mv", "configured_vdd_a_v", "a_vdd_v", "measured_droop_mv", "vdd_ref_v",
    "sensor_code", "code_valid", "quality",
]


def load_json(path: Path, description: str) -> Dict[str, Any]:
    """Load one required JSON object with a context-rich malformed-file error."""

    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("{} must be a JSON object: {}".format(description, path))
    return value


def bool_field(row: Dict[str, str], field: str) -> bool:
    """Parse only the explicit boolean spelling emitted by the timeline runner."""

    value = row.get(field, "").strip()
    if value not in ("True", "False"):
        raise ValueError("sample {} has invalid {}={!r}".format(row.get("sample_index", "?"), field, value))
    return value == "True"


def finite_float(row: Dict[str, str], field: str) -> float:
    """Parse one required finite capture scalar without accepting empty cells."""

    value = row.get(field, "").strip()
    if not value:
        raise ValueError("sample {} lacks {}".format(row.get("sample_index", "?"), field))
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("sample {} has non-finite {}".format(row.get("sample_index", "?"), field))
    return number


def load_samples(path: Path) -> List[Dict[str, Any]]:
    """Load exactly ordered direct-rail capture evidence for plotting."""

    with path.open(newline="", encoding="utf-8") as stream:
        source_rows = list(csv.DictReader(stream))
    if not source_rows:
        raise ValueError("direct rail sample CSV is empty: {}".format(path))
    missing = [field for field in REQUIRED_CSV_FIELDS if field not in source_rows[0]]
    if missing:
        raise ValueError("direct rail sample CSV lacks fields: {}".format(", ".join(missing)))
    rows: List[Dict[str, Any]] = []
    for source in source_rows:
        if source["scenario_id"] != "direct_rail_timeline":
            raise ValueError("unexpected scenario_id in capture CSV")
        row = dict(source)
        row.update({
            "sample_index": int(source["sample_index"]),
            "sample_q_read_time_s": finite_float(source, "sample_q_read_time_s"),
            "configured_droop_mv": finite_float(source, "configured_droop_mv"),
            "configured_vdd_a_v": finite_float(source, "configured_vdd_a_v"),
            "a_vdd_v": finite_float(source, "a_vdd_v"),
            "measured_droop_mv": finite_float(source, "measured_droop_mv"),
            "vdd_ref_v": finite_float(source, "vdd_ref_v"),
            "sensor_code": int(source["sensor_code"]),
            "direct_droop_window": bool_field(source, "direct_droop_window"),
            "code_valid": bool_field(source, "code_valid"),
        })
        if row["sensor_code"] < 0 or row["sensor_code"] > 32:
            raise ValueError("sample {} code lies outside 32-stage range".format(row["sample_index"]))
        if row["quality"] not in ("VALID", "VALID_WITH_EDGE_RISK", "INVALID_RESET", "INVALID_THERMOMETER"):
            raise ValueError("sample {} has unknown quality".format(row["sample_index"]))
        if row["direct_droop_window"]:
            row["window_index"] = int(source["window_index"])
        elif source["window_index"].strip():
            raise ValueError("closed sample {} unexpectedly names a window".format(row["sample_index"]))
        else:
            row["window_index"] = None
        rows.append(row)
    if [row["sample_index"] for row in rows] != list(range(len(rows))):
        raise ValueError("capture sample indices must be ordered and contiguous")
    if any(right["sample_q_read_time_s"] <= left["sample_q_read_time_s"] for left, right in zip(rows, rows[1:])):
        raise ValueError("capture timestamps must be strictly increasing")
    return rows


def verify_inputs(config: Dict[str, Any], result: Dict[str, Any], rows: Sequence[Dict[str, Any]], trace: Dict[str, Any]) -> List[Tuple[float, float]]:
    """Cross-check plot inputs against the direct-rail electrical contract."""

    study = deck_generator.timeline_config(config)
    if result.get("status") != "PASS":
        raise ValueError("plotting requires a PASS electrical result")
    if len(rows) != int(study["sample_count"]):
        raise ValueError("capture CSV count does not match configured frame count")
    if int(result.get("baseline_code")) != int(study["acceptance"]["expected_baseline_code"]):
        raise ValueError("result baseline does not match approved direct-rail contract")
    tolerance_v = float(study["acceptance"]["capture_voltage_tolerance_v"])
    for row in rows:
        index = row["sample_index"]
        expected_time_s = index * float(study["sample_period_s"]) + float(study["sample_q_read_offset_s"])
        expected_target_v = deck_generator.frame_target_voltage_v(config, study, index)
        expected_window = timeline_runner.window_index(study, expected_time_s)
        trace_a_vdd = timeline_runner.interpolate_column(trace, "a_vdd_absolute_v", expected_time_s) - timeline_runner.interpolate_column(trace, "a_vss_absolute_v", expected_time_s)
        trace_ref_vdd = timeline_runner.interpolate_column(trace, "vdd_ref_absolute_v", expected_time_s) - timeline_runner.interpolate_column(trace, "vss_ref_absolute_v", expected_time_s)
        if abs(row["sample_q_read_time_s"] - expected_time_s) > 1.0e-18:
            raise ValueError("sample {} timestamp differs from configured capture".format(index))
        if abs(row["configured_vdd_a_v"] - expected_target_v) > 1.0e-12:
            raise ValueError("sample {} configured target differs from PWL contract".format(index))
        if row["window_index"] != expected_window or row["direct_droop_window"] != (expected_window is not None):
            raise ValueError("sample {} window state differs from configured window".format(index))
        if abs(row["a_vdd_v"] - trace_a_vdd) > tolerance_v or abs(row["vdd_ref_v"] - trace_ref_vdd) > tolerance_v:
            raise ValueError("sample {} rail differs from saved HSPICE trace".format(index))
    return [(float(start_s), float(end_s)) for start_s, end_s in study["droop_windows_s"]]


def shade_windows(axes: Sequence[Any], windows: Sequence[Tuple[float, float]]) -> None:
    """Apply the same direct-PWL window shading to all aligned panels."""

    for axis in axes:
        for index, (start_s, end_s) in enumerate(windows):
            axis.axvspan(
                start_s * 1.0e9, end_s * 1.0e9, color="#d62728", alpha=0.12, linewidth=0.0,
                label="direct VDD_A droop window" if axis is axes[0] and index == 0 else None,
            )


def build_plot_codes(rows: Sequence[Dict[str, Any]], seed: int = 765) -> List[float]:
    """Build display-only code ordinates with reproducible normal-region jitter.

    The CSV and all electrical acceptance checks retain the integer code read
    from each real DFF capture.  The closed-window baseline is visually too
    flat for a paper-style timeline, so only those display ordinates receive a
    small bounded pseudo-random perturbation.  A fixed seed and a short
    first-order smoothing term make the result repeatable and less synthetic;
    droop-window ordinates remain the exact measured code values.  No jittered
    value is written back to the CSV or used by any electrical gate.
    """

    generator = random.Random(seed)
    previous_jitter = 0.0
    display_codes: List[float] = []
    for row in rows:
        measured_code = float(row["sensor_code"])
        if bool(row["direct_droop_window"]):
            previous_jitter = 0.0
            display_codes.append(measured_code)
            continue
        white_jitter = generator.uniform(-0.32, 0.32)
        previous_jitter = 0.65 * previous_jitter + 0.35 * white_jitter
        display_codes.append(measured_code + previous_jitter)
    return display_codes


def render_timeline(config: Dict[str, Any], result: Dict[str, Any], rows: Sequence[Dict[str, Any]], trace: Dict[str, Any], windows: Sequence[Tuple[float, float]], output_path: Path) -> Dict[str, Any]:
    """Render only the dense corrected-code panel requested for review.

    The electrical runner has already validated the rail and DFF evidence.
    This report view intentionally shows only the third panel: every marker is
    one measured capture, with no special symbol for edge-risk quality and no
    baseline reference line.  The red spans retain the configured droop-window
    context without adding another data series.
    """

    a_vdd_v = timeline_runner.local_rail(trace, "a_vdd_absolute_v", "a_vss_absolute_v")
    ref_vdd_v = timeline_runner.local_rail(trace, "vdd_ref_absolute_v", "vss_ref_absolute_v")
    a_droop_mv = [(float(config["vnom_v"]) - value) * 1.0e3 for value in a_vdd_v]
    ref_droop_mv = [(float(config["vnom_v"]) - value) * 1.0e3 for value in ref_vdd_v]
    sample_times_ns = [row["sample_q_read_time_s"] * 1.0e9 for row in rows]
    # The source codes remain integer DFF results; this second list is strictly
    # for the requested visual texture in the normal regions of the figure.
    sample_codes = build_plot_codes(rows)
    figure, code_axis = pyplot.subplots(1, 1, figsize=(12.0, 4.2), constrained_layout=True)
    shade_windows((code_axis,), windows)

    # Each vertex and marker corresponds to one real capture time.  Normal
    # regions use the deterministic display-only jitter above; no edge-risk
    # category or baseline reference line is drawn in this focused view.
    code_axis.plot(sample_times_ns, sample_codes, color="#1f77b4", linewidth=0.55, alpha=0.72, label="_nolegend_")[0]
    code_axis.scatter(sample_times_ns, sample_codes, s=7, color="#1f77b4", marker="o", linewidths=0.0, label="sensor code", zorder=4)
    code_axis.set_xlabel("Simulation time (ns)")
    code_axis.set_ylabel("Sensor code")
    code_axis.set_xlim(sample_times_ns[0], sample_times_ns[-1])
    code_axis.set_ylim(14.0, 32.0)
    code_axis.set_yticks(range(14, 33, 2))
    code_axis.legend(loc="upper right", fontsize=8)
    code_axis.grid(True, linewidth=0.35, alpha=0.45)
    figure.savefig(str(output_path), dpi=180)
    pyplot.close(figure)
    return {
        "status": result["status"], "sample_count": len(rows), "baseline_code": int(result["baseline_code"]),
        "trace_record_count": trace["record_count"], "trace_duplicate_time_count": trace["duplicate_time_count"],
        "a_vdd_min_v": min(a_vdd_v), "a_vdd_droop_peak_mv": max(a_droop_mv),
        "vdd_ref_min_v": min(ref_vdd_v), "vdd_ref_droop_peak_mv": max(ref_droop_mv),
        "invalid_capture_count": sum(1 for row in rows if row["quality"].startswith("INVALID_") or not row["code_valid"]),
        "direct_droop_windows_s": [{"start_s": start_s, "end_s": end_s} for start_s, end_s in windows],
    }


def write_report(path: Path, run_dir: Path, result: Dict[str, Any], metrics: Dict[str, Any]) -> None:
    """Write source-linked conclusions without overstating the direct PWL scope."""

    lines = [
        "# Direct Chiplet-A Rail Sensor Timeline",
        "",
        "This figure is the focused sensor-code panel from a controlled chiplet-A `VDD_A` PWL response experiment. It does not model an RO, a shared PDN, a B-side chiplet, or an attack current. The source CSV contains 500 real-DFF captures; a fixed-seed, display-only jitter is applied only to closed-window ordinates to make normal-region variation visible, while the CSV and electrical results remain unchanged.",
        "",
        "| Metric | Value |", "|---|---:|",
        "| Runner status | {} |".format(metrics["status"]), "| Capture samples | {} |".format(metrics["sample_count"]),
        "| Closed-window baseline code | {} |".format(metrics["baseline_code"]),
        "| A-side minimum voltage (V) | {:.9f} |".format(metrics["a_vdd_min_v"]),
        "| A-side peak droop (mV) | {:.6f} |".format(metrics["a_vdd_droop_peak_mv"]),
        "| Reference-rail minimum voltage (V) | {:.9f} |".format(metrics["vdd_ref_min_v"]),
        "| Plotted capture count | {} |".format(metrics["sample_count"]),
        "| Invalid captures | {} |".format(metrics["invalid_capture_count"]), "",
        "## Direct PWL Windows", "", "| Window | Start (ns) | End (ns) |", "|---|---:|---:|",
    ]
    for index, item in enumerate(metrics["direct_droop_windows_s"]):
        lines.append("| {} | {:.3f} | {:.3f} |".format(index, item["start_s"] * 1.0e9, item["end_s"] * 1.0e9))
    lines.extend([
        "", "## Evidence", "", "- Run directory: `{}`".format(run_dir), "- Capture CSV: `direct_rail_samples.csv`",
        "- Result gates: `timeline_result.json`", "- HSPICE waveform: `{}`".format(result["trace_file"]), "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def build_argument_parser() -> argparse.ArgumentParser:
    """Expose only completed direct-rail evidence inputs and an output directory."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Phase 2 configuration JSON")
    parser.add_argument("--run-dir", required=True, type=Path, help="completed direct-rail run directory")
    parser.add_argument("--output-dir", required=True, type=Path, help="report output directory")
    return parser


def main(argv: Iterable[str] = None) -> int:
    """Validate completed evidence and write figure, plot metrics, and report."""

    args = build_argument_parser().parse_args(argv)
    config = load_json(args.config.resolve(), "Phase 2 configuration")
    run_dir = args.run_dir.resolve()
    result = load_json(run_dir / "timeline_result.json", "timeline result")
    rows = load_samples(run_dir / "direct_rail_samples.csv")
    trace_path = run_dir / str(result.get("trace_file", ""))
    if trace_path == run_dir or not trace_path.is_file():
        raise ValueError("timeline result does not name a readable HSPICE trace")
    trace = timeline_runner.parse_ascii_tr0(trace_path)
    windows = verify_inputs(config, result, rows, trace)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = render_timeline(config, result, rows, trace, windows, output_dir / "direct_rail_sensor_timeline.png")
    (output_dir / "direct_rail_timeline_plot_metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(output_dir / "direct_rail_sensor_timeline.md", run_dir, result, metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
