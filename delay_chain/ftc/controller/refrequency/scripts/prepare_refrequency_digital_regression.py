#!/usr/bin/env python3
"""Prepare isolated RF9A/RF9B three-voltage behavioral regression inputs.

The established Phase-8B bench already checks each nominal trajectory, exact
operation counts, physical controller S_CLK edges, both Q samples, one-bit
thermometer changes, final lock, and protocol errors.  RF9 needs those same
checks at the active 2.5 ns clock, so this script copies it into RF-owned
directories and applies one verified localparam replacement only.
"""

import hashlib
import json
import shutil
from pathlib import Path


CONTROLLER_ROOT = Path(__file__).resolve().parents[2]
RF_ROOT = CONTROLLER_ROOT / "refrequency"
SOURCE_TB = CONTROLLER_ROOT / "analysis" / "phase8_gate_level" / "delayed" / "tb_delayed_gate_level.sv"
SENSOR = CONTROLLER_ROOT / "tb" / "ftc_sensor_behavior_model.sv"
CELL_MODEL = CONTROLLER_ROOT / "analysis" / "phase9_autonomous_transistor_level" / "vcs_xa" / "inputs" / "sc9mc_logic0040ll_base_rvt_c40.v"
NETLIST = RF_ROOT / "synthesis" / "netlist" / "ftc_cal_controller_top_synth.v"
SDF = RF_ROOT / "synthesis" / "netlist" / "ftc_cal_controller_top_synth.sdf"
MS_SOURCE = CONTROLLER_ROOT / "final_closure" / "timing_composition" / "src"
SENSOR_SPICE = CONTROLLER_ROOT / "analysis" / "phase9_autonomous_transistor_level" / "vcs_xa" / "inputs" / "ftc_sensor_frozen.sp"
EMPTY_SUBCKT = CONTROLLER_ROOT / "analysis" / "phase9_autonomous_transistor_level" / "vcs_xa" / "inputs" / "empty_subckt.sp_cal"


