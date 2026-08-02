#!/usr/bin/env python3
"""Exhaustive tests for the authenticated 384x128 CNN weight ROM image."""

from __future__ import print_function

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from power_macro.rtl.cnn_monitor.scripts.generate_smic40ll_rom_content import (
    _load_authenticated_package, build_words, generate)


CNN_ROOT = Path(__file__).resolve().parents[1]
ROM_CONFIG = CNN_ROOT / "config" / "smic40ll_rom_config_v1.json"
RTL_CONFIG = CNN_ROOT / "config" / "cnn_rtl_config_v1.json"


class Smic40llRomContentTest(unittest.TestCase):
    """Prove every physical byte and every authentication failure boundary."""

    @classmethod
    def setUpClass(cls):
        cls.config, _, _, cls.package = _load_authenticated_package(ROM_CONFIG)
        cls.words, cls.rows = build_words(cls.config, cls.package["tensors"])

    def test_every_physical_byte_matches_the_frozen_address_formula(self):
        """Compare all 384 words by 16 lanes, including every forced zero."""

        layer_by_address = {}
        for item in self.config["address_map"]:
            for address in range(item["first_address"], item["last_address"] + 1):
                layer_by_address[address] = item
        for address in range(384):
            for lane in range(16):
                if address >= 370:
                    expected = 0
                else:
                    item = layer_by_address[address]
                    relative = address - item["first_address"]
                    group_span = item["input_channels"] * 5
                    group = relative // group_span
                    within_group = relative % group_span
                    input_channel = within_group // 5
                    kernel_tap = within_group % 5
                    output_channel = group * 16 + lane
                    expected = (int(self.package["tensors"][item["tensor"]][
                        output_channel, input_channel, kernel_tap]) & 0xff
                                if output_channel < 18 else 0)
                self.assertEqual(self.words[address][lane], expected,
                                 "address {} lane {}".format(address, lane))

    def test_rcf_lane_zero_is_the_rightmost_byte_and_generation_repeats(self):
        """Two clean runs must be byte-identical and preserve Q slice order."""

        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            generate(ROM_CONFIG, first)
            generate(ROM_CONFIG, second)
            first_rcf = (first / "CNNW384X128.rcf").read_bytes()
            second_rcf = (second / "CNNW384X128.rcf").read_bytes()
            self.assertEqual(first_rcf, second_rcf)
            lines = first_rcf.decode("ascii").splitlines()
            self.assertEqual(len(lines), 384)
            self.assertTrue(all(len(line) == 128 for line in lines))
            for address, line in enumerate(lines):
                self.assertEqual(int(line[-8:], 2), self.words[address][0])
                self.assertEqual(int(line[:8], 2), self.words[address][15])

    def test_bad_package_digest_fails_before_output_directory_creation(self):
        """A mismatched binding cannot leave even a partial compiler input."""

        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            bad_rtl = temporary / "bad_rtl_config.json"
            payload = json.loads(RTL_CONFIG.read_text(encoding="utf-8"))
            payload["task1_binding"]["manifest_sha256"] = "0" * 64
            bad_rtl.write_text(json.dumps(payload), encoding="ascii")
            output = temporary / "must_not_exist"
            with self.assertRaisesRegex(ValueError, "manifest digest mismatch"):
                generate(ROM_CONFIG, output, bad_rtl)
            self.assertFalse(output.exists())

    def test_manifest_authenticates_rcf_and_complete_address_map(self):
        """Generated manifest must bind both machine-consumed content files."""

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "image"
            manifest = generate(ROM_CONFIG, output)
            for name in ("CNNW384X128.rcf", "address_map.csv"):
                path = output / name
                observed = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(manifest["files"][name]["sha256"], observed)
            self.assertEqual(manifest["content_layout"]["coefficient_count"],
                             3330)


if __name__ == "__main__":
    unittest.main()
