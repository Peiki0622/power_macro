#!/usr/bin/env python3
"""Stream the frozen full-binary no-FC detector through the Stage-1 interface."""

from __future__ import print_function

from collections import deque

import numpy as np

from power_macro.tcn_detection.bnn.bittrue_nofc import run_bittrue
from power_macro.tcn_detection.fast_detection.detector_base import Detector


def _layer_popcount_widths(package):
    """Return one integer popcount width per folded layer for cost accounting."""

    widths = []
    for layer in package["layers"]:
        weights = layer["weights"]
        widths.append(int(weights.shape[1] * weights.shape[2]))
    return widths


class BnnNofcDetector(Detector):
    """Causal 32-sample full-binary detector with one alarm bit of output."""

    name = "bnn_therm32_w1a1_nofc_l32"

    def __init__(self, package):
        super().__init__()
        self.package = package
        self.window_length = 32
        self.vote_k = int(package["vote_k"])

    def _reset_state(self):
        """Clear the causal code deque and the latest bit-true evidence."""

        self._codes = deque(maxlen=self.window_length)
        self.vote_count = None
        self.temporal_bits = None

    def step(self, sensor_code, valid):
        """Append one accepted code and evaluate the packed XNOR pipeline."""

        code, accepted = self._begin_step(sensor_code, valid)
        if not accepted:
            return self.alarm
        self._codes.append(code)
        if len(self._codes) < self.window_length:
            self._alarm = False
            self.vote_count = None
            self.temporal_bits = None
            return self.alarm
        window = np.asarray(list(self._codes), dtype=np.int16).reshape(1, 32)
        result = run_bittrue(window, self.package, batch_size=1)
        self.vote_count = int(result["vote_count"][0])
        self.temporal_bits = result["temporal_bits"][0].copy()
        self._alarm = bool(result["predictions"][0])
        return self.alarm

    def snapshot(self):
        """Expose only bounded stream state, never raw training metadata."""

        state = super().snapshot()
        state.update({
            "window_fill": len(getattr(self, "_codes", ())),
            "vote_count": (int(self.vote_count) if self.vote_count is not None
                            else None),
            "vote_k": int(self.vote_k),
            "temporal_bits": (self.temporal_bits.tolist()
                               if self.temporal_bits is not None else None),
        })
        return state

    def hardware_cost(self):
        """Return an integer resource proxy for XNOR/popcount deployment."""

        xnor_ops = 0
        popcount_ops = 0
        compare_ops = 1  # final K-of-32 vote only; layer thresholds are encoded as counters.
        threshold_bits = 0
        memory_bits = 0
        for layer in self.package["layers"]:
            weights = layer["weights"]
            output_channels, input_channels, kernel = weights.shape
            xnor_ops += int(output_channels * input_channels * kernel * self.window_length)
            popcount_ops += int(output_channels * self.window_length)
            threshold_bits += int(output_channels * int(np.ceil(np.log2(input_channels * kernel + 2))))
            memory_bits += int(weights.size + layer["thresholds"].size
                               + layer["inversion_flags"].size)
        threshold_bits += int(np.ceil(np.log2(self.window_length + 1)))
        memory_bits += int(np.ceil(np.log2(self.window_length + 1)))
        return {
            "add_sub_count": 0,
            "compare_count": compare_ops,
            "multiplier_count": 0,
            "xnor_operation_count": xnor_ops,
            "popcount_operation_count": popcount_ops,
            "threshold_storage_bits": threshold_bits,
            "state_bits": 32 * 6,
            "memory_bits": memory_bits,
            "cycles_per_sample": 1,
        }
