"""Pure-data and rendered-deck regression for FTC wavefront feasibility work.

These tests intentionally do not invoke HSPICE.  They verify the finite-edge
stimulus contract, raw-XOR interpretation, compact-evidence schema, and gated
decision helpers with deterministic data; electrical validity remains the
responsibility of the separately retained task-owned HSPICE runs.
"""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import generate_ftc_deck as deck  # noqa: E402  # Render the public HSPICE interface.
import run_ftc_characterization as runner  # noqa: E402  # Exercise pure wavefront helpers.


def synthetic_sample(edge_index, polarity, raw_word, edge_time_s=1.0e-9):
    """Build one complete raw-XOR row with monotonic 30-stage transitions.

    The timing vectors are deliberately simple and strictly ordered.  Tests
    that need a destructive transition can alter one value explicitly instead
    of relying on unstated fixture behavior.
    """

    rvt = [edge_time_s + (index + 1) * 2.0e-11 for index in range(30)]
    lvt = [edge_time_s + (index + 1) * 1.0e-11 for index in range(30)]
    return {
        "edge_index": edge_index,
        "edge_polarity": polarity,
        "edge_time_s": edge_time_s,
        "sample_time_s": edge_time_s + 3.0e-10,
        "raw_xor_word": raw_word,
        "rvt_transition_s": rvt,
        "lvt_transition_s": lvt,
    }


