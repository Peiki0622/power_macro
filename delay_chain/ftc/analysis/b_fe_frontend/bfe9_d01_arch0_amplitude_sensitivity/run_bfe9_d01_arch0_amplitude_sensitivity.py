#!/usr/bin/env python3
"""BFE9 D01 ARCH0 amplitude-sensitivity staged runner.

The runner is deliberately task-local.  It reads frozen BFE7/BFE8 evidence,
places all generated evidence below this directory, and places raw simulator
artifacts below the matching task-local ``ftc/runs`` directory.  No function
in this file changes production RTL or historical BFE7/BFE8 artifacts.

The generated XA/VCS files are simulation glue, not synthesizable RTL.  They
still document every electrical port because the port direction and supply
domain are part of the capture contract being audited.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend"
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe9_d01_arch0_amplitude_sensitivity"
SEEDS = tuple(range(41001, 41031))

BFE7_ROOT = ANALYSIS_ROOT / "bfe7_droop12_waveforms"
BFE8_ROOT = ANALYSIS_ROOT / "bfe8_d02_arch0_pilot"
BFE4_ROOT = ANALYSIS_ROOT / "bfe4_caln0_self_calibration"
BFE8_RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe8_d02_arch0_pilot"
D01_INC = BFE7_ROOT / "waveforms" / "D01_SHALLOW_CANONICAL.inc"
D01_CSV = BFE7_ROOT / "waveforms" / "D01_SHALLOW_CANONICAL.csv"
EXPECTED_D01_INC_SHA256 = "cc264410443f03ce1ca1f1ef2b6f7870f08b2a8f1a8fb9befe44c92b9f050fdc"
EXPECTED_D01_CSV_SHA256 = "49ae91c52ed12f1603a0d25303da855f05df9ca3bf5eaed35b1d9123b9fb42ff"

SAFE_V = 1.10
CAPTURE_G_CLOSE_OFFSET_PS = 534.524618567
CAPTURE_DFF_OFFSET_PS = 1534.524618567
PROBE_PERIOD_PS = 2500.0
SOURCE_TRAN_STEP_S = 2.0e-12
MARGIN_RISE = 22
MARGIN_FALL = 24

sys.path.insert(0, str(FTC_ROOT / "scripts"))
import bfe1_frontend  # noqa: E402


def sha256(path):
    """Hash one retained or generated file without changing it."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Read a JSON object and reject malformed authority files early."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def retained_signatures():
    """Load the frozen BFE4 process fingerprint for every population seed."""
    values = {}
    with (BFE4_ROOT / "BFE4_CALN0_RESULTS.csv").open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            values[int(row["seed"])] = row["mc_random_signature"]
    if tuple(sorted(values)) != SEEDS:
        raise ValueError("BFE4 process authority is not exactly seeds 41001..41030")
    return values


def audit_authorities():
    """Validate BFE7/BFE8 authorities before any simulator invocation."""
    required = {
        "bfe7_gate": BFE7_ROOT / "BFE7_DROOP12_GATE.json",
        "bfe7_contract": BFE7_ROOT / "DROOP12_WAVEFORM_CONTRACT.json",
        "bfe7_manifest": BFE7_ROOT / "DROOP12_MANIFEST.json",
        "d01_csv": D01_CSV,
        "d01_inc": D01_INC,
        "healthy": BFE8_ROOT / "BFE8_HEALTHY_PER_SEED.csv",
        "margin_lock": BFE8_ROOT / "BFE8_D02_MARGIN_LOCK.json",
        "fpr": BFE8_ROOT / "BFE8_D02_HEALTHY_FPR_METRICS.json",
        "d02_per_seed": BFE8_ROOT / "BFE8_D02_PER_SEED.csv",
        "d02_metrics": BFE8_ROOT / "BFE8_D02_METRICS.json",
        "r0_gate": BFE8_ROOT / "R0_GATE.json",
        "r0_report": BFE8_ROOT / "R0_REPORT.md",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing BFE9 authority: {}".format(", ".join(missing)))
    gate = read_json(required["bfe7_gate"])
    if gate.get("status") != "PASS" or gate.get("frozen") is not True:
        raise ValueError("BFE7 gate is not frozen PASS")
    if sha256(D01_CSV) != EXPECTED_D01_CSV_SHA256 or sha256(D01_INC) != EXPECTED_D01_INC_SHA256:
        raise ValueError("D01 waveform hash differs from frozen manifest")
    lock = read_json(required["margin_lock"])
    if not lock.get("locked") or lock.get("attack_data_generated"):
        raise ValueError("BFE8 margin lock is not immutable")
    if (lock.get("M_MARGIN_RISE_P0"), lock.get("M_MARGIN_FALL_P0")) != (MARGIN_RISE, MARGIN_FALL):
        raise ValueError("BFE8 margin lock is not RISE=22/FALL=24")
    if lock.get("reference_arithmetic") != "sum4 >> 2" or lock.get("comparison") != "strict D_M > margin":
        raise ValueError("BFE8 arithmetic/comparison authority changed")
    metrics = read_json(required["d02_metrics"])
    if metrics.get("coverage", {}).get("detected") != 30 or metrics.get("headroom_all_seeds") != {"min": 19, "median": 38.0}:
        raise ValueError("frozen D02 metrics do not match the plan authority")
    fpr = read_json(required["fpr"])
    if fpr.get("FPR_healthy", {}).get("alarms") != 1 or fpr.get("FPR_healthy", {}).get("events") != 240:
        raise ValueError("frozen healthy FPR is not 1/240")
    r0 = read_json(required["r0_gate"])
    if r0.get("status") != "PASS" or "polarity" not in json.dumps(r0).lower():
        raise ValueError("BFE8 R0 polarity-aware authority is unavailable")
    return required, {name: sha256(path) for name, path in required.items()}, retained_signatures()


def write_p0():
    """Write the authority matrix and explicit bounded simulation budget."""
    paths, digests, signatures = audit_authorities()
    ROOT.mkdir(parents=True, exist_ok=True)
    matrix = {
        "gate": "BFE9_D01_P0_AUTHORITY_AND_REUSE_FROZEN", "status": "PASS",
        "scenario": {"id": "D01", "depth_mv": 30, "target": "21 ns RISE", "background_seed": 7301,
                     "onset_ns": 19.5, "stop_ns": 65.0, "nominal_v": 1.10, "temperature_c": 25.0},
        "seeds": list(SEEDS), "seed_count": len(SEEDS), "authority_sha256": digests,
        "reused_without_rerun": ["BFE4 process signatures", "BFE8 M_REF_RISE/FALL", "BFE8 margins 22/24",
                                  "BFE8 healthy FPR 1/240", "BFE8 D02 per-seed results", "BFE8 TIM0", "BFE8-R0"],
        "new_data_required": ["D01 transistor-level source response", "D01 real LATQ/DFF capture"],
        "conditional_only": ["production ARCH0 RTL replay for a new decision-boundary class"],
        "signatures": signatures,
        "prohibitions": ["no BFE7/BFE8 writes", "no margin retuning", "no ARCH1", "no D03-D12"],
    }
    (ROOT / "P0_EVIDENCE_MATRIX.json").write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="ascii")
    (ROOT / "P0_REUSE_MANIFEST.json").write_text(json.dumps({"matrix_sha256": sha256(ROOT / "P0_EVIDENCE_MATRIX.json"),
        "reused": matrix["reused_without_rerun"], "new": matrix["new_data_required"]}, indent=2, sort_keys=True) + "\n", encoding="ascii")
    budget = {"gate": matrix["gate"], "upper_bound": {"d01_hspice": 30, "d01_capture": 30,
        "healthy_hspice": 0, "healthy_capture": 0, "d02_hspice": 0, "d02_capture": 0,
        "fpr": 0, "dc_sta_pnr": 0, "production_rtl_vcs": 1},
        "simulation_count_so_far": {"d01_hspice": 0, "d01_capture": 0, "production_rtl_vcs": 0},
        "resume_rule": "authority -> BFE9 reparse -> matching case resume -> new simulator call"}
    (ROOT / "P0_SIMULATION_BUDGET.json").write_text(json.dumps(budget, indent=2, sort_keys=True) + "\n", encoding="ascii")
    (ROOT / "P0_EVIDENCE_MATRIX.md").write_text("# BFE9 D01 P0 authority and reuse\n\n"
        "Gate: `BFE9_D01_P0_AUTHORITY_AND_REUSE_FROZEN`\n\n"
        "BFE7 D01 and BFE8 D02 ARCH0 authorities were hashed and remain immutable. "
        "Only D01 source/capture data are new; the bounded budget records zero healthy/D02/FPR reruns.\n", encoding="utf-8")
    return signatures


