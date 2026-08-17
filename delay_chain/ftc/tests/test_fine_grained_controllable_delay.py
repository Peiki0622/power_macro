"""Pure regressions for the FTC fine-grained controllable-delay runner.

These tests intentionally exercise only deterministic parsing, scheduling, and
deck rendering.  They must never launch HSPICE: retained raw runs, rather than
unit-test fixtures, are the source of electrical evidence.
"""

import importlib.util
import json
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = FTC_ROOT / "scripts" / "run_fine_grained_controllable_delay.py"
SPEC = importlib.util.spec_from_file_location("fine_grained_controllable_delay", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class FineGrainedControllableDelayTests(unittest.TestCase):
    """Protect the fixed architecture and the bounded stage scheduler."""

    def setUp(self):
        """Load immutable local contracts without creating any run directory."""

        self.config = RUNNER.load_json(FTC_ROOT / "ftc_config.json")
        self.cells = RUNNER.load_json(FTC_ROOT / "discovery/selected_cells.json")

    def test_phase0_uses_real_dff_evidence_and_fixed_range(self):
        """Requirements must preserve 0.80--1.10 V and the real-DFF bracket."""

        frozen = RUNNER.verify_frozen_evidence()
        requirements = RUNNER.build_requirements(frozen)
        self.assertEqual(requirements["formal_vdd_range_v"], [0.80, 1.10])
        self.assertEqual(set(requirements["real_boundary_brackets_by_vdd"]), {
            "0.80", "0.85", "0.90", "0.95", "1.00", "1.05", "1.10",
        })
        self.assertGreater(requirements["required_delay_ratio_lower_bound"], 3.0)
        self.assertEqual(requirements["high_vdd_boundary_bracket"]["D_last_Q1_ps"], 231.43456200000003)
        self.assertEqual(requirements["low_vdd_boundary_bracket"]["D_first_Q0_ps"], 848.4663350000002)

    def test_thermometer_code_changes_exactly_one_unit(self):
        """C+1 must change one physical unit from FAST to SLOW, never a pattern."""

        for units in (1, 8, 17):
            for code in range(units):
                before = RUNNER.thermometer_bits(units, code)
                after = RUNNER.thermometer_bits(units, code + 1)
                changed = [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
                self.assertEqual(changed, [code])
                self.assertEqual(before[code], 0)
                self.assertEqual(after[code], 1)

    def test_rendered_decks_keep_only_the_fixed_architecture(self):
        """Deck text proves the new chain has no old tap tree or large MUX path."""

        unit = RUNNER.render_unit_deck(self.config, self.cells, 0.95, "SLOW")
        chain = RUNNER.render_chain_deck(self.config, self.cells, 0.95, 8, 3, dff_load=False)
        system = RUNNER.render_system_deck(self.config, self.cells, 0.95, 8, 3)
        self.assertIn("XUNIT_BUF", unit)
        self.assertIn("XUNIT_MUX", unit)
        self.assertEqual(sum(line.startswith("XU") and "_MUX" in line for line in chain.splitlines()), 8)
        self.assertEqual(sum(line.startswith("V_EN_") for line in chain.splitlines()), 8)
        self.assertEqual(sum(line.startswith("XXOR_") for line in system.splitlines()), 30)
        self.assertIn("XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29", system)
        for forbidden in ("XMUX_L1", "XMUX_L2", "XMUX_L3", "thr_tap_", "code0", "code1", "code2"):
            self.assertNotIn(forbidden, chain)

    def test_fixed_sensor_and_standard_cells_are_preserved(self):
        """The runner's constants must agree with selected-cell collateral."""

        RUNNER.validate_config(self.config)
        RUNNER.validate_cells(self.cells)
        self.assertEqual(RUNNER.TAP_INDEX, 29)
        self.assertEqual(RUNNER.XOR_CELL, "XOR2_X0P5M_A9TR40")
        self.assertEqual(RUNNER.DFF_CELL, "DFFRPQ_X0P5M_A9TR40")
        self.assertEqual(RUNNER.ANCHOR_VDD, (1.10, 0.95, 0.80))

    def test_candidate_b_review_is_bounded_and_does_not_invent_a_cell(self):
        """The one static review may block B, but must never create a third choice."""

        review = RUNNER.review_candidate_b()
        self.assertEqual(review["decision"], "ARCHITECTURE_BLOCKED")
        self.assertEqual(review["candidate_count"], 0)
        self.assertIn("output-inverting", review["reason"])

    def test_sizing_is_pure_python_and_does_not_call_hspice(self):
        """Sizing consumes synthetic rows only, so offline stage 3 has no runner hook."""

        requirements = RUNNER.build_requirements(RUNNER.verify_frozen_evidence())
        unit_rows = [
            {"vdd_v": vdd, "t_fast_rise_ps": 10.0, "t_slow_rise_ps": 40.0}
            for vdd in RUNNER.ANCHOR_VDD
        ]
        short_rows = [
            {"vdd_v": vdd, "code": code, "D_code_ps": 10.0 + 10.0 * 8 + 30.0 * code}
            for vdd in RUNNER.ANCHOR_VDD for code in range(9)
        ]
        result = RUNNER.size_chain(unit_rows, short_rows, requirements)
        self.assertIn(result["decision"], ("GO", "NO-GO"))
        self.assertNotIn("scenario_count", result)

    def test_local_calibration_search_never_expands_to_all_codes(self):
        """A valid first-zero can be located only in the documented ±2 window."""

        rows = []
        for code, q_value in ((2, 1), (3, 1), (4, 0), (5, 0), (6, 0)):
            rows.append({"code": code, "valid": 1, "Q": q_value, "D_code_ps": float(code) * 10.0})
        self.assertEqual(RUNNER.find_lock(rows, predicted_k=4, units=8), 4)
        self.assertIsNone(RUNNER.find_lock(rows, predicted_k=1, units=8))

    def test_early_stop_summary_marks_every_later_stage_not_run(self):
        """A unit NO-GO cannot be misreported as a later electrical success."""

        stages = RUNNER.stage_summary(unit={"decision": "NO-GO"})
        self.assertEqual(stages["Unit Cell"], "NO-GO")
        for name, status in stages.items():
            if name != "Unit Cell":
                self.assertEqual(status, "NOT_RUN")

    def test_historical_runner_loops_are_not_imported(self):
        """The new experiment may share parser helpers but must not call old loops."""

        source = RUNNER_PATH.read_text(encoding="utf-8")
        for old_runner in (
            "run_static_self_calibration", "run_programmable_acceptance_window",
            "run_delay_code_refinement",
        ):
            self.assertNotIn("import " + old_runner, source)
        self.assertIn("import run_dc_sweep", source)

    def test_public_requirements_file_is_json_object_shaped(self):
        """The generated Phase 0 artifact remains consumable by later stages."""

        path = FTC_ROOT / "analysis/fine_grained_controllable_delay/requirements.json"
        if path.is_file():
            self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)


if __name__ == "__main__":
    unittest.main()
