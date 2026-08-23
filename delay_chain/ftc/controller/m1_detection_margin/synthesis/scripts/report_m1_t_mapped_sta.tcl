# ============================================================================
# M1-T report-only mapped STA and path-classification evidence
# ============================================================================
# This script intentionally reads the committed M1 mapped Verilog and emitted
# SDC instead of elaborating RTL or running compile.  Its sole purpose is to
# make the existing 400 MHz timing numbers independently reproducible and to
# separate interface budgets from the M1 combinational/register timing cone.
#
# Frozen H0, all six frozen calibration RTL files, FTC_SENSOR, M0/M0-E data,
# and all transistor or mixed-signal flows are absent by construction.  There
# is no analyze, elaborate, compile, write, HSPICE, XA, RF, or calibration
# command in this driver.
# ============================================================================

set SCRIPT_DIR [file dirname [file normalize [info script]]]
set M1_ROOT [file normalize [file join $SCRIPT_DIR ../..]]
set NETLIST_DIR "$M1_ROOT/synthesis/netlist"
set REPORT_DIR "$M1_ROOT/synthesis/reports"
set NETLIST "$NETLIST_DIR/ftc_detection_margin_manager_synth.v"
set SDC "$NETLIST_DIR/ftc_detection_margin_manager_synth.sdc"
set DESIGN_NAME "ftc_detection_margin_manager"

# Reuse the exact normal SMIC40LL RVT controller corner used for the committed
# M1 synthesis.  No alternate PVT, wire model, voltage, frequency, or timing
# constraint is introduced by M1-T.
set LIB_BASE "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1"
set TARGET_LIBRARY "$LIB_BASE/db/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db"

if {![file readable $NETLIST]} {
    error "M1-T requires committed mapped netlist: $NETLIST"
}
if {![file readable $SDC]} {
    error "M1-T requires committed SDC: $SDC"
}
file mkdir $REPORT_DIR

set_app_var sh_enable_page_mode false
set_app_var target_library $TARGET_LIBRARY
set_app_var link_library "* $TARGET_LIBRARY"
set search_path [concat $search_path "$LIB_BASE/db"]

# Loading the mapped design preserves the exact cell choices that were used by
# the M1 gate/SDF regression.  read_sdc restores the committed external input
# and output delays, clock uncertainty, false paths, and 2.5 ns clock exactly.
read_verilog $NETLIST
current_design $DESIGN_NAME
link
read_sdc $SDC

# Full path reports carry input/output budgets, clock uncertainty, endpoint
# setup/hold times, individual cell arcs, and nets.  They are the primary
# proof source for any number published by M1_T_TIMING_CLASSIFICATION.json.
redirect -tee "$REPORT_DIR/M1_T_GLOBAL_SETUP.rpt" {
    report_timing -path full -delay max -max_paths 50 -nworst 1 \
        -input_pins -nets -transition_time -capacitance -significant_digits 6
}
redirect -tee "$REPORT_DIR/M1_T_GLOBAL_HOLD.rpt" {
    report_timing -path full -delay min -max_paths 50 -nworst 1 \
        -input_pins -nets -transition_time -capacitance -significant_digits 6
}

