# Read-only Design Compiler query for RF2 SMIC40LL sequential timing evidence.
#
# This Tcl file intentionally does not read RTL, elaborate a design, compile,
# or write a mapped netlist.  It opens the exact SS 0.99 V / 125 C database
# used by the historical synthesis flow and prints the relevant sequential
# cell attributes.  The surrounding shell command redirects stdout to a
# task-owned ``.txt`` artifact for later JSON normalization.

# Keep the library path explicit so a host default library cannot silently
# substitute another SMIC corner or a different standard-cell family.
set target_library [list \
    /home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/db/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db]
set link_library "* $target_library"

# These are the exact current mapping classes plus the drive-strength variants
# that DC can plausibly substitute while preserving the reset/set interface.
set rf2_cells [list \
    DFFRPQ_X0P5M_A9TR40 DFFRPQ_X1M_A9TR40 DFFRPQ_X2M_A9TR40 DFFRPQ_X3M_A9TR40 \
    DFFRPQN_X0P5M_A9TR40 DFFRPQN_X1M_A9TR40 DFFRPQN_X2M_A9TR40 DFFRPQN_X3M_A9TR40 \
    DFFSRPQ_X0P5M_A9TR40 DFFSRPQ_X1M_A9TR40 DFFSRPQ_X2M_A9TR40 DFFSRPQ_X3M_A9TR40]

puts "RF2_LIBRARY_QUERY_BEGIN"
foreach cell $rf2_cells {
    # A missing cell is itself evidence and is reported rather than hidden.
    set cell_object [get_lib_cells -quiet */$cell]
    if {[sizeof_collection $cell_object] == 0} {
        puts "RF2_CELL_MISSING $cell"
    } else {
        puts "RF2_CELL_BEGIN $cell"
        # In the installed Q-2019.12 DC release ``report_lib`` accepts the
        # resolved library-cell collection as its positional object.  This
        # prints timing arcs, pin constraints and minimum pulse-width data
        # without reading RTL or performing a synthesis implementation.
        report_lib $cell_object
        puts "RF2_CELL_END $cell"
    }
}
puts "RF2_LIBRARY_QUERY_END"
quit
