// ============================================================================
// H0 ownership handoff safety assertions
// ============================================================================
// This file is verification-only.  It binds to ftc_sensor_owner_handoff and
// checks the externally visible H0 contract at the 400 MHz cal_clk boundary.
// It does not add logic to the synthesizable RTL and does not instantiate the
// frozen calibration controller, XA, or the transistor-level sensor.
// ============================================================================
`timescale 1ns/1ps
`default_nettype none

module ftc_sensor_owner_handoff_sva (
    // The assertion clock/reset ports are connected to the handoff instance.
    input logic        cal_clk_i,
    input logic        ctrl_por_n_i,

    // Inputs needed to prove failure containment and ready-contract checking.
    input logic        cal_fail_i,
    input logic        det_takeover_ready_i,
    input logic        det_sense_dff_reset_i,
    input logic        det_sense_s_clk_i,
    input logic [15:0] det_medium_therm_i,
    input logic [9:0]  det_fine_therm_i,

    // H0 state, snapshot, and sensor-control outputs under assertion.
    input logic [2:0]  handoff_state_o,
    input logic        cal_cfg_valid_o,
    input logic        det_owner_valid_o,
    input logic        handoff_blocked_o,
    input logic        handoff_protocol_error_o,
    input logic        sense_dff_reset_o,
    input logic        sense_s_clk_o,
    input logic [15:0] medium_therm_o,
    input logic [9:0]  fine_therm_o,
    input logic [15:0] cal_medium_therm_snapshot_o,
    input logic [9:0]  cal_fine_therm_snapshot_o
);

    localparam logic [2:0] H_CAL_OWNED   = 3'd0;
    localparam logic [2:0] H_WAIT_DET    = 3'd1;
    localparam logic [2:0] H_SWITCH_SAFE = 3'd2;
    localparam logic [2:0] H_DET_OWNED   = 3'd3;
    localparam logic [2:0] H_BLOCKED     = 3'd4;

    default clocking h0_clk @(posedge cal_clk_i); endclocking

    // Ownership is monotonic within one POR session: once DET is published it
    // cannot fall back to CAL, and DET validity is equivalent to H_DET_OWNED.
    ap_det_owner_state: assert property (
        disable iff (!ctrl_por_n_i)
        det_owner_valid_o == (handoff_state_o == H_DET_OWNED)
    );
    ap_det_owner_sticky: assert property (
        disable iff (!ctrl_por_n_i)
        det_owner_valid_o |=> det_owner_valid_o
    );

    // A captured calibration baseline is write-once until POR.  Both
    // thermometer buses must remain stable after validity is advertised.
    ap_snapshot_stable: assert property (
        disable iff (!ctrl_por_n_i)
        cal_cfg_valid_o |=> cal_cfg_valid_o &&
            $stable(cal_medium_therm_snapshot_o) &&
            $stable(cal_fine_therm_snapshot_o)
    );

    // Calibration failure is a permanent safety stop and cannot publish DET.
    ap_cal_fail_blocks: assert property (
        disable iff (!ctrl_por_n_i)
        cal_fail_i |=> handoff_blocked_o && !det_owner_valid_o
    );

    // A malformed ready is accepted only when every detector precharge value
    // exactly equals the snapshot and reset/S_CLK are at their safe levels.
    // If ready is asserted with any mismatch, the next state is BLOCKED and
    // the sticky protocol error is visible to downstream control logic.
    ap_ready_requires_exact_precharge: assert property (
        disable iff (!ctrl_por_n_i)
        (handoff_state_o == H_WAIT_DET && det_takeover_ready_i &&
         ((det_medium_therm_i != cal_medium_therm_snapshot_o) ||
          (det_fine_therm_i != cal_fine_therm_snapshot_o) ||
          !det_sense_dff_reset_i || det_sense_s_clk_i))
        |=> handoff_blocked_o && handoff_protocol_error_o && !det_owner_valid_o
    );

    // Both the explicit SAFE state and the blocked state force a precharged
    // sensor: reset is asserted, S_CLK is low, and no detector ownership is
    // externally visible.  This is the sampled form of the no-pulse window.
    ap_safe_window: assert property (
        disable iff (!ctrl_por_n_i)
        (handoff_state_o == H_SWITCH_SAFE || handoff_state_o == H_BLOCKED)
        |-> sense_dff_reset_o && !sense_s_clk_o && !det_owner_valid_o
    );

    // The published DET state has the detector's exact precharge snapshot for
    // the first cycle, preventing a mapped mux delay skew from creating a
    // functional bus transition at the ownership boundary.
    ap_det_entry_precharge: assert property (
        disable iff (!ctrl_por_n_i)
        $rose(det_owner_valid_o) |-> sense_dff_reset_o && !sense_s_clk_o &&
            medium_therm_o == $past(cal_medium_therm_snapshot_o) &&
            fine_therm_o == $past(cal_fine_therm_snapshot_o)
    );

    // POR is the only legal way to clear ownership and sticky diagnostics.
    ap_por_clears_handoff: assert property (
        !ctrl_por_n_i |=> handoff_state_o == H_CAL_OWNED &&
            !cal_cfg_valid_o && !det_owner_valid_o && !handoff_blocked_o &&
            !handoff_protocol_error_o
    );

endmodule

// Bind the assertions to every H0 handoff instance.  All connected names are
// existing module ports, so this bind has no effect on synthesized RTL.
bind ftc_sensor_owner_handoff ftc_sensor_owner_handoff_sva h0_contract_sva (
    .cal_clk_i(cal_clk_i),
    .ctrl_por_n_i(ctrl_por_n_i),
    .cal_fail_i(cal_fail_i),
    .det_takeover_ready_i(det_takeover_ready_i),
    .det_sense_dff_reset_i(det_sense_dff_reset_i),
    .det_sense_s_clk_i(det_sense_s_clk_i),
    .det_medium_therm_i(det_medium_therm_i),
    .det_fine_therm_i(det_fine_therm_i),
    .handoff_state_o(handoff_state_o),
    .cal_cfg_valid_o(cal_cfg_valid_o),
    .det_owner_valid_o(det_owner_valid_o),
    .handoff_blocked_o(handoff_blocked_o),
    .handoff_protocol_error_o(handoff_protocol_error_o),
    .sense_dff_reset_o(sense_dff_reset_o),
    .sense_s_clk_o(sense_s_clk_o),
    .medium_therm_o(medium_therm_o),
    .fine_therm_o(fine_therm_o),
    .cal_medium_therm_snapshot_o(cal_medium_therm_snapshot_o),
    .cal_fine_therm_snapshot_o(cal_fine_therm_snapshot_o)
);

`default_nettype wire
