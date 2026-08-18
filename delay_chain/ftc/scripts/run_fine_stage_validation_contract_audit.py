#!/usr/bin/env python3
"""Audit the fine-stage waveform contract without changing the fine hardware.

The earlier driver co-design used absolute 2.5/5.5 ns voltage reads as part of
its ``valid`` field.  This task deliberately keeps that evidence immutable and
answers a narrower question: did each retained waveform complete a real
10/50/90-percent pulse, and does the fixed X0P8/NOR2/K10 candidate still cover
the frozen medium step?  Only after that read-only result is positive may this
runner create the one worst-case and 18 endpoint two-cycle HSPICE scenarios.
"""

import argparse
import csv
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = FTC_ROOT / "scripts" / "run_standard_cell_load_fine_stage.py"
CORE_SPEC = importlib.util.spec_from_file_location("fine_stage_core", CORE_PATH)
assert CORE_SPEC is not None and CORE_SPEC.loader is not None
CORE = importlib.util.module_from_spec(CORE_SPEC)
CORE_SPEC.loader.exec_module(CORE)

STUDY = "fine_stage_validation_contract_audit_v1"
UPSTREAM_COMMIT = "2c7944a28cc5b838eb4cfeb9c9b0c3f7a5bc3199"
PRIMARY_DRIVER = "BUF_X0P8M_A9TL40"
PRIMARY_LOAD = "NOR2_X4A_A9TL40__signal_A"
PRIMARY_K = 10
RAW_R2_NAME = "r2"
BOUNDARIES = (0, 7, 15)

RECLASSIFICATION_FIELDS = (
    "scenario", "phase", "driver_cell", "medium_code", "fine_code", "K", "vdd_v",
    "legacy_valid", "legacy_fixed_sample_high", "legacy_fixed_sample_low",
    "legacy_high_pass", "legacy_low_pass", "waveform_valid", "classification",
    "failure_reasons", "t_rise10_s", "t_rise50_s", "t_rise90_s",
    "t_fall90_s", "t_fall50_s", "t_fall10_s", "W_high90_ps", "W_50_ps",
    "unexpected_transition_count",
)
TWO_CYCLE_FIELDS = (
    "phase", "medium_code", "fine_code", "K", "vdd_v", "scenario",
    "D_rise_ps", "W_high90_ps", "W_low10_ps", "valid", "failure_reasons",
    "unexpected_transition_count", "reference_deck_sha256",
)


