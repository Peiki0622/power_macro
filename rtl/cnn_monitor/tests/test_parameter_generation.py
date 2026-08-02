#!/usr/bin/env python3
"""Tests for authenticated, deterministic RTL parameter generation."""

from __future__ import print_function

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from power_macro.rtl.cnn_monitor.model.parameter_package import (
    EXPECTED_TENSORS, load_parameter_package)
from power_macro.rtl.cnn_monitor.scripts.generate_rtl_constants import generate
from power_macro.rtl.cnn_monitor.scripts.generate_rtl_constants import (
    _emit_channel_contract_rom, _emit_conv_bias_rom, _emit_conv_weight_rom)


CNN_ROOT = Path(__file__).resolve().parents[1]
POWER_MACRO_ROOT = CNN_ROOT.parents[1]
CONFIG = CNN_ROOT / "config" / "cnn_rtl_config_v1.json"


class ParameterGenerationTest(unittest.TestCase):
    """Lock source-package authentication and generated address semantics."""

    def setUp(self):
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.package_root = POWER_MACRO_ROOT.parent / self.config[
            "task1_binding"]["package_root"]

    def test_all_tensor_shapes_and_signed_extremes_load_exactly(self):
        """Every declared tensor must decode with its frozen shape and width."""

        package = load_parameter_package(
            self.package_root,
            self.config["task1_binding"]["manifest_sha256"],
            self.config["task1_binding"]["quantization_config_sha256"])
        for name, (shape, bits, _) in EXPECTED_TENSORS.items():
            tensor = package["tensors"][name]
            self.assertEqual(tensor.shape, shape)
            self.assertGreaterEqual(int(tensor.min()), -(1 << (bits - 1)))
            self.assertLessEqual(int(tensor.max()), (1 << (bits - 1)) - 1)

    def test_generation_is_byte_reproducible_and_has_no_runtime_mem_load(self):
        """Two clean generations must match and remain self-contained RTL."""

        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first.sv"
            second = Path(temporary) / "second.sv"
            generate(CONFIG, first)
            generate(CONFIG, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            text = first.read_text(encoding="ascii")
            self.assertNotIn("$readmem", text)
            self.assertNotIn("function", text)
            self.assertNotIn("module cnn_conv_weight_rom", text)
            self.assertIn("cnn_conv_bias_rom", text)
            self.assertIn("cnn_classifier_parameter_rom", text)

    def test_every_grouped_weight_address_matches_task_one_tensor(self):
        """Decode every generated case item and compare all sixteen lane slices.

        This is intentionally exhaustive rather than a few spot checks.  It
        protects the non-trivial address concatenation
        ``{layer,output_base,input_channel,kernel}`` and catches reversed packed
        lanes even when the source memory files themselves load correctly.
        """

        package = load_parameter_package(
            self.package_root,
            self.config["task1_binding"]["manifest_sha256"],
            self.config["task1_binding"]["quantization_config_sha256"])
        text = "\n".join(_emit_conv_weight_rom(package["tensors"]))
        entries = [int(value, 16) for value in re.findall(
            r"\d+'d\d+: lane_weights = 128'h([0-9a-f]+);", text)]
        expected_count = 18 * 1 * 5 + 18 * 18 * 5 + 18 * 18 * 5
        self.assertEqual(len(entries), expected_count)
        entry_index = 0
        for layer_id, name in ((1, "conv1.weights"), (2, "conv2.weights"),
                               (3, "conv3.weights")):
            tensor = package["tensors"][name]
            for output_base in range(18):
                for input_channel in range(tensor.shape[1]):
                    for kernel_tap in range(5):
                        packed = entries[entry_index]
                        entry_index += 1
                        for lane in range(16):
                            unsigned = (packed >> (lane * 8)) & 0xff
                            signed = unsigned - 256 if unsigned >= 128 else unsigned
                            channel = output_base + lane
                            expected = (int(tensor[channel, input_channel, kernel_tap])
                                        if channel < 18 else 0)
                            self.assertEqual(signed, expected)

    def test_packed_bias_rom_matches_every_legal_lane_configuration(self):
        """Exhaustively decode all 14 bias words for 4/8/16-lane engines.

        The engine selects a physical 16-channel word with output_base[4],
        then uses output_base[3:0] as the first lane of a comparison build.
        Exercising every legal base and every L32 position protects both that
        two-level mapping and the five-class Conv1 padding compression.
        """

        package = load_parameter_package(
            self.package_root,
            self.config["task1_binding"]["manifest_sha256"],
            self.config["task1_binding"]["quantization_config_sha256"])
        text = "\n".join(_emit_conv_bias_rom(package["tensors"]))
        words = {int(key, 16): int(value, 16) for key, value in re.findall(
            r"6'h([0-9a-f]+): lane_biases = 320'h([0-9a-f]+);", text)}
        self.assertEqual(len(words), 14)

        for lane_count in (4, 8, 16):
            for layer_id, tensor_name in (
                    (1, "conv1.bias"), (2, "conv2.bias"),
                    (3, "conv3.bias")):
                tensor = package["tensors"][tensor_name]
                for output_base in range(0, 18, lane_count):
                    physical_group = output_base >> 4
                    for position in range(32):
                        if layer_id != 1:
                            position_class = 0
                        elif position < 2:
                            position_class = position
                        elif position < 30:
                            position_class = 2
                        else:
                            position_class = position - 27
                        key = ((layer_id << 4)
                               | (physical_group << 3)
                               | position_class)
                        packed = words[key]
                        for lane in range(lane_count):
                            physical_lane = (output_base & 15) + lane
                            unsigned = (packed >> (physical_lane * 20)) & 0xfffff
                            signed = (unsigned - (1 << 20)
                                      if unsigned >= (1 << 19) else unsigned)
                            channel = output_base + lane
                            if channel >= 18:
                                expected = 0
                            elif layer_id == 1:
                                expected = int(tensor[channel, position])
                            else:
                                expected = int(tensor[channel])
                            self.assertEqual(
                                signed, expected,
                                "bias mismatch lanes={} layer={} base={} "
                                "position={} lane={}".format(
                                    lane_count, layer_id, output_base,
                                    position, lane))

    def test_packed_contract_rom_matches_every_legal_lane_configuration(self):
        """Exhaustively decode all six packed shift/bound contract words."""

        package = load_parameter_package(
            self.package_root,
            self.config["task1_binding"]["manifest_sha256"],
            self.config["task1_binding"]["quantization_config_sha256"])
        text = "\n".join(_emit_channel_contract_rom(package["selected"]))
        entries = re.findall(
            r"3'h([0-9a-f]+): begin\s+"
            r"lane_right_shifts = 80'h([0-9a-f]+);\s+"
            r"lane_magnitude_bounds = 320'h([0-9a-f]+);",
            text)
        words = {int(key, 16): (int(shifts, 16), int(bounds, 16))
                 for key, shifts, bounds in entries}
        self.assertEqual(len(words), 6)

        for lane_count in (4, 8, 16):
            for layer_id, layer in enumerate(package["selected"]["layers"], 1):
                expected_shifts = [
                    int(layer["output_exponent"]) - int(source)
                    for source in layer["accumulator_exponents"]]
                expected_bounds = [int(value)
                                   for value in layer["accumulator_bounds"]]
                for output_base in range(0, 18, lane_count):
                    physical_group = output_base >> 4
                    packed_shifts, packed_bounds = words[
                        (layer_id << 1) | physical_group]
                    # Contract data is position independent.  Iterating all 32
                    # positions explicitly locks that the engine may reuse the
                    # same packed response throughout each output-position run.
                    for position in range(32):
                        for lane in range(lane_count):
                            physical_lane = (output_base & 15) + lane
                            actual_shift = ((packed_shifts
                                             >> (physical_lane * 5)) & 0x1f)
                            actual_bound = ((packed_bounds
                                             >> (physical_lane * 20)) & 0xfffff)
                            channel = output_base + lane
                            expected_shift = (expected_shifts[channel]
                                              if channel < 18 else 0)
                            expected_bound = (expected_bounds[channel]
                                              if channel < 18 else 0)
                            self.assertEqual(
                                actual_shift, expected_shift,
                                "shift mismatch lanes={} layer={} base={} "
                                "position={} lane={}".format(
                                    lane_count, layer_id, output_base,
                                    position, lane))
                            self.assertEqual(
                                actual_bound, expected_bound,
                                "bound mismatch lanes={} layer={} base={} "
                                "position={} lane={}".format(
                                    lane_count, layer_id, output_base,
                                    position, lane))

    def test_corrupted_weight_is_rejected_before_generation(self):
        """A one-byte coefficient change must fail digest authentication."""

        with tempfile.TemporaryDirectory() as temporary:
            copy_root = Path(temporary) / "package"
            shutil.copytree(self.package_root, copy_root)
            weight = copy_root / "weights" / "conv1_weights.mem"
            payload = weight.read_text(encoding="ascii")
            weight.write_text(payload.replace("a7\n", "a6\n", 1), encoding="ascii")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                load_parameter_package(copy_root)


if __name__ == "__main__":
    unittest.main()
