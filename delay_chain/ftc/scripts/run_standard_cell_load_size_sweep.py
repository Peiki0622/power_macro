#!/usr/bin/env python3
"""Scan bounded SMIC40LL LVT NAND/NOR input-load sizes.

This runner is an isolated characterization task.  It reuses only the reviewed
deck, HSPICE listing, measurement, and waveform helpers from the current fine
stage runner; it never invokes an older FTC runner and never changes the
existing X0P5 or maximum-LVT evidence.  Every candidate receives real three-
voltage single-load and K=8 full-code measurements before a deterministic
winner is sent through the original coupled-coverage gates.
"""

import argparse
import csv
import importlib.util
import json
import math
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = FTC_ROOT / "scripts" / "run_standard_cell_load_fine_stage.py"
SPEC = importlib.util.spec_from_file_location("standard_cell_load_fine_stage_core", CORE_PATH)
assert SPEC is not None and SPEC.loader is not None
CORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CORE)


SIZE_TIERS = ("0P7", "1", "1P4", "2", "3", "4", "6")
LOGIC_FAMILIES = (("NAND2", "Y = ~(A & B)"), ("NOR2", "Y = ~(A | B)"))
ANCHOR_VDD = CORE.ANCHOR_VDD
K_TEST = 8
MAX_FINE_BANK = CORE.MAX_FINE_BANK
DEFAULT_HIGH_RATIO = CORE.DEFAULT_LOGIC_HIGH_MIN_RATIO
LOW_RATIO = CORE.LOGIC_LOW_MAX_RATIO
SCAN_STAGE = "size_scan_8unit"

METRIC_FIELDS = (
    "candidate_id", "cell", "size_tier", "logic_family", "signal_pin",
    "control_pin", "single_load_valid", "control_mapping_stable",
    "unit_delta_ps_by_vdd", "fine_range_8_ps_by_vdd", "K_pred_by_vdd",
    "K_candidate", "delta_fine_max_ps_by_vdd", "settling_max_ps_by_vdd",
    "monotonic", "decision", "reasons",
)


def load_json(path: Path) -> Dict[str, Any]:
    """Read one object-shaped contract and reject malformed generated evidence."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write deterministic reviewable JSON beneath this task's analysis root."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    """Write a rectangular CSV while preserving failed values as empty cells."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def vkey(value: float) -> str:
    """Use the established two-decimal voltage keys in all contracts."""

    return "{:.2f}".format(float(value))


def freeze_inputs() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Path]]:
    """Freeze the completed medium handoff without rerunning or importing it."""

    interface, cells, paths = CORE.freeze_inputs()
    return interface, cells, paths


def discover_size_candidates(cells: Mapping[str, Any]) -> Dict[str, Any]:
    """Select one widest real A/B/M implementation per size and logic family.

    A/B/M are physical transistor implementations, not additional nominal size
    tiers.  Choosing by CDL total width keeps this scan finite and matches the
    already-reviewed maximum-LVT selection rule; both input directions remain
    electrical candidates because their stack positions differ.
    """

    verilog_path = Path(cells["source_files"]["lvt_verilog"])
    cdl_path = Path(cells["source_files"]["lvt_cdl"])
    verilog = verilog_path.read_text(encoding="latin-1", errors="replace")
    cdl = cdl_path.read_text(encoding="latin-1", errors="replace")
    entries: List[Dict[str, Any]] = []
    selections: List[Dict[str, Any]] = []
    for family, truth in LOGIC_FAMILIES:
        for tier in SIZE_TIERS:
            pattern = r"{}_X{}[ABM]_A9TL40".format(family, tier)
            names = sorted(set(re.findall(r"(?m)^module\s+({})\s*\(Y,\s*VDD,\s*VSS,\s*A,\s*B\);".format(pattern), verilog)))
            ranked: List[Tuple[float, int, str, List[float]]] = []
            for cell in names:
                vblock = CORE._cell_block(verilog, cell, False)
                cblock = CORE._cell_block(cdl, cell, True)
                if not vblock or not cblock or ("nand" if family == "NAND2" else "nor") not in vblock.lower():
                    continue
                widths = [float(value) for value in re.findall(r"\bw=([0-9.eE+-]+)", cblock)]
                if widths:
                    # The second key is zero for the conventional M tie-break.
                    ranked.append((sum(widths), 0 if cell.endswith("M_A9TL40") else 1, cell, widths))
            if not ranked:
                continue
            ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
            total, _, cell, widths = ranked[0]
            selections.append({"logic_family": family, "size_tier": tier, "selected_cell": cell, "total_width_m": total, "available_cells": [item[2] for item in ranked]})
            for signal, control in (("A", "B"), ("B", "A")):
                entries.append({
                    "candidate_id": "{}__signal_{}".format(cell, signal), "cell": cell,
                    "size_tier": tier, "logic_family": family, "signal_pin": signal,
                    "control_pin": control, "output_pin": "Y",
                    "cdl_ports": ["Y", "VDD", "VNW", "VPW", "VSS", "A", "B"],
                    "verilog_ports": ["Y", "VDD", "VSS", "A", "B"],
                    "truth_function": truth, "vt_class": "LVT",
                    "estimated_transistor_or_structure_note": "CDL transistor widths (meters): {}".format(widths),
                    "source_file_sha256": {"verilog": CORE.sha256_file(verilog_path), "cdl": CORE.sha256_file(cdl_path)},
                })
    if len(entries) != len(SIZE_TIERS) * len(LOGIC_FAMILIES) * 2:
        raise ValueError("size discovery did not produce exactly 28 candidates")
    return {"schema_version": 1, "size_tiers": list(SIZE_TIERS), "candidate_count": len(entries), "selection_rule": "maximum CDL total width; tie M then cell name", "selections": selections, "candidates": entries}


