# Direct Chiplet-A Rail Experiment

## Result

The completed `direct_rail_sensor_timeline_20260725_r1` HSPICE run is `PASS`.
It directly drives only the chiplet-A `VDD_A/VSS_A` rail and captures the
calibrated 32-stage sensor's real DFF outputs every 5 ns for 200 ns.  The
reference chain, comparator bank, DFF supply, and DFF well terminals remain at
the separate fixed `VDD_REF/VSS_REF = 1.100 V` domain.

This is a controlled sensor-response experiment.  It does not include a
RO-bank, a B-side chiplet, a shared PDN, a background workload current, a
reference-island RC network, PVT variation, or sensor self-disturbance.

| Electrical/decoder gate | Result |
|---|---:|
| HSPICE captures | 40 |
| Closed-window baseline code | 15 |
| Closed samples / valid closed samples | 20 / 20 |
| Direct-PWL windows | 4 |
| Samples / valid samples in each window | 5 / 5 |
| Distinct valid window codes | 14 |
| Valid window code set | 16, 17, 18, 19, 20, 21, 22, 23, 25, 26, 27, 28, 30, 31 |
| Invalid thermometer words | 0 |
| Reset failures | 0 |
| Maximum capture voltage error | `2.220446049250313e-16 V` |
| Solved `VDD_A` minimum | 1.070 V |
| Solved `VDD_REF` minimum | 1.100 V |

## Stimulus and Timing

The direct rail PWL changes only during the asserted-reset part of each 5 ns
frame: it holds the prior target to 20 ps after the boundary and reaches the
next target at 200 ps.  Reference launch occurs at 1.0 ns, calibrated sense
launch occurs at 1.02 ns, and capture reads at 2.5 ns, leaving at least 800 ps
of supply settling before launch.

The four direct voltage windows are 20--45 ns, 60--85 ns, 100--125 ns, and
140--165 ns.  Window targets are a fixed nonmonotonic 4--30 mV sequence;
closed-frame targets are fixed 0.5--2.0 mV fluctuations.  The 30 mV maximum
is below the latest 765 MHz 35-bank voltage-drop bound of 45.938672293 mV.

## Evidence and Reproduction

- Configuration: `../../phase2_config.json`
- Deck and HSPICE products: `../../runs/direct_rail_sensor_timeline_20260725_r1/scenario/`
- Capture evidence: `../../runs/direct_rail_sensor_timeline_20260725_r1/direct_rail_samples.csv`
- Gate results: `../../runs/direct_rail_sensor_timeline_20260725_r1/timeline_result.json`
- Provenance: `../../runs/direct_rail_sensor_timeline_20260725_r1/manifest.json`
- Figure: `direct_rail_sensor_timeline.png`

```bash
python3 power_macro/delay_chain/phase2_vernier/scripts/run_direct_rail_sensor_timeline.py \
  --config power_macro/delay_chain/phase2_vernier/phase2_config.json \
  --output-dir power_macro/delay_chain/phase2_vernier/runs/direct_rail_sensor_timeline_20260725_r1
python3 power_macro/delay_chain/phase2_vernier/scripts/plot_direct_rail_sensor_timeline.py \
  --config power_macro/delay_chain/phase2_vernier/phase2_config.json \
  --run-dir power_macro/delay_chain/phase2_vernier/runs/direct_rail_sensor_timeline_20260725_r1 \
  --output-dir power_macro/delay_chain/phase2_vernier/reports/direct_rail_sensor_timeline_20260725_r1
```
