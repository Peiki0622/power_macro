# ============================================================================
# M1 standalone manager/mapper synthesis and 400 MHz STA
# ============================================================================
# This run maps only the new M1 manager hierarchy, including its exact mapper
# child.  Frozen H0, calibration RTL, sensor netlist, and all mixed-signal
# content are intentionally absent.  Consequently this is an incremental M1
# timing proof, not a re-synthesis or re-optimization of H0's CAL->S_CLK cone.
# ============================================================================

set SCRIPT_DIR [file dirname [file normalize [info script]]]
set M1_ROOT [file normalize [file join $SCRIPT_DIR ../..]]
set REPO_ROOT [file normalize [file join $M1_ROOT ../../../..]]
set RTL_ROOT "$REPO_ROOT/delay_chain/ftc/controller/rtl"
set OUTPUT_DIR "$M1_ROOT/synthesis/netlist"
set REPORT_DIR "$M1_ROOT/synthesis/reports"
set WORK_DIR "$M1_ROOT/synthesis/work"

# Reuse the same ordinary SMIC40LL RVT controller library/corner used by H0.
# No power-crossing cell search or alternate library is introduced for M1.
set LIB_BASE "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1"
set TARGET_LIBRARY "$LIB_BASE/db/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db"
set DESIGN_NAME "ftc_detection_margin_manager"

file mkdir $OUTPUT_DIR
file mkdir $REPORT_DIR
file mkdir $WORK_DIR
set_app_var sh_enable_page_mode false
set_app_var enable_recovery_removal_arcs true
set_app_var compile_delete_unloaded_sequential_cells false
set_app_var compile_seqmap_propagate_constants false
set_app_var target_library $TARGET_LIBRARY
set_app_var link_library "* $TARGET_LIBRARY"
set search_path [concat $search_path "$LIB_BASE/db"]
define_design_lib WORK -path $WORK_DIR

# Analyze the literal mapper before its sequential manager parent.  Both are
# synthesizable SystemVerilog and deliberately contain no synthesizable
# function, arithmetic codebook generator, or generic thermometer decoder.
analyze -format sverilog -work WORK "$RTL_ROOT/ftc_detection_margin_mapper.sv"
analyze -format sverilog -work WORK "$RTL_ROOT/ftc_detection_margin_manager.sv"
elaborate $DESIGN_NAME -work WORK
current_design $DESIGN_NAME
link
check_design

# The trusted H0/M1 sequencing contract remains 400 MHz / 2.5 ns.  POR is an
# asynchronous reset, excluded from ordinary data timing while recovery/removal
# arcs remain enabled on the mapped sequential cells.
create_clock -name cal_clk -period 2.5 [get_ports cal_clk_i]
set_clock_uncertainty -setup 0.05 [get_clocks cal_clk]
set_clock_uncertainty -hold 0.02 [get_clocks cal_clk]
set_clock_transition 0.05 [get_clocks cal_clk]
set_input_transition 0.10 [get_ports ctrl_por_n_i]
set_false_path -from [get_ports ctrl_por_n_i] -to [all_registers]

# H0 snapshot, handoff status, and M1 selection are synchronous controller
# signals.  The budgets match H0-style PD_CTRL interfaces and intentionally do
# not claim an added physical CTRL-to-SENSE crossing delay.
set_input_delay -clock cal_clk -max 0.6 [get_ports {cal_cfg_valid_i det_prepare_i det_owner_valid_i handoff_blocked_i}]
set_input_delay -clock cal_clk -min 0.1 [get_ports {cal_cfg_valid_i det_prepare_i det_owner_valid_i handoff_blocked_i}]
set_input_delay -clock cal_clk -max 0.3 [get_ports {cal_medium_code_snapshot_i* cal_fine_code_snapshot_i* cal_medium_therm_snapshot_i* cal_fine_therm_snapshot_i*}]
set_input_delay -clock cal_clk -min 0.0 [get_ports {cal_medium_code_snapshot_i* cal_fine_code_snapshot_i* cal_medium_therm_snapshot_i* cal_fine_therm_snapshot_i*}]
set_input_delay -clock cal_clk -max 0.5 [get_ports {margin_sel_i* margin_select_valid_i}]
set_input_delay -clock cal_clk -min 0.0 [get_ports {margin_sel_i* margin_select_valid_i}]

