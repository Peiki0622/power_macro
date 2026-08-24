"""Zero-HSPICE regression checks for the D0-BR shared-sensor hard gate.

These tests deliberately exercise only compact evidence and pure Python
classification logic.  They never invoke the BR1 runner, so they cannot
consume its strictly limited two-scenario transistor-level allowance.
"""

import json
import sys
import unittest
from pathlib import Path


# Import the task runner directly from the local FTC script directory.  This
# mirrors the existing D0-A regression convention and keeps simulation launch
# authority exclusively in the explicit runner command, not in unit tests.
FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import run_d0_interleaved_capture as study  # noqa: E402


def synthetic_result(raw_second_rise_s=3.8e-9, raw_third_rise_s=None, raw_prelaunch_ratio=0.0):
    """Build one two-launch scalar result with independently controllable faults.

    HSPICE reports times in seconds.  The values below model two clean events:
    launch0 at 1.49 ns, first event completed by 2.40 ns, and launch1 at
    3.565 ns.  Individual tests alter only the raw-CK behaviour so a failure
    reason remains attributable to the shared sensing path rather than a test
    fixture ambiguity.
    """

    launch0, launch1 = 1.49e-9, 3.565e-9
    timing = {"launch0_s": launch0, "fall0_s": 3.18e-9, "launch1_s": launch1, "prelaunch_s": launch1 - 1e-12,
              "stop_s": 5.1e-9, "fall_offset_ps": 1690.0}
    measurements = {}
    for short, rise0, rise1 in (("xor", 1.90e-9, 3.70e-9), ("medium", 2.05e-9, 3.75e-9), ("raw_ck", 2.20e-9, raw_second_rise_s)):
        measurements["b1_{}_rise1".format(short)] = rise0
        measurements["b1_{}_rise2".format(short)] = rise1
        measurements["b1_{}_rise3".format(short)] = raw_third_rise_s if short == "raw_ck" else None
        measurements["b1_{}_fall1".format(short)] = 2.40e-9
        measurements["b1_{}_fall2".format(short)] = 4.20e-9
        measurements["b1_{}_prelaunch".format(short)] = raw_prelaunch_ratio if short == "raw_ck" else 0.0
        measurements["b1_{}_vdd_prelaunch".format(short)] = 1.0
    return {
        "spec": {"scenario_key": "unit", "baseline_vdd_v": 0.95, "Vdroop_v": 0.86},
        "parameters": {"M_det": 5, "F_det": 6},
        "timing": timing,
        "scenario_path": "task-owned/unit",
        "deck_sha256": "unit",
        "measurements": measurements,
    }


