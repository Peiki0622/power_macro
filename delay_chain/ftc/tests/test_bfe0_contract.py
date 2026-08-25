"""Zero-HSPICE regression for the B-FE0 front-end contract.

The tests deliberately inspect source and JSON only.  They ensure that the
new contract is complete, that the selected TL40 library evidence is real,
and that legacy sensor files remain byte-identical to the recorded baseline.
No HSPICE executable is invoked by this test module.
"""

import hashlib
import json
import sys
from pathlib import Path
import unittest


FTC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = FTC_ROOT.parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import bfe0_contract  # noqa: E402


class Bfe0ContractTest(unittest.TestCase):
    """Validate the B-FE0 gate without creating electrical run products."""

    def test_contract_builder_is_zero_hspice_and_complete(self) -> None:
        """The builder must produce the exact planned immutable architecture."""

        contracts = bfe0_contract.build_contracts()
        architecture = contracts["architecture"]
        self.assertEqual(architecture["stage"], "B-FE0")
        self.assertEqual(architecture["observable_taps"], 30)
        self.assertEqual(architecture["rvt_prefix"], 4)
        self.assertEqual(architecture["lvt_prefix"], 0)
        self.assertEqual(architecture["xor_cell"], "XOR2_X0P5M_A9TL40")
        self.assertFalse(architecture["real_latch_instantiated"])
        self.assertFalse(architecture["real_mf_sample_generator"])
        self.assertFalse(architecture["legacy_sensor_modified"])
        self.assertEqual(architecture["new_hspice_scenarios"], 0)
        self.assertEqual(architecture["gate"], "BFE0_FRONTEND_CONTRACT_READY")

    def test_tl40_library_contract_is_real(self) -> None:
        """The planned LVT XOR must have the expected powered CDL interface."""

        cells = bfe0_contract.read_json("delay_chain/ftc/discovery/selected_cells.json")
        evidence = bfe0_contract.validate_library_contract(cells)
        self.assertEqual(evidence["cell"], "XOR2_X0P5M_A9TL40")
        self.assertEqual(evidence["cdl_ports"], ["Y", "VDD", "VNW", "VPW", "VSS", "A", "B"])
        self.assertGreater(len(evidence["cdl_sha256"]), 32)
        self.assertGreater(len(evidence["verilog_sha256"]), 32)

    def test_legacy_hashes_match_the_generated_inventory(self) -> None:
        """Every inherited source hash must still match its recorded file."""

        contracts = bfe0_contract.build_contracts()
        for relative, record in contracts["legacy"]["files"].items():
            path = REPO_ROOT / relative
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, record["sha256"], relative)

    def test_observable_definition_preserves_raw_code(self) -> None:
        """The snapshot contract must expose raw and diagnostic fields."""

        observable = bfe0_contract.build_contracts()["observable"]
        self.assertTrue(observable["threshold_follows_instantaneous_local_supply"])
        self.assertTrue(observable["bit_definition"].startswith("1 iff V(xor_i,t)"))
        self.assertIn("raw_code", observable["derived_fields"])
        self.assertIn("bubble_count", observable["derived_fields"])
        self.assertIn("record_all_equal_length_maximum_runs", observable["main_run_tie_policy"])


if __name__ == "__main__":
    unittest.main()
