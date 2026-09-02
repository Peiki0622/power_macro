# BFE13 TRACK0 P3 Directed RTL Report

Gate: `BFE13_TRACK0_P3_DIRECTED_RTL_PASS`

One VCS W-2024.09_Full64 regression exercised both the candidate controller
with deterministic `M_FF` values and the candidate full top with the unchanged
capture/feature pipeline.  The local nonzero parameters were explicitly
`DIRECTED_TEST_ONLY` and are not production selections.

The regression passed exact four-sample RISE/FALL calibration, immutable
startup/security anchors, zero-parameter disable intent, independent two-bit
RISE/FALL persistence FSMs, direction reversal, zero/HOLD behavior, saturated
upper/lower bounds, and one-LSB update limits.  ABS and signed-only RISE
alarms blocked the current update; sticky then froze autonomous movement until
reset.  After a real track-reference move, ABS used the moved reference while
the signed trip remained on the startup anchor.  Back-to-back old snapshots
were rejected as stale, demonstrating no E8-to-E4 bypass.

The full-top checks preserved the seven-probe-edge E0-to-E7 alarm boundary;
tracker commit is observed only at E8.  Six compile/harness or directed
expectation retries were recorded, with identical scientific stimulus after
each correction.

No physical simulation, threshold sweep, synthesis, timing signoff, or source
rewrite was performed in P3.
