#!/usr/bin/env python3
"""Deterministic L0 replay fallback for the frozen B-FE2.2C stimulus.

This fallback is used only because the remote VCS compiler currently exits
255 in its finalizer on the host.  It implements the same scalar equations as
the VCS testbench: source-domain thresholding, fixed PD_SAFE restoration, and
transparent-high latch hold.  It never changes the source waveform or close.
The resulting probes are marked offline in the manifest and cannot be used to
claim a successful VCS compile.
"""
import sys
from pathlib import Path


def replay(stimulus: Path, probe: Path) -> int:
    rows = []
    with stimulus.open(encoding="ascii") as stream:
        for line in stream:
            if line.startswith("#") or not line.strip():
                continue
            values = [float(item) for item in line.split()]
            if len(values) != 33:
                raise ValueError("unexpected stimulus width: {}".format(len(values)))
            rows.append(values)
    q = [0.0] * 30
    probe.parent.mkdir(parents=True, exist_ok=True)
    with probe.open("w", encoding="ascii") as stream:
        stream.write("time_ps vdd_sense_v vdd_safe_v g_v")
        stream.write(" " + " ".join("xor_{}".format(i) for i in range(30)))
        stream.write(" " + " ".join("safe_d_{}".format(i) for i in range(30)))
        stream.write(" " + " ".join("q_{}".format(i) for i in range(30)) + "\n")
        for time_ps, vdd_sense, g, *xor_values in rows:
            safe_d = [0.95 if value > 0.5 * vdd_sense else 0.0 for value in xor_values]
            if g > 0.5 * 0.95:
                q = safe_d[:]
            stream.write("{:.9f} {:.9f} {:.9f} {:.9f} {} {} {}\n".format(
                time_ps, vdd_sense, 0.95, g,
                " ".join("{:.9f}".format(value) for value in xor_values),
                " ".join("{:.9f}".format(value) for value in safe_d),
                " ".join("{:.9f}".format(value) for value in q)))
    return len(rows)


if __name__ == "__main__":
    count = replay(Path(sys.argv[1]), Path(sys.argv[2]))
    print("L0_OFFLINE_REPLAY rows={}".format(count))
