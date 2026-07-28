#!/usr/bin/env python3
"""Execute, extract, verify, and compact one real-DFF TCN trace.

This runner has a deliberately narrow ownership boundary.  Its `attempt_dir`
contains every generated HSPICE product, while `compact_dir` receives only
verified CSV/JSON assets.  Raw products are never deleted until the compact
assets have been atomically published and checksummed by the batch worker.
"""

from __future__ import print_function

import csv
import hashlib
import json
import math
import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PHASE1_SCRIPTS = ROOT / "power_macro" / "delay_chain" / "phase1" / "scripts"
PHASE2_SCRIPTS = ROOT / "power_macro" / "delay_chain" / "phase2_vernier" / "scripts"
LOCAL_SPICE = Path(__file__).resolve().parent
for directory in (PHASE1_SCRIPTS, PHASE2_SCRIPTS, LOCAL_SPICE):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
import decode_vernier_code  # noqa: E402
import run_dc_sweep  # noqa: E402
import run_dff_sweep  # noqa: E402
import generate_dataset_deck  # noqa: E402
import stream_tr0  # noqa: E402


CSV_FIELDS = [
    "trace_id", "base_waveform_id", "waveform_family_id", "split", "hard_pair_id", "sample_index", "sample_time_s",
    "configured_droop_mv", "configured_vdd_a_v", "measured_vdd_a_v", "measured_droop_mv", "vdd_ref_v",
    "raw_code", "corrected_code", "sensor_code", "raw_bubble_count", "bubble_count",
    "raw_transition_count", "transition_count", "code_valid", "sample_done", "expected_arrival_code",
    "mismatch_count", "reset_failure_count", "metastability_risk_count", "quality"
]


