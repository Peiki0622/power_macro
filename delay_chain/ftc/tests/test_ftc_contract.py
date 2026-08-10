"""FTC-only compact-evidence and structural-contract regression."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
VCS = Path("/home/synopsys/vcs/W-2024.09/bin/vcs")
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import ftc_analysis  # noqa: E402


class FtcContractTest(unittest.TestCase):
    """Consume committed evidence only; never invoke HSPICE from a test."""

    def test_selected_range_and_static_transfer(self) -> None:
        """Check the selected 0.75--1.10 V contract and software replay data."""

        config = json.loads((FTC_ROOT / "ftc_config.json").read_text())
        self.assertEqual(config["minimum_vdd_v"], 0.75)
        self.assertEqual(config["selected_operating_point"]["capture_phase_s"], 3.0e-10)
        with (FTC_ROOT / "runs/integrated_coarse_phase300/voltage_xor.csv").open(newline="", encoding="utf-8") as stream:
            coarse = list(csv.DictReader(stream))
        selected = [row for row in coarse if float(row["vdd_v"]) >= 0.75]
        self.assertEqual(len(selected), 8)
        for row in selected:
            corrected = ftc_analysis.majority_repair([int(bit) for bit in row["captured_xor_word"]])
            decoded = ftc_analysis.longest_one_run(corrected)
            self.assertEqual(decoded["start_index"], int(row["start_index"]))
            self.assertEqual(decoded["end_index"], int(row["end_index"]))
            self.assertEqual(decoded["one_run_length"], int(row["one_run_length"]))
            self.assertEqual(decoded["valid"], int(row["valid"]))
        with (FTC_ROOT / "runs/static_fine/static_transfer.csv").open(newline="", encoding="utf-8") as stream:
            fine = list(csv.DictReader(stream))
        self.assertEqual(len(fine), 36)
        self.assertTrue(all(int(row["valid"]) == 1 for row in fine))

    def test_physical_structure_contract(self) -> None:
        """Reject non-FTC topology additions and require selected physical cells."""

        cells = json.loads((FTC_ROOT / "discovery/selected_cells.json").read_text())
        self.assertEqual(cells["delay_rvt"]["cell"], "BUF_X0P7M_A9TR40")
        self.assertEqual(cells["delay_lvt"]["cell"], "BUF_X0P7M_A9TL40")
        # Strip comments before checking RTL syntax constructs: explanatory
        # comments may name a forbidden architecture while the hardware must not.
        sensor = "\n".join(line.split("//", 1)[0] for line in (FTC_ROOT / "rtl/ftc_sensor.sv").read_text().splitlines())
        for forbidden in ("VDD_REF", "VSS_REF", "CAL_SEL", "CUSUM", "Vernier", "#"):
            self.assertNotIn(forbidden, sensor)
        self.assertIn("OBSERVABLE_STAGES = 30", (FTC_ROOT / "rtl/ftc_config_pkg.sv").read_text())
        self.assertIn("LATQ_X0P5M_A9TR40", (FTC_ROOT / "rtl/ftc_capture_struct.sv").read_text())
        self.assertIn("DFFRPQ_X0P5M_A9TR40", (FTC_ROOT / "rtl/ftc_capture_struct.sv").read_text())

    def test_hspice_captured_words_replay_through_rtl(self) -> None:
        """Drive all formal coarse captures through VCS and assert exact encoding."""

        with (FTC_ROOT / "runs/integrated_coarse_phase300/voltage_xor.csv").open(newline="", encoding="utf-8") as stream:
            rows = [row for row in csv.DictReader(stream) if float(row["vdd_v"]) >= 0.75]
        lines = ["`timescale 1ns/1ps", "module ftc_hspice_replay_tb;", "logic [29:0] raw;", "wire [29:0] corrected;", "wire [4:0] start_i,end_i,length_i,runs_i,bubbles_i;", "wire valid_i;", "ftc_longest_run_encoder u(.captured_xor_word_i(raw),.corrected_xor_word_o(corrected),.start_index_o(start_i),.end_index_o(end_i),.one_run_length_o(length_i),.valid_o(valid_i),.run_count_o(runs_i),.bubble_count_o(bubbles_i));", "initial begin"]
        for index, row in enumerate(rows):
            # CSV character zero is physical stage zero, whereas an SV binary
            # literal's rightmost digit drives bit zero; reverse at the boundary.
            lines.append("raw=30'b{}; #1; if(start_i!==5'd{} || end_i!==5'd{} || length_i!==5'd{} || valid_i!==1'b{}) $fatal(1, \"HSPICE replay {} failed\");".format(row["captured_xor_word"][::-1], row["start_index"], row["end_index"], row["one_run_length"], row["valid"], index))
        lines.extend(["$display(\"FTC_HSPICE_REPLAY_PASS vectors=8\"); $finish; end", "endmodule"])
        with tempfile.TemporaryDirectory(prefix="hspice_replay_", dir=FTC_ROOT / "runs") as temporary:
            temporary_path = Path(temporary)
            testbench = temporary_path / "ftc_hspice_replay_tb.sv"
            testbench.write_text("\n".join(lines) + "\n", encoding="ascii")
            # The configured EDA launcher currently places Python 3.6 first
            # on PATH.  universal_newlines has the same decoded-text behavior
            # as text=True here while retaining compatibility with that runner.
            build = subprocess.run([str(VCS), "-full64", "-sverilog", "-o", str(temporary_path / "simv"), str(FTC_ROOT / "rtl/ftc_longest_run_encoder.sv"), str(testbench)], cwd=temporary_path, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(build.returncode, 0, build.stdout)
            replay = subprocess.run([str(temporary_path / "simv")], cwd=temporary_path, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            self.assertEqual(replay.returncode, 0, replay.stdout)
            self.assertIn("FTC_HSPICE_REPLAY_PASS vectors=8", replay.stdout)


if __name__ == "__main__":
    unittest.main()
