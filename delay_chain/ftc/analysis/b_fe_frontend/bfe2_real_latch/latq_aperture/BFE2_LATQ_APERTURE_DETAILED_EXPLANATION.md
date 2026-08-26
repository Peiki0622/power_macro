# B-FE2-LATQ-APERTURE detailed execution note

## Scope and frozen conditions

This is a narrow tap29 experiment only. It does not change the normal 0.95 V
source waveform, the 30-tap 4/0 RVT/LVT sensing geometry, the real
`XOR2_X0P5M_A9TL40` observation loading, or the Level-0 restoration rule:

```text
safe_d = 0.95 V when xor > 0.5 * VDD_SENSE; otherwise safe_d = 0 V
```

The real capture cell is `LATQ_X0P5M_A9TR40`; its VDD/VNW rails and the
restored data high are both held at 0.95 V. The gate has one 1 ps falling edge.
The only changing quantity is:

```text
Delta t = G_close - D_crossing
```

The frozen tap29 rising `safe_d` crossing is `D_crossing =
1529.871837153 ps`. The raw source trace and deck hashes are recorded in the
manifest. VCS W-2024.09 and PrimeSim XA W-2024.09 compiled and completed each
of the four retained runs with their co-simulation and XA version markers.

## Point selection

The points are intentionally sparse. CENTER and RIGHT are the existing
evidence anchors, MID is one representative point between them, and
LATE_CAPTURE is deliberately later than the earlier observed tap29 D-to-Q
threshold event (about 32.13 ps) only as an independent capture anchor. That
previous propagation observation is not used to define any aperture boundary.

| Point | Delta t (ps) | G close (ps) | Role |
|---|---:|---:|---|
| CENTER | 4.652781414 | 1534.524618567 | Known safe-reject anchor |
| MID | 15.000000000 | 1544.871837153 | Single interior representative |
| RIGHT | 23.196735917 | 1553.068573070 | Known failure anchor |
| LATE_CAPTURE | 45.000000000 | 1574.871837153 | Clearly late capture anchor |

There is no dense sweep, no HSPICE scenario, no new sensing experiment, and no
self-calibration, M/F, FSM, or detector work.

## Classification rule

The result is driven by the analog Q output of tap29, not by `safe_d`, a
predicted D-to-Q delay, or a direction-global fallback.

- `SAFE_REJECT`: final Q remains old value 0, Q has no post-close re-flip, and
  its final and 1 ns tail samples agree.
- `UNSAFE_APERTURE`: a source-free re-flip, more than one post-close Q event,
  or final mid-rail Q is observed.
- `SAFE_CAPTURE`: final Q is new value 1, Q has no re-flip, and its final and
  1 ns tail samples agree.

Source-backed versus source-free labels are assigned from Q's before/after
state sequence and the retained same-direction source event ledger. They are
diagnostic labels only; no delay maximum is subtracted from a proposed capture
window.

## Retained XA observations

| Point | Q crossing(s) (ps) | Final Q | Classification |
|---|---|---:|---|
| CENTER | none | 0 | `SAFE_REJECT` |
| MID | none | 0 | `SAFE_REJECT` |
| RIGHT | 1562, 1565 | 0 | `UNSAFE_APERTURE` |
| LATE_CAPTURE | 1559 | 1 | `SAFE_CAPTURE` |

RIGHT has a source-backed rising Q threshold crossing at 1562 ps followed by a
source-free falling re-flip at 1565 ps, so it is unsafe even though its final
digital value is old 0. LATE_CAPTURE has one stable Q rise and ends near 0.95
V. These observations establish the ordered evidence sequence:

```text
SAFE_REJECT -> UNSAFE_APERTURE -> SAFE_CAPTURE
```

The evidence supports the existence of ordered regions, not an interpolated
numerical aperture edge. The boundaries remain bracketed by the sparse points.

## Execution corrections

Two generator audits were performed before accepting evidence. The inherited
L1A wrapper defaulted its latch supply to 1.10 V; this was corrected to the
stage-required 0.95 V before the retained runs. A second audit found that the
inherited testbench initialized a signal to its first event state when that
event was rising; this incorrectly made tap29 `safe_d` high at time zero. The
testbench was corrected to initialize every `safe_d` to frozen old value 0,
then the four points were rerun. No output from either pre-correction execution
is used by the manifest, analysis, report, or Gate.

## Gate and stop condition

`BFE2_LATQ_DG_APERTURE_READY` is asserted because the retained Q evidence has
at least one safe reject at lower Delta t, one unsafe aperture observation at a
larger Delta t, and one safe capture at a still larger Delta t. This Gate does
not authorize a follow-on stage. The stage ends here.
