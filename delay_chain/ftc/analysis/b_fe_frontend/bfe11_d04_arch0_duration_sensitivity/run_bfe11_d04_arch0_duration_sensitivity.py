#!/usr/bin/env python3
"""BFE11 D04 ARCH0 duration-sensitivity staged runner.

The runner owns only the BFE11 task-local evidence directory and its matching
ignored raw-run directory.  It reads the frozen BFE7/BFE8/BFE10 authorities,
adds the one permitted D04 transistor/capture population, and computes the
paired duration result offline.  Production RTL, historical analysis files,
and the frozen D04/D02 waveform definitions are never rewritten.

The generated SPICE and SystemVerilog files are simulation glue.  They are
deliberately verbose about port groups because a short-pulse result is only
useful when the monitored rail, Level-0 decisions, real LATQ/DFF capture, and
safe-domain backend timing can be audited independently.
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
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe11_d04_arch0_duration_sensitivity"

SEEDS = tuple(range(41001, 41031))
TARGET_INDEX = 2
TARGET_EVENT = "21 ns RISE"
SAFE_V = 1.10
MARGIN_RISE = 22
MARGIN_FALL = 24
Q_WIDTH = 30
M_MAX = sum(range(Q_WIDTH))
CAPTURE_G_CLOSE_OFFSET_PS = 534.524618567
CAPTURE_DFF_OFFSET_PS = 1534.524618567
PROBE_PERIOD_PS = 2500.0
SOURCE_TRAN_STEP_S = 2.0e-12
TOTAL_STOP_PS = 65000.0

BFE7_ROOT = ANALYSIS_ROOT / "bfe7_droop12_waveforms"
BFE8_ROOT = ANALYSIS_ROOT / "bfe8_d02_arch0_pilot"
BFE4_ROOT = ANALYSIS_ROOT / "bfe4_caln0_self_calibration"
BFE10_ROOT = ANALYSIS_ROOT / "bfe10_d01_miss0"
SIGNED_ROOT = ANALYSIS_ROOT / "arch1_signed_error_separability_audit"

D04_CSV = BFE7_ROOT / "waveforms" / "D04_SHORT_MEDIUM.csv"
D04_INC = BFE7_ROOT / "waveforms" / "D04_SHORT_MEDIUM.inc"
EXPECTED_D04_CSV_SHA256 = "4c08d1efcb8d37c03627d740abcd7840d4b939e97f3d55f03f2f43e9bf081415"
EXPECTED_D04_INC_SHA256 = "a2be7662b35b4a11ed640a9e66bb2acc30ec84054d5b619e4a5a6242b3e6c5ac"

# Reuse the reviewed BFE1 electrical renderer and BFE8 real-cell capture
# renderer.  Importing these modules does not run a simulator or write an
# artifact; all writes below remain under this task's own directories.
sys.path.insert(0, str(FTC_ROOT / "scripts"))
sys.path.insert(0, str(BFE8_ROOT))
sys.path.insert(0, str(ANALYSIS_ROOT / "bfe9_d01_arch0_amplitude_sensitivity"))
import bfe1_frontend  # noqa: E402
import run_bfe8_d02_arch0_pilot as bfe8_helper  # noqa: E402
import run_bfe9_d01_arch0_amplitude_sensitivity as bfe9_helper  # noqa: E402


def sha256(path):
    """Hash one file without changing it; hashes are the reuse authority."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Read an object-shaped JSON authority and fail closed on bad input."""
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path, value):
    """Write deterministic ASCII JSON only below the BFE11 evidence root."""
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="ascii")


def read_csv(path):
    """Read an ASCII evidence table while preserving its declared schema."""
    with Path(path).open(newline="", encoding="ascii") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    """Write a deterministic ASCII table using the first row's field order."""
    if not rows:
        raise ValueError("cannot write empty CSV: {}".format(path))
    with Path(path).open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def retained_signatures():
    """Load the exact 30 BFE4 MC fingerprints used by BFE8/BFE9."""
    values = {}
    for row in read_csv(BFE4_ROOT / "BFE4_CALN0_RESULTS.csv"):
        values[int(row["seed"])] = row["mc_random_signature"]
    if tuple(sorted(values)) != SEEDS:
        raise ValueError("process authority is not exactly seeds 41001..41030")
    if any(not re.match(r"^[0-9a-f]{64}$", value) for value in values.values()):
        raise ValueError("process authority contains a non-SHA256 signature")
    return values


def audit_authorities():
    """Validate every upstream file before any possible simulator call."""
    required = {
        "bfe7_gate": BFE7_ROOT / "BFE7_DROOP12_GATE.json",
        "bfe7_contract": BFE7_ROOT / "DROOP12_WAVEFORM_CONTRACT.json",
        "bfe7_manifest": BFE7_ROOT / "DROOP12_MANIFEST.json",
        "d04_csv": D04_CSV,
        "d04_inc": D04_INC,
        "bfe0_contract": ANALYSIS_ROOT / "bfe0_architecture_contract.json",
        "healthy": BFE8_ROOT / "BFE8_HEALTHY_PER_SEED.csv",
        "margin_lock": BFE8_ROOT / "BFE8_D02_MARGIN_LOCK.json",
        "fpr": BFE8_ROOT / "BFE8_D02_HEALTHY_FPR_METRICS.json",
        "d02_per_seed": BFE8_ROOT / "BFE8_D02_PER_SEED.csv",
        "d02_metrics": BFE8_ROOT / "BFE8_D02_METRICS.json",
        "bfe8_gate": BFE8_ROOT / "BFE8_D02_GATE.json",
        "r0_gate": BFE8_ROOT / "R0_GATE.json",
        "bfe5_tim0": FTC_ROOT / "backend" / "reports" / "BFE5_TIM0_PIPELINE_CONTRACT.md",
        "bfe4_results": BFE4_ROOT / "BFE4_CALN0_RESULTS.csv",
        "signed_gate": SIGNED_ROOT / "ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT_GATE.json",
        "signed_json": SIGNED_ROOT / "ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT.json",
        "signed_report": SIGNED_ROOT / "ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT_REPORT.md",
        "bfe10_gate": BFE10_ROOT / "BFE10_D01_GATE.json",
    }
    missing = [str(path) for path in required.values() if not Path(path).is_file()]
    if missing:
        raise FileNotFoundError("missing BFE11 authority: {}".format(", ".join(missing)))

    gate = read_json(required["bfe7_gate"])
    if gate.get("gate") != "BFE7_DROOP12_WAVEFORM_CONTRACT_FROZEN" or gate.get("status") != "PASS" or gate.get("frozen") is not True:
        raise ValueError("BFE7 waveform authority is not frozen PASS")
    manifest = read_json(required["bfe7_manifest"])
    for name, expected in (("D04_SHORT_MEDIUM.csv", EXPECTED_D04_CSV_SHA256),
                           ("D04_SHORT_MEDIUM.inc", EXPECTED_D04_INC_SHA256)):
        if manifest.get("files", {}).get(name, {}).get("sha256") != expected:
            raise ValueError("BFE7 manifest hash mismatch for {}".format(name))
        if sha256(manifest["files"][name]["path"] if False else BFE7_ROOT / "waveforms" / name) != expected:
            raise ValueError("D04 file hash mismatch for {}".format(name))

    contract = read_json(required["bfe7_contract"])
    scenarios = {item["scenario_id"]: item for item in contract.get("scenarios", [])}
    d04 = scenarios.get("D04")
    d02 = scenarios.get("D02")
    expected_d04_points = [[20690, 0.0], [20700, 0.06], [21300, 0.06], [21310, 0.0]]
    expected_d02_points = [[19490, 0.0], [19500, 0.06], [22500, 0.06], [22510, 0.0]]
    if not d04 or d04.get("short_name") != "SHORT_MEDIUM" or d04.get("attack_breakpoints_ps") != expected_d04_points:
        raise ValueError("D04 contract geometry changed")
    if not d02 or d02.get("attack_breakpoints_ps") != expected_d02_points:
        raise ValueError("D02 control geometry changed")
    if contract.get("finite_slope_slew_ps") != 10 or contract.get("nominal_vdd_v") != SAFE_V:
        raise ValueError("BFE7 common voltage/slew authority changed")

    bfe0 = read_json(required["bfe0_contract"])
    for key, expected in (("observable_taps", 30), ("rvt_prefix", 4), ("lvt_prefix", 0),
                          ("xor_cell", "XOR2_X0P5M_A9TL40"),
                          ("threshold", "V(xor_i,t) > 0.5 * V(VDD_MONITORED,t)")):
        if bfe0.get(key) != expected:
            raise ValueError("BFE0 contract mismatch for {}".format(key))

    lock = read_json(required["margin_lock"])
    if not lock.get("locked") or lock.get("attack_data_generated"):
        raise ValueError("BFE8 margin lock is not immutable")
    if (lock.get("M_MARGIN_RISE_P0"), lock.get("M_MARGIN_FALL_P0")) != (MARGIN_RISE, MARGIN_FALL):
        raise ValueError("BFE8 margins are not RISE=22/FALL=24")
    if lock.get("reference_arithmetic") != "sum4 >> 2" or lock.get("comparison") != "strict D_M > margin":
        raise ValueError("BFE8 reference/comparison rule changed")
    metrics = read_json(required["d02_metrics"])
    if metrics.get("coverage", {}).get("detected") != 30 or metrics.get("headroom_all_seeds") != {"min": 19, "median": 38.0}:
        raise ValueError("BFE8 D02 baseline metrics changed")
    fpr = read_json(required["fpr"])
    if fpr.get("FPR_healthy", {}).get("alarms") != 1 or fpr.get("FPR_healthy", {}).get("events") != 240:
        raise ValueError("BFE8 healthy FPR is not 1/240")
    r0 = read_json(required["r0_gate"])
    if r0.get("status") != "PASS" or r0.get("formal_metrics_unchanged", {}).get("detection_coverage") != "30/30":
        raise ValueError("BFE8 R0 polarity-aware authority is unavailable")
    if read_json(required["bfe8_gate"]).get("production_rtl_modified") or read_json(required["bfe10_gate"]).get("production_rtl_modified"):
        raise ValueError("historical authority reports production RTL modification")

    signed_gate = read_json(required["signed_gate"])
    signed = read_json(required["signed_json"])
    if signed_gate.get("status") != "PASS" or signed_gate.get("candidate_T_POS_integer") != [18, 19]:
        raise ValueError("signed-error candidates are not the frozen [18,19] pair")
    if signed.get("signed_error_distributions", {}).get("healthy_rise", {}).get("max") != 18:
        raise ValueError("signed healthy maximum is not the frozen +18")
    scope_limits = signed.get("scope_limits", [])
    if "no D04" not in scope_limits:
        raise ValueError("signed-error authority no longer states no D04")
    return required, {name: sha256(path) for name, path in required.items()}, retained_signatures()


