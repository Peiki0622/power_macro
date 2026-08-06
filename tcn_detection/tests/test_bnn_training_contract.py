"""End-to-end contract tests for the three-stage BNN trainer."""

from __future__ import print_function

import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from power_macro.tcn_detection.bnn.train_nofc_bnn import run_training


def _window(code):
    """Serialize one exact normalized L32 code window used by the frozen data."""

    value = (int(code) - 15) / 17.0
    return json.dumps([[value] for _ in range(32)])


class BnnTrainingContractTests(unittest.TestCase):
    """Exercise split filtering and stage hand-off without touching release data."""

    def _write_windows(self, path):
        """Write balanced development rows plus malformed IID data to reject leaks."""

        fields = ["window_id", "trace_id", "split", "end_index",
                  "target_label", "length", "feature_channels", "features_json"]
        rows = [
            ("train_safe", "train_a", "train", 31, 0, _window(10)),
            ("train_critical", "train_b", "train", 32, 1, _window(25)),
            ("val_safe", "val_a", "validation", 31, 0, _window(9)),
            ("val_critical", "val_b", "validation", 32, 1, _window(26)),
            # This IID payload is deliberately malformed.  The loader must
            # skip it before JSON parsing because training cannot read IID.
            ("iid_forbidden", "iid_a", "iid_test", 31, 0, "not-json"),
        ]
        with Path(path).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for window_id, trace_id, split, endpoint, label, features in rows:
                writer.writerow({"window_id": window_id, "trace_id": trace_id,
                                 "split": split, "end_index": endpoint,
                                 "target_label": label, "length": 32,
                                 "feature_channels": 1,
                                 "features_json": features})

    def test_three_stages_publish_validation_only_artifacts(self):
        """FP->W1A8->W1A1 completes from a clean temporary input directory."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            windows = root / "windows_L32.csv"
            model_config = root / "model.json"
            training_config = root / "training.json"
            output = root / "run"
            self._write_windows(windows)
            model_config.write_text(json.dumps({
                "candidate_widths": [8], "window_length": 32,
                "input_channels": 32}), encoding="utf-8")
            training_config.write_text(json.dumps({
                "seeds": [11], "cpu_threads_per_process": 1,
                "batch_size": 2, "max_epochs": 1,
                "early_stopping_patience": 1, "learning_rate": 0.003,
                "weight_decay": 0.00001}), encoding="utf-8")
            arguments = SimpleNamespace(
                windows=windows, model_config=model_config,
                training_config=training_config, seed=11, width=8,
                output_dir=output)
            result = run_training(arguments)
            self.assertEqual(set(result), {"fp_pretrain", "w1a8", "w1a1"})
            for stage in result:
                summary = json.loads((output / stage / "training_summary.json").read_text(
                    encoding="utf-8"))
                self.assertFalse(summary["iid_features_loaded"])
                self.assertTrue((output / stage / "best_checkpoint.pt").is_file())
                self.assertTrue((output / stage / "validation_predictions.csv").is_file())
            with self.assertRaises(FileExistsError):
                run_training(arguments)


if __name__ == "__main__":
    unittest.main()
