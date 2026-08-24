#!/usr/bin/env python3
"""Render the final five provenance-backed FTC T0 evidence figures.

The plotter deliberately consumes only compact, corrected T0 CSV/JSON
artifacts.  It never opens an HSPICE run directory, never invokes a simulator,
and never turns a sample-count diagnostic into a physical coverage claim.
Every output is confined to ``analysis/t0_transient_droop/figures`` and its
manifest records the exact compact evidence consumed by that figure.
"""

import csv
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


# Formal plots are generated only in the reviewed DL environment.  Select the
# headless backend before importing pyplot because this container has no GUI;
# it does not change the resulting vector PDF or 600 dpi PNG evidence.
if os.environ.get("CONDA_DEFAULT_ENV") != "DL":
    raise RuntimeError("T0 plotting requires CONDA_DEFAULT_ENV=DL")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
from PIL import Image


FTC_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = FTC_ROOT / "analysis" / "t0_transient_droop"
FIGURES = ANALYSIS / "figures"
MANIFEST_PATH = FIGURES / "figure_manifest.json"

PHASE_COVERAGE_CSV = ANALYSIS / "phase_coverage" / "phase_coverage.csv"
PHASE_COVERAGE_SUMMARY = ANALYSIS / "phase_coverage" / "phase_coverage_summary.json"
BOUNDARY_CSV = ANALYSIS / "amplitude_duration" / "minimum_duration_boundary.csv"
AMPLITUDE_SUMMARY = ANALYSIS / "amplitude_duration" / "summary.json"
CADENCE_CSV = ANALYSIS / "cadence" / "coverage_vs_probe_period.csv"
CADENCE_SUMMARY = ANALYSIS / "cadence" / "cadence_summary.json"
GATE_PATH = ANALYSIS / "reports" / "T0_GATE_STATUS.json"

# These frozen event values are rendered solely as labelled evidence markers
# in Figure T0-1.  The selected phase-coverage row carries any pre-simulation
# translation; adding that one shift preserves the immutable event spacings.
FROZEN_SCLK_RISE_NS = 1.49
FROZEN_Q_SAMPLE_1_NS = 3.79
FROZEN_Q_SAMPLE_2_NS = 3.99
TARGET_LONG_KEY = "t0_5a_0p95_l2_long"

# T0-2 must distinguish all four physical classifications.  Boundary gaps are
# a fifth visual category because the adaptive 25 ps scan did not guarantee
# either adjacent state there; they must not be painted as CLEAN_Q1.
STATE_STYLE = {
    "CLEAN_Q1": {"color": "#2ca25f", "label": "CLEAN_Q1（保证检测）"},
    "STABLE_Q0": {"color": "#bdbdbd", "label": "STABLE_Q0（稳定盲区）"},
    "RECOVERY_EDGE_AMBIGUOUS": {"color": "#fdae6b", "label": "RECOVERY_EDGE_AMBIGUOUS"},
    "OTHER_INVALID_AMBIGUOUS": {"color": "#ef3b2c", "label": "OTHER_INVALID_AMBIGUOUS"},
    "BOUNDARY_UNCERTAINTY": {"color": "#9e9ac8", "label": "25 ps 边界不确定"},
}
MARGIN_COLORS = {"L1": "#1b9e77", "L2": "#377eb8", "L3": "#d95f02"}

_CJK_FONT = "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"
if Path(_CJK_FONT).is_file():
    font_manager.fontManager.addfont(_CJK_FONT)
    matplotlib.rcParams["font.family"] = "Noto Sans CJK JP"
matplotlib.rcParams["axes.unicode_minus"] = False


def sha256_file(path: Path) -> str:
    """Hash one compact input incrementally for reproducible figure provenance."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_rows(path: Path, required: Sequence[str]) -> List[Dict[str, str]]:
    """Read a non-empty rectangular evidence table and reject missing fields."""

    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not set(required).issubset(reader.fieldnames):
            raise ValueError("T0 figure input has missing columns: {}".format(path))
        rows = list(reader)
    if not rows:
        raise ValueError("T0 figure input is empty: {}".format(path))
    return rows


def read_json(path: Path) -> Dict[str, Any]:
    """Read one object-shaped compact contract without accepting stale text."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("T0 figure input is not a JSON object: {}".format(path))
    return value


