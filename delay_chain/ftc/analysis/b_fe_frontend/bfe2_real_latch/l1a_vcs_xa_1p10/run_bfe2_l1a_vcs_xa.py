#!/usr/bin/env python3
"""Run the bounded B-FE2-L1A VCS+PrimeSim XA latch-boundary experiment.

This file intentionally owns a new task directory and never edits the prior
0.95 V L1A causal-isolation products.  The frozen B-FE2.2C source traces are
used only to generate the Level-0 threshold event schedule.  VCS drives those
events as digital ``safe_d`` crossings, XA converts the crossings into analog
ports, and the analog wrapper contains thirty real ``LATQ_X0P5M_A9TR40``
cells.  This is a real VCS-XA mixed-signal latch-boundary co-simulation; it is
not a transistor-level simulation of the 4/0 sensing chain or a physical
level-shifter signoff.

The data level is deliberately kept separate from the capture supply:
``safe_d`` is restored to 0.95 V by the frozen rule, while every latch VDD/VNW
port is tied to the stable 1.10 V ``PD_SAFE`` rail and every VPW/VSS port is
tied to the safe-domain ground.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

FTC_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import bfe1_frontend  # noqa: E402

SOURCE_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "real_snapshot" / "corrected_seed_534p525ps"
SOURCE_MANIFEST = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "real_snapshot" / "BFE2_2C_SCENARIO_MANIFEST.json"
CELLS = FTC_ROOT / "discovery" / "selected_cells.json"
AUDIT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "BFE2_0_LATCH_CELL_AUDIT.json"
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "l1a_vcs_xa_1p10"
REPORT_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "l1a_vcs_xa_1p10"
SCENARIOS = ("BFE2L-095-N", "BFE2L-095-L2")
SAMPLE_CLOSE_PS = 534.524618567
PD_SAFE_V = 1.10
SAFE_D_HIGH_V = 0.95
THRESHOLD_FRACTION = 0.5
STOP_S = 7.0e-9


def sha256(path: Path) -> str:
    """Hash an evidence file in streaming chunks for reproducibility."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    """Read one object-shaped JSON contract and reject malformed manifests."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def source_path(scenario: str) -> Path:
    """Return the immutable B-FE2.2C trace for one authorized scenario."""

    return SOURCE_ROOT / scenario.lower().replace("-", "_") / "bfe2c_corrected.tr0"


def source_deck_path(scenario: str) -> Path:
    """Return the immutable source deck paired with a retained trace."""

    return source_path(scenario).with_suffix(".sp")


def validate_inputs() -> List[Mapping[str, Any]]:
    """Check every frozen identity before generating any VCS/XA input."""

    manifest = load_json(SOURCE_MANIFEST)
    entries = manifest.get("scenarios")
    if not isinstance(entries, list) or tuple(item.get("scenario_id") for item in entries) != SCENARIOS:
        raise ValueError("L1A requires exactly the frozen normal/L2 pair")
    if abs(float(manifest["requested_close_ps"]) - SAMPLE_CLOSE_PS) > 1.0e-6:
        raise ValueError("sample_close drifted from B-FE2-L0")
    for entry in entries:
        scenario = str(entry["scenario_id"])
        trace = source_path(scenario)
        deck = source_deck_path(scenario)
        if not trace.is_file() or not deck.is_file():
            raise FileNotFoundError("missing frozen source for {}".format(scenario))
        if sha256(trace) != entry["tr0_sha256"] or sha256(deck) != entry["deck_sha256"]:
            raise ValueError("source SHA mismatch for {}".format(scenario))
        if float(entry["baseline_v"]) != 0.95 or (scenario.endswith("-L2") and float(entry["droop_v"]) != 0.86):
            raise ValueError("source voltage signature changed for {}".format(scenario))
        if entry.get("electrical_signature", {}).get("xor_cell") != "XOR2_X0P5M_A9TL40":
            raise ValueError("XOR identity changed for {}".format(scenario))
    cells = load_json(CELLS)
    if cells["latch"]["cell"] != "LATQ_X0P5M_A9TR40":
        raise ValueError("real latch identity changed")
    audit = load_json(AUDIT)
    if audit["cdl_ports"] != ["Q", "VDD", "VNW", "VPW", "VSS", "D", "G"]:
        raise ValueError("real latch port order changed")
    return entries


