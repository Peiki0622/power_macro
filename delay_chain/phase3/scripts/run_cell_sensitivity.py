#!/usr/bin/env python3
"""Run and summarize the Phase-3 RVT/LVT single-stage sweep.

Every candidate/voltage owns a separate directory.  HSPICE output names are
fixed by the tool, so this isolation is required to prevent one candidate from
silently replacing another candidate's listing or measurement file.
"""

import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
PHASE1_SCRIPTS = WORKSPACE_ROOT / "power_macro/delay_chain/phase1/scripts"
# Phase 1 already pins the compatible transistor-model path and local HSPICE
# executable.  Reusing only that collateral location avoids expanding the
# Phase-3 electrical configuration with a second source-of-truth copy.
PHASE1_CONFIG = WORKSPACE_ROOT / "power_macro/delay_chain/phase1/phase1_config.json"
EMPTY_SUBCKT_INCLUDE = WORKSPACE_ROOT / "power_macro/delay_chain/phase3/spice/includes/empty_subckt.sp_cal"
if str(PHASE1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PHASE1_SCRIPTS))
import run_dc_sweep  # noqa: E402  # Reuse the reviewed HSPICE completion/MEASFORM parser.
import generate_phase3_deck  # noqa: E402  # Render the exact deck under test.


FIELDS = [
    "candidate_id", "lvt_cell", "vdd_v", "rvt_rise_s", "rvt_fall_s", "rvt_stage_s",
    "lvt_rise_s", "lvt_fall_s", "lvt_stage_s", "delta_t_s", "delta_t_swing_s",
    "warning_count", "measurement_file",
]


def load_json(path: Path) -> Dict[str, Any]:
    """Load one required object configuration."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def finite(value: Optional[float], name: str) -> float:
    """Reject failed or non-finite HSPICE timing values."""

    if value is None or not math.isfinite(float(value)):
        raise ValueError("{} is missing or non-finite".format(name))
    return float(value)


def voltage_points(config: Dict[str, Any]) -> List[float]:
    """Build the 5 mV grid plus the exact non-grid violation anchor.

    The additional point is a real HSPICE scenario, not interpolation.  It is
    necessary because the timing failure voltage is more precise than a 5 mV
    grid position and Step 3 explicitly requires its differential delay.
    """

    current = Decimal(str(config["coarse_vdd_start_v"]))
    stop = Decimal(str(config["coarse_vdd_stop_v"]))
    step = Decimal(str(config["coarse_vdd_step_v"]))
    if step <= 0 or current > stop:
        raise ValueError("coarse sweep must ascend with a positive step")
    values: List[Decimal] = []
    while current <= stop:
        values.append(current)
        current += step
    if values[-1] != stop:
        raise ValueError("coarse grid does not land exactly on stop voltage")
    critical = Decimal(str(config["first_violation_v"]))
    if critical not in values:
        values.append(critical)
    return [float(value) for value in sorted(values)]


def scenario_name(candidate: str, voltage: float) -> str:
    """Keep voltage precision in a stable, filesystem-safe scenario label."""

    return "{}/v{:0.12f}".format(candidate, voltage).replace(".", "p")


def run_point(
    config: Dict[str, Any], selected: Dict[str, Any], hspice: Path, model_library: Path,
    run_dir: Path, lvt_item: Dict[str, Any], voltage: float,
) -> Dict[str, Any]:
    """Render, run, validate and decode one candidate/voltage experiment."""

    candidate_id = lvt_item["cell"]
    point_dir = run_dir / "scenarios" / scenario_name(candidate_id, voltage)
    point_dir.mkdir(parents=True, exist_ok=False)
    # The immutable vendor LVT CDL contains a relative no-op include.  HSPICE
    # resolves it from the scenario CWD, so copy only this task-owned comment
    # file beside the deck instead of changing the PDK or duplicating its CDL.
    if not EMPTY_SUBCKT_INCLUDE.is_file():
        raise ValueError("missing local LVT placeholder include: {}".format(EMPTY_SUBCKT_INCLUDE))
    shutil.copyfile(EMPTY_SUBCKT_INCLUDE, point_dir / "empty_subckt.sp_cal")
    deck_path = point_dir / "cell_sensitivity.sp"
    generate_phase3_deck.write_sensitivity_deck(
        output_path=deck_path,
        rvt_cdl=Path(selected["source_files"]["rvt_cdl"]),
        lvt_cdl=Path(selected["source_files"]["lvt_cdl"]),
        model_library=model_library,
        corner=str(config["corner"]),
        temperature_c=float(config["temperature_c"]),
        vdd_v=voltage,
        rvt_cell=str(config["rvt_inverter_cell"]),
        lvt_cell=candidate_id,
    )
    result = subprocess.run(
        [str(hspice), deck_path.name, "-o", "cell_sensitivity"],
        cwd=str(point_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True, check=False, timeout=180,
    )
    (point_dir / "hspice_command.log").write_text(
        "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            " ".join([str(hspice), deck_path.name, "-o", "cell_sensitivity"]),
            result.returncode, result.stdout, result.stderr,
        ), encoding="utf-8"
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, point_dir))
    warning_count = run_dc_sweep.validate_listing(point_dir / "cell_sensitivity.lis")
    measurement_path = run_dc_sweep.find_measurement_file(point_dir, "cell_sensitivity")
    measurements = run_dc_sweep.parse_measurements(measurement_path)
    rvt_rise = finite(measurements.get("rvt_rise_s"), "rvt_rise_s")
    rvt_fall = finite(measurements.get("rvt_fall_s"), "rvt_fall_s")
    lvt_rise = finite(measurements.get("lvt_rise_s"), "lvt_rise_s")
    lvt_fall = finite(measurements.get("lvt_fall_s"), "lvt_fall_s")
    rvt_stage = finite(measurements.get("rvt_stage_s"), "rvt_stage_s")
    lvt_stage = finite(measurements.get("lvt_stage_s"), "lvt_stage_s")
    return {
        "candidate_id": candidate_id,
        "lvt_cell": candidate_id,
        "vdd_v": voltage,
        "rvt_rise_s": rvt_rise,
        "rvt_fall_s": rvt_fall,
        "rvt_stage_s": rvt_stage,
        "lvt_rise_s": lvt_rise,
        "lvt_fall_s": lvt_fall,
        "lvt_stage_s": lvt_stage,
        "delta_t_s": rvt_stage - lvt_stage,
        "delta_t_swing_s": "",
        "warning_count": warning_count,
        "measurement_file": str(measurement_path.relative_to(run_dir)),
    }


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Write a rectangular timing contract consumed by reports and later steps."""

    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                field: "" if row[field] == "" else "{:.12e}".format(row[field]) if isinstance(row[field], float) else row[field]
                for field in FIELDS
            })


