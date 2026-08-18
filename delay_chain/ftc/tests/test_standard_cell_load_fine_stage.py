"""Pure regressions for the bounded standard-cell load fine-stage runner.

These tests inspect deterministic discovery, deck construction, cache rules,
and Gate propagation only.  They deliberately never execute HSPICE: retained
task-owned raw scenarios are the electrical acceptance evidence.
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


FTC_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = FTC_ROOT / "scripts" / "run_standard_cell_load_fine_stage.py"
SPEC = importlib.util.spec_from_file_location("standard_cell_load_fine_stage", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class StandardCellLoadFineStageTests(unittest.TestCase):
    """Protect the physical scope and bounded scheduler without a smoke run."""

    def setUp(self):
        """Load only frozen local inputs; no task raw-run directory is created."""

        self.config = RUNNER.load_json(FTC_ROOT / "ftc_config.json")
        self.cells = RUNNER.load_json(FTC_ROOT / "discovery" / "selected_cells.json")
        self.candidates = RUNNER.discover_candidates(self.cells)["candidates"]
        self.assertTrue(self.candidates, "the checked-in LVT library must expose bounded candidates")

    def test_discovery_is_limited_to_four_nand_nor_input_choices(self):
        """Only the plan-approved two-input X0P5 NAND/NOR physical variants may enter HSPICE."""

        self.assertLessEqual(len(self.candidates), 4)
        for candidate in self.candidates:
            self.assertRegex(candidate["cell"], r"^(NAND2|NOR2)_X0P5[A-Z]_A9TL40$")
            self.assertNotEqual(candidate["signal_pin"], candidate["control_pin"])
            self.assertEqual(candidate["output_pin"], "Y")

    def test_maximum_probe_selects_only_the_largest_lvt_drive_cells(self):
        """The optional probe selects X8 cells without changing the default study."""

        maximum = RUNNER.discover_candidates(self.cells, "maximum")
        self.assertEqual(maximum["size_mode"], "maximum")
        self.assertEqual({candidate["cell"] for candidate in maximum["candidates"]}, {
            "NAND2_X8M_A9TL40", "NOR2_X8A_A9TL40",
        })

    def test_logic_high_policy_is_explicit_and_changes_scenario_identity(self):
        """The authorized 0.88 policy is distinct while the default remains 0.90."""

        self.assertEqual(RUNNER.validate_logic_high_min_ratio(.90), .90)
        self.assertEqual(RUNNER.validate_logic_high_min_ratio(.88), .88)
        candidate = self.candidates[0]
        default = RUNNER.scenario_parameters("fine8", 8, .80, candidate, 8, 8, 0, 1)
        waived = RUNNER.scenario_parameters("fine8", 8, .80, candidate, 8, 8, 0, 1, .88)
        self.assertEqual(default["logic_high_min_ratio"], .90)
        self.assertEqual(waived["logic_high_min_ratio"], .88)
        self.assertNotEqual(RUNNER.scenario_id(default), RUNNER.scenario_id(waived))
        with self.assertRaises(ValueError):
            RUNNER.validate_logic_high_min_ratio(0.0)

    def test_waveform_policy_reclassifies_only_the_authorized_high_level(self):
        """A sample just below 0.90 passes only under the explicit 0.88 policy."""

        record = {
            "t_in_rise": 1.0, "t_in_fall": 2.0, "t_out_rise": 1.2,
            "t_out_fall": 2.3, "t_out_rise_10": 1.1, "t_out_rise_90": 1.3,
            "t_out_fall_90": 2.1, "t_out_fall_10": 2.4,
            "out_logic_high": .709, "out_logic_low": .001,
            "t_out_rise_2": None, "t_out_fall_2": None,
        }
        self.assertFalse(RUNNER.classify(record, .80, .90)["valid"])
        self.assertTrue(RUNNER.classify(record, .80, .88)["valid"])

    def test_thermometer_encoding_rejects_bad_codes_and_changes_one_load(self):
        """A fine-code increment changes exactly one physical load from low to high state."""

        self.assertEqual(RUNNER.thermometer(8, 0), (0,) * 8)
        self.assertEqual(RUNNER.thermometer(8, 8), (1,) * 8)
        for code in range(8):
            before, after = RUNNER.thermometer(8, code), RUNNER.thermometer(8, code + 1)
            self.assertEqual([index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]], [code])
        for code in (-1, 9):
            with self.assertRaises(ValueError):
                RUNNER.thermometer(8, code)

    def test_deck_has_fixed_driver_and_all_parallel_loads(self):
        """Every code keeps K loads present; their outputs never join the main path."""

        deck = RUNNER.render_deck(self.config, self.cells, .95, 8, self.candidates[0], 8, 3, 1)
        self.assertIn("XFINE_DRIVER out", deck)
        self.assertEqual(sum(line.startswith("XLOAD_") for line in deck.splitlines()), 8)
        self.assertEqual(sum(line.startswith("V_F_") for line in deck.splitlines()), 8)
        self.assertNotIn("z_0 medium_out", deck)
        for forbidden in ("tap29", "XOR", "DFF", "XBYPASS", "XCONFIG_SKIP", "CAP", "varactor"):
            self.assertNotIn(forbidden, deck)

    def test_deck_rejects_invalid_bank_parameters(self):
        """Deck rendering cannot silently omit a requested fine-code bit or load cell."""

        with self.assertRaises(ValueError):
            RUNNER.render_deck(self.config, self.cells, .95, 8, self.candidates[0], 8, 9)
        with self.assertRaises(ValueError):
            RUNNER.render_deck(self.config, self.cells, .95, 8, None, 1, 0)

    def test_pass_manifest_reuses_only_exact_hashes_and_parameters(self):
        """A complete PASS scenario may resume; an altered physical parameter may not."""

        candidate = self.candidates[0]
        parameters = RUNNER.scenario_parameters("fine8", 8, .95, candidate, 8, 3, 0, 1)
        signature = {"runner_sha256": "runner", "requirements_sha256": "requirements", "candidate_contract_sha256": "candidate"}
        with tempfile.TemporaryDirectory() as temporary:
            scenario = Path(temporary)
            deck, listing, measurement = scenario / "fine_stage.sp", scenario / "fine_stage.lis", scenario / "fine_stage.mt0"
            deck.write_text("* retained\n", encoding="ascii")
            listing.write_text("retained\n", encoding="ascii")
            measurement.write_text("retained\n", encoding="ascii")
            RUNNER.write_json(scenario / "scenario_manifest.json", {"parameters": parameters, "netlist_sha256": RUNNER.sha256_file(deck), "completion_status": "PASS", "measurement_file": measurement.name, **signature})
            with mock.patch.object(RUNNER.run_dc_sweep, "validate_listing", return_value=0), mock.patch.object(RUNNER.run_dc_sweep, "find_measurement_file", return_value=measurement), mock.patch.object(RUNNER.run_dc_sweep, "parse_measurements", return_value={"t_in_rise": 1.0}):
                self.assertEqual(RUNNER.reuse_scenario(scenario, parameters, signature)["t_in_rise"], 1.0)
                changed = dict(parameters); changed["fine_code"] = 4
                self.assertIsNone(RUNNER.reuse_scenario(scenario, changed, signature))
                self.assertNotEqual(RUNNER.scenario_id(parameters), RUNNER.scenario_id(changed))

    def test_budgets_and_failure_propagation_are_fixed(self):
        """The study cannot grow a candidate sweep or report later work after a failed Gate."""

        self.assertEqual(RUNNER.PHASE2_MAX_SCENARIOS, 27)
        self.assertEqual(RUNNER.PHASE3_MAX_SCENARIOS, 25)
        self.assertEqual(RUNNER.MAX_FINE_BANK, 64)
        stages = {name: "NOT_RUN" for name in RUNNER.STAGES}
        stages["8-Unit Fine Bank"] = "NO-GO"
        RUNNER.mark_later_not_run(stages, "8-Unit Fine Bank")
        self.assertTrue(all(stages[name] == "NOT_RUN" for name in RUNNER.STAGES[4:]))

    def test_retained_stats_counts_physical_pass_scenarios_not_checkpoint_reuse(self):
        """Final publication must report task-owned raw evidence across process checkpoints."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index in range(2):
                scenario = root / "r1" / "scenarios" / str(index)
                scenario.mkdir(parents=True)
                RUNNER.write_json(scenario / "scenario_manifest.json", {"completion_status": "PASS"})
            self.assertEqual(RUNNER.retained_stats(root), {"new": 2, "reused": 0})

    def test_requirements_preserve_open_final_sizing_and_forbidden_scope(self):
        """This phase documents future bypass work without implementing it or freezing N/K."""

        interface, _, paths = RUNNER.freeze_inputs()
        requirements = RUNNER.build_requirements(interface, paths)
        self.assertFalse(requirements["final_medium_N_frozen"])
        self.assertFalse(requirements["final_fine_K_frozen"])
        self.assertEqual(requirements["bypass"], "future_work")
        for field in ("sensor", "xor", "dff", "calibration", "droop", "pvt", "rtl"):
            self.assertEqual(requirements[field], "forbidden")

    def test_old_runners_are_not_imported_or_dispatched(self):
        """Only the generic Phase-1 integrity helper may be shared with this task."""

        source = RUNNER_PATH.read_text(encoding="utf-8")
        for old_runner in ("run_static_self_calibration", "run_programmable_acceptance_window", "run_delay_code_refinement", "run_fine_grained_controllable_delay", "run_path_selection_medium_stage"):
            self.assertNotIn("import " + old_runner, source)
            self.assertNotIn("subprocess.run([" + old_runner, source)
        self.assertIn("import run_dc_sweep", source)


if __name__ == "__main__":
    unittest.main()
