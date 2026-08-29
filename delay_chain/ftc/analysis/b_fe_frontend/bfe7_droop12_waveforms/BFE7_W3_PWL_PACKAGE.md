# B-FE7 W3 HSPICE PWL Package

The generator consumed only the frozen W2 contract and shared `NBG_7301.csv`.
For each scenario it merged background knots with explicit attack breakpoints,
evaluated the background at every inserted point, and wrote a compact exact
piecewise-linear representation.

Each `.inc` has one and only one source with the modular port map
`V_VDD_MONITORED vdd_monitored vss_a`: `vdd_monitored` is the positive
monitored-domain rail and `vss_a` is its local return.  No clock, detector,
sensor, LATQ, DFF, backend, ARCH0, or ARCH1 logic is emitted.

The package was checked offline.  HSPICE/VCS/DC/PrimeSim invocation count
remains zero.
