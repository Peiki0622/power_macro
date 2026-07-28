#!/usr/bin/env python3
"""Build the fixed V1 Pilot request corpus before any HSPICE execution."""

from __future__ import print_function

import argparse
import json
import random
from pathlib import Path

from waveform_schema import build_trace, stable_id

# This is deliberately below the Phase-2 explicit PWL validator's exclusive
# 100 mV endpoint.  Keep the value named here so corpus tests and any future
# qualified-source range change can locate the contract in one place.
HARD_PAIR_MAX_DROOP_MV = 99.9


def load_json(path):
    """Read one explicitly configured corpus policy object."""

    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def make_event(family, duty, seed, ood, ordinal):
    """Choose deterministic but non-fixed event parameters and placement.

    ``duty_cycle`` is retained alongside the frame count even though the two
    are equivalent for this fixed 500-capture Pilot.  Reporting code needs the
    requested experiment category (1%, 5%, 10%, or 25%) directly, rather than
    reverse-engineering it from a potentially changed future trace length.
    """

    rng = random.Random(seed)
    length = max(2, int(round(500 * duty)))
    start = rng.randint(16, 500 - length - 16)
    if ood and ordinal % 4 == 0:
        amplitude = rng.uniform(8.0, 28.0)
    else:
        amplitude = rng.uniform(20.0, 80.0)
    return {"family": family, "amplitude_mv": round(amplitude, 6), "duty_cycle": duty,
            "length_samples": length, "start_index": start}


def main():
    """Emit exactly 96 independent trace specifications in JSON Lines form."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    config = load_json(args.config)
    if args.output.exists():
        raise ValueError("refusing to overwrite corpus: {}".format(args.output))
    root_seed = int(config["root_seed"])
    partitions = [("train", 48, False), ("validation", 16, False), ("iid_test", 16, False), ("ood_test", 16, True)]
    specs = []
    global_index = 0
    for split, count, is_ood in partitions:
        for local_index in range(count):
            seed = root_seed + global_index * 7919
            background = config["background_modes"][global_index % len(config["background_modes"])]
            normal = local_index < (16 if split == "train" else 6 if split != "ood_test" else 2)
            family_pool = config["ood_families"] if is_ood else config["known_families"]
            family = family_pool[global_index % len(family_pool)]
            duty_pool = [0.01, 0.05] if is_ood else [0.10, 0.25]
            event = None if normal else make_event(family, duty_pool[global_index % len(duty_pool)], seed, is_ood, local_index)
            # A base ID intentionally excludes the per-variant seed and event
            # position, but includes every invariant event category that
            # evaluation will report.  This keeps grouped splits robust if
            # future variants reuse an amplitude or frame length by chance.
            base_payload = {"split": split, "background_mode": background, "family": None if event is None else family,
                            "amplitude_mv": None if event is None else event["amplitude_mv"],
                            "duty_cycle": None if event is None else event["duty_cycle"],
                            "length_samples": None if event is None else event["length_samples"]}
            base_id = stable_id("base", base_payload)
            spec = {"schema_version": 1, "split": split, "seed": seed, "background_mode": background,
                    "waveform_family_id": "background" if event is None else family, "base_waveform_id": base_id,
                    # A top-level field lets later distribution reports group
                    # every trace without parsing nested optional event JSON.
                    # ``None`` denotes an intentionally event-free safe trace.
                    "event_duty_cycle": None if event is None else event["duty_cycle"], "event": event}
            spec["trace_id"] = stable_id("trace", {"base": base_id, "seed": seed, "start": None if event is None else event["start_index"]})
            specs.append(build_trace(spec))
            global_index += 1

    # Reserve four OOD member pairs for the temporal-detection claim.  Each
    # pair starts from the same fully rendered background and shares its PWL
    # through a decision frame.  The recovering member loses its extra droop
    # immediately afterwards; the worsening member adds a late collapse.  A
    # later electrical audit compares the real sensor-code prefix, but this
    # construction prevents a pair from being merely two unrelated OOD rows
    # decorated with the same identifier.
    ood_event_indices = [index for index, spec in enumerate(specs) if spec["split"] == "ood_test" and spec.get("event")]
    for pair_number, first_index in enumerate(ood_event_indices[:8:2]):
        second_index = ood_event_indices[pair_number * 2 + 1]
        recovering = specs[first_index]
        worsening = specs[second_index]
        decision = min(420, max(32, int(recovering["event"]["start_index"]) + int(recovering["event"]["length_samples"]) // 2))
        shared = list(recovering["target_droop_mv"][:decision + 1])
        # Keep the OOD pair's online history bit-for-bit equal.  Both requests
        # remain in OOD test; only their future source trajectory differs.
        worsening["target_droop_mv"][:decision + 1] = shared
        for index in range(decision + 1, 500):
            recovering["target_droop_mv"][index] = min(recovering["target_droop_mv"][index], 3.0)
            # The reviewed direct-rail extension has a strict ``<100 mV``
            # source contract, so retain a small guard band below its upper
            # endpoint.  The 99.9 mV value remains well inside the intended
            # saturated Critical regime while producing a renderable PWL.
            worsening["target_droop_mv"][index] = min(HARD_PAIR_MAX_DROOP_MV, max(worsening["target_droop_mv"][index], shared[-1] + 55.0))
        pair_id = "hard_pair_{:02d}".format(pair_number)
        recovering["hard_pair_id"] = pair_id
        worsening["hard_pair_id"] = pair_id
        recovering["hard_pair_decision_index"] = decision
        worsening["hard_pair_decision_index"] = decision
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        for spec in specs:
            stream.write(json.dumps(spec, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
