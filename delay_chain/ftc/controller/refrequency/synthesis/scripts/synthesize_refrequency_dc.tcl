# ============================================================================
# RF8 isolated Design Compiler synthesis and static-timing flow
# ============================================================================
# Every generated file is rooted below controller/refrequency/synthesis.  The
# historical Phase-7 netlist, SDF, reports, RTL, and timing handoff are read
# only.  This script does not add synthesis RTL functions or modify algorithmic
# logic; it maps the already audited RF7 timing constants.
# ============================================================================

set SCRIPT_DIR [file dirname [file normalize [info script]]]
set RF_SYNTH_ROOT [file normalize [file join $SCRIPT_DIR ..]]
set CONTROLLER_ROOT [file normalize [file join $SCRIPT_DIR ../../..]]
set DESIGN_NAME "ftc_cal_controller_top"
set RTL_DIR "$CONTROLLER_ROOT/rtl"
set CONSTRAINT_FILE "$RF_SYNTH_ROOT/constraints/ftc_controller_refrequency.sdc"
set OUTPUT_DIR "$RF_SYNTH_ROOT/netlist"
set REPORT_DIR "$RF_SYNTH_ROOT/reports"

# RF2 audited this exact SMIC40LL RVT database.  It is accessed on the EDA
# host, never via a container-only /host/data path, so the run is reproducible
# with the verified host mapping.
set LIB_BASE "/home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1"
set TARGET_LIBRARY "$LIB_BASE/db/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db"
set LINK_LIBRARY "* $TARGET_LIBRARY"

file mkdir $OUTPUT_DIR
file mkdir $REPORT_DIR
file mkdir ./work
set_app_var sh_enable_page_mode false
# ``analyze -format sverilog`` below selects SystemVerilog explicitly.  Do not
# set the retired ``hdlin_language_extensions`` app-var: DC Q-2019 reports it
# as an error even though it continues, which would pollute the active RF8 log.
set_app_var enable_recovery_removal_arcs true
set_app_var compile_delete_unloaded_sequential_cells false
set_app_var compile_seqmap_propagate_constants false
set_app_var target_library $TARGET_LIBRARY
set_app_var link_library $LINK_LIBRARY
set search_path [concat $search_path "$LIB_BASE/db"]
define_design_lib WORK -path ./work

# Package first, then explicit dependency order.  The list is intentionally
# short and mirrors the historical controller topology, avoiding broad globs
# that could accidentally compile unrelated experiment RTL.
analyze -format sverilog -work WORK "$RTL_DIR/ftc_cal_pkg.sv"
foreach rtl_file [list \
    "$RTL_DIR/ftc_cfg_therm_regs.sv" \
    "$RTL_DIR/ftc_q_sampler.sv" \
    "$RTL_DIR/ftc_operation_sequencer.sv" \
    "$RTL_DIR/ftc_cal_fsm.sv" \
    "$RTL_DIR/ftc_cal_controller_top.sv"] {
    analyze -format sverilog -work WORK $rtl_file
}
elaborate $DESIGN_NAME -work WORK
current_design $DESIGN_NAME
link
check_design

# The active 2.5 ns timing environment is a separate, task-owned SDC.  No
# global clock-gating transform is requested; sensor controls remain ordinary
# registered outputs and retain the hardware-friendly RTL implementation.
source $CONSTRAINT_FILE
set_operating_conditions -max ss_typical_max_0p99v_125c
set_fix_multiple_port_nets -all -buffer_constants [get_designs]
compile -map_effort high -area_effort high

# RF8 requires independently reviewable reports for timing, design rules,
# asynchronous controls, and every controller/sensor interface class.
redirect -tee "$REPORT_DIR/check_design.rpt" { check_design }
redirect -tee "$REPORT_DIR/timing_setup.rpt" { report_timing -path full -delay max -max_paths 20 -nworst 1 }
redirect -tee "$REPORT_DIR/timing_hold.rpt" { report_timing -path full -delay min -max_paths 20 -nworst 1 }
redirect -tee "$REPORT_DIR/constraints_all.rpt" { report_constraint -all_violators }
redirect -tee "$REPORT_DIR/clock_and_pulse_width.rpt" { report_clock -skew -attribute }
redirect -tee "$REPORT_DIR/fanout_transition.rpt" { report_constraint -all_violators -max_transition; report_constraint -all_violators -max_fanout }
redirect -tee "$REPORT_DIR/q_final_sampling_path.rpt" { report_timing -from [get_ports q_final] -delay max -path full }
redirect -tee "$REPORT_DIR/sense_s_clk_path.rpt" { report_timing -to [get_ports sense_s_clk] -delay max -path full }
redirect -tee "$REPORT_DIR/sense_dff_reset_path.rpt" { report_timing -to [get_ports sense_dff_reset] -delay max -path full }
redirect -tee "$REPORT_DIR/thermometer_paths.rpt" { report_timing -to [get_ports {medium_therm* fine_therm*}] -delay max -path full }
redirect -tee "$REPORT_DIR/cell_usage.rpt" { report_cell; report_reference -hierarchy }
redirect -tee "$REPORT_DIR/qor.rpt" { report_qor }
redirect -tee "$REPORT_DIR/ports.rpt" { report_port -verbose }

# The mapped netlist, propagated SDC, and Verilog-context SDF are the only
# RF8 implementation handoff artifacts consumed by later dynamic stages.
write -format verilog -hierarchy -output "$OUTPUT_DIR/${DESIGN_NAME}_synth.v"
write -format ddc -hierarchy -output "$OUTPUT_DIR/${DESIGN_NAME}_synth.ddc"
write_sdc "$OUTPUT_DIR/${DESIGN_NAME}_synth.sdc"
write_sdf -version 3.0 -context verilog -load_delay net "$OUTPUT_DIR/${DESIGN_NAME}_synth.sdf"
puts "RF8 synthesis completed for 400 MHz / 2.5 ns active timing contract"
exit
