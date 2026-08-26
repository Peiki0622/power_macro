#!/usr/bin/env python3
"""B-FE4-CALN0 paired SMIC40LL Monte Carlo startup-calibration study.

Only the source RVT/LVT/XOR front end is statistically varied through the
vendor HSPICE ``MOS_MC`` section.  The already-validated Level-0 to real
LATQ-to-real-DFF capture path remains a fixed 0.95 V safe-domain replay.  A
normal and a 0.95-to-0.92 V (+75 ps, 3002 ps) source deck share each seed and
must have identical HSPICE MC random-vector fingerprints before either result
is accepted.
"""

import csv
import hashlib
import json
import math
import multiprocessing as mp
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe4_caln0_self_calibration"
TAPS = 30
SEEDS = tuple(range(41001, 41031))
WORKERS = 4
VDD = 0.95
DROOP_V = 0.92
DROP_START_PS = 21075.0
DROP_TOTAL_PS = 3002.0
NORMAL_STOP_PS = 102000.0
DROOP_STOP_PS = 62000.0
G_FALL_OFFSET_PS = 534.524618567
DFF_OFFSET_PS = 1534.524618567
SAMPLE_READ_PS = 100.0
THRESHOLD = 0.5 * VDD
RAIL_LOW = 0.1 * VDD
RAIL_HIGH = 0.9 * VDD

sys.path.insert(0, str(FTC_ROOT / "scripts"))
sys.path.insert(0, str(FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "l1a_r_vcs_xa"))
import bfe1_frontend  # noqa: E402
import run_bfe2_l1a_r_vcs_xa as bridge  # noqa: E402


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


def spice(value):
    return "{:.12e}".format(float(value))


