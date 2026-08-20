# ============================================================================
# FTC Calibration Controller - Synthesis Timing Constraints (SDC)
# ============================================================================
# Target: 1 GHz control clock (1.0 ns period)
# Technology: TSMC library (to be specified by tool setup)
#
# Constraints cover:
#   - Clock definition and uncertainty
#   - Input/output delays
#   - False paths for asynchronous signals
#   - Multi-cycle paths (if needed)
#   - Load constraints for outputs
#
# Phase: 7 - Controller synthesis
# Date: 2026-08-20
# ============================================================================

# =========================================================================
# Clock Definition
# =========================================================================
# Main control clock: 1 GHz (1.0 ns period)
create_clock -name cal_clk -period 1.0 [get_ports cal_clk]

# Clock uncertainty: model jitter and skew
# Conservative estimate: 50 ps (5% of period)
set_clock_uncertainty -setup 0.05 [get_clocks cal_clk]
set_clock_uncertainty -hold 0.02 [get_clocks cal_clk]

# Clock transition time
set_clock_transition 0.05 [get_clocks cal_clk]

# =========================================================================
# Input Constraints
# =========================================================================
# Asynchronous reset input - no timing constraint needed, but set max transition
set_input_transition 0.1 [get_ports ctrl_por_n]

# Calibration start - synchronous to cal_clk, arrives shortly after clock edge
# Assume external logic provides signal with 0.3 ns setup margin
set_input_delay -clock cal_clk -max 0.7 [get_ports cal_start]
set_input_delay -clock cal_clk -min 0.1 [get_ports cal_start]

# Q final from sensor - critical timing path
# Sensor Q is sampled on cal_clk edge, assume it arrives with sufficient setup
# Sensor has its own clock domain, but we sample synchronously
# Conservative: require Q stable 0.4 ns before cal_clk edge
set_input_delay -clock cal_clk -max 0.6 [get_ports q_final]
set_input_delay -clock cal_clk -min 0.2 [get_ports q_final]

# =========================================================================
# Output Constraints
# =========================================================================
# All outputs are registered and drive sensor or external logic
# Assume external loads similar to 4x standard cell input capacitance

# Sensor control outputs - drive sensor DFF and S_CLK
set_output_delay -clock cal_clk -max 0.4 [get_ports sense_dff_reset]
set_output_delay -clock cal_clk -min 0.0 [get_ports sense_dff_reset]

set_output_delay -clock cal_clk -max 0.4 [get_ports sense_s_clk]
set_output_delay -clock cal_clk -min 0.0 [get_ports sense_s_clk]

# Thermometer code outputs - drive sensor delay chain
# These are critical - must be stable before sensor reset is released
set_output_delay -clock cal_clk -max 0.3 [get_ports medium_therm*]
set_output_delay -clock cal_clk -min 0.0 [get_ports medium_therm*]

set_output_delay -clock cal_clk -max 0.3 [get_ports fine_therm*]
set_output_delay -clock cal_clk -min 0.0 [get_ports fine_therm*]

# Status outputs - less critical, observed by external logic
set_output_delay -clock cal_clk -max 0.5 [get_ports cal_busy]
set_output_delay -clock cal_clk -min 0.0 [get_ports cal_busy]

set_output_delay -clock cal_clk -max 0.5 [get_ports cal_done]
set_output_delay -clock cal_clk -min 0.0 [get_ports cal_done]

set_output_delay -clock cal_clk -max 0.5 [get_ports cal_fail]
set_output_delay -clock cal_clk -min 0.0 [get_ports cal_fail]

set_output_delay -clock cal_clk -max 0.5 [get_ports lock_valid]
set_output_delay -clock cal_clk -min 0.0 [get_ports lock_valid]

# Debug outputs (if present)
set_output_delay -clock cal_clk -max 0.6 [get_ports medium_code*]
set_output_delay -clock cal_clk -min 0.0 [get_ports medium_code*]

set_output_delay -clock cal_clk -max 0.6 [get_ports fine_code*]
set_output_delay -clock cal_clk -min 0.0 [get_ports fine_code*]

set_output_delay -clock cal_clk -max 0.6 [get_ports fail_reason*]
set_output_delay -clock cal_clk -min 0.0 [get_ports fail_reason*]

set_output_delay -clock cal_clk -max 0.6 [get_ports fsm_state*]
set_output_delay -clock cal_clk -min 0.0 [get_ports fsm_state*]

# =========================================================================
# Load Constraints
# =========================================================================
# Assume all outputs drive equivalent of 4 standard cell inputs
# Load value will be set by technology-specific setup
# Placeholder: set_load 0.02 [all_outputs]

# =========================================================================
# False Paths
# =========================================================================
# Asynchronous reset - no timing check on reset assertion
set_false_path -from [get_ports ctrl_por_n] -to [all_registers]

# =========================================================================
# Case Analysis (Constant Inputs)
# =========================================================================
# None - all inputs are functional

# =========================================================================
# Multi-Cycle Paths
# =========================================================================
# None expected - all paths should meet single-cycle timing

# =========================================================================
# Design Rule Constraints
# =========================================================================
# Maximum fanout per net
set_max_fanout 16 [current_design]

# Maximum transition time on nets
set_max_transition 0.2 [current_design]

# Maximum capacitance on nets
set_max_capacitance 0.1 [current_design]

# =========================================================================
# Area Constraint
# =========================================================================
# No hard area constraint - optimize for timing first
# set_max_area 0

# =========================================================================
# Operating Conditions
# =========================================================================
# Will be set by technology library setup
# Typical: worst-case corner for setup, best-case for hold

# =========================================================================
# End of Constraints
# =========================================================================