def d04_edges():
    """Return the frozen seven 50 MHz edges; index 2 is 21 ns RISE."""
    return [(1000.0 + index * 10000.0, "RISE" if index % 2 == 0 else "FALL") for index in range(7)]


def d04_attack_onset_ns():
    """Derive attack onset from the hashed D04 CSV, never from a new literal."""
    if sha256(D04_CSV) != EXPECTED_D04_CSV_SHA256:
        raise ValueError("D04 CSV hash changed")
    for row in read_csv(D04_CSV):
        if float(row["attack_depth_v"]) > 0.0:
            return float(row["time_s"]) * 1.0e9
    raise ValueError("D04 CSV has no attack onset")


def clock_pwl():
    """Render the same fixed 50 MHz source clock used by BFE8/BFE9."""
    points = [(0.0, 0.0)]
    state = 0.0
    for edge_ps, _polarity in d04_edges():
        points.extend([(edge_ps - 0.5, state),
                       (edge_ps + 0.5, SAFE_V if state == 0.0 else 0.0)])
        state = SAFE_V if state == 0.0 else 0.0
    points.append((TOTAL_STOP_PS, state))
    return "V_SCLK s_clk vss_a PWL({})".format(" ".join("{:.12e} {:.12e}".format(t * 1e-12, v) for t, v in points))


def d04_source_deck(cells, model, seed):
    """Render a transistor-level D04 deck with explicit source contracts.

    The physical ports are intentionally visible in this generated deck:
    ``vdd_monitored/vss_a`` is the sole PD_SENSE rail, the two inherited
    RVT/LVT paths feed thirty real XOR outputs, and no capture/backend cell is
    placed in the HSPICE source experiment.  Measurement points are exactly
    the seven fixed LATQ-close offsets, so a short pulse cannot cause the
    runner to silently move its observation phase.
    """
    deck = bfe1_frontend.render_deck(cells, {
        "scenario_id": "BFE11-D04-{}".format(seed),
        "baseline_v": SAFE_V, "droop_v": None, "phase_ps": None}, model)
    deck = re.sub(r"\* Normal condition:[^\n]*\nV_VDD_MONITORED[^\n]*\n",
                  '.include "D04_SHORT_MEDIUM.inc"\n', deck)
    deck = re.sub(r"V_SCLK s_clk vss_a PWL\([^\n]+", clock_pwl(), deck)
    deck = deck.replace('.lib "{}" tt'.format(model), '.lib "{}" MOS_MC'.format(model))
    deck = deck.replace(".option post=2 probe nomod measform=3 measdgt=10 runlvl=3",
                        ".option post=0 nomod measform=3 measdgt=10 runlvl=3 seed={}".format(seed))
    measurements = []
    for index, (edge_ps, _polarity) in enumerate(d04_edges()):
        at_s = "{:.12e}".format((edge_ps + CAPTURE_G_CLOSE_OFFSET_PS) * 1.0e-12)
        measurements.append(".measure tran m_rail_{:02d} find v(vdd_monitored) at={}".format(index, at_s))
        for tap in range(Q_WIDTH):
            measurements.append(".measure tran m_x_{:02d}_{:02d} find v(xor_{}) at={}".format(index, tap, tap, at_s))
    deck = deck.replace(".end", "\n" + "\n".join(measurements) + "\n.end")
    deck = re.sub(r"\.tran\s+[^\s]+\s+[^\n]+",
                  ".tran {:.12e} {:.12e} sweep monte=2".format(SOURCE_TRAN_STEP_S, TOTAL_STOP_PS * 1e-12), deck, count=1)
    if deck.count("MOS_MC") != 1 or "D04_SHORT_MEDIUM.inc" not in deck or "0.95" in deck:
        raise ValueError("D04 source deck contract failed")
    return deck


def parse_measurements(path):
    """Parse MC row 2 and apply the instantaneous monitored-rail threshold."""
    lines = [line for line in Path(path).read_text(encoding="ascii", errors="strict").splitlines()
             if line and not line.startswith("$") and not line.startswith(".TITLE")]
    rows = {int(row["index"]): row for row in csv.DictReader(lines)}
    if 2 not in rows:
        raise ValueError("D04 measurement file lacks Monte-Carlo row 2")
    row = rows[2]
    samples = []
    for index, (edge_ps, polarity) in enumerate(d04_edges()):
        rail = float(row["m_rail_{:02d}".format(index)])
        xor = [float(row["m_x_{:02d}_{:02d}".format(index, tap)]) for tap in range(Q_WIDTH)]
        if not math.isfinite(rail) or not all(math.isfinite(value) for value in xor):
            raise ValueError("D04 source measurement is non-finite")
        bits = [int(value > 0.5 * rail) for value in xor]
        samples.append({"event_index": index, "edge_ps": edge_ps, "edge": polarity,
                        "rail_v": rail, "bits": bits,
                        "m_ff": sum(tap * bit for tap, bit in enumerate(bits))})
    return samples


