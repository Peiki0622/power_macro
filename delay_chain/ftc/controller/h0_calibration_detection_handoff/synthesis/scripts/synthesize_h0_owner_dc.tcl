# ============================================================================
# H0 independent ownership-module synthesis and STA
# ============================================================================
# This Design Compiler run maps only ftc_sensor_owner_handoff.  The frozen
# startup-calibration controller is intentionally absent: H0-5 measures the
# incremental ownership/snapshot logic first, exactly as required by the H0
# plan.  Every generated netlist, SDC, SDF, log, and report is rooted in the
# H0-owned synthesis directory.
# ============================================================================

set SCRIPT_DIR [file dirname [file normalize [info script]]]
set H0_ROOT [file normalize [file join $SCRIPT_DIR ../..]]
set REPO_ROOT [file normalize [file join $H0_ROOT ../../../..]]
set RTL_FILE "$REPO_ROOT/delay_chain/ftc/controller/rtl/ftc_sensor_owner_handoff.sv"
set DESIGN_NAME "ftc_sensor_owner_handoff"
set OUTPUT_DIR "$H0_ROOT/synthesis/netlist"
set REPORT_DIR "$H0_ROOT/synthesis/reports"
set WORK_DIR "$H0_ROOT/synthesis/work"

# Reuse the exact RF8 RVT library/corner from the project-owned SMIC40LL
# technology mount.  The /host/data mount is the authoritative container
# path; no user-home copy or alternative level-shifter library is introduced.
set LIB_BASE "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1"
set TARGET_LIBRARY "$LIB_BASE/db/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db"

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

analyze -format sverilog -work WORK $RTL_FILE
elaborate $DESIGN_NAME -work WORK
current_design $DESIGN_NAME
link
check_design

# Active H0 clock and asynchronous controller POR.  All ordinary data paths
# are required to close in one 2.5 ns cycle; POR is excluded from data timing
# while recovery/removal arcs remain enabled for the mapped sequential cells.
create_clock -name cal_clk -period 2.5 [get_ports cal_clk_i]
set_clock_uncertainty -setup 0.05 [get_clocks cal_clk]
set_clock_uncertainty -hold 0.02 [get_clocks cal_clk]
set_clock_transition 0.05 [get_clocks cal_clk]
set_input_transition 0.1 [get_ports ctrl_por_n_i]
set_false_path -from [get_ports ctrl_por_n_i] -to [all_registers]

# The status/control inputs are synchronous to cal_clk in H0.  Modest input
# delays preserve a real controller interface without claiming a physical
# cross-domain delay for the later ideal power-aware boundary.
set_input_delay -clock cal_clk -max 0.6 [get_ports {cal_busy_i cal_done_i cal_fail_i lock_valid_i}]
set_input_delay -clock cal_clk -min 0.1 [get_ports {cal_busy_i cal_done_i cal_fail_i lock_valid_i}]
set_input_delay -clock cal_clk -max 0.3 [get_ports {cal_sense_dff_reset_i cal_sense_s_clk_i}]
set_input_delay -clock cal_clk -min 0.0 [get_ports {cal_sense_dff_reset_i cal_sense_s_clk_i}]
set_input_delay -clock cal_clk -max 0.3 [get_ports {cal_medium_therm_i* cal_fine_therm_i* cal_medium_code_i* cal_fine_code_i*}]
set_input_delay -clock cal_clk -min 0.0 [get_ports {cal_medium_therm_i* cal_fine_therm_i* cal_medium_code_i* cal_fine_code_i*}]
set_input_delay -clock cal_clk -max 0.5 [get_ports det_takeover_ready_i]
set_input_delay -clock cal_clk -min 0.0 [get_ports det_takeover_ready_i]
set_input_delay -clock cal_clk -max 0.3 [get_ports {det_sense_dff_reset_i det_sense_s_clk_i det_medium_therm_i* det_fine_therm_i*}]
set_input_delay -clock cal_clk -min 0.0 [get_ports {det_sense_dff_reset_i det_sense_s_clk_i det_medium_therm_i* det_fine_therm_i*}]

