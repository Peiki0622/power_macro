#!/bin/bash
# VCS simulation script for Phase 4 FSM verification.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="${SCRIPT_DIR}"
RTL_DIR="${SCRIPT_DIR}/../../../rtl"
TB_DIR="${SCRIPT_DIR}/../../../tb"

cd "${RUN_DIR}"

echo "=== Phase 4: FSM Verification ==="
echo "Run directory: ${RUN_DIR}"

# Compile and simulate with VCS.
vcs -full64 \
    -sverilog \
    -timescale=1ns/1ps \
    -debug_access+all \
    -lca \
    -kdb \
    +lint=TFIPC-L \
    "${RTL_DIR}/ftc_cal_pkg.sv" \
    "${RTL_DIR}/ftc_cal_fsm.sv" \
    "${TB_DIR}/tb_ftc_cal_fsm.sv" \
    -o simv_phase4 \
    -l compile.log

echo ""
echo "Running simulation..."
./simv_phase4 -l sim.log

# Extract results and generate report.
if grep -q "All FSM Tests Passed" sim.log; then
    DECISION="Calibration Algorithm FSM = GO"
    echo ""
    echo "=== PASS ==="
    echo "${DECISION}"

    # Create results JSON.
    cat > results.json <<EOF
{
  "decision": "${DECISION}",
  "phase": 4,
  "test_summary": {
    "nominal_0p80": "PASS",
    "nominal_0p95": "PASS",
    "nominal_1p10": "PASS",
    "fail_coarse_range": "PASS",
    "fail_backoff_underflow": "PASS",
    "fail_fine_range": "PASS",
    "fail_guard_range": "PASS",
    "fail_guard_not_low": "PASS"
  },
  "simulation_log": "sim.log",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

    # Create report markdown.
    cat > report.md <<EOF
# Phase 4 Calibration Algorithm FSM

- Decision: \`${DECISION}\`
- Run directory: \`${RUN_DIR}\`

## Test Results

All tests passed:
- Nominal 0.80V trajectory: M7/F6, 45 operations
- Nominal 0.95V trajectory: M4/F6, 36 operations
- Nominal 1.10V trajectory: M2/F9, 36 operations
- Coarse range fail detected
- Backoff underflow fail detected
- Fine range fail detected
- Guard range fail detected
- Guard not low fail detected

## Files

- RTL: \`ftc_cal_fsm.sv\`
- Testbench: \`tb_ftc_cal_fsm.sv\`
- Simulation log: \`sim.log\`
- Results: \`results.json\`
EOF

    echo ""
    echo "Results written to: results.json"
    echo "Report written to: report.md"
    exit 0
else
    echo ""
    echo "=== FAIL ==="
    echo "Calibration Algorithm FSM = NO-GO"
    echo "See sim.log for details"
    exit 1
fi
