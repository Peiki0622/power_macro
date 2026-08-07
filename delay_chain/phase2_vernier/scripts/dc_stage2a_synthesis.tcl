# Minimal Design Compiler check for the Stage 2A macro boundary.
#
# The physical frontend is deliberately protected as a structural region.  The
# digital backend is still read as ordinary synthesizable RTL so its area and
# hierarchy can be reported separately.  All run products are written under the
# caller-provided RUN_DIR, never beside the RTL sources.

set run_dir    $env(RUN_DIR)
set target_db  $env(TARGET_LIBRARY)
set rtl_root   $env(RTL_ROOT)

file mkdir $run_dir
set_app_var search_path [list [file dirname $target_db]]
set_app_var target_library [list $target_db]
set_app_var link_library [list "*" $target_db dw_foundation.sldb]
# Arithmetic inferred by the normal digital decoder is implemented by
# DesignWare during elaboration.  Declaring this as the synthetic library, not
# merely a link library, authorizes DC to expand it into target-library gates;
# the protected physical frontend remains outside that optimization region.
set_app_var synthetic_library [list dw_foundation.sldb]

define_design_lib WORK -path "$run_dir/work"

set rtl_sources [list     "$rtl_root/vernier_sensor_calibration_pkg.sv"     "$rtl_root/vernier_sensor_digital_backend.sv"     "$rtl_root/vernier_sense_stage_struct.sv"     "$rtl_root/vernier_reference_stage_struct.sv"     "$rtl_root/vernier_comparator_struct.sv"     "$rtl_root/vernier_launch_cal_struct.sv"     "$rtl_root/vernier_frontend_struct.sv"     "$rtl_root/vernier_sample_adapter.sv"     "$rtl_root/vernier_sensor.sv"]

analyze -format sverilog -library WORK $rtl_sources
elaborate vernier_sensor -library WORK
link
uniquify

# Preserve the complete physical frontend hierarchy before compilation.  The
# backend is intentionally left outside this collection so normal synthesis can
# optimize its decoder logic.
set physical_cells [get_cells -hierarchical *u_frontend*]
if {[sizeof_collection $physical_cells] == 0} {
    echo "FATAL: structural frontend instance was not found after link"
    exit 2
}
set_dont_touch $physical_cells
set_ungroup $physical_cells false

# No normal STA constraint is applied to the Vernier delay comparison paths.
# The only clock constraint is a deliberately loose digital-backend synthesis
# clock on clk_i.  It is not connected to the physical frontend's asynchronous
# launch/comparison path and is not a macro timing claim; HSPICE remains the
# sole source of Vernier delay evidence.  The clock simply lets DC map the
# backend's registers and arithmetic into target-library cells for area audit.
# The full macro is deliberately not compiled as one logic cone.  Its retained
# power-pin structural frontend contains asynchronous cell arcs that must stay
# electrically intact; compiling it together with the decoder can cause DC to
# skip decoder mapping.  These reports are therefore the physical-region proof.
redirect "$run_dir/physical_check_design.rpt" {check_design -summary}
redirect "$run_dir/physical_hierarchy.rpt" {report_hierarchy}
redirect "$run_dir/physical_area.rpt" {report_area -hierarchy}
redirect "$run_dir/physical_cell.rpt" {report_cell}
redirect "$run_dir/physical_reference.rpt" {report_reference -hierarchy}

# Re-elaborate only the wholly digital decoder as a synthesis top.  This is the
# same default M=32/CODE_WIDTH=6 specialization instantiated by vernier_sensor,
# but it has no physical inout rails or protected delay arcs.  Normal mapping is
# consequently allowed here, exactly as required for the backend region.
elaborate vernier_sensor_digital_backend -library WORK
link
create_clock -name backend_clk -period 10.000 [get_ports clk]
set_false_path -from [get_ports sensor_reset]
redirect "$run_dir/backend_check_design.rpt" {check_design -summary}
compile -map_effort medium -area_effort medium
redirect "$run_dir/backend_check_design_postcompile.rpt" {check_design -summary}
redirect "$run_dir/backend_area.rpt" {report_area -hierarchy}
redirect "$run_dir/backend_cell.rpt" {report_cell}
redirect "$run_dir/backend_reference.rpt" {report_reference -hierarchy}
redirect "$run_dir/backend_qor.rpt" {report_qor}

# The two regions are intentionally synthesized with different policies.  DC
# does not expose a portable area attribute on hierarchical cells/designs, so
# the two authoritative report_area outputs are retained separately and their
# scalar sum is recorded in the Stage 2A synthesis Markdown report.  This avoids
# tool-version-specific parsing or a misleading unified timing optimization.
redirect "$run_dir/synthesis_summary.rpt" {
    echo "physical_frontend_area_source=physical_area.rpt (u_frontend hierarchy)"
    echo "backend_area_source=backend_area.rpt (mapped decoder top)"
    echo "total_macro_area_method=physical_frontend_area + backend_area"
}

# Keep the fully mapped backend for digital integration.  The structural macro
# hierarchy is retained in the physical reports above and is verified by the
# top-level VCS elaboration rather than being flattened into this netlist.
write -format ddc -hierarchy -output "$run_dir/vernier_sensor_digital_backend_stage2a_mapped.ddc"
write -format verilog -hierarchy -output "$run_dir/vernier_sensor_digital_backend_stage2a_mapped.v"

quit
