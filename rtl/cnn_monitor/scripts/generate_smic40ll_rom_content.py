#!/usr/bin/env python3
"""Generate authenticated SMIC40LL ROM compiler content for CNN weights.

The physical ROM has 384 synchronous-read words and returns sixteen signed
INT8 convolution weights per word.  This script is the only supported bridge
from the accepted task-one parameter package to the compiler RCF.  It loads
the package through the existing digest gate before creating the output
directory, so a stale or modified parameter file cannot leave a plausible but
unauthenticated RCF behind.

RCF lines are written in the memory compiler's documented Q[127:0] display
order: Q[127] is the first character and Q[0] is the final character.  Lane
zero therefore occupies the final eight characters and maps to Q[7:0].
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from pathlib import Path

from power_macro.rtl.cnn_monitor.model.parameter_package import (
    load_parameter_package)


def _sha256(path):
    """Return the lowercase SHA256 digest used in generated manifests."""

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_authenticated_package(rom_config_path, rtl_config_override=None):
    """Load configuration and authenticate every task-one package artifact.

    The ROM configuration names the checked-in RTL configuration relative to
    its own directory.  Tests may supply an alternate RTL configuration to
    prove that a bad manifest digest is rejected before output creation.
    """

    rom_config_path = Path(rom_config_path).resolve()
    rom_config = json.loads(rom_config_path.read_text(encoding="utf-8"))
    rtl_config_path = (Path(rtl_config_override).resolve()
                       if rtl_config_override is not None
                       else rom_config_path.parent / rom_config["rtl_config"])
    rtl_config = json.loads(rtl_config_path.read_text(encoding="utf-8"))
    # The repository root is anchored to the checked-in ROM configuration,
    # not to a test-only RTL-config override that may live in a shallow
    # temporary directory.  config/ is three levels below power_macro.
    power_macro_root = rom_config_path.parents[3]
    binding = rtl_config["task1_binding"]
    package_root = power_macro_root.parent / binding["package_root"]
    package = load_parameter_package(
        package_root, binding["manifest_sha256"],
        binding["quantization_config_sha256"])
    return rom_config, rtl_config_path, rtl_config, package


def build_words(rom_config, tensors):
    """Return the complete 384-by-16 byte image and address metadata.

    Each address represents one output-channel group for one input channel and
    kernel tap.  There are two groups because the network has 18 outputs while
    the physical word holds 16 lanes.  Group one carries channels 0..15;
    group two carries channels 16..17 in lanes 0..1 and forces lanes 2..15 to
    zero.  The closed-form address below is deliberately shared by all layers:

      first + ((group * input_channels + input_channel) * 5 + kernel_tap)

    This makes sequential controller traversal produce addresses 0..369 and
    avoids a synthesis-time weight remapping mux.
    """

    words = [[0 for _ in range(rom_config["lane_count"])]
             for _ in range(rom_config["words"])]
    address_rows = []
    assigned_coefficients = 0

    for layer_config in rom_config["address_map"]:
        tensor = tensors[layer_config["tensor"]]
        input_channels = int(layer_config["input_channels"])
        first_address = int(layer_config["first_address"])
        expected_last = first_address + 2 * input_channels * 5 - 1
        if expected_last != int(layer_config["last_address"]):
            raise ValueError("ROM address range does not match layer dimensions")
        if tuple(tensor.shape) != (18, input_channels, 5):
            raise ValueError("authenticated tensor shape disagrees with ROM map")

        for group in range(2):
            output_base = group * 16
            for input_channel in range(input_channels):
                for kernel_tap in range(5):
                    address = first_address + (
                        (group * input_channels + input_channel) * 5
                        + kernel_tap)
                    for lane in range(16):
                        output_channel = output_base + lane
                        if output_channel < 18:
                            # Store the exact two's-complement byte.  Conversion
                            # back to signed INT8 occurs only in the consumer.
                            words[address][lane] = int(tensor[
                                output_channel, input_channel, kernel_tap]) & 0xff
                            assigned_coefficients += 1
                    address_rows.append({
                        "address": address,
                        "layer": int(layer_config["layer"]),
                        "output_base": output_base,
                        "input_channel": input_channel,
                        "kernel_tap": kernel_tap,
                    })

    if assigned_coefficients != 3330:
        raise ValueError("expected exactly 3330 authenticated CNN coefficients")
    if sorted(row["address"] for row in address_rows) != list(range(370)):
        raise ValueError("valid ROM addresses are not a unique contiguous range")
    if any(any(word) for word in words[370:]):
        raise ValueError("reserved ROM tail must remain zero-filled")
    return words, address_rows


def _rcf_payload(words):
    """Serialize bytes as one MSB-first 128-bit binary row per address."""

    lines = []
    for word in words:
        # Reversing lane order places lane 15 at Q[127:120] on the left and
        # lane 0 at Q[7:0] on the right, matching the compiler manual.
        lines.append("".join(format(value, "08b") for value in reversed(word)))
    return ("\n".join(lines) + "\n").encode("ascii")


def generate(rom_config_path, output_directory, rtl_config_override=None):
    """Authenticate inputs, then atomically create RCF, map, and manifest.

    The caller must provide a path that does not already exist.  Refusing to
    merge with an old directory prevents an earlier compiler input or manifest
    from being mistaken for the current authenticated image.
    """

    rom_config, rtl_config_path, rtl_config, package = (
        _load_authenticated_package(rom_config_path, rtl_config_override))
    words, address_rows = build_words(rom_config, package["tensors"])
    output = Path(output_directory)
    if output.exists():
        raise ValueError("ROM content output directory already exists: {}".format(
            output))
    output.mkdir(parents=True)

    rcf_path = output / "CNNW384X128.rcf"
    rcf_path.write_bytes(_rcf_payload(words))
    map_path = output / "address_map.csv"
    with map_path.open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "address", "layer", "output_base", "input_channel", "kernel_tap",
            "q127_to_q0_hex"))
        writer.writeheader()
        row_by_address = {row["address"]: row for row in address_rows}
        for address, word in enumerate(words):
            metadata = row_by_address.get(address, {
                "layer": 0, "output_base": 0, "input_channel": 0,
                "kernel_tap": 0})
            writer.writerow(dict(metadata, address=address,
                                 q127_to_q0_hex="".join(
                                     format(value, "02x")
                                     for value in reversed(word))))

    binding = rtl_config["task1_binding"]
    manifest = {
        "schema_version": 1,
        "instance_name": rom_config["instance_name"],
        "geometry": {"words": 384, "bits": 128, "mux": 8},
        "content_layout": {
            "valid_addresses": [0, 369],
            "zero_fill_addresses": [370, 383],
            "lane_zero_slice": "Q[7:0]",
            "coefficient_count": 3330,
        },
        "source_authentication": {
            "rtl_config_sha256": _sha256(rtl_config_path),
            "manifest_sha256": binding["manifest_sha256"],
            "quantization_config_sha256": binding[
                "quantization_config_sha256"],
            "checkpoint_sha256": binding["checkpoint_sha256"],
        },
        "files": {
            rcf_path.name: {"bytes": rcf_path.stat().st_size,
                            "sha256": _sha256(rcf_path)},
            map_path.name: {"bytes": map_path.stat().st_size,
                            "sha256": _sha256(map_path)},
        },
    }
    manifest_path = output / "rom_content_manifest.json"
    manifest_path.write_text(json.dumps(
        manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return manifest


def main():
    """Parse explicit input/output paths for reproducible batch generation."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--rtl-config", default=None,
                        help="test-only override for the authenticated RTL config")
    arguments = parser.parse_args()
    generate(arguments.config, arguments.output_directory,
             arguments.rtl_config)


if __name__ == "__main__":
    main()
