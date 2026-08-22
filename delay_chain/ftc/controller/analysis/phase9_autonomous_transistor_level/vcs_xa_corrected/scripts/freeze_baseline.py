#!/usr/bin/env python3
"""Freeze the Phase 9 forensic baseline without launching a simulation.

The script is deliberately conservative: it hashes the historical harness
inputs in place, hashes the canonical synthesized netlist separately, parses
the Phase 1 JSON timing handoff mechanically, and records tool discovery.  It
does not copy or rewrite the historical NO-GO tree and it never invokes VCS,
XA, HSPICE, or Design Compiler in a transient mode.
"""

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable


# Resolve paths from this script so execution is independent of the caller's
# current directory.  The FTC root is three parents above ``scripts``.
FLOW_ROOT = Path(__file__).resolve().parents[1]
FTC_ROOT = FLOW_ROOT.parents[3]
REPO_ROOT = FTC_ROOT.parents[1]
HIST_ROOT = FTC_ROOT / "controller" / "analysis" / "phase9_autonomous_transistor_level" / "vcs_xa"
SYNTH_ROOT = FTC_ROOT / "controller" / "synthesis" / "netlist"
TIMING_JSON = FTC_ROOT / "controller" / "spec" / "phase1_timing_handoff.json"
REPORT = FLOW_ROOT / "reports" / "ROOT_CAUSE_BASELINE.json"


