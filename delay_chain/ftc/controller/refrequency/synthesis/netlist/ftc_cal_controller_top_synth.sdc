###################################################################

# Created by write_sdc on Sat Aug 22 14:46:42 2026

###################################################################
set sdc_version 2.1

set_units -time ns -resistance kOhm -capacitance pF -voltage V -current mA
set_operating_conditions ss_typical_max_0p99v_125c -library                    \
sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c
set_max_capacitance 0.1 [current_design]
set_max_transition 0.2 [current_design]
set_max_fanout 16 [current_design]
create_clock [get_ports cal_clk]  -period 2.5  -waveform {0 1.25}
set_clock_uncertainty -setup 0.05  [get_clocks cal_clk]
set_clock_uncertainty -hold 0.02  [get_clocks cal_clk]
set_clock_transition -max -rise 0.05 [get_clocks cal_clk]
set_clock_transition -max -fall 0.05 [get_clocks cal_clk]
set_clock_transition -min -rise 0.05 [get_clocks cal_clk]
set_clock_transition -min -fall 0.05 [get_clocks cal_clk]
set_false_path   -from [get_ports ctrl_por_n]  -to [list [get_cells u_fsm/cal_fail_q_reg] [get_cells u_fsm/cal_done_q_reg]   \
[get_cells u_fsm/cal_busy_q_reg] [get_cells u_fsm/seq_fine_dec_q_reg]          \
[get_cells u_fsm/seq_fine_inc_q_reg] [get_cells u_fsm/seq_medium_dec_q_reg]    \
[get_cells u_fsm/seq_medium_inc_q_reg] [get_cells {u_fsm/seq_cmd_q_reg[0]}]    \
[get_cells {u_fsm/seq_cmd_q_reg[1]}] [get_cells u_fsm/seq_req_q_reg]           \
[get_cells {u_fsm/fail_reason_q_reg[0]}] [get_cells                            \
{u_fsm/fail_reason_q_reg[1]}] [get_cells {u_fsm/fail_reason_q_reg[2]}]         \
[get_cells {u_fsm/fine_probe_result_q_reg[0]}] [get_cells                      \
{u_fsm/fine_probe_result_q_reg[1]}] [get_cells                                 \
{u_fsm/coarse_probe_b_result_q_reg[0]}] [get_cells                             \
{u_fsm/coarse_probe_b_result_q_reg[1]}] [get_cells                             \
{u_fsm/coarse_probe_a_result_q_reg[0]}] [get_cells                             \
{u_fsm/coarse_probe_a_result_q_reg[1]}] [get_cells {u_fsm/state_q_reg[0]}]     \
[get_cells {u_fsm/state_q_reg[1]}] [get_cells {u_fsm/state_q_reg[2]}]          \
[get_cells {u_fsm/state_q_reg[3]}] [get_cells {u_fsm/state_q_reg[4]}]          \
[get_cells u_fsm/lock_valid_q_reg] [get_cells                                  \
{u_sequencer/probe_count_q_reg[0]}] [get_cells                                 \
{u_sequencer/probe_count_q_reg[1]}] [get_cells                                 \
{u_sequencer/probe_count_q_reg[2]}] [get_cells                                 \
{u_sequencer/probe_count_q_reg[3]}] [get_cells                                 \
u_sequencer/probe_start_event_o_reg] [get_cells                                \
u_sequencer/config_update_event_o_reg] [get_cells                              \
u_sequencer/q_class_valid_o_reg] [get_cells                                    \
u_sequencer/q_sample_2_event_o_reg] [get_cells                                 \
u_sequencer/q_sample_1_event_o_reg] [get_cells u_sequencer/probe_done_o_reg]   \
[get_cells u_sequencer/done_o_reg] [get_cells u_sequencer/busy_o_reg]          \
[get_cells u_sequencer/cfg_fine_dec_o_reg] [get_cells                          \
u_sequencer/cfg_fine_inc_o_reg] [get_cells u_sequencer/cfg_medium_dec_o_reg]   \
[get_cells u_sequencer/cfg_medium_inc_o_reg] [get_cells                        \
u_sequencer/sense_s_clk_o_reg] [get_cells u_sequencer/sense_dff_reset_o_reg]   \
[get_cells {u_sequencer/active_cmd_q_reg[0]}] [get_cells                       \
{u_sequencer/active_cmd_q_reg[1]}] [get_cells                                  \
{u_sequencer/u_q_sampler/q_class_o_reg[0]}] [get_cells                         \
{u_sequencer/u_q_sampler/q_class_o_reg[1]}] [get_cells                         \
u_sequencer/u_q_sampler/q_sample_2_o_reg] [get_cells                           \
u_sequencer/u_q_sampler/q_sample_1_o_reg] [get_cells                           \
u_sequencer/u_q_sampler/class_valid_o_reg] [get_cells                          \
{u_cfg_regs/fine_code_o_reg[0]}] [get_cells {u_cfg_regs/fine_code_o_reg[1]}]   \
[get_cells {u_cfg_regs/fine_code_o_reg[2]}] [get_cells                         \
{u_cfg_regs/fine_code_o_reg[3]}] [get_cells {u_cfg_regs/medium_code_o_reg[0]}] \
[get_cells {u_cfg_regs/medium_code_o_reg[1]}] [get_cells                       \
{u_cfg_regs/medium_code_o_reg[2]}] [get_cells                                  \
{u_cfg_regs/medium_code_o_reg[3]}] [get_cells                                  \
{u_cfg_regs/medium_code_o_reg[4]}] [get_cells                                  \
{u_cfg_regs/fine_therm_o_reg[0]}] [get_cells {u_cfg_regs/fine_therm_o_reg[1]}] \
[get_cells {u_cfg_regs/fine_therm_o_reg[2]}] [get_cells                        \
{u_cfg_regs/fine_therm_o_reg[3]}] [get_cells {u_cfg_regs/fine_therm_o_reg[4]}] \
[get_cells {u_cfg_regs/fine_therm_o_reg[5]}] [get_cells                        \
{u_cfg_regs/fine_therm_o_reg[6]}] [get_cells {u_cfg_regs/fine_therm_o_reg[7]}] \
[get_cells {u_cfg_regs/fine_therm_o_reg[8]}] [get_cells                        \
{u_cfg_regs/fine_therm_o_reg[9]}] [get_cells                                   \
{u_cfg_regs/medium_therm_o_reg[0]}] [get_cells                                 \
{u_cfg_regs/medium_therm_o_reg[1]}] [get_cells                                 \
{u_cfg_regs/medium_therm_o_reg[2]}] [get_cells                                 \
{u_cfg_regs/medium_therm_o_reg[3]}] [get_cells                                 \
{u_cfg_regs/medium_therm_o_reg[4]}] [get_cells                                 \
{u_cfg_regs/medium_therm_o_reg[5]}] [get_cells                                 \
{u_cfg_regs/medium_therm_o_reg[6]}] [get_cells                                 \
{u_cfg_regs/medium_therm_o_reg[7]}] [get_cells                                 \
{u_cfg_regs/medium_therm_o_reg[8]}] [get_cells                                 \
{u_cfg_regs/medium_therm_o_reg[9]}] [get_cells                                 \
{u_cfg_regs/medium_therm_o_reg[10]}] [get_cells                                \
{u_cfg_regs/medium_therm_o_reg[11]}] [get_cells                                \
{u_cfg_regs/medium_therm_o_reg[12]}] [get_cells                                \
{u_cfg_regs/medium_therm_o_reg[13]}] [get_cells                                \
{u_cfg_regs/medium_therm_o_reg[14]}] [get_cells                                \
{u_cfg_regs/medium_therm_o_reg[15]}] [get_cells u_cfg_regs/cfg_locked_o_reg]]
set_input_delay -clock cal_clk  -max 0.7  [get_ports cal_start]
set_input_delay -clock cal_clk  -min 0.1  [get_ports cal_start]
set_input_delay -clock cal_clk  -max 0.6  [get_ports q_final]
set_input_delay -clock cal_clk  -min 0.2  [get_ports q_final]
set_output_delay -clock cal_clk  -max 0.4  [get_ports sense_dff_reset]
set_output_delay -clock cal_clk  -min 0  [get_ports sense_dff_reset]
set_output_delay -clock cal_clk  -max 0.4  [get_ports sense_s_clk]
set_output_delay -clock cal_clk  -min 0  [get_ports sense_s_clk]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[15]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[15]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[14]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[14]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[13]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[13]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[12]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[12]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[11]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[11]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[10]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[10]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[9]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[9]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[8]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[8]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[7]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[7]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[6]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[6]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[5]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[5]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[4]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[4]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[3]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[3]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[2]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[2]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[1]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[1]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {medium_therm[0]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_therm[0]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {fine_therm[9]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fine_therm[9]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {fine_therm[8]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fine_therm[8]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {fine_therm[7]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fine_therm[7]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {fine_therm[6]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fine_therm[6]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {fine_therm[5]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fine_therm[5]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {fine_therm[4]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fine_therm[4]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {fine_therm[3]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fine_therm[3]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {fine_therm[2]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fine_therm[2]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {fine_therm[1]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fine_therm[1]}]
set_output_delay -clock cal_clk  -max 0.3  [get_ports {fine_therm[0]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fine_therm[0]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports cal_busy]
set_output_delay -clock cal_clk  -min 0  [get_ports cal_busy]
set_output_delay -clock cal_clk  -max 0.5  [get_ports cal_done]
set_output_delay -clock cal_clk  -min 0  [get_ports cal_done]
set_output_delay -clock cal_clk  -max 0.5  [get_ports cal_fail]
set_output_delay -clock cal_clk  -min 0  [get_ports cal_fail]
set_output_delay -clock cal_clk  -max 0.5  [get_ports lock_valid]
set_output_delay -clock cal_clk  -min 0  [get_ports lock_valid]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {medium_code[4]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_code[4]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {medium_code[3]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_code[3]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {medium_code[2]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_code[2]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {medium_code[1]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_code[1]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {medium_code[0]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {medium_code[0]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {fine_code[3]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fine_code[3]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {fine_code[2]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fine_code[2]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {fine_code[1]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fine_code[1]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {fine_code[0]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fine_code[0]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {fail_reason[2]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fail_reason[2]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {fail_reason[1]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fail_reason[1]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {fail_reason[0]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fail_reason[0]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {fsm_state[4]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fsm_state[4]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {fsm_state[3]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fsm_state[3]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {fsm_state[2]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fsm_state[2]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {fsm_state[1]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fsm_state[1]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {fsm_state[0]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {fsm_state[0]}]
set_input_transition -max 0.1  [get_ports ctrl_por_n]
set_input_transition -min 0.1  [get_ports ctrl_por_n]
