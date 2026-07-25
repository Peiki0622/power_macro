#!/usr/bin/env python3
"""Regression tests for the direct-chiplet-A rail timeline experiment.

The tests intentionally do not invoke HSPICE.  They protect the deterministic
experiment definition, generated standard-cell deck contracts, trace parser,
capture acceptance gates, and plot-input schema before the full 2 us
electrical simulation is started by the runner.
"""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
PHASE2_ROOT = ROOT / "power_macro" / "delay_chain" / "phase2_vernier"
SCRIPT_DIR = PHASE2_ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import generate_direct_rail_sensor_timeline_deck as deck_generator  # noqa: E402
import plot_direct_rail_sensor_timeline as timeline_plotter  # noqa: E402
import run_direct_rail_sensor_timeline as timeline_runner  # noqa: E402


class DirectRailSensorTimelineTests(unittest.TestCase):
    """Protect the reviewed direct-PWL/M=32/real-DFF experiment contract."""

    @classmethod
    def setUpClass(cls):
        """Load the one authoritative 765 MHz configuration once for this class."""

        cls.config = json.loads((PHASE2_ROOT / "phase2_config.json").read_text(encoding="utf-8"))
        cls.study = deck_generator.timeline_config(cls.config)

    def test_configuration_has_aligned_windows_and_bounded_nonmonotonic_targets(self):
        """The fixed target sequence must preserve frame/window and voltage bounds."""

        self.assertEqual(self.study["sample_count"], 500)
        self.assertAlmostEqual(self.study["sample_period_s"], 4.0e-9, places=24)
        # Binary floating-point cannot represent 4 ns exactly; use the same
        # physically insignificant tolerance as the production contract
        # rather than asserting a decimal representation artifact.
        self.assertAlmostEqual(self.study["sample_count"] * self.study["sample_period_s"], self.study["simulation_stop_s"], delta=1.0e-18)
        self.assertEqual(len(self.study["droop_windows_s"]), 4)
        self.assertEqual(len(self.study["capture_droop_sequence"]["window_cycle_phase_offsets"]), 4)
        window_targets = []
        closed_targets = []
        window_population = []
        for index in range(self.study["sample_count"]):
            droop_mv = deck_generator.capture_droop_mv(self.study, index)
            capture_s = index * self.study["sample_period_s"] + self.study["sample_q_read_offset_s"]
            if timeline_runner.window_index(self.study, capture_s) is None:
                closed_targets.append(droop_mv)
            else:
                window_targets.append(droop_mv)
        self.assertTrue(all(0.5 <= value <= 2.0 for value in closed_targets))
        self.assertTrue(all(4.0 <= value <= 30.0 for value in window_targets))
        self.assertGreater(len(set(window_targets)), 10)
        self.assertNotEqual(window_targets, sorted(window_targets))
        for start_s, end_s in self.study["droop_windows_s"]:
            window_population.append(sum(start_s <= index * self.study["sample_period_s"] + self.study["sample_q_read_offset_s"] < end_s for index in range(self.study["sample_count"])))
        self.assertEqual(window_population, [62, 62, 62, 62])

    def test_direct_vdd_a_changes_only_during_reset_and_settles_before_every_launch(self):
        """Each PWL rail transition must finish before the frame's launch aperture."""

        points = deck_generator.build_vdd_a_pwl(self.config, self.study)
        period_s = self.study["sample_period_s"]
        transition_start = self.study["rail_transition_start_offset_s"]
        transition_end = self.study["rail_transition_end_offset_s"]
        launch = self.study["sample_launch_offset_s"]
        self.assertEqual(len(points), 1002)
        self.assertEqual(points[0], (0.0, self.config["vnom_v"]))
        for index in range(self.study["sample_count"]):
            slot_start = index * period_s
            # Point zero is the nominal DC-consistent source value at t=0;
            # each frame then contributes the old-value/start and target/end
            # pair at positions 2*i+1 and 2*i+2.
            self.assertAlmostEqual(points[2 * index + 1][0], slot_start + transition_start, places=24)
            self.assertAlmostEqual(points[2 * index + 2][0], slot_start + transition_end, places=24)
            self.assertGreaterEqual(launch - transition_end, 800.0e-12)
            self.assertAlmostEqual(
                points[2 * index + 2][1], deck_generator.frame_target_voltage_v(self.config, self.study, index), places=15
            )

    def test_generated_deck_has_all_real_dff_evidence_and_no_old_integration_instances(self):
        """Deck contents must be direct A rail plus real sensor, not a hidden PDN model."""

        deck, metadata = deck_generator.render_direct_rail_deck(self.config)
        lines = deck.splitlines()
        self.assertEqual(sum(1 for line in lines if line.startswith("XSENSE_STAGE_")), 32)
        self.assertEqual(sum(1 for line in lines if line.startswith("XREF_STAGE_")), 32)
        self.assertEqual(sum(1 for line in lines if line.startswith("XCOMP_")), 32)
        self.assertEqual(sum(1 for line in lines if line.startswith(".measure tran")), 65002)
        self.assertEqual(metadata["measurement_count"], 65002)
        self.assertIn("XCOMP_000 raw_q_000 vdd_ref vss_ref sense_000 ref_000 sensor_reset PHASE2_COMPARATOR", deck)
        self.assertIn("V_VDD_A vdd_a vss_a PWL(", deck)
        self.assertIn("V_VDD_REF vdd_ref vss_ref DC=1.100000000000e+00", deck)
        self.assertFalse(any(line.startswith(prefix) for prefix in ("X_DOMAIN", "I_A_", "I_B_") for line in lines))
        self.assertNotIn("ro_nbank", deck.lower())
        self.assertNotIn("package_three_port_pdn", deck.lower())

    def test_acceptance_rejects_closed_code_excursion_even_when_windows_detect(self):
        """Closed-window controls are a separate gate and cannot be masked by detections."""

        rows = []
        for index in range(self.study["sample_count"]):
            capture_s = index * self.study["sample_period_s"] + self.study["sample_q_read_offset_s"]
            current_window = timeline_runner.window_index(self.study, capture_s)
            is_window = current_window is not None
            rows.append({
                "sample_index": index, "sample_q_read_time_s": capture_s, "direct_droop_window": is_window,
                "sensor_code": 20 if is_window else 15, "a_vdd_v": deck_generator.frame_target_voltage_v(self.config, self.study, index),
                "configured_vdd_a_v": deck_generator.frame_target_voltage_v(self.config, self.study, index),
                "configured_droop_mv": deck_generator.capture_droop_mv(self.study, index),
                "code_valid": True, "quality": "VALID", "reset_failure_count": 0,
            })
        rows[0]["sensor_code"] = 17
        result = timeline_runner.acceptance_summary(self.config, self.study, rows)
        self.assertFalse(result["gates"]["closed_codes_within_baseline_plus_minus_one"])
        self.assertEqual(result["status"], "FAIL")

    def test_ascii_tr0_parser_accepts_direct_probe_contract(self):
        """The parser must preserve each direct rail and reset observation column."""

        labels = ["TIME", "v(vdd_a", "v(vss_a", "v(vdd_ref", "v(vss_ref", "v(sensor_reset"]
        rows = [
            [0.0, 1.1, 0.0, 1.1, 0.0, 1.1],
            [1.0e-9, 1.099, 0.0, 1.1, 0.0, 0.0],
            [2.0e-9, 1.099, 0.0, 1.1, 0.0, 0.0],
        ]
        header = "".join("{:<16}".format(label) for label in labels)
        payload = "".join("{:.7E}".format(value) for row in rows for value in row) + "{:.7E}".format(1.0)
        with tempfile.TemporaryDirectory() as temporary_directory:
            trace_path = Path(temporary_directory) / "direct.tr0"
            trace_path.write_text("0006" + "0" * 20 + header + "$&%#\n" + payload, encoding="ascii")
            trace = timeline_runner.parse_ascii_tr0(trace_path)
        self.assertEqual(trace["record_count"], 3)
        self.assertEqual(trace["columns"]["reset_v"], [1.1, 0.0, 0.0])
        self.assertAlmostEqual(timeline_runner.interpolate_column(trace, "a_vdd_absolute_v", 1.5e-9), 1.099, places=12)

    def test_plot_loader_requires_structured_direct_capture_rows(self):
        """Plot data remains a capture table, never a synthetic code waveform."""

        fields = timeline_plotter.REQUIRED_CSV_FIELDS
        source = {
            "scenario_id": "direct_rail_timeline", "sample_index": "0", "sample_q_read_time_s": "2.5e-9",
            "window_index": "", "direct_droop_window": "False", "configured_droop_mv": "0.5",
            "configured_vdd_a_v": "1.0995", "a_vdd_v": "1.0995", "measured_droop_mv": "0.5",
            "vdd_ref_v": "1.1", "sensor_code": "15", "code_valid": "True", "quality": "VALID_WITH_EDGE_RISK",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            csv_path = Path(temporary_directory) / "captures.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
                writer.writeheader()
                writer.writerow(source)
            rows = timeline_plotter.load_samples(csv_path)
        self.assertEqual(rows[0]["sensor_code"], 15)
        self.assertFalse(rows[0]["direct_droop_window"])
        self.assertEqual(rows[0]["quality"], "VALID_WITH_EDGE_RISK")


if __name__ == "__main__":
    unittest.main()
