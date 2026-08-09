#!/usr/bin/env python3
"""Render the measured FTC static output-code transfer as a publication SVG.

The script deliberately uses only Python's standard library so the figure can
be regenerated in the characterization environment without installing a
plotting package.  It reads the compact HSPICE-derived CSV rather than a raw
waveform, and writes the resulting vector figure only below ``reports/figures``.
"""

import argparse
import csv
from pathlib import Path


WIDTH = 900
HEIGHT = 700
LEFT = 105
RIGHT = 50
TOP = 55
PANEL_HEIGHT = 220
GAP = 95
PLOT_WIDTH = WIDTH - LEFT - RIGHT
BLUE = "#0072B2"
ORANGE = "#D55E00"
GRAY = "#D9D9D9"
BLACK = "#202020"


def x_coordinate(voltage: float) -> float:
    """Map the formal 0.75--1.10 V range onto the shared horizontal axis."""

    return LEFT + (voltage - 0.75) / (1.10 - 0.75) * PLOT_WIDTH


def y_coordinate(value: float, minimum: float, maximum: float, panel_top: float) -> float:
    """Map a measured integer code onto one panel with an upward data axis."""

    return panel_top + PANEL_HEIGHT - (value - minimum) / (maximum - minimum) * PANEL_HEIGHT


def polyline(rows, key: str, minimum: float, maximum: float, panel_top: float) -> str:
    """Return an SVG point list for one measured output-code series."""

    return " ".join(
        "{:.2f},{:.2f}".format(x_coordinate(row["vdd"]), y_coordinate(row[key], minimum, maximum, panel_top))
        for row in rows
    )


def render(input_path: Path, output_path: Path) -> None:
    """Create a two-panel, journal-style vector plot from valid captured words."""

    with input_path.open(newline="", encoding="utf-8") as stream:
        rows = [
            {"vdd": float(row["vdd_v"]), "start": int(row["start_index"]), "end": int(row["end_index"]), "length": int(row["one_run_length"])}
            for row in csv.DictReader(stream)
            if int(row["valid"]) == 1 and 0.75 <= float(row["vdd_v"]) <= 1.10
        ]
    if len(rows) != 36:
        raise ValueError("expected 36 valid 0.75--1.10 V FTC static points, found {}".format(len(rows)))
    rows.sort(key=lambda row: row["vdd"])
    lower_top = TOP + PANEL_HEIGHT + GAP
    pieces = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 {} {}">'.format(WIDTH, HEIGHT, WIDTH, HEIGHT),
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,\'Liberation Sans\',sans-serif;fill:%s} .axis{stroke:%s;stroke-width:1.4} .grid{stroke:%s;stroke-width:1} .tick{font-size:15px} .label{font-size:17px;font-weight:600} .panel{font-size:18px;font-weight:700}</style>' % (BLACK, BLACK, GRAY),
    ]
    # Both panels share VDD ticks and use integer y grids to make stage movement readable.
    for panel_top, ymin, ymax, ylabel, panel_label in ((TOP, 0, 20, "Output code index", "(a) Captured FTC code"), (lower_top, 0, 10, "Longest 1-run length", "(b) Window length")):
        pieces.append('<text class="panel" x="{}" y="{}">{}</text>'.format(LEFT, panel_top - 20, panel_label))
        for value in range(ymin, ymax + 1, 2):
            y = y_coordinate(value, ymin, ymax, panel_top)
            pieces.append('<line class="grid" x1="{}" y1="{:.2f}" x2="{}" y2="{:.2f}"/>'.format(LEFT, y, LEFT + PLOT_WIDTH, y))
            pieces.append('<text class="tick" x="{}" y="{:.2f}" text-anchor="end" dominant-baseline="middle">{}</text>'.format(LEFT - 12, y, value))
        pieces.append('<line class="axis" x1="{}" y1="{}" x2="{}" y2="{}"/>'.format(LEFT, panel_top, LEFT, panel_top + PANEL_HEIGHT))
        pieces.append('<line class="axis" x1="{}" y1="{}" x2="{}" y2="{}"/>'.format(LEFT, panel_top + PANEL_HEIGHT, LEFT + PLOT_WIDTH, panel_top + PANEL_HEIGHT))
        pieces.append('<text class="label" transform="translate(28 {:.2f}) rotate(-90)" text-anchor="middle">{}</text>'.format(panel_top + PANEL_HEIGHT / 2, ylabel))
    for voltage in (0.75, 0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10):
        x = x_coordinate(voltage)
        pieces.append('<line class="axis" x1="{:.2f}" y1="{}" x2="{:.2f}" y2="{}"/>'.format(x, lower_top + PANEL_HEIGHT, x, lower_top + PANEL_HEIGHT + 7))
        pieces.append('<text class="tick" x="{:.2f}" y="{}" text-anchor="middle">{:.2f}</text>'.format(x, lower_top + PANEL_HEIGHT + 29, voltage))
    pieces.append('<text class="label" x="{}" y="{}" text-anchor="middle">Supply voltage VDD (V)</text>'.format(LEFT + PLOT_WIDTH / 2, HEIGHT - 34))
    # Start and end are the public FTC symbols.  Markers show every real 10 mV sample.
    for key, color, legend, offset in (("start", BLUE, "Start index", 0), ("end", ORANGE, "End index", 165)):
        pieces.append('<polyline fill="none" stroke="{}" stroke-width="2.6" points="{}"/>'.format(color, polyline(rows, key, 0, 20, TOP)))
        for row in rows:
            pieces.append('<circle cx="{:.2f}" cy="{:.2f}" r="3.2" fill="white" stroke="{}" stroke-width="1.8"/>'.format(x_coordinate(row["vdd"]), y_coordinate(row[key], 0, 20, TOP), color))
        pieces.append('<line x1="{}" y1="{}" x2="{}" y2="{}" stroke="{}" stroke-width="2.6"/>'.format(LEFT + 410 + offset, TOP - 25, LEFT + 436 + offset, TOP - 25, color))
        pieces.append('<text class="tick" x="{}" y="{}">{}</text>'.format(LEFT + 443 + offset, TOP - 20, legend))
    pieces.append('<polyline fill="none" stroke="{}" stroke-width="2.6" points="{}"/>'.format(BLUE, polyline(rows, "length", 0, 10, lower_top)))
    for row in rows:
        pieces.append('<circle cx="{:.2f}" cy="{:.2f}" r="3.2" fill="white" stroke="{}" stroke-width="1.8"/>'.format(x_coordinate(row["vdd"]), y_coordinate(row["length"], 0, 10, lower_top), BLUE))
    pieces.append('<text class="tick" x="{}" y="{}">TT, 25 C; 30-stage RVT/LVT FTC-style sensor; 10 mV static steps</text>'.format(LEFT, HEIGHT - 10))
    pieces.append('</svg>')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(pieces) + "\n", encoding="utf-8")


def main() -> int:
    """Provide reproducible default paths while allowing explicit evidence paths."""

    ftc_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="render FTC static output-code transfer SVG")
    parser.add_argument("--input", type=Path, default=ftc_root / "runs/static_fine/static_transfer.csv")
    parser.add_argument("--output", type=Path, default=ftc_root / "reports/figures/ftc_output_code_vs_vdd.svg")
    args = parser.parse_args()
    render(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
