#!/usr/bin/env bash
set -euo pipefail

# Run the release 16-lane RTL through a bounded, low-effort SMIC40LL mapping.
# Every work file and report remains under the caller-provided run tag.  This
# driver is a structural gate, not a substitute for the final 500 MHz run.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CNN_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
RUN_TAG=${1:?run tag is required}
RUN_DIR="${CNN_ROOT}/runs/${RUN_TAG}"
DC_WRAPPER=${DC_WRAPPER:-/home/zhupl25/.local/bin/dc_shell}
TIMEOUT_BIN=${TIMEOUT_BIN:-/usr/bin/timeout}
TARGET_LIBRARY=${TARGET_LIBRARY:-/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/db/sc9mc_logic0040ll_base_rvt_c40_tt_typical_max_1p10v_25c.db}
ROM_DB=${ROM_DB:-${CNN_ROOT}/runs/stage89_20260801_r1/rom_compiler/output/CNNW384X128_tt_1p10v_1p10v_25c.db}

if [[ -e "${RUN_DIR}" ]]; then
    echo "ERROR: refusing to overwrite ${RUN_DIR}" >&2
    exit 2
fi
for required_file in "${DC_WRAPPER}" "${TIMEOUT_BIN}" "${TARGET_LIBRARY}" "${ROM_DB}"; do
    if [[ ! -s "${required_file}" ]]; then
        echo "ERROR: required probe input missing: ${required_file}" >&2
        exit 2
    fi
done

mkdir -p "${RUN_DIR}"
"${DC_WRAPPER}" -version > "${RUN_DIR}/dc_version.txt" 2>&1 || true
RUN_DIR="${RUN_DIR}" CNN_ROOT="${CNN_ROOT}" MAC_LANES=16 \
CLOCK_PERIOD_NS=2.000 TARGET_LIBRARY="${TARGET_LIBRARY}" ROM_DB="${ROM_DB}" \
    "${TIMEOUT_BIN}" --signal=TERM --kill-after=120s 20m \
    "${DC_WRAPPER}" -64bit -f "${CNN_ROOT}/synthesis/dc_structure_probe.tcl" \
    > "${RUN_DIR}/dc_stdout.log" 2> "${RUN_DIR}/dc_stderr.log"

# DC may return success after a recoverable Tcl error, so explicit diagnostics
# and required reports are part of the probe's pass condition.
if grep -Eqi '(^|[[:space:]])(Error|Fatal):' \
        "${RUN_DIR}/dc_stdout.log" "${RUN_DIR}/dc_stderr.log"; then
    echo "ERROR: structure-probe log contains an error or fatal diagnostic" >&2
    exit 3
fi
for required_report in qor.rpt area.rpt cell.rpt reference.rpt resources.rpt \
        check_design_postcompile.rpt timing_setup.rpt; do
    if [[ ! -s "${RUN_DIR}/${required_report}" ]]; then
        echo "ERROR: structure probe did not produce ${required_report}" >&2
        exit 3
    fi
done
if grep -Eqi 'unresolved|unlinked|multiply driven|latch' \
        "${RUN_DIR}/check_design_postcompile.rpt"; then
    echo "ERROR: structure-probe design check failed" >&2
    exit 3
fi

# report_cell without -hierarchy lists only cells directly below the top-level
# design, while the ROM resides below convolution_engine/weight_rom.  The
# hierarchical reference report contains one exact physical-reference row and
# is therefore the authoritative macro count.  For convolution multipliers we
# require both the convolution_engine hierarchy and the expected signed
# DesignWare reference.  DC embeds the SystemVerilog source line in names such
# as mult_291, so deliberately do not match that numeric suffix: an unrelated
# comment or register declaration can change it without changing the hardware.
# Unsigned DesignWare multiplier references would expose an accidental address
# multiply and remain a separate zero-count gate below.
MACRO_COUNT=$(grep -Ec '^CNNW384X128[[:space:]]' "${RUN_DIR}/reference.rpt" || true)
CONV_MULTIPLIER_COUNT=$(grep -Ec \
    '^convolution_engine/mult_[^[:space:]]*[[:space:]].*cnn_convolution_engine_MAC_LANES16_DW_mult_tc_' \
    "${RUN_DIR}/area.rpt" || true)
CLASSIFIER_MULTIPLIER_COUNT=$(grep -Ec '^pool_classifier/mult_' \
    "${RUN_DIR}/area.rpt" || true)
UNSIGNED_MULTIPLIER_COUNT=$(grep -Ec 'DW_mult_uns|MULT_UNS' \
    "${RUN_DIR}/reference.rpt" || true)
LEAF_CELL_COUNT=$(awk '/Leaf Cell Count:/ {print $4; exit}' \
    "${RUN_DIR}/qor.rpt")
SEQUENTIAL_CELL_COUNT=$(awk '/Sequential Cell Count:/ {print $4; exit}' \
    "${RUN_DIR}/qor.rpt")

printf '%s\n' \
    "rom_macro_count=${MACRO_COUNT}" \
    "conv_signed_multiplier_count=${CONV_MULTIPLIER_COUNT}" \
    "classifier_signed_multiplier_count=${CLASSIFIER_MULTIPLIER_COUNT}" \
    "address_unsigned_multiplier_count=${UNSIGNED_MULTIPLIER_COUNT}" \
    "leaf_cell_count=${LEAF_CELL_COUNT}" \
    "sequential_cell_count=${SEQUENTIAL_CELL_COUNT}" \
    'clock_period_ns=2.000' \
    'mapping_scope=structural_map_then_constrained_report' \
    > "${RUN_DIR}/structure_summary.txt"

if [[ ${MACRO_COUNT} -ne 1 ]]; then
    echo "ERROR: expected one hierarchical CNNW384X128 reference" >&2
    exit 3
fi
if [[ ${CONV_MULTIPLIER_COUNT} -ne 16 ]]; then
    echo "ERROR: expected sixteen convolution signed multipliers" >&2
    exit 3
fi
if [[ ${CLASSIFIER_MULTIPLIER_COUNT} -ne 2 ]]; then
    echo "ERROR: expected two classifier signed multipliers" >&2
    exit 3
fi
if [[ ${UNSIGNED_MULTIPLIER_COUNT} -ne 0 ]]; then
    echo "ERROR: address/control unsigned multiplier remains" >&2
    exit 3
fi
if [[ ${LEAF_CELL_COUNT} -gt 160000 ]]; then
    echo "ERROR: mapped leaf-cell count exceeds structural gate" >&2
    exit 3
fi
if [[ ${SEQUENTIAL_CELL_COUNT} -gt 12000 ]]; then
    echo "ERROR: mapped sequential-cell count exceeds structural gate" >&2
    exit 3
fi

echo "Bounded 500 MHz structural probe passed: ${RUN_DIR}"
