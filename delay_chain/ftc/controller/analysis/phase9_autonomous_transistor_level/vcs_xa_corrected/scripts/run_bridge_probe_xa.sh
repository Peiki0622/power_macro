#!/usr/bin/env bash
# ============================================================================
# Run the corrected R3/R4 bridge probe on the configured EDA host.
#
# The container has the VCS W-2024.09 digital compiler, but the supported XA
# executable is host-only.  This script therefore invokes the host VCS/XA pair
# through the required SSH port and uses the documented container-to-host path
# mapping.  Every generated file remains under diagnostics/bridge_probe_0p80.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLOW_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIAG_ROOT="${FLOW_ROOT}/diagnostics/bridge_probe_0p80"
RUN_DIR="${DIAG_ROOT}/run"
HOST_USER="zhupl@166.111.78.45"
HOST_PORT="40022"
HOST_ROOT="/home/zhupl/rocky8/container-home/zhupl25"
LOCAL_ROOT="/home/zhupl25"

mkdir -p "${RUN_DIR}"
cp "${DIAG_ROOT}/bridge_probe_0p80.sp" "${RUN_DIR}/bridge_probe_0p80.sp"
cp "${FLOW_ROOT}/src/ftc_sensor_ams_stub.sv" "${RUN_DIR}/ftc_sensor_ams_stub.sv"
cp "${FLOW_ROOT}/src/ftc_sensor_ams_wrapper.sp" "${RUN_DIR}/ftc_sensor_ams_wrapper.sp"
cp "${FLOW_ROOT}/src/tb_ftc_vcs_xa_bridge_probe.sv" "${RUN_DIR}/tb_ftc_vcs_xa_bridge_probe.sv"
cp "${FLOW_ROOT}/src/xa.cfg" "${RUN_DIR}/xa.cfg"
cp "${FLOW_ROOT}/inputs/empty_subckt.sp_cal" "${RUN_DIR}/empty_subckt.sp_cal"

# The frozen sensor is historical input and is consumed read-only.  The
# corrected deck keeps it outside the run directory and resolves its mapped
# host path below, so generated products remain task-scoped.

HOST_RUN_DIR="${HOST_ROOT}${RUN_DIR#${LOCAL_ROOT}}"
HOST_DECK="${HOST_RUN_DIR}/bridge_probe_0p80.sp"
HOST_CFG="${HOST_RUN_DIR}/xa.cfg"
# Resolve all deck includes to the mapped host path.  Relative includes would
# be ambiguous after the run directory is isolated under diagnostics/run.
HOST_FLOW_ROOT="${HOST_ROOT}${FLOW_ROOT#${LOCAL_ROOT}}"
sed -i \
    "s|../../inputs/empty_subckt.sp_cal|${HOST_FLOW_ROOT}/inputs/empty_subckt.sp_cal|; s|../../inputs/ftc_sensor_frozen.sp|${HOST_FLOW_ROOT}/../vcs_xa/inputs/ftc_sensor_frozen.sp|; s|../../src/ftc_sensor_ams_wrapper.sp|${HOST_FLOW_ROOT}/src/ftc_sensor_ams_wrapper.sp|" \
    "${RUN_DIR}/bridge_probe_0p80.sp"
cp "${RUN_DIR}/bridge_probe_0p80.sp" "${RUN_DIR}/bridge_probe_0p80.host.sp"
sed "s|PLACEHOLDER_SPICE_TOP|${HOST_DECK}|; s|PLACEHOLDER_XA_CFG|${HOST_CFG}|; s|PLACEHOLDER_XA_OUT|${HOST_RUN_DIR}/xa/xa|" \
    "${FLOW_ROOT}/src/vcsAD.init" > "${RUN_DIR}/vcsAD.init"

ssh -p "${HOST_PORT}" -o BatchMode=yes "${HOST_USER}" "bash -lc '
set -euo pipefail
export VCS_HOME=/home/soft/synopsys/vcs/P-2019.06-SP2
export XA_HOME=/home/soft/synopsys/xa/S-2021.09-SP2
export HSP_HOME=/home/soft/synopsys/hspice/P-2019.06-SP2/hspice
export PATH=\$VCS_HOME/bin:\$XA_HOME/bin:\$HSP_HOME/linux64:\$PATH
cd ${HOST_RUN_DIR}
rm -f compile.log run.log simv
vcs -full64 -sverilog -timescale=1ns/1ps -ad=vcsAD.init -debug_access+all -fsdb \\
    -o simv ftc_sensor_ams_stub.sv tb_ftc_vcs_xa_bridge_probe.sv > compile.log 2>&1
./simv > run.log 2>&1
'"

echo "Corrected bridge probe completed in ${RUN_DIR}"
