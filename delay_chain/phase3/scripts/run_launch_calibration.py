#!/usr/bin/env python3
"""Select a physical same-rail CAL_SEL value with eight real DFF runs.

This Step-7 runner never applies a source-time delay.  Each scenario instead
instantiates the selected standard-cell BUF/MXT2 calibration topology from the
deck renderer and obtains its thermometer word from the real DFF Q nodes.
"""

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
PHASE1_CONFIG = WORKSPACE_ROOT / "power_macro/delay_chain/phase1/phase1_config.json"
PHASE1_SCRIPTS = WORKSPACE_ROOT / "power_macro/delay_chain/phase1/scripts"
PHASE2_SCRIPTS = WORKSPACE_ROOT / "power_macro/delay_chain/phase2_vernier/scripts"
PHASE3_SCRIPTS = Path(__file__).resolve().parent
EMPTY_SUBCKT_INCLUDE = WORKSPACE_ROOT / "power_macro/delay_chain/phase3/spice/includes/empty_subckt.sp_cal"
for import_path in (PHASE1_SCRIPTS, PHASE2_SCRIPTS, PHASE3_SCRIPTS):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))
import decode_vernier_code  # noqa: E402  # Shared Phase-3 decoder contract.
import generate_phase3_deck  # noqa: E402  # Physical BUF/MXT2/DFF deck renderer.
import run_dc_sweep  # noqa: E402  # Reviewed HSPICE output validation.


CSV_FIELDS = [
    "cal_sel", "vdd_v", "raw_thermometer_word", "normalized_raw_word",
    "corrected_thermometer_word", "sensor_code", "raw_bubble_count", "bubble_count",
    "code_valid", "reset_failure_count", "measurement_file",
    "rvt_launch_cross_s", "companion_launch_cross_s", "launch_d_minus_ck_s",
    "ck_000_cross_s", "d_000_cross_s", "d_minus_ck_000_s",
    "ck_007_cross_s", "d_007_cross_s", "d_minus_ck_007_s",
    "ck_015_cross_s", "d_015_cross_s", "d_minus_ck_015_s",
    "ck_023_cross_s", "d_023_cross_s", "d_minus_ck_023_s",
    "ck_031_cross_s", "d_031_cross_s", "d_minus_ck_031_s",
]


TIMING_PROBE_STAGES = (0, 7, 15, 23, 31)


