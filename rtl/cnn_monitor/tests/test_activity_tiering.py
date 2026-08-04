"""Deterministic acceptance tests for task-three measured-activity tiering."""

import json
import tempfile
import unittest
from pathlib import Path

from power_macro.rtl.cnn_monitor.scripts.analyze_activity_codebook_v2 import (
    TieringError,
    parse_vcd,
    tier_candidates,
)


CNN_ROOT = Path(__file__).resolve().parents[1]


def _records(values):
    """Create minimal measured candidates without using family names as inputs."""
    return [
        {"pattern_id": "p{:02d}".format(index), "family": "synthetic",
         "repeat_cv": 0.0, "total_toggle_count": value}
        for index, value in enumerate(values)
    ]


class ActivityTieringTest(unittest.TestCase):
    """Lock the failure behavior that replaced forced equal-count tiers."""

    def setUp(self):
        self.config = json.loads((CNN_ROOT / "config" / "cnn_activity_power_config_v2.json").read_text())

    def test_clear_three_tiers_pass_independent_of_input_order(self):
        """Actual values, not input ordering, define the stable partition."""
        values = [100, 102, 104, 150, 152, 154, 220, 222, 224]
        first = tier_candidates(_records(values), self.config, "total_toggle_count")
        second = tier_candidates(reversed(_records(values)), self.config, "total_toggle_count")
        self.assertEqual(first, second)
        self.assertEqual(set(first.values()), {"low", "medium", "high"})

    def test_two_tiers_and_small_separation_fail(self):
        """The analyzer must not invent a third tier from a continuous cluster."""
        with self.assertRaises(TieringError):
            tier_candidates(_records([100, 101, 102, 103, 104, 105, 160, 161, 162]),
                            self.config, "total_toggle_count")
        with self.assertRaises(TieringError):
            tier_candidates(_records([100, 101, 102, 104, 105, 106, 108, 109, 110]),
                            self.config, "total_toggle_count")

    def test_cv_and_minimum_membership_fail(self):
        """Repeatability and membership are hard gates before clustering succeeds."""
        unstable = _records([100, 102, 104, 150, 152, 154, 220, 222, 224])
        unstable[0]["repeat_cv"] = 0.0011
        with self.assertRaises(TieringError):
            tier_candidates(unstable, self.config, "total_toggle_count")
        with self.assertRaises(TieringError):
            tier_candidates(_records([100, 150, 220]), self.config, "total_toggle_count")

    def test_vcd_initial_x_is_not_activity_but_late_x_is_a_failure(self):
        """Accept initialization/dumpoff X while rejecting a measured late X.

        This compact fixture mirrors a normal VCD initialization: a signal is
        X before reset establishes zero.  A second X after known data is a
        genuine observability failure and must remain visible to the Stage-1
        codebook gate.
        """
        prefix = (
            "$scope module tb $end\n"
            "$var reg 1 ! clk $end\n"
            "$var wire 1 \" data $end\n"
            "$upscope $end\n"
            "$enddefinitions $end\n"
            "#0\n"
            "0!\n"
            "x\"\n"
            "#1\n"
            "1!\n"
            "0\"\n"
            "#2\n"
            "0!\n"
            "1\"\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "initialization.vcd"
            path.write_text(prefix, encoding="ascii")
            self.assertFalse(parse_vcd(path)["unknown_state_seen"])
            path.write_text(prefix + "#3\n0!\nx\"\n", encoding="ascii")
            self.assertTrue(parse_vcd(path)["unknown_state_seen"])
            path.write_text(
                prefix + "$dumpoff\nx\"\n$end\n", encoding="ascii"
            )
            self.assertFalse(parse_vcd(path)["unknown_state_seen"])
