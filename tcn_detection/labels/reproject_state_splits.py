#!/usr/bin/env python3
"""Reproject immutable current-state labels onto a new split assignment.

This command does not derive labels and does not read electrical waveforms.  It
copies the existing audited state-label CSVs and changes only their ``split``
column to match a new corpus.  The deliberately narrow transformation prevents
dataset repartitioning from silently changing truth, features, or row order.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path


def sha256_file(path):
    """Hash a possibly large provenance input using bounded memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_corpus_splits(path):
    """Return unique trace assignments from the authoritative new corpus."""

    assignments = {}
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            trace_id = row["trace_id"]
            if trace_id in assignments:
                raise ValueError("duplicate corpus trace at line {}".format(line_number))
            assignments[trace_id] = row["split"]
    if len(assignments) != 240:
        raise ValueError("new corpus must contain exactly 240 traces")
    if set(assignments.values()) != {"train", "validation", "iid_test"}:
        raise ValueError("new corpus must contain train/validation/iid_test only")
    return assignments


def assert_split_only_projection(source_rows, projected_rows, expected_split, path):
    """Prove that projection changed no CSV cell except ``split``.

    Comparison is performed on the original text returned by ``csv.DictReader``
    rather than parsed numeric values.  Consequently a harmless-looking float
    reformat, boolean spelling change, column loss, or row reorder is rejected.
    This exactness matters because the old label layer is frozen evidence.
    """

    if len(source_rows) != 500 or len(projected_rows) != len(source_rows):
        raise ValueError("state trace must contain exactly 500 rows: {}".format(path))
    for row_index, (source, projected) in enumerate(zip(source_rows, projected_rows)):
        if set(source) != set(projected) or "split" not in source:
            raise ValueError("CSV schema changed during projection: {}".format(path))
        if projected["split"] != expected_split:
            raise ValueError("projected split mismatch at row {}: {}".format(row_index, path))
        for field in source:
            if field != "split" and projected[field] != source[field]:
                raise ValueError("field {} changed at row {}: {}".format(
                    field, row_index, path))


