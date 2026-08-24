"""Zero-HSPICE regression tests for the FTC T0 transient contracts.

These tests check renderer structure, input reuse, waveform legality, power
domain normalization, and the zero-HSPICE correction gate.  They never substitute for the retained HSPICE
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
        threat = contract["t0"]
        power = contract["power_domain"]
        self.assertEqual(threat["formal_scope"]["baseline_vdd_v"], [0.95, 1.1])
        self.assertEqual(threat["formal_scope"]["margin_levels"], ["L1", "L2", "L3"])
        self.assertEqual(threat["formal_scope"]["formal_minimum_vdd_v"], 0.8)
        self.assertTrue(threat["waveform"]["zero_time_voltage_jump_forbidden"])
        self.assertEqual(power["crossings"]["PD_CTRL_to_PD_SENSE"]["count"], 28)

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
        self.assertEqual(sum(line.startswith("E_M_") for line in deck.splitlines()), 16)
        self.assertEqual(sum(line.startswith("E_F_") for line in deck.splitlines()), 10)
        self.assertIn("E_SCLK s_clk vss_a VOL='V(ctrl_sclk,vss_a)*V(vdd_a,vss_a)'", deck)
        self.assertIn("V(vdd_a,vss_a)/2", deck)
        # T0-3+ classifications are rail-relative at each individual Q read,
        # so the deck must measure both instantaneous local supply values.
        self.assertIn("vdd_at_q_sample_1 FIND v(vdd_a,vss_a)", deck)
        self.assertIn("vdd_at_q_sample_2 FIND v(vdd_a,vss_a)", deck)

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

    def test_correction_audit_and_legacy_marker_are_present(self):
        audit = json.loads((FTC_ROOT / "analysis/t0_transient_droop/correction/correction_audit.json").read_text())
        equivalence = json.loads((FTC_ROOT / "analysis/t0_transient_droop/correction/constant_low_equivalence_audit.json").read_text())
        marker = json.loads((FTC_ROOT / "analysis/t0_transient_droop/correction/legacy_62_scenarios_marker.json").read_text())
        self.assertEqual(audit["decision"], "GO_TO_FOUR_POINT_CORRECTION_ONLY")
        self.assertTrue(equivalence["equivalent"])
        self.assertEqual(marker["scenario_count"], 62)

    def test_dynamic_q_uses_each_sample_local_vdd(self):
        """Reject a rail-edge pair that a fixed Vdroop threshold could mislabel."""

        self.assertEqual(
            # Keep both ratios strictly above 0.90 so IEEE floating-point
            # representation at the exact threshold cannot obscure intent.
            study.classify_dynamic_q(0.91, 0.73, 0.95, 0.80)[:2],
            (1, "stable_high"),
        )
        self.assertEqual(
            study.classify_dynamic_q(0.91, 0.73, 0.95, 0.95)[:2],
            (None, "ambiguous"),
        )
        self.assertEqual(
            study.classify_dynamic_q(0.05, 0.04, 0.95, None)[:2],
            (None, "ambiguous"),
        )

    def test_t0_2e_evidence_closes_legacy_stop_without_simulation(self):
        """Validate the T0-2E inputs without mutating the stage gate in a test."""

        result = study.verify_corrected_t0_2_evidence()
        supersession = json.loads((FTC_ROOT / "analysis/t0_transient_droop/long_pulse_consistency/supersession.json").read_text())
        gate = json.loads((FTC_ROOT / "analysis/t0_transient_droop/reports/T0_GATE_STATUS.json").read_text())
        self.assertEqual(result["hspice_scenarios"], 0)
        self.assertEqual(supersession["historical_decision"], "STOP")
        self.assertIn(gate["t0_3_status"], ("ENABLED", "GO"))

    def test_phase_windows_keep_disconnected_q1_and_blind_intervals(self):
        """Interval extraction must not collapse a multi-window physical result."""

        rows = [
            {"baseline_vdd_v": 0.95, "phase_ps": 0.0, "valid": 1, "q_final": 0},
            {"baseline_vdd_v": 0.95, "phase_ps": 25.0, "valid": 1, "q_final": 1},
            {"baseline_vdd_v": 0.95, "phase_ps": 50.0, "valid": 1, "q_final": 0},
            {"baseline_vdd_v": 0.95, "phase_ps": 75.0, "valid": 1, "q_final": 1},
        ]
        summary = study.phase_window_summary(rows, 0.95)
        self.assertEqual(len(summary["detectable_windows"]), 2)
        self.assertEqual(len(summary["blind_windows"]), 2)
        self.assertEqual(len(summary["transition_boundaries"]), 3)

    def test_t0_4_uses_only_m0_brackets_and_formal_floor(self):
        """Amplitude points are local to each margin and never cross 0.80 V."""

        points = study.t0_4_vdroop_points()
        self.assertEqual(len(points), 6)
        for baseline, margin, rails in points:
            self.assertIn((baseline, margin), study.FORMAL_CODES)
            self.assertGreaterEqual(min(value for _, value in rails), 0.80)
            self.assertEqual(rails[0][0], "last_q0_control")
            self.assertEqual(rails[1][0], "first_q1_anchor")

    def test_terminal_gate_keeps_t0_2_pass_and_blocks_cadence(self):
        """T0-4E unlocks T0-5 without fabricating a cadence result.

        The transition is intentionally asymmetric: phase coverage may now be
        measured, but cadence needs those completed windows and therefore
        remains pending with no numerical maximum probe period.
        """

        gate = json.loads((FTC_ROOT / "analysis/t0_transient_droop/reports/T0_GATE_STATUS.json").read_text())
        downstream = json.loads((FTC_ROOT / "analysis/t0_transient_droop/contract/T0_DOWNSTREAM_D0_TIMING_CONTRACT.json").read_text())
        self.assertEqual(gate["t0_2_status"], "T0-2 CORRECTED PASS")
        self.assertEqual(gate["t0_4_status"], "GO")
        self.assertEqual(gate["t0_4e_status"], "PASS_ZERO_HSPICE_EVIDENCE_CLOSURE")
        self.assertEqual(gate["t0_5_status"], "ENABLED")
        self.assertEqual(gate["t0_6_status"], "WAITING_FOR_T0_5_GATE")
        self.assertEqual(downstream["source_gate"], "T0-4 GO")
        self.assertEqual(downstream["runtime_probe_period"]["status"], "PENDING_T0_5_T0_6")
        self.assertEqual(downstream["runtime_probe_period"]["maximum_period_s"], None)

    def test_t0_4e_authority_hashes_and_stop_supersession_are_present(self):
        """The T0-4E handoff must hash evidence rather than trust filenames.

        This check reads the six authoritative inputs directly.  It protects
        against a future report/gate edit leaving a stale hash record that
        could incorrectly unlock a later physical phase.
        """

        closure = FTC_ROOT / "analysis/t0_transient_droop/t0_4e_closure"
        authority = json.loads((closure / "authoritative_evidence_hashes.json").read_text())
        supersession = json.loads((closure / "stale_stop_supersession.json").read_text())
        self.assertEqual(authority["t0_4_status"], "GO")
        self.assertEqual(authority["formal_historical_scenario_count"], 238)
        self.assertEqual(authority["diagnostic_unique_electrical_case_count"], 4)
        self.assertEqual(authority["hspice_scenarios"], 0)
        self.assertEqual(len(authority["authority_input_sha256"]), 6)
        self.assertEqual(supersession["historical_status"], "HISTORICAL_SUPERSEDED_NOT_DELETED")
        self.assertEqual(supersession["historical_gate"], "T0-4 STOP")

    def test_source_hash_drift_reuses_electrically_identical_t0_3_measurement(self):
        """Runner growth must not rerun a retained long-pulse phase point.

        The requested parameters intentionally receive the current runner
        hash, whereas the retained T0-3 manifest carries the old one.  The
        executor may reuse it only after the explicit electrical projection
        and normalized transistor deck both match; this test also proves that
        the reuse path does not need an HSPICE preflight.
        """

        parameters = study.parameters_for(0.95, "L2", 0.86, 3000.0, -1000.0)
        stats = {"new": 0, "reused": 0}
        row = study.execute(self.context, parameters, stats)
        self.assertEqual(row["evidence_source"], "REUSED_RETAINED_MEASUREMENT")
        self.assertEqual(row["reuse_reason"], "ELECTRICALLY_EQUIVALENT_SOURCE_HASH_DRIFT")
        self.assertEqual(stats["new"], 0)
        self.assertEqual(stats["reused_electrical"], 1)
        self.assertEqual(row["electrical_projection_sha256"], study.electrical_projection_sha256(parameters))

    def test_legacy_t0_4_entry_cannot_overwrite_corrected_go(self):
        """Historical amplitude-duration code must fail closed after T0-4E."""

        gate_path = FTC_ROOT / "analysis/t0_transient_droop/reports/T0_GATE_STATUS.json"
        before = gate_path.read_text()
        with self.assertRaisesRegex(RuntimeError, "historical-only"):
            study.phase_amplitude_duration()
        self.assertEqual(gate_path.read_text(), before)

    def test_t0_4_negative_controls_and_clean_q1_boundaries(self):
        """Null duration is legal only for stable-Q0 negative controls."""

        summary = json.loads((FTC_ROOT / "analysis/t0_transient_droop/amplitude_duration/summary.json").read_text())
        self.assertTrue(summary["negative_control_pass"])
        self.assertEqual(summary["valid_minimum_duration_count"], 18)
        self.assertEqual(summary["invalid_minimum_duration_count"], 0)
        self.assertEqual(summary["q1_to_q0_reversal_count"], 0)
        controls = [item for item in summary["boundaries"] if item["point_label"] == "last_q0_control"]
        self.assertEqual(len(controls), 6)
        self.assertTrue(all(item["minimum_detectable_hold_ps"] is None and item["negative_control_pass"] for item in controls))
        corrected = [item for item in summary["boundaries"] if item["baseline_vdd_v"] == "0.95" and item["margin_level"] == "L3" and item["point_label"] == "first_q1_anchor"]
        self.assertEqual(corrected[0]["clean_q1_bracket_ps"], {"q0_ps": 1500.0, "q1_ps": 2000.0})

    def test_t0_4_diagnostics_exclude_real_second_clock(self):
        """The recovery-local second crossing is slew-sensitive and Q stays high."""

        diagnostics = json.loads((FTC_ROOT / "analysis/t0_transient_droop/amplitude_duration/anomaly_diagnostics.json").read_text())
        self.assertEqual(diagnostics["unique_diagnostic_case_count"], 4)
        self.assertEqual(diagnostics["new_hspice"], 8)
        for case in diagnostics["cases"]:
            self.assertTrue(case["slew_1ps"]["second_ratio_cross_present"])
            self.assertTrue(case["slew_1ps"]["raw_second_cross_present"])
            self.assertEqual(case["slew_1ps"]["ratio_min_between_local_recovery_crossings"], 0.5)
            self.assertFalse(case["slew_10ps"]["second_ratio_cross_present"])
            self.assertFalse(case["slew_10ps"]["raw_second_cross_present"])
            self.assertEqual(case["slew_1ps"]["q_state"], "stable_high")
            self.assertEqual(case["slew_10ps"]["q_state"], "stable_high")


if __name__ == "__main__":
    unittest.main()
