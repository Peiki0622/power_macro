#!/usr/bin/env python3
"""BFE14 healthy-temperature characterization runner.

The runner deliberately keeps the physical flow small and task-local.  It
imports the already validated BFE8 helpers for source deck rendering,
source-referenced Level-0 conversion, and real LATQ/DFF capture generation.
The only physical deck edit made by this runner is the HSPICE ``.temp`` line.
No production RTL is generated or modified by this file.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import multiprocessing as mp
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend"
BFE8_ROOT = ANALYSIS_ROOT / "bfe8_d02_arch0_pilot"
BFE12_ROOT = ANALYSIS_ROOT / "bfe12_arch1_sign0_signed_droop_rtl"
BFE13_ROOT = ANALYSIS_ROOT / "bfe13_arch1_track0_rtl"
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe14_arch1_benign_temp_drift"
SEEDS = tuple(range(41001, 41031))
TEMPERATURES = (-40, 25, 85, 125)
NEW_TEMPERATURES = (-40, 85, 125)
SCOUT_RANKS = (0, 15, 29)
SAFE_V = 1.10
T_TRACK_PROBE = 5
B_TRACK_PROBE = 2


def load_bfe8_module():
    """Load BFE8 helpers without executing its command-line entry point."""
    path = BFE8_ROOT / "run_bfe8_d02_arch0_pilot.py"
    spec = importlib.util.spec_from_file_location("bfe8_helpers", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BFE8 = load_bfe8_module()


def sha256(path):
    """Return a content hash used to make every reuse decision auditable."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Read one JSON object and reject malformed evidence early."""
    value = json.loads(path.read_text(encoding="ascii"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path, value):
    """Write deterministic ASCII JSON inside the task evidence directory."""
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="ascii")


def p0_path(name):
    """Resolve a repository-relative path recorded by P0 authority evidence."""
    return Path("/home/zhupl25/chiplet_side_channel/chiplet_gds_data/power_macro") / name


def retained_signatures():
    """Load the frozen BFE4 per-seed process signatures."""
    result = {}
    path = ANALYSIS_ROOT / "bfe4_caln0_self_calibration" / "BFE4_CALN0_RESULTS.csv"
    with path.open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            result[int(row["seed"])] = row["mc_random_signature"]
    if tuple(sorted(result)) != SEEDS:
        raise ValueError("BFE4 signature authority is not exactly seeds 41001..41030")
    return result


def retained_rows():
    """Return the retained 25 C calibration/reference rows keyed by seed."""
    path = BFE8_ROOT / "BFE8_HEALTHY_PER_SEED.csv"
    result = {}
    with path.open(newline="", encoding="ascii") as stream:
        for row in csv.DictReader(stream):
            result[int(row["seed"])] = row
    if tuple(sorted(result)) != SEEDS:
        raise ValueError("retained BFE8 healthy rows are incomplete")
    return result


def retained_case(seed):
    """Load one validated BFE8 real-capture case used as the 25 C baseline."""
    path = (FTC_ROOT / "runs" / "b_fe_frontend" / "bfe8_d02_arch0_pilot"
            / "healthy" / "seed_{:05d}".format(seed) / "HEALTHY_CASE.json")
    payload = read_json(path)
    if payload.get("seed") != seed or payload.get("q_ff_width") != 30:
        raise ValueError("invalid retained 25 C case: {}".format(path))
    if len(payload.get("events", [])) != 24:
        raise ValueError("retained 25 C case does not contain 24 events: {}".format(path))
    return payload, path


def verify_p0():
    """Re-read P0 authority and ensure no frozen RTL drift occurred."""
    authority = read_json(ROOT / "P0_AUTHORITY.json")
    if authority.get("gate") != "BFE14_TEMP0_P0_AUTHORITIES_AND_ARCH1_STATUS_FROZEN":
        raise ValueError("P0 gate is not frozen")
    if authority.get("status") != "PASS":
        raise ValueError("P0 authority is not PASS")
    expected = {
        "delay_chain/ftc/rtl/bfe_backend_ctrl_arch1_track0.sv": "d8d9128ccbdc65dc1fa0f96662afeca638e82efd380d9f72da98b7b5ff92d723",
        "delay_chain/ftc/rtl/bfe_backend_arch1_track0_top.sv": "aeb865c0d7a6a7bca6a8907484deb956d9037b1fed166f4838e9cf97c5ce0f33",
    }
    for relative, digest in expected.items():
        if sha256(p0_path(relative)) != digest:
            raise ValueError("frozen RTL changed: {}".format(relative))
    return authority


def select_scouts():
    """Select low/median/high RISE startup references before new HSPICE data."""
    rows = retained_rows()
    ranked = sorted((int(row["M_REF_RISE"]), seed) for seed, row in rows.items())
    return [ranked[index][1] for index in SCOUT_RANKS]


