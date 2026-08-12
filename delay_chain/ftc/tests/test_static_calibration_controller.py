"""Trace-driven VCS regression for the synthesized FTC calibration FSM."""

import subprocess
import tempfile
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
VCS = Path("/home/synopsys/vcs/W-2024.09/bin/vcs")
TRACE = FTC_ROOT / "analysis" / "static_self_calibration" / "calibration_trace.csv"


class StaticCalibrationControllerTest(unittest.TestCase):
    """Compile the controller and exercise all published and fault Q traces."""

    def test_real_trace_and_boundary_fault_contract(self):
        """Prove exact locks for all seven VDDs and all mandated fault edges.

        The SystemVerilog harness consumes the complete 54-row physical trace,
        uses every lock-reachable Q response to drive the FSM, validates the
        remaining measured headroom rows, then runs four protocol-local fault
        sequences.  VCS work products are isolated in a TemporaryDirectory
        under runs/ and removed automatically on both pass and assertion fail.
        """

        self.assertTrue(VCS.is_file(), "expected local VCS executable is unavailable")
        self.assertTrue(TRACE.is_file(), "published real-DFF calibration trace is unavailable")
        run_root = FTC_ROOT / "runs"
        run_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="static_calibration_controller_", dir=run_root) as temporary:
            output_dir = Path(temporary)
            compile_result = subprocess.run(
                [
                    str(VCS), "-full64", "-sverilog",
                    "-Mdir={}".format(output_dir / "csrc"),
                    "-o", str(output_dir / "simv"),
                    str(FTC_ROOT / "rtl" / "ftc_static_calibration_controller.sv"),
                    str(FTC_ROOT / "tests" / "ftc_static_calibration_controller_tb.sv"),
                ],
                cwd=output_dir,
                universal_newlines=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stdout)
            run_result = subprocess.run(
                [str(output_dir / "simv"), "+TRACE={}".format(TRACE)],
                cwd=output_dir,
                universal_newlines=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(run_result.returncode, 0, run_result.stdout)
            self.assertIn(
                "FTC_CAL_TRACE_PASS traces=7 rows=54 locks=5,5,5,5,5,4,4 fault_cases=4",
                run_result.stdout,
            )


if __name__ == "__main__":
    unittest.main()
