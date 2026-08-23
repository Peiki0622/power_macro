// ============================================================================
// FTC M1 exact detection-margin mapper
// ============================================================================
// This combinational block is deliberately a closed, literal M0 codebook.
// It does not infer a detector point from a voltage, a delta code, arithmetic,
// interpolation, or nearest-neighbor rule.  Every supported output below is
// one M0-characterized M_cal/F_cal snapshot plus one selected L0..L3 level.
//
// The mapper never drives physical sensor controls itself.  Its outputs are
// captured by ftc_detection_margin_manager before they can reach the frozen
// H0 detector-input interface.  That register boundary preserves the H0
// snapshot-equality handoff contract and makes all control transitions
// synchronous to the trusted controller clock.
// ============================================================================
`timescale 1ns/1ps
`default_nettype none

module ftc_detection_margin_mapper (
    // ------------------------------------------------------------------------
    // Immutable H0 calibration snapshot codes
    // ------------------------------------------------------------------------
    // These debug/status codes are captured once by H0 after successful
    // calibration.  They are the sole lookup key; M1 has no baseline-VDD port.
    input  logic [4:0]  cal_medium_code_snapshot_i,
    input  logic [3:0]  cal_fine_code_snapshot_i,

    // ------------------------------------------------------------------------
    // One of four exact M0 margin levels: 2'b00=L0 through 2'b11=L3.
    // The manager samples this value only with its synchronous valid request.
    // ------------------------------------------------------------------------
    input  logic [1:0]  margin_sel_i,

    // ------------------------------------------------------------------------
    // Exact lookup result and evidence qualification
    // ------------------------------------------------------------------------
    // mapping_supported_o is high only for the twelve characterized entries.
    // trip_qualified_o is intentionally independent: 0.80 V mappings and all
    // L0 guard snapshots remain mapping-supported but are not trip-qualified.
    output logic        mapping_supported_o,
    output logic        trip_qualified_o,

    // M_det/F_det are observability values.  F_det_o is four bits so the
    // legal detection-only value decimal 10 is representable without changing
    // frozen calibration registers, whose stepper remains capped at F9.
    output logic [4:0]  m_det_o,
    output logic [3:0]  f_det_o,

    // Physical detector target vectors in packed [15:0] / [9:0] order.
    // Medium is a positive prefix thermometer; fine is active-low.  These are
    // literal constants rather than a generic decoder, avoiding an accidental
    // unsupported-code mapping and keeping the codebook reviewable.
    output logic [15:0] target_medium_therm_o,
    output logic [9:0]  target_fine_therm_o
);

    // Unsupported inputs receive deterministic unused values.  The manager
    // gates handoff readiness with mapping_supported_o, so these constants can
    // never become live sensor controls or imply a fallback detector setting.
    always_comb begin
        mapping_supported_o     = 1'b0;
        trip_qualified_o        = 1'b0;
        m_det_o                 = 5'd0;
        f_det_o                 = 4'd0;
        target_medium_therm_o   = 16'h0000;
        target_fine_therm_o     = 10'h3ff;

        // Each branch is a direct transcription of M1_MARGIN_CODEBOOK.json.
        // No branch performs arithmetic on the calibration codes or level.
        unique case ({cal_medium_code_snapshot_i,
                     cal_fine_code_snapshot_i,
                     margin_sel_i})
            // H0 M7/F6 snapshot: 0.80 V evidence provenance.
            {5'd7, 4'd6, 2'd0}: begin
                mapping_supported_o   = 1'b1;
                m_det_o               = 5'd7;
                f_det_o               = 4'd6;
                target_medium_therm_o = 16'h007f;
                target_fine_therm_o   = 10'h3c0;
            end
            {5'd7, 4'd6, 2'd1}: begin
                mapping_supported_o   = 1'b1;
                m_det_o               = 5'd8;
                f_det_o               = 4'd6;
                target_medium_therm_o = 16'h00ff;
                target_fine_therm_o   = 10'h3c0;
            end
            {5'd7, 4'd6, 2'd2}: begin
                mapping_supported_o   = 1'b1;
                m_det_o               = 5'd8;
                f_det_o               = 4'd8;
                target_medium_therm_o = 16'h00ff;
                target_fine_therm_o   = 10'h300;
            end
            {5'd7, 4'd6, 2'd3}: begin
                mapping_supported_o   = 1'b1;
                m_det_o               = 5'd8;
                f_det_o               = 4'd9;
                target_medium_therm_o = 16'h00ff;
                target_fine_therm_o   = 10'h200;
            end

            // H0 M4/F6 snapshot: 0.95 V evidence provenance.
            {5'd4, 4'd6, 2'd0}: begin
                mapping_supported_o   = 1'b1;
                m_det_o               = 5'd4;
                f_det_o               = 4'd6;
                target_medium_therm_o = 16'h000f;
                target_fine_therm_o   = 10'h3c0;
            end
            {5'd4, 4'd6, 2'd1}: begin
                mapping_supported_o   = 1'b1;
                trip_qualified_o      = 1'b1;
                m_det_o               = 5'd4;
                f_det_o               = 4'd9;
                target_medium_therm_o = 16'h000f;
                target_fine_therm_o   = 10'h200;
            end
            {5'd4, 4'd6, 2'd2}: begin
                mapping_supported_o   = 1'b1;
                trip_qualified_o      = 1'b1;
                m_det_o               = 5'd5;
                f_det_o               = 4'd6;
                target_medium_therm_o = 16'h001f;
                target_fine_therm_o   = 10'h3c0;
            end
            {5'd4, 4'd6, 2'd3}: begin
                mapping_supported_o   = 1'b1;
                trip_qualified_o      = 1'b1;
                m_det_o               = 5'd5;
                f_det_o               = 4'd9;
                target_medium_therm_o = 16'h001f;
                target_fine_therm_o   = 10'h200;
            end

            // H0 M2/F9 snapshot: 1.10 V evidence provenance.  L1 and L3
            // intentionally use F10=10'h000, the all-load active-low state.
            {5'd2, 4'd9, 2'd0}: begin
                mapping_supported_o   = 1'b1;
                m_det_o               = 5'd2;
                f_det_o               = 4'd9;
                target_medium_therm_o = 16'h0003;
                target_fine_therm_o   = 10'h200;
            end
            {5'd2, 4'd9, 2'd1}: begin
                mapping_supported_o   = 1'b1;
                trip_qualified_o      = 1'b1;
                m_det_o               = 5'd2;
                f_det_o               = 4'd10;
                target_medium_therm_o = 16'h0003;
                target_fine_therm_o   = 10'h000;
            end
            {5'd2, 4'd9, 2'd2}: begin
                mapping_supported_o   = 1'b1;
                trip_qualified_o      = 1'b1;
                m_det_o               = 5'd3;
                f_det_o               = 4'd8;
                target_medium_therm_o = 16'h0007;
                target_fine_therm_o   = 10'h300;
            end
            {5'd2, 4'd9, 2'd3}: begin
                mapping_supported_o   = 1'b1;
                trip_qualified_o      = 1'b1;
                m_det_o               = 5'd3;
                f_det_o               = 4'd10;
                target_medium_therm_o = 16'h0007;
                target_fine_therm_o   = 10'h000;
            end

            default: begin
                // Defaults above deliberately preserve the unsupported state.
            end
        endcase
    end

endmodule

`default_nettype wire
