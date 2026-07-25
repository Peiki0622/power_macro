#!/usr/bin/env python3
"""Regression tests for the direct 765 MHz voltage-droop-to-code experiment."""

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
PHASE2_ROOT = ROOT / "power_macro" / "delay_chain" / "phase2_vernier"
SCRIPT_DIR = PHASE2_ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import generate_vernier_deck  # noqa: E402  # Verify the dynamic source on the real topology.
import run_dff_sweep  # noqa: E402  # Verify that calibrated crossings are not offset twice.
import run_voltage_code_pwl  # noqa: E402  # Verify declared PWL cases.
import run_voltage_code_sweep  # noqa: E402  # Verify grid, calibration, and row gates.


class VoltageCodeSweepTests(unittest.TestCase):
    """Protect the experiment definition before a 303-deck HSPICE run starts."""

    @classmethod
    def setUpClass(cls):
        """Load the authoritative 765 MHz configuration once for all test cases."""

        cls.config = json.loads((PHASE2_ROOT / "phase2_config.json").read_text(encoding="utf-8"))

    def test_static_grid_has_301_regular_points_and_two_exact_extra_anchors(self):
        """Anchors must survive the grid without pretending they are 0.5 mV values."""

        points = run_voltage_code_sweep.voltage_points(self.config)
        self.assertEqual(len(points), 303)
        self.assertAlmostEqual(points[0], 1.1, places=12)
        self.assertAlmostEqual(points[-1], 0.95, places=12)
        for anchor in self.config["phase1_anchor_voltages_v"]:
            self.assertTrue(any(abs(point - anchor) <= 1.0e-12 for point in points))

    def test_calibrated_candidate_matches_measured_cal_sel_two_contract(self):
        """The voltage curve must use the recorded M=32/dummy=1/20 ps baseline."""

        point_candidate = run_voltage_code_sweep.candidate(self.config)
        self.assertEqual(point_candidate["m_stages"], 32)
        self.assertEqual(point_candidate["dummy_load_count"], 1)
        self.assertAlmostEqual(point_candidate["launch_offset_s"], 20.0e-12, places=24)

    def test_decode_row_preserves_raw_code_when_majority_correction_changes_transition(self):
        """A corrected bubble must still retain raw anomaly evidence for quality logic."""

        raw_row = {
            "raw_code": "010111",
            "sensor_code": 1,
            "vdd_a_v": 1.05,
        }
        decoded = run_voltage_code_sweep.decode_row(self.config, raw_row, 2)
        self.assertEqual(decoded["raw_code"], "010111")
        self.assertEqual(decoded["raw_sensor_code"], 1)
        self.assertNotEqual(decoded["corrected_code"], decoded["raw_code"])
        self.assertEqual(decoded["raw_bubble_count"], 1)
        self.assertTrue(decoded["code_valid"])

    def test_pwl_decks_keep_reference_dff_domain_and_track_sense_supply_after_launch(self):
        """PWL must not leave a fixed 1.1 V START_SENSE overdriving VDD_A."""

        for item in run_voltage_code_pwl.pwl_cases(self.config):
            deck = generate_vernier_deck.render_dff_pwl_deck(self.config, 32, 1, 20.0e-12, item["pwl_points"])
            self.assertIn("V_VDD_A vdd_a vss_a PWL(", deck)
            self.assertIn("V_START_SENSE start_sense vss_a PWL(", deck)
            self.assertNotIn("V_START_SENSE start_sense vss_a PULSE", deck)
            self.assertIn("XCOMP_000 raw_q_000 vdd_ref vss_ref sense_000 ref_000 sensor_reset PHASE2_COMPARATOR", deck)
            self.assertIn("vdd_a_at_capture_v", deck)

    def test_metastability_distance_uses_measured_crossings_without_double_offset(self):
        """A 20 ps calibrated launch must not be added again to the SPICE crossing."""

        measurements = {
            "q_000_reset_level": 0.0,
            "q_000_level": 1.1,
            "sense_000_cross": 1.020e-9,
            "ref_000_cross": 1.021e-9,
            "q_000_rise": 1.030e-9,
        }
        result = run_dff_sweep.parse_bits(
            measurements,
            m_stages=1,
            vdd_ref_v=1.1,
            launch_offset_s=20.0e-12,
            risk_margin_s=2.0e-12,
        )
        self.assertEqual(result["metastability_risk_count"], 1)


if __name__ == "__main__":
    unittest.main()
