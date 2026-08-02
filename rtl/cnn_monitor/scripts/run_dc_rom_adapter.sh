#!/usr/bin/env bash
set -euo pipefail

# Run the isolated ROM hard-macro synthesis gate through the known-good local
# DC wrapper.  The wrapper's reports and mapped netlist remain in the stage run.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CNN_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
RUN_TAG=${1:?run tag is required}
RUN_ROOT="${CNN_ROOT}/runs/${RUN_TAG}"
OUT="${RUN_ROOT}/rom_adapter_dc"
ROM_DB="${RUN_ROOT}/rom_compiler/output/CNNW384X128_tt_1p10v_1p10v_25c.db"
DC_WRAPPER=${DC_WRAPPER:-/home/zhupl25/.local/bin/dc_shell}
STD_DB=${STD_DB:-/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/db/sc9mc_logic0040ll_base_rvt_c40_tt_typical_max_1p10v_25c.db}

if [[ -e "${OUT}" ]]; then
    echo "ERROR: refusing to overwrite ${OUT}" >&2
    exit 2
fi
[[ -s "${ROM_DB}" && -s "${STD_DB}" ]] || {
    echo "ERROR: ROM or standard-cell DB missing" >&2; exit 2;
}
mkdir -p "${OUT}"
ROM_ADAPTER_RUN="${OUT}" CNN_ROOT="${CNN_ROOT}" ROM_DB="${ROM_DB}" \
STD_DB="${STD_DB}" "${DC_WRAPPER}" -64bit \
    -f "${CNN_ROOT}/synthesis/dc_rom_adapter.tcl" \
    > "${OUT}/dc_stdout.log" 2> "${OUT}/dc_stderr.log"
grep -q 'CNNW384X128' "${OUT}/cell.rpt" || {
    echo "ERROR: mapped adapter report contains no CNNW384X128 cell" >&2
    exit 3
}
if grep -Eqi 'unresolved|unlinked|error' "${OUT}/check_design.rpt"; then
    echo "ERROR: adapter check_design contains link errors" >&2
    exit 3
fi
echo "ROM adapter DC gate passed: ${OUT}"