def process_signature(mc0, seed):
    """Prove MC row 2 is the exact retained BFE4 process instance."""
    for line in Path(mc0).read_text(encoding="ascii", errors="replace").splitlines():
        if line.startswith("2,"):
            signature = hashlib.sha256(line[2:].encode("ascii")).hexdigest()
            if signature != retained_signatures()[seed]:
                raise ValueError("D04 process signature mismatch for seed {}".format(seed))
            return signature
    raise ValueError("D04 MC row 2 missing for seed {}".format(seed))


def capture_schedule(samples):
    """Convert source words to safe-domain changes at the measured system edges."""
    states, schedules = bfe8_helper.measured_capture_schedule(samples)
    return {tap: schedules[tap] for tap in range(Q_WIDTH)}, {tap: states[tap] for tap in range(Q_WIDTH)}


def run_capture(case_root, samples):
    """Run real LATQ/DFF capture for one D04 source population instance.

    Port groups in the generated wrapper are fixed and documented by the
    reviewed BFE8 helper: ``safe_d_00..29`` are source-derived Level-0 inputs;
    ``latch_g`` is the common active-high LATQ gate; ``dff_ck`` is the common
    positive-edge DFF clock; ``q_lat_00..29`` and ``q_ff_00..29`` are analog
    observations of the real cell outputs.  The safe capture supply remains
    a separate 1.10 V rail, while the D04 monitored rail is retained only as
    source evidence and is never substituted for the safe-domain supply.
    """
    config = read_json(FTC_ROOT / "ftc_config.json")
    cells = read_json(FTC_ROOT / "discovery" / "selected_cells.json")
    model = str(config["model_library"])
    vcs = shutil.which("vcs") or "/home/synopsys/vcs/W-2024.09/bin/vcs"
    xa = Path(case_root) / "vcs_xa"
    xa.mkdir(parents=True, exist_ok=True)
    schedules, states = capture_schedule(samples)
    capture_times = [0.0, TOTAL_STOP_PS * 1e-12]
    columns = {bfe1_frontend.label_for("vdd_monitored"): [SAFE_V, SAFE_V]}
    for tap in range(Q_WIDTH):
        columns[bfe1_frontend.label_for("xor_{}".format(tap))] = [states[tap] * SAFE_V] * 2
    values = {tap: {"xor_v": columns[bfe1_frontend.label_for("xor_{}".format(tap))][0],
                    "threshold_v": 0.5 * SAFE_V} for tap in range(Q_WIDTH)}
    capture = xa / "xa_dff_samples.csv"
    if not capture.is_file():
        (xa / "bfe11_capture_ams_wrapper.sp").write_text(
            bfe8_helper.render_capture_wrapper(columns, capture_times, TOTAL_STOP_PS), encoding="ascii")
        (xa / "tb_bfe11_capture_vcs_xa.sv").write_text(
            bfe8_helper.render_capture_tb(schedules, states, values, TOTAL_STOP_PS, d04_edges()), encoding="ascii")
        (xa / "xa.cfg").write_text("set_sim_level 7\nset_waveform -format fsdb\n", encoding="ascii")
        (xa / "vcsAD.init").write_text(
            "bus_format [%d];\nuse_spice -cell bfe8_capture_ams;\n"
            "choose xa -hspice bfe11_capture_ams.sp -c xa.cfg -o xa;\n", encoding="ascii")
        (xa / "bfe11_capture_ams.sp").write_text(
            "* BFE11 D04 real LATQ/DFF capture top deck.\n"
            ".option post=1 probe\n.lib '{}' tt\n.include '{}'\n.include '{}'\n"
            ".include '{}'\n.include 'bfe11_capture_ams_wrapper.sp'\n"
            ".tran 2p {:.12e}\n.end\n".format(
                model, cells["source_files"]["rvt_cdl"], cells["source_files"]["lvt_cdl"],
                FTC_ROOT / "spice" / "empty_subckt.sp_cal", TOTAL_STOP_PS * 1e-12), encoding="ascii")
        shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", xa / "empty_subckt.sp_cal")
        compile_result = subprocess.run(
            [vcs, "-full64", "-sverilog", "-timescale=1ps/1ps", "-ad=vcsAD.init",
             "-debug_access+all", "-o", "simv", "tb_bfe11_capture_vcs_xa.sv"], cwd=xa,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
            check=False, timeout=1800)
        (xa / "compile.log").write_text(compile_result.stdout, encoding="utf-8", errors="replace")
        if compile_result.returncode:
            raise RuntimeError("D04 VCS compile failed for {}".format(case_root))
        run_result = subprocess.run(["./simv"], cwd=xa, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, universal_newlines=True,
                                    check=False, timeout=1800)
        (xa / "run.log").write_text(run_result.stdout, encoding="utf-8", errors="replace")
        if run_result.returncode:
            raise RuntimeError("D04 VCS/XA capture failed for {}".format(case_root))
    return capture


def capture_events(capture, samples):
    """Validate analog rails and reconstruct captured 30-bit event words."""
    rows = read_csv(capture)
    if len(rows) != len(samples) * Q_WIDTH:
        raise ValueError("D04 capture must contain {} tap rows".format(len(samples) * Q_WIDTH))
    low, high = 0.1 * SAFE_V, 0.9 * SAFE_V
    for row in rows:
        if low < float(row["q_lat_v"]) < high or low < float(row["q_ff_v"]) < high:
            raise ValueError("D04 LATQ/DFF output is not rail-resolved")
        if abs(float(row["vdd_safe_v"]) - SAFE_V) > 1e-6:
            raise ValueError("D04 safe capture rail is not 1.10 V")
    events = []
    for index, sample in enumerate(samples):
        event_rows = [row for row in rows if int(row["sample_index"]) == index]
        if [int(row["tap"]) for row in event_rows] != list(range(Q_WIDTH)):
            raise ValueError("D04 capture tap order is not 0..29")
        bits = [int(float(row["q_ff_v"]) > 0.5 * SAFE_V) for row in event_rows]
        if bits != sample["bits"]:
            raise ValueError("D04 real capture differs from source Level-0 event {}".format(index))
        edge_ps = float(event_rows[0]["nearest_system_edge_ps"])
        if edge_ps != float(sample["edge_ps"]):
            raise ValueError("D04 capture event alignment changed at index {}".format(index))
        events.append({"event_index": index, "edge_ps": sample["edge_ps"], "edge": sample["edge"],
                       "M_FF": sum(tap * bit for tap, bit in enumerate(bits)),
                       "m_ff": sum(tap * bit for tap, bit in enumerate(bits)),
                       "q_ff": "".join(str(bit) for bit in bits)})
    return events


