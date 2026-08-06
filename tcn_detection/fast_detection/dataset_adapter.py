#!/usr/bin/env python3
"""Read the frozen binary state trace release for causal detector evaluation."""

from __future__ import print_function

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from power_macro.tcn_detection.fast_detection.detector_base import TraceMetadata


EXPECTED_SPLIT_COUNTS = {"train": 144, "validation": 48, "iid_test": 48}
EXPECTED_SAMPLES_PER_TRACE = 500


@dataclass(frozen=True)
class Sample:
    """One immutable online observation plus evaluator-only truth."""

    sample_index: int
    sensor_code: int
    bubble_count: int
    valid: bool
    target_label: int


@dataclass(frozen=True)
class Trace:
    """One complete 500-sample trace and its provenance metadata."""

    metadata: TraceMetadata
    samples: tuple


def sha256_file(path):
    """Hash an input artifact without loading large CSV files at once."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class DatasetAdapter:
    """Validate and stream the immutable current-state binary trace release."""

    def __init__(self, label_root, config_path=None):
        self.label_root = Path(label_root)
        self.config_path = Path(config_path) if config_path else None
        if not self.label_root.is_dir():
            raise FileNotFoundError("label root does not exist: {}".format(self.label_root))
        self._manifest = self._read_manifest()

    def _read_manifest(self):
        """Load provenance and reject a policy other than Safe/Critical state."""

        path = self.label_root / "provenance.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("policy_id") != "state_code_binary_iid_v1_20260730_r1":
            raise ValueError("unexpected binary label policy")
        if len(payload.get("traces", [])) != 240:
            raise ValueError("binary release must contain exactly 240 traces")
        return payload

    @property
    def manifest(self):
        """Return the immutable provenance object for report generation."""

        return self._manifest

    def iter_traces(self, splits):
        """Yield complete traces in stable ID order for the requested splits.

        Split filtering happens before CSV sample conversion.  No other split's
        sensor values are materialized in the process, preserving the same
        development/test boundary used by the existing model loaders.
        """

        requested = {str(value) for value in splits}
        allowed = set(EXPECTED_SPLIT_COUNTS)
        if not requested or not requested <= allowed:
            raise ValueError("unknown or empty split selection")
        selected = []
        for entry in self._manifest["traces"]:
            path = self.label_root / "traces" / entry["binary_label_csv"]
            if not path.is_file():
                raise FileNotFoundError("missing label trace: {}".format(path))
            with path.open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                rows = list(reader)
            if len(rows) != EXPECTED_SAMPLES_PER_TRACE:
                raise ValueError("trace must contain 500 samples: {}".format(path))
            split = rows[0]["split"]
            if any(row["split"] != split for row in rows):
                raise ValueError("trace split changes within file: {}".format(path))
            if split not in requested:
                continue
            selected.append(self._parse_trace(rows, entry))
        counts = {}
        for trace in selected:
            counts[trace.metadata.split] = counts.get(trace.metadata.split, 0) + 1
        for split in requested:
            if counts.get(split, 0) != EXPECTED_SPLIT_COUNTS[split]:
                raise ValueError("split count mismatch for {}".format(split))
        return tuple(sorted(selected, key=lambda trace: trace.metadata.trace_id))

    def _parse_trace(self, rows, manifest_entry):
        """Validate one trace's online fields and construct immutable samples."""

        first = rows[0]
        if first["trace_id"] != manifest_entry["trace_id"]:
            raise ValueError("trace ID differs from provenance manifest")
        metadata = TraceMetadata(
            trace_id=first["trace_id"], split=first["split"],
            base_waveform_id=first["base_waveform_id"],
            hard_pair_id=first.get("hard_pair_id", ""),
        )
        samples = []
        for expected_index, row in enumerate(rows):
            if int(row["sample_index"]) != expected_index:
                raise ValueError("sample index is not chronological")
            code = int(row["sensor_code"])
            bubbles = int(row["bubble_count"])
            if not 0 <= code <= 32 or not 0 <= bubbles <= 32:
                raise ValueError("sensor code or bubble count outside legal range")
            if row["binary_raw_label"] not in {"0", "1"}:
                raise ValueError("binary target is not Safe/Critical")
            if row.get("binary_label_eligible", "False").lower() != "true":
                raise ValueError("binary trace contains an ineligible target")
            samples.append(Sample(
                sample_index=expected_index, sensor_code=code,
                bubble_count=bubbles,
                valid=row["code_valid"].lower() == "true",
                target_label=int(row["binary_raw_label"])))
        return Trace(metadata=metadata, samples=tuple(samples))
