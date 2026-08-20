# FTC Cycle-Quantized Startup Protocol

## Decision

**Cycle-Quantized Startup Protocol = NO-GO**

## First Failing Evidence

The `cycle_path_0p80` scenario passed. The next frozen scenario,
`cycle_path_0p95`, failed at probe 0 and therefore terminated Phase 1B before
the third scenario was run.

The candidate schedule drove S_CLK low at 4.0000 ns and did not reassert the
sensor reset until 5.0000 ns. HSPICE measured the first `dff_ck` rising edge
at 1.6749 ns and a second rising edge at 4.7108 ns. The second edge is caused
by return activity after the intended S_CLK falling transition and occurs
before the reset assertion, so the probe has more than one active CK edge.

All 22 probes in the 0.95 V scenario show the same failed edge-integrity
classification. Their Q double samples and recovery checks passed; this does
not override the required single-edge condition.

## Boundary

No cycle count, sensor component, backoff rule, guard rule, or physical cell
was changed after the failure. No 1.10 V run, timing sweep, or diagnostic
fourth scenario was launched. A separate timing-quantization root-cause plan
is required before restarting this controller plan.
