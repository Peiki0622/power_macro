"""Static regressions for the bounded two-stage real-DFF calibration study.

These tests exercise only deterministic contracts, rendered text, and synthetic
post-HSPICE rows.  They must never launch HSPICE: transistor-level acceptance
remains exclusively the new task-owned scenario schedule in the runner.
"""

import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_two_stage_real_dff_hierarchical_calibration as study  # noqa: E402


def synthetic_row(phase, vdd_v, medium_code, fine_code, delay_ps, q_value, valid=1, reason=None):
    """Build a complete scalar result row without modeling any standard cell.

    The fixture deliberately tests the decision logic only.  Its timestamps
    preserve positive XOR width and the fixed 200 ps Q-settle rule so a failed
    test points at scheduling/classification code rather than a made-up circuit
    waveform.
    """

    xor_rise = 1.5e-9
    return {
        "phase": phase,
        "vdd_v": vdd_v,
        "medium_code": medium_code,
        "fine_code": fine_code,
        "K": study.FINE_K,
        "scenario": "synthetic/{}-{}-{}".format(phase, medium_code, fine_code),
        "t_xor_rise_s": xor_rise,
        "t_xor_fall_s": xor_rise + 400.0e-12,
        "t_ck_rise_s": xor_rise + delay_ps * 1.0e-12,
        "q_final_v": vdd_v if q_value else 0.0,
        "q_final": q_value if valid else None,
        "D_code_ps": delay_ps,
        "W_xor_ps": 400.0,
        "valid": valid,
        "reason": reason,
    }


