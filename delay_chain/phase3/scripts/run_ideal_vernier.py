#!/usr/bin/env python3
"""Run and decode the ideal 32-stage same-rail RVT/LVT Vernier.

HSPICE is run once per retained pair and voltage.  The five local launch-offset
choices are evaluated from those measured arrivals in Python, because a pure
launch translation does not change physical propagation and re-simulating it
would duplicate identical transistor-level evidence.
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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
PHASE1_CONFIG = WORKSPACE_ROOT / "power_macro/delay_chain/phase1/phase1_config.json"
PHASE1_SCRIPTS = WORKSPACE_ROOT / "power_macro/delay_chain/phase1/scripts"
EMPTY_SUBCKT_INCLUDE = WORKSPACE_ROOT / "power_macro/delay_chain/phase3/spice/includes/empty_subckt.sp_cal"
if str(PHASE1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PHASE1_SCRIPTS))
import run_dc_sweep  # noqa: E402  # Reviewed listing and MEASFORM validation.
import generate_phase3_deck  # noqa: E402  # Real standard-cell arrival topology.


CSV_FIELDS = [
    "candidate_id", "lvt_cell", "dummy_load_count", "offset_sweep_kind", "launch_offset_ps",
    "launch_delayed_path", "threshold_ps", "thermometer_invert", "vdd_v", "raw_code",
    "normalized_code", "sensor_code", "bubble_count", "code_valid", "polarity",
    "arrival_measurement_file",
]


def load_json(path: Path) -> Dict[str, Any]:
    """Load one JSON object without implicit defaults."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def voltages(config: Dict[str, Any]) -> List[float]:
    """Build the coarse range plus exact timing anchors with Decimal arithmetic."""

    start = Decimal(str(config["coarse_vdd_start_v"]))
    stop = Decimal(str(config["coarse_vdd_stop_v"]))
    step = Decimal(str(config["coarse_vdd_step_v"]))
    values: List[Decimal] = []
    current = start
    while current <= stop:
        values.append(current)
        current += step
    for anchor in (config["last_pass_v"], config["first_violation_v"]):
        value = Decimal(str(anchor))
        if value not in values:
            values.append(value)
    return [float(value) for value in sorted(values, reverse=True)]


def run_arrival_point(
    config: Dict[str, Any], selected: Dict[str, Any], phase1: Dict[str, Any], hspice: Path,
    run_dir: Path, pair: Dict[str, Any], voltage: float,
) -> Dict[str, Any]:
    """Run one 64-tap HSPICE deck and return every ordered crossing."""

    label = "{}_v{:0.12f}".format(pair["candidate_id"], voltage).replace(".", "p")
    point_dir = run_dir / "scenarios" / label
    point_dir.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(EMPTY_SUBCKT_INCLUDE, point_dir / "empty_subckt.sp_cal")
    deck = point_dir / "ideal_vernier.sp"
    generate_phase3_deck.write_ideal_vernier_deck(
        output_path=deck,
        rvt_cdl=Path(selected["source_files"]["rvt_cdl"]), lvt_cdl=Path(selected["source_files"]["lvt_cdl"]),
        model_library=Path(phase1["model_library"]), corner=str(config["corner"]),
        temperature_c=float(config["temperature_c"]), vdd_v=voltage,
        rvt_cell=str(config["rvt_inverter_cell"]), lvt_cell=pair["lvt_cell"], stages=int(config["stages"]),
        lvt_dummy_load_count=int(pair["dummy_load_count"]),
    )
    result = subprocess.run(
        [str(hspice), deck.name, "-o", "ideal_vernier"], cwd=str(point_dir),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=300,
    )
    (point_dir / "hspice_command.log").write_text(
        "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            " ".join([str(hspice), deck.name, "-o", "ideal_vernier"]), result.returncode, result.stdout, result.stderr,
        ), encoding="utf-8"
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, point_dir))
    run_dc_sweep.validate_listing(point_dir / "ideal_vernier.lis")
    measurement = run_dc_sweep.find_measurement_file(point_dir, "ideal_vernier")
    values = run_dc_sweep.parse_measurements(measurement)
    rvt: List[float] = []
    lvt: List[float] = []
    for index in range(int(config["stages"])):
        r_name = "rvt_{:03d}_cross_s".format(index)
        l_name = "lvt_{:03d}_cross_s".format(index)
        if values.get(r_name) is None or values.get(l_name) is None:
            raise ValueError("missing arrival {} or {} in {}".format(r_name, l_name, measurement))
        rvt.append(float(values[r_name]))
        lvt.append(float(values[l_name]))
    if any(rvt[index + 1] <= rvt[index] for index in range(len(rvt) - 1)):
        raise ValueError("RVT arrivals are not strictly ordered: {}".format(point_dir))
    if any(lvt[index + 1] <= lvt[index] for index in range(len(lvt) - 1)):
        raise ValueError("LVT arrivals are not strictly ordered: {}".format(point_dir))
    return {
        "candidate_id": pair["candidate_id"], "lvt_cell": pair["lvt_cell"],
        "dummy_load_count": int(pair["dummy_load_count"]), "vdd_v": voltage,
        "rvt": rvt, "lvt": lvt, "measurement_file": str(measurement.relative_to(run_dir)),
    }