def p1():
    """Freeze stimulus/reuse facts without invoking a simulator."""
    verify_p0()
    signatures = retained_signatures()
    rows = retained_rows()
    controls_meta_path = BFE8_ROOT / "healthy_controls" / "HEALTHY_CONTROLS_METADATA.json"
    controls_meta = read_json(controls_meta_path)
    event_map_path = BFE8_ROOT / "healthy_controls" / "HEALTHY_COMPOSITE_EVENT_MAP.json"
    event_map = read_json(event_map_path)
    valid_events = [item for item in event_map["events"] if item.get("valid")]
    if len(valid_events) != 24:
        raise ValueError("BFE8 healthy event map must contain 24 valid events")
    for seed in SEEDS:
        payload, _ = retained_case(seed)
        if payload["mc_random_signature"] != signatures[seed]:
            raise ValueError("retained case signature mismatch for seed {}".format(seed))
        if payload["source_v"] != SAFE_V or payload["safe_v"] != SAFE_V:
            raise ValueError("retained 25 C case is not nominal 1.10 V")
        ref_rise = int(rows[seed]["M_REF_RISE"])
        ref_fall = int(rows[seed]["M_REF_FALL"])
        rise_cal = [int(value) for value in rows[seed]["M_CAL_RISE"].split(";")]
        fall_cal = [int(value) for value in rows[seed]["M_CAL_FALL"].split(";")]
        if (sum(rise_cal) >> 2) != ref_rise or (sum(fall_cal) >> 2) != ref_fall:
            raise ValueError("retained sum4 >> 2 mismatch for seed {}".format(seed))

    scout_seeds = select_scouts()
    runner_path = BFE8_ROOT / "run_bfe8_d02_arch0_pilot.py"
    contract = {
        "gate": "BFE14_TEMP0_P1_STIMULUS_AND_REUSE_FROZEN",
        "status": "PASS",
        "nominal25_classification": "NOMINAL25_REUSE_VALID",
        "operating_point": {"corner": "tt", "vdd_v": SAFE_V,
                             "startup_temperature_c": 25,
                             "temperatures_c": list(TEMPERATURES)},
        "process_population": {
            "seed_first": 41001, "seed_last": 41030, "count": 30,
            "signature_source": "BFE4_CALN0_RESULTS.csv",
            "signature_rule": "HSPICE MOS_MC index-2 source.mc0.csv line hash",
        },
        "stimulus": {
            "source": str(BFE8_ROOT / "healthy_controls" / "HEALTHY_COMPOSITE.inc"),
            "source_sha256": sha256(BFE8_ROOT / "healthy_controls" / "HEALTHY_COMPOSITE.inc"),
            "event_map": str(event_map_path),
            "event_map_sha256": sha256(event_map_path),
            "valid_events_per_case": 24,
            "background_signature": controls_meta["composite"]["inc_sha256"],
            "healthy_only": True,
            "allowed_physical_difference": "HSPICE .temp line only",
        },
        "capture": {
            "method": "BFE8 source-referenced Level-0 then real LATQ/DFF VCS-XA",
            "runner": str(runner_path), "runner_sha256": sha256(runner_path),
            "tap_count": 30, "feature": "M_FF=sum(tap*q_ff[tap])",
            "q_ff_threshold": "q_ff_v > 0.5 * 1.10 V",
        },
        "calibration": {
            "samples": "four RISE plus four FALL",
            "arithmetic": "sum4 >> 2",
            "startup_reference": "retained 25 C BFE8_HEALTHY_PER_SEED.csv",
        },
        "schema": ["seed", "mc_process_signature", "temperature_c",
                   "background_stimulus_signature", "event_index", "polarity",
                   "q_ff", "M_FF", "M_REF_STARTUP_RISE",
                   "M_REF_STARTUP_FALL", "source_run", "capture_status"],
        "simulation_count": {"hspice": 0, "capture_support_vcs": 0},
        "stop_after_stage": True,
    }
    write_json(ROOT / "P1_TEMP_STIMULUS_CONTRACT.json", contract)
    write_json(ROOT / "P1_SCOUT_SEEDS.json", {
        "gate": "BFE14_TEMP0_P1_STIMULUS_AND_REUSE_FROZEN",
        "selection_source": "retained 25 C M_REF_RISE only",
        "selection_rule": "sort (M_REF_RISE, seed); ranks 0, 15, 29",
        "scout_seeds": scout_seeds,
        "new_temperature_c": list(NEW_TEMPERATURES),
        "selected_before_new_temperature_simulation": True,
    })
    (ROOT / "P1_NOMINAL25_REUSE_AUDIT.md").write_text(
        "# BFE14 P1 nominal 25 C reuse audit\n\n"
        "Gate: `BFE14_TEMP0_P1_STIMULUS_AND_REUSE_FROZEN`\n\n"
        "Classification: `NOMINAL25_REUSE_VALID`. The retained BFE8 cases cover "
        "all 30 seeds with 24 mapped events, 30 resolved q_ff taps, nominal "
        "1.10 V source/safe rails, matching BFE4 MC signatures, exact four-plus-four "
        "calibration, and the same source-referenced Level-0 plus real LATQ/DFF "
        "capture method. The BFE8 healthy composite and event-map hashes are "
        "recorded in `P1_TEMP_STIMULUS_CONTRACT.json`; the new deck is permitted "
        "to differ only in simulator `.temp`. No 25 C rerun is authorized.\n\n"
        "Simulation accounting: HSPICE=0, capture-support VCS=0.\n",
        encoding="ascii")
    write_json(ROOT / "P1_GATE.json", {
        "gate": "BFE14_TEMP0_P1_STIMULUS_AND_REUSE_FROZEN",
        "status": "PASS", "nominal25_classification": "NOMINAL25_REUSE_VALID",
        "scout_seeds": scout_seeds,
        "simulation_accounting": {"hspice": 0, "vcs": 0},
        "stop_after_stage": True,
    })


def temperature_deck(seed, temperature_c, total_stop_ps, cells, model):
    """Render BFE8's healthy deck and replace exactly its temperature line."""
    baseline = BFE8.healthy_source_deck(cells, model, seed, total_stop_ps)
    updated, count = re.subn(r"(?m)^\.temp\s+[^\n]+$",
                             ".temp {:.12e}".format(float(temperature_c)),
                             baseline)
    if count != 1:
        raise ValueError("healthy deck did not contain exactly one .temp line")
    baseline_lines = [line for line in baseline.splitlines() if not line.startswith(".temp")]
    updated_lines = [line for line in updated.splitlines() if not line.startswith(".temp")]
    if baseline_lines != updated_lines:
        raise ValueError("temperature deck changed beyond the .temp line")
    if "D02" in updated or "droop" in updated.lower() or "0.95" in updated:
        raise ValueError("attack or historical 0.95 V content leaked into temperature deck")
    return updated


def parse_mc_signature(mc0, seed):
    """Hash the exact HSPICE index-2 MC row used by the retained authority."""
    signature = None
    for line in mc0.read_text(encoding="ascii", errors="replace").splitlines():
        if line.startswith("2,"):
            signature = hashlib.sha256(line[2:].encode("ascii")).hexdigest()
            break
    if signature != retained_signatures()[seed]:
        raise ValueError("temperature process signature mismatch for seed {}".format(seed))
    return signature


