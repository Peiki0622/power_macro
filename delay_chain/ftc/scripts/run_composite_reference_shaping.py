#!/usr/bin/env python3
"""Screen the fixed, tiny RVT/LVT composite-reference space from frozen data.

This is intentionally an analysis-only first gate.  It reconstructs each
simple reference delay movement from the committed residual evidence, then
recalculates the calibration factor for a weighted composite.  It never
instantiates tap29, reruns a simple reference, or invokes HSPICE.  Physical
simulation is permitted only after this script produces a nonempty shortlist.
"""

import argparse
import csv
import json
import math
from itertools import product
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
V0S = (1.10, 0.90)
TEMPERATURES = (-40.0, 25.0, 125.0)
RATIOS = ((1, 1), (1, 2), (2, 1))

# The prior physical study established a simple BUF/MUX unit as one cell and
# the INV/NAND2/NOR2 non-inverting units as two cells.  Keeping this explicit
# avoids rereading PDK collateral merely to enforce this task's <=4-cell gate.
SIMPLE_UNIT_CELLS = {"buf": 1, "mux": 1, "inv": 2, "nand2": 2, "nor2": 2}

OUTPUT_FIELDS = (
    "candidate_id", "rvt_candidate_id", "lvt_candidate_id", "rvt_units",
    "lvt_units", "total_standard_cells", "v0_v", "d_c_25c_ps",
    "w_s_25c_ps", "k_c", "e_t_m40c_ps", "e_t_125c_ps", "e_t_max_ps",
    "raw_sensor_temperature_movement_ps", "e_v_50mv_ps", "e_v_100mv_ps",
    "m_50_ps", "m_100_ps", "temperature_reduced", "m_100_positive",
    "candidate_rank", "shortlisted",
)
REQUIRED_SIMPLE_COLUMNS = {
    "candidate_id", "candidate_kind", "v0_v", "d_r_25c_ps",
    "w_s_25c_ps", "equivalent_unit_count", "e_t_m40c_ps",
    "e_t_125c_ps", "e_v_50mv_ps", "e_v_100mv_ps",
}
# ``fine.csv`` is a 25 C voltage curve and therefore has no corner/temperature
# columns; the temperature and PVT matrices carry those extra coordinates.
REQUIRED_FINE_COLUMNS = {"vdd_v", "W_real_ps", "valid"}
REQUIRED_PVT_COLUMNS = {"vdd_v", "corner", "temperature_c", "W_real_ps", "valid"}


def finite(value: Any, name: str) -> float:
    """Convert an evidence scalar and reject missing, nonnumeric, or NaN data."""

    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("{} is not numeric: {!r}".format(name, value)) from error
    if not math.isfinite(result):
        raise ValueError("{} is not finite: {!r}".format(name, value))
    return result


def voltage_key(value: Any) -> float:
    """Use the two-decimal voltage grid shared by the frozen sensor tables."""

    return round(finite(value, "VDD"), 2)


def load_rows(path: Path, required_columns: Sequence[str]) -> List[Dict[str, str]]:
    """Load one nonempty CSV and verify its schema before its data is used."""

    if not path.is_file():
        raise ValueError("required evidence is unavailable: {}".format(path))
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not set(required_columns).issubset(reader.fieldnames):
            raise ValueError("evidence schema is incomplete: {}".format(path))
        rows = list(reader)
    if not rows:
        raise ValueError("evidence is empty: {}".format(path))
    return rows


def load_object(path: Path) -> Dict[str, Any]:
    """Read one required JSON object so all mandated provenance is checked."""

    if not path.is_file():
        raise ValueError("required evidence is unavailable: {}".format(path))
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def stage_count(candidate_id: str) -> int:
    """Return the established physical cell count for one prior simple unit."""

    family = candidate_id.split("_", 1)[0]
    try:
        return SIMPLE_UNIT_CELLS[family]
    except KeyError as error:
        raise ValueError("unknown simple-unit family: {}".format(candidate_id)) from error


