#!/usr/bin/env python3
"""Minimum Phase-3 contract and SPICE-to-RTL replay regression.

This is deliberately a small unittest module rather than a general simulation
framework.  It checks the exact artifacts required by Steps 1, 7, 8, 10, and
11, then uses VCS in task-owned temporary directories for hierarchy elaboration
and decoder replay.  No generated compiler database is left in the tests or
RTL directories.
"""

import csv
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[3]
PHASE3 = ROOT / "delay_chain/phase3"
RTL = PHASE3 / "rtl"
TESTS = PHASE3 / "tests"
RUNS = PHASE3 / "runs"
SCRIPT_DIR = PHASE3 / "scripts"
PHASE2_SCRIPT_DIR = ROOT / "delay_chain/phase2_vernier/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(PHASE2_SCRIPT_DIR))
import decode_vernier_code  # noqa: E402  # Python reference for bit-exact replay.
import run_voltage_sweep  # noqa: E402  # Exact point-grid and raw CSV contract.
import run_launch_calibration  # noqa: E402  # Endpoint-safe CAL selection policy.


CASE_RE = re.compile(
    r"^CASE (?P<case>\d+) raw=(?P<raw>[01]{32}) normalized=(?P<normalized>[01]{32}) "
    r"corrected=(?P<corrected>[01]{32}) code=(?P<code>\d+) bubbles=(?P<bubbles>\d+) "
    r"valid=(?P<valid>[01]) sample_valid=(?P<sample_valid>[01])$"
)


def read_config():
    """Load the one authoritative Phase-3 configuration object."""

    return json.loads((PHASE3 / "phase3_config.json").read_text(encoding="utf-8"))


def physical_raw_vectors(config):
    """Return raw physical words from both exact HSPICE voltage sweeps.

    The selected RVT/LVT run is the source of retained SPICE vectors.  A
    separate pair of all-zero/all-one legal words is appended to exercise both
    decoder endpoints even if the physical sweep does not reach them.
    """

    path = RUNS / "voltage_sweep/voltage_code.csv"
    with path.open(newline="", encoding="utf-8") as stream:
        words = [row["raw_thermometer_word"] for row in csv.DictReader(stream)]
    if len(words) != 123:
        raise AssertionError("expected 123 retained physical raw words")
    # These are raw words, not normalized words, because the selected physical
    # polarity is inverted by the RTL package before majority correction.
    words.extend(["0" * 32, "1" * 32])
    return words


