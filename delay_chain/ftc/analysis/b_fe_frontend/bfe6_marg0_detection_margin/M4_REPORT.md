# B-FE6-MARG0 M4 margin selection

Gate: `BFE6_MARG0_M4_MARGIN_SWEEP_COMPLETE`

Condition: 0.95 V / 25 C fixed-condition process-population characterization.
The exact strict rule is `D_M > margin`; RISE and FALL are swept independently.

| Polarity | Candidate | Healthy max | 0.92 V TPR | 0.89 V TPR | 0.86 V TPR |
|---|---:|---:|---:|---:|---:|
| RISE | 7 | 7 | 0.933 | 1.000 | 1.000 |
| FALL | 3 | 3 | 0.967 | 1.000 | 1.000 |

The candidate criterion is the smallest integer margin with zero observed healthy FPR, preserving the highest TPR under the zero-FPR constraint.
The 0.92 V FALL distribution overlaps healthy FALL by one code; this overlap is retained.
The historical CALN0 absolute-M ablation rule is not recoverable from retained artifacts, so no ablation claim is made.
Candidates are characterization values, not final silicon settings or PVT guardbands.
