# BFE8 D02 ARCH0 quantitative pilot

Gate: `BFE8_D02_ARCH0_QUANTITATIVE_PILOT_FROZEN`

| Metric | D02 ARCH0 pilot |
|---|---:|
| Healthy FPR | 1/240 observed healthy events |
| Detection coverage C_det | 30/30 (100.0%) |
| Decision headroom H_D | 19 / 38.0 M-codes (min / median) |
| First-alarm latency L_det | 20.534525 / 20.534525 ns (median / worst) |

Frozen margins: `M_MARGIN_RISE_P0=22` and `M_MARGIN_FALL_P0=24` M-codes.
Margins were selected from healthy-only MARGIN_BG=7302 development data and committed before any D02 attack simulation.
Coverage is observed over 30 paired process seeds, not a universal silicon claim; FPR is observed over independent FPR_BG=7303 events.
First-alarm latency is a derived fixed-TIM0 pipeline value (target edge + frozen DFF offset + seven probe periods); P7 measured the three-period E4-to-E7 leg on representative real vectors, while the frozen capture contract supplies four periods from E0 to E4.
R0 corrected the pre-attack diagnostic to be polarity-aware using only existing D02/healthy raw artifacts and captured vectors; R0 simulation accounting is HSPICE=0, VCS=0, PrimeSim=0, DC=0. Corrected pre-attack alarms are 0/30 seeds.

The single figure `BFE8_D02_HEADROOM.png` is generated from the final per-seed CSV; the method is now frozen for later DROOP12 expansion.
