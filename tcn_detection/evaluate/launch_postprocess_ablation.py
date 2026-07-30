#!/usr/bin/env python3
"""Run five-fold causal postprocessing for both selected ablation arms."""

from __future__ import print_function

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    """Return an ISO-8601 UTC timestamp for run-state evidence."""

    return datetime.now(timezone.utc).isoformat()


def write_manifest(path, payload):
    """Atomically update progress without exposing truncated JSON."""

    temporary = Path(path).with_suffix(Path(path).suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def main():
    """Launch six selected arm/seed jobs while retaining gate failures."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-summary", required=True, type=Path)
    parser.add_argument("--ablation-dir", required=True, type=Path)
    parser.add_argument("--label-dir", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-parallel", type=int, default=2)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite postprocess ablation directory: {}".format(args.output_dir))
    if int(args.max_parallel) < 1:
        raise ValueError("max-parallel must be positive")

    raw = json.loads(args.raw_summary.read_text(encoding="utf-8"))
    selected = list(raw.get("selected_top_two", []))
    if len(selected) != 2:
        raise ValueError("raw summary must declare exactly two selected arms")
    runs = [item for item in raw["runs"].values() if item["arm"] in set(selected)]
    if len(runs) != 6:
        raise ValueError("selected arms must contain exactly six arm/seed runs")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    jobs = []
    for run in sorted(runs, key=lambda item: (selected.index(item["arm"]), item["seed"])):
        name = "{}_seed{}".format(run["arm"], run["seed"])
        output = args.output_dir / name
        log = args.output_dir / (name + ".log")
        predictions = args.ablation_dir / name / "validation_predictions.csv"
        command = [
            sys.executable, "-m", "power_macro.tcn_detection.evaluate.tune_postprocess",
            "--predictions", str(predictions), "--label-dir", str(args.label_dir),
            "--corpus", str(args.corpus), "--output-dir", str(output),
        ]
        jobs.append({"name": name, "arm": run["arm"], "seed": run["seed"],
                     "status": "PENDING", "exit_code": None, "pid": None,
                     "command": command, "log": log.name, "output_dir": output.name,
                     "started_at_utc": None, "finished_at_utc": None})
    manifest_path = args.output_dir / "postprocess_ablation_manifest.json"
    manifest = {"schema_version": 1, "status": "RUNNING", "scope": "validation_only",
                "iid_ood_metrics_computed": False, "selected_arms": selected,
                "started_at_utc": utc_now(), "finished_at_utc": None, "jobs": jobs}
    write_manifest(manifest_path, manifest)

    pending = list(jobs)
    running = {}
    logs = {}
    try:
        while pending or running:
            while pending and len(running) < int(args.max_parallel):
                job = pending.pop(0)
                stream = (args.output_dir / job["log"]).open("w", encoding="utf-8", buffering=1)
                try:
                    process = subprocess.Popen(job["command"], stdout=stream, stderr=subprocess.STDOUT)
                except BaseException:
                    stream.close()
                    raise
                running[job["name"]] = process
                logs[job["name"]] = stream
                job.update({"status": "RUNNING", "pid": process.pid, "started_at_utc": utc_now()})
                write_manifest(manifest_path, manifest)
                print("started {} pid={}".format(job["name"], process.pid), flush=True)

            for name, process in list(running.items()):
                exit_code = process.poll()
                if exit_code is None:
                    continue
                logs[name].close()
                job = next(item for item in jobs if item["name"] == name)
                report_path = args.output_dir / job["output_dir"] / "postprocess_report.json"
                # tune_postprocess uses exit 2 only to communicate that its
                # fully published OOF report failed an acceptance gate.  This
                # launcher preserves that scientific result as COMPLETE_FAIL;
                # missing reports or any other exit code are execution errors.
                if exit_code in (0, 2) and report_path.is_file():
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    status = "PASS" if report["acceptance"]["pass"] else "COMPLETE_FAIL"
                else:
                    status = "ERROR"
                job.update({"status": status, "exit_code": exit_code, "finished_at_utc": utc_now()})
                del running[name]
                write_manifest(manifest_path, manifest)
                print("finished {} exit_code={} status={}".format(name, exit_code, status), flush=True)
            if pending or running:
                time.sleep(0.25)
    except BaseException:
        for process in running.values():
            process.terminate()
        for name, process in running.items():
            job = next(item for item in jobs if item["name"] == name)
            job.update({"status": "INTERRUPTED", "exit_code": process.wait(),
                        "finished_at_utc": utc_now()})
            logs[name].close()
        for job in pending:
            job.update({"status": "INTERRUPTED", "finished_at_utc": utc_now()})
        manifest.update({"status": "INTERRUPTED", "finished_at_utc": utc_now()})
        write_manifest(manifest_path, manifest)
        raise

    errors = [job for job in jobs if job["status"] == "ERROR"]
    manifest.update({"status": "ERROR" if errors else "COMPLETE", "finished_at_utc": utc_now()})
    write_manifest(manifest_path, manifest)
    if errors:
        raise SystemExit("postprocess execution errors: {}".format([job["name"] for job in errors]))


if __name__ == "__main__":
    main()
