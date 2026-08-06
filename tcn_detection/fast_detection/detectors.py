#!/usr/bin/env python3
"""Eight small causal detector families used by the Stage-1 screening flow."""

from __future__ import print_function

from power_macro.tcn_detection.fast_detection.detector_base import Detector


class _FeatureTracker:
    """Maintain the integer code-derived statistics shared by complex rules.

    Every value is bounded by legal sensor-code ranges or an explicit CUSUM
    limit.  No tracker method receives a label, waveform family, voltage, or a
    future capture, which keeps learned and hand-written detectors equivalent
    at the online input boundary.
    """

    def __init__(self, baseline=15, cusum_drift=0, cusum_limit=255,
                 count_threshold=1):
        self.baseline = int(baseline)
        self.cusum_drift = int(cusum_drift)
        self.cusum_limit = int(cusum_limit)
        self.count_threshold = int(count_threshold)
        self.reset()

    def reset(self):
        """Initialize registers to calibrated no-droop values."""

        self.previous = self.baseline
        self.previous_slope = 0
        self.cusum = 0
        self.max_residual = 0
        self.threshold_count = 0

    def update(self, code):
        """Advance all integer statistics once and return their current values."""

        residual = int(code) - self.baseline
        slope = int(code) - self.previous
        acceleration = slope - self.previous_slope
        self.cusum = min(self.cusum_limit,
                         max(0, self.cusum + residual - self.cusum_drift))
        self.max_residual = max(self.max_residual, residual)
        self.threshold_count = (self.threshold_count + 1
                                if residual >= self.count_threshold else 0)
        self.previous = int(code)
        self.previous_slope = slope
        return {"residual": residual, "slope": slope,
                "acceleration": acceleration, "cusum": self.cusum,
                "max_residual": self.max_residual,
                "threshold_count": self.threshold_count}


def derive_feature_rows(codes, baseline=15, cusum_drift=0,
                        count_threshold=1):
    """Return the five causal scorecard features for one complete code trace.

    This helper is intentionally identical to the register update used by the
    online scorecard/FSM.  It is used only on train rows while fitting the
    shallow models, and therefore cannot create a second, subtly different
    feature definition.
    """

    tracker = _FeatureTracker(baseline, cusum_drift, 255, count_threshold)
    return [tracker.update(int(code)) for code in codes]


class SingleThresholdDetector(Detector):
    """Immediate monotonic detector implementing ``sensor_code >= threshold``."""

    name = "single_threshold"

    def __init__(self, threshold):
        super().__init__()
        self.threshold = int(threshold)
        if not 1 <= self.threshold <= 32:
            raise ValueError("threshold must be in [1,32]")

    def _reset_state(self):
        """No extra state is needed beyond the base alarm register."""

    def step(self, sensor_code, valid):
        """Raise immediately for a valid code meeting the frozen threshold."""

        code, accepted = self._begin_step(sensor_code, valid)
        if accepted:
            self._alarm = code >= self.threshold
        return self.alarm

    def hardware_cost(self):
        """Describe the single comparator implementation cost."""

        return {"add_sub_count": 0, "compare_count": 1, "multiplier_count": 0,
                "state_bits": 1, "memory_bits": 0, "cycles_per_sample": 1}


class ThresholdConfirmDetector(SingleThresholdDetector):
    """Require K consecutive strict threshold exceedances before alarming."""

    name = "threshold_confirm"

    def __init__(self, threshold, confirm_count):
        super().__init__(threshold)
        self.confirm_count = int(confirm_count)
        if self.confirm_count not in {1, 2, 3, 4, 8}:
            raise ValueError("confirm_count is outside the approved search set")

    def _reset_state(self):
        """Clear the only confirmation counter at each trace boundary."""

        self.counter = 0

    def step(self, sensor_code, valid):
        """Update the consecutive counter only on a valid capture."""

        code, accepted = self._begin_step(sensor_code, valid)
        if accepted:
            self.counter = self.counter + 1 if code > self.threshold else 0
            self._alarm = self.counter >= self.confirm_count
        return self.alarm

    def hardware_cost(self):
        """Count comparator and bounded confirmation register requirements."""

        return {"add_sub_count": 1, "compare_count": 2, "multiplier_count": 0,
                "state_bits": 4, "memory_bits": 0, "cycles_per_sample": 1}


class AmplitudeSlopeDetector(Detector):
    """Alarm only when code amplitude and the current rise both exceed limits."""

    name = "amplitude_slope"

    def __init__(self, amplitude_threshold, slope_threshold):
        super().__init__()
        self.amplitude_threshold = int(amplitude_threshold)
        self.slope_threshold = int(slope_threshold)
        if not 0 <= self.amplitude_threshold <= 17 or not 0 <= self.slope_threshold <= 32:
            raise ValueError("amplitude/slope thresholds outside sensor bounds")

    def _reset_state(self):
        """Start the finite difference from the calibrated baseline code."""

        self.previous = 15

    def step(self, sensor_code, valid):
        """Calculate residual and slope from current/past code only."""

        code, accepted = self._begin_step(sensor_code, valid)
        if accepted:
            residual = code - self.metadata.baseline_code
            slope = code - self.previous
            self._alarm = (residual > self.amplitude_threshold
                           and slope > self.slope_threshold)
            self.previous = code
        return self.alarm

    def hardware_cost(self):
        """Report two subtractors and two decision comparisons."""

        return {"add_sub_count": 2, "compare_count": 2, "multiplier_count": 0,
                "state_bits": 6, "memory_bits": 0, "cycles_per_sample": 1}


