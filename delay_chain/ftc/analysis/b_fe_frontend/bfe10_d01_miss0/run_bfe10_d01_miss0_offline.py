#!/usr/bin/env python3
"""BFE10-D01-MISS0 retained-artifact mechanism audit.

This program is intentionally an offline parser.  It reads only the frozen
BFE8 healthy/D02 records and the frozen BFE9 D01 records, then writes all
derived evidence into its own analysis directory.  It never invokes HSPICE,
PrimeSim, VCS, DC, STA, P&R, or any other simulator, and it never edits the
production RTL or the BFE8/BFE9 authority files.

The two generated figures are diagnostic evidence, not new operating points:
the scalar sweep is a sensitivity analysis over retained samples and must not
be used to select a replacement margin.
"""

import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend"
BFE8_ROOT = ANALYSIS_ROOT / "bfe8_d02_arch0_pilot"
BFE9_ROOT = ANALYSIS_ROOT / "bfe9_d01_arch0_amplitude_sensitivity"
BFE8_RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe8_d02_arch0_pilot"
BFE9_RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe9_d01_arch0_amplitude_sensitivity"

SEEDS = tuple(range(41001, 41031))
MISS_SEEDS = (41005, 41007, 41012, 41015, 41016, 41022, 41025, 41028)
MARGIN_RISE = 22
MARGIN_FALL = 24
TARGET_INDEX = 2
TARGET_EVENT = "21 ns RISE"
Q_WIDTH = 30
M_MAX = sum(range(Q_WIDTH))


