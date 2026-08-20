#!/bin/bash
# ============================================================================
# Phase 8A: Gate-Level Functional Simulation Script
# ============================================================================
# Runs functional gate-level simulation using VCS with the synthesized netlist
# and behavioral sensor model.
#
# Phase: 8A - Gate-level functional verification
# Date: 2026-08-20
# ============================================================================

set -e

# =========================================================================
# Configuration
# =========================================================================
# Use absolute paths from current script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTROLLER_ROOT="${SCRIPT_DIR}/../../.."
NETLIST_DIR="${CONTROLLER_ROOT}/synthesis/netlist"
TB_DIR="${CONTROLLER_ROOT}/tb"
GATE_NETLIST="${NETLIST_DIR}/ftc_cal_controller_top_synth.v"
SENSOR_MODEL="${TB_DIR}/ftc_sensor_behavior_model.sv"
TESTBENCH="${SCRIPT_DIR}/tb_gate_level_functional.sv"

# Standard cell library for simulation
SMIC_LIB="/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/verilog/sc9mc_logic0040ll_base_rvt_c40.v"

# Output directory
OUTPUT_DIR="./sim_output"

echo "========================================="
echo "Phase 8A: Gate-Level Functional Simulation"
echo "========================================="

# =========================================================================
# Check Files
# =========================================================================
echo ""
echo "Checking required files..."

if [ ! -f "${GATE_NETLIST}" ]; then
    echo "ERROR: Gate-level netlist not found: ${GATE_NETLIST}"
    exit 1
fi
echo "  ✓ Gate-level netlist: ${GATE_NETLIST}"

if [ ! -f "${SENSOR_MODEL}" ]; then
    echo "ERROR: Sensor model not found: ${SENSOR_MODEL}"
    exit 1
fi
echo "  ✓ Sensor model: ${SENSOR_MODEL}"

if [ ! -f "${SMIC_LIB}" ]; then
    echo "ERROR: SMIC library not found: ${SMIC_LIB}"
    exit 1
fi
echo "  ✓ SMIC library: ${SMIC_LIB}"

if [ ! -f "${TESTBENCH}" ]; then
    echo "ERROR: Testbench not found: ${TESTBENCH}"
    exit 1
fi
echo "  ✓ Testbench: ${TESTBENCH}"

# =========================================================================
# Setup
# =========================================================================
echo ""
echo "Setting up simulation..."

# Create output directory
mkdir -p ${OUTPUT_DIR}
cd ${OUTPUT_DIR}

# =========================================================================
# Compile with VCS
# =========================================================================
echo ""
echo "Compiling design with VCS..."

vlogan -sverilog \
    -full64 \
    +v2k \
    -timescale=1ns/1ps \
    +delay_mode_zero \
    ${SMIC_LIB} \
    ${GATE_NETLIST} \
    ${SENSOR_MODEL} \
    ${TESTBENCH} \
    2>&1 | tee compile.log

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo ""
    echo "ERROR: Compilation failed!"
    exit 1
fi

echo ""
echo "Elaborating design..."

vcs -full64 \
    -debug_access+all \
    +notimingcheck \
    -R \
    tb_gate_level_functional \
    +vcs+dumpvars+gate_level_functional.vcd \
    2>&1 | tee elaborate_run.log

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo ""
    echo "ERROR: Simulation failed!"
    exit 1
fi

# =========================================================================
# Results
# =========================================================================
echo ""
echo "========================================="
echo "Simulation Complete"
echo "========================================="
echo "Output directory: ${OUTPUT_DIR}"
echo "Waveform: gate_level_functional.vcd"
echo "Logs: compile.log, elaborate_run.log"
echo ""

# Check for PASS in simulation output
if grep -q "All Tests Complete" elaborate_run.log && \
   grep -q "successfully verified" elaborate_run.log; then
    echo "✓ Phase 8A: PASS - Gate-level functional verification successful"
    echo ""
    exit 0
else
    echo "✗ Phase 8A: FAIL - Check elaborate_run.log for details"
    echo ""
    exit 1
fi