def sha256_file(path):
    """Hash one published compact artifact in bounded memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path):
    """Load a trace request or execution configuration object."""

    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def require_local_hspice(execution):
    """Enforce the user-selected local executable and expected release string."""

    path = Path(execution["hspice_executable"]).resolve()
    if str(path) != "/home/zhupl25/.local/bin/hspice" or not path.is_file():
        raise RuntimeError("dataset execution requires the local HSPICE path, found {}".format(path))
    version = run_dc_sweep.hspice_version(path)
    if execution["required_hspice_version"] not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    return path, version


def read_measurement_rows(measurements, trace, sample_times):
    """Join real DFF measures with streamed rail samples for all 500 frames.

    Comparator-port evidence is reconstructed through the existing Phase-2
    `run_dff_sweep.parse_bits` implementation.  It preserves the established
    semantics: D is `sense_i`, CK is `ref_i`, reset is measured before launch,
    and thermometer correction is delegated to the shared decoder.
    """

    rails = stream_tr0.sample_rails(trace, sample_times)
    if len(rails["samples"]) != 500:
        raise ValueError("streamed .tr0 did not return 500 rail samples")
    rows = []
    for sample_index in range(500):
        per_capture = {}
        for stage_index in range(32):
            # The measurement namespace is frame-first only in the generated
            # deck.  These assignments deliberately adapt names for the
            # reviewed parser without changing numerical values or deciding
            # any bit in Python.
            per_capture["sense_{:03d}_cross".format(stage_index)] = measurements.get("sense_{:03d}_cross_{:03d}".format(sample_index, stage_index))
            per_capture["ref_{:03d}_cross".format(stage_index)] = measurements.get("ref_{:03d}_cross_{:03d}".format(sample_index, stage_index))
            per_capture["q_{:03d}_reset_level".format(stage_index)] = measurements.get("q_{:03d}_reset_level_{:03d}".format(sample_index, stage_index))
            per_capture["q_{:03d}_level".format(stage_index)] = measurements.get("q_{:03d}_level_{:03d}".format(sample_index, stage_index))
        if any(value is None for value in per_capture.values()):
            raise ValueError("frame {} lacks real DFF measurement evidence".format(sample_index))
        electrical = run_dff_sweep.parse_bits(per_capture, 32, 1.1, 20.0e-12, 2.0e-12)
        decoded = decode_vernier_code.decode_word(electrical["raw_code"])
        measured_a = measurements.get("sample_{:03d}_a_vdd".format(sample_index))
        measured_ref = measurements.get("sample_{:03d}_vdd_ref".format(sample_index))
        if measured_a is None or measured_ref is None:
            raise ValueError("frame {} lacks rail measure".format(sample_index))
        stream_sample = rails["samples"][sample_index]
        if abs(float(measured_a) - stream_sample["a_vdd_v"]) > 2.0e-4:
            raise ValueError("frame {} .mt0/.tr0 VDD_A disagreement".format(sample_index))
        if abs(float(measured_ref) - stream_sample["vdd_ref_v"]) > 2.0e-4:
            raise ValueError("frame {} .mt0/.tr0 VDD_REF disagreement".format(sample_index))
        quality = "VALID"
        if int(electrical["reset_failure_count"]):
            quality = "INVALID_RESET"
        elif not bool(decoded["code_valid"]):
            quality = "INVALID_THERMOMETER"
        elif int(electrical["metastability_risk_count"]):
            quality = "VALID_WITH_EDGE_RISK"
        row = {"sample_index": sample_index, "sample_time_s": sample_times[sample_index], "measured_vdd_a_v": float(measured_a),
               "vdd_ref_v": float(measured_ref), "measured_droop_mv": (1.1 - float(measured_a)) * 1.0e3,
               "expected_arrival_code": electrical["expected_arrival_code"], "mismatch_count": electrical["mismatch_count"],
               "reset_failure_count": electrical["reset_failure_count"], "metastability_risk_count": electrical["metastability_risk_count"],
               "quality": quality, "sample_done": True}
        row.update(decoded)
        rows.append(row)
    return rows, rails


def write_csv(path, rows):
    """Write one compact electrical trace while preserving every DFF field."""

    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in CSV_FIELDS})


def execute(trace_path, phase2_config_path, execution_path, attempt_dir, compact_dir, timeout_s):
    """Run one task-private electrical attempt and publish verified compact data."""

    trace = load_json(trace_path)
    execution = load_json(execution_path)
    hspice, version = require_local_hspice(execution)
    attempt_dir.mkdir(parents=True, exist_ok=False)
    compact_dir.mkdir(parents=True, exist_ok=True)
    deck_path = attempt_dir / "trace.sp"
    metadata = generate_dataset_deck.write(trace_path, phase2_config_path, deck_path)
    result = subprocess.run([str(hspice), deck_path.name, "-o", "trace"], cwd=str(attempt_dir), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=timeout_s)
    (attempt_dir / "hspice_command.log").write_text("command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
        " ".join([str(hspice), deck_path.name, "-o", "trace"]), result.returncode, result.stdout, result.stderr), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError("HSPICE returned {}".format(result.returncode))
    warning_count = run_dc_sweep.validate_listing(attempt_dir / "trace.lis")
    measures = run_dc_sweep.parse_measurements(run_dc_sweep.find_measurement_file(attempt_dir, "trace"))
    sample_times = [index * 4.0e-9 + 2.5e-9 for index in range(500)]
    rows, rail_summary = read_measurement_rows(measures, attempt_dir / "trace.tr0", sample_times)
    if any(row["quality"] not in ("VALID", "VALID_WITH_EDGE_RISK") for row in rows):
        raise RuntimeError("trace contains invalid reset or thermometer captures")
    for row in rows:
        row.update({"trace_id": trace["trace_id"], "base_waveform_id": trace["base_waveform_id"], "waveform_family_id": trace["waveform_family_id"],
                    "split": trace["split"], "hard_pair_id": trace.get("hard_pair_id", ""),
                    "configured_droop_mv": trace["target_droop_mv"][row["sample_index"]],
                    "configured_vdd_a_v": 1.1 - trace["target_droop_mv"][row["sample_index"]] * 1.0e-3})
        # This is separate from the .mt0/.tr0 consistency check above: both
        # HSPICE outputs could agree while the generated PWL itself were
        # wrong.  The 0.1 mV bound is the completed Phase-2 direct-rail
        # contract and detects that distinct failure before data publication.
        if abs(float(row["measured_vdd_a_v"]) - float(row["configured_vdd_a_v"])) > 1.0e-4:
            raise RuntimeError("frame {} measured VDD_A differs from configured PWL".format(row["sample_index"]))
    csv_temp = compact_dir / (trace["trace_id"] + ".csv.tmp")
    csv_final = compact_dir / (trace["trace_id"] + ".csv")
    write_csv(csv_temp, rows)
    csv_temp.replace(csv_final)
    manifest = {"trace_id": trace["trace_id"], "base_waveform_id": trace["base_waveform_id"], "hspice": {"path": str(hspice), "version": version},
                "deck_metadata": metadata, "warning_count": warning_count, "rail_summary": rail_summary,
                "capture_count": len(rows), "compact_csv": csv_final.name, "compact_csv_sha256": sha256_file(csv_final)}
    manifest_temp = compact_dir / (trace["trace_id"] + ".json.tmp")
    manifest_final = compact_dir / (trace["trace_id"] + ".json")
    manifest_temp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_temp.replace(manifest_final)
    return {"csv": csv_final, "manifest": manifest_final, "raw_files": [path for path in attempt_dir.iterdir() if path.is_file()]}


def main():
    """Expose a task-local command so tmux does not need nested shell quoting."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--phase2-config", required=True, type=Path)
    parser.add_argument("--execution-config", required=True, type=Path)
    parser.add_argument("--attempt-dir", required=True, type=Path)
    parser.add_argument("--compact-dir", required=True, type=Path)
    parser.add_argument("--timeout-s", required=True, type=int)
    args = parser.parse_args()
    result = execute(args.trace, args.phase2_config, args.execution_config, args.attempt_dir, args.compact_dir, args.timeout_s)
    print(json.dumps({"csv": str(result["csv"]), "manifest": str(result["manifest"])}, sort_keys=True))


if __name__ == "__main__":
    main()
