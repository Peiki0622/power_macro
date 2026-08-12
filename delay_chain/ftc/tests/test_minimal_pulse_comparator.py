"""Structural and pure-data regressions for the fixed FTC pulse comparator.

These tests do not invoke HSPICE.  They protect the rendered real-cell netlist,
frozen-input contract, code-to-tap mapping, result schema, and final decision
logic.  The separate 16-scenario HSPICE run remains the electrical acceptance
evidence and cannot be replaced by this synthetic coverage.
"""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_minimal_pulse_comparator as study  # noqa: E402  # Exercise the task-owned public helpers.


def synthetic_rows(vdd_v=1.10, width_ps=300.0, delays=None, q_values=None):
    """Create one valid local-VDD evidence set with explicit timing relations.

    The fixture models only post-HSPICE scalar values.  It is deliberately not
    a behavioral model of the standard cells and does not claim physical delay
    numbers.  Its purpose is to make every decision branch deterministic.
    """

    delays = list(delays if delays is not None else (120.0, 150.0, 180.0, 220.0, 340.0, 380.0, 420.0, 460.0))
    expected = [1 if width_ps > delay else 0 for delay in delays]
    q_values = list(q_values if q_values is not None else expected)
    rows = []
    for code, (delay, q_value) in enumerate(zip(delays, q_values)):
        xor_rise = 1.50e-9
        xor_fall = xor_rise + width_ps * 1.0e-12
        ck_rise = xor_rise + delay * 1.0e-12
        row = {
            "vdd_v": vdd_v, "code": code, "selected_tap": study.THRESHOLD_TAPS[code],
            "scenario": "synthetic/code{}".format(code),
            "t_xor_rise_s": xor_rise, "t_xor_fall_s": xor_fall,
            "w_s_int_ps": width_ps, "t_ck_rise_s": ck_rise, "d_code_ps": delay,
            "q_final_v": vdd_v if q_value else 0.0, "q_final": q_value,
            "w_s_frozen_ps": width_ps - 10.0, "delta_w_load_ps": 10.0,
            "q_expected": expected[code], "q_matches_expected": int(q_value == expected[code]), "valid": 1,
        }
        rows.append(row)
    return rows


