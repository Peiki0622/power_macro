# B-FE3-P0R M phase-representative audit

Gate: `BFE3_P0R_M_PHASE_OVERLAP`

Three newly simulated discrete L2 phases use the frozen 30-tap 4/0 source, Level-0 restoration, real `LATQ_X0P5M_A9TR40`, `VDD_SAFE=0.95 V`, and common `G_close=1534.524618567 ps`.
Only `M=sum(i*q[i]), i=0..29` is evaluated. No N/T decision, RTL, calibration, lookup table, filtering, bubble repair, or multi-feature fusion is used.

Frozen normal/capture-perturbation M envelope: `260..315`.
Existing P0 L2 phase reference: phase `75 ps`, q_raw[29:0]=`000000011111111111110000000000`, M=`208`, margin=`52`.

| Phase | Phase (ps) | q_raw[29:0] | M | Final/tail valid | Outside normal envelope | Margin |
|---|---:|---|---:|---|---|---:|
| EARLY | 0.000 | `000000001111111111110000000000` | 186 | True | True | 74 |
| MIDDLE | 250.000 | `000001111111111111000000000000` | 234 | True | True | 26 |
| LATE | 500.000 | `001111111111111100000000000000` | 287 | True | False | 0 |

Worst phase: `LATE` at `500.000 ps`, q_raw[29:0]=`001111111111111100000000000000`, M=`287`, margin=`0`.
Minimum margin: `0`.

The Gate is robust only if every new representative phase is rail-resolved/tail-stable and lies strictly outside the closed normal M envelope. This stage stops here regardless of outcome.
