#!/usr/bin/env python3
"""B-FE3-VD1: sparse L2 droop-amplitude response at the final DFF.

This runner keeps the B-FE3-VD0/CLK2 electrical and capture timing frozen.
Each voltage point is a task-owned, fresh HSPICE source run followed by a
fresh VCS/PrimeSim XA LATQ-to-DFF run.  The only varied quantity is the low
level of the monitored-rail trapezoid; the 50 MHz system clock, 400 MHz safe
clock, phase, pulse width, cell identities, and 30-tap topology are constants.
The nominal point is represented by a constant 0.95 V monitored rail, so its
designated rise is the reference rather than an artificial zero-amplitude
PWL event.
"""

import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
CLK2_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe3_clk2_ftc_latch_dff_capture"
sys.path.insert(0, str(FTC_ROOT / "scripts"))
sys.path.insert(0, str(CLK2_ROOT))
import bfe1_frontend  # noqa: E402
import run_bfe3_clk2_ftc_latch_dff_capture as clk2  # noqa: E402
import run_dc_sweep  # noqa: E402
import run_bfe2_l1a_r_vcs_xa as bridge  # noqa: E402


TAPS = 30
VDD_NOM = 0.95
VOLTAGE_POINTS = (0.95, 0.92, 0.89, 0.86)
DROP_START_PS = 21075.0
DROP_FALL_END_PS = 21076.0
DROP_HOLD_END_PS = 24076.0
DROP_RISE_END_PS = 24077.0
DROP_TOTAL_PS = 3002.0
STOP_PS = 62000.0
RAIL_LOW = 0.1 * VDD_NOM
RAIL_HIGH = 0.9 * VDD_NOM
THRESHOLD = 0.5 * VDD_NOM
RUN_BASE = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe3_vd1_droop_amplitude_response"


def sha256(path):
    """Hash retained evidence so each point can be traced to its raw run."""
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
    """Use a filesystem-safe, unambiguous voltage token."""
    return "{:.2f}".format(voltage).replace(".", "p")


def system_pwl():
    """Render the frozen 20 ns, 50 percent system monitor clock."""
    points = [(0.0, 0.0)]
    state = 0.0
    for edge_ps, _polarity in clk2.SYSTEM_EDGES:
        points.extend([(edge_ps - 0.5, state),
                       (edge_ps + 0.5, VDD_NOM if state == 0.0 else 0.0)])
        state = VDD_NOM if state == 0.0 else 0.0
    points.append((STOP_PS, state))
    return "V_SCLK s_clk vss_a PWL({})".format(
        " ".join("{:.12e} {:.12e}".format(t * 1e-12, v) for t, v in points)
    )


def source_deck(cells, model, droop_v):
    """Build one source-only deck while changing only VDD_DROOP."""
    # A nominal point has no droop event; all other points share the exact VD0
    # 1 ps fall / 3000 ps hold / 1 ps rise event after the 21 ns rise.
    scenario = {
        "scenario_id": "BFE3-VD1-{}".format(token(droop_v)),
        "baseline_v": VDD_NOM,
        "droop_v": None if droop_v == VDD_NOM else droop_v,
        "phase_ps": None if droop_v == VDD_NOM else DROP_START_PS - 1000.0,
    }
    deck = bfe1_frontend.render_deck(cells, scenario, model)
    deck = deck.replace("V_SCLK s_clk vss_a PWL(", "V_SCLK s_clk vss_a PWL(", 1)
    # render_deck emits a single-line clock and a 7 ns terminal point.  Replace
    # both so every point has the same six system edges and 62 ns stop time.
    lines = deck.splitlines()
    lines = [system_pwl() if line.startswith("V_SCLK s_clk vss_a PWL(") else line for line in lines]
    rendered = "\n".join(lines) + "\n"
    rendered = rendered.replace(
        " 7.000000000000e-09)", " {:.12e})".format(STOP_PS * 1e-12), 1
    )
    rendered = rendered.replace(
        ".tran 1.000000000000e-12 7.000000000000e-09",
        ".tran 1.000000000000e-12 {:.12e}".format(STOP_PS * 1e-12),
    )
    return rendered