def crossing_schedule(times: Sequence[float], values: Sequence[float], rail: Sequence[float]) -> List[Tuple[float, int]]:
    """Convert a source XOR trace into exact Level-0 binary events.

    Linear interpolation is applied only at the frozen ``0.5*VDD_SENSE``
    crossing.  No delay, edge slew, hysteresis, pulse filtering, or X-region is
    introduced.  Returned times are absolute seconds and values are 0/1 logic
    states suitable for the VCS event driver.
    """

    delta = [v - THRESHOLD_FRACTION * r for v, r in zip(values, rail)]
    state = 1 if delta[0] > 0.0 else 0
    events: List[Tuple[float, int]] = []
    for index in range(1, len(delta)):
        left, right = delta[index - 1], delta[index]
        if left == 0.0:
            crossing = times[index - 1]
        elif left * right > 0.0 or right == left:
            continue
        else:
            crossing = times[index - 1] + (-left / (right - left)) * (times[index] - times[index - 1])
        next_state = 1 if right >= left else 0
        if next_state != state:
            events.append((crossing, next_state))
            state = next_state
    return events


def spice(value: float) -> str:
    """Render a finite SI number in a locale-independent SPICE spelling."""

    return "{:.12e}".format(float(value))


def scalar_pwl(times: Sequence[float], values: Sequence[float]) -> List[Tuple[float, float]]:
    """Keep a frozen source voltage column as explicit PWL points."""

    return list(zip(times, values))


def pwl(name: str, node: str, points: Iterable[Tuple[float, float]]) -> str:
    """Render one explicit source-domain probe PWL source."""

    return "V_{} {} 0 PWL({})".format(name.upper(), node, " ".join("{} {}".format(spice(t), spice(v)) for t, v in points))


def port_names(prefix: str) -> List[str]:
    """Return the thirty scalar ports in stable tap order."""

    return ["{}_{}".format(prefix, tap) for tap in range(30)]


def render_wrapper(scenario: str, columns: Mapping[str, List[float]], times: Sequence[float]) -> str:
    """Build the XA wrapper with explicit safe-domain wiring and probes."""

    d_ports = port_names("safe_d")
    q_ports = port_names("q")
    ports = d_ports + ["latch_g"] + q_ports
    lines = [
        "* B-FE2-L1A VCS-XA wrapper; scenario={}.".format(scenario),
        "* VCS digital safe_d/latch_g ports are converted at this cell boundary.",
        "* safe_d data is restored to exactly 0.95 V; latch PD_SAFE is 1.10 V.",
        ".SUBCKT bfe2_l1a_ams \\",
        "+ " + " \\\n+".join(ports),
        "* Frozen source-domain reference probes (not live transistor sensing).",
        pwl("vdd_sense", "vdd_sense", scalar_pwl(times, columns[bfe1_frontend.label_for("vdd_monitored")])),
        "V_VDD_SAFE vdd_safe 0 DC 1.100000000000e+00",
        "V_VSS_SAFE vss_safe 0 DC 0",
        "* The bridge's D2A high level is normalized by a zero-delay ideal source.",
        "* This source has no slew, delay, hysteresis, pulse filter, or X-region.",
    ]
    # Store the original XOR PWLs to make the causal source ledger auditable in
    # the same XA database as safe_d, Q, G, VDD_SAFE, and VDD_SENSE.
    for tap in range(30):
        xor_node = "xor_{:02d}".format(tap)
        lines.append(pwl(xor_node, xor_node, scalar_pwl(times, columns[bfe1_frontend.label_for("xor_{}".format(tap))])))
    for tap in range(30):
        # The gain is deliberately explicit: if the bridge uses 1.10 V as its
        # digital high, the latch D input is still the required 0.95 V level.
        lines.append("E_SAFE_D_{:02d} safe_d_r_{:02d} 0 safe_d_{} 0 {:.12e}".format(tap, tap, tap, SAFE_D_HIGH_V / PD_SAFE_V))
    # E-source syntax is output+ output- control+ control- gain.  The explicit
    # control return keeps latch_g referenced to the same safe-domain ground.
    lines.append("E_LATCH_G latch_g_r 0 latch_g 0 0.999999999999")
    lines.append("* LATQ positional order: Q VDD VNW VPW VSS D G.")
    for tap in range(30):
        lines.append("XLATCH_{:02d} q_{:02d} vdd_safe vdd_safe vss_safe vss_safe safe_d_r_{:02d} latch_g_r LATQ_X0P5M_A9TR40".format(tap, tap, tap))
    lines.append("* Probe every required analog boundary and every latch output.")
    probe = ["v(vdd_sense)", "v(vdd_safe)", "v(latch_g_r)"]
    probe += ["v(xor_{:02d})".format(tap) for tap in range(30)]
    probe += ["v(safe_d_r_{:02d})".format(tap) for tap in range(30)]
    probe += ["v(q_{:02d})".format(tap) for tap in range(30)]
    lines += [".probe tran {}".format(" ".join(probe)), ".tran 1p {:.12e}".format(STOP_S), ".ENDS bfe2_l1a_ams", ""]
    return "\n".join(lines)