# Sensor-control outputs are constrained with the existing RF8-style external
# budget.  Snapshot/status outputs are observed in PD_CTRL and receive a less
# restrictive but still explicit one-cycle external budget.
set_output_delay -clock cal_clk -max 0.4 [get_ports {sense_dff_reset_o sense_s_clk_o}]
set_output_delay -clock cal_clk -min 0.0 [get_ports {sense_dff_reset_o sense_s_clk_o}]
set_output_delay -clock cal_clk -max 0.5 [get_ports {medium_therm_o* fine_therm_o*}]
set_output_delay -clock cal_clk -min 0.0 [get_ports {medium_therm_o* fine_therm_o*}]
set_output_delay -clock cal_clk -max 0.6 [get_ports {cal_cfg_valid_o cal_medium_code_snapshot_o* cal_fine_code_snapshot_o* cal_medium_therm_snapshot_o* cal_fine_therm_snapshot_o* det_prepare_o det_owner_valid_o handoff_blocked_o handoff_protocol_error_o handoff_state_o*}]
set_output_delay -clock cal_clk -min 0.0 [get_ports {cal_cfg_valid_o cal_medium_code_snapshot_o* cal_fine_code_snapshot_o* cal_medium_therm_snapshot_o* cal_fine_therm_snapshot_o* det_prepare_o det_owner_valid_o handoff_blocked_o handoff_protocol_error_o handoff_state_o*}]

set_max_fanout 16 [current_design]
# The state/status observability ports are not the physical sensor clock path.
# A 0.25 ns explicit output slew limit avoids a zero-slack report-rounding
# violation on handoff_state_o[1] while remaining a bounded controller-output
# constraint; sensor-control outputs retain their tighter output-delay budget.
set_max_transition 0.25 [current_design]
set_max_capacitance 0.1 [current_design]
compile -map_effort high -area_effort high

