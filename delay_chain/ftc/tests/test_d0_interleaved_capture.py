"""Zero-HSPICE regression checks for BR1 fixed-fall and BR1R wavefront gates.

These tests inspect only pure-Python classifications, rendered strings and
compact reviewed records.  They intentionally never call a runner phase, so
the six-scenario BR1R transistor-level allowance remains under the explicit
user-facing command rather than being hidden in a unit-test side effect.
"""

import json
import sys
import unittest
from pathlib import Path


# Import the task runner directly from the local FTC script directory.  This
# matches the established D0-A convention while keeping all simulator launch
# authority in an explicit command-line phase, not in regression discovery.
FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_d0_interleaved_capture as study  # noqa: E402


def synthetic_wavefront_result(prefix="b1r", overlap=False, dref_shift_ps=0.0):
    """Build a three-wavefront trace without source-completion windows.

    EF remains active in downstream stages when source rise1 occurs.  The
    fixture nevertheless has clean E0/EF/E1 pulse separation at every node,
    which is the physically relevant repeated-probe condition.
    """

    rise0, fall0, rise1, stop = 1.49e-9, 2.49e-9, 3.00e-9, 5.20e-9
    timing = {
        "launch0_s": rise0,
        "fall0_s": fall0,
        "launch1_s": rise1,
        "prelaunch_s": rise1 - 1.0e-12,
        "stop_s": stop,
        "fall_offset_ps": 1000.0,
    }
    values = {
        "{}_sclk_rise0".format(prefix): rise0,
        "{}_sclk_fall0".format(prefix): fall0,
        "{}_sclk_rise1".format(prefix): rise1,
    }
    # Each tuple is (E0 rise/fall, EF rise/fall, E1 rise/fall).  E1 source
    # launch intentionally precedes EF's medium/raw falls, but E1 reaches each
    # node only after EF has ended at that same node.
    events = {
        "xor": ((1.90e-9, 2.15e-9), (2.75e-9, 3.05e-9), (3.60e-9, 3.85e-9)),
        "medium": ((2.00e-9, 2.25e-9), (2.85e-9, 3.20e-9), (3.70e-9, 3.95e-9)),
        "raw_ck": ((2.20e-9, 2.40e-9), (3.05e-9, 3.40e-9),
                   (3.90e-9 + dref_shift_ps * 1.0e-12, 4.15e-9 + dref_shift_ps * 1.0e-12)),
    }
    if overlap:
        # EF reaches raw CK before E0 falls there.  The same-node pulse train
        # is then merged/overlapped even though source-edge order is valid.
        events["raw_ck"] = ((2.20e-9, 3.10e-9), (3.05e-9, 3.40e-9), events["raw_ck"][2])
    for node, node_events in events.items():
        rises = [event[0] for event in node_events]
        falls = [event[1] for event in node_events]
        for index in range(1, study.BR1R_MEASURED_EDGE_LIMIT + 1):
            values["{}_{}_rise{}".format(prefix, node, index)] = rises[index - 1] if index <= len(rises) else None
            values["{}_{}_fall{}".format(prefix, node, index)] = falls[index - 1] if index <= len(falls) else None
        values["{}_{}_prelaunch".format(prefix, node)] = 0.0
        values["{}_{}_vdd_prelaunch".format(prefix, node)] = 1.0
    return {
        "spec": {"scenario_key": "unit", "baseline_vdd_v": 0.95, "Vdroop_v": 0.86},
        "parameters": {"M_det": 5, "F_det": 6},
        "timing": timing,
        "scenario_path": "task-owned/unit",
        "deck_sha256": "unit",
        "fall_offset_ps": 1000.0,
        "measurements": values,
    }


