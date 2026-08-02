# Activity-annotated TT power estimate for one task-three RTL VCD/SAIF pair.
#
# This Tcl consumes the frozen release DDC rather than recompiling RTL.  The
# caller must provide a task-scoped SAIF and output report path through the
# environment.  Four-nanosecond simulation activity is intentional because the
# delivered ROM model has that verified functional period; consumers may scale
# only the dynamic component when presenting a 500 MHz projection.

set ddc_path $env(CNN_ACTIVITY_DDC)
set saif_path $env(CNN_ACTIVITY_SAIF)
set report_path $env(CNN_ACTIVITY_REPORT)
set target_db $env(CNN_ACTIVITY_TARGET_DB)
set rom_db $env(CNN_ACTIVITY_ROM_DB)

set_app_var search_path [concat [list [file dirname $target_db] [file dirname $rom_db]] $search_path]
set_app_var target_library [list $target_db]
set_app_var link_library [list "*" $target_db $rom_db]
read_ddc $ddc_path
current_design cnn_monitor_MAC_LANES16
link

# Override the 2 ns synthesis clock only for this measurement session.  SAIF
# toggle rates came from the known-good 4 ns compiler-ROM simulation, so using
# a matching clock prevents a false claim that the VCD itself ran at 500 MHz.
remove_clock [get_clocks clk]
create_clock -name activity_clk -period 4.000 [get_ports clk]
read_saif -input $saif_path -instance_name cnn_activity_tb/dut -auto_map_names -verbose
redirect $report_path {report_power -hierarchy}
quit