def load_json(path: Path) -> Dict[str, Any]:
    """Read one required JSON object without silently supplying defaults."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def normalize_word(raw_word: str, invert: bool) -> str:
    """Apply the Step-5 raw bit direction before the standard decoder."""

    return "".join("1" if bit == "0" else "0" for bit in raw_word) if invert else raw_word


def run_cal_sel(
    config: Dict[str, Any], selected: Dict[str, Any], phase1: Dict[str, Any], hspice: Path,
    output_dir: Path, cal_sel: int, timeout_s: int, active_mask: Optional[int] = None,
    q_read_time_ns: float = 2.5, stop_time_ns: float = 4.0,
    launch_balance_load_count: int = 2, timing_debug: bool = False,
    rvt_launch_load_count: int = 0,
) -> Dict[str, Any]:
    """Simulate one static CAL_SEL value at nominal VDD with all 32 DFFs."""

    point_dir = output_dir / "scenarios" / "cal_sel_{:03b}".format(cal_sel)
    point_dir.mkdir(parents=True, exist_ok=False)
    # Preserve the installed LVT CDL's relative include requirement in the
    # task-owned scenario directory.  The PDK itself remains untouched.
    if not EMPTY_SUBCKT_INCLUDE.is_file():
        raise ValueError("missing Phase-3 empty_subckt.sp_cal placeholder")
    shutil.copyfile(EMPTY_SUBCKT_INCLUDE, point_dir / "empty_subckt.sp_cal")
    deck_path = point_dir / "phase3_launch_calibration.sp"
    generate_phase3_deck.write_real_dff_vernier_deck(
        output_path=deck_path,
        rvt_cdl=Path(selected["source_files"]["rvt_cdl"]),
        lvt_cdl=Path(selected["source_files"]["lvt_cdl"]),
        model_library=Path(phase1["model_library"]),
        corner=str(config["corner"]), temperature_c=float(config["temperature_c"]),
        vdd_v=float(config["vnom_v"]), rvt_cell=str(config["rvt_inverter_cell"]),
        lvt_cell=str(config["selected_lvt_cell"]), dff_cell=str(config["rvt_dff_cell"]),
        stages=int(config["stages"]), lvt_dummy_load_count=int(config["selected_dummy_load_count"]),
        launch_offset_ps=0.0, launch_delayed_path=str(config["ideal_launch_delayed_path"]),
        cal_sel=cal_sel, buffer_cell=str(config["rvt_buffer_cell"]), mux_cell=str(config["rvt_mux_cell"]),
        active_stage_mask=active_mask, q_read_time_ns=q_read_time_ns, stop_time_ns=stop_time_ns,
        launch_balance_load_count=launch_balance_load_count,
        rvt_launch_load_count=rvt_launch_load_count,
        timing_probe_stages=list(TIMING_PROBE_STAGES) if timing_debug else None,
    )
    result = subprocess.run(
        [str(hspice), deck_path.name, "-o", "phase3_launch_calibration"], cwd=str(point_dir),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
        check=False, timeout=timeout_s,
    )
    (point_dir / "hspice_command.log").write_text(
        "command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            " ".join([str(hspice), deck_path.name, "-o", "phase3_launch_calibration"]),
            result.returncode, result.stdout, result.stderr,
        ), encoding="utf-8"
    )
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {} for {}".format(result.returncode, point_dir))
    run_dc_sweep.validate_listing(point_dir / "phase3_launch_calibration.lis")
    measurement = run_dc_sweep.find_measurement_file(point_dir, "phase3_launch_calibration")
    values = run_dc_sweep.parse_measurements(measurement)
    raw_bits: List[str] = []
    reset_failures = 0
    vdd_v = float(config["vnom_v"])
    for index in range(int(config["stages"])):
        reset_level = values.get("q_{:03d}_reset_level".format(index))
        q_level = values.get("q_{:03d}_level".format(index))
        if reset_level is None or q_level is None:
            raise ValueError("missing DFF level measurement for stage {:03d}".format(index))
        if float(reset_level) > 0.1 * vdd_v:
            reset_failures += 1
        raw_bits.append("1" if float(q_level) >= 0.5 * vdd_v else "0")
    raw_word = "".join(raw_bits)
    decoded = decode_vernier_code.decode_word(normalize_word(raw_word, bool(config["thermometer_invert"])))
    row = {
        "cal_sel": cal_sel,
        "vdd_v": vdd_v,
        "raw_thermometer_word": raw_word,
        "normalized_raw_word": decoded["raw_code"],
        "corrected_thermometer_word": decoded["corrected_code"],
        "sensor_code": int(decoded["sensor_code"]),
        "raw_bubble_count": int(decoded["raw_bubble_count"]),
        "bubble_count": int(decoded["bubble_count"]),
        "code_valid": int(bool(decoded["code_valid"])),
        "reset_failure_count": reset_failures,
        "measurement_file": str(measurement.relative_to(output_dir)),
    }
    # Keep the compact CSV schema stable for ordinary calibration while making
    # every debug column explicit.  Empty values are intentional when probes
    # were not requested; a requested probe must exist or the run is invalid.
    for name in ("rvt_launch_cross", "companion_launch_cross", "launch_d_minus_ck"):
        value = values.get(name)
        if timing_debug and value is None:
            raise ValueError("missing requested calibration timing measurement: {}".format(name))
        row[name + "_s"] = float(value) if value is not None else ""
    for index in TIMING_PROBE_STAGES:
        for prefix in ("ck", "d", "d_minus_ck"):
            name = "{}_{:03d}_cross".format(prefix, index) if prefix != "d_minus_ck" else "d_minus_ck_{:03d}".format(index)
            value = values.get(name)
            if timing_debug and value is None:
                raise ValueError("missing requested calibration timing measurement: {}".format(name))
            row[(name + "_s") if prefix != "d_minus_ck" else (name + "_s")] = float(value) if value is not None else ""
    return row


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Write one compact record for every physical CAL_SEL option."""

    with path.open("w", newline="", encoding="utf-8") as stream:
        # Use LF explicitly so compact evidence is stable on every host and
        # does not create a whole-file CRLF diff when it is committed.
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in CSV_FIELDS})


