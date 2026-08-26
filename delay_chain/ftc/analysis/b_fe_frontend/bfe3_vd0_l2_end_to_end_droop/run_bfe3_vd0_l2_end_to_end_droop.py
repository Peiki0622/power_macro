#!/usr/bin/env python3
"""B-FE3-VD0: one formal L2 droop through the frozen LATQ->DFF path."""

import csv
import hashlib
import json
import re
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
import run_bfe2_l1a_r_vcs_xa as bridge  # noqa: E402
import run_dc_sweep  # noqa: E402

TAPS = 30
VDD_NOM = 0.95
VDD_DROOP = 0.86
DROP_START_PS = 21075.0
DROP_FALL_END_PS = 21076.0
DROP_HOLD_END_PS = 24076.0
DROP_RISE_END_PS = 24077.0
DROP_TOTAL_PS = 3002.0
STOP_PS = 62000.0
SYSTEM_EDGES = clk2.SYSTEM_EDGES
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe3_vd0_l2_end_to_end_droop" / "normal_0p95_l2"
SOURCE_DIR = RUN_ROOT / "source_hspice"
XA_DIR = RUN_ROOT / "vcs_xa"
RAIL_LOW = 0.1 * VDD_NOM
RAIL_HIGH = 0.9 * VDD_NOM
THRESHOLD = 0.5 * VDD_NOM


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def system_pwl():
    points = [(0.0, 0.0)]
    state = 0.0
    for edge_ps, _polarity in SYSTEM_EDGES:
        points.extend([(edge_ps - 0.5, state), (edge_ps + 0.5, VDD_NOM if state == 0.0 else 0.0)])
        state = VDD_NOM if state == 0.0 else 0.0
    points.append((STOP_PS, state))
    return "V_SCLK s_clk vss_a PWL({})".format(" ".join("{:.12e} {:.12e}".format(t * 1e-12, v) for t, v in points))


def source_deck(cells, model):
    scenario = {"scenario_id": "BFE3-VD0-095-L2", "baseline_v": VDD_NOM, "droop_v": VDD_DROOP, "phase_ps": DROP_START_PS - 1000.0}
    deck = bfe1_frontend.render_deck(cells, scenario, model)
    deck = re.sub(r"V_SCLK s_clk vss_a PWL\([^\n]+", system_pwl(), deck)
    # bfe1_frontend.render_supply() uses its historical 7 ns terminal point;
    # this stage runs the frozen periodic clock through 62 ns, so keep the
    # final nominal-rail PWL point monotonic after the 21 ns L2 pulse.
    deck = re.sub(r" 7\.000000000000e-09\)$", " {:.12e})".format(STOP_PS * 1e-12), deck, count=1, flags=re.MULTILINE)
    deck = deck.replace("* S_CLK port: one 1-ps rising edge at 1 ns, then a constant high level through STOP_S.", "* CLK_SYS_MON: frozen 50 MHz / 50% duty; one formal L2 drop after the 21 ns rise.")
    deck = re.sub(r"\.tran\s+[^\s]+\s+[^\s]+", ".tran 1.000000000000e-12 {:.12e}".format(STOP_PS * 1e-12), deck)
    return deck


def run_hspice(cells, config):
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    deck_path = SOURCE_DIR / "bfe3_vd0_source.sp"
    trace_path = SOURCE_DIR / "bfe3_vd0_source.tr0"
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", SOURCE_DIR / "empty_subckt.sp_cal")
    deck_path.write_text(source_deck(cells, config["model_library"]), encoding="ascii")
    result = subprocess.run([config["hspice"], deck_path.name, "-o", "bfe3_vd0_source"], cwd=SOURCE_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=1800)
    (SOURCE_DIR / "hspice_command.log").write_text(result.stdout, encoding="utf-8", errors="replace")
    if result.returncode or not trace_path.is_file():
        raise RuntimeError("VD0 HSPICE source failed")
    run_dc_sweep.validate_listing(SOURCE_DIR / "bfe3_vd0_source.lis")
    trace = bfe1_frontend.parse_ascii_tr0(trace_path)
    if trace["record_width"] != 93:
        raise ValueError("VD0 source trace must retain TIME plus 92 probes")
    return trace_path, {"deck_sha256": sha256(deck_path), "tr0_sha256": sha256(trace_path), "record_count": trace["record_count"], "record_width": trace["record_width"], "hspice_version": run_dc_sweep.hspice_version(Path(config["hspice"]))}


