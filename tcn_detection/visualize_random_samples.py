#!/usr/bin/env python3
"""Render a reproducible SCI-style random overview of labelled TCN traces.

The script samples *complete traces*, not correlated sliding windows.  Each
panel therefore remains an independent electrical experiment and can show the
relationship between measured VDD_A, online Vernier code, and the separately
derived future timing-risk label without concealing trace boundaries.
"""

from __future__ import print_function

import argparse
import csv
import json
import random
from pathlib import Path

import matplotlib

# Batch machines usually have no display server.  Select the raster backend
# before importing pyplot so the same command works in tmux and CI as well as
# on an interactive workstation.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


# A restrained, colour-blind-friendly palette: VDD and sensor code retain
# strong visual priority, while label bands remain transparent contextual truth
# rather than obscuring the measured trace beneath them.
VDD_COLOR = "#007C91"
CODE_COLOR = "#253746"
LABEL_COLORS = {"0": "#D9E2E8", "1": "#F2C14E", "2": "#D65A4A"}
LABEL_NAMES = {"0": "Safe", "1": "Warning", "2": "Critical"}


def read_trace(path):
    """Load one versioned derived-label CSV and validate its basic trace contract.

    Args:
        path: A CSV in ``labels/v1/traces``.  The file is expected to contain
            exactly one trace copied from the immutable compact electrical
            layer, followed by slack-derived label columns.

    Returns:
        A chronologically ordered list of CSV dictionaries.

    Raises:
        ValueError: If the file does not describe one 500-capture trace.  A
            figure produced from a partial file would look plausible while
            hiding a failed dataset contract, so visualization fails closed.
    """

    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 500:
        raise ValueError("label trace must contain 500 captures: {}".format(path))
    trace_ids = {row["trace_id"] for row in rows}
    if len(trace_ids) != 1:
        raise ValueError("label trace mixes trace IDs: {}".format(path))
    return rows


def contiguous_label_spans(rows):
    """Return time spans for each eligible, constant hysteresis-label segment.

    The final eight captures deliberately lack a complete future horizon and
    are excluded from the bands.  They are not painted Safe, because doing so
    would visually imply timing truth that the dataset intentionally does not
    possess.
    """

    eligible = [row for row in rows if row["label_eligible"].lower() == "true"]
    spans = []
    start = 0
    while start < len(eligible):
        label = eligible[start]["hysteresis_label"]
        end = start + 1
        while end < len(eligible) and eligible[end]["hysteresis_label"] == label:
            end += 1
        # The sample period is 4 ns.  Extending the final point by one capture
        # makes a single-capture Critical/Warning band visible at paper scale.
        left = float(eligible[start]["sample_time_s"]) * 1.0e9
        right = float(eligible[end - 1]["sample_time_s"]) * 1.0e9 + 4.0
        spans.append((left, right, label))
        start = end
    return spans


def plot_trace_panel(axis, rows, panel_index):
    """Draw one trace panel with modular electrical, sensor, and label layers.

    Args:
        axis: Primary Matplotlib axis used only for measured VDD_A and the
            semi-transparent risk background.  The paired sensor-code axis is
            created locally to avoid sharing state across panels.
        rows: One full 500-capture labelled trace from :func:`read_trace`.
        panel_index: One-based panel number used as a compact publication
            locator, e.g. ``(a)`` through ``(l)``.
    """

    times_ns = [float(row["sample_time_s"]) * 1.0e9 for row in rows]
    vdd_mv = [float(row["measured_vdd_a_v"]) * 1.0e3 for row in rows]
    code = [int(row["sensor_code"]) for row in rows]
    for left, right, label in contiguous_label_spans(rows):
        axis.axvspan(left, right, color=LABEL_COLORS[label], alpha=0.24, linewidth=0, zorder=0)
    axis.plot(times_ns, vdd_mv, color=VDD_COLOR, linewidth=1.15, zorder=3)
    axis.set_xlim(times_ns[0], times_ns[-1])
    axis.set_ylim(min(vdd_mv) - 2.0, max(vdd_mv) + 2.0)
    axis.grid(axis="y", color="#D8DEE3", linewidth=0.45, alpha=0.8)
    axis.tick_params(axis="both", labelsize=7.5, width=0.65, length=3)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    code_axis = axis.twinx()
    code_axis.step(times_ns, code, where="mid", color=CODE_COLOR, linewidth=0.78, alpha=0.86, zorder=4)
    code_axis.set_ylim(-0.5, 32.5)
    code_axis.set_yticks((0, 16, 32))
    code_axis.tick_params(axis="y", labelsize=7.5, width=0.65, length=3, colors=CODE_COLOR)
    code_axis.spines["top"].set_visible(False)
    code_axis.spines["left"].set_visible(False)
    first = rows[0]
    # OOD family names can be longer than a one-column panel.  A deliberate
    # two-line title preserves the full scientific identifier without title
    # collisions between adjacent panels in a journal-width grid.
    title = "({}) {} | {}\n{}".format(chr(ord("a") + panel_index), first["trace_id"][-8:],
                                        first["split"], first["waveform_family_id"])
    axis.set_title(title, fontsize=7.7, linespacing=1.18, loc="left", pad=4.0, fontweight="semibold")


