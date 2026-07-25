#!/usr/bin/env python3
"""Regression checks for the authoritative 765 MHz r3 experiment anchor."""

import json
import unittest
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[1] / "phase2_config.json"


class ConfigValidationTests(unittest.TestCase):
    """Prevent an old 770 MHz threshold from re-entering Phase 2 by accident."""

    def test_765mhz_35_40_bank_anchor_is_exact(self):
        """The static sensor study must use the latest passing/failing r3 pair."""

        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        anchor = config["timing_anchor"]
        self.assertEqual(anchor["clock_frequency_mhz"], 765.0)
        self.assertEqual(anchor["last_passing_bank_count"], 35)
        self.assertEqual(anchor["first_violation_bank_count"], 40)
        self.assertAlmostEqual(anchor["first_violation_voltage_v"], 1.047473942801, places=12)
        self.assertEqual(config["phase1_anchor_voltages_v"][2], anchor["first_violation_voltage_v"])


if __name__ == "__main__":
    unittest.main()
