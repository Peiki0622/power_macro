#!/usr/bin/env python3
"""Run the bounded B-FE3-P0R L2 phase-representative XA campaign.

Only three new 0.95-to-0.86 V source phases are allowed: early, middle, and
late within the already-frozen transparent interval.  Each physical point has
two inseparable parts: a B-FE2.2C-compatible HSPICE source trace retaining
the 30 loaded XOR waveforms, followed by the existing VCS+PrimeSim XA bridge
to the real safe-domain 0.95 V LATQ bank.  No source wave is synthesized or
filtered in Python; the code only renders existing topology and transports
threshold crossings into the reviewed XA boundary wrapper.
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
sys.path.insert(0, str(FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "l1a_r_vcs_xa"))

import bfe1_frontend  # noqa: E402  # Frozen source waveform conventions and parser.
import bfe2_real_snapshot  # noqa: E402  # Reviewed 30-latch-loaded finite-G source renderer.
import run_bfe2_l1a_r_vcs_xa as bridge  # noqa: E402  # Reviewed 0.95 V LATQ VCS-XA boundary bridge.
import run_dc_sweep  # noqa: E402  # Project-standard HSPICE listing/version checks.


RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe3_p0r_m_phase"
P0_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe3_p0_postprocess_features"
P0_ANALYSIS = P0_ROOT / "BFE3_P0_ANALYSIS.json"
P0_MANIFEST = P0_ROOT / "BFE3_P0_MANIFEST.json"
CELLS = FTC_ROOT / "discovery" / "selected_cells.json"
CONFIG = FTC_ROOT / "ftc_config.json"
SOURCE_SAMPLE_CLOSE_PS = 534.524618567
FIXED_G_CLOSE_PS = 1534.524618567
EXPECTED_RECORD_WIDTH = 124

# These are phase representatives, not a sweep: start at launch, midpoint of
# the 534.5246 ps transparent interval, and a late arrival 34.5 ps before G
# closes.  The existing 75 ps L2 point remains a retained reference only.
PHASE_POINTS = (
    ("EARLY", 0.0),
    ("MIDDLE", 250.0),
    ("LATE", 500.0),
)


def sha256(path: Path) -> str:
    """Hash retained source and generated evidence without loading raw traces at once."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    """Read one object-shaped contract and fail closed on malformed provenance."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def signature(scenario: dict, hspice_version: str) -> dict:
    """Record every source-side parameter that must remain frozen across phase points."""

    cells = load_json(CELLS)
    config = load_json(CONFIG)
    return {
        "topology": "bfe2_2c_30tap_4over0_loaded_xor_source",
        "rvt_prefix": bfe1_frontend.RVT_PREFIX,
        "lvt_prefix": bfe1_frontend.LVT_PREFIX,
        "tap_count": 30,
        "xor_cell": bfe1_frontend.XOR_CELL,
        "source_latch_cell": "LATQ_X0P5M_A9TR40",
        "safe_latch_cell": "LATQ_X0P5M_A9TR40",
        "baseline_v": scenario["baseline_v"],
        "droop_v": scenario["droop_v"],
        "phase_ps": scenario["phase_ps"],
        "source_sample_close_ps": SOURCE_SAMPLE_CLOSE_PS,
        "fixed_safe_g_close_ps": FIXED_G_CLOSE_PS,
        "model_sha256": sha256(Path(config["model_library"])),
        "rvt_cell": cells["delay_rvt"]["cell"],
        "lvt_cell": cells["delay_lvt"]["cell"],
        "hspice_version": hspice_version,
    }


def signature_id(value: dict) -> str:
    """Derive an immutable source identity used to reject accidental overwrite."""

    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def source_scenario(label: str, phase_ps: float) -> dict:
    """Create the only permitted new L2 source condition for one representative phase."""

    return {
        "scenario_id": "BFE3P0R-095-L2-{}".format(label),
        "baseline_v": 0.95,
        "droop_v": 0.86,
        "phase_ps": phase_ps,
        "authority_scenario_key": "BFE3_P0R_representative_phase",
    }


