#!/usr/bin/env python3
"""Step 8 optional kernel-crop tensor contracts."""

from __future__ import print_function

import unittest

import torch

from power_macro.tcn_detection.compression.kernel_surgery import (
    crop_model, crop_state_dict, validate_kernel_transition)
from power_macro.tcn_detection.models.cnn1d import CNN1D


class KernelSurgeryTests(unittest.TestCase):
    """Verify physical center taps and fail-closed transition validation."""

    def test_center_taps_are_physically_retained(self):
        """The k=3 tensor equals source taps [1,2,3], not a runtime mask."""

        torch.manual_seed(51)
        model = CNN1D(input_channels=1, class_count=2, channels=[3, 3, 3],
                      kernel_sizes=[5, 5, 5], dropout=0.0,
                      pooling_contract="multistat_average_max_endpoint")
        cropped = crop_model(model, [5, 3, 3])
        self.assertEqual(tuple(cropped.features[3].weight.shape[-1:]), (3,))
        self.assertEqual(tuple(cropped.features[6].weight.shape[-1:]), (3,))
        self.assertTrue(torch.equal(cropped.features[3].weight,
                                    model.features[3].weight[..., 1:4]))
        self.assertTrue(torch.equal(cropped.features[6].weight,
                                    model.features[6].weight[..., 1:4]))

    def test_invalid_kernel_transitions_fail_closed(self):
        """Changing Conv1 or jumping to unsupported widths is forbidden."""

        for target in ([3, 5, 5], [3, 3, 3], [5, 3, 5]):
            with self.assertRaises(ValueError):
                validate_kernel_transition([5, 5, 5], target)


if __name__ == "__main__":
    unittest.main()