class MinimalPulseComparatorTest(unittest.TestCase):
    """Protect the minimal architecture rather than a generalized timing macro."""

    def setUp(self):
        """Load existing frozen inputs without editing any committed evidence."""

        self.config = study.load_json(FTC_ROOT / "ftc_config.json")
        self.cells = study.load_json(FTC_ROOT / "discovery" / "selected_cells.json")
        self.mux = study.parse_manifest_mux(
            FTC_ROOT / "analysis" / "reference_sensitivity_contrast" / "candidate_manifest.csv",
            self.cells,
        )

    def test_frozen_inputs_and_prior_provenance_remain_compatible(self):
        """The new primitive must only use the explicitly frozen earlier evidence."""

        study.verify_frozen_inputs(self.config, self.cells, self.mux)
        study.verify_mux_collateral(self.mux)
        study.verify_frozen_provenance()
        widths = study.frozen_widths(FTC_ROOT / "analysis" / "real_xor_pulse_width" / "fine.csv")
        self.assertAlmostEqual(widths[1.10], 242.236313)
        self.assertAlmostEqual(widths[0.90], 470.158019)

    def test_rendered_deck_has_exact_fixed_sensor_threshold_and_dff_structure(self):
        """Inspect all port-level instances for code 0 and code 7 selection rails.

        This check keeps the original complete XOR bank, verifies that the
        delay chain starts at xor_29, and proves the MUX tree and DFF connect
        according to the documented positional CDL interfaces.
        """

        low = study.render_integrated_deck(self.config, self.cells, 1.10, 0)
        high = study.render_integrated_deck(self.config, self.cells, 0.90, 7)
        self.assertEqual(sum(line.startswith("XXOR_") for line in low.splitlines()), 30)
        self.assertEqual(sum(line.startswith("XTHR_BUF_") for line in low.splitlines()), 24)
        self.assertEqual(sum(line.startswith("XMUX_") for line in low.splitlines()), 7)
        self.assertEqual(sum(line.startswith("XDFF ") for line in low.splitlines()), 1)
        self.assertIn("XTHR_BUF_01 thr_tap_1 vdd_a vdd_a vss_a vss_a xor_29 BUF_X0P7M_A9TL40", low)
        self.assertIn("XMUX_L1_0 mux_l1_0 vdd_a vdd_a vss_a vss_a thr_tap_10 thr_tap_12 code0 MXT2_X0P5M_A9TL40", low)
        self.assertIn("XMUX_L3 dff_ck vdd_a vdd_a vss_a vss_a mux_l2_0 mux_l2_1 code2 MXT2_X0P5M_A9TL40", low)
        self.assertIn("XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset DFFRPQ_X0P5M_A9TR40", low)
        self.assertIn("V_CODE0 code0 vss_a 0", low)
        self.assertIn("V_CODE1 code1 vss_a 0", low)
        self.assertIn("V_CODE2 code2 vss_a 0", low)
        self.assertIn("V_CODE0 code0 vss_a 'VDD_VALUE'", high)
        self.assertIn("V_CODE1 code1 vss_a 'VDD_VALUE'", high)
        self.assertIn("V_CODE2 code2 vss_a 'VDD_VALUE'", high)
        for name in ("t_xor_rise", "t_xor_fall", "t_ck_rise", "q_final_v"):
            self.assertEqual(low.count(name), 1)

    def test_fixed_code_mapping_and_architecture_metadata(self):
        """Code order must be explicit and monotonically select the eight requested taps."""

        self.assertEqual({code: study.THRESHOLD_TAPS[code] for code in study.CODES}, {
            0: 10, 1: 12, 2: 14, 3: 16, 4: 18, 5: 20, 6: 22, 7: 24,
        })
        value = study.architecture(self.cells, self.mux)
        self.assertEqual(value["threshold"]["buffer_count"], 24)
        self.assertEqual(value["threshold"]["mux_count"], 7)
        self.assertEqual(value["threshold"]["mux_select_truth"], {"0": "A", "1": "B"})
        self.assertEqual(value["same_rail_mapping"], {"VDD": "VDD_A", "VNW": "VDD_A", "VPW": "VSS_A", "VSS": "VSS_A"})

    def test_record_conversion_retains_physical_measurement_arithmetic(self):
        """Width, threshold, frozen-load delta, and DFF bit use their stated definitions."""

        row = study.row_from_record({
            "vdd_v": 1.10, "code": 2, "scenario": "synthetic",
            "t_xor_rise_s": 1.50e-9, "t_xor_fall_s": 1.80e-9,
            "t_ck_rise_s": 1.72e-9, "q_final_v": 1.10,
        }, {1.10: 242.236313, 0.90: 470.158019})
        self.assertEqual(row["valid"], 1)
        self.assertAlmostEqual(row["w_s_int_ps"], 300.0)
        self.assertAlmostEqual(row["d_code_ps"], 220.0)
        self.assertAlmostEqual(row["delta_w_load_ps"], 57.763687)
        self.assertEqual(row["q_expected"], 1)
        self.assertEqual(row["q_final"], 1)
        self.assertEqual(row["q_matches_expected"], 1)
        too_late = study.row_from_record({
            "vdd_v": 1.10, "code": 0, "scenario": "late",
            "t_xor_rise_s": 1.50e-9, "t_xor_fall_s": 2.50e-9,
            "t_ck_rise_s": study.LATEST_ALLOWED_CK_S + 1.0e-12, "q_final_v": 1.10,
        }, {1.10: 242.236313, 0.90: 470.158019})
        self.assertEqual(too_late["valid"], 0)

    def test_gate_accepts_monotonic_bracketed_two_voltage_comparison(self):
        """Both workpoints require one real 1-to-0 DFF transition and correct timing relation."""

        result = study.evaluate(synthetic_rows(1.10) + synthetic_rows(0.90, width_ps=500.0, delays=(200.0, 250.0, 320.0, 400.0, 540.0, 620.0, 700.0, 780.0)))
        self.assertEqual(result["decision"], "GO")
        self.assertTrue(all(item["monotonic"] for item in result["per_voltage"]))
        self.assertTrue(all(item["bracketed"] for item in result["per_voltage"]))

    def test_gate_rejects_nonmonotonic_and_unbracketed_ranges(self):
        """No smoothing or tap-range rescue is allowed after either physical failure."""

        nonmonotonic = synthetic_rows(1.10, delays=(120.0, 180.0, 170.0, 220.0, 340.0, 380.0, 420.0, 460.0))
        normal = synthetic_rows(0.90, width_ps=500.0, delays=(200.0, 250.0, 320.0, 400.0, 540.0, 620.0, 700.0, 780.0))
        self.assertEqual(study.evaluate(nonmonotonic + normal)["decision"], "NO-GO")
        unbracketed = synthetic_rows(1.10, width_ps=80.0)
        self.assertEqual(study.evaluate(unbracketed + normal)["decision"], "NO-GO")

    def test_only_adjacent_transition_codes_can_be_exempt_from_q_match(self):
        """A mismatch at code 3 or 4 is recorded near the transition; code 0 is not exempt."""

        near_boundary = synthetic_rows(1.10, q_values=(1, 1, 1, 0, 1, 0, 0, 0))
        # There are three transitions, so only codes participating in a
        # transition may be excluded.  An independent mismatch at code 0 must
        # still fail the comparison gate.
        near_boundary[0]["q_final"] = 0
        near_boundary[0]["q_final_v"] = 0.0
        near_boundary[0]["q_matches_expected"] = 0
        normal = synthetic_rows(0.90, width_ps=500.0, delays=(200.0, 250.0, 320.0, 400.0, 540.0, 620.0, 700.0, 780.0))
        result = study.evaluate(near_boundary + normal)
        self.assertEqual(result["decision"], "NO-GO")

    def test_compact_artifacts_have_fixed_schema_and_report_answers(self):
        """Temporary publication covers CSV, JSON, SVG, and the concise research report."""

        rows = synthetic_rows(1.10) + synthetic_rows(0.90, width_ps=500.0, delays=(200.0, 250.0, 320.0, 400.0, 540.0, 620.0, 700.0, 780.0))
        result = study.evaluate(rows)
        with tempfile.TemporaryDirectory(prefix="ftc_minimal_pulse_comparator_") as temporary:
            root = Path(temporary)
            study.write_csv(root / "code_sweep.csv", rows)
            study.write_json(root / "architecture.json", study.architecture(self.cells, self.mux))
            study.write_json(root / "summary.json", {"schema_version": 1, **result})
            study.plot_threshold(rows, root / "threshold_vs_pulse.svg")
            study.render_report(root / "report.md", result)
            with (root / "code_sweep.csv").open(newline="", encoding="utf-8") as stream:
                self.assertEqual(next(csv.reader(stream)), list(study.RESULT_FIELDS))
            self.assertEqual(json.loads((root / "summary.json").read_text(encoding="utf-8"))["decision"], "GO")
            self.assertTrue((root / "threshold_vs_pulse.svg").is_file())
            report = (root / "report.md").read_text(encoding="utf-8")
            self.assertIn("真实标准单元可编程 delay", report)
            self.assertIn("static self-calibration", report)


if __name__ == "__main__":
    unittest.main()
