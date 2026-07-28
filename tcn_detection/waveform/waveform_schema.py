#!/usr/bin/env python3
"""Deterministically define direct-rail TCN waveform requests.

This module intentionally produces *voltage-source requests*, not sensor
codes.  HSPICE and the existing real-DFF Vernier decoder remain the only
source of sensor observations.  The schema separates a base waveform from a
trace variant so that variants can be grouped before simulation and cannot
leak between train, validation, and test splits.
"""

from __future__ import print_function

import hashlib
import json
import math
import random


SAMPLE_PERIOD_S = 4.0e-9
SAMPLE_COUNT = 500


def canonical_json(value):
    """Serialize a public identifier payload in a version-stable form."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_id(prefix, value):
    """Derive a short stable ID without depending on Python hash randomization."""

    digest = hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()
    return "{}_{}".format(prefix, digest[:16])


def bounded(value, low, high):
    """Clip an electrical droop value to the declared HSPICE-safe envelope."""

    return max(low, min(high, float(value)))


def background_droop_mv(mode, rng, sample_count=SAMPLE_COUNT):
    """Create a correlated timing-safe background droop sequence.

    The result is one droop value per 4 ns frame.  The deck renderer performs
    the port-level conversion to `VDD_A=Vnom-droop` during reset; keeping this
    routine in millivolts makes the provenance and range checks readable.
    """

    values = []
    state = rng.uniform(0.5, 2.0)
    burst_remaining = 0
    for index in range(sample_count):
        if mode == "busy":
            target = rng.uniform(0.5, 5.0)
        elif mode == "bursty":
            if burst_remaining <= 0:
                burst_remaining = rng.randint(4, 40)
                active = rng.random() < 0.5
            burst_remaining -= 1
            target = rng.uniform(1.0, 8.0) if active else rng.uniform(0.2, 1.5)
        elif mode == "mixed":
            target = rng.uniform(0.5, 5.0) if (index // 20) % 2 else rng.uniform(0.2, 6.0)
        elif mode == "randomizer_like":
            # Safe power-randomization-like clusters deliberately remain well
            # above the measured first-violation droop near 52 mV.
            target = rng.uniform(2.0, 12.0) if rng.random() < 0.35 else rng.uniform(0.5, 3.0)
        elif mode == "unseen_multiscale_bursty":
            # This OOD-only background is intentionally not a renamed copy of
            # any training mode.  It combines a slowly correlated safe load
            # wander with irregular short bursts, modelling an untrained
            # activity schedule while remaining well below the timing-risk
            # droop region by construction.  It is a voltage-source request,
            # never a synthetic sensor-code perturbation.
            slow_wander = 0.7 + 1.8 * (0.5 + 0.5 * math.sin(float(index) / 31.0))
            burst = rng.uniform(4.0, 10.0) if rng.random() < 0.18 else rng.uniform(0.2, 1.8)
            target = slow_wander + burst
        else:
            raise ValueError("unknown background mode: {}".format(mode))
        state = 0.72 * state + 0.28 * target
        values.append(bounded(state, 0.2, 12.0))
    return values


def event_profile(family, amplitude_mv, length, rng):
    """Render a nonnegative event profile with a normalized peak of one.

    `length` is a count of complete sensor frames.  The returned profile does
    not include the timing-safe background; callers add it after validating
    the event placement.  Each branch documents its intended temporal shape
    because waveform family is an OOD boundary, not an online model feature.
    """

    if length < 2:
        raise ValueError("event length must include at least two frames")
    profile = []
    for index in range(length):
        x = float(index) / float(length - 1)
        if family == "trapezoid":
            y = min(1.0, x / 0.2, (1.0 - x) / 0.25)
        elif family == "triangle":
            y = 1.0 - abs(2.0 * x - 1.0)
        elif family == "exponential":
            y = (1.0 - math.exp(-7.0 * min(1.0, x / 0.35))) * (1.0 if x < 0.65 else math.exp(-7.0 * (x - 0.65) / 0.35))
        elif family == "staircase":
            y = min(1.0, math.floor(x * 5.0 + 1.0) / 5.0)
            if x > 0.75:
                y *= max(0.0, (1.0 - x) / 0.25)
        elif family == "double_event":
            y = max(1.0 - abs(6.0 * x - 1.5), 0.8 * (1.0 - abs(6.0 * x - 4.5)), 0.0)
        elif family == "plateau_with_jitter":
            y = min(1.0, x / 0.2, (1.0 - x) / 0.2) * (0.92 + 0.08 * rng.random())
        elif family == "rlc_ringing":
            # Avoid an integer number of half-cycles across short 1%-duty
            # traces.  The former 7*pi phase made every eight-frame sample
            # land on a sine zero, silently producing an all-zero OOD event.
            # A non-integer cycle count preserves the intended damped ringing
            # shape at both short and long sensor sampling windows.
            y = max(0.0, math.exp(-3.5 * x) * math.sin(6.5 * math.pi * x))
        elif family == "glitch_cluster":
            y = 1.0 if int(x * 12.0) in (2, 3, 6, 8, 9) else 0.0
        elif family == "partial_recovery_second_collapse":
            y = max(min(1.0, x / 0.25), 0.65 * min(1.0, max(0.0, (x - 0.45) / 0.25)))
        elif family == "asymmetric_double_peak":
            y = max(1.0 - abs((x - 0.28) / 0.22), 0.72 * (1.0 - abs((x - 0.74) / 0.12)), 0.0)
        elif family == "random_walk_collapse":
            y = min(1.0, max(0.0, 0.15 * index / length + 0.65 * max(0.0, (x - 0.7) / 0.3)))
        else:
            raise ValueError("unknown waveform family: {}".format(family))
        profile.append(max(0.0, min(1.0, y)))
    # Families are sampled at the sensor's discrete 4 ns cadence, so a
    # continuous-time peak can fall between samples (notably for damped RLC
    # ringing).  Normalize after sampling to keep ``amplitude_mv`` equal to
    # the actual requested peak droop for every family and duty cycle.
    peak = max(profile)
    if peak <= 0.0:
        raise ValueError("event profile has no positive sampled point")
    return [value * float(amplitude_mv) / peak for value in profile]


def build_trace(spec):
    """Generate one trace request and its full 500-point target droop sequence."""

    rng = random.Random(int(spec["seed"]))
    values = background_droop_mv(spec["background_mode"], rng)
    event = spec.get("event")
    if event:
        start = int(event["start_index"])
        profile = event_profile(event["family"], float(event["amplitude_mv"]), int(event["length_samples"]), rng)
        if start < 16 or start + len(profile) > SAMPLE_COUNT - 16:
            raise ValueError("event violates 16-frame pre/post context margin")
        for offset, value in enumerate(profile):
            values[start + offset] = bounded(values[start + offset] + value, 0.2, 100.0)
    rendered = dict(spec)
    rendered["target_droop_mv"] = [round(value, 9) for value in values]
    rendered["sample_count"] = SAMPLE_COUNT
    rendered["sample_period_s"] = SAMPLE_PERIOD_S
    return rendered
