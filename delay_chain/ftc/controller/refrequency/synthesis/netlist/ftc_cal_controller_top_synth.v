/////////////////////////////////////////////////////////////
// Created by: Synopsys DC Expert(TM) in wire load mode
// Version   : Q-2019.12
// Date      : Sat Aug 22 14:46:42 2026
/////////////////////////////////////////////////////////////


module ftc_cfg_therm_regs ( clk_i, por_n_i, init_i, medium_inc_i, medium_dec_i, 
        fine_inc_i, fine_dec_i, lock_i, medium_therm_o, fine_therm_o, 
        medium_code_o, fine_code_o, medium_at_min_o, medium_at_max_o, 
        fine_at_min_o, fine_at_max_o, cfg_locked_o, 
        medium_too_low_for_backoff_o );
  output [15:0] medium_therm_o;
  output [9:0] fine_therm_o;
  output [4:0] medium_code_o;
  output [3:0] fine_code_o;
  input clk_i, por_n_i, init_i, medium_inc_i, medium_dec_i, fine_inc_i,
         fine_dec_i, lock_i;
  output medium_at_min_o, medium_at_max_o, fine_at_min_o, fine_at_max_o,
         cfg_locked_o, medium_too_low_for_backoff_o;
  wire   N108, N109, N110, N111, N131, N132, N133, N134, N135, N416, N425,
         N429, N435, n145, n146, n147, n148, n149, n150, n151, n152, n153,
         n154, n155, n156, n157, n158, n159, n160, n161, n162, n163, n164,
         n165, n166, n167, n168, n169, n170, n171, n172, n173, n174, n175,
         n176, n177, n178, n179, n180, \add_72/carry[4] , \add_72/carry[3] ,
         \add_72/carry[2] , n1, n2, n3, n4, n5, n6, n7, n8, n9, n10, n11, n12,
         n13, n14, n15, n16, n17, n18, n19, n20, n21, n22, n23, n24, n25, n26,
         n27, n28, n29, n30, n31, n32, n33, n34, n35, n36, n37, n38, n39, n40,
         n41, n42, n43, n44, n45, n46, n47, n48, n49, n50, n51, n52, n53, n54,
         n55, n56, n57, n58, n59, n60, n61, n62, n63, n64, n65, n66, n67, n68,
         n69, n70, n71, n72, n73, n74, n75, n76, n77, n78, n79, n80, n81, n82,
         n83, n84, n85, n86, n87, n88, n89, n90, n91, n92, n93, n94, n95, n96,
         n97, n98, n99, n100, n101, n102, n103, n104, n105, n106, n107, n108,
         n109, n110, n111, n112, n113, n114, n115, n116, n117, n118, n119,
         n120, n121, n122, n123, n124, n125, n126, n127, n128, n129, n130,
         n131, n132, n133, n134, n135, n136, n137, n138, n139, n140, n141,
         n142, n143, n144, n181, n182, n183, n184, n185, n186, n187, n188,
         n189, n190, n191, n192, n193, n194, n195, n196, n197, n198, n199,
         n200, n201, n202, n203, n204, n205, n206;
  assign medium_at_min_o = N416;
  assign medium_at_max_o = N425;
  assign fine_at_min_o = N429;
  assign fine_at_max_o = N435;

  DFFSQ_X1M_A9TR40 \fine_therm_o_reg[7]  ( .D(n152), .CK(clk_i), .SN(por_n_i), 
        .Q(fine_therm_o[7]) );
  DFFSQ_X1M_A9TR40 \fine_therm_o_reg[6]  ( .D(n151), .CK(clk_i), .SN(por_n_i), 
        .Q(fine_therm_o[6]) );
  DFFSQ_X1M_A9TR40 \fine_therm_o_reg[3]  ( .D(n150), .CK(clk_i), .SN(por_n_i), 
        .Q(fine_therm_o[3]) );
  DFFSQ_X1M_A9TR40 \fine_therm_o_reg[2]  ( .D(n149), .CK(clk_i), .SN(por_n_i), 
        .Q(fine_therm_o[2]) );
  DFFSQ_X1M_A9TR40 \fine_therm_o_reg[5]  ( .D(n148), .CK(clk_i), .SN(por_n_i), 
        .Q(fine_therm_o[5]) );
  DFFSQ_X1M_A9TR40 \fine_therm_o_reg[4]  ( .D(n147), .CK(clk_i), .SN(por_n_i), 
        .Q(fine_therm_o[4]) );
  DFFSQ_X1M_A9TR40 \fine_therm_o_reg[1]  ( .D(n146), .CK(clk_i), .SN(por_n_i), 
        .Q(fine_therm_o[1]) );
  DFFSQ_X1M_A9TR40 \fine_therm_o_reg[8]  ( .D(n153), .CK(clk_i), .SN(por_n_i), 
        .Q(fine_therm_o[8]) );
  DFFSQ_X1M_A9TR40 \fine_therm_o_reg[9]  ( .D(n154), .CK(clk_i), .SN(por_n_i), 
        .Q(fine_therm_o[9]) );
  DFFSQ_X1M_A9TR40 \fine_therm_o_reg[0]  ( .D(n145), .CK(clk_i), .SN(por_n_i), 
        .Q(fine_therm_o[0]) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[15]  ( .D(n166), .CK(clk_i), .R(n13), 
        .Q(medium_therm_o[15]) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[14]  ( .D(n174), .CK(clk_i), .R(n12), 
        .Q(medium_therm_o[14]) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[10]  ( .D(n173), .CK(clk_i), .R(n12), 
        .Q(medium_therm_o[10]) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[6]  ( .D(n172), .CK(clk_i), .R(n12), 
        .Q(medium_therm_o[6]) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[12]  ( .D(n171), .CK(clk_i), .R(n12), 
        .Q(medium_therm_o[12]) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[8]  ( .D(n170), .CK(clk_i), .R(n12), 
        .Q(medium_therm_o[8]) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[4]  ( .D(n169), .CK(clk_i), .R(n12), 
        .Q(medium_therm_o[4]) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[3]  ( .D(n168), .CK(clk_i), .R(n12), 
        .Q(medium_therm_o[3]) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[11]  ( .D(n165), .CK(clk_i), .R(n13), 
        .Q(medium_therm_o[11]) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[7]  ( .D(n164), .CK(clk_i), .R(n13), 
        .Q(medium_therm_o[7]) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[13]  ( .D(n163), .CK(clk_i), .R(n13), 
        .Q(medium_therm_o[13]) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[9]  ( .D(n162), .CK(clk_i), .R(n13), 
        .Q(medium_therm_o[9]) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[5]  ( .D(n161), .CK(clk_i), .R(n13), 
        .Q(medium_therm_o[5]) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[2]  ( .D(n160), .CK(clk_i), .R(n13), 
        .Q(medium_therm_o[2]) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[1]  ( .D(n159), .CK(clk_i), .R(n13), 
        .Q(medium_therm_o[1]) );
  DFFRPQ_X1M_A9TR40 \medium_code_o_reg[4]  ( .D(n178), .CK(clk_i), .R(n12), 
        .Q(medium_code_o[4]) );
  DFFRPQ_X1M_A9TR40 cfg_locked_o_reg ( .D(n180), .CK(clk_i), .R(n12), .Q(
        cfg_locked_o) );
  DFFRPQ_X1M_A9TR40 \medium_therm_o_reg[0]  ( .D(n167), .CK(clk_i), .R(n12), 
        .Q(medium_therm_o[0]) );
  DFFRPQ_X1M_A9TR40 \fine_code_o_reg[1]  ( .D(n157), .CK(clk_i), .R(n13), .Q(
        fine_code_o[1]) );
  DFFRPQ_X1M_A9TR40 \fine_code_o_reg[2]  ( .D(n156), .CK(clk_i), .R(n13), .Q(
        fine_code_o[2]) );
  DFFRPQ_X1M_A9TR40 \fine_code_o_reg[3]  ( .D(n155), .CK(clk_i), .R(n13), .Q(
        fine_code_o[3]) );
  DFFRPQ_X2M_A9TR40 \medium_code_o_reg[0]  ( .D(n179), .CK(clk_i), .R(n12), 
        .Q(medium_code_o[0]) );
  DFFRPQ_X2M_A9TR40 \medium_code_o_reg[3]  ( .D(n177), .CK(clk_i), .R(n12), 
        .Q(medium_code_o[3]) );
  DFFRPQ_X2M_A9TR40 \fine_code_o_reg[0]  ( .D(n158), .CK(clk_i), .R(n13), .Q(
        fine_code_o[0]) );
  DFFRPQ_X2M_A9TR40 \medium_code_o_reg[1]  ( .D(n175), .CK(clk_i), .R(n12), 
        .Q(medium_code_o[1]) );
  DFFRPQ_X2M_A9TR40 \medium_code_o_reg[2]  ( .D(n176), .CK(clk_i), .R(n12), 
        .Q(medium_code_o[2]) );
  OR2_X1M_A9TR40 U3 ( .A(n10), .B(n11), .Y(n1) );
  OR2_X1M_A9TR40 U4 ( .A(n15), .B(n5), .Y(n2) );
  INV_X3M_A9TR40 U5 ( .A(n17), .Y(n15) );
  OAI221_X0P7M_A9TR40 U6 ( .A0(n125), .A1(n131), .B0(n14), .B1(n132), .C0(n133), .Y(n155) );
  NOR4BB_X2M_A9TR40 U7 ( .AN(n46), .BN(n81), .C(medium_code_o[2]), .D(
        medium_code_o[3]), .Y(n111) );
  NOR2_X1A_A9TR40 U8 ( .A(medium_code_o[3]), .B(n23), .Y(n24) );
  NOR2_X1P4B_A9TR40 U9 ( .A(medium_code_o[1]), .B(medium_code_o[0]), .Y(n22)
         );
  AO21_X0P7M_A9TR40 U10 ( .A0(medium_code_o[0]), .A1(medium_code_o[1]), .B0(
        n22), .Y(N132) );
  MXT2_X0P7M_A9TR40 U11 ( .A(n72), .B(medium_therm_o[4]), .S0(n73), .Y(n169)
         );
  MXT2_X0P7M_A9TR40 U12 ( .A(n66), .B(medium_therm_o[8]), .S0(n67), .Y(n170)
         );
  MXT2_X0P7M_A9TR40 U13 ( .A(n77), .B(medium_therm_o[3]), .S0(n78), .Y(n168)
         );
  MXT2_X0P7M_A9TR40 U14 ( .A(n108), .B(medium_therm_o[2]), .S0(n109), .Y(n160)
         );
  AOI221_X1P4M_A9TR40 U15 ( .A0(n94), .A1(n8), .B0(n58), .B1(n82), .C0(n15), 
        .Y(n93) );
  INV_X1M_A9TR40 U16 ( .A(medium_code_o[3]), .Y(n33) );
  MXT2_X0P7M_A9TR40 U17 ( .A(n112), .B(medium_therm_o[1]), .S0(n113), .Y(n159)
         );
  AND2_X1M_A9TR40 U18 ( .A(n38), .B(n39), .Y(n30) );
  AND2_X0P7M_A9TR40 U19 ( .A(n27), .B(n17), .Y(n38) );
  NOR2_X2A_A9TR40 U20 ( .A(n95), .B(n96), .Y(n48) );
  AOI211_X2M_A9TR40 U21 ( .A0(n62), .A1(n9), .B0(n15), .C0(n63), .Y(n61) );
  NOR3_X1A_A9TR40 U22 ( .A(n64), .B(medium_code_o[1]), .C(medium_code_o[0]), 
        .Y(n63) );
  NOR2_X0P5A_A9TR40 U23 ( .A(n3), .B(n2), .Y(n90) );
  INV_X0P5B_A9TR40 U24 ( .A(n91), .Y(n4) );
  NOR2_X0P5A_A9TR40 U25 ( .A(n45), .B(n4), .Y(n5) );
  INV_X0P5B_A9TR40 U26 ( .A(n82), .Y(n6) );
  INV_X0P5B_A9TR40 U27 ( .A(n53), .Y(n7) );
  NOR2_X0P5A_A9TR40 U28 ( .A(n6), .B(n7), .Y(n3) );
  MXT2_X0P5M_A9TR40 U29 ( .A(n89), .B(medium_therm_o[11]), .S0(n90), .Y(n165)
         );
  NOR3_X3M_A9TR40 U30 ( .A(n33), .B(medium_code_o[2]), .C(n41), .Y(n53) );
  XOR2_X1P4M_A9TR40 U31 ( .A(medium_code_o[4]), .B(n24), .Y(N135) );
  OR2_X1M_A9TR40 U32 ( .A(lock_i), .B(cfg_locked_o), .Y(n45) );
  INV_X1M_A9TR40 U33 ( .A(n45), .Y(n8) );
  INV_X3M_A9TR40 U34 ( .A(n45), .Y(n9) );
  NAND3_X0P5M_A9TR40 U35 ( .A(n59), .B(n9), .C(n70), .Y(n86) );
  AOI211_X1M_A9TR40 U36 ( .A0(n74), .A1(n9), .B0(n16), .C0(n75), .Y(n73) );
  AOI211_X1M_A9TR40 U37 ( .A0(n110), .A1(n9), .B0(n15), .C0(n111), .Y(n109) );
  AOI211_X1M_A9TR40 U38 ( .A0(n68), .A1(n9), .B0(n69), .C0(n15), .Y(n67) );
  AOI211_X1M_A9TR40 U39 ( .A0(n79), .A1(n9), .B0(n15), .C0(n80), .Y(n78) );
  AOI211_X1M_A9TR40 U40 ( .A0(n114), .A1(n9), .B0(n15), .C0(n115), .Y(n113) );
  NOR2_X0P7B_A9TR40 U41 ( .A(n8), .B(n15), .Y(n180) );
  NOR2_X0P5M_A9TR40 U42 ( .A(fine_code_o[2]), .B(n205), .Y(n10) );
  NOR2_X0P5A_A9TR40 U43 ( .A(n198), .B(n205), .Y(n11) );
  NOR2_X2A_A9TR40 U44 ( .A(n131), .B(n205), .Y(n136) );
  NOR2_X1P4B_A9TR40 U45 ( .A(n198), .B(fine_code_o[2]), .Y(n205) );
  NOR2_X2A_A9TR40 U46 ( .A(n96), .B(N132), .Y(n65) );
  NOR2_X1A_A9TR40 U47 ( .A(n116), .B(medium_code_o[0]), .Y(N416) );
  NAND4_X1M_A9TR40 U48 ( .A(n36), .B(n25), .C(n33), .D(n31), .Y(n116) );
  NAND2_X1A_A9TR40 U49 ( .A(n22), .B(n25), .Y(n23) );
  NOR2_X2A_A9TR40 U50 ( .A(n36), .B(n26), .Y(n82) );
  INV_X1M_A9TR40 U51 ( .A(medium_code_o[0]), .Y(n26) );
  INV_X1M_A9TR40 U52 ( .A(medium_code_o[1]), .Y(n36) );
  NOR2B_X2M_A9TR40 U53 ( .AN(n38), .B(n39), .Y(n29) );
  NOR2_X1P4B_A9TR40 U54 ( .A(medium_code_o[4]), .B(n117), .Y(N425) );
  NAND2_X1A_A9TR40 U55 ( .A(n192), .B(n193), .Y(n144) );
  NOR3_X1A_A9TR40 U56 ( .A(n76), .B(medium_code_o[1]), .C(medium_code_o[0]), 
        .Y(n75) );
  AOI211_X2M_A9TR40 U57 ( .A0(N429), .A1(n142), .B0(n16), .C0(n204), .Y(n203)
         );
  NOR2_X2A_A9TR40 U58 ( .A(n135), .B(n40), .Y(n142) );
  NOR2_X1P4B_A9TR40 U59 ( .A(n95), .B(N133), .Y(n54) );
  NOR2_X1P4B_A9TR40 U60 ( .A(N133), .B(N132), .Y(n70) );
  OAI21_X1P4M_A9TR40 U61 ( .A0(n22), .A1(n25), .B0(n23), .Y(N133) );
  NOR3_X1P4M_A9TR40 U62 ( .A(n196), .B(fine_code_o[2]), .C(n131), .Y(N435) );
  AOI221_X1P4M_A9TR40 U63 ( .A0(n99), .A1(n9), .B0(n100), .B1(n47), .C0(n15), 
        .Y(n98) );
  AOI221_X1P4M_A9TR40 U64 ( .A0(n104), .A1(n9), .B0(n100), .B1(n53), .C0(n15), 
        .Y(n103) );
  AOI221_X1P4M_A9TR40 U65 ( .A0(n107), .A1(n9), .B0(n100), .B1(n58), .C0(n15), 
        .Y(n106) );
  NOR2_X1P4M_A9TR40 U66 ( .A(n26), .B(medium_code_o[1]), .Y(n100) );
  AOI221_X1P4M_A9TR40 U67 ( .A0(n44), .A1(n9), .B0(n46), .B1(n47), .C0(n15), 
        .Y(n43) );
  AOI221_X1P4M_A9TR40 U68 ( .A0(n52), .A1(n9), .B0(n53), .B1(n46), .C0(n15), 
        .Y(n51) );
  AOI221_X1P4M_A9TR40 U69 ( .A0(n57), .A1(n9), .B0(n58), .B1(n46), .C0(n15), 
        .Y(n56) );
  NOR2_X1P4B_A9TR40 U70 ( .A(n36), .B(medium_code_o[0]), .Y(n46) );
  NOR3BB_X1P4M_A9TR40 U71 ( .AN(medium_code_o[0]), .BN(n71), .C(N134), .Y(n59)
         );
  AND3_X1M_A9TR40 U72 ( .A(N134), .B(n71), .C(medium_code_o[0]), .Y(n49) );
  XNOR2_X3M_A9TR40 U73 ( .A(medium_code_o[3]), .B(n23), .Y(N134) );
  OAI31_X1M_A9TR40 U74 ( .A0(n84), .A1(n16), .A2(n41), .B0(n85), .Y(n167) );
  NOR2_X0P7M_A9TR40 U75 ( .A(n41), .B(n25), .Y(n101) );
  NOR3_X1M_A9TR40 U76 ( .A(n41), .B(n116), .C(n26), .Y(n115) );
  NAND4_X2M_A9TR40 U77 ( .A(medium_inc_i), .B(n8), .C(n117), .D(n31), .Y(n41)
         );
  NOR2_X0P5M_A9TR40 U78 ( .A(fine_code_o[2]), .B(n130), .Y(n128) );
  NOR2_X0P5B_A9TR40 U79 ( .A(n129), .B(n193), .Y(n143) );
  INV_X0P6B_A9TR40 U80 ( .A(n136), .Y(n132) );
  NAND4_X0P7M_A9TR40 U81 ( .A(n143), .B(n136), .C(n123), .D(n9), .Y(n137) );
  INV_X0P7B_A9TR40 U82 ( .A(n1), .Y(n129) );
  AOI21B_X1M_A9TR40 U83 ( .A0(n130), .A1(n134), .B0N(n118), .Y(n125) );
  NAND3_X0P7M_A9TR40 U84 ( .A(n132), .B(n126), .C(n142), .Y(n189) );
  OAI22_X0P7M_A9TR40 U85 ( .A0(n118), .A1(n121), .B0(n119), .B1(n122), .Y(n157) );
  XNOR2_X0P7M_A9TR40 U86 ( .A(n123), .B(n124), .Y(n122) );
  NAND2_X1A_A9TR40 U87 ( .A(n186), .B(n196), .Y(n124) );
  NAND3_X0P5M_A9TR40 U88 ( .A(n8), .B(n132), .C(n123), .Y(n199) );
  NAND3_X1M_A9TR40 U89 ( .A(fine_code_o[2]), .B(n132), .C(n142), .Y(n183) );
  NOR2_X1A_A9TR40 U90 ( .A(n141), .B(fine_code_o[3]), .Y(N429) );
  OAI22_X0P7M_A9TR40 U91 ( .A0(n125), .A1(n126), .B0(n119), .B1(n127), .Y(n156) );
  NAND2_X1A_A9TR40 U92 ( .A(fine_code_o[0]), .B(n121), .Y(n196) );
  INV_X1M_A9TR40 U93 ( .A(fine_code_o[3]), .Y(n131) );
  OAI31_X0P7M_A9TR40 U94 ( .A0(n140), .A1(n141), .A2(n131), .B0(
        fine_therm_o[8]), .Y(n139) );
  NAND2_X1A_A9TR40 U95 ( .A(fine_code_o[1]), .B(fine_code_o[0]), .Y(n130) );
  BUF_X2M_A9TR40 U96 ( .A(n20), .Y(n18) );
  BUFH_X1M_A9TR40 U97 ( .A(n20), .Y(n17) );
  BUFH_X1M_A9TR40 U98 ( .A(n21), .Y(n20) );
  INV_X2M_A9TR40 U99 ( .A(n18), .Y(n14) );
  INV_X1M_A9TR40 U100 ( .A(n17), .Y(n16) );
  BUF_X3M_A9TR40 U101 ( .A(n206), .Y(n12) );
  BUF_X3M_A9TR40 U102 ( .A(n206), .Y(n13) );
  BUFH_X1M_A9TR40 U103 ( .A(n20), .Y(n19) );
  NAND2_X1A_A9TR40 U104 ( .A(medium_dec_i), .B(n84), .Y(n39) );
  INV_X2M_A9TR40 U105 ( .A(fine_code_o[0]), .Y(n120) );
  INV_X1M_A9TR40 U106 ( .A(medium_code_o[2]), .Y(n25) );
  INV_X1M_A9TR40 U107 ( .A(init_i), .Y(n21) );
  ADDH_X1M_A9TR40 U108 ( .A(medium_code_o[2]), .B(\add_72/carry[2] ), .CO(
        \add_72/carry[3] ), .S(N109) );
  ADDH_X1M_A9TR40 U109 ( .A(medium_code_o[1]), .B(medium_code_o[0]), .CO(
        \add_72/carry[2] ), .S(N108) );
  ADDH_X1M_A9TR40 U110 ( .A(medium_code_o[3]), .B(\add_72/carry[3] ), .CO(
        \add_72/carry[4] ), .S(N110) );
  NOR3BB_X1P4M_A9TR40 U111 ( .AN(N131), .BN(n71), .C(N134), .Y(n83) );
  AND3_X0P7M_A9TR40 U112 ( .A(N134), .B(N131), .C(n71), .Y(n88) );
  AND2_X0P5M_A9TR40 U113 ( .A(n59), .B(n48), .Y(n57) );
  NOR2_X1P4B_A9TR40 U114 ( .A(n39), .B(N135), .Y(n71) );
  NOR4BB_X0P7M_A9TR40 U115 ( .AN(n81), .BN(n82), .C(medium_code_o[2]), .D(
        medium_code_o[3]), .Y(n80) );
  NAND3_X0P7M_A9TR40 U116 ( .A(medium_code_o[2]), .B(n82), .C(medium_code_o[3]), .Y(n117) );
  OAI211_X2M_A9TR40 U117 ( .A0(n40), .A1(n39), .B0(n41), .C0(n18), .Y(n27) );
  NOR2XB_X2M_A9TR40 U118 ( .BN(fine_dec_i), .A(N429), .Y(n123) );
  NOR2_X2A_A9TR40 U119 ( .A(n14), .B(n123), .Y(n134) );
  OA21A1OI2_X3M_A9TR40 U120 ( .A0(n135), .A1(n136), .B0(n134), .C0(n180), .Y(
        n118) );
  INV_X0P5B_A9TR40 U121 ( .A(medium_code_o[0]), .Y(N131) );
  XOR2_X0P5M_A9TR40 U122 ( .A(\add_72/carry[4] ), .B(medium_code_o[4]), .Y(
        N111) );
  INV_X0P5B_A9TR40 U123 ( .A(por_n_i), .Y(n206) );
  OAI21_X0P5M_A9TR40 U124 ( .A0(n26), .A1(n27), .B0(n28), .Y(n179) );
  AOI22_X0P5M_A9TR40 U125 ( .A0(N131), .A1(n29), .B0(N131), .B1(n30), .Y(n28)
         );
  OAI21_X0P5M_A9TR40 U126 ( .A0(n27), .A1(n31), .B0(n32), .Y(n178) );
  AOI22_X0P5M_A9TR40 U127 ( .A0(N135), .A1(n29), .B0(N111), .B1(n30), .Y(n32)
         );
  OAI21_X0P5M_A9TR40 U128 ( .A0(n33), .A1(n27), .B0(n34), .Y(n177) );
  AOI22_X0P5M_A9TR40 U129 ( .A0(N134), .A1(n29), .B0(N110), .B1(n30), .Y(n34)
         );
  OAI21_X0P5M_A9TR40 U130 ( .A0(n25), .A1(n27), .B0(n35), .Y(n176) );
  AOI22_X0P5M_A9TR40 U131 ( .A0(N133), .A1(n29), .B0(N109), .B1(n30), .Y(n35)
         );
  OAI21_X0P5M_A9TR40 U132 ( .A0(n36), .A1(n27), .B0(n37), .Y(n175) );
  AOI22_X0P5M_A9TR40 U133 ( .A0(N132), .A1(n29), .B0(N108), .B1(n30), .Y(n37)
         );
  MX2_X0P5B_A9TR40 U134 ( .A(n42), .B(medium_therm_o[14]), .S0(n43), .Y(n174)
         );
  NOR2_X0P5A_A9TR40 U135 ( .A(n15), .B(n44), .Y(n42) );
  AND2_X0P5B_A9TR40 U136 ( .A(n48), .B(n49), .Y(n44) );
  MX2_X0P5B_A9TR40 U137 ( .A(n50), .B(medium_therm_o[10]), .S0(n51), .Y(n173)
         );
  NOR2_X0P5A_A9TR40 U138 ( .A(n15), .B(n52), .Y(n50) );
  AND2_X0P5B_A9TR40 U139 ( .A(n54), .B(n49), .Y(n52) );
  MX2_X0P5B_A9TR40 U140 ( .A(n55), .B(medium_therm_o[6]), .S0(n56), .Y(n172)
         );
  NOR2_X0P5A_A9TR40 U141 ( .A(n14), .B(n57), .Y(n55) );
  MX2_X0P5B_A9TR40 U142 ( .A(n60), .B(medium_therm_o[12]), .S0(n61), .Y(n171)
         );
  NOR2_X0P5A_A9TR40 U143 ( .A(n14), .B(n62), .Y(n60) );
  AND2_X0P5B_A9TR40 U144 ( .A(n65), .B(n49), .Y(n62) );
  AND3_X0P5M_A9TR40 U145 ( .A(n53), .B(n36), .C(n26), .Y(n69) );
  NOR2_X0P5A_A9TR40 U146 ( .A(n14), .B(n68), .Y(n66) );
  AND2_X0P5B_A9TR40 U147 ( .A(n70), .B(n49), .Y(n68) );
  NOR2_X0P5A_A9TR40 U148 ( .A(n14), .B(n74), .Y(n72) );
  AND2_X0P5B_A9TR40 U149 ( .A(n65), .B(n59), .Y(n74) );
  NOR2_X0P5A_A9TR40 U150 ( .A(n14), .B(n79), .Y(n77) );
  AND2_X0P5B_A9TR40 U151 ( .A(n83), .B(n54), .Y(n79) );
  NAND3_X0P5A_A9TR40 U152 ( .A(n86), .B(n18), .C(medium_therm_o[0]), .Y(n85)
         );
  NOR3BB_X0P5M_A9TR40 U153 ( .AN(n17), .BN(medium_therm_o[15]), .C(n87), .Y(
        n166) );
  AND3_X0P5M_A9TR40 U154 ( .A(n88), .B(n48), .C(n9), .Y(n87) );
  NOR2_X0P5A_A9TR40 U155 ( .A(n14), .B(n91), .Y(n89) );
  AND2_X0P5B_A9TR40 U156 ( .A(n88), .B(n54), .Y(n91) );
  MX2_X0P5B_A9TR40 U157 ( .A(n92), .B(medium_therm_o[7]), .S0(n93), .Y(n164)
         );
  NOR2_X0P5A_A9TR40 U158 ( .A(n14), .B(n94), .Y(n92) );
  AND2_X0P5B_A9TR40 U159 ( .A(n83), .B(n48), .Y(n94) );
  MX2_X0P5B_A9TR40 U160 ( .A(n97), .B(medium_therm_o[13]), .S0(n98), .Y(n163)
         );
  INV_X0P5B_A9TR40 U161 ( .A(n64), .Y(n47) );
  NAND2_X0P5A_A9TR40 U162 ( .A(n101), .B(medium_code_o[3]), .Y(n64) );
  NOR2_X0P5A_A9TR40 U163 ( .A(n14), .B(n99), .Y(n97) );
  AND2_X0P5B_A9TR40 U164 ( .A(n88), .B(n65), .Y(n99) );
  MX2_X0P5B_A9TR40 U165 ( .A(n102), .B(medium_therm_o[9]), .S0(n103), .Y(n162)
         );
  NOR2_X0P5A_A9TR40 U166 ( .A(n14), .B(n104), .Y(n102) );
  AND2_X0P5B_A9TR40 U167 ( .A(n88), .B(n70), .Y(n104) );
  MX2_X0P5B_A9TR40 U168 ( .A(n105), .B(medium_therm_o[5]), .S0(n106), .Y(n161)
         );
  INV_X0P5B_A9TR40 U169 ( .A(n76), .Y(n58) );
  NAND2_X0P5A_A9TR40 U170 ( .A(n101), .B(n33), .Y(n76) );
  NOR2_X0P5A_A9TR40 U171 ( .A(n14), .B(n107), .Y(n105) );
  AND2_X0P5B_A9TR40 U172 ( .A(n83), .B(n65), .Y(n107) );
  INV_X0P5B_A9TR40 U173 ( .A(N133), .Y(n96) );
  INV_X0P5B_A9TR40 U174 ( .A(n41), .Y(n81) );
  NOR2_X0P5A_A9TR40 U175 ( .A(n14), .B(n110), .Y(n108) );
  AND2_X0P5B_A9TR40 U176 ( .A(n59), .B(n54), .Y(n110) );
  INV_X0P5B_A9TR40 U177 ( .A(N132), .Y(n95) );
  NOR2_X0P5A_A9TR40 U178 ( .A(n14), .B(n114), .Y(n112) );
  AND2_X0P5B_A9TR40 U179 ( .A(n83), .B(n70), .Y(n114) );
  INV_X0P5B_A9TR40 U180 ( .A(N416), .Y(n84) );
  MXIT2_X0P5M_A9TR40 U181 ( .A(n118), .B(n119), .S0(n120), .Y(n158) );
  MXIT2_X0P5M_A9TR40 U182 ( .A(n128), .B(n129), .S0(n123), .Y(n127) );
  NAND2_X0P5A_A9TR40 U183 ( .A(n118), .B(n18), .Y(n119) );
  NAND4BB_X0P5M_A9TR40 U184 ( .AN(n130), .BN(n126), .C(n118), .D(n134), .Y(
        n133) );
  OAI21_X0P5M_A9TR40 U185 ( .A0(fine_code_o[0]), .A1(n137), .B0(n138), .Y(n154) );
  NOR2_X0P5A_A9TR40 U186 ( .A(n14), .B(fine_therm_o[9]), .Y(n138) );
  OAI211_X0P5M_A9TR40 U187 ( .A0(n120), .A1(n137), .B0(n18), .C0(n139), .Y(
        n153) );
  INV_X0P5B_A9TR40 U188 ( .A(n142), .Y(n140) );
  OAI211_X0P5M_A9TR40 U189 ( .A0(n144), .A1(n181), .B0(n18), .C0(n182), .Y(
        n152) );
  OAI21_X0P5M_A9TR40 U190 ( .A0(n130), .A1(n183), .B0(fine_therm_o[7]), .Y(
        n182) );
  NAND2_X0P5A_A9TR40 U191 ( .A(n129), .B(n120), .Y(n181) );
  OAI211_X0P5M_A9TR40 U192 ( .A0(n144), .A1(n184), .B0(n18), .C0(n185), .Y(
        n151) );
  OAI21_X0P5M_A9TR40 U193 ( .A0(n183), .A1(n186), .B0(fine_therm_o[6]), .Y(
        n185) );
  NAND2_X0P5A_A9TR40 U194 ( .A(fine_code_o[0]), .B(n129), .Y(n184) );
  OAI211_X0P5M_A9TR40 U195 ( .A0(n144), .A1(n187), .B0(n18), .C0(n188), .Y(
        n150) );
  OAI21_X0P5M_A9TR40 U196 ( .A0(n130), .A1(n189), .B0(fine_therm_o[3]), .Y(
        n188) );
  NAND2_X0P5A_A9TR40 U197 ( .A(n1), .B(n120), .Y(n187) );
  OAI211_X0P5M_A9TR40 U198 ( .A0(n144), .A1(n190), .B0(n18), .C0(n191), .Y(
        n149) );
  OAI21_X0P5M_A9TR40 U199 ( .A0(n186), .A1(n189), .B0(fine_therm_o[2]), .Y(
        n191) );
  NAND2_X0P5A_A9TR40 U200 ( .A(n1), .B(fine_code_o[0]), .Y(n190) );
  OAI211_X0P5M_A9TR40 U201 ( .A0(fine_code_o[0]), .A1(n194), .B0(n195), .C0(
        n18), .Y(n148) );
  OAI21_X0P5M_A9TR40 U202 ( .A0(n183), .A1(n196), .B0(fine_therm_o[5]), .Y(
        n195) );
  OAI211_X0P5M_A9TR40 U203 ( .A0(n120), .A1(n194), .B0(n197), .C0(n18), .Y(
        n147) );
  OAI21_X0P5M_A9TR40 U204 ( .A0(n198), .A1(n183), .B0(fine_therm_o[4]), .Y(
        n197) );
  NAND3_X0P5A_A9TR40 U205 ( .A(n129), .B(n124), .C(n192), .Y(n194) );
  OAI211_X0P5M_A9TR40 U206 ( .A0(n199), .A1(n200), .B0(n19), .C0(n201), .Y(
        n146) );
  OAI21_X0P5M_A9TR40 U207 ( .A0(n189), .A1(n196), .B0(fine_therm_o[1]), .Y(
        n201) );
  INV_X0P5B_A9TR40 U208 ( .A(fine_code_o[2]), .Y(n126) );
  NAND2_X0P5A_A9TR40 U209 ( .A(n143), .B(n120), .Y(n200) );
  MXIT2_X0P5M_A9TR40 U210 ( .A(n134), .B(n202), .S0(n203), .Y(n145) );
  AND3_X0P5M_A9TR40 U211 ( .A(n192), .B(n143), .C(fine_code_o[0]), .Y(n204) );
  INV_X0P5B_A9TR40 U212 ( .A(n124), .Y(n193) );
  NAND2_X0P5A_A9TR40 U213 ( .A(fine_code_o[1]), .B(n120), .Y(n186) );
  INV_X0P5B_A9TR40 U214 ( .A(n199), .Y(n192) );
  INV_X0P5B_A9TR40 U215 ( .A(n8), .Y(n40) );
  INV_X0P5B_A9TR40 U216 ( .A(fine_inc_i), .Y(n135) );
  INV_X0P5B_A9TR40 U217 ( .A(fine_therm_o[0]), .Y(n202) );
  INV_X0P5B_A9TR40 U218 ( .A(n116), .Y(medium_too_low_for_backoff_o) );
  INV_X0P5B_A9TR40 U219 ( .A(n205), .Y(n141) );
  NAND2_X0P5A_A9TR40 U220 ( .A(n121), .B(n120), .Y(n198) );
  INV_X0P5B_A9TR40 U221 ( .A(fine_code_o[1]), .Y(n121) );
  INV_X0P5B_A9TR40 U222 ( .A(medium_code_o[4]), .Y(n31) );
endmodule


module ftc_q_sampler ( clk_i, por_n_i, q_final_i, sample_1_i, sample_2_i, 
        q_sample_1_o, q_sample_2_o, class_valid_o, q_class_o );
  output [1:0] q_class_o;
  input clk_i, por_n_i, q_final_i, sample_1_i, sample_2_i;
  output q_sample_1_o, q_sample_2_o, class_valid_o;
  wire   n1, n3, n6, n7, n8, n9, n2, n4, n5, n10;

  DFFRPQ_X1M_A9TR40 q_sample_2_o_reg ( .D(n8), .CK(clk_i), .R(n5), .Q(
        q_sample_2_o) );
  DFFRPQ_X1M_A9TR40 class_valid_o_reg ( .D(sample_2_i), .CK(clk_i), .R(n5), 
        .Q(class_valid_o) );
  DFFSQ_X1M_A9TR40 \q_class_o_reg[1]  ( .D(n7), .CK(clk_i), .SN(por_n_i), .Q(
        q_class_o[1]) );
  DFFRPQ_X1M_A9TR40 \q_class_o_reg[0]  ( .D(n6), .CK(clk_i), .R(n5), .Q(
        q_class_o[0]) );
  DFFRPQ_X1M_A9TR40 q_sample_1_o_reg ( .D(n9), .CK(clk_i), .R(n5), .Q(
        q_sample_1_o) );
  INV_X1M_A9TR40 U3 ( .A(sample_2_i), .Y(n4) );
  NOR2_X2A_A9TR40 U4 ( .A(n4), .B(n10), .Y(n1) );
  OAI22BB_X1M_A9TR40 U5 ( .A0(sample_1_i), .A1(n2), .B0N(q_final_i), .B1N(
        sample_1_i), .Y(n9) );
  INV_X1M_A9TR40 U6 ( .A(q_sample_1_o), .Y(n2) );
  INV_X1M_A9TR40 U7 ( .A(q_final_i), .Y(n10) );
  AO1B2_X1M_A9TR40 U8 ( .B0(q_class_o[1]), .B1(n4), .A0N(n3), .Y(n7) );
  AOI32_X1M_A9TR40 U9 ( .A0(sample_2_i), .A1(n10), .A2(q_sample_1_o), .B0(n1), 
        .B1(n2), .Y(n3) );
  AO21_X1M_A9TR40 U10 ( .A0(q_sample_2_o), .A1(n4), .B0(n1), .Y(n8) );
  AO22_X1M_A9TR40 U11 ( .A0(n1), .A1(q_sample_1_o), .B0(q_class_o[0]), .B1(n4), 
        .Y(n6) );
  INV_X1M_A9TR40 U12 ( .A(por_n_i), .Y(n5) );
endmodule


module ftc_operation_sequencer ( cal_clk_i, ctrl_por_n_i, req_i, cmd_i, 
        medium_inc_i, medium_dec_i, fine_inc_i, fine_dec_i, q_final_i, 
        sense_dff_reset_o, sense_s_clk_o, cfg_medium_inc_o, cfg_medium_dec_o, 
        cfg_fine_inc_o, cfg_fine_dec_o, busy_o, done_o, probe_done_o, 
        q_class_o, q_class_valid_o, q_sample_1_event_o, q_sample_2_event_o, 
        config_update_event_o, probe_start_event_o );
  input [1:0] cmd_i;
  output [1:0] q_class_o;
  input cal_clk_i, ctrl_por_n_i, req_i, medium_inc_i, medium_dec_i, fine_inc_i,
         fine_dec_i, q_final_i;
  output sense_dff_reset_o, sense_s_clk_o, cfg_medium_inc_o, cfg_medium_dec_o,
         cfg_fine_inc_o, cfg_fine_dec_o, busy_o, done_o, probe_done_o,
         q_class_valid_o, q_sample_1_event_o, q_sample_2_event_o,
         config_update_event_o, probe_start_event_o;
  wire   sample_1_fire, sample_2_fire, sampler_class_valid, N43, N55, N56, N57,
         N58, N59, N60, N61, n3, n7, n8, n9, n10, n11, n13, n15, n16, n18, n19,
         n20, n21, n23, n24, n27, n28, n31, n32, n34, n35, n36, n37, n38, n39,
         n41, n42, n43, n44, n45, n46, n47, n48, n49, n50, n51, n53, n1, n2,
         n4, n5, n6, n12, n14, n17, n22, n25, n26, n29, n30, n33, n40, n52,
         n54, n55, n56;
  wire   [1:0] active_cmd_q;
  wire   [3:0] probe_count_q;

  ftc_q_sampler u_q_sampler ( .clk_i(cal_clk_i), .por_n_i(ctrl_por_n_i), 
        .q_final_i(q_final_i), .sample_1_i(sample_1_fire), .sample_2_i(
        sample_2_fire), .class_valid_o(sampler_class_valid), .q_class_o(
        q_class_o) );
  DFFRPQ_X1M_A9TR40 cfg_fine_inc_o_reg ( .D(N57), .CK(cal_clk_i), .R(n2), .Q(
        cfg_fine_inc_o) );
  DFFSQ_X1M_A9TR40 sense_dff_reset_o_reg ( .D(n42), .CK(cal_clk_i), .SN(
        ctrl_por_n_i), .Q(sense_dff_reset_o) );
  DFFRPQ_X1M_A9TR40 cfg_fine_dec_o_reg ( .D(N58), .CK(cal_clk_i), .R(n2), .Q(
        cfg_fine_dec_o) );
  DFFRPQ_X1M_A9TR40 probe_done_o_reg ( .D(n17), .CK(cal_clk_i), .R(n2), .Q(
        probe_done_o) );
  DFFRPQ_X1M_A9TR40 sense_s_clk_o_reg ( .D(n43), .CK(cal_clk_i), .R(n56), .Q(
        sense_s_clk_o) );
  DFFRPQ_X1M_A9TR40 q_class_valid_o_reg ( .D(n45), .CK(cal_clk_i), .R(n56), 
        .Q(q_class_valid_o) );
  DFFRPQ_X1M_A9TR40 \probe_count_q_reg[0]  ( .D(n51), .CK(cal_clk_i), .R(n56), 
        .Q(probe_count_q[0]) );
  DFFRPQ_X1M_A9TR40 \active_cmd_q_reg[1]  ( .D(n48), .CK(cal_clk_i), .R(n56), 
        .Q(active_cmd_q[1]) );
  DFFRPQ_X1M_A9TR40 \probe_count_q_reg[3]  ( .D(n44), .CK(cal_clk_i), .R(n56), 
        .Q(probe_count_q[3]) );
  DFFRPQ_X1M_A9TR40 cfg_medium_inc_o_reg ( .D(N55), .CK(cal_clk_i), .R(n56), 
        .Q(cfg_medium_inc_o) );
  DFFRPQ_X1M_A9TR40 cfg_medium_dec_o_reg ( .D(N56), .CK(cal_clk_i), .R(n56), 
        .Q(cfg_medium_dec_o) );
  DFFRPQ_X1M_A9TR40 config_update_event_o_reg ( .D(n53), .CK(cal_clk_i), .R(
        n56), .Q(config_update_event_o) );
  DFFRPQ_X1M_A9TR40 probe_start_event_o_reg ( .D(N43), .CK(cal_clk_i), .R(n56), 
        .Q(probe_start_event_o) );
  DFFRPQ_X1M_A9TR40 q_sample_2_event_o_reg ( .D(N61), .CK(cal_clk_i), .R(n56), 
        .Q(q_sample_2_event_o) );
  DFFRPQ_X1M_A9TR40 q_sample_1_event_o_reg ( .D(N60), .CK(cal_clk_i), .R(n56), 
        .Q(q_sample_1_event_o) );
  DFFRPQ_X1M_A9TR40 \active_cmd_q_reg[0]  ( .D(n47), .CK(cal_clk_i), .R(n56), 
        .Q(active_cmd_q[0]) );
  DFFRPQ_X1M_A9TR40 done_o_reg ( .D(N59), .CK(cal_clk_i), .R(n56), .Q(done_o)
         );
  DFFRPQ_X1M_A9TR40 \probe_count_q_reg[1]  ( .D(n46), .CK(cal_clk_i), .R(n2), 
        .Q(probe_count_q[1]) );
  DFFRPQ_X2M_A9TR40 busy_o_reg ( .D(n49), .CK(cal_clk_i), .R(n56), .Q(busy_o)
         );
  DFFRPQ_X2M_A9TR40 \probe_count_q_reg[2]  ( .D(n50), .CK(cal_clk_i), .R(n56), 
        .Q(probe_count_q[2]) );
  NOR2_X0P7M_A9TR40 U3 ( .A(n55), .B(probe_count_q[2]), .Y(n1) );
  NOR2_X0P5B_A9TR40 U4 ( .A(n55), .B(probe_count_q[2]), .Y(n9) );
  XNOR2_X0P5M_A9TR40 U5 ( .A(n21), .B(probe_count_q[2]), .Y(n34) );
  NAND2_X0P5A_A9TR40 U6 ( .A(n21), .B(probe_count_q[2]), .Y(n20) );
  NOR2_X0P7B_A9TR40 U7 ( .A(probe_count_q[2]), .B(probe_count_q[1]), .Y(n36)
         );
  INV_X0P6B_A9TR40 U8 ( .A(probe_count_q[2]), .Y(n25) );
  OAI211_X0P5M_A9TR40 U9 ( .A0(probe_count_q[2]), .A1(n33), .B0(n31), .C0(n28), 
        .Y(n49) );
  BUFH_X1M_A9TR40 U10 ( .A(n56), .Y(n2) );
  OAI221_X2M_A9TR40 U11 ( .A0(n36), .A1(n37), .B0(n16), .B1(n30), .C0(n38), 
        .Y(n18) );
  INV_X1M_A9TR40 U12 ( .A(n10), .Y(n33) );
  NOR3_X2A_A9TR40 U13 ( .A(n26), .B(n22), .C(n3), .Y(sample_2_fire) );
  INV_X1M_A9TR40 U14 ( .A(n16), .Y(n22) );
  AOI21_X2M_A9TR40 U15 ( .A0(n52), .A1(active_cmd_q[0]), .B0(n40), .Y(n10) );
  NAND3_X1M_A9TR40 U16 ( .A(n39), .B(n40), .C(req_i), .Y(n28) );
  XNOR2_X0P7M_A9TR40 U17 ( .A(n6), .B(cmd_i[0]), .Y(n39) );
  INV_X1M_A9TR40 U18 ( .A(active_cmd_q[1]), .Y(n52) );
  INV_X1M_A9TR40 U19 ( .A(cmd_i[1]), .Y(n6) );
  NAND3_X1M_A9TR40 U20 ( .A(busy_o), .B(n52), .C(active_cmd_q[0]), .Y(n37) );
  INV_X1M_A9TR40 U21 ( .A(probe_count_q[0]), .Y(n14) );
  NOR2_X1A_A9TR40 U22 ( .A(n14), .B(probe_count_q[3]), .Y(n8) );
  NAND3XXB_X1M_A9TR40 U23 ( .CN(cmd_i[0]), .A(cmd_i[1]), .B(req_i), .Y(n11) );
  INV_X1M_A9TR40 U24 ( .A(probe_count_q[1]), .Y(n55) );
  NAND3_X1M_A9TR40 U25 ( .A(req_i), .B(n6), .C(cmd_i[0]), .Y(n27) );
  INV_X1M_A9TR40 U26 ( .A(n24), .Y(n30) );
  INV_X1M_A9TR40 U27 ( .A(n18), .Y(n4) );
  NOR3_X1A_A9TR40 U28 ( .A(n33), .B(n29), .C(n12), .Y(N60) );
  NOR3_X1A_A9TR40 U29 ( .A(n33), .B(n22), .C(n26), .Y(N61) );
  OA21A1OI2_X1P4M_A9TR40 U30 ( .A0(n55), .A1(n25), .B0(n10), .C0(n5), .Y(n38)
         );
  NOR3_X2A_A9TR40 U31 ( .A(n55), .B(n4), .C(n14), .Y(n21) );
  NAND2_X1A_A9TR40 U32 ( .A(n33), .B(n37), .Y(n24) );
  NOR3_X2A_A9TR40 U33 ( .A(n33), .B(n22), .C(n25), .Y(n13) );
  INV_X1M_A9TR40 U34 ( .A(n28), .Y(n5) );
  OAI22_X1M_A9TR40 U35 ( .A0(n14), .A1(n18), .B0(n4), .B1(n35), .Y(n51) );
  NAND2_X1A_A9TR40 U36 ( .A(n24), .B(n14), .Y(n35) );
  OAI22_X1M_A9TR40 U37 ( .A0(n5), .A1(n52), .B0(n28), .B1(n11), .Y(n48) );
  OAI31_X1M_A9TR40 U38 ( .A0(n37), .A1(n22), .A2(n29), .B0(n41), .Y(N59) );
  OAI22_X1M_A9TR40 U39 ( .A0(n5), .A1(n54), .B0(n27), .B1(n28), .Y(n47) );
  INV_X1M_A9TR40 U40 ( .A(n36), .Y(n29) );
  INV_X1M_A9TR40 U41 ( .A(n9), .Y(n26) );
  INV_X1M_A9TR40 U42 ( .A(n8), .Y(n12) );
  INV_X1M_A9TR40 U43 ( .A(n41), .Y(n17) );
  INV_X1M_A9TR40 U44 ( .A(busy_o), .Y(n40) );
  AOI21_X1M_A9TR40 U45 ( .A0(n30), .A1(n18), .B0(n19), .Y(n44) );
  XOR2_X0P7M_A9TR40 U46 ( .A(n20), .B(probe_count_q[3]), .Y(n19) );
  NOR2_X2A_A9TR40 U47 ( .A(n27), .B(busy_o), .Y(n53) );
  NOR3_X2A_A9TR40 U48 ( .A(n12), .B(n3), .C(n29), .Y(sample_1_fire) );
  NOR2_X2A_A9TR40 U49 ( .A(probe_count_q[3]), .B(probe_count_q[0]), .Y(n16) );
  NAND3_X1M_A9TR40 U50 ( .A(active_cmd_q[1]), .B(n54), .C(busy_o), .Y(n3) );
  AOI211_X1M_A9TR40 U51 ( .A0(n13), .A1(n55), .B0(n40), .C0(n15), .Y(n43) );
  AOI31_X1M_A9TR40 U52 ( .A0(n16), .A1(n55), .A2(n10), .B0(sense_s_clk_o), .Y(
        n15) );
  OAI31_X1M_A9TR40 U53 ( .A0(n22), .A1(n1), .A2(n32), .B0(busy_o), .Y(n31) );
  AOI21_X1M_A9TR40 U54 ( .A0(n10), .A1(probe_count_q[1]), .B0(n25), .Y(n32) );
  OAI31_X1M_A9TR40 U55 ( .A0(n14), .A1(probe_count_q[1]), .A2(n30), .B0(n23), 
        .Y(n46) );
  AO21A1AI2_X1M_A9TR40 U56 ( .A0(n24), .A1(n14), .B0(n4), .C0(probe_count_q[1]), .Y(n23) );
  NAND2_X1A_A9TR40 U57 ( .A(n13), .B(probe_count_q[1]), .Y(n41) );
  NOR2_X1A_A9TR40 U58 ( .A(busy_o), .B(n11), .Y(N43) );
  AOI21_X0P7M_A9TR40 U59 ( .A0(n30), .A1(n18), .B0(n34), .Y(n50) );
  INV_X1M_A9TR40 U60 ( .A(active_cmd_q[0]), .Y(n54) );
  OA1B2_X1M_A9TR40 U61 ( .B0(q_class_valid_o), .B1(sampler_class_valid), .A0N(
        n53), .Y(n45) );
  AO1B2_X0P7M_A9TR40 U62 ( .B0(sense_dff_reset_o), .B1(busy_o), .A0N(n7), .Y(
        n42) );
  AOI32_X1M_A9TR40 U63 ( .A0(n8), .A1(n1), .A2(n10), .B0(n11), .B1(n40), .Y(n7) );
  AND2_X1M_A9TR40 U64 ( .A(medium_inc_i), .B(n53), .Y(N55) );
  AND2_X1M_A9TR40 U65 ( .A(medium_dec_i), .B(n53), .Y(N56) );
  AND2_X1M_A9TR40 U66 ( .A(fine_inc_i), .B(n53), .Y(N57) );
  AND2_X1M_A9TR40 U67 ( .A(fine_dec_i), .B(n53), .Y(N58) );
  INV_X4M_A9TR40 U68 ( .A(ctrl_por_n_i), .Y(n56) );
endmodule


module ftc_cal_fsm ( cal_clk_i, ctrl_por_n_i, cal_start_i, seq_busy_i, 
        seq_done_i, seq_probe_done_i, seq_req_o, seq_cmd_o, seq_medium_inc_o, 
        seq_medium_dec_o, seq_fine_inc_o, seq_fine_dec_o, q_class_i, 
        q_class_valid_i, cfg_at_max_medium_i, cfg_at_min_medium_i, 
        cfg_at_max_fine_i, cfg_medium_too_low_for_backoff_i, cal_busy_o, 
        cal_done_o, cal_fail_o, lock_valid_o, fail_reason_o, fsm_state_o );
  output [1:0] seq_cmd_o;
  input [1:0] q_class_i;
  output [2:0] fail_reason_o;
  output [4:0] fsm_state_o;
  input cal_clk_i, ctrl_por_n_i, cal_start_i, seq_busy_i, seq_done_i,
         seq_probe_done_i, q_class_valid_i, cfg_at_max_medium_i,
         cfg_at_min_medium_i, cfg_at_max_fine_i,
         cfg_medium_too_low_for_backoff_i;
  output seq_req_o, seq_medium_inc_o, seq_medium_dec_o, seq_fine_inc_o,
         seq_fine_dec_o, cal_busy_o, cal_done_o, cal_fail_o, lock_valid_o;
  wire   n191, n1, n2, n3, n4, n6, n7, n8, n9, n10, n12, n14, n15, n18, n19,
         n20, n21, n22, n23, n24, n25, n27, n29, n30, n31, n32, n33, n34, n35,
         n36, n37, n39, n40, n41, n42, n43, n44, n45, n47, n48, n49, n50, n52,
         n53, n54, n55, n58, n59, n60, n61, n62, n63, n64, n65, n66, n67, n68,
         n69, n70, n71, n72, n73, n74, n76, n77, n78, n80, n81, n82, n83, n85,
         n87, n88, n90, n91, n92, n94, n97, n98, n99, n100, n101, n102, n103,
         n104, n105, n107, n108, n110, n113, n121, n122, n123, n127, n128,
         n129, n132, n134, n135, n139, n141, n143, n144, n145, n146, n147,
         n148, n149, n150, n152, n153, n154, n156, n157, n158, n159, n161,
         n162, n163, n164, n165, n166, n167, n168, n169, n170, n171, n172,
         n173, n174, n175, n176, n177, n178, n179, n180, n181, n182, n183,
         n184, n185, n186, n11, n13, n16, n17, n26, n28, n38, n46, n51, n56,
         n57, n75, n79, n84, n86, n89, n93, n95, n96, n106, n109, n111, n112,
         n114, n115, n116, n117, n118, n119, n120, n124, n125, n126, n130,
         n131, n133, n136, n137, n138, n140, n142, n151, n155, n160, n187,
         n188, n189, n190;
  wire   [1:0] coarse_probe_a_result_q;
  wire   [1:0] coarse_probe_b_result_q;
  wire   [1:0] fine_probe_result_q;

  DFFRPQ_X1M_A9TR40 seq_fine_dec_q_reg ( .D(n165), .CK(cal_clk_i), .R(n13), 
        .Q(seq_fine_dec_o) );
  DFFRPQ_X1M_A9TR40 seq_fine_inc_q_reg ( .D(n166), .CK(cal_clk_i), .R(n13), 
        .Q(seq_fine_inc_o) );
  DFFRPQ_X1M_A9TR40 seq_medium_dec_q_reg ( .D(n167), .CK(cal_clk_i), .R(n13), 
        .Q(seq_medium_dec_o) );
  DFFRPQ_X1M_A9TR40 seq_medium_inc_q_reg ( .D(n168), .CK(cal_clk_i), .R(n13), 
        .Q(seq_medium_inc_o) );
  DFFRPQ_X1M_A9TR40 \coarse_probe_b_result_q_reg[1]  ( .D(n180), .CK(cal_clk_i), .R(n11), .Q(coarse_probe_b_result_q[1]) );
  DFFRPQ_X1M_A9TR40 \coarse_probe_b_result_q_reg[0]  ( .D(n179), .CK(cal_clk_i), .R(n11), .Q(coarse_probe_b_result_q[0]) );
  DFFRPQ_X1M_A9TR40 \coarse_probe_a_result_q_reg[1]  ( .D(n176), .CK(cal_clk_i), .R(n11), .Q(coarse_probe_a_result_q[1]) );
  DFFRPQ_X1M_A9TR40 \coarse_probe_a_result_q_reg[0]  ( .D(n175), .CK(cal_clk_i), .R(n11), .Q(coarse_probe_a_result_q[0]) );
  DFFRPQ_X1M_A9TR40 cal_done_q_reg ( .D(n163), .CK(cal_clk_i), .R(n13), .Q(
        cal_done_o) );
  DFFRPQ_X1M_A9TR40 \fail_reason_q_reg[2]  ( .D(n174), .CK(cal_clk_i), .R(n11), 
        .Q(fail_reason_o[2]) );
  DFFRPQ_X1M_A9TR40 cal_fail_q_reg ( .D(n162), .CK(cal_clk_i), .R(n13), .Q(
        cal_fail_o) );
  DFFRPQ_X1M_A9TR40 \fail_reason_q_reg[0]  ( .D(n172), .CK(cal_clk_i), .R(n13), 
        .Q(fail_reason_o[0]) );
  DFFRPQ_X1M_A9TR40 \fine_probe_result_q_reg[1]  ( .D(n178), .CK(cal_clk_i), 
        .R(n11), .Q(fine_probe_result_q[1]) );
  DFFRPQ_X1M_A9TR40 \fail_reason_q_reg[1]  ( .D(n173), .CK(cal_clk_i), .R(n11), 
        .Q(fail_reason_o[1]) );
  DFFRPQ_X1M_A9TR40 \fine_probe_result_q_reg[0]  ( .D(n186), .CK(cal_clk_i), 
        .R(n11), .Q(fine_probe_result_q[0]) );
  DFFRPQ_X1M_A9TR40 cal_busy_q_reg ( .D(n164), .CK(cal_clk_i), .R(n13), .Q(
        cal_busy_o) );
  DFFRPQ_X1M_A9TR40 \state_q_reg[4]  ( .D(n183), .CK(cal_clk_i), .R(n11), .Q(
        n191) );
  DFFRPQ_X1M_A9TR40 lock_valid_q_reg ( .D(n177), .CK(cal_clk_i), .R(n11), .Q(
        lock_valid_o) );
  DFFRPQ_X1M_A9TR40 \seq_cmd_q_reg[0]  ( .D(n169), .CK(cal_clk_i), .R(n13), 
        .Q(seq_cmd_o[0]) );
  DFFRPQ_X1M_A9TR40 \seq_cmd_q_reg[1]  ( .D(n170), .CK(cal_clk_i), .R(n13), 
        .Q(seq_cmd_o[1]) );
  DFFRPQ_X1M_A9TR40 \state_q_reg[2]  ( .D(n181), .CK(cal_clk_i), .R(n11), .Q(
        fsm_state_o[2]) );
  DFFRPQ_X1M_A9TR40 seq_req_q_reg ( .D(n171), .CK(cal_clk_i), .R(n13), .Q(
        seq_req_o) );
  DFFRPQ_X2M_A9TR40 \state_q_reg[1]  ( .D(n184), .CK(cal_clk_i), .R(n11), .Q(
        fsm_state_o[1]) );
  DFFRPQ_X2M_A9TR40 \state_q_reg[3]  ( .D(n182), .CK(cal_clk_i), .R(n11), .Q(
        fsm_state_o[3]) );
  DFFRPQ_X2M_A9TR40 \state_q_reg[0]  ( .D(n185), .CK(cal_clk_i), .R(n11), .Q(
        fsm_state_o[0]) );
  NOR2_X1A_A9TR40 U3 ( .A(n136), .B(fsm_state_o[3]), .Y(n161) );
  INV_X1M_A9TR40 U4 ( .A(n161), .Y(n133) );
  NOR2_X3A_A9TR40 U5 ( .A(n133), .B(n109), .Y(n128) );
  NOR3_X3A_A9TR40 U6 ( .A(n133), .B(fsm_state_o[0]), .C(n125), .Y(n32) );
  NOR3_X3A_A9TR40 U7 ( .A(fsm_state_o[0]), .B(fsm_state_o[3]), .C(n124), .Y(
        n65) );
  NOR3_X3M_A9TR40 U8 ( .A(n93), .B(fsm_state_o[1]), .C(n130), .Y(n105) );
  NOR2_X0P7M_A9TR40 U9 ( .A(fsm_state_o[0]), .B(fsm_state_o[1]), .Y(n77) );
  AOI211_X1M_A9TR40 U10 ( .A0(n96), .A1(cfg_at_max_medium_i), .B0(
        fsm_state_o[4]), .C0(n90), .Y(n88) );
  NOR2_X0P7M_A9TR40 U11 ( .A(n119), .B(cfg_at_max_fine_i), .Y(n103) );
  OAI21_X1P4M_A9TR40 U12 ( .A0(n125), .A1(n130), .B0(n71), .Y(n39) );
  INV_X1M_A9TR40 U13 ( .A(n128), .Y(n95) );
  NOR2_X2A_A9TR40 U14 ( .A(n130), .B(n109), .Y(n58) );
  OAI31_X2M_A9TR40 U15 ( .A0(n110), .A1(n61), .A2(n40), .B0(n126), .Y(n97) );
  OAI21_X1M_A9TR40 U16 ( .A0(n160), .A1(n1), .B0(n52), .Y(n110) );
  NOR2_X1A_A9TR40 U17 ( .A(n21), .B(n39), .Y(n27) );
  NAND3_X1M_A9TR40 U18 ( .A(n50), .B(n115), .C(n27), .Y(n40) );
  NOR4BB_X2M_A9TR40 U19 ( .AN(n188), .BN(n33), .C(n46), .D(n127), .Y(n123) );
  OAI22BB_X1P4M_A9TR40 U20 ( .A0(n31), .A1(n141), .B0N(n141), .B1N(
        cfg_at_max_medium_i), .Y(n80) );
  NOR2_X2A_A9TR40 U21 ( .A(n105), .B(n58), .Y(n1) );
  NAND4_X1A_A9TR40 U22 ( .A(n69), .B(n33), .C(n188), .D(n111), .Y(n60) );
  AO21B_X0P5M_A9TR40 U23 ( .A0(cfg_at_max_medium_i), .A1(n128), .B0N(n104), 
        .Y(n145) );
  NOR2_X1A_A9TR40 U24 ( .A(n105), .B(n30), .Y(n104) );
  NAND2_X1A_A9TR40 U25 ( .A(n70), .B(n154), .Y(n61) );
  NOR2_X1A_A9TR40 U26 ( .A(n131), .B(n136), .Y(n157) );
  NOR2_X1A_A9TR40 U27 ( .A(fsm_state_o[4]), .B(n53), .Y(n3) );
  INV_X1M_A9TR40 U28 ( .A(n32), .Y(n115) );
  NAND4_X2A_A9TR40 U29 ( .A(n142), .B(n140), .C(n138), .D(n137), .Y(n141) );
  NAND2_X1A_A9TR40 U30 ( .A(n116), .B(n131), .Y(n52) );
  INV_X2M_A9TR40 U31 ( .A(fsm_state_o[4]), .Y(n126) );
  INV_X1M_A9TR40 U32 ( .A(n82), .Y(n160) );
  INV_X1M_A9TR40 U33 ( .A(n45), .Y(n17) );
  NAND3_X2M_A9TR40 U34 ( .A(n152), .B(n126), .C(n153), .Y(n132) );
  NOR2_X2A_A9TR40 U35 ( .A(fsm_state_o[1]), .B(fsm_state_o[2]), .Y(n158) );
  OAI22_X0P7M_A9TR40 U36 ( .A0(n74), .A1(n133), .B0(cfg_at_max_fine_i), .B1(
        n76), .Y(n73) );
  NAND3_X1A_A9TR40 U37 ( .A(n158), .B(n93), .C(fsm_state_o[3]), .Y(n70) );
  AOI31_X1M_A9TR40 U38 ( .A0(seq_done_i), .A1(n114), .A2(n111), .B0(n89), .Y(
        n59) );
  INV_X2M_A9TR40 U39 ( .A(fsm_state_o[3]), .Y(n131) );
  INV_X2M_A9TR40 U40 ( .A(fsm_state_o[0]), .Y(n93) );
  BUF_X2M_A9TR40 U41 ( .A(n191), .Y(fsm_state_o[4]) );
  NAND3_X1M_A9TR40 U42 ( .A(fsm_state_o[0]), .B(n131), .C(n85), .Y(n71) );
  INV_X1M_A9TR40 U43 ( .A(fsm_state_o[2]), .Y(n136) );
  NOR2_X2A_A9TR40 U44 ( .A(q_class_i[1]), .B(q_class_i[0]), .Y(n45) );
  NAND2_X1A_A9TR40 U45 ( .A(fsm_state_o[0]), .B(n158), .Y(n76) );
  NAND2B_X1M_A9TR40 U46 ( .AN(fine_probe_result_q[1]), .B(
        fine_probe_result_q[0]), .Y(n100) );
  INV_X1M_A9TR40 U47 ( .A(q_class_i[0]), .Y(n26) );
  INV_X1M_A9TR40 U48 ( .A(q_class_i[1]), .Y(n16) );
  INV_X1M_A9TR40 U49 ( .A(n15), .Y(n46) );
  NOR2_X2A_A9TR40 U50 ( .A(n23), .B(n128), .Y(n15) );
  OAI211_X1M_A9TR40 U51 ( .A0(n95), .A1(n189), .B0(n97), .C0(n117), .Y(n91) );
  INV_X1M_A9TR40 U52 ( .A(n40), .Y(n89) );
  INV_X1M_A9TR40 U53 ( .A(n113), .Y(n51) );
  INV_X1M_A9TR40 U54 ( .A(n58), .Y(n106) );
  NOR2_X1A_A9TR40 U55 ( .A(n58), .B(n96), .Y(n94) );
  INV_X1M_A9TR40 U56 ( .A(n97), .Y(n56) );
  INV_X1M_A9TR40 U57 ( .A(n50), .Y(n84) );
  INV_X1M_A9TR40 U58 ( .A(n34), .Y(n96) );
  NOR3_X2A_A9TR40 U59 ( .A(n61), .B(n57), .C(n79), .Y(n129) );
  NOR3BB_X2M_A9TR40 U60 ( .AN(n15), .BN(n52), .C(n60), .Y(n113) );
  NAND3_X1M_A9TR40 U61 ( .A(n121), .B(n54), .C(n160), .Y(n122) );
  NAND2_X1A_A9TR40 U62 ( .A(n17), .B(n97), .Y(n2) );
  INV_X1M_A9TR40 U63 ( .A(n103), .Y(n117) );
  OAI21_X1M_A9TR40 U64 ( .A0(n95), .A1(n80), .B0(n117), .Y(n43) );
  NAND3_X1M_A9TR40 U65 ( .A(n119), .B(n126), .C(n129), .Y(n23) );
  AOI21_X1M_A9TR40 U66 ( .A0(n126), .A1(n43), .B0(n56), .Y(n10) );
  INV_X1M_A9TR40 U67 ( .A(n1), .Y(n79) );
  INV_X1M_A9TR40 U68 ( .A(n123), .Y(n38) );
  INV_X1M_A9TR40 U69 ( .A(n31), .Y(n189) );
  INV_X1M_A9TR40 U70 ( .A(n54), .Y(n57) );
  INV_X1M_A9TR40 U71 ( .A(n157), .Y(n130) );
  INV_X1M_A9TR40 U72 ( .A(n3), .Y(n118) );
  AND2_X1M_A9TR40 U73 ( .A(n80), .B(n128), .Y(n7) );
  NOR2_X2A_A9TR40 U74 ( .A(n106), .B(n17), .Y(n14) );
  NOR2_X2A_A9TR40 U75 ( .A(n95), .B(n141), .Y(n30) );
  NOR2_X2A_A9TR40 U76 ( .A(n20), .B(n29), .Y(n50) );
  NOR2_X1A_A9TR40 U77 ( .A(n149), .B(n128), .Y(n47) );
  NAND2_X1A_A9TR40 U78 ( .A(n1), .B(n47), .Y(n6) );
  INV_X1M_A9TR40 U79 ( .A(n149), .Y(n119) );
  NAND3_X1M_A9TR40 U80 ( .A(n52), .B(n115), .C(n112), .Y(n127) );
  NAND2_X1A_A9TR40 U81 ( .A(n128), .B(n141), .Y(n34) );
  INV_X1M_A9TR40 U82 ( .A(n39), .Y(n111) );
  INV_X1M_A9TR40 U83 ( .A(n21), .Y(n112) );
  INV_X1M_A9TR40 U84 ( .A(n29), .Y(n120) );
  OAI21_X0P5M_A9TR40 U85 ( .A0(cfg_at_max_medium_i), .A1(n95), .B0(n104), .Y(
        n102) );
  NAND3_X2M_A9TR40 U86 ( .A(n93), .B(n131), .C(n158), .Y(n54) );
  NOR2_X1P4B_A9TR40 U87 ( .A(cfg_at_min_medium_i), .B(
        cfg_medium_too_low_for_backoff_i), .Y(n31) );
  NOR2B_X1P4M_A9TR40 U88 ( .AN(cfg_at_max_fine_i), .B(n119), .Y(n53) );
  NOR4BB_X2M_A9TR40 U89 ( .AN(n52), .BN(n89), .C(fsm_state_o[4]), .D(n6), .Y(
        n121) );
  INV_X1M_A9TR40 U90 ( .A(n132), .Y(n28) );
  OAI22_X1M_A9TR40 U91 ( .A0(n93), .A1(n132), .B0(n28), .B1(n146), .Y(n185) );
  NOR4BB_X1M_A9TR40 U92 ( .AN(n94), .BN(n147), .C(n148), .D(n118), .Y(n146) );
  NAND4XXXB_X1M_A9TR40 U93 ( .DN(n150), .A(n114), .B(n115), .C(n54), .Y(n148)
         );
  AOI22_X1M_A9TR40 U94 ( .A0(n128), .A1(n189), .B0(n105), .B1(n17), .Y(n147)
         );
  AND4_X1M_A9TR40 U95 ( .A(n54), .B(n55), .C(n126), .D(n75), .Y(n44) );
  OA21A1OI2_X1M_A9TR40 U96 ( .A0(n58), .A1(n59), .B0(n60), .C0(n61), .Y(n55)
         );
  NAND2_X1A_A9TR40 U97 ( .A(n15), .B(n37), .Y(n19) );
  OAI31_X1M_A9TR40 U98 ( .A0(n187), .A1(n32), .A2(n39), .B0(n40), .Y(n37) );
  NAND2_X1A_A9TR40 U99 ( .A(n114), .B(n159), .Y(n21) );
  OAI22_X1M_A9TR40 U100 ( .A0(n123), .A1(n138), .B0(n26), .B1(n38), .Y(n179)
         );
  OAI22_X1M_A9TR40 U101 ( .A0(n123), .A1(n137), .B0(n16), .B1(n38), .Y(n180)
         );
  OAI22_X1M_A9TR40 U102 ( .A0(n136), .A1(n132), .B0(n28), .B1(n134), .Y(n181)
         );
  NOR3_X1A_A9TR40 U103 ( .A(n135), .B(n118), .C(n79), .Y(n134) );
  OAI211_X1M_A9TR40 U104 ( .A0(n93), .A1(n124), .B0(n95), .C0(n115), .Y(n135)
         );
  INV_X1M_A9TR40 U105 ( .A(n65), .Y(n114) );
  OAI22_X1M_A9TR40 U106 ( .A0(n113), .A1(n142), .B0(n51), .B1(n26), .Y(n175)
         );
  OAI22_X1M_A9TR40 U107 ( .A0(n113), .A1(n140), .B0(n51), .B1(n16), .Y(n176)
         );
  OAI22_X1M_A9TR40 U108 ( .A0(n125), .A1(n132), .B0(n28), .B1(n143), .Y(n184)
         );
  NOR3_X1A_A9TR40 U109 ( .A(n144), .B(n127), .C(n145), .Y(n143) );
  OAI211_X1M_A9TR40 U110 ( .A0(n45), .A1(n106), .B0(n119), .C0(n126), .Y(n144)
         );
  INV_X1M_A9TR40 U111 ( .A(n85), .Y(n124) );
  NAND2_X1A_A9TR40 U112 ( .A(n121), .B(n70), .Y(n8) );
  INV_X1M_A9TR40 U113 ( .A(n77), .Y(n109) );
  NOR2_X1A_A9TR40 U114 ( .A(n132), .B(n126), .Y(n183) );
  OAI21_X1M_A9TR40 U115 ( .A0(n28), .A1(n139), .B0(n131), .Y(n182) );
  NOR3_X1A_A9TR40 U116 ( .A(n84), .B(fsm_state_o[4]), .C(n7), .Y(n139) );
  NOR2B_X1M_A9TR40 U117 ( .AN(n53), .B(n100), .Y(n90) );
  INV_X1M_A9TR40 U118 ( .A(n59), .Y(n86) );
  NOR3_X2A_A9TR40 U119 ( .A(n93), .B(n133), .C(n125), .Y(n20) );
  NAND4_X1M_A9TR40 U120 ( .A(n105), .B(n160), .C(n45), .D(n126), .Y(n9) );
  NOR2_X2A_A9TR40 U121 ( .A(n84), .B(n65), .Y(n36) );
  INV_X0P8B_A9TR40 U122 ( .A(n105), .Y(n75) );
  NOR2_X2A_A9TR40 U123 ( .A(n124), .B(n131), .Y(n29) );
  NOR2_X2A_A9TR40 U124 ( .A(n131), .B(n76), .Y(n149) );
  NAND3_X1M_A9TR40 U125 ( .A(n70), .B(n75), .C(n71), .Y(n67) );
  INV_X1M_A9TR40 U126 ( .A(n76), .Y(n116) );
  INV_X1M_A9TR40 U127 ( .A(n66), .Y(n188) );
  AND2_X1M_A9TR40 U128 ( .A(n159), .B(n115), .Y(n69) );
  AO1B2_X1M_A9TR40 U129 ( .B0(n149), .B1(n100), .A0N(n70), .Y(n150) );
  BUF_X3M_A9TR40 U130 ( .A(n190), .Y(n11) );
  BUF_X3M_A9TR40 U131 ( .A(n190), .Y(n13) );
  OAI211_X1M_A9TR40 U132 ( .A0(n2), .A1(n106), .B0(n87), .C0(n88), .Y(n172) );
  OAI21_X1M_A9TR40 U133 ( .A0(n91), .A1(n92), .B0(fail_reason_o[0]), .Y(n87)
         );
  OAI21_X1M_A9TR40 U134 ( .A0(n17), .A1(n75), .B0(n94), .Y(n92) );
  OAI31_X0P7M_A9TR40 U135 ( .A0(n34), .A1(cfg_at_max_medium_i), .A2(n23), .B0(
        n35), .Y(n168) );
  OAI2XB1_X1M_A9TR40 U136 ( .A1N(n36), .A0(n19), .B0(seq_medium_inc_o), .Y(n35) );
  NAND4_X1A_A9TR40 U137 ( .A(n36), .B(cal_start_i), .C(n69), .D(n156), .Y(n152) );
  AOI32_X1M_A9TR40 U138 ( .A0(n154), .A1(n54), .A2(n160), .B0(n129), .B1(n86), 
        .Y(n153) );
  NOR3_X1A_A9TR40 U139 ( .A(n79), .B(n39), .C(n61), .Y(n156) );
  NOR2_X2A_A9TR40 U140 ( .A(n125), .B(fsm_state_o[2]), .Y(n85) );
  INV_X2M_A9TR40 U141 ( .A(fsm_state_o[1]), .Y(n125) );
  OAI211_X1M_A9TR40 U142 ( .A0(n1), .A1(n2), .B0(n3), .C0(n4), .Y(n162) );
  OA21A1OI2_X1M_A9TR40 U143 ( .A0(n56), .A1(n6), .B0(cal_fail_o), .C0(n7), .Y(
        n4) );
  OAI22_X1M_A9TR40 U144 ( .A0(n10), .A1(n155), .B0(fsm_state_o[4]), .B1(n12), 
        .Y(n164) );
  INV_X1M_A9TR40 U145 ( .A(cal_busy_o), .Y(n155) );
  AOI22_X1M_A9TR40 U146 ( .A0(cal_start_i), .A1(n57), .B0(cal_busy_o), .B1(n14), .Y(n12) );
  OAI22_X1M_A9TR40 U147 ( .A0(n10), .A1(n151), .B0(fsm_state_o[4]), .B1(n107), 
        .Y(n174) );
  AOI22_X1M_A9TR40 U148 ( .A0(n53), .A1(n100), .B0(n108), .B1(n79), .Y(n107)
         );
  NAND2_X1A_A9TR40 U149 ( .A(n151), .B(n2), .Y(n108) );
  INV_X1M_A9TR40 U150 ( .A(fail_reason_o[2]), .Y(n151) );
  AOI22_X1M_A9TR40 U151 ( .A0(n77), .A1(n78), .B0(seq_done_i), .B1(n109), .Y(
        n74) );
  NAND2B_X1M_A9TR40 U152 ( .AN(seq_req_o), .B(n80), .Y(n78) );
  OAI21_X1M_A9TR40 U153 ( .A0(n22), .A1(n23), .B0(n24), .Y(n167) );
  AOI22_X1M_A9TR40 U154 ( .A0(n30), .A1(n31), .B0(n32), .B1(n33), .Y(n22) );
  OAI21_X1M_A9TR40 U155 ( .A0(n25), .A1(n46), .B0(seq_medium_dec_o), .Y(n24)
         );
  AOI31_X1M_A9TR40 U156 ( .A0(n27), .A1(n120), .A2(seq_busy_i), .B0(n89), .Y(
        n25) );
  OAI22BB_X1M_A9TR40 U157 ( .A0(n62), .A1(n63), .B0N(n63), .B1N(seq_req_o), 
        .Y(n171) );
  OAI21_X1M_A9TR40 U158 ( .A0(seq_busy_i), .A1(n64), .B0(n126), .Y(n63) );
  AOI211_X1M_A9TR40 U159 ( .A0(n29), .A1(seq_done_i), .B0(n72), .C0(n73), .Y(
        n62) );
  AOI211_X1M_A9TR40 U160 ( .A0(n65), .A1(n66), .B0(n67), .C0(n68), .Y(n64) );
  OAI22BB_X1M_A9TR40 U161 ( .A0(n16), .A1(n122), .B0N(n122), .B1N(
        fine_probe_result_q[1]), .Y(n178) );
  OAI22BB_X1M_A9TR40 U162 ( .A0(n26), .A1(n122), .B0N(n122), .B1N(
        fine_probe_result_q[0]), .Y(n186) );
  OAI22BB_X1M_A9TR40 U163 ( .A0(fsm_state_o[4]), .A1(n98), .B0N(
        fail_reason_o[1]), .B1N(n56), .Y(n173) );
  AOI211_X1M_A9TR40 U164 ( .A0(n30), .A1(n189), .B0(n99), .C0(n90), .Y(n98) );
  OAI21_X1M_A9TR40 U165 ( .A0(n2), .A1(n75), .B0(n101), .Y(n99) );
  OAI31_X0P7M_A9TR40 U166 ( .A0(n102), .A1(n103), .A2(n14), .B0(
        fail_reason_o[1]), .Y(n101) );
  AO1B2_X1M_A9TR40 U167 ( .B0(cal_done_o), .B1(n8), .A0N(n9), .Y(n163) );
  AO1B2_X1M_A9TR40 U168 ( .B0(lock_valid_o), .B1(n8), .A0N(n9), .Y(n177) );
  OAI21_X1M_A9TR40 U169 ( .A0(fsm_state_o[4]), .A1(n117), .B0(n18), .Y(n166)
         );
  OAI31_X1M_A9TR40 U170 ( .A0(n19), .A1(n20), .A2(n21), .B0(seq_fine_inc_o), 
        .Y(n18) );
  AO1B2_X1M_A9TR40 U171 ( .B0(seq_cmd_o[0]), .B1(n41), .A0N(n42), .Y(n169) );
  OAI211_X1M_A9TR40 U172 ( .A0(n45), .A1(n106), .B0(n47), .C0(n44), .Y(n41) );
  OAI21_X0P5M_A9TR40 U173 ( .A0(n32), .A1(n43), .B0(n44), .Y(n42) );
  AO22_X1M_A9TR40 U174 ( .A0(seq_cmd_o[1]), .A1(n48), .B0(n44), .B1(n49), .Y(
        n170) );
  NAND4XXXB_X1M_A9TR40 U175 ( .DN(n14), .A(n50), .B(n112), .C(n52), .Y(n49) );
  NAND4BB_X1M_A9TR40 U176 ( .AN(n53), .BN(n7), .C(n44), .D(n106), .Y(n48) );
  NOR2B_X2M_A9TR40 U177 ( .AN(seq_done_i), .B(n84), .Y(n33) );
  OAI211_X1M_A9TR40 U178 ( .A0(n81), .A1(n82), .B0(n52), .C0(n83), .Y(n72) );
  AO21A1AI2_X1M_A9TR40 U179 ( .A0(n58), .A1(n187), .B0(n116), .C0(seq_req_o), 
        .Y(n83) );
  AOI21_X1M_A9TR40 U180 ( .A0(n85), .A1(n93), .B0(n14), .Y(n81) );
  NAND3_X1M_A9TR40 U181 ( .A(n161), .B(n125), .C(fsm_state_o[0]), .Y(n159) );
  INV_X1M_A9TR40 U182 ( .A(seq_busy_i), .Y(n187) );
  NAND2_X1A_A9TR40 U183 ( .A(n157), .B(fsm_state_o[1]), .Y(n154) );
  NAND2_X1A_A9TR40 U184 ( .A(seq_done_i), .B(n188), .Y(n82) );
  AOI21_X1M_A9TR40 U185 ( .A0(n69), .A1(n36), .B0(seq_done_i), .Y(n68) );
  NAND2_X1A_A9TR40 U186 ( .A(seq_probe_done_i), .B(q_class_valid_i), .Y(n66)
         );
  AOI21B_X1M_A9TR40 U187 ( .A0(n15), .A1(n89), .B0N(seq_fine_dec_o), .Y(n165)
         );
  INV_X1M_A9TR40 U188 ( .A(coarse_probe_b_result_q[0]), .Y(n138) );
  INV_X1M_A9TR40 U189 ( .A(coarse_probe_a_result_q[1]), .Y(n140) );
  INV_X1M_A9TR40 U190 ( .A(coarse_probe_b_result_q[1]), .Y(n137) );
  INV_X1M_A9TR40 U191 ( .A(coarse_probe_a_result_q[0]), .Y(n142) );
  INV_X1M_A9TR40 U192 ( .A(ctrl_por_n_i), .Y(n190) );
endmodule


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
  wire   seq_medium_inc, seq_medium_dec, seq_fine_inc, seq_fine_dec,
         cfg_at_max_medium, cfg_at_min_medium, cfg_at_max_fine,
         cfg_medium_too_low, seq_req, fsm_medium_inc, fsm_medium_dec,
         fsm_fine_inc, fsm_fine_dec, seq_busy, seq_done, seq_probe_done,
         q_class_valid, n1, n2;
  wire   [1:0] seq_cmd;
  wire   [1:0] q_class;

  ftc_cfg_therm_regs u_cfg_regs ( .clk_i(cal_clk), .por_n_i(ctrl_por_n), 
        .init_i(n2), .medium_inc_i(seq_medium_inc), .medium_dec_i(
        seq_medium_dec), .fine_inc_i(seq_fine_inc), .fine_dec_i(seq_fine_dec), 
        .lock_i(lock_valid), .medium_therm_o(medium_therm), .fine_therm_o(
        fine_therm), .medium_code_o(medium_code), .fine_code_o(fine_code), 
        .medium_at_min_o(cfg_at_min_medium), .medium_at_max_o(
        cfg_at_max_medium), .fine_at_max_o(cfg_at_max_fine), 
        .medium_too_low_for_backoff_o(cfg_medium_too_low) );
  ftc_operation_sequencer u_sequencer ( .cal_clk_i(cal_clk), .ctrl_por_n_i(
        ctrl_por_n), .req_i(seq_req), .cmd_i(seq_cmd), .medium_inc_i(
        fsm_medium_inc), .medium_dec_i(fsm_medium_dec), .fine_inc_i(
        fsm_fine_inc), .fine_dec_i(fsm_fine_dec), .q_final_i(q_final), 
        .sense_dff_reset_o(sense_dff_reset), .sense_s_clk_o(sense_s_clk), 
        .cfg_medium_inc_o(seq_medium_inc), .cfg_medium_dec_o(seq_medium_dec), 
        .cfg_fine_inc_o(seq_fine_inc), .cfg_fine_dec_o(seq_fine_dec), .busy_o(
        seq_busy), .done_o(seq_done), .probe_done_o(seq_probe_done), 
        .q_class_o(q_class), .q_class_valid_o(q_class_valid), 
        .q_sample_1_event_o(q_sample_1_event), .q_sample_2_event_o(
        q_sample_2_event), .config_update_event_o(config_update_event), 
        .probe_start_event_o(probe_start_event) );
  ftc_cal_fsm u_fsm ( .cal_clk_i(cal_clk), .ctrl_por_n_i(ctrl_por_n), 
        .cal_start_i(cal_start), .seq_busy_i(seq_busy), .seq_done_i(seq_done), 
        .seq_probe_done_i(seq_probe_done), .seq_req_o(seq_req), .seq_cmd_o(
        seq_cmd), .seq_medium_inc_o(fsm_medium_inc), .seq_medium_dec_o(
        fsm_medium_dec), .seq_fine_inc_o(fsm_fine_inc), .seq_fine_dec_o(
        fsm_fine_dec), .q_class_i(q_class), .q_class_valid_i(q_class_valid), 
        .cfg_at_max_medium_i(cfg_at_max_medium), .cfg_at_min_medium_i(
        cfg_at_min_medium), .cfg_at_max_fine_i(cfg_at_max_fine), 
        .cfg_medium_too_low_for_backoff_i(cfg_medium_too_low), .cal_busy_o(
        cal_busy), .cal_done_o(cal_done), .cal_fail_o(cal_fail), 
        .lock_valid_o(lock_valid), .fail_reason_o(fail_reason), .fsm_state_o(
        fsm_state) );
  NOR4BB_X1M_A9TR40 U3 ( .AN(fsm_state[0]), .BN(n1), .C(fsm_state[2]), .D(
        fsm_state[1]), .Y(n2) );
  NOR2_X1A_A9TR40 U4 ( .A(fsm_state[4]), .B(fsm_state[3]), .Y(n1) );
endmodule

