// Registered, single-step FTC medium/fine thermometer configuration.
//
// The physical sensor rails are the registered vectors medium_therm_o and
// fine_therm_o.  The code registers below are bookkeeping/debug state only;
// there is deliberately no combinational binary-to-thermometer decoder.
`timescale 1ns/1ps
`default_nettype none

module ftc_cfg_therm_regs #(
    parameter int MEDIUM_BITS = 16,
    parameter int FINE_BITS = 10,
    parameter int MEDIUM_CODE_WIDTH = 5,
    parameter int FINE_CODE_WIDTH = 4
) (
    // Controller clock.  All configuration changes occur on this edge.
    input  logic                         clk_i,
    // Active-low controller POR.  Reset is the only way to clear a lock.
    input  logic                         por_n_i,
    // Synchronous initialization request; returns both vectors to code zero.
    input  logic                         init_i,
    // One-cycle single-step requests from the calibration FSM/sequencer.
    input  logic                         medium_inc_i,
    input  logic                         medium_dec_i,
    input  logic                         fine_inc_i,
    input  logic                         fine_dec_i,
    // Permanent lock request.  Once captured, all step requests are ignored
    // until por_n_i is asserted low.
    input  logic                         lock_i,
    // Registered physical medium and fine control rails.
    output logic [MEDIUM_BITS-1:0]       medium_therm_o,
    output logic [FINE_BITS-1:0]         fine_therm_o,
    // Registered binary positions used for status/debug only.
    output logic [MEDIUM_CODE_WIDTH-1:0] medium_code_o,
    output logic [FINE_CODE_WIDTH-1:0]   fine_code_o,
    // Range and lock status.
    output logic                         medium_at_min_o,
    output logic                         medium_at_max_o,
    output logic                         fine_at_min_o,
    output logic                         fine_at_max_o,
    output logic                         cfg_locked_o,
    // Additional range check for two-step backoff safety.
    // True when medium_code < 2 (insufficient room for two-step backoff).
    output logic                         medium_too_low_for_backoff_o
);
    // The vectors are initialized to the physical code-zero encodings:
    // medium first-code-high => all zero; fine active-low => all one.
    always_ff @(posedge clk_i or negedge por_n_i) begin
        if (!por_n_i) begin
            medium_therm_o <= '0;
            fine_therm_o <= {FINE_BITS{1'b1}};
            medium_code_o <= '0;
            fine_code_o <= '0;
            cfg_locked_o <= 1'b0;
        end else begin
            if (init_i) begin
                medium_therm_o <= '0;
                fine_therm_o <= {FINE_BITS{1'b1}};
                medium_code_o <= '0;
                fine_code_o <= '0;
                cfg_locked_o <= 1'b0;
            end else begin
                if (lock_i)
                    cfg_locked_o <= 1'b1;

                if (!cfg_locked_o && !lock_i) begin
                    // Medium code increments assert exactly the next rail.
                    if (medium_inc_i && (medium_code_o < MEDIUM_BITS)) begin
                        medium_therm_o[medium_code_o] <= 1'b1;
                        medium_code_o <= medium_code_o + 1'b1;
                    end
                    // Medium decrements release exactly the previous rail.
                    if (medium_dec_i && (medium_code_o > 0)) begin
                        medium_therm_o[medium_code_o - 1'b1] <= 1'b0;
                        medium_code_o <= medium_code_o - 1'b1;
                    end
                    // Fine code increments assert one active-low rail.
                    if (fine_inc_i && (fine_code_o < FINE_BITS)) begin
                        fine_therm_o[fine_code_o] <= 1'b0;
                        fine_code_o <= fine_code_o + 1'b1;
                    end
                    // Fine decrements release exactly the previous rail.
                    if (fine_dec_i && (fine_code_o > 0)) begin
                        fine_therm_o[fine_code_o - 1'b1] <= 1'b1;
                        fine_code_o <= fine_code_o - 1'b1;
                    end
                end
            end
        end
    end

    // These flags are pure comparisons of registered state and are not used
    // to drive the physical vectors.
    always_comb begin
        medium_at_min_o = (medium_code_o == 0);
        medium_at_max_o = (medium_code_o == MEDIUM_BITS);
        fine_at_min_o = (fine_code_o == 0);
        fine_at_max_o = (fine_code_o == FINE_BITS);
        // Two-step backoff requires medium_code >= 2 to reach medium_code-2.
        medium_too_low_for_backoff_o = (medium_code_o < 2);
    end
endmodule

`default_nettype wire