def select_nominal_calibration(
    rows: List[Dict[str, Any]], minimum: int, maximum: int, target: int,
) -> Dict[str, Any]:
    """Classify measured CAL rows without changing configuration state.

    Keeping this policy pure makes the endpoint-safety rule independently
    testable: callers get either a real ``selected`` row or only a clearly
    named diagnostic row.  No HSPICE path, filesystem write, or wide-range
    compatibility exception belongs in this decision routine.
    """

    valid = [row for row in rows if row["code_valid"] and row["reset_failure_count"] == 0]
    acceptable = [row for row in valid if minimum <= row["sensor_code"] <= maximum]
    rank = lambda row: (abs(row["sensor_code"] - target), row["sensor_code"], row["cal_sel"])
    if not acceptable:
        return {
            "status": "FAIL",
            "reason": "no_nominal_center_setting",
            "nearest_valid_diagnostic": sorted(valid, key=rank)[0] if valid else None,
        }
    return {"status": "PASS", "selected": sorted(acceptable, key=rank)[0]}


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run all eight settings, choose the nearest legal nominal center code, and update configuration."""

    parser = argparse.ArgumentParser(description="run Phase-3 physical same-rail launch calibration")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout-s", type=int, default=300)
    parser.add_argument("--wide-range", action="store_true")
    parser.add_argument("--active-stage-count", type=int)
    parser.add_argument(
        "--active-stage-mask", type=lambda value: int(value, 0),
        help="static sparse mask for a measured placement experiment; mutually exclusive with --active-stage-count",
    )
    parser.add_argument("--launch-balance-load-count", type=int, choices=(0, 1, 2), default=2)
    parser.add_argument("--rvt-launch-load-count", type=int, choices=range(8), default=0)
    parser.add_argument("--timing-debug", action="store_true")
    parser.add_argument(
        "--cal-sels", type=int, nargs="+", choices=range(8),
        help="run a diagnostic subset; omit only for the required complete eight-setting calibration",
    )
    args = parser.parse_args(argv)
    config = load_json(args.config)
    selected = load_json(WORKSPACE_ROOT / "power_macro/delay_chain/phase3/discovery/selected_cells.json")
    phase1 = load_json(PHASE1_CONFIG)
    hspice = run_dc_sweep.require_regular_file(Path("/home/zhupl25/.local/bin/hspice"), "HSPICE", executable=True)
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise ValueError("refusing to overwrite launch-calibration run directory")
    output_dir.mkdir(parents=True)
    if args.active_stage_count is not None and not args.wide_range:
        raise ValueError("--active-stage-count requires --wide-range")
    if args.active_stage_mask is not None and not args.wide_range:
        raise ValueError("--active-stage-mask requires --wide-range")
    if args.active_stage_count is not None and args.active_stage_mask is not None:
        raise ValueError("choose only one of --active-stage-count and --active-stage-mask")
    active_mask = args.active_stage_mask
    if args.active_stage_count is not None:
        active_mask = generate_phase3_deck.active_stage_mask(int(config["stages"]), args.active_stage_count)
    if active_mask is not None and (active_mask < 0 or active_mask >= (1 << int(config["stages"]))):
        raise ValueError("--active-stage-mask must fit the Phase-3 stage count")
    read_ns = float(config.get("wide_range", {}).get("characterization_read_time_ns", 2.5)) if args.wide_range else 2.5
    stop_ns = float(config.get("wide_range", {}).get("characterization_stop_time_ns", 4.0)) if args.wide_range else 4.0
    cal_sels = list(range(8)) if args.cal_sels is None else list(args.cal_sels)
    if len(set(cal_sels)) != len(cal_sels):
        raise ValueError("--cal-sels must not repeat a physical setting")
    rows = [
        run_cal_sel(
            config, selected, phase1, hspice, output_dir, cal_sel, args.timeout_s,
            active_mask, read_ns, stop_ns, args.launch_balance_load_count,
            args.timing_debug, args.rvt_launch_load_count,
        )
        for cal_sel in cal_sels
    ]
    write_csv(output_dir / "calibration.csv", rows)
    wide = config.get("wide_range", {})
    minimum = int(wide.get("acceptable_nominal_code_min", 14)) if args.wide_range else 14
    maximum = int(wide.get("acceptable_nominal_code_max", 18)) if args.wide_range else 18
    target = int(wide.get("target_nominal_code", config["target_nominal_code"])) if args.wide_range else int(config["target_nominal_code"])
    (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "study": "phase3_launch_calibration",
                "wide_range": bool(args.wide_range),
                "active_stage_mask": active_mask,
                "launch_balance_load_count": args.launch_balance_load_count,
                "rvt_launch_load_count": args.rvt_launch_load_count,
                "timing_probe_stages": list(TIMING_PROBE_STAGES) if args.timing_debug else [],
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    decision = select_nominal_calibration(rows, minimum, maximum, target)
    if decision["status"] != "PASS":
        # All eight physical observations are already in calibration.csv.  The
        # JSON deliberately keeps a *diagnostic* nearest endpoint so an
        # engineer can see the closest measured setting, but it must never be
        # published as a selected calibration or turn this failed run into a
        # success.  In particular, wide-range calibration may not fall back
        # to CAL_SEL=0/code=0 merely because that thermometer word is legal.
        (output_dir / "calibration_selection.json").write_text(
            json.dumps(
                {
                    "status": "FAIL",
                    "reason": "no_nominal_center_setting",
                    "target_nominal_code": target,
                    "acceptable_nominal_code_min": minimum,
                    "acceptable_nominal_code_max": maximum,
                    "nearest_valid_diagnostic": decision["nearest_valid_diagnostic"],
                    "all_rows": rows,
                },
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        (output_dir / "completion.rpt").write_text("status=FAIL\nreason=no_nominal_center_setting\n", encoding="ascii")
        return 2
    chosen = decision["selected"]
    if not args.wide_range:
        config.update({"selected_cal_sel": chosen["cal_sel"], "baseline_code": chosen["sensor_code"]})
        args.config.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "calibration_selection.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "target_nominal_code": target,
                "acceptable_nominal_code_min": minimum,
                "acceptable_nominal_code_max": maximum,
                "selected": chosen,
                "all_rows": rows,
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    (output_dir / "completion.rpt").write_text("status=PASS\nselected_cal_sel={}\nbaseline_code={}\n".format(chosen["cal_sel"], chosen["sensor_code"]), encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
