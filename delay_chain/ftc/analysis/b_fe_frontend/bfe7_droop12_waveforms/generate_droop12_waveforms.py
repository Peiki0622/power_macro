#!/usr/bin/env python3
"""Generate the deterministic B-FE7 DROOP12 voltage-stimulus package.

The module is intentionally stimulus-only.  It contains no detector, sensor,
clock, latch, DFF, backend, or RTL dependency.  Its electrical boundary is a
single monitored-domain source with the project port contract::

    V_VDD_MONITORED vdd_monitored vss_a PWL(...)

``vdd_monitored`` is the positive supply node observed by the frontend and
``vss_a`` is its local return node.  Keeping this port map explicit makes each
include directly reusable by later ARCH0 and ARCH1 decks without copying any
detector circuitry into the benchmark files.

All internal times are integer picoseconds.  This avoids accumulated binary
floating-point error while constructing a piecewise-linear waveform.  Values
are converted to SI seconds only when serialized for CSV/HSPICE output.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np


SCRIPT_VERSION = "bfe7_droop12_generator_v1"
SEED = 7301
T_STOP_PS = 65000
V_NOM = 1.10
TEMP_C = 25.0
SLOW_SPACING_PS = 2500
FAST_SPACING_PS = 250
SLOW_LIMIT_V = 0.005
FAST_LIMIT_V = 0.003
BACKGROUND_LIMIT_V = 0.008
MONITORED_SOURCE = "V_VDD_MONITORED vdd_monitored vss_a"


def sha256_file(path):
    """Return a streaming SHA256 digest for reproducibility manifests."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _center_and_bound(samples, limit):
    """Center seeded samples while retaining the declared per-component bound."""

    values = np.asarray(samples, dtype=np.float64)
    values = values - float(np.mean(values))
    # The source distribution is already narrow; clipping is a defensive
    # contract guard for future changes to the sampling implementation.
    return np.clip(values, -limit, limit)


def _time_grid(step_ps):
    """Return inclusive integer-ps knots from zero through the 65 ns stop."""

    if T_STOP_PS % step_ps:
        raise ValueError("stop time must be divisible by knot spacing")
    return np.arange(0, T_STOP_PS + step_ps, step_ps, dtype=np.int64)


def generate_background(seed=SEED):
    """Construct the shared normal background on the canonical 250 ps grid.

    ``PCG64`` is named explicitly instead of relying on NumPy's
    ``default_rng`` alias, so a future NumPy default change cannot silently
    replace the paper-facing realization.  Slow samples are generated first,
    followed by fast samples, making the random draw order part of the frozen
    metadata contract.
    """

    if int(seed) != SEED:
        raise ValueError("DROOP12 canonical background seed is {}".format(SEED))
    rng = np.random.Generator(np.random.PCG64(int(seed)))
    slow_times = _time_grid(SLOW_SPACING_PS)
    fast_times = _time_grid(FAST_SPACING_PS)
    slow_samples = _center_and_bound(
        rng.uniform(-SLOW_LIMIT_V, SLOW_LIMIT_V, len(slow_times)), SLOW_LIMIT_V
    )
    fast_samples = _center_and_bound(
        rng.uniform(-FAST_LIMIT_V, FAST_LIMIT_V, len(fast_times)), FAST_LIMIT_V
    )
    # The exported grid is the fast grid.  Slow knots are exact members of it,
    # so np.interp introduces no additional time points or ambiguity.
    slow_on_fast = np.interp(fast_times, slow_times, slow_samples)
    n_bg = np.clip(slow_on_fast + fast_samples, -BACKGROUND_LIMIT_V, BACKGROUND_LIMIT_V)
    healthy = V_NOM + n_bg
    rows = []
    for time_ps, slow_v, fast_v, bg_v, healthy_v in zip(
            fast_times, slow_on_fast, fast_samples, n_bg, healthy):
        values = (int(time_ps), float(slow_v), float(fast_v), float(bg_v), float(healthy_v))
        if not all(math.isfinite(value) for value in values[1:]):
            raise ValueError("background contains a non-finite value")
        rows.append({
            "time_ps": values[0],
            "n_slow_v": values[1],
            "n_fast_v": values[2],
            "n_bg_v": values[3],
            "vdd_healthy_v": values[4],
        })
    return rows


