#!/usr/bin/env bash
# Run all focused M1 RTL tests in a task-owned directory.
#
# VCS temporary databases, executables, compile logs, and run logs are created
# below verification/rtl/run only.  The script never invokes HSPICE, XA, or a
# startup-calibration regression; H0 is compiled solely as a read-only child
# for the M1 manager/handoff protocol check.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
M1_ROOT=$(cd "${SCRIPT_DIR}/../.." && pwd)
REPO_ROOT=$(cd "${M1_ROOT}/../../../.." && pwd)
RTL_ROOT="${REPO_ROOT}/delay_chain/ftc/controller/rtl"
ASSERTION_ROOT="${M1_ROOT}/assertions"
RUN_PARENT="${SCRIPT_DIR}/run"
# A caller may provide a deterministic run label for a reproduced result.  The
# default UTC label preserves prior task-owned evidence instead of deleting or
# overwriting another engineer's regression directory.
RUN_ID="${M1_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_ROOT="${RUN_PARENT}/${RUN_ID}"

run_vcs_case() {
    local case_name=$1
    shift
    local case_root="${RUN_ROOT}/${case_name}"
    mkdir -p "${case_root}"
    (
        cd "${case_root}"
        vcs -full64 -sverilog -timescale=1ns/1ps -assert svaext \
            -Mdir="${case_root}/csrc" -o "${case_root}/simv" \
            "$@" -l "${case_root}/compile.log"
        "${case_root}/simv" -l "${case_root}/run.log"
        # Some simulators report a testbench $fatal as a completed simulation
        # process.  Treat every testbench/SVA failure marker as a shell error
        # so the evidence summary can never label a failing regression PASS.
        if rg -q '(^FAIL |M1 SVA:|integration FAIL|mapper unit FAIL|Fatal:)' "${case_root}/run.log"; then
            printf 'M1 RTL case %s failed; inspect %s\n' "${case_name}" "${case_root}/run.log" >&2
            exit 1
        fi
    )
}

mkdir -p "${RUN_ROOT}"

run_vcs_case mapper \
    "${RTL_ROOT}/ftc_detection_margin_mapper.sv" \
    "${SCRIPT_DIR}/tb_ftc_detection_margin_mapper.sv"

run_vcs_case manager \
    "${RTL_ROOT}/ftc_detection_margin_mapper.sv" \
    "${RTL_ROOT}/ftc_detection_margin_manager.sv" \
    "${RTL_ROOT}/ftc_sensor_owner_handoff.sv" \
    "${ASSERTION_ROOT}/ftc_detection_margin_manager_sva.sv" \
    "${SCRIPT_DIR}/tb_ftc_detection_margin_manager.sv"

run_vcs_case top \
    "${RTL_ROOT}/ftc_cal_pkg.sv" \
    "${RTL_ROOT}/ftc_cfg_therm_regs.sv" \
    "${RTL_ROOT}/ftc_operation_sequencer.sv" \
    "${RTL_ROOT}/ftc_q_sampler.sv" \
    "${RTL_ROOT}/ftc_cal_fsm.sv" \
    "${RTL_ROOT}/ftc_cal_controller_top.sv" \
    "${RTL_ROOT}/ftc_sensor_owner_handoff.sv" \
    "${RTL_ROOT}/ftc_cal_detect_handoff_top.sv" \
    "${RTL_ROOT}/ftc_detection_margin_mapper.sv" \
    "${RTL_ROOT}/ftc_detection_margin_manager.sv" \
    "${RTL_ROOT}/ftc_cal_detect_margin_top.sv" \
    "${SCRIPT_DIR}/tb_ftc_cal_detect_margin_top.sv"

printf 'M1 RTL regression PASS\n' | tee "${RUN_ROOT}/summary.txt"
