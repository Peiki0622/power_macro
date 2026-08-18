#!/usr/bin/env python3
"""Measure a bounded fine-driver strength fix at the retained failing endpoint.

This is intentionally not a new fine-load or K sweep.  It holds the retained
NOR2_X4A, M=15, F=8, and 0.80 V endpoint fixed, then tests four increasing
real LVT buffer cells.  A passing endpoint only proves a waveform improvement
at that point; it cannot reverse the preceding full-stage NO-GO result.
"""

import csv
import importlib.util
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = FTC_ROOT / "scripts" / "run_standard_cell_load_fine_stage.py"
SPEC = importlib.util.spec_from_file_location("standard_cell_load_fine_stage_core", CORE_PATH)
assert SPEC is not None and SPEC.loader is not None
CORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CORE)


DRIVER_SEQUENCE = (("0P8", "BUF_X0P8M_A9TL40"), ("1", "BUF_X1M_A9TL40"), ("1P4", "BUF_X1P4M_A9TL40"), ("2", "BUF_X2M_A9TL40"))
REMAINING_DRIVER_SEQUENCE = DRIVER_SEQUENCE[1:]
BASELINE_DRIVER = ("0P7", "BUF_X0P7M_A9TL40")
PROBE_VDD = 0.80
PROBE_MEDIUM_CODE = 15
PROBE_K = 8
PROBE_FINE_CODE = 8
ROW_FIELDS = ("driver_cell", "driver_size_tier", "driver_total_width_m", "output_logic_high_ratio", "output_logic_low_ratio") + CORE.ROW_FIELDS


def read_json(path: Path) -> Dict[str, Any]:
    """Read an object contract and fail before any HSPICE work if it is malformed."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write deterministic task-owned analysis without touching prior evidence."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Publish all measured quantities, including invalid endpoint values."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=ROW_FIELDS, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
                writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in ROW_FIELDS})


def read_retained_probe_rows(path: Path) -> List[Dict[str, Any]]:
    """Read only the already measured X0P8M row for the continuation.

    The continuation must not rerun X0P8M after the runner source changes.  Its
    row is consumed from the prior analysis CSV and combined with the three
    newly requested driver measurements.
    """

    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as stream:
        return [row for row in csv.DictReader(stream) if row.get("driver_cell") == "BUF_X0P8M_A9TL40"]


def buffer_width(cdl: str, cell: str) -> float:
    """Validate one LVT BUF view and return its physical CDL width sum.

    Buffer names alone are insufficient evidence.  The exact Verilog/CDL port
    contracts are checked so a different cell family or a partial name cannot
    enter a deck merely because its nominal size appears larger.
    """

    block = re.search(r"(?ims)^\.SUBCKT\s+{}\s+Y\s+VDD\s+VNW\s+VPW\s+VSS\s+A\s*$\n(.*?)^\.ends\b".format(re.escape(cell)), cdl)
    if not block:
        raise ValueError("missing exact BUF CDL block: {}".format(cell))
    widths = [float(value) for value in re.findall(r"\bw=([0-9.eE+-]+)", block.group(0))]
    if not widths:
        raise ValueError("BUF CDL has no transistor widths: {}".format(cell))
    return sum(widths)


def discover_drivers(cells: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Freeze the four approved M buffers in strictly increasing CDL width order."""

    verilog = Path(cells["source_files"]["lvt_verilog"]).read_text(encoding="latin-1", errors="replace")
    cdl = Path(cells["source_files"]["lvt_cdl"]).read_text(encoding="latin-1", errors="replace")
    result: List[Dict[str, Any]] = []
    previous = 0.0
    for tier, cell in DRIVER_SEQUENCE:
        if not re.search(r"(?m)^module\s+{}\s*\(Y,\s*VDD,\s*VSS,\s*A\);".format(re.escape(cell)), verilog):
            raise ValueError("missing exact BUF Verilog module: {}".format(cell))
        width = buffer_width(cdl, cell)
        if width <= previous:
            raise ValueError("driver widths are not strictly increasing at {}".format(cell))
        result.append({"driver_cell": cell, "driver_size_tier": tier, "driver_total_width_m": width})
        previous = width
    return result


def fixed_load() -> Dict[str, Any]:
    """Reuse only the retained rank-2 electrical contract, never a new load choice."""

    contract = read_json(FTC_ROOT / "analysis" / "standard_cell_load_size_sweep" / "fallback_1" / "selected_size_contract.json")
    required = {"candidate_id": "NOR2_X4A_A9TL40__signal_A", "cell": "NOR2_X4A_A9TL40", "signal_pin": "A", "control_pin": "B", "high_cap_control_value": 0, "low_cap_control_value": 1, "K_candidate": 8}
    if any(contract.get(key) != value for key, value in required.items()):
        raise ValueError("retained fallback contract no longer matches the approved endpoint")
    return contract