def system_edges(stop_ps):
    return tuple((1000.0 + 10000.0 * index, "rise" if index % 2 == 0 else "fall")
                 for index in range(int((stop_ps - 1000.0) // 10000.0) + 1))


def system_pwl(stop_ps):
    points, state = [(0.0, 0.0)], 0.0
    for edge_ps, _ in system_edges(stop_ps):
        points.extend(((edge_ps - 0.5, state), (edge_ps + 0.5, VDD if state == 0.0 else 0.0)))
        state = VDD if state == 0.0 else 0.0
    points.append((stop_ps, state))
    return "V_SCLK s_clk vss_a PWL({})".format(" ".join("{} {}".format(spice(t * 1e-12), spice(v)) for t, v in points))


def host_cells(cells):
    """The local container paths are the authoritative execution paths."""
    for key in ("rvt_cdl", "lvt_cdl"):
        if not Path(cells["source_files"][key]).is_file():
            raise FileNotFoundError("missing selected cell CDL: {}".format(cells["source_files"][key]))
    return cells


def source_deck(cells, model, condition, seed):
    stop_ps = NORMAL_STOP_PS if condition == "normal" else DROOP_STOP_PS
    scenario = {
        "scenario_id": "BFE4-CALN0-{}-{}".format(condition, seed),
        "baseline_v": VDD,
        "droop_v": None if condition == "normal" else DROOP_V,
        "phase_ps": None if condition == "normal" else DROP_START_PS - 1000.0,
    }
    deck = bfe1_frontend.render_deck(cells, scenario, model)
    deck = re.sub(r"V_SCLK s_clk vss_a PWL\([^\n]+", system_pwl(stop_ps), deck)
    deck = re.sub(r"\.lib \"[^\"]+\" tt", '.lib "{}" MOS_MC'.format(model), deck)
    # The proprietary MC waveform file is deliberately not consumed.  Native
    # .measure rows are stable CSV evidence and directly represent the frozen
    # Level-0 input state at every LATQ closing boundary.
    deck = deck.replace(".option post=2 probe nomod measform=3 measdgt=10 runlvl=3",
                        ".option post=0 nomod measform=3 measdgt=10 runlvl=3 seed={}".format(seed))
    deck = re.sub(r" 7\.000000000000e-09\)", " {})".format(spice(stop_ps * 1e-12)), deck, count=1)
    deck = re.sub(r"\.probe tran[^\n]*\n", "", deck)
    deck = re.sub(r"\.tran\s+[^\s]+\s+[^\s]+", ".tran 1.000000000000e-12 {} sweep monte=2".format(spice(stop_ps * 1e-12)), deck)
    measures = []
    for index, dff_rise in dff_rises(stop_ps):
        latch_close = dff_rise - 1000.0
        measures.append(".measure tran m_rail_{:02d} find v(vdd_monitored) at={}".format(index, spice(latch_close * 1e-12)))
        for tap in range(TAPS):
            measures.append(".measure tran m_x_{:02d}_{:02d} find v(xor_{}) at={}".format(index, tap, tap, spice(latch_close * 1e-12)))
    deck = deck.replace(".end", "\n".join(measures) + "\n.end")
    if deck.count("MOS_MC") != 1 or "monte=2" not in deck or "seed={}".format(seed) not in deck:
        raise ValueError("failed to render paired MC source deck")
    return deck


def read_measurements(path, stop_ps):
    """Load native HSPICE measure CSV and return only MC index 2.

    ``*.mt0.csv`` is documented CSV output, unlike the proprietary waveform
    format.  Measurements are taken exactly at LATQ close, so thresholding
    each XOR against the simultaneously measured monitored rail is the
    frozen Level-0 decision delivered into the real capture chain.
    """
    data_lines = [line for line in path.read_text(encoding="ascii", errors="strict").splitlines()
                  if line and not line.startswith("$") and not line.startswith(".TITLE")]
    rows = list(csv.DictReader(data_lines))
    by_index = {int(row["index"]): row for row in rows}
    if set(by_index) != {1, 2}:
        raise ValueError("HSPICE measure table must contain nominal and random rows: {}".format(path))
    random_row, samples = by_index[2], {}
    for index, dff_rise in dff_rises(stop_ps):
        rail_key = "m_rail_{:02d}".format(index)
        if rail_key not in random_row:
            raise ValueError("measure table lacks {}".format(rail_key))
        rail = float(random_row[rail_key])
        xor = []
        for tap in range(TAPS):
            key = "m_x_{:02d}_{:02d}".format(index, tap)
            if key not in random_row:
                raise ValueError("measure table lacks {}".format(key))
            xor.append(float(random_row[key]))
        if not math.isfinite(rail) or not all(math.isfinite(value) for value in xor):
            raise ValueError("measure table contains non-finite Level-0 sample")
        latch_close = dff_rise - 1000.0
        samples[index] = {"dff_rise_ps": dff_rise, "latch_close_ps": latch_close,
                          "aperture_open_ps": 0.0 if index == 0 else latch_close - 1250.0,
                          "rail_v": rail, "xor_v": xor,
                          "bits": [1 if value > 0.5 * rail else 0 for value in xor]}
    return samples


def mc_signature(path):
    """Hash the index-2 random vector emitted by this HSPICE version.

    W-2024.09 writes the variation report as ``*.mc0.csv``.  Its index-2
    record contains the full ordered global and local random-variable vector,
    so hashing that record is a direct check that the paired decks used the
    same process realization while intentionally allowing their stimuli to
    differ.
    """
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        if re.match(r"^2,", line):
            return hashlib.sha256(line[2:].encode("ascii")).hexdigest()
    raise ValueError("MC random sample index=2 is absent: {}".format(path))


def validate_listing(path):
    text = path.read_text(encoding="utf-8", errors="replace").lower()
    if "job concluded" not in text or "**error**" in text:
        raise RuntimeError("HSPICE listing is not clean: {}".format(path))
    if "monte carlo simulation is detected" not in text:
        raise RuntimeError("HSPICE did not enter Monte Carlo: {}".format(path))


def run_source(seed, condition, cells, model, hspice):
    directory = RUN_ROOT / "instances" / "seed_{:05d}".format(seed) / condition / "source_hspice"
    directory.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    deck = directory / "source.sp"
    deck.write_text(source_deck(cells, model, condition, seed), encoding="ascii")
    # The local project Python is 3.6, where universal_newlines is the
    # compatible spelling of text=True while preserving decoded HSPICE logs.
    result = subprocess.run([hspice, deck.name, "-o", "source"], cwd=directory,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            universal_newlines=True, check=False, timeout=2400)
    (directory / "hspice_command.log").write_text(result.stdout, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError("HSPICE {} seed {} failed".format(condition, seed))
    listing, measures = directory / "source.lis", directory / "source.mt0.csv"
    # PrimeSim HSPICE W-2024.09 exports the MC vector table as CSV rather
    # than the legacy extensionless mc0 report used by older flows.
    mc0 = directory / "source.mc0.csv"
    if not measures.is_file() or not mc0.is_file():
        raise RuntimeError("HSPICE {} seed {} missed MC artifacts".format(condition, seed))
    validate_listing(listing)
    stop_ps = NORMAL_STOP_PS if condition == "normal" else DROOP_STOP_PS
    level0_samples = read_measurements(measures, stop_ps)
    return level0_samples, {
        "seed": seed, "condition": condition, "deck_sha256": sha256(deck), "measurements_sha256": sha256(measures),
        "mc0_sha256": sha256(mc0), "mc_random_signature": mc_signature(mc0),
        "measure_row_index": 2, "level0_sample_count": len(level0_samples), "run_dir": str(directory),
    }


def dff_rises(stop_ps):
    # The testbench first raises DFF_CK 1534.5246 ps after the 1 ns system
    # edge, then repeats at the frozen 400 MHz period.
    rise, index, result = 1000.0 + DFF_OFFSET_PS, 0, []
    while rise < stop_ps:
        result.append((index, rise)); index += 1; rise += 2500.0
    return result


def monitored_rail_points(condition, stop_ps):
    """Return the frozen source-rail PWL for the diagnostic vdd_sense probe."""
    if condition == "normal":
        return ((0.0, VDD), (stop_ps, VDD))
    return ((0.0, VDD), (DROP_START_PS, VDD), (DROP_START_PS + 1.0, DROOP_V),
            (DROP_START_PS + DROP_TOTAL_PS - 1.0, DROOP_V),
            (DROP_START_PS + DROP_TOTAL_PS, VDD), (stop_ps, VDD))


def render_wrapper(condition, stop_ps):
    ports = ["safe_d_{}".format(tap) for tap in range(TAPS)] + ["latch_g", "dff_ck"]
    ports += ["q_lat_{}".format(tap) for tap in range(TAPS)] + ["q_ff_{}".format(tap) for tap in range(TAPS)]
    def pwl(name, node, points):
        return "V_{} {} 0 PWL({})".format(name, node, " ".join("{} {}".format(spice(t), spice(v)) for t, v in points))
    lines = ["* B-FE4 frozen real LATQ to real DFF wrapper.", ".SUBCKT bfe4_ams \\", "+ " + " \\\n+".join(ports),
             pwl("vdd_sense", "vdd_sense", ((time_ps * 1e-12, value) for time_ps, value in monitored_rail_points(condition, stop_ps))),
             "V_VDD_SAFE vdd_safe 0 DC 9.500000000000e-01", "V_VSS_SAFE vss_safe 0 DC 0", "V_RESET dff_reset 0 DC 0"]
    for tap in range(TAPS):
        lines.append("E_SAFE_D_{:02d} safe_d_r_{:02d} 0 safe_d_{} 0 1".format(tap, tap, tap))
    lines += ["E_G latch_g_r 0 latch_g 0 1", "E_CK dff_ck_r 0 dff_ck 0 1"]
    for tap in range(TAPS):
        lines += ["XLAT_{:02d} q_lat_r_{:02d} vdd_safe vdd_safe vss_safe vss_safe safe_d_r_{:02d} latch_g_r LATQ_X0P5M_A9TR40".format(tap, tap, tap),
                  "XDFF_{:02d} q_ff_r_{:02d} vdd_safe vdd_safe vss_safe vss_safe dff_ck_r q_lat_r_{:02d} dff_reset DFFRPQ_X0P5M_A9TR40".format(tap, tap, tap),
                  "E_QL_{:02d} q_lat_{} 0 q_lat_r_{:02d} 0 1".format(tap, tap, tap),
                  "E_QF_{:02d} q_ff_{} 0 q_ff_r_{:02d} 0 1".format(tap, tap, tap)]
    probe = ["v(vdd_sense)", "v(vdd_safe)", "v(latch_g_r)", "v(dff_ck_r)"]
    probe += ["v(q_lat_r_{:02d})".format(tap) for tap in range(TAPS)]
    probe += ["v(q_ff_r_{:02d})".format(tap) for tap in range(TAPS)]
    lines += [".probe tran {}".format(" ".join(probe)), ".tran 1p {}".format(spice(stop_ps * 1e-12)), ".ENDS bfe4_ams", ""]
    return "\n".join(lines)


def level0_schedule(level0_samples, tap):
    """Drive a real LATQ with its HSPICE-resolved value during its aperture.

    The value measured at an aperture's closing boundary is established at
    that aperture's opening boundary.  This preserves the verified 50/400 MHz
    latch/DFF timing while ensuring every real latch sees a settled,
    rail-resolved Level-0 decision before it closes.
    """
    ordered = [level0_samples[index] for index in sorted(level0_samples)]
    if not ordered or ordered[0]["aperture_open_ps"] != 0.0:
        raise ValueError("Level-0 sample sequence lacks the initial aperture")
    return ordered[0]["bits"][tap], [(sample["aperture_open_ps"] * 1e-12, sample["bits"][tap], "sampled")
                                       for sample in ordered[1:]]


def render_tb(level0_samples, stop_ps):
    schedules = {tap: level0_schedule(level0_samples, tap) for tap in range(TAPS)}
    ports = ["safe_d_{}".format(tap) for tap in range(TAPS)]
    qports = ["q_lat_{}".format(tap) for tap in range(TAPS)] + ["q_ff_{}".format(tap) for tap in range(TAPS)]
    lines = ["`timescale 1ps/1ps", "module bfe4_tb;", *["logic {};".format(port) for port in ports],
             "logic latch_g;", "logic dff_ck;", *["wire {};".format(port) for port in qports], "bfe4_ams u_ams (",
             ",\n".join(".{}({})".format(port, port) for port in ports + ["latch_g", "dff_ck"] + qports), ");",
             "initial begin latch_g=1'b1; #(1534.524618567) latch_g=1'b0; forever begin #(1250) latch_g=1'b1; #(1250) latch_g=1'b0; end end",
             "initial begin dff_ck=1'b0; #(2534.524618567) dff_ck=1'b1; forever begin #(1250) dff_ck=1'b0; #(1250) dff_ck=1'b1; end end"]
    for tap, port in enumerate(ports):
        initial, events = schedules[tap]
        lines += ["initial begin", "{}=1'b{};".format(port, initial)]
        previous = 0.0
        for time_s, state, _ in events:
            current = time_s * 1e12
            lines.append("#({:.12f}) {}=1'b{};".format(current - previous, port, state)); previous = current
        lines += ["end"]
    lines += ["integer fd;", "initial begin fd=$fopen(\"xa_dff_samples.csv\",\"w\");", "$fwrite(fd,\"sample_index,sample_time_ps,nearest_edge_ps,polarity,tap,q_lat_v,q_ff_v,vdd_safe_v\\n\");"]
    previous = 0.0
    for index, edge in dff_rises(stop_ps):
        lines.append("#({:.12f});".format(edge - previous)); previous = edge
        lines.append("#({:.12f});".format(SAMPLE_READ_PS)); previous += SAMPLE_READ_PS
        nearest, polarity = min(system_edges(stop_ps), key=lambda item: abs(item[0] - edge))
        for tap in range(TAPS):
            lines.append("$fwrite(fd,\"{},%.6f,{:.6f},{},%d,%.9f,%.9f,%.9f\\n\",$realtime,{},$snps_get_volt(bfe4_tb.u_ams.q_lat_r_{:02d}),$snps_get_volt(bfe4_tb.u_ams.q_ff_r_{:02d}),$snps_get_volt(bfe4_tb.u_ams.vdd_safe));".format(index, nearest, polarity, tap, tap, tap))
    lines += ["$fclose(fd); end", "initial begin #({:.12f}) $finish; end".format(stop_ps), "endmodule", ""]
    return "\n".join(lines)


def run_xa(seed, condition, level0_samples, cells, model, vcs):
    stop_ps = NORMAL_STOP_PS if condition == "normal" else DROOP_STOP_PS
    directory = RUN_ROOT / "instances" / "seed_{:05d}".format(seed) / condition / "vcs_xa"
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "bfe4_ams_wrapper.sp").write_text(render_wrapper(condition, stop_ps), encoding="ascii")
    (directory / "tb_bfe4.sv").write_text(render_tb(level0_samples, stop_ps), encoding="ascii")
    (directory / "xa.cfg").write_text("set_sim_level 7\nset_waveform -format fsdb\n", encoding="ascii")
    (directory / "vcsAD.init").write_text("bus_format [%d];\nuse_spice -cell bfe4_ams;\nchoose xa -hspice {} -c {} -o {}/xa;\n".format(directory / "bfe4_ams.sp", directory / "xa.cfg", directory), encoding="ascii")
    (directory / "bfe4_ams.sp").write_text("* B-FE4 fixed safe capture deck.\n.option post=1 probe\n.lib '{}' tt\n.include '{}'\n.include '{}'\n.include '{}'\n.include '{}'\n.tran 1p {}\n.end\n".format(model, cells["source_files"]["rvt_cdl"], cells["source_files"]["lvt_cdl"], FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "bfe4_ams_wrapper.sp", spice(stop_ps * 1e-12)), encoding="ascii")
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    # Keep the run callable under the workspace's Python 3.6 interpreter.
    compile_result = subprocess.run([vcs, "-full64", "-sverilog", "-timescale=1ps/1ps", "-ad=vcsAD.init", "-debug_access+all", "-o", "simv", "tb_bfe4.sv"], cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=1800)
    (directory / "compile.log").write_text(compile_result.stdout, encoding="utf-8", errors="replace")
    if compile_result.returncode:
        raise RuntimeError("VCS compile {} seed {} failed".format(condition, seed))
    run_result = subprocess.run(["./simv"], cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=3600)
    (directory / "run.log").write_text(run_result.stdout, encoding="utf-8", errors="replace")
    evidence = directory / "xa_dff_samples.csv"
    if run_result.returncode or not evidence.is_file():
        raise RuntimeError("VCS/XA {} seed {} failed".format(condition, seed))
    return evidence, {"run_dir": str(directory), "compile_log_sha256": sha256(directory / "compile.log"), "run_log_sha256": sha256(directory / "run.log"), "samples_sha256": sha256(evidence), "cosim_marker": "Start Cosim VCS-Analog Processing" in run_result.stdout}


def read_samples(path):
    rows = []
    with path.open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            row["sample_index"], row["tap"] = int(row["sample_index"]), int(row["tap"])
            for key in ("sample_time_ps", "nearest_edge_ps", "q_lat_v", "q_ff_v", "vdd_safe_v"):
                row[key] = float(row[key])
            rows.append(row)
    return rows


def designated_rises(rows, stop_ps):
    values = {}
    for index, edge in dff_rises(stop_ps):
        tap_rows = {row["tap"]: row for row in rows if row["sample_index"] == index}
        if set(tap_rows) != set(range(TAPS)):
            raise ValueError("DFF sample {} lacks 30 taps".format(index))
        nearest, polarity = min(system_edges(stop_ps), key=lambda item: abs(item[0] - edge))
        if polarity != "rise" or abs(edge - nearest - DFF_OFFSET_PS) > 0.01:
            continue
        bits = [1 if tap_rows[tap]["q_ff_v"] > THRESHOLD else 0 for tap in range(TAPS)]
        q_lat_mid = [tap for tap in range(TAPS) if RAIL_LOW < tap_rows[tap]["q_lat_v"] < RAIL_HIGH]
        q_ff_mid = [tap for tap in range(TAPS) if RAIL_LOW < tap_rows[tap]["q_ff_v"] < RAIL_HIGH]
        safe_bad = [tap for tap in range(TAPS) if abs(tap_rows[tap]["vdd_safe_v"] - VDD) > 1e-6]
        values[nearest] = {"sample_index": index, "sample_time_ps": tap_rows[0]["sample_time_ps"], "M_FF": sum(tap * bit for tap, bit in enumerate(bits)), "q_ff": "".join(str(bit) for bit in reversed(bits)), "q_ff_rail_resolved": not q_ff_mid and not safe_bad, "latq_rail_resolved": not q_lat_mid, "q_ff_mid_rail_taps": q_ff_mid, "latq_mid_rail_taps": q_lat_mid, "safe_rail_bad_taps": safe_bad}
    return values


def round_mean(values):
    return int(math.floor(sum(values) / len(values) + 0.5))


def run_instance(seed, cells, model, hspice, vcs):
    normal_trace, normal_source = run_source(seed, "normal", cells, model, hspice)
    droop_trace, droop_source = run_source(seed, "droop", cells, model, hspice)
    if normal_source["mc_random_signature"] != droop_source["mc_random_signature"]:
        raise RuntimeError("normal/droop MC realization differs for seed {}".format(seed))
    normal_csv, normal_xa = run_xa(seed, "normal", normal_trace, cells, model, vcs)
    droop_csv, droop_xa = run_xa(seed, "droop", droop_trace, cells, model, vcs)
    normal = designated_rises(read_samples(normal_csv), NORMAL_STOP_PS)
    droop = designated_rises(read_samples(droop_csv), DROOP_STOP_PS)
    calibration_edges, test_edge, droop_edge = (1000.0, 21000.0, 41000.0, 61000.0), 81000.0, 21000.0
    if any(edge not in normal for edge in calibration_edges + (test_edge,)) or droop_edge not in droop:
        raise RuntimeError("designated rise set is incomplete for seed {}".format(seed))
    calibration = [normal[edge] for edge in calibration_edges]
    normal_test, droop_test = normal[test_edge], droop[droop_edge]
    all_captures = calibration + [normal_test, droop_test]
    if not all(item["q_ff_rail_resolved"] and item["latq_rail_resolved"] for item in all_captures):
        raise RuntimeError("unresolved LATQ/DFF rail state for seed {}".format(seed))
    m_cal = [item["M_FF"] for item in calibration]
    m_ref = round_mean(m_cal)
    return {"seed": seed, "mc_random_signature": normal_source["mc_random_signature"], "M_CAL": m_cal, "M_REF": m_ref,
            "M_NORMAL": normal_test["M_FF"], "M_DROOP": droop_test["M_FF"],
            "DeltaM_NORMAL": m_ref - normal_test["M_FF"], "DeltaM_DROOP": m_ref - droop_test["M_FF"],
            "normal_calibration": calibration, "normal_test": normal_test, "droop_test": droop_test,
            "source": {"normal": normal_source, "droop": droop_source}, "xa": {"normal": normal_xa, "droop": droop_xa}}


def stats(values):
    ordered = sorted(values)
    def percentile(fraction):
        position = (len(ordered) - 1) * fraction
        low, high = int(math.floor(position)), int(math.ceil(position))
        return ordered[low] + (ordered[high] - ordered[low]) * (position - low)
    return {"count": len(values), "mean": sum(values) / len(values), "min": min(values), "max": max(values), "p05": percentile(0.05), "p50": percentile(0.50), "p95": percentile(0.95)}


def plot_distribution(rows, absolute, png, pdf, margin):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    normal_key, droop_key = ("M_NORMAL", "M_DROOP") if absolute else ("DeltaM_NORMAL", "DeltaM_DROOP")
    normal, droop = [row[normal_key] for row in rows], [row[droop_key] for row in rows]
    fig, axis = plt.subplots(figsize=(7.0, 4.6), dpi=180)
    violin = axis.violinplot([normal, droop], positions=(1, 2), showmeans=True, showextrema=True)
    for body, color in zip(violin["bodies"], ("#2878B5", "#C64E39")):
        body.set_facecolor(color); body.set_edgecolor(color); body.set_alpha(0.42)
    for index, (n_value, d_value) in enumerate(zip(normal, droop)):
        axis.plot((1, 2), (n_value, d_value), color="#777777", alpha=0.28, linewidth=0.6, zorder=1)
        axis.scatter((1, 2), (n_value, d_value), color=("#2878B5", "#C64E39"), s=12, zorder=2)
    ns, ds = stats(normal), stats(droop)
    axis.set_xticks((1, 2), ("Normal 0.95 V", "Droop 0.92 V"))
    axis.set_ylabel("M_FF" if absolute else "Delta M = M_REF - M_FF")
    axis.set_title("B-FE4-CALN0 " + ("absolute M_FF" if absolute else "self-calibrated Delta M"))
    axis.grid(axis="y", alpha=0.25)
    annotation = "normal: mean={:.2f}, [{:.0f},{:.0f}], P05/P95={:.1f}/{:.1f}\n".format(ns["mean"], ns["min"], ns["max"], ns["p05"], ns["p95"])
    annotation += "droop: mean={:.2f}, [{:.0f},{:.0f}], P05/P95={:.1f}/{:.1f}\nG_{}={:.2f}".format(ds["mean"], ds["min"], ds["max"], ds["p05"], ds["p95"], "ABS" if absolute else "CAL", margin)
    axis.text(0.03, 0.97, annotation, transform=axis.transAxes, va="top", fontsize=8, bbox={"facecolor": "white", "edgecolor": "#999999", "alpha": 0.92})
    fig.tight_layout(); fig.savefig(png); fig.savefig(pdf); plt.close(fig)


def publish(rows, cells, hspice, vcs):
    normal, droop = [row["M_NORMAL"] for row in rows], [row["M_DROOP"] for row in rows]
    dnormal, ddroop = [row["DeltaM_NORMAL"] for row in rows], [row["DeltaM_DROOP"] for row in rows]
    margins = {"W_ABS": max(normal) - min(normal), "W_CAL": max(dnormal) - min(dnormal),
               "G_ABS": min(normal) - max(droop), "G_CAL": min(ddroop) - max(dnormal)}
    all_resolved = all(item["normal_test"]["q_ff_rail_resolved"] and item["droop_test"]["q_ff_rail_resolved"] for item in rows)
    overlap = margins["G_ABS"] <= 0
    beneficial = margins["G_ABS"] > 0 and margins["W_CAL"] <= 0.5 * margins["W_ABS"] and margins["G_CAL"] > margins["G_ABS"]
    if not all_resolved:
        gate = "BFE4_CALN0_FAIL"
    elif overlap and margins["G_CAL"] > 0:
        gate = "BFE4_CALN0_SELF_CALIBRATION_NECESSITY_PASS"
    elif beneficial:
        gate = "BFE4_CALN0_CALIBRATION_BENEFICIAL_NOT_NECESSARY"
    else:
        gate = "BFE4_CALN0_INCONCLUSIVE"
    csv_rows = []
    for item in rows:
        row = {"seed": item["seed"], "mc_random_signature": item["mc_random_signature"], "M_REF_i": item["M_REF"], "M_NORMAL_i": item["M_NORMAL"], "M_DROOP_i": item["M_DROOP"], "DeltaM_NORMAL_i": item["DeltaM_NORMAL"], "DeltaM_DROOP_i": item["DeltaM_DROOP"], "q_ff_normal": item["normal_test"]["q_ff"], "q_ff_droop": item["droop_test"]["q_ff"], "normal_q_ff_rail_resolved": item["normal_test"]["q_ff_rail_resolved"], "droop_q_ff_rail_resolved": item["droop_test"]["q_ff_rail_resolved"]}
        row.update({"M_CAL_{}".format(index): value for index, value in enumerate(item["M_CAL"])})
        csv_rows.append(row)
    fields = list(csv_rows[0])
    with (ROOT / "BFE4_CALN0_RESULTS.csv").open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(csv_rows)
    (ROOT / "BFE4_CALN0_RESULTS.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    plot_distribution(rows, True, ROOT / "BFE4_CALN0_ABSOLUTE_MFF_DISTRIBUTION.png", ROOT / "BFE4_CALN0_ABSOLUTE_MFF_DISTRIBUTION.pdf", margins["G_ABS"])
    plot_distribution(rows, False, ROOT / "BFE4_CALN0_SELFCAL_DELTA_M_DISTRIBUTION.png", ROOT / "BFE4_CALN0_SELFCAL_DELTA_M_DISTRIBUTION.pdf", margins["G_CAL"])
    summary = {"instance_count": len(rows), "absolute_normal": stats(normal), "absolute_droop": stats(droop), "calibrated_normal": stats(dnormal), "calibrated_droop": stats(ddroop), "margins": margins, "fixed_absolute_threshold_overlap": overlap, "calibration_beneficial": beneficial, "all_q_ff_rail_resolved": all_resolved, "gate": gate}
    manifest = {"schema_version": 1, "stage": "B-FE4-CALN0", "gate": gate, "verification_mode": "local HSPICE MOS_MC source + local VCS/PrimeSim XA frozen real LATQ/DFF", "tools": {"hspice": hspice, "vcs": vcs}, "monte_carlo": {"instances": len(rows), "seed_list": list(SEEDS), "per_seed_pairing": "normal and droop use same HSPICE seed and verified MC random-vector signature", "random_sample": "index=2 after HSPICE nominal index=1"}, "method_point": {"anchor_v": VDD, "anchor_scope": "healthy methodology anchor only; not a universal chip nominal claim", "droop_v": DROOP_V, "relative_phase_ps": 75.0, "duration_ps": DROP_TOTAL_PS}, "frozen": {"tap_count": 30, "rvt_prefix": 4, "lvt_prefix": 0, "xor_cell": "XOR2_X0P5M_A9TL40", "latch_cell": cells["latch"]["cell"], "dff_cell": cells["dff"]["cell"], "system_clock_mhz": 50.0, "probe_clock_mhz": 400.0, "gfall_offset_ps": G_FALL_OFFSET_PS, "dff_offset_ps": DFF_OFFSET_PS, "level0_restore": "source XOR threshold replay at 0.5*VDD_SENSE"}, "calibration": {"designated_normal_rise_edges_ps": [1000.0, 21000.0, 41000.0, 61000.0], "normal_test_rise_ps": 81000.0, "droop_test_rise_ps": 21000.0, "M_REF": "round_half_up(mean(M_CAL[0:4]))"}, "summary": summary, "forbidden": ["temperature_sweep", "PVT_sweep", "DVFS", "threshold_optimization", "online_adaptation", "clock_glitch", "LUT", "multi_feature_fusion", "latch_aperture_research"], "stop_after_stage": True, "next_stage_authorized": False}
    manifest_path = ROOT / "BFE4_CALN0_MANIFEST.json"; manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    analysis = {"schema_version": 1, "stage": "B-FE4-CALN0", "gate": gate, "summary": summary, "instances": rows, "criteria": {"necessity": "G_ABS <= 0 and G_CAL > 0", "beneficial": "G_ABS > 0, W_CAL <= 0.5*W_ABS, and G_CAL > G_ABS"}, "manifest_sha256": sha256(manifest_path), "stop_after_stage": True, "next_stage_authorized": False}
    analysis_path = ROOT / "BFE4_CALN0_ANALYSIS.json"; analysis_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = ["# B-FE4-CALN0 per-chip startup self-calibration Monte Carlo", "", "Gate: `{}`".format(gate), "", "Thirty paired SMIC40LL `MOS_MC` process instances were run locally. Each seed produced one 0.95 V normal and one 0.95->0.92 V, +75 ps, 3002 ps droop source realization; their index-2 HSPICE random-vector signatures were required to match. The 0.95 V point is a healthy methodology anchor, not a claim about all target-chip nominal voltages.", "", "| Metric | Value |", "|---|---:|", "| W_ABS | {:.3f} |".format(margins["W_ABS"]), "| W_CAL | {:.3f} |".format(margins["W_CAL"]), "| G_ABS | {:.3f} |".format(margins["G_ABS"]), "| G_CAL | {:.3f} |".format(margins["G_CAL"]), "", "| Domain | Normal mean [min,max] | Droop mean [min,max] |", "|---|---|---|"]
    for label, left, right in (("Absolute M_FF", stats(normal), stats(droop)), ("Self-calibrated Delta M", stats(dnormal), stats(ddroop))):
        report.append("| {} | {:.2f} [{:.0f},{:.0f}] | {:.2f} [{:.0f},{:.0f}] |".format(label, left["mean"], left["min"], left["max"], right["mean"], right["min"], right["max"]))
    report += ["", "Fixed absolute threshold overlap: `{}`. All final DFF samples rail-resolved: `{}`. Calibration beneficial under the predeclared 0.5 width ratio: `{}`.".format(overlap, all_resolved, beneficial), "", "Only two paper figures are emitted: `BFE4_CALN0_ABSOLUTE_MFF_DISTRIBUTION` and `BFE4_CALN0_SELFCAL_DELTA_M_DISTRIBUTION`, each as PNG and PDF. No temperature/PVT/DVFS sweep, threshold work, online adaptation, glitching, LUT/fusion, or aperture study was performed. This stage stops here."]
    report_path = ROOT / "BFE4_CALN0_REPORT.md"; report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    gate_path = ROOT / "BFE4_CALN0_GATE.json"; gate_path.write_text(json.dumps({"stage": "B-FE4-CALN0", "gate": gate, "summary": summary, "analysis_sha256": sha256(analysis_path), "manifest_sha256": sha256(manifest_path), "report_sha256": sha256(report_path), "absolute_png_sha256": sha256(ROOT / "BFE4_CALN0_ABSOLUTE_MFF_DISTRIBUTION.png"), "absolute_pdf_sha256": sha256(ROOT / "BFE4_CALN0_ABSOLUTE_MFF_DISTRIBUTION.pdf"), "calibrated_png_sha256": sha256(ROOT / "BFE4_CALN0_SELFCAL_DELTA_M_DISTRIBUTION.png"), "calibrated_pdf_sha256": sha256(ROOT / "BFE4_CALN0_SELFCAL_DELTA_M_DISTRIBUTION.pdf"), "stop_after_stage": True, "next_stage_authorized": False}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if gate == "BFE4_CALN0_SELF_CALIBRATION_NECESSITY_PASS" else 1


def main():
    if any(ROOT.glob("BFE4_CALN0_*")) or RUN_ROOT.exists():
        raise FileExistsError("refusing to overwrite B-FE4-CALN0 evidence")
    config, cells = load_json(FTC_ROOT / "ftc_config.json"), host_cells(load_json(FTC_ROOT / "discovery" / "selected_cells.json"))
    if (cells["delay_rvt"]["cell"], cells["delay_lvt"]["cell"], cells["latch"]["cell"], cells["dff"]["cell"]) != ("BUF_X0P7M_A9TR40", "BUF_X0P7M_A9TL40", "LATQ_X0P5M_A9TR40", "DFFRPQ_X0P5M_A9TR40"):
        raise ValueError("frozen B-FE cell identity drift")
    hspice = str(Path(config["hspice"]).resolve())
    vcs = shutil.which("vcs")
    if not Path(hspice).is_file() or not vcs:
        raise RuntimeError("local HSPICE or VCS is unavailable")
    RUN_ROOT.mkdir(parents=True)
    args = [(seed, cells, str(config["model_library"]), hspice, vcs) for seed in SEEDS]
    # Python 3.6's starmap chunk bookkeeping can leave workers idle after a
    # long-running external simulator returns.  Explicit four-seed batches
    # retain exactly four concurrent workers while making every batch barrier
    # observable and preventing a lost result from silently stalling the run.
    rows = []
    for batch_start in range(0, len(args), WORKERS):
        batch = args[batch_start:batch_start + WORKERS]
        with mp.Pool(processes=WORKERS) as pool:
            rows.extend(pool.starmap(run_instance, batch, chunksize=1))
    return publish(sorted(rows, key=lambda item: item["seed"]), cells, hspice, vcs)


if __name__ == "__main__":
    raise SystemExit(main())
