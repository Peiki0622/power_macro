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
import math
import shutil
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


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
                 glitch: Optional[Dict[str, float]] = None,
                 edge_train: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        capture_phase_s=float(capture_phase_s), glitch=glitch, edge_train=edge_train,
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
    if edge_train is not None:
        # Wavefront experiments preserve independent transition evidence for
        # every injected edge.  Do not overload the legacy single-RISE keys:
        # a falling edge and a later repeated rise have different HSPICE
        # occurrence counts and must remain attributable in compact evidence.
        sequence = generate_ftc_deck.normalize_edge_train(edge_train)
        samples: List[Dict[str, Any]] = []
        for edge in sequence["edges"]:
            edge_index = int(edge["edge_index"])
            rvt = [values.get("rvt_e{:02d}_t{:02d}_cross".format(edge_index, tap)) for tap in range(stages)]
            lvt = [values.get("lvt_e{:02d}_t{:02d}_cross".format(edge_index, tap)) for tap in range(stages)]
            if any(value is None for value in rvt + lvt):
                raise ValueError("FTC edge train has a missing observable transition: {} edge {}".format(scenario_dir, edge_index))
            sample: Dict[str, Any] = {
                "scenario": str(scenario_dir.relative_to(output_dir)), "mode": mode, "vdd_v": float(vdd_v),
                "initial_rvt_stages": int(initial_rvt), "initial_lvt_stages": int(initial_lvt),
                "capture_phase_s": float(capture_phase_s),
                "first_edge_time_s": float(sequence["first_edge_time_s"]),
                "edge_spacing_s": float(sequence["edge_spacing_s"]),
                "edge_count": int(sequence["edge_count"]),
                "initial_logic_level": int(sequence["initial_logic_level"]),
                "edge_index": edge_index, "edge_polarity": str(edge["polarity"]),
                "edge_time_s": float(edge["time_s"]),
                "sample_time_s": float(edge["time_s"]) + float(capture_phase_s),
                "rvt_transition_s": [float(value) for value in rvt],
                "lvt_transition_s": [float(value) for value in lvt],
                "vdd_a_min_v": values.get("vdd_a_min_v"),
            }
            if mode == "xor":
                xor_levels = [values.get("xor_e{:02d}_t{:02d}_level".format(edge_index, tap)) for tap in range(stages)]
                if any(value is None for value in xor_levels):
                    raise ValueError("FTC edge train XOR measurement is incomplete: {} edge {}".format(scenario_dir, edge_index))
                sample["raw_xor_word"] = ftc_analysis.word(ftc_analysis.bits_from_levels(xor_levels, float(vdd_v) / 2.0))
            samples.append(sample)
        return {"scenario": str(scenario_dir.relative_to(output_dir)), "samples": samples}
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
    for key in ("rvt_crossings_s", "lvt_crossings_s", "rvt_transition_s", "lvt_transition_s"):
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


def phase_diverse_settings(path: Path, base_config: Dict[str, Any]) -> Dict[str, Any]:
    """Load and strictly validate the task-local phase-diversity contract.

    This deliberately lives beside the existing runner rather than creating a
    second HSPICE flow.  The base FTC configuration remains the immutable
    single-phase reference while this object contains only the new candidate
    phase and glitch-screening parameters.  Rejecting malformed inputs here
    prevents an invalid voltage glitch from consuming a physical run.
    """

    settings = load_json(path)
    required = (
        "phase_reference_s", "phase_step_s", "candidate_multipliers",
        "anchor_vdd_v", "coarse_vdd_v", "formal_minimum_vdd_v",
        "maximum_glitch_depth_v", "medium_glitch", "representative_glitches",
        "jitter_offset_multipliers",
    )
    if any(key not in settings for key in required):
        raise ValueError("incomplete phase-diversity configuration: {}".format(path))
    if float(settings["formal_minimum_vdd_v"]) != float(base_config["minimum_vdd_v"]):
        raise ValueError("phase-diversity minimum VDD must match the frozen FTC range")
    if float(settings["phase_reference_s"]) != float(base_config["selected_operating_point"]["capture_phase_s"]):
        raise ValueError("phase-diversity reference phase must remain the frozen 300 ps point")
    if float(settings["phase_step_s"]) != float(base_config["selected_operating_point"]["capture_phase_step_s"]):
        raise ValueError("phase-diversity phase step must come from measured FTC evidence")
    multipliers = settings["candidate_multipliers"]
    if not isinstance(multipliers, list) or len(multipliers) < 2 or len(set(multipliers)) != len(multipliers):
        raise ValueError("candidate phase multipliers must be a unique list containing at least two values")
    if any(int(value) != value for value in multipliers):
        raise ValueError("candidate phase multipliers must be integral measured-step offsets")
    phases = [float(settings["phase_reference_s"]) + int(value) * float(settings["phase_step_s"]) for value in multipliers]
    if any(phase <= 0.0 or phase >= float(base_config["sampling_period_s"]) for phase in phases):
        raise ValueError("candidate capture phase lies outside the FTC sampling period")
    if sorted(float(value) for value in settings["anchor_vdd_v"]) != [0.75, 0.9, 1.1]:
        raise ValueError("phase-diversity anchors must be exactly 0.75, 0.90, and 1.10 V")
    if any(float(value) < float(settings["formal_minimum_vdd_v"]) for value in settings["coarse_vdd_v"]):
        raise ValueError("phase-diversity coarse sweep exceeds the formal minimum VDD")
    if float(settings["maximum_glitch_depth_v"]) > float(base_config["nominal_vdd_v"]) - float(settings["formal_minimum_vdd_v"]):
        raise ValueError("phase-diversity glitch ceiling would violate the formal minimum VDD")
    for glitch in [settings["medium_glitch"]] + list(settings["representative_glitches"]):
        if not isinstance(glitch, dict) or not isinstance(glitch.get("case_id"), str):
            raise ValueError("every phase-diversity glitch needs a stable case_id")
        if float(glitch.get("depth_v", 0.0)) <= 0.0 or float(glitch["depth_v"]) > float(settings["maximum_glitch_depth_v"]):
            raise ValueError("phase-diversity glitch depth is outside the approved 0--350 mV range")
        if float(glitch.get("width_s", 0.0)) <= 0.0:
            raise ValueError("phase-diversity glitch width must be positive")
    return settings