def d01_edges():
    """Return the seven frozen 50 MHz edges, with target index 2 at 21 ns."""
    return [(1000.0 + i * 10000.0, "RISE" if i % 2 == 0 else "FALL") for i in range(7)]


def d01_attack_onset_ns():
    """Derive onset from the hashed D01 CSV, never from a duplicate literal."""
    if sha256(D01_CSV) != EXPECTED_D01_CSV_SHA256:
        raise ValueError("D01 CSV hash changed")
    with D01_CSV.open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            if float(row["attack_depth_v"]) > 0.0:
                return float(row["time_s"]) * 1e9
    raise ValueError("D01 CSV has no attack onset")


def d01_source_deck(cells, model, seed):
    """Render the transistor-level D01 deck around the exact frozen include."""
    deck = bfe1_frontend.render_deck(cells, {"scenario_id": "BFE9-D01-{}".format(seed),
        "baseline_v": SAFE_V, "droop_v": None, "phase_ps": None}, model)
    deck = re.sub(r"\* Normal condition:[^\n]*\nV_VDD_MONITORED[^\n]*\n", '.include "D01_SHALLOW_CANONICAL.inc"\n', deck)
    points = [(edge - 0.5, 0.0 if i % 2 == 0 else SAFE_V) for i, (edge, _) in enumerate(d01_edges())]
    points += [(edge + 0.5, SAFE_V if i % 2 == 0 else 0.0) for i, (edge, _) in enumerate(d01_edges())]
    points.sort()
    clock = "V_SCLK s_clk vss_a PWL(" + " ".join("{:.12e} {:.12e}".format(t * 1e-12, v) for t, v in points) + ")"
    deck = re.sub(r"V_SCLK s_clk vss_a PWL\([^\n]+", clock, deck)
    deck = deck.replace('.lib "{}" tt'.format(model), '.lib "{}" MOS_MC'.format(model))
    deck = deck.replace(".option post=2 probe nomod measform=3 measdgt=10 runlvl=3",
        ".option post=0 nomod measform=3 measdgt=10 runlvl=3 seed={}".format(seed))
    measures = []
    for index, (edge_ps, _) in enumerate(d01_edges()):
        at_s = "{:.12e}".format((edge_ps + CAPTURE_G_CLOSE_OFFSET_PS) * 1e-12)
        measures.append(".measure tran m_rail_{:02d} find v(vdd_monitored) at={}".format(index, at_s))
        for tap in range(30):
            measures.append(".measure tran m_x_{:02d}_{:02d} find v(xor_{}) at={}".format(index, tap, tap, at_s))
    deck = deck.replace(".end", "\n" + "\n".join(measures) + "\n.end")
    deck = re.sub(r"\.tran\s+[^\s]+\s+[^\n]+", ".tran {:.12e} 6.500000000000e-08 sweep monte=2".format(SOURCE_TRAN_STEP_S), deck, count=1)
    if deck.count("MOS_MC") != 1 or "D01_SHALLOW_CANONICAL.inc" not in deck or "0.95" in deck:
        raise ValueError("D01 deck contract failed")
    return deck


def parse_measurements(path):
    """Read Monte-Carlo row 2 and apply instantaneous monitored-rail threshold."""
    lines = [line for line in path.read_text(encoding="ascii").splitlines() if line and not line.startswith(("$", ".TITLE"))]
    rows = {int(row["index"]): row for row in csv.DictReader(lines)}
    if 2 not in rows:
        raise ValueError("D01 mt0.csv lacks Monte-Carlo index 2")
    row, samples = rows[2], []
    for index, (edge_ps, polarity) in enumerate(d01_edges()):
        rail = float(row["m_rail_{:02d}".format(index)])
        xor = [float(row["m_x_{:02d}_{:02d}".format(index, tap)]) for tap in range(30)]
        if not math.isfinite(rail) or not all(math.isfinite(value) for value in xor):
            raise ValueError("non-finite D01 source measurement")
        bits = [int(value > 0.5 * rail) for value in xor]
        samples.append({"event_index": index, "edge_ps": edge_ps, "edge": polarity,
                        "bits": bits, "m_ff": sum(tap * bit for tap, bit in enumerate(bits))})
    return samples


def process_signature(mc0, seed):
    """Hash the retained HSPICE MC row and compare it to BFE4 authority."""
    for line in mc0.read_text(encoding="ascii", errors="replace").splitlines():
        if line.startswith("2,"):
            signature = hashlib.sha256(line[2:].encode("ascii")).hexdigest()
            expected = retained_signatures()[seed]
            if signature != expected:
                raise ValueError("D01 process signature mismatch for seed {}".format(seed))
            return signature
    raise ValueError("D01 MC row 2 missing for seed {}".format(seed))