def requirements(interface: Mapping[str, Any], paths: Mapping[str, Path]) -> Dict[str, Any]:
    """Publish the independent scan contract and preserve the original scope limits."""

    base = CORE.build_requirements(interface, paths, DEFAULT_HIGH_RATIO)
    base.update({
        "schema_version": 2, "study_name": "standard_cell_load_size_sweep",
        "size_tiers": list(SIZE_TIERS), "candidate_count": 28,
        "candidate_selection": "widest_CDL_total_width_tie_M_then_cell_name",
        "K_test": K_TEST, "single_load_scenario_budget": 171,
        "size_scan_8unit_scenario_budget": 756,
        "settling_metric": "max_rise_fall_10_to_90_ps_over_F_and_V",
        "ranking": ["K_candidate", "max_normalized_fine_step", "max_settling_ps", "candidate_id"],
        "historical_endpoint_policy": "read_only_X0P5_and_X8_reference",
    })
    return base


def select_run_dir(root: Path, signature: Mapping[str, str], hspice: Path, version: str, revision_tag: str) -> Path:
    """Reuse only a complete matching revision; never overwrite raw evidence."""

    root.mkdir(parents=True, exist_ok=True)
    revisions = sorted((item for item in root.glob("r*") if re.fullmatch(r"r\d+", item.name)), key=lambda item: int(item.name[1:]), reverse=True)
    for revision in revisions:
        manifest = revision / "run_manifest.json"
        if manifest.is_file() and load_json(manifest).get("signature") == dict(signature):
            scenarios = list((revision / "scenarios").glob("*/scenario_manifest.json"))
            if scenarios and all(load_json(item).get("completion_status") == "PASS" for item in scenarios):
                return revision
    number = max([int(item.name[1:]) for item in revisions], default=0) + 1
    revision = root / "r{}".format(number)
    revision.mkdir(parents=True)
    write_json(revision / "run_manifest.json", {"schema_version": 1, "study": "standard_cell_load_size_sweep", "revision": revision_tag, "signature": dict(signature), "system_hspice": str(hspice), "hspice_version": version})
    return revision


def signature(runner_path: Path, *contracts: Path) -> Dict[str, str]:
    """Bind raw scenarios to this runner and every contract used to render them."""

    result = {"runner_sha256": CORE.sha256_file(runner_path)}
    for index, contract in enumerate(contracts):
        result["contract_{}_sha256".format(index)] = CORE.sha256_file(contract)
    return result


