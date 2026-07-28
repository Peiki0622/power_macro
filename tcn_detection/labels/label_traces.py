#!/usr/bin/env python3
"""Materialize future timing-risk labels without changing electrical evidence.

The source compact CSVs remain the immutable electrical-fact layer.  This
module copies each source row into a separate label directory and appends only
slack-derived truth columns; it never uses sensor codes to decide labels.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from pathlib import Path


def load_map(path):
    """Load and sort finite map points for bounded linear interpolation."""

    with path.open(newline="", encoding="utf-8") as stream:
        rows = [{"v": float(row["vdd_a_v"]), "s": float(row["worst_slack_ps"])} for row in csv.DictReader(stream)]
    return sorted(rows, key=lambda row: row["v"])


def sha256_file(path):
    """Hash an input or derived artifact without loading it all into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def interpolate(points, voltage):
    """Interpolate only inside measured voltage bounds; never silently extrapolate."""

    if voltage < points[0]["v"] or voltage > points[-1]["v"]:
        raise ValueError("VDD_A lies outside slack-map bounds")
    for left, right in zip(points, points[1:]):
        if left["v"] <= voltage <= right["v"]:
            if right["v"] == left["v"]:
                return min(left["s"], right["s"])
            ratio = (voltage - left["v"]) / (right["v"] - left["v"])
            return left["s"] + ratio * (right["s"] - left["s"])
    return points[-1]["s"]


def hysteresis(raw, slack, recover_samples, recover_slack):
    """Prevent rapid downgrade while retaining immediate future-risk upgrades."""

    state = raw[0]
    safe_count = 0
    output = [state]
    for index in range(1, len(raw)):
        if raw[index] > state:
            state = raw[index]
            safe_count = 0
        elif state != 0 and slack[index] > recover_slack:
            safe_count += 1
            if safe_count >= recover_samples:
                state = max(0, state - 1)
                safe_count = 0
        else:
            safe_count = 0
        output.append(state)
    return output


def label_rows(rows, points, label_cfg):
    """Return copied rows with causal future-risk labels appended.

    ``future_min_slack_ps[e]`` deliberately examines exactly ``e+1..e+H``.
    This leaves the sensor history ending at ``e`` available to a causal model
    while reserving the following H captures as timing truth.  The final H
    rows cannot have a complete future horizon and are explicitly marked
    ineligible instead of receiving fabricated safe labels.
    """

    horizon = int(label_cfg["prediction_horizon_samples"])
    warning = float(label_cfg["warning_slack_ps"])
    slack = [interpolate(points, float(row["measured_vdd_a_v"])) for row in rows]
    future = [None] * len(rows)
    time_to_violation = [None] * len(rows)
    raw = [None] * len(rows)
    for end in range(len(rows) - horizon):
        future_slice = slack[end + 1:end + horizon + 1]
        future[end] = min(future_slice)
        violation_offset = next((offset for offset, value in enumerate(future_slice, start=1) if value <= 0.0), None)
        time_to_violation[end] = violation_offset
        raw[end] = 2 if future[end] <= 0.0 else 1 if future[end] <= warning else 0
    # Hysteresis uses the same slack-derived future state.  Ineligible tail
    # entries are only placeholders for the state machine and are blanked
    # again before output, so they cannot become train or evaluation targets.
    stable = hysteresis([value if value is not None else 0 for value in raw],
                        [value if value is not None else 0.0 for value in future],
                        int(label_cfg["recover_samples"]), float(label_cfg["recover_safe_slack_ps"]))
    labelled = []
    for index, source in enumerate(rows):
        row = dict(source)
        eligible = raw[index] is not None
        row.update({
            "mapped_slack_ps": "{:.9f}".format(slack[index]),
            "future_min_slack_ps": "" if future[index] is None else "{:.9f}".format(future[index]),
            "time_to_violation_samples": "" if time_to_violation[index] is None else str(time_to_violation[index]),
            "raw_label": "" if not eligible else str(raw[index]),
            "hysteresis_label": "" if not eligible else str(stable[index]),
            "label_eligible": str(eligible),
        })
        labelled.append(row)
    return labelled


def main():
    """Copy every compact trace to a versioned, labelled derived-data layer."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--slack-map", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path,
                        help="Authoritative corpus whose trace IDs and split assignments this label layer represents.")
    parser.add_argument("--requeue-ledger", type=Path,
                        help="Optional correction ledger retained when a trace was rerun with a corrected specification.")
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    # A derived label layer is immutable once published: accepting an empty
    # pre-created directory would otherwise make its lifecycle ambiguous and
    # could hide a partial earlier invocation.
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite derived label directory: {}".format(args.output_dir))
    label_cfg = json.loads(args.config.read_text(encoding="utf-8"))
    points = load_map(args.slack_map)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    outputs = []
    for source in sorted(args.source_dir.glob("*.csv")):
        with source.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != 500:
            raise ValueError("compact trace must contain 500 captures: {}".format(source))
        labelled = label_rows(rows, points, label_cfg)
        fields = list(labelled[0].keys())
        temporary = args.output_dir / (source.stem + ".csv.tmp")
        output = args.output_dir / source.name
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(labelled)
        temporary.replace(output)
        outputs.append({"trace_id": rows[0]["trace_id"], "source_csv": source.name, "source_sha256": sha256_file(source),
                        "label_csv": output.name, "label_sha256": sha256_file(output), "row_count": len(labelled)})
    # Hash every source that defines label truth or corpus membership.  This
    # permits a later consumer to prove that no historic, superseded corpus
    # was accidentally used after the 99.9 mV corrected rerun.
    manifest = {"schema_version": 1, "label_config_sha256": sha256_file(args.config),
                "slack_map_sha256": sha256_file(args.slack_map), "corpus": str(args.corpus.resolve()),
                "corpus_sha256": sha256_file(args.corpus),
                "requeue_ledger": "" if args.requeue_ledger is None else str(args.requeue_ledger.resolve()),
                "requeue_ledger_sha256": "" if args.requeue_ledger is None else sha256_file(args.requeue_ledger),
                "source_dir": str(args.source_dir.resolve()),
                "source_trace_count": len(outputs), "traces": outputs}
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