def run_source(label: str, phase_ps: float, hspice: Path, version: str) -> dict:
    """Run one loaded-XOR source trace, or reuse only byte-identified evidence."""

    scenario = source_scenario(label, phase_ps)
    directory = RUN_ROOT / label.lower() / "source_hspice"
    deck_path = directory / "bfe3_p0r_source.sp"
    trace_path = directory / "bfe3_p0r_source.tr0"
    evidence_path = directory / "source_evidence.json"
    sig = signature(scenario, version)
    sig_id = signature_id(sig)
    if directory.exists():
        if not (evidence_path.is_file() and deck_path.is_file() and trace_path.is_file()):
            raise FileExistsError("P0R source directory is incomplete: {}".format(directory))
        evidence = load_json(evidence_path)
        if evidence.get("electrical_signature_id") != sig_id or sha256(deck_path) != evidence.get("deck_sha256") or sha256(trace_path) != evidence.get("tr0_sha256"):
            raise FileExistsError("P0R source directory has a different physical identity: {}".format(directory))
        return {**evidence, "run_disposition": "reused-completed"}
    directory.mkdir(parents=True)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    # This renderer preserves all 30 source-domain LATQ loads and its finite
    # common G close.  Its q outputs are not the B-FE3 decision surface; the
    # trace is retained only to produce loaded XOR/safe_d input to XA.
    deck = bfe2_real_snapshot.render(load_json(CELLS), scenario, SOURCE_SAMPLE_CLOSE_PS)
    bfe2_real_snapshot.validate(deck)
    if "phase_ps" not in sig or sig["phase_ps"] != phase_ps:
        raise AssertionError("phase identity drift")
    deck_path.write_text(deck, encoding="ascii")
    result = subprocess.run([str(hspice), deck_path.name, "-o", "bfe3_p0r_source"], cwd=str(directory), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=600)
    (directory / "hspice_command.log").write_text("command={} {} -o bfe3_p0r_source\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(hspice, deck_path.name, result.returncode, result.stdout, result.stderr), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError("P0R HSPICE source failed for {} phase".format(label))
    run_dc_sweep.validate_listing(directory / "bfe3_p0r_source.lis")
    trace = bfe1_frontend.parse_ascii_tr0(trace_path)
    if trace["record_width"] != EXPECTED_RECORD_WIDTH:
        raise ValueError("P0R source trace does not retain the 124-column contract")
    evidence = {
        "scenario_id": scenario["scenario_id"], "phase_ps": phase_ps, "baseline_v": 0.95, "droop_v": 0.86,
        "source_sample_close_ps": SOURCE_SAMPLE_CLOSE_PS, "electrical_signature": sig, "electrical_signature_id": sig_id,
        "deck_sha256": sha256(deck_path), "tr0_sha256": sha256(trace_path), "record_width": trace["record_width"],
        "record_count": trace["record_count"], "hspice_version": version, "run_disposition": "new",
    }
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence


def prepare_xa(label: str, source: dict) -> dict:
    """Build one VCS-XA real-safe-LATQ case from one completed physical source trace."""

    source_dir = RUN_ROOT / label.lower() / "source_hspice"
    trace_path = source_dir / "bfe3_p0r_source.tr0"
    directory = RUN_ROOT / label.lower() / "vcs_xa"
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    trace = bfe1_frontend.parse_ascii_tr0(trace_path)
    columns = trace["columns"]
    times = columns["time"]
    vdd_sense = columns[bfe1_frontend.label_for("vdd_monitored")]
    schedules, initial_states, initial_values, ledger = {}, {}, {}, {}
    for tap in range(30):
        xor = columns[bfe1_frontend.label_for("xor_{}".format(tap))]
        initial, events = bridge.threshold_schedule(times, xor, vdd_sense)
        schedules[tap], initial_states[tap] = events, initial
        initial_values[tap] = {"xor_v": float(xor[0]), "vdd_sense_v": float(vdd_sense[0]), "threshold_v": 0.5 * float(vdd_sense[0]), "safe_d_v": 0.95 if initial else 0.0}
        ledger["tap_{:02d}".format(tap)] = {"initial": {"logic_state": initial, **initial_values[tap]}, "crossings": [{"time_ps": event[0] * 1.0e12, "logic_state": event[1], "direction": event[2]} for event in events]}
    (directory / "safe_d_crossing_ledger.json").write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    scenario_id = source["scenario_id"]
    (directory / "bfe3_p0r_ams_wrapper.sp").write_text(bridge.render_wrapper(scenario_id, columns, times), encoding="ascii")
    (directory / "tb_bfe2_l1a_r_vcs_xa.sv").write_text(bridge.render_tb(schedules, initial_states, initial_values), encoding="ascii")
    (directory / "xa.cfg").write_text("set_sim_level 7\nset_waveform -format fsdb\n" + "\n".join(["probe_waveform_voltage vdd_sense", "probe_waveform_voltage vdd_safe", "probe_waveform_voltage latch_g_r"] + ["probe_waveform_voltage safe_d_r_{:02d}".format(tap) for tap in range(30)] + ["probe_waveform_voltage q_{:02d}".format(tap) for tap in range(30)]) + "\n", encoding="ascii")
    (directory / "vcsAD.init").write_text("bus_format [%d];\nuse_spice -cell bfe2_l1a_r_ams;\nchoose xa -hspice {} -c {} -o {}/xa;\n".format(directory / "bfe3_p0r_ams.sp", directory / "xa.cfg", directory), encoding="ascii")
    top = bridge.render_top_deck(directory).replace("bfe2_l1a_r_ams_wrapper.sp", "bfe3_p0r_ams_wrapper.sp")
    (directory / "bfe3_p0r_ams.sp").write_text(top, encoding="ascii")
    return {"phase_label": label, "phase_ps": source["phase_ps"], "directory": str(directory), "source_tr0_sha256": source["tr0_sha256"], "safe_d_ledger_sha256": sha256(directory / "safe_d_crossing_ledger.json")}


def main() -> int:
    """Execute the three authorized representative phases, publish manifest, and stop."""

    p0 = load_json(P0_ANALYSIS)
    p0_manifest = load_json(P0_MANIFEST)
    if p0.get("gate") != "BFE3_P0_POSTPROCESS_FEATURES_PROMISING" or p0.get("normal_feature_envelope", {}).get("M") != {"min": 260, "max": 315}:
        raise ValueError("P0R requires the frozen P0 M envelope")
    if p0_manifest.get("tap_count") != 30 or p0_manifest.get("vdd_safe_v") != 0.95:
        raise ValueError("P0 physical contract is not frozen")
    config = load_json(CONFIG)
    hspice = Path(config["hspice"])
    version = run_dc_sweep.hspice_version(hspice)
    if config["expected_hspice_version"] not in version:
        raise RuntimeError("unexpected HSPICE version")
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    sources = [run_source(label, phase, hspice, version) for label, phase in PHASE_POINTS]
    xa_metadata = [prepare_xa(label, source) for (label, _phase), source in zip(PHASE_POINTS, sources)]
    xa_results = [bridge.run_scenario(meta) for meta in xa_metadata]
    manifest = {
        "schema_version": 1, "stage": "B-FE3-P0R", "verification_mode": "representative-phase HSPICE source + VCS W-2024.09 / PrimeSim XA W-2024.09 real LATQ capture",
        "phase_selection": [{"label": label, "phase_ps": phase, "role": {"EARLY": "launch-aligned early", "MIDDLE": "transparent-window middle", "LATE": "pre-close late"}[label]} for label, phase in PHASE_POINTS],
        "dense_phase_scan": False, "new_phase_points": len(PHASE_POINTS), "new_hspice_source_scenarios": sum(item["run_disposition"] == "new" for item in sources), "new_vcs_xa_scenarios": len(PHASE_POINTS),
        "frozen_normal_m_envelope": {"min": 260, "max": 315}, "fixed_g_close_ps": FIXED_G_CLOSE_PS, "source_sample_close_ps": SOURCE_SAMPLE_CLOSE_PS,
        "sensing_geometry": {"tap_count": 30, "rvt_prefix": 4, "lvt_prefix": 0, "xor_cell": bfe1_frontend.XOR_CELL}, "latch_cell": "LATQ_X0P5M_A9TR40", "vdd_safe_v": 0.95,
        "safe_d_rule": "xor > 0.5*VDD_SENSE ? 0.95 V : 0 V", "decision_feature": "M=sum(i*q[i]), i=0..29",
        "forbidden": ["RTL", "self_calibration", "N_or_T_decision", "lookup_table", "filter", "bubble_repair", "multi_feature_fusion"],
        "p0_analysis_sha256": sha256(P0_ANALYSIS), "p0_manifest_sha256": sha256(P0_MANIFEST), "source_hspice": sources, "xa_scenarios": xa_results,
        "container_tools": {"vcs": os.environ.get("VCS_HOME", "unknown"), "xa": os.environ.get("PRIMESIM_XA_HOME", os.environ.get("XA_HOME", "unknown"))}, "stop_after_stage": True, "next_stage_authorized": False,
    }
    path = ROOT / "BFE3_P0R_MANIFEST.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if all(item.get("compile_returncode") == 0 and item.get("run_returncode") == 0 and item.get("cosim_marker") and item.get("xa_version_marker") for item in xa_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