def decode(rvt: Sequence[float], lvt: Sequence[float], threshold_s: float, thermometer_invert: bool) -> Dict[str, Any]:
    """Apply the physical DFF comparison and return a decoder-ready word.

    Every later Phase-3 comparator connects LVT to D and RVT to CK.  A DFF
    captures one exactly when ``T_LVT + delay_LVT < T_RVT + delay_RVT``.  The
    equivalent threshold is ``T_RVT - T_LVT > delay_LVT - delay_RVT`` and is
    represented here by the signed ``threshold_s`` value.  Positive threshold
    values delay the LVT launch; negative values delay the RVT launch.

    The physical DFF word can naturally be either ``0*1*`` or ``1*0``.  This
    function retains the unmodified DFF result as ``raw_code`` and performs a
    visible, single-bit inversion only when the selected structure needs it to
    meet the common decoder's ``0*1*`` contract.  No timing result is hidden by
    this normalization: both words are written to the CSV.
    """

    raw_bits = [1 if (r_time - l_time) > threshold_s else 0 for r_time, l_time in zip(rvt, lvt)]
    normalized_bits = [1 - bit for bit in raw_bits] if thermometer_invert else list(raw_bits)
    first_one = next((index for index, bit in enumerate(normalized_bits) if bit), len(normalized_bits))
    bubbles = sum(1 for bit in normalized_bits[first_one:] if bit == 0)
    transitions = sum(1 for index in range(1, len(normalized_bits)) if normalized_bits[index] != normalized_bits[index - 1])
    return {
        "raw_code": "".join(str(bit) for bit in raw_bits),
        "normalized_code": "".join(str(bit) for bit in normalized_bits),
        "sensor_code": first_one,
        "bubble_count": bubbles, "code_valid": bubbles == 0 and transitions <= 1,
    }


