#!/usr/bin/env python3
"""Launch the independent Pilot CAE/CNN/TCN jobs concurrently on CPU."""

from __future__ import print_function

import argparse
import json
import subprocess
import sys
from pathlib import Path


def command_matrix(args):
    """Return fixed subprocess commands and output names for all required models.

    Each command is a module invocation under the current interpreter.  When
    this launcher is called through ``conda run -n DL``, all children therefore
    inherit exactly the selected CPU PyTorch runtime rather than accidentally
    falling back to the system Python.
    """

    common = ["--training-config", str(args.training_config), "--model-config", str(args.model_config)]
    return [
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


def main():
    """Run all independent model jobs and fail only after collecting every status."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows-dir", required=True, type=Path)
    parser.add_argument("--label-dir", required=True, type=Path)
    parser.add_argument("--training-config", required=True, type=Path)
    parser.add_argument("--model-config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("refusing to overwrite model version directory: {}".format(args.output_dir))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    running = []
    for name, command in command_matrix(args):
        output = args.output_dir / name
        log_path = args.output_dir / (name + ".log")
        # Child scripts own their model directory and refuse an existing path.
        # The separate log file bounds diagnostics to textual epoch summaries;
        # no raw waveform, tensor dump, or epoch-checkpoint directory is made.
        log = log_path.open("w", encoding="utf-8")
        process = subprocess.Popen([*command, "--output-dir", str(output)], stdout=log, stderr=subprocess.STDOUT)
        running.append((name, process, log, command, log_path))
    results = []
    for name, process, log, command, log_path in running:
        exit_code = process.wait()
        log.close()
        results.append({"name": name, "exit_code": exit_code, "command": command, "log": log_path.name})
    manifest = {"schema_version": 1, "runtime_python": sys.executable, "jobs": results}
    (args.output_dir / "parallel_training_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    failed = [result for result in results if result["exit_code"] != 0]
    if failed:
        raise SystemExit("parallel model jobs failed: {}".format([result["name"] for result in failed]))


if __name__ == "__main__":
    main()
