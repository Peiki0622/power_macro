#!/usr/bin/env python3
"""Launch the fixed Safe/Critical four-arm, three-seed TCN ablation."""

from __future__ import print_function

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ARMS = (
    ("a_natural_ce", "training_state_code_binary_a_natural_ce.json"),
    ("b_sqrt_ce", "training_state_code_binary_b_sqrt_ce.json"),
    ("c_sqrt_focal", "training_state_code_binary_c_sqrt_focal.json"),
    ("d_balanced_sampler_ce", "training_state_code_binary_d_balanced_sampler_ce.json"),
)
SEEDS = (20260725, 20260726, 20260727)


def sha256_file(path):
    """Hash immutable experiment inputs without loading them in memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now():
    """Return an unambiguous UTC process timestamp."""

    return datetime.now(timezone.utc).isoformat()


def write_manifest(path, payload):
    """Atomically expose launcher progress after every child transition."""

    temporary = Path(path).with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def build_jobs(args):
    """Build deterministic, non-overlapping binary run commands."""

    selected = set(args.arms) if args.arms else {arm for arm, _ in ARMS}
    jobs = []
    for arm, config_name in ARMS:
        if arm not in selected:
            continue
        training_config = args.config_dir / config_name
        if not training_config.is_file():
            raise ValueError("missing binary training config: {}".format(training_config))
        for seed in SEEDS:
            name = "{}_seed{}".format(arm, seed)
            output = args.output_dir / name
            jobs.append({
                "name": name, "arm": arm, "seed": seed,
                "status": "PENDING", "pid": None, "exit_code": None,
                "started_at_utc": None, "finished_at_utc": None,
                "output_dir": output.name, "log": name + ".log",
                "training_config": str(training_config.resolve()),
                "training_config_sha256": sha256_file(training_config),
                "command": [
                    sys.executable, "-m",
                    "power_macro.tcn_detection.train.train_binary_classifier",
                    "--windows", str(args.windows),
                    "--training-config", str(training_config),
                    "--model-config", str(args.model_config),
                    "--seed", str(seed), "--output-dir", str(output),
                ],
            })
    return jobs


def main():
    """Run a bounded parallel matrix and retain every job's evidence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--config-dir", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-parallel", type=int, default=4)
    parser.add_argument("--arms", nargs="+", choices=tuple(arm for arm, _ in ARMS))
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite binary ablation directory")
    if int(args.max_parallel) < 1:
        raise ValueError("max-parallel must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    jobs = build_jobs(args)
    manifest_path = args.output_dir / "ablation_manifest.json"
    manifest = {
        "schema_version": 1, "task": "safe_critical_binary",
        "scope": "train_validation_only", "iid_metrics_computed": False,
        "status": "RUNNING", "started_at_utc": utc_now(),
        "finished_at_utc": None, "max_parallel": int(args.max_parallel),
        "inputs": {"windows": str(args.windows.resolve()),
                   "windows_sha256": sha256_file(args.windows),
                   "model_config": str(args.model_config.resolve()),
                   "model_config_sha256": sha256_file(args.model_config)},
        "jobs": jobs,
    }
    write_manifest(manifest_path, manifest)
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
        # Terminate only children owned by this launcher.  Partial versioned
        # output remains immutable failure evidence and is never auto-resumed.
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
        raise SystemExit("binary ablation failures: {}".format(
            [job["name"] for job in failures]))


if __name__ == "__main__":
    main()
