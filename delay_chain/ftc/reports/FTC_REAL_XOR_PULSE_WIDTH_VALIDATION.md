# FTC Real XOR Pulse-Width Validation

## Scope

Re-published for the formal 0.80--1.10 V range from completed TT/25 C physical `fine.csv` evidence. No HSPICE run was launched.

## Result

All 31 retained 10 mV points have valid real XOR pulses and strictly increasing `W_real` as VDD decreases.

| VDD (V) | W_real (ps) | Valid |
|---:|---:|---:|
| 1.10 | 242.236 | 1 |
| 1.09 | 248.409 | 1 |
| 1.08 | 254.521 | 1 |
| 1.07 | 261.289 | 1 |
| 1.06 | 268.362 | 1 |
| 1.05 | 275.420 | 1 |
| 1.04 | 284.486 | 1 |
| 1.03 | 292.845 | 1 |
| 1.02 | 302.019 | 1 |
| 1.01 | 311.390 | 1 |
| 1.00 | 322.244 | 1 |
| 0.99 | 331.766 | 1 |
| 0.98 | 343.787 | 1 |
| 0.97 | 356.327 | 1 |
| 0.96 | 369.817 | 1 |
| 0.95 | 383.481 | 1 |
| 0.94 | 398.797 | 1 |
| 0.93 | 415.010 | 1 |
| 0.92 | 432.058 | 1 |
| 0.91 | 449.750 | 1 |
| 0.90 | 470.158 | 1 |
| 0.89 | 491.489 | 1 |
| 0.88 | 514.849 | 1 |
| 0.87 | 539.571 | 1 |
| 0.86 | 566.317 | 1 |
| 0.85 | 596.477 | 1 |
| 0.84 | 628.819 | 1 |
| 0.83 | 662.095 | 1 |
| 0.82 | 701.178 | 1 |
| 0.81 | 743.988 | 1 |
| 0.80 | 789.004 | 1 |

## Decision

**GO for TT/25 C 0.80--1.10 V real-XOR pulse completeness and monotonicity.**
