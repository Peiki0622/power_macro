"""Zero-HSPICE regression tests for the FTC T0 transient contracts.

These tests check renderer structure, input reuse, waveform legality, and
terminal STOP evidence.  They never substitute for the retained HSPICE
scenarios in ``delay_chain/ftc/runs/t0_transient_droop``.
"""

import csv
import json
import os
import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_t0_transient_droop_characterization as study  # noqa: E402


class T0TransientDroopTests(unittest.TestCase):
    """Protect the T0 physical and evidence contracts without new simulation."""

    @classmethod
    def setUpClass(cls):
        if os.environ.get("CONDA_DEFAULT_ENV") != "DL":
            raise unittest.SkipTest("T0 tests require the DL environment")
        cls.context = study.frozen_context()

    def test_contract_has_only_formal_baselines_and_margins(self):
        contract = study.contract()
        self.assertEqual(contract["formal_scope"]["baseline_vdd_v"], [0.95, 1.1])
        self.assertEqual(contract["formal_scope"]["margin_levels"], ["L1", "L2", "L3"])
        self.assertEqual(contract["formal_scope"]["formal_minimum_vdd_v"], 0.8)
        self.assertTrue(contract["waveform"]["zero_time_voltage_jump_forbidden"])

    def test_codebook_matches_m1_entries(self):
        expected = {
            (0.95, "L1"): (4, 9), (0.95, "L2"): (5, 6), (0.95, "L3"): (5, 9),
            (1.10, "L1"): (2, 10), (1.10, "L2"): (3, 8), (1.10, "L3"): (3, 10),
        }
        self.assertEqual(study.FORMAL_CODES, expected)
        self.assertEqual(study.FORMAL_CODES[(1.10, "L1")][1], 10)

    def test_pwl_rejects_zero_slope_and_zero_hold(self):
        with self.assertRaises(ValueError):
            study.droop_points(0.95, 0.85, 1e-12, 0.0, 1e-9, 1e-12, 8e-9)
        with self.assertRaises(ValueError):
            study.droop_points(0.95, 0.85, 1e-12, 1e-12, 0.0, 1e-12, 8e-9)

    def test_rendered_dff_ports_and_real_topology_are_preserved(self):
        parameters = study.parameters_for(0.95, "L2", 0.85, 3000.0, 0.0)
        deck = study.render_deck(self.context, parameters)
        checks = study.topology_checks(deck, parameters)
        self.assertTrue(all(checks.values()), checks)
        self.assertIn("XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset DFFRPQ_X0P5M_A9TR40", deck)
        self.assertEqual(sum(line.startswith("V_M_") for line in deck.splitlines()), 16)
        self.assertEqual(sum(line.startswith("V_F_") for line in deck.splitlines()), 10)

    def test_static_trip_rows_use_nearest_q0_from_original_sweep(self):
        rows = study.static_trip_rows()
        by_key = {(float(row["baseline_vdd_v"]), row["margin_level"]): row for row in rows}
        self.assertEqual(by_key[(0.95, "L1")]["last_q0_v"], 0.89)
        self.assertEqual(by_key[(0.95, "L2")]["last_q0_v"], 0.87)
        self.assertEqual(by_key[(0.95, "L3")]["last_q0_v"], 0.84)
        self.assertEqual(by_key[(1.10, "L1")]["last_q0_v"], 1.02)
        self.assertEqual(by_key[(1.10, "L2")]["last_q0_v"], 0.97)
        self.assertEqual(by_key[(1.10, "L3")]["last_q0_v"], 0.94)

    def test_real_dff_q_is_authoritative_over_residual(self):
        self.assertEqual(study.m0.stable_q(0.95, 0.95, 0.95), (1, "stable_high"))
        self.assertEqual(study.m0.stable_q(0.0, 0.0, 0.95), (0, "stable_low"))
        self.assertEqual(study.m0.stable_q(0.95, 0.0, 0.95), (None, "ambiguous"))

    def test_terminal_gate_and_downstream_contract_are_present(self):
        gate = json.loads((FTC_ROOT / "analysis/t0_transient_droop/reports/T0_GATE_STATUS.json").read_text())
        downstream = json.loads((FTC_ROOT / "analysis/t0_transient_droop/contract/T0_DOWNSTREAM_D0_TIMING_CONTRACT.json").read_text())
        self.assertEqual(gate["decision"], "NO-GO / STOP")
        self.assertEqual(gate["stop_stage"], "T0-2")
        self.assertFalse(downstream["below_floor_requirement"]["precise_timing_trip_allowed"])
        self.assertIsNone(downstream["runtime_probe_period"]["maximum_period_s"])


if __name__ == "__main__":
    unittest.main()
