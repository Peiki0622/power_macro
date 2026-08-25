#!/usr/bin/env python3
"""Reconstruct B-FE1 spatial codes and discrimination platforms from .tr0.

This script is a zero-HSPICE analysis stage.  It reads the four completed
B-FE1 waveform traces, finds each real XOR threshold crossing against the
instantaneous monitored supply, and samples only between adjacent physical
crossing boundaries.  It never substitutes a fixed time grid and never
modifies a raw code to hide bubbles or fragmented runs.

All compact products are emitted under ``analysis/b_fe_frontend``.  The raw
decks, solver listings, .tr0 files, and command logs remain grouped under the
single task-owned ``runs/b_fe_frontend`` directory created by the runner.
"""

import bisect
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as error:  # pragma: no cover - only a missing environment dependency.
    raise SystemExit("B-FE1 figure generation requires matplotlib: {}".format(error))


FTC_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = FTC_ROOT / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))
import bfe1_frontend  # noqa: E402  # Reviewed ASCII .tr0 reader and common constants.


RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend"
OUTPUT_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe1_spatial_observability"
LAUNCH_PS = bfe1_frontend.LAUNCH_S * 1.0e12
STOP_PS = bfe1_frontend.STOP_S * 1.0e12
EPSILON_PS = 1.0e-6
UNDEFINED_MARGIN_V = 1.0e-9


