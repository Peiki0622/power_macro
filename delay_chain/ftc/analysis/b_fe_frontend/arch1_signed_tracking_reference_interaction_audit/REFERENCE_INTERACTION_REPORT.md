# ARCH1 Signed Tracking Reference-Interaction Audit

Gate: `ARCH1_SIGNED_TRACKING_REFERENCE_INTERACTION_AUDIT_FROZEN`

This is a retained-data-only offline audit.  It reads BFE8/BFE9/BFE11/BFE12 artifacts and evaluates the signed comparator branch only; it does not rerun or alter the absolute comparator.

## Scope and formula

The audit uses 360 healthy RISE samples, 30 D01 targets, 30 D02 targets, and 30 D04 targets.  For a hypothetical `DeltaR=M_REF_TRACK-M_REF_STARTUP`, it applies `e_track=e_startup-DeltaR` and strict `e>T_POS_RISE` at 18 and 19.  The common retained 9-bit reference-code range is `[-153, 200]` because startup references span 153..235.

The safe interval criterion is zero healthy positive false alarms plus 30/30 signed detection for D01, D02, and D04.  Intervals below are inclusive integer DeltaR values; strict-comparator continuous bounds are stated separately.

## Policy comparison

| Policy | T | Integer safe DeltaR | Continuous interpretation | Weakest attack headroom at DeltaR=0 |
|---|---:|---|---|---:|
| A_TRACK_SOURCE | 18 | [0, 1] | [0, 2) | 2 |
| A_TRACK_SOURCE | 19 | [-1, 0] | [-1, 1) | 1 |
| B_STARTUP_ANCHOR_SOURCE | 18 | [-153, 200] | [-153, 200] (representability bound) | 2 |
| B_STARTUP_ANCHOR_SOURCE | 19 | [-153, 200] | [-153, 200] (representability bound) | 1 |
| C_TRACK_WITH_THRESHOLD_COMPENSATION | 18 | [-153, 18] | [-153, 18] (threshold-code bound) | 2 |
| C_TRACK_WITH_THRESHOLD_COMPENSATION | 19 | [-153, 19] | [-153, 19] (threshold-code bound) | 1 |

## Baseline and headroom

At DeltaR=0, the weakest signed headroom is D01/D04 `+2` M-codes at T=18 and `+1` M-code at T=19; D02 is `+23` and `+22` respectively.  Under policy A, every additional reference displacement subtracts directly from these headrooms.  Under B and exact C compensation, they remain unchanged.

Policy A therefore has only `[0,1]` integer safety at T=18 and `[-1,0]` at T=19.  Positive displacement beyond that loses the weakest D01/D04 detections; negative displacement eventually creates healthy positive false alarms.

Policy B keeps the signed comparator on the startup/trusted anchor, so all retained metrics are invariant over the common representable range `[-153,200]`.

Policy C uses `T_comp=T_POS_RISE-DeltaR`; it is algebraically equivalent to B, but its practical interval is limited by the 9-bit threshold range to `[-153,18]` at T=18 and `[-153,19]` at T=19.

## Evidence conclusion

Policy B is the strongest candidate for the next TRACK0 RTL stage: it preserves the frozen signed-error separation without making the signed threshold track mutable reference state and without adding threshold-compensation arithmetic.  Policy C is a valid offline control but should remain a fallback comparison because exact compensation, threshold encoding, and saturation behavior would become new RTL contracts.  Policy A should not be the default signed-comparator source because its retained-population safe interval is narrow.

No new T_POS was selected.  No tracker, waveform, process population, frontend, production ARCH0 RTL, SIGN0 RTL, or physical simulation was modified or executed.

Artifacts: `REFERENCE_INTERACTION_SWEEP.csv`, `REFERENCE_INTERACTION_SUMMARY.json`, and `REFERENCE_INTERACTION_RUN_LEDGER.json`.
