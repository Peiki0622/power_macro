#!/usr/bin/env python3
"""Collect repeated real-DFF nominal samples for every configured CAL_SEL tap."""

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PHASE1_SCRIPTS = REPOSITORY_ROOT / "power_macro" / "delay_chain" / "phase1" / "scripts"
SCRIPT_DIR = Path(__file__).resolve().parent
for import_path in (PHASE1_SCRIPTS, SCRIPT_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))
import run_dc_sweep  # noqa: E402  # HSPICE listing and measure parser are shared evidence rules.
import run_dff_sweep  # noqa: E402  # Reuse the real DFF topology and raw-bit decoder.


def load_json(path: Path) -> Dict[str, Any]:
    """Load one JSON object and reject malformed simulation provenance."""

    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def resolve_repo_path(value: str) -> Path:
    """Resolve inherited Phase 1 paths independently of caller working directory."""

    path = Path(value)
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def candidate_for_tap(m_stages: int, dummy_load_count: int, cal_sel: int, offset_s: float) -> Dict[str, Any]:
    """Describe one physical calibration setting with an explicit PULSE offset.

    This is the Phase-2 pre-layout representation of one eventual CAL_SEL
    setting.  It exercises the actual sense/reference/DFF cell topology; only
    the programmable delay source remains ideal while the library MUX/tap RTL
    interface is prepared separately.
    """

    return {
        "candidate_id": "m{:02d}_d{}_cal_sel_{:03d}".format(m_stages, dummy_load_count, cal_sel),
        "m_stages": m_stages,
        "dummy_load_count": dummy_load_count,
        "launch_offset_s": offset_s,
    }


def load_completed(
    config: Dict[str, Any], output_dir: Path, candidate: Dict[str, Any], sample_index: int
) -> Dict[str, Any]:
    """Rebuild a completed row from HSPICE artifacts for resumable long sweeps."""

    point_dir = output_dir / "scenarios" / run_dff_sweep.scenario_name(candidate, "sample_{:02d}".format(sample_index))
    warning_count = run_dc_sweep.validate_listing(point_dir / "vernier_dff.lis")
    measurement_path = run_dc_sweep.find_measurement_file(point_dir, "vernier_dff")
    measurements = run_dc_sweep.parse_measurements(measurement_path)
    m_stages = int(candidate["m_stages"])
    run_dff_sweep.require_measurements(measurements, m_stages)
    decoded = run_dff_sweep.parse_bits(
        measurements,
        m_stages,
        float(config["vdd_ref_v"]),
        float(candidate["launch_offset_s"]),
        float(config["measurement_timing"]["dff_metastability_margin_s"]),
    )
    decoded.update(
        {
            "scenario_id": run_dff_sweep.scenario_name(candidate, "sample_{:02d}".format(sample_index)),
            "candidate_id": candidate["candidate_id"],
            "scenario_label": "nominal_calibration",
            "vdd_a_v": float(config["vnom_v"]),
            "vdd_ref_v": float(config["vdd_ref_v"]),
            "m_stages": m_stages,
            "dummy_load_count": int(candidate["dummy_load_count"]),
            "launch_offset_s": float(candidate["launch_offset_s"]),
            "comparator_avg_current_a": measurements["comparator_ref_avg_current_a"],
            "comparator_peak_current_a": measurements["comparator_ref_peak_current_a"],
            "warning_count": warning_count,
            "measurement_file": str(measurement_path.relative_to(output_dir)),
        }
    )
    return decoded


