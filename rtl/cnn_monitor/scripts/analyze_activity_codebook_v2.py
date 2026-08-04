#!/usr/bin/env python3
"""Build a deterministic RTL-activity codebook with enforceable tier gates.

This v2 analyzer intentionally remains separate from ``analyze_activity_vcd``.
The v1 output is historical evidence and used a forced equal-count partition.
Here every low/medium/high label is earned from measured toggle values, repeat
variation, minimum membership, and explicit centre-separation gates.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


# These names are the task-three reporting contract.  A group with zero
# observed transitions is retained as zero instead of disappearing from JSON,
# so downstream validators can distinguish "quiet" from "not measured".
MODULE_GROUPS = (
    "convolution_mac",
    "weight_intermediate_storage",
    "average_accumulator",
    "maximum_tracker",
    "endpoint_registers",
    "classifier",
    "control_address",
)


class TieringError(ValueError):
    """Raised when measured activity cannot meet the frozen three-tier gates."""


def _group(scope: str, name: str) -> str:
    """Classify one RTL VCD signal into one mutually exclusive reporting group."""
    lower = (scope + "/" + name).lower()
    if "pool_classifier" in lower:
        if "average_sum" in lower or "pool_operand" in lower:
            return "average_accumulator"
        if "maximum_value" in lower:
            return "maximum_tracker"
        if "endpoint_value" in lower:
            return "endpoint_registers"
        if "classifier" in lower or "summary_" in lower or "logit" in lower:
            return "classifier"
    if "convolution_engine" in lower:
        if "weight_rom" in lower or "feature_bank" in lower or "final_features" in lower:
            return "weight_intermediate_storage"
        if any(token in lower for token in (
            "accumulator", "activation", "product", "requant", "source_"
        )):
            return "convolution_mac"
    if "window_buffer" in lower and any(token in lower for token in (
        "snapshot", "circular_buffer"
    )):
        return "weight_intermediate_storage"
    return "control_address"


def _known(value: str) -> bool:
    """Return true only for VCD values that can contribute real bit toggles."""
    return bool(value) and all(bit in "01" for bit in value)


def _normalise(value: str, width: int) -> str:
    """Expand a scalar VCD change to the declared vector width before XORing."""
    if len(value) < width:
        return value[0] * (width - len(value)) + value
    return value[-width:]


def parse_vcd(path: Path) -> Dict[str, object]:
    """Parse a VCS VCD interval without treating X/Z transitions as activity.

    The input VCD is produced from an RTL activity run.  A VCD identifier may
    be visible through multiple hierarchy aliases, therefore it is counted
    once.  ``macro_q`` is the documented compiler-model X alias and is kept
    outside toggle totals; any other unknown state is reported as an audit
    flag rather than converted into a numeric transition.
    """
    scopes: List[str] = []
    identifiers: Dict[str, Dict[str, object]] = {}
    values: Dict[str, str] = {}
    # A VCD commonly starts every flop at X before reset drives a defined
    # state.  Those pre-reset values are neither functional activity nor an
    # indication that the measured transaction propagated X.  Record whether
    # each identifier has reached a known value so only a later regression
    # from a known state to X/Z is reported as a functional unknown.
    known_seen = set()
    groups: Dict[str, int] = defaultdict(int)
    cycles: Dict[int, int] = defaultdict(int)
    clock_ids, reset_ids = set(), set()
    header, cycle, saw_rise, unknown_state_seen = True, 0, False, False
    # VCS emits X values inside a ``$dumpoff`` block to invalidate all dumped
    # signals after waveform capture stops.  These values are a VCD transport
    # convention, not DUT transitions, and must not affect unknown-state or
    # toggle checks.  A later ``$dumpon`` resumes normal measurement.
    dumping = True

    with path.open("r", encoding="ascii", errors="replace") as stream:
        for raw in stream:
            line = raw.strip()
            if header:
                if line.startswith("$scope"):
                    scopes.append(line.split()[2])
                elif line.startswith("$upscope"):
                    scopes.pop()
                elif line.startswith("$var"):
                    fields = line.split()
                    width, identifier, name = int(fields[2]), fields[3], fields[4]
                    signal = {
                        "width": width,
                        "name": name,
                        "group": _group("/".join(scopes), name),
                    }
                    if (identifier not in identifiers or
                            (identifiers[identifier]["group"] == "control_address" and
                             signal["group"] != "control_address")):
                        identifiers[identifier] = signal
                    if name == "clk":
                        clock_ids.add(identifier)
                    if name == "reset":
                        reset_ids.add(identifier)
                elif line == "$enddefinitions $end":
                    header = False
                continue
            if line == "$dumpoff":
                dumping = False
                continue
            if line == "$dumpon":
                dumping = True
                continue
            if not line or line.startswith("$") or line.startswith("#") or not dumping:
                continue
            if line[0] in "01xXzZ":
                value, identifier = line[0].lower(), line[1:]
            elif line[0] in "bBrR":
                fields = line[1:].split()
                if len(fields) != 2:
                    continue
                value, identifier = fields[0].lower(), fields[1]
            else:
                continue
            if identifier not in identifiers:
                continue
            signal = identifiers[identifier]
            value = _normalise(value, int(signal["width"]))
            old = values.get(identifier)
            values[identifier] = value
            if identifier in clock_ids and old == "0" and value == "1":
                cycle += 1
                saw_rise = True
                continue
            if identifier in clock_ids or identifier in reset_ids or old is None:
                continue
            if not _known(old) or not _known(value):
                # ``old`` can be X during reset initialization.  It becomes
                # an error only after this identifier was known once and then
                # returns to X/Z.  The sole exception is the documented RTL
                # compiler-ROM public-Q alias, which is not the observed data
                # path in this historical RTL run.  No generic signal name,
                # hierarchy, or module group is otherwise exempted.
                if (identifier in known_seen and not _known(value) and
                        signal["name"] != "macro_q"):
                    unknown_state_seen = True
                # The first known value after reset establishes the point
                # after which a return to X/Z is a functional failure.
                if _known(value):
                    known_seen.add(identifier)
                continue
            known_seen.add(identifier)
            toggles = sum(left != right for left, right in zip(old, value))
            if toggles:
                group = str(signal["group"])
                groups[group] += toggles
                cycles[cycle] += toggles
    if not saw_rise:
        raise ValueError("VCD contains no rising clock edge: {}".format(path))
    waveform = [cycles[index] for index in range(1, cycle + 1)]
    vector = {group: int(groups.get(group, 0)) for group in MODULE_GROUPS}
    return {
        "total_toggle_count": int(sum(vector.values())),
        "module_toggle_vector": vector,
        "cycle_activity_waveform": waveform,
        "peak_cycle": waveform.index(max(waveform)) + 1 if waveform else 0,
        "peak_cycle_activity": max(waveform, default=0),
        "unknown_state_seen": unknown_state_seen,
    }


def _cv(values: Sequence[float]) -> float:
    """Return population CV, treating three identical zeros as perfectly stable."""
    mean = statistics.mean(values)
    if mean == 0:
        return 0.0 if len(set(values)) == 1 else float("inf")
    return statistics.pstdev(values) / mean


def _partition_score(groups: Sequence[Sequence[Mapping[str, object]]], metric: str) -> float:
    """Return within-tier squared error for one fully deterministic partition."""
    score = 0.0
    for group in groups:
        centre = statistics.mean(float(item[metric]) for item in group)
        score += sum((float(item[metric]) - centre) ** 2 for item in group)
    return score


def tier_candidates(records: Iterable[Mapping[str, object]], config: Mapping[str, object],
                    metric: str) -> Dict[str, str]:
    """Assign measured candidates to low/medium/high or raise a gate failure.

    Candidate values are sorted by ``metric`` and ``pattern_id`` only.  Every
    legal pair of contiguous cuts is evaluated, so there is no RNG, seed,
    input-order dependence, or forced equal-count fallback.  The best valid
    partition minimizes within-tier SSE; ties use the lexicographically first
    cut pair, making repeated analyses byte-stable.
    """
    candidates = [dict(item) for item in records if item["family"] != "control"]
    minimum = int(config["minimum_patterns_per_tier"])
    if len(candidates) < minimum * int(config["required_tier_count"]):
        raise TieringError("not enough candidates for the required tier count")
    limit = float(config["max_repeat_cv_fraction"])
    for item in candidates:
        if float(item["repeat_cv"]) > limit:
            raise TieringError("repeat CV exceeds gate for {}".format(item["pattern_id"]))
    ordered = sorted(candidates, key=lambda item: (float(item[metric]), item["pattern_id"]))
    best: Optional[Tuple[float, int, int, Sequence[Sequence[Mapping[str, object]]]]] = None
    separation = float(config["activity_separation_fraction"])
    total = len(ordered)
    for first in range(minimum, total - 2 * minimum + 1):
        for second in range(first + minimum, total - minimum + 1):
            groups = (ordered[:first], ordered[first:second], ordered[second:])
            centres = [statistics.mean(float(item[metric]) for item in group) for group in groups]
            if centres[0] <= 0:
                continue
            lower_gap = (centres[1] - centres[0]) / centres[0]
            upper_gap = (centres[2] - centres[1]) / centres[1] if centres[1] else 0.0
            if lower_gap < separation or upper_gap < separation:
                continue
            candidate = (_partition_score(groups, metric), first, second, groups)
            if best is None or candidate[:3] < best[:3]:
                best = candidate
    if best is None:
        raise TieringError("measured values do not form three separated tiers")
    labels = ("low", "medium", "high")
    return {
        str(item["pattern_id"]): label
        for label, group in zip(labels, best[3])
        for item in group
    }


def _load_config(path: Path) -> Dict[str, object]:
    """Validate the v2 shape used by the analyzer before any output is written."""
    config = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema_version", "config_id", "baseline_commit", "window_length",
        "sensor_code_min", "sensor_code_max", "mac_lanes", "repeat_count",
        "compute_latency_cycles", "initiation_interval_cycles",
        "activity_separation_fraction", "max_repeat_cv_fraction",
        "minimum_patterns_per_tier", "required_tier_count",
        "required_valid_pattern_count", "required_candidate_pattern_count",
        "primary_input_annotation_fraction_min",
        "sequential_output_annotation_fraction_min", "rom_output_annotation_fraction_min",
        "overall_state_element_annotation_fraction_min", "reject_power_warning_ids",
        "scope_reconciliation_residual_fraction_max", "control_pattern_ids",
    }
    missing = sorted(required - set(config))
    if missing:
        raise ValueError("v2 configuration is missing {}".format(", ".join(missing)))
    integer_contract = {
        "schema_version": 2,
        "window_length": 32,
        "sensor_code_min": 0,
        "sensor_code_max": 32,
        "mac_lanes": 16,
        "repeat_count": 3,
        "compute_latency_cycles": 12892,
        "initiation_interval_cycles": 12893,
        "minimum_patterns_per_tier": 3,
        "required_tier_count": 3,
        "required_valid_pattern_count": 36,
        "required_candidate_pattern_count": 31,
    }
    for name, expected in integer_contract.items():
        if type(config[name]) is not int or config[name] != expected:
            raise ValueError("{} must equal frozen value {}".format(name, expected))
    probability_contract = {
        "activity_separation_fraction": 0.05,
        "max_repeat_cv_fraction": 0.001,
        "primary_input_annotation_fraction_min": 1.0,
        "sequential_output_annotation_fraction_min": 0.95,
        "rom_output_annotation_fraction_min": 1.0,
        "overall_state_element_annotation_fraction_min": 0.95,
        "scope_reconciliation_residual_fraction_max": 0.02,
    }
    for name, expected in probability_contract.items():
        if type(config[name]) not in (int, float) or config[name] != expected:
            raise ValueError("{} must equal frozen threshold {}".format(name, expected))
    if config["reject_power_warning_ids"] != ["PWR-415", "PWR-428"]:
        raise ValueError("reject_power_warning_ids differs from the frozen gate")
    if len(config["control_pattern_ids"]) != 5:
        raise ValueError("control_pattern_ids must bind the five frozen controls")
    return config


def analyze(input_run: Path, output: Path, config: Mapping[str, object]) -> Dict[str, object]:
    """Re-analyze the immutable v1 RTL VCD run into a separate v2 output tree."""
    if output.exists():
        raise FileExistsError("refusing to overwrite analysis output {}".format(output))
    windows_path = input_run / "rtl_characterization" / "inputs" / "windows" / "windows.jsonl"
    windows = [json.loads(line) for line in windows_path.read_text(encoding="utf-8").splitlines()]
    raw: List[Dict[str, object]] = []
    codebook: List[Dict[str, object]] = []
    for record in windows:
        repeats = []
        for repeat in range(int(config["repeat_count"])):
            stem = "{}_r{}".format(record["pattern_id"], repeat)
            result = (input_run / "rtl_characterization" / "results" / (stem + ".txt")).read_text().split()
            metric = parse_vcd(input_run / "rtl_characterization" / "vcd" / (stem + ".vcd"))
            metric.update({
                "pattern_id": record["pattern_id"],
                "repeat": repeat,
                "latency_cycles": int(result[1]),
                "safe_logit": int(result[2]),
                "critical_logit": int(result[3]),
                "decision": int(result[4]),
                "numeric_overflow": bool(int(result[5])),
                "protocol_error": bool(int(result[6])),
            })
            raw.append(metric)
            repeats.append(metric)
        totals = [int(item["total_toggle_count"]) for item in repeats]
        valid = all(
            item["latency_cycles"] == int(config["compute_latency_cycles"])
            and not item["numeric_overflow"]
            and not item["protocol_error"]
            and not item["unknown_state_seen"]
            for item in repeats
        )
        vector = dict(repeats[0]["module_toggle_vector"])
        branches = {
            name: vector[name]
            for name in ("average_accumulator", "maximum_tracker", "endpoint_registers")
        }
        codebook.append({
            **record,
            "total_toggle_count": int(statistics.median(totals)),
            "repeat_toggle_values": totals,
            "repeat_cv": _cv(totals),
            "peak_cycle": repeats[0]["peak_cycle"],
            "peak_cycle_activity": repeats[0]["peak_cycle_activity"],
            "module_toggle_vector": vector,
            "dominant_statistic_path": max(branches, key=branches.get),
            "latency_cycles": repeats[0]["latency_cycles"],
            "logits": [repeats[0]["safe_logit"], repeats[0]["critical_logit"]],
            "decision": repeats[0]["decision"],
            "validity_status": "valid" if valid else "invalid",
            "activity_tier": None,
            "average_dynamic_power_mw": None,
            "energy_window_nj": None,
            "peak_power_mw": None,
        })
    valid_candidates = [
        item for item in codebook
        if item["family"] != "control" and item["validity_status"] == "valid"
    ]
    status, failure = "PASS", None
    try:
        labels = tier_candidates(valid_candidates, config, "total_toggle_count")
        for item in codebook:
            item["activity_tier"] = labels.get(item["pattern_id"])
    except TieringError as error:
        status, failure = "FAIL", str(error)
    output.mkdir(parents=True)
    (output / "raw_rtl_activity_metrics_v2.jsonl").write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in raw), encoding="ascii"
    )
    (output / "cnn_rtl_activity_codebook_v2.jsonl").write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in codebook), encoding="ascii"
    )
    summary = {
        "status": status,
        "failure": failure,
        "pattern_count": len(codebook),
        "valid_count": sum(item["validity_status"] == "valid" for item in codebook),
        "candidate_count": len(valid_candidates),
        "tier_counts": {
            tier: sum(item["activity_tier"] == tier for item in codebook)
            for tier in ("low", "medium", "high")
        },
        "power_annotation": "unavailable_rtl_activity_only",
    }
    (output / "activity_tiering_summary_v2.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="ascii"
    )
    return summary


def main() -> None:
    """Expose immutable input-run and new output-dir command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-run", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    summary = analyze(args.input_run.resolve(), args.output_directory.resolve(),
                      _load_config(args.config.resolve()))
    if summary["status"] != "PASS":
        raise SystemExit("activity tiering failed: {}".format(summary["failure"]))


if __name__ == "__main__":
    main()
