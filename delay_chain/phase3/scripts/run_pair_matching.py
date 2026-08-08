#!/usr/bin/env python3
"""Match nominal RVT/LVT stage delays with real LVT input loads.

The runner intentionally performs only the three Phase-1 timing-anchor
voltages.  It retains all raw HSPICE evidence and publishes a small table that
can be consumed by the ideal 32-stage experiment without carrying every
unselected combination forward.
"""

import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
PHASE1_CONFIG = WORKSPACE_ROOT / "power_macro/delay_chain/phase1/phase1_config.json"
PHASE1_SCRIPTS = WORKSPACE_ROOT / "power_macro/delay_chain/phase1/scripts"
EMPTY_SUBCKT_INCLUDE = WORKSPACE_ROOT / "power_macro/delay_chain/phase3/spice/includes/empty_subckt.sp_cal"
if str(PHASE1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PHASE1_SCRIPTS))
import run_dc_sweep  # noqa: E402  # Preserve the established HSPICE validators.
import generate_phase3_deck  # noqa: E402  # Test the exact matching topology.


FIELDS = [
    "candidate_id", "lvt_cell", "dummy_load_count", "t_r_nom_s", "t_l_nom_s", "nominal_gap_s",
    "delta_t_last_pass_s", "delta_t_first_violation_s", "g_droop_s", "measurement_files",
]


def load_json(path: Path) -> Dict[str, Any]:
    """Load one required JSON object."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def run_point(
    config: Dict[str, Any], selected: Dict[str, Any], phase1: Dict[str, Any],
    hspice: Path, run_dir: Path, item: Dict[str, Any], dummy_count: int, voltage: float,
) -> Dict[str, Any]:
    """Run one candidate/dummy/anchor directory and return measured stage delays."""

    label = "{}_d{}_v{:0.12f}".format(item["cell"], dummy_count, voltage).replace(".", "p")
    point_dir = run_dir / "scenarios" / label
    point_dir.mkdir(parents=True, exist_ok=False)
    if not EMPTY_SUBCKT_INCLUDE.is_file():
        raise ValueError("missing local LVT placeholder include")
    shutil.copyfile(EMPTY_SUBCKT_INCLUDE, point_dir / "empty_subckt.sp_cal")
    deck = point_dir / "pair_matching.sp"
    generate_phase3_deck.write_pair_matching_deck(
        output_path=deck,
        rvt_cdl=Path(selected["source_files"]["rvt_cdl"]),
        lvt_cdl=Path(selected["source_files"]["lvt_cdl"]),
        model_library=Path(phase1["model_library"]),
        corner=str(config["corner"]), temperature_c=float(config["temperature_c"]), vdd_v=voltage,
        rvt_cell=str(config["rvt_inverter_cell"]), lvt_cell=item["cell"], dummy_load_count=dummy_count,
    )
    result = subprocess.run(
        [str(hspice), deck.name, "-o", "pair_matching"], cwd=str(point_dir),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=180,
    )
    (point_dir / "hspice_command.log").write_text(
        "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            " ".join([str(hspice), deck.name, "-o", "pair_matching"]), result.returncode, result.stdout, result.stderr,
        ), encoding="utf-8"
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, point_dir))
    warning_count = run_dc_sweep.validate_listing(point_dir / "pair_matching.lis")
    measurement = run_dc_sweep.find_measurement_file(point_dir, "pair_matching")
    values = run_dc_sweep.parse_measurements(measurement)
    required = ["rvt_stage_s", "lvt_stage_s"]
    if any(values.get(name) is None or not math.isfinite(float(values[name])) for name in required):
        raise ValueError("missing pair timing measure at {}".format(point_dir))
    return {
        "cell": item["cell"], "dummy_load_count": dummy_count, "vdd_v": voltage,
        "rvt_stage_s": float(values["rvt_stage_s"]), "lvt_stage_s": float(values["lvt_stage_s"]),
        "delta_t_s": float(values["rvt_stage_s"]) - float(values["lvt_stage_s"]),
        "warning_count": warning_count, "measurement_file": str(measurement.relative_to(run_dir)),
    }


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Write the exact comparison fields required by the Phase-3 plan."""

    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                field: "" if row[field] == "" else "{:.12e}".format(row[field]) if isinstance(row[field], float) else row[field]
                for field in FIELDS
            })


