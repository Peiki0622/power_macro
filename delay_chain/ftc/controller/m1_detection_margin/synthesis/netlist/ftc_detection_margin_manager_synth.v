/////////////////////////////////////////////////////////////
// Created by: Synopsys DC Expert(TM) in wire load mode
// Version   : W-2024.09
// Date      : Sun Aug 23 12:07:29 2026
/////////////////////////////////////////////////////////////


module ftc_detection_margin_mapper ( cal_medium_code_snapshot_i,
        cal_fine_code_snapshot_i, margin_sel_i, mapping_supported_o,
        trip_qualified_o, m_det_o, f_det_o, target_medium_therm_o,
        target_fine_therm_o );
  input [4:0] cal_medium_code_snapshot_i;
  input [3:0] cal_fine_code_snapshot_i;
  input [1:0] margin_sel_i;
  output [4:0] m_det_o;
  output [3:0] f_det_o;
  output [15:0] target_medium_therm_o;
  output [9:0] target_fine_therm_o;
  output mapping_supported_o, trip_qualified_o;
  wire   \*Logic0* , \m_det_o[3] , \target_medium_therm_o[6] ,
         mapping_supported_o, \target_fine_therm_o[7] ,
         \target_fine_therm_o[5] , n3, n4, n5, n6, n7, n8, n9, n10, n11, n12,
         n13, n14, n15, n16, n17, n18, n19, n20, n21, n22, n23, n24, n25, n26,
         n27, n28, n29, n30, n1, n2, n31, n32;
  assign target_medium_therm_o[8] = \*Logic0* ;
  assign target_medium_therm_o[9] = \*Logic0* ;
  assign target_medium_therm_o[10] = \*Logic0* ;
  assign target_medium_therm_o[11] = \*Logic0* ;
  assign target_medium_therm_o[12] = \*Logic0* ;
  assign target_medium_therm_o[13] = \*Logic0* ;
  assign target_medium_therm_o[14] = \*Logic0* ;
  assign target_medium_therm_o[15] = \*Logic0* ;
  assign m_det_o[4] = \*Logic0* ;
  assign target_medium_therm_o[7] = \m_det_o[3] ;
  assign m_det_o[3] = \m_det_o[3] ;
  assign target_medium_therm_o[5] = \target_medium_therm_o[6] ;
  assign target_medium_therm_o[6] = \target_medium_therm_o[6] ;
  assign target_medium_therm_o[0] = mapping_supported_o;
  assign target_medium_therm_o[1] = mapping_supported_o;
  assign target_fine_therm_o[6] = \target_fine_therm_o[7] ;
  assign target_fine_therm_o[7] = \target_fine_therm_o[7] ;
  assign target_fine_therm_o[0] = \target_fine_therm_o[5] ;
  assign target_fine_therm_o[1] = \target_fine_therm_o[5] ;
  assign target_fine_therm_o[2] = \target_fine_therm_o[5] ;
  assign target_fine_therm_o[3] = \target_fine_therm_o[5] ;
  assign target_fine_therm_o[4] = \target_fine_therm_o[5] ;
  assign target_fine_therm_o[5] = \target_fine_therm_o[5] ;

  NAND2_X2A_A9TR40 U3 ( .A(n15), .B(n4), .Y(target_medium_therm_o[2]) );
  INV_X2M_A9TR40 U4 ( .A(margin_sel_i[1]), .Y(n6) );
  INV_X1M_A9TR40 U5 ( .A(cal_medium_code_snapshot_i[2]), .Y(n31) );
  INV_X1M_A9TR40 U6 ( .A(cal_medium_code_snapshot_i[0]), .Y(n5) );
  NOR4BB_X1M_A9TR40 U7 ( .AN(cal_fine_code_snapshot_i[2]), .BN(
        cal_fine_code_snapshot_i[1]), .C(n31), .D(n32), .Y(n2) );
  AND2_X1M_A9TR40 U8 ( .A(n20), .B(n21), .Y(n8) );
  NAND3B_X2M_A9TR40 U9 ( .AN(target_medium_therm_o[4]), .B(n16), .C(n9), .Y(
        target_medium_therm_o[3]) );
  NAND2_X1A_A9TR40 U10 ( .A(n18), .B(n19), .Y(\m_det_o[3] ) );
  NAND3_X1M_A9TR40 U11 ( .A(margin_sel_i[0]), .B(n26), .C(n23), .Y(n19) );
  NOR2_X1A_A9TR40 U12 ( .A(n6), .B(cal_fine_code_snapshot_i[0]), .Y(n24) );
  NAND3_X1M_A9TR40 U13 ( .A(n26), .B(n7), .C(n23), .Y(n17) );
  NOR2_X0P7B_A9TR40 U14 ( .A(n6), .B(cal_fine_code_snapshot_i[0]), .Y(n1) );
  NOR2_X2A_A9TR40 U15 ( .A(margin_sel_i[1]), .B(cal_fine_code_snapshot_i[0]),
        .Y(n26) );
  NAND3BB_X1M_A9TR40 U16 ( .AN(target_medium_therm_o[2]), .BN(n3), .C(n14),
        .Y(mapping_supported_o) );
  NOR3BB_X2M_A9TR40 U17 ( .AN(n5), .BN(n2), .C(cal_medium_code_snapshot_i[1]),
        .Y(n25) );
  INV_X0P8B_A9TR40 U18 ( .A(mapping_supported_o), .Y(\target_fine_therm_o[5] )
         );
  NAND3_X1M_A9TR40 U19 ( .A(n26), .B(n7), .C(n25), .Y(n16) );
  INV_X1M_A9TR40 U20 ( .A(margin_sel_i[0]), .Y(n7) );
  NOR4BB_X4M_A9TR40 U21 ( .AN(cal_fine_code_snapshot_i[2]), .BN(
        cal_fine_code_snapshot_i[1]), .C(n31), .D(n32), .Y(n30) );
  OR3_X8M_A9TR40 U22 ( .A(cal_fine_code_snapshot_i[3]), .B(
        cal_medium_code_snapshot_i[4]), .C(cal_medium_code_snapshot_i[3]), .Y(
        n32) );
  NAND4_X0P7M_A9TR40 U23 ( .A(n16), .B(n17), .C(n19), .D(n20), .Y(f_det_o[2])
         );
  NAND3B_X0P5M_A9TR40 U24 ( .AN(f_det_o[0]), .B(n18), .C(n10), .Y(f_det_o[3])
         );
  NAND3_X0P5M_A9TR40 U25 ( .A(n11), .B(n17), .C(n10), .Y(m_det_o[1]) );
  NAND4_X0P5M_A9TR40 U26 ( .A(n8), .B(n16), .C(n17), .D(n9), .Y(m_det_o[2]) );
  NAND3_X0P5M_A9TR40 U27 ( .A(n17), .B(n15), .C(n8), .Y(m_det_o[0]) );
  NAND3_X0P5M_A9TR40 U28 ( .A(n8), .B(n9), .C(n10), .Y(trip_qualified_o) );
  NAND4_X0P5M_A9TR40 U29 ( .A(mapping_supported_o), .B(n11), .C(n12), .D(n4),
        .Y(target_fine_therm_o[9]) );
  NAND3_X1M_A9TR40 U30 ( .A(n25), .B(n26), .C(margin_sel_i[0]), .Y(n9) );
  NAND2_X0P5M_A9TR40 U31 ( .A(margin_sel_i[1]), .B(n22), .Y(n15) );
  NAND2_X0P5A_A9TR40 U32 ( .A(n22), .B(margin_sel_i[0]), .Y(n14) );
  NAND3_X0P5M_A9TR40 U33 ( .A(n21), .B(n9), .C(n27), .Y(f_det_o[0]) );
  AOI31_X0P5M_A9TR40 U34 ( .A0(n1), .A1(margin_sel_i[0]), .A2(n23), .B0(n3),
        .Y(n27) );
  NAND2_X0P5A_A9TR40 U35 ( .A(margin_sel_i[1]), .B(n7), .Y(n12) );
  NOR3BB_X4M_A9TR40 U36 ( .AN(cal_medium_code_snapshot_i[1]), .BN(n30), .C(n5),
        .Y(n23) );
  INV_X1M_A9TR40 U37 ( .A(n13), .Y(\target_fine_therm_o[7] ) );
  NAND2B_X1M_A9TR40 U38 ( .AN(\m_det_o[3] ), .B(n17), .Y(
        \target_medium_therm_o[6] ) );
  INV_X1M_A9TR40 U39 ( .A(target_medium_therm_o[3]), .Y(n4) );
  NAND2B_X1M_A9TR40 U40 ( .AN(\target_medium_therm_o[6] ), .B(n8), .Y(
        target_medium_therm_o[4]) );
  INV_X1M_A9TR40 U41 ( .A(n11), .Y(n3) );
  NOR2_X1A_A9TR40 U42 ( .A(\target_fine_therm_o[5] ), .B(f_det_o[2]), .Y(n13)
         );
  NAND2_X1A_A9TR40 U43 ( .A(n23), .B(n24), .Y(n18) );
  NAND3_X1M_A9TR40 U44 ( .A(n25), .B(n7), .C(n1), .Y(n20) );
  NAND3_X1M_A9TR40 U45 ( .A(n7), .B(n6), .C(n22), .Y(n11) );
  AND2_X1M_A9TR40 U46 ( .A(n15), .B(n14), .Y(n10) );
  NAND2B_X1M_A9TR40 U47 ( .AN(f_det_o[2]), .B(n14), .Y(f_det_o[1]) );
  NAND3_X1M_A9TR40 U48 ( .A(margin_sel_i[0]), .B(n25), .C(n1), .Y(n21) );
  NAND2_X1A_A9TR40 U49 ( .A(n12), .B(n13), .Y(target_fine_therm_o[8]) );
  NOR4BB_X2M_A9TR40 U50 ( .AN(n28), .BN(n5), .C(cal_fine_code_snapshot_i[2]),
        .D(n29), .Y(n22) );
  NOR3_X1A_A9TR40 U51 ( .A(cal_medium_code_snapshot_i[2]), .B(
        cal_medium_code_snapshot_i[4]), .C(cal_medium_code_snapshot_i[3]), .Y(
        n28) );
  NAND4XXXB_X1M_A9TR40 U52 ( .DN(cal_fine_code_snapshot_i[1]), .A(
        cal_medium_code_snapshot_i[1]), .B(cal_fine_code_snapshot_i[3]), .C(
        cal_fine_code_snapshot_i[0]), .Y(n29) );
  TIELO_X1M_A9TR40 U53 ( .Y(\*Logic0* ) );
