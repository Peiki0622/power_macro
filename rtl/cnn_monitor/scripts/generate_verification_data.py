#!/usr/bin/env python3
"""Generate deterministic VCS vectors and cycle traces from the cycle model."""

from __future__ import print_function

import argparse
import json
from pathlib import Path

from power_macro.rtl.cnn_monitor.model.cycle_model import (
    CnnCycleModel, _bound_package)


def _directed_windows():
    """Return hardware-focused edge patterns absent from the task-one set."""

    patterns = [
        ("directed_all_zero", [0] * 32),
        ("directed_all_fifteen", [15] * 32),
        ("directed_all_thirtytwo", [32] * 32),
        ("directed_single_peak", [15] * 10 + [32] + [15] * 21),
        ("directed_endpoint_jump", [15] * 31 + [32]),
        ("directed_alternating_extremes", [0, 32] * 16),
        ("directed_ramp", list(range(32))),
    ]
    return patterns


def _write_vector_record(stream, name, codes, result):
    """Write one whitespace-delimited record that SystemVerilog can scan."""

    fields = [name] + [str(int(value)) for value in codes]
    fields += [str(int(result["integer_logits"][0])),
               str(int(result["integer_logits"][1])),
               str(int(result["integer_logit_difference"])),
               str(int(result["integer_decision"]))]
    stream.write(" ".join(fields) + "\n")


def _write_tensor_record(stream, name, result):
    """Serialize every internal tensor checked at fixed RTL milestones."""

    fields = [name]
    for key in ("integer_relu1", "integer_relu2", "integer_relu3",
                "integer_summary", "integer_classifier_accumulator"):
        fields.extend(str(int(value)) for value in result[key].reshape(-1))
    stream.write(" ".join(fields) + "\n")


def _trace_fields(row):
    """Map one rich model event to fixed-width RTL-observable trace fields.

    Every row contains ten scalar control/address fields followed by sixteen
    signed product-register values and sixteen signed accumulator values.  The
    classifier uses lanes zero and one of those arrays; unused positions are
    zero padded.  A fixed row width keeps the SystemVerilog scanner simple and
    makes a truncated or shifted trace fail immediately rather than silently
    corrupting all later cycle comparisons.
    """

    event_codes = {
        "conv_bias_init": 1,
        "conv_rom_issue": 2,
        "conv_requantize_prepare": 5,
        "conv_requantize_write": 6,
        "pool_init": 7,
        "pool_update": 8,
        "pool_finalize": 9,
        "classifier_bias_init": 10,
        "classifier_mac": 11,
        "classifier_pipeline_drain": 12,
        "classifier_logit_prepare": 13,
        "classifier_result": 14,
    }
    event = row["event"]
    if event == "conv_pipeline_drain":
        event_code = 3 if row["stage"] == 1 else 4
    else:
        event_code = event_codes[event]
    if event.startswith("conv_"):
        position = row["output_position"]
        output_base = row.get("output_base", -1)
        input_channel = row.get("input_channel", -1)
        kernel_tap = row.get("kernel_tap", -1)
        layer = row["layer"]
    elif event == "pool_update":
        layer, position, output_base, input_channel, kernel_tap = (
            0, row["output_position"], -1, -1, -1)
    elif event == "classifier_mac":
        layer, position, output_base, input_channel, kernel_tap = (
            0, row["summary_address"], -1, -1, -1)
    else:
        layer, position, output_base, input_channel, kernel_tap = (
            0, -1, -1, -1, -1)
    rom_address = row.get("weight_address", -1)
    activation = row.get("activation_value", 0)
    product_valid = row.get("product_valid", 0)
    products = list(row.get("product_values", []))
    accumulators = list(row.get("accumulator_values", []))
    products.extend([0] * (16 - len(products)))
    accumulators.extend([0] * (16 - len(accumulators)))
    return ((row["cycle"], event_code, layer, position, output_base,
             input_channel, kernel_tap, rom_address, activation,
             product_valid)
            + tuple(products[:16]) + tuple(accumulators[:16]))


def generate(config_path, output_directory):
    """Create self-checking inputs, internal tensors, trace, and special cases."""

    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    package = _bound_package(config_path)
    task1_root = package["root"]
    golden_rows = [json.loads(line) for line in (
        task1_root / "golden" / "windows.jsonl").read_text(
            encoding="utf-8").splitlines()]
    windows = [("golden_{}_{}".format(index, row["category"]),
                row["sensor_codes"]) for index, row in enumerate(golden_rows)]
    windows.extend(_directed_windows())

    results = []
    for name, codes in windows:
        results.append((name, codes, CnnCycleModel(
            package, mac_lanes=16, capture_trace=(len(results) == 0)).run(codes)))

    with (output / "vectors.txt").open("w", encoding="ascii") as stream:
        stream.write(str(len(results)) + "\n")
        for name, codes, result in results:
            _write_vector_record(stream, name, codes, result)
    with (output / "internal_tensors.txt").open("w", encoding="ascii") as stream:
        stream.write(str(len(results)) + "\n")
        for name, _, result in results:
            _write_tensor_record(stream, name, result)
    with (output / "cycle_trace.txt").open("w", encoding="ascii") as stream:
        trace = results[0][2]["trace"]
        stream.write(str(len(trace)) + "\n")
        for row in trace:
            stream.write(" ".join(str(value) for value in _trace_fields(row))
                         + "\n")

    # Special integration cases have windows formed by protocol timing rather
    # than by loading one static vector through the ordinary test task.
    special = {
        "same_cycle": [15] * 31 + [32],
        "all_fifteen": [15] * 32,
        "all_zero": [0] * 32,
    }
    with (output / "special_expected.txt").open("w", encoding="ascii") as stream:
        stream.write(str(len(special)) + "\n")
        for name, codes in special.items():
            result = CnnCycleModel(package, 16, capture_trace=False).run(codes)
            _write_vector_record(stream, name, codes, result)


def main():
    """Parse stable config/output paths for the VCS regression driver."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-directory", required=True)
    arguments = parser.parse_args()
    generate(arguments.config, arguments.output_directory)


if __name__ == "__main__":
    main()
