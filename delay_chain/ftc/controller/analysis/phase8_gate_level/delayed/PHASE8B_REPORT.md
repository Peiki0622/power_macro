# Phase 8B SDF Delayed Gate-Level Regression

Status: `PASS`; gate contribution: `Gate-Level Calibration Controller = GO`.

The current mapped netlist was annotated with the Phase 7 MAX SDF and simulated
at the permitted 10 ns GLS clock. All three nominal trajectories retained the
exact operation counts and final codes:

| Scenario | Final M/F | Operations | Configs | Probes | Q samples 1/2 |
|---|---:|---:|---:|---:|---:|
| 0.80 V | M7/F6 | 45 | 17 | 28 | 28/28 |
| 0.95 V | M4/F6 | 36 | 14 | 22 | 22/22 |
| 1.10 V | M2/F9 | 36 | 15 | 21 | 21/21 |

The public event and physical-interface audits found no double-trigger, skipped
operation, illegal reset/clock overlap, multi-bit thermometer transition, Q
sample mismatch, or post-lock configuration change. The SDF log contains the
tool's negative-delay and negative timing-check diagnostics; those values were
clamped by VCS and did not produce a protocol failure. The raw log is retained
at `sim_output/elaborate_run.log`; summary evidence is
`../phase8_results.json`.
