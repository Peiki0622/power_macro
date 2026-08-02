#!/usr/bin/env python3
"""Static contract tests for the real-window CNN RTL configuration."""

from __future__ import print_function

import hashlib
import json
import math
import re
import unittest
from pathlib import Path


CNN_ROOT = Path(__file__).resolve().parents[1]
POWER_MACRO_ROOT = CNN_ROOT.parents[1]
CONFIG = CNN_ROOT / "config" / "cnn_rtl_config_v1.json"


class CnnRtlContractTest(unittest.TestCase):
    """Lock architectural choices before the datapath is implemented."""

    def setUp(self):
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))

    def expected_cycles(self, lanes):
        """Calculate the fixed controller schedule from loop dimensions."""

        groups = int(math.ceil(18.0 / int(lanes)))
        # Every output group has one bias edge, one issue per fan-in,
        # two fixed ROM/product drain edges, and separate requantize prepare
        # and write edges.  Pooling and classifier retain their independently
        # frozen 34- and 58-cycle budgets.
        conv1 = 32 * groups * (1 + 5 + 2 + 1 + 1)
        conv2_or_3 = 32 * groups * (1 + 90 + 2 + 1 + 1)
        pooling = 1 + 32 + 1
        classifier = 1 + 54 + 1 + 1 + 1
        return conv1 + 2 * conv2_or_3 + pooling + classifier

    def test_release_schedule_is_fixed_and_internally_consistent(self):
        """Release latency and II must match the declared 16-lane loops."""

        self.assertEqual(self.config["release_mac_lanes"], 16)
        self.assertEqual(self.config["supported_mac_lanes"], [4, 8, 16])
        latency = self.expected_cycles(self.config["release_mac_lanes"])
        self.assertEqual(latency, 12892)
        self.assertEqual(self.config["schedule"]["release_latency_cycles"],
                         latency)
        self.assertEqual(
            self.config["schedule"]["release_initiation_interval_cycles"],
            latency + 1)

    def test_task1_package_binding_is_exact(self):
        """RTL must consume the already accepted task-one numeric package."""

        binding = self.config["task1_binding"]
        package = POWER_MACRO_ROOT.parent / binding["package_root"]
        manifest = package / "manifest.json"
        quantization = package / "quantization_config.json"
        self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(),
                         binding["manifest_sha256"])
        self.assertEqual(hashlib.sha256(quantization.read_bytes()).hexdigest(),
                         binding["quantization_config_sha256"])
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(payload["checkpoint_sha256"],
                         binding["checkpoint_sha256"])
        self.assertEqual(payload["selected_candidate"], "w8_a8")

    def test_interface_and_numeric_widths_are_explicit(self):
        """No interface or arithmetic width may acquire an implementation default."""

        interface = self.config["interface"]
        numeric = self.config["numeric"]
        self.assertEqual(interface["request_policy"],
                         "explicit_ready_valid_snapshot")
        self.assertEqual(interface["same_cycle_sample_request"],
                         "include_accepted_sample_when_window_already_full")
        self.assertEqual(
            [numeric["conv1_accumulator_bits"],
             numeric["conv2_accumulator_bits"],
             numeric["conv3_accumulator_bits"],
             numeric["classifier_accumulator_bits"]],
            [14, 20, 20, 20])
        self.assertEqual(numeric["logit_bits"], 32)
        self.assertEqual(numeric["logit_difference_bits"], 33)

    def test_synthesis_rtl_has_no_forbidden_runtime_constructs(self):
        """Release RTL must remain self-contained and fully synthesizable.

        Testbench constructs are intentionally outside this scan.  Anchoring
        procedural keywords at the beginning of a source line avoids treating
        explanatory comments as executable code while still detecting normal
        SystemVerilog declarations after indentation.
        """

        rtl_files = list((CNN_ROOT / "rtl").glob("*.sv"))
        rtl_files += list((CNN_ROOT / "rtl" / "generated").glob("*.sv"))
        combined = "\n".join(path.read_text(encoding="ascii")
                             for path in rtl_files)
        self.assertIsNone(re.search(r"(?m)^\s*function\b", combined))
        self.assertIsNone(re.search(r"(?m)^\s*initial\b", combined))
        self.assertNotIn("$readmem", combined)

    def test_large_data_arrays_are_write_before_read_not_reset(self):
        """Reset may initialize controls but not the four bulk data arrays."""

        convolution = (CNN_ROOT / "rtl" / "cnn_convolution_engine.sv").read_text(
            encoding="ascii")
        window = (CNN_ROOT / "rtl" / "cnn_window_buffer.sv").read_text(
            encoding="ascii")
        convolution_reset = convolution.split(
            "if (reset) begin", 1)[1].split("end else begin", 1)[0]
        window_reset = window.split(
            "if (reset) begin", 1)[1].split("end else begin", 1)[0]
        for array_name in ("feature_bank_b", "final_features"):
            self.assertNotRegex(
                convolution_reset,
                r"{}\s*\[.*\]\s*<=".format(array_name))
        for array_name in ("circular_buffer", "snapshot"):
            self.assertNotRegex(
                window_reset,
                r"{}\s*\[.*\]\s*<=".format(array_name))

    def test_feature_storage_and_multiplier_structure_is_locked(self):
        """Lock two feature banks and timing-safe multiplier operand cones."""

        convolution = (CNN_ROOT / "rtl" / "cnn_convolution_engine.sv").read_text(
            encoding="ascii")
        self.assertNotIn("feature_bank_a", convolution)
        self.assertEqual(len(re.findall(
            r"logic \[7:0\] feature_bank_b \[0:575\]", convolution)), 1)
        self.assertEqual(len(re.findall(
            r"output logic \[7:0\]\s+final_features \[0:575\]",
            convolution)), 1)
        # The single procedural convolution product capture must consume the
        # generated lane_weight wire.  The release branch maps that wire with a
        # constant packed slice, while the named compatibility branch retains
        # dynamic selection only for supported 4/8-lane configurations.  These
        # checks prevent a source refactor from silently placing output_base's
        # packed-word decoder back in front of all sixteen multipliers.
        self.assertEqual(len(re.findall(
            r"activation_pipe\s*\n\s*\* \$signed\(lane_weight\[lane\]\)",
            convolution)), 1)
        self.assertIn("g_release_static_lane_slice", convolution)
        self.assertIn("g_compatible_dynamic_lane_slice", convolution)
        self.assertIn("rom_weight_word[(generated_lane * 8) +: 8]",
                      convolution)
        self.assertIn("logic [6:0] packed_shift_bit_index", convolution)
        self.assertIn("logic [8:0] packed_bias_bound_bit_index", convolution)
        self.assertIn("logic [79:0]  registered_lane_right_shifts", convolution)
        self.assertIn(
            "registered_lane_right_shifts <= rom_lane_right_shifts",
            convolution)
        self.assertIn("for (write_channel = 0; write_channel < 18;",
                      convolution)
        self.assertIn("for (write_position = 0; write_position < 32;",
                      convolution)
        self.assertNotIn("{(prepared_output_base + lane), 5'b00000}",
                         convolution)

        # The classifier's summary/weight decoders must terminate at the small
        # operand-prefetch registers rather than feeding either signed
        # multiplier in the same cycle.  This assertion locks the structural
        # timing boundary while the end-to-end VCS regression checks ordering.
        classifier = (CNN_ROOT / "rtl" / "cnn_pool_classifier.sv").read_text(
            encoding="ascii")
        self.assertEqual(classifier.count(
            "$signed({1'b0, classifier_feature_operand})"), 2)
        self.assertNotRegex(
            classifier,
            r"\$signed\(\{1'b0, summary_features\[summary_index\]\}\)\s*\*")

        # ROM address arithmetic must use constant selects/shift-adds, and the
        # window path must never reintroduce 32 separate rotate muxes.
        address_block = convolution.split(
            "rom_read_enable =", 1)[1].split("cnn_weight_rom weight_rom", 1)[0]
        self.assertNotIn("*", address_block)
        window = (CNN_ROOT / "rtl" / "cnn_window_buffer.sv").read_text(
            encoding="ascii")
        self.assertNotRegex(window, r"%\s*32")
        self.assertNotIn("write_pointer + index", window)

    def test_every_synthesis_port_has_an_inline_interface_comment(self):
        """Each port declaration must document its hardware interface role."""

        rtl_files = list((CNN_ROOT / "rtl").glob("*.sv"))
        rtl_files += list((CNN_ROOT / "rtl" / "generated").glob("*.sv"))
        missing = []
        for path in rtl_files:
            for line_number, line in enumerate(
                    path.read_text(encoding="ascii").splitlines(), 1):
                if re.match(r"\s*(input|output|inout)\s", line):
                    if "//" not in line:
                        missing.append("{}:{}".format(path.name, line_number))
        self.assertEqual(missing, [], "ports without comments: {}".format(
            ", ".join(missing)))


if __name__ == "__main__":
    unittest.main()
