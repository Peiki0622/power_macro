// ============================================================================
// FTC Calibration Controller Top-Level Module
// ============================================================================
// Top-level integration of all calibration controller blocks:
//   - Configuration thermometer registers (medium/fine)
//   - Operation sequencer (sensor control timing and Q sampling)
//   - High-level calibration FSM (algorithmic orchestration)
//
// This module autonomously calibrates the FTC sensor by:
//   1. Coarse search: increment medium until both probes are STABLE_LOW
//   2. Two-step backoff: M_boundary → M-1 → M-2 (zero probes between)
//   3. Fine search: increment fine until first STABLE_LOW/AMBIGUOUS
//   4. Guard/hold verification: both must be STABLE_LOW to lock
//
// Baseline: Phase 0-4 acceptance (dynamic startup protocol + FSM)
// Phase: 5 - Top-level integration
// Author: Autonomous calibration controller implementation
// Date: 2026-08-20
// ============================================================================

module ftc_cal_controller_top
    import ftc_cal_pkg::*;
(
    // =========================================================================
    // Clock and Reset
    // =========================================================================
    // Calibration clock - 1 GHz (1 ns period) per Phase 1 timing contract.
    input  logic        cal_clk,
    // Controller power-on reset, active low. Resets all internal state.
    input  logic        ctrl_por_n,

    // =========================================================================
    // Control Interface
    // =========================================================================
    // Start calibration pulse (single cycle). Must be asserted after POR
    // deassertion when ready to begin autonomous calibration sequence.
    input  logic        cal_start,

    // =========================================================================
    // Sensor Feedback
    // =========================================================================
    // Final Q output from FTC sensor capture DFF. Sampled twice per probe
    // to classify as STABLE_LOW (0,0), STABLE_HIGH (1,1), or AMBIGUOUS.
    input  logic        q_final,

    // =========================================================================
    // Sensor Control Outputs
    // =========================================================================
    // Sensor capture DFF asynchronous reset (active high).
    // Asserted during config updates and between probes for reset.
    output logic        sense_dff_reset,

    // Sensor sampling clock. Generated as registered pulse (one rising edge
    // per probe). Must never glitch during config updates.
    output logic        sense_s_clk,

    // Medium delay thermometer code [15:0], one-hot incrementing from LSB.
    // Controls path-selection muxes. Changes only when sense_dff_reset high
    // and sense_s_clk low.
    output logic [15:0] medium_therm,

    // Fine delay thermometer code [9:0], one-hot incrementing from LSB.
    // Controls standard-cell load stages. Changes only when sense_dff_reset
    // high and sense_s_clk low.
    output logic [9:0]  fine_therm,

    // =========================================================================
    // Status Outputs
    // =========================================================================
    // Calibration busy flag. Asserted when FSM is not IDLE.
    output logic        cal_busy,

    // Calibration done flag. Asserted when lock succeeds (guard and hold
    // both STABLE_LOW). Remains high until next POR.
    output logic        cal_done,

    // Calibration failure flag. Asserted when any failure mode detected
    // (range exhaustion, backoff underflow, guard/hold not low). Remains
    // high until next POR.
    output logic        cal_fail,

    // Lock valid flag. Asserted with cal_done to indicate M/F outputs are
    // frozen at calibrated values.
    output logic        lock_valid,

    // =========================================================================
    // Debug Outputs
    // =========================================================================
    // Medium binary code [4:0] for monitoring (0..15). Derived from
    // thermometer register internal state. Width matches MEDIUM_CODE_WIDTH=5.
    output logic [4:0]  medium_code,

    // Fine binary code [3:0] for monitoring (0..9, 10..15 invalid).
    // Derived from thermometer register internal state. Width matches FINE_CODE_WIDTH=4.
    output logic [3:0]  fine_code,

    // Failure reason encoding (stable after cal_fail assertion):
    //   3'b000: No failure
    //   3'b001: COARSE_RANGE_FAIL
    //   3'b010: COARSE_BACKOFF_UNDERFLOW
    //   3'b011: FINE_RANGE_FAIL
    //   3'b100: GUARD_RANGE_FAIL
    //   3'b101: GUARD_NOT_LOW
    //   3'b110: HOLD_NOT_LOW
    output logic [2:0]  fail_reason,

    // FSM state [4:0] for debug visibility. 5 bits to encode 12 states.
    output logic [4:0]  fsm_state
);

    // =========================================================================
    // Internal Signals - FSM to Sequencer
    // =========================================================================
    logic       seq_req;          // FSM requests operation
    logic [1:0] seq_cmd;          // Operation command (CONFIG_UPDATE or PROBE)
    logic       seq_busy;         // Sequencer operation in progress
    logic       seq_done;         // Sequencer operation completed
    logic       seq_probe_done;   // Probe-specific done (with Q classification)

    // =========================================================================
    // Internal Signals - FSM Configuration Intent (to Sequencer)
    // =========================================================================
    logic       fsm_medium_inc;   // FSM requests medium increment
    logic       fsm_medium_dec;   // FSM requests medium decrement
    logic       fsm_fine_inc;     // FSM requests fine increment
    logic       fsm_fine_dec;     // FSM requests fine decrement

    // =========================================================================
    // Internal Signals - Sequencer to Configuration Registers
    // =========================================================================
    logic       seq_medium_inc;   // Sequencer drives medium increment (timed)
    logic       seq_medium_dec;   // Sequencer drives medium decrement (timed)
    logic       seq_fine_inc;     // Sequencer drives fine increment (timed)
    logic       seq_fine_dec;     // Sequencer drives fine decrement (timed)

    // =========================================================================
    // Internal Signals - Configuration Control
    // =========================================================================
    logic       cfg_locked;       // Lock configuration (freeze outputs)
    logic       cfg_init;         // Initialize to all zeros

    // =========================================================================
    // Internal Signals - Configuration Register Status
    // =========================================================================
    logic       cfg_at_max_medium;  // Medium at maximum (15)
    logic       cfg_at_min_medium;  // Medium at minimum (0)
    logic       cfg_at_max_fine;    // Fine at maximum (9)
    logic       cfg_medium_too_low; // Medium < 2 (insufficient backoff room)

    // =========================================================================
    // Internal Signals - Q Classification
    // =========================================================================
    logic [1:0] q_class;          // Q classification result
    logic       q_class_valid;    // Q classification valid (after probe)

    // =========================================================================
    // Module Instantiation - Configuration Thermometer Registers
    // =========================================================================
    ftc_cfg_therm_regs u_cfg_regs (
        .clk_i(cal_clk),
        .por_n_i(ctrl_por_n),
        .medium_inc_i(seq_medium_inc),
        .medium_dec_i(seq_medium_dec),
        .fine_inc_i(seq_fine_inc),
        .fine_dec_i(seq_fine_dec),
        .init_i(cfg_init),
        .lock_i(cfg_locked),
        .medium_therm_o(medium_therm),
        .fine_therm_o(fine_therm),
        .medium_code_o(medium_code),
        .fine_code_o(fine_code),
        .medium_at_max_o(cfg_at_max_medium),
        .medium_at_min_o(cfg_at_min_medium),
        .fine_at_max_o(cfg_at_max_fine),
        .fine_at_min_o(),  // Not used
        .cfg_locked_o(),   // Not used (lock driven by FSM)
        .medium_too_low_for_backoff_o(cfg_medium_too_low)
    );

    // =========================================================================
    // Module Instantiation - Operation Sequencer
    // =========================================================================
    // Handles cycle-accurate timing for config updates and probes.
    // Instantiates Q sampler internally.
    ftc_operation_sequencer u_sequencer (
        .cal_clk_i(cal_clk),
        .ctrl_por_n_i(ctrl_por_n),
        .req_i(seq_req),
        .cmd_i(seq_cmd),
        .medium_inc_i(fsm_medium_inc),
        .medium_dec_i(fsm_medium_dec),
        .fine_inc_i(fsm_fine_inc),
        .fine_dec_i(fsm_fine_dec),
        .q_final_i(q_final),
        .sense_dff_reset_o(sense_dff_reset),
        .sense_s_clk_o(sense_s_clk),
        .cfg_medium_inc_o(seq_medium_inc),
        .cfg_medium_dec_o(seq_medium_dec),
        .cfg_fine_inc_o(seq_fine_inc),
        .cfg_fine_dec_o(seq_fine_dec),
        .busy_o(seq_busy),
        .done_o(seq_done),
        .probe_done_o(seq_probe_done),
        .q_class_o(q_class),
        .q_class_valid_o(q_class_valid),
        .q_sample_1_event_o(),  // Not used at top level
        .q_sample_2_event_o()   // Not used at top level
    );

    // =========================================================================
    // Module Instantiation - High-Level Calibration FSM
    // =========================================================================
    // Implements the algorithmic sequencing (coarse, backoff, fine, guard,
    // hold). Does not handle cycle-level timing (delegated to sequencer).
    ftc_cal_fsm u_fsm (
        .cal_clk_i(cal_clk),
        .ctrl_por_n_i(ctrl_por_n),
        .cal_start_i(cal_start),
        .seq_busy_i(seq_busy),
        .seq_done_i(seq_done),
        .seq_probe_done_i(seq_probe_done),
        .seq_req_o(seq_req),
        .seq_cmd_o(seq_cmd),
        .seq_medium_inc_o(fsm_medium_inc),
        .seq_medium_dec_o(fsm_medium_dec),
        .seq_fine_inc_o(fsm_fine_inc),
        .seq_fine_dec_o(fsm_fine_dec),
        .q_class_i(q_class),
        .q_class_valid_i(q_class_valid),
        .cfg_at_max_medium_i(cfg_at_max_medium),
        .cfg_at_min_medium_i(cfg_at_min_medium),
        .cfg_at_max_fine_i(cfg_at_max_fine),
        .cfg_medium_too_low_for_backoff_i(cfg_medium_too_low),
        .cal_busy_o(cal_busy),
        .cal_done_o(cal_done),
        .cal_fail_o(cal_fail),
        .lock_valid_o(lock_valid),
        .fail_reason_o(fail_reason),
        .fsm_state_o(fsm_state)
    );

    // =========================================================================
    // FSM Drives Configuration Lock
    // =========================================================================
    // Lock signal derived from FSM reaching LOCKED state.
    assign cfg_locked = lock_valid;

    // Init signal driven by FSM during initialization state.
    assign cfg_init = (fsm_state == 4'd1);  // INIT state

endmodule
