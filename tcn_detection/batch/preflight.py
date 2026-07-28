#!/usr/bin/env python3
"""Validate local HSPICE, tmux, host capacity, and batch disk headroom."""

from __future__ import print_function

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def mem_available_gib():
    """Read Linux MemAvailable without requiring a nonstandard Python package."""

    for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
        if line.startswith("MemAvailable:"):
            return float(line.split()[1]) / float(1024 ** 2)
    raise RuntimeError("/proc/meminfo has no MemAvailable")


def main():
    """Fail fast before any HSPICE work directory or tmux window is created."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    config_path = ROOT / "power_macro" / "tcn_detection" / "config" / "execution_v1.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    hspice = Path(config["hspice_executable"]).resolve()
    if str(hspice) != "/home/zhupl25/.local/bin/hspice" or not os.access(str(hspice), os.X_OK):
        raise RuntimeError("required local HSPICE is unavailable: {}".format(hspice))
    version = subprocess.check_output([str(hspice), "-v"], stderr=subprocess.STDOUT, universal_newlines=True, timeout=30)
    if config["required_hspice_version"] not in version:
        raise RuntimeError("HSPICE version mismatch: {}".format(version))
    tmux_version = subprocess.check_output(["tmux", "-V"], universal_newlines=True).strip()
    free_gib = shutil.disk_usage(str(args.run_dir)).free / float(1024 ** 3)
    required_gib = float(config["minimum_free_gib"]) + int(config["worker_count"]) * float(config["per_active_trace_gib"])
    if free_gib < required_gib:
        raise RuntimeError("insufficient disk: {:.2f} GiB < {:.2f} GiB".format(free_gib, required_gib))
    available = mem_available_gib()
    if available < 256.0:
        raise RuntimeError("insufficient available RAM: {:.2f} GiB".format(available))
    print(json.dumps({"hspice": str(hspice), "hspice_version": version.strip(), "tmux": tmux_version,
                      "free_gib": round(free_gib, 3), "required_gib": required_gib, "mem_available_gib": round(available, 3)}, sort_keys=True))


if __name__ == "__main__":
    main()
