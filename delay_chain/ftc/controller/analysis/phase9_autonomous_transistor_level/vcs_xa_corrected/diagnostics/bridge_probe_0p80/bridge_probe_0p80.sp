* ============================================================================
* Phase 9 R3/R4 corrected 0.80 V XA diagnostic deck.
*
* The corrected wrapper creates VDD_LOCAL/VSS_LOCAL internally from VDD_VALUE.
* No VDD/VSS Verilog ports or generic supply D2A elements are used.  The deck
* retains only compact waveform probes required by the R3/R4 contracts.
* ============================================================================
.option post=1
.option probe
.param VDD_VALUE=0.80
.lib /home/yangz/virtuoso/SMIC40TXRX/smic40ll_1125_2tm_oa_cds_1P9M_2012_10_11_v1.4/models/hspice/l0040ll_v1p4_1r.lib tt
.include /home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/cdl/sc9mc_logic0040ll_base_rvt_c40.cdl
.include /home/yangz/virtuoso/SMIC40TXRX/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/cdl/sc9mc_logic0040ll_base_lvt_c40.cdl
.include ../../inputs/empty_subckt.sp_cal
.include ../../inputs/ftc_sensor_frozen.sp
.include ../../src/ftc_sensor_ams_wrapper.sp
.probe tran V(q_final) V(sense_s_clk) V(sense_dff_reset) V(medium_therm[0]) V(fine_therm[0])
.tran 1p 100n
.end
