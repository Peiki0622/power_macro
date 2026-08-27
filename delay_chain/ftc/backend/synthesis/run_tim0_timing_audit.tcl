# B-FE5-TIM0 timing audit.
#
# This script reads the already mapped timing-opt DDC.  It does not analyze
# RTL, invoke compile, retime registers, or write a replacement netlist.  The
# sweep therefore characterizes the frozen implementation at several clock
# periods without changing ARCH0 or the 30-LATQ/30-DFF capture boundary.
set SCRIPT_DIR [file dirname [file normalize [info script]]]
set BACKEND_ROOT [file normalize [file join $SCRIPT_DIR ..]]
set DEFAULT_DDC "$BACKEND_ROOT/netlist/timing_opt/bfe_backend_timing_opt_mapped.ddc"
set DDC_PATH [expr {[info exists ::env(BFE5_TIM0_DDC)] ? $::env(BFE5_TIM0_DDC) : $DEFAULT_DDC}]
set REPORT_DIR "$BACKEND_ROOT/reports/tim0"
set LIB_BASE "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1"
set TARGET_LIBRARY "$LIB_BASE/db/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db"
set LIB_SOURCE "$LIB_BASE/lib/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.lib"
file mkdir $REPORT_DIR

if {![file exists $DDC_PATH]} {
    puts "BFE5_TIM0_TIMING_AUDIT_STOP: mapped DDC not found: $DDC_PATH"
    exit 2
}

set_app_var sh_enable_page_mode false
set_app_var target_library $TARGET_LIBRARY
set_app_var link_library "* $TARGET_LIBRARY"
set search_path [concat $search_path "$LIB_BASE/db"]
read_ddc $DDC_PATH
current_design bfe_backend_top
link

