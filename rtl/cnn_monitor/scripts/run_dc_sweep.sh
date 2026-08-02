#!/usr/bin/env bash
set -euo pipefail

# Run 4/8/16-lane comparisons at the conservative 4 ns constraint, then retain
# a separate 16-lane attempt at the preferred 765 MHz period.  Each invocation
# owns a unique subdirectory and therefore cannot overwrite another DC database.
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CNN_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
RUN_TAG=${1:-dc_sweep_20260801_r1}
SWEEP_ROOT="${CNN_ROOT}/runs/${RUN_TAG}"
DC_BIN=${DC_BIN:-dc_shell}
TARGET_LIBRARY=${TARGET_LIBRARY:-/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/db/sc9mc_logic0040ll_base_rvt_c40_tt_typical_max_1p10v_25c.db}

mkdir -p "${SWEEP_ROOT}"
# W-2024.09 prints a valid version record but returns status 1 for -version.
# Preserve the evidence without allowing that query-only convention to abort
# the sweep; synthesis invocations below remain protected by set -o pipefail.
"${DC_BIN}" -version > "${SWEEP_ROOT}/dc_version.txt" || true

run_point() {
    local lanes=$1
    local period=$2
    local point_name=$3
    local point_dir="${SWEEP_ROOT}/${point_name}"
    mkdir -p "${point_dir}"
    RUN_DIR="${point_dir}" \
    CNN_ROOT="${CNN_ROOT}" \
    MAC_LANES="${lanes}" \
    CLOCK_PERIOD_NS="${period}" \
    TARGET_LIBRARY="${TARGET_LIBRARY}" \
        "${DC_BIN}" -64bit -f "${CNN_ROOT}/synthesis/dc_synthesize.tcl" \
        | tee "${point_dir}/dc_stdout.log"
}

run_point 4  4.0         lanes4_period4ns
run_point 8  4.0         lanes8_period4ns
run_point 16 4.0         lanes16_period4ns
run_point 16 1.307189542 lanes16_period1p307189542ns
