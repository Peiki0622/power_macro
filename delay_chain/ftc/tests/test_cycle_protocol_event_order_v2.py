"""Zero-HSPICE regression for the corrected FTC event-order timing contract.

The test imports only the pure v2 audit/scheduling module.  It does not render
a SPICE deck, invoke HSPICE, or inspect a pre-existing simulation result, so a
passing result proves the intended structural contract only.  Physical DFF CK
edge integrity remains the later Phase 1R4 HSPICE responsibility.
"""

import importlib.util
import unittest
from pathlib import Path


# The builder deliberately lives beside its generated evidence.  Loading it by
# path keeps this test independent of Python package layout in the EDA tree.
FTC_ROOT = Path(__file__).resolve().parents[1]
BUILDER = FTC_ROOT / "controller" / "analysis" / "cycle_protocol_event_order_v2" / "build_cycle_protocol_event_order_v2.py"

SPEC = importlib.util.spec_from_file_location("ftc_cycle_protocol_event_order_v2", BUILDER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load event-order v2 builder")
study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study)


class EventOrderedCycleProtocolV2Test(unittest.TestCase):
    """Validate every R2 structural invariant from immutable inputs in memory."""

    @classmethod
    def setUpClass(cls):
        """Build an in-memory R0/R1 view without creating deck or run artefacts."""

        cls.audit, _, cls.manifest = study.audit_exact_paths()
        cls.template = study.solve_local_template(cls.audit)
        cls.phase0 = study.read_json(study.PHASE0_CONTRACT)
        cls.schedules = {
            voltage: study.build_schedule(cls.phase0["scenarios"][voltage], cls.template, cls.audit)
            for voltage in study.VOLTAGES
        }

    def test_rejected_v1_schedule_is_explicitly_order_invalid(self):
        """Lock the concrete defect: v1 fell S_CLK before reset assertion."""

        # Read the preserved historical contract rather than duplicating its
        # cycle values in this test.  The strict predicate below is exactly
        # the rule which the v2 contract must satisfy for every probe.
        v1_path = study.FTC_ROOT / "controller" / "analysis" / "cycle_protocol" / "cycle_path_0p95_contract.json"
        v1 = study.read_json(v1_path)
        self.assertEqual(v1["timing"]["sclk_high_cycles"], 3)
        for probe in v1["probes"]:
            with self.subTest(probe=probe["probe_index"]):
                self.assertFalse(probe["sample_2_cycle"] < probe["reset_assert_cycle"] < probe["sclk_fall_cycle"])
                self.assertLess(probe["sclk_fall_cycle"], probe["reset_assert_cycle"])

    def test_audit_and_solver_prove_the_single_earliest_template(self):
        """Require R0 GO, all physical inequalities, and the derived v2 cycles."""

        self.assertEqual(self.audit["decision"], "Exact-Path Event Order Extraction = GO")
        self.assertTrue(all(self.template["constraints_satisfied"].values()))
        self.assertTrue(self.template["earliest_solution_matches_expected"])
        self.assertEqual(
            self.template["controller_action_cycles"],
            {
                "RESET_RELEASE": 0,
                "S_CLK_RISE": 1,
                "Q_SAMPLE_1": 4,
                "Q_SAMPLE_2": 5,
                "RESET_ASSERT": 6,
                "S_CLK_FALL": 7,
                "RECOVERY_DONE": 10,
            },
        )

    def test_each_probe_obeys_all_order_and_count_constraints(self):
        """Check all generated probes rather than sampling one voltage or one code."""

        for voltage, schedule in self.schedules.items():
            self.assertTrue(all(schedule["checks"].values()), voltage)
            for probe in schedule["probes"]:
                with self.subTest(voltage=voltage, probe=probe["probe_index"]):
                    self.assertLess(probe["reset_release_cycle"], probe["sclk_rise_cycle"])
                    self.assertLess(probe["sclk_rise_cycle"], probe["sample_1_cycle"])
                    self.assertLess(probe["sample_1_cycle"], probe["sample_2_cycle"])
                    self.assertLess(probe["sample_2_cycle"], probe["reset_assert_cycle"])
                    self.assertLess(probe["reset_assert_cycle"], probe["sclk_fall_cycle"])
                    self.assertLess(probe["sclk_fall_cycle"], probe["recovery_done_cycle"])
                    self.assertEqual(probe["sample_2_cycle"] - probe["sample_1_cycle"], 1)
                    self.assertGreaterEqual(probe["sample_1_cycle"] - probe["sclk_rise_cycle"], 3)

    def test_probe_codes_remain_constant_and_updates_remain_single_step(self):
        """Keep M/F changes outside probes and retain the frozen thermometer walk."""

        for voltage, schedule in self.schedules.items():
            operations = schedule["operations"]
            for probe in schedule["probes"]:
                operation = operations[probe["operation_index"]]
                with self.subTest(voltage=voltage, probe=probe["probe_index"]):
                    self.assertEqual((probe["M"], probe["F"]), (operation["M_before"], operation["F_before"]))
                    self.assertEqual((operation["M_before"], operation["F_before"]), (operation["M_after"], operation["F_after"]))
            for transition in schedule["transitions"]:
                with self.subTest(voltage=voltage, operation=transition["operation_index"]):
                    self.assertEqual(abs(transition["M_after"] - transition["M_before"]) + abs(transition["F_after"] - transition["F_before"]), 1)
                    self.assertEqual(transition["settle_done_cycle"] - transition["update_cycle"], 2)

    def test_voltage_trajectories_share_template_and_frozen_outcomes(self):
        """Verify the unchanged functional trajectories and exactly three scenarios."""

        expected = {
            "0p80": (45, {"M": 7, "F": 6}),
            "0p95": (36, {"M": 4, "F": 6}),
            "1p10": (36, {"M": 2, "F": 9}),
        }
        first_template = None
        for voltage, (operation_count, final_code) in expected.items():
            schedule = self.schedules[voltage]
            self.assertEqual(len(schedule["operations"]), operation_count)
            self.assertEqual(self.phase0["scenarios"][voltage]["final_locked_code"], final_code)
            template = [
                (
                    probe["sclk_rise_cycle"] - probe["reset_release_cycle"],
                    probe["sample_1_cycle"] - probe["reset_release_cycle"],
                    probe["sample_2_cycle"] - probe["reset_release_cycle"],
                    probe["reset_assert_cycle"] - probe["reset_release_cycle"],
                    probe["sclk_fall_cycle"] - probe["reset_release_cycle"],
                    probe["recovery_done_cycle"] - probe["reset_release_cycle"],
                )
                for probe in schedule["probes"]
            ]
            self.assertTrue(all(item == template[0] for item in template), voltage)
            first_template = template[0] if first_template is None else first_template
            self.assertEqual(template[0], first_template)
        self.assertEqual(study.SCENARIO_BUDGET, 3)
        self.assertEqual(tuple(self.schedules), ("0p80", "0p95", "1p10"))

    def test_zero_hspice_gate_has_no_result_dependency(self):
        """Document that R2 consumes source evidence and creates no HSPICE result."""

        self.assertEqual(self.manifest["schema_version"], 1)
        self.assertTrue(all("hspice" not in item["name"] for item in self.manifest["inputs"] if item["name"].startswith("exact_schedule")))
        # The builder contains no process execution interface.  This keeps
        # the R2 test valid both before and after the later R4 evidence exists.
        self.assertFalse(hasattr(study, "subprocess"))


if __name__ == "__main__":
    unittest.main()
