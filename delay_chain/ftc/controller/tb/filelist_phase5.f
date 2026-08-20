# FTC Calibration Controller Top-Level Filelist
# Phase 5: Complete integration with behavioral sensor model

# Package
../../rtl/ftc_cal_pkg.sv

# RTL modules (in dependency order)
../../rtl/ftc_cfg_therm_regs.sv
../../rtl/ftc_q_sampler.sv
../../rtl/ftc_operation_sequencer.sv
../../rtl/ftc_cal_fsm.sv
../../rtl/ftc_cal_controller_top.sv

# Testbench support
../ftc_sensor_behavior_model.sv

# Top-level testbench
../tb_ftc_cal_controller.sv
