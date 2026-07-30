#!/usr/bin/env python3
"""Launch the fixed L32 four-arm, three-seed code-state ablation."""

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
    ("a_direct_natural", "training_state_code_v1_a_direct_natural.json", "tcn"),
    ("b_direct_sqrt", "training_state_code_v1_b_direct_sqrt.json", "tcn"),
    ("c_ordinal_natural", "training_state_code_v1_c_ordinal_natural.json", "ordinal_tcn"),
    ("d_ordinal_sqrt", "training_state_code_v1_d_ordinal_sqrt.json", "ordinal_tcn"),
)
SEEDS = (20260725, 20260726, 20260727)


def sha256_file(path):
    """Hash one immutable experiment input without loading it into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now():
    """Return an unambiguous timestamp for process provenance."""

    return datetime.now(timezone.utc).isoformat()


def write_manifest(path, payload):
    """Atomically expose launcher state after each process transition."""

    temporary = Path(path).with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def build_jobs(args):
    """Materialize exactly twelve non-overlapping run commands.

    Every command names its arm and seed in the output directory.  Config and
    common input hashes are persisted before any child starts, so a partial
    matrix remains diagnosable and cannot be confused with another version.
    """

    selected_arms = set(args.arms) if args.arms else {item[0] for item in ARMS}
    jobs = []
    for arm, config_name, model in ARMS:
        if arm not in selected_arms:
            continue
        config = args.config_dir / config_name
        if not config.is_file():
            raise ValueError("missing state ablation config: {}".format(config))
        for seed in SEEDS:
            name = "{}_seed{}".format(arm, seed)
            output = args.output_dir / name
            jobs.append({
                "name": name, "arm": arm, "seed": seed, "model": model,
                "status": "PENDING", "pid": None, "exit_code": None,
                "started_at_utc": None, "finished_at_utc": None,
                "output_dir": output.name, "log": name + ".log",
                "training_config": str(config.resolve()),
                "training_config_sha256": sha256_file(config),
                "command": [sys.executable, "-m",
                            "power_macro.tcn_detection.train.train_classifier",
                            "--model", model, "--windows", str(args.windows),
                            "--training-config", str(config), "--model-config",
                            str(args.model_config), "--seed", str(seed),
                            "--output-dir", str(output)],
            })
    return jobs


def main():
    """Run the bounded CPU matrix and retain evidence for every child."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--config-dir", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-parallel", type=int, default=4)
    parser.add_argument("--arms", nargs="+", choices=tuple(item[0] for item in ARMS),
                        help="Optional arm subset; omitted runs the full four-arm matrix.")
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite state ablation directory")
    if not args.windows.is_file() or not args.model_config.is_file():
        raise ValueError("windows and model config must exist")
    if int(args.max_parallel) < 1:
        raise ValueError("max-parallel must be positive")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    jobs = build_jobs(args)
    manifest_path = args.output_dir / "ablation_manifest.json"
    manifest = {
        "schema_version": 1, "task": "same_sample_current_state_monitoring",
        "status": "RUNNING", "started_at_utc": utc_now(),
        "finished_at_utc": None, "runtime_python": sys.executable,
        "max_parallel": int(args.max_parallel),
        "selected_arms": list(args.arms) if args.arms else [item[0] for item in ARMS],
        "inputs": {"windows": str(args.windows.resolve()),
                   "windows_sha256": sha256_file(args.windows),
                   "model_config": str(args.model_config.resolve()),
                   "model_config_sha256": sha256_file(args.model_config)},
        "jobs": jobs,
    }
    write_manifest(manifest_path, manifest)

    pending = list(jobs)
    running = {}
    logs = {}
    try:
        while pending or running:
            while pending and len(running) < int(args.max_parallel):
                job = pending.pop(0)
                log = (args.output_dir / job["log"]).open(
                    "w", encoding="utf-8", buffering=1)
                process = subprocess.Popen(job["command"], stdout=log,
                                           stderr=subprocess.STDOUT)
                logs[job["name"]] = log
                running[job["name"]] = process
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
        # Only children created by this launcher are terminated.  Partial
        # directories remain intentionally immutable for diagnosis.
        for process in running.values():
            process.terminate()
        for name, process in running.items():
            exit_code = process.wait()
            logs[name].close()
            job = next(item for item in jobs if item["name"] == name)
            job.update(status="INTERRUPTED", exit_code=exit_code,
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
        raise SystemExit("state ablation failures: {}".format(
            [job["name"] for job in failures]))


if __name__ == "__main__":
    main()
