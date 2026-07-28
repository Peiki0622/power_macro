#!/usr/bin/env python3
"""Create a traceable monotonic VDD-to-slack map from timing evidence.

The map is a *label truth source*, not an online TCN feature.  It is written
once into a versioned derived-data directory, together with a short report
that binds the voltage/slack points to their timing-analysis input SHA256.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TIMING = ROOT / "chiplets" / "FIR" / "timing_droop" / "runs" / "fir_parallel_ro_bank_timing_765mhz_20260724_r3" / "timing_analysis" / "bank_timing_summary.csv"


def sha256_file(path):
    """Return a bounded-memory digest for one reproducibility input."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_map(base_source, explicit_source=None):
    """Return one sorted monotonic map from coarse and explicit timing evidence.

    The ``control`` scenario is intentionally replaced with the nominal-path
    union anchor at exactly 1.1 V.  The source control row measures 1.099 V
    under activity, while this anchor represents the calibrated no-droop
    condition used by the direct-rail sensor dataset.
    """

    rows = []
    with base_source.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["scenario"] == "control":
                continue
            rows.append({"source_scenario": row["scenario"], "vdd_a_v": float(row["a_active_min_v"]),
                         "worst_slack_ps": float(row["worst_derated_slack_ns"]) * 1000.0})
    rows.append({"source_scenario": "nominal_path_union", "vdd_a_v": 1.1, "worst_slack_ps": 9.226})
    if explicit_source is not None:
        # Explicit boundary rows are generated from the same frozen PrimeTime
        # catalog as the coarse map.  Keeping their source scenario instead
        # of collapsing duplicate-looking values preserves an audit trail for
        # every new label boundary used by the formal corpus.
        with explicit_source.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                rows.append({"source_scenario": row["source_scenario"], "vdd_a_v": float(row["vdd_a_v"]),
                             "worst_slack_ps": float(row["worst_slack_ps"])})
    rows.sort(key=lambda item: item["vdd_a_v"])
    for previous, current in zip(rows, rows[1:]):
        # Rising VDD must never reduce the mapped worst slack.  This catches a
        # source-column unit error before any labels are materialized.
        if current["worst_slack_ps"] < previous["worst_slack_ps"] - 1.0e-9:
            raise ValueError("slack map is not monotonic with rising VDD_A")
    return rows


def main():
    """Write one map CSV and its source-grounded Markdown provenance report."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--base-source", type=Path, default=TIMING,
                        help="Coarse approved timing table; defaults to the reviewed 765 MHz Pilot source.")
    parser.add_argument("--explicit-source", type=Path,
                        help="Optional explicit-VDD calibration CSV produced by calibrate_vdd_slack.py.")
    args = parser.parse_args()
    if args.output.exists() or args.report.exists():
        raise ValueError("refusing to overwrite slack-map output")
    rows = build_map(args.base_source, args.explicit_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["source_scenario", "vdd_a_v", "worst_slack_ps"])
        writer.writeheader()
        writer.writerows(rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        "# Slack Map V2\n\n"
        "- Coarse timing source: `{}`\n"
        "- Coarse timing source SHA256: `{}`\n"
        "- Explicit boundary source: `{}`\n"
        "- Explicit boundary source SHA256: `{}`\n"
        "- Point count: {}\n"
        "- VDD_A coverage: {:.12f} V to {:.12f} V\n"
        "- Worst-slack coverage: {:.9f} ps to {:.9f} ps\n"
        "- Interpolation: bounded linear; extrapolation is prohibited.\n".format(
            args.base_source.resolve(), sha256_file(args.base_source),
            "" if args.explicit_source is None else args.explicit_source.resolve(),
            "" if args.explicit_source is None else sha256_file(args.explicit_source),
            len(rows), rows[0]["vdd_a_v"], rows[-1]["vdd_a_v"], rows[0]["worst_slack_ps"],
            rows[-1]["worst_slack_ps"]), encoding="utf-8")


if __name__ == "__main__":
    main()