def load_evidence() -> Dict[str, Any]:
    """Read and cross-check every frozen artifact named by the task plan.

    Only TT values needed for prediction are indexed, but the previous finalist
    confirmation, its summary/report, and the full PVT matrix are also loaded
    and minimally checked.  This makes the final NO-GO traceable to the exact
    evidence set without treating any old experiment as a mutable input.
    """

    contrast = FTC_ROOT / "analysis" / "reference_sensitivity_contrast"
    baseline = FTC_ROOT / "analysis" / "real_xor_pvt_baseline"
    pulse = FTC_ROOT / "analysis" / "real_xor_pulse_width"
    paths = {
        "simple_candidate_screen": contrast / "simple_candidate_screen.csv",
        "finalist_pvt_confirmation": contrast / "finalist_pvt_confirmation.csv",
        "reference_summary": contrast / "summary.json",
        "reference_report": FTC_ROOT / "reports" / "FTC_REFERENCE_SENSITIVITY_CONTRAST_FEASIBILITY.md",
        "fine": pulse / "fine.csv",
        "temperature_screen": baseline / "temperature_screen.csv",
        "pvt_matrix": baseline / "pvt_matrix.csv",
    }
    simple_rows = load_rows(paths["simple_candidate_screen"], REQUIRED_SIMPLE_COLUMNS)
    finalist_rows = load_rows(paths["finalist_pvt_confirmation"], ("candidate_id", "corner"))
    fine_rows = load_rows(paths["fine"], REQUIRED_FINE_COLUMNS)
    temperature_rows = load_rows(paths["temperature_screen"], REQUIRED_PVT_COLUMNS)
    pvt_rows = load_rows(paths["pvt_matrix"], REQUIRED_PVT_COLUMNS)
    reference_summary = load_object(paths["reference_summary"])
    report_text = paths["reference_report"].read_text(encoding="utf-8") if paths["reference_report"].is_file() else ""
    if reference_summary.get("decision") != "CONDITIONAL" or "CONDITIONAL" not in report_text:
        raise ValueError("prior reference-sensitivity conclusion provenance is invalid")

    simple: Dict[Tuple[str, float], Dict[str, float]] = {}
    for row in simple_rows:
        candidate_id = row["candidate_id"]
        if row["candidate_kind"] != "simple" or not candidate_id.endswith(("_rvt", "_lvt")):
            raise ValueError("unexpected simple candidate: {}".format(candidate_id))
        key = (candidate_id, voltage_key(row["v0_v"]))
        if key in simple:
            raise ValueError("duplicate simple evidence: {}".format(key))
        simple[key] = {
            "d_r_25c_ps": finite(row["d_r_25c_ps"], "D_R 25C"),
            "k": finite(row["equivalent_unit_count"], "simple k"),
            "e_t_m40c_ps": finite(row["e_t_m40c_ps"], "E_T -40C"),
            "e_t_125c_ps": finite(row["e_t_125c_ps"], "E_T 125C"),
            "e_v_50mv_ps": finite(row["e_v_50mv_ps"], "E_V 50mV"),
            "e_v_100mv_ps": finite(row["e_v_100mv_ps"], "E_V 100mV"),
        }
    candidate_ids = sorted({key[0] for key in simple})
    if any((candidate_id, v0) not in simple for candidate_id in candidate_ids for v0 in V0S):
        raise ValueError("simple evidence lacks one required TT workpoint")

    fine: Dict[float, float] = {}
    for row in fine_rows:
        if int(row["valid"]) != 1:
            raise ValueError("invalid fine sensor evidence")
        vdd = voltage_key(row["vdd_v"])
        if vdd in fine:
            raise ValueError("duplicate fine sensor voltage: {}".format(vdd))
        fine[vdd] = finite(row["W_real_ps"], "fine W_real")
    temperature: Dict[Tuple[float, float], float] = {}
    for row in temperature_rows:
        if row["corner"].lower() != "tt" or int(row["valid"]) != 1:
            continue
        key = (voltage_key(row["vdd_v"]), finite(row["temperature_c"], "temperature"))
        if key in temperature:
            raise ValueError("duplicate TT temperature evidence: {}".format(key))
        temperature[key] = finite(row["W_real_ps"], "temperature W_real")
    for v0 in V0S:
        for temperature_c in TEMPERATURES:
            if (v0, temperature_c) not in temperature:
                raise ValueError("missing TT temperature evidence: {} {}".format(v0, temperature_c))
        for drop in (0.05, 0.10):
            if voltage_key(v0 - drop) not in fine:
                raise ValueError("missing fine sensor evidence at {} V".format(v0 - drop))
        if abs(temperature[(v0, 25.0)] - fine[v0]) > 1.0e-9:
            raise ValueError("temperature and fine sensor evidence disagree at {} V".format(v0))
    # The PVT table is not used before a physical shortlist exists, but reject
    # malformed old evidence now rather than claiming it was reused blindly.
    if not any(row["corner"].lower() in ("tt", "ff", "ss") and int(row["valid"]) == 1 for row in pvt_rows):
        raise ValueError("PVT matrix has no valid TT/FF/SS evidence")
    return {
        "simple": simple,
        "candidate_ids": candidate_ids,
        "fine": fine,
        "temperature": temperature,
        "sources": {name: str(path) for name, path in paths.items()},
        "source_rows": {"simple_candidate_screen": len(simple_rows), "finalist_pvt_confirmation": len(finalist_rows), "fine": len(fine_rows), "temperature_screen": len(temperature_rows), "pvt_matrix": len(pvt_rows)},
    }