def parse_args():
    """Parse all provenance dependencies explicitly."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-label-root", required=True, type=Path,
                        help="Frozen state_code_v1 directory containing traces/provenance.json.")
    parser.add_argument("--corpus", required=True, type=Path,
                        help="Published IID-only corpus with authoritative split values.")
    parser.add_argument("--split-provenance", required=True, type=Path,
                        help="Provenance manifest produced by repartition_state_iid.py.")
    parser.add_argument("--output-label-root", required=True, type=Path,
                        help="Absent version root to publish with traces/provenance.json.")
    return parser.parse_args()


def main():
    """Validate, transform, verify, and atomically publish all 240 label CSVs."""

    args = parse_args()
    if args.output_label_root.exists():
        raise FileExistsError("refusing to overwrite label release: {}".format(
            args.output_label_root))
    source_trace_dir = args.source_label_root / "traces"
    source_provenance_path = args.source_label_root / "provenance.json"
    source_provenance = json.loads(source_provenance_path.read_text(encoding="utf-8"))
    source_entries = {entry["trace_id"]: entry for entry in source_provenance["traces"]}
    corpus_splits = load_corpus_splits(args.corpus)
    split_provenance = json.loads(args.split_provenance.read_text(encoding="utf-8"))
    if split_provenance["published_corpus_sha256"] != sha256_file(args.corpus):
        raise ValueError("split provenance does not bind to the supplied corpus")
    if set(source_entries) != set(corpus_splits):
        raise ValueError("source label provenance and new corpus membership differ")

    # Preflight all immutable inputs before creating temporary output.  This
    # catches an incomplete source directory or modified old CSV before any
    # potentially publishable artifact exists.
    prepared = []
    for trace_id in sorted(corpus_splits):
        entry = source_entries[trace_id]
        source_path = source_trace_dir / entry["label_csv"]
        if sha256_file(source_path) != entry["label_sha256"]:
            raise ValueError("source state-label digest mismatch: {}".format(trace_id))
        with source_path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            source_rows = list(reader)
            fieldnames = list(reader.fieldnames or [])
        if len(source_rows) != 500 or {row["trace_id"] for row in source_rows} != {trace_id}:
            raise ValueError("source state-label trace is malformed: {}".format(trace_id))
        projected_rows = []
        for source_row in source_rows:
            projected = dict(source_row)
            projected["split"] = corpus_splits[trace_id]
            projected_rows.append(projected)
        assert_split_only_projection(
            source_rows, projected_rows, corpus_splits[trace_id], source_path)
        prepared.append((trace_id, source_path, fieldnames, source_rows, projected_rows))

    args.output_label_root.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(
        prefix=".{}.tmp.".format(args.output_label_root.name),
        dir=str(args.output_label_root.parent)))
    temporary_trace_dir = temporary_root / "traces"
    temporary_trace_dir.mkdir()
    output_entries = []
    split_class_counts = defaultdict(Counter)
    try:
        for trace_id, source_path, fieldnames, source_rows, projected_rows in prepared:
            output_path = temporary_trace_dir / source_path.name
            with output_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(projected_rows)

            # Re-open bytes from disk and prove the actual published CSV, not
            # merely the in-memory representation, is a split-only projection.
            with output_path.open(newline="", encoding="utf-8") as stream:
                written_rows = list(csv.DictReader(stream))
            split = corpus_splits[trace_id]
            assert_split_only_projection(source_rows, written_rows, split, output_path)
            counts = Counter(int(row["current_raw_label"]) for row in written_rows)
            split_class_counts[split].update(counts)
            output_entries.append({
                "trace_id": trace_id,
                "split": split,
                "source_label_csv": source_path.name,
                "source_label_sha256": sha256_file(source_path),
                "label_csv": output_path.name,
                "label_sha256": sha256_file(output_path),
                "row_count": len(written_rows),
                "class_counts": {str(class_id): counts[class_id]
                                 for class_id in range(3)},
                "transformation": "split_column_only",
            })

        manifest = {
            "schema_version": 1,
            "policy_id": split_provenance["policy_id"],
            "task": source_provenance["task"],
            "class_names": source_provenance["class_names"],
            "thresholds": source_provenance["thresholds"],
            "future_horizon_samples": source_provenance["future_horizon_samples"],
            "transformation": "split_column_only_no_label_recomputation",
            "corpus": str(args.corpus.resolve()),
            "corpus_sha256": sha256_file(args.corpus),
            "split_provenance": str(args.split_provenance.resolve()),
            "split_provenance_sha256": sha256_file(args.split_provenance),
            "source_label_root": str(args.source_label_root.resolve()),
            "source_label_provenance_sha256": sha256_file(source_provenance_path),
            "source_trace_count": len(output_entries),
            "row_count": sum(entry["row_count"] for entry in output_entries),
            "split_trace_counts": dict(sorted(Counter(corpus_splits.values()).items())),
            "split_class_counts": {
                split: {str(class_id): split_class_counts[split][class_id]
                        for class_id in range(3)}
                for split in sorted(split_class_counts)
            },
            "traces": output_entries,
        }
        (temporary_root / "provenance.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        # A directory rename publishes traces and manifest as one unit.  The
        # destination was absent at preflight and ``os.rename`` refuses a
        # concurrently-created non-empty directory instead of merging files.
        os.rename(str(temporary_root), str(args.output_label_root))
    finally:
        if temporary_root.exists():
            shutil.rmtree(str(temporary_root))

    print(json.dumps({
        "status": "published",
        "output_label_root": str(args.output_label_root),
        "trace_count": len(output_entries),
        "row_count": sum(entry["row_count"] for entry in output_entries),
        "split_trace_counts": dict(sorted(Counter(corpus_splits.values()).items())),
        "split_class_counts": manifest["split_class_counts"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
