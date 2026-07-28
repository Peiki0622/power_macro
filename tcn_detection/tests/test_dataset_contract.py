#!/usr/bin/env python3
"""Regression tests for TCN corpus, split, labels, and raw cleanup contracts."""

from __future__ import print_function

import csv
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / "power_macro" / "tcn_detection" / "waveform", ROOT / "power_macro" / "tcn_detection" / "labels",
                  ROOT / "power_macro" / "tcn_detection" / "batch", ROOT / "power_macro" / "tcn_detection" / "dataset"):
    # Append helper directories after the standard library.  Inserting
    # ``batch/`` at position zero shadows Python's stdlib ``queue`` module with
    # the project's ``batch/queue.py`` and breaks PyTorch imports in the model
    # contract suite.
    sys.path.append(str(directory))
import waveform_schema  # noqa: E402
import label_traces  # noqa: E402
import worker  # noqa: E402
import build_corpus  # noqa: E402
import audit_splits  # noqa: E402
import build_windows  # noqa: E402


class DatasetContractTests(unittest.TestCase):
    """Keep data-model promises independent of long licensed simulations."""

    def test_waveform_is_deterministic_and_has_safe_context(self):
        """The same request must regenerate exactly one source waveform."""

        spec = {"seed": 7, "background_mode": "busy", "event": {"family": "trapezoid", "amplitude_mv": 40.0, "length_samples": 50, "start_index": 80}}
        first = waveform_schema.build_trace(spec)
        second = waveform_schema.build_trace(spec)
        self.assertEqual(first["target_droop_mv"], second["target_droop_mv"])
        self.assertEqual(len(first["target_droop_mv"]), 500)
        self.assertTrue(all(0.2 <= value <= 100.0 for value in first["target_droop_mv"]))

    def test_event_metadata_preserves_requested_duty_cycle(self):
        """The low-duty evaluation stratum must not depend on implicit lengths."""

        event = build_corpus.make_event("trapezoid", 0.05, 17, False, 1)
        self.assertEqual(event["duty_cycle"], 0.05)
        self.assertEqual(event["length_samples"], 25)

    def test_hard_pair_respects_strict_direct_rail_upper_bound(self):
        """Critical hard pairs must remain renderable by the qualified PWL port."""

        self.assertLess(build_corpus.HARD_PAIR_MAX_DROOP_MV, 100.0)
        self.assertEqual(build_corpus.HARD_PAIR_MAX_DROOP_MV, 99.9)

    def test_slack_interpolation_refuses_extrapolation(self):
        """Labels cannot silently invent timing truth outside measured voltage."""

        points = [{"v": 1.0, "s": -2.0}, {"v": 1.1, "s": 8.0}]
        self.assertAlmostEqual(label_traces.interpolate(points, 1.05), 3.0)
        with self.assertRaises(ValueError):
            label_traces.interpolate(points, 0.99)

    def test_label_rows_use_voltage_truth_not_sensor_code(self):
        """Changing a sensor observation cannot change slack-derived labels."""

        rows = [{"measured_vdd_a_v": "1.10", "sensor_code": "15"},
                {"measured_vdd_a_v": "1.06", "sensor_code": "32"},
                {"measured_vdd_a_v": "1.04", "sensor_code": "0"}]
        points = [{"v": 1.04, "s": -1.0}, {"v": 1.06, "s": 2.0}, {"v": 1.10, "s": 10.0}]
        config = {"prediction_horizon_samples": 1, "warning_slack_ps": 5.0,
                  "recover_samples": 3, "recover_safe_slack_ps": 6.0}
        labels = label_traces.label_rows(rows, points, config)
        changed_rows = [dict(row, sensor_code="999") for row in rows]
        changed = label_traces.label_rows(changed_rows, points, config)
        self.assertEqual([row["raw_label"] for row in labels], [row["raw_label"] for row in changed])
        self.assertNotIn("sensor_code", inspect.getsource(label_traces.label_rows))

    def test_future_horizon_excludes_current_sample_and_blanks_tail(self):
        """Endpoint e targets exactly e+1 through e+H, never its own slack."""

        rows = [{"measured_vdd_a_v": voltage} for voltage in ("1.04", "1.10", "1.10", "1.10")]
        points = [{"v": 1.04, "s": -1.0}, {"v": 1.10, "s": 10.0}]
        config = {"prediction_horizon_samples": 2, "warning_slack_ps": 5.0,
                  "recover_samples": 3, "recover_safe_slack_ps": 6.0}
        labels = label_traces.label_rows(rows, points, config)
        self.assertEqual(labels[0]["raw_label"], "0")
        self.assertEqual(labels[1]["raw_label"], "0")
        self.assertEqual(labels[2]["label_eligible"], "False")
        self.assertEqual(labels[3]["future_min_slack_ps"], "")

    def test_hysteresis_requires_three_safe_future_samples_before_recovery(self):
        """A dangerous state cannot downgrade after an isolated safe point."""

        self.assertEqual(label_traces.hysteresis([2, 0, 0, 0], [0.0, 7.0, 7.0, 7.0], 3, 6.0), [2, 2, 2, 1])

    def test_windows_preserve_causal_bounds_and_train_cap(self):
        """Train uses stride two/cap 240 while evaluation keeps every endpoint."""

        def rows(split):
            result = []
            for index in range(500):
                result.append({"trace_id": "trace_unit", "base_waveform_id": "base_unit", "waveform_family_id": "triangle",
                               "hard_pair_id": "", "split": split, "sensor_code": str(15 + (index % 2)),
                               "bubble_count": "0", "code_valid": "True", "label_eligible": str(index < 492),
                               "hysteresis_label": "0"})
            return result
        train = build_windows.build_trace_windows(rows("train"), 8, 15, 32, 240)
        evaluation = build_windows.build_trace_windows(rows("iid_test"), 8, 15, 32, 240)
        self.assertEqual(len(train), 240)
        self.assertEqual(train[0]["end_index"], 7)
        self.assertEqual(train[1]["end_index"], 9)
        self.assertEqual(train[-1]["target_end_index"], train[-1]["end_index"] + 8)
        self.assertEqual(len(evaluation), 485)
        self.assertEqual(evaluation[-1]["end_index"], 491)

    def test_split_audit_requires_hard_pairs_to_remain_in_ood(self):
        """Hard-pair traces are an OOD-only paired experiment, not train data."""

        valid = [{"trace_id": "a", "base_waveform_id": "base_a", "waveform_family_id": "rlc_ringing", "split": "ood_test",
                  "hard_pair_id": "pair", "background_mode": "busy", "event_duty_cycle": 0.01},
                 {"trace_id": "b", "base_waveform_id": "base_b", "waveform_family_id": "glitch_cluster", "split": "ood_test",
                  "hard_pair_id": "pair", "background_mode": "mixed", "event_duty_cycle": 0.05}]
        self.assertEqual(audit_splits.build_audit(valid)["hard_pair_splits"]["pair"], ["ood_test"])
        invalid = [dict(row) for row in valid]
        invalid[0]["split"] = "train"
        with self.assertRaises(ValueError):
            audit_splits.build_audit(invalid)

    def test_cleanup_retains_only_bounded_command_log(self):
        """Raw cleanup must not delete arbitrary files or retain waveforms."""

        with tempfile.TemporaryDirectory() as temporary:
            attempt = Path(temporary)
            for name in ("trace.tr0", "trace.lis", "trace.mt0.csv", "trace.sp", "hspice_command.log"):
                (attempt / name).write_text("x", encoding="ascii")
            ledger = worker.cleanup_raw(attempt, [Path("compact.csv"), Path("compact.json")])
            self.assertEqual({entry["path"] for entry in ledger}, {"trace.tr0", "trace.lis", "trace.mt0.csv", "trace.sp"})
            self.assertTrue((attempt / "hspice_command.log").is_file())
            self.assertTrue((attempt / "cleanup.json").is_file())

    def test_failure_listing_retains_only_last_64_kib(self):
        """Failed runs retain bounded diagnostics while discarding raw listings."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attempt = root / "attempt"
            failure = root / "failure"
            attempt.mkdir()
            failure.mkdir()
            # A distinctive suffix proves that the EOF-oriented copy preserved
            # the useful final diagnostic rather than the beginning of a large
            # HSPICE listing.
            payload = b"prefix" * (worker.FAILURE_LISTING_TAIL_BYTES + 32) + b"FINAL DIAGNOSTIC"
            (attempt / "trace.lis").write_bytes(payload)
            name = worker.retain_failure_listing_tail(attempt, failure, 1)
            retained = (failure / name).read_bytes()
            self.assertLessEqual(len(retained), worker.FAILURE_LISTING_TAIL_BYTES)
            self.assertTrue(retained.endswith(b"FINAL DIAGNOSTIC"))


if __name__ == "__main__":
    unittest.main()
