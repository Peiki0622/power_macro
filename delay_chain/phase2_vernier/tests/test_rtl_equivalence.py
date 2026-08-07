#!/usr/bin/env python3
"""VCS-backed equivalence checks for the Stage 2A digital backend."""

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RTL_DIR = ROOT / "delay_chain" / "phase2_vernier" / "rtl"
TEST_DIR = ROOT / "delay_chain" / "phase2_vernier" / "tests"
SCRIPT_DIR = ROOT / "delay_chain" / "phase2_vernier" / "scripts"

import sys

sys.path.insert(0, str(SCRIPT_DIR))
import decode_vernier_code  # noqa: E402


CASE_RE = re.compile(
    r"^CASE (?P<case>\d+) raw=(?P<raw>[01]+) corrected=(?P<corrected>[01]+) "
    r"code=(?P<code>\d+) bubbles=(?P<bubbles>\d+) valid=(?P<valid>[01]) "
    r"sample_valid=(?P<sample_valid>[01])$"
)
IDLE_RE = re.compile(r"^IDLE (?P<case>\d+) sample_valid=(?P<sample_valid>[01])$")


class RtlEquivalenceTests(unittest.TestCase):
    """Compare every backend field with the Python 0*1* reference decoder."""

    def test_backend_source_keeps_synthesizable_contract(self):
        """The adapted backend has the target ports and no forbidden constructs."""

        source = (RTL_DIR / "vernier_sensor_digital_backend.sv").read_text(encoding="utf-8")
        self.assertIn("input  logic                  clk", source)
        self.assertIn("input  logic                  capture_enable", source)
        self.assertIn("output logic                  sample_valid", source)
        self.assertNotIn("sample_done", source)
        self.assertNotIn("function ", source)
        self.assertNotIn("#delay", source)

    def test_vcs_backend_matches_python_decoder(self):
        """Run the real SystemVerilog backend over all required vector classes."""

        vcs = shutil.which("vcs")
        if vcs is None:
            self.skipTest("VCS is not available in this environment")

        with tempfile.TemporaryDirectory(prefix="vernier_stage2a_rtl_") as temp_dir:
            temp_path = Path(temp_dir)
            compile_cmd = [
                vcs,
                "-full64",
                "-sverilog",
                "-timescale=1ns/1ps",
                f"-Mdir={temp_path / 'csrc'}",
                "-o",
                str(temp_path / "simv"),
                "-top",
                "vernier_sensor_digital_backend_tb",
                str(RTL_DIR / "vernier_sensor_digital_backend.sv"),
                str(TEST_DIR / "vernier_sensor_digital_backend_tb.sv"),
            ]
            compile = subprocess.run(
                compile_cmd,
                # VCS writes auxiliary keys and logs into its working
                # directory even when -Mdir is supplied.  Keep those runner
                # products beside the temporary executable, never at repo root.
                cwd=temp_path,
                universal_newlines=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self.assertEqual(compile.returncode, 0, compile.stdout)

            run = subprocess.run(
                [str(temp_path / "simv")],
                cwd=temp_path,
                universal_newlines=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self.assertEqual(run.returncode, 0, run.stdout)

        case_rows = {}
        idle_rows = {}
        for line in run.stdout.splitlines():
            match = CASE_RE.match(line.strip())
            if match:
                case_rows[int(match.group("case"))] = match.groupdict()
                continue
            match = IDLE_RE.match(line.strip())
            if match:
                idle_rows[int(match.group("case"))] = match.groupdict()

        words = [
            "00000000",  # all-zero endpoint
            "11111111",  # all-one endpoint
            "00011111",  # ideal thermometer word
            "00110111",  # single bubble repaired by majority filtering
            "00110101",  # multiple bubbles, still invalid
            "01010111",  # strongly invalid word
        ]
        self.assertEqual(sorted(case_rows), list(range(len(words))))
        self.assertEqual(sorted(idle_rows), list(range(len(words))))

        for case_id, word in enumerate(words):
            expected = decode_vernier_code.decode_word(word)
            observed = case_rows[case_id]

            # The SV testbench prints the packed vector MSB-first.  The Python
            # reference defines bit zero as the leftmost/earliest stage, so
            # widen, reverse, and compare in the declared physical order.
            observed_raw = format(int(observed["raw"], 2), "08b")[::-1]
            observed_corrected = format(int(observed["corrected"], 2), "08b")[::-1]

            self.assertEqual(observed_raw, expected["raw_code"], f"raw case {case_id}")
            self.assertEqual(observed_corrected, expected["corrected_code"], f"corrected case {case_id}")
            self.assertEqual(int(observed["code"]), expected["sensor_code"], f"code case {case_id}")
            self.assertEqual(int(observed["bubbles"]), expected["bubble_count"], f"bubble case {case_id}")
            self.assertEqual(observed["valid"] == "1", expected["code_valid"], f"valid case {case_id}")
            self.assertEqual(observed["sample_valid"], "1", f"sample pulse case {case_id}")
            self.assertEqual(idle_rows[case_id]["sample_valid"], "0", f"idle pulse case {case_id}")

        self.assertIn("BACKEND_TEST_PASS", run.stdout)


if __name__ == "__main__":
    unittest.main()
