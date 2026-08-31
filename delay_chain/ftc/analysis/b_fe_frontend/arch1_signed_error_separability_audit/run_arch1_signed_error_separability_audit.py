#!/usr/bin/env python3
"""Offline ARCH1 signed-error separability audit.

Only retained BFE8/BFE9/BFE10 evidence is read.  The script deliberately has
no simulator subprocess, no RTL writer, and no margin-selection side effect.
The generated ``e > T_POS`` sweep is a diagnostic projection of frozen data;
it is not an authorization to add a signed comparator or to change ARCH0's
formal ``abs(e) > margin`` rule.
"""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend"
BFE8_ROOT = ANALYSIS_ROOT / "bfe8_d02_arch0_pilot"
BFE9_ROOT = ANALYSIS_ROOT / "bfe9_d01_arch0_amplitude_sensitivity"
BFE10_ROOT = ANALYSIS_ROOT / "bfe10_d01_miss0"
ARCH1_CANDIDATE = ANALYSIS_ROOT / "bfe5_arch1_candidate" / "BFE5_ARCH1_CANDIDATE.md"
BFE8_RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe8_d02_arch0_pilot"
BFE9_RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe9_d01_arch0_amplitude_sensitivity"

SEEDS = tuple(range(41001, 41031))
Q_WIDTH = 30
MARGIN_RISE = 22
MARGIN_FALL = 24
TARGET_INDEX = 2
TARGET_EVENT = "21 ns RISE"


