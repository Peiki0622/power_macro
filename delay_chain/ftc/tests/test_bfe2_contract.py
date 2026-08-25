"""Zero-HSPICE tests for the B-FE2 latch contract and source audit."""

import sys
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import bfe2_contract  # noqa: E402


class Bfe2ContractTest(unittest.TestCase):
    """Check that B-FE2.0 freezes real library facts before any deck exists."""

    def test_latch_audit_has_required_powered_ports_and_capacitances(self):
        """The real latch must expose physical supply/well and D/G facts."""

        audit = bfe2_contract.audit_latch_cell()
        self.assertEqual(audit["cell"], "LATQ_X0P5M_A9TR40")
        self.assertEqual(audit["cdl_ports"], ["Q", "VDD", "VNW", "VPW", "VSS", "D", "G"])
        self.assertEqual(audit["verilog_powered_ports"], ["Q", "VDD", "VSS", "D", "G"])
        self.assertGreater(audit["liberty"]["inputs"]["D"]["capacitance"], 0.0)
        self.assertGreater(audit["liberty"]["inputs"]["G"]["capacitance"], 0.0)

    def test_contract_keeps_zero_hspice_and_bounded_budgets(self):
        """The contract must not pre-authorize an unbounded analog matrix."""

        contract = bfe2_contract.build_contract()
        self.assertEqual(contract["new_hspice_scenarios"], 0)
        self.assertEqual(contract["scenario_budgets"]["bfe2_1_latch_load"], 4)
        self.assertEqual(contract["scenario_budgets"]["bfe2_2_real_snapshot"], 8)
        self.assertEqual(contract["scenario_budgets"]["bfe2_3_close_aperture_additional"], 16)
        self.assertIn("latch_cell", contract["signature_fields"])


if __name__ == "__main__":
    unittest.main()
