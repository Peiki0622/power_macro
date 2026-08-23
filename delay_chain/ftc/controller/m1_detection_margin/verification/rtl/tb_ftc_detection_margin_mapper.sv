// ============================================================================
// M1 RTL unit test: exact detection-margin mapper
// ============================================================================
// The test writes all twelve frozen M0 keys explicitly and checks every
// hardware-visible result.  It additionally exercises nearby unsupported
// snapshots so an accidental arithmetic or saturation implementation cannot
// pass by returning a plausible-but-uncharacterized configuration.
// ============================================================================
`timescale 1ns/1ps
`default_nettype none

module tb_ftc_detection_margin_mapper;
    // Lookup inputs corresponding to the immutable H0 snapshot codes and the
    // externally selected L0..L3 value.  They are driven directly because this
    // bench proves only pure combinational codebook behavior.
    logic [4:0] cal_medium_code_snapshot;
    logic [3:0] cal_fine_code_snapshot;
    logic [1:0] margin_sel;

    // Mapper outputs under test.  The exact physical vectors are checked in
    // the task below instead of being reconstructed by a decoder in the DUT.
    logic        mapping_supported;
    logic        trip_qualified;
    logic [4:0]  m_det;
    logic [3:0]  f_det;
    logic [15:0] target_medium_therm;
    logic [9:0]  target_fine_therm;
    integer      failures;

    ftc_detection_margin_mapper dut (
        .cal_medium_code_snapshot_i(cal_medium_code_snapshot),
        .cal_fine_code_snapshot_i  (cal_fine_code_snapshot),
        .margin_sel_i               (margin_sel),
        .mapping_supported_o        (mapping_supported),
        .trip_qualified_o           (trip_qualified),
        .m_det_o                    (m_det),
        .f_det_o                    (f_det),
        .target_medium_therm_o      (target_medium_therm),
        .target_fine_therm_o        (target_fine_therm)
    );

    // One call checks a complete M0 codebook entry.  This testbench task is
    // verification-only; the synthesizable mapper contains no functions or
    // programmable decoder.  A small delay lets always_comb settle before the
    // comparison, avoiding a same-time-slot testbench race.
    task automatic expect_supported(
        input logic [4:0] expected_cal_m,
        input logic [3:0] expected_cal_f,
        input logic [1:0] expected_level,
        input logic       expected_trip_qualified,
        input logic [4:0] expected_m_det,
        input logic [3:0] expected_f_det,
        input logic [15:0] expected_medium_therm,
        input logic [9:0] expected_fine_therm,
        input string label
    );
        begin
            cal_medium_code_snapshot = expected_cal_m;
            cal_fine_code_snapshot = expected_cal_f;
            margin_sel = expected_level;
            #0.01;
            if (mapping_supported !== 1'b1 ||
                trip_qualified !== expected_trip_qualified ||
                m_det !== expected_m_det || f_det !== expected_f_det ||
                target_medium_therm !== expected_medium_therm ||
                target_fine_therm !== expected_fine_therm) begin
                $display("FAIL %s: supp=%b trip=%b M/F=%0d/%0d therm=%h/%h",
                         label, mapping_supported, trip_qualified, m_det, f_det,
                         target_medium_therm, target_fine_therm);
                failures = failures + 1;
            end
        end
    endtask

    // Unsupported keys must have their valid bit low.  The deterministic
    // default vector itself is intentionally not treated as a legal fallback.
    task automatic expect_unsupported(
        input logic [4:0] input_cal_m,
        input logic [3:0] input_cal_f,
        input logic [1:0] input_level,
        input string label
    );
        begin
            cal_medium_code_snapshot = input_cal_m;
            cal_fine_code_snapshot = input_cal_f;
            margin_sel = input_level;
            #0.01;
            if (mapping_supported !== 1'b0 || trip_qualified !== 1'b0) begin
                $display("FAIL %s: unsupported key became valid", label);
                failures = failures + 1;
            end
        end
    endtask

    initial begin
        failures = 0;
        cal_medium_code_snapshot = 5'd0;
        cal_fine_code_snapshot = 4'd0;
        margin_sel = 2'd0;

        // M7/F6: mapping-supported only, because 0.80 V has no formal trip.
        expect_supported(5'd7, 4'd6, 2'd0, 1'b0, 5'd7, 4'd6, 16'h007f, 10'h3c0, "M7F6_L0");
        expect_supported(5'd7, 4'd6, 2'd1, 1'b0, 5'd8, 4'd6, 16'h00ff, 10'h3c0, "M7F6_L1");
        expect_supported(5'd7, 4'd6, 2'd2, 1'b0, 5'd8, 4'd8, 16'h00ff, 10'h300, "M7F6_L2");
        expect_supported(5'd7, 4'd6, 2'd3, 1'b0, 5'd8, 4'd9, 16'h00ff, 10'h200, "M7F6_L3");

        // M4/F6: L1..L3 carry only the already measured M0 trip qualification.
        expect_supported(5'd4, 4'd6, 2'd0, 1'b0, 5'd4, 4'd6, 16'h000f, 10'h3c0, "M4F6_L0");
        expect_supported(5'd4, 4'd6, 2'd1, 1'b1, 5'd4, 4'd9, 16'h000f, 10'h200, "M4F6_L1");
        expect_supported(5'd4, 4'd6, 2'd2, 1'b1, 5'd5, 4'd6, 16'h001f, 10'h3c0, "M4F6_L2");
        expect_supported(5'd4, 4'd6, 2'd3, 1'b1, 5'd5, 4'd9, 16'h001f, 10'h200, "M4F6_L3");

        // M2/F9: F10 vectors must be exact all-zero active-low physical rails.
        expect_supported(5'd2, 4'd9, 2'd0, 1'b0, 5'd2, 4'd9, 16'h0003, 10'h200, "M2F9_L0");
        expect_supported(5'd2, 4'd9, 2'd1, 1'b1, 5'd2, 4'd10, 16'h0003, 10'h000, "M2F9_L1_F10");
        expect_supported(5'd2, 4'd9, 2'd2, 1'b1, 5'd3, 4'd8, 16'h0007, 10'h300, "M2F9_L2");
        expect_supported(5'd2, 4'd9, 2'd3, 1'b1, 5'd3, 4'd10, 16'h0007, 10'h000, "M2F9_L3_F10");

        expect_unsupported(5'd6, 4'd6, 2'd0, "nearby_M6F6");
        expect_unsupported(5'd7, 4'd7, 2'd1, "nearby_M7F7");
        expect_unsupported(5'd4, 4'd5, 2'd2, "nearby_M4F5");
        expect_unsupported(5'd2, 4'd10, 2'd3, "nearby_M2F10");

        if (failures != 0) begin
            $display("M1 mapper unit FAIL: %0d failures", failures);
            $fatal(1);
        end
        $display("M1 mapper unit PASS: 12 exact entries, F10, qualification, unsupported keys");
        $finish;
    end
endmodule

`default_nettype wire