def sha256(path):
    """Hash each copied immutable input for the RF9 pre-run manifest."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare(mode):
    """Create one input directory, refusing to overwrite prior RF9 evidence."""

    root = RF_ROOT / "verification" / mode
    inputs = root / "inputs"
    manifest = root / "pre_run_manifest.json"
    if manifest.exists():
        raise RuntimeError("RF9 {} inputs already prepared".format(mode))
    inputs.mkdir(parents=True, exist_ok=False)
    original = SOURCE_TB.read_text(encoding="utf-8")
    old = "localparam real CLK_PERIOD_NS=10.0;"
    new = "localparam real CLK_PERIOD_NS=2.5;"
    if original.count(old) != 1:
        raise ValueError("historical Phase-8B clock parameter is not unique")
    # The historical bench's comments and all assertion logic are preserved.
    # Only its one local clock-period declaration is changed for RF9.
    (inputs / "tb_refrequency_gate_level.sv").write_text(original.replace(old, new), encoding="utf-8")
    shutil.copyfile(SENSOR, inputs / SENSOR.name)
    if mode == "rtl_behavioral":
        rtl_files = [
            "ftc_cal_pkg.sv", "ftc_cfg_therm_regs.sv", "ftc_q_sampler.sv",
            "ftc_operation_sequencer.sv", "ftc_cal_fsm.sv", "ftc_cal_controller_top.sv",
        ]
        for name in rtl_files:
            shutil.copyfile(CONTROLLER_ROOT / "rtl" / name, inputs / name)
    elif mode == "sdf_behavioral":
        shutil.copyfile(NETLIST, inputs / NETLIST.name)
        shutil.copyfile(SDF, inputs / SDF.name)
        shutil.copyfile(CELL_MODEL, inputs / CELL_MODEL.name)
    else:
        raise ValueError("unsupported RF9 digital mode: {}".format(mode))
    files = sorted(path for path in inputs.iterdir() if path.is_file())
    document = {
        "schema_version": 1,
        "decision": "RF9 {} Input Freeze = GO".format(mode),
        "clock_period_ns": 2.5,
        "historical_bench": str(SOURCE_TB.relative_to(CONTROLLER_ROOT)),
        "only_testbench_change": {"old": old, "new": new},
        "inputs": [{"name": path.name, "sha256": sha256(path)} for path in files],
        "sdf_enabled": mode == "sdf_behavioral",
        "timing_checks_disabled": False,
    }
    manifest.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prepare_mixed_signal():
    """Freeze shared 2.5 ns XA inputs for RF9C and RF9D without retuning.

    Both later stages use byte-identical controller/sensor/testbench inputs.
    The only mode difference is the explicit SDF flag supplied by the remote
    launcher; voltage remains a SPICE parameter, never a digital bench edit.
    """

    original = (MS_SOURCE / "tb_ftc_vcs_xa_autonomous.sv").read_text(encoding="utf-8")
    replacements = [("forever #0.5 cal_clk", "forever #1.25 cal_clk"), ("#800;", "#2000;")]
    for old, new in replacements:
        if original.count(old) != 1:
            raise ValueError("mixed-signal bench replacement is not unique: {}".format(old))
        original = original.replace(old, new)
    for mode in ("mixed_signal_no_sdf", "mixed_signal_sdf"):
        root = RF_ROOT / "verification" / mode
        inputs = root / "inputs"
        if (root / "pre_run_manifest.json").exists():
            raise RuntimeError("RF9 {} inputs already prepared".format(mode))
        inputs.mkdir(parents=True, exist_ok=False)
        for source in (CELL_MODEL, NETLIST, SENSOR_SPICE, EMPTY_SUBCKT,
                       MS_SOURCE / "ftc_sensor_ams_stub.sv", MS_SOURCE / "ftc_sensor_ams_wrapper.sp",
                       MS_SOURCE / "xa.cfg", CONTROLLER_ROOT / "analysis" / "phase9_autonomous_transistor_level" / "vcs_xa_corrected" / "src" / "vcsAD.init"):
            shutil.copyfile(source, inputs / source.name)
        if mode == "mixed_signal_sdf":
            shutil.copyfile(SDF, inputs / SDF.name)
        (inputs / "tb_ftc_vcs_xa_autonomous.sv").write_text(original, encoding="utf-8")
        files = sorted(path for path in inputs.iterdir() if path.is_file())
        (root / "pre_run_manifest.json").write_text(json.dumps({
            "schema_version": 1, "decision": "RF9 {} Input Freeze = GO".format(mode),
            "clock_period_ns": 2.5, "only_bench_timing_changes": replacements,
            "sdf_enabled": mode == "mixed_signal_sdf", "timing_checks_disabled": False,
            "inputs": [{"name": path.name, "sha256": sha256(path)} for path in files],
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def instantiate_mixed_runs(mode):
    """Materialize the three voltage decks from one frozen shared input set."""

    root = RF_ROOT / "verification" / mode
    local_root = "/home/zhupl25"
    host_root = "/home/zhupl/rocky8/container-home/zhupl25"
    for tag, supply in (("0p80", "0.80"), ("0p95", "0.95"), ("1p10", "1.10")):
        # Keep each run name explicit; never merge voltage evidence folders.
        run = root / "runs" / ("rf9_" + tag)
        if run.exists():
            continue
        run.mkdir(parents=True)
        for source in (root / "inputs").iterdir():
            if source.is_file(): shutil.copyfile(source, run / source.name)
        host_run = host_root + str(run).replace(local_root, "")
        deck = """* RF9 {mode} {tag}; frozen 2.5 ns controller contract.\n.option post=1 probe\n.param VDD_VALUE={supply}\n.lib /home/yangz/virtuoso/SMIC40TXRX/smic40ll_1125_2tm_oa_cds_1P9M_2012_10_11_v1.4/models/hspice/l0040ll_v1p4_1r.lib tt\n.include /home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/cdl/sc9mc_logic0040ll_base_rvt_c40.cdl\n.include /home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/cdl/sc9mc_logic0040ll_base_lvt_c40.cdl\n.include {host_run}/empty_subckt.sp_cal\n.include {host_run}/ftc_sensor_frozen.sp\n.include {host_run}/ftc_sensor_ams_wrapper.sp\n.tran 500p 2000n\n.end\n""".format(mode=mode, tag=tag, supply=supply, host_run=host_run)
        (run / "rf9_{}.sp".format(tag)).write_text(deck, encoding="utf-8")
        init = (run / "vcsAD.init").read_text(encoding="utf-8")
        init = init.replace("PLACEHOLDER_SPICE_TOP", host_run + "/rf9_{}.sp".format(tag)).replace("PLACEHOLDER_XA_CFG", host_run + "/xa.cfg").replace("PLACEHOLDER_XA_OUT", host_run + "/xa/xa")
        (run / "vcsAD.init").write_text(init, encoding="utf-8")


def instantiate_locale_retries():
    """Freeze three RF9C environment-only retries beside failed attempts.

    The first XA attempts ended before elaboration because locale diagnostics
    polluted AnalogSim-VCS's helper query.  Every retry retains the identical
    copied RF9C inputs and 2.5 ns bench; only the generated bridge paths point
    to the retry child so its raw products cannot overwrite the failure logs.
    The remote launcher, rather than this input freeze, exports ``LC_ALL=C``
    and ``LANG=C`` to suppress the known unrelated diagnostic.
    """

    root = RF_ROOT / "verification" / "mixed_signal_no_sdf"
    local_root = "/home/zhupl25"
    host_root = "/home/zhupl/rocky8/container-home/zhupl25"
    for tag, supply in (("0p80", "0.80"), ("0p95", "0.95"), ("1p10", "1.10")):
        parent = root / "runs" / ("rf9_" + tag)
        retry = parent / "infrastructure_retry_locale"
        if retry.exists():
            continue
        original_log = parent / "compile.log"
        if not original_log.is_file() or "MSV-SETUP-ERR" not in original_log.read_text(encoding="utf-8", errors="replace"):
            raise ValueError("RF9C retry requires the verified locale setup failure: {}".format(tag))
        retry.mkdir()
        for source in (root / "inputs").iterdir():
            if source.is_file():
                shutil.copyfile(source, retry / source.name)
        host_retry = host_root + str(retry).replace(local_root, "")
        deck = """* RF9C {tag} environment-only retry; frozen 2.5 ns contract.\n.option post=1 probe\n.param VDD_VALUE={supply}\n.lib /home/yangz/virtuoso/SMIC40TXRX/smic40ll_1125_2tm_oa_cds_1P9M_2012_10_11_v1.4/models/hspice/l0040ll_v1p4_1r.lib tt\n.include /home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/cdl/sc9mc_logic0040ll_base_rvt_c40.cdl\n.include /home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/cdl/sc9mc_logic0040ll_base_lvt_c40.cdl\n.include {path}/empty_subckt.sp_cal\n.include {path}/ftc_sensor_frozen.sp\n.include {path}/ftc_sensor_ams_wrapper.sp\n.tran 500p 2000n\n.end\n""".format(tag=tag, supply=supply, path=host_retry)
        (retry / "rf9_{}.sp".format(tag)).write_text(deck, encoding="utf-8")
        init = (retry / "vcsAD.init").read_text(encoding="utf-8")
        init = init.replace("PLACEHOLDER_SPICE_TOP", host_retry + "/rf9_{}.sp".format(tag)).replace("PLACEHOLDER_XA_CFG", host_retry + "/xa.cfg").replace("PLACEHOLDER_XA_OUT", host_retry + "/xa/xa")
        (retry / "vcsAD.init").write_text(init, encoding="utf-8")
        (retry / "retry_freeze.json").write_text(json.dumps({
            "schema_version": 1,
            "decision": "RF9C Locale Infrastructure Retry Freeze = GO",
            "scenario": "rf9_" + tag,
            "reason": "original attempt stopped before analog simulation because locale warnings corrupted AnalogSim-VCS simulator-type detection",
            "only_runtime_environment_change": {"LC_ALL": "C", "LANG": "C"},
            "original_compile_log_sha256": sha256(original_log),
            "retry_input_sha256": [{"name": path.name, "sha256": sha256(path)} for path in sorted(retry.iterdir()) if path.is_file() and path.name != "retry_freeze.json"],
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def instantiate_no_sdf_functional_retries():
    """Freeze RF9C's intended no-SDF functional bridge configuration.

    RF9C precedes digital timing composition and follows the corrected
    historical Phase-9 convention: it deliberately suppresses cell specify
    checks because it measures the transistor bridge/function only.  RF9B
    already ran SDF with timing checks enabled, and RF9D will do so again.
    This child preserves the preceding full-timing-check failure and changes
    only those two mode flags, never the RTL, period, sensor, or voltage.
    """

    root = RF_ROOT / "verification" / "mixed_signal_no_sdf"
    local_root = "/home/zhupl25"
    host_root = "/home/zhupl/rocky8/container-home/zhupl25"
    for tag, supply in (("0p80", "0.80"), ("0p95", "0.95"), ("1p10", "1.10")):
        parent = root / "runs" / ("rf9_" + tag) / "infrastructure_retry_locale"
        retry = parent / "functional_no_sdf"
        if retry.exists():
            continue
        original_log = root / "runs" / "rf9_0p80" / "infrastructure_retry_locale" / "run.log"
        if not original_log.is_file() or "Timing violation" not in original_log.read_text(encoding="utf-8", errors="replace"):
            raise ValueError("RF9C functional retry requires retained 0.80 V timing-check evidence")
        if not (parent / "retry_freeze.json").is_file():
            raise ValueError("RF9C functional retry requires the common locale retry freeze: {}".format(tag))
        retry.mkdir()
        for source in (root / "inputs").iterdir():
            if source.is_file():
                shutil.copyfile(source, retry / source.name)
        host_retry = host_root + str(retry).replace(local_root, "")
        deck = """* RF9C {tag} functional no-SDF retry; frozen 2.5 ns contract.\n.option post=1 probe\n.param VDD_VALUE={supply}\n.lib /home/yangz/virtuoso/SMIC40TXRX/smic40ll_1125_2tm_oa_cds_1P9M_2012_10_11_v1.4/models/hspice/l0040ll_v1p4_1r.lib tt\n.include /home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/cdl/sc9mc_logic0040ll_base_rvt_c40.cdl\n.include /home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/cdl/sc9mc_logic0040ll_base_lvt_c40.cdl\n.include {path}/empty_subckt.sp_cal\n.include {path}/ftc_sensor_frozen.sp\n.include {path}/ftc_sensor_ams_wrapper.sp\n.tran 500p 2000n\n.end\n""".format(tag=tag, supply=supply, path=host_retry)
        (retry / "rf9_{}.sp".format(tag)).write_text(deck, encoding="utf-8")
        init = (retry / "vcsAD.init").read_text(encoding="utf-8")
        init = init.replace("PLACEHOLDER_SPICE_TOP", host_retry + "/rf9_{}.sp".format(tag)).replace("PLACEHOLDER_XA_CFG", host_retry + "/xa.cfg").replace("PLACEHOLDER_XA_OUT", host_retry + "/xa/xa")
        (retry / "vcsAD.init").write_text(init, encoding="utf-8")
        (retry / "retry_freeze.json").write_text(json.dumps({
            "schema_version": 1, "decision": "RF9C Functional No-SDF Retry Freeze = GO",
            "scenario": "rf9_" + tag, "clock_period_ns": 2.5,
            "only_simulator_mode_change": ["+nospecify", "+notimingcheck"],
            "justification": "RF9C bridge-function stage; full timing checks are mandatory in RF9B and RF9D, not this no-SDF stage",
            "previous_full_timing_check_run_log_sha256": sha256(original_log),
            "retry_input_sha256": [{"name": path.name, "sha256": sha256(path)} for path in sorted(retry.iterdir()) if path.is_file() and path.name != "retry_freeze.json"],
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def add_rf9d_observation_extension():
    """Freeze an observation-only event monitor into each unrun RF9D deck.

    The monitor is bound by input-only ports and cannot alter the mapped
    controller, SDF annotation, XA boundary, sensor topology, or testbench
    stimulus.  It adds S_CLK falling-edge records to the established monitor,
    which lets RF9D prove reset assertion occurs before every falling-return
    activity without inferring it from a waveform screenshot.
    """

    root = RF_ROOT / "verification" / "mixed_signal_sdf"
    source = MS_SOURCE / "timing_composition_monitor.sv"
    original = source.read_text(encoding="utf-8")
    old_reference = "canonical 1 ns calibration clock"
    new_reference = "active 2.5 ns re-frequency calibration clock"
    old_block = """    // Reset transitions are captured independently so the audit can verify\n    // release before S_CLK rise and reassertion before the return/fall edge.\n    always @(sense_dff_reset) begin\n"""
    new_block = """    // Reset transitions are captured independently so the audit can verify\n    // release before S_CLK rise and reassertion before the return/fall edge.\n    // Falling S_CLK is separately recorded below; this monitor never drives it.\n    always @(sense_dff_reset) begin\n"""
    if original.count(old_reference) != 1 or original.count(old_block) != 1:
        raise ValueError("RF9D monitor source replacement is not unique")
    monitor = original.replace(old_reference, new_reference).replace(old_block, new_block)
    insert = """\n    // Record every controller S_CLK falling return after SDF annotation.\n    // Together with RESET_CHANGE rows this establishes the reset-before-fall\n    // invariant at the actual mapped-controller/XA interface.\n    always @(negedge sense_s_clk) begin\n        $fwrite(event_fd, \"%0.6f,SCLK_FALL,%0d,%0d,%0d,%0d,%0d,%0d,%b,%b,%b,%b,%b,%b,%h,%h,%b\\n\",\n            $realtime, cal_edge_count, sclk_edge_count, sample1_count,\n            sample2_count, config_count, probe_count, cal_busy, cal_done,\n            cal_fail, lock_valid, sense_dff_reset, sense_s_clk,\n            medium_therm, fine_therm, q_final);\n    end\n"""
    anchor = "\n    // Count physical thermometer transitions and preserve their exact time."
    if monitor.count(anchor) != 1:
        raise ValueError("RF9D monitor insertion anchor is not unique")
    monitor = monitor.replace(anchor, insert + anchor)
    for tag in ("0p80", "0p95", "1p10"):
        run = root / "runs" / ("rf9_" + tag)
        freeze = run / "rf9d_observation_extension_freeze.json"
        if freeze.exists():
            continue
        if any((run / name).exists() for name in ("compile.log", "run.log", "returncode.txt")):
            raise RuntimeError("RF9D run already started; observation extension is too late: {}".format(tag))
        monitor_path = run / "timing_composition_monitor.sv"
        monitor_path.write_text(monitor, encoding="utf-8")
        freeze.write_text(json.dumps({
            "schema_version": 1,
            "decision": "RF9D Observation Extension Freeze = GO",
            "scenario": "rf9_" + tag,
            "source": str(source.relative_to(CONTROLLER_ROOT)),
            "source_sha256": sha256(source),
            "monitor_sha256": sha256(monitor_path),
            "observation_only": True,
            "only_added_event": "SCLK_FALL post-SDF timestamp",
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    # Earlier RF9A/RF9B freezes may already exist when this helper is extended
    # for RF9C/RF9D.  Reuse their immutable inputs rather than overwriting
    # them, while still refusing to regenerate any mixed-signal input set.
    for digital_mode in ("rtl_behavioral", "sdf_behavioral"):
        if not (RF_ROOT / "verification" / digital_mode / "pre_run_manifest.json").exists():
            prepare(digital_mode)
    if not (RF_ROOT / "verification" / "mixed_signal_no_sdf" / "pre_run_manifest.json").exists():
        prepare_mixed_signal()
    instantiate_mixed_runs("mixed_signal_no_sdf")
    instantiate_mixed_runs("mixed_signal_sdf")
    instantiate_locale_retries()
    instantiate_no_sdf_functional_retries()
    add_rf9d_observation_extension()
