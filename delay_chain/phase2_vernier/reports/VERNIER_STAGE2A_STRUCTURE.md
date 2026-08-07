# Stage 2A Vernier Sensor Structure

Status: PASS

## Frozen contract

- Technology: SMIC40LL.
- Vernier depth: 32 comparator stages.
- Sense stage: two `INV_X0P5M_A9TR40` cells on `VDD_A/VSS_A`.
- Reference stage: two `INV_X0P5M_A9TR40` cells plus one retained dummy load on `VDD_REF/VSS_REF`.
- Comparator: `DFFRPQ_X0P5M_A9TR40`, with sense connected to `D` and reference connected to `CK`.
- Thermometer polarity: `0*1*`; decoding is outside the physical frontend.

## RTL boundary

`vernier_sensor.sv` exports `clk_i`, `rst_i`, `sample_req_i`, four explicit
power rails, `sensor_code_o[5:0]`, `code_valid_o`, `sample_valid_o`, and
`sensor_fault_o`.  Raw comparator taps remain private to
`vernier_frontend_struct.sv`; the future detector therefore sees only the
stable decoded interface.

The structural hierarchy is:

```
vernier_sensor
  u_sample_adapter
  u_frontend
    u_launch_cal
    32 x u_sense_stage
    32 x u_reference_stage
    32 x u_comparator
  u_backend
```

The frontend contains 210 intentionally retained physical instances: 160
sense/reference inverters, 7 calibration buffers, 11 calibration MUX cells,
and 32 comparator DFFs.  `keep_hierarchy`, `keep`, and `dont_touch` attributes
are applied at the structural boundaries and physical cells.  The reference
dummy outputs terminate on private kept nodes, so their input loading cannot
be optimized away.

## Evidence

- RTL: `delay_chain/phase2_vernier/rtl/vernier_*.sv`.
- Physical SPICE mirror: `delay_chain/phase2_vernier/spice/launch_calibration.inc`.
- DC hierarchy/reference evidence: `/tmp/vernier_stage2a_dc_signoff.pergR3rz/physical_hierarchy.rpt` and `physical_reference.rpt`.
- Final VCS top elaboration: `/tmp/vernier_stage2a_vcs_signoff.zFfoU3zo/vcs_compile.log`.

No behavioral delay model or synthesizable `function` is used.
