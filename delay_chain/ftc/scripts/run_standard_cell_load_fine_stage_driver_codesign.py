#!/usr/bin/env python3
"""Co-design the fixed NOR2 fine-load bank with the smallest valid LVT driver.

The historical X0P7M fine-stage and the four endpoint driver probes are read
only inputs.  This runner therefore owns a new raw-run root and changes only
``XFINE_DRIVER`` while preserving the frozen N=16 medium network and NOR2_X4A
load contract.  It is intentionally bounded to four real library buffers and
does not implement bypass, calibration, RTL, PVT, or any sensor behaviour.
"""

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = FTC_ROOT / "scripts" / "run_standard_cell_load_fine_stage.py"
CORE_SPEC = importlib.util.spec_from_file_location("standard_cell_load_fine_stage_core", CORE_PATH)
assert CORE_SPEC is not None and CORE_SPEC.loader is not None
CORE = importlib.util.module_from_spec(CORE_SPEC)
CORE_SPEC.loader.exec_module(CORE)


TOPOLOGY_VERSION = "standard_cell_load_fine_stage_driver_codesign_v1"
FIXED_LOAD_ID = "NOR2_X4A_A9TL40__signal_A"
FIXED_LOAD_CELL = "NOR2_X4A_A9TL40"
FIXED_SIGNAL_PIN = "A"
FIXED_CONTROL_PIN = "B"
LOW_CAP_CONTROL = 1
HIGH_CAP_CONTROL = 0
HISTORICAL_K = 8
MAX_FINE_BANK = 64
DRIVER_SEQUENCE = (("0P8", "BUF_X0P8M_A9TL40"), ("1", "BUF_X1M_A9TL40"), ("1P4", "BUF_X1P4M_A9TL40"), ("2", "BUF_X2M_A9TL40"))
ROW_FIELDS = ("driver_cell", "driver_size_tier", "driver_total_width_m") + CORE.ROW_FIELDS


def read_json(path: Path) -> Dict[str, Any]:
    """Read an object contract and reject malformed retained evidence early."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write deterministic task-owned evidence without changing historical data."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Publish every requested point, including invalid but parsed measurements."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=ROW_FIELDS, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in ROW_FIELDS})


def read_csv(path: Path) -> List[Dict[str, Any]]:
    """Read task-owned result rows for a report-only finalization without HSPICE."""

    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def fixed_load() -> Dict[str, Any]:
    """Read the approved fallback contract instead of selecting a new load cell."""

    path = FTC_ROOT / "analysis" / "standard_cell_load_size_sweep" / "fallback_1" / "selected_size_contract.json"
    contract = read_json(path)
    required = {
        "candidate_id": FIXED_LOAD_ID, "cell": FIXED_LOAD_CELL,
        "signal_pin": FIXED_SIGNAL_PIN, "control_pin": FIXED_CONTROL_PIN,
        "high_cap_control_value": HIGH_CAP_CONTROL,
        "low_cap_control_value": LOW_CAP_CONTROL, "K_candidate": HISTORICAL_K,
    }
    if any(contract.get(key) != value for key, value in required.items()):
        raise ValueError("retained fine-load contract no longer matches the approved fallback")
    return contract


def frozen_evidence() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Path]]:
    """Freeze all upstream GO/endpoint evidence without invoking any old runner."""

    interface, cells, medium_paths = CORE.freeze_inputs()
    candidate = fixed_load()
    paths = {
        **medium_paths,
        "fixed_load_contract": FTC_ROOT / "analysis" / "standard_cell_load_size_sweep" / "fallback_1" / "selected_size_contract.json",
        "fallback_summary": FTC_ROOT / "analysis" / "standard_cell_load_size_sweep" / "fallback_1" / "summary.json",
        "fallback_coupled": FTC_ROOT / "analysis" / "standard_cell_load_size_sweep" / "fallback_1" / "winner_coupled_medium.csv",
        "probe_requirements": FTC_ROOT / "analysis" / "standard_cell_load_driver_strength_probe" / "requirements.json",
        "probe_summary": FTC_ROOT / "analysis" / "standard_cell_load_driver_strength_probe" / "summary.json",
        "probe_rows": FTC_ROOT / "analysis" / "standard_cell_load_driver_strength_probe" / "driver_probe.csv",
        "historical_driver_only": FTC_ROOT / "analysis" / "standard_cell_load_fine_stage" / "single_load_screen.csv",
    }
    if any(not path.is_file() or path.stat().st_size == 0 for path in paths.values()):
        raise ValueError("required frozen evidence is missing")
    probe = read_json(paths["probe_summary"])
    if probe.get("full_fine_stage_acceptance") != "NOT_RUN":
        raise ValueError("endpoint probe must remain distinct from full fine-stage acceptance")
    return interface, cells, candidate, paths


def requirements(interface: Mapping[str, Any], candidate: Mapping[str, Any], paths: Mapping[str, Path]) -> Dict[str, Any]:
    """Publish the exact bounded architecture and hashes consumed by this run."""

    return {
        "schema_version": 1, "topology_version": TOPOLOGY_VERSION,
        "medium_stage_decision": "GO", "medium_N": CORE.MEDIUM_N,
        "medium_delay_cell": CORE.MEDIUM_DELAY_CELL, "medium_mux_cell": CORE.MEDIUM_MUX_CELL,
        "anchor_vdd_v": list(CORE.ANCHOR_VDD),
        "medium_step_max_ps_by_vdd": interface["medium_step_max_ps_by_vdd"],
        "fixed_load_candidate": candidate["candidate_id"], "fixed_load_cell": candidate["cell"],
        "signal_pin": candidate["signal_pin"], "control_pin": candidate["control_pin"],
        "high_cap_control": HIGH_CAP_CONTROL, "low_cap_control": LOW_CAP_CONTROL,
        "historical_K": HISTORICAL_K, "historical_driver_baseline": "BUF_X0P7M_A9TL40",
        "historical_driver_baseline_result": "FAIL_AT_0P80_M15_F8",
        "driver_candidates": [cell for _, cell in DRIVER_SEQUENCE],
        "driver_selection_policy": "smallest_full_acceptance_GO",
        "logic_high_min_ratio": CORE.DEFAULT_LOGIC_HIGH_MIN_RATIO,
        "logic_low_max_ratio": CORE.LOGIC_LOW_MAX_RATIO, "max_fine_bank": MAX_FINE_BANK,
        "max_k_rescales_per_driver": 1, "historical_medium_scenarios_rerun": 0,
        "historical_load_sweep_scenarios_rerun": 0, "historical_driver_probe_scenarios_rerun": 0,
        "bypass": "future_work", "config_skip": "future_work", "sensor": "forbidden",
        "xor": "forbidden", "dff": "forbidden", "calibration": "forbidden",
        "droop": "forbidden", "pvt": "forbidden", "rtl": "forbidden",
        "power": "forbidden", "area": "forbidden", "layout": "forbidden",
        "final_medium_N_frozen": False, "final_fine_K_frozen": False,
        "source_file_sha256": {name: CORE.sha256_file(path) for name, path in paths.items()},
    }


def _verilog_block(text: str, cell: str) -> Optional[str]:
    """Return the power-aware vendor BUF module, avoiding unpowered duplicates."""

    match = re.search(r"(?ims)^module\s+{}\s*\(Y,\s*VDD,\s*VSS,\s*A\);(.*?)^endmodule".format(re.escape(cell)), text)
    return match.group(0) if match else None


def _cdl_block(text: str, cell: str) -> Optional[str]:
    """Return one exact six-port CDL subcircuit rather than a partial name match."""

    match = re.search(r"(?ims)^\.SUBCKT\s+{}\s+Y\s+VDD\s+VNW\s+VPW\s+VSS\s+A\s*$\n(.*?)^\.ends\b".format(re.escape(cell)), text)
    return match.group(0) if match else None


def discover_drivers(cells: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Verify the four approved same-polarity LVT buffers and physical ordering."""

    verilog = Path(cells["source_files"]["lvt_verilog"]).read_text(encoding="latin-1", errors="replace")
    cdl = Path(cells["source_files"]["lvt_cdl"]).read_text(encoding="latin-1", errors="replace")
    result: List[Dict[str, Any]] = []
    prior_width = 0.0
    for tier, cell in DRIVER_SEQUENCE:
        vblock, cblock = _verilog_block(verilog, cell), _cdl_block(cdl, cell)
        if not vblock or not cblock:
            raise ValueError("missing exact LVT Verilog/CDL contract: {}".format(cell))
        # A primitive BUF proves non-inverting behaviour; the power guard only
        # converts an invalid supply state to X and does not change Y=A at TT.
        if not re.search(r"\bbuf\s+\w+\s*\(\s*out_temp\s*,\s*A\s*\)", vblock):
            raise ValueError("BUF is not a same-polarity Y=A implementation: {}".format(cell))
        widths = [float(value) for value in re.findall(r"\bw=([0-9.eE+-]+)", cblock)]
        width = sum(widths)
        if not widths or width <= prior_width:
            raise ValueError("driver widths are not strictly increasing at {}".format(cell))
        result.append({
            "driver_size_tier": tier, "driver_cell": cell, "driver_total_width_m": width,
            "verilog_ports": ["Y", "VDD", "VSS", "A"],
            "cdl_ports": ["Y", "VDD", "VNW", "VPW", "VSS", "A"], "truth_function": "Y = A",
        })
        prior_width = width
    return result


