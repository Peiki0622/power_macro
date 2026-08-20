# ============================================================================
# FTC Calibration Controller - Simplified DC Synthesis Script
# ============================================================================
# Technology: SMIC 40LL RVT
# Target: 1 GHz control clock (1.0 ns period)
# ============================================================================

# =========================================================================
# Basic Setup
# =========================================================================
set DESIGN_NAME "ftc_cal_controller_top"

# Technology library - SMIC 40LL RVT worst corner
set target_library "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/db/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db"
set link_library "* $target_library"

# =========================================================================
# Read RTL
# =========================================================================
puts "Reading RTL files..."

# Read all RTL files one by one
read_file -format sverilog ../../rtl/ftc_cal_pkg.sv
read_file -format sverilog ../../rtl/ftc_cfg_therm_regs.sv
read_file -format sverilog ../../rtl/ftc_q_sampler.sv
read_file -format sverilog ../../rtl/ftc_operation_sequencer.sv
read_file -format sverilog ../../rtl/ftc_cal_fsm.sv
read_file -format sverilog ../../rtl/ftc_cal_controller_top.sv

# Set current design
current_design ${DESIGN_NAME}

# Link
link

# Check design
check_design

# =========================================================================
# Apply Basic Constraints
# =========================================================================
puts "Applying constraints..."

# Create clock
create_clock -name cal_clk -period 1.0 [get_ports cal_clk]
set_clock_uncertainty 0.05 [get_clocks cal_clk]

# Input delays
set_input_delay -clock cal_clk -max 0.7 [get_ports cal_start]
set_input_delay -clock cal_clk -max 0.6 [get_ports q_final]

# Output delays
set_output_delay -clock cal_clk -max 0.4 [all_outputs]

# False paths
set_false_path -from [get_ports ctrl_por_n]

# Design rules
set_max_fanout 16 [current_design]

# =========================================================================
# Compile
# =========================================================================
puts "Compiling..."

compile_ultra

# =========================================================================
# Reports
# =========================================================================
puts "Generating reports..."

file mkdir ../reports

report_timing -max_paths 5 > ../reports/timing.rpt
report_area -hierarchy > ../reports/area.rpt
report_qor > ../reports/qor.rpt
report_power > ../reports/power.rpt

# =========================================================================
# Write Netlist
# =========================================================================
puts "Writing netlist..."

file mkdir ../netlist

write -format verilog -hierarchy -output ../netlist/${DESIGN_NAME}_synth.v
write_sdc ../netlist/${DESIGN_NAME}_synth.sdc

puts "Synthesis complete!"

exit
