#!/usr/bin/env python3
"""B-FE3-CLK2: FTC-style real LATQ -> DFF digital snapshot capture.

The frozen CLK1 HSPICE source trace is replayed through the existing Level-0
bridge into real ``LATQ_X0P5M_A9TR40`` cells.  This stage adds thirty real
``DFFRPQ_X0P5M_A9TR40`` cells in the safe domain.  Latch G and DFF CK are
independent 400 MHz clocks with fixed phases: each G falling edge is at
system-edge+534.524618567 ps and the following DFF rising edge is exactly
1000 ps later.  Only the final DFF Q rail-resolved digital snapshot is gated;
short LATQ analog motion between those two instants is diagnostic evidence.
"""

import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
CLK1_RUN = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe3_clk1_real_probe_capture" / "normal_0p95"
SOURCE_DIR = CLK1_RUN / "source_hspice"
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe3_clk2_ftc_latch_dff_capture" / "normal_0p95"
XA_DIR = RUN_ROOT / "vcs_xa"
TAPS = 30
VDD = 0.95
SYSTEM_FIRST_PS = 1000.0
SYSTEM_HALF_PS = 10000.0
SYSTEM_EDGES = tuple((SYSTEM_FIRST_PS + i * SYSTEM_HALF_PS, "rise" if i % 2 == 0 else "fall") for i in range(6))
G_FIRST_FALL_PS = SYSTEM_FIRST_PS + 534.524618567
G_HALF_PS = 1250.0
G_PERIOD_PS = 2500.0
DFF_FIRST_RISE_PS = G_FIRST_FALL_PS + 1000.0
DFF_HALF_PS = 1250.0
DFF_PERIOD_PS = 2500.0
SAMPLE_READ_DELAY_PS = 100.0
STOP_PS = 62000.0
DESIGNATED_OFFSET_PS = 1534.524618567
TIME_TOL_PS = 0.01
RAIL_LOW = 0.1 * VDD
RAIL_HIGH = 0.9 * VDD
THRESHOLD = 0.5 * VDD