# Classify all synchronous path families explicitly.  Input-to-register paths
# include SDC input delay; register-to-register paths do not.  Register-to-
# output paths include SDC output delay.  This prevents an interface budget
# from being reported as an internal M1 critical path.
redirect -tee "$REPORT_DIR/M1_T_INPUT_TO_REGISTER_SETUP.rpt" {
    report_timing -from [remove_from_collection [all_inputs] [get_ports {cal_clk_i ctrl_por_n_i}]] \
        -to [all_registers -data_pins] -path full -delay max -max_paths 80 -nworst 1 \
        -input_pins -nets -transition_time -capacitance -significant_digits 6
}
redirect -tee "$REPORT_DIR/M1_T_INPUT_TO_REGISTER_HOLD.rpt" {
    report_timing -from [remove_from_collection [all_inputs] [get_ports {cal_clk_i ctrl_por_n_i}]] \
        -to [all_registers -data_pins] -path full -delay min -max_paths 80 -nworst 1 \
        -input_pins -nets -transition_time -capacitance -significant_digits 6
}
redirect -tee "$REPORT_DIR/M1_T_REGISTER_TO_REGISTER_SETUP.rpt" {
    report_timing -from [all_registers -output_pins] -to [all_registers -data_pins] \
        -path full -delay max -max_paths 80 -nworst 1 \
        -input_pins -nets -transition_time -capacitance -significant_digits 6
}
redirect -tee "$REPORT_DIR/M1_T_REGISTER_TO_REGISTER_HOLD.rpt" {
    report_timing -from [all_registers -output_pins] -to [all_registers -data_pins] \
        -path full -delay min -max_paths 80 -nworst 1 \
        -input_pins -nets -transition_time -capacitance -significant_digits 6
}
redirect -tee "$REPORT_DIR/M1_T_REGISTER_TO_OUTPUT_SETUP.rpt" {
    report_timing -from [all_registers -output_pins] -to [all_outputs] \
        -path full -delay max -max_paths 80 -nworst 1 \
        -input_pins -nets -transition_time -capacitance -significant_digits 6
}
redirect -tee "$REPORT_DIR/M1_T_REGISTER_TO_OUTPUT_HOLD.rpt" {
    report_timing -from [all_registers -output_pins] -to [all_outputs] \
        -path full -delay min -max_paths 80 -nworst 1 \
        -input_pins -nets -transition_time -capacitance -significant_digits 6
}

# Define the implementation registers once.  The mapped naming is checked
# explicitly so an optimization or accidental netlist replacement cannot make
# a targeted report silently empty while still producing a DC transcript.
set STATE_D [get_pins -hierarchical "state_q_reg*/D"]
set TARGET_D [get_pins -hierarchical "target_medium_therm_q_reg*/D target_fine_therm_q_reg*/D"]
set TARGET_CONFIG_Q [get_pins -hierarchical "target_medium_therm_q_reg*/Q target_fine_therm_q_reg*/Q state_q_reg*/Q margin_cfg_valid_q_reg/Q"]
set DET_CONTROL_D [get_pins -hierarchical "det_medium_therm_q_reg*/D det_fine_therm_q_reg*/D"]
set DET_CONTROL_Q [get_pins -hierarchical "det_medium_therm_q_reg*/Q det_fine_therm_q_reg*/Q"]
foreach {collection label} [list $STATE_D STATE_D $TARGET_D TARGET_D $TARGET_CONFIG_Q TARGET_CONFIG_Q $DET_CONTROL_D DET_CONTROL_D $DET_CONTROL_Q DET_CONTROL_Q] {
    if {[sizeof_collection $collection] == 0} {
        error "M1-T mapped netlist does not contain expected $label collection"
    }
}

# Targeted family 1: the margin selection/request interface may change mapper
# outputs and manager state.  Both endpoint families are reported separately,
# making the 0.5 ns external input-delay contribution reviewable.
set MARGIN_REQUEST_PORTS [get_ports {margin_sel_i* margin_select_valid_i}]
redirect -tee "$REPORT_DIR/M1_T_MARGIN_SELECTION_TO_STATE_SETUP.rpt" {
    report_timing -from $MARGIN_REQUEST_PORTS -to $STATE_D -path full -delay max \
        -max_paths 40 -nworst 1 -input_pins -nets -transition_time -capacitance -significant_digits 6
}
redirect -tee "$REPORT_DIR/M1_T_MARGIN_SELECTION_TO_TARGET_SETUP.rpt" {
    report_timing -from $MARGIN_REQUEST_PORTS -to $TARGET_D -path full -delay max \
        -max_paths 80 -nworst 1 -input_pins -nets -transition_time -capacitance -significant_digits 6
}

# Targeted family 2: M1's mapper uses the immutable H0 M/F *code* snapshots as
# lookup keys.  Raw thermometer snapshot rails are only preloaded; therefore
# code snapshots, not raw rails, are the correct sources for the codebook-to-
# target-register timing report.
set CAL_CODE_PORTS [get_ports {cal_medium_code_snapshot_i* cal_fine_code_snapshot_i*}]
redirect -tee "$REPORT_DIR/M1_T_CAL_CODE_TO_TARGET_SETUP.rpt" {
    report_timing -from $CAL_CODE_PORTS -to $TARGET_D -path full -delay max \
        -max_paths 80 -nworst 1 -input_pins -nets -transition_time -capacitance -significant_digits 6
}