def valid_case(case_root, seed):
    """Return true only when a reusable D04 case still proves its raw evidence.

    P3 may reuse an earlier task-local case, but it may not trust metadata by
    itself.  The three payload hashes bind the parsed source measurements,
    Monte-Carlo signature source, and real LATQ/DFF capture CSV to the exact
    files that will be used for the formal D04 metrics.  Checking the copied
    D04 include as well prevents a stale case directory from being accepted
    after its waveform input has been replaced.
    """
    case_root = Path(case_root)
    path = case_root / "D04_CASE.json"
    if not path.is_file():
        return False
    try:
        case = read_json(path)
        if case.get("seed") != seed or case.get("mc_random_signature") != retained_signatures()[seed]:
            return False
        if case.get("d04_inc_sha256") != EXPECTED_D04_INC_SHA256 or case.get("target_event") != TARGET_EVENT:
            return False
        if case.get("q_ff_width") != Q_WIDTH or len(case.get("events", [])) != len(d04_edges()):
            return False
        if not case.get("all_q_ff_rail_resolved"):
            return False
        # These are the only raw files whose contents feed the retained case:
        # source.mt0.csv defines source Level-0 samples, source.mc0.csv proves
        # the same process draw, and xa_dff_samples.csv proves real capture.
        # A missing file or a changed byte makes the case non-reusable.
        raw_hashes = (
            (case_root / "source_hspice" / D04_INC.name, EXPECTED_D04_INC_SHA256),
            (case_root / "source_hspice" / "source.mt0.csv", case.get("source_measurements_sha256")),
            (case_root / "source_hspice" / "source.mc0.csv", case.get("source_mc0_sha256")),
            (case_root / "vcs_xa" / "xa_dff_samples.csv", case.get("capture_sha256")),
        )
        if any(not digest or not artifact.is_file() or sha256(artifact) != digest
               for artifact, digest in raw_hashes):
            return False
        return all(0 <= int(event["M_FF"]) <= M_MAX for event in case["events"])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def run_d04_seed(seed):
    """Run or reuse one complete D04 HSPICE plus real capture case."""
    if seed not in SEEDS:
        raise ValueError("seed outside BFE11 population: {}".format(seed))
    if sha256(D04_INC) != EXPECTED_D04_INC_SHA256:
        raise ValueError("D04 include hash changed before launch")
    case_root = RUN_ROOT / "d04" / "seed_{:05d}".format(seed)
    source = case_root / "source_hspice"
    source.mkdir(parents=True, exist_ok=True)
    if valid_case(case_root, seed):
        return case_root, False, False
    inc_copy = source / D04_INC.name
    if not inc_copy.is_file():
        shutil.copyfile(D04_INC, inc_copy)
    if sha256(inc_copy) != EXPECTED_D04_INC_SHA256:
        raise ValueError("task-local D04 include copy hash mismatch")
    empty_subckt = FTC_ROOT / "spice" / "empty_subckt.sp_cal"
    if not empty_subckt.is_file():
        raise FileNotFoundError("missing CDL shim: {}".format(empty_subckt))
    shutil.copyfile(empty_subckt, source / empty_subckt.name)
    listing, measures, mc0 = source / "source.lis", source / "source.mt0.csv", source / "source.mc0.csv"
    source_ran = False
    if not (listing.is_file() and measures.is_file() and mc0.is_file()):
        config = read_json(FTC_ROOT / "ftc_config.json")
        cells = read_json(FTC_ROOT / "discovery" / "selected_cells.json")
        (source / "source.sp").write_text(d04_source_deck(cells, str(config["model_library"]), seed), encoding="ascii")
        hspice = str(Path(config["hspice"]).resolve())
        result = subprocess.run([hspice, "source.sp", "-o", "source"], cwd=source,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True, check=False, timeout=3600)
        (source / "hspice_command.log").write_text(result.stdout, encoding="utf-8", errors="replace")
        source_ran = True
        if result.returncode:
            raise RuntimeError("D04 HSPICE failed for seed {}".format(seed))
    if not (listing.is_file() and measures.is_file() and mc0.is_file()):
        raise RuntimeError("D04 HSPICE did not emit complete source artifacts")
    listing_text = listing.read_text(encoding="utf-8", errors="replace").lower()
    if "job concluded" not in listing_text or "monte carlo simulation is detected" not in listing_text or "**error**" in listing_text:
        raise RuntimeError("D04 HSPICE listing is not clean for seed {}".format(seed))
    signature = process_signature(mc0, seed)
    samples = parse_measurements(measures)
    capture = case_root / "vcs_xa" / "xa_dff_samples.csv"
    capture_ran = False
    if not capture.is_file():
        capture = run_capture(case_root, samples)
        capture_ran = True
    events = capture_events(capture, samples)
    healthy = {int(row["seed"]): row for row in read_csv(BFE8_ROOT / "BFE8_HEALTHY_PER_SEED.csv")}
    target = events[TARGET_INDEX]
    payload = {
        "seed": seed, "mc_random_signature": signature, "d04_inc_sha256": sha256(inc_copy),
        "source_measurements_sha256": sha256(measures), "source_mc0_sha256": sha256(mc0),
        "capture_sha256": sha256(capture), "target_event": TARGET_EVENT, "target_event_index": TARGET_INDEX,
        "q_ff_width": Q_WIDTH, "q_ff_target": target["q_ff"], "M_FF_target": target["M_FF"],
        "M_REF_RISE": int(healthy[seed]["M_REF_RISE"]), "M_REF_FALL": int(healthy[seed]["M_REF_FALL"]),
        "locked_rise_margin": MARGIN_RISE, "locked_fall_margin": MARGIN_FALL,
        "rail_resolved": True, "all_q_ff_rail_resolved": True, "all_latq_rail_resolved": True,
        "all_safe_rail_resolved": True, "events": events,
    }
    write_json(case_root / "D04_CASE.json", payload)
    return case_root, source_ran, capture_ran


def wilson(successes, trials):
    """Return the two-sided 95% Wilson interval used by BFE8/BFE9."""
    if trials <= 0 or successes < 0 or successes > trials:
        raise ValueError("invalid binomial counts")
    z = 1.959963984540054
    p = successes / float(trials)
    denominator = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denominator
    radius = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * trials)) / trials) / denominator
    return [max(0.0, center - radius), min(1.0, center + radius)]


def write_p0():
    """Freeze hashes, reuse classes, and zero-rerun budget before simulation."""
    required, hashes, signatures = audit_authorities()
    ROOT.mkdir(parents=True, exist_ok=True)
    matrix = {
        "gate": "BFE11_D04_P0_AUTHORITY_AND_REUSE_FROZEN", "status": "PASS",
        "scenario": {"id": "D04", "short_name": "SHORT_MEDIUM", "depth_mv": 60,
                      "dwell_ns": 0.6, "target": TARGET_EVENT, "background_seed": 7301,
                      "onset_ns": 20.7, "nominal_v": SAFE_V, "temperature_c": 25.0,
                      "breakpoints_ps": [[20690, 0], [20700, 60], [21300, 60], [21310, 0]]},
        "control": {"id": "D02", "depth_mv": 60, "dwell_ns": 3.0, "coverage": "30/30",
                    "headroom_min_median": [19, 38]},
        "seeds": list(SEEDS), "seed_count": len(SEEDS), "authority_sha256": hashes,
        "reuse_without_rerun": ["BFE4 process signatures", "BFE8 M_REF_RISE/FALL",
            "BFE8 margins 22/24", "BFE8 healthy FPR 1/240", "BFE8 D02 per-seed physical/capture/metrics",
            "BFE10 mechanism context", "signed-error healthy distribution and T_POS=18/19",
            "BFE5 TIM0/backend evidence"],
        "new_data_required": ["D04 transistor-level source response", "D04 real LATQ/DFF capture"],
        "conditional_only": ["one task-scoped ARCH0 RTL replay for a new boundary/alignment class"],
        "prohibitions": ["no waveform or margin retuning", "no healthy/D01/D02 rerun", "no ARCH1", "no D03-D12"],
        "process_signatures": signatures,
    }
    write_json(ROOT / "P0_EVIDENCE_MATRIX.json", matrix)
    write_json(ROOT / "P0_REUSE_MANIFEST.json", {
        "matrix_sha256": sha256(ROOT / "P0_EVIDENCE_MATRIX.json"),
        "reused": matrix["reuse_without_rerun"], "new": matrix["new_data_required"],
        "authority_paths": {name: str(path) for name, path in required.items()},
    })
    write_json(ROOT / "P0_SIMULATION_BUDGET.json", {
        "gate": matrix["gate"],
        "upper_bound": {"d04_hspice": 30, "d04_capture": 30, "healthy_hspice": 0,
                         "healthy_capture": 0, "d01_hspice": 0, "d01_capture": 0,
                         "d02_hspice": 0, "d02_capture": 0, "fpr": 0, "primesim": 0,
                         "dc_sta_pnr": 0, "production_rtl_vcs": 1},
        "simulation_count_so_far": {"d04_hspice": 0, "d04_capture": 0, "production_rtl_vcs": 0},
        "resume_rule": "authority -> offline reparse -> matching D04 case -> new simulator call",
    })
    (ROOT / "P0_EVIDENCE_MATRIX.md").write_text(
        "# BFE11 D04 P0 authority and reuse\n\n"
        "Gate: `BFE11_D04_P0_AUTHORITY_AND_REUSE_FROZEN`\n\n"
        "BFE7 D04 and BFE8 ARCH0 authorities were hashed and remain immutable. "
        "Only D04 source/capture cases are new; healthy, D01, D02, FPR and backend work are reused.\n",
        encoding="utf-8")


