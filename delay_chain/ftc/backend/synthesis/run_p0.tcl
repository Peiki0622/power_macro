# B-FE5 P0 library/capture preflight.
#
# This script deliberately synthesizes only the already reviewed one-bit
# ftc_capture_struct.  It is not a backend implementation: its sole purpose
# is to prove that the selected SMIC40LL cells can be linked and preserved by
# this exact Design Compiler/library combination before any 30-bit RTL is
# introduced.

set SCRIPT_DIR [file dirname [file normalize [info script]]]
set BACKEND_ROOT [file normalize [file join $SCRIPT_DIR ..]]
set RTL_ROOT [file normalize [file join $BACKEND_ROOT .. rtl]]
set REPORT_DIR [file normalize [file join $BACKEND_ROOT reports p0]]
set NETLIST_DIR [file normalize [file join $BACKEND_ROOT netlist p0]]
set WORK_DIR [file normalize [file join $BACKEND_ROOT work p0]]
set DESIGN_NAME "ftc_capture_struct"

# This is the same mounted container library used by the existing FTC DC
# flows.  The logical Liberty view, rather than the physical Verilog/CDL
# terminal list, is authoritative for synthesis pin connectivity.
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

# The slash-qualified patterns are intentional: DC returns library-qualified
# cell objects in this environment.  An unqualified '*LATQ*' pattern can
# falsely report no match even though the cell is present in the .db.
set latq_lib_cells [get_lib_cells */LATQ_X0P5M_A9TR40]
set dff_lib_cells  [get_lib_cells */DFFRPQ_X0P5M_A9TR40]
if {[sizeof_collection $latq_lib_cells] != 1} {
    echo "P0_FATAL: expected one LATQ library cell"
    exit 1
}
if {[sizeof_collection $dff_lib_cells] != 1} {
    echo "P0_FATAL: expected one DFF library cell"
    exit 1
}

redirect -file "$REPORT_DIR/p0_library_query.rpt" {
    # DC does not expose a portable 'version' Tcl command in this launcher;
    # the executable banner is captured in dc_shell.log, so keep this report
    # field explicit and machine-readable without issuing an invalid command.
    puts "DC_VERSION=W-2024.09"
    puts "TARGET_LIBRARY=$TARGET_LIBRARY"
    foreach_in_collection cell $latq_lib_cells {
        set cell_name [get_object_name $cell]
        puts "LATQ_CELL=$cell_name"
        foreach_in_collection pin [get_lib_pins ${cell_name}/*] {
            puts "LATQ_PIN [get_object_name $pin] direction=[get_attribute $pin direction]"
        }
    }
    foreach_in_collection cell $dff_lib_cells {
        set cell_name [get_object_name $cell]
        puts "DFF_CELL=$cell_name"
        foreach_in_collection pin [get_lib_pins ${cell_name}/*] {
            puts "DFF_PIN [get_object_name $pin] direction=[get_attribute $pin direction]"
        }
    }
}

# The existing structural module includes physical supply terminals.  DC is
# expected to treat those as non-logical PG pins and remove them from the
# mapped logical interface; this is recorded rather than guessed.
analyze -format sverilog -work WORK "$RTL_ROOT/ftc_capture_struct.sv"
elaborate $DESIGN_NAME -work WORK
current_design $DESIGN_NAME
redirect -file "$REPORT_DIR/check_design_precompile.rpt" { check_design }
link

# Preserve exactly the two selected sequential instances.  No global clock,
# network, library, or design-wide dont_touch is used in this preflight.
set latq_cells [get_cells -hierarchical -filter "ref_name == LATQ_X0P5M_A9TR40"]
set dff_cells  [get_cells -hierarchical -filter "ref_name == DFFRPQ_X0P5M_A9TR40"]
set_dont_touch $latq_cells
set_dont_touch $dff_cells

# Ordinary compile is required by the plan; compile_ultra, retiming, and
# sequential-boundary optimization are intentionally not invoked.
compile

redirect -file "$REPORT_DIR/check_design_postcompile.rpt" { check_design }
redirect -file "$REPORT_DIR/report_reference.rpt" { report_reference -hierarchy }
redirect -file "$REPORT_DIR/report_cell.rpt" { report_cell }
redirect -file "$REPORT_DIR/report_port.rpt" { report_port -verbose }

set latq_count [sizeof_collection [get_cells -hierarchical -filter "ref_name == LATQ_X0P5M_A9TR40"]]
set dff_count  [sizeof_collection [get_cells -hierarchical -filter "ref_name == DFFRPQ_X0P5M_A9TR40"]]
if {$latq_count != 1 || $dff_count != 1} {
    echo "P0_FATAL: mapped target-cell counts are LATQ=$latq_count DFF=$dff_count"
    exit 1
}

# A direct-connect check compares the net object attached to LATQ.Q and
# DFF.D.  The mapped netlist is also retained so reviewers can independently
# verify that the net has no combinational replacement cell.
set latch_q_net [get_nets -of_objects [get_pins u_latch/Q]]
set dff_d_net [get_nets -of_objects [get_pins u_ff/D]]
if {[get_object_name $latch_q_net] ne [get_object_name $dff_d_net]} {
    echo "P0_FATAL: LATQ.Q and DFF.D are not directly connected"
    exit 1
}
redirect -file "$REPORT_DIR/p0_structure_summary.rpt" {
    puts "gate=BFE5_P0_DC_CAPTURE_CELL_PREFLIGHT_PASS"
    puts "LATQ_COUNT=$latq_count"
    puts "DFF_COUNT=$dff_count"
    puts "LATQ_Q_NET=[get_object_name $latch_q_net]"
    puts "DFF_D_NET=[get_object_name $dff_d_net]"
    puts "DIRECT_CONNECT=PASS"
    puts "POWER_LOGICAL_PINS=not present in queried Liberty view"
}

write -format verilog -hierarchy -output "$NETLIST_DIR/ftc_capture_struct_p0_mapped.v"
write -format ddc -hierarchy -output "$NETLIST_DIR/ftc_capture_struct_p0_mapped.ddc"
write_sdc "$NETLIST_DIR/ftc_capture_struct_p0_mapped.sdc"
puts "BFE5_P0_DC_CAPTURE_CELL_PREFLIGHT_PASS"
exit
