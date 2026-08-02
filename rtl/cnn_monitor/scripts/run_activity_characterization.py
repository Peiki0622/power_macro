#!/usr/bin/env python3
"""Run deterministic RTL VCD characterization under one task-scoped run."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from power_macro.rtl.cnn_monitor.scripts.generate_activity_windows import generate


def _run(command, cwd: Path, log: Path) -> None:
    """Run one external tool and retain merged stdout/stderr as evidence."""
    with log.open("w", encoding="utf-8") as stream:
        completed = subprocess.run(command, cwd=str(cwd), stdout=stream,
                                   stderr=subprocess.STDOUT, check=False)
    if completed.returncode:
        raise RuntimeError("command failed; inspect {}".format(log))


def main() -> None:
    """Compile once, then execute every fixed pattern/repetition separately."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-tag", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    power_macro = root.parents[1]
    workspace = power_macro.parent
    run = root / "runs" / args.run_tag
    if run.exists():
        raise FileExistsError("refusing to overwrite {}".format(run))
    for directory in (run / "inputs", run / "vcd", run / "results", run / "logs", run / "csrc"):
        directory.mkdir(parents=True, exist_ok=False)
    config = root / "config" / "cnn_activity_config_v1.json"
    generate(config, run / "inputs" / "windows")
    records = [json.loads(line) for line in (run / "inputs" / "windows" / "windows.jsonl").read_text().splitlines()]
    rom_model = root / "runs" / "stage89_20260801_r1" / "rom_compiler" / "output" / "CNNW384X128.v"
    rom_rcf = root / "runs" / "stage89_20260801_r1" / "rom_compiler" / "output" / "CNNW384X128_verilog.rcf"
    if not rom_model.is_file() or not rom_rcf.is_file():
        raise FileNotFoundError("authenticated compiler ROM model/content is missing")
    shutil.copy2(rom_model, run / rom_model.name)
    shutil.copy2(rom_rcf, run / rom_rcf.name)
    vcs = os.environ.get("VCS_BIN", "/home/synopsys/vcs/W-2024.09/bin/vcs")
    compile_command = [vcs, "-full64", "-sverilog", "-timescale=1ns/1ps", "-DARM_UD_MODEL", "-DCNN_ROM_COMPILER_MODEL", "+notimingcheck", "-top", "cnn_activity_tb", str(run / rom_model.name), str(root / "rtl" / "generated" / "cnn_parameter_roms.sv"), str(root / "rtl" / "cnn_requantize_relu.sv"), str(root / "rtl" / "cnn_weight_rom.sv"), str(root / "rtl" / "cnn_window_buffer.sv"), str(root / "rtl" / "cnn_convolution_engine.sv"), str(root / "rtl" / "cnn_pool_classifier.sv"), str(root / "rtl" / "cnn_monitor.sv"), str(root / "tb" / "cnn_activity_tb.sv"), "-Mdir=" + str(run / "csrc"), "-o", str(run / "simv")]
    _run(compile_command, run, run / "logs" / "compile.log")
    repeat_count = json.loads(config.read_text())["repeat_count"]
    for record in records:
        expected = record["expected"]
        for repeat in range(repeat_count):
            stem = "{}_r{}".format(record["pattern_id"], repeat)
            vector = run / "inputs" / (stem + ".txt")
            vector.write_text(" ".join([record["pattern_id"]] + [str(value) for value in record["sensor_codes"]] + [str(expected["safe_logit"]), str(expected["critical_logit"]), str(expected["decision"])]) + "\n", encoding="ascii")
            _run([str(run / "simv"), "+notimingcheck", "+VECTOR=" + str(vector), "+VCD=" + str(run / "vcd" / (stem + ".vcd")), "+RESULT=" + str(run / "results" / (stem + ".txt"))], run, run / "logs" / (stem + ".log"))


if __name__ == "__main__":
    main()
