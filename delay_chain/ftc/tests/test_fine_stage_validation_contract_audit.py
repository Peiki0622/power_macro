"""Static regressions for the fine-stage validation-contract audit.

These tests intentionally parse retained r2 evidence but never launch HSPICE.
Electrical acceptance is supplied only by the bounded Phase-2/3 runner flow.
"""

import importlib.util
import inspect
import tempfile
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = FTC_ROOT / "scripts" / "run_fine_stage_validation_contract_audit.py"
SPEC = importlib.util.spec_from_file_location("fine_stage_validation_contract_audit", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class FineStageValidationContractAuditTests(unittest.TestCase):
    """Protect the narrow audit boundary before licensed simulation begins."""

    @classmethod
    def setUpClass(cls):
        """Load immutable inputs once; this only hashes and parses local evidence."""

        cls.context = RUNNER.frozen_context()

    def test_phase1_uses_only_r2_raw_readback_and_never_dispatches_hspice(self):
        """The decisive r2 reparse must stay read-only and cannot invoke a simulator."""

        source = inspect.getsource(RUNNER.legacy_reclassification)
        self.assertEqual(RUNNER.RAW_R2_NAME, "r2")
        self.assertNotIn("validate_hspice", source)
        self.assertNotIn("CORE.execute", source)
        self.assertIn("parse_measurements", source)
        self.assertEqual(len(list((RUNNER.raw_root() / "scenarios").glob("*/scenario_manifest.json"))), 378)

    def test_phase1_reparse_does_not_mutate_historical_validity_or_csv(self):
        """Readback may classify copies, but cannot alter the published r2 table."""

        historical = FTC_ROOT / "analysis" / "standard_cell_load_fine_stage_driver_codesign" / "driver_0P8" / "coupled_medium_coverage.csv"
        before = RUNNER.sha256_file(historical)
        rows = RUNNER.legacy_reclassification(self.context)
        self.assertEqual(len(rows), 378)
        self.assertEqual(before, RUNNER.sha256_file(historical))
        self.assertTrue(all(isinstance(row["legacy_valid"], bool) for row in rows))

    def test_crossing_contract_ignores_absolute_sample_values_and_distinguishes_failures(self):
        """A delayed full pulse is valid even when a hypothetical old sample would miss it."""

        pulse = {
            "t_out_rise_10": 2.0, "t_out_rise": 2.1, "t_out_rise_90": 2.2,
            "t_out_fall_90": 3.0, "t_out_fall": 3.1, "t_out_fall_10": 3.2,
            "t_out_rise_2": None, "t_out_fall_2": None,
            # The new gate intentionally has no dependency on these fields.
            "out_logic_high": 0.0, "out_logic_low": 1.0,
        }
        self.assertTrue(RUNNER.one_cycle_waveform(pulse)["valid"])
        self.assertEqual(RUNNER.reclassification_label(False, True, False, True), "legacy_fixed_sample_miss")
        self.assertEqual(RUNNER.reclassification_label(False, False, False, True), "electrical_waveform_failure")
        broken = dict(pulse, t_out_rise_90=None)
        self.assertIn("missing_90_percent_crossing", RUNNER.one_cycle_waveform(broken)["reasons"])

    def test_contract_freezes_ratios_primary_candidate_and_forbidden_scope(self):
        """No relaxed threshold or hardware-search knob may enter this task."""

        requirements = RUNNER.requirement_document(self.context)
        self.assertEqual((requirements["legacy_high_ratio"], requirements["legacy_low_ratio"]), (0.90, 0.10))
        self.assertEqual((requirements["primary_candidate_driver"], requirements["fixed_load"], requirements["primary_candidate_K"]), (RUNNER.PRIMARY_DRIVER, RUNNER.PRIMARY_LOAD, 10))
        for field in ("new_hardware_search", "load_rescan", "driver_rescan", "medium_change", "sensor", "droop_sweep", "pvt", "rtl", "layout"):
            self.assertEqual(requirements[field], "forbidden")
        self.assertEqual(requirements["bypass"], "future_work")
        self.assertEqual(requirements["config_skip"], "future_work")

    def test_two_cycle_schedule_is_exactly_one_plus_eighteen_approved_endpoints(self):
        """The only runnable hardware points are the mandated worst point and boundaries."""

        self.assertEqual((15, RUNNER.PRIMARY_K, 0.80), (15, 10, 0.80))
        schedule = RUNNER.phase3_schedule()
        self.assertEqual(len(schedule), 18)
        self.assertEqual(set(schedule), {
            (medium, fine, vdd)
            for medium in (0, 1, 7, 8, 15, 16)
            for fine in (0, 10)
            for vdd in RUNNER.CORE.ANCHOR_VDD
            if (medium, fine) in ((0, 10), (1, 0), (7, 10), (8, 0), (15, 10), (16, 0))
        })
        self.assertLessEqual(1 + len(schedule), 19)
        self.assertNotIn("BUF_X1M_A9TL40", inspect.getsource(RUNNER.phase3_schedule))

    def test_two_cycle_deck_changes_only_observation_and_matches_r2_physical_topology(self):
        """Every new deck must retain the frozen medium, driver, and ten NOR loads."""

        deck = RUNNER.render_two_cycle_deck(self.context, 15, 10, 0.80)
        reference = RUNNER.reference_deck(self.context, 15, 10, 0.80).read_text(encoding="ascii")
        self.assertEqual(RUNNER.physical_prefix(deck), RUNNER.physical_prefix(reference))
        self.assertIn("XFINE_DRIVER out vdd_a vdd_a vss_a vss_a medium_out BUF_X0P8M_A9TL40", deck)
        self.assertEqual(sum(line.startswith("XLOAD_") for line in deck.splitlines()), 10)
        self.assertIn("t_out_rise_90_2", deck)
        self.assertNotIn("out_logic_high FIND", deck)
        for forbidden in ("XBYPASS", "XCONFIG_SKIP", "DFF", "XOR", "CAP"):
            self.assertNotIn(forbidden, deck)

    def test_two_cycle_gate_requires_positive_windows_and_no_extra_crossings(self):
        """A passing two-cycle result must contain the first pulse and second rise only."""

        record = {
            "t_in_rise_1": 1.0,
            "t_out_rise_10_1": 2.0, "t_out_rise_50_1": 2.1, "t_out_rise_90_1": 2.2,
            "t_out_fall_90_1": 3.0, "t_out_fall_50_1": 3.1, "t_out_fall_10_1": 3.2,
            "t_out_rise_10_2": 8.0, "t_out_rise_50_2": 8.1, "t_out_rise_90_2": 8.2,
            "t_out_rise_50_3": None, "t_out_fall_50_2": None,
        }
        self.assertTrue(RUNNER.two_cycle_waveform(record)["valid"])
        self.assertFalse(RUNNER.two_cycle_waveform(dict(record, t_out_fall_50_2=9.0))["valid"])
        self.assertFalse(RUNNER.two_cycle_waveform(dict(record, t_out_rise_10_2=3.1))["valid"])

    def test_summary_records_zero_historical_reruns_and_enforces_budget(self):
        """Publication must expose both the historical boundary and the 19-run cap."""

        phase1 = {"phase1_go": True}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index in range(19):
                scenario = root / "r1" / "scenarios" / str(index)
                scenario.mkdir(parents=True)
                RUNNER.write_json(scenario / "scenario_manifest.json", {"completion_status": "PASS"})
            result = RUNNER.summary_document(phase1, {"valid": True}, [{"valid": True}] * 18, root, "Fine-Stage Delay-Line Waveform Contract = GO", [])
        self.assertEqual(result["historical_driver_codesign_rerun"], 0)
        self.assertEqual(result["new_hspice_scenarios"], 19)
        self.assertEqual(result["phase3"]["status"], "GO")
        source = inspect.getsource(RUNNER.main)
        self.assertIn("if not phase2[\"valid\"]", source)
        self.assertIn("if not row[\"valid\"]", source)

    def test_report_readback_retains_all_driver_counts_and_phase2_crossings(self):
        """Final report data must come from retained task evidence, never inferred values."""

        analysis = FTC_ROOT / "analysis" / "fine_stage_validation_contract_audit"
        if not (analysis / "two_cycle_waveforms.csv").is_file():
            self.skipTest("two-cycle HSPICE evidence has not been generated yet")
        counts = RUNNER.classification_counts(analysis)
        self.assertEqual({driver: item["complete_crossing"] for driver, item in counts.items()}, {
            "BUF_X0P8M_A9TL40": 86, "BUF_X1M_A9TL40": 89,
            "BUF_X1P4M_A9TL40": 97, "BUF_X2M_A9TL40": 106,
        })
        phase2, phase3 = RUNNER.saved_two_cycle_rows(analysis / "two_cycle_waveforms.csv")
        crossings = RUNNER.phase2_crossings(FTC_ROOT / "runs" / "fine_stage_validation_contract_audit", phase2)
        self.assertEqual(len(phase3), 18)
        self.assertIsNotNone(crossings["t_out_rise_90_1"])
        self.assertIsNotNone(crossings["t_out_fall_10_1"])


if __name__ == "__main__":
    unittest.main()