class D0InterleavedCaptureTests(unittest.TestCase):
    """Protect the no-capture-bank-before-BR1 sequencing invariant."""

    def test_br0_binds_the_authoritative_d0a_t0_and_rf_conditions(self):
        """BR0 must preserve the hard timing limits rather than infer a new cadence."""

        baseline = json.loads((FTC_ROOT / "analysis/d0_interleaved_capture/baseline/frozen_input_sha256.json").read_text())
        self.assertEqual(baseline["gate"], "D0_BR_BASELINE_READY")
        self.assertEqual(baseline["authority_state"]["d0a_decision"], "ARCHITECTURE_ESCALATION_REQUIRED")
        self.assertEqual(baseline["authority_state"]["t0_pmax_coverage_ps"], study.RUNTIME_PERIOD_PS)
        self.assertIsNone(baseline["authority_state"]["p_lane_verified_ps"])
        self.assertEqual(baseline["authority_state"]["dff_timing_checks_ns"]["minimum_ck_high_width_ns"], 1.0)
        self.assertEqual(baseline["simulation_accounting"]["new_hspice_scenarios"], 0)

    def test_clean_two_event_result_is_shared_sensor_go(self):
        """Exactly two edge sequences and positive D-ref permit only the BR2 route."""

        result = study.classify_br1(synthetic_result())
        self.assertEqual(result["gate"], "SHARED_SENSOR_CADENCE_GO")
        self.assertEqual(result["d_ref_ps"]["probe1"], 100.0)
        self.assertEqual(result["nodes"]["raw_ck"]["rise_count_observed"], 2)
        self.assertGreaterEqual(result["nodes"]["raw_ck"]["rearm_margin_ps"], study.EDGE_GUARD_PS)

    def test_falling_induced_third_raw_edge_is_a_hard_fail(self):
        """An extra raw edge cannot be hidden by holding the capture DFF reset."""

        result = study.classify_br1(synthetic_result(raw_third_rise_s=4.5e-9))
        self.assertEqual(result["gate"], "SHARED_SENSOR_CADENCE_FAIL")
        self.assertIn("raw_ck_rise_count_is_3_not_2", result["structural_failures"])

    def test_early_second_raw_edge_is_a_hard_fail(self):
        """A fall-wave edge before the second launch is not a valid probe-1 event."""

        result = study.classify_br1(synthetic_result(raw_second_rise_s=3.4e-9))
        self.assertEqual(result["gate"], "SHARED_SENSOR_CADENCE_FAIL")
        self.assertIn("raw_ck_second_rise_not_after_second_launch", result["structural_failures"])

    def test_sub_guard_rearm_margin_is_timing_fragile_not_go(self):
        """A clean-looking event with less than 25 ps recovery is not robust closure."""

        result = synthetic_result()
        result["measurements"]["b1_raw_ck_fall1"] = result["timing"]["launch1_s"] - 10e-12
        classified = study.classify_br1(result)
        self.assertEqual(classified["gate"], "SHARED_SENSOR_TIMING_FRAGILE")
        self.assertIn("raw_ck_rearm_margin_below_25.0ps", classified["fragile_reasons"])

    def test_repeated_deck_has_two_launches_one_fall_and_no_new_capture_topology(self):
        """Deck rendering must expose BR1 edges without adding a bank or legalizer.

        This is intentionally a pure renderer check.  It protects the exact
        five-field edge measures that HSPICE consumes, while avoiding a test
        path that would launch the simulator or create a run directory.
        """

        spec = study.BR1_SPECS[0]
        parameters = study.t0.parameters_for(
            spec["baseline_vdd_v"], spec["margin_level"], spec["Vdroop_v"], spec["hold_ps"], spec["phase_ps"])
        deck, timing = study.render_br1_deck(study.t0.frozen_context(), parameters, study.br1_fall_offset_ps())
        self.assertIn("XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset DFFRPQ_X0P5M_A9TR40", deck)
        self.assertNotIn("LEGALIZER", deck)
        self.assertNotIn("BANK_A", deck)
        self.assertNotIn("\n.\n", deck)
        self.assertIn("RISE=2", deck)
        self.assertIn("b1_raw_ck_rise3", deck)
        self.assertLess(timing["launch0_s"], timing["fall0_s"])
        self.assertLess(timing["fall0_s"], timing["launch1_s"])

    def test_published_br1_failure_never_authorizes_capture_banks(self):
        """A shared-sensor FAIL is terminal evidence, not a partial two-bank GO."""

        br1 = json.loads((FTC_ROOT / "analysis/d0_interleaved_capture/br1_shared_sensor_cadence/shared_sensor_cadence_contract.json").read_text())
        contract = json.loads((FTC_ROOT / "analysis/d0_interleaved_capture/contract/D0_INTERLEAVED_CAPTURE_CONTRACT.json").read_text())
        gate = json.loads((FTC_ROOT / "analysis/d0_interleaved_capture/reports/D0_BR_GATE_STATUS.json").read_text())
        self.assertEqual(br1["gate"], "SHARED_SENSOR_CADENCE_FAIL")
        self.assertEqual(br1["simulation_accounting"]["new_hspice_scenarios"], 2)
        self.assertEqual(contract["decision"], "SHARED_SENSOR_CADENCE_FAIL")
        self.assertIsNone(contract["shared_sensor_cadence"]["p_sensor_verified_ps"])
        self.assertFalse(contract["preserved_contracts"]["capture_bank_created"])
        self.assertEqual(gate["terminal_stage"], "D0-BR1")
        self.assertIn("capture_event_legalizer", gate["forbidden_after_failure"])


if __name__ == "__main__":
    unittest.main()
