#!/usr/bin/env python3
"""Launch a versioned validation-only binary CNN hyperparameter search."""

from __future__ import print_function

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path):
    """Return a bounded-memory digest for one immutable search input."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now():
    """Return a timezone-explicit timestamp for process evidence."""

    return datetime.now(timezone.utc).isoformat()


def write_json_atomic(path, payload):
    """Publish JSON through a sibling rename so readers never see truncation."""

    temporary = Path(path).with_suffix(Path(path).suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def validate_contract(contract):
    """Fail closed if a search could change the task, data, or objective.

    This search is intentionally limited to optimizer dynamics.  Architecture,
    label ontology, objective, checkpoint metric, and seeds remain fixed so an
    apparent improvement can be attributed to training parameters rather than
    an unrecorded experiment change.
    """

    fixed = contract.get("fixed_training", {})
    arms = contract.get("arms", [])
    expected_seeds = [20260725, 20260726, 20260727]
    if (contract.get("scope") != "train_validation_only"
            or contract.get("model") != "cnn"
            or contract.get("task") != "safe_critical_binary"
            or int(contract.get("window_length", -1)) != 32
            or contract.get("seeds") != expected_seeds
            or contract.get("iid_policy") != {
                "features_loaded": False, "metrics_computed": False,
                "selection_allowed": False}
            or fixed.get("sampling_strategy") != "natural"
            or fixed.get("loss_type") != "cross_entropy"
            or fixed.get("class_weight_strategy") != "none"
            or fixed.get("checkpoint_selection_metric") != "critical_pr_auc"):
        raise ValueError("hyperparameter search violates the fixed CNN contract")
    variable_keys = contract.get(
        "variable_keys", ["learning_rate", "weight_decay"])
    expected_arm_count = int(contract.get("expected_arm_count", 9))
    if (not isinstance(variable_keys, list) or not variable_keys
            or len(set(variable_keys)) != len(variable_keys)
            or any(not isinstance(key, str) or not key for key in variable_keys)):
        raise ValueError("search variable_keys must be unique non-empty strings")
    names = [arm.get("name") for arm in arms]
    if (len(arms) != expected_arm_count or len(set(names)) != expected_arm_count
            or any(not name for name in names)):
        raise ValueError("bounded search arm count or names are invalid")
    for arm in arms:
        if set(arm) != {"name"}.union(variable_keys):
            raise ValueError("search arm fields differ from declared variable_keys")
        resolved_lr = arm.get("learning_rate", fixed.get("learning_rate"))
        resolved_weight_decay = arm.get("weight_decay", fixed.get("weight_decay"))
        if (resolved_lr is None or resolved_weight_decay is None
                or float(resolved_lr) <= 0.0
                or float(resolved_weight_decay) < 0.0):
            raise ValueError("optimizer hyperparameters are outside valid bounds")
    return variable_keys, expected_arm_count


def build_jobs(contract, windows, model_config, output_dir, python_executable):
    """Materialize exactly 27 deterministic train/validation commands.

    Each arm receives its own complete training JSON.  Storing resolved configs
    next to the manifest avoids implicit defaults and makes every checkpoint's
    optimizer settings independently hashable.  The trainer itself requests
    only train and validation splits before feature deserialization, providing
    the structural IID exclusion rather than relying on naming conventions.
    """

    variable_keys, expected_arm_count = validate_contract(contract)
    config_dir = output_dir / "resolved_training_configs"
    config_dir.mkdir(parents=True, exist_ok=False)
    jobs = []
    for arm in contract["arms"]:
        resolved = dict(contract["fixed_training"])
        # Only keys explicitly declared by the versioned contract may override
        # fixed training values.  This supports scheduler/batch refinements
        # without allowing a hidden objective or data-policy change.
        resolved.update({key: arm[key] for key in variable_keys})
        training_config = config_dir / (arm["name"] + ".json")
        write_json_atomic(training_config, resolved)
        for seed in contract["seeds"]:
            name = "{}_seed{}".format(arm["name"], seed)
            run_dir = output_dir / name
            jobs.append({
                "name": name, "arm": arm["name"], "seed": int(seed),
                "learning_rate": float(resolved["learning_rate"]),
                "weight_decay": float(resolved["weight_decay"]),
                "training_overrides": {key: arm[key] for key in variable_keys},
                "status": "PENDING", "pid": None, "exit_code": None,
                "started_at_utc": None, "finished_at_utc": None,
                "output_dir": str(run_dir.resolve()),
                "log": str((output_dir / (name + ".log")).resolve()),
                "windows": str(windows.resolve()),
                "windows_sha256": sha256_file(windows),
                "model_config": str(model_config.resolve()),
                "model_config_sha256": sha256_file(model_config),
                "training_config": str(training_config.resolve()),
                "training_config_sha256": sha256_file(training_config),
                "command": [
                    python_executable, "-m",
                    "power_macro.tcn_detection.train.train_binary_classifier",
                    "--model", "cnn", "--windows", str(windows.resolve()),
                    "--training-config", str(training_config.resolve()),
                    "--model-config", str(model_config.resolve()),
                    "--seed", str(seed), "--output-dir", str(run_dir.resolve()),
                ],
            })
    expected_jobs = expected_arm_count * len(contract["seeds"])
    if (len(jobs) != expected_jobs
            or len({job["name"] for job in jobs}) != expected_jobs):
        raise ValueError("bounded search built an unexpected job matrix")
    return jobs


def main():
    """Run the bounded matrix and retain an auditable state transition log."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-config", required=True, type=Path)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-parallel", type=int, default=4)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("refusing to overwrite CNN hyperparameter search")
    if int(args.max_parallel) < 1:
        raise ValueError("max-parallel must be positive")
    contract = json.loads(args.search_config.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    jobs = build_jobs(contract, args.windows, args.model_config,
                      args.output_dir, sys.executable)
    manifest_path = args.output_dir / "search_manifest.json"
    manifest = {
        "schema_version": 1, "search_id": contract["search_id"],
        "scope": "train_validation_only", "model": "cnn",
        "task": "safe_critical_binary", "status": "RUNNING",
        "iid_features_loaded": False, "iid_metrics_computed": False,
        "started_at_utc": utc_now(), "finished_at_utc": None,
        "expected_job_count": len(jobs), "max_parallel": int(args.max_parallel),
        "search_config": str(args.search_config.resolve()),
        "search_config_sha256": sha256_file(args.search_config), "jobs": jobs,
    }
    write_json_atomic(manifest_path, manifest)

    # The launcher owns only its child processes.  Every child writes to a
    # unique absent directory, while the manifest is refreshed after each
    # transition.  Interruptions retain partial evidence and never masquerade
    # as a complete screen.
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
        raise SystemExit("hyperparameter jobs failed: {}".format(
            [job["name"] for job in failures]))


if __name__ == "__main__":
    main()