def measure(phase: str, hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any], candidate: Optional[Mapping[str, Any]], medium_code: int, vdd: float, K: int, fine_code: int, low_control: Any, high_control: Any, sig: Mapping[str, str], stats: Dict[str, int], control_value: Any = None) -> Dict[str, Any]:
    """Render and execute one real scenario using the reviewed core topology."""

    physical_high = int(high_control) if isinstance(high_control, int) else 1
    deck = CORE.render_deck(config, cells, vdd, medium_code, candidate, K, fine_code, physical_high)
    parameters = CORE.scenario_parameters(phase, medium_code, vdd, candidate, K, fine_code, low_control, high_control, DEFAULT_HIGH_RATIO)
    parameters.update({"study_name": "standard_cell_load_size_sweep", "candidate_id": candidate.get("candidate_id") if candidate else "driver_only", "size_tier": candidate.get("size_tier") if candidate else "none"})
    record = CORE.execute(hspice, run_dir, deck, parameters, sig, stats)
    result = CORE.classify(record, vdd, DEFAULT_HIGH_RATIO)
    return {"stage": phase, "candidate_id": candidate.get("candidate_id") if candidate else "driver_only", "medium_code": medium_code, "fine_code": fine_code, "K": K, "vdd_v": vdd, "control_value": control_value, **result, "scenario": str(Path(record["scenario"]).relative_to(run_dir))}


def retained_count(root: Path) -> int:
    """Count physical PASS manifests across all retained scan revisions."""

    manifests = list(root.glob("r*/scenarios/*/scenario_manifest.json"))
    if any(load_json(item).get("completion_status") != "PASS" for item in manifests):
        raise RuntimeError("scan raw root contains an incomplete scenario")
    return len(manifests)


def single_decisions(rows: Sequence[Mapping[str, Any]], interface: Mapping[str, Any]) -> Dict[str, Any]:
    """Classify all directions without prematurely discarding useful size data."""

    decisions = []
    for candidate_id in sorted({row["candidate_id"] for row in rows if row["candidate_id"] != "driver_only"}):
        local = [row for row in rows if row["candidate_id"] == candidate_id]
        high_values, deltas, reasons = [], {}, []
        for vdd in ANCHOR_VDD:
            points = {int(row["control_value"]): row for row in local if float(row["vdd_v"]) == vdd}
            if set(points) != {0, 1} or any(not row["valid"] for row in points.values()):
                reasons.append("{} V missing valid control pair".format(vkey(vdd)))
                continue
            first, second = float(points[0]["D_rise_ps"]), float(points[1]["D_rise_ps"])
            high = 1 if second > first else 0
            high_values.append(high)
            deltas[vkey(vdd)] = abs(second - first)
            if deltas[vkey(vdd)] <= 0:
                reasons.append("{} V non-positive unit delta".format(vkey(vdd)))
            if deltas[vkey(vdd)] >= float(interface["medium_step_min_ps_by_vdd"][vkey(vdd)]):
                reasons.append("{} V unit delta is not below medium minimum".format(vkey(vdd)))
        if len(set(high_values)) != 1:
            reasons.append("control mapping is not voltage stable")
        decisions.append({
            "candidate_id": candidate_id, "decision": "GO" if not reasons else "REJECTED",
            "mapping_valid": bool(high_values) and len(set(high_values)) == 1,
            "high_cap_control_value": high_values[0] if high_values and len(set(high_values)) == 1 else None,
            "low_cap_control_value": 1 - high_values[0] if high_values and len(set(high_values)) == 1 else None,
            "unit_delta_ps_by_vdd": deltas, "reasons": reasons,
        })
    return {"schema_version": 1, "decisions": decisions}


def monotonic_rows(rows: Sequence[Mapping[str, Any]], codes: Sequence[int]) -> Tuple[bool, List[str]]:
    """Require valid measurements and strictly increasing rising propagation delay."""

    by_code = {int(row["fine_code"]): row for row in rows}
    values = []
    reasons = []
    for code in codes:
        row = by_code.get(code)
        if not row or not row.get("valid") or row.get("D_rise_ps") is None:
            reasons.append("fine code {} lacks a valid measurement".format(code))
        else:
            values.append(float(row["D_rise_ps"]))
    if len(values) == len(codes) and any(right <= left for left, right in zip(values, values[1:])):
        reasons.append("rising delay is not strictly monotonic")
    return not reasons, reasons


