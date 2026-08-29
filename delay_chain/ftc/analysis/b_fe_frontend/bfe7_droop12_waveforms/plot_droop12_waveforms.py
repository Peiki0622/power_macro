#!/usr/bin/env python3
"""Render the paper-facing BFE7 12-panel atlas from frozen CSV stimuli.

The plotting boundary is deliberately file-based: every solid waveform is
read from a generated CSV whose SHA256 is present in ``DROOP12_MANIFEST.json``.
The script never reconstructs an ideal attack for plotting.  This keeps the
figure faithful to the exact HSPICE-feedable source and makes a changed plot
trace detectable through the manifest audit.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


NOMINAL_V = 1.10
EDGE_PS = {"T_E": 21000, "T_E1": 31000, "T_E2": 41000, "T_E3": 51000}
GROUPS = ("A", "B", "C", "D")


def sha256_file(path):
    """Return one artifact digest for manifest-to-plot provenance."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_waveform(path):
    """Read only the generated CSV numerical columns used by the plot."""

    with Path(path).open(newline="", encoding="ascii") as stream:
        rows = list(csv.DictReader(stream))
    return ([float(row["time_s"]) * 1.0e9 - 21.0 for row in rows],
            [float(row["vdd_v"]) for row in rows])


def audit_manifest(root, contract, manifest):
    """Resolve every scenario CSV and require its frozen manifest SHA256."""

    audited = []
    file_entries = manifest.get("files", {})
    for record in contract["scenarios"]:
        stem = record["scenario_id"] + "_" + record["short_name"]
        path = root / "waveforms" / (stem + ".csv")
        relative = str(path.relative_to(root))
        matching = [entry for entry in file_entries.values() if entry["path"] == relative]
        if len(matching) != 1 or sha256_file(path) != matching[0]["sha256"]:
            raise ValueError("plot input is absent or hash-mismatched: {}".format(relative))
        audited.append({"scenario_id": record["scenario_id"], "path": relative, "sha256": matching[0]["sha256"]})
    return audited


def render(root):
    """Create the 4x3 grayscale-readable atlas and a trace audit JSON."""

    root = Path(root)
    contract = json.loads((root / "DROOP12_WAVEFORM_CONTRACT.json").read_text(encoding="ascii"))
    manifest = json.loads((root / "DROOP12_MANIFEST.json").read_text(encoding="ascii"))
    audited = audit_manifest(root, contract, manifest)
    by_id = {item["scenario_id"]: item for item in audited}
    records = {record["scenario_id"]: record for record in contract["scenarios"]}
    plt.rcParams.update({"font.family": "serif", "font.size": 8, "axes.linewidth": 0.55, "xtick.major.width": 0.45, "ytick.major.width": 0.45})
    figure, axes = plt.subplots(4, 3, figsize=(7.2, 7.0), sharey=True)
    axes = axes.reshape(4, 3)
    colors = {"A": "#202020", "B": "#505050", "C": "#303030", "D": "#606060"}
    panel_index = 0
    for row_index, group in enumerate(GROUPS):
        for column_index, record in enumerate(record for record in contract["scenarios"] if record["group"] == group):
            axis = axes[row_index, column_index]
            times_ns, voltage = read_waveform(root / by_id[record["scenario_id"]]["path"])
            axis.plot(times_ns, voltage, color=colors[group], linewidth=0.85, label="VDD monitored" if panel_index == 0 else None)
            axis.axhline(NOMINAL_V, color="black", linestyle="--", linewidth=0.45, label="1.10 V nominal" if panel_index == 0 else None)
            left, right = min(times_ns), max(times_ns)
            margin = max(0.25, 0.04 * (right - left))
            axis.set_xlim(left - margin, right + margin)
            for edge_name, edge_ps in EDGE_PS.items():
                edge_ns = edge_ps / 1000.0 - 21.0
                if left - margin <= edge_ns <= right + margin:
                    axis.axvline(edge_ns, color="#888888", linestyle=":", linewidth=0.4)
                    if edge_name in ("T_E", "T_E1"):
                        axis.text(edge_ns, 1.108, "R" if edge_name in ("T_E", "T_E2") else "F", ha="center", va="top", fontsize=6, color="#555555")
            axis.set_title("({}) {} {}".format(chr(ord("a") + panel_index), record["scenario_id"], record["short_name"].replace("_", " ").title()), fontsize=8)
            axis.grid(False)
            axis.tick_params(direction="out", length=2.2, pad=1.5)
            if row_index == 3:
                axis.set_xlabel("Time relative to T_E (ns)")
            if column_index == 0:
                axis.set_ylabel("VDD_MONITORED (V)")
            panel_index += 1
    figure.legend(loc="lower center", ncol=2, frameon=False, fontsize=7, bbox_to_anchor=(0.5, 0.005))
    figure.tight_layout(rect=(0.0, 0.035, 1.0, 1.0), h_pad=0.65, w_pad=0.45)
    pdf_path = root / "BFE7_DROOP12_WAVEFORM_ATLAS.pdf"
    png_path = root / "BFE7_DROOP12_WAVEFORM_ATLAS.png"
    figure.savefig(pdf_path, format="pdf")
    figure.savefig(png_path, format="png", dpi=600)
    plt.close(figure)
    audit_path = root / "BFE7_W5_PLOT_INPUT_AUDIT.json"
    audit_path.write_text(json.dumps({"source": "generated CSV only", "traces": audited}, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return pdf_path, png_path, audit_path


def main(argv=None):
    """CLI entry point for deterministic atlas generation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args(argv)
    outputs = render(args.root)
    print("BFE7_W5_ATLAS_PASS pdf={} png={} audit={}".format(*[str(path) for path in outputs]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
