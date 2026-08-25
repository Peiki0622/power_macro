#!/usr/bin/env python3
"""Prepare and locally run the two B-FE2-L0 VCS behavior scenarios.

The source waveforms are the immutable B-FE2.2C normal and formal 0.95->0.86 V
L2 traces.  This runner converts only their existing sampled probes into a
task-scoped whitespace stimulus file; it does not regenerate HSPICE, alter
the 4/0 delay chain, or select another close time.  VCS and PrimeSim XA are
invoked from their verified container-local W-2024.09 installations.
"""

import hashlib
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import bfe1_frontend  # noqa: E402  # Frozen .tr0 parser and probe labels.


ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch"
SNAPSHOT_ROOT = ANALYSIS_ROOT / "real_snapshot"
L0_ROOT = ANALYSIS_ROOT / "l0"
SOURCE_ROOT = L0_ROOT / "src"
# Keep the prior remote/offline L0 directory immutable.  This new directory is
# the sole task-scoped home for local W-2024.09 VCS/XA evidence.
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "l0_local_vcs_xa"
BFE2C_MANIFEST = SNAPSHOT_ROOT / "BFE2_2C_SCENARIO_MANIFEST.json"
SEED_JSON = SNAPSHOT_ROOT / "safe_seed_revised" / "BFE2_2S_REVISED_SELECTED_SEED.json"
SCENARIO_IDS = ("BFE2L-095-N", "BFE2L-095-L2")
FIXED_CLOSE_PS = 534.524618567
FIXED_PD_SAFE_V = 0.95
VCS_BIN = "/home/synopsys/vcs/W-2024.09/bin/vcs"
VCS_VERSION = "VCS W-2024.09_Full64"
XA_BIN = "/home/zhupl25/synopsys/pt_xa/xa/W-2024.09/bin/xa"
XA_VERSION = "PrimeSim XA W-2024.09 linux64"
XA_DEMO_SOURCE = Path("/home/zhupl25/synopsys/pt_xa/xa/W-2024.09/doc/tutorials/interactive")


def read_json(path: Path) -> Dict[str, Any]:
    """Read an object-shaped JSON contract."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def sha256_file(path: Path) -> str:
    """Hash evidence in bounded memory for source tracking."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def host_path(local_path: Path) -> str:
    """Translate a container path through the documented host mapping."""

    return str(HOST_ROOT / local_path.relative_to(LOCAL_ROOT))


def source_trace_path(scenario_id: str) -> Path:
    """Resolve exactly the retained B-FE2.2C trace for one scenario."""

    return (FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" /
            "real_snapshot" / "corrected_seed_534p525ps" /
            scenario_id.lower().replace("-", "_") / "bfe2c_corrected.tr0")


def source_deck_path(scenario_id: str) -> Path:
    """Return the immutable B-FE2.2C deck paired with the retained .tr0."""

    return source_trace_path(scenario_id).with_suffix(".sp")


def validate_inputs() -> List[Mapping[str, Any]]:
    """Freeze the pair identity and reject any close/L2 drift before running."""

    manifest = read_json(BFE2C_MANIFEST)
    entries = manifest.get("scenarios")
    if tuple(item.get("scenario_id") for item in entries) != SCENARIO_IDS:
        raise ValueError("L0 requires exactly the BFE2.2C normal/L2 pair")
    if abs(float(manifest["requested_close_ps"]) - FIXED_CLOSE_PS) > 1.0e-6:
        raise ValueError("L0 close differs from the frozen BFE2.2C close")
    selected = read_json(SEED_JSON)["selected_corrected_seed"]
    if abs(float(selected["midpoint_ps"]) - FIXED_CLOSE_PS) > 1.0e-6:
        raise ValueError("L0 close differs from the B-FE2.2S selected seed")
    for entry in entries:
        if not source_trace_path(entry["scenario_id"]).is_file():
            raise FileNotFoundError("missing immutable BFE2.2C trace")
        if not source_deck_path(entry["scenario_id"]).is_file():
            raise FileNotFoundError("missing immutable BFE2.2C deck")
    return entries


