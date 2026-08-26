#!/usr/bin/env python3
"""B-FE3-CLK1: one 50 MHz source / 400 MHz real-safe-LATQ capture run.

The source is the frozen B-FE1 30-tap 4/0 RVT/LVT topology with thirty real
TL40 XOR cells.  A HSPICE trace is threshold-restored by the existing Level-0
bridge and drives thirty real safe-domain LATQ cells in VCS/PrimeSim XA.
Only one normal 0.95 V, 50 MHz/50% system-clock point is rendered here.
"""

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
sys.path.insert(0, str(FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "l1a_r_vcs_xa"))
import bfe1_frontend  # noqa: E402
import run_bfe2_l1a_r_vcs_xa as bridge  # noqa: E402
import run_dc_sweep  # noqa: E402

TAPS = 30
VDD = 0.95
SYS_FIRST_PS = 1000.0
SYS_HALF_PS = 10000.0
SYS_PERIOD_PS = 20000.0
SYSTEM_EDGES = tuple((SYS_FIRST_PS + index * SYS_HALF_PS, "rise" if index % 2 == 0 else "fall") for index in range(6))
G_FIRST_FALL_PS = SYS_FIRST_PS + 534.524618567
G_HALF_PS = 1250.0
G_PERIOD_PS = 2500.0
CAPTURE_READ_OFFSET_PS = 100.0
CAPTURE_TAIL_OFFSET_PS = 1000.0
STOP_PS = 62000.0
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe3_clk1_real_probe_capture"
SCENARIO_DIR = RUN_ROOT / "normal_0p95"
SOURCE_DIR = SCENARIO_DIR / "source_hspice"
XA_DIR = SCENARIO_DIR / "vcs_xa"
RAIL_LOW = 0.095
RAIL_HIGH = 0.855
TAIL_TOL = 1.0e-5
TIME_TOL_PS = 0.01


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def system_pwl() -> str:
    """Return exact 50 MHz / 50% edges with 1 ps physical slew."""

    points = [(0.0, 0.0)]
    state = 0.0
    for time_ps, _polarity in SYSTEM_EDGES:
        before = time_ps - 0.5
        after = time_ps + 0.5
        points.extend([(before, state), (after, VDD if state == 0.0 else 0.0)])
        state = VDD if state == 0.0 else 0.0
    points.append((STOP_PS, state))
    return "V_SCLK s_clk vss_a PWL({})".format(" ".join("{:.12e} {:.12e}".format(time * 1e-12, value) for time, value in points))


def source_deck(cells: dict, model_library: str) -> str:
    scenario = {"scenario_id": "BFE3-CLK1-095-N", "baseline_v": VDD, "droop_v": None, "phase_ps": None}
    deck = bfe1_frontend.render_deck(cells, scenario, model_library)
    deck = re.sub(r"V_SCLK s_clk vss_a PWL\([^\n]+", system_pwl(), deck)
    deck = deck.replace("* S_CLK port: one 1-ps rising edge at 1 ns, then a constant high level through STOP_S.", "* CLK_SYS_MON: frozen 50 MHz / 50% duty, 3 complete periods.")
    deck = re.sub(r"\.tran\s+[^\s]+\s+[^\s]+", ".tran 1.000000000000e-12 {:.12e}".format(STOP_PS * 1e-12), deck)
    return deck


def capture_falls() -> list:
    result = []
    index = 0
    time_ps = G_FIRST_FALL_PS
    while time_ps + CAPTURE_TAIL_OFFSET_PS < STOP_PS:
        result.append((index, time_ps))
        index += 1
        time_ps += G_PERIOD_PS
    return result


def system_context(time_ps: float) -> tuple:
    nearest_time, polarity = min(SYSTEM_EDGES, key=lambda item: abs(item[0] - time_ps))
    delta = time_ps - nearest_time
    designated = abs(delta - 534.524618567) <= TIME_TOL_PS
    return nearest_time, polarity, delta, designated


