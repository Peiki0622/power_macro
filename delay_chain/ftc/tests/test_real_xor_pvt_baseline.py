"""Pure-data contract tests for the FTC tap29 PVT baseline characterization.

The test suite never launches HSPICE.  It verifies the queue, topology,
arithmetic, and bounded Golden lookup before the separately required physical
process/temperature scenarios are run by the task-owned runner.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_ftc_characterization as characterization  # noqa: E402  # Read frozen FTC inputs.
import run_real_xor_pvt_baseline as pvt  # noqa: E402  # Exercise only pure PVT helpers.


def measured_row(vdd_v, width_ps):
    """Create a complete synthetic tap29 measurement, not a physical cell model."""

    return {
        "vdd_v": vdd_v,
        "W_real_ps": width_ps,
        "W_proxy_ps": width_ps - 2.0,
        "width_ratio": width_ps / (width_ps - 2.0),
        "xor29_peak_ratio": 0.99,
        "valid": 1,
    }


def pvt_row(corner, temperature_c, vdd_v, width_ps):
    """Attach the minimum provenance used by screen/matrix pure-data functions."""

    row = measured_row(vdd_v, width_ps)
    row.update({
        "scenario_id": pvt.scenario_id(corner, temperature_c, vdd_v),
        "corner": corner,
        "temperature_c": temperature_c,
    })
    return row


class FtcRealXorPvtBaselineTest(unittest.TestCase):
    """Protect the planned PVT evidence surface without replacing electrical acceptance."""

    def setUp(self):
        """Load actual frozen collateral and the approved nominal curve for every test."""

        self.config = characterization.load_json(FTC_ROOT / "ftc_config.json")
        self.cells = characterization.load_json(FTC_ROOT / "discovery" / "selected_cells.json")
        self.nominal = pvt.load_nominal_fine(FTC_ROOT / "analysis" / "real_xor_pulse_width" / "fine.csv")

    def test_process_corners_are_taken_from_the_pdk_declaration(self):
        """A synthetic PDK with arbitrary names proves discovery does not hard-code ff/ss."""

        with tempfile.TemporaryDirectory(prefix="ftc_pvt_corner_") as temporary:
            model = Path(temporary) / "model.lib"
            model.write_text(
                "* Three corners are supported: ALPHA, BETA and GAMMA.\n"
                ".lib alpha\n.endl alpha\n.lib beta\n.endl beta\n.lib gamma\n.endl gamma\n"
                ".lib mos_mc\n.endl mos_mc\n",
                encoding="utf-8",
            )
            self.assertEqual(pvt.discover_process_corners(model, "alpha"), ["alpha", "beta", "gamma"])

    def test_manifest_deduplicates_tt25_and_never_queues_it(self):
        """The shared TT/25 anchors in two screens remain three reuse rows, never decks."""

        manifest = pvt.initial_manifest(["tt", "alpha"])
        self.assertEqual(len(manifest), 15)
        reused = [row for row in manifest if row["corner"] == "tt" and row["temperature_c"] == 25.0]
        self.assertEqual(len(reused), 3)
        self.assertTrue(all(row["source"] == "reused_tt25_fine" and row["needs_hspice"] == 0 for row in reused))
        self.assertEqual(pvt.deduplicate_manifest([reused[0], dict(reused[0])]), [reused[0]])

    def test_frozen_deck_keeps_tap29_and_full_xor_bank(self):
        """Rendered deck inspection prevents a PVT override from changing physical topology."""

        point = pvt.verify_frozen_topology(self.config, self.cells)
        pvt.verify_rendered_topology(self.config, self.cells, point)
        scenario = pvt.scenario_config(self.config, "example_corner", -40.0)
        self.assertEqual(self.config["corner"], "tt")
        self.assertEqual(self.config["temperature_c"], 25.0)
        self.assertEqual(scenario["corner"], "example_corner")
        self.assertEqual(scenario["temperature_c"], -40.0)

    def test_envelope_selection_and_offset_span_are_direct_arithmetic(self):
        """Measured extrema, including all anchors, select only actual envelope corners."""

        process = []
        temperature = []
        matrix = []
        nominal = {voltage: measured_row(voltage, 100.0 + index * 100.0) for index, voltage in enumerate(pvt.ANCHOR_VDDS)}
        for voltage in pvt.ANCHOR_VDDS:
            base = nominal[voltage]["W_real_ps"]
            process.extend([pvt_row("tt", 25.0, voltage, base), pvt_row("fast", 25.0, voltage, base - 10.0), pvt_row("slow", 25.0, voltage, base + 15.0)])
            temperature.extend(pvt_row("tt", temperature_c, voltage, base + (temperature_c - 25.0) / 10.0) for temperature_c in pvt.TEMPERATURES_C)
            matrix.extend(
                pvt_row(corner, temperature_c, voltage, base + offset + (temperature_c - 25.0) / 10.0)
                for corner, offset in (("tt", 0.0), ("fast", -10.0), ("slow", 15.0))
                for temperature_c in pvt.TEMPERATURES_C
            )
        selected, envelope = pvt.select_envelope_corners(process, ["tt", "fast", "slow"])
        self.assertEqual(selected, ["tt", "fast", "slow"])
        self.assertEqual(envelope["1.10"]["corner_min_width"], ["fast"])
        self.assertEqual(pvt.offset_summary(process, nominal, "process")["1.10"]["process_span_ps"], 25.0)
        self.assertEqual(pvt.offset_summary(temperature, nominal, "temperature")["0.90"]["temperature_span_ps"], 16.5)
        self.assertEqual(pvt.combined_summary(matrix)["0.75"]["pvt_span_ps"], 41.5)

    def test_voltage_comparison_uses_existing_fine_data_without_hspice(self):
        """The 50/100 mV comparison remains a pure lookup over the committed baseline."""

        with mock.patch.object(pvt.characterization, "run_scenario", side_effect=AssertionError("HSPICE must not run")):
            shifts = pvt.vdd_sensitivity(self.nominal)
        self.assertGreater(shifts["1.10"]["shift_50mV_ps"], 0.0)
        self.assertGreater(shifts["0.90"]["shift_100mV_ps"], shifts["0.90"]["shift_50mV_ps"])

    def test_golden_inverse_mapping_is_bounded_and_interpolated(self):
        """Synthetic monotonic points cover exact hit, interpolation, and no-extrapolation behavior."""

        curve = {
            1.10: measured_row(1.10, 100.0),
            1.00: measured_row(1.00, 200.0),
            0.90: measured_row(0.90, 400.0),
        }
        self.assertEqual(pvt.inverse_nominal_voltage(curve, 200.0), 1.0)
        self.assertAlmostEqual(pvt.inverse_nominal_voltage(curve, 150.0), 1.05)
        self.assertIsNone(pvt.inverse_nominal_voltage(curve, 99.0))
        rows = pvt.golden_equivalent_rows([pvt_row("fast", -40.0, 1.10, 450.0)], curve)
        self.assertEqual(rows[0]["out_of_nominal_curve"], 1)
        self.assertIsNone(rows[0]["golden_equivalent_error_mV"])


if __name__ == "__main__":
    unittest.main()
