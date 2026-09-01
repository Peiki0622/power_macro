# BFE12 P4 Retained A/B RTL Characterization

Gate: `BFE12_SIGN0_P4_RETAINED_AB_RTL_CHARACTERIZED`

One VCS regression replayed all 690 retained events through four parallel
controllers: authoritative ARCH0, SIGN0 at 435, SIGN0 at 18, and SIGN0 at 19.
The independent post-run audit classified the result as
`RTL_REPRODUCES_FROZEN_SHADOW` with zero event mismatches.

| Dataset | ARCH0 | SIGN0@18 | SIGN0@19 |
|---|---:|---:|---:|
| Healthy held-out FPR | 1/240 | 1/240 | 1/240 |
| Healthy signed RISE additions | 0/360 | 0/360 | 0/360 |
| D01 | 22/30 | 30/30 | 30/30 |
| D02 | 30/30 | 30/30 | 30/30 |
| D04 | 24/30 | 30/30 | 30/30 |

All FALL events matched ARCH0 for both signed candidates.  The P2 cycle table
already records the unchanged seven-edge E0-to-E7 detector latency; P4 adds no
physical-latency claim.  No physical simulator was invoked.