def finite(row: Mapping[str, Any], key: str) -> float:
    """Return one required finite scalar with an evidence-specific error."""

    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("missing plotted scalar {}".format(key)) from error
    if not math.isfinite(value):
        raise ValueError("non-finite plotted scalar {}".format(key))
    return value


def optional_finite(row: Mapping[str, Any], key: str) -> Optional[float]:
    """Read an optional numeric table cell without converting blank to zero."""

    value = row.get(key)
    if value in (None, ""):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def style_axis(axis: plt.Axes, xlabel: str, ylabel: str) -> None:
    """Apply the shared print-friendly axes treatment to every formal panel."""

    axis.set_xlabel(xlabel)
    axis.set_ylabel(ylabel)
    axis.grid(True, color="0.88", linewidth=0.6, zorder=0)
    axis.tick_params(labelsize=8)


def save_figure(stem: str, figure: plt.Figure, sources: Sequence[Path],
                manifest: List[Dict[str, Any]]) -> None:
    """Write a PDF and 600 dpi PNG, then record deterministic rendering facts.

    PNG dimensions and embedded DPI are checked after writing, rather than
    trusting matplotlib options.  This catches a backend regression before a
    T0-8 Gate can cite an under-resolution image as publication evidence.
    """

    FIGURES.mkdir(parents=True, exist_ok=True)
    pdf_path, png_path = FIGURES / (stem + ".pdf"), FIGURES / (stem + ".png")
    figure.savefig(pdf_path, bbox_inches="tight")
    figure.savefig(png_path, dpi=600, bbox_inches="tight")
    plt.close(figure)
    with Image.open(png_path) as image:
        width, height = image.size
        dpi = image.info.get("dpi", (0.0, 0.0))
    if width < 1200 or height < 800 or min(float(value) for value in dpi) < 590.0:
        raise RuntimeError("T0 figure resolution QA failed: {}".format(stem))
    manifest.append({
        "figure_stem": stem,
        "pdf": str(pdf_path.relative_to(FTC_ROOT)),
        "png": str(png_path.relative_to(FTC_ROOT)),
        "source_sha256": {str(path.relative_to(FTC_ROOT)): sha256_file(path) for path in sources},
        "plot_script_sha256": sha256_file(Path(__file__)),
        "python_executable": sys.executable,
        "matplotlib_version": matplotlib.__version__,
        "conda_env": "DL",
        "png_width_px": width,
        "png_height_px": height,
        "png_dpi": [float(dpi[0]), float(dpi[1])],
    })


def phase_boundary_gaps(summary: Mapping[str, Any]) -> List[Tuple[float, float]]:
    """Return only the retained sampled-state gaps inside a closed T0-5 map.

    The returned spans are visual evidence of uncertainty, not interpolated
    transitions.  Endpoints have zero measure, so a touching state interval
    creates no plotted gap; a 25 ps separation remains visible and cannot be
    confused with a confirmed CLEAN_Q1 region.
    """

    start, end = finite(summary, "characterized_phase_start_ps"), finite(summary, "characterized_phase_end_ps")
    intervals = sorted(summary["intervals"], key=lambda item: finite(item, "phase_start_ps"))
    cursor = start
    gaps: List[Tuple[float, float]] = []
    for interval in intervals:
        interval_start, interval_end = finite(interval, "phase_start_ps"), finite(interval, "phase_end_ps")
        if interval_start > cursor:
            gaps.append((cursor, interval_start))
        cursor = max(cursor, interval_end)
    if cursor < end:
        gaps.append((cursor, end))
    return gaps


def parse_ambiguous_holds(row: Mapping[str, str]) -> List[float]:
    """Decode the compact JSON bracket column while preserving blank controls."""

    text = row.get("ambiguous_hold_ps", "")
    if not text:
        return []
    value = json.loads(text)
    if not isinstance(value, list):
        raise ValueError("ambiguous_hold_ps must be a JSON list")
    return [float(item) for item in value]


