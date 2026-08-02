#!/usr/bin/env bash
set -euo pipefail

# Run the SMIC40LL ROM compiler non-interactively on the host EDA machine.
#
# The compiler ships with an old 32-bit JVM.  On both the shared library mount
# and the container-home mount that JVM reports that server/libjvm.so is
# unavailable, although the file is present.  The proven host workaround is to
# copy the complete compiler release to a host-local mktemp directory, invoke
# its unmodified batch executable there, archive every result under runs/<tag>,
# and remove only that exact driver-owned temporary directory.
#
# Usage:
#   run_smic40ll_rom_compiler.sh <run-tag> [--preflight-only]
#
# The run root may already contain the authenticated rom_content directory,
# but rom_compiler must not exist.  This narrower refusal rule permits a single
# task run to collect all stage 8-9 artifacts without allowing stale compiler
# outputs to be overwritten.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CNN_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
RUN_TAG=${1:?run tag is required}
MODE=${2:---generate}
RUN_ROOT="${CNN_ROOT}/runs/${RUN_TAG}"
CONTENT_ROOT="${RUN_ROOT}/rom_content"
COMPILER_ROOT="${RUN_ROOT}/rom_compiler"
HOST=166.111.78.45
HOST_USER=zhupl
SSH_PORT=40022

# Container home paths map to this stable host prefix.  Resolve the relative
# suffix rather than assuming that /home/zhupl25 exists on the host itself.
CONTAINER_HOME_PREFIX=/home/zhupl25
HOST_HOME_PREFIX=/home/zhupl/rocky8/container-home/zhupl25
COMPILER_SOURCE=/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/Memory/arm/smic/logic0040ll/rom_via_hdd_rvt_rvt/r1p1