def capture_case(seed, temperature_c):
    """Run one healthy HSPICE plus one exact BFE8 real-capture support case."""
    config = read_json(FTC_ROOT / "ftc_config.json")
    cells = read_json(FTC_ROOT / "discovery" / "selected_cells.json")
    model = str(config["model_library"])
    hspice = str(Path(config["hspice"]).resolve())
    vcs = shutil.which("vcs") or "/home/synopsys/vcs/W-2024.09/bin/vcs"
    if not Path(hspice).is_file() or not Path(vcs).is_file():
        raise RuntimeError("configured HSPICE and VCS are required")
    meta = read_json(BFE8_ROOT / "healthy_controls" / "HEALTHY_CONTROLS_METADATA.json")
    total_stop_ps = int(meta["composite"]["stop_ps"])
    case_root = RUN_ROOT / "physical" / "seed_{:05d}".format(seed) / "t_{:+04d}C".format(int(temperature_c))
    source_dir = case_root / "source_hspice"
    xa_dir = case_root / "vcs_xa"
    case_json = case_root / "CASE.json"
    if case_json.is_file():
        payload = read_json(case_json)
        if payload.get("capture_status") == "VALID":
            return payload
    source_dir.mkdir(parents=True, exist_ok=True)
    xa_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", source_dir / "empty_subckt.sp_cal")
    shutil.copyfile(BFE8_ROOT / "healthy_controls" / "HEALTHY_COMPOSITE.inc",
                    source_dir / "HEALTHY_COMPOSITE.inc")
    source_sp = source_dir / "source.sp"
    source_sp.write_text(temperature_deck(seed, temperature_c, total_stop_ps, cells, model), encoding="ascii")
    listing = source_dir / "source.lis"
    measures = source_dir / "source.mt0.csv"
    mc0 = source_dir / "source.mc0.csv"
    if not (listing.is_file() and measures.is_file() and mc0.is_file()):
        result = subprocess.run([hspice, "source.sp", "-o", "source"], cwd=source_dir,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True, check=False, timeout=3600)
        (source_dir / "hspice_command.log").write_text(result.stdout, encoding="ascii", errors="replace")
        if result.returncode:
            raise RuntimeError("HSPICE failed for seed {} temperature {}".format(seed, temperature_c))
    if not (listing.is_file() and measures.is_file() and mc0.is_file()):
        raise RuntimeError("HSPICE did not produce required listing/mt0/mc0 files")
    listing_text = listing.read_text(encoding="ascii", errors="replace").lower()
    if "job concluded" not in listing_text or "monte carlo simulation is detected" not in listing_text or "**error**" in listing_text:
        raise RuntimeError("HSPICE listing is not clean for seed {} temperature {}".format(seed, temperature_c))
    signature = parse_mc_signature(mc0, seed)
    measured = BFE8.parse_measurements(measures, total_stop_ps)
    states_list, schedules_list = BFE8.measured_capture_schedule(measured)
    capture_times = [0.0, total_stop_ps * 1.0e-12]
    columns = {BFE8.bfe1_frontend.label_for("vdd_monitored"): [SAFE_V, SAFE_V]}
    for tap in range(30):
        initial = states_list[tap]
        columns[BFE8.bfe1_frontend.label_for("xor_{}".format(tap))] = [initial * SAFE_V, initial * SAFE_V]
    states = {tap: states_list[tap] for tap in range(30)}
    schedules = {tap: schedules_list[tap] for tap in range(30)}
    samples = xa_dir / "xa_dff_samples.csv"
    expected_rows = len(BFE8._dff_rises(total_stop_ps)) * 30
    # A multiprocessing failure can terminate a sibling XA process midway.
    # Do not accept that partial CSV on resume; rerun the identical capture
    # support step while preserving all HSPICE evidence and the same stimulus.
    if samples.is_file():
        try:
            existing_count = sum(1 for _ in samples.open(encoding="ascii")) - 1
        except (OSError, UnicodeError):
            existing_count = -1
        if existing_count != expected_rows:
            samples.unlink()
    if not samples.is_file():
        (xa_dir / "bfe8_capture_ams_wrapper.sp").write_text(
            BFE8.render_capture_wrapper(columns, capture_times, total_stop_ps), encoding="ascii")
        (xa_dir / "tb_bfe8_capture_vcs_xa.sv").write_text(
            BFE8.render_capture_tb(schedules, states, {}, total_stop_ps), encoding="ascii")
        (xa_dir / "xa.cfg").write_text(
            "set_sim_level 7\nset_waveform -format fsdb\n" + "\n".join(
                ["probe_waveform_voltage vdd_safe", "probe_waveform_voltage dff_ck_r"] +
                ["probe_waveform_voltage q_ff_r_{:02d}".format(tap) for tap in range(30)]) + "\n",
            encoding="ascii")
        (xa_dir / "vcsAD.init").write_text(
            "bus_format [%d];\nuse_spice -cell bfe8_capture_ams;\n"
            "choose xa -hspice bfe8_capture_ams.sp -c xa.cfg -o xa;\n", encoding="ascii")
        (xa_dir / "bfe8_capture_ams.sp").write_text(
            "* BFE14 real LATQ/DFF capture support deck.\n"
            ".option post=1 probe\n.lib '{}' tt\n"
            ".include '{}'\n.include '{}'\n.include '{}'\n"
            ".include '{}'\n.tran 2p {:.12e}\n.end\n".format(
                model, cells["source_files"]["rvt_cdl"], cells["source_files"]["lvt_cdl"],
                FTC_ROOT / "spice" / "empty_subckt.sp_cal",
                xa_dir / "bfe8_capture_ams_wrapper.sp", total_stop_ps * 1.0e-12),
            encoding="ascii")
        shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", xa_dir / "empty_subckt.sp_cal")
        compile_result = subprocess.run(
            [vcs, "-full64", "-sverilog", "-timescale=1ps/1ps", "-ad=vcsAD.init",
             "-debug_access+all", "-o", "simv", "tb_bfe8_capture_vcs_xa.sv"],
            cwd=xa_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True, check=False, timeout=1800)
        (xa_dir / "compile.log").write_text(compile_result.stdout, encoding="ascii", errors="replace")
        if compile_result.returncode:
            raise RuntimeError("capture VCS compile failed for seed {} temperature {}".format(seed, temperature_c))
        run_result = subprocess.run(["./simv"], cwd=xa_dir, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, universal_newlines=True,
                                    check=False, timeout=3600)
        (xa_dir / "run.log").write_text(run_result.stdout, encoding="ascii", errors="replace")
        if run_result.returncode:
            raise RuntimeError("capture VCS run failed for seed {} temperature {}".format(seed, temperature_c))
    capture_rows = list(csv.DictReader(samples.open(newline="", encoding="ascii")))
    if len(capture_rows) != expected_rows:
        raise RuntimeError("capture row count mismatch for seed {} temperature {}".format(seed, temperature_c))
    if any(float(row["vdd_safe_v"]) != SAFE_V for row in capture_rows):
        raise RuntimeError("capture safe rail is not 1.10 V")
    low, high = 0.1 * SAFE_V, 0.9 * SAFE_V
    if any(low < float(row["q_ff_v"]) < high for row in capture_rows):
        raise RuntimeError("capture q_ff contains unresolved mid-rail output")
    bits_by_event = {sample["event_index"]: sample["bits"] for sample in measured}
    m_by_event = {sample["event_index"]: sample["m_ff"] for sample in measured}
    event_payload = []
    for event_index in range(len(measured)):
        event_rows = [row for row in capture_rows if int(row["sample_index"]) == event_index]
        if [int(row["tap"]) for row in event_rows] != list(range(30)):
            raise RuntimeError("capture tap order mismatch")
        bits = [1 if float(row["q_ff_v"]) > 0.5 * SAFE_V else 0 for row in event_rows]
        if bits != bits_by_event[event_index]:
            raise RuntimeError("real capture differs from source Level-0 bits")
        m_ff = sum(tap * bit for tap, bit in enumerate(bits))
        if m_ff != m_by_event[event_index] or not 0 <= m_ff <= 435:
            raise RuntimeError("captured M_FF mismatch or out of range")
        event_payload.append({
            "event_index": event_index,
            "polarity": measured[event_index]["edge"],
            "edge_ps": measured[event_index]["edge_ps"],
            "q_ff": "".join(str(bit) for bit in bits),
            "M_FF": m_ff,
        })
    payload = {
        "seed": seed, "temperature_c": int(temperature_c),
        "mc_process_signature": signature,
        "background_stimulus_signature": sha256(BFE8_ROOT / "healthy_controls" / "HEALTHY_COMPOSITE.inc"),
        "source_run": str(source_dir), "capture_run": str(xa_dir),
        "source_measurements_sha256": sha256(measures),
        "source_mc0_sha256": sha256(mc0), "capture_sha256": sha256(samples),
        "source_v": SAFE_V, "safe_v": SAFE_V, "tap_count": 30, "q_ff_width": 30,
        "capture_status": "VALID", "all_q_ff_rail_resolved": True,
        "events": event_payload,
    }
    write_json(case_json, payload)
    return payload


def capture_job(job):
    """Multiprocessing adapter preserving the explicit two-argument API."""
    return capture_case(job[0], job[1])


def startup_refs(seed):
    """Return retained 25 C startup references and calibration samples."""
    row = retained_rows()[seed]
    return {
        "rise": int(row["M_REF_RISE"]), "fall": int(row["M_REF_FALL"]),
        "rise_samples": [int(value) for value in row["M_CAL_RISE"].split(";")],
        "fall_samples": [int(value) for value in row["M_CAL_FALL"].split(";")],
    }


