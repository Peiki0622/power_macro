#!/usr/bin/env python3
"""Run the narrow B-FE2-L1A-R stimulus-repair experiment.

The previous L1A VCS-XA bench inferred a tap's time-zero ``safe_d`` state
from the first *future* threshold crossing.  That is incorrect whenever the
source starts below threshold, and it initialized every frozen B-FE2.2C tap
high.  This runner keeps the same VCS+PrimeSim XA path and real latch cell,
but carries the source-derived initial state explicitly for every tap:
``safe_d_i(0) = 0.95 V`` iff ``xor_i(0) > 0.5*VDD_SENSE(0)``.  After t=0,
only genuine crossings of that same relative threshold create digital events.

The runner is intentionally task-scoped.  It reads the immutable B-FE2.2C
normal/L2 traces, generates local bridge/deck files, runs exactly those two
scenarios, and writes a standalone manifest.  Capture analysis is performed
by the companion ``analyze_bfe2_l1a_r_vcs_xa.py`` script.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


# Reuse only the immutable-source and bridge discovery helpers from the prior
# runner; all generated files, constants, and stimulus scheduling below are
# local to L1A-R so the contaminated L1A evidence remains untouched.
PREVIOUS_ROOT = Path(__file__).resolve().parents[1] / "l1a_vcs_xa_1p10"
sys.path.insert(0, str(PREVIOUS_ROOT))
import run_bfe2_l1a_vcs_xa as previous  # noqa: E402


FTC_ROOT = previous.FTC_ROOT
SOURCE_MANIFEST = previous.SOURCE_MANIFEST
CELLS = previous.CELLS
AUDIT = previous.AUDIT
SOURCE_ROOT = previous.SOURCE_ROOT
SCENARIOS = previous.SCENARIOS
SAMPLE_CLOSE_PS = 534.524618567
# The stage contract names the launch as exactly 1000 ps.  Do not inherit a
# binary floating-point representation of the parser's seconds constant when
# emitting the fixed G close or its manifest.
LAUNCH_PS = 1000.0
# Keep the decimal contract itself as the manifest value; adding binary
# floating-point seconds can render the last digit as 5669998/5680002.
FIXED_G_CLOSE_PS = 1534.524618567
PD_SAFE_V = 0.95
SAFE_D_HIGH_V = 0.95
THRESHOLD_FRACTION = 0.5
STOP_S = 7.0e-9
STAGE = "B-FE2-L1A-R"
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "l1a_r_vcs_xa"
REPORT_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch" / "l1a_r_vcs_xa"


def sha256(path: Path) -> str:
    """Hash one retained input or generated evidence file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    """Read and type-check one object-shaped JSON contract."""

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
    """Reject any source, close, cell, or port drift before generation."""

    entries = previous.validate_inputs()
    manifest = load_json(SOURCE_MANIFEST)
    if tuple(item["scenario_id"] for item in entries) != SCENARIOS:
        raise ValueError("L1A-R requires exactly the frozen normal/L2 pair")
    if abs(float(manifest["requested_close_ps"]) - SAMPLE_CLOSE_PS) > 1.0e-6:
        raise ValueError("sample_close changed from the frozen B-FE2.2C value")
    if float(PD_SAFE_V) != 0.95 or float(SAFE_D_HIGH_V) != 0.95:
        raise ValueError("L1A-R safe-domain rail/restoration is not 0.95 V")
    cells = load_json(CELLS)
    if cells["latch"]["cell"] != "LATQ_X0P5M_A9TR40":
        raise ValueError("real capture latch identity changed")
    audit = load_json(AUDIT)
    if audit["cdl_ports"] != ["Q", "VDD", "VNW", "VPW", "VSS", "D", "G"]:
        raise ValueError("LATQ positional port contract changed")
    return entries


def spice(value: float) -> str:
    """Render a finite SI value in locale-independent SPICE notation."""

    return "{:.12e}".format(float(value))


