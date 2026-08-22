#!/usr/bin/env bash
# ============================================================================
# C2 static/elaboration-only SDF composition preflight.
#
# This launcher deliberately stops after VCS elaboration.  It never executes
# the generated ``simv`` and therefore cannot consume transient-simulation
# budget.  The controller instance, SDF, bridge, and transistor sensor inputs
# are copied into one task-owned directory; the historical Phase 9 run trees
# remain immutable and raw databases stay below ``diagnostics``/``runs``.
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSITION_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONTROLLER_ROOT="$(cd "${COMPOSITION_ROOT}/../.." && pwd)"
REPO_ROOT="$(cd "${CONTROLLER_ROOT}/../../.." && pwd)"
INPUT_ROOT="${COMPOSITION_ROOT}/inputs"
SOURCE_ROOT="${COMPOSITION_ROOT}/src"
REPORT_ROOT="${COMPOSITION_ROOT}/reports"
RUN_ROOT="${COMPOSITION_ROOT}/diagnostics/sdf_preflight"

# The mapped workspace path is part of the host EDA contract.  The host copy
# is used only for compilation and elaboration, and it is never confused with
# the container-local path in the evidence report.
HOST_USER="zhupl@166.111.78.45"
HOST_PORT="40022"
LOCAL_ROOT="/home/zhupl25"
HOST_ROOT="/home/zhupl/rocky8/container-home/zhupl25"
HOST_RUN_ROOT="${HOST_ROOT}${RUN_ROOT#${LOCAL_ROOT}}"

python3 "${SCRIPT_DIR}/prepare_sdf_preflight.py"

mkdir -p "${RUN_ROOT}"
cp "${CONTROLLER_ROOT}/synthesis/netlist/ftc_cal_controller_top_synth.v" "${RUN_ROOT}/ftc_cal_controller_top_synth.v"
cp "${CONTROLLER_ROOT}/synthesis/netlist/ftc_cal_controller_top_synth.sdf" "${RUN_ROOT}/ftc_cal_controller_top_synth.sdf"
cp "${CONTROLLER_ROOT}/analysis/phase9_autonomous_transistor_level/vcs_xa/inputs/sc9mc_logic0040ll_base_rvt_c40.v" "${RUN_ROOT}/sc9mc_logic0040ll_base_rvt_c40.v"
cp "${CONTROLLER_ROOT}/analysis/phase9_autonomous_transistor_level/vcs_xa/inputs/ftc_sensor_frozen.sp" "${RUN_ROOT}/ftc_sensor_frozen.sp"
cp "${CONTROLLER_ROOT}/analysis/phase9_autonomous_transistor_level/vcs_xa/inputs/empty_subckt.sp_cal" "${RUN_ROOT}/empty_subckt.sp_cal"
cp "${SOURCE_ROOT}/ftc_sensor_ams_stub.sv" "${RUN_ROOT}/ftc_sensor_ams_stub.sv"
cp "${SOURCE_ROOT}/ftc_sensor_ams_wrapper.sp" "${RUN_ROOT}/ftc_sensor_ams_wrapper.sp"
cp "${SOURCE_ROOT}/tb_ftc_vcs_xa_autonomous.sv" "${RUN_ROOT}/tb_ftc_vcs_xa_autonomous.sv"

# The XA bridge requires a real SPICE top even though this C2 stage will not
# launch the generated simv.  The deck is deliberately bounded to a one-point
# transient description solely as a valid XA input; because simv is never
# executed, no transient sample is produced and the C2 budget remains zero.
cat > "${RUN_ROOT}/timing_composed_preflight.sp" <<EOF
* C2 bridge/elaboration-only deck; simv is intentionally not executed.
.option post=1 probe
.param VDD_VALUE=0.80
.lib /home/yangz/virtuoso/SMIC40TXRX/smic40ll_1125_2tm_oa_cds_1P9M_2012_10_11_v1.4/models/hspice/l0040ll_v1p4_1r.lib tt
.include /home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/cdl/sc9mc_logic0040ll_base_rvt_c40.cdl
.include /home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/cdl/sc9mc_logic0040ll_base_lvt_c40.cdl
.include ${HOST_RUN_ROOT}/empty_subckt.sp_cal
.include ${HOST_RUN_ROOT}/ftc_sensor_frozen.sp
.include ${HOST_RUN_ROOT}/ftc_sensor_ams_wrapper.sp
.probe tran V(VDD_LOCAL) V(VSS_LOCAL) V(sense_s_clk) V(sense_dff_reset) V(q_final)
.tran 500p 1n
.end
EOF