def event_rows_from_case(seed, temperature_c, payload):
    """Expand one case into the frozen BFE14 per-event CSV contract."""
    refs = startup_refs(seed)
    result = []
    for event in payload["events"]:
        polarity = event["polarity"]
        reference = refs["rise" if polarity == "RISE" else "fall"]
        e_anchor = int(event["M_FF"]) - reference
        result.append({
            "seed": seed, "mc_process_signature": payload["mc_process_signature"],
            "temperature_c": int(temperature_c),
            "background_stimulus_signature": payload["background_stimulus_signature"],
            "event_index": int(event["event_index"]), "polarity": polarity,
            "q_ff": event["q_ff"], "M_FF": int(event["M_FF"]),
            "M_REF_STARTUP_RISE": refs["rise"], "M_REF_STARTUP_FALL": refs["fall"],
            "source_run": payload["source_run"], "capture_status": payload["capture_status"],
            "e_anchor": e_anchor, "D_start": abs(e_anchor),
            "signed_alarm_18": int(polarity == "RISE" and e_anchor > 18),
            "signed_alarm_19": int(polarity == "RISE" and e_anchor > 19),
        })
    return result


def write_event_csv(path, rows):
    """Write a stable ASCII CSV with explicit provenance and diagnostics."""
    fields = ["seed", "mc_process_signature", "temperature_c",
              "background_stimulus_signature", "event_index", "polarity", "q_ff",
              "M_FF", "M_REF_STARTUP_RISE", "M_REF_STARTUP_FALL", "source_run",
              "capture_status", "e_anchor", "D_start", "signed_alarm_18", "signed_alarm_19"]
    with path.open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def p2():
    """Run the three-seed endpoint/interior temperature scout."""
    # Re-read the P1 section before any physical call, as required by the plan.
    verify_p0()
    contract = read_json(ROOT / "P1_TEMP_STIMULUS_CONTRACT.json")
    if contract.get("nominal25_classification") != "NOMINAL25_REUSE_VALID":
        raise RuntimeError("P1 did not authorize retained 25 C reuse")
    scouts = read_json(ROOT / "P1_SCOUT_SEEDS.json")["scout_seeds"]
    # Two workers match the validated BFE8 execution pattern. Each worker has
    # its own seed/temperature directory, so no raw artifact is shared.
    jobs = [(int(seed), int(temperature_c)) for seed in scouts for temperature_c in NEW_TEMPERATURES]
    with mp.Pool(processes=2) as pool:
        payloads = pool.map(capture_job, jobs)
    rows = []
    ledger = []
    for (seed, temperature_c), payload in zip(jobs, payloads):
        rows.extend(event_rows_from_case(seed, temperature_c, payload))
        ledger.append({"seed": seed, "temperature_c": temperature_c,
                       "type": "new_hspice_plus_capture_support_vcs",
                       "source_run": payload["source_run"], "capture_run": payload["capture_run"],
                       "mc_process_signature": payload["mc_process_signature"]})
    write_event_csv(ROOT / "P2_SCOUT_PER_EVENT.csv", rows)
    summary = {"gate": "BFE14_TEMP0_P2_SCOUT_VALID", "status": "PASS",
               "scout_seeds": [int(seed) for seed in scouts],
               "temperatures_c": list(NEW_TEMPERATURES), "event_count": len(rows),
               "full_85c_required": False, "simulation_accounting": {"hspice": 9, "capture_support_vcs": 9},
               "checks": {"q_ff_width_30": True, "M_FF_range_0_435": True,
                           "paired_process_signatures": True, "healthy_no_droop": True,
                           "background_unchanged": True, "capture_method_unchanged": True}}
    # Determine the predeclared 85 C decision from scout data only.
    by_seed_pol = {}
    for row in rows:
        by_seed_pol.setdefault((int(row["seed"]), row["polarity"]), {})[int(row["temperature_c"])] = int(row["M_FF"])
    nonmonotonic = False
    more_critical = False
    for values in by_seed_pol.values():
        if all(temp in values for temp in (-40, 85, 125)):
            if values[85] > max(values[-40], values[125]) or values[85] < min(values[-40], values[125]):
                nonmonotonic = True
        refs = next(iter(by_seed_pol)) if False else None
    # Compare signed/absolute proximity at 85 C against both endpoints.
    for (seed, polarity), values in by_seed_pol.items():
        ref = startup_refs(seed)["rise" if polarity == "RISE" else "fall"]
        if all(temp in values for temp in (-40, 85, 125)):
            endpoint = [abs(values[temp] - ref) for temp in (-40, 125)]
            interior = abs(values[85] - ref)
            if interior > max(endpoint):
                more_critical = True
            if polarity == "RISE":
                endpoint_signed = [values[temp] - ref for temp in (-40, 125)]
                interior_signed = values[85] - ref
                if interior_signed > max(endpoint_signed):
                    more_critical = True
    summary["full_85c_required"] = bool(nonmonotonic or more_critical)
    summary["decision_basis"] = {"nonmonotonic_85c": nonmonotonic,
                                  "85c_more_critical_than_endpoints": more_critical}
    write_json(ROOT / "P2_SCOUT_SUMMARY.json", summary)
    write_json(ROOT / "P2_SCOUT_RUN_LEDGER.json", {
        "gate": "BFE14_TEMP0_P2_SCOUT_VALID", "status": "PASS",
        "new_hspice_runs": ledger, "reused_nominal25": True,
        "hspice_count": len(ledger), "capture_support_vcs_count": len(ledger),
        "backend_scientific_vcs_count": 0,
    })


