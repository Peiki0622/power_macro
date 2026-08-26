# B-FE3-VD2 minimum reliable operating voltage

Gate: `BFE3_VD2_MINIMUM_OPERATING_VOLTAGE_CHARACTERIZATION_FAIL`

The VD1 architecture and all timing were frozen. Fresh real HSPICE plus VCS/PrimeSim XA LATQ+DFF runs were made at each VD2 voltage. Coarse points used 30 mV steps from 0.86 V; only the interval between the last PASS and first FAIL was refined at 10 mV.

| VDD_DROOP (V) | Mode | Functional | q_ff[29:0] | M_FF | HD | delta_M | normal recovery |
|---:|---|---|---|---:|---:|---:|---|
| 0.86 | coarse | True | `000000011111111111110000000000` | 208 | 9 | -79 | True |
| 0.83 | coarse | True | `000000000111111111111000000000` | 174 | 12 | -113 | True |
| 0.80 | coarse | True | `000000000011111111111100000000` | 162 | 14 | -125 | True |
| 0.77 | coarse | True | `000000000000111111111110000000` | 132 | 17 | -155 | True |
| 0.74 | coarse | True | `000000000000001111111111000000` | 105 | 20 | -182 | True |
| 0.71 | coarse | True | `000000000000000011111111100000` | 81 | 23 | -206 | True |
| 0.68 | coarse | True | `000000000000000001111111110000` | 72 | 23 | -215 | True |
| 0.65 | coarse | True | `000000000000000000011111111000` | 52 | 22 | -235 | True |
| 0.62 | coarse | True | `000000000000000000001111111100` | 44 | 22 | -243 | True |
| 0.59 | coarse | True | `000000000000000000000011111110` | 28 | 21 | -259 | True |
| 0.56 | coarse | True | `000000000000000000000001111110` | 21 | 20 | -266 | True |
| 0.53 | coarse | True | `000000000000000000000000111111` | 15 | 20 | -272 | True |
| 0.50 | coarse | True | `000000000000000000000000011111` | 10 | 19 | -277 | True |
| 0.47 | coarse | True | `000000000000000000000000001111` | 6 | 18 | -281 | True |

Last PASS V: `0.47`. First FAIL V: `None`. VMIN_SENSE: `None`.
Incomplete points (not classified as FAIL because the 3-cycle DFF evidence is truncated): `[{'voltage_v': 0.44, 'capture_indices': [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15], 'expected_capture_count': 24, 'observed_capture_count': 16, 'reason': 'XA CSV contains only capture indices 0-15 after user-requested stop'}, {'voltage_v': 0.41, 'capture_indices': [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15], 'expected_capture_count': 24, 'observed_capture_count': 16, 'reason': 'XA CSV contains only capture indices 0-15 after user-requested stop'}, {'voltage_v': 0.38, 'capture_indices': [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15], 'expected_capture_count': 24, 'observed_capture_count': 16, 'reason': 'XA CSV contains only capture indices 0-15 after user-requested stop'}, {'voltage_v': 0.35, 'capture_indices': [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15], 'expected_capture_count': 24, 'observed_capture_count': 16, 'reason': 'XA CSV contains only capture indices 0-15 after user-requested stop'}]`.

Merged VD1+VD2 M_FF Pearson/Spearman correlation: `0.9739034313046765` / `0.9810153749788859` (trend description only).

The main M_FF and auxiliary HD plots are saved as PNG and PDF. Rail resolution and normal 287/246 recovery are the only functional criteria; saturated or extreme but definite digital codes are not independently failed. No phase/duration sweep, PVT, calibration, alarm threshold optimization, glitch, LUT, fusion, or latch-aperture study was performed. This stage stops here.