def threshold_schedule(times: Sequence[float], xor: Sequence[float], vdd_sense: Sequence[float]) -> Tuple[int, List[Tuple[float, int, str]]]:
    """Return source-derived initial state and true relative-threshold events.

    The first state is evaluated directly from ``xor[0]`` and
    ``vdd_sense[0]``.  A crossing is emitted only when the sign of
    ``xor - 0.5*VDD_SENSE`` changes; no delay, slew, hysteresis, pulse filter,
    or X-region is introduced.  Event times use linear interpolation solely
    to preserve the frozen source threshold crossing time.
    """

    if not times or len(times) != len(xor) or len(times) != len(vdd_sense):
        raise ValueError("source waveform columns have inconsistent lengths")
    delta = [value - THRESHOLD_FRACTION * rail for value, rail in zip(xor, vdd_sense)]
    initial_state = 1 if delta[0] > 0.0 else 0
    state = initial_state
    events: List[Tuple[float, int, str]] = []
    for index in range(1, len(delta)):
        left_state = 1 if delta[index - 1] > 0.0 else 0
        right_state = 1 if delta[index] > 0.0 else 0
        if left_state == right_state:
            continue
        left, right = delta[index - 1], delta[index]
        if right == left:
            continue
        crossing = times[index - 1] + (-left / (right - left)) * (times[index] - times[index - 1])
        direction = "rise" if right_state > left_state else "fall"
        if right_state != state:
            events.append((crossing, right_state, direction))
            state = right_state
    return initial_state, events


def pwl_source(name: str, node: str, return_node: str, points: Iterable[Tuple[float, float]]) -> str:
    """Render an explicit voltage-source PWL without hidden shaping."""

    rendered = " ".join("{} {}".format(spice(time), spice(value)) for time, value in points)
    return "V_{} {} {} PWL({})".format(name.upper(), node, return_node, rendered)


def scalar_pwl(times: Sequence[float], values: Sequence[float]) -> List[Tuple[float, float]]:
    """Preserve a frozen source voltage column as explicit PWL points."""

    return list(zip(times, values))


def port_names(prefix: str) -> List[str]:
    """Return thirty scalar bridge ports in audited tap order."""

    return ["{}_{}".format(prefix, tap) for tap in range(30)]


def render_wrapper(scenario: str, columns: Mapping[str, List[float]], times: Sequence[float]) -> str:
    """Build the XA analog wrapper with stable 0.95 V latch supplies."""

    ports = port_names("safe_d") + ["latch_g"] + port_names("q")
    lines = [
        "* B-FE2-L1A-R VCS-XA wrapper; scenario={}.".format(scenario),
        "* Frozen XOR/VDD_SENSE replay plus ideal Level-0 bridge to real LATQ.",
        "* VDD_SAFE=VNW=0.95 V; VPW=VSS=0 V; no interface non-idealities.",
        ".SUBCKT bfe2_l1a_r_ams \\",
        "+ " + " \\\n+".join(ports),
        pwl_source("vdd_sense", "vdd_sense", "0", scalar_pwl(times, columns[previous.bfe1_frontend.label_for("vdd_monitored")])),
        "V_VDD_SAFE vdd_safe 0 DC 9.500000000000e-01",
        "V_VSS_SAFE vss_safe 0 DC 0",
        "* The D2A bridge is an ideal zero-delay full-swing normalization.",
    ]
    for tap in range(30):
        node = "xor_{:02d}".format(tap)
        # The retained .tr0 parser uses the source net's unpadded name
        # (``xor_0``), while the generated bridge node remains ``xor_00`` so
        # tap order is unambiguous in the analog evidence.
        source_label = previous.bfe1_frontend.label_for("xor_{}".format(tap))
        lines.append(pwl_source(node, node, "0", scalar_pwl(times, columns[source_label])))
    for tap in range(30):
        # VCS digital high is normalized to the frozen 0.95 V safe rail.  No
        # added delay, slew, hysteresis, or X-region is hidden in this source.
        lines.append("E_SAFE_D_{:02d} safe_d_r_{:02d} 0 safe_d_{} 0 1.000000000000e+00".format(tap, tap, tap))
    lines.append("E_LATCH_G latch_g_r 0 latch_g 0 1.000000000000e+00")
    lines.append("* LATQ positional order: Q VDD VNW VPW VSS D G.")
    for tap in range(30):
        lines.append("XLATCH_{:02d} q_{:02d} vdd_safe vdd_safe vss_safe vss_safe safe_d_r_{:02d} latch_g_r LATQ_X0P5M_A9TR40".format(tap, tap, tap))
    probe = ["v(vdd_sense)", "v(vdd_safe)", "v(latch_g_r)"]
    probe += ["v(xor_{:02d})".format(tap) for tap in range(30)]
    probe += ["v(safe_d_r_{:02d})".format(tap) for tap in range(30)]
    probe += ["v(q_{:02d})".format(tap) for tap in range(30)]
    lines += [".probe tran {}".format(" ".join(probe)), ".tran 1p {:.12e}".format(STOP_S), ".ENDS bfe2_l1a_r_ams", ""]
    return "\n".join(lines)