def read_json(path: Path) -> Dict[str, Any]:
    """Read an object-shaped JSON artifact without changing source evidence."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def interpolate(times: Sequence[float], values: Sequence[float], time_s: float) -> float:
    """Linearly evaluate one adaptive HSPICE waveform at one interior time.

    Duplicate HSPICE timestamps are legal; ``bisect_right`` deliberately uses
    the final value at an exact timestamp before interpolating to the next
    distinct time.  The caller only requests times inside the recorded span.
    """

    if time_s < times[0] - 1.0e-18 or time_s > times[-1] + 1.0e-18:
        raise ValueError("query time is outside the retained B-FE1 waveform")
    right = bisect.bisect_right(times, time_s)
    if right == 0:
        return values[0]
    left = right - 1
    if right == len(times) or times[left] == time_s:
        return values[left]
    if times[right] == times[left]:
        return values[right]
    fraction = (time_s - times[left]) / (times[right] - times[left])
    return values[left] + fraction * (values[right] - values[left])


def crossing_events(trace: Mapping[str, Any], node: str) -> Dict[str, List[float]]:
    """Return all physical rise/fall crossings of node minus local VDD/2.

    The result is launch-relative picoseconds.  A zero exactly at a saved
    solver point is emitted once, with its direction inferred from the next
    sign change; adjacent duplicate events are collapsed only at numerical
    epsilon, never by an arbitrary time bin.
    """

    columns = trace["columns"]
    times = columns["time"]
    node_values = columns[bfe1_frontend.label_for(node)]
    rail_values = columns[bfe1_frontend.label_for("vdd_monitored")]
    signed = [value - 0.5 * rail for value, rail in zip(node_values, rail_values)]
    events = {"rise_ps": [], "fall_ps": []}
    for index in range(1, len(signed)):
        left, right = signed[index - 1], signed[index]
        if left == right or (left > 0.0 and right > 0.0) or (left < 0.0 and right < 0.0):
            continue
        if left == 0.0:
            crossing_s = times[index - 1]
        elif right == 0.0:
            crossing_s = times[index]
        else:
            crossing_s = times[index - 1] + (-left / (right - left)) * (times[index] - times[index - 1])
        direction = "rise_ps" if right > left else "fall_ps"
        crossing_ps = crossing_s * 1.0e12 - LAUNCH_PS
        if crossing_ps < -EPSILON_PS or crossing_ps > STOP_PS - LAUNCH_PS + EPSILON_PS:
            continue
        if not events[direction] or abs(events[direction][-1] - crossing_ps) > EPSILON_PS:
            events[direction].append(crossing_ps)
    return events


def code_metrics(bits: Sequence[int]) -> Dict[str, Any]:
    """Describe the raw spatial word without bubble repair or run selection edits.

    ``raw_code`` is intentionally tap-ascending: its leftmost character is
    physical tap 0.  This matches the legacy FTC CSV convention and makes
    START/END refer directly to a readable character index.  Tied longest
    runs are all retained; the first one supplies the scalar START/END fields
    only so every interval has a deterministic schema.
    """

    runs = []
    index = 0
    while index < len(bits):
        if bits[index] == 0:
            index += 1
            continue
        start = index
        while index < len(bits) and bits[index] == 1:
            index += 1
        runs.append({"start": start, "end": index - 1, "len": index - start})
    raw_code = "".join(str(bit) for bit in bits)
    if not runs:
        return {
            "raw_code": raw_code, "start": None, "end": None, "len": 0,
            "center": None, "run_count": 0, "bubble_count": 0,
            "left_headroom": None, "right_headroom": None,
            "main_run_ties": [], "empty": True, "touches_left": False,
            "touches_right": False, "fragmented": False,
        }
    maximum = max(item["len"] for item in runs)
    tied = [item for item in runs if item["len"] == maximum]
    main = tied[0]
    return {
        "raw_code": raw_code,
        "start": main["start"], "end": main["end"], "len": main["len"],
        "center": (main["start"] + main["end"]) / 2.0,
        "run_count": len(runs),
        # A main run is by definition contiguous.  Do not invent a repaired
        # bubble metric: fragmentation is reported separately by run_count.
        "bubble_count": 0,
        "left_headroom": main["start"],
        "right_headroom": bfe1_frontend.OBSERVABLE_TAPS - 1 - main["end"],
        "main_run_ties": tied,
        "empty": False,
        "touches_left": main["start"] == 0,
        "touches_right": main["end"] == bfe1_frontend.OBSERVABLE_TAPS - 1,
        "fragmented": len(runs) > 1,
    }


def snapshot(trace: Mapping[str, Any], relative_ps: float) -> Dict[str, Any]:
    """Classify all 30 XOR nodes at one non-boundary launch-relative time."""

    absolute_s = (LAUNCH_PS + relative_ps) * 1.0e-12
    columns = trace["columns"]
    times = columns["time"]
    rail = interpolate(times, columns[bfe1_frontend.label_for("vdd_monitored")], absolute_s)
    bits = []
    margins = []
    for index in range(bfe1_frontend.OBSERVABLE_TAPS):
        voltage = interpolate(times, columns[bfe1_frontend.label_for("xor_{}".format(index))], absolute_s)
        margin = voltage - 0.5 * rail
        bits.append(1 if margin > 0.0 else 0)
        margins.append(abs(margin))
    result = code_metrics(bits)
    result["sample_ps"] = relative_ps
    result["minimum_bit_margin_v"] = min(margins)
    result["undefined_bit_count"] = sum(1 for margin in margins if margin <= UNDEFINED_MARGIN_V)
    return result


def unique_boundaries(values: Iterable[float]) -> List[float]:
    """Sort physical boundaries and merge only numerical duplicates."""

    sorted_values = sorted(float(value) for value in values)
    result = []
    for value in sorted_values:
        if not result or abs(value - result[-1]) > EPSILON_PS:
            result.append(value)
    return result


def path_monotonicity(trace: Mapping[str, Any], prefix: str) -> Dict[str, Any]:
    """Measure first rising edge order on all path taps using local VDD/2."""

    first = []
    for index in range(bfe1_frontend.OBSERVABLE_TAPS):
        rises = crossing_events(trace, "{}_{}".format(prefix, index))["rise_ps"]
        first.append(rises[0] if rises else None)
    finite = [value for value in first if value is not None]
    ordered = len(finite) == bfe1_frontend.OBSERVABLE_TAPS and all(
        first[index] < first[index + 1] for index in range(bfe1_frontend.OBSERVABLE_TAPS - 1)
    )
    return {"first_rise_ps": first, "all_taps_crossed": len(finite) == bfe1_frontend.OBSERVABLE_TAPS, "strictly_monotonic": ordered}


def analyze_scenario(scenario: Mapping[str, Any]) -> Tuple[Dict[str, Any], Mapping[str, Any]]:
    """Produce all piecewise-constant spatial intervals for one saved .tr0."""

    scenario_id = str(scenario["scenario_id"])
    directory = RUN_ROOT / "scenarios" / scenario_id.lower().replace("-", "_")
    trace = bfe1_frontend.parse_ascii_tr0(directory / "bfe1.tr0")
    all_crossings = {}
    boundaries = [0.0, STOP_PS - LAUNCH_PS]
    for index in range(bfe1_frontend.OBSERVABLE_TAPS):
        node = "xor_{}".format(index)
        crossings = crossing_events(trace, node)
        all_crossings[node] = crossings
        boundaries.extend(crossings["rise_ps"])
        boundaries.extend(crossings["fall_ps"])
    boundaries = unique_boundaries(boundaries)
    intervals = []
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        if right - left <= EPSILON_PS:
            continue
        interval = snapshot(trace, (left + right) / 2.0)
        interval.update({
            "interval_start_ps": left,
            "interval_end_ps": right,
            "interval_width_ps": right - left,
        })
        intervals.append(interval)
    return {
        "scenario_id": scenario_id,
        "baseline_v": scenario["baseline_v"], "droop_v": scenario["droop_v"], "phase_ps": scenario["phase_ps"],
        "bit_order": "raw_code leftmost character is tap_0; rightmost is tap_29",
        "xor_crossings": all_crossings,
        "rvt_monotonicity": path_monotonicity(trace, "rvt"),
        "lvt_monotonicity": path_monotonicity(trace, "lvt"),
        "intervals": intervals,
    }, trace


def pairwise(normal: Mapping[str, Any], normal_trace: Mapping[str, Any], droop: Mapping[str, Any], droop_trace: Mapping[str, Any]) -> Dict[str, Any]:
    """Compare a normal/L2 pair only on their shared physical time segments."""

    boundaries = [0.0, STOP_PS - LAUNCH_PS]
    for scenario in (normal, droop):
        for crossing in scenario["xor_crossings"].values():
            boundaries.extend(crossing["rise_ps"])
            boundaries.extend(crossing["fall_ps"])
    boundaries = unique_boundaries(boundaries)
    records = []
    candidates = []
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        if right - left <= EPSILON_PS:
            continue
        sample_ps = (left + right) / 2.0
        normal_code = snapshot(normal_trace, sample_ps)
        droop_code = snapshot(droop_trace, sample_ps)
        record = {
            "interval_start_ps": left, "interval_end_ps": right, "interval_width_ps": right - left,
            "normal": normal_code, "l2": droop_code,
            "delta_start": None if normal_code["start"] is None or droop_code["start"] is None else droop_code["start"] - normal_code["start"],
            "delta_end": None if normal_code["end"] is None or droop_code["end"] is None else droop_code["end"] - normal_code["end"],
            "delta_len": droop_code["len"] - normal_code["len"],
            "delta_center": None if normal_code["center"] is None or droop_code["center"] is None else droop_code["center"] - normal_code["center"],
            "hamming_distance": sum(left_bit != right_bit for left_bit, right_bit in zip(normal_code["raw_code"], droop_code["raw_code"])),
        }
        stable = normal_code["undefined_bit_count"] == 0 and droop_code["undefined_bit_count"] == 0
        nonempty = not normal_code["empty"] and not droop_code["empty"]
        interior = nonempty and not normal_code["touches_left"] and not normal_code["touches_right"] and not droop_code["touches_left"] and not droop_code["touches_right"]
        descriptive_change = any(record[key] not in (None, 0) for key in ("delta_start", "delta_end", "delta_len", "delta_center"))
        record["common_discrimination_platform"] = stable and interior and record["hamming_distance"] > 0 and descriptive_change
        records.append(record)
        if record["common_discrimination_platform"]:
            candidates.append(record)
    largest = max(candidates, key=lambda item: item["interval_width_ps"]) if candidates else None
    any_different = any(item["hamming_distance"] > 0 for item in records)
    return {
        "baseline_v": normal["baseline_v"], "normal_scenario": normal["scenario_id"], "l2_scenario": droop["scenario_id"],
        "common_segments": records, "candidate_platforms": candidates, "largest_platform": largest,
        "any_different_raw_code": any_different,
    }


def decide_gate(pair_results: Sequence[Mapping[str, Any]], scenarios: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Apply the plan's GO/CONDITIONAL/BLOCKED definitions without tuning data."""

    clean_pairs = [item for item in pair_results if item["candidate_platforms"]]
    any_spatial = any(any(not interval["empty"] for interval in scenario["intervals"]) for scenario in scenarios)
    monotonic = all(
        scenario["rvt_monotonicity"]["strictly_monotonic"] and scenario["lvt_monotonicity"]["strictly_monotonic"] for scenario in scenarios
    )
    if len(clean_pairs) == 2 and monotonic:
        decision = "BFE1_SPATIAL_OBSERVABILITY_GO"
        reason = "both formal baselines have a positive-width, interior, stable common discrimination platform"
    elif any_spatial and any(item["any_different_raw_code"] for item in pair_results):
        decision = "BFE1_SPATIAL_OBSERVABILITY_CONDITIONAL"
        reason = "spatial code movement exists, but at least one formal baseline lacks a clean common platform or a path monotonicity diagnostic failed"
    else:
        decision = "BFE1_SPATIAL_OBSERVABILITY_BLOCKED"
        reason = "no qualifying spatial discrimination mechanism is present in the completed four-scenario matrix"
    return {
        "schema_version": 1, "stage": "B-FE1", "gate": decision, "reason": reason,
        "clean_pair_count": len(clean_pairs), "pair_count": len(pair_results), "all_path_monotonic": monotonic,
        "new_hspice_scenarios": 4, "forbidden_work_performed": False,
    }


