# B-FE3-P0T late-droop diagnostic re-probe

Gate: `BFE3_P0T_LATE_DROOP_RECOVERED_BY_REPROBE`

Frozen source: P0R LATE, phase=500 ps, 0.95->0.86 V L2, 3002 ps droop, 30 taps, 4/0 RVT/LVT, Level-0 restoration, real `LATQ_X0P5M_A9TR40` at `VDD_SAFE=0.95 V`.
Only raw `M=sum(i*q[i])` is evaluated; no N/T, RTL, calibration, lookup table, filtering, bubble repair, or multi-feature fusion.

Normal M envelope: `260..315`. Droop duration is measured from the 1500 ps falling-transition onset to each G close.

| Probe | Launch (ps) | G close (ps) | Droop duration at G close (ps) | q_raw[29:0] | M | Rail/tail valid | Outside envelope | Margin |
|---|---:|---:|---:|---|---:|---|---|---:|
| FIRST | 1000.000000000 | 1534.524618567 | 34.524618567 | `001111111111111100000000000000` | 287 | True | False | 0 |
| REPROBE_PLUS1000 | 2000.000000000 | 2534.524618567 | 1034.524618567 | `000000001111111111110000000000` | 186 | True | True | 74 |
| REPROBE_PLUS2000 | 3000.000000000 | 3534.524618567 | 2034.524618567 | `000000001111111111110000000000` | 186 | True | True | 74 |

Worst new probe: `REPROBE_PLUS1000` at 2000.000000000 ps, q_raw[29:0]=`000000001111111111110000000000`, M=186, margin=74.

The first P0R LATE point is retained as the M=287 blind-window baseline. This stage stops after the two diagnostic re-probes.
