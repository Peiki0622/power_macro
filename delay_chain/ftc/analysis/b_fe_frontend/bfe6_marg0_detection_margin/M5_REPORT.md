# B-FE6-MARG0 M5 ARCH0 RTL replay

Gate: `BFE6_MARG0_M5_RTL_REPLAY_PASS`

The replay used the frozen public `bfe_backend_top` interface and the retained
30-bit q_ff vectors for CALN0 seeds 41001 and 41002.  Each epoch consumed four
RISE and four FALL calibration samples, verified `CAL_LOCK` and the expected
references, then sent overlapping one-event-per-probe-clock detection parcels.

The checks covered healthy and droop vectors, 0.92/0.89/0.86 V representative
responses, reverse-direction FALL movement, alternating RISE/FALL polarity,
`D_M == margin` quiet behavior, `D_M == margin+1` alarm behavior, E7 alarm
alignment, and E8 sticky assertion.  Both epochs matched the strict offline
rule `D_M > margin`; no production RTL was changed.

This is a captured-vector RTL replay, not a new HSPICE run, physical signoff,
PVT claim, or universal operating-range result.
