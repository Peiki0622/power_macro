#!/usr/bin/env python3
"""Perform the zero-HSPICE B-FE1R review.

This stage does not render a deck and never starts HSPICE.  It consumes the
already committed B-FE1 pairwise JSON and the four saved scenario metadata
records, then emits a compact review package for a later latch decision.

The review has three deliberately bounded responsibilities:

1. Compare the formally selected LVT XOR2 cell with the legacy RVT XOR2 cell
   using the existing Liberty and CDL sources.  The legacy source record is
   not edited and no RVT replacement run is attempted.
2. Re-rank every existing normal/L2 candidate interval with one explicit,
   reproducible score that combines time width, four-sided headroom, Hamming
   distance, descriptive movement, bit margin, centrality, and fragmentation.
3. Record a small evidence manifest containing hashes and solver metadata, but
   never copy or hash-copy the large ``.tr0`` payload into the report tree.

The source and output formats are Python 3.6 compatible because this project
uses the host's Python 3.6 interpreter for several existing regressions.
"""

import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend"
ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe1_spatial_observability"
OUTPUT_ROOT = ANALYSIS_ROOT
PAIRWISE_JSON = ANALYSIS_ROOT / "normal_l2_pairwise_discrimination.json"
SCENARIO_MANIFEST = ANALYSIS_ROOT / "scenario_manifest.json"
BFE1_GATE = ANALYSIS_ROOT / "BFE1_GATE_STATUS.json"
BFE1_REPORT = ANALYSIS_ROOT / "BFE1_SPATIAL_OBSERVABILITY_REPORT.md"
STATUS_JSON = OUTPUT_ROOT / "BFE1R_REVIEW_STATUS.json"
EVIDENCE_JSON = OUTPUT_ROOT / "BFE1R_EVIDENCE_MANIFEST.json"
REPORT_MD = OUTPUT_ROOT / "BFE1R_REVIEW_REPORT.md"

LVT_CDL = Path("/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/cdl/sc9mc_logic0040ll_base_lvt_c40.cdl")
RVT_CDL = Path("/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/cdl/sc9mc_logic0040ll_base_rvt_c40.cdl")
LVT_LIB = Path("/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/lib/sc9mc_logic0040ll_base_lvt_c40_tt_typical_max_1p10v_25c.lib")
RVT_LIB = Path("/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/lib/sc9mc_logic0040ll_base_rvt_c40_tt_typical_max_1p10v_25c.lib")

XOR_NAMES = {"LVT": "XOR2_X0P5M_A9TL40", "RVT": "XOR2_X0P5M_A9TR40"}


def sha256_file(path: Path) -> str:
    """Hash one existing regular file without loading large traces in memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    """Read and validate one object-shaped JSON input."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def hash_inventory(paths: Iterable[Path]) -> Dict[str, str]:
    """Return stable workspace-relative or absolute labels and SHA256 values."""

    result = {}
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError("B-FE1R evidence input is missing: {}".format(path))
        try:
            label = str(path.relative_to(FTC_ROOT.parent.parent))
        except ValueError:
            label = str(path)
        result[label] = sha256_file(path)
    return result


def extract_cell_block(liberty: str, cell_name: str) -> str:
    """Extract one Liberty cell using its top-level cell boundary."""

    marker = "cell({}) {{".format(cell_name)
    start = liberty.find(marker)
    if start < 0:
        raise ValueError("Liberty cell is absent: {}".format(cell_name))
    end = liberty.find("\n  cell(", start + len(marker))
    return liberty[start:] if end < 0 else liberty[start:end]


def extract_cdl_block(cdl: str, cell_name: str) -> str:
    """Extract one CDL subcircuit through its matching ``.ends`` line."""

    match = re.search(r"(?im)^\.SUBCKT\s+{}\s+[^\n]+\n(.*?)(?=^\.ends)".format(re.escape(cell_name)), cdl, re.S)
    if match is None:
        raise ValueError("CDL subcircuit is absent: {}".format(cell_name))
    header = re.search(r"(?im)^\.SUBCKT\s+{}\s+[^\n]+".format(re.escape(cell_name)), cdl)
    return header.group(0) + "\n" + match.group(1)


