"""Failure-oriented tests for task-three codebook integrity validation."""

import json
import unittest
from copy import deepcopy
from pathlib import Path

from power_macro.rtl.cnn_monitor.scripts.validate_activity_codebook import (
    CodebookValidationError,
    validate_records,
)


CNN_ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    "convolution_mac", "weight_intermediate_storage", "average_accumulator",
    "maximum_tracker", "endpoint_registers", "classifier", "control_address",
}


def _fixtures():
    """Build a valid 36-pattern in-memory codebook with exactly three repeats."""
    windows, codebook, raw = [], [], []
    for index in range(36):
        pattern_id = "control_{:02d}".format(index) if index < 5 else "dummy_{:02d}".format(index)
        family = "control" if index < 5 else "synthetic"
        digest = "{:064x}".format(index + 1)
        expected = {"safe_logit": index, "critical_logit": -index, "decision": 0}
        window = {"pattern_id": pattern_id, "family": family, "input_sha256": digest}
        record = {
            **window, "expected": expected, "validity_status": "valid",
            "module_toggle_vector": {group: 0 for group in GROUPS},
            "average_dynamic_power_mw": None, "energy_window_nj": None,
            "peak_power_mw": None,
        }
        windows.append(window)
        codebook.append(record)
        for repeat in range(3):
            raw.append({
                "pattern_id": pattern_id, "repeat": repeat, "latency_cycles": 12892,
                "safe_logit": index, "critical_logit": -index, "decision": 0,
                "numeric_overflow": False, "protocol_error": False,
            })
    return windows, codebook, raw


class ActivityCodebookValidationTest(unittest.TestCase):
    """Keep every mandated malformed-codebook failure path executable."""

    def setUp(self):
        self.config = json.loads((CNN_ROOT / "config" / "cnn_activity_power_config_v2.json").read_text())
        self.windows, self.codebook, self.raw = _fixtures()

    def _assert_invalid(self, mutate):
        """Apply one fixture mutation and require the validator to reject it."""
        windows, codebook, raw = deepcopy(self.windows), deepcopy(self.codebook), deepcopy(self.raw)
        mutate(windows, codebook, raw)
        with self.assertRaises(CodebookValidationError):
            validate_records(codebook, raw, windows, self.config, power_required=False)

    def test_valid_fixture_passes(self):
        """The fixture proves tests are exercising validator behavior, not setup errors."""
        self.assertEqual(
            validate_records(self.codebook, self.raw, self.windows, self.config, False)["status"],
            "PASS",
        )

    def test_missing_duplicate_sha_latency_and_power_fail(self):
        """Each error must remain independently visible to future refactors."""
        self._assert_invalid(lambda windows, codebook, raw: codebook.pop())
        self._assert_invalid(lambda windows, codebook, raw: codebook.append(deepcopy(codebook[0])))
        self._assert_invalid(lambda windows, codebook, raw: codebook[5].update(input_sha256="bad"))
        self._assert_invalid(lambda windows, codebook, raw: raw[0].update(latency_cycles=1))
        self._assert_invalid(lambda windows, codebook, raw: codebook[0].update(energy_window_nj=1.0))
