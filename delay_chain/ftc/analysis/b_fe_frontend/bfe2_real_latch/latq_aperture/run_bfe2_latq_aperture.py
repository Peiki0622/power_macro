#!/usr/bin/env python3
"""Run the bounded tap29 D-versus-G falling capture-aperture experiment.

The source is the frozen 0.95 V normal B-FE2.2C waveform.  Only the falling
gate time is changed, and it is represented by ``delta_t_ps`` relative to the
frozen tap29 ``safe_d`` rising crossing.  The generated XA wrapper is the
existing real ``LATQ_X0P5M_A9TR40`` safe-domain wrapper; no HSPICE scenario,
sensing geometry, interface, or circuit control is changed here.
"""

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "l1a_vcs_xa_1p10"))
import run_bfe2_l1a_vcs_xa as previous  # noqa: E402

FTC_ROOT = previous.FTC_ROOT
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "latq_aperture"
OUT_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "latq_aperture"
SOURCE_SCENARIO = "BFE2L-095-N"
D_CROSSING_PS = 1529.871837153
TAP_COUNT = 30
POINTS = (
    ("CENTER", 4.652781414, "known safe-reject anchor"),
    ("MID", 15.0, "representative aperture point"),
    ("RIGHT", 23.196735917, "known failure anchor"),
    ("LATE_CAPTURE", 45.0, "late safe-capture anchor"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare(point_name: str, delta_t_ps: float, note: str, entry: dict) -> dict:
    close_ps = D_CROSSING_PS + delta_t_ps
    directory = RUN_ROOT / point_name.lower()
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    trace = previous.bfe1_frontend.parse_ascii_tr0(previous.source_path(SOURCE_SCENARIO))
    columns = trace["columns"]
    times = columns["time"]
    schedules = {}
    ledger = {}
    for tap in range(TAP_COUNT):
        events = previous.crossing_schedule(
            times,
            columns[previous.bfe1_frontend.label_for("xor_{}".format(tap))],
            columns[previous.bfe1_frontend.label_for("vdd_monitored")],
        )
        schedules[tap] = events
        ledger["tap_{:02d}".format(tap)] = {
            "crossings": [{"time_ps": t * 1.0e12, "logic_state": state,
                           "direction": "rise" if state else "fall"} for t, state in events]
        }
    (directory / "safe_d_crossing_ledger.json").write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    wrapper = previous.render_wrapper("LATQ-APERTURE-{}".format(point_name), columns, times)
    # The inherited L1A runner targets its earlier 1.10 V safe-domain study.
    # This stage has an explicit 0.95 V safe rail, so normalize only the
    # generated bridge constants while retaining the same real-cell topology.
    wrapper = wrapper.replace("latch PD_SAFE is 1.10 V", "latch PD_SAFE is 0.95 V")
    wrapper = wrapper.replace("1.100000000000e+00", "9.500000000000e-01")
    wrapper = wrapper.replace("8.636363636364e-01", "1.000000000000e+00")
    (directory / "bfe2_latq_aperture_ams_wrapper.sp").write_text(wrapper, encoding="ascii")
    # The inherited wrapper/testbench names are local to each task directory;
    # keeping them unchanged preserves the already validated XA bridge path.
    tb = previous.render_tb(schedules, close_ps)
    # The inherited renderer's convenience initializer mirrors the first
    # event state.  For an aperture measurement every safe_d starts at the
    # frozen old value 0; the first scheduled rise must be the first change.
    tb_lines = tb.splitlines()
    for tap in range(TAP_COUNT):
        marker = "// Tap {:02d}:".format(tap)
        start = next(index for index, line in enumerate(tb_lines) if marker in line)
        init_line = next(index for index in range(start, len(tb_lines)) if tb_lines[index].strip() == "initial begin")
        value_line = init_line + 1
        if tb_lines[value_line].strip().startswith("safe_d_{} =".format(tap)):
            tb_lines[value_line] = "        safe_d_{} = 1'b0;".format(tap)
    (directory / "tb_bfe2_l1a_vcs_xa.sv").write_text("\n".join(tb_lines) + "\n", encoding="ascii")
    (directory / "xa.cfg").write_text(
        "set_sim_level 7\nset_waveform -format fsdb\n" + "\n".join(
            ["probe_waveform_voltage vdd_sense", "probe_waveform_voltage vdd_safe", "probe_waveform_voltage latch_g_r"]
            + ["probe_waveform_voltage safe_d_r_{:02d}".format(tap) for tap in range(30)]
            + ["probe_waveform_voltage q_{:02d}".format(tap) for tap in range(30)]
        ) + "\n", encoding="ascii"
    )
    (directory / "vcsAD.init").write_text(
        "bus_format [%d];\nuse_spice -cell bfe2_l1a_ams;\nchoose xa -hspice {} -c {} -o {}/xa;\n".format(
            directory / "bfe2_latq_aperture_ams.sp", directory / "xa.cfg", directory
        ), encoding="ascii"
    )
    # render_top_deck includes the old wrapper filename, so replace only that
    # local include while retaining its audited model/CDL setup verbatim.
    deck = previous.render_top_deck("LATQ-APERTURE-{}".format(point_name), directory)
    deck = deck.replace("bfe2_l1a_ams_wrapper.sp", "bfe2_latq_aperture_ams_wrapper.sp")
    (directory / "bfe2_latq_aperture_ams.sp").write_text(deck, encoding="ascii")
    return {
        "point": point_name,
        "note": note,
        "delta_t_ps": delta_t_ps,
        "d_crossing_ps": D_CROSSING_PS,
        "g_close_ps": close_ps,
        "directory": str(directory),
        "safe_d_ledger_sha256": sha256(directory / "safe_d_crossing_ledger.json"),
        "source_trace_sha256": sha256(previous.source_path(SOURCE_SCENARIO)),
        "source_deck_sha256": sha256(previous.source_deck_path(SOURCE_SCENARIO)),
        "source_manifest_entry": entry["scenario_id"],
    }


def main() -> int:
    entries = previous.validate_inputs()
    entry = next(item for item in entries if item["scenario_id"] == SOURCE_SCENARIO)
    trace = previous.bfe1_frontend.parse_ascii_tr0(previous.source_path(SOURCE_SCENARIO))
    # The user-frozen crossing is a contract, not a value inferred from the
    # D->Q delay or from any direction-global fallback.
    schedules = previous.crossing_schedule(
        trace["columns"]["time"],
        trace["columns"][previous.bfe1_frontend.label_for("xor_29")],
        trace["columns"][previous.bfe1_frontend.label_for("vdd_monitored")],
    )
    tap29_rises = [t * 1.0e12 for t, state in schedules if state == 1]
    if not tap29_rises or abs(tap29_rises[0] - D_CROSSING_PS) > 1.0e-6:
        raise ValueError("tap29 safe_d crossing does not match frozen aperture contract")
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    results = []
    for point_name, delta_t_ps, note in POINTS:
        meta = prepare(point_name, delta_t_ps, note, entry)
        results.append(previous.run_scenario(meta))
    manifest = {
        "schema_version": 1,
        "stage": "B-FE2-LATQ-APERTURE",
        "verification_mode": "VCS W-2024.09 + PrimeSim XA W-2024.09 real LATQ aperture co-simulation",
        "source_scenario": SOURCE_SCENARIO,
        "source_manifest_sha256": sha256(previous.SOURCE_MANIFEST),
        "source_trace_sha256": sha256(previous.source_path(SOURCE_SCENARIO)),
        "source_deck_sha256": sha256(previous.source_deck_path(SOURCE_SCENARIO)),
        "latch_cell": "LATQ_X0P5M_A9TR40",
        "vdd_sense_source_v": 0.95,
        "vdd_safe_v": 0.95,
        "safe_d_rule": "xor > 0.5*VDD_SENSE ? 0.95 V : 0 V",
        "tap_count": 30,
        "sensing_geometry": {"rvt_prefix": 4, "lvt_prefix": 0, "taps": 30, "xor_cell": "XOR2_X0P5M_A9TL40"},
        "tap_under_test": 29,
        "frozen_d_crossing_ps": D_CROSSING_PS,
        "delta_t_definition": "G_close_ps - D_crossing_ps",
        "close_edge": "single 1 ps falling G edge",
        "points": results,
        "new_hspice_scenarios": 0,
        "dense_sweep": False,
        "forbidden_semantics": ["D_to_Q_max_delay_window", "direction_global_fallback", "self_calibration", "M/F", "FSM", "detection"],
        "container_tools": {"vcs": os.environ.get("VCS_HOME", "unknown"), "xa": os.environ.get("PRIMESIM_XA_HOME", os.environ.get("XA_HOME", "unknown"))},
        "stop_after_stage": True,
        "next_stage_authorized": False,
    }
    path = OUT_ROOT / "BFE2_LATQ_APERTURE_MANIFEST.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if all(item.get("compile_returncode") == 0 and item.get("run_returncode") == 0 and item.get("cosim_marker") and item.get("xa_version_marker") for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
