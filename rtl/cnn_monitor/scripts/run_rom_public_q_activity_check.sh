#!/usr/bin/env bash
# Compile and run the Stage-2 mapped-ROM public-Q compatibility proof.
#
# All generated compilation databases, executable files, logs, copied RCF, and
# machine-readable result remain under the supplied task run directory.  This
# driver only consumes the frozen mapped netlist and compiler artifacts; it
# never invokes synthesis or edits an immutable input.
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <task-run-directory>" >&2
    exit 64
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CNN_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
POWER_ROOT=$(cd "${CNN_ROOT}/../.." && pwd)
RUN_DIR=$(cd "$1" && pwd)
# The prior complete attempts exposed two gate-DFF observation races.  Preserve
# them as evidence and write the corrected exhaustive proof to a new,
# non-overwritable directory within the same task run.
OUT_DIR="${RUN_DIR}/gate_rom_compat_r6"
MAPPED_ROOT="${CNN_ROOT}/runs/stage89_20260801_r2/step11_dc_500mhz_operand_prefetch_static_lanes"
ROM_ROOT="${CNN_ROOT}/runs/stage89_20260801_r1/rom_compiler/output"
STD_CELL_MODEL=${STD_CELL_MODEL:-/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/verilog/sc9mc_logic0040ll_base_rvt_c40.v}
VCS_BIN=${VCS_BIN:-/home/synopsys/vcs/W-2024.09/bin/vcs}

for required in "${MAPPED_ROOT}/cnn_monitor_mapped.v" "${ROM_ROOT}/CNNW384X128.v" \
    "${ROM_ROOT}/CNNW384X128_verilog.rcf" "${STD_CELL_MODEL}" "${VCS_BIN}"; do
    [[ -r "${required}" || -x "${required}" ]] || {
        echo "ERROR: required Stage-2 input is unavailable: ${required}" >&2
        exit 66
    }
done
[[ ! -e "${OUT_DIR}" ]] || {
    echo "ERROR: refusing to overwrite existing Stage-2 run: ${OUT_DIR}" >&2
    exit 73
}

mkdir -p "${OUT_DIR}/csrc"
cp "${ROM_ROOT}/CNNW384X128_verilog.rcf" "${OUT_DIR}/CNNW384X128_verilog.rcf"
cd "${OUT_DIR}"

# The mapped adapter's public Q is force-driven only by the same model
# instance's Q_ during simulation.  No CNN RTL source is compiled here.
"${VCS_BIN}" -full64 -sverilog -DARM_UD_MODEL -timescale=1ns/1ps \
    -top cnn_rom_activity_compat \
    "${STD_CELL_MODEL}" \
    "${ROM_ROOT}/CNNW384X128.v" \
    "${MAPPED_ROOT}/cnn_monitor_mapped.v" \
    "${CNN_ROOT}/tb/cnn_rom_activity_compat.sv" \
    -Mdir="${OUT_DIR}/csrc" -o "${OUT_DIR}/simv" -l "${OUT_DIR}/compile.log"

"${OUT_DIR}/simv" -l "${OUT_DIR}/simulation.log"
grep -q 'PASS: mapped public-Q compatibility readback 384/384 addresses' "${OUT_DIR}/simulation.log"

"${CNN_ROOT}/scripts/audit_rom_observability.py" \
    --adapter "${CNN_ROOT}/rtl/cnn_weight_rom.sv" \
    --mapped-netlist "${MAPPED_ROOT}/cnn_monitor_mapped.v" \
    --compiler-model "${ROM_ROOT}/CNNW384X128.v" \
    --gate-vcd "${OUT_DIR}/rom_public_q.vcd" \
    --output "${RUN_DIR}/analysis/rom_observability_audit.json"

# Keep the result compact but independently auditable alongside the full log.
printf '{\n  "status": "PASS",\n  "addresses_checked": 384,\n  "clock_period_ns": 4.0,\n  "proof": "public_Q_equals_Q__equals_RCF",\n  "log": "gate_rom_compat_r6/simulation.log"\n}\n' \
    > "${RUN_DIR}/analysis/rom_public_q_check.json"
