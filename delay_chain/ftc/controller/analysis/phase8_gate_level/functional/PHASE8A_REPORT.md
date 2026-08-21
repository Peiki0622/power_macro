# Phase 8A Functional Gate-Level Regression

Status: `PASS`; gate contribution: `Gate-Level Calibration Controller = GO`.

The mapped SMIC standard-cell netlist was simulated with the behavioral sensor
oracle at a permitted 10 ns calibration clock. Public `config_update_event` and
`probe_start_event` pulses supplied exact operation counts; no internal
sequencer approximation was used.

| Scenario | Final M/F | Operations | Configs | Probes | Q samples 1/2 |
|---|---:|---:|---:|---:|---:|
| 0.80 V | M7/F6 | 45 | 17 | 28 | 28/28 |
| 0.95 V | M4/F6 | 36 | 14 | 22 | 22/22 |
| 1.10 V | M2/F9 | 36 | 15 | 21 | 21/21 |

All eight required negative scenarios terminated with their contract fail
reasons (1, 2, 3, 4, 5, 5, 6, 6). Every probe had exactly one released-reset
sensor-clock edge and two sample events. Every configuration transaction
changed one thermometer rail while reset was asserted and the sensor clock was
low. Terminal physical vectors remained frozen; the sensor model reported zero
violations.

Raw evidence is in `sim_output/elaborate_run.log` and the machine-readable
summary is `../phase8_results.json`.
