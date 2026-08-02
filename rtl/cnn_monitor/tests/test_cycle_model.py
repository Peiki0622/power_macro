#!/usr/bin/env python3
"""Golden and schedule tests for the independent cycle-accurate model."""

from __future__ import print_function

import csv
import json
import unittest
from pathlib import Path

import numpy as np

from power_macro.rtl.cnn_monitor.model.cycle_model import (
    CnnCycleModel, _bound_package, round_right_shift_ties_even_scalar)


CNN_ROOT = Path(__file__).resolve().parents[1]
POWER_MACRO_ROOT = CNN_ROOT.parents[1]
CONFIG = CNN_ROOT / "config" / "cnn_rtl_config_v1.json"
TASK1 = (POWER_MACRO_ROOT / "tcn_detection" / "runs"
         / "formal_v1_20260727_r1" / "fixed_point"
         / "multistat_w18_k5_v1_20260801_r1")


class CycleModelTest(unittest.TestCase):
    """Prove cycle state, addresses, and results against task-one artifacts."""

    @classmethod
    def setUpClass(cls):
        cls.package = _bound_package(CONFIG)
        cls.golden = np.load(TASK1 / "golden" / "expected_layer_outputs.npz")
        cls.windows = [json.loads(line) for line in (
            TASK1 / "golden" / "windows.jsonl").read_text(
                encoding="utf-8").splitlines()]

    def test_signed_ties_even_matches_both_midpoint_directions(self):
        """Hardware-oriented scalar rounding must cover positive and negative ties."""

        values = [-7, -6, -5, -3, -2, -1, 1, 2, 3, 5, 6, 7]
        expected = [-4, -3, -2, -2, -1, 0, 0, 1, 2, 2, 3, 4]
        self.assertEqual([round_right_shift_ties_even_scalar(value, 1)
                          for value in values], expected)

    def test_all_task_one_golden_windows_match_every_rtl_visible_tensor(self):
        """All eight audited windows must match layers, summaries, and logits."""

        keys = ("integer_centered_codes", "integer_relu1", "integer_relu2",
                "integer_relu3", "integer_average_sum", "integer_average",
                "integer_maximum", "integer_endpoint", "integer_summary",
                "integer_classifier_accumulator", "integer_logits",
                "integer_logit_difference", "integer_decision")
        for index, window in enumerate(self.windows):
            result = CnnCycleModel(self.package, 16, capture_trace=False).run(
                window["sensor_codes"], endpoint_index=window["end_index"])
            for key in keys:
                observed = np.asarray(result[key])
                expected = np.asarray(self.golden[key][index])
                self.assertTrue(np.array_equal(observed, expected),
                                "{} differs for {}".format(key,
                                                           window["window_id"]))
            self.assertFalse(result["numeric_overflow"])
            self.assertEqual(result["latency_cycles"], 12892)

    def test_trace_has_fixed_event_counts_and_monotonic_issue_retire(self):
        """Trace structure must expose every fixed controller state and address."""

        result = CnnCycleModel(self.package, 16, capture_trace=True).run(
            self.windows[0]["sensor_codes"])
        trace = result["trace"]
        self.assertEqual([row["cycle"] for row in trace],
                         list(range(1, 12893)))
        counts = {}
        for row in trace:
            counts[row["event"]] = counts.get(row["event"], 0) + 1
            if row["event"] == "conv_rom_issue":
                self.assertEqual(row["mac_issue_cycle"], row["cycle"])
                self.assertEqual(row["rom_response_cycle"], row["cycle"] + 1)
                self.assertEqual(row["mac_retire_cycle"], row["cycle"] + 2)
            elif row["event"] == "classifier_mac":
                self.assertEqual(row["mac_issue_cycle"], row["cycle"])
                self.assertEqual(row["mac_retire_cycle"], row["cycle"] + 1)
        self.assertEqual(counts, {
            "conv_bias_init": 192,
            # Conv1 issues 32*2*5=320 reads; Conv2 and Conv3 each issue
            # 32*2*90=5,760.  Two drain and two requantization events wrap
            # every one of the 192 fixed output groups.
            "conv_rom_issue": 11840,
            "conv_pipeline_drain": 384,
            "conv_requantize_prepare": 192,
            "conv_requantize_write": 192,
            "pool_init": 1,
            "pool_update": 32,
            "pool_finalize": 1,
            "classifier_bias_init": 1,
            "classifier_mac": 54,
            "classifier_pipeline_drain": 1,
            "classifier_logit_prepare": 1,
            "classifier_result": 1,
        })
        self.assertTrue(trace[-1]["result_valid"])

    def test_compiled_rom_addresses_cover_only_authenticated_weight_words(self):
        """All requests must follow the frozen 0..369 physical ROM map."""

        trace = CnnCycleModel(self.package, 16, capture_trace=True).run(
            self.windows[0]["sensor_codes"])["trace"]
        addresses = {1: set(), 2: set(), 3: set()}
        for row in trace:
            if row["event"] == "conv_rom_issue":
                addresses[row["layer"]].add(row["weight_address"])
        self.assertEqual(addresses[1], set(range(0, 10)))
        self.assertEqual(addresses[2], set(range(10, 190)))
        self.assertEqual(addresses[3], set(range(190, 370)))

    def test_requantization_midpoints_and_saturation_boundaries(self):
        """Exercise every remainder around ties and both ReLU clamp edges.

        For each legal shift, four adjacent floor quotients cover even/odd and
        positive/negative behavior.  Every possible remainder is checked, so
        below-half, exact-half, and above-half cases cannot be skipped.  The
        resulting values are also passed through the RTL-equivalent 0..127
        clamp to cover negative ReLU and positive saturation boundaries.
        """

        model = CnnCycleModel(self.package, 16, capture_trace=False)
        shifts = set()
        for layer in self.package["selected"]["layers"]:
            shifts.update(int(layer["output_exponent"])
                          - int(exponent) for exponent in
                          layer["accumulator_exponents"])
        observed_clamps = set()
        for shift in shifts:
            denominator = 1 << shift
            # Quotient zero is required to cover the 0-to-1 rounding edge;
            # negative values cover ReLU, while 126/127 cover the positive
            # saturation boundary.
            for quotient in (-2, -1, 0, 126, 127):
                for remainder in range(denominator):
                    value = quotient * denominator + remainder
                    rounded = round_right_shift_ties_even_scalar(value, shift)
                    expected = quotient + int(
                        remainder > denominator // 2
                        or (remainder == denominator // 2
                            and (quotient & 1)))
                    self.assertEqual(rounded, expected)
                    observed_clamps.add(min(127, max(0, rounded)))
        self.assertTrue({0, 1, 126, 127}.issubset(observed_clamps))

    def test_csv_logits_are_identical_not_merely_same_decision(self):
        """The package CSV provides a second serialized check of final INT32 values."""

        with (TASK1 / "golden" / "expected_logits.csv").open(
                newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        for window, row in zip(self.windows, rows):
            result = CnnCycleModel(self.package, 16, capture_trace=False).run(
                window["sensor_codes"])
            self.assertEqual(result["integer_logits"].tolist(), [
                int(row["integer_logit_safe"]),
                int(row["integer_logit_critical"]),
            ])


if __name__ == "__main__":
    unittest.main()
