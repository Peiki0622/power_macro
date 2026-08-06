"""Exhaustive contracts for the deterministic thermometer encoder."""

from __future__ import print_function

import unittest

import numpy as np

from power_macro.tcn_detection.bnn.input_encoding import (
    THERMOMETER_WIDTH,
    encode_code,
    encode_codes,
    encode_windows,
)


class BnnInputEncodingTests(unittest.TestCase):
    """Bind every legal code and the channel-first window representation."""

    def test_all_33_codes_are_exact_thermometer_words(self):
        """Every legal lattice point has the specified prefix and population."""

        for code in range(THERMOMETER_WIDTH + 1):
            word = encode_code(code)
            self.assertEqual(word.shape, (THERMOMETER_WIDTH,))
            self.assertEqual(word.dtype, np.uint8)
            self.assertEqual(int(word.sum()), code)
            self.assertTrue(np.array_equal(
                word, np.asarray([int(index < code)
                                  for index in range(THERMOMETER_WIDTH)],
                                 dtype=np.uint8)))

    def test_invalid_codes_fail_closed(self):
        """Rounding, NaN, and out-of-range values cannot enter the bit path."""

        for value in (-1, 33, 1.5, np.nan, np.inf):
            with self.assertRaises((TypeError, ValueError)):
                encode_code(value)
        with self.assertRaises(TypeError):
            encode_code("15")

    def test_window_layout_is_channel_first_and_causal(self):
        """Encoding preserves order and cannot use a later code for a prefix."""

        prefix = np.asarray([0, 3, 15, 32], dtype=np.int64)
        extended = np.asarray([0, 3, 15, 32, 7], dtype=np.int64)
        first = encode_windows(prefix)
        second = encode_windows(extended)
        self.assertEqual(first.shape, (THERMOMETER_WIDTH, len(prefix)))
        self.assertEqual(second.shape, (THERMOMETER_WIDTH, len(extended)))
        self.assertTrue(np.array_equal(first, second[:, :len(prefix)]))
        self.assertTrue(np.array_equal(first[:, 0], encode_code(0)))
        self.assertTrue(np.array_equal(first[:, -1], encode_code(32)))

    def test_batched_windows_have_expected_shape(self):
        """The training layout is [batch, channel, time], not a hidden FC vector."""

        codes = np.asarray([[0, 1, 2], [30, 31, 32]], dtype=np.int64)
        encoded = encode_windows(codes)
        self.assertEqual(encoded.shape, (2, THERMOMETER_WIDTH, 3))
        self.assertTrue(np.array_equal(encoded[0, :, 2], encode_code(2)))
        self.assertTrue(np.array_equal(encoded[1, :, 0], encode_code(30)))


if __name__ == "__main__":
    unittest.main()
