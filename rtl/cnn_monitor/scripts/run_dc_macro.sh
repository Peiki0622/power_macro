#!/usr/bin/env bash
set -euo pipefail

# Run the release 16-lane CNN against the SMIC40LL TT standard-cell library and
# the generated CNNW384X128 TT hard-macro DB.  The driver accepts a task-scoped
# run tag, refuses to overwrite an existing output, and archives all DC text,
# reports, mapped netlists, constraints, and databases below that directory.

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
        echo "ERROR: required synthesis input missing: ${required_file}" >&2
        exit 2
    fi
done

mkdir -p "${RUN_DIR}"
"${DC_WRAPPER}" -version > "${RUN_DIR}/dc_version.txt" 2>&1 || true
# A full run that cannot complete within 45 minutes is itself a failed QoR
# result for this small block.  TERM gives DC an opportunity to flush its log;
# KILL is used only if the wrapper remains alive for another two minutes.
RUN_DIR="${RUN_DIR}" CNN_ROOT="${CNN_ROOT}" MAC_LANES=16 \
CLOCK_PERIOD_NS=2.000 TARGET_LIBRARY="${TARGET_LIBRARY}" ROM_DB="${ROM_DB}" \
    "${TIMEOUT_BIN}" --signal=TERM --kill-after=120s 45m \
    "${DC_WRAPPER}" -64bit -f "${CNN_ROOT}/synthesis/dc_synthesize.tcl" \
    > "${RUN_DIR}/dc_stdout.log" 2> "${RUN_DIR}/dc_stderr.log"

# A zero process exit is insufficient: DC continues after many Tcl and design
# errors.  Reject every explicit error/fatal message before consuming reports.
if grep -Eqi '(^|[[:space:]])(Error|Fatal):' \
        "${RUN_DIR}/dc_stdout.log" "${RUN_DIR}/dc_stderr.log"; then
    echo "ERROR: Design Compiler log contains an error or fatal diagnostic" >&2
    exit 3
fi

# Fail if an interrupted or partially successful DC invocation omitted any
# release report.  DC can return zero after recoverable Tcl diagnostics, so
# report completeness is part of the synthesis contract rather than a later
# manual assumption.
for required_report in qor.rpt area.rpt cell.rpt reference.rpt resources.rpt \
        check_design_postcompile.rpt check_timing.rpt timing_setup.rpt \
        constraint_violators.rpt power_vectorless.rpt; do
    if [[ ! -s "${RUN_DIR}/${required_report}" ]]; then
        echo "ERROR: full synthesis did not produce ${required_report}" >&2
        exit 3
    fi
done
if grep -Eqi 'unresolved|unlinked|multiply driven|latch' \
        "${RUN_DIR}/check_design_postcompile.rpt"; then
    echo "ERROR: postcompile structural check failed" >&2
    exit 3
fi

# The macro is nested below convolution_engine/weight_rom, so the hierarchical
# reference report, not top-level-only report_cell output, is authoritative.
# WNS and TNS are read from report_qor and enforced numerically; a structurally
# valid netlist that misses 500 MHz is not a completed release result.
MACRO_COUNT=$(grep -Ec '^CNNW384X128[[:space:]]' \
    "${RUN_DIR}/reference.rpt" || true)
WNS_NS=$(awk '/Critical Path Slack:/ {print $4; exit}' "${RUN_DIR}/qor.rpt")
TNS_NS=$(awk '/Total Negative Slack:/ {print $4; exit}' "${RUN_DIR}/qor.rpt")
LEAF_CELL_COUNT=$(awk '/Leaf Cell Count:/ {print $4; exit}' \
    "${RUN_DIR}/qor.rpt")
SEQUENTIAL_CELL_COUNT=$(awk '/Sequential Cell Count:/ {print $4; exit}' \
    "${RUN_DIR}/qor.rpt")
CELL_AREA_UM2=$(awk '/Cell Area:/ {print $3; exit}' "${RUN_DIR}/qor.rpt")

printf '%s\n' \
    "rom_macro_count=${MACRO_COUNT}" \
    "setup_wns_ns=${WNS_NS}" \
    "setup_tns_ns=${TNS_NS}" \
    "leaf_cell_count=${LEAF_CELL_COUNT}" \
    "sequential_cell_count=${SEQUENTIAL_CELL_COUNT}" \
    "cell_area_um2=${CELL_AREA_UM2}" \
    'clock_period_ns=2.000' \
    'library_corner=TT_1p10V_25C' \
    > "${RUN_DIR}/synthesis_summary.txt"

if [[ ${MACRO_COUNT} -ne 1 ]]; then
    echo "ERROR: final hierarchy does not contain exactly one CNNW384X128" >&2
    exit 3
fi
if ! awk -v value="${WNS_NS}" 'BEGIN {exit !(value >= 0.0)}'; then
    echo "ERROR: 500 MHz setup WNS is negative (${WNS_NS} ns)" >&2
    exit 3
fi
if ! awk -v value="${TNS_NS}" 'BEGIN {exit !(value == 0.0)}'; then
    echo "ERROR: 500 MHz setup TNS is nonzero (${TNS_NS} ns)" >&2
    exit 3
fi

echo "Full 500 MHz macro-aware DC run passed timing and structural gates: ${RUN_DIR}"
