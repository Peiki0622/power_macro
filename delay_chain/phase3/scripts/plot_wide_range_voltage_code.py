#!/usr/bin/env python3
"""Render the reviewed Phase-3 wide-range voltage-to-code figure.

The input is the compact CSV emitted by ``run_voltage_sweep.py`` after the
complete real-DFF HSPICE characterization.  The script intentionally derives
every plotted code, anchor, and first-positive-residual annotation from that
CSV rather than using a hand-entered transfer curve.  It writes only the two
publication-ready figure formats requested by the caller; no simulator deck,
listing, or temporary plot artifact is created outside the selected directory.
"""

import argparse
import csv
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator


def read_rows(path: Path) -> List[Dict[str, str]]:
    """Load and validate the complete physical CSV before drawing anything.

    Exactly one row at each requested voltage is required because a duplicated
    or partially written HSPICE result could otherwise make a step plot appear
    smoother than the hardware data.  Numeric fields remain strings in the
    returned dictionaries so annotations can retain the original point label.
    """

    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("voltage-code CSV has no data rows: {}".format(path))
    required = {"vdd_v", "sensor_code", "residual_code", "point_kind", "code_valid"}
    missing = required.difference(rows[0])
    if missing:
        raise ValueError("voltage-code CSV misses fields: {}".format(", ".join(sorted(missing))))
    voltages = [float(row["vdd_v"]) for row in rows]
    if len(set(voltages)) != len(voltages):
        raise ValueError("voltage-code CSV repeats a VDD point")
    if any(int(row["code_valid"]) != 1 for row in rows):
        raise ValueError("refusing to plot an invalid physical code row")
    return sorted(rows, key=lambda row: float(row["vdd_v"]))


def exact_row(rows: Iterable[Dict[str, str]], voltage: float) -> Dict[str, str]:
    """Return the one retained row at an exact reported voltage.

    The 1e-12 V tolerance is much smaller than the 5 mV final grid and only
    accommodates the decimal-to-binary representation used by CSV parsing.
    """

    matches = [row for row in rows if abs(float(row["vdd_v"]) - voltage) <= 1.0e-12]
    if len(matches) != 1:
        raise ValueError("expected exactly one {} V row".format(voltage))
    return matches[0]


def first_positive_row(rows: Iterable[Dict[str, str]]) -> Dict[str, str]:
    """Find the highest-VDD positive residual, i.e. the first droop response."""

    candidates = [row for row in rows if int(row["residual_code"]) > 0]
    if not candidates:
        raise ValueError("physical curve has no positive residual to annotate")
    return max(candidates, key=lambda row: float(row["vdd_v"]))


def render_figure(rows: List[Dict[str, str]], png_path: Path, pdf_path: Path) -> None:
    """Draw the final 83-point curve in a compact SCI-paper plotting style.

    VDD increases left-to-right, so the measured code naturally decreases
    toward its nominal value.  The step primitive preserves each physical
    code transition instead of visually implying an analog interpolation.
    """

    nominal = exact_row(rows, 1.100)
    point_25mv = exact_row(rows, 1.075)
    point_50mv = exact_row(rows, 1.050)
    first_positive = first_positive_row(rows)
    anchors = [row for row in rows if row["point_kind"] != "grid"]
    vdds = [float(row["vdd_v"]) for row in rows]
    codes = [int(row["sensor_code"]) for row in rows]
    nominal_code = int(nominal["sensor_code"])

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.labelsize": 11,
            "axes.titlesize": 11,
            "legend.fontsize": 9,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    figure, axis = plt.subplots(figsize=(7.2, 4.5), constrained_layout=True)
    axis.set_facecolor("#fbfbfb")
    axis.step(
        vdds,
        codes,
        where="mid",
        color="#0072B2",
        linewidth=1.8,
        label="83-point real-DFF characterization",
        zorder=2,
    )
    axis.plot(vdds, codes, "o", color="#0072B2", markersize=2.6, zorder=3)
    axis.axhline(
        nominal_code,
        color="#6b6b6b",
        linewidth=1.1,
        linestyle="--",
        label="Nominal baseline (code {})".format(nominal_code),
        zorder=1,
    )
    axis.scatter(
        [float(nominal["vdd_v"])],
        [nominal_code],
        marker="o",
        s=54,
        facecolors="white",
        edgecolors="black",
        linewidths=1.2,
        label="Nominal, 1.10 V",
        zorder=5,
    )
    axis.scatter(
        [float(first_positive["vdd_v"])],
        [int(first_positive["sensor_code"])],
        marker="D",
        s=38,
        color="#D55E00",
        label="First +1 residual, {:.3f} V".format(float(first_positive["vdd_v"])),
        zorder=6,
    )
    axis.scatter(
        [float(point_25mv["vdd_v"]), float(point_50mv["vdd_v"])],
        [int(point_25mv["sensor_code"]), int(point_50mv["sensor_code"])],
        marker="s",
        s=30,
        color="#009E73",
        label="25/50 mV +1 verification",
        zorder=6,
    )
    if anchors:
        axis.scatter(
            [float(row["vdd_v"]) for row in anchors],
            [int(row["sensor_code"]) for row in anchors],
            marker="s",
            s=24,
            color="#6A3D9A",
            label="Retained timing anchors",
            zorder=6,
        )

    low_vdd_row = exact_row(rows, 0.700)
    axis.annotate(
        "0.70 V: code {}\n(no saturation)".format(low_vdd_row["sensor_code"]),
        xy=(float(low_vdd_row["vdd_v"]), int(low_vdd_row["sensor_code"])),
        xytext=(0.735, max(codes) - 0.15),
        arrowprops={"arrowstyle": "->", "lw": 0.9, "color": "#333333"},
        ha="left",
        va="top",
        color="#333333",
    )
    axis.annotate(
        "+1 at 20 mV droop",
        xy=(float(first_positive["vdd_v"]), int(first_positive["sensor_code"])),
        xytext=(0.985, nominal_code + 2.55),
        arrowprops={"arrowstyle": "->", "lw": 0.9, "color": "#D55E00"},
        ha="left",
        va="center",
        color="#A64700",
    )

    axis.set_xlabel(r"Supply voltage, $V_{DD}$ (V)")
    axis.set_ylabel("Decoded sensor output code")
    axis.set_xlim(min(vdds) - 0.008, max(vdds) + 0.010)
    axis.set_ylim(min(codes) - 0.35, max(codes) + 0.75)
    axis.xaxis.set_major_locator(MultipleLocator(0.05))
    axis.xaxis.set_minor_locator(MultipleLocator(0.01))
    axis.yaxis.set_major_locator(MultipleLocator(1))
    axis.yaxis.set_minor_locator(MultipleLocator(0.5))
    axis.grid(which="major", color="#d0d0d0", linewidth=0.6)
    axis.grid(which="minor", color="#ebebeb", linewidth=0.4)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.legend(loc="upper right", frameon=True, framealpha=0.96, edgecolor="#aaaaaa")

    png_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(png_path, dpi=300, bbox_inches="tight")
    figure.savefig(pdf_path, bbox_inches="tight")
    plt.close(figure)


def build_argument_parser() -> argparse.ArgumentParser:
    """Keep the plotting interface explicit and limited to final evidence."""

    parser = argparse.ArgumentParser(description="render the Phase-3 final voltage-to-code figure")
    parser.add_argument("--input-csv", required=True, type=Path)
    parser.add_argument("--png", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Read final evidence and produce exactly one PNG/PDF figure pair."""

    args = build_argument_parser().parse_args(argv)
    rows = read_rows(args.input_csv)
    render_figure(rows, args.png, args.pdf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