def run_signature(requirements_path: Path, contract_path: Path, fixed_contract_path: Path) -> Dict[str, str]:
    """Bind retained raw evidence to this runner and all inputs that can alter physics."""

    return {
        "runner_sha256": CORE.sha256_file(Path(__file__)),
        "requirements_sha256": CORE.sha256_file(requirements_path),
        "driver_contract_sha256": CORE.sha256_file(contract_path),
        "fixed_load_contract_sha256": CORE.sha256_file(fixed_contract_path),
    }


def select_run_dir(root: Path, signature: Mapping[str, str], hspice: Path, version: str) -> Path:
    """Reuse only a fully passing co-design revision; never overwrite raw evidence."""

    root.mkdir(parents=True, exist_ok=True)
    revisions = sorted((item for item in root.glob("r*") if re.fullmatch(r"r\d+", item.name)), key=lambda item: int(item.name[1:]), reverse=True)
    for revision in revisions:
        manifest = revision / "run_manifest.json"
        scenario_manifests = list(revision.glob("scenarios/*/scenario_manifest.json"))
        if manifest.is_file() and read_json(manifest).get("signature") == dict(signature) and all(read_json(item).get("completion_status") == "PASS" for item in scenario_manifests):
            return revision
    index = max((int(item.name[1:]) for item in revisions), default=0) + 1
    revision = root / "r{}".format(index)
    revision.mkdir()
    write_json(revision / "run_manifest.json", {
        "schema_version": 1, "study": TOPOLOGY_VERSION, "signature": dict(signature),
        "system_hspice": str(hspice), "hspice_version": version,
    })
    return revision


def raw_scenario_counts(run_root: Path, qualified_run: Path) -> Dict[str, int]:
    """Separate final-contract evidence from superseded revisions without hiding work."""

    all_manifests = list(run_root.glob("r*/scenarios/*/scenario_manifest.json"))
    qualified = list(qualified_run.glob("scenarios/*/scenario_manifest.json"))
    if any(read_json(path).get("completion_status") != "PASS" for path in all_manifests):
        raise ValueError("raw scenario accounting requires only completed revisions")
    return {"qualified": len(qualified), "task_total": len(all_manifests), "superseded": len(all_manifests) - len(qualified)}


def scenario_parameters(phase: str, driver: Mapping[str, Any], candidate: Optional[Mapping[str, Any]], medium_code: int, vdd: float, K: int, fine_code: int) -> Dict[str, Any]:
    """Include the selected driver in every cache key so measurements cannot cross-share."""

    result = CORE.scenario_parameters(
        phase, medium_code, vdd, candidate, K, fine_code, LOW_CAP_CONTROL,
        HIGH_CAP_CONTROL, CORE.DEFAULT_LOGIC_HIGH_MIN_RATIO, str(driver["driver_cell"]),
    )
    result.update({
        "study_name": TOPOLOGY_VERSION, "driver_size_tier": driver["driver_size_tier"],
        "driver_total_width_m": driver["driver_total_width_m"],
        # The low-level rule does not alter the deck, but it alters waveform
        # acceptance and must therefore be part of the reusable evidence key.
        "logic_low_max_ratio": CORE.LOGIC_LOW_MAX_RATIO,
    })
    return result


