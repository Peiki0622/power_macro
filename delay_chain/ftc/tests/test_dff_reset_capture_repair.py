"""No-HSPICE contracts for the FTC DFF reset-arm revalidation.

These tests intentionally inspect the generated diagnostic deck instead of
running it.  They prevent the old release-at-launch modelling defect, factor
creep, and accidental expansion into DFF cell screening before licensed
simulation is permitted.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_dff_reset_capture_repair as study  # noqa: E402


class DffResetCaptureRepairTests(unittest.TestCase):
    """Protect the planned reset-arm experiment before HSPICE is authorized."""

    @classmethod
    def setUpClass(cls):
        cls.baseline = study.freeze_baseline()
        cls.schedule = study.build_diagnostic_schedule()
        cls.deck = study.render_diagnostic_deck(study.context(), cls.schedule)

    def test_freeze_records_the_prior_release_at_launch_defect(self):
        """The new study cannot silently treat the old reset factor as valid."""
        self.assertTrue(self.baseline["old_root_schedule_reset_release_equals_launch"])
        self.assertEqual(self.baseline["legacy_reset_arm_s"], study.LEGACY_ARM_S)
        self.assertTrue(all(value == 0 for value in self.baseline["old_reruns"].values()))

    def test_matrix_has_only_the_approved_independent_factors(self):
        """Reset arm and reset-high pad remain the only target timing factors."""
        targets = [probe for probe in self.schedule["probes"] if probe["kind"] == "target"]
        self.assertEqual(tuple(study.RESET_ARM_VALUES), (0.0, 0.49e-9, 1.0e-9))
        self.assertEqual(tuple(study.TIMELINE_PAD_VALUES), (0.0, 0.51e-9))
        self.assertEqual({probe["predecessor_M"] for probe in targets}, {7, 8, 9})
        self.assertEqual({probe["reset_arm_s"] for probe in targets}, set(study.RESET_ARM_VALUES))
        self.assertEqual({probe["timeline_pad_s"] for probe in targets}, set(study.TIMELINE_PAD_VALUES))
        self.assertEqual(len(self.schedule["episodes"]), 30)

    def test_reset_arm_is_real_and_m_updates_are_serial(self):
        """Every pulse releases reset before launch by the named arm interval."""
        self.assertTrue(all(abs(probe["launch_time_s"] - probe["reset_release_s"] - probe["reset_arm_s"]) < 1e-21 for probe in self.schedule["probes"]))
        self.assertTrue(all(abs(item["new_M"] - item["old_M"]) == 1 for item in self.schedule["transitions"]))
        self.assertTrue(all(probe["F"] == 0 for probe in self.schedule["probes"]))

    def test_deck_measures_dff_boundary_and_excludes_early_scope(self):
        """Actual reset/clock crossings, Q double-read, and DFF nodes are required."""
        checks = study.topology_checks(self.deck, self.schedule)
        self.assertTrue(all(checks.values()), checks)
        for node in study.DFF_INTERNAL_NODES:
            self.assertIn("XDFF." + node, self.deck)
        for token in ("_reset_release50", "_sclk_launch50", "_q_read_late_v", "_dff_ck_rise50_2"):
            self.assertIn(token, self.deck)
        self.assertNotIn("CONFIG_SKIP", self.deck)
        self.assertNotIn("DFFRPQ_X1M", self.deck)

    def test_phase0_never_calls_hspice(self):
        """The freeze phase cannot consume the diagnostic scenario budget."""
        with tempfile.TemporaryDirectory(prefix="ftc_dff_reset_phase0_") as temporary:
            root = Path(temporary)
            with mock.patch.object(study, "validate_hspice", side_effect=AssertionError("phase0 launched HSPICE")), mock.patch.object(study, "execute_scenario", side_effect=AssertionError("phase0 launched HSPICE")):
                self.assertEqual(study.main(["--phase", "phase0", "--analysis-dir", str(root / "analysis"), "--run-root", str(root / "runs")]), 0)
            self.assertFalse((root / "runs").exists())

    def test_classification_compares_pad_controls_in_seconds(self):
        """Pad sensitivity must use stored seconds, not a nanosecond dictionary key.

        A fully passing synthetic matrix exercises the parser-side gate without
        HSPICE.  It specifically protects the 0.51 ns control from being looked
        up as the incompatible floating-point value 0.51.
        """
        rows = []
        for predecessor in (7, 8, 9):
            for arm in study.RESET_ARM_VALUES:
                for pad in study.TIMELINE_PAD_VALUES:
                    rows.append({
                        "kind": "target", "condition": "p{}_a{}_t{}".format(predecessor, arm, pad),
                        "predecessor_M": predecessor, "reset_arm_s": arm,
                        "reset_release_s": 0.0, "launch_time_s": arm,
                        "timeline_pad_s": pad, "D_total_ps": 100.0,
                        "valid": 1, "Q_logic": 1, "Q_late_logic": 1,
                    })
        result = study.classify(rows, [], [])
        self.assertFalse(result["timeline_pad_sensitive"])
        self.assertIsNone(result["selected_reset_arm_s"])
        self.assertEqual(result["primary_classification"], "dff_falling_data_hold_aperture_boundary")

    def test_return_ck_after_active_end_is_not_an_extra_edge(self):
        """A legal return after reset reassertion belongs to recovery, not capture."""
        probe = dict(self.schedule["probes"][0])
        prefix = "p{}".format(probe["probe_index"])
        record = {
            prefix + "_reset_release50": probe["reset_release_s"],
            prefix + "_sclk_launch50": probe["launch_time_s"],
            prefix + "_xor_29_rise_50": probe["launch_time_s"] + 1e-12,
            prefix + "_xor_29_fall_50": probe["launch_time_s"] + 2e-9,
            prefix + "_medium_out_rise_50": probe["launch_time_s"] + 2e-12,
            prefix + "_dff_ck_rise_50": probe["launch_time_s"] + 3e-12,
            prefix + "_dff_ck_rise50_2": probe["reset_assert_start_s"] + 1e-12,
            prefix + "_q_read_v": study.VDD,
            prefix + "_q_read_late_v": study.VDD,
        }
        row = study.parse_probe(record, probe)
        self.assertFalse(row["extra_ck_edge"])
        self.assertEqual(row["valid"], 1)

    def test_transition_edge_after_quiet_end_is_ignored(self):
        """An unbounded WHEN result from a later probe cannot fail quiet time."""
        transition = self.schedule["transitions"][0]
        window = study.transition_window(self.schedule, transition)
        self.assertIsNotNone(window)
        record = {"tr0_xor_max": 0.0, "tr0_medium_max": 0.0, "tr0_ck_max": 0.0,
                  "tr0_ck_rise_1": window[1] + 1e-12, "tr0_ck_rise_2": window[1] + 2e-12}
        row = study.parse_transition(record, transition, 0, window)
        self.assertEqual(row["configuration_ck_edge_count"], 0)
        self.assertEqual(row["status"], "PASS")

    def test_missing_transition_window_or_measure_is_invalid(self):
        """Cleanup and failed bounded measurements must never become PASS rows."""
        transition = self.schedule["transitions"][-1]
        self.assertEqual(study.parse_transition({}, transition, 503, None)["status"], "INVALID")
        measured = self.schedule["transitions"][0]
        window = study.transition_window(self.schedule, measured)
        self.assertEqual(study.parse_transition({"tr0_xor_max": 0.0}, measured, 0, window)["status"], "INVALID")

    def test_completed_diagnostic_is_reused_without_a_second_hspice_launch(self):
        """An exact PASS manifest must return its retained measurements only.

        This test protects the one-scenario budget.  A subprocess replacement
        raises if the runner tries to launch HSPICE after finding the exact
        scenario identity, while the measurement parser supplies a small
        retained record without requiring any simulator collateral.
        """
        with tempfile.TemporaryDirectory(prefix="ftc_dff_reset_reuse_") as temporary:
            run_root = Path(temporary) / "runs"
            deck = "* retained diagnostic deck\n.end\n"
            parameters = {"study": study.STUDY, "phase": "acceptance_v3_0p80_normal"}
            identity = "acceptance_v3_0p80_normal__" + study.hashlib.sha256(study.json.dumps(parameters, sort_keys=True).encode("ascii")).hexdigest()[:20]
            scenario = run_root / "r1" / "scenarios" / identity
            scenario.mkdir(parents=True)
            study.write_json(scenario / "scenario_manifest.json", {
                "netlist_sha256": study.hashlib.sha256(deck.encode("ascii")).hexdigest(),
                "parameters": parameters, "completion_status": "PASS",
                "measurement_file": "retained.mt0.csv",
            })
            expected = {"retained": 1.0}
            with mock.patch.object(study.history.run_dc_sweep, "parse_measurements", return_value=expected) as parse, mock.patch.object(study.subprocess, "run", side_effect=AssertionError("unexpected HSPICE launch")):
                record, reused = study.execute_scenario(Path("/not-called"), "not-used", run_root, deck, parameters, "acceptance_v3_0p80_normal")
            self.assertEqual(record, expected)
            self.assertEqual(reused, scenario)
            parse.assert_called_once_with(scenario / "retained.mt0.csv")

    @staticmethod
    def synthetic_rows(schedule, coarse_boundary=9, fine_boundary=9, fallback=False):
        """Build compact electrical rows for the v3 classifier tests.

        Coarse pairs become low at the requested boundary.  In a normal case
        the first fine base has ``fine_boundary``; in the fallback case that
        base remains high through K-1 and the next base gets the boundary.
        """
        rows = []
        for probe in schedule["probes"]:
            phase, fine, medium = probe["protocol_phase"], probe["fine_code"], probe["medium_code"]
            state = "stable_high"
            if phase in ("coarse_scan", "coarse_repeat") and medium >= coarse_boundary:
                state = "stable_low"
            if phase.startswith("fine_m{}_".format(schedule["fine_bases"][0])):
                if not fallback and fine >= fine_boundary:
                    state = "stable_low"
            if fallback and phase.startswith("fine_m{}_".format(schedule["fine_bases"][1])) and fine >= fine_boundary:
                state = "stable_low"
            rows.append({"vdd_v": schedule["vdd_v"], "probe_index": probe["probe_index"],
                         "protocol_phase": phase,
                         "medium_code": medium, "fine_code": fine, "q_state": state,
                         "electrical_valid": 1, "reason": None, "active_ck_edge_count": 1,
                         "recovery_max_ratio": 0.01})
        return rows

    def test_protocol_uses_allowed_coarse_windows_and_bases(self):
        """The reference contains windows, not a predicted measured result."""
        references = study.retained_protocol_reference()
        self.assertEqual({key: item["allowed_boundaries"] for key, item in references.items()},
                         {"0.80": [9, 10], "0.95": [6, 7], "1.10": [4, 5]})
        self.assertEqual({key: item["fine_bases"] for key, item in references.items()},
                         {"0.80": [7, 8, 9], "0.95": [4, 5, 6], "1.10": [2, 3, 4]})
        self.assertFalse(any("predicted" in key for item in references.values() for key in item))

    def test_coarse_pair_requires_two_stable_low_reads(self):
        """A high/low disagreement cannot confirm an aperture boundary."""
        schedule = study.build_guarded_trajectory(study.retained_protocol_reference()["0.80"], False)
        rows = self.synthetic_rows(schedule, coarse_boundary=9, fine_boundary=9)
        pair = [row for row in rows if row["medium_code"] == 9 and row["protocol_phase"] in ("coarse_scan", "coarse_repeat")]
        pair[0]["q_state"] = "stable_high"
        for row in rows:
            if row["protocol_phase"].startswith("fine_m8_") and row["fine_code"] >= 9:
                row["q_state"] = "stable_low"
        result = study.evaluate_guarded_scenario("coarse_disagreement", schedule, rows, [])
        self.assertEqual(result["coarse_boundary"], 10)
        self.assertEqual(result["selected_medium_base"], 8)

    def test_coarse_boundary_must_be_inside_allowed_window(self):
        """A measured pair outside the pre-rendered window blocks acceptance."""
        schedule = study.build_guarded_trajectory(study.retained_protocol_reference()["0.80"], False)
        rows = self.synthetic_rows(schedule, coarse_boundary=10, fine_boundary=9)
        schedule["allowed_boundaries"] = [9]
        result = study.evaluate_guarded_scenario("coarse_outside_window", schedule, rows, [])
        self.assertIn("coarse_boundary_outside_allowed_window", result["reasons"])

    def test_absent_coarse_boundary_is_rejected(self):
        """All-high coarse observations cannot silently choose a base."""
        schedule = study.build_guarded_trajectory(study.retained_protocol_reference()["0.80"], False)
        rows = self.synthetic_rows(schedule, coarse_boundary=99, fine_boundary=9)
        result = study.evaluate_guarded_scenario("coarse_missing", schedule, rows, [])
        self.assertIn("coarse_boundary_missing", result["reasons"])
        self.assertIsNone(result["selected_medium_base"])

    def test_every_fine_code_has_consecutive_scan_and_repeat_probes(self):
        """Any measured boundary must already have an independent next-code hold."""
        reference = study.retained_protocol_reference()["0.80"]
        normal = study.build_guarded_trajectory(reference, False)
        pairs = [probe for probe in normal["probes"] if probe["protocol_phase"].startswith("fine_m7_")]
        self.assertEqual([(probe["fine_code"], probe["protocol_phase"]) for probe in pairs],
                         [(fine, phase) for fine in range(study.dynamic.FINE_K + 1)
                          for phase in ("fine_m7_scan", "fine_m7_repeat")])
        for scan, repeat in zip(pairs[::2], pairs[1::2]):
            self.assertEqual((scan["medium_code"], scan["fine_code"]),
                             (repeat["medium_code"], repeat["fine_code"]))
            self.assertNotEqual(scan["probe_index"], repeat["probe_index"])

    def test_normal_and_single_fallback_algorithms(self):
        """Normal and one allowed fine-base fallback both converge."""
        reference = study.retained_protocol_reference()["0.80"]
        normal = study.build_guarded_trajectory(reference, False)
        normal_result = study.evaluate_guarded_scenario("normal", normal, self.synthetic_rows(normal, fine_boundary=9), [])
        fallback = study.build_guarded_trajectory(reference, False)
        fallback_result = study.evaluate_guarded_scenario("fallback", fallback, self.synthetic_rows(fallback, fine_boundary=9, fallback=True), [])
        self.assertEqual(normal_result["status"], "GO", normal_result)
        self.assertEqual(fallback_result["status"], "GO", fallback_result)
        self.assertFalse(normal_result["fallback_used"])
        self.assertTrue(fallback_result["fallback_used"])
        self.assertEqual((normal_result["selected_medium_base"], normal_result["guard_code"]), (7, 10))
        self.assertEqual((fallback_result["selected_medium_base"], fallback_result["guard_code"]), (8, 10))
        self.assertNotEqual(normal_result["guard_probe_index"], normal_result["lock_hold_probe_index"])
        self.assertNotEqual(fallback_result["guard_probe_index"], fallback_result["lock_hold_probe_index"])

    def test_ambiguous_scan_can_mark_boundary_but_not_guard(self):
        """Aperture ambiguity locates a boundary but can never accept a lock."""
        schedule = study.build_guarded_trajectory(study.retained_protocol_reference()["0.95"], False)
        rows = self.synthetic_rows(schedule, coarse_boundary=6, fine_boundary=5)
        next(row for row in rows if row["protocol_phase"] == "fine_m4_scan" and row["fine_code"] == 5)["q_state"] = "ambiguous"
        accepted = study.evaluate_guarded_scenario("ambiguous_boundary", schedule, rows, [])
        self.assertEqual(accepted["status"], "GO", accepted)
        self.assertEqual((accepted["fine_boundary"], accepted["guard_code"]), (5, 6))

        next(row for row in rows if row["protocol_phase"] == "fine_m4_scan" and row["fine_code"] == 6)["q_state"] = "ambiguous"
        rejected = study.evaluate_guarded_scenario("ambiguous_guard", schedule, rows, [])
        self.assertIn("guard_not_stable_low", rejected["reasons"])

    def test_fine_boundary_at_k_has_no_legal_guard(self):
        """F=K cannot lock because the required one-step guard is out of range."""
        reference = study.retained_protocol_reference()["0.80"]
        schedule = study.build_guarded_trajectory(reference, False)
        rows = self.synthetic_rows(schedule, fine_boundary=study.dynamic.FINE_K)
        next(row for row in rows if row["protocol_phase"] == "fine_m8_scan" and row["fine_code"] == study.dynamic.FINE_K)["q_state"] = "stable_low"
        result = study.evaluate_guarded_scenario("limit", schedule, rows, [])
        self.assertEqual(result["status"], "NO-GO")
        self.assertIn("fine_guard_out_of_range", result["reasons"])

    def test_guard_and_lock_hold_each_require_stable_low(self):
        """Neither an ambiguous guard nor a high lock-hold may be accepted."""
        reference = study.retained_protocol_reference()["0.80"]
        schedule = study.build_guarded_trajectory(reference, False)
        guard_rows = self.synthetic_rows(schedule, fine_boundary=9)
        next(row for row in guard_rows if row["protocol_phase"] == "fine_m7_scan" and row["fine_code"] == 10)["q_state"] = "ambiguous"
        guard_result = study.evaluate_guarded_scenario("guard_fail", schedule, guard_rows, [])
        self.assertIn("guard_not_stable_low", guard_result["reasons"])
        hold_rows = self.synthetic_rows(schedule, fine_boundary=9)
        next(row for row in hold_rows if row["protocol_phase"] == "fine_m7_repeat" and row["fine_code"] == 10)["q_state"] = "stable_high"
        hold_result = study.evaluate_guarded_scenario("hold_fail", schedule, hold_rows, [])
        self.assertIn("lock_hold_not_stable_low", hold_result["reasons"])

    def test_fallback_is_forbidden_after_an_early_primary_boundary(self):
        """A usable boundary in the first base cannot be hidden by fallback."""
        schedule = study.build_guarded_trajectory(study.retained_protocol_reference()["0.80"], False)
        rows = self.synthetic_rows(schedule, fine_boundary=8, fallback=True)
        next(row for row in rows if row["protocol_phase"] == "fine_m7_scan" and row["fine_code"] == 8)["q_state"] = "stable_low"
        result = study.evaluate_guarded_scenario("illegal_fallback", schedule, rows, [])
        self.assertFalse(result["fallback_used"])
        self.assertEqual(result["selected_medium_base"], 7)

    def test_protocol_contract_generation_never_calls_hspice(self):
        """All three decks and contracts must exist before simulator preflight."""
        with tempfile.TemporaryDirectory(prefix="ftc_dff_protocol_") as temporary:
            root = Path(temporary)
            with mock.patch.object(study, "validate_hspice", side_effect=AssertionError("protocol launched HSPICE")), mock.patch.object(study, "execute_scenario", side_effect=AssertionError("protocol launched HSPICE")):
                self.assertEqual(study.main(["--phase", "protocol", "--analysis-dir", str(root / "analysis"), "--run-root", str(root / "runs")]), 0)
            contract = study.load_json(root / "analysis" / "guarded_lock_contract.json")
            self.assertEqual(len(contract["scenarios"]), 3)
            self.assertEqual(contract["protocol_revision"], study.PROTOCOL_REVISION)
            self.assertTrue(all(item["decision"] == "GO" for item in contract["scenarios"].values()))
            final_times = {item["schedule"]["final_time_s"] for item in contract["scenarios"].values()}
            self.assertEqual(len(final_times), 1)
            self.assertNotIn("predicted_fine_boundary", study.json.dumps(contract))
            self.assertNotIn("predicted_guard_code", study.json.dumps(contract))
            self.assertFalse((root / "runs").exists())

    def test_recovery_diagnostic_derives_guard_from_full_v3_schedule(self):
        """The diagnostic uses return-fall timing, not the old 2.7 ns constant."""
        timing = study.acceptance_timing()
        timing["recovery_guard_s"] = study.RECOVERY_DIAGNOSTIC_S
        trajectory = study.build_guarded_trajectory(study.retained_protocol_reference()["0.80"])
        schedule = study.dynamic.schedule_trajectory(trajectory, timing)
        record = {}
        for probe in schedule["probes"]:
            index = probe["probe_index"]
            for suffix in ("xor", "medium", "ck"):
                prefix = "p{}".format(index)
                record["{}_return_{}_rise10".format(prefix, suffix)] = probe["sclk_fall_s"] + 1.0e-9
                record["{}_return_{}_fall10".format(prefix, suffix)] = probe["sclk_fall_s"] + 2.0e-9
                record["{}_return_{}_rise10_2".format(prefix, suffix)] = None
                record["{}_recovery_{}_end".format(prefix, suffix)] = 0.0
                record["{}_recovery_{}_tail_max".format(prefix, suffix)] = 0.0
                record["{}_recovery_{}_tail_min".format(prefix, suffix)] = -0.01
        rows, summary = study.parse_recovery_diagnostic_rows("synthetic", schedule, record)
        self.assertEqual(len(rows), len(schedule["probes"]) * 3)
        self.assertAlmostEqual(summary["candidate_recovery_guard_s"], 2.2e-9, places=21)
        self.assertEqual(summary["invalid_row_count"], 0)

    def test_recovery_diagnostic_deck_contains_bounded_return_measures(self):
        """The widened diagnostic measures all three nodes and both tail signs."""
        timing = study.acceptance_timing()
        timing["recovery_guard_s"] = study.RECOVERY_DIAGNOSTIC_S
        trajectory = study.build_guarded_trajectory(study.retained_protocol_reference()["0.80"])
        schedule = study.dynamic.schedule_trajectory(trajectory, timing)
        deck = study.render_recovery_diagnostic_deck(study.context(), timing, schedule)
        self.assertIn("p0_return_ck_fall10", deck)
        self.assertIn("p0_recovery_ck_tail_max", deck)
        self.assertIn("p0_recovery_ck_tail_min", deck)
        self.assertTrue(all(abs(value["recovery_end_s"] - value["sclk_fall_s"] - study.RECOVERY_DIAGNOSTIC_S) < 1.0e-21 for value in schedule["probes"]))


if __name__ == "__main__":
    unittest.main()