def plot_spatial_code(scenario: Mapping[str, Any], output: Path) -> None:
    """Draw one paper-ready time-by-tap raw-code image from saved intervals.

    Each interval is a *vertical* 30-bit stripe: the horizontal extent is its
    physical crossing-to-crossing time range and row ``i`` is physical tap
    ``i``.  Empty pre-launch and post-wavefront intervals remain in JSON but
    are deliberately excluded from this presentation window; otherwise the
    6-ns simulation tail would visually compress the useful sub-ns code into
    a few pixels and obscure the very code this figure is intended to show.
    """

    intervals = scenario["intervals"]
    active_intervals = [item for item in intervals if not item["empty"]]
    if not active_intervals:
        raise ValueError("B-FE1 spatial-code figure requires at least one non-empty interval")
    active_start = active_intervals[0]["interval_start_ps"]
    active_end = active_intervals[-1]["interval_end_ps"]
    # A small, data-derived margin exposes the first and final crossing edges
    # without introducing an arbitrary sampling grid or hiding any interval.
    horizontal_padding = max((active_end - active_start) * 0.02, 1.0)
    figure, axis = plt.subplots(figsize=(8.0, 3.2))
    for interval in intervals:
        # ``imshow`` consumes rows as y coordinates.  A list of singleton
        # rows therefore maps bit[i] onto tap i; the earlier one-row form
        # accidentally mapped the 30 bits across time and made the plot blank.
        tap_rows = [[int(bit)] for bit in interval["raw_code"]]
        axis.imshow(tap_rows, aspect="auto", interpolation="nearest", cmap="Blues", vmin=0, vmax=1,
                    origin="lower", extent=[interval["interval_start_ps"], interval["interval_end_ps"], -0.5, 29.5])
    axis.set_title("{} spatial RAW_CODE (active wavefront window)".format(scenario["scenario_id"]))
    axis.set_xlabel("launch-relative Tsample (ps)")
    axis.set_ylabel("tap index")
    axis.set_xlim(active_start - horizontal_padding, active_end + horizontal_padding)
    axis.set_ylim(-0.5, 29.5)
    axis.set_yticks(range(0, 30, 5))
    figure.tight_layout()
    figure.savefig(str(output), dpi=220)
    plt.close(figure)


