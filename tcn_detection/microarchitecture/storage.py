#!/usr/bin/env python3
"""Logical weight-bank and parameter-storage model for Stage 1.

The results are intentionally expressed as exact bits and simple logical-bank
payloads.  No SRAM macro, layout area, or power number is fabricated before
RTL and synthesis exist; later selection uses these values only as transparent
resource proxies.
"""

from __future__ import print_function

import math


# Storage size and modulo layout depend on the authenticated package and bank
# count, not on MAC/position/fan-in parallelism.  This cache avoids repeatedly
# redistributing the same 1,530 convolution words during exhaustive search.
_STORAGE_CACHE = {}


def _signed_bits(values):
    """Return the smallest signed width covering all integer configuration values."""

    lower = min(int(value) for value in values)
    upper = max(int(value) for value in values)
    bits = 2
    while lower < -(1 << (bits - 1)) or upper > (1 << (bits - 1)) - 1:
        bits += 1
    return bits


def _bank_layout(word_count, bank_count, base_address):
    """Map consecutive package words to modulo-indexed banks without gaps."""

    entries = [0] * int(bank_count)
    for offset in range(int(word_count)):
        entries[(int(base_address) + offset) % int(bank_count)] += 1
    return entries


def describe_storage(package, spec):
    """Return exact parameter storage and bank payloads for one candidate.

    Convolution weights share the searched bank array.  The two-class head is
    intentionally a dedicated small store: it has a different 54-feature
    reduction access pattern, and sharing it would add a controller mode
    without reducing the authenticated parameter bits.
    """

    bank_count = int(spec["weight_bank_count"])
    if bank_count < 1:
        raise ValueError("weight bank count is positive")
    package_shape_key = tuple(tuple(int(value) for value in layer["weights"].shape)
                              for layer in package["layers"])
    cache_key = (package_shape_key, bank_count)
    cached = _STORAGE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    conv_weight_bits = 0
    conv_bias_bits = 0
    bank_entries = [0] * bank_count
    base_address = 0
    layer_records = []
    requant_shifts = []
    for layer in package["layers"]:
        weight_words = int(layer["weights"].size)
        weight_bits = 8  # The authenticated selected package is W8.
        bias_bits = int(layer["bias"].size) * int(layer["accumulator_width"])
        layout = _bank_layout(weight_words, bank_count, base_address)
        bank_entries = [left + right for left, right in zip(bank_entries, layout)]
        conv_weight_bits += weight_words * weight_bits
        conv_bias_bits += bias_bits
        requant_shifts.extend(int(layer["output_exponent"]) - int(value)
                              for value in layer["accumulator_exponents"])
        layer_records.append({
            "name": layer["name"],
            "weight_words": weight_words,
            "weight_bits": weight_words * weight_bits,
            "bias_entries": int(layer["bias"].size),
            "bias_bits": bias_bits,
            "base_weight_address": base_address,
            "bank_entries": layout,
        })
        base_address += weight_words

    classifier = package["classifier"]
    classifier_weight_bits = int(classifier["weights"].size) * 8
    classifier_bias_bits = (int(classifier["bias"].size)
                            * int(classifier["accumulator_width"]))
    requant_shifts.extend(int(classifier["output_exponent"]) - int(value)
                          for value in classifier["accumulator_exponents"])
    shift_bits = _signed_bits(requant_shifts)
    # One signed shift per output channel captures all per-channel scale
    # alignment.  Four output exponents are retained as small constants for
    # auditability even though a later RTL may encode them directly in control.
    requant_bits = shift_bits * len(requant_shifts) + shift_bits * 4
    total_bits = (conv_weight_bits + conv_bias_bits + classifier_weight_bits
                  + classifier_bias_bits + requant_bits)
    result = {
        "conv_weight_storage": {
            "bank_count": bank_count,
            "word_bits": 8,
            "total_words": sum(bank_entries),
            "total_bits": conv_weight_bits,
            "bank_entries": bank_entries,
            "max_bank_entries": max(bank_entries),
            "min_bank_entries": min(bank_entries),
        },
        "bias_storage": {
            "total_bits": conv_bias_bits + classifier_bias_bits,
            "conv_bits": conv_bias_bits,
            "classifier_bits": classifier_bias_bits,
            "conv1_position_dependent": True,
        },
        "requant_storage": {
            "shift_entries": len(requant_shifts),
            "signed_shift_bits": shift_bits,
            "shift_range": [min(requant_shifts), max(requant_shifts)],
            "total_bits": requant_bits,
        },
        "classifier_storage": {
            "mode": "dedicated_linear_store",
            "weight_bits": classifier_weight_bits,
            "bias_bits": classifier_bias_bits,
            "total_bits": classifier_weight_bits + classifier_bias_bits,
        },
        "layers": layer_records,
        "total_parameter_bits": total_bits,
        "total_parameter_bytes_ceiling": int(math.ceil(total_bits / 8.0)),
    }
    _STORAGE_CACHE[cache_key] = result
    return result
