#!/usr/bin/env python3
"""Replay retained HSPICE raw-Q captures through the actual SV backend."""

import csv
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[3]
RTL_DIR = ROOT / "delay_chain" / "phase2_vernier" / "rtl"
TEST_DIR = ROOT / "delay_chain" / "phase2_vernier" / "tests"
SCRIPT_DIR = ROOT / "delay_chain" / "phase2_vernier" / "scripts"
RUN_CSV = (
    ROOT
    / "delay_chain"
    / "phase2_vernier"
    / "runs"
    / "direct_rail_sensor_timeline_20260725_r2"
    / "direct_rail_samples.csv"
)
sys.path.insert(0, str(SCRIPT_DIR))
import decode_vernier_code  # noqa: E402


CASE_RE = re.compile(
    r"^CASE (?P<case>\d+) raw=(?P<raw>[01]{32}) corrected=(?P<corrected>[01]{32}) "
    r"code=(?P<code>\d+) bubbles=(?P<bubbles>\d+) valid=(?P<valid>[01]) sample_valid=(?P<sample_valid>[01])$"
)


class SpiceRawQReplayTests(unittest.TestCase):
    """Require zero mismatch between retained SPICE captures and RTL outputs."""

    def test_direct_rail_raw_q_replay_has_zero_mismatch(self):
        """Run every retained raw-Q vector through VCS, then compare all fields."""

        vcs = shutil.which("vcs")
        if vcs is None:
            self.skipTest("VCS is not available in this environment")

        with RUN_CSV.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))

        self.assertEqual(len(rows), 500)

        with tempfile.TemporaryDirectory(prefix="vernier_stage2a_spice_replay_") as temp_dir:
            temp_path = Path(temp_dir)
            # Reverse each Python-order word for packed SV bit numbering.  The
            # resulting file is a temporary runner artifact, never a repo file.
            (temp_path / "raw_q.mem").write_text(
                "\n".join(row["raw_code"][::-1] for row in rows) + "\n", encoding="ascii"
            )
            simv = temp_path / "simv"
            compile_cmd = [
                vcs,
                "-full64",
                "-sverilog",
                "-timescale=1ns/1ps",
                f"-Mdir={temp_path / 'csrc'}",
                "-o",
                str(simv),
                "-top",
                "vernier_sensor_spice_raw_q_replay_tb",
                str(RTL_DIR / "vernier_sensor_digital_backend.sv"),
                str(TEST_DIR / "vernier_sensor_spice_raw_q_replay_tb.sv"),
            ]
            compile = subprocess.run(
                compile_cmd,
                # Keep VCS auxiliary logs and key files inside this test's
                # task-owned temporary directory together with raw_q.mem.
                cwd=temp_path,
                universal_newlines=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self.assertEqual(compile.returncode, 0, compile.stdout)
            run = subprocess.run(
                [str(simv)],
                cwd=temp_path,
                universal_newlines=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self.assertEqual(run.returncode, 0, run.stdout)
            self.assertIn("SPICE_RAW_Q_REPLAY_PASS", run.stdout)

        observed = {}
        for line in run.stdout.splitlines():
            match = CASE_RE.match(line.strip())
            if match:
                observed[int(match.group("case"))] = match.groupdict()
        self.assertEqual(sorted(observed), list(range(len(rows))))

        mismatch_count = 0
        for case_index, row in enumerate(rows):
            result = observed[case_index]
            expected = decode_vernier_code.decode_word(row["raw_code"])
            # VCS prints packed words MSB-first; restore the physical stage
            # order used by the HSPICE CSV before doing an exact comparison.
            rtl_raw = result["raw"][::-1]
            rtl_corrected = result["corrected"][::-1]
            mismatch = (
                rtl_raw != row["raw_code"]
                or rtl_corrected != expected["corrected_code"]
                or int(result["code"]) != expected["sensor_code"]
                or int(result["bubbles"]) != expected["bubble_count"]
                or (result["valid"] == "1") != expected["code_valid"]
                or result["sample_valid"] != "1"
            )
            if mismatch:
                mismatch_count += 1
        self.assertEqual(mismatch_count, 0)


if __name__ == "__main__":
    unittest.main()
