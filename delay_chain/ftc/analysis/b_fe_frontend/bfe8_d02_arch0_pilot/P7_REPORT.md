# BFE8 D02 P7 ARCH0 RTL replay

Gate: `BFE8_D02_P7_ARCH0_RTL_REPLAY_PASS`

The weakest, near-median and strongest actual D02 headroom seeds were replayed through the unchanged production ARCH0 RTL. Calibration, strict comparison, E7 alignment and E8 sticky behavior passed without new HSPICE.

The task-scoped `P7_ALARM_TIMING.csv` records the actual `$realtime` E4 consume and E7 alarm timestamps. All three target rows measured an E4-to-E7 interval of 7.500000 ns (3 x 2.5 ns probe periods); the frozen capture contract contributes 4 probe periods from E0 to E4, so E0-to-E7 remains 7 periods. Absolute rows are sequential bench epochs; P6's absolute latency is the target-edge + DFF-offset + seven-period derivation.

| Seed | E4 event (ns) | E7 alarm (ns) | E4->E7 (ns) |
|---:|---:|---:|---:|
| 41022 | 41.260000 | 48.760000 | 7.500000 |
| 41028 | 106.260000 | 113.760000 | 7.500000 |
| 41027 | 171.260000 | 178.760000 | 7.500000 |
