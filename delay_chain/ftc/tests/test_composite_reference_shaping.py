"""Data and terminal-gate tests for the narrow composite-reference study.

These tests do not run HSPICE because the task permits no physical simulation
without a predicted shortlist.  They prove the analytical reconstruction,
bounded enumeration, frozen-data outcome, and generated evidence contracts.
"""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_composite_reference_shaping as study  # noqa: E402


class CompositeReferenceShapingTest(unittest.TestCase):
    """Protect the exact arithmetic and early-stop behavior of this task."""

    def test_composite_reconstructs_delay_then_recalibrates(self):
        """The result differs from parent-residual addition by construction.

        Both parents see a 12 ps sensor temperature move, but their recovered
        delay moves are 1 ps and 2 ps.  A 1:2 macro has 5 ps total movement,
        gets a new k_C=2, and therefore produces a 2 ps residual rather than
        the incorrect 6 ps sum of the three parent residual contributions.
        """

        evidence = {
            "simple": {
                ("buf_rvt", 1.10): {"d_r_25c_ps": 10.0, "k": 10.0, "e_t_m40c_ps": 2.0, "e_t_125c_ps": -1.0, "e_v_50mv_ps": 1.0, "e_v_100mv_ps": 3.0},
                ("buf_lvt", 1.10): {"d_r_25c_ps": 20.0, "k": 5.0, "e_t_m40c_ps": 2.0, "e_t_125c_ps": -1.0, "e_v_50mv_ps": 1.0, "e_v_100mv_ps": 3.0},
            },
            "fine": {1.10: 100.0, 1.05: 106.0, 1.00: 112.0},
            "temperature": {(1.10, -40.0): 112.0, (1.10, 25.0): 100.0, (1.10, 125.0): 94.0},
        }
        row = study.predict_row(evidence, "buf_rvt", "buf_lvt", 1, 2, 1.10)
        self.assertAlmostEqual(row["d_c_25c_ps"], 50.0)
        self.assertAlmostEqual(row["k_c"], 2.0)
        self.assertAlmostEqual(row["e_t_m40c_ps"], 2.0)
        self.assertNotAlmostEqual(row["e_t_m40c_ps"], 6.0)

    def test_frozen_evidence_has_only_legal_mixed_vt_candidates(self):
        """All 45 legal combinations have exactly two TT rows and no shortlist."""

        evidence = study.load_evidence()
        rows, shortlist = study.predict_candidates(evidence)
        self.assertEqual(len({row["candidate_id"] for row in rows}), 45)
        self.assertEqual(len(rows), 90)
        self.assertEqual(shortlist, [])
        self.assertTrue(all(row["rvt_candidate_id"].endswith("_rvt") for row in rows))
        self.assertTrue(all(row["lvt_candidate_id"].endswith("_lvt") for row in rows))
        self.assertTrue(all(row["total_standard_cells"] <= 4 for row in rows))
        self.assertTrue(all((row["rvt_units"], row["lvt_units"]) in study.RATIOS for row in rows))

    def test_main_writes_auditable_no_go_without_hspice_outputs(self):
        """A complete invocation writes only prediction, summary, and report."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            analysis = root / "analysis"
            report = root / "report.md"
            self.assertEqual(study.main(["--analysis-dir", str(analysis), "--report-output", str(report)]), 0)
            with (analysis / "predicted_candidates.csv").open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            summary = json.loads((analysis / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 90)
            self.assertEqual(summary["decision"], "NO-GO")
            self.assertFalse(summary["hspice_executed"])
            self.assertFalse((analysis / "measured_tt.csv").exists())
            self.assertFalse((analysis / "pvt_confirmation.csv").exists())
            self.assertIn("Passive Sensitivity-Contrast Reference = NO-GO", report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
