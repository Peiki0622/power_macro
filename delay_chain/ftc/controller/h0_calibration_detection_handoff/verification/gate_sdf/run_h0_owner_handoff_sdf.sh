#!/usr/bin/env bash
# H0 mapped + SDF verification command record.
# All compiler databases, logs, and the executable stay below this one gate_sdf
# directory so the repository does not acquire scattered simulation products.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
H0_ROOT=$(cd "${SCRIPT_DIR}/../.." && pwd)
REPO_ROOT=$(cd "${H0_ROOT}/../../../.." && pwd)
RUN_ROOT="${SCRIPT_DIR}/run"
BUILD_ROOT="${SCRIPT_DIR}/build"
NETLIST="${H0_ROOT}/synthesis/netlist/ftc_sensor_owner_handoff_synth.v"
SDF="${H0_ROOT}/synthesis/netlist/ftc_sensor_owner_handoff_synth.sdf"
CELL_MODEL="/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/verilog/sc9mc_logic0040ll_base_rvt_c40.v"
TB="${SCRIPT_DIR}/tb_h0_owner_handoff_sdf.sv"
SIMV="${BUILD_ROOT}/simv_h0_owner_handoff_sdf"

mkdir -p "${RUN_ROOT}" "${BUILD_ROOT}"
{
    printf 'date_utc='; date -u +%Y-%m-%dT%H:%M:%SZ
    printf 'hostname='; hostname
    printf 'vcs='; vcs -ID -full64 -version 2>&1 | head -1
    printf 'netlist=%s\n' "${NETLIST}"
    printf 'sdf=%s\n' "${SDF}"
    printf 'cell_model=%s\n' "${CELL_MODEL}"
} > "${RUN_ROOT}/preflight.txt"

test -r "${NETLIST}"
test -r "${SDF}"
test -r "${CELL_MODEL}"

vcs -full64 -sverilog -timescale=1ns/1ps \
    -debug_access+all +neg_tchk \
    "${CELL_MODEL}" "${NETLIST}" "${TB}" \
    -top tb_h0_owner_handoff_sdf \
    -sdf max:tb_h0_owner_handoff_sdf.dut:"${SDF}" \
    -o "${SIMV}" \
    -l "${RUN_ROOT}/compile.log"

"${SIMV}" +sdfverbose -l "${RUN_ROOT}/run.log"
printf '0\n' > "${RUN_ROOT}/returncode.txt"
