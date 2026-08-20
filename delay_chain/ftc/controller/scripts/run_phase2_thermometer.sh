#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
TAG=${1:-phase2_therm_$(date -u +%Y%m%dT%H%M%SZ)}
RUN_DIR="${ROOT}/analysis/phase2/${TAG}"
mkdir -p "${RUN_DIR}"
VCS_BIN=${VCS_BIN:-/home/synopsys/vcs/W-2024.09/bin/vcs}
"${VCS_BIN}" -full64 -sverilog -timescale=1ns/1ps \
  -top tb_ftc_cfg_therm_regs \
  -o "${RUN_DIR}/simv" \
  "${ROOT}/rtl/ftc_cfg_therm_regs.sv" \
  "${ROOT}/tb/tb_ftc_cfg_therm_regs.sv" \
  >"${RUN_DIR}/compile.log" 2>&1
"${RUN_DIR}/simv" >"${RUN_DIR}/simulation.log" 2>&1
grep -q THERMOMETER_UNIT_PASS "${RUN_DIR}/simulation.log"
printf '{\n  "decision": "Thermometer Configuration Block = GO",\n  "run_dir": "%s"\n}\n' "${RUN_DIR}" >"${RUN_DIR}/results.json"
printf '# Phase 2 Thermometer Configuration\n\n- Decision: `Thermometer Configuration Block = GO`\n- Run directory: `%s`\n' "${RUN_DIR}" >"${RUN_DIR}/report.md"
