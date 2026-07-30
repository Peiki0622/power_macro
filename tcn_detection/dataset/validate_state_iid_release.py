#!/usr/bin/env python3
"""Validate the complete state-code IID repartition release end to end."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from power_macro.tcn_detection.dataset.build_code_state_windows import normalized_code
from power_macro.tcn_detection.dataset.model_data import load_window_table
from power_macro.tcn_detection.dataset.repartition_state_iid import (
    audit_assignment,
    build_component_inventory,
    load_corpus,
    load_state_profiles,
    sha256_file,
)
from power_macro.tcn_detection.labels.reproject_state_splits import (
    assert_split_only_projection,
)


EXPECTED_SPLITS = {"train", "validation", "iid_test"}
EXPECTED_WINDOW_COUNTS = {
    8: {"train": 34560, "validation": 23664, "iid_test": 23664},
    16: {"train": 34560, "validation": 23280, "iid_test": 23280},
    32: {"train": 33840, "validation": 22512, "iid_test": 22512},
}


def stable_digest(payload):
    """Hash JSON-compatible evidence with stable ordering."""

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_csv(path):
    """Return field names and all textual rows from one auditable CSV."""

    with Path(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def parse_args():
    """Require every version boundary needed by the validation proof."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--source-corpus", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--split-root", required=True, type=Path)
    parser.add_argument("--source-label-root", required=True, type=Path)
    parser.add_argument("--label-root", required=True, type=Path)
    parser.add_argument("--windows-root", required=True, type=Path)
    parser.add_argument("--output-report", required=True, type=Path)
    return parser.parse_args()


