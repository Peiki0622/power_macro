# Independently prove that the stable Design Compiler wrapper can read the ROM
# database and resolve the expected hard macro cell before RTL integration.

set rom_db      $env(ROM_DB)
set rom_library $env(ROM_LIBRARY_NAME)

read_db $rom_db
redirect $env(ROM_DC_LIBRARY_REPORT) {report_lib $rom_library}
set macro_cells [get_lib_cells -quiet "${rom_library}/CNNW384X128"]
if {[sizeof_collection $macro_cells] != 1} {
    echo "ERROR: expected exactly one CNNW384X128 library cell"
    exit 2
}
# This DC release has no report_lib_cell command.  Recording the single object
# returned by get_lib_cells is the version-independent proof that read_db
# resolved the generated macro rather than a similarly named RTL module.
redirect $env(ROM_DC_CELL_REPORT) {echo [get_object_name $macro_cells]}
quit
