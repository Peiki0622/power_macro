"""Static regressions for the bounded dynamic FTC protocol.

These tests exercise immutable evidence, schedule construction, deck text, and
synthetic MEAS records only.  They never launch HSPICE or modify upstream runs.
"""

import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_dynamic_startup_calibration_protocol as study  # noqa: E402


class DynamicStartupCalibrationProtocolTests(unittest.TestCase):
    """Protect the protocol boundary without making an electrical claim."""

    @classmethod
    def setUpClass(cls):
        """Read immutable evidence once and derive the deterministic contracts."""

        cls.context = study.frozen_context()
        cls.golden = study.golden_reference(cls.context)
        cls.timing = study.timing_contract(cls.context)

    def schedule(self, voltage):
        """Create the exact per-voltage schedule used by deck and parser tests."""

        trajectory = study.build_trajectory(voltage, self.golden["voltages"][study.vkey(voltage)])
        return study.schedule_trajectory(trajectory, self.timing)

    def synthetic_record(self, schedule, vdd, q_value=1):
        """Build a complete clean record; callers choose Q to test early stop."""

        record = {}
        for probe in schedule["probes"]:
            index = probe["probe_index"]
            prefix = "p{}".format(index)
            xor_rise = probe["launch_time_s"] + 5.0e-10
            record.update({
                prefix + "_t_xor_rise": xor_rise,
                prefix + "_t_xor_fall": xor_rise + 4.0e-10,
                prefix + "_t_xor_rise_2": probe["sclk_fall_s"] + 5.0e-10,
                prefix + "_t_ck_rise": xor_rise + 2.0e-10,
                prefix + "_t_ck_rise_2": probe["sclk_fall_s"] + 7.0e-10,
                prefix + "_q_read_v": vdd if q_value else 0.0,
                prefix + "_xor_peak": vdd,
                prefix + "_ck_peak": vdd,
                prefix + "_recovery_xor_end": 0.0,
                prefix + "_recovery_medium_end": 0.0,
                prefix + "_recovery_ck_end": 0.0,
                prefix + "_recovery_xor_tail": 0.0,
                prefix + "_recovery_medium_tail": 0.0,
                prefix + "_recovery_ck_tail": 0.0,
            })
        for transition in schedule["transitions"]:
            prefix = "tr{}".format(transition["transition_index"])
            record.update({
                prefix + "_xor_max": 0.0,
                prefix + "_medium_max": 0.0,
                prefix + "_ck_max": 0.0,
                prefix + "_ck_rise_1": transition["next_launch_s"],
                prefix + "_ck_rise_2": transition["next_launch_s"] + 1.0e-9,
            })
        return record

    def test_upstream_go_locks_and_prefixes_are_frozen(self):
        """The dynamic task is blocked unless all upstream static evidence agrees."""

        self.assertEqual(self.context["summary"]["new_hspice_scenarios"], 84)
        self.assertEqual(self.context["summary"]["decision"], "Two-Stage Real-DFF Hierarchical Self-Calibration = GO")
        expected = {"0.95": (6, 5, 1, "1111110", "10"), "1.10": (4, 3, 4, "11110", "11110"), "0.80": (9, 8, 1, "1111111110", "10")}
        for key, values in expected.items():
            reference = self.golden["voltages"][key]
            self.assertEqual((reference["M_transition"], reference["M_fine"], reference["F_lock"]), values[:3])
            self.assertEqual("".join(reference["coarse_prefix_q"]), values[3])
            self.assertEqual("".join(reference["fine_prefix_q"]), values[4])
        self.assertTrue(all(value == 0 for name, value in study.requirements_document(self.context).items() if name.endswith("_rerun")))

    def test_timing_and_trajectories_are_bounded(self):
        """Guards come from retained data and no voltage expands to a full sweep."""

        self.assertEqual(self.timing["q_read_offset_s"], 2.3e-9)
        self.assertEqual(self.timing["q_settle_s"], 2.0e-10)
        self.assertGreaterEqual(self.timing["code_settle_guard_s"], 1.5e-9)
        self.assertGreaterEqual(self.timing["recovery_guard_s"], 2.3e-9)
        self.assertEqual(self.timing["reset_fully_low_to_launch_s"], 4.9e-10)
        for voltage, count in ((0.95, 10), (1.10, 11), (0.80, 13)):
            schedule = self.schedule(voltage)
            self.assertEqual(len(schedule["probes"]), count)
            for transition in schedule["transitions"]:
                medium_changes = sum(a != b for a, b in zip(study.thermometer(study.MEDIUM_N, transition["old_M"]), study.thermometer(study.MEDIUM_N, transition["new_M"])))
                fine_changes = sum(a != b for a, b in zip(study.thermometer(study.FINE_K, transition["old_F"]), study.thermometer(study.FINE_K, transition["new_F"])))
                self.assertEqual(medium_changes + fine_changes, 1)
            self.assertTrue(all(probe["update_end_s"] <= probe["launch_time_s"] for probe in schedule["probes"]))

    def test_dynamic_deck_preserves_topology_and_uses_pwl_controls(self):
        """Deck text exposes the one permitted change without running HSPICE."""

        schedule = self.schedule(0.95)
        deck = study.render_deck(self.context, self.timing, schedule, 0.95)
        contract = study.integration_contract(self.context, self.timing, schedule, deck)
        self.assertEqual(contract["decision"], "GO")
        self.assertTrue(all(contract["checks"].values()))
        self.assertIn("XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset DFFRPQ_X0P5M_A9TR40", deck)
        self.assertIn("XMED_BUF_00 x1 vdd_a vdd_a vss_a vss_a xor_29 BUF_X0P7M_A9TL40", deck)
        self.assertIn("XFINE_DRIVER dff_ck vdd_a vdd_a vss_a vss_a medium_out BUF_X0P8M_A9TL40", deck)
        self.assertEqual(sum(line.startswith("V_M_") and "PWL(" in line for line in deck.splitlines()), 16)
        self.assertEqual(sum(line.startswith("V_F_") and "PWL(" in line for line in deck.splitlines()), 10)
        for forbidden in ("XBYPASS", "XCONFIG_SKIP", "XMUX_L1", "FSM"):
            self.assertNotIn(forbidden, deck)

    def test_phase0_only_never_calls_hspice(self):
        """Phase 0 writes contracts to a caller-owned temporary output only."""

        with tempfile.TemporaryDirectory(prefix="ftc_dynamic_phase0_") as temporary:
            root = Path(temporary)
            with mock.patch.object(study.subprocess, "run", side_effect=AssertionError("phase0 must not launch HSPICE")):
                result = study.main(["--phase0-only", "--analysis-dir", str(root / "analysis"), "--run-root", str(root / "runs"), "--report-output", str(root / "report.md")])
            self.assertEqual(result, 0)
            for name in ("requirements.json", "golden_reference.json", "timing_contract.json", "trajectory_contract.json", "integration_contract.json", "summary.json"):
                self.assertTrue((root / "analysis" / name).is_file())

    def test_first_voltage_failure_stops_scheduler(self):
        """A 0.95 V Q mismatch must prevent 1.10 V and 0.80 V execution."""

        schedule = self.schedule(0.95)
        record = self.synthetic_record(schedule, 0.95, q_value=1)
        with tempfile.TemporaryDirectory(prefix="ftc_dynamic_stop_") as temporary:
            root = Path(temporary)
            with mock.patch.object(study, "validate_hspice", return_value=(Path("hspice"), "W-2024.09")), mock.patch.object(study, "execute_scenario", return_value=record) as execute:
                result = study.main(["--analysis-dir", str(root / "analysis"), "--run-root", str(root / "runs"), "--report-output", str(root / "report.md")])
            self.assertEqual(result, 2)
            self.assertEqual(execute.call_count, 1)
            summary = json.loads((root / "analysis" / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["per_voltage"][0]["vdd_v"], 0.95)
            self.assertIn("dynamic_coarse_q_mismatch", summary["reasons"])

    def test_runner_does_not_import_or_dispatch_upstream_campaign(self):
        """Only the shared phase-1 parser is allowed to cross task boundaries."""

        source = inspect.getsource(study)
        self.assertNotIn("import run_two_stage_real_dff_hierarchical_calibration", source)
        self.assertNotIn("from run_two_stage_real_dff_hierarchical_calibration", source)
        self.assertIn("import run_dc_sweep", source)


if __name__ == "__main__":
    unittest.main()