def metric_rows(fine_rows: Sequence[Mapping[str, Any]], decisions: Mapping[str, Any], candidates: Mapping[str, Mapping[str, Any]], interface: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Reduce all K=8 waveforms to the four requested size-scan metrics."""

    decision_by_id = {item["candidate_id"]: item for item in decisions["decisions"]}
    metrics = []
    for candidate_id, decision in sorted(decision_by_id.items()):
        local = [row for row in fine_rows if row["candidate_id"] == candidate_id]
        ranges, predicted, max_steps, settling, reasons = {}, {}, {}, {}, list(decision["reasons"])
        monotonic = True
        for vdd in ANCHOR_VDD:
            points = [row for row in local if float(row["vdd_v"]) == vdd]
            points.sort(key=lambda row: int(row["fine_code"]))
            ok, mono_reasons = monotonic_rows(points, tuple(range(K_TEST + 1)))
            monotonic = monotonic and ok
            reasons.extend(["{} V {}".format(vkey(vdd), reason) for reason in mono_reasons])
            if len(points) != K_TEST + 1 or any(not row["valid"] for row in points):
                reasons.append("{} V waveform-invalid K=8 point".format(vkey(vdd)))
                continue
            delay_values = [float(row["D_rise_ps"]) for row in points]
            ranges[vkey(vdd)] = delay_values[-1] - delay_values[0]
            if ranges[vkey(vdd)] <= 0:
                reasons.append("{} V non-positive 8-unit range".format(vkey(vdd)))
            else:
                predicted[vkey(vdd)] = int(math.ceil(8.0 * float(interface["medium_step_max_ps_by_vdd"][vkey(vdd)]) / ranges[vkey(vdd)]))
            max_steps[vkey(vdd)] = max(right - left for left, right in zip(delay_values, delay_values[1:]))
            settling[vkey(vdd)] = max(max(float(row["output_rise_time_ps"]), float(row["output_fall_time_ps"])) for row in points)
            if max_steps[vkey(vdd)] >= float(interface["medium_step_min_ps_by_vdd"][vkey(vdd)]):
                reasons.append("{} V K=8 fine step is not below medium minimum".format(vkey(vdd)))
        K_candidate = max(predicted.values()) if len(predicted) == len(ANCHOR_VDD) else None
        if K_candidate is None:
            reasons.append("incomplete K prediction")
        elif K_candidate > MAX_FINE_BANK:
            reasons.append("K_candidate exceeds 64")
        gate_reasons = list(dict.fromkeys(reasons))
        metrics.append({
            "candidate_id": candidate_id, "cell": candidate_id.rsplit("__signal_", 1)[0],
            "size_tier": candidates[candidate_id]["size_tier"],
            "logic_family": candidate_id.split("_X", 1)[0],
            "signal_pin": candidate_id.rsplit("_", 1)[-1][-1],
            "control_pin": "B" if candidate_id.endswith("signal_A") else "A",
            "single_load_valid": decision["mapping_valid"], "control_mapping_stable": decision["mapping_valid"],
            "unit_delta_ps_by_vdd": decision["unit_delta_ps_by_vdd"], "fine_range_8_ps_by_vdd": ranges,
            "K_pred_by_vdd": predicted, "K_candidate": K_candidate,
            "delta_fine_max_ps_by_vdd": max_steps, "settling_max_ps_by_vdd": settling,
            "monotonic": monotonic, "decision": "GO" if not gate_reasons else "REJECTED", "reasons": gate_reasons,
        })
    return metrics


def choose_winner(metrics: Sequence[Mapping[str, Any]], interface: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Apply the fixed minimum-K, resolution, settling, and ID ordering."""

    eligible = []
    for item in metrics:
        if item["decision"] != "GO":
            continue
        ratios = [float(item["delta_fine_max_ps_by_vdd"][vkey(v)]) / float(interface["medium_step_min_ps_by_vdd"][vkey(v)]) for v in ANCHOR_VDD]
        settle = max(float(item["settling_max_ps_by_vdd"][vkey(v)]) for v in ANCHOR_VDD)
        eligible.append((int(item["K_candidate"]), max(ratios), settle, item["candidate_id"], dict(item)))
    return min(eligible)[-1] if eligible else None


def coverage_rows(candidate: Mapping[str, Any], K: int, phase: str, hspice: Path, run_dir: Path, config: Mapping[str, Any], cells: Mapping[str, Any], low: int, high: int, sig: Mapping[str, str], stats: Dict[str, int]) -> List[Dict[str, Any]]:
    """Measure the plan's nine worst-position coverage endpoints for one K."""

    return [measure(phase, hspice, run_dir, config, cells, candidate, medium, vdd, K, fine, low, high, sig, stats) for vdd in ANCHOR_VDD for medium, fine in ((7, 0), (7, K), (8, 0))]


def coverage_fail(rows: Sequence[Mapping[str, Any]], K: int) -> List[str]:
    """Check D(7,K,V) >= D(8,0,V) and all endpoint waveform contracts."""

    failures = []
    for vdd in ANCHOR_VDD:
        local = {(int(row["medium_code"]), int(row["fine_code"])): row for row in rows if float(row["vdd_v"]) == vdd}
        left, right = local.get((7, K)), local.get((8, 0))
        if not left or not right or not left["valid"] or not right["valid"] or float(left["D_rise_ps"]) < float(right["D_rise_ps"]):
            failures.append("{} V M7->8 coverage failed".format(vkey(vdd)))
    return failures


def winner_acceptance(candidate: Mapping[str, Any], initial_K: int, analysis: Path, run_root: Path, hspice: Path, config: Mapping[str, Any], cells: Mapping[str, Any], sig: Mapping[str, str], stats: Dict[str, int], interface: Mapping[str, Any], screen_rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Run the bounded original full-bank gates for only the selected candidate."""

    low, high = int(candidate["low_cap_control_value"]), int(candidate["high_cap_control_value"])
    K = initial_K
    coverage = coverage_rows(candidate, K, "winner_full_bank_coverage", hspice, run_root, config, cells, low, high, sig, stats)
    gaps = coverage_fail(coverage, K)
    if gaps and all(row["valid"] for row in coverage):
        estimates = []
        for vdd in ANCHOR_VDD:
            local = {(int(row["medium_code"]), int(row["fine_code"])): row for row in coverage if float(row["vdd_v"]) == vdd}
            base = float(local[(7, 0)]["D_rise_ps"])
            span = float(local[(7, K)]["D_rise_ps"]) - base
            target = float(local[(8, 0)]["D_rise_ps"]) - base
            if span <= 0:
                estimates.append(MAX_FINE_BANK + 1)
            else:
                estimates.append(int(math.ceil(K * target / span)))
        rescaled = max(estimates)
        if K < rescaled <= MAX_FINE_BANK:
            K = rescaled
            coverage = coverage_rows(candidate, K, "winner_full_bank_coverage_rescaled", hspice, run_root, config, cells, low, high, sig, stats)
            gaps = coverage_fail(coverage, K)
    write_csv(analysis / "winner_full_bank_coverage.csv", coverage, CORE.ROW_FIELDS)
    result: Dict[str, Any] = {"initial_K": initial_K, "final_K": K, "K_rescaled": K if K != initial_K else None, "coverage_reasons": gaps}
    if gaps:
        result["decision"] = "NO-GO"
        return result
    final_rows = [measure("winner_full_bank_monotonicity", hspice, run_root, config, cells, candidate, 7, 0.95, K, code, low, high, sig, stats) for code in range(K + 1)]
    sample_codes = tuple(sorted(set((0, 1, round(K / 4), round(K / 2), round(3 * K / 4), K - 1, K))))
    for vdd in (1.10, 0.80):
        final_rows.extend(measure("winner_full_bank_monotonicity", hspice, run_root, config, cells, candidate, 7, vdd, K, code, low, high, sig, stats) for code in sample_codes)
    mono_ok, mono_reasons = monotonic_rows([row for row in final_rows if float(row["vdd_v"]) == 0.95], tuple(range(K + 1)))
    for vdd in (1.10, 0.80):
        ok, reasons = monotonic_rows([row for row in final_rows if float(row["vdd_v"]) == vdd], sample_codes)
        mono_ok = mono_ok and ok
        mono_reasons.extend(["{} V {}".format(vkey(vdd), reason) for reason in reasons])
    write_csv(analysis / "winner_full_bank_monotonicity.csv", final_rows, CORE.ROW_FIELDS)
    if not mono_ok:
        result.update({"decision": "NO-GO", "monotonic_reasons": mono_reasons})
        return result
    coupled = [measure("winner_coupled_medium", hspice, run_root, config, cells, candidate, medium, vdd, K, K, low, high, sig, stats) for vdd in ANCHOR_VDD for medium in (0, 7, 15)]
    coupled.extend(measure("winner_coupled_medium", hspice, run_root, config, cells, candidate, medium + 1, vdd, K, 0, low, high, sig, stats) for vdd in ANCHOR_VDD for medium in (0, 7, 15))
    coupled.extend(measure("winner_coupled_medium_step", hspice, run_root, config, cells, candidate, medium, vdd, K, 0, low, high, sig, stats) for vdd in ANCHOR_VDD for medium in (0, 7, 15))
    coupled_reasons, min_medium = [], {}
    for vdd in ANCHOR_VDD:
        local = {(int(row["medium_code"]), int(row["fine_code"])): row for row in coupled if float(row["vdd_v"]) == vdd}
        steps = []
        for medium in (0, 7, 15):
            left, right, base = local[(medium, K)], local[(medium + 1, 0)], local[(medium, 0)]
            if not left["valid"] or not right["valid"] or float(left["D_rise_ps"]) < float(right["D_rise_ps"]):
                coupled_reasons.append("{} V M{}->{} coverage failed".format(vkey(vdd), medium, medium + 1))
            steps.append(float(right["D_rise_ps"]) - float(base["D_rise_ps"]))
        min_medium[vkey(vdd)] = min(steps)
    write_csv(analysis / "winner_coupled_medium.csv", coupled, CORE.ROW_FIELDS)
    measured_steps = {}
    for vdd in ANCHOR_VDD:
        local = [row for row in final_rows if float(row["vdd_v"]) == vdd]
        local.sort(key=lambda row: int(row["fine_code"]))
        adjacent = [float(right["D_rise_ps"]) - float(left["D_rise_ps"]) for left, right in zip(local, local[1:]) if int(right["fine_code"]) == int(left["fine_code"]) + 1]
        measured_steps[vkey(vdd)] = max(adjacent) if adjacent else None
        if measured_steps[vkey(vdd)] is None or measured_steps[vkey(vdd)] >= min_medium[vkey(vdd)]:
            coupled_reasons.append("{} V fine resolution is not below coupled medium step".format(vkey(vdd)))
    result.update({"decision": "GO" if not coupled_reasons else "NO-GO", "coupled_reasons": coupled_reasons, "medium_step_coupled_min_ps_by_vdd": min_medium, "delta_fine_max_ps_by_vdd": measured_steps})
    if result["decision"] == "GO":
        historical = list(csv.DictReader((FTC_ROOT / "analysis/path_selection_medium_stage/medium_step_characterization.csv").open(encoding="utf-8")))
        result["future_bypass_interface"] = {"schema_version": 1, "selected_load_cell": candidate["cell"], "signal_pin": candidate["signal_pin"], "control_pin": candidate["control_pin"], "K_candidate_tt25": K, "bypass_not_implemented": True, "fine_driver_offset_ps_by_vdd": {}, "fine_bank_code0_offset_ps_by_vdd": {}}
        for vdd in ANCHOR_VDD:
            key = vkey(vdd)
            medium_only = next(float(row["D_rise_ps"]) for row in historical if float(row["vdd_v"]) == vdd and int(row["code"]) == 8)
            driver = next(float(row["D_rise_ps"]) for row in screen_rows if row["candidate_id"] == "driver_only" and float(row["vdd_v"]) == vdd)
            bank0 = next(float(row["D_rise_ps"]) for row in coverage if int(row["medium_code"]) == 8 and int(row["fine_code"]) == 0 and float(row["vdd_v"]) == vdd)
            result["future_bypass_interface"]["fine_driver_offset_ps_by_vdd"][key] = driver - medium_only
            result["future_bypass_interface"]["fine_bank_code0_offset_ps_by_vdd"][key] = bank0 - driver
        write_json(analysis / "future_bypass_interface.json", result["future_bypass_interface"])
    return result


def render_report(path: Path, result: Mapping[str, Any], candidates: Mapping[str, Any], metrics: Sequence[Mapping[str, Any]], winner: Optional[Mapping[str, Any]], interface: Mapping[str, Any]) -> None:
    """Render the complete metric table and terminal winner evidence."""

    lines = ["# SMIC40LL Intermediate LVT Fine-Load Size Sweep", "", "## Policy", "", "- Sizes: `X0P7, X1, X1P4, X2, X3, X4, X6`.", "- Candidate selection: widest CDL total transistor width per NAND/NOR size; ties prefer M.", "- Waveform policy: high `>= 0.90 * VDD`, low `<= 0.10 * VDD`.", "- Output settling metric: maximum measured 10%-90% rise/fall time.", "- Historical X0P5 and X8 results are reference-only and were not rerun.", "", "## Four-Metric Scan", "", "| Candidate | Unit delta ps (1.10/0.95/0.80) | K pred | Max fine ps | Max settle ps | Result |", "|---|---|---|---|---|---|"]
    for item in metrics:
        delta = item.get("unit_delta_ps_by_vdd", {})
        kpred = item.get("K_pred_by_vdd", {})
        fine = item.get("delta_fine_max_ps_by_vdd", {})
        settle = item.get("settling_max_ps_by_vdd", {})
        lines.append("| `{}` | {} / {} / {} | {} | {} / {} / {} | {} / {} / {} | {} |".format(item["candidate_id"], delta.get("1.10"), delta.get("0.95"), delta.get("0.80"), item.get("K_candidate"), fine.get("1.10"), fine.get("0.95"), fine.get("0.80"), settle.get("1.10"), settle.get("0.95"), settle.get("0.80"), item.get("decision")))
    lines.extend(["", "## Decision", "", "- Static candidates: {}.".format(candidates["candidate_count"]), "- Scan HSPICE budget: 171 single-load plus 756 K=8 full-code scenarios.", "- Retained scan PASS scenarios: {}.".format(result.get("retained_pass_scenarios")), "- Winner: `{}`.".format(winner["candidate_id"] if winner else "none"), "- Winner acceptance: `{}`.".format(result.get("winner_decision", "NOT_RUN")), "- Historical medium scenarios rerun: `0`.", "- Historical FTC runner invocations: `0`.", "- Bypass/configuration skip/sensor/XOR/DFF/calibration/PVT/RTL/power/area/layout: `0`."])
    if result.get("winner_reasons"):
        lines.extend(["", "## Winner Gate Reasons", "", *["- {}".format(reason) for reason in result["winner_reasons"]]])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run static discovery, complete size metrics, and one bounded winner check."""

    parser = argparse.ArgumentParser(description="scan intermediate SMIC40LL LVT fine-load sizes")
    parser.add_argument("--config", type=Path, default=FTC_ROOT / "ftc_config.json")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis" / "standard_cell_load_size_sweep")
    parser.add_argument("--run-root", type=Path, default=FTC_ROOT / "runs" / "standard_cell_load_size_sweep")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports" / "FTC_STANDARD_CELL_LOAD_SIZE_SWEEP.md")
    parser.add_argument("--stop-after", choices=("static", "single", "scan"))
    args = parser.parse_args(args=list(argv) if argv is not None else None)
    analysis, run_root, config = args.analysis_dir.resolve(), args.run_root.resolve(), load_json(args.config.resolve())
    interface, cells, paths = freeze_inputs()
    analysis.mkdir(parents=True, exist_ok=True)
    req = requirements(interface, paths)
    write_json(analysis / "requirements.json", req)
    candidates_doc = discover_size_candidates(cells)
    write_json(analysis / "size_scan_candidates.json", candidates_doc)
    if args.stop_after == "static":
        print("FTC_STANDARD_CELL_LOAD_SIZE_SWEEP static=GO")
        return 0
    hspice, version = CORE.validate_hspice(config)
    stats = {"new": 0, "reused": 0}
    static_sig = signature(Path(__file__), analysis / "requirements.json", analysis / "size_scan_candidates.json")
    run_dir = select_run_dir(run_root, static_sig, hspice, version, "single_load")
    screen = [measure("size_scan_driver_baseline", hspice, run_dir, config, cells, None, 8, vdd, 0, 0, "none", "none", static_sig, stats) for vdd in ANCHOR_VDD]
    for candidate in candidates_doc["candidates"]:
        for vdd in ANCHOR_VDD:
            for control in (0, 1):
                screen.append(measure("size_scan_single_load", hspice, run_dir, config, cells, candidate, 8, vdd, 1, 1, "unknown", control, static_sig, stats, control))
    write_csv(analysis / "size_scan_single_load.csv", screen, CORE.ROW_FIELDS)
    if stats["new"] > 171:
        raise RuntimeError("single-load size scan exceeded 171 scenarios")
    decision_doc = single_decisions(screen, interface)
    write_json(analysis / "size_scan_single_load_decision.json", decision_doc)
    if args.stop_after == "single":
        print("FTC_STANDARD_CELL_LOAD_SIZE_SWEEP single=GO")
        return 0
    fine_candidates = {item["candidate_id"]: item for item in candidates_doc["candidates"]}
    scan_sig = signature(Path(__file__), analysis / "requirements.json", analysis / "size_scan_candidates.json", analysis / "size_scan_single_load_decision.json")
    run_dir = select_run_dir(run_root, scan_sig, hspice, version, "k8_scan")
    fine_rows = []
    for decision in decision_doc["decisions"]:
        if not decision["mapping_valid"]:
            continue
        candidate = fine_candidates[decision["candidate_id"]]
        for vdd in ANCHOR_VDD:
            for code in range(K_TEST + 1):
                fine_rows.append(measure(SCAN_STAGE, hspice, run_dir, config, cells, candidate, 8, vdd, K_TEST, code, decision["low_cap_control_value"], decision["high_cap_control_value"], scan_sig, stats))
    write_csv(analysis / "size_scan_8unit.csv", fine_rows, CORE.ROW_FIELDS)
    metrics = metric_rows(fine_rows, decision_doc, fine_candidates, interface)
    write_csv(analysis / "size_scan_metrics.csv", [{field: json.dumps(item.get(field), sort_keys=True) if isinstance(item.get(field), (dict, list)) else item.get(field) for field in METRIC_FIELDS} for item in metrics], METRIC_FIELDS)
    winner_metric = choose_winner(metrics, interface)
    winner = None
    winner_result = {"winner_decision": "NOT_RUN", "winner_reasons": []}
    if args.stop_after == "scan":
        summary = {"schema_version": 1, "decision": "SCAN_COMPLETE", "static_candidate_count": len(candidates_doc["candidates"]), "new_hspice_scenarios": retained_count(run_root), "reused_new_task_scenarios": 0, "historical_medium_scenarios_rerun": 0, "historical_runner_invocations": 0, "sensor_scenarios": 0, "dff_scenarios": 0, "droop_scenarios": 0, "bypass_scenarios": 0, "winner_candidate_id": winner_metric["candidate_id"] if winner_metric else None, "metrics": metrics}
        write_json(analysis / "summary.json", summary)
        render_report(args.report_output.resolve(), {**summary, "retained_pass_scenarios": summary["new_hspice_scenarios"], "winner_decision": "NOT_RUN"}, candidates_doc, metrics, winner_metric, interface)
        print("FTC_STANDARD_CELL_LOAD_SIZE_SWEEP scan=COMPLETE")
        return 0
    if winner_metric:
        winner = fine_candidates[winner_metric["candidate_id"]].copy()
        selected_decision = next(item for item in decision_doc["decisions"] if item["candidate_id"] == winner_metric["candidate_id"])
        winner.update({"decision": "GO", "K_candidate": winner_metric["K_candidate"], "unit_delta_ps_by_vdd": winner_metric["unit_delta_ps_by_vdd"], "low_cap_control_value": selected_decision["low_cap_control_value"], "high_cap_control_value": selected_decision["high_cap_control_value"], "selected_by": "minimum_K_then_resolution_then_settling_then_candidate_id"})
        write_json(analysis / "selected_size_contract.json", winner)
        winner_sig = signature(Path(__file__), analysis / "requirements.json", analysis / "selected_size_contract.json")
        run_dir = select_run_dir(run_root, winner_sig, hspice, version, "winner_acceptance")
        winner_result = winner_acceptance(winner, int(winner_metric["K_candidate"]), analysis, run_dir, hspice, config, cells, winner_sig, stats, interface, screen)
        winner_result["winner_decision"] = winner_result.get("decision", "NO-GO")
        winner_result["winner_reasons"] = winner_result.get("coverage_reasons", []) + winner_result.get("monotonic_reasons", []) + winner_result.get("coupled_reasons", [])
    summary = {"schema_version": 1, "decision": "GO" if winner and winner_result.get("winner_decision") == "GO" else "NO-GO", "static_candidate_count": len(candidates_doc["candidates"]), "new_hspice_scenarios": retained_count(run_root), "reused_new_task_scenarios": 0, "historical_medium_scenarios_rerun": 0, "historical_runner_invocations": 0, "sensor_scenarios": 0, "dff_scenarios": 0, "droop_scenarios": 0, "bypass_scenarios": 0, "winner_candidate_id": winner.get("candidate_id") if winner else None, "winner_decision": winner_result.get("winner_decision"), "winner_reasons": winner_result.get("winner_reasons", []), "metrics": metrics}
    write_json(analysis / "summary.json", summary)
    render_report(args.report_output.resolve(), {**summary, "retained_pass_scenarios": summary["new_hspice_scenarios"]}, candidates_doc, metrics, winner, interface)
    print("FTC_STANDARD_CELL_LOAD_SIZE_SWEEP decision={}".format(summary["decision"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
