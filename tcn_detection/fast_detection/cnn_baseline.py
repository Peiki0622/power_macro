#!/usr/bin/env python3
"""Stream the frozen W8/A8 CNN through the fast-detector interface.

The CNN remains a reference only.  This module reads the already exported
integer memory package rather than rebuilding or recalibrating quantization,
so the Stage-1 comparison cannot silently change the deployed numeric path.
"""

from __future__ import print_function

import hashlib
import json
from collections import deque
from pathlib import Path

import numpy as np

from power_macro.tcn_detection.fast_detection.detector_base import Detector
from power_macro.tcn_detection.fixed_point import bittrue
from power_macro.tcn_detection.fixed_point.export_package import read_mem


def _sha256_file(path):
    """Return the declared artifact digest before accepting a memory tensor."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_tensor(root, record):
    """Load one signed memory file only after its shape and digest are checked."""

    path = Path(root) / "weights" / record["path"]
    if _sha256_file(path) != record["sha256"]:
        raise ValueError("fixed-point memory digest mismatch: {}".format(path))
    return read_mem(path, record["shape"], record["signed_bits"])


def load_w8_a8_package(package_root):
    """Reconstruct the selected exported package required by ``run_bittrue``.

    The quantization JSON contains all exponents, accumulator bounds and memory
    shapes; the numerical payload is loaded from separately hashed `.mem`
    files.  Keeping this reconstruction local avoids a second package format.
    """

    root = Path(package_root)
    config = json.loads((root / "quantization_config.json").read_text(
        encoding="utf-8"))["selected_numeric_package"]
    if (config["candidate_id"] != "w8_a8" or config["weight_bits"] != 8
            or config["activation_bits"] != 8):
        raise ValueError("fast detector baseline requires the exported W8/A8 package")
    layers = []
    widths = {}
    for description in config["layers"]:
        layer = dict(description)
        layer["weights"] = _load_tensor(root, description["weight_file"])
        layer["bias"] = _load_tensor(root, description["bias_file"])
        for field in ("weight_exponents", "accumulator_exponents", "accumulator_bounds"):
            layer[field] = np.asarray(description[field], dtype=np.int64)
        for field in ("input_exponent", "output_exponent"):
            layer[field] = int(description[field])
        layers.append(layer)
        widths[layer["name"]] = int(description["accumulator_width"])
    classifier_description = config["classifier"]
    classifier = dict(classifier_description)
    classifier["weights"] = _load_tensor(root, classifier_description["weight_file"])
    classifier["bias"] = _load_tensor(root, classifier_description["bias_file"])
    for field in ("weight_exponents", "accumulator_exponents", "accumulator_bounds"):
        classifier[field] = np.asarray(classifier_description[field], dtype=np.int64)
    classifier["input_exponent"] = int(classifier_description["input_exponent"])
    classifier["output_exponent"] = int(config["classifier_output_exponent"])
    classifier["output_bits"] = int(config["classifier_output_bits"])
    widths["classifier"] = int(classifier_description["accumulator_width"])
    return {
        "architecture_id": config["architecture_id"],
        "candidate_id": config["candidate_id"],
        "weight_bits": int(config["weight_bits"]),
        "activation_bits": int(config["activation_bits"]),
        "activation_exponents": dict(config["activation_exponents"]),
        "layers": layers,
        "classifier": classifier,
        "accumulator_widths": widths,
        "normalization_fold": dict(config["normalization_fold"]),
    }


class CnnBaselineDetector(Detector):
    """Use the frozen W8/A8 L32 CNN as a causal 32-sample alarm reference."""

    name = "cnn_w8_a8_l32"

    def __init__(self, package):
        super().__init__()
        self.package = package
        self.window_length = 32

    def _reset_state(self):
        """Discard the prior trace window so no cross-trace context survives."""

        self._codes = deque(maxlen=self.window_length)
        self.integer_logits = None

    def step(self, sensor_code, valid):
        """Append one valid code and run fixed-point CNN only after warm-up.

        Invalid captures hold both the window and the preceding alarm.  Before
        32 valid captures the CNN has no legal causal window, so it reports a
        safe level rather than fabricating a padded deployment decision.
        """

        code, accepted = self._begin_step(sensor_code, valid)
        if not accepted:
            return self.alarm
        self._codes.append(code)
        if len(self._codes) < self.window_length:
            self._alarm = False
            self.integer_logits = None
            return False
        window = np.asarray(list(self._codes), dtype=np.int16).reshape(1, 1, 32)
        result = bittrue.run_bittrue(window, self.package, batch_size=1)
        self.integer_logits = result["integer_logits"][0].astype(np.int64)
        # ``run_bittrue`` uses argmax, which selects Safe for equal logits.  The
        # explicit comparison below documents the hardware threshold directly.
        self._alarm = bool(self.integer_logits[1] > self.integer_logits[0])
        return self.alarm

    def snapshot(self):
        """Expose only bounded stream state and the last fixed-point decision."""

        state = super().snapshot()
        state.update({"window_fill": len(getattr(self, "_codes", ())),
                      "integer_logits": (self.integer_logits.tolist()
                                         if self.integer_logits is not None else None)})
        return state

    def hardware_cost(self):
        """Return the published structural CNN cost, not legacy RTL area."""

        return {"add_sub_count": 49068, "compare_count": 1,
                "multiplier_count": 49068, "state_bits": 32 * 6,
                "memory_bits": 1684 * 8, "cycles_per_sample": None,
                "estimated_macs_per_window": 49068}