class Phase3ContractTests(unittest.TestCase):
    """Protect the small set of Phase-3 implementation obligations."""

    def test_discovery_and_config(self):
        """Require a real LVT source and a complete selected-cell contract."""

        config = read_config()
        candidates = json.loads((PHASE3 / "discovery/lvt_inverter_candidates.json").read_text(encoding="utf-8"))
        selected = json.loads((PHASE3 / "discovery/selected_cells.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(candidates), 1)
        self.assertTrue(Path(selected["source_files"]["lvt_cdl"]).is_file())
        self.assertTrue(Path(selected["source_files"]["lvt_verilog"]).is_file())
        self.assertEqual(config["selected_lvt_cell"], "INV_X0P5M_A9TL40")
        self.assertEqual(config["selected_dummy_load_count"], 1)
        self.assertEqual(config["selected_cal_sel"], 1)
        self.assertEqual(config["baseline_code"], 18)

    def test_final_deck_has_selected_rvt_lvt_and_no_reference_rail(self):
        """Check the final physical deck rather than only its renderer source."""

        deck = PHASE3 / "runs/voltage_sweep/scenarios/v1p100000000000/phase3_voltage_code.sp"
        text = deck.read_text(encoding="ascii")
        self.assertIn("INV_X0P5M_A9TR40", text)
        self.assertIn("INV_X0P5M_A9TL40", text)
        self.assertIn("D=LVT tap, CK=RVT tap", text)
        self.assertIn("CAL_RVT_MUX_L2_0", text)
        self.assertNotIn("VDD_REF", text)
        self.assertNotIn("VSS_REF", text)
        # The known renderer regression would leave a bare final node line.
        self.assertIsNone(re.search(r"^CAL_(?:RVT|LVT)_MUX_L2_0$", text, re.MULTILINE))

    def test_calibration_nominal_is_center_region(self):
        """Require the selected physical tap to reproduce baseline code 18."""

        with (RUNS / "launch_calibration/calibration.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        selected = [row for row in rows if int(row["cal_sel"]) == 1]
        self.assertEqual(len(selected), 1)
        self.assertEqual(int(selected[0]["sensor_code"]), 18)
        self.assertEqual(int(selected[0]["code_valid"]), 1)
        self.assertEqual(int(selected[0]["reset_failure_count"]), 0)

    def test_calibration_rejects_valid_endpoint_only_rows(self):
        """A legal DFF word outside 3..6 is diagnostic evidence, never CAL PASS."""

        rows = [
            {"cal_sel": index, "sensor_code": 0 if index == 0 else 32,
             "code_valid": 1, "reset_failure_count": 0}
            for index in range(8)
        ]
        decision = run_launch_calibration.select_nominal_calibration(rows, 3, 6, 4)
        self.assertEqual(decision["status"], "FAIL")
        self.assertEqual(decision["reason"], "no_nominal_center_setting")
        self.assertNotIn("selected", decision)
        self.assertEqual(decision["nearest_valid_diagnostic"]["cal_sel"], 0)

    def test_wide_range_validation_rejects_constant_endpoint_curve(self):
        """All-zero physical words must fail even when timing and reset checks pass."""

        points = [{"vdd_v": 1.1}, {"vdd_v": 1.0}, {"vdd_v": 0.7}]
        rows = [
            {
                "vdd_v": point["vdd_v"], "droop_mv": (1.1 - point["vdd_v"]) * 1000.0,
                "sensor_code": 0, "residual_code": 0, "code_valid": 1,
                "reset_failure_count": 0, "final_taps_arrived": 1,
                "rvt_031_cross_s": 2.0e-9, "lvt_031_cross_s": 2.1e-9,
            }
            for point in points
        ]
        summary = run_voltage_sweep.validate_wide_rows(rows, points, 0, 3, 6)
        self.assertEqual(summary["status"], "FAIL")
        self.assertFalse(summary["gates"]["nominal_not_endpoint"])
        self.assertFalse(summary["gates"]["nominal_in_requested_window"])
        self.assertFalse(summary["gates"]["nonzero_code_span"])

    def test_wide_range_sparse_selection_and_final_evidence(self):
        """Require the frozen sparse mask and complete real-DFF range result."""

        config = read_config()
        selected = config["wide_range"]["selected"]
        self.assertEqual(selected["topology"], "sparse_lvt_rvt")
        self.assertEqual(selected["active_stage_count"], 11)
        self.assertEqual(selected["active_stage_indices"], [0, 2, 5, 8, 11, 14, 17, 20, 23, 26, 29])
        self.assertEqual(selected["active_stage_mask"], "0x24924925")
        self.assertEqual(selected["cal_sel"], 0)
        self.assertEqual(selected["baseline_code"], 4)
        self.assertEqual(selected["launch_balance_load_count"], 0)
        self.assertEqual(selected["rvt_launch_load_count"], 6)
        summary = json.loads((RUNS / "wide_range_gain_11_screen/voltage_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["scenario_count"], 7)
        self.assertTrue(all(summary["gates"].values()))
        frontend = (RTL / "phase3_frontend_struct.sv").read_text(encoding="ascii")
        companion = (RTL / "phase3_companion_stage_struct.sv").read_text(encoding="ascii")
        self.assertEqual(frontend.count("phase3_comparator_struct u_comparator"), 1)
        self.assertIn("WIDE_RANGE_ACTIVE_STAGE_MASK[stage_index]", frontend)
        self.assertIn("INV_X0P5M_A9TL40 u_first_lvt", companion)
        self.assertIn("INV_X0P5M_A9TR40 u_second_rvt", companion)
        self.assertNotIn("dummy", companion.lower())

    def test_wide_range_rtl_matches_repaired_physical_selection(self):
        """Keep static configuration, RTL mask/CAL, and CK load repair aligned."""

        config = read_config()["wide_range"]["selected"]
        package = (RTL / "phase3_calibration_pkg.sv").read_text(encoding="ascii")
        top = (RTL / "phase3_sensor.sv").read_text(encoding="ascii")
        launch = (RTL / "phase3_launch_cal_struct.sv").read_text(encoding="ascii")
        self.assertIn("32'h2492_4925", package)
        self.assertIn("WIDE_RANGE_DEFAULT_CAL_SEL = 3'd{}".format(config["cal_sel"]), package)
        self.assertIn("WIDE_RANGE_BASELINE_CODE = 6'd{}".format(config["baseline_code"]), package)
        self.assertIn("WIDE_RANGE_RVT_LAUNCH_LOAD_COUNT = 6", package)
        self.assertIn(".cal_sel_i(WIDE_RANGE_DEFAULT_CAL_SEL)", top)
        self.assertNotIn("u_lvt_balance_load", launch)
        self.assertIn("g_rvt_launch_load", launch)

    def test_rtl_source_has_no_forbidden_construct_or_reference_port(self):
        """Guard every synthesizable Phase-3 SV file against forbidden RTL."""

        for path in RTL.glob("*.sv"):
            text = path.read_text(encoding="ascii")
            self.assertNotRegex(text, r"(?m)^\s*function\b")
            self.assertNotRegex(text, r"(?m)^\s*#\s*[0-9]")
        top = (RTL / "phase3_sensor.sv").read_text(encoding="ascii")
        self.assertNotIn("vdd_ref_i", top)
        self.assertNotIn("vss_ref_i", top)

    def test_rtl_elaborates_with_power_aware_task_stubs(self):
        """Elaborate the complete hierarchy with the documented cell ports."""

        vcs = shutil.which("vcs") or "/home/synopsys/vcs/W-2024.09/bin/vcs"
        if not Path(vcs).is_file() and shutil.which("vcs") is None:
            self.skipTest("VCS is not available")
        with tempfile.TemporaryDirectory(prefix="phase3_elab_", dir=str(RUNS / "rtl_elaboration")) as temp_dir:
            temp = Path(temp_dir)
            command = [
                vcs, "-full64", "-sverilog", "-timescale=1ns/1ps",
                "-Mdir={}".format(temp / "csrc"), "-o", str(temp / "simv"),
                "-top", "phase3_sensor",
            ]
            command.extend(str(path) for path in sorted(RTL.glob("*.sv")))
            command.append(str(RUNS / "rtl_elaboration/standard_cell_elab_stubs.sv"))
            result = subprocess.run(command, cwd=str(temp), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertTrue((temp / "simv").is_file())

    def test_spice_raw_code_replay_is_bit_exact(self):
        """Replay every retained physical raw word through the SV decoder."""

        vcs = shutil.which("vcs") or "/home/synopsys/vcs/W-2024.09/bin/vcs"
        if not Path(vcs).is_file() and shutil.which("vcs") is None:
            self.skipTest("VCS is not available")
        config = read_config()
        words = physical_raw_vectors(config)
        with tempfile.TemporaryDirectory(prefix="phase3_replay_", dir=str(RUNS / "rtl_elaboration")) as temp_dir:
            temp = Path(temp_dir)
            # Packed SV bit 31 prints first, while HSPICE CSV strings are in
            # physical stage order bit 0 first; reverse on file creation.
            (temp / "raw_q.mem").write_text("\n".join(word[::-1] for word in words) + "\n", encoding="ascii")
            command = [
                vcs, "-full64", "-sverilog", "-timescale=1ns/1ps",
                "+define+PHASE3_VECTOR_COUNT={}".format(len(words)),
                "-Mdir={}".format(temp / "csrc"), "-o", str(temp / "simv"),
                "-top", "phase3_decoder_replay_tb",
                str(RTL / "phase3_calibration_pkg.sv"), str(RTL / "phase3_decoder.sv"),
                str(TESTS / "phase3_decoder_replay_tb.sv"),
            ]
            compile_result = subprocess.run(command, cwd=str(temp), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            self.assertEqual(compile_result.returncode, 0, compile_result.stdout)
            run_result = subprocess.run([str(temp / "simv")], cwd=str(temp), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            self.assertEqual(run_result.returncode, 0, run_result.stdout)
            observed = {}
            for line in run_result.stdout.splitlines():
                match = CASE_RE.match(line.strip())
                if match:
                    observed[int(match.group("case"))] = match.groupdict()
            self.assertEqual(sorted(observed), list(range(len(words))), run_result.stdout)
            for index, raw_word in enumerate(words):
                normalized = raw_word
                if config["thermometer_invert"]:
                    normalized = "".join("1" if bit == "0" else "0" for bit in raw_word)
                expected = decode_vernier_code.decode_word(normalized)
                result = observed[index]
                # VCS prints packed vectors MSB-first, so restore stage order.
                self.assertEqual(result["raw"][::-1], raw_word, "raw case {}".format(index))
                self.assertEqual(result["normalized"][::-1], expected["raw_code"], "normalized case {}".format(index))
                self.assertEqual(result["corrected"][::-1], expected["corrected_code"], "corrected case {}".format(index))
                self.assertEqual(int(result["code"]), expected["sensor_code"], "code case {}".format(index))
                self.assertEqual(int(result["bubbles"]), expected["bubble_count"], "bubble case {}".format(index))
                self.assertEqual(result["valid"] == "1", expected["code_valid"], "valid case {}".format(index))
                self.assertEqual(result["sample_valid"], "1", "sample pulse case {}".format(index))
            self.assertIn("PHASE3_DECODER_REPLAY_PASS", run_result.stdout)


if __name__ == "__main__":
    unittest.main()
