#!/usr/bin/env python3
"""Launch the independent Pilot CAE/CNN/TCN jobs concurrently on CPU."""

from __future__ import print_function

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


JOB_ORDER = ("cae_L16", "cnn_L16", "tcn_L8", "tcn_L16", "tcn_L32")


def sha256_file(path):
    """Hash one immutable training input without loading a window CSV at once."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now():
    """Return a stable ISO-8601 UTC timestamp for operational run evidence."""

    return datetime.now(timezone.utc).isoformat()


def write_manifest(path, payload):
    """Atomically update the live launcher manifest after each state change."""

    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def aggregate_status(jobs):
    """Return the aggregate status for a set of persisted child-job records."""

    statuses = {job["status"] for job in jobs}
    if statuses <= {"PASS"}:
        return "PASS"
    if statuses <= {"PASS", "FAIL"}:
        return "FAIL"
    return "RUNNING"


def command_matrix(args, selected_jobs=None):
    """Return fixed subprocess commands and output names for all required models.

    Each command is a module invocation under the current interpreter.  When
    this launcher is called through ``conda run -n DL``, all children therefore
    inherit exactly the selected CPU PyTorch runtime rather than accidentally
    falling back to the system Python.
    """

    common = ["--training-config", str(args.training_config), "--model-config", str(args.model_config)]
    matrix = [
        ("cae_L16", [sys.executable, "-m", "power_macro.tcn_detection.train.train_autoencoder", "--windows",
                     str(args.windows_dir / "windows_L16.csv"), "--label-dir", str(args.label_dir), *common]),
        ("cnn_L16", [sys.executable, "-m", "power_macro.tcn_detection.train.train_classifier", "--model", "cnn", "--windows",
                     str(args.windows_dir / "windows_L16.csv"), *common]),
        ("tcn_L8", [sys.executable, "-m", "power_macro.tcn_detection.train.train_classifier", "--model", "tcn", "--windows",
                    str(args.windows_dir / "windows_L8.csv"), *common]),
        ("tcn_L16", [sys.executable, "-m", "power_macro.tcn_detection.train.train_classifier", "--model", "tcn", "--windows",
                     str(args.windows_dir / "windows_L16.csv"), *common]),
        ("tcn_L32", [sys.executable, "-m", "power_macro.tcn_detection.train.train_classifier", "--model", "tcn", "--windows",
                     str(args.windows_dir / "windows_L32.csv"), *common]),
    ]
    if selected_jobs is None:
        return matrix
    requested = list(selected_jobs)
    if len(requested) != len(set(requested)):
        raise ValueError("training job selection contains duplicates")
    unknown = set(requested) - set(JOB_ORDER)
    if unknown:
        raise ValueError("unknown training jobs: {}".format(sorted(unknown)))
    requested_set = set(requested)
    return [job for job in matrix if job[0] in requested_set]


def main():
    """Run all independent model jobs and fail only after collecting every status."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows-dir", required=True, type=Path)
    parser.add_argument("--label-dir", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--jobs", nargs="+", choices=JOB_ORDER,
                        help="Optional subset of the fixed model matrix; omitted preserves the historical all-job behavior.")
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite model version directory: {}".format(args.output_dir))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    selected = list(args.jobs) if args.jobs else list(JOB_ORDER)
    matrix = command_matrix(args, selected)
    manifest_path = args.output_dir / "parallel_training_manifest.json"
    jobs = []
    for name, command in matrix:
        output = args.output_dir / name
        log_path = args.output_dir / (name + ".log")
        full_command = [*command, "--output-dir", str(output)]
        jobs.append({"name": name, "status": "PENDING", "exit_code": None, "pid": None,
                     "command": full_command, "log": log_path.name, "output_dir": output.name,
                     "started_at_utc": None, "finished_at_utc": None})
    manifest = {"schema_version": 2, "status": "RUNNING", "started_at_utc": utc_now(),
                "finished_at_utc": None, "runtime_python": sys.executable, "selected_jobs": selected,
                "inputs": {"windows_dir": str(args.windows_dir.resolve()), "label_dir": str(args.label_dir.resolve()),
                           "training_config": str(args.training_config.resolve()),
                           "training_config_sha256": sha256_file(args.training_config),
                           "model_config": str(args.model_config.resolve()),
                           "model_config_sha256": sha256_file(args.model_config),
                           "window_sha256": {name: sha256_file(args.windows_dir / "windows_L{}.csv".format(name.split("L")[-1]))
                                             for name in selected if name.startswith("tcn_L")}},
                "jobs": jobs}
    write_manifest(manifest_path, manifest)

    # Start every selected process before waiting so the small CPU models train
    # concurrently.  Logs are line buffered and child epoch records are flushed,
    # making progress visible without retaining tensor or per-epoch checkpoints.
    running = {}
    logs = {}
    try:
        for job in jobs:
            log_path = args.output_dir / job["log"]
            log = log_path.open("w", encoding="utf-8", buffering=1)
            try:
                process = subprocess.Popen(job["command"], stdout=log, stderr=subprocess.STDOUT)
            except BaseException:
                # Opening the log and spawning the process are two separate OS
                # operations.  If process creation fails (for example because
                # the interpreter disappears), no child owns this descriptor,
                # so the launcher must close it before recording interruption.
                log.close()
                raise
            logs[job["name"]] = log
            running[job["name"]] = process
            job.update({"status": "RUNNING", "pid": process.pid, "started_at_utc": utc_now()})
            write_manifest(manifest_path, manifest)
            print("started {} pid={} log={}".format(job["name"], process.pid, log_path), flush=True)

        while running:
            for name, process in list(running.items()):
                exit_code = process.poll()
                if exit_code is None:
                    continue
                logs[name].close()
                job = next(item for item in jobs if item["name"] == name)
                job.update({"status": "PASS" if exit_code == 0 else "FAIL", "exit_code": exit_code,
                            "finished_at_utc": utc_now()})
                del running[name]
                manifest["status"] = aggregate_status(jobs)
                write_manifest(manifest_path, manifest)
                print("finished {} exit_code={}".format(name, exit_code), flush=True)
            if running:
                time.sleep(0.25)
    except BaseException:
        # Never leave untracked children updating an immutable model directory
        # after the launcher reports failure.  Retain every partial artifact and
        # mark the version interrupted; a retry must use a new output version.
        for name, process in running.items():
            process.terminate()
        for name, process in running.items():
            exit_code = process.wait()
            logs[name].close()
            job = next(item for item in jobs if item["name"] == name)
            job.update({"status": "INTERRUPTED", "exit_code": exit_code, "finished_at_utc": utc_now()})
        # A spawn failure can occur before every matrix entry starts.  Those
        # entries have no PID or exit code, but leaving them as PENDING would
        # incorrectly suggest that the immutable run could still be resumed.
        # Mark them interrupted while preserving the null process metadata.
        for job in jobs:
            if job["status"] == "PENDING":
                job.update({"status": "INTERRUPTED", "finished_at_utc": utc_now()})
        manifest.update({"status": "INTERRUPTED", "finished_at_utc": utc_now()})
        write_manifest(manifest_path, manifest)
        raise

    manifest.update({"status": aggregate_status(jobs), "finished_at_utc": utc_now()})
    write_manifest(manifest_path, manifest)
    failed = [job for job in jobs if job["status"] != "PASS"]
    if failed:
        raise SystemExit("parallel model jobs failed: {}".format([job["name"] for job in failed]))


if __name__ == "__main__":
    main()
