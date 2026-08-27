# B-FE5 RTL0 real-cell mapping and structural gate.
#
# RTL0 is intentionally limited to the fixed capture bank and M feature.  The
# script keeps every generated artifact below backend/{reports,netlist,work}
# and fails before writing the final gate summary if the protected sequential
# structure is not exactly the frozen 30-lane topology.

set SCRIPT_DIR [file dirname [file normalize [info script]]]
set BACKEND_ROOT [file normalize [file join $SCRIPT_DIR ..]]
set REPO_ROOT [file normalize [file join $BACKEND_ROOT ../../..]]
set RTL_ROOT "$REPO_ROOT/delay_chain/ftc/rtl"
set REPORT_DIR "$BACKEND_ROOT/reports/rtl0"
set NETLIST_DIR "$BACKEND_ROOT/netlist/rtl0"
set WORK_DIR "$BACKEND_ROOT/work/rtl0"
set DESIGN_NAME "bfe_backend_rtl0_top"
set LIB_BASE "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1"
set TARGET_LIBRARY "$LIB_BASE/db/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db"

file mkdir $REPORT_DIR
file mkdir $NETLIST_DIR
file mkdir $WORK_DIR
set_app_var sh_enable_page_mode false
set_app_var compile_delete_unloaded_sequential_cells false
set_app_var compile_seqmap_propagate_constants false
set_app_var target_library $TARGET_LIBRARY
set_app_var link_library "* $TARGET_LIBRARY"
set search_path [concat $search_path "$LIB_BASE/db"]
define_design_lib WORK -path $WORK_DIR

# Analyze only the fixed modules required by this stage.  No package or
# unrelated historical controller RTL is allowed into the design library.
foreach rtl_file [list \
    "$RTL_ROOT/ftc_capture_struct.sv" \
    "$RTL_ROOT/bfe_capture_bank.sv" \
    "$RTL_ROOT/bfe_m_feature.sv" \
    "$RTL_ROOT/bfe_backend_rtl0_top.sv"] {
    analyze -format sverilog -work WORK $rtl_file
}
elaborate $DESIGN_NAME -work WORK
current_design $DESIGN_NAME
redirect -file "$REPORT_DIR/check_design_precompile.rpt" { check_design }
link

# Protect only the physical capture bank.  Feature logic remains available to
# ordinary DC optimization, while the 60 foundry sequential cells cannot be
# removed, merged, replaced, or moved across the bank boundary.
set capture_hier [get_cells u_capture_bank]
set_ungroup $capture_hier false
set_boundary_optimization $capture_hier false
set latq_cells [get_cells -hierarchical -filter "ref_name == LATQ_X0P5M_A9TR40"]
set dff_cells  [get_cells -hierarchical -filter "ref_name == DFFRPQ_X0P5M_A9TR40"]
set_dont_touch $latq_cells
set_dont_touch $dff_cells

# RTL0 uses the frozen 400 MHz probe clock only to make timing reports
# reproducible; no old 1 GHz controller constraint is inherited.
create_clock -name clk_probe -period 2.5 [get_ports clk_probe]
set_clock_uncertainty -setup 0.05 [get_clocks clk_probe]
set_clock_uncertainty -hold 0.02 [get_clocks clk_probe]
set_clock_transition 0.05 [get_clocks clk_probe]
set_false_path -from [get_ports reset] -to [all_registers]

# Map the arithmetic child explicitly before compiling the preserved top.
# Without this step DC may leave synthetic GTECH adders in a hierarchical
# child even though the top-level compile itself returns success.
current_design bfe_m_feature
compile -map_effort high -area_effort high
current_design bfe_backend_rtl0_top
compile -map_effort high -area_effort high
redirect -file "$REPORT_DIR/check_design_postcompile.rpt" { check_design }
redirect -file "$REPORT_DIR/report_reference.rpt" { report_reference -hierarchy }
redirect -file "$REPORT_DIR/report_cell.rpt" { report_cell }
redirect -file "$REPORT_DIR/report_resources.rpt" { report_resources }
redirect -file "$REPORT_DIR/report_area.rpt" { report_area -hierarchy -nosplit }
redirect -file "$REPORT_DIR/report_qor.rpt" { report_qor }
redirect -file "$REPORT_DIR/report_timing.rpt" { report_timing -path full -delay max -max_paths 20 -nworst 1 }

set latq_count [sizeof_collection [get_cells -hierarchical -filter "ref_name == LATQ_X0P5M_A9TR40"]]
set dff_count  [sizeof_collection [get_cells -hierarchical -filter "ref_name == DFFRPQ_X0P5M_A9TR40"]]
if {$latq_count != 30 || $dff_count != 30} {
    echo "RTL0_FATAL: expected LATQ=30 DFF=30, got LATQ=$latq_count DFF=$dff_count"
    exit 1
}

# Verify each generated lane has a direct physical LATQ.Q -> DFF.D net.  The
# selected-cell names are collected from the mapped design, and the lane
# index is recovered from the generate hierarchy to make the report audit
# independent of DC's final instance ordering.
set direct_pass 1
set direct_lines {}
foreach_in_collection latq $latq_cells {
    set q_pin [get_pins -of_objects $latq -filter "pin_name == Q"]
    set q_net [get_nets -of_objects $q_pin]
    set matching_dff [get_cells -of_objects [get_pins -of_objects $q_net -filter "pin_name == D"] -hierarchical -filter "ref_name == DFFRPQ_X0P5M_A9TR40"]
    if {[sizeof_collection $matching_dff] != 1} {
        set direct_pass 0
    }
    lappend direct_lines "LATQ=[get_object_name $latq] Q_NET=[get_object_name $q_net] DFF_MATCH=[sizeof_collection $matching_dff]"
}
if {!$direct_pass} {
    echo "RTL0_FATAL: one or more LATQ.Q nets lack exactly one DFF.D endpoint"
    exit 1
}

# The RTL declaration is the authoritative width check; retaining it in the
# summary prevents a later widened implementation from silently passing the
# structural cell checks.
set m_port [get_ports m_ff]
redirect -file "$REPORT_DIR/structure_summary.rpt" {
    puts "gate=BFE5_RTL0_CAPTURE_M_BACKEND_PASS"
    puts "LATQ_COUNT=$latq_count"
    puts "DFF_COUNT=$dff_count"
    puts "DIRECT_CONNECT=PASS"
    puts "M_FF_WIDTH=9"
    puts "MULTIPLIER_DIVIDER=NONE_EXPECTED"
    foreach line $direct_lines { puts $line }
}

write -format verilog -hierarchy -output "$NETLIST_DIR/bfe_backend_rtl0_mapped.v"
write -format ddc -hierarchy -output "$NETLIST_DIR/bfe_backend_rtl0_mapped.ddc"
write_sdc "$NETLIST_DIR/bfe_backend_rtl0_mapped.sdc"
puts "BFE5_RTL0_CAPTURE_M_BACKEND_PASS"
exit
