#!/usr/bin/env python3
"""Deterministic, simulator-free regression for the B-FE7 waveform contract.

These tests exercise the public stimulus boundary only.  The generated
include must expose exactly one positive monitored rail (`vdd_monitored`) and
one local return (`vss_a`); detector/backend behavior is intentionally absent
and therefore cannot be validated or inferred here.
"""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[1]
BFE7_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe7_droop12_waveforms"
sys.path.insert(0, str(BFE7_ROOT))
import generate_droop12_waveforms as generator  # noqa: E402
import validate_droop12_waveforms as validator  # noqa: E402


class Bfe7Droop12Test(unittest.TestCase):
    """Protect the immutable twelve-scenario offline stimulus package."""

    def test_contract_and_manifest_are_frozen_with_zero_runs(self):
        """The package gate must freeze inputs without claiming circuit results."""

        contract = json.loads((BFE7_ROOT / "DROOP12_WAVEFORM_CONTRACT.json").read_text())
        manifest = json.loads((BFE7_ROOT / "DROOP12_MANIFEST.json").read_text())
        self.assertTrue(contract["frozen"])
        self.assertEqual(len(contract["scenarios"]), 12)
        self.assertEqual(manifest["simulation_accounting"]["hspice_runs"], 0)
        self.assertEqual(manifest["simulation_accounting"]["arch0_tests"], 0)
        self.assertEqual(manifest["simulation_accounting"]["arch1_tests"], 0)

    def test_every_source_has_the_modular_monitored_port_contract(self):
        """Each include has one supply source and no detector circuitry."""

        for path in sorted((BFE7_ROOT / "waveforms").glob("*.inc")):
            points = validator.parse_inc(path)
            self.assertGreater(len(points), 2)
            text = path.read_text(encoding="ascii")
            self.assertEqual(text.count("V_VDD_MONITORED vdd_monitored vss_a PWL("), 1)
            electrical = "\n".join(line.split("*", 1)[0] for line in text.splitlines()).lower()
            for token in ("backend", "detector", "sensor", "latq", "dff", "arch0", "arch1"):
                self.assertNotIn(token, electrical)

    def test_d10_d11_mirror_and_d07_d08_d12_geometry(self):
        """High-signal attack semantics remain exactly those frozen in W2."""

        contract = json.loads((BFE7_ROOT / "DROOP12_WAVEFORM_CONTRACT.json").read_text())
        by_id = {record["scenario_id"]: record for record in contract["scenarios"]}
        d10 = by_id["D10"]["attack_breakpoints_ps"]
        d11 = by_id["D11"]["attack_breakpoints_ps"]
        self.assertEqual(sorted([[42000 - t, value] for t, value in d10]), sorted(d11))
        self.assertEqual(validator._attack_value(by_id["D12"]["attack_breakpoints_ps"], 21000), 0.03)
        self.assertEqual(validator._attack_value(by_id["D12"]["attack_breakpoints_ps"], 31000), 0.03)
        for scenario_id, count in (("D07", 2), ("D08", 4)):
            points = by_id[scenario_id]["attack_breakpoints_ps"]
            starts = [t for index, (t, value) in enumerate(points)
                      if value > 0 and (index == 0 or points[index - 1][1] == 0)]
            self.assertEqual(len(starts), count)
            self.assertTrue(all(b - a == 10000 for a, b in zip(starts, starts[1:])))

    def test_regeneration_is_byte_identical(self):
        """The canonical PCG64 background and all W3 files must not drift."""

        with tempfile.TemporaryDirectory(prefix="bfe7_test_") as temporary:
            output = Path(temporary)
            generator.main(["--output-dir", str(output), "--contract", str(BFE7_ROOT / "DROOP12_WAVEFORM_CONTRACT.json")])
            for relative in ("normal_background/NBG_7301.csv", "normal_background/NBG_7301.inc"):
                self.assertEqual(hashlib.sha256((BFE7_ROOT / relative).read_bytes()).hexdigest(),
                                 hashlib.sha256((output / relative).read_bytes()).hexdigest())
            for source in sorted((BFE7_ROOT / "waveforms").glob("*.csv")):
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                                 hashlib.sha256((output / "waveforms" / source.name).read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