def main():
    """Sample requested traces once and write the figure plus selection provenance."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-dir", required=True, type=Path,
                        help="Versioned derived label CSV directory, never the compact source directory.")
    parser.add_argument("--output", required=True, type=Path,
                        help="PNG or PDF overview figure; its suffix selects the Matplotlib format.")
    parser.add_argument("--selection-output", required=True, type=Path,
                        help="JSON recording seed, source directory, and sampled trace IDs.")
    parser.add_argument("--seed", type=int, default=20260727,
                        help="Deterministic seed used for uniform sampling without replacement.")
    parser.add_argument("--count", type=int, default=12,
                        help="Number of complete trace files to sample; this overview defaults to twelve.")
    args = parser.parse_args()
    sources = sorted(args.label_dir.glob("*.csv"))
    if len(sources) < args.count:
        raise ValueError("requested {} traces but only {} label CSVs exist".format(args.count, len(sources)))
    # ``Random.sample`` is uniform without replacement.  Sorting the source
    # list removes filesystem-order variability, while recording the seed and
    # selected IDs makes the exact paper figure reconstructible.
    selected = random.Random(args.seed).sample(sources, args.count)
    traces = [(path, read_trace(path)) for path in selected]
    columns = 3
    rows_count = (args.count + columns - 1) // columns
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5, "axes.linewidth": 0.7,
                         "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.dpi": 400})
    figure, axes = plt.subplots(rows_count, columns, figsize=(12.2, 9.1), sharex=True)
    axes = list(axes.flat)
    for index, (_, trace_rows) in enumerate(traces):
        plot_trace_panel(axes[index], trace_rows, index)
    for axis in axes[args.count:]:
        axis.set_visible(False)
    for axis in axes[(rows_count - 1) * columns:args.count]:
        axis.set_xlabel("Time (ns)", fontsize=8.5)
    for row_index in range(rows_count):
        axes[row_index * columns].set_ylabel("Measured VDD_A (mV)", fontsize=8.5, color=VDD_COLOR)
    figure.text(0.987, 0.51, "Vernier sensor code", rotation=90, va="center", ha="right", fontsize=8.5, color=CODE_COLOR)
    legend_handles = [Line2D([0], [0], color=VDD_COLOR, lw=1.3, label="Measured VDD_A"),
                      Line2D([0], [0], color=CODE_COLOR, lw=1.0, label="Sensor code")]
    legend_handles.extend(Patch(facecolor=LABEL_COLORS[key], alpha=0.45, label=LABEL_NAMES[key]) for key in ("0", "1", "2"))
    figure.legend(handles=legend_handles, loc="upper center", ncol=5, frameon=False, fontsize=8.2,
                  bbox_to_anchor=(0.5, 0.993), columnspacing=1.1, handlelength=1.8)
    figure.subplots_adjust(left=0.065, right=0.94, top=0.94, bottom=0.07, hspace=0.43, wspace=0.27)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, bbox_inches="tight")
    plt.close(figure)
    selection = {"schema_version": 1, "seed": args.seed, "sample_count": args.count,
                 "label_dir": str(args.label_dir.resolve()),
                 "samples": [{"trace_id": rows[0]["trace_id"], "base_waveform_id": rows[0]["base_waveform_id"],
                              "split": rows[0]["split"], "waveform_family_id": rows[0]["waveform_family_id"]}
                             for _, rows in traces]}
    args.selection_output.parent.mkdir(parents=True, exist_ok=True)
    args.selection_output.write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
