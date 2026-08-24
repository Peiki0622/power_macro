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

    def test_t0_4e_keeps_t0_2_pass_and_t0_6_is_the_only_cadence_authority(self):
        """Keep T0-4E provenance separate from the later T0-6 conclusion.

        T0-4E released phase coverage but never manufactured a runtime
        cadence.  The completed repository must retain the corrected upstream
        statuses while assigning the numerical Pmax only to the zero-HSPICE
        T0-6 interval-mapping contract.
        """

        gate = json.loads((FTC_ROOT / "analysis/t0_transient_droop/reports/T0_GATE_STATUS.json").read_text())
        downstream = json.loads((FTC_ROOT / "analysis/t0_transient_droop/contract/T0_DOWNSTREAM_D0_TIMING_CONTRACT.json").read_text())
        self.assertEqual(gate["t0_2_status"], "T0-2 CORRECTED PASS")
        self.assertEqual(gate["t0_4_status"], "GO")
        self.assertEqual(gate["t0_4e_status"], "PASS_ZERO_HSPICE_EVIDENCE_CLOSURE")
        self.assertEqual(gate["t0_5_status"], "GO")
        self.assertEqual(gate["t0_6_status"], "CONDITIONAL_GO")
        self.assertEqual(downstream["source_gate"], "T0-6 CONDITIONAL_GO")
        self.assertEqual(downstream["runtime_probe_period"]["status"], "QUALIFIED_BY_T0_6_INTERVAL_MATH")
        self.assertAlmostEqual(downstream["runtime_probe_period"]["maximum_period_s"], 2075.0e-12)

    def test_t0_5_complete_phase_closure_is_real_and_complete(self):
        """Confirm complete T0-5 uses physical Q0 closure and audited reuse.

        Both long pulses must extend left beyond the old time-zero source
        coordinate and then actually return to stable Q0.  The two T0-5B
        special-margin maps must also close at Q0 while preserving their one
        known T0-4 fast-recovery ambiguity each.  This is an evidence test,
        not a smoke test: it checks all six published maps, per-substage
        HSPICE/reuse accounting, four-state intervals, and proves that later
        cadence publication did not alter the retained physical T0-5 result.
        """

        summary_path = FTC_ROOT / "analysis/t0_transient_droop/phase_coverage/phase_coverage_summary.json"
        phase_path = FTC_ROOT / "analysis/t0_transient_droop/phase_coverage/phase_coverage.csv"
        summary = json.loads(summary_path.read_text())
        with phase_path.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        by_key = {}
        for row in rows:
            by_key.setdefault(row["scenario_key"], []).append(row)

        self.assertEqual(summary["decision"], "GO")
        self.assertEqual(summary["stage"], "T0-5 COMPLETE")
        self.assertEqual(summary["new_hspice"], 139)
        self.assertEqual(summary["reused"], 46)
        self.assertEqual(summary["reused_electrical"], 46)
        self.assertEqual(summary["reused_interrupted_t0_5a"], 60)
        self.assertEqual(summary["unique_physical_scenario_count"], 185)
        self.assertEqual(summary["t0_5a_accounting"]["new_hspice"], 75)
        self.assertEqual(summary["t0_5a_accounting"]["reused"], 44)
        self.assertEqual(summary["t0_5a_accounting"]["reused_interrupted_t0_5a"], 60)
        self.assertEqual(summary["t0_5a_accounting"]["unique_physical_scenario_count"], 119)
        self.assertEqual(summary["t0_5b_accounting"], {
            "new_hspice": 64, "reused": 2, "reused_exact": 0, "reused_electrical": 2,
        })
        self.assertEqual(set(by_key), {
            "t0_5a_0p95_l2_boundary", "t0_5a_0p95_l2_long",
            "t0_5a_1p10_l2_boundary", "t0_5a_1p10_l2_long",
            "t0_5b_0p95_l3_recovery", "t0_5b_1p10_l1_recovery",
        })
        summaries = {item["scenario_key"]: item for item in summary["scenarios"]}
        expected_time_measure = {
            "t0_5a_0p95_l2_boundary": (1000.0, 525.0, 0.525, 250.0),
            "t0_5a_0p95_l2_long": (4750.0, 2075.0, 2075.0 / 4750.0, 2425.0),
            "t0_5a_1p10_l2_boundary": (1000.0, 525.0, 0.525, 250.0),
            "t0_5a_1p10_l2_long": (5000.0, 2325.0, 0.465, 2475.0),
            "t0_5b_0p95_l3_recovery": (1250.0, 875.0, 0.70, 250.0),
            "t0_5b_1p10_l1_recovery": (1250.0, 950.0, 0.76, 175.0),
        }
        for item in summaries.values():
            group = sorted(by_key[item["scenario_key"]], key=lambda row: float(row["phase_ps"]))
            self.assertTrue(item["left_closed_by_stable_q0"])
            self.assertTrue(item["right_closed_by_stable_q0"])
            self.assertTrue(item["clean_q1_intervals"])
            self.assertEqual(group[0]["t0_5_state"], "STABLE_Q0")
            self.assertEqual(group[-1]["t0_5_state"], "STABLE_Q0")
            span, clean_measure, coverage, maximum_non_guarantee = expected_time_measure[item["scenario_key"]]
            self.assertNotIn("clean_phase_coverage_fraction", item)
            self.assertAlmostEqual(item["characterized_phase_span_ps"], span)
            self.assertAlmostEqual(item["guaranteed_clean_measure_ps"], clean_measure)
            self.assertAlmostEqual(item["clean_time_coverage_fraction"], coverage)
            self.assertAlmostEqual(item["non_guarantee_measure_ps"], span - clean_measure)
            self.assertAlmostEqual(item["maximum_non_guarantee_window_ps"], maximum_non_guarantee)
            self.assertAlmostEqual(
                item["guaranteed_clean_measure_ps"] + item["non_guarantee_measure_ps"], span)

        # The original four maps contain no ambiguity; their phase closure
        # remains untouched by publication of the two supplementary maps.
        for key in (
                "t0_5a_0p95_l2_boundary", "t0_5a_0p95_l2_long",
                "t0_5a_1p10_l2_boundary", "t0_5a_1p10_l2_long"):
            self.assertEqual(summaries[key]["ambiguous_sample_count"], 0)

        for key, expected_left in (("t0_5a_0p95_l2_long", -2250.0), ("t0_5a_1p10_l2_long", -2500.0)):
            group = sorted(by_key[key], key=lambda row: float(row["phase_ps"]))
            self.assertEqual(float(group[0]["phase_ps"]), expected_left)
            self.assertGreater(float(group[0]["time_axis_shift_s"]), 0.0)

        # T0-5B is deliberately restricted to two T0-4 recovery-edge
        # boundaries.  At each one, exactly one sampled phase is a known fast
        # recovery ambiguity; it is retained as non-guaranteed rather than
        # silently promoted to CLEAN_Q1, and no unknown invalid state remains.
        for key in ("t0_5b_0p95_l3_recovery", "t0_5b_1p10_l1_recovery"):
            item = summaries[key]
            group = by_key[key]
            self.assertEqual(item["ambiguous_sample_count"], 1)
            self.assertEqual(len(item["recovery_edge_ambiguous_intervals"]), 1)
            self.assertFalse(item["other_invalid_ambiguous_intervals"])
            self.assertEqual(item["needs_local_recovery_diagnosis_count"], 0)
            ambiguous_rows = [row for row in group if row["t0_5_state"] == "RECOVERY_EDGE_AMBIGUOUS"]
            self.assertEqual(len(ambiguous_rows), 1)
            self.assertEqual(ambiguous_rows[0]["recovery_model_status"], "KNOWN_T0_4_FAST_RECOVERY_PATTERN")
        gate = json.loads((FTC_ROOT / "analysis/t0_transient_droop/reports/T0_GATE_STATUS.json").read_text())
        self.assertEqual(gate["t0_5a_status"], "GO")
        self.assertEqual(gate["t0_5b_status"], "GO")
        self.assertEqual(gate["t0_5_status"], "GO")
        self.assertEqual(gate["decision"], "CONDITIONAL_GO")
        self.assertEqual(gate["t0_6_status"], "CONDITIONAL_GO")
        self.assertEqual(gate["t0_8_status"], "FINAL_EVIDENCE_PUBLISHED")

    def test_t0_5_time_measure_ignores_adaptive_sample_density_and_keeps_boundary_gaps(self):
        """Measure identical physical windows identically on coarse and fine grids.

        The two first synthetic maps have the same closed Q0 domain and the
        same confirmed CLEAN_Q1 interval, but one includes an extra in-window
        refinement sample.  Time coverage must be identical despite different
        sample counts.  The third map inserts a recovery ambiguity between two
        clean intervals: it verifies both that they remain distinct and that
        the two transition brackets plus the ambiguous phase remain in the
        non-guaranteed complement.
        """

        def summarize(key, samples):
            rows = []
            for phase_ps, state in samples:
                rows.append({
                    "scenario_key": key,
                    "scenario_family": "TEST_INTERVAL_MEASURE",
                    "baseline_vdd_v": 0.95,
                    "margin_level": "L2",
                    "Vdroop_v": 0.86,
                    "t_hold_ps": 1454.0,
                    "t_fall_ps": 1.0,
                    "t_rise_ps": 1.0,
                    "phase_ps": phase_ps,
                    "t0_5_state": state,
                    "recovery_model_status": "NOT_APPLICABLE",
                })
            return study.summarize_t0_5_rows(rows)[0]

        coarse = summarize("coarse", [
            (0.0, "STABLE_Q0"), (25.0, "CLEAN_Q1"),
            (75.0, "CLEAN_Q1"), (100.0, "STABLE_Q0"),
        ])
        refined = summarize("refined", [
            (0.0, "STABLE_Q0"), (25.0, "CLEAN_Q1"),
            (50.0, "CLEAN_Q1"), (75.0, "CLEAN_Q1"), (100.0, "STABLE_Q0"),
        ])
        self.assertNotEqual(coarse["sample_count"], refined["sample_count"])
        self.assertEqual(coarse["clean_q1_sample_count"], 2)
        self.assertEqual(refined["clean_q1_sample_count"], 3)
        for item in (coarse, refined):
            self.assertAlmostEqual(item["characterized_phase_span_ps"], 100.0)
            self.assertAlmostEqual(item["guaranteed_clean_measure_ps"], 50.0)
            self.assertAlmostEqual(item["clean_time_coverage_fraction"], 0.50)
            self.assertAlmostEqual(item["maximum_non_guarantee_window_ps"], 25.0)
            self.assertEqual(item["non_guarantee_intervals"], [
                {"phase_start_ps": 0.0, "phase_end_ps": 25.0, "width_ps": 25.0},
                {"phase_start_ps": 75.0, "phase_end_ps": 100.0, "width_ps": 25.0},
            ])

        ambiguous = summarize("ambiguous", [
            (0.0, "STABLE_Q0"), (25.0, "CLEAN_Q1"), (50.0, "CLEAN_Q1"),
            (75.0, "RECOVERY_EDGE_AMBIGUOUS"), (100.0, "CLEAN_Q1"),
            (125.0, "CLEAN_Q1"), (150.0, "STABLE_Q0"),
        ])
        self.assertEqual(len(ambiguous["clean_q1_intervals"]), 2)
        self.assertAlmostEqual(ambiguous["guaranteed_clean_measure_ps"], 50.0)
        self.assertAlmostEqual(ambiguous["non_guarantee_measure_ps"], 100.0)
        self.assertAlmostEqual(ambiguous["clean_time_coverage_fraction"], 1.0 / 3.0)
        self.assertAlmostEqual(ambiguous["maximum_non_guarantee_window_ps"], 50.0)
        self.assertIn(
            {"phase_start_ps": 50.0, "phase_end_ps": 100.0, "width_ps": 50.0},
            ambiguous["non_guarantee_intervals"],
        )

    def test_t0_6_periodic_interval_math_keeps_circle_seams_and_ambiguity_conservative(self):
        """Check T0-6 geometry without any HSPICE or runner side effect.

        The first synthetic map proves an interval that crosses the period
        seam remains one continuous blind window.  The second proves a
        non-zero recovery-ambiguous interval and every sampled transition gap
        remain non-guaranteed even when a different periodic copy is absent.
        """

        simple = {
            "characterized_phase_start_ps": 0.0,
            "characterized_phase_end_ps": 150.0,
            "left_closed_by_stable_q0": True,
            "right_closed_by_stable_q0": True,
            "recovery_edge_ambiguous_intervals": [],
            "other_invalid_ambiguous_intervals": [],
            "intervals": [
                {"state": "STABLE_Q0", "phase_start_ps": 0.0, "phase_end_ps": 25.0},
                {"state": "CLEAN_Q1", "phase_start_ps": 50.0, "phase_end_ps": 100.0},
                {"state": "STABLE_Q0", "phase_start_ps": 125.0, "phase_end_ps": 150.0},
            ],
        }
        measure = study.t0_6_measure_period(simple, 75.0)
        self.assertAlmostEqual(measure["guaranteed_clean_measure_ps"], 50.0)
        self.assertAlmostEqual(measure["boundary_uncertainty_measure_ps"], 25.0)
        self.assertAlmostEqual(measure["stable_blind_measure_ps"], 0.0)
        self.assertAlmostEqual(measure["maximum_non_guarantee_window_ps"], 25.0)
        self.assertAlmostEqual(measure["worst_attack_phase_ps"], 25.0)
        self.assertFalse(measure["full_phase_guaranteed"])

        wrapped_width, wrapped_phase = study.t0_6_largest_circular_interval([
            {"phase_start_ps": 0.0, "phase_end_ps": 20.0},
            {"phase_start_ps": 70.0, "phase_end_ps": 75.0},
        ], 75.0)
        self.assertAlmostEqual(wrapped_width, 25.0)
        self.assertAlmostEqual(wrapped_phase, 70.0)

        ambiguous = {
            "characterized_phase_start_ps": 0.0,
            "characterized_phase_end_ps": 220.0,
            "left_closed_by_stable_q0": True,
            "right_closed_by_stable_q0": True,
            "recovery_edge_ambiguous_intervals": [
                {"state": "RECOVERY_EDGE_AMBIGUOUS", "phase_start_ps": 100.0, "phase_end_ps": 120.0},
            ],
            "other_invalid_ambiguous_intervals": [],
            "intervals": [
                {"state": "STABLE_Q0", "phase_start_ps": 0.0, "phase_end_ps": 20.0},
                {"state": "CLEAN_Q1", "phase_start_ps": 40.0, "phase_end_ps": 80.0},
                {"state": "RECOVERY_EDGE_AMBIGUOUS", "phase_start_ps": 100.0, "phase_end_ps": 120.0},
                {"state": "CLEAN_Q1", "phase_start_ps": 140.0, "phase_end_ps": 180.0},
                {"state": "STABLE_Q0", "phase_start_ps": 200.0, "phase_end_ps": 220.0},
            ],
        }
        measure = study.t0_6_measure_period(ambiguous, 300.0)
        self.assertAlmostEqual(measure["guaranteed_clean_measure_ps"], 80.0)
        self.assertAlmostEqual(measure["recovery_ambiguous_measure_ps"], 20.0)
        self.assertAlmostEqual(measure["boundary_uncertainty_measure_ps"], 80.0)
        self.assertAlmostEqual(measure["stable_blind_measure_ps"], 120.0)
        self.assertEqual(measure["recovery_ambiguous_event_count"], 1)
        self.assertAlmostEqual(measure["non_guarantee_measure_ps"], 220.0)

    def test_t0_6_completed_cadence_contract_uses_only_interval_evidence(self):
        """Validate target Pmax, reference periods, and the zero-HSPICE ledger.

        The selected threat is the common 3002 ps L2 long pulse.  The narrower
        0.95 V clean interval limits its full-phase guaranteed cadence to
        2075 ps, so neither the 2.5 ns control clock nor the 5.70 ns one-shot
        reference can be misreported as a qualified runtime implementation.
        """

        cadence_csv = FTC_ROOT / "analysis/t0_transient_droop/cadence/coverage_vs_probe_period.csv"
        cadence_summary_path = FTC_ROOT / "analysis/t0_transient_droop/cadence/cadence_summary.json"
        with cadence_csv.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        summary = json.loads(cadence_summary_path.read_text())
        downstream = json.loads((FTC_ROOT / "analysis/t0_transient_droop/contract/T0_DOWNSTREAM_D0_TIMING_CONTRACT.json").read_text())
        self.assertEqual(len(rows), 6 * 240)
        self.assertEqual(summary["decision"], "CONDITIONAL_GO")
        self.assertEqual(summary["simulation_accounting"]["hspice_scenarios"], 0)
        self.assertEqual(summary["pmax_coverage_ps"], 2075.0)
        self.assertEqual(summary["target_threat"]["scenario_keys"], list(study.T0_6_TARGET_SCENARIO_KEYS))
        by_key_period = {(row["scenario_key"], float(row["probe_period_ps"])): row for row in rows}
        low_2075 = by_key_period[("t0_5a_0p95_l2_long", 2075.0)]
        low_2500 = by_key_period[("t0_5a_0p95_l2_long", 2500.0)]
        high_2500 = by_key_period[("t0_5a_1p10_l2_long", 2500.0)]
        self.assertEqual(low_2075["full_phase_guaranteed"], "True")
        self.assertAlmostEqual(float(low_2500["clean_coverage_fraction"]), 0.83)
        self.assertAlmostEqual(float(high_2500["clean_coverage_fraction"]), 0.93)
        self.assertEqual(low_2500["full_phase_guaranteed"], "False")
        self.assertFalse(downstream["control_clock_reference"]["is_runtime_probe_cadence"])
        self.assertFalse(downstream["control_clock_reference"]["target_full_phase_guaranteed"])
        self.assertFalse(downstream["one_shot_nonoverlap_reference"]["target_full_phase_guaranteed"])
        self.assertTrue(downstream["d0_runtime_probe_requirement"]["needs_more_compact_sequence"])
        self.assertEqual(downstream["d0_runtime_probe_requirement"]["maximum_runtime_probe_period_ps"], 2075.0)
        self.assertEqual(downstream["simulation_accounting"]["hspice_scenarios"], 0)

    def test_t0_8_final_package_has_current_figures_report_and_zero_hspice_accounting(self):
        """Require the five final figures to cite current corrected evidence.

        The test validates manifest hashes rather than trusting filenames.  It
        also checks the final report and Gate retain CONDITIONAL_GO with the
        concrete D0 period condition, instead of the obsolete T0-4 STOP image
        text or an unqualified claim that the 400 MHz control clock is runtime
        probe hardware.
        """

        manifest_path = FTC_ROOT / "analysis/t0_transient_droop/figures/figure_manifest.json"
        report_path = FTC_ROOT / "reports/FTC_T0_TRANSIENT_DROOP_CHARACTERIZATION.md"
        manifest = json.loads(manifest_path.read_text())
        gate = json.loads((FTC_ROOT / "analysis/t0_transient_droop/reports/T0_GATE_STATUS.json").read_text())
        self.assertEqual(manifest["schema_version"], 3)
        self.assertEqual(manifest["stage"], "T0-8")
        self.assertEqual(manifest["decision"], "CONDITIONAL_GO")
        expected_sources = study.t0_8_expected_figure_sources()
        figures = {item["figure_stem"]: item for item in manifest["figures"]}
        self.assertEqual(set(figures), set(expected_sources))
        for stem, sources in expected_sources.items():
            item = figures[stem]
            self.assertEqual(item["plot_script_sha256"], study.sha256_file(FTC_ROOT / "scripts/plot_t0_transient_droop_figures.py"))
            self.assertEqual(item["conda_env"], "DL")
            self.assertGreaterEqual(min(item["png_dpi"]), 590.0)
            self.assertGreaterEqual(item["png_width_px"], 1200)
            self.assertGreaterEqual(item["png_height_px"], 800)
            self.assertEqual(item["source_sha256"], {
                str(path.relative_to(FTC_ROOT)): study.sha256_file(path) for path in sources
            })
            self.assertTrue((FTC_ROOT / item["pdf"]).is_file())
            self.assertTrue((FTC_ROOT / item["png"]).is_file())
        report = report_path.read_text()
        self.assertIn("**CONDITIONAL_GO**", report)
        self.assertIn("2.075 ns", report)
        self.assertIn("T0-6 interval mapping：新增 HSPICE 0", report)
        self.assertNotIn("T0-4 STOP", report)
        self.assertEqual(gate["decision"], "CONDITIONAL_GO")
        self.assertEqual(gate["t0_8_status"], "FINAL_EVIDENCE_PUBLISHED")
        self.assertEqual(gate["t0_8_simulation_accounting"]["hspice_scenarios"], 0)

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

    def test_early_t0_5_phase_uses_uniform_pre_simulation_translation(self):
        """Represent a pre-probe long pulse without changing probe physics.

        A 3002 ps pulse needs phases earlier than the old time-zero source
        limit before it can recover before the probe.  This test verifies the
        renderer's only permitted remedy: add one common offset to reset,
        S_CLK, both Q reads, reset assert, S_CLK fall, recovery, and stop.
        It deliberately checks differences rather than absolute timestamps,
        because the phase and frozen M0 event intervals are the physical
        contract while the added HSPICE prelude is only a testbench coordinate.
        """

        parameters = study.parameters_for(0.95, "L2", 0.86, 3000.0, -3250.0)
        frozen = study.probe_timing()
        shifted = study.shifted_probe_timing(parameters)
        shift = shifted["time_axis_shift_s"]
        self.assertGreater(shift, 0.0)
        self.assertAlmostEqual(
            shifted["launch_time_s"] + parameters["phase_ps"] * 1e-12,
            study.T0_PRE_SIMULATION_TIME_S,
            places=18,
        )
        self.assertAlmostEqual(
            (shifted["launch_time_s"] + parameters["phase_ps"] * 1e-12 - shifted["launch_time_s"]) * 1e12,
            parameters["phase_ps"],
            places=9,
        )
        for key in (
            "reset_release_s", "launch_time_s", "q_read_time_s",
            "q_read_late_time_s", "reset_assert_start_s",
            "reset_assert_end_s", "sclk_fall_s", "recovery_end_s",
            "stop_time_s",
        ):
            self.assertAlmostEqual(shifted[key] - frozen[key], shift, places=18)

        deck = study.render_deck(self.context, parameters)
        for key in (
            "launch_time_s", "q_read_time_s", "q_read_late_time_s",
            "reset_assert_start_s", "reset_assert_end_s", "sclk_fall_s",
            "recovery_end_s",
        ):
            self.assertIn(study.physical.spice(shifted[key]), deck)
        self.assertTrue(all(study.topology_checks(deck, parameters).values()))

    def test_retained_t0_3_left_endpoint_needs_no_time_translation(self):
        """Keep the existing -1000 ps long-pulse deck reusable byte-for-byte.

        The formal T0-3 left endpoint already starts at positive HSPICE time,
        so the new prelude mechanism must be dormant.  Together with the
        retained-measurement reuse test above, this protects against an
        accidental whole-map rerun caused only by runner source growth.
        """

        parameters = study.parameters_for(0.95, "L2", 0.86, 3000.0, -1000.0)
        timing = study.shifted_probe_timing(parameters)
        self.assertEqual(timing["time_axis_shift_s"], 0.0)
        self.assertGreater(timing["launch_time_s"] + parameters["phase_ps"] * 1e-12, 0.0)
        self.assertFalse(hasattr(study, "MIN_LEGAL_PHASE_PS"))

    def test_t0_3_csv_selects_canonical_duplicate_phase_evidence(self):
        """Reuse the T0-3-selected listing when a source-only duplicate exists.

        The 1.10 V/L2/3000 ps/-500 ps physical deck has two PASS directories
        with identical HSPICE scalar measurements.  The generic reuse helper
        must remain conservative about such duplicates, while T0-5's explicit
        T0-3 reuse must consume the compact phase-window authority row rather
        than rerunning a completed electrical point or choosing a directory
        by incidental filesystem order.
        """

        spec = next(item for item in study.T0_5A_SPECS if item["scenario_key"] == "t0_5a_1p10_l2_long")
        authority = next(
            item for item in study.t0_3_reusable_rows(spec)
            if float(item["phase_ps"]) == -500.0
        )
        parameters = study.parameters_for(1.10, "L2", 0.96, 3000.0, -500.0)
        stats = {"new": 0, "reused": 0}
        row = study.reuse_t0_3_authority_row(
            parameters, study.render_deck(self.context, parameters), authority, stats,
        )
        self.assertEqual(authority["scenario_id"], row["scenario_id"])
        self.assertIn("/r103/", row["scenario_path"])
        self.assertEqual(row["evidence_source"], "REUSED_T0_3_AUTHORITY_ROW")
        self.assertEqual(stats["new"], 0)
        self.assertEqual(stats["reused_electrical"], 1)

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
