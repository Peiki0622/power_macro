#!/usr/bin/env python3
"""Decode raw DFF thermometer words without concealing bubbles.

The three-bit majority filter is deliberately limited to interior bits; both
edges retain their measured value because no external neighbor exists.  The
CSV carries raw and corrected bubble counts independently, making a corrected
single-bubble word auditable instead of silently indistinguishable from an
ideal measurement.
"""

import argparse
import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


def parse_word(word: str) -> List[int]:
    """Convert one nonempty binary thermometer word into ordered integer bits."""

    normalized = word.strip()
    if not normalized or any(bit not in "01" for bit in normalized):
        raise ValueError("raw_code must be a nonempty binary word: {!r}".format(word))
    return [int(bit) for bit in normalized]


def majority_correct(bits: Sequence[int]) -> List[int]:
    """Apply the declared three-bit majority filter while preserving edge bits."""

    if len(bits) <= 2:
        return list(bits)
    corrected = [bits[0]]
    for index in range(1, len(bits) - 1):
        corrected.append(1 if bits[index - 1] + bits[index] + bits[index + 1] >= 2 else 0)
    corrected.append(bits[-1])
    return corrected


def thermometer_metrics(bits: Sequence[int]) -> Dict[str, Any]:
    """Measure a 0*1* word, exposing all non-monotonic zeros after first one."""

    first_one = next((index for index, bit in enumerate(bits) if bit == 1), len(bits))
    bubble_count = sum(1 for bit in bits[first_one:] if bit == 0)
    transition_count = sum(1 for index in range(1, len(bits)) if bits[index] != bits[index - 1])
    return {
        "sensor_code": first_one,
        "bubble_count": bubble_count,
        "transition_count": transition_count,
        "code_valid": bubble_count == 0 and transition_count <= 1,
    }


def decode_word(raw_code: str) -> Dict[str, Any]:
    """Return raw/corrected observability plus the corrected leading-zero code."""

    raw_bits = parse_word(raw_code)
    corrected_bits = majority_correct(raw_bits)
    raw = thermometer_metrics(raw_bits)
    corrected = thermometer_metrics(corrected_bits)
    return {
        "raw_code": "".join(str(bit) for bit in raw_bits),
        "corrected_code": "".join(str(bit) for bit in corrected_bits),
        "sensor_code": corrected["sensor_code"],
        "raw_bubble_count": raw["bubble_count"],
        "bubble_count": corrected["bubble_count"],
        "raw_transition_count": raw["transition_count"],
        "transition_count": corrected["transition_count"],
        "code_valid": corrected["code_valid"],
    }


def decode_rows(rows: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Preserve scenario provenance while adding a standard decoded-code schema."""

    decoded = []
    for row in rows:
        metrics = decode_word(row.get("raw_code", ""))
        metrics.update(
            {
                "scenario_id": row.get("scenario_id", ""),
                "candidate_id": row.get("candidate_id", ""),
                "vdd_a_v": row.get("vdd_a_v", ""),
                "vdd_ref_v": row.get("vdd_ref_v", ""),
                "m_stages": row.get("m_stages", ""),
                "dummy_load_count": row.get("dummy_load_count", ""),
                "launch_offset_s": row.get("launch_offset_s", ""),
                "cal_sel": row.get("cal_sel", ""),
                "sample_index": row.get("sample_index", ""),
            }
        )
        decoded.append(metrics)
    return decoded


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    """Write the documented Phase 2 decoded-code interchange format."""

    fields = [
        "scenario_id", "candidate_id", "vdd_a_v", "vdd_ref_v", "m_stages", "dummy_load_count", "launch_offset_s",
        "cal_sel", "sample_index", "raw_code", "corrected_code", "sensor_code", "raw_bubble_count", "bubble_count",
        "raw_transition_count", "transition_count", "code_valid",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})


def build_argument_parser() -> argparse.ArgumentParser:
    """Expose a simple CSV-to-CSV command used by simulation and calibration."""

    parser = argparse.ArgumentParser(description="decode Phase-2 Vernier thermometer words")
    parser.add_argument("--input-csv", required=True, type=Path, help="raw DFF or calibration CSV")
    parser.add_argument("--output-csv", required=True, type=Path, help="decoded-code CSV")
    return parser


def main(argv: Iterable[str] = None) -> int:
    """Decode every raw word and require a nonempty source result."""

    args = build_argument_parser().parse_args(argv)
    with args.input_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("input CSV is empty: {}".format(args.input_csv))
    decoded = decode_rows(rows)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_csv, decoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
