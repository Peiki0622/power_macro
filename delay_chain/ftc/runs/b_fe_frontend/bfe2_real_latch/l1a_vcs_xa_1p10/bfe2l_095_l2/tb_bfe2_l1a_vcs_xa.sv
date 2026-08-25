// B-FE2-L1A VCS-XA testbench; generated from immutable B-FE2.2C trace.
// This is simulation glue only and is intentionally not synthesizable.
`timescale 1ps/1ps
module bfe2_l1a_vcs_xa;
    // Each safe_d_i is a source-domain Level-0 restored logic crossing.
    // XA converts it to analog and the wrapper forces its data high to 0.95 V.
    logic safe_d_0;
    logic safe_d_1;
    logic safe_d_2;
    logic safe_d_3;
    logic safe_d_4;
    logic safe_d_5;
    logic safe_d_6;
    logic safe_d_7;
    logic safe_d_8;
    logic safe_d_9;
    logic safe_d_10;
    logic safe_d_11;
    logic safe_d_12;
    logic safe_d_13;
    logic safe_d_14;
    logic safe_d_15;
    logic safe_d_16;
    logic safe_d_17;
    logic safe_d_18;
    logic safe_d_19;
    logic safe_d_20;
    logic safe_d_21;
    logic safe_d_22;
    logic safe_d_23;
    logic safe_d_24;
    logic safe_d_25;
    logic safe_d_26;
    logic safe_d_27;
    logic safe_d_28;
    logic safe_d_29;
    // latch_g is the one trusted safe-domain active-high gate; it falls
    // exactly once at 534.524618567 ps and is never swept or retimed.
    logic latch_g;
    // q_i are A2D-returned outputs of the thirty real LATQ cells.
    wire q_0;
    wire q_1;
    wire q_2;
    wire q_3;
    wire q_4;
    wire q_5;
    wire q_6;
    wire q_7;
    wire q_8;
    wire q_9;
    wire q_10;
    wire q_11;
    wire q_12;
    wire q_13;
    wire q_14;
    wire q_15;
    wire q_16;
    wire q_17;
    wire q_18;
    wire q_19;
    wire q_20;
    wire q_21;
    wire q_22;
    wire q_23;
    wire q_24;
    wire q_25;
    wire q_26;
    wire q_27;
    wire q_28;
    wire q_29;

    // Explicit scalar port mapping preserves the audited 30-tap order.
    bfe2_l1a_ams u_ams (

        .safe_d_0(safe_d_0),
        .safe_d_1(safe_d_1),
        .safe_d_2(safe_d_2),
        .safe_d_3(safe_d_3),
        .safe_d_4(safe_d_4),
        .safe_d_5(safe_d_5),
        .safe_d_6(safe_d_6),
        .safe_d_7(safe_d_7),
        .safe_d_8(safe_d_8),
        .safe_d_9(safe_d_9),
        .safe_d_10(safe_d_10),
        .safe_d_11(safe_d_11),
        .safe_d_12(safe_d_12),
        .safe_d_13(safe_d_13),
        .safe_d_14(safe_d_14),
        .safe_d_15(safe_d_15),
        .safe_d_16(safe_d_16),
        .safe_d_17(safe_d_17),
        .safe_d_18(safe_d_18),
        .safe_d_19(safe_d_19),
        .safe_d_20(safe_d_20),
        .safe_d_21(safe_d_21),
        .safe_d_22(safe_d_22),
        .safe_d_23(safe_d_23),
        .safe_d_24(safe_d_24),
        .safe_d_25(safe_d_25),
        .safe_d_26(safe_d_26),
        .safe_d_27(safe_d_27),
        .safe_d_28(safe_d_28),
        .safe_d_29(safe_d_29),
        .latch_g(latch_g),
        .q_0(q_0),
        .q_1(q_1),
        .q_2(q_2),
        .q_3(q_3),
        .q_4(q_4),
        .q_5(q_5),
        .q_6(q_6),
        .q_7(q_7),
        .q_8(q_8),
        .q_9(q_9),
        .q_10(q_10),
        .q_11(q_11),
        .q_12(q_12),
        .q_13(q_13),
        .q_14(q_14),
        .q_15(q_15),
        .q_16(q_16),
        .q_17(q_17),
        .q_18(q_18),
        .q_19(q_19),
        .q_20(q_20),
        .q_21(q_21),
        .q_22(q_22),
        .q_23(q_23),
        .q_24(q_24),
        .q_25(q_25),
        .q_26(q_26),
        .q_27(q_27),
        .q_28(q_28),
        .q_29(q_29)
    );

    // One trusted falling edge; no second close is permitted.
    initial begin
        latch_g = 1'b1;
        #( 1534.524618567000 ) latch_g = 1'b0;
    end

    // Tap 00: threshold-event schedule generated from xor_00.
    initial begin
        safe_d_0 = 1'b1;
        #( 1039.079843937778 ) safe_d_0 = 1'b1;
        #( 79.124470368312 ) safe_d_0 = 1'b0;
    end

    // Tap 01: threshold-event schedule generated from xor_01.
    initial begin
        safe_d_1 = 1'b1;
        #( 1056.140927630766 ) safe_d_1 = 1'b1;
        #( 100.882385494234 ) safe_d_1 = 1'b0;
    end

    // Tap 02: threshold-event schedule generated from xor_02.
    initial begin
        safe_d_2 = 1'b1;
        #( 1073.200568784502 ) safe_d_2 = 1'b1;
        #( 122.610184148863 ) safe_d_2 = 1'b0;
    end

    // Tap 03: threshold-event schedule generated from xor_03.
    initial begin
        safe_d_3 = 1'b1;
        #( 1094.828596538484 ) safe_d_3 = 1'b1;
        #( 139.749376322071 ) safe_d_3 = 1'b0;
    end

    // Tap 04: threshold-event schedule generated from xor_04.
    initial begin
        safe_d_4 = 1'b1;
        #( 1116.037784790735 ) safe_d_4 = 1'b1;
        #( 157.279567430795 ) safe_d_4 = 1'b0;
    end

    // Tap 05: threshold-event schedule generated from xor_05.
    initial begin
        safe_d_5 = 1'b1;
        #( 1137.084582639987 ) safe_d_5 = 1'b1;
        #( 175.167069978132 ) safe_d_5 = 1'b0;
    end

    // Tap 06: threshold-event schedule generated from xor_06.
    initial begin
        safe_d_6 = 1'b1;
        #( 1158.403360663247 ) safe_d_6 = 1'b1;
        #( 192.720528394666 ) safe_d_6 = 1'b0;
    end

    // Tap 07: threshold-event schedule generated from xor_07.
    initial begin
        safe_d_7 = 1'b1;
        #( 1179.664754660253 ) safe_d_7 = 1'b1;
        #( 210.180875463251 ) safe_d_7 = 1'b0;
    end

    // Tap 08: threshold-event schedule generated from xor_08.
    initial begin
        safe_d_8 = 1'b1;
        #( 1200.843848304882 ) safe_d_8 = 1'b1;
        #( 227.799088588265 ) safe_d_8 = 1'b0;
    end

    // Tap 09: threshold-event schedule generated from xor_09.
    initial begin
        safe_d_9 = 1'b1;
        #( 1222.213761153781 ) safe_d_9 = 1'b1;
        #( 245.329090030081 ) safe_d_9 = 1'b0;
    end

    // Tap 10: threshold-event schedule generated from xor_10.
    initial begin
        safe_d_10 = 1'b1;
        #( 1243.340570115586 ) safe_d_10 = 1'b1;
        #( 262.934512193639 ) safe_d_10 = 1'b0;
    end

    // Tap 11: threshold-event schedule generated from xor_11.
    initial begin
        safe_d_11 = 1'b1;
        #( 1264.717536020368 ) safe_d_11 = 1'b1;
        #( 280.287776489808 ) safe_d_11 = 1'b0;
    end

    // Tap 12: threshold-event schedule generated from xor_12.
    initial begin
        safe_d_12 = 1'b1;
        #( 1285.896719325453 ) safe_d_12 = 1'b1;
        #( 297.926581065893 ) safe_d_12 = 1'b0;
    end

    // Tap 13: threshold-event schedule generated from xor_13.
    initial begin
        safe_d_13 = 1'b1;
        #( 1307.154807028432 ) safe_d_13 = 1'b1;
        #( 315.434868008472 ) safe_d_13 = 1'b0;
    end

    // Tap 14: threshold-event schedule generated from xor_14.
    initial begin
        safe_d_14 = 1'b1;
        #( 1328.426114518589 ) safe_d_14 = 1'b1;
        #( 333.267594950931 ) safe_d_14 = 1'b0;
    end

    // Tap 15: threshold-event schedule generated from xor_15.
    initial begin
        safe_d_15 = 1'b1;
        #( 1349.596260641260 ) safe_d_15 = 1'b1;
        #( 350.728934116876 ) safe_d_15 = 1'b0;
    end

    // Tap 16: threshold-event schedule generated from xor_16.
    initial begin
        safe_d_16 = 1'b1;
        #( 1370.813092371370 ) safe_d_16 = 1'b1;
        #( 368.496227503522 ) safe_d_16 = 1'b0;
    end

    // Tap 17: threshold-event schedule generated from xor_17.
    initial begin
        safe_d_17 = 1'b1;
        #( 1392.130024835104 ) safe_d_17 = 1'b1;
        #( 386.068073080301 ) safe_d_17 = 1'b0;
    end

    // Tap 18: threshold-event schedule generated from xor_18.
    initial begin
        safe_d_18 = 1'b1;
        #( 1413.364038687901 ) safe_d_18 = 1'b1;
        #( 403.816896426675 ) safe_d_18 = 1'b0;
    end

    // Tap 19: threshold-event schedule generated from xor_19.
    initial begin
        safe_d_19 = 1'b1;
        #( 1434.524164240112 ) safe_d_19 = 1'b1;
        #( 421.547270539285 ) safe_d_19 = 1'b0;
    end

    // Tap 20: threshold-event schedule generated from xor_20.
    initial begin
        safe_d_20 = 1'b1;
        #( 1455.975530322087 ) safe_d_20 = 1'b1;
        #( 439.083862054204 ) safe_d_20 = 1'b0;
    end

    // Tap 21: threshold-event schedule generated from xor_21.
    initial begin
        safe_d_21 = 1'b1;
        #( 1477.148011549744 ) safe_d_21 = 1'b1;
        #( 456.815366506725 ) safe_d_21 = 1'b0;
    end

    // Tap 22: threshold-event schedule generated from xor_22.
    initial begin
        safe_d_22 = 1'b1;
        #( 1498.127679068296 ) safe_d_22 = 1'b1;
        #( 474.648975084208 ) safe_d_22 = 1'b0;
    end

    // Tap 23: threshold-event schedule generated from xor_23.
    initial begin
        safe_d_23 = 1'b1;
        #( 1519.463732681104 ) safe_d_23 = 1'b1;
        #( 492.208415239352 ) safe_d_23 = 1'b0;
    end

    // Tap 24: threshold-event schedule generated from xor_24.
    initial begin
        safe_d_24 = 1'b1;
        #( 1540.692252176825 ) safe_d_24 = 1'b1;
        #( 509.685183355329 ) safe_d_24 = 1'b0;
    end

    // Tap 25: threshold-event schedule generated from xor_25.
    initial begin
        safe_d_25 = 1'b1;
        #( 1561.727810785982 ) safe_d_25 = 1'b1;
        #( 527.410410182723 ) safe_d_25 = 1'b0;
    end

    // Tap 26: threshold-event schedule generated from xor_26.
    initial begin
        safe_d_26 = 1'b1;
        #( 1582.992309819965 ) safe_d_26 = 1'b1;
        #( 545.271633010352 ) safe_d_26 = 1'b0;
    end

    // Tap 27: threshold-event schedule generated from xor_27.
    initial begin
        safe_d_27 = 1'b1;
        #( 1604.174651077770 ) safe_d_27 = 1'b1;
        #( 562.845784292383 ) safe_d_27 = 1'b0;
    end

    // Tap 28: threshold-event schedule generated from xor_28.
    initial begin
        safe_d_28 = 1'b1;
        #( 1625.419238163655 ) safe_d_28 = 1'b1;
        #( 580.724677902371 ) safe_d_28 = 1'b0;
    end

    // Tap 29: threshold-event schedule generated from xor_29.
    initial begin
        safe_d_29 = 1'b1;
        #( 1643.276388426368 ) safe_d_29 = 1'b1;
        #( 598.468792088343 ) safe_d_29 = 1'b0;
    end

    // XA analog evidence file. $snps_get_volt is diagnostic only: it
    // reads the analog nodes owned by the real XA wrapper and never
    // feeds a digital decision or changes capture behavior.
    integer evidence_fd;
    real analog_sample;
    initial begin
        evidence_fd = $fopen("xa_boundary_samples.csv", "w");
        $fwrite(evidence_fd, "kind,time_ps,tap,safe_d_v,q_v,vdd_sense_v,vdd_safe_v,g_v\n");
        #( 1634.524618567000 );
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_00);
        $fwrite(evidence_fd, "post_close,%.6f,0,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_00), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_01);
        $fwrite(evidence_fd, "post_close,%.6f,1,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_01), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_02);
        $fwrite(evidence_fd, "post_close,%.6f,2,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_02), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_03);
        $fwrite(evidence_fd, "post_close,%.6f,3,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_03), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_04);
        $fwrite(evidence_fd, "post_close,%.6f,4,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_04), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_05);
        $fwrite(evidence_fd, "post_close,%.6f,5,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_05), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_06);
        $fwrite(evidence_fd, "post_close,%.6f,6,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_06), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_07);
        $fwrite(evidence_fd, "post_close,%.6f,7,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_07), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_08);
        $fwrite(evidence_fd, "post_close,%.6f,8,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_08), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_09);
        $fwrite(evidence_fd, "post_close,%.6f,9,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_09), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_10);
        $fwrite(evidence_fd, "post_close,%.6f,10,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_10), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_11);
        $fwrite(evidence_fd, "post_close,%.6f,11,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_11), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_12);
        $fwrite(evidence_fd, "post_close,%.6f,12,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_12), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_13);
        $fwrite(evidence_fd, "post_close,%.6f,13,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_13), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_14);
        $fwrite(evidence_fd, "post_close,%.6f,14,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_14), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_15);
        $fwrite(evidence_fd, "post_close,%.6f,15,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_15), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_16);
        $fwrite(evidence_fd, "post_close,%.6f,16,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_16), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_17);
        $fwrite(evidence_fd, "post_close,%.6f,17,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_17), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_18);
        $fwrite(evidence_fd, "post_close,%.6f,18,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_18), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_19);
        $fwrite(evidence_fd, "post_close,%.6f,19,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_19), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_20);
        $fwrite(evidence_fd, "post_close,%.6f,20,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_20), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_21);
        $fwrite(evidence_fd, "post_close,%.6f,21,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_21), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_22);
        $fwrite(evidence_fd, "post_close,%.6f,22,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_22), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_23);
        $fwrite(evidence_fd, "post_close,%.6f,23,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_23), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_24);
        $fwrite(evidence_fd, "post_close,%.6f,24,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_24), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_25);
        $fwrite(evidence_fd, "post_close,%.6f,25,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_25), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_26);
        $fwrite(evidence_fd, "post_close,%.6f,26,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_26), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_27);
        $fwrite(evidence_fd, "post_close,%.6f,27,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_27), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_28);
        $fwrite(evidence_fd, "post_close,%.6f,28,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_28), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_29);
        $fwrite(evidence_fd, "post_close,%.6f,29,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_29), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        #( 1000.0 );
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_00);
        $fwrite(evidence_fd, "tail_1ns,%.6f,0,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_00), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_01);
        $fwrite(evidence_fd, "tail_1ns,%.6f,1,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_01), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_02);
        $fwrite(evidence_fd, "tail_1ns,%.6f,2,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_02), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_03);
        $fwrite(evidence_fd, "tail_1ns,%.6f,3,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_03), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_04);
        $fwrite(evidence_fd, "tail_1ns,%.6f,4,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_04), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_05);
        $fwrite(evidence_fd, "tail_1ns,%.6f,5,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_05), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_06);
        $fwrite(evidence_fd, "tail_1ns,%.6f,6,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_06), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_07);
        $fwrite(evidence_fd, "tail_1ns,%.6f,7,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_07), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_08);
        $fwrite(evidence_fd, "tail_1ns,%.6f,8,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_08), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_09);
        $fwrite(evidence_fd, "tail_1ns,%.6f,9,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_09), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_10);
        $fwrite(evidence_fd, "tail_1ns,%.6f,10,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_10), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_11);
        $fwrite(evidence_fd, "tail_1ns,%.6f,11,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_11), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_12);
        $fwrite(evidence_fd, "tail_1ns,%.6f,12,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_12), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_13);
        $fwrite(evidence_fd, "tail_1ns,%.6f,13,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_13), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_14);
        $fwrite(evidence_fd, "tail_1ns,%.6f,14,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_14), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_15);
        $fwrite(evidence_fd, "tail_1ns,%.6f,15,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_15), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_16);
        $fwrite(evidence_fd, "tail_1ns,%.6f,16,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_16), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_17);
        $fwrite(evidence_fd, "tail_1ns,%.6f,17,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_17), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_18);
        $fwrite(evidence_fd, "tail_1ns,%.6f,18,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_18), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_19);
        $fwrite(evidence_fd, "tail_1ns,%.6f,19,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_19), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_20);
        $fwrite(evidence_fd, "tail_1ns,%.6f,20,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_20), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_21);
        $fwrite(evidence_fd, "tail_1ns,%.6f,21,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_21), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_22);
        $fwrite(evidence_fd, "tail_1ns,%.6f,22,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_22), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_23);
        $fwrite(evidence_fd, "tail_1ns,%.6f,23,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_23), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_24);
        $fwrite(evidence_fd, "tail_1ns,%.6f,24,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_24), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_25);
        $fwrite(evidence_fd, "tail_1ns,%.6f,25,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_25), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_26);
        $fwrite(evidence_fd, "tail_1ns,%.6f,26,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_26), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_27);
        $fwrite(evidence_fd, "tail_1ns,%.6f,27,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_27), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_28);
        $fwrite(evidence_fd, "tail_1ns,%.6f,28,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_28), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_29);
        $fwrite(evidence_fd, "tail_1ns,%.6f,29,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_29), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        #( 4364.475381433000 );
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_00);
        $fwrite(evidence_fd, "final,%.6f,0,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_00), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_01);
        $fwrite(evidence_fd, "final,%.6f,1,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_01), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_02);
        $fwrite(evidence_fd, "final,%.6f,2,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_02), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_03);
        $fwrite(evidence_fd, "final,%.6f,3,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_03), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_04);
        $fwrite(evidence_fd, "final,%.6f,4,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_04), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_05);
        $fwrite(evidence_fd, "final,%.6f,5,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_05), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_06);
        $fwrite(evidence_fd, "final,%.6f,6,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_06), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_07);
        $fwrite(evidence_fd, "final,%.6f,7,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_07), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_08);
        $fwrite(evidence_fd, "final,%.6f,8,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_08), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_09);
        $fwrite(evidence_fd, "final,%.6f,9,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_09), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_10);
        $fwrite(evidence_fd, "final,%.6f,10,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_10), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_11);
        $fwrite(evidence_fd, "final,%.6f,11,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_11), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_12);
        $fwrite(evidence_fd, "final,%.6f,12,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_12), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_13);
        $fwrite(evidence_fd, "final,%.6f,13,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_13), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_14);
        $fwrite(evidence_fd, "final,%.6f,14,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_14), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_15);
        $fwrite(evidence_fd, "final,%.6f,15,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_15), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_16);
        $fwrite(evidence_fd, "final,%.6f,16,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_16), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_17);
        $fwrite(evidence_fd, "final,%.6f,17,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_17), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_18);
        $fwrite(evidence_fd, "final,%.6f,18,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_18), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_19);
        $fwrite(evidence_fd, "final,%.6f,19,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_19), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_20);
        $fwrite(evidence_fd, "final,%.6f,20,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_20), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_21);
        $fwrite(evidence_fd, "final,%.6f,21,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_21), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_22);
        $fwrite(evidence_fd, "final,%.6f,22,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_22), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_23);
        $fwrite(evidence_fd, "final,%.6f,23,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_23), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_24);
        $fwrite(evidence_fd, "final,%.6f,24,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_24), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_25);
        $fwrite(evidence_fd, "final,%.6f,25,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_25), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_26);
        $fwrite(evidence_fd, "final,%.6f,26,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_26), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_27);
        $fwrite(evidence_fd, "final,%.6f,27,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_27), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_28);
        $fwrite(evidence_fd, "final,%.6f,28,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_28), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_29);
        $fwrite(evidence_fd, "final,%.6f,29,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_29), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
        $fclose(evidence_fd);
    end

    // A2D Q transitions are logged independently of periodic analog
    // samples to retain every observable post-close crossing.
    always @(q_0) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_00);
        $fwrite(evidence_fd, "q_event,%.6f,0,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_00), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_1) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_01);
        $fwrite(evidence_fd, "q_event,%.6f,1,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_01), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_2) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_02);
        $fwrite(evidence_fd, "q_event,%.6f,2,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_02), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_3) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_03);
        $fwrite(evidence_fd, "q_event,%.6f,3,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_03), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_4) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_04);
        $fwrite(evidence_fd, "q_event,%.6f,4,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_04), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_5) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_05);
        $fwrite(evidence_fd, "q_event,%.6f,5,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_05), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_6) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_06);
        $fwrite(evidence_fd, "q_event,%.6f,6,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_06), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_7) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_07);
        $fwrite(evidence_fd, "q_event,%.6f,7,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_07), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_8) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_08);
        $fwrite(evidence_fd, "q_event,%.6f,8,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_08), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_9) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_09);
        $fwrite(evidence_fd, "q_event,%.6f,9,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_09), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_10) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_10);
        $fwrite(evidence_fd, "q_event,%.6f,10,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_10), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_11) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_11);
        $fwrite(evidence_fd, "q_event,%.6f,11,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_11), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_12) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_12);
        $fwrite(evidence_fd, "q_event,%.6f,12,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_12), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_13) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_13);
        $fwrite(evidence_fd, "q_event,%.6f,13,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_13), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_14) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_14);
        $fwrite(evidence_fd, "q_event,%.6f,14,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_14), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_15) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_15);
        $fwrite(evidence_fd, "q_event,%.6f,15,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_15), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_16) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_16);
        $fwrite(evidence_fd, "q_event,%.6f,16,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_16), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_17) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_17);
        $fwrite(evidence_fd, "q_event,%.6f,17,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_17), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_18) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_18);
        $fwrite(evidence_fd, "q_event,%.6f,18,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_18), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_19) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_19);
        $fwrite(evidence_fd, "q_event,%.6f,19,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_19), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_20) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_20);
        $fwrite(evidence_fd, "q_event,%.6f,20,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_20), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_21) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_21);
        $fwrite(evidence_fd, "q_event,%.6f,21,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_21), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_22) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_22);
        $fwrite(evidence_fd, "q_event,%.6f,22,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_22), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_23) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_23);
        $fwrite(evidence_fd, "q_event,%.6f,23,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_23), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_24) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_24);
        $fwrite(evidence_fd, "q_event,%.6f,24,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_24), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_25) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_25);
        $fwrite(evidence_fd, "q_event,%.6f,25,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_25), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_26) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_26);
        $fwrite(evidence_fd, "q_event,%.6f,26,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_26), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_27) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_27);
        $fwrite(evidence_fd, "q_event,%.6f,27,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_27), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_28) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_28);
        $fwrite(evidence_fd, "q_event,%.6f,28,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_28), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    always @(q_29) begin
        analog_sample = $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.q_29);
        $fwrite(evidence_fd, "q_event,%.6f,29,%.9f,%.9f,%.9f,%.9f,%.9f\n", $realtime, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.safe_d_r_29), analog_sample, $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_sense), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.vdd_safe), $snps_get_volt(bfe2_l1a_vcs_xa.u_ams.latch_g_r));
    end

    // Keep the XA transient alive through the complete retained source window.
    initial begin
        #( 7000.000000 ) $finish;
    end
endmodule
