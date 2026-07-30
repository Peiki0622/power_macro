#!/usr/bin/env python3
"""Build one-channel causal code histories for current-state monitoring.

Each chronological sample contributes exactly one model feature: the corrected
integer ``sensor_code`` normalized by the fixed sensor range.  The builder
rejects data where the raw thermometer word differs from the corrected word,
or where either bubble counter is nonzero.  That fail-closed check is what
makes scalar code information-equivalent to the raw code word for this
version; a future dataset that needs correction must receive a new feature
contract rather than silently entering this release.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path


FEATURE_CHANNELS = ("normalized_sensor_code",)
BASELINE_CODE = 15
MAX_CODE = 32
CODE_SCALE = MAX_CODE - BASELINE_CODE


def sha256_file(path):
    """Hash a provenance input or generated window using bounded memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_trace(rows, source_name="trace"):
    """Validate the assumptions that permit a scalar-only representation.

    Besides raw/corrected equality, this checks stable identity, chronological
    sample indices, legal integer code bounds, and complete current labels.
    These checks run before any output directory is created, so malformed
    input cannot leave a partially published window release.
    """

    if len(rows) != 500:
        raise ValueError("{} must contain exactly 500 captures".format(source_name))
    trace_ids = {row["trace_id"] for row in rows}
    splits = {row["split"] for row in rows}
    if len(trace_ids) != 1 or len(splits) != 1:
        raise ValueError("{} changes trace_id or split within a trace".format(source_name))
    if next(iter(splits)) not in {"train", "validation", "iid_test"}:
        raise ValueError("{} contains a split outside the IID-only contract".format(
            source_name))
    for expected_index, row in enumerate(rows):
        if int(row["sample_index"]) != expected_index:
            raise ValueError("{} has non-contiguous sample indices".format(source_name))
        if row["raw_code"] != row["corrected_code"]:
            raise ValueError("{} requires raw-code correction at sample {}".format(
                source_name, expected_index))
        if int(row["raw_bubble_count"]) != 0 or int(row["bubble_count"]) != 0:
            raise ValueError("{} contains a thermometer-code bubble at sample {}".format(
                source_name, expected_index))
        code = int(row["sensor_code"])
        if not BASELINE_CODE <= code <= MAX_CODE:
            raise ValueError("{} has sensor_code outside [{}, {}]".format(
                source_name, BASELINE_CODE, MAX_CODE))
        if row.get("state_label_eligible", "").lower() != "true":
            raise ValueError("{} has an ineligible current-state row".format(source_name))
        if row.get("current_raw_label") not in {"0", "1", "2"}:
            raise ValueError("{} has an invalid current-state target".format(source_name))


def normalized_code(row):
    """Return ``(sensor_code - 15) / 17`` as the sole feature sample."""

    return [(int(row["sensor_code"]) - BASELINE_CODE) / float(CODE_SCALE)]


def build_trace_windows(rows, length, max_train_windows=240):
    """Build current-target histories without crossing a trace boundary.

    A window ending at ``e`` sees only ``e-L+1..e`` and predicts the raw state
    at that same endpoint.  Train uses stride two and a per-trace cap to limit
    temporal duplication; every evaluation split retains stride-one order so
    later event and filtering metrics have no artificial gaps.
    """

    validate_trace(rows)
    split = rows[0]["split"]
    stride = 2 if split == "train" else 1
    windows = []
    for end in range(int(length) - 1, len(rows), stride):
        features = [normalized_code(rows[index])
                    for index in range(end - int(length) + 1, end + 1)]
        windows.append({
            "window_id": "{}_state_code_L{}_e{:03d}".format(
                rows[end]["trace_id"], length, end),
            "trace_id": rows[end]["trace_id"],
            "base_waveform_id": rows[end]["base_waveform_id"],
            "waveform_family_id": rows[end]["waveform_family_id"],
            "hard_pair_id": rows[end].get("hard_pair_id", ""),
            "split": split,
            "end_index": end,
            # All three indices are identical because the task monitors the
            # present state.  No future sample contributes to truth.
            "target_start_index": end,
            "target_end_index": end,
            "length": int(length),
            "feature_channels": 1,
            "baseline_code": BASELINE_CODE,
            "code_scale": CODE_SCALE,
            "target_label": rows[end]["current_raw_label"],
            "features_json": json.dumps(features, separators=(",", ":")),
        })
    return windows[:int(max_train_windows)] if split == "train" else windows


