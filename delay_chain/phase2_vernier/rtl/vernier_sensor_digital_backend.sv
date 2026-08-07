`default_nettype none

// Synthesizable digital backend for the standard-cell Vernier comparator bank.
//
// The physical frontend owns launch generation, comparator sampling, and the
// recovered raw thermometer word.  This module only latches that already-made
// word on a controller request, reports a one-cycle sample-valid pulse, applies
// the documented interior majority correction, and emits the leading-zero code
// plus bubble validity metadata.
module vernier_sensor_digital_backend #(
    parameter int M_STAGES = 32,
    parameter int CODE_WIDTH = $clog2(M_STAGES + 1)
) (
    // Clock domain used by the controller that requests one capture cycle.
    input  logic                  clk,

    // One-cycle capture request in the clk domain.  The upstream sample adapter
    // guarantees the pulse width, so the backend can use this signal directly.
    input  logic                  capture_enable,

    // Active-high asynchronous clear shared with the comparator-bank DFFs.
    // This matches the selected DFFRPQ_X0P5M_A9TR40 reset polarity.
    input  logic                  sensor_reset,

    // Calibrated launch selection is threaded through the boundary so the
    // controller can associate each decoded sample with the physical tap that
    // produced it.  It does not alter the thermometer decode itself.
    input  logic [2:0]            cal_sel,

    // Raw comparator-bank word.  Bit zero is the earliest Vernier stage, so a
    // monotonic capture moves from zeroes toward ones as delay accumulates.
    input  logic [M_STAGES-1:0]   raw_code_i,

    // Registered raw evidence and corrected/encoded output contract.
    output logic [M_STAGES-1:0]   raw_code,
    output logic [M_STAGES-1:0]   corrected_code,
    output logic [CODE_WIDTH-1:0] sensor_code,
    output logic [CODE_WIDTH-1:0] bubble_count,
    output logic                  code_valid,
    output logic                  sample_valid
);

    logic [M_STAGES-1:0] corrected_next;
    logic                 seen_one;
    integer               correct_index;
    integer               encode_index;

    // Latch the raw word only when a new capture request arrives.  The sample
    // valid pulse is generated from the same edge so the consumer sees one
    // clean request/response beat per measurement.
    always_ff @(posedge clk or posedge sensor_reset) begin
        if (sensor_reset) begin
            raw_code     <= '0;
            sample_valid <= 1'b0;
        end else begin
            sample_valid <= capture_enable;
            if (capture_enable) begin
                raw_code <= raw_code_i;
            end
        end
    end

    // Interior majority filtering suppresses a one-bit local bubble.  Edge
    // bits remain untouched because fabricating an external neighbor would
    // change the observed physical result instead of correcting it.
    always_comb begin
        corrected_next = raw_code;
        for (correct_index = 1; correct_index < M_STAGES - 1; correct_index = correct_index + 1) begin
            corrected_next[correct_index] = (raw_code[correct_index - 1] & raw_code[correct_index]) |
                                            (raw_code[correct_index - 1] & raw_code[correct_index + 1]) |
                                            (raw_code[correct_index] & raw_code[correct_index + 1]);
        end
    end

    // Leading-zero encoding and bubble detection stay fully explicit so the
    // RTL mirrors the Python reference model used by the Phase 2 reports.
    always_comb begin
        corrected_code = corrected_next;
        sensor_code    = '0;
        bubble_count   = '0;
        seen_one       = 1'b0;
        for (encode_index = 0; encode_index < M_STAGES; encode_index = encode_index + 1) begin
            if (!seen_one && !corrected_next[encode_index]) begin
                sensor_code = sensor_code + 1'b1;
            end
            if (corrected_next[encode_index]) begin
                seen_one = 1'b1;
            end else if (seen_one) begin
                bubble_count = bubble_count + 1'b1;
            end
        end
        code_valid = (bubble_count == '0);
    end

endmodule

`default_nettype wire
