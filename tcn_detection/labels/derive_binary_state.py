#!/usr/bin/env python3
"""Project frozen three-state labels onto a Safe/Critical binary target.

Warning is merged into Safe for the binary experiment.  The source
``current_raw_label`` remains in every CSV as immutable evidence; this module
only appends an explicit binary target and never recalculates electrical slack.
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
    """Hash one input or output in bounded memory for provenance."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_corpus(path):
    """Load the authoritative unchanged trace-to-split mapping."""

    rows = [json.loads(line) for line in Path(path).read_text(
        encoding="utf-8").splitlines() if line.strip()]
    by_id = {row["trace_id"]: row for row in rows}
    if len(rows) != 240 or len(by_id) != 240:
        raise ValueError("binary release requires exactly 240 unique traces")
    if set(row["split"] for row in rows) != {"train", "validation", "iid_test"}:
        raise ValueError("binary release requires the IID-only split contract")
    return by_id


def project_rows(source_rows, mapping):
    """Append binary truth without altering any source cell.

    The mapping is supplied by the versioned config rather than embedded as an
    implicit convention.  ``binary_label_eligible`` mirrors the already-audited
    current-state eligibility; every row must be eligible because this task has
    no future horizon or incomplete tail.
    """

    projected = []
    for row in source_rows:
        source_label = row.get("current_raw_label")
        if source_label not in mapping:
            raise ValueError("source current-state label is outside configured mapping")
        if row.get("state_label_eligible", "").lower() != "true":
            raise ValueError("binary label source contains an ineligible row")
        binary_label = int(mapping[source_label])
        if binary_label not in (0, 1):
            raise ValueError("configured binary mapping produced a non-binary target")
        output = dict(row)
        output["binary_raw_label"] = str(binary_label)
        output["binary_class_name"] = "Safe" if binary_label == 0 else "Critical"
        output["binary_label_eligible"] = "True"
        projected.append(output)
    return projected


def verify_projection(source_rows, projected_rows, mapping, path):
    """Prove disk rows preserve source text and implement the exact mapping."""

    if len(source_rows) != 500 or len(projected_rows) != 500:
        raise ValueError("binary trace must contain exactly 500 rows: {}".format(path))
    appended = {"binary_raw_label", "binary_class_name", "binary_label_eligible"}
    for row_index, (source, projected) in enumerate(zip(source_rows, projected_rows)):
        if set(projected) != set(source) | appended:
            raise ValueError("binary label schema differs at {} row {}".format(path, row_index))
        if any(projected[field] != value for field, value in source.items()):
            raise ValueError("source label cell changed at {} row {}".format(path, row_index))
        expected = str(int(mapping[source["current_raw_label"]]))
        if projected["binary_raw_label"] != expected:
            raise ValueError("binary mapping mismatch at {} row {}".format(path, row_index))
        expected_name = "Safe" if expected == "0" else "Critical"
        if (projected["binary_class_name"] != expected_name
                or projected["binary_label_eligible"].lower() != "true"):
            raise ValueError("binary class metadata mismatch at {} row {}".format(path, row_index))