def plot_metrics(scenarios: Sequence[Mapping[str, Any]], output: Path) -> None:
    """Plot START/END/LEN/CENTER trajectories using interval midpoints only."""

    figure, axes = plt.subplots(2, 2, figsize=(9.0, 5.8), sharex=True)
    fields = (("start", "START"), ("end", "END"), ("len", "LEN"), ("center", "CENTER"))
    for scenario in scenarios:
        sample = [(item["interval_start_ps"] + item["interval_end_ps"]) / 2.0 for item in scenario["intervals"]]
        for axis, (field, label) in zip(axes.flat, fields):
            values = [item[field] if item[field] is not None else math.nan for item in scenario["intervals"]]
            axis.step(sample, values, where="mid", label=scenario["scenario_id"])
            axis.set_ylabel(label)
    for axis in axes.flat:
        axis.grid(True, alpha=0.25)
    axes[-1][0].set_xlabel("launch-relative Tsample (ps)")
    axes[-1][1].set_xlabel("launch-relative Tsample (ps)")
    axes[0][0].legend(fontsize=7)
    figure.tight_layout()
    figure.savefig(str(output), dpi=220)
    plt.close(figure)


def plot_platforms(pair_results: Sequence[Mapping[str, Any]], output: Path) -> None:
    """Draw all candidate common platforms; no single preferred point is hidden."""

    figure, axis = plt.subplots(figsize=(8.0, 2.8))
    for row, pair in enumerate(pair_results):
        for candidate in pair["candidate_platforms"]:
            axis.barh(row, candidate["interval_width_ps"], left=candidate["interval_start_ps"], height=0.55)
        axis.text(0.0, row + 0.32, "{} V".format(pair["baseline_v"]), fontsize=8)
    axis.set_yticks(range(len(pair_results)))
    axis.set_yticklabels(["{} normal/L2".format(pair["baseline_v"]) for pair in pair_results])
    axis.set_xlabel("launch-relative common platform (ps)")
    axis.set_title("All B-FE1 common discrimination platforms")
    axis.grid(True, axis="x", alpha=0.25)
    figure.tight_layout()
    figure.savefig(str(output), dpi=220)
    plt.close(figure)


