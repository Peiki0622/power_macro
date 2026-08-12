"""Pure-data regression tests for FTC phase-diverse qualification and scoring.

The tests use synthetic compact records only.  They intentionally never import
the deck generator or invoke HSPICE, so a pass validates deterministic analysis
contracts without being mistaken for fresh electrical evidence.
"""

import json
import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import analyze_phase_diverse as analysis  # noqa: E402  # Exercise public pure-data helpers.
import run_ftc_characterization as runner  # noqa: E402  # Exercise phase-ID/config validation only.


def row(phase_id, multiplier, phase_s, vdd, start, end, valid=1, onset=0.0, case_id="medium"):
    """Build a complete compact row with only physically relevant synthetic fields."""

    return {
        "phase_id": phase_id, "phase_multiplier": str(multiplier), "capture_phase_s": str(phase_s),
        "vdd_v": str(vdd), "start_index": str(start), "end_index": str(end),
        "one_run_length": str(end - start + 1 if valid else 0), "valid": str(valid),
        "touches_left_boundary": "0", "touches_right_boundary": "0", "captured_xor_word": "0" * 30,
        "case_id": case_id, "glitch_onset_rel_s": str(onset), "encoded_state_changed": "0",
        "boundary_distance": "0",
    }


class FtcPhaseDiverseTest(unittest.TestCase):
    """Protect the phase-specific baseline and common-blind-window semantics."""

    def test_candidate_ids_follow_measured_step(self):
        """Phase IDs must preserve signed measured-step identity rather than rounded time text."""

        base = runner.load_json(FTC_ROOT / "ftc_config.json")
        settings = runner.phase_diverse_settings(FTC_ROOT / "analysis/phase_diverse/phase_diverse_config.json", base)
        candidates = runner.phase_diverse_candidates(settings)
        self.assertEqual(candidates[0]["phase_id"], "phi_m04")
        self.assertEqual(candidates[4]["phase_id"], "phi_p00")
        self.assertAlmostEqual(candidates[-1]["capture_phase_s"], 3.5487374e-10)

    def test_qualification_allows_low_voltage_boundary_but_rejects_invalid(self):
        """The 0.80 V endpoint is valid when decodable; a failed capture is not."""

        anchors = [row("phi_p00", 0, 3e-10, vdd, start, end) for vdd, start, end in ((1.1, 10, 18), (0.9, 4, 10), (0.8, 0, 3))]
        coarse = [row("phi_p00", 0, 3e-10, vdd, max(0, 10 - index), max(1, 18 - index)) for index, vdd in enumerate((1.1, 1.05, 1.0, 0.95, 0.9, 0.85, 0.8))]
        qualified, summary = analysis.qualify_candidates(anchors, coarse)
        self.assertEqual(summary["eligible_phase_ids"], ["phi_p00"])
        self.assertEqual(qualified[0]["phase_id"], "phi_p00")
        anchors[-1]["valid"] = "0"
        _, failed = analysis.qualify_candidates(anchors, coarse)
        self.assertEqual(failed["eligible_phase_ids"], [])

    def test_blind_intervals_keep_detection_flags_paired_when_input_is_unsorted(self):
        """Local refined onsets may be unsorted, but their flags must not move to another bin."""

        intervals = analysis.blind_intervals([2.0, 0.0, 1.0], [True, False, False])
        self.assertEqual(len(intervals), 1)
        self.assertEqual(intervals[0]["start_s"], 0.0)
        self.assertEqual(intervals[0]["end_s"], 2.0)

    def test_pair_union_and_jitter_envelope_are_not_single_phase_metrics(self):
        """A pair detects when either same-launch observation detects, then applies its own envelope."""

        records = []
        for onset, a, b in ((0.0, 1, 0), (1.0, 0, 1), (2.0, 0, 0)):
            first = row("phi_m01", -1, 2.86e-10, 1.1, 10, 18, onset=onset)
            second = row("phi_p01", 1, 3.14e-10, 1.1, 11, 19, onset=onset)
            first["encoded_state_changed"] = str(a)
            second["encoded_state_changed"] = str(b)
            records.extend((first, second))
        ranked = analysis.rank_phase_sets(records, ["phi_m01", "phi_p01"], "encoded_state_changed")
        pair = next(item for item in ranked if item["phase_count"] == 2)
        self.assertEqual(pair["case_summaries"][0]["detection_fraction"], 2.0 / 3.0)
        baselines = {"phases": [
            {"phase_id": "phi_m01", "start_index": 10, "end_index": 18},
            {"phase_id": "phi_p01", "start_index": 11, "end_index": 19},
        ]}
        jitter = [
            row("phi_m01", -1, 2.86e-10, 1.1, 10, 18),
            row("phi_m01", -1, 2.86e-10, 1.1, 10, 19),
            row("phi_p01", 1, 3.14e-10, 1.1, 11, 19),
            row("phi_p01", 1, 3.14e-10, 1.1, 11, 20),
        ]
        # Each synthetic group has a zero-offset nominal and a perturbed
        # capture, matching the physical runner's phase-jitter CSV contract.
        jitter[0]["phase_offset_s"] = "0.0"
        jitter[1]["phase_offset_s"] = "1e-12"
        jitter[2]["phase_offset_s"] = "0.0"
        jitter[3]["phase_offset_s"] = "1e-12"
        envelope = analysis.jitter_summary(jitter, baselines)
        self.assertEqual(envelope["groups"][0]["maximum_boundary_distance"], 1)
        records[0]["start_index"] = "12"
        scored = analysis.apply_jitter_envelope(records, baselines, envelope)
        self.assertEqual(scored[0]["jitter_aware_detected"], 1)

    def test_sequential_summary_never_reports_same_launch_union(self):
        """A/B interleaving averages the phase assigned to an event, not an OR of both phases."""

        records = []
        for onset, a, b in ((0.0, 1, 0), (1.0, 0, 1)):
            first = row("phi_m01", -1, 2.86e-10, 1.1, 10, 18, onset=onset)
            second = row("phi_p01", 1, 3.14e-10, 1.1, 11, 19, onset=onset)
            first["jitter_aware_detected"] = str(a)
            second["jitter_aware_detected"] = str(b)
            records.extend((first, second))
        result = analysis.sequential_schedule_summary(records, ["phi_m01", "phi_p01"], 6e-9)["results"][0]
        self.assertTrue(result["same_launch_union_not_used"])
        self.assertEqual(result["single_event_detection_fraction_unknown_parity"], 0.5)
        self.assertIsNone(result["persistent_two_cycle_coverage"])


if __name__ == "__main__":
    unittest.main()
