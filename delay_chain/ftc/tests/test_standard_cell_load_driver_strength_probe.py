"""Pure regressions for the bounded fine-driver strength probe.

Electrical acceptance remains the retained HSPICE evidence.  These checks only
protect the fixed endpoint, exact driver order, and deck/cache separation.
"""

import importlib.util
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = FTC_ROOT / "scripts" / "run_standard_cell_load_driver_strength_probe.py"
SPEC = importlib.util.spec_from_file_location("standard_cell_load_driver_strength_probe", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class DriverStrengthProbeTests(unittest.TestCase):
    """Keep the four-point experiment bounded without replacing HSPICE evidence."""

    def setUp(self):
        """Load frozen evidence and the real library without creating raw runs."""

        self.config = RUNNER.CORE.load_json(FTC_ROOT / "ftc_config.json")
        _, self.cells, _ = RUNNER.CORE.freeze_inputs()
        self.candidate = RUNNER.fixed_load()
        self.drivers = RUNNER.discover_drivers(self.cells)

    def test_discovery_is_exactly_the_approved_increasing_m_sequence(self):
        """No arbitrary buffer family or unbounded strength sweep may enter HSPICE."""

        self.assertEqual([item["driver_cell"] for item in self.drivers], [item[1] for item in RUNNER.DRIVER_SEQUENCE])
        self.assertEqual(len(self.drivers), 4)
        self.assertTrue(all(right["driver_total_width_m"] > left["driver_total_width_m"] for left, right in zip(self.drivers, self.drivers[1:])))

    def test_user_requested_continuation_contains_only_the_remaining_three_sizes(self):
        """The continuation reuses X0P8M and schedules exactly X1/X1P4/X2."""

        self.assertEqual([item[1] for item in RUNNER.REMAINING_DRIVER_SEQUENCE], [
            "BUF_X1M_A9TL40", "BUF_X1P4M_A9TL40", "BUF_X2M_A9TL40",
        ])

    def test_deck_changes_only_the_fine_driver(self):
        """The fixed failing endpoint retains all eight parallel NOR input loads."""

        deck = RUNNER.render_probe_deck(self.config, self.cells, self.candidate, self.drivers[0])
        self.assertIn("XFINE_DRIVER out vdd_a vdd_a vss_a vss_a medium_out BUF_X0P8M_A9TL40", deck)
        self.assertEqual(sum(line.startswith("XLOAD_") for line in deck.splitlines()), 8)
        self.assertEqual(sum(line.startswith("V_F_") for line in deck.splitlines()), 8)
        self.assertNotIn("XBYPASS", deck)
        self.assertNotIn("XCONFIG_SKIP", deck)
        self.assertNotIn("tap29", deck)
        self.assertNotIn("varactor", deck)

    def test_driver_identity_changes_the_reusable_scenario(self):
        """A larger buffer cannot reuse a cached X0P8M electrical measurement."""

        first = RUNNER.probe_parameters(self.drivers[0], self.candidate)
        second = RUNNER.probe_parameters(self.drivers[1], self.candidate)
        self.assertNotEqual(first["fine_driver_cell"], second["fine_driver_cell"])
        self.assertNotEqual(RUNNER.CORE.scenario_id(first), RUNNER.CORE.scenario_id(second))

    def test_original_voltage_and_waveform_contract_remain_fixed(self):
        """The probe cannot silently borrow the X8 0.88 high-level waiver."""

        self.assertEqual(RUNNER.PROBE_VDD, .80)
        self.assertEqual(RUNNER.PROBE_MEDIUM_CODE, 15)
        self.assertEqual(RUNNER.PROBE_FINE_CODE, 8)
        self.assertEqual(RUNNER.CORE.DEFAULT_LOGIC_HIGH_MIN_RATIO, .90)
        self.assertEqual(RUNNER.CORE.LOGIC_LOW_MAX_RATIO, .10)

    def test_current_failure_is_read_only_baseline(self):
        """The known X0P7M failure is consumed from retained analysis, not simulated."""

        row = RUNNER.baseline_row()
        self.assertEqual(row["output_logic_high"], "0.717393004")
        self.assertEqual(row["valid"], "False")


if __name__ == "__main__":
    unittest.main()