sed "s|PLACEHOLDER_SPICE_TOP|${HOST_RUN_ROOT}/timing_composed_preflight.sp|; s|PLACEHOLDER_XA_CFG|${HOST_RUN_ROOT}/xa.cfg|; s|PLACEHOLDER_XA_OUT|${HOST_RUN_ROOT}/xa/xa|" \
    "${CONTROLLER_ROOT}/analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/src/vcsAD.init" > "${RUN_ROOT}/vcsAD.init"
cp "${SOURCE_ROOT}/xa.cfg" "${RUN_ROOT}/xa.cfg"

# The preflight compiles the corrected mixed-signal sources with SDF enabled,
# but the absence of ``-R`` is intentional: no transient is launched here.
# Timing checks remain enabled because the forbidden bypass flags are omitted.
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
rm -f compile.log elaborate.log simv
mkdir -p xa
vcs -full64 -sverilog -timescale=1ns/1ps +v2k +define+AUTONOMOUS_0P80 \\
    -ad=vcsAD.init -debug_access+all -fsdb +neg_tchk \\
    -sdf max:tb_ftc_vcs_xa_autonomous.u_controller:ftc_cal_controller_top_synth.sdf \\
    -o simv \\
    sc9mc_logic0040ll_base_rvt_c40.v \\
    ftc_cal_controller_top_synth.v \\
    ftc_sensor_ams_stub.sv \\
    tb_ftc_vcs_xa_autonomous.sv > compile.log 2>&1
printf "TRANSIENT_NOT_STARTED\\n" > elaborate.log
EOF

cp "${RUN_ROOT}/compile.log" "${REPORT_ROOT}/SDF_PREflight_compile.log" 2>/dev/null || true

python3 - "${RUN_ROOT}" "${REPORT_ROOT}/SDF_ANNOTATION_PREFLIGHT.json" <<'PY'
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
report_path = Path(sys.argv[2])
compile_log = run / "compile.log"
text = compile_log.read_text(encoding="utf-8", errors="replace")
forbidden = [flag for flag in ("+nospecify", "+notimingcheck") if flag in text]
# VCS prints accepted negative SDF hold/recovery values with the literal
# phrase ``SDF Error``.  They are retained as annotation statistics; only
# compiler error codes and fatal diagnostics invalidate this preflight.
fatal = [
    line
    for line in text.splitlines()
    if ("Error-[" in line or "FATAL" in line or "fatal" in line.lower())
    and "SDF Error" not in line
]
annotation_completed = "SDF annotation completed" in text
error_count = None
warning_count = None
for line in text.splitlines():
    if "Total errors:" in line:
        error_count = line.strip()
    if "Total warnings:" in line:
        warning_count = line.strip()
report = json.loads(report_path.read_text(encoding="utf-8"))
report["remote_elaboration"] = {
    "performed": True,
    "compile_log": str(compile_log),
    "transient_started": False,
    "forbidden_flags_observed": forbidden,
    "fatal_lines": fatal[:20],
    "annotation_completed": annotation_completed,
    "annotation_error_summary": error_count,
    "annotation_warning_summary": warning_count,
    "negative_timing_checks_enabled": "+neg_tchk" in text,
    "compile_exit_status": 0,
}
report["status"] = "GO" if annotation_completed and not forbidden and not fatal else "FAIL"
report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
if report["status"] != "GO":
    raise SystemExit("C2 elaboration preflight failed")
print(json.dumps(report, indent=2, sort_keys=True))
PY
