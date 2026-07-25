#!/usr/bin/env python3
"""Select the startup launch setting from 32 real decoded DFF samples per tap."""

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List


def load_json(path: Path) -> Dict[str, Any]:
    """Read the Phase 2 configuration object without substituting defaults."""

    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def numeric(row: Dict[str, str], field: str) -> float:
    """Parse one required calibration CSV scalar with scenario context."""

    value = row.get(field, "").strip()
    if not value:
        raise ValueError("calibration row lacks {}".format(field))
    return float(value)


def choose(rows: List[Dict[str, str]], config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply midpoint, bubble-count, then smaller-offset tie breaking exactly."""

    expected_samples = int(config["calibration_sample_count"])
    grouped: Dict[int, List[Dict[str, str]]] = {}
    for row in rows:
        cal_sel = int(numeric(row, "cal_sel"))
        grouped.setdefault(cal_sel, []).append(row)
    expected_taps = list(range(len(config["calibration_launch_offsets_s"])))
    if sorted(grouped) != expected_taps:
        raise ValueError("calibration CSV must contain all configured CAL_SEL values")
    summaries = []
    for cal_sel in expected_taps:
        samples = grouped[cal_sel]
        if len(samples) != expected_samples:
            raise ValueError("CAL_SEL {} has {} samples, expected {}".format(cal_sel, len(samples), expected_samples))
        valid = [row for row in samples if row["code_valid"].strip().lower() == "true"]
        if not valid:
            raise ValueError("CAL_SEL {} has no valid decoded samples".format(cal_sel))
        codes = [numeric(row, "sensor_code") for row in valid]
        bubbles = [numeric(row, "raw_bubble_count") for row in samples]
        offsets = [numeric(row, "launch_offset_s") for row in samples]
        m_values = {int(numeric(row, "m_stages")) for row in samples}
        if len(m_values) != 1:
            raise ValueError("CAL_SEL {} mixes M values".format(cal_sel))
        summaries.append(
            {
                "cal_sel": cal_sel,
                "m_stages": m_values.pop(),
                "baseline_code": statistics.median(codes),
                "baseline_variation": max(codes) - min(codes),
                "median_raw_bubble_count": statistics.median(bubbles),
                "launch_offset_s": statistics.median(offsets),
                "valid_sample_count": len(valid),
            }
        )
    target = summaries[0]["m_stages"] / 2.0
    selected = min(
        summaries,
        key=lambda item: (
            abs(item["baseline_code"] - target),
            item["median_raw_bubble_count"],
            item["launch_offset_s"],
        ),
    )
    return {
        "schema_version": 1,
        "calibration_status": "PASS",
        "selected_cal_sel": selected["cal_sel"],
        "baseline_code": selected["baseline_code"],
        "baseline_variation": selected["baseline_variation"],
        "selected_launch_offset_s": selected["launch_offset_s"],
        "tap_summaries": summaries,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    """Define explicit evidence inputs and structured calibration output."""

    parser = argparse.ArgumentParser(description="calibrate Phase-2 Vernier launch tap")
    parser.add_argument("--config", required=True, type=Path, help="Phase 2 configuration")
    parser.add_argument("--decoded-csv", required=True, type=Path, help="32-sample-per-tap decoded CSV")
    parser.add_argument("--output-json", required=True, type=Path, help="calibration result JSON")
    return parser


def main(argv: Iterable[str] = None) -> int:
    """Select one startup tap and reject incomplete sampling evidence."""

    args = build_argument_parser().parse_args(argv)
    config = load_json(args.config)
    with args.decoded_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    result = choose(rows, config)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
