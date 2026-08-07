# Stage 2A Physical Launch Calibration

Status: PASS

## Method

The ideal launch offset was replaced by the structural BUF/MXT2 network in
`vernier_launch_cal_struct.sv`.  The identical topology, including the three-
MUX balanced reference path and the retained final reference input load, is
present in `spice/launch_calibration.inc`.  No fixed per-buffer delay is used
in RTL.

## HSPICE result

Evidence directory: `/tmp/vernier_stage2a_calibration_final.6EauLa/run`

`completion.rpt` reports `status=PASS` and `scenario_count=256` (8 taps x 32
nominal repeats).  The final `calibration_result.json` reports:

| CAL_SEL | measured launch offset | baseline code |
|---:|---:|---:|
| 0 | -12 ps | 0 |
| 1 | 5 ps | 7 |
| 2 | 21 ps | 15 |
| 3 | 38 ps | 22 |
| 4 | 54 ps | 30 |
| 5 | 72 ps | 32 |
| 6 | 88 ps | 32 |
| 7 | 101 ps | 32 |

Every tap has 32 valid samples, zero baseline variation, and zero median raw
bubbles.  The selected contract is therefore `CAL_SEL=2`, baseline
`sensor_code=15`, with a measured (not assumed) 21 ps launch offset.

The synthesizable package stores only `DEFAULT_CAL_SEL=3'd2` and the baseline
code; it does not encode a behavioral time delay.
