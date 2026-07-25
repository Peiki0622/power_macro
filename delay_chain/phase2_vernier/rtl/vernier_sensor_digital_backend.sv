// Synthesizable digital backend for the standard-cell Vernier comparator bank.
// The analog/SPICE front end owns delay generation and DFF sampling.  This
// module only captures the already-sampled raw word, exposes detected bubbles,
// and encodes the corrected 0*1* thermometer transition without any #delay.
module vernier_sensor_digital_backend #(
    parameter int M_STAGES = 32,
    parameter int CODE_WIDTH = $clog2(M_STAGES + 1)
) (
    // Capture-domain control ports.  capture_clk is generated after the final
    // reference comparison edge; sensor_reset is active high to match the
    // discovered DFFRPQ asynchronous-clear polarity.
    input  logic                  capture_clk,
    input  logic                  sensor_reset,

    // Calibration is consumed by the analog launch-tap network.  It is kept
    // visible at this boundary so a controller can associate each sample with
    // its selected physical tap; it does not alter digital thermometer logic.
    input  logic [2:0]            cal_sel,

    // Raw DFF-bank word.  Bit zero is the earliest Vernier stage, so valid
    // words progress from zeroes to ones as the sense edge catches reference.
    input  logic [M_STAGES-1:0]   raw_code_i,

    // Registered raw evidence and corrected/encoded output contract.
    output logic [M_STAGES-1:0]   raw_code,
    output logic [M_STAGES-1:0]   corrected_code,
    output logic [CODE_WIDTH-1:0] sensor_code,
    output logic [CODE_WIDTH-1:0] bubble_count,
    output logic                  code_valid,
    output logic                  sample_done
);

    logic [M_STAGES-1:0] corrected_next;
    logic                 seen_one;
    integer               index;

    // Capture all comparator bits simultaneously at the controller-selected
    // completion edge.  No combinational path feeds back into the DFF bank.
    always_ff @(posedge capture_clk or posedge sensor_reset) begin
        if (sensor_reset) begin
            raw_code   <= '0;
            sample_done <= 1'b0;
        end else begin
            raw_code   <= raw_code_i;
            sample_done <= 1'b1;
        end
    end

    // Interior majority filtering suppresses a one-bit local bubble.  Edge
    // bits remain untouched because applying a fabricated external neighbor
    // would change the observable physical result rather than correct it.
    always_comb begin
        corrected_next = raw_code;
        for (index = 1; index < M_STAGES - 1; index = index + 1) begin
            corrected_next[index] = (raw_code[index-1] & raw_code[index]) |
                                    (raw_code[index-1] & raw_code[index+1]) |
                                    (raw_code[index] & raw_code[index+1]);
        end
    end

    // Leading-zero encoding and bubble detection are intentionally explicit.
    // A zero after the first corrected one is counted and invalidates the
    // word, so diagnostic software can distinguish a corrected-looking code
    // from a physically monotonic thermometer result.
    always_comb begin
        corrected_code = corrected_next;
        sensor_code = '0;
        bubble_count = '0;
        seen_one = 1'b0;
        for (index = 0; index < M_STAGES; index = index + 1) begin
            if (!seen_one && !corrected_next[index]) begin
                sensor_code = sensor_code + 1'b1;
            end
            if (corrected_next[index]) begin
                seen_one = 1'b1;
            end else if (seen_one) begin
                bubble_count = bubble_count + 1'b1;
            end
        end
        code_valid = (bubble_count == '0);
    end

endmodule