def run_p1():
    """Perform all zero-simulation D04 runner contract checks."""
    audit_authorities()
    if D04_INC.read_text(encoding="ascii").count("vdd_monitored vss_a") != 1:
        raise ValueError("D04 include must contain one monitored rail source")
    if d04_edges()[TARGET_INDEX] != (21000.0, "RISE") or abs(d04_attack_onset_ns() - 20.7) > 1e-12:
        raise ValueError("D04 target/onset contract mismatch")
    # Re-read geometry directly from the frozen BFE7 contract rather than
    # trusting duplicated constants in this runner.  These assertions prove
    # that D02/D04 differ only in dwell duration while their full-depth center,
    # depth, slew, background seed, and target edge remain common.
    contract = read_json(BFE7_ROOT / "DROOP12_WAVEFORM_CONTRACT.json")
    scenarios = {item["scenario_id"]: item for item in contract["scenarios"]}
    d02_points = scenarios["D02"]["attack_breakpoints_ps"]
    d04_points = scenarios["D04"]["attack_breakpoints_ps"]
    if ((d02_points[2][0] - d02_points[1][0], d04_points[2][0] - d04_points[1][0]) != (3000, 600)
            or ((d02_points[1][0] + d02_points[2][0]) / 2.0,
                (d04_points[1][0] + d04_points[2][0]) / 2.0) != (21000.0, 21000.0)
            or (scenarios["D02"]["nominal_depth_v"], scenarios["D04"]["nominal_depth_v"]) != (0.06, 0.06)
            or contract["background"]["seed"] != 7301 or contract["finite_slope_slew_ps"] != 10):
        raise ValueError("D02/D04 controlled-duration geometry contract changed")
    healthy_rows = read_csv(BFE8_ROOT / "BFE8_HEALTHY_PER_SEED.csv")
    if (len(healthy_rows) != len(SEEDS) or {int(row["seed"]) for row in healthy_rows} != set(SEEDS)
            or any(not row["M_REF_RISE"] or not row["M_REF_FALL"] for row in healthy_rows)):
        raise ValueError("BFE8 healthy authority is not a complete 30-seed reference set")
    cells = read_json(FTC_ROOT / "discovery" / "selected_cells.json")
    config = read_json(FTC_ROOT / "ftc_config.json")
    deck = d04_source_deck(cells, str(config["model_library"]), 41001)
    forbidden = ("ARCH1", "T_POS", "TEMPORAL_ACCUMULATOR", "0.95")
    if any(token in deck.upper() for token in forbidden):
        raise ValueError("forbidden ARCH1/retuned content leaked into D04 deck")
    if deck.count("D04_SHORT_MEDIUM.inc") != 1 or deck.count("MOS_MC") != 1:
        raise ValueError("D04 deck does not bind exactly one frozen include/MC mode")
    if any(int(row["seed"]) not in SEEDS for row in read_csv(BFE8_ROOT / "BFE8_HEALTHY_PER_SEED.csv")):
        raise ValueError("BFE8 healthy seed authority changed")
    if any(path.name.upper().startswith("ARCH1") for path in ROOT.iterdir()):
        raise ValueError("ARCH1 artifact leaked into BFE11 evidence root")
    (ROOT / "P1_REPORT.md").write_text(
        "# BFE11 D04 P1 runner contract\n\n"
        "Gate: `BFE11_D04_P1_RUNNER_CONTRACT_READY`\n\n"
        "D04 hash/geometry, source-referenced instantaneous threshold, fixed LATQ/DFF timing, "
        "30-tap width, strict ARCH0 comparison, polarity-aware reuse and task-local write boundaries passed offline.\n\n"
        "Simulation accounting: HSPICE=0, VCS=0, PrimeSim=0.\n", encoding="utf-8")
    write_json(ROOT / "P1_GATE.json", {"gate": "BFE11_D04_P1_RUNNER_CONTRACT_READY", "status": "PASS",
        "simulation_accounting": {"hspice": 0, "capture": 0, "vcs": 0}, "stop_after_stage": True})


def run_p2():
    """Run only seed 41001 and retain it for the population stage."""
    case, source_ran, capture_ran = run_d04_seed(41001)
    payload = read_json(case / "D04_CASE.json")
    if payload["target_event"] != TARGET_EVENT or payload["target_event_index"] != TARGET_INDEX:
        raise RuntimeError("P2 target event identity is not frozen 21 ns RISE")
    (ROOT / "P2_REPORT.md").write_text(
        "# BFE11 D04 P2 single-seed capture\n\n"
        "Gate: `BFE11_D04_P2_SINGLE_SEED_CAPTURE_PASS`\n\n"
        "Seed 41001 used the manifest-hashed D04 include, retained process signature, fixed target/capture timing, "
        "real LATQ/DFF outputs and 30-bit q_ff. HIT or MISS is accepted without waveform or margin adjustment.\n",
        encoding="utf-8")
    write_json(ROOT / "P2_GATE.json", {"gate": "BFE11_D04_P2_SINGLE_SEED_CAPTURE_PASS", "status": "PASS",
        "seed": 41001, "case": str(case), "source_simulated": source_ran, "capture_simulated": capture_ran,
        "simulation_accounting": {"d04_hspice": int(source_ran), "d04_capture": int(capture_ran)},
        "stop_after_stage": True})


def run_p3():
    """Complete only missing D04 seeds; seed41001 is never rerun here."""
    if not (RUN_ROOT / "d04" / "seed_41001" / "D04_CASE.json").is_file():
        raise RuntimeError("P3 requires the validated P2 seed41001 case")
    source_count = capture_count = 0
    reused = []
    launched = []
    for seed in SEEDS:
        case, source_ran, capture_ran = run_d04_seed(seed)
        if source_ran:
            source_count += 1
        if capture_ran:
            capture_count += 1
        (launched if source_ran or capture_ran else reused).append(seed)
        if not valid_case(case, seed):
            raise RuntimeError("D04 case failed final validation for seed {}".format(seed))
    cases = [str(RUN_ROOT / "d04" / "seed_{:05d}".format(seed) / "D04_CASE.json") for seed in SEEDS]
    ledger = {"stage": "P3", "cases": cases, "reused_seeds": reused, "launched_seeds": launched,
              # The headline figures are physical/capture cases completed for
              # this BFE11 population, not merely processes started during a
              # resumable P3 invocation.  Seed 41001 was completed in P2;
              # seeds 41002..41030 were completed only when missing in P3.
              "simulation_accounting": {"d04_hspice": len(SEEDS), "d04_capture": len(SEEDS),
                                         "d04_hspice_p2": 1, "d04_capture_p2": 1,
                                         "d04_hspice_p3_new": source_count,
                                         "d04_capture_p3_new": capture_count,
                                         "healthy": 0, "d01": 0, "d02": 0, "fpr": 0, "primesim": 0,
                                         "dc_sta_pnr": 0, "production_rtl_vcs": 0}}
    write_json(ROOT / "BFE11_D04_RUN_LEDGER.json", ledger)
    (ROOT / "P3_REPORT.md").write_text(
        "# BFE11 D04 P3 population capture\n\n"
        "Gate: `BFE11_D04_P3_POPULATION_CAPTURE_COMPLETE`\n\n"
        "All 30 process seeds have complete same-hash D04 source/capture evidence. "
        "Seed 41001 came from P2 and was not rerun; all other launches were missing-case only.\n",
        encoding="utf-8")
    write_json(ROOT / "P3_GATE.json", {"gate": "BFE11_D04_P3_POPULATION_CAPTURE_COMPLETE", "status": "PASS",
        "seed_count": len(SEEDS), "reused_seeds": reused, "launched_seeds": launched,
        "simulation_accounting": ledger["simulation_accounting"], "stop_after_stage": True})


