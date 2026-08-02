# Macro-aware synthesis gate for the ROM adapter.
#
# This intentionally small top isolates the hard-memory integration contract:
# one CNNW384X128 library cell plus the q_valid response flop.  The full CNN
# synthesis later reuses the same target/link library setup.

set run_dir  $env(ROM_ADAPTER_RUN)
set cnn_root $env(CNN_ROOT)
set rom_db   $env(ROM_DB)
set std_db   $env(STD_DB)

set_app_var search_path [concat [list [file dirname $rom_db]
                                      [file dirname $std_db]] $search_path]
set_app_var target_library [list $std_db]
set_app_var link_library [list "*" $std_db $rom_db]

file mkdir $run_dir
define_design_lib WORK -path "$run_dir/work"
analyze -format sverilog -library WORK "$cnn_root/rtl/cnn_weight_rom.sv"
elaborate cnn_weight_rom -library WORK
link
uniquify
redirect "$run_dir/check_design.rpt" {check_design -summary}
create_clock -name clk -period 2.0 [get_ports clk]
set_false_path -from [get_ports reset]
compile -map_effort medium -area_effort medium
redirect "$run_dir/area.rpt" {report_area -hierarchy}
redirect "$run_dir/cell.rpt" {report_cell}
redirect "$run_dir/timing.rpt" {
    report_timing -delay_type max -max_paths 10 -nworst 2
}
change_names -rules verilog -hierarchy
write -format verilog -hierarchy -output "$run_dir/cnn_weight_rom_mapped.v"
quit
