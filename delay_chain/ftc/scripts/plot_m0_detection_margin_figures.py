#!/usr/bin/env python3
"""Render the four reproducible publication figures required by FTC M0.

The script consumes only formal M0 CSV/JSON evidence and writes only below
``analysis/m0_detection_margin_characterization/figures`` plus the M0 figure
manifest.  It intentionally contains no HSPICE invocation, no electrical
selection logic, and no manual-image post processing.
"""

import csv
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


# Matplotlib must select its headless backend before pyplot is imported.  The
# HSPICE execution environment has no display server, but figure pixels and
# vector PDFs remain identical to an interactive rendering workflow.
if os.environ.get("CONDA_DEFAULT_ENV") != "DL":
    raise RuntimeError("M0 plotting requires CONDA_DEFAULT_ENV=DL")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize, TwoSlopeNorm
from matplotlib.lines import Line2D
from PIL import Image


FTC_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = FTC_ROOT / "analysis" / "m0_detection_margin_characterization"
FIGURES = ANALYSIS / "figures"
MANIFEST = ANALYSIS / "figure_manifest.json"

ANCHORS = {
    0.80: (7, 6),
    0.95: (4, 6),
    1.10: (2, 9),
}
FIGURE_NAMES = {
    "M0-1": "fig_m0_local_code_surface",
    "M0-2": "fig_m0_voltage_response",
    "M0-3": "fig_m0_residual_trip",
    "M0-4": "fig_m0_trip_depth_summary",
}


