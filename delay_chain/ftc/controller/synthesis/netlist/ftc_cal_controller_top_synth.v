/////////////////////////////////////////////////////////////
// Created by: Synopsys DC Ultra(TM) in wire load mode
// Version   : W-2024.09
// Date      : Thu Aug 20 12:05:24 2026
/////////////////////////////////////////////////////////////


module ftc_cal_controller_top ( cal_clk, ctrl_por_n, cal_start, q_final, 
        sense_dff_reset, sense_s_clk, medium_therm, fine_therm, cal_busy, 
        cal_done, cal_fail, lock_valid, medium_code, fine_code, fail_reason, 
        fsm_state );
  output [15:0] medium_therm;
  output [9:0] fine_therm;
  output [4:0] medium_code;
  output [3:0] fine_code;
  output [2:0] fail_reason;
  output [4:0] fsm_state;
  input cal_clk, ctrl_por_n, cal_start, q_final;
  output sense_dff_reset, sense_s_clk, cal_busy, cal_done, cal_fail,
         lock_valid;
  wire   n712, n713, n714, n715, n716, seq_medium_inc, seq_medium_dec,
         seq_fine_inc, seq_req, fsm_medium_inc, fsm_medium_dec, fsm_fine_inc,
         seq_busy, seq_done, seq_probe_done, \q_class[1] , \u_cfg_regs/n1 ,
         \u_sequencer/N54 , \u_sequencer/N51 , \u_sequencer/u_q_sampler/n1 ,
         n289, n292, n293, n294, n295, n296, n297, n298, n299, n300, n301,
         n302, n303, n304, n305, n306, n307, n308, n309, n310, n311, n312,
         n313, n314, n315, n316, n317, n318, n319, n320, n321, n322, n323,
         n324, n325, n326, n327, n328, n329, n330, n331, n332, n333, n334,
         n335, n336, n337, n338, n339, n340, n341, n342, n343, n344, n345,
         n346, n348, n349, n350, n351, n352, n353, n354, n355, n356, n357,
         n358, n359, n362, n363, n364, n365, n366, n367, n368, n369, n370,
         n371, n372, n373, n374, n375, n376, n377, n378, n379, n380, n381,
         n382, n383, n384, n385, n386, n387, n388, n389, n390, n391, n392,
         n393, n394, n395, n396, n397, n398, n399, n400, n401, n402, n403,
         n404, n405, n406, n407, n408, n409, n410, n411, n412, n413, n414,
         n415, n416, n417, n418, n419, n420, n421, n422, n423, n424, n425,
         n426, n427, n428, n429, n430, n431, n432, n433, n434, n435, n436,
         n437, n438, n439, n440, n441, n442, n443, n444, n445, n446, n447,
         n448, n449, n450, n451, n452, n453, n454, n455, n456, n457, n458,
         n459, n460, n461, n462, n463, n464, n465, n466, n467, n468, n469,
         n470, n471, n472, n473, n474, n475, n476, n477, n478, n479, n480,
         n481, n482, n483, n484, n485, n486, n487, n488, n489, n490, n491,
         n492, n493, n494, n495, n496, n497, n498, n499, n500, n501, n502,
         n503, n504, n505, n506, n507, n508, n509, n510, n511, n512, n513,
         n514, n515, n516, n517, n518, n519, n520, n521, n522, n523, n524,
         n525, n526, n527, n528, n529, n530, n531, n532, n533, n534, n535,
         n536, n537, n538, n539, n540, n541, n542, n543, n544, n545, n546,
         n547, n548, n549, n550, n551, n552, n553, n554, n555, n556, n557,
         n558, n559, n560, n561, n562, n563, n564, n565, n566, n567, n568,
         n569, n570, n571, n572, n574, n575, n576, n577, n578, n579, n580,
         n581, n582, n583, n584, n585, n586, n587, n588, n589, n590, n591,
         n592, n593, n594, n595, n596, n597, n598, n599, n600, n601, n602,
         n603, n604, n605, n606, n607, n608, n609, n610, n611, n612, n613,
         n614, n615, n616, n617, n618, n619, n620, n621, n622, n623, n624,
         n625, n626, n627, n628, n629, n630, n631, n632, n633, n634, n635,
         n636, n637, n638, n639, n640, n641, n642, n643, n644, n645, n646,
         n647, n648, n649, n650, n651, n652, n653, n654, n655, n656, n657,
         n658, n659, n660, n661, n662, n663, n664, n665, n666, n667, n668,
         n669, n670, n671, n672, n673, n674, n675, n676, n677, n678, n679,
         n680, n681, n682, n683, n684, n685, n686, n687, n688, n689, n690,
         n691, n692, n693, n694, n695, n699, n700, n701, n702, n705, n706,
         n707, n708, n709, n710, n711;
  wire   [1:0] seq_cmd;
  wire   [3:0] \u_sequencer/probe_count_q ;
  wire   [1:0] \u_sequencer/active_cmd_q ;
  wire   [1:0] \u_fsm/fine_probe_result_q ;
  wire   [1:0] \u_fsm/coarse_probe_b_result_q ;
  wire   [1:0] \u_fsm/coarse_probe_a_result_q ;

  DFFRPQ_X0P5M_A9TR40 \u_sequencer/u_q_sampler/q_sample_1_o_reg  ( .D(n700), 
        .CK(cal_clk), .R(n705), .Q(\u_sequencer/u_q_sampler/n1 ) );
  DFFRPQ_X2M_A9TR40 \u_fsm/seq_cmd_q_reg[1]  ( .D(n343), .CK(cal_clk), .R(n705), .Q(seq_cmd[1]) );
  DFFRPQ_X0P5M_A9TR40 \u_fsm/seq_medium_dec_q_reg  ( .D(n318), .CK(cal_clk), 
        .R(n707), .Q(fsm_medium_dec) );
  DFFRPQ_X2M_A9TR40 \u_sequencer/cfg_medium_dec_o_reg  ( .D(n701), .CK(cal_clk), .R(n707), .Q(seq_medium_dec) );
  DFFRPQ_X1M_A9TR40 \u_fsm/seq_req_q_reg  ( .D(n359), .CK(cal_clk), .R(n706), 
        .Q(seq_req) );
  DFFRPQ_X2M_A9TR40 \u_sequencer/active_cmd_q_reg[0]  ( .D(n337), .CK(cal_clk), 
        .R(n706), .Q(\u_sequencer/active_cmd_q [0]) );
  DFFRPQ_X2M_A9TR40 \u_sequencer/probe_count_q_reg[1]  ( .D(n340), .CK(cal_clk), .R(n708), .Q(\u_sequencer/probe_count_q [1]) );
  DFFRPQ_X2M_A9TR40 \u_sequencer/probe_count_q_reg[2]  ( .D(n339), .CK(cal_clk), .R(n706), .Q(\u_sequencer/probe_count_q [2]) );
  DFFRPQ_X2M_A9TR40 \u_sequencer/probe_count_q_reg[3]  ( .D(n338), .CK(cal_clk), .R(n708), .Q(\u_sequencer/probe_count_q [3]) );
  DFFRPQ_X2M_A9TR40 \u_sequencer/probe_done_o_reg  ( .D(\u_sequencer/N54 ), 
        .CK(cal_clk), .R(n708), .Q(seq_probe_done) );
  DFFRPQ_X2M_A9TR40 \u_sequencer/active_cmd_q_reg[1]  ( .D(n336), .CK(cal_clk), 
        .R(n705), .Q(\u_sequencer/active_cmd_q [1]) );
  DFFRPQ_X2M_A9TR40 \u_fsm/coarse_probe_a_result_q_reg[1]  ( .D(n327), .CK(
        cal_clk), .R(n707), .Q(\u_fsm/coarse_probe_a_result_q [1]) );
  DFFRPQ_X0P5M_A9TR40 \u_fsm/seq_fine_inc_q_reg  ( .D(n358), .CK(cal_clk), .R(
        n707), .Q(fsm_fine_inc) );
  DFFRPQ_X1M_A9TR40 \u_sequencer/cfg_fine_inc_o_reg  ( .D(n702), .CK(cal_clk), 
        .R(n707), .Q(seq_fine_inc) );
  DFFRPQ_X2M_A9TR40 \u_cfg_regs/cfg_locked_o_reg  ( .D(n344), .CK(cal_clk), 
        .R(n707), .Q(\u_cfg_regs/n1 ) );
  DFFRPQ_X2M_A9TR40 \u_fsm/coarse_probe_a_result_q_reg[0]  ( .D(n326), .CK(
        cal_clk), .R(n708), .Q(\u_fsm/coarse_probe_a_result_q [0]) );
  DFFRPQ_X0P5M_A9TR40 \u_fsm/seq_medium_inc_q_reg  ( .D(n334), .CK(cal_clk), 
        .R(n708), .Q(fsm_medium_inc) );
  DFFRPQ_X2M_A9TR40 \u_sequencer/cfg_medium_inc_o_reg  ( .D(n699), .CK(cal_clk), .R(n708), .Q(seq_medium_inc) );
  DFFSQ_X2M_A9TR40 \u_sequencer/u_q_sampler/q_class_o_reg[1]  ( .D(n289), .CK(
        cal_clk), .SN(ctrl_por_n), .Q(\q_class[1] ) );
  DFFRPQ_X4M_A9TR40 \u_cfg_regs/medium_code_o_reg[0]  ( .D(n353), .CK(cal_clk), 
        .R(n707), .Q(medium_code[0]) );
  DFFRPQ_X4M_A9TR40 \u_fsm/state_q_reg[2]  ( .D(n345), .CK(cal_clk), .R(n706), 
        .Q(n714) );
  DFFRPQ_X3M_A9TR40 \u_fsm/state_q_reg[0]  ( .D(n710), .CK(cal_clk), .R(n705), 
        .Q(n716) );
  DFFRPQ_X3M_A9TR40 \u_sequencer/busy_o_reg  ( .D(n335), .CK(cal_clk), .R(n706), .Q(seq_busy) );
  DFFRPQ_X4M_A9TR40 \u_cfg_regs/medium_code_o_reg[1]  ( .D(n352), .CK(cal_clk), 
        .R(n707), .Q(medium_code[1]) );
  DFFRPQ_X4M_A9TR40 \u_fsm/state_q_reg[1]  ( .D(n346), .CK(cal_clk), .R(n706), 
        .Q(n715) );
  DFFRPQ_X4M_A9TR40 \u_fsm/state_q_reg[3]  ( .D(n348), .CK(cal_clk), .R(n706), 
        .Q(n713) );
  DFFRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[9]  ( .D(n298), .CK(cal_clk), .R(n708), .Q(medium_therm[9]) );
  DFFRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[0]  ( .D(n307), .CK(cal_clk), .R(n705), .Q(medium_therm[0]) );
  DFFRPQ_X1M_A9TR40 \u_fsm/fail_reason_q_reg[1]  ( .D(n322), .CK(cal_clk), .R(
        n705), .Q(fail_reason[1]) );
  DFFRPQ_X1M_A9TR40 \u_fsm/fail_reason_q_reg[2]  ( .D(n321), .CK(cal_clk), .R(
        n705), .Q(fail_reason[2]) );
  DFFRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[6]  ( .D(n301), .CK(cal_clk), .R(n711), .Q(medium_therm[6]) );
  DFFRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[10]  ( .D(n297), .CK(
        cal_clk), .R(n711), .Q(medium_therm[10]) );
  DFFRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[5]  ( .D(n302), .CK(cal_clk), .R(n711), .Q(medium_therm[5]) );
  DFFRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[2]  ( .D(n305), .CK(cal_clk), .R(n705), .Q(medium_therm[2]) );
  DFFRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[14]  ( .D(n293), .CK(
        cal_clk), .R(n711), .Q(medium_therm[14]) );
  DFFRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[11]  ( .D(n296), .CK(
        cal_clk), .R(n708), .Q(medium_therm[11]) );
  DFFRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[13]  ( .D(n294), .CK(
        cal_clk), .R(n708), .Q(medium_therm[13]) );
  DFFRPQ_X1M_A9TR40 \u_sequencer/sense_s_clk_o_reg  ( .D(n333), .CK(cal_clk), 
        .R(n711), .Q(sense_s_clk) );
  DFFRPQ_X1M_A9TR40 \u_fsm/cal_done_q_reg  ( .D(n324), .CK(cal_clk), .R(n705), 
        .Q(cal_done) );
  DFFRPQ_X1M_A9TR40 \u_fsm/cal_busy_q_reg  ( .D(n319), .CK(cal_clk), .R(n705), 
        .Q(cal_busy) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[2]  ( .D(n315), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[2]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[6]  ( .D(n311), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[6]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[3]  ( .D(n314), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[3]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[7]  ( .D(n310), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[7]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[8]  ( .D(n309), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[8]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[9]  ( .D(n308), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[9]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[0]  ( .D(n317), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[0]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[4]  ( .D(n313), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[4]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[1]  ( .D(n316), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[1]) );
  DFFSQ_X1M_A9TR40 \u_cfg_regs/fine_therm_o_reg[5]  ( .D(n312), .CK(cal_clk), 
        .SN(ctrl_por_n), .Q(fine_therm[5]) );
  DFFRPQ_X1M_A9TR40 \u_fsm/fail_reason_q_reg[0]  ( .D(n323), .CK(cal_clk), .R(
        n705), .Q(fail_reason[0]) );
  DFFRPQ_X2M_A9TR40 \u_cfg_regs/fine_code_o_reg[0]  ( .D(n357), .CK(cal_clk), 
        .R(n706), .Q(fine_code[0]) );
  DFFRPQ_X2M_A9TR40 \u_cfg_regs/fine_code_o_reg[3]  ( .D(n354), .CK(cal_clk), 
        .R(n706), .Q(fine_code[3]) );
  DFFRPQ_X2M_A9TR40 \u_cfg_regs/fine_code_o_reg[2]  ( .D(n355), .CK(cal_clk), 
        .R(n707), .Q(fine_code[2]) );
  DFFRPQ_X1M_A9TR40 \u_fsm/coarse_probe_b_result_q_reg[0]  ( .D(n328), .CK(
        cal_clk), .R(n708), .Q(\u_fsm/coarse_probe_b_result_q [0]) );
  DFFRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[8]  ( .D(n299), .CK(cal_clk), .R(n711), .Q(medium_therm[8]) );
  DFFRPQ_X3M_A9TR40 \u_sequencer/done_o_reg  ( .D(\u_sequencer/N51 ), .CK(
        cal_clk), .R(n708), .Q(seq_done) );
  DFFRPQ_X3M_A9TR40 \u_sequencer/probe_count_q_reg[0]  ( .D(n341), .CK(cal_clk), .R(n706), .Q(\u_sequencer/probe_count_q [0]) );
  DFFRPQ_X1M_A9TR40 \u_fsm/fine_probe_result_q_reg[1]  ( .D(n331), .CK(cal_clk), .R(n705), .Q(\u_fsm/fine_probe_result_q [1]) );
  DFFSQ_X2M_A9TR40 \u_sequencer/u_q_sampler/q_class_o_reg[0]  ( .D(n367), .CK(
        cal_clk), .SN(ctrl_por_n), .Q(n709) );
  DFFSRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[15]  ( .D(n292), .CK(
        cal_clk), .R(n708), .SN(n695), .Q(medium_therm[15]) );
  DFFRPQ_X4M_A9TR40 \u_cfg_regs/medium_code_o_reg[2]  ( .D(n351), .CK(cal_clk), 
        .R(n707), .Q(medium_code[2]) );
  DFFRPQ_X0P5M_A9TR40 \u_fsm/fine_probe_result_q_reg[0]  ( .D(n330), .CK(
        cal_clk), .R(n706), .Q(\u_fsm/fine_probe_result_q [0]) );
  DFFSQ_X0P5M_A9TR40 \u_sequencer/sense_dff_reset_o_reg  ( .D(n332), .CK(
        cal_clk), .SN(ctrl_por_n), .Q(sense_dff_reset) );
  DFFRPQ_X0P5M_A9TR40 \u_cfg_regs/medium_therm_o_reg[3]  ( .D(n304), .CK(
        cal_clk), .R(n711), .Q(medium_therm[3]) );
  DFFRPQ_X2M_A9TR40 \u_fsm/coarse_probe_b_result_q_reg[1]  ( .D(n329), .CK(
        cal_clk), .R(n707), .Q(\u_fsm/coarse_probe_b_result_q [1]) );
  DFFRPQ_X3M_A9TR40 \u_cfg_regs/medium_code_o_reg[3]  ( .D(n350), .CK(cal_clk), 
        .R(n707), .Q(n712) );
  DFFRPQ_X2M_A9TR40 \u_fsm/lock_valid_q_reg  ( .D(n325), .CK(cal_clk), .R(n707), .Q(lock_valid) );
  DFFRPQ_X2M_A9TR40 \u_cfg_regs/medium_code_o_reg[4]  ( .D(n349), .CK(cal_clk), 
        .R(n707), .Q(medium_code[4]) );
  DFFRPQ_X3M_A9TR40 \u_cfg_regs/fine_code_o_reg[1]  ( .D(n356), .CK(cal_clk), 
        .R(n706), .Q(fine_code[1]) );
  DFFRPQ_X2M_A9TR40 \u_fsm/seq_cmd_q_reg[0]  ( .D(n342), .CK(cal_clk), .R(n706), .Q(seq_cmd[0]) );
  DFFRPQ_X1M_A9TR40 \u_fsm/cal_fail_q_reg  ( .D(n320), .CK(cal_clk), .R(n705), 
        .Q(cal_fail) );
  DFFRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[7]  ( .D(n300), .CK(cal_clk), .R(n711), .Q(medium_therm[7]) );
  DFFRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[12]  ( .D(n295), .CK(
        cal_clk), .R(n711), .Q(medium_therm[12]) );
  DFFRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[1]  ( .D(n306), .CK(cal_clk), .R(n705), .Q(medium_therm[1]) );
  DFFSRPQ_X1M_A9TR40 \u_cfg_regs/medium_therm_o_reg[4]  ( .D(n303), .CK(
        cal_clk), .R(n711), .SN(n695), .Q(medium_therm[4]) );
  OAI21_X1P4M_A9TR40 U365 ( .A0(n494), .A1(n469), .B0(n468), .Y(n351) );
  MXIT2_X0P7M_A9TR40 U366 ( .A(n364), .B(n709), .S0(n512), .Y(n328) );
  MXIT2_X0P7M_A9TR40 U367 ( .A(n489), .B(n590), .S0(n488), .Y(n331) );
  NAND2_X1B_A9TR40 U368 ( .A(n404), .B(n403), .Y(n345) );
  MXIT2_X1M_A9TR40 U369 ( .A(n389), .B(n616), .S0(n650), .Y(n355) );
  NAND3_X1A_A9TR40 U370 ( .A(n453), .B(n452), .C(n451), .Y(n359) );
  OA21A1OI2_X1P4M_A9TR40 U371 ( .A0(n487), .A1(n486), .B0(n485), .C0(n484), 
        .Y(n346) );
  OA1B2_X2M_A9TR40 U372 ( .B0(cal_start), .B1(n545), .A0N(n412), .Y(n710) );
  AND2_X1M_A9TR40 U373 ( .A(n497), .B(n496), .Y(n680) );
  INV_X1M_A9TR40 U374 ( .A(n465), .Y(n385) );
  BUF_X1M_A9TR40 U375 ( .A(n679), .Y(n362) );
  INV_X1B_A9TR40 U376 ( .A(n494), .Y(n455) );
  NOR3_X2M_A9TR40 U377 ( .A(n530), .B(medium_code[0]), .C(n529), .Y(n577) );
  NAND2_X1B_A9TR40 U378 ( .A(n537), .B(n475), .Y(n565) );
  NAND3_X1P4M_A9TR40 U379 ( .A(n625), .B(fsm_state[0]), .C(n624), .Y(n626) );
  OAI31_X3M_A9TR40 U380 ( .A0(n561), .A1(n537), .A2(n470), .B0(fail_reason[0]), 
        .Y(n426) );
  NAND2_X2B_A9TR40 U381 ( .A(n388), .B(n666), .Y(n611) );
  NAND4_X3A_A9TR40 U382 ( .A(n481), .B(n549), .C(n365), .D(n592), .Y(n482) );
  OA21A1OI2_X1P4M_A9TR40 U383 ( .A0(n638), .A1(n637), .B0(fail_reason[2]), 
        .C0(n636), .Y(n639) );
  NAND2XB_X3M_A9TR40 U384 ( .BN(n544), .A(n430), .Y(n637) );
  INV_X2B_A9TR40 U385 ( .A(n470), .Y(n600) );
  NOR2XB_X1M_A9TR40 U386 ( .BN(seq_busy), .A(\u_sequencer/probe_count_q [0]), 
        .Y(n581) );
  NOR2XB_X1M_A9TR40 U387 ( .BN(\u_sequencer/probe_count_q [1]), .A(
        \u_sequencer/probe_count_q [2]), .Y(n685) );
  NAND2_X3B_A9TR40 U388 ( .A(n448), .B(fsm_state[0]), .Y(n550) );
  OAI21_X4M_A9TR40 U389 ( .A0(n390), .A1(n525), .B0(n521), .Y(n668) );
  INV_X3B_A9TR40 U390 ( .A(n464), .Y(n522) );
  INV_X1P7B_A9TR40 U391 ( .A(n563), .Y(n553) );
  NOR2B_X4M_A9TR40 U392 ( .AN(\u_sequencer/probe_count_q [2]), .B(
        \u_sequencer/probe_count_q [1]), .Y(n682) );
  OAI21_X3M_A9TR40 U393 ( .A0(n402), .A1(n401), .B0(n400), .Y(n486) );
  INV_X3M_A9TR40 U394 ( .A(medium_code[2]), .Y(n392) );
  NOR2B_X4M_A9TR40 U395 ( .AN(fsm_state[0]), .B(fsm_state[1]), .Y(n606) );
  NAND2B_X2M_A9TR40 U396 ( .AN(n393), .B(n464), .Y(n454) );
  NOR2_X2B_A9TR40 U397 ( .A(n555), .B(n627), .Y(n442) );
  NOR2_X3A_A9TR40 U398 ( .A(medium_code[1]), .B(medium_code[0]), .Y(n393) );
  INV_X2M_A9TR40 U399 ( .A(n407), .Y(n555) );
  INV_X2M_A9TR40 U400 ( .A(fine_code[2]), .Y(n659) );
  NAND2_X1B_A9TR40 U401 ( .A(n715), .B(n713), .Y(n439) );
  NOR2_X4M_A9TR40 U402 ( .A(medium_code[2]), .B(n712), .Y(n491) );
  INV_X1M_A9TR40 U403 ( .A(n405), .Y(n556) );
  NAND2_X1P4B_A9TR40 U404 ( .A(n560), .B(n601), .Y(n401) );
  BUF_X2M_A9TR40 U405 ( .A(n712), .Y(medium_code[3]) );
  INV_X2B_A9TR40 U406 ( .A(seq_busy), .Y(n690) );
  NAND2XB_X4M_A9TR40 U407 ( .BN(n627), .A(n552), .Y(n427) );
  INV_X2M_A9TR40 U408 ( .A(n397), .Y(n398) );
  NAND2_X2B_A9TR40 U409 ( .A(n560), .B(fsm_state[1]), .Y(n592) );
  INV_X4M_A9TR40 U410 ( .A(n679), .Y(n666) );
  INV_X2B_A9TR40 U411 ( .A(\u_sequencer/probe_count_q [0]), .Y(n686) );
  AND2_X2M_A9TR40 U412 ( .A(seq_done), .B(seq_probe_done), .Y(n458) );
  INV_X3B_A9TR40 U413 ( .A(n472), .Y(n432) );
  INV_X5M_A9TR40 U414 ( .A(n713), .Y(n627) );
  BUFH_X9M_A9TR40 U415 ( .A(n716), .Y(fsm_state[0]) );
  INV_X1M_A9TR40 U416 ( .A(seq_medium_dec), .Y(n375) );
  NAND2_X1B_A9TR40 U417 ( .A(n497), .B(n494), .Y(n670) );
  AOI21_X2M_A9TR40 U418 ( .A0(fine_code[3]), .A1(n644), .B0(n643), .Y(n662) );
  AOI211_X1M_A9TR40 U419 ( .A0(n502), .A1(n576), .B0(n679), .C0(n492), .Y(n305) );
  INV_X1M_A9TR40 U420 ( .A(\u_fsm/coarse_probe_b_result_q [0]), .Y(n364) );
  NAND2_X3B_A9TR40 U421 ( .A(n379), .B(n521), .Y(n469) );
  INV_X1M_A9TR40 U422 ( .A(n476), .Y(n436) );
  NAND2_X1P4B_A9TR40 U423 ( .A(n449), .B(n448), .Y(n479) );
  INV_X1B_A9TR40 U424 ( .A(n592), .Y(n593) );
  NOR2_X3A_A9TR40 U425 ( .A(n521), .B(n679), .Y(n382) );
  INV_X1B_A9TR40 U426 ( .A(n585), .Y(n588) );
  INV_X0P6M_A9TR40 U427 ( .A(n522), .Y(n383) );
  INV_X1M_A9TR40 U428 ( .A(n532), .Y(n676) );
  INV_X0P6M_A9TR40 U429 ( .A(n394), .Y(n395) );
  INV_X1B_A9TR40 U430 ( .A(n601), .Y(n604) );
  INV_X0P6M_A9TR40 U431 ( .A(n632), .Y(n635) );
  NOR2_X1A_A9TR40 U432 ( .A(n659), .B(fine_code[1]), .Y(n655) );
  INV_X4M_A9TR40 U433 ( .A(medium_code[0]), .Y(n671) );
  INV_X2P5B_A9TR40 U434 ( .A(n469), .Y(n380) );
  INV_X5B_A9TR40 U435 ( .A(n486), .Y(n549) );
  INV_X2P5B_A9TR40 U436 ( .A(n523), .Y(n379) );
  NAND2_X2B_A9TR40 U437 ( .A(n520), .B(n530), .Y(n511) );
  NAND3_X1A_A9TR40 U438 ( .A(n604), .B(n603), .C(n602), .Y(n640) );
  INV_X2B_A9TR40 U439 ( .A(n479), .Y(n543) );
  NAND3_X1A_A9TR40 U440 ( .A(n613), .B(fine_code[1]), .C(fine_code[2]), .Y(
        n614) );
  INV_X2M_A9TR40 U441 ( .A(n528), .Y(n681) );
  NAND2_X3B_A9TR40 U442 ( .A(n519), .B(n599), .Y(n563) );
  NOR2_X2M_A9TR40 U443 ( .A(n388), .B(n679), .Y(n613) );
  NOR2_X3M_A9TR40 U444 ( .A(n373), .B(n679), .Y(n520) );
  NAND3_X1A_A9TR40 U445 ( .A(q_final), .B(\u_sequencer/u_q_sampler/n1 ), .C(
        n585), .Y(n370) );
  AOI21_X1M_A9TR40 U446 ( .A0(n577), .A1(n491), .B0(medium_therm[2]), .Y(n492)
         );
  NAND2_X2B_A9TR40 U447 ( .A(n424), .B(n472), .Y(n519) );
  NAND3_X1A_A9TR40 U448 ( .A(n685), .B(n505), .C(n504), .Y(n506) );
  OR2_X2B_A9TR40 U449 ( .A(n607), .B(n560), .Y(n459) );
  INV_X1P7B_A9TR40 U450 ( .A(n682), .Y(n693) );
  NAND2_X1B_A9TR40 U451 ( .A(n415), .B(seq_cmd[0]), .Y(n416) );
  NAND2_X2B_A9TR40 U452 ( .A(n533), .B(n671), .Y(n394) );
  NAND2_X3B_A9TR40 U453 ( .A(n393), .B(n491), .Y(n431) );
  INV_X5M_A9TR40 U454 ( .A(medium_code[1]), .Y(n529) );
  INV_X0P6M_A9TR40 U455 ( .A(fine_code[3]), .Y(n615) );
  INV_X0P6M_A9TR40 U456 ( .A(lock_valid), .Y(n605) );
  INV_X0P6M_A9TR40 U457 ( .A(cal_done), .Y(n641) );
  OAI21_X2M_A9TR40 U458 ( .A0(n529), .A1(n511), .B0(n381), .Y(n352) );
  OAI21_X2M_A9TR40 U459 ( .A0(n490), .A1(n469), .B0(n386), .Y(n350) );
  AOI22_X2M_A9TR40 U460 ( .A0(n466), .A1(medium_code[3]), .B0(n385), .B1(n384), 
        .Y(n386) );
  AO22_X1P4M_A9TR40 U461 ( .A0(cal_busy), .A1(n480), .B0(cal_start), .B1(n642), 
        .Y(n319) );
  AOI21_X1M_A9TR40 U462 ( .A0(n445), .A1(n515), .B0(n444), .Y(n453) );
  NAND3_X1A_A9TR40 U463 ( .A(n478), .B(n477), .C(n476), .Y(n322) );
  MXIT2_X1M_A9TR40 U464 ( .A(n463), .B(n709), .S0(n488), .Y(n330) );
  AO1B2_X3M_A9TR40 U465 ( .B0(n383), .B1(n382), .A0N(n511), .Y(n466) );
  AOI211_X2M_A9TR40 U466 ( .A0(n572), .A1(n535), .B0(n362), .C0(n413), .Y(n306) );
  NAND4_X1A_A9TR40 U467 ( .A(n410), .B(n409), .C(n633), .D(n408), .Y(n411) );
  OAI31_X1M_A9TR40 U468 ( .A0(n670), .A1(n669), .A2(n668), .B0(medium_therm[0]), .Y(n675) );
  AOI211_X2M_A9TR40 U469 ( .A0(n572), .A1(n576), .B0(n362), .C0(n457), .Y(n304) );
  OAI31_X1M_A9TR40 U470 ( .A0(n694), .A1(n693), .A2(n692), .B0(n691), .Y(n332)
         );
  INV_X2M_A9TR40 U471 ( .A(n550), .Y(n602) );
  NOR3_X1M_A9TR40 U472 ( .A(n600), .B(n473), .C(n472), .Y(n474) );
  OR2_X1M_A9TR40 U473 ( .A(n634), .B(n632), .Y(n476) );
  NOR2_X2M_A9TR40 U474 ( .A(n669), .B(n668), .Y(n502) );
  NAND2_X2B_A9TR40 U475 ( .A(n513), .B(seq_busy), .Y(n419) );
  NAND2_X3B_A9TR40 U476 ( .A(n378), .B(n666), .Y(n523) );
  NAND2_X2B_A9TR40 U477 ( .A(n382), .B(n378), .Y(n465) );
  INV_X2M_A9TR40 U478 ( .A(n490), .Y(n527) );
  INV_X1B_A9TR40 U479 ( .A(n564), .Y(n562) );
  MXT2_X1M_A9TR40 U480 ( .A(q_final), .B(\u_sequencer/u_q_sampler/n1 ), .S0(
        n506), .Y(n700) );
  NOR2_X2M_A9TR40 U481 ( .A(n369), .B(n368), .Y(n585) );
  NOR2_X4M_A9TR40 U482 ( .A(n443), .B(n416), .Y(n617) );
  NOR2_X2M_A9TR40 U483 ( .A(n601), .B(n485), .Y(n508) );
  INV_X1B_A9TR40 U484 ( .A(n473), .Y(n672) );
  NOR3_X2M_A9TR40 U485 ( .A(n530), .B(n529), .C(n532), .Y(n574) );
  NAND2_X2B_A9TR40 U486 ( .A(n364), .B(n363), .Y(n472) );
  NOR3_X0P5A_A9TR40 U487 ( .A(n683), .B(\u_sequencer/probe_count_q [1]), .C(
        \u_sequencer/probe_count_q [2]), .Y(n584) );
  NAND2_X2B_A9TR40 U488 ( .A(n533), .B(n406), .Y(n473) );
  NOR3_X3M_A9TR40 U489 ( .A(\u_fsm/coarse_probe_a_result_q [0]), .B(
        \u_fsm/coarse_probe_a_result_q [1]), .C(
        \u_fsm/coarse_probe_b_result_q [1]), .Y(n363) );
  INV_X1B_A9TR40 U490 ( .A(fine_therm[0]), .Y(n645) );
  INV_X1B_A9TR40 U491 ( .A(\u_sequencer/probe_count_q [2]), .Y(n420) );
  INV_X1B_A9TR40 U492 ( .A(fine_therm[4]), .Y(n652) );
  INV_X1B_A9TR40 U493 ( .A(fsm_medium_inc), .Y(n517) );
  INV_X1B_A9TR40 U494 ( .A(fine_therm[1]), .Y(n647) );
  INV_X1B_A9TR40 U495 ( .A(fine_therm[5]), .Y(n654) );
  TIELO_X1M_A9TR40 U496 ( .Y(fsm_state[4]) );
  NAND4B_X2M_A9TR40 U497 ( .AN(n459), .B(n516), .C(n458), .D(n515), .Y(n462)
         );
  NAND4_X2A_A9TR40 U498 ( .A(n631), .B(n541), .C(n630), .D(n479), .Y(n480) );
  OAI211_X2M_A9TR40 U499 ( .A0(n471), .A1(n600), .B0(n550), .C0(n630), .Y(n538) );
  NOR2_X3A_A9TR40 U500 ( .A(medium_code[2]), .B(medium_code[0]), .Y(n423) );
  NOR3_X2A_A9TR40 U501 ( .A(n686), .B(\u_sequencer/probe_count_q [1]), .C(
        \u_sequencer/probe_count_q [2]), .Y(n417) );
  NAND2_X2B_A9TR40 U502 ( .A(n515), .B(n715), .Y(n397) );
  BUF_X5M_A9TR40 U503 ( .A(n715), .Y(fsm_state[1]) );
  NOR2_X4A_A9TR40 U504 ( .A(n715), .B(n714), .Y(n405) );
  NOR3_X1P4M_A9TR40 U505 ( .A(lock_valid), .B(n375), .C(\u_cfg_regs/n1 ), .Y(
        n371) );
  NOR2_X4A_A9TR40 U506 ( .A(medium_code[4]), .B(medium_code[1]), .Y(n376) );
  OAI31_X2M_A9TR40 U507 ( .A0(n596), .A1(fsm_state[3]), .A2(n595), .B0(
        fsm_medium_dec), .Y(n597) );
  OR2_X1M_A9TR40 U508 ( .A(n439), .B(n515), .Y(n365) );
  AND2_X1M_A9TR40 U509 ( .A(medium_code[2]), .B(medium_code[3]), .Y(n366) );
  OA21_X1M_A9TR40 U510 ( .A0(n585), .A1(n709), .B0(n370), .Y(n367) );
  INV_X1M_A9TR40 U511 ( .A(n475), .Y(n603) );
  NOR4BB_X2M_A9TR40 U512 ( .AN(n565), .BN(n564), .C(n568), .D(n609), .Y(n567)
         );
  TIEHI_X1M_A9TR40 U513 ( .Y(n695) );
  NOR2_X1M_A9TR40 U514 ( .A(\u_sequencer/probe_count_q [3]), .B(
        \u_sequencer/active_cmd_q [0]), .Y(n504) );
  NAND2_X1B_A9TR40 U515 ( .A(n682), .B(n504), .Y(n369) );
  NAND2_X1B_A9TR40 U516 ( .A(n581), .B(\u_sequencer/active_cmd_q [1]), .Y(n368) );
  INV_X0P6B_A9TR40 U517 ( .A(ctrl_por_n), .Y(n711) );
  BUF_X0P7M_A9TR40 U518 ( .A(n711), .Y(n706) );
  INV_X3B_A9TR40 U519 ( .A(n712), .Y(n500) );
  NAND3_X1M_A9TR40 U520 ( .A(n376), .B(n423), .C(n500), .Y(n372) );
  NAND2_X1B_A9TR40 U521 ( .A(n372), .B(n371), .Y(n377) );
  INV_X2M_A9TR40 U522 ( .A(n377), .Y(n373) );
  NAND2_X6B_A9TR40 U523 ( .A(n627), .B(fsm_state[0]), .Y(n446) );
  NOR2B_X8M_A9TR40 U524 ( .AN(n405), .B(n446), .Y(n679) );
  NOR2_X4B_A9TR40 U525 ( .A(lock_valid), .B(\u_cfg_regs/n1 ), .Y(n646) );
  NOR2B_X2M_A9TR40 U526 ( .AN(seq_medium_inc), .B(medium_code[4]), .Y(n374) );
  NAND2_X3B_A9TR40 U527 ( .A(n646), .B(n374), .Y(n530) );
  AOI31_X6M_A9TR40 U528 ( .A0(n491), .A1(n376), .A2(n671), .B0(n375), .Y(n521)
         );
  NAND2_X2B_A9TR40 U529 ( .A(n377), .B(n530), .Y(n378) );
  NAND2_X3B_A9TR40 U530 ( .A(medium_code[1]), .B(medium_code[0]), .Y(n464) );
  MXIT2_X3M_A9TR40 U531 ( .A(n385), .B(n380), .S0(n454), .Y(n381) );
  NOR2_X3M_A9TR40 U532 ( .A(medium_code[1]), .B(medium_code[2]), .Y(n533) );
  AOI21B_X6M_A9TR40 U533 ( .A0(medium_code[3]), .A1(n394), .B0N(n431), .Y(n490) );
  NAND2_X1P4M_A9TR40 U534 ( .A(n522), .B(n500), .Y(n456) );
  MXIT2_X0P7M_A9TR40 U535 ( .A(n456), .B(n500), .S0(n392), .Y(n384) );
  INV_X1M_A9TR40 U536 ( .A(fine_code[1]), .Y(n387) );
  NAND2_X2B_A9TR40 U537 ( .A(n387), .B(n659), .Y(n644) );
  NAND2_X1P4M_A9TR40 U538 ( .A(n646), .B(seq_fine_inc), .Y(n643) );
  NAND2_X2B_A9TR40 U539 ( .A(n662), .B(fine_code[0]), .Y(n388) );
  NAND2_X1B_A9TR40 U540 ( .A(n613), .B(fine_code[1]), .Y(n389) );
  OA21_X1M_A9TR40 U541 ( .A0(fine_code[1]), .A1(n679), .B0(n611), .Y(n616) );
  INV_X1M_A9TR40 U542 ( .A(n659), .Y(n650) );
  INV_X1P7B_A9TR40 U543 ( .A(n431), .Y(n390) );
  INV_X1M_A9TR40 U544 ( .A(medium_code[4]), .Y(n525) );
  NOR3_X3A_A9TR40 U545 ( .A(n668), .B(n490), .C(n671), .Y(n580) );
  BUF_X2M_A9TR40 U546 ( .A(n646), .Y(n514) );
  INV_X1M_A9TR40 U547 ( .A(n514), .Y(n391) );
  NOR2_X2A_A9TR40 U548 ( .A(n454), .B(n391), .Y(n497) );
  NOR2_X1P4M_A9TR40 U549 ( .A(n393), .B(n392), .Y(n496) );
  NOR2B_X6M_A9TR40 U550 ( .AN(n394), .B(n496), .Y(n494) );
  INV_X1M_A9TR40 U551 ( .A(n670), .Y(n535) );
  INV_X1M_A9TR40 U552 ( .A(n530), .Y(n673) );
  AOI31_X1M_A9TR40 U553 ( .A0(n673), .A1(n395), .A2(medium_code[3]), .B0(
        medium_therm[8]), .Y(n396) );
  AOI211_X2M_A9TR40 U554 ( .A0(n580), .A1(n535), .B0(n679), .C0(n396), .Y(n299) );
  BUF_X2M_A9TR40 U555 ( .A(n714), .Y(fsm_state[2]) );
  INV_X2P5B_A9TR40 U556 ( .A(n714), .Y(n515) );
  INV_X2M_A9TR40 U557 ( .A(n398), .Y(n402) );
  INV_X1M_A9TR40 U558 ( .A(n402), .Y(n542) );
  NOR4BB_X4M_A9TR40 U559 ( .AN(fine_code[3]), .BN(fine_code[1]), .C(
        fine_code[2]), .D(fine_code[0]), .Y(n407) );
  INV_X2M_A9TR40 U560 ( .A(n446), .Y(n629) );
  NAND2_X3B_A9TR40 U561 ( .A(n405), .B(n713), .Y(n425) );
  AOI22BB_X4M_A9TR40 U562 ( .A0(n629), .A1(n398), .B0N(n425), .B1N(
        fsm_state[0]), .Y(n548) );
  NOR2B_X6M_A9TR40 U563 ( .AN(n714), .B(n715), .Y(n552) );
  INV_X4M_A9TR40 U564 ( .A(n458), .Y(n601) );
  AO1B2_X4M_A9TR40 U565 ( .B0(n548), .B1(n427), .A0N(n601), .Y(n481) );
  NOR2_X8B_A9TR40 U566 ( .A(fsm_state[0]), .B(n713), .Y(n560) );
  AOI21_X1M_A9TR40 U567 ( .A0(n713), .A1(n714), .B0(seq_done), .Y(n399) );
  OAI211_X2M_A9TR40 U568 ( .A0(fsm_state[0]), .A1(n715), .B0(n399), .C0(n556), 
        .Y(n400) );
  AND3_X6M_A9TR40 U569 ( .A(n481), .B(n365), .C(n549), .Y(n625) );
  OAI211_X1M_A9TR40 U570 ( .A0(n542), .A1(n442), .B0(fsm_state[0]), .C0(n625), 
        .Y(n404) );
  AOI22_X0P7M_A9TR40 U571 ( .A0(n552), .A1(n446), .B0(n482), .B1(fsm_state[2]), 
        .Y(n403) );
  NAND2_X1B_A9TR40 U572 ( .A(n560), .B(n405), .Y(n545) );
  INV_X2M_A9TR40 U573 ( .A(fsm_state[0]), .Y(n447) );
  INV_X6M_A9TR40 U574 ( .A(n427), .Y(n448) );
  AND2_X6B_A9TR40 U575 ( .A(n448), .B(n447), .Y(n537) );
  AOI21_X1M_A9TR40 U576 ( .A0(n405), .A1(n447), .B0(n537), .Y(n410) );
  NOR2_X2B_A9TR40 U577 ( .A(medium_code[4]), .B(n712), .Y(n406) );
  NAND2_X2B_A9TR40 U578 ( .A(n432), .B(n473), .Y(n599) );
  OAI21_X1M_A9TR40 U579 ( .A0(n599), .A1(fsm_state[1]), .B0(n560), .Y(n409) );
  INV_X2M_A9TR40 U580 ( .A(\q_class[1] ), .Y(n590) );
  NAND2_X2B_A9TR40 U581 ( .A(n709), .B(n590), .Y(n475) );
  NAND2_X1B_A9TR40 U582 ( .A(n448), .B(n475), .Y(n633) );
  NAND2XB_X1M_A9TR40 U583 ( .BN(\u_fsm/fine_probe_result_q [1]), .A(
        \u_fsm/fine_probe_result_q [0]), .Y(n632) );
  INV_X1M_A9TR40 U584 ( .A(n425), .Y(n460) );
  OAI21_X1M_A9TR40 U585 ( .A0(n407), .A1(n632), .B0(n460), .Y(n408) );
  MXIT2_X1P4M_A9TR40 U586 ( .A(fsm_state[0]), .B(n411), .S0(n625), .Y(n412) );
  NOR3_X3A_A9TR40 U587 ( .A(n527), .B(n668), .C(medium_code[0]), .Y(n572) );
  AOI31_X1M_A9TR40 U588 ( .A0(n673), .A1(n672), .A2(medium_code[0]), .B0(
        medium_therm[1]), .Y(n413) );
  NAND2_X3B_A9TR40 U589 ( .A(n690), .B(seq_req), .Y(n443) );
  INV_X1M_A9TR40 U590 ( .A(seq_cmd[0]), .Y(n566) );
  NAND2_X1B_A9TR40 U591 ( .A(n566), .B(seq_cmd[1]), .Y(n414) );
  NOR2_X2M_A9TR40 U592 ( .A(n443), .B(n414), .Y(n620) );
  INV_X1M_A9TR40 U593 ( .A(seq_cmd[1]), .Y(n415) );
  INV_X3P5B_A9TR40 U594 ( .A(\u_sequencer/active_cmd_q [1]), .Y(n536) );
  NAND2_X2B_A9TR40 U595 ( .A(n536), .B(\u_sequencer/active_cmd_q [0]), .Y(n684) );
  XNOR2_X1P4M_A9TR40 U596 ( .A(n684), .B(\u_sequencer/probe_count_q [3]), .Y(
        n418) );
  NAND2_X2B_A9TR40 U597 ( .A(n418), .B(n417), .Y(n513) );
  NAND3BB_X2M_A9TR40 U598 ( .AN(n620), .BN(n617), .C(n419), .Y(n335) );
  NOR2_X1A_A9TR40 U599 ( .A(n419), .B(n686), .Y(n623) );
  NAND3_X1M_A9TR40 U600 ( .A(n623), .B(\u_sequencer/probe_count_q [2]), .C(
        \u_sequencer/probe_count_q [1]), .Y(n422) );
  AO21A1AI2_X2M_A9TR40 U601 ( .A0(\u_sequencer/probe_count_q [0]), .A1(
        \u_sequencer/probe_count_q [1]), .B0(n690), .C0(n335), .Y(n622) );
  AOI21_X1M_A9TR40 U602 ( .A0(seq_busy), .A1(n420), .B0(n622), .Y(n421) );
  MXIT2_X1P4M_A9TR40 U603 ( .A(n422), .B(n421), .S0(
        \u_sequencer/probe_count_q [3]), .Y(n338) );
  BUF_X2M_A9TR40 U604 ( .A(n713), .Y(fsm_state[3]) );
  NAND4_X2A_A9TR40 U605 ( .A(n423), .B(medium_code[4]), .C(n529), .D(n500), 
        .Y(n424) );
  INV_X1M_A9TR40 U606 ( .A(n537), .Y(n554) );
  NOR2_X4M_A9TR40 U607 ( .A(n425), .B(n447), .Y(n609) );
  NAND2_X4B_A9TR40 U608 ( .A(n609), .B(n555), .Y(n630) );
  INV_X1P7B_A9TR40 U609 ( .A(n630), .Y(n561) );
  AND2_X3B_A9TR40 U610 ( .A(n552), .B(n560), .Y(n470) );
  AOI31_X1P4M_A9TR40 U611 ( .A0(n553), .A1(n554), .A2(n630), .B0(n426), .Y(
        n438) );
  NOR2_X3B_A9TR40 U612 ( .A(n427), .B(n458), .Y(n544) );
  NOR2_X1A_A9TR40 U613 ( .A(n627), .B(fsm_state[1]), .Y(n429) );
  NOR2_X2B_A9TR40 U614 ( .A(fsm_state[0]), .B(n714), .Y(n507) );
  NAND2_X1B_A9TR40 U615 ( .A(n507), .B(fsm_state[3]), .Y(n428) );
  OA211_X2M_A9TR40 U616 ( .A0(n429), .A1(n560), .B0(n428), .C0(n592), .Y(n430)
         );
  NOR3_X2A_A9TR40 U617 ( .A(n432), .B(n431), .C(n525), .Y(n471) );
  NAND2_X1B_A9TR40 U618 ( .A(n471), .B(n470), .Y(n434) );
  NAND3_X0P7A_A9TR40 U619 ( .A(n602), .B(n603), .C(fail_reason[0]), .Y(n433)
         );
  OAI211_X1P4M_A9TR40 U620 ( .A0(n637), .A1(n565), .B0(n434), .C0(n433), .Y(
        n437) );
  NAND2_X2B_A9TR40 U621 ( .A(n609), .B(n407), .Y(n634) );
  AND2_X1M_A9TR40 U622 ( .A(n637), .B(fail_reason[0]), .Y(n435) );
  OR4_X2M_A9TR40 U623 ( .A(n438), .B(n437), .C(n436), .D(n435), .Y(n323) );
  INV_X0P6B_A9TR40 U624 ( .A(seq_req), .Y(n441) );
  INV_X2M_A9TR40 U625 ( .A(n606), .Y(n516) );
  INV_X1M_A9TR40 U626 ( .A(n439), .Y(n607) );
  INV_X1M_A9TR40 U627 ( .A(n715), .Y(n485) );
  AOI22_X0P5M_A9TR40 U628 ( .A0(seq_done), .A1(n607), .B0(n508), .B1(n560), 
        .Y(n440) );
  AO21A1AI2_X1M_A9TR40 U629 ( .A0(n442), .A1(n441), .B0(n516), .C0(n440), .Y(
        n445) );
  AOI31_X2M_A9TR40 U630 ( .A0(n548), .A1(n549), .A2(n427), .B0(n443), .Y(n444)
         );
  NAND2_X1B_A9TR40 U631 ( .A(fsm_state[1]), .B(fsm_state[2]), .Y(n594) );
  OAI22_X0P7M_A9TR40 U632 ( .A0(fsm_state[3]), .A1(n594), .B0(n446), .B1(n515), 
        .Y(n450) );
  AND2_X2M_A9TR40 U633 ( .A(n603), .B(n447), .Y(n449) );
  AOI22_X1M_A9TR40 U634 ( .A0(seq_done), .A1(n450), .B0(n543), .B1(n458), .Y(
        n452) );
  OAI21_X1M_A9TR40 U635 ( .A0(n563), .A1(seq_req), .B0(n470), .Y(n451) );
  NAND2_X1B_A9TR40 U636 ( .A(n454), .B(n514), .Y(n493) );
  NOR2_X2A_A9TR40 U637 ( .A(n455), .B(n493), .Y(n576) );
  NOR2_X1M_A9TR40 U638 ( .A(n530), .B(n456), .Y(n570) );
  AOI21_X1M_A9TR40 U639 ( .A0(n570), .A1(n392), .B0(medium_therm[3]), .Y(n457)
         );
  INV_X1M_A9TR40 U640 ( .A(\u_fsm/coarse_probe_b_result_q [1]), .Y(n461) );
  NOR2_X2A_A9TR40 U641 ( .A(n462), .B(n460), .Y(n512) );
  MXIT2_X1M_A9TR40 U642 ( .A(n461), .B(n590), .S0(n512), .Y(n329) );
  INV_X1M_A9TR40 U643 ( .A(\u_fsm/fine_probe_result_q [0]), .Y(n463) );
  NOR2_X2A_A9TR40 U644 ( .A(n462), .B(n542), .Y(n488) );
  NOR2_X1P4M_A9TR40 U645 ( .A(n465), .B(n464), .Y(n467) );
  MXIT2_X1P4M_A9TR40 U646 ( .A(n467), .B(n466), .S0(medium_code[2]), .Y(n468)
         );
  OAI31_X1P4M_A9TR40 U647 ( .A0(n538), .A1(n543), .A2(n637), .B0(
        fail_reason[1]), .Y(n478) );
  INV_X4M_A9TR40 U648 ( .A(n637), .Y(n541) );
  AOI31_X1M_A9TR40 U649 ( .A0(n541), .A1(n602), .A2(n475), .B0(n474), .Y(n477)
         );
  NAND2_X2B_A9TR40 U650 ( .A(n563), .B(n470), .Y(n631) );
  INV_X1M_A9TR40 U651 ( .A(n545), .Y(n642) );
  INV_X1M_A9TR40 U652 ( .A(n481), .Y(n487) );
  NAND3_X1M_A9TR40 U653 ( .A(n519), .B(n552), .C(n627), .Y(n483) );
  NOR4BB_X2M_A9TR40 U654 ( .AN(n633), .BN(n483), .C(n482), .D(n606), .Y(n484)
         );
  INV_X1M_A9TR40 U655 ( .A(\u_fsm/fine_probe_result_q [1]), .Y(n489) );
  NAND2_X1B_A9TR40 U656 ( .A(n490), .B(medium_code[0]), .Y(n669) );
  NOR2_X2A_A9TR40 U657 ( .A(n494), .B(n493), .Y(n579) );
  AOI31_X0P7M_A9TR40 U658 ( .A0(n577), .A1(medium_code[2]), .A2(n500), .B0(
        medium_therm[6]), .Y(n495) );
  AOI211_X2M_A9TR40 U659 ( .A0(n502), .A1(n579), .B0(n679), .C0(n495), .Y(n301) );
  NOR3_X2A_A9TR40 U660 ( .A(n530), .B(medium_code[1]), .C(n392), .Y(n677) );
  AOI31_X1M_A9TR40 U661 ( .A0(n677), .A1(medium_code[3]), .A2(n671), .B0(
        medium_therm[12]), .Y(n498) );
  AOI211_X2M_A9TR40 U662 ( .A0(n580), .A1(n680), .B0(n679), .C0(n498), .Y(n295) );
  AOI31_X1M_A9TR40 U663 ( .A0(n677), .A1(medium_code[0]), .A2(n500), .B0(
        medium_therm[5]), .Y(n499) );
  AOI211_X2M_A9TR40 U664 ( .A0(n572), .A1(n680), .B0(n679), .C0(n499), .Y(n302) );
  AOI31_X1M_A9TR40 U665 ( .A0(n677), .A1(n500), .A2(n671), .B0(medium_therm[4]), .Y(n501) );
  AOI211_X2M_A9TR40 U666 ( .A0(n502), .A1(n680), .B0(n362), .C0(n501), .Y(n303) );
  AOI31_X1M_A9TR40 U667 ( .A0(n577), .A1(medium_code[3]), .A2(n392), .B0(
        medium_therm[10]), .Y(n503) );
  AOI211_X2M_A9TR40 U668 ( .A0(n580), .A1(n576), .B0(n679), .C0(n503), .Y(n297) );
  BUF_X0P7M_A9TR40 U669 ( .A(n711), .Y(n708) );
  BUF_X0P7M_A9TR40 U670 ( .A(n711), .Y(n705) );
  BUF_X0P7M_A9TR40 U671 ( .A(n711), .Y(n707) );
  AND2_X1M_A9TR40 U672 ( .A(n617), .B(fsm_fine_inc), .Y(n702) );
  AND2_X1M_A9TR40 U673 ( .A(n617), .B(fsm_medium_dec), .Y(n701) );
  AND2_X1M_A9TR40 U674 ( .A(n617), .B(fsm_medium_inc), .Y(n699) );
  NAND2_X1B_A9TR40 U675 ( .A(\u_sequencer/probe_count_q [0]), .B(seq_busy), 
        .Y(n694) );
  NOR2_X1A_A9TR40 U676 ( .A(n694), .B(n536), .Y(n505) );
  INV_X1M_A9TR40 U677 ( .A(\u_fsm/coarse_probe_a_result_q [0]), .Y(n510) );
  NAND2_X0P5B_A9TR40 U678 ( .A(n507), .B(n627), .Y(n509) );
  NAND2XB_X1M_A9TR40 U679 ( .BN(n509), .A(n508), .Y(n591) );
  MXIT2_X0P7M_A9TR40 U680 ( .A(n709), .B(n510), .S0(n591), .Y(n326) );
  MXIT2_X0P7M_A9TR40 U681 ( .A(n511), .B(n523), .S0(n671), .Y(n353) );
  NOR2_X1A_A9TR40 U682 ( .A(n513), .B(n690), .Y(\u_sequencer/N51 ) );
  NOR2_X1A_A9TR40 U683 ( .A(n362), .B(n514), .Y(n344) );
  NOR2_X1M_A9TR40 U684 ( .A(n516), .B(n515), .Y(n596) );
  AOI211_X1M_A9TR40 U685 ( .A0(n596), .A1(n690), .B0(fsm_state[3]), .C0(n516), 
        .Y(n518) );
  OAI22_X1M_A9TR40 U686 ( .A0(n600), .A1(n519), .B0(n518), .B1(n517), .Y(n334)
         );
  INV_X1M_A9TR40 U687 ( .A(n520), .Y(n526) );
  AO21A1AI2_X1M_A9TR40 U688 ( .A0(n522), .A1(n366), .B0(n521), .C0(n668), .Y(
        n524) );
  OAI22_X1M_A9TR40 U689 ( .A0(n526), .A1(n525), .B0(n524), .B1(n523), .Y(n349)
         );
  NAND3B_X2M_A9TR40 U690 ( .AN(n668), .B(n527), .C(n671), .Y(n528) );
  NAND2_X1B_A9TR40 U691 ( .A(medium_code[0]), .B(medium_code[3]), .Y(n532) );
  AOI21_X0P7M_A9TR40 U692 ( .A0(n574), .A1(medium_code[2]), .B0(
        medium_therm[15]), .Y(n531) );
  AOI211_X2M_A9TR40 U693 ( .A0(n681), .A1(n579), .B0(n362), .C0(n531), .Y(n292) );
  AOI31_X1M_A9TR40 U694 ( .A0(n673), .A1(n533), .A2(n676), .B0(medium_therm[9]), .Y(n534) );
  AOI211_X2M_A9TR40 U695 ( .A0(n681), .A1(n535), .B0(n679), .C0(n534), .Y(n298) );
  INV_X1M_A9TR40 U696 ( .A(n620), .Y(n689) );
  OAI21_X1M_A9TR40 U697 ( .A0(n617), .A1(n536), .B0(n689), .Y(n336) );
  OAI211_X1M_A9TR40 U698 ( .A0(n563), .A1(n600), .B0(n633), .C0(n634), .Y(n540) );
  OAI31_X1M_A9TR40 U699 ( .A0(n538), .A1(n537), .A2(n637), .B0(cal_fail), .Y(
        n539) );
  AO21B_X1M_A9TR40 U700 ( .A0(n541), .A1(n540), .B0N(n539), .Y(n320) );
  NOR3_X1M_A9TR40 U701 ( .A(n543), .B(n542), .C(n629), .Y(n559) );
  INV_X1M_A9TR40 U702 ( .A(n544), .Y(n547) );
  NAND2_X2B_A9TR40 U703 ( .A(n365), .B(n545), .Y(n546) );
  NOR2B_X6M_A9TR40 U704 ( .AN(n547), .B(n546), .Y(n551) );
  NAND4_X4A_A9TR40 U705 ( .A(n551), .B(n550), .C(n549), .D(n548), .Y(n568) );
  NAND2_X2B_A9TR40 U706 ( .A(n553), .B(n552), .Y(n628) );
  OAI211_X2M_A9TR40 U707 ( .A0(n556), .A1(n555), .B0(n554), .C0(n628), .Y(n557) );
  OAI21_X2M_A9TR40 U708 ( .A0(n557), .A1(n568), .B0(seq_cmd[1]), .Y(n558) );
  OAI21_X1P4M_A9TR40 U709 ( .A0(n559), .A1(n568), .B0(n558), .Y(n343) );
  NAND2_X1B_A9TR40 U710 ( .A(n560), .B(fsm_state[2]), .Y(n564) );
  OA21A1OI2_X1M_A9TR40 U711 ( .A0(n563), .A1(fsm_state[1]), .B0(n562), .C0(
        n561), .Y(n569) );
  OAI22_X1P4M_A9TR40 U712 ( .A0(n569), .A1(n568), .B0(n567), .B1(n566), .Y(
        n342) );
  AOI21_X1M_A9TR40 U713 ( .A0(n570), .A1(medium_code[2]), .B0(medium_therm[7]), 
        .Y(n571) );
  AOI211_X1M_A9TR40 U714 ( .A0(n572), .A1(n579), .B0(n679), .C0(n571), .Y(n300) );
  AOI21_X1M_A9TR40 U715 ( .A0(n574), .A1(n392), .B0(medium_therm[11]), .Y(n575) );
  AOI211_X2M_A9TR40 U716 ( .A0(n681), .A1(n576), .B0(n362), .C0(n575), .Y(n296) );
  AOI21_X1M_A9TR40 U717 ( .A0(n577), .A1(n366), .B0(medium_therm[14]), .Y(n578) );
  AOI211_X1M_A9TR40 U718 ( .A0(n580), .A1(n579), .B0(n679), .C0(n578), .Y(n293) );
  INV_X1M_A9TR40 U719 ( .A(n581), .Y(n621) );
  NAND2_X1B_A9TR40 U720 ( .A(n335), .B(n621), .Y(n582) );
  MXIT2_X0P7M_A9TR40 U721 ( .A(n623), .B(n582), .S0(
        \u_sequencer/probe_count_q [1]), .Y(n583) );
  INV_X1M_A9TR40 U722 ( .A(n583), .Y(n340) );
  INV_X1M_A9TR40 U723 ( .A(\u_sequencer/probe_count_q [3]), .Y(n683) );
  NOR3BB_X1M_A9TR40 U724 ( .AN(n584), .BN(n684), .C(n694), .Y(
        \u_sequencer/N54 ) );
  NAND2_X1B_A9TR40 U725 ( .A(\u_sequencer/u_q_sampler/n1 ), .B(q_final), .Y(
        n586) );
  OAI211_X1M_A9TR40 U726 ( .A0(q_final), .A1(\u_sequencer/u_q_sampler/n1 ), 
        .B0(n586), .C0(n585), .Y(n587) );
  AO21B_X1M_A9TR40 U727 ( .A0(\q_class[1] ), .A1(n588), .B0N(n587), .Y(n289)
         );
  NAND2_X1B_A9TR40 U728 ( .A(n591), .B(\u_fsm/coarse_probe_a_result_q [1]), 
        .Y(n589) );
  OAI21_X1M_A9TR40 U729 ( .A0(n591), .A1(n590), .B0(n589), .Y(n327) );
  NAND3_X1M_A9TR40 U730 ( .A(n593), .B(fsm_state[2]), .C(seq_done), .Y(n598)
         );
  INV_X1M_A9TR40 U731 ( .A(n594), .Y(n624) );
  AOI21_X1M_A9TR40 U732 ( .A0(n624), .A1(seq_busy), .B0(n606), .Y(n595) );
  OAI211_X1M_A9TR40 U733 ( .A0(n600), .A1(n599), .B0(n598), .C0(n597), .Y(n318) );
  OAI21_X1M_A9TR40 U734 ( .A0(n642), .A1(n605), .B0(n640), .Y(n325) );
  AOI21_X1M_A9TR40 U735 ( .A0(n607), .A1(seq_busy), .B0(n606), .Y(n608) );
  OAI31_X1M_A9TR40 U736 ( .A0(n609), .A1(fsm_state[2]), .A2(n608), .B0(
        fsm_fine_inc), .Y(n610) );
  NAND2_X1B_A9TR40 U737 ( .A(n610), .B(n630), .Y(n358) );
  OA21B_X1M_A9TR40 U738 ( .A0(fine_code[0]), .A1(n662), .B0N(n611), .Y(n357)
         );
  INV_X1M_A9TR40 U739 ( .A(n613), .Y(n612) );
  MXIT2_X0P7M_A9TR40 U740 ( .A(n612), .B(n611), .S0(fine_code[1]), .Y(n356) );
  OAI21_X1M_A9TR40 U741 ( .A0(n616), .A1(n615), .B0(n614), .Y(n354) );
  INV_X1M_A9TR40 U742 ( .A(\u_sequencer/active_cmd_q [0]), .Y(n619) );
  INV_X1M_A9TR40 U743 ( .A(n617), .Y(n618) );
  OAI21_X1M_A9TR40 U744 ( .A0(n620), .A1(n619), .B0(n618), .Y(n337) );
  OAI21_X1M_A9TR40 U745 ( .A0(n335), .A1(n686), .B0(n621), .Y(n341) );
  AO22_X1M_A9TR40 U746 ( .A0(n685), .A1(n623), .B0(
        \u_sequencer/probe_count_q [2]), .B1(n622), .Y(n339) );
  OAI211_X1M_A9TR40 U747 ( .A0(n629), .A1(n628), .B0(n627), .C0(n626), .Y(n348) );
  NAND3_X1M_A9TR40 U748 ( .A(n631), .B(n427), .C(n630), .Y(n638) );
  OA21A1OI2_X4M_A9TR40 U749 ( .A0(n635), .A1(n634), .B0(n633), .C0(n637), .Y(
        n636) );
  INV_X1M_A9TR40 U750 ( .A(n639), .Y(n321) );
  OAI21_X1M_A9TR40 U751 ( .A0(n642), .A1(n641), .B0(n640), .Y(n324) );
  NOR3_X2A_A9TR40 U752 ( .A(n643), .B(fine_code[0]), .C(fine_code[3]), .Y(n653) );
  INV_X1M_A9TR40 U753 ( .A(n644), .Y(n648) );
  AO21A1AI2_X1M_A9TR40 U754 ( .A0(n653), .A1(n648), .B0(n645), .C0(n666), .Y(
        n317) );
  INV_X1M_A9TR40 U755 ( .A(fine_code[0]), .Y(n664) );
  NOR4BB_X1M_A9TR40 U756 ( .AN(n646), .BN(seq_fine_inc), .C(fine_code[3]), .D(
        n664), .Y(n656) );
  AO21A1AI2_X1M_A9TR40 U757 ( .A0(n656), .A1(n648), .B0(n647), .C0(n666), .Y(
        n316) );
  NAND2_X1B_A9TR40 U758 ( .A(n653), .B(fine_code[1]), .Y(n657) );
  OAI21_X1M_A9TR40 U759 ( .A0(n657), .A1(n650), .B0(fine_therm[2]), .Y(n649)
         );
  NAND2_X1B_A9TR40 U760 ( .A(n649), .B(n666), .Y(n315) );
  NAND2_X1B_A9TR40 U761 ( .A(n656), .B(fine_code[1]), .Y(n660) );
  OAI21_X1M_A9TR40 U762 ( .A0(n660), .A1(n650), .B0(fine_therm[3]), .Y(n651)
         );
  NAND2_X1B_A9TR40 U763 ( .A(n651), .B(n666), .Y(n314) );
  AO21A1AI2_X1M_A9TR40 U764 ( .A0(n653), .A1(n655), .B0(n652), .C0(n666), .Y(
        n313) );
  AO21A1AI2_X1M_A9TR40 U765 ( .A0(n656), .A1(n655), .B0(n654), .C0(n666), .Y(
        n312) );
  OAI21_X1M_A9TR40 U766 ( .A0(n657), .A1(n659), .B0(fine_therm[6]), .Y(n658)
         );
  NAND2_X1B_A9TR40 U767 ( .A(n658), .B(n666), .Y(n311) );
  OAI21_X1M_A9TR40 U768 ( .A0(n660), .A1(n659), .B0(fine_therm[7]), .Y(n661)
         );
  NAND2_X1B_A9TR40 U769 ( .A(n661), .B(n666), .Y(n310) );
  NAND2_X1B_A9TR40 U770 ( .A(n662), .B(fine_code[3]), .Y(n665) );
  OAI21_X1M_A9TR40 U771 ( .A0(n665), .A1(fine_code[0]), .B0(fine_therm[8]), 
        .Y(n663) );
  NAND2_X1B_A9TR40 U772 ( .A(n663), .B(n666), .Y(n309) );
  OAI21_X1M_A9TR40 U773 ( .A0(n665), .A1(n664), .B0(fine_therm[9]), .Y(n667)
         );
  NAND2_X1B_A9TR40 U774 ( .A(n667), .B(n666), .Y(n308) );
  NAND3_X1M_A9TR40 U775 ( .A(n673), .B(n672), .C(n671), .Y(n674) );
  AOI21_X1M_A9TR40 U776 ( .A0(n675), .A1(n674), .B0(n362), .Y(n307) );
  AOI21_X1M_A9TR40 U777 ( .A0(n677), .A1(n676), .B0(medium_therm[13]), .Y(n678) );
  AOI211_X2M_A9TR40 U778 ( .A0(n681), .A1(n680), .B0(n679), .C0(n678), .Y(n294) );
  NAND2_X1B_A9TR40 U779 ( .A(n684), .B(n683), .Y(n692) );
  NOR4BB_X1M_A9TR40 U780 ( .AN(n693), .BN(n686), .C(n685), .D(n692), .Y(n688)
         );
  OAI21_X1M_A9TR40 U781 ( .A0(n688), .A1(sense_s_clk), .B0(seq_busy), .Y(n687)
         );
  AOI21_X1M_A9TR40 U782 ( .A0(\u_sequencer/probe_count_q [2]), .A1(n688), .B0(
        n687), .Y(n333) );
  OAI21_X1M_A9TR40 U783 ( .A0(sense_dff_reset), .A1(n690), .B0(n689), .Y(n691)
         );
endmodule

