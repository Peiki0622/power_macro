#!/usr/bin/env python3
"""Run bounded, evidence-preserving FTC physical characterizations.

The command intentionally exposes only the stages of the approved FTC plan.
Every analog scenario is isolated below one caller-chosen run directory, so
generated decks, listings, measurements, and solver state cannot escape into
the workspace.  Compact CSV/JSON evidence is written at the run root; the
repository ignore policy retains only those files for review.
"""

import argparse
import csv
import json
import shutil
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


FTC_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
PHASE1_SCRIPTS = WORKSPACE_ROOT / "power_macro/delay_chain/phase1/scripts"
if str(PHASE1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PHASE1_SCRIPTS))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import ftc_analysis  # noqa: E402  # Pure FTC word/run metrics.
import generate_ftc_deck  # noqa: E402  # The one reviewed deck renderer.
import run_dc_sweep  # noqa: E402  # Existing HSPICE version/listing/MEAS parser.


def load_json(path: Path) -> Dict[str, Any]:
    """Read an object-shaped JSON input and fail before creating run outputs."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def scenario_name(label: str, vdd_v: float, index: int) -> str:
    """Build a stable unique scenario directory without rounding voltage data."""

    return "{:03d}_{}_v{:0.12f}".format(index, label, float(vdd_v)).replace(".", "p")


def prepare_output(path: Path, config: Dict[str, Any], cells: Dict[str, Any]) -> Path:
    """Validate all immutable inputs before creating one task-owned run root."""

    if path.exists():
        raise ValueError("refusing to overwrite existing FTC run directory: {}".format(path))
    hspice = run_dc_sweep.require_regular_file(Path(config["hspice"]), "HSPICE", executable=True)
    version = run_dc_sweep.hspice_version(hspice)
    if str(config["expected_hspice_version"]) not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    for source in list(cells["source_files"].values()) + [config["model_library"]]:
        run_dc_sweep.require_regular_file(Path(source), "FTC source collateral")
    compatibility = FTC_ROOT / "spice/empty_subckt.sp_cal"
    run_dc_sweep.require_regular_file(compatibility, "FTC LVT compatibility include")
    path.mkdir(parents=True)
    (path / "manifest.json").write_text(
        json.dumps({"study": config["study_name"], "hspice_version": version, "config": config, "selected_cells": cells}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return hspice


def run_scenario(hspice: Path, output_dir: Path, config: Dict[str, Any], cells: Dict[str, Any],
                 index: int, label: str, vdd_v: float, mode: str, initial_rvt: int,
                 initial_lvt: int, capture_phase_s: float,
                 glitch: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Generate, execute, validate, and retain one physical FTC scenario.

    The returned record is purely compact measurement data.  Full HSPICE files
    remain under ``scenarios/`` where the task-specific ignore rule prevents
    them from being accidentally committed or mixed with source files.
    """

    scenario_dir = output_dir / "scenarios" / scenario_name(label, vdd_v, index)
    scenario_dir.mkdir(parents=True, exist_ok=False)
    # The installed LVT CDL refers to this filename relatively.  Copying the
    # documented no-op include into the scenario is the smallest compatible
    # fix and never writes to the immutable vendor directory.
    shutil.copyfile(FTC_ROOT / "spice/empty_subckt.sp_cal", scenario_dir / "empty_subckt.sp_cal")
    deck_path = scenario_dir / "ftc.sp"
    generate_ftc_deck.write_deck(
        deck_path, config=config, cells=cells, vdd_v=float(vdd_v), mode=mode,
        initial_rvt_stages=int(initial_rvt), initial_lvt_stages=int(initial_lvt),
        capture_phase_s=float(capture_phase_s), glitch=glitch,
    )
    result = subprocess.run(
        [str(hspice), deck_path.name, "-o", "ftc"], cwd=str(scenario_dir),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
        check=False, timeout=300,
    )
    (scenario_dir / "hspice_command.log").write_text(
        "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            " ".join([str(hspice), deck_path.name, "-o", "ftc"]), result.returncode, result.stdout, result.stderr
        ), encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, scenario_dir))
    run_dc_sweep.validate_listing(scenario_dir / "ftc.lis")
    measurement_path = run_dc_sweep.find_measurement_file(scenario_dir, "ftc")
    values = run_dc_sweep.parse_measurements(measurement_path)
    stages = int(config["observable_stages"])
    rvt = [values.get("rvt_{:02d}_cross".format(index)) for index in range(stages)]
    lvt = [values.get("lvt_{:02d}_cross".format(index)) for index in range(stages)]
    if any(value is None for value in rvt + lvt):
        raise ValueError("FTC delay line has a missing observable crossing: {}".format(scenario_dir))
    record: Dict[str, Any] = {
        "scenario": str(scenario_dir.relative_to(output_dir)), "mode": mode, "vdd_v": float(vdd_v),
        "initial_rvt_stages": int(initial_rvt), "initial_lvt_stages": int(initial_lvt),
        "capture_phase_s": float(capture_phase_s), "sample_time_s": float(config["launch_time_s"]) + float(capture_phase_s),
        "rvt_crossings_s": [float(value) for value in rvt], "lvt_crossings_s": [float(value) for value in lvt],
        "vdd_a_min_v": values.get("vdd_a_min_v"),
    }
    if mode in ("xor", "capture"):
        xor_levels = [values.get("xor_{:02d}_level".format(index)) for index in range(stages)]
        if any(value is None for value in xor_levels):
            raise ValueError("FTC XOR measurement is incomplete: {}".format(scenario_dir))
        record["raw_xor_word"] = ftc_analysis.word(ftc_analysis.bits_from_levels(xor_levels, float(vdd_v) / 2.0))
    if mode == "capture":
        latch_levels = [values.get("latch_{:02d}_level".format(index)) for index in range(stages)]
        ff_levels = [values.get("ff_{:02d}_level".format(index)) for index in range(stages)]
        if any(value is None for value in latch_levels + ff_levels):
            raise ValueError("FTC capture measurement is incomplete: {}".format(scenario_dir))
        record["latch_word"] = ftc_analysis.word(ftc_analysis.bits_from_levels(latch_levels, float(vdd_v) / 2.0))
        record["captured_xor_word"] = ftc_analysis.word(ftc_analysis.bits_from_levels(ff_levels, float(vdd_v) / 2.0))
    return record


