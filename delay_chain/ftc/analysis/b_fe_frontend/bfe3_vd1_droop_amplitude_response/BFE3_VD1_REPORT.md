# B-FE3-VD1 droop amplitude response

Gate: `BFE3_VD1_DROOP_AMPLITUDE_RESPONSE_PASS`

Formal L1/L2/L3 voltage values matching the frozen 0.95 V monitored baseline were not present in the repository; the requested sparse points 0.95/0.92/0.89/0.86 V were used. Each point reran the real HSPICE source and VCS/PrimeSim XA LATQ+DFF chain with frozen clocks, phase, pulse timing, cells, and 30 taps.

| VDD_DROOP (V) | q_ff[29:0] | M_FF | HD vs nominal | delta_M | DFF rail | normal rise/fall |
|---:|---|---:|---:|---:|---|---|
| 0.95 | `001111111111111100000000000000` | 287 | 0 | 0 | True | True |
| 0.92 | `000111111111111110000000000000` | 273 | 2 | -14 | True | True |
| 0.89 | `000001111111111111000000000000` | 234 | 5 | -53 | True | True |
| 0.86 | `000000011111111111110000000000` | 208 | 9 | -79 | True | True |

Pearson correlation (VDD_DROOP vs M_FF): `0.9860916889387764`.
Spearman correlation (VDD_DROOP vs M_FF): `0.9999999999999998`; these are trend descriptors only, not a linearity requirement.

Direction-consistent response: `True`. At least one point shallower than 0.86 V separates from nominal M_FF=287: `True`.

The plotted response is saved as `BFE3_VD1_M_FF_vs_VDD_DROOP.png` and `.pdf`. LATQ internal transients were not used as an independent failure condition. No phase/duration sweep, threshold optimization, PVT, glitch, calibration, RTL decision, LUT, fusion, or aperture study was performed. This stage stops here.
