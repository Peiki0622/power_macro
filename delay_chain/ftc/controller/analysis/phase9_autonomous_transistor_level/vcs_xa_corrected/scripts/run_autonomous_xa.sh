#!/usr/bin/env bash
# ============================================================================
# Run one corrected autonomous Phase 9 scenario on the configured EDA host.
#
# The script is intentionally scenario-agnostic.  It copies the same corrected
# wrapper, controller netlist, sensor netlist, audit testbench, and XA config
# for every voltage; only VDD_VALUE, the expected final trajectory, and the
# task-scoped run directory differ.  This prevents per-voltage bridge tuning.
# ============================================================================
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 autonomous_0p80|autonomous_0p95|autonomous_1p10" >&2
    exit 2
fi
SCENARIO="$1"
case "${SCENARIO}" in
    autonomous_0p80) SUPPLY="0.80"; FINAL_M="7"; FINAL_F="6"; OPS="45"; CFGS="17"; PROBES="28"; SCENARIO_DEFINE="AUTONOMOUS_0P80";;
    autonomous_0p95) SUPPLY="0.95"; FINAL_M="4"; FINAL_F="6"; OPS="36"; CFGS="14"; PROBES="22"; SCENARIO_DEFINE="AUTONOMOUS_0P95";;
    autonomous_1p10) SUPPLY="1.10"; FINAL_M="2"; FINAL_F="9"; OPS="36"; CFGS="15"; PROBES="21"; SCENARIO_DEFINE="AUTONOMOUS_1P10";;
    *) echo "unknown scenario ${SCENARIO}" >&2; exit 2;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLOW_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOCAL_ROOT="/home/zhupl25"
HOST_ROOT="/home/zhupl/rocky8/container-home/zhupl25"
RUN_DIR="${FLOW_ROOT}/runs/${SCENARIO}"
HOST_RUN_DIR="${HOST_ROOT}${RUN_DIR#${LOCAL_ROOT}}"
HOST_FLOW_ROOT="${HOST_ROOT}${FLOW_ROOT#${LOCAL_ROOT}}"
HOST_USER="zhupl@166.111.78.45"
HOST_PORT="40022"

mkdir -p "${RUN_DIR}"
cp "${FLOW_ROOT}/src/ftc_sensor_ams_stub.sv" "${RUN_DIR}/ftc_sensor_ams_stub.sv"
cp "${FLOW_ROOT}/src/ftc_sensor_ams_wrapper.sp" "${RUN_DIR}/ftc_sensor_ams_wrapper.sp"
cp "${FLOW_ROOT}/src/tb_ftc_vcs_xa_autonomous.sv" "${RUN_DIR}/tb_ftc_vcs_xa_autonomous.sv"
cp "${FLOW_ROOT}/src/xa.cfg" "${RUN_DIR}/xa.cfg"
cp "${FLOW_ROOT}/inputs/empty_subckt.sp_cal" "${RUN_DIR}/empty_subckt.sp_cal"
# The autonomous bench instantiates the frozen synthesized controller by
# module name.  VCS therefore needs both the exact synthesis snapshot and the
# standard-cell behavioral models that implement every cell in that snapshot.
# These files are copied into the task-scoped run directory so the remote
# compile command is self-contained and leaves no generated artifacts in the
# source or historical NO-GO trees.  They are invariant across all voltages.
cp "${FLOW_ROOT}/../vcs_xa/inputs/ftc_cal_controller_top_synth.v" "${RUN_DIR}/ftc_cal_controller_top_synth.v"
cp "${FLOW_ROOT}/../vcs_xa/inputs/sc9mc_logic0040ll_base_rvt_c40.v" "${RUN_DIR}/sc9mc_logic0040ll_base_rvt_c40.v"