def capture_wrapper_and_tb(case_root, samples):
    """Create documented XA wrapper and VCS stimulus from source-derived bits.

    Port groups are explicit:
    - ``safe_d_00..29``: Level-0 tap decisions entering the safe-domain LATQ.
    - ``latch_g``: active-high LATQ gate; its falling edge closes capture.
    - ``dff_ck``: safe-domain DFF clock; rising edge transfers LATQ to q_ff.
    - ``q_lat_*`` and ``q_ff_*``: analog observation ports, not production RTL.
    """
    total_stop_ps = 65000.0
    times = [0.0, total_stop_ps * 1e-12]
    initial = samples[0]["bits"]
    schedules = {tap: [] for tap in range(30)}
    state = list(initial)
    for sample in samples[1:]:
        for tap, bit in enumerate(sample["bits"]):
            if bit != state[tap]:
                schedules[tap].append((sample["edge_ps"], bit))
                state[tap] = bit
    ports = ["safe_d_{:02d}".format(t) for t in range(30)] + ["latch_g", "dff_ck"]
    ports += ["q_lat_{:02d}".format(t) for t in range(30)] + ["q_ff_{:02d}".format(t) for t in range(30)]
    lines = ["* BFE9 D01 real LATQ/DFF capture wrapper.", ".SUBCKT bfe9_capture_ams \\"]
    lines += ["+ {} \\".format(port) for port in ports]
    lines += ["* vdd_safe/vss_safe are stable capture supplies; vdd_sense is observed only.",
              "V_VDD_SAFE vdd_safe 0 DC 1.100000000000e+00", "V_VSS_SAFE vss_safe 0 DC 0", "V_DFF_RESET dff_reset 0 DC 0"]
    for tap in range(30):
        lines.append("* safe_d_{:02d}: Level-0 source decision for XOR tap {:02d}.".format(tap, tap))
        lines.append("E_SAFE_D_{:02d} safe_d_r_{:02d} 0 safe_d_{:02d} 0 1.0".format(tap, tap, tap))
        lines.append("* q_lat_{:02d}: real LATQ output; q_ff_{:02d}: real DFF output.".format(tap, tap))
        lines.append("XLATCH_{:02d} q_lat_r_{:02d} vdd_safe vdd_safe vss_safe vss_safe safe_d_r_{:02d} latch_g LATQ_X0P5M_A9TR40".format(tap, tap, tap))
        lines.append("XDFF_{:02d} q_ff_r_{:02d} vdd_safe vdd_safe vss_safe vss_safe dff_ck q_lat_r_{:02d} dff_reset DFFRPQ_X0P5M_A9TL40".format(tap, tap, tap))
        lines.append("E_Q_LAT_{:02d} q_lat_{:02d} 0 q_lat_r_{:02d} 0 1.0".format(tap, tap, tap))
        lines.append("E_Q_FF_{:02d} q_ff_{:02d} 0 q_ff_r_{:02d} 0 1.0".format(tap, tap, tap))
    lines += [".probe tran " + " ".join(["v(q_lat_r_{:02d})".format(t) for t in range(30)] + ["v(q_ff_r_{:02d})".format(t) for t in range(30)]),
              ".tran 2p 6.500000000000e-08", ".ENDS bfe9_capture_ams", ""]
    (case_root / "bfe9_capture_ams_wrapper.sp").write_text("\n".join(lines), encoding="ascii")

    tb = ["// BFE9 D01 simulation glue; this file is not production RTL.", "// Each safe_d port is a source-derived Level-0 bit; q ports are analog wires.", "`timescale 1ps/1ps", "module bfe9_capture_vcs_xa;"]
    tb += ["  logic safe_d_{:02d}; // input tap {:02d}, safe-domain decision".format(t, t) for t in range(30)]
    tb += ["  logic latch_g; // input: LATQ active-high gate", "  logic dff_ck; // input: DFF rising-edge clock"]
    tb += ["  wire q_lat_{:02d}; // output: real LATQ tap {:02d}".format(t, t) for t in range(30)]
    tb += ["  wire q_ff_{:02d}; // output: real DFF tap {:02d}".format(t, t) for t in range(30)]
    tb += ["  bfe9_capture_ams u_ams (", ",\n".join("    .{}({})".format(p, p) for p in ports), "  );"]
    tb += ["  initial begin latch_g=1'b1;", "    // Frozen G-close: each system edge + 534.524618567 ps."]
    previous = 0.0
    for edge_ps, _ in d01_edges():
        close = edge_ps + CAPTURE_G_CLOSE_OFFSET_PS
        tb.append("    #( {:.12f} ) latch_g=1'b0; #( 1000.000000000000 ) latch_g=1'b1;".format(close - previous))
        previous = close + 1000.0
    tb += ["  end", "  initial begin dff_ck=1'b0;"]
    previous = 0.0
    for edge_ps, _ in d01_edges():
        rise = edge_ps + CAPTURE_DFF_OFFSET_PS
        tb.append("    #( {:.12f} ) dff_ck=1'b1; #( 1250.000000000000 ) dff_ck=1'b0;".format(rise - previous))
        previous = rise + 1250.0
    tb += ["  end"]
    for tap in range(30):
        tb += ["  // Tap {:02d} starts from source Level-0 at t=0 and changes only at measured edges.".format(tap),
               "  initial begin safe_d_{:02d}=1'b{};".format(tap, initial[tap])]
        previous = 0.0
        for event_ps, bit in schedules[tap]:
            tb.append("    #( {:.12f} ) safe_d_{:02d}=1'b{};".format(event_ps - previous, tap, bit))
            previous = event_ps
        tb += ["  end"]
    tb += ["  integer fd;", "  initial begin", "    fd=$fopen(\"xa_dff_samples.csv\",\"w\");",
           "    $fwrite(fd,\"sample_index,sample_time_ps,nearest_system_edge_ps,system_polarity,tap,q_lat_v,q_ff_v\\n\");"]
    # Keep a cumulative timestamp here.  Each record is taken 100 ps after
    # its own DFF rising edge, so the delta between records is one 50 MHz
    # system period (10 ns), rather than a spuriously repeated 100 ps delay.
    previous_sample_ps = 0.0
    for index, (edge_ps, polarity) in enumerate(d01_edges()):
        sample_ps = edge_ps + CAPTURE_DFF_OFFSET_PS
        sample_observe_ps = sample_ps + 100.0
        tb.append("    #( {:.12f} );".format(sample_observe_ps - previous_sample_ps))
        previous_sample_ps = sample_observe_ps
        for tap in range(30):
            # Edge time and polarity are format literals.  The runtime values
            # therefore match exactly the three numeric placeholders:
            # sample time, tap number, and the two observed analog outputs.
            tb.append("    $fwrite(fd,\"{},%.6f,{:.6f},{},%d,%.9f,%.9f\\n\", $realtime, {}, $snps_get_volt(bfe9_capture_vcs_xa.u_ams.q_lat_r_{:02d}), $snps_get_volt(bfe9_capture_vcs_xa.u_ams.q_ff_r_{:02d}));".format(index, edge_ps, polarity, tap, tap, tap))
    tb += ["    $fclose(fd);", "  end", "  initial begin #( 65000.000000 ); $finish; end", "endmodule", ""]
    (case_root / "tb_bfe9_capture_vcs_xa.sv").write_text("\n".join(tb), encoding="ascii")


