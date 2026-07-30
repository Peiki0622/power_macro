#!/usr/bin/env python3
"""Derive immutable, same-sample operating-state labels from mapped slack.

This module intentionally consumes the published ``labels/v2`` CSV layer
rather than recomputing electrical slack from voltage.  That design preserves
the already audited VDD-to-slack mapping byte for byte and gives the new state
monitoring task a narrow truth dependency: the ``mapped_slack_ps`` value on
the same row.  Sensor observations and future rows are never passed to the
classification function, so they cannot leak into the target.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


SAFE_LABEL = 0
WARNING_LABEL = 1
CRITICAL_LABEL = 2


def sha256_file(path):
    """Return a bounded-memory digest suitable for immutable provenance."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def current_state_label(mapped_slack_ps, warning_slack_ps=5.0):
    """Map one current slack measurement to the ordered three-state target.

    The boundary semantics are deliberately explicit:

    * Safe requires strictly more than ``warning_slack_ps``.
    * Warning includes the upper boundary and requires positive slack.
    * Critical includes zero because zero slack already has no timing margin.

    Accepting only a scalar slack value is a structural safeguard: neither a
    sensor code nor surrounding samples can influence this ground truth.
    """

    slack = float(mapped_slack_ps)
    if slack > float(warning_slack_ps):
        return SAFE_LABEL
    if slack > 0.0:
        return WARNING_LABEL
    return CRITICAL_LABEL


def derive_rows(rows, warning_slack_ps=5.0):
    """Copy source rows and append current-state truth for every capture.

    Unlike the former future-prediction task, the current-state task has no
    incomplete tail horizon.  Every row with an existing mapped slack value is
    therefore eligible.  ``current_slack_ps`` repeats the source text exactly
    instead of reformatting the float; this avoids introducing irrelevant
    numeric round-off into the derived evidence layer.
    """

    derived = []
    for source in rows:
        if source.get("mapped_slack_ps", "") == "":
            raise ValueError("mapped_slack_ps is required for every state label")
        row = dict(source)
        row.update({
            "current_slack_ps": source["mapped_slack_ps"],
            "current_raw_label": str(current_state_label(
                source["mapped_slack_ps"], warning_slack_ps)),
            "state_label_eligible": "True",
        })
        derived.append(row)
    return derived


def load_corpus_splits(path):
    """Load the authoritative trace-to-split assignment from JSON Lines."""

    assignments = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            trace_id = record["trace_id"]
            if trace_id in assignments:
                raise ValueError("duplicate corpus trace_id at line {}: {}".format(
                    line_number, trace_id))
            assignments[trace_id] = record["split"]
    return assignments


def main():
    """Publish one non-overwriting state-label directory and its manifest."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path,
                        help="Published labels/v2 trace directory.")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="New state_code_v1 trace directory; it must not exist.")
    parser.add_argument("--corpus", required=True, type=Path,
                        help="Authoritative corpus used to validate membership and splits.")
    parser.add_argument("--source-provenance", required=True, type=Path,
                        help="Published labels/v2 provenance manifest.")
    parser.add_argument("--manifest", required=True, type=Path,
                        help="Output provenance path outside the trace subdirectory.")
    parser.add_argument("--warning-slack-ps", type=float, default=5.0)
    args = parser.parse_args()

    # A published derived-data version is append-never.  Refusing even an
    # empty pre-created target prevents a partial failed run from being
    # mistaken for a complete immutable release.
    if args.output_dir.exists() or args.manifest.exists():
        raise ValueError("refusing to overwrite state-label release")

    corpus_splits = load_corpus_splits(args.corpus)
    source_manifest = json.loads(args.source_provenance.read_text(encoding="utf-8"))
    source_entries = {entry["trace_id"]: entry for entry in source_manifest["traces"]}
    source_paths = sorted(args.source_dir.glob("*.csv"))
    if len(source_paths) != len(corpus_splits) or set(source_entries) != set(corpus_splits):
        raise ValueError("source provenance and corpus membership differ")

    # Validate all inputs before creating the destination.  This ordering
    # keeps failures recoverable and ensures no half-published directory is
    # left behind because a late source digest or membership check failed.
    prepared = []
    for source_path in source_paths:
        with source_path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != 500:
            raise ValueError("source trace must contain 500 rows: {}".format(source_path))
        trace_ids = {row["trace_id"] for row in rows}
        splits = {row["split"] for row in rows}
        if len(trace_ids) != 1 or len(splits) != 1:
            raise ValueError("trace identity or split changes within {}".format(source_path))
        trace_id = next(iter(trace_ids))
        split = next(iter(splits))
        if trace_id not in corpus_splits or corpus_splits[trace_id] != split:
            raise ValueError("trace split disagrees with corpus: {}".format(trace_id))
        expected_digest = source_entries[trace_id]["label_sha256"]
        if sha256_file(source_path) != expected_digest:
            raise ValueError("source label digest mismatch: {}".format(trace_id))
        prepared.append((source_path, trace_id, split, derive_rows(
            rows, args.warning_slack_ps)))

    args.output_dir.mkdir(parents=True, exist_ok=False)
    output_entries = []
    split_counts = defaultdict(Counter)
    for source_path, trace_id, split, rows in prepared:
        output_path = args.output_dir / source_path.name
        temporary_path = output_path.with_suffix(".csv.tmp")
        with temporary_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        # Atomic rename means readers observe either no trace or one complete
        # trace, never a CSV that is still being streamed.
        temporary_path.replace(output_path)
        counts = Counter(int(row["current_raw_label"]) for row in rows)
        split_counts[split].update(counts)
        output_entries.append({
            "trace_id": trace_id,
            "split": split,
            "source_csv": source_path.name,
            "source_sha256": sha256_file(source_path),
            "label_csv": output_path.name,
            "label_sha256": sha256_file(output_path),
            "row_count": len(rows),
            "class_counts": {str(label): counts[label] for label in range(3)},
        })

    manifest = {
        "schema_version": 1,
        "task": "same_sample_current_state_monitoring",
        "class_names": {"0": "Safe", "1": "Warning", "2": "Critical"},
        "thresholds": {"safe": "slack_ps > 5", "warning": "0 < slack_ps <= 5",
                       "critical": "slack_ps <= 0"},
        "future_horizon_samples": 0,
        "warning_slack_ps": args.warning_slack_ps,
        "corpus": str(args.corpus.resolve()),
        "corpus_sha256": sha256_file(args.corpus),
        "source_dir": str(args.source_dir.resolve()),
        "source_provenance": str(args.source_provenance.resolve()),
        "source_provenance_sha256": sha256_file(args.source_provenance),
        "source_trace_count": len(output_entries),
        "row_count": sum(entry["row_count"] for entry in output_entries),
        "split_class_counts": {
            split: {str(label): split_counts[split][label] for label in range(3)}
            for split in sorted(split_counts)
        },
        "traces": output_entries,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")


if __name__ == "__main__":
    main()
