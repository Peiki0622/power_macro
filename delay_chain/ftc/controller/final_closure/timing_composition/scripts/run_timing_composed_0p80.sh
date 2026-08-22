#!/usr/bin/env bash
# ============================================================================
# C3 timing-composed 0.80 V autonomous closure.
#
# This is the only mandatory new transient in the final-closure plan.  It
# combines the frozen synthesized controller, Phase 7 SDF, corrected VCS-XA
# bridge, and frozen transistor sensor at the canonical 1 ns clock.  The
# external bench owns only POR, start, clock, and the analog VDD parameter.
# No +nospecify or +notimingcheck bypass is permitted.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSITION_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONTROLLER_ROOT="$(cd "${COMPOSITION_ROOT}/../.." && pwd)"
SOURCE_ROOT="${COMPOSITION_ROOT}/src"
RUN_ROOT="${COMPOSITION_ROOT}/runs/timing_composed_0p80"
REPORT_ROOT="${COMPOSITION_ROOT}/reports"
LOCAL_ROOT="/home/zhupl25"
HOST_ROOT="/home/zhupl/rocky8/container-home/zhupl25"
HOST_USER="zhupl@166.111.78.45"
HOST_PORT="40022"
HOST_RUN_ROOT="${HOST_ROOT}${RUN_ROOT#${LOCAL_ROOT}}"

# Verify the frozen contract and hashes before copying anything into the run.
# C2 already owns the SDF preflight report; do not regenerate that report here,
# because doing so would erase the completed remote annotation statistics.
python3 - "${COMPOSITION_ROOT}/inputs/input_sha256.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for item in manifest["files"]:
    path = Path(item["path"])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != item["sha256"]:
        raise SystemExit("C3 input hash mismatch: " + item["path"])
print("C3 input hashes verified: %d files" % len(manifest["files"]))
PY

mkdir -p "${RUN_ROOT}"
cp "${CONTROLLER_ROOT}/synthesis/netlist/ftc_cal_controller_top_synth.v" "${RUN_ROOT}/ftc_cal_controller_top_synth.v"
cp "${CONTROLLER_ROOT}/synthesis/netlist/ftc_cal_controller_top_synth.sdf" "${RUN_ROOT}/ftc_cal_controller_top_synth.sdf"
cp "${CONTROLLER_ROOT}/analysis/phase9_autonomous_transistor_level/vcs_xa/inputs/sc9mc_logic0040ll_base_rvt_c40.v" "${RUN_ROOT}/sc9mc_logic0040ll_base_rvt_c40.v"
cp "${CONTROLLER_ROOT}/analysis/phase9_autonomous_transistor_level/vcs_xa/inputs/ftc_sensor_frozen.sp" "${RUN_ROOT}/ftc_sensor_frozen.sp"
cp "${CONTROLLER_ROOT}/analysis/phase9_autonomous_transistor_level/vcs_xa/inputs/empty_subckt.sp_cal" "${RUN_ROOT}/empty_subckt.sp_cal"
cp "${SOURCE_ROOT}/ftc_sensor_ams_stub.sv" "${RUN_ROOT}/ftc_sensor_ams_stub.sv"
cp "${SOURCE_ROOT}/ftc_sensor_ams_wrapper.sp" "${RUN_ROOT}/ftc_sensor_ams_wrapper.sp"
cp "${SOURCE_ROOT}/tb_ftc_vcs_xa_autonomous.sv" "${RUN_ROOT}/tb_ftc_vcs_xa_autonomous.sv"
cp "${SOURCE_ROOT}/timing_composition_monitor.sv" "${RUN_ROOT}/timing_composition_monitor.sv"
cp "${SOURCE_ROOT}/xa.cfg" "${RUN_ROOT}/xa.cfg"

# The SPICE deck is the same corrected bridge topology as Phase 9.  Only the
# scenario VDD and bounded transient duration are selected for C3; all bridge
# conversion policies remain the frozen contract values.
cat > "${RUN_ROOT}/timing_composed_0p80.sp" <<EOF
* C3 0.80 V timing-composed autonomous closure.
.option post=1 probe
.param VDD_VALUE=0.80
.lib /home/yangz/virtuoso/SMIC40TXRX/smic40ll_1125_2tm_oa_cds_1P9M_2012_10_11_v1.4/models/hspice/l0040ll_v1p4_1r.lib tt
.include /home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/cdl/sc9mc_logic0040ll_base_rvt_c40.cdl
.include /home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/cdl/sc9mc_logic0040ll_base_lvt_c40.cdl
.include ${HOST_RUN_ROOT}/empty_subckt.sp_cal
.include ${HOST_RUN_ROOT}/ftc_sensor_frozen.sp
.include ${HOST_RUN_ROOT}/ftc_sensor_ams_wrapper.sp
.probe tran V(VDD_LOCAL) V(VSS_LOCAL) V(sense_s_clk) V(sense_dff_reset) V(q_final)
.tran 500p 705n
.end
EOF

sed "s|PLACEHOLDER_SPICE_TOP|${HOST_RUN_ROOT}/timing_composed_0p80.sp|; s|PLACEHOLDER_XA_CFG|${HOST_RUN_ROOT}/xa.cfg|; s|PLACEHOLDER_XA_OUT|${HOST_RUN_ROOT}/xa/xa|" \
    "${CONTROLLER_ROOT}/analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/src/vcsAD.init" > "${RUN_ROOT}/vcsAD.init"

ssh -p "${HOST_PORT}" -o BatchMode=yes "${HOST_USER}" "bash -s" <<EOF
set -euo pipefail
export LC_ALL=C
export LANG=C
export VCS_HOME=/home/soft/synopsys/vcs/P-2019.06-SP2
export XA_HOME=/home/soft/synopsys/xa/S-2021.09-SP2
export HSP_HOME=/home/soft/synopsys/hspice/P-2019.06-SP2/hspice
export PATH=\${VCS_HOME}/bin:\${XA_HOME}/bin:\${HSP_HOME}/linux64:\$PATH
cd ${HOST_RUN_ROOT}
rm -rf xa
rm -f compile.log run.log simv timing_events.csv
mkdir -p xa
vcs -full64 -sverilog -timescale=1ns/1ps +v2k +define+AUTONOMOUS_0P80 \\
    -ad=vcsAD.init -debug_access+all -fsdb +neg_tchk \\
    -sdf max:tb_ftc_vcs_xa_autonomous.u_controller:ftc_cal_controller_top_synth.sdf \\
    -o simv sc9mc_logic0040ll_base_rvt_c40.v ftc_cal_controller_top_synth.v \\
    ftc_sensor_ams_stub.sv tb_ftc_vcs_xa_autonomous.sv timing_composition_monitor.sv > compile.log 2>&1
./simv > run.log 2>&1
EOF

cp "${RUN_ROOT}/compile.log" "${REPORT_ROOT}/timing_composed_0p80_compile.log"
cp "${RUN_ROOT}/run.log" "${REPORT_ROOT}/timing_composed_0p80_run.log"
python3 "${COMPOSITION_ROOT}/scripts/audit_timing_composed.py" "${RUN_ROOT}"