def main():
    """Preflight all labels, then atomically publish L8/L16/L32 indexes."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-dir", required=True, type=Path)
    parser.add_argument("--label-provenance", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-train-windows-per-trace", type=int, default=240)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite code-window release: {}".format(
            args.output_dir))

    label_manifest = json.loads(args.label_provenance.read_text(encoding="utf-8"))
    expected = {entry["trace_id"]: entry for entry in label_manifest["traces"]}
    prepared = []
    for source in sorted(args.label_dir.glob("*.csv")):
        with source.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        validate_trace(rows, str(source))
        trace_id = rows[0]["trace_id"]
        if trace_id not in expected or sha256_file(source) != expected[trace_id]["label_sha256"]:
            raise ValueError("label provenance mismatch: {}".format(trace_id))
        prepared.append(rows)
    if len(prepared) != label_manifest["source_trace_count"] or len(prepared) != len(expected):
        raise ValueError("label trace count differs from provenance")

    # Build the complete version under a private sibling name.  Publishing the
    # directory only after all three CSVs have been written and revalidated
    # prevents a failed L32 build from leaving apparently usable L8/L16 files.
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary_output_dir = Path(tempfile.mkdtemp(
        prefix=".{}.tmp.".format(args.output_dir.name),
        dir=str(args.output_dir.parent)))
    manifest = {
        "schema_version": 1,
        "policy_id": label_manifest.get("policy_id"),
        "task": "same_sample_current_state_monitoring",
        "label_dir": str(args.label_dir.resolve()),
        "label_provenance_sha256": sha256_file(args.label_provenance),
        "feature_channels": list(FEATURE_CHANNELS),
        "feature_shape": "[window_length,1]",
        "normalization": "(sensor_code - 15) / 17",
        "baseline_code": BASELINE_CODE,
        "max_code": MAX_CODE,
        "max_train_windows_per_trace": args.max_train_windows_per_trace,
        "files": {},
    }
    fields = ["window_id", "trace_id", "base_waveform_id", "waveform_family_id",
              "hard_pair_id", "split", "end_index", "target_start_index",
              "target_end_index", "length", "feature_channels", "baseline_code",
              "code_scale", "target_label", "features_json"]
    try:
        for length in (8, 16, 32):
            windows = []
            for rows in prepared:
                windows.extend(build_trace_windows(
                    rows, length, args.max_train_windows_per_trace))
            path = temporary_output_dir / "windows_L{}.csv".format(length)
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(windows)

            # Read the serialized CSV back before hashing it.  These checks bind
            # the published counts and shape contract to disk bytes and catch a
            # malformed ``features_json`` or accidental OOD row immediately.
            with path.open(newline="", encoding="utf-8") as stream:
                written = list(csv.DictReader(stream))
            if len(written) != len(windows):
                raise ValueError("serialized window count changed for L{}".format(length))
            for row in written:
                features = json.loads(row["features_json"])
                if (len(features) != length
                        or any(not isinstance(sample, list) or len(sample) != 1
                               for sample in features)):
                    raise ValueError("serialized feature shape differs from [L,1]")
                if row["split"] not in {"train", "validation", "iid_test"}:
                    raise ValueError("serialized windows contain a forbidden split")
                if not (int(row["target_start_index"]) == int(row["end_index"])
                        == int(row["target_end_index"])):
                    raise ValueError("window target is not the same-sample endpoint")
            split_counts = Counter(row["split"] for row in written)
            class_counts = Counter(row["target_label"] for row in written)
            manifest["files"][path.name] = {
                "sha256": sha256_file(path),
                "window_count": len(written),
                "split_counts": dict(sorted(split_counts.items())),
                "class_counts": {label: class_counts[label] for label in ("0", "1", "2")},
            }
        (temporary_output_dir / "windows_manifest_v1.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.rename(str(temporary_output_dir), str(args.output_dir))
    finally:
        if temporary_output_dir.exists():
            shutil.rmtree(str(temporary_output_dir))


if __name__ == "__main__":
    main()
