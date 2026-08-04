#!/usr/bin/env python3
"""Validate task-three codebooks before a report may claim a pass.

The validator is intentionally format-focused: it cross-checks the frozen
window manifest, the three raw repeats, and the aggregated codebook.  Physical
power is separately gated, so an RTL-only codebook must retain null power
fields instead of accidentally inheriting a vectorless estimate.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, Mapping

# Use the repository package path so this module behaves identically when run
# by unittest and when invoked directly with the workspace on PYTHONPATH.
from power_macro.rtl.cnn_monitor.scripts.analyze_activity_codebook_v2 import MODULE_GROUPS


class CodebookValidationError(ValueError):
    """Raised when a mandatory task-three integrity gate is not satisfied."""


def _read_jsonl(path: Path) -> list[Dict[str, object]]:
    """Load a compact JSONL artifact while rejecting blank or malformed lines."""
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise CodebookValidationError("blank JSONL record at {}:{}".format(path, line_number))
        records.append(json.loads(line))
    return records


def validate_records(codebook: Iterable[Mapping[str, object]], raw: Iterable[Mapping[str, object]],
                     windows: Iterable[Mapping[str, object]], config: Mapping[str, object],
                     power_required: bool) -> Dict[str, object]:
    """Apply all cardinality, repeat, functional, and power-nullability gates."""
    codebook_rows, raw_rows, window_rows = list(codebook), list(raw), list(windows)
    expected_total = int(config["required_valid_pattern_count"])
    expected_candidates = int(config["required_candidate_pattern_count"])
    if len(codebook_rows) != expected_total:
        raise CodebookValidationError("codebook count is {}, expected {}".format(len(codebook_rows), expected_total))
    identifiers = [str(row["pattern_id"]) for row in codebook_rows]
    if len(set(identifiers)) != len(identifiers):
        raise CodebookValidationError("codebook contains duplicate pattern_id")
    window_by_id = {str(row["pattern_id"]): row for row in window_rows}
    if set(identifiers) != set(window_by_id):
        raise CodebookValidationError("codebook and frozen window manifest differ")
    candidates = [row for row in codebook_rows if row["family"] != "control"]
    if len(candidates) != expected_candidates:
        raise CodebookValidationError("candidate count differs from frozen contract")

    repeats = defaultdict(list)
    for row in raw_rows:
        repeats[str(row["pattern_id"])].append(row)
    required_groups = set(MODULE_GROUPS)
    for row in codebook_rows:
        pattern_id = str(row["pattern_id"])
        if row.get("input_sha256") != window_by_id[pattern_id].get("input_sha256"):
            raise CodebookValidationError("input SHA mismatch for {}".format(pattern_id))
        if row.get("validity_status") != "valid":
            raise CodebookValidationError("invalid codebook entry {}".format(pattern_id))
        if set(row.get("module_toggle_vector", {})) != required_groups:
            raise CodebookValidationError("incomplete module vector for {}".format(pattern_id))
        observations = repeats.get(pattern_id, [])
        if len(observations) != int(config["repeat_count"]):
            raise CodebookValidationError("wrong raw repeat count for {}".format(pattern_id))
        expected = row.get("expected", {})
        for observation in observations:
            if observation.get("latency_cycles") != int(config["compute_latency_cycles"]):
                raise CodebookValidationError("latency mismatch for {}".format(pattern_id))
            if observation.get("numeric_overflow") or observation.get("protocol_error"):
                raise CodebookValidationError("sticky error for {}".format(pattern_id))
            if [observation.get("safe_logit"), observation.get("critical_logit")] != [
                    expected.get("safe_logit"), expected.get("critical_logit")]:
                raise CodebookValidationError("logit mismatch for {}".format(pattern_id))
            if observation.get("decision") != expected.get("decision"):
                raise CodebookValidationError("decision mismatch for {}".format(pattern_id))

    power_fields = ("average_dynamic_power_mw", "energy_window_nj", "peak_power_mw")
    present = [
        any(row.get(field) is not None for field in power_fields)
        for row in codebook_rows
    ]
    if power_required and not all(present):
        raise CodebookValidationError("power-required codebook contains null power fields")
    if not power_required and any(present):
        raise CodebookValidationError("RTL-only codebook contains physical power fields")
    if any(present) and not all(present):
        raise CodebookValidationError("power annotations are only partially populated")
    return {"status": "PASS", "pattern_count": len(codebook_rows)}


def main() -> None:
    """Run the validator over explicit input artifacts and print compact JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--codebook", required=True, type=Path)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--window-manifest", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--power-required", action="store_true")
    args = parser.parse_args()
    windows_path = args.window_manifest.with_name("windows.jsonl")
    result = validate_records(
        _read_jsonl(args.codebook), _read_jsonl(args.raw), _read_jsonl(windows_path),
        json.loads(args.config.read_text(encoding="utf-8")), args.power_required,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
