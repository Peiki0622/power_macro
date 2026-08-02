# Reproducible Design Compiler synthesis for one CNN MAC-lane/clock point.
# All paths and design choices enter through environment variables supplied by
# run_dc_sweep.sh; every generated database and report stays in RUN_DIR.

set run_dir       $env(RUN_DIR)
set cnn_root      $env(CNN_ROOT)
set mac_lanes     $env(MAC_LANES)
set clock_period  $env(CLOCK_PERIOD_NS)
set target_db     $env(TARGET_LIBRARY)
set rom_db        $env(ROM_DB)

file mkdir $run_dir
# Build the search-directory list as a complete Tcl value before concatenating
# it with the existing application search path.  Keeping both file dirname
# commands on one logical list expression prevents Tcl from interpreting the
# second directory as a command when this script is read non-interactively.
set synthesis_search_dirs [list [file dirname $target_db] [file dirname $rom_db]]
set_app_var search_path [concat $synthesis_search_dirs $search_path]
set_app_var target_library [list $target_db]
set_app_var link_library [list "*" $target_db $rom_db dw_foundation.sldb]

# Analyze only synthesizable RTL.  Generated constants are source-level case
# ROMs, so synthesis has no run-directory-dependent memory initialization file.
set rtl_sources [list \
    "$cnn_root/rtl/generated/cnn_parameter_roms.sv" \
    "$cnn_root/rtl/cnn_requantize_relu.sv" \
    "$cnn_root/rtl/cnn_weight_rom.sv" \
    "$cnn_root/rtl/cnn_window_buffer.sv" \
    "$cnn_root/rtl/cnn_convolution_engine.sv" \
    "$cnn_root/rtl/cnn_pool_classifier.sv" \
    "$cnn_root/rtl/cnn_monitor.sv"]

define_design_lib WORK -path "$run_dir/work"
analyze -format sverilog -library WORK $rtl_sources
elaborate cnn_monitor -library WORK -parameters "MAC_LANES=$mac_lanes"
# Parameterized elaboration renames the current design to
# cnn_monitor_MAC_LANES<N>.  Elaborate already selects that object, so retaining
# the current selection avoids a false UID-109 lookup for the unparameterized name.
link
uniquify

# The synchronous compiler memory is a characterized hard macro.  Preserve the
# linked library instance as one physical cell; allowing boundary optimization
# or ungrouping here could invalidate both its Liberty timing and LEF/GDS
# correspondence even if the logical output happened to remain equivalent.
set rom_instances [get_cells -hierarchical -filter "ref_name == CNNW384X128"]
if {[sizeof_collection $rom_instances] != 1} {
    echo "FATAL: expected exactly one CNNW384X128 instance after link"
    exit 3
}
set_dont_touch $rom_instances

# Save precompile diagnostics separately so unresolved references, inferred
# latches, multiply-driven nets, and width issues remain auditable even if a
# later optimization command fails.
redirect "$run_dir/check_design_precompile.rpt" {check_design -summary}
redirect "$run_dir/compile_options.rpt" {
    echo "MAC_LANES=$mac_lanes"
    echo "CLOCK_PERIOD_NS=$clock_period"
    echo "TARGET_LIBRARY=$target_db"
    echo "ROM_DB=$rom_db"
    report_design
}

create_clock -name clk -period $clock_period [get_ports clk]
set clock_uncertainty [expr {$clock_period * 0.05}]
set interface_delay [expr {$clock_period * 0.10}]
set_clock_uncertainty $clock_uncertainty [get_clocks clk]
set_input_delay $interface_delay -clock clk \
    [remove_from_collection [all_inputs] [get_ports {clk reset}]]
set_output_delay $interface_delay -clock clk [all_outputs]
set_input_transition [expr {$clock_period * 0.05}] \
    [remove_from_collection [all_inputs] [get_ports {clk reset}]]
set_load 0.02 [all_outputs]
set_false_path -from [get_ports reset]
# Reset is an asynchronous architectural control, not a data path to optimize
# or a reset tree to synthesize during logic mapping.  Marking the primary reset
# network ideal preserves every asynchronous reset pin while leaving reset-tree
# construction to the physical implementation flow.
set_ideal_network [get_ports reset]
set_max_fanout 32 [current_design]

# Standard constrained DC mapping is deliberate here.  Packed parameter words
# and static feature-register write enables keep the release network bounded;
# ordinary medium timing/area effort can therefore optimize the real SMIC40LL
# gate netlist without compile_ultra's cross-hierarchy transformations.  No
# retiming is requested, preserving the verified fixed controller schedule and
# every pipeline register boundary exercised by the cycle-exact VCS regression.
compile -map_effort medium -area_effort medium

redirect "$run_dir/check_design_postcompile.rpt" {check_design -summary}
redirect "$run_dir/check_timing.rpt" {check_timing}
redirect "$run_dir/clocks.rpt" {report_clock}
redirect "$run_dir/qor.rpt" {report_qor}
redirect "$run_dir/area.rpt" {report_area -hierarchy}
redirect "$run_dir/cell.rpt" {report_cell}
redirect "$run_dir/reference.rpt" {report_reference -hierarchy}
redirect "$run_dir/resources.rpt" {report_resources}
redirect "$run_dir/timing_setup.rpt" {
    report_timing -delay_type max -max_paths 10 -nworst 2 \
        -transition_time -capacitance -nets
}
redirect "$run_dir/constraint_violators.rpt" {report_constraint -all_violators}
redirect "$run_dir/unconstrained_paths.rpt" {
    report_timing -from [all_registers -clock_pins] -to [all_registers -data_pins] \
        -max_paths 10 -nworst 1
}

# This is explicitly vectorless power.  Primary data/control inputs receive a
# neutral 0.5 probability and 0.1 toggles/clock; the clock retains tool clock
# semantics.  Activity-annotated power is a later step and is reported only if
# annotation coverage meets the configured 90 percent gate.
set_switching_activity -static_probability 0.5 -toggle_rate 0.1 \
    [remove_from_collection [all_inputs] [get_ports {clk reset}]]
redirect "$run_dir/power_vectorless.rpt" {report_power -hierarchy}

change_names -rules verilog -hierarchy
write -format ddc -hierarchy -output "$run_dir/cnn_monitor_mapped.ddc"
write -format verilog -hierarchy -output "$run_dir/cnn_monitor_mapped.v"
write_sdc "$run_dir/cnn_monitor_mapped.sdc"
write_sdf "$run_dir/cnn_monitor_mapped.sdf"

quit
