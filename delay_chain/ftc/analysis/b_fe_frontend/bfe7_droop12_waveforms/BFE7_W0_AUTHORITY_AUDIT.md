# B-FE7 W0 Authority Audit

The BFE7 stimulus package uses the frozen SMIC40LL TT, 25 C, 1.10 V
configuration and the finite-slope PWL semantics retained by the FTC T0
contract.  The machine-readable audit in `BFE7_W0_AUTHORITY_AUDIT.json`
contains the SHA256 values used to detect source drift.

The monitored supply port is deliberately limited to one source,
`V_VDD_MONITORED vdd_monitored vss_a`.  The BFE1 implementation establishes
this node/return naming; no detector, sensor, latch, DFF, clock, or backend
is part of a BFE7 waveform include.

The time frame is 0--65 ns with reference markers at 21, 31, 41, and 51 ns.
The RISE/FALL labels are construction markers only.  Previous BFE3/BFE4/BFE6
reports are retained solely for timing/provenance reuse and were not rerun.

This gate records an offline authority freeze.  It does not imply that any
waveform has yet been generated or that a detector result has been measured.
