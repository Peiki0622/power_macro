# B-FE3-CLK0 periodic frontend audit

Gate: `BFE3_CLK0_50MHZ_PERIODIC_FRONTEND_PASS`

Frozen 0.95 V normal condition with 50 MHz / 50% `CLK_SYS_MON` (20 ns period, 10 ns high and 10 ns low). The 30-tap 4/0 RVT/LVT geometry and real `XOR2_X0P5M_A9TL40` loads are unchanged.

| Edge | Time (ps) | Polarity | Raw code [29:0] | M | Packet start (ps) | Packet end (ps) | Width (ps) | Overlap | Recovery |
|---:|---:|---|---|---:|---:|---:|---:|---|---|
| 0 | 1000.500 | rise | `111111111111111000000000000000` | 330 | 1036.630 | 1946.147 | 909.517 | False | True |
| 1 | 11001.500 | fall | `111111111111100000000000000000` | 299 | 11034.382 | 11896.485 | 862.103 | False | True |
| 2 | 21000.500 | rise | `111111111111111000000000000000` | 330 | 21036.485 | 21946.615 | 910.130 | False | True |
| 3 | 31001.500 | fall | `111111111111100000000000000000` | 299 | 31034.382 | 31896.585 | 862.202 | False | True |
| 4 | 41000.500 | rise | `111111111111111000000000000000` | 330 | 41036.485 | 41946.171 | 909.686 | False | True |
| 5 | 51001.500 | fall | `111111111111100000000000000000` | 299 | 51034.383 | 51896.292 | 861.910 | False | True |
| 6 | 61000.500 | rise | `111111111111111000000000000000` | 330 | 61036.485 | 61946.491 | 910.006 | False | True |
| 7 | 71001.500 | fall | `111111111111100000000000000000` | 299 | 71034.382 | 71896.415 | 862.032 | False | True |

Rise consistency: code=True, M=True, start span=0.145 ps, end span=0.467 ps, width span=0.613 ps.
Fall consistency: code=True, M=True, start span=0.001 ps, end span=0.292 ps, width span=0.293 ps.
Rise M values: `[330]`; fall M values: `[299]`.
Recommendation: **establish separate M_RISE/M_FALL baselines**.

This stage stops here. No CLK_PROBE, glitch detection, frequency/duty/phase scan, RTL, calibration, fault decision, lookup table, or multi-feature fusion was added.