def run_p4():
    """Compute formal D04 metrics and exact-seed D04-vs-D02 pairing offline."""
    healthy = {int(row["seed"]): row for row in read_csv(BFE8_ROOT / "BFE8_HEALTHY_PER_SEED.csv")}
    d02 = {int(row["seed"]): row for row in read_csv(BFE8_ROOT / "BFE8_D02_PER_SEED.csv")}
    rows, paired, headrooms, latencies = [], [], [], []
    onset_ns = d04_attack_onset_ns()
    for seed in SEEDS:
        case = read_json(RUN_ROOT / "d04" / "seed_{:05d}".format(seed) / "D04_CASE.json")
        if case["mc_random_signature"] != healthy[seed]["mc_random_signature"] or case["mc_random_signature"] != d02[seed]["mc_random_signature"]:
            raise ValueError("D04/D02/healthy process signature mismatch for seed {}".format(seed))
        target = next(event for event in case["events"] if int(event["event_index"]) == TARGET_INDEX)
        ref = int(healthy[seed]["M_REF_RISE"])
        d_m = abs(int(target["M_FF"]) - ref)
        headroom, detected = d_m - MARGIN_RISE, int(d_m > MARGIN_RISE)
        headrooms.append(headroom)
        latency = "N/A"
        if detected:
            latency = (float(target["edge_ps"]) + CAPTURE_DFF_OFFSET_PS + 7.0 * PROBE_PERIOD_PS) / 1000.0 - onset_ns
            latencies.append(latency)
        pre = [event for event in case["events"] if int(event["event_index"]) < TARGET_INDEX]
        refs = {"RISE": int(healthy[seed]["M_REF_RISE"]), "FALL": int(healthy[seed]["M_REF_FALL"])}
        margins = {"RISE": MARGIN_RISE, "FALL": MARGIN_FALL}
        pre_dm = [abs(int(event["M_FF"]) - refs[event["edge"]]) for event in pre]
        pre_margin = [margins[event["edge"]] for event in pre]
        pre_alarm = [int(value > margin) for value, margin in zip(pre_dm, pre_margin)]
        row = {"seed": seed, "mc_random_signature": case["mc_random_signature"], "target_event": TARGET_EVENT,
               "q_ff_target": case["q_ff_target"], "M_FF_target": int(target["M_FF"]),
               "M_REF_RISE": ref, "M_REF_FALL": refs["FALL"], "D_M_D04": d_m, "H_D_D04": headroom,
               "D04_detected": detected, "locked_rise_margin": MARGIN_RISE, "locked_fall_margin": MARGIN_FALL,
               "pre_attack_alarm_count": sum(pre_alarm), "pre_attack_polarities": ";".join(event["edge"] for event in pre),
               "pre_attack_D_M": ";".join(map(str, pre_dm)), "pre_attack_margin_selected": ";".join(map(str, pre_margin)),
               "pre_attack_alarm_vector": ";".join(map(str, pre_alarm)), "first_alarm_latency_ns": latency,
               "first_alarm_latency_basis": "derived_fixed_tim0_pipeline", "rail_resolved": True,
               "source_measurements_sha256": case["source_measurements_sha256"], "source_mc0_sha256": case["source_mc0_sha256"],
               "capture_sha256": case["capture_sha256"]}
        rows.append(row)
        paired.append({"seed": seed, "mc_random_signature": case["mc_random_signature"], "M_REF_RISE": ref,
                       "D_M_D04": d_m, "H_D_D04": headroom, "D04_detected": detected,
                       "D_M_D02": int(d02[seed]["D_M"]), "H_D_D02": int(d02[seed]["H_D"]),
                       "D02_detected": int(d02[seed]["detected"]),
                       "HEADROOM_CHANGE_D04_MINUS_D02": headroom - int(d02[seed]["H_D"])})
    write_csv(ROOT / "BFE11_D04_PER_SEED.csv", rows)
    write_csv(ROOT / "BFE11_D04_D02_PAIRED.csv", paired)
    detected_count = sum(int(row["D04_detected"]) for row in rows)
    metrics = {"coverage": {"detected": detected_count, "total": len(rows), "fraction": detected_count / 30.0,
                             "wilson_95": wilson(detected_count, 30)},
               "headroom_all_seeds": {"min": min(headrooms), "median": float(np.median(headrooms))},
               "first_alarm_latency_detected_only_ns": {"median": float(np.median(latencies)) if latencies else "N/A",
                                                         "worst": max(latencies) if latencies else "N/A"},
               "first_alarm_latency_basis": "derived_fixed_tim0_pipeline",
               "first_alarm_latency_formula": "(target_edge_ps + 1534.524618567 ps + 7 * 2500 ps) - attack_onset",
               "pipeline_probe_edges": {"e0_to_e4": 4, "e4_to_e7": 3, "e0_to_e7": 7},
               "attack_onset_ns": onset_ns, "target_event": TARGET_EVENT,
               "locked_rise_margin": MARGIN_RISE, "locked_fall_margin": MARGIN_FALL,
               "common_healthy_fpr": "1/240", "pre_attack_alarm_total": sum(int(row["pre_attack_alarm_count"]) for row in rows),
               "simulation_accounting": {"hspice": 0, "capture": 0, "d02_rerun": 0}}
    write_json(ROOT / "BFE11_D04_METRICS.json", metrics)
    change = [int(row["HEADROOM_CHANGE_D04_MINUS_D02"]) for row in paired]
    interpretation = "ROBUST_SHORT_PULSE" if detected_count == 30 and min(headrooms) > 5 else (
        "MARGINAL_SHORT_PULSE" if detected_count == 30 else "PARTIAL_SHORT_PULSE_COVERAGE")
    write_json(ROOT / "BFE11_D04_D02_COMPARISON.json", {
        "d04": metrics, "d02_frozen": read_json(BFE8_ROOT / "BFE8_D02_METRICS.json"),
        "paired_csv_sha256": sha256(ROOT / "BFE11_D04_D02_PAIRED.csv"),
        "headroom_change_d04_minus_d02_median": float(np.median(change)),
        "interpretation_class": interpretation, "d02_resimulated": False,
    })
    (ROOT / "P4_REPORT.md").write_text(
        "# BFE11 D04 P4 ARCH0 duration metrics\n\n"
        "Gate: `BFE11_D04_P4_ARCH0_DURATION_METRICS_CHARACTERIZED`\n\n"
        "D04 formal metrics use only the frozen RISE margin 22 and strict `D_M > margin`; "
        "D02 values are copied from BFE8 and joined by exact seed/signature. "
        "The D04 attack-onset latency is not a backend speedup: TIM0 remains seven probe edges.\n",
        encoding="utf-8")
    write_json(ROOT / "P4_GATE.json", {"gate": "BFE11_D04_P4_ARCH0_DURATION_METRICS_CHARACTERIZED", "status": "PASS",
        "coverage": metrics["coverage"], "headroom": metrics["headroom_all_seeds"],
        "interpretation_class": interpretation, "d02_resimulated": False, "stop_after_stage": True})


