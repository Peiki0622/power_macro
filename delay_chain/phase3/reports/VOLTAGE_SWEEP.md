# Phase-3 Physical Voltage Sweep

Mode: `rvt_lvt`; CAL_SEL=1 ; all frontend cells use VDD_A/VSS_A.

The CSV contains every 0.5 mV grid point plus exact timing anchors. `residual_code` is `code_polarity * (sensor_code - baseline_code)`.

## Summary

- Status: `PASS`
- Baseline code: `18`; nominal observed code: `18`
- `delta_code_last`: `12`; `delta_code_crit`: `14`
- Local monotonicity reversals: `1`; maximum reversal: `1` code

## Curve Samples

| Point | VDD (V) | Droop (mV) | Code | Residual | RVT-LVT final delay (ps) | Valid |
|---|---:|---:|---:|---:|---:|---:|
| grid | 1.100000000000 | 0.000 | 18 | 0 | -7.186855 | 1 |
| grid | 1.095000000000 | 5.000 | 18 | 0 | -8.355905 | 1 |
| grid | 1.090000000000 | 10.000 | 19 | 1 | -9.526517 | 1 |
| grid | 1.085000000000 | 15.000 | 21 | 3 | -10.647931 | 1 |
| grid | 1.080000000000 | 20.000 | 22 | 4 | -11.750975 | 1 |
| grid | 1.075000000000 | 25.000 | 23 | 5 | -12.429197 | 1 |
| grid | 1.070000000000 | 30.000 | 24 | 6 | -13.606677 | 1 |
| grid | 1.065000000000 | 35.000 | 25 | 7 | -14.540248 | 1 |
| grid | 1.060000000000 | 40.000 | 27 | 9 | -16.133966 | 1 |
| grid | 1.055000000000 | 45.000 | 30 | 12 | -17.464032 | 1 |
| last_pass_anchor | 1.054061327707 | 45.939 | 30 | 12 | -17.645365 | 1 |
| grid | 1.050500000000 | 49.500 | 32 | 14 | -18.732664 | 1 |
| first_violation_anchor | 1.047473942801 | 52.526 | 32 | 14 | -19.372962 | 1 |
| grid | 1.046000000000 | 54.000 | 32 | 14 | -19.667477 | 1 |
| grid | 1.041000000000 | 59.000 | 32 | 14 | -21.017392 | 1 |
