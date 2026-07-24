#!/usr/bin/env python3
"""Unit tests for phase-1 topology generation and fixed-time code analysis.

These tests are intentionally simulator-free.  They verify the contracts that
would otherwise be easy to break with a successful-but-wrong SPICE run: exact
two-inverter unit count, positional well connections, midpoint sampling, code
monotonicity and the deterministic feasibility decision.
"""

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import analyze_dc_sweep  # noqa: E402  # Tests exercise scripts as direct CLIs do.
import generate_delay_chain  # noqa: E402


class DelayChainRenderingTests(unittest.TestCase):
    """Check that generated standard-cell SPICE lines honor the foundry ports."""

    def setUp(self):
        """Load the reviewed study configuration once for all topology tests."""

        self.config = generate_delay_chain.load_config(
            Path(__file__).resolve().parents[1] / "phase1_config.json"
        )

    def test_each_candidate_has_two_inverters_per_non_inverting_unit(self):
        """A tap must follow exactly two inversions to preserve rising polarity."""

        for units in (16, 32, 64):
            deck = generate_delay_chain.render_deck(self.config, units, 1.10)
            instance_lines = [line for line in deck.splitlines() if line.startswith("XINV_")]
            tap_measures = [line for line in deck.splitlines() if line.startswith(".measure tran tap_")]
            self.assertEqual(len(instance_lines), units * 2)
            self.assertEqual(len(tap_measures), units)

    def test_all_standard_cell_instances_tie_wells_to_local_rails(self):
        """VNW/VPW are electrical terminals and must not be omitted or swapped."""

        deck = generate_delay_chain.render_deck(self.config, 16, 1.10)
        for line in deck.splitlines():
            if line.startswith("XINV_"):
                fields = line.split()
                self.assertEqual(fields[2:6], ["vdd_a", "vdd_a", "vss_a", "vss_a"])


class FixedTimeAnalysisTests(unittest.TestCase):
    """Check code decoding and selection rules with an independently built trace."""

    @staticmethod
    def make_row(kind, voltage, unit_delay_s):
        """Create one serial 16-tap raw row whose code changes with unit delay.

        The nominal trace has 10 ps per non-inverting unit.  Increasing the
        delay shifts later crossings across the fixed nominal midpoint, which
        produces known thermometer codes without relying on HSPICE output.
        """

        row = {
            "scenario_id": "chain_16/{}".format(kind),
            "scenario_kind": kind,
            "chain_units": "16",
            "inverter_count": "32",
            "vdd_v": str(voltage),
            "stage_delay_s": str(unit_delay_s),
            "chain_delay_s": str(unit_delay_s * 16),
            "i_peak_a": "1e-5",
            "power_avg_w": "2e-6",
        }
        for index in range(16):
            row["tap_{:03d}_cross_s".format(index)] = str(1.0e-9 + (index + 1) * unit_delay_s)
        return row

    def test_midpoint_sample_and_feasibility_rules(self):
        """The test trace supplies three code steps at the violation voltage."""

        rows = [
            self.make_row("canonical_000mv", 1.10, 10.0e-12),
            self.make_row("canonical_010mv", 1.09, 12.0e-12),
            self.make_row("canonical_150mv", 0.95, 20.0e-12),
            self.make_row("first_violation", 1.092826204042, 16.0e-12),
        ]
        calibration, summary = analyze_dc_sweep.analyze_chain(rows, 1.092826204042)
        nominal = [row for row in calibration if row["scenario_kind"] == "canonical_000mv"][0]
        violation = [row for row in calibration if row["scenario_kind"] == "first_violation"][0]
        self.assertEqual(nominal["propagation_code"], 8)
        self.assertEqual(violation["propagation_code"], 5)
        self.assertEqual(summary["first_violation_code_delta"], 3)
        self.assertTrue(summary["feasible"])


if __name__ == "__main__":
    unittest.main()
