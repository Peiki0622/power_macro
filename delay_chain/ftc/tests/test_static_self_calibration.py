"""Evidence-replay tests for the FTC 0.80--1.10 V static calibration result.

The original r2 HSPICE directories are deliberately read-only inputs here.
These tests verify that the publication code reconstructs its compact trace
from retained raw MEAS/listing/deck collateral.  They never launch HSPICE and
therefore cannot be mistaken for a fresh electrical simulation.
"""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_static_self_calibration as study  # noqa: E402  # Exercise replay-only public helpers.


class StaticSelfCalibrationReplayTests(unittest.TestCase):
    """Protect the r2 evidence boundary, current voltage range, and GO gate."""

    def setUp(self):
        """Bind every test to the completed physical r2 root without modifying it."""

        self.raw_run = FTC_ROOT / "runs/static_self_calibration_full_range/r2"

    def test_scenario_name_parser_excludes_sizing_and_preserves_scan_identity(self):
        """Only calibration scenario directories may become legal-range trace rows."""

        self.assertIsNone(study.parse_scenario_name("sizing_tt25_v0p75_code7"))
        self.assertEqual(
            study.parse_scenario_name("v0p80_step13_code5"),
            {"vdd_centi_v": 80, "step_index": 13, "code": 5},
        )

    def test_r2_replay_reconstructs_every_legal_raw_probe(self):
        """Cross-check all 54 retained physical probes before applying the gate."""

        rows = study.replay_r2_trace(self.raw_run)
        self.assertEqual(len(rows), 54)
        self.assertEqual(sorted({float(row["vdd_v"]) for row in rows}), list(study.VDD_POINTS))
        self.assertTrue(all(bool(row["valid"]) for row in rows))
        self.assertEqual([int(row["code"]) for row in rows if float(row["vdd_v"]) == 0.80], list(range(8)))
        result = study.evaluate_all(rows)
        self.assertEqual(result["decision"], "Static Self Calibration + Full-Range Code Headroom = GO")
        self.assertEqual([item["lock_code"] for item in result["per_voltage"]], [5, 5, 5, 5, 5, 4, 4])
        self.assertEqual([item["headroom_up"] for item in result["per_voltage"]], [2, 2, 2, 2, 2, 3, 3])
        self.assertTrue(all(item["monotonic"] and item["q_monotonic"] for item in result["per_voltage"]))

    def test_mapping_states_verified_coverage_without_a_minimum_claim(self):
        """Prevent a replay from accidentally becoming an unproven sizing claim."""

        mapping = study.replay_mapping()
        self.assertEqual(mapping["tap_list"], [10, 12, 14, 16, 18, 36, 37, 38])
        self.assertEqual(mapping["validated_vdd_range_v"], [0.80, 1.10])
        self.assertEqual(mapping["selection_basis"], "reused_r2_verified_mapping")
        self.assertTrue(mapping["minimum_mapping_not_claimed"])

    def test_public_artifacts_have_current_schema_and_four_go_answers(self):
        """Write temporary publication files and verify their trace/report contract."""

        rows = study.replay_r2_trace(self.raw_run)
        result = study.evaluate_all(rows)
        mapping = study.replay_mapping()
        with tempfile.TemporaryDirectory(prefix="ftc_static_calibration_replay_") as temporary:
            root = Path(temporary)
            trace = root / "calibration_trace.csv"
            report = root / "report.md"
            summary = root / "summary.json"
            study.write_csv(trace, rows)
            study.write_json(summary, {"mapping": mapping, **result})
            study.render_report(report, mapping, result)
            with trace.open(newline="", encoding="utf-8") as stream:
                replayed = list(csv.DictReader(stream))
            self.assertEqual(len(replayed), 54)
            self.assertEqual(list(replayed[0]), list(study.TRACE_FIELDS))
            self.assertEqual(json.loads(summary.read_text(encoding="utf-8"))["decision"], result["decision"])
            rendered = report.read_text(encoding="utf-8")
            self.assertIn("0.80--1.10 V", rendered)
            self.assertIn("new-range minimum mapping claimed: no", rendered)
            self.assertIn("可以", rendered)


if __name__ == "__main__":
    unittest.main()