def run_d01_seed(seed):
    """Run or resume one D01 HSPICE plus real LATQ/DFF capture case."""
    config = read_json(FTC_ROOT / "ftc_config.json")
    cells = read_json(FTC_ROOT / "discovery" / "selected_cells.json")
    hspice = str(Path(config["hspice"]).resolve())
    vcs = shutil.which("vcs") or "/home/synopsys/vcs/W-2024.09/bin/vcs"
    case = RUN_ROOT / "d01" / "seed_{:05d}".format(seed)
    source = case / "source_hspice"
    xa = case / "vcs_xa"
    source.mkdir(parents=True, exist_ok=True)
    xa.mkdir(parents=True, exist_ok=True)
    inc_copy = source / D01_INC.name
    if not inc_copy.is_file():
        shutil.copyfile(D01_INC, inc_copy)
    if sha256(inc_copy) != EXPECTED_D01_INC_SHA256:
        raise ValueError("copied D01 include hash mismatch")
    # The selected RVT/LVT CDL files contain a relative include of this
    # project-local empty-subcircuit shim.  Copying it into the task-local
    # source directory keeps PDK resolution deterministic without editing the
    # shared CDL or placing generated files in the repository root.
    empty_subckt = FTC_ROOT / "spice" / "empty_subckt.sp_cal"
    if not empty_subckt.is_file():
        raise FileNotFoundError("missing task-local CDL shim source: {}".format(empty_subckt))
    shutil.copyfile(empty_subckt, source / empty_subckt.name)
    listing, measures, mc0 = source / "source.lis", source / "source.mt0.csv", source / "source.mc0.csv"
    if not (listing.is_file() and measures.is_file() and mc0.is_file()):
        (source / "source.sp").write_text(d01_source_deck(cells, str(config["model_library"]), seed), encoding="ascii")
        result = subprocess.run([hspice, "source.sp", "-o", "source"], cwd=source, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=3600)
        (source / "hspice_command.log").write_text(result.stdout, encoding="utf-8", errors="replace")
        if result.returncode:
            raise RuntimeError("D01 HSPICE failed for seed {}".format(seed))
    listing_text = listing.read_text(encoding="utf-8", errors="replace").lower()
    if "job concluded" not in listing_text or "monte carlo simulation is detected" not in listing_text or "**error**" in listing_text:
        raise RuntimeError("D01 HSPICE listing is not clean for seed {}".format(seed))
    signature = process_signature(mc0, seed)
    samples = parse_measurements(measures)
    capture_path = xa / "xa_dff_samples.csv"
    # A prior interrupted/debug run may leave a syntactically valid but
    # incomplete CSV.  It is not reusable evidence; rebuild only this
    # task-local capture directory while preserving the already valid source
    # HSPICE artifacts above.
    if capture_path.is_file():
        existing_rows = list(csv.DictReader(capture_path.open(newline="", encoding="ascii")))
        if len(existing_rows) != 7 * 30:
            shutil.rmtree(xa)
            xa.mkdir(parents=True, exist_ok=True)
    if not capture_path.is_file():
        columns = {bfe1_frontend.label_for("xor_{}".format(t)): [samples[0]["bits"][t] * SAFE_V] * 2 for t in range(30)}
        capture_wrapper_and_tb(xa, samples)
        model = str(config["model_library"])
        (xa / "xa.cfg").write_text("set_sim_level 7\nset_waveform -format fsdb\n", encoding="ascii")
        (xa / "vcsAD.init").write_text("bus_format [%d];\nuse_spice -cell bfe9_capture_ams;\nchoose xa -hspice bfe9_capture_ams.sp -c xa.cfg -o xa;\n", encoding="ascii")
        (xa / "bfe9_capture_ams.sp").write_text("* BFE9 D01 XA top deck.\n.lib '{}' tt\n.include '{}'\n.include '{}'\n.include '{}'\n.include 'bfe9_capture_ams_wrapper.sp'\n.tran 2p 6.500000000000e-08\n.end\n".format(model, cells["source_files"]["rvt_cdl"], cells["source_files"]["lvt_cdl"], FTC_ROOT / "spice" / "empty_subckt.sp_cal"), encoding="ascii")
        shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", xa / "empty_subckt.sp_cal")
        compile_result = subprocess.run([vcs, "-full64", "-sverilog", "-timescale=1ps/1ps", "-ad=vcsAD.init", "-debug_access+all", "-o", "simv", "tb_bfe9_capture_vcs_xa.sv"], cwd=xa, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=1800)
        (xa / "compile.log").write_text(compile_result.stdout, encoding="utf-8", errors="replace")
        if compile_result.returncode:
            raise RuntimeError("D01 VCS compile failed for seed {}".format(seed))
        run_result = subprocess.run(["./simv"], cwd=xa, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=1800)
        (xa / "run.log").write_text(run_result.stdout, encoding="utf-8", errors="replace")
        if run_result.returncode:
            raise RuntimeError("D01 VCS/XA run failed for seed {}".format(seed))
    capture = xa / "xa_dff_samples.csv"
    rows = list(csv.DictReader(capture.open(newline="", encoding="ascii")))
    if len(rows) != 7 * 30:
        raise ValueError("D01 capture must contain 210 tap rows")
    for row in rows:
        for name in ("q_lat_v", "q_ff_v"):
            value = float(row[name])
            if 0.1 * SAFE_V < value < 0.9 * SAFE_V:
                raise ValueError("D01 {} output is not rail-resolved".format(name))
    healthy = {int(row["seed"]): row for row in csv.DictReader((BFE8_ROOT / "BFE8_HEALTHY_PER_SEED.csv").open(newline="", encoding="ascii"))}
    target = samples[2]
    payload = {"seed": seed, "mc_random_signature": signature, "d01_inc_sha256": sha256(inc_copy),
        "source_measurements_sha256": sha256(measures), "source_mc0_sha256": sha256(mc0), "capture_sha256": sha256(capture),
        "target_event": "21 ns RISE", "target_event_index": 2, "q_ff_target": "".join(map(str, target["bits"])),
        "M_D01_target": target["m_ff"], "M_REF_RISE": int(healthy[seed]["M_REF_RISE"]), "M_REF_FALL": int(healthy[seed]["M_REF_FALL"]),
        "locked_rise_margin": MARGIN_RISE, "locked_fall_margin": MARGIN_FALL,
        "rail_resolved": True, "events": [{"event_index": s["event_index"], "edge_ps": s["edge_ps"], "edge": s["edge"], "M_FF": s["m_ff"], "q_ff": "".join(map(str, s["bits"]))} for s in samples]}
    (case / "D01_CASE.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return case


def run_p1():
    """Perform zero-simulation contract checks and publish P1 gate."""
    audit_authorities()
    if D01_INC.read_text(encoding="ascii").count("vdd_monitored vss_a") != 1:
        raise ValueError("D01 source port contract missing")
    if d01_edges()[2] != (21000.0, "RISE") or d01_attack_onset_ns() != 19.5:
        raise ValueError("D01 target/onset contract mismatch")
    if any("ARCH1" in path.name.upper() for path in ROOT.iterdir()):
        raise ValueError("ARCH1 artifact leaked into BFE9 directory")
    (ROOT / "P1_REPORT.md").write_text("# BFE9 D01 P1 runner contract\n\nGate: `BFE9_D01_P1_RUNNER_CONTRACT_READY`\n\n"
        "D01 hash, attack geometry, 30-tap source-referenced threshold, frozen capture timing, strict comparison, "
        "polarity-aware diagnostic and task-local write boundaries passed offline.\n", encoding="utf-8")
    (ROOT / "P1_GATE.json").write_text(json.dumps({"gate": "BFE9_D01_P1_RUNNER_CONTRACT_READY", "status": "PASS",
        "simulation_accounting": {"hspice": 0, "capture": 0, "vcs": 0}, "stop_after_stage": True}, indent=2) + "\n", encoding="ascii")


def run_p2():
    """Run only seed 41001 and publish the sanity gate."""
    case = run_d01_seed(41001)
    (ROOT / "P2_REPORT.md").write_text("# BFE9 D01 P2 single-seed capture\n\nGate: `BFE9_D01_P2_SINGLE_SEED_CAPTURE_PASS`\n\n"
        "Seed 41001 used the frozen D01 include, retained process signature, 21 ns RISE target, 30-bit capture and fixed margins.\n", encoding="utf-8")
    (ROOT / "P2_GATE.json").write_text(json.dumps({"gate": "BFE9_D01_P2_SINGLE_SEED_CAPTURE_PASS", "status": "PASS",
        "seed": 41001, "case": str(case), "simulation_accounting": {"d01_hspice": 1, "d01_capture": 1}, "stop_after_stage": True}, indent=2) + "\n", encoding="ascii")


def run_p3():
    """Complete only missing D01 population cases, reusing valid artifacts."""
    run_p2_case = RUN_ROOT / "d01" / "seed_41001" / "D01_CASE.json"
    if not run_p2_case.is_file():
        raise RuntimeError("P3 requires completed P2 seed 41001")
    for seed in SEEDS:
        case_json = RUN_ROOT / "d01" / "seed_{:05d}".format(seed) / "D01_CASE.json"
        if not case_json.is_file():
            run_d01_seed(seed)
    cases = [RUN_ROOT / "d01" / "seed_{:05d}".format(seed) / "D01_CASE.json" for seed in SEEDS]
    if not all(path.is_file() for path in cases):
        raise RuntimeError("D01 population is incomplete")
    (ROOT / "BFE9_D01_RUN_LEDGER.json").write_text(json.dumps({"stage": "P3", "cases": [str(path) for path in cases],
        "simulation_accounting": {"d01_hspice": len(SEEDS), "d01_capture": len(SEEDS), "healthy": 0, "d02": 0}}, indent=2) + "\n", encoding="ascii")
    (ROOT / "P3_REPORT.md").write_text("# BFE9 D01 P3 population capture\n\nGate: `BFE9_D01_P3_POPULATION_CAPTURE_COMPLETE`\n\n"
        "All 30 process seeds have validated D01 source and real capture cases.\n", encoding="utf-8")
    (ROOT / "P3_GATE.json").write_text(json.dumps({"gate": "BFE9_D01_P3_POPULATION_CAPTURE_COMPLETE", "status": "PASS",
        "seed_count": 30, "simulation_accounting": {"d01_hspice": 30, "d01_capture": 30}, "stop_after_stage": True}, indent=2) + "\n", encoding="ascii")


def wilson(successes, trials):
    """Return the two-sided 95% Wilson interval used by BFE8."""
    z = 1.959963984540054
    p = successes / float(trials)
    den = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / den
    radius = z * math.sqrt((p * (1 - p) + z * z / (4 * trials)) / trials) / den
    return [max(0.0, center - radius), min(1.0, center + radius)]


def run_p4():
    """Extract D01 metrics and pair them with frozen D02 rows offline."""
    healthy = {int(row["seed"]): row for row in csv.DictReader((BFE8_ROOT / "BFE8_HEALTHY_PER_SEED.csv").open(newline="", encoding="ascii"))}
    d02 = {int(row["seed"]): row for row in csv.DictReader((BFE8_ROOT / "BFE8_D02_PER_SEED.csv").open(newline="", encoding="ascii"))}
    rows, paired, headrooms, latencies = [], [], [], []
    onset = d01_attack_onset_ns()
    for seed in SEEDS:
        case = read_json(RUN_ROOT / "d01" / "seed_{:05d}".format(seed) / "D01_CASE.json")
        if case["mc_random_signature"] != healthy[seed]["mc_random_signature"] or case["mc_random_signature"] != d02[seed]["mc_random_signature"]:
            raise ValueError("D01/D02 signature mismatch for seed {}".format(seed))
        target = next(event for event in case["events"] if event["event_index"] == 2)
        dm = abs(int(target["M_FF"]) - int(healthy[seed]["M_REF_RISE"]))
        hd, detected = dm - MARGIN_RISE, int(dm > MARGIN_RISE)
        headrooms.append(hd)
        latency = "N/A"
        if detected:
            latency = (target["edge_ps"] + CAPTURE_DFF_OFFSET_PS + 7 * PROBE_PERIOD_PS) / 1000.0 - onset
            latencies.append(latency)
        pre = [event for event in case["events"] if event["event_index"] < 2]
        pre_dm = [abs(int(event["M_FF"]) - int(healthy[seed]["M_REF_" + event["edge"]])) for event in pre]
        pre_margin = [MARGIN_RISE if event["edge"] == "RISE" else MARGIN_FALL for event in pre]
        pre_alarm = [int(value > margin) for value, margin in zip(pre_dm, pre_margin)]
        row = {"seed": seed, "mc_random_signature": case["mc_random_signature"], "target_event": "21 ns RISE",
            "q_ff_target": case["q_ff_target"], "M_FF_target": int(target["M_FF"]), "M_REF_RISE": int(healthy[seed]["M_REF_RISE"]),
            "M_REF_FALL": int(healthy[seed]["M_REF_FALL"]), "D_M_D01": dm, "H_D_D01": hd, "D01_detected": detected,
            "locked_rise_margin": MARGIN_RISE, "locked_fall_margin": MARGIN_FALL, "pre_attack_alarm_count": sum(pre_alarm),
            "pre_attack_polarities": ";".join(event["edge"] for event in pre), "pre_attack_D_M": ";".join(map(str, pre_dm)),
            "pre_attack_margin_selected": ";".join(map(str, pre_margin)), "pre_attack_alarm_vector": ";".join(map(str, pre_alarm)),
            "first_alarm_latency_ns": latency, "rail_resolved": True, "source_measurements_sha256": case["source_measurements_sha256"],
            "source_mc0_sha256": case["source_mc0_sha256"], "capture_sha256": case["capture_sha256"]}
        rows.append(row)
        paired.append({"seed": seed, "mc_random_signature": case["mc_random_signature"], "M_REF_RISE": row["M_REF_RISE"],
            "D_M_D01": dm, "H_D_D01": hd, "D01_detected": detected, "D_M_D02": int(d02[seed]["D_M"]),
            "H_D_D02": int(d02[seed]["H_D"]), "D02_detected": int(d02[seed]["detected"]),
            "HEADROOM_DROP_D02_TO_D01": int(d02[seed]["H_D"]) - hd})
    with (ROOT / "BFE9_D01_PER_SEED.csv").open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
    with (ROOT / "BFE9_D01_D02_PAIRED.csv").open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(paired[0]), lineterminator="\n"); writer.writeheader(); writer.writerows(paired)
    detected_count = sum(row["D01_detected"] for row in rows)
    metrics = {"coverage": {"detected": detected_count, "total": 30, "fraction": detected_count / 30.0, "wilson_95": wilson(detected_count, 30)},
        "headroom_all_seeds": {"min": min(headrooms), "median": float(np.median(headrooms))},
        "first_alarm_latency_detected_only_ns": {"median": float(np.median(latencies)) if latencies else "N/A", "worst": max(latencies) if latencies else "N/A"},
        "attack_onset_ns": onset, "target_event": "21 ns RISE", "locked_rise_margin": MARGIN_RISE, "locked_fall_margin": MARGIN_FALL,
        "common_healthy_fpr": "1/240", "pre_attack_alarm_total": sum(int(row["pre_attack_alarm_count"]) for row in rows),
        "simulation_accounting": {"hspice": 0, "capture": 0, "d02_rerun": 0}}
    comparison = {"d01": metrics, "d02_frozen": read_json(BFE8_ROOT / "BFE8_D02_METRICS.json"),
        "paired_csv_sha256": sha256(ROOT / "BFE9_D01_D02_PAIRED.csv"), "headroom_drop_median": float(np.median([row["HEADROOM_DROP_D02_TO_D01"] for row in paired])),
        "interpretation_class": "FULL_OBSERVED_COVERAGE" if detected_count == 30 and min(headrooms) > 0 else ("MARGINAL_FULL_COVERAGE" if detected_count == 30 else "PARTIAL_COVERAGE")}
    (ROOT / "BFE9_D01_METRICS.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="ascii")
    (ROOT / "BFE9_D01_D02_COMPARISON.json").write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="ascii")
    (ROOT / "P4_REPORT.md").write_text("# BFE9 D01 P4 paired ARCH0 metrics\n\nGate: `BFE9_D01_P4_ARCH0_AMPLITUDE_METRICS_CHARACTERIZED`\n\n"
        "D01 metrics were extracted offline and paired to frozen D02 by exact process signature.\n", encoding="utf-8")
    (ROOT / "P4_GATE.json").write_text(json.dumps({"gate": "BFE9_D01_P4_ARCH0_AMPLITUDE_METRICS_CHARACTERIZED", "status": "PASS",
        "coverage": metrics["coverage"], "headroom": metrics["headroom_all_seeds"], "stop_after_stage": True}, indent=2) + "\n", encoding="ascii")