if [[ "${CNN_ROOT}" != "${CONTAINER_HOME_PREFIX}"/* ]]; then
    echo "ERROR: CNN root is outside the documented host mapping" >&2
    exit 2
fi
if [[ ! -r "${CONTENT_ROOT}/CNNW384X128.rcf" ]] \
   || [[ ! -r "${CONTENT_ROOT}/rom_content_manifest.json" ]]; then
    echo "ERROR: authenticated stage-8.1 ROM content is missing" >&2
    exit 2
fi
if [[ -e "${COMPILER_ROOT}" ]]; then
    echo "ERROR: refusing to overwrite existing compiler run: ${COMPILER_ROOT}" >&2
    exit 2
fi
if [[ "${MODE}" != "--generate" && "${MODE}" != "--preflight-only" ]]; then
    echo "ERROR: mode must be --generate or --preflight-only" >&2
    exit 2
fi

# Recheck the RCF against its authenticated manifest immediately before any
# host action.  The small Python expression parses structured JSON rather than
# relying on line-oriented text matching for a security-relevant digest.
EXPECTED_RCF_SHA=$(/home/zhupl25/miniconda3/envs/DL/bin/python -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["files"]["CNNW384X128.rcf"]["sha256"])' \
    "${CONTENT_ROOT}/rom_content_manifest.json")
OBSERVED_RCF_SHA=$(sha256sum "${CONTENT_ROOT}/CNNW384X128.rcf" | awk '{print $1}')
if [[ "${EXPECTED_RCF_SHA}" != "${OBSERVED_RCF_SHA}" ]]; then
    echo "ERROR: RCF digest differs from authenticated content manifest" >&2
    exit 2
fi

HOST_CNN_ROOT="${HOST_HOME_PREFIX}${CNN_ROOT#${CONTAINER_HOME_PREFIX}}"
HOST_RUN_ROOT="${HOST_CNN_ROOT}/runs/${RUN_TAG}"
HOST_CONTENT_ROOT="${HOST_RUN_ROOT}/rom_content"
HOST_COMPILER_ROOT="${HOST_RUN_ROOT}/rom_compiler"

# Passing all values as positional arguments keeps the remote shell script
# free of local interpolation.  It also leaves an exact command record in the
# run directory without embedding credentials or unrelated environment state.
ssh -p "${SSH_PORT}" "${HOST_USER}@${HOST}" bash -s -- \
    "${COMPILER_SOURCE}" "${HOST_CONTENT_ROOT}" "${HOST_COMPILER_ROOT}" \
    "${EXPECTED_RCF_SHA}" "${MODE}" <<'REMOTE_SCRIPT'
set -euo pipefail

compiler_source=$1
content_root=$2
compiler_root=$3
expected_rcf_sha=$4
mode=$5

if [[ ! -x "${compiler_source}/bin/rom_via_hdd_rvt_rvt" ]]; then
    echo "ERROR: SMIC40LL ROM compiler executable is unavailable" >&2
    exit 3
fi
if [[ ! -r "${content_root}/CNNW384X128.rcf" ]]; then
    echo "ERROR: mapped host RCF path is unavailable" >&2
    exit 3
fi
observed_rcf_sha=$(sha256sum "${content_root}/CNNW384X128.rcf" | awk '{print $1}')
if [[ "${observed_rcf_sha}" != "${expected_rcf_sha}" ]]; then
    echo "ERROR: host-visible RCF digest mismatch" >&2
    exit 3
fi
if [[ -e "${compiler_root}" ]]; then
    echo "ERROR: refusing to overwrite host compiler directory" >&2
    exit 3
fi

mkdir -p "${compiler_root}/evidence"
{
    echo "host=$(hostname)"
    echo "user=$(id -un)"
    echo "kernel=$(uname -srmo)"
    echo "compiler_source=${compiler_source}"
    echo "rcf_sha256=${observed_rcf_sha}"
    echo "start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "mode=${mode}"
} > "${compiler_root}/evidence/preflight.txt"

# The direct executable check is expected to fail on the mounted source tree;
# record the result without treating it as the usable compiler invocation.
set +e
"${compiler_source}/bin/rom_via_hdd_rvt_rvt" -help \
    > "${compiler_root}/evidence/source_tree_help.stdout" \
    2> "${compiler_root}/evidence/source_tree_help.stderr"
source_help_status=$?
set -e
echo "source_tree_help_status=${source_help_status}" \
    >> "${compiler_root}/evidence/preflight.txt"

if [[ "${mode}" == "--preflight-only" ]]; then
    echo "end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        >> "${compiler_root}/evidence/preflight.txt"
    exit 0
fi

# Copying the entire release is required because view generators and binary
# support data resolve relative to basedir.  The scratch path is created with
# mktemp and checked against a narrow prefix before cleanup, so no broad path,
# glob, or unresolved variable can become a destructive target.
scratch_root=$(mktemp -d /tmp/cnn_smic40ll_rom.XXXXXXXX)
case "${scratch_root}" in
    /tmp/cnn_smic40ll_rom.*) ;;
    *) echo "ERROR: mktemp returned an unexpected path" >&2; exit 4 ;;
esac
cleanup_scratch() {
    if [[ -n "${scratch_root:-}" \
          && "${scratch_root}" == /tmp/cnn_smic40ll_rom.* ]]; then
        rm -rf -- "${scratch_root}"
    fi
}
trap cleanup_scratch EXIT
cp -a "${compiler_source}" "${scratch_root}/tool_copy"
mkdir "${scratch_root}/output" "${compiler_root}/output"
cp "${content_root}/CNNW384X128.rcf" \
   "${scratch_root}/output/CNNW384X128.rcf"
cd "${scratch_root}/output"

command_file="${compiler_root}/evidence/compiler_command.txt"
cat > "${command_file}" <<'COMMAND_RECORD'
<host-mktemp>/tool_copy/bin/rom_via_hdd_rvt_rvt verilog liberty lef-fp gds2 ascii \
  -instname CNNW384X128 -words 384 -bits 128 -mux 8 \
  -code_file CNNW384X128.rcf -frequency 500 -activity_factor 100 \
  -corners tt_1p10v_1p10v_25c -libname cnnw_tt -site_def off
COMMAND_RECORD

set +e
"${scratch_root}/tool_copy/bin/rom_via_hdd_rvt_rvt" \
    verilog liberty lef-fp gds2 ascii \
    -instname CNNW384X128 -words 384 -bits 128 -mux 8 \
    -code_file CNNW384X128.rcf -frequency 500 -activity_factor 100 \
    -corners tt_1p10v_1p10v_25c -libname cnnw_tt -site_def off \
    > "${compiler_root}/evidence/compiler.stdout" \
    2> "${compiler_root}/evidence/compiler.stderr"
compiler_status=$?
set -e
echo "compiler_exit_status=${compiler_status}" \
    >> "${compiler_root}/evidence/preflight.txt"
echo "end_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    >> "${compiler_root}/evidence/preflight.txt"
if [[ ${compiler_status} -ne 0 ]]; then
    echo "ERROR: ROM compiler returned ${compiler_status}" >&2
    exit "${compiler_status}"
fi

# These are the minimum views needed by simulation, synthesis, timing, and
# physical integration.  The datatable is retained as the source of compiler
# geometry, cycle-time, and current evidence.
required_files=(
    CNNW384X128.v
    CNNW384X128_verilog.rcf
    CNNW384X128_tt_1p10v_1p10v_25c.lib
    CNNW384X128_tt_1p10v_1p10v_25c.dat
    CNNW384X128.lef
    CNNW384X128.gds2
)
for required_file in "${required_files[@]}"; do
    if [[ ! -s "${required_file}" ]]; then
        echo "ERROR: compiler did not create ${required_file}" >&2
        exit 4
    fi
done
if grep -nE '(^|[^A-Za-z])(ERROR|FATAL|Error|Fatal)([^A-Za-z]|$)' \
        "${compiler_root}/evidence/compiler.stdout" \
        "${compiler_root}/evidence/compiler.stderr"; then
    echo "ERROR: compiler log contains a fatal/error diagnostic" >&2
    exit 4
fi

# Archive the complete output only after every required view and log gate has
# passed.  The scratch tool copy is reproducible from the PDK and intentionally
# omitted from retained artifacts.
cp -a "${scratch_root}/output/." "${compiler_root}/output/"
REMOTE_SCRIPT

echo "ROM compiler ${MODE} completed under ${COMPILER_ROOT}"