def sha256(path):
    """Return a file digest without mutating or rewriting the source file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Load one retained JSON object and fail closed on a malformed record."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def read_csv(path):
    """Read a retained CSV into dictionaries while preserving string fields."""
    with path.open(newline="", encoding="ascii") as stream:
        return list(csv.DictReader(stream))


def q_bits(q_ff, label):
    """Decode the repository's tap-0..29 q_ff string into integer bits.

    BFE8/BFE9 serialize q_ff by joining the list in tap order.  Consequently
    character zero is tap 0, character 29 is tap 29, and the weighted feature
    is exactly ``sum(tap_index * bit)``.  The explicit checks prevent a silent
    reversal of the 30-bit word from contaminating Hamming or Delta-M results.
    """
    if not isinstance(q_ff, str) or len(q_ff) != Q_WIDTH or any(bit not in "01" for bit in q_ff):
        raise ValueError("{} is not a 30-bit binary q_ff string".format(label))
    return [int(bit) for bit in q_ff]


def weighted_m(bits):
    """Recompute the ARCH0 M feature from tap bits without introducing RTL."""
    return sum(index * bit for index, bit in enumerate(bits))


def diff_metrics(healthy_bits, attack_bits):
    """Return Hamming, changed taps, signed Delta-M, and optional N delta."""
    changed = [index for index, (healthy, attack) in enumerate(zip(healthy_bits, attack_bits)) if healthy != attack]
    delta_m = sum(index * (attack_bits[index] - healthy_bits[index]) for index in range(Q_WIDTH))
    return {
        "hamming": len(changed),
        "changed_taps": changed,
        "delta_m": delta_m,
        "delta_n": sum(attack_bits) - sum(healthy_bits),
    }


def load_authority():
    """Load and cross-check every retained row needed by the audit.

    The checks intentionally include process signatures, target identity,
    frozen references, margins, and q_ff/M consistency.  This makes the
    mechanism report a reparse of frozen evidence rather than a second source
    of silently regenerated values.
    """
    healthy_rows = {int(row["seed"]): row for row in read_csv(BFE8_ROOT / "BFE8_HEALTHY_PER_SEED.csv")}
    d01_rows = {int(row["seed"]): row for row in read_csv(BFE9_ROOT / "BFE9_D01_PER_SEED.csv")}
    d02_rows = {int(row["seed"]): row for row in read_csv(BFE8_ROOT / "BFE8_D02_PER_SEED.csv")}
    if set(healthy_rows) != set(SEEDS) or set(d01_rows) != set(SEEDS) or set(d02_rows) != set(SEEDS):
        raise ValueError("retained BFE8/BFE9 population is not exactly seeds 41001..41030")
    if tuple(sorted(int(row["seed"]) for row in read_csv(BFE9_ROOT / "BFE9_D01_D02_PAIRED.csv"))) != SEEDS:
        raise ValueError("BFE9 paired CSV is not a complete 30-seed population")
    for seed in SEEDS:
        if healthy_rows[seed]["mc_random_signature"] != d01_rows[seed]["mc_random_signature"]:
            raise ValueError("healthy/D01 process signature mismatch for seed {}".format(seed))
        if healthy_rows[seed]["mc_random_signature"] != d02_rows[seed]["mc_random_signature"]:
            raise ValueError("healthy/D02 process signature mismatch for seed {}".format(seed))
        if d01_rows[seed]["target_event"] != TARGET_EVENT or d02_rows[seed]["target_event"] != TARGET_EVENT:
            raise ValueError("target event mismatch for seed {}".format(seed))
        if int(d01_rows[seed]["locked_rise_margin"]) != MARGIN_RISE or int(d02_rows[seed]["locked_rise_margin"]) != MARGIN_RISE:
            raise ValueError("RISE margin changed for seed {}".format(seed))
        if int(d01_rows[seed]["locked_fall_margin"]) != MARGIN_FALL or int(d02_rows[seed]["locked_fall_margin"]) != MARGIN_FALL:
            raise ValueError("FALL margin changed for seed {}".format(seed))
    return healthy_rows, d01_rows, d02_rows


def target_event(case_path, label):
    """Return target event 2 from a retained raw case after identity checks."""
    case = read_json(case_path)
    if case.get("target_event_index") not in (None, TARGET_INDEX):
        raise ValueError("{} target index is not 2: {}".format(label, case_path))
    events = case.get("events", [])
    if len(events) <= TARGET_INDEX:
        raise ValueError("{} has no event index 2: {}".format(label, case_path))
    event = events[TARGET_INDEX]
    if event.get("event_index") != TARGET_INDEX or event.get("edge") != "RISE":
        raise ValueError("{} event index 2 is not RISE: {}".format(label, case_path))
    return event, case


def load_raw_targets(healthy_rows, d01_rows, d02_rows):
    """Read target q_ff vectors and all healthy RISE events from task-local raw cases."""
    targets = {}
    healthy_rise = []
    for seed in SEEDS:
        healthy_case = read_json(BFE8_RUN_ROOT / "healthy" / "seed_{:05d}".format(seed) / "HEALTHY_CASE.json")
        d01_event, d01_case = target_event(BFE9_RUN_ROOT / "d01" / "seed_{:05d}".format(seed) / "D01_CASE.json", "D01")
        d02_event, d02_case = target_event(BFE8_RUN_ROOT / "d02" / "seed_{:05d}".format(seed) / "D02_CASE.json", "D02")
        signature = healthy_rows[seed]["mc_random_signature"]
        if healthy_case.get("mc_random_signature") != signature or d01_case.get("mc_random_signature") != signature or d02_case.get("mc_random_signature") != signature:
            raise ValueError("raw process signature mismatch for seed {}".format(seed))
        healthy_events = healthy_case["events"]
        rise_events = [event for event in healthy_events if event.get("edge") == "RISE"]
        if len(rise_events) != 12:
            raise ValueError("healthy seed {} does not contain 12 RISE events".format(seed))
        ref = int(healthy_rows[seed]["M_REF_RISE"])
        for event in rise_events:
            bits = q_bits(event["q_ff"], "healthy seed {} event {}".format(seed, event["event_index"]))
            if int(event["m_ff"]) != weighted_m(bits):
                raise ValueError("healthy M/q_ff mismatch for seed {} event {}".format(seed, event["event_index"]))
            healthy_rise.append({"seed": seed, "event_index": int(event["event_index"]), "m_ff": int(event["m_ff"]),
                                "m_ref_rise": ref, "d_m": abs(int(event["m_ff"]) - ref), "q_ff": event["q_ff"]})
        for label, event in (("D01", d01_event), ("D02", d02_event)):
            bits = q_bits(event["q_ff"], "{} seed {} target".format(label, seed))
            m_field = int(event.get("M_FF", event.get("m_ff")))
            if m_field != weighted_m(bits) or not 0 <= m_field <= M_MAX:
                raise ValueError("{} M/q_ff mismatch or range error for seed {}".format(label, seed))
        targets[seed] = {"healthy": healthy_events[TARGET_INDEX], "d01": d01_event, "d02": d02_event}
    return targets, healthy_rise


def threshold_sweep(healthy_rise, d01_values):
    """Evaluate diagnostic scalar thresholds without changing locked margin."""
    rows = []
    healthy_count = len(healthy_rise)
    for threshold in range(M_MAX + 1):
        healthy_false = sum(int(sample["d_m"] > threshold) for sample in healthy_rise)
        d01_detected = sum(int(value > threshold) for value in d01_values)
        rows.append({"threshold_T": threshold, "rule": "D_M > T", "healthy_rise_samples": healthy_count,
                     "healthy_rise_false_alarms": healthy_false, "healthy_rise_false_alarm_rate": healthy_false / float(healthy_count),
                     "d01_samples": len(d01_values), "d01_detected": d01_detected,
                     "d01_coverage": d01_detected / float(len(d01_values)),
                     "simulator_calls": 0, "margin_selection": "diagnostic_only"})
    return rows


def classify(row):
    """Assign evidence-based mechanism labels to one D01 MISS."""
    scalar_overlap = row["d01_d_m"] <= row["healthy_rise_max_d_m"]
    spatial_compression = row["d01_hamming"] < row["d02_hamming"] and row["d01_abs_delta_m"] < row["d02_abs_delta_m"]
    labels = []
    if scalar_overlap:
        labels.append("SCALAR_THRESHOLD_OVERLAP")
    if spatial_compression:
        labels.append("SPATIAL_COMPRESSION_LOSS")
    if not labels:
        labels.append("UNRESOLVED_FROM_RETAINED_Q_FF")
    return "+".join(labels), scalar_overlap, spatial_compression


def write_csv(path, rows):
    """Write a deterministic ASCII evidence table with the row schema visible."""
    if not rows:
        raise ValueError("cannot write empty evidence table: {}".format(path))
    with path.open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def make_figures(healthy_rise, d01_values, d02_values, miss_rows):
    """Create the two compact grayscale SCI-style diagnostic figures."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm

    plt.rcParams.update({"font.family": "serif", "font.size": 9, "axes.linewidth": 0.8})
    figure_dir = ROOT
    # Figure 1: same D_M quantity, with the frozen 22-code operating point
    # shown only as a reference line.  No new margin is selected from this plot.
    fig, ax = plt.subplots(figsize=(7.0, 3.8))
    bins = np.arange(-0.5, max(max(d01_values), max(d02_values), max(sample["d_m"] for sample in healthy_rise)) + 1.5, 1.0)
    ax.hist([sample["d_m"] for sample in healthy_rise], bins=bins, color="white", edgecolor="black", linewidth=0.8,
            histtype="stepfilled", label="Healthy RISE (n=360)")
    ax.hist(d01_values, bins=bins, color="0.58", edgecolor="0.15", linewidth=0.8, histtype="step", label="D01 30 mV (n=30)")
    ax.hist(d02_values, bins=bins, color="0.15", edgecolor="0.15", linewidth=0.8, histtype="step", label="D02 60 mV (n=30)")
    ax.axvline(MARGIN_RISE, color="0.25", linestyle="--", linewidth=0.9, label="Frozen RISE margin 22")
    ax.set_xlabel("D_M = |M_FF - M_REF_RISE| (M-codes)")
    ax.set_ylabel("Retained sample count")
    ax.set_xlim(-0.5, max(bins))
    ax.grid(True, axis="y", color="0.88", linewidth=0.5)
    ax.legend(frameon=False, ncol=2, loc="upper left")
    fig.tight_layout()
    fig.savefig(figure_dir / "BFE10_D01_D_M_DISTRIBUTIONS.png", dpi=220)
    fig.savefig(figure_dir / "BFE10_D01_D_M_DISTRIBUTIONS.pdf")
    plt.close(fig)

    # Figure 2: signed D01-minus-healthy tap differences.  Dark gray means
    # 0->1, mid gray means 1->0, and white means unchanged; this avoids a
    # rainbow palette while retaining direction for every changed tap.
    matrix = np.array([[int(bit) for bit in row["d01_diff_vector"].split(";")] for row in miss_rows], dtype=float)
    cmap = LinearSegmentedColormap.from_list("signed_gray", ["#666666", "#ffffff", "#111111"], N=3)
    norm = BoundaryNorm([-1.5, -0.5, 0.5, 1.5], cmap.N)
    fig, ax = plt.subplots(figsize=(8.0, 2.8))
    image = ax.imshow(matrix, aspect="auto", interpolation="nearest", cmap=cmap, norm=norm)
    ax.set_xlabel("Tap index (q_ff character index, tap 0..29)")
    ax.set_ylabel("D01 MISS seed")
    ax.set_xticks(np.arange(Q_WIDTH))
    ax.set_yticks(np.arange(len(miss_rows)))
    ax.set_yticklabels([row["seed"] for row in miss_rows])
    ax.set_xticks(np.arange(-0.5, Q_WIDTH, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(miss_rows), 1), minor=True)
    ax.grid(which="minor", color="0.82", linewidth=0.35)
    ax.tick_params(which="minor", bottom=False, left=False)
    colorbar = fig.colorbar(image, ax=ax, ticks=[-1, 0, 1], pad=0.02)
    colorbar.ax.set_yticklabels(["1->0", "unchanged", "0->1"])
    colorbar.set_label("D01 attack minus healthy bit")
    fig.tight_layout()
    fig.savefig(figure_dir / "BFE10_D01_MISS_SPATIAL_HEATMAP.png", dpi=220)
    fig.savefig(figure_dir / "BFE10_D01_MISS_SPATIAL_HEATMAP.pdf")
    plt.close(fig)


