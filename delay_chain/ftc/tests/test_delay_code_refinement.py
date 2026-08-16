"""Pure regressions for the FTC delay-code boundary refinement runner.

These tests intentionally never launch HSPICE.  They protect the physical
contract rendered into a deck and the bounded candidate/publication policy;
the retained raw-run directory remains the source of electrical evidence.
"""

import importlib.util
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = FTC_ROOT / "scripts" / "run_delay_code_refinement.py"
SPEC = importlib.util.spec_from_file_location("delay_code_refinement", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class DelayCodeRefinementTests(unittest.TestCase):
    """Protect only deterministic, non-electrical behavior."""

    def setUp(self):
        self.config = RUNNER.load_json(FTC_ROOT / "ftc_config.json")
        self.cells = RUNNER.load_json(FTC_ROOT / "discovery/selected_cells.json")
        self.taps = (14, 16, 18, 21, 24, 28, 30, 32)

    def test_mapping_contract_is_strictly_increasing_and_three_bit(self):
        """The candidate has exactly eight physical leaves and no duplicate tap."""

        self.assertTrue(RUNNER.mapping_is_valid(self.taps))
        self.assertFalse(RUNNER.mapping_is_valid((14, 16, 18, 21, 24, 28, 28, 32)))
        self.assertFalse(RUNNER.mapping_is_valid((14, 16, 18, 21, 24, 28, 30, 39)))

    def test_rendered_deck_keeps_frozen_sensor_mux_and_dff_ports(self):
        """The long physical deck retains every frozen load and positional port."""

        deck = RUNNER.render_deck(self.config, self.cells, 0.95, self.taps, 3, 3.5e-9)
        self.assertEqual(deck.count("XXOR_"), 30)
        self.assertEqual(deck.count("XTHR_BUF_"), 32)
        self.assertEqual(deck.count("XMUX_"), 7)
        self.assertEqual(deck.count("XDFF q_final"), 1)
        self.assertIn("XTHR_BUF_01 thr_tap_1 vdd_a vdd_a vss_a vss_a xor_29 BUF_X0P7M_A9TL40", deck)
        self.assertIn("XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset DFFRPQ_X0P5M_A9TR40", deck)
        self.assertIn("V_CODE0 code0 vss_a 'VDD_VALUE'", deck)
        self.assertIn("V_CODE1 code1 vss_a 'VDD_VALUE'", deck)
        self.assertIn("V_CODE2 code2 vss_a 0", deck)
        sizing = RUNNER.render_deck(
            self.config, self.cells, 0.80, tuple(range(1, 39)), 4, 3.5e-9, sizing=True
        )
        self.assertEqual(sizing.count("XTHR_BUF_"), 38)
        self.assertEqual(sum("t_thr_tap_" in line for line in sizing.splitlines()), 25)

    def test_render_deck_rejects_subminimum_vdd(self):
        """No new physical probe may silently enter the forbidden sub-0.80 V rail."""

        with self.assertRaises(ValueError):
            RUNNER.render_deck(self.config, self.cells, 0.79, self.taps, 0, 3.5e-9)
        self.assertEqual(RUNNER.coarse_points(0.85), [0.8])
        self.assertGreaterEqual(min(RUNNER.coarse_points(1.10)), RUNNER.VDD_MIN_V)

    def test_boundary_screening_produces_one_small_candidate(self):
        """The deterministic screen rule yields eight taps without a search loop."""

        summary = {}
        boundary_by_vdd = {1.10: 16, 0.95: 22, 0.80: 29}
        for vdd_v in RUNNER.SCREEN_VDD_POINTS:
            boundary = boundary_by_vdd[vdd_v]
            delays = [(tap - boundary) * 20.0 for tap in RUNNER.SCREEN_TAPS]
            summary[vdd_v] = {"W_S_int_ps": 0.0, "D_est_ps": delays}
        candidate = RUNNER.make_candidate(summary, guard=1)
        self.assertTrue(RUNNER.mapping_is_valid(candidate["tap_list"]))
        self.assertEqual(len(candidate["predicted_first_zero_code"]), 7)
        self.assertLessEqual(RUNNER.MAX_CANDIDATES, 2)

    def test_failed_feasibility_cannot_publish_refined_mapping(self):
        """Only the exact final GO token can authorize the refined artifact."""

        failed = {"decision": "3-bit Boundary-Centered Mapping = NO-GO", "candidate_attempts": []}
        passed = {"decision": "Delay-Code Boundary Refinement = GO", "candidate_attempts": [{"candidate_id": "primary"}]}
        self.assertFalse(RUNNER.refined_mapping_allowed(failed))
        self.assertTrue(RUNNER.refined_mapping_allowed(passed))
        self.assertEqual(RUNNER.final_decision(False)[0], "3-bit Boundary-Centered Mapping = NO-GO")
        self.assertEqual(RUNNER.final_decision(True)[1], "READY_FOR_FULL_ACCEPTANCE_WINDOW_CHARACTERIZATION")

    def test_summary_preserves_failed_gate_reasons_without_republishing_mapping(self):
        """Publication must retain the recorded Gate failure and NO-GO action."""

        attempt = {
            "candidate_id": "primary", "mapping": {"tap_list": list(self.taps)},
            "calibration": {"decision": "NO-GO", "reasons": ["boundary mismatch"]},
            "feasibility": {"decision": "NOT_RUN", "reasons": []},
        }
        summary = RUNNER.build_summary(Path("/tmp/refinement"), 3.5e-9, 3, [attempt], False)
        self.assertEqual(summary["decision"], "3-bit Boundary-Centered Mapping = NO-GO")
        self.assertEqual(summary["decision_reasons"], ["primary / calibration: boundary mismatch"])
        self.assertFalse(RUNNER.refined_mapping_allowed(summary))


if __name__ == "__main__":
    unittest.main()
