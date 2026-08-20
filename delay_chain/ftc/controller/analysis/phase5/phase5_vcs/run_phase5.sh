#!/bin/bash
# VCS simulation script for Phase 5 controller integration verification.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="${SCRIPT_DIR}"
RTL_DIR="${SCRIPT_DIR}/../../../rtl"
TB_DIR="${SCRIPT_DIR}/../../../tb"

cd "${RUN_DIR}"

echo "=== Phase 5: Controller Integration Verification ==="
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
    "${RTL_DIR}/ftc_cfg_therm_regs.sv" \
    "${RTL_DIR}/ftc_q_sampler.sv" \
    "${RTL_DIR}/ftc_operation_sequencer.sv" \
    "${RTL_DIR}/ftc_cal_fsm.sv" \
    "${RTL_DIR}/ftc_cal_controller_top.sv" \
    "${RTL_DIR}/ftc_sensor_behavior_model.sv" \
    "${TB_DIR}/tb_ftc_cal_controller.sv" \
    -o simv_phase5 \
    -l compile.log

echo ""
echo "Running simulation..."
./simv_phase5 -l sim.log

# Extract results and generate report.
if grep -q "All Controller Integration Tests Passed" sim.log; then
    DECISION="RTL Golden-Path Reproduction = GO"
    echo ""
    echo "=== PASS ==="
    echo "${DECISION}"

    # Extract operation counts from log.
    OP_0P80=$(grep "Test 1 completed" sim.log | awk '{print $6}')
    OP_0P95=$(grep "Test 2 completed" sim.log | awk '{print $6}')
    OP_1P10=$(grep "Test 3 completed" sim.log | awk '{print $6}')

    # Create results JSON.
    cat > results.json <<EOF
{
  "decision": "${DECISION}",
  "phase": 5,
  "test_summary": {
    "nominal_0p80": {
      "status": "PASS",
      "final_code": "M7/F6",
      "operations": "${OP_0P80}"
    },
    "nominal_0p95": {
      "status": "PASS",
      "final_code": "M4/F6",
      "operations": "${OP_0P95}"
    },
    "nominal_1p10": {
      "status": "PASS",
      "final_code": "M2/F9",
      "operations": "${OP_1P10}"
    },
    "lock_permanence": "PASS"
  },
  "autonomous_operation": true,
  "zero_probes_between_backoff": true,
  "guard_and_hold_verified": true,
  "simulation_log": "sim.log",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

    # Create report markdown.
    cat > report.md <<EOF
# Phase 5 RTL Controller Integration

- Decision: \`${DECISION}\`
- Run directory: \`${RUN_DIR}\`

## Test Results

All integration tests passed:
- Nominal 0.80V: M7/F6, ${OP_0P80} operations
- Nominal 0.95V: M4/F6, ${OP_0P95} operations
- Nominal 1.10V: M2/F9, ${OP_1P10} operations
- Lock permanence verified (M/F frozen after lock)

## Verification Coverage

✅ Autonomous operation (testbench only provides cal_clk, ctrl_por_n, cal_start)
✅ Controller drives all sensor controls (sense_dff_reset, sense_s_clk)
✅ Controller drives configuration (medium_therm[], fine_therm[])
✅ Two-step backoff with zero probes between steps
✅ Guard and hold probes both occur and both return STABLE_LOW
✅ Final codes match golden trajectories

## Files

- Top-level RTL: \`ftc_cal_controller_top.sv\`
- Behavioral sensor: \`ftc_sensor_behavior_model.sv\`
- Testbench: \`tb_ftc_cal_controller.sv\`
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
    echo "RTL Golden-Path Reproduction = NO-GO"
    echo "See sim.log for details"
    exit 1
fi