set lib_cells {}
foreach cell_name {DFFRPQ_X0P5M_A9TR40 DFFRPQ_X1M_A9TR40 LATQ_X0P5M_A9TR40} {
    set cell_matches [get_lib_cells -quiet "*/$cell_name"]
    if {[sizeof_collection $cell_matches] > 0} {
        set lib_cells [add_to_collection $lib_cells $cell_matches]
    }
}
redirect -file "$REPORT_DIR/clock_pulse_margin.rpt" {
    puts "BFE5_TIM0_CLOCK_PULSE_MARGIN_AUDIT"
    puts "LIBERTY_CELLS=[get_object_name $lib_cells]"
    foreach_in_collection cell $lib_cells {
        puts "CELL=[get_object_name $cell]"
        foreach attr {min_clock_high min_clock_low min_period recovery removal} {
            set value [get_attribute -quiet $cell $attr]
            if {$value eq ""} { set value "UNAVAILABLE" }
            puts "  $attr=$value"
        }
        # The Liberty source stores these as timing arcs rather than scalar
        # cell attributes.  Extract only the selected cell block and retain
        # its timing_type/index/values records as the auditable pulse and
        # recovery/removal margin evidence.
        set cell_name [lindex [split [get_object_name $cell] /] end]
        set lib_extract [exec awk -v target=$cell_name {
            index($0, "cell(" target ")") { inside=1; next }
            inside && /^  cell\(/ { exit }
            inside && /timing_type : (min_pulse_width|recovery|removal|min_period)/ { print NR ":" $0; in_check=1; next }
            inside && in_check && /(index_[123]|values)\(/ { print NR ":" $0 }
            inside && in_check && substr($0,1,9) == ("        " sprintf("%c",125)) { in_check=0 }
        } $LIB_SOURCE]
        if {$lib_extract eq ""} { puts "  LIBERTY_TIMING_RECORDS=UNAVAILABLE" } else { puts $lib_extract }
    }
}

# Emit one full timing report per requested period.  The report includes
# startpoint, endpoint, arrival, required, slack, and the complete point list,
# from which the critical combinational depth is counted by the review tool.
# Name matching is deliberately hierarchical and bounded to the frozen
# register groups; it cannot silently substitute an unrelated global worst path.
proc report_tim0_class {label from_glob to_glob} {
    global tim0_audit_gap
    puts "PATH_CLASS=$label"
    set from_pins [get_pins -hierarchical $from_glob -quiet]
    set to_pins   [get_pins -hierarchical $to_glob -quiet]
    if {[sizeof_collection $from_pins] == 0 || [sizeof_collection $to_pins] == 0} {
        puts "STATUS=NO_ENDPOINT_MATCH"
        puts "FROM_GLOB=$from_glob"
        puts "TO_GLOB=$to_glob"
        set tim0_audit_gap 1
        return
    }
    if {[catch {set paths [get_timing_paths -from $from_pins -to $to_pins -max_paths 1 -nworst 1 -delay_type max]} path_error]} {
        puts "STATUS=PATH_QUERY_ERROR"
        puts "ERROR=$path_error"
        set tim0_audit_gap 1
        return
    }
    if {[sizeof_collection $paths] == 0} {
        puts "STATUS=NO_TIMING_PATH"
        set tim0_audit_gap 1
        return
    }
    puts "STATUS=REPORTING"
    set path [index_collection $paths 0]
    puts "STARTPOINT=[get_object_name [get_attribute $path startpoint]]"
    puts "ENDPOINT=[get_object_name [get_attribute $path endpoint]]"
    puts "ARRIVAL=[get_attribute $path arrival]"
    puts "REQUIRED=[get_attribute $path required]"
    puts "SLACK=[get_attribute $path slack]"
    puts "DEPTH_METHOD=full_path_point_list_below"
    report_timing -from $from_pins -to $to_pins -path full -delay max -max_paths 1 -nworst 1
}

set periods {2.40 2.45 2.50 2.60 2.75}
set tim0_audit_gap 0
foreach period $periods {
    remove_clock [get_clocks clk_probe -quiet]
    create_clock -name clk_probe -period $period [get_ports clk_probe]
    set_clock_uncertainty -setup 0.05 [get_clocks clk_probe]
    set_clock_uncertainty -hold 0.02 [get_clocks clk_probe]
    set_clock_transition 0.05 [get_clocks clk_probe]
    # Override the 2.50 ns max-delay constraint serialized in the source DDC;
    # otherwise every sweep point would silently report the same requirement.
    set_max_delay $period -from [all_registers] -to [all_registers]
    redirect -file "$REPORT_DIR/timing_${period}ns.rpt" {
        puts "BFE5_TIM0_TIMING_SWEEP_PERIOD_NS=$period"
        report_tim0_class q_ff_to_P1 \
            "*u_ff/Q" \
            "*pair_q_reg*/D"
        report_tim0_class P1_to_P2 \
            "*pair_q_reg*/Q" \
            "*level_two_q_reg*/D"
        report_tim0_class P2_to_M_FF \
            "*level_two_q_reg*/Q" \
            "*m_ff_o_reg*/D"
        report_tim0_class event_context_to_operand \
            "*event_m_q_reg*/Q" \
            "*event_m_pipe_q_reg*/D"
        report_tim0_class operand_to_P4a \
            "*event_m_pipe_q_reg*/Q" \
            "*sub_low_q_reg*/D"
        report_tim0_class P4a_to_P4b \
            "*sub_high_m_q_reg*/Q" \
            "*delta_q_reg*/D"
        report_tim0_class P4b_to_alarm_sticky \
            "*delta_q_reg*/Q" \
            "*droop_alarm_sticky_o_reg/D"
    }
}

# A compact machine-readable summary records the sweep's worst slack without
# claiming signoff.  Detailed start/end points stay in the period reports.
redirect -file "$REPORT_DIR/summary.rpt" {
    puts "BFE5_TIM0_TIMING_MARGIN_CHARACTERIZED"
    puts "SOURCE_DDC=$DDC_PATH"
    puts "CLOCK_PERIODS_NS=$periods"
    puts "PVT_STATUS=single mapped Liberty corner from timing-opt DDC"
    puts "AUDIT_GAP=$tim0_audit_gap"
    puts "PHYSICAL_SIGNOFF=NO"
}
if {$tim0_audit_gap} {
    puts "BFE5_TIM0_TIMING_AUDIT_STOP: one or more requested path classes were unavailable"
    exit 3
}
puts "BFE5_TIM0_TIMING_MARGIN_CHARACTERIZED"
exit