def prepare_xa(trace_path, cells):
    trace = bfe1_frontend.parse_ascii_tr0(trace_path)
    times, columns = trace["columns"]["time"], trace["columns"]
    rail = columns[bfe1_frontend.label_for("vdd_monitored")]
    schedules, states, values, ledger = {}, {}, {}, {}
    for tap in range(TAPS):
        xor = columns[bfe1_frontend.label_for("xor_{}".format(tap))]
        initial, events = bridge.threshold_schedule(times, xor, rail)
        schedules[tap], states[tap] = events, initial
        values[tap] = {"xor_v": float(xor[0]), "threshold_v": 0.5 * float(rail[0])}
        ledger["tap_{:02d}".format(tap)] = {"initial_logic": initial, "crossings": [{"time_ps": e[0] * 1e12, "logic_state": e[1], "direction": e[2]} for e in events]}
    XA_DIR.mkdir(parents=True, exist_ok=True)
    (XA_DIR / "safe_d_crossing_ledger.json").write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (XA_DIR / "bfe3_clk2_ams_wrapper.sp").write_text(clk2.render_wrapper(columns, times), encoding="ascii")
    (XA_DIR / "tb_bfe3_clk2_vcs_xa.sv").write_text(clk2.render_tb(schedules, states, values), encoding="ascii")
    probes = ["probe_waveform_voltage vdd_sense", "probe_waveform_voltage vdd_safe", "probe_waveform_voltage latch_g_r", "probe_waveform_voltage dff_ck_r"]
    probes += ["probe_waveform_voltage q_lat_r_{:02d}".format(t) for t in range(TAPS)]
    probes += ["probe_waveform_voltage q_ff_r_{:02d}".format(t) for t in range(TAPS)]
    (XA_DIR / "xa.cfg").write_text("set_sim_level 7\nset_waveform -format fsdb\n" + "\n".join(probes) + "\n", encoding="ascii")
    config = load_json(FTC_ROOT / "ftc_config.json")
    (XA_DIR / "vcsAD.init").write_text("bus_format [%d];\nuse_spice -cell bfe3_clk2_ams;\nchoose xa -hspice {} -c {} -o {}/xa;\n".format(XA_DIR / "bfe3_clk2_ams.sp", XA_DIR / "xa.cfg", XA_DIR), encoding="utf-8")
    (XA_DIR / "bfe3_clk2_ams.sp").write_text("* B-FE3-VD0 XA deck.\n.option post=1 probe\n.lib '{}' tt\n.include '{}'\n.include '{}'\n.include '{}'\n.include '{}'\n.tran 1p {:.12e}\n.end\n".format(config["model_library"], cells["source_files"]["rvt_cdl"], cells["source_files"]["lvt_cdl"], FTC_ROOT / "spice" / "empty_subckt.sp_cal", XA_DIR / "bfe3_clk2_ams_wrapper.sp", STOP_PS * 1e-12), encoding="ascii")
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", XA_DIR / "empty_subckt.sp_cal")


