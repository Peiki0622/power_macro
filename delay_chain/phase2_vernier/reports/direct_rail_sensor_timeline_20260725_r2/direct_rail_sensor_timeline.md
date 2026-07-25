# Direct Chiplet-A Rail Sensor Timeline

This figure is the focused sensor-code panel from a controlled chiplet-A `VDD_A` PWL response experiment. It does not model an RO, a shared PDN, a B-side chiplet, or an attack current. The source CSV contains 500 real-DFF captures; a fixed-seed, display-only jitter is applied only to closed-window ordinates to make normal-region variation visible, while the CSV and electrical results remain unchanged.

| Metric | Value |
|---|---:|
| Runner status | PASS |
| Capture samples | 500 |
| Closed-window baseline code | 15 |
| A-side minimum voltage (V) | 1.070000000 |
| A-side peak droop (mV) | 30.000000 |
| Reference-rail minimum voltage (V) | 1.100000000 |
| Plotted capture count | 500 |
| Invalid captures | 0 |

## Direct PWL Windows

| Window | Start (ns) | End (ns) |
|---|---:|---:|
| 0 | 200.000 | 448.000 |
| 1 | 600.000 | 848.000 |
| 2 | 1000.000 | 1248.000 |
| 3 | 1400.000 | 1648.000 |

## Evidence

- Run directory: `/home/zhupl25/chiplet_side_channel/chiplet_gds_data/power_macro/delay_chain/phase2_vernier/runs/direct_rail_sensor_timeline_20260725_r2`
- Capture CSV: `direct_rail_samples.csv`
- Result gates: `timeline_result.json`
- HSPICE waveform: `scenario/direct_rail_sensor.tr0`