class EwmaResidualDetector(Detector):
    """Detect code residual above a shift-only EWMA baseline."""

    name = "ewma_residual"

    def __init__(self, q, threshold):
        super().__init__()
        self.q = int(q)
        self.threshold = int(threshold)
        if self.q not in {3, 4, 5, 6} or not 0 <= self.threshold <= 17:
            raise ValueError("EWMA configuration is outside the approved grid")

    def _reset_state(self):
        """Store baseline with q fractional bits to avoid a divider or multiplier."""

        self.baseline_q = 15 << self.q

    def step(self, sensor_code, valid):
        """Apply ``b += (x-b)/2**q`` with integer arithmetic right shifting."""

        code, accepted = self._begin_step(sensor_code, valid)
        if accepted:
            sample_q = code << self.q
            self.baseline_q += (sample_q - self.baseline_q) >> self.q
            residual = code - (self.baseline_q >> self.q)
            self._alarm = residual > self.threshold
        return self.alarm

    def snapshot(self):
        """Include fixed-point baseline state for drift reporting."""

        state = super().snapshot()
        state["baseline_q"] = int(getattr(self, "baseline_q", 0))
        return state

    def hardware_cost(self):
        """EWMA uses only add/subtract, one shift, one compare and one register."""

        return {"add_sub_count": 3, "compare_count": 1, "multiplier_count": 0,
                "state_bits": 12, "memory_bits": 0, "cycles_per_sample": 1}


class CusumDetector(Detector):
    """Pure-integer one-sided CUSUM detector with an explicit saturating bound."""

    name = "cusum"

    def __init__(self, drift, threshold):
        super().__init__()
        self.drift = int(drift)
        self.threshold = int(threshold)
        if not 0 <= self.drift <= 8 or not 1 <= self.threshold <= 128:
            raise ValueError("CUSUM drift/threshold outside the approved grid")

    def _reset_state(self):
        """Clear the saturating non-negative CUSUM accumulator."""

        self.cusum = 0

    def step(self, sensor_code, valid):
        """Update ``max(0, S + code-baseline-drift)`` without multiplication."""

        code, accepted = self._begin_step(sensor_code, valid)
        if accepted:
            residual = code - self.metadata.baseline_code
            self.cusum = min(self.threshold,
                             max(0, self.cusum + residual - self.drift))
            self._alarm = self.cusum >= self.threshold
        return self.alarm

    def snapshot(self):
        """Expose the bounded accumulator for detector result diagnostics."""

        state = super().snapshot()
        state["cusum"] = int(getattr(self, "cusum", 0))
        return state

    def hardware_cost(self):
        """CUSUM requires two additions, saturation checks and no multiplier."""

        return {"add_sub_count": 2, "compare_count": 3, "multiplier_count": 0,
                "state_bits": 8, "memory_bits": 0, "cycles_per_sample": 1}


class MultiStatisticFSMDetector(Detector):
    """Five-state RTL-shaped detector using only bounded integer statistics."""

    name = "multistat_fsm"
    SAFE, SUSPECT, WARNING, CRITICAL, RECOVERY = range(5)

    def __init__(self, thresholds, clear_count=2):
        super().__init__()
        self.thresholds = {level: {name: int(value) for name, value in values.items()}
                           for level, values in thresholds.items()}
        self.clear_count = int(clear_count)
        required = {"suspect", "warning", "critical"}
        features = {"residual", "slope", "acceleration", "cusum", "threshold_count"}
        if (set(self.thresholds) != required or self.clear_count < 1
                or any(set(values) != features for values in self.thresholds.values())):
            raise ValueError("FSM thresholds must define every level and feature")

    def _reset_state(self):
        """Reset state code, clear counter, and all source statistics."""

        self.state = self.SAFE
        self.clear_streak = 0
        self.features = _FeatureTracker(baseline=15, cusum_drift=0,
                                        cusum_limit=128, count_threshold=1)

    def _reaches(self, level, values):
        """Evaluate one fixed OR-composed danger level without look-ahead."""

        return any(values[name] >= self.thresholds[level][name]
                   for name in self.thresholds[level])

    def step(self, sensor_code, valid):
        """Run the explicit SAFE/SUSPECT/WARNING/CRITICAL/RECOVERY table."""

        code, accepted = self._begin_step(sensor_code, valid)
        if not accepted:
            return self.alarm
        values = self.features.update(code)
        suspect = self._reaches("suspect", values)
        warning = self._reaches("warning", values)
        critical = self._reaches("critical", values)
        self.clear_streak = self.clear_streak + 1 if not suspect else 0
        if self.state == self.SAFE:
            self.state = self.SUSPECT if suspect else self.SAFE
        elif self.state == self.SUSPECT:
            self.state = self.WARNING if warning else (self.SAFE if not suspect else self.SUSPECT)
        elif self.state == self.WARNING:
            self.state = self.CRITICAL if critical else (self.SUSPECT if not warning else self.WARNING)
        elif self.state == self.CRITICAL:
            self.state = self.RECOVERY if not warning else self.CRITICAL
        else:  # RECOVERY
            if critical:
                self.state = self.CRITICAL
            elif warning:
                self.state = self.WARNING
            elif self.clear_streak >= self.clear_count:
                self.state = self.SAFE
        self._alarm = self.state in {self.WARNING, self.CRITICAL, self.RECOVERY}
        return self.alarm

    def snapshot(self):
        """Publish state encoding and current integer features for audit traces."""

        state = super().snapshot()
        state.update({"fsm_state": int(getattr(self, "state", self.SAFE)),
                      "clear_streak": int(getattr(self, "clear_streak", 0))})
        return state

    def hardware_cost(self):
        """Estimate fixed single-cycle comparator/FSM resources structurally."""

        return {"add_sub_count": 6, "compare_count": 18, "multiplier_count": 0,
                "state_bits": 30, "memory_bits": 0, "cycles_per_sample": 1}


