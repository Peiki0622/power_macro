#!/usr/bin/env python3
"""Deterministic cycle estimator for the compressed CNN search.

This is deliberately a schedule model rather than an RTL simulator.  Every
cycle category it reports has a named future controller event: bias setup,
weight issue limited by bank bandwidth, synchronous-ROM drain, requantization,
and writeback.  Keeping those categories separate prevents a later RTL design
from claiming a shorter latency by hiding a required pipeline stage.
"""

from __future__ import print_function

import math


# Search candidates with different physical MAC ceilings often share an
# identical legal per-layer schedule.  Caching that immutable calculation keeps
# exhaustive enumeration practical without sampling or changing any formula.
_LAYER_CACHE = {}
_CLASSIFIER_CACHE = {}


def ceil_div(numerator, denominator):
    """Return ``ceil(numerator / denominator)`` after validating dimensions."""

    numerator = int(numerator)
    denominator = int(denominator)
    if numerator < 0 or denominator < 1:
        raise ValueError("invalid non-negative count or positive divisor")
    return (numerator + denominator - 1) // denominator


def _bank_issue_cycles(addresses, bank_count, words_per_bank_cycle):
    """Return fixed issue cycles for one weight group and its bank histogram.

    A convolution weight is broadcast to every parallel output position, so an
    issue group contains one word per output channel and fan-in item rather
    than one word per physical MAC.  The modulo mapping is intentionally
    simple and deterministic; the Stage 1 storage report exposes its bank
    conflicts instead of assuming an unspecified multi-port ROM.
    """

    counts = [0] * int(bank_count)
    for address in addresses:
        counts[int(address) % int(bank_count)] += 1
    cycles = max([ceil_div(value, words_per_bank_cycle) for value in counts] or [0])
    return cycles, counts


def _layer_schedule(layer, spec, position_count, schedule, weight_base_address):
    """Estimate one convolution layer using the exact exported weight shape.

    ``position_count`` is normally 32.  It is an explicit argument so the
    dependency analysis can later ask how much a proven incremental update
    would cost without changing the W8/A8 arithmetic or controller rules.
    """

    weights = layer["weights"]
    output_channels, input_channels, kernel_size = [int(value) for value in
                                                     weights.shape]
    fanin = input_channels * kernel_size
    output_parallel = min(int(spec["output_channel_parallel"]), output_channels)
    position_parallel = min(int(spec["position_parallel"]), int(position_count))
    fanin_parallel = min(int(spec["fan_in_parallel"]), fanin)
    if output_parallel * position_parallel * fanin_parallel > int(spec["mac_count"]):
        raise ValueError("candidate overcommits its physical MAC count")

    bank_count = int(spec["weight_bank_count"])
    read_width = int(spec["weight_read_width"])
    writeback_bandwidth = int(spec.get(
        "writeback_bandwidth", output_parallel * position_parallel))
    if bank_count < 1 or read_width < 1 or writeback_bandwidth < 1:
        raise ValueError("bank count, read width, and writeback bandwidth are positive")

    cache_key = (layer["name"], tuple(int(value) for value in weights.shape),
                 int(position_count), output_parallel, position_parallel,
                 fanin_parallel, bank_count, read_width, writeback_bandwidth,
                 int(schedule["rom_latency_cycles"]),
                 int(schedule["requant_pipeline_cycles"]),
                 int(weight_base_address))
    cached = _LAYER_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)

    output_groups = ceil_div(output_channels, output_parallel)
    position_groups = ceil_div(position_count, position_parallel)
    fanin_groups = ceil_div(fanin, fanin_parallel)
    bias_cycles = output_groups * position_groups
    issue_cycles = 0
    weight_words = 0
    peak_words = 0
    peak_bank_occupancy = 0

    # Weight addresses follow the immutable [out][in][kernel] C-order package.
    # The same per-channel/fan-in group is reused for each position tile, but
    # the final output-channel tile may contain fewer than ``output_parallel``
    # valid channels and is therefore counted separately.
    for group_index in range(output_groups):
        output_start = group_index * output_parallel
        valid_outputs = min(output_parallel, output_channels - output_start)
        per_position_issue = 0
        for fanin_group in range(fanin_groups):
            fanin_start = fanin_group * fanin_parallel
            valid_fanin = min(fanin_parallel, fanin - fanin_start)
            addresses = [
                int(weight_base_address) + output_channel * fanin + fanin_index
                for output_channel in range(output_start,
                                            output_start + valid_outputs)
                for fanin_index in range(fanin_start,
                                         fanin_start + valid_fanin)
            ]
            group_cycles, bank_histogram = _bank_issue_cycles(
                addresses, bank_count, read_width)
            per_position_issue += group_cycles
            weight_words += len(addresses) * position_groups
            peak_words = max(peak_words, len(addresses))
            peak_bank_occupancy = max(peak_bank_occupancy,
                                      max(bank_histogram or [0]))
        issue_cycles += per_position_issue * position_groups

    valid_outputs_total = output_channels * int(position_count)
    writeback_cycles = ceil_div(valid_outputs_total, writeback_bandwidth)
    rom_cycles = output_groups * position_groups * int(
        schedule["rom_latency_cycles"])
    requant_cycles = output_groups * position_groups * int(
        schedule["requant_pipeline_cycles"])
    total_cycles = (bias_cycles + issue_cycles + rom_cycles + requant_cycles
                    + writeback_cycles)
    useful_macs = output_channels * int(position_count) * fanin
    result = {
        "name": layer["name"],
        "output_channels": output_channels,
        "input_channels": input_channels,
        "kernel_size": kernel_size,
        "fanin": fanin,
        "position_count": int(position_count),
        "output_parallel": output_parallel,
        "position_parallel": position_parallel,
        "fanin_parallel": fanin_parallel,
        "output_groups": output_groups,
        "position_groups": position_groups,
        "fanin_groups": fanin_groups,
        "bias_cycles": bias_cycles,
        "weight_issue_cycles": issue_cycles,
        "rom_cycles": rom_cycles,
        "requant_cycles": requant_cycles,
        "writeback_cycles": writeback_cycles,
        "cycles": total_cycles,
        "useful_macs": useful_macs,
        "weight_words_read": weight_words,
        "peak_weight_words_per_issue": peak_words,
        "peak_bank_word_occupancy": peak_bank_occupancy,
    }
    _LAYER_CACHE[cache_key] = dict(result)
    return result


