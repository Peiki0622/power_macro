# Phase 4 Calibration Algorithm FSM

- Decision: `Calibration Algorithm FSM = GO`
- Run directory: `/home/zhupl25/chiplet_side_channel/chiplet_gds_data/power_macro/delay_chain/ftc/controller/analysis/phase4/phase4_vcs`

## Test Results

All tests passed:
- Nominal 0.80V trajectory: M7/F6, 45 operations
- Nominal 0.95V trajectory: M4/F6, 36 operations
- Nominal 1.10V trajectory: M2/F9, 36 operations
- Coarse range fail detected
- Backoff underflow fail detected
- Fine range fail detected
- Guard range fail detected
- Guard not low fail detected

## Files

- RTL: `ftc_cal_fsm.sv`
- Testbench: `tb_ftc_cal_fsm.sv`
- Simulation log: `sim.log`
- Results: `results.json`
