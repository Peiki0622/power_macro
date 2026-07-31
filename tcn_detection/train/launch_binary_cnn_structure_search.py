#!/usr/bin/env python3
"""Launch the fixed validation-only binary CNN structure search."""

from __future__ import print_function

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from power_macro.tcn_detection.train.common import (
    build_classifier, estimate_macs, parameter_count)
from power_macro.tcn_detection.train.train_binary_classifier import (
    validate_binary_model_config)


def sha256_file(path):
    """Return a bounded-memory digest for one search input."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now():
    """Return an explicit UTC timestamp for the process manifest."""

    return datetime.now(timezone.utc).isoformat()


def write_json_atomic(path, payload):
    """Publish manifest state without exposing a partially written JSON file."""

    temporary = Path(path).with_suffix(Path(path).suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def build_jobs(contract, config_dir, windows, output_dir, python_executable):
    """Build exactly six structures x three seeds after complexity preflight.

    Architecture, receptive-field claim, training parameters, seeds, and L32
    windows are all fixed by the versioned contract.  Each config is actually
    instantiated here: this catches invalid shapes and computes complexity
    before a long-running child can create misleading partial evidence.
    """

    if (contract.get("scope") != "train_validation_only"
            or contract.get("task") != "safe_critical_binary"
            or contract.get("model") != "cnn"
            or int(contract.get("window_length", -1)) != 32
            or contract.get("seeds") != [20260725, 20260726, 20260727]
            or contract.get("iid_policy") != {
                "features_loaded": False, "metrics_computed": False,
                "selection_allowed": False}):
        raise ValueError("structure search violates the validation-only contract")
    candidates = contract.get("candidates", [])
    if len(candidates) != 6 or len({item.get("name") for item in candidates}) != 6:
        raise ValueError("structure search requires six unique candidates")
    training_config = config_dir / contract["training_config"]
    if not training_config.is_file():
        raise ValueError("missing tuned CNN training config")
    tcn = contract["tcn_comparison"]
    jobs = []
    for candidate in candidates:
        model_config_path = config_dir / candidate["model_config"]
        model_config = json.loads(model_config_path.read_text(encoding="utf-8"))
        validate_binary_model_config("cnn", model_config)
        model = build_classifier("cnn", model_config)
        parameters = parameter_count(model)
        macs = estimate_macs(model, 32, model_config["input_channels"])
        if (parameters >= int(tcn["parameter_count"])
                or macs >= int(tcn["estimated_macs_per_window"])):
            raise ValueError("CNN candidate is not strictly cheaper than TCN: {}".format(
                candidate["name"]))
        for seed in contract["seeds"]:
            name = "{}_seed{}".format(candidate["name"], seed)
            run_dir = output_dir / name
            jobs.append({
                "name": name, "candidate": candidate["name"],
                "receptive_field": int(candidate["receptive_field"]),
                "seed": int(seed), "parameter_count": parameters,
                "estimated_macs_per_window": macs, "status": "PENDING",
                "pid": None, "exit_code": None, "started_at_utc": None,
                "finished_at_utc": None, "output_dir": str(run_dir.resolve()),
                "log": str((output_dir / (name + ".log")).resolve()),
                "windows": str(windows.resolve()),
                "windows_sha256": sha256_file(windows),
                "model_config": str(model_config_path.resolve()),
                "model_config_sha256": sha256_file(model_config_path),
                "training_config": str(training_config.resolve()),
                "training_config_sha256": sha256_file(training_config),
                "command": [
                    python_executable, "-m",
                    "power_macro.tcn_detection.train.train_binary_classifier",
                    "--model", "cnn", "--windows", str(windows.resolve()),
                    "--training-config", str(training_config.resolve()),
                    "--model-config", str(model_config_path.resolve()),
                    "--seed", str(seed), "--output-dir", str(run_dir.resolve()),
                ],
            })
    if len(jobs) != 18 or len({job["name"] for job in jobs}) != 18:
        raise ValueError("structure search must build exactly 18 unique jobs")
    return jobs


def main():
    """Execute the bounded child queue and retain every state transition."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-config", required=True, type=Path)
    parser.add_argument("--config-dir", required=True, type=Path)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-parallel", type=int, default=4)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite CNN structure search")
    if int(args.max_parallel) < 1:
        raise ValueError("max-parallel must be positive")
    contract = json.loads(args.search_config.read_text(encoding="utf-8"))
    # Build into an absent logical output path first; build_jobs performs no
    # writes and therefore all contract/complexity failures happen before the
    # versioned result directory becomes visible.
    jobs = build_jobs(contract, args.config_dir, args.windows,
                      args.output_dir, sys.executable)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = args.output_dir / "search_manifest.json"
    manifest = {
        "schema_version": 1, "search_id": contract["search_id"],
        "scope": "train_validation_only", "task": "safe_critical_binary",
        "model": "cnn", "status": "RUNNING", "iid_features_loaded": False,
        "iid_metrics_computed": False, "expected_job_count": 18,
        "started_at_utc": utc_now(), "finished_at_utc": None,
        "max_parallel": int(args.max_parallel),
        "search_config": str(args.search_config.resolve()),
        "search_config_sha256": sha256_file(args.search_config), "jobs": jobs,
    }
    write_json_atomic(manifest_path, manifest)

    # Every child owns a unique output directory and log.  The manifest is
    # refreshed after every transition; interruption terminates only children
    # launched here and retains partial evidence instead of silently resuming.
    pending, running, streams = list(jobs), {}, {}
    try:
        while pending or running:
            while pending and len(running) < int(args.max_parallel):
                job = pending.pop(0)
                stream = Path(job["log"]).open("w", encoding="utf-8", buffering=1)
                process = subprocess.Popen(job["command"], stdout=stream,
                                           stderr=subprocess.STDOUT)
                running[job["name"]] = process
                streams[job["name"]] = stream
                job.update(status="RUNNING", pid=process.pid,
                           started_at_utc=utc_now())
                write_json_atomic(manifest_path, manifest)
                print("started {} pid={}".format(job["name"], process.pid), flush=True)
            for name, process in list(running.items()):
                exit_code = process.poll()
                if exit_code is None:
                    continue
                streams[name].close()
                job = next(item for item in jobs if item["name"] == name)
                job.update(status="PASS" if exit_code == 0 else "FAIL",
                           exit_code=exit_code, finished_at_utc=utc_now())
                del running[name]
                write_json_atomic(manifest_path, manifest)
                print("finished {} exit_code={}".format(name, exit_code), flush=True)
            if pending or running:
                time.sleep(0.25)
    except BaseException:
        for process in running.values():
            process.terminate()
        for name, process in running.items():
            streams[name].close()
            job = next(item for item in jobs if item["name"] == name)
            job.update(status="INTERRUPTED", exit_code=process.wait(),
                       finished_at_utc=utc_now())
        for job in pending:
            job.update(status="INTERRUPTED", finished_at_utc=utc_now())
        manifest.update(status="INTERRUPTED", finished_at_utc=utc_now())
        write_json_atomic(manifest_path, manifest)
        raise
    failures = [job for job in jobs if job["status"] != "PASS"]
    manifest.update(status="PASS" if not failures else "FAIL",
                    finished_at_utc=utc_now())
    write_json_atomic(manifest_path, manifest)
    if failures:
        raise SystemExit("structure jobs failed: {}".format(
            [job["name"] for job in failures]))


if __name__ == "__main__":
    main()
