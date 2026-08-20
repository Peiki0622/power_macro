# FTC Calibration Controller Phase 6 Filelist
# Protocol assertions and negative-path verification

# Package
../../rtl/ftc_cal_pkg.sv

# RTL modules (in dependency order)
../../rtl/ftc_cfg_therm_regs.sv
../../rtl/ftc_q_sampler.sv
../../rtl/ftc_operation_sequencer.sv
../../rtl/ftc_cal_fsm.sv
../../rtl/ftc_cal_controller_top.sv

# Assertions module
../../assertions/ftc_cal_controller_sva.sv

# Testbench support
../ftc_sensor_behavior_model.sv

# Top-level testbench
../tb_ftc_negative_scenarios.sv
