* B-FE2-L1A local-container VCS-XA top deck.
.option post=1 probe
.lib '/host/data/libtech/SMIC_40LL/PDK/SPDK40LL_1125_2TM_OA_CDS_V1.4/smic40ll_1125_2tm_oa_cds_1P7M_2012_10_11_v1.4/models/hspice/l0040ll_v1p4_1r.lib' tt
.include '/home/zhupl25/chiplet_side_channel/chiplet_gds_data/chiplets/FIR/syn/runs/fir_smic40ll_tt_1310ps_spice_20260722_r1/spice/sc9mc_logic0040ll_base_rvt_c40.hspice.cdl'
.include '/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/cdl/sc9mc_logic0040ll_base_lvt_c40.cdl'
.include '/home/zhupl25/chiplet_side_channel/chiplet_gds_data/power_macro/delay_chain/ftc/spice/empty_subckt.sp_cal'
.include '/home/zhupl25/chiplet_side_channel/chiplet_gds_data/power_macro/delay_chain/ftc/runs/b_fe_frontend/bfe2_real_latch/l1a_vcs_xa_1p10/bfe2l_095_n/bfe2_l1a_ams_wrapper.sp'
.tran 1p 7.000000000000e-09
.end
