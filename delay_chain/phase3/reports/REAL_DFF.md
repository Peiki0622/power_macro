# Phase-3 Real Same-Rail DFF

D=LVT tap, CK=RVT tap; all 32 DFF supply and well pins use VDD_A/VSS_A.

| Scenario | VDD (V) | Source offset (ps) | Raw word | Corrected word | Code | Raw bubbles | Bubbles | Valid | Reset failures |
|---|---:|---:|---|---|---:|---:|---:|---|---:|
| nominal | 1.100000000000 | 30.000000 | `11111111111111111000000000000000` | `00000000000000000111111111111111` | 17 | 0 | 0 | 1 | 0 |
| last_pass | 1.054061327707 | 30.000000 | `11111111111111111111111000000000` | `00000000000000000000000111111111` | 23 | 0 | 0 | 1 | 0 |
| first_violation | 1.047473942801 | 30.000000 | `11111111111111111111111100000000` | `00000000000000000000000011111111` | 24 | 0 | 0 | 1 | 0 |

All data is sourced from `runs/real_dff/scenarios/*/phase3_real_dff.mt0.csv`.
