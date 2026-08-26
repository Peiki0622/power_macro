# B-FE4-CALN0 per-chip startup self-calibration Monte Carlo

Gate: `BFE4_CALN0_INCONCLUSIVE`

Thirty paired SMIC40LL `MOS_MC` process instances were run locally. Each seed produced one 0.95 V normal and one 0.95->0.92 V, +75 ps, 3002 ps droop source realization; their index-2 HSPICE random-vector signatures were required to match. The 0.95 V point is a healthy methodology anchor, not a claim about all target-chip nominal voltages.

| Metric | Value |
|---|---:|
| W_ABS | 173.000 |
| W_CAL | 7.000 |
| G_ABS | -186.000 |
| G_CAL | -34.000 |

| Domain | Normal mean [min,max] | Droop mean [min,max] |
|---|---|---|
| Absolute M_FF | 293.77 [171,344] | 273.93 [162,357] |
| Self-calibrated Delta M | 0.23 [0,7] | 20.07 [-27,43] |

Fixed absolute threshold overlap: `True`. All final DFF samples rail-resolved: `True`. Calibration beneficial under the predeclared 0.5 width ratio: `False`.

Only two paper figures are emitted: `BFE4_CALN0_ABSOLUTE_MFF_DISTRIBUTION` and `BFE4_CALN0_SELFCAL_DELTA_M_DISTRIBUTION`, each as PNG and PDF. No temperature/PVT/DVFS sweep, threshold work, online adaptation, glitching, LUT/fusion, or aperture study was performed. This stage stops here.
