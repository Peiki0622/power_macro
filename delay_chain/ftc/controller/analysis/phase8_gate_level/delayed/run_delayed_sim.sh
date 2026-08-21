#!/bin/bash
# ============================================================================
# Phase 8B: Delayed Gate-Level Simulation Script
# ============================================================================
# Runs timing-accurate gate-level simulation with SDF back-annotation
# to verify protocol timing requirements.
#
# Phase: 8B - Delayed gate-level verification
# Date: 2026-08-20
# ============================================================================

set -e

# =========================================================================
# Configuration
# =========================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTROLLER_ROOT="${SCRIPT_DIR}/../../.."
NETLIST_DIR="${CONTROLLER_ROOT}/synthesis/netlist"
TB_DIR="${CONTROLLER_ROOT}/tb"
GATE_NETLIST="${NETLIST_DIR}/ftc_cal_controller_top_synth.v"
SDF_FILE="${NETLIST_DIR}/ftc_cal_controller_top_synth.sdf"
SENSOR_MODEL="${TB_DIR}/ftc_sensor_behavior_model.sv"
TESTBENCH="${SCRIPT_DIR}/tb_delayed_gate_level.sv"

# Standard cell library for simulation
SMIC_LIB="/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/verilog/sc9mc_logic0040ll_base_rvt_c40.v"

# Output directory
# Keep all generated VCS databases, logs, and waveforms inside this phase's
# task-scoped evidence directory regardless of the caller's current directory.
OUTPUT_DIR="${SCRIPT_DIR}/sim_output"

echo "========================================="
echo "Phase 8B: Delayed Gate-Level Simulation"
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

if [ ! -f "${SDF_FILE}" ]; then
    echo "ERROR: SDF file not found: ${SDF_FILE}"
    echo "  Please run synthesis/scripts/generate_sdf.sh first"
    exit 1
fi
echo "  ✓ SDF file: ${SDF_FILE}"
echo "    Size: $(ls -lh ${SDF_FILE} | awk '{print $5}')"

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

# =========================================================================
# Elaborate and Run with SDF Back-Annotation
# =========================================================================
echo ""
echo "Elaborating and running simulation with SDF..."
echo "Note: This enables timing checks and cell delays"

vcs -full64 \
    -debug_access+all \
    -R \
    tb_delayed_gate_level \
    +sdf_verbose \
    +vcs+dumpvars+delayed_gate_level.vcd \
    -sdf max:tb_delayed_gate_level.dut:${SDF_FILE} \
    2>&1 | tee elaborate_run.log

SIM_EXIT_CODE=${PIPESTATUS[0]}

# =========================================================================
# Results
# =========================================================================
echo ""
echo "========================================="
echo "Simulation Complete"
echo "========================================="
echo "Output directory: ${OUTPUT_DIR}"
echo "Waveform: delayed_gate_level.vcd"
echo "Logs: compile.log, elaborate_run.log"
echo ""

# Check for PASS in simulation output
if [ ${SIM_EXIT_CODE} -eq 0 ]; then
    if grep -q "PHASE8B_ALL_PASS" elaborate_run.log && \
       ! grep -q "PHASE8B_FAIL" elaborate_run.log; then
        echo "✓ Phase 8B: PASS - Delayed gate-level verification successful"
        echo ""

        # Extract key metrics
        echo "Key Metrics:"
        grep "Total S_CLK edges:" elaborate_run.log || true
        grep "Protocol violations:" elaborate_run.log || true
        grep "Final configuration:" elaborate_run.log || true
        echo ""

        exit 0
    fi
fi

echo "✗ Phase 8B: FAIL - Check elaborate_run.log for details"
echo ""

# Show last few lines for quick diagnosis
echo "Last 20 lines of simulation output:"
tail -20 elaborate_run.log

exit 1
