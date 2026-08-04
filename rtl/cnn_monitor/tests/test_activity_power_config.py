"""Schema tests for the frozen task-three gate-power configuration."""

import json
import unittest
from pathlib import Path

from power_macro.rtl.cnn_monitor.scripts.analyze_activity_codebook_v2 import _load_config


CNN_ROOT = Path(__file__).resolve().parents[1]


class ActivityPowerConfigTest(unittest.TestCase):
    """Reject incomplete or physically meaningless v2 gate settings."""

    def setUp(self):
        self.config = json.loads((CNN_ROOT / "config" / "cnn_activity_power_config_v2.json").read_text())

    def test_required_fields_and_frozen_values(self):
        """The file must contain the complete task-three acceptance contract."""
        required = {
            "schema_version", "config_id", "baseline_commit", "window_length",
            "sensor_code_min", "sensor_code_max", "mac_lanes", "repeat_count",
            "compute_latency_cycles", "initiation_interval_cycles",
            "activity_separation_fraction", "max_repeat_cv_fraction",
            "minimum_patterns_per_tier", "required_tier_count",
            "required_valid_pattern_count", "required_candidate_pattern_count",
            "primary_input_annotation_fraction_min",
            "sequential_output_annotation_fraction_min", "rom_output_annotation_fraction_min",
            "overall_state_element_annotation_fraction_min", "reject_power_warning_ids",
        }
        self.assertTrue(required.issubset(self.config))
        self.assertEqual(self.config["window_length"], 32)
        self.assertEqual(self.config["mac_lanes"], 16)
        self.assertEqual(self.config["repeat_count"], 3)
        self.assertEqual(self.config["compute_latency_cycles"], 12892)
        self.assertEqual(self.config["initiation_interval_cycles"], 12893)

    def test_thresholds_are_within_legal_ranges(self):
        """Coverage and repeatability gates must be strict probabilities."""
        for name in (
            "activity_separation_fraction", "max_repeat_cv_fraction",
            "primary_input_annotation_fraction_min",
            "sequential_output_annotation_fraction_min", "rom_output_annotation_fraction_min",
            "overall_state_element_annotation_fraction_min",
        ):
            self.assertGreaterEqual(self.config[name], 0.0)
            self.assertLessEqual(self.config[name], 1.0)
        self.assertEqual(self.config["primary_input_annotation_fraction_min"], 1.0)
        self.assertEqual(self.config["rom_output_annotation_fraction_min"], 1.0)
        self.assertIn("PWR-415", self.config["reject_power_warning_ids"])
        self.assertIn("PWR-428", self.config["reject_power_warning_ids"])

    def test_schema_loader_rejects_missing_type_and_threshold_drift(self):
        """A malformed or weakened config must fail before a power run starts."""
        path = CNN_ROOT / "config" / "cnn_activity_power_config_v2.json"
        self.assertEqual(_load_config(path), self.config)
        missing = dict(self.config)
        missing.pop("repeat_count")
        broken = self._write_fixture(missing)
        with self.assertRaises(ValueError):
            _load_config(broken)
        wrong_type = dict(self.config)
        wrong_type["repeat_count"] = "3"
        broken = self._write_fixture(wrong_type)
        with self.assertRaises(ValueError):
            _load_config(broken)
        weakened = dict(self.config)
        weakened["rom_output_annotation_fraction_min"] = 0.99
        broken = self._write_fixture(weakened)
        with self.assertRaises(ValueError):
            _load_config(broken)

    def _write_fixture(self, payload):
        """Create an isolated configuration fixture cleaned by unittest itself."""
        path = self.id().replace(".", "_")
        fixture = Path("/tmp") / (path + ".json")
        fixture.write_text(json.dumps(payload), encoding="utf-8")
        self.addCleanup(lambda: fixture.unlink(missing_ok=True))
        return fixture
