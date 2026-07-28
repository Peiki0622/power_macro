#!/usr/bin/env python3
"""Build causal five-channel windows from verified, labelled trace CSVs.

The index stores feature values in a compact CSV instead of copying HSPICE
waveforms.  A window ending at sample ``e`` contains only samples
``e-L+1..e``; its target is the already-computed label over ``e+1..e+H``.
This explicit indexing preserves the causal deployment contract and makes
future-data leakage independently auditable.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from pathlib import Path


def feature_row(rows, index, baseline, stages):
    """Return the five online-observable scalar channels for one sample.

    Args:
        rows: One chronological compact trace.  It must contain only real DFF
            captures and must not contain a sample from another trace.
        index: The capture index represented by the output feature vector.
        baseline: The fixed calibrated no-droop code for this sensor revision.
        stages: Number of Vernier thermometer stages; this fixes normalization.

    Returns:
        ``[x0, x1, x2, x3, x4]`` as specified in plan section 4.  In
        particular, no measured VDD, configured PWL value, family name, or
        future capture is included, because those are unavailable to hardware
        at online inference time.
    """

    current = int(rows[index]["sensor_code"])
    previous = int(rows[index - 1]["sensor_code"]) if index else baseline
    return [(current - baseline) / float(stages - baseline), (current - previous) / float(stages),
            1.0 if current == stages else 0.0, float(rows[index]["bubble_count"]) / float(stages),
            1.0 if rows[index]["code_valid"].lower() == "true" else 0.0]


def sha256_file(path):
    """Hash source label/config artifacts for the window manifest."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_trace_windows(rows, length, baseline, stages, max_train_windows):
    """Build one trace's causal windows without crossing its capture boundary.

    A label at endpoint ``e`` already encodes risk over ``e+1..e+8``.  The
    explicit target bounds below therefore make the temporal contract visible
    to later training and leakage tests instead of hiding it in label code.
    """

    split = rows[0]["split"]
    if any(row["split"] != split for row in rows):
        raise ValueError("labelled trace has inconsistent split")
    stride = 2 if split == "train" else 1
    windows = []
    for end in range(length - 1, len(rows), stride):
        if rows[end].get("label_eligible", "False").lower() != "true":
            continue
        windows.append({
            "window_id": "{}_L{}_e{:03d}".format(rows[end]["trace_id"], length, end),
            "trace_id": rows[end]["trace_id"], "base_waveform_id": rows[end]["base_waveform_id"],
            "waveform_family_id": rows[end]["waveform_family_id"], "hard_pair_id": rows[end].get("hard_pair_id", ""),
            "split": split, "end_index": end, "target_start_index": end + 1, "target_end_index": end + 8,
            "length": length, "baseline_code": baseline, "target_label": rows[end]["hysteresis_label"],
            "features_json": json.dumps([feature_row(rows, index, baseline, stages) for index in range(end - length + 1, end + 1)],
                                        separators=(",", ":")),
        })
    # A long event must not create an unbounded number of train samples from
    # one electrical trace.  Evaluation windows remain complete and ordered.
    return windows[:max_train_windows] if split == "train" else windows


def main():
    """Emit L=8/16/32 causal window indexes from labelled derived traces.

    Train windows use the plan-approved stride of two to limit correlation
    and the influence of a single long trace.  Validation and both test
    partitions use stride one so chronological event metrics see every
    possible decision instant without artificial downsampling.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--dataset-config", required=True, type=Path)
    parser.add_argument("--max-train-windows-per-trace", type=int, default=240)
    args = parser.parse_args()
    # Window indexes are reproducible, versioned artifacts.  Refuse every
    # pre-existing target directory so a failed old run cannot be blended with
    # a new configuration or a changed label layer.
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite derived window directory: {}".format(args.output_dir))
    dataset_cfg = json.loads(args.dataset_config.read_text(encoding="utf-8"))
    baseline = int(dataset_cfg["baseline_code"])
    stages = int(dataset_cfg["m_stages"])
    args.output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": 1, "label_dir": str(args.label_dir.resolve()), "dataset_config_sha256": sha256_file(args.dataset_config),
                "baseline_code": baseline, "m_stages": stages, "max_train_windows_per_trace": args.max_train_windows_per_trace,
                "files": {}}
    for length in (8, 16, 32):
        rows_out = []
        for source in sorted(args.label_dir.glob("*.csv")):
            with source.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            if len(rows) != 500:
                raise ValueError("labelled trace must contain 500 rows: {}".format(source))
            rows_out.extend(build_trace_windows(rows, length, baseline, stages, args.max_train_windows_per_trace))
        path = args.output_dir / ("windows_L{}.csv".format(length))
        fields = ["window_id", "trace_id", "base_waveform_id", "waveform_family_id", "hard_pair_id", "split", "end_index",
                  "target_start_index", "target_end_index", "length", "baseline_code", "target_label", "features_json"]
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows_out)
        split_counts = {}
        for row in rows_out:
            split_counts[row["split"]] = split_counts.get(row["split"], 0) + 1
        manifest["files"][path.name] = {"sha256": sha256_file(path), "window_count": len(rows_out), "split_counts": split_counts}
    (args.output_dir / "windows_manifest_v1.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
