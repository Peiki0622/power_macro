# Stage 2A Signoff

Overall status: PASS

| Stage 2A gate | Evidence | Result |
|---|---|---|
| Structural frontend exists | RTL wrappers and DC hierarchy/reference reports | PASS |
| Physical launch calibration | 256-scenario HSPICE run, `/tmp/vernier_stage2a_calibration_final.6EauLa/run` | PASS |
| `CAL_SEL=2` gives baseline code 15 | `calibration_result.json`, variation 0 | PASS |
| Python and SystemVerilog decoder equivalence | Full Phase 2 unittest regression | PASS |
| SPICE raw-Q replay | 500-vector VCS replay, mismatch 0 | PASS |
| Physical structure preserved in synthesis | DC physical reports, 32 DFFs and protected chain hierarchy | PASS |
| Stable macro interface | Top-level VCS elaboration of `vernier_sensor` | PASS |

The final macro exports `sensor_code_o[5:0]`, `code_valid_o`,
`sample_valid_o`, and `sensor_fault_o` behind the clock/reset/request and
explicit local power rails.  The design is ready for the planned Stage 2B
`cusum_V07_H008` consumer; CUSUM is intentionally not included in Stage 2A.

All simulation, HSPICE, VCS, and DC intermediate products remain under
`/tmp` task directories.  The repository retains RTL, scripts, SPICE include,
tests, and these final reports only.