def main():
    """Fail closed on any mismatch and publish one immutable PASS report."""

    args = parse_args()
    if args.output_report.exists():
        raise FileExistsError("refusing to overwrite validation report")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    split_provenance = json.loads((args.split_root / "provenance.json").read_text(
        encoding="utf-8"))
    label_provenance = json.loads((args.label_root / "provenance.json").read_text(
        encoding="utf-8"))
    window_manifest_path = args.windows_root / "windows_manifest_v1.json"
    window_manifest = json.loads(window_manifest_path.read_text(encoding="utf-8"))
    source_label_provenance_path = args.source_label_root / "provenance.json"
    source_label_provenance = json.loads(source_label_provenance_path.read_text(
        encoding="utf-8"))

    checks = {}
    # Re-establish every hash edge rather than trusting manifests to agree with
    # one another.  This catches both modified bytes and a valid artifact passed
    # from the wrong dataset version.
    source_corpus_hash = sha256_file(args.source_corpus)
    corpus_hash = sha256_file(args.corpus)
    checks["source_corpus_sha256"] = source_corpus_hash
    checks["corpus_sha256"] = corpus_hash
    if source_corpus_hash != config["source_hashes"]["corpus_sha256"]:
        raise ValueError("frozen source corpus digest mismatch")
    if corpus_hash != split_provenance["published_corpus_sha256"]:
        raise ValueError("new corpus digest differs from split provenance")
    if corpus_hash != label_provenance["corpus_sha256"]:
        raise ValueError("new labels bind to a different corpus")
    if sha256_file(args.label_root / "provenance.json") != window_manifest["label_provenance_sha256"]:
        raise ValueError("windows bind to a different label release")

    source_rows = load_corpus(args.source_corpus)
    corpus_rows = load_corpus(args.corpus)
    source_by_id = {row["trace_id"]: row for row in source_rows}
    corpus_by_id = {row["trace_id"]: row for row in corpus_rows}
    if len(corpus_by_id) != 240 or set(corpus_by_id) != set(source_by_id):
        raise ValueError("new corpus membership differs from the 240 frozen traces")
    for trace_id, source in source_by_id.items():
        projected = dict(corpus_by_id[trace_id])
        if projected.pop("original_split") != source["split"]:
            raise ValueError("original_split does not preserve source corpus")
        if projected.pop("split_policy_id") != config["policy_id"]:
            raise ValueError("corpus split policy ID mismatch")
        projected["split"] = source["split"]
        if projected != source:
            raise ValueError("new corpus changed a non-split source field")
    corpus_split_counts = Counter(row["split"] for row in corpus_rows)
    if set(corpus_split_counts) != EXPECTED_SPLITS:
        raise ValueError("corpus is not IID-only")
    if dict(corpus_split_counts) != config["split_trace_quotas"]:
        raise ValueError("corpus trace quotas differ from config")
    checks["corpus_split_counts"] = dict(sorted(corpus_split_counts.items()))

    # Recompute connected components from frozen inputs and rerun the same
    # acceptance audit.  This independently proves base-waveform/hard-pair
    # transitive closure and all distribution limits for the published rows.
    profiles = load_state_profiles(
        args.source_label_root / "traces", list(source_by_id))
    inventory = build_component_inventory(source_rows, profiles, config)
    assignment = {trace_id: row["split"] for trace_id, row in corpus_by_id.items()}
    split_audit = audit_assignment(inventory, source_rows, assignment, config)
    if split_audit["assignment_sha256"] != split_provenance["assignment_sha256"]:
        raise ValueError("recomputed assignment digest differs from provenance")
    checks["component_count"] = len(inventory)
    checks["assignment_sha256"] = split_audit["assignment_sha256"]
    checks["max_current_state_proportion_deviation"] = (
        split_audit["max_current_state_proportion_deviation"])
    checks["max_supported_stratum_proportion_deviation"] = (
        split_audit["max_supported_stratum_proportion_deviation"])

    source_label_entries = {
        entry["trace_id"]: entry for entry in source_label_provenance["traces"]}
    label_entries = {entry["trace_id"]: entry for entry in label_provenance["traces"]}
    if set(source_label_entries) != set(label_entries) or set(label_entries) != set(corpus_by_id):
        raise ValueError("label provenance membership mismatch")
    labels_by_trace = {}
    for trace_id in sorted(corpus_by_id):
        old_path = args.source_label_root / "traces" / source_label_entries[trace_id]["label_csv"]
        new_path = args.label_root / "traces" / label_entries[trace_id]["label_csv"]
        if sha256_file(old_path) != source_label_entries[trace_id]["label_sha256"]:
            raise ValueError("old label CSV digest mismatch")
        if sha256_file(new_path) != label_entries[trace_id]["label_sha256"]:
            raise ValueError("new label CSV digest mismatch")
        old_fields, old_rows = load_csv(old_path)
        new_fields, new_rows = load_csv(new_path)
        if old_fields != new_fields:
            raise ValueError("label CSV column order changed")
        assert_split_only_projection(
            old_rows, new_rows, corpus_by_id[trace_id]["split"], new_path)
        labels_by_trace[trace_id] = new_rows
    checks["label_trace_count"] = len(labels_by_trace)
    checks["label_row_count"] = sum(len(rows) for rows in labels_by_trace.values())

    # Validate every serialized window against the exact label rows that
    # generated it.  Expected endpoint sequences additionally prove train
    # stride/cap behavior and complete stride-one validation/IID coverage.
    window_evidence = {}
    for length, expected_split_counts in EXPECTED_WINDOW_COUNTS.items():
        path = args.windows_root / "windows_L{}.csv".format(length)
        entry = window_manifest["files"][path.name]
        if sha256_file(path) != entry["sha256"]:
            raise ValueError("window CSV digest mismatch for L{}".format(length))
        _, rows = load_csv(path)
        if len({row["window_id"] for row in rows}) != len(rows):
            raise ValueError("duplicate window ID for L{}".format(length))
        actual_split_counts = Counter(row["split"] for row in rows)
        if dict(actual_split_counts) != expected_split_counts:
            raise ValueError("unexpected split window counts for L{}".format(length))
        if entry["split_counts"] != expected_split_counts or entry["window_count"] != len(rows):
            raise ValueError("window manifest count mismatch for L{}".format(length))
        endpoints = defaultdict(list)
        for row in rows:
            trace_id = row["trace_id"]
            split = corpus_by_id[trace_id]["split"]
            end = int(row["end_index"])
            if row["split"] != split or int(row["length"]) != length:
                raise ValueError("window identity/split/length mismatch")
            if int(row["target_start_index"]) != end or int(row["target_end_index"]) != end:
                raise ValueError("window target uses a future or non-endpoint sample")
            label_rows = labels_by_trace[trace_id]
            expected_features = [normalized_code(label_rows[index])
                                 for index in range(end - length + 1, end + 1)]
            if json.loads(row["features_json"]) != expected_features:
                raise ValueError("window features differ from raw code history")
            if row["target_label"] != label_rows[end]["current_raw_label"]:
                raise ValueError("window target differs from endpoint state label")
            endpoints[trace_id].append(end)
        for trace_id, label_rows in labels_by_trace.items():
            split = corpus_by_id[trace_id]["split"]
            expected_endpoints = list(range(length - 1, len(label_rows),
                                            2 if split == "train" else 1))
            if split == "train":
                expected_endpoints = expected_endpoints[:240]
            if endpoints[trace_id] != expected_endpoints:
                raise ValueError("window stride/cap mismatch for {} L{}".format(
                    trace_id, length))
        window_evidence[str(length)] = {
            "sha256": entry["sha256"],
            "window_count": len(rows),
            "split_counts": dict(sorted(actual_split_counts.items())),
        }
    checks["windows"] = window_evidence

    # Training must stream-filter before feature parsing.  Loading only these
    # two splits and checking metadata proves no IID tensor is materialized by
    # the standard training call path.  The frozen IID CSV remains on disk.
    development = load_window_table(
        args.windows_root / "windows_L32.csv", splits={"train", "validation"})
    development_splits = {row["split"] for row in development.metadata}
    if development_splits != {"train", "validation"}:
        raise ValueError("training loader exposed IID metadata")
    if tuple(development.features.shape[1:]) != (1, 32):
        raise ValueError("training loader changed the one-channel model shape")
    checks["training_loader"] = {
        "loaded_splits": sorted(development_splits),
        "iid_features_loaded": False,
        "shape": list(development.features.shape),
    }

    report = {
        "schema_version": 1,
        "status": "PASS",
        "policy_id": config["policy_id"],
        "checks": checks,
        "report_payload_sha256": stable_digest(checks),
    }
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".{}.tmp.".format(args.output_report.name),
        dir=str(args.output_report.parent))
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
        # Atomic hard-link publication refuses a concurrently-created report;
        # unlike ``replace``, it never overwrites immutable evidence.
        os.link(str(temporary), str(args.output_report))
    finally:
        if temporary.exists():
            temporary.unlink()
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