sys.path.insert(0, str(FTC_ROOT / "scripts"))
sys.path.insert(0, str(FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe3_clk1_real_probe_capture"))
import bfe1_frontend  # noqa: E402
import run_bfe3_clk1_real_probe_capture as clk1  # noqa: E402
import run_bfe2_l1a_r_vcs_xa as bridge  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def port_names(prefix: str):
    return ["{}_{}".format(prefix, tap) for tap in range(TAPS)]


def capture_falls():
    result, fall = [], G_FIRST_FALL_PS
    index = 0
    while fall + 1000.0 < STOP_PS:
        result.append((index, fall))
        index += 1
        fall += G_PERIOD_PS
    return result


def dff_rises():
    result, rise = [], DFF_FIRST_RISE_PS
    index = 0
    while rise < STOP_PS:
        result.append((index, rise))
        index += 1
        rise += DFF_PERIOD_PS
    return result


def system_context(sample_ps: float):
    edge, polarity = min(SYSTEM_EDGES, key=lambda item: abs(item[0] - sample_ps))
    delta = sample_ps - edge
    designated = abs(delta - DESIGNATED_OFFSET_PS) <= TIME_TOL_PS
    return edge, polarity, delta, designated


def pwl(name, node, return_node, points):
    rendered = " ".join("{:.12e} {:.12e}".format(t, v) for t, v in points)
    return "V_{} {} {} PWL({})".format(name.upper(), node, return_node, rendered)


def render_wrapper(columns, times):
    d_ports = port_names("safe_d")
    q_lat_ports = port_names("q_lat")
    q_ff_ports = port_names("q_ff")
    ports = d_ports + ["latch_g", "dff_ck"] + q_lat_ports + q_ff_ports
    lines = [
        "* B-FE3-CLK2 real LATQ -> DFF wrapper; frozen 0.95 V source replay.",
        ".SUBCKT bfe3_clk2_ams \\",
        "+ " + " \\\n+".join(ports),
        pwl("vdd_sense", "vdd_sense", "0", zip(times, columns[bfe1_frontend.label_for("vdd_monitored")])),
        "V_VDD_SAFE vdd_safe 0 DC 9.500000000000e-01",
        "V_VSS_SAFE vss_safe 0 DC 0",
        "V_DFF_RESET dff_reset 0 DC 0",
    ]
    for tap in range(TAPS):
        label = bfe1_frontend.label_for("xor_{}".format(tap))
        lines.append(pwl("xor_{:02d}".format(tap), "xor_{:02d}".format(tap), "0", zip(times, columns[label])))
        lines.append("E_SAFE_D_{:02d} safe_d_r_{:02d} 0 safe_d_{} 0 1.0".format(tap, tap, tap))
    lines += ["E_LATCH_G latch_g_r 0 latch_g 0 1.0", "E_DFF_CK dff_ck_r 0 dff_ck 0 1.0"]
    for tap in range(TAPS):
        lines.append("XLATCH_{:02d} q_lat_r_{:02d} vdd_safe vdd_safe vss_safe vss_safe safe_d_r_{:02d} latch_g_r LATQ_X0P5M_A9TR40".format(tap, tap, tap))
        lines.append("XDFF_{:02d} q_ff_r_{:02d} vdd_safe vdd_safe vss_safe vss_safe dff_ck_r q_lat_r_{:02d} dff_reset DFFRPQ_X0P5M_A9TR40".format(tap, tap, tap))
        lines.append("E_Q_LAT_{:02d} q_lat_{:02d} 0 q_lat_r_{:02d} 0 1.0".format(tap, tap, tap))
        lines.append("E_Q_FF_{:02d} q_ff_{:02d} 0 q_ff_r_{:02d} 0 1.0".format(tap, tap, tap))
    probe = ["v(vdd_sense)", "v(vdd_safe)", "v(latch_g_r)", "v(dff_ck_r)"]
    probe += ["v(safe_d_r_{:02d})".format(tap) for tap in range(TAPS)]
    probe += ["v(q_lat_r_{:02d})".format(tap) for tap in range(TAPS)]
    probe += ["v(q_ff_r_{:02d})".format(tap) for tap in range(TAPS)]
    lines += [".probe tran {}".format(" ".join(probe)), ".tran 1p {:.12e}".format(STOP_PS * 1e-12), ".ENDS bfe3_clk2_ams", ""]
    return "\n".join(lines)


def render_tb(schedules, states, values):
    d_ports, q_lat_ports, q_ff_ports = port_names("safe_d"), port_names("q_lat"), port_names("q_ff")
    lines = ["`timescale 1ps/1ps", "module bfe3_clk2_vcs_xa;", *["  logic {};".format(x) for x in d_ports], "  logic latch_g;", "  logic dff_ck;", *["  wire {};".format(x) for x in q_lat_ports + q_ff_ports], "  bfe3_clk2_ams u_ams (", ",\n".join("    .{}({})".format(x, x) for x in d_ports + ["latch_g", "dff_ck"] + q_lat_ports + q_ff_ports), "  );", ""]
    lines += ["  // LATQ G: first falling edge is system edge + 534.524618567 ps.", "  initial begin latch_g = 1'b1; #( 1534.524618567000 ) latch_g = 1'b0; forever begin #( 1250.000000000000 ) latch_g = 1'b1; #( 1250.000000000000 ) latch_g = 1'b0; end end", "  // DFF CK: first valid rising sample is Gfall + 1000 ps.", "  initial begin dff_ck = 1'b0; #( 2534.524618567000 ) dff_ck = 1'b1; forever begin #( 1250.000000000000 ) dff_ck = 1'b0; #( 1250.000000000000 ) dff_ck = 1'b1; end end", ""]
    for tap, name in enumerate(d_ports):
        lines += ["  // Tap {:02d}: source-derived initial safe_d={} (xor={:.9e} V, threshold={:.9e} V).".format(tap, states[tap], values[tap]["xor_v"], values[tap]["threshold_v"]), "  initial begin", "    {} = 1'b{};".format(name, states[tap])]
        previous_ps = 0.0
        for event_s, event_state, _direction in schedules[tap]:
            event_ps = event_s * 1e12
            lines.append("    #( {:.12f} ) {} = 1'b{};".format(event_ps - previous_ps, name, event_state))
            previous_ps = event_ps
        lines += ["  end", ""]
    lines += ["  integer fd; real v;", "  initial begin", "    fd = $fopen(\"xa_dff_samples.csv\", \"w\");", "    $fwrite(fd, \"kind,sample_index,sample_time_ps,nearest_system_edge_ps,system_polarity,tap,q_lat_v,q_ff_v,safe_d_v,vdd_safe_v,g_v,dff_ck_v\\n\");"]
    previous_ps = 0.0
    for index, sample_ps in dff_rises():
        lines.append("    #( {:.12f} );".format(sample_ps - previous_ps))
        previous_ps = sample_ps
        lines.append("    #( {:.12f} );".format(SAMPLE_READ_DELAY_PS))
        previous_ps += SAMPLE_READ_DELAY_PS
        edge_ps, polarity = min(SYSTEM_EDGES, key=lambda item: abs(item[0] - sample_ps))
        for tap in range(TAPS):
            lines.append("    $fwrite(fd, \"dff_sample,{},%.6f,{:.6f},{},%d,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, {}, $snps_get_volt(bfe3_clk2_vcs_xa.u_ams.q_lat_r_{:02d}), $snps_get_volt(bfe3_clk2_vcs_xa.u_ams.q_ff_r_{:02d}), $snps_get_volt(bfe3_clk2_vcs_xa.u_ams.safe_d_r_{:02d}), $snps_get_volt(bfe3_clk2_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe3_clk2_vcs_xa.u_ams.latch_g_r), $snps_get_volt(bfe3_clk2_vcs_xa.u_ams.dff_ck_r));".format(index, edge_ps, polarity, tap, tap, tap, tap, tap))
    lines += ["    $fclose(fd);", "  end", "  initial begin #( 62000.000000 ); $finish; end", "endmodule", ""]
    return "\n".join(lines)


def prepare():
    cells = load_json(FTC_ROOT / "discovery" / "selected_cells.json")
    if cells.get("latch", {}).get("cell") != "LATQ_X0P5M_A9TR40" or cells.get("dff", {}).get("cell") != "DFFRPQ_X0P5M_A9TR40":
        raise ValueError("selected real LATQ/DFF identity drift")
    trace_path = SOURCE_DIR / "bfe3_clk1_source.tr0"
    if not trace_path.is_file():
        raise FileNotFoundError("frozen CLK1 HSPICE trace is missing: {}".format(trace_path))
    trace = bfe1_frontend.parse_ascii_tr0(trace_path)
    times, columns = trace["columns"]["time"], trace["columns"]
    rail = columns[bfe1_frontend.label_for("vdd_monitored")]
    schedules, states, values, ledger = {}, {}, {}, {}
    for tap in range(TAPS):
        xor = columns[bfe1_frontend.label_for("xor_{}".format(tap))]
        initial, events = bridge.threshold_schedule(times, xor, rail)
        schedules[tap], states[tap] = events, initial
        values[tap] = {"xor_v": float(xor[0]), "threshold_v": float(rail[0]) * 0.5}
        ledger["tap_{:02d}".format(tap)] = {"initial_logic": initial, "crossings": [{"time_ps": e[0] * 1e12, "logic_state": e[1], "direction": e[2]} for e in events]}
    XA_DIR.mkdir(parents=True, exist_ok=True)
    (XA_DIR / "safe_d_crossing_ledger.json").write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (XA_DIR / "bfe3_clk2_ams_wrapper.sp").write_text(render_wrapper(columns, times), encoding="ascii")
    (XA_DIR / "tb_bfe3_clk2_vcs_xa.sv").write_text(render_tb(schedules, states, values), encoding="ascii")
    (XA_DIR / "xa.cfg").write_text("set_sim_level 7\nset_waveform -format fsdb\n" + "\n".join(["probe_waveform_voltage vdd_sense", "probe_waveform_voltage vdd_safe", "probe_waveform_voltage latch_g_r", "probe_waveform_voltage dff_ck_r"] + ["probe_waveform_voltage q_lat_r_{:02d}".format(t) for t in range(TAPS)] + ["probe_waveform_voltage q_ff_r_{:02d}".format(t) for t in range(TAPS)]) + "\n", encoding="ascii")
    config = load_json(FTC_ROOT / "ftc_config.json")
    (XA_DIR / "vcsAD.init").write_text("bus_format [%d];\nuse_spice -cell bfe3_clk2_ams;\nchoose xa -hspice {} -c {} -o {}/xa;\n".format(XA_DIR / "bfe3_clk2_ams.sp", XA_DIR / "xa.cfg", XA_DIR), encoding="utf-8")
    (XA_DIR / "bfe3_clk2_ams.sp").write_text("* B-FE3-CLK2 XA top deck.\n.option post=1 probe\n.lib '{}' tt\n.include '{}'\n.include '{}'\n.include '{}'\n.include '{}'\n.tran 1p {:.12e}\n.end\n".format(config["model_library"], cells["source_files"]["rvt_cdl"], cells["source_files"]["lvt_cdl"], FTC_ROOT / "spice" / "empty_subckt.sp_cal", XA_DIR / "bfe3_clk2_ams_wrapper.sp", STOP_PS * 1e-12), encoding="ascii")
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", XA_DIR / "empty_subckt.sp_cal")
    return trace_path, cells, states


def run_xa():
    vcs = shutil.which("vcs")
    if not vcs:
        raise RuntimeError("VCS is unavailable")
    result = subprocess.run([vcs, "-full64", "-sverilog", "-timescale=1ps/1ps", "-ad=vcsAD.init", "-debug_access+all", "-o", "simv", "tb_bfe3_clk2_vcs_xa.sv"], cwd=XA_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=900)
    (XA_DIR / "compile.log").write_text(result.stdout, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError("CLK2 VCS compilation failed")
    result = subprocess.run(["./simv"], cwd=XA_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=1800)
    (XA_DIR / "run.log").write_text(result.stdout, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError("CLK2 VCS/XA simulation failed")
    evidence = XA_DIR / "xa_dff_samples.csv"
    if not evidence.is_file():
        raise RuntimeError("CLK2 DFF sample evidence missing")
    return {"compile_returncode": 0, "run_returncode": 0, "cosim_marker": "Start Cosim VCS-Analog Processing" in result.stdout, "xa_version_marker": "PrimeSim XA" in result.stdout, "sample_csv_sha256": sha256(evidence)}


def load_samples():
    rows = []
    with (XA_DIR / "xa_dff_samples.csv").open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            for key in ("sample_index", "tap"):
                row[key] = int(row[key])
            for key in ("sample_time_ps", "nearest_system_edge_ps", "q_lat_v", "q_ff_v", "safe_d_v", "vdd_safe_v", "g_v", "dff_ck_v"):
                row[key] = float(row[key])
            rows.append(row)
    return rows


def summarize(rows):
    samples = []
    for index, sample_ps in dff_rises():
        tap_rows = {r["tap"]: r for r in rows if r["sample_index"] == index}
        if set(tap_rows) != set(range(TAPS)):
            raise ValueError("sample {} does not contain 30 taps".format(index))
        bits = [1 if tap_rows[t]["q_ff_v"] > THRESHOLD else 0 for t in range(TAPS)]
        q_lat_mid = [t for t in range(TAPS) if RAIL_LOW < tap_rows[t]["q_lat_v"] < RAIL_HIGH]
        q_ff_mid = [t for t in range(TAPS) if RAIL_LOW < tap_rows[t]["q_ff_v"] < RAIL_HIGH]
        supply_bad = [t for t in range(TAPS) if abs(tap_rows[t]["vdd_safe_v"] - VDD) > 1e-6]
        ck_bad = [t for t in range(TAPS) if abs(tap_rows[t]["dff_ck_v"] - VDD) > 0.1 * VDD]
        edge, polarity, delta, designated = system_context(sample_ps)
        code = "".join(str(x) for x in bits)
        samples.append({"sample_index": index, "sample_edge_ps": sample_ps, "sample_time_ps": sample_ps + SAMPLE_READ_DELAY_PS, "nearest_system_edge_ps": edge, "system_edge_polarity": polarity, "time_from_nearest_system_edge_ps": delta, "designated": designated, "q_ff_raw_tap0_to_tap29": code, "q_ff_raw_29_to_0": code[::-1], "M_FF": sum(t * bit for t, bit in enumerate(bits)), "N_FF": sum(bits), "latq_mid_rail_taps": q_lat_mid, "dff_mid_rail_taps": q_ff_mid, "dff_supply_bad_taps": supply_bad, "dff_clock_bad_taps": ck_bad, "dff_rail_resolved": not q_ff_mid and not supply_bad, "latq_rail_resolved_at_sample": not q_lat_mid})
    designated = [x for x in samples if x["designated"]]
    rise = [x for x in designated if x["system_edge_polarity"] == "rise"]
    fall = [x for x in designated if x["system_edge_polarity"] == "fall"]
    idle = [x for x in samples if not x["designated"]]
    def family(items):
        return {"count": len(items), "codes": sorted(set(x["q_ff_raw_tap0_to_tap29"] for x in items)), "M_values": sorted(set(x["M_FF"] for x in items)), "all_nonempty": bool(items) and all(x["N_FF"] > 0 for x in items), "all_rail_resolved": bool(items) and all(x["dff_rail_resolved"] for x in items)}
    rise_s, fall_s = family(rise), family(fall)
    designated_bad = [x for x in designated if not x["dff_rail_resolved"] or not x["latq_rail_resolved_at_sample"] or x["N_FF"] == 0]
    idle_bad = [x for x in idle if not x["dff_rail_resolved"] or x["N_FF"] != 0]
    gate = "BFE3_CLK2_FTC_LATCH_DFF_CAPTURE_PASS" if len(rise) >= 3 and len(fall) >= 3 and rise_s["all_nonempty"] and fall_s["all_nonempty"] and len(rise_s["codes"]) == 1 and len(fall_s["codes"]) == 1 and len(rise_s["M_values"]) == 1 and len(fall_s["M_values"]) == 1 and not designated_bad and not idle_bad else "BFE3_CLK2_FTC_LATCH_DFF_CAPTURE_FAIL"
    return samples, rise_s, fall_s, designated_bad, idle_bad, gate


def publish(trace_path, cells, states, xa):
    rows = load_samples()
    samples, rise, fall, designated_bad, idle_bad, gate = summarize(rows)
    ROOT.mkdir(parents=True, exist_ok=True)
    for item in samples:
        stem = ROOT / "sample_{:03d}".format(item["sample_index"])
        (stem.with_suffix(".json")).write_text(json.dumps(item, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with stem.with_suffix(".csv").open("w", newline="", encoding="ascii") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(item), lineterminator="\n"); writer.writeheader(); writer.writerow(item)
    with (ROOT / "BFE3_CLK2_DFF_SAMPLES.csv").open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(samples[0]), lineterminator="\n"); writer.writeheader(); writer.writerows(samples)
    manifest = {"schema_version": 1, "stage": "B-FE3-CLK2", "gate": gate, "verification_mode": "HSPICE frozen source + VCS/PrimeSim XA real LATQ+DFF", "simulation_run": True, "source_trace": {"path": str(trace_path), "sha256": sha256(trace_path)}, "clock_sys_mon": {"frequency_mhz": 50.0, "duty_percent": 50.0, "period_ns": 20.0, "system_edges": [{"time_ps": t, "polarity": p} for t, p in SYSTEM_EDGES]}, "clk_probe": {"frequency_mhz": 400.0, "duty_percent": 50.0, "period_ns": 2.5, "g_first_fall_ps": G_FIRST_FALL_PS, "dff_first_rise_ps": DFF_FIRST_RISE_PS, "dff_sample_offset_from_gfall_ps": 1000.0, "sample_count": len(samples)}, "frozen_structure": {"vdd_monitored_v": VDD, "tap_count": TAPS, "rvt_prefix": 4, "lvt_prefix": 0, "xor_cell": "XOR2_X0P5M_A9TL40", "latch_cell": cells["latch"]["cell"], "dff_cell": cells["dff"]["cell"], "level0_restore": "safe_d = 0.95 V iff XOR > 0.5*VDD_MONITORED"}, "designated_rise": rise, "designated_fall": fall, "designated_failures": [x["sample_index"] for x in designated_bad], "non_designated_failures": [x["sample_index"] for x in idle_bad], "forbidden": ["droop", "clock_glitch", "phase_sweep", "frequency_sweep", "duty_sweep", "self_calibration", "RTL_fault_decision", "LUT", "multi_feature_fusion", "latch_aperture_optimization", "CLK2_after_this_stage"], "stop_after_stage": True, "next_stage_authorized": False}
    (ROOT / "BFE3_CLK2_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    analysis = {"schema_version": 1, "stage": "B-FE3-CLK2", "gate": gate, "designated_rise": rise, "designated_fall": fall, "designated_failures": designated_bad, "non_designated_failures": idle_bad, "samples": samples, "criteria": {"designated": "3 rise and 3 fall same non-empty q_ff/M_FF, DFF Q rail-resolved", "non_designated": "q_ff digital code all zero", "latq_transient_between_gfall_and_dff_sample": "diagnostic only; never an independent FAIL"}, "xa": xa, "simulation_run": True, "stop_after_stage": True, "next_stage_authorized": False}
    analysis_path = ROOT / "BFE3_CLK2_ANALYSIS.json"; analysis_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = ["# B-FE3-CLK2 FTC LATQ to real DFF capture", "", "Gate: `{}`".format(gate), "", "Frozen 50 MHz/50% `CLK_SYS_MON`, 0.95 V monitored rail, 30-tap 4/0 RVT/LVT chain, real `XOR2_X0P5M_A9TL40`, real `LATQ_X0P5M_A9TR40`, and selected real `DFFRPQ_X0P5M_A9TR40` were used. The frozen CLK1 HSPICE source trace was replayed through a new VCS/PrimeSim XA LATQ+DFF bench.", "", "G falling is fixed at system edge + 534.524618567 ps. DFF CK rising is fixed at Gfall + 1000 ps (system edge + 1534.524618567 ps). LATQ analog behavior between these points is diagnostic only; the gate uses the DFF sample instant.", "", "| Family | Count | q_ff code(s) | M_FF | Non-empty | DFF rail-resolved |", "|---|---:|---|---|---|---|", "| Rise designated | {} | `{}` | `{}` | {} | {} |".format(rise["count"], rise["codes"], rise["M_values"], rise["all_nonempty"], rise["all_rail_resolved"]), "| Fall designated | {} | `{}` | `{}` | {} | {} |".format(fall["count"], fall["codes"], fall["M_values"], fall["all_nonempty"], fall["all_rail_resolved"]), "", "| Sample | Time (ps) | Edge | Designated | q_ff[29:0] | M_FF | DFF rail |", "|---:|---:|---|---|---|---:|---|"]
    for x in samples: report.append("| {} | {:.6f} | {} | {} | `{}` | {} | {} |".format(x["sample_index"], x["sample_time_ps"], x["system_edge_polarity"], x["designated"], x["q_ff_raw_29_to_0"], x["M_FF"], x["dff_rail_resolved"]))
    report += ["", "Designated failures: `{}`. Non-designated failures: `{}`.".format([x["sample_index"] for x in designated_bad], [x["sample_index"] for x in idle_bad]), "", "No droop, glitch, clock sweep, RTL fault decision, self-calibration, LUT, multi-feature fusion, or latch-aperture optimization was performed. This stage stops here."]
    (ROOT / "BFE3_CLK2_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (ROOT / "BFE3_CLK2_GATE.json").write_text(json.dumps({"stage": "B-FE3-CLK2", "gate": gate, "designated_rise": rise, "designated_fall": fall, "designated_failures": [x["sample_index"] for x in designated_bad], "non_designated_failures": [x["sample_index"] for x in idle_bad], "analysis_sha256": sha256(analysis_path), "report_sha256": sha256(ROOT / "BFE3_CLK2_REPORT.md"), "stop_after_stage": True, "next_stage_authorized": False}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if gate.endswith("PASS") else 1


def main():
    if (XA_DIR / "xa_dff_samples.csv").is_file():
        raise FileExistsError("refusing to overwrite completed CLK2 evidence")
    trace_path, cells, states = prepare()
    xa = run_xa()
    return publish(trace_path, cells, states, xa)


if __name__ == "__main__":
    raise SystemExit(main())