class D0InterleavedCaptureTests(unittest.TestCase):
    """Protect the fixed-topology, same-node-wavefront BR1R boundary."""

    def test_br0_binds_the_authoritative_d0a_t0_and_rf_conditions(self):
        """BR0 must retain hard source authority instead of deriving a new cadence."""

        baseline = json.loads((FTC_ROOT / "analysis/d0_interleaved_capture/baseline/frozen_input_sha256.json").read_text())
        self.assertEqual(baseline["gate"], "D0_BR_BASELINE_READY")
        self.assertEqual(baseline["authority_state"]["d0a_decision"], "ARCHITECTURE_ESCALATION_REQUIRED")
        self.assertEqual(baseline["authority_state"]["t0_pmax_coverage_ps"], study.RUNTIME_PERIOD_PS)
        self.assertIsNone(baseline["authority_state"]["p_lane_verified_ps"])
        self.assertEqual(baseline["authority_state"]["dff_timing_checks_ns"]["minimum_ck_high_width_ns"], 1.0)
        self.assertEqual(baseline["simulation_accounting"]["new_hspice_scenarios"], 0)

    def test_same_node_separation_passes_when_ef_is_downstream_at_source_rise1(self):
        """Source rise1 need not wait for EF to return at later delay stages."""

        result = study.wavefront_separation_analysis(
            synthetic_wavefront_result(), "b1r", study.BR1R_MEASURED_EDGE_LIMIT,
            study.BR1R_MEASURED_EDGE_LIMIT, True)
        self.assertEqual(result["gate"], "WAVEFRONT_SEPARATION_PASS")
        self.assertEqual([row["id"] for row in result["wavefronts"]], ["E0", "EF", "E1"])
        self.assertEqual(result["wavefronts"][2]["d_ref_ps"], 300.0)
        self.assertFalse(result["rise1_prelaunch_snapshot"]["used_for_gate"])
        self.assertGreater(result["same_node_separation"]["raw_ck"][1]["low_gap_ps"], 0.0)

    def test_same_node_overlap_is_a_wavefront_collision(self):
        """A next rise before the previous same-node fall is a real collision."""

        result = study.wavefront_separation_analysis(
            synthetic_wavefront_result(overlap=True), "b1r", study.BR1R_MEASURED_EDGE_LIMIT,
            study.BR1R_MEASURED_EDGE_LIMIT, True)
        self.assertEqual(result["gate"], "WAVEFRONT_SEPARATION_FAIL")
        self.assertIn("raw_ck_E0_to_EF_pulses_overlap_or_merge", result["failures"])

    def test_dref_variation_is_reported_not_qualified_by_t0_phase_resolution(self):
        """A positive, separated 50 ps D_ref change is not a collision by itself."""

        result = study.wavefront_separation_analysis(
            synthetic_wavefront_result(dref_shift_ps=50.0), "b1r", study.BR1R_MEASURED_EDGE_LIMIT,
            study.BR1R_MEASURED_EDGE_LIMIT, True)
        self.assertEqual(result["gate"], "WAVEFRONT_SEPARATION_PASS")
        self.assertEqual(result["d_ref_variation"]["delta_from_E0_ps"]["E1"], 50.0)
        self.assertIsNone(result["d_ref_variation"]["allowed_drift_limit_ps"])
        self.assertEqual(result["d_ref_variation"]["classification"],
                         "TRANSIENT_PHYSICAL_DELAY_VARIATION_WITHOUT_WAVEFRONT_COLLISION")

    def test_fixed_br1_classification_reports_partial_wavefront_observation(self):
        """The two-fall retained endpoint is incomplete, not a false collision."""

        result = synthetic_wavefront_result(prefix="b1")
        # Retained BR1 records only three rises/two falls; remove the extra
        # observability keys to reproduce that exact historical interface.
        for node in ("xor", "medium", "raw_ck"):
            for index in range(4, study.BR1R_MEASURED_EDGE_LIMIT + 1):
                result["measurements"].pop("b1_{}_rise{}".format(node, index), None)
            for index in range(3, study.BR1R_MEASURED_EDGE_LIMIT + 1):
                result["measurements"].pop("b1_{}_fall{}".format(node, index), None)
        classified = study.classify_br1(result)
        self.assertEqual(classified["gate"], "SHARED_SENSOR_CADENCE_EVIDENCE_INCOMPLETE")
        self.assertIn("E1_raw_ck_fall_not_observed", classified["wavefront_analysis"]["incomplete_observations"])

    def test_br1r_offsets_are_rederived_from_retained_probe0_delays(self):
        """The three approved source widths must remain data-derived and finite."""

        fixed = []
        for scenario_key in ("low", "high"):
            fixed.append({
                "scenario_key": scenario_key,
                "wavefront_analysis": {
                    "measured_source_edges_s": {"rise0_s": 1.0e-9},
                    "wavefronts": [{"nodes": {
                        "xor": {"rise_s": 1.65e-9},
                        "raw_ck": {"rise_s": 2.15e-9},
                    }}],
                },
            })
        rationale = study.br1r_offset_rationale(fixed)
        self.assertEqual(rationale["approved_common_fall_offsets_ps"], [750.0, 1000.0, 1250.0])
        self.assertEqual(rationale["slowest_probe0_raw_ck_rise_delay_ps"], 1150.0)

    def test_br1r_deck_keeps_real_ports_and_adds_six_crossing_observability(self):
        """Retiming may change fall0 only; it must not add a capture topology."""

        spec = study.BR1_SPECS[0]
        parameters = study.t0.parameters_for(
            spec["baseline_vdd_v"], spec["margin_level"], spec["Vdroop_v"], spec["hold_ps"], spec["phase_ps"])
        deck, timing = study.render_br1r_deck(study.t0.frozen_context(), parameters, 1000.0)
        self.assertIn("XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset DFFRPQ_X0P5M_A9TR40", deck)
        self.assertIn("b1r_raw_ck_rise6", deck)
        self.assertIn("b1r_raw_ck_fall6", deck)
        self.assertNotIn("LEGALIZER", deck)
        self.assertNotIn("BANK_A", deck)
        self.assertNotIn("\n.\n", deck)
        self.assertLess(timing["launch0_s"], timing["fall0_s"])
        self.assertLess(timing["fall0_s"], timing["launch1_s"])
        self.assertEqual(round((timing["launch1_s"] - timing["launch0_s"]) * 1.0e12, 6), study.RUNTIME_PERIOD_PS)

    def test_published_br1r_wavefront_go_authorizes_only_br2_research(self):
        """Separated retained wavefronts revoke the false physical block only."""

        br1 = json.loads((FTC_ROOT / "analysis/d0_interleaved_capture/br1_shared_sensor_cadence/shared_sensor_cadence_contract.json").read_text())
        br1r = json.loads((FTC_ROOT / "analysis/d0_interleaved_capture/br1r_fall_retiming/retiming_search_contract.json").read_text())
        contract = json.loads((FTC_ROOT / "analysis/d0_interleaved_capture/contract/D0_INTERLEAVED_CAPTURE_CONTRACT.json").read_text())
        gate = json.loads((FTC_ROOT / "analysis/d0_interleaved_capture/reports/D0_BR_GATE_STATUS.json").read_text())
        self.assertEqual(br1["gate"], "SHARED_SENSOR_TIMING_FRAGILE")
        self.assertEqual(br1r["decision"], "SHARED_SENSOR_CADENCE_RETIMING_GO")
        self.assertEqual(br1r["simulation_accounting"]["new_hspice_scenarios"], 0)
        self.assertEqual(br1r["simulation_accounting"]["reparsed_hspice_scenarios"], 8)
        self.assertEqual(br1r["retained_physical_evidence"]["historical_distinct_hspice_scenarios"], 8)
        self.assertEqual([row["fall_offset_ps"] for row in br1r["candidate_summary"]], [750.0, 1000.0, 1250.0])
        self.assertTrue(all(row["gate"] == "WAVEFRONT_SEPARATION_PASS" for row in br1r["candidate_summary"]))
        self.assertEqual(br1r["selected_common_fall_offset_ps"], 1000.0)
        preferred = next(row for row in br1r["candidate_summary"] if row["fall_offset_ps"] == 1250.0)
        self.assertGreater(preferred["minimum_same_node_low_gap_ps"], study.WAVEFRONT_LOW_GAP_MARGIN_PS)
        self.assertEqual(contract["decision"], "SHARED_SENSOR_CADENCE_RETIMING_GO")
        self.assertEqual(contract["shared_sensor_cadence"]["p_sensor_verified_ps"], study.RUNTIME_PERIOD_PS)
        self.assertFalse(contract["preserved_contracts"]["capture_event_legalizer_created"])
        self.assertFalse(contract["preserved_contracts"]["capture_bank_created"])
        self.assertFalse(contract["preserved_contracts"]["runtime_rtl_created"])
        self.assertEqual(gate["next_permitted_stage"], "D0-BR2_capture_event_legalizer_research")
        self.assertIn("capture_bank", gate["forbidden_before_BR2_gate"])


if __name__ == "__main__":
    unittest.main()
