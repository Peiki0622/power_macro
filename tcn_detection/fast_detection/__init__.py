"""Causal fast-detector screening utilities for the power macro monitor.

The package deliberately stays separate from model training code.  A detector
consumes one sensor capture at a time and returns a level alarm, which makes
the same implementation usable by the offline evaluator and a later RTL
reference model.
"""

from power_macro.tcn_detection.fast_detection.detector_base import (
    Detector,
    TraceMetadata,
)

__all__ = ["Detector", "TraceMetadata"]
