# Stage 2A Synthesis Evidence

Status: PASS

## Method

Design Compiler W-2024.09 was run from a fresh task directory using
`delay_chain/phase2_vernier/scripts/dc_stage2a_synthesis.tcl`.  The complete
macro was elaborated with the physical frontend hierarchy protected and
reported separately.  The pure digital backend was then elaborated as an
independent synthesis top and compiled normally with a 10 ns backend clock.
No STA optimization was applied to Vernier delay-comparison paths.

Run directory: `/tmp/vernier_stage2a_dc_signoff.pergR3rz`

## Results

- Physical frontend area: `266.212799` library area units.
- Digital backend mapped area: `1074.187800` library area units.
- Total macro area (reported sum): `1340.400599` library area units.
- Backend: 618 cells (584 combinational, 33 sequential), 0 macros/black boxes.
- Backend timing: 10 ns clock, critical path slack `9.59 ns`, TNS `0.00 ns`.
- Backend reference report contains only mapped SMIC40LL cells and one mapped DesignWare adder; no GTECH reference remains in the backend report.

The physical hierarchy/reference reports retain the sense/reference wrappers,
all 32 comparator wrappers, and the launch calibration structure.  The only
top-level unmapped notices belong to intentionally protected physical/top
boundary logic and are not part of the standalone backend mapping result.
