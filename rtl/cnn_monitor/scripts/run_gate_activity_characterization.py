#!/usr/bin/env python3
"""Run the frozen mapped CNN for every task-three window and repetition.

Only the task-two mapped netlist is compiled as DUT.  Level A omits SDF for a
functional hierarchy proof; Level B supplies the same frozen SDF and creates
the VCD/marker pairs later converted into three scope-specific SAIF files.
All mutable files are confined below the caller-selected task run directory.
"""
import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


def run(command, cwd, log):
    """Run one tool command and preserve combined output before raising failure."""
    with log.open("w", encoding="utf-8") as stream:
        status = subprocess.run(command, cwd=str(cwd), stdout=stream,
                                stderr=subprocess.STDOUT).returncode
    if status:
        raise RuntimeError("command failed; inspect {}".format(log))


def write_vector(path, record):
    """Write expected payload then exactly 32 legal sensor codes for one run."""
    expected = record["expected"]
    values = [expected["safe_logit"], expected["critical_logit"], expected["decision"]]
    values.extend(record["sensor_codes"])
    path.write_text(" ".join(str(value) for value in values) + "\n", encoding="ascii")


def compile_level(root, run_root, level, inputs):
    """Compile the mapped DUT once for one timing level, never invoking synthesis."""
    build = run_root / level / "build"
    build.mkdir(parents=True, exist_ok=False)
    vcs = os.environ.get("VCS_BIN", "/home/synopsys/vcs/W-2024.09/bin/vcs")
    command = [vcs, "-full64", "-sverilog", "-DARM_UD_MODEL", "-timescale=1ns/1ps",
               "-top", "cnn_gate_activity_tb", str(inputs["stdcell"]), str(inputs["rom"]),
               str(inputs["mapped"]), str(root / "tb" / "cnn_gate_activity_tb.sv"),
               "-Mdir=" + str(build / "csrc"), "-o", str(build / "simv")]
    if level == "gate_functional":
        # VCS resolves specify path-delay mode while elaborating the cell
        # models.  The generic library's 1 ns fallback delays therefore must
        # be suppressed at compile time, not merely passed to simv at run
        # time.  This Level-A-only option retains the mapped netlist and
        # library hierarchy while making the preflight a true zero-delay
        # connectivity/payload proof.  Level B deliberately omits it so its
        # frozen SDF remains the sole source of physical timing delays.
        command.insert(5, "+delay_mode_zero")
    if level == "gate_sdf":
        # Keep the SDF under the task-local build directory and use a compile
        # define so the testbench provides VCS with a legal constant pathname.
        shutil.copy2(inputs["sdf"], build / "cnn_monitor_mapped.sdf")
        command.insert(4, "-DGATE_SDF")
    run(command, build, build / "compile.log")
    return build / "simv"


def main():
    """Compile both required levels and execute all 36 x 3 deterministic cases."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-directory", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    # Preserve every failed gate attempt with its exact log.  r9 is the first
    # non-overwriting full run after separating the Level-A library fallback
    # delay model from the Level-B annotated physical timing model.
    run_root = args.run_directory.resolve() / "gate_characterization_r9"
    if run_root.exists():
        raise FileExistsError("refusing to overwrite {}".format(run_root))
    mapped_root = root / "runs" / "stage89_20260801_r2" / "step11_dc_500mhz_operand_prefetch_static_lanes"
    rom_root = root / "runs" / "stage89_20260801_r1" / "rom_compiler" / "output"
    inputs = {
        "mapped": mapped_root / "cnn_monitor_mapped.v",
        "sdf": mapped_root / "cnn_monitor_mapped.sdf",
        "rom": rom_root / "CNNW384X128.v",
        "rcf": rom_root / "CNNW384X128_verilog.rcf",
        "stdcell": Path("/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/verilog/sc9mc_logic0040ll_base_rvt_c40.v"),
    }
    if not all(path.is_file() for path in inputs.values()):
        raise FileNotFoundError("frozen mapped/SDF/ROM/std-cell input is missing")
    window_path = root / "runs" / "activity_codebook_20260802_r1" / "rtl_characterization" / "inputs" / "windows" / "windows.jsonl"
    records = [json.loads(line) for line in window_path.read_text().splitlines()]
    if len(records) != 36:
        raise ValueError("frozen window input is not 36 records")
    run_root.mkdir(parents=True)
    (run_root / "inputs.json").write_text(json.dumps({name: str(path) for name, path in inputs.items()}, indent=2) + "\n")
    for level in ("gate_functional", "gate_sdf"):
        simv = compile_level(root, run_root, level, inputs)
        for record in records:
            for repeat in range(3):
                stem = "{}_r{}".format(record["pattern_id"], repeat)
                case = run_root / level / "cases" / stem
                case.mkdir(parents=True)
                # The delivered ROM model uses a relative $readmem path.
                # Copy the authenticated RCF into each simulator cwd so all
                # cases consume identical immutable contents without relying
                # on an ambient working-directory search path.
                shutil.copy2(inputs["rcf"], case / "CNNW384X128_verilog.rcf")
                vector = case / "vector.txt"
                write_vector(vector, record)
                command = [str(simv), "+VECTOR=" + str(vector),
                           "+RESULT=" + str(case / "result.txt"),
                           "+MARKERS=" + str(case / "markers.txt")]
                if level == "gate_functional":
                    # Level A is a logic/hierarchy preflight.  Its unannotated
                    # library defines 1 ns generic specify delays, which are
                    # placeholders rather than this mapped design's physical
                    # timing.  Disable their checks only here; the matching
                    # compile-time delay-mode selection is made above.  The
                    # Level-B SDF invocation below intentionally receives
                    # neither waiver and is the timing-valid activity source.
                    command.append("+notimingcheck")
                run(command, case, case / "simulation.log")
                if "GATE_ACTIVITY_PASS cycles=12892" not in (case / "simulation.log").read_text(errors="replace"):
                    raise RuntimeError("gate self-check marker is missing for {}".format(stem))
                vcd_dir = run_root / level / "vcd"
                marker_dir = run_root / level / "markers"
                result_dir = run_root / level / "results"
                for directory in (vcd_dir, marker_dir, result_dir):
                    directory.mkdir(exist_ok=True)
                shutil.move(str(case / "gate_activity.vcd"), str(vcd_dir / (stem + ".vcd")))
                shutil.move(str(case / "markers.txt"), str(marker_dir / (stem + ".txt")))
                shutil.move(str(case / "result.txt"), str(result_dir / (stem + ".txt")))


if __name__ == "__main__":
    main()
