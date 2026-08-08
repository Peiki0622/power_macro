# Phase-3 Physical Voltage Sweep

Mode: `rvt_rvt`; CAL_SEL=1 ; all frontend cells use VDD_A/VSS_A.

The CSV contains every 0.5 mV grid point plus exact timing anchors. `residual_code` is `code_polarity * (sensor_code - baseline_code)`.

## Summary

- Status: `PASS`
- Baseline code: `18`; nominal observed code: `2`
- `delta_code_last`: `-16`; `delta_code_crit`: `-16`
- Local monotonicity reversals: `0`; maximum reversal: `0` code

## Curve Samples

| Point | VDD (V) | Droop (mV) | Code | Residual | RVT-LVT final delay (ps) | Valid |
|---|---:|---:|---:|---:|---:|---:|
| grid | 1.100000000000 | 0.000 | 2 | -16 | 177.704948 | 1 |
| grid | 1.095000000000 | 5.000 | 2 | -16 | 179.633040 | 1 |
| grid | 1.090000000000 | 10.000 | 2 | -16 | 181.371152 | 1 |
| grid | 1.085000000000 | 15.000 | 2 | -16 | 183.168086 | 1 |
| grid | 1.080000000000 | 20.000 | 2 | -16 | 185.195391 | 1 |
| grid | 1.075000000000 | 25.000 | 2 | -16 | 187.517901 | 1 |
| grid | 1.070000000000 | 30.000 | 2 | -16 | 189.347003 | 1 |
| grid | 1.065000000000 | 35.000 | 2 | -16 | 190.896168 | 1 |
| grid | 1.060000000000 | 40.000 | 2 | -16 | 192.848074 | 1 |
| grid | 1.055000000000 | 45.000 | 2 | -16 | 195.446800 | 1 |
| last_pass_anchor | 1.054061327707 | 45.939 | 2 | -16 | 195.854171 | 1 |
| grid | 1.050500000000 | 49.500 | 2 | -16 | 197.372062 | 1 |
| first_violation_anchor | 1.047473942801 | 52.526 | 2 | -16 | 198.712162 | 1 |
| grid | 1.046000000000 | 54.000 | 2 | -16 | 199.253805 | 1 |
| grid | 1.041000000000 | 59.000 | 2 | -16 | 200.773851 | 1 |