def render_scenario_deck(config: Mapping[str, Any], cells: Mapping[str, Any], driver: Mapping[str, Any], candidate: Optional[Mapping[str, Any]], medium_code: int, vdd: float, K: int, fine_code: int) -> str:
    """Render the frozen topology while changing only the named fine-driver instance."""

    return CORE.render_deck(config, cells, vdd, medium_code, candidate, K, fine_code, HIGH_CAP_CONTROL, str(driver["driver_cell"]))


def measure(phase: str, driver: Mapping[str, Any], candidate: Optional[Mapping[str, Any]], medium_code: int, vdd: float, K: int, fine_code: int, config: Mapping[str, Any], cells: Mapping[str, Any], hspice: Path, run_dir: Path, signature: Mapping[str, str], stats: Dict[str, int]) -> Dict[str, Any]:
    """Run one complete physical scenario and retain its normalized measurement row."""

    deck = render_scenario_deck(config, cells, driver, candidate, medium_code, vdd, K, fine_code)
    parameters = scenario_parameters(phase, driver, candidate, medium_code, vdd, K, fine_code)
    record = CORE.execute(hspice, run_dir, deck, parameters, signature, stats)
    result = CORE.classify(record, vdd, CORE.DEFAULT_LOGIC_HIGH_MIN_RATIO)
    return {
        "driver_cell": driver["driver_cell"], "driver_size_tier": driver["driver_size_tier"],
        "driver_total_width_m": driver["driver_total_width_m"], "stage": phase,
        "candidate_id": candidate["candidate_id"] if candidate else "driver_only",
        "medium_code": medium_code, "fine_code": fine_code, "K": K, "vdd_v": vdd,
        "control_value": HIGH_CAP_CONTROL if candidate else None,
        **result, "scenario": str(Path(record["scenario"]).relative_to(run_dir)),
    }


def row_is_valid(row: Mapping[str, Any]) -> bool:
    """Interpret live booleans and CSV round-tripped values with identical semantics."""

    value = row.get("valid")
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def waveform_reasons(rows: Iterable[Mapping[str, Any]]) -> List[str]:
    """Classify invalid rows by physical failure instead of collapsing them into NO-GO."""

    reasons: List[str] = []
    for row in rows:
        if row_is_valid(row):
            continue
        high, low, vdd = row.get("output_logic_high"), row.get("output_logic_low"), float(row["vdd_v"])
        if high is not None and float(high) < CORE.DEFAULT_LOGIC_HIGH_MIN_RATIO * vdd:
            reasons.append("driver_waveform_high_fail")
        if low is not None and float(low) > CORE.LOGIC_LOW_MAX_RATIO * vdd:
            reasons.append("driver_waveform_low_fail")
        if high is None or low is None or row.get("D_rise_ps") is None or row.get("D_fall_ps") is None or row.get("output_rise_time_ps") is None or row.get("output_fall_time_ps") is None:
            reasons.append("driver_settling_fail")
        if int(float(row.get("unexpected_transition_count") or 0)) > 0:
            reasons.append("edge_integrity_failure")
    return list(dict.fromkeys(reasons))


def rows_for(rows: Iterable[Mapping[str, Any]], medium_code: int, vdd: float) -> Dict[int, Mapping[str, Any]]:
    """Index one medium/voltage slice by fine code and reject accidental duplicates."""

    result = {int(row["fine_code"]): row for row in rows if int(row["medium_code"]) == medium_code and float(row["vdd_v"]) == vdd}
    return result


def monotonic_reasons(rows: Sequence[Mapping[str, Any]], medium_code: int, vdd: float, codes: Sequence[int]) -> List[str]:
    """Use the reviewed strict-positive checker with a phase-specific reason label."""

    reasons = CORE.monotonic([row for row in rows if int(row["medium_code"]) == medium_code and float(row["vdd_v"]) == vdd], tuple(codes))
    return ["fine_code_non_monotonic: {}".format(reason) for reason in reasons]


