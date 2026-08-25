// ============================================================================
// B-FE2-L0 VCS behavioral replay testbench
//
// The bench replays the immutable B-FE2.2C normal/L2 stimulus.  Thirty scalar
// real variables are used instead of unpacked real arrays because the host
// VCS front end crashes while finalizing unpacked-real aggregate designs.
// The scalar names are the 30 modular XOR, safe_d, and Q ports; macro calls
// below expand the identical equation for every tap without hiding a tap.
// ============================================================================
`timescale 1ps/1ps

module tb_bfe2_l0;
    string input_path;
    string output_path;
    integer input_fd;
    integer output_fd;
    integer rc;
    integer row_count;
    real time_ps;
    real previous_time_ps;
    real delta_ps;
    real vdd_sense_voltage;
    real g_voltage;
    real vdd_safe_voltage;

    real xor_0, xor_1, xor_2, xor_3, xor_4, xor_5, xor_6, xor_7, xor_8, xor_9;
    real xor_10, xor_11, xor_12, xor_13, xor_14, xor_15, xor_16, xor_17, xor_18, xor_19;
    real xor_20, xor_21, xor_22, xor_23, xor_24, xor_25, xor_26, xor_27, xor_28, xor_29;
    real safe_d_0, safe_d_1, safe_d_2, safe_d_3, safe_d_4, safe_d_5, safe_d_6, safe_d_7, safe_d_8, safe_d_9;
    real safe_d_10, safe_d_11, safe_d_12, safe_d_13, safe_d_14, safe_d_15, safe_d_16, safe_d_17, safe_d_18, safe_d_19;
    real safe_d_20, safe_d_21, safe_d_22, safe_d_23, safe_d_24, safe_d_25, safe_d_26, safe_d_27, safe_d_28, safe_d_29;
    real q_0, q_1, q_2, q_3, q_4, q_5, q_6, q_7, q_8, q_9;
    real q_10, q_11, q_12, q_13, q_14, q_15, q_16, q_17, q_18, q_19;
    real q_20, q_21, q_22, q_23, q_24, q_25, q_26, q_27, q_28, q_29;

    localparam real FIXED_PD_SAFE_V = 0.95;

    // The marker module carries the L0 contract; this bench executes its
    // scalar equations so VCS never has to elaborate an unpacked real port.
    bfe2_l0_behavior_model u_l0_contract();

    // One macro invocation is one fully independent XOR->Level-0->latch tap.
    // Strict thresholding and transparent-high/hold-low behavior are explicit.
`define L0_STEP(X, D, Q) \
    begin \
        if (X > (0.5 * vdd_sense_voltage)) D = FIXED_PD_SAFE_V; else D = 0.0; \
        if (g_voltage > (0.5 * FIXED_PD_SAFE_V)) Q = D; \
    end

