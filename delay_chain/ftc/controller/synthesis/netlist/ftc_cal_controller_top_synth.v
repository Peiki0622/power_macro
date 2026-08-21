/////////////////////////////////////////////////////////////
// Created by: Synopsys DC Ultra(TM) in wire load mode
// Version   : W-2024.09
// Date      : Thu Aug 20 13:49:36 2026
/////////////////////////////////////////////////////////////


module ftc_cal_controller_top ( cal_clk, ctrl_por_n, cal_start, q_final, 
        sense_dff_reset, sense_s_clk, medium_therm, fine_therm, cal_busy, 
        cal_done, cal_fail, lock_valid, medium_code, fine_code, fail_reason, 
        fsm_state, q_sample_1_event, q_sample_2_event, config_update_event, 
        probe_start_event );
  output [15:0] medium_therm;
  output [9:0] fine_therm;
  output [4:0] medium_code;
  output [3:0] fine_code;
  output [2:0] fail_reason;
  output [4:0] fsm_state;
  input cal_clk, ctrl_por_n, cal_start, q_final;
  output sense_dff_reset, sense_s_clk, cal_busy, cal_done, cal_fail,
         lock_valid, q_sample_1_event, q_sample_2_event, config_update_event,
         probe_start_event;
  wire   \q_class[1] , \u_sequencer/N62 , \u_sequencer/N61 , \u_sequencer/N59 ,
         \u_sequencer/N57 , \u_sequencer/N56 , \u_sequencer/N55 ,
         \u_sequencer/N43 , \u_sequencer/sample_2_fire ,
         \u_sequencer/u_q_sampler/n1 , n257, n258, n260, n261, n262, n264,
         n265, n266, n267, n269, n270, n272, n273, n274, n275, n276, n277,
         n278, n279, n280, n281, n282, n283, n284, n285, n286, n287, n288,
         n289, n290, n291, n292, n293, n294, n295, n296, n297, n298, n299,
         n300, n301, n302, n303, n304, n305, n306, n307, n308, n309, n311,
         n312, n313, n314, n315, n316, n317, n318, n319, n320, n321, n322,
         n324, n325, n326, n327, n328, n329, n330, n331, n332, n333, n334,
         n335, n336, n337, n338, n339, n340, n341, n342, n343, n344, n346,
         n347, n348, n349, n350, n351, n352, n353, n354, n355, n356, n357,
         n358, n359, n360, n362, n363, n364, n365, n366, n367, n368, n369,
         n370, n371, n372, n373, n374, n375, n376, n377, n378, n379, n382,
         n383, n384, n386, n388, n389, n390, n391, n393, n395, n396, n398,
         n399, n400, n401, n402, n403, \fsm_state[4] , n406, n407, n408, n409,
         n410, n411, n412, n413, n414, n415, n416, n417, n418, n419, n420,
         n421, n422, n423, n424, n425, n426, n427, n428, n429, n430, n431,
         n432, n433, n434, n435, n436, n437, n438, n439, n440, n441, n442,
         n443, n444, n445, n446, n447, n448, n449, n450, n451, n452, n453,
         n454, n455, n456, n457, n458, n459, n460, n461, n462, n463, n464,
         n465, n466, n467, n468, n469, n470, n471, n472, n473, n474, n475,
         n476, n477, n478, n479, n480, n481, n482, n483, n484, n485, n486,
         n487, n488, n489, n490, n491, n492, n493, n494, n496, n497, n498,
         n499, n500, n501, n502, n503, n504, n505, n506, n507, n508, n509,
         n510, n511, n512, n513, n514, n515, n516, n517, n518, n519, n520,
         n521, n522, n523, n524, n525, n526, n527, n528, n529, n530, n531,
         n532, n533, n534, n535, n536, n537, n538, n539, n540, n541, n542,
         n543, n544, n545, n546, n547, n548, n549, n550, n551, n552, n553,
         n554, n555, n556, n557, n558, n559, n560, n561, n562, n563, n564,
         n565, n566, n567, n568, n569, n570, n571, n572, n573, n574, n575,
         n576, n577, n578, n579, n580, n581, n582, n583, n584, n585, n586,
         n587, n588, n589, n590, n591, n592, n593, n594, n595, n596, n597,
         n598, n599, n600, n601, n602, n603, n604, n605, n606, n607, n608,
         n609, n610, n611, n612, n613, n614, n615, n616, n617, n618, n619,
         n620, n621, n622, n623, n624, n625, n626, n627, n628, n629, n630,
         n631, n632, n633, n634, n635, n636, n637, n638, n639, n640, n641,
         n642, n643, n644, n645, n646, n647, n648, n649, n650, n651, n652,
         n653, n654, n655, n656, n657, n658, n659, n660, n661, n662, n663,
         n664, n665, n666, n667, n668, n669, n670, n671, n672, n673, n674,
         n675, n676, n677, n678, n679, n680, n681, n682, n683, n684, n685,
         n686, n687, n688, n689, n690, n691, n692, n693, n694, n695, n696,
         n697, n698, n699, n700, n701, n702, n703, n704, n705, n706, n707,
         n708, n709, n710, n711, n712, n713, n714, n715, n716, n717, n718,
         n719, n720, n721, n722, n723, n724, n725, n726, n727, n728, n729,
         n730, n731, n732, n733, n734, n735, n736, n737, n738, n739, n740,
         n741, n742, n743, n744, n745, n746, n747, n748, n749, n750, n751,
         n752, n753, n754, n755, n756, n757, n758, n759, n760, n761, n762,
         n763, n764, n765, n766, n767, n768, n769, n770, n771, n772, n773,
         n774, n775, n776, n777, n778, n779, n784, n785, n786, n787, n788,
         n789, n790, n791, n792, n793, n809, n810;
  assign medium_therm[15] = \fsm_state[4] ;
  assign fsm_state[4] = \fsm_state[4] ;

  DFFRPQN_X0P5M_A9TR40 \u_sequencer/u_q_sampler/class_valid_o_reg  ( .D(
        \u_sequencer/sample_2_fire ), .CK(cal_clk), .R(n788), .QN(n327) );
  DFFRPQN_X1M_A9TR40 \u_fsm/coarse_probe_a_result_q_reg[1]  ( .D(n331), .CK(
        cal_clk), .R(n787), .QN(n325) );
  DFFRPQN_X2M_A9TR40 \u_sequencer/active_cmd_q_reg[1]  ( .D(n389), .CK(cal_clk), .R(n788), .QN(n322) );
  DFFRPQN_X2M_A9TR40 \u_sequencer/done_o_reg  ( .D(\u_sequencer/N59 ), .CK(
        cal_clk), .R(n788), .QN(n320) );
  DFFRPQN_X0P5M_A9TR40 \u_fsm/seq_fine_inc_q_reg  ( .D(n330), .CK(cal_clk), 
        .R(n810), .QN(n318) );
  DFFRPQN_X0P5M_A9TR40 \u_sequencer/cfg_fine_inc_o_reg  ( .D(\u_sequencer/N57 ), .CK(cal_clk), .R(n790), .QN(n317) );
  DFFRPQN_X2M_A9TR40 \u_fsm/state_q_reg[2]  ( .D(n383), .CK(cal_clk), .R(n810), 
        .QN(n315) );
  DFFRPQN_X2M_A9TR40 \u_fsm/state_q_reg[0]  ( .D(n785), .CK(cal_clk), .R(n788), 
        .QN(n312) );
  DFFRPQN_X2M_A9TR40 \u_sequencer/probe_count_q_reg[0]  ( .D(n393), .CK(
        cal_clk), .R(n788), .QN(n308) );
  DFFRPQN_X2M_A9TR40 \u_fsm/state_q_reg[3]  ( .D(n386), .CK(cal_clk), .R(n787), 
        .QN(n302) );
  DFFRPQN_X0P5M_A9TR40 \u_fsm/seq_medium_inc_q_reg  ( .D(n382), .CK(cal_clk), 
        .R(n787), .QN(n301) );
  DFFRPQN_X2M_A9TR40 \u_sequencer/cfg_medium_inc_o_reg  ( .D(\u_sequencer/N55 ), .CK(cal_clk), .R(n787), .QN(n300) );
  DFFRPQN_X2M_A9TR40 \u_cfg_regs/cfg_locked_o_reg  ( .D(n453), .CK(cal_clk), 
        .R(n810), .QN(n299) );
  DFFRPQN_X2M_A9TR40 \u_cfg_regs/fine_code_o_reg[0]  ( .D(n379), .CK(cal_clk), 
        .R(n810), .QN(n298) );
  DFFRPQN_X2M_A9TR40 \u_cfg_regs/fine_code_o_reg[2]  ( .D(n377), .CK(cal_clk), 
        .R(n810), .QN(n296) );
  DFFRPQN_X1M_A9TR40 \u_fsm/coarse_probe_a_result_q_reg[0]  ( .D(n334), .CK(
        cal_clk), .R(n787), .QN(n294) );
  DFFRPQN_X1M_A9TR40 \u_fsm/fine_probe_result_q_reg[0]  ( .D(n336), .CK(
        cal_clk), .R(n788), .QN(n293) );
  DFFRPQN_X1M_A9TR40 \u_fsm/coarse_probe_b_result_q_reg[0]  ( .D(n335), .CK(
        cal_clk), .R(n787), .QN(n291) );
  DFFRPQN_X1M_A9TR40 \u_fsm/coarse_probe_b_result_q_reg[1]  ( .D(n332), .CK(
        cal_clk), .R(n787), .QN(n290) );
  DFFRPQN_X0P5M_A9TR40 \u_fsm/seq_medium_dec_q_reg  ( .D(n793), .CK(cal_clk), 
        .R(n787), .QN(n289) );
  DFFRPQN_X2M_A9TR40 \u_cfg_regs/medium_therm_o_reg[0]  ( .D(n360), .CK(
        cal_clk), .R(n789), .QN(n283) );
  DFFRPQ_X0P5M_A9TR40 \u_sequencer/u_q_sampler/q_sample_1_o_reg  ( .D(n786), 
        .CK(cal_clk), .R(n787), .Q(\u_sequencer/u_q_sampler/n1 ) );
  DFFRPQN_X2M_A9TR40 \u_cfg_regs/medium_code_o_reg[0]  ( .D(n375), .CK(cal_clk), .R(n787), .QN(n287) );
  DFFRPQN_X2M_A9TR40 \u_cfg_regs/medium_code_o_reg[1]  ( .D(n374), .CK(cal_clk), .R(n787), .QN(n286) );
  DFFRPQN_X2M_A9TR40 \u_sequencer/probe_count_q_reg[1]  ( .D(n784), .CK(
        cal_clk), .R(n788), .QN(n307) );
  DFFRPQN_X2M_A9TR40 \u_cfg_regs/medium_code_o_reg[4]  ( .D(n371), .CK(cal_clk), .R(n787), .QN(n313) );
  DFFRPQN_X1M_A9TR40 \u_fsm/seq_cmd_q_reg[0]  ( .D(n338), .CK(cal_clk), .R(
        n788), .QN(n324) );
  DFFRPQN_X2M_A9TR40 \u_cfg_regs/fine_code_o_reg[1]  ( .D(n378), .CK(cal_clk), 
        .R(n810), .QN(n297) );
  DFFRPQN_X2M_A9TR40 \u_cfg_regs/medium_code_o_reg[2]  ( .D(n373), .CK(cal_clk), .R(n787), .QN(n285) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[4]  ( .D(n366), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[4]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[8]  ( .D(n362), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[8]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[0]  ( .D(n370), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[0]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[1]  ( .D(n369), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[1]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[2]  ( .D(n368), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[2]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[3]  ( .D(n367), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[3]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[5]  ( .D(n365), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[5]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[6]  ( .D(n364), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[6]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[7]  ( .D(n363), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[7]) );
  DFFSQ_X1M_A9TR40 \u_sequencer/sense_dff_reset_o_reg  ( .D(n328), .CK(cal_clk), .SN(ctrl_por_n), .Q(sense_dff_reset) );
  DFFRPQN_X1M_A9TR40 \u_sequencer/q_sample_1_event_o_reg  ( .D(n452), .CK(
        cal_clk), .R(n789), .QN(n305) );
  DFFRPQN_X1M_A9TR40 \u_sequencer/q_sample_2_event_o_reg  ( .D(
        \u_sequencer/N61 ), .CK(cal_clk), .R(n789), .QN(n260) );
  DFFRPQN_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[2]  ( .D(n358), .CK(
        cal_clk), .R(n790), .QN(n273) );
  DFFRPQN_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[7]  ( .D(n353), .CK(
        cal_clk), .R(n790), .QN(n269) );
  DFFRPQN_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[8]  ( .D(n352), .CK(
        cal_clk), .R(n790), .QN(n279) );
  DFFRPQN_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[4]  ( .D(n356), .CK(
        cal_clk), .R(n790), .QN(n277) );
  DFFRPQN_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[12]  ( .D(n348), .CK(
        cal_clk), .R(n790), .QN(n275) );
  DFFRPQN_X1M_A9TR40 \u_fsm/fail_reason_q_reg[0]  ( .D(n343), .CK(cal_clk), 
        .R(n789), .QN(n266) );
  DFFRPQN_X1M_A9TR40 \u_fsm/cal_done_q_reg  ( .D(n344), .CK(cal_clk), .R(n789), 
        .QN(n267) );
  DFFRPQN_X1M_A9TR40 \u_sequencer/sense_s_clk_o_reg  ( .D(n329), .CK(cal_clk), 
        .R(n789), .QN(n261) );
  DFFRPQN_X1M_A9TR40 \u_fsm/seq_cmd_q_reg[1]  ( .D(n792), .CK(cal_clk), .R(
        n789), .QN(n295) );
  DFFRPQN_X1M_A9TR40 \u_fsm/fine_probe_result_q_reg[1]  ( .D(n333), .CK(
        cal_clk), .R(n788), .QN(n292) );
  DFFRPQN_X2M_A9TR40 \u_sequencer/busy_o_reg  ( .D(n388), .CK(cal_clk), .R(
        n789), .QN(n319) );
  DFFRPQN_X2M_A9TR40 \u_fsm/state_q_reg[1]  ( .D(n384), .CK(cal_clk), .R(n788), 
        .QN(n303) );
  DFFRPQN_X3M_A9TR40 \u_fsm/fail_reason_q_reg[1]  ( .D(n342), .CK(cal_clk), 
        .R(n789), .QN(n265) );
  DFFRPQN_X2M_A9TR40 \u_sequencer/active_cmd_q_reg[0]  ( .D(n337), .CK(cal_clk), .R(n810), .QN(n304) );
  DFFRPQN_X3M_A9TR40 \u_cfg_regs/medium_code_o_reg[3]  ( .D(n372), .CK(cal_clk), .R(n787), .QN(n284) );
  DFFRPQN_X3M_A9TR40 \u_cfg_regs/medium_therm_o_reg[14]  ( .D(n346), .CK(
        cal_clk), .R(n810), .QN(n270) );
  DFFSQ_X1M_A9TR40 \u_sequencer/u_q_sampler/q_class_o_reg[1]  ( .D(n257), .CK(
        cal_clk), .SN(ctrl_por_n), .Q(\q_class[1] ) );
  DFFRPQN_X1M_A9TR40 \u_sequencer/u_q_sampler/q_class_o_reg[0]  ( .D(n258), 
        .CK(cal_clk), .R(n810), .QN(n791) );
  DFFRPQ_X1M_A9TR40 \u_sequencer/probe_start_event_o_reg  ( .D(
        \u_sequencer/N43 ), .CK(cal_clk), .R(n789), .Q(probe_start_event) );
  DFFRPQN_X1M_A9TR40 \u_cfg_regs/fine_code_o_reg[3]  ( .D(n376), .CK(cal_clk), 
        .R(n810), .QN(n316) );
  DFFRPQN_X0P5M_A9TR40 \u_cfg_regs/medium_therm_o_reg[6]  ( .D(n354), .CK(
        cal_clk), .R(n790), .QN(n272) );
  DFFRPQ_X0P5M_A9TR40 \u_sequencer/config_update_event_o_reg  ( .D(n809), .CK(
        cal_clk), .R(n789), .Q(config_update_event) );
  DFFRPQN_X1M_A9TR40 \u_sequencer/q_class_valid_o_reg  ( .D(n396), .CK(cal_clk), .R(n788), .QN(n326) );
  DFFRPQN_X1M_A9TR40 \u_sequencer/probe_done_o_reg  ( .D(\u_sequencer/N62 ), 
        .CK(cal_clk), .R(n788), .QN(n321) );
  DFFRPQN_X1M_A9TR40 \u_sequencer/cfg_medium_dec_o_reg  ( .D(\u_sequencer/N56 ), .CK(cal_clk), .R(n787), .QN(n288) );
  DFFSQ_X2M_A9TR40 \u_fsm/lock_valid_q_reg  ( .D(n455), .CK(cal_clk), .SN(
        ctrl_por_n), .Q(n314) );
  DFFRPQN_X1M_A9TR40 \u_fsm/seq_req_q_reg  ( .D(n395), .CK(cal_clk), .R(n788), 
        .QN(n311) );
  DFFRPQN_X2M_A9TR40 \u_sequencer/probe_count_q_reg[3]  ( .D(n390), .CK(
        cal_clk), .R(n810), .QN(n309) );
  DFFRPQN_X2M_A9TR40 \u_sequencer/probe_count_q_reg[2]  ( .D(n391), .CK(
        cal_clk), .R(n788), .QN(n306) );
  DFFRPQN_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[3]  ( .D(n357), .CK(
        cal_clk), .R(n790), .QN(n281) );
  DFFRPQN_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[13]  ( .D(n347), .CK(
        cal_clk), .R(n790), .QN(n274) );
  DFFRPQN_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[5]  ( .D(n355), .CK(
        cal_clk), .R(n790), .QN(n276) );
  DFFRPQN_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[1]  ( .D(n359), .CK(
        cal_clk), .R(n790), .QN(n282) );
  DFFRPQN_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[9]  ( .D(n351), .CK(
        cal_clk), .R(n790), .QN(n278) );
  DFFRPQN_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[11]  ( .D(n349), .CK(
        cal_clk), .R(n790), .QN(n280) );
  DFFRPQN_X1M_A9TR40 \u_fsm/cal_fail_q_reg  ( .D(n340), .CK(cal_clk), .R(n789), 
        .QN(n264) );
  DFFRPQN_X2M_A9TR40 \u_fsm/cal_busy_q_reg  ( .D(n339), .CK(cal_clk), .R(n789), 
        .QN(n262) );
  DFFSRPQ_X1M_A9TR40 \u_fsm/fail_reason_q_reg[2]  ( .D(n341), .CK(cal_clk), 
        .R(n789), .SN(fine_therm[9]), .Q(fail_reason[2]) );
  DFFSRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[10]  ( .D(n350), .CK(
        cal_clk), .R(n790), .SN(fine_therm[9]), .Q(medium_therm[10]) );
  OAI21_X1P4M_A9TR40 U382 ( .A0(n679), .A1(n533), .B0(n510), .Y(n374) );
  AO21B_X1M_A9TR40 U383 ( .A0(n658), .A1(n657), .B0N(n656), .Y(n341) );
  OAI21_X2M_A9TR40 U384 ( .A0(n586), .A1(n602), .B0(n585), .Y(n340) );
  OAI21_X2M_A9TR40 U385 ( .A0(n650), .A1(n649), .B0(n648), .Y(n339) );
  OAI21_X1M_A9TR40 U386 ( .A0(n551), .A1(n318), .B0(n647), .Y(n330) );
  NAND2_X1B_A9TR40 U387 ( .A(n417), .B(n416), .Y(n372) );
  NAND2_X1B_A9TR40 U388 ( .A(n415), .B(n414), .Y(n373) );
  NAND2_X1B_A9TR40 U389 ( .A(n567), .B(n566), .Y(n386) );
  AOI21_X2M_A9TR40 U390 ( .A0(n594), .A1(n267), .B0(n593), .Y(n344) );
  OAI21_X1M_A9TR40 U391 ( .A0(n575), .A1(n289), .B0(n574), .Y(n793) );
  NOR2XB_X1M_A9TR40 U392 ( .BN(n809), .A(n301), .Y(\u_sequencer/N55 ) );
  OAI211_X2M_A9TR40 U393 ( .A0(n547), .A1(n546), .B0(n647), .C0(n545), .Y(n338) );
  MXIT2_X1M_A9TR40 U394 ( .A(n534), .B(n533), .S0(medium_code[0]), .Y(n375) );
  AO21A1AI2_X1M_A9TR40 U395 ( .A0(n706), .A1(n696), .B0(n570), .C0(n482), .Y(
        n383) );
  MXIT2_X1M_A9TR40 U396 ( .A(n729), .B(n290), .S0(n734), .Y(n332) );
  AOI21_X2M_A9TR40 U397 ( .A0(n494), .A1(n493), .B0(n492), .Y(n785) );
  OAI211_X2M_A9TR40 U398 ( .A0(n603), .A1(n602), .B0(n601), .C0(n600), .Y(n342) );
  OAI21_X2M_A9TR40 U399 ( .A0(n703), .A1(n436), .B0(n435), .Y(n792) );
  MXIT2_X1M_A9TR40 U400 ( .A(n791), .B(n294), .S0(n718), .Y(n334) );
  NOR2_X2B_A9TR40 U401 ( .A(n561), .B(n684), .Y(n764) );
  OAI21_X1P4M_A9TR40 U402 ( .A0(n401), .A1(n422), .B0(fsm_state[1]), .Y(n421)
         );
  INV_X0P6M_A9TR40 U403 ( .A(n509), .Y(n719) );
  OAI21B_X3M_A9TR40 U404 ( .A0(n702), .A1(n436), .B0N(n295), .Y(n435) );
  NOR2_X2M_A9TR40 U405 ( .A(n646), .B(n561), .Y(n757) );
  NOR2_X2B_A9TR40 U406 ( .A(n687), .B(n606), .Y(n686) );
  OAI21_X1M_A9TR40 U407 ( .A0(n319), .A1(n639), .B0(n388), .Y(n642) );
  NAND2_X1P4M_A9TR40 U408 ( .A(n540), .B(n539), .Y(n546) );
  INV_X0P6B_A9TR40 U409 ( .A(n402), .Y(n771) );
  OAI31_X3M_A9TR40 U410 ( .A0(n655), .A1(n654), .A2(n653), .B0(fail_reason[2]), 
        .Y(n656) );
  NAND3BB_X1M_A9TR40 U411 ( .AN(n564), .BN(n563), .C(fsm_state[0]), .Y(n567)
         );
  NOR2_X1A_A9TR40 U412 ( .A(n565), .B(n400), .Y(n566) );
  OAI21_X3M_A9TR40 U413 ( .A0(n584), .A1(n599), .B0(cal_fail), .Y(n585) );
  INV_X1M_A9TR40 U414 ( .A(n563), .Y(n493) );
  OAI21_X3M_A9TR40 U415 ( .A0(cal_start), .A1(n649), .B0(n491), .Y(n492) );
  NOR3BB_X0P7M_A9TR40 U416 ( .AN(n627), .BN(n444), .C(n569), .Y(n575) );
  INV_X1M_A9TR40 U417 ( .A(n409), .Y(n762) );
  INV_X1B_A9TR40 U418 ( .A(n408), .Y(n765) );
  NOR2_X2B_A9TR40 U419 ( .A(n552), .B(n319), .Y(n723) );
  NOR2_X2B_A9TR40 U420 ( .A(n645), .B(n446), .Y(n445) );
  INV_X1M_A9TR40 U421 ( .A(n606), .Y(n743) );
  INV_X3M_A9TR40 U422 ( .A(n589), .Y(n402) );
  INV_X3P5B_A9TR40 U423 ( .A(n540), .Y(n436) );
  INV_X1M_A9TR40 U424 ( .A(n699), .Y(n584) );
  INV_X1B_A9TR40 U425 ( .A(n297), .Y(fine_code[1]) );
  BUFH_X1M_A9TR40 U426 ( .A(n474), .Y(n570) );
  INV_X2P5B_A9TR40 U427 ( .A(n428), .Y(n426) );
  NAND2_X2B_A9TR40 U428 ( .A(n701), .B(n454), .Y(n702) );
  NAND4_X1A_A9TR40 U429 ( .A(n723), .B(n307), .C(n308), .D(n774), .Y(n619) );
  NAND2XB_X1M_A9TR40 U430 ( .BN(n689), .A(n747), .Y(n408) );
  INV_X1B_A9TR40 U431 ( .A(n407), .Y(n769) );
  NAND2XB_X1M_A9TR40 U432 ( .BN(n559), .A(n747), .Y(n409) );
  NAND2_X2B_A9TR40 U433 ( .A(n537), .B(n430), .Y(n425) );
  INV_X1B_A9TR40 U434 ( .A(n743), .Y(n413) );
  NAND2_X1B_A9TR40 U435 ( .A(n542), .B(n524), .Y(n652) );
  NAND2_X1B_A9TR40 U436 ( .A(n554), .B(n519), .Y(n446) );
  NAND3_X1M_A9TR40 U437 ( .A(n713), .B(n704), .C(n705), .Y(n422) );
  NAND2_X2B_A9TR40 U438 ( .A(n744), .B(n753), .Y(n687) );
  OAI211_X1M_A9TR40 U439 ( .A0(n571), .A1(n705), .B0(n484), .C0(n699), .Y(n489) );
  INV_X1B_A9TR40 U440 ( .A(n715), .Y(n593) );
  INV_X1M_A9TR40 U441 ( .A(n646), .Y(n412) );
  NOR2_X1M_A9TR40 U442 ( .A(n592), .B(n778), .Y(n809) );
  NAND2_X1B_A9TR40 U443 ( .A(n563), .B(n711), .Y(n491) );
  NOR2_X1M_A9TR40 U444 ( .A(n617), .B(n778), .Y(\u_sequencer/N43 ) );
  NOR2_X2M_A9TR40 U445 ( .A(n701), .B(fsm_state[0]), .Y(n565) );
  NAND2_X3B_A9TR40 U446 ( .A(n556), .B(n284), .Y(n555) );
  AOI21_X3M_A9TR40 U447 ( .A0(n543), .A1(n564), .B0(n542), .Y(n548) );
  INV_X1B_A9TR40 U448 ( .A(n720), .Y(medium_code[4]) );
  NAND2_X3B_A9TR40 U449 ( .A(n504), .B(n519), .Y(n721) );
  INV_X1B_A9TR40 U450 ( .A(n319), .Y(n778) );
  NAND2_X3B_A9TR40 U451 ( .A(n478), .B(n498), .Y(n667) );
  NAND3_X1A_A9TR40 U452 ( .A(n775), .B(n618), .C(n306), .Y(n738) );
  INV_X4M_A9TR40 U453 ( .A(n668), .Y(n706) );
  NOR2_X4M_A9TR40 U454 ( .A(n746), .B(n595), .Y(n571) );
  NAND3_X2M_A9TR40 U455 ( .A(n521), .B(n704), .C(n520), .Y(n522) );
  NOR2_X4B_A9TR40 U456 ( .A(n668), .B(n490), .Y(n714) );
  AOI21_X1M_A9TR40 U457 ( .A0(fsm_state[2]), .A1(n543), .B0(n542), .Y(n439) );
  AND3_X2M_A9TR40 U458 ( .A(n580), .B(n704), .C(n715), .Y(n538) );
  INV_X1P7B_A9TR40 U459 ( .A(n432), .Y(n429) );
  NOR2_X2B_A9TR40 U460 ( .A(n705), .B(n483), .Y(n573) );
  NOR2_X4B_A9TR40 U461 ( .A(n464), .B(n542), .Y(n466) );
  NOR2_X2B_A9TR40 U462 ( .A(medium_code[3]), .B(n678), .Y(n755) );
  OAI21_X4M_A9TR40 U463 ( .A0(n625), .A1(n621), .B0(n587), .Y(n674) );
  AND3_X2M_A9TR40 U464 ( .A(n476), .B(n320), .C(n470), .Y(n472) );
  BUF_X2M_A9TR40 U465 ( .A(n316), .Y(n621) );
  INV_X1M_A9TR40 U466 ( .A(n307), .Y(n609) );
  INV_X3B_A9TR40 U467 ( .A(n442), .Y(n707) );
  NAND2_X2B_A9TR40 U468 ( .A(n543), .B(n661), .Y(n715) );
  BUFH_X2M_A9TR40 U469 ( .A(n527), .Y(medium_code[1]) );
  NAND2_X2B_A9TR40 U470 ( .A(n675), .B(n297), .Y(n622) );
  NOR2_X2A_A9TR40 U471 ( .A(n553), .B(n304), .Y(n618) );
  NOR2_X1M_A9TR40 U472 ( .A(n682), .B(n288), .Y(n503) );
  AND2_X8B_A9TR40 U473 ( .A(n661), .B(n463), .Y(n542) );
  NOR2_X3A_A9TR40 U474 ( .A(n450), .B(n506), .Y(n746) );
  NOR2XB_X2M_A9TR40 U475 ( .BN(n664), .A(n699), .Y(n440) );
  NAND2_X1P4M_A9TR40 U476 ( .A(n643), .B(n768), .Y(n501) );
  AOI21_X4M_A9TR40 U477 ( .A0(n550), .A1(n470), .B0(n568), .Y(n663) );
  XOR2_X0P7M_A9TR40 U478 ( .A(n708), .B(n474), .Y(n473) );
  NAND2_X4B_A9TR40 U479 ( .A(n458), .B(n457), .Y(n498) );
  INV_X2B_A9TR40 U480 ( .A(n536), .Y(n716) );
  NOR2_X2M_A9TR40 U481 ( .A(n699), .B(n517), .Y(n541) );
  INV_X2P5B_A9TR40 U482 ( .A(n284), .Y(n448) );
  NOR2_X3M_A9TR40 U483 ( .A(n284), .B(n285), .Y(n768) );
  INV_X1B_A9TR40 U484 ( .A(n320), .Y(n460) );
  BUF_X2M_A9TR40 U485 ( .A(n469), .Y(n711) );
  INV_X0P6B_A9TR40 U486 ( .A(n300), .Y(n499) );
  INV_X4M_A9TR40 U487 ( .A(n527), .Y(n679) );
  INV_X3B_A9TR40 U488 ( .A(n285), .Y(n526) );
  INV_X1M_A9TR40 U489 ( .A(n516), .Y(n720) );
  BUF_X3M_A9TR40 U490 ( .A(n298), .Y(n675) );
  AND2_X8B_A9TR40 U491 ( .A(n483), .B(n474), .Y(n661) );
  NOR2_X6M_A9TR40 U492 ( .A(fsm_state[3]), .B(n469), .Y(n696) );
  NAND2_X4B_A9TR40 U493 ( .A(n708), .B(n469), .Y(n705) );
  NOR2_X2M_A9TR40 U494 ( .A(n475), .B(n468), .Y(n665) );
  INV_X4M_A9TR40 U495 ( .A(n753), .Y(medium_code[0]) );
  BUF_X6M_A9TR40 U496 ( .A(n312), .Y(n469) );
  INV_X6M_A9TR40 U497 ( .A(n465), .Y(n483) );
  INV_X7P5M_A9TR40 U498 ( .A(n525), .Y(n753) );
  INV_X11M_A9TR40 U499 ( .A(n474), .Y(n461) );
  INV_X4B_A9TR40 U500 ( .A(n708), .Y(n400) );
  NAND2_X1B_A9TR40 U501 ( .A(n647), .B(n580), .Y(n581) );
  NAND3BB_X1M_A9TR40 U502 ( .AN(medium_code[1]), .BN(n753), .C(n747), .Y(n407)
         );
  NAND3_X1M_A9TR40 U503 ( .A(n713), .B(n706), .C(n481), .Y(n482) );
  INV_X2M_A9TR40 U504 ( .A(n286), .Y(n527) );
  MXT2_X1B_A9TR40 U505 ( .A(q_final), .B(\u_sequencer/u_q_sampler/n1 ), .S0(
        n613), .Y(n786) );
  AND2_X1M_A9TR40 U506 ( .A(n747), .B(n680), .Y(n398) );
  AND2_X1M_A9TR40 U507 ( .A(n714), .B(n713), .Y(n399) );
  OAI21_X1P4M_A9TR40 U508 ( .A0(n605), .A1(n621), .B0(n591), .Y(n376) );
  INV_X1P7B_A9TR40 U509 ( .A(n541), .Y(n441) );
  NAND2_X1P4B_A9TR40 U510 ( .A(n716), .B(n715), .Y(n431) );
  INV_X1M_A9TR40 U511 ( .A(n716), .Y(n654) );
  NAND2_X2B_A9TR40 U512 ( .A(n451), .B(n503), .Y(n504) );
  NAND3_X2M_A9TR40 U513 ( .A(n449), .B(n678), .C(n447), .Y(n451) );
  INV_X3B_A9TR40 U514 ( .A(n501), .Y(n410) );
  INV_X0P6B_A9TR40 U515 ( .A(n578), .Y(n518) );
  INV_X3B_A9TR40 U516 ( .A(n598), .Y(n517) );
  INV_X2B_A9TR40 U517 ( .A(n610), .Y(n512) );
  INV_X0P6B_A9TR40 U518 ( .A(n621), .Y(fine_code[3]) );
  INV_X2M_A9TR40 U519 ( .A(n296), .Y(fine_code[2]) );
  INV_X2M_A9TR40 U520 ( .A(n308), .Y(n639) );
  NAND2_X1B_A9TR40 U521 ( .A(n712), .B(n399), .Y(n423) );
  INV_X2B_A9TR40 U522 ( .A(n645), .Y(n533) );
  INV_X1P7B_A9TR40 U523 ( .A(n431), .Y(n430) );
  INV_X2M_A9TR40 U524 ( .A(n750), .Y(n758) );
  INV_X2B_A9TR40 U525 ( .A(n440), .Y(n695) );
  NAND3BB_X3M_A9TR40 U526 ( .AN(medium_code[0]), .BN(n679), .C(n747), .Y(n406)
         );
  NOR3BB_X4M_A9TR40 U527 ( .AN(n519), .BN(n403), .C(n536), .Y(n496) );
  OA21_X2M_A9TR40 U528 ( .A0(n722), .A1(n693), .B0(n388), .Y(n724) );
  NAND3_X2A_A9TR40 U529 ( .A(n512), .B(n511), .C(n776), .Y(n616) );
  AND2_X1P4M_A9TR40 U530 ( .A(n755), .B(n679), .Y(n680) );
  INV_X1M_A9TR40 U531 ( .A(n723), .Y(n725) );
  NOR2_X1M_A9TR40 U532 ( .A(n320), .B(n570), .Y(n572) );
  NAND2_X2B_A9TR40 U533 ( .A(n791), .B(n729), .Y(n598) );
  INV_X1B_A9TR40 U534 ( .A(n324), .Y(n544) );
  INV_X0P6B_A9TR40 U535 ( .A(n314), .Y(lock_valid) );
  INV_X2M_A9TR40 U536 ( .A(n322), .Y(n553) );
  INV_X0P6B_A9TR40 U537 ( .A(n261), .Y(sense_s_clk) );
  INV_X2M_A9TR40 U538 ( .A(\q_class[1] ), .Y(n729) );
  INV_X0P6B_A9TR40 U539 ( .A(sense_dff_reset), .Y(n777) );
  INV_X0P6B_A9TR40 U540 ( .A(n267), .Y(cal_done) );
  NAND2_X1P4B_A9TR40 U541 ( .A(n423), .B(n421), .Y(n384) );
  NAND2_X2B_A9TR40 U542 ( .A(n413), .B(n411), .Y(n417) );
  INV_X2M_A9TR40 U543 ( .A(n438), .Y(n434) );
  BUFH_X3M_A9TR40 U544 ( .A(n509), .Y(n411) );
  NOR2_X3M_A9TR40 U545 ( .A(n490), .B(n425), .Y(n424) );
  NOR2_X6A_A9TR40 U546 ( .A(n401), .B(n437), .Y(n540) );
  NAND3_X2A_A9TR40 U547 ( .A(n441), .B(n695), .C(n439), .Y(n438) );
  INV_X5M_A9TR40 U548 ( .A(n706), .Y(n401) );
  OAI21_X1M_A9TR40 U549 ( .A0(n698), .A1(n665), .B0(n403), .Y(n670) );
  OAI21_X3M_A9TR40 U550 ( .A0(n678), .A1(n558), .B0(n557), .Y(n684) );
  NAND2_X4B_A9TR40 U551 ( .A(n693), .B(n727), .Y(n388) );
  INV_X3P5B_A9TR40 U552 ( .A(n419), .Y(n418) );
  NOR2_X1A_A9TR40 U553 ( .A(n735), .B(n289), .Y(\u_sequencer/N56 ) );
  NAND2_X2B_A9TR40 U554 ( .A(n665), .B(n664), .Y(n471) );
  NOR2_X1A_A9TR40 U555 ( .A(n735), .B(n318), .Y(\u_sequencer/N57 ) );
  INV_X2M_A9TR40 U556 ( .A(n665), .Y(n521) );
  NAND2_X2B_A9TR40 U557 ( .A(n515), .B(n319), .Y(n727) );
  INV_X2M_A9TR40 U558 ( .A(n809), .Y(n735) );
  INV_X1B_A9TR40 U559 ( .A(n570), .Y(n539) );
  NAND2B_X4M_A9TR40 U560 ( .AN(n448), .B(n678), .Y(n450) );
  INV_X0P6M_A9TR40 U561 ( .A(n611), .Y(n612) );
  INV_X4M_A9TR40 U562 ( .A(n469), .Y(fsm_state[0]) );
  BUFH_X1P7M_A9TR40 U563 ( .A(n526), .Y(medium_code[2]) );
  NOR2_X2M_A9TR40 U564 ( .A(n324), .B(n311), .Y(n514) );
  INV_X0P6B_A9TR40 U565 ( .A(n305), .Y(q_sample_1_event) );
  INV_X0P6B_A9TR40 U566 ( .A(n260), .Y(q_sample_2_event) );
  NAND2_X4B_A9TR40 U567 ( .A(n299), .B(n314), .Y(n682) );
  NAND2_X2B_A9TR40 U568 ( .A(n433), .B(n544), .Y(n545) );
  NAND2_X2B_A9TR40 U569 ( .A(n411), .B(n412), .Y(n415) );
  NAND2_X2B_A9TR40 U570 ( .A(n540), .B(n434), .Y(n433) );
  MXIT2_X1P4M_A9TR40 U571 ( .A(n445), .B(n509), .S0(n683), .Y(n510) );
  INV_X7P5M_A9TR40 U572 ( .A(n658), .Y(n602) );
  AOI21_X1P4M_A9TR40 U573 ( .A0(n758), .A1(n772), .B0(n754), .Y(n356) );
  OAI21_X1P4M_A9TR40 U574 ( .A0(n745), .A1(n750), .B0(medium_therm[0]), .Y(
        n749) );
  NAND2_X4B_A9TR40 U575 ( .A(n714), .B(n713), .Y(n563) );
  NOR2XB_X6M_A9TR40 U576 ( .BN(n663), .A(n497), .Y(n614) );
  MX2_X1B_A9TR40 U577 ( .A(n642), .B(n641), .S0(n640), .Y(n784) );
  INV_X2M_A9TR40 U578 ( .A(n742), .Y(n745) );
  INV_X3B_A9TR40 U579 ( .A(n406), .Y(n759) );
  AOI21_X2M_A9TR40 U580 ( .A0(n535), .A1(n543), .B0(n573), .Y(n547) );
  NOR2_X2M_A9TR40 U581 ( .A(n489), .B(n488), .Y(n494) );
  AOI211_X2M_A9TR40 U582 ( .A0(n660), .A1(n577), .B0(n596), .C0(n576), .Y(n586) );
  NOR2B_X6M_A9TR40 U583 ( .AN(n582), .B(n581), .Y(n583) );
  OAI21_X2M_A9TR40 U584 ( .A0(n579), .A1(n578), .B0(n577), .Y(n582) );
  INV_X3B_A9TR40 U585 ( .A(n704), .Y(n490) );
  OAI21B_X1M_A9TR40 U586 ( .A0(n319), .A1(n738), .B0N(\u_sequencer/N62 ), .Y(
        \u_sequencer/N59 ) );
  NOR2XB_X8M_A9TR40 U587 ( .BN(n502), .A(n410), .Y(n747) );
  NOR2_X6M_A9TR40 U588 ( .A(n674), .B(n675), .Y(n588) );
  NAND2_X8B_A9TR40 U589 ( .A(n696), .B(n661), .Y(n519) );
  INV_X3P5B_A9TR40 U590 ( .A(n476), .Y(n457) );
  INV_X6M_A9TR40 U591 ( .A(n705), .Y(n543) );
  NAND3_X0P7M_A9TR40 U592 ( .A(n776), .B(n775), .C(n774), .Y(n779) );
  NOR2_X2A_A9TR40 U593 ( .A(n619), .B(n611), .Y(\u_sequencer/sample_2_fire )
         );
  INV_X1M_A9TR40 U594 ( .A(n450), .Y(n751) );
  INV_X2M_A9TR40 U595 ( .A(medium_code[0]), .Y(n449) );
  NOR2_X2M_A9TR40 U596 ( .A(n500), .B(n682), .Y(n502) );
  NAND2_X2B_A9TR40 U597 ( .A(n639), .B(n306), .Y(n610) );
  NAND3_X1A_A9TR40 U598 ( .A(n513), .B(n666), .C(n324), .Y(n617) );
  BUFH_X3P5M_A9TR40 U599 ( .A(n465), .Y(n420) );
  INV_X2P5B_A9TR40 U600 ( .A(n664), .Y(n403) );
  INV_X1B_A9TR40 U601 ( .A(fine_therm[6]), .Y(n635) );
  INV_X1B_A9TR40 U602 ( .A(fine_therm[7]), .Y(n634) );
  INV_X3M_A9TR40 U603 ( .A(n302), .Y(n456) );
  INV_X1B_A9TR40 U604 ( .A(fine_therm[0]), .Y(n624) );
  INV_X1B_A9TR40 U605 ( .A(fine_therm[1]), .Y(n629) );
  INV_X1B_A9TR40 U606 ( .A(fine_therm[2]), .Y(n632) );
  INV_X1B_A9TR40 U607 ( .A(fine_therm[5]), .Y(n637) );
  NOR2_X2M_A9TR40 U608 ( .A(n326), .B(n321), .Y(n459) );
  INV_X4B_A9TR40 U609 ( .A(n284), .Y(medium_code[3]) );
  INV_X1B_A9TR40 U610 ( .A(fine_therm[3]), .Y(n630) );
  TIEHI_X1M_A9TR40 U611 ( .Y(fine_therm[9]) );
  TIELO_X1M_A9TR40 U612 ( .Y(\fsm_state[4] ) );
  OAI211_X1M_A9TR40 U613 ( .A0(n663), .A1(n320), .B0(n662), .C0(n519), .Y(n671) );
  AOI21_X1M_A9TR40 U614 ( .A0(n297), .A1(n519), .B0(n673), .Y(n605) );
  NAND2_X4B_A9TR40 U615 ( .A(n542), .B(n700), .Y(n647) );
  NOR2_X4A_A9TR40 U616 ( .A(n708), .B(n469), .Y(n463) );
  NAND2_X2B_A9TR40 U617 ( .A(n679), .B(n753), .Y(n689) );
  NAND2_X2B_A9TR40 U618 ( .A(n683), .B(n676), .Y(n561) );
  AOI22_X1P4M_A9TR40 U619 ( .A0(n645), .A1(medium_code[2]), .B0(n445), .B1(
        n644), .Y(n414) );
  AOI22_X1P4M_A9TR40 U620 ( .A0(n645), .A1(medium_code[3]), .B0(n445), .B1(
        n508), .Y(n416) );
  NAND3_X0P7M_A9TR40 U621 ( .A(n419), .B(n707), .C(n708), .Y(n709) );
  NOR2_X8M_A9TR40 U622 ( .A(n571), .B(n418), .Y(n660) );
  OAI22_X0P5M_A9TR40 U623 ( .A0(n659), .A1(n419), .B0(n628), .B1(n301), .Y(
        n382) );
  OAI21_X4M_A9TR40 U624 ( .A0(n529), .A1(n528), .B0(n595), .Y(n419) );
  NAND2_X6B_A9TR40 U625 ( .A(n467), .B(fsm_state[3]), .Y(n704) );
  NAND2_X1B_A9TR40 U626 ( .A(n537), .B(n704), .Y(n427) );
  INV_X3P5B_A9TR40 U627 ( .A(n303), .Y(n465) );
  NAND2_X3B_A9TR40 U628 ( .A(n426), .B(n424), .Y(n718) );
  NOR2_X4B_A9TR40 U629 ( .A(n428), .B(n427), .Y(n717) );
  NAND2_X3B_A9TR40 U630 ( .A(n466), .B(n429), .Y(n428) );
  INV_X3P5B_A9TR40 U631 ( .A(n663), .Y(n432) );
  NAND2_X4B_A9TR40 U632 ( .A(n538), .B(n537), .Y(n437) );
  NAND2_X3B_A9TR40 U633 ( .A(n461), .B(n483), .Y(n442) );
  INV_X5B_A9TR40 U634 ( .A(n443), .Y(n536) );
  NAND3_X4M_A9TR40 U635 ( .A(n461), .B(n483), .C(n400), .Y(n443) );
  NOR2_X0P5A_A9TR40 U636 ( .A(n568), .B(n707), .Y(n444) );
  NOR2_X2A_A9TR40 U637 ( .A(n506), .B(n448), .Y(n447) );
  OAI31_X3M_A9TR40 U638 ( .A0(n655), .A1(n698), .A2(n653), .B0(cal_busy), .Y(
        n648) );
  OAI21_X3M_A9TR40 U639 ( .A0(n599), .A1(n698), .B0(fail_reason[1]), .Y(n600)
         );
  NAND2_X2B_A9TR40 U640 ( .A(n614), .B(n694), .Y(n615) );
  NOR2_X4B_A9TR40 U641 ( .A(n694), .B(n708), .Y(n568) );
  AOI21_X2M_A9TR40 U642 ( .A0(n749), .A1(n748), .B0(n589), .Y(n360) );
  AOI211_X2M_A9TR40 U643 ( .A0(n773), .A1(n772), .B0(n589), .C0(n770), .Y(n347) );
  AOI211_X2M_A9TR40 U644 ( .A0(n773), .A1(n764), .B0(n589), .C0(n763), .Y(n349) );
  AOI211_X2M_A9TR40 U645 ( .A0(n758), .A1(n757), .B0(n589), .C0(n756), .Y(n354) );
  AOI211_X2M_A9TR40 U646 ( .A0(n758), .A1(n764), .B0(n589), .C0(n752), .Y(n358) );
  AOI211_X2M_A9TR40 U647 ( .A0(n686), .A1(n772), .B0(n589), .C0(n681), .Y(n355) );
  AOI211_X2M_A9TR40 U648 ( .A0(n773), .A1(n742), .B0(n589), .C0(n688), .Y(n351) );
  AOI211_X2M_A9TR40 U649 ( .A0(n686), .A1(n742), .B0(n589), .C0(n685), .Y(n359) );
  AND3_X1M_A9TR40 U650 ( .A(n776), .B(n691), .C(n723), .Y(n452) );
  AND2_X1M_A9TR40 U651 ( .A(n402), .B(n682), .Y(n453) );
  OA21_X1M_A9TR40 U652 ( .A0(fsm_state[2]), .A1(n700), .B0(n699), .Y(n454) );
  AO21_X1M_A9TR40 U653 ( .A0(n594), .A1(n314), .B0(n593), .Y(n455) );
  INV_X1M_A9TR40 U654 ( .A(n700), .Y(n524) );
  NAND3_X1M_A9TR40 U655 ( .A(n643), .B(n768), .C(n720), .Y(n578) );
  INV_X2M_A9TR40 U656 ( .A(n643), .Y(n559) );
  AO21A1AI2_X1M_A9TR40 U657 ( .A0(n398), .A1(n753), .B0(medium_therm[4]), .C0(
        n402), .Y(n754) );
  AOI211_X2M_A9TR40 U658 ( .A0(n764), .A1(n767), .B0(n589), .C0(n760), .Y(n350) );
  INV_X11M_A9TR40 U659 ( .A(n456), .Y(n708) );
  INV_X16M_A9TR40 U660 ( .A(n708), .Y(fsm_state[3]) );
  BUF_X3M_A9TR40 U661 ( .A(n465), .Y(fsm_state[1]) );
  BUFH_X6M_A9TR40 U662 ( .A(n315), .Y(n474) );
  BUFH_X11M_A9TR40 U663 ( .A(n461), .Y(fsm_state[2]) );
  NAND2_X4B_A9TR40 U664 ( .A(n420), .B(n708), .Y(n475) );
  NAND2_X1P4M_A9TR40 U665 ( .A(fsm_state[0]), .B(n474), .Y(n480) );
  NAND2_X4B_A9TR40 U666 ( .A(n474), .B(n469), .Y(n468) );
  INV_X2M_A9TR40 U667 ( .A(n468), .Y(n458) );
  NAND2_X6B_A9TR40 U668 ( .A(fsm_state[3]), .B(n483), .Y(n476) );
  OA21_X4M_A9TR40 U669 ( .A0(n475), .A1(n480), .B0(n498), .Y(n537) );
  INV_X4M_A9TR40 U670 ( .A(n519), .Y(n462) );
  NAND2_X3B_A9TR40 U671 ( .A(n460), .B(n459), .Y(n664) );
  NAND2_X6B_A9TR40 U672 ( .A(n707), .B(n543), .Y(n659) );
  NAND3BB_X4M_A9TR40 U673 ( .AN(n462), .BN(n664), .C(n659), .Y(n464) );
  NOR2_X2A_A9TR40 U674 ( .A(fsm_state[3]), .B(n474), .Y(n550) );
  NAND2_X2B_A9TR40 U675 ( .A(n483), .B(n469), .Y(n470) );
  NAND2_X2B_A9TR40 U676 ( .A(n420), .B(n474), .Y(n694) );
  NAND2_X8B_A9TR40 U677 ( .A(fsm_state[1]), .B(fsm_state[2]), .Y(n564) );
  INV_X5M_A9TR40 U678 ( .A(n564), .Y(n467) );
  NAND2_X6B_A9TR40 U679 ( .A(n536), .B(n711), .Y(n699) );
  NAND4_X4M_A9TR40 U680 ( .A(n717), .B(n517), .C(n521), .D(n699), .Y(n594) );
  AO1B2_X4M_A9TR40 U681 ( .B0(n473), .B1(n472), .A0N(n471), .Y(n668) );
  INV_X1M_A9TR40 U682 ( .A(n475), .Y(n477) );
  OAI22BB_X4M_A9TR40 U683 ( .A0(n477), .A1(fsm_state[2]), .B0N(n476), .B1N(
        fsm_state[2]), .Y(n478) );
  NAND2_X2B_A9TR40 U684 ( .A(n667), .B(n664), .Y(n713) );
  NOR2_X2M_A9TR40 U685 ( .A(n316), .B(n298), .Y(n479) );
  NAND3_X3M_A9TR40 U686 ( .A(n479), .B(n296), .C(n297), .Y(n700) );
  OA21A1OI2_X1M_A9TR40 U687 ( .A0(n700), .A1(n708), .B0(n483), .C0(n480), .Y(
        n481) );
  INV_X5M_A9TR40 U688 ( .A(n526), .Y(n678) );
  NAND2_X2B_A9TR40 U689 ( .A(n286), .B(n313), .Y(n506) );
  NAND4_X3M_A9TR40 U690 ( .A(n290), .B(n291), .C(n294), .D(n325), .Y(n595) );
  AOI21_X0P5M_A9TR40 U691 ( .A0(n711), .A1(n661), .B0(n573), .Y(n484) );
  INV_X1M_A9TR40 U692 ( .A(n292), .Y(n485) );
  NOR2_X1A_A9TR40 U693 ( .A(n293), .B(n485), .Y(n651) );
  NAND2_X0P7B_A9TR40 U694 ( .A(n700), .B(n651), .Y(n486) );
  NAND3_X1A_A9TR40 U695 ( .A(n486), .B(n661), .C(fsm_state[3]), .Y(n487) );
  NAND2_X2B_A9TR40 U696 ( .A(n536), .B(n598), .Y(n710) );
  NAND2_X1B_A9TR40 U697 ( .A(n487), .B(n710), .Y(n488) );
  INV_X1M_A9TR40 U698 ( .A(n593), .Y(n649) );
  NAND3_X4M_A9TR40 U699 ( .A(n548), .B(n704), .C(n496), .Y(n497) );
  NAND2_X1P4M_A9TR40 U700 ( .A(n614), .B(n498), .Y(n734) );
  INV_X1M_A9TR40 U701 ( .A(n266), .Y(fail_reason[0]) );
  INV_X3P5B_A9TR40 U702 ( .A(n287), .Y(n525) );
  NAND2_X1B_A9TR40 U703 ( .A(n499), .B(n313), .Y(n500) );
  NOR2_X6A_A9TR40 U704 ( .A(n679), .B(n753), .Y(n643) );
  NOR2_X6A_A9TR40 U705 ( .A(n747), .B(n721), .Y(n645) );
  NAND2_X4B_A9TR40 U706 ( .A(n753), .B(n285), .Y(n507) );
  INV_X1M_A9TR40 U707 ( .A(n288), .Y(n505) );
  OAI31_X6M_A9TR40 U708 ( .A0(n506), .A1(n507), .A2(medium_code[3]), .B0(n505), 
        .Y(n554) );
  INV_X5M_A9TR40 U709 ( .A(n519), .Y(n589) );
  NOR3_X4M_A9TR40 U710 ( .A(n645), .B(n554), .C(n589), .Y(n509) );
  NOR2_X6A_A9TR40 U711 ( .A(n507), .B(medium_code[1]), .Y(n556) );
  XOR2_X4M_A9TR40 U712 ( .A(n556), .B(medium_code[3]), .Y(n606) );
  OAI21_X1M_A9TR40 U713 ( .A0(n559), .A1(n678), .B0(n284), .Y(n508) );
  NAND2_X2B_A9TR40 U714 ( .A(n559), .B(n689), .Y(n683) );
  NOR3BB_X2M_A9TR40 U715 ( .AN(n309), .BN(n307), .C(n308), .Y(n775) );
  NOR2_X1A_A9TR40 U716 ( .A(n609), .B(n309), .Y(n511) );
  INV_X2M_A9TR40 U717 ( .A(n618), .Y(n776) );
  NAND3_X3A_A9TR40 U718 ( .A(n738), .B(n616), .C(n778), .Y(n693) );
  INV_X1M_A9TR40 U719 ( .A(n295), .Y(n513) );
  INV_X1M_A9TR40 U720 ( .A(n311), .Y(n666) );
  NAND2_X1B_A9TR40 U721 ( .A(n514), .B(n295), .Y(n592) );
  NAND2_X1B_A9TR40 U722 ( .A(n617), .B(n592), .Y(n515) );
  INV_X2P5B_A9TR40 U723 ( .A(n659), .Y(n577) );
  INV_X2M_A9TR40 U724 ( .A(n313), .Y(n516) );
  AOI31_X1M_A9TR40 U725 ( .A0(n577), .A1(n518), .A2(n595), .B0(n541), .Y(n532)
         );
  NAND3_X4M_A9TR40 U726 ( .A(n663), .B(n537), .C(n519), .Y(n523) );
  NAND2_X1B_A9TR40 U727 ( .A(n536), .B(n664), .Y(n520) );
  NOR2_X6A_A9TR40 U728 ( .A(n523), .B(n522), .Y(n658) );
  INV_X1M_A9TR40 U729 ( .A(n652), .Y(n576) );
  NAND2_X1B_A9TR40 U730 ( .A(n576), .B(n651), .Y(n601) );
  NAND2_X2B_A9TR40 U731 ( .A(medium_code[3]), .B(n720), .Y(n529) );
  NAND3_X1M_A9TR40 U732 ( .A(n527), .B(n526), .C(n525), .Y(n528) );
  NOR2_X4A_A9TR40 U733 ( .A(n660), .B(n659), .Y(n653) );
  OAI21_X1M_A9TR40 U734 ( .A0(n716), .A1(n598), .B0(n647), .Y(n530) );
  OAI31_X4M_A9TR40 U735 ( .A0(n602), .A1(n653), .A2(n530), .B0(fail_reason[0]), 
        .Y(n531) );
  OAI211_X2M_A9TR40 U736 ( .A0(n532), .A1(n602), .B0(n601), .C0(n531), .Y(n343) );
  NAND2_X1B_A9TR40 U737 ( .A(n533), .B(n402), .Y(n534) );
  INV_X1M_A9TR40 U738 ( .A(n660), .Y(n535) );
  NAND2_X2B_A9TR40 U739 ( .A(n536), .B(fsm_state[0]), .Y(n580) );
  INV_X1M_A9TR40 U740 ( .A(n667), .Y(n549) );
  NAND3_X2M_A9TR40 U741 ( .A(n549), .B(n548), .C(n704), .Y(n569) );
  AOI211_X1P4M_A9TR40 U742 ( .A0(n568), .A1(n319), .B0(n550), .C0(n569), .Y(
        n551) );
  INV_X1M_A9TR40 U743 ( .A(n309), .Y(n552) );
  INV_X1M_A9TR40 U744 ( .A(n306), .Y(n774) );
  NAND2_X1B_A9TR40 U745 ( .A(n553), .B(n304), .Y(n611) );
  INV_X1M_A9TR40 U746 ( .A(n281), .Y(medium_therm[3]) );
  AOI21_X6M_A9TR40 U747 ( .A0(n555), .A1(medium_code[4]), .B0(n554), .Y(n744)
         );
  INV_X1M_A9TR40 U748 ( .A(n682), .Y(n676) );
  INV_X1M_A9TR40 U749 ( .A(n689), .Y(n558) );
  INV_X2M_A9TR40 U750 ( .A(n556), .Y(n557) );
  AOI21_X1M_A9TR40 U751 ( .A0(n762), .A1(n751), .B0(medium_therm[3]), .Y(n560)
         );
  AOI211_X2M_A9TR40 U752 ( .A0(n686), .A1(n764), .B0(n589), .C0(n560), .Y(n357) );
  INV_X1M_A9TR40 U753 ( .A(n269), .Y(medium_therm[7]) );
  INV_X1M_A9TR40 U754 ( .A(n684), .Y(n646) );
  AOI21_X1M_A9TR40 U755 ( .A0(n762), .A1(medium_code[2]), .B0(medium_therm[7]), 
        .Y(n562) );
  AOI211_X2M_A9TR40 U756 ( .A0(n686), .A1(n757), .B0(n589), .C0(n562), .Y(n353) );
  INV_X1M_A9TR40 U757 ( .A(n277), .Y(medium_therm[4]) );
  NAND2_X3B_A9TR40 U758 ( .A(n660), .B(n707), .Y(n701) );
  NAND2_X1B_A9TR40 U759 ( .A(fsm_state[2]), .B(n319), .Y(n627) );
  AOI22_X1M_A9TR40 U760 ( .A0(n573), .A1(n572), .B0(n577), .B1(n571), .Y(n574)
         );
  INV_X1M_A9TR40 U761 ( .A(n265), .Y(fail_reason[1]) );
  INV_X1M_A9TR40 U762 ( .A(n264), .Y(cal_fail) );
  INV_X1M_A9TR40 U763 ( .A(n710), .Y(n596) );
  INV_X1M_A9TR40 U764 ( .A(n595), .Y(n579) );
  NAND2_X4B_A9TR40 U765 ( .A(n658), .B(n583), .Y(n599) );
  NOR2_X4A_A9TR40 U766 ( .A(n622), .B(fine_code[2]), .Y(n625) );
  NOR2_X1P4M_A9TR40 U767 ( .A(n682), .B(n317), .Y(n587) );
  NOR2_X2A_A9TR40 U768 ( .A(n588), .B(n589), .Y(n673) );
  INV_X2M_A9TR40 U769 ( .A(n588), .Y(n590) );
  NOR2_X3B_A9TR40 U770 ( .A(n590), .B(n589), .Y(n731) );
  NAND3_X1A_A9TR40 U771 ( .A(n731), .B(fine_code[2]), .C(fine_code[1]), .Y(
        n591) );
  NOR2_X1A_A9TR40 U772 ( .A(n659), .B(n595), .Y(n597) );
  AOI22_X1M_A9TR40 U773 ( .A0(n597), .A1(n746), .B0(n596), .B1(fsm_state[0]), 
        .Y(n603) );
  NOR2_X3A_A9TR40 U774 ( .A(n699), .B(n598), .Y(n698) );
  NAND2_X1B_A9TR40 U775 ( .A(n731), .B(fine_code[1]), .Y(n604) );
  MXIT2_X1P4M_A9TR40 U776 ( .A(n605), .B(n604), .S0(n296), .Y(n377) );
  INV_X1M_A9TR40 U777 ( .A(n270), .Y(medium_therm[14]) );
  NAND2_X1B_A9TR40 U778 ( .A(n606), .B(medium_code[0]), .Y(n607) );
  NOR2B_X2M_A9TR40 U779 ( .AN(n744), .B(n607), .Y(n767) );
  AOI21_X0P5M_A9TR40 U780 ( .A0(n759), .A1(n768), .B0(medium_therm[14]), .Y(
        n608) );
  AOI211_X2M_A9TR40 U781 ( .A0(n757), .A1(n767), .B0(n771), .C0(n608), .Y(n346) );
  INV_X0P6B_A9TR40 U782 ( .A(ctrl_por_n), .Y(n810) );
  BUF_X0P7M_A9TR40 U783 ( .A(n810), .Y(n787) );
  BUF_X0P7M_A9TR40 U784 ( .A(n810), .Y(n788) );
  BUF_X0P7M_A9TR40 U785 ( .A(n810), .Y(n790) );
  BUF_X0P7M_A9TR40 U786 ( .A(n810), .Y(n789) );
  INV_X1M_A9TR40 U787 ( .A(n283), .Y(medium_therm[0]) );
  INV_X1M_A9TR40 U788 ( .A(n278), .Y(medium_therm[9]) );
  INV_X1M_A9TR40 U789 ( .A(n276), .Y(medium_therm[5]) );
  INV_X1M_A9TR40 U790 ( .A(n272), .Y(medium_therm[6]) );
  INV_X1M_A9TR40 U791 ( .A(n274), .Y(medium_therm[13]) );
  INV_X1M_A9TR40 U792 ( .A(n273), .Y(medium_therm[2]) );
  INV_X1M_A9TR40 U793 ( .A(n275), .Y(medium_therm[12]) );
  INV_X1M_A9TR40 U794 ( .A(n279), .Y(medium_therm[8]) );
  INV_X1M_A9TR40 U795 ( .A(n262), .Y(cal_busy) );
  INV_X1M_A9TR40 U796 ( .A(n609), .Y(n640) );
  NOR2_X1A_A9TR40 U797 ( .A(n610), .B(n640), .Y(n691) );
  INV_X1M_A9TR40 U798 ( .A(n282), .Y(medium_therm[1]) );
  MXIT2_X0P7M_A9TR40 U799 ( .A(n388), .B(n693), .S0(n308), .Y(n393) );
  INV_X1M_A9TR40 U800 ( .A(n675), .Y(fine_code[0]) );
  INV_X1M_A9TR40 U801 ( .A(n280), .Y(medium_therm[11]) );
  NAND3_X1M_A9TR40 U802 ( .A(n691), .B(n723), .C(n612), .Y(n613) );
  MXIT2_X0P7M_A9TR40 U803 ( .A(n791), .B(n293), .S0(n615), .Y(n336) );
  MXIT2_X0P7M_A9TR40 U804 ( .A(n729), .B(n292), .S0(n615), .Y(n333) );
  NOR2_X1A_A9TR40 U805 ( .A(n616), .B(n319), .Y(\u_sequencer/N62 ) );
  NOR2_X1A_A9TR40 U806 ( .A(n619), .B(n618), .Y(\u_sequencer/N61 ) );
  OAI21_X1M_A9TR40 U807 ( .A0(n674), .A1(n621), .B0(fine_therm[8]), .Y(n620)
         );
  NAND2_X1B_A9TR40 U808 ( .A(n620), .B(n402), .Y(n362) );
  NAND3BB_X1M_A9TR40 U809 ( .AN(n682), .BN(n317), .C(n621), .Y(n633) );
  OAI31_X1M_A9TR40 U810 ( .A0(n633), .A1(n296), .A2(n622), .B0(fine_therm[4]), 
        .Y(n623) );
  NAND2_X1B_A9TR40 U811 ( .A(n623), .B(n402), .Y(n366) );
  INV_X1M_A9TR40 U812 ( .A(n633), .Y(n626) );
  AO21A1AI2_X1M_A9TR40 U813 ( .A0(n626), .A1(n625), .B0(n624), .C0(n402), .Y(
        n370) );
  NOR3BB_X1M_A9TR40 U814 ( .AN(n696), .BN(n627), .C(fsm_state[1]), .Y(n628) );
  NOR3_X1A_A9TR40 U815 ( .A(n633), .B(n675), .C(fine_code[2]), .Y(n631) );
  AO21A1AI2_X1M_A9TR40 U816 ( .A0(n631), .A1(n297), .B0(n629), .C0(n402), .Y(
        n369) );
  AO21A1AI2_X1M_A9TR40 U817 ( .A0(n631), .A1(fine_code[1]), .B0(n630), .C0(
        n402), .Y(n367) );
  NOR3_X1A_A9TR40 U818 ( .A(n633), .B(n297), .C(fine_code[0]), .Y(n636) );
  AO21A1AI2_X1M_A9TR40 U819 ( .A0(n636), .A1(n296), .B0(n632), .C0(n402), .Y(
        n368) );
  NOR3_X1A_A9TR40 U820 ( .A(n633), .B(n296), .C(n675), .Y(n638) );
  AO21A1AI2_X1M_A9TR40 U821 ( .A0(n638), .A1(fine_code[1]), .B0(n634), .C0(
        n402), .Y(n363) );
  AO21A1AI2_X1M_A9TR40 U822 ( .A0(n636), .A1(fine_code[2]), .B0(n635), .C0(
        n402), .Y(n364) );
  AO21A1AI2_X1M_A9TR40 U823 ( .A0(n638), .A1(n297), .B0(n637), .C0(n402), .Y(
        n365) );
  NOR2_X1M_A9TR40 U824 ( .A(n693), .B(n308), .Y(n641) );
  XOR2_X0P7M_A9TR40 U825 ( .A(n643), .B(medium_code[2]), .Y(n644) );
  INV_X1M_A9TR40 U826 ( .A(cal_start), .Y(n650) );
  NAND2_X4B_A9TR40 U827 ( .A(n658), .B(n647), .Y(n655) );
  OAI21_X1M_A9TR40 U828 ( .A0(n652), .A1(n651), .B0(n710), .Y(n657) );
  AOI21_X1M_A9TR40 U829 ( .A0(n660), .A1(n311), .B0(n659), .Y(n672) );
  OAI211_X1M_A9TR40 U830 ( .A0(n700), .A1(n666), .B0(n661), .C0(fsm_state[0]), 
        .Y(n662) );
  OAI211_X1M_A9TR40 U831 ( .A0(n668), .A1(n667), .B0(n319), .C0(n666), .Y(n669) );
  NAND4BB_X1M_A9TR40 U832 ( .AN(n672), .BN(n671), .C(n670), .D(n669), .Y(n395)
         );
  INV_X1M_A9TR40 U833 ( .A(n673), .Y(n733) );
  AOI21_X1M_A9TR40 U834 ( .A0(n675), .A1(n674), .B0(n733), .Y(n379) );
  NAND2_X1B_A9TR40 U835 ( .A(n676), .B(medium_code[2]), .Y(n677) );
  NOR2_X2A_A9TR40 U836 ( .A(n683), .B(n677), .Y(n772) );
  AOI21_X1M_A9TR40 U837 ( .A0(n398), .A1(medium_code[0]), .B0(medium_therm[5]), 
        .Y(n681) );
  NOR3_X3A_A9TR40 U838 ( .A(n684), .B(n683), .C(n682), .Y(n742) );
  AOI31_X1M_A9TR40 U839 ( .A0(n747), .A1(n746), .A2(medium_code[0]), .B0(
        medium_therm[1]), .Y(n685) );
  NOR2_X2A_A9TR40 U840 ( .A(n687), .B(n743), .Y(n773) );
  NOR2_X1A_A9TR40 U841 ( .A(medium_code[2]), .B(n284), .Y(n761) );
  AOI21_X1M_A9TR40 U842 ( .A0(n769), .A1(n761), .B0(medium_therm[9]), .Y(n688)
         );
  AO21A1AI2_X1M_A9TR40 U843 ( .A0(n765), .A1(n761), .B0(medium_therm[8]), .C0(
        n402), .Y(n690) );
  AOI21_X1P4M_A9TR40 U844 ( .A0(n767), .A1(n742), .B0(n690), .Y(n352) );
  INV_X1M_A9TR40 U845 ( .A(n691), .Y(n692) );
  NOR3_X1A_A9TR40 U846 ( .A(n307), .B(n308), .C(n306), .Y(n722) );
  OAI22_X1M_A9TR40 U847 ( .A0(n693), .A1(n692), .B0(n724), .B1(n306), .Y(n391)
         );
  INV_X0P6M_A9TR40 U848 ( .A(n694), .Y(n697) );
  OAI31_X4M_A9TR40 U849 ( .A0(n698), .A1(n697), .A2(n696), .B0(n695), .Y(n703)
         );
  OAI211_X1M_A9TR40 U850 ( .A0(n711), .A1(fsm_state[1]), .B0(n710), .C0(n709), 
        .Y(n712) );
  MXIT2_X1M_A9TR40 U851 ( .A(n729), .B(n325), .S0(n718), .Y(n331) );
  OAI22_X1P4M_A9TR40 U852 ( .A0(n721), .A1(n720), .B0(n719), .B1(n744), .Y(
        n371) );
  INV_X1M_A9TR40 U853 ( .A(n722), .Y(n726) );
  OAI22_X1M_A9TR40 U854 ( .A0(n726), .A1(n725), .B0(n724), .B1(n309), .Y(n390)
         );
  INV_X1M_A9TR40 U855 ( .A(n727), .Y(n737) );
  OAI21_X1M_A9TR40 U856 ( .A0(n737), .A1(n304), .B0(n735), .Y(n337) );
  XNOR2_X0P7M_A9TR40 U857 ( .A(q_final), .B(\u_sequencer/u_q_sampler/n1 ), .Y(
        n728) );
  MXIT2_X0P7M_A9TR40 U858 ( .A(n729), .B(n728), .S0(
        \u_sequencer/sample_2_fire ), .Y(n257) );
  NAND2_X1B_A9TR40 U859 ( .A(q_final), .B(\u_sequencer/u_q_sampler/n1 ), .Y(
        n730) );
  MXIT2_X0P7M_A9TR40 U860 ( .A(n791), .B(n730), .S0(
        \u_sequencer/sample_2_fire ), .Y(n258) );
  INV_X2M_A9TR40 U861 ( .A(n731), .Y(n732) );
  MXIT2_X0P7M_A9TR40 U862 ( .A(n733), .B(n732), .S0(n297), .Y(n378) );
  MXIT2_X1M_A9TR40 U863 ( .A(n791), .B(n291), .S0(n734), .Y(n335) );
  INV_X1M_A9TR40 U864 ( .A(\u_sequencer/N43 ), .Y(n736) );
  OAI21_X1M_A9TR40 U865 ( .A0(n737), .A1(n322), .B0(n736), .Y(n389) );
  AOI21_X1M_A9TR40 U866 ( .A0(n326), .A1(n327), .B0(n809), .Y(n396) );
  XNOR2_X0P7M_A9TR40 U867 ( .A(n307), .B(n306), .Y(n739) );
  NAND4_X1A_A9TR40 U868 ( .A(n776), .B(n308), .C(n309), .D(n739), .Y(n741) );
  OAI21_X1M_A9TR40 U869 ( .A0(n741), .A1(n306), .B0(n778), .Y(n740) );
  AOI21_X1M_A9TR40 U870 ( .A0(n261), .A1(n741), .B0(n740), .Y(n329) );
  NAND3_X4M_A9TR40 U871 ( .A(n744), .B(n743), .C(medium_code[0]), .Y(n750) );
  NAND3_X1M_A9TR40 U872 ( .A(n747), .B(n746), .C(n753), .Y(n748) );
  AOI21_X1M_A9TR40 U873 ( .A0(n759), .A1(n751), .B0(medium_therm[2]), .Y(n752)
         );
  AOI21_X1M_A9TR40 U874 ( .A0(n759), .A1(n755), .B0(medium_therm[6]), .Y(n756)
         );
  AOI21_X1M_A9TR40 U875 ( .A0(n759), .A1(n761), .B0(medium_therm[10]), .Y(n760) );
  AOI21_X1M_A9TR40 U876 ( .A0(n762), .A1(n761), .B0(medium_therm[11]), .Y(n763) );
  AO21A1AI2_X1M_A9TR40 U877 ( .A0(n765), .A1(n768), .B0(medium_therm[12]), 
        .C0(n402), .Y(n766) );
  AOI21_X1P4M_A9TR40 U878 ( .A0(n767), .A1(n772), .B0(n766), .Y(n348) );
  AOI21_X1M_A9TR40 U879 ( .A0(n769), .A1(n768), .B0(medium_therm[13]), .Y(n770) );
  AOI31_X1M_A9TR40 U880 ( .A0(n779), .A1(n778), .A2(n777), .B0(
        \u_sequencer/N43 ), .Y(n328) );
endmodule