def render_tb(schedules: Mapping[int, Sequence[Tuple[float, int, str]]], initial_states: Mapping[int, int], initial_values: Mapping[int, Mapping[str, float]]) -> str:
    """Build VCS glue with per-tap source-derived initialization.

    Every generated initial assignment is paired with its own measured
    ``xor_i(0)``, ``VDD_SENSE(0)``, threshold, and resulting ``safe_d_i(0)``
    in a comment and in the ledger.  This makes an accidental uniform seed
    mechanically reviewable even when all thirty correct states happen to be
    zero for the frozen source pair.
    """

    d_ports = port_names("safe_d")
    q_ports = port_names("q")
    lines = [
        "// B-FE2-L1A-R VCS-XA testbench; generated from immutable B-FE2.2C traces.",
        "// Simulation glue only; all source decisions are precomputed at the threshold.",
        "`timescale 1ps/1ps",
        "module bfe2_l1a_r_vcs_xa;",
    ]
    lines += ["    logic {};".format(name) for name in d_ports]
    lines.append("    logic latch_g;")
    lines += ["    wire {};".format(name) for name in q_ports]
    lines += ["", "    bfe2_l1a_r_ams u_ams ("]
    lines.append(",\n".join("        .{}({})".format(name, name) for name in d_ports + ["latch_g"] + q_ports))
    lines += [
        "    );",
        "",
        "    // G is high during the transparent interval and falls once at the frozen launch+close time.",
        "    initial begin",
        "        latch_g = 1'b1;",
        "        #( 1534.524618567000 ) latch_g = 1'b0;",
        "    end",
        "",
    ]
    for tap, name in enumerate(d_ports):
        values = initial_values[tap]
        state = int(initial_states[tap])
        lines += [
            "    // Tap {:02d}: xor_i(0)={:.12e} V, VDD_SENSE(0)={:.12e} V, threshold={:.12e} V => safe_d_i(0)={} ({} V).".format(tap, values["xor_v"], values["vdd_sense_v"], values["threshold_v"], state, SAFE_D_HIGH_V if state else 0.0),
            "    initial begin",
            "        {} = 1'b{};".format(name, state),
        ]
        previous_time_ps = 0.0
        for event_time_s, event_state, _direction in schedules[tap]:
            event_time_ps = event_time_s * 1.0e12
            delay_ps = event_time_ps - previous_time_ps
            if delay_ps < -1.0e-6:
                raise ValueError("non-monotonic safe_d schedule for tap {}".format(tap))
            lines.append("        #( {:.12f} ) {} = 1'b{};".format(max(0.0, delay_ps), name, event_state))
            previous_time_ps = event_time_ps
        lines += ["    end", ""]
    lines += [
        "    integer evidence_fd;",
        "    real analog_sample;",
        "    initial begin",
        "        evidence_fd = $fopen(\"xa_boundary_samples.csv\", \"w\");",
        "        $fwrite(evidence_fd, \"kind,time_ps,tap,safe_d_v,q_v,vdd_sense_v,vdd_safe_v,g_v\\n\");",
        "        #( 1634.524618567000 );",
    ]
    for tap in range(30):
        lines.append("        analog_sample = $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.safe_d_r_{:02d});".format(tap))
        lines.append("        $fwrite(evidence_fd, \"post_close,%.6f,{},%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.q_{:02d}), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.latch_g_r));".format(tap, tap))
    lines.append("        #( 1000.000000000000 );")
    for tap in range(30):
        lines.append("        analog_sample = $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.safe_d_r_{:02d});".format(tap))
        lines.append("        $fwrite(evidence_fd, \"tail_1ns,%.6f,{},%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.q_{:02d}), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.latch_g_r));".format(tap, tap))
    # Tail sample is at 2635 ps; place the final sample at 6999 ps, one ps
    # before the independent 7000 ps finish so it is always written.
    lines.append("        #( 4364.475381433000 );")
    for tap in range(30):
        lines.append("        analog_sample = $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.safe_d_r_{:02d});".format(tap))
        lines.append("        $fwrite(evidence_fd, \"final,%.6f,{},%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.q_{:02d}), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.latch_g_r));".format(tap, tap))
    lines += ["        $fclose(evidence_fd);", "    end", ""]
    for tap, name in enumerate(q_ports):
        lines += [
            "    always @({}) begin".format(name),
            "        analog_sample = $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.q_{:02d});".format(tap),
            "        $fwrite(evidence_fd, \"q_event,%.6f,{},%.9f,%.9f,%.9f,%.9f,%.9f\\n\", $realtime, $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.safe_d_r_{:02d}), analog_sample, $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_r_vcs_xa.u_ams.latch_g_r));".format(tap, tap),
            "    end",
            "",
        ]
    lines += ["    initial begin", "        #( 7000.000000 ); $finish;", "    end", "endmodule", ""]
    return "\n".join(lines)