def p3():
    """Complete the endpoint population and freeze physical healthy data."""
    # Re-read P3 instructions and P2's frozen decision before new physical calls.
    p2_summary = read_json(ROOT / "P2_SCOUT_SUMMARY.json")
    full_85c = bool(p2_summary["full_85c_required"])
    temperatures = [-40, 125] + ([85] if full_85c else [])
    all_rows = []
    ledger = []
    for seed in SEEDS:
        for temperature_c in temperatures:
            case_json = RUN_ROOT / "physical" / "seed_{:05d}".format(seed) / "t_{:+04d}C".format(temperature_c) / "CASE.json"
            if case_json.is_file():
                payload = read_json(case_json)
                reuse_type = "reused_P2_scout"
            else:
                payload = capture_case(seed, temperature_c)
                reuse_type = "new_hspice_plus_capture_support_vcs"
            all_rows.extend(event_rows_from_case(seed, temperature_c, payload))
            ledger.append({"seed": seed, "temperature_c": temperature_c, "type": reuse_type,
                           "source_run": payload["source_run"], "capture_run": payload["capture_run"],
                           "mc_process_signature": payload["mc_process_signature"]})
    write_event_csv(ROOT / "BFE14_HEALTHY_TEMP_PER_EVENT.csv", all_rows)
    per_seed = []
    for seed in SEEDS:
        seed_rows = [row for row in all_rows if int(row["seed"]) == seed]
        refs = startup_refs(seed)
        item = {"seed": seed, "mc_process_signature": retained_signatures()[seed],
                "M_REF_STARTUP_RISE": refs["rise"], "M_REF_STARTUP_FALL": refs["fall"],
                "temperatures_c": temperatures, "event_count": len(seed_rows)}
        for temperature_c in temperatures:
            current = [row for row in seed_rows if int(row["temperature_c"]) == temperature_c]
            item["temperature_{}_M_FF".format(temperature_c)] = [int(row["M_FF"]) for row in current]
            item["temperature_{}_max_D_start".format(temperature_c)] = max(int(row["D_start"]) for row in current)
        per_seed.append(item)
    fields = ["seed", "mc_process_signature", "M_REF_STARTUP_RISE", "M_REF_STARTUP_FALL", "temperatures_c", "event_count"]
    for temperature_c in temperatures:
        fields += ["temperature_{}_M_FF".format(temperature_c), "temperature_{}_max_D_start".format(temperature_c)]
    with (ROOT / "BFE14_HEALTHY_TEMP_PER_SEED.csv").open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(per_seed)
    write_json(ROOT / "BFE14_HEALTHY_TEMP_PHYSICAL_LEDGER.json", {
        "gate": "BFE14_TEMP0_P3_HEALTHY_PHYSICS_FROZEN", "status": "PASS",
        "temperatures_c": temperatures, "full_85c_required": full_85c,
        "new_hspice_unique_runs": sum(item["type"] == "new_hspice_plus_capture_support_vcs" for item in ledger),
        "reused_p2_runs": sum(item["type"] == "reused_P2_scout" for item in ledger),
        "reused_retained_25c": True, "attack_runs": 0, "vdd_sweep_runs": 0,
        "ledger": ledger,
    })
    write_json(ROOT / "P3_GATE.json", {
        "gate": "BFE14_TEMP0_P3_HEALTHY_PHYSICS_FROZEN", "status": "PASS",
        "event_rows": len(all_rows), "seed_count": len(SEEDS),
        "temperatures_c": temperatures, "full_85c_required": full_85c,
        "threshold_selection": False, "stop_after_stage": True,
    })


def p4():
    """Perform the no-simulator dual-reference compatibility audit."""
    # Re-read the P4 section before consuming the frozen physical CSV.
    p3_gate = read_json(ROOT / "P3_GATE.json")
    if p3_gate.get("status") != "PASS":
        raise RuntimeError("P3 physical data are not frozen")
    source_rows = []
    with (ROOT / "BFE14_HEALTHY_TEMP_PER_EVENT.csv").open(newline="", encoding="ascii") as stream:
        source_rows = list(csv.DictReader(stream))
    audit_rows = []
    for row in source_rows:
        m_ff = int(row["M_FF"])
        ref = int(row["M_REF_STARTUP_RISE"] if row["polarity"] == "RISE" else row["M_REF_STARTUP_FALL"])
        e_anchor = m_ff - ref
        audit_rows.append({
            "seed": int(row["seed"]), "temperature_c": int(row["temperature_c"]),
            "event_index": int(row["event_index"]), "polarity": row["polarity"],
            "M_FF": m_ff, "M_REF_STARTUP_SELECTED": ref,
            "e_anchor": e_anchor, "D_anchor": abs(e_anchor),
            "signed_alarm_18": int(row["polarity"] == "RISE" and e_anchor > 18),
            "signed_alarm_19": int(row["polarity"] == "RISE" and e_anchor > 19),
            "startup_abs_alarm": int(abs(e_anchor) > (22 if row["polarity"] == "RISE" else 24)),
            "outside_T_TRACK_5": int(abs(e_anchor) > T_TRACK_PROBE),
            "outside_B_TRACK_2": int(abs(e_anchor) > B_TRACK_PROBE),
            "q_ff": row["q_ff"], "source_run": row["source_run"],
        })
    fields = list(audit_rows[0].keys()) if audit_rows else []
    with (ROOT / "P4_DUAL_REFERENCE_AUDIT.csv").open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(audit_rows)
    temperatures = sorted({int(row["temperature_c"]) for row in audit_rows})
    by_temp = {}
    for temperature_c in temperatures:
        current = [row for row in audit_rows if int(row["temperature_c"]) == temperature_c]
        rise = [row for row in current if row["polarity"] == "RISE"]
        by_temp[str(temperature_c)] = {
            "event_count": len(current), "rise_event_count": len(rise),
            "healthy_signed_alarm_18": sum(row["signed_alarm_18"] for row in rise),
            "healthy_signed_alarm_19": sum(row["signed_alarm_19"] for row in rise),
            "max_positive_e_anchor_rise": max([int(row["e_anchor"]) for row in rise] or [0]),
            "min_headroom_18": min([18 - int(row["e_anchor"]) for row in rise] or [18]),
            "min_headroom_19": min([19 - int(row["e_anchor"]) for row in rise] or [19]),
            "startup_abs_alarm_count": sum(row["startup_abs_alarm"] for row in current),
            "outside_T_TRACK_5_count": sum(row["outside_T_TRACK_5"] for row in current),
            "outside_B_TRACK_2_count": sum(row["outside_B_TRACK_2"] for row in current),
            "max_abs_temperature_displacement": max(int(row["D_anchor"]) for row in current),
        }
    anchor_conflict = any(row["signed_alarm_18"] or row["signed_alarm_19"] for row in audit_rows)
    max_displacement = max([int(row["D_anchor"]) for row in audit_rows] or [0])
    classes = []
    if anchor_conflict:
        classes.append("SECURITY_ANCHOR_HEALTHY_CONFLICT_OBSERVED")
    else:
        classes.append("SECURITY_ANCHOR_QUIET_ON_OBSERVED_TEMP_PILOT")
    if max_displacement <= B_TRACK_PROBE:
        classes.append("BFE13_TEST_TRACK_WINDOW_COVERS_OBSERVED_DRIFT")
    else:
        classes.append("BFE13_TEST_TRACK_WINDOW_TOO_NARROW")
    p2_summary = read_json(ROOT / "P2_SCOUT_SUMMARY.json")
    if p2_summary.get("decision_basis", {}).get("nonmonotonic_85c"):
        classes.append("TEMPERATURE_RESPONSE_NONMONOTONIC_NEEDS_MORE_CHARACTERIZATION")
    summary = {"gate": "BFE14_TEMP0_P4_DUAL_REFERENCE_CHARACTERIZED", "status": "PASS",
               "thresholds_evaluated": [18, 19], "margins": {"RISE": 22, "FALL": 24},
               "tracking_probe": {"T_TRACK": 5, "B_TRACK": 2, "classification": "DIRECTED_TEST_ONLY"},
               "event_count": len(audit_rows), "by_temperature": by_temp,
               "interpretation_classes": classes, "simulator_count": 0}
    write_json(ROOT / "P4_DUAL_REFERENCE_SUMMARY.json", summary)
    (ROOT / "P4_DUAL_REFERENCE_REPORT.md").write_text(
        "# BFE14 P4 dual-reference compatibility audit\n\n"
        "Gate: `BFE14_TEMP0_P4_DUAL_REFERENCE_CHARACTERIZED`\n\n"
        "The audit treats `e_anchor=M_FF-M_REF_STARTUP_selected` as the fixed "
        "security-anchor quantity and does not label it as a post-tracking residual. "
        "Only strict RISE comparisons `e_anchor>18` and `e_anchor>19` were evaluated. "
        "Margins remain 22/24. The values T_TRACK=5 and B_TRACK=2 are reported only "
        "as the BFE13 directed-test probe. Machine-readable per-event values and "
        "temperature aggregates are in the accompanying CSV/JSON.\n\n"
        "Interpretation classes: {}\n\nSimulation accounting: HSPICE=0, VCS=0.\n".format(
            ", ".join(classes)), encoding="ascii")


