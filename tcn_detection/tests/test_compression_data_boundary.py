#!/usr/bin/env python3
"""Compression runners must fail closed at the train-only calibration boundary."""

from __future__ import print_function

import unittest

import numpy as np

from power_macro.tcn_detection.compression.run_sensitivity_scan import select_calibration
from power_macro.tcn_detection.dataset.model_data import WindowTable


class CompressionDataBoundaryTests(unittest.TestCase):
    """Verify deterministic selection without validation or test leakage."""

    def _table(self, splits):
        labels = np.asarray([0, 0, 1, 1], dtype=np.int64)
        metadata = tuple({"split": split, "window_id": "window-{}".format(index)}
                         for index, split in enumerate(splits))
        return WindowTable(np.zeros((4, 1, 32), dtype=np.float32), labels, metadata, 32)

    def test_calibration_is_deterministic_and_balanced(self):
        """The same seed and train table produce the same balanced identities."""

        table = self._table(["train"] * 4)
        first = select_calibration(table, 7, 1)
        second = select_calibration(table, 7, 1)
        self.assertEqual(first.metadata, second.metadata)
        self.assertEqual(np.bincount(first.labels, minlength=2).tolist(), [1, 1])

    def test_calibration_rejects_any_non_train_row(self):
        """Validation/IID/OOD rows cannot enter the importance estimator."""

        for split in ("validation", "iid_test", "ood_test"):
            table = self._table(["train", "train", "train", split])
            with self.assertRaisesRegex(ValueError, "train rows only"):
                select_calibration(table, 7, 1)


if __name__ == "__main__":
    unittest.main()
