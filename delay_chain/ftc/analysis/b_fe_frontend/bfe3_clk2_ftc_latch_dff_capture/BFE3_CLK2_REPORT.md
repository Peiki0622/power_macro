# B-FE3-CLK2 FTC LATQ to real DFF capture

Gate: `BFE3_CLK2_FTC_LATCH_DFF_CAPTURE_PASS`

Frozen 50 MHz/50% `CLK_SYS_MON`, 0.95 V monitored rail, 30-tap 4/0 RVT/LVT chain, real `XOR2_X0P5M_A9TL40`, real `LATQ_X0P5M_A9TR40`, and selected real `DFFRPQ_X0P5M_A9TR40` were used. The frozen CLK1 HSPICE source trace was replayed through a new VCS/PrimeSim XA LATQ+DFF bench.

G falling is fixed at system edge + 534.524618567 ps. DFF CK rising is fixed at Gfall + 1000 ps (system edge + 1534.524618567 ps). LATQ analog behavior between these points is diagnostic only; the gate uses the DFF sample instant.

| Family | Count | q_ff code(s) | M_FF | Non-empty | DFF rail-resolved |
|---|---:|---|---|---|---|
| Rise designated | 3 | `['000000000000001111111111111100']` | `[287]` | True | True |
| Fall designated | 3 | `['000000000000000111111111111000']` | `[246]` | True | True |

| Sample | Time (ps) | Edge | Designated | q_ff[29:0] | M_FF | DFF rail |
|---:|---:|---|---|---|---:|---|
| 0 | 2634.524619 | rise | True | `001111111111111100000000000000` | 287 | True |
| 1 | 5134.524619 | rise | False | `000000000000000000000000000000` | 0 | True |
| 2 | 7634.524619 | fall | False | `000000000000000000000000000000` | 0 | True |
| 3 | 10134.524619 | fall | False | `000000000000000000000000000000` | 0 | True |
| 4 | 12634.524619 | fall | True | `000111111111111000000000000000` | 246 | True |
| 5 | 15134.524619 | fall | False | `000000000000000000000000000000` | 0 | True |
| 6 | 17634.524619 | rise | False | `000000000000000000000000000000` | 0 | True |
| 7 | 20134.524619 | rise | False | `000000000000000000000000000000` | 0 | True |
| 8 | 22634.524619 | rise | True | `001111111111111100000000000000` | 287 | True |
| 9 | 25134.524619 | rise | False | `000000000000000000000000000000` | 0 | True |
| 10 | 27634.524619 | fall | False | `000000000000000000000000000000` | 0 | True |
| 11 | 30134.524619 | fall | False | `000000000000000000000000000000` | 0 | True |
| 12 | 32634.524619 | fall | True | `000111111111111000000000000000` | 246 | True |
| 13 | 35134.524619 | fall | False | `000000000000000000000000000000` | 0 | True |
| 14 | 37634.524619 | rise | False | `000000000000000000000000000000` | 0 | True |
| 15 | 40134.524619 | rise | False | `000000000000000000000000000000` | 0 | True |
| 16 | 42634.524619 | rise | True | `001111111111111100000000000000` | 287 | True |
| 17 | 45134.524619 | rise | False | `000000000000000000000000000000` | 0 | True |
| 18 | 47634.524619 | fall | False | `000000000000000000000000000000` | 0 | True |
| 19 | 50134.524619 | fall | False | `000000000000000000000000000000` | 0 | True |
| 20 | 52634.524619 | fall | True | `000111111111111000000000000000` | 246 | True |
| 21 | 55134.524619 | fall | False | `000000000000000000000000000000` | 0 | True |
| 22 | 57634.524619 | fall | False | `000000000000000000000000000000` | 0 | True |
| 23 | 60134.524619 | fall | False | `000000000000000000000000000000` | 0 | True |

Designated failures: `[]`. Non-designated failures: `[]`.

No droop, glitch, clock sweep, RTL fault decision, self-calibration, LUT, multi-feature fusion, or latch-aperture optimization was performed. This stage stops here.
