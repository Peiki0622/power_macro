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
