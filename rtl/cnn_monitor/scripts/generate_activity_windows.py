#!/usr/bin/env python3
"""Generate the fixed task-three L32 activity-window library.

The generator deliberately contains no random source: every pattern is a
small, reviewable recipe and the two real controls are copied from task one's
authenticated validation golden set.  The resulting JSONL is both the
measurement input and an audit record; changing any code value changes the
record SHA256 and the enclosing manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from power_macro.rtl.cnn_monitor.model.cycle_model import CnnCycleModel, _bound_package


WINDOW_LENGTH = 32


def _sha256_bytes(payload: bytes) -> str:
    """Return a stable SHA256 without depending on platform text newlines."""
    return hashlib.sha256(payload).hexdigest()


def _record(pattern_id: str, family: str, parameters: Dict[str, object],
            codes: Iterable[int]) -> Dict[str, object]:
    """Validate one hand-authored recipe and construct its canonical record.

    Validation is intentionally performed before invoking the cycle model so a
    malformed dummy cannot accidentally exercise the RTL or consume a run
    directory.  Compact JSON separators make the input digest independent of
    the surrounding manifest formatting.
    """
    values = [int(value) for value in codes]
    if len(values) != WINDOW_LENGTH:
        raise ValueError("{} is not an L32 window".format(pattern_id))
    if any(value < 0 or value > 32 for value in values):
        raise ValueError("{} contains a code outside [0,32]".format(pattern_id))
    input_bytes = json.dumps(values, separators=(",", ":")).encode("ascii")
    return {
        "pattern_id": pattern_id,
        "family": family,
        "parameters": parameters,
        "sensor_codes": values,
        "input_sha256": _sha256_bytes(input_bytes),
    }


def _ramp(start: int, stop: int) -> List[int]:
    """Create a deterministic inclusive integer ramp with exactly 32 points."""
    return [round(start + (stop - start) * index / 31.0)
            for index in range(WINDOW_LENGTH)]


def _peak(base: int, locations: Iterable[int], amplitude: int,
          width: int = 1) -> List[int]:
    """Place bounded rectangular peaks while keeping every sample legal."""
    result = [base] * WINDOW_LENGTH
    for location in locations:
        for offset in range(width):
            position = location + offset
            if 0 <= position < WINDOW_LENGTH:
                result[position] = amplitude
    return result


def _recipes() -> List[Tuple[str, str, Dict[str, object], List[int]]]:
    """Return all fixed synthetic patterns required by task three.

    The bounded-walk sequences are literal step lists rather than PRNG output.
    This preserves the requested random-walk-like transition coverage while
    retaining reproducibility and making every sample auditable in source.
    """
    items = []
    add = items.append
    for value, name in ((8, "low"), (16, "mid"), (24, "high")):
        add(("mean_constant_" + name, "mean_dominant", {"value": value},
             [value] * 32))
    add(("mean_ramp_up", "mean_dominant", {"start": 8, "stop": 24}, _ramp(8, 24)))
    add(("mean_ramp_down", "mean_dominant", {"start": 24, "stop": 8}, _ramp(24, 8)))
    add(("mean_plateau_high", "mean_dominant", {"base": 8, "plateau": 24, "start": 8, "width": 16}, [8] * 8 + [24] * 16 + [8] * 8))
    add(("mean_plateau_low", "mean_dominant", {"base": 24, "plateau": 8, "start": 8, "width": 16}, [24] * 8 + [8] * 16 + [24] * 8))
    for amplitude in (24, 32):
        add(("peak_single_{}".format(amplitude), "peak_dominant", {"base": 15, "amplitude": amplitude, "position": 16}, _peak(15, [16], amplitude)))
        add(("peak_double_{}".format(amplitude), "peak_dominant", {"base": 15, "amplitude": amplitude, "positions": [8, 23]}, _peak(15, [8, 23], amplitude)))
        add(("peak_burst_{}".format(amplitude), "peak_dominant", {"base": 15, "amplitude": amplitude, "position": 14, "width": 3}, _peak(15, [14], amplitude, 3)))
    for position in (0, 10, 21, 31):
        add(("peak_position_{}".format(position), "peak_dominant", {"base": 15, "amplitude": 32, "position": position}, _peak(15, [position], 32)))
    add(("endpoint_final_rise", "endpoint_dominant", {"base": 15, "endpoint": 28}, [15] * 31 + [28]))
    add(("endpoint_final_fall", "endpoint_dominant", {"base": 24, "endpoint": 8}, [24] * 31 + [8]))
    add(("endpoint_last4_rise", "endpoint_dominant", {"prefix": 15, "tail": [18, 23, 28, 32]}, [15] * 28 + [18, 23, 28, 32]))
    add(("endpoint_last4_fall", "endpoint_dominant", {"prefix": 24, "tail": [20, 16, 12, 8]}, [24] * 28 + [20, 16, 12, 8]))
    prefix = [14, 16] * 15 + [14]
    add(("endpoint_same_prefix_low", "endpoint_dominant", {"prefix": "alternating_14_16", "endpoint": 8}, prefix + [8]))
    add(("endpoint_same_prefix_high", "endpoint_dominant", {"prefix": "alternating_14_16", "endpoint": 32}, prefix + [32]))
    for name, start, steps in (("mixed_walk_low", 12, [1, -1, 2, 0, -2, 1, 1, -1] * 4), ("mixed_walk_high", 20, [-1, 1, -2, 0, 2, -1, -1, 1] * 4)):
        values = [start]
        for step in steps[:31]:
            values.append(max(0, min(32, values[-1] + step)))
        add((name, "mixed_statistic", {"start": start, "fixed_steps": steps[:31]}, values))
    add(("mixed_ramp_peak_low", "mixed_statistic", {"shape": "ramp_peak_recovery", "peak": 30}, _ramp(8, 20)[:12] + [30] * 4 + _ramp(20, 10)[16:]))
    add(("mixed_ramp_peak_high", "mixed_statistic", {"shape": "ramp_peak_recovery", "peak": 32}, _ramp(18, 26)[:12] + [32] * 4 + _ramp(26, 16)[16:]))
    add(("mixed_double_plateau_up", "mixed_statistic", {"plateaus": [8, 24], "endpoint": 28}, [8] * 10 + [24] * 18 + [26, 27, 28, 28]))
    add(("mixed_double_plateau_down", "mixed_statistic", {"plateaus": [24, 8], "endpoint": 4}, [24] * 10 + [8] * 18 + [6, 5, 4, 4]))
    add(("mixed_alternating_narrow", "mixed_statistic", {"values": [10, 20]}, [10, 20] * 16))
    add(("mixed_alternating_wide", "mixed_statistic", {"values": [6, 26]}, [6, 26] * 16))
    for value in (0, 15, 32):
        add(("control_all_{}".format(value), "control", {"value": value}, [value] * 32))
    return items


def generate(config_path: Path, output_directory: Path) -> List[Dict[str, object]]:
    """Write canonical windows and a provenance-bound manifest into one run.

    Existing output is rejected rather than overwritten.  The manifest records
    both the task-one parameter package digest and the exact generated JSONL
    digest, preventing a later activity run from silently changing either
    neural weights or window contents.
    """
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if output_directory.exists():
        raise FileExistsError("refusing to overwrite {}".format(output_directory))
    package = _bound_package(config_path.parents[1] / "config" / "cnn_rtl_config_v1.json")
    golden_rows = [json.loads(line) for line in (package["root"] / "golden" / "windows.jsonl").read_text(encoding="utf-8").splitlines()]
    controls = {row["category"]: row for row in golden_rows}
    records = [_record(pattern_id, family, parameters, codes)
               for pattern_id, family, parameters, codes in _recipes()]
    for category in config["real_control_categories"]:
        row = controls[category]
        records.append(_record("control_real_" + category, "control", {"source_window_id": row["window_id"], "category": category}, row["sensor_codes"]))
    for record in records:
        # A cycle model instance owns its monotonically increasing trace clock.
        # Create one per independent RTL request so every expected latency is
        # measured from that request edge rather than from a prior pattern.
        result = CnnCycleModel(package, mac_lanes=config["mac_lanes"],
                               capture_trace=False).run(record["sensor_codes"])
        record["expected"] = {"safe_logit": int(result["integer_logits"][0]), "critical_logit": int(result["integer_logits"][1]), "decision": int(result["integer_decision"]), "latency_cycles": int(result["latency_cycles"]), "numeric_overflow": bool(result["numeric_overflow"])}
    output_directory.mkdir(parents=True)
    jsonl = "".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records)
    (output_directory / "windows.jsonl").write_text(jsonl, encoding="ascii")
    # load_parameter_package returns decoded tensors, not a duplicate digest
    # field.  Hashing the authenticated package manifest here keeps provenance
    # explicit while avoiding a second, subtly different package loader.
    task1_manifest_sha256 = _sha256_bytes(
        (package["root"] / "manifest.json").read_bytes())
    manifest = {"config_id": config["config_id"], "record_count": len(records), "windows_sha256": _sha256_bytes(jsonl.encode("ascii")), "task1_manifest_sha256": task1_manifest_sha256, "families": {family: sum(record["family"] == family for record in records) for family in sorted({record["family"] for record in records})}}
    (output_directory / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="ascii")
    return records


def main() -> None:
    """Expose one narrow CLI so run drivers never write outside their run."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    generate(args.config.resolve(), args.output_directory.resolve())


if __name__ == "__main__":
    main()
