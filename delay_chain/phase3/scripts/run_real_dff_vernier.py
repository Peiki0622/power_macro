#!/usr/bin/env python3
"""Run the Phase-3 same-rail 32-DFF comparator bank at three anchors.

The HSPICE deck is the source of the thermometer word in this step.  Python
only converts the measured Q levels into the documented decoder representation;
it never substitutes ideal arrival timestamps for the real DFF result.
"""

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
PHASE1_CONFIG = WORKSPACE_ROOT / "power_macro/delay_chain/phase1/phase1_config.json"
PHASE1_SCRIPTS = WORKSPACE_ROOT / "power_macro/delay_chain/phase1/scripts"
PHASE2_SCRIPTS = WORKSPACE_ROOT / "power_macro/delay_chain/phase2_vernier/scripts"
PHASE3_SCRIPTS = Path(__file__).resolve().parent
EMPTY_SUBCKT_INCLUDE = WORKSPACE_ROOT / "power_macro/delay_chain/phase3/spice/includes/empty_subckt.sp_cal"
for import_path in (PHASE1_SCRIPTS, PHASE2_SCRIPTS, PHASE3_SCRIPTS):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))
import decode_vernier_code  # noqa: E402  # Shared majority/thermometer decoder.
import generate_phase3_deck  # noqa: E402  # Real standard-cell Step-6 deck renderer.
import run_dc_sweep  # noqa: E402  # HSPICE listing and MEASFORM validation.


CSV_FIELDS = [
    "scenario_id", "vdd_v", "launch_offset_ps", "raw_thermometer_word", "normalized_raw_word",
    "corrected_thermometer_word", "sensor_code", "raw_bubble_count", "bubble_count",
    "code_valid", "reset_failure_count", "measurement_file",
]


def load_json(path: Path) -> Dict[str, Any]:
    """Read one required JSON object and reject malformed collateral."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def parse_anchor_voltages(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return exactly the nominal, last-pass, and first-violation scenarios."""

    return [
        {"label": "nominal", "vdd_v": float(config["vnom_v"])},
        {"label": "last_pass", "vdd_v": float(config["last_pass_v"])},
        {"label": "first_violation", "vdd_v": float(config["first_violation_v"])},
    ]


def normalized_word(raw_word: str, invert: bool) -> str:
    """Apply the selected raw thermometer polarity before majority correction."""

    if not invert:
        return raw_word
    return "".join("1" if bit == "0" else "0" for bit in raw_word)


