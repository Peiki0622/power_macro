#!/usr/bin/env python3
"""Simulator-free tests for raw-code observability and majority correction."""

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import decode_vernier_code  # noqa: E402  # Tests import the same CLI module used by reports.


class ThermometerDecoderTests(unittest.TestCase):
    """Protect the 0*1* polarity contract used by the Vernier comparator bank."""

    def test_ideal_word_counts_leading_zeroes(self):
        """A bubble-free 0*1* word maps directly to the transition index."""

        result = decode_vernier_code.decode_word("00011111")
        self.assertEqual(result["sensor_code"], 3)
        self.assertTrue(result["code_valid"])
        self.assertEqual(result["bubble_count"], 0)

    def test_single_bubble_is_reported_even_when_majority_filter_repairs_it(self):
        """Raw anomaly evidence must survive correction for downstream quality logic."""

        result = decode_vernier_code.decode_word("00110111")
        self.assertEqual(result["raw_bubble_count"], 1)
        self.assertEqual(result["corrected_code"], "00111111")
        self.assertTrue(result["code_valid"])

    def test_full_scale_endpoints_are_valid_and_unambiguous(self):
        """All-zero and all-one words represent saturated but valid endpoints."""

        self.assertEqual(decode_vernier_code.decode_word("0000")["sensor_code"], 4)
        self.assertEqual(decode_vernier_code.decode_word("1111")["sensor_code"], 0)


if __name__ == "__main__":
    unittest.main()
