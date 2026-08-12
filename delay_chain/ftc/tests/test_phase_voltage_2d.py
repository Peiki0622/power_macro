"""Unit and physical-evidence regression tests for FTC phase/voltage analysis.

These tests intentionally exercise only CSV post-processing.  They do not
import the FTC HSPICE runner, deck renderer, or VCS-based RTL regressions, so
passing them cannot accidentally be mistaken for a new electrical simulation.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_phase_voltage_2d as analysis  # noqa: E402  # Test the public pure-analysis helpers.


class FtcPhaseVoltage2DTest(unittest.TestCase):
    """Validate both isolated math contracts and the completed local evidence flow."""

    @staticmethod
    def static_rows(valid: int = 1):
        """Build the exact 31-point static shape required by input validation.

        The codes vary only enough to keep the synthetic rows well formed.  A
        dedicated helper makes validation tests alter one intended condition
        instead of accidentally constructing an incomplete experiment.
        """

        return [
            {
                "vdd_v": "{:.2f}".format(vdd),
                "start_index": str(index % 10),
                "end_index": str(index % 10 + 1),
                "valid": str(valid),
            }
            for index, vdd in enumerate(analysis.STATIC_EXPECTED_VDDS)
        ]

    @staticmethod
    def phase_rows():
        """Build three valid minus/nominal/plus samples for each required anchor."""

        rows = []
        for anchor in analysis.ANCHORS:
            for offset, start, end in ((-1.0e-12, 2, 5), (0.0, 3, 6), (1.0e-12, 4, 7)):
                rows.append(
                    {
                        "vdd_v": "{:.2f}".format(anchor),
                        "phase_offset_s": "{:.12g}".format(offset),
                        "start_index": str(start),
                        "end_index": str(end),
                        "valid": "1",
                    }
                )
        return rows

    def test_cw_calculation_retains_original_fields(self) -> None:
        """C/W must be derived from, not substituted for, the FTC start/end contract."""

        rows = analysis.add_cw(
            [{"vdd_v": "1.10", "start_index": "10", "end_index": "18", "valid": "1", "source_tag": "physical"}]
        )
        self.assertEqual(rows[0]["start_index"], "10")
        self.assertEqual(rows[0]["end_index"], "18")
        self.assertEqual(rows[0]["source_tag"], "physical")
        self.assertEqual(rows[0]["c"], 28)
        self.assertEqual(rows[0]["w"], 9)

    def test_input_validation_rejects_invalid_static_sample(self) -> None:
        """A failed physical-validity bit must stop analysis rather than be ignored."""

        with self.assertRaisesRegex(ValueError, "valid=1"):
            analysis.validate_inputs(self.static_rows(valid=0), self.phase_rows(), Path("static.csv"), Path("phase.csv"))

    def test_phase_vector_and_zero_phase_handling(self) -> None:
        """Phase vectors use only measured endpoints and preserve a true zero vector."""

        moving = analysis.phase_vector(
            1.10,
            [
                {"phase_offset_s": -1.0, "c": 10, "w": 4},
                {"phase_offset_s": 0.0, "c": 11, "w": 5},
                {"phase_offset_s": 1.0, "c": 13, "w": 6},
            ],
        )
        self.assertEqual((moving["vPhi_C"], moving["vPhi_W"]), (3.0, 2.0))
        self.assertFalse(moving["phase_insensitive"])
        stationary = analysis.phase_vector(
            0.90,
            [
                {"phase_offset_s": -1.0, "c": 7, "w": 3},
                {"phase_offset_s": 0.0, "c": 7, "w": 3},
                {"phase_offset_s": 1.0, "c": 7, "w": 3},
            ],
        )
        self.assertTrue(stationary["phase_insensitive"])
        self.assertIsNone(analysis.cosine_metrics([1.0, 0.0], [0.0, 0.0])["acute_angle_deg"])

    def test_cosine_collinear_and_orthogonal_examples(self) -> None:
        """Acute angles must treat opposite parallel motion as equally non-separable."""

        collinear = analysis.cosine_metrics([3.0, 1.0], [-6.0, -2.0])
        orthogonal = analysis.cosine_metrics([1.0, 0.0], [0.0, -9.0])
        self.assertAlmostEqual(collinear["cosine_similarity"], -1.0)
        self.assertAlmostEqual(collinear["acute_angle_deg"], 0.0)
        self.assertAlmostEqual(orthogonal["absolute_cosine_similarity"], 0.0)
        self.assertAlmostEqual(orthogonal["acute_angle_deg"], 90.0)

    def test_projection_weight_normalization(self) -> None:
        """Scaling and sign duplicates must collapse before any hardware ranking occurs."""

        self.assertEqual(analysis.normalize_weight(4, 2), (2, 1))
        self.assertEqual(analysis.normalize_weight(-4, -2), (2, 1))
        self.assertEqual(analysis.normalize_weight(0, -4), (0, 1))
        with self.assertRaises(ValueError):
            analysis.normalize_weight(0, 0)

    def test_plateau_detection(self) -> None:
        """A plateau is a consecutive measured state, not a merged/smoothed range."""

        summary = analysis.plateau_summary([1.10, 1.09, 1.08, 1.07], [8, 8, 7, 7])
        self.assertEqual(len(summary["plateaus"]), 2)
        self.assertAlmostEqual(summary["maximum"]["width_v"], 0.01)
        self.assertEqual(summary["maximum"]["point_count"], 2)

    def test_local_ambiguity_reports_zero_voltage_span(self) -> None:
        """A local quantization plateau must remain explicit instead of using epsilon."""

        required_vdds = sorted({value for window in analysis.AMBIGUITY_WINDOWS.values() for value in window}, reverse=True)
        static = [{"vdd": value, "start": 1, "end": 1, "c": 2, "w": 1} for value in required_vdds]
        phase_groups = {
            anchor: [
                {"c": 2, "w": 1},
                {"c": 3, "w": 1},
                {"c": 2, "w": 1},
            ]
            for anchor in analysis.ANCHORS
        }
        rows = analysis.local_ambiguity(static, phase_groups, {"status": "skipped_near_collinear"})
        self.assertTrue(rows)
        self.assertTrue(all(row["status"] == "local_plateau" for row in rows))
        self.assertTrue(all(row["phase_to_voltage_ratio"] is None for row in rows))

    def test_historical_phase_evidence_is_rejected_without_a_0p80_anchor(self) -> None:
        """Do not turn a historical 0.75 V phase study into new-range coverage.

        The completed phase data has anchors at 1.10, 0.90 and 0.75 V only.
        The current formal contract requires 0.80 V, so validation must reject
        the historical input rather than interpolate or silently relabel it.
        The constrained re-publication report records this evidence gap.
        """

        static_input = FTC_ROOT / "runs/static_fine/static_transfer.csv"
        phase_input = FTC_ROOT / "runs/phase_sensitivity/phase_sensitivity.csv"
        with tempfile.TemporaryDirectory(prefix="ftc_phase_voltage_2d_") as temporary:
            root = Path(temporary)
            self.assertEqual(root.name, Path(temporary).name)
            # Validation rejects the historical source at its first missing
            # current-range requirement: its static transfer still contains
            # 36 rows down to 0.75 V rather than the required 31-row grid.
            with self.assertRaisesRegex(ValueError, "static transfer must contain 31 points"):
                analysis.run_analysis(static_input, phase_input, root / "result", root / "report.md")


if __name__ == "__main__":
    unittest.main()