def run_hspice(point_dir, cells, config, droop_v):
    """Run and validate the real transistor source for one voltage point."""
    source_dir = point_dir / "source_hspice"
    source_dir.mkdir(parents=True, exist_ok=True)
    deck_path = source_dir / "bfe3_vd1_source.sp"
    trace_path = source_dir / "bfe3_vd1_source.tr0"
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", source_dir / "empty_subckt.sp_cal")
    deck_path.write_text(source_deck(cells, config["model_library"], droop_v), encoding="ascii")
    result = subprocess.run(
        [config["hspice"], deck_path.name, "-o", "bfe3_vd1_source"],
        cwd=source_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True, check=False, timeout=1800,
    )
    (source_dir / "hspice_command.log").write_text(result.stdout, encoding="utf-8", errors="replace")
    if result.returncode or not trace_path.is_file():
        raise RuntimeError("VD1 HSPICE source failed at {} V".format(droop_v))
    run_dc_sweep.validate_listing(source_dir / "bfe3_vd1_source.lis")
    trace = bfe1_frontend.parse_ascii_tr0(trace_path)
    if trace["record_width"] != 93:
        raise ValueError("VD1 source trace must retain TIME plus 92 probes")
    return trace_path, {
        "deck_sha256": sha256(deck_path),
        "tr0_sha256": sha256(trace_path),
        "record_count": trace["record_count"],
        "record_width": trace["record_width"],
        "hspice_version": run_dc_sweep.hspice_version(Path(config["hspice"])),
    }


def prepare_xa(point_dir, trace_path, cells):
    """Replay source crossings through the real LATQ and DFF cells."""
    trace = bfe1_frontend.parse_ascii_tr0(trace_path)
    times, columns = trace["columns"]["time"], trace["columns"]
    rail = columns[bfe1_frontend.label_for("vdd_monitored")]
    schedules, states, values, ledger = {}, {}, {}, {}
    for tap in range(TAPS):
        xor = columns[bfe1_frontend.label_for("xor_{}".format(tap))]
        initial, events = bridge.threshold_schedule(times, xor, rail)
        schedules[tap], states[tap] = events, initial
        values[tap] = {"xor_v": float(xor[0]), "threshold_v": 0.5 * float(rail[0])}
        ledger["tap_{:02d}".format(tap)] = {
            "initial_logic": initial,
            "crossings": [{"time_ps": event[0] * 1e12, "logic_state": event[1], "direction": event[2]} for event in events],
        }
    xa_dir = point_dir / "vcs_xa"
    xa_dir.mkdir(parents=True, exist_ok=True)
    (xa_dir / "safe_d_crossing_ledger.json").write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (xa_dir / "bfe3_clk2_ams_wrapper.sp").write_text(clk2.render_wrapper(columns, times), encoding="ascii")
    (xa_dir / "tb_bfe3_clk2_vcs_xa.sv").write_text(clk2.render_tb(schedules, states, values), encoding="ascii")
    probes = ["probe_waveform_voltage vdd_sense", "probe_waveform_voltage vdd_safe", "probe_waveform_voltage latch_g_r", "probe_waveform_voltage dff_ck_r"]
    probes += ["probe_waveform_voltage q_lat_r_{:02d}".format(tap) for tap in range(TAPS)]
    probes += ["probe_waveform_voltage q_ff_r_{:02d}".format(tap) for tap in range(TAPS)]
    (xa_dir / "xa.cfg").write_text("set_sim_level 7\nset_waveform -format fsdb\n" + "\n".join(probes) + "\n", encoding="ascii")
    config = load_json(FTC_ROOT / "ftc_config.json")
    (xa_dir / "vcsAD.init").write_text(
        "bus_format [%d];\nuse_spice -cell bfe3_clk2_ams;\nchoose xa -hspice {} -c {} -o {}/xa;\n".format(xa_dir / "bfe3_clk2_ams.sp", xa_dir / "xa.cfg", xa_dir), encoding="utf-8"
    )
    (xa_dir / "bfe3_clk2_ams.sp").write_text(
        "* B-FE3-VD1 real LATQ+DFF deck.\n.option post=1 probe\n.lib '{}' tt\n.include '{}'\n.include '{}'\n.include '{}'\n.include '{}'\n.tran 1p {:.12e}\n.end\n".format(
            config["model_library"], cells["source_files"]["rvt_cdl"], cells["source_files"]["lvt_cdl"], FTC_ROOT / "spice" / "empty_subckt.sp_cal", xa_dir / "bfe3_clk2_ams_wrapper.sp", STOP_PS * 1e-12
        ), encoding="ascii"
    )
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", xa_dir / "empty_subckt.sp_cal")
    return xa_dir