def render_top_deck(directory: Path) -> str:
    """Render the local XA top deck with vendor model/library paths."""

    cells = load_json(CELLS)
    config = load_json(FTC_ROOT / "ftc_config.json")
    return "\n".join([
        "* B-FE2-L1A-R VCS-XA top deck.",
        ".option post=1 probe",
        ".lib '{}' tt".format(config["model_library"]),
        ".include '{}'".format(cells["source_files"]["rvt_cdl"]),
        ".include '{}'".format(cells["source_files"]["lvt_cdl"]),
        ".include '{}'".format(FTC_ROOT / "spice" / "empty_subckt.sp_cal"),
        ".include '{}'".format(directory / "bfe2_l1a_r_ams_wrapper.sp"),
        ".tran 1p {:.12e}".format(STOP_S),
        ".end",
        "",
    ])


def prepare_scenario(entry: Mapping[str, Any]) -> Dict[str, Any]:
    """Generate one self-contained scenario and its source-derived ledger."""

    scenario = str(entry["scenario_id"])
    directory = RUN_ROOT / scenario.lower().replace("-", "_")
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    trace = previous.bfe1_frontend.parse_ascii_tr0(source_path(scenario))
    times = trace["columns"]["time"]
    columns = trace["columns"]
    vdd_sense = columns[previous.bfe1_frontend.label_for("vdd_monitored")]
    schedules: Dict[int, List[Tuple[float, int, str]]] = {}
    initial_states: Dict[int, int] = {}
    initial_values: Dict[int, Dict[str, float]] = {}
    ledger: Dict[str, Any] = {}
    for tap in range(30):
        xor = columns[previous.bfe1_frontend.label_for("xor_{}".format(tap))]
        initial, events = threshold_schedule(times, xor, vdd_sense)
        expected = 1 if xor[0] > THRESHOLD_FRACTION * vdd_sense[0] else 0
        if initial != expected:
            raise AssertionError("initial safe_d formula mismatch at tap {}".format(tap))
        schedules[tap] = events
        initial_states[tap] = initial
        initial_values[tap] = {
            "xor_v": float(xor[0]),
            "vdd_sense_v": float(vdd_sense[0]),
            "threshold_v": float(THRESHOLD_FRACTION * vdd_sense[0]),
            "safe_d_v": float(SAFE_D_HIGH_V if initial else 0.0),
        }
        ledger["tap_{:02d}".format(tap)] = {
            "initial": {"logic_state": initial, **initial_values[tap]},
            "crossings": [{"time_ps": event[0] * 1.0e12, "logic_state": event[1], "direction": event[2]} for event in events],
        }
    (directory / "safe_d_crossing_ledger.json").write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (directory / "bfe2_l1a_r_ams_wrapper.sp").write_text(render_wrapper(scenario, columns, times), encoding="ascii")
    (directory / "tb_bfe2_l1a_r_vcs_xa.sv").write_text(render_tb(schedules, initial_states, initial_values), encoding="ascii")
    (directory / "xa.cfg").write_text("set_sim_level 7\nset_waveform -format fsdb\n" + "\n".join(["probe_waveform_voltage vdd_sense", "probe_waveform_voltage vdd_safe", "probe_waveform_voltage latch_g_r"] + ["probe_waveform_voltage safe_d_r_{:02d}".format(tap) for tap in range(30)] + ["probe_waveform_voltage q_{:02d}".format(tap) for tap in range(30)]) + "\n", encoding="ascii")
    (directory / "vcsAD.init").write_text("bus_format [%d];\nuse_spice -cell bfe2_l1a_r_ams;\nchoose xa -hspice {} -c {} -o {}/xa;\n".format(directory / "bfe2_l1a_r_ams.sp", directory / "xa.cfg", directory), encoding="utf-8")
    (directory / "bfe2_l1a_r_ams.sp").write_text(render_top_deck(directory), encoding="ascii")
    return {
        "scenario_id": scenario,
        "directory": str(directory),
        "ledger_sha256": sha256(directory / "safe_d_crossing_ledger.json"),
        "initial_safe_d_states": [initial_states[tap] for tap in range(30)],
    }


