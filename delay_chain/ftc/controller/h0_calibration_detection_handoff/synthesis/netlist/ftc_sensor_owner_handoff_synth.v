/////////////////////////////////////////////////////////////
// Created by: Synopsys DC Expert(TM) in wire load mode
// Version   : W-2024.09
// Date      : Sun Aug 23 04:11:32 2026
/////////////////////////////////////////////////////////////


module ftc_sensor_owner_handoff ( cal_clk_i, ctrl_por_n_i, cal_busy_i,
        cal_done_i, cal_fail_i, lock_valid_i, cal_sense_dff_reset_i,
        cal_sense_s_clk_i, cal_medium_therm_i, cal_fine_therm_i,
        cal_medium_code_i, cal_fine_code_i, det_takeover_ready_i,
        det_sense_dff_reset_i, det_sense_s_clk_i, det_medium_therm_i,
        det_fine_therm_i, sense_dff_reset_o, sense_s_clk_o, medium_therm_o,
        fine_therm_o, cal_cfg_valid_o, cal_medium_code_snapshot_o,
        cal_fine_code_snapshot_o, cal_medium_therm_snapshot_o,
        cal_fine_therm_snapshot_o, det_prepare_o, det_owner_valid_o,
        handoff_blocked_o, handoff_protocol_error_o, handoff_state_o );
  input [15:0] cal_medium_therm_i;
  input [9:0] cal_fine_therm_i;
  input [4:0] cal_medium_code_i;
  input [3:0] cal_fine_code_i;
  input [15:0] det_medium_therm_i;
  input [9:0] det_fine_therm_i;
  output [15:0] medium_therm_o;
  output [9:0] fine_therm_o;
  output [4:0] cal_medium_code_snapshot_o;
  output [3:0] cal_fine_code_snapshot_o;
  output [15:0] cal_medium_therm_snapshot_o;
  output [9:0] cal_fine_therm_snapshot_o;
  output [2:0] handoff_state_o;
  input cal_clk_i, ctrl_por_n_i, cal_busy_i, cal_done_i, cal_fail_i,
         lock_valid_i, cal_sense_dff_reset_i, cal_sense_s_clk_i,
         det_takeover_ready_i, det_sense_dff_reset_i, det_sense_s_clk_i;
  output sense_dff_reset_o, sense_s_clk_o, cal_cfg_valid_o, det_prepare_o,
         det_owner_valid_o, handoff_blocked_o, handoff_protocol_error_o;
  wire   N22, N23, sensor_cal_enable_d, sensor_safe_enable_d,
         sensor_det_enable_d, sensor_cal_enable_q, sensor_safe_enable_q,
         sensor_det_enable_q, sensor_blocked_enable_q, blocked_hold_valid_q,
         n6, n7, n11, n12, n15, n17, n19, n20, n22, n25, n27, n29, n31, n107,
         n108, n109, n111, n112, n113, n114, n115, n116, n117, n118, n119,
         n120, n121, n122, n123, n124, n125, n126, n127, n128, n129, n130,
         n131, n132, n133, n134, n135, n136, n137, n138, n139, n140, n141,
         n142, n143, n144, n145, n146, n147, n148, n149, n150, n151, n152,
         n153, n154, n155, n156, n157, n158, n159, n160, n161, n162, n163,
         n164, n165, n166, n167, n168, n169, n170, n171, n172, n173, n174,
         n175, n176, n177, n178, n179, n180, n181, n182, n183, n184, n185,
         n186, n187, n188, n189, n190, n191, n192, n193, n194, n195, n196,
         n197, n198, n199, n200, n201, n202, n203, n204, n208, n209, n210,
         n211, n212, n213, n214, n215, n216, n217, n218, n219, n220, n221,
         n222, n223, n224, n225, n226, n227, n228, n229, n230, n231, n232,
         n233, n234, n235, n236, n237, n238, n239, n240, n241, n242, n243,
         n244, n245, n246, n247, n248, n249, n250, n251, n252, n253, n254,
         n255, n256, n257, n258, n259, n260, n261, n262, n263, n264, n265,
         n266, n267, n268, n269, n270, n271, n272, n273, n274, n275, n276,
         n277, n278, n279, n280, n281, n282, n283, n284, n285, n286, n287,
         n288, n289, n290, n291, n292, n293, n294, n295, n296, n297, n298,
         n299, n300, n301, n302, n303, n304, n305, n306, n307, n308, n309,
         n310, n311, n312, n313, n314, n315, n316, n317, n318, n319, n320,
         n321, n322, n323, n324, n325, n326, n327, n328, n329, n330, n331,
         n332, n333, n334, n335, n336, n337, n338, n339, n340, n341, n342,
         n343, n344, n345, n346, n347, n348, n349, n350, n351, n352, n353,
         n354, n355, n356, n357, n358, n359, n360, n361, n362, n363, n364,
         n365, n366, n367, n368, n369, n370, n371, n372, n373, n374, n375,
         n376, n377, n378, n379, n380, n381, n382, n383, n384;
  wire   [2:0] state_d;
  wire   [15:0] blocked_medium_q;
  wire   [9:0] blocked_fine_q;

  DFFRPQ_X1M_A9TR40 \blocked_fine_q_reg[9]  ( .D(n166), .CK(cal_clk_i), .R(
        n214), .Q(blocked_fine_q[9]) );
  DFFRPQ_X1M_A9TR40 \blocked_fine_q_reg[8]  ( .D(n165), .CK(cal_clk_i), .R(
        n214), .Q(blocked_fine_q[8]) );
  DFFRPQ_X1M_A9TR40 \blocked_fine_q_reg[7]  ( .D(n164), .CK(cal_clk_i), .R(
        n214), .Q(blocked_fine_q[7]) );
  DFFRPQ_X1M_A9TR40 \blocked_fine_q_reg[6]  ( .D(n163), .CK(cal_clk_i), .R(
        n214), .Q(blocked_fine_q[6]) );
  DFFRPQ_X1M_A9TR40 \blocked_fine_q_reg[5]  ( .D(n162), .CK(cal_clk_i), .R(
        n214), .Q(blocked_fine_q[5]) );
  DFFRPQ_X1M_A9TR40 \blocked_fine_q_reg[4]  ( .D(n161), .CK(cal_clk_i), .R(
        n214), .Q(blocked_fine_q[4]) );
  DFFRPQ_X1M_A9TR40 \blocked_fine_q_reg[3]  ( .D(n160), .CK(cal_clk_i), .R(
        n214), .Q(blocked_fine_q[3]) );
  DFFRPQ_X1M_A9TR40 \blocked_fine_q_reg[2]  ( .D(n159), .CK(cal_clk_i), .R(
        n214), .Q(blocked_fine_q[2]) );
  DFFRPQ_X1M_A9TR40 \blocked_fine_q_reg[1]  ( .D(n158), .CK(cal_clk_i), .R(
        n214), .Q(blocked_fine_q[1]) );
  DFFRPQ_X1M_A9TR40 \blocked_fine_q_reg[0]  ( .D(n157), .CK(cal_clk_i), .R(
        n214), .Q(blocked_fine_q[0]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[15]  ( .D(n156), .CK(cal_clk_i), .R(
        n214), .Q(blocked_medium_q[15]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[14]  ( .D(n155), .CK(cal_clk_i), .R(
        n214), .Q(blocked_medium_q[14]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[13]  ( .D(n154), .CK(cal_clk_i), .R(
        n215), .Q(blocked_medium_q[13]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[12]  ( .D(n153), .CK(cal_clk_i), .R(
        n215), .Q(blocked_medium_q[12]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[11]  ( .D(n152), .CK(cal_clk_i), .R(
        n215), .Q(blocked_medium_q[11]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[10]  ( .D(n151), .CK(cal_clk_i), .R(
        n215), .Q(blocked_medium_q[10]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[9]  ( .D(n150), .CK(cal_clk_i), .R(
        n215), .Q(blocked_medium_q[9]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[8]  ( .D(n149), .CK(cal_clk_i), .R(
        n215), .Q(blocked_medium_q[8]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[7]  ( .D(n148), .CK(cal_clk_i), .R(
        n215), .Q(blocked_medium_q[7]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[6]  ( .D(n147), .CK(cal_clk_i), .R(
        n215), .Q(blocked_medium_q[6]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[5]  ( .D(n146), .CK(cal_clk_i), .R(
        n215), .Q(blocked_medium_q[5]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[4]  ( .D(n145), .CK(cal_clk_i), .R(
        n215), .Q(blocked_medium_q[4]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[3]  ( .D(n144), .CK(cal_clk_i), .R(
        n215), .Q(blocked_medium_q[3]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[2]  ( .D(n143), .CK(cal_clk_i), .R(
        n215), .Q(blocked_medium_q[2]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[1]  ( .D(n142), .CK(cal_clk_i), .R(
        n215), .Q(blocked_medium_q[1]) );
  DFFRPQ_X1M_A9TR40 \blocked_medium_q_reg[0]  ( .D(n141), .CK(cal_clk_i), .R(
        n215), .Q(blocked_medium_q[0]) );
  DFFRPQ_X1M_A9TR40 protocol_error_q_reg ( .D(n168), .CK(cal_clk_i), .R(n214),
        .Q(handoff_protocol_error_o) );
  DFFRPQ_X1M_A9TR40 \fine_code_snapshot_q_reg[3]  ( .D(n177), .CK(cal_clk_i),
        .R(n213), .Q(cal_fine_code_snapshot_o[3]) );
  DFFRPQ_X1M_A9TR40 \fine_code_snapshot_q_reg[2]  ( .D(n176), .CK(cal_clk_i),
        .R(n213), .Q(cal_fine_code_snapshot_o[2]) );
  DFFRPQ_X1M_A9TR40 \fine_code_snapshot_q_reg[1]  ( .D(n175), .CK(cal_clk_i),
        .R(n213), .Q(cal_fine_code_snapshot_o[1]) );
  DFFRPQ_X1M_A9TR40 \fine_code_snapshot_q_reg[0]  ( .D(n174), .CK(cal_clk_i),
        .R(n213), .Q(cal_fine_code_snapshot_o[0]) );
  DFFRPQ_X1M_A9TR40 \medium_code_snapshot_q_reg[4]  ( .D(n173), .CK(cal_clk_i),
        .R(n213), .Q(cal_medium_code_snapshot_o[4]) );
  DFFRPQ_X1M_A9TR40 \medium_code_snapshot_q_reg[3]  ( .D(n172), .CK(cal_clk_i),
        .R(n213), .Q(cal_medium_code_snapshot_o[3]) );
  DFFRPQ_X1M_A9TR40 \medium_code_snapshot_q_reg[2]  ( .D(n171), .CK(cal_clk_i),
        .R(n213), .Q(cal_medium_code_snapshot_o[2]) );
  DFFRPQ_X1M_A9TR40 \medium_code_snapshot_q_reg[1]  ( .D(n170), .CK(cal_clk_i),
        .R(n213), .Q(cal_medium_code_snapshot_o[1]) );
  DFFRPQ_X1M_A9TR40 \medium_code_snapshot_q_reg[0]  ( .D(n169), .CK(cal_clk_i),
        .R(n213), .Q(cal_medium_code_snapshot_o[0]) );
  DFFRPQ_X1M_A9TR40 sensor_det_enable_q_reg ( .D(sensor_det_enable_d), .CK(
        cal_clk_i), .R(n213), .Q(sensor_det_enable_q) );
  DFFSQ_X1M_A9TR40 sensor_cal_enable_q_reg ( .D(sensor_cal_enable_d), .CK(
        cal_clk_i), .SN(ctrl_por_n_i), .Q(sensor_cal_enable_q) );
  DFFRPQ_X1M_A9TR40 sensor_safe_enable_q_reg ( .D(sensor_safe_enable_d), .CK(
        cal_clk_i), .R(n213), .Q(sensor_safe_enable_q) );
  DFFRPQ_X1M_A9TR40 sensor_blocked_enable_q_reg ( .D(state_d[2]), .CK(
        cal_clk_i), .R(n213), .Q(sensor_blocked_enable_q) );
  DFFRPQ_X1M_A9TR40 cal_cfg_valid_q_reg ( .D(n203), .CK(cal_clk_i), .R(n211),
        .Q(cal_cfg_valid_o) );
  DFFRPQ_X1M_A9TR40 blocked_hold_valid_q_reg ( .D(n167), .CK(cal_clk_i), .R(
        n214), .Q(blocked_hold_valid_q) );
  DFFRPQ_X1M_A9TR40 \fine_snapshot_q_reg[3]  ( .D(n196), .CK(cal_clk_i), .R(
        n211), .Q(cal_fine_therm_snapshot_o[3]) );
  DFFRPQ_X1M_A9TR40 \fine_snapshot_q_reg[2]  ( .D(n195), .CK(cal_clk_i), .R(
        n211), .Q(cal_fine_therm_snapshot_o[2]) );
  DFFRPQ_X1M_A9TR40 \fine_snapshot_q_reg[9]  ( .D(n202), .CK(cal_clk_i), .R(
        n211), .Q(cal_fine_therm_snapshot_o[9]) );
  DFFRPQ_X1M_A9TR40 \fine_snapshot_q_reg[8]  ( .D(n201), .CK(cal_clk_i), .R(
        n211), .Q(cal_fine_therm_snapshot_o[8]) );
  DFFRPQ_X1M_A9TR40 \fine_snapshot_q_reg[7]  ( .D(n200), .CK(cal_clk_i), .R(
        n211), .Q(cal_fine_therm_snapshot_o[7]) );
  DFFRPQ_X1M_A9TR40 \fine_snapshot_q_reg[1]  ( .D(n194), .CK(cal_clk_i), .R(
        n211), .Q(cal_fine_therm_snapshot_o[1]) );
  DFFRPQ_X1M_A9TR40 \fine_snapshot_q_reg[6]  ( .D(n199), .CK(cal_clk_i), .R(
        n211), .Q(cal_fine_therm_snapshot_o[6]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[2]  ( .D(n180), .CK(cal_clk_i), .R(
        n212), .Q(cal_medium_therm_snapshot_o[2]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[6]  ( .D(n184), .CK(cal_clk_i), .R(
        n212), .Q(cal_medium_therm_snapshot_o[6]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[15]  ( .D(n193), .CK(cal_clk_i),
        .R(n212), .Q(cal_medium_therm_snapshot_o[15]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[5]  ( .D(n183), .CK(cal_clk_i), .R(
        n212), .Q(cal_medium_therm_snapshot_o[5]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[4]  ( .D(n182), .CK(cal_clk_i), .R(
        n212), .Q(cal_medium_therm_snapshot_o[4]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[3]  ( .D(n181), .CK(cal_clk_i), .R(
        n212), .Q(cal_medium_therm_snapshot_o[3]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[14]  ( .D(n192), .CK(cal_clk_i),
        .R(n212), .Q(cal_medium_therm_snapshot_o[14]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[10]  ( .D(n188), .CK(cal_clk_i),
        .R(n212), .Q(cal_medium_therm_snapshot_o[10]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[1]  ( .D(n179), .CK(cal_clk_i), .R(
        n213), .Q(cal_medium_therm_snapshot_o[1]) );
  DFFRPQ_X1M_A9TR40 \fine_snapshot_q_reg[4]  ( .D(n197), .CK(cal_clk_i), .R(
        n211), .Q(cal_fine_therm_snapshot_o[4]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[13]  ( .D(n191), .CK(cal_clk_i),
        .R(n212), .Q(cal_medium_therm_snapshot_o[13]) );
  DFFRPQ_X1M_A9TR40 \fine_snapshot_q_reg[5]  ( .D(n198), .CK(cal_clk_i), .R(
        n211), .Q(cal_fine_therm_snapshot_o[5]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[9]  ( .D(n187), .CK(cal_clk_i), .R(
        n212), .Q(cal_medium_therm_snapshot_o[9]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[12]  ( .D(n190), .CK(cal_clk_i),
        .R(n212), .Q(cal_medium_therm_snapshot_o[12]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[8]  ( .D(n186), .CK(cal_clk_i), .R(
        n212), .Q(cal_medium_therm_snapshot_o[8]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[11]  ( .D(n189), .CK(cal_clk_i),
        .R(n212), .Q(cal_medium_therm_snapshot_o[11]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[7]  ( .D(n185), .CK(cal_clk_i), .R(
        n212), .Q(cal_medium_therm_snapshot_o[7]) );
  DFFRPQ_X1M_A9TR40 \fine_snapshot_q_reg[0]  ( .D(n204), .CK(cal_clk_i), .R(
        n211), .Q(cal_fine_therm_snapshot_o[0]) );
  DFFRPQ_X1M_A9TR40 \medium_snapshot_q_reg[0]  ( .D(n178), .CK(cal_clk_i), .R(
        n213), .Q(cal_medium_therm_snapshot_o[0]) );
  DFFRPQ_X1M_A9TR40 \state_q_reg[1]  ( .D(state_d[1]), .CK(cal_clk_i), .R(n211), .Q(handoff_state_o[1]) );
  DFFRPQ_X1M_A9TR40 \state_q_reg[2]  ( .D(state_d[2]), .CK(cal_clk_i), .R(n211), .Q(handoff_state_o[2]) );
  DFFRPQ_X1M_A9TR40 \state_q_reg[0]  ( .D(n297), .CK(cal_clk_i), .R(n211), .Q(
        handoff_state_o[0]) );
  NOR2_X2A_A9TR40 U243 ( .A(n111), .B(n112), .Y(n25) );
  NOR4BB_X1M_A9TR40 U244 ( .AN(n276), .BN(n275), .C(n274), .D(n273), .Y(N22)
         );
  NOR4BB_X1M_A9TR40 U245 ( .AN(n293), .BN(n292), .C(n291), .D(n290), .Y(N23)
         );
  BUF_X2M_A9TR40 U246 ( .A(n27), .Y(n224) );
  BUF_X2M_A9TR40 U247 ( .A(n29), .Y(n223) );
  BUF_X2M_A9TR40 U248 ( .A(n29), .Y(n222) );
  BUFH_X1M_A9TR40 U249 ( .A(n296), .Y(n209) );
  BUFH_X1M_A9TR40 U250 ( .A(n296), .Y(n208) );
  AOI21B_X1M_A9TR40 U251 ( .A0(n108), .A1(cal_fail_i), .B0N(n19), .Y(n27) );
  AOI21_X1M_A9TR40 U252 ( .A0(n15), .A1(n331), .B0(handoff_state_o[2]), .Y(
        state_d[1]) );
  OAI211_X1M_A9TR40 U253 ( .A0(handoff_state_o[1]), .A1(n300), .B0(n19), .C0(
        n330), .Y(state_d[2]) );
  NOR3_X2A_A9TR40 U254 ( .A(handoff_state_o[1]), .B(handoff_state_o[2]), .C(
        n332), .Y(n108) );
  INV_X1M_A9TR40 U255 ( .A(cal_fail_i), .Y(n300) );
  AOI31_X1M_A9TR40 U256 ( .A0(sensor_blocked_enable_q), .A1(n358), .A2(
        cal_cfg_valid_o), .B0(sensor_safe_enable_q), .Y(n113) );
  AO21A1AI2_X1M_A9TR40 U257 ( .A0(n7), .A1(n300), .B0(handoff_state_o[1]),
        .C0(n330), .Y(n6) );
  BUF_X2M_A9TR40 U258 ( .A(sensor_cal_enable_q), .Y(n254) );
  BUF_X2M_A9TR40 U259 ( .A(sensor_cal_enable_q), .Y(n253) );
  BUF_X2M_A9TR40 U260 ( .A(sensor_det_enable_q), .Y(n251) );
  BUF_X2M_A9TR40 U261 ( .A(sensor_det_enable_q), .Y(n252) );
  INV_X1M_A9TR40 U262 ( .A(cal_medium_therm_snapshot_o[0]), .Y(n356) );
  INV_X1M_A9TR40 U263 ( .A(cal_fine_therm_snapshot_o[0]), .Y(n329) );
  INV_X1M_A9TR40 U264 ( .A(cal_fine_therm_snapshot_o[4]), .Y(n339) );
  INV_X1M_A9TR40 U265 ( .A(cal_fine_therm_snapshot_o[5]), .Y(n338) );
  INV_X1M_A9TR40 U266 ( .A(cal_medium_therm_snapshot_o[2]), .Y(n355) );
  INV_X1M_A9TR40 U267 ( .A(cal_medium_therm_snapshot_o[3]), .Y(n354) );
  INV_X1M_A9TR40 U268 ( .A(cal_medium_therm_snapshot_o[4]), .Y(n353) );
  INV_X1M_A9TR40 U269 ( .A(cal_medium_therm_snapshot_o[5]), .Y(n352) );
  INV_X1M_A9TR40 U270 ( .A(cal_medium_therm_snapshot_o[6]), .Y(n351) );
  INV_X1M_A9TR40 U271 ( .A(cal_medium_therm_snapshot_o[7]), .Y(n350) );
  INV_X1M_A9TR40 U272 ( .A(cal_medium_therm_snapshot_o[8]), .Y(n349) );
  INV_X1M_A9TR40 U273 ( .A(cal_medium_therm_snapshot_o[9]), .Y(n348) );
  INV_X1M_A9TR40 U274 ( .A(cal_medium_therm_snapshot_o[10]), .Y(n347) );
  INV_X1M_A9TR40 U275 ( .A(cal_medium_therm_snapshot_o[11]), .Y(n346) );
  INV_X1M_A9TR40 U276 ( .A(cal_medium_therm_snapshot_o[12]), .Y(n345) );
  INV_X1M_A9TR40 U277 ( .A(cal_medium_therm_snapshot_o[13]), .Y(n344) );
  INV_X1M_A9TR40 U278 ( .A(cal_medium_therm_snapshot_o[14]), .Y(n343) );
  INV_X1M_A9TR40 U279 ( .A(cal_medium_therm_snapshot_o[15]), .Y(n342) );
  INV_X1M_A9TR40 U280 ( .A(cal_fine_therm_snapshot_o[2]), .Y(n341) );
  INV_X1M_A9TR40 U281 ( .A(cal_fine_therm_snapshot_o[3]), .Y(n340) );
  INV_X1M_A9TR40 U282 ( .A(cal_fine_therm_snapshot_o[6]), .Y(n337) );
  INV_X1M_A9TR40 U283 ( .A(cal_fine_therm_snapshot_o[7]), .Y(n336) );
  INV_X1M_A9TR40 U284 ( .A(cal_fine_therm_snapshot_o[8]), .Y(n335) );
  INV_X1M_A9TR40 U285 ( .A(cal_fine_therm_snapshot_o[9]), .Y(n334) );
  BUF_X2M_A9TR40 U286 ( .A(n31), .Y(n220) );
  BUF_X2M_A9TR40 U287 ( .A(n31), .Y(n221) );
  NAND2_X1A_A9TR40 U288 ( .A(n225), .B(n223), .Y(n31) );
  INV_X2M_A9TR40 U289 ( .A(n250), .Y(n227) );
  INV_X2M_A9TR40 U290 ( .A(n246), .Y(n226) );
  BUFH_X1M_A9TR40 U291 ( .A(n245), .Y(n244) );
  BUFH_X1M_A9TR40 U292 ( .A(n245), .Y(n243) );
  BUFH_X1M_A9TR40 U293 ( .A(n245), .Y(n242) );
  BUFH_X1M_A9TR40 U294 ( .A(n246), .Y(n241) );
  BUFH_X1M_A9TR40 U295 ( .A(n246), .Y(n240) );
  BUFH_X1M_A9TR40 U296 ( .A(n247), .Y(n238) );
  BUFH_X1M_A9TR40 U297 ( .A(n247), .Y(n237) );
  BUFH_X1M_A9TR40 U298 ( .A(n247), .Y(n236) );
  BUFH_X1M_A9TR40 U299 ( .A(n248), .Y(n235) );
  BUFH_X1M_A9TR40 U300 ( .A(n248), .Y(n234) );
  BUFH_X1M_A9TR40 U301 ( .A(n248), .Y(n233) );
  BUFH_X1M_A9TR40 U302 ( .A(n249), .Y(n232) );
  BUFH_X1M_A9TR40 U303 ( .A(n249), .Y(n231) );
  BUFH_X1M_A9TR40 U304 ( .A(n249), .Y(n230) );
  BUFH_X1M_A9TR40 U305 ( .A(n246), .Y(n239) );
  BUFH_X1M_A9TR40 U306 ( .A(n250), .Y(n229) );
  BUF_X3M_A9TR40 U307 ( .A(n209), .Y(n214) );
  BUF_X3M_A9TR40 U308 ( .A(n209), .Y(n213) );
  BUF_X3M_A9TR40 U309 ( .A(n208), .Y(n212) );
  BUF_X3M_A9TR40 U310 ( .A(n208), .Y(n211) );
  OAI222_X1M_A9TR40 U311 ( .A0(n224), .A1(n356), .B0(n222), .B1(n317), .C0(
        n220), .C1(n384), .Y(n141) );
  OAI222_X1M_A9TR40 U312 ( .A0(n224), .A1(n277), .B0(n223), .B1(n316), .C0(
        n220), .C1(n383), .Y(n142) );
  OAI222_X1M_A9TR40 U313 ( .A0(n224), .A1(n355), .B0(n223), .B1(n315), .C0(
        n220), .C1(n382), .Y(n143) );
  OAI222_X1M_A9TR40 U314 ( .A0(n224), .A1(n354), .B0(n223), .B1(n314), .C0(
        n220), .C1(n381), .Y(n144) );
  OAI222_X1M_A9TR40 U315 ( .A0(n224), .A1(n353), .B0(n223), .B1(n313), .C0(
        n220), .C1(n380), .Y(n145) );
  OAI222_X1M_A9TR40 U316 ( .A0(n224), .A1(n352), .B0(n223), .B1(n312), .C0(
        n220), .C1(n379), .Y(n146) );
  OAI222_X1M_A9TR40 U317 ( .A0(n224), .A1(n351), .B0(n223), .B1(n311), .C0(
        n220), .C1(n378), .Y(n147) );
  OAI222_X1M_A9TR40 U318 ( .A0(n224), .A1(n350), .B0(n223), .B1(n310), .C0(
        n220), .C1(n377), .Y(n148) );
  OAI222_X1M_A9TR40 U319 ( .A0(n224), .A1(n349), .B0(n223), .B1(n309), .C0(
        n220), .C1(n376), .Y(n149) );
  OAI222_X1M_A9TR40 U320 ( .A0(n224), .A1(n348), .B0(n223), .B1(n308), .C0(
        n220), .C1(n375), .Y(n150) );
  OAI222_X1M_A9TR40 U321 ( .A0(n224), .A1(n347), .B0(n223), .B1(n307), .C0(
        n220), .C1(n374), .Y(n151) );
  OAI222_X1M_A9TR40 U322 ( .A0(n224), .A1(n346), .B0(n223), .B1(n306), .C0(
        n220), .C1(n373), .Y(n152) );
  OAI222_X1M_A9TR40 U323 ( .A0(n224), .A1(n345), .B0(n223), .B1(n305), .C0(
        n220), .C1(n372), .Y(n153) );
  OAI222_X1M_A9TR40 U324 ( .A0(n224), .A1(n344), .B0(n222), .B1(n304), .C0(
        n220), .C1(n371), .Y(n154) );
  BUF_X2M_A9TR40 U325 ( .A(n27), .Y(n225) );
  OAI222_X1M_A9TR40 U326 ( .A0(n225), .A1(n343), .B0(n222), .B1(n303), .C0(
        n221), .C1(n370), .Y(n155) );
  OAI222_X1M_A9TR40 U327 ( .A0(n225), .A1(n342), .B0(n222), .B1(n302), .C0(
        n221), .C1(n369), .Y(n156) );
  OAI222_X1M_A9TR40 U328 ( .A0(n225), .A1(n329), .B0(n327), .B1(n222), .C0(
        n221), .C1(n368), .Y(n157) );
  OAI222_X1M_A9TR40 U329 ( .A0(n225), .A1(n341), .B0(n222), .B1(n325), .C0(
        n221), .C1(n366), .Y(n159) );
  OAI222_X1M_A9TR40 U330 ( .A0(n225), .A1(n340), .B0(n222), .B1(n324), .C0(
        n221), .C1(n365), .Y(n160) );
  OAI222_X1M_A9TR40 U331 ( .A0(n225), .A1(n339), .B0(n222), .B1(n323), .C0(
        n221), .C1(n364), .Y(n161) );
  OAI222_X1M_A9TR40 U332 ( .A0(n225), .A1(n338), .B0(n222), .B1(n322), .C0(
        n221), .C1(n363), .Y(n162) );
  OAI222_X1M_A9TR40 U333 ( .A0(n225), .A1(n337), .B0(n222), .B1(n321), .C0(
        n221), .C1(n362), .Y(n163) );
  OAI222_X1M_A9TR40 U334 ( .A0(n225), .A1(n336), .B0(n222), .B1(n320), .C0(
        n221), .C1(n361), .Y(n164) );
  OAI222_X1M_A9TR40 U335 ( .A0(n225), .A1(n335), .B0(n222), .B1(n319), .C0(
        n221), .C1(n360), .Y(n165) );
  OAI222_X1M_A9TR40 U336 ( .A0(n225), .A1(n334), .B0(n222), .B1(n318), .C0(
        n221), .C1(n359), .Y(n166) );
  OAI222_X1M_A9TR40 U337 ( .A0(n225), .A1(n294), .B0(n222), .B1(n326), .C0(
        n221), .C1(n367), .Y(n158) );
  NAND2B_X1M_A9TR40 U338 ( .AN(n221), .B(n358), .Y(n167) );
  INV_X1M_A9TR40 U339 ( .A(state_d[1]), .Y(n299) );
  NOR2_X1A_A9TR40 U340 ( .A(n6), .B(n299), .Y(sensor_det_enable_d) );
  NOR2_X1A_A9TR40 U341 ( .A(state_d[2]), .B(state_d[1]), .Y(
        sensor_cal_enable_d) );
  OAI22_X1M_A9TR40 U342 ( .A0(n227), .A1(n317), .B0(n241), .B1(n356), .Y(n178)
         );
  OAI22_X1M_A9TR40 U343 ( .A0(n227), .A1(n316), .B0(n241), .B1(n277), .Y(n179)
         );
  OAI22_X1M_A9TR40 U344 ( .A0(n227), .A1(n315), .B0(n240), .B1(n355), .Y(n180)
         );
  OAI22_X1M_A9TR40 U345 ( .A0(n227), .A1(n314), .B0(n240), .B1(n354), .Y(n181)
         );
  OAI22_X1M_A9TR40 U346 ( .A0(n227), .A1(n313), .B0(n239), .B1(n353), .Y(n182)
         );
  OAI22_X1M_A9TR40 U347 ( .A0(n227), .A1(n312), .B0(n237), .B1(n352), .Y(n183)
         );
  OAI22_X1M_A9TR40 U348 ( .A0(n227), .A1(n311), .B0(n238), .B1(n351), .Y(n184)
         );
  OAI22_X1M_A9TR40 U349 ( .A0(n227), .A1(n310), .B0(n238), .B1(n350), .Y(n185)
         );
  OAI22_X1M_A9TR40 U350 ( .A0(n227), .A1(n309), .B0(n237), .B1(n349), .Y(n186)
         );
  OAI22_X1M_A9TR40 U351 ( .A0(n227), .A1(n308), .B0(n236), .B1(n348), .Y(n187)
         );
  OAI22_X1M_A9TR40 U352 ( .A0(n227), .A1(n307), .B0(n236), .B1(n347), .Y(n188)
         );
  OAI22_X1M_A9TR40 U353 ( .A0(n227), .A1(n306), .B0(n235), .B1(n346), .Y(n189)
         );
  OAI22_X1M_A9TR40 U354 ( .A0(n227), .A1(n305), .B0(n235), .B1(n345), .Y(n190)
         );
  OAI22_X1M_A9TR40 U355 ( .A0(n226), .A1(n304), .B0(n234), .B1(n344), .Y(n191)
         );
  OAI22_X1M_A9TR40 U356 ( .A0(n226), .A1(n303), .B0(n234), .B1(n343), .Y(n192)
         );
  OAI22_X1M_A9TR40 U357 ( .A0(n226), .A1(n302), .B0(n233), .B1(n342), .Y(n193)
         );
  OAI22_X1M_A9TR40 U358 ( .A0(n226), .A1(n326), .B0(n233), .B1(n294), .Y(n194)
         );
  OAI22_X1M_A9TR40 U359 ( .A0(n226), .A1(n325), .B0(n232), .B1(n341), .Y(n195)
         );
  OAI22_X1M_A9TR40 U360 ( .A0(n226), .A1(n324), .B0(n232), .B1(n340), .Y(n196)
         );
  OAI22_X1M_A9TR40 U361 ( .A0(n226), .A1(n323), .B0(n231), .B1(n339), .Y(n197)
         );
  OAI22_X1M_A9TR40 U362 ( .A0(n226), .A1(n322), .B0(n231), .B1(n338), .Y(n198)
         );
  OAI22_X1M_A9TR40 U363 ( .A0(n226), .A1(n321), .B0(n230), .B1(n337), .Y(n199)
         );
  OAI22_X1M_A9TR40 U364 ( .A0(n226), .A1(n320), .B0(n230), .B1(n336), .Y(n200)
         );
  OAI22_X1M_A9TR40 U365 ( .A0(n226), .A1(n319), .B0(n229), .B1(n335), .Y(n201)
         );
  OAI22_X1M_A9TR40 U366 ( .A0(n226), .A1(n318), .B0(n239), .B1(n334), .Y(n202)
         );
  OAI22_X1M_A9TR40 U367 ( .A0(n226), .A1(n327), .B0(n229), .B1(n329), .Y(n204)
         );
  BUFH_X1M_A9TR40 U368 ( .A(n25), .Y(n250) );
  NOR2B_X1M_A9TR40 U369 ( .AN(n108), .B(n333), .Y(det_prepare_o) );
  BUFH_X1M_A9TR40 U370 ( .A(n25), .Y(n245) );
  INV_X2M_A9TR40 U371 ( .A(n248), .Y(n228) );
  NAND2_X1A_A9TR40 U372 ( .A(n333), .B(n228), .Y(n203) );
  BUFH_X1M_A9TR40 U373 ( .A(n25), .Y(n247) );
  BUFH_X1M_A9TR40 U374 ( .A(n25), .Y(n248) );
  BUFH_X1M_A9TR40 U375 ( .A(n25), .Y(n249) );
  BUFH_X1M_A9TR40 U376 ( .A(n25), .Y(n246) );
  BUF_X2M_A9TR40 U377 ( .A(n113), .Y(n218) );
  BUF_X2M_A9TR40 U378 ( .A(n113), .Y(n219) );
  BUF_X2M_A9TR40 U379 ( .A(n114), .Y(n216) );
  INV_X1M_A9TR40 U380 ( .A(n6), .Y(n297) );
  BUF_X2M_A9TR40 U381 ( .A(n114), .Y(n217) );
  BUF_X3M_A9TR40 U382 ( .A(n210), .Y(n215) );
  BUFH_X1M_A9TR40 U383 ( .A(n296), .Y(n210) );
  INV_X1M_A9TR40 U384 ( .A(cal_medium_therm_snapshot_o[1]), .Y(n277) );
  NAND3_X1M_A9TR40 U385 ( .A(n108), .B(n109), .C(det_takeover_ready_i), .Y(n19) );
  NAND4_X0P5M_A9TR40 U386 ( .A(det_sense_dff_reset_i), .B(N23), .C(N22), .D(
        n328), .Y(n109) );
  INV_X1M_A9TR40 U387 ( .A(cal_fine_therm_snapshot_o[1]), .Y(n294) );
  INV_X1M_A9TR40 U388 ( .A(det_medium_therm_i[1]), .Y(n278) );
  INV_X1M_A9TR40 U389 ( .A(det_fine_therm_i[1]), .Y(n295) );
  NAND4XXXB_X0P5M_A9TR40 U390 ( .DN(n17), .A(det_sense_dff_reset_i), .B(
        det_takeover_ready_i), .C(N23), .Y(n15) );
  NAND4_X0P5M_A9TR40 U391 ( .A(N22), .B(handoff_state_o[0]), .C(n300), .D(n328), .Y(n17) );
  AOI21_X1M_A9TR40 U392 ( .A0(n297), .A1(handoff_state_o[0]), .B0(n299), .Y(
        sensor_safe_enable_d) );
  OAI21B_X1M_A9TR40 U393 ( .A0(n19), .A1(cal_fail_i), .B0N(
        handoff_protocol_error_o), .Y(n168) );
  NAND4_X1A_A9TR40 U394 ( .A(n107), .B(lock_valid_i), .C(cal_sense_dff_reset_i), .D(cal_done_i), .Y(n112) );
  NAND4_X1A_A9TR40 U395 ( .A(n298), .B(n333), .C(n300), .D(n301), .Y(n111) );
  INV_X1M_A9TR40 U396 ( .A(handoff_state_o[0]), .Y(n332) );
  AO22_X1M_A9TR40 U397 ( .A0(cal_medium_code_i[0]), .A1(n244), .B0(
        cal_medium_code_snapshot_o[0]), .B1(n228), .Y(n169) );
  AO22_X1M_A9TR40 U398 ( .A0(cal_medium_code_i[1]), .A1(n244), .B0(
        cal_medium_code_snapshot_o[1]), .B1(n228), .Y(n170) );
  AO22_X1M_A9TR40 U399 ( .A0(cal_medium_code_i[2]), .A1(n244), .B0(
        cal_medium_code_snapshot_o[2]), .B1(n228), .Y(n171) );
  AO22_X1M_A9TR40 U400 ( .A0(cal_medium_code_i[3]), .A1(n243), .B0(
        cal_medium_code_snapshot_o[3]), .B1(n228), .Y(n172) );
  AO22_X1M_A9TR40 U401 ( .A0(cal_medium_code_i[4]), .A1(n243), .B0(
        cal_medium_code_snapshot_o[4]), .B1(n228), .Y(n173) );
  AO22_X1M_A9TR40 U402 ( .A0(cal_fine_code_i[0]), .A1(n243), .B0(
        cal_fine_code_snapshot_o[0]), .B1(n228), .Y(n174) );
  AO22_X1M_A9TR40 U403 ( .A0(cal_fine_code_i[1]), .A1(n242), .B0(
        cal_fine_code_snapshot_o[1]), .B1(n228), .Y(n175) );
  AO22_X1M_A9TR40 U404 ( .A0(cal_fine_code_i[2]), .A1(n242), .B0(
        cal_fine_code_snapshot_o[2]), .B1(n228), .Y(n176) );
  AO22_X1M_A9TR40 U405 ( .A0(cal_fine_code_i[3]), .A1(n242), .B0(
        cal_fine_code_snapshot_o[3]), .B1(n228), .Y(n177) );
  INV_X1M_A9TR40 U406 ( .A(cal_busy_i), .Y(n298) );
  OAI221_X1M_A9TR40 U407 ( .A0(n218), .A1(n277), .B0(n383), .B1(n216), .C0(
        n123), .Y(medium_therm_o[1]) );
  AOI22_X1M_A9TR40 U408 ( .A0(cal_medium_therm_i[1]), .A1(n253), .B0(
        det_medium_therm_i[1]), .B1(n251), .Y(n123) );
  OAI221_X1M_A9TR40 U409 ( .A0(n218), .A1(n355), .B0(n382), .B1(n216), .C0(
        n122), .Y(medium_therm_o[2]) );
  AOI22_X1M_A9TR40 U410 ( .A0(cal_medium_therm_i[2]), .A1(n253), .B0(
        det_medium_therm_i[2]), .B1(n251), .Y(n122) );
  OAI221_X1M_A9TR40 U411 ( .A0(n218), .A1(n354), .B0(n381), .B1(n216), .C0(
        n121), .Y(medium_therm_o[3]) );
  AOI22_X1M_A9TR40 U412 ( .A0(cal_medium_therm_i[3]), .A1(n253), .B0(
        det_medium_therm_i[3]), .B1(n251), .Y(n121) );
  OAI221_X1M_A9TR40 U413 ( .A0(n218), .A1(n353), .B0(n380), .B1(n216), .C0(
        n120), .Y(medium_therm_o[4]) );
  AOI22_X1M_A9TR40 U414 ( .A0(cal_medium_therm_i[4]), .A1(n253), .B0(
        det_medium_therm_i[4]), .B1(n251), .Y(n120) );
  OAI221_X1M_A9TR40 U415 ( .A0(n218), .A1(n352), .B0(n379), .B1(n216), .C0(
        n119), .Y(medium_therm_o[5]) );
  AOI22_X1M_A9TR40 U416 ( .A0(cal_medium_therm_i[5]), .A1(n253), .B0(
        det_medium_therm_i[5]), .B1(n251), .Y(n119) );
  OAI221_X1M_A9TR40 U417 ( .A0(n218), .A1(n351), .B0(n378), .B1(n216), .C0(
        n118), .Y(medium_therm_o[6]) );
  AOI22_X1M_A9TR40 U418 ( .A0(cal_medium_therm_i[6]), .A1(n253), .B0(
        det_medium_therm_i[6]), .B1(n251), .Y(n118) );
  OAI221_X1M_A9TR40 U419 ( .A0(n218), .A1(n350), .B0(n377), .B1(n216), .C0(
        n117), .Y(medium_therm_o[7]) );
  AOI22_X1M_A9TR40 U420 ( .A0(cal_medium_therm_i[7]), .A1(n253), .B0(
        det_medium_therm_i[7]), .B1(n251), .Y(n117) );
  OAI221_X1M_A9TR40 U421 ( .A0(n218), .A1(n349), .B0(n376), .B1(n216), .C0(
        n116), .Y(medium_therm_o[8]) );
  AOI22_X1M_A9TR40 U422 ( .A0(cal_medium_therm_i[8]), .A1(n253), .B0(
        det_medium_therm_i[8]), .B1(n251), .Y(n116) );
  OAI221_X1M_A9TR40 U423 ( .A0(n218), .A1(n348), .B0(n375), .B1(n216), .C0(
        n115), .Y(medium_therm_o[9]) );
  AOI22_X1M_A9TR40 U424 ( .A0(cal_medium_therm_i[9]), .A1(n253), .B0(
        det_medium_therm_i[9]), .B1(n251), .Y(n115) );
  OAI221_X1M_A9TR40 U425 ( .A0(n218), .A1(n346), .B0(n373), .B1(n216), .C0(
        n128), .Y(medium_therm_o[11]) );
  AOI22_X1M_A9TR40 U426 ( .A0(cal_medium_therm_i[11]), .A1(n253), .B0(
        det_medium_therm_i[11]), .B1(n251), .Y(n128) );
  OAI221_X1M_A9TR40 U427 ( .A0(n218), .A1(n345), .B0(n372), .B1(n216), .C0(
        n127), .Y(medium_therm_o[12]) );
  AOI22_X1M_A9TR40 U428 ( .A0(cal_medium_therm_i[12]), .A1(n253), .B0(
        det_medium_therm_i[12]), .B1(n251), .Y(n127) );
  OAI221_X1M_A9TR40 U429 ( .A0(n218), .A1(n344), .B0(n371), .B1(n216), .C0(
        n126), .Y(medium_therm_o[13]) );
  AOI22_X1M_A9TR40 U430 ( .A0(cal_medium_therm_i[13]), .A1(n253), .B0(
        det_medium_therm_i[13]), .B1(n251), .Y(n126) );
  OAI221_X1M_A9TR40 U431 ( .A0(n218), .A1(n343), .B0(n370), .B1(n216), .C0(
        n125), .Y(medium_therm_o[14]) );
  AOI22_X1M_A9TR40 U432 ( .A0(cal_medium_therm_i[14]), .A1(n253), .B0(
        det_medium_therm_i[14]), .B1(n251), .Y(n125) );
  OAI221_X1M_A9TR40 U433 ( .A0(n218), .A1(n342), .B0(n369), .B1(n216), .C0(
        n124), .Y(medium_therm_o[15]) );
  AOI22_X1M_A9TR40 U434 ( .A0(cal_medium_therm_i[15]), .A1(n253), .B0(
        det_medium_therm_i[15]), .B1(n251), .Y(n124) );
  INV_X1M_A9TR40 U435 ( .A(blocked_hold_valid_q), .Y(n358) );
  OAI221_X1M_A9TR40 U436 ( .A0(n219), .A1(n294), .B0(n367), .B1(n217), .C0(
        n139), .Y(fine_therm_o[1]) );
  AOI22_X1M_A9TR40 U437 ( .A0(cal_fine_therm_i[1]), .A1(n254), .B0(
        det_fine_therm_i[1]), .B1(n252), .Y(n139) );
  OAI221_X1M_A9TR40 U438 ( .A0(n219), .A1(n329), .B0(n368), .B1(n217), .C0(
        n140), .Y(fine_therm_o[0]) );
  AOI22_X1M_A9TR40 U439 ( .A0(cal_fine_therm_i[0]), .A1(n254), .B0(
        det_fine_therm_i[0]), .B1(n252), .Y(n140) );
  OAI221_X1M_A9TR40 U440 ( .A0(n219), .A1(n356), .B0(n384), .B1(n217), .C0(
        n130), .Y(medium_therm_o[0]) );
  AOI22_X1M_A9TR40 U441 ( .A0(cal_medium_therm_i[0]), .A1(n254), .B0(
        det_medium_therm_i[0]), .B1(n252), .Y(n130) );
  OAI221_X1M_A9TR40 U442 ( .A0(n219), .A1(n341), .B0(n366), .B1(n217), .C0(
        n138), .Y(fine_therm_o[2]) );
  AOI22_X1M_A9TR40 U443 ( .A0(cal_fine_therm_i[2]), .A1(n254), .B0(
        det_fine_therm_i[2]), .B1(n252), .Y(n138) );
  OAI221_X1M_A9TR40 U444 ( .A0(n219), .A1(n340), .B0(n365), .B1(n217), .C0(
        n137), .Y(fine_therm_o[3]) );
  AOI22_X1M_A9TR40 U445 ( .A0(cal_fine_therm_i[3]), .A1(n254), .B0(
        det_fine_therm_i[3]), .B1(n252), .Y(n137) );
  OAI221_X1M_A9TR40 U446 ( .A0(n219), .A1(n339), .B0(n364), .B1(n217), .C0(
        n136), .Y(fine_therm_o[4]) );
  AOI22_X1M_A9TR40 U447 ( .A0(cal_fine_therm_i[4]), .A1(n254), .B0(
        det_fine_therm_i[4]), .B1(n252), .Y(n136) );
  OAI221_X1M_A9TR40 U448 ( .A0(n219), .A1(n338), .B0(n363), .B1(n217), .C0(
        n135), .Y(fine_therm_o[5]) );
  AOI22_X1M_A9TR40 U449 ( .A0(cal_fine_therm_i[5]), .A1(n254), .B0(
        det_fine_therm_i[5]), .B1(n252), .Y(n135) );
  OAI221_X1M_A9TR40 U450 ( .A0(n219), .A1(n337), .B0(n362), .B1(n217), .C0(
        n134), .Y(fine_therm_o[6]) );
  AOI22_X1M_A9TR40 U451 ( .A0(cal_fine_therm_i[6]), .A1(n254), .B0(
        det_fine_therm_i[6]), .B1(n252), .Y(n134) );
  OAI221_X1M_A9TR40 U452 ( .A0(n219), .A1(n336), .B0(n361), .B1(n217), .C0(
        n133), .Y(fine_therm_o[7]) );
  AOI22_X1M_A9TR40 U453 ( .A0(cal_fine_therm_i[7]), .A1(n254), .B0(
        det_fine_therm_i[7]), .B1(n252), .Y(n133) );
  OAI221_X1M_A9TR40 U454 ( .A0(n219), .A1(n335), .B0(n360), .B1(n217), .C0(
        n132), .Y(fine_therm_o[8]) );
  AOI22_X1M_A9TR40 U455 ( .A0(cal_fine_therm_i[8]), .A1(n254), .B0(
        det_fine_therm_i[8]), .B1(n252), .Y(n132) );
  OAI221_X1M_A9TR40 U456 ( .A0(n219), .A1(n334), .B0(n359), .B1(n217), .C0(
        n131), .Y(fine_therm_o[9]) );
  AOI22_X1M_A9TR40 U457 ( .A0(cal_fine_therm_i[9]), .A1(n254), .B0(
        det_fine_therm_i[9]), .B1(n252), .Y(n131) );
  OAI221_X1M_A9TR40 U458 ( .A0(n219), .A1(n347), .B0(n374), .B1(n217), .C0(
        n129), .Y(medium_therm_o[10]) );
  AOI22_X1M_A9TR40 U459 ( .A0(cal_medium_therm_i[10]), .A1(n254), .B0(
        det_medium_therm_i[10]), .B1(n252), .Y(n129) );
  NAND2_X1A_A9TR40 U460 ( .A(n107), .B(cal_fail_i), .Y(n29) );
  INV_X1M_A9TR40 U461 ( .A(det_sense_s_clk_i), .Y(n328) );
  NOR3_X1A_A9TR40 U462 ( .A(n331), .B(handoff_state_o[2]), .C(n332), .Y(
        det_owner_valid_o) );
  INV_X1M_A9TR40 U463 ( .A(handoff_state_o[1]), .Y(n331) );
  NOR3_X2A_A9TR40 U464 ( .A(handoff_state_o[1]), .B(handoff_state_o[2]), .C(
        handoff_state_o[0]), .Y(n107) );
  NAND2_X1A_A9TR40 U465 ( .A(blocked_hold_valid_q), .B(sensor_blocked_enable_q), .Y(n114) );
  OAI22_X1M_A9TR40 U466 ( .A0(det_takeover_ready_i), .A1(n332), .B0(n11), .B1(
        n12), .Y(n7) );
  NAND3_X1M_A9TR40 U467 ( .A(cal_sense_dff_reset_i), .B(cal_done_i), .C(
        lock_valid_i), .Y(n12) );
  NAND3_X1M_A9TR40 U468 ( .A(n301), .B(n332), .C(n298), .Y(n11) );
  INV_X1M_A9TR40 U469 ( .A(handoff_state_o[2]), .Y(n330) );
  NOR3_X1A_A9TR40 U470 ( .A(n330), .B(handoff_state_o[1]), .C(
        handoff_state_o[0]), .Y(handoff_blocked_o) );
  INV_X1M_A9TR40 U471 ( .A(cal_cfg_valid_o), .Y(n333) );
  INV_X1M_A9TR40 U472 ( .A(cal_sense_s_clk_i), .Y(n301) );
  NAND3XXB_X1M_A9TR40 U473 ( .CN(sensor_blocked_enable_q), .A(n357), .B(n22),
        .Y(sense_dff_reset_o) );
  AOI22_X1M_A9TR40 U474 ( .A0(n253), .A1(cal_sense_dff_reset_i), .B0(n251),
        .B1(det_sense_dff_reset_i), .Y(n22) );
  NOR2_X1A_A9TR40 U475 ( .A(sensor_blocked_enable_q), .B(n20), .Y(
        sense_s_clk_o) );
  AOI32_X1M_A9TR40 U476 ( .A0(cal_sense_s_clk_i), .A1(n357), .A2(n253), .B0(
        n251), .B1(det_sense_s_clk_i), .Y(n20) );
  INV_X1M_A9TR40 U477 ( .A(sensor_safe_enable_q), .Y(n357) );
  INV_X1M_A9TR40 U478 ( .A(blocked_medium_q[0]), .Y(n384) );
  INV_X1M_A9TR40 U479 ( .A(blocked_medium_q[1]), .Y(n383) );
  INV_X1M_A9TR40 U480 ( .A(blocked_medium_q[2]), .Y(n382) );
  INV_X1M_A9TR40 U481 ( .A(blocked_medium_q[3]), .Y(n381) );
  INV_X1M_A9TR40 U482 ( .A(blocked_medium_q[4]), .Y(n380) );
  INV_X1M_A9TR40 U483 ( .A(blocked_medium_q[5]), .Y(n379) );
  INV_X1M_A9TR40 U484 ( .A(blocked_medium_q[6]), .Y(n378) );
  INV_X1M_A9TR40 U485 ( .A(blocked_medium_q[7]), .Y(n377) );
  INV_X1M_A9TR40 U486 ( .A(blocked_medium_q[8]), .Y(n376) );
  INV_X1M_A9TR40 U487 ( .A(blocked_medium_q[9]), .Y(n375) );
  INV_X1M_A9TR40 U488 ( .A(blocked_medium_q[10]), .Y(n374) );
  INV_X1M_A9TR40 U489 ( .A(blocked_medium_q[11]), .Y(n373) );
  INV_X1M_A9TR40 U490 ( .A(blocked_medium_q[12]), .Y(n372) );
  INV_X1M_A9TR40 U491 ( .A(blocked_medium_q[13]), .Y(n371) );
  INV_X1M_A9TR40 U492 ( .A(blocked_medium_q[14]), .Y(n370) );
  INV_X1M_A9TR40 U493 ( .A(blocked_medium_q[15]), .Y(n369) );
  INV_X1M_A9TR40 U494 ( .A(blocked_fine_q[0]), .Y(n368) );
  INV_X1M_A9TR40 U495 ( .A(blocked_fine_q[1]), .Y(n367) );
  INV_X1M_A9TR40 U496 ( .A(blocked_fine_q[2]), .Y(n366) );
  INV_X1M_A9TR40 U497 ( .A(blocked_fine_q[3]), .Y(n365) );
  INV_X1M_A9TR40 U498 ( .A(blocked_fine_q[4]), .Y(n364) );
  INV_X1M_A9TR40 U499 ( .A(blocked_fine_q[5]), .Y(n363) );
  INV_X1M_A9TR40 U500 ( .A(blocked_fine_q[6]), .Y(n362) );
  INV_X1M_A9TR40 U501 ( .A(blocked_fine_q[7]), .Y(n361) );
  INV_X1M_A9TR40 U502 ( .A(blocked_fine_q[8]), .Y(n360) );
  INV_X1M_A9TR40 U503 ( .A(blocked_fine_q[9]), .Y(n359) );
  INV_X1M_A9TR40 U504 ( .A(cal_medium_therm_i[0]), .Y(n317) );
  INV_X1M_A9TR40 U505 ( .A(cal_medium_therm_i[1]), .Y(n316) );
  INV_X1M_A9TR40 U506 ( .A(cal_medium_therm_i[2]), .Y(n315) );
  INV_X1M_A9TR40 U507 ( .A(cal_medium_therm_i[3]), .Y(n314) );
  INV_X1M_A9TR40 U508 ( .A(cal_medium_therm_i[4]), .Y(n313) );
  INV_X1M_A9TR40 U509 ( .A(cal_medium_therm_i[5]), .Y(n312) );
  INV_X1M_A9TR40 U510 ( .A(cal_medium_therm_i[6]), .Y(n311) );
  INV_X1M_A9TR40 U511 ( .A(cal_medium_therm_i[7]), .Y(n310) );
  INV_X1M_A9TR40 U512 ( .A(cal_medium_therm_i[8]), .Y(n309) );
  INV_X1M_A9TR40 U513 ( .A(cal_medium_therm_i[9]), .Y(n308) );
  INV_X1M_A9TR40 U514 ( .A(cal_medium_therm_i[10]), .Y(n307) );
  INV_X1M_A9TR40 U515 ( .A(cal_medium_therm_i[11]), .Y(n306) );
  INV_X1M_A9TR40 U516 ( .A(cal_medium_therm_i[12]), .Y(n305) );
  INV_X1M_A9TR40 U517 ( .A(cal_medium_therm_i[13]), .Y(n304) );
  INV_X1M_A9TR40 U518 ( .A(cal_medium_therm_i[14]), .Y(n303) );
  INV_X1M_A9TR40 U519 ( .A(cal_medium_therm_i[15]), .Y(n302) );
  INV_X1M_A9TR40 U520 ( .A(cal_fine_therm_i[1]), .Y(n326) );
  INV_X1M_A9TR40 U521 ( .A(cal_fine_therm_i[2]), .Y(n325) );
  INV_X1M_A9TR40 U522 ( .A(cal_fine_therm_i[3]), .Y(n324) );
  INV_X1M_A9TR40 U523 ( .A(cal_fine_therm_i[4]), .Y(n323) );
  INV_X1M_A9TR40 U524 ( .A(cal_fine_therm_i[5]), .Y(n322) );
  INV_X1M_A9TR40 U525 ( .A(cal_fine_therm_i[6]), .Y(n321) );
  INV_X1M_A9TR40 U526 ( .A(cal_fine_therm_i[7]), .Y(n320) );
  INV_X1M_A9TR40 U527 ( .A(cal_fine_therm_i[8]), .Y(n319) );
  INV_X1M_A9TR40 U528 ( .A(cal_fine_therm_i[9]), .Y(n318) );
  INV_X1M_A9TR40 U529 ( .A(cal_fine_therm_i[0]), .Y(n327) );
  INV_X1M_A9TR40 U530 ( .A(ctrl_por_n_i), .Y(n296) );
  XNOR2_X0P5M_A9TR40 U531 ( .A(cal_medium_therm_snapshot_o[14]), .B(
        det_medium_therm_i[14]), .Y(n258) );
  XNOR2_X0P5M_A9TR40 U532 ( .A(cal_medium_therm_snapshot_o[13]), .B(
        det_medium_therm_i[13]), .Y(n257) );
  XNOR2_X0P5M_A9TR40 U533 ( .A(cal_medium_therm_snapshot_o[12]), .B(
        det_medium_therm_i[12]), .Y(n256) );
  XNOR2_X0P5M_A9TR40 U534 ( .A(cal_medium_therm_snapshot_o[11]), .B(
        det_medium_therm_i[11]), .Y(n255) );
  AND4_X0P5M_A9TR40 U535 ( .A(n258), .B(n257), .C(n256), .D(n255), .Y(n276) );
  XNOR2_X0P5M_A9TR40 U536 ( .A(cal_medium_therm_snapshot_o[10]), .B(
        det_medium_therm_i[10]), .Y(n262) );
  XNOR2_X0P5M_A9TR40 U537 ( .A(cal_medium_therm_snapshot_o[9]), .B(
        det_medium_therm_i[9]), .Y(n261) );
  XNOR2_X0P5M_A9TR40 U538 ( .A(cal_medium_therm_snapshot_o[8]), .B(
        det_medium_therm_i[8]), .Y(n260) );
  XNOR2_X0P5M_A9TR40 U539 ( .A(cal_medium_therm_snapshot_o[7]), .B(
        det_medium_therm_i[7]), .Y(n259) );
  AND4_X0P5M_A9TR40 U540 ( .A(n262), .B(n261), .C(n260), .D(n259), .Y(n275) );
  XNOR2_X0P5M_A9TR40 U541 ( .A(cal_medium_therm_snapshot_o[2]), .B(
        det_medium_therm_i[2]), .Y(n268) );
  XNOR2_X0P5M_A9TR40 U542 ( .A(cal_medium_therm_snapshot_o[15]), .B(
        det_medium_therm_i[15]), .Y(n267) );
  NOR2B_X0P5M_A9TR40 U543 ( .AN(det_medium_therm_i[0]), .B(
        cal_medium_therm_snapshot_o[0]), .Y(n263) );
  OAI22_X0P5M_A9TR40 U544 ( .A0(det_medium_therm_i[1]), .A1(n263), .B0(n263),
        .B1(n277), .Y(n266) );
  NOR2B_X0P5M_A9TR40 U545 ( .AN(cal_medium_therm_snapshot_o[0]), .B(
        det_medium_therm_i[0]), .Y(n264) );
  OAI22_X0P5M_A9TR40 U546 ( .A0(n264), .A1(n278), .B0(
        cal_medium_therm_snapshot_o[1]), .B1(n264), .Y(n265) );
  NAND4_X0P5A_A9TR40 U547 ( .A(n268), .B(n267), .C(n266), .D(n265), .Y(n274)
         );
  XNOR2_X0P5M_A9TR40 U548 ( .A(cal_medium_therm_snapshot_o[6]), .B(
        det_medium_therm_i[6]), .Y(n272) );
  XNOR2_X0P5M_A9TR40 U549 ( .A(cal_medium_therm_snapshot_o[5]), .B(
        det_medium_therm_i[5]), .Y(n271) );
  XNOR2_X0P5M_A9TR40 U550 ( .A(cal_medium_therm_snapshot_o[4]), .B(
        det_medium_therm_i[4]), .Y(n270) );
  XNOR2_X0P5M_A9TR40 U551 ( .A(cal_medium_therm_snapshot_o[3]), .B(
        det_medium_therm_i[3]), .Y(n269) );
  NAND4_X0P5A_A9TR40 U552 ( .A(n272), .B(n271), .C(n270), .D(n269), .Y(n273)
         );
  XNOR2_X0P5M_A9TR40 U553 ( .A(cal_fine_therm_snapshot_o[3]), .B(
        det_fine_therm_i[3]), .Y(n293) );
  XNOR2_X0P5M_A9TR40 U554 ( .A(cal_fine_therm_snapshot_o[2]), .B(
        det_fine_therm_i[2]), .Y(n292) );
  XNOR2_X0P5M_A9TR40 U555 ( .A(cal_fine_therm_snapshot_o[8]), .B(
        det_fine_therm_i[8]), .Y(n284) );
  XNOR2_X0P5M_A9TR40 U556 ( .A(cal_fine_therm_snapshot_o[7]), .B(
        det_fine_therm_i[7]), .Y(n283) );
  XOR2_X0P5M_A9TR40 U557 ( .A(cal_fine_therm_snapshot_o[4]), .B(
        det_fine_therm_i[4]), .Y(n280) );
  XOR2_X0P5M_A9TR40 U558 ( .A(cal_fine_therm_snapshot_o[5]), .B(
        det_fine_therm_i[5]), .Y(n279) );
  NOR2_X0P5A_A9TR40 U559 ( .A(n280), .B(n279), .Y(n282) );
  XNOR2_X0P5M_A9TR40 U560 ( .A(cal_fine_therm_snapshot_o[6]), .B(
        det_fine_therm_i[6]), .Y(n281) );
  NAND4_X0P5A_A9TR40 U561 ( .A(n284), .B(n283), .C(n282), .D(n281), .Y(n291)
         );
  NOR2B_X0P5M_A9TR40 U562 ( .AN(det_fine_therm_i[0]), .B(
        cal_fine_therm_snapshot_o[0]), .Y(n285) );
  OAI22_X0P5M_A9TR40 U563 ( .A0(det_fine_therm_i[1]), .A1(n285), .B0(n285),
        .B1(n294), .Y(n289) );
  NOR2B_X0P5M_A9TR40 U564 ( .AN(cal_fine_therm_snapshot_o[0]), .B(
        det_fine_therm_i[0]), .Y(n286) );
  OAI22_X0P5M_A9TR40 U565 ( .A0(n286), .A1(n295), .B0(
        cal_fine_therm_snapshot_o[1]), .B1(n286), .Y(n288) );
  XNOR2_X0P5M_A9TR40 U566 ( .A(cal_fine_therm_snapshot_o[9]), .B(
        det_fine_therm_i[9]), .Y(n287) );
  NAND3_X0P5A_A9TR40 U567 ( .A(n289), .B(n288), .C(n287), .Y(n290) );
endmodule
