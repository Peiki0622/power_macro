* FTC dynamic startup calibration: frozen topology, PWL testbench controls.
.option post=0 nomod measform=3 measdgt=10 runlvl=3
.temp 2.500000000000e+01
.include "/home/zhupl25/chiplet_side_channel/chiplet_gds_data/chiplets/FIR/syn/runs/fir_smic40ll_tt_1310ps_spice_20260722_r1/spice/sc9mc_logic0040ll_base_rvt_c40.hspice.cdl"
.include "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/cdl/sc9mc_logic0040ll_base_lvt_c40.cdl"
.lib "/host/data/libtech/SMIC_40LL/PDK/SPDK40LL_1125_2TM_OA_CDS_V1.4/smic40ll_1125_2tm_oa_cds_1P7M_2012_10_11_v1.4/models/hspice/l0040ll_v1p4_1r.lib" tt
.param VDD_VALUE=8.000000000000e-01
V_VDD vdd_a vss_a 'VDD_VALUE'
V_VSS vss_a 0 0
V_SCLK s_clk vss_a PWL(0.000000000000e+00 0 4.990000000000e-10 0 5.000000000000e-10 'VDD_VALUE' 3.500000000000e-09 'VDD_VALUE' 3.501000000000e-09 0 6.699000000000e-09 0 6.700000000000e-09 'VDD_VALUE' 9.700000000000e-09 'VDD_VALUE' 9.701000000000e-09 0 1.440900000000e-08 0 1.441000000000e-08 'VDD_VALUE' 1.741000000000e-08 'VDD_VALUE' 1.741100000000e-08 0 2.060900000000e-08 0 2.061000000000e-08 'VDD_VALUE' 2.361000000000e-08 'VDD_VALUE' 2.361100000000e-08 0 2.831900000000e-08 0 2.832000000000e-08 'VDD_VALUE' 3.132000000000e-08 'VDD_VALUE' 3.132100000000e-08 0 3.451900000000e-08 0 3.452000000000e-08 'VDD_VALUE' 3.752000000000e-08 'VDD_VALUE' 3.752100000000e-08 0 4.222900000000e-08 0 4.223000000000e-08 'VDD_VALUE' 4.523000000000e-08 'VDD_VALUE' 4.523100000000e-08 0 4.842900000000e-08 0 4.843000000000e-08 'VDD_VALUE' 5.143000000000e-08 'VDD_VALUE' 5.143100000000e-08 0 5.613900000000e-08 0 5.614000000000e-08 'VDD_VALUE' 5.914000000000e-08 'VDD_VALUE' 5.914100000000e-08 0 6.233900000000e-08 0 6.234000000000e-08 'VDD_VALUE' 6.534000000000e-08 'VDD_VALUE' 6.534100000000e-08 0 7.004900000000e-08 0 7.005000000000e-08 'VDD_VALUE' 7.305000000000e-08 'VDD_VALUE' 7.305100000000e-08 0 7.624900000000e-08 0 7.625000000000e-08 'VDD_VALUE' 7.925000000000e-08 'VDD_VALUE' 7.925100000000e-08 0 8.395900000000e-08 0 8.396000000000e-08 'VDD_VALUE' 8.696000000000e-08 'VDD_VALUE' 8.696100000000e-08 0 9.015900000000e-08 0 9.016000000000e-08 'VDD_VALUE' 9.316000000000e-08 'VDD_VALUE' 9.316100000000e-08 0 9.786900000000e-08 0 9.787000000000e-08 'VDD_VALUE' 1.008700000000e-07 'VDD_VALUE' 1.008710000000e-07 0 1.040690000000e-07 0 1.040700000000e-07 'VDD_VALUE' 1.070700000000e-07 'VDD_VALUE' 1.070710000000e-07 0 1.117790000000e-07 0 1.117800000000e-07 'VDD_VALUE' 1.147800000000e-07 'VDD_VALUE' 1.147810000000e-07 0 1.179790000000e-07 0 1.179800000000e-07 'VDD_VALUE' 1.209800000000e-07 'VDD_VALUE' 1.209810000000e-07 0 1.256890000000e-07 0 1.256900000000e-07 'VDD_VALUE' 1.286900000000e-07 'VDD_VALUE' 1.286910000000e-07 0 1.318890000000e-07 0 1.318900000000e-07 'VDD_VALUE' 1.348900000000e-07 'VDD_VALUE' 1.348910000000e-07 0 1.411090000000e-07 0 1.411100000000e-07 'VDD_VALUE' 1.441100000000e-07 'VDD_VALUE' 1.441110000000e-07 0 1.488190000000e-07 0 1.488200000000e-07 'VDD_VALUE' 1.518200000000e-07 'VDD_VALUE' 1.518210000000e-07 0 1.565290000000e-07 0 1.565300000000e-07 'VDD_VALUE' 1.595300000000e-07 'VDD_VALUE' 1.595310000000e-07 0 1.642390000000e-07 0 1.642400000000e-07 'VDD_VALUE' 1.672400000000e-07 'VDD_VALUE' 1.672410000000e-07 0 1.719490000000e-07 0 1.719500000000e-07 'VDD_VALUE' 1.749500000000e-07 'VDD_VALUE' 1.749510000000e-07 0 1.796590000000e-07 0 1.796600000000e-07 'VDD_VALUE' 1.826600000000e-07 'VDD_VALUE' 1.826610000000e-07 0 1.873690000000e-07 0 1.873700000000e-07 'VDD_VALUE' 1.903700000000e-07 'VDD_VALUE' 1.903710000000e-07 0 1.935690000000e-07 0 1.935700000000e-07 'VDD_VALUE' 1.965700000000e-07 'VDD_VALUE' 1.965710000000e-07 0)
V_DFF_RESET dff_reset vss_a PWL(0.000000000000e+00 'VDD_VALUE' 0.000000000000e+00 'VDD_VALUE' 1.000000000000e-11 'VDD_VALUE' 2.000000000000e-11 0 3.200000000000e-09 0 3.210000000000e-09 'VDD_VALUE' 6.200000000000e-09 'VDD_VALUE' 6.210000000000e-09 'VDD_VALUE' 6.220000000000e-09 0 9.400000000000e-09 0 9.410000000000e-09 'VDD_VALUE' 1.391000000000e-08 'VDD_VALUE' 1.392000000000e-08 'VDD_VALUE' 1.393000000000e-08 0 1.711000000000e-08 0 1.712000000000e-08 'VDD_VALUE' 2.011000000000e-08 'VDD_VALUE' 2.012000000000e-08 'VDD_VALUE' 2.013000000000e-08 0 2.331000000000e-08 0 2.332000000000e-08 'VDD_VALUE' 2.782000000000e-08 'VDD_VALUE' 2.783000000000e-08 'VDD_VALUE' 2.784000000000e-08 0 3.102000000000e-08 0 3.103000000000e-08 'VDD_VALUE' 3.402000000000e-08 'VDD_VALUE' 3.403000000000e-08 'VDD_VALUE' 3.404000000000e-08 0 3.722000000000e-08 0 3.723000000000e-08 'VDD_VALUE' 4.173000000000e-08 'VDD_VALUE' 4.174000000000e-08 'VDD_VALUE' 4.175000000000e-08 0 4.493000000000e-08 0 4.494000000000e-08 'VDD_VALUE' 4.793000000000e-08 'VDD_VALUE' 4.794000000000e-08 'VDD_VALUE' 4.795000000000e-08 0 5.113000000000e-08 0 5.114000000000e-08 'VDD_VALUE' 5.564000000000e-08 'VDD_VALUE' 5.565000000000e-08 'VDD_VALUE' 5.566000000000e-08 0 5.884000000000e-08 0 5.885000000000e-08 'VDD_VALUE' 6.184000000000e-08 'VDD_VALUE' 6.185000000000e-08 'VDD_VALUE' 6.186000000000e-08 0 6.504000000000e-08 0 6.505000000000e-08 'VDD_VALUE' 6.955000000000e-08 'VDD_VALUE' 6.956000000000e-08 'VDD_VALUE' 6.957000000000e-08 0 7.275000000000e-08 0 7.276000000000e-08 'VDD_VALUE' 7.575000000000e-08 'VDD_VALUE' 7.576000000000e-08 'VDD_VALUE' 7.577000000000e-08 0 7.895000000000e-08 0 7.896000000000e-08 'VDD_VALUE' 8.346000000000e-08 'VDD_VALUE' 8.347000000000e-08 'VDD_VALUE' 8.348000000000e-08 0 8.666000000000e-08 0 8.667000000000e-08 'VDD_VALUE' 8.966000000000e-08 'VDD_VALUE' 8.967000000000e-08 'VDD_VALUE' 8.968000000000e-08 0 9.286000000000e-08 0 9.287000000000e-08 'VDD_VALUE' 9.737000000000e-08 'VDD_VALUE' 9.738000000000e-08 'VDD_VALUE' 9.739000000000e-08 0 1.005700000000e-07 0 1.005800000000e-07 'VDD_VALUE' 1.035700000000e-07 'VDD_VALUE' 1.035800000000e-07 'VDD_VALUE' 1.035900000000e-07 0 1.067700000000e-07 0 1.067800000000e-07 'VDD_VALUE' 1.112800000000e-07 'VDD_VALUE' 1.112900000000e-07 'VDD_VALUE' 1.113000000000e-07 0 1.144800000000e-07 0 1.144900000000e-07 'VDD_VALUE' 1.174800000000e-07 'VDD_VALUE' 1.174900000000e-07 'VDD_VALUE' 1.175000000000e-07 0 1.206800000000e-07 0 1.206900000000e-07 'VDD_VALUE' 1.251900000000e-07 'VDD_VALUE' 1.252000000000e-07 'VDD_VALUE' 1.252100000000e-07 0 1.283900000000e-07 0 1.284000000000e-07 'VDD_VALUE' 1.313900000000e-07 'VDD_VALUE' 1.314000000000e-07 'VDD_VALUE' 1.314100000000e-07 0 1.345900000000e-07 0 1.346000000000e-07 'VDD_VALUE' 1.406100000000e-07 'VDD_VALUE' 1.406200000000e-07 'VDD_VALUE' 1.406300000000e-07 0 1.438100000000e-07 0 1.438200000000e-07 'VDD_VALUE' 1.483200000000e-07 'VDD_VALUE' 1.483300000000e-07 'VDD_VALUE' 1.483400000000e-07 0 1.515200000000e-07 0 1.515300000000e-07 'VDD_VALUE' 1.560300000000e-07 'VDD_VALUE' 1.560400000000e-07 'VDD_VALUE' 1.560500000000e-07 0 1.592300000000e-07 0 1.592400000000e-07 'VDD_VALUE' 1.637400000000e-07 'VDD_VALUE' 1.637500000000e-07 'VDD_VALUE' 1.637600000000e-07 0 1.669400000000e-07 0 1.669500000000e-07 'VDD_VALUE' 1.714500000000e-07 'VDD_VALUE' 1.714600000000e-07 'VDD_VALUE' 1.714700000000e-07 0 1.746500000000e-07 0 1.746600000000e-07 'VDD_VALUE' 1.791600000000e-07 'VDD_VALUE' 1.791700000000e-07 'VDD_VALUE' 1.791800000000e-07 0 1.823600000000e-07 0 1.823700000000e-07 'VDD_VALUE' 1.868700000000e-07 'VDD_VALUE' 1.868800000000e-07 'VDD_VALUE' 1.868900000000e-07 0 1.900700000000e-07 0 1.900800000000e-07 'VDD_VALUE' 1.930700000000e-07 'VDD_VALUE' 1.930800000000e-07 'VDD_VALUE' 1.930900000000e-07 0 1.962700000000e-07 0 1.962800000000e-07 'VDD_VALUE')
* Frozen sensor: four RVT prefix stages, then 30 observable stages.
XRVT_INIT_00 rvt_initial_0 vdd_a vdd_a vss_a vss_a s_clk BUF_X0P7M_A9TR40
XRVT_INIT_01 rvt_initial_1 vdd_a vdd_a vss_a vss_a rvt_initial_0 BUF_X0P7M_A9TR40
XRVT_INIT_02 rvt_initial_2 vdd_a vdd_a vss_a vss_a rvt_initial_1 BUF_X0P7M_A9TR40
XRVT_INIT_03 rvt_initial_3 vdd_a vdd_a vss_a vss_a rvt_initial_2 BUF_X0P7M_A9TR40
XRVT_00 rvt_0 vdd_a vdd_a vss_a vss_a rvt_initial_3 BUF_X0P7M_A9TR40
XRVT_01 rvt_1 vdd_a vdd_a vss_a vss_a rvt_0 BUF_X0P7M_A9TR40
XRVT_02 rvt_2 vdd_a vdd_a vss_a vss_a rvt_1 BUF_X0P7M_A9TR40
XRVT_03 rvt_3 vdd_a vdd_a vss_a vss_a rvt_2 BUF_X0P7M_A9TR40
XRVT_04 rvt_4 vdd_a vdd_a vss_a vss_a rvt_3 BUF_X0P7M_A9TR40
XRVT_05 rvt_5 vdd_a vdd_a vss_a vss_a rvt_4 BUF_X0P7M_A9TR40
XRVT_06 rvt_6 vdd_a vdd_a vss_a vss_a rvt_5 BUF_X0P7M_A9TR40
XRVT_07 rvt_7 vdd_a vdd_a vss_a vss_a rvt_6 BUF_X0P7M_A9TR40
XRVT_08 rvt_8 vdd_a vdd_a vss_a vss_a rvt_7 BUF_X0P7M_A9TR40
XRVT_09 rvt_9 vdd_a vdd_a vss_a vss_a rvt_8 BUF_X0P7M_A9TR40
XRVT_10 rvt_10 vdd_a vdd_a vss_a vss_a rvt_9 BUF_X0P7M_A9TR40
XRVT_11 rvt_11 vdd_a vdd_a vss_a vss_a rvt_10 BUF_X0P7M_A9TR40
XRVT_12 rvt_12 vdd_a vdd_a vss_a vss_a rvt_11 BUF_X0P7M_A9TR40
XRVT_13 rvt_13 vdd_a vdd_a vss_a vss_a rvt_12 BUF_X0P7M_A9TR40
XRVT_14 rvt_14 vdd_a vdd_a vss_a vss_a rvt_13 BUF_X0P7M_A9TR40
XRVT_15 rvt_15 vdd_a vdd_a vss_a vss_a rvt_14 BUF_X0P7M_A9TR40
XRVT_16 rvt_16 vdd_a vdd_a vss_a vss_a rvt_15 BUF_X0P7M_A9TR40
XRVT_17 rvt_17 vdd_a vdd_a vss_a vss_a rvt_16 BUF_X0P7M_A9TR40
XRVT_18 rvt_18 vdd_a vdd_a vss_a vss_a rvt_17 BUF_X0P7M_A9TR40
XRVT_19 rvt_19 vdd_a vdd_a vss_a vss_a rvt_18 BUF_X0P7M_A9TR40
XRVT_20 rvt_20 vdd_a vdd_a vss_a vss_a rvt_19 BUF_X0P7M_A9TR40
XRVT_21 rvt_21 vdd_a vdd_a vss_a vss_a rvt_20 BUF_X0P7M_A9TR40
XRVT_22 rvt_22 vdd_a vdd_a vss_a vss_a rvt_21 BUF_X0P7M_A9TR40
XRVT_23 rvt_23 vdd_a vdd_a vss_a vss_a rvt_22 BUF_X0P7M_A9TR40
XRVT_24 rvt_24 vdd_a vdd_a vss_a vss_a rvt_23 BUF_X0P7M_A9TR40
XRVT_25 rvt_25 vdd_a vdd_a vss_a vss_a rvt_24 BUF_X0P7M_A9TR40
XRVT_26 rvt_26 vdd_a vdd_a vss_a vss_a rvt_25 BUF_X0P7M_A9TR40
XRVT_27 rvt_27 vdd_a vdd_a vss_a vss_a rvt_26 BUF_X0P7M_A9TR40
XRVT_28 rvt_28 vdd_a vdd_a vss_a vss_a rvt_27 BUF_X0P7M_A9TR40
XRVT_29 rvt_29 vdd_a vdd_a vss_a vss_a rvt_28 BUF_X0P7M_A9TR40
XLVT_00 lvt_0 vdd_a vdd_a vss_a vss_a s_clk BUF_X0P7M_A9TL40
XLVT_01 lvt_1 vdd_a vdd_a vss_a vss_a lvt_0 BUF_X0P7M_A9TL40
XLVT_02 lvt_2 vdd_a vdd_a vss_a vss_a lvt_1 BUF_X0P7M_A9TL40
XLVT_03 lvt_3 vdd_a vdd_a vss_a vss_a lvt_2 BUF_X0P7M_A9TL40
XLVT_04 lvt_4 vdd_a vdd_a vss_a vss_a lvt_3 BUF_X0P7M_A9TL40
XLVT_05 lvt_5 vdd_a vdd_a vss_a vss_a lvt_4 BUF_X0P7M_A9TL40
XLVT_06 lvt_6 vdd_a vdd_a vss_a vss_a lvt_5 BUF_X0P7M_A9TL40
XLVT_07 lvt_7 vdd_a vdd_a vss_a vss_a lvt_6 BUF_X0P7M_A9TL40
XLVT_08 lvt_8 vdd_a vdd_a vss_a vss_a lvt_7 BUF_X0P7M_A9TL40
XLVT_09 lvt_9 vdd_a vdd_a vss_a vss_a lvt_8 BUF_X0P7M_A9TL40
XLVT_10 lvt_10 vdd_a vdd_a vss_a vss_a lvt_9 BUF_X0P7M_A9TL40
XLVT_11 lvt_11 vdd_a vdd_a vss_a vss_a lvt_10 BUF_X0P7M_A9TL40
XLVT_12 lvt_12 vdd_a vdd_a vss_a vss_a lvt_11 BUF_X0P7M_A9TL40
XLVT_13 lvt_13 vdd_a vdd_a vss_a vss_a lvt_12 BUF_X0P7M_A9TL40
XLVT_14 lvt_14 vdd_a vdd_a vss_a vss_a lvt_13 BUF_X0P7M_A9TL40
XLVT_15 lvt_15 vdd_a vdd_a vss_a vss_a lvt_14 BUF_X0P7M_A9TL40
XLVT_16 lvt_16 vdd_a vdd_a vss_a vss_a lvt_15 BUF_X0P7M_A9TL40
XLVT_17 lvt_17 vdd_a vdd_a vss_a vss_a lvt_16 BUF_X0P7M_A9TL40
XLVT_18 lvt_18 vdd_a vdd_a vss_a vss_a lvt_17 BUF_X0P7M_A9TL40
XLVT_19 lvt_19 vdd_a vdd_a vss_a vss_a lvt_18 BUF_X0P7M_A9TL40
XLVT_20 lvt_20 vdd_a vdd_a vss_a vss_a lvt_19 BUF_X0P7M_A9TL40
XLVT_21 lvt_21 vdd_a vdd_a vss_a vss_a lvt_20 BUF_X0P7M_A9TL40
XLVT_22 lvt_22 vdd_a vdd_a vss_a vss_a lvt_21 BUF_X0P7M_A9TL40
XLVT_23 lvt_23 vdd_a vdd_a vss_a vss_a lvt_22 BUF_X0P7M_A9TL40
XLVT_24 lvt_24 vdd_a vdd_a vss_a vss_a lvt_23 BUF_X0P7M_A9TL40
XLVT_25 lvt_25 vdd_a vdd_a vss_a vss_a lvt_24 BUF_X0P7M_A9TL40
XLVT_26 lvt_26 vdd_a vdd_a vss_a vss_a lvt_25 BUF_X0P7M_A9TL40
XLVT_27 lvt_27 vdd_a vdd_a vss_a vss_a lvt_26 BUF_X0P7M_A9TL40
XLVT_28 lvt_28 vdd_a vdd_a vss_a vss_a lvt_27 BUF_X0P7M_A9TL40
XLVT_29 lvt_29 vdd_a vdd_a vss_a vss_a lvt_28 BUF_X0P7M_A9TL40
XXOR_00 xor_0 vdd_a vdd_a vss_a vss_a rvt_0 lvt_0 XOR2_X0P5M_A9TR40
XXOR_01 xor_1 vdd_a vdd_a vss_a vss_a rvt_1 lvt_1 XOR2_X0P5M_A9TR40
XXOR_02 xor_2 vdd_a vdd_a vss_a vss_a rvt_2 lvt_2 XOR2_X0P5M_A9TR40
XXOR_03 xor_3 vdd_a vdd_a vss_a vss_a rvt_3 lvt_3 XOR2_X0P5M_A9TR40
XXOR_04 xor_4 vdd_a vdd_a vss_a vss_a rvt_4 lvt_4 XOR2_X0P5M_A9TR40
XXOR_05 xor_5 vdd_a vdd_a vss_a vss_a rvt_5 lvt_5 XOR2_X0P5M_A9TR40
XXOR_06 xor_6 vdd_a vdd_a vss_a vss_a rvt_6 lvt_6 XOR2_X0P5M_A9TR40
XXOR_07 xor_7 vdd_a vdd_a vss_a vss_a rvt_7 lvt_7 XOR2_X0P5M_A9TR40
XXOR_08 xor_8 vdd_a vdd_a vss_a vss_a rvt_8 lvt_8 XOR2_X0P5M_A9TR40
XXOR_09 xor_9 vdd_a vdd_a vss_a vss_a rvt_9 lvt_9 XOR2_X0P5M_A9TR40
XXOR_10 xor_10 vdd_a vdd_a vss_a vss_a rvt_10 lvt_10 XOR2_X0P5M_A9TR40
XXOR_11 xor_11 vdd_a vdd_a vss_a vss_a rvt_11 lvt_11 XOR2_X0P5M_A9TR40
XXOR_12 xor_12 vdd_a vdd_a vss_a vss_a rvt_12 lvt_12 XOR2_X0P5M_A9TR40
XXOR_13 xor_13 vdd_a vdd_a vss_a vss_a rvt_13 lvt_13 XOR2_X0P5M_A9TR40
XXOR_14 xor_14 vdd_a vdd_a vss_a vss_a rvt_14 lvt_14 XOR2_X0P5M_A9TR40
XXOR_15 xor_15 vdd_a vdd_a vss_a vss_a rvt_15 lvt_15 XOR2_X0P5M_A9TR40
XXOR_16 xor_16 vdd_a vdd_a vss_a vss_a rvt_16 lvt_16 XOR2_X0P5M_A9TR40
XXOR_17 xor_17 vdd_a vdd_a vss_a vss_a rvt_17 lvt_17 XOR2_X0P5M_A9TR40
XXOR_18 xor_18 vdd_a vdd_a vss_a vss_a rvt_18 lvt_18 XOR2_X0P5M_A9TR40
XXOR_19 xor_19 vdd_a vdd_a vss_a vss_a rvt_19 lvt_19 XOR2_X0P5M_A9TR40
XXOR_20 xor_20 vdd_a vdd_a vss_a vss_a rvt_20 lvt_20 XOR2_X0P5M_A9TR40
XXOR_21 xor_21 vdd_a vdd_a vss_a vss_a rvt_21 lvt_21 XOR2_X0P5M_A9TR40
XXOR_22 xor_22 vdd_a vdd_a vss_a vss_a rvt_22 lvt_22 XOR2_X0P5M_A9TR40
XXOR_23 xor_23 vdd_a vdd_a vss_a vss_a rvt_23 lvt_23 XOR2_X0P5M_A9TR40
XXOR_24 xor_24 vdd_a vdd_a vss_a vss_a rvt_24 lvt_24 XOR2_X0P5M_A9TR40
XXOR_25 xor_25 vdd_a vdd_a vss_a vss_a rvt_25 lvt_25 XOR2_X0P5M_A9TR40
XXOR_26 xor_26 vdd_a vdd_a vss_a vss_a rvt_26 lvt_26 XOR2_X0P5M_A9TR40
XXOR_27 xor_27 vdd_a vdd_a vss_a vss_a rvt_27 lvt_27 XOR2_X0P5M_A9TR40
XXOR_28 xor_28 vdd_a vdd_a vss_a vss_a rvt_28 lvt_28 XOR2_X0P5M_A9TR40
XXOR_29 xor_29 vdd_a vdd_a vss_a vss_a rvt_29 lvt_29 XOR2_X0P5M_A9TR40
V_M_00 m_0 vss_a PWL(0.000000000000e+00 0 1.240000000000e-08 0 1.241000000000e-08 'VDD_VALUE' 2.012700000000e-07 'VDD_VALUE')
V_M_01 m_1 vss_a PWL(0.000000000000e+00 0 2.631000000000e-08 0 2.632000000000e-08 'VDD_VALUE' 2.012700000000e-07 'VDD_VALUE')
V_M_02 m_2 vss_a PWL(0.000000000000e+00 0 4.022000000000e-08 0 4.023000000000e-08 'VDD_VALUE' 2.012700000000e-07 'VDD_VALUE')
V_M_03 m_3 vss_a PWL(0.000000000000e+00 0 5.413000000000e-08 0 5.414000000000e-08 'VDD_VALUE' 2.012700000000e-07 'VDD_VALUE')
V_M_04 m_4 vss_a PWL(0.000000000000e+00 0 6.804000000000e-08 0 6.805000000000e-08 'VDD_VALUE' 2.012700000000e-07 'VDD_VALUE')
V_M_05 m_5 vss_a PWL(0.000000000000e+00 0 8.195000000000e-08 0 8.196000000000e-08 'VDD_VALUE' 2.012700000000e-07 'VDD_VALUE')
V_M_06 m_6 vss_a PWL(0.000000000000e+00 0 9.586000000000e-08 0 9.587000000000e-08 'VDD_VALUE' 2.012700000000e-07 'VDD_VALUE')
V_M_07 m_7 vss_a PWL(0.000000000000e+00 0 1.097700000000e-07 0 1.097800000000e-07 'VDD_VALUE' 1.391000000000e-07 'VDD_VALUE' 1.391100000000e-07 0 2.012700000000e-07 0)
V_M_08 m_8 vss_a PWL(0.000000000000e+00 0 1.236800000000e-07 0 1.236900000000e-07 'VDD_VALUE' 1.375900000000e-07 'VDD_VALUE' 1.376000000000e-07 0 2.012700000000e-07 0)
V_M_09 m_9 vss_a PWL(0.000000000000e+00 0 2.012700000000e-07 0)
V_M_10 m_10 vss_a PWL(0.000000000000e+00 0 2.012700000000e-07 0)
V_M_11 m_11 vss_a PWL(0.000000000000e+00 0 2.012700000000e-07 0)
V_M_12 m_12 vss_a PWL(0.000000000000e+00 0 2.012700000000e-07 0)
V_M_13 m_13 vss_a PWL(0.000000000000e+00 0 2.012700000000e-07 0)
V_M_14 m_14 vss_a PWL(0.000000000000e+00 0 2.012700000000e-07 0)
V_M_15 m_15 vss_a PWL(0.000000000000e+00 0 2.012700000000e-07 0)
XMED_BUF_00 x1 vdd_a vdd_a vss_a vss_a xor_29 BUF_X0P7M_A9TL40
XMED_BUF_01 x2 vdd_a vdd_a vss_a vss_a x1 BUF_X0P7M_A9TL40
XMED_BUF_02 x3 vdd_a vdd_a vss_a vss_a x2 BUF_X0P7M_A9TL40
XMED_BUF_03 x4 vdd_a vdd_a vss_a vss_a x3 BUF_X0P7M_A9TL40
XMED_BUF_04 x5 vdd_a vdd_a vss_a vss_a x4 BUF_X0P7M_A9TL40
XMED_BUF_05 x6 vdd_a vdd_a vss_a vss_a x5 BUF_X0P7M_A9TL40
XMED_BUF_06 x7 vdd_a vdd_a vss_a vss_a x6 BUF_X0P7M_A9TL40
XMED_BUF_07 x8 vdd_a vdd_a vss_a vss_a x7 BUF_X0P7M_A9TL40
XMED_BUF_08 x9 vdd_a vdd_a vss_a vss_a x8 BUF_X0P7M_A9TL40
XMED_BUF_09 x10 vdd_a vdd_a vss_a vss_a x9 BUF_X0P7M_A9TL40
XMED_BUF_10 x11 vdd_a vdd_a vss_a vss_a x10 BUF_X0P7M_A9TL40
XMED_BUF_11 x12 vdd_a vdd_a vss_a vss_a x11 BUF_X0P7M_A9TL40
XMED_BUF_12 x13 vdd_a vdd_a vss_a vss_a x12 BUF_X0P7M_A9TL40
XMED_BUF_13 x14 vdd_a vdd_a vss_a vss_a x13 BUF_X0P7M_A9TL40
XMED_BUF_14 x15 vdd_a vdd_a vss_a vss_a x14 BUF_X0P7M_A9TL40
XMED_BUF_15 x16 vdd_a vdd_a vss_a vss_a x15 BUF_X0P7M_A9TL40
XMED_BUF_16 x17 vdd_a vdd_a vss_a vss_a x16 BUF_X0P7M_A9TL40
XMED_MUX_00 medium_out vdd_a vdd_a vss_a vss_a x1 my1 m_0 MXT2_X0P5M_A9TL40
XMED_MUX_01 my1 vdd_a vdd_a vss_a vss_a x2 my2 m_1 MXT2_X0P5M_A9TL40
XMED_MUX_02 my2 vdd_a vdd_a vss_a vss_a x3 my3 m_2 MXT2_X0P5M_A9TL40
XMED_MUX_03 my3 vdd_a vdd_a vss_a vss_a x4 my4 m_3 MXT2_X0P5M_A9TL40
XMED_MUX_04 my4 vdd_a vdd_a vss_a vss_a x5 my5 m_4 MXT2_X0P5M_A9TL40
XMED_MUX_05 my5 vdd_a vdd_a vss_a vss_a x6 my6 m_5 MXT2_X0P5M_A9TL40
XMED_MUX_06 my6 vdd_a vdd_a vss_a vss_a x7 my7 m_6 MXT2_X0P5M_A9TL40
XMED_MUX_07 my7 vdd_a vdd_a vss_a vss_a x8 my8 m_7 MXT2_X0P5M_A9TL40
XMED_MUX_08 my8 vdd_a vdd_a vss_a vss_a x9 my9 m_8 MXT2_X0P5M_A9TL40
XMED_MUX_09 my9 vdd_a vdd_a vss_a vss_a x10 my10 m_9 MXT2_X0P5M_A9TL40
XMED_MUX_10 my10 vdd_a vdd_a vss_a vss_a x11 my11 m_10 MXT2_X0P5M_A9TL40
XMED_MUX_11 my11 vdd_a vdd_a vss_a vss_a x12 my12 m_11 MXT2_X0P5M_A9TL40
XMED_MUX_12 my12 vdd_a vdd_a vss_a vss_a x13 my13 m_12 MXT2_X0P5M_A9TL40
XMED_MUX_13 my13 vdd_a vdd_a vss_a vss_a x14 my14 m_13 MXT2_X0P5M_A9TL40
XMED_MUX_14 my14 vdd_a vdd_a vss_a vss_a x15 my15 m_14 MXT2_X0P5M_A9TL40
XMED_MUX_15 my15 vdd_a vdd_a vss_a vss_a x16 x17 m_15 MXT2_X0P5M_A9TL40
XFINE_DRIVER dff_ck vdd_a vdd_a vss_a vss_a medium_out BUF_X0P8M_A9TL40
V_F_00 f_0 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 1.468100000000e-07 'VDD_VALUE' 1.468200000000e-07 0 2.012700000000e-07 0)
XLOAD_00 z_0 vdd_a vdd_a vss_a vss_a dff_ck f_0 NOR2_X4A_A9TL40
V_F_01 f_1 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 1.545200000000e-07 'VDD_VALUE' 1.545300000000e-07 0 2.012700000000e-07 0)
XLOAD_01 z_1 vdd_a vdd_a vss_a vss_a dff_ck f_1 NOR2_X4A_A9TL40
V_F_02 f_2 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 1.622300000000e-07 'VDD_VALUE' 1.622400000000e-07 0 2.012700000000e-07 0)
XLOAD_02 z_2 vdd_a vdd_a vss_a vss_a dff_ck f_2 NOR2_X4A_A9TL40
V_F_03 f_3 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 1.699400000000e-07 'VDD_VALUE' 1.699500000000e-07 0 2.012700000000e-07 0)
XLOAD_03 z_3 vdd_a vdd_a vss_a vss_a dff_ck f_3 NOR2_X4A_A9TL40
V_F_04 f_4 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 1.776500000000e-07 'VDD_VALUE' 1.776600000000e-07 0 2.012700000000e-07 0)
XLOAD_04 z_4 vdd_a vdd_a vss_a vss_a dff_ck f_4 NOR2_X4A_A9TL40
V_F_05 f_5 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 1.853600000000e-07 'VDD_VALUE' 1.853700000000e-07 0 2.012700000000e-07 0)
XLOAD_05 z_5 vdd_a vdd_a vss_a vss_a dff_ck f_5 NOR2_X4A_A9TL40
V_F_06 f_6 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 2.012700000000e-07 'VDD_VALUE')
XLOAD_06 z_6 vdd_a vdd_a vss_a vss_a dff_ck f_6 NOR2_X4A_A9TL40
V_F_07 f_7 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 2.012700000000e-07 'VDD_VALUE')
XLOAD_07 z_7 vdd_a vdd_a vss_a vss_a dff_ck f_7 NOR2_X4A_A9TL40
V_F_08 f_8 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 2.012700000000e-07 'VDD_VALUE')
XLOAD_08 z_8 vdd_a vdd_a vss_a vss_a dff_ck f_8 NOR2_X4A_A9TL40
V_F_09 f_9 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 2.012700000000e-07 'VDD_VALUE')
XLOAD_09 z_9 vdd_a vdd_a vss_a vss_a dff_ck f_9 NOR2_X4A_A9TL40
XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset DFFRPQ_X0P5M_A9TR40
.tran 1.000000000000e-12 2.012700000000e-07
.measure tran p0_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=5.000000000000e-10
.measure tran p0_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=5.000000000000e-10
.measure tran p0_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=5.000000000000e-10
.measure tran p0_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=5.000000000000e-10
.measure tran p0_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=5.000000000000e-10
.measure tran p0_q_read_v FIND v(q_final,vss_a) AT=2.800000000000e-09
.measure tran p0_xor_peak MAX v(xor_29,vss_a) FROM=5.000000000000e-10 TO=3.200000000000e-09
.measure tran p0_ck_peak MAX v(dff_ck,vss_a) FROM=5.000000000000e-10 TO=3.200000000000e-09
.measure tran p0_recovery_xor_end FIND v(xor_29,vss_a) AT=6.200000000000e-09
.measure tran p0_recovery_medium_end FIND v(medium_out,vss_a) AT=6.200000000000e-09
.measure tran p0_recovery_ck_end FIND v(dff_ck,vss_a) AT=6.200000000000e-09
.measure tran p0_recovery_xor_tail MAX v(xor_29,vss_a) FROM=6.000000000000e-09 TO=6.200000000000e-09
.measure tran p0_recovery_medium_tail MAX v(medium_out,vss_a) FROM=6.000000000000e-09 TO=6.200000000000e-09
.measure tran p0_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=6.000000000000e-09 TO=6.200000000000e-09
.measure tran p1_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=6.700000000000e-09
.measure tran p1_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=6.700000000000e-09
.measure tran p1_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=6.700000000000e-09
.measure tran p1_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=6.700000000000e-09
.measure tran p1_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=6.700000000000e-09
.measure tran p1_q_read_v FIND v(q_final,vss_a) AT=9.000000000000e-09
.measure tran p1_xor_peak MAX v(xor_29,vss_a) FROM=6.700000000000e-09 TO=9.400000000000e-09
.measure tran p1_ck_peak MAX v(dff_ck,vss_a) FROM=6.700000000000e-09 TO=9.400000000000e-09
.measure tran p1_recovery_xor_end FIND v(xor_29,vss_a) AT=1.240000000000e-08
.measure tran p1_recovery_medium_end FIND v(medium_out,vss_a) AT=1.240000000000e-08
.measure tran p1_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.240000000000e-08
.measure tran p1_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.220000000000e-08 TO=1.240000000000e-08
.measure tran p1_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.220000000000e-08 TO=1.240000000000e-08
.measure tran p1_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.220000000000e-08 TO=1.240000000000e-08
.measure tran p2_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.441000000000e-08
.measure tran p2_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.441000000000e-08
.measure tran p2_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.441000000000e-08
.measure tran p2_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.441000000000e-08
.measure tran p2_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.441000000000e-08
.measure tran p2_q_read_v FIND v(q_final,vss_a) AT=1.671000000000e-08
.measure tran p2_xor_peak MAX v(xor_29,vss_a) FROM=1.441000000000e-08 TO=1.711000000000e-08
.measure tran p2_ck_peak MAX v(dff_ck,vss_a) FROM=1.441000000000e-08 TO=1.711000000000e-08
.measure tran p2_recovery_xor_end FIND v(xor_29,vss_a) AT=2.011000000000e-08
.measure tran p2_recovery_medium_end FIND v(medium_out,vss_a) AT=2.011000000000e-08
.measure tran p2_recovery_ck_end FIND v(dff_ck,vss_a) AT=2.011000000000e-08
.measure tran p2_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.991000000000e-08 TO=2.011000000000e-08
.measure tran p2_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.991000000000e-08 TO=2.011000000000e-08
.measure tran p2_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.991000000000e-08 TO=2.011000000000e-08
.measure tran p3_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=2.061000000000e-08
.measure tran p3_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=2.061000000000e-08
.measure tran p3_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=2.061000000000e-08
.measure tran p3_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=2.061000000000e-08
.measure tran p3_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=2.061000000000e-08
.measure tran p3_q_read_v FIND v(q_final,vss_a) AT=2.291000000000e-08
.measure tran p3_xor_peak MAX v(xor_29,vss_a) FROM=2.061000000000e-08 TO=2.331000000000e-08
.measure tran p3_ck_peak MAX v(dff_ck,vss_a) FROM=2.061000000000e-08 TO=2.331000000000e-08
.measure tran p3_recovery_xor_end FIND v(xor_29,vss_a) AT=2.631000000000e-08
.measure tran p3_recovery_medium_end FIND v(medium_out,vss_a) AT=2.631000000000e-08
.measure tran p3_recovery_ck_end FIND v(dff_ck,vss_a) AT=2.631000000000e-08
.measure tran p3_recovery_xor_tail MAX v(xor_29,vss_a) FROM=2.611000000000e-08 TO=2.631000000000e-08
.measure tran p3_recovery_medium_tail MAX v(medium_out,vss_a) FROM=2.611000000000e-08 TO=2.631000000000e-08
.measure tran p3_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=2.611000000000e-08 TO=2.631000000000e-08
.measure tran p4_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=2.832000000000e-08
.measure tran p4_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=2.832000000000e-08
.measure tran p4_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=2.832000000000e-08
.measure tran p4_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=2.832000000000e-08
.measure tran p4_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=2.832000000000e-08
.measure tran p4_q_read_v FIND v(q_final,vss_a) AT=3.062000000000e-08
.measure tran p4_xor_peak MAX v(xor_29,vss_a) FROM=2.832000000000e-08 TO=3.102000000000e-08
.measure tran p4_ck_peak MAX v(dff_ck,vss_a) FROM=2.832000000000e-08 TO=3.102000000000e-08
.measure tran p4_recovery_xor_end FIND v(xor_29,vss_a) AT=3.402000000000e-08
.measure tran p4_recovery_medium_end FIND v(medium_out,vss_a) AT=3.402000000000e-08
.measure tran p4_recovery_ck_end FIND v(dff_ck,vss_a) AT=3.402000000000e-08
.measure tran p4_recovery_xor_tail MAX v(xor_29,vss_a) FROM=3.382000000000e-08 TO=3.402000000000e-08
.measure tran p4_recovery_medium_tail MAX v(medium_out,vss_a) FROM=3.382000000000e-08 TO=3.402000000000e-08
.measure tran p4_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=3.382000000000e-08 TO=3.402000000000e-08
.measure tran p5_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=3.452000000000e-08
.measure tran p5_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=3.452000000000e-08
.measure tran p5_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=3.452000000000e-08
.measure tran p5_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=3.452000000000e-08
.measure tran p5_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=3.452000000000e-08
.measure tran p5_q_read_v FIND v(q_final,vss_a) AT=3.682000000000e-08
.measure tran p5_xor_peak MAX v(xor_29,vss_a) FROM=3.452000000000e-08 TO=3.722000000000e-08
.measure tran p5_ck_peak MAX v(dff_ck,vss_a) FROM=3.452000000000e-08 TO=3.722000000000e-08
.measure tran p5_recovery_xor_end FIND v(xor_29,vss_a) AT=4.022000000000e-08
.measure tran p5_recovery_medium_end FIND v(medium_out,vss_a) AT=4.022000000000e-08
.measure tran p5_recovery_ck_end FIND v(dff_ck,vss_a) AT=4.022000000000e-08
.measure tran p5_recovery_xor_tail MAX v(xor_29,vss_a) FROM=4.002000000000e-08 TO=4.022000000000e-08
.measure tran p5_recovery_medium_tail MAX v(medium_out,vss_a) FROM=4.002000000000e-08 TO=4.022000000000e-08
.measure tran p5_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=4.002000000000e-08 TO=4.022000000000e-08
.measure tran p6_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=4.223000000000e-08
.measure tran p6_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=4.223000000000e-08
.measure tran p6_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=4.223000000000e-08
.measure tran p6_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=4.223000000000e-08
.measure tran p6_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=4.223000000000e-08
.measure tran p6_q_read_v FIND v(q_final,vss_a) AT=4.453000000000e-08
.measure tran p6_xor_peak MAX v(xor_29,vss_a) FROM=4.223000000000e-08 TO=4.493000000000e-08
.measure tran p6_ck_peak MAX v(dff_ck,vss_a) FROM=4.223000000000e-08 TO=4.493000000000e-08
.measure tran p6_recovery_xor_end FIND v(xor_29,vss_a) AT=4.793000000000e-08
.measure tran p6_recovery_medium_end FIND v(medium_out,vss_a) AT=4.793000000000e-08
.measure tran p6_recovery_ck_end FIND v(dff_ck,vss_a) AT=4.793000000000e-08
.measure tran p6_recovery_xor_tail MAX v(xor_29,vss_a) FROM=4.773000000000e-08 TO=4.793000000000e-08
.measure tran p6_recovery_medium_tail MAX v(medium_out,vss_a) FROM=4.773000000000e-08 TO=4.793000000000e-08
.measure tran p6_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=4.773000000000e-08 TO=4.793000000000e-08
.measure tran p7_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=4.843000000000e-08
.measure tran p7_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=4.843000000000e-08
.measure tran p7_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=4.843000000000e-08
.measure tran p7_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=4.843000000000e-08
.measure tran p7_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=4.843000000000e-08
.measure tran p7_q_read_v FIND v(q_final,vss_a) AT=5.073000000000e-08
.measure tran p7_xor_peak MAX v(xor_29,vss_a) FROM=4.843000000000e-08 TO=5.113000000000e-08
.measure tran p7_ck_peak MAX v(dff_ck,vss_a) FROM=4.843000000000e-08 TO=5.113000000000e-08
.measure tran p7_recovery_xor_end FIND v(xor_29,vss_a) AT=5.413000000000e-08
.measure tran p7_recovery_medium_end FIND v(medium_out,vss_a) AT=5.413000000000e-08
.measure tran p7_recovery_ck_end FIND v(dff_ck,vss_a) AT=5.413000000000e-08
.measure tran p7_recovery_xor_tail MAX v(xor_29,vss_a) FROM=5.393000000000e-08 TO=5.413000000000e-08
.measure tran p7_recovery_medium_tail MAX v(medium_out,vss_a) FROM=5.393000000000e-08 TO=5.413000000000e-08
.measure tran p7_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=5.393000000000e-08 TO=5.413000000000e-08
.measure tran p8_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=5.614000000000e-08
.measure tran p8_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=5.614000000000e-08
.measure tran p8_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=5.614000000000e-08
.measure tran p8_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=5.614000000000e-08
.measure tran p8_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=5.614000000000e-08
.measure tran p8_q_read_v FIND v(q_final,vss_a) AT=5.844000000000e-08
.measure tran p8_xor_peak MAX v(xor_29,vss_a) FROM=5.614000000000e-08 TO=5.884000000000e-08
.measure tran p8_ck_peak MAX v(dff_ck,vss_a) FROM=5.614000000000e-08 TO=5.884000000000e-08
.measure tran p8_recovery_xor_end FIND v(xor_29,vss_a) AT=6.184000000000e-08
.measure tran p8_recovery_medium_end FIND v(medium_out,vss_a) AT=6.184000000000e-08
.measure tran p8_recovery_ck_end FIND v(dff_ck,vss_a) AT=6.184000000000e-08
.measure tran p8_recovery_xor_tail MAX v(xor_29,vss_a) FROM=6.164000000000e-08 TO=6.184000000000e-08
.measure tran p8_recovery_medium_tail MAX v(medium_out,vss_a) FROM=6.164000000000e-08 TO=6.184000000000e-08
.measure tran p8_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=6.164000000000e-08 TO=6.184000000000e-08
.measure tran p9_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=6.234000000000e-08
.measure tran p9_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=6.234000000000e-08
.measure tran p9_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=6.234000000000e-08
.measure tran p9_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=6.234000000000e-08
.measure tran p9_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=6.234000000000e-08
.measure tran p9_q_read_v FIND v(q_final,vss_a) AT=6.464000000000e-08
.measure tran p9_xor_peak MAX v(xor_29,vss_a) FROM=6.234000000000e-08 TO=6.504000000000e-08
.measure tran p9_ck_peak MAX v(dff_ck,vss_a) FROM=6.234000000000e-08 TO=6.504000000000e-08
.measure tran p9_recovery_xor_end FIND v(xor_29,vss_a) AT=6.804000000000e-08
.measure tran p9_recovery_medium_end FIND v(medium_out,vss_a) AT=6.804000000000e-08
.measure tran p9_recovery_ck_end FIND v(dff_ck,vss_a) AT=6.804000000000e-08
.measure tran p9_recovery_xor_tail MAX v(xor_29,vss_a) FROM=6.784000000000e-08 TO=6.804000000000e-08
.measure tran p9_recovery_medium_tail MAX v(medium_out,vss_a) FROM=6.784000000000e-08 TO=6.804000000000e-08
.measure tran p9_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=6.784000000000e-08 TO=6.804000000000e-08
.measure tran p10_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=7.005000000000e-08
.measure tran p10_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=7.005000000000e-08
.measure tran p10_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=7.005000000000e-08
.measure tran p10_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=7.005000000000e-08
.measure tran p10_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=7.005000000000e-08
.measure tran p10_q_read_v FIND v(q_final,vss_a) AT=7.235000000000e-08
.measure tran p10_xor_peak MAX v(xor_29,vss_a) FROM=7.005000000000e-08 TO=7.275000000000e-08
.measure tran p10_ck_peak MAX v(dff_ck,vss_a) FROM=7.005000000000e-08 TO=7.275000000000e-08
.measure tran p10_recovery_xor_end FIND v(xor_29,vss_a) AT=7.575000000000e-08
.measure tran p10_recovery_medium_end FIND v(medium_out,vss_a) AT=7.575000000000e-08
.measure tran p10_recovery_ck_end FIND v(dff_ck,vss_a) AT=7.575000000000e-08
.measure tran p10_recovery_xor_tail MAX v(xor_29,vss_a) FROM=7.555000000000e-08 TO=7.575000000000e-08
.measure tran p10_recovery_medium_tail MAX v(medium_out,vss_a) FROM=7.555000000000e-08 TO=7.575000000000e-08
.measure tran p10_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=7.555000000000e-08 TO=7.575000000000e-08
.measure tran p11_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=7.625000000000e-08
.measure tran p11_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=7.625000000000e-08
.measure tran p11_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=7.625000000000e-08
.measure tran p11_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=7.625000000000e-08
.measure tran p11_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=7.625000000000e-08
.measure tran p11_q_read_v FIND v(q_final,vss_a) AT=7.855000000000e-08
.measure tran p11_xor_peak MAX v(xor_29,vss_a) FROM=7.625000000000e-08 TO=7.895000000000e-08
.measure tran p11_ck_peak MAX v(dff_ck,vss_a) FROM=7.625000000000e-08 TO=7.895000000000e-08
.measure tran p11_recovery_xor_end FIND v(xor_29,vss_a) AT=8.195000000000e-08
.measure tran p11_recovery_medium_end FIND v(medium_out,vss_a) AT=8.195000000000e-08
.measure tran p11_recovery_ck_end FIND v(dff_ck,vss_a) AT=8.195000000000e-08
.measure tran p11_recovery_xor_tail MAX v(xor_29,vss_a) FROM=8.175000000000e-08 TO=8.195000000000e-08
.measure tran p11_recovery_medium_tail MAX v(medium_out,vss_a) FROM=8.175000000000e-08 TO=8.195000000000e-08
.measure tran p11_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=8.175000000000e-08 TO=8.195000000000e-08
.measure tran p12_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=8.396000000000e-08
.measure tran p12_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=8.396000000000e-08
.measure tran p12_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=8.396000000000e-08
.measure tran p12_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=8.396000000000e-08
.measure tran p12_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=8.396000000000e-08
.measure tran p12_q_read_v FIND v(q_final,vss_a) AT=8.626000000000e-08
.measure tran p12_xor_peak MAX v(xor_29,vss_a) FROM=8.396000000000e-08 TO=8.666000000000e-08
.measure tran p12_ck_peak MAX v(dff_ck,vss_a) FROM=8.396000000000e-08 TO=8.666000000000e-08
.measure tran p12_recovery_xor_end FIND v(xor_29,vss_a) AT=8.966000000000e-08
.measure tran p12_recovery_medium_end FIND v(medium_out,vss_a) AT=8.966000000000e-08
.measure tran p12_recovery_ck_end FIND v(dff_ck,vss_a) AT=8.966000000000e-08
.measure tran p12_recovery_xor_tail MAX v(xor_29,vss_a) FROM=8.946000000000e-08 TO=8.966000000000e-08
.measure tran p12_recovery_medium_tail MAX v(medium_out,vss_a) FROM=8.946000000000e-08 TO=8.966000000000e-08
.measure tran p12_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=8.946000000000e-08 TO=8.966000000000e-08
.measure tran p13_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=9.016000000000e-08
.measure tran p13_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=9.016000000000e-08
.measure tran p13_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=9.016000000000e-08
.measure tran p13_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=9.016000000000e-08
.measure tran p13_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=9.016000000000e-08
.measure tran p13_q_read_v FIND v(q_final,vss_a) AT=9.246000000000e-08
.measure tran p13_xor_peak MAX v(xor_29,vss_a) FROM=9.016000000000e-08 TO=9.286000000000e-08
.measure tran p13_ck_peak MAX v(dff_ck,vss_a) FROM=9.016000000000e-08 TO=9.286000000000e-08
.measure tran p13_recovery_xor_end FIND v(xor_29,vss_a) AT=9.586000000000e-08
.measure tran p13_recovery_medium_end FIND v(medium_out,vss_a) AT=9.586000000000e-08
.measure tran p13_recovery_ck_end FIND v(dff_ck,vss_a) AT=9.586000000000e-08
.measure tran p13_recovery_xor_tail MAX v(xor_29,vss_a) FROM=9.566000000000e-08 TO=9.586000000000e-08
.measure tran p13_recovery_medium_tail MAX v(medium_out,vss_a) FROM=9.566000000000e-08 TO=9.586000000000e-08
.measure tran p13_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=9.566000000000e-08 TO=9.586000000000e-08
.measure tran p14_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=9.787000000000e-08
.measure tran p14_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=9.787000000000e-08
.measure tran p14_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=9.787000000000e-08
.measure tran p14_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=9.787000000000e-08
.measure tran p14_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=9.787000000000e-08
.measure tran p14_q_read_v FIND v(q_final,vss_a) AT=1.001700000000e-07
.measure tran p14_xor_peak MAX v(xor_29,vss_a) FROM=9.787000000000e-08 TO=1.005700000000e-07
.measure tran p14_ck_peak MAX v(dff_ck,vss_a) FROM=9.787000000000e-08 TO=1.005700000000e-07
.measure tran p14_recovery_xor_end FIND v(xor_29,vss_a) AT=1.035700000000e-07
.measure tran p14_recovery_medium_end FIND v(medium_out,vss_a) AT=1.035700000000e-07
.measure tran p14_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.035700000000e-07
.measure tran p14_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.033700000000e-07 TO=1.035700000000e-07
.measure tran p14_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.033700000000e-07 TO=1.035700000000e-07
.measure tran p14_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.033700000000e-07 TO=1.035700000000e-07
.measure tran p15_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.040700000000e-07
.measure tran p15_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.040700000000e-07
.measure tran p15_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.040700000000e-07
.measure tran p15_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.040700000000e-07
.measure tran p15_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.040700000000e-07
.measure tran p15_q_read_v FIND v(q_final,vss_a) AT=1.063700000000e-07
.measure tran p15_xor_peak MAX v(xor_29,vss_a) FROM=1.040700000000e-07 TO=1.067700000000e-07
.measure tran p15_ck_peak MAX v(dff_ck,vss_a) FROM=1.040700000000e-07 TO=1.067700000000e-07
.measure tran p15_recovery_xor_end FIND v(xor_29,vss_a) AT=1.097700000000e-07
.measure tran p15_recovery_medium_end FIND v(medium_out,vss_a) AT=1.097700000000e-07
.measure tran p15_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.097700000000e-07
.measure tran p15_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.095700000000e-07 TO=1.097700000000e-07
.measure tran p15_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.095700000000e-07 TO=1.097700000000e-07
.measure tran p15_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.095700000000e-07 TO=1.097700000000e-07
.measure tran p16_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.117800000000e-07
.measure tran p16_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.117800000000e-07
.measure tran p16_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.117800000000e-07
.measure tran p16_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.117800000000e-07
.measure tran p16_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.117800000000e-07
.measure tran p16_q_read_v FIND v(q_final,vss_a) AT=1.140800000000e-07
.measure tran p16_xor_peak MAX v(xor_29,vss_a) FROM=1.117800000000e-07 TO=1.144800000000e-07
.measure tran p16_ck_peak MAX v(dff_ck,vss_a) FROM=1.117800000000e-07 TO=1.144800000000e-07
.measure tran p16_recovery_xor_end FIND v(xor_29,vss_a) AT=1.174800000000e-07
.measure tran p16_recovery_medium_end FIND v(medium_out,vss_a) AT=1.174800000000e-07
.measure tran p16_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.174800000000e-07
.measure tran p16_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.172800000000e-07 TO=1.174800000000e-07
.measure tran p16_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.172800000000e-07 TO=1.174800000000e-07
.measure tran p16_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.172800000000e-07 TO=1.174800000000e-07
.measure tran p17_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.179800000000e-07
.measure tran p17_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.179800000000e-07
.measure tran p17_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.179800000000e-07
.measure tran p17_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.179800000000e-07
.measure tran p17_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.179800000000e-07
.measure tran p17_q_read_v FIND v(q_final,vss_a) AT=1.202800000000e-07
.measure tran p17_xor_peak MAX v(xor_29,vss_a) FROM=1.179800000000e-07 TO=1.206800000000e-07
.measure tran p17_ck_peak MAX v(dff_ck,vss_a) FROM=1.179800000000e-07 TO=1.206800000000e-07
.measure tran p17_recovery_xor_end FIND v(xor_29,vss_a) AT=1.236800000000e-07
.measure tran p17_recovery_medium_end FIND v(medium_out,vss_a) AT=1.236800000000e-07
.measure tran p17_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.236800000000e-07
.measure tran p17_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.234800000000e-07 TO=1.236800000000e-07
.measure tran p17_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.234800000000e-07 TO=1.236800000000e-07
.measure tran p17_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.234800000000e-07 TO=1.236800000000e-07
.measure tran p18_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.256900000000e-07
.measure tran p18_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.256900000000e-07
.measure tran p18_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.256900000000e-07
.measure tran p18_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.256900000000e-07
.measure tran p18_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.256900000000e-07
.measure tran p18_q_read_v FIND v(q_final,vss_a) AT=1.279900000000e-07
.measure tran p18_xor_peak MAX v(xor_29,vss_a) FROM=1.256900000000e-07 TO=1.283900000000e-07
.measure tran p18_ck_peak MAX v(dff_ck,vss_a) FROM=1.256900000000e-07 TO=1.283900000000e-07
.measure tran p18_recovery_xor_end FIND v(xor_29,vss_a) AT=1.313900000000e-07
.measure tran p18_recovery_medium_end FIND v(medium_out,vss_a) AT=1.313900000000e-07
.measure tran p18_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.313900000000e-07
.measure tran p18_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.311900000000e-07 TO=1.313900000000e-07
.measure tran p18_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.311900000000e-07 TO=1.313900000000e-07
.measure tran p18_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.311900000000e-07 TO=1.313900000000e-07
.measure tran p19_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.318900000000e-07
.measure tran p19_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.318900000000e-07
.measure tran p19_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.318900000000e-07
.measure tran p19_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.318900000000e-07
.measure tran p19_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.318900000000e-07
.measure tran p19_q_read_v FIND v(q_final,vss_a) AT=1.341900000000e-07
.measure tran p19_xor_peak MAX v(xor_29,vss_a) FROM=1.318900000000e-07 TO=1.345900000000e-07
.measure tran p19_ck_peak MAX v(dff_ck,vss_a) FROM=1.318900000000e-07 TO=1.345900000000e-07
.measure tran p19_recovery_xor_end FIND v(xor_29,vss_a) AT=1.375900000000e-07
.measure tran p19_recovery_medium_end FIND v(medium_out,vss_a) AT=1.375900000000e-07
.measure tran p19_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.375900000000e-07
.measure tran p19_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.373900000000e-07 TO=1.375900000000e-07
.measure tran p19_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.373900000000e-07 TO=1.375900000000e-07
.measure tran p19_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.373900000000e-07 TO=1.375900000000e-07
.measure tran p20_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.411100000000e-07
.measure tran p20_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.411100000000e-07
.measure tran p20_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.411100000000e-07
.measure tran p20_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.411100000000e-07
.measure tran p20_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.411100000000e-07
.measure tran p20_q_read_v FIND v(q_final,vss_a) AT=1.434100000000e-07
.measure tran p20_xor_peak MAX v(xor_29,vss_a) FROM=1.411100000000e-07 TO=1.438100000000e-07
.measure tran p20_ck_peak MAX v(dff_ck,vss_a) FROM=1.411100000000e-07 TO=1.438100000000e-07
.measure tran p20_recovery_xor_end FIND v(xor_29,vss_a) AT=1.468100000000e-07
.measure tran p20_recovery_medium_end FIND v(medium_out,vss_a) AT=1.468100000000e-07
.measure tran p20_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.468100000000e-07
.measure tran p20_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.466100000000e-07 TO=1.468100000000e-07
.measure tran p20_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.466100000000e-07 TO=1.468100000000e-07
.measure tran p20_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.466100000000e-07 TO=1.468100000000e-07
.measure tran p21_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.488200000000e-07
.measure tran p21_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.488200000000e-07
.measure tran p21_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.488200000000e-07
.measure tran p21_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.488200000000e-07
.measure tran p21_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.488200000000e-07
.measure tran p21_q_read_v FIND v(q_final,vss_a) AT=1.511200000000e-07
.measure tran p21_xor_peak MAX v(xor_29,vss_a) FROM=1.488200000000e-07 TO=1.515200000000e-07
.measure tran p21_ck_peak MAX v(dff_ck,vss_a) FROM=1.488200000000e-07 TO=1.515200000000e-07
.measure tran p21_recovery_xor_end FIND v(xor_29,vss_a) AT=1.545200000000e-07
.measure tran p21_recovery_medium_end FIND v(medium_out,vss_a) AT=1.545200000000e-07
.measure tran p21_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.545200000000e-07
.measure tran p21_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.543200000000e-07 TO=1.545200000000e-07
.measure tran p21_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.543200000000e-07 TO=1.545200000000e-07
.measure tran p21_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.543200000000e-07 TO=1.545200000000e-07
.measure tran p22_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.565300000000e-07
.measure tran p22_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.565300000000e-07
.measure tran p22_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.565300000000e-07
.measure tran p22_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.565300000000e-07
.measure tran p22_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.565300000000e-07
.measure tran p22_q_read_v FIND v(q_final,vss_a) AT=1.588300000000e-07
.measure tran p22_xor_peak MAX v(xor_29,vss_a) FROM=1.565300000000e-07 TO=1.592300000000e-07
.measure tran p22_ck_peak MAX v(dff_ck,vss_a) FROM=1.565300000000e-07 TO=1.592300000000e-07
.measure tran p22_recovery_xor_end FIND v(xor_29,vss_a) AT=1.622300000000e-07
.measure tran p22_recovery_medium_end FIND v(medium_out,vss_a) AT=1.622300000000e-07
.measure tran p22_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.622300000000e-07
.measure tran p22_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.620300000000e-07 TO=1.622300000000e-07
.measure tran p22_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.620300000000e-07 TO=1.622300000000e-07
.measure tran p22_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.620300000000e-07 TO=1.622300000000e-07
.measure tran p23_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.642400000000e-07
.measure tran p23_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.642400000000e-07
.measure tran p23_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.642400000000e-07
.measure tran p23_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.642400000000e-07
.measure tran p23_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.642400000000e-07
.measure tran p23_q_read_v FIND v(q_final,vss_a) AT=1.665400000000e-07
.measure tran p23_xor_peak MAX v(xor_29,vss_a) FROM=1.642400000000e-07 TO=1.669400000000e-07
.measure tran p23_ck_peak MAX v(dff_ck,vss_a) FROM=1.642400000000e-07 TO=1.669400000000e-07
.measure tran p23_recovery_xor_end FIND v(xor_29,vss_a) AT=1.699400000000e-07
.measure tran p23_recovery_medium_end FIND v(medium_out,vss_a) AT=1.699400000000e-07
.measure tran p23_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.699400000000e-07
.measure tran p23_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.697400000000e-07 TO=1.699400000000e-07
.measure tran p23_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.697400000000e-07 TO=1.699400000000e-07
.measure tran p23_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.697400000000e-07 TO=1.699400000000e-07
.measure tran p24_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.719500000000e-07
.measure tran p24_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.719500000000e-07
.measure tran p24_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.719500000000e-07
.measure tran p24_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.719500000000e-07
.measure tran p24_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.719500000000e-07
.measure tran p24_q_read_v FIND v(q_final,vss_a) AT=1.742500000000e-07
.measure tran p24_xor_peak MAX v(xor_29,vss_a) FROM=1.719500000000e-07 TO=1.746500000000e-07
.measure tran p24_ck_peak MAX v(dff_ck,vss_a) FROM=1.719500000000e-07 TO=1.746500000000e-07
.measure tran p24_recovery_xor_end FIND v(xor_29,vss_a) AT=1.776500000000e-07
.measure tran p24_recovery_medium_end FIND v(medium_out,vss_a) AT=1.776500000000e-07
.measure tran p24_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.776500000000e-07
.measure tran p24_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.774500000000e-07 TO=1.776500000000e-07
.measure tran p24_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.774500000000e-07 TO=1.776500000000e-07
.measure tran p24_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.774500000000e-07 TO=1.776500000000e-07
.measure tran p25_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.796600000000e-07
.measure tran p25_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.796600000000e-07
.measure tran p25_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.796600000000e-07
.measure tran p25_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.796600000000e-07
.measure tran p25_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.796600000000e-07
.measure tran p25_q_read_v FIND v(q_final,vss_a) AT=1.819600000000e-07
.measure tran p25_xor_peak MAX v(xor_29,vss_a) FROM=1.796600000000e-07 TO=1.823600000000e-07
.measure tran p25_ck_peak MAX v(dff_ck,vss_a) FROM=1.796600000000e-07 TO=1.823600000000e-07
.measure tran p25_recovery_xor_end FIND v(xor_29,vss_a) AT=1.853600000000e-07
.measure tran p25_recovery_medium_end FIND v(medium_out,vss_a) AT=1.853600000000e-07
.measure tran p25_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.853600000000e-07
.measure tran p25_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.851600000000e-07 TO=1.853600000000e-07
.measure tran p25_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.851600000000e-07 TO=1.853600000000e-07
.measure tran p25_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.851600000000e-07 TO=1.853600000000e-07
.measure tran p26_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.873700000000e-07
.measure tran p26_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.873700000000e-07
.measure tran p26_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.873700000000e-07
.measure tran p26_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.873700000000e-07
.measure tran p26_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.873700000000e-07
.measure tran p26_q_read_v FIND v(q_final,vss_a) AT=1.896700000000e-07
.measure tran p26_xor_peak MAX v(xor_29,vss_a) FROM=1.873700000000e-07 TO=1.900700000000e-07
.measure tran p26_ck_peak MAX v(dff_ck,vss_a) FROM=1.873700000000e-07 TO=1.900700000000e-07
.measure tran p26_recovery_xor_end FIND v(xor_29,vss_a) AT=1.930700000000e-07
.measure tran p26_recovery_medium_end FIND v(medium_out,vss_a) AT=1.930700000000e-07
.measure tran p26_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.930700000000e-07
.measure tran p26_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.928700000000e-07 TO=1.930700000000e-07
.measure tran p26_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.928700000000e-07 TO=1.930700000000e-07
.measure tran p26_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.928700000000e-07 TO=1.930700000000e-07
.measure tran p27_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.935700000000e-07
.measure tran p27_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.935700000000e-07
.measure tran p27_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.935700000000e-07
.measure tran p27_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.935700000000e-07
.measure tran p27_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.935700000000e-07
.measure tran p27_q_read_v FIND v(q_final,vss_a) AT=1.958700000000e-07
.measure tran p27_xor_peak MAX v(xor_29,vss_a) FROM=1.935700000000e-07 TO=1.962700000000e-07
.measure tran p27_ck_peak MAX v(dff_ck,vss_a) FROM=1.935700000000e-07 TO=1.962700000000e-07
.measure tran p27_recovery_xor_end FIND v(xor_29,vss_a) AT=1.992700000000e-07
.measure tran p27_recovery_medium_end FIND v(medium_out,vss_a) AT=1.992700000000e-07
.measure tran p27_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.992700000000e-07
.measure tran p27_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.990700000000e-07 TO=1.992700000000e-07
.measure tran p27_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.990700000000e-07 TO=1.992700000000e-07
.measure tran p27_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.990700000000e-07 TO=1.992700000000e-07
.measure tran tr0_xor_max MAX v(xor_29,vss_a) FROM=1.241000000000e-08 TO=1.390000000000e-08
.measure tran tr0_medium_max MAX v(medium_out,vss_a) FROM=1.241000000000e-08 TO=1.390000000000e-08
.measure tran tr0_ck_max MAX v(dff_ck,vss_a) FROM=1.241000000000e-08 TO=1.390000000000e-08
.measure tran tr0_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.241000000000e-08
.measure tran tr0_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.241000000000e-08
.measure tran tr0_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.241000000000e-08
.measure tran tr1_xor_max MAX v(xor_29,vss_a) FROM=2.632000000000e-08 TO=2.781000000000e-08
.measure tran tr1_medium_max MAX v(medium_out,vss_a) FROM=2.632000000000e-08 TO=2.781000000000e-08
.measure tran tr1_ck_max MAX v(dff_ck,vss_a) FROM=2.632000000000e-08 TO=2.781000000000e-08
.measure tran tr1_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=2.632000000000e-08
.measure tran tr1_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=2.632000000000e-08
.measure tran tr1_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=2.632000000000e-08
.measure tran tr2_xor_max MAX v(xor_29,vss_a) FROM=4.023000000000e-08 TO=4.172000000000e-08
.measure tran tr2_medium_max MAX v(medium_out,vss_a) FROM=4.023000000000e-08 TO=4.172000000000e-08
.measure tran tr2_ck_max MAX v(dff_ck,vss_a) FROM=4.023000000000e-08 TO=4.172000000000e-08
.measure tran tr2_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=4.023000000000e-08
.measure tran tr2_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=4.023000000000e-08
.measure tran tr2_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=4.023000000000e-08
.measure tran tr3_xor_max MAX v(xor_29,vss_a) FROM=5.414000000000e-08 TO=5.563000000000e-08
.measure tran tr3_medium_max MAX v(medium_out,vss_a) FROM=5.414000000000e-08 TO=5.563000000000e-08
.measure tran tr3_ck_max MAX v(dff_ck,vss_a) FROM=5.414000000000e-08 TO=5.563000000000e-08
.measure tran tr3_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=5.414000000000e-08
.measure tran tr3_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=5.414000000000e-08
.measure tran tr3_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=5.414000000000e-08
.measure tran tr4_xor_max MAX v(xor_29,vss_a) FROM=6.805000000000e-08 TO=6.954000000000e-08
.measure tran tr4_medium_max MAX v(medium_out,vss_a) FROM=6.805000000000e-08 TO=6.954000000000e-08
.measure tran tr4_ck_max MAX v(dff_ck,vss_a) FROM=6.805000000000e-08 TO=6.954000000000e-08
.measure tran tr4_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=6.805000000000e-08
.measure tran tr4_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=6.805000000000e-08
.measure tran tr4_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=6.805000000000e-08
.measure tran tr5_xor_max MAX v(xor_29,vss_a) FROM=8.196000000000e-08 TO=8.345000000000e-08
.measure tran tr5_medium_max MAX v(medium_out,vss_a) FROM=8.196000000000e-08 TO=8.345000000000e-08
.measure tran tr5_ck_max MAX v(dff_ck,vss_a) FROM=8.196000000000e-08 TO=8.345000000000e-08
.measure tran tr5_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=8.196000000000e-08
.measure tran tr5_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=8.196000000000e-08
.measure tran tr5_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=8.196000000000e-08
.measure tran tr6_xor_max MAX v(xor_29,vss_a) FROM=9.587000000000e-08 TO=9.736000000000e-08
.measure tran tr6_medium_max MAX v(medium_out,vss_a) FROM=9.587000000000e-08 TO=9.736000000000e-08
.measure tran tr6_ck_max MAX v(dff_ck,vss_a) FROM=9.587000000000e-08 TO=9.736000000000e-08
.measure tran tr6_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=9.587000000000e-08
.measure tran tr6_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=9.587000000000e-08
.measure tran tr6_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=9.587000000000e-08
.measure tran tr7_xor_max MAX v(xor_29,vss_a) FROM=1.097800000000e-07 TO=1.112700000000e-07
.measure tran tr7_medium_max MAX v(medium_out,vss_a) FROM=1.097800000000e-07 TO=1.112700000000e-07
.measure tran tr7_ck_max MAX v(dff_ck,vss_a) FROM=1.097800000000e-07 TO=1.112700000000e-07
.measure tran tr7_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.097800000000e-07
.measure tran tr7_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.097800000000e-07
.measure tran tr7_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.097800000000e-07
.measure tran tr8_xor_max MAX v(xor_29,vss_a) FROM=1.236900000000e-07 TO=1.251800000000e-07
.measure tran tr8_medium_max MAX v(medium_out,vss_a) FROM=1.236900000000e-07 TO=1.251800000000e-07
.measure tran tr8_ck_max MAX v(dff_ck,vss_a) FROM=1.236900000000e-07 TO=1.251800000000e-07
.measure tran tr8_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.236900000000e-07
.measure tran tr8_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.236900000000e-07
.measure tran tr8_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.236900000000e-07
.measure tran tr9_xor_max MAX v(xor_29,vss_a) FROM=1.376000000000e-07 TO=1.390900000000e-07
.measure tran tr9_medium_max MAX v(medium_out,vss_a) FROM=1.376000000000e-07 TO=1.390900000000e-07
.measure tran tr9_ck_max MAX v(dff_ck,vss_a) FROM=1.376000000000e-07 TO=1.390900000000e-07
.measure tran tr9_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.376000000000e-07
.measure tran tr9_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.376000000000e-07
.measure tran tr9_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.376000000000e-07
.measure tran tr10_xor_max MAX v(xor_29,vss_a) FROM=1.391100000000e-07 TO=1.406000000000e-07
.measure tran tr10_medium_max MAX v(medium_out,vss_a) FROM=1.391100000000e-07 TO=1.406000000000e-07
.measure tran tr10_ck_max MAX v(dff_ck,vss_a) FROM=1.391100000000e-07 TO=1.406000000000e-07
.measure tran tr10_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.391100000000e-07
.measure tran tr10_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.391100000000e-07
.measure tran tr10_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.391100000000e-07
.measure tran tr11_xor_max MAX v(xor_29,vss_a) FROM=1.468200000000e-07 TO=1.483100000000e-07
.measure tran tr11_medium_max MAX v(medium_out,vss_a) FROM=1.468200000000e-07 TO=1.483100000000e-07
.measure tran tr11_ck_max MAX v(dff_ck,vss_a) FROM=1.468200000000e-07 TO=1.483100000000e-07
.measure tran tr11_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.468200000000e-07
.measure tran tr11_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.468200000000e-07
.measure tran tr11_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.468200000000e-07
.measure tran tr12_xor_max MAX v(xor_29,vss_a) FROM=1.545300000000e-07 TO=1.560200000000e-07
.measure tran tr12_medium_max MAX v(medium_out,vss_a) FROM=1.545300000000e-07 TO=1.560200000000e-07
.measure tran tr12_ck_max MAX v(dff_ck,vss_a) FROM=1.545300000000e-07 TO=1.560200000000e-07
.measure tran tr12_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.545300000000e-07
.measure tran tr12_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.545300000000e-07
.measure tran tr12_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.545300000000e-07
.measure tran tr13_xor_max MAX v(xor_29,vss_a) FROM=1.622400000000e-07 TO=1.637300000000e-07
.measure tran tr13_medium_max MAX v(medium_out,vss_a) FROM=1.622400000000e-07 TO=1.637300000000e-07
.measure tran tr13_ck_max MAX v(dff_ck,vss_a) FROM=1.622400000000e-07 TO=1.637300000000e-07
.measure tran tr13_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.622400000000e-07
.measure tran tr13_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.622400000000e-07
.measure tran tr13_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.622400000000e-07
.measure tran tr14_xor_max MAX v(xor_29,vss_a) FROM=1.699500000000e-07 TO=1.714400000000e-07
.measure tran tr14_medium_max MAX v(medium_out,vss_a) FROM=1.699500000000e-07 TO=1.714400000000e-07
.measure tran tr14_ck_max MAX v(dff_ck,vss_a) FROM=1.699500000000e-07 TO=1.714400000000e-07
.measure tran tr14_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.699500000000e-07
.measure tran tr14_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.699500000000e-07
.measure tran tr14_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.699500000000e-07
.measure tran tr15_xor_max MAX v(xor_29,vss_a) FROM=1.776600000000e-07 TO=1.791500000000e-07
.measure tran tr15_medium_max MAX v(medium_out,vss_a) FROM=1.776600000000e-07 TO=1.791500000000e-07
.measure tran tr15_ck_max MAX v(dff_ck,vss_a) FROM=1.776600000000e-07 TO=1.791500000000e-07
.measure tran tr15_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.776600000000e-07
.measure tran tr15_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.776600000000e-07
.measure tran tr15_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.776600000000e-07
.measure tran tr16_xor_max MAX v(xor_29,vss_a) FROM=1.853700000000e-07 TO=1.868600000000e-07
.measure tran tr16_medium_max MAX v(medium_out,vss_a) FROM=1.853700000000e-07 TO=1.868600000000e-07
.measure tran tr16_ck_max MAX v(dff_ck,vss_a) FROM=1.853700000000e-07 TO=1.868600000000e-07
.measure tran tr16_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.853700000000e-07
.measure tran tr16_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.853700000000e-07
.measure tran tr16_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.853700000000e-07
.measure tran p0_q_read_late_v FIND v(q_final,vss_a) AT=3.000000000000e-09
.measure tran p1_q_read_late_v FIND v(q_final,vss_a) AT=9.200000000000e-09
.measure tran p2_q_read_late_v FIND v(q_final,vss_a) AT=1.691000000000e-08
.measure tran p3_q_read_late_v FIND v(q_final,vss_a) AT=2.311000000000e-08
.measure tran p4_q_read_late_v FIND v(q_final,vss_a) AT=3.082000000000e-08
.measure tran p5_q_read_late_v FIND v(q_final,vss_a) AT=3.702000000000e-08
.measure tran p6_q_read_late_v FIND v(q_final,vss_a) AT=4.473000000000e-08
.measure tran p7_q_read_late_v FIND v(q_final,vss_a) AT=5.093000000000e-08
.measure tran p8_q_read_late_v FIND v(q_final,vss_a) AT=5.864000000000e-08
.measure tran p9_q_read_late_v FIND v(q_final,vss_a) AT=6.484000000000e-08
.measure tran p10_q_read_late_v FIND v(q_final,vss_a) AT=7.255000000000e-08
.measure tran p11_q_read_late_v FIND v(q_final,vss_a) AT=7.875000000000e-08
.measure tran p12_q_read_late_v FIND v(q_final,vss_a) AT=8.646000000000e-08
.measure tran p13_q_read_late_v FIND v(q_final,vss_a) AT=9.266000000000e-08
.measure tran p14_q_read_late_v FIND v(q_final,vss_a) AT=1.003700000000e-07
.measure tran p15_q_read_late_v FIND v(q_final,vss_a) AT=1.065700000000e-07
.measure tran p16_q_read_late_v FIND v(q_final,vss_a) AT=1.142800000000e-07
.measure tran p17_q_read_late_v FIND v(q_final,vss_a) AT=1.204800000000e-07
.measure tran p18_q_read_late_v FIND v(q_final,vss_a) AT=1.281900000000e-07
.measure tran p19_q_read_late_v FIND v(q_final,vss_a) AT=1.343900000000e-07
.measure tran p20_q_read_late_v FIND v(q_final,vss_a) AT=1.436100000000e-07
.measure tran p21_q_read_late_v FIND v(q_final,vss_a) AT=1.513200000000e-07
.measure tran p22_q_read_late_v FIND v(q_final,vss_a) AT=1.590300000000e-07
.measure tran p23_q_read_late_v FIND v(q_final,vss_a) AT=1.667400000000e-07
.measure tran p24_q_read_late_v FIND v(q_final,vss_a) AT=1.744500000000e-07
.measure tran p25_q_read_late_v FIND v(q_final,vss_a) AT=1.821600000000e-07
.measure tran p26_q_read_late_v FIND v(q_final,vss_a) AT=1.898700000000e-07
.measure tran p27_q_read_late_v FIND v(q_final,vss_a) AT=1.960700000000e-07
.end