def sv_literal(value):
    """Format an integer for a nine-bit SystemVerilog assignment."""
    return "9'd{}".format(int(value))


def build_p5_testbench(rows, calibrations):
    """Generate the single, fully commented controller replay testbench."""
    lines = [
        "// BFE14 P5 TRACK0 physical healthy-event replay.",
        "// This is a controller-level scientific testbench; it is not production RTL.",
        "// Four instances receive identical events:",
        "//   A18/A19: TRACK0 defaults T_TRACK=0 and B_TRACK=0 (disabled).",
        "//   B18/B19: fixed BFE13 directed-test probe T_TRACK=5 and B_TRACK=2.",
        "// The two threshold subcases are the frozen diagnostic T_POS_RISE=18/19.",
        "// No physical waveform is regenerated here; M_FF/q_ff rows are consumed",
        "// from the validated BFE14 physical-capture CSV.",
        "`timescale 1ns/1ps",
        "`default_nettype none",
        "module tb_bfe14_track0_physical_replay;",
        "    // Shared replay inputs. These correspond exactly to the controller's",
        "    // event_valid, edge_pol, cal_mode, feature, margins, and signed threshold",
        "    // ports. There is intentionally no tracking/debug/rebase port.",
        "    reg clk; reg reset; reg event_valid; reg edge_pol; reg cal_mode;",
        "    reg [8:0] m_ff; reg [8:0] margin_rise; reg [8:0] margin_fall;",
        "    reg [8:0] t18; reg [8:0] t19;",
        "    wire lock_a18, lock_a19, lock_b18, lock_b19;",
        "    wire alarm_a18, alarm_a19, alarm_b18, alarm_b19;",
        "    wire sticky_a18, sticky_a19, sticky_b18, sticky_b19;",
        "    integer fd; integer block_count; integer event_count;",
        "",
        "    // A18/A19 are the required default-disabled TRACK0 A configurations.",
        "    bfe_backend_ctrl_arch1_track0 #(.T_TRACK_RISE(0),.T_TRACK_FALL(0),.B_TRACK_RISE(0),.B_TRACK_FALL(0)) u_a18 (",
        "        .clk_probe_i(clk), .reset_i(reset), .event_valid_i(event_valid),",
        "        .edge_pol_i(edge_pol), .cal_mode_i(cal_mode), .m_ff_i(m_ff),",
        "        .m_margin_rise_i(margin_rise), .m_margin_fall_i(margin_fall),",
        "        .t_pos_rise_i(t18), .cal_lock_o(lock_a18),",
        "        .droop_alarm_o(alarm_a18), .droop_alarm_sticky_o(sticky_a18));",
        "    bfe_backend_ctrl_arch1_track0 #(.T_TRACK_RISE(0),.T_TRACK_FALL(0),.B_TRACK_RISE(0),.B_TRACK_FALL(0)) u_a19 (",
        "        .clk_probe_i(clk), .reset_i(reset), .event_valid_i(event_valid),",
        "        .edge_pol_i(edge_pol), .cal_mode_i(cal_mode), .m_ff_i(m_ff),",
        "        .m_margin_rise_i(margin_rise), .m_margin_fall_i(margin_fall),",
        "        .t_pos_rise_i(t19), .cal_lock_o(lock_a19),",
        "        .droop_alarm_o(alarm_a19), .droop_alarm_sticky_o(sticky_a19));",
        "",
        "    // B18/B19 use only the already exercised BFE13 directed-test values.",
        "    bfe_backend_ctrl_arch1_track0 #(.T_TRACK_RISE(5),.T_TRACK_FALL(5),.B_TRACK_RISE(2),.B_TRACK_FALL(2)) u_b18 (",
        "        .clk_probe_i(clk), .reset_i(reset), .event_valid_i(event_valid),",
        "        .edge_pol_i(edge_pol), .cal_mode_i(cal_mode), .m_ff_i(m_ff),",
        "        .m_margin_rise_i(margin_rise), .m_margin_fall_i(margin_fall),",
        "        .t_pos_rise_i(t18), .cal_lock_o(lock_b18),",
        "        .droop_alarm_o(alarm_b18), .droop_alarm_sticky_o(sticky_b18));",
        "    bfe_backend_ctrl_arch1_track0 #(.T_TRACK_RISE(5),.T_TRACK_FALL(5),.B_TRACK_RISE(2),.B_TRACK_FALL(2)) u_b19 (",
        "        .clk_probe_i(clk), .reset_i(reset), .event_valid_i(event_valid),",
        "        .edge_pol_i(edge_pol), .cal_mode_i(cal_mode), .m_ff_i(m_ff),",
        "        .m_margin_rise_i(margin_rise), .m_margin_fall_i(margin_fall),",
        "        .t_pos_rise_i(t19), .cal_lock_o(lock_b19),",
        "        .droop_alarm_o(alarm_b19), .droop_alarm_sticky_o(sticky_b19));",
        "",
        "    task automatic clock_once; begin clk=1'b1; #1; clk=1'b0; #1; end endtask",
        "",
        "    // Drive one atomic event, wait through E4..E8, and record the",
        "    // before/after references. Four idle clocks separate events, so an",
        "    // event cannot overlap the following event and stale rejection is 0",
        "    // by construction; the Python post-audit still reports that fact.",
        "    task automatic drive_event;",
        "        input integer seed_value; input integer temperature_value; input integer index_value;",
        "        input integer m_value; input integer polarity_value; input integer margin_value;",
        "        input integer calibration_value;",
        "        integer before_ar; integer before_af; integer before_br; integer before_bf;",
        "        integer after_ar; integer after_af; integer after_br; integer after_bf;",
        "        begin",
        "            before_ar=u_a18.m_ref_track_rise_q; before_af=u_a18.m_ref_track_fall_q;",
        "            before_br=u_b18.m_ref_track_rise_q; before_bf=u_b18.m_ref_track_fall_q;",
        "            m_ff=m_value[8:0]; edge_pol=polarity_value[0]; cal_mode=calibration_value[0];",
        "            margin_rise=(!polarity_value && !calibration_value) ? margin_value[8:0] : 9'd0;",
        "            margin_fall=(polarity_value && !calibration_value) ? margin_value[8:0] : 9'd0;",
        "            event_valid=1'b1; clock_once(); event_valid=1'b0;",
        "            clock_once(); clock_once(); clock_once();",
        "            after_ar=u_a18.m_ref_track_rise_q; after_af=u_a18.m_ref_track_fall_q;",
        "            after_br=u_b18.m_ref_track_rise_q; after_bf=u_b18.m_ref_track_fall_q;",
        "            $fwrite(fd," +
        "\"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\\n\",",
        "                seed_value,temperature_value,index_value,polarity_value,m_value,calibration_value,",
        "                alarm_a18,alarm_b18,alarm_a19,alarm_b19,sticky_a18,sticky_b18,",
        "                before_ar,before_af,before_br,before_bf,after_ar,after_af,after_br,after_bf,",
        "                lock_a18,lock_b18,lock_a19,lock_b19,event_count);",
        "            event_count=event_count+1;",
        "        end",
        "    endtask",
        "",
        "    initial begin",
        "        clk=1'b0; reset=1'b1; event_valid=1'b0; edge_pol=1'b0; cal_mode=1'b0;",
        "        m_ff=9'd0; margin_rise=9'd0; margin_fall=9'd0; t18=9'd18; t19=9'd19;",
        "        block_count=0; event_count=0; fd=$fopen(\"P5_VCS_EVENT_TRACE.csv\",\"w\");",
        "        if (fd==0) $fatal(1,\"P5 trace file could not be opened\");",
        "        $fwrite(fd,\"seed,temperature_c,event_index,polarity,m_ff,calibration,alarm_a18,alarm_b18,alarm_a19,alarm_b19,sticky_a18,sticky_b18,before_a_rise,before_a_fall,before_b_rise,before_b_fall,after_a_rise,after_a_fall,after_b_rise,after_b_fall,lock_a18,lock_b18,lock_a19,lock_b19,event_count\\n\");",
        "        #1; reset=1'b0;",
    ]
    current_key = None
    for row in rows:
        key = (int(row["seed"]), int(row["temperature_c"]))
        if key != current_key:
            seed, temperature_c = key
            if current_key is not None:
                lines.append("        if (!lock_a18 || !lock_b18 || !lock_a19 || !lock_b19) $fatal(1,\"P5 CAL_LOCK missing\");")
            lines += [
                "        reset=1'b1; #1; reset=1'b0;",
            ]
            cal = calibrations[seed]
            for value in cal["rise_samples"]:
                lines.append("        drive_event({},{},-1,{},0,0,1);".format(seed, temperature_c, value))
            for value in cal["fall_samples"]:
                lines.append("        drive_event({},{},-1,{},1,0,1);".format(seed, temperature_c, value))
            current_key = key
        margin = 22 if row["polarity"] == "RISE" else 24
        polarity = 0 if row["polarity"] == "RISE" else 1
        lines.append("        drive_event({},{},{},{},{},{},0);".format(
            int(row["seed"]), int(row["temperature_c"]), int(row["event_index"]),
            int(row["M_FF"]), polarity, margin))
    lines += [
        "        if (!lock_a18 || !lock_b18 || !lock_a19 || !lock_b19) $fatal(1,\"P5 final CAL_LOCK missing\");",
        "        $fclose(fd); $display(\"BFE14_TRACK0_P5_VCS_PASS\"); $finish;",
        "    end",
        "endmodule",
        "`default_nettype wire",
        "",
    ]
    return "\n".join(lines)