def mechanism_metrics(record: Dict[str, Any]) -> Dict[str, Any]:
    """Derive the plan's mechanism-only wavefront/XOR evidence from crossings."""

    rvt_bits = ftc_analysis.bits_from_crossings(record["rvt_crossings_s"], record["sample_time_s"])
    lvt_bits = ftc_analysis.bits_from_crossings(record["lvt_crossings_s"], record["sample_time_s"])
    xor_bits = [left ^ right for left, right in zip(rvt_bits, lvt_bits)]
    result = dict(record)
    result.update({
        "rvt_wavefront_word": ftc_analysis.word(rvt_bits), "lvt_wavefront_word": ftc_analysis.word(lvt_bits),
        "raw_xor_word": ftc_analysis.word(xor_bits),
    })
    result.update(ftc_analysis.longest_one_run(xor_bits))
    return result


def capture_metrics(record: Dict[str, Any]) -> Dict[str, Any]:
    """Decode an observed real capture while retaining raw and repaired evidence."""

    raw_bits = [int(bit) for bit in record["captured_xor_word"]]
    repaired = ftc_analysis.majority_repair(raw_bits)
    result = dict(record)
    result["corrected_xor_word"] = ftc_analysis.word(repaired)
    result["raw_bubble_count"] = ftc_analysis.bubble_count(raw_bits)
    result.update(ftc_analysis.longest_one_run(repaired))
    return result


