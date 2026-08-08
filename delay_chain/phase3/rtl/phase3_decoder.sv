// Synthesizable Phase-3 thermometer capture and decoder.
//
// The decoder accepts the physical 32-bit DFF word, normalizes the selected
// 1*0 raw polarity to a 0*1 thermometer convention, applies a three-bit
// interior majority correction, then encodes the leading-zero count.  It is
// deliberately limited to those operations; no CUSUM, filtering history, or
// glitch capture state is added in this phase.
`default_nettype none

module phase3_decoder (
    // Capture-control interface:
    // clk_i captures a settled physical DFF word, rst_i clears the registered
    // capture state, and capture_enable_i marks the single cycle to capture.
    input  logic        clk_i,
    input  logic        rst_i,
    input  logic        capture_enable_i,

    // Physical-thermometer input interface:
    // raw_thermometer_i is the real comparator-bank word, with bit 0 assigned
    // to the earliest stage.  Its bit order matches the SPICE CSV evidence.
    input  logic [31:0] raw_thermometer_i,

    // Decoder-observability and result interface:
    // raw_thermometer_o retains captured raw evidence; normalized_thermometer_o
    // and corrected_thermometer_o expose the two decode stages.  sensor_code_o
    // is the 0..32 leading-zero position, bubble_count_o reports later zeros,
    // code_valid_o qualifies the corrected word, and sample_valid_o marks a
    // fresh capture for one controller clock.
    output logic [31:0] raw_thermometer_o,
    output logic [31:0] normalized_thermometer_o,
    output logic [31:0] corrected_thermometer_o,
    output logic [5:0]  sensor_code_o,
    output logic [5:0]  bubble_count_o,
    output logic        code_valid_o,
    output logic        sample_valid_o
);
    import phase3_calibration_pkg::*;

    // Combinational intermediate values separate physical capture from decode.
    logic [31:0] normalized_next;
    logic [31:0] corrected_next;
    logic [5:0]  sensor_code_next;
    logic [5:0]  bubble_count_next;
    logic [5:0]  transition_count_next;
    logic        code_valid_next;
    logic        seen_one;
    // Each always_comb block owns its own loop variable.  Sharing a procedural
    // integer across blocks would create multiple drivers under strict VCS
    // elaboration even though the synthesized loop bounds are constant.
    integer      majority_index;
    integer      encode_index;

    // Raw capture is the only sequential thermometer storage.  The physical
    // frontend must settle before capture_enable_i; this module introduces no
    // timing delay or resampling of individual comparator bits.
    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i) begin
            raw_thermometer_o <= '0;
            sample_valid_o    <= 1'b0;
        end else begin
            sample_valid_o <= capture_enable_i;
            if (capture_enable_i) begin
                raw_thermometer_o <= raw_thermometer_i;
            end
        end
    end

    // Normalize raw 1*0 captures into the common decoder 0*1 convention.
    // The constant comes from the selected physical polarity, not a runtime
    // mode, so no uncalibrated polarity control is exposed at the top level.
    always_comb begin
        if (THERMOMETER_INVERT) begin
            normalized_next = ~raw_thermometer_o;
        end else begin
            normalized_next = raw_thermometer_o;
        end
    end

    // Three-bit majority correction changes only interior bits.  Endpoints are
    // copied directly because inventing a neighbor outside the 32-stage chain
    // would change the observed hardware data rather than repair a bubble.
    always_comb begin
        corrected_next = normalized_next;
        for (majority_index = 1; majority_index < 31; majority_index = majority_index + 1) begin
            corrected_next[majority_index] =
                (normalized_next[majority_index - 1] & normalized_next[majority_index]) |
                (normalized_next[majority_index - 1] & normalized_next[majority_index + 1]) |
                (normalized_next[majority_index] & normalized_next[majority_index + 1]);
        end
    end

    // Count the leading zero run, count any later zero bubbles, and record the
    // number of 0/1 boundaries.  All counters are fixed six-bit hardware and
    // the bounded for-loop unrolls to exactly 32 comparisons during synthesis.
    always_comb begin
        sensor_code_next      = '0;
        bubble_count_next     = '0;
        transition_count_next = '0;
        seen_one              = 1'b0;
        for (encode_index = 0; encode_index < 32; encode_index = encode_index + 1) begin
            if (!seen_one && !corrected_next[encode_index]) begin
                sensor_code_next = sensor_code_next + 6'd1;
            end
            if (corrected_next[encode_index]) begin
                seen_one = 1'b1;
            end else if (seen_one) begin
                bubble_count_next = bubble_count_next + 6'd1;
            end
            if ((encode_index != 0) && (corrected_next[encode_index] != corrected_next[encode_index - 1])) begin
                transition_count_next = transition_count_next + 6'd1;
            end
        end
        code_valid_next = (bubble_count_next == 6'd0) && (transition_count_next <= 6'd1);
    end

    // The decoded data is combinational from the registered raw capture.  On
    // the capture clock edge sample_valid_o identifies the new stable result.
    always_comb begin
        normalized_thermometer_o = normalized_next;
        corrected_thermometer_o  = corrected_next;
        sensor_code_o            = sensor_code_next;
        bubble_count_o           = bubble_count_next;
        code_valid_o             = code_valid_next;
    end
endmodule

`default_nettype wire
