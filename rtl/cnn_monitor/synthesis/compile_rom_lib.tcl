# Convert the generated SMIC40LL ROM Liberty view to a Synopsys .db.
#
# Environment variables are supplied by run_smic40ll_rom_lib.sh so this Tcl is
# independent of the caller's current directory and never writes tool products
# beside checked-in source files.

set rom_liberty $env(ROM_LIBERTY)
set rom_db      $env(ROM_DB)
set rom_library $env(ROM_LIBRARY_NAME)

read_lib $rom_liberty
write_lib $rom_library -output $rom_db
redirect $env(ROM_LC_REPORT) {report_lib $rom_library}
quit
