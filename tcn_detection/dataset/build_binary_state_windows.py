#!/usr/bin/env python3
"""Project frozen code-only windows onto the Safe/Critical binary target.

The source window rows already satisfy the audited causal feature contract.
This command deliberately preserves their metadata and ``features_json`` text,
maps only the endpoint target, and verifies that mapping against the separately
published binary label CSV at the same trace/end index.
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


EXPECTED_COUNTS = {
    8: {"train": 34560, "validation": 23664, "iid_test": 23664},
    16: {"train": 34560, "validation": 23280, "iid_test": 23280},
    32: {"train": 33840, "validation": 22512, "iid_test": 22512},
}


def sha256_file(path):
    """Hash large window and provenance files in bounded memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_binary_targets(label_root, label_manifest):
    """Load authoritative binary endpoint targets keyed by trace and index."""

    targets = {}
    for entry in label_manifest["traces"]:
        path = Path(label_root) / "traces" / entry["binary_label_csv"]
        if sha256_file(path) != entry["binary_label_sha256"]:
            raise ValueError("binary label digest mismatch: {}".format(entry["trace_id"]))
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != 500:
            raise ValueError("binary label trace must contain 500 rows")
        for expected_index, row in enumerate(rows):
            if (int(row["sample_index"]) != expected_index
                    or row["binary_raw_label"] not in {"0", "1"}):
                raise ValueError("binary label index/target contract failed")
            targets[(row["trace_id"], expected_index)] = row["binary_raw_label"]
    if len(targets) != 120000:
        raise ValueError("binary target table must cover all 120,000 samples")
    return targets


def parse_args():
    """Parse frozen source and absent destination paths explicitly."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--source-windows-root", required=True, type=Path)
    parser.add_argument("--binary-label-root", required=True, type=Path)
    parser.add_argument("--output-windows-root", required=True, type=Path)
    return parser.parse_args()


def main():
    """Validate inputs, project all windows, and atomically publish the release."""

    args = parse_args()
    if args.output_windows_root.exists():
        raise FileExistsError("refusing to overwrite binary window release")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    mapping = {str(key): str(value)
               for key, value in config["source_state_to_binary"].items()}
    if mapping != {"0": "0", "1": "0", "2": "1"}:
        raise ValueError("window builder requires the approved Warning-to-Safe mapping")
    label_manifest_path = args.binary_label_root / "provenance.json"
    label_manifest = json.loads(label_manifest_path.read_text(encoding="utf-8"))
    if (label_manifest.get("policy_id") != config["policy_id"]
            or label_manifest.get("warning_policy") != "merge_into_safe"):
        raise ValueError("binary labels belong to a different policy")
    targets = load_binary_targets(args.binary_label_root, label_manifest)

    # Bind each source window file to the Step-1 frozen hash.  Projection may
    # not proceed from a later regenerated or manually edited source index.
    for length in config["window_lengths"]:
        source = args.source_windows_root / "windows_L{}.csv".format(length)
        expected = config["source_hashes"]["state_windows_L{}_sha256".format(length)]
        if sha256_file(source) != expected:
            raise ValueError("source L{} windows differ from frozen config".format(length))

    args.output_windows_root.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(
        prefix=".{}.tmp.".format(args.output_windows_root.name),
        dir=str(args.output_windows_root.parent)))
    manifest = {
        "schema_version": 1,
        "policy_id": config["policy_id"],
        "task": config["task"],
        "class_names": config["class_names"],
        "warning_policy": config["warning_policy"],
        "feature_channels": ["normalized_sensor_code"],
        "feature_shape": "[window_length,1]",
        "normalization": "(sensor_code - 15) / 17",
        "source_windows_root": str(args.source_windows_root.resolve()),
        "binary_label_provenance_sha256": sha256_file(label_manifest_path),
        "files": {},
    }
    try:
        for length in config["window_lengths"]:
            source_path = args.source_windows_root / "windows_L{}.csv".format(length)
            with source_path.open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                source_rows = list(reader)
                source_fields = list(reader.fieldnames or [])
            output_fields = source_fields + ["source_state_label"]
            output_rows = []
            for source in source_rows:
                source_label = source["target_label"]
                if source_label not in mapping:
                    raise ValueError("source window has invalid three-state target")
                end = int(source["end_index"])
                mapped = mapping[source_label]
                if targets.get((source["trace_id"], end)) != mapped:
                    raise ValueError("window target disagrees with binary label endpoint")
                output = dict(source)
                output["target_label"] = mapped
                output["source_state_label"] = source_label
                output_rows.append(output)

            output_path = temporary_root / source_path.name
            with output_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=output_fields)
                writer.writeheader()
                writer.writerows(output_rows)

            # Re-open serialized rows and prove every non-target source field,
            # especially ``features_json``, is text-identical.  Target mapping
            # and source-label retention are checked independently.
            with output_path.open(newline="", encoding="utf-8") as stream:
                written_rows = list(csv.DictReader(stream))
            if len(written_rows) != len(source_rows):
                raise ValueError("binary window serialization changed row count")
            split_counts = Counter()
            split_class_counts = defaultdict(Counter)
            for source, written in zip(source_rows, written_rows):
                if any(written[field] != value for field, value in source.items()
                       if field != "target_label"):
                    raise ValueError("binary projection changed a non-target window field")
                if (written["source_state_label"] != source["target_label"]
                        or written["target_label"] != mapping[source["target_label"]]):
                    raise ValueError("binary window target mapping changed on disk")
                features = json.loads(written["features_json"])
                if (len(features) != int(length)
                        or any(not isinstance(sample, list) or len(sample) != 1
                               for sample in features)):
                    raise ValueError("binary window feature shape differs from [L,1]")
                split_counts[written["split"]] += 1
                split_class_counts[written["split"]][written["target_label"]] += 1
            if dict(split_counts) != EXPECTED_COUNTS[int(length)]:
                raise ValueError("binary L{} split counts differ from plan".format(length))
            manifest["files"][output_path.name] = {
                "sha256": sha256_file(output_path),
                "source_sha256": sha256_file(source_path),
                "window_count": len(written_rows),
                "split_counts": dict(sorted(split_counts.items())),
                "split_class_counts": {
                    split: {str(class_id): split_class_counts[split][str(class_id)]
                            for class_id in (0, 1)}
                    for split in sorted(split_class_counts)
                },
                "features_text_identical_to_source": True,
            }
        (temporary_root / "windows_manifest_v1.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.rename(str(temporary_root), str(args.output_windows_root))
    finally:
        if temporary_root.exists():
            shutil.rmtree(str(temporary_root))

    print(json.dumps({"status": "published", "files": manifest["files"]},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
