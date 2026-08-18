"""Pure Python regression for the bounded intermediate-size sweep.

These tests never launch HSPICE.  They protect the static library contract,
deck topology, four-metric reduction, deterministic winner ordering, and the
explicit separation from historical FTC runners.
"""

import importlib.util
import json
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = FTC_ROOT / "scripts" / "run_standard_cell_load_size_sweep.py"
SPEC = importlib.util.spec_from_file_location("standard_cell_load_size_sweep", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class StandardCellLoadSizeSweepTests(unittest.TestCase):
    """Check deterministic scope and arithmetic without substituting smoke SPICE."""

    def setUp(self):
        self.config = RUNNER.load_json(FTC_ROOT / "ftc_config.json")
        self.interface, self.cells, self.paths = RUNNER.freeze_inputs()
        self.document = RUNNER.discover_size_candidates(self.cells)
        self.candidates = {item["candidate_id"]: item for item in self.document["candidates"]}

    def test_static_discovery_is_exactly_28_bounded_candidates(self):
        """Seven nominal tiers, two logic families, and two input directions are present."""

        self.assertEqual(self.document["candidate_count"], 28)
        self.assertEqual(set(self.document["size_tiers"]), set(RUNNER.SIZE_TIERS))
        self.assertEqual(len(self.document["selections"]), 14)
        for candidate in self.document["candidates"]:
            self.assertIn(candidate["logic_family"], ("NAND2", "NOR2"))
            self.assertNotEqual(candidate["signal_pin"], candidate["control_pin"])
            self.assertEqual(candidate["output_pin"], "Y")

    def test_static_selection_records_real_cell_and_width_rule(self):
        """The selected implementation is reproducible from frozen CDL widths."""

        for selection in self.document["selections"]:
            self.assertTrue(selection["selected_cell"].startswith(selection["logic_family"] + "_X" + selection["size_tier"]))
            self.assertIn(selection["selected_cell"], selection["available_cells"])
            self.assertGreater(selection["total_width_m"], 0.0)

    def test_deck_keeps_all_parallel_outputs_isolated(self):
        """Every requested load remains present and its private output is not the main output."""

        candidate = self.document["candidates"][0]
        deck = RUNNER.CORE.render_deck(self.config, self.cells, .95, 8, candidate, 8, 3, 1)
        self.assertEqual(sum(line.startswith("XLOAD_") for line in deck.splitlines()), 8)
        self.assertEqual(sum(line.startswith("V_F_") for line in deck.splitlines()), 8)
        self.assertNotIn("z_0 medium_out", deck)
        for forbidden in ("XBYPASS", "XCONFIG_SKIP", "tap29", "XOR", "DFF", "CAP", "varactor"):
            self.assertNotIn(forbidden, deck)

    def test_policy_is_original_point_ninety(self):
        """The intermediate scan cannot silently inherit the authorized X8 waiver."""

        self.assertEqual(RUNNER.DEFAULT_HIGH_RATIO, .90)
        record = {
            "t_in_rise": 1.0, "t_in_fall": 2.0, "t_out_rise": 1.2,
            "t_out_fall": 2.3, "t_out_rise_10": 1.1, "t_out_rise_90": 1.3,
            "t_out_fall_90": 2.1, "t_out_fall_10": 2.4,
            "out_logic_high": .709, "out_logic_low": .001,
            "t_out_rise_2": None, "t_out_fall_2": None,
        }
        self.assertFalse(RUNNER.CORE.classify(record, .80, .90)["valid"])

    def test_four_metric_reduction_and_winner_order(self):
        """K, maximum fine step, and settling are reduced from every K=8 code."""

        candidate = self.document["candidates"][0]
        decision = {"candidate_id": candidate["candidate_id"], "mapping_valid": True, "high_cap_control_value": 1, "low_cap_control_value": 0, "unit_delta_ps_by_vdd": {"1.10": 1.0, "0.95": 1.0, "0.80": 1.0}, "reasons": []}
        rows = []
        for vdd in RUNNER.ANCHOR_VDD:
            for code in range(9):
                rows.append({"candidate_id": candidate["candidate_id"], "fine_code": code, "vdd_v": vdd, "D_rise_ps": float(code), "valid": True, "output_rise_time_ps": 2.0 + code, "output_fall_time_ps": 3.0 + code})
        metrics = RUNNER.metric_rows(rows, {"decisions": [decision]}, {candidate["candidate_id"]: candidate}, self.interface)
        self.assertEqual(metrics[0]["K_candidate"], 67)
        self.assertEqual(metrics[0]["delta_fine_max_ps_by_vdd"]["0.80"], 1.0)
        self.assertEqual(metrics[0]["settling_max_ps_by_vdd"]["1.10"], 11.0)
        self.assertEqual(metrics[0]["decision"], "REJECTED")

    def test_requirements_publish_finite_budget_and_forbidden_scope(self):
        """The generated contract prevents an unbounded candidate or K sweep."""

        requirements = RUNNER.requirements(self.interface, self.paths)
        self.assertEqual(requirements["candidate_count"], 28)
        self.assertEqual(requirements["single_load_scenario_budget"], 171)
        self.assertEqual(requirements["size_scan_8unit_scenario_budget"], 756)
        self.assertFalse(requirements["final_medium_N_frozen"])
        self.assertFalse(requirements["final_fine_K_frozen"])
        self.assertEqual(requirements["logic_high_min_ratio"], .90)

    def test_no_historical_runner_dispatch(self):
        """Only the current reviewed core helper is imported; old runners stay read-only."""

        source = RUNNER_PATH.read_text(encoding="utf-8")
        for old_runner in ("run_static_self_calibration", "run_programmable_acceptance_window", "run_delay_code_refinement", "run_fine_grained_controllable_delay", "run_path_selection_medium_stage"):
            self.assertNotIn("import " + old_runner, source)
            self.assertNotIn("subprocess.run([" + old_runner, source)
        self.assertIn("run_standard_cell_load_fine_stage.py", source)

    def test_scenario_parameters_include_candidate_size(self):
        """Changing size or direction cannot reuse a physically different scenario."""

        candidate = self.document["candidates"][0]
        parameters = RUNNER.CORE.scenario_parameters("size_scan_8unit", 8, .95, candidate, 8, 3, 0, 1, .90)
        parameters.update({"study_name": "standard_cell_load_size_sweep", "candidate_id": candidate["candidate_id"], "size_tier": candidate["size_tier"]})
        changed = dict(parameters)
        changed["size_tier"] = "X8"
        self.assertNotEqual(RUNNER.CORE.scenario_id(parameters), RUNNER.CORE.scenario_id(changed))


if __name__ == "__main__":
    unittest.main()