def simple_delta_delay(simple: Mapping[str, float], sensor_delta: float, residual_key: str) -> float:
    """Recover one simple unit's delay movement from its residual definition.

    The stored residual is ``E = DeltaW_S - k * DeltaD_R``.  Solving that
    equation, rather than adding residuals from different calibrated units,
    yields the physical delay movement that can legally be added in a macro.
    """

    return (sensor_delta - simple[residual_key]) / simple["k"]


def predict_row(evidence: Mapping[str, Any], rvt_id: str, lvt_id: str, rvt_units: int, lvt_units: int, v0: float) -> Dict[str, Any]:
    """Compute one composite residual row with a newly calibrated ``k_C``."""

    simple = evidence["simple"]
    fine = evidence["fine"]
    temperature = evidence["temperature"]
    rvt = simple[(rvt_id, v0)]
    lvt = simple[(lvt_id, v0)]
    d_c_25 = rvt_units * rvt["d_r_25c_ps"] + lvt_units * lvt["d_r_25c_ps"]
    w_s_25 = fine[v0]
    k_c = w_s_25 / d_c_25
    e_t: Dict[float, float] = {}
    for temperature_c, residual_key in ((-40.0, "e_t_m40c_ps"), (125.0, "e_t_125c_ps")):
        sensor_delta = temperature[(v0, temperature_c)] - w_s_25
        composite_delta = (
            rvt_units * simple_delta_delay(rvt, sensor_delta, residual_key)
            + lvt_units * simple_delta_delay(lvt, sensor_delta, residual_key)
        )
        e_t[temperature_c] = sensor_delta - k_c * composite_delta
    voltage: Dict[str, float] = {}
    for drop, label, residual_key in ((0.05, "50", "e_v_50mv_ps"), (0.10, "100", "e_v_100mv_ps")):
        sensor_delta = fine[voltage_key(v0 - drop)] - w_s_25
        composite_delta = (
            rvt_units * simple_delta_delay(rvt, sensor_delta, residual_key)
            + lvt_units * simple_delta_delay(lvt, sensor_delta, residual_key)
        )
        voltage[label] = sensor_delta - k_c * composite_delta
    e_t_max = max(abs(value) for value in e_t.values())
    raw_movement = max(abs(temperature[(v0, temperature_c)] - w_s_25) for temperature_c in TEMPERATURES)
    candidate_id = "comp_{}x{}_{}x{}".format(rvt_id, rvt_units, lvt_id, lvt_units)
    return {
        "candidate_id": candidate_id, "rvt_candidate_id": rvt_id, "lvt_candidate_id": lvt_id,
        "rvt_units": rvt_units, "lvt_units": lvt_units,
        "total_standard_cells": rvt_units * stage_count(rvt_id) + lvt_units * stage_count(lvt_id),
        "v0_v": v0, "d_c_25c_ps": d_c_25, "w_s_25c_ps": w_s_25, "k_c": k_c,
        "e_t_m40c_ps": e_t[-40.0], "e_t_125c_ps": e_t[125.0], "e_t_max_ps": e_t_max,
        "raw_sensor_temperature_movement_ps": raw_movement,
        "e_v_50mv_ps": voltage["50"], "e_v_100mv_ps": voltage["100"],
        "m_50_ps": abs(voltage["50"]) - e_t_max, "m_100_ps": abs(voltage["100"]) - e_t_max,
        "temperature_reduced": int(e_t_max < raw_movement), "m_100_positive": int(abs(voltage["100"]) - e_t_max > 0.0),
        "candidate_rank": "", "shortlisted": 0,
    }


