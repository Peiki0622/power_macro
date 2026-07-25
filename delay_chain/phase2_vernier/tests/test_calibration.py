#!/usr/bin/env python3
"""Check deterministic 32-sample CAL_SEL choice and tie breaking."""

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import calibrate_vernier  # noqa: E402  # Direct import exercises the production selection logic.


class CalibrationTests(unittest.TestCase):
    """Build a compact synthetic CSV-equivalent trace with eight tap settings."""

    def test_midpoint_then_bubble_then_offset_ranking(self):
        """Tap two wins because it is closest to M/2 before later tie breakers."""

        config = {"calibration_sample_count": 32, "calibration_launch_offsets_s": [index * 1e-11 for index in range(8)]}
        rows = []
        for cal_sel in range(8):
            code = [6, 10, 15, 19, 24, 29, 32, 32][cal_sel]
            for sample_index in range(32):
                rows.append(
                    {
                        "cal_sel": str(cal_sel), "sensor_code": str(code), "raw_bubble_count": "0",
                        "launch_offset_s": "{:.12e}".format(cal_sel * 1e-11), "m_stages": "32", "code_valid": "True",
                    }
                )
        result = calibrate_vernier.choose(rows, config)
        self.assertEqual(result["selected_cal_sel"], 2)
        self.assertEqual(result["baseline_code"], 15)
        self.assertEqual(result["baseline_variation"], 0)


if __name__ == "__main__":
    unittest.main()
