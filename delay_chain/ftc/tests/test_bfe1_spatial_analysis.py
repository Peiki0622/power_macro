"""Pure-Python checks for B-FE1 raw-code and platform semantics."""

import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_bfe1_spatial as analysis  # noqa: E402


class Bfe1SpatialAnalysisTest(unittest.TestCase):
    """Exercise deterministic zero-HSPICE pieces with simple raw bit words."""

    def test_code_metrics_retains_fragmentation_and_ties(self):
        """No bubble repair may hide two equal-length physical runs."""

        result = analysis.code_metrics([0, 1, 1, 0, 1, 1] + [0] * 24)
        self.assertEqual(result["raw_code"][:6], "011011")
        self.assertEqual(result["run_count"], 2)
        self.assertEqual(len(result["main_run_ties"]), 2)
        self.assertTrue(result["fragmented"])
        self.assertEqual(result["start"], 1)
        self.assertEqual(result["end"], 2)

    def test_code_metrics_reports_empty_without_fake_headroom(self):
        """An empty word must not be converted to a synthetic longest run."""

        result = analysis.code_metrics([0] * 30)
        self.assertTrue(result["empty"])
        self.assertIsNone(result["start"])
        self.assertIsNone(result["left_headroom"])

    def test_unique_boundaries_preserves_real_platform_width(self):
        """Only numerical duplicates may collapse; close physical edges remain."""

        boundaries = analysis.unique_boundaries([0.0, 10.0, 10.0 + 1.0e-8, 11.0])
        self.assertEqual(boundaries, [0.0, 10.0, 11.0])
        boundaries = analysis.unique_boundaries([0.0, 10.0, 10.1, 11.0])
        self.assertEqual(boundaries, [0.0, 10.0, 10.1, 11.0])

    def test_spatial_figure_uses_active_window_and_vertical_tap_rows(self):
        """The plot must not compress a code into the full transient tail.

        This source-level regression protects the physical axis convention:
        tap ``i`` is a y-axis row, while a raw interval occupies its real
        crossing-bounded x-axis duration.  The image is deliberately derived
        only from saved interval JSON, without any HSPICE invocation.
        """

        source = Path(analysis.__file__).read_text(encoding="utf-8")
        self.assertIn("active_intervals = [item for item in intervals if not item[\"empty\"]]", source)
        self.assertIn("tap_rows = [[int(bit)] for bit in interval[\"raw_code\"]]", source)
        self.assertIn("axis.set_xlim(active_start - horizontal_padding, active_end + horizontal_padding)", source)


if __name__ == "__main__":
    unittest.main()