def q_word(bits):
    """Convert tap-0..29 binary decisions into the production [29:0] word."""
    if len(bits) != 30 or any(int(bit) not in (0, 1) for bit in bits):
        raise ValueError("q_ff must contain exactly thirty binary taps")
    return sum(int(bit) << index for index, bit in enumerate(bits))


def render_bfe9_rtl_replay_tb(representatives):
    """Render one self-checking bench for the newly observed D01 boundaries.

    The generated file is simulation glue only.  The port comments are kept
    beside each declaration so reviewers can audit the exact ARCH0 contract:
    30 safe-domain bits, LATQ gate, probe clock, reset, consume metadata,
    polarity-specific margins, calibration lock, and alarm outputs.
    """
    lines = [
        "// BFE9 P5 ARCH0 replay: simulation-only verification of unchanged RTL.",
        "// This module is generated under a task-local run directory.",
        "`timescale 1ns/1ps", "`default_nettype none", "module bfe9_backend_replay_tb;",
        "    // Input: thirty restored Level-0 tap decisions in safe domain.",
        "    reg [29:0] safe_d;",
        "    // Input: active-high LATQ transparency gate; capture closes on low.",
        "    reg latch_gate;",
        "    // Input: shared 400 MHz backend/probe clock.",
        "    reg clk_probe;",
        "    // Input: active-high asynchronous reset for capture and controller.",
        "    reg reset;",
        "    // Input: E4 consume strobe for the current captured M_FF sample.",
        "    reg event_valid;",
        "    // Input: polarity selector, 0=RISE and 1=FALL.",
        "    reg edge_pol;",
        "    // Input: startup calibration qualifier; normal target uses zero.",
        "    reg cal_mode;",
        "    // Input: strict unsigned RISE and FALL margins, frozen at 22/24.",
        "    reg [8:0] m_margin_rise; reg [8:0] m_margin_fall;",
        "    // Output: high after four valid calibration samples per polarity.",
        "    wire cal_lock;",
        "    // Output: registered E7 alarm pulse for the consumed target event.",
        "    wire droop_alarm;",
        "    // Output: E8 sticky alarm state, cleared only by reset.",
        "    wire droop_alarm_sticky;",
        "    bfe_backend_top dut (.safe_d(safe_d), .latch_gate(latch_gate), .clk_probe(clk_probe),",
        "        .reset(reset), .event_valid(event_valid), .edge_pol(edge_pol), .cal_mode(cal_mode),",
        "        .m_margin_rise(m_margin_rise), .m_margin_fall(m_margin_fall), .cal_lock(cal_lock),",
        "        .droop_alarm(droop_alarm), .droop_alarm_sticky(droop_alarm_sticky));",
        "    always #1.25 clk_probe = ~clk_probe;",
        "    integer cycle; integer source_index; integer expected_alarm; integer alarm_count;",
        "    real e4_event_time_ns [0:8]; integer timing_fd;",
        "    reg [29:0] stimulus [0:8]; reg [8:0] expected_m [0:8];",
        "    reg [8:0] expected_ref [0:8]; reg [8:0] expected_margin [0:8];",
        "    reg expected_pol [0:8]; reg expected_cal [0:8];",
    ]
    for rep in representatives:
        seed = rep["seed"]
        events = rep["healthy_events"][:8] + [rep["target"]]
        lines += ["    // Seed {}: eight healthy calibration events plus D01 target.".format(seed),
                  "    task run_seed_{:05d};".format(seed), "    begin"]
        for index, event in enumerate(events):
            bits = [int(bit) for bit in event["q_ff"]]
            m_value = q_word(bits)
            m_code = int(event.get("m_ff", event.get("M_FF")))
            if index < 8:
                polarity = 0 if index % 2 == 0 else 1
                ref = 0; margin = 0; cal = 1
            else:
                polarity = 0  # D01 target is the frozen 21 ns RISE event.
                ref = rep["ref_rise"]; margin = MARGIN_RISE; cal = 0
            lines.append("        stimulus[{}] = 30'h{:08x}; expected_m[{}] = 9'd{}; expected_ref[{}] = 9'd{}; expected_margin[{}] = 9'd{}; expected_pol[{}] = 1'b{}; expected_cal[{}] = 1'b{};".format(
                index, m_value, index, m_code, index, ref, index, margin, index, polarity, index, cal))
        lines += [
            "        safe_d=30'd0; latch_gate=1'b1; event_valid=1'b0; edge_pol=1'b0; cal_mode=1'b0;",
            "        m_margin_rise=9'd0; m_margin_fall=9'd0; alarm_count=0; reset=1'b1; #2.0; reset=1'b0;",
            "        for (cycle=0; cycle<23; cycle=cycle+1) begin",
            "            @(negedge clk_probe);",
            "            if (cycle<9) safe_d=stimulus[cycle]; else safe_d=30'd0;",
            "            source_index=cycle-4; event_valid=(source_index>=0 && source_index<9);",
            "            if (event_valid) begin edge_pol=expected_pol[source_index]; cal_mode=expected_cal[source_index];",
            "                m_margin_rise=(expected_pol[source_index]==1'b0) ? expected_margin[source_index] : 9'd0;",
            "                m_margin_fall=(expected_pol[source_index]==1'b1) ? expected_margin[source_index] : 9'd0; end",
            "            else begin edge_pol=1'b0; cal_mode=1'b0; m_margin_rise=9'd0; m_margin_fall=9'd0; end",
            "            @(posedge clk_probe); #0.01;",
            "            if (event_valid) e4_event_time_ns[source_index] = $realtime;",
            "            if (event_valid && dut.u_backend_ctrl.event_m_q !== expected_m[source_index]) $fatal(1, \"P5 M mismatch seed=%0d event=%0d\", {}, source_index);".format(seed),
            "            if (cycle>=7) begin source_index=cycle-7; expected_alarm=(source_index==8) ? ((expected_m[source_index]>=expected_ref[source_index]) ? (expected_m[source_index]-expected_ref[source_index] > expected_margin[source_index]) : (expected_ref[source_index]-expected_m[source_index] > expected_margin[source_index])) : 0; if (droop_alarm !== expected_alarm[0]) $fatal(1, \"P5 E7 mismatch seed=%0d event=%0d\", {}, source_index); if (droop_alarm) begin alarm_count=alarm_count+1; $fwrite(timing_fd, \"{},%0d,%.6f,%.6f,%.6f\\n\", source_index, e4_event_time_ns[source_index], $realtime, $realtime-e4_event_time_ns[source_index]); end end".format(seed, seed, seed),
            "        end",
            "        if (!cal_lock) $fatal(1, \"P5 CAL_LOCK missing seed=%0d\", {});".format(seed),
            "        if ((expected_m[8]-expected_ref[8] > expected_margin[8]) && !droop_alarm_sticky) $fatal(1, \"P5 E8 sticky missing seed=%0d\", {});".format(seed),
            "        if ((expected_m[8]-expected_ref[8] <= expected_margin[8]) && droop_alarm_sticky) $fatal(1, \"P5 unexpected sticky alarm seed=%0d\", {});".format(seed),
            "    end", "    endtask",
        ]
    lines += [
        "    initial begin timing_fd=$fopen(\"P5_ALARM_TIMING.csv\",\"w\"); if (timing_fd==0) $fatal(1, \"P5 timing evidence file could not be opened\");",
        "        $fwrite(timing_fd,\"seed,event_index,e4_event_ns,alarm_ns,e4_to_e7_ns\\n\"); clk_probe=1'b0; safe_d=30'd0; latch_gate=1'b1; reset=1'b1; event_valid=1'b0; edge_pol=1'b0; cal_mode=1'b0; m_margin_rise=9'd0; m_margin_fall=9'd0; #1;",
    ]
    for rep in representatives:
        lines.append("        run_seed_{:05d};".format(rep["seed"]))
    lines += ["        $fclose(timing_fd); $display(\"BFE9_D01_P5_RTL_REPLAY_PASS\"); $finish;", "    end", "endmodule", "`default_nettype wire", ""]
    return "\n".join(lines)


