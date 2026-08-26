#!/usr/bin/env python3
"""Run the bounded B-FE3-P0T late-droop re-probe experiment.

The first 1000 ps launch is retained from B-FE3-P0R.  Only two new, fully
independent source/HSPICE and VCS-XA points are authorized: launches at 2000
ps and 3000 ps with the same 500 ps-relative L2 droop and a G close exactly
534.524618567 ps after each launch.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
sys.path.insert(0, str(FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe3_p0r_m_phase"))
sys.path.insert(0, str(FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "l1a_r_vcs_xa"))

import bfe1_frontend  # noqa: E402
import bfe2_real_snapshot  # noqa: E402
import run_bfe3_p0r_m_phase as p0r  # noqa: E402
import run_bfe2_l1a_r_vcs_xa as bridge  # noqa: E402
import run_dc_sweep  # noqa: E402

RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe3_p0t_late_reprobe"
P0R_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe3_p0r_m_phase"
P0R_ANALYSIS = P0R_ROOT / "BFE3_P0R_ANALYSIS.json"
P0R_MANIFEST = P0R_ROOT / "BFE3_P0R_MANIFEST.json"
CELLS = FTC_ROOT / "discovery" / "selected_cells.json"
CONFIG = FTC_ROOT / "ftc_config.json"
LAUNCHES = (("FIRST", 1000.0, "retained P0R LATE baseline"), ("REPROBE_PLUS1000", 2000.0, "new diagnostic re-probe"), ("REPROBE_PLUS2000", 3000.0, "new diagnostic re-probe"))
NEW_LAUNCHES = LAUNCHES[1:]
LATE_PHASE_PS = 500.0
SAMPLE_CLOSE_PS = 534.524618567
P0R_FIRST_G_CLOSE_PS = 1534.524618567
DROOP_ONSET_PS = 1500.0
STOP_S = 7.0e-9
EXPECTED_RECORD_WIDTH = 124


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def fmt_spice(value: float) -> str:
    return "{:.12e}".format(float(value) * 1.0e-12)


def source_scenario(label: str) -> dict:
    return {
        "scenario_id": "BFE3P0T-095-L2-{}".format(label),
        "baseline_v": 0.95,
        "droop_v": 0.86,
        "phase_ps": LATE_PHASE_PS,
        "authority_scenario_key": "BFE3_P0T_LATE_DROOP_REPROBE",
    }


def launch_and_close_lines(launch_ps: float) -> tuple:
    close_ps = launch_ps + SAMPLE_CLOSE_PS
    edge_ps = 0.5
    sclk = "V_SCLK s_clk vss_a PWL(0 0 {} 0 {} 'VDD_VALUE' {:.12e} 'VDD_VALUE')".format(
        fmt_spice(launch_ps - edge_ps), fmt_spice(launch_ps + edge_ps), STOP_S
    )
    g = "V_LATCH_G latch_g vss_a PWL(0 'VDD_VALUE' {} 'VDD_VALUE' {} 0 {:.12e} 0)".format(
        fmt_spice(close_ps - edge_ps), fmt_spice(close_ps + edge_ps), STOP_S
    )
    return sclk, g, close_ps


def render_source(cells: dict, scenario: dict, launch_ps: float) -> str:
    deck = bfe2_real_snapshot.render(cells, scenario, p0r.SOURCE_SAMPLE_CLOSE_PS)
    old_sclk = next(line for line in deck.splitlines() if line.startswith("V_SCLK s_clk"))
    old_g = next(line for line in deck.splitlines() if line.startswith("V_LATCH_G latch_g"))
    sclk, g, _ = launch_and_close_lines(launch_ps)
    return deck.replace(old_sclk, sclk).replace(old_g, g)


def run_source(label: str, launch_ps: float, hspice: Path, version: str) -> dict:
    directory = RUN_ROOT / label.lower() / "source_hspice"
    directory.mkdir(parents=True, exist_ok=True)
    deck_path = directory / "bfe3_p0t_source.sp"
    trace_path = directory / "bfe3_p0t_source.tr0"
    evidence_path = directory / "source_evidence.json"
    scenario = source_scenario(label)
    if evidence_path.is_file() and deck_path.is_file() and trace_path.is_file():
        evidence = read_json(evidence_path)
        if evidence.get("launch_ps") == launch_ps and sha256(deck_path) == evidence.get("deck_sha256") and sha256(trace_path) == evidence.get("tr0_sha256"):
            return dict(evidence, run_disposition="reused-completed")
        raise FileExistsError("P0T source identity mismatch: {}".format(directory))
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    deck = render_source(read_json(CELLS), scenario, launch_ps)
    bfe2_real_snapshot.validate(deck)
    deck_path.write_text(deck, encoding="ascii")
    result = subprocess.run([str(hspice), deck_path.name, "-o", "bfe3_p0t_source"], cwd=str(directory), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=600)
    (directory / "hspice_command.log").write_text("returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError("P0T HSPICE source failed: {}".format(label))
    run_dc_sweep.validate_listing(directory / "bfe3_p0t_source.lis")
    trace = bfe1_frontend.parse_ascii_tr0(trace_path)
    if trace["record_width"] != EXPECTED_RECORD_WIDTH:
        raise ValueError("P0T source trace width changed: {}".format(trace["record_width"]))
    evidence = {
        "scenario_id": scenario["scenario_id"], "phase_ps": LATE_PHASE_PS, "launch_ps": launch_ps,
        "g_close_ps": launch_ps + SAMPLE_CLOSE_PS, "droop_onset_ps": DROOP_ONSET_PS,
        "baseline_v": 0.95, "droop_v": 0.86, "sample_close_ps": SAMPLE_CLOSE_PS,
        "record_width": trace["record_width"], "record_count": trace["record_count"], "hspice_version": version,
        "deck_sha256": sha256(deck_path), "tr0_sha256": sha256(trace_path), "run_disposition": "new",
    }
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def render_tb(schedules: dict, initial_states: dict, initial_values: dict, close_ps: float) -> str:
    d_ports = bridge.port_names("safe_d")
    q_ports = bridge.port_names("q")
    lines = ["// B-FE3-P0T VCS-XA testbench; one independent late-droop probe.", "`timescale 1ps/1ps", "module bfe2_l1a_r_vcs_xa;"]
    lines += ["    logic {};".format(name) for name in d_ports] + ["    logic latch_g;"] + ["    wire {};".format(name) for name in q_ports]
    lines += ["", "    bfe2_l1a_r_ams u_ams ("]
    lines.append(",\n".join("        .{}({})".format(name, name) for name in d_ports + ["latch_g"] + q_ports))
    lines += ["    );", "", "    initial begin", "        latch_g = 1'b1;", "        #( {:.12f} ) latch_g = 1'b0;".format(close_ps), "    end", ""]
    for tap, name in enumerate(d_ports):
        values = initial_values[tap]
        lines += ["    initial begin", "        {} = 1'b{};".format(name, int(initial_states[tap]))]
        previous_time_ps = 0.0
        for event_time_s, event_state, _direction in schedules[tap]:
            event_ps = event_time_s * 1.0e12
            lines.append("        #( {:.12f} ) {} = 1'b{};".format(max(0.0, event_ps - previous_time_ps), name, event_state))
            previous_time_ps = event_ps
        lines += ["    end", ""]
    post_ps = close_ps + 100.0
    tail_ps = close_ps + 1100.0
    final_ps = 6999.0
    lines += ["    integer evidence_fd;", "    real analog_sample;", "    initial begin", "        evidence_fd = $fopen(\"xa_boundary_samples.csv\", \"w\");", "        $fwrite(evidence_fd, \"kind,time_ps,tap,safe_d_v,q_v,vdd_sense_v,vdd_safe_v,g_v\\n\");", "        #( {:.12f} );".format(post_ps)]
    for tap in range(30):
        lines += ["        analog_sample = $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.safe_d_r_{:02d});".format(tap), "        $fwrite(evidence_fd, \"post_close,%.6f,{},%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.q_{:02d}), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.latch_g_r));".format(tap, tap)]
    lines.append("        #( {:.12f} );".format(tail_ps - post_ps))
    for tap in range(30):
        lines += ["        analog_sample = $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.safe_d_r_{:02d});".format(tap), "        $fwrite(evidence_fd, \"tail_1ns,%.6f,{},%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.q_{:02d}), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.latch_g_r));".format(tap, tap)]
    lines.append("        #( {:.12f} );".format(final_ps - tail_ps))
    for tap in range(30):
        lines += ["        analog_sample = $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.safe_d_r_{:02d});".format(tap), "        $fwrite(evidence_fd, \"final,%.6f,{},%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.q_{:02d}), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.latch_g_r));".format(tap, tap)]
    lines += ["        $fclose(evidence_fd);", "    end", ""]
    for tap, name in enumerate(q_ports):
        lines += ["    always @({}) begin".format(name), "        analog_sample = $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.q_{:02d});".format(tap), "        $fwrite(evidence_fd, \"q_event,%.6f,{},%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.safe_d_r_{:02d}), analog_sample, $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.latch_g_r));".format(tap, tap), "    end", ""]
    lines += ["    initial begin", "        #( 7000.000000 ); $finish;", "    end", "endmodule", ""]
    return "\n".join(lines)


def prepare_xa(label: str, source: dict) -> dict:
    source_dir = RUN_ROOT / label.lower() / "source_hspice"
    directory = RUN_ROOT / label.lower() / "vcs_xa"
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    trace = bfe1_frontend.parse_ascii_tr0(source_dir / "bfe3_p0t_source.tr0")
    times, columns = trace["columns"]["time"], trace["columns"]
    vdd_sense = columns[bfe1_frontend.label_for("vdd_monitored")]
    schedules, initial_states, initial_values, ledger = {}, {}, {}, {}
    for tap in range(30):
        xor = columns[bfe1_frontend.label_for("xor_{}".format(tap))]
        initial, events = bridge.threshold_schedule(times, xor, vdd_sense)
        schedules[tap], initial_states[tap] = events, initial
        initial_values[tap] = {"xor_v": float(xor[0]), "vdd_sense_v": float(vdd_sense[0]), "threshold_v": 0.5 * float(vdd_sense[0]), "safe_d_v": 0.95 if initial else 0.0}
        ledger["tap_{:02d}".format(tap)] = {"initial": {"logic_state": initial, **initial_values[tap]}, "crossings": [{"time_ps": event[0] * 1.0e12, "logic_state": event[1], "direction": event[2]} for event in events]}
    (directory / "safe_d_crossing_ledger.json").write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (directory / "bfe3_p0t_ams_wrapper.sp").write_text(bridge.render_wrapper(source["scenario_id"], columns, times), encoding="ascii")
    (directory / "tb_bfe2_l1a_r_vcs_xa.sv").write_text(render_tb(schedules, initial_states, initial_values, source["g_close_ps"]), encoding="ascii")
    (directory / "xa.cfg").write_text("set_sim_level 7\nset_waveform -format fsdb\n" + "\n".join(["probe_waveform_voltage vdd_sense", "probe_waveform_voltage vdd_safe", "probe_waveform_voltage latch_g_r"] + ["probe_waveform_voltage safe_d_r_{:02d}".format(tap) for tap in range(30)] + ["probe_waveform_voltage q_{:02d}".format(tap) for tap in range(30)]) + "\n", encoding="ascii")
    (directory / "vcsAD.init").write_text("bus_format [%d];\nuse_spice -cell bfe2_l1a_r_ams;\nchoose xa -hspice {} -c {} -o {}/xa;\n".format(directory / "bfe3_p0t_ams.sp", directory / "xa.cfg", directory), encoding="ascii")
    (directory / "bfe3_p0t_ams.sp").write_text(bridge.render_top_deck(directory).replace("bfe2_l1a_r_ams_wrapper.sp", "bfe3_p0t_ams_wrapper.sp"), encoding="ascii")
    return {"phase_label": label, "launch_ps": source["launch_ps"], "g_close_ps": source["g_close_ps"], "directory": str(directory), "source_tr0_sha256": source["tr0_sha256"], "safe_d_ledger_sha256": sha256(directory / "safe_d_crossing_ledger.json")}


def run_xa(meta: dict) -> dict:
    directory = Path(meta["directory"])
    vcs = shutil.which("vcs")
    if not vcs:
        raise RuntimeError("VCS is unavailable in the configured container")
    command = [vcs, "-full64", "-sverilog", "-timescale=1ps/1ps", "-ad=vcsAD.init", "-debug_access+all", "-o", "simv", "tb_bfe2_l1a_r_vcs_xa.sv"]
    compile_result = subprocess.run(command, cwd=str(directory), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=900)
    (directory / "compile.log").write_text(compile_result.stdout, encoding="utf-8", errors="replace")
    if compile_result.returncode != 0:
        return dict(meta, compile_returncode=compile_result.returncode, run_returncode=None, cosim_marker=False, xa_version_marker=False)
    run_result = subprocess.run(["./simv"], cwd=str(directory), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=1800)
    (directory / "run.log").write_text(run_result.stdout, encoding="utf-8", errors="replace")
    boundary = directory / "xa_boundary_samples.csv"
    return dict(meta, compile_returncode=0, run_returncode=run_result.returncode, cosim_marker="Start Cosim VCS-Analog Processing" in run_result.stdout, xa_version_marker="PrimeSim XA" in run_result.stdout, boundary_csv_sha256=sha256(boundary) if boundary.is_file() else None)


def main() -> int:
    p0r = read_json(P0R_ANALYSIS)
    p0r_manifest = read_json(P0R_MANIFEST)
    if p0r.get("gate") != "BFE3_P0R_M_PHASE_OVERLAP" or p0r.get("worst_phase", {}).get("M") != 287:
        raise ValueError("P0T requires the retained P0R LATE M=287 overlap evidence")
    if p0r_manifest.get("latch_cell") != "LATQ_X0P5M_A9TR40" or p0r_manifest.get("vdd_safe_v") != 0.95:
        raise ValueError("P0R safe-domain contract drifted")
    config = read_json(CONFIG)
    hspice = Path(config["hspice"])
    version = run_dc_sweep.hspice_version(hspice)
    if config["expected_hspice_version"] not in version:
        raise RuntimeError("unexpected HSPICE version")
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    sources = [run_source(label, launch, hspice, version) for label, launch, _role in NEW_LAUNCHES]
    xa_meta = [prepare_xa(label, source) for (label, _launch, _role), source in zip(NEW_LAUNCHES, sources)]
    xa_results = [run_xa(meta) for meta in xa_meta]
    manifest = {
        "schema_version": 1, "stage": "B-FE3-P0T", "source_scenario": "P0R LATE phase=500 ps, 0.95->0.86 V L2",
        "launch_schedule": [{"label": label, "launch_ps": launch, "g_close_ps": launch + SAMPLE_CLOSE_PS, "role": role} for label, launch, role in LAUNCHES],
        "new_launches": [{"label": label, "launch_ps": launch} for label, launch, _role in NEW_LAUNCHES], "dense_scan": False,
        "droop_onset_ps": DROOP_ONSET_PS, "droop_duration_ps": 3002.0, "sample_close_ps": SAMPLE_CLOSE_PS,
        "normal_m_envelope": {"min": 260, "max": 315}, "baseline_p0r_m": 287,
        "tap_count": 30, "rvt_prefix": 4, "lvt_prefix": 0, "latch_cell": "LATQ_X0P5M_A9TR40", "vdd_safe_v": 0.95,
        "decision_feature": "M=sum(i*q[i]), i=0..29", "forbidden": ["RTL", "self_calibration", "N", "T", "lookup_table", "filter", "bubble_repair", "multi_feature_fusion"],
        "p0r_analysis_sha256": sha256(P0R_ANALYSIS), "p0r_manifest_sha256": sha256(P0R_MANIFEST),
        "source_hspice": sources, "xa_scenarios": xa_results,
        "container_tools": {"vcs": os.environ.get("VCS_HOME", "unknown"), "xa": os.environ.get("PRIMESIM_XA_HOME", os.environ.get("XA_HOME", "unknown"))},
        "stop_after_stage": True, "next_stage_authorized": False,
    }
    path = ROOT / "BFE3_P0T_MANIFEST.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if all(x["compile_returncode"] == 0 and x["run_returncode"] == 0 and x["cosim_marker"] and x["xa_version_marker"] for x in xa_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
