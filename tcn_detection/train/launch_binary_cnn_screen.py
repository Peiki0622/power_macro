#!/usr/bin/env python3
"""Launch the fixed 3-architecture x 3-history x 3-seed CNN screen."""

from __future__ import print_function

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ARCHITECTURES = (
    ("small", "model_cnn_state_code_binary_small_v1.json"),
    ("medium", "model_cnn_state_code_binary_medium_v1.json"),
    ("large", "model_cnn_state_code_binary_large_v1.json"),
)
WINDOW_LENGTHS = (8, 16, 32)
SEEDS = (20260725, 20260726, 20260727)
TRAINING_CONFIG = "training_state_code_binary_b_sqrt_ce.json"


def sha256_file(path):
    """Hash one immutable input without loading large windows into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now():
    """Return a timezone-explicit process timestamp for the run manifest."""

    return datetime.now(timezone.utc).isoformat()


def write_manifest(path, payload):
    """Atomically publish process state after each child transition."""

    temporary = Path(path).with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def build_jobs(args):
    """Build exactly 27 deterministic, non-overlapping development jobs.

    Architecture, history, objective, and seeds are code constants because the
    experiment contract was frozen before execution.  Allowing arbitrary CLI
    subsets here would make a partial screen look complete.  Every trainer is
    explicitly passed ``--model cnn`` and reads a full window CSV through the
    train/validation streaming filter; IID tensors therefore never enter these
    child processes.
    """

    training_config = args.config_dir / TRAINING_CONFIG
    if not training_config.is_file():
        raise ValueError("missing frozen screen training config")
    jobs = []
    for architecture, config_name in ARCHITECTURES:
        model_config = args.config_dir / config_name
        if not model_config.is_file():
            raise ValueError("missing CNN model config: {}".format(model_config))
        for length in WINDOW_LENGTHS:
            windows = args.windows_dir / "windows_L{}.csv".format(length)
            if not windows.is_file():
                raise ValueError("missing binary window table: {}".format(windows))
            for seed in SEEDS:
                name = "{}_L{}_seed{}".format(architecture, length, seed)
                output = args.output_dir / name
                jobs.append({
                    "name": name, "architecture": architecture,
                    "window_length": length, "seed": seed,
                    "training_arm": "b_sqrt_ce", "status": "PENDING",
                    "pid": None, "exit_code": None,
                    "started_at_utc": None, "finished_at_utc": None,
                    "output_dir": output.name, "log": name + ".log",
                    "windows": str(windows.resolve()),
                    "windows_sha256": sha256_file(windows),
                    "model_config": str(model_config.resolve()),
                    "model_config_sha256": sha256_file(model_config),
                    "training_config": str(training_config.resolve()),
                    "training_config_sha256": sha256_file(training_config),
                    "command": [
                        sys.executable, "-m",
                        "power_macro.tcn_detection.train.train_binary_classifier",
                        "--model", "cnn", "--windows", str(windows),
                        "--training-config", str(training_config),
                        "--model-config", str(model_config),
                        "--seed", str(seed), "--output-dir", str(output),
                    ],
                })
    if len(jobs) != 27 or len({job["name"] for job in jobs}) != 27:
        raise ValueError("frozen CNN screen must contain 27 unique jobs")
    return jobs


def main():
    """Run the bounded matrix and retain every success or failure as evidence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows-dir", required=True, type=Path)
    parser.add_argument("--config-dir", required=True, type=Path)
    parser.add_argument("--policy-config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-parallel", type=int, default=4)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite CNN architecture screen")
    if int(args.max_parallel) < 1:
        raise ValueError("max-parallel must be positive")
    policy = json.loads(args.policy_config.read_text(encoding="utf-8"))
    if (policy.get("policy_id") != "state_code_binary_cnn_iid_v1_20260731_r1"
            or policy.get("iid_policy", {}).get("development_load_allowed") is not False):
        raise ValueError("CNN screen requires the frozen no-IID experiment policy")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    jobs = build_jobs(args)
    manifest_path = args.output_dir / "screen_manifest.json"
    manifest = {
        "schema_version": 1, "task": "safe_critical_binary",
        "model": "cnn", "stage": "architecture_history_screen",
        "scope": "train_validation_only", "iid_metrics_computed": False,
        "status": "RUNNING", "started_at_utc": utc_now(),
        "finished_at_utc": None, "max_parallel": int(args.max_parallel),
        "policy_config": str(args.policy_config.resolve()),
        "policy_config_sha256": sha256_file(args.policy_config),
        "expected_job_count": 27, "jobs": jobs,
    }
    write_manifest(manifest_path, manifest)

    # Each child owns a unique immutable output directory and line-buffered log.
    # The launcher updates the manifest after every transition so interruption
    # cannot be mistaken for a completed screen.  On interruption it terminates
    # only its own children and deliberately retains partial evidence rather
    # than attempting an unsafe in-place resume.
    pending, running, logs = list(jobs), {}, {}
    try:
        while pending or running:
            while pending and len(running) < int(args.max_parallel):
                job = pending.pop(0)
                stream = (args.output_dir / job["log"]).open(
                    "w", encoding="utf-8", buffering=1)
                process = subprocess.Popen(job["command"], stdout=stream,
                                           stderr=subprocess.STDOUT)
                running[job["name"]] = process
                logs[job["name"]] = stream
                job.update(status="RUNNING", pid=process.pid,
                           started_at_utc=utc_now())
                write_manifest(manifest_path, manifest)
                print("started {} pid={}".format(job["name"], process.pid), flush=True)
            for name, process in list(running.items()):
                exit_code = process.poll()
                if exit_code is None:
                    continue
                logs[name].close()
                job = next(item for item in jobs if item["name"] == name)
                job.update(status="PASS" if exit_code == 0 else "FAIL",
                           exit_code=exit_code, finished_at_utc=utc_now())
                del running[name]
                write_manifest(manifest_path, manifest)
                print("finished {} exit_code={}".format(name, exit_code), flush=True)
            if pending or running:
                time.sleep(0.25)
    except BaseException:
        for process in running.values():
            process.terminate()
        for name, process in running.items():
            logs[name].close()
            job = next(item for item in jobs if item["name"] == name)
            job.update(status="INTERRUPTED", exit_code=process.wait(),
                       finished_at_utc=utc_now())
        for job in pending:
            job.update(status="INTERRUPTED", finished_at_utc=utc_now())
        manifest.update(status="INTERRUPTED", finished_at_utc=utc_now())
        write_manifest(manifest_path, manifest)
        raise

    failures = [job for job in jobs if job["status"] != "PASS"]
    manifest.update(status="PASS" if not failures else "FAIL",
                    finished_at_utc=utc_now())
    write_manifest(manifest_path, manifest)
    if failures:
        raise SystemExit("CNN screen failures: {}".format(
            [job["name"] for job in failures]))


if __name__ == "__main__":
    main()
