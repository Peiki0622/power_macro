# Bounded low-effort structural probe for the release 16-lane CNN.
#
# This entry point deliberately uses the same RTL, SMIC40LL TT standard-cell
# library, compiled ROM DB, clock, and interface constraints as the release
# synthesis.  It stops after low-effort mapping and structural reports so an
# accidental multiplier, decoder, reset tree, or register-array explosion is
# detected before a long medium-effort optimization run is allowed to start.

set run_dir       $env(RUN_DIR)
set cnn_root      $env(CNN_ROOT)
set mac_lanes     $env(MAC_LANES)
set clock_period  $env(CLOCK_PERIOD_NS)
set target_db     $env(TARGET_LIBRARY)
set rom_db        $env(ROM_DB)

file mkdir $run_dir
set probe_search_dirs [list [file dirname $target_db] [file dirname $rom_db]]
set_app_var search_path [concat $probe_search_dirs $search_path]
set_app_var target_library [list $target_db]
set_app_var link_library [list "*" $target_db $rom_db dw_foundation.sldb]

# Only synthesizable sources are analyzed.  The compiled weight macro is linked
# from ROM_DB; no behavioral memory or simulation model enters this flow.
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
link
uniquify

# Exactly one characterized ROM cell must survive link.  Preserving that cell
# also keeps the probe's leaf/reference counts from accidentally describing a
# synthesized behavioral replacement.
set rom_instances [get_cells -hierarchical -filter "ref_name == CNNW384X128"]
if {[sizeof_collection $rom_instances] != 1} {
    echo "FATAL: expected exactly one CNNW384X128 instance after link"
    exit 3
}
set_dont_touch $rom_instances

redirect "$run_dir/check_design_precompile.rpt" {check_design -summary}
redirect "$run_dir/reference_precompile.rpt" {report_reference -hierarchy}
redirect "$run_dir/resources_precompile.rpt" {report_resources}

# W-2024.09 removed compile's historical low map effort; requesting low silently
# runs medium timing optimization and caused a structure-only probe to spend the
# entire watchdog window repairing 2 ns paths.  Map the generic network before
# optimization constraints are installed and explicitly skip area recovery and
# design-rule repair.  This still produces real SMIC40LL cells, maps all 16+2
# arithmetic operators, and preserves the hard ROM, which is exactly the data
# needed by this structural gate.  It is intentionally not the timing-closure
# run: the release constraints are applied immediately after mapping so the
# reports show an honest unoptimized 500 MHz reference, while dc_synthesize.tcl
# performs the full constrained optimization in the following plan step.
compile -map_effort medium -area_effort none -no_design_rule

# Apply the same 500 MHz release interface contract after structural mapping.
# Reset remains architecturally asynchronous but is ideal for timing analysis,
# so reported paths describe the datapath rather than an artificial reset tree.
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
set_ideal_network [get_ports reset]
set_max_fanout 32 [current_design]

redirect "$run_dir/check_design_postcompile.rpt" {check_design -summary}
redirect "$run_dir/qor.rpt" {report_qor}
redirect "$run_dir/area.rpt" {report_area -hierarchy}
redirect "$run_dir/cell.rpt" {report_cell}
redirect "$run_dir/reference.rpt" {report_reference -hierarchy}
redirect "$run_dir/resources.rpt" {report_resources}
redirect "$run_dir/timing_setup.rpt" {
    report_timing -delay_type max -max_paths 10 -nworst 2
}
quit