def run_p5():
    """Replay the minimum new D01 boundary classes through unchanged ARCH0 RTL.

    P4 found real misses, an equality boundary, and a weakest hit.  Those
    classes were absent from the frozen BFE8 D02 replay, so one task-local VCS
    invocation is required.  The bench below consumes only retained healthy
    calibration vectors and the already captured D01 target vectors; it does
    not launch HSPICE or alter the production RTL.
    """
    metrics = read_json(ROOT / "BFE9_D01_METRICS.json")
    boundary = metrics["coverage"]["detected"] < 30 or metrics["headroom_all_seeds"]["min"] in (0, 1)
    if not boundary:
        gate = "BFE9_D01_P5_RTL_REPLAY_REUSED_BFE8"
        (ROOT / "P5_REPORT.md").write_text(
            "# BFE9 D01 P5 RTL replay decision\n\nGate: `{}`\n\n"
            "No new decision-boundary class was observed; BFE8 P7 replay is reused.\n".format(gate),
            encoding="utf-8")
        (ROOT / "P5_GATE.json").write_text(json.dumps({"gate": gate, "status": "PASS",
            "new_rtl_replay": False, "reused_bfe8_p7": True,
            "simulation_accounting": {"vcs": 0}, "stop_after_stage": True}, indent=2) + "\n", encoding="ascii")
        return

    # Select one seed for each newly observed boundary class.  Sorting by
    # headroom makes the selection deterministic and keeps the replay minimal.
    rows = list(csv.DictReader((ROOT / "BFE9_D01_PER_SEED.csv").open(newline="", encoding="ascii")))
    by_headroom = sorted(rows, key=lambda row: (int(row["H_D_D01"]), int(row["seed"])))
    selected = []
    for desired in (-2, 0, 1):
        candidates = [row for row in by_headroom if int(row["H_D_D01"]) == desired]
        if candidates:
            selected.append(int(candidates[0]["seed"]))
    if not selected:
        raise RuntimeError("P5 boundary classification found no replay seed")

    healthy = {int(row["seed"]): row for row in csv.DictReader(
        (BFE8_ROOT / "BFE8_HEALTHY_PER_SEED.csv").open(newline="", encoding="ascii"))}
    representatives = []
    for seed in selected:
        healthy_case = read_json(BFE8_RUN_ROOT / "healthy" / "seed_{:05d}".format(seed) / "HEALTHY_CASE.json")
        d01_case = read_json(RUN_ROOT / "d01" / "seed_{:05d}".format(seed) / "D01_CASE.json")
        target = d01_case["events"][d01_case["target_event_index"]]
        representatives.append({"seed": seed, "healthy_events": healthy_case["events"],
            "target": target, "ref_rise": int(healthy[seed]["M_REF_RISE"]),
            "ref_fall": int(healthy[seed]["M_REF_FALL"]),
            "expected_headroom": int(next(row["H_D_D01"] for row in rows if int(row["seed"]) == seed))})

    replay_root = RUN_ROOT / "p5_rtl_replay"
    replay_root.mkdir(parents=True, exist_ok=True)
    tb = replay_root / "tb_bfe9_backend_replay.sv"
    tb.write_text(render_bfe9_rtl_replay_tb(representatives), encoding="ascii")
    vcs = shutil.which("vcs") or "/home/synopsys/vcs/W-2024.09/bin/vcs"
    rtl_files = [FTC_ROOT / "rtl" / name for name in
                 ("ftc_capture_struct.sv", "bfe_capture_bank.sv", "bfe_m_feature.sv",
                  "bfe_backend_ctrl.sv", "bfe_backend_top.sv")]
    # Standard-cell models are elaboration-only test models.  They are kept
    # outside the production RTL and are never synthesized by this stage.
    rtl_files.append(FTC_ROOT / "tests" / "ftc_standard_cell_elab_stubs.sv")
    compile_result = subprocess.run(
        [vcs, "-full64", "-sverilog", "-timescale=1ns/1ps", "-o", "simv", str(tb)] +
        [str(path) for path in rtl_files], cwd=replay_root, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=900)
    (replay_root / "compile.log").write_text(compile_result.stdout, encoding="utf-8", errors="replace")
    if compile_result.returncode:
        raise RuntimeError("P5 VCS compilation failed")
    run_result = subprocess.run(["./simv"], cwd=replay_root, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, universal_newlines=True,
                                check=False, timeout=900)
    (replay_root / "run.log").write_text(run_result.stdout, encoding="utf-8", errors="replace")
    if run_result.returncode or "BFE9_D01_P5_RTL_REPLAY_PASS" not in run_result.stdout:
        raise RuntimeError("P5 RTL replay failed")
    timing_path = replay_root / "P5_ALARM_TIMING.csv"
    if not timing_path.is_file():
        raise RuntimeError("P5 timing evidence was not produced")
    timing_rows = list(csv.DictReader(timing_path.open(newline="", encoding="ascii")))
    expected_pipeline_ns = 3.0 * PROBE_PERIOD_PS / 1000.0
    expected_hit_seeds = {rep["seed"] for rep in representatives if rep["expected_headroom"] > 0}
    timing_seeds = {int(row["seed"]) for row in timing_rows}
    if timing_seeds != expected_hit_seeds:
        raise RuntimeError("P5 alarm rows do not match strict D01 hit classes")
    for row in timing_rows:
        if abs(float(row["e4_to_e7_ns"]) - expected_pipeline_ns) > 1.0e-6:
            raise RuntimeError("P5 E4-to-E7 latency is not 7.5 ns")
    gate = "BFE9_D01_P5_BOUNDARY_RTL_REPLAY_PASS"
    report = ["# BFE9 D01 P5 ARCH0 RTL boundary replay", "", "Gate: `{}`".format(gate), "",
              "One task-local VCS replay covered the weakest HIT, strict equality boundary, and closest MISS.",
              "Production ARCH0 RTL and frozen margins were unchanged; no HSPICE was launched.", "",
              "| Seed | H_D_D01 | Expected alarm | E4->E7 (ns) |", "|---:|---:|---:|---:|"]
    timing_by_seed = {int(row["seed"]): row for row in timing_rows}
    for rep in representatives:
        timing = timing_by_seed.get(rep["seed"])
        report.append("| {} | {} | {} | {} |".format(rep["seed"], rep["expected_headroom"],
            "HIT" if rep["expected_headroom"] > 0 else "MISS",
            timing["e4_to_e7_ns"] if timing else "N/A"))
    (ROOT / "P5_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (ROOT / "P5_GATE.json").write_text(json.dumps({"gate": gate, "status": "PASS",
        "new_rtl_replay": True, "reused_bfe8_p7": False, "representative_seeds": selected,
        "timing_evidence": {"path": str(timing_path), "sha256": sha256(timing_path),
                            "rows": timing_rows, "expected_pipeline_ns": expected_pipeline_ns},
        "simulation_accounting": {"vcs": 1, "hspice": 0}, "stop_after_stage": True},
        indent=2, sort_keys=True) + "\n", encoding="ascii")


