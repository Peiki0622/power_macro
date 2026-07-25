#!/usr/bin/env python3
"""Characterize the three voltage anchors inherited from the 765 MHz study.

This runner intentionally reuses Phase 1's standard-cell deck renderer and
HSPICE result parser.  The inherited Phase 1 configuration is read only: the
old 770 MHz first-violation voltage remains historical evidence, while this
script supplies the 765 MHz nominal, last-passing, and first-violating values
as individual scenarios.  Keeping the new evidence below ``phase2_vernier``
prevents accidental reinterpretation or overwrite of the completed Phase 1
study.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


# The Phase 1 scripts are intentionally imported as reviewed source modules.
# They own the foundry CDL positional-port rendering and defensive HSPICE
# parser, so this wrapper does not duplicate a second, potentially divergent
# implementation of either safety-critical operation.
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PHASE1_SCRIPTS = REPOSITORY_ROOT / "power_macro" / "delay_chain" / "phase1" / "scripts"
if str(PHASE1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PHASE1_SCRIPTS))
import generate_delay_chain  # noqa: E402  # Path setup above is required for direct CLI use.
import run_dc_sweep  # noqa: E402  # Phase 1 owns raw-result validation and CSV layout.


ANCHOR_KINDS = (
    "anchor_nominal",
    "anchor_last_passing",
    "anchor_first_violation",
)


def load_json(path: Path) -> Dict[str, Any]:
    """Read one configuration object and reject non-object JSON documents."""

    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("configuration must be a JSON object: {}".format(path))
    return value


def resolve_repo_path(value: str) -> Path:
    """Resolve a repository-relative collateral path without using CWD state."""

    path = Path(value)
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def anchor_points(phase2_config: Dict[str, Any]) -> List[Tuple[str, float]]:
    """Pair the declared scenario names with the exact 765 MHz anchor voltages.

    The order is fixed because downstream reports use these semantic names,
    not rounded values, to distinguish the safe 35-bank point from the first
    40-bank violation.  Exact values are retained at full CSV precision.
    """

    voltages = phase2_config.get("phase1_anchor_voltages_v")
    if not isinstance(voltages, list) or len(voltages) != len(ANCHOR_KINDS):
        raise ValueError("phase1_anchor_voltages_v must contain exactly three values")
    points = []
    for kind, voltage in zip(ANCHOR_KINDS, voltages):
        parsed = float(voltage)
        if parsed <= 0.0:
            raise ValueError("{} voltage must be positive".format(kind))
        points.append((kind, parsed))
    if not points[0][1] > points[1][1] > points[2][1]:
        raise ValueError("anchor voltages must be nominal > last-passing > first-violation")
    return points


def write_manifest(
    output_dir: Path,
    phase2_config_path: Path,
    phase1_config_path: Path,
    phase1_config: Dict[str, Any],
    hspice: Path,
    version: str,
    points: List[Tuple[str, float]],
) -> None:
    """Persist enough immutable provenance to independently audit every run."""

    manifest = {
        "study_name": "phase2_765mhz_phase1_anchor_characterization",
        "phase2_config": str(phase2_config_path.resolve()),
        "phase1_config": str(phase1_config_path.resolve()),
        "hspice": {"executable": str(hspice), "version": version},
        "technology": phase1_config["technology"],
        "corner": phase1_config["corner"],
        "temperature_c": phase1_config["temperature_c"],
        "anchors": [{"scenario_kind": kind, "vdd_v": voltage} for kind, voltage in points],
        "inputs": {
            "cell_cdl": str(generate_delay_chain.resolve_input_path(phase1_config["cell_cdl"])),
            "model_library": str(generate_delay_chain.resolve_input_path(phase1_config["model_library"])),
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def build_argument_parser() -> argparse.ArgumentParser:
    """Define a non-overwriting CLI for the task-scoped anchor experiment."""

    parser = argparse.ArgumentParser(description="run 765 MHz Phase 1 anchor characterizations")
    parser.add_argument("--config", required=True, type=Path, help="Phase 2 configuration path")
    parser.add_argument("--output-dir", required=True, type=Path, help="new Phase 2 run directory")
    parser.add_argument("--timeout-s", type=int, default=180, help="per-deck HSPICE timeout")
    return parser


def main(argv: Iterable[str] = None) -> int:
    """Run all 3x3 anchor decks and write one rectangular raw-evidence CSV."""

    args = build_argument_parser().parse_args(argv)
    phase2_config_path = args.config.resolve()
    phase2_config = load_json(phase2_config_path)
    phase1_config_path = resolve_repo_path(str(phase2_config["phase1_config_path"]))
    phase1_config = generate_delay_chain.load_config(phase1_config_path)
    points = anchor_points(phase2_config)

    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise ValueError("refusing to overwrite existing anchor run directory: {}".format(output_dir))
    output_dir.mkdir(parents=True)

    hspice = run_dc_sweep.require_regular_file(Path(phase1_config["hspice"]), "HSPICE", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if phase1_config["expected_hspice_version"] not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    write_manifest(output_dir, phase2_config_path, phase1_config_path, phase1_config, hspice, version, points)

    rows = []
    for chain_units in phase1_config["chain_lengths"]:
        for kind, voltage in points:
            rows.append(
                run_dc_sweep.run_scenario(
                    phase1_config,
                    hspice,
                    output_dir,
                    int(chain_units),
                    kind,
                    voltage,
                    args.timeout_s,
                )
            )
    run_dc_sweep.write_raw_csv(output_dir / "raw_anchor_metrics.csv", rows)
    (output_dir / "completion.rpt").write_text(
        "status=PASS\nscenario_count={}\n".format(len(rows)), encoding="ascii"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