def report(gate: Mapping[str, Any], pairs: Sequence[Mapping[str, Any]]) -> str:
    """Render the review summary without hiding any selected platform detail.

    The JSON products remain the complete record: every crossing interval and
    every qualifying platform is retained there.  This Markdown companion
    reports the count and the widest member of each full candidate set so a
    reviewer can see both the physical time range and the two raw words
    without mistaking the summary for a hand-picked single-point result.
    """

    lines = [
        "# B-FE1 多抽头空间可观测性报告", "", "## Gate", "",
        "**{}**".format(gate["gate"]), "", gate["reason"], "",
        "四个正式 transient 场景均只运行一次；每个保存的 `.tr0` 严格包含 `TIME + 92` 个计划定义观测项。", "",
        "## 共同判别平台", "",
        "| Baseline | 候选数 | 最大平台范围 (launch-relative ps) | 宽度 (ps) | normal RAW_CODE | L2 RAW_CODE |",
        "|---:|---:|---:|---:|---|---|",
    ]
    for pair in pairs:
        largest = pair["largest_platform"]
        if largest is None:
            lines.append("| {:.2f} | {} |  |  |  |  |".format(float(pair["baseline_v"]), len(pair["candidate_platforms"])))
            continue
        lines.append(
            "| {:.2f} | {} | {:.6f}–{:.6f} | {:.6f} | `{}` | `{}` |".format(
                float(pair["baseline_v"]), len(pair["candidate_platforms"]),
                largest["interval_start_ps"], largest["interval_end_ps"], largest["interval_width_ps"],
                largest["normal"]["raw_code"], largest["l2"]["raw_code"],
            )
        )
    lines.extend([
        "", "全部 crossing、原始码区间、成对分段和平台均保存在相邻 JSON；六张图由这些 JSON 自动生成。",
        "本阶段未实例化 latch、M/F、DFF、控制器，也未运行 PVT、Monte Carlo、全 phase 或重复 probe。",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    """Run complete zero-HSPICE B-FE1 post-processing and figure generation."""

    manifest = read_json(OUTPUT_ROOT / "scenario_manifest.json")
    if manifest.get("hspice_scenarios") != 4:
        raise ValueError("B-FE1 analysis requires exactly four completed scenarios")
    scenarios = []
    traces = {}
    for item in manifest["scenarios"]:
        scenario, trace = analyze_scenario(item)
        scenarios.append(scenario)
        traces[scenario["scenario_id"]] = trace
    by_id = {item["scenario_id"]: item for item in scenarios}
    pairs = [
        pairwise(by_id["BFE1-095-N"], traces["BFE1-095-N"], by_id["BFE1-095-L2"], traces["BFE1-095-L2"]),
        pairwise(by_id["BFE1-110-N"], traces["BFE1-110-N"], by_id["BFE1-110-L2"], traces["BFE1-110-L2"]),
    ]
    gate = decide_gate(pairs, scenarios)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "waveform_crossings.json").write_text(json.dumps({"scenarios": [{key: value for key, value in item.items() if key != "intervals"} for item in scenarios]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_ROOT / "spatial_code_intervals.json").write_text(json.dumps({"scenarios": scenarios}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_ROOT / "normal_l2_pairwise_discrimination.json").write_text(json.dumps({"pairs": pairs}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_ROOT / "BFE1_GATE_STATUS.json").write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUTPUT_ROOT / "BFE1_SPATIAL_OBSERVABILITY_REPORT.md").write_text(report(gate, pairs), encoding="utf-8")
    figures = OUTPUT_ROOT / "figures"
    figures.mkdir(exist_ok=True)
    for scenario in scenarios:
        plot_spatial_code(scenario, figures / "{}_spatial_code.png".format(scenario["scenario_id"].lower()))
    plot_metrics(scenarios, figures / "spatial_metrics.png")
    plot_platforms(pairs, figures / "common_discrimination_platforms.png")
    print("{} zero_hspice_analysis=PASS".format(gate["gate"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