def _classifier_schedule(classifier, spec, schedule):
    """Estimate the fixed two-logit linear head with its dedicated weight store."""

    weights = classifier["weights"]
    output_classes, feature_count = [int(value) for value in weights.shape]
    output_parallel = min(int(spec["output_channel_parallel"]), output_classes)
    fanin_parallel = min(int(spec["fan_in_parallel"]), feature_count)
    if output_parallel * fanin_parallel > int(spec["mac_count"]):
        raise ValueError("candidate overcommits MACs in the classifier")
    output_groups = ceil_div(output_classes, output_parallel)
    feature_groups = ceil_div(feature_count, fanin_parallel)
    # The classifier is small enough to remain a distinct logical store.  It
    # uses the requested word width but one bank, avoiding an artificial
    # dependency on convolution-bank layout during the final reduction.
    read_width = int(spec["weight_read_width"])
    writeback_bandwidth = int(spec.get("writeback_bandwidth", output_parallel))
    cache_key = (tuple(int(value) for value in weights.shape), output_parallel,
                 fanin_parallel, read_width, writeback_bandwidth,
                 int(schedule["rom_latency_cycles"]),
                 int(schedule["requant_pipeline_cycles"]))
    cached = _CLASSIFIER_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)
    issue_cycles = 0
    for output_group in range(output_groups):
        valid_outputs = min(output_parallel,
                            output_classes - output_group * output_parallel)
        for feature_group in range(feature_groups):
            valid_features = min(fanin_parallel,
                                 feature_count - feature_group * fanin_parallel)
            issue_cycles += ceil_div(valid_outputs * valid_features, read_width)
    writeback_cycles = ceil_div(output_classes, writeback_bandwidth)
    total_cycles = (1 + issue_cycles + int(schedule["rom_latency_cycles"])
                    + int(schedule["requant_pipeline_cycles"])
                    + writeback_cycles)
    result = {
        "cycles": total_cycles,
        "bias_cycles": 1,
        "weight_issue_cycles": issue_cycles,
        "rom_cycles": int(schedule["rom_latency_cycles"]),
        "requant_cycles": int(schedule["requant_pipeline_cycles"]),
        "writeback_cycles": writeback_cycles,
        "useful_macs": output_classes * feature_count,
        "weight_words_read": output_classes * feature_count,
        "peak_weight_words_per_issue": output_parallel * fanin_parallel,
    }
    _CLASSIFIER_CACHE[cache_key] = dict(result)
    return result