def parse_args():
    """Parse explicit version boundaries and the absent output root."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--source-label-root", required=True, type=Path)
    parser.add_argument("--output-label-root", required=True, type=Path)
    return parser.parse_args()


def main():
    """Validate all sources, build all traces, and publish one atomic release."""

    args = parse_args()
    if args.output_label_root.exists():
        raise FileExistsError("refusing to overwrite binary label release")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if (config.get("warning_policy") != "merge_into_safe"
            or config.get("class_names") != {"0": "Safe", "1": "Critical"}):
        raise ValueError("config does not describe the approved binary semantics")
    mapping = {str(key): int(value)
               for key, value in config["source_state_to_binary"].items()}
    if mapping != {"0": 0, "1": 0, "2": 1}:
        raise ValueError("binary mapping must be exactly 0/1->Safe and 2->Critical")
    if sha256_file(args.corpus) != config["source_hashes"]["corpus_sha256"]:
        raise ValueError("binary label corpus differs from frozen config")

    corpus = load_corpus(args.corpus)
    source_manifest_path = args.source_label_root / "provenance.json"
    if (sha256_file(source_manifest_path)
            != config["source_hashes"]["state_label_provenance_sha256"]):
        raise ValueError("source state-label provenance differs from frozen config")
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_entries = {entry["trace_id"]: entry for entry in source_manifest["traces"]}
    if set(source_entries) != set(corpus):
        raise ValueError("source label membership differs from binary corpus")

    # Preflight all source bytes before creating a temporary output.  This
    # prevents a late modified trace from leaving a plausible partial release.
    prepared = []
    for trace_id in sorted(corpus):
        entry = source_entries[trace_id]
        source_path = args.source_label_root / "traces" / entry["label_csv"]
        if sha256_file(source_path) != entry["label_sha256"]:
            raise ValueError("source label digest mismatch: {}".format(trace_id))
        with source_path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
            fields = list(reader.fieldnames or [])
        if (len(rows) != 500 or {row["trace_id"] for row in rows} != {trace_id}
                or {row["split"] for row in rows} != {corpus[trace_id]["split"]}):
            raise ValueError("source label identity/split contract failed: {}".format(trace_id))
        prepared.append((trace_id, source_path, fields, rows, project_rows(rows, mapping)))

    args.output_label_root.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(
        prefix=".{}.tmp.".format(args.output_label_root.name),
        dir=str(args.output_label_root.parent)))
    trace_dir = temporary_root / "traces"
    trace_dir.mkdir()
    entries = []
    split_counts = defaultdict(Counter)
    try:
        for trace_id, source_path, fields, source_rows, projected_rows in prepared:
            output_path = trace_dir / source_path.name
            output_fields = fields + ["binary_raw_label", "binary_class_name",
                                      "binary_label_eligible"]
            with output_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=output_fields)
                writer.writeheader()
                writer.writerows(projected_rows)
            with output_path.open(newline="", encoding="utf-8") as stream:
                written_rows = list(csv.DictReader(stream))
            verify_projection(source_rows, written_rows, mapping, output_path)
            counts = Counter(row["binary_raw_label"] for row in written_rows)
            split = corpus[trace_id]["split"]
            split_counts[split].update(counts)
            entries.append({
                "trace_id": trace_id,
                "split": split,
                "source_label_csv": source_path.name,
                "source_label_sha256": sha256_file(source_path),
                "binary_label_csv": output_path.name,
                "binary_label_sha256": sha256_file(output_path),
                "row_count": len(written_rows),
                "class_counts": {str(class_id): counts[str(class_id)]
                                 for class_id in (0, 1)},
            })

        manifest = {
            "schema_version": 1,
            "policy_id": config["policy_id"],
            "task": config["task"],
            "class_names": config["class_names"],
            "source_state_to_binary": mapping,
            "warning_policy": config["warning_policy"],
            "transformation": "append_binary_target_without_recomputing_truth",
            "config": str(args.config.resolve()),
            "config_sha256": sha256_file(args.config),
            "corpus": str(args.corpus.resolve()),
            "corpus_sha256": sha256_file(args.corpus),
            "source_label_root": str(args.source_label_root.resolve()),
            "source_label_provenance_sha256": sha256_file(source_manifest_path),
            "source_trace_count": len(entries),
            "row_count": sum(entry["row_count"] for entry in entries),
            "split_class_counts": {
                split: {str(class_id): split_counts[split][str(class_id)]
                        for class_id in (0, 1)}
                for split in sorted(split_counts)
            },
            "traces": entries,
        }
        (temporary_root / "provenance.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.rename(str(temporary_root), str(args.output_label_root))
    finally:
        if temporary_root.exists():
            shutil.rmtree(str(temporary_root))

    print(json.dumps({"status": "published",
                      "trace_count": len(entries),
                      "row_count": manifest["row_count"],
                      "split_class_counts": manifest["split_class_counts"]},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