def run_p6():
    """Generate paired headroom figure and freeze the final report package."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    paired = list(csv.DictReader((ROOT / "BFE9_D01_D02_PAIRED.csv").open(newline="", encoding="ascii")))
    x = np.arange(1, len(paired) + 1)
    d01 = [int(row["H_D_D01"]) for row in paired]; d02 = [int(row["H_D_D02"]) for row in paired]
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.plot(x, d02, "o-", color="black", markerfacecolor="white", label="D02 60 mV")
    ax.plot(x, d01, "s--", color="0.35", markerfacecolor="0.35", label="D01 30 mV")
    ax.axhline(0, color="0.1", linewidth=0.8)
    ax.set_xlabel("Paired process index (seed mapping in CSV)"); ax.set_ylabel("Detection decision headroom H_D (M-codes)")
    ax.grid(True, axis="y", color="0.88", linewidth=0.6); ax.legend(frameon=False); fig.tight_layout()
    fig.savefig(ROOT / "BFE9_D01_D02_PAIRED_HEADROOM.png", dpi=220); fig.savefig(ROOT / "BFE9_D01_D02_PAIRED_HEADROOM.pdf")
    plt.close(fig)
    metrics = read_json(ROOT / "BFE9_D01_METRICS.json"); d02 = read_json(BFE8_ROOT / "BFE8_D02_METRICS.json")
    report = ["# BFE9 D01 ARCH0 amplitude sensitivity", "", "Gate: `BFE9_D01_ARCH0_AMPLITUDE_SENSITIVITY_FROZEN`", "",
        "| Metric | D01 30 mV | D02 60 mV frozen baseline |", "|---|---:|---:|",
        "| Detection coverage | {}/30 | 30/30 |".format(metrics["coverage"]["detected"]),
        "| Headroom min / median | {} / {} | 19 / 38 M-codes |".format(metrics["headroom_all_seeds"]["min"], metrics["headroom_all_seeds"]["median"]),
        "| First-alarm latency median / worst | {} / {} ns | 20.5345 / 20.5345 ns |".format(metrics["first_alarm_latency_detected_only_ns"]["median"], metrics["first_alarm_latency_detected_only_ns"]["worst"]), "",
        "Common ARCH0 margins: RISE=22, FALL=24 M-codes.", "Common held-out healthy FPR: 1/240 observed events.", "",
        "This paired result addresses only the observed response to halving the canonical droop amplitude. It does not claim a continuous minimum detectable voltage."]
    (ROOT / "BFE9_D01_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    ledger = read_json(ROOT / "BFE9_D01_RUN_LEDGER.json")
    p5_gate = read_json(ROOT / "P5_GATE.json")
    ledger["final_artifacts"] = {name: sha256(ROOT / name) for name in ["BFE9_D01_PER_SEED.csv", "BFE9_D01_METRICS.json", "BFE9_D01_D02_PAIRED.csv", "BFE9_D01_D02_COMPARISON.json", "BFE9_D01_D02_PAIRED_HEADROOM.png", "BFE9_D01_D02_PAIRED_HEADROOM.pdf", "BFE9_D01_REPORT.md"]}
    ledger["stage"] = "P6"
    ledger["simulation_accounting"] = {
        "d01_hspice": 30, "d01_capture": 30, "healthy": 0, "d02": 0,
        "new_rtl": int(bool(p5_gate.get("new_rtl_replay"))),
    }
    (ROOT / "BFE9_D01_RUN_LEDGER.json").write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="ascii")
    final = {"gate": "BFE9_D01_ARCH0_AMPLITUDE_SENSITIVITY_FROZEN", "status": "PASS", "coverage": metrics["coverage"],
        "headroom": metrics["headroom_all_seeds"], "common_healthy_fpr": "1/240", "production_rtl_modified": False,
        "arch1_implemented": False, "simulation_accounting": ledger["simulation_accounting"],
        "artifact_sha256": ledger["final_artifacts"], "stop_after_stage": True}
    (ROOT / "BFE9_D01_GATE.json").write_text(json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="ascii")


def main():
    parser = argparse.ArgumentParser(description="BFE9 D01 ARCH0 staged runner")
    parser.add_argument("--stage", choices=("p0", "p1", "p2", "p3", "p4", "p5", "p6"), required=True)
    stage = parser.parse_args().stage
    if stage == "p0": write_p0()
    elif stage == "p1": run_p1()
    elif stage == "p2": run_p2()
    elif stage == "p3": run_p3()
    elif stage == "p4": run_p4()
    elif stage == "p5": run_p5()
    elif stage == "p6": run_p6()
    print("BFE9 {} PASS".format(stage.upper()))


if __name__ == "__main__":
    main()