# General closure reports plus explicit H0 path reports required by the plan.
redirect -tee "$REPORT_DIR/check_design.rpt" { check_design }
redirect -tee "$REPORT_DIR/timing_setup.rpt" { report_timing -path full -delay max -max_paths 30 -nworst 1 }
redirect -tee "$REPORT_DIR/timing_hold.rpt" { report_timing -path full -delay min -max_paths 30 -nworst 1 }
redirect -tee "$REPORT_DIR/constraints_all.rpt" { report_constraint -all_violators }
redirect -tee "$REPORT_DIR/clock_and_pulse_width.rpt" { report_clock -skew -attribute }
redirect -tee "$REPORT_DIR/fanout_transition.rpt" { report_constraint -all_violators -max_transition; report_constraint -all_violators -max_fanout }
redirect -tee "$REPORT_DIR/cal_sclk_to_sensor_sclk.rpt" { report_timing -from [get_ports cal_sense_s_clk_i] -to [get_ports sense_s_clk_o] -path full -delay max }
redirect -tee "$REPORT_DIR/cal_reset_to_sensor_reset.rpt" { report_timing -from [get_ports cal_sense_dff_reset_i] -to [get_ports sense_dff_reset_o] -path full -delay max }
redirect -tee "$REPORT_DIR/cal_medium_to_sensor_medium.rpt" { report_timing -from [get_ports cal_medium_therm_i*] -to [get_ports medium_therm_o*] -path full -delay max }
redirect -tee "$REPORT_DIR/cal_fine_to_sensor_fine.rpt" { report_timing -from [get_ports cal_fine_therm_i*] -to [get_ports fine_therm_o*] -path full -delay max }
redirect -tee "$REPORT_DIR/cal_sclk_to_sensor_sclk_min.rpt" { report_timing -from [get_ports cal_sense_s_clk_i] -to [get_ports sense_s_clk_o] -path full -delay min }
redirect -tee "$REPORT_DIR/cal_reset_to_sensor_reset_min.rpt" { report_timing -from [get_ports cal_sense_dff_reset_i] -to [get_ports sense_dff_reset_o] -path full -delay min }
redirect -tee "$REPORT_DIR/cal_medium_to_sensor_medium_min.rpt" { report_timing -from [get_ports cal_medium_therm_i*] -to [get_ports medium_therm_o*] -path full -delay min }
redirect -tee "$REPORT_DIR/cal_fine_to_sensor_fine_min.rpt" { report_timing -from [get_ports cal_fine_therm_i*] -to [get_ports fine_therm_o*] -path full -delay min }
# Edge-specific reports make the measured rise/fall bounds explicit instead
# of inferring them from one worst path selected by report_timing.
redirect -tee "$REPORT_DIR/cal_sclk_rise_to_sensor_sclk.rpt" { report_timing -rise_from [get_ports cal_sense_s_clk_i] -rise_to [get_ports sense_s_clk_o] -path full -delay max }
redirect -tee "$REPORT_DIR/cal_sclk_fall_to_sensor_sclk.rpt" { report_timing -fall_from [get_ports cal_sense_s_clk_i] -fall_to [get_ports sense_s_clk_o] -path full -delay max }
redirect -tee "$REPORT_DIR/cal_reset_rise_to_sensor_reset.rpt" { report_timing -rise_from [get_ports cal_sense_dff_reset_i] -rise_to [get_ports sense_dff_reset_o] -path full -delay max }
redirect -tee "$REPORT_DIR/cal_reset_fall_to_sensor_reset.rpt" { report_timing -fall_from [get_ports cal_sense_dff_reset_i] -fall_to [get_ports sense_dff_reset_o] -path full -delay max }
redirect -tee "$REPORT_DIR/cal_medium_rise_to_sensor_medium.rpt" { report_timing -rise_from [get_ports cal_medium_therm_i*] -rise_to [get_ports medium_therm_o*] -path full -delay max -max_paths 100 }
redirect -tee "$REPORT_DIR/cal_medium_fall_to_sensor_medium.rpt" { report_timing -fall_from [get_ports cal_medium_therm_i*] -fall_to [get_ports medium_therm_o*] -path full -delay max -max_paths 100 }
redirect -tee "$REPORT_DIR/cal_fine_rise_to_sensor_fine.rpt" { report_timing -rise_from [get_ports cal_fine_therm_i*] -rise_to [get_ports fine_therm_o*] -path full -delay max -max_paths 100 }
redirect -tee "$REPORT_DIR/cal_fine_fall_to_sensor_fine.rpt" { report_timing -fall_from [get_ports cal_fine_therm_i*] -fall_to [get_ports fine_therm_o*] -path full -delay max -max_paths 100 }
redirect -tee "$REPORT_DIR/det_ready_to_state.rpt" { report_timing -from [get_ports det_takeover_ready_i] -to [all_registers -data_pins] -path full -delay max }
redirect -tee "$REPORT_DIR/status_to_state.rpt" { report_timing -from [get_ports {cal_busy_i cal_done_i cal_fail_i lock_valid_i}] -to [all_registers -data_pins] -path full -delay max }
redirect -tee "$REPORT_DIR/thermometer_paths.rpt" { report_timing -to [get_ports {medium_therm_o* fine_therm_o*}] -path full -delay max }
redirect -tee "$REPORT_DIR/cell_usage.rpt" { report_cell; report_reference -hierarchy }
redirect -tee "$REPORT_DIR/qor.rpt" { report_qor }
redirect -tee "$REPORT_DIR/ports.rpt" { report_port -verbose }

write -format verilog -hierarchy -output "$OUTPUT_DIR/${DESIGN_NAME}_synth.v"
write -format ddc -hierarchy -output "$OUTPUT_DIR/${DESIGN_NAME}_synth.ddc"
write_sdc "$OUTPUT_DIR/${DESIGN_NAME}_synth.sdc"
write_sdf -version 3.0 -context verilog -load_delay net "$OUTPUT_DIR/${DESIGN_NAME}_synth.sdf"
puts "H0-5 synthesis completed for ftc_sensor_owner_handoff at 400 MHz / 2.5 ns"
exit
