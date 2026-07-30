#!/usr/bin/env python3
"""Append label-only time-to-violation buckets to immutable v1 windows."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def sha256_file(path):
    """Hash one source or derived file without loading it into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def time_bucket_from_offset(value):
    """Map a label offset to none/near/middle/far auxiliary classes.

    Empty offsets mean no newly predicted violation within the eight-sample
    label horizon and map to class 0.  Non-empty values must be inside that
    horizon; failing on any other value prevents a label-generation mismatch
    from being silently collapsed into the ``none`` class.
    """

    if value is None or str(value).strip() == "":
        return 0
    offset = int(value)
    if 1 <= offset <= 2:
        return 1
    if 3 <= offset <= 4:
        return 2
    if 5 <= offset <= 8:
        return 3
    raise ValueError("time-to-violation offset is outside the 1..8 horizon: {}".format(offset))


def read_label_offsets(label_dir):
    """Index only the derived label offset needed by the auxiliary target."""

    offsets = {}
    for path in sorted(Path(label_dir).glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                key = (row["trace_id"], int(row["sample_index"]))
                if key in offsets:
                    raise ValueError("duplicate trace/sample label key: {}".format(key))
                offsets[key] = row["time_to_violation_samples"]
    if not offsets:
        raise ValueError("label directory contains no trace rows")
    return offsets


def derive_file(source, destination, offsets):
    """Copy every v1 field verbatim and append one integer target column."""

    counts = defaultdict(lambda: defaultdict(int))
    with Path(source).open(newline="", encoding="utf-8") as input_stream:
        reader = csv.DictReader(input_stream)
        if not reader.fieldnames or "target_time_bucket" in reader.fieldnames:
            raise ValueError("source window schema is missing or already augmented")
        fields = list(reader.fieldnames) + ["target_time_bucket"]
        with Path(destination).open("w", newline="", encoding="utf-8") as output_stream:
            writer = csv.DictWriter(output_stream, fieldnames=fields)
            writer.writeheader()
            row_count = 0
            for row in reader:
                key = (row["trace_id"], int(row["end_index"]))
                if key not in offsets:
                    raise ValueError("window endpoint is absent from label truth: {}".format(key))
                bucket = time_bucket_from_offset(offsets[key])
                writer.writerow({**row, "target_time_bucket": bucket})
                counts[row["split"]][str(bucket)] += 1
                row_count += 1
    return row_count, {split: dict(sorted(values.items())) for split, values in sorted(counts.items())}


def main():
    """Create a non-overwriting v2 directory for L8/L16/L32 indexes."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows-v1-dir", required=True, type=Path)
    parser.add_argument("--label-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite time-bucket window directory: {}".format(args.output_dir))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    offsets = read_label_offsets(args.label_dir)
    manifest = {"schema_version": 2, "derivation": "append_label_only_time_bucket",
                "feature_channels_changed": False, "files": {}}
    for length in (8, 16, 32):
        source = args.windows_v1_dir / "windows_L{}.csv".format(length)
        destination = args.output_dir / source.name
        row_count, bucket_counts = derive_file(source, destination, offsets)
        manifest["files"][source.name] = {
            "source": str(source.resolve()), "source_sha256": sha256_file(source),
            "derived_sha256": sha256_file(destination), "window_count": row_count,
            "bucket_counts_by_split": bucket_counts,
        }
    manifest_path = args.output_dir / "windows_manifest_v2.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
