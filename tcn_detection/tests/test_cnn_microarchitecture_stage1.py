#!/usr/bin/env python3
"""End-to-end contract tests for the Stage 1 software-only search."""

from __future__ import print_function

import json
import unittest
from pathlib import Path

from power_macro.tcn_detection.microarchitecture.cycle_model import (
    estimate_candidate)
from power_macro.tcn_detection.microarchitecture.dependency import (
    validate_replay_and_shift)
from power_macro.tcn_detection.microarchitecture.package import load_package
from power_macro.tcn_detection.microarchitecture.publish import (
    CANDIDATE_ROW_FIELDS, _compact_candidates_payload)
from power_macro.tcn_detection.microarchitecture.search import run_search
from power_macro.tcn_detection.microarchitecture.storage import describe_storage


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "power_macro" / "tcn_detection" / "config" / "cnn_microarchitecture_stage1_v1.json"


class CnnMicroarchitectureStage1Test(unittest.TestCase):
    """Protect the model binding and every Stage 1 decision input."""

    @classmethod
    def setUpClass(cls):
        cls.package = load_package()
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        cls.spec = {
            "mac_count": 128,
            "output_channel_parallel": 16,
            "position_parallel": 1,
            "fan_in_parallel": 8,
            "weight_bank_count": 16,
            "weight_read_width": 8,
        }

    def test_frozen_package_has_the_compressed_shapes_and_widths(self):
        """Reject accidental reuse of the historical 18/18/18 package."""

        self.assertEqual([tuple(layer["weights"].shape)
                          for layer in self.package["layers"]],
                         [(18, 1, 5), (8, 18, 5), (18, 8, 5)])
        self.assertEqual([tuple(layer["bias"].shape)
                          for layer in self.package["layers"]],
                         [(18, 32), (8,), (18,)])
        self.assertEqual([layer["accumulator_width"]
                          for layer in self.package["layers"]], [14, 20, 19])
        self.assertEqual(self.package["classifier"]["accumulator_width"], 19)

    def test_integer_replay_matches_all_exported_golden_windows(self):
        """Dependency conclusions must be grounded in the frozen integer trace."""

        result = validate_replay_and_shift(self.package)
        self.assertEqual(result["golden_windows_verified"], 8)
        self.assertEqual(result["affected_position_counts"], {
            "conv1": 32, "conv2": 32, "conv3": 32, "pool": 32})
        self.assertTrue(result["mode_b_exact"])
        self.assertFalse(result["mode_b_reduces_work"])

    def test_cycle_model_counts_all_model_macs_and_banks_limit_latency(self):
        """Exercise total work, II guard, and a real single-bank bottleneck."""

        wide = estimate_candidate(self.package, self.spec,
                                  self.config["nominal_schedule"])
        narrow_spec = dict(self.spec)
        narrow_spec.update({"weight_bank_count": 1, "weight_read_width": 1})
        narrow = estimate_candidate(self.package, narrow_spec,
                                    self.config["nominal_schedule"])
        self.assertEqual(wide["useful_macs"], 49068)
        self.assertEqual(wide["initiation_interval_cycles"],
                         wide["total_latency_cycles"] + 1)
        self.assertGreater(narrow["total_latency_cycles"],
                           wide["total_latency_cycles"])
        self.assertGreater(wide["memory_bandwidth"][
            "peak_weight_words_per_issue"], 0)

    def test_storage_uses_exact_exported_words_and_bias_widths(self):
        """Ensure Conv1's large position bias cannot disappear from estimates."""

        storage = describe_storage(self.package, self.spec)
        self.assertEqual(storage["conv_weight_storage"]["total_words"], 1530)
        self.assertEqual(sum(storage["conv_weight_storage"]["bank_entries"]),
                         1530)
        self.assertEqual(storage["bias_storage"]["total_bits"], 8604)
        self.assertEqual(storage["requant_storage"]["shift_entries"], 46)
        self.assertEqual(storage["total_parameter_bits"], 22008)

    def test_full_search_is_complete_feasible_and_json_serialisable(self):
        """Run every required MAC count and validate deterministic gate inputs."""

        result = run_search(CONFIG)
        self.assertEqual(result["candidate_count"], 8475)
        self.assertEqual(sorted(set(candidate["mac_count"]
                                    for candidate in result["candidates"])),
                         [16, 32, 64, 128])
        self.assertTrue(all(candidate["incremental_matches_full"]
                            for candidate in result["candidates"]))
        self.assertEqual(result["status"], "SELECTED")
        selected = result["selection"]["selected"]
        self.assertLessEqual(selected["total_latency_cycles"],
                             result["selection"]["budget_cycles"])
        self.assertLessEqual(selected["initiation_interval_cycles"],
                             result["selection"]["budget_cycles"])
        self.assertIn(selected["candidate_id"],
                      set(item["candidate_id"] for item in result["candidates"]))
        compact = _compact_candidates_payload(dict(result,
                                                   source_git_commit="test"))
        self.assertEqual(compact["candidate_count"], 8475)
        self.assertEqual(compact["candidate_row_fields"],
                         list(CANDIDATE_ROW_FIELDS))
        self.assertEqual(len(compact["candidate_rows"]), 8475)
        self.assertTrue(compact["dataflow_comparison"][
            "full_window_and_incremental_match_for_all_candidates"])
        self.assertEqual(compact["selection"]["selected_candidate_id"],
                         selected["candidate_id"])
        json.dumps(compact, sort_keys=True)


if __name__ == "__main__":
    unittest.main()
