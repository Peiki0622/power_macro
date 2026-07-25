# 765 MHz Phase-1 Delay Delta

Source CSV: `/home/zhupl25/chiplet_side_channel/chiplet_gds_data/power_macro/delay_chain/phase2_vernier/runs/phase1_anchors_20260724_r1/raw_anchor_metrics.csv`

The values below are direct HSPICE measures of the first non-inverting
sensing stage.  No image measurement, interpolation, or analytical delay
model is used.

| Chain units | Vnom stage delay (s) | V35 stage delay (s) | V40 stage delay (s) | epsilon Vnom->V40 (s) | change (%) |
|---:|---:|---:|---:|---:|---:|
| 16 | 1.203000000000e-11 | 1.296000000000e-11 | 1.311000000000e-11 | 1.080000000000e-12 | 8.977556110 |
| 32 | 1.203000000000e-11 | 1.296000000000e-11 | 1.311000000000e-11 | 1.080000000000e-12 | 8.977556110 |
| 64 | 1.203000000000e-11 | 1.296000000000e-11 | 1.311000000000e-11 | 1.080000000000e-12 | 8.977556110 |

## Vernier reference

The 16-unit first-stage result is selected as the nominal unloaded
sensing-stage reference for the first Vernier sweep.  The next step
measures each reference-stage dummy-load variant directly before any
candidate is accepted.
