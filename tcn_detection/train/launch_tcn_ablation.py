#!/usr/bin/env python3
"""Launch selected three-seed L32 TCN objective-ablation arms."""

from __future__ import print_function

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ARM_CONFIGS = (
    ("a_natural_ce", "training_v2_a_natural_ce.json", "tcn"),
    ("b_natural_focal", "training_v2_b_natural_focal.json", "tcn"),
    ("c_sqrt_ce", "training_v2_c_sqrt_ce.json", "tcn"),
    ("d_sampler_ce", "training_v2_d_sampler_ce.json", "tcn"),
    ("e_ordinal", "training_v2_e_ordinal.json", "ordinal_tcn"),
    ("f_ordinal_time", "training_v2_f_ordinal_time.json", "ordinal_time_tcn"),
)
FORMAL_SEEDS = (20260725, 20260726, 20260727)


def sha256_file(path):
    """Hash one immutable input without loading the large window CSV in memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now():
    """Return an unambiguous timestamp for the persisted experiment audit."""

    return datetime.now(timezone.utc).isoformat()


def write_manifest(path, payload):
    """Atomically publish launcher state so interruption cannot truncate JSON."""

    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def build_jobs(args):
    """Create the immutable selected-arm matrix with explicit seed provenance.

    The arm name and seed both appear in the output path.  This prevents two
    statistically independent trials from sharing artifacts and makes a
    partial failure diagnosable without parsing its log.  Config hashes are
    recorded per job because the four objective definitions intentionally
    differ, while windows and architecture are common to the whole matrix.
    """

    jobs = []
    selected_arms = set(args.arms) if args.arms else {item[0] for item in ARM_CONFIGS[:4]}
    for arm_name, config_name, model_name in ARM_CONFIGS:
        if arm_name not in selected_arms:
            continue
        config_path = args.config_dir / config_name
        if not config_path.is_file():
            raise ValueError("missing ablation config: {}".format(config_path))
        for seed in FORMAL_SEEDS:
            name = "{}_seed{}".format(arm_name, seed)
            output_dir = args.output_dir / name
            log_path = args.output_dir / (name + ".log")
            command = [
                sys.executable, "-m", "power_macro.tcn_detection.train.train_classifier",
                "--model", model_name, "--windows", str(args.windows),
                "--training-config", str(config_path), "--model-config", str(args.model_config),
                "--seed", str(seed), "--output-dir", str(output_dir),
            ]
            jobs.append({
                "name": name, "arm": arm_name, "seed": seed,
                "status": "PENDING", "exit_code": None, "pid": None,
                "command": command, "output_dir": output_dir.name,
                "log": log_path.name, "training_config": str(config_path.resolve()),
                "training_config_sha256": sha256_file(config_path),
                "started_at_utc": None, "finished_at_utc": None,
            })
    return jobs


def main():
    """Run the bounded matrix and retain complete evidence for every outcome."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--config-dir", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-parallel", type=int, default=4,
                        help="Maximum simultaneous 8-thread trainers; default bounds CPU contention.")
    parser.add_argument("--arms", nargs="+", choices=tuple(item[0] for item in ARM_CONFIGS),
                        help="Optional arm subset; omitted preserves the original four-arm matrix.")
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite ablation directory: {}".format(args.output_dir))
    if not args.windows.is_file() or not args.model_config.is_file():
        raise ValueError("windows and model configuration must be existing files")
    if int(args.max_parallel) < 1:
        raise ValueError("max-parallel must be positive")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    jobs = build_jobs(args)
    manifest_path = args.output_dir / "ablation_manifest.json"
    manifest = {
        "schema_version": 1, "status": "RUNNING",
        "started_at_utc": utc_now(), "finished_at_utc": None,
        "max_parallel": int(args.max_parallel), "runtime_python": sys.executable,
        "inputs": {
            "windows": str(args.windows.resolve()), "windows_sha256": sha256_file(args.windows),
            "model_config": str(args.model_config.resolve()),
            "model_config_sha256": sha256_file(args.model_config),
        },
        "jobs": jobs,
    }
    write_manifest(manifest_path, manifest)

    pending = list(jobs)
    running = {}
    logs = {}
    try:
        while pending or running:
            # Admission is bounded rather than starting all twelve processes at
            # once.  Each formal config requests eight PyTorch threads; four
            # children therefore use roughly one third of the 96-core host and
            # avoid latency inflation from BLAS oversubscription.
            while pending and len(running) < int(args.max_parallel):
                job = pending.pop(0)
                log_path = args.output_dir / job["log"]
                log = log_path.open("w", encoding="utf-8", buffering=1)
                try:
                    process = subprocess.Popen(job["command"], stdout=log, stderr=subprocess.STDOUT)
                except BaseException:
                    log.close()
                    raise
                logs[job["name"]] = log
                running[job["name"]] = process
                job.update({"status": "RUNNING", "pid": process.pid, "started_at_utc": utc_now()})
                write_manifest(manifest_path, manifest)
                print("started {} pid={}".format(job["name"], process.pid), flush=True)

            for name, process in list(running.items()):
                exit_code = process.poll()
                if exit_code is None:
                    continue
                logs[name].close()
                job = next(item for item in jobs if item["name"] == name)
                job.update({"status": "PASS" if exit_code == 0 else "FAIL",
                            "exit_code": exit_code, "finished_at_utc": utc_now()})
                del running[name]
                write_manifest(manifest_path, manifest)
                print("finished {} exit_code={}".format(name, exit_code), flush=True)
            if pending or running:
                time.sleep(0.25)
    except BaseException:
        # Terminate only children owned by this launcher.  Their partial output
        # directories and logs are deliberately retained and the root cannot
        # be reused, making failures inspectable rather than silently resumed.
        for process in running.values():
            process.terminate()
        for name, process in running.items():
            exit_code = process.wait()
            logs[name].close()
            job = next(item for item in jobs if item["name"] == name)
            job.update({"status": "INTERRUPTED", "exit_code": exit_code,
                        "finished_at_utc": utc_now()})
        for job in pending:
            job.update({"status": "INTERRUPTED", "finished_at_utc": utc_now()})
        manifest.update({"status": "INTERRUPTED", "finished_at_utc": utc_now()})
        write_manifest(manifest_path, manifest)
        raise

    failures = [job for job in jobs if job["status"] != "PASS"]
    manifest.update({"status": "PASS" if not failures else "FAIL", "finished_at_utc": utc_now()})
    write_manifest(manifest_path, manifest)
    if failures:
        raise SystemExit("ablation jobs failed: {}".format([job["name"] for job in failures]))


if __name__ == "__main__":
    main()