def render_tb(schedules: Mapping[int, Sequence[Tuple[float, int]]], close_ps: float) -> str:
    """Build non-synthesizable VCS glue that drives only frozen events.

    Each scalar port is documented at the module boundary.  Separate initial
    blocks keep the thirty independent D2A crossings explicit in the generated
    source and make a missing tap immediately visible during elaboration.
    """

    d_ports = port_names("safe_d")
    q_ports = port_names("q")
    lines = [
        "// B-FE2-L1A VCS-XA testbench; generated from immutable B-FE2.2C trace.",
        "// This is simulation glue only and is intentionally not synthesizable.",
        "`timescale 1ps/1ps",
        "module bfe2_l1a_vcs_xa;",
        "    // Each safe_d_i is a source-domain Level-0 restored logic crossing.",
        "    // XA converts it to analog and the wrapper forces its data high to 0.95 V.",
    ]
    for name in d_ports:
        lines.append("    logic {};".format(name))
    lines += [
        "    // latch_g is the one trusted safe-domain active-high gate; it falls",
        "    // exactly once at 534.524618567 ps and is never swept or retimed.",
        "    logic latch_g;",
        "    // q_i are A2D-returned outputs of the thirty real LATQ cells.",
    ]
    for name in q_ports:
        lines.append("    wire {};".format(name))
    lines += ["", "    // Explicit scalar port mapping preserves the audited 30-tap order.", "    bfe2_l1a_ams u_ams (\n"]
    maps = ["        .{}({})".format(name, name) for name in d_ports + ["latch_g"] + q_ports]
    lines.append(",\n".join(maps))
    lines += ["    );", "", "    // One trusted falling edge; no second close is permitted.", "    initial begin", "        latch_g = 1'b1;", "        #( {:.12f} ) latch_g = 1'b0;".format(close_ps), "    end", ""]
    for tap, name in enumerate(d_ports):
        lines += ["    // Tap {:02d}: threshold-event schedule generated from xor_{:02d}.".format(tap, tap), "    initial begin", "        {} = 1'b{};".format(name, 0 if not schedules[tap] or schedules[tap][0][1] == 0 else 1)]
        previous = 0.0
        first = True
        for event_time_s, state in schedules[tap]:
            absolute_ps = event_time_s * 1.0e12
            delay_ps = absolute_ps if first else absolute_ps - previous
            if delay_ps < 0.0:
                raise ValueError("non-monotonic schedule for tap {}".format(tap))
            lines.append("        #( {:.12f} ) {} = 1'b{};".format(delay_ps, name, state))
            previous = absolute_ps
            first = False
        lines += ["    end", ""]
    lines += [
        "    // XA analog evidence file. $snps_get_volt is diagnostic only: it",
        "    // reads the analog nodes owned by the real XA wrapper and never",
        "    // feeds a digital decision or changes capture behavior.",
        "    integer evidence_fd;",
        "    real analog_sample;",
        "    initial begin",
        "        evidence_fd = $fopen(\"xa_boundary_samples.csv\", \"w\");",
        "        $fwrite(evidence_fd, \"kind,time_ps,tap,safe_d_v,q_v,vdd_sense_v,vdd_safe_v,g_v\\n\");",
        "        #( {:.12f} );".format(close_ps + 100.0),
    ]
    for tap in range(30):
        lines += [
            "        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_{:02d});".format(tap),
            "        $fwrite(evidence_fd, \"post_close,%.6f,{},%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_{:02d}), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));".format(tap, tap),
        ]
    lines += ["        #( 1000.0 );"]
    for tap in range(30):
        lines += [
            "        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_{:02d});".format(tap),
            "        $fwrite(evidence_fd, \"tail_1ns,%.6f,{},%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_{:02d}), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));".format(tap, tap),
        ]
    # The final sample is scheduled one ps before the fixed 7 ns stop so the
    # evidence file is closed before the independent $finish block executes.
    lines += ["        #( {:.12f} );".format(STOP_S * 1.0e12 - (close_ps + 100.0 + 1000.0) - 1.0)]
    for tap in range(30):
        lines += [
            "        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_{:02d});".format(tap),
            "        $fwrite(evidence_fd, \"final,%.6f,{},%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_{:02d}), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));".format(tap, tap),
        ]
    lines += ["        $fclose(evidence_fd);", "    end", ""]
    lines += [
        "    // A2D Q transitions are logged independently of periodic analog",
        "    // samples to retain every observable post-close crossing.",
    ]
    for tap, name in enumerate(q_ports):
        lines += [
            "    always @({}) begin".format(name),
            "        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_{:02d});".format(tap),
            "        $fwrite(evidence_fd, \"q_event,%.6f,{},%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_{:02d}), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));".format(tap, tap),
            "    end",
            "",
        ]
    lines += [
        "    // Keep the XA transient alive through the complete retained source window.",
        "    initial begin",
        "        #( {:.6f} ) $finish;".format(STOP_S * 1.0e12),
        "    end",
        "endmodule",
        "",
    ]
    return "\n".join(lines)


