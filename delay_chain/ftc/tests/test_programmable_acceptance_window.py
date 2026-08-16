#!/usr/bin/env python3
"""Pure regressions for the FTC programmable acceptance-window task runner.

These checks deliberately do not invoke HSPICE.  They protect immutable input
contracts, electrical-deck structure and analysis gates before expensive raw
simulation is started by the task-specific runner.
"""

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = FTC_ROOT / "scripts" / "run_programmable_acceptance_window.py"
SPEC = importlib.util.spec_from_file_location("programmable_acceptance_window", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def row(baseline_vdd_v, margin_code, attack_vdd_v, q, valid=True):
    """Build one compact synthetic trace row using the frozen alarm-code policy."""

    lock_code = RUNNER.FROZEN_LOCKS[baseline_vdd_v]
    return {
        "baseline_vdd_v": baseline_vdd_v,
        "margin_code": margin_code,
        "lock_code": lock_code,
        "alarm_code": lock_code + margin_code,
        "attack_vdd_v": attack_vdd_v,
        "Q": q if valid else None,
        "valid": valid,
    }


def complete_rows(m1_depth_mv=40.0, m2_depth_mv=50.0):
    """Create a passing synthetic data set with M2 one grid step less sensitive."""

    rows = []
    for baseline_vdd_v in RUNNER.BASELINES_V:
        # M1 trips at 40mV and M2 at 50mV.  Both are legal at the 0.85V
        # baseline, and their 10mV separation exercises the distinction gate.
        m1_attack_v = baseline_vdd_v - m1_depth_mv / 1000.0
        rows.extend([row(baseline_vdd_v, 1, m1_attack_v + 0.01, 0), row(baseline_vdd_v, 1, m1_attack_v, 1)])
        m2_attack_v = baseline_vdd_v - m2_depth_mv / 1000.0
        rows.extend([row(baseline_vdd_v, 2, m2_attack_v + 0.01, 0), row(baseline_vdd_v, 2, m2_attack_v, 1)])
    return rows


class ProgrammableAcceptanceWindowTests(unittest.TestCase):
    """Test only deterministic logic; physical results are checked separately."""

    def normal_q0(self):
        """Return the exact normal evidence predicate required by every group."""

        return {(vdd_v, RUNNER.FROZEN_LOCKS[vdd_v] + margin): True for vdd_v in RUNNER.BASELINES_V for margin in RUNNER.MARGINS}

    def test_frozen_input_contract_and_headroom(self):
        """The runner must consume the existing seven-point mapping and Q=0 evidence."""

        inputs = RUNNER.frozen_inputs()
        self.assertEqual(inputs["mapping"]["tap_list"], list(RUNNER.FROZEN_TAPS))
        self.assertEqual(RUNNER.FROZEN_LOCKS[0.80], 5)
        self.assertEqual(RUNNER.FROZEN_LOCKS[1.10], 4)

    def test_coarse_schedule_respects_lowest_legal_rail(self):
        """Coarse attack begins 50mV down, reaches 0.80V and never goes lower."""

        self.assertEqual(RUNNER.coarse_points(0.85), [0.8])
        self.assertEqual(RUNNER.coarse_points(1.10), [1.05, 1.0, 0.95, 0.9, 0.85, 0.8])
        for baseline_vdd_v in RUNNER.BASELINES_V:
            self.assertNotIn(baseline_vdd_v, RUNNER.coarse_points(baseline_vdd_v))
            self.assertGreaterEqual(min(RUNNER.coarse_points(baseline_vdd_v)), RUNNER.VDD_MIN_V)

    def test_refinement_is_only_the_interior_10mv_bracket(self):
        """A 50mV bracket has four interior points and neither endpoint is rerun."""

        self.assertEqual(RUNNER.refinement_points(1.00, 0.95), [0.99, 0.98, 0.97, 0.96])
        self.assertEqual(RUNNER.refinement_points(0.85, 0.80), [0.84, 0.83, 0.82, 0.81])

    def test_analysis_reports_trip_and_resolution_ready(self):
        """A monotonic, ordered, distinct trace is admitted to the next planned stage."""

        analysis = RUNNER.analyze_rows(complete_rows(), self.normal_q0())
        self.assertTrue(analysis["mechanism_go"])
        self.assertEqual(analysis["mapping_decision"], "READY_FOR_PVT_DETECTOR_VERIFICATION")
        self.assertTrue(all(item["trip_status"] == "TRIP" for item in analysis["trip_rows"]))

    def test_analysis_reports_no_in_range_trip_and_invalid(self):
        """No trip and failed measurement retain distinct public status values."""

        rows = complete_rows()
        rows = [item for item in rows if not (item["baseline_vdd_v"] == 0.90 and item["margin_code"] == 1)]
        rows.append(row(0.90, 1, 0.85, 0))
        rows.append(row(1.00, 2, 0.95, 0, valid=False))
        analysis = RUNNER.analyze_rows(rows, self.normal_q0())
        by_key = {(item["baseline_vdd_v"], item["margin_code"]): item for item in analysis["trip_rows"]}
        self.assertEqual(by_key[(0.90, 1)]["trip_status"], "NO_IN_RANGE_TRIP")
        self.assertEqual(by_key[(1.00, 2)]["trip_status"], "INVALID")
        self.assertFalse(analysis["mechanism_go"])

    def test_analysis_rejects_q_reversion_and_margin_ordering(self):
        """A 0-to-1-to-0 response or a shallower M2 trip rejects the mechanism."""

        rows = complete_rows(m2_depth_mv=30.0)
        rows.extend([row(0.95, 1, 0.93, 1), row(0.95, 1, 0.92, 0)])
        analysis = RUNNER.analyze_rows(rows, self.normal_q0())
        self.assertFalse(analysis["mechanism_go"])
        self.assertTrue(any("Q reversion" in reason for reason in analysis["mechanism_reasons"]))
        self.assertTrue(any("shallower" in reason for reason in analysis["mechanism_reasons"]))

    def test_analysis_requires_m1_sensitivity_and_distinction(self):
        """Mechanism GO still requires both M1 sensitivity limits and a 10mV distinction."""

        insensitive = complete_rows()
        insensitive = [item for item in insensitive if not (item["baseline_vdd_v"] == 0.85)]
        # This synthetic row isolates the mathematical 50mV threshold check;
        # physical execution cannot generate it because the runner forbids a
        # rail below 0.80V before HSPICE is called.
        insensitive.extend([row(0.85, 1, 0.79, 1), row(0.85, 2, 0.80, 0)])
        analysis = RUNNER.analyze_rows(insensitive, self.normal_q0())
        self.assertTrue(analysis["mechanism_go"])
        self.assertEqual(analysis["mapping_decision"], "REFINEMENT_REQUIRED")
        same_boundary = complete_rows(m2_depth_mv=40.0)
        analysis = RUNNER.analyze_rows(same_boundary, self.normal_q0())
        self.assertTrue(analysis["mechanism_go"])
        self.assertEqual(analysis["mapping_decision"], "REFINEMENT_REQUIRED")

    def test_deck_retains_required_real_cell_structure(self):
        """The rendered deck must contain the frozen sensor, threshold and DFF topology."""

        config = RUNNER.load_json(FTC_ROOT / "ftc_config.json")
        cells = RUNNER.load_json(FTC_ROOT / "discovery/selected_cells.json")
        deck = RUNNER.render_deck(config, cells, 0.90, 6)
        self.assertEqual(deck.count("XXOR_"), 30)
        self.assertEqual(deck.count("XTHR_BUF_"), 38)
        self.assertEqual(deck.count("XMUX_"), 7)
        self.assertEqual(deck.count("XDFF q_final"), 1)
        self.assertIn("V_CODE0 code0 vss_a 0", deck)
        self.assertIn("V_CODE1 code1 vss_a 'VDD_VALUE'", deck)
        self.assertIn("V_CODE2 code2 vss_a 'VDD_VALUE'", deck)
        for measure in ("t_xor_rise", "t_xor_fall", "t_ck_rise", "q_final_v", "vdd_a_min_v"):
            self.assertIn(measure, deck)

    def test_public_artifact_schema_and_report(self):
        """Public writers produce only the requested compact CSV/JSON/Markdown artifacts."""

        analysis = RUNNER.analyze_rows(complete_rows(), self.normal_q0())
        with tempfile.TemporaryDirectory(dir=FTC_ROOT / "runs") as temporary:
            root = Path(temporary)
            RUNNER.write_csv(root / "attack_sweep.csv", RUNNER.ATTACK_FIELDS, [
                {"baseline_vdd_v": 0.90, "attack_vdd_v": 0.85, "margin_code": 1, "lock_code": 5,
                 "alarm_code": 6, "selected_tap": 37, "scan_phase": "coarse", "scenario": "test",
                 "W_S_int_ps": 1.0, "D_alarm_ps": 2.0, "Q": 1, "alarm": 1, "valid": True}
            ])
            RUNNER.write_csv(root / "trip_map.csv", RUNNER.TRIP_FIELDS, analysis["trip_rows"])
            RUNNER.write_json(root / "summary.json", {"decision": analysis["decision"]})
            RUNNER.write_json(root / "manifest.json", {"study": "test"})
            RUNNER.record_actual_scenario_count(root, 1)
            RUNNER.render_report(root / "report.md", analysis)
            with (root / "attack_sweep.csv").open(newline="", encoding="utf-8") as stream:
                self.assertEqual(tuple(csv.DictReader(stream).fieldnames or ()), RUNNER.ATTACK_FIELDS)
            self.assertEqual(json.loads((root / "summary.json").read_text(encoding="utf-8"))["decision"], "Programmable Acceptance Window = GO")
            self.assertEqual(json.loads((root / "manifest.json").read_text(encoding="utf-8"))["actual_scenario_count"], 1)
            self.assertIn("Required Answers", (root / "report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