def run_p5():
    """Evaluate only the predeclared signed-error shadow candidates 18 and 19."""
    rows = read_csv(ROOT / "BFE11_D04_PER_SEED.csv")
    shadow_rows = []
    for row in rows:
        signed = int(row["M_FF_target"]) - int(row["M_REF_RISE"])
        shadow_rows.append({"seed": int(row["seed"]), "mc_random_signature": row["mc_random_signature"],
                            "signed_e_D04": signed, "shadow18": int(signed > 18), "shadow19": int(signed > 19),
                            "ARCH0_D04_detected": int(row["D04_detected"]), "ARCH0_H_D": int(row["H_D_D04"])})
    write_csv(ROOT / "BFE11_D04_SIGNED_SHADOW.csv", shadow_rows)
    summary = {}
    arch0_misses = {int(row["seed"]) for row in rows if int(row["D04_detected"]) == 0}
    for threshold in (18, 19):
        key = "T_POS_{}".format(threshold)
        detected = {row["seed"] for row in shadow_rows if row["shadow{}".format(threshold)]}
        arch0_hits = {int(row["seed"]) for row in rows if int(row["D04_detected"]) == 1}
        summary[key] = {"rule": "e_D04 > {}".format(threshold), "detected": len(detected), "total": 30,
                        "coverage": len(detected) / 30.0,
                        "signed_e_min_median_max": [min(row["signed_e_D04"] for row in shadow_rows),
                                                     float(np.median([row["signed_e_D04"] for row in shadow_rows])),
                                                     max(row["signed_e_D04"] for row in shadow_rows)],
                        "weakest_detected_signed_headroom": min((row["signed_e_D04"] - threshold for row in shadow_rows if row["shadow{}".format(threshold)]), default=None),
                        "ARCH0_MISS_SEEDS_RECOVERED": sorted(arch0_misses & detected),
                        "ARCH0_HIT_SEEDS_NOT_SHADOW_DETECTED": sorted(arch0_hits - detected),
                        "diagnostic_only": True}
    result = {"gate": "BFE11_D04_P5_SIGNED_SHADOW_FROZEN", "status": "PASS", "target_event": TARGET_EVENT,
              "formal_ARCH0_rule_unchanged": "abs(M_FF-M_REF_RISE) > 22", "healthy_signed_e_max_authority": 18,
              "frozen_candidates": [18, 19], "candidates": summary,
              "interpretation": ("GENERALIZES_TO_D04" if any(item["ARCH0_MISS_SEEDS_RECOVERED"] for item in summary.values())
                                 else "D01_SPECIFIC_OR_LIMITED"),
              "no_threshold_sweep": True, "no_comparator_implemented": True,
              "simulation_accounting": {"HSPICE": 0, "VCS": 0, "PrimeSim": 0, "DC": 0}}
    write_json(ROOT / "BFE11_D04_SIGNED_SHADOW.json", result)
    (ROOT / "P5_REPORT.md").write_text(
        "# BFE11 D04 P5 signed-error shadow audit\n\n"
        "Gate: `BFE11_D04_P5_SIGNED_SHADOW_FROZEN`\n\n"
        "Only the previously frozen `T_POS=18` and `T_POS=19` rules were evaluated. "
        "They are diagnostic projections of D04 data, not formal ARCH0 thresholds and not production RTL. "
        "The healthy positive signed-error authority remains +18; no healthy simulation was rerun. "
        "This retained-data diagnostic is not silicon or PVT signoff.\n",
        encoding="utf-8")
    write_json(ROOT / "P5_GATE.json", {"gate": "BFE11_D04_P5_SIGNED_SHADOW_FROZEN", "status": "PASS",
        "candidate_values": [18, 19], "formal_arch0_unchanged": True,
        "simulation_accounting": result["simulation_accounting"], "stop_after_stage": True})


def run_p6():
    """Replay RTL only if P4 exposed a genuinely new boundary/alignment class."""
    metrics = read_json(ROOT / "BFE11_D04_METRICS.json")
    rows = read_csv(ROOT / "BFE11_D04_PER_SEED.csv")
    new_class = (metrics["coverage"]["detected"] < 30 or metrics["headroom_all_seeds"]["min"] in (0, 1))
    replay_root = RUN_ROOT / "p6_rtl_replay"
    if not new_class:
        gate = "BFE11_D04_P6_RTL_REPLAY_REUSED_PRIOR_EVIDENCE"
        (ROOT / "P6_REPORT.md").write_text(
            "# BFE11 D04 P6 RTL replay decision\n\nGate: `{}`\n\n"
            "No new D04 boundary/alignment class was observed; BFE8/BFE9 replay evidence is reused.\n".format(gate),
            encoding="utf-8")
        write_json(ROOT / "P6_GATE.json", {"gate": gate, "status": "PASS", "new_rtl_replay": False,
            "reused_prior_evidence": True, "simulation_accounting": {"vcs": 0}, "stop_after_stage": True})
        return
    # Select at most one representative per newly observed class.  The bench
    # itself is generated by the reviewed BFE9 helper, which exercises the
    # unchanged production ports: 30-bit safe_d, LATQ gate, probe clock,
    # reset, event_valid/edge_pol/cal_mode, polarity-specific margins,
    # cal_lock, droop_alarm, and droop_alarm_sticky.
    sorted_rows = sorted(rows, key=lambda row: (int(row["H_D_D04"]), int(row["seed"])))
    selected = []
    for desired in (-2, 0, 1):
        candidates = [row for row in sorted_rows if int(row["H_D_D04"]) == desired]
        if candidates:
            selected.append(int(candidates[0]["seed"]))
    if not selected:
        selected = [int(sorted_rows[0]["seed"])]
    healthy_cases = {int(row["seed"]): read_json(RUN_ROOT.parent / "bfe8_d02_arch0_pilot" / "healthy" / "seed_{:05d}".format(int(row["seed"])) / "HEALTHY_CASE.json") for row in rows if int(row["seed"]) in selected}
    representatives = []
    for seed in selected:
        case = read_json(RUN_ROOT / "d04" / "seed_{:05d}".format(seed) / "D04_CASE.json")
        target = case["events"][TARGET_INDEX]
        representatives.append({"seed": seed, "healthy_events": healthy_cases[seed]["events"], "target": target,
                                "ref_rise": int(next(row["M_REF_RISE"] for row in rows if int(row["seed"]) == seed)),
                                "ref_fall": int(next(row["M_REF_FALL"] for row in rows if int(row["seed"]) == seed)),
                                "expected_headroom": int(next(row["H_D_D04"] for row in rows if int(row["seed"]) == seed))})
    replay_root.mkdir(parents=True, exist_ok=True)
    tb = replay_root / "tb_bfe11_backend_replay.sv"
    # The reviewed BFE9 testbench generator is reused only for the unchanged
    # ARCH0 port protocol.  Rename its D01 task marker before the generic
    # BFE9 prefix so the runtime success token is unambiguously BFE11/D04.
    tb_text = bfe9_helper.render_bfe9_rtl_replay_tb(representatives)
    tb_text = tb_text.replace("BFE9_D01", "BFE11_D04").replace("BFE9", "BFE11")
    tb.write_text(tb_text, encoding="ascii")
    vcs = shutil.which("vcs") or "/home/synopsys/vcs/W-2024.09/bin/vcs"
    rtl_files = [FTC_ROOT / "rtl" / name for name in ("ftc_capture_struct.sv", "bfe_capture_bank.sv", "bfe_m_feature.sv", "bfe_backend_ctrl.sv", "bfe_backend_top.sv")]
    rtl_files.append(FTC_ROOT / "tests" / "ftc_standard_cell_elab_stubs.sv")
    compile_result = subprocess.run([vcs, "-full64", "-sverilog", "-timescale=1ns/1ps", "-o", "simv", str(tb)] + [str(path) for path in rtl_files], cwd=replay_root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=900)
    (replay_root / "compile.log").write_text(compile_result.stdout, encoding="utf-8", errors="replace")
    if compile_result.returncode:
        raise RuntimeError("BFE11 RTL replay compilation failed")
    run_result = subprocess.run(["./simv"], cwd=replay_root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=900)
    (replay_root / "run.log").write_text(run_result.stdout, encoding="utf-8", errors="replace")
    if run_result.returncode or "BFE11_D04_P5_RTL_REPLAY_PASS" not in run_result.stdout:
        raise RuntimeError("BFE11 RTL replay failed")
    timing = replay_root / "P5_ALARM_TIMING.csv"
    if not timing.is_file():
        raise RuntimeError("BFE11 RTL replay produced no timing evidence")
    timing_rows = read_csv(timing)
    for row in timing_rows:
        if abs(float(row["e4_to_e7_ns"]) - 3.0 * PROBE_PERIOD_PS / 1000.0) > 1e-6:
            raise RuntimeError("BFE11 RTL replay E4-to-E7 latency changed")
    gate = "BFE11_D04_P6_BOUNDARY_RTL_REPLAY_PASS"
    (ROOT / "P6_REPORT.md").write_text(
        "# BFE11 D04 P6 ARCH0 boundary replay\n\nGate: `{}`\n\n"
        "One task-scoped VCS replay covered the newly observed D04 boundary classes. "
        "Production RTL, margins and waveforms were unchanged; no HSPICE was launched.\n".format(gate), encoding="utf-8")
    write_json(ROOT / "P6_GATE.json", {"gate": gate, "status": "PASS", "new_rtl_replay": True,
        "representative_seeds": selected, "timing_evidence": {"path": str(timing), "sha256": sha256(timing), "rows": timing_rows},
        "simulation_accounting": {"vcs": 1, "hspice": 0}, "stop_after_stage": True})