def prepare_scenario(entry: Mapping[str, Any]) -> Dict[str, Any]:
    """Generate one self-contained scenario directory and its evidence ledger."""

    scenario = str(entry["scenario_id"])
    directory = RUN_ROOT / scenario.lower().replace("-", "_")
    directory.mkdir(parents=True, exist_ok=True)
    # The vendor LVT CDL contains a relative .INCLUDE of this compatibility
    # file.  XA resolves that include from its working directory, so keep a
    # task-local copy and never alter the vendor library tree.
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    trace = bfe1_frontend.parse_ascii_tr0(source_path(scenario))
    columns = trace["columns"]
    times = columns["time"]
    schedules = {}
    ledger = {}
    for tap in range(30):
        events = crossing_schedule(times, columns[bfe1_frontend.label_for("xor_{}".format(tap))], columns[bfe1_frontend.label_for("vdd_monitored")])
        schedules[tap] = events
        ledger["tap_{:02d}".format(tap)] = [{"time_ps": t * 1.0e12, "logic_state": state} for t, state in events]
    (directory / "safe_d_crossing_ledger.json").write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (directory / "bfe2_l1a_ams_wrapper.sp").write_text(render_wrapper(scenario, columns, times), encoding="ascii")
    (directory / "tb_bfe2_l1a_vcs_xa.sv").write_text(render_tb(schedules, bfe1_frontend.LAUNCH_S * 1.0e12 + SAMPLE_CLOSE_PS), encoding="ascii")
    (directory / "xa.cfg").write_text("set_sim_level 7\nset_waveform -format fsdb\n" + "\n".join(["probe_waveform_voltage vdd_sense", "probe_waveform_voltage vdd_safe", "probe_waveform_voltage latch_g_r"] + ["probe_waveform_voltage safe_d_r_{:02d}".format(tap) for tap in range(30)] + ["probe_waveform_voltage q_{:02d}".format(tap) for tap in range(30)]) + "\n", encoding="ascii")
    # VCS-XA W-2024.09 accepts only bridge selection in vcsAD.init.  Solver
    # level and waveform commands belong exclusively to xa.cfg; duplicating
    # them here causes MSV-CCF-ERR before any analog netlist is elaborated.
    (directory / "vcsAD.init").write_text("bus_format [%d];\nuse_spice -cell bfe2_l1a_ams;\nchoose xa -hspice {} -c {} -o {}/xa;\n".format(directory / "bfe2_l1a_ams.sp", directory / "xa.cfg", directory), encoding="ascii")
    deck = render_top_deck(scenario, directory)
    (directory / "bfe2_l1a_ams.sp").write_text(deck, encoding="ascii")
    return {"scenario_id": scenario, "directory": str(directory), "ledger_sha256": sha256(directory / "safe_d_crossing_ledger.json")}


