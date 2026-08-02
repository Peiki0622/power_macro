"""Contract tests for the deterministic task-three dummy-window library."""

import json
import tempfile
import unittest
from pathlib import Path

from power_macro.rtl.cnn_monitor.scripts.generate_activity_windows import generate


CNN_ROOT = Path(__file__).resolve().parents[1]


class ActivityWindowTest(unittest.TestCase):
    """Ensure activity inputs cannot drift outside the frozen L32 contract."""

    def test_library_is_complete_legal_and_reproducible(self):
        """Two independent outputs must have identical manifest and JSONL bytes."""
        config = CNN_ROOT / "config" / "cnn_activity_config_v1.json"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            generate(config, root / "first")
            generate(config, root / "second")
            self.assertEqual((root / "first" / "windows.jsonl").read_bytes(), (root / "second" / "windows.jsonl").read_bytes())
            manifest = json.loads((root / "first" / "manifest.json").read_text())
            records = [json.loads(line) for line in (root / "first" / "windows.jsonl").read_text().splitlines()]
        self.assertEqual(manifest["record_count"], 36)
        self.assertEqual(manifest["families"], {"control": 5, "endpoint_dominant": 6, "mean_dominant": 7, "mixed_statistic": 8, "peak_dominant": 10})
        self.assertEqual(len({record["pattern_id"] for record in records}), len(records))
        self.assertTrue(all(len(record["sensor_codes"]) == 32 for record in records))
        self.assertTrue(all(0 <= value <= 32 for record in records for value in record["sensor_codes"]))
        self.assertTrue(all(record["expected"]["latency_cycles"] == 12892 for record in records))
        self.assertTrue(all(not record["expected"]["numeric_overflow"] for record in records))


if __name__ == "__main__":
    unittest.main()
