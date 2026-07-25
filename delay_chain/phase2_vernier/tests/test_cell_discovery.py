#!/usr/bin/env python3
"""Regression checks for the selected real standard-cell interfaces."""

import json
import unittest
from pathlib import Path


DISCOVERY_PATH = Path(__file__).resolve().parents[1] / "discovery" / "selected_cells.json"


class CellDiscoveryTests(unittest.TestCase):
    """Ensure deck generators consume verified positional CDL port order."""

    def test_selected_dff_has_expected_clock_data_reset_ports(self):
        """A DFF port swap would electrically invalidate every comparator bit."""

        cells = json.loads(DISCOVERY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(cells["dff"]["cell"], "DFFRPQ_X0P5M_A9TR40")
        self.assertEqual(cells["dff"]["cdl_ports"], ["Q", "VDD", "VNW", "VPW", "VSS", "CK", "D", "R"])
        self.assertEqual(cells["dff"]["reset_polarity"], "active_high_async_clear")

    def test_selected_mux_and_buffer_are_real_cdl_candidates(self):
        """The launch-control path must not depend on a conventional guessed name."""

        cells = json.loads(DISCOVERY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(cells["mux"]["cdl_ports"], ["Y", "VDD", "VNW", "VPW", "VSS", "A", "B", "S0"])
        self.assertEqual(cells["buffer"]["cdl_ports"], ["Y", "VDD", "VNW", "VPW", "VSS", "A"])


if __name__ == "__main__":
    unittest.main()