def validate_inputs(phase_summary: Mapping[str, Any], amplitude_summary: Mapping[str, Any],
                    cadence_summary: Mapping[str, Any], gate: Mapping[str, Any]) -> None:
    """Reject legacy STOP placeholders before overwriting official figure slots."""

    if phase_summary.get("decision") != "GO" or phase_summary.get("stage") != "T0-5 COMPLETE":
        raise RuntimeError("T0-8 figures require completed T0-5 GO evidence")
    if amplitude_summary.get("decision") != "GO" or gate.get("t0_4_status") != "GO":
        raise RuntimeError("T0-8 figures require corrected T0-4 GO evidence")
    if cadence_summary.get("decision") not in ("GO", "CONDITIONAL_GO"):
        raise RuntimeError("T0-8 figures require completed T0-6 cadence evidence")
    if gate.get("t0_6_status") != cadence_summary.get("decision"):
        raise RuntimeError("T0-8 figures reject a cadence summary inconsistent with the Gate")
    if cadence_summary.get("simulation_accounting", {}).get("hspice_scenarios") != 0:
        raise RuntimeError("T0-8 figures must be based on zero-HSPICE T0-6 evidence")


def plot_t0_1_representative_waveform(phase_rows: Sequence[Mapping[str, str]], manifest: List[Dict[str, Any]]) -> None:
    """Plot one measured clean long-pulse case without inventing analogue Q data.

    The rail trace is the exact finite-slope PWL specified by the retained row.
    XOR and comparator crossings are recorded HSPICE scalars.  Real DFF Q is
    deliberately shown only at its two recorded sample instants, normalized by
    the local rail; a connecting analogue waveform would be fabricated data.
    """

    row = next(
        item for item in phase_rows
        if item["scenario_key"] == TARGET_LONG_KEY and item["t0_5_state"] == "CLEAN_Q1"
        and item["phase_ps"] == "-500.0"
    )
    baseline, vdroop = finite(row, "baseline_vdd_v"), finite(row, "Vdroop_v")
    shift_ns = finite(row, "time_axis_shift_s") * 1e9
    sclk_rise_ns = FROZEN_SCLK_RISE_NS + shift_ns
    start_ns = sclk_rise_ns + finite(row, "phase_ps") / 1000.0
    fall_ns, hold_ns, rise_ns = (finite(row, key) / 1000.0 for key in ("t_fall_ps", "t_hold_ps", "t_rise_ps"))
    recovery_ns = finite(row, "recovery_end_s") * 1e9
    end_ns = max(recovery_ns, start_ns + fall_ns + hold_ns + rise_ns) + 0.25
    q_times = [FROZEN_Q_SAMPLE_1_NS + shift_ns, FROZEN_Q_SAMPLE_2_NS + shift_ns]
    q_ratio = [finite(row, "q_sample_1_ratio"), finite(row, "q_sample_2_ratio")]
    xor_rise, xor_fall, ck_rise = (
        finite(row, "t_xor_rise_s") * 1e9,
        finite(row, "t_xor_fall_s") * 1e9,
        finite(row, "t_ck_rise_s") * 1e9,
    )

    figure, axes = plt.subplots(3, 1, figsize=(9.0, 7.2), sharex=True,
                                gridspec_kw={"height_ratios": [2.2, 1.1, 1.4]})
    rail_time = [0.0, start_ns, start_ns + fall_ns, start_ns + fall_ns + hold_ns,
                 start_ns + fall_ns + hold_ns + rise_ns, end_ns]
    rail_value = [baseline, baseline, vdroop, vdroop, baseline, baseline]
    axes[0].plot(rail_time, rail_value, color="black", linewidth=1.6, label="VDD_MONITORED（记录 PWL）")
    for event, label, color in (
            (start_ns, "droop fall", "#3182bd"),
            (start_ns + fall_ns, "hold", "#6baed6"),
            (start_ns + fall_ns + hold_ns, "recovery", "#de2d26"),
            (sclk_rise_ns, "S_CLK rise", "#756bb1")):
        axes[0].axvline(event, color=color, linewidth=0.9, linestyle="--", label=label)
    axes[0].set_ylim(vdroop - 0.03, baseline + 0.03)
    style_axis(axes[0], "", "VDD (V)")
    axes[0].legend(ncol=2, fontsize=7, loc="best")
    axes[0].set_title("图 T0-1：0.95 V / L2 / 3002 ps 长脉冲的记录事件与真实 Q 采样")

    # Only two XOR edge measurements are retained.  Draw the high window from
    # them and mark CK as a crossing event, rather than constructing an
    # unmeasured full clock waveform with an assumed width or falling edge.
    axes[1].hlines(0.75, xor_rise, xor_fall, color="#31a354", linewidth=5.0, label="记录 XOR 有效窗口")
    axes[1].plot([xor_rise, xor_fall], [0.75, 0.75], "o", color="#31a354", markersize=4)
    axes[1].axvline(ck_rise, color="#756bb1", linewidth=1.2, linestyle="--", label="记录采样 CK crossing")
    axes[1].set_ylim(0.0, 1.1)
    axes[1].set_yticks([])
    style_axis(axes[1], "", "XOR / CK")
    axes[1].legend(fontsize=7, loc="best")

    axes[2].scatter(q_times, q_ratio, color="#e31a1c", zorder=3, label="真实 DFF Q / 当时本地 VDD")
    # The two samples are only 0.20 ns apart.  Offset their labels in opposite
    # directions so the rendered evidence remains readable at publication
    # scale without moving either measured marker on the time axis.
    for time, value, label, offset, alignment in zip(
            q_times, q_ratio, ("Q sample 1", "Q sample 2"),
            ((-6, -18), (4, 7)), ("right", "left")):
        axes[2].annotate(label, (time, value), xytext=offset, textcoords="offset points",
                         fontsize=7, ha=alignment)
    axes[2].set_ylim(-0.05, 1.08)
    style_axis(axes[2], "时间 (ns)", "Q / VDD")
    axes[2].legend(fontsize=7, loc="best")
    axes[2].text(
        0.01, 0.05,
        "恢复沿 ambiguous 仅出现在两个 T0-5B 特殊点；其保留为非保证区域，\n"
        "并非本图 CLEAN_Q1 记录中被平滑掉的第二时钟。",
        transform=axes[2].transAxes, fontsize=7, va="bottom",
    )
    save_figure("fig_t0_1_representative_waveform", figure, [PHASE_COVERAGE_CSV, PHASE_COVERAGE_SUMMARY], manifest)


