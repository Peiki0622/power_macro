#!/usr/bin/env bash
set -euo pipefail

# Keep every generated input, compiler work library, executable, simulator log,
# and optional waveform under one task-scoped run directory.  Source RTL,
# testbench code, and generation scripts remain outside the ignored run tree.
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CNN_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
POWER_MACRO_ROOT=$(cd "${CNN_ROOT}/../.." && pwd)
WORKSPACE_ROOT=$(cd "${POWER_MACRO_ROOT}/.." && pwd)
RUN_TAG=${1:-vcs_full_20260801_r1}
RUN_DIR="${CNN_ROOT}/runs/${RUN_TAG}"
PYTHON_BIN=${PYTHON_BIN:-/home/zhupl25/miniconda3/envs/DL/bin/python}
VCS_BIN=${VCS_BIN:-/home/synopsys/vcs/W-2024.09/bin/vcs}
ROM_MODEL=${ROM_MODEL:-${CNN_ROOT}/runs/stage89_20260801_r1/rom_compiler/output/CNNW384X128.v}
ROM_RCF=${ROM_RCF:-$(dirname "${ROM_MODEL}")/CNNW384X128_verilog.rcf}

# Full RTL regression must use the delivered compiler model.  Refuse to fall
# back to a behavioral array or source-level case ROM when the authenticated
# model path is absent; such a fallback would no longer verify macro timing and
# control integration.
if [[ ! -f "${ROM_MODEL}" ]]; then
    echo "ERROR: compiler ROM model not found: ${ROM_MODEL}" >&2
    exit 2
fi
if [[ ! -f "${ROM_RCF}" ]]; then
    echo "ERROR: compiler ROM content not found: ${ROM_RCF}" >&2
    exit 2
fi

mkdir -p "${RUN_DIR}/generated" "${RUN_DIR}/csrc"
# The delivered model opens its RCF by basename at runtime.  Local copies keep
# that relative lookup inside the task-scoped run and bind the exact model and
# content used by the executable to the archived evidence directory.
cp "${ROM_MODEL}" "${RUN_DIR}/CNNW384X128.v"
cp "${ROM_RCF}" "${RUN_DIR}/CNNW384X128_verilog.rcf"
PYTHONPATH="${WORKSPACE_ROOT}" "${PYTHON_BIN}" \
    "${CNN_ROOT}/scripts/generate_verification_data.py" \
    --config "${CNN_ROOT}/config/cnn_rtl_config_v1.json" \
    --output-directory "${RUN_DIR}/generated"

cd "${RUN_DIR}"
"${VCS_BIN}" -full64 -sverilog -timescale=1ns/1ps \
    -DARM_UD_MODEL -DCNN_ROM_COMPILER_MODEL +notimingcheck \
    -top cnn_monitor_tb \
    "${RUN_DIR}/CNNW384X128.v" \
    "${CNN_ROOT}/rtl/generated/cnn_parameter_roms.sv" \
    "${CNN_ROOT}/rtl/cnn_requantize_relu.sv" \
    "${CNN_ROOT}/rtl/cnn_weight_rom.sv" \
    "${CNN_ROOT}/rtl/cnn_window_buffer.sv" \
    "${CNN_ROOT}/rtl/cnn_convolution_engine.sv" \
    "${CNN_ROOT}/rtl/cnn_pool_classifier.sv" \
    "${CNN_ROOT}/rtl/cnn_monitor.sv" \
    "${CNN_ROOT}/tb/cnn_monitor_tb.sv" \
    -Mdir="${RUN_DIR}/csrc" -o "${RUN_DIR}/simv" \
    -l "${RUN_DIR}/compile.log"

"${RUN_DIR}/simv" \
    +notimingcheck \
    +VECTORS="${RUN_DIR}/generated/vectors.txt" \
    +TENSORS="${RUN_DIR}/generated/internal_tensors.txt" \
    +TRACE="${RUN_DIR}/generated/cycle_trace.txt" \
    +SPECIAL="${RUN_DIR}/generated/special_expected.txt" \
    -l "${RUN_DIR}/simulation.log"
