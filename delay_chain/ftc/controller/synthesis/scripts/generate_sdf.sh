#!/bin/bash
# ============================================================================
# Generate SDF (Standard Delay Format) file from synthesized netlist
# ============================================================================
# This script uses Design Compiler to write out SDF with actual cell delays
# for timing-accurate gate-level simulation.
#
# Phase: 8B - Delayed gate-level simulation preparation
# Date: 2026-08-20
# ============================================================================

set -e

echo "========================================="
echo "Generating SDF File for Gate-Level Simulation"
echo "========================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NETLIST_DIR="${SCRIPT_DIR}/../netlist"
REPORTS_DIR="${SCRIPT_DIR}/../reports"

# Check if netlist exists
if [ ! -f "${NETLIST_DIR}/ftc_cal_controller_top_synth.v" ]; then
    echo "ERROR: Synthesized netlist not found!"
    exit 1
fi

echo ""
echo "Creating SDF generation TCL script..."

cat > generate_sdf.tcl << 'EOF'
# =========================================================================
# SDF Generation Script
# =========================================================================
set DESIGN_NAME "ftc_cal_controller_top"
set LIB_PATH "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1"

# =========================================================================
# Setup
# =========================================================================
set target_library "${LIB_PATH}/db/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db"
set link_library "* $target_library"

# Suppress messages
set_app_var sh_enable_page_mode false

# =========================================================================
# Read Netlist and SDC
# =========================================================================
puts "Reading synthesized netlist..."
read_verilog ../netlist/${DESIGN_NAME}_synth.v
current_design ${DESIGN_NAME}
link

puts "Reading SDC constraints..."
read_sdc ../netlist/${DESIGN_NAME}_synth.sdc

# =========================================================================
# Generate SDF
# =========================================================================
puts "Writing SDF file..."
write_sdf -version 3.0 \
          -context verilog \
          -load_delay net \
          ../netlist/${DESIGN_NAME}_synth.sdf

puts "SDF generation complete!"
puts "Output: ../netlist/${DESIGN_NAME}_synth.sdf"

exit
EOF

echo ""
echo "Running Design Compiler to generate SDF..."
cd "${SCRIPT_DIR}"

dc_shell -f generate_sdf.tcl 2>&1 | tee sdf_generation.log

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo ""
    echo "ERROR: SDF generation failed!"
    exit 1
fi

echo ""
echo "========================================="
echo "SDF Generation Complete"
echo "========================================="

if [ -f "${NETLIST_DIR}/ftc_cal_controller_top_synth.sdf" ]; then
    ls -lh "${NETLIST_DIR}/ftc_cal_controller_top_synth.sdf"
    echo ""
    echo "✓ SDF file successfully generated"
    echo ""
else
    echo "ERROR: SDF file not found after generation"
    exit 1
fi

# Move log to reports
mv sdf_generation.log "${REPORTS_DIR}/"
echo "Log saved to: ${REPORTS_DIR}/sdf_generation.log"