def compact_row(record: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize timing arrays into CSV fields while preserving all 30 samples."""

    row = dict(record)
    for key in ("rvt_crossings_s", "lvt_crossings_s"):
        if key in row:
            row[key] = json.dumps(row[key], separators=(",", ":"))
    return row


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    """Write a deterministic compact CSV whose columns are the union of rows."""

    if not rows:
        raise ValueError("refusing to write empty FTC CSV: {}".format(path))
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(compact_row(row))


def write_report(path: Path, title: str, summary: Dict[str, Any], rows: Sequence[Dict[str, Any]]) -> None:
    """Publish a small review report without duplicating ignored raw artifacts."""

    lines = ["# {}".format(title), "", "## Summary", ""]
    for key, value in summary.items():
        lines.append("- `{}`: `{}`".format(key, value))
    lines.extend(["", "## Measured Points", "", "| VDD (V) | Raw XOR | Captured XOR | Start | End | Length | Valid |", "|---:|---|---|---:|---:|---:|---:|"])
    for row in rows:
        lines.append("| {:.3f} | `{}` | `{}` | {} | {} | {} | {} |".format(
            float(row["vdd_v"]), row.get("raw_xor_word", ""), row.get("captured_xor_word", ""),
            row.get("start_index", ""), row.get("end_index", ""), row.get("one_run_length", ""), row.get("valid", ""),
        ))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def select_nominal(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Select the simplest internal, nonempty mechanism window deterministically."""

    usable = [row for row in rows if row["valid"] and not row["touches_left_boundary"] and not row["touches_right_boundary"]]
    if not usable:
        raise RuntimeError("no non-boundary FTC XOR window was found in the bounded nominal search")
    # Prefer the largest observable window, then the least added initial delay,
    # then the earliest sample phase for an unambiguous repeatable selection.
    selected = sorted(usable, key=lambda row: (-int(row["one_run_length"]), int(row["initial_rvt_stages"]) + int(row["initial_lvt_stages"]), float(row["capture_phase_s"])))[0]
    increments = [
        later - earlier for earlier, later in zip(selected["rvt_crossings_s"], selected["rvt_crossings_s"][1:]) if later > earlier
    ]
    phase_step = statistics.median(increments) if increments else 1.0e-11
    result = dict(selected)
    result["capture_phase_step_s"] = float(phase_step)
    return result


def run_mechanism_search(args: argparse.Namespace, config: Dict[str, Any], cells: Dict[str, Any]) -> None:
    """Perform only the approved bounded physical search at nominal VDD."""

    out = args.output_dir.resolve()
    hspice = prepare_output(out, config, cells)
    rows: List[Dict[str, Any]] = []
    index = 0
    search = config["nominal_search"]
    for initial_rvt in search["initial_rvt_stages"]:
        for initial_lvt in search["initial_lvt_stages"]:
            for phase in search["capture_phase_s"]:
                raw = run_scenario(hspice, out, config, cells, index, "nominal", config["nominal_vdd_v"], "mechanism", initial_rvt, initial_lvt, phase)
                rows.append(mechanism_metrics(raw))
                index += 1
    selection = select_nominal(rows)
    write_csv(out / "search.csv", rows)
    (out / "selection.json").write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(FTC_ROOT / "reports/MECHANISM_NOMINAL.md", "FTC Nominal Mechanism", {"selected_initial_rvt": selection["initial_rvt_stages"], "selected_initial_lvt": selection["initial_lvt_stages"], "selected_capture_phase_s": selection["capture_phase_s"], "selected_raw_xor": selection["raw_xor_word"]}, [selection])


def read_selection(name: str) -> Dict[str, Any]:
    """Load a prior compact FTC selection without rerunning its physical search."""

    path = FTC_ROOT / "runs" / name / "selection.json"
    if not path.is_file():
        raise ValueError("required FTC selection is unavailable: {}".format(path))
    return load_json(path)


def selected_operating_point(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return the one physically validated FTC setting used after Step 8.

    Early mechanism and nominal-capture selections are intentionally retained
    as characterization evidence, but they are not final design constants.
    This explicit object prevents later static, phase, and glitch studies from
    accidentally reverting to a preliminary capture phase.
    """

    point = config.get("selected_operating_point")
    required = ("initial_rvt_stages", "initial_lvt_stages", "capture_phase_s", "ff_capture_delay_s", "capture_phase_step_s")
    if not isinstance(point, dict) or any(key not in point for key in required):
        raise ValueError("FTC configuration lacks a complete selected_operating_point")
    if float(point["capture_phase_s"]) <= 0.0 or float(point["capture_phase_step_s"]) <= 0.0:
        raise ValueError("FTC selected capture phase and phase step must be positive")
    return point


def run_coarse(args: argparse.Namespace, config: Dict[str, Any], cells: Dict[str, Any]) -> None:
    """Run the fixed nine-point mechanism or integrated capture characterization."""

    selection = read_selection("capture_nominal" if args.mode == "capture" else "mechanism_nominal_search")
    # A coarse-window retune is permitted only after the fixed nominal search
    # has supplied real crossings.  These explicit optional overrides retain
    # that selection unchanged while making the retried nine-point evidence
    # self-describing instead of silently mutating its original JSON record.
    initial_rvt = int(selection["initial_rvt_stages"] if args.initial_rvt_stages is None else args.initial_rvt_stages)
    initial_lvt = int(selection["initial_lvt_stages"] if args.initial_lvt_stages is None else args.initial_lvt_stages)
    phase = float(selection["capture_phase_s"] if args.capture_phase_s is None else args.capture_phase_s)
    out = args.output_dir.resolve()
    # A coarse HSPICE batch is deliberately resumable only when the caller
    # explicitly requests it and the prior manifest proves the same immutable
    # configuration/cell selection.  This retains finished physical evidence
    # after an execution interruption without silently mixing candidates.
    if args.resume:
        manifest_path = out / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError("cannot resume FTC run without manifest: {}".format(out))
        manifest = load_json(manifest_path)
        if manifest.get("config") != config or manifest.get("selected_cells") != cells:
            raise ValueError("cannot resume FTC run with changed configuration or selected cells: {}".format(out))
        hspice = run_dc_sweep.require_regular_file(Path(config["hspice"]), "HSPICE", executable=True)
    else:
        hspice = prepare_output(out, config, cells)
    rows: List[Dict[str, Any]] = []
    for index, voltage in enumerate(config["coarse_vdd_v"]):
        scenario_dir = out / "scenarios" / scenario_name("coarse", voltage, index)
        # A process may create the scenario directory before HSPICE writes its
        # measurement CSV.  Reuse only a genuinely completed scenario; an
        # empty/interrupted directory is regenerated by the normal runner.
        if args.resume and (scenario_dir / "ftc.mt0.csv").is_file():
            measurement_path = run_dc_sweep.find_measurement_file(scenario_dir, "ftc")
            values = run_dc_sweep.parse_measurements(measurement_path)
            stages = int(config["observable_stages"])
            rvt = [values.get("rvt_{:02d}_cross".format(tap)) for tap in range(stages)]
            lvt = [values.get("lvt_{:02d}_cross".format(tap)) for tap in range(stages)]
            xor = [values.get("xor_{:02d}_level".format(tap)) for tap in range(stages)]
            latch = [values.get("latch_{:02d}_level".format(tap)) for tap in range(stages)]
            ff = [values.get("ff_{:02d}_level".format(tap)) for tap in range(stages)]
            if any(value is None for value in rvt + lvt + xor + latch + ff):
                raise ValueError("cannot resume incomplete FTC measurements: {}".format(scenario_dir))
            record = {
                "scenario": str(scenario_dir.relative_to(out)), "mode": args.mode, "vdd_v": float(voltage),
                "initial_rvt_stages": initial_rvt, "initial_lvt_stages": initial_lvt,
                "capture_phase_s": phase, "sample_time_s": float(config["launch_time_s"]) + phase,
                "rvt_crossings_s": [float(value) for value in rvt], "lvt_crossings_s": [float(value) for value in lvt],
                "vdd_a_min_v": values.get("vdd_a_min_v"),
                "raw_xor_word": ftc_analysis.word(ftc_analysis.bits_from_levels(xor, float(voltage) / 2.0)),
                "latch_word": ftc_analysis.word(ftc_analysis.bits_from_levels(latch, float(voltage) / 2.0)),
                "captured_xor_word": ftc_analysis.word(ftc_analysis.bits_from_levels(ff, float(voltage) / 2.0)),
            }
        else:
            record = run_scenario(hspice, out, config, cells, index, "coarse", voltage, args.mode, initial_rvt, initial_lvt, phase)
        rows.append(capture_metrics(record) if args.mode == "capture" else mechanism_metrics(record))
    write_csv(out / "voltage_xor.csv", rows)
    states = sorted({(row["start_index"], row["end_index"]) for row in rows if row["valid"]})
    summary = {"mode": args.mode, "scenario_count": len(rows), "initial_rvt_stages": initial_rvt, "initial_lvt_stages": initial_lvt, "capture_phase_s": phase, "distinct_start_end_states": len(states), "nonconstant_response": len(states) > 1, "valid_points": sum(int(row["valid"]) for row in rows)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(FTC_ROOT / "reports/{}.md".format("INTEGRATED_COARSE" if args.mode == "capture" else "MECHANISM_COARSE"), "FTC {} Coarse Sweep".format(args.mode), summary, rows)


def run_xor_loading(args: argparse.Namespace, config: Dict[str, Any], cells: Dict[str, Any]) -> None:
    """Compare nominal bare delay lines against the physically loaded XOR bank.

    The compact result intentionally retains enough timing detail to audit the
    observer-loading interface without committing raw HSPICE listings: the
    first, nominal-window center, and final observable taps expose localized
    loading, while the full same-index RVT-minus-LVT profile preserves the
    physical separation that creates the FTC XOR window.
    """

    selection = read_selection("mechanism_nominal_search")
    out = args.output_dir.resolve()
    hspice = prepare_output(out, config, cells)
    base = mechanism_metrics(run_scenario(hspice, out, config, cells, 0, "bare", config["nominal_vdd_v"], "mechanism", selection["initial_rvt_stages"], selection["initial_lvt_stages"], selection["capture_phase_s"]))
    loaded = run_scenario(hspice, out, config, cells, 1, "xor", config["nominal_vdd_v"], "xor", selection["initial_rvt_stages"], selection["initial_lvt_stages"], selection["capture_phase_s"])
    loaded.update(ftc_analysis.longest_one_run([int(bit) for bit in loaded["raw_xor_word"]]))
    # These fixed physical locations bound the line and sample its interior.
    # The center index is derived from the selected bare XOR window rather
    # than a magic tap number, so the evidence remains meaningful if the
    # bounded nominal search selects another internal window in a future run.
    representative_indices = sorted({0, int(base["start_index"] + base["end_index"]) // 2, int(config["observable_stages"]) - 1})

    def path_timing_evidence(record: Dict[str, Any]) -> Dict[str, Any]:
        """Return serializable same-index timing evidence for one line state."""

        separation_s = [float(rvt) - float(lvt) for rvt, lvt in zip(record["rvt_crossings_s"], record["lvt_crossings_s"])]
        representatives = []
        for tap_index in representative_indices:
            representatives.append({
                "tap_index": tap_index,
                "rvt_cross_s": float(record["rvt_crossings_s"][tap_index]),
                "lvt_cross_s": float(record["lvt_crossings_s"][tap_index]),
                "rvt_minus_lvt_s": separation_s[tap_index],
            })
        return {"representative_taps": representatives, "rvt_minus_lvt_profile_s": separation_s}

    summary = {
        "bare_final_rvt_cross_s": base["rvt_crossings_s"][-1], "bare_final_lvt_cross_s": base["lvt_crossings_s"][-1],
        "xor_final_rvt_cross_s": loaded["rvt_crossings_s"][-1], "xor_final_lvt_cross_s": loaded["lvt_crossings_s"][-1],
        "bare_raw_xor_word": base["raw_xor_word"], "real_xor_word": loaded["raw_xor_word"], "real_xor_valid": loaded["valid"],
        "real_xor_start_index": loaded["start_index"], "real_xor_end_index": loaded["end_index"],
        "real_xor_one_run_length": loaded["one_run_length"],
        "bare": path_timing_evidence(base), "xor_loaded": path_timing_evidence(loaded),
    }
    (out / "loading_comparison.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(
        FTC_ROOT / "reports/XOR_LOADING.md", "FTC Real XOR Loading",
        {
            "bare_raw_xor_word": base["raw_xor_word"],
            "real_xor_word": loaded["raw_xor_word"],
            "real_xor_start_end": "{}-{}".format(loaded["start_index"], loaded["end_index"]),
            "real_xor_one_run_length": loaded["one_run_length"],
            "real_xor_valid": loaded["valid"],
        },
        [loaded],
    )


def run_capture_phase(args: argparse.Namespace, config: Dict[str, Any], cells: Dict[str, Any]) -> None:
    """Sweep a measured-delay-derived local capture neighborhood, not a generic grid."""

    mechanism = read_selection("mechanism_nominal_search")
    step = float(mechanism["capture_phase_step_s"])
    phases = [float(mechanism["capture_phase_s"]) + multiplier * step for multiplier in (-2, -1, 0, 1, 2)]
    out = args.output_dir.resolve()
    hspice = prepare_output(out, config, cells)
    rows = [capture_metrics(run_scenario(hspice, out, config, cells, index, "phase", config["nominal_vdd_v"], "capture", mechanism["initial_rvt_stages"], mechanism["initial_lvt_stages"], phase)) for index, phase in enumerate(phases)]
    valid = [row for row in rows if row["valid"] and not row["touches_left_boundary"] and not row["touches_right_boundary"]]
    if not valid:
        raise RuntimeError("no stable nonendpoint capture phase was found")
    selection = sorted(valid, key=lambda row: (int(row["raw_bubble_count"]), -int(row["one_run_length"]), abs(float(row["capture_phase_s"]) - float(mechanism["capture_phase_s"]))))[0]
    selection["capture_phase_step_s"] = step
    write_csv(out / "capture_phase.csv", rows)
    (out / "selection.json").write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_report(FTC_ROOT / "reports/CAPTURE_NOMINAL.md", "FTC Nominal Capture", {"selected_capture_phase_s": selection["capture_phase_s"], "phase_step_s": step, "captured_xor_word": selection["captured_xor_word"]}, rows)


def run_fine(args: argparse.Namespace, config: Dict[str, Any], cells: Dict[str, Any]) -> None:
    """Characterize the integrated selected sensor on the initial 10 mV grid."""

    selection = selected_operating_point(config)
    out = args.output_dir.resolve()
    hspice = prepare_output(out, config, cells)
    voltages: List[float] = []
    value = float(config["nominal_vdd_v"])
    while value >= float(config["minimum_vdd_v"]) - 1.0e-12:
        voltages.append(round(value, 12))
        value -= float(config["fine_static_step_v"])
    rows = [capture_metrics(run_scenario(hspice, out, config, cells, index, "fine", voltage, "capture", selection["initial_rvt_stages"], selection["initial_lvt_stages"], selection["capture_phase_s"])) for index, voltage in enumerate(voltages)]
    write_csv(out / "static_transfer.csv", rows)
    states = sorted({(row["start_index"], row["end_index"]) for row in rows if row["valid"]})
    summary = {"scenario_count": len(rows), "distinct_start_end_states": len(states), "states": states, "position_sum_values": sorted({row["start_index"] + row["end_index"] for row in rows if row["valid"]}), "valid_points": sum(int(row["valid"]) for row in rows), "capture_phase_s": selection["capture_phase_s"]}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_phase_sensitivity(args: argparse.Namespace, config: Dict[str, Any], cells: Dict[str, Any]) -> None:
    """Measure the selected capture's phase dependence at three planned voltages."""

    selection = selected_operating_point(config)
    step = float(selection["capture_phase_step_s"])
    out = args.output_dir.resolve()
    hspice = prepare_output(out, config, cells)
    rows: List[Dict[str, Any]] = []
    index = 0
    for voltage in (1.1, 0.9, float(config["minimum_vdd_v"])):
        for multiplier in (-1, 0, 1):
            row = capture_metrics(run_scenario(hspice, out, config, cells, index, "phase", voltage, "capture", selection["initial_rvt_stages"], selection["initial_lvt_stages"], float(selection["capture_phase_s"]) + multiplier * step))
            row["phase_offset_s"] = multiplier * step
            rows.append(row)
            index += 1
    write_csv(out / "phase_sensitivity.csv", rows)
    movement = {}
    for voltage in (1.1, 0.9, float(config["minimum_vdd_v"])):
        group = [row for row in rows if float(row["vdd_v"]) == voltage and row["valid"]]
        movement[str(voltage)] = {
            "max_start_movement": max(row["start_index"] for row in group) - min(row["start_index"] for row in group),
            "max_end_movement": max(row["end_index"] for row in group) - min(row["end_index"] for row in group),
            "max_length_movement": max(row["one_run_length"] for row in group) - min(row["one_run_length"] for row in group),
        }
    (out / "summary.json").write_text(json.dumps({"capture_phase_s": selection["capture_phase_s"], "phase_step_s": step, "movement": movement}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_glitch(args: argparse.Namespace, config: Dict[str, Any], cells: Dict[str, Any]) -> None:
    """Run nine representative voltage-glitch cases without Cartesian expansion."""

    selection = selected_operating_point(config)
    close = float(config["launch_time_s"]) + float(selection["capture_phase_s"])
    delta = float(selection["capture_phase_step_s"])
    out = args.output_dir.resolve()
    hspice = prepare_output(out, config, cells)
    rows: List[Dict[str, Any]] = []
    index = 0
    for case in config["glitch_cases"]:
        width = float(case["width_s"])
        starts = {"before": max(1.0e-10, close - width - delta), "center": max(1.0e-10, close - width / 2.0), "after": close + delta}
        for placement, start in starts.items():
            glitch = {"start_s": start, "width_s": width, "depth_v": float(case["depth_v"])}
            row = capture_metrics(run_scenario(hspice, out, config, cells, index, "{}_{}".format(case["case_id"], placement), config["nominal_vdd_v"], "capture", selection["initial_rvt_stages"], selection["initial_lvt_stages"], selection["capture_phase_s"], glitch))
            row.update({"case_id": case["case_id"], "placement": placement, "glitch_start_s": start, "glitch_width_s": width, "glitch_depth_v": float(case["depth_v"])})
            rows.append(row)
            index += 1
    write_csv(out / "glitch_matrix.csv", rows)
    summarize_glitch_csv(out, str(selection["nominal_captured_xor_word"]))


def summarize_glitch_csv(output_dir: Path, baseline: str) -> None:
    """Annotate completed glitch evidence without launching another HSPICE run.

    The nominal captured word is a measured selected-operating-point value.
    Comparing every retained glitch word against it makes both detected and
    blind placements explicit while leaving raw analog/capture evidence intact.
    """

    matrix_path = output_dir / "glitch_matrix.csv"
    with matrix_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("cannot summarize empty FTC glitch matrix: {}".format(matrix_path))
    for row in rows:
        row["detection_state_change"] = int(row["captured_xor_word"] != baseline)
    write_csv(matrix_path, rows)
    summary = {
        "scenario_count": len(rows), "baseline_captured_xor_word": baseline,
        "changed_cases": sum(int(row["detection_state_change"]) for row in rows),
        "blind_cases": sum(1 - int(row["detection_state_change"]) for row in rows),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: Iterable[str] = None) -> int:
    """Dispatch only explicitly named FTC characterization stages."""

    parser = argparse.ArgumentParser(description="run standalone FTC physical characterizations")
    parser.add_argument("stage", choices=("mechanism-search", "mechanism-coarse", "xor-loading", "capture-phase", "integrated-coarse", "fine", "phase-sensitivity", "glitch", "glitch-summary"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--initial-rvt-stages", type=int, help="explicit coarse-only window-placement retry value")
    parser.add_argument("--initial-lvt-stages", type=int, help="explicit coarse-only window-placement retry value")
    parser.add_argument("--capture-phase-s", type=float, help="explicit coarse-only window-placement retry phase")
    parser.add_argument("--resume", action="store_true", help="reuse manifest-matched completed coarse scenarios and run only missing points")
    args = parser.parse_args(argv)
    config = load_json(args.config)
    cells = load_json(FTC_ROOT / "discovery/selected_cells.json")
    if args.stage == "mechanism-search": run_mechanism_search(args, config, cells)
    elif args.stage == "mechanism-coarse": args.mode = "mechanism"; run_coarse(args, config, cells)
    elif args.stage == "xor-loading": run_xor_loading(args, config, cells)
    elif args.stage == "capture-phase": run_capture_phase(args, config, cells)
    elif args.stage == "integrated-coarse": args.mode = "capture"; run_coarse(args, config, cells)
    elif args.stage == "fine": run_fine(args, config, cells)
    elif args.stage == "phase-sensitivity": run_phase_sensitivity(args, config, cells)
    elif args.stage == "glitch": run_glitch(args, config, cells)
    else: summarize_glitch_csv(args.output_dir.resolve(), str(selected_operating_point(config)["nominal_captured_xor_word"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
