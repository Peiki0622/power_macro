#!/usr/bin/env python3
"""Small causal interface shared by every Stage-1 detector.

The interface intentionally exposes only the sensor code and the capture-valid
bit.  Labels and physical voltage values remain evaluator-side data and can
never accidentally become runtime detector inputs.
"""

from __future__ import print_function

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class TraceMetadata:
    """Immutable context supplied once when a trace starts.

    ``baseline_code`` is a calibrated sensor constant, not a measured voltage
    value.  ``split`` and IDs are retained for provenance and are never passed
    to arithmetic decisions inside a detector.
    """

    trace_id: str
    split: str
    base_waveform_id: str
    hard_pair_id: str
    baseline_code: int = 15
    sensor_code_min: int = 0
    sensor_code_max: int = 32
    sample_period_ns: float = 4.0


class Detector(ABC):
    """Abstract one-sample causal detector contract."""

    name = "detector"

    def __init__(self):
        self.metadata = None
        self.sample_index = -1
        self._alarm = False

    def reset(self, metadata):
        """Reset all state at a trace boundary and return the cleared state.

        Returning a small state dictionary is useful to audit callers and does
        not expose labels or future samples to the detector implementation.
        Subclasses must call this method before their own state initialization.
        """

        if not isinstance(metadata, TraceMetadata):
            raise TypeError("metadata must be TraceMetadata")
        self.metadata = metadata
        self.sample_index = -1
        self._alarm = False
        self._reset_state()
        return self.snapshot()

    @abstractmethod
    def _reset_state(self):
        """Clear subclass-owned registers and counters."""

    @abstractmethod
    def step(self, sensor_code, valid):
        """Consume one capture and return the current level alarm."""

    def snapshot(self):
        """Return JSON-friendly state useful for debug and hardware costing."""

        return {"sample_index": int(self.sample_index), "alarm": bool(self._alarm)}

    def _begin_step(self, sensor_code, valid):
        """Validate a sample and advance the logical endpoint when accepted.

        Invalid captures deliberately do not advance the endpoint.  This makes
        a missing/invalid sensor result a hold operation rather than an
        invented zero-valued sample that could alter a slope or accumulator.
        """

        if self.metadata is None:
            raise RuntimeError("detector.reset(metadata) is required first")
        code = int(sensor_code)
        if not self.metadata.sensor_code_min <= code <= self.metadata.sensor_code_max:
            raise ValueError("sensor code outside legal range")
        if not bool(valid):
            return code, False
        self.sample_index += 1
        return code, True

    @property
    def alarm(self):
        """Expose the most recent level alarm without mutating state."""

        return bool(self._alarm)