def run_xa():
    vcs = shutil.which("vcs")
    if not vcs:
        raise RuntimeError("VCS is unavailable")
    result = subprocess.run([vcs, "-full64", "-sverilog", "-timescale=1ps/1ps", "-ad=vcsAD.init", "-debug_access+all", "-o", "simv", "tb_bfe3_clk2_vcs_xa.sv"], cwd=XA_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=900)
    (XA_DIR / "compile.log").write_text(result.stdout, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError("VD0 VCS compilation failed")
    result = subprocess.run(["./simv"], cwd=XA_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=2400)
    (XA_DIR / "run.log").write_text(result.stdout, encoding="utf-8", errors="replace")
    if result.returncode or not (XA_DIR / "xa_dff_samples.csv").is_file():
        raise RuntimeError("VD0 VCS/XA simulation failed")
    return {"compile_returncode": 0, "run_returncode": 0, "cosim_marker": "Start Cosim VCS-Analog Processing" in result.stdout, "xa_version_marker": "PrimeSim XA" in result.stdout, "sample_csv_sha256": sha256(XA_DIR / "xa_dff_samples.csv")}


def load_samples():
    rows = []
    with (XA_DIR / "xa_dff_samples.csv").open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            row["sample_index"], row["tap"] = int(row["sample_index"]), int(row["tap"])
            for key in ("sample_time_ps", "nearest_system_edge_ps", "q_lat_v", "q_ff_v", "safe_d_v", "vdd_safe_v", "g_v", "dff_ck_v"):
                row[key] = float(row[key])
            rows.append(row)
    return rows


def summarize(rows):
    samples = []
    for index, edge_ps in clk2.dff_rises():
        tap_rows = {row["tap"]: row for row in rows if row["sample_index"] == index}
        if set(tap_rows) != set(range(TAPS)):
            raise ValueError("DFF sample {} lacks 30 taps".format(index))
        bits = [1 if tap_rows[t]["q_ff_v"] > THRESHOLD else 0 for t in range(TAPS)]
        q_lat_mid = [t for t in range(TAPS) if RAIL_LOW < tap_rows[t]["q_lat_v"] < RAIL_HIGH]
        q_ff_mid = [t for t in range(TAPS) if RAIL_LOW < tap_rows[t]["q_ff_v"] < RAIL_HIGH]
        edge, polarity, delta, designated = clk2.system_context(edge_ps)
        code = "".join(str(bit) for bit in bits)
        samples.append({"sample_index": index, "sample_edge_ps": edge_ps, "sample_time_ps": edge_ps + clk2.SAMPLE_READ_DELAY_PS, "nearest_system_edge_ps": edge, "system_edge_polarity": polarity, "time_from_nearest_system_edge_ps": delta, "designated": designated, "q_ff_raw_tap0_to_tap29": code, "q_ff_raw_29_to_0": code[::-1], "M_FF": sum(t * bit for t, bit in enumerate(bits)), "N_FF": sum(bits), "latq_mid_rail_taps": q_lat_mid, "dff_mid_rail_taps": q_ff_mid, "dff_rail_resolved": not q_ff_mid, "latq_rail_resolved_at_sample": not q_lat_mid})
    designated = [x for x in samples if x["designated"]]
    rise = [x for x in designated if x["system_edge_polarity"] == "rise"]
    fall = [x for x in designated if x["system_edge_polarity"] == "fall"]
    pre_rise = next(x for x in rise if x["nearest_system_edge_ps"] == 1000.0)
    droop_rise = next(x for x in rise if x["nearest_system_edge_ps"] == 21000.0)
    post_rise = next(x for x in rise if x["nearest_system_edge_ps"] == 41000.0)
    normal_rises = [pre_rise, post_rise]
    normal_falls = [x for x in fall if x["nearest_system_edge_ps"] in (11000.0, 31000.0, 51000.0)]
    baseline_code, baseline_m = pre_rise["q_ff_raw_tap0_to_tap29"], pre_rise["M_FF"]
    hd = sum(a != b for a, b in zip(droop_rise["q_ff_raw_tap0_to_tap29"], baseline_code))
    for item in samples:
        item["normal_rise_reference"] = item in normal_rises
        item["normal_fall_reference"] = item in normal_falls
    droop_ok = droop_rise["dff_rail_resolved"] and droop_rise["latq_rail_resolved_at_sample"] and hd > 0 and droop_rise["M_FF"] != baseline_m
    normal_ok = all(x["q_ff_raw_tap0_to_tap29"] == baseline_code and x["M_FF"] == 287 for x in normal_rises) and all(x["q_ff_raw_tap0_to_tap29"] == "000000000000000111111111111000" and x["M_FF"] == 246 for x in normal_falls)
    gate = "BFE3_VD0_L2_END_TO_END_DROOP_SENSITIVITY_PASS" if droop_ok and normal_ok else "BFE3_VD0_L2_END_TO_END_DROOP_SENSITIVITY_FAIL"
    return samples, {"pre_rise": pre_rise, "droop_rise": droop_rise, "post_rise": post_rise, "hamming_distance": hd, "delta_M": droop_rise["M_FF"] - baseline_m, "normal_rises": normal_rises, "normal_falls": normal_falls, "droop_ok": droop_ok, "normal_recovery_ok": normal_ok}, gate


def publish(trace_path, cells, source_meta, xa_meta):
    samples, summary, gate = summarize(load_samples())
    ROOT.mkdir(parents=True, exist_ok=True)
    for item in samples:
        stem = ROOT / "sample_{:03d}".format(item["sample_index"])
        (stem.with_suffix(".json")).write_text(json.dumps(item, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with stem.with_suffix(".csv").open("w", newline="", encoding="ascii") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(item), lineterminator="\n"); writer.writeheader(); writer.writerow(item)
    with (ROOT / "BFE3_VD0_DFF_SAMPLES.csv").open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(samples[0]), lineterminator="\n"); writer.writeheader(); writer.writerows(samples)
    manifest = {"schema_version": 1, "stage": "B-FE3-VD0", "gate": gate, "base_clk2_commit": "93674bc63392d4a1c6b01a5ad9876b181ff62f70", "verification_mode": "new HSPICE L2 source + VCS/PrimeSim XA real LATQ+DFF", "clock_sys_mon": {"frequency_mhz": 50.0, "duty_percent": 50.0, "period_ns": 20.0, "system_edges": [{"time_ps": t, "polarity": p} for t, p in SYSTEM_EDGES]}, "clk_probe": {"frequency_mhz": 400.0, "duty_percent": 50.0, "gfall_offset_ps": 534.524618567, "dff_sample_offset_from_gfall_ps": 1000.0}, "l2_injection": {"target_system_edge_ps": 21000.0, "relative_start_ps": 75.0, "start_ps": DROP_START_PS, "fall_end_ps": DROP_FALL_END_PS, "hold_end_ps": DROP_HOLD_END_PS, "rise_end_ps": DROP_RISE_END_PS, "baseline_v": VDD_NOM, "droop_v": VDD_DROOP, "fall_ps": 1.0, "hold_ps": 3000.0, "rise_ps": 1.0, "total_ps": DROP_TOTAL_PS}, "frozen_structure": {"tap_count": TAPS, "rvt_prefix": 4, "lvt_prefix": 0, "xor_cell": "XOR2_X0P5M_A9TL40", "latch_cell": cells["latch"]["cell"], "dff_cell": cells["dff"]["cell"], "level0_restore": "dynamic XOR > 0.5*VDD_MONITORED"}, "normal_references": {"rise_M_FF": 287, "fall_M_FF": 246}, "source": {**source_meta, "trace_path": str(trace_path), "trace_sha256": sha256(trace_path)}, "xa": xa_meta, "result": summary, "forbidden": ["phase_sweep", "amplitude_sweep", "duration_sweep", "threshold_optimization", "self_calibration", "RTL_fault_decision", "clock_glitch", "LUT", "multi_feature_fusion", "latch_aperture_research"], "stop_after_stage": True, "next_stage_authorized": False}
    (ROOT / "BFE3_VD0_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    analysis = {"schema_version": 1, "stage": "B-FE3-VD0", "gate": gate, "samples": samples, "summary": summary, "criteria": {"droop_designated_rise": "rail-resolved q_ff, HD>0, M_FF != 287", "normal_recovery": "pre/post rise code/M=287 and normal fall code/M=246", "latq_transients": "diagnostic only; never an independent FAIL"}, "source": source_meta, "xa": xa_meta, "stop_after_stage": True, "next_stage_authorized": False}
    analysis_path = ROOT / "BFE3_VD0_ANALYSIS.json"; analysis_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = ["# B-FE3-VD0 L2 end-to-end droop sensitivity", "", "Gate: `{}`".format(gate), "", "A single formal L2 drop was injected after the 21 ns system rise: 0.95 V -> 0.86 V with 1 ps fall, 3000 ps hold, and 1 ps recovery (total 3002 ps). The frozen 50/400 MHz clocks, 30-tap chain, real LATQ, and real DFF were retained.", "", "| Capture | Edge | Designated | q_ff[29:0] | M_FF |", "|---:|---|---|---|---:|"]
    for item in samples:
        report.append("| {} | {} | {} | `{}` | {} |".format(item["sample_index"], item["system_edge_polarity"], item["designated"], item["q_ff_raw_29_to_0"], item["M_FF"]))
    report += ["", "Droop designated rise: sample {} at {} ps, HD={}, delta_M={}, M_FF={}.".format(summary["droop_rise"]["sample_index"], summary["droop_rise"]["sample_time_ps"], summary["hamming_distance"], summary["delta_M"], summary["droop_rise"]["M_FF"]), "Pre/post normal rise recovery: {}. Normal fall references: {}.".format(summary["normal_recovery_ok"], all(x["M_FF"] == 246 for x in summary["normal_falls"])), "", "LATQ internal transients were not used as an independent failure condition. No sweep, calibration, RTL fault decision, glitch, LUT, fusion, or latch-aperture study was performed. This stage stops here."]
    report_path = ROOT / "BFE3_VD0_REPORT.md"; report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    (ROOT / "BFE3_VD0_GATE.json").write_text(json.dumps({"stage": "B-FE3-VD0", "gate": gate, "droop_sample": summary["droop_rise"], "hamming_distance": summary["hamming_distance"], "delta_M": summary["delta_M"], "normal_recovery_ok": summary["normal_recovery_ok"], "analysis_sha256": sha256(analysis_path), "report_sha256": sha256(report_path), "stop_after_stage": True, "next_stage_authorized": False}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if gate.endswith("PASS") else 1


def main():
    if (XA_DIR / "xa_dff_samples.csv").is_file():
        raise FileExistsError("refusing to overwrite completed VD0 run")
    config = load_json(FTC_ROOT / "ftc_config.json")
    cells = load_json(FTC_ROOT / "discovery" / "selected_cells.json")
    if cells["latch"]["cell"] != "LATQ_X0P5M_A9TR40" or cells["dff"]["cell"] != "DFFRPQ_X0P5M_A9TR40":
        raise ValueError("selected real LATQ/DFF identity drift")
    trace_path, source_meta = run_hspice(cells, config)
    prepare_xa(trace_path, cells)
    xa_meta = run_xa()
    return publish(trace_path, cells, source_meta, xa_meta)


if __name__ == "__main__":
    raise SystemExit(main())
