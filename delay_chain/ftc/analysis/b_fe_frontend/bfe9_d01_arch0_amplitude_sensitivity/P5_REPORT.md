# BFE9 D01 P5 ARCH0 RTL boundary replay

Gate: `BFE9_D01_P5_BOUNDARY_RTL_REPLAY_PASS`

One task-local VCS replay covered the weakest HIT, strict equality boundary, and closest MISS.
Production ARCH0 RTL and frozen margins were unchanged; no HSPICE was launched.

| Seed | H_D_D01 | Expected alarm | E4->E7 (ns) |
|---:|---:|---:|---:|
| 41025 | -2 | MISS | N/A |
| 41016 | 0 | MISS | N/A |
| 41020 | 1 | HIT | 7.500000 |
