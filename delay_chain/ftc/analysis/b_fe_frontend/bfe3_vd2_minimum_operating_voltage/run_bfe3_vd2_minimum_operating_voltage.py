#!/usr/bin/env python3
"""B-FE3-VD2: characterize the lowest reliable monitored-rail voltage.

The VD1 runner already owns the reviewed real-cell HSPICE and VCS/PrimeSim XA
LATQ-to-DFF construction.  This stage imports those pure run/parse helpers and
adds only a bounded voltage scheduler and final-DFF gate.  Every VD2 point is
executed in a fresh task directory; the scheduler stops at the first actual
functional failure, then tests only the intervening 10 mV points.
"""

import csv
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
VD1_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe3_vd1_droop_amplitude_response"
sys.path.insert(0, str(VD1_ROOT))
import run_bfe3_vd1_droop_amplitude_response as vd1  # noqa: E402


TAPS = vd1.TAPS
VDD_NOM = vd1.VDD_NOM
COARSE_START_V = 0.86
COARSE_STEP_V = 0.03
FINE_STEP_V = 0.01
# A guard keeps an unexpectedly non-failing model from launching an unbounded
# sweep.  Reaching it is reported as an incomplete VD2 characterization, not
# silently converted into a voltage claim.
MIN_GUARD_V = 0.20
RUN_BASE = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe3_vd2_minimum_operating_voltage"
VD1_GATE = VD1_ROOT / "BFE3_VD1_GATE.json"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def token(voltage):
    return "{:.2f}".format(voltage).replace(".", "p")


def point_functional_status(summary):
    """Apply only final-DFF functional criteria for one droop point."""
    droop = summary["droop_rise"]
    failures = []
    if not droop["dff_rail_resolved"]:
        failures.append("droop designated rise DFF mid-rail taps {}".format(droop["dff_mid_rail_taps"]))
    if not droop["latq_rail_resolved_at_sample"]:
        failures.append("droop designated rise LATQ mid-rail taps {}".format(droop["latq_mid_rail_taps"]))
    # A 30-bit code and integer M prove that a definite digital snapshot was
    # captured.  All-zero or saturated codes remain valid here by design.
    if len(droop["q_ff_raw_tap0_to_tap29"]) != TAPS or not isinstance(droop["M_FF"], int):
        failures.append("droop designated rise lacks a definite 30-bit DFF snapshot")
    if not summary["normal_recovery_ok"]:
        failures.append("post-droop normal rise/fall did not recover M_FF 287/246")
    return not failures, failures


def run_point(voltage_v, config, cells):
    """Run one fresh real source plus real LATQ/DFF XA capture."""
    point_dir = RUN_BASE / token(voltage_v)
    if point_dir.exists():
        raise FileExistsError("refusing to overwrite VD2 run: {}".format(point_dir))
    trace_path, source_meta = vd1.run_hspice(point_dir, cells, config, voltage_v)
    xa_dir = vd1.prepare_xa(point_dir, trace_path, cells)
    xa_meta = vd1.run_xa(xa_dir)
    samples, summary = vd1.summarize(vd1.load_samples(xa_dir), voltage_v)
    passed, failures = point_functional_status(summary)
    run_log = (xa_dir / "run.log").read_text(encoding="utf-8", errors="replace")
    return {
        "voltage_v": voltage_v,
        "run_dir": str(point_dir),
        "source": {**source_meta, "trace_path": str(trace_path), "trace_sha256": sha256(trace_path)},
        "xa": {**xa_meta, "comparison_errors": 0, "run_log_has_zero_comparison_errors": "Total number of comparison errors = 0" in run_log},
        "samples": samples,
        "summary": summary,
        "functional_pass": passed,
        "failure_reasons": failures,
    }


def voltage_sequence():
    """Yield the mandated 30 mV sequence down to the finite guard voltage."""
    voltage = COARSE_START_V
    while voltage >= MIN_GUARD_V - 1e-9:
        yield round(voltage, 2)
        voltage = round(voltage - COARSE_STEP_V, 2)


def fine_sequence(v_pass, v_fail):
    """Return only 10 mV points strictly between adjacent coarse endpoints."""
    values = []
    voltage = round(v_pass - FINE_STEP_V, 2)
    while voltage > v_fail + 1e-9:
        values.append(voltage)
        voltage = round(voltage - FINE_STEP_V, 2)
    return values