def pareto_front(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return pairs not dominated in nominal gap (low) and droop gain (high)."""

    front = []
    for candidate in rows:
        dominated = any(
            other is not candidate
            and other["nominal_gap_s"] <= candidate["nominal_gap_s"]
            and other["g_droop_s"] >= candidate["g_droop_s"]
            and (
                other["nominal_gap_s"] < candidate["nominal_gap_s"]
                or other["g_droop_s"] > candidate["g_droop_s"]
            )
            for other in rows
        )
        if not dominated:
            front.append(candidate)
    return front


def write_report(path: Path, rows: List[Dict[str, Any]], selected: List[Dict[str, Any]]) -> None:
    """Publish all pair metrics and the deterministic short-list decision."""

    selected_ids = {row["candidate_id"] for row in selected}
    lines = [
        "# Pair Selection",
        "",
        "RVT is fixed at 2 x INV_X0P5M_A9TR40; only LVT cell and dummy input count vary.",
        "",
        "| Candidate | LVT cell | Dummy | t_R nominal (s) | t_L nominal (s) | E_nom (s) | delta_t last-pass (s) | delta_t first-violation (s) | G_droop (s) | Selected |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| `{candidate_id}` | `{lvt_cell}` | {dummy_load_count} | {t_r_nom_s:.12e} | {t_l_nom_s:.12e} | {nominal_gap_s:.12e} | {delta_t_last_pass_s:.12e} | {delta_t_first_violation_s:.12e} | {g_droop_s:.12e} | {} |".format(
                "yes" if row["candidate_id"] in selected_ids else "no", **row
            )
        )
    lines.extend(["", "Selected pairs are the non-dominated front, limited to three by E_nom ascending then G_droop descending.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Execute all 36 real decks and emit a no-more-than-three selection."""

    parser = argparse.ArgumentParser(description="run Phase-3 nominal pair matching")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--selection-json", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    config = load_json(args.config)
    selected = load_json(args.selection_json)
    phase1 = load_json(PHASE1_CONFIG)
    hspice = run_dc_sweep.require_regular_file(Path("/home/zhupl25/.local/bin/hspice"), "HSPICE", executable=True)
    if "W-2024.09" not in run_dc_sweep.hspice_version(hspice):
        raise RuntimeError("unexpected HSPICE version")
    run_dir = args.output_dir.resolve()
    if run_dir.exists():
        raise ValueError("refusing to overwrite existing pair-matching run")
    run_dir.mkdir(parents=True)
    anchors = [float(config["vnom_v"]), float(config["last_pass_v"]), float(config["first_violation_v"])]
    raw: List[Dict[str, Any]] = []
    for item in selected["lvt_inverter_candidates"]:
        for dummy_count in range(4):
            for voltage in anchors:
                raw.append(run_point(config, selected, phase1, hspice, run_dir, item, dummy_count, voltage))
    summary: List[Dict[str, Any]] = []
    for item in selected["lvt_inverter_candidates"]:
        for dummy_count in range(4):
            group = [row for row in raw if row["cell"] == item["cell"] and row["dummy_load_count"] == dummy_count]
            by_voltage = {round(row["vdd_v"], 12): row for row in group}
            nominal = by_voltage[round(anchors[0], 12)]
            last_pass = by_voltage[round(anchors[1], 12)]
            critical = by_voltage[round(anchors[2], 12)]
            delta_last = last_pass["delta_t_s"] - nominal["delta_t_s"]
            delta_critical = critical["delta_t_s"] - nominal["delta_t_s"]
            summary.append({
                "candidate_id": "{}_d{}".format(item["cell"], dummy_count),
                "lvt_cell": item["cell"], "dummy_load_count": dummy_count,
                "t_r_nom_s": nominal["rvt_stage_s"], "t_l_nom_s": nominal["lvt_stage_s"],
                "nominal_gap_s": abs(nominal["delta_t_s"]),
                "delta_t_last_pass_s": delta_last, "delta_t_first_violation_s": delta_critical,
                "g_droop_s": abs(delta_critical),
                "measurement_files": ";".join(row["measurement_file"] for row in group),
            })
    front = pareto_front(summary)
    selected_pairs = sorted(front, key=lambda row: (row["nominal_gap_s"], -row["g_droop_s"], row["candidate_id"]))[:3]
    write_csv(run_dir / "pair_results.csv", summary)
    report = WORKSPACE_ROOT / "power_macro/delay_chain/phase3/reports/PAIR_SELECTION.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    write_report(report, summary, selected_pairs)
    (run_dir / "selected_pairs.json").write_text(json.dumps({"schema_version": 1, "selected_pairs": selected_pairs, "pareto_count": len(front)}, indent=2) + "\n", encoding="utf-8")
    if not selected_pairs:
        raise RuntimeError("no practical RVT/LVT pair survived matching")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
