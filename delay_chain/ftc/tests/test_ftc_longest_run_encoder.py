"""Run the standalone FTC encoder's nine-vector synthesizable RTL contract."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
VCS = Path("/home/synopsys/vcs/W-2024.09/bin/vcs")


class FtcLongestRunEncoderTest(unittest.TestCase):
    """Compile and execute the decoder without regenerating any HSPICE data."""

    def test_synthetic_longest_run_contract(self) -> None:
        """Verify all plan-required words, bubble repair, and the low tie rule."""

        self.assertTrue(VCS.is_file(), "expected local VCS executable is unavailable")
        run_root = FTC_ROOT / "runs"
        run_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="encoder_unit_", dir=run_root) as temporary:
            output_dir = Path(temporary)
            # Use universal_newlines rather than text=True because the EDA
            # environment's default Python is 3.6; output remains decoded
            # text for the assertions below on both old and new interpreters.
            compile_result = subprocess.run(
                [
                    str(VCS), "-full64", "-sverilog", "-o", str(output_dir / "simv"),
                    str(FTC_ROOT / "rtl" / "ftc_longest_run_encoder.sv"),
                    str(FTC_ROOT / "tests" / "ftc_longest_run_encoder_tb.sv"),
                ],
                cwd=output_dir, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stdout)
            run_result = subprocess.run(
                [str(output_dir / "simv")], cwd=output_dir, universal_newlines=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            self.assertEqual(run_result.returncode, 0, run_result.stdout)
            self.assertIn("FTC_ENCODER_UNIT_PASS cases=9", run_result.stdout)


if __name__ == "__main__":
    unittest.main()