# Targeted family 3a: private target/configuration registers feed the visible
# detector-control registers only on the registered M_APPLY transition.  This
# is the internal reg-to-reg proof for safe detector vector application.
redirect -tee "$REPORT_DIR/M1_T_TARGET_CONFIG_TO_DET_REGISTER_SETUP.rpt" {
    report_timing -from $TARGET_CONFIG_Q -to $DET_CONTROL_D -path full -delay max \
        -max_paths 80 -nworst 1 -input_pins -nets -transition_time -capacitance -significant_digits 6
}
redirect -tee "$REPORT_DIR/M1_T_TARGET_CONFIG_TO_DET_REGISTER_HOLD.rpt" {
    report_timing -from $TARGET_CONFIG_Q -to $DET_CONTROL_D -path full -delay min \
        -max_paths 80 -nworst 1 -input_pins -nets -transition_time -capacitance -significant_digits 6
}

# Targeted family 3b: configuration registers also have a direct, same-cycle
# view to detector-facing outputs such as det_takeover_ready_o.  Reporting this
# family explicitly satisfies the target/config-register-to-det_* interface
# check and exposes the output-delay budget without pretending that a path
# through a detector flop remains combinational after that register boundary.
set DETECTOR_OUTPUT_PORTS [get_ports {det_medium_therm_o* det_fine_therm_o* det_takeover_ready_o det_sense_dff_reset_o det_sense_s_clk_o}]
redirect -tee "$REPORT_DIR/M1_T_TARGET_CONFIG_TO_DET_OUTPUT_SETUP.rpt" {
    report_timing -from $TARGET_CONFIG_Q -to $DETECTOR_OUTPUT_PORTS -path full -delay max \
        -max_paths 80 -nworst 1 -input_pins -nets -transition_time -capacitance -significant_digits 6
}
redirect -tee "$REPORT_DIR/M1_T_TARGET_CONFIG_TO_DET_OUTPUT_HOLD.rpt" {
    report_timing -from $TARGET_CONFIG_Q -to $DETECTOR_OUTPUT_PORTS -path full -delay min \
        -max_paths 80 -nworst 1 -input_pins -nets -transition_time -capacitance -significant_digits 6
}

# Targeted family 3c: det_* output timing starts at the visible detector
# registers and includes the explicit output-delay budget consumed by H0.  It
# is deliberately separate from families 3a/3b so a port budget is never
# conflated with the target/configuration-to-detector-register path.
redirect -tee "$REPORT_DIR/M1_T_DET_REGISTER_TO_OUTPUT_SETUP.rpt" {
    report_timing -from $DET_CONTROL_Q -to $DETECTOR_OUTPUT_PORTS \
        -path full -delay max -max_paths 80 -nworst 1 \
        -input_pins -nets -transition_time -capacitance -significant_digits 6
}
redirect -tee "$REPORT_DIR/M1_T_DET_REGISTER_TO_OUTPUT_HOLD.rpt" {
    report_timing -from $DET_CONTROL_Q -to $DETECTOR_OUTPUT_PORTS \
        -path full -delay min -max_paths 80 -nworst 1 \
        -input_pins -nets -transition_time -capacitance -significant_digits 6
}

# Preserve the exact interface assumptions adjacent to the path reports.  This
# report records all external input/output delays, the 0.05/0.02 ns setup/hold
# clock uncertainty, and the 2.5 ns clock without relying on a narrative.
redirect -tee "$REPORT_DIR/M1_T_CONSTRAINTS_AND_CLOCK.rpt" {
    report_clock -skew -attribute
    report_port -verbose [get_ports {margin_sel_i* margin_select_valid_i cal_medium_code_snapshot_i* cal_fine_code_snapshot_i* det_medium_therm_o* det_fine_therm_o* det_takeover_ready_o det_sense_dff_reset_o det_sense_s_clk_o}]
    report_constraint -all_violators
}
redirect -tee "$REPORT_DIR/M1_T_REPORT_ONLY_MANIFEST.rpt" {
    report_design
    report_reference -hierarchy
}

puts "M1-T report-only mapped STA completed without synthesis: $DESIGN_NAME"
exit