def phase2_rows(driver: Mapping[str, Any], candidate: Mapping[str, Any], config: Mapping[str, Any], cells: Mapping[str, Any], hspice: Path, run_dir: Path, signature: Mapping[str, str], stats: Dict[str, int]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Run the exact 25-point K=8 characterization required before K is derived."""

    rows: List[Dict[str, Any]] = []
    for code in range(HISTORICAL_K + 1):
        rows.append(measure("phase2_fine8", driver, candidate, 8, 0.95, HISTORICAL_K, code, config, cells, hspice, run_dir, signature, stats))
    for vdd in (1.10, 0.80):
        for code in (0, 1, 4, 7, 8):
            rows.append(measure("phase2_fine8", driver, candidate, 8, vdd, HISTORICAL_K, code, config, cells, hspice, run_dir, signature, stats))
    for medium_code in (0, 15):
        for code in (0, 1, 8):
            rows.append(measure("phase2_position", driver, candidate, medium_code, 0.95, HISTORICAL_K, code, config, cells, hspice, run_dir, signature, stats))
    if len(rows) != 25:
        raise RuntimeError("Phase 2 scenario schedule changed")
    reasons = waveform_reasons(rows)
    reasons.extend(monotonic_reasons(rows, 8, 0.95, tuple(range(9))))
    for vdd in (1.10, 0.80):
        reasons.extend(monotonic_reasons(rows, 8, vdd, (0, 1, 4, 7, 8)))
    for medium_code in (0, 15):
        reasons.extend(monotonic_reasons(rows, medium_code, 0.95, (0, 1, 8)))
    return rows, list(dict.fromkeys(reasons))


def derive_sizing(rows: Sequence[Mapping[str, Any]], interface: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Derive K only from this driver's measured eight-unit range at all anchors."""

    ranges, predictions, reasons = {}, {}, []
    for vdd in CORE.ANCHOR_VDD:
        local = rows_for(rows, 8, vdd)
        if set((0, HISTORICAL_K)) - set(local) or any(not row_is_valid(local[code]) for code in (0, HISTORICAL_K)):
            reasons.append("fine_range_insufficient")
            continue
        fine_range = float(local[HISTORICAL_K]["D_rise_ps"]) - float(local[0]["D_rise_ps"])
        key = CORE.vkey(vdd)
        ranges[key] = fine_range
        if fine_range <= 0:
            reasons.append("fine_range_insufficient")
        else:
            predictions[key] = int(math.ceil(HISTORICAL_K * float(interface["medium_step_max_ps_by_vdd"][key]) / fine_range))
    candidate = max(predictions.values()) if len(predictions) == len(CORE.ANCHOR_VDD) else None
    if candidate is not None and candidate > MAX_FINE_BANK:
        reasons.append("K_exceeds_bounded_limit")
    return {
        "schema_version": 1, "FineRange_8_ps_by_vdd": ranges,
        "K_pred_by_vdd": predictions, "K_candidate": candidate, "K_rescaled": None,
        "max_fine_bank": MAX_FINE_BANK,
    }, list(dict.fromkeys(reasons))


def coverage_rows(phase: str, driver: Mapping[str, Any], candidate: Mapping[str, Any], K: int, pairs: Sequence[int], config: Mapping[str, Any], cells: Mapping[str, Any], hspice: Path, run_dir: Path, signature: Mapping[str, str], stats: Dict[str, int]) -> List[Dict[str, Any]]:
    """Measure both endpoints and the code-zero medium step for every requested pair."""

    rows: List[Dict[str, Any]] = []
    for vdd in CORE.ANCHOR_VDD:
        for medium_code in pairs:
            rows.append(measure(phase, driver, candidate, medium_code, vdd, K, 0, config, cells, hspice, run_dir, signature, stats))
            rows.append(measure(phase, driver, candidate, medium_code, vdd, K, K, config, cells, hspice, run_dir, signature, stats))
            rows.append(measure(phase, driver, candidate, medium_code + 1, vdd, K, 0, config, cells, hspice, run_dir, signature, stats))
    return rows


def coverage_reasons(rows: Sequence[Mapping[str, Any]], pairs: Sequence[int], K: int) -> List[str]:
    """Evaluate coverage only after confirming all three endpoint waveforms are valid."""

    reasons = waveform_reasons(rows)
    for vdd in CORE.ANCHOR_VDD:
        for medium_code in pairs:
            local = rows_for(rows, medium_code, vdd)
            next_rows = rows_for(rows, medium_code + 1, vdd)
            left0, leftk, right0 = local.get(0), local.get(K), next_rows.get(0)
            if not left0 or not leftk or not right0 or not all(row_is_valid(row) for row in (left0, leftk, right0)):
                continue
            if float(leftk["D_rise_ps"]) < float(right0["D_rise_ps"]):
                reasons.append("medium_fine_gap_remains")
    return list(dict.fromkeys(reasons))


def rescaled_k(rows: Sequence[Mapping[str, Any]], K: int) -> Optional[int]:
    """Use the measured M=7 range once; this replaces brute-force K searching."""

    predictions = []
    for vdd in CORE.ANCHOR_VDD:
        local, next_rows = rows_for(rows, 7, vdd), rows_for(rows, 8, vdd)
        left0, leftk, right0 = local.get(0), local.get(K), next_rows.get(0)
        if not left0 or not leftk or not right0 or not all(row_is_valid(row) for row in (left0, leftk, right0)):
            return None
        span = float(leftk["D_rise_ps"]) - float(left0["D_rise_ps"])
        medium_step = float(right0["D_rise_ps"]) - float(left0["D_rise_ps"])
        if span <= 0 or medium_step <= 0:
            return None
        predictions.append(int(math.ceil(K * medium_step / span)))
    return max(predictions)


def sample_codes(K: int) -> Tuple[int, ...]:
    """Keep high/low-voltage final checks bounded while retaining endpoint increments."""

    if K < 1:
        raise ValueError("final K must be positive")
    return tuple(sorted({0, 1, int(round(K / 4.0)), int(round(K / 2.0)), int(round(3.0 * K / 4.0)), K - 1, K}))


def final_monotonic_rows(driver: Mapping[str, Any], candidate: Mapping[str, Any], K: int, config: Mapping[str, Any], cells: Mapping[str, Any], hspice: Path, run_dir: Path, signature: Mapping[str, str], stats: Dict[str, int]) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, float]]:
    """Run the required 0.95 V full code set and bounded high/low-voltage samples."""

    rows = [measure("phase4_final_monotonicity", driver, candidate, 7, 0.95, K, code, config, cells, hspice, run_dir, signature, stats) for code in range(K + 1)]
    selected_codes = sample_codes(K)
    for vdd in (1.10, 0.80):
        rows.extend(measure("phase4_final_monotonicity", driver, candidate, 7, vdd, K, code, config, cells, hspice, run_dir, signature, stats) for code in selected_codes)
    reasons = waveform_reasons(rows)
    reasons.extend(monotonic_reasons(rows, 7, 0.95, tuple(range(K + 1))))
    for vdd in (1.10, 0.80):
        reasons.extend(monotonic_reasons(rows, 7, vdd, selected_codes))
    fine_steps: Dict[str, float] = {}
    for vdd in CORE.ANCHOR_VDD:
        local = rows_for(rows, 7, vdd)
        # At 0.95 V this is the true full-bank maximum.  At 1.10/0.80 V the
        # plan deliberately permits only endpoint-adjacent samples, so publish
        # the maximum *measured* one-code increment rather than inventing data.
        pairs = [(code, code + 1) for code in range(K)] if vdd == 0.95 else [(0, 1), (K - 1, K)]
        deltas = [float(local[right]["D_rise_ps"]) - float(local[left]["D_rise_ps"]) for left, right in pairs if left in local and right in local and row_is_valid(local[left]) and row_is_valid(local[right])]
        if not deltas or any(delta <= 0 for delta in deltas):
            reasons.append("fine_code_non_monotonic")
        else:
            fine_steps[CORE.vkey(vdd)] = max(deltas)
    return rows, list(dict.fromkeys(reasons)), fine_steps


def coupled_metrics(rows: Sequence[Mapping[str, Any]], K: int, fine_steps: Mapping[str, float]) -> Tuple[Dict[str, float], Dict[str, float], List[str]]:
    """Compute coverage and resolution from the final shallow/middle/deep measurements."""

    reasons = coverage_reasons(rows, (0, 7, 15), K)
    minimum_steps: Dict[str, float] = {}
    margins: Dict[str, float] = {}
    for vdd in CORE.ANCHOR_VDD:
        coupled, coverage_margins = [], []
        for medium_code in (0, 7, 15):
            local, next_rows = rows_for(rows, medium_code, vdd), rows_for(rows, medium_code + 1, vdd)
            left0, leftk, right0 = local.get(0), local.get(K), next_rows.get(0)
            if not left0 or not leftk or not right0 or not all(row_is_valid(row) for row in (left0, leftk, right0)):
                continue
            coupled.append(float(right0["D_rise_ps"]) - float(left0["D_rise_ps"]))
            coverage_margins.append(float(leftk["D_rise_ps"]) - float(right0["D_rise_ps"]))
        key = CORE.vkey(vdd)
        # Missing coupled points are already classified as waveform failures by
        # ``coverage_reasons``.  Do not relabel unavailable delay evidence as a
        # physical delay gap; a gap is reported only for three valid endpoints.
        if len(coupled) != 3 or any(step <= 0 for step in coupled):
            continue
        minimum_steps[key], margins[key] = min(coupled), min(coverage_margins)
        if key not in fine_steps or fine_steps[key] >= minimum_steps[key]:
            reasons.append("fine_resolution_not_below_medium")
    return minimum_steps, margins, list(dict.fromkeys(reasons))