class Int8ScorecardDetector(Detector):
    """Apply a frozen five-feature INT8 linear score without a sigmoid."""

    name = "int8_scorecard"
    FEATURE_ORDER = ("residual", "slope", "cusum", "max_residual", "threshold_count")

    def __init__(self, weights, bias, score_threshold, cusum_drift=0,
                 threshold_count_threshold=1):
        super().__init__()
        self.weights = tuple(int(value) for value in weights)
        self.bias = int(bias)
        self.score_threshold = int(score_threshold)
        self.cusum_drift = int(cusum_drift)
        self.threshold_count_threshold = int(threshold_count_threshold)
        if len(self.weights) != len(self.FEATURE_ORDER) or any(abs(value) > 127 for value in self.weights):
            raise ValueError("scorecard requires five INT8 weights")

    def _reset_state(self):
        """Reset the same bounded features used during train-only fitting."""

        self.features = _FeatureTracker(15, self.cusum_drift, 255,
                                        self.threshold_count_threshold)
        self.score = self.bias

    def step(self, sensor_code, valid):
        """Compute integer dot product and compare it directly to the threshold."""

        code, accepted = self._begin_step(sensor_code, valid)
        if accepted:
            values = self.features.update(code)
            self.score = self.bias + sum(weight * values[name]
                                         for weight, name in zip(self.weights, self.FEATURE_ORDER))
            self._alarm = self.score >= self.score_threshold
        return self.alarm

    def hardware_cost(self):
        """Record five INT8 products; shift-only conversion is evaluated later."""

        return {"add_sub_count": 6, "compare_count": 1, "multiplier_count": 5,
                "state_bits": 38, "memory_bits": 5 * 8 + 32,
                "cycles_per_sample": 1}


class ShallowTreeDetector(Int8ScorecardDetector):
    """Evaluate a frozen comparator tree whose leaves are Safe/Critical bits."""

    name = "shallow_tree"

    def __init__(self, nodes, cusum_drift=0, threshold_count_threshold=1):
        # The parent owns feature extraction only; its score is unused here.
        super().__init__((0, 0, 0, 0, 0), 0, 1, cusum_drift,
                         threshold_count_threshold)
        self.nodes = tuple(nodes)
        if not self.nodes or len(self.nodes) > 31:
            raise ValueError("tree must have a bounded non-empty node list")

    def step(self, sensor_code, valid):
        """Traverse at most four comparator levels using current causal features."""

        code, accepted = self._begin_step(sensor_code, valid)
        if not accepted:
            return self.alarm
        values = self.features.update(code)
        index = 0
        for _ in range(5):
            node = self.nodes[index]
            if "leaf" in node:
                self._alarm = bool(int(node["leaf"]))
                return self.alarm
            feature = str(node["feature"])
            if feature not in self.FEATURE_ORDER:
                raise ValueError("tree uses an unknown feature")
            index = int(node["left"] if values[feature] <= int(node["threshold"])
                        else node["right"])
            if not 0 <= index < len(self.nodes):
                raise ValueError("tree child index is invalid")
        raise ValueError("tree depth exceeds the approved four comparisons")

    def hardware_cost(self):
        """A depth-four tree is comparator-only and stores its node table."""

        comparisons = sum(1 for node in self.nodes if "leaf" not in node)
        return {"add_sub_count": 1, "compare_count": comparisons,
                "multiplier_count": 0, "state_bits": 30,
                "memory_bits": len(self.nodes) * 24, "cycles_per_sample": 1}