def sha256(path):
    """Hash one retained input or generated output without modifying it."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Read a retained JSON object and reject malformed authority data."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def read_csv(path):
    """Read an ASCII retained table into dictionaries."""
    with path.open(newline="", encoding="ascii") as stream:
        return list(csv.DictReader(stream))


def check_authority():
    """Verify frozen BFE8/BFE9/BFE10 gates and collect source hashes."""
    required = {
        "BFE8_D02_GATE.json": BFE8_ROOT / "BFE8_D02_GATE.json",
        "BFE8_HEALTHY_PER_SEED.csv": BFE8_ROOT / "BFE8_HEALTHY_PER_SEED.csv",
        "BFE8_D02_PER_SEED.csv": BFE8_ROOT / "BFE8_D02_PER_SEED.csv",
        "BFE9_D01_GATE.json": BFE9_ROOT / "BFE9_D01_GATE.json",
        "BFE9_D01_PER_SEED.csv": BFE9_ROOT / "BFE9_D01_PER_SEED.csv",
        "BFE9_D01_D02_PAIRED.csv": BFE9_ROOT / "BFE9_D01_D02_PAIRED.csv",
        "BFE10_D01_GATE.json": BFE10_ROOT / "BFE10_D01_GATE.json",
        "BFE10_D01_MISS_MECHANISM.json": BFE10_ROOT / "BFE10_D01_MISS_MECHANISM.json",
        "BFE5_ARCH1_CANDIDATE.md": ARCH1_CANDIDATE,
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing retained authority: {}".format(", ".join(missing)))
    for name in ("BFE8_D02_GATE.json", "BFE9_D01_GATE.json", "BFE10_D01_GATE.json"):
        gate = read_json(required[name])
        if gate.get("status") != "PASS":
            raise ValueError("retained gate is not PASS: {}".format(name))
    bfe8_gate = read_json(required["BFE8_D02_GATE.json"])
    bfe9_gate = read_json(required["BFE9_D01_GATE.json"])
    bfe10_gate = read_json(required["BFE10_D01_GATE.json"])
    if bfe9_gate.get("production_rtl_modified") or bfe9_gate.get("arch1_implemented"):
        raise ValueError("BFE9 retained gate reports a forbidden RTL/ARCH1 change")
    if bfe10_gate.get("production_rtl_modified") or bfe10_gate.get("arch1_modified"):
        raise ValueError("BFE10 retained gate reports a forbidden RTL/ARCH1 change")
    if bfe9_gate.get("simulation_accounting", {}).get("d02") != 0 or bfe9_gate.get("simulation_accounting", {}).get("healthy") != 0:
        raise ValueError("BFE9 retained accounting indicates a forbidden rerun")
    if bfe10_gate.get("simulation_accounting") != {"DC": 0, "HSPICE": 0, "PrimeSim": 0, "VCS": 0}:
        raise ValueError("BFE10 retained accounting is not zero simulation")
    hashes = {name: sha256(path) for name, path in required.items()}
    return hashes, bfe8_gate, bfe9_gate, bfe10_gate


def q_bits(q_ff, label):
    """Validate the retained tap-0..29 q_ff serialization before using M."""
    if not isinstance(q_ff, str) or len(q_ff) != Q_WIDTH or any(bit not in "01" for bit in q_ff):
        raise ValueError("{} is not a 30-bit q_ff string".format(label))
    return [int(bit) for bit in q_ff]


def weighted_m(q_ff, label):
    """Recompute M_FF from the retained q_ff word as an offline cross-check."""
    return sum(index * bit for index, bit in enumerate(q_bits(q_ff, label)))


def target_case(path, label):
    """Read event index 2 and prove it is the frozen 21 ns RISE target."""
    case = read_json(path)
    events = case.get("events", [])
    if len(events) <= TARGET_INDEX:
        raise ValueError("{} lacks event index 2: {}".format(label, path))
    event = events[TARGET_INDEX]
    if event.get("event_index") != TARGET_INDEX or event.get("edge") != "RISE":
        raise ValueError("{} target is not event index 2 RISE: {}".format(label, path))
    return event, case


def load_samples(healthy_rows, d01_rows, d02_rows):
    """Build frozen healthy-RISE, D01-target, and D02-target signed samples."""
    healthy_samples, d01_samples, d02_samples = [], [], []
    for seed in SEEDS:
        signature = healthy_rows[seed]["mc_random_signature"]
        ref = int(healthy_rows[seed]["M_REF_RISE"])
        healthy_case = read_json(BFE8_RUN_ROOT / "healthy" / "seed_{:05d}".format(seed) / "HEALTHY_CASE.json")
        d01_event, d01_case = target_case(BFE9_RUN_ROOT / "d01" / "seed_{:05d}".format(seed) / "D01_CASE.json", "D01")
        d02_event, d02_case = target_case(BFE8_RUN_ROOT / "d02" / "seed_{:05d}".format(seed) / "D02_CASE.json", "D02")
        if any(case.get("mc_random_signature") != signature for case in (healthy_case, d01_case, d02_case)):
            raise ValueError("process signature mismatch for seed {}".format(seed))
        rise_events = [event for event in healthy_case["events"] if event.get("edge") == "RISE"]
        if len(rise_events) != 12:
            raise ValueError("healthy seed {} does not contain 12 RISE events".format(seed))
        for event in rise_events:
            m_value = int(event["m_ff"])
            if weighted_m(event["q_ff"], "healthy seed {}".format(seed)) != m_value:
                raise ValueError("healthy M/q_ff mismatch for seed {}".format(seed))
            signed = m_value - ref
            healthy_samples.append({"dataset": "healthy_rise", "seed": seed, "event_index": int(event["event_index"]),
                                    "event": "{} ns RISE".format(float(event["edge_ps"]) / 1000.0), "M_FF": m_value,
                                    "M_REF_RISE": ref, "signed_e": signed, "abs_e": abs(signed), "q_ff": event["q_ff"]})
        for dataset, event in (("d01_target", d01_event), ("d02_target", d02_event)):
            m_value = int(event.get("M_FF", event.get("m_ff")))
            if weighted_m(event["q_ff"], "{} seed {}".format(dataset, seed)) != m_value:
                raise ValueError("{} M/q_ff mismatch for seed {}".format(dataset, seed))
            sample = {"dataset": dataset, "seed": seed, "event_index": TARGET_INDEX, "event": TARGET_EVENT,
                      "M_FF": m_value, "M_REF_RISE": ref, "signed_e": m_value - ref,
                      "abs_e": abs(m_value - ref), "q_ff": event["q_ff"]}
            (d01_samples if dataset == "d01_target" else d02_samples).append(sample)
    return healthy_samples, d01_samples, d02_samples


def describe(samples):
    """Return signed distribution and positive-tail min/max/quantile data."""
    values = [sample["signed_e"] for sample in samples]
    positive = [value for value in values if value > 0]
    quantile = lambda data: {"p05": float(np.percentile(data, 5)), "p25": float(np.percentile(data, 25)),
                             "p50": float(np.percentile(data, 50)), "p75": float(np.percentile(data, 75)),
                             "p95": float(np.percentile(data, 95))}
    result = {"count": len(values), "min": min(values), "max": max(values), "median": float(np.median(values)),
              "mean": float(np.mean(values)), "signed_counts": dict(sorted(Counter(values).items())),
              "quantiles": quantile(values), "positive_count": len(positive)}
    if positive:
        result["positive"] = {"min": min(positive), "max": max(positive), "median": float(np.median(positive)),
                               "quantiles": quantile(positive), "counts": dict(sorted(Counter(positive).items()))}
    else:
        result["positive"] = {"min": None, "max": None, "median": None, "quantiles": {}, "counts": {}}
    result["existing_abs_margin_alarm_count"] = sum(int(sample["abs_e"] > MARGIN_RISE) for sample in samples)
    return result


def sweep_thresholds(healthy, d01, d02):
    """Evaluate e>T_POS for integer positive thresholds as a diagnostic only."""
    rows = []
    for threshold in range(0, 436):
        healthy_alarm = sum(int(sample["signed_e"] > threshold) for sample in healthy)
        d01_alarm = sum(int(sample["signed_e"] > threshold) for sample in d01)
        d02_alarm = sum(int(sample["signed_e"] > threshold) for sample in d02)
        rows.append({"T_POS": threshold, "rule": "signed_e > T_POS", "healthy_rise_samples": len(healthy),
                     "healthy_positive_false_alarms": healthy_alarm, "healthy_positive_false_alarm_rate": healthy_alarm / float(len(healthy)),
                     "D01_samples": len(d01), "D01_detected": d01_alarm, "D01_coverage": d01_alarm / 30.0,
                     "D02_samples": len(d02), "D02_detected": d02_alarm, "D02_coverage": d02_alarm / 30.0,
                     "diagnostic_only": True, "formal_margin_unchanged": "RISE=22,FALL=24"})
    return rows


def write_csv(path, rows):
    """Write deterministic ASCII CSV evidence with the first row's schema."""
    with path.open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def make_figure(samples):
    """Render a compact grayscale signed-e distribution figure."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "serif", "font.size": 9, "axes.linewidth": 0.8})
    by_dataset = {name: [sample["signed_e"] for sample in samples if sample["dataset"] == name]
                  for name in ("healthy_rise", "d01_target", "d02_target")}
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    bins = np.arange(-25.5, 75.5, 1.0)
    styles = [("healthy_rise", "Healthy RISE (n=360)", "white", "black", "-"),
              ("d01_target", "D01 30 mV (n=30)", "0.55", "0.15", "--"),
              ("d02_target", "D02 60 mV (n=30)", "0.15", "0.15", ":")]
    for name, label, face, edge, linestyle in styles:
        ax.hist(by_dataset[name], bins=bins, histtype="step", color=edge, linewidth=1.1,
                linestyle=linestyle, label=label)
    ax.axvline(18, color="0.25", linestyle="-.", linewidth=0.9, label="Diagnostic T_POS=18")
    ax.axvline(22, color="0.45", linestyle=":", linewidth=0.9, label="Frozen RISE margin=22 (reference)")
    ax.set_xlabel("Signed error e = M_FF - M_REF_RISE (M-codes)")
    ax.set_ylabel("Retained sample count")
    ax.set_xlim(-25.5, 74.5)
    ax.grid(True, axis="y", color="0.88", linewidth=0.5)
    ax.legend(frameon=False, ncol=2, loc="upper left")
    fig.tight_layout()
    fig.savefig(ROOT / "ARCH1_SIGNED_ERROR_DISTRIBUTION.png", dpi=220)
    fig.savefig(ROOT / "ARCH1_SIGNED_ERROR_DISTRIBUTION.pdf")
    plt.close(fig)


def main():
    """Run the complete zero-simulation audit and freeze its evidence gate."""
    ROOT.mkdir(parents=True, exist_ok=True)
    authority_hashes, bfe8_gate, bfe9_gate, bfe10_gate = check_authority()
    healthy_rows = {int(row["seed"]): row for row in read_csv(BFE8_ROOT / "BFE8_HEALTHY_PER_SEED.csv")}
    d01_rows = {int(row["seed"]): row for row in read_csv(BFE9_ROOT / "BFE9_D01_PER_SEED.csv")}
    d02_rows = {int(row["seed"]): row for row in read_csv(BFE8_ROOT / "BFE8_D02_PER_SEED.csv")}
    if set(healthy_rows) != set(SEEDS) or set(d01_rows) != set(SEEDS) or set(d02_rows) != set(SEEDS):
        raise ValueError("retained populations are not exactly seeds 41001..41030")
    healthy, d01, d02 = load_samples(healthy_rows, d01_rows, d02_rows)
    all_samples = healthy + d01 + d02
    for sample in all_samples:
        sample["existing_abs_margin_alarm"] = int(sample["abs_e"] > MARGIN_RISE)
        sample["diagnostic_signed_T18_alarm"] = int(sample["signed_e"] > 18)
    descriptions = {name: describe([sample for sample in all_samples if sample["dataset"] == name])
                    for name in ("healthy_rise", "d01_target", "d02_target")}
    sweep = sweep_thresholds(healthy, d01, d02)
    d01_full = [row["T_POS"] for row in sweep if row["D01_detected"] == 30]
    healthy_zero = [row["T_POS"] for row in sweep if row["healthy_positive_false_alarms"] == 0]
    intersection = [row["T_POS"] for row in sweep if row["D01_detected"] == 30 and row["healthy_positive_false_alarms"] == 0]
    if descriptions["healthy_rise"]["positive"]["max"] != 18 or descriptions["d01_target"]["min"] != 20 or intersection != [18, 19]:
        raise AssertionError("signed-error retained boundary result changed unexpectedly")
    write_csv(ROOT / "ARCH1_SIGNED_ERROR_PER_SAMPLE.csv", all_samples)
    write_csv(ROOT / "ARCH1_SIGNED_ERROR_THRESHOLD_SWEEP.csv", sweep)
    make_figure(all_samples)
    signed18 = next(row for row in sweep if row["T_POS"] == 18)
    abs22_d01 = descriptions["d01_target"]["existing_abs_margin_alarm_count"]
    result = {
        "gate": "ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT_FROZEN", "status": "PASS",
        "input_authority_sha256": authority_hashes,
        "sample_counts": {name: descriptions[name]["count"] for name in descriptions},
        "signed_error_distributions": descriptions,
        "threshold_sweep": {"rule": "e > T_POS", "diagnostic_only": True,
            "formal_margin_unchanged": {"M_MARGIN_RISE": MARGIN_RISE, "M_MARGIN_FALL": MARGIN_FALL},
            "D01_full_coverage_integer_T_POS": d01_full, "healthy_RISE_zero_positive_false_alarm_integer_T_POS": healthy_zero,
            "intersection_integer_T_POS": intersection, "continuous_feasible_interval": "[18,20)",
            "result": "SEPARATION_EXISTS", "candidate_values_not_formal_margin": [18, 19]},
        "relative_to_existing_abs_error": {"existing_rule": "abs(e) > 22 for RISE", "D01_detected": abs22_d01,
            "D01_total": 30, "diagnostic_signed_e_gt_18_detected": signed18["D01_detected"],
            "additional_D01_seeds_detected": signed18["D01_detected"] - abs22_d01,
            "healthy_RISE_false_alarms_at_signed_e_gt_18": signed18["healthy_positive_false_alarms"],
            "value": "signed direction recovers positive low-amplitude D01 samples while retaining zero observed healthy positive alarms; no comparator or margin is changed"},
        "scope_limits": ["post-SUBTRACT/pre-ABS diagnostic only", "no new comparator", "no complete ARCH1", "no D04"],
        "simulation_accounting": {"HSPICE": 0, "VCS": 0, "PrimeSim": 0, "DC": 0},
    }
    (ROOT / "ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    report = [
        "# ARCH1 signed-error separability audit", "", "Final gate: `ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT_FROZEN`", "",
        "本阶段只复用冻结的 BFE8/BFE9/BFE10 retained artifacts，审计 SUBTRACT 后、ABS 前的 signed error `e=M_FF-M_REF_RISE`。没有修改 production RTL、frontend、waveform、process population、startup reference、M_MARGIN_RISE=22、M_MARGIN_FALL=24 或 ARCH1 candidate。没有运行 HSPICE、VCS、PrimeSim、DC。", "",
        "## 分布", "",
        "| Dataset | Samples | signed-e min / median / max | positive min / max |", "|---|---:|---:|---:|",
        "| Healthy RISE | 360 | {}/{}/{} | {}/{} |".format(descriptions["healthy_rise"]["min"], descriptions["healthy_rise"]["median"], descriptions["healthy_rise"]["max"], descriptions["healthy_rise"]["positive"]["min"], descriptions["healthy_rise"]["positive"]["max"]),
        "| D01 target 30 mV | 30 | {}/{}/{} | {}/{} |".format(descriptions["d01_target"]["min"], descriptions["d01_target"]["median"], descriptions["d01_target"]["max"], descriptions["d01_target"]["positive"]["min"], descriptions["d01_target"]["positive"]["max"]),
        "| D02 target 60 mV | 30 | {}/{}/{} | {}/{} |".format(descriptions["d02_target"]["min"], descriptions["d02_target"]["median"], descriptions["d02_target"]["max"], descriptions["d02_target"]["positive"]["min"], descriptions["d02_target"]["positive"]["max"]), "",
        "正向 signed-e 分位数（p05/p25/p50/p75/p95）：Healthy RISE `{}`；D01 `{}`；D02 `{}`。完整 signed-e 计数、正向计数和每个 retained sample 均记录在 CSV/JSON。".format(
            descriptions["healthy_rise"]["positive"]["quantiles"], descriptions["d01_target"]["positive"]["quantiles"], descriptions["d02_target"]["positive"]["quantiles"]), "",
        "## 诊断 sweep", "",
        "规则为 `e > T_POS`，仅对 retained samples 做诊断。D01 30/30 的整数阈值为 `T_POS=0..19`；Healthy RISE 零观测正向误报的整数阈值为 `T_POS=18..435`；交集为 `18..19`，连续可行区间为 `[18,20)`。因此 signed-error alone 在本 retained population 上存在分离区间。", "",
        "相对现有 RISE `abs(e)>22`：正式规则在 D01 为 {}/30；诊断 `e>18` 为 30/30，并且 Healthy RISE 误报为 0。新增价值是 retained D01 coverage 增加 8 个 seed；这不是正式 margin 重选，也不是新 comparator 的实现依据。".format(abs22_d01), "",
        "## 范围限制", "",
        "本结果只证明当前两种冻结 amplitude 与当前 retained process samples 上，signed direction 的局部分离价值。它不实现完整 ARCH1、不改变现有 ARCH1 candidate、不运行 D04，也不构成连续 minimum detectable voltage 或 silicon guarantee。",
        "仿真 accounting：HSPICE=0，VCS=0，PrimeSim=0，DC=0。",
    ]
    (ROOT / "ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    artifacts = ["ARCH1_SIGNED_ERROR_PER_SAMPLE.csv", "ARCH1_SIGNED_ERROR_THRESHOLD_SWEEP.csv", "ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT.json", "ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT_REPORT.md", "ARCH1_SIGNED_ERROR_DISTRIBUTION.png", "ARCH1_SIGNED_ERROR_DISTRIBUTION.pdf"]
    gate = {
        "gate": "ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT_FROZEN", "status": "PASS", "scope": "post-SUBTRACT/pre-ABS retained-data diagnostic",
        "separation_exists": True, "candidate_T_POS_integer": [18, 19], "candidate_T_POS_continuous": "[18,20)",
        "formal_margin_modified": False, "arch1_candidate_modified": False, "production_rtl_modified": False,
        "frontend_modified": False, "waveform_modified": False, "population_modified": False, "startup_reference_modified": False,
        "simulation_accounting": {"HSPICE": 0, "VCS": 0, "PrimeSim": 0, "DC": 0},
        "input_authority_sha256": authority_hashes,
        "artifact_sha256": {name: sha256(ROOT / name) for name in artifacts}, "stop_after_stage": True,
    }
    (ROOT / "ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT_GATE.json").write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print("ARCH1 SIGNED ERROR SEPARABILITY AUDIT PASS")


if __name__ == "__main__":
    main()