def predict_candidates(evidence: Mapping[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Enumerate only the 1:1, 1:2, and 2:1 mixed-VT legal combinations."""

    rvt_ids = [candidate_id for candidate_id in evidence["candidate_ids"] if candidate_id.endswith("_rvt")]
    lvt_ids = [candidate_id for candidate_id in evidence["candidate_ids"] if candidate_id.endswith("_lvt")]
    rows: List[Dict[str, Any]] = []
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for rvt_id, lvt_id, (rvt_units, lvt_units) in product(rvt_ids, lvt_ids, RATIOS):
        total_cells = rvt_units * stage_count(rvt_id) + lvt_units * stage_count(lvt_id)
        if total_cells > 4:
            continue
        candidate_rows = [predict_row(evidence, rvt_id, lvt_id, rvt_units, lvt_units, v0) for v0 in V0S]
        grouped[candidate_rows[0]["candidate_id"]] = candidate_rows
        rows.extend(candidate_rows)
    qualified = []
    for candidate_id, candidate_rows in grouped.items():
        if all(row["temperature_reduced"] and row["m_100_positive"] for row in candidate_rows):
            qualified.append((
                not all(row["m_50_ps"] > 0.0 for row in candidate_rows),
                -min(row["m_100_ps"] for row in candidate_rows),
                max(row["e_t_max_ps"] for row in candidate_rows),
                candidate_rows[0]["total_standard_cells"], candidate_id,
            ))
    qualified.sort()
    shortlist = [entry[-1] for entry in qualified[:3]]
    for rank, candidate_id in enumerate(shortlist, start=1):
        for row in grouped[candidate_id]:
            row["candidate_rank"] = rank
            row["shortlisted"] = 1
    rows.sort(key=lambda row: (row["candidate_id"], -row["v0_v"]))
    return rows, shortlist


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Write the complete nonempty audit table with its fixed public schema."""

    if not rows:
        raise ValueError("refusing to write empty composite prediction evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in OUTPUT_FIELDS})


def write_summary(path: Path, evidence: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], shortlist: Sequence[str]) -> None:
    """Persist the terminal gate decision and explicit reason HSPICE was skipped."""

    candidate_count = len({row["candidate_id"] for row in rows})
    summary = {
        "schema_version": 1,
        "study": "ftc_composite_reference_sensitivity_shaping",
        # A nonempty prediction shortlist is only permission for the limited
        # physical campaign.  It cannot be called GO until TT and PVT data
        # satisfy the later task gates.
        "decision": "PENDING_PHYSICAL_VALIDATION" if shortlist else "NO-GO",
        "decision_statement": "physical validation required" if shortlist else "Passive composite sensitivity shaping = NO-GO",
        "legal_candidate_count": candidate_count,
        "predicted_row_count": len(rows),
        "predicted_shortlist": list(shortlist),
        "hspice_executed": False,
        "hspice_skip_reason": "no TT-predicted composite passed both V0 temperature and M_100 gates" if not shortlist else "physical validation is required before a final decision",
        "sensor_experiments_rerun": False,
        "sources": evidence["sources"],
        "source_rows": evidence["source_rows"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_report(path: Path, rows: Sequence[Mapping[str, Any]], shortlist: Sequence[str]) -> None:
    """Answer only the task's three closure questions; no architecture is added."""

    candidate_count = len({row["candidate_id"] for row in rows})
    if shortlist:
        answer_one = "是；预测 shortlist 为 `{}`，必须进入受限的真实 composite HSPICE。".format(", ".join(shortlist))
        answer_two = "尚未验证；只允许对上述 shortlist 运行计划规定的 reference-only HSPICE。"
        answer_three = "尚未收口；真实 TT 与 PVT confirmation 后只能给出 GO 或 NO-GO。"
        decision = "PENDING PHYSICAL VALIDATION"
    else:
        answer_one = "否；{} 个合法组合均未在 1.10 V 和 0.90 V 同时通过温度 residual 与 M_100 门限。".format(candidate_count)
        answer_two = "未运行；预测 shortlist 为空，计划要求直接停止而不启动新 HSPICE。"
        answer_three = "`Passive Sensitivity-Contrast Reference = NO-GO`；下一阶段转为 programmable timing threshold、self-calibration 与 security-aware slow tracking。"
        decision = "NO-GO"
    lines = [
        "# FTC Composite Reference Sensitivity-Shaping", "",
        "## Decision", "", "**{}**".format(decision), "",
        "## Required Answers", "",
        "1. 正确 composite scaling 后，是否存在预测可行组合？{}".format(answer_one),
        "2. 真实 composite HSPICE 是否保留这种温度/VDD 可分性？{}".format(answer_two),
        "3. 这条 passive reference 路线最终是 GO 还是 NO-GO，下一阶段进入哪里？{}".format(answer_three), "",
        "## Provenance", "",
        "- 预测仅使用冻结的 simple reference、tap29 fine/temperature/PVT evidence；没有复跑 sensor、旧 simple reference 或 prior finalist PVT。",
        "- 搜索空间固定为一个 RVT unit 加一个 LVT unit，比例仅为 1:1、1:2、2:1，且总标准单元数不超过 4。",
        "- 每个 composite 先反解 parent delay movement，再以 composite nominal delay 重算 k_C；没有相加 parent residual。",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Iterable[str] = None) -> argparse.Namespace:
    """Expose only output locations; physical sweep coordinates are not inputs."""

    parser = argparse.ArgumentParser(description="screen frozen FTC composite-reference evidence")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis" / "composite_reference_shaping")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports" / "FTC_COMPOSITE_REFERENCE_SENSITIVITY_SHAPING.md")
    return parser.parse_args(argv)


def main(argv: Iterable[str] = None) -> int:
    """Run the prediction gate and terminate before HSPICE when it is empty."""

    args = parse_args(argv)
    evidence = load_evidence()
    rows, shortlist = predict_candidates(evidence)
    analysis_dir = args.analysis_dir.resolve()
    write_csv(analysis_dir / "predicted_candidates.csv", rows)
    write_summary(analysis_dir / "summary.json", evidence, rows, shortlist)
    write_report(args.report_output.resolve(), rows, shortlist)
    print("FTC_COMPOSITE_REFERENCE_SHAPING decision={} candidates={} shortlist={} hspice_executed=false".format(
        "PENDING_PHYSICAL_VALIDATION" if shortlist else "NO-GO", len({row["candidate_id"] for row in rows}), ",".join(shortlist)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