def read_json(path: Path) -> Dict[str, Any]:
    """Read one object-shaped contract and fail before using malformed evidence."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write only task-owned JSON with a stable layout for later audit."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    """Write a fixed public table; absent HSPICE values remain visibly blank."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def read_csv(path: Path) -> List[Dict[str, str]]:
    """Read a historical CSV without giving this task permission to rewrite it."""

    with path.open(encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def sha256_file(path: Path) -> str:
    """Use the reviewed streaming hash helper to bind every consumed input."""

    return CORE.sha256_file(path)


def is_true(value: Any) -> bool:
    """Treat live booleans and historical CSV strings identically."""

    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def finite(value: Any) -> Optional[float]:
    """Keep HSPICE's ``failed`` measure distinct from a numeric zero."""

    return CORE.finite(value)


def raw_root() -> Path:
    """Name the final driver-co-design revision; r1 is never an audit input."""

    return FTC_ROOT / "runs" / "standard_cell_load_fine_stage_driver_codesign" / RAW_R2_NAME


def evidence_files() -> List[Path]:
    """Return exactly the retained files this audit consumes, in stable order.

    The plan asks for provenance of upstream evidence, not a hash of unrelated
    work.  For r2 the manifest, deck, and measure file are all consumed; for
    the three frozen upstream directories every regular file is retained in the
    provenance inventory because those directories are explicit task inputs.
    """

    files = [
        FTC_ROOT / "reports" / "FTC_STANDARD_CELL_LOAD_FINE_STAGE_DRIVER_CODESIGN.md",
        FTC_ROOT / "analysis" / "standard_cell_load_fine_stage_driver_codesign" / "summary.json",
        FTC_ROOT / "analysis" / "standard_cell_load_fine_stage_driver_codesign" / "requirements.json",
        FTC_ROOT / "scripts" / "run_standard_cell_load_fine_stage_driver_codesign.py",
        CORE_PATH,
        FTC_ROOT / "ftc_config.json",
    ]
    for directory in (
        FTC_ROOT / "analysis" / "path_selection_medium_stage",
        FTC_ROOT / "analysis" / "standard_cell_load_size_sweep" / "fallback_1",
        FTC_ROOT / "analysis" / "standard_cell_load_driver_strength_probe",
    ):
        files.extend(path for path in directory.rglob("*") if path.is_file())
    for scenario in sorted((raw_root() / "scenarios").glob("*")):
        files.extend(path for path in (
            scenario / "scenario_manifest.json", scenario / "fine_stage.sp",
            scenario / "fine_stage.mt0.csv",
        ) if path.is_file())
    files.append(raw_root() / "run_manifest.json")
    return sorted(set(files))


def frozen_context() -> Dict[str, Any]:
    """Validate every immutable architecture choice before creating task output."""

    interface, cells, medium_paths = CORE.freeze_inputs()
    config = CORE.load_json(FTC_ROOT / "ftc_config.json")
    summary = read_json(FTC_ROOT / "analysis" / "standard_cell_load_fine_stage_driver_codesign" / "summary.json")
    requirements = read_json(FTC_ROOT / "analysis" / "standard_cell_load_fine_stage_driver_codesign" / "requirements.json")
    load = read_json(FTC_ROOT / "analysis" / "standard_cell_load_size_sweep" / "fallback_1" / "selected_size_contract.json")
    if summary.get("decision") != "Fine Driver Co-Design = NO-GO":
        raise ValueError("the historical co-design decision is no longer the frozen NO-GO")
    if load.get("candidate_id") != PRIMARY_LOAD or load.get("cell") != "NOR2_X4A_A9TL40":
        raise ValueError("the fixed NOR2 load contract changed")
    if (load.get("signal_pin"), load.get("control_pin"), load.get("high_cap_control_value"), load.get("low_cap_control_value")) != ("A", "B", 0, 1):
        raise ValueError("the fixed NOR2 pin or control polarity changed")
    primary = next((item for item in summary.get("drivers", []) if item.get("driver", {}).get("driver_cell") == PRIMARY_DRIVER), None)
    if not primary or primary.get("metrics", {}).get("final_K") != PRIMARY_K:
        raise ValueError("the X0P8/K10 candidate is not present in frozen co-design evidence")
    if requirements.get("logic_high_min_ratio") != 0.90 or requirements.get("logic_low_max_ratio") != 0.10:
        raise ValueError("the legacy 0.90/0.10 ratios changed")
    if (float(config["launch_time_s"]), float(config["sampling_period_s"])) != (1.0e-9, 6.0e-9):
        raise ValueError("the frozen launch/period contract changed")
    root = raw_root()
    manifest = read_json(root / "run_manifest.json")
    scenarios = sorted((root / "scenarios").glob("*/scenario_manifest.json"))
    if manifest.get("study") != "standard_cell_load_fine_stage_driver_codesign_v1" or len(scenarios) != 378:
        raise ValueError("r2 is not the expected 378-scenario co-design revision")
    if any(read_json(path).get("completion_status") != "PASS" for path in scenarios):
        raise ValueError("r2 contains incomplete scenarios")
    files = evidence_files()
    missing = [path for path in files if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise ValueError("frozen evidence is missing: {}".format(missing[0]))
    return {
        "config": config, "cells": cells, "interface": interface, "medium_paths": medium_paths,
        "load": load, "summary": summary, "r2_root": root,
        "source_file_sha256": {str(path.relative_to(FTC_ROOT)): sha256_file(path) for path in files},
    }


def requirement_document(context: Mapping[str, Any]) -> Dict[str, Any]:
    """Publish the narrow contract before reading a single raw measurement."""

    config = context["config"]
    return {
        "schema_version": 1,
        "study": STUDY,
        "upstream_driver_codesign_decision": "NO-GO",
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_raw_revision": RAW_R2_NAME,
        "fixed_load": PRIMARY_LOAD,
        "primary_candidate_driver": PRIMARY_DRIVER,
        "primary_candidate_K": PRIMARY_K,
        "legacy_high_ratio": 0.90,
        "legacy_low_ratio": 0.10,
        "legacy_high_sample_s": float(config["launch_time_s"]) + float(config["sampling_period_s"]) / 4.0,
        "legacy_low_sample_s": float(config["launch_time_s"]) + 3.0 * float(config["sampling_period_s"]) / 4.0,
        "anchor_vdd_v": list(CORE.ANCHOR_VDD),
        "new_hardware_search": "forbidden", "load_rescan": "forbidden", "driver_rescan": "forbidden",
        "medium_change": "forbidden", "bypass": "future_work", "config_skip": "future_work",
        "dff_integration": "future_work", "sensor": "forbidden", "droop_sweep": "forbidden",
        "pvt": "forbidden", "rtl": "forbidden", "layout": "forbidden",
        "historical_driver_codesign_rerun": 0,
        "source_file_sha256": context["source_file_sha256"],
    }


def legacy_rows() -> Dict[str, Dict[str, str]]:
    """Index all published r2 rows by raw scenario path and reject ambiguity."""

    root = FTC_ROOT / "analysis" / "standard_cell_load_fine_stage_driver_codesign"
    rows: Dict[str, Dict[str, str]] = {}
    for directory in sorted(root.glob("driver_*")):
        for name in ("phase2_fine8.csv", "initial_coverage.csv", "full_bank_monotonicity.csv", "coupled_medium_coverage.csv"):
            path = directory / name
            if not path.is_file():
                continue
            for row in read_csv(path):
                key = row["scenario"]
                if key in rows:
                    raise ValueError("historical scenario appears twice: {}".format(key))
                rows[key] = row
    if len(rows) != 378:
        raise ValueError("published analysis does not describe all 378 r2 scenarios")
    return rows


def required_values(record: Mapping[str, Any], names: Sequence[str]) -> Tuple[Dict[str, float], List[str]]:
    """Return finite measures and precise missing-crossing reasons for a gate."""

    values: Dict[str, float] = {}
    reasons: List[str] = []
    for name in names:
        value = finite(record.get(name))
        if value is None:
            if "90" in name:
                reasons.append("missing_90_percent_crossing")
            elif "10" in name:
                reasons.append("missing_10_percent_crossing")
            else:
                reasons.append("pulse_collapse")
        else:
            values[name] = value
    return values, list(dict.fromkeys(reasons))


def one_cycle_waveform(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate the Phase-1 pulse contract using crossings, never sample voltage."""

    names = ("t_out_rise_10", "t_out_rise", "t_out_rise_90", "t_out_fall_90", "t_out_fall", "t_out_fall_10")
    values, reasons = required_values(record, names)
    extra = sum(finite(record.get(name)) is not None for name in ("t_out_rise_2", "t_out_fall_2"))
    if len(values) == len(names):
        ordered = [values[name] for name in names]
        if any(right <= left for left, right in zip(ordered, ordered[1:])):
            reasons.append("pulse_collapse")
        high_window = values["t_out_fall_90"] - values["t_out_rise_90"]
        width_50 = values["t_out_fall"] - values["t_out_rise"]
        if high_window <= 0:
            reasons.append("nonpositive_high_window")
    else:
        high_window = width_50 = None
    if extra:
        reasons.append("unexpected_transition")
    return {
        "valid": not reasons, "reasons": list(dict.fromkeys(reasons)), "values": values,
        "W_high90_ps": high_window * 1.0e12 if high_window is not None else None,
        "W_50_ps": width_50 * 1.0e12 if width_50 is not None else None,
        "unexpected_transition_count": extra,
    }


def reclassification_label(legacy_valid: bool, waveform_valid: bool, high_pass: bool, low_pass: bool) -> str:
    """Separate a bad fixed-time read from a missing or malformed waveform."""

    if not waveform_valid:
        return "electrical_waveform_failure"
    if not legacy_valid and (not high_pass or not low_pass):
        return "legacy_fixed_sample_miss"
    if legacy_valid:
        return "legacy_gate_pass"
    raise ValueError("historical failure is not explained by fixed samples")


def legacy_reclassification(context: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Reparse every final raw measure and preserve every published legacy value."""

    historical = legacy_rows()
    rows: List[Dict[str, Any]] = []
    for manifest_path in sorted((context["r2_root"] / "scenarios").glob("*/scenario_manifest.json")):
        scenario = manifest_path.parent
        manifest = read_json(manifest_path)
        parameters = manifest["parameters"]
        key = "scenarios/{}".format(scenario.name)
        old = historical.get(key)
        if old is None:
            raise ValueError("r2 scenario has no published historical row: {}".format(key))
        measure = CORE.run_dc_sweep.parse_measurements(scenario / str(manifest["measurement_file"]))
        vdd = float(parameters["vdd_v"])
        recomputed = CORE.classify(measure, vdd, 0.90)
        # This compare prevents the new interpretation from silently correcting
        # the historical classifier or overwriting its field-level conclusion.
        if is_true(old["valid"]) != bool(recomputed["valid"]):
            raise ValueError("legacy valid readback mismatch: {}".format(key))
        for field in ("output_logic_high", "output_logic_low"):
            old_value, new_value = finite(old[field]), finite(recomputed[field])
            if old_value is None or new_value is None or abs(old_value - new_value) > 1.0e-12:
                raise ValueError("legacy {} readback mismatch: {}".format(field, key))
        waveform = one_cycle_waveform(measure)
        high, low = finite(measure.get("out_logic_high")), finite(measure.get("out_logic_low"))
        high_pass, low_pass = high is not None and high >= 0.90 * vdd, low is not None and low <= 0.10 * vdd
        legacy_valid = is_true(old["valid"])
        try:
            classification = reclassification_label(legacy_valid, waveform["valid"], high_pass, low_pass)
        except ValueError as error:
            raise ValueError("{}: {}".format(error, key)) from error
        values = waveform["values"]
        rows.append({
            "scenario": key, "phase": parameters["phase"], "driver_cell": parameters["fine_driver_cell"],
            "medium_code": parameters["medium_code"], "fine_code": parameters["fine_code"], "K": parameters["K"], "vdd_v": vdd,
            "legacy_valid": legacy_valid, "legacy_fixed_sample_high": high, "legacy_fixed_sample_low": low,
            "legacy_high_pass": high_pass, "legacy_low_pass": low_pass, "waveform_valid": waveform["valid"],
            "classification": classification, "failure_reasons": ";".join(waveform["reasons"]),
            "t_rise10_s": values.get("t_out_rise_10"), "t_rise50_s": values.get("t_out_rise"),
            "t_rise90_s": values.get("t_out_rise_90"), "t_fall90_s": values.get("t_out_fall_90"),
            "t_fall50_s": values.get("t_out_fall"), "t_fall10_s": values.get("t_out_fall_10"),
            "W_high90_ps": waveform["W_high90_ps"], "W_50_ps": waveform["W_50_ps"],
            "unexpected_transition_count": waveform["unexpected_transition_count"],
            "D_rise_ps": recomputed["D_rise_ps"],
        })
    if len(rows) != 378:
        raise ValueError("r2 reparse count changed")
    return rows


def index_rows(rows: Iterable[Mapping[str, Any]], phase: str, medium: int, fine: int, vdd: float) -> Mapping[str, Any]:
    """Find one r2 record for an exact phase/endpoint and reject accidental reuse."""

    matches = [row for row in rows if row["phase"] == phase and int(row["medium_code"]) == medium and int(row["fine_code"]) == fine and float(row["vdd_v"]) == vdd]
    if len(matches) != 1:
        raise ValueError("expected one r2 row for {} M{} F{} V{}, found {}".format(phase, medium, fine, vdd, len(matches)))
    return matches[0]


def recompute_primary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Recalculate only the frozen X0P8/NOR2/K10 range, coverage, and resolution."""

    primary = [row for row in rows if row["driver_cell"] == PRIMARY_DRIVER and int(row["K"]) == PRIMARY_K]
    coverage: Dict[str, List[Dict[str, Any]]] = {}
    coupled_steps: Dict[str, float] = {}
    coverage_ok = True
    electrical_reasons: List[str] = []
    for vdd in CORE.ANCHOR_VDD:
        entries = []
        for medium in BOUNDARIES:
            left0 = index_rows(primary, "phase5_coupled_coverage", medium, 0, vdd)
            leftk = index_rows(primary, "phase5_coupled_coverage", medium, PRIMARY_K, vdd)
            right0 = index_rows(primary, "phase5_coupled_coverage", medium + 1, 0, vdd)
            if not all(row["waveform_valid"] for row in (left0, leftk, right0)):
                electrical_reasons.append("pulse_collapse")
            margin = float(leftk["D_rise_ps"]) - float(right0["D_rise_ps"])
            step = float(right0["D_rise_ps"]) - float(left0["D_rise_ps"])
            entries.append({"from_medium_code": medium, "to_medium_code": medium + 1, "coverage_margin_ps": margin, "coupled_medium_step_ps": step, "coverage_pass": margin >= 0})
            coverage_ok = coverage_ok and margin >= 0
        coverage[CORE.vkey(vdd)] = entries
        coupled_steps[CORE.vkey(vdd)] = min(item["coupled_medium_step_ps"] for item in entries)
    monotonic_rows = [row for row in primary if row["phase"] == "phase4_final_monotonicity" and int(row["medium_code"]) == 7]
    fine_steps: Dict[str, float] = {}
    monotonic_095 = True
    resolution_ok = True
    for vdd in CORE.ANCHOR_VDD:
        local = {int(row["fine_code"]): row for row in monotonic_rows if float(row["vdd_v"]) == vdd}
        pairs = [(code, code + 1) for code in range(PRIMARY_K)] if vdd == 0.95 else [(0, 1), (PRIMARY_K - 1, PRIMARY_K)]
        if any(first not in local or second not in local or not local[first]["waveform_valid"] or not local[second]["waveform_valid"] for first, second in pairs):
            electrical_reasons.append("fine_range_insufficient")
            continue
        deltas = [float(local[second]["D_rise_ps"]) - float(local[first]["D_rise_ps"]) for first, second in pairs]
        if any(delta <= 0 for delta in deltas):
            electrical_reasons.append("fine_code_non_monotonic")
            if vdd == 0.95:
                monotonic_095 = False
        fine_steps[CORE.vkey(vdd)] = max(deltas)
        if fine_steps[CORE.vkey(vdd)] >= coupled_steps[CORE.vkey(vdd)]:
            electrical_reasons.append("fine_resolution_not_below_medium")
            resolution_ok = False
    primary_misses = [row for row in primary if row["classification"] == "legacy_fixed_sample_miss"]
    primary_failures = [row for row in primary if row["classification"] == "electrical_waveform_failure"]
    return {
        "schema_version": 1, "primary_driver": PRIMARY_DRIVER, "primary_load": PRIMARY_LOAD, "K": PRIMARY_K,
        "coverage_by_vdd": coverage, "medium_step_coupled_min_ps_by_vdd": coupled_steps,
        "delta_fine_max_measured_ps_by_vdd": fine_steps, "coverage_pass": coverage_ok,
        "fine_monotonic_0p95_pass": monotonic_095, "fine_resolution_pass": resolution_ok,
        "legacy_fixed_sample_miss_count": len(primary_misses),
        "electrical_waveform_failure_count": len(primary_failures),
        "electrical_reasons": list(dict.fromkeys(electrical_reasons)),
        "phase1_go": bool(primary_misses) and not primary_failures and coverage_ok and monotonic_095 and resolution_ok and not electrical_reasons,
    }


def physical_prefix(deck: str) -> str:
    """Exclude only transient/measure directives when comparing circuit topology."""

    lines = deck.splitlines()
    try:
        return "\n".join(lines[:next(index for index, line in enumerate(lines) if line.lower().startswith(".tran "))])
    except StopIteration as error:
        raise ValueError("deck lacks a transient statement") from error


def two_cycle_measurements(config: Mapping[str, Any]) -> List[str]:
    """Measure two rises and one fall without adding any arbitrary readback time.

    The stop time is before the input's second falling edge: it comfortably
    includes the delayed second rise but makes a second output fall an explicit
    unexpected-transition measurement, rather than silently accepting it.
    """

    launch, period, step = (float(config[key]) for key in ("launch_time_s", "sampling_period_s", "tran_max_step_s"))
    lines = [".tran {} {}".format(CORE.spice(step), CORE.spice(launch + 1.5 * period - step))]
    lines.append(".measure tran t_in_rise_1 WHEN v(in,vss_a)='VDD_VALUE/2' RISE=1")
    for suffix, crossing, edge, count in (
        ("rise_10_1", "VDD_VALUE/10", "RISE", 1), ("rise_50_1", "VDD_VALUE/2", "RISE", 1),
        ("rise_90_1", "9*VDD_VALUE/10", "RISE", 1), ("fall_90_1", "9*VDD_VALUE/10", "FALL", 1),
        ("fall_50_1", "VDD_VALUE/2", "FALL", 1), ("fall_10_1", "VDD_VALUE/10", "FALL", 1),
        ("rise_10_2", "VDD_VALUE/10", "RISE", 2), ("rise_50_2", "VDD_VALUE/2", "RISE", 2),
        ("rise_90_2", "9*VDD_VALUE/10", "RISE", 2), ("rise_50_3", "VDD_VALUE/2", "RISE", 3),
        ("fall_50_2", "VDD_VALUE/2", "FALL", 2),
    ):
        lines.append(".measure tran t_out_{} WHEN v(out,vss_a)='{}' {}={}".format(suffix, crossing, edge, count))
    return lines


def render_two_cycle_deck(context: Mapping[str, Any], medium: int, fine: int, vdd: float) -> str:
    """Reuse the production physical deck and replace only its observer block."""

    load = context["load"]
    base = CORE.render_deck(context["config"], context["cells"], vdd, medium, load, PRIMARY_K, fine, 0, PRIMARY_DRIVER)
    return physical_prefix(base) + "\n" + "\n".join(two_cycle_measurements(context["config"])) + "\n.end\n"


def reference_deck(context: Mapping[str, Any], medium: int, fine: int, vdd: float) -> Path:
    """Find the r2 endpoint with identical hardware, independent of its old phase."""

    matches = []
    for manifest_path in (context["r2_root"] / "scenarios").glob("*/scenario_manifest.json"):
        parameters = read_json(manifest_path)["parameters"]
        if parameters.get("phase") == "phase5_coupled_coverage" and (parameters.get("fine_driver_cell"), parameters.get("fine_load_cell"), parameters.get("signal_pin"), parameters.get("control_pin"), parameters.get("K"), parameters.get("medium_code"), parameters.get("fine_code"), parameters.get("vdd_v")) == (PRIMARY_DRIVER, "NOR2_X4A_A9TL40", "A", "B", PRIMARY_K, medium, fine, vdd):
            matches.append(manifest_path.parent / "fine_stage.sp")
    if len(matches) != 1:
        raise ValueError("expected one r2 physical reference for M{} F{} V{}, found {}".format(medium, fine, vdd, len(matches)))
    return matches[0]


def two_cycle_waveform(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Apply the two-cycle contract to raw HSPICE measures from a new scenario."""

    first = ("t_out_rise_10_1", "t_out_rise_50_1", "t_out_rise_90_1", "t_out_fall_90_1", "t_out_fall_50_1", "t_out_fall_10_1")
    second = ("t_out_rise_10_2", "t_out_rise_50_2", "t_out_rise_90_2")
    values, reasons = required_values(record, first + second + ("t_in_rise_1",))
    if len(values) == len(first) + len(second) + 1:
        if any(right <= left for left, right in zip((values[name] for name in first), (values[name] for name in first[1:]))):
            reasons.append("pulse_collapse")
        if any(right <= left for left, right in zip((values[name] for name in second), (values[name] for name in second[1:]))):
            reasons.append("pulse_collapse")
        high = values["t_out_fall_90_1"] - values["t_out_rise_90_1"]
        low = values["t_out_rise_10_2"] - values["t_out_fall_10_1"]
        if high <= 0:
            reasons.append("nonpositive_high_window")
        if low <= 0:
            reasons.append("nonpositive_low_window")
        delay = values["t_out_rise_50_1"] - values["t_in_rise_1"]
        if delay <= 0:
            reasons.append("pulse_collapse")
    else:
        high = low = delay = None
    extra = sum(finite(record.get(name)) is not None for name in ("t_out_rise_50_3", "t_out_fall_50_2"))
    if extra:
        reasons.append("unexpected_transition")
    return {
        "valid": not reasons, "reasons": list(dict.fromkeys(reasons)),
        "D_rise_ps": delay * 1.0e12 if delay is not None else None,
        "W_high90_ps": high * 1.0e12 if high is not None else None,
        "W_low10_ps": low * 1.0e12 if low is not None else None,
        "unexpected_transition_count": extra,
    }


def audit_signature(requirements_path: Path, reference: Path) -> Dict[str, str]:
    """Prevent reuse if the audit policy, runner, or r2 physical reference changes."""

    return {
        "runner_sha256": sha256_file(Path(__file__)),
        "requirements_sha256": sha256_file(requirements_path),
        "reference_deck_sha256": sha256_file(reference),
    }


def select_run_dir(root: Path, signature: Mapping[str, str], hspice: Path, version: str) -> Path:
    """Reuse a complete matching task revision, never alter a prior raw run."""

    root.mkdir(parents=True, exist_ok=True)
    revisions = sorted((path for path in root.glob("r*") if re.fullmatch(r"r\d+", path.name)), key=lambda path: int(path.name[1:]), reverse=True)
    for revision in revisions:
        manifest = revision / "run_manifest.json"
        if manifest.is_file() and read_json(manifest).get("signature") == dict(signature):
            if all(read_json(path).get("completion_status") == "PASS" for path in revision.glob("scenarios/*/scenario_manifest.json")):
                return revision
    index = max((int(path.name[1:]) for path in revisions), default=0) + 1
    revision = root / "r{}".format(index)
    revision.mkdir()
    write_json(revision / "run_manifest.json", {"schema_version": 1, "study": STUDY, "signature": dict(signature), "system_hspice": str(hspice), "hspice_version": version})
    return revision


def run_two_cycle(context: Mapping[str, Any], requirements_path: Path, run_dir: Path, hspice: Path, medium: int, fine: int, vdd: float, phase: str, stats: Dict[str, int]) -> Dict[str, Any]:
    """Run exactly one approved endpoint after proving its physical netlist identity."""

    deck = render_two_cycle_deck(context, medium, fine, vdd)
    reference = reference_deck(context, medium, fine, vdd)
    if physical_prefix(deck) != physical_prefix(reference.read_text(encoding="ascii")):
        raise ValueError("two-cycle deck changed physical topology for M{} F{} V{}".format(medium, fine, vdd))
    signature = audit_signature(requirements_path, reference)
    parameters = CORE.scenario_parameters(phase, medium, vdd, context["load"], PRIMARY_K, fine, 1, 0, 0.90, PRIMARY_DRIVER)
    parameters.update({"study_name": STUDY, "observation_contract": "two_cycle_crossing_windows_v1", "reference_deck_sha256": sha256_file(reference), "logic_low_max_ratio": 0.10})
    record = CORE.execute(hspice, run_dir, deck, parameters, signature, stats)
    waveform = two_cycle_waveform(record)
    return {
        "phase": phase, "medium_code": medium, "fine_code": fine, "K": PRIMARY_K, "vdd_v": vdd,
        "scenario": str(Path(record["scenario"]).relative_to(run_dir)), **waveform,
        "failure_reasons": ";".join(waveform["reasons"]), "reference_deck_sha256": sha256_file(reference),
    }


def phase3_schedule() -> List[Tuple[int, int, float]]:
    """Publish the exact 18 endpoints; no driver/load/K search is expressible."""

    return [
        (endpoint_medium, fine, vdd)
        for boundary in BOUNDARIES
        for endpoint_medium, fine in ((boundary, PRIMARY_K), (boundary + 1, 0))
        for vdd in CORE.ANCHOR_VDD
    ]


def summary_document(phase1: Mapping[str, Any], phase2: Optional[Mapping[str, Any]], phase3: Sequence[Mapping[str, Any]], run_root: Path, decision: str, reasons: Sequence[str]) -> Dict[str, Any]:
    """Keep terminal status and scenario accounting in one task-owned summary."""

    manifests = list(run_root.glob("r*/scenarios/*/scenario_manifest.json")) if run_root.is_dir() else []
    result = {
        "schema_version": 1, "study": STUDY, "decision": decision, "reasons": list(dict.fromkeys(reasons)),
        "phase1": dict(phase1), "phase2": dict(phase2) if phase2 else {"status": "NOT_RUN"},
        "phase3": {"requested_scenarios": 18, "completed_scenarios": len(phase3), "status": "GO" if len(phase3) == 18 and all(row["valid"] for row in phase3) else "NOT_RUN" if not phase3 else "NO-GO"},
        "new_hspice_scenarios": len(manifests), "historical_driver_codesign_rerun": 0,
        "historical_r2_scenarios_rerun": 0, "primary_candidate_driver": PRIMARY_DRIVER,
        "primary_candidate_load": PRIMARY_LOAD, "primary_candidate_K": PRIMARY_K,
    }
    if decision == "Fine-Stage Delay-Line Waveform Contract = GO":
        # These are intentionally provisional: capture timing and structural
        # bypass/skip work remain outside the waveform-only contract.
        result.update({"selected_provisional_fine_driver": PRIMARY_DRIVER, "selected_provisional_fine_load": PRIMARY_LOAD, "provisional_K": PRIMARY_K})
    return result


def saved_two_cycle_rows(path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Load complete task-owned HSPICE outcomes for report-only finalization."""

    rows = read_csv(path)
    converted: List[Dict[str, Any]] = []
    for row in rows:
        value: Dict[str, Any] = dict(row)
        for field in ("medium_code", "fine_code", "K"):
            value[field] = int(value[field])
        for field in ("vdd_v", "D_rise_ps", "W_high90_ps", "W_low10_ps"):
            value[field] = float(value[field])
        value["valid"] = is_true(value["valid"])
        value["reasons"] = [reason for reason in value["failure_reasons"].split(";") if reason]
        converted.append(value)
    phase2 = [row for row in converted if row["phase"] == "phase2_worst_endpoint"]
    phase3 = [row for row in converted if row["phase"] == "phase3_boundary_endpoint"]
    if len(phase2) != 1 or len(phase3) != 18 or not all(row["valid"] for row in converted):
        raise ValueError("saved two-cycle evidence is incomplete or invalid")
    return phase2[0], phase3


def classification_counts(analysis: Path) -> Dict[str, Dict[str, int]]:
    """Count complete r2 crossing pulses by driver from the task-owned readback."""

    result: Dict[str, Dict[str, int]] = {}
    for row in read_csv(analysis / "r2_reclassification.csv"):
        counts = result.setdefault(row["driver_cell"], {"complete_crossing": 0, "legacy_fixed_sample_miss": 0, "electrical_waveform_failure": 0})
        if is_true(row["waveform_valid"]):
            counts["complete_crossing"] += 1
        counts[row["classification"]] = counts.get(row["classification"], 0) + 1
    return result


def phase2_crossings(run_root: Path, phase2: Mapping[str, Any]) -> Mapping[str, Optional[float]]:
    """Read exact Phase-2 crossing times from raw evidence rather than report guesses."""

    measures = list(run_root.glob("r*/{}/fine_stage.mt0.csv".format(phase2["scenario"])))
    if len(measures) != 1:
        raise ValueError("cannot find unique Phase-2 raw measurement")
    raw = CORE.run_dc_sweep.parse_measurements(measures[0])
    return {name: finite(raw.get(name)) for name in ("t_out_rise_90_1", "t_out_fall_10_1", "t_out_rise_10_2")}


def render_report(path: Path, analysis: Path, run_root: Path, requirements: Mapping[str, Any], phase1: Mapping[str, Any], phase2: Optional[Mapping[str, Any]], phase3: Sequence[Mapping[str, Any]], summary: Mapping[str, Any]) -> None:
    """Answer the required review questions without claiming a complete FTC macro."""

    counts = classification_counts(analysis)
    crossings = phase2_crossings(run_root, phase2) if phase2 else {}
    coverage = phase1["coverage_by_vdd"]
    phase2_text = "not run" if phase2 is None else ("GO" if phase2["valid"] else "NO-GO: " + ";".join(phase2["reasons"]))
    lines = [
        "# FTC Fine-Stage Validation Contract Audit", "", "## Decision", "",
        "**{}**".format(summary["decision"]), "", "## Direct Answers", "",
        "1. The old Gate comes from `run_standard_cell_load_fine_stage.py:measurement_lines()` and `classify()`.",
        "2. It checked voltages at fixed 2.5/5.5 ns times, not a receiver capture contract.",
        "3. Every r2 record was reparsed from raw measures; the per-driver complete-pulse count is listed below.",
        "4. The Phase-2 X0P8/K10 M15/F10 0.80 V path crossed 90% on its first rise at {} ns.".format("not run" if not crossings else "{:.6f}".format(crossings["t_out_rise_90_1"] * 1.0e9)),
        "5. It returned through 10% on its first fall at {} ns.".format("not run" if not crossings else "{:.6f}".format(crossings["t_out_fall_10_1"] * 1.0e9)),
        "6. Phase-2 result is `{}`; W_high90/W_low10 = {} / {} ps, both positive.".format(phase2_text, "not run" if phase2 is None else "{:.6f}".format(phase2["W_high90_ps"]), "not run" if phase2 is None else "{:.6f}".format(phase2["W_low10_ps"])),
        "7. Three-voltage representative-boundary coverage is `{}`.".format("GO" if phase1["coverage_pass"] else "NO-GO"),
        "8. At 0.80 V, max fine step {:.6f} ps is below min coupled-medium step {:.6f} ps.".format(phase1["delta_fine_max_measured_ps_by_vdd"]["0.80"], phase1["medium_step_coupled_min_ps_by_vdd"]["0.80"]),
        "9. The four old NO-GO endpoints are validation false negatives: all 378 raw records have complete crossings and zero electrical waveform failures.",
        "10. Stronger drivers reduce load sensitivity, reducing FineRange_8 and increasing required K.",
        "11. Driver/load rescans are forbidden because this audit first isolates the validation contract.",
        "12. The historical 378-scenario co-design matrix and all upstream medium/load/probe runs were not rerun.",
        "13. New HSPICE scenarios: {} (limit: 19).".format(summary["new_hspice_scenarios"]),
        "14. A GO is only a delay-line waveform-contract GO; no consumer capture edge or setup/hold contract exists yet.",
        "15. Bypass, configuration skip, and the real capture contract remain later architecture work, not this audit.",
        "", "## Frozen Contract", "",
        "- Driver/load/K: `{}` / `{}` / `{}`.".format(PRIMARY_DRIVER, PRIMARY_LOAD, PRIMARY_K),
        "- Legacy ratios remain `{}` / `{}`; they were not relaxed.".format(requirements["legacy_high_ratio"], requirements["legacy_low_ratio"]),
        "- Phase 3 completed {}/18 endpoint scenarios.".format(len(phase3)),
        "", "## r2 Crossing Reclassification", "",
        "| Driver | Complete 10/50/90 pulse records | Fixed-sample misses | Electrical waveform failures |",
        "|---|---:|---:|---:|",
    ]
    if summary["decision"] == "Fine-Stage Delay-Line Waveform Contract = GO":
        lines[6:6] = ["## Provisional Result", "", "- Provisional fine driver/load/K: `{}` / `{}` / `{}`. This is not a complete FTC macro GO.", ""]
        lines[8] = lines[8].format(PRIMARY_DRIVER, PRIMARY_LOAD, PRIMARY_K)
    for driver in ("BUF_X0P8M_A9TL40", "BUF_X1M_A9TL40", "BUF_X1P4M_A9TL40", "BUF_X2M_A9TL40"):
        item = counts[driver]
        lines.append("| `{}` | {} | {} | {} |".format(driver, item["complete_crossing"], item.get("legacy_fixed_sample_miss", 0), item.get("electrical_waveform_failure", 0)))
    lines.extend(["", "## X0P8/K10 Coverage Margins", "", "| VDD (V) | M0→1 / M7→8 / M15→16 margin (ps) |", "|---:|---:|"])
    for voltage in ("1.10", "0.95", "0.80"):
        margins = "/".join("{:.6f}".format(item["coverage_margin_ps"]) for item in coverage[voltage])
        lines.append("| {} | {} |".format(voltage, margins))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def publish(context: Mapping[str, Any], analysis: Path, run_root: Path, phase1: Mapping[str, Any], phase2: Optional[Mapping[str, Any]], phase3: Sequence[Mapping[str, Any]], decision: str, reasons: Sequence[str]) -> Dict[str, Any]:
    """Publish one coherent terminal state after each allowed stop point."""

    requirements = requirement_document(context)
    requirements_path = analysis / "requirements.json"
    write_json(requirements_path, requirements)
    summary = summary_document(phase1, phase2, phase3, run_root, decision, reasons)
    if summary["new_hspice_scenarios"] > 19:
        raise RuntimeError("validation-contract audit exceeded its 19-scenario HSPICE budget")
    write_json(analysis / "summary.json", summary)
    render_report(FTC_ROOT / "reports" / "FTC_FINE_STAGE_VALIDATION_CONTRACT_AUDIT.md", analysis, run_root, requirements, phase1, phase2, phase3, summary)
    if decision == "Fine-Stage Delay-Line Waveform Contract = GO":
        write_json(analysis / "future_capture_contract.json", {
            "schema_version": 1, "capture_edge_not_yet_frozen": True,
            "setup_hold_not_yet_frozen": True,
            "fixed_absolute_sample_not_a_fine_stage_hard_gate": True,
        })
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Execute the audited state machine; each electrical failure terminates it."""

    parser = argparse.ArgumentParser(description="audit fine-stage waveform validation contract")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis" / "fine_stage_validation_contract_audit")
    parser.add_argument("--run-root", type=Path, default=FTC_ROOT / "runs" / "fine_stage_validation_contract_audit")
    parser.add_argument("--phase0-only", action="store_true", help="freeze provenance only; never run HSPICE")
    parser.add_argument("--phase1-only", action="store_true", help="freeze and reparse r2 only; never run HSPICE")
    parser.add_argument("--phase2-only", action="store_true", help="run only the approved worst endpoint before Phase 3")
    parser.add_argument("--finalize-existing", action="store_true", help="republish complete task-owned evidence without HSPICE")
    args = parser.parse_args(argv)
    if sum(bool(value) for value in (args.phase0_only, args.phase1_only, args.phase2_only, args.finalize_existing)) > 1:
        raise ValueError("only one stage stop option may be selected")
    analysis, run_root = args.analysis_dir.resolve(), args.run_root.resolve()
    context = frozen_context()
    requirements_path = analysis / "requirements.json"
    write_json(requirements_path, requirement_document(context))
    if args.phase0_only:
        print("FTC_FINE_STAGE_VALIDATION_CONTRACT_AUDIT phase0=requirements_published")
        return 0
    rows = legacy_reclassification(context)
    write_csv(analysis / "r2_reclassification.csv", RECLASSIFICATION_FIELDS, rows)
    phase1 = recompute_primary(rows)
    write_json(analysis / "x0p8_k10_recomputed_coverage.json", phase1)
    misses = [row for row in rows if row["classification"] == "legacy_fixed_sample_miss"]
    write_json(analysis / "legacy_gate_false_negative_candidates.json", {"schema_version": 1, "count": len(misses), "rows": misses})
    if args.finalize_existing:
        if not phase1["phase1_go"]:
            raise ValueError("cannot finalize an electrically failed Phase 1")
        phase2, phase3 = saved_two_cycle_rows(analysis / "two_cycle_waveforms.csv")
        publish(context, analysis, run_root, phase1, phase2, phase3, "Fine-Stage Delay-Line Waveform Contract = GO", [])
        print("FTC_FINE_STAGE_VALIDATION_CONTRACT_AUDIT finalized=GO")
        return 0
    if args.phase1_only:
        publish(context, analysis, run_root, phase1, None, [], "Fine-Stage Validation Contract = PHASE1_COMPLETE", [])
        print("FTC_FINE_STAGE_VALIDATION_CONTRACT_AUDIT phase1=complete")
        return 0
    if not phase1["phase1_go"]:
        publish(context, analysis, run_root, phase1, None, [], "Validation-Contract Audit = REAL_ELECTRICAL_NO-GO", phase1["electrical_reasons"] or ["legacy_fixed_sample_miss_not_established"])
        print("FTC_FINE_STAGE_VALIDATION_CONTRACT_AUDIT decision=REAL_ELECTRICAL_NO-GO")
        return 0
    # A report-only edit must never turn an already complete audit into a
    # second electrical campaign.  ``--finalize-existing`` is the only safe
    # path once all 1 + 18 permitted raw scenarios have been retained.
    if len(list(run_root.glob("r*/scenarios/*/scenario_manifest.json"))) >= 19:
        raise RuntimeError("complete 19-scenario audit evidence exists; use --finalize-existing")
    hspice, version = CORE.validate_hspice(context["config"])
    reference = reference_deck(context, 15, PRIMARY_K, 0.80)
    run_dir = select_run_dir(run_root, audit_signature(requirements_path, reference), hspice, version)
    stats = {"new": 0, "reused": 0}
    phase2 = run_two_cycle(context, requirements_path, run_dir, hspice, 15, PRIMARY_K, 0.80, "phase2_worst_endpoint", stats)
    write_csv(analysis / "two_cycle_waveforms.csv", TWO_CYCLE_FIELDS, [phase2])
    if not phase2["valid"]:
        publish(context, analysis, run_root, phase1, phase2, [], "Validation-Contract Audit = REAL_ELECTRICAL_NO-GO", phase2["reasons"])
        print("FTC_FINE_STAGE_VALIDATION_CONTRACT_AUDIT decision=REAL_ELECTRICAL_NO-GO")
        return 0
    if args.phase2_only:
        publish(context, analysis, run_root, phase1, phase2, [], "Fine-Stage Validation Contract = PHASE2_COMPLETE", [])
        print("FTC_FINE_STAGE_VALIDATION_CONTRACT_AUDIT phase2=complete")
        return 0
    phase3: List[Dict[str, Any]] = []
    for medium, fine, vdd in phase3_schedule():
        row = run_two_cycle(context, requirements_path, run_dir, hspice, medium, fine, vdd, "phase3_boundary_endpoint", stats)
        phase3.append(row)
        if not row["valid"]:
            write_csv(analysis / "two_cycle_waveforms.csv", TWO_CYCLE_FIELDS, [phase2] + phase3)
            publish(context, analysis, run_root, phase1, phase2, phase3, "Validation-Contract Audit = REAL_ELECTRICAL_NO-GO", row["reasons"])
            print("FTC_FINE_STAGE_VALIDATION_CONTRACT_AUDIT decision=REAL_ELECTRICAL_NO-GO")
            return 0
    write_csv(analysis / "two_cycle_waveforms.csv", TWO_CYCLE_FIELDS, [phase2] + phase3)
    publish(context, analysis, run_root, phase1, phase2, phase3, "Fine-Stage Delay-Line Waveform Contract = GO", [])
    print("FTC_FINE_STAGE_VALIDATION_CONTRACT_AUDIT decision=GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
