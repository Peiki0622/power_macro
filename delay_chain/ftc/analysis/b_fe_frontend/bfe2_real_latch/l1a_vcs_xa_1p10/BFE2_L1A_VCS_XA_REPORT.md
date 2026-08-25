# B-FE2-L1A VCS-XA 1.10 V Report

Verification mode: VCS W-2024.09 + PrimeSim XA W-2024.09 mixed-signal latch-boundary co-simulation.
Frozen source: B-FE2.2C 0.95 V normal and 0.95->0.86 V L2; sample_close=534.524618567 ps.
safe_d rule: xor > 0.5*VDD_SENSE ? 0.95 V : 0 V; VDD_SAFE/VNW=1.10 V, VPW/VSS=0 V.

| Scenario | Final code | Ones | Source-free re-flip | Unresolved | Mid-rail | Tail unstable |
|---|---|---:|---|---|---|---|
| BFE2L-095-N | `000000000000000111111111111111` | 15 | [] | [] | [] | [] |
| BFE2L-095-L2 | `000000000001111111111111111111` | 19 | [] | [] | [] | [] |

Hamming distance: 4 (required >=9).
tap27 normal: final=1.099999663 V, post-close events=[]; tap27 L2: final=1.099999663 V, post-close events=[].

Gate: **BFE2_L1A_REAL_SAFE_LATCH_FAIL**