def phase_diverse_candidates(settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create deterministic phase IDs and values from the measured local step.

    The ID encodes the signed measured-step multiplier rather than a rounded
    time in picoseconds.  It is therefore stable across CSV, JSON, RTL
    packaging, and future physical tap characterization.
    """

    result: List[Dict[str, Any]] = []
    for multiplier in settings["candidate_multipliers"]:
        signed = int(multiplier)
        phase_id = "phi_{:+03d}".format(signed).replace("+", "p").replace("-", "m")
        result.append({
            "phase_id": phase_id,
            "phase_multiplier": signed,
            "capture_phase_s": float(settings["phase_reference_s"]) + signed * float(settings["phase_step_s"]),
        })
    return result


def requested_phase_candidates(settings: Dict[str, Any], phase_ids: Optional[str]) -> List[Dict[str, Any]]:
    """Resolve an optional comma-separated phase-ID subset without guessing IDs."""

    candidates = phase_diverse_candidates(settings)
    by_id = {str(item["phase_id"]): item for item in candidates}
    if phase_ids is None:
        return candidates
    requested = [item.strip() for item in phase_ids.split(",") if item.strip()]
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("phase-diversity phase IDs must be a nonempty unique comma-separated list")
    unknown = [item for item in requested if item not in by_id]
    if unknown:
        raise ValueError("unknown phase-diversity phase IDs: {}".format(",".join(unknown)))
    return [by_id[item] for item in requested]


def phase_diverse_output(path: Path, config: Dict[str, Any], cells: Dict[str, Any]) -> Path:
    """Open one resumable task-owned run root without overwriting evidence.

    The anchor, coarse, jitter, and glitch subcommands write different compact
    files below their own root.  A repeated command is allowed only when the
    manifest proves that it uses the identical frozen FTC configuration and
    selected real cells; raw scenario names remain unique because each stage
    includes its phase and purpose in the label.
    """

    if not path.exists():
        return prepare_output(path, config, cells)
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        # Baseline analysis is intentionally pure data and may create its
        # compact JSON before the first jitter simulation.  Permit exactly
        # that ordering, but never reuse a directory that already contains
        # raw scenarios without an auditable immutable-input manifest.
        if (path / "scenarios").exists():
            raise ValueError("existing phase-diversity scenarios lack a manifest: {}".format(path))
        hspice = run_dc_sweep.require_regular_file(Path(config["hspice"]), "HSPICE", executable=True)
        version = run_dc_sweep.hspice_version(hspice)
        if str(config["expected_hspice_version"]) not in version:
            raise RuntimeError("unexpected HSPICE version: {}".format(version))
        for source in list(cells["source_files"].values()) + [config["model_library"]]:
            run_dc_sweep.require_regular_file(Path(source), "FTC source collateral")
        run_dc_sweep.require_regular_file(FTC_ROOT / "spice/empty_subckt.sp_cal", "FTC LVT compatibility include")
        manifest_path.write_text(
            json.dumps({"study": config["study_name"], "hspice_version": version, "config": config, "selected_cells": cells}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return hspice
    manifest = load_json(manifest_path)
    if manifest.get("config") != config or manifest.get("selected_cells") != cells:
        raise ValueError("existing phase-diversity run has incompatible FTC inputs: {}".format(path))
    return run_dc_sweep.require_regular_file(Path(config["hspice"]), "HSPICE", executable=True)


def read_rows_if_present(path: Path) -> List[Dict[str, Any]]:
    """Read a compact CSV before appending another disjoint physical campaign."""

    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def run_phase_diverse_static(args: argparse.Namespace, config: Dict[str, Any], cells: Dict[str, Any]) -> None:
    """Characterize caller-selected explicit phases at anchors or the coarse grid.

    This is intentionally a separate stage from the frozen fine sweep.  It
    keeps the physical front-end unchanged and records one independently
    captured observation for every (phase, VDD) point, which is the required
    evidence for later virtual same-launch union analysis.
    """

    settings = phase_diverse_settings(args.phase_diverse_config, config)
    candidates = requested_phase_candidates(settings, args.phase_ids)
    voltages = settings["anchor_vdd_v"] if args.screen == "anchor" else settings["coarse_vdd_v"]
    out = args.output_dir.resolve()
    hspice = phase_diverse_output(out, config, cells)
    rows: List[Dict[str, Any]] = []
    index = 0
    for candidate in candidates:
        for voltage in voltages:
            record = capture_metrics(run_scenario(
                hspice, out, config, cells, index,
                "{}_{}".format(args.screen, candidate["phase_id"]), float(voltage), "capture",
                int(config["selected_operating_point"]["initial_rvt_stages"]),
                int(config["selected_operating_point"]["initial_lvt_stages"]),
                float(candidate["capture_phase_s"]),
            ))
            record.update(candidate)
            rows.append(record)
            index += 1
    output_name = "phase_candidate_anchor.csv" if args.screen == "anchor" else "phase_candidate_coarse.csv"
    write_csv(out / output_name, rows)


def run_phase_diverse_jitter(args: argparse.Namespace, config: Dict[str, Any], cells: Dict[str, Any]) -> None:
    """Measure the bounded no-glitch phase envelope for already selected phases."""

    settings = phase_diverse_settings(args.phase_diverse_config, config)
    candidates = requested_phase_candidates(settings, args.phase_ids)
    out = args.output_dir.resolve()
    hspice = phase_diverse_output(out, config, cells)
    rows: List[Dict[str, Any]] = []
    index = 0
    for candidate in candidates:
        for voltage in settings["anchor_vdd_v"]:
            for offset_multiplier in settings["jitter_offset_multipliers"]:
                offset_s = float(offset_multiplier) * float(settings["phase_step_s"])
                record = capture_metrics(run_scenario(
                    hspice, out, config, cells, index,
                    "jitter_{}_{}".format(candidate["phase_id"], str(offset_multiplier).replace("-", "m")),
                    float(voltage), "capture",
                    int(config["selected_operating_point"]["initial_rvt_stages"]),
                    int(config["selected_operating_point"]["initial_lvt_stages"]),
                    float(candidate["capture_phase_s"]) + offset_s,
                ))
                record.update(candidate)
                record["phase_offset_s"] = offset_s
                rows.append(record)
                index += 1
    write_csv(out / "phase_jitter.csv", rows)


def phase_diverse_glitch_cases(settings: Dict[str, Any], requested_ids: str) -> List[Dict[str, Any]]:
    """Resolve named bounded glitch families and reject accidental broad sweeps."""

    all_cases = [settings["medium_glitch"]] + list(settings["representative_glitches"])
    by_id = {str(item["case_id"]): item for item in all_cases}
    requested = [item.strip() for item in requested_ids.split(",") if item.strip()]
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("glitch case IDs must be a nonempty unique comma-separated list")
    unknown = [item for item in requested if item not in by_id]
    if unknown:
        raise ValueError("unknown phase-diversity glitch IDs: {}".format(",".join(unknown)))
    return [by_id[item] for item in requested]


def parse_onsets(value: Optional[str], width_s: float, last_phase_s: float, config: Dict[str, Any], settings: Dict[str, Any]) -> List[float]:
    """Build a finite relative-onset grid or consume explicit local refinements.

    Default coverage begins one width before launch and ends only after the
    latest selected capture plus its FF/read margin.  The coarse interval is
    tied to measured stage timing and never becomes a gratuitous sub-ps grid.
    """

    if value is not None:
        result = [float(item.strip()) for item in value.split(",") if item.strip()]
        if not result:
            raise ValueError("explicit onset list is empty")
        return sorted(set(result))
    step_s = min(float(settings["phase_step_s"]), float(width_s) / 4.0)
    end_s = float(last_phase_s) + float(config["ff_capture_delay_s"]) + float(config["post_capture_read_delay_s"])
    start_s = -float(width_s)
    count = int((end_s - start_s) / step_s) + 1
    return [start_s + index * step_s for index in range(count + 1) if start_s + index * step_s <= end_s + 1.0e-18]


def run_phase_diverse_glitch(args: argparse.Namespace, config: Dict[str, Any], cells: Dict[str, Any]) -> None:
    """Run a bounded onset-by-phase physical map against phase-specific baselines."""

    settings = phase_diverse_settings(args.phase_diverse_config, config)
    candidates = requested_phase_candidates(settings, args.phase_ids)
    baselines = load_json(args.baseline_path)
    by_phase = {str(item["phase_id"]): item for item in baselines.get("phases", [])}
    if set(item["phase_id"] for item in candidates) - set(by_phase):
        raise ValueError("glitch map lacks a phase-specific nominal baseline")
    cases = phase_diverse_glitch_cases(settings, args.glitch_case_ids)
    out = args.output_dir.resolve()
    hspice = phase_diverse_output(out, config, cells)
    existing = read_rows_if_present(out / "glitch_phase_map.csv")
    rows: List[Dict[str, Any]] = []
    index = len(existing)
    last_phase = max(float(item["capture_phase_s"]) for item in candidates)
    for case in cases:
        for onset_s in parse_onsets(args.onsets_s, float(case["width_s"]), last_phase, config, settings):
            glitch = {
                "start_s": float(config["launch_time_s"]) + onset_s,
                "width_s": float(case["width_s"]),
                "depth_v": float(case["depth_v"]),
            }
            if glitch["start_s"] <= 0.0:
                # The deck requires a positive absolute PWL time.  The formal
                # relative interval is still represented by the earliest
                # physically realizable start instead of silently clipping it.
                continue
            for candidate in candidates:
                record = capture_metrics(run_scenario(
                    hspice, out, config, cells, index,
                    "glitch_{}_{}_o{:04d}".format(case["case_id"], candidate["phase_id"], index),
                    float(config["nominal_vdd_v"]), "capture",
                    int(config["selected_operating_point"]["initial_rvt_stages"]),
                    int(config["selected_operating_point"]["initial_lvt_stages"]),
                    float(candidate["capture_phase_s"]), glitch,
                ))
                baseline = by_phase[str(candidate["phase_id"])]
                record.update(candidate)
                record.update({
                    "case_id": case["case_id"], "glitch_depth_v": float(case["depth_v"]),
                    "glitch_width_s": float(case["width_s"]), "glitch_start_s": glitch["start_s"],
                    "glitch_onset_rel_s": onset_s,
                    "full_word_changed": int(record["captured_xor_word"] != baseline["captured_xor_word"]),
                    "encoded_state_changed": int(
                        int(record["start_index"]) != int(baseline["start_index"]) or
                        int(record["end_index"]) != int(baseline["end_index"])
                    ),
                    "boundary_distance": abs(int(record["start_index"]) - int(baseline["start_index"])) +
                                         abs(int(record["end_index"]) - int(baseline["end_index"])),
                })
                rows.append(record)
                index += 1
    write_csv(out / "glitch_phase_map.csv", existing + rows)


def load_wavefront_settings(path: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    """Load the small task-local edge-train contract without touching FTC defaults.

    The formal FTC configuration remains the source of process, cells, delay
    chain length, and selected operating point.  This sidecar contains only
    experiment-local stimulus values, so a wavefront study cannot accidentally
    become a new nominal configuration selection.
    """

    settings = load_json(path)
    required = ("first_edge_time_s", "sample_offset_s", "anchor_vdd_v", "falling_edge", "two_edge", "eight_edge")
    if any(key not in settings for key in required):
        raise ValueError("wavefront configuration is incomplete: {}".format(path))
    anchors = [float(value) for value in settings["anchor_vdd_v"]]
    if anchors != [1.1, 0.9, float(config["minimum_vdd_v"])]:
        raise ValueError("wavefront anchors must remain 1.10, 0.90, and the selected minimum VDD")
    selected = selected_operating_point(config)
    if not math.isclose(float(settings["sample_offset_s"]), float(selected["capture_phase_s"]), rel_tol=0.0, abs_tol=1.0e-18):
        raise ValueError("wavefront sample offset must retain the selected 300 ps relative observation")
    spacings = [float(value) for value in settings["two_edge"].get("candidate_spacing_s", [])]
    if len(spacings) != 7 or any(value <= 0.0 for value in spacings) or spacings != sorted(spacings, reverse=True):
        raise ValueError("wavefront nominal spacing list must contain seven descending positive values")
    for name, expected_count in (("falling_edge", 1), ("two_edge", 2), ("eight_edge", 8)):
        block = settings[name]
        if int(block.get("edge_count", 0)) != expected_count or int(block.get("initial_logic_level", -1)) not in (0, 1):
            raise ValueError("wavefront {} edge-train definition is invalid".format(name))
    return settings


def wavefront_stage_dir(root: Path, step: str) -> Path:
    """Return the one isolated run directory owned by a wavefront sub-step."""

    return root.resolve() / step


def wavefront_train(settings: Dict[str, Any], block_name: str, spacing_s: float) -> Dict[str, Any]:
    """Build only the four permitted regular-edge controls for one scenario."""

    block = settings[block_name]
    return {
        "first_edge_time_s": float(settings["first_edge_time_s"]),
        "edge_spacing_s": float(spacing_s),
        "edge_count": int(block["edge_count"]),
        "initial_logic_level": int(block["initial_logic_level"]),
    }


def wavefront_window_level(metrics: Dict[str, Any]) -> int:
    """Classify raw multi-window evidence without adding a physical decoder.

    Level 1 is deliberately narrow: exactly two runs and a 2:1 dominant-run
    ratio.  Three or more runs, equal windows, and all-zero words are never
    hidden behind the historical longest-run result.
    """

    if not int(metrics["valid"]):
        return 3
    if int(metrics["run_count"]) == 1:
        return 0
    if int(metrics["run_count"]) == 2 and int(metrics["largest_run_length"]) >= 2 * int(metrics["second_largest_run_length"]):
        return 1
    return 2


def transition_ordered(sample: Dict[str, Any]) -> int:
    """Check that one physical edge propagated once and in tap order on both paths.

    This is an evidence-quality check, not a new timing criterion.  Each tap
    must cross after its source edge and successive buffer taps must cross in
    strictly increasing time order; otherwise the result cannot support a
    claim that a falling edge cleanly restored the shared delay line.
    """

    edge_time = float(sample["edge_time_s"])
    for key in ("rvt_transition_s", "lvt_transition_s"):
        values = [float(value) for value in sample[key]]
        if any(value <= edge_time for value in values):
            return 0
        if any(later <= earlier for earlier, later in zip(values, values[1:])):
            return 0
    return 1


def wavefront_sample_metrics(sample: Dict[str, Any]) -> Dict[str, Any]:
    """Attach raw-XOR run metrics and transition-quality evidence to one sample."""

    result = dict(sample)
    result.update(ftc_analysis.longest_one_run([int(bit) for bit in result["raw_xor_word"]]))
    result["window_level"] = wavefront_window_level(result)
    result["transition_ordered"] = transition_ordered(result)
    return result


def run_wavefront_scenario(hspice: Path, output_dir: Path, config: Dict[str, Any], cells: Dict[str, Any],
                           index: int, label: str, vdd_v: float, settings: Dict[str, Any],
                           block_name: str, spacing_s: float) -> List[Dict[str, Any]]:
    """Execute one bounded raw-XOR edge-train scenario and return one row per edge.

    The generic runner owns process invocation, scenario isolation, listing
    validation, and measurement parsing.  This wrapper only assigns the
    wavefront interpretation that depends on consecutive physical edges.
    """

    point = selected_operating_point(config)
    raw = run_scenario(
        hspice, output_dir, config, cells, index, label, float(vdd_v), "xor",
        int(point["initial_rvt_stages"]), int(point["initial_lvt_stages"]),
        float(settings["sample_offset_s"]), edge_train=wavefront_train(settings, block_name, spacing_s),
    )
    rows = [wavefront_sample_metrics(sample) for sample in raw["samples"]]
    for row_index, row in enumerate(rows):
        if row_index == 0:
            row["preceding_wavefront_exit_time_s"] = ""
            row["overlap_expected"] = 0
            continue
        previous = rows[row_index - 1]
        # A wavefront remains in the observable line until the later of the
        # RVT/LVT final taps crosses.  This is measured in the same scenario,
        # not inferred from a nominal delay table or spacing label.
        exit_time = max(float(previous["rvt_transition_s"][-1]), float(previous["lvt_transition_s"][-1]))
        row["preceding_wavefront_exit_time_s"] = exit_time
        row["overlap_expected"] = int(float(row["edge_time_s"]) < exit_time)
    return rows


def write_wavefront_summary(path: Path, summary: Dict[str, Any]) -> None:
    """Write a deterministic, compact task decision record."""

    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_wavefront_summary(root: Path, step: str, name: str) -> Dict[str, Any]:
    """Read a prerequisite summary and fail before launching an invalid later step."""

    path = wavefront_stage_dir(root, step) / name
    if not path.is_file():
        raise ValueError("required wavefront prerequisite is unavailable: {}".format(path))
    return load_json(path)


def read_wavefront_rows(root: Path, step: str, name: str) -> List[Dict[str, Any]]:
    """Read compact committed-style evidence; never inspect ignored HSPICE products."""

    path = wavefront_stage_dir(root, step) / name
    if not path.is_file():
        return []
    return read_rows_if_present(path)


def spacing_key(value: float) -> str:
    """Use a lossless-enough fixed key for deterministic JSON spacing maps."""

    return "{:.12e}".format(float(value))


def two_edge_rows_acceptable(rows: Sequence[Dict[str, Any]], falling_class: str) -> int:
    """Apply the plan's A/B decoding rule to one rise/fall physical scenario."""

    ordered = sorted(rows, key=lambda row: int(row["edge_index"]))
    if len(ordered) != 2 or any(not int(row["transition_ordered"]) for row in ordered):
        return 0
    if falling_class == "sensible":
        return int(all(int(row["window_level"]) <= 1 for row in ordered))
    # A reset-only falling edge is not called an independent probe.  Its
    # rising predecessor must remain decodable while the fall still carries
    # complete physical transition evidence for the later 8-edge experiment.
    return int(int(ordered[0]["window_level"]) <= 1)


def falling_classification(rows: Sequence[Dict[str, Any]]) -> str:
    """Return the minimal A/B/C classification required before overlap testing."""

    if any(not int(row["transition_ordered"]) for row in rows):
        return "destructive"
    if all(int(row["window_level"]) <= 1 for row in rows):
        return "sensible"
    return "reset_only"


def run_wavefront_falling(args: argparse.Namespace, config: Dict[str, Any], cells: Dict[str, Any], settings: Dict[str, Any]) -> None:
    """Measure isolated falling-edge raw-XOR behavior at the three anchors."""

    out = wavefront_stage_dir(args.output_dir, "falling")
    hspice = prepare_output(out, config, cells)
    rows: List[Dict[str, Any]] = []
    spacing = float(settings["falling_edge"]["edge_spacing_s"])
    for index, voltage in enumerate(settings["anchor_vdd_v"]):
        rows.extend(run_wavefront_scenario(hspice, out, config, cells, index, "falling", float(voltage), settings, "falling_edge", spacing))
    classification = falling_classification(rows)
    write_csv(out / "isolated_falling_edge.csv", rows)
    write_wavefront_summary(out / "isolated_falling_edge_summary.json", {
        "classification": classification,
        "edge_count": 1,
        "sample_offset_s": float(settings["sample_offset_s"]),
        "vdd_anchor_count": len(settings["anchor_vdd_v"]),
        "all_transition_ordered": int(all(int(row["transition_ordered"]) for row in rows)),
        "all_windows_decodable": int(all(int(row["window_level"]) <= 1 for row in rows)),
    })


def run_wavefront_two_edge_nominal(args: argparse.Namespace, config: Dict[str, Any], cells: Dict[str, Any], settings: Dict[str, Any]) -> None:
    """Find the bounded 1.10 V two-wavefront coexistence boundary."""

    root = args.output_dir.resolve()
    falling = read_wavefront_summary(root, "falling", "isolated_falling_edge_summary.json")
    falling_class = str(falling["classification"])
    if falling_class == "destructive":
        raise RuntimeError("falling edge is destructive; two-edge wavefront experiment is not authorized")
    out = wavefront_stage_dir(root, "two_edge_nominal")
    hspice = prepare_output(out, config, cells)
    rows: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    for index, spacing in enumerate(settings["two_edge"]["candidate_spacing_s"]):
        scenario_rows = run_wavefront_scenario(
            hspice, out, config, cells, index, "two_t{}ps".format(int(round(float(spacing) * 1.0e12))),
            1.1, settings, "two_edge", float(spacing),
        )
        rows.extend(scenario_rows)
        second = [row for row in scenario_rows if int(row["edge_index"]) == 1][0]
        results.append({
            "edge_spacing_s": float(spacing),
            "overlap_expected": int(second["overlap_expected"]),
            "acceptable": two_edge_rows_acceptable(scenario_rows, falling_class),
            "window_levels": [int(row["window_level"]) for row in scenario_rows],
        })
    overlap_pass = [item for item in results if item["overlap_expected"] and item["acceptable"]]
    write_csv(out / "two_edge_nominal.csv", rows)
    write_wavefront_summary(out / "two_edge_nominal_summary.json", {
        "falling_classification": falling_class,
        "spacing_results": results,
        "overlap_pass_count": len(overlap_pass),
        "status": "pass" if overlap_pass else "no_go",
    })


def select_anchor_spacings(nominal: Dict[str, Any]) -> List[float]:
    """Select at most three informative points, avoiding a Cartesian re-run."""

    results = nominal["spacing_results"]
    passing_nonoverlap = sorted(float(item["edge_spacing_s"]) for item in results if not int(item["overlap_expected"]) and int(item["acceptable"]))
    passing_overlap = sorted((float(item["edge_spacing_s"]) for item in results if int(item["overlap_expected"]) and int(item["acceptable"])), reverse=True)
    selected: List[float] = []
    if passing_nonoverlap:
        # The shortest passing non-overlap point is closest to coexistence and
        # is more useful than repeating a very slow two-nanosecond baseline.
        selected.append(passing_nonoverlap[0])
    if passing_overlap:
        # The largest passing overlap is the conservative overlapping point.
        selected.append(passing_overlap[0])
        # A distinct smallest passing overlap supplies one aggressive boundary
        # probe without expanding back to the seven-point nominal sweep.
        if passing_overlap[-1] != passing_overlap[0]:
            selected.append(passing_overlap[-1])
    return selected


def run_wavefront_two_edge_anchor(args: argparse.Namespace, config: Dict[str, Any], cells: Dict[str, Any], settings: Dict[str, Any]) -> None:
    """Validate only selected two-edge candidates at the approved VDD anchors."""

    root = args.output_dir.resolve()
    nominal = read_wavefront_summary(root, "two_edge_nominal", "two_edge_nominal_summary.json")
    if nominal["status"] != "pass":
        raise RuntimeError("no acceptable nominal overlap exists; anchor expansion is not authorized")
    falling_class = str(nominal["falling_classification"])
    spacings = select_anchor_spacings(nominal)
    out = wavefront_stage_dir(root, "two_edge_anchor")
    hspice = prepare_output(out, config, cells)
    rows: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    scenario_index = 0
    for spacing in spacings:
        voltage_results: List[Dict[str, Any]] = []
        for voltage in settings["anchor_vdd_v"]:
            scenario_rows = run_wavefront_scenario(
                hspice, out, config, cells, scenario_index,
                "anchor_t{}ps".format(int(round(spacing * 1.0e12))), float(voltage), settings, "two_edge", spacing,
            )
            scenario_index += 1
            rows.extend(scenario_rows)
            second = [row for row in scenario_rows if int(row["edge_index"]) == 1][0]
            voltage_results.append({
                "vdd_v": float(voltage), "overlap_expected": int(second["overlap_expected"]),
                "acceptable": two_edge_rows_acceptable(scenario_rows, falling_class),
                "window_levels": [int(row["window_level"]) for row in scenario_rows],
            })
        stable_overlap = int(all(item["overlap_expected"] and item["acceptable"] for item in voltage_results))
        results.append({"edge_spacing_s": spacing, "vdd_results": voltage_results, "stable_overlap": stable_overlap})
    write_csv(out / "two_edge_anchor.csv", rows)
    write_wavefront_summary(out / "two_edge_anchor_summary.json", {
        "falling_classification": falling_class,
        "selected_spacings_s": spacings,
        "spacing_results": results,
        "stable_overlap_count": sum(int(item["stable_overlap"]) for item in results),
        "status": "pass" if any(int(item["stable_overlap"]) for item in results) else "no_go",
    })


def eight_edge_stable(rows: Sequence[Dict[str, Any]], falling_class: str) -> int:
    """Evaluate the explicitly bounded rise/fall steady-state criterion."""

    ordered = sorted(rows, key=lambda row: int(row["edge_index"]))
    if len(ordered) != 8 or any(not int(row["transition_ordered"]) for row in ordered):
        return 0
    rises = [row for row in ordered if row["edge_polarity"] == "rise"]
    falls = [row for row in ordered if row["edge_polarity"] == "fall"]
    if len(rises) != 4 or len(falls) != 4:
        return 0
    signature = lambda row: (int(row["window_level"]), int(row["start_index"]), int(row["end_index"]))
    if falling_class == "sensible":
        if any(int(row["window_level"]) > 1 for row in ordered[2:]):
            return 0
        return int(signature(rises[-2]) == signature(rises[-1]) and signature(falls[-2]) == signature(falls[-1]))
    # Reset-only mode still rejects any drifting or undecodable rising probe;
    # falling rows are checked through ordered physical transition evidence,
    # not relabelled as usable observation windows.
    if any(int(row["window_level"]) > 1 for row in rises[1:]):
        return 0
    return int(signature(rises[-2]) == signature(rises[-1]))


def run_wavefront_eight_edge(args: argparse.Namespace, config: Dict[str, Any], cells: Dict[str, Any], settings: Dict[str, Any]) -> None:
    """Test 8-edge periodicity, adding 0.90 V only after endpoint success."""

    root = args.output_dir.resolve()
    anchor = read_wavefront_summary(root, "two_edge_anchor", "two_edge_anchor_summary.json")
    if anchor["status"] != "pass":
        raise RuntimeError("no three-anchor stable overlap exists; eight-edge experiment is not authorized")
    falling_class = str(anchor["falling_classification"])
    stable = sorted((float(item["edge_spacing_s"]) for item in anchor["spacing_results"] if int(item["stable_overlap"])), reverse=True)
    spacings = stable[:1] + ([stable[-1]] if len(stable) > 1 and stable[-1] != stable[0] else [])
    out = wavefront_stage_dir(root, "eight_edge")
    hspice = prepare_output(out, config, cells)
    rows: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    scenario_index = 0
    for spacing in spacings:
        voltage_results: List[Dict[str, Any]] = []
        for voltage in (1.1, float(config["minimum_vdd_v"])):
            scenario_rows = run_wavefront_scenario(
                hspice, out, config, cells, scenario_index,
                "eight_t{}ps".format(int(round(spacing * 1.0e12))), voltage, settings, "eight_edge", spacing,
            )
            scenario_index += 1
            rows.extend(scenario_rows)
            voltage_results.append({"vdd_v": voltage, "steady_state": eight_edge_stable(scenario_rows, falling_class)})
        if all(int(item["steady_state"]) for item in voltage_results):
            scenario_rows = run_wavefront_scenario(
                hspice, out, config, cells, scenario_index,
                "eight_t{}ps".format(int(round(spacing * 1.0e12))), 0.9, settings, "eight_edge", spacing,
            )
            scenario_index += 1
            rows.extend(scenario_rows)
            voltage_results.append({"vdd_v": 0.9, "steady_state": eight_edge_stable(scenario_rows, falling_class)})
        stable_three_anchor = int(len(voltage_results) == 3 and all(int(item["steady_state"]) for item in voltage_results))
        results.append({"edge_spacing_s": spacing, "vdd_results": voltage_results, "stable_three_anchor": stable_three_anchor})
    write_csv(out / "eight_edge_pipeline.csv", rows)
    write_wavefront_summary(out / "eight_edge_pipeline_summary.json", {
        "falling_classification": falling_class,
        "tested_spacings_s": spacings,
        "spacing_results": results,
        "stable_three_anchor_count": sum(int(item["stable_three_anchor"]) for item in results),
        "status": "pass" if any(int(item["stable_three_anchor"]) for item in results) else "no_go",
    })


def optional_wavefront_summary(root: Path, step: str, name: str) -> Optional[Dict[str, Any]]:
    """Return an optional completed-stage summary without probing raw artifacts."""

    path = wavefront_stage_dir(root, step) / name
    return load_json(path) if path.is_file() else None


def tested_interval_summary(nominal: Optional[Dict[str, Any]], anchor: Optional[Dict[str, Any]],
                            eight: Optional[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Report only measured interval landmarks; never interpolate a frequency limit."""

    intervals: Dict[str, Optional[float]] = {
        "T_edge_nonoverlap_s": None,
        "T_edge_overlap_begin_s": None,
        "T_edge_min_tested_stable_s": None,
        "T_edge_first_unstable_s": None,
        "T_edge_recommended_for_next_stage_s": None,
    }
    if nominal is not None:
        nominal_results = nominal.get("spacing_results", [])
        nonoverlap = sorted(float(item["edge_spacing_s"]) for item in nominal_results if not int(item["overlap_expected"]))
        overlap = sorted((float(item["edge_spacing_s"]) for item in nominal_results if int(item["overlap_expected"])), reverse=True)
        intervals["T_edge_nonoverlap_s"] = nonoverlap[0] if nonoverlap else None
        intervals["T_edge_overlap_begin_s"] = overlap[0] if overlap else None
    stable_anchor: List[float] = []
    if anchor is not None:
        stable_anchor = sorted(float(item["edge_spacing_s"]) for item in anchor.get("spacing_results", []) if int(item["stable_overlap"]))
    stable_eight: List[float] = []
    if eight is not None:
        stable_eight = sorted(float(item["edge_spacing_s"]) for item in eight.get("spacing_results", []) if int(item["stable_three_anchor"]))
    if stable_eight:
        intervals["T_edge_min_tested_stable_s"] = stable_eight[0]
        intervals["T_edge_recommended_for_next_stage_s"] = stable_eight[-1]
    elif stable_anchor:
        # This remains a two-edge-only result.  It is useful diagnostic
        # evidence but is intentionally not recommended as a hardware input.
        intervals["T_edge_min_tested_stable_s"] = stable_anchor[0]
    if anchor is not None:
        # A cross-anchor failure is more meaningful than a nominal-only
        # failure: Step 4 is explicitly where an otherwise clean 1.10 V
        # overlap must prove it remains decodable down to 0.75 V.  Ignore a
        # spacing that is non-overlapping at any anchor, then report the first
        # all-anchor overlap that fails as spacing is reduced.
        anchor_outcomes = sorted(anchor.get("spacing_results", []), key=lambda item: float(item["edge_spacing_s"]), reverse=True)
        for item in anchor_outcomes:
            all_anchor_overlap = all(int(point["overlap_expected"]) for point in item["vdd_results"])
            if all_anchor_overlap and not int(item["stable_overlap"]):
                intervals["T_edge_first_unstable_s"] = float(item["edge_spacing_s"])
                break
    if intervals["T_edge_first_unstable_s"] is None and nominal is not None:
        outcomes = sorted(nominal.get("spacing_results", []), key=lambda item: float(item["edge_spacing_s"]), reverse=True)
        seen_overlap_pass = False
        for item in outcomes:
            if not int(item["overlap_expected"]):
                continue
            if int(item["acceptable"]):
                seen_overlap_pass = True
            elif seen_overlap_pass:
                intervals["T_edge_first_unstable_s"] = float(item["edge_spacing_s"])
                break
    return intervals


def decide_wavefront_result(falling: Dict[str, Any], nominal: Optional[Dict[str, Any]],
                            anchor: Optional[Dict[str, Any]], eight: Optional[Dict[str, Any]]) -> str:
    """Apply the plan's GO/CONDITIONAL/NO-GO gates in their physical order."""

    if falling.get("classification") == "destructive":
        return "NO-GO"
    if nominal is None or nominal.get("status") != "pass":
        return "NO-GO"
    if anchor is None or anchor.get("status") != "pass":
        return "NO-GO"
    if eight is None or eight.get("status") != "pass":
        return "NO-GO"
    # A reset-only falling edge can support faster repeated rising probes but
    # cannot honestly be called a dual-edge pipelined-wavefront FTC.
    if falling.get("classification") == "reset_only":
        return "CONDITIONAL"
    return "GO"


def format_ps(value: Optional[float]) -> str:
    """Render nullable interval values without inventing an unmeasured bound."""

    return "not measured" if value is None else "{:.1f} ps".format(float(value) * 1.0e12)


def render_wavefront_report(root: Path, falling: Dict[str, Any], nominal: Optional[Dict[str, Any]],
                            anchor: Optional[Dict[str, Any]], eight: Optional[Dict[str, Any]],
                            intervals: Dict[str, Optional[float]], decision: str) -> None:
    """Publish the compact physical-feasibility report from CSV/JSON evidence only."""

    falling_rows = read_wavefront_rows(root, "falling", "isolated_falling_edge.csv")
    eight_rows = read_wavefront_rows(root, "eight_edge", "eight_edge_pipeline.csv")
    lines = [
        "# FTC Pipelined-Wavefront Physical Feasibility",
        "",
        "## Scope",
        "",
        "Phase-diverse sampling is already closed because its capture phases shared the post-capture blind interval. This study instead moves the input-edge aperture while retaining the existing SMIC40LL RVT/LVT delay chains and raw corresponding-tap XOR bank. It does not implement a capture pipeline, controller, alarm, PVT sweep, or glitch-coverage claim.",
        "",
        "## Falling-Edge Behavior",
        "",
        "| VDD (V) | Raw XOR | Start--End | Runs | Level | Ordered transition |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for row in falling_rows:
        lines.append("| {:.2f} | `{}` | {}--{} | {} | {} | {} |".format(
            float(row["vdd_v"]), row["raw_xor_word"], row["start_index"], row["end_index"],
            row["run_count"], row["window_level"], row["transition_ordered"],
        ))
    lines.extend([
        "",
        "Classification: **{}**. `sensible` means a falling edge is independently decodable at all anchors; `reset_only` means it is retained only as a physical recovery edge; `destructive` closes the route.".format(falling.get("classification", "not measured")),
        "",
        "## Two-Edge Coexistence",
        "",
        "| T_edge | All-anchor overlap | 1.10 V | 0.90 V | 0.75 V | Window levels (edge0/edge1) | Conclusion |",
        "|---:|---:|---|---|---|---|---|",
    ])
    if anchor is not None:
        for item in anchor.get("spacing_results", []):
            by_vdd = {"{:.2f}".format(float(point["vdd_v"])): point for point in item["vdd_results"]}
            def anchor_cell(voltage: str) -> str:
                point = by_vdd[voltage]
                return "overlap={}, accepted={}".format(point["overlap_expected"], point["acceptable"])
            levels = "; ".join("{} V={}".format(voltage, by_vdd[voltage]["window_levels"]) for voltage in ("1.10", "0.90", "0.75"))
            lines.append("| {:.1f} ps | {} | {} | {} | {} | {} | stable_overlap={} |".format(
                float(item["edge_spacing_s"]) * 1.0e12, int(all(int(point["overlap_expected"]) for point in item["vdd_results"])),
                anchor_cell("1.10"), anchor_cell("0.90"), anchor_cell("0.75"), levels, item["stable_overlap"],
            ))
    elif nominal is not None:
        for item in nominal.get("spacing_results", []):
            lines.append("| {:.1f} ps | not expanded | overlap={}, accepted={} | not run | not run | 1.10 V={} | nominal only |".format(
                float(item["edge_spacing_s"]) * 1.0e12, item["overlap_expected"], item["acceptable"], item["window_levels"]
            ))
    else:
        lines.append("| not run | -- | prerequisite falling-edge result stopped the study | -- | -- | -- | NO-GO |")
    lines.extend([
        "",
        "## Eight-Edge Periodicity",
        "",
        "| VDD (V) | T_edge | Edge | Polarity | Level | Start--End | Runs |",
        "|---:|---:|---:|---|---:|---:|---:|",
    ])
    for row in sorted(eight_rows, key=lambda item: (float(item["edge_spacing_s"]), float(item["vdd_v"]), int(item["edge_index"]))):
        lines.append("| {:.2f} | {:.1f} ps | {} | {} | {} | {}--{} | {} |".format(
            float(row["vdd_v"]), float(row["edge_spacing_s"]) * 1.0e12, row["edge_index"], row["edge_polarity"],
            row["window_level"], row["start_index"], row["end_index"], row["run_count"],
        ))
    if not eight_rows:
        lines.append("| not run | not run | -- | -- | -- | -- | -- |")
        lines.extend(["", "The eight-edge HSPICE step was correctly not launched because no tested T_edge was both overlapping and decodable at all three voltage anchors."])
    lines.extend([
        "",
        "## Measured Physical Interval",
        "",
        "| Landmark | Measured value |",
        "|---|---:|",
        "| Stable non-overlap point | {} |".format(format_ps(intervals["T_edge_nonoverlap_s"])),
        "| Overlap begins by | {} |".format(format_ps(intervals["T_edge_overlap_begin_s"])),
        "| Minimum tested stable point | {} |".format(format_ps(intervals["T_edge_min_tested_stable_s"])),
        "| First tested unstable point | {} |".format(format_ps(intervals["T_edge_first_unstable_s"])),
        "| Recommended next-stage point | {} |".format(format_ps(intervals["T_edge_recommended_for_next_stage_s"])),
        "",
        "## Final Decision",
        "",
        "**{}**".format(decision),
    ])
    if decision == "GO":
        lines.append("A common three-anchor overlapping interval and repeatable eight-edge rise/fall state were measured. A separate later task may evaluate real capture architecture and transient coverage.")
    elif decision == "CONDITIONAL":
        lines.append("Only rise-probe/recovery-edge repetition is supported; this is not a full dual-edge pipelined-wavefront FTC claim.")
    else:
        lines.append("The measured prerequisites did not establish a common stable overlapping pipeline region. No complex multi-window decoder or pipeline-control workaround was added.")
    (FTC_ROOT / "reports" / "FTC_PIPELINED_WAVEFRONT_PHYSICAL_FEASIBILITY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_wavefront_summarize(args: argparse.Namespace) -> None:
    """Collect staged evidence into the sole final physical-feasibility decision."""

    root = args.output_dir.resolve()
    falling = read_wavefront_summary(root, "falling", "isolated_falling_edge_summary.json")
    nominal = optional_wavefront_summary(root, "two_edge_nominal", "two_edge_nominal_summary.json")
    anchor = optional_wavefront_summary(root, "two_edge_anchor", "two_edge_anchor_summary.json")
    eight = optional_wavefront_summary(root, "eight_edge", "eight_edge_pipeline_summary.json")
    decision = decide_wavefront_result(falling, nominal, anchor, eight)
    intervals = tested_interval_summary(nominal, anchor, eight)
    summary = {
        "decision": decision,
        "falling_classification": falling.get("classification"),
        "two_edge_nominal_status": nominal.get("status") if nominal is not None else "not_run",
        "two_edge_anchor_status": anchor.get("status") if anchor is not None else "not_run",
        "eight_edge_status": eight.get("status") if eight is not None else "not_run",
        "intervals": intervals,
    }
    write_wavefront_summary(root / "physical_interval_summary.json", summary)
    render_wavefront_report(root, falling, nominal, anchor, eight, intervals, decision)


def run_pipelined_wavefront(args: argparse.Namespace, config: Dict[str, Any], cells: Dict[str, Any]) -> None:
    """Dispatch one gated wavefront experiment step; no step silently runs another."""

    if args.wavefront_config is None or args.wavefront_step is None:
        raise ValueError("pipelined-wavefront requires --wavefront-config and --wavefront-step")
    settings = load_wavefront_settings(args.wavefront_config, config)
    if args.wavefront_step == "falling":
        run_wavefront_falling(args, config, cells, settings)
    elif args.wavefront_step == "two-edge-nominal":
        run_wavefront_two_edge_nominal(args, config, cells, settings)
    elif args.wavefront_step == "two-edge-anchor":
        run_wavefront_two_edge_anchor(args, config, cells, settings)
    elif args.wavefront_step == "eight-edge":
        run_wavefront_eight_edge(args, config, cells, settings)
    else:
        run_wavefront_summarize(args)


def main(argv: Iterable[str] = None) -> int:
    """Dispatch only explicitly named FTC characterization stages."""

    parser = argparse.ArgumentParser(description="run standalone FTC physical characterizations")
    parser.add_argument("stage", choices=(
        "mechanism-search", "mechanism-coarse", "xor-loading", "capture-phase",
        "integrated-coarse", "fine", "phase-sensitivity", "glitch", "glitch-summary",
        "phase-diverse-static", "phase-diverse-jitter", "phase-diverse-glitch", "pipelined-wavefront",
    ))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--phase-diverse-config", type=Path, help="task-local phase-diversity configuration")
    parser.add_argument("--wavefront-config", type=Path, help="task-local finite edge-train configuration")
    parser.add_argument("--wavefront-step", choices=("falling", "two-edge-nominal", "two-edge-anchor", "eight-edge", "summarize"), help="one gated pipelined-wavefront physical step")
    parser.add_argument("--screen", choices=("anchor", "coarse"), help="phase-diverse static screen to execute")
    parser.add_argument("--phase-ids", help="comma-separated explicit phase IDs; omitted means every configured candidate")
    parser.add_argument("--glitch-case-ids", help="comma-separated bounded glitch family IDs")
    parser.add_argument("--baseline-path", type=Path, help="phase-specific nominal baseline JSON for glitch scoring")
    parser.add_argument("--onsets-s", help="comma-separated relative onset times for local boundary refinement")
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
    elif args.stage == "phase-diverse-static":
        if args.phase_diverse_config is None or args.screen is None:
            parser.error("phase-diverse-static requires --phase-diverse-config and --screen")
        run_phase_diverse_static(args, config, cells)
    elif args.stage == "phase-diverse-jitter":
        if args.phase_diverse_config is None:
            parser.error("phase-diverse-jitter requires --phase-diverse-config")
        run_phase_diverse_jitter(args, config, cells)
    elif args.stage == "phase-diverse-glitch":
        if args.phase_diverse_config is None or args.glitch_case_ids is None or args.baseline_path is None:
            parser.error("phase-diverse-glitch requires --phase-diverse-config, --glitch-case-ids, and --baseline-path")
        run_phase_diverse_glitch(args, config, cells)
    elif args.stage == "pipelined-wavefront":
        try:
            run_pipelined_wavefront(args, config, cells)
        except ValueError as error:
            parser.error(str(error))
    else: summarize_glitch_csv(args.output_dir.resolve(), str(selected_operating_point(config)["nominal_captured_xor_word"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
