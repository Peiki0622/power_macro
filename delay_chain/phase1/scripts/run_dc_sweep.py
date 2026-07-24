#!/usr/bin/env python3
"""Run the complete phase-1 SMIC40LL constant-VDD delay-chain sweep.

The runner is intentionally limited to phase 1.  It creates 16 canonical DC
voltages from 1.10 V through 0.95 V plus the exact 770 MHz FIR first-violation
voltage, for each of the 16/32/64-unit candidates.  It neither instantiates the
shared RLC network nor adds DFF loading, so its output is a delay calibration
and current budget, not a package-droop or self-disturbance claim.

All generated SPICE decks have a fixed positional standard-cell interface:
``Y VDD VNW VPW VSS A``.  The generator documents every instance and connects
the well pins to the same local rails as the corresponding power pins.  This
runner preserves each deck, listing, measurement result, command log, source
hash and raw timing crossing so a later result can be independently audited.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


# Importing through the script directory makes the command work without
# packaging this small one-phase tool as a project-wide Python distribution.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import generate_delay_chain  # noqa: E402  # The path insertion above is intentional.


RAW_FIXED_FIELDS = [
    "scenario_id",
    "scenario_kind",
    "chain_units",
    "inverter_count",
    "vdd_v",
    "start_cross_s",
    "stage_delay_s",
    "chain_delay_s",
    "i_avg_a",
    "i_peak_a",
    "power_avg_w",
    "warning_count",
    "measurement_file",
]


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 digest for a read-only study input."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_regular_file(path: Path, description: str, executable: bool = False) -> Path:
    """Validate one tool or collateral path before any task-owned output exists."""

    resolved = path.resolve()
    if not resolved.is_file() or resolved.stat().st_size == 0:
        raise ValueError("{} is missing, empty, or not a regular file: {}".format(description, resolved))
    if executable and not os.access(str(resolved), os.X_OK):
        raise ValueError("{} is not executable: {}".format(description, resolved))
    return resolved


def finite_number(value: str, description: str) -> float:
    """Parse one HSPICE scalar and reject failed/non-finite measurements."""

    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("{} is not numeric: {!r}".format(description, value)) from error
    if not math.isfinite(number):
        raise ValueError("{} is not finite: {!r}".format(description, value))
    return number


def optional_number(value: str) -> Optional[float]:
    """Return a finite scalar, or None for HSPICE's explicit failed measure token.

    A missing late tap is physically meaningful for a fixed-duration scan: it
    means the transition did not arrive before transient stop.  It is retained
    as an empty CSV field for analysis rather than silently converted to zero.
    """

    normalized = value.strip().lower()
    if normalized in ("", "failed", "fail"):
        return None
    return finite_number(value, "optional HSPICE measurement")


def parse_measurements(path: Path) -> Dict[str, Optional[float]]:
    """Read the single MEASFORM=3 header/data pair emitted by one deck.

    HSPICE may name the file ``.mt0`` or ``.mt0.csv`` by installation.  Its
    content has optional metadata lines beginning with ``$`` or ``.``, followed
    by exactly one comma-separated header and one result row.  Requiring that
    shape detects truncated, multi-alter, or partially written results.
    """

    text = require_regular_file(path, "HSPICE measurement file").read_text(
        encoding="latin-1", errors="replace"
    )
    data_lines = [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith(("$", "."))
    ]
    if len(data_lines) != 2:
        raise ValueError("measurement file must contain one header/data pair: {}".format(path))
    header = next(csv.reader([data_lines[0]]))
    values = next(csv.reader([data_lines[1]]))
    if len(header) != len(values):
        raise ValueError("measurement header/value length mismatch: {}".format(path))
    result = {}
    for name, value in zip(header, values):
        key = name.strip().lower()
        if key and key != "alter#":
            result[key] = optional_number(value)
    return result


def find_measurement_file(scenario_dir: Path, prefix: str) -> Path:
    """Accept the two known W-2024.09 measurement suffixes and no ambiguity."""

    candidates = [scenario_dir / (prefix + suffix) for suffix in (".mt0.csv", ".mt0")]
    existing = [candidate for candidate in candidates if candidate.is_file()]
    if len(existing) != 1:
        raise ValueError("expected exactly one HSPICE measure file, found {}".format(existing))
    return existing[0]


def validate_listing(path: Path) -> int:
    """Reject simulator failures while retaining any non-fatal warning evidence."""

    contents = require_regular_file(path, "HSPICE listing").read_text(
        encoding="latin-1", errors="replace"
    )
    lower = contents.lower()
    if "job concluded" not in lower:
        raise RuntimeError("HSPICE listing lacks completion marker: {}".format(path))
    for forbidden in (
        "fatal error",
        "syntax error",
        "singular matrix",
        "convergence problem",
        "job aborted",
        "**error**",
    ):
        if forbidden in lower:
            raise RuntimeError("HSPICE listing contains {}: {}".format(forbidden, path))
    return sum(1 for line in contents.splitlines() if "**warning**" in line.lower())


def hspice_version(hspice: Path) -> str:
    """Read the executable version before beginning a run that uses licensed EDA."""

    result = subprocess.run(
        [str(hspice), "-v"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE -v failed with {}".format(result.returncode))
    return result.stdout.strip()


def voltage_points(config: Dict[str, Any]) -> List[Tuple[str, float]]:
    """Build the canonical 0--150 mV sweep plus one non-duplicate diagnostic point."""

    vnom = float(config["vnom_v"])
    step = float(config["scan_step_v"])
    drops = int(config["scan_drop_count"])
    points = [("canonical_{:03d}mv".format(drop * 10), vnom - step * drop) for drop in range(drops + 1)]
    violation_v = float(config["first_violation_voltage_v"])
    if not any(abs(voltage - violation_v) <= 1.0e-12 for _, voltage in points):
        points.append(("first_violation", violation_v))
    return points


def scenario_directory_name(chain_units: int, kind: str, vdd_v: float) -> str:
    """Make a portable, readable path with voltage precision preserved in metadata."""

    return "chain_{:02d}/{}_v{:0.12f}".format(chain_units, kind, vdd_v).replace(".", "p")


def require_measurements(measurements: Dict[str, Optional[float]], chain_units: int) -> None:
    """Require rail-current and START measures; taps may be late but are recorded."""

    required = ["start_cross", "i_avg_a", "i_peak_a", "power_avg_w"]
    missing = [name for name in required if measurements.get(name) is None]
    if missing:
        raise ValueError("required HSPICE measurements are absent or failed: {}".format(missing))
    for name in generate_delay_chain.tap_measure_names(chain_units):
        if name not in measurements:
            raise ValueError("measurement file lacks required tap measure: {}".format(name))


def run_scenario(
    config: Dict[str, Any],
    hspice: Path,
    run_dir: Path,
    chain_units: int,
    kind: str,
    vdd_v: float,
    timeout_s: int,
) -> Dict[str, Any]:
    """Generate, execute, validate and summarize one isolated HSPICE scenario.

    Each scenario owns one directory so HSPICE's fixed extension-based output
    names cannot collide across voltages or candidates.  The function writes a
    command log before interpreting outputs, which preserves stderr even when a
    later validation guard rejects an otherwise zero exit status.
    """

    scenario_dir = run_dir / "scenarios" / scenario_directory_name(chain_units, kind, vdd_v)
    scenario_dir.mkdir(parents=True, exist_ok=False)
    deck_path = scenario_dir / "delay_chain.sp"
    prefix = "delay_chain"
    generate_delay_chain.write_deck(config, chain_units, vdd_v, deck_path)

    result = subprocess.run(
        [str(hspice), deck_path.name, "-o", prefix],
        cwd=str(scenario_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        timeout=timeout_s,
    )
    (scenario_dir / "hspice_command.log").write_text(
        "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            " ".join([str(hspice), deck_path.name, "-o", prefix]),
            result.returncode,
            result.stdout,
            result.stderr,
        ),
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, scenario_dir))
    warning_count = validate_listing(scenario_dir / (prefix + ".lis"))
    measurement_path = find_measurement_file(scenario_dir, prefix)
    measurements = parse_measurements(measurement_path)
    require_measurements(measurements, chain_units)

    row = {
        "scenario_id": scenario_directory_name(chain_units, kind, vdd_v),
        "scenario_kind": kind,
        "chain_units": chain_units,
        "inverter_count": chain_units * 2,
        "vdd_v": vdd_v,
        "start_cross_s": measurements["start_cross"],
        "stage_delay_s": measurements.get("stage_delay_s"),
        "chain_delay_s": measurements.get("chain_delay_s"),
        "i_avg_a": measurements["i_avg_a"],
        "i_peak_a": measurements["i_peak_a"],
        "power_avg_w": measurements["power_avg_w"],
        "warning_count": warning_count,
        "measurement_file": str(measurement_path.relative_to(run_dir)),
    }
    for index, name in enumerate(generate_delay_chain.tap_measure_names(chain_units)):
        row["tap_{:03d}_cross_s".format(index)] = measurements[name]
    return row


def csv_value(value: Any) -> str:
    """Render optional numeric evidence without inventing a value for a failed tap."""

    if value is None:
        return ""
    if isinstance(value, float):
        return "{:.12e}".format(value)
    return str(value)


def write_raw_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    """Write one rectangular raw-evidence table with columns for all 64 taps."""

    tap_fields = ["tap_{:03d}_cross_s".format(index) for index in range(64)]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=RAW_FIXED_FIELDS + tap_fields, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in RAW_FIXED_FIELDS + tap_fields})


def build_manifest(config: Dict[str, Any], hspice: Path, version: str) -> Dict[str, Any]:
    """Freeze all executable and source provenance used by this run."""

    cdl = require_regular_file(generate_delay_chain.resolve_input_path(config["cell_cdl"]), "standard-cell CDL")
    model = require_regular_file(generate_delay_chain.resolve_input_path(config["model_library"]), "SMIC40LL TT model")
    return {
        "study_name": config.get("study_name"),
        "technology": config.get("technology"),
        "corner": config.get("corner"),
        "temperature_c": config.get("temperature_c"),
        "hspice": {"executable": str(hspice), "version": version},
        "inputs": {
            "cell_cdl": {"path": str(cdl), "sha256": sha256_file(cdl)},
            "model_library": {"path": str(model), "sha256": sha256_file(model)},
        },
        "scan": {
            "chain_lengths": config["chain_lengths"],
            "canonical_vnom_v": config["vnom_v"],
            "canonical_step_v": config["scan_step_v"],
            "canonical_drop_count": config["scan_drop_count"],
            "first_violation_voltage_v": config["first_violation_voltage_v"],
            "scenario_count": len(config["chain_lengths"]) * len(voltage_points(config)),
        },
    }


def build_argument_parser() -> argparse.ArgumentParser:
    """Define the non-overwriting full-sweep command-line contract."""

    parser = argparse.ArgumentParser(description="Run phase-1 SMIC40LL constant-VDD delay-chain scan")
    parser.add_argument("--config", required=True, type=Path, help="phase1_config.json path")
    parser.add_argument("--output-dir", required=True, type=Path, help="new task-owned run directory")
    parser.add_argument("--timeout-s", type=int, default=300, help="per-HSPICE-scenario timeout in seconds")
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run all candidates only after every immutable input passes preflight."""

    args = build_argument_parser().parse_args(argv)
    if args.timeout_s <= 0:
        raise ValueError("--timeout-s must be positive")
    config = generate_delay_chain.load_config(args.config)
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise ValueError("refusing to overwrite existing output directory: {}".format(output_dir))

    hspice = require_regular_file(Path(config["hspice"]), "HSPICE executable", executable=True)
    version = hspice_version(hspice)
    expected_version = str(config["expected_hspice_version"])
    if expected_version not in version:
        raise RuntimeError("expected HSPICE {}, received {}".format(expected_version, version))
    # Validate all hashes before creating output so an unavailable PDK never
    # leaves a directory that could be mistaken for an incomplete experiment.
    manifest = build_manifest(config, hspice, version)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir()
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    rows = []
    for chain_units in config["chain_lengths"]:
        for kind, voltage in voltage_points(config):
            rows.append(run_scenario(config, hspice, output_dir, int(chain_units), kind, voltage, args.timeout_s))
    write_raw_csv(output_dir / "raw_sweep_metrics.csv", rows)
    (output_dir / "completion.rpt").write_text(
        "status=PASS\nscenario_count={}\nraw_metrics=raw_sweep_metrics.csv\n".format(len(rows)),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