cat > "${RUN_DIR}/${SCENARIO}.sp" <<EOF
* Corrected autonomous Phase 9 ${SCENARIO} deck.
* The testbench owns only POR/start/clock.  Sensor VDD/VSS are private
* wrapper nodes, and VDD_VALUE is the only scenario-specific analog setting.
.option post=1 probe
.param VDD_VALUE=${SUPPLY}
.lib /home/yangz/virtuoso/SMIC40TXRX/smic40ll_1125_2tm_oa_cds_1P9M_2012_10_11_v1.4/models/hspice/l0040ll_v1p4_1r.lib tt
.include /home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/cdl/sc9mc_logic0040ll_base_rvt_c40.cdl
.include /home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/cdl/sc9mc_logic0040ll_base_lvt_c40.cdl
.include ${HOST_FLOW_ROOT}/../vcs_xa/inputs/empty_subckt.sp_cal
.include ${HOST_FLOW_ROOT}/../vcs_xa/inputs/ftc_sensor_frozen.sp
.include ${HOST_FLOW_ROOT}/src/ftc_sensor_ams_wrapper.sp
.probe tran V(VDD_LOCAL) V(VSS_LOCAL) V(sense_s_clk) V(sense_dff_reset) V(q_final)
.tran 500p 705n
.end
EOF

HOST_DECK="${HOST_RUN_DIR}/${SCENARIO}.sp"
HOST_CFG="${HOST_RUN_DIR}/xa.cfg"
sed "s|PLACEHOLDER_SPICE_TOP|${HOST_DECK}|; s|PLACEHOLDER_XA_CFG|${HOST_CFG}|; s|PLACEHOLDER_XA_OUT|${HOST_RUN_DIR}/xa/xa|" "${FLOW_ROOT}/src/vcsAD.init" > "${RUN_DIR}/vcsAD.init"

ssh -p "${HOST_PORT}" -o BatchMode=yes "${HOST_USER}" "bash -lc '
set -euo pipefail
export VCS_HOME=/home/soft/synopsys/vcs/P-2019.06-SP2
export XA_HOME=/home/soft/synopsys/xa/S-2021.09-SP2
export HSP_HOME=/home/soft/synopsys/hspice/P-2019.06-SP2/hspice
export PATH=\$VCS_HOME/bin:\$XA_HOME/bin:\$HSP_HOME/linux64:\$PATH
cd ${HOST_RUN_DIR}
# Remove only simulator products owned by this scenario.  This also clears a
# stale XA pid/log lock left by an interrupted task-scoped run; source inputs,
# compact reports, and the historical flow are outside this cleanup target.
rm -rf xa
rm -f compile.log run.log controller_events.csv
vcs -full64 -sverilog -timescale=1ns/1ps +v2k +define+${SCENARIO_DEFINE} +nospecify +notimingcheck -ad=vcsAD.init -debug_access+all -fsdb -o simv \\
    sc9mc_logic0040ll_base_rvt_c40.v ftc_cal_controller_top_synth.v \\
    ftc_sensor_ams_stub.sv tb_ftc_vcs_xa_autonomous.sv > compile.log 2>&1
./simv > run.log 2>&1
'"

python3 - "${RUN_DIR}" "${SCENARIO}" "${SUPPLY}" "${FINAL_M}" "${FINAL_F}" "${OPS}" "${CFGS}" "${PROBES}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
scenario, supply, final_m, final_f, ops, cfgs, probes = sys.argv[2:]
log = (run / "run.log").read_text(encoding="utf-8", errors="replace")
status = "PASS" if ("R6_PASS" in log and "R6_FAIL" not in log) else "FAIL"
report = {
    "schema_version": 1,
    "scenario": scenario,
    "supply_v": float(supply),
    "clock_period_ns": 1,
    "status": status,
    "expected": {"final_medium": int(final_m), "final_fine": int(final_f), "operations": int(ops), "configs": int(cfgs), "probes": int(probes), "sclk_rising_edges": int(probes), "sample1": int(probes), "sample2": int(probes)},
    "r6_pass_marker": "R6_PASS" in log,
    "evidence": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in (("compile_log", run / "compile.log"), ("run_log", run / "run.log"), ("event_csv", run / "controller_events.csv")) if path.exists()},
    "tool_pair": "VCS P-2019.06-SP2_Full64 + PrimeSim XA S-2021.09-SP2",
    "bridge_parameters_retuned_per_voltage": False,
}
(run / (scenario + "_audit.json")).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2, sort_keys=True))
if status != "PASS":
    raise SystemExit(1)
PY