def plot_t0_2_phase_windows(phase_summary: Mapping[str, Any], manifest: List[Dict[str, Any]]) -> None:
    """Plot all six closed maps so disconnected windows never collapse visually."""

    summaries = sorted(phase_summary["scenarios"], key=lambda item: str(item["scenario_key"]))
    figure, axes = plt.subplots(3, 2, figsize=(10.0, 8.4), sharey=True)
    for axis, summary in zip(axes.flat, summaries):
        start, end = finite(summary, "characterized_phase_start_ps"), finite(summary, "characterized_phase_end_ps")
        for interval in summary["intervals"]:
            state = str(interval["state"])
            left, right = finite(interval, "phase_start_ps"), finite(interval, "phase_end_ps")
            width = right - left
            if width > 0.0:
                axis.axvspan(left, right, color=STATE_STYLE[state]["color"], alpha=0.78, ymin=0.18, ymax=0.82)
                if width >= 100.0:
                    axis.text((left + right) / 2.0, 0.50, "{}\n{}..{} ps".format(
                        state.replace("_", "\n"), int(left), int(right)), ha="center", va="center", fontsize=6)
            else:
                # A sampled ambiguous point has zero measure but must remain
                # visible; draw a full-height marker instead of a false width.
                axis.axvline(left, color=STATE_STYLE[state]["color"], linewidth=2.0)
                axis.text(left, 0.88, state.replace("_", "\n"), ha="center", va="bottom", fontsize=6)
        for left, right in phase_boundary_gaps(summary):
            axis.axvspan(left, right, color=STATE_STYLE["BOUNDARY_UNCERTAINTY"]["color"], alpha=0.35,
                       hatch="///", ymin=0.18, ymax=0.82)
        axis.set_xlim(start - 40.0, end + 40.0)
        axis.set_ylim(0.0, 1.0)
        axis.set_yticks([])
        style_axis(axis, "攻击 phase = droop start − S_CLK rise (ps)", "")
        axis.set_title("{}\n{:.2f} V / {} / {:.0f} ps".format(
            summary["scenario_key"], finite(summary, "baseline_vdd_v"), summary["margin_level"],
            finite(summary, "total_pulse_ps")), fontsize=8)
    handles = [Patch(color=value["color"], label=value["label"]) for value in STATE_STYLE.values()]
    figure.legend(handles=handles, loc="lower center", ncol=3, fontsize=8)
    figure.suptitle("图 T0-2：T0-5 完整单 probe 时间敏感窗口（所有六个闭合场景）", y=0.98)
    figure.tight_layout(rect=(0, 0.08, 1, 0.95))
    save_figure("fig_t0_2_phase_window", figure, [PHASE_COVERAGE_SUMMARY], manifest)