def restart_if_incomplete(point_dir: Path) -> None:
    """Delete only a runner-owned interrupted point lacking a nonempty listing."""

    listing = point_dir / "vernier_dff.lis"
    if listing.is_file() and listing.stat().st_size > 0:
        raise RuntimeError("refusing to discard nonempty DFF listing: {}".format(point_dir))
    shutil.rmtree(point_dir)


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Write raw repeated-sample evidence with CAL_SEL and sample-index labels."""

    fields = [
        "scenario_id", "candidate_id", "cal_sel", "sample_index", "vdd_a_v", "vdd_ref_v", "m_stages",
        "dummy_load_count", "launch_offset_s", "raw_code", "expected_arrival_code", "sensor_code", "bubble_count",
        "raw_code_valid", "mismatch_count", "reset_failure_count", "metastability_risk_count", "measurement_file",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            rendered = {}
            for field in fields:
                value = row[field]
                rendered[field] = "" if value is None else "{:.12e}".format(value) if isinstance(value, float) else str(value)
            writer.writerow(rendered)


def build_argument_parser() -> argparse.ArgumentParser:
    """Expose the calibration topology and exact repeat count as explicit inputs."""

    parser = argparse.ArgumentParser(description="run repeated real-DFF CAL_SEL calibration sweep")
    parser.add_argument("--config", required=True, type=Path, help="Phase 2 configuration")
    parser.add_argument("--output-dir", required=True, type=Path, help="new or resumable task-owned directory")
    parser.add_argument("--m-stages", type=int, default=32, help="chosen DFF candidate stage count")
    parser.add_argument("--dummy-load-count", type=int, default=1, help="chosen reference dummy count")
    parser.add_argument("--sample-count", type=int, required=True, help="independent nominal samples per CAL_SEL")
    parser.add_argument("--timeout-s", type=int, default=180, help="per-deck HSPICE timeout")
    parser.add_argument("--resume", action="store_true", help="resume only compatible completed point directories")
    return parser


def main(argv: Iterable[str] = None) -> int:
    """Run every tap/sample pair; only complete raw evidence receives a CSV."""

    args = build_argument_parser().parse_args(argv)
    config = load_json(args.config)
    offsets = [float(value) for value in config["calibration_launch_offsets_s"]]
    if args.sample_count <= 0:
        raise ValueError("sample_count must be positive")
    phase1 = load_json(resolve_repo_path(str(config["phase1_config_path"])))
    hspice = run_dc_sweep.require_regular_file(Path(phase1["hspice"]), "HSPICE", executable=True)
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and not args.resume:
        raise ValueError("refusing to overwrite calibration run: {}".format(output_dir))
    if args.resume and not output_dir.is_dir():
        raise ValueError("--resume requires an existing calibration directory")
    output_dir.mkdir(parents=True, exist_ok=args.resume)
    manifest = {"m_stages": args.m_stages, "dummy_load_count": args.dummy_load_count, "sample_count": args.sample_count, "tap_count": len(offsets)}
    manifest_path = output_dir / "manifest.json"
    if args.resume:
        if load_json(manifest_path) != manifest:
            raise ValueError("calibration resume manifest mismatch")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = []
    for cal_sel, offset_s in enumerate(offsets):
        candidate = candidate_for_tap(args.m_stages, args.dummy_load_count, cal_sel, offset_s)
        for sample_index in range(args.sample_count):
            point_dir = output_dir / "scenarios" / run_dff_sweep.scenario_name(candidate, "sample_{:02d}".format(sample_index))
            if point_dir.exists():
                try:
                    row = load_completed(config, output_dir, candidate, sample_index)
                except ValueError:
                    restart_if_incomplete(point_dir)
                    row = run_dff_sweep.run_scenario(
                        config, hspice, output_dir, candidate, {"label": "sample_{:02d}".format(sample_index), "vdd_a_v": float(config["vnom_v"])}, args.timeout_s
                    )
            else:
                row = run_dff_sweep.run_scenario(
                    config, hspice, output_dir, candidate, {"label": "sample_{:02d}".format(sample_index), "vdd_a_v": float(config["vnom_v"])}, args.timeout_s
                )
            row["cal_sel"] = cal_sel
            row["sample_index"] = sample_index
            rows.append(row)
    write_csv(output_dir / "calibration_raw_metrics.csv", rows)
    (output_dir / "completion.rpt").write_text("status=PASS\nscenario_count={}\n".format(len(rows)), encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
