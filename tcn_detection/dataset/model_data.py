#!/usr/bin/env python3
"""Load immutable causal-window indexes into model-ready arrays.

The electrical dataset intentionally remains in CSV form for auditability.
This module is the narrow boundary between that evidence layer and numerical
training: it parses only the five pre-approved online features already stored
in ``features_json`` and keeps trace metadata separate for chronological
evaluation.  It never exposes measured VDD, configured droop, or waveform
family as an input tensor.
"""

from __future__ import print_function

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


ONLINE_CHANNELS = 5
CLASS_IDS = (0, 1, 2)


@dataclass(frozen=True)
class WindowTable:
    """One homogeneous L-length window table plus immutable metadata columns.

    Attributes:
        features: Float32 array shaped ``[window_count, 5, L]``.  Channel
            order is fixed by the dataset contract: normalized code, code
            delta, saturation bit, bubble ratio, and code-valid bit.
        labels: Integer class targets shaped ``[window_count]``.
        metadata: Parallel list of CSV dictionaries.  This remains outside the
            tensor specifically so event scoring can join trace ID, endpoint,
            split, family, and hard-pair information without letting a model
            consume any of those unavailable online attributes.
        length: Causal history length L read from the source index.
    """

    features: np.ndarray
    labels: np.ndarray
    metadata: tuple
    length: int


def sha256_file(path):
    """Hash a source index for run manifests without loading it into memory."""

    import hashlib

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_window_table(path):
    """Parse and validate one ``windows_L*.csv`` file.

    Args:
        path: Immutable causal window CSV emitted by ``build_windows.py``.

    Returns:
        :class:`WindowTable` with a channel-first Float32 tensor layout.

    Raises:
        ValueError: On malformed JSON, inconsistent L, non-five-channel input,
            or an invalid target label.  Failing closed is important because a
            malformed field could otherwise quietly bypass the causal dataset
            contract during model training.
    """

    path = Path(path)
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("window file is empty: {}".format(path))
    length = int(rows[0]["length"])
    feature_rows = []
    labels = []
    for row in rows:
        if int(row["length"]) != length or row["target_label"] not in {"0", "1", "2"}:
            raise ValueError("inconsistent window metadata in {}".format(path))
        try:
            window = json.loads(row["features_json"])
        except json.JSONDecodeError as error:
            raise ValueError("invalid features_json in {}: {}".format(row["window_id"], error))
        if len(window) != length or any(len(sample) != ONLINE_CHANNELS for sample in window):
            raise ValueError("window does not have Lx5 online features: {}".format(row["window_id"]))
        # CSV stores chronological samples as [L, 5].  Models use the standard
        # Conv1d [channels, sequence] convention, hence the explicit transpose.
        feature_rows.append(np.asarray(window, dtype=np.float32).T)
        labels.append(int(row["target_label"]))
    return WindowTable(np.stack(feature_rows), np.asarray(labels, dtype=np.int64), tuple(rows), length)


def filter_split(table, split):
    """Select a named immutable split without reshuffling or trace mixing."""

    selected = [index for index, row in enumerate(table.metadata) if row["split"] == split]
    if not selected:
        raise ValueError("split {} has no windows".format(split))
    indices = np.asarray(selected, dtype=np.int64)
    return WindowTable(table.features[indices], table.labels[indices], tuple(table.metadata[index] for index in indices), table.length)


def fit_normalizer(train_table):
    """Fit per-channel mean/std from train windows only.

    Zero variance is mapped to unit scale, preserving binary channels while
    avoiding a divide-by-zero.  The returned JSON-serializable mapping is the
    only normalization state later applied to validation and test data.
    """

    mean = train_table.features.mean(axis=(0, 2), dtype=np.float64)
    std = train_table.features.std(axis=(0, 2), dtype=np.float64)
    std[std < 1.0e-12] = 1.0
    return {"mean": mean.tolist(), "std": std.tolist(), "source_split": "train", "window_length": train_table.length}


def apply_normalizer(table, normalizer):
    """Return a normalized copy of one table using a frozen train-only state."""

    mean = np.asarray(normalizer["mean"], dtype=np.float32).reshape(1, ONLINE_CHANNELS, 1)
    std = np.asarray(normalizer["std"], dtype=np.float32).reshape(1, ONLINE_CHANNELS, 1)
    if int(normalizer["window_length"]) != table.length:
        raise ValueError("normalizer length does not match window table")
    return WindowTable((table.features - mean) / std, table.labels.copy(), table.metadata, table.length)


def select_class_indices(labels, class_id):
    """Return deterministic integer indices for one target class."""

    return np.flatnonzero(labels == int(class_id)).astype(np.int64)


def load_safe_stride_one_windows(label_dir, split, length=16, baseline_code=15, stages=32):
    """Build the CAE's L=16/stride=1 Safe-only windows in memory.

    The supervised classification CSV intentionally uses train stride two to
    limit one trace's influence.  Plan step 11 separately calls for a
    literature-style CAE trained on normal windows with stride one.  This
    function realizes that narrow exception without materializing another
    large, redundant window file and without adding non-online inputs.
    """

    label_dir = Path(label_dir)
    features = []
    labels = []
    metadata = []
    for source in sorted(label_dir.glob("*.csv")):
        with source.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != 500 or rows[0]["split"] != split:
            continue
        for end in range(int(length) - 1, len(rows) - 8):
            if rows[end]["label_eligible"].lower() != "true" or rows[end]["hysteresis_label"] != "0":
                continue
            samples = []
            for index in range(end - int(length) + 1, end + 1):
                current = int(rows[index]["sensor_code"])
                previous = int(rows[index - 1]["sensor_code"]) if index else int(baseline_code)
                samples.append([(current - int(baseline_code)) / float(int(stages) - int(baseline_code)),
                                (current - previous) / float(int(stages)),
                                1.0 if current == int(stages) else 0.0,
                                float(rows[index]["bubble_count"]) / float(int(stages)),
                                1.0 if rows[index]["code_valid"].lower() == "true" else 0.0])
            # The expression above is intentionally kept equivalent to the
            # dataset builder.  Converting chronological [L,5] to [5,L] below
            # makes the CAE's port contract match the CNN/TCN interfaces.
            features.append(np.asarray(samples, dtype=np.float32).T)
            labels.append(0)
            metadata.append({"trace_id": rows[end]["trace_id"], "base_waveform_id": rows[end]["base_waveform_id"],
                             "split": split, "end_index": str(end), "target_label": "0"})
    if not features:
        raise ValueError("no Safe stride-one windows for split {}".format(split))
    return WindowTable(np.stack(features), np.asarray(labels, dtype=np.int64), tuple(metadata), int(length))


def write_json(path, payload):
    """Atomically write a compact JSON artifact used by reproducibility reports."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