`define READ_X(X) rc = $fscanf(input_fd, " %f", X)
`define WRITE_V(V) $fwrite(output_fd, " %0.9f", V)

    initial begin
        if (!$value$plusargs("INPUT=%s", input_path))
            $fatal(1, "L0_FAIL missing +INPUT");
        if (!$value$plusargs("OUTPUT=%s", output_path))
            $fatal(1, "L0_FAIL missing +OUTPUT");
        input_fd = $fopen(input_path, "r");
        output_fd = $fopen(output_path, "w");
        if (input_fd == 0 || output_fd == 0)
            $fatal(1, "L0_FAIL cannot open input/output files");

        $fwrite(output_fd, "time_ps vdd_sense_v vdd_safe_v g_v");
        for (rc = 0; rc < 30; rc = rc + 1) $fwrite(output_fd, " xor_%0d", rc);
        for (rc = 0; rc < 30; rc = rc + 1) $fwrite(output_fd, " safe_d_%0d", rc);
        for (rc = 0; rc < 30; rc = rc + 1) $fwrite(output_fd, " q_%0d", rc);
        $fwrite(output_fd, "\n");

        previous_time_ps = 0.0;
        row_count = 0;
        q_0=0.0; q_1=0.0; q_2=0.0; q_3=0.0; q_4=0.0; q_5=0.0; q_6=0.0; q_7=0.0; q_8=0.0; q_9=0.0;
        q_10=0.0; q_11=0.0; q_12=0.0; q_13=0.0; q_14=0.0; q_15=0.0; q_16=0.0; q_17=0.0; q_18=0.0; q_19=0.0;
        q_20=0.0; q_21=0.0; q_22=0.0; q_23=0.0; q_24=0.0; q_25=0.0; q_26=0.0; q_27=0.0; q_28=0.0; q_29=0.0;

        while (!$feof(input_fd)) begin
            rc = $fscanf(input_fd, "%f %f %f", time_ps, vdd_sense_voltage, g_voltage);
            if (rc != 3) break;
            rc = $fscanf(input_fd, "%f %f %f %f %f %f %f %f %f %f %f %f %f %f %f %f %f %f %f %f %f %f %f %f %f %f %f %f %f %f", xor_0, xor_1, xor_2, xor_3, xor_4, xor_5, xor_6, xor_7, xor_8, xor_9, xor_10, xor_11, xor_12, xor_13, xor_14, xor_15, xor_16, xor_17, xor_18, xor_19, xor_20, xor_21, xor_22, xor_23, xor_24, xor_25, xor_26, xor_27, xor_28, xor_29);
            delta_ps = time_ps - previous_time_ps;
            if (delta_ps > 0.0) #(delta_ps);
            `L0_STEP(xor_0,safe_d_0,q_0); `L0_STEP(xor_1,safe_d_1,q_1); `L0_STEP(xor_2,safe_d_2,q_2);
            `L0_STEP(xor_3,safe_d_3,q_3); `L0_STEP(xor_4,safe_d_4,q_4); `L0_STEP(xor_5,safe_d_5,q_5);
            `L0_STEP(xor_6,safe_d_6,q_6); `L0_STEP(xor_7,safe_d_7,q_7); `L0_STEP(xor_8,safe_d_8,q_8);
            `L0_STEP(xor_9,safe_d_9,q_9); `L0_STEP(xor_10,safe_d_10,q_10); `L0_STEP(xor_11,safe_d_11,q_11);
            `L0_STEP(xor_12,safe_d_12,q_12); `L0_STEP(xor_13,safe_d_13,q_13); `L0_STEP(xor_14,safe_d_14,q_14);
            `L0_STEP(xor_15,safe_d_15,q_15); `L0_STEP(xor_16,safe_d_16,q_16); `L0_STEP(xor_17,safe_d_17,q_17);
            `L0_STEP(xor_18,safe_d_18,q_18); `L0_STEP(xor_19,safe_d_19,q_19); `L0_STEP(xor_20,safe_d_20,q_20);
            `L0_STEP(xor_21,safe_d_21,q_21); `L0_STEP(xor_22,safe_d_22,q_22); `L0_STEP(xor_23,safe_d_23,q_23);
            `L0_STEP(xor_24,safe_d_24,q_24); `L0_STEP(xor_25,safe_d_25,q_25); `L0_STEP(xor_26,safe_d_26,q_26);
            `L0_STEP(xor_27,safe_d_27,q_27); `L0_STEP(xor_28,safe_d_28,q_28); `L0_STEP(xor_29,safe_d_29,q_29);
            $fwrite(output_fd, "%0.9f %0.9f %0.9f %0.9f", time_ps, vdd_sense_voltage, FIXED_PD_SAFE_V, g_voltage);
            $fwrite(output_fd, " %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f", xor_0, xor_1, xor_2, xor_3, xor_4, xor_5, xor_6, xor_7, xor_8, xor_9, xor_10, xor_11, xor_12, xor_13, xor_14, xor_15, xor_16, xor_17, xor_18, xor_19, xor_20, xor_21, xor_22, xor_23, xor_24, xor_25, xor_26, xor_27, xor_28, xor_29);
            $fwrite(output_fd, " %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f", safe_d_0, safe_d_1, safe_d_2, safe_d_3, safe_d_4, safe_d_5, safe_d_6, safe_d_7, safe_d_8, safe_d_9, safe_d_10, safe_d_11, safe_d_12, safe_d_13, safe_d_14, safe_d_15, safe_d_16, safe_d_17, safe_d_18, safe_d_19, safe_d_20, safe_d_21, safe_d_22, safe_d_23, safe_d_24, safe_d_25, safe_d_26, safe_d_27, safe_d_28, safe_d_29);
            $fwrite(output_fd, " %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f %0.9f", q_0, q_1, q_2, q_3, q_4, q_5, q_6, q_7, q_8, q_9, q_10, q_11, q_12, q_13, q_14, q_15, q_16, q_17, q_18, q_19, q_20, q_21, q_22, q_23, q_24, q_25, q_26, q_27, q_28, q_29);
            $fwrite(output_fd, "\n");
            previous_time_ps = time_ps;
            row_count = row_count + 1;
        end
        $fclose(input_fd); $fclose(output_fd);
        if (row_count < 2) $fatal(1, "L0_FAIL insufficient replay rows=%0d", row_count);
        $display("L0_PASS rows=%0d pd_safe_v=%0.3f", row_count, FIXED_PD_SAFE_V);
        $finish;
    end

    initial begin
        #10000000;
        $fatal(1, "L0_FAIL timeout");
    end
endmodule
