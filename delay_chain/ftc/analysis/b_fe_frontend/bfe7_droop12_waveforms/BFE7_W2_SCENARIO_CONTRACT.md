# B-FE7 W2 Scenario Contract

`DROOP12_SCENARIOS.csv` and `DROOP12_WAVEFORM_CONTRACT.json` freeze exactly
twelve representative elemental attack envelopes.  Each envelope is a list
of explicit finite-slope `(time_ps, attack_depth_v)` points.  The final rail
will be formed only as `1.10 V + NBG_7301 noise - attack_depth`.

The source port remains `V_VDD_MONITORED vdd_monitored vss_a`; attack records
do not alter clocks, capture gates, reset, or circuit parameters.  D09 uses
the confirmed edge-after-start interpretation: each 10 ps ramp begins at its
21/31/41/51 ns marker and reaches the next cumulative depth at marker+10 ps.

The contract is marked `frozen=true` only after the twelve-ID, monotonic-time,
canonical-frame and finite-slope assertions pass.  No detector result was
consulted and no simulator was called.
