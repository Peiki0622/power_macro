"""Static regressions for the bounded fine-driver co-design runner.

These tests deliberately inspect contracts, decks, cache identities, and policy
only.  Electrical acceptance remains the full HSPICE flow run by the runner;
the tests must never invoke it or any historical runner main function.
"""

import importlib.util
import inspect
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = FTC_ROOT / "scripts" / "run_standard_cell_load_fine_stage_driver_codesign.py"
SPEC = importlib.util.spec_from_file_location("standard_cell_load_fine_stage_driver_codesign", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class FineStageDriverCodesignTests(unittest.TestCase):
    """Protect the intentionally small architecture surface before HSPICE starts."""

    def setUp(self):
        """Load real read-only contracts and library views without creating runs."""

        self.interface, self.cells, self.candidate, self.paths = RUNNER.frozen_evidence()
        self.drivers = RUNNER.discover_drivers(self.cells)
        self.config = RUNNER.CORE.load_json(FTC_ROOT / "ftc_config.json")

    def test_fixed_load_contract_cannot_rerank_the_historical_winner(self):
        """The new study must retain NOR2 X4 signal A and its verified polarity."""

        self.assertEqual(self.candidate["candidate_id"], "NOR2_X4A_A9TL40__signal_A")
        self.assertEqual(self.candidate["cell"], "NOR2_X4A_A9TL40")
        self.assertEqual(self.candidate["signal_pin"], "A")
        self.assertEqual(self.candidate["control_pin"], "B")
        self.assertEqual(self.candidate["high_cap_control_value"], 0)
        self.assertEqual(self.candidate["low_cap_control_value"], 1)

    def test_driver_sequence_is_exact_and_physically_increasing(self):
        """No extra library families or unbounded larger sizes may enter the state machine."""

        self.assertEqual([item["driver_cell"] for item in self.drivers], [item[1] for item in RUNNER.DRIVER_SEQUENCE])
        self.assertEqual(len(self.drivers), 4)
        self.assertTrue(all(right["driver_total_width_m"] > left["driver_total_width_m"] for left, right in zip(self.drivers, self.drivers[1:])))
        self.assertTrue(all(item["truth_function"] == "Y = A" for item in self.drivers))

    def test_only_xfine_driver_changes_between_candidate_decks(self):
        """Changing fine strength must not mutate either frozen medium cell or the load bank."""

        first = RUNNER.render_scenario_deck(self.config, self.cells, self.drivers[0], self.candidate, 8, 0.95, 8, 8)
        second = RUNNER.render_scenario_deck(self.config, self.cells, self.drivers[1], self.candidate, 8, 0.95, 8, 8)
        self.assertIn("XFINE_DRIVER out vdd_a vdd_a vss_a vss_a medium_out BUF_X0P8M_A9TL40", first)
        self.assertEqual(first.replace(self.drivers[0]["driver_cell"], "DRIVER"), second.replace(self.drivers[1]["driver_cell"], "DRIVER"))
        self.assertEqual(first.count("BUF_X0P7M_A9TL40"), second.count("BUF_X0P7M_A9TL40"))
        self.assertEqual(first.count("MXT2_X0P5M_A9TL40"), second.count("MXT2_X0P5M_A9TL40"))
        self.assertEqual(sum(line.startswith("XLOAD_") for line in first.splitlines()), 8)

    def test_driver_identity_prevents_cross_driver_cache_reuse(self):
        """Every driver selection must produce a distinct complete scenario identity."""

        first = RUNNER.scenario_parameters("phase2_fine8", self.drivers[0], self.candidate, 8, 0.95, 8, 8)
        second = RUNNER.scenario_parameters("phase2_fine8", self.drivers[1], self.candidate, 8, 0.95, 8, 8)
        self.assertIn("fine_driver_cell", first)
        self.assertEqual(first["logic_low_max_ratio"], 0.10)
        self.assertNotEqual(first["fine_driver_cell"], second["fine_driver_cell"])
        self.assertNotEqual(RUNNER.CORE.scenario_id(first), RUNNER.CORE.scenario_id(second))

    def test_original_waveform_policy_and_final_freeze_flags_remain_open(self):
        """The previous X8 0.88 waiver and premature K/N freezing are both prohibited."""

        document = RUNNER.requirements(self.interface, self.candidate, self.paths)
        self.assertEqual(document["logic_high_min_ratio"], 0.90)
        self.assertEqual(document["logic_low_max_ratio"], 0.10)
        self.assertFalse(document["final_fine_K_frozen"])
        self.assertFalse(document["final_medium_N_frozen"])
        self.assertEqual(document["bypass"], "future_work")

    def test_k_limit_and_voltage_sampling_are_bounded(self):
        """A deliberately tiny measured range must stop above K=64 without extra decks."""

        fake_rows = []
        for vdd in RUNNER.CORE.ANCHOR_VDD:
            for code, delay in ((0, 100.0), (8, 101.0)):
                fake_rows.append({"medium_code": 8, "vdd_v": vdd, "fine_code": code, "D_rise_ps": delay, "valid": True})
        sizing, reasons = RUNNER.derive_sizing(fake_rows, self.interface)
        self.assertGreater(sizing["K_candidate"], RUNNER.MAX_FINE_BANK)
        self.assertIn("K_exceeds_bounded_limit", reasons)
        self.assertLessEqual(len(RUNNER.sample_codes(64)), 7)
        self.assertEqual(RUNNER.sample_codes(8), (0, 1, 2, 4, 6, 7, 8))

    def test_csv_false_validity_remains_an_invalid_waveform(self):
        """Report-only finalization must not treat the nonempty string ``False`` as true."""

        row = {"valid": "False", "vdd_v": "0.8", "output_logic_high": "0.68", "output_logic_low": "0.09", "D_rise_ps": "1", "D_fall_ps": "1", "output_rise_time_ps": "1", "output_fall_time_ps": "1", "unexpected_transition_count": "0"}
        self.assertFalse(RUNNER.row_is_valid(row))
        self.assertIn("driver_waveform_high_fail", RUNNER.waveform_reasons([row]))
        self.assertIn("driver_waveform_low_fail", RUNNER.waveform_reasons([row]))

    def test_runner_has_no_historical_main_or_direct_subprocess_execution(self):
        """The new flow imports only reviewed helpers and owns all new raw scenarios."""

        source = inspect.getsource(RUNNER)
        self.assertNotIn("run_standard_cell_load_driver_strength_probe.py", source)
        self.assertNotIn("run_path_selection_medium_stage.py", source)
        self.assertNotIn("subprocess.run", source)


if __name__ == "__main__":
    unittest.main()
