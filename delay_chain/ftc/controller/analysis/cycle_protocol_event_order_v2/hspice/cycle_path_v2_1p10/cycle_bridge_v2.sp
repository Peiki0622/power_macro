* FTC dynamic startup calibration: frozen topology, PWL testbench controls.
.option post=0 nomod measform=3 measdgt=10 runlvl=3
.temp 2.500000000000e+01
.include "/home/zhupl25/chiplet_side_channel/chiplet_gds_data/chiplets/FIR/syn/runs/fir_smic40ll_tt_1310ps_spice_20260722_r1/spice/sc9mc_logic0040ll_base_rvt_c40.hspice.cdl"
.include "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/cdl/sc9mc_logic0040ll_base_lvt_c40.cdl"
.lib "/host/data/libtech/SMIC_40LL/PDK/SPDK40LL_1125_2TM_OA_CDS_V1.4/smic40ll_1125_2tm_oa_cds_1P7M_2012_10_11_v1.4/models/hspice/l0040ll_v1p4_1r.lib" tt
.param VDD_VALUE=1.100000000000e+00
V_VDD vdd_a vss_a 'VDD_VALUE'
V_VSS vss_a 0 0
V_SCLK s_clk vss_a PWL(0.000000000000e+00 0 9.990000000000e-10 0 1.000000000000e-09 'VDD_VALUE' 7.000000000000e-09 'VDD_VALUE' 7.001000000000e-09 0 1.099900000000e-08 0 1.100000000000e-08 'VDD_VALUE' 1.700000000000e-08 'VDD_VALUE' 1.700100000000e-08 0 2.299900000000e-08 0 2.300000000000e-08 'VDD_VALUE' 2.900000000000e-08 'VDD_VALUE' 2.900100000000e-08 0 3.299900000000e-08 0 3.300000000000e-08 'VDD_VALUE' 3.900000000000e-08 'VDD_VALUE' 3.900100000000e-08 0 4.499900000000e-08 0 4.500000000000e-08 'VDD_VALUE' 5.100000000000e-08 'VDD_VALUE' 5.100100000000e-08 0 5.499900000000e-08 0 5.500000000000e-08 'VDD_VALUE' 6.100000000000e-08 'VDD_VALUE' 6.100100000000e-08 0 6.699900000000e-08 0 6.700000000000e-08 'VDD_VALUE' 7.300000000000e-08 'VDD_VALUE' 7.300100000000e-08 0 7.699900000000e-08 0 7.700000000000e-08 'VDD_VALUE' 8.300000000000e-08 'VDD_VALUE' 8.300100000000e-08 0 8.899900000000e-08 0 8.900000000000e-08 'VDD_VALUE' 9.500000000000e-08 'VDD_VALUE' 9.500100000000e-08 0 9.899900000000e-08 0 9.900000000000e-08 'VDD_VALUE' 1.050000000000e-07 'VDD_VALUE' 1.050010000000e-07 0 1.129990000000e-07 0 1.130000000000e-07 'VDD_VALUE' 1.190000000000e-07 'VDD_VALUE' 1.190010000000e-07 0 1.249990000000e-07 0 1.250000000000e-07 'VDD_VALUE' 1.310000000000e-07 'VDD_VALUE' 1.310010000000e-07 0 1.369990000000e-07 0 1.370000000000e-07 'VDD_VALUE' 1.430000000000e-07 'VDD_VALUE' 1.430010000000e-07 0 1.489990000000e-07 0 1.490000000000e-07 'VDD_VALUE' 1.550000000000e-07 'VDD_VALUE' 1.550010000000e-07 0 1.609990000000e-07 0 1.610000000000e-07 'VDD_VALUE' 1.670000000000e-07 'VDD_VALUE' 1.670010000000e-07 0 1.729990000000e-07 0 1.730000000000e-07 'VDD_VALUE' 1.790000000000e-07 'VDD_VALUE' 1.790010000000e-07 0 1.849990000000e-07 0 1.850000000000e-07 'VDD_VALUE' 1.910000000000e-07 'VDD_VALUE' 1.910010000000e-07 0 1.969990000000e-07 0 1.970000000000e-07 'VDD_VALUE' 2.030000000000e-07 'VDD_VALUE' 2.030010000000e-07 0 2.089990000000e-07 0 2.090000000000e-07 'VDD_VALUE' 2.150000000000e-07 'VDD_VALUE' 2.150010000000e-07 0 2.209990000000e-07 0 2.210000000000e-07 'VDD_VALUE' 2.270000000000e-07 'VDD_VALUE' 2.270010000000e-07 0 2.309990000000e-07 0 2.310000000000e-07 'VDD_VALUE' 2.370000000000e-07 'VDD_VALUE' 2.370010000000e-07 0)
V_DFF_RESET dff_reset vss_a PWL(0.000000000000e+00 'VDD_VALUE' -1.000000000000e-11 'VDD_VALUE' 0.000000000000e+00 'VDD_VALUE' 1.000000000000e-11 0 6.000000000000e-09 0 6.010000000000e-09 'VDD_VALUE' 9.990000000000e-09 'VDD_VALUE' 1.000000000000e-08 'VDD_VALUE' 1.001000000000e-08 0 1.600000000000e-08 0 1.601000000000e-08 'VDD_VALUE' 2.199000000000e-08 'VDD_VALUE' 2.200000000000e-08 'VDD_VALUE' 2.201000000000e-08 0 2.800000000000e-08 0 2.801000000000e-08 'VDD_VALUE' 3.199000000000e-08 'VDD_VALUE' 3.200000000000e-08 'VDD_VALUE' 3.201000000000e-08 0 3.800000000000e-08 0 3.801000000000e-08 'VDD_VALUE' 4.399000000000e-08 'VDD_VALUE' 4.400000000000e-08 'VDD_VALUE' 4.401000000000e-08 0 5.000000000000e-08 0 5.001000000000e-08 'VDD_VALUE' 5.399000000000e-08 'VDD_VALUE' 5.400000000000e-08 'VDD_VALUE' 5.401000000000e-08 0 6.000000000000e-08 0 6.001000000000e-08 'VDD_VALUE' 6.599000000000e-08 'VDD_VALUE' 6.600000000000e-08 'VDD_VALUE' 6.601000000000e-08 0 7.200000000000e-08 0 7.201000000000e-08 'VDD_VALUE' 7.599000000000e-08 'VDD_VALUE' 7.600000000000e-08 'VDD_VALUE' 7.601000000000e-08 0 8.200000000000e-08 0 8.201000000000e-08 'VDD_VALUE' 8.799000000000e-08 'VDD_VALUE' 8.800000000000e-08 'VDD_VALUE' 8.801000000000e-08 0 9.400000000000e-08 0 9.401000000000e-08 'VDD_VALUE' 9.799000000000e-08 'VDD_VALUE' 9.800000000000e-08 'VDD_VALUE' 9.801000000000e-08 0 1.040000000000e-07 0 1.040100000000e-07 'VDD_VALUE' 1.119900000000e-07 'VDD_VALUE' 1.120000000000e-07 'VDD_VALUE' 1.120100000000e-07 0 1.180000000000e-07 0 1.180100000000e-07 'VDD_VALUE' 1.239900000000e-07 'VDD_VALUE' 1.240000000000e-07 'VDD_VALUE' 1.240100000000e-07 0 1.300000000000e-07 0 1.300100000000e-07 'VDD_VALUE' 1.359900000000e-07 'VDD_VALUE' 1.360000000000e-07 'VDD_VALUE' 1.360100000000e-07 0 1.420000000000e-07 0 1.420100000000e-07 'VDD_VALUE' 1.479900000000e-07 'VDD_VALUE' 1.480000000000e-07 'VDD_VALUE' 1.480100000000e-07 0 1.540000000000e-07 0 1.540100000000e-07 'VDD_VALUE' 1.599900000000e-07 'VDD_VALUE' 1.600000000000e-07 'VDD_VALUE' 1.600100000000e-07 0 1.660000000000e-07 0 1.660100000000e-07 'VDD_VALUE' 1.719900000000e-07 'VDD_VALUE' 1.720000000000e-07 'VDD_VALUE' 1.720100000000e-07 0 1.780000000000e-07 0 1.780100000000e-07 'VDD_VALUE' 1.839900000000e-07 'VDD_VALUE' 1.840000000000e-07 'VDD_VALUE' 1.840100000000e-07 0 1.900000000000e-07 0 1.900100000000e-07 'VDD_VALUE' 1.959900000000e-07 'VDD_VALUE' 1.960000000000e-07 'VDD_VALUE' 1.960100000000e-07 0 2.020000000000e-07 0 2.020100000000e-07 'VDD_VALUE' 2.079900000000e-07 'VDD_VALUE' 2.080000000000e-07 'VDD_VALUE' 2.080100000000e-07 0 2.140000000000e-07 0 2.140100000000e-07 'VDD_VALUE' 2.199900000000e-07 'VDD_VALUE' 2.200000000000e-07 'VDD_VALUE' 2.200100000000e-07 0 2.260000000000e-07 0 2.260100000000e-07 'VDD_VALUE' 2.299900000000e-07 'VDD_VALUE' 2.300000000000e-07 'VDD_VALUE' 2.300100000000e-07 0 2.360000000000e-07 0 2.360100000000e-07 'VDD_VALUE')
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
V_M_00 m_0 vss_a PWL(0.000000000000e+00 0 2.000000000000e-08 0 2.001000000000e-08 'VDD_VALUE' 2.420000000000e-07 'VDD_VALUE')
V_M_01 m_1 vss_a PWL(0.000000000000e+00 0 4.200000000000e-08 0 4.201000000000e-08 'VDD_VALUE' 2.420000000000e-07 'VDD_VALUE')
V_M_02 m_2 vss_a PWL(0.000000000000e+00 0 6.400000000000e-08 0 6.401000000000e-08 'VDD_VALUE' 1.100000000000e-07 'VDD_VALUE' 1.100100000000e-07 0 2.420000000000e-07 0)
V_M_03 m_3 vss_a PWL(0.000000000000e+00 0 8.600000000000e-08 0 8.601000000000e-08 'VDD_VALUE' 1.080000000000e-07 'VDD_VALUE' 1.080100000000e-07 0 2.420000000000e-07 0)
V_M_04 m_4 vss_a PWL(0.000000000000e+00 0 2.420000000000e-07 0)
V_M_05 m_5 vss_a PWL(0.000000000000e+00 0 2.420000000000e-07 0)
V_M_06 m_6 vss_a PWL(0.000000000000e+00 0 2.420000000000e-07 0)
V_M_07 m_7 vss_a PWL(0.000000000000e+00 0 2.420000000000e-07 0)
V_M_08 m_8 vss_a PWL(0.000000000000e+00 0 2.420000000000e-07 0)
V_M_09 m_9 vss_a PWL(0.000000000000e+00 0 2.420000000000e-07 0)
V_M_10 m_10 vss_a PWL(0.000000000000e+00 0 2.420000000000e-07 0)
V_M_11 m_11 vss_a PWL(0.000000000000e+00 0 2.420000000000e-07 0)
V_M_12 m_12 vss_a PWL(0.000000000000e+00 0 2.420000000000e-07 0)
V_M_13 m_13 vss_a PWL(0.000000000000e+00 0 2.420000000000e-07 0)
V_M_14 m_14 vss_a PWL(0.000000000000e+00 0 2.420000000000e-07 0)
V_M_15 m_15 vss_a PWL(0.000000000000e+00 0 2.420000000000e-07 0)
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
V_F_00 f_0 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 1.220000000000e-07 'VDD_VALUE' 1.220100000000e-07 0 2.420000000000e-07 0)
XLOAD_00 z_0 vdd_a vdd_a vss_a vss_a dff_ck f_0 NOR2_X4A_A9TL40
V_F_01 f_1 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 1.340000000000e-07 'VDD_VALUE' 1.340100000000e-07 0 2.420000000000e-07 0)
XLOAD_01 z_1 vdd_a vdd_a vss_a vss_a dff_ck f_1 NOR2_X4A_A9TL40
V_F_02 f_2 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 1.460000000000e-07 'VDD_VALUE' 1.460100000000e-07 0 2.420000000000e-07 0)
XLOAD_02 z_2 vdd_a vdd_a vss_a vss_a dff_ck f_2 NOR2_X4A_A9TL40
V_F_03 f_3 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 1.580000000000e-07 'VDD_VALUE' 1.580100000000e-07 0 2.420000000000e-07 0)
XLOAD_03 z_3 vdd_a vdd_a vss_a vss_a dff_ck f_3 NOR2_X4A_A9TL40
V_F_04 f_4 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 1.700000000000e-07 'VDD_VALUE' 1.700100000000e-07 0 2.420000000000e-07 0)
XLOAD_04 z_4 vdd_a vdd_a vss_a vss_a dff_ck f_4 NOR2_X4A_A9TL40
V_F_05 f_5 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 1.820000000000e-07 'VDD_VALUE' 1.820100000000e-07 0 2.420000000000e-07 0)
XLOAD_05 z_5 vdd_a vdd_a vss_a vss_a dff_ck f_5 NOR2_X4A_A9TL40
V_F_06 f_6 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 1.940000000000e-07 'VDD_VALUE' 1.940100000000e-07 0 2.420000000000e-07 0)
XLOAD_06 z_6 vdd_a vdd_a vss_a vss_a dff_ck f_6 NOR2_X4A_A9TL40
V_F_07 f_7 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 2.060000000000e-07 'VDD_VALUE' 2.060100000000e-07 0 2.420000000000e-07 0)
XLOAD_07 z_7 vdd_a vdd_a vss_a vss_a dff_ck f_7 NOR2_X4A_A9TL40
V_F_08 f_8 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 2.180000000000e-07 'VDD_VALUE' 2.180100000000e-07 0 2.420000000000e-07 0)
XLOAD_08 z_8 vdd_a vdd_a vss_a vss_a dff_ck f_8 NOR2_X4A_A9TL40
V_F_09 f_9 vss_a PWL(0.000000000000e+00 'VDD_VALUE' 2.420000000000e-07 'VDD_VALUE')
XLOAD_09 z_9 vdd_a vdd_a vss_a vss_a dff_ck f_9 NOR2_X4A_A9TL40
XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset DFFRPQ_X0P5M_A9TR40
.tran 1.000000000000e-12 2.420000000000e-07
.measure tran p0_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.000000000000e-09
.measure tran p0_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.000000000000e-09
.measure tran p0_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.000000000000e-09
.measure tran p0_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.000000000000e-09
.measure tran p0_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.000000000000e-09
.measure tran p0_q_read_v FIND v(q_final,vss_a) AT=4.000000000000e-09
.measure tran p0_xor_peak MAX v(xor_29,vss_a) FROM=1.000000000000e-09 TO=6.000000000000e-09
.measure tran p0_ck_peak MAX v(dff_ck,vss_a) FROM=1.000000000000e-09 TO=6.000000000000e-09
.measure tran p0_recovery_xor_end FIND v(xor_29,vss_a) AT=1.000000000000e-08
.measure tran p0_recovery_medium_end FIND v(medium_out,vss_a) AT=1.000000000000e-08
.measure tran p0_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.000000000000e-08
.measure tran p0_recovery_xor_tail MAX v(xor_29,vss_a) FROM=9.800000000000e-09 TO=1.000000000000e-08
.measure tran p0_recovery_medium_tail MAX v(medium_out,vss_a) FROM=9.800000000000e-09 TO=1.000000000000e-08
.measure tran p0_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=9.800000000000e-09 TO=1.000000000000e-08
.measure tran p1_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.100000000000e-08
.measure tran p1_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.100000000000e-08
.measure tran p1_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.100000000000e-08
.measure tran p1_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.100000000000e-08
.measure tran p1_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.100000000000e-08
.measure tran p1_q_read_v FIND v(q_final,vss_a) AT=1.400000000000e-08
.measure tran p1_xor_peak MAX v(xor_29,vss_a) FROM=1.100000000000e-08 TO=1.600000000000e-08
.measure tran p1_ck_peak MAX v(dff_ck,vss_a) FROM=1.100000000000e-08 TO=1.600000000000e-08
.measure tran p1_recovery_xor_end FIND v(xor_29,vss_a) AT=2.000000000000e-08
.measure tran p1_recovery_medium_end FIND v(medium_out,vss_a) AT=2.000000000000e-08
.measure tran p1_recovery_ck_end FIND v(dff_ck,vss_a) AT=2.000000000000e-08
.measure tran p1_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.980000000000e-08 TO=2.000000000000e-08
.measure tran p1_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.980000000000e-08 TO=2.000000000000e-08
.measure tran p1_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.980000000000e-08 TO=2.000000000000e-08
.measure tran p2_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=2.300000000000e-08
.measure tran p2_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=2.300000000000e-08
.measure tran p2_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=2.300000000000e-08
.measure tran p2_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=2.300000000000e-08
.measure tran p2_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=2.300000000000e-08
.measure tran p2_q_read_v FIND v(q_final,vss_a) AT=2.600000000000e-08
.measure tran p2_xor_peak MAX v(xor_29,vss_a) FROM=2.300000000000e-08 TO=2.800000000000e-08
.measure tran p2_ck_peak MAX v(dff_ck,vss_a) FROM=2.300000000000e-08 TO=2.800000000000e-08
.measure tran p2_recovery_xor_end FIND v(xor_29,vss_a) AT=3.200000000000e-08
.measure tran p2_recovery_medium_end FIND v(medium_out,vss_a) AT=3.200000000000e-08
.measure tran p2_recovery_ck_end FIND v(dff_ck,vss_a) AT=3.200000000000e-08
.measure tran p2_recovery_xor_tail MAX v(xor_29,vss_a) FROM=3.180000000000e-08 TO=3.200000000000e-08
.measure tran p2_recovery_medium_tail MAX v(medium_out,vss_a) FROM=3.180000000000e-08 TO=3.200000000000e-08
.measure tran p2_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=3.180000000000e-08 TO=3.200000000000e-08
.measure tran p3_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=3.300000000000e-08
.measure tran p3_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=3.300000000000e-08
.measure tran p3_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=3.300000000000e-08
.measure tran p3_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=3.300000000000e-08
.measure tran p3_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=3.300000000000e-08
.measure tran p3_q_read_v FIND v(q_final,vss_a) AT=3.600000000000e-08
.measure tran p3_xor_peak MAX v(xor_29,vss_a) FROM=3.300000000000e-08 TO=3.800000000000e-08
.measure tran p3_ck_peak MAX v(dff_ck,vss_a) FROM=3.300000000000e-08 TO=3.800000000000e-08
.measure tran p3_recovery_xor_end FIND v(xor_29,vss_a) AT=4.200000000000e-08
.measure tran p3_recovery_medium_end FIND v(medium_out,vss_a) AT=4.200000000000e-08
.measure tran p3_recovery_ck_end FIND v(dff_ck,vss_a) AT=4.200000000000e-08
.measure tran p3_recovery_xor_tail MAX v(xor_29,vss_a) FROM=4.180000000000e-08 TO=4.200000000000e-08
.measure tran p3_recovery_medium_tail MAX v(medium_out,vss_a) FROM=4.180000000000e-08 TO=4.200000000000e-08
.measure tran p3_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=4.180000000000e-08 TO=4.200000000000e-08
.measure tran p4_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=4.500000000000e-08
.measure tran p4_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=4.500000000000e-08
.measure tran p4_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=4.500000000000e-08
.measure tran p4_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=4.500000000000e-08
.measure tran p4_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=4.500000000000e-08
.measure tran p4_q_read_v FIND v(q_final,vss_a) AT=4.800000000000e-08
.measure tran p4_xor_peak MAX v(xor_29,vss_a) FROM=4.500000000000e-08 TO=5.000000000000e-08
.measure tran p4_ck_peak MAX v(dff_ck,vss_a) FROM=4.500000000000e-08 TO=5.000000000000e-08
.measure tran p4_recovery_xor_end FIND v(xor_29,vss_a) AT=5.400000000000e-08
.measure tran p4_recovery_medium_end FIND v(medium_out,vss_a) AT=5.400000000000e-08
.measure tran p4_recovery_ck_end FIND v(dff_ck,vss_a) AT=5.400000000000e-08
.measure tran p4_recovery_xor_tail MAX v(xor_29,vss_a) FROM=5.380000000000e-08 TO=5.400000000000e-08
.measure tran p4_recovery_medium_tail MAX v(medium_out,vss_a) FROM=5.380000000000e-08 TO=5.400000000000e-08
.measure tran p4_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=5.380000000000e-08 TO=5.400000000000e-08
.measure tran p5_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=5.500000000000e-08
.measure tran p5_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=5.500000000000e-08
.measure tran p5_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=5.500000000000e-08
.measure tran p5_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=5.500000000000e-08
.measure tran p5_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=5.500000000000e-08
.measure tran p5_q_read_v FIND v(q_final,vss_a) AT=5.800000000000e-08
.measure tran p5_xor_peak MAX v(xor_29,vss_a) FROM=5.500000000000e-08 TO=6.000000000000e-08
.measure tran p5_ck_peak MAX v(dff_ck,vss_a) FROM=5.500000000000e-08 TO=6.000000000000e-08
.measure tran p5_recovery_xor_end FIND v(xor_29,vss_a) AT=6.400000000000e-08
.measure tran p5_recovery_medium_end FIND v(medium_out,vss_a) AT=6.400000000000e-08
.measure tran p5_recovery_ck_end FIND v(dff_ck,vss_a) AT=6.400000000000e-08
.measure tran p5_recovery_xor_tail MAX v(xor_29,vss_a) FROM=6.380000000000e-08 TO=6.400000000000e-08
.measure tran p5_recovery_medium_tail MAX v(medium_out,vss_a) FROM=6.380000000000e-08 TO=6.400000000000e-08
.measure tran p5_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=6.380000000000e-08 TO=6.400000000000e-08
.measure tran p6_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=6.700000000000e-08
.measure tran p6_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=6.700000000000e-08
.measure tran p6_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=6.700000000000e-08
.measure tran p6_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=6.700000000000e-08
.measure tran p6_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=6.700000000000e-08
.measure tran p6_q_read_v FIND v(q_final,vss_a) AT=7.000000000000e-08
.measure tran p6_xor_peak MAX v(xor_29,vss_a) FROM=6.700000000000e-08 TO=7.200000000000e-08
.measure tran p6_ck_peak MAX v(dff_ck,vss_a) FROM=6.700000000000e-08 TO=7.200000000000e-08
.measure tran p6_recovery_xor_end FIND v(xor_29,vss_a) AT=7.600000000000e-08
.measure tran p6_recovery_medium_end FIND v(medium_out,vss_a) AT=7.600000000000e-08
.measure tran p6_recovery_ck_end FIND v(dff_ck,vss_a) AT=7.600000000000e-08
.measure tran p6_recovery_xor_tail MAX v(xor_29,vss_a) FROM=7.580000000000e-08 TO=7.600000000000e-08
.measure tran p6_recovery_medium_tail MAX v(medium_out,vss_a) FROM=7.580000000000e-08 TO=7.600000000000e-08
.measure tran p6_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=7.580000000000e-08 TO=7.600000000000e-08
.measure tran p7_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=7.700000000000e-08
.measure tran p7_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=7.700000000000e-08
.measure tran p7_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=7.700000000000e-08
.measure tran p7_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=7.700000000000e-08
.measure tran p7_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=7.700000000000e-08
.measure tran p7_q_read_v FIND v(q_final,vss_a) AT=8.000000000000e-08
.measure tran p7_xor_peak MAX v(xor_29,vss_a) FROM=7.700000000000e-08 TO=8.200000000000e-08
.measure tran p7_ck_peak MAX v(dff_ck,vss_a) FROM=7.700000000000e-08 TO=8.200000000000e-08
.measure tran p7_recovery_xor_end FIND v(xor_29,vss_a) AT=8.600000000000e-08
.measure tran p7_recovery_medium_end FIND v(medium_out,vss_a) AT=8.600000000000e-08
.measure tran p7_recovery_ck_end FIND v(dff_ck,vss_a) AT=8.600000000000e-08
.measure tran p7_recovery_xor_tail MAX v(xor_29,vss_a) FROM=8.580000000000e-08 TO=8.600000000000e-08
.measure tran p7_recovery_medium_tail MAX v(medium_out,vss_a) FROM=8.580000000000e-08 TO=8.600000000000e-08
.measure tran p7_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=8.580000000000e-08 TO=8.600000000000e-08
.measure tran p8_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=8.900000000000e-08
.measure tran p8_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=8.900000000000e-08
.measure tran p8_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=8.900000000000e-08
.measure tran p8_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=8.900000000000e-08
.measure tran p8_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=8.900000000000e-08
.measure tran p8_q_read_v FIND v(q_final,vss_a) AT=9.200000000000e-08
.measure tran p8_xor_peak MAX v(xor_29,vss_a) FROM=8.900000000000e-08 TO=9.400000000000e-08
.measure tran p8_ck_peak MAX v(dff_ck,vss_a) FROM=8.900000000000e-08 TO=9.400000000000e-08
.measure tran p8_recovery_xor_end FIND v(xor_29,vss_a) AT=9.800000000000e-08
.measure tran p8_recovery_medium_end FIND v(medium_out,vss_a) AT=9.800000000000e-08
.measure tran p8_recovery_ck_end FIND v(dff_ck,vss_a) AT=9.800000000000e-08
.measure tran p8_recovery_xor_tail MAX v(xor_29,vss_a) FROM=9.780000000000e-08 TO=9.800000000000e-08
.measure tran p8_recovery_medium_tail MAX v(medium_out,vss_a) FROM=9.780000000000e-08 TO=9.800000000000e-08
.measure tran p8_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=9.780000000000e-08 TO=9.800000000000e-08
.measure tran p9_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=9.900000000000e-08
.measure tran p9_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=9.900000000000e-08
.measure tran p9_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=9.900000000000e-08
.measure tran p9_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=9.900000000000e-08
.measure tran p9_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=9.900000000000e-08
.measure tran p9_q_read_v FIND v(q_final,vss_a) AT=1.020000000000e-07
.measure tran p9_xor_peak MAX v(xor_29,vss_a) FROM=9.900000000000e-08 TO=1.040000000000e-07
.measure tran p9_ck_peak MAX v(dff_ck,vss_a) FROM=9.900000000000e-08 TO=1.040000000000e-07
.measure tran p9_recovery_xor_end FIND v(xor_29,vss_a) AT=1.080000000000e-07
.measure tran p9_recovery_medium_end FIND v(medium_out,vss_a) AT=1.080000000000e-07
.measure tran p9_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.080000000000e-07
.measure tran p9_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.078000000000e-07 TO=1.080000000000e-07
.measure tran p9_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.078000000000e-07 TO=1.080000000000e-07
.measure tran p9_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.078000000000e-07 TO=1.080000000000e-07
.measure tran p10_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.130000000000e-07
.measure tran p10_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.130000000000e-07
.measure tran p10_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.130000000000e-07
.measure tran p10_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.130000000000e-07
.measure tran p10_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.130000000000e-07
.measure tran p10_q_read_v FIND v(q_final,vss_a) AT=1.160000000000e-07
.measure tran p10_xor_peak MAX v(xor_29,vss_a) FROM=1.130000000000e-07 TO=1.180000000000e-07
.measure tran p10_ck_peak MAX v(dff_ck,vss_a) FROM=1.130000000000e-07 TO=1.180000000000e-07
.measure tran p10_recovery_xor_end FIND v(xor_29,vss_a) AT=1.220000000000e-07
.measure tran p10_recovery_medium_end FIND v(medium_out,vss_a) AT=1.220000000000e-07
.measure tran p10_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.220000000000e-07
.measure tran p10_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.218000000000e-07 TO=1.220000000000e-07
.measure tran p10_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.218000000000e-07 TO=1.220000000000e-07
.measure tran p10_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.218000000000e-07 TO=1.220000000000e-07
.measure tran p11_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.250000000000e-07
.measure tran p11_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.250000000000e-07
.measure tran p11_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.250000000000e-07
.measure tran p11_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.250000000000e-07
.measure tran p11_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.250000000000e-07
.measure tran p11_q_read_v FIND v(q_final,vss_a) AT=1.280000000000e-07
.measure tran p11_xor_peak MAX v(xor_29,vss_a) FROM=1.250000000000e-07 TO=1.300000000000e-07
.measure tran p11_ck_peak MAX v(dff_ck,vss_a) FROM=1.250000000000e-07 TO=1.300000000000e-07
.measure tran p11_recovery_xor_end FIND v(xor_29,vss_a) AT=1.340000000000e-07
.measure tran p11_recovery_medium_end FIND v(medium_out,vss_a) AT=1.340000000000e-07
.measure tran p11_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.340000000000e-07
.measure tran p11_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.338000000000e-07 TO=1.340000000000e-07
.measure tran p11_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.338000000000e-07 TO=1.340000000000e-07
.measure tran p11_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.338000000000e-07 TO=1.340000000000e-07
.measure tran p12_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.370000000000e-07
.measure tran p12_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.370000000000e-07
.measure tran p12_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.370000000000e-07
.measure tran p12_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.370000000000e-07
.measure tran p12_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.370000000000e-07
.measure tran p12_q_read_v FIND v(q_final,vss_a) AT=1.400000000000e-07
.measure tran p12_xor_peak MAX v(xor_29,vss_a) FROM=1.370000000000e-07 TO=1.420000000000e-07
.measure tran p12_ck_peak MAX v(dff_ck,vss_a) FROM=1.370000000000e-07 TO=1.420000000000e-07
.measure tran p12_recovery_xor_end FIND v(xor_29,vss_a) AT=1.460000000000e-07
.measure tran p12_recovery_medium_end FIND v(medium_out,vss_a) AT=1.460000000000e-07
.measure tran p12_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.460000000000e-07
.measure tran p12_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.458000000000e-07 TO=1.460000000000e-07
.measure tran p12_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.458000000000e-07 TO=1.460000000000e-07
.measure tran p12_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.458000000000e-07 TO=1.460000000000e-07
.measure tran p13_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.490000000000e-07
.measure tran p13_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.490000000000e-07
.measure tran p13_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.490000000000e-07
.measure tran p13_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.490000000000e-07
.measure tran p13_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.490000000000e-07
.measure tran p13_q_read_v FIND v(q_final,vss_a) AT=1.520000000000e-07
.measure tran p13_xor_peak MAX v(xor_29,vss_a) FROM=1.490000000000e-07 TO=1.540000000000e-07
.measure tran p13_ck_peak MAX v(dff_ck,vss_a) FROM=1.490000000000e-07 TO=1.540000000000e-07
.measure tran p13_recovery_xor_end FIND v(xor_29,vss_a) AT=1.580000000000e-07
.measure tran p13_recovery_medium_end FIND v(medium_out,vss_a) AT=1.580000000000e-07
.measure tran p13_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.580000000000e-07
.measure tran p13_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.578000000000e-07 TO=1.580000000000e-07
.measure tran p13_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.578000000000e-07 TO=1.580000000000e-07
.measure tran p13_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.578000000000e-07 TO=1.580000000000e-07
.measure tran p14_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.610000000000e-07
.measure tran p14_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.610000000000e-07
.measure tran p14_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.610000000000e-07
.measure tran p14_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.610000000000e-07
.measure tran p14_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.610000000000e-07
.measure tran p14_q_read_v FIND v(q_final,vss_a) AT=1.640000000000e-07
.measure tran p14_xor_peak MAX v(xor_29,vss_a) FROM=1.610000000000e-07 TO=1.660000000000e-07
.measure tran p14_ck_peak MAX v(dff_ck,vss_a) FROM=1.610000000000e-07 TO=1.660000000000e-07
.measure tran p14_recovery_xor_end FIND v(xor_29,vss_a) AT=1.700000000000e-07
.measure tran p14_recovery_medium_end FIND v(medium_out,vss_a) AT=1.700000000000e-07
.measure tran p14_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.700000000000e-07
.measure tran p14_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.698000000000e-07 TO=1.700000000000e-07
.measure tran p14_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.698000000000e-07 TO=1.700000000000e-07
.measure tran p14_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.698000000000e-07 TO=1.700000000000e-07
.measure tran p15_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.730000000000e-07
.measure tran p15_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.730000000000e-07
.measure tran p15_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.730000000000e-07
.measure tran p15_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.730000000000e-07
.measure tran p15_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.730000000000e-07
.measure tran p15_q_read_v FIND v(q_final,vss_a) AT=1.760000000000e-07
.measure tran p15_xor_peak MAX v(xor_29,vss_a) FROM=1.730000000000e-07 TO=1.780000000000e-07
.measure tran p15_ck_peak MAX v(dff_ck,vss_a) FROM=1.730000000000e-07 TO=1.780000000000e-07
.measure tran p15_recovery_xor_end FIND v(xor_29,vss_a) AT=1.820000000000e-07
.measure tran p15_recovery_medium_end FIND v(medium_out,vss_a) AT=1.820000000000e-07
.measure tran p15_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.820000000000e-07
.measure tran p15_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.818000000000e-07 TO=1.820000000000e-07
.measure tran p15_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.818000000000e-07 TO=1.820000000000e-07
.measure tran p15_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.818000000000e-07 TO=1.820000000000e-07
.measure tran p16_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.850000000000e-07
.measure tran p16_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.850000000000e-07
.measure tran p16_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.850000000000e-07
.measure tran p16_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.850000000000e-07
.measure tran p16_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.850000000000e-07
.measure tran p16_q_read_v FIND v(q_final,vss_a) AT=1.880000000000e-07
.measure tran p16_xor_peak MAX v(xor_29,vss_a) FROM=1.850000000000e-07 TO=1.900000000000e-07
.measure tran p16_ck_peak MAX v(dff_ck,vss_a) FROM=1.850000000000e-07 TO=1.900000000000e-07
.measure tran p16_recovery_xor_end FIND v(xor_29,vss_a) AT=1.940000000000e-07
.measure tran p16_recovery_medium_end FIND v(medium_out,vss_a) AT=1.940000000000e-07
.measure tran p16_recovery_ck_end FIND v(dff_ck,vss_a) AT=1.940000000000e-07
.measure tran p16_recovery_xor_tail MAX v(xor_29,vss_a) FROM=1.938000000000e-07 TO=1.940000000000e-07
.measure tran p16_recovery_medium_tail MAX v(medium_out,vss_a) FROM=1.938000000000e-07 TO=1.940000000000e-07
.measure tran p16_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=1.938000000000e-07 TO=1.940000000000e-07
.measure tran p17_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.970000000000e-07
.measure tran p17_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=1.970000000000e-07
.measure tran p17_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=1.970000000000e-07
.measure tran p17_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.970000000000e-07
.measure tran p17_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.970000000000e-07
.measure tran p17_q_read_v FIND v(q_final,vss_a) AT=2.000000000000e-07
.measure tran p17_xor_peak MAX v(xor_29,vss_a) FROM=1.970000000000e-07 TO=2.020000000000e-07
.measure tran p17_ck_peak MAX v(dff_ck,vss_a) FROM=1.970000000000e-07 TO=2.020000000000e-07
.measure tran p17_recovery_xor_end FIND v(xor_29,vss_a) AT=2.060000000000e-07
.measure tran p17_recovery_medium_end FIND v(medium_out,vss_a) AT=2.060000000000e-07
.measure tran p17_recovery_ck_end FIND v(dff_ck,vss_a) AT=2.060000000000e-07
.measure tran p17_recovery_xor_tail MAX v(xor_29,vss_a) FROM=2.058000000000e-07 TO=2.060000000000e-07
.measure tran p17_recovery_medium_tail MAX v(medium_out,vss_a) FROM=2.058000000000e-07 TO=2.060000000000e-07
.measure tran p17_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=2.058000000000e-07 TO=2.060000000000e-07
.measure tran p18_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=2.090000000000e-07
.measure tran p18_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=2.090000000000e-07
.measure tran p18_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=2.090000000000e-07
.measure tran p18_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=2.090000000000e-07
.measure tran p18_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=2.090000000000e-07
.measure tran p18_q_read_v FIND v(q_final,vss_a) AT=2.120000000000e-07
.measure tran p18_xor_peak MAX v(xor_29,vss_a) FROM=2.090000000000e-07 TO=2.140000000000e-07
.measure tran p18_ck_peak MAX v(dff_ck,vss_a) FROM=2.090000000000e-07 TO=2.140000000000e-07
.measure tran p18_recovery_xor_end FIND v(xor_29,vss_a) AT=2.180000000000e-07
.measure tran p18_recovery_medium_end FIND v(medium_out,vss_a) AT=2.180000000000e-07
.measure tran p18_recovery_ck_end FIND v(dff_ck,vss_a) AT=2.180000000000e-07
.measure tran p18_recovery_xor_tail MAX v(xor_29,vss_a) FROM=2.178000000000e-07 TO=2.180000000000e-07
.measure tran p18_recovery_medium_tail MAX v(medium_out,vss_a) FROM=2.178000000000e-07 TO=2.180000000000e-07
.measure tran p18_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=2.178000000000e-07 TO=2.180000000000e-07
.measure tran p19_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=2.210000000000e-07
.measure tran p19_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=2.210000000000e-07
.measure tran p19_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=2.210000000000e-07
.measure tran p19_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=2.210000000000e-07
.measure tran p19_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=2.210000000000e-07
.measure tran p19_q_read_v FIND v(q_final,vss_a) AT=2.240000000000e-07
.measure tran p19_xor_peak MAX v(xor_29,vss_a) FROM=2.210000000000e-07 TO=2.260000000000e-07
.measure tran p19_ck_peak MAX v(dff_ck,vss_a) FROM=2.210000000000e-07 TO=2.260000000000e-07
.measure tran p19_recovery_xor_end FIND v(xor_29,vss_a) AT=2.300000000000e-07
.measure tran p19_recovery_medium_end FIND v(medium_out,vss_a) AT=2.300000000000e-07
.measure tran p19_recovery_ck_end FIND v(dff_ck,vss_a) AT=2.300000000000e-07
.measure tran p19_recovery_xor_tail MAX v(xor_29,vss_a) FROM=2.298000000000e-07 TO=2.300000000000e-07
.measure tran p19_recovery_medium_tail MAX v(medium_out,vss_a) FROM=2.298000000000e-07 TO=2.300000000000e-07
.measure tran p19_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=2.298000000000e-07 TO=2.300000000000e-07
.measure tran p20_t_xor_rise WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=2.310000000000e-07
.measure tran p20_t_xor_fall WHEN v(xor_29,vss_a)='VDD_VALUE/2' FALL=1 TD=2.310000000000e-07
.measure tran p20_t_xor_rise_2 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=2 TD=2.310000000000e-07
.measure tran p20_t_ck_rise WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=2.310000000000e-07
.measure tran p20_t_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=2.310000000000e-07
.measure tran p20_q_read_v FIND v(q_final,vss_a) AT=2.340000000000e-07
.measure tran p20_xor_peak MAX v(xor_29,vss_a) FROM=2.310000000000e-07 TO=2.360000000000e-07
.measure tran p20_ck_peak MAX v(dff_ck,vss_a) FROM=2.310000000000e-07 TO=2.360000000000e-07
.measure tran p20_recovery_xor_end FIND v(xor_29,vss_a) AT=2.400000000000e-07
.measure tran p20_recovery_medium_end FIND v(medium_out,vss_a) AT=2.400000000000e-07
.measure tran p20_recovery_ck_end FIND v(dff_ck,vss_a) AT=2.400000000000e-07
.measure tran p20_recovery_xor_tail MAX v(xor_29,vss_a) FROM=2.398000000000e-07 TO=2.400000000000e-07
.measure tran p20_recovery_medium_tail MAX v(medium_out,vss_a) FROM=2.398000000000e-07 TO=2.400000000000e-07
.measure tran p20_recovery_ck_tail MAX v(dff_ck,vss_a) FROM=2.398000000000e-07 TO=2.400000000000e-07
.measure tran tr0_xor_max MAX v(xor_29,vss_a) FROM=2.001000000000e-08 TO=2.199000000000e-08
.measure tran tr0_medium_max MAX v(medium_out,vss_a) FROM=2.001000000000e-08 TO=2.199000000000e-08
.measure tran tr0_ck_max MAX v(dff_ck,vss_a) FROM=2.001000000000e-08 TO=2.199000000000e-08
.measure tran tr0_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=2.001000000000e-08
.measure tran tr0_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=2.001000000000e-08
.measure tran tr0_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=2.001000000000e-08
.measure tran tr1_xor_max MAX v(xor_29,vss_a) FROM=4.201000000000e-08 TO=4.399000000000e-08
.measure tran tr1_medium_max MAX v(medium_out,vss_a) FROM=4.201000000000e-08 TO=4.399000000000e-08
.measure tran tr1_ck_max MAX v(dff_ck,vss_a) FROM=4.201000000000e-08 TO=4.399000000000e-08
.measure tran tr1_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=4.201000000000e-08
.measure tran tr1_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=4.201000000000e-08
.measure tran tr1_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=4.201000000000e-08
.measure tran tr2_xor_max MAX v(xor_29,vss_a) FROM=6.401000000000e-08 TO=6.599000000000e-08
.measure tran tr2_medium_max MAX v(medium_out,vss_a) FROM=6.401000000000e-08 TO=6.599000000000e-08
.measure tran tr2_ck_max MAX v(dff_ck,vss_a) FROM=6.401000000000e-08 TO=6.599000000000e-08
.measure tran tr2_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=6.401000000000e-08
.measure tran tr2_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=6.401000000000e-08
.measure tran tr2_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=6.401000000000e-08
.measure tran tr3_xor_max MAX v(xor_29,vss_a) FROM=8.601000000000e-08 TO=8.799000000000e-08
.measure tran tr3_medium_max MAX v(medium_out,vss_a) FROM=8.601000000000e-08 TO=8.799000000000e-08
.measure tran tr3_ck_max MAX v(dff_ck,vss_a) FROM=8.601000000000e-08 TO=8.799000000000e-08
.measure tran tr3_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=8.601000000000e-08
.measure tran tr3_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=8.601000000000e-08
.measure tran tr3_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=8.601000000000e-08
.measure tran tr4_xor_max MAX v(xor_29,vss_a) FROM=1.080100000000e-07 TO=1.099900000000e-07
.measure tran tr4_medium_max MAX v(medium_out,vss_a) FROM=1.080100000000e-07 TO=1.099900000000e-07
.measure tran tr4_ck_max MAX v(dff_ck,vss_a) FROM=1.080100000000e-07 TO=1.099900000000e-07
.measure tran tr4_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.080100000000e-07
.measure tran tr4_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.080100000000e-07
.measure tran tr4_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.080100000000e-07
.measure tran tr5_xor_max MAX v(xor_29,vss_a) FROM=1.100100000000e-07 TO=1.119900000000e-07
.measure tran tr5_medium_max MAX v(medium_out,vss_a) FROM=1.100100000000e-07 TO=1.119900000000e-07
.measure tran tr5_ck_max MAX v(dff_ck,vss_a) FROM=1.100100000000e-07 TO=1.119900000000e-07
.measure tran tr5_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.100100000000e-07
.measure tran tr5_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.100100000000e-07
.measure tran tr5_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.100100000000e-07
.measure tran tr6_xor_max MAX v(xor_29,vss_a) FROM=1.220100000000e-07 TO=1.239900000000e-07
.measure tran tr6_medium_max MAX v(medium_out,vss_a) FROM=1.220100000000e-07 TO=1.239900000000e-07
.measure tran tr6_ck_max MAX v(dff_ck,vss_a) FROM=1.220100000000e-07 TO=1.239900000000e-07
.measure tran tr6_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.220100000000e-07
.measure tran tr6_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.220100000000e-07
.measure tran tr6_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.220100000000e-07
.measure tran tr7_xor_max MAX v(xor_29,vss_a) FROM=1.340100000000e-07 TO=1.359900000000e-07
.measure tran tr7_medium_max MAX v(medium_out,vss_a) FROM=1.340100000000e-07 TO=1.359900000000e-07
.measure tran tr7_ck_max MAX v(dff_ck,vss_a) FROM=1.340100000000e-07 TO=1.359900000000e-07
.measure tran tr7_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.340100000000e-07
.measure tran tr7_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.340100000000e-07
.measure tran tr7_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.340100000000e-07
.measure tran tr8_xor_max MAX v(xor_29,vss_a) FROM=1.460100000000e-07 TO=1.479900000000e-07
.measure tran tr8_medium_max MAX v(medium_out,vss_a) FROM=1.460100000000e-07 TO=1.479900000000e-07
.measure tran tr8_ck_max MAX v(dff_ck,vss_a) FROM=1.460100000000e-07 TO=1.479900000000e-07
.measure tran tr8_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.460100000000e-07
.measure tran tr8_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.460100000000e-07
.measure tran tr8_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.460100000000e-07
.measure tran tr9_xor_max MAX v(xor_29,vss_a) FROM=1.580100000000e-07 TO=1.599900000000e-07
.measure tran tr9_medium_max MAX v(medium_out,vss_a) FROM=1.580100000000e-07 TO=1.599900000000e-07
.measure tran tr9_ck_max MAX v(dff_ck,vss_a) FROM=1.580100000000e-07 TO=1.599900000000e-07
.measure tran tr9_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.580100000000e-07
.measure tran tr9_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.580100000000e-07
.measure tran tr9_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.580100000000e-07
.measure tran tr10_xor_max MAX v(xor_29,vss_a) FROM=1.700100000000e-07 TO=1.719900000000e-07
.measure tran tr10_medium_max MAX v(medium_out,vss_a) FROM=1.700100000000e-07 TO=1.719900000000e-07
.measure tran tr10_ck_max MAX v(dff_ck,vss_a) FROM=1.700100000000e-07 TO=1.719900000000e-07
.measure tran tr10_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.700100000000e-07
.measure tran tr10_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.700100000000e-07
.measure tran tr10_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.700100000000e-07
.measure tran tr11_xor_max MAX v(xor_29,vss_a) FROM=1.820100000000e-07 TO=1.839900000000e-07
.measure tran tr11_medium_max MAX v(medium_out,vss_a) FROM=1.820100000000e-07 TO=1.839900000000e-07
.measure tran tr11_ck_max MAX v(dff_ck,vss_a) FROM=1.820100000000e-07 TO=1.839900000000e-07
.measure tran tr11_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.820100000000e-07
.measure tran tr11_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.820100000000e-07
.measure tran tr11_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.820100000000e-07
.measure tran tr12_xor_max MAX v(xor_29,vss_a) FROM=1.940100000000e-07 TO=1.959900000000e-07
.measure tran tr12_medium_max MAX v(medium_out,vss_a) FROM=1.940100000000e-07 TO=1.959900000000e-07
.measure tran tr12_ck_max MAX v(dff_ck,vss_a) FROM=1.940100000000e-07 TO=1.959900000000e-07
.measure tran tr12_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=1.940100000000e-07
.measure tran tr12_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=1.940100000000e-07
.measure tran tr12_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=1.940100000000e-07
.measure tran tr13_xor_max MAX v(xor_29,vss_a) FROM=2.060100000000e-07 TO=2.079900000000e-07
.measure tran tr13_medium_max MAX v(medium_out,vss_a) FROM=2.060100000000e-07 TO=2.079900000000e-07
.measure tran tr13_ck_max MAX v(dff_ck,vss_a) FROM=2.060100000000e-07 TO=2.079900000000e-07
.measure tran tr13_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=2.060100000000e-07
.measure tran tr13_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=2.060100000000e-07
.measure tran tr13_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=2.060100000000e-07
.measure tran tr14_xor_max MAX v(xor_29,vss_a) FROM=2.180100000000e-07 TO=2.199900000000e-07
.measure tran tr14_medium_max MAX v(medium_out,vss_a) FROM=2.180100000000e-07 TO=2.199900000000e-07
.measure tran tr14_ck_max MAX v(dff_ck,vss_a) FROM=2.180100000000e-07 TO=2.199900000000e-07
.measure tran tr14_xor_rise_1 WHEN v(xor_29,vss_a)='VDD_VALUE/2' RISE=1 TD=2.180100000000e-07
.measure tran tr14_ck_rise_1 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=1 TD=2.180100000000e-07
.measure tran tr14_ck_rise_2 WHEN v(dff_ck,vss_a)='VDD_VALUE/2' RISE=2 TD=2.180100000000e-07
.measure tran p0_q_read_late_v FIND v(q_final,vss_a) AT=5.000000000000e-09
.measure tran p1_q_read_late_v FIND v(q_final,vss_a) AT=1.500000000000e-08
.measure tran p2_q_read_late_v FIND v(q_final,vss_a) AT=2.700000000000e-08
.measure tran p3_q_read_late_v FIND v(q_final,vss_a) AT=3.700000000000e-08
.measure tran p4_q_read_late_v FIND v(q_final,vss_a) AT=4.900000000000e-08
.measure tran p5_q_read_late_v FIND v(q_final,vss_a) AT=5.900000000000e-08
.measure tran p6_q_read_late_v FIND v(q_final,vss_a) AT=7.100000000000e-08
.measure tran p7_q_read_late_v FIND v(q_final,vss_a) AT=8.100000000000e-08
.measure tran p8_q_read_late_v FIND v(q_final,vss_a) AT=9.300000000000e-08
.measure tran p9_q_read_late_v FIND v(q_final,vss_a) AT=1.030000000000e-07
.measure tran p10_q_read_late_v FIND v(q_final,vss_a) AT=1.170000000000e-07
.measure tran p11_q_read_late_v FIND v(q_final,vss_a) AT=1.290000000000e-07
.measure tran p12_q_read_late_v FIND v(q_final,vss_a) AT=1.410000000000e-07
.measure tran p13_q_read_late_v FIND v(q_final,vss_a) AT=1.530000000000e-07
.measure tran p14_q_read_late_v FIND v(q_final,vss_a) AT=1.650000000000e-07
.measure tran p15_q_read_late_v FIND v(q_final,vss_a) AT=1.770000000000e-07
.measure tran p16_q_read_late_v FIND v(q_final,vss_a) AT=1.890000000000e-07
.measure tran p17_q_read_late_v FIND v(q_final,vss_a) AT=2.010000000000e-07
.measure tran p18_q_read_late_v FIND v(q_final,vss_a) AT=2.130000000000e-07
.measure tran p19_q_read_late_v FIND v(q_final,vss_a) AT=2.250000000000e-07
.measure tran p20_q_read_late_v FIND v(q_final,vss_a) AT=2.350000000000e-07
.end