def sha256_file(path: Path) -> str:
    """Hash a consumed CSV/script so the manifest proves exact provenance."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_rows(path: Path) -> List[Dict[str, str]]:
    """Read a formal CSV; a header-only terminal NO-GO table is valid evidence."""

    if not path.is_file():
        raise FileNotFoundError("required M0 source CSV is missing: {}".format(path))
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError("M0 source CSV has no header: {}".format(path))
        return list(reader)


def number(row: Mapping[str, Any], key: str) -> float:
    """Read one required finite plotted scalar and expose malformed evidence."""

    value = row.get(key)
    if value in (None, ""):
        raise ValueError("missing plotted scalar {} in scenario {}".format(key, row.get("scenario_id", "<table-row>")))
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite plotted scalar {}".format(key))
    return result


def optional_number(row: Mapping[str, Any], key: str) -> Optional[float]:
    """Return optional map/table scalars without turning NO_IN_RANGE_TRIP into zero."""

    value = row.get(key)
    if value in (None, ""):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def style_axis(axis: plt.Axes, xlabel: str, ylabel: str) -> None:
    """Apply the shared print-friendly scientific style to every panel."""

    axis.set_xlabel(xlabel)
    axis.set_ylabel(ylabel)
    axis.grid(True, color="0.88", linewidth=0.6, zorder=0)
    axis.tick_params(labelsize=8)


def annotate_no_data(axis: plt.Axes, message: str) -> None:
    """Keep a terminal NO-GO plot explicit rather than silently omitting it."""

    axis.text(0.5, 0.5, message, transform=axis.transAxes, ha="center", va="center", fontsize=9)
    axis.set_xticks([])
    axis.set_yticks([])


def candidate_lookup(candidates: Sequence[Mapping[str, str]]) -> Dict[Tuple[float, int, int], Mapping[str, str]]:
    """Index formal candidate rows by their actual electrical M/F setting."""

    return {
        (round(number(row, "baseline_vdd_v"), 2), int(number(row, "M_det")), int(number(row, "F_det"))): row
        for row in candidates
        if row.get("margin_level") != "L0"
    }


def local_surface_normalization(surface: Sequence[Mapping[str, str]]) -> Normalize:
    """Create one physically meaningful R scale shared by all M0-1 panels.

    A per-panel autoscale makes equal colors represent different residuals and
    makes a single shared colorbar scientifically incorrect.  M0 residual R
    has a natural physical boundary at 0 ps, so a shared ``TwoSlopeNorm`` is
    preferred whenever the formal valid surface spans both signs.  The plain
    ``Normalize`` fallback keeps a one-sided terminal NO-GO surface legible
    without inventing an unavailable opposite-sign range.
    """

    residuals = [number(row, "R_ps") for row in surface if int(number(row, "valid")) == 1]
    if not residuals:
        raise ValueError("M0-1 has no valid residual values for normalization")
    lower = min(residuals)
    upper = max(residuals)
    if lower < 0.0 < upper:
        return TwoSlopeNorm(vmin=lower, vcenter=0.0, vmax=upper)
    if lower == upper:
        # Matplotlib requires a non-zero range even for a degenerate terminal
        # evidence table.  This does not alter a normal multi-point M0 plot.
        span = max(abs(lower), 1.0) * 0.01
        return Normalize(vmin=lower - span, vmax=upper + span)
    return Normalize(vmin=lower, vmax=upper)


def save_figure(figure_id: str, figure: plt.Figure, source_files: Sequence[Path], plotted_ids: Set[str]) -> Dict[str, Any]:
    """Write PDF/600-dpi PNG and perform the required machine-checkable QA."""

    FIGURES.mkdir(parents=True, exist_ok=True)
    stem = FIGURE_NAMES[figure_id]
    pdf = FIGURES / (stem + ".pdf")
    png = FIGURES / (stem + ".png")
    figure.savefig(pdf, bbox_inches="tight")
    figure.savefig(png, dpi=600, bbox_inches="tight")
    plt.close(figure)
    if not pdf.is_file() or not png.is_file() or pdf.stat().st_size == 0 or png.stat().st_size == 0:
        raise RuntimeError("M0 figure output is missing or empty: {}".format(stem))
    with Image.open(png) as image:
        width, height = image.size
        dpi = image.info.get("dpi", (0.0, 0.0))
    # PNG writers can round 600 to 599.998; 590 dpi is a strict tolerance for
    # metadata representation, not a lower-quality output allowance.
    if width < 1800 or height < 1200 or min(float(dpi[0]), float(dpi[1])) < 590.0:
        raise RuntimeError("M0 PNG QA failed for {}: pixels={}x{}, dpi={}".format(stem, width, height, dpi))
    return {
        "figure_id": figure_id,
        "pdf_path": str(pdf),
        "png_path": str(png),
        "source_files": [str(path) for path in source_files],
        "source_sha256": {str(path): sha256_file(path) for path in source_files},
        "plot_script_sha256": sha256_file(Path(__file__)),
        "python_executable": sys.executable,
        "matplotlib_version": matplotlib.__version__,
        "conda_env": os.environ["CONDA_DEFAULT_ENV"],
        "png_width_px": width,
        "png_height_px": height,
        "png_dpi": [float(dpi[0]), float(dpi[1])],
        "plotted_scenario_ids": sorted(plotted_ids),
    }


def fig_local_surface(surface: Sequence[Mapping[str, str]], candidates: Sequence[Mapping[str, str]]) -> Tuple[plt.Figure, Set[str]]:
    """Plot Fig. M0-1 as three measured M/F residual maps with explicit marks."""

    figure, axes = plt.subplots(1, 3, figsize=(10.8, 3.25), constrained_layout=True)
    chosen = candidate_lookup(candidates)
    plotted: Set[str] = set()
    # Every panel receives this exact same object, and the colorbar below is
    # constructed from the same object rather than from whichever scatter was
    # rendered last.  Thus a color always represents the same residual R.
    normalization = local_surface_normalization(surface)
    cmap = plt.get_cmap("coolwarm")
    for axis, baseline in zip(axes, (0.80, 0.95, 1.10)):
        rows = [row for row in surface if round(number(row, "baseline_vdd_v"), 2) == baseline]
        valid = [row for row in rows if int(number(row, "valid")) == 1]
        invalid = [row for row in rows if int(number(row, "valid")) != 1]
        if valid:
            axis.scatter([number(row, "fine_code") for row in valid], [number(row, "medium_code") for row in valid], c=[number(row, "R_ps") for row in valid], cmap=cmap, norm=normalization, marker="s", s=120, edgecolors="black", linewidths=0.4, zorder=2)
            plotted.update(row["scenario_id"] for row in valid)
            for row in valid:
                q = int(number(row, "q_final"))
                axis.text(number(row, "fine_code"), number(row, "medium_code"), "Q{}".format(q), ha="center", va="center", fontsize=6, zorder=3)
        if invalid:
            axis.scatter([number(row, "fine_code") for row in invalid], [number(row, "medium_code") for row in invalid], marker="x", c="black", s=38, label="invalid", zorder=4)
            plotted.update(row["scenario_id"] for row in invalid)
        medium, fine = ANCHORS[baseline]
        axis.scatter([fine], [medium], marker="*", s=140, c="black", label="calibration", zorder=5)
        for row in valid:
            chosen_row = chosen.get((baseline, int(number(row, "medium_code")), int(number(row, "fine_code"))))
            if chosen_row is not None:
                axis.scatter([number(row, "fine_code")], [number(row, "medium_code")], facecolors="none", edgecolors="black", marker="o", s=210, linewidths=1.1, zorder=6)
        axis.set_title("{:.2f} V".format(baseline), fontsize=9)
        style_axis(axis, "Fine code F", "Medium code M")
    color_mapper = ScalarMappable(norm=normalization, cmap=cmap)
    color_mapper.set_array([])
    colorbar = figure.colorbar(color_mapper, ax=axes, shrink=0.82, pad=0.02)
    colorbar.set_label("Residual R (ps)", fontsize=8)
    colorbar.ax.tick_params(labelsize=7)
    # A shared legend sits outside the measured grids.  Per-panel legends
    # overlapped the calibration star at the upper-left code, obscuring a
    # required physical marker in the publication evidence.
    figure.legend(handles=[
        Line2D([], [], marker="*", color="black", linestyle="None", markersize=10, label="calibration"),
        Line2D([], [], marker="o", color="black", markerfacecolor="none", linestyle="None", markersize=8, label="selected L1/L2/L3"),
        Line2D([], [], marker="x", color="black", linestyle="None", markersize=7, label="invalid"),
    ], loc="lower center", bbox_to_anchor=(0.5, -0.08), ncol=3, fontsize=7, frameon=False)
    figure.suptitle("M0 local measured M/F code surface", fontsize=10)
    return figure, plotted


def fig_voltage_response(mechanism: Sequence[Mapping[str, str]]) -> Tuple[plt.Figure, Set[str]]:
    """Plot Fig. M0-2 with W_xor and D_ref response for each high-VDD baseline."""

    figure, axes = plt.subplots(1, 2, figsize=(7.1, 3.15), constrained_layout=True)
    plotted: Set[str] = set()
    for axis, baseline in zip(axes, (0.95, 1.10)):
        rows = [row for row in mechanism if round(number(row, "baseline_vdd_v"), 2) == baseline and int(number(row, "mechanism_candidate_pass")) == 1]
        grouped: Dict[str, List[Mapping[str, str]]] = {}
        for row in rows:
            grouped.setdefault(str(row["candidate_id"]), []).append(row)
        if not grouped:
            annotate_no_data(axis, "No mechanism-pass candidate\nM0 stopped before Vtrip")
            axis.set_title("{:.2f} V baseline".format(baseline), fontsize=9)
            continue
        for candidate_id, series in sorted(grouped.items()):
            ordered = sorted(series, key=lambda row: number(row, "physical_vdd_v"))
            volts = [number(row, "physical_vdd_v") for row in ordered]
            level = candidate_id.split("_")[-1]
            # Line style distinguishes the physical quantity; marker shape
            # distinguishes L1/L2/L3.  The curves remain separable when color
            # is unavailable in a grayscale paper printout.
            marker = {"L1": "o", "L2": "s", "L3": "^"}[level]
            axis.plot(volts, [number(row, "W_xor_ps") for row in ordered], marker=marker, linestyle="-", linewidth=1.2, markersize=4, label="{} W".format(level))
            axis.plot(volts, [number(row, "D_ref_ps") for row in ordered], marker=marker, linestyle="--", linewidth=1.2, markersize=4, label="{} D".format(level))
            plotted.update(row["scenario_id"] for row in ordered)
        style_axis(axis, "Static VDD (V)", "Time (ps)")
        axis.set_title("{:.2f} V baseline".format(baseline), fontsize=9)
        axis.legend(fontsize=6, ncol=2, frameon=False)
    figure.suptitle("M0 XOR width and reference-delay voltage response", fontsize=10)
    return figure, plotted


def fig_residual_trip(mechanism: Sequence[Mapping[str, str]], trip_sweep: Sequence[Mapping[str, str]], trip_map: Sequence[Mapping[str, str]]) -> Tuple[plt.Figure, Set[str]]:
    """Plot Fig. M0-3, retaining Q=0/Q=1 as distinct markers on R curves."""

    # Reserve a real bottom margin for the Q-marker key.  With constrained
    # layout alone, the explanatory sentence overlapped the x-axis labels in
    # the raster output even though the data coordinates themselves were valid.
    figure, axes = plt.subplots(1, 2, figsize=(7.1, 3.45))
    figure.subplots_adjust(left=0.08, right=0.985, bottom=0.25, top=0.80, wspace=0.22)
    plotted: Set[str] = set()
    trip_by_candidate = {str(row["candidate_id"]): row for row in trip_map}
    for axis, baseline in zip(axes, (0.95, 1.10)):
        rows = [row for row in trip_sweep if round(number(row, "baseline_vdd_v"), 2) == baseline]
        if not rows:
            rows = [row for row in mechanism if round(number(row, "baseline_vdd_v"), 2) == baseline and int(number(row, "mechanism_candidate_pass")) == 1]
        grouped: Dict[str, List[Mapping[str, str]]] = {}
        for row in rows:
            grouped.setdefault(str(row["candidate_id"]), []).append(row)
        axis.axhline(0.0, color="0.3", linewidth=0.8, linestyle=":", label="R = 0")
        if not grouped:
            annotate_no_data(axis, "No trip data; mechanism gate did not pass")
            axis.set_title("{:.2f} V baseline".format(baseline), fontsize=9)
            continue
        for candidate_id, series in sorted(grouped.items()):
            ordered = sorted(series, key=lambda row: number(row, "physical_vdd_v"))
            volts = [number(row, "physical_vdd_v") for row in ordered]
            residuals = [number(row, "R_ps") for row in ordered]
            level = candidate_id.split("_")[-1]
            # Candidate identity is encoded by line style as well as color;
            # Q state remains separately encoded by the open/filled markers.
            axis.plot(volts, residuals, linewidth=1.1, linestyle={"L1": "-", "L2": "--", "L3": "-."}[level], label=level)
            q0 = [row for row in ordered if int(number(row, "q_final")) == 0]
            q1 = [row for row in ordered if int(number(row, "q_final")) == 1]
            axis.scatter([number(row, "physical_vdd_v") for row in q0], [number(row, "R_ps") for row in q0], marker="o", facecolors="white", edgecolors="black", s=24, zorder=3)
            axis.scatter([number(row, "physical_vdd_v") for row in q1], [number(row, "R_ps") for row in q1], marker="^", c="black", s=27, zorder=3)
            mapped = trip_by_candidate.get(candidate_id)
            if mapped is not None and mapped.get("trip_status") == "IN_RANGE_TRIP":
                trip_voltage = optional_number(mapped, "Vtrip_v")
                if trip_voltage is not None:
                    axis.axvline(trip_voltage, color="0.45", linewidth=0.7, linestyle="--")
            plotted.update(row["scenario_id"] for row in ordered)
        style_axis(axis, "Static VDD (V)", "Residual R (ps)")
        axis.set_title("{:.2f} V baseline".format(baseline), fontsize=9)
        axis.legend(fontsize=6, frameon=False)
    figure.text(0.5, 0.06, "Open circle: stable Q=0; filled triangle: stable Q=1; R=0 is diagnostic only.", ha="center", fontsize=7)
    figure.suptitle("M0 residual and real-DFF static trip relation", fontsize=10, y=0.96)
    return figure, plotted


def fig_trip_depth(trip_map: Sequence[Mapping[str, str]]) -> Tuple[plt.Figure, Set[str]]:
    """Plot Fig. M0-4 without converting NO_IN_RANGE_TRIP into a zero-depth datum."""

    figure, axis = plt.subplots(figsize=(4.1, 3.15), constrained_layout=True)
    plotted: Set[str] = set()
    palette = {0.95: ("black", "o"), 1.10: ("0.35", "s")}
    any_trip = False
    for baseline in (0.95, 1.10):
        rows = [row for row in trip_map if round(number(row, "baseline_vdd_v"), 2) == baseline]
        in_range = [row for row in rows if row.get("trip_status") == "IN_RANGE_TRIP"]
        color, marker = palette[baseline]
        if in_range:
            ordered = sorted(in_range, key=lambda row: number(row, "nominal_D_ref_shift_ps"))
            axis.plot([number(row, "nominal_D_ref_shift_ps") for row in ordered], [number(row, "DeltaV_trip_mv") for row in ordered], color=color, marker=marker, linewidth=1.2, markersize=4, label="{:.2f} V".format(baseline))
            any_trip = True
        no_trip = [row for row in rows if row.get("trip_status") == "NO_IN_RANGE_TRIP"]
        for row in no_trip:
            axis.annotate("NO IN-RANGE TRIP", (number(row, "nominal_D_ref_shift_ps"), 0.0), xytext=(0, 8), textcoords="offset points", rotation=90, ha="center", va="bottom", fontsize=6)
    if not any_trip:
        annotate_no_data(axis, "No in-range static Vtrip\nM0 is NO-GO")
    else:
        style_axis(axis, "Nominal timing shift (ps)", "Static trip depth ΔVtrip (mV)")
        axis.legend(fontsize=7, frameon=False)
    axis.set_title("M0 margin level versus static trip depth", fontsize=9)
    return figure, plotted


def main() -> int:
    """Render all four figures and write a hash-bound manifest after QA."""

    surface_path = ANALYSIS / "local_surface" / "local_code_surface.csv"
    candidate_path = ANALYSIS / "tables" / "table_m0_candidate_summary.csv"
    mechanism_path = ANALYSIS / "mechanism_gate" / "mechanism_gate.csv"
    trip_sweep_path = ANALYSIS / "trip" / "trip_sweep.csv"
    trip_map_path = ANALYSIS / "trip" / "trip_map.csv"
    surface = load_rows(surface_path)
    candidates = load_rows(candidate_path)
    mechanism = load_rows(mechanism_path)
    trip_sweep = load_rows(trip_sweep_path)
    trip_map = load_rows(trip_map_path)
    # Formal scenario provenance is checked after all figure builders return.
    # Surface, mechanism, and trip rows are all authoritative CSVs; candidate
    # and trip-map tables contain derived configurations rather than raw IDs.
    formal_ids = {row["scenario_id"] for row in surface + mechanism + trip_sweep if row.get("scenario_id")}
    figures = [
        ("M0-1", fig_local_surface(surface, candidates), [surface_path, candidate_path]),
        ("M0-2", fig_voltage_response(mechanism), [mechanism_path]),
        ("M0-3", fig_residual_trip(mechanism, trip_sweep, trip_map), [mechanism_path, trip_sweep_path, trip_map_path]),
        ("M0-4", fig_trip_depth(trip_map), [trip_map_path]),
    ]
    manifest_figures = []
    for figure_id, (figure, plotted_ids), sources in figures:
        if not plotted_ids.issubset(formal_ids):
            raise RuntimeError("figure {} references a scenario absent from formal CSV".format(figure_id))
        manifest_figures.append(save_figure(figure_id, figure, sources, plotted_ids))
    # M0's formal voltage scope has a hard 0.80 V floor.  This check covers all
    # raw series potentially shown in a figure; table-only Vtrip values do not
    # introduce an unplotted, unsupported detection point.
    plotted_rows = surface + mechanism + trip_sweep
    if any(number(row, "physical_vdd_v") < 0.80 - 1e-12 for row in plotted_rows):
        raise RuntimeError("M0 figure would claim a below-0.80-V point")
    MANIFEST.write_text(json.dumps({
        "schema_version": 1,
        "study": "ftc_m0_detection_margin_characterization_v1",
        "figures": manifest_figures,
        "qa": {
            "all_target_pdf_png_nonempty": True,
            "png_600_dpi": True,
            "source_hashes_match_current_files": True,
            "plotted_scenarios_in_formal_csv": True,
            "below_0p80_detection_claim": False,
        },
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