# H0 consumes the detector-side controls under its existing safe handoff.  The
# control budgets are explicit but this standalone run does not time H0 itself.
set_output_delay -clock cal_clk -max 0.4 [get_ports {det_takeover_ready_o det_sense_dff_reset_o det_sense_s_clk_o}]
set_output_delay -clock cal_clk -min 0.0 [get_ports {det_takeover_ready_o det_sense_dff_reset_o det_sense_s_clk_o}]
set_output_delay -clock cal_clk -max 0.5 [get_ports {det_medium_therm_o* det_fine_therm_o*}]
set_output_delay -clock cal_clk -min 0.0 [get_ports {det_medium_therm_o* det_fine_therm_o*}]
set_output_delay -clock cal_clk -max 0.6 [get_ports {margin_cfg_valid_o mapping_supported_o trip_qualified_o margin_protocol_error_o m_det_o* f_det_o* margin_level_o*}]
set_output_delay -clock cal_clk -min 0.0 [get_ports {margin_cfg_valid_o mapping_supported_o trip_qualified_o margin_protocol_error_o m_det_o* f_det_o* margin_level_o*}]

set_max_fanout 16 [current_design]
set_max_transition 0.25 [current_design]
set_max_capacitance 0.1 [current_design]
compile -map_effort high -area_effort high

# Preserve enough report detail to distinguish input-to-state, codebook-to-
# target-register, and output control timing without inspecting H0's frozen
# internal timing cone.
redirect -tee "$REPORT_DIR/check_design.rpt" { check_design }
redirect -tee "$REPORT_DIR/timing_setup.rpt" { report_timing -path full -delay max -max_paths 30 -nworst 1 }
redirect -tee "$REPORT_DIR/timing_hold.rpt" { report_timing -path full -delay min -max_paths 30 -nworst 1 }
redirect -tee "$REPORT_DIR/constraints_all.rpt" { report_constraint -all_violators }
redirect -tee "$REPORT_DIR/clock_and_pulse_width.rpt" { report_clock -skew -attribute }
redirect -tee "$REPORT_DIR/fanout_transition.rpt" { report_constraint -all_violators -max_transition; report_constraint -all_violators -max_fanout }
redirect -tee "$REPORT_DIR/selection_to_state.rpt" { report_timing -from [get_ports {margin_sel_i* margin_select_valid_i}] -to [all_registers -data_pins] -path full -delay max -max_paths 30 }
redirect -tee "$REPORT_DIR/mapper_to_target_register.rpt" { report_timing -from [get_ports {cal_medium_code_snapshot_i* cal_fine_code_snapshot_i* margin_sel_i*}] -to [all_registers -data_pins] -path full -delay max -max_paths 30 }
redirect -tee "$REPORT_DIR/detector_control_outputs.rpt" { report_timing -to [get_ports {det_takeover_ready_o det_sense_dff_reset_o det_sense_s_clk_o det_medium_therm_o* det_fine_therm_o*}] -path full -delay max -max_paths 60 }
redirect -tee "$REPORT_DIR/cell_usage.rpt" { report_cell; report_reference -hierarchy }
redirect -tee "$REPORT_DIR/qor.rpt" { report_qor }
redirect -tee "$REPORT_DIR/ports.rpt" { report_port -verbose }

write -format verilog -hierarchy -output "$OUTPUT_DIR/${DESIGN_NAME}_synth.v"
write -format ddc -hierarchy -output "$OUTPUT_DIR/${DESIGN_NAME}_synth.ddc"
write_sdc "$OUTPUT_DIR/${DESIGN_NAME}_synth.sdc"
write_sdf -version 3.0 -context verilog -load_delay net "$OUTPUT_DIR/${DESIGN_NAME}_synth.sdf"
puts "M1 standalone synthesis completed: ftc_detection_margin_manager at 400 MHz"
exit
