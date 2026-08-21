# ============================================================================
# FTC Calibration Controller - Design Compiler Synthesis Script
# ============================================================================
# Technology: SMIC 40LL RVT
# Target: 1 GHz control clock (1.0 ns period)
#
# Usage: dc_shell-xg-t -f synthesize_dc.tcl
#
# Phase: 7 - Controller synthesis
# Date: 2026-08-20
# ============================================================================

# =========================================================================
# Setup Variables
# =========================================================================
set DESIGN_NAME "ftc_cal_controller_top"
set RTL_DIR "../../rtl"
set CONSTRAINT_FILE "../constraints/ftc_controller_timing.sdc"
set OUTPUT_DIR "../netlist"
set REPORT_DIR "../reports"

# Technology library paths - SMIC 40LL RVT
set LIB_BASE "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1"

# Use worst-case corner for setup timing (slow corner)
set TARGET_LIBRARY "${LIB_BASE}/db/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db"
set LINK_LIBRARY "* ${TARGET_LIBRARY}"

# DC consumes these as application variables.  Keeping only a Tcl variable
# leaves the default placeholder library active and makes every RTL analyze
# appear unlinked even when the technology database exists.
set_app_var target_library ${TARGET_LIBRARY}
set_app_var link_library ${LINK_LIBRARY}

# Symbol library for schematic view
set SYMBOL_LIBRARY "${LIB_BASE}/slib/sc9mc_logic0040ll_base_rvt_c40.sdb"

# =========================================================================
# Setup Search Path
# =========================================================================
set search_path [concat $search_path ${LIB_BASE}/db]

# =========================================================================
# Setup App Variables
# =========================================================================
# Suppress specific warnings
set_app_var sh_enable_page_mode false
set_app_var compile_delete_unloaded_sequential_cells false
set_app_var compile_seqmap_propagate_constants false

# Enable SystemVerilog support
set_app_var enable_recovery_removal_arcs true
set_app_var hdlin_enable_hier_map true

# =========================================================================
# Read RTL Files
# =========================================================================
puts "\n========================================="
puts "Reading RTL files..."
puts "=========================================\n"

# Set SystemVerilog mode
set_app_var hdlin_language_extensions SystemVerilog

# Define work library
define_design_lib WORK -path ./work

# Read package first
analyze -format sverilog -work WORK ${RTL_DIR}/ftc_cal_pkg.sv
puts "Analyzed package ftc_cal_pkg.sv"

# Read RTL modules in dependency order
set rtl_files [list \
    "${RTL_DIR}/ftc_cfg_therm_regs.sv" \
    "${RTL_DIR}/ftc_q_sampler.sv" \
    "${RTL_DIR}/ftc_operation_sequencer.sv" \
    "${RTL_DIR}/ftc_cal_fsm.sv" \
    "${RTL_DIR}/ftc_cal_controller_top.sv" \
]

foreach file $rtl_files {
    puts "Analyzing: $file"
    analyze -format sverilog -work WORK $file
}

# Elaborate design
puts "\n========================================="
puts "Elaborating design: ${DESIGN_NAME}"
puts "=========================================\n"

elaborate ${DESIGN_NAME} -work WORK
if { [llength [get_designs ${DESIGN_NAME}]] == 0 } {
    puts "ERROR: Failed to elaborate ${DESIGN_NAME}"
    exit 1
}

# Set current design
current_design ${DESIGN_NAME}

# Link design
puts "\n========================================="
puts "Linking design..."
puts "=========================================\n"

link
puts "Link completed with target library ${TARGET_LIBRARY}"

# =========================================================================
# Check Design
# =========================================================================
puts "\n========================================="
puts "Checking design..."
puts "=========================================\n"

check_design > ${REPORT_DIR}/check_design.rpt
redirect -tee ${REPORT_DIR}/check_design.rpt { check_design }

# =========================================================================
# Apply Constraints
# =========================================================================
puts "\n========================================="
puts "Applying timing constraints..."
puts "=========================================\n"

source ${CONSTRAINT_FILE}

# Additional synthesis constraints
set_fix_multiple_port_nets -all -buffer_constants [get_designs]

# Set operating conditions (worst case for setup)
set_operating_conditions -max ss_typical_max_0p99v_125c

# Set wire load model (if needed)
# set_wire_load_mode top

# =========================================================================
# Compile Design
# =========================================================================
puts "\n========================================="
puts "Compiling design..."
puts "=========================================\n"

# Initial compile with ultra optimization
# Keep the registered sensor S_CLK implementation intact.  The gate-clock
# optimization requires a verification-top setup and is not needed for this
# design; removing it prevents DC from aborting before standard-cell mapping.
set_verification_top ${DESIGN_NAME}
compile -map_effort high -area_effort high

# =========================================================================
# Generate Reports
# =========================================================================
puts "\n========================================="
puts "Generating reports..."
puts "=========================================\n"

# Timing reports
redirect -tee ${REPORT_DIR}/timing_setup.rpt { report_timing -path full -delay max -max_paths 10 -nworst 1 }
redirect -tee ${REPORT_DIR}/timing_hold.rpt { report_timing -path full -delay min -max_paths 10 -nworst 1 }
redirect -tee ${REPORT_DIR}/constraints.rpt { report_constraint -all_violators }
redirect -tee ${REPORT_DIR}/clock.rpt { report_clock -skew -attribute }

# Area reports
redirect -tee ${REPORT_DIR}/area.rpt { report_area -hierarchy -nosplit }
redirect -tee ${REPORT_DIR}/cell.rpt { report_cell }
redirect -tee ${REPORT_DIR}/reference.rpt { report_reference -hierarchy }

# Power report
redirect -tee ${REPORT_DIR}/power.rpt { report_power -analysis_effort high }

# Quality of results
redirect -tee ${REPORT_DIR}/qor.rpt { report_qor }
redirect -tee ${REPORT_DIR}/qor_summary.rpt { report_qor }

# Design statistics
redirect -tee ${REPORT_DIR}/design.rpt { report_design }

# Port report
redirect -tee ${REPORT_DIR}/port.rpt { report_port -verbose }

# =========================================================================
# Write Netlist
# =========================================================================
puts "\n========================================="
puts "Writing netlist..."
puts "=========================================\n"

# Create output directory if it doesn't exist
file mkdir ${OUTPUT_DIR}

# Verilog netlist
write -format verilog -hierarchy -output ${OUTPUT_DIR}/${DESIGN_NAME}_synth.v
puts "Wrote: ${OUTPUT_DIR}/${DESIGN_NAME}_synth.v"

# DDC format (for further analysis)
write -format ddc -hierarchy -output ${OUTPUT_DIR}/${DESIGN_NAME}_synth.ddc
puts "Wrote: ${OUTPUT_DIR}/${DESIGN_NAME}_synth.ddc"

# SDC constraints (propagated)
write_sdc ${OUTPUT_DIR}/${DESIGN_NAME}_synth.sdc
puts "Wrote: ${OUTPUT_DIR}/${DESIGN_NAME}_synth.sdc"

# =========================================================================
# Summary
# =========================================================================
puts "\n========================================="
puts "Synthesis Complete!"
puts "=========================================\n"
puts "Design: ${DESIGN_NAME}"
puts "Technology: SMIC 40LL RVT"
puts "Target Clock: 1.0 ns (1 GHz)"
puts ""
puts "Outputs:"
puts "  Netlist: ${OUTPUT_DIR}/${DESIGN_NAME}_synth.v"
puts "  Reports: ${REPORT_DIR}/"
puts ""

# Display QoR summary
puts "Quality of Results:"
report_qor

exit