def positive_boundary_rows(rows: Iterable[Mapping[str, str]], baseline: float) -> List[Mapping[str, str]]:
    """Select only resolved clean-Q1 minima; Q0 controls remain a separate class."""

    return [
        row for row in rows
        if math.isclose(finite(row, "baseline_vdd_v"), baseline, rel_tol=0.0, abs_tol=1e-9)
        and optional_finite(row, "minimum_detectable_hold_ps") is not None
    ]


def plot_t0_3_amplitude_duration(boundary_rows: Sequence[Mapping[str, str]], manifest: List[Dict[str, Any]]) -> None:
    """Plot corrected depth-duration observations without promoting controls to minima."""

    figure, axes = plt.subplots(1, 2, figsize=(10.0, 4.4), sharey=True)
    for axis, baseline in zip(axes, (0.95, 1.10)):
        for margin in ("L1", "L2", "L3"):
            selected = [row for row in positive_boundary_rows(boundary_rows, baseline) if row["margin_level"] == margin]
            selected.sort(key=lambda row: finite(row, "DeltaV_mv"))
            if selected:
                axis.plot([finite(row, "DeltaV_mv") for row in selected],
                          [finite(row, "minimum_detectable_hold_ps") for row in selected], "o-",
                          color=MARGIN_COLORS[margin], label="{} clean-Q1 boundary".format(margin), zorder=3)
            controls = [
                row for row in boundary_rows
                if math.isclose(finite(row, "baseline_vdd_v"), baseline, rel_tol=0.0, abs_tol=1e-9)
                and row["margin_level"] == margin and row["point_label"] == "last_q0_control"
            ]
            for control in controls:
                tested = finite(control, "negative_control_max_tested_hold_ps")
                axis.scatter([finite(control, "DeltaV_mv")], [tested], marker="x", s=38,
                             color=MARGIN_COLORS[margin], zorder=4,
                             label="{} Q0 control @ {:.0f} ps（非 minimum）".format(margin, tested))
        style_axis(axis, "跌落深度 ΔV (mV)", "最短 clean-Q1 hold (ps)")
        axis.set_title("{:.2f} V 基准".format(baseline))
        axis.legend(fontsize=6.5, loc="best")
    figure.suptitle("图 T0-3：纠偏后跌落深度—持续时间二维检测边界", y=1.01)
    figure.tight_layout()
    save_figure("fig_t0_3_amplitude_duration_boundary", figure, [BOUNDARY_CSV, AMPLITUDE_SUMMARY], manifest)


def plot_t0_4_margin_comparison(boundary_rows: Sequence[Mapping[str, str]], manifest: List[Dict[str, Any]]) -> None:
    """Compare L1/L2/L3 clean durations and preserve recovery ambiguity brackets."""

    figure, axes = plt.subplots(1, 2, figsize=(10.0, 4.4), sharey=True)
    for axis, baseline in zip(axes, (0.95, 1.10)):
        for margin in ("L1", "L2", "L3"):
            selected = [row for row in positive_boundary_rows(boundary_rows, baseline) if row["margin_level"] == margin]
            selected.sort(key=lambda row: finite(row, "DeltaV_mv"))
            if selected:
                axis.plot([finite(row, "DeltaV_mv") for row in selected],
                          [finite(row, "minimum_detectable_hold_ps") for row in selected], "o-",
                          color=MARGIN_COLORS[margin], label=margin, zorder=3)
            for row in selected:
                clean = finite(row, "minimum_detectable_hold_ps")
                for ambiguous_hold in parse_ambiguous_holds(row):
                    depth = finite(row, "DeltaV_mv")
                    axis.plot([depth, depth], [ambiguous_hold, clean], color=MARGIN_COLORS[margin],
                              linestyle=":", linewidth=1.0, zorder=2)
                    axis.scatter([depth], [ambiguous_hold], marker="s", facecolors="none",
                                 edgecolors=MARGIN_COLORS[margin], s=38, zorder=4)
                    axis.annotate("恢复沿 ambiguous\n非 clean", (depth, ambiguous_hold), xytext=(4, -18),
                                  textcoords="offset points", fontsize=6.5)
        style_axis(axis, "跌落深度 ΔV (mV)", "最短 clean-Q1 hold (ps)")
        axis.set_title("{:.2f} V：margin 比较".format(baseline))
        axis.legend(fontsize=7, loc="best")
    figure.suptitle("图 T0-4：可编程 margin 与恢复沿 ambiguous bracket", y=1.01)
    figure.tight_layout()
    save_figure("fig_t0_4_margin_duration_comparison", figure, [BOUNDARY_CSV, AMPLITUDE_SUMMARY], manifest)


