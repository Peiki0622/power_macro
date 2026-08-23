###################################################################

# Created by write_sdc on Sun Aug 23 12:07:29 2026

###################################################################
set sdc_version 2.1

set_units -time ns -resistance kOhm -capacitance pF -voltage V -current mA
set_max_capacitance 0.1 [current_design]
set_max_transition 0.25 [current_design]
set_max_fanout 16 [current_design]
create_clock [get_ports cal_clk_i]  -name cal_clk  -period 2.5  -waveform {0 1.25}
set_clock_uncertainty -setup 0.05  [get_clocks cal_clk]
set_clock_uncertainty -hold 0.02  [get_clocks cal_clk]
set_clock_transition -max -rise 0.05 [get_clocks cal_clk]
set_clock_transition -max -fall 0.05 [get_clocks cal_clk]
set_clock_transition -min -rise 0.05 [get_clocks cal_clk]
set_clock_transition -min -fall 0.05 [get_clocks cal_clk]
set_input_delay -clock cal_clk  -max 0.6  [get_ports cal_cfg_valid_i]
set_input_delay -clock cal_clk  -min 0.1  [get_ports cal_cfg_valid_i]
set_input_delay -clock cal_clk  -max 0.6  [get_ports det_prepare_i]
set_input_delay -clock cal_clk  -min 0.1  [get_ports det_prepare_i]
set_input_delay -clock cal_clk  -max 0.6  [get_ports det_owner_valid_i]
set_input_delay -clock cal_clk  -min 0.1  [get_ports det_owner_valid_i]
set_input_delay -clock cal_clk  -max 0.6  [get_ports handoff_blocked_i]
set_input_delay -clock cal_clk  -min 0.1  [get_ports handoff_blocked_i]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_code_snapshot_i[4]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_code_snapshot_i[4]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_code_snapshot_i[3]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_code_snapshot_i[3]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_code_snapshot_i[2]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_code_snapshot_i[2]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_code_snapshot_i[1]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_code_snapshot_i[1]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_code_snapshot_i[0]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_code_snapshot_i[0]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_fine_code_snapshot_i[3]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_fine_code_snapshot_i[3]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_fine_code_snapshot_i[2]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_fine_code_snapshot_i[2]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_fine_code_snapshot_i[1]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_fine_code_snapshot_i[1]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_fine_code_snapshot_i[0]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_fine_code_snapshot_i[0]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[15]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[15]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[14]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[14]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[13]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[13]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[12]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[12]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[11]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[11]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[10]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[10]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[9]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[9]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[8]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[8]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[7]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[7]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[6]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[6]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[5]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[5]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[4]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[4]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[3]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[3]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[2]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[2]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[1]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[1]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_medium_therm_snapshot_i[0]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_medium_therm_snapshot_i[0]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_fine_therm_snapshot_i[9]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_fine_therm_snapshot_i[9]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_fine_therm_snapshot_i[8]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_fine_therm_snapshot_i[8]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_fine_therm_snapshot_i[7]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_fine_therm_snapshot_i[7]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_fine_therm_snapshot_i[6]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_fine_therm_snapshot_i[6]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_fine_therm_snapshot_i[5]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_fine_therm_snapshot_i[5]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_fine_therm_snapshot_i[4]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_fine_therm_snapshot_i[4]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_fine_therm_snapshot_i[3]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_fine_therm_snapshot_i[3]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_fine_therm_snapshot_i[2]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_fine_therm_snapshot_i[2]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_fine_therm_snapshot_i[1]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_fine_therm_snapshot_i[1]}]
set_input_delay -clock cal_clk  -max 0.3  [get_ports {cal_fine_therm_snapshot_i[0]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {cal_fine_therm_snapshot_i[0]}]
set_input_delay -clock cal_clk  -max 0.5  [get_ports {margin_sel_i[1]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {margin_sel_i[1]}]
set_input_delay -clock cal_clk  -max 0.5  [get_ports {margin_sel_i[0]}]
set_input_delay -clock cal_clk  -min 0  [get_ports {margin_sel_i[0]}]
set_input_delay -clock cal_clk  -max 0.5  [get_ports margin_select_valid_i]
set_input_delay -clock cal_clk  -min 0  [get_ports margin_select_valid_i]
set_output_delay -clock cal_clk  -max 0.4  [get_ports det_takeover_ready_o]
set_output_delay -clock cal_clk  -min 0  [get_ports det_takeover_ready_o]
set_output_delay -clock cal_clk  -max 0.4  [get_ports det_sense_dff_reset_o]
set_output_delay -clock cal_clk  -min 0  [get_ports det_sense_dff_reset_o]
set_output_delay -clock cal_clk  -max 0.4  [get_ports det_sense_s_clk_o]
set_output_delay -clock cal_clk  -min 0  [get_ports det_sense_s_clk_o]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[15]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[15]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[14]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[14]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[13]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[13]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[12]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[12]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[11]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[11]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[10]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[10]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[9]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[9]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[8]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[8]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[7]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[7]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[6]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[6]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[5]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[5]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[4]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[4]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[3]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[3]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[2]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[2]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[1]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[1]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_medium_therm_o[0]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_medium_therm_o[0]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_fine_therm_o[9]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_fine_therm_o[9]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_fine_therm_o[8]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_fine_therm_o[8]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_fine_therm_o[7]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_fine_therm_o[7]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_fine_therm_o[6]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_fine_therm_o[6]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_fine_therm_o[5]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_fine_therm_o[5]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_fine_therm_o[4]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_fine_therm_o[4]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_fine_therm_o[3]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_fine_therm_o[3]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_fine_therm_o[2]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_fine_therm_o[2]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_fine_therm_o[1]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_fine_therm_o[1]}]
set_output_delay -clock cal_clk  -max 0.5  [get_ports {det_fine_therm_o[0]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {det_fine_therm_o[0]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports margin_cfg_valid_o]
set_output_delay -clock cal_clk  -min 0  [get_ports margin_cfg_valid_o]
set_output_delay -clock cal_clk  -max 0.6  [get_ports mapping_supported_o]
set_output_delay -clock cal_clk  -min 0  [get_ports mapping_supported_o]
set_output_delay -clock cal_clk  -max 0.6  [get_ports trip_qualified_o]
set_output_delay -clock cal_clk  -min 0  [get_ports trip_qualified_o]
set_output_delay -clock cal_clk  -max 0.6  [get_ports margin_protocol_error_o]
set_output_delay -clock cal_clk  -min 0  [get_ports margin_protocol_error_o]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {m_det_o[4]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {m_det_o[4]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {m_det_o[3]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {m_det_o[3]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {m_det_o[2]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {m_det_o[2]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {m_det_o[1]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {m_det_o[1]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {m_det_o[0]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {m_det_o[0]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {f_det_o[3]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {f_det_o[3]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {f_det_o[2]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {f_det_o[2]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {f_det_o[1]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {f_det_o[1]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {f_det_o[0]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {f_det_o[0]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {margin_level_o[1]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {margin_level_o[1]}]
set_output_delay -clock cal_clk  -max 0.6  [get_ports {margin_level_o[0]}]
set_output_delay -clock cal_clk  -min 0  [get_ports {margin_level_o[0]}]
set_input_transition -max 0.1  [get_ports ctrl_por_n_i]
set_input_transition -min 0.1  [get_ports ctrl_por_n_i]
set_false_path   -from [get_ports ctrl_por_n_i]  -to [list [get_cells {det_medium_therm_q_reg[0]}] [get_cells                  \
{det_medium_therm_q_reg[1]}] [get_cells {det_medium_therm_q_reg[2]}]           \
[get_cells {det_medium_therm_q_reg[3]}] [get_cells                             \
{det_medium_therm_q_reg[4]}] [get_cells {det_medium_therm_q_reg[5]}]           \
[get_cells {det_medium_therm_q_reg[6]}] [get_cells                             \
{det_medium_therm_q_reg[7]}] [get_cells {det_medium_therm_q_reg[8]}]           \
[get_cells {det_medium_therm_q_reg[9]}] [get_cells                             \
{det_medium_therm_q_reg[10]}] [get_cells {det_medium_therm_q_reg[11]}]         \
[get_cells {det_medium_therm_q_reg[12]}] [get_cells                            \
{det_medium_therm_q_reg[13]}] [get_cells {det_medium_therm_q_reg[14]}]         \
[get_cells {det_medium_therm_q_reg[15]}] [get_cells                            \
{target_fine_therm_q_reg[0]}] [get_cells {target_fine_therm_q_reg[1]}]         \
[get_cells {target_fine_therm_q_reg[2]}] [get_cells                            \
{target_fine_therm_q_reg[3]}] [get_cells {target_fine_therm_q_reg[4]}]         \
[get_cells {target_fine_therm_q_reg[5]}] [get_cells                            \
{target_fine_therm_q_reg[6]}] [get_cells {target_fine_therm_q_reg[7]}]         \
[get_cells {target_fine_therm_q_reg[8]}] [get_cells                            \
{target_fine_therm_q_reg[9]}] [get_cells {target_medium_therm_q_reg[0]}]       \
[get_cells {target_medium_therm_q_reg[1]}] [get_cells                          \
{target_medium_therm_q_reg[2]}] [get_cells {target_medium_therm_q_reg[3]}]     \
[get_cells {target_medium_therm_q_reg[4]}] [get_cells                          \
{target_medium_therm_q_reg[5]}] [get_cells {target_medium_therm_q_reg[6]}]     \
[get_cells {target_medium_therm_q_reg[7]}] [get_cells                          \
{target_medium_therm_q_reg[8]}] [get_cells {target_medium_therm_q_reg[9]}]     \
[get_cells {target_medium_therm_q_reg[10]}] [get_cells                         \
{target_medium_therm_q_reg[11]}] [get_cells {target_medium_therm_q_reg[12]}]   \
[get_cells {target_medium_therm_q_reg[13]}] [get_cells                         \
{target_medium_therm_q_reg[14]}] [get_cells {target_medium_therm_q_reg[15]}]   \
[get_cells margin_cfg_valid_q_reg] [get_cells margin_protocol_error_q_reg]     \
[get_cells snapshot_loaded_q_reg] [get_cells {margin_level_q_reg[0]}]          \
[get_cells {margin_level_q_reg[1]}] [get_cells {f_det_q_reg[0]}] [get_cells    \
{f_det_q_reg[1]}] [get_cells {f_det_q_reg[2]}] [get_cells {f_det_q_reg[3]}]    \
[get_cells {m_det_q_reg[0]}] [get_cells {m_det_q_reg[1]}] [get_cells           \
{m_det_q_reg[2]}] [get_cells {m_det_q_reg[3]}] [get_cells {m_det_q_reg[4]}]    \
[get_cells trip_qualified_q_reg] [get_cells mapping_supported_q_reg]           \
[get_cells {state_q_reg[0]}] [get_cells {state_q_reg[1]}] [get_cells           \
{state_q_reg[2]}] [get_cells {state_q_reg[3]}] [get_cells                      \
{det_fine_therm_q_reg[0]}] [get_cells {det_fine_therm_q_reg[1]}] [get_cells    \
{det_fine_therm_q_reg[2]}] [get_cells {det_fine_therm_q_reg[3]}] [get_cells    \
{det_fine_therm_q_reg[4]}] [get_cells {det_fine_therm_q_reg[5]}] [get_cells    \
{det_fine_therm_q_reg[6]}] [get_cells {det_fine_therm_q_reg[7]}] [get_cells    \
{det_fine_therm_q_reg[8]}] [get_cells {det_fine_therm_q_reg[9]}]]