endmodule


module ftc_detection_margin_manager ( cal_clk_i, ctrl_por_n_i, cal_cfg_valid_i,
        cal_medium_code_snapshot_i, cal_fine_code_snapshot_i,
        cal_medium_therm_snapshot_i, cal_fine_therm_snapshot_i, det_prepare_i,
        det_owner_valid_i, handoff_blocked_i, margin_sel_i,
        margin_select_valid_i, det_takeover_ready_o, det_sense_dff_reset_o,
        det_sense_s_clk_o, det_medium_therm_o, det_fine_therm_o,
        margin_cfg_valid_o, mapping_supported_o, trip_qualified_o,
        margin_protocol_error_o, m_det_o, f_det_o, margin_level_o );
  input [4:0] cal_medium_code_snapshot_i;
  input [3:0] cal_fine_code_snapshot_i;
  input [15:0] cal_medium_therm_snapshot_i;
  input [9:0] cal_fine_therm_snapshot_i;
  input [1:0] margin_sel_i;
  output [15:0] det_medium_therm_o;
  output [9:0] det_fine_therm_o;
  output [4:0] m_det_o;
  output [3:0] f_det_o;
  output [1:0] margin_level_o;
  input cal_clk_i, ctrl_por_n_i, cal_cfg_valid_i, det_prepare_i,
         det_owner_valid_i, handoff_blocked_i, margin_select_valid_i;
  output det_takeover_ready_o, det_sense_dff_reset_o, det_sense_s_clk_o,
         margin_cfg_valid_o, mapping_supported_o, trip_qualified_o,
         margin_protocol_error_o;
  wire   \*Logic1* , \*Logic0* , mapper_mapping_supported,
         mapper_trip_qualified, snapshot_loaded_q, n1, n2, n3, n4, n5, n6, n7,
         n8, n9, n10, n11, n12, n13, n14, n15, n16, n17, n18, n19, n20, n21,
         n23, n24, n25, n26, n27, n28, n29, n30, n31, n32, n33, n34, n35, n36,
         n37, n38, n39, n40, n41, n42, n43, n44, n45, n46, n47, n48, n49, n50,
         n51, n53, n54, n55, n56, n57, n58, n59, n60, n61, n62, n63, n64, n65,
         n66, n67, n68, n69, n70, n71, n72, n73, n74, n75, n76, n77, n78, n79,
         n80, n81, n82, n83, n84, n85, n86, n87, n88, n89, n90, n91, n92, n93,
         n94, n95, n96, n97, n98, n99, n100, n101, n102, n111, n112, n113,
         n114, n115, n116, n117, n118, n119, n120, n121, n122, n123, n125,
         n126, n127, n128, n129, n130, n131, n133, n134, n135, n136, n137,
         n138, n139, n140, n141, n142, n143, n144, n145, n146, n147, n148,
         n149, n150, n151, n152, n153, n154, n155, n156, n157, n158, n159,
         n160, n161, n162, n163, n164, n165, n166, n167, n168, n169, n170,
         n171, n172;
  wire   [4:0] mapper_m_det;
  wire   [3:0] mapper_f_det;
  wire   [15:0] mapper_medium_therm;
  wire   [9:0] mapper_fine_therm;
  wire   [3:0] state_q;
  wire   [15:0] target_medium_therm_q;
  wire   [9:0] target_fine_therm_q;
  assign det_sense_dff_reset_o = \*Logic1* ;
  assign det_sense_s_clk_o = \*Logic0* ;

  ftc_detection_margin_mapper u_exact_mapper ( .cal_medium_code_snapshot_i(
        cal_medium_code_snapshot_i), .cal_fine_code_snapshot_i(
        cal_fine_code_snapshot_i), .margin_sel_i(margin_sel_i),
        .mapping_supported_o(mapper_mapping_supported), .trip_qualified_o(
        mapper_trip_qualified), .m_det_o(mapper_m_det), .f_det_o(mapper_f_det),
        .target_medium_therm_o(mapper_medium_therm), .target_fine_therm_o(
        mapper_fine_therm) );
  AO1B2_X0P5M_A9TR40 U3 ( .B0(det_medium_therm_o[0]), .B1(n171), .A0N(n2), .Y(
        n59) );
  AOI22_X0P5M_A9TR40 U4 ( .A0(cal_medium_therm_snapshot_i[0]), .A1(n168), .B0(
        target_medium_therm_q[0]), .B1(n165), .Y(n2) );
  AO1B2_X0P5M_A9TR40 U5 ( .B0(det_medium_therm_o[1]), .B1(n171), .A0N(n5), .Y(
        n60) );
  AOI22_X0P5M_A9TR40 U6 ( .A0(cal_medium_therm_snapshot_i[1]), .A1(n168), .B0(
        target_medium_therm_q[1]), .B1(n165), .Y(n5) );
  AO1B2_X0P5M_A9TR40 U7 ( .B0(det_medium_therm_o[2]), .B1(n171), .A0N(n6), .Y(
        n61) );
  AOI22_X0P5M_A9TR40 U8 ( .A0(cal_medium_therm_snapshot_i[2]), .A1(n168), .B0(
        target_medium_therm_q[2]), .B1(n165), .Y(n6) );
  AO1B2_X0P5M_A9TR40 U9 ( .B0(det_medium_therm_o[3]), .B1(n171), .A0N(n7), .Y(
        n62) );
  AOI22_X0P5M_A9TR40 U10 ( .A0(cal_medium_therm_snapshot_i[3]), .A1(n168),
        .B0(target_medium_therm_q[3]), .B1(n165), .Y(n7) );
  AO1B2_X0P5M_A9TR40 U11 ( .B0(det_medium_therm_o[4]), .B1(n171), .A0N(n8),
        .Y(n63) );
  AOI22_X0P5M_A9TR40 U12 ( .A0(cal_medium_therm_snapshot_i[4]), .A1(n168),
        .B0(target_medium_therm_q[4]), .B1(n165), .Y(n8) );
  AO1B2_X0P5M_A9TR40 U13 ( .B0(det_medium_therm_o[5]), .B1(n171), .A0N(n9),
        .Y(n64) );
  AOI22_X0P5M_A9TR40 U14 ( .A0(cal_medium_therm_snapshot_i[5]), .A1(n168),
        .B0(target_medium_therm_q[5]), .B1(n165), .Y(n9) );
  AO1B2_X0P5M_A9TR40 U15 ( .B0(det_medium_therm_o[6]), .B1(n171), .A0N(n10),
        .Y(n65) );
  AOI22_X0P5M_A9TR40 U16 ( .A0(cal_medium_therm_snapshot_i[6]), .A1(n168),
        .B0(target_medium_therm_q[6]), .B1(n165), .Y(n10) );
  AO1B2_X0P5M_A9TR40 U17 ( .B0(det_medium_therm_o[7]), .B1(n171), .A0N(n11),
        .Y(n66) );
  AOI22_X0P5M_A9TR40 U18 ( .A0(cal_medium_therm_snapshot_i[7]), .A1(n168),
        .B0(target_medium_therm_q[7]), .B1(n165), .Y(n11) );
  AO1B2_X0P5M_A9TR40 U19 ( .B0(det_medium_therm_o[8]), .B1(n171), .A0N(n12),
        .Y(n67) );
  AOI22_X0P5M_A9TR40 U20 ( .A0(cal_medium_therm_snapshot_i[8]), .A1(n168),
        .B0(target_medium_therm_q[8]), .B1(n165), .Y(n12) );
  AO1B2_X0P5M_A9TR40 U21 ( .B0(det_medium_therm_o[9]), .B1(n171), .A0N(n13),
        .Y(n68) );
  AOI22_X0P5M_A9TR40 U22 ( .A0(cal_medium_therm_snapshot_i[9]), .A1(n168),
        .B0(target_medium_therm_q[9]), .B1(n165), .Y(n13) );
  AO1B2_X0P5M_A9TR40 U23 ( .B0(det_medium_therm_o[10]), .B1(n171), .A0N(n14),
        .Y(n69) );
  AOI22_X0P5M_A9TR40 U24 ( .A0(cal_medium_therm_snapshot_i[10]), .A1(n167),
        .B0(target_medium_therm_q[10]), .B1(n165), .Y(n14) );
  AO1B2_X0P5M_A9TR40 U25 ( .B0(det_medium_therm_o[11]), .B1(n170), .A0N(n15),
        .Y(n70) );
  AOI22_X0P5M_A9TR40 U26 ( .A0(cal_medium_therm_snapshot_i[11]), .A1(n167),
        .B0(target_medium_therm_q[11]), .B1(n165), .Y(n15) );
  AO1B2_X0P5M_A9TR40 U27 ( .B0(det_medium_therm_o[12]), .B1(n170), .A0N(n16),
        .Y(n71) );
  AOI22_X0P5M_A9TR40 U28 ( .A0(cal_medium_therm_snapshot_i[12]), .A1(n167),
        .B0(target_medium_therm_q[12]), .B1(n164), .Y(n16) );
  AO1B2_X0P5M_A9TR40 U29 ( .B0(det_medium_therm_o[13]), .B1(n170), .A0N(n17),
        .Y(n72) );
  AOI22_X0P5M_A9TR40 U30 ( .A0(cal_medium_therm_snapshot_i[13]), .A1(n167),
        .B0(target_medium_therm_q[13]), .B1(n164), .Y(n17) );
  AO1B2_X0P5M_A9TR40 U31 ( .B0(det_medium_therm_o[14]), .B1(n170), .A0N(n18),
        .Y(n73) );
  AOI22_X0P5M_A9TR40 U32 ( .A0(cal_medium_therm_snapshot_i[14]), .A1(n167),
        .B0(target_medium_therm_q[14]), .B1(n164), .Y(n18) );
  AO1B2_X0P5M_A9TR40 U33 ( .B0(det_medium_therm_o[15]), .B1(n170), .A0N(n19),
        .Y(n74) );
  AOI22_X0P5M_A9TR40 U34 ( .A0(cal_medium_therm_snapshot_i[15]), .A1(n167),
        .B0(target_medium_therm_q[15]), .B1(n164), .Y(n19) );
  AO1B2_X0P5M_A9TR40 U35 ( .B0(det_fine_therm_o[0]), .B1(n170), .A0N(n20), .Y(
        n75) );
  AOI22_X0P5M_A9TR40 U36 ( .A0(cal_fine_therm_snapshot_i[0]), .A1(n167), .B0(
        target_fine_therm_q[0]), .B1(n164), .Y(n20) );
  AO22_X0P5M_A9TR40 U37 ( .A0(n155), .A1(target_fine_therm_q[0]), .B0(
        mapper_fine_therm[0]), .B1(n159), .Y(n76) );
  AO1B2_X0P5M_A9TR40 U38 ( .B0(det_fine_therm_o[1]), .B1(n170), .A0N(n23), .Y(
        n77) );
  AOI22_X0P5M_A9TR40 U39 ( .A0(cal_fine_therm_snapshot_i[1]), .A1(n167), .B0(
        target_fine_therm_q[1]), .B1(n164), .Y(n23) );
  AO22_X0P5M_A9TR40 U40 ( .A0(n154), .A1(target_fine_therm_q[1]), .B0(
        mapper_fine_therm[1]), .B1(n136), .Y(n78) );
  AO1B2_X0P5M_A9TR40 U41 ( .B0(det_fine_therm_o[2]), .B1(n170), .A0N(n24), .Y(
        n79) );
  AOI22_X0P5M_A9TR40 U42 ( .A0(cal_fine_therm_snapshot_i[2]), .A1(n167), .B0(
        target_fine_therm_q[2]), .B1(n164), .Y(n24) );
  AO22_X0P5M_A9TR40 U43 ( .A0(n154), .A1(target_fine_therm_q[2]), .B0(
        mapper_fine_therm[2]), .B1(n159), .Y(n80) );
  AO1B2_X0P5M_A9TR40 U44 ( .B0(det_fine_therm_o[3]), .B1(n170), .A0N(n25), .Y(
        n81) );
  AOI22_X0P5M_A9TR40 U45 ( .A0(cal_fine_therm_snapshot_i[3]), .A1(n167), .B0(
        target_fine_therm_q[3]), .B1(n164), .Y(n25) );
  AO22_X0P5M_A9TR40 U46 ( .A0(n154), .A1(target_fine_therm_q[3]), .B0(
        mapper_fine_therm[3]), .B1(n158), .Y(n82) );
  AO1B2_X0P5M_A9TR40 U47 ( .B0(det_fine_therm_o[4]), .B1(n170), .A0N(n26), .Y(
        n83) );
  AOI22_X0P5M_A9TR40 U48 ( .A0(cal_fine_therm_snapshot_i[4]), .A1(n167), .B0(
        target_fine_therm_q[4]), .B1(n164), .Y(n26) );
  AO22_X0P5M_A9TR40 U49 ( .A0(n155), .A1(target_fine_therm_q[4]), .B0(
        mapper_fine_therm[4]), .B1(n160), .Y(n84) );
  AO1B2_X0P5M_A9TR40 U50 ( .B0(det_fine_therm_o[5]), .B1(n170), .A0N(n27), .Y(
        n85) );
  AOI22_X0P5M_A9TR40 U51 ( .A0(cal_fine_therm_snapshot_i[5]), .A1(n167), .B0(
        target_fine_therm_q[5]), .B1(n164), .Y(n27) );
  AO22_X0P5M_A9TR40 U52 ( .A0(n155), .A1(target_fine_therm_q[5]), .B0(
        mapper_fine_therm[5]), .B1(n161), .Y(n86) );
  AO1B2_X0P5M_A9TR40 U53 ( .B0(det_fine_therm_o[6]), .B1(n170), .A0N(n28), .Y(
        n87) );
  AOI22_X0P5M_A9TR40 U54 ( .A0(cal_fine_therm_snapshot_i[6]), .A1(n167), .B0(
        target_fine_therm_q[6]), .B1(n164), .Y(n28) );
  AO22_X0P5M_A9TR40 U55 ( .A0(n155), .A1(target_fine_therm_q[6]), .B0(
        mapper_fine_therm[6]), .B1(n136), .Y(n88) );
  AO1B2_X0P5M_A9TR40 U56 ( .B0(det_fine_therm_o[7]), .B1(n170), .A0N(n29), .Y(
        n89) );
  AOI22_X0P5M_A9TR40 U57 ( .A0(cal_fine_therm_snapshot_i[7]), .A1(n167), .B0(
        target_fine_therm_q[7]), .B1(n164), .Y(n29) );
  AO22_X0P5M_A9TR40 U58 ( .A0(n155), .A1(target_fine_therm_q[7]), .B0(
        mapper_fine_therm[7]), .B1(n158), .Y(n90) );
  AO1B2_X0P5M_A9TR40 U59 ( .B0(det_fine_therm_o[8]), .B1(n170), .A0N(n30), .Y(
        n91) );
  AOI22_X0P5M_A9TR40 U60 ( .A0(cal_fine_therm_snapshot_i[8]), .A1(n167), .B0(
        target_fine_therm_q[8]), .B1(n164), .Y(n30) );
  AO22_X0P5M_A9TR40 U61 ( .A0(n155), .A1(target_fine_therm_q[8]), .B0(
        mapper_fine_therm[8]), .B1(n160), .Y(n92) );
  AO1B2_X0P5M_A9TR40 U62 ( .B0(det_fine_therm_o[9]), .B1(n170), .A0N(n31), .Y(
        n93) );
  AOI22_X0P5M_A9TR40 U63 ( .A0(cal_fine_therm_snapshot_i[9]), .A1(n167), .B0(
        target_fine_therm_q[9]), .B1(n164), .Y(n31) );
  AO22_X0P5M_A9TR40 U67 ( .A0(n155), .A1(target_fine_therm_q[9]), .B0(
        mapper_fine_therm[9]), .B1(n160), .Y(n94) );
  AO22_X0P5M_A9TR40 U68 ( .A0(n155), .A1(target_medium_therm_q[0]), .B0(
        mapper_medium_therm[0]), .B1(n159), .Y(n95) );
  AO22_X0P5M_A9TR40 U69 ( .A0(n155), .A1(target_medium_therm_q[1]), .B0(
        mapper_medium_therm[1]), .B1(n158), .Y(n96) );
  AO22_X0P5M_A9TR40 U70 ( .A0(n155), .A1(target_medium_therm_q[2]), .B0(
        mapper_medium_therm[2]), .B1(n160), .Y(n97) );
  AO22_X0P5M_A9TR40 U71 ( .A0(n155), .A1(target_medium_therm_q[3]), .B0(
        mapper_medium_therm[3]), .B1(n136), .Y(n98) );
  AO22_X0P5M_A9TR40 U72 ( .A0(n155), .A1(target_medium_therm_q[4]), .B0(
        mapper_medium_therm[4]), .B1(n159), .Y(n99) );
  AO22_X0P5M_A9TR40 U73 ( .A0(n155), .A1(target_medium_therm_q[5]), .B0(
        mapper_medium_therm[5]), .B1(n158), .Y(n100) );
  AO22_X0P5M_A9TR40 U74 ( .A0(n155), .A1(target_medium_therm_q[6]), .B0(
        mapper_medium_therm[6]), .B1(n160), .Y(n101) );
  AO22_X0P5M_A9TR40 U75 ( .A0(n155), .A1(target_medium_therm_q[7]), .B0(
        mapper_medium_therm[7]), .B1(n159), .Y(n102) );
  INV_X0P5B_A9TR40 U88 ( .A(margin_cfg_valid_o), .Y(n32) );
  OAI21_X0P5M_A9TR40 U89 ( .A0(n42), .A1(n40), .B0(n43), .Y(n112) );
  NOR2_X0P5A_A9TR40 U90 ( .A(margin_protocol_error_o), .B(handoff_blocked_i),
        .Y(n43) );
  OR2_X0P5B_A9TR40 U91 ( .A(cal_cfg_valid_i), .B(snapshot_loaded_q), .Y(n113)
         );
  AO22_X0P5M_A9TR40 U93 ( .A0(margin_sel_i[1]), .A1(n136), .B0(
        margin_level_o[1]), .B1(n154), .Y(n115) );
  AO22_X0P5M_A9TR40 U94 ( .A0(mapper_f_det[0]), .A1(n159), .B0(f_det_o[0]),
        .B1(n154), .Y(n116) );
  AO22_X0P5M_A9TR40 U96 ( .A0(mapper_f_det[2]), .A1(n158), .B0(f_det_o[2]),
        .B1(n154), .Y(n118) );
  AO22_X0P5M_A9TR40 U97 ( .A0(mapper_f_det[3]), .A1(n136), .B0(f_det_o[3]),
        .B1(n154), .Y(n119) );
  AO22_X0P5M_A9TR40 U98 ( .A0(mapper_m_det[0]), .A1(n161), .B0(m_det_o[0]),
        .B1(n154), .Y(n120) );
  AO22_X0P5M_A9TR40 U99 ( .A0(mapper_m_det[1]), .A1(n161), .B0(m_det_o[1]),
        .B1(n154), .Y(n121) );
  AO22_X0P5M_A9TR40 U100 ( .A0(mapper_m_det[2]), .A1(n161), .B0(m_det_o[2]),
        .B1(n154), .Y(n122) );
  AO22_X0P5M_A9TR40 U101 ( .A0(mapper_m_det[3]), .A1(n161), .B0(m_det_o[3]),
        .B1(n154), .Y(n123) );
  AO22_X0P5M_A9TR40 U103 ( .A0(mapper_trip_qualified), .A1(n161), .B0(
        trip_qualified_o), .B1(n154), .Y(n125) );
  NAND2B_X0P5M_A9TR40 U105 ( .AN(mapping_supported_o), .B(n156), .Y(n126) );
  INV_X0P5B_A9TR40 U108 ( .A(n45), .Y(n127) );
  OAI21_X0P5M_A9TR40 U111 ( .A0(n46), .A1(n49), .B0(n50), .Y(n128) );
  NOR2B_X0P5M_A9TR40 U114 ( .AN(state_q[3]), .B(n53), .Y(n129) );
  OAI22_X0P5M_A9TR40 U115 ( .A0(state_q[0]), .A1(n46), .B0(n54), .B1(n41), .Y(
        n130) );
  OAI21_X0P5M_A9TR40 U120 ( .A0(n35), .A1(n40), .B0(n36), .Y(n55) );
  INV_X0P5B_A9TR40 U121 ( .A(margin_select_valid_i), .Y(n40) );
  INV_X0P5B_A9TR40 U122 ( .A(n53), .Y(n46) );
  NOR2_X0P5A_A9TR40 U124 ( .A(n51), .B(margin_select_valid_i), .Y(n48) );
  INV_X0P5B_A9TR40 U125 ( .A(n36), .Y(n51) );
  AOI22_X0P5M_A9TR40 U127 ( .A0(state_q[1]), .A1(n58), .B0(cal_cfg_valid_i),
        .B1(n41), .Y(n57) );
  OR2_X0P5B_A9TR40 U128 ( .A(det_owner_valid_i), .B(n41), .Y(n58) );
  INV_X0P5B_A9TR40 U130 ( .A(n135), .Y(n131) );
  INV_X0P5B_A9TR40 U132 ( .A(state_q[1]), .Y(n35) );
  NAND2_X0P5A_A9TR40 U133 ( .A(state_q[0]), .B(n50), .Y(n37) );
  INV_X0P5B_A9TR40 U134 ( .A(state_q[2]), .Y(n50) );
  DFFSQ_X1M_A9TR40 \target_fine_therm_q_reg[9]  ( .D(n94), .CK(cal_clk_i),
        .SN(n135), .Q(target_fine_therm_q[9]) );
  DFFSQ_X1M_A9TR40 \target_fine_therm_q_reg[8]  ( .D(n92), .CK(cal_clk_i),
        .SN(n135), .Q(target_fine_therm_q[8]) );
  DFFSQ_X1M_A9TR40 \target_fine_therm_q_reg[7]  ( .D(n90), .CK(cal_clk_i),
        .SN(ctrl_por_n_i), .Q(target_fine_therm_q[7]) );
  DFFSQ_X1M_A9TR40 \target_fine_therm_q_reg[6]  ( .D(n88), .CK(cal_clk_i),
        .SN(n135), .Q(target_fine_therm_q[6]) );
  DFFSQ_X1M_A9TR40 \target_fine_therm_q_reg[5]  ( .D(n86), .CK(cal_clk_i),
        .SN(n135), .Q(target_fine_therm_q[5]) );
  DFFSQ_X1M_A9TR40 \target_fine_therm_q_reg[4]  ( .D(n84), .CK(cal_clk_i),
        .SN(n135), .Q(target_fine_therm_q[4]) );
  DFFSQ_X1M_A9TR40 \target_fine_therm_q_reg[3]  ( .D(n82), .CK(cal_clk_i),
        .SN(n135), .Q(target_fine_therm_q[3]) );
  DFFSQ_X1M_A9TR40 \target_fine_therm_q_reg[2]  ( .D(n80), .CK(cal_clk_i),
        .SN(n135), .Q(target_fine_therm_q[2]) );
  DFFSQ_X1M_A9TR40 \target_fine_therm_q_reg[1]  ( .D(n78), .CK(cal_clk_i),
        .SN(n135), .Q(target_fine_therm_q[1]) );
  DFFSQ_X1M_A9TR40 \target_fine_therm_q_reg[0]  ( .D(n76), .CK(cal_clk_i),
        .SN(n135), .Q(target_fine_therm_q[0]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[7]  ( .D(n102), .CK(cal_clk_i),
        .R(n148), .Q(target_medium_therm_q[7]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[6]  ( .D(n101), .CK(cal_clk_i),
        .R(n148), .Q(target_medium_therm_q[6]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[5]  ( .D(n100), .CK(cal_clk_i),
        .R(n148), .Q(target_medium_therm_q[5]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[4]  ( .D(n99), .CK(cal_clk_i),
        .R(n148), .Q(target_medium_therm_q[4]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[3]  ( .D(n98), .CK(cal_clk_i),
        .R(n148), .Q(target_medium_therm_q[3]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[2]  ( .D(n97), .CK(cal_clk_i),
        .R(n148), .Q(target_medium_therm_q[2]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[1]  ( .D(n96), .CK(cal_clk_i),
        .R(n148), .Q(target_medium_therm_q[1]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[0]  ( .D(n95), .CK(cal_clk_i),
        .R(n148), .Q(target_medium_therm_q[0]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[15]  ( .D(n146), .CK(cal_clk_i),
        .R(n149), .Q(target_medium_therm_q[15]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[14]  ( .D(n145), .CK(cal_clk_i),
        .R(n149), .Q(target_medium_therm_q[14]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[13]  ( .D(n144), .CK(cal_clk_i),
        .R(n149), .Q(target_medium_therm_q[13]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[12]  ( .D(n143), .CK(cal_clk_i),
        .R(n149), .Q(target_medium_therm_q[12]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[11]  ( .D(n142), .CK(cal_clk_i),
        .R(n148), .Q(target_medium_therm_q[11]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[10]  ( .D(n141), .CK(cal_clk_i),
        .R(n148), .Q(target_medium_therm_q[10]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[9]  ( .D(n140), .CK(cal_clk_i),
        .R(n148), .Q(target_medium_therm_q[9]) );
  DFFRPQ_X1M_A9TR40 \target_medium_therm_q_reg[8]  ( .D(n139), .CK(cal_clk_i),
        .R(n148), .Q(target_medium_therm_q[8]) );
  DFFSQ_X1M_A9TR40 \det_fine_therm_q_reg[9]  ( .D(n93), .CK(cal_clk_i), .SN(
        n135), .Q(det_fine_therm_o[9]) );
  DFFSQ_X1M_A9TR40 \det_fine_therm_q_reg[8]  ( .D(n91), .CK(cal_clk_i), .SN(
        ctrl_por_n_i), .Q(det_fine_therm_o[8]) );
  DFFSQ_X1M_A9TR40 \det_fine_therm_q_reg[7]  ( .D(n89), .CK(cal_clk_i), .SN(
        ctrl_por_n_i), .Q(det_fine_therm_o[7]) );
  DFFSQ_X1M_A9TR40 \det_fine_therm_q_reg[6]  ( .D(n87), .CK(cal_clk_i), .SN(
        ctrl_por_n_i), .Q(det_fine_therm_o[6]) );
  DFFSQ_X1M_A9TR40 \det_fine_therm_q_reg[5]  ( .D(n85), .CK(cal_clk_i), .SN(
        ctrl_por_n_i), .Q(det_fine_therm_o[5]) );
  DFFSQ_X1M_A9TR40 \det_fine_therm_q_reg[4]  ( .D(n83), .CK(cal_clk_i), .SN(
        ctrl_por_n_i), .Q(det_fine_therm_o[4]) );
  DFFSQ_X1M_A9TR40 \det_fine_therm_q_reg[3]  ( .D(n81), .CK(cal_clk_i), .SN(
        ctrl_por_n_i), .Q(det_fine_therm_o[3]) );
  DFFSQ_X1M_A9TR40 \det_fine_therm_q_reg[2]  ( .D(n79), .CK(cal_clk_i), .SN(
        ctrl_por_n_i), .Q(det_fine_therm_o[2]) );
  DFFSQ_X1M_A9TR40 \det_fine_therm_q_reg[1]  ( .D(n77), .CK(cal_clk_i), .SN(
        ctrl_por_n_i), .Q(det_fine_therm_o[1]) );
  DFFSQ_X1M_A9TR40 \det_fine_therm_q_reg[0]  ( .D(n75), .CK(cal_clk_i), .SN(
        ctrl_por_n_i), .Q(det_fine_therm_o[0]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[15]  ( .D(n74), .CK(cal_clk_i),
        .R(n148), .Q(det_medium_therm_o[15]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[14]  ( .D(n73), .CK(cal_clk_i),
        .R(n148), .Q(det_medium_therm_o[14]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[13]  ( .D(n72), .CK(cal_clk_i),
        .R(n147), .Q(det_medium_therm_o[13]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[12]  ( .D(n71), .CK(cal_clk_i),
        .R(n147), .Q(det_medium_therm_o[12]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[11]  ( .D(n70), .CK(cal_clk_i),
        .R(n147), .Q(det_medium_therm_o[11]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[10]  ( .D(n69), .CK(cal_clk_i),
        .R(n147), .Q(det_medium_therm_o[10]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[9]  ( .D(n68), .CK(cal_clk_i), .R(
        n147), .Q(det_medium_therm_o[9]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[8]  ( .D(n67), .CK(cal_clk_i), .R(
        n147), .Q(det_medium_therm_o[8]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[7]  ( .D(n66), .CK(cal_clk_i), .R(
        n147), .Q(det_medium_therm_o[7]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[6]  ( .D(n65), .CK(cal_clk_i), .R(
        n147), .Q(det_medium_therm_o[6]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[5]  ( .D(n64), .CK(cal_clk_i), .R(
        n147), .Q(det_medium_therm_o[5]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[4]  ( .D(n63), .CK(cal_clk_i), .R(
        n147), .Q(det_medium_therm_o[4]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[3]  ( .D(n62), .CK(cal_clk_i), .R(
        n147), .Q(det_medium_therm_o[3]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[2]  ( .D(n61), .CK(cal_clk_i), .R(
        n147), .Q(det_medium_therm_o[2]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[1]  ( .D(n60), .CK(cal_clk_i), .R(
        n147), .Q(det_medium_therm_o[1]) );
  DFFRPQ_X1M_A9TR40 \det_medium_therm_q_reg[0]  ( .D(n59), .CK(cal_clk_i), .R(
        n147), .Q(det_medium_therm_o[0]) );
  DFFRPQ_X1M_A9TR40 margin_protocol_error_q_reg ( .D(n112), .CK(cal_clk_i),
        .R(n149), .Q(margin_protocol_error_o) );
  DFFRPQ_X1M_A9TR40 mapping_supported_q_reg ( .D(n126), .CK(cal_clk_i), .R(
        n150), .Q(mapping_supported_o) );
  DFFRPQ_X1M_A9TR40 trip_qualified_q_reg ( .D(n125), .CK(cal_clk_i), .R(n150),
        .Q(trip_qualified_o) );
  DFFRPQ_X1M_A9TR40 \m_det_q_reg[3]  ( .D(n123), .CK(cal_clk_i), .R(n150), .Q(
        m_det_o[3]) );
  DFFRPQ_X1M_A9TR40 \m_det_q_reg[2]  ( .D(n122), .CK(cal_clk_i), .R(n150), .Q(
        m_det_o[2]) );
  DFFRPQ_X1M_A9TR40 \m_det_q_reg[1]  ( .D(n121), .CK(cal_clk_i), .R(n150), .Q(
        m_det_o[1]) );
  DFFRPQ_X1M_A9TR40 \m_det_q_reg[0]  ( .D(n120), .CK(cal_clk_i), .R(n149), .Q(
        m_det_o[0]) );
  DFFRPQ_X1M_A9TR40 \f_det_q_reg[3]  ( .D(n119), .CK(cal_clk_i), .R(n149), .Q(
        f_det_o[3]) );
  DFFRPQ_X1M_A9TR40 \f_det_q_reg[2]  ( .D(n118), .CK(cal_clk_i), .R(n149), .Q(
        f_det_o[2]) );
  DFFRPQ_X1M_A9TR40 \f_det_q_reg[1]  ( .D(n117), .CK(cal_clk_i), .R(n149), .Q(
        f_det_o[1]) );
  DFFRPQ_X1M_A9TR40 \f_det_q_reg[0]  ( .D(n116), .CK(cal_clk_i), .R(n149), .Q(
        f_det_o[0]) );
  DFFRPQ_X1M_A9TR40 \margin_level_q_reg[1]  ( .D(n115), .CK(cal_clk_i), .R(
        n149), .Q(margin_level_o[1]) );
  DFFRPQ_X1M_A9TR40 \margin_level_q_reg[0]  ( .D(n114), .CK(cal_clk_i), .R(
        n149), .Q(margin_level_o[0]) );
  DFFRPQ_X1M_A9TR40 \m_det_q_reg[4]  ( .D(n138), .CK(cal_clk_i), .R(n150), .Q(
        m_det_o[4]) );
  DFFRPQ_X0P5M_A9TR40 margin_cfg_valid_q_reg ( .D(n111), .CK(cal_clk_i), .R(
        n149), .Q(margin_cfg_valid_o) );
  DFFRPQ_X1M_A9TR40 snapshot_loaded_q_reg ( .D(n113), .CK(cal_clk_i), .R(n149),
        .Q(snapshot_loaded_q) );
  DFFRPQ_X1M_A9TR40 \state_q_reg[3]  ( .D(n129), .CK(cal_clk_i), .R(n150), .Q(
        state_q[3]) );
  DFFRPQ_X1M_A9TR40 \state_q_reg[1]  ( .D(n127), .CK(cal_clk_i), .R(n150), .Q(
        state_q[1]) );
  DFFRPQ_X1M_A9TR40 \state_q_reg[0]  ( .D(n130), .CK(cal_clk_i), .R(n150), .Q(
        state_q[0]) );
  DFFRPQ_X1M_A9TR40 \state_q_reg[2]  ( .D(n128), .CK(cal_clk_i), .R(n150), .Q(
        state_q[2]) );
  BUF_X1P2M_A9TR40 U135 ( .A(n163), .Y(n136) );
  AO22_X0P7M_A9TR40 U136 ( .A0(margin_sel_i[0]), .A1(n160), .B0(
        margin_level_o[0]), .B1(n154), .Y(n114) );
  AO22_X0P7M_A9TR40 U137 ( .A0(mapper_f_det[1]), .A1(n160), .B0(f_det_o[1]),
        .B1(n154), .Y(n117) );
  BUF_X2P5M_A9TR40 U138 ( .A(n163), .Y(n160) );
  BUF_X2M_A9TR40 U139 ( .A(n163), .Y(n159) );
  INV_X3P5B_A9TR40 U140 ( .A(n21), .Y(n163) );
  BUFH_X1M_A9TR40 U141 ( .A(n4), .Y(n166) );
  OR2_X1M_A9TR40 U142 ( .A(n37), .B(state_q[3]), .Y(n133) );
  INV_X1M_A9TR40 U143 ( .A(ctrl_por_n_i), .Y(n134) );
  INV_X2M_A9TR40 U144 ( .A(n134), .Y(n135) );
  INV_X3M_A9TR40 U145 ( .A(n136), .Y(n155) );
  AOI211_X1M_A9TR40 U146 ( .A0(state_q[2]), .A1(margin_select_valid_i), .B0(
        n55), .C0(n56), .Y(n54) );
  OAI31_X1M_A9TR40 U147 ( .A0(n137), .A1(state_q[2]), .A2(state_q[1]), .B0(n53), .Y(n56) );
  OAI31_X1M_A9TR40 U148 ( .A0(n32), .A1(margin_select_valid_i), .A2(
        handoff_blocked_i), .B0(n33), .Y(n111) );
  NAND3_X0P5M_A9TR40 U149 ( .A(n34), .B(n35), .C(n36), .Y(n33) );
  OAI31_X1M_A9TR40 U150 ( .A0(n32), .A1(n37), .A2(n38), .B0(n39), .Y(n34) );
  NAND2_X2A_A9TR40 U151 ( .A(mapper_mapping_supported), .B(det_prepare_i), .Y(
        n38) );
  AOI221_X1M_A9TR40 U152 ( .A0(state_q[0]), .A1(n44), .B0(
        margin_select_valid_i), .B1(n41), .C0(n51), .Y(n49) );
  NAND2_X1M_A9TR40 U153 ( .A(n137), .B(n35), .Y(n44) );
  NOR2_X0P7B_A9TR40 U154 ( .A(n44), .B(n133), .Y(n42) );
  BUF_X1M_A9TR40 U155 ( .A(n163), .Y(n162) );
  BUFH_X1M_A9TR40 U156 ( .A(n163), .Y(n157) );
  INV_X1M_A9TR40 U157 ( .A(n38), .Y(n137) );
  OA21A1OI2_X0P7M_A9TR40 U158 ( .A0(n41), .A1(state_q[1]), .B0(n48), .C0(n46),
        .Y(n47) );
  OAI221_X1M_A9TR40 U159 ( .A0(state_q[1]), .A1(n50), .B0(state_q[2]), .B1(n57), .C0(n48), .Y(n53) );
  NOR2_X1A_A9TR40 U160 ( .A(state_q[3]), .B(handoff_blocked_i), .Y(n36) );
  OA21A1OI2_X0P7M_A9TR40 U161 ( .A0(n37), .A1(n46), .B0(state_q[1]), .C0(n47),
        .Y(n45) );
  INV_X1M_A9TR40 U162 ( .A(state_q[0]), .Y(n41) );
  NAND3_X0P5M_A9TR40 U163 ( .A(n40), .B(n41), .C(state_q[2]), .Y(n39) );
  BUFH_X1M_A9TR40 U164 ( .A(n162), .Y(n158) );
  BUFH_X1M_A9TR40 U165 ( .A(n3), .Y(n169) );
  BUFH_X1M_A9TR40 U166 ( .A(n153), .Y(n152) );
  BUFH_X1M_A9TR40 U167 ( .A(n153), .Y(n151) );
  NAND3BB_X1M_A9TR40 U168 ( .AN(handoff_blocked_i), .BN(n40), .C(n42), .Y(n21)
         );
  AND2_X0P7M_A9TR40 U169 ( .A(m_det_o[4]), .B(n154), .Y(n138) );
  AND2_X0P7M_A9TR40 U170 ( .A(n156), .B(target_medium_therm_q[9]), .Y(n140) );
  AND2_X0P7M_A9TR40 U171 ( .A(n156), .B(target_medium_therm_q[10]), .Y(n141)
         );
  AND2_X0P7M_A9TR40 U172 ( .A(n156), .B(target_medium_therm_q[11]), .Y(n142)
         );
  AND2_X0P7M_A9TR40 U173 ( .A(n156), .B(target_medium_therm_q[12]), .Y(n143)
         );
  AND2_X0P7M_A9TR40 U174 ( .A(n156), .B(target_medium_therm_q[13]), .Y(n144)
         );
  AND2_X0P7M_A9TR40 U175 ( .A(n156), .B(target_medium_therm_q[14]), .Y(n145)
         );
  AND2_X0P7M_A9TR40 U176 ( .A(n156), .B(target_medium_therm_q[15]), .Y(n146)
         );
  AND2_X0P5M_A9TR40 U177 ( .A(n155), .B(target_medium_therm_q[8]), .Y(n139) );
  BUFH_X1M_A9TR40 U178 ( .A(n1), .Y(n172) );
  INV_X1M_A9TR40 U179 ( .A(n160), .Y(n156) );
  BUF_X2M_A9TR40 U180 ( .A(n169), .Y(n167) );
  BUF_X2M_A9TR40 U181 ( .A(n169), .Y(n168) );
  BUFH_X1M_A9TR40 U182 ( .A(n157), .Y(n161) );
  NOR2_X1A_A9TR40 U183 ( .A(n170), .B(n164), .Y(n3) );
  BUF_X3M_A9TR40 U184 ( .A(n152), .Y(n147) );
  BUF_X3M_A9TR40 U185 ( .A(n152), .Y(n148) );
  BUF_X3M_A9TR40 U186 ( .A(n151), .Y(n149) );
  BUF_X2M_A9TR40 U187 ( .A(n151), .Y(n150) );
  BUF_X2M_A9TR40 U188 ( .A(n166), .Y(n164) );
  BUF_X2M_A9TR40 U189 ( .A(n172), .Y(n170) );
  BUF_X2M_A9TR40 U190 ( .A(n172), .Y(n171) );
  BUF_X2M_A9TR40 U191 ( .A(n166), .Y(n165) );
  AOI2XB1_X1M_A9TR40 U192 ( .A1N(snapshot_loaded_q), .A0(cal_cfg_valid_i),
        .B0(n164), .Y(n1) );
  BUFH_X1M_A9TR40 U193 ( .A(n131), .Y(n153) );
  TIEHI_X1M_A9TR40 U194 ( .Y(\*Logic1* ) );
  TIELO_X1M_A9TR40 U195 ( .Y(\*Logic0* ) );
  INV_X2M_A9TR40 U196 ( .A(n159), .Y(n154) );
  NOR3_X1A_A9TR40 U197 ( .A(n37), .B(state_q[3]), .C(n35), .Y(
        det_takeover_ready_o) );
  NOR4BB_X0P7M_A9TR40 U198 ( .AN(det_owner_valid_i), .BN(det_takeover_ready_o),
        .C(handoff_blocked_i), .D(margin_select_valid_i), .Y(n4) );
endmodule