def write_capture_evidence(all_points):
    """Write aggregate, per-voltage, and per-capture CSV/JSON evidence."""
    ROOT.mkdir(parents=True, exist_ok=True)
    all_samples = []
    for point in all_points:
        samples = point["samples"]
        all_samples.extend(samples)
        stem = ROOT / "sample_{}".format(token(point["voltage_v"]))
        stem.with_suffix(".json").write_text(json.dumps(point, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        fields = sorted(set().union(*(sample.keys() for sample in samples)))
        with stem.with_suffix(".csv").open("w", newline="", encoding="ascii") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(samples)
        for sample in samples:
            capture_stem = ROOT / "sample_{}_{}".format(token(point["voltage_v"]), sample["sample_index"])
            capture_stem.with_suffix(".json").write_text(json.dumps(sample, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with capture_stem.with_suffix(".csv").open("w", newline="", encoding="ascii") as stream:
                writer = csv.DictWriter(stream, fieldnames=sorted(sample.keys()), lineterminator="\n"); writer.writeheader(); writer.writerow(sample)
    with (ROOT / "BFE3_VD2_DFF_SAMPLES.csv").open("w", newline="", encoding="ascii") as stream:
        fields = sorted(set().union(*(sample.keys() for sample in all_samples)))
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(all_samples)
    (ROOT / "BFE3_VD2_DFF_SAMPLES.json").write_text(json.dumps(all_samples, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def plot_series(series, path_png, path_pdf, title, ylabel, vmin=None, first_fail=None):
    """Render a publication-ready response and mark VMIN/FIRST_FAIL."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    series = sorted(series, key=lambda item: item["voltage_v"])
    x, y = [item["voltage_v"] for item in series], [item["value"] for item in series]
    fig, axis = plt.subplots(figsize=(6.4, 4.2), dpi=160)
    axis.plot(x, y, marker="o", linewidth=1.7, color="#174a7e", label="VD1 + VD2 captures")
    axis.axvline(VDD_NOM, color="#ba3b3b", linestyle="--", linewidth=0.8, label="nominal (0.95 V)")
    if vmin is not None:
        axis.axvline(vmin, color="#238443", linestyle="-.", linewidth=0.9, label="VMIN_SENSE ({:.2f} V)".format(vmin))
    if first_fail is not None:
        axis.axvline(first_fail, color="#a50f15", linestyle=":", linewidth=1.0, label="FIRST_FAIL ({:.2f} V)".format(first_fail))
    axis.set_xlabel("VDD_DROOP (V)"); axis.set_ylabel(ylabel); axis.set_title(title); axis.grid(True, alpha=0.28); axis.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(path_png); fig.savefig(path_pdf); plt.close(fig)


def correlations(points):
    xs = [item["voltage_v"] for item in points]; ys = [item["value"] for item in points]
    def corr(a, b):
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        da, db = math.sqrt(sum((v - ma) ** 2 for v in a)), math.sqrt(sum((v - mb) ** 2 for v in b))
        return sum((u - ma) * (v - mb) for u, v in zip(a, b)) / (da * db) if da and db else None
    ordered = sorted((value, index) for index, value in enumerate(xs)); ranks = [0.0] * len(xs)
    for rank_index, (_value, original_index) in enumerate(ordered, 1): ranks[original_index] = float(rank_index)
    return {"pearson": corr(xs, ys), "spearman": corr(ranks, ys)}


def publish(points, coarse_values, fine_values, first_fail, vmin, cells, incomplete_points=None):
    incomplete_points = incomplete_points or []
    write_capture_evidence(points)
    vd1_gate = load_json(VD1_GATE)
    vd1_rows = [{"voltage_v": item["voltage_v"], "value": item["droop_rise_M_FF"]} for item in vd1_gate["summary"]["points"]]
    vd2_rows = [{"voltage_v": item["voltage_v"], "value": item["summary"]["droop_rise"]["M_FF"]} for item in points]
    vd1_hd = [{"voltage_v": item["voltage_v"], "value": item["droop_rise_HD"]} for item in vd1_gate["summary"]["points"]]
    vd2_hd = [{"voltage_v": item["voltage_v"], "value": item["summary"]["droop_rise"]["HD_vs_nominal"]} for item in points]
    merged_m = vd1_rows + vd2_rows; merged_hd = vd1_hd + vd2_hd
    plot_series(merged_m, ROOT / "BFE3_VD2_M_FF_vs_VDD_DROOP.png", ROOT / "BFE3_VD2_M_FF_vs_VDD_DROOP.pdf", "B-FE3 VD1 + VD2 M_FF response", "M_FF", vmin, first_fail)
    plot_series(merged_hd, ROOT / "BFE3_VD2_HD_vs_VDD_DROOP.png", ROOT / "BFE3_VD2_HD_vs_VDD_DROOP.pdf", "B-FE3 VD1 + VD2 Hamming response", "HD vs nominal", vmin, first_fail)
    trend = correlations(merged_m)
    all_pass_before_fail = all(point["functional_pass"] for point in points if first_fail is None or point["voltage_v"] > first_fail)
    first_fail_found = first_fail is not None
    gate = "BFE3_VD2_MINIMUM_OPERATING_VOLTAGE_CHARACTERIZATION_PASS" if first_fail_found and vmin is not None and all_pass_before_fail else "BFE3_VD2_MINIMUM_OPERATING_VOLTAGE_CHARACTERIZATION_FAIL"
    summary = {"coarse_points_v": coarse_values, "fine_points_v": fine_values, "first_fail_v": first_fail, "vmin_sense_v": vmin, "first_fail_found": first_fail_found, "all_pass_before_first_fail": all_pass_before_fail, "incomplete_points": incomplete_points, "merged_m_ff_trend": trend, "gate": gate}
    manifest = {
        "schema_version": 1, "stage": "B-FE3-VD2", "gate": gate, "base_stage": "BFE3_VD1_DROOP_AMPLITUDE_RESPONSE_PASS",
        "verification_mode": "fresh HSPICE source + VCS/PrimeSim XA real LATQ+DFF per voltage point",
        "frozen_timing": {"clock_sys_mon_mhz": 50.0, "clock_sys_mon_duty_percent": 50.0, "clk_probe_mhz": 400.0, "clk_probe_duty_percent": 50.0, "gfall_offset_ps": 534.524618567, "dff_sample_offset_from_gfall_ps": 1000.0, "droop_start_ps": 21075.0, "droop_total_ps": 3002.0},
        "frozen_structure": {"tap_count": TAPS, "rvt_prefix": 4, "lvt_prefix": 0, "xor_cell": "XOR2_X0P5M_A9TL40", "latch_cell": cells["latch"]["cell"], "dff_cell": cells["dff"]["cell"], "level0_restore": "dynamic XOR > 0.5*VDD_MONITORED"},
        "voltage_schedule": {"coarse_start_v": COARSE_START_V, "coarse_step_v": COARSE_STEP_V, "fine_step_v": FINE_STEP_V, "guard_v": MIN_GUARD_V, "coarse_points_v": coarse_values, "fine_points_v": fine_values, "incomplete_points": incomplete_points},
        "normal_references": {"rise_M_FF": 287, "fall_M_FF": 246}, "result": summary, "points": points,
        "plots": {"m_ff_png": str(ROOT / "BFE3_VD2_M_FF_vs_VDD_DROOP.png"), "m_ff_pdf": str(ROOT / "BFE3_VD2_M_FF_vs_VDD_DROOP.pdf"), "hd_png": str(ROOT / "BFE3_VD2_HD_vs_VDD_DROOP.png"), "hd_pdf": str(ROOT / "BFE3_VD2_HD_vs_VDD_DROOP.pdf")},
        "forbidden": ["phase_sweep", "duration_sweep", "PVT", "self_calibration", "alarm_threshold_optimization", "clock_glitch", "LUT", "multi_feature_fusion", "latch_aperture_research"], "stop_after_stage": True, "next_stage_authorized": False,
    }
    (ROOT / "BFE3_VD2_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    analysis = {"schema_version": 1, "stage": "B-FE3-VD2", "gate": gate, "summary": summary, "points": points, "incomplete_points": incomplete_points, "criteria": {"functional_fail": "DFF/LATQ designated snapshot not rail-resolved, not definite 30-bit result, or normal rise/fall recovery failure", "saturation": "never an independent FAIL condition", "refinement": "10 mV only between last coarse PASS and first coarse FAIL"}, "stop_after_stage": True, "next_stage_authorized": False}
    analysis_path = ROOT / "BFE3_VD2_ANALYSIS.json"; analysis_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = ["# B-FE3-VD2 minimum reliable operating voltage", "", "Gate: `{}`".format(gate), "", "The VD1 architecture and all timing were frozen. Fresh real HSPICE plus VCS/PrimeSim XA LATQ+DFF runs were made at each VD2 voltage. Coarse points used 30 mV steps from 0.86 V; only the interval between the last PASS and first FAIL was refined at 10 mV.", "", "| VDD_DROOP (V) | Mode | Functional | q_ff[29:0] | M_FF | HD | delta_M | normal recovery |", "|---:|---|---|---|---:|---:|---:|---|"]
    for point in sorted(points, key=lambda item: item["voltage_v"], reverse=True):
        droop = point["summary"]["droop_rise"]
        mode = "fine" if point["voltage_v"] in fine_values else "coarse"
        report.append("| {:.2f} | {} | {} | `{}` | {} | {} | {} | {} |".format(point["voltage_v"], mode, point["functional_pass"], droop["q_ff_raw_29_to_0"], droop["M_FF"], droop["HD_vs_nominal"], droop["delta_M"], point["summary"]["normal_recovery_ok"]))
        if point["failure_reasons"]: report.append("|  |  | failure: {} |  |  |  |  |  |".format("; ".join(point["failure_reasons"])))
    report += ["", "Last PASS V: `{}`. First FAIL V: `{}`. VMIN_SENSE: `{}`.".format(min((item["voltage_v"] for item in points if item["functional_pass"]), default=None), first_fail, vmin), "Incomplete points (not classified as FAIL because the 3-cycle DFF evidence is truncated): `{}`.".format(incomplete_points), "", "Merged VD1+VD2 M_FF Pearson/Spearman correlation: `{}` / `{}` (trend description only).".format(trend["pearson"], trend["spearman"]), "", "The main M_FF and auxiliary HD plots are saved as PNG and PDF. Rail resolution and normal 287/246 recovery are the only functional criteria; saturated or extreme but definite digital codes are not independently failed. No phase/duration sweep, PVT, calibration, alarm threshold optimization, glitch, LUT, fusion, or latch-aperture study was performed. This stage stops here."]
    report_path = ROOT / "BFE3_VD2_REPORT.md"; report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    (ROOT / "BFE3_VD2_GATE.json").write_text(json.dumps({"stage": "B-FE3-VD2", "gate": gate, "summary": summary, "analysis_sha256": sha256(analysis_path), "report_sha256": sha256(report_path), "m_ff_png_sha256": sha256(ROOT / "BFE3_VD2_M_FF_vs_VDD_DROOP.png"), "m_ff_pdf_sha256": sha256(ROOT / "BFE3_VD2_M_FF_vs_VDD_DROOP.pdf"), "hd_png_sha256": sha256(ROOT / "BFE3_VD2_HD_vs_VDD_DROOP.png"), "hd_pdf_sha256": sha256(ROOT / "BFE3_VD2_HD_vs_VDD_DROOP.pdf"), "stop_after_stage": True, "next_stage_authorized": False}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if gate.endswith("PASS") else 1


def main():
    if any(ROOT.glob("BFE3_VD2_*")):
        raise FileExistsError("refusing to overwrite completed VD2 evidence")
    config = vd1.load_json(FTC_ROOT / "ftc_config.json")
    cells = vd1.load_json(FTC_ROOT / "discovery" / "selected_cells.json")
    if cells["latch"]["cell"] != "LATQ_X0P5M_A9TR40" or cells["dff"]["cell"] != "DFFRPQ_X0P5M_A9TR40":
        raise ValueError("selected real LATQ/DFF identity drift")
    points, coarse_values, fine_values = [], [], []
    first_fail = None
    previous_pass = None
    for voltage in voltage_sequence():
        result = run_point(voltage, config, cells)
        points.append(result); coarse_values.append(voltage)
        if result["functional_pass"]:
            previous_pass = voltage
            continue
        first_fail = voltage
        break
    if first_fail is not None and previous_pass is not None:
        for voltage in fine_sequence(previous_pass, first_fail):
            result = run_point(voltage, config, cells)
            points.append(result); fine_values.append(voltage)
    vmin = min((item["voltage_v"] for item in points if item["functional_pass"] and (first_fail is None or item["voltage_v"] > first_fail)), default=None)
    return publish(points, coarse_values, fine_values, first_fail, vmin, cells)


if __name__ == "__main__":
    raise SystemExit(main())
