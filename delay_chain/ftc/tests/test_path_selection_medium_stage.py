"""Pure regressions for the bounded FTC path-selection medium-stage runner.

These checks inspect deterministic topology, cache, and report behavior only.
They deliberately never invoke HSPICE, because retained raw scenarios—not a
test fixture or smoke simulation—are the electrical acceptance evidence.
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


FTC_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = FTC_ROOT / "scripts" / "run_path_selection_medium_stage.py"
SPEC = importlib.util.spec_from_file_location("path_selection_medium_stage", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class PathSelectionMediumStageTests(unittest.TestCase):
    """Protect the fixed topology, gate ordering, and no-overwrite contract."""

    def setUp(self):
        """Load only read-only study inputs; no raw-run directory is created."""

        self.config = RUNNER.load_json(FTC_ROOT / "ftc_config.json")
        self.cells = RUNNER.load_json(FTC_ROOT / "discovery/selected_cells.json")

    def test_thermometer_code_is_continuous_and_rejects_bad_codes(self):
        """Every increment flips exactly the next low-to-high enable bit."""

        self.assertEqual(RUNNER.thermometer_code(8, 0), (0, 0, 0, 0, 0, 0, 0, 0))
        self.assertEqual(RUNNER.thermometer_code(8, 8), (1, 1, 1, 1, 1, 1, 1, 1))
        for code in range(8):
            before = RUNNER.thermometer_code(8, code)
            after = RUNNER.thermometer_code(8, code + 1)
            self.assertEqual([index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]], [code])
        for units, code in ((0, 0), (8, -1), (8, 9)):
            with self.assertRaises(ValueError):
                RUNNER.thermometer_code(units, code)

    def test_static_selected_paths_are_shallow_then_deepen_one_level(self):
        """The shortest path stays constant while deeper codes extend one exit depth."""

        shallow = [RUNNER.trace_selected_path(units, 0) for units in (1, 4, 8, 16)]
        self.assertEqual([trace["selected_exit_depth"] for trace in shallow], [1, 1, 1, 1])
        self.assertEqual([trace["selected_mux_count"] for trace in shallow], [1, 1, 1, 1])
        deep = [RUNNER.trace_selected_path(units, units) for units in (1, 4, 8, 16)]
        self.assertEqual([trace["selected_buffer_count"] for trace in deep], [2, 5, 9, 17])
        for units in (1, 4, 8, 16):
            depths = [RUNNER.trace_selected_path(units, code)["selected_exit_depth"] for code in range(units + 1)]
            self.assertEqual(depths, list(range(1, units + 2)))

    def test_deck_contains_only_local_path_selection_cells(self):
        """Deck text rules out balanced trees, fast/slow templates, and system blocks."""

        deck = "\n".join(RUNNER.build_path_selection_medium_stage(16, 7, RUNNER.PRIMARY_MUX_CELL))
        self.assertEqual(sum(line.startswith("XMUX_") for line in deck.splitlines()), 16)
        self.assertEqual(sum(line.startswith("XBUF_") for line in deck.splitlines()), 17)
        for forbidden in ("XMUX_L1", "XMUX_L2", "XMUX_L3", "FAST", "SLOW", "tap29", "XOR", "DFF", "CAP", "fine"):
            self.assertNotIn(forbidden, deck)

    def test_cell_contract_and_static_proof_use_the_bounded_lvt_choice(self):
        """The vendor contract must be non-inverting A/0, B/1 without a library scan."""

        contract = RUNNER.build_cell_contract(self.cells)
        selected = contract["selected_mux"]
        self.assertEqual(selected["cell"], RUNNER.PRIMARY_MUX_CELL)
        self.assertEqual(selected["s0_zero_selects"], "A")
        self.assertEqual(selected["s0_one_selects"], "B")
        proof = RUNNER.topology_proof((1, 4, 8, 16), selected["cell"])
        self.assertFalse(proof["large_balanced_tap_tree"])
        self.assertFalse(proof["fast_slow_unit_template"])

    def test_pass_manifest_reuses_without_launching_hspice(self):
        """An exact PASS manifest is reusable only after listing and MEAS validation."""

        parameters = RUNNER.scenario_parameters(8, 3, 0.95, RUNNER.PRIMARY_MUX_CELL)
        signature = {"runner_sha256": "runner", "requirements_sha256": "requirements", "cell_contract_sha256": "cell"}
        with tempfile.TemporaryDirectory() as temporary:
            scenario = Path(temporary)
            deck = scenario / "medium_stage.sp"
            deck.write_text("* retained deck\n", encoding="ascii")
            (scenario / "medium_stage.lis").write_text("retained\n", encoding="ascii")
            measurement = scenario / "medium_stage.mt0"
            measurement.write_text("retained\n", encoding="ascii")
            RUNNER.write_json(scenario / "scenario_manifest.json", {
                "completion_status": "PASS", "parameters": parameters,
                "netlist_sha256": RUNNER.sha256_file(deck), "measurement_file": measurement.name,
                **signature,
            })
            with mock.patch.object(RUNNER.run_dc_sweep, "validate_listing", return_value=0), mock.patch.object(RUNNER.run_dc_sweep, "find_measurement_file", return_value=measurement), mock.patch.object(RUNNER.run_dc_sweep, "parse_measurements", return_value={"t_in_rise": 1.0}):
                reused = RUNNER._reuse_scenario(scenario, parameters, signature)
            self.assertEqual(reused["t_in_rise"], 1.0)
            changed = dict(parameters)
            changed["code"] = 4
            self.assertIsNone(RUNNER._reuse_scenario(scenario, changed, signature))

    def test_budgets_and_early_stop_statuses_are_fixed(self):
        """Gate failures cannot consume later scenario budgets or report a later pass."""

        self.assertEqual(RUNNER.PHASE2_MAX_SCENARIOS, 19)
        self.assertEqual(RUNNER.PHASE3_MAX_SCENARIOS, 10)
        self.assertEqual(RUNNER.PHASE4_MAX_SCENARIOS, 12)
        self.assertEqual(RUNNER.TOTAL_MAX_SCENARIOS, 41)
        stages = RUNNER.initial_stages()
        stages["Historical Evidence Freeze"] = "GO"
        stages["Static Path-Selection Contract"] = "GO"
        stages["N8 Code Monotonicity"] = "NO-GO"
        self.assertEqual(stages["Stage-Count Scaling"], "NOT_RUN")
        self.assertEqual(stages["Medium-Step Characterization"], "NOT_RUN")
        self.assertEqual(stages["Future Fine-Stage Interface"], "NOT_RUN")

    def test_projection_cannot_freeze_final_n(self):
        """The future estimate remains an offline input to a later fine-stage task."""

        projection = RUNNER.future_projection({"historical_system_span_reference_ps": 617.031773}, {"medium_step_global_max_ps": 20.0})
        self.assertTrue(projection["projection_only"])
        self.assertFalse(projection["final_N_frozen"])

    def test_fine_stage_interface_exposes_per_voltage_handoff_maps(self):
        """Future fine-stage consumers need compact maps as well as raw step pairs."""

        rows = []
        for vdd in RUNNER.ANCHOR_VDD:
            for code in (0, 1, 7, 8, 15, 16):
                rows.append({"vdd_v": vdd, "code": code, "D_rise_ps": float(code) * 10.0, "valid": True})
        interface, reasons = RUNNER.medium_interface(rows)
        self.assertEqual(reasons, [])
        for field in (
            "medium_step_min_ps_by_vdd", "medium_step_max_ps_by_vdd",
            "medium_span_n16_by_vdd", "minimum_path_delay_n16_by_vdd",
            "maximum_path_delay_n16_by_vdd",
        ):
            self.assertEqual(set(interface[field]), {"1.10", "0.95", "0.80"})

    def test_historical_ftc_runners_and_prohibited_outputs_are_not_used(self):
        """The new runner may read evidence but cannot dispatch old experiment loops."""

        source = RUNNER_PATH.read_text(encoding="utf-8")
        for old_runner in (
            "run_static_self_calibration", "run_programmable_acceptance_window",
            "run_delay_code_refinement", "run_fine_grained_controllable_delay",
        ):
            self.assertNotIn("import " + old_runner, source)
            self.assertNotIn("subprocess.run([" + old_runner, source)
        self.assertIn("import run_dc_sweep", source)
        # Historical evidence legitimately contains a calibration CSV filename.
        # Prove instead that Phase 0 creates only the requirements artifact and
        # never emits a new calibration or droop result under a fresh directory.
        with tempfile.TemporaryDirectory() as temporary:
            analysis = Path(temporary) / "analysis"
            self.assertEqual(RUNNER.main(["--analysis-dir", str(analysis), "--phase0-only"]), 0)
            self.assertTrue((analysis / "requirements.json").is_file())
            self.assertFalse((analysis / "calibration_gate.csv").exists())
            self.assertFalse((analysis / "attack_sweep.csv").exists())

    def test_system_spice_contract_remains_the_configured_system_binary(self):
        """No test launches SPICE; this verifies the fixed path contract only."""

        self.assertEqual(self.config["hspice"], "/home/zhupl25/.local/bin/hspice")
        self.assertEqual(self.config["expected_hspice_version"], "W-2024.09")


if __name__ == "__main__":
    unittest.main()
