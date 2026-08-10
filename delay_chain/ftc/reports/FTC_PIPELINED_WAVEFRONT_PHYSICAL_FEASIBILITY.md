# FTC Pipelined-Wavefront Physical Feasibility

## Scope

Phase-diverse sampling is already closed because its capture phases shared the post-capture blind interval. This study instead moves the input-edge aperture while retaining the existing SMIC40LL RVT/LVT delay chains and raw corresponding-tap XOR bank. It does not implement a capture pipeline, controller, alarm, PVT sweep, or glitch-coverage claim.

## Falling-Edge Behavior

| VDD (V) | Raw XOR | Start--End | Runs | Level | Ordered transition |
|---:|---|---:|---:|---:|---:|
| 1.10 | `000000000000111111111000000000` | 12--20 | 1 | 0 | 1 |
| 0.90 | `000001111111100000000000000000` | 5--12 | 1 | 0 | 1 |
| 0.75 | `011111100000000000000000000000` | 1--6 | 1 | 0 | 1 |

Classification: **sensible**. `sensible` means a falling edge is independently decodable at all anchors; `reset_only` means it is retained only as a physical recovery edge; `destructive` closes the route.

## Two-Edge Coexistence

| T_edge | All-anchor overlap | 1.10 V | 0.90 V | 0.75 V | Window levels (edge0/edge1) | Conclusion |
|---:|---:|---|---|---|---|---|
| 750.0 ps | 0 | overlap=0, accepted=1 | overlap=1, accepted=1 | overlap=1, accepted=1 | 1.10 V=[0, 0]; 0.90 V=[0, 1]; 0.75 V=[0, 1] | stable_overlap=0 |
| 600.0 ps | 1 | overlap=1, accepted=1 | overlap=1, accepted=0 | overlap=1, accepted=1 | 1.10 V=[0, 0]; 0.90 V=[0, 2]; 0.75 V=[0, 1] | stable_overlap=0 |
| 400.0 ps | 1 | overlap=1, accepted=1 | overlap=1, accepted=0 | overlap=1, accepted=1 | 1.10 V=[0, 0]; 0.90 V=[0, 2]; 0.75 V=[0, 0] | stable_overlap=0 |

## Eight-Edge Periodicity

| VDD (V) | T_edge | Edge | Polarity | Level | Start--End | Runs |
|---:|---:|---:|---|---:|---:|---:|
| not run | not run | -- | -- | -- | -- | -- |

The eight-edge HSPICE step was correctly not launched because no tested T_edge was both overlapping and decodable at all three voltage anchors.

## Measured Physical Interval

| Landmark | Measured value |
|---|---:|
| Stable non-overlap point | 750.0 ps |
| Overlap begins by | 600.0 ps |
| Minimum tested stable point | not measured |
| First tested unstable point | 600.0 ps |
| Recommended next-stage point | not measured |

## Final Decision

**NO-GO**
The measured prerequisites did not establish a common stable overlapping pipeline region. No complex multi-window decoder or pipeline-control workaround was added.