def render_top_deck(scenario: str, directory: Path) -> str:
    """Render the XA top deck with local container model/library paths."""

    cells = load_json(CELLS)
    return "\n".join([
        "* B-FE2-L1A local-container VCS-XA top deck.",
        ".option post=1 probe",
        ".lib '{}' tt".format(load_json(FTC_ROOT / "ftc_config.json")["model_library"]),
        ".include '{}'".format(cells["source_files"]["rvt_cdl"]),
        ".include '{}'".format(cells["source_files"]["lvt_cdl"]),
        ".include '{}'".format(FTC_ROOT / "spice" / "empty_subckt.sp_cal"),
        ".include '{}'".format(directory / "bfe2_l1a_ams_wrapper.sp"),
        ".tran 1p {:.12e}".format(STOP_S),
        ".end",
        "",
    ])


def run_scenario(meta: Mapping[str, Any]) -> Dict[str, Any]:
    """Compile and run one scenario using the container's VCS and XA pair."""

    directory = Path(meta["directory"])
    vcs = shutil.which("vcs")
    if not vcs:
        raise RuntimeError("container VCS is unavailable")
    command = [vcs, "-full64", "-sverilog", "-timescale=1ps/1ps", "-ad=vcsAD.init", "-debug_access+all", "-o", "simv", "tb_bfe2_l1a_vcs_xa.sv"]
    compile_result = subprocess.run(command, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=900)
    (directory / "compile.log").write_text(compile_result.stdout, encoding="utf-8", errors="replace")
    if compile_result.returncode != 0:
        return {**meta, "compile_returncode": compile_result.returncode, "run_returncode": None}
    run_result = subprocess.run(["./simv"], cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=1800)
    (directory / "run.log").write_text(run_result.stdout, encoding="utf-8", errors="replace")
    return {**meta, "compile_returncode": compile_result.returncode, "run_returncode": run_result.returncode, "cosim_marker": "Start Cosim VCS-Analog Processing" in run_result.stdout, "xa_version_marker": "PrimeSim XA" in run_result.stdout}


def main() -> int:
    """Run exactly normal and L2, publish a manifest, and stop at L1A."""

    entries = validate_inputs()
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    metadata = [prepare_scenario(entry) for entry in entries]
    results = [run_scenario(item) for item in metadata]
    manifest = {
        "schema_version": 1,
        "stage": "B-FE2-L1A",
        "verification_mode": "VCS-XA mixed-signal latch-boundary co-simulation",
        "container_tools": {"vcs": os.environ.get("VCS_HOME", "W-2024.09"), "xa": os.environ.get("XA_HOME", "W-2024.09")},
        "source_manifest_sha256": sha256(SOURCE_MANIFEST),
        "source_trace_sha256": {scenario: sha256(source_path(scenario)) for scenario in SCENARIOS},
        "source_deck_sha256": {scenario: sha256(source_deck_path(scenario)) for scenario in SCENARIOS},
        "latch_cell": "LATQ_X0P5M_A9TR40",
        "latch_cdl_sha256": load_json(AUDIT)["cdl"]["sha256"],
        "fixed_sample_close_ps": SAMPLE_CLOSE_PS,
        "vdd_sense_source_v": "frozen B-FE2.2C 0.95 V normal / 0.95->0.86 V L2",
        "vdd_safe_v": PD_SAFE_V,
        "safe_d_rule": "xor > 0.5*VDD_SENSE ? 0.95 V : 0 V",
        "safe_d_high_v": SAFE_D_HIGH_V,
        "additional_delay_ps": 0.0,
        "additional_slew": "none",
        "hysteresis": "none",
        "x_region": "none",
        "scenarios": results,
    }
    (REPORT_ROOT / "BFE2_L1A_VCS_XA_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if all(item.get("compile_returncode") == 0 and item.get("run_returncode") == 0 and item.get("cosim_marker") and item.get("xa_version_marker") for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