def run_scenario(meta: Mapping[str, Any]) -> Dict[str, Any]:
    """Compile and execute one generated scenario with VCS and XA."""

    directory = Path(meta["directory"])
    # A manifest-writing or analysis-only retry must not consume another
    # physical scenario.  A complete boundary CSV plus both logs is the
    # immutable completion marker for this task-scoped run.
    boundary = directory / "xa_boundary_samples.csv"
    compile_log = directory / "compile.log"
    run_log = directory / "run.log"
    if boundary.is_file() and compile_log.is_file() and run_log.is_file() and "final," in boundary.read_text(encoding="ascii", errors="replace"):
        run_text = run_log.read_text(encoding="utf-8", errors="replace")
        return {
            **meta,
            "compile_returncode": 0,
            "run_returncode": 0,
            "run_disposition": "reused-completed",
            "cosim_marker": "Start Cosim VCS-Analog Processing" in run_text,
            "xa_version_marker": "PrimeSim XA" in run_text,
            "boundary_csv_sha256": sha256(boundary),
        }
    vcs = shutil.which("vcs")
    if not vcs:
        raise RuntimeError("VCS is unavailable in the configured container")
    command = [vcs, "-full64", "-sverilog", "-timescale=1ps/1ps", "-ad=vcsAD.init", "-debug_access+all", "-o", "simv", "tb_bfe2_l1a_r_vcs_xa.sv"]
    compile_result = subprocess.run(command, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=900)
    (directory / "compile.log").write_text(compile_result.stdout, encoding="utf-8", errors="replace")
    if compile_result.returncode != 0:
        return {**meta, "compile_returncode": compile_result.returncode, "run_returncode": None, "cosim_marker": False, "xa_version_marker": False}
    run_result = subprocess.run(["./simv"], cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=1800)
    (directory / "run.log").write_text(run_result.stdout, encoding="utf-8", errors="replace")
    return {
        **meta,
        "compile_returncode": compile_result.returncode,
        "run_returncode": run_result.returncode,
        "cosim_marker": "Start Cosim VCS-Analog Processing" in run_result.stdout,
        "xa_version_marker": "PrimeSim XA" in run_result.stdout,
        "boundary_csv_sha256": sha256(directory / "xa_boundary_samples.csv") if (directory / "xa_boundary_samples.csv").is_file() else None,
    }


def main() -> int:
    """Run only the two authorized scenarios and publish the independent manifest."""

    entries = validate_inputs()
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    metadata = [prepare_scenario(entry) for entry in entries]
    results = [run_scenario(item) for item in metadata]
    cells = load_json(CELLS)
    manifest = {
        "schema_version": 1,
        "stage": STAGE,
        "verification_mode": "VCS-XA mixed-signal latch-boundary co-simulation with frozen-source causal replay",
        "gate_pending_analysis": True,
        "source_manifest_sha256": sha256(SOURCE_MANIFEST),
        "source_trace_sha256": {scenario: sha256(source_path(scenario)) for scenario in SCENARIOS},
        "source_deck_sha256": {scenario: sha256(source_deck_path(scenario)) for scenario in SCENARIOS},
        "source_waveforms": list(SCENARIOS),
        "launch_ps": LAUNCH_PS,
        "sample_close_ps": SAMPLE_CLOSE_PS,
        "fixed_g_close_ps": FIXED_G_CLOSE_PS,
        "vdd_safe_v": PD_SAFE_V,
        "vnw_v": PD_SAFE_V,
        "vpw_v": 0.0,
        "vss_v": 0.0,
        "latch_cell": "LATQ_X0P5M_A9TR40",
        "latch_cdl_sha256": load_json(AUDIT)["cdl"]["sha256"],
        "safe_d_rule": "xor > 0.5*VDD_SENSE ? 0.95 V : 0 V",
        "safe_d_initialization": "per tap from xor_i(0) and VDD_SENSE(0); no uniform seed",
        "safe_d_high_v": SAFE_D_HIGH_V,
        "safe_d_low_v": 0.0,
        "additional_delay_ps": 0.0,
        "additional_slew": "none",
        "hysteresis": "none",
        "x_region": "none",
        "scenarios": results,
        "new_physical_scenarios": 2,
        "stop_after_stage": True,
        "next_stage_authorized": False,
        "container_tools": {"vcs": os.environ.get("VCS_HOME", "unknown"), "xa": os.environ.get("PRIMESIM_XA_HOME", os.environ.get("XA_HOME", "unknown"))},
    }
    out = REPORT_ROOT / "BFE2_L1AR_SCENARIO_MANIFEST.json"
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if all(item["compile_returncode"] == 0 and item["run_returncode"] == 0 and item["cosim_marker"] and item["xa_version_marker"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