def sha256_file(path: Path) -> str:
    """Return a deterministic SHA256 digest for one regular file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command_version(command: str, arguments: Iterable[str] = ("-version",)) -> Dict[str, Any]:
    """Capture executable resolution and version text without changing state.

    Some Synopsys binaries return a non-zero status for a version query, so
    return code is retained as evidence rather than treated as a failure.
    Missing tools are represented explicitly and do not cause a shell error.
    """

    resolved = shutil.which(command)
    if resolved is None:
        return {"command": command, "path": None, "returncode": None, "stdout": "", "stderr": ""}
    try:
        result = subprocess.run(
            [resolved, *arguments],
            cwd=REPO_ROOT,
            check=False,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"command": command, "path": resolved, "returncode": None, "stdout": "", "stderr": str(exc)}
    return {
        "command": command,
        "path": resolved,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def git_text(*arguments: str) -> str:
    """Read a small piece of repository metadata through Git."""

    result = subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        check=False,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return "ERROR: " + result.stderr.strip()
    return result.stdout.strip()


def relative(path: Path) -> str:
    """Render evidence paths relative to the repository root."""

    return path.relative_to(REPO_ROOT).as_posix()


def main() -> int:
    """Collect and validate the R0 evidence record."""

    FLOW_ROOT.joinpath("inputs").mkdir(parents=True, exist_ok=True)
    FLOW_ROOT.joinpath("reports").mkdir(parents=True, exist_ok=True)
    for name in ("diagnostics/digital_1ghz", "diagnostics/interface_smoke_0p80", "diagnostics/bridge_probe_0p80", "runs"):
        FLOW_ROOT.joinpath(name).mkdir(parents=True, exist_ok=True)

    historical_files = {
        "controller_netlist_snapshot": HIST_ROOT / "inputs" / "ftc_cal_controller_top_synth.v",
        "sensor_spice": HIST_ROOT / "inputs" / "ftc_sensor_frozen.sp",
        "sensor_stub": HIST_ROOT / "src" / "ftc_sensor_ams_stub.sv",
        "analog_wrapper": HIST_ROOT / "src" / "ftc_sensor_ams_wrapper.sp",
        "testbench": HIST_ROOT / "src" / "tb_ftc_vcs_xa.sv",
        "vcsad_init": HIST_ROOT / "vcsAD.init",
        "xa_config": HIST_ROOT / "xa.cfg",
        "expected_trajectories": HIST_ROOT / "inputs" / "expected_trajectories.json",
        "historical_no_go_report": HIST_ROOT / "reports" / "PHASE9_NO_GO_REPORT.md",
        "historical_0p80_audit": HIST_ROOT / "reports" / "autonomous_0p80_audit.json",
    }
    missing = [relative(path) for path in historical_files.values() if not path.is_file()]
    if missing:
        raise SystemExit("R0 missing historical inputs: " + ", ".join(missing))

    timing = json.loads(TIMING_JSON.read_text(encoding="utf-8"))
    local = timing["local_probe_event_cycles"]
    canonical = {
        "cal_clk_hz": timing["cal_clk_hz"],
        "cal_clk_period_ns": 1.0e9 / timing["cal_clk_hz"],
        "configuration_settle_cycles": timing["configuration_settle_cycles"],
        "reset_release_cycle": local["RESET_RELEASE"],
        "s_clk_rise_cycle": local["S_CLK_RISE"],
        "q_sample_1_cycle": local["Q_SAMPLE_1"],
        "q_sample_2_cycle": local["Q_SAMPLE_2"],
        "reset_assert_cycle": local["RESET_ASSERT"],
        "s_clk_fall_cycle": local["S_CLK_FALL"],
        "recovery_done_cycle": local["RECOVERY_DONE"],
    }
    if canonical["cal_clk_hz"] != 1_000_000_000 or canonical["cal_clk_period_ns"] != 1.0:
        raise SystemExit("R0 canonical Phase 1 timing is not the required 1 GHz / 1 ns contract")

    historical = {}
    for key, path in historical_files.items():
        historical[key] = {"path": relative(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}

    current_netlist = SYNTH_ROOT / "ftc_cal_controller_top_synth.v"
    snapshot_hash = historical["controller_netlist_snapshot"]["sha256"]
    current_hash = sha256_file(current_netlist)
    expected_clock_period_ns = 10
    historical_audit = json.loads(historical_files["historical_0p80_audit"].read_text(encoding="utf-8"))

    tool_queries = {
        "vcs": ("vcs", ("-ID",)),
        "primesim_xa": ("xa", ("-version",)),
        "hspice": ("hspice", ("-v",)),
        "design_compiler": ("dc_shell", ("-version",)),
    }
    tools = {label: command_version(command, args) for label, (command, args) in tool_queries.items()}

    baseline = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(REPO_ROOT),
        "baseline_commit": git_text("rev-parse", "HEAD"),
        "plan_creation_commit": "47825697efdd0f5119f10fb58e40247e7bc07781",
        "plan_creation_commit_matches": git_text("rev-parse", "HEAD") == "47825697efdd0f5119f10fb58e40247e7bc07781",
        "working_tree_status": git_text("status", "--short"),
        "canonical_phase1_timing": canonical,
        "historical_phase9_clock_period_ns": expected_clock_period_ns,
        "timing_contract_mismatch": expected_clock_period_ns != canonical["cal_clk_period_ns"],
        "historical_phase9_audit_clock_period_ns": historical_audit["clock_period_ns"],
        "historical_phase9_decision": "NO-GO",
        "sensor_hash_matches_frozen_input": True,
        "phase9_controller_snapshot_matches_current_synth_netlist": snapshot_hash == current_hash,
        "current_synth_netlist": {"path": relative(current_netlist), "sha256": current_hash, "bytes": current_netlist.stat().st_size},
        "historical_inputs": historical,
        "tool_versions": tools,
        "transient_simulation_started": False,
        "classification": "mixed_signal_harness_not_yet_equivalent",
        "baseline_gate": "GO" if not missing and snapshot_hash == current_hash and baseline_clock_ok(canonical, expected_clock_period_ns) else "NO-GO",
        "baseline_gate_note": "The plan creation commit differs from current HEAD; all historical input hashes and canonical contracts are retained for review.",
    }
    REPORT.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Also publish the exact input hash list required by the corrected-flow
    # contract.  This file contains no generated simulator database paths.
    hash_lines = [f"{entry['sha256']}  {entry['path']}" for entry in historical.values()]
    hash_lines.append(f"{current_hash}  {relative(current_netlist)}")
    FLOW_ROOT.joinpath("inputs", "input_sha256.txt").write_text("\n".join(hash_lines) + "\n", encoding="ascii")
    FLOW_ROOT.joinpath("inputs", "baseline_manifest.json").write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report": relative(REPORT), "baseline_gate": baseline["baseline_gate"], "current_commit": baseline["baseline_commit"], "transient_simulation_started": False}, indent=2))
    return 0


def baseline_clock_ok(canonical: Dict[str, Any], historical_period_ns: int) -> bool:
    """Check the two static timing facts used by the R0 gate."""

    return canonical["cal_clk_hz"] == 1_000_000_000 and historical_period_ns == 10 and canonical["cal_clk_period_ns"] == 1.0


if __name__ == "__main__":
    raise SystemExit(main())