class TwoStageRealDffHierarchicalCalibrationTests(unittest.TestCase):
    """Protect the new integration boundary without performing electrical work."""

    @classmethod
    def setUpClass(cls):
        """Read existing evidence once; this neither writes it nor invokes HSPICE."""

        cls.context = study.frozen_context()

    def test_frozen_upstream_cells_and_constraints(self):
        """The study has exactly one approved medium/fine/sensor/DFF contract."""

        requirements = study.requirements_document(self.context)
        self.assertEqual(requirements["upstream_fine_waveform_decision"], "GO")
        self.assertEqual((requirements["fine_driver"], requirements["fine_load"], requirements["initial_K"]), ("BUF_X0P8M_A9TL40", "NOR2_X4A_A9TL40__signal_A", 10))
        self.assertEqual((requirements["medium_N"], requirements["medium_delay_cell"], requirements["medium_mux_cell"]), (16, "BUF_X0P7M_A9TL40", "MXT2_X0P5M_A9TL40"))
        self.assertEqual((requirements["sensor_tap"], requirements["xor_cell"], requirements["dff_cell"]), (29, "XOR2_X0P5M_A9TR40", "DFFRPQ_X0P5M_A9TR40"))
        self.assertTrue(all(value == 0 for key, value in requirements.items() if key == "historical_hspice_rerun"))

    def test_rendered_deck_has_exact_signal_flow_and_no_forbidden_hardware(self):
        """Inspect real CDL instance text rather than trusting helper names alone."""

        deck = study.render_deck(self.context, 0.95, 7, 3)
        contract = study.integration_contract(self.context)
        self.assertEqual(contract["decision"], "GO")
        self.assertTrue(all(contract["checks"].values()))
        self.assertIn("XMED_BUF_00 x1 vdd_a vdd_a vss_a vss_a xor_29 BUF_X0P7M_A9TL40", deck)
        self.assertIn("XFINE_DRIVER dff_ck vdd_a vdd_a vss_a vss_a medium_out BUF_X0P8M_A9TL40", deck)
        self.assertIn("XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset DFFRPQ_X0P5M_A9TR40", deck)
        self.assertEqual(sum(line.startswith("XLOAD_") for line in deck.splitlines()), 10)
        for forbidden in ("XMUX_L1", "XMUX_L2", "XMUX_L3", "XBYPASS", "XCONFIG_SKIP"):
            self.assertNotIn(forbidden, deck)

    def test_q_read_contract_covers_all_historical_projections(self):
        """The new read time must cover the slowest CK and precede next launch."""

        contract = study.projected_q_read_contract(self.context)
        self.assertEqual(contract["q_read_time_s"], 3.3e-9)
        self.assertEqual(set(contract["projections_by_vdd"]), {"1.10", "0.95", "0.80"})
        self.assertTrue(all(contract["q_read_time_s"] >= item["minimum_safe_q_read_s"] for item in contract["projections_by_vdd"].values()))
        self.assertLess(contract["q_read_time_s"], contract["next_sensor_xor_event_s"])

    def test_coarse_and_fine_gate_require_one_ordered_one_to_zero_boundary(self):
        """Delay monotonicity and Q monotonicity remain separate physical gates."""

        coarse = [synthetic_row("coarse", 0.95, code, 0, 100.0 + code, 1 if code < 5 else 0) for code in range(17)]
        fine = [synthetic_row("fine", 0.95, 4, code, 100.0 + code, 1 if code < 6 else 0) for code in range(11)]
        self.assertEqual(study.evaluate_scan(coarse, "coarse"), {"status": "GO", "transition": 5, "q_sequence": [1, 1, 1, 1, 1] + [0] * 12, "delays_ps": [100.0 + code for code in range(17)]})
        self.assertEqual(study.evaluate_scan(fine, "fine")["transition"], 6)
        self.assertEqual(study.evaluate_scan(coarse[:-1], "coarse")["reason"], "hspice_execution_failure")
        nonmonotonic = list(fine)
        nonmonotonic[5] = dict(nonmonotonic[5], D_code_ps=90.0)
        self.assertEqual(study.evaluate_scan(nonmonotonic, "fine")["reason"], "fine_delay_non_monotonic")
        bad_q = [synthetic_row("coarse", 0.95, code, 0, 100.0 + code, (1, 0, 1)[code % 3]) for code in range(17)]
        self.assertEqual(study.evaluate_scan(bad_q, "coarse")["reason"], "coarse_q_non_monotonic")

    def test_raw_hspice_measure_names_map_to_task_owned_time_columns(self):
        """The MEAS labels remain physical deck labels, not CSV field aliases."""

        record = {
            "scenario": "/tmp/runs/r1/scenarios/example",
            "t_xor_rise": 1.5e-9,
            "t_xor_fall": 1.9e-9,
            "t_ck_rise": 1.7e-9,
            "q_final_v": 0.95,
        }
        row = study.row_from_record("coarse", 0.95, 0, 0, record, Path("/tmp/runs"))
        self.assertEqual(row["valid"], 1)
        self.assertAlmostEqual(row["W_xor_ps"], 400.0)
        self.assertAlmostEqual(row["D_code_ps"], 200.0)
        self.assertEqual(row["q_final"], 1)

    def test_voltage_scheduler_runs_only_m_transition_minus_one_for_fine(self):
        """A successful coarse pass permits exactly one 11-point fine scan."""

        calls = []

        def fake_run_one(_context, _hspice, _version, _root, run_dir, phase, vdd_v, medium_code, fine_code, _signature, _stats):
            calls.append((phase, medium_code, fine_code))
            code = medium_code if phase == "coarse" else fine_code
            q_value = 1 if code < (3 if phase == "coarse" else 4) else 0
            return synthetic_row(phase, vdd_v, medium_code, fine_code, 100.0 + code, q_value), run_dir

        with mock.patch.object(study, "run_one", side_effect=fake_run_one):
            result, coarse, fine, _ = study.run_voltage(self.context, Path("hspice"), "test", Path("/tmp"), None, 0.95, {}, {"new": 0, "reused": 0})
        self.assertEqual(result["status"], "GO")
        self.assertEqual((result["M_transition"], result["M_fine"], result["F_lock"]), (3, 2, 4))
        self.assertEqual(len(coarse), 17)
        self.assertEqual(len(fine), 11)
        self.assertEqual(calls[:17], [("coarse", code, 0) for code in range(17)])
        self.assertEqual(calls[17:], [("fine", 2, code) for code in range(11)])

    def test_invalid_coarse_row_stops_before_fine(self):
        """A capture/readout failure is terminal for that voltage and task order."""

        calls = []

        def fake_run_one(_context, _hspice, _version, _root, run_dir, phase, vdd_v, medium_code, fine_code, _signature, _stats):
            calls.append((phase, medium_code, fine_code))
            return synthetic_row(phase, vdd_v, medium_code, fine_code, 100.0, 1, valid=0, reason="q_settle_window_insufficient"), run_dir

        with mock.patch.object(study, "run_one", side_effect=fake_run_one):
            result, coarse, fine, _ = study.run_voltage(self.context, Path("hspice"), "test", Path("/tmp"), None, 0.95, {}, {"new": 0, "reused": 0})
        self.assertEqual(result["reason"], "q_settle_window_insufficient")
        self.assertEqual(len(coarse), 1)
        self.assertEqual(fine, [])
        self.assertEqual(calls, [("coarse", 0, 0)])

    def test_budget_summary_and_static_mode_never_launch_hspice(self):
        """Static publication validates contracts but cannot become a smoke run."""

        self.assertEqual(len(study.ANCHOR_VDD) * ((study.MEDIUM_N + 1) + (study.FINE_K + 1)), study.TOTAL_SCENARIO_LIMIT)
        with tempfile.TemporaryDirectory(prefix="ftc_two_stage_static_") as temporary:
            root = Path(temporary)
            manifest = root / "runs" / "r1" / "scenarios" / "retained" / "scenario_manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}\n", encoding="utf-8")
            summary = study.summary_document("NOT_RUN", [], [], {"new": 0, "reused": 0}, root / "runs")
            self.assertEqual(summary["new_hspice_scenarios"], 1)
            self.assertTrue(all(value == 0 for key, value in summary.items() if key.startswith("historical_")))
            with mock.patch.object(study.subprocess, "run", side_effect=AssertionError("HSPICE must not run in phase0")):
                self.assertEqual(study.main(["--phase0-only", "--analysis-dir", str(root / "analysis"), "--run-root", str(root / "static-runs"), "--report-output", str(root / "report.md")]), 0)
            self.assertTrue((root / "analysis" / "requirements.json").is_file())
            self.assertTrue((root / "analysis" / "integration_contract.json").is_file())
            self.assertTrue((root / "analysis" / "q_read_contract.json").is_file())

    def test_runner_cannot_dispatch_historical_experiment_mains(self):
        """Only the shared MEAS/listing parser is imported from older work."""

        source = inspect.getsource(study)
        for old_runner in (
            "run_fine_stage_validation_contract_audit",
            "run_path_selection_medium_stage",
            "run_minimal_pulse_comparator",
            "run_real_xor_pulse_width",
            "run_static_self_calibration",
        ):
            self.assertNotIn("import " + old_runner, source)
            self.assertNotIn("subprocess.run([" + old_runner, source)
        self.assertIn("import run_dc_sweep", source)


if __name__ == "__main__":
    unittest.main()
