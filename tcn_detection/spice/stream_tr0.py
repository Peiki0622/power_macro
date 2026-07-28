#!/usr/bin/env python3
"""Stream selected HSPICE POST=2 rail samples without loading a multi-GB trace.

HSPICE W-2024.09 writes fixed-width 13-character numbers after a `$&%#`
marker.  This parser retains only the immediately adjacent records needed for
linear interpolation at the 500 real DFF Q-read times.  It validates all
required port probes while avoiding the historical parser's full-file
`read_text()` allocation.
"""

from __future__ import print_function

import math
import re


FIELD_WIDTH = 13
MARKER = b"$&%#"
REQUIRED = {
    "time_s": "time",
    "a_vdd_absolute_v": "v(vdd_a",
    "a_vss_absolute_v": "v(vss_a",
    "vdd_ref_absolute_v": "v(vdd_ref",
    "vss_ref_absolute_v": "v(vss_ref",
}


def _header(path):
    """Read only the small fixed-width header that precedes numerical records."""

    with path.open("rb") as stream:
        payload = b""
        while MARKER not in payload:
            block = stream.read(65536)
            if not block:
                raise ValueError(".tr0 lacks $&%# marker: {}".format(path))
            payload += block
        marker_at = payload.index(MARKER)
        width_match = re.match(br"^(\d{4})", payload)
        if width_match is None:
            raise ValueError(".tr0 lacks record width")
        record_width = int(width_match.group(1))
        time_at = payload.find(b"TIME")
        if time_at < 0 or time_at >= marker_at:
            raise ValueError(".tr0 lacks ordered TIME header")
        labels_raw = payload[time_at:marker_at].replace(b"\r", b"").replace(b"\n", b"")
        if len(labels_raw) < record_width * 16:
            raise ValueError(".tr0 label table is too short")
        labels = [labels_raw[index * 16:(index + 1) * 16].strip().lower().decode("ascii") for index in range(record_width)]
        selected = {}
        for semantic, expected in REQUIRED.items():
            matches = [index for index, label in enumerate(labels) if label == expected]
            if len(matches) != 1:
                raise ValueError("required .tr0 probe {} is ambiguous: {}".format(expected, labels))
            selected[semantic] = matches[0]
        if selected["time_s"] != 0:
            raise ValueError("TIME must be column zero")
        newline_at = payload.find(b"\n", marker_at)
        if newline_at < 0:
            raise ValueError(".tr0 marker has no numerical payload")
        # Reopen and skip exactly to the byte after the marker line.  Header
        # parsing is isolated from numerical streaming so the header size does
        # not constrain the later chunk size.
        return record_width, selected, newline_at + 1


def sample_rails(path, sample_times):
    """Return interpolated differential rails and summary statistics.

    `sample_times` must be ascending Q-read instants.  Each record's rail
    values are checked as finite, time must not decrease, and the final HSPICE
    terminal field is tolerated only after all complete records are consumed.
    """

    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("missing .tr0: {}".format(path))
    record_width, selected, payload_offset = _header(path)
    record_bytes = record_width * FIELD_WIDTH
    answers = []
    next_sample = 0
    previous = None
    record_count = 0
    duplicate_time_count = 0
    min_a = math.inf
    max_a = -math.inf
    carry = b""
    with path.open("rb") as stream:
        stream.seek(payload_offset)
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            compact = re.sub(br"\s+", b"", carry + chunk)
            usable = (len(compact) // record_bytes) * record_bytes
            records, carry = compact[:usable], compact[usable:]
            for offset in range(0, len(records), record_bytes):
                fields = records[offset:offset + record_bytes]
                values = {}
                for name, column in selected.items():
                    value = float(fields[column * FIELD_WIDTH:(column + 1) * FIELD_WIDTH])
                    if not math.isfinite(value):
                        raise ValueError("non-finite {} at record {}".format(name, record_count))
                    values[name] = value
                current_time = values["time_s"]
                if previous is not None and current_time < previous["time_s"]:
                    raise ValueError(".tr0 time decreases at record {}".format(record_count))
                if previous is not None and current_time == previous["time_s"]:
                    duplicate_time_count += 1
                a_rail = values["a_vdd_absolute_v"] - values["a_vss_absolute_v"]
                min_a = min(min_a, a_rail)
                max_a = max(max_a, a_rail)
                while previous is not None and next_sample < len(sample_times) and previous["time_s"] <= sample_times[next_sample] <= current_time:
                    query = sample_times[next_sample]
                    if current_time == previous["time_s"]:
                        fraction = 1.0
                    else:
                        fraction = (query - previous["time_s"]) / (current_time - previous["time_s"])
                    a_value = previous["a_vdd_absolute_v"] - previous["a_vss_absolute_v"] + fraction * (a_rail - (previous["a_vdd_absolute_v"] - previous["a_vss_absolute_v"]))
                    ref_previous = previous["vdd_ref_absolute_v"] - previous["vss_ref_absolute_v"]
                    ref_current = values["vdd_ref_absolute_v"] - values["vss_ref_absolute_v"]
                    answers.append({"a_vdd_v": a_value, "vdd_ref_v": ref_previous + fraction * (ref_current - ref_previous)})
                    next_sample += 1
                previous = values
                record_count += 1
    if next_sample != len(sample_times):
        raise ValueError(".tr0 ends before all requested capture times")
    # HSPICE appends one terminal field after the final full record.  Reject
    # anything larger because that signals a changed fixed-width contract.
    if len(carry) not in (0, FIELD_WIDTH):
        raise ValueError(".tr0 payload leaves unexpected trailing bytes")
    return {"samples": answers, "record_count": record_count, "duplicate_time_count": duplicate_time_count,
            "a_vdd_min_v": min_a, "a_vdd_max_v": max_a}