def run_p7():
    """Generate the paired figure and freeze the final BFE11 package."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paired = read_csv(ROOT / "BFE11_D04_D02_PAIRED.csv")
    x = np.arange(1, len(paired) + 1)
    d02 = [int(row["H_D_D02"]) for row in paired]
    d04 = [int(row["H_D_D04"]) for row in paired]
    plt.rcParams.update({"font.family": "serif", "font.size": 9, "axes.linewidth": 0.8})
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.plot(x, d02, "o-", color="black", markerfacecolor="white", label="D02 60 mV / 3.0 ns")
    ax.plot(x, d04, "s--", color="0.35", markerfacecolor="0.35", label="D04 60 mV / 0.6 ns")
    ax.axhline(0, color="0.1", linewidth=0.8)
    ax.set_xlabel("Paired process index (seed mapping in CSV)")
    ax.set_ylabel("Detection decision headroom H_D (M-codes)")
    ax.grid(True, axis="y", color="0.88", linewidth=0.6)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(ROOT / "BFE11_D04_D02_PAIRED_HEADROOM.png", dpi=220)
    fig.savefig(ROOT / "BFE11_D04_D02_PAIRED_HEADROOM.pdf")
    plt.close(fig)

    metrics = read_json(ROOT / "BFE11_D04_METRICS.json")
    comparison = read_json(ROOT / "BFE11_D04_D02_COMPARISON.json")
    d02 = read_json(BFE8_ROOT / "BFE8_D02_METRICS.json")
    p6 = read_json(ROOT / "P6_GATE.json")
    report = ["# BFE11 D04 ARCH0 duration sensitivity", "", "Gate: `BFE11_D04_ARCH0_DURATION_SENSITIVITY_FROZEN`", "",
              "| Metric | D04 60 mV / 0.6 ns | D02 60 mV / 3.0 ns frozen baseline |", "|---|---:|---:|",
              "| Detection coverage | {}/30 | 30/30 |".format(metrics["coverage"]["detected"]),
              "| Headroom min / median | {} / {} | 19 / 38 M-codes |".format(metrics["headroom_all_seeds"]["min"], metrics["headroom_all_seeds"]["median"]),
              "| First-alarm latency median / worst | {} / {} ns | {} / {} ns |".format(metrics["first_alarm_latency_detected_only_ns"]["median"], metrics["first_alarm_latency_detected_only_ns"]["worst"], d02["first_alarm_latency_detected_only_ns"]["median"], d02["first_alarm_latency_detected_only_ns"]["worst"]), "",
              "Common ARCH0 margins: RISE=22, FALL=24 M-codes.",
              "Common held-out healthy FPR: 1/240 observed events.",
              "D04 latency is attack-onset referenced. Its approximately 1.2 ns difference from D02 comes from the later D04 onset; the fixed TIM0 capture-to-alarm pipeline remains seven probe edges (E4 to E7 is 7.5 ns).",
              "Interpretation class: {}.".format(comparison["interpretation_class"]),
              "RTL replay gate: {}.".format(p6["gate"]), "",
              "This package freezes only the paired 60 mV duration comparison. It does not implement ARCH1 or authorize waveform/margin retuning."]
    (ROOT / "BFE11_D04_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    ledger = read_json(ROOT / "BFE11_D04_RUN_LEDGER.json")
    ledger["stage"] = "P7"
    accounting = ledger["simulation_accounting"]
    # P3's launch list intentionally excludes the P2 sanity seed because P3
    # must reuse it.  The final package, however, reports the complete D04
    # physical population: one P2 source/capture pair plus 29 P3 pairs.  Keep
    # this provenance alongside the total so a reader cannot mistake the P3
    # incremental count for the task's total simulation count.
    p3_new_cases = len(ledger.get("launched_seeds", ()))
    accounting.update({"d04_hspice": len(SEEDS), "d04_capture": len(SEEDS),
                       "d04_hspice_p2": 1, "d04_capture_p2": 1,
                       "d04_hspice_p3_new": p3_new_cases,
                       "d04_capture_p3_new": p3_new_cases})
    ledger["final_artifacts"] = {name: sha256(ROOT / name) for name in (
        "BFE11_D04_PER_SEED.csv", "BFE11_D04_METRICS.json", "BFE11_D04_D02_PAIRED.csv",
        "BFE11_D04_D02_COMPARISON.json", "BFE11_D04_SIGNED_SHADOW.json", "BFE11_D04_SIGNED_SHADOW.csv",
        "BFE11_D04_D02_PAIRED_HEADROOM.png", "BFE11_D04_D02_PAIRED_HEADROOM.pdf", "BFE11_D04_REPORT.md")}
    accounting["production_rtl_vcs"] = int(bool(p6.get("new_rtl_replay")))
    write_json(ROOT / "BFE11_D04_RUN_LEDGER.json", ledger)
    write_json(ROOT / "BFE11_D04_GATE.json", {
        "gate": "BFE11_D04_ARCH0_DURATION_SENSITIVITY_FROZEN", "status": "PASS",
        "coverage": metrics["coverage"], "headroom": metrics["headroom_all_seeds"],
        "interpretation_class": comparison["interpretation_class"], "common_healthy_fpr": "1/240",
        "production_rtl_modified": False, "arch1_implemented": False,
        "simulation_accounting": ledger["simulation_accounting"], "artifact_sha256": ledger["final_artifacts"],
        "stop_after_stage": True,
    })
    (ROOT / "P7_REPORT.md").write_text(
        "# BFE11 D04 P7 SCI-style package and final freeze\n\n"
        "Gate: `BFE11_D04_ARCH0_DURATION_SENSITIVITY_FROZEN`\n\n"
        "The paired headroom figure and report were generated only from the completed D04 data and frozen BFE8 D02 data.\n",
        encoding="utf-8")


def main(argv=None):
    """Dispatch one explicit stage; stages are intentionally resumable."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("p0", "p1", "p2", "p3", "p4", "p5", "p6", "p7"), required=True)
    stage = parser.parse_args(argv).stage
    if stage == "p0":
        write_p0()
    elif stage == "p1":
        run_p1()
    elif stage == "p2":
        run_p2()
    elif stage == "p3":
        run_p3()
    elif stage == "p4":
        run_p4()
    elif stage == "p5":
        run_p5()
    elif stage == "p6":
        run_p6()
    elif stage == "p7":
        run_p7()
    print("BFE11 {} PASS".format(stage.upper()))


if __name__ == "__main__":
    raise SystemExit(main())
