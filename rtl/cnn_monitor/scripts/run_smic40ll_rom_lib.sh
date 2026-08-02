#!/usr/bin/env bash
set -euo pipefail

# Create the TT ROM .db on the host EDA machine, then independently validate it
# in the container.  Library Compiler is host-only.  The validated DC wrapper
# is container-local because its DC installation and compatibility libraries
# are not mounted at the same absolute path on the host login shell.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CNN_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
RUN_TAG=${1:?run tag is required}
RUN_ROOT="${CNN_ROOT}/runs/${RUN_TAG}"
OUTPUT_ROOT="${RUN_ROOT}/rom_compiler/output"
EVIDENCE_ROOT="${RUN_ROOT}/rom_compiler/evidence"
LIBERTY="${OUTPUT_ROOT}/CNNW384X128_tt_1p10v_1p10v_25c.lib"
ROM_DB="${OUTPUT_ROOT}/CNNW384X128_tt_1p10v_1p10v_25c.db"
ROM_LIBRARY_NAME=cnnw_tt_tt_1p10v_1p10v_25c

CONTAINER_HOME_PREFIX=/home/zhupl25
HOST_HOME_PREFIX=/home/zhupl/rocky8/container-home/zhupl25
HOST=zhupl@166.111.78.45
SSH_PORT=40022
LC_SHELL=/home/soft/synopsys/library_compiler/bin/lc_shell
DC_WRAPPER=/home/zhupl25/.local/bin/dc_shell

if [[ "${CNN_ROOT}" != "${CONTAINER_HOME_PREFIX}"/* ]]; then
    echo "ERROR: CNN root is outside the documented host mapping" >&2
    exit 2
fi
if [[ ! -s "${LIBERTY}" ]]; then
    echo "ERROR: generated TT Liberty view is missing" >&2
    exit 2
fi
if [[ -e "${ROM_DB}" ]]; then
    echo "ERROR: refusing to overwrite existing ROM database" >&2
    exit 2
fi

HOST_CNN_ROOT="${HOST_HOME_PREFIX}${CNN_ROOT#${CONTAINER_HOME_PREFIX}}"
HOST_LIBERTY="${HOST_CNN_ROOT}/runs/${RUN_TAG}/rom_compiler/output/${LIBERTY##*/}"
HOST_ROM_DB="${HOST_CNN_ROOT}/runs/${RUN_TAG}/rom_compiler/output/${ROM_DB##*/}"
HOST_EVIDENCE="${HOST_CNN_ROOT}/runs/${RUN_TAG}/rom_compiler/evidence"
HOST_LC_TCL="${HOST_CNN_ROOT}/synthesis/compile_rom_lib.tcl"
HOST_DC_TCL="${HOST_CNN_ROOT}/synthesis/check_rom_db.tcl"

ssh -p "${SSH_PORT}" "${HOST}" bash -s -- \
    "${LC_SHELL}" "${HOST_LIBERTY}" "${HOST_ROM_DB}" \
    "${ROM_LIBRARY_NAME}" "${HOST_EVIDENCE}" "${HOST_LC_TCL}" "${HOST_DC_TCL}" <<'REMOTE_SCRIPT'
set -euo pipefail
lc_shell=$1
rom_liberty=$2
rom_db=$3
rom_library_name=$4
evidence_root=$5
lc_tcl=$6
dc_tcl=$7

for executable in "${lc_shell}"; do
    if [[ ! -x "${executable}" ]]; then
        echo "ERROR: required Synopsys executable is unavailable: ${executable}" >&2
        exit 3
    fi
done
{
    echo "start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "lc_shell=${lc_shell}"
    echo "rom_liberty=${rom_liberty}"
    echo "rom_db=${rom_db}"
} > "${evidence_root}/rom_db_command.txt"

ROM_LIBERTY="${rom_liberty}" ROM_DB="${rom_db}" \
ROM_LIBRARY_NAME="${rom_library_name}" \
ROM_LC_REPORT="${evidence_root}/lc_report_lib.rpt" \
    "${lc_shell}" -f "${lc_tcl}" \
    > "${evidence_root}/lc_stdout.log" \
    2> "${evidence_root}/lc_stderr.log"

{
    echo "end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    sha256sum "${rom_liberty}" "${rom_db}"
} >> "${evidence_root}/rom_db_command.txt"
REMOTE_SCRIPT

[[ -s "${ROM_DB}" ]] || { echo "ERROR: Library Compiler produced no .db" >&2; exit 4; }

# The container-local wrapper was the one previously proven to load this
# database without the official DC startup crash.  Keep its reports beside
# the host-generated database and make failure explicit.
ROM_DB="${ROM_DB}" ROM_LIBRARY_NAME="${ROM_LIBRARY_NAME}" \
ROM_DC_LIBRARY_REPORT="${EVIDENCE_ROOT}/dc_report_lib.rpt" \
ROM_DC_CELL_REPORT="${EVIDENCE_ROOT}/dc_report_lib_cell.rpt" \
    "${DC_WRAPPER}" -64bit -f "${CNN_ROOT}/synthesis/check_rom_db.tcl" \
    > "${EVIDENCE_ROOT}/dc_read_db_stdout.log" \
    2> "${EVIDENCE_ROOT}/dc_read_db_stderr.log"
echo "ROM database created and container DC wrapper validation passed: ${ROM_DB}"