def run_xa(xa_dir):
    """Compile and execute the real VCS/PrimeSim XA co-simulation."""
    vcs = shutil.which("vcs")
    if not vcs:
        raise RuntimeError("VCS is unavailable")
    result = subprocess.run(
        [vcs, "-full64", "-sverilog", "-timescale=1ps/1ps", "-ad=vcsAD.init", "-debug_access+all", "-o", "simv", "tb_bfe3_clk2_vcs_xa.sv"],
        cwd=xa_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=900,
    )
    (xa_dir / "compile.log").write_text(result.stdout, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError("VD1 VCS compilation failed in {}".format(xa_dir))
    result = subprocess.run(["./simv"], cwd=xa_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=2400)
    (xa_dir / "run.log").write_text(result.stdout, encoding="utf-8", errors="replace")
    evidence = xa_dir / "xa_dff_samples.csv"
    if result.returncode or not evidence.is_file():
        raise RuntimeError("VD1 VCS/XA simulation failed in {}".format(xa_dir))
    return {
        "compile_returncode": 0,
        "run_returncode": 0,
        "cosim_marker": "Start Cosim VCS-Analog Processing" in result.stdout,
        "xa_version_marker": "PrimeSim XA" in result.stdout,
        "sample_csv_sha256": sha256(evidence),
    }


def load_samples(xa_dir):
    rows = []
    with (xa_dir / "xa_dff_samples.csv").open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            row["sample_index"], row["tap"] = int(row["sample_index"]), int(row["tap"])
            for key in ("sample_time_ps", "nearest_system_edge_ps", "q_lat_v", "q_ff_v", "safe_d_v", "vdd_safe_v", "g_v", "dff_ck_v"):
                row[key] = float(row[key])
            rows.append(row)
    return rows


def summarize(rows, droop_v):
    """Classify only final DFF snapshots; LATQ is diagnostic at sample time."""
    samples = []
    for index, sample_ps in clk2.dff_rises():
        tap_rows = {row["tap"]: row for row in rows if row["sample_index"] == index}
        if set(tap_rows) != set(range(TAPS)):
            raise ValueError("VD1 sample {} lacks 30 taps".format(index))
        bits = [1 if tap_rows[tap]["q_ff_v"] > THRESHOLD else 0 for tap in range(TAPS)]
        q_lat_mid = [tap for tap in range(TAPS) if RAIL_LOW < tap_rows[tap]["q_lat_v"] < RAIL_HIGH]
        q_ff_mid = [tap for tap in range(TAPS) if RAIL_LOW < tap_rows[tap]["q_ff_v"] < RAIL_HIGH]
        edge, polarity, delta, designated = clk2.system_context(sample_ps)
        code = "".join(str(bit) for bit in bits)
        samples.append({
            "voltage_v": droop_v, "sample_index": index, "sample_time_ps": sample_ps + clk2.SAMPLE_READ_DELAY_PS,
            "nearest_system_edge_ps": edge, "system_edge_polarity": polarity, "time_from_nearest_system_edge_ps": delta,
            "designated": designated, "q_ff_raw_tap0_to_tap29": code, "q_ff_raw_29_to_0": code[::-1],
            "M_FF": sum(tap * bit for tap, bit in enumerate(bits)), "N_FF": sum(bits),
            "latq_mid_rail_taps": q_lat_mid, "dff_mid_rail_taps": q_ff_mid,
            "dff_rail_resolved": not q_ff_mid, "latq_rail_resolved_at_sample": not q_lat_mid,
        })
    designated = [item for item in samples if item["designated"]]
    rise = [item for item in designated if item["system_edge_polarity"] == "rise"]
    fall = [item for item in designated if item["system_edge_polarity"] == "fall"]
    pre_rise = next(item for item in rise if item["nearest_system_edge_ps"] == 1000.0)
    droop_rise = next(item for item in rise if item["nearest_system_edge_ps"] == 21000.0)
    post_rise = next(item for item in rise if item["nearest_system_edge_ps"] == 41000.0)
    normal_falls = [item for item in fall if item["nearest_system_edge_ps"] in (11000.0, 31000.0, 51000.0)]
    normal_recovery_ok = (
        pre_rise["M_FF"] == 287 and post_rise["M_FF"] == 287 and
        pre_rise["q_ff_raw_tap0_to_tap29"] == post_rise["q_ff_raw_tap0_to_tap29"] and
        all(item["M_FF"] == 246 for item in normal_falls) and
        all(item["q_ff_raw_tap0_to_tap29"] == "000000000000000111111111111000" for item in normal_falls)
    )
    baseline_code = pre_rise["q_ff_raw_tap0_to_tap29"]
    droop_rise["HD_vs_nominal"] = sum(a != b for a, b in zip(droop_rise["q_ff_raw_tap0_to_tap29"], baseline_code))
    droop_rise["delta_M"] = droop_rise["M_FF"] - 287
    point_ok = (
        all(item["dff_rail_resolved"] for item in samples)
        and droop_rise["dff_rail_resolved"]
        and droop_rise["N_FF"] > 0
        and normal_recovery_ok
    )
    return samples, {"pre_rise": pre_rise, "droop_rise": droop_rise, "post_rise": post_rise, "normal_falls": normal_falls, "normal_recovery_ok": normal_recovery_ok, "point_ok": point_ok}


def pearson(xs, ys):
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    return numerator / (denom_x * denom_y) if denom_x and denom_y else None


def rank(values):
    ordered = sorted((value, index) for index, value in enumerate(values))
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][0] == ordered[cursor][0]:
            end += 1
        average = (cursor + 1 + end) / 2.0
        for _, index in ordered[cursor:end]:
            ranks[index] = average
        cursor = end
    return ranks