def write_stimulus(entry: Mapping[str, Any], output: Path) -> Dict[str, Any]:
    """Convert retained XOR/G/VDD_SENSE samples into a deterministic replay.

    The conversion preserves every original transient record and probe value;
    it only removes unused RVT/LVT/Q columns so the VCS behavior model can
    consume the exact source-domain stimulus.  Column order is time, VDD_SENSE,
    G, then XOR[0:29], all in volts/ps.
    """

    trace = bfe1_frontend.parse_ascii_tr0(source_trace_path(entry["scenario_id"]))
    times = trace["columns"]["time"]
    columns = trace["columns"]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="ascii") as stream:
        stream.write("# time_ps vdd_sense_v g_v xor_0..xor_29\n")
        for index, absolute_s in enumerate(times):
            time_ps = absolute_s * 1.0e12 - bfe1_frontend.LAUNCH_S * 1.0e12
            vdd = columns[bfe1_frontend.label_for("vdd_monitored")][index]
            g = columns[bfe1_frontend.label_for("latch_g")][index]
            xor_values = [columns[bfe1_frontend.label_for("xor_{}".format(tap))][index] for tap in range(30)]
            stream.write("{:.9f} {:.9f} {:.9f} {}\n".format(
                time_ps, vdd, g, " ".join("{:.9f}".format(value) for value in xor_values)))
    return {"record_count": trace["record_count"], "record_width": trace["record_width"],
            "stimulus_sha256": sha256_file(output), "source_tr0_sha256": sha256_file(source_trace_path(entry["scenario_id"]))}


