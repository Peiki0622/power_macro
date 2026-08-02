#!/usr/bin/env python3
"""Cycle-accurate software model of the real-window CNN RTL controller.

This model performs every multiply-accumulate in the same loop order as the
RTL.  It intentionally does not call the vectorized bit-true forward path for
the result: the per-cycle state updates are the independent bridge between the
accepted task-one integer tensors and RTL waveforms.
"""

from __future__ import print_function

import argparse
import json
from pathlib import Path

import numpy as np

from power_macro.rtl.cnn_monitor.model.parameter_package import (
    load_parameter_package)


def round_right_shift_ties_even_scalar(value, shift):
    """Round a signed integer divided by 2**shift to nearest, ties to even."""

    value = int(value)
    shift = int(shift)
    if shift < 0:
        raise ValueError("right shift cannot be negative")
    if shift == 0:
        return value
    denominator = 1 << shift
    quotient = value // denominator
    remainder = value - quotient * denominator
    half = denominator >> 1
    if remainder > half or (remainder == half and (quotient & 1)):
        quotient += 1
    return quotient


class CnnCycleModel(object):
    """Execute one frozen L32 snapshot with a fixed lane-count schedule."""

    def __init__(self, package, mac_lanes=16, capture_trace=True):
        self.package = package
        self.selected = package["selected"]
        self.tensors = package["tensors"]
        self.mac_lanes = int(mac_lanes)
        if self.mac_lanes not in (4, 8, 16):
            raise ValueError("MAC lanes must be one of 4, 8, or 16")
        self.capture_trace = bool(capture_trace)
        self.cycle = 0
        self.trace = []
        self.overflow = False

    def _record(self, event, **fields):
        """Append one controller-cycle event without affecting model state."""

        self.cycle += 1
        if self.capture_trace:
            row = {"cycle": self.cycle, "event": event}
            row.update(fields)
            self.trace.append(row)

    def _requantize_relu(self, value, source_exponent, output_exponent):
        """Apply the layer's single ties-even shift, INT8 clamp, and ReLU."""

        shift = int(output_exponent) - int(source_exponent)
        if shift < 0:
            aligned = int(value) << (-shift)
        else:
            aligned = round_right_shift_ties_even_scalar(value, shift)
        return min(127, max(0, aligned))

    def _run_convolution(self, layer_index, source):
        """Run one same-padded k=5 layer in position/group/fanin order.

        ``source`` is channel-major ``[input_channel][position]``.  The
        activation address is recorded as -1 for either padding location; RTL
        treats that address as a zero operand and does not access feature RAM.
        One ROM request is issued per cycle.  The synchronous ROM response and
        registered product retire through two fixed drain cycles after the last
        request.  Requantization prepare and bank write are separate cycles,
        giving exactly ``fanin + 5`` cycles per output group.
        """

        metadata = self.selected["layers"][layer_index - 1]
        name = "conv{}".format(layer_index)
        weights = self.tensors[name + ".weights"]
        bias = self.tensors[name + ".bias"]
        input_channels = int(weights.shape[1])
        destination = np.zeros((18, 32), dtype=np.int64)
        groups = (18 + self.mac_lanes - 1) // self.mac_lanes

        for position in range(32):
            for group in range(groups):
                output_base = group * self.mac_lanes
                accumulators = [0] * self.mac_lanes
                for lane in range(self.mac_lanes):
                    output_channel = output_base + lane
                    if output_channel < 18:
                        accumulators[lane] = int(
                            bias[output_channel, position]
                            if bias.ndim == 2 else bias[output_channel])
                self._record(
                    "conv_bias_init", layer=layer_index,
                    output_position=position, output_base=output_base,
                    bias_address=((output_base * 32 + position)
                                  if bias.ndim == 2 else output_base))

                # These variables model the values visible immediately before
                # each RTL rising edge.  A ROM response and its matching
                # activation form a product on one edge; an already-registered
                # product retires on that same edge.  Keeping both ages here is
                # essential: a model that adds the current issue directly can
                # produce correct final tensors while still hiding a one-cycle
                # RTL alignment defect.
                activation_pipe = 0
                activation_valid = False
                response_weights = [0] * self.mac_lanes
                response_valid = False
                product_pipe = [0] * self.mac_lanes
                product_valid = False

                for input_channel in range(input_channels):
                    for kernel_tap in range(5):
                        source_position = position + kernel_tap - 2
                        activation = (int(source[input_channel, source_position])
                                      if 0 <= source_position < 32 else 0)
                        physical_group = output_base // 16
                        physical_base = (0 if layer_index == 1 else
                                         10 if layer_index == 2 else 190)
                        physical_address = (physical_base
                                            + physical_group * input_channels * 5
                                            + input_channel * 5 + kernel_tap)
                        issue_weights = []
                        for lane in range(self.mac_lanes):
                            output_channel = output_base + lane
                            issue_weights.append(
                                int(weights[output_channel, input_channel,
                                            kernel_tap])
                                if output_channel < 18 else 0)
                        next_cycle = self.cycle + 1
                        self._record(
                            "conv_rom_issue", layer=layer_index,
                            output_position=position, output_base=output_base,
                            input_channel=input_channel, kernel_tap=kernel_tap,
                            weight_address=physical_address,
                            activation_channel=input_channel,
                            activation_position=source_position,
                            activation_value=activation,
                            product_valid=int(product_valid),
                            product_values=list(product_pipe),
                            accumulator_values=list(accumulators),
                            mac_issue_cycle=next_cycle,
                            rom_response_cycle=next_cycle + 1,
                            mac_retire_cycle=next_cycle + 2)

                        # Apply exactly the nonblocking updates performed by
                        # STATE_MAC_ISSUE.  The old product retires first in
                        # mathematical notation, while new_product is formed
                        # exclusively from the previous response/activation.
                        if product_valid:
                            for lane in range(self.mac_lanes):
                                if output_base + lane < 18:
                                    accumulators[lane] += product_pipe[lane]
                        new_product_valid = (response_valid
                                             and activation_valid)
                        new_product = [0] * self.mac_lanes
                        if new_product_valid:
                            for lane in range(self.mac_lanes):
                                if output_base + lane < 18:
                                    new_product[lane] = (
                                        activation_pipe
                                        * response_weights[lane])
                        product_pipe = new_product
                        product_valid = new_product_valid
                        response_weights = issue_weights
                        response_valid = True
                        activation_pipe = activation
                        activation_valid = True

                # These fixed bubbles drain the response/product pipeline; no
                # loop bound or event depends on activation or weight values.
                self._record("conv_pipeline_drain", stage=1,
                             layer=layer_index, output_position=position,
                             output_base=output_base,
                             product_valid=int(product_valid),
                             product_values=list(product_pipe),
                             accumulator_values=list(accumulators))
                if product_valid:
                    for lane in range(self.mac_lanes):
                        if output_base + lane < 18:
                            accumulators[lane] += product_pipe[lane]
                product_pipe = [
                    activation_pipe * response_weights[lane]
                    if output_base + lane < 18 else 0
                    for lane in range(self.mac_lanes)]
                product_valid = response_valid and activation_valid
                activation_valid = False
                response_valid = False

                self._record("conv_pipeline_drain", stage=2,
                             layer=layer_index, output_position=position,
                             output_base=output_base,
                             product_valid=int(product_valid),
                             product_values=list(product_pipe),
                             accumulator_values=list(accumulators))
                if product_valid:
                    for lane in range(self.mac_lanes):
                        if output_base + lane < 18:
                            accumulators[lane] += product_pipe[lane]
                product_pipe = [0] * self.mac_lanes
                product_valid = False

                written = []
                for lane in range(self.mac_lanes):
                    output_channel = output_base + lane
                    if output_channel >= 18:
                        continue
                    bound = int(metadata["accumulator_bounds"][output_channel])
                    if abs(accumulators[lane]) > bound:
                        self.overflow = True
                    destination[output_channel, position] = self._requantize_relu(
                        accumulators[lane],
                        metadata["accumulator_exponents"][output_channel],
                        metadata["output_exponent"])
                    written.append(int(destination[output_channel, position]))
                self._record(
                    "conv_requantize_prepare", layer=layer_index,
                    output_position=position, output_base=output_base,
                    product_valid=int(product_valid),
                    product_values=list(product_pipe),
                    accumulator_values=list(accumulators),
                    prepared_values=written)
                self._record(
                    "conv_requantize_write", layer=layer_index,
                    output_position=position, output_base=output_base,
                    product_valid=int(product_valid),
                    product_values=list(product_pipe),
                    accumulator_values=list(accumulators),
                    destination_addresses=[channel * 32 + position
                                           for channel in range(output_base,
                                               min(output_base + self.mac_lanes, 18))],
                    written_values=written)
        return destination

    def _run_pooling(self, source):
        """Execute average, maximum, and last-position branches in 34 cycles."""

        sums = np.zeros(18, dtype=np.int64)
        maxima = np.zeros(18, dtype=np.int64)
        endpoints = np.zeros(18, dtype=np.int64)
        self._record("pool_init")
        for position in range(32):
            for channel in range(18):
                value = int(source[channel, position])
                sums[channel] += value
                maxima[channel] = max(int(maxima[channel]), value)
                if position == 31:
                    endpoints[channel] = value
            self._record("pool_update", output_position=position,
                         source_address=position)
        averages = np.asarray([
            round_right_shift_ties_even_scalar(value, 5) for value in sums
        ], dtype=np.int64)
        summary = np.concatenate((averages, maxima, endpoints))
        self._record("pool_finalize", summary_order="average,maximum,endpoint")
        return sums, averages, maxima, endpoints, summary

    def _run_classifier(self, summary):
        """Execute the registered-product classifier and final scale alignment."""

        weights = self.tensors["classifier.weights"]
        biases = self.tensors["classifier.bias"]
        metadata = self.selected["classifier"]
        accumulators = [int(biases[0]), int(biases[1])]
        self._record("classifier_bias_init")
        product_pipe = [0, 0]
        product_valid = False
        for feature in range(54):
            value = int(summary[feature])
            next_cycle = self.cycle + 1
            self._record("classifier_mac", summary_address=feature,
                         weight_address=feature,
                         product_valid=int(product_valid),
                         product_values=list(product_pipe),
                         accumulator_values=list(accumulators),
                         mac_issue_cycle=next_cycle,
                         mac_retire_cycle=next_cycle + 1)
            if product_valid:
                accumulators[0] += product_pipe[0]
                accumulators[1] += product_pipe[1]
            product_pipe = [value * int(weights[0, feature]),
                            value * int(weights[1, feature])]
            product_valid = True
        self._record("classifier_pipeline_drain",
                     product_valid=int(product_valid),
                     product_values=list(product_pipe),
                     accumulator_values=list(accumulators))
        if product_valid:
            accumulators[0] += product_pipe[0]
            accumulators[1] += product_pipe[1]
        logits = []
        for output_class in range(2):
            bound = int(metadata["accumulator_bounds"][output_class])
            if abs(accumulators[output_class]) > bound:
                self.overflow = True
            shift = (int(metadata["accumulator_exponents"][output_class])
                     - int(self.selected["classifier_output_exponent"]))
            value = int(accumulators[output_class]) << shift
            logits.append(min((1 << 31) - 1, max(-(1 << 31), value)))
        self._record("classifier_logit_prepare",
                     accumulator_values=list(accumulators))
        self._record("classifier_result", result_valid=True)
        return np.asarray(accumulators, dtype=np.int64), np.asarray(logits,
                                                                   dtype=np.int64)

    def run(self, sensor_codes, endpoint_index=31):
        """Return every RTL-visible tensor and the fixed request-to-result trace."""

        codes = np.asarray(sensor_codes, dtype=np.int64)
        if codes.shape != (32,):
            raise ValueError("one RTL snapshot must contain exactly 32 samples")
        if np.any(codes < 0) or np.any(codes > 32):
            raise ValueError("sensor code outside legal [0,32] range")
        centered = (codes - 15).reshape(1, 32)
        relu1 = self._run_convolution(1, centered)
        relu2 = self._run_convolution(2, relu1)
        relu3 = self._run_convolution(3, relu2)
        average_sum, average, maximum, endpoint, summary = self._run_pooling(relu3)
        classifier_accumulator, logits = self._run_classifier(summary)
        return {
            "endpoint_index": int(endpoint_index),
            "integer_centered_codes": centered,
            "integer_relu1": relu1,
            "integer_relu2": relu2,
            "integer_relu3": relu3,
            "integer_average_sum": average_sum,
            "integer_average": average,
            "integer_maximum": maximum,
            "integer_endpoint": endpoint,
            "integer_summary": summary,
            "integer_classifier_accumulator": classifier_accumulator,
            "integer_logits": logits,
            "integer_logit_difference": int(logits[1]) - int(logits[0]),
            "integer_decision": int(logits[1] > logits[0]),
            "numeric_overflow": self.overflow,
            "latency_cycles": self.cycle,
            "trace": self.trace,
        }


def _bound_package(config_path):
    """Resolve and authenticate the package named by the checked-in RTL config."""

    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    power_macro_root = config_path.parents[3]
    package_root = power_macro_root.parent / config["task1_binding"]["package_root"]
    return load_parameter_package(
        package_root, config["task1_binding"]["manifest_sha256"],
        config["task1_binding"]["quantization_config_sha256"])


def main():
    """Generate a JSON-lines trace for one JSON array of 32 sensor codes."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--window", required=True,
                        help="JSON file containing one array of 32 integer codes")
    parser.add_argument("--trace", required=True)
    parser.add_argument("--mac-lanes", type=int, default=16)
    arguments = parser.parse_args()
    codes = json.loads(Path(arguments.window).read_text(encoding="utf-8"))
    result = CnnCycleModel(_bound_package(arguments.config),
                           arguments.mac_lanes, capture_trace=True).run(codes)
    with Path(arguments.trace).open("w", encoding="utf-8") as stream:
        for row in result["trace"]:
            stream.write(json.dumps(row, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
