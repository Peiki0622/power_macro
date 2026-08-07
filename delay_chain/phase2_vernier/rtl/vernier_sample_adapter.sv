// One-cycle request adapter for the Vernier macro wrapper.
//
// The public macro request is the external "please take a sample" pulse.  This
// adapter turns that request into the internal capture-enable beat used by the
// digital backend, while letting the physical launch network consume the
// request directly in the same cycle.
`default_nettype none

module vernier_sample_adapter (
    // Clock used to time the request-to-capture separation.
    input  logic clk_i,

    // Active-high asynchronous clear.
    input  logic rst_i,

    // Public request from the macro interface.
    input  logic sample_req_i,

    // Internal one-cycle delayed capture enable for the backend.
    output logic capture_enable_o
);
    logic sample_req_q;

    // Register the public request for one cycle and edge-detect it so a caller
    // that holds sample_req_i high cannot generate repeated backend captures.
    // The physical launch still consumes sample_req_i directly; only the
    // backend capture pulse is delayed by one clk cycle.
    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i) begin
            capture_enable_o <= 1'b0;
            sample_req_q     <= 1'b0;
        end else begin
            capture_enable_o <= sample_req_i && !sample_req_q;
            sample_req_q     <= sample_req_i;
        end
    end

endmodule

`default_nettype wire