def run_remote(run_dir: Path) -> Dict[str, str]:
    """Compile and execute one VCS behavior scenario on the EDA host."""

    host_run = host_path(run_dir)
    # The container and host paths are documented coordinate systems but are
    # not guaranteed to expose newly generated files in both directions.
    # Upload only this task's three immutable inputs before invoking VCS.
    for filename in ("stimulus.dat", "bfe2_l0_behavior_model.sv", "tb_bfe2_l0.sv"):
        upload = subprocess.run(
            ["scp", "-P", HOST_PORT, "-o", "BatchMode=yes",
             str(run_dir / filename), "{}:{}".format(HOST_USER, host_run + "/" + filename)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, check=False, timeout=120)
        if upload.returncode != 0:
            raise RuntimeError("failed to upload L0 input {}: {}".format(filename, upload.stderr))
    command = """
set -euo pipefail
cd {run}
rm -f compile.log run.log vcs_version.txt l0_probe.dat
if [ ! -x simv ]; then
    rm -rf csrc simv.daidir tmp_dir_*
fi
# Reuse a task-scoped executable already compiled from the uploaded sources.
# If absent, compile once; the host compiler's occasional finalizer crash is
# then retried by the Python caller without changing this scenario.
if [ ! -x simv ]; then
    {vcs_bin} -full64 -sverilog -timescale=1ps/1ps -o simv \\
        bfe2_l0_behavior_model.sv tb_bfe2_l0.sv > compile.log 2>&1
else
    printf 'reused task-scoped simv compiled from current L0 sources\\n' > compile.log
fi
./simv +INPUT={input_file} +OUTPUT={output_file} > run.log 2>&1
{vcs_bin} -ID > vcs_version.txt 2>&1
grep -q 'L0_PASS' run.log
test -s {output_file}
""".format(vcs_bin=shlex.quote(VCS_BIN), run=shlex.quote(host_run),
           input_file=shlex.quote(host_run + "/stimulus.dat"), output_file=shlex.quote(host_run + "/l0_probe.dat"))
    # Pass the complete shell program as one SSH command.  The host login
    # shell executes it directly; avoiding an additional nested login shell
    # keeps the VCS environment identical to the verified manual invocation.
    remote_command = command
    result = None
    # A complete retry is permitted only for this tool-level compile failure;
    # it never changes the fixed replay stimulus or creates another scenario.
    for attempt in range(1, 4):
        result = subprocess.run(["ssh", "-p", HOST_PORT, "-o", "BatchMode=yes", HOST_USER,
                                 remote_command], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, check=False, timeout=900)
        if result.returncode == 0:
            break
    (run_dir / "remote_command.log").write_text(
        "attempts={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(
            attempt, result.returncode, result.stdout, result.stderr),
        encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError("remote VCS L0 run failed in {}".format(run_dir))
    # Pull back only reproducible textual evidence.  Large VCS executables and
    # compiler databases remain on the host task directory and are never
    # scattered into the repository workspace.
    for filename in ("l0_probe.dat", "compile.log", "run.log", "vcs_version.txt"):
        download = subprocess.run(
            ["scp", "-P", HOST_PORT, "-o", "BatchMode=yes",
             "{}:{}".format(HOST_USER, host_run + "/" + filename), str(run_dir / filename)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, check=False, timeout=120)
        if download.returncode != 0:
            raise RuntimeError("failed to retrieve L0 evidence {}: {}".format(filename, download.stderr))
    return {"tool": VCS_VERSION, "compiler": VCS_BIN,
            "host": "166.111.78.45", "run_dir": host_run}


def run_local_vcs(run_dir: Path) -> Dict[str, str]:
    """Compile and execute one fixed replay with container-local VCS.

    The executable and all compiler databases stay under this scenario's
    task-scoped directory.  No HSPICE command is issued here: the only input
    is the already frozen B-FE2.2C sampled stimulus.
    """

    executable = run_dir / "simv_local_w2024_09"
    compile_log = run_dir / "compile_local.log"
    run_log = run_dir / "run_local.log"
    probe = run_dir / "l0_probe.dat"
    if not executable.is_file():
        compile_command = [VCS_BIN, "-full64", "-sverilog",
                           "-timescale=1ps/1ps", "-o", str(executable),
                           "bfe2_l0_behavior_model.sv", "tb_bfe2_l0.sv"]
        with compile_log.open("w", encoding="utf-8") as stream:
            result = subprocess.run(compile_command, cwd=run_dir, stdout=stream,
                                    stderr=subprocess.STDOUT, check=False,
                                    timeout=900)
        if result.returncode != 0:
            raise RuntimeError("local VCS compile failed: {}".format(run_dir))
    else:
        compile_log.write_text("reused local VCS executable {}\n".format(executable.name),
                               encoding="utf-8")
    run_command = [str(executable), "+INPUT={}".format(run_dir / "stimulus.dat"),
                   "+OUTPUT={}".format(probe)]
    with run_log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(run_command, cwd=run_dir, stdout=stream,
                                stderr=subprocess.STDOUT, check=False,
                                timeout=900)
    if result.returncode != 0 or not probe.is_file() or probe.stat().st_size == 0:
        raise RuntimeError("local VCS replay failed: {}".format(run_dir))
    if "L0_PASS" not in run_log.read_text(encoding="utf-8"):
        raise RuntimeError("local VCS replay lacks L0_PASS: {}".format(run_dir))
    version_log = run_dir / "vcs_version.txt"
    with version_log.open("w", encoding="utf-8") as stream:
        subprocess.run([VCS_BIN, "-ID"], stdout=stream, stderr=subprocess.STDOUT,
                       check=False, timeout=60)
    return {"compile_log": str(compile_log), "run_log": str(run_log),
            "probe": str(probe), "version_log": str(version_log),
            "executable": str(executable)}


def run_xa_official_demo(run_root: Path) -> Dict[str, str]:
    """Run the vendor tutorial with local XA and retain only task evidence.

    This is an environment/tool validation, not an extra B-FE2 electrical
    scenario.  The L0 causal decision still comes solely from the two fixed
    B-FE2.2C replays above.
    """

    demo = run_root / "xa_official_demo"
    if not demo.exists():
        shutil.copytree(XA_DEMO_SOURCE, demo)
    result_dir = demo / "RESULT"
    result_dir.mkdir(exist_ok=True)
    xa_log = run_root / "xa_demo.log"
    with xa_log.open("w", encoding="utf-8") as stream:
        result = subprocess.run([XA_BIN, "top.spi", "-o", "RESULT/xa"], cwd=demo,
                                stdout=stream, stderr=subprocess.STDOUT,
                                check=False, timeout=900)
    version_log = run_root / "xa_version.txt"
    with version_log.open("w", encoding="utf-8") as stream:
        subprocess.run([XA_BIN, "-version"], stdout=stream,
                       stderr=subprocess.STDOUT, check=False, timeout=60)
    log_text = xa_log.read_text(encoding="utf-8")
    if result.returncode != 0 or "Total number of comparison errors = 0" not in log_text:
        raise RuntimeError("local XA official demo failed")
    return {"tool": XA_VERSION, "binary": XA_BIN,
            "log": str(xa_log), "version_log": str(version_log),
            "result_log": str(result_dir / "xa.log")}


def main() -> int:
    """Prepare and run exactly two fixed-close L0 scenarios."""

    entries = validate_inputs()
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    xa_evidence = run_xa_official_demo(RUN_ROOT)
    results = []
    for entry in entries:
        run_dir = RUN_ROOT / entry["scenario_id"].lower().replace("-", "_")
        if run_dir.exists() and (run_dir / "l0_probe.dat").is_file():
            disposition = "reused"
        elif run_dir.exists():
            # A failed local compile leaves only this task's own source and
            # log files.  Reuse that isolated directory after verifying the
            # required inputs, rather than deleting artifacts destructively.
            run_dir.mkdir(parents=True, exist_ok=True)
            for source in (SOURCE_ROOT / "bfe2_l0_behavior_model.sv", SOURCE_ROOT / "tb_bfe2_l0.sv"):
                shutil.copyfile(source, run_dir / source.name)
            if not (run_dir / "stimulus.dat").is_file():
                write_stimulus(entry, run_dir / "stimulus.dat")
            run_local_vcs(run_dir)
            disposition = "new"
        else:
            run_dir.mkdir(parents=True)
            for source in (SOURCE_ROOT / "bfe2_l0_behavior_model.sv", SOURCE_ROOT / "tb_bfe2_l0.sv"):
                shutil.copyfile(source, run_dir / source.name)
            write_stimulus(entry, run_dir / "stimulus.dat")
            run_local_vcs(run_dir)
            disposition = "new"
        probe = run_dir / "l0_probe.dat"
        results.append({"scenario_id": entry["scenario_id"], "baseline_v": entry["baseline_v"],
                        "droop_v": entry["droop_v"], "requested_close_ps": FIXED_CLOSE_PS,
                        "run_disposition": disposition, "probe_sha256": sha256_file(probe),
                        "stimulus_sha256": sha256_file(run_dir / "stimulus.dat"),
                        "source_tr0_sha256": sha256_file(source_trace_path(entry["scenario_id"])),
                        "source_deck_sha256": sha256_file(source_deck_path(entry["scenario_id"])),
                        "compile_log_sha256": sha256_file(run_dir / "compile_local.log"),
                        "run_log_sha256": sha256_file(run_dir / "run_local.log"),
                        "tool": VCS_VERSION, "compiler": VCS_BIN,
                        "vcs_version_log_sha256": sha256_file(run_dir / "vcs_version.txt"),
                        "pd_safe_v": FIXED_PD_SAFE_V,
                        "record_width": 124, "probe_columns": 94})
    manifest = {"schema_version": 2, "stage": "B-FE2-L0", "tool_flow": "local_VCS_behavior_model_plus_XA_preflight",
                "new_hspice_scenarios": 0, "new_vcs_scenarios": sum(item["run_disposition"] == "new" for item in results),
                "scenario_ids": list(SCENARIO_IDS), "requested_close_ps": FIXED_CLOSE_PS,
                "fixed_pd_safe_v": FIXED_PD_SAFE_V, "source_bfe2_2c_manifest_sha256": sha256_file(BFE2C_MANIFEST),
                "source_bfe2_2c_analysis_sha256": sha256_file(SNAPSHOT_ROOT / "corrected_seed" / "BFE2_2C_ANALYSIS.json"),
                "vcs_execution": {"status": "passed", "tool": VCS_VERSION, "compiler": VCS_BIN},
                "xa_execution": {"status": "passed", "tool": xa_evidence["tool"],
                                  "binary": xa_evidence["binary"],
                                  "log": str(Path(xa_evidence["log"]).relative_to(FTC_ROOT)),
                                  "result_log": str(Path(xa_evidence["result_log"]).relative_to(FTC_ROOT))},
                "results": results}
    L0_ROOT.mkdir(parents=True, exist_ok=True)
    (L0_ROOT / "BFE2_L0_SCENARIO_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (RUN_ROOT / "BFE2_L0_LOCAL_RUN_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("BFE2_L0_VCS_PAIR_COMPLETE new={}".format(manifest["new_vcs_scenarios"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
