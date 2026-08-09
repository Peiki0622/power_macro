"""Pure-data decoding used by FTC physical-characterization runners and tests.

The physical HSPICE measurements are converted to words in ascending stage
order: character zero in every CSV word is physical stage zero.  Keeping this
order explicit avoids silently confusing a human-readable SPICE vector with a
packed SystemVerilog vector, which prints its most-significant bit first.
"""

from typing import Any, Dict, Iterable, List, Sequence


def bits_from_crossings(crossings: Sequence[float], sample_time_s: float) -> List[int]:
    """Return one wavefront bit per tap using the documented FTC comparison."""

    return [1 if float(crossing) <= float(sample_time_s) else 0 for crossing in crossings]


def bits_from_levels(levels: Sequence[float], threshold_v: float) -> List[int]:
    """Digitize sampled cell outputs against the local supply midpoint."""

    return [1 if float(level) >= float(threshold_v) else 0 for level in levels]


def word(bits: Iterable[int]) -> str:
    """Serialize a stage-ascending binary vector for compact CSV evidence."""

    return "".join("1" if int(bit) else "0" for bit in bits)


def bubble_count(bits: Sequence[int]) -> int:
    """Count isolated interior ``1-0-1`` bubbles in a physical XOR word.

    Trailing zeros are the normal end of a finite FTC window, so they must not
    be classified as bubbles.  This diagnostic deliberately matches the
    one-bit majority correction used below: only a zero directly surrounded by
    asserted neighboring taps is counted and potentially repaired.
    """

    return sum(
        1
        for index in range(1, len(bits) - 1)
        if int(bits[index - 1]) and not int(bits[index]) and int(bits[index + 1])
    )


def longest_one_run(bits: Sequence[int]) -> Dict[str, Any]:
    """Find the longest contiguous run of ones with a deterministic low-index tie.

    This mechanism-stage decoder intentionally does not repair bubbles.  It
    exposes the actual physical XOR shape before the later FTC RTL applies its
    explicitly documented single-bubble correction.
    """

    best_start = 0
    best_length = 0
    current_start = 0
    current_length = 0
    run_count = 0
    previous = 0
    for index, bit in enumerate(bits):
        if bit:
            if not previous:
                current_start = index
                current_length = 0
                run_count += 1
            current_length += 1
            if current_length > best_length:
                best_start = current_start
                best_length = current_length
        previous = int(bool(bit))
    end = best_start + best_length - 1 if best_length else 0
    return {
        "start_index": best_start if best_length else 0,
        "end_index": end,
        "one_run_length": best_length,
        "valid": int(best_length > 0),
        "run_count": run_count,
        "bubble_count": bubble_count(bits),
        "touches_left_boundary": int(best_length > 0 and best_start == 0),
        "touches_right_boundary": int(best_length > 0 and end == len(bits) - 1),
    }


def majority_repair(bits: Sequence[int]) -> List[int]:
    """Fill an isolated interior ``1-0-1`` bubble without erasing a real run.

    A generic three-tap median filter would also change a valid isolated
    ``0-1-0`` single-bit run into zero.  FTC's encoder contract must retain
    every physical one-run, including a single-bit run, so this directional
    three-tap repair changes only a zero whose two immediate neighbors agree
    that the window continues through that stage.
    """

    if len(bits) <= 2:
        return list(bits)
    repaired = [int(bits[0])]
    for index in range(1, len(bits) - 1):
        if int(bits[index - 1]) and not int(bits[index]) and int(bits[index + 1]):
            repaired.append(1)
        else:
            repaired.append(int(bits[index]))
    repaired.append(int(bits[-1]))
    return repaired
