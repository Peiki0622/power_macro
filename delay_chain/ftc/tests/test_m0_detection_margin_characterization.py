"""Zero-HSPICE regressions for the FTC M0 single-probe characterization.

These tests intentionally inspect contracts, rendered deck text, and synthetic
MEAS records only.  Electrical acceptance remains the task-owned M0 HSPICE
campaign; a unit-test pass must never be interpreted as a substitute for it.
"""

import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_m0_detection_margin_characterization as study  # noqa: E402
import plot_m0_detection_margin_figures as m0_plots  # noqa: E402


class M0DetectionMarginCharacterizationTests(unittest.TestCase):
    """Protect the physical contract and data gates without launching HSPICE."""

    @classmethod
    def setUpClass(cls):
        """Load frozen source evidence once; no output file is created here."""

        if os.environ.get("CONDA_DEFAULT_ENV") != "DL":
            raise unittest.SkipTest("M0 regression is specified to run in the DL environment")
        cls.context = study.physical.frozen_context()

    def test_single_probe_deck_keeps_frozen_real_cell_ports_and_snapshot_rails(self):
        """Inspect the full deck instead of trusting a helper function name.

        The DFF positional port line proves that CK is the medium/fine output
        while D is tap29 XOR.  The constant PWL sources prove M0 starts after
        calibration and does not replay a multi-step calibration trajectory.
        """

        deck = study.render_single_probe_deck(self.context, 0.95, 4, 6)
        checks = study.topology_checks(deck, 4, 6)
        self.assertTrue(all(checks.values()), checks)
        self.assertIn("XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset DFFRPQ_X0P5M_A9TR40", deck)
        self.assertEqual(sum(line.startswith("V_M_") for line in deck.splitlines()), 16)
        self.assertEqual(sum(line.startswith("V_F_") for line in deck.splitlines()), 10)
        self.assertNotIn("XCONFIG_SKIP", deck)
        self.assertNotIn("XBYPASS", deck)

    def test_h0_corrected_single_probe_event_separations_are_preserved(self):
        """Keep every H0 physical minimum explicit in the M0 testbench timing."""

        timing = study.probe_timing()
        self.assertAlmostEqual(timing["launch_time_s"] - timing["reset_release_s"], 0.49e-9)
        self.assertAlmostEqual(timing["q_read_time_s"] - timing["launch_time_s"], 2.30e-9)
        self.assertAlmostEqual(timing["q_read_late_time_s"] - timing["q_read_time_s"], 0.20e-9)
        self.assertAlmostEqual(timing["reset_assert_start_s"] - timing["q_read_late_time_s"], 0.20e-9)
        self.assertAlmostEqual(timing["sclk_fall_s"] - timing["reset_assert_end_s"], 0.29e-9)
        self.assertAlmostEqual(timing["recovery_end_s"] - timing["sclk_fall_s"], 2.70e-9)

    def test_real_dff_trip_classifier_requires_two_stable_rail_samples(self):
        """Reject a mixed rail pair so residual R cannot become a proxy trip."""

        self.assertEqual(study.stable_q(0.95, 0.95, 0.95), (1, "stable_high"))
        self.assertEqual(study.stable_q(0.0, 0.0, 0.95), (0, "stable_low"))
        self.assertEqual(study.stable_q(0.95, 0.0, 0.95), (None, "ambiguous"))
        self.assertEqual(study.stable_q(None, 0.0, 0.95), (None, "ambiguous"))

    def test_raw_measurement_parser_reports_r_but_decides_q_from_the_dff(self):
        """A synthetic physical row verifies units, R identity, and Q validity."""

        parameters = study.probe_parameters(0.95, 0.95, 4, 6, "frozen-contract")
        timing = study.probe_timing()
        record = {
            "t_xor_rise": timing["launch_time_s"] + 0.20e-9,
            "t_xor_fall": timing["launch_time_s"] + 0.60e-9,
            "t_ck_rise": timing["launch_time_s"] + 0.70e-9,
            "t_ck_rise_2": None,
            "q_final_v": 0.0,
            "q_final_late_v": 0.0,
            "recovery_xor_end": 0.0, "recovery_xor_tail": 0.0,
            "recovery_medium_end": 0.0, "recovery_medium_tail": 0.0,
            "recovery_ck_end": 0.0, "recovery_ck_tail": 0.0,
        }
        row = study.parse_probe_record("synthetic", parameters, record, Path("/tmp/m0"), "deck")
        self.assertEqual(row["q_final"], 0)
        self.assertEqual(row["valid"], 1)
        self.assertAlmostEqual(row["W_xor_ps"], 400.0)
        self.assertAlmostEqual(row["D_ref_ps"], 500.0)
        self.assertAlmostEqual(row["R_ps"], -100.0)

    def test_cached_csv_probe_rows_restore_integer_q_for_trip_state_machine(self):
        """Prevent cached M0-4 Q strings from becoming false ambiguous trips.

        This is deliberately a CSV-boundary test: M0-5 avoids re-running an
        already-characterized normal/coarse point, but its control flow must
        see the same integer Q=0/Q=1 values that an immediate HSPICE probe
        would return.  An empty Q stays unknown and cannot be treated as 0.
        """

        low = study.normalize_cached_probe_record({"q_final": "0", "valid": "1", "R_ps": "-12.5"})
        high = study.normalize_cached_probe_record({"q_final": "1", "valid": "1"})
        ambiguous = study.normalize_cached_probe_record({"q_final": "", "valid": "0"})
        self.assertEqual((low["q_final"], low["valid"]), (0, 1))
        self.assertEqual(low["R_ps"], -12.5)
        self.assertEqual((high["q_final"], high["valid"]), (1, 1))
        self.assertEqual((ambiguous["q_final"], ambiguous["valid"]), (None, 0))

    def test_header_only_formal_table_is_allowed_only_for_terminal_reporting(self):
        """Keep an intentional NO-GO table publishable without weakening gates."""

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "terminal.csv"
            path.write_text("required,other\n", encoding="utf-8")
            self.assertEqual(study.read_csv(path, ("required",), allow_empty=True), [])
            with self.assertRaisesRegex(ValueError, "CSV is empty"):
                study.read_csv(path, ("required",))

    def test_complete_trip_csv_uses_the_last_fine_q0_before_first_q1(self):
        """Derive Table M0-B from all rows, not the coarse-sweep loop state.

        The 0.89 V Q=0 row is a fine point inserted after the 0.90 V coarse
        Q=0.  It must become ``R_at_last_q0_ps`` while the first stable Q=1 at
        0.88 V remains the Vtrip definition and therefore preserves ΔVtrip.
        """

        candidate = {
            "candidate_id": "fixture_L1", "baseline_vdd_v": 0.95,
            "margin_level": "L1", "M_det": 4, "F_det": 9,
            "nominal_D_ref_shift_ps": 24.0,
        }
        rows = [
            {"candidate_id": "fixture_L1", "physical_vdd_v": "0.95", "valid": "1", "q_final": "0", "q_state": "stable_low", "R_ps": "-1.0"},
            {"candidate_id": "fixture_L1", "physical_vdd_v": "0.90", "valid": "1", "q_final": "0", "q_state": "stable_low", "R_ps": "43.60"},
            {"candidate_id": "fixture_L1", "physical_vdd_v": "0.89", "valid": "1", "q_final": "0", "q_state": "stable_low", "R_ps": "54.63"},
            {"candidate_id": "fixture_L1", "physical_vdd_v": "0.88", "valid": "1", "q_final": "1", "q_state": "stable_high", "R_ps": "68.18"},
            {"candidate_id": "fixture_L1", "physical_vdd_v": "0.85", "valid": "1", "q_final": "1", "q_state": "stable_high", "R_ps": "114.79"},
        ]
        derived = study.derive_trip_map_from_sweep_rows([candidate], rows)["trip_map"][0]
        self.assertEqual(derived["trip_status"], "IN_RANGE_TRIP")
        self.assertAlmostEqual(derived["R_at_last_q0_ps"], 54.63)
        self.assertAlmostEqual(derived["R_at_first_q1_ps"], 68.18)
        self.assertAlmostEqual(derived["Vtrip_v"], 0.88)
        self.assertAlmostEqual(derived["DeltaV_trip_mv"], 70.0)

    def test_complete_trip_csv_rejects_q1_to_q0_reversal(self):
        """A later safe Q after a trip cannot be accepted as a valid bracket."""

        candidate = {
            "candidate_id": "reversal_L1", "baseline_vdd_v": 0.95,
            "margin_level": "L1", "M_det": 4, "F_det": 9,
            "nominal_D_ref_shift_ps": 24.0,
        }
        rows = [
            {"candidate_id": "reversal_L1", "physical_vdd_v": "0.95", "valid": "1", "q_final": "0", "q_state": "stable_low", "R_ps": "-1.0"},
            {"candidate_id": "reversal_L1", "physical_vdd_v": "0.90", "valid": "1", "q_final": "1", "q_state": "stable_high", "R_ps": "40.0"},
            {"candidate_id": "reversal_L1", "physical_vdd_v": "0.89", "valid": "1", "q_final": "0", "q_state": "stable_low", "R_ps": "50.0"},
        ]
        derived = study.derive_trip_map_from_sweep_rows([candidate], rows)["trip_map"][0]
        self.assertEqual(derived["trip_status"], "INVALID")
        self.assertEqual(derived["reason"], "q_one_to_zero_reversal")
        self.assertIsNone(derived["Vtrip_v"])

    def test_local_surface_panels_share_one_zero_centered_normalization(self):
        """Ensure M0-1 color meaning is identical across all three baselines."""

        surface = [
            {"scenario_id": "surface_080", "baseline_vdd_v": "0.80", "physical_vdd_v": "0.80", "medium_code": "7", "fine_code": "6", "R_ps": "-40.0", "q_final": "0", "valid": "1"},
            {"scenario_id": "surface_095", "baseline_vdd_v": "0.95", "physical_vdd_v": "0.95", "medium_code": "4", "fine_code": "6", "R_ps": "0.0", "q_final": "0", "valid": "1"},
            {"scenario_id": "surface_110", "baseline_vdd_v": "1.10", "physical_vdd_v": "1.10", "medium_code": "2", "fine_code": "9", "R_ps": "60.0", "q_final": "0", "valid": "1"},
        ]
        figure, _ = m0_plots.fig_local_surface(surface, [])
        try:
            mapped_collections = [collection for axis in figure.axes[:3] for collection in axis.collections if collection.get_array() is not None]
            self.assertEqual(len(mapped_collections), 3)
            shared_norm = mapped_collections[0].norm
            self.assertIsInstance(shared_norm, m0_plots.TwoSlopeNorm)
            self.assertTrue(all(collection.norm is shared_norm for collection in mapped_collections))
            self.assertAlmostEqual(shared_norm(-40.0), 0.0)
            self.assertAlmostEqual(shared_norm(0.0), 0.5)
            self.assertAlmostEqual(shared_norm(60.0), 1.0)
        finally:
            m0_plots.plt.close(figure)

    def test_surface_gate_requires_complete_two_dimensional_ordering(self):
        """Build synthetic full windows to verify both M and F adjacency gates."""

        rows = []
        for anchor in study.ANCHORS.values():
            baseline = float(anchor["baseline_vdd_v"])
            for medium in anchor["m_values"]:
                for fine in anchor["f_values"]:
                    # Both code directions add delay in this deterministic
                    # fixture, while Q stays at the normal safe state.
                    delay = 1000.0 * medium + 10.0 * fine
                    rows.append({
                        "baseline_vdd_v": baseline, "physical_vdd_v": baseline,
                        "medium_code": medium, "fine_code": fine, "D_ref_ps": delay,
                        "W_xor_ps": delay - 20.0, "R_ps": -20.0,
                        "q_final": 0, "valid": 1,
                    })
        self.assertEqual(study.surface_gate(rows)["decision"], "GO")
        rows[-1] = dict(rows[-1], D_ref_ps=0.0)
        self.assertEqual(study.surface_gate(rows)["decision"], "NO-GO")

    def test_scenario_identity_is_physical_not_analysis_phase_and_old_static_runner_is_not_imported(self):
        """Permit same-deck reuse across M0 stages while forbidding old lock reuse."""

        first = study.probe_parameters(0.95, 0.95, 4, 6, "contract")
        second = study.probe_parameters(0.95, 0.95, 4, 6, "contract")
        self.assertEqual(study.scenario_id(first), study.scenario_id(second))
        source = inspect.getsource(study)
        self.assertNotIn("import run_two_stage_real_dff_hierarchical_calibration", source)
        self.assertIn("import run_dynamic_startup_calibration_protocol", source)


if __name__ == "__main__":
    unittest.main()