def _format_si(value):
    """Render one finite SI value using locale-independent scientific notation."""

    number = float(value)
    if not math.isfinite(number):
        raise ValueError("cannot serialize non-finite value")
    return "{:.12e}".format(number)


def write_background(rows, csv_path, inc_path):
    """Write the shared background CSV and its one-port HSPICE PWL include."""

    csv_path = Path(csv_path)
    inc_path = Path(inc_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    inc_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="ascii") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["time_s", "n_slow_v", "n_fast_v", "n_bg_v", "vdd_healthy_v"])
        for row in rows:
            writer.writerow([
                _format_si(row["time_ps"] * 1.0e-12),
                _format_si(row["n_slow_v"]),
                _format_si(row["n_fast_v"]),
                _format_si(row["n_bg_v"]),
                _format_si(row["vdd_healthy_v"]),
            ])
    lines = [
        "* BFE7 W1 deterministic healthy background; seed={} PCG64.".format(SEED),
        "* Port map: positive monitored rail=vdd_monitored; local return=vss_a.",
        "* This include contains one supply source and no detector circuitry.",
        "{} PWL(".format(MONITORED_SOURCE),
    ]
    for index, row in enumerate(rows):
        suffix = ")" if index == len(rows) - 1 else ""
        lines.append("+ {} {}{}".format(
            _format_si(row["time_ps"] * 1.0e-12),
            _format_si(row["vdd_healthy_v"]),
            suffix,
        ))
    inc_path.write_text("\n".join(lines) + "\n", encoding="ascii")


def validate_background(rows):
    """Apply all W1 offline assertions before a background gate is published."""

    if not rows or rows[0]["time_ps"] != 0 or rows[-1]["time_ps"] != T_STOP_PS:
        raise ValueError("background must start at 0 ps and end at 65000 ps")
    times = [row["time_ps"] for row in rows]
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError("background times are not strictly increasing")
    for row in rows:
        for key in ("n_slow_v", "n_fast_v", "n_bg_v", "vdd_healthy_v"):
            if not math.isfinite(float(row[key])):
                raise ValueError("non-finite background field {}".format(key))
        if abs(float(row["n_bg_v"])) > BACKGROUND_LIMIT_V + 1.0e-15:
            raise ValueError("background exceeds +/-8 mV")
        if not (V_NOM - BACKGROUND_LIMIT_V - 1.0e-15 <= float(row["vdd_healthy_v"]) <=
                V_NOM + BACKGROUND_LIMIT_V + 1.0e-15):
            raise ValueError("healthy rail is outside the 1.092..1.108 V contract")


def main(argv=None):
    """Generate only W1 unless a later frozen contract is explicitly supplied."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    rows = generate_background(args.seed)
    validate_background(rows)
    background = args.output_dir / "normal_background"
    csv_path = background / "NBG_7301.csv"
    inc_path = background / "NBG_7301.inc"
    write_background(rows, csv_path, inc_path)
    metadata = {
        "schema_version": 1,
        "generator_version": SCRIPT_VERSION,
        "seed": SEED,
        "rng": "numpy.random.Generator(numpy.random.PCG64(7301))",
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "nominal_vdd_v": V_NOM,
        "temperature_c": TEMP_C,
        "stop_time_s": T_STOP_PS * 1.0e-12,
        "slow_knot_spacing_s": SLOW_SPACING_PS * 1.0e-12,
        "fast_knot_spacing_s": FAST_SPACING_PS * 1.0e-12,
        "background_limit_v": BACKGROUND_LIMIT_V,
        "csv_sha256": sha256_file(csv_path),
        "inc_sha256": sha256_file(inc_path),
        "simulation_accounting": {"hspice_runs": 0, "vcs_runs": 0, "dc_runs": 0, "primesim_runs": 0},
    }
    (background / "NBG_7301_METADATA.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    print("BFE7_W1_BACKGROUND_PASS rows={} csv_sha256={} inc_sha256={}".format(
        len(rows), metadata["csv_sha256"], metadata["inc_sha256"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
