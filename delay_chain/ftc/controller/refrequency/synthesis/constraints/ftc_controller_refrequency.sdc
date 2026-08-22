# ============================================================================
# FTC re-frequency controller timing constraints
# ============================================================================
# Active source: refrequency/handoff/phase1_timing_handoff_refrequency.json
# Calibration clock: 400 MHz, 2.5 ns period.  This SDC is task-owned and does
# not alter the historical Phase-7 1 GHz constraint file.
# ============================================================================

# The one active synchronous controller clock.  Sensor Q remains sampled by
# the registered controller interface; its external arrival budget is retained
# from the accepted flow rather than treated as a false path.
create_clock -name cal_clk -period 2.5 [get_ports cal_clk]

# Preserve the existing absolute 50 ps setup and 20 ps hold uncertainty.  At
# the longer selected period this is conservative and leaves explicit digital
# margin, rather than silently relaxing the environment with a percentage rule.
set_clock_uncertainty -setup 0.05 [get_clocks cal_clk]
set_clock_uncertainty -hold 0.02 [get_clocks cal_clk]
set_clock_transition 0.05 [get_clocks cal_clk]

# ctrl_por_n is asynchronous assertion/deassertion control.  It is excluded
# from ordinary data-path timing while recovery/removal checks remain enabled
# in the synthesis script and are reported separately.
set_input_transition 0.1 [get_ports ctrl_por_n]
set_false_path -from [get_ports ctrl_por_n] -to [all_registers]

# Synchronous controller command and physical sensor-Q timing budgets.  These
# remain the accepted interface values; only the controller clock period and
# internal quantized event cycles changed in this re-frequency task.
set_input_delay -clock cal_clk -max 0.7 [get_ports cal_start]
set_input_delay -clock cal_clk -min 0.1 [get_ports cal_start]
set_input_delay -clock cal_clk -max 0.6 [get_ports q_final]
set_input_delay -clock cal_clk -min 0.2 [get_ports q_final]

# Registered sensor-control outputs.  Their max delays are the timing budget
# used by RF6's physical-contract derivation; keeping them constrained here
# prevents an unconstrained mapped output from masking a controller delay.
set_output_delay -clock cal_clk -max 0.4 [get_ports {sense_dff_reset sense_s_clk}]
set_output_delay -clock cal_clk -min 0.0 [get_ports {sense_dff_reset sense_s_clk}]

# Thermometer rails are registered configuration outputs.  The wildcard form
# covers every bit without adding per-bit special cases or changing the rail
# architecture that RF6 validated physically.
set_output_delay -clock cal_clk -max 0.3 [get_ports {medium_therm* fine_therm*}]
set_output_delay -clock cal_clk -min 0.0 [get_ports {medium_therm* fine_therm*}]

# Registered status/debug outputs are externally observed but do not create
# sensor events.  They keep the same environment as the accepted controller.
set_output_delay -clock cal_clk -max 0.5 [get_ports {cal_busy cal_done cal_fail lock_valid}]
set_output_delay -clock cal_clk -min 0.0 [get_ports {cal_busy cal_done cal_fail lock_valid}]
set_output_delay -clock cal_clk -max 0.6 [get_ports {medium_code* fine_code* fail_reason* fsm_state*}]
set_output_delay -clock cal_clk -min 0.0 [get_ports {medium_code* fine_code* fail_reason* fsm_state*}]

# The physical library and system-level environment bound these design rules.
# No multi-cycle exception is introduced: all internal controller paths must
# close in one 400 MHz calibration-clock cycle.
set_max_fanout 16 [current_design]
set_max_transition 0.2 [current_design]
set_max_capacitance 0.1 [current_design]
