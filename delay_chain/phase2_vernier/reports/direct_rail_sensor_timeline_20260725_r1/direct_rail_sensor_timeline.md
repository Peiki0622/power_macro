# Direct Chiplet-A Rail Sensor Timeline

This figure is a controlled chiplet-A `VDD_A` PWL response experiment. It does not model an RO, a shared PDN, a B-side chiplet, or an attack current. Continuous rail traces are retained HSPICE `.tr0` points. The 40 code markers are real-DFF captures decoded from `direct_rail_samples.csv`; no intermediate code is inferred.

| Metric | Value |
|---|---:|
| Runner status | PASS |
| Capture samples | 40 |
| Closed-window baseline code | 15 |
| A-side minimum voltage (V) | 1.070000000 |
| A-side peak droop (mV) | 30.000000 |
| Reference-rail minimum voltage (V) | 1.100000000 |
| Valid captures without edge risk | 0 |
| Valid captures with edge risk | 40 |
| Invalid captures | 0 |

## Direct PWL Windows

| Window | Start (ns) | End (ns) |
|---|---:|---:|
| 0 | 20.000 | 45.000 |
| 1 | 60.000 | 85.000 |
| 2 | 100.000 | 125.000 |
| 3 | 140.000 | 165.000 |

## Evidence

- Run directory: `/home/zhupl25/chiplet_side_channel/chiplet_gds_data/power_macro/delay_chain/phase2_vernier/runs/direct_rail_sensor_timeline_20260725_r1`
- Capture CSV: `direct_rail_samples.csv`
- Result gates: `timeline_result.json`
- HSPICE waveform: `scenario/direct_rail_sensor.tr0`
