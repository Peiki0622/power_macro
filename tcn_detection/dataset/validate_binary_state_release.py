#!/usr/bin/env python3
"""Validate binary labels and code windows against frozen three-state sources."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path

from power_macro.tcn_detection.dataset.model_data import load_window_table


EXPECTED_WINDOWS = {8: 81888, 16: 81120, 32: 78864}


def sha256_file(path):
    """Return a bounded-memory digest for validation evidence."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path):
    """Read auditable textual CSV rows without numeric normalization."""

    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def parse_args():
    """Parse every source and derived version boundary."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--source-label-root", required=True, type=Path)
    parser.add_argument("--binary-label-root", required=True, type=Path)
    parser.add_argument("--source-windows-root", required=True, type=Path)
    parser.add_argument("--binary-windows-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main():
    """Run all cross-version checks and atomically publish a PASS report."""

    args = parse_args()
    if args.output.exists():
        raise FileExistsError("refusing to overwrite binary validation report")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    binary_labels = json.loads((args.binary_label_root / "provenance.json").read_text(
        encoding="utf-8"))
    source_labels = json.loads((args.source_label_root / "provenance.json").read_text(
        encoding="utf-8"))
    windows_manifest = json.loads((args.binary_windows_root / "windows_manifest_v1.json").read_text(
        encoding="utf-8"))
    if (binary_labels["policy_id"] != config["policy_id"]
            or windows_manifest["policy_id"] != config["policy_id"]):
        raise ValueError("binary artifacts have mismatched policy IDs")
    if (sha256_file(args.source_label_root / "provenance.json")
            != config["source_hashes"]["state_label_provenance_sha256"]):
        raise ValueError("source label manifest differs from frozen config")

    source_entries = {entry["trace_id"]: entry for entry in source_labels["traces"]}
    binary_entries = {entry["trace_id"]: entry for entry in binary_labels["traces"]}
    if set(source_entries) != set(binary_entries) or len(binary_entries) != 240:
        raise ValueError("binary label membership differs from source")
    label_rows_checked = 0
    for trace_id in sorted(source_entries):
        source_path = args.source_label_root / "traces" / source_entries[trace_id]["label_csv"]
        binary_path = args.binary_label_root / "traces" / binary_entries[trace_id]["binary_label_csv"]
        if sha256_file(binary_path) != binary_entries[trace_id]["binary_label_sha256"]:
            raise ValueError("binary label digest mismatch")
        source_rows, projected_rows = read_csv(source_path), read_csv(binary_path)
        if len(source_rows) != len(projected_rows) or len(source_rows) != 500:
            raise ValueError("binary label row count mismatch")
        for source, projected in zip(source_rows, projected_rows):
            if any(projected[field] != value for field, value in source.items()):
                raise ValueError("binary label changed a frozen source cell")
            expected = "1" if source["current_raw_label"] == "2" else "0"
            if projected["binary_raw_label"] != expected:
                raise ValueError("binary label mapping mismatch")
            label_rows_checked += 1
    if label_rows_checked != 120000:
        raise ValueError("binary validation did not cover all label rows")

    window_evidence = {}
    for length in config["window_lengths"]:
        source_path = args.source_windows_root / "windows_L{}.csv".format(length)
        binary_path = args.binary_windows_root / "windows_L{}.csv".format(length)
        entry = windows_manifest["files"][binary_path.name]
        if (sha256_file(source_path) != entry["source_sha256"]
                or sha256_file(binary_path) != entry["sha256"]):
            raise ValueError("binary window source/output digest mismatch")
        source_rows, binary_rows = read_csv(source_path), read_csv(binary_path)
        if len(source_rows) != len(binary_rows) or len(binary_rows) != EXPECTED_WINDOWS[length]:
            raise ValueError("binary window row count mismatch")
        counts = Counter()
        for source, binary in zip(source_rows, binary_rows):
            if any(binary[field] != value for field, value in source.items()
                   if field != "target_label"):
                raise ValueError("binary window changed causal feature/metadata text")
            expected = "1" if source["target_label"] == "2" else "0"
            if (binary["target_label"] != expected
                    or binary["source_state_label"] != source["target_label"]):
                raise ValueError("binary window target/source label mismatch")
            counts[(binary["split"], binary["target_label"])] += 1
        window_evidence[str(length)] = {
            "sha256": entry["sha256"], "window_count": len(binary_rows),
            "split_class_counts": entry["split_class_counts"],
            "source_features_text_identical": True,
        }

    # Exercise the actual training call path.  The returned shape and metadata
    # prove one-channel binary development tensors load while IID remains on
    # disk and outside this process's parsed feature arrays.
    development = load_window_table(
        args.binary_windows_root / "windows_L32.csv",
        splits={"train", "validation"})
    if ({row["split"] for row in development.metadata} != {"train", "validation"}
            or set(np_unique(development.labels)) != {0, 1}
            or tuple(development.features.shape[1:]) != (1, 32)):
        raise ValueError("binary training loader contract failed")
    report = {
        "schema_version": 1, "status": "PASS",
        "policy_id": config["policy_id"],
        "label_trace_count": 240, "label_row_count": label_rows_checked,
        "windows": window_evidence,
        "training_loader": {"loaded_splits": ["train", "validation"],
                            "iid_features_loaded": False,
                            "shape": list(development.features.shape)},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".{}.tmp.".format(args.output.name), dir=str(args.output.parent))
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
        os.link(str(temporary), str(args.output))
    finally:
        if temporary.exists():
            temporary.unlink()
    print(json.dumps(report, indent=2, sort_keys=True))


def np_unique(values):
    """Return integer unique values without adding NumPy to validation imports."""

    return sorted({int(value) for value in values})


if __name__ == "__main__":
    main()
