"""Unit tests for pure FTC XOR pulse-width proxy post-processing.

The module under test reads completed CSV evidence only.  These tests never
import the FTC deck generator or characterization runner, so passing them is
not evidence of a new HSPICE simulation or a physical XOR output measurement.
"""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_xor_pulse_width_vdd as analysis  # noqa: E402  # Test public pure-analysis helpers.


class FtcXorPulseWidthVddTest(unittest.TestCase):
    """Exercise the documented input, arithmetic, ranking, and artifact contracts."""

    @staticmethod
    def crossing_row(vdd: float, phase_id: str = "phi_p00", phase_multiplier: int = 0) -> dict:
        """Build one valid 30-tap synthetic physical-evidence row.

        Every tap's RVT crossing is later than its LVT crossing.  The measured
        separation grows both with tap index and lower VDD, which makes the
        generated fine/coarse fixtures suitable for deterministic GO-path
        output checks without claiming those synthetic numbers are silicon.
        """

        lvt = [1.0e-9 + tap * 1.0e-12 for tap in range(analysis.TAP_COUNT)]
        # Later taps receive a larger synthetic VDD slope so the complete-flow
        # test has one unambiguous best candidate without adding a ranking
        # threshold that the real analysis does not use.
        separation_ps = [20.0 + tap + (1.10 - vdd) * (100.0 + tap) for tap in range(analysis.TAP_COUNT)]
        rvt = [crossing + delta * 1.0e-12 for crossing, delta in zip(lvt, separation_ps)]
        return {
            "vdd_v": "{:.2f}".format(vdd),
            "initial_rvt_stages": "4",
            "initial_lvt_stages": "0",
            "rvt_crossings_s": json.dumps(rvt),
            "lvt_crossings_s": json.dumps(lvt),
            "phase_id": phase_id,
            "phase_multiplier": str(phase_multiplier),
        }

    @staticmethod
    def write_rows(path: Path, rows: list) -> None:
        """Write a temporary CSV with fixed test-only source columns."""

        fields = [
            "vdd_v",
            "initial_rvt_stages",
            "initial_lvt_stages",
            "rvt_crossings_s",
            "lvt_crossings_s",
            "phase_id",
            "phase_multiplier",
        ]
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_crossing_parser_requires_thirty_finite_positive_values(self) -> None:
        """A missing, short, or nonphysical crossing array must stop analysis."""

        valid = self.crossing_row(1.10)
        parsed = analysis.validate_record(valid, Path("synthetic.csv"), 2)
        self.assertEqual(len(parsed["rvt_crossings_s"]), analysis.TAP_COUNT)
        invalid = dict(valid)
        invalid["rvt_crossings_s"] = json.dumps([1.0e-9] * 29)
        with self.assertRaisesRegex(ValueError, "must contain 30 crossings"):
            analysis.validate_record(invalid, Path("synthetic.csv"), 3)
        invalid["rvt_crossings_s"] = json.dumps([1.0e-9] * 29 + [0.0])
        with self.assertRaisesRegex(ValueError, "finite positive crossings"):
            analysis.validate_record(invalid, Path("synthetic.csv"), 4)

    def test_proxy_units_signed_delta_and_lead_path(self) -> None:
        """The matrix must retain signed path order while deriving the ps width."""

        row = self.crossing_row(1.10)
        lvt = json.loads(row["lvt_crossings_s"])
        rvt = list(lvt)
        rvt[0] += 2.5e-12
        rvt[1] -= 3.0e-12
        rvt[2] = lvt[2]
        row["rvt_crossings_s"] = json.dumps(rvt)
        matrix = analysis.build_proxy_matrix([analysis.validate_record(row, Path("synthetic.csv"), 2)])
        self.assertAlmostEqual(matrix[0]["delta_signed_ps"], 2.5)
        self.assertAlmostEqual(matrix[0]["xor_width_proxy_ps"], 2.5)
        self.assertEqual(matrix[0]["lead_path"], "LVT")
        self.assertAlmostEqual(matrix[1]["delta_signed_ps"], -3.0)
        self.assertAlmostEqual(matrix[1]["xor_width_proxy_ps"], 3.0)
        self.assertEqual(matrix[1]["lead_path"], "RVT")
        self.assertEqual(matrix[2]["lead_path"], "tie")

    def test_monotonic_classes_and_sign_flip_rejection(self) -> None:
        """Plateaus remain visible and a path reversal cannot enter the shortlist."""

        self.assertEqual(analysis.monotonic_summary([1.0, 2.0, 3.0])["monotonic_class"], "strict_increasing")
        self.assertEqual(analysis.monotonic_summary([3.0, 2.0, 1.0])["monotonic_class"], "strict_decreasing")
        plateau = analysis.monotonic_summary([1.0, 1.0, 2.0])
        self.assertEqual(plateau["monotonic_class"], "nondecreasing_with_plateau")
        self.assertEqual(plateau["plateau_count"], 1)
        self.assertEqual(analysis.monotonic_summary([1.0, 3.0, 2.0])["monotonic_class"], "nonmonotonic")
        sign_flip = analysis.lead_sign_metrics([5.0, 0.0, -2.0])
        self.assertFalse(sign_flip["lead_sign_stable"])
        self.assertEqual(sign_flip["sign_flip_count"], 1)
        rejected = {
            "tap_index": 4,
            **sign_flip,
            "monotonic_class": "strict_increasing",
            "plateau_count": 0,
            "span_ps": 100.0,
            "median_abs_sensitivity_ps_per_100mV": 20.0,
            "step_margin_ps": 10.0,
        }
        self.assertEqual(analysis.rank_and_shortlist([rejected], True), [])

    def test_nominal_coarse_selection_supports_phase_id_and_multiplier(self) -> None:
        """Only nominal phase rows form a coarse VDD curve; repeats stay separate."""

        nominal = self.crossing_row(1.10, "phi_p00", 0)
        shifted = self.crossing_row(1.10, "phi_p01", 1)
        selected = analysis.select_nominal_coarse_rows([nominal, shifted], list(nominal), Path("coarse.csv"))
        self.assertEqual([row["phase_id"] for row in selected], ["phi_p00"])
        multiplier_nominal = {key: value for key, value in nominal.items() if key != "phase_id"}
        multiplier_shifted = {key: value for key, value in shifted.items() if key != "phase_id"}
        selected = analysis.select_nominal_coarse_rows(
            [multiplier_nominal, multiplier_shifted], list(multiplier_nominal), Path("coarse.csv")
        )
        self.assertEqual([row["phase_multiplier"] for row in selected], ["0"])

    def test_full_synthetic_flow_is_deterministic_and_uses_stable_csv_schemas(self) -> None:
        """Run complete temporary CSV post-processing twice without physical tools."""

        fine_rows = [self.crossing_row(vdd) for vdd in analysis.FINE_VDDS]
        coarse_rows = []
        for vdd in analysis.COARSE_VDDS:
            coarse_rows.extend((self.crossing_row(vdd, "phi_p00", 0), self.crossing_row(vdd, "phi_p01", 1)))
        with tempfile.TemporaryDirectory(prefix="ftc_xor_pulse_width_") as temporary:
            root = Path(temporary)
            fine = root / "fine.csv"
            coarse = root / "coarse.csv"
            self.write_rows(fine, fine_rows)
            self.write_rows(coarse, coarse_rows)
            first = root / "first"
            second = root / "second"
            first_report = root / "first.md"
            second_report = root / "second.md"
            first_result = analysis.run_analysis(fine, coarse, first, first_report)
            second_result = analysis.run_analysis(fine, coarse, second, second_report)
            self.assertEqual(first_result["decision"], "GO")
            self.assertEqual(first_result["best_tap"], analysis.TAP_COUNT - 1)
            self.assertEqual(first_result["shortlisted_taps"], [analysis.TAP_COUNT - 1])
            for name in ("xor_pulse_width_matrix.csv", "tap_metrics.csv", "repeat_consistency.csv", "summary.json"):
                self.assertEqual((first / name).read_text(encoding="utf-8"), (second / name).read_text(encoding="utf-8"), name)
            self.assertEqual(first_report.read_text(encoding="utf-8"), second_report.read_text(encoding="utf-8"))
            with (first / "xor_pulse_width_matrix.csv").open(newline="", encoding="utf-8") as stream:
                self.assertEqual(next(csv.reader(stream)), list(analysis.MATRIX_FIELDS))
            with (first / "tap_metrics.csv").open(newline="", encoding="utf-8") as stream:
                metric_fields = next(csv.reader(stream))
            self.assertIn("step_margin_ps", metric_fields)
            with (first / "repeat_consistency.csv").open(newline="", encoding="utf-8") as stream:
                repeat_rows = list(csv.DictReader(stream))
            # Repeat consistency follows the current seven-point legal coarse
            # grid; the retained 0.75 V row is excluded from re-publication.
            self.assertEqual(len(repeat_rows), len(analysis.COARSE_VDDS) * analysis.TAP_COUNT)
            summary = json.loads((first / "summary.json").read_text(encoding="utf-8"))
            self.assertFalse(summary["used_new_hspice"])
            # The primary synthetic fine curve follows the formal 31-point
            # 1.10--0.80 V grid, not the retired 36-point historical range.
            self.assertEqual(summary["vdd_point_count"], len(analysis.FINE_VDDS))
            self.assertIn("not the output pulse width of a real XOR cell", first_report.read_text(encoding="utf-8"))
            fallback_kind, _, fallback_records = analysis.load_primary_evidence(root / "missing-fine.csv", coarse)
            self.assertEqual(fallback_kind, "8-point committed coarse evidence")
            self.assertEqual(len(fallback_records), len(analysis.COARSE_VDDS))


if __name__ == "__main__":
    unittest.main()