def main():
    """Perform the complete retained-data audit and publish the final gate."""
    ROOT.mkdir(parents=True, exist_ok=True)
    healthy_rows, d01_rows, d02_rows = load_authority()
    targets, healthy_rise = load_raw_targets(healthy_rows, d01_rows, d02_rows)
    healthy_values = [sample["d_m"] for sample in healthy_rise]
    healthy_max = max(healthy_values)
    d01_values = [abs(int(targets[seed]["d01"].get("M_FF", targets[seed]["d01"].get("m_ff"))) - int(healthy_rows[seed]["M_REF_RISE"])) for seed in SEEDS]
    d02_values = [abs(int(targets[seed]["d02"].get("M_FF", targets[seed]["d02"].get("m_ff"))) - int(healthy_rows[seed]["M_REF_RISE"])) for seed in SEEDS]
    sweep = threshold_sweep(healthy_rise, d01_values)
    full_d01 = [row for row in sweep if row["d01_detected"] == len(SEEDS)]
    zero_healthy = [row for row in sweep if row["healthy_rise_false_alarms"] == 0]
    intersection = [row for row in sweep if row["d01_detected"] == len(SEEDS) and row["healthy_rise_false_alarms"] == 0]
    if min(d01_values) != 20 or healthy_max != 22 or intersection:
        raise AssertionError("retained scalar-boundary result changed unexpectedly")

    miss_rows = []
    for seed in MISS_SEEDS:
        healthy_bits = q_bits(targets[seed]["healthy"]["q_ff"], "healthy target seed {}".format(seed))
        d01_bits = q_bits(targets[seed]["d01"]["q_ff"], "D01 target seed {}".format(seed))
        d02_bits = q_bits(targets[seed]["d02"]["q_ff"], "D02 target seed {}".format(seed))
        d01_diff = diff_metrics(healthy_bits, d01_bits)
        d02_diff = diff_metrics(healthy_bits, d02_bits)
        d01_m = weighted_m(d01_bits)
        d02_m = weighted_m(d02_bits)
        ref = int(healthy_rows[seed]["M_REF_RISE"])
        row = {
            "seed": seed, "mc_random_signature": healthy_rows[seed]["mc_random_signature"],
            "M_REF_RISE": ref, "healthy_M_FF": weighted_m(healthy_bits), "D01_M_FF": d01_m, "D02_M_FF": d02_m,
            "healthy_D_M": abs(weighted_m(healthy_bits) - ref), "d01_d_m": abs(d01_m - ref), "d02_d_m": abs(d02_m - ref),
            "d01_h_d": abs(d01_m - ref) - MARGIN_RISE, "d01_detected_at_locked_margin": int(abs(d01_m - ref) > MARGIN_RISE),
            "d01_hamming": d01_diff["hamming"], "d01_changed_taps": ";".join(map(str, d01_diff["changed_taps"])),
            "d01_diff_vector": ";".join(str(d01_bits[index] - healthy_bits[index]) for index in range(Q_WIDTH)),
            "d01_delta_m": d01_diff["delta_m"], "d01_abs_delta_m": abs(d01_diff["delta_m"]),
            "healthy_N": sum(healthy_bits), "d01_N": sum(d01_bits), "d01_delta_n": d01_diff["delta_n"],
            "d02_hamming": d02_diff["hamming"], "d02_changed_taps": ";".join(map(str, d02_diff["changed_taps"])),
            "d02_delta_m": d02_diff["delta_m"], "d02_abs_delta_m": abs(d02_diff["delta_m"]),
            "d02_N": sum(d02_bits), "q_ff_healthy": targets[seed]["healthy"]["q_ff"],
            "q_ff_d01": targets[seed]["d01"]["q_ff"], "q_ff_d02": targets[seed]["d02"]["q_ff"],
            "healthy_rise_max_d_m": healthy_max,
        }
        mechanism, scalar_overlap, spatial_compression = classify(row)
        row["scalar_threshold_overlap"] = int(scalar_overlap)
        row["spatial_compression_loss"] = int(spatial_compression)
        row["frontend_low_observability"] = "NOT_SEPARATELY_IDENTIFIABLE_FROM_Q_FF_ONLY"
        row["mechanism_class"] = mechanism
        miss_rows.append(row)

    if any(int(row["d01_detected_at_locked_margin"]) != 0 for row in miss_rows):
        raise AssertionError("MISS set no longer matches frozen D01 verdicts")
    if any(row["d01_hamming"] != 1 for row in miss_rows):
        raise AssertionError("expected one-tap D01 compression pattern is absent")

    write_csv(ROOT / "BFE10_D01_MISS_MECHANISM.csv", miss_rows)
    write_csv(ROOT / "BFE10_D01_SCALAR_THRESHOLD_SWEEP.csv", sweep)
    make_figures(healthy_rise, d01_values, d02_values, miss_rows)

    stats = {
        "input_authority_sha256": {
            "BFE8_HEALTHY_PER_SEED.csv": sha256(BFE8_ROOT / "BFE8_HEALTHY_PER_SEED.csv"),
            "BFE8_D02_PER_SEED.csv": sha256(BFE8_ROOT / "BFE8_D02_PER_SEED.csv"),
            "BFE9_D01_PER_SEED.csv": sha256(BFE9_ROOT / "BFE9_D01_PER_SEED.csv"),
            "BFE9_D01_D02_PAIRED.csv": sha256(BFE9_ROOT / "BFE9_D01_D02_PAIRED.csv"),
            "BFE8_D02_GATE.json": sha256(BFE8_ROOT / "BFE8_D02_GATE.json"),
            "BFE9_D01_GATE.json": sha256(BFE9_ROOT / "BFE9_D01_GATE.json"),
        },
        "sample_count": {"healthy_rise": len(healthy_values), "d01_target": len(d01_values), "d02_target": len(d02_values)},
        "D_M": {
            "healthy_rise": {"min": min(healthy_values), "median": float(np.median(healthy_values)), "max": max(healthy_values), "counts": dict(sorted(Counter(healthy_values).items()))},
            "d01_target": {"min": min(d01_values), "median": float(np.median(d01_values)), "max": max(d01_values), "counts": dict(sorted(Counter(d01_values).items()))},
            "d02_target": {"min": min(d02_values), "median": float(np.median(d02_values)), "max": max(d02_values), "counts": dict(sorted(Counter(d02_values).items()))},
        },
        "scalar_threshold_sweep": {
            "rule": "alarm iff D_M > T",
            "diagnostic_only": True,
            "locked_margin_unchanged": {"rise": MARGIN_RISE, "fall": MARGIN_FALL},
            "healthy_rise_zero_false_alarm_thresholds": [row["threshold_T"] for row in zero_healthy],
            "d01_full_coverage_thresholds": [row["threshold_T"] for row in full_d01],
            "intersection_thresholds": [row["threshold_T"] for row in intersection],
            "result": "NO_SINGLE_THRESHOLD",
            "reason": "D01 full coverage requires T <= 19, while zero healthy RISE false alarms requires T >= 22.",
        },
        "miss_population": {
            "seeds": list(MISS_SEEDS), "count": len(miss_rows),
            "d01_hamming_distribution": dict(sorted(Counter(row["d01_hamming"] for row in miss_rows).items())),
            "d02_hamming_distribution": dict(sorted(Counter(row["d02_hamming"] for row in miss_rows).items())),
            "d01_changed_tap_union": sorted({tap for row in miss_rows for tap in map(int, filter(None, row["d01_changed_taps"].split(";")))}),
        },
        "mechanism_conclusion": {
            "classification": "MIXED_SCALAR_THRESHOLD_OVERLAP+SPATIAL_COMPRESSION_LOSS",
            "scalar_threshold_overlap": "D01 D_M values 20..22 overlap the healthy RISE retained maximum of 22.",
            "spatial_compression_loss": "Every MISS has one D01 changed tap, versus two or three changed taps for matched D02.",
            "frontend_low_observability": "A q_ff-only audit cannot isolate analog internal frontend loss; the retained evidence supports an output-level one-tap observability compression, not a separate causal claim.",
        },
        "simulation_accounting": {"HSPICE": 0, "VCS": 0, "PrimeSim": 0, "DC": 0},
    }
    (ROOT / "BFE10_D01_MISS_MECHANISM.json").write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = [
        "# BFE10-D01-MISS0：D01 ARCH0 MISS 机制离线审计", "",
        "最终 gate：`BFE10_D01_ARCH0_MISS_MECHANISM_FROZEN`", "",
        "本报告只读取冻结的 BFE8/BFE9 retained artifacts。没有启动 HSPICE、VCS、PrimeSim 或 DC；没有修改 production RTL、frontend、波形、30-seed population、reference、margin 或 ARCH1。", "",
        "## 1. 标量 D_M 分布与诊断 sweep", "",
        "健康 RISE retained 样本为 360 个，D01 target 为 30 个，D02 target 为 30 个。健康 RISE 的 D_M 范围为 {}..{}，D01 为 {}..{}，D02 为 {}..{}。".format(min(healthy_values), max(healthy_values), min(d01_values), max(d01_values), min(d02_values), max(d02_values)),
        "诊断规则为 `alarm iff D_M > T`，仅用于 retained sample sensitivity，不改变锁定的 RISE=22/FALL=24 margin。D01 全覆盖需要 `T <= 19`；健康 RISE 零观测误报需要 `T >= 22`；交集为空，因此不存在可同时满足两者的单一 scalar threshold。", "",
        "## 2. 八个 MISS 的空间审计", "",
        "| Seed | D01 D_M | H_D | D01 Hamming | D01 changed taps | ΔM D01 | D02 Hamming | ΔM D02 | 机制 |", "|---:|---:|---:|---:|:---|---:|---:|---:|:---|",
    ]
    for row in miss_rows:
        report.append("| {seed} | {d01_d_m} | {d01_h_d} | {d01_hamming} | {d01_changed_taps} | {d01_delta_m:+d} | {d02_hamming} | {d02_delta_m:+d} | {mechanism_class} |".format(**row))
    report += [
        "", "八个 MISS 的 D01 q_ff 相对同 seed healthy RISE 均只改变一个 tap：41005/41007/41012/41015/41022/41028 为 tap 21，41016 为 tap 22，41025 为 tap 20。D01 的 `N=sum(q)` 增量均为 +1，D01 `ΔM` 为 +20/+21/+22；匹配的 D02 target 改变 2～3 个 taps，产生更大的 `|ΔM|`。", "",
        "## 3. 机制结论", "",
        "结论为混合机制：`SCALAR_THRESHOLD_OVERLAP + SPATIAL_COMPRESSION_LOSS`。标量层面，D01 的 20..22 M-code 信号与健康 RISE 的最大 D_M=22 重叠；空间层面，30 mV D01 在这些 process instances 只保留一个高位 tap 的输出变化，而 60 mV D02 保留两个或三个 tap 变化。", 
        "`FRONTEND_LOW_OBSERVABILITY` 在本审计中不能作为独立模拟因果机制从 q_ff-only retained evidence 中分离出来。证据支持的是 frontend 输出端的低空间可观测性/压缩现象；没有内部模拟节点或新增仿真，不能进一步断言具体晶体管级原因。", "",
        "MISS 是 sensor/detector observability miss，不是 timing fault 结论；本报告也不据两种 amplitude 推导连续 minimum detectable voltage，不重新选择 margin，不继续执行 D04，也不实现 ARCH1。", "",
        "仿真 accounting：HSPICE=0，VCS=0，PrimeSim=0，DC=0。",
    ]
    (ROOT / "BFE10_D01_MISS_MECHANISM_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    artifact_names = ["BFE10_D01_MISS_MECHANISM.csv", "BFE10_D01_SCALAR_THRESHOLD_SWEEP.csv", "BFE10_D01_MISS_MECHANISM.json", "BFE10_D01_MISS_MECHANISM_REPORT.md", "BFE10_D01_D_M_DISTRIBUTIONS.png", "BFE10_D01_D_M_DISTRIBUTIONS.pdf", "BFE10_D01_MISS_SPATIAL_HEATMAP.png", "BFE10_D01_MISS_SPATIAL_HEATMAP.pdf"]
    artifact_hashes = {name: sha256(ROOT / name) for name in artifact_names}
    gate = {
        "gate": "BFE10_D01_ARCH0_MISS_MECHANISM_FROZEN", "status": "PASS", "scope": "D01 eight ARCH0 MISS offline mechanism audit",
        "input_authority_sha256": stats["input_authority_sha256"],
        "miss_seeds": list(MISS_SEEDS), "classification": "MIXED_SCALAR_THRESHOLD_OVERLAP+SPATIAL_COMPRESSION_LOSS",
        "single_scalar_threshold_exists": False, "locked_margins": {"M_MARGIN_RISE": 22, "M_MARGIN_FALL": 24},
        "simulation_accounting": {"HSPICE": 0, "VCS": 0, "PrimeSim": 0, "DC": 0},
        "production_rtl_modified": False, "frontend_modified": False, "waveforms_modified": False, "population_modified": False,
        "startup_reference_modified": False, "arch1_modified": False, "no_d04_or_arch1_followup": True,
        "artifact_sha256": artifact_hashes, "stop_after_stage": True,
    }
    (ROOT / "BFE10_D01_GATE.json").write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print("BFE10 D01 MISS0 PASS")


if __name__ == "__main__":
    main()
