# B-FE6-MARG0 ARCH0 detection-margin characterization

Final gate: `BFE6_MARG0_DETECTION_MARGIN_CHARACTERIZED`

## Scope and method

This package characterizes the frozen 30-tap ARCH0 detector at the 0.95 V /
25 C methodology anchor.  It computes the calibrated decision variable
`D_M = abs(M_FF - M_REF_selected)` using the exact strict RTL rule
`D_M > margin`.  RISE and FALL references and distributions remain separate.
No production RTL, tap count, feature arithmetic, calibration protocol, or
TIM0 interface was changed.

## Evidence and simulations

M0 inventoried and hashed retained BFE3/BFE4/BFE5 evidence.  M1 reused the
30-seed CALN0 population with zero new simulation.  M2 added only the missing
0.89 V and 0.86 V RISE cases: 60 HSPICE source and 60 VCS XA cases, paired by
the retained MC random signatures.  M3 reused all 30 healthy FALL captures and
added only the missing FALL droop set: 90 HSPICE source and 90 VCS XA cases at
0.92/0.89/0.86 V.  Every M3 XA log reported zero comparison errors, 30 taps,
sample index 36 at the 91 ns FALL edge, and resolved rails.

## Distributions and candidate margins

| Polarity | Healthy D_M range | 0.92 V droop range / TPR | 0.89 V droop range / TPR | 0.86 V droop range / TPR | Candidate |
|---|---:|---:|---:|---:|---:|
| RISE | 0..7 | 0..43 / 28/30 | 10..78 / 30/30 | 11..116 / 30/30 | 7 |
| FALL | 0..3 | 2..42 / 29/30 | 21..64 / 30/30 | 35..93 / 30/30 | 3 |

Candidates are the smallest integer margins with zero observed healthy FPR,
which preserves the highest empirical TPR under that observed constraint.
The RISE 0.92 V gap is -7 and the FALL 0.92 V gap is -1, so shallow-droop
overlap is retained honestly.  The historical CALN0 absolute-M ablation rule
was not recoverable; no favorable absolute comparator is claimed.

## RTL replay

M5 replayed retained/new q_ff vectors for CALN0 seeds 41001 and 41002 through
the implemented `bfe_backend_top`.  It consumed four RISE plus four FALL
calibration events per epoch, verified references and `CAL_LOCK`, exercised
healthy and 0.92/0.89/0.86 V representatives, reverse-direction FALL,
alternating polarity, one-event-per-clock overlap, equality quiet boundaries,
`margin+1` alarm boundaries, E7 alignment, and E8 sticky behavior.  Fresh VCS
build `build_v5` produced `BFE6_MARG0_M5_RTL_REPLAY_PASS` in `replay_v5.log`.

## Claim boundary

The supported conclusion is limited to this fixed-condition process-population
characterization and its captured-vector ARCH0 RTL replay.  It is not a claim
of universal 0.8..1.1 V operation, final silicon FPR, temperature/PVT
robustness, physical Level-0 correctness, post-layout signoff, continuous
adaptation, or coverage outside the characterized sampling threat model.