def render_periodic_tb(schedules: dict, initial_states: dict, initial_values: dict) -> str:
    """Render one 400 MHz 50%-duty G and per-fall real-LATQ evidence reads."""

    d_ports = bridge.port_names("safe_d")
    q_ports = bridge.port_names("q")
    falls = capture_falls()
    lines = [
        "`timescale 1ps/1ps",
        "module bfe2_l1a_r_vcs_xa;",
        *["    logic {};".format(name) for name in d_ports],
        "    logic latch_g;",
        *["    wire {};".format(name) for name in q_ports],
        "    bfe2_l1a_r_ams u_ams (",
        ",\n".join("        .{}({})".format(name, name) for name in d_ports + ["latch_g"] + q_ports),
        "    );",
        "",
        "    // CLK_PROBE: 400 MHz, 50% duty. Its first falling edge is exactly",
        "    // 534.524618567 ps after the first 50 MHz system rising edge.",
        "    initial begin",
        "        latch_g = 1'b0;",
        "        #( 284.524618567000 ) latch_g = 1'b1;",
        "        forever begin #( 1250.000000000000 ) latch_g = 1'b0; #( 1250.000000000000 ) latch_g = 1'b1; end",
        "    end",
        "",
    ]
    for tap, name in enumerate(d_ports):
        values = initial_values[tap]
        lines += [
            "    // Tap {:02d}: source-derived Level-0 initial state, xor={:.12e} V, threshold={:.12e} V.".format(tap, values["xor_v"], values["threshold_v"]),
            "    initial begin", "        {} = 1'b{};".format(name, initial_states[tap]),
        ]
        previous_ps = 0.0
        for event_time_s, event_state, _direction in schedules[tap]:
            current_ps = event_time_s * 1e12
            lines.append("        #( {:.12f} ) {} = 1'b{};".format(current_ps - previous_ps, name, event_state))
            previous_ps = current_ps
        lines += ["    end", ""]
    lines += [
        "    integer evidence_fd;", "    real analog_sample;", "    initial begin",
        "        evidence_fd = $fopen(\"xa_capture_samples.csv\", \"w\");",
        "        $fwrite(evidence_fd, \"kind,capture_index,capture_g_fall_ps,time_ps,tap,safe_d_v,q_v,vdd_sense_v,vdd_safe_v,g_v\\n\");",
    ]
    previous_ps = 0.0
    for index, fall_ps in falls:
        read_ps = fall_ps + CAPTURE_READ_OFFSET_PS
        tail_ps = fall_ps + CAPTURE_TAIL_OFFSET_PS
        lines.append("        #( {:.12f} );".format(read_ps - previous_ps))
        previous_ps = read_ps
        for tap in range(TAPS):
            lines.append("        analog_sample = $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.safe_d_r_{:02d});".format(tap))
            lines.append("        $fwrite(evidence_fd, \"capture_sample,{}, {:.12f},%.6f,{},%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.q_{:02d}), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.latch_g_r));".format(index, fall_ps, tap, tap))
        lines.append("        #( {:.12f} );".format(tail_ps - previous_ps))
        previous_ps = tail_ps
        for tap in range(TAPS):
            lines.append("        analog_sample = $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.safe_d_r_{:02d});".format(tap))
            lines.append("        $fwrite(evidence_fd, \"tail_1ns,{}, {:.12f},%.6f,{},%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.q_{:02d}), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.latch_g_r));".format(index, fall_ps, tap, tap))
    lines += ["        $fclose(evidence_fd);", "    end", ""]
    for tap, name in enumerate(q_ports):
        lines += [
            "    always @({}) begin".format(name),
            "        if ($realtime > 0.0) $fwrite(evidence_fd, \"q_event,-1,-1,%.6f,{},%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.safe_d_r_{:02d}), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.q_{:02d}), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.latch_g_r));".format(tap, tap, tap),
            "    end", "",
        ]
    lines += ["    initial begin #( 62000.000000000000 ); $finish; end", "endmodule", ""]
    return "\n".join(lines)


