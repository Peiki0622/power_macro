#!/usr/bin/env python3
"""Evaluate the approved Talukdar timing model at explicit VDD_A points.

The Pilot slack map was assembled from a coarse parallel-RO-bank sweep.  This
tool adds only finite, requested VDD_A points near the Warning and Critical
boundaries.  It reuses the immutable 765 MHz PrimeTime path catalog and
path-point evidence; it neither changes the routed design nor treats a sensor
code as timing truth.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha256_file(path):
    """Return a bounded-memory digest for one timing-evidence input."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path):
    """Load one RFC-4180 timing CSV and reject empty evidence files."""

    with Path(path).open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("timing evidence is empty: {}".format(path))
    return rows


def derating_factor(vdd_a_v, vnom_v, vth_v):
    """Compute Talukdar Eq. (1) while enforcing its physical voltage domain."""

    voltage = float(vdd_a_v)
    if not float(vth_v) < voltage <= float(vnom_v):
        raise ValueError("VDD_A is outside Talukdar model domain: {:.12f} V".format(voltage))
    denominator = 1.0 - float(vth_v) / voltage
    if denominator <= 0.0:
        raise ValueError("Talukdar denominator is non-positive")
    return (1.0 - float(vth_v) / float(vnom_v)) / denominator


def reconstruct_path_cells(catalog_path, points_path, expected_path_count):
    """Return ``path_id -> (nominal slack, summed physical cell delay)``.

    PrimeTime's point report alternates cell input and output records.  The
    arrival difference from an input to its immediately following output is
    the cell arc delay, so this reconstruction deliberately excludes nets,
    capture setup, clock-network delay, and constraints.  Those terms remain
    frozen inside the nominal path slack, exactly as in the reviewed Pilot
    timing model.
    """

    catalog_rows = read_csv(catalog_path)
    if len(catalog_rows) != int(expected_path_count):
        raise ValueError("catalog path count {} differs from expected {}".format(len(catalog_rows), expected_path_count))
    catalog = {row["path_id"]: row for row in catalog_rows}
    if len(catalog) != len(catalog_rows):
        raise ValueError("catalog contains duplicate path_id")
    grouped = {path_id: [] for path_id in catalog}
    for row in read_csv(points_path):
        path_id = row["path_id"]
        if path_id not in grouped:
            raise ValueError("path-point row references unknown path {}".format(path_id))
        grouped[path_id].append(row)
    result = {}
    for path_id, rows in grouped.items():
        rows.sort(key=lambda row: int(row["point_index"]))
        if len(rows) != int(catalog[path_id]["point_count"]) or len(rows) % 2 == 0:
            raise ValueError("malformed point sequence for {}".format(path_id))
        total_delay = 0.0
        for index, row in enumerate(rows):
            if int(row["point_index"]) != index + 1:
                raise ValueError("non-contiguous point indexes for {}".format(path_id))
            expected_direction = "in" if index % 2 == 0 else "out"
            if row["direction"] != expected_direction:
                raise ValueError("unexpected point direction for {}".format(path_id))
            if expected_direction == "out":
                source = rows[index - 1]
                if source["instance"] != row["instance"] or source["lib_cell"] != row["lib_cell"]:
                    raise ValueError("cell input/output mismatch for {}".format(path_id))
                arc_delay = float(row["arrival_ns"]) - float(source["arrival_ns"])
                if arc_delay <= 0.0:
                    raise ValueError("non-positive cell delay for {}".format(path_id))
                total_delay += arc_delay
        result[path_id] = (float(catalog[path_id]["slack_ns"]), total_delay)
    return result


def calculate_rows(path_cells, voltages, vnom_v, vth_v):
    """Calculate worst setup slack at each explicit VDD_A point in picoseconds."""

    output = []
    for voltage in sorted(set(float(value) for value in voltages)):
        factor = derating_factor(voltage, vnom_v, vth_v)
        slacks = {path_id: nominal - delay * (factor - 1.0) for path_id, (nominal, delay) in path_cells.items()}
        worst_path_id = min(slacks, key=slacks.get)
        output.append({"source_scenario": "explicit_vdd_{:.6f}V".format(voltage), "vdd_a_v": voltage,
                       "talukdar_delay_factor": factor, "worst_slack_ps": slacks[worst_path_id] * 1000.0,
                       "worst_path_id": worst_path_id})
    return output


def main():
    """Write non-overwriting direct-VDD calibration data and its provenance."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--points", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.report.exists():
        raise ValueError("refusing to overwrite calibration output")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    voltages = list(config["warning_boundary_points_v"]) + list(config["critical_boundary_points_v"])
    cells = reconstruct_path_cells(args.catalog, args.points, config["expected_path_count"])
    rows = calculate_rows(cells, voltages, config["vnom_v"], config["vth_v"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["source_scenario", "vdd_a_v", "talukdar_delay_factor", "worst_slack_ps", "worst_path_id"])
        writer.writeheader()
        writer.writerows(rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    # Use real line-feed characters so the retained run report renders as
    # Markdown.  Escaped ``\\n`` text would collapse the full provenance record
    # onto one line and make the only versioned calibration artifact unreadable.
    args.report.write_text(
        "# Explicit VDD Slack Calibration V2\n\n"
        "- Clock: {:.9f} MHz ({:.9f} ns)\n"
        "- Model: Talukdar Eq. (1), Vnom={:.6f} V, Vth={:.6f} V\n"
        "- Fixed PrimeTime path count: {}\n"
        "- Catalog SHA256: `{}`\n"
        "- Point CSV SHA256: `{}`\n"
        "- Config SHA256: `{}`\n"
        "- Explicit VDD points: {}\n"
        "- No low-voltage Liberty, net-delay, capture-setup, or clock-network re-analysis was introduced.\n".format(
            float(config["clock_frequency_mhz"]), float(config["clock_period_ns"]), float(config["vnom_v"]),
            float(config["vth_v"]), int(config["expected_path_count"]), sha256_file(args.catalog),
            sha256_file(args.points), sha256_file(args.config), ", ".join("{:.6f} V".format(row["vdd_a_v"]) for row in rows)),
        encoding="utf-8")


if __name__ == "__main__":
    main()