def plot_t0_5_cadence(cadence_rows: Sequence[Mapping[str, str]], cadence_summary: Mapping[str, Any],
                      manifest: List[Dict[str, Any]]) -> None:
    """Plot target clean coverage and blind-window length against probe period."""

    target_keys = tuple(cadence_summary["target_threat"]["scenario_keys"])
    figure, axes = plt.subplots(2, 1, figsize=(8.6, 6.6), sharex=True)
    for key, color, label in (
            (target_keys[0], "#1f78b4", "0.95 V / L2 / 3002 ps"),
            (target_keys[1], "#e31a1c", "1.10 V / L2 / 3002 ps")):
        selected = [row for row in cadence_rows if row["scenario_key"] == key]
        selected.sort(key=lambda row: finite(row, "probe_period_ps"))
        periods_ns = [finite(row, "probe_period_ps") / 1000.0 for row in selected]
        axes[0].plot(periods_ns, [finite(row, "clean_coverage_fraction") * 100.0 for row in selected],
                     color=color, linewidth=1.6, label=label)
        axes[1].plot(periods_ns, [finite(row, "maximum_non_guarantee_window_ps") / 1000.0 for row in selected],
                     color=color, linewidth=1.6, label=label)
    pmax_ns = finite(cadence_summary, "pmax_coverage_ps") / 1000.0
    for axis in axes:
        axis.axvline(pmax_ns, color="black", linewidth=1.2, linestyle="-", label="Pmax = {:.3f} ns".format(pmax_ns))
        axis.axvline(2.5, color="#756bb1", linewidth=1.0, linestyle="--", label="400 MHz 控制时钟 2.5 ns")
        axis.axvline(5.7, color="#636363", linewidth=1.0, linestyle=":", label="当前 one-shot 参考 5.70 ns")
    axes[0].axhline(100.0, color="#238b45", linewidth=0.9, linestyle="--", label="100% CLEAN_Q1 要求")
    axes[0].set_ylim(-2.0, 105.0)
    style_axis(axes[0], "", "保证 clean 覆盖率 (%)")
    style_axis(axes[1], "probe period (ns)", "最大连续非保证窗口 (ns)")
    axes[0].legend(fontsize=7, ncol=2, loc="best")
    axes[1].legend(fontsize=7, ncol=2, loc="best")
    axes[0].set_title("图 T0-5：目标 3002 ps 长脉冲的 probe period—保证检测关系")
    figure.tight_layout()
    save_figure("fig_t0_5_cadence_coverage", figure, [CADENCE_CSV, CADENCE_SUMMARY], manifest)


def main() -> int:
    """Render the final T0-8 figure package from current corrected evidence."""

    phase_rows = read_rows(PHASE_COVERAGE_CSV, ("scenario_key", "t0_5_state", "phase_ps"))
    boundary_rows = read_rows(BOUNDARY_CSV, ("baseline_vdd_v", "margin_level", "DeltaV_mv"))
    cadence_rows = read_rows(CADENCE_CSV, ("scenario_key", "probe_period_ps", "clean_coverage_fraction"))
    phase_summary, amplitude_summary = read_json(PHASE_COVERAGE_SUMMARY), read_json(AMPLITUDE_SUMMARY)
    cadence_summary, gate = read_json(CADENCE_SUMMARY), read_json(GATE_PATH)
    validate_inputs(phase_summary, amplitude_summary, cadence_summary, gate)
    manifest: List[Dict[str, Any]] = []
    plot_t0_1_representative_waveform(phase_rows, manifest)
    plot_t0_2_phase_windows(phase_summary, manifest)
    plot_t0_3_amplitude_duration(boundary_rows, manifest)
    plot_t0_4_margin_comparison(boundary_rows, manifest)
    plot_t0_5_cadence(cadence_rows, cadence_summary, manifest)
    MANIFEST_PATH.write_text(json.dumps({
        "schema_version": 3,
        "study": "ftc_t0_transient_voltage_droop_characterization_v1",
        "stage": "T0-8",
        "decision": cadence_summary["decision"],
        "figures": manifest,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
