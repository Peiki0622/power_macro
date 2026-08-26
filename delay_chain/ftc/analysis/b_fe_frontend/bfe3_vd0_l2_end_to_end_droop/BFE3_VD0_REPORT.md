# B-FE3-VD0 L2 end-to-end droop sensitivity

Gate: `BFE3_VD0_L2_END_TO_END_DROOP_SENSITIVITY_PASS`

A single formal L2 drop was injected after the 21 ns system rise: 0.95 V -> 0.86 V with 1 ps fall, 3000 ps hold, and 1 ps recovery (total 3002 ps). The frozen 50/400 MHz clocks, 30-tap chain, real LATQ, and real DFF were retained.

| Capture | Edge | Designated | q_ff[29:0] | M_FF |
|---:|---|---|---|---:|
| 0 | rise | True | `001111111111111100000000000000` | 287 |
| 1 | rise | False | `000000000000000000000000000000` | 0 |
| 2 | fall | False | `000000000000000000000000000000` | 0 |
| 3 | fall | False | `000000000000000000000000000000` | 0 |
| 4 | fall | True | `000111111111111000000000000000` | 246 |
| 5 | fall | False | `000000000000000000000000000000` | 0 |
| 6 | rise | False | `000000000000000000000000000000` | 0 |
| 7 | rise | False | `000000000000000000000000000000` | 0 |
| 8 | rise | True | `000000011111111111110000000000` | 208 |
| 9 | rise | False | `000000000000000000000000000000` | 0 |
| 10 | fall | False | `000000000000000000000000000000` | 0 |
| 11 | fall | False | `000000000000000000000000000000` | 0 |
| 12 | fall | True | `000111111111111000000000000000` | 246 |
| 13 | fall | False | `000000000000000000000000000000` | 0 |
| 14 | rise | False | `000000000000000000000000000000` | 0 |
| 15 | rise | False | `000000000000000000000000000000` | 0 |
| 16 | rise | True | `001111111111111100000000000000` | 287 |
| 17 | rise | False | `000000000000000000000000000000` | 0 |
| 18 | fall | False | `000000000000000000000000000000` | 0 |
| 19 | fall | False | `000000000000000000000000000000` | 0 |
| 20 | fall | True | `000111111111111000000000000000` | 246 |
| 21 | fall | False | `000000000000000000000000000000` | 0 |
| 22 | fall | False | `000000000000000000000000000000` | 0 |
| 23 | fall | False | `000000000000000000000000000000` | 0 |

Droop designated rise: sample 8 at 22634.524618567 ps, HD=9, delta_M=-79, M_FF=208.
Pre/post normal rise recovery: True. Normal fall references: True.

LATQ internal transients were not used as an independent failure condition. No sweep, calibration, RTL fault decision, glitch, LUT, fusion, or latch-aperture study was performed. This stage stops here.