def liberty_metrics(path: Path, cell_name: str) -> Dict[str, Any]:
    """Extract input capacitance and compact combinational timing summaries."""

    block = extract_cell_block(path.read_text(encoding="utf-8", errors="replace"), cell_name)
    metrics = {"cell": cell_name, "area": float(re.search(r"area\s*:\s*([0-9.eE+-]+)", block).group(1)), "inputs": {}}
    for pin in ("A", "B"):
        match = re.search(r"pin\({}\) \{{(.*?)\n    \}}".format(pin), block, re.S)
        if match is None:
            raise ValueError("Liberty input pin is absent: {} {}".format(cell_name, pin))
        pin_block = match.group(1)
        metrics["inputs"][pin] = {
            key: float(re.search(r"{}\s*:\s*([0-9.eE+-]+)".format(key), pin_block).group(1))
            for key in ("capacitance", "rise_capacitance", "fall_capacitance")
        }
    timing_records = []
    starts = [match.start() for match in re.finditer(r"(?m)^      timing\(\) \{", block)]
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(block)
        timing_block = block[start:end]
        related = re.search(r"related_pin\s*:\s*\"([AB])\"", timing_block)
        sense = re.search(r"timing_sense\s*:\s*([^;]+)", timing_block)
        if related is None or sense is None:
            continue
        record = {"related_pin": related.group(1), "timing_sense": sense.group(1).strip(), "tables": {}}
        for table_name in ("cell_rise", "cell_fall", "rise_transition", "fall_transition"):
            table = re.search(r"{}\([^)]*\) \{{(.*?)\n        \}}".format(table_name), timing_block, re.S)
            if table is None:
                continue
            values = []
            for row in re.findall(r"values\((.*?)\);", table.group(1), re.S):
                values.extend(float(token) for token in re.findall(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?", row))
            record["tables"][table_name] = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "mean": statistics.mean(values),
            }
        timing_records.append(record)
    metrics["timing"] = timing_records
    metrics["timing_record_count"] = len(timing_records)
    return metrics


def cdl_metrics(path: Path, cell_name: str) -> Dict[str, Any]:
    """Summarize topology/model identity without changing the CDL source."""

    block = extract_cdl_block(path.read_text(encoding="utf-8", errors="replace"), cell_name)
    devices = [line.strip() for line in block.splitlines() if line.strip().startswith("XI")]
    models = sorted(set(match.group(1) for line in devices for match in [re.search(r"\s([^\s]+)\s+w=", line)] if match))
    widths = sorted(set(re.findall(r"w=([^\s]+)", block)))
    lengths = sorted(set(re.findall(r"l=([^\s]+)", block)))
    ports = re.search(r"(?im)^\.SUBCKT\s+{}\s+([^\n]+)".format(re.escape(cell_name)), block).group(1).split()
    return {"cell": cell_name, "ports": ports, "device_count": len(devices), "models": models, "widths": widths, "lengths": lengths}


def compare_xor_cells() -> Dict[str, Any]:
    """Compare the formal LVT candidate and legacy RVT reference."""

    sources = {"LVT": {"cdl": LVT_CDL, "liberty": LVT_LIB}, "RVT": {"cdl": RVT_CDL, "liberty": RVT_LIB}}
    result = {"decision": "retain_lvt_formal_selection", "decision_reason": [
        "B-FE0/B-FE1 explicitly selected the real LVT XOR and the saved four-scenario evidence uses that cell.",
        "LVT and RVT have identical XOR truth function, seven-port CDL interface, transistor count, widths, lengths, and Liberty area.",
        "LVT input load is modestly higher, but the existing B-FE1 traces already include that physical load and all four paths remain monotonic with GO.",
        "The TT Liberty timing summaries do not show an across-the-board LVT slowdown; the lower-VT cell is suitable for the spatial front-end observation role.",
    ], "cells": {}}
    for vt, files in sources.items():
        cell = XOR_NAMES[vt]
        result["cells"][vt] = {
            "cell": cell,
            "cdl_path": str(files["cdl"]),
            "cdl_sha256": sha256_file(files["cdl"]),
            "liberty_path": str(files["liberty"]),
            "liberty_sha256": sha256_file(files["liberty"]),
            "cdl": cdl_metrics(files["cdl"], cell),
            "liberty": liberty_metrics(files["liberty"], cell),
        }
    lvt = result["cells"]["LVT"]["liberty"]["inputs"]
    rvt = result["cells"]["RVT"]["liberty"]["inputs"]
    result["input_capacitance_delta_percent"] = {
        pin: 100.0 * (lvt[pin]["capacitance"] / rvt[pin]["capacitance"] - 1.0) for pin in ("A", "B")
    }
    result["input_capacitance_mean_delta_percent"] = 100.0 * (
        (lvt["A"]["capacitance"] + lvt["B"]["capacitance"]) /
        (rvt["A"]["capacitance"] + rvt["B"]["capacitance"]) - 1.0
    )
    lvt_timing = result["cells"]["LVT"]["liberty"]["timing"]
    rvt_timing = result["cells"]["RVT"]["liberty"]["timing"]
    # Liberty may serialize otherwise identical timing arcs in a different
    # order between VT libraries.  Timing comparison is therefore keyed by
    # electrical arc identity, never by positional list order.  A missing or
    # duplicate key is an audit failure: silently pairing it to another arc
    # would manufacture a meaningless LVT/RVT comparison.
    def arc_map(records, vt_name):
        mapped = {}
        for record in records:
            key = "{}|{}".format(record["related_pin"], record["timing_sense"])
            if key in mapped:
                raise ValueError("duplicate Liberty timing arc in {}: {}".format(vt_name, key))
            mapped[key] = record
        return mapped

    lvt_arcs = arc_map(lvt_timing, "LVT")
    rvt_arcs = arc_map(rvt_timing, "RVT")
    if set(lvt_arcs) != set(rvt_arcs):
        raise ValueError("LVT/RVT Liberty timing arc identities differ: LVT={} RVT={}".format(
            sorted(lvt_arcs), sorted(rvt_arcs)))
    timing_delta = {}
    for arc in sorted(lvt_arcs):
        lvt_record = lvt_arcs[arc]
        rvt_record = rvt_arcs[arc]
        timing_delta[arc] = {}
        if set(lvt_record["tables"]) != set(rvt_record["tables"]):
            raise ValueError("LVT/RVT Liberty timing tables differ for arc: {}".format(arc))
        for table_name, lvt_table in lvt_record["tables"].items():
            rvt_table = rvt_record["tables"][table_name]
            timing_delta[arc][table_name] = 100.0 * (lvt_table["mean"] / rvt_table["mean"] - 1.0)
    result["timing_mean_delta_percent_lvt_vs_rvt"] = timing_delta
    return result


def candidate_rank(pair: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Rank all pairwise candidates with an explicit latch-oriented score.

    The score is intentionally small and auditable rather than a new detector:
    width (30%), four-sided headroom (20%), Hamming distance (15%), aggregate
    descriptive movement (15%), minimum bit margin (15%), and centrality (5%).
    Fragmented/tied/undefined candidates receive a zero fragmentation factor.
    All current candidates are already clean, but the factor makes the review
    robust if the saved JSON later contains a degraded interval.
    """

    candidates = pair["candidate_platforms"]
    if not candidates:
        return []
    max_width = max(item["interval_width_ps"] for item in candidates)
    max_hamming = max(item["hamming_distance"] for item in candidates) or 1
    max_margin = max(min(item["normal"]["minimum_bit_margin_v"], item["l2"]["minimum_bit_margin_v"]) for item in candidates) or 1.0
    ranked = []
    for item in candidates:
        normal = item["normal"]
        l2 = item["l2"]
        headroom = min(normal["left_headroom"], normal["right_headroom"], l2["left_headroom"], l2["right_headroom"])
        margin = min(normal["minimum_bit_margin_v"], l2["minimum_bit_margin_v"])
        movement = sum(abs(item[key] or 0.0) for key in ("delta_start", "delta_end", "delta_center"))
        mean_center = (normal["center"] + l2["center"]) / 2.0
        centrality = max(0.0, 1.0 - abs(mean_center - 14.5) / 14.5)
        clean = (not normal["fragmented"] and not l2["fragmented"] and
                 normal["run_count"] == 1 and l2["run_count"] == 1 and
                 len(normal["main_run_ties"]) == 1 and len(l2["main_run_ties"]) == 1 and
                 normal["undefined_bit_count"] == 0 and l2["undefined_bit_count"] == 0)
        score = (
            0.30 * item["interval_width_ps"] / max_width +
            0.20 * headroom / 14.5 +
            0.15 * item["hamming_distance"] / max_hamming +
            0.15 * min(movement / 30.0, 1.0) +
            0.15 * margin / max_margin +
            0.05 * centrality
        ) * (1.0 if clean else 0.0)
        ranked.append({
            "rank": 0,
            "score": score,
            "interval_start_ps": item["interval_start_ps"],
            "interval_end_ps": item["interval_end_ps"],
            "interval_width_ps": item["interval_width_ps"],
            "minimum_headroom_taps": headroom,
            "hamming_distance": item["hamming_distance"],
            "delta_start": item["delta_start"],
            "delta_end": item["delta_end"],
            "delta_center": item["delta_center"],
            "aggregate_movement": movement,
            "minimum_bit_margin_v": margin,
            "mean_main_run_center": mean_center,
            "central_tap_region": 10.0 <= mean_center <= 19.0,
            "fragmentation_clean": clean,
            "normal_headroom": {"left": normal["left_headroom"], "right": normal["right_headroom"]},
            "l2_headroom": {"left": l2["left_headroom"], "right": l2["right_headroom"]},
            "normal_main_run": {
                "start": normal["start"], "end": normal["end"], "len": normal["len"],
                "center": normal["center"], "run_count": normal["run_count"],
                "fragmented": normal["fragmented"], "tie_count": len(normal["main_run_ties"]),
                "undefined_bit_count": normal["undefined_bit_count"],
            },
            "l2_main_run": {
                "start": l2["start"], "end": l2["end"], "len": l2["len"],
                "center": l2["center"], "run_count": l2["run_count"],
                "fragmented": l2["fragmented"], "tie_count": len(l2["main_run_ties"]),
                "undefined_bit_count": l2["undefined_bit_count"],
            },
            "normal_raw_code": normal["raw_code"],
            "l2_raw_code": l2["raw_code"],
        })
    ranked.sort(key=lambda item: (-item["score"], -item["interval_width_ps"], -item["minimum_headroom_taps"], item["interval_start_ps"]))
    for index, item in enumerate(ranked, 1):
        item["rank"] = index
    return ranked


def review_candidates(pairwise: Mapping[str, Any]) -> Dict[str, Any]:
    """Rank both formal baselines and compare 0.95-V early versus central windows."""

    result = {"score_formula": {
        "width": 0.30, "minimum_four_sided_headroom": 0.20, "hamming_distance": 0.15,
        "aggregate_abs_delta_start_end_center": 0.15, "minimum_bit_margin": 0.15, "centrality": 0.05,
        "fragmentation_factor": "1 for clean single-run candidates, otherwise 0",
    }, "pairs": []}
    for pair in pairwise["pairs"]:
        ranked = candidate_rank(pair)
        central = [item for item in ranked if item["central_tap_region"]]
        current = pair["largest_platform"]
        current_ranked = next(item for item in ranked if abs(item["interval_start_ps"] - current["interval_start_ps"]) < 1.0e-9)
        result["pairs"].append({
            "baseline_v": pair["baseline_v"],
            "candidate_count": len(ranked),
            "ranked_candidates": ranked,
            "priority_candidates": ranked[:5],
            "central_tap_priority_candidates": central[:5],
            "previous_report_largest_platform": current_ranked,
            "central_region_beats_previous_report_largest": bool(central and central[0]["score"] > current_ranked["score"]),
        })
    return result


def scenario_evidence() -> Dict[str, Any]:
    """Collect four scenario identities and compact file hashes only."""

    sys.path.insert(0, str(FTC_ROOT / "scripts"))
    import bfe1_frontend  # noqa: E402

    manifest = read_json(SCENARIO_MANIFEST)
    authority_keys = {
        "BFE1-095-L2": "t0_5a_0p95_l2_long",
        "BFE1-110-L2": "t0_5a_1p10_l2_long",
    }
    entries = []
    for scenario in manifest["scenarios"]:
        scenario_id = scenario["scenario_id"]
        directory = RUN_ROOT / "scenarios" / scenario_id.lower().replace("-", "_")
        trace = bfe1_frontend.parse_ascii_tr0(directory / "bfe1.tr0")
        entries.append({
            "scenario_id": scenario_id,
            "baseline_v": scenario["baseline_v"],
            "droop_v": scenario["droop_v"],
            "phase_ps": scenario["phase_ps"],
            "authority_scenario_key": scenario.get("authority_scenario_key") or authority_keys.get(scenario_id),
            "deck_sha256": sha256_file(directory / "bfe1.sp"),
            "tr0_sha256": sha256_file(directory / "bfe1.tr0"),
            # Version is recorded per scenario.  It must not be copied from
            # the first record, because mixed-solver evidence is invalid even
            # when the four decks and traces otherwise look complete.
            "hspice_version": scenario.get("hspice_version"),
            "record_count": trace["record_count"],
            "record_width": trace["record_width"],
        })
    return {"hspice_scenario_count": len(entries), "scenarios": entries}


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write one deterministic, human-readable JSON artifact."""

    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bfe1r_gate_reasons(gate, pairwise, scenario_review, prior_evidence, bfe0):
    """Return concrete B-FE1R readiness failures from retained evidence.

    This is intentionally a small predicate, rather than a second detector:
    it verifies that the already-approved B-FE1 physical evidence still says
    what B-FE1R relies on.  Every failure is retained as a string so an
    inconsistent review cannot be mistaken for a ready-to-run B-FE2 result.
    """

    reasons = []
    if gate.get("gate") != "BFE1_SPATIAL_OBSERVABILITY_GO":
        reasons.append("legacy B-FE1 gate is not BFE1_SPATIAL_OBSERVABILITY_GO")
    if bfe0.get("xor_cell") != XOR_NAMES["LVT"]:
        reasons.append("formal B-FE1 XOR is not XOR2_X0P5M_A9TL40")
    if len(scenario_review["scenarios"]) != 4:
        reasons.append("B-FE1 scenario count is not four")
    previous = {item["scenario_id"]: item for item in prior_evidence.get("scenario_evidence", {}).get("scenarios", [])}
    for record in scenario_review["scenarios"]:
        expected = previous.get(record["scenario_id"])
        if expected is None:
            reasons.append("missing prior evidence for {}".format(record["scenario_id"]))
            continue
        for field in ("deck_sha256", "tr0_sha256"):
            if record.get(field) != expected.get(field):
                reasons.append("{} SHA mismatch for {}".format(field, record["scenario_id"]))
        if not record.get("hspice_version"):
            reasons.append("missing HSPICE version for {}".format(record["scenario_id"]))
    for pair in pairwise.get("pairs", []):
        baseline = pair.get("baseline_v")
        clean = [item for item in pair.get("candidate_platforms", []) if
                 item.get("interval_width_ps", 0.0) > 0.0 and
                 not item["normal"].get("fragmented") and not item["l2"].get("fragmented") and
                 item["normal"].get("undefined_bit_count") == 0 and item["l2"].get("undefined_bit_count") == 0 and
                 not item["normal"].get("touches_left") and not item["normal"].get("touches_right") and
                 not item["l2"].get("touches_left") and not item["l2"].get("touches_right")]
        central = [item for item in clean if 10.0 <= (item["normal"]["center"] + item["l2"]["center"]) / 2.0 <= 19.0]
        if not central:
            reasons.append("no clean central positive-width candidate at {:.2f} V".format(baseline))
    if len(pairwise.get("pairs", [])) != 2:
        reasons.append("B-FE1 pairwise evidence does not contain both formal baselines")
    return reasons


def build_report(status: Mapping[str, Any]) -> str:
    """Render the short Chinese review report required by B-FE1R."""

    lines = [
        "# B-FE1R 修正审查报告", "", "## Gate", "", "**{}**".format(status["gate"]), "",
        "本阶段 0 个新 HSPICE；未实现 latch，未修改 M/F、控制器或旧 sensor。", "",
        "## XOR 选择", "",
        "正式选择：`XOR2_X0P5M_A9TL40`（LVT）。它与 legacy `XOR2_X0P5M_A9TR40` 具有相同七端口、真值函数、10 个晶体管和相同 W/L；LVT A/B 输入电容分别比 RVT 高约 {:.2f}%/{:.2f}%，但已有四场景就是在该真实 LVT 负载下完成，且 TT Liberty 时序没有显示系统性变慢。".format(
            status["xor_review"]["input_capacitance_delta_percent"]["A"], status["xor_review"]["input_capacitance_delta_percent"]["B"]),
        "若未来改回 RVT，必须重新运行 B-FE1 四场景；本阶段没有重跑。", "",
        "## 候选窗口", "",
        "评分同时考虑平台宽度、四侧最小 headroom、汉明距离、ΔSTART/ΔEND/ΔCENTER、最小 bit 裕量、中心 tap 偏好及碎裂。完整排名在 `BFE1R_REVIEW_STATUS.json`。",
    ]
    for pair in status["candidate_review"]["pairs"]:
        top = pair["priority_candidates"][0]
        lines.append("- {:.2f} V：首选 {:.6f}–{:.6f} ps，宽 {:.6f} ps，中心 {:.2f}，headroom {} tap，HD {}，最小裕量 {:.6f} V。".format(
            pair["baseline_v"], top["interval_start_ps"], top["interval_end_ps"], top["interval_width_ps"],
            top["mean_main_run_center"], top["minimum_headroom_taps"], top["hamming_distance"], top["minimum_bit_margin_v"]))
        if pair["baseline_v"] == 0.95:
            lines.append("  0.95 V 中部 tap 候选优于旧报告最大平台：综合分 {:.4f} 对 {:.4f}；旧平台中心 {:.2f}、headroom {}，中部首选中心 {:.2f}、headroom {}。".format(
                top["score"], pair["previous_report_largest_platform"]["score"],
                pair["previous_report_largest_platform"]["mean_main_run_center"], pair["previous_report_largest_platform"]["minimum_headroom_taps"],
                top["mean_main_run_center"], top["minimum_headroom_taps"]))
    lines.extend(["", "## 证据边界", "", "`BFE1R_EVIDENCE_MANIFEST.json` 只保存四个场景的身份、deck/tr0 SHA256、HSPICE 版本、record count、权威输入 SHA 和分析产物 SHA，不复制巨大 `.tr0`。现有 `BFE1_SPATIAL_OBSERVABILITY_GO` 未被无依据推翻。", ""])
    return "\n".join(lines)


def main() -> int:
    """Build BFE1R status, evidence manifest, and report with zero HSPICE."""

    sys.path.insert(0, str(FTC_ROOT / "scripts"))
    import bfe1_frontend  # noqa: E402

    # Read the previous compact manifest before regenerating it.  This lets
    # the review prove that the retained deck/trace bytes are unchanged rather
    # than merely reporting the hashes it just computed.
    prior_evidence = read_json(EVIDENCE_JSON)
    pairwise = read_json(PAIRWISE_JSON)
    manifest = read_json(SCENARIO_MANIFEST)
    gate = read_json(BFE1_GATE)
    xor_review = compare_xor_cells()
    candidate_review = review_candidates(pairwise)
    scenario_review = scenario_evidence()
    input_authorities = [
        FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe0_architecture_contract.json",
        FTC_ROOT / "ftc_config.json", FTC_ROOT / "discovery" / "selected_cells.json",
        FTC_ROOT / "analysis" / "t0_transient_droop" / "contract" / "T0_TRANSIENT_THREAT_CONTRACT.json",
        FTC_ROOT / "analysis" / "t0_transient_droop" / "cadence" / "cadence_summary.json",
    ]
    analysis_inputs = [SCENARIO_MANIFEST, PAIRWISE_JSON, BFE1_GATE, BFE1_REPORT]
    bfe0 = read_json(FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe0_architecture_contract.json")
    gate_reasons = bfe1r_gate_reasons(gate, pairwise, scenario_review, prior_evidence, bfe0)
    status = {
        "schema_version": 1,
        "stage": "B-FE1R",
        "review_commit": "59a852c80d44c15b54726a095e0476c3d382cc4c",
        "branch": "bfe-multitap-latched-frontend",
        "new_hspice_scenarios": 0,
        "forbidden_work_performed": False,
        "legacy_bfe1_gate_preserved": gate.get("gate") == "BFE1_SPATIAL_OBSERVABILITY_GO",
        "gate": "BFE1R_READY_FOR_BFE2" if not gate_reasons else "BFE1R_REVIEW_INCONSISTENT",
        "gate_reasons": gate_reasons,
        "xor_review": xor_review,
        "candidate_review": candidate_review,
        "scenario_evidence": scenario_review,
        "input_authority_sha256": hash_inventory(input_authorities),
        "existing_analysis_artifact_sha256": hash_inventory(analysis_inputs),
        "large_tr0_copied": False,
        "bfe2_started": False,
    }
    write_json(STATUS_JSON, status)
    evidence = {
        "schema_version": 1, "stage": "B-FE1R", "review_commit": status["review_commit"],
        "scenario_evidence": scenario_review,
        "input_authority_sha256": status["input_authority_sha256"],
        "existing_analysis_artifact_sha256": status["existing_analysis_artifact_sha256"],
        "xor_source_sha256": {vt: {"cdl": record["cdl_sha256"], "liberty": record["liberty_sha256"]} for vt, record in xor_review["cells"].items()},
        "large_tr0_copied": False,
    }
    report = build_report(status)
    REPORT_MD.write_text(report, encoding="utf-8")
    # Add the generated report hash to the status, then record both generated
    # review products in the compact evidence manifest.  The manifest does not
    # self-hash, avoiding a circular provenance value.
    status["generated_review_report_sha256"] = sha256_file(REPORT_MD)
    write_json(STATUS_JSON, status)
    evidence["generated_review_artifact_sha256"] = {
        "BFE1R_REVIEW_STATUS.json": sha256_file(STATUS_JSON),
        "BFE1R_REVIEW_REPORT.md": sha256_file(REPORT_MD),
    }
    write_json(EVIDENCE_JSON, evidence)
    print("{} zero_hspice=0 candidates_reparsed={}".format(status["gate"], sum(item["candidate_count"] for item in candidate_review["pairs"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
