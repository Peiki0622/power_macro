#!/usr/bin/env bash
# ============================================================================
# Phase 9 R1 1 GHz gate-level diagnostic runner
#
# All generated VCS work products are placed below diagnostics/digital_1ghz.
# The runner never invokes XA or HSPICE and never edits the historical Phase 8
# output.  A compact machine-readable report is written only after the VCS
# transcript has been checked for the exact R1_PASS marker.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLOW_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
FTC_ROOT="$(cd "${FLOW_ROOT}/../../../.." && pwd)"
REPO_ROOT="$(cd "${FTC_ROOT}/../.." && pwd)"
OUT_DIR="${FLOW_ROOT}/diagnostics/digital_1ghz"
NETLIST="${FTC_ROOT}/controller/synthesis/netlist/ftc_cal_controller_top_synth.v"
SENSOR="${FTC_ROOT}/controller/tb/ftc_sensor_behavior_model.sv"
TESTBENCH="${FLOW_ROOT}/src/tb_ftc_vcs_xa_1ghz.sv"
CELL_LIB="/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/verilog/sc9mc_logic0040ll_base_rvt_c40.v"
VCS_BIN="${VCS_BIN:-/home/synopsys/vcs/W-2024.09/bin/vcs}"
VLOGAN_BIN="${VLOGAN_BIN:-/home/synopsys/vcs/W-2024.09/bin/vlogan}"

mkdir -p "${OUT_DIR}"
cd "${OUT_DIR}"
rm -f compile.log elaborate_run.log simv R1_PASS.marker DIGITAL_1GHZ_GATE.json

if [[ ! -x "${VLOGAN_BIN}" || ! -x "${VCS_BIN}" ]]; then
    echo "R1 infrastructure failure: VCS W-2024.09 binaries are unavailable" >&2
    exit 2
fi
if [[ ! -f "${NETLIST}" || ! -f "${SENSOR}" || ! -f "${TESTBENCH}" || ! -f "${CELL_LIB}" ]]; then
    echo "R1 infrastructure failure: required source is missing" >&2
    exit 2
fi

"${VLOGAN_BIN}" -sverilog -full64 +v2k -timescale=1ns/1ps +delay_mode_zero \
    "${CELL_LIB}" "${NETLIST}" "${SENSOR}" "${TESTBENCH}" \
    2>&1 | tee compile.log

"${VCS_BIN}" -full64 -debug_access+all +notimingcheck -R \
    tb_ftc_vcs_xa_1ghz 2>&1 | tee elaborate_run.log

if grep -q "R1_PASS clock_period_ns=1 operations=45 configs=17 probes=28 sclk_edges=28 samples=28/28 final=M7/F6" elaborate_run.log \
   && ! grep -q "R1_FAIL\|R1_ERROR" elaborate_run.log; then
    python3 - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path('.')
report = {
    "schema_version": 1,
    "status": "PASS",
    "clock_period_ns": 1,
    "operations": 45,
    "configuration_updates": 17,
    "probes": 28,
    "sense_s_clk_rising_edges": 28,
    "q_sample_1_events": 28,
    "q_sample_2_events": 28,
    "final_medium": 7,
    "final_fine": 6,
    "transient_kind": "digital_gate_level_behavioral_sensor_only",
    "evidence": {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in (("compile_log", root / "compile.log"), ("run_log", root / "elaborate_run.log"))
    },
}
(root / "DIGITAL_1GHZ_GATE.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
    echo "R1 digital gate = GO"
else
    echo "R1 digital gate = NO-GO" >&2
    exit 1
fi