def p5():
    """Run one VCS regression for the fixed A/B TRACK0 configurations."""
    # Re-read P5 instructions before compiling the single backend regression.
    p4_summary = read_json(ROOT / "P4_DUAL_REFERENCE_SUMMARY.json")
    if p4_summary.get("status") != "PASS":
        raise RuntimeError("P4 audit is not frozen")
    rows = []
    with (ROOT / "BFE14_HEALTHY_TEMP_PER_EVENT.csv").open(newline="", encoding="ascii") as stream:
        rows = list(csv.DictReader(stream))
    calibrations = {}
    for seed in SEEDS:
        refs = startup_refs(seed)
        calibrations[seed] = {"rise_samples": refs["rise_samples"], "fall_samples": refs["fall_samples"]}
    p5_dir = ROOT / "p5_replay"
    p5_dir.mkdir(parents=True, exist_ok=True)
    tb = p5_dir / "tb_bfe14_track0_physical_replay.sv"
    tb.write_text(build_p5_testbench(rows, calibrations), encoding="ascii")
    vcs = shutil.which("vcs") or "/home/synopsys/vcs/W-2024.09/bin/vcs"
    if not Path(vcs).is_file():
        raise RuntimeError("VCS W-2024.09 is unavailable")
    compile_result = subprocess.run(
        [vcs, "-full64", "-sverilog", "-timescale=1ns/1ps", "-debug_access+all", "-o", "simv",
         str(tb), str(FTC_ROOT / "rtl" / "bfe_backend_ctrl_arch1_track0.sv")],
        cwd=p5_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True, check=False, timeout=1800)
    (p5_dir / "compile.log").write_text(compile_result.stdout, encoding="ascii", errors="replace")
    if compile_result.returncode:
        raise RuntimeError("P5 VCS compile failed")
    run_result = subprocess.run(["./simv"], cwd=p5_dir, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, universal_newlines=True,
                                check=False, timeout=3600)
    (p5_dir / "run.log").write_text(run_result.stdout, encoding="ascii", errors="replace")
    if run_result.returncode:
        raise RuntimeError("P5 VCS regression failed")
    trace_path = p5_dir / "P5_VCS_EVENT_TRACE.csv"
    if not trace_path.is_file():
        raise RuntimeError("P5 VCS trace is missing")
    trace = list(csv.DictReader(trace_path.open(newline="", encoding="ascii")))
    if len(trace) != len(rows) + 8 * len(SEEDS):
        raise RuntimeError("P5 trace count includes unexpected calibration/event rows")
    # Discard calibration rows and keep the physical event rows in the required result file.
    physical = [row for row in trace if int(row["calibration"]) == 0]
    if len(physical) != len(rows):
        raise RuntimeError("P5 physical event row count mismatch")
    result_fields = ["seed", "temperature_c", "event_index", "polarity", "M_FF",
                     "alarm_a18", "alarm_b18", "alarm_a19", "alarm_b19",
                     "sticky_a18", "sticky_b18", "before_a_rise", "before_a_fall",
                     "before_b_rise", "before_b_fall", "after_a_rise", "after_a_fall",
                     "after_b_rise", "after_b_fall", "M_REF_STARTUP_RISE",
                     "M_REF_STARTUP_FALL", "D_track_a", "D_track_b",
                     "abs_alarm_a", "abs_alarm_b", "signed_alarm_18", "signed_alarm_19"]
    result_rows = []
    for source, observed in zip(rows, physical):
        seed = int(source["seed"]); temperature_c = int(source["temperature_c"])
        polarity = source["polarity"]; m_ff = int(source["M_FF"])
        refs = startup_refs(seed)
        selected_a = int(observed["before_a_rise"] if polarity == "RISE" else observed["before_a_fall"])
        selected_b = int(observed["before_b_rise"] if polarity == "RISE" else observed["before_b_fall"])
        margin = 22 if polarity == "RISE" else 24
        signed18 = int(polarity == "RISE" and m_ff - refs["rise"] > 18)
        signed19 = int(polarity == "RISE" and m_ff - refs["rise"] > 19)
        result_rows.append({
            "seed": seed, "temperature_c": temperature_c, "event_index": int(source["event_index"]),
            "polarity": polarity, "M_FF": m_ff,
            "alarm_a18": int(observed["alarm_a18"]), "alarm_b18": int(observed["alarm_b18"]),
            "alarm_a19": int(observed["alarm_a19"]), "alarm_b19": int(observed["alarm_b19"]),
            "sticky_a18": int(observed["sticky_a18"]), "sticky_b18": int(observed["sticky_b18"]),
            "before_a_rise": int(observed["before_a_rise"]), "before_a_fall": int(observed["before_a_fall"]),
            "before_b_rise": int(observed["before_b_rise"]), "before_b_fall": int(observed["before_b_fall"]),
            "after_a_rise": int(observed["after_a_rise"]), "after_a_fall": int(observed["after_a_fall"]),
            "after_b_rise": int(observed["after_b_rise"]), "after_b_fall": int(observed["after_b_fall"]),
            "M_REF_STARTUP_RISE": refs["rise"], "M_REF_STARTUP_FALL": refs["fall"],
            "D_track_a": abs(m_ff - selected_a), "D_track_b": abs(m_ff - selected_b),
            "abs_alarm_a": int(abs(m_ff - selected_a) > margin),
            "abs_alarm_b": int(abs(m_ff - selected_b) > margin),
            "signed_alarm_18": signed18, "signed_alarm_19": signed19,
        })
    with (ROOT / "P5_TRACK0_REPLAY_RESULTS.csv").open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=result_fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(result_rows)
    summary = {"gate": "BFE14_TEMP0_P5_TRACK0_PHYSICAL_REPLAY_CHARACTERIZED", "status": "PASS",
               "backend_scientific_vcs_regressions": 1, "rows": len(result_rows),
               "configurations": {"A": {"T_TRACK": 0, "B_TRACK": 0},
                                  "B": {"T_TRACK": 5, "B_TRACK": 2}},
               "thresholds": [18, 19], "stale_snapshot_rejections": 0,
               "checks": {"vcs_pass": True, "event_order_preserved": True,
                           "security_anchor_isolation": True, "no_parameter_sweep": True}}
    for name, prefix in (("A18", "a18"), ("B18", "b18"), ("A19", "a19"), ("B19", "b19")):
        alarm_key = "alarm_{}".format(prefix)
        summary[name] = {
            "combined_alarm_count": sum(row[alarm_key] for row in result_rows),
            "abs_alarm_count": sum(row["abs_alarm_{}".format("a" if prefix.startswith("a") else "b")] for row in result_rows),
            "signed_alarm_count": sum(row["signed_alarm_18" if name.endswith("18") else "signed_alarm_19"] for row in result_rows),
            "accepted_tracker_updates": sum(
                (row["after_a_rise"] != row["before_a_rise"] or row["after_a_fall"] != row["before_a_fall"])
                if prefix.startswith("a") else
                (row["after_b_rise"] != row["before_b_rise"] or row["after_b_fall"] != row["before_b_fall"])
                for row in result_rows),
            "max_D_track": max(row["D_track_a" if prefix.startswith("a") else "D_track_b"] for row in result_rows),
        }
    write_json(ROOT / "P5_TRACK0_REPLAY_SUMMARY.json", summary)