def run_source(config: dict, cells: dict, version: str) -> dict:
    deck_path = SOURCE_DIR / "bfe3_clk1_source.sp"
    trace_path = SOURCE_DIR / "bfe3_clk1_source.tr0"
    if deck_path.is_file() and trace_path.is_file():
        trace = bfe1_frontend.parse_ascii_tr0(trace_path)
        return {"deck_sha256": sha256(deck_path), "tr0_sha256": sha256(trace_path), "record_count": trace["record_count"], "record_width": trace["record_width"], "hspice_version": version, "run_disposition": "reused-completed"}
    SOURCE_DIR.mkdir(parents=True)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", SOURCE_DIR / "empty_subckt.sp_cal")
    deck_path.write_text(source_deck(cells, str(config["model_library"])), encoding="ascii")
    result = subprocess.run([str(config["hspice"]), deck_path.name, "-o", "bfe3_clk1_source"], cwd=SOURCE_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=1200)
    (SOURCE_DIR / "hspice_command.log").write_text("returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError("CLK1 HSPICE source failed")
    run_dc_sweep.validate_listing(SOURCE_DIR / "bfe3_clk1_source.lis")
    trace = bfe1_frontend.parse_ascii_tr0(trace_path)
    if trace["record_width"] != 93:
        raise ValueError("CLK1 source trace must retain TIME plus 92 probes")
    return {"deck_sha256": sha256(deck_path), "tr0_sha256": sha256(trace_path), "record_count": trace["record_count"], "record_width": trace["record_width"], "hspice_version": version, "run_disposition": "new"}


def prepare_xa(trace_path: Path) -> dict:
    XA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", XA_DIR / "empty_subckt.sp_cal")
    trace = bfe1_frontend.parse_ascii_tr0(trace_path)
    columns, times = trace["columns"], trace["columns"]["time"]
    rail = columns[bfe1_frontend.label_for("vdd_monitored")]
    schedules, states, values, ledger = {}, {}, {}, {}
    for tap in range(TAPS):
        xor = columns[bfe1_frontend.label_for("xor_{}".format(tap))]
        initial, events = bridge.threshold_schedule(times, xor, rail)
        schedules[tap], states[tap] = events, initial
        values[tap] = {"xor_v": float(xor[0]), "vdd_sense_v": float(rail[0]), "threshold_v": 0.5 * float(rail[0]), "safe_d_v": VDD if initial else 0.0}
        ledger["tap_{:02d}".format(tap)] = {"initial": {"logic_state": initial, **values[tap]}, "crossings": [{"time_ps": event[0] * 1e12, "logic_state": event[1], "direction": event[2]} for event in events]}
    (XA_DIR / "safe_d_crossing_ledger.json").write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    wrapper = bridge.render_wrapper("BFE3-CLK1-095-N", columns, times).replace(".tran 1p 7.000000000000e-09", ".tran 1p {:.12e}".format(STOP_PS * 1e-12))
    (XA_DIR / "bfe2_l1a_r_ams_wrapper.sp").write_text(wrapper, encoding="ascii")
    (XA_DIR / "tb_bfe2_l1a_r_vcs_xa.sv").write_text(render_periodic_tb(schedules, states, values), encoding="ascii")
    (XA_DIR / "xa.cfg").write_text("set_sim_level 7\nset_waveform -format fsdb\n" + "\n".join(["probe_waveform_voltage vdd_sense", "probe_waveform_voltage vdd_safe", "probe_waveform_voltage latch_g_r"] + ["probe_waveform_voltage safe_d_r_{:02d}".format(tap) for tap in range(TAPS)] + ["probe_waveform_voltage q_{:02d}".format(tap) for tap in range(TAPS)]) + "\n", encoding="ascii")
    (XA_DIR / "vcsAD.init").write_text("bus_format [%d];\nuse_spice -cell bfe2_l1a_r_ams;\nchoose xa -hspice {} -c {} -o {}/xa;\n".format(XA_DIR / "bfe2_l1a_r_ams.sp", XA_DIR / "xa.cfg", XA_DIR), encoding="ascii")
    top = bridge.render_top_deck(XA_DIR).replace(".tran 1p 7.000000000000e-09", ".tran 1p {:.12e}".format(STOP_PS * 1e-12))
    (XA_DIR / "bfe2_l1a_r_ams.sp").write_text(top, encoding="ascii")
    return {"ledger_sha256": sha256(XA_DIR / "safe_d_crossing_ledger.json"), "initial_safe_d_states": [states[tap] for tap in range(TAPS)]}


def run_xa() -> dict:
    vcs = shutil.which("vcs")
    if not vcs:
        raise RuntimeError("VCS is unavailable")
    command = [vcs, "-full64", "-sverilog", "-timescale=1ps/1ps", "-ad=vcsAD.init", "-debug_access+all", "-o", "simv", "tb_bfe2_l1a_r_vcs_xa.sv"]
    compile_result = subprocess.run(command, cwd=XA_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False, timeout=900)
    (XA_DIR / "compile.log").write_text(compile_result.stdout, encoding="utf-8", errors="replace")
    if compile_result.returncode != 0:
        raise RuntimeError("CLK1 VCS/XA compilation failed")
    run_result = subprocess.run(["./simv"], cwd=XA_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False, timeout=1800)
    (XA_DIR / "run.log").write_text(run_result.stdout, encoding="utf-8", errors="replace")
    if run_result.returncode != 0:
        raise RuntimeError("CLK1 VCS/XA simulation failed")
    boundary = XA_DIR / "xa_capture_samples.csv"
    if not boundary.is_file():
        raise RuntimeError("CLK1 XA capture evidence is missing")
    return {"compile_returncode": compile_result.returncode, "run_returncode": run_result.returncode, "cosim_marker": "Start Cosim VCS-Analog Processing" in run_result.stdout, "xa_version_marker": "PrimeSim XA" in run_result.stdout, "capture_csv_sha256": sha256(boundary)}


def load_capture_rows(path: Path) -> list:
    rows = []
    with path.open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            row["capture_index"] = int(row["capture_index"])
            row["tap"] = int(row["tap"])
            for key in ("capture_g_fall_ps", "time_ps", "safe_d_v", "q_v", "vdd_sense_v", "vdd_safe_v", "g_v"):
                row[key] = float(row[key])
            rows.append(row)
    return rows


def capture_summary(index: int, fall_ps: float, rows: list) -> dict:
    samples = {row["tap"]: row for row in rows if row["kind"] == "capture_sample" and row["capture_index"] == index}
    tails = {row["tap"]: row for row in rows if row["kind"] == "tail_1ns" and row["capture_index"] == index}
    if set(samples) != set(range(TAPS)) or set(tails) != set(range(TAPS)):
        raise ValueError("missing 30 sample/tail values for capture {}".format(index))
    bits = [1 if samples[tap]["q_v"] > 0.5 * VDD else 0 for tap in range(TAPS)]
    mid = [tap for tap in range(TAPS) if RAIL_LOW < samples[tap]["q_v"] < RAIL_HIGH]
    tail_unstable = [tap for tap in range(TAPS) if abs(samples[tap]["q_v"] - tails[tap]["q_v"]) > TAIL_TOL]
    safe_bad = [tap for tap in range(TAPS) if abs(samples[tap]["vdd_safe_v"] - VDD) > 1e-6 or abs(tails[tap]["vdd_safe_v"] - VDD) > 1e-6]
    g_bad = [tap for tap in range(TAPS) if samples[tap]["g_v"] > 0.1 * VDD or tails[tap]["g_v"] > 0.1 * VDD]
    # A Q transition after the settled 100 ps capture sample and before the
    # next G rising edge is an unambiguously post-close re-flip.  Recording it
    # prevents a temporary source-free error from being hidden by the 1 ns
    # tail sample returning to the original rail.
    next_g_rise_ps = fall_ps + G_HALF_PS
    post_close_events = [
        {"time_ps": row["time_ps"], "tap": row["tap"], "safe_d_v": row["safe_d_v"], "q_v": row["q_v"]}
        for row in rows
        if row["kind"] == "q_event" and fall_ps + CAPTURE_READ_OFFSET_PS < row["time_ps"] < next_g_rise_ps - TIME_TOL_PS
    ]
    edge_ps, polarity, delta_ps, designated = system_context(fall_ps)
    return {"capture_index": index, "g_fall_ps": fall_ps, "sample_time_ps": samples[0]["time_ps"], "tail_time_ps": tails[0]["time_ps"], "nearest_system_edge_ps": edge_ps, "system_edge_polarity": polarity, "time_from_nearest_system_edge_ps": delta_ps, "designated": designated, "q_raw_tap0_to_tap29": "".join(str(bit) for bit in bits), "q_raw_29_to_0": "".join(str(bit) for bit in reversed(bits)), "N": sum(bits), "M": sum(tap * bit for tap, bit in enumerate(bits)), "T": sum(bits[tap] ^ bits[tap - 1] for tap in range(1, TAPS)), "mid_rail_taps": mid, "unstable_tail_taps": tail_unstable, "safe_supply_bad_taps": safe_bad, "g_not_closed_taps": g_bad, "source_free_post_close_events": post_close_events, "rail_tail_stable": not mid and not tail_unstable and not safe_bad and not g_bad and not post_close_events}


def publish(source: dict, xa: dict) -> int:
    rows = load_capture_rows(XA_DIR / "xa_capture_samples.csv")
    captures = [capture_summary(index, fall_ps, rows) for index, fall_ps in capture_falls()]
    for capture in captures:
        stem = "capture_{:03d}".format(capture["capture_index"])
        with (ROOT / (stem + ".csv")).open("w", newline="", encoding="ascii") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(capture), lineterminator="\n")
            writer.writeheader(); writer.writerow(capture)
        (ROOT / (stem + ".json")).write_text(json.dumps(capture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (ROOT / "BFE3_CLK1_CAPTURE_SAMPLES.csv").open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(captures[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(captures)
    designated = [capture for capture in captures if capture["designated"]]
    nondesignated = [capture for capture in captures if not capture["designated"]]
    def family(polarity):
        values = [capture for capture in designated if capture["system_edge_polarity"] == polarity]
        return {"count": len(values), "codes": sorted(set(item["q_raw_tap0_to_tap29"] for item in values)), "M_values": sorted(set(item["M"] for item in values)), "all_nonempty": all(item["N"] > 0 for item in values), "all_stable": all(item["rail_tail_stable"] for item in values)}
    rise, fall = family("rise"), family("fall")
    designated_ok = all(group["count"] >= 3 and len(group["codes"]) == 1 and len(group["M_values"]) == 1 and group["all_nonempty"] and group["all_stable"] for group in (rise, fall))
    idle_bad = [capture for capture in nondesignated if not capture["rail_tail_stable"] or capture["N"] != 0]
    gate = "BFE3_CLK1_400MHZ_REAL_PROBE_CAPTURE_PASS" if designated_ok and not idle_bad else "BFE3_CLK1_400MHZ_REAL_PROBE_CAPTURE_FAIL"
    reasons = []
    if not designated_ok: reasons.append("designated rise/fall capture is missing, empty, unstable, or non-reproducible")
    if idle_bad: reasons.append("non-designated capture is non-idle or unstable: {}".format([item["capture_index"] for item in idle_bad]))
    manifest = {"schema_version": 1, "stage": "B-FE3-CLK1", "gate": gate, "verification_mode": "HSPICE W-2024.09 source + VCS W-2024.09 / PrimeSim XA W-2024.09 real LATQ capture", "new_hspice_scenarios": 1, "new_vcs_xa_scenarios": 1, "clock_sys_mon": {"frequency_mhz": 50.0, "duty_percent": 50.0, "period_ns": 20.0, "system_edges": [{"time_ps": time, "polarity": polarity} for time, polarity in SYSTEM_EDGES]}, "clk_probe": {"frequency_mhz": 400.0, "duty_percent": 50.0, "period_ns": 2.5, "first_falling_edge_ps": G_FIRST_FALL_PS, "designated_offset_ps": 534.524618567, "capture_count": len(captures)}, "vdd_monitored_v": VDD, "sensing_geometry": {"tap_count": TAPS, "rvt_prefix": 4, "lvt_prefix": 0, "xor_cell": bfe1_frontend.XOR_CELL}, "level0_restoration": "xor > 0.5*VDD_MONITORED ? 0.95 V : 0 V", "safe_latch_cell": "LATQ_X0P5M_A9TR40", "source": source, "xa": xa, "forbidden": ["droop", "clock_glitch", "frequency_scan", "phase_scan", "duty_scan", "RTL", "self_calibration", "fault_decision", "lookup_table", "multi_feature_fusion", "CLK2"], "stop_after_stage": True, "next_stage_authorized": False}
    manifest_path = ROOT / "BFE3_CLK1_MANIFEST.json"; manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    analysis = {"schema_version": 1, "stage": "B-FE3-CLK1", "gate": gate, "failure_reasons": reasons, "designated_rise": rise, "designated_fall": fall, "idle_failure_captures": idle_bad, "captures": captures, "all_designated_stable_repeatable": designated_ok, "all_nondesignated_stable_idle": not idle_bad, "manifest_sha256": sha256(manifest_path), "stop_after_stage": True, "next_stage_authorized": False}
    analysis_path = ROOT / "BFE3_CLK1_ANALYSIS.json"; analysis_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = ["# B-FE3-CLK1 real 400 MHz probe capture", "", "Gate: `{}`".format(gate), "", "One 0.95 V normal HSPICE source trace drives real safe-domain `LATQ_X0P5M_A9TR40` through the frozen Level-0 restoration bridge. `CLK_SYS_MON` is fixed at 50 MHz/50%; `CLK_PROBE` is fixed at 400 MHz/50%.", "", "| Capture | G fall (ps) | System edge | Delta (ps) | Designated | q_raw[29:0] | M | Stable |", "|---:|---:|---|---:|---|---|---:|---|"]
    for item in captures:
        report.append("| {} | {:.6f} | {} | {:.6f} | {} | `{}` | {} | {} |".format(item["capture_index"], item["g_fall_ps"], item["system_edge_polarity"], item["time_from_nearest_system_edge_ps"], item["designated"], item["q_raw_29_to_0"], item["M"], item["rail_tail_stable"]))
    report += ["", "Designated rise captures: codes=`{}`, M=`{}`.".format(rise["codes"], rise["M_values"]), "Designated fall captures: codes=`{}`, M=`{}`.".format(fall["codes"], fall["M_values"]), "Non-designated idle failures: `{}`.".format([item["capture_index"] for item in idle_bad]), "", "No droop, glitch experiment, frequency/phase/duty scan, RTL, calibration, fault decision, lookup table, or multi-feature fusion is included. This stage stops here."]
    report_path = ROOT / "BFE3_CLK1_REPORT.md"; report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    (ROOT / "BFE3_CLK1_GATE.json").write_text(json.dumps({"stage": "B-FE3-CLK1", "gate": gate, "failure_reasons": reasons, "designated_rise": rise, "designated_fall": fall, "idle_failure_captures": [item["capture_index"] for item in idle_bad], "analysis_sha256": sha256(analysis_path), "report_sha256": sha256(report_path), "stop_after_stage": True, "next_stage_authorized": False}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if gate.endswith("PASS") else 1


def main() -> int:
    if (XA_DIR / "xa_capture_samples.csv").is_file(): raise FileExistsError("refusing to overwrite completed CLK1 run root")
    config, cells = load_json(FTC_ROOT / "ftc_config.json"), load_json(FTC_ROOT / "discovery" / "selected_cells.json")
    if cells["latch"]["cell"] != "LATQ_X0P5M_A9TR40": raise ValueError("safe latch identity drift")
    version = run_dc_sweep.hspice_version(Path(config["hspice"]))
    if config["expected_hspice_version"] not in version: raise RuntimeError("unexpected HSPICE version")
    source = run_source(config, cells, version)
    xa = prepare_xa(SOURCE_DIR / "bfe3_clk1_source.tr0")
    xa.update(run_xa())
    return publish(source, xa)


if __name__ == "__main__": raise SystemExit(main())
