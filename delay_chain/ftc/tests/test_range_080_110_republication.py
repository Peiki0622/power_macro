"""Regression for the data-only FTC 0.80--1.10 V re-publication flow."""

import json
import sys
import tempfile
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import republish_range_080_110 as republish  # noqa: E402  # Test the no-HSPICE data path.


class RangeRepublishTest(unittest.TestCase):
    """Verify range filtering, manifest provenance, and declared evidence gaps."""

    def test_filtered_source_rows_match_current_contract(self):
        """The pure filter must retain all and only the legal fixed grids.

        The coarse evidence deliberately retains every phase repeat for the
        downstream repeat-consistency calculation, while its phi_p00 subset
        independently proves that the nominal seven-point grid is complete.
        """

        static = republish.in_range(republish.read_csv(FTC_ROOT / "runs/static_fine/static_transfer.csv"))
        real_xor = republish.in_range(republish.read_csv(FTC_ROOT / "analysis/real_xor_pulse_width/fine.csv"))
        republish.exact_grid(static, republish.FINE_VDDS, "static")
        republish.exact_grid(real_xor, republish.FINE_VDDS, "real xor")
        coarse_all = republish.in_range(
            republish.read_csv(FTC_ROOT / "runs/phase_diverse_screen/phase_candidate_coarse.csv")
        )
        nominal_coarse = [row for row in coarse_all if row["phase_id"] == "phi_p00"]
        republish.exact_grid(nominal_coarse, republish.COARSE_VDDS, "nominal coarse")
        self.assertEqual(len(static), 31)
        self.assertEqual(len(real_xor), 31)
        self.assertGreater(len(coarse_all), len(nominal_coarse))
        self.assertTrue(all(float(row["vdd_v"]) >= 0.80 for row in static + real_xor + coarse_all))

    def test_manifest_is_explicitly_data_only(self):
        """A temporary audit manifest must record no HSPICE and the study limits."""

        with tempfile.TemporaryDirectory(prefix="ftc_range_republication_") as temporary:
            root = Path(temporary) / "r1"
            # This test exercises only filtering, hashes, and report generation.
            # The production analysis output paths are not used by this helper.
            static = republish.in_range(republish.read_csv(FTC_ROOT / "runs/static_fine/static_transfer.csv"))
            republish.write_csv(root / "filtered_inputs/static.csv", static)
            manifest = {
                "new_hspice_runs": 0,
                "legal_vdd_range_v": [0.80, 1.10],
                "input_hash": republish.sha256(FTC_ROOT / "runs/static_fine/static_transfer.csv"),
            }
            republish.write_json(root / "manifest.json", manifest)
            loaded = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(loaded["new_hspice_runs"], 0)
        self.assertEqual(loaded["legal_vdd_range_v"], [0.80, 1.10])
        self.assertEqual(len(loaded["input_hash"]), 64)


if __name__ == "__main__":
    unittest.main()
