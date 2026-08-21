// FTC high-level calibration finite-state machine.
//
// This module implements the algorithmic decision logic for the startup
// calibration protocol.  It orchestrates the coarse search, two-step backoff,
// fine search, and guard/hold verification sequence.  All cycle-level timing
// and sensor control generation is delegated to the operation sequencer.
//
// The FSM operates on a simple request/busy/done handshake with the sequencer:
// it asserts seq_req_o with the desired operation command and configuration
// action, waits for seq_busy_o to go low and seq_done_o to pulse, then
// evaluates the result and decides the next state.
//
// Decision semantics frozen by Phase 0 contract:
// - Coarse: two independent probes per M; both must be STABLE_LOW to confirm boundary
// - Backoff: exactly two config updates (M_boundary -> M-1 -> M-2), zero probes between
// - Fine: STABLE_HIGH continues scan; STABLE_LOW or AMBIGUOUS is boundary
// - Guard/Hold: both must independently be STABLE_LOW; otherwise FAIL
//
// After successful hold probe, the FSM asserts lock_valid_o, cal_done_o, freezes
// all outputs, and remains in LOCKED state until POR.
`timescale 1ns/1ps
`default_nettype none

module ftc_cal_fsm (
    // =========================================================================
    // Clock and Reset
    // =========================================================================
    // Synchronous 1 GHz calibration clock from the frozen Phase 1 contract.
    input  logic       cal_clk_i,
    // Active-low controller power-on-reset.  This is the controller's own
    // reset, independent of the sensor DFF reset controlled by the sequencer.
    input  logic       ctrl_por_n_i,

    // =========================================================================
    // Control Input
    // =========================================================================
    // Start calibration request.  Sampled when FSM is in IDLE state.
    input  logic       cal_start_i,

    // =========================================================================
    // Operation Sequencer Interface
    // =========================================================================
    // Request handshake: FSM asserts seq_req_o with cmd and config action,
    // waits for seq_busy_o to deassert and seq_done_o to pulse.
    input  logic       seq_busy_i,
    input  logic       seq_done_i,
    input  logic       seq_probe_done_i,
    output logic       seq_req_o,
    output logic [1:0] seq_cmd_o,
    output logic       seq_medium_inc_o,
    output logic       seq_medium_dec_o,
    output logic       seq_fine_inc_o,
    output logic       seq_fine_dec_o,

    // =========================================================================
    // Q Classifier Input (from sequencer's embedded sampler)
    // =========================================================================
    // Two-sample Q classification result: STABLE_LOW, STABLE_HIGH, or AMBIGUOUS.
    input  logic [1:0] q_class_i,
    input  logic       q_class_valid_i,

    // =========================================================================
    // Configuration Register Status (from thermometer registers)
    // =========================================================================
    // Range flags used for defensive failure detection.
    input  logic       cfg_at_max_medium_i,
    input  logic       cfg_at_min_medium_i,
    input  logic       cfg_at_max_fine_i,
    // True when medium_code < 2 (insufficient room for two-step backoff).
    input  logic       cfg_medium_too_low_for_backoff_i,

    // =========================================================================
    // Calibration Status Outputs
    // =========================================================================
    // Calibration is active (not IDLE, LOCKED, or FAIL).
    output logic       cal_busy_o,
    // Calibration completed successfully and configuration is locked.
    output logic       cal_done_o,
    // Calibration failed; see fail_reason_o for root cause.
    output logic       cal_fail_o,
    // Lock valid: configuration is frozen and safe to use for detection.
    output logic       lock_valid_o,
    // Encoded failure reason (3 bits support up to 8 failure modes).
    output logic [2:0] fail_reason_o,

    // =========================================================================
    // Debug Output
    // =========================================================================
    // FSM state encoding for waveform analysis and testbench monitoring.
    output logic [4:0] fsm_state_o
);
    // =========================================================================
    // Import Phase 1 Timing Constants and Q Class Encodings
    // =========================================================================
    import ftc_cal_pkg::*;

    // =========================================================================
    // Operation Commands (match sequencer encoding)
    // =========================================================================
    localparam logic [1:0] OP_CONFIG_UPDATE = 2'b01;
    localparam logic [1:0] OP_PROBE         = 2'b10;

    // =========================================================================
    // Failure Reason Encodings (3-bit)
    // =========================================================================
    localparam logic [2:0] FAIL_NONE                   = 3'b000;
    localparam logic [2:0] FAIL_COARSE_RANGE           = 3'b001;
    localparam logic [2:0] FAIL_COARSE_BACKOFF_UNDERFLOW = 3'b010;
    localparam logic [2:0] FAIL_FINE_RANGE             = 3'b011;
    localparam logic [2:0] FAIL_GUARD_RANGE            = 3'b100;
    localparam logic [2:0] FAIL_GUARD_NOT_LOW          = 3'b101;
    localparam logic [2:0] FAIL_HOLD_NOT_LOW           = 3'b110;

    // =========================================================================
    // FSM State Encodings (5-bit one-hot for clarity and timing)
    // =========================================================================
    typedef enum logic [4:0] {
        ST_IDLE            = 5'b00000,
        ST_INIT            = 5'b00001,
        ST_COARSE_PROBE_A  = 5'b00010,
        ST_COARSE_PROBE_B  = 5'b00011,
        ST_COARSE_EVAL     = 5'b00100,
        ST_COARSE_INC      = 5'b00101,
        ST_BACKOFF_1       = 5'b00110,
        ST_BACKOFF_2       = 5'b00111,
        ST_FINE_PROBE      = 5'b01000,
        ST_FINE_EVAL       = 5'b01001,
        ST_FINE_INC        = 5'b01010,
        ST_GUARD_INC       = 5'b01011,
        ST_GUARD_PROBE     = 5'b01100,
        ST_HOLD_PROBE      = 5'b01101,
        ST_LOCKED          = 5'b01110,
        ST_FAIL            = 5'b01111
    } state_t;

    state_t state_q, state_d;

    // =========================================================================
    // Internal Registers
    // =========================================================================
    // Store independent coarse probe A and B results.
    logic [1:0] coarse_probe_a_result_q, coarse_probe_a_result_d;
    logic [1:0] coarse_probe_b_result_q, coarse_probe_b_result_d;

    // Store fine probe result for evaluation.
    logic [1:0] fine_probe_result_q, fine_probe_result_d;

    // Store guard and hold probe results.
    logic [1:0] guard_result_q, guard_result_d;
    logic [1:0] hold_result_q, hold_result_d;

    // Failure reason register (stable after entering FAIL state).
    logic [2:0] fail_reason_q, fail_reason_d;

    // Sequencer request outputs (registered for timing).
    logic       seq_req_q, seq_req_d;
    logic [1:0] seq_cmd_q, seq_cmd_d;
    logic       seq_medium_inc_q, seq_medium_inc_d;
    logic       seq_medium_dec_q, seq_medium_dec_d;
    logic       seq_fine_inc_q, seq_fine_inc_d;
    logic       seq_fine_dec_q, seq_fine_dec_d;

    // Status outputs (registered for timing and glitch-free behavior).
    logic       cal_busy_q, cal_busy_d;
    logic       cal_done_q, cal_done_d;
    logic       cal_fail_q, cal_fail_d;
    logic       lock_valid_q, lock_valid_d;

    // =========================================================================
    // Sequential Logic: State and Register Updates
    // =========================================================================
    always_ff @(posedge cal_clk_i or negedge ctrl_por_n_i) begin
        if (!ctrl_por_n_i) begin
            state_q                <= ST_IDLE;
            coarse_probe_a_result_q <= Q_CLASS_STABLE_LOW;
            coarse_probe_b_result_q <= Q_CLASS_STABLE_LOW;
            fine_probe_result_q     <= Q_CLASS_STABLE_LOW;
            guard_result_q          <= Q_CLASS_STABLE_LOW;
            hold_result_q           <= Q_CLASS_STABLE_LOW;
            fail_reason_q           <= FAIL_NONE;
            seq_req_q               <= 1'b0;
            seq_cmd_q               <= 2'b00;
            seq_medium_inc_q        <= 1'b0;
            seq_medium_dec_q        <= 1'b0;
            seq_fine_inc_q          <= 1'b0;
            seq_fine_dec_q          <= 1'b0;
            cal_busy_q              <= 1'b0;
            cal_done_q              <= 1'b0;
            cal_fail_q              <= 1'b0;
            lock_valid_q            <= 1'b0;
        end else begin
            state_q                <= state_d;
            coarse_probe_a_result_q <= coarse_probe_a_result_d;
            coarse_probe_b_result_q <= coarse_probe_b_result_d;
            fine_probe_result_q     <= fine_probe_result_d;
            guard_result_q          <= guard_result_d;
            hold_result_q           <= hold_result_d;
            fail_reason_q           <= fail_reason_d;
            seq_req_q               <= seq_req_d;
            seq_cmd_q               <= seq_cmd_d;
            seq_medium_inc_q        <= seq_medium_inc_d;
            seq_medium_dec_q        <= seq_medium_dec_d;
            seq_fine_inc_q          <= seq_fine_inc_d;
            seq_fine_dec_q          <= seq_fine_dec_d;
            cal_busy_q              <= cal_busy_d;
            cal_done_q              <= cal_done_d;
            cal_fail_q              <= cal_fail_d;
            lock_valid_q            <= lock_valid_d;
        end
    end

    // =========================================================================
    // Combinational Logic: Next-State and Output Decode
    // =========================================================================
    always_comb begin
        // Default: hold current state and register values.
        state_d                = state_q;
        coarse_probe_a_result_d = coarse_probe_a_result_q;
        coarse_probe_b_result_d = coarse_probe_b_result_q;
        fine_probe_result_d     = fine_probe_result_q;
        guard_result_d          = guard_result_q;
        hold_result_d           = hold_result_q;
        fail_reason_d           = fail_reason_q;
        seq_req_d               = seq_req_q;
        seq_cmd_d               = seq_cmd_q;
        seq_medium_inc_d        = seq_medium_inc_q;
        seq_medium_dec_d        = seq_medium_dec_q;
        seq_fine_inc_d          = seq_fine_inc_q;
        seq_fine_dec_d          = seq_fine_dec_q;
        cal_busy_d              = cal_busy_q;
        cal_done_d              = cal_done_q;
        cal_fail_d              = cal_fail_q;
        lock_valid_d            = lock_valid_q;

        // =====================================================================
        // State Machine Logic
        // =====================================================================
        case (state_q)
            // -----------------------------------------------------------------
            // IDLE: Wait for cal_start_i to begin calibration.
            // -----------------------------------------------------------------
            ST_IDLE: begin
                cal_busy_d = 1'b0;
                cal_done_d = 1'b0;
                cal_fail_d = 1'b0;
                lock_valid_d = 1'b0;
                fail_reason_d = FAIL_NONE;
                seq_req_d = 1'b0;

                if (cal_start_i) begin
                    state_d = ST_INIT;
                    cal_busy_d = 1'b1;
                end
            end

            // -----------------------------------------------------------------
            // INIT: Initialize configuration to M=0, F=0 and begin coarse search.
            // -----------------------------------------------------------------
            ST_INIT: begin
                // Issue config initialization (handled by cfg registers).
                // Then immediately move to first coarse probe.
                state_d = ST_COARSE_PROBE_A;
                seq_req_d = 1'b1;
                seq_cmd_d = OP_PROBE;
                seq_medium_inc_d = 1'b0;
                seq_medium_dec_d = 1'b0;
                seq_fine_inc_d = 1'b0;
                seq_fine_dec_d = 1'b0;
            end

            // -----------------------------------------------------------------
            // COARSE_PROBE_A: Execute first probe at current M.
            // -----------------------------------------------------------------
            ST_COARSE_PROBE_A: begin
                // Wait for sequencer to accept and complete probe.
                if (seq_busy_i) begin
                    seq_req_d = 1'b0;
                end

                // When probe completes, q_class_i is valid (locked from sample_2).
                if (seq_done_i && seq_probe_done_i && q_class_valid_i) begin
                    // Capture probe A result.
                    coarse_probe_a_result_d = q_class_i;
                    // Issue second probe at same M.
                    state_d = ST_COARSE_PROBE_B;
                    seq_req_d = 1'b1;
                    seq_cmd_d = OP_PROBE;
                end
            end

            // -----------------------------------------------------------------
            // COARSE_PROBE_B: Execute second probe at current M.
            // -----------------------------------------------------------------
            ST_COARSE_PROBE_B: begin
                if (seq_busy_i) begin
                    seq_req_d = 1'b0;
                end

                // When probe completes, q_class_i is valid (locked from sample_2).
                if (seq_done_i && seq_probe_done_i && q_class_valid_i) begin
                    // Capture probe B result.
                    coarse_probe_b_result_d = q_class_i;
                    // Move to evaluation state.
                    state_d = ST_COARSE_EVAL;
                end
            end

            // -----------------------------------------------------------------
            // COARSE_EVAL: Evaluate coarse boundary decision.
            // -----------------------------------------------------------------
            ST_COARSE_EVAL: begin
                // Check if both probes are STABLE_LOW (boundary confirmed).
                if ((coarse_probe_a_result_q == Q_CLASS_STABLE_LOW) &&
                    (coarse_probe_b_result_q == Q_CLASS_STABLE_LOW)) begin
                    // Coarse boundary found. Check if two-step backoff is possible.
                    // Two-step backoff requires current M >= 2 (to reach M-2).
                    if (cfg_medium_too_low_for_backoff_i || cfg_at_min_medium_i) begin
                        // Boundary at M=0 or M=1, cannot backoff 2 steps.
                        state_d = ST_FAIL;
                        fail_reason_d = FAIL_COARSE_BACKOFF_UNDERFLOW;
                        cal_fail_d = 1'b1;
                        cal_busy_d = 1'b0;
                    end else begin
                        // Begin two-step backoff: M_boundary -> M-1.
                        state_d = ST_BACKOFF_1;
                        seq_req_d = 1'b1;
                        seq_cmd_d = OP_CONFIG_UPDATE;
                        seq_medium_dec_d = 1'b1;
                    end
                end else begin
                    // Boundary not confirmed. Check if at max medium range.
                    if (cfg_at_max_medium_i) begin
                        // No boundary found before max medium.
                        state_d = ST_FAIL;
                        fail_reason_d = FAIL_COARSE_RANGE;
                        cal_fail_d = 1'b1;
                        cal_busy_d = 1'b0;
                    end else begin
                        // Continue coarse scan: increment M and probe again.
                        state_d = ST_COARSE_INC;
                        seq_req_d = 1'b1;
                        seq_cmd_d = OP_CONFIG_UPDATE;
                        seq_medium_inc_d = 1'b1;
                    end
                end
            end

            // -----------------------------------------------------------------
            // COARSE_INC: Increment medium and return to probe A.
            // -----------------------------------------------------------------
            ST_COARSE_INC: begin
                if (seq_busy_i) begin
                    seq_req_d = 1'b0;
                    seq_medium_inc_d = 1'b0;
                end

                if (seq_done_i) begin
                    // Config update done. Issue next probe A.
                    state_d = ST_COARSE_PROBE_A;
                    seq_req_d = 1'b1;
                    seq_cmd_d = OP_PROBE;
                end
            end

            // -----------------------------------------------------------------
            // BACKOFF_1: First backoff step (M_boundary -> M-1).
            // -----------------------------------------------------------------
            ST_BACKOFF_1: begin
                if (seq_busy_i) begin
                    seq_req_d = 1'b0;
                    seq_medium_dec_d = 1'b0;
                end

                if (seq_done_i) begin
                    // First backoff done. Issue second backoff immediately (zero probes).
                    state_d = ST_BACKOFF_2;
                    seq_req_d = 1'b1;
                    seq_cmd_d = OP_CONFIG_UPDATE;
                    seq_medium_dec_d = 1'b1;
                end
            end

            // -----------------------------------------------------------------
            // BACKOFF_2: Second backoff step (M-1 -> M-2).
            // -----------------------------------------------------------------
            ST_BACKOFF_2: begin
                if (seq_busy_i) begin
                    seq_req_d = 1'b0;
                    seq_medium_dec_d = 1'b0;
                end

                if (seq_done_i) begin
                    // Two-step backoff complete. Begin fine search at F=0.
                    state_d = ST_FINE_PROBE;
                    seq_req_d = 1'b1;
                    seq_cmd_d = OP_PROBE;
                end
            end

            // -----------------------------------------------------------------
            // FINE_PROBE: Execute probe at current fine code.
            // -----------------------------------------------------------------
            ST_FINE_PROBE: begin
                if (seq_busy_i) begin
                    seq_req_d = 1'b0;
                end

                // When probe completes, q_class_i is valid (locked from sample_2).
                if (seq_done_i && seq_probe_done_i && q_class_valid_i) begin
                    // Capture fine probe result.
                    fine_probe_result_d = q_class_i;
                    // Move to evaluation.
                    state_d = ST_FINE_EVAL;
                end
            end

            // -----------------------------------------------------------------
            // FINE_EVAL: Evaluate fine boundary decision.
            // -----------------------------------------------------------------
            ST_FINE_EVAL: begin
                // STABLE_HIGH continues scan; STABLE_LOW or AMBIGUOUS is boundary.
                if (fine_probe_result_q == Q_CLASS_STABLE_HIGH) begin
                    // Continue fine scan. Check if at max fine range.
                    if (cfg_at_max_fine_i) begin
                        // No boundary found before max fine.
                        state_d = ST_FAIL;
                        fail_reason_d = FAIL_FINE_RANGE;
                        cal_fail_d = 1'b1;
                        cal_busy_d = 1'b0;
                    end else begin
                        // Increment fine and probe again.
                        state_d = ST_FINE_INC;
                        seq_req_d = 1'b1;
                        seq_cmd_d = OP_CONFIG_UPDATE;
                        seq_fine_inc_d = 1'b1;
                    end
                end else begin
                    // Fine boundary found (STABLE_LOW or AMBIGUOUS).
                    // Check if guard increment is possible.
                    if (cfg_at_max_fine_i) begin
                        // At max fine, no room for guard.
                        state_d = ST_FAIL;
                        fail_reason_d = FAIL_GUARD_RANGE;
                        cal_fail_d = 1'b1;
                        cal_busy_d = 1'b0;
                    end else begin
                        // Increment to guard position (F_boundary + 1).
                        state_d = ST_GUARD_INC;
                        seq_req_d = 1'b1;
                        seq_cmd_d = OP_CONFIG_UPDATE;
                        seq_fine_inc_d = 1'b1;
                    end
                end
            end

            // -----------------------------------------------------------------
            // FINE_INC: Increment fine and return to probe.
            // -----------------------------------------------------------------
            ST_FINE_INC: begin
                if (seq_busy_i) begin
                    seq_req_d = 1'b0;
                    seq_fine_inc_d = 1'b0;
                end

                if (seq_done_i) begin
                    // Config update done. Issue next fine probe.
                    state_d = ST_FINE_PROBE;
                    seq_req_d = 1'b1;
                    seq_cmd_d = OP_PROBE;
                end
            end

            // -----------------------------------------------------------------
            // GUARD_INC: Increment to guard position (F_boundary + 1).
            // -----------------------------------------------------------------
            ST_GUARD_INC: begin
                if (seq_busy_i) begin
                    seq_req_d = 1'b0;
                    seq_fine_inc_d = 1'b0;
                end

                if (seq_done_i) begin
                    // Guard position reached. Issue guard probe.
                    state_d = ST_GUARD_PROBE;
                    seq_req_d = 1'b1;
                    seq_cmd_d = OP_PROBE;
                end
            end

            // -----------------------------------------------------------------
            // GUARD_PROBE: Execute guard probe at F_boundary + 1.
            // -----------------------------------------------------------------
            ST_GUARD_PROBE: begin
                if (seq_busy_i) begin
                    seq_req_d = 1'b0;
                end

                // When probe completes, q_class_i is valid (locked from sample_2).
                if (seq_done_i && seq_probe_done_i && q_class_valid_i) begin
                    // Capture guard result.
                    guard_result_d = q_class_i;

                    // Guard must be STABLE_LOW.
                    if (q_class_i == Q_CLASS_STABLE_LOW) begin
                        // Guard passed. Issue independent hold probe.
                        state_d = ST_HOLD_PROBE;
                        seq_req_d = 1'b1;
                        seq_cmd_d = OP_PROBE;
                    end else begin
                        // Guard not low (STABLE_HIGH or AMBIGUOUS).
                        state_d = ST_FAIL;
                        fail_reason_d = FAIL_GUARD_NOT_LOW;
                        cal_fail_d = 1'b1;
                        cal_busy_d = 1'b0;
                    end
                end
            end

            // -----------------------------------------------------------------
            // HOLD_PROBE: Execute hold probe at same position as guard.
            // -----------------------------------------------------------------
            ST_HOLD_PROBE: begin
                if (seq_busy_i) begin
                    seq_req_d = 1'b0;
                end

                // When probe completes, q_class_i is valid (locked from sample_2).
                if (seq_done_i && seq_probe_done_i && q_class_valid_i) begin
                    // Capture hold result.
                    hold_result_d = q_class_i;

                    // Hold must be STABLE_LOW.
                    if (q_class_i == Q_CLASS_STABLE_LOW) begin
                        // Hold passed. Calibration successful.
                        state_d = ST_LOCKED;
                        cal_busy_d = 1'b0;
                        cal_done_d = 1'b1;
                        lock_valid_d = 1'b1;
                    end else begin
                        // Hold not low (STABLE_HIGH or AMBIGUOUS).
                        state_d = ST_FAIL;
                        fail_reason_d = FAIL_HOLD_NOT_LOW;
                        cal_fail_d = 1'b1;
                        cal_busy_d = 1'b0;
                    end
                end
            end

            // -----------------------------------------------------------------
            // LOCKED: Calibration completed successfully. Remain here until POR.
            // -----------------------------------------------------------------
            ST_LOCKED: begin
                // All outputs frozen. Do nothing until POR.
                seq_req_d = 1'b0;
            end

            // -----------------------------------------------------------------
            // FAIL: Calibration failed. Remain here until POR.
            // -----------------------------------------------------------------
            ST_FAIL: begin
                // Failure reason and outputs frozen. Do nothing until POR.
                seq_req_d = 1'b0;
            end

            // -----------------------------------------------------------------
            // Default case (should never reach here).
            // -----------------------------------------------------------------
            default: begin
                state_d = ST_FAIL;
                fail_reason_d = FAIL_COARSE_RANGE;  // Arbitrary failure code.
                cal_fail_d = 1'b1;
                cal_busy_d = 1'b0;
            end
        endcase
    end

    // =========================================================================
    // Output Assignments
    // =========================================================================
    assign seq_req_o        = seq_req_q;
    assign seq_cmd_o        = seq_cmd_q;
    assign seq_medium_inc_o = seq_medium_inc_q;
    assign seq_medium_dec_o = seq_medium_dec_q;
    assign seq_fine_inc_o   = seq_fine_inc_q;
    assign seq_fine_dec_o   = seq_fine_dec_q;
    assign cal_busy_o       = cal_busy_q;
    assign cal_done_o       = cal_done_q;
    assign cal_fail_o       = cal_fail_q;
    assign lock_valid_o     = lock_valid_q;
    assign fail_reason_o    = fail_reason_q;
    assign fsm_state_o      = state_q;

endmodule

`default_nettype wire
