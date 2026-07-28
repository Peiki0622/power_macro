#!/usr/bin/env python3
"""Render one real-DFF Vernier HSPICE deck for a corpus trace.

The renderer delegates all electrical topology to the completed Phase-2 deck
generator.  Its only dataset-specific operation is to place the prevalidated
500-frame droop array in the explicit PWL extension.  Consequently the port
contract remains exactly the reviewed implementation:

* `V_VDD_A vdd_a vss_a` drives only the chiplet-A sense chain and sense launch;
* `V_VDD_REF vdd_ref vss_ref` supplies reference stages, DFFs, and DFF wells;
* each comparator binds `D=sense_i`, `CK=ref_i`, and `R=sensor_reset`.
"""

from __future__ import print_function

import copy
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PHASE2_SCRIPTS = ROOT / "power_macro" / "delay_chain" / "phase2_vernier" / "scripts"
if str(PHASE2_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PHASE2_SCRIPTS))
import generate_direct_rail_sensor_timeline_deck as phase2_deck  # noqa: E402


def load_json(path):
    """Load one trace request or Phase-2 configuration object."""

    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    """Hash compact inputs so a retained trace can be audited after cleanup."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def render(trace, phase2_config):
    """Return a deck and review metadata for exactly one 500-frame trace."""

    targets = trace.get("target_droop_mv")
    if not isinstance(targets, list) or len(targets) != 500:
        raise ValueError("trace must provide exactly 500 target_droop_mv values")
    config = copy.deepcopy(phase2_config)
    study = config["direct_rail_sensor_timeline"]
    study["explicit_capture_droop_mv"] = [float(value) for value in targets]
    deck, metadata = phase2_deck.render_direct_rail_deck(config)
    metadata["trace_id"] = trace["trace_id"]
    metadata["target_droop_sha256"] = hashlib.sha256(",".join("{:.9f}".format(value) for value in targets).encode("ascii")).hexdigest()
    return deck, metadata


def write(trace_path, phase2_config_path, output_path):
    """Write one ASCII HSPICE deck to the caller-owned attempt directory."""

    trace = load_json(trace_path)
    phase2_config = load_json(phase2_config_path)
    deck, metadata = render(trace, phase2_config)
    output_path.write_text(deck, encoding="ascii")
    metadata["phase2_config_sha256"] = sha256_file(phase2_config_path)
    metadata["trace_spec_sha256"] = sha256_file(trace_path)
    return metadata
