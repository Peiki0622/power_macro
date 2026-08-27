# B-FE5 RTL2 detector mapping and frozen-capture preservation gate.
# All reports, mapped netlist, DDC, and SDC remain inside backend/rtl2.
set SCRIPT_DIR [file dirname [file normalize [info script]]]
set BACKEND_ROOT [file normalize [file join $SCRIPT_DIR ..]]
set REPO_ROOT [file normalize [file join $BACKEND_ROOT ../../..]]
set RTL_ROOT "$REPO_ROOT/delay_chain/ftc/rtl"
set REPORT_DIR "$BACKEND_ROOT/reports/rtl2"
set NETLIST_DIR "$BACKEND_ROOT/netlist/rtl2"
set WORK_DIR "$BACKEND_ROOT/work/rtl2"
set LIB_BASE "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1"
set TARGET_LIBRARY "$LIB_BASE/db/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db"
file mkdir $REPORT_DIR; file mkdir $NETLIST_DIR; file mkdir $WORK_DIR
set_app_var sh_enable_page_mode false
set_app_var compile_delete_unloaded_sequential_cells false
set_app_var compile_seqmap_propagate_constants false
set_app_var target_library $TARGET_LIBRARY
set_app_var link_library "* $TARGET_LIBRARY"
set search_path [concat $search_path "$LIB_BASE/db"]
define_design_lib WORK -path $WORK_DIR
foreach rtl_file [list \
    "$RTL_ROOT/ftc_capture_struct.sv" "$RTL_ROOT/bfe_capture_bank.sv" \
    "$RTL_ROOT/bfe_m_feature.sv" "$RTL_ROOT/bfe_backend_ctrl.sv" \
    "$RTL_ROOT/bfe_backend_top.sv"] {
    analyze -format sverilog -work WORK $rtl_file
}
elaborate bfe_backend_top -work WORK
current_design bfe_backend_top
redirect -file "$REPORT_DIR/check_design_precompile.rpt" { check_design }
link

# Protect only the physical capture bank and its 60 selected sequential cells.
set capture_hier [get_cells u_capture_bank]
set_ungroup $capture_hier false
set_boundary_optimization $capture_hier false
set latq_cells [get_cells -hierarchical -filter "ref_name == LATQ_X0P5M_A9TR40"]
set dff_cells  [get_cells -hierarchical -filter "ref_name == DFFRPQ_X0P5M_A9TR40"]
set_dont_touch $latq_cells; set_dont_touch $dff_cells
create_clock -name clk_probe -period 2.5 [get_ports clk_probe]
set_clock_uncertainty -setup 0.05 [get_clocks clk_probe]
set_clock_uncertainty -hold 0.02 [get_clocks clk_probe]
set_clock_transition 0.05 [get_clocks clk_probe]
set_false_path -from [get_ports reset] -to [all_registers]

# Ordinary compile is used for both arithmetic/control children.  Their DW
# add/sub wrappers are retained only when composed of mapped library cells;
# no compile_ultra, multiplier, divider, or custom datapath macro is used.
current_design bfe_m_feature; compile -map_effort high -area_effort high
current_design bfe_backend_ctrl; compile -map_effort high -area_effort high
current_design bfe_backend_top; link; compile -map_effort high -area_effort high
redirect -file "$REPORT_DIR/check_design_postcompile.rpt" { check_design }
redirect -file "$REPORT_DIR/report_reference.rpt" { report_reference -hierarchy }
redirect -file "$REPORT_DIR/report_cell.rpt" { report_cell }
redirect -file "$REPORT_DIR/report_resources.rpt" { report_resources }
redirect -file "$REPORT_DIR/report_area.rpt" { report_area -hierarchy -nosplit }
redirect -file "$REPORT_DIR/report_qor.rpt" { report_qor }
redirect -file "$REPORT_DIR/report_timing.rpt" { report_timing -path full -delay max -max_paths 30 -nworst 1 }
set latq_count [sizeof_collection [get_cells -hierarchical -filter "ref_name == LATQ_X0P5M_A9TR40"]]
set dff_count  [sizeof_collection [get_cells -hierarchical -filter "ref_name == DFFRPQ_X0P5M_A9TR40"]]
if {$latq_count != 30 || $dff_count != 30} { echo "RTL2_FATAL: LATQ=$latq_count DFF=$dff_count"; exit 1 }
set direct_pass 1; set direct_lines {}
foreach_in_collection latq $latq_cells {
    set q_pin [get_pins -of_objects $latq -filter "pin_name == Q"]
    set q_net [get_nets -of_objects $q_pin]
    set matching_dff [get_cells -of_objects [get_pins -of_objects $q_net -filter "pin_name == D"] -hierarchical -filter "ref_name == DFFRPQ_X0P5M_A9TR40"]
    if {[sizeof_collection $matching_dff] != 1} { set direct_pass 0 }
    lappend direct_lines "LATQ=[get_object_name $latq] Q_NET=[get_object_name $q_net] DFF_MATCH=[sizeof_collection $matching_dff]"
}
if {!$direct_pass} { echo "RTL2_FATAL: capture direct-connect check failed"; exit 1 }
redirect -file "$REPORT_DIR/structure_summary.rpt" {
    puts "gate=BFE5_RTL2_MINIMAL_DETECTOR_PASS"
    puts "LATQ_COUNT=$latq_count"; puts "DFF_COUNT=$dff_count"
    puts "DIRECT_CONNECT=PASS"; puts "M_FF_WIDTH=9"; puts "REFERENCE_WIDTH=9"
    puts "MARGIN_WIDTH=9"; puts "MULTIPLIER_DIVIDER=NONE_EXPECTED"
    foreach line $direct_lines { puts $line }
}
write -format verilog -hierarchy -output "$NETLIST_DIR/bfe_backend_rtl2_mapped.v"
write -format ddc -hierarchy -output "$NETLIST_DIR/bfe_backend_rtl2_mapped.ddc"
write_sdc "$NETLIST_DIR/bfe_backend_rtl2_mapped.sdc"
puts "BFE5_RTL2_MINIMAL_DETECTOR_PASS"
exit
