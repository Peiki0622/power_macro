#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
TAG=${1:-phase3_seq_$(date -u +%Y%m%dT%H%M%SZ)}
RUN_DIR="${ROOT}/analysis/phase3/${TAG}"
mkdir -p "${RUN_DIR}"
VCS_BIN=${VCS_BIN:-/home/synopsys/vcs/W-2024.09/bin/vcs}
"${VCS_BIN}" -full64 -sverilog -timescale=1ns/1ps -top tb_ftc_operation_sequencer \
  -o "${RUN_DIR}/simv" "${ROOT}/rtl/ftc_cal_pkg.sv" \
  "${ROOT}/rtl/ftc_q_sampler.sv" "${ROOT}/rtl/ftc_operation_sequencer.sv" \
  "${ROOT}/tb/tb_ftc_operation_sequencer.sv" >"${RUN_DIR}/compile.log" 2>&1
"${RUN_DIR}/simv" >"${RUN_DIR}/simulation.log" 2>&1
grep -q SEQUENCER_UNIT_PASS "${RUN_DIR}/simulation.log"
printf '{\n  "decision": "Operation Sequencer = GO",\n  "run_dir": "%s",\n  "hspice_runs": 0\n}\n' "${RUN_DIR}" >"${RUN_DIR}/results.json"
printf '# Phase 3 Operation Sequencer\n\n- Decision: `Operation Sequencer = GO`\n- Run directory: `%s`\n' "${RUN_DIR}" >"${RUN_DIR}/report.md"
