// Synthesizable static self-calibration controller for the FTC threshold path.
//
// The controller deliberately implements only the measured startup operation:
// scan a 3-bit threshold code from zero upward and retain the first code whose
// completed real-DFF comparison is zero.  It is separate from ftc_sensor so
// the characterized sensor/capture hierarchy remains unchanged.  In
// particular, this RTL contains no timing delay, binary search, tracking, or
// acceptance-window behavior; analogue probe scheduling and DFF reset remain
// the responsibility of the surrounding comparator/probe wrapper.
`timescale 1ns/1ps
`default_nettype none

module ftc_static_calibration_controller (
    // Clock and reset domain.
    // clk_i clocks only digital calibration state.  reset_i asynchronously
    // returns the controller to IDLE, clears its candidate and retained lock
    // codes, and deasserts all terminal status.  It must be held asserted
    // while the external analogue comparator/probe wrapper is initialized.
    input  logic       clk_i,
    input  logic       reset_i,

    // Calibration start command.
    // start_i is sampled only in IDLE.  Requests while a calibration is in
    // progress or after DONE/FAULT are intentionally ignored so a stable
    // retained result cannot be overwritten without an explicit reset.
    input  logic       start_i,

    // Comparator probe-response handshake.
    // probe_done_i acknowledges the probe requested by probe_req_o and must
    // be asserted only after the selected code has settled, the DFF has been
    // reset, and one isolated physical probe has completed.  q_compare_i is
    // sampled with that acknowledgement: one means the DFF remained high;
    // zero means this code is at or beyond the real hardware boundary.
    input  logic       probe_done_i,
    input  logic       q_compare_i,

    // Comparator programming and request outputs.
    // code_o is the stable 3-bit threshold selector.  It changes only after
    // a completed high-Q probe, then spends a complete SETTLE state before a
    // new request.  probe_req_o is high for exactly the PROBE state, allowing
    // the wrapper to perform one reset/launch/read transaction per code.
    output logic       probe_req_o,
    output logic [2:0] code_o,

    // Retained calibration outcome.
    // lock_code_o captures the first legal zero-Q code.  done_o is asserted
    // only after a legal lock at code 1 through 5, which leaves codes above
    // the lock for the characterized two-code headroom requirement.  fault_o
    // is asserted for a zero at code 0, 6, or 7, or for Q still high at code
    // 7; neither terminal result is changed until reset_i is asserted.
    output logic [2:0] lock_code_o,
    output logic       done_o,
    output logic       fault_o
);
    // The five-state machine separates each electrical action.  SETTLE keeps
    // a changed MUX selection quiet for a full clock period; PROBE exposes a
    // single request; WAIT_RESULT samples only an acknowledged completed
    // comparison.  DONE and FAULT are sticky terminal states.
    typedef enum logic [2:0] {
        IDLE,
        SETTLE,
        PROBE,
        WAIT_RESULT,
        DONE,
        FAULT
    } state_t;

    state_t     state_q;
    state_t     state_d;
    logic [2:0] code_q;

    // State-transition logic contains the complete calibration policy.  A
    // high Q advances exactly one code without wraparound.  A low Q locks only
    // within 1..5; codes 0, 6 and 7 are explicit range/headroom failures.
    always_comb begin
        state_d = state_q;
        case (state_q)
            IDLE: begin
                if (start_i) begin
                    state_d = SETTLE;
                end
            end

            SETTLE: begin
                state_d = PROBE;
            end

            PROBE: begin
                state_d = WAIT_RESULT;
            end

            WAIT_RESULT: begin
                if (probe_done_i) begin
                    if (!q_compare_i) begin
                        if ((code_q >= 3'd1) && (code_q <= 3'd5)) begin
                            state_d = DONE;
                        end else begin
                            state_d = FAULT;
                        end
                    end else if (code_q == 3'd7) begin
                        state_d = FAULT;
                    end else begin
                        state_d = SETTLE;
                    end
                end
            end

            DONE: begin
                state_d = DONE;
            end

            FAULT: begin
                state_d = FAULT;
            end

            default: begin
                state_d = FAULT;
            end
        endcase
    end

    // All retained hardware state changes on one clock edge.  The candidate
    // increments only after an acknowledged high-Q result and the explicit
    // code-7 guard prevents arithmetic wraparound.  lock_code_o changes only
    // on a legal first zero, so FAULT never exposes an invalid lock value.
    always_ff @(posedge clk_i or posedge reset_i) begin
        if (reset_i) begin
            state_q     <= IDLE;
            code_q      <= 3'd0;
            lock_code_o <= 3'd0;
        end else begin
            state_q <= state_d;
            if ((state_q == WAIT_RESULT) && probe_done_i && q_compare_i &&
                (code_q != 3'd7)) begin
                code_q <= code_q + 3'd1;
            end
            if ((state_q == WAIT_RESULT) && probe_done_i && !q_compare_i &&
                (code_q >= 3'd1) && (code_q <= 3'd5)) begin
                lock_code_o <= code_q;
            end
        end
    end

    // Terminal and request status are direct decoded state signals.  This
    // makes reset behavior and one-state PROBE pulse width unambiguous without
    // introducing extra status flops or a second clocked protocol.
    always_comb begin
        code_o      = code_q;
        probe_req_o = (state_q == PROBE);
        done_o      = (state_q == DONE);
        fault_o     = (state_q == FAULT);
    end
endmodule

`default_nettype wire