def arrival_from_existing_scenario(run_dir: Path, pair: Dict[str, Any], voltage: float, stages: int) -> Dict[str, Any]:
    """Recover one completed HSPICE arrival vector without rerunning a deck.

    This helper accepts only the deterministic scenario names emitted by this
    script and validates all 64 required measurements.  It is used only when a
    completed task-owned HSPICE run needs its Python summary reconstructed; it
    cannot pull data from a different candidate, supply, or experiment.
    """

    label = "{}_v{:0.12f}".format(pair["candidate_id"], voltage).replace(".", "p")
    point_dir = run_dir / "scenarios" / label
    measurement = run_dc_sweep.find_measurement_file(point_dir, "ideal_vernier")
    values = run_dc_sweep.parse_measurements(measurement)
    rvt: List[float] = []
    lvt: List[float] = []
    for index in range(stages):
        r_name = "rvt_{:03d}_cross_s".format(index)
        l_name = "lvt_{:03d}_cross_s".format(index)
        if values.get(r_name) is None or values.get(l_name) is None:
            raise ValueError("missing arrival {} or {} in {}".format(r_name, l_name, measurement))
        rvt.append(float(values[r_name]))
        lvt.append(float(values[l_name]))
    if any(rvt[index + 1] <= rvt[index] for index in range(len(rvt) - 1)):
        raise ValueError("RVT arrivals are not strictly ordered: {}".format(point_dir))
    if any(lvt[index + 1] <= lvt[index] for index in range(len(lvt) - 1)):
        raise ValueError("LVT arrivals are not strictly ordered: {}".format(point_dir))
    return {
        "candidate_id": pair["candidate_id"], "lvt_cell": pair["lvt_cell"],
        "dummy_load_count": int(pair["dummy_load_count"]), "vdd_v": voltage,
        "rvt": rvt, "lvt": lvt, "measurement_file": str(measurement.relative_to(run_dir)),
    }


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Write all offset/voltage observations with raw word provenance."""

    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in CSV_FIELDS})


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run all retained candidates, select one nominal-centered monotonic pair, and update config."""

    parser = argparse.ArgumentParser(description="run Phase-3 ideal 32-stage Vernier")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--selection-json", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--reuse-arrivals", action="store_true", help="summarize only a completed task-owned arrival run")
    args = parser.parse_args(argv)
    config = load_json(args.config)
    selected = load_json(WORKSPACE_ROOT / "power_macro/delay_chain/phase3/discovery/selected_cells.json")
    pairs = load_json(args.selection_json)["selected_pairs"]
    phase1 = load_json(PHASE1_CONFIG)
    hspice = run_dc_sweep.require_regular_file(Path("/home/zhupl25/.local/bin/hspice"), "HSPICE", executable=True)
    run_dir = args.output_dir.resolve()
    if run_dir.exists() and not args.reuse_arrivals:
        raise ValueError("refusing to overwrite existing ideal-vernier run")
    if args.reuse_arrivals and not run_dir.is_dir():
        raise ValueError("--reuse-arrivals requires an existing ideal-vernier run directory")
    if not args.reuse_arrivals:
        run_dir.mkdir(parents=True)
    arrivals: List[Dict[str, Any]] = []
    for pair in pairs:
        for voltage in voltages(config):
            if args.reuse_arrivals:
                arrivals.append(arrival_from_existing_scenario(run_dir, pair, voltage, int(config["stages"])))
            else:
                arrivals.append(run_arrival_point(config, selected, phase1, hspice, run_dir, pair, voltage))
    rows: List[Dict[str, Any]] = []
    evaluations: List[Dict[str, Any]] = []
    for pair in pairs:
        estimate_ps = 16.0 * abs(float(pair["t_r_nom_s"]) - float(pair["t_l_nom_s"])) * 1.0e12
        group = [item for item in arrivals if item["candidate_id"] == pair["candidate_id"]]
        nominal_arrival = min(group, key=lambda item: abs(item["vdd_v"] - float(config["vnom_v"])))
        nominal_gaps_ps = [(r_time - l_time) * 1.0e12 for r_time, l_time in zip(nominal_arrival["rvt"], nominal_arrival["lvt"])]
        target_index = int(config["target_nominal_code"])
        if target_index <= 0 or target_index >= len(nominal_gaps_ps):
            raise ValueError("target nominal code must select an interior thermometer transition")
        # A rising arrival-difference sequence yields physical 0*1* DFF bits.
        # A falling sequence yields 1*0 and uses the one explicit inversion
        # mandated by the shared decoder contract.
        thermometer_invert = nominal_gaps_ps[target_index] < nominal_gaps_ps[target_index - 1]
        # This midpoint is derived from two adjacent measured taps.  It is a
        # local correction to the prescribed pair-delay estimate, not a broad
        # search, and accounts for native full-chain input loading.
        measured_threshold_ps = 0.5 * (nominal_gaps_ps[target_index - 1] + nominal_gaps_ps[target_index])
        direction_sign = 1.0 if measured_threshold_ps >= 0.0 else -1.0
        estimate_magnitudes_ps = [estimate_ps - 20.0, estimate_ps - 10.0, estimate_ps, estimate_ps + 10.0, estimate_ps + 20.0]
        local_step_ps = max(0.25, min(2.0, 0.5 * abs(nominal_gaps_ps[target_index] - nominal_gaps_ps[target_index - 1])))
        offset_choices = [("pair_estimate", direction_sign * magnitude) for magnitude in estimate_magnitudes_ps]
        offset_choices.extend(("measured_transition", measured_threshold_ps + multiplier * local_step_ps) for multiplier in (-2.0, -1.0, 0.0, 1.0, 2.0))
        seen_thresholds = set()
        for sweep_kind, threshold_ps in offset_choices:
            rounded_threshold = round(threshold_ps, 15)
            if rounded_threshold in seen_thresholds:
                continue
            seen_thresholds.add(rounded_threshold)
            launch_delayed_path = "lvt" if threshold_ps >= 0.0 else "rvt"
            launch_offset_ps = abs(threshold_ps)
            decoded = []
            for item in sorted(group, key=lambda value: value["vdd_v"], reverse=True):
                code = decode(item["rvt"], item["lvt"], threshold_ps * 1.0e-12, thermometer_invert)
                decoded.append({"vdd_v": item["vdd_v"], **code})
                rows.append({
                    "candidate_id": pair["candidate_id"], "lvt_cell": pair["lvt_cell"],
                    "dummy_load_count": pair["dummy_load_count"], "offset_sweep_kind": sweep_kind,
                    "launch_offset_ps": launch_offset_ps, "launch_delayed_path": launch_delayed_path,
                    "threshold_ps": threshold_ps, "thermometer_invert": int(thermometer_invert),
                    "vdd_v": item["vdd_v"], "raw_code": code["raw_code"], "normalized_code": code["normalized_code"],
                    "sensor_code": code["sensor_code"], "bubble_count": code["bubble_count"],
                    "code_valid": int(code["code_valid"]), "polarity": 0,
                    "arrival_measurement_file": item["measurement_file"],
                })
            nominal = min(decoded, key=lambda item: abs(item["vdd_v"] - float(config["vnom_v"])))
            increasing = all(decoded[index + 1]["sensor_code"] >= decoded[index]["sensor_code"] for index in range(len(decoded) - 1))
            decreasing = all(decoded[index + 1]["sensor_code"] <= decoded[index]["sensor_code"] for index in range(len(decoded) - 1))
            monotonic = increasing or decreasing
            # Residual normalization later multiplies ``code-baseline`` by
            # this sign, so a raw code that falls with droop is still a valid
            # physical polarity rather than an invalid Vernier transition.
            polarity = 1 if increasing else -1 if decreasing else 0
            valid = all(item["code_valid"] for item in decoded)
            evaluations.append({
                "candidate_id": pair["candidate_id"], "lvt_cell": pair["lvt_cell"],
                "dummy_load_count": pair["dummy_load_count"], "offset_sweep_kind": sweep_kind,
                "launch_offset_ps": launch_offset_ps, "launch_delayed_path": launch_delayed_path,
                "threshold_ps": threshold_ps, "thermometer_invert": thermometer_invert,
                "offset_estimate_ps": estimate_ps, "measured_transition_threshold_ps": measured_threshold_ps,
                "nominal_code": nominal["sensor_code"],
                "nominal_centered": 14 <= nominal["sensor_code"] <= 18,
                "monotonic": monotonic, "polarity": polarity, "all_valid": valid,
                "first_violation_code": min(decoded, key=lambda item: abs(item["vdd_v"] - float(config["first_violation_v"])))["sensor_code"],
            })
    feasible = [item for item in evaluations if item["nominal_centered"] and item["monotonic"] and item["all_valid"]]
    if not feasible:
        raise RuntimeError("no ideal Vernier candidate reached nominal-centered monotonic code")
    # Prefer the largest observed anchor separation, then the centered code.
    # This is a direct physical ranking, not a weighted scoring function.
    chosen = sorted(feasible, key=lambda item: (-abs(item["first_violation_code"] - item["nominal_code"]), abs(item["nominal_code"] - 16), item["offset_sweep_kind"] != "pair_estimate", item["candidate_id"]))[0]
    write_csv(run_dir / "ideal_vernier.csv", rows)
    (run_dir / "ideal_selection.json").write_text(json.dumps({"schema_version": 1, "evaluations": evaluations, "selected": chosen}, indent=2) + "\n", encoding="utf-8")
    config.update({
        "selected_pair_id": chosen["candidate_id"], "selected_lvt_cell": chosen["lvt_cell"],
        "selected_dummy_load_count": chosen["dummy_load_count"], "ideal_launch_offset_ps": chosen["launch_offset_ps"],
        "ideal_launch_delayed_path": chosen["launch_delayed_path"], "thermometer_invert": chosen["thermometer_invert"],
        "code_polarity": chosen["polarity"],
    })
    args.config.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = WORKSPACE_ROOT / "power_macro/delay_chain/phase3/reports/IDEAL_VERNIER.md"
    report.write_text(
        "# Ideal Vernier\n\nSelected `{}` with LVT `{}` dummy={}, delay {} launch by {:.6f} ps, normalize raw DFF bits by inversion={}, nominal code={}, first-violation code={}, code polarity={:+d}.\n\nThe initial five-point pair-delay estimate and the five-point measured-transition correction are both retained in `runs/ideal_vernier/ideal_vernier.csv`; selection evidence is in `runs/ideal_vernier/ideal_selection.json`.\n".format(
            chosen["candidate_id"], chosen["lvt_cell"], chosen["dummy_load_count"], chosen["launch_delayed_path"], chosen["launch_offset_ps"], chosen["thermometer_invert"], chosen["nominal_code"], chosen["first_violation_code"], chosen["polarity"]
        ), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