def run_point(
    config: Dict[str, Any], selected: Dict[str, Any], phase1: Dict[str, Any], hspice: Path,
    output_dir: Path, voltage: Dict[str, Any], timeout_s: int, launch_offset_ps: float,
) -> Dict[str, Any]:
    """Run one real-DFF anchor and decode all 32 measured Q levels."""

    label = str(voltage["label"])
    point_dir = output_dir / "scenarios" / label
    point_dir.mkdir(parents=True, exist_ok=False)
    # The installed LVT CDL references its historical sibling include by a
    # relative name.  Copy the Phase-3 read-only placeholder into this
    # task-owned directory so HSPICE resolves that dependency without changing
    # the PDK library or scattering generated files into the source tree.
    if not EMPTY_SUBCKT_INCLUDE.is_file():
        raise ValueError("missing Phase-3 empty_subckt.sp_cal placeholder")
    shutil.copyfile(EMPTY_SUBCKT_INCLUDE, point_dir / "empty_subckt.sp_cal")
    deck_path = point_dir / "phase3_real_dff.sp"
    generate_phase3_deck.write_real_dff_vernier_deck(
        output_path=deck_path,
        rvt_cdl=Path(selected["source_files"]["rvt_cdl"]),
        lvt_cdl=Path(selected["source_files"]["lvt_cdl"]),
        model_library=Path(phase1["model_library"]),
        corner=str(config["corner"]), temperature_c=float(config["temperature_c"]),
        vdd_v=float(voltage["vdd_v"]), rvt_cell=str(config["rvt_inverter_cell"]),
        lvt_cell=str(config["selected_lvt_cell"]), dff_cell=str(config["rvt_dff_cell"]),
        stages=int(config["stages"]), lvt_dummy_load_count=int(config["selected_dummy_load_count"]),
        # Step 6 may need a small source-offset correction for the real DFF
        # setup aperture.  This is kept explicit in the CSV and is replaced by
        # the physical BUF/MXT2 calibration path in Step 7.
        launch_offset_ps=launch_offset_ps,
        launch_delayed_path=str(config["ideal_launch_delayed_path"]),
    )
    result = subprocess.run(
        [str(hspice), deck_path.name, "-o", "phase3_real_dff"], cwd=str(point_dir),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
        check=False, timeout=timeout_s,
    )
    (point_dir / "hspice_command.log").write_text(
        "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            " ".join([str(hspice), deck_path.name, "-o", "phase3_real_dff"]),
            result.returncode, result.stdout, result.stderr,
        ), encoding="utf-8"
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, point_dir))
    run_dc_sweep.validate_listing(point_dir / "phase3_real_dff.lis")
    measurement = run_dc_sweep.find_measurement_file(point_dir, "phase3_real_dff")
    values = run_dc_sweep.parse_measurements(measurement)
    stages = int(config["stages"])
    raw_bits: List[str] = []
    reset_failures = 0
    threshold = 0.1 * float(voltage["vdd_v"])
    for index in range(stages):
        reset_level = values.get("q_{:03d}_reset_level".format(index))
        q_level = values.get("q_{:03d}_level".format(index))
        if reset_level is None or q_level is None:
            raise ValueError("missing q_{:03d} reset or capture measurement".format(index))
        if float(reset_level) > threshold:
            reset_failures += 1
        raw_bits.append("1" if float(q_level) >= 0.5 * float(voltage["vdd_v"]) else "0")
    raw_word = "".join(raw_bits)
    normalized = normalized_word(raw_word, bool(config.get("thermometer_invert", False)))
    decoded = decode_vernier_code.decode_word(normalized)
    return {
        "scenario_id": label,
        "vdd_v": float(voltage["vdd_v"]),
        "launch_offset_ps": launch_offset_ps,
        "raw_thermometer_word": raw_word,
        "normalized_raw_word": decoded["raw_code"],
        "corrected_thermometer_word": decoded["corrected_code"],
        "sensor_code": int(decoded["sensor_code"]),
        "raw_bubble_count": int(decoded["raw_bubble_count"]),
        "bubble_count": int(decoded["bubble_count"]),
        "code_valid": int(bool(decoded["code_valid"])),
        "reset_failure_count": reset_failures,
        "measurement_file": str(measurement.relative_to(output_dir)),
    }


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Write the Step-6 real-DFF evidence with both raw and corrected words."""

    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in CSV_FIELDS})


def write_report(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Publish a compact anchor table and the explicit completion checks."""

    lines = [
        "# Phase-3 Real Same-Rail DFF",
        "",
        "D=LVT tap, CK=RVT tap; all 32 DFF supply and well pins use VDD_A/VSS_A.",
        "",
        "| Scenario | VDD (V) | Source offset (ps) | Raw word | Corrected word | Code | Raw bubbles | Bubbles | Valid | Reset failures |",
        "|---|---:|---:|---|---|---:|---:|---:|---|---:|",
    ]
    for row in rows:
        lines.append(
            "| {scenario_id} | {vdd_v:.12f} | {launch_offset_ps:.6f} | `{raw_thermometer_word}` | `{corrected_thermometer_word}` | {sensor_code} | {raw_bubble_count} | {bubble_count} | {code_valid} | {reset_failure_count} |".format(**row)
        )
    lines.extend(["", "All data is sourced from `runs/real_dff/scenarios/*/phase3_real_dff.mt0.csv`.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run exactly three Step-6 anchors and enforce reset/thermometer validity."""

    parser = argparse.ArgumentParser(description="run Phase-3 real same-rail DFF bank")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout-s", type=int, default=300)
    parser.add_argument("--launch-offset-ps", type=float, default=None, help="temporary Step-6 source offset for real-DFF setup calibration")
    args = parser.parse_args(argv)
    config = load_json(args.config)
    selected = load_json(WORKSPACE_ROOT / "power_macro/delay_chain/phase3/discovery/selected_cells.json")
    phase1 = load_json(PHASE1_CONFIG)
    hspice = run_dc_sweep.require_regular_file(Path("/home/zhupl25/.local/bin/hspice"), "HSPICE", executable=True)
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise ValueError("refusing to overwrite existing real-DFF run directory")
    output_dir.mkdir(parents=True)
    launch_offset_ps = float(config["ideal_launch_offset_ps"]) if args.launch_offset_ps is None else float(args.launch_offset_ps)
    if launch_offset_ps < 0.0:
        raise ValueError("--launch-offset-ps must not be negative")
    rows = [run_point(config, selected, phase1, hspice, output_dir, point, args.timeout_s, launch_offset_ps) for point in parse_anchor_voltages(config)]
    write_csv(output_dir / "real_dff.csv", rows)
    write_report(WORKSPACE_ROOT / "power_macro/delay_chain/phase3/reports/REAL_DFF.md", rows)
    (output_dir / "completion.rpt").write_text(
        "status={}\nscenario_count={}\n".format(
            "PASS" if all(row["code_valid"] and row["reset_failure_count"] == 0 for row in rows) else "FAIL", len(rows)
        ), encoding="ascii"
    )
    if not all(row["code_valid"] and row["reset_failure_count"] == 0 for row in rows):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
