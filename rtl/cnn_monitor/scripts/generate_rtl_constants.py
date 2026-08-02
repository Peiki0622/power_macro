#!/usr/bin/env python3
"""Generate non-weight RTL constants from the authenticated task-one package.

The generated modules deliberately use combinational ``case`` statements.  A
synthesis or gate simulation therefore never depends on a working directory,
an initialization file, or ``$readmemh`` support.  Convolution weights are not
emitted here: their only release implementation is the authenticated
``CNNW384X128`` compiled macro.  This file retains convolution biases,
per-channel numeric contracts, and the small classifier coefficient table.
"""

from __future__ import print_function

import argparse
import json
from pathlib import Path

from power_macro.rtl.cnn_monitor.model.parameter_package import (
    load_parameter_package)


def _unsigned_word(value, bits):
    """Encode a Python signed integer as a fixed-width two's-complement word."""

    return int(value) & ((1 << int(bits)) - 1)


def _pack(values, bits, lanes=16):
    """Pack lane zero into the least-significant slice of a constant vector."""

    packed = 0
    for lane, value in enumerate(list(values)[:lanes]):
        packed |= _unsigned_word(value, bits) << (lane * bits)
    return "{}'h{:0{}x}".format(lanes * bits, packed,
                                (lanes * bits + 3) // 4)


def _module_header(name, ports, purpose):
    """Return a generated-module header with modular, per-port documentation."""

    lines = [
        "// Generated file: do not hand edit.",
        "// {}".format(purpose),
        "// Lane zero always occupies the least-significant packed slice.",
        "module {} (".format(name),
    ]
    for index, (declaration, comment) in enumerate(ports):
        comma = "," if index + 1 != len(ports) else ""
        lines.append("    {}{} // {}".format(declaration, comma, comment))
    lines.extend([
        ");",
        "",
    ])
    return lines


def _emit_conv_weight_rom(tensors):
    """Emit grouped convolution weights for all legal output-channel bases."""

    lines = _module_header("cnn_conv_weight_rom", [
        ("input  logic [1:0]   layer_id", "1/2/3 select the convolution layer."),
        ("input  logic [4:0]   output_base", "First output channel in the returned lane group."),
        ("input  logic [4:0]   input_channel", "Input feature channel; layer 1 uses zero."),
        ("input  logic [2:0]   kernel_tap", "Cross-correlation tap 0 through 4."),
        ("output logic [127:0] lane_weights", "Sixteen signed 8-bit weights packed by lane."),
    ], "Authenticated W8 convolution coefficients for the shared MAC array.")
    lines.extend([
        "    // Nested cases expose the natural address hierarchy to DC: layer and",
        "    // output group are decoded once, then the 5xinput-channel tap table",
        "    // is selected.  This avoids a single flat 3,330-way mux.",
        "    always_comb begin",
        "        lane_weights = 128'b0;",
        "        case (layer_id)",
    ])
    for layer_id, name in ((1, "conv1.weights"), (2, "conv2.weights"),
                           (3, "conv3.weights")):
        weights = tensors[name]
        lines.append("            2'd{}: begin".format(layer_id))
        lines.append("                case (output_base)")
        for output_base in range(18):
            lines.append("                    5'd{}: begin".format(output_base))
            lines.append("                        case ({input_channel, kernel_tap})")
            for input_channel in range(weights.shape[1]):
                for kernel_tap in range(5):
                    values = [weights[channel, input_channel, kernel_tap]
                              if channel < 18 else 0
                              for channel in range(output_base, output_base + 16)]
                    tap_key = (input_channel << 3) | kernel_tap
                    lines.append("                            8'd{}: lane_weights = {};".format(
                        tap_key, _pack(values, 8)))
            lines.extend(["                            default: lane_weights = 128'b0;",
                          "                        endcase", "                    end"])
        lines.extend(["                    default: lane_weights = 128'b0;",
                      "                endcase", "            end"])
    lines.extend(["            default: lane_weights = 128'b0;", "        endcase",
                  "    end", "endmodule", ""])
    return lines


def _emit_conv_bias_rom(tensors):
    """Emit fourteen packed physical-group bias words.

    Conv1 has five genuinely distinct padding classes: positions 0, 1, the
    shared interior interval 2..29, 30, and 31.  Each class has two physical
    16-channel words.  Conv2 and Conv3 are position independent and each add
    two more words.  Packing at generation time removes sixteen replicated
    run-time channel decoders while preserving contiguous 4/8-lane slicing.
    """

    conv1_bias = tensors["conv1.bias"]
    # Compression is valid only when every interior position is identical.
    # Reject a future package that violates this property instead of silently
    # mapping a distinct bias to the shared interior class.
    for position in range(3, 30):
        if not (conv1_bias[:, position] == conv1_bias[:, 2]).all():
            raise ValueError(
                "conv1 bias positions 2 through 29 are not one class")
    class_positions = (0, 1, 2, 30, 31)

    lines = _module_header("cnn_conv_bias_rom", [
        ("input  logic [1:0]   layer_id", "1/2/3 select the convolution layer."),
        ("input  logic         physical_group", "Zero selects channels 0..15; one selects 16..31."),
        ("input  logic [2:0]   position_class", "Conv1 classes 0/1/interior/30/31; other layers use zero."),
        ("output logic [319:0] lane_biases", "Sixteen signed 20-bit biases; physical lane zero is [19:0]."),
    ], "Packed accumulator-domain convolution biases for one physical group.")
    lines.extend([
        "    // Only fourteen whole-word alternatives are decoded: ten Conv1",
        "    // position/group words plus two words for each later layer.",
        "    always_comb begin",
        "        lane_biases = 320'b0;",
        "        case ({layer_id, physical_group, position_class})",
    ])
    for physical_group in range(2):
        channel_base = physical_group * 16
        for position_class, position in enumerate(class_positions):
            values = [conv1_bias[channel, position] if channel < 18 else 0
                      for channel in range(channel_base, channel_base + 16)]
            key = (1 << 4) | (physical_group << 3) | position_class
            lines.append("            6'h{:02x}: lane_biases = {};".format(
                key, _pack(values, 20)))
    for layer_id, name in ((2, "conv2.bias"), (3, "conv3.bias")):
        bias = tensors[name]
        for physical_group in range(2):
            channel_base = physical_group * 16
            values = [bias[channel] if channel < 18 else 0
                      for channel in range(channel_base, channel_base + 16)]
            key = (layer_id << 4) | (physical_group << 3)
            lines.append("            6'h{:02x}: lane_biases = {};".format(
                key, _pack(values, 20)))
    lines.extend([
        "            default: lane_biases = 320'b0;",
        "        endcase",
        "    end",
        "endmodule",
        "",
    ])
    return lines


def _emit_channel_contract_rom(selected):
    """Emit six packed physical-group numeric-contract words."""

    lines = _module_header("cnn_channel_contract_rom", [
        ("input  logic [1:0]  layer_id", "1/2/3 select the convolution layer."),
        ("input  logic        physical_group", "Zero selects channels 0..15; one selects 16..31."),
        ("output logic [79:0] lane_right_shifts", "Sixteen unsigned five-bit requantization shifts."),
        ("output logic [319:0] lane_magnitude_bounds", "Sixteen unsigned twenty-bit accumulator bounds."),
    ], "Packed fixed-point shifts and overflow bounds for one physical group.")
    lines.extend([
        "    // One decoder supplies every lane; channels 18 through 31 remain",
        "    // zero-filled in physical group one and are masked by the engine.",
        "    always_comb begin",
        "        lane_right_shifts = 80'b0;",
        "        lane_magnitude_bounds = 320'b0;",
        "        case ({layer_id, physical_group})",
    ])
    for layer_id, layer in enumerate(selected["layers"], 1):
        shifts = []
        for source in layer["accumulator_exponents"]:
            shift = int(layer["output_exponent"]) - int(source)
            if shift < 0:
                raise ValueError(
                    "RTL convolution contract unexpectedly needs a left shift")
            shifts.append(shift)
        bounds = [int(value) for value in layer["accumulator_bounds"]]
        for physical_group in range(2):
            channel_base = physical_group * 16
            group_shifts = [shifts[channel] if channel < 18 else 0
                            for channel in range(channel_base,
                                                 channel_base + 16)]
            group_bounds = [bounds[channel] if channel < 18 else 0
                            for channel in range(channel_base,
                                                 channel_base + 16)]
            key = (layer_id << 1) | physical_group
            lines.extend([
                "            3'h{:x}: begin".format(key),
                "                lane_right_shifts = {};".format(
                    _pack(group_shifts, 5)),
                "                lane_magnitude_bounds = {};".format(
                    _pack(group_bounds, 20)),
                "            end",
            ])
    lines.extend([
        "            default: begin",
        "                lane_right_shifts = 80'b0;",
        "                lane_magnitude_bounds = 320'b0;",
        "            end",
        "        endcase",
        "    end",
        "endmodule",
        "",
    ])
    return lines


def _emit_classifier_rom(tensors, selected):
    """Emit the two-output classifier coefficients and final requantization data."""

    weights = tensors["classifier.weights"]
    bias = tensors["classifier.bias"]
    classifier = selected["classifier"]
    # The accepted package places classifier accumulators at 2^-10/2^-9 and
    # logits at 2^-26.  Expressing the same real number at the finer logit
    # scale therefore requires exact left shifts of 16/17 bits.  The 20-bit
    # analytical accumulator bounds guarantee the shifted values fit INT32.
    shifts = [int(value) - int(selected["classifier_output_exponent"])
              for value in classifier["accumulator_exponents"]]
    if any(shift < 0 for shift in shifts):
        raise ValueError("RTL classifier contract unexpectedly needs a right shift")
    lines = _module_header("cnn_classifier_parameter_rom", [
        ("input  logic [5:0]  summary_index", "Summary feature 0 through 53 in average/max/endpoint order."),
        ("output logic [15:0] class_weights", "Signed 8-bit Safe weight in [7:0], Critical in [15:8]."),
        ("output logic [39:0] class_biases", "Signed 20-bit Safe bias in [19:0], Critical in [39:20]."),
        ("output logic [9:0]  class_left_shifts", "Five-bit exact left shift for each output class."),
        ("output logic [39:0] class_bounds", "Twenty-bit magnitude bound for each output class."),
    ], "Binary classifier constants in the task-one summary concatenation order.")
    lines.extend(["    always_comb begin", "        class_weights = 16'b0;",
                  "        case (summary_index)"])
    for index in range(54):
        lines.append("            6'd{}: class_weights = {};".format(
            index, _pack([weights[0, index], weights[1, index]], 8, lanes=2)))
    lines.extend(["            default: class_weights = 16'b0;", "        endcase",
                  "        class_biases = 40'h{:010x};".format(
                      _unsigned_word(bias[0], 20) | (_unsigned_word(bias[1], 20) << 20)),
                  "        class_left_shifts = 10'h{:03x};".format(shifts[0] | (shifts[1] << 5)),
                  "        class_bounds = 40'h{:010x};".format(
                      int(classifier["accumulator_bounds"][0])
                      | (int(classifier["accumulator_bounds"][1]) << 20)),
                  "    end", "endmodule", ""])
    return lines


def generate(config_path, output_path):
    """Authenticate the bound package and atomically replace the generated RTL."""

    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    # config/... is three levels below power_macro; resolving from that stable
    # repository root makes generation independent of the caller's cwd.
    power_macro_root = config_path.parents[3]
    package_root = power_macro_root.parent / config["task1_binding"]["package_root"]
    package = load_parameter_package(
        package_root,
        config["task1_binding"]["manifest_sha256"],
        config["task1_binding"]["quantization_config_sha256"])
    lines = ["`default_nettype none", ""]
    # Do not emit the historical source-level convolution weight case ROM.
    # Keeping it out of the analyzed RTL prevents accidental fallback to a
    # standard-cell mux/register implementation when the hard macro is absent.
    lines += _emit_conv_bias_rom(package["tensors"])
    lines += _emit_channel_contract_rom(package["selected"])
    lines += _emit_classifier_rom(package["tensors"], package["selected"])
    lines += ["`default_nettype wire", ""]
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text("\n".join(lines), encoding="ascii")
    temporary.replace(output_path)


def main():
    """Parse command-line paths and generate the checked-in RTL constants."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    generate(arguments.config, arguments.output)


if __name__ == "__main__":
    main()