def baseline_row() -> Dict[str, Any]:
    """Read the existing X0P7M failure without rerunning its electrical deck."""

    path = FTC_ROOT / "analysis" / "standard_cell_load_size_sweep" / "fallback_1" / "winner_coupled_medium.csv"
    # Close the retained evidence stream before HSPICE setup so repeated unit
    # tests do not leave a file descriptor open in a long-running process.
    with path.open(encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["medium_code"] == "15" and row["fine_code"] == "8" and row["vdd_v"] == "0.8":
                return row
    raise ValueError("retained X0P7M failure row is missing")


def probe_parameters(driver: Mapping[str, Any], candidate: Mapping[str, Any]) -> Dict[str, Any]:
    """Bind every varying physical property into the HSPICE reuse identity."""

    parameters = CORE.scenario_parameters("driver_strength_probe", PROBE_MEDIUM_CODE, PROBE_VDD, candidate, PROBE_K, PROBE_FINE_CODE, 1, 0, CORE.DEFAULT_LOGIC_HIGH_MIN_RATIO, str(driver["driver_cell"]))
    parameters.update({"study_name": "standard_cell_load_driver_strength_probe", "driver_size_tier": driver["driver_size_tier"], "driver_total_width_m": driver["driver_total_width_m"]})
    return parameters


def render_probe_deck(config: Mapping[str, Any], cells: Mapping[str, Any], candidate: Mapping[str, Any], driver: Mapping[str, Any]) -> str:
    """Render the approved endpoint while changing only the fine-driver cell."""

    return CORE.render_deck(config, cells, PROBE_VDD, PROBE_MEDIUM_CODE, candidate, PROBE_K, PROBE_FINE_CODE, 0, str(driver["driver_cell"]))


def measure_driver(driver: Mapping[str, Any], candidate: Mapping[str, Any], config: Mapping[str, Any], cells: Mapping[str, Any], hspice: Path, run_dir: Path, signature: Mapping[str, str], stats: Dict[str, int]) -> Dict[str, Any]:
    """Run one complete HSPICE endpoint, then apply the unchanged 0.90/0.10 Gate."""

    record = CORE.execute(hspice, run_dir, render_probe_deck(config, cells, candidate, driver), probe_parameters(driver, candidate), signature, stats)
    result = CORE.classify(record, PROBE_VDD, CORE.DEFAULT_LOGIC_HIGH_MIN_RATIO)
    result.update({
        "stage": "driver_strength_probe", "candidate_id": candidate["candidate_id"],
        "medium_code": PROBE_MEDIUM_CODE, "fine_code": PROBE_FINE_CODE,
        "K": PROBE_K, "vdd_v": PROBE_VDD, "control_value": 0,
        "scenario": str(Path(record["scenario"]).relative_to(run_dir)),
        "driver_cell": driver["driver_cell"], "driver_size_tier": driver["driver_size_tier"],
        "driver_total_width_m": driver["driver_total_width_m"],
        "output_logic_high_ratio": result["output_logic_high"] / PROBE_VDD if result["output_logic_high"] is not None else None,
        "output_logic_low_ratio": result["output_logic_low"] / PROBE_VDD if result["output_logic_low"] is not None else None,
    })
    return result


def render_report(path: Path, baseline: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], drivers: Sequence[Mapping[str, Any]]) -> None:
    """State the endpoint result without conflating it with full-bank acceptance."""

    winner = next((row for row in rows if str(row.get("valid")).lower() == "true"), None)
    lines = ["# SMIC40LL Fine-Driver Strength Probe", "", "## Fixed Endpoint", "", "- `NOR2_X4A_A9TL40`, signal `A`, control `B`, high-load control `0`.", "- `M=15`, `F=8`, `K=8`, `VDD=0.80 V`; original high/low limits remain `0.72 V` / `0.08 V`.", "- Existing X0P7M baseline is read-only and was not rerun.", "", "## Measurements", "", "| Driver | CDL total width (um) | Output high (V) | High/VDD | 10%-90% rise (ps) | Result |", "|---|---:|---:|---:|---:|---|"]
    lines.append("| `BUF_X0P7M_A9TL40` (baseline) | 0.780 | {} | {} | {} | retained failure |".format(baseline["output_logic_high"], float(baseline["output_logic_high"]) / PROBE_VDD, baseline["output_rise_time_ps"]))
    for row in rows:
        lines.append("| `{}` | {:.3f} | {} | {} | {} | {} |".format(row["driver_cell"], float(row["driver_total_width_m"]) * 1.0e6, row["output_logic_high"], row["output_logic_high_ratio"], row["output_rise_time_ps"], "PASS" if row["valid"] else "FAIL"))
    lines.extend(["", "## Decision", "", "- Endpoint result: `{}`.".format("IMPROVED_AT_FIXED_ENDPOINT" if winner else "UNRESOLVED_WITHIN_BOUNDED_DRIVER_SET"), "- Comparison rows: `{}` of `{}` driver entries (X0P8M retained, X1M/X1P4M/X2M newly measured).".format(len(rows), len(drivers)), "- This probe does not rerank loads, derive K, or establish Fine Stage GO; any passing driver requires a separately authorized full re-evaluation.", "- Historical medium scenarios rerun: `0`; historical runner invocations: `0`; bypass/configuration/sensor/XOR/DFF/calibration/PVT/RTL/power/area/layout scenarios: `0`."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    """Run the four-entry maximum bounded probe and publish its retained evidence."""

    analysis = FTC_ROOT / "analysis" / "standard_cell_load_driver_strength_probe"
    run_root = FTC_ROOT / "runs" / "standard_cell_load_driver_strength_probe"
    interface, cells, _ = CORE.freeze_inputs()
    candidate, drivers = fixed_load(), discover_drivers(cells)
    baseline = baseline_row()
    retained_rows = read_retained_probe_rows(analysis / "driver_probe.csv")
    requirements = {"schema_version": 1, "candidate_id": candidate["candidate_id"], "driver_sequence": drivers, "max_new_hspice_scenarios": len(drivers), "endpoint": {"vdd_v": PROBE_VDD, "medium_code": PROBE_MEDIUM_CODE, "K": PROBE_K, "fine_code": PROBE_FINE_CODE}, "logic_high_min_ratio": CORE.DEFAULT_LOGIC_HIGH_MIN_RATIO, "logic_low_max_ratio": CORE.LOGIC_LOW_MAX_RATIO, "historical_medium_scenarios_rerun": 0, "historical_runner_invocations": 0, "full_fine_stage_acceptance": "not_run"}
    write_json(analysis / "requirements.json", requirements)
    write_json(analysis / "driver_candidates.json", {"schema_version": 1, "drivers": drivers})
    config = CORE.load_json(FTC_ROOT / "ftc_config.json")
    hspice, version = CORE.validate_hspice(config)
    signature = {"runner_sha256": CORE.sha256_file(Path(__file__)), "requirements_sha256": CORE.sha256_file(analysis / "requirements.json"), "candidate_contract_sha256": CORE.sha256_file(FTC_ROOT / "analysis" / "standard_cell_load_size_sweep" / "fallback_1" / "selected_size_contract.json")}
    run_dir = CORE.select_run_dir(run_root, signature, hspice, version)
    stats = {"new": 0, "reused": 0}
    rows = list(retained_rows)
    for driver in drivers[1:]:
        row = measure_driver(driver, candidate, config, cells, hspice, run_dir, signature, stats)
        rows.append(row)
    if stats["new"] > len(REMAINING_DRIVER_SEQUENCE):
        raise RuntimeError("driver continuation exceeded its three-scenario budget")
    write_csv(analysis / "driver_probe.csv", rows)
    retained = CORE.retained_stats(run_root)
    winner = next((row for row in rows if str(row.get("valid")).lower() == "true"), None)
    summary = {"schema_version": 1, "decision": "IMPROVED_AT_FIXED_ENDPOINT" if winner else "UNRESOLVED_WITHIN_BOUNDED_DRIVER_SET", "selected_driver": winner["driver_cell"] if winner else None, "tested_driver_count": len(rows), "driver_sequence_count": len(drivers), "new_hspice_scenarios": stats["new"], "reused_new_task_scenarios": stats["reused"] + len(retained_rows), "retained_pass_scenarios": retained["new"], "historical_medium_scenarios_rerun": 0, "historical_runner_invocations": 0, "full_fine_stage_acceptance": "NOT_RUN", "baseline_output_logic_high_v": float(baseline["output_logic_high"]), "rows": rows}
    write_json(analysis / "summary.json", summary)
    render_report(FTC_ROOT / "reports" / "FTC_STANDARD_CELL_LOAD_DRIVER_STRENGTH.md", baseline, rows, drivers)
    print("FTC_STANDARD_CELL_LOAD_DRIVER_STRENGTH decision={}".format(summary["decision"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