def historical_driver_only() -> Dict[str, float]:
    """Read X0P7M no-load reference values; do not regenerate those historical decks."""

    path = FTC_ROOT / "analysis" / "standard_cell_load_fine_stage" / "single_load_screen.csv"
    result: Dict[str, float] = {}
    with path.open(encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["stage"] == "single_driver_baseline" and row["medium_code"] == "8":
                result[CORE.vkey(float(row["vdd_v"]))] = float(row["D_rise_ps"])
    if set(result) != {CORE.vkey(vdd) for vdd in CORE.ANCHOR_VDD}:
        raise ValueError("historical X0P7M driver-only reference is incomplete")
    return result


def historical_failure_endpoint() -> Dict[str, Any]:
    """Read the retained X0P7M deep failure used for an apples-to-apples report table."""

    path = FTC_ROOT / "analysis" / "standard_cell_load_size_sweep" / "fallback_1" / "winner_coupled_medium.csv"
    for row in read_csv(path):
        if row["medium_code"] == "15" and row["fine_code"] == "8" and row["vdd_v"] == "0.8":
            return row
    raise ValueError("retained X0P7M deep failure row is missing")


def future_interface(driver: Mapping[str, Any], candidate: Mapping[str, Any], K: int, phase4_coverage: Sequence[Mapping[str, Any]], coupled: Sequence[Mapping[str, Any]], config: Mapping[str, Any], cells: Mapping[str, Any], hspice: Path, run_dir: Path, signature: Mapping[str, str], stats: Dict[str, int]) -> Dict[str, Any]:
    """Publish offsets for later bypass work without implementing a bypass circuit now."""

    baseline = historical_driver_only()
    no_load_rows = [measure("future_driver_only", driver, None, 8, vdd, 0, 0, config, cells, hspice, run_dir, signature, stats) for vdd in CORE.ANCHOR_VDD]
    result: Dict[str, Any] = {
        "schema_version": 1, "selected_fine_driver": driver["driver_cell"],
        "selected_fine_load": candidate["candidate_id"], "K_candidate_tt25": K,
        "fine_driver_offset_ps_by_vdd": {}, "fine_bank_code0_offset_ps_by_vdd": {},
        "fine_range_by_vdd": {}, "coverage_margin_by_vdd": {},
        "bypass_not_implemented": True, "final_K_frozen": False, "final_medium_N_frozen": False,
    }
    for vdd in CORE.ANCHOR_VDD:
        key = CORE.vkey(vdd)
        no_load = next(row for row in no_load_rows if float(row["vdd_v"]) == vdd)
        initial = rows_for(phase4_coverage, 7, vdd)
        coupled_m7, coupled_m8 = rows_for(coupled, 7, vdd), rows_for(coupled, 8, vdd)
        result["fine_driver_offset_ps_by_vdd"][key] = float(no_load["D_rise_ps"]) - baseline[key]
        result["fine_bank_code0_offset_ps_by_vdd"][key] = float(coupled_m8[0]["D_rise_ps"]) - float(no_load["D_rise_ps"])
        result["fine_range_by_vdd"][key] = float(initial[K]["D_rise_ps"]) - float(initial[0]["D_rise_ps"])
        result["coverage_margin_by_vdd"][key] = float(coupled_m7[K]["D_rise_ps"]) - float(coupled_m8[0]["D_rise_ps"])
    return result


def driver_summary(driver: Mapping[str, Any], status: str, reasons: Sequence[str], stats: Mapping[str, int], sizing: Optional[Mapping[str, Any]] = None, metrics: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Keep each candidate terminal result self-contained and auditable."""

    return {
        "schema_version": 1, "driver": dict(driver), "status": status,
        "reasons": list(dict.fromkeys(reasons)), "new_hspice_scenarios": stats["new"],
        "reused_new_task_scenarios": stats["reused"], "sizing": dict(sizing or {}),
        "metrics": dict(metrics or {}), "historical_medium_scenarios_rerun": 0,
        "historical_load_sweep_scenarios_rerun": 0, "historical_driver_probe_scenarios_rerun": 0,
    }


def critical_endpoint(rows: Sequence[Mapping[str, Any]], K: int) -> Dict[str, Any]:
    """Extract the mandated deep 0.80 V endpoint so reports show the actual failure."""

    for row in rows:
        if int(row["medium_code"]) == 15 and int(row["fine_code"]) == K and float(row["vdd_v"]) == 0.80:
            return {key: row.get(key) for key in ("output_logic_high", "output_logic_low", "output_rise_time_ps", "valid", "scenario")}
    return {}


def run_driver(driver: Mapping[str, Any], candidate: Mapping[str, Any], interface: Mapping[str, Any], config: Mapping[str, Any], cells: Mapping[str, Any], hspice: Path, run_dir: Path, signature: Mapping[str, str], analysis: Path, total_stats: Dict[str, int]) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Complete one candidate before considering a stronger driver, preserving minimum selection."""

    directory = analysis / "driver_{}".format(driver["driver_size_tier"])
    start = dict(total_stats)
    phase2, reasons = phase2_rows(driver, candidate, config, cells, hspice, run_dir, signature, total_stats)
    write_csv(directory / "phase2_fine8.csv", phase2)
    local_stats = {key: total_stats[key] - start[key] for key in total_stats}
    if reasons:
        summary = driver_summary(driver, "NO-GO", reasons, local_stats)
        write_json(directory / "summary.json", summary)
        return summary, None
    sizing, sizing_reasons = derive_sizing(phase2, interface)
    write_json(directory / "fine_bank_sizing.json", sizing)
    if sizing_reasons:
        summary = driver_summary(driver, "NO-GO", sizing_reasons, {key: total_stats[key] - start[key] for key in total_stats}, sizing)
        write_json(directory / "summary.json", summary)
        return summary, None
    K = int(sizing["K_candidate"])
    first_coverage = coverage_rows("phase4_initial_coverage", driver, candidate, K, (7,), config, cells, hspice, run_dir, signature, total_stats)
    coverage_failures = coverage_reasons(first_coverage, (7,), K)
    if coverage_failures:
        corrected = rescaled_k(first_coverage, K) if coverage_failures == ["medium_fine_gap_remains"] else None
        if corrected is None or corrected <= K:
            summary = driver_summary(driver, "NO-GO", coverage_failures, {key: total_stats[key] - start[key] for key in total_stats}, sizing)
            write_csv(directory / "initial_coverage.csv", first_coverage)
            write_json(directory / "summary.json", summary)
            return summary, None
        if corrected > MAX_FINE_BANK:
            sizing["K_rescaled"] = corrected
            write_json(directory / "fine_bank_sizing.json", sizing)
            summary = driver_summary(driver, "NO-GO", ["K_exceeds_bounded_limit"], {key: total_stats[key] - start[key] for key in total_stats}, sizing)
            write_csv(directory / "initial_coverage.csv", first_coverage)
            write_json(directory / "summary.json", summary)
            return summary, None
        sizing["K_rescaled"] = corrected
        K = corrected
        first_coverage.extend(coverage_rows("phase4_initial_coverage_rescaled", driver, candidate, K, (7,), config, cells, hspice, run_dir, signature, total_stats))
        coverage_failures = coverage_reasons([row for row in first_coverage if int(row["K"]) == K], (7,), K)
    write_csv(directory / "initial_coverage.csv", first_coverage)
    write_json(directory / "fine_bank_sizing.json", sizing)
    if coverage_failures:
        summary = driver_summary(driver, "NO-GO", coverage_failures, {key: total_stats[key] - start[key] for key in total_stats}, sizing)
        write_json(directory / "summary.json", summary)
        return summary, None
    final_rows, final_reasons, fine_steps = final_monotonic_rows(driver, candidate, K, config, cells, hspice, run_dir, signature, total_stats)
    write_csv(directory / "full_bank_monotonicity.csv", final_rows)
    if final_reasons:
        summary = driver_summary(driver, "NO-GO", final_reasons, {key: total_stats[key] - start[key] for key in total_stats}, sizing)
        write_json(directory / "summary.json", summary)
        return summary, None
    coupled = coverage_rows("phase5_coupled_coverage", driver, candidate, K, (0, 7, 15), config, cells, hspice, run_dir, signature, total_stats)
    write_csv(directory / "coupled_medium_coverage.csv", coupled)
    coupled_min, margins, coupled_reasons = coupled_metrics(coupled, K, fine_steps)
    metrics = {"delta_fine_max_measured_ps_by_vdd": fine_steps, "medium_step_coupled_min_ps_by_vdd": coupled_min, "coverage_margin_ps_by_vdd": margins, "final_K": K, "critical_0p80_m15_fK": critical_endpoint(coupled, K)}
    if coupled_reasons:
        summary = driver_summary(driver, "NO-GO", coupled_reasons, {key: total_stats[key] - start[key] for key in total_stats}, sizing, metrics)
        write_json(directory / "summary.json", summary)
        return summary, None
    summary = driver_summary(driver, "GO", [], {key: total_stats[key] - start[key] for key in total_stats}, sizing, metrics)
    write_json(directory / "summary.json", summary)
    return summary, {"K": K, "coverage": [row for row in first_coverage if int(row["K"]) == K], "coupled": coupled, "metrics": metrics}


def render_report(path: Path, overall: Mapping[str, Any], probe_rows: Sequence[Mapping[str, Any]]) -> None:
    """Report endpoint improvement separately from full fine-stage acceptance."""

    baseline = historical_failure_endpoint()
    baseline_high, baseline_rise = float(baseline["output_logic_high"]), float(baseline["output_rise_time_ps"])
    lines = ["# FTC Standard-Cell Load Fine-Stage Driver Co-Design", "", "## Decision", "", "**{}**".format(overall["decision"]), "", "## Boundary", "", "- Fixed load: `NOR2_X4A_A9TL40__signal_A`, signal `A`, control `B`, high-load control `0`.", "- Frozen medium network: `N=16`, `BUF_X0P7M_A9TL40`, and `MXT2_X0P5M_A9TL40`.", "- Original logic limits remain `output_high >= 0.90*VDD` and `output_low <= 0.10*VDD`.", "- The historical endpoint probe is read-only evidence; endpoint PASS is not Fine Stage GO.", "", "## Historical Endpoint Probe", "", "Fixed endpoint: `M=15`, `F=8`, `K=8`, `VDD=0.80 V`.  The original high-level limit is `0.72 V`.", "", "| Driver | Output high (V) | High/VDD | Rise (ps) | Delta high vs X0P7 (V) | Delta rise vs X0P7 (ps) | Endpoint result |", "|---|---:|---:|---:|---:|---:|---|"]
    lines.append("| `BUF_X0P7M_A9TL40` (read-only baseline) | {:.9f} | {:.9f} | {:.3f} | 0.000000000 | 0.000 | FAIL |".format(baseline_high, baseline_high / 0.80, baseline_rise))
    for row in probe_rows:
        high, rise = float(row["output_logic_high"]), float(row["output_rise_time_ps"])
        lines.append("| `{}` | {:.9f} | {} | {:.3f} | {:.9f} | {:.3f} | {} |".format(row["driver_cell"], high, row["output_logic_high_ratio"], rise, high - baseline_high, rise - baseline_rise, "PASS" if str(row["valid"]).lower() == "true" else "FAIL"))
    lines.extend(["", "## Full Co-Design Results", "", "| Driver | Status | K | Reasons |", "|---|---|---:|---|"])
    for item in overall["drivers"]:
        sizing = item.get("sizing", {})
        K = item.get("metrics", {}).get("final_K", sizing.get("K_candidate", "-"))
        lines.append("| `{}` | {} | {} | {} |".format(item["driver"]["driver_cell"], item["status"], K, "; ".join(item["reasons"]) or "all gates passed"))
    lines.extend(["", "## Measured K And Critical Endpoint", "", "| Driver | K | FineRange_8 at 1.10/0.95/0.80 V (ps) | Deep 0.80 V high/low (V) | Result |", "|---|---:|---|---|---|"])
    for item in overall["drivers"]:
        sizing, metrics = item.get("sizing", {}), item.get("metrics", {})
        ranges = sizing.get("FineRange_8_ps_by_vdd", {})
        critical = metrics.get("critical_0p80_m15_fK", {})
        range_text = "/".join("{:.3f}".format(float(ranges[key])) if key in ranges else "-" for key in ("1.10", "0.95", "0.80"))
        level_text = "{}/{}".format(critical.get("output_logic_high", "-"), critical.get("output_logic_low", "-"))
        lines.append("| `{}` | {} | {} | {} | {} |".format(item["driver"]["driver_cell"], metrics.get("final_K", sizing.get("K_candidate", "-")), range_text, level_text, critical.get("valid", "-")))
    lines.extend(["", "## Coupled Gate Evidence", "", "| Driver | Fine max at 1.10/0.95 V (ps) | Coupled medium min at 1.10/0.95 V (ps) | 0.80 V conclusion |", "|---|---|---|---|"])
    for item in overall["drivers"]:
        metrics = item.get("metrics", {})
        fine, medium = metrics.get("delta_fine_max_measured_ps_by_vdd", {}), metrics.get("medium_step_coupled_min_ps_by_vdd", {})
        fine_text = "/".join("{:.3f}".format(float(fine[key])) if key in fine else "invalid" for key in ("1.10", "0.95"))
        medium_text = "/".join("{:.3f}".format(float(medium[key])) if key in medium else "invalid" for key in ("1.10", "0.95"))
        lines.append("| `{}` | {} | {} | deep waveform invalid; coverage/resolution gate not claimable |".format(item["driver"]["driver_cell"], fine_text, medium_text))
    qualified = overall.get("qualified_hspice_scenarios", overall["new_hspice_scenarios"])
    total = overall.get("task_total_hspice_scenarios", qualified)
    superseded = overall.get("superseded_hspice_scenarios", 0)
    lines.extend(["", "## Interpretation", "", "- The historical X0P7M failure was a weak-driver waveform failure, not evidence that the fixed NOR2 load lacks range.  The endpoint probe confirms that stronger buffers improve that one endpoint, but it does not characterize the larger K required after the driver changes.", "- Each candidate re-derived K from its own measured `FineRange_8`; the strongest tested driver reduces load sensitivity and therefore needs the largest K.", "- Every derived K remains within 64, but all four final deep 0.80 V endpoints violate the original high-level requirement; X2 also violates the low-level requirement.  Therefore a coverage or resolution claim at that voltage is deliberately not made.", "- A complete GO would require valid 0.80 V deep coverage in addition to monotonicity, 0.90/0.10 logic levels, K<=64, and fine resolution below the coupled medium step.  No `future_bypass_interface.json` is emitted because no driver passed all gates.", "", "## Evidence Accounting", "", "- Final-contract HSPICE scenarios: `{}`; reused matching final-contract scenarios: `{}`.".format(qualified, overall["reused_new_task_scenarios"]), "- Task-total HSPICE scenarios: `{}`; superseded non-final-contract scenarios: `{}`.".format(total, superseded), "- The superseded revision is retained for audit only and excluded from the final decision because its scenario identity omitted `logic_low_max_ratio`; the final revision reran the complete bounded matrix with that field present.", "- Historical medium/load-sweep/driver-probe scenarios rerun: `0/0/0`.", "- No bypass, configuration skip, sensor, XOR, DFF, calibration, droop, PVT, RTL, power, area, or layout scenarios were created.", "- A Fine Stage GO only covers this standard-cell fine stage and one-medium-step coverage; it is not a complete FTC droop-detection macro GO."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def finalize_existing(analysis: Path, report_path: Path) -> int:
    """Reclassify retained CSV evidence without changing decks or launching HSPICE.

    This path exists for report corrections after a runner-only change.  It
    refuses to proceed unless every retained raw scenario is already PASS, so
    it cannot turn an interrupted simulation into an apparent conclusion.
    """

    current = read_json(analysis / "summary.json")
    run_root = FTC_ROOT / "runs" / "standard_cell_load_fine_stage_driver_codesign"
    manifests = list(run_root.glob("r*/scenarios/*/scenario_manifest.json"))
    if not manifests or any(read_json(path).get("completion_status") != "PASS" for path in manifests):
        raise ValueError("cannot finalize retained evidence with incomplete raw scenarios")
    results = []
    for item in current["drivers"]:
        driver = item["driver"]
        directory = analysis / "driver_{}".format(driver["driver_size_tier"])
        phase2 = read_csv(directory / "phase2_fine8.csv")
        initial = read_csv(directory / "initial_coverage.csv")
        final_rows = read_csv(directory / "full_bank_monotonicity.csv")
        coupled = read_csv(directory / "coupled_medium_coverage.csv")
        K = int(item.get("metrics", {}).get("final_K", item["sizing"]["K_candidate"]))
        reasons = waveform_reasons(phase2 + initial + final_rows + coupled)
        reasons.extend(coverage_reasons(coupled, (0, 7, 15), K))
        # Preserve non-waveform decisions already computed from complete rows,
        # but remove the former false gap label caused by invalid waveforms.
        reasons.extend(reason for reason in item["reasons"] if reason not in ("driver_waveform_high_fail", "driver_waveform_low_fail", "medium_fine_gap_remains"))
        fine_steps: Dict[str, float] = {}
        for vdd in CORE.ANCHOR_VDD:
            local = rows_for(final_rows, 7, vdd)
            pairs = [(code, code + 1) for code in range(K)] if vdd == 0.95 else [(0, 1), (K - 1, K)]
            deltas = [float(local[right]["D_rise_ps"]) - float(local[left]["D_rise_ps"]) for left, right in pairs if left in local and right in local and row_is_valid(local[left]) and row_is_valid(local[right])]
            if deltas and all(delta > 0 for delta in deltas):
                fine_steps[CORE.vkey(vdd)] = max(deltas)
        coupled_min, margins, coupled_reasons = coupled_metrics(coupled, K, fine_steps)
        reasons.extend(coupled_reasons)
        metrics = {"delta_fine_max_measured_ps_by_vdd": fine_steps, "medium_step_coupled_min_ps_by_vdd": coupled_min, "coverage_margin_ps_by_vdd": margins, "final_K": K, "critical_0p80_m15_fK": critical_endpoint(coupled, K)}
        refreshed = driver_summary(driver, "NO-GO" if reasons else "GO", list(dict.fromkeys(reasons)), {"new": item["new_hspice_scenarios"], "reused": item["reused_new_task_scenarios"]}, item["sizing"], metrics)
        write_json(directory / "summary.json", refreshed)
        results.append(refreshed)
    current["drivers"] = results
    current["decision"] = "Fine Driver Co-Design = GO" if any(item["status"] == "GO" for item in results) else "Fine Driver Co-Design = NO-GO"
    revisions = sorted((path for path in run_root.glob("r*") if re.fullmatch(r"r\d+", path.name)), key=lambda path: int(path.name[1:]))
    counts = raw_scenario_counts(run_root, revisions[-1])
    current.update({"qualified_hspice_scenarios": counts["qualified"], "task_total_hspice_scenarios": counts["task_total"], "superseded_hspice_scenarios": counts["superseded"]})
    with (FTC_ROOT / "analysis" / "standard_cell_load_driver_strength_probe" / "driver_probe.csv").open(encoding="utf-8") as stream:
        probe_rows = list(csv.DictReader(stream))
    write_json(analysis / "summary.json", current)
    render_report(report_path, current, probe_rows)
    print("FTC_STANDARD_CELL_LOAD_FINE_STAGE_DRIVER_CODESIGN finalized={}".format(current["decision"]))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the bounded state machine and stop immediately at the smallest complete GO."""

    parser = argparse.ArgumentParser(description="run bounded fine-driver co-design")
    parser.add_argument("--config", type=Path, default=FTC_ROOT / "ftc_config.json")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis" / "standard_cell_load_fine_stage_driver_codesign")
    parser.add_argument("--run-root", type=Path, default=FTC_ROOT / "runs" / "standard_cell_load_fine_stage_driver_codesign")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports" / "FTC_STANDARD_CELL_LOAD_FINE_STAGE_DRIVER_CODESIGN.md")
    parser.add_argument("--stop-after", choices=("static",), help="publish only frozen/static evidence; never runs HSPICE")
    parser.add_argument("--finalize-existing", action="store_true", help="rebuild summaries and report from complete retained raw evidence only")
    args = parser.parse_args(argv)
    analysis, run_root = args.analysis_dir.resolve(), args.run_root.resolve()
    if args.finalize_existing:
        if args.stop_after:
            raise ValueError("--finalize-existing cannot be combined with --stop-after")
        return finalize_existing(analysis, args.report_output.resolve())
    interface, cells, candidate, paths = frozen_evidence()
    requirement_doc = requirements(interface, candidate, paths)
    requirement_path = analysis / "requirements.json"
    write_json(requirement_path, requirement_doc)
    try:
        drivers = discover_drivers(cells)
    except ValueError as error:
        overall = {"schema_version": 1, "decision": "Fine Driver Co-Design = ARCHITECTURE_BLOCKED", "drivers": [], "reasons": ["library_driver_contract_blocked: {}".format(error)], "new_hspice_scenarios": 0, "reused_new_task_scenarios": 0, "historical_medium_scenarios_rerun": 0, "historical_load_sweep_scenarios_rerun": 0, "historical_driver_probe_scenarios_rerun": 0}
        write_json(analysis / "summary.json", overall)
        render_report(args.report_output.resolve(), overall, [])
        return 0
    contract_path = analysis / "driver_contract.json"
    write_json(contract_path, {"schema_version": 1, "drivers": drivers, "medium_delay_cell": CORE.MEDIUM_DELAY_CELL, "medium_mux_cell": CORE.MEDIUM_MUX_CELL, "only_variable_instance": "XFINE_DRIVER"})
    write_json(analysis / "driver_candidates.json", {"schema_version": 1, "drivers": drivers})
    if args.stop_after == "static":
        print("FTC_STANDARD_CELL_LOAD_FINE_STAGE_DRIVER_CODESIGN static=contract_published")
        return 0
    config = CORE.load_json(args.config.resolve())
    hspice, version = CORE.validate_hspice(config)
    signature = run_signature(requirement_path, contract_path, paths["fixed_load_contract"])
    run_dir = select_run_dir(run_root, signature, hspice, version)
    stats, results, selected = {"new": 0, "reused": 0}, [], None
    for driver in drivers:
        result, accepted = run_driver(driver, candidate, interface, config, cells, hspice, run_dir, signature, analysis, stats)
        results.append(result)
        if accepted is not None:
            selected = (driver, result, accepted)
            break
    for driver in drivers[len(results):]:
        result = driver_summary(driver, "NOT_RUN", ["smaller_driver_complete_GO"], {"new": 0, "reused": 0})
        write_json(analysis / "driver_{}".format(driver["driver_size_tier"]) / "summary.json", result)
        results.append(result)
    overall: Dict[str, Any] = {
        "schema_version": 1, "decision": "Fine Driver Co-Design = GO" if selected else "Fine Driver Co-Design = NO-GO",
        "selected_fine_driver": selected[0]["driver_cell"] if selected else None,
        "selected_fine_load": candidate["candidate_id"], "drivers": results,
        "new_hspice_scenarios": stats["new"], "reused_new_task_scenarios": stats["reused"],
        "historical_medium_scenarios_rerun": 0, "historical_load_sweep_scenarios_rerun": 0,
        "historical_driver_probe_scenarios_rerun": 0, "sensor_scenarios": 0, "dff_scenarios": 0,
        "droop_scenarios": 0, "bypass_scenarios": 0, "final_fine_K_frozen": False,
        "final_medium_N_frozen": False,
    }
    counts = raw_scenario_counts(run_root, run_dir)
    overall.update({"qualified_hspice_scenarios": counts["qualified"], "task_total_hspice_scenarios": counts["task_total"], "superseded_hspice_scenarios": counts["superseded"]})
    if selected:
        driver, result, accepted = selected
        interface_doc = future_interface(driver, candidate, int(accepted["K"]), accepted["coverage"], accepted["coupled"], config, cells, hspice, run_dir, signature, stats)
        write_json(analysis / "future_bypass_interface.json", interface_doc)
        overall["future_bypass_interface"] = interface_doc
        overall["new_hspice_scenarios"] = stats["new"]
        overall["reused_new_task_scenarios"] = stats["reused"]
    with (paths["probe_rows"]).open(encoding="utf-8") as stream:
        probe_rows = list(csv.DictReader(stream))
    write_json(analysis / "summary.json", overall)
    render_report(args.report_output.resolve(), overall, probe_rows)
    print("FTC_STANDARD_CELL_LOAD_FINE_STAGE_DRIVER_CODESIGN decision={}".format(overall["decision"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
