#!/usr/bin/env bash
# Run M1 mapped + SDF verification with frozen H0 mapped logic as read-only.
#
# The test reuses the thorough manager/H0 protocol bench: twelve exact M0
# mappings, F10, unsupported input, duplicate/early request, delayed owner,
# H0 block, POR, safe control changes, and one-cycle settle.  It compiles no
# transistor sensor, HSPICE deck, XA bridge, calibration rerun, or H0 RTL.
# Every generated simulator product stays below this M1 gate_sdf run root.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
M1_ROOT=$(cd "${SCRIPT_DIR}/../.." && pwd)
REPO_ROOT=$(cd "${M1_ROOT}/../../../.." && pwd)
RTL_VERIFY_ROOT="${M1_ROOT}/verification/rtl"
ASSERTION_ROOT="${M1_ROOT}/assertions"
RUN_PARENT="${SCRIPT_DIR}/run"
RUN_ID="${M1_GATE_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_ROOT="${RUN_PARENT}/${RUN_ID}"

M1_NETLIST="${M1_ROOT}/synthesis/netlist/ftc_detection_margin_manager_synth.v"
M1_SDF="${M1_ROOT}/synthesis/netlist/ftc_detection_margin_manager_synth.sdf"
H0_ROOT="${REPO_ROOT}/delay_chain/ftc/controller/h0_calibration_detection_handoff"
H0_NETLIST="${H0_ROOT}/synthesis/netlist/ftc_sensor_owner_handoff_synth.v"
H0_SDF="${H0_ROOT}/synthesis/netlist/ftc_sensor_owner_handoff_synth.sdf"
CELL_MODEL="/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/verilog/sc9mc_logic0040ll_base_rvt_c40.v"

for input in "${M1_NETLIST}" "${M1_SDF}" "${H0_NETLIST}" "${H0_SDF}" "${CELL_MODEL}"; do
    test -r "${input}"
done
mkdir -p "${RUN_ROOT}"

(
    cd "${RUN_ROOT}"
    vcs -full64 -sverilog -timescale=1ns/1ps -assert svaext +neg_tchk \
        +define+M1_GATE_SDF -debug_access+all \
        -Mdir="${RUN_ROOT}/csrc" -o "${RUN_ROOT}/simv_m1_gate_sdf" \
        -sdf max:tb_ftc_detection_margin_manager.u_manager:"${M1_SDF}" \
        -sdf max:tb_ftc_detection_margin_manager.u_frozen_h0:"${H0_SDF}" \
        "${CELL_MODEL}" "${M1_NETLIST}" "${H0_NETLIST}" \
        "${ASSERTION_ROOT}/ftc_detection_margin_manager_sva.sv" \
        "${RTL_VERIFY_ROOT}/tb_ftc_detection_margin_manager.sv" \
        -l "${RUN_ROOT}/compile.log"
    "${RUN_ROOT}/simv_m1_gate_sdf" +sdfverbose -l "${RUN_ROOT}/run.log"
)

# VCS can return success after a testbench $fatal.  Refuse to publish a gate
# PASS if the functional bench, SVA, or annotated timing checks reported any
# error marker, including a setup/hold timing violation.
if rg -q '(^FAIL |M1 SVA:|integration FAIL|Fatal:|Timing violation|\$setup|\$hold)' "${RUN_ROOT}/run.log"; then
    printf 'M1 mapped+SDF verification failed; inspect %s\n' "${RUN_ROOT}/run.log" >&2
    exit 1
fi
printf 'M1 mapped+SDF regression PASS\n' | tee "${RUN_ROOT}/summary.txt"