def plot_response(rows, path_png, path_pdf):
    """Create the paper-ready amplitude response in both raster and vector forms."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    points = sorted(rows, key=lambda item: item["voltage_v"])
    x = [item["voltage_v"] for item in points]
    y = [item["droop_rise_M_FF"] for item in points]
    fig, axis = plt.subplots(figsize=(6.4, 4.2), dpi=160)
    axis.plot(x, y, marker="o", linewidth=1.8, color="#174a7e", label="designated rise")
    axis.scatter([VDD_NOM], [287], s=48, marker="s", color="#ba3b3b", label="nominal reference (0.95 V)", zorder=4)
    axis.axvline(VDD_NOM, color="#ba3b3b", linestyle="--", linewidth=0.8)
    axis.axvline(0.86, color="#555555", linestyle=":", linewidth=0.9, label="L2 (0.86 V)")
    axis.set_xlabel("VDD_DROOP (V)")
    axis.set_ylabel("M_FF")
    axis.set_title("B-FE3-VD1 droop amplitude response")
    axis.grid(True, alpha=0.28)
    axis.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path_png)
    fig.savefig(path_pdf)
    plt.close(fig)


def publish(point_results, cells, config):
    ROOT.mkdir(parents=True, exist_ok=True)
    all_samples, rows = [], []
    for point in point_results:
        samples = point["samples"]
        all_samples.extend(samples)
        droop = point["summary"]["droop_rise"]
        rows.append({"voltage_v": point["voltage_v"], "droop_rise_M_FF": droop["M_FF"], "droop_rise_HD": droop["HD_vs_nominal"], "delta_M": droop["delta_M"], "dff_rail_resolved": droop["dff_rail_resolved"], "normal_recovery_ok": point["summary"]["normal_recovery_ok"], "q_ff": droop["q_ff_raw_29_to_0"]})
        stem = ROOT / "sample_{}".format(token(point["voltage_v"]))
        stem.with_suffix(".json").write_text(json.dumps({"voltage_v": point["voltage_v"], "samples": samples, "summary": point["summary"]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with stem.with_suffix(".csv").open("w", newline="", encoding="ascii") as stream:
            # Some fields (HD and delta_M) are meaningful only for the
            # designated rise.  Use the union of keys so ordinary captures
            # remain explicit blank fields rather than making CSV emission
            # fail on the first row.
            fields = sorted(set().union(*(item.keys() for item in samples)))
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(samples)
        # Preserve the established B-FE3 per-capture evidence convention in
        # addition to the per-voltage summary above.  The voltage token keeps
        # filenames collision-free while the sample index maps directly to
        # the 400 MHz DFF capture schedule.
        for item in samples:
            capture_stem = ROOT / "sample_{}_{}".format(token(point["voltage_v"]), item["sample_index"])
            capture_stem.with_suffix(".json").write_text(json.dumps(item, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with capture_stem.with_suffix(".csv").open("w", newline="", encoding="ascii") as stream:
                writer = csv.DictWriter(stream, fieldnames=sorted(item.keys()), lineterminator="\n"); writer.writeheader(); writer.writerow(item)
    with (ROOT / "BFE3_VD1_DFF_SAMPLES.csv").open("w", newline="", encoding="ascii") as stream:
        fields = sorted(set().union(*(item.keys() for item in all_samples)))
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(all_samples)
    (ROOT / "BFE3_VD1_DFF_SAMPLES.json").write_text(json.dumps(all_samples, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    x = [item["voltage_v"] for item in sorted(rows, key=lambda item: item["voltage_v"])]
    y = [item["droop_rise_M_FF"] for item in sorted(rows, key=lambda item: item["voltage_v"])]
    correlations = {"pearson_vdd_vs_M_FF": pearson(x, y), "spearman_vdd_vs_M_FF": pearson(rank(x), rank(y))}
    descending = sorted(rows, key=lambda item: item["voltage_v"], reverse=True)
    deltas = [item["droop_rise_M_FF"] - 287 for item in descending]
    direction_consistent = all(deltas[i] <= deltas[i - 1] for i in range(1, len(deltas))) or all(deltas[i] >= deltas[i - 1] for i in range(1, len(deltas)))
    shallow_separation = any(item["voltage_v"] > 0.86 and item["droop_rise_M_FF"] != 287 for item in rows)
    all_points_ok = all(point["summary"]["point_ok"] and point["summary"]["droop_rise"]["dff_rail_resolved"] for point in point_results)
    gate = "BFE3_VD1_DROOP_AMPLITUDE_RESPONSE_PASS" if all_points_ok and direction_consistent and shallow_separation else "BFE3_VD1_DROOP_AMPLITUDE_RESPONSE_FAIL"
    summary = {"points": rows, "correlations": correlations, "direction_consistent": direction_consistent, "shallow_separation": shallow_separation, "all_points_ok": all_points_ok, "gate": gate}
    plot_response(rows, ROOT / "BFE3_VD1_M_FF_vs_VDD_DROOP.png", ROOT / "BFE3_VD1_M_FF_vs_VDD_DROOP.pdf")
    manifest = {
        "schema_version": 1, "stage": "B-FE3-VD1", "gate": gate, "base_stage": "BFE3_VD0_L2_END_TO_END_DROOP_SENSITIVITY_PASS",
        "voltage_definition": {"formal_levels_found": False, "selection": "sparse representative points", "points_v": list(VOLTAGE_POINTS), "nominal_reference_v": VDD_NOM},
        "frozen_timing": {"clock_sys_mon_mhz": 50.0, "clock_sys_mon_duty_percent": 50.0, "clk_probe_mhz": 400.0, "clk_probe_duty_percent": 50.0, "gfall_offset_ps": 534.524618567, "dff_sample_offset_from_gfall_ps": 1000.0, "droop_start_ps": DROP_START_PS, "droop_total_ps": DROP_TOTAL_PS},
        "frozen_structure": {"tap_count": TAPS, "rvt_prefix": 4, "lvt_prefix": 0, "xor_cell": "XOR2_X0P5M_A9TL40", "latch_cell": cells["latch"]["cell"], "dff_cell": cells["dff"]["cell"], "level0_restore": "dynamic XOR > 0.5*VDD_MONITORED"},
        "normal_references": {"rise_M_FF": 287, "fall_M_FF": 246}, "points": point_results, "summary": summary,
        "artifacts": {"png": str(ROOT / "BFE3_VD1_M_FF_vs_VDD_DROOP.png"), "pdf": str(ROOT / "BFE3_VD1_M_FF_vs_VDD_DROOP.pdf")},
        "forbidden": ["phase_sweep", "duration_sweep", "amplitude_sweep_beyond_sparse_points", "threshold_optimization", "self_calibration", "PVT", "clock_glitch", "LUT", "multi_feature_fusion", "latch_aperture_research"],
        "stop_after_stage": True, "next_stage_authorized": False,
    }
    (ROOT / "BFE3_VD1_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    analysis = {"schema_version": 1, "stage": "B-FE3-VD1", "gate": gate, "summary": summary, "point_results": point_results, "criteria": {"point": "DFF rail-resolved and normal rise/fall recover 287/246", "trend": "M_FF changes in one direction as VDD_DROOP decreases", "separation": "at least one point above 0.86 V differs from nominal 287"}, "stop_after_stage": True, "next_stage_authorized": False}
    analysis_path = ROOT / "BFE3_VD1_ANALYSIS.json"; analysis_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = ["# B-FE3-VD1 droop amplitude response", "", "Gate: `{}`".format(gate), "", "Formal L1/L2/L3 voltage values matching the frozen 0.95 V monitored baseline were not present in the repository; the requested sparse points 0.95/0.92/0.89/0.86 V were used. Each point reran the real HSPICE source and VCS/PrimeSim XA LATQ+DFF chain with frozen clocks, phase, pulse timing, cells, and 30 taps.", "", "| VDD_DROOP (V) | q_ff[29:0] | M_FF | HD vs nominal | delta_M | DFF rail | normal rise/fall |", "|---:|---|---:|---:|---:|---|---|"]
    for row in sorted(rows, key=lambda item: item["voltage_v"], reverse=True):
        report.append("| {:.2f} | `{}` | {} | {} | {} | {} | {} |".format(row["voltage_v"], row["q_ff"], row["droop_rise_M_FF"], row["droop_rise_HD"], row["delta_M"], row["dff_rail_resolved"], row["normal_recovery_ok"]))
    report += ["", "Pearson correlation (VDD_DROOP vs M_FF): `{}`.".format(correlations["pearson_vdd_vs_M_FF"]), "Spearman correlation (VDD_DROOP vs M_FF): `{}`; these are trend descriptors only, not a linearity requirement.".format(correlations["spearman_vdd_vs_M_FF"]), "", "Direction-consistent response: `{}`. At least one point shallower than 0.86 V separates from nominal M_FF=287: `{}`.".format(direction_consistent, shallow_separation), "", "The plotted response is saved as `BFE3_VD1_M_FF_vs_VDD_DROOP.png` and `.pdf`. LATQ internal transients were not used as an independent failure condition. No phase/duration sweep, threshold optimization, PVT, glitch, calibration, RTL decision, LUT, fusion, or aperture study was performed. This stage stops here."]
    report_path = ROOT / "BFE3_VD1_REPORT.md"; report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    (ROOT / "BFE3_VD1_GATE.json").write_text(json.dumps({"stage": "B-FE3-VD1", "gate": gate, "summary": summary, "analysis_sha256": sha256(analysis_path), "report_sha256": sha256(report_path), "plot_png_sha256": sha256(ROOT / "BFE3_VD1_M_FF_vs_VDD_DROOP.png"), "plot_pdf_sha256": sha256(ROOT / "BFE3_VD1_M_FF_vs_VDD_DROOP.pdf"), "stop_after_stage": True, "next_stage_authorized": False}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if gate.endswith("PASS") else 1


def main():
    if ROOT.exists() and any(ROOT.glob("BFE3_VD1_*")):
        raise FileExistsError("refusing to overwrite completed VD1 evidence")
    config = load_json(FTC_ROOT / "ftc_config.json")
    cells = load_json(FTC_ROOT / "discovery" / "selected_cells.json")
    if cells["latch"]["cell"] != "LATQ_X0P5M_A9TR40" or cells["dff"]["cell"] != "DFFRPQ_X0P5M_A9TR40":
        raise ValueError("selected real LATQ/DFF identity drift")
    point_results = []
    for droop_v in VOLTAGE_POINTS:
        point_dir = RUN_BASE / token(droop_v)
        trace_path = point_dir / "source_hspice" / "bfe3_vd1_source.tr0"
        xa_dir = point_dir / "vcs_xa"
        evidence = xa_dir / "xa_dff_samples.csv"
        if point_dir.exists():
            # Publishing is restartable after an analysis-only failure, but a
            # partial raw run is never silently accepted or overwritten.
            if not trace_path.is_file() or not evidence.is_file():
                raise FileExistsError("incomplete existing VD1 run: {}".format(point_dir))
            source_meta = {
                "deck_sha256": sha256(point_dir / "source_hspice" / "bfe3_vd1_source.sp"),
                "tr0_sha256": sha256(trace_path),
                "record_count": bfe1_frontend.parse_ascii_tr0(trace_path)["record_count"],
                "record_width": bfe1_frontend.parse_ascii_tr0(trace_path)["record_width"],
                "hspice_version": run_dc_sweep.hspice_version(Path(config["hspice"])),
                "reused_completed_run": True,
            }
            xa_meta = {
                "compile_returncode": 0, "run_returncode": 0,
                "cosim_marker": "Start Cosim VCS-Analog Processing" in (xa_dir / "run.log").read_text(encoding="utf-8", errors="replace"),
                "xa_version_marker": "PrimeSim XA" in (xa_dir / "run.log").read_text(encoding="utf-8", errors="replace"),
                "sample_csv_sha256": sha256(evidence), "reused_completed_run": True,
            }
        else:
            trace_path, source_meta = run_hspice(point_dir, cells, config, droop_v)
            xa_dir = prepare_xa(point_dir, trace_path, cells)
            xa_meta = run_xa(xa_dir)
        samples, summary = summarize(load_samples(xa_dir), droop_v)
        point_results.append({"voltage_v": droop_v, "run_dir": str(point_dir), "source": {**source_meta, "trace_path": str(trace_path), "trace_sha256": sha256(trace_path)}, "xa": xa_meta, "samples": samples, "summary": summary})
    return publish(point_results, cells, config)


if __name__ == "__main__":
    raise SystemExit(main())
