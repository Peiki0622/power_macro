#!/usr/bin/env bash
set -euo pipefail

# Compile and run the exhaustive ROM adapter test.  All compiler model copies,
# VCS objects, logs, and the executable remain under the selected run tag.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CNN_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
RUN_TAG=${1:?run tag is required}
RUN_ROOT="${CNN_ROOT}/runs/${RUN_TAG}"
ROM_ROOT="${RUN_ROOT}/rom_compiler/output"
CHECK_ROOT="${RUN_ROOT}/rom_adapter_check"
VCS_BIN=${VCS_BIN:-/home/synopsys/vcs/W-2024.09/bin/vcs}

if [[ -e "${CHECK_ROOT}" ]]; then
    echo "ERROR: refusing to overwrite ROM adapter check directory" >&2
    exit 2
fi
for input_file in CNNW384X128.v CNNW384X128_verilog.rcf; do
    [[ -s "${ROM_ROOT}/${input_file}" ]] || {
        echo "ERROR: missing compiler view ${input_file}" >&2; exit 2;
    }
done
mkdir -p "${CHECK_ROOT}/csrc"
cp "${ROM_ROOT}/CNNW384X128.v" "${CHECK_ROOT}/CNNW384X128.v"
cp "${ROM_ROOT}/CNNW384X128_verilog.rcf" "${CHECK_ROOT}/CNNW384X128_verilog.rcf"
cd "${CHECK_ROOT}"
"${VCS_BIN}" -full64 -sverilog -DARM_UD_MODEL -DCNN_ROM_COMPILER_MODEL \
    -timescale=1ns/1ps \
    -top cnn_weight_rom_tb \
    "${CHECK_ROOT}/CNNW384X128.v" \
    "${CNN_ROOT}/rtl/cnn_weight_rom.sv" \
    "${CNN_ROOT}/tb/cnn_weight_rom_tb.sv" \
    -Mdir="${CHECK_ROOT}/csrc" -o "${CHECK_ROOT}/simv" \
    -l "${CHECK_ROOT}/compile.log"
"${CHECK_ROOT}/simv" -l "${CHECK_ROOT}/simulation.log"