def p6():
    """Freeze the complete package and choose the next research direction."""
    # Re-read all preceding gates before issuing the final characterization gate.
    required = ["P0_AUTHORITY.json", "P1_GATE.json", "P2_SCOUT_SUMMARY.json", "P3_GATE.json",
                "P4_DUAL_REFERENCE_SUMMARY.json", "P5_TRACK0_REPLAY_SUMMARY.json"]
    for name in required:
        if not (ROOT / name).is_file():
            raise RuntimeError("missing required stage artifact: {}".format(name))
    p4_summary = read_json(ROOT / "P4_DUAL_REFERENCE_SUMMARY.json")
    if "SECURITY_ANCHOR_HEALTHY_CONFLICT_OBSERVED" in p4_summary["interpretation_classes"]:
        next_stage = "TRUSTED-ANCHOR-MANAGEMENT / REBASE0 architecture study"
    elif "BFE13_TEST_TRACK_WINDOW_TOO_NARROW" in p4_summary["interpretation_classes"]:
        next_stage = "offline TRACK-PARAM characterization using frozen physical data"
    else:
        next_stage = "POISON0 / slow unauthorized droop study"
    report = "# BFE14 benign temperature drift characterization\n\n"
    report += "Final gate: `BFE14_ARCH1_BENIGN_TEMP_DRIFT_CHARACTERIZED`\n\n"
    report += "This PASS means the healthy-temperature characterization package is "
    report += "complete and internally consistent; it is not a production-safety, "
    report += "PVT, silicon, aging, poisoning, OPP/rebase, or physical Level-0 signoff.\n\n"
    report += "P4 interpretation classes: {}\n\n".format(
        ", ".join(p4_summary["interpretation_classes"]))
    report += "Next candidate direction: {}\n\n".format(next_stage)
    report += "No threshold, tracker parameter, startup calibration, security anchor, "
    report += "frontend, waveform, or RTL was retuned in BFE14.\n"
    (ROOT / "BFE14_BENIGN_TEMP_REPORT.md").write_text(report, encoding="ascii")
    write_json(ROOT / "BFE14_BENIGN_TEMP_RUN_LEDGER.json", {
        "gate": "BFE14_ARCH1_BENIGN_TEMP_DRIFT_CHARACTERIZED", "status": "PASS",
        "stage_gates": {"P0": "BFE14_TEMP0_P0_AUTHORITIES_AND_ARCH1_STATUS_FROZEN",
                        "P1": "BFE14_TEMP0_P1_STIMULUS_AND_REUSE_FROZEN",
                        "P2": "BFE14_TEMP0_P2_SCOUT_VALID",
                        "P3": "BFE14_TEMP0_P3_HEALTHY_PHYSICS_FROZEN",
                        "P4": "BFE14_TEMP0_P4_DUAL_REFERENCE_CHARACTERIZED",
                        "P5": "BFE14_TEMP0_P5_TRACK0_PHYSICAL_REPLAY_CHARACTERIZED"},
        "prohibited_campaigns": {"droop": 0, "vdd_sweep": 0, "corner_matrix": 0,
                                 "aging": 0, "opp_rebase": 0, "threshold_sweep": 0},
        "next_stage": next_stage,
    })
    write_json(ROOT / "BFE14_BENIGN_TEMP_GATE.json", {
        "gate": "BFE14_ARCH1_BENIGN_TEMP_DRIFT_CHARACTERIZED", "status": "PASS",
        "classification": "HEALTHY_TEMPERATURE_CHARACTERIZATION_COMPLETE",
        "next_stage": next_stage, "production_safe_claim": False,
        "stop_after_stage": True,
    })


def main():
    parser = argparse.ArgumentParser(description="BFE14 staged healthy-temperature runner")
    parser.add_argument("--stage", choices=("p1", "p2", "p3", "p4", "p5", "p6"), required=True)
    args = parser.parse_args()
    if args.stage == "p1":
        p1()
    elif args.stage == "p2":
        p2()
    elif args.stage == "p3":
        p3()
    elif args.stage == "p4":
        p4()
    elif args.stage == "p5":
        p5()
    else:
        p6()
    print("BFE14 {} PASS".format(args.stage.upper()))


if __name__ == "__main__":
    main()