class FtcPipelinedWavefrontTest(unittest.TestCase):
    """Protect the smallest allowed continuous-edge experiment surface."""

    def setUp(self):
        """Load immutable FTC inputs for every independent test case."""

        self.config = runner.load_json(FTC_ROOT / "ftc_config.json")
        self.cells = runner.load_json(FTC_ROOT / "discovery" / "selected_cells.json")
        self.settings = runner.load_wavefront_settings(
            FTC_ROOT / "analysis" / "pipelined_wavefront" / "pipelined_wavefront_config.json",
            self.config,
        )

    def test_task_local_settings_preserve_selected_operating_point(self):
        """Wavefront settings must not become a second formal FTC configuration."""

        point = self.config["selected_operating_point"]
        self.assertEqual(point["initial_rvt_stages"], 4)
        self.assertEqual(point["initial_lvt_stages"], 0)
        self.assertEqual(point["capture_phase_s"], 3.0e-10)
        self.assertEqual(self.settings["sample_offset_s"], 3.0e-10)
        self.assertEqual(self.settings["anchor_vdd_v"], [1.1, 0.9, 0.8])
        self.assertEqual(self.settings["two_edge"]["candidate_spacing_s"], [
            2.0e-9, 1.5e-9, 1.0e-9, 7.5e-10, 6.0e-10, 5.0e-10, 4.0e-10,
        ])

    def test_finite_pwl_decks_cover_one_two_and_eight_edges(self):
        """Rendered decks must retain exactly one raw-XOR measure set per edge."""

        point = self.config["selected_operating_point"]
        for edge_count, initial_level, expected_rise, expected_fall in (
            (1, 1, 0, 1), (2, 0, 1, 1), (8, 0, 4, 4),
        ):
            rendered = deck.render_deck(
                config=self.config, cells=self.cells, vdd_v=1.1, mode="xor",
                initial_rvt_stages=point["initial_rvt_stages"], initial_lvt_stages=point["initial_lvt_stages"],
                capture_phase_s=3.0e-10,
                edge_train={
                    "first_edge_time_s": 1.0e-9,
                    "edge_spacing_s": 4.0e-10,
                    "edge_count": edge_count,
                    "initial_logic_level": initial_level,
                },
            )
            # Finite PWL forbids an unrequested periodic ninth edge; the
            # regular legacy PULSE is checked separately below for compatibility.
            self.assertIn("V_SCLK s_clk vss_a PWL(", rendered)
            self.assertNotIn("V_SCLK s_clk vss_a PULSE", rendered)
            self.assertEqual(rendered.count(".measure tran xor_e"), 30 * edge_count)
            self.assertEqual(rendered.count("RISE="), 60 * expected_rise)
            self.assertEqual(rendered.count("FALL="), 60 * expected_fall)
            self.assertIn("AT=1.300000000000e-09", rendered)
        legacy = deck.render_deck(
            config=self.config, cells=self.cells, vdd_v=1.1, mode="xor",
            initial_rvt_stages=point["initial_rvt_stages"], initial_lvt_stages=point["initial_lvt_stages"],
            capture_phase_s=3.0e-10,
        )
        self.assertIn("V_SCLK s_clk vss_a PULSE", legacy)
        self.assertNotIn("rvt_e00_t00_cross", legacy)

    def test_raw_run_metrics_and_window_levels_are_not_implicitly_repaired(self):
        """Two physical windows must remain visible in the compact classification."""

        level_zero = runner.wavefront_sample_metrics(synthetic_sample(0, "rise", "00" + "1" * 6 + "0" * 22))
        level_one = runner.wavefront_sample_metrics(synthetic_sample(0, "rise", "00" + "1" * 5 + "000" + "1" + "0" * 19))
        level_two = runner.wavefront_sample_metrics(synthetic_sample(0, "rise", "00" + "1" * 3 + "000" + "1" * 4 + "0" * 18))
        level_three = runner.wavefront_sample_metrics(synthetic_sample(0, "rise", "0" * 30))
        self.assertEqual((level_zero["run_count"], level_zero["largest_run_length"], level_zero["second_largest_run_length"], level_zero["window_level"]), (1, 6, 0, 0))
        self.assertEqual((level_one["run_count"], level_one["largest_run_length"], level_one["second_largest_run_length"], level_one["window_level"]), (2, 5, 1, 1))
        self.assertEqual((level_two["run_count"], level_two["largest_run_length"], level_two["second_largest_run_length"], level_two["window_level"]), (2, 4, 3, 2))
        self.assertEqual((level_three["valid"], level_three["window_level"]), (0, 3))

    def test_candidate_selection_and_eight_edge_steady_state_gate(self):
        """Only bounded representative candidates may advance to the 8-edge step."""

        nominal = {"spacing_results": [
            {"edge_spacing_s": 7.5e-10, "overlap_expected": 0, "acceptable": 1},
            {"edge_spacing_s": 6.0e-10, "overlap_expected": 1, "acceptable": 1},
            {"edge_spacing_s": 5.0e-10, "overlap_expected": 1, "acceptable": 1},
            {"edge_spacing_s": 4.0e-10, "overlap_expected": 1, "acceptable": 0},
        ]}
        self.assertEqual(runner.select_anchor_spacings(nominal), [7.5e-10, 6.0e-10, 5.0e-10])
        rows = []
        for index in range(8):
            # Last two rises share 5--9 and last two falls share 6--10.  The
            # first pair is intentionally a startup transient allowed by plan.
            polarity = "rise" if index % 2 == 0 else "fall"
            word = "0" * (4 + (index % 2)) + "1" * 5 + "0" * (21 - (index % 2))
            row = runner.wavefront_sample_metrics(synthetic_sample(index, polarity, word, 1.0e-9 + index * 6.0e-10))
            rows.append(row)
        self.assertEqual(runner.eight_edge_stable(rows, "sensible"), 1)
        rows[-1]["window_level"] = 2
        self.assertEqual(runner.eight_edge_stable(rows, "sensible"), 0)

    def test_compact_csv_serializes_transition_vectors_and_stable_columns(self):
        """CSV output must retain all 30 transition values without raw waveforms."""

        row = runner.wavefront_sample_metrics(synthetic_sample(0, "rise", "0" * 5 + "1" * 5 + "0" * 20))
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence.csv"
            runner.write_csv(output, [row])
            with output.open(newline="", encoding="utf-8") as stream:
                record = next(csv.DictReader(stream))
        self.assertEqual(record["raw_xor_word"], row["raw_xor_word"])
        self.assertEqual(len(json.loads(record["rvt_transition_s"])), 30)
        self.assertEqual(len(json.loads(record["lvt_transition_s"])), 30)
        self.assertEqual(record["second_largest_run_length"], "0")

    def test_interval_summary_reports_cross_anchor_first_failure_not_nonoverlap(self):
        """A mixed-overlap 750 ps point must not masquerade as the first failure."""

        nominal = {"spacing_results": [
            {"edge_spacing_s": 7.5e-10, "overlap_expected": 0, "acceptable": 1},
            {"edge_spacing_s": 6.0e-10, "overlap_expected": 1, "acceptable": 1},
        ]}
        anchor = {"spacing_results": [
            {
                "edge_spacing_s": 7.5e-10, "stable_overlap": 0,
                "vdd_results": [
                    {"overlap_expected": 0}, {"overlap_expected": 1}, {"overlap_expected": 1},
                ],
            },
            {
                "edge_spacing_s": 6.0e-10, "stable_overlap": 0,
                "vdd_results": [
                    {"overlap_expected": 1}, {"overlap_expected": 1}, {"overlap_expected": 1},
                ],
            },
        ]}
        intervals = runner.tested_interval_summary(nominal, anchor, None)
        self.assertEqual(intervals["T_edge_nonoverlap_s"], 7.5e-10)
        self.assertEqual(intervals["T_edge_overlap_begin_s"], 6.0e-10)
        self.assertEqual(intervals["T_edge_first_unstable_s"], 6.0e-10)


if __name__ == "__main__":
    unittest.main()