def estimate_candidate(package, spec, schedule, affected_positions=None):
    """Estimate fixed latency, II, utilization, and memory bandwidth.

    ``affected_positions`` is optional and maps ``conv1`` through ``conv3``
    to proven recomputation counts.  Omitting it performs the required full
    L32 calculation.  No arithmetic values are inspected, so the reported
    schedule cannot become data dependent.
    """

    required = ("mac_count", "output_channel_parallel", "position_parallel",
                "fan_in_parallel", "weight_bank_count", "weight_read_width")
    missing = [name for name in required if name not in spec]
    if missing:
        raise ValueError("candidate misses {}".format(", ".join(missing)))
    if int(spec["mac_count"]) < 1:
        raise ValueError("MAC count is positive")

    positions = affected_positions or {}
    layer_results = []
    weight_base_address = 0
    for layer in package["layers"]:
        count = int(positions.get(layer["name"], package["model"]["window_length"]))
        if count < 1 or count > int(package["model"]["window_length"]):
            raise ValueError("invalid affected-position count for {}".format(
                layer["name"]))
        layer_results.append(_layer_schedule(layer, spec, count, schedule,
                                             weight_base_address))
        # All convolution weight files flatten in C order, so the next layer
        # begins immediately after the current layer's physical words.
        weight_base_address += int(layer["weights"].size)

    pool_positions = int(positions.get("pool", layer_results[-1]["position_count"]))
    if pool_positions < 1 or pool_positions > int(package["model"]["window_length"]):
        raise ValueError("invalid affected-position count for pooling")
    pool_cycles = (int(schedule["pool_init_cycles"])
                   + ceil_div(pool_positions, int(spec["position_parallel"]))
                   + int(schedule["pool_finalize_cycles"]))
    classifier = _classifier_schedule(package["classifier"], spec, schedule)
    latency = (sum(item["cycles"] for item in layer_results) + pool_cycles
               + classifier["cycles"])
    ii = latency + int(schedule["result_commit_guard_cycles"])
    useful_macs = sum(item["useful_macs"] for item in layer_results)
    useful_macs += classifier["useful_macs"]
    weight_words = sum(item["weight_words_read"] for item in layer_results)
    weight_words += classifier["weight_words_read"]
    activation_writes = sum(
        item["output_channels"] * item["position_count"] for item in layer_results)
    peak_weight_words = max([item["peak_weight_words_per_issue"]
                             for item in layer_results]
                            + [classifier["peak_weight_words_per_issue"]])
    return {
        "dataflow": "incremental" if affected_positions else "full_window",
        "spec": dict(spec),
        "conv1_cycles": layer_results[0]["cycles"],
        "conv2_cycles": layer_results[1]["cycles"],
        "conv3_cycles": layer_results[2]["cycles"],
        "pool_cycles": pool_cycles,
        "classifier_cycles": classifier["cycles"],
        "total_latency_cycles": latency,
        "initiation_interval_cycles": ii,
        "mac_utilization": float(useful_macs) / float(
            int(spec["mac_count"]) * latency),
        "useful_macs": useful_macs,
        "weight_words_read": weight_words,
        "activation_write_elements": activation_writes,
        "memory_bandwidth": {
            "average_weight_words_per_cycle": float(weight_words) / float(latency),
            "peak_weight_words_per_issue": peak_weight_words,
            "convolution_bank_capacity_words_per_cycle": int(
                spec["weight_bank_count"]) * int(spec["weight_read_width"]),
        },
        "layers": layer_results,
        "classifier": classifier,
    }
