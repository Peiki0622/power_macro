"""Rendered-deck and pure-data tests for real FTC xor_29 pulse validation.

These tests never invoke HSPICE.  They protect the measurement interface,
same-run timing arithmetic, and anchor/fine decision contract; retained task
HSPICE scenarios remain the required electrical acceptance evidence.
"""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import generate_ftc_deck as deck  # noqa: E402  # Exercise the public deck rendering hook.
import run_ftc_characterization as characterization  # noqa: E402  # Load the frozen FTC inputs.
import run_real_xor_pulse_width as real  # noqa: E402  # Exercise task-owned pure helpers.


def physical_row(vdd_v, width_ps, valid=1, peak_ratio=0.98):
    """Create one complete synthetic row with only task-required observables.

    The synthetic values are deliberately simple and are used solely to prove
    decision logic.  They do not model a library cell or replace the physical
    HSPICE validation run.
    """

    return {
        "vdd_v": vdd_v,
        "W_real_ps": width_ps,
        "W_proxy_ps": width_ps - 10.0,
        "width_error_ps": 10.0,
        "width_ratio": width_ps / (width_ps - 10.0),
        "xor29_peak_ratio": peak_ratio,
        "valid": valid,
    }


class FtcRealXorPulseWidthTest(unittest.TestCase):
    """Protect the smallest task-specific physical-validation surface."""

    def setUp(self):
        """Load immutable repository inputs for each independent assertion."""

        self.config = characterization.load_json(FTC_ROOT / "ftc_config.json")
        self.cells = characterization.load_json(FTC_ROOT / "discovery" / "selected_cells.json")
        self.point = self.config["selected_operating_point"]

    def rendered_xor_deck(self, pulse_width_taps=None, include_pulse_argument=False):
        """Render the selected XOR topology, optionally omitting the new argument."""

        kwargs = {
            "config": self.config,
            "cells": self.cells,
            "vdd_v": 1.10,
            "mode": "xor",
            "initial_rvt_stages": self.point["initial_rvt_stages"],
            "initial_lvt_stages": self.point["initial_lvt_stages"],
            "capture_phase_s": self.point["capture_phase_s"],
        }
        if include_pulse_argument:
            kwargs["pulse_width_taps"] = pulse_width_taps
        return deck.render_deck(**kwargs)

    def test_default_deck_is_identical_and_tap29_keeps_full_xor_bank(self):
        """Default callers retain legacy text while tap29 adds only three measures."""

        legacy = self.rendered_xor_deck()
        self.assertEqual(legacy, self.rendered_xor_deck(None, include_pulse_argument=True))
        measured = self.rendered_xor_deck([29], include_pulse_argument=True)
        self.assertEqual(measured.count("XXOR_"), 30)
        self.assertIn("XXOR_29 xor_29 ", measured)
        for measure in ("xor_29_rise", "xor_29_fall", "xor_29_peak_v"):
            self.assertEqual(measured.count(measure), 1)
        self.assertNotIn("xor_28_rise", measured)
        self.assertEqual(measured.count(".measure tran xor_"), legacy.count(".measure tran xor_") + 3)

    def test_fixed_operating_point_and_same_run_timing_arithmetic(self):
        """The task must remain at 4/0 and preserve the stated timing identity."""

        point = real.verify_fixed_experiment(self.config, self.cells)
        self.assertEqual(point["initial_rvt_stages"], 4)
        self.assertEqual(point["initial_lvt_stages"], 0)
        self.assertEqual(point["capture_phase_s"], 3.0e-10)
        rvt = [1.0e-9 + index * 1.0e-12 for index in range(30)]
        lvt = [1.0e-9 + index * 1.0e-12 for index in range(30)]
        rvt[29] = 2.00e-9
        lvt[29] = 1.80e-9
        row = real.row_from_record(1.0, {
            "rvt_crossings_s": rvt,
            "lvt_crossings_s": lvt,
            "pulse_width_measurements": [{
                "tap_index": 29,
                "xor_rise_s": 1.90e-9,
                "xor_fall_s": 2.25e-9,
                "xor_peak_v": 0.98,
            }],
        })
        self.assertEqual(row["valid"], 1)
        self.assertAlmostEqual(row["W_proxy_ps"], 200.0)
        self.assertAlmostEqual(row["W_real_ps"], 350.0)
        self.assertAlmostEqual(row["start_shift_ps"], 100.0)
        self.assertAlmostEqual(row["end_shift_ps"], 250.0)
        self.assertAlmostEqual(row["W_real_ps"], row["W_proxy_ps"] + row["end_shift_ps"] - row["start_shift_ps"])
        self.assertAlmostEqual(row["width_error_ps"], 150.0)
        self.assertAlmostEqual(row["width_ratio"], 1.75)

    def test_anchor_gate_prevents_any_fine_grid_after_failure(self):
        """A failed anchor returns no fine VDDs rather than attempting a rescue run."""

        anchors = [physical_row(vdd, 100.0 + index * 10.0) for index, vdd in enumerate(real.ANCHOR_VDDS)]
        decision, _, _ = real.anchor_decision(anchors)
        self.assertEqual(decision, "GO")
        self.assertEqual(real.fine_vdds_after_anchor(decision), real.FINE_VDDS)
        anchors[-1]["valid"] = 0
        failed, _, _ = real.anchor_decision(anchors)
        self.assertEqual(failed, "NO-GO")
        self.assertEqual(real.fine_vdds_after_anchor(failed), ())

    def test_fine_go_conditional_and_no_go_classes(self):
        """Strict, one-local-error, and missing-pulse grids keep distinct outcomes."""

        strict = [physical_row(vdd, 100.0 + index) for index, vdd in enumerate(real.FINE_VDDS)]
        self.assertEqual(real.fine_decision(strict)[0], "GO")
        one_reverse = [physical_row(vdd, 100.0 + index) for index, vdd in enumerate(real.FINE_VDDS)]
        one_reverse[12]["W_real_ps"] = one_reverse[11]["W_real_ps"] - 0.5
        self.assertEqual(real.fine_decision(one_reverse)[0], "CONDITIONAL")
        missing = [dict(row) for row in strict]
        missing[20]["valid"] = 0
        self.assertEqual(real.fine_decision(missing)[0], "NO-GO")

    def test_synthetic_fine_artifacts_use_the_fixed_schema_and_two_figures(self):
        """Pure-data publication verifies CSV, SVG, and report paths without HSPICE."""

        anchors = [physical_row(vdd, 100.0 + index * 10.0) for index, vdd in enumerate(real.ANCHOR_VDDS)]
        fine = [physical_row(vdd, 100.0 + index) for index, vdd in enumerate(real.FINE_VDDS)]
        anchor_result = real.anchor_decision(anchors)
        fine_result = real.fine_decision(fine)
        metrics = real.fine_metrics(fine, fine_result[2])
        with tempfile.TemporaryDirectory(prefix="ftc_real_xor_pulse_width_") as temporary:
            root = Path(temporary)
            evidence = root / "analysis"
            report = root / "report.md"
            real.write_csv(evidence / "fine.csv", fine)
            real.plot_fine(fine, evidence)
            real.render_report(report, anchors, anchor_result, fine, fine_result, metrics)
            with (evidence / "fine.csv").open(newline="", encoding="utf-8") as stream:
                self.assertEqual(next(csv.reader(stream)), list(real.RESULT_FIELDS))
            self.assertTrue((evidence / "fig1_real_vs_proxy.svg").is_file())
            self.assertTrue((evidence / "fig2_width_error_vs_vdd.svg").is_file())
            text = report.read_text(encoding="utf-8")
            self.assertIn("Fine transfer", text)
            self.assertIn("Final decision", text)
            self.assertLess(text.index("Real span"), text.index("## E. Physical interpretation"))


if __name__ == "__main__":
    unittest.main()
