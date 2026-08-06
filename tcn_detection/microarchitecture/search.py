#!/usr/bin/env python3
"""Exhaustive, deterministic Stage 1 CNN microarchitecture search."""

from __future__ import print_function

import hashlib
import json
from pathlib import Path

from power_macro.tcn_detection.microarchitecture.cycle_model import (
    estimate_candidate)
from power_macro.tcn_detection.microarchitecture.dependency import (
    analyze_dependencies, validate_replay_and_shift)
from power_macro.tcn_detection.microarchitecture.package import load_package
from power_macro.tcn_detection.microarchitecture.storage import describe_storage


def _sha256(path):
    """Hash a configuration file so generated artifacts bind their assumptions."""

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_config(path):
    """Load the checked-in search contract without accepting implicit defaults."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def enumerate_specs(config):
    """Yield every legal hardware tuple in stable, human-readable order.

    The physical MAC limit is checked before cycle estimation.  This avoids
    comparing a superficially fast candidate that would require more
    multipliers than the declared implementation contains.
    """

    for mac_count in config["mac_counts"]:
        for output_parallel in config["output_channel_parallel_candidates"]:
            for position_parallel in config["position_parallel_candidates"]:
                for fanin_parallel in config["fan_in_parallel_candidates"]:
                    if output_parallel * position_parallel * fanin_parallel > mac_count:
                        continue
                    for bank_count in config["weight_bank_candidates"]:
                        for read_width in config["weight_read_width_candidates"]:
                            yield {
                                "mac_count": int(mac_count),
                                "output_channel_parallel": int(output_parallel),
                                "position_parallel": int(position_parallel),
                                "fan_in_parallel": int(fanin_parallel),
                                "weight_bank_count": int(bank_count),
                                "weight_read_width": int(read_width),
                            }


def _candidate_id(spec):
    """Use all implementation-relevant dimensions in a stable identifier."""

    return "m{mac_count}_o{output_channel_parallel}_p{position_parallel}" \
           "_f{fan_in_parallel}_b{weight_bank_count}_w{weight_read_width}".format(
               **spec)


def _resource_proxies(result, storage, spec):
    """Return transparent pre-synthesis ranking proxies, not physical QoR.

    Area combines provisioned MACs, parameter bytes, and bank/read interface
    width.  Energy is a conservative scheduled-operation proxy: all useful
    MACs, weight reads, activation writes, and provisioned MAC clock slots are
    counted equally.  The report explicitly labels both values as relative
    search units; no technology or power number is inferred from them.
    """

    area = (int(spec["mac_count"])
            + int(storage["total_parameter_bytes_ceiling"])
            + int(spec["weight_bank_count"]) * int(spec["weight_read_width"]))
    energy = (int(result["useful_macs"])
              + int(result["weight_words_read"])
              + int(result["activation_write_elements"])
              + int(spec["mac_count"]) * int(result["total_latency_cycles"]))
    return {"area_proxy_units": area, "energy_proxy_units": energy}


def _timing_summary(result):
    """Keep the candidate artifact compact while retaining every reported metric.

    Per-tile bank histograms and controller sub-events are deterministic
    derivations of the candidate spec and remain available from
    ``estimate_candidate``.  Repeating them for all 8,475 candidates created
    an 85 MB artifact without adding selection evidence, so only the layer and
    total timing contract is published for each candidate.
    """

    return {
        "dataflow": result["dataflow"],
        "conv1_cycles": result["conv1_cycles"],
        "conv2_cycles": result["conv2_cycles"],
        "conv3_cycles": result["conv3_cycles"],
        "pool_cycles": result["pool_cycles"],
        "classifier_cycles": result["classifier_cycles"],
        "total_latency_cycles": result["total_latency_cycles"],
        "initiation_interval_cycles": result["initiation_interval_cycles"],
        "mac_utilization": result["mac_utilization"],
        "useful_macs": result["useful_macs"],
        "weight_words_read": result["weight_words_read"],
        "activation_write_elements": result["activation_write_elements"],
        "memory_bandwidth": result["memory_bandwidth"],
    }


def _storage_summary(storage):
    """Publish exact storage totals without duplicating layer layouts per candidate."""

    return {
        "total_parameter_bits": storage["total_parameter_bits"],
        "total_parameter_bytes_ceiling": storage["total_parameter_bytes_ceiling"],
        "conv_weight_storage": storage["conv_weight_storage"],
        "bias_storage": storage["bias_storage"],
        "requant_storage": storage["requant_storage"],
        "classifier_storage": storage["classifier_storage"],
    }


def _dominates(left, right):
    """Return whether one feasible configuration is no worse in all objectives."""

    metrics = ("area_proxy_units", "energy_proxy_units",
               "storage_bits", "initiation_interval_cycles")
    return (all(left[name] <= right[name] for name in metrics)
            and any(left[name] < right[name] for name in metrics))


def _pareto(candidates):
    """Keep the exact non-dominated frontier without quadratic comparison.

    Sorting by area means a later entry can never improve the first objective
    over an earlier one.  The maintained frontier is normally very small, so
    this scan preserves the same Pareto definition while keeping the complete
    8,475-candidate search practical on the project Python environment.
    """

    ordered = sorted(candidates, key=lambda item: (
        item["area_proxy_units"], item["energy_proxy_units"],
        item["storage_bits"], item["initiation_interval_cycles"],
        item["candidate_id"]))
    frontier = []
    for candidate in ordered:
        if any(_dominates(existing, candidate) for existing in frontier):
            continue
        frontier = [existing for existing in frontier
                    if not _dominates(candidate, existing)]
        frontier.append(candidate)
    return frontier


def _normalised_score(candidates, weights):
    """Add a deterministic equal-domain score to each Pareto candidate."""

    fields = {
        "area": "area_proxy_units",
        "energy": "energy_proxy_units",
        "storage": "storage_bits",
        "ii": "initiation_interval_cycles",
    }
    extrema = {name: (min(item[field] for item in candidates),
                      max(item[field] for item in candidates))
               for name, field in fields.items()}
    scored = []
    for candidate in candidates:
        score = 0.0
        for name, field in fields.items():
            low, high = extrema[name]
            normalised = 0.0 if high == low else float(candidate[field] - low) / float(high - low)
            score += float(weights[name]) * normalised
        copy_candidate = dict(candidate)
        copy_candidate["selection_score"] = score
        scored.append(copy_candidate)
    return scored


def _select(candidates, config):
    """Select the smallest feasible stride, then the frozen Pareto trade-off."""

    clock = config["clock"]
    cycles_per_sample = int(round(float(clock["sample_period_ns"])
                                  / float(clock["compute_period_ns"])))
    strides = list(config["stride_candidates"]) + list(config["stride_extension"])
    for stride in strides:
        budget = int(stride) * cycles_per_sample
        feasible = [candidate for candidate in candidates
                    if candidate["total_latency_cycles"] <= budget
                    and candidate["initiation_interval_cycles"] <= budget]
        if not feasible:
            continue
        frontier = _pareto(feasible)
        scored = _normalised_score(frontier,
                                   config["selection"]["normalised_resource_score"])
        selected = min(scored, key=lambda item: (
            item["selection_score"], item["mac_count"],
            item["total_latency_cycles"], item["storage_bits"],
            item["candidate_id"]))
        return {
            "status": "SELECTED",
            "selected_stride_samples": int(stride),
            "budget_cycles": budget,
            "pareto_candidate_ids": [item["candidate_id"] for item in frontier],
            "selected": selected,
        }
    return {
        "status": "BLOCKED_NO_FEASIBLE_CANDIDATE",
        "selected_stride_samples": None,
        "budget_cycles": None,
        "pareto_candidate_ids": [],
        "selected": None,
    }


def run_search(config_path):
    """Run preflight, both dataflow models, all candidates, and selection."""

    config_path = Path(config_path)
    config = load_config(config_path)
    package = load_package()
    dependency = validate_replay_and_shift(package)
    # The standalone structural result is retained to make the report clear
    # even if a future replay implementation changes its validation metadata.
    structural_dependency = analyze_dependencies(package)
    affected = dependency["affected_position_counts"]
    candidates = []
    for spec in enumerate_specs(config):
        full = estimate_candidate(package, spec, config["nominal_schedule"])
        incremental = estimate_candidate(package, spec, config["nominal_schedule"],
                                         affected_positions=affected)
        storage = describe_storage(package, spec)
        chosen = incremental if dependency["mode_b_reduces_work"] else full
        proxies = _resource_proxies(chosen, storage, spec)
        full_summary = _timing_summary(full)
        incremental_summary = _timing_summary(incremental)
        compact_storage = _storage_summary(storage)
        candidates.append({
            "candidate_id": _candidate_id(spec),
            "mac_count": spec["mac_count"],
            "output_channel_parallel": spec["output_channel_parallel"],
            "position_parallel": spec["position_parallel"],
            "fan_in_parallel": spec["fan_in_parallel"],
            "weight_bank_count": spec["weight_bank_count"],
            "weight_read_width": spec["weight_read_width"],
            "chosen_dataflow": chosen["dataflow"],
            "full_window": full_summary,
            "incremental": incremental_summary,
            "incremental_matches_full": (
                full["total_latency_cycles"] == incremental["total_latency_cycles"]
                and full["initiation_interval_cycles"] == incremental[
                    "initiation_interval_cycles"]),
            "storage": compact_storage,
            "storage_bits": storage["total_parameter_bits"],
            "area_proxy_units": proxies["area_proxy_units"],
            "energy_proxy_units": proxies["energy_proxy_units"],
            "total_latency_cycles": chosen["total_latency_cycles"],
            "initiation_interval_cycles": chosen["initiation_interval_cycles"],
            "mac_utilization": chosen["mac_utilization"],
            "memory_bandwidth": chosen["memory_bandwidth"],
        })
    selected = _select(candidates, config)
    return {
        "schema_version": 1,
        "status": selected["status"],
        "source_binding": package["source_binding"],
        "model_contract": package["model"],
        "search_config_path": str(config_path),
        "search_config_sha256": _sha256(config_path),
        "dependency_analysis": dependency,
        "structural_dependency_analysis": structural_dependency,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "selection": selected,
    }