def write_report(path: Path, rows: List[Dict[str, Any]], swings: Dict[str, float]) -> None:
    """Publish tabulated curves and the exact anchor differential swing."""

    lines = [
        "# Cell Sensitivity",
        "",
        "Both structures use the same VDD_A/VSS_A source, PULSE, 1 fF output load, and VDD/2 thresholds.",
        "",
        "| LVT cell | VDD (V) | RVT stage (s) | LVT stage (s) | RVT-LVT (s) |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append("| `{lvt_cell}` | {vdd_v:.12f} | {rvt_stage_s:.12e} | {lvt_stage_s:.12e} | {delta_t_s:.12e} |".format(**row))
    lines.extend(["", "## Anchor differential swing", "", "| LVT cell | delta_t(1.047473942801)-delta_t(1.1) (s) |", "|---|---:|"])
    for cell, swing in sorted(swings.items()):
        lines.append("| `{}` | {:.12e} |".format(cell, swing))
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run the complete coarse Step-3 study and enforce its completion gate."""

    parser = argparse.ArgumentParser(description="run Phase-3 RVT/LVT cell sensitivity")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--selection-json", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    config = load_json(args.config)
    phase1 = load_json(PHASE1_CONFIG)
    selected = load_json(args.selection_json)
    hspice = run_dc_sweep.require_regular_file(Path("/home/zhupl25/.local/bin/hspice"), "HSPICE", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if "W-2024.09" not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    run_dir = args.output_dir.resolve()
    if run_dir.exists():
        raise ValueError("refusing to overwrite existing run directory: {}".format(run_dir))
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({"hspice_version": version, "study": "phase3_cell_sensitivity"}, indent=2) + "\n", encoding="utf-8")
    rows: List[Dict[str, Any]] = []
    model_library = Path(phase1["model_library"])
    candidates = selected["lvt_inverter_candidates"]
    for item in candidates:
        for voltage in voltage_points(config):
            rows.append(run_point(config, selected, hspice, model_library, run_dir, item, voltage))
    swings: Dict[str, float] = {}
    nominal = float(config["vnom_v"])
    critical = float(config["first_violation_v"])
    for item in candidates:
        group = [row for row in rows if row["lvt_cell"] == item["cell"]]
        nominal_row = min(group, key=lambda row: abs(row["vdd_v"] - nominal))
        critical_row = min(group, key=lambda row: abs(row["vdd_v"] - critical))
        if abs(nominal_row["vdd_v"] - nominal) > 1e-12 or abs(critical_row["vdd_v"] - critical) > 1e-12:
            raise ValueError("coarse grid does not contain required nominal/critical evidence for {}".format(item["cell"]))
        swing = critical_row["delta_t_s"] - nominal_row["delta_t_s"]
        swings[item["cell"]] = swing
        for row in group:
            row["delta_t_swing_s"] = swing
        if not all(math.isfinite(row["delta_t_s"]) for row in group):
            raise ValueError("non-finite differential delay for {}".format(item["cell"]))
    write_csv(run_dir / "cell_delay.csv", rows)
    report = WORKSPACE_ROOT / "power_macro/delay_chain/phase3/reports/CELL_SENSITIVITY.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    write_report(report, rows, swings)
    if not any(abs(value) > 0.0 for value in swings.values()):
        raise RuntimeError("no RVT/LVT differential delay swing was observed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
