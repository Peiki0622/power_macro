// ============================================================================
// FTC calibration plus calibration-to-detection handoff top level
// ============================================================================
// This wrapper preserves ftc_cal_controller_top as an unchanged child.  Its
// 28 frozen sensor-control outputs are first named cal_* and then pass through
// ftc_sensor_owner_handoff before reaching the actual FTC_SENSOR integration
// boundary.  The wrapper adds no detector algorithm, margin arithmetic, or
// second Q path; it only exposes future detector controls and the immutable
// calibration snapshot required by the next project phase.
// ============================================================================
`timescale 1ns/1ps
`default_nettype none

module ftc_cal_detect_handoff_top (
    // ------------------------------------------------------------------------
    // Trusted controller clock, POR, and calibration start
    // ------------------------------------------------------------------------
    // cal_clk_i is the active 400 MHz startup-calibration clock.  The wrapper
    // does not gate or divide it.  ctrl_por_n_i resets both the frozen child
    // controller and the one-way ownership handoff.
    input  logic        cal_clk_i,
    input  logic        ctrl_por_n_i,
    input  logic        cal_start_i,

    // ------------------------------------------------------------------------
    // Shared latched sensor return
    // ------------------------------------------------------------------------
    // q_final_i remains a direct sensor capture-DFF state return to the frozen
    // calibration controller.  It is intentionally not an ownership-muxed
    // detector input and is preserved for the future detector as a separate
    // downstream integration concern.
    input  logic        q_final_i,

    // ------------------------------------------------------------------------
    // Future detector precharge/control inputs
    // ------------------------------------------------------------------------
    // det_takeover_ready_i must be synchronized to cal_clk_i by the future
    // detector integration.  The four detector sensor controls must match the
    // published snapshot and safe levels before ready is asserted.
    input  logic        det_takeover_ready_i,
    input  logic        det_sense_dff_reset_i,
    input  logic        det_sense_s_clk_i,
    input  logic [15:0] det_medium_therm_i,
    input  logic [9:0]  det_fine_therm_i,

    // ------------------------------------------------------------------------
    // Actual FTC_SENSOR controls after ownership selection
    // ------------------------------------------------------------------------
    // These outputs are the sole sensor-control ports of the new wrapper.  An
    // ideal power-aware CTRL-to-SENSE boundary may be attached after them.
    output logic        sense_dff_reset_o,
    output logic        sense_s_clk_o,
    output logic [15:0] medium_therm_o,
    output logic [9:0]  fine_therm_o,

    // ------------------------------------------------------------------------
    // Frozen calibration controller status/debug outputs
    // ------------------------------------------------------------------------
    // These signals retain the existing startup-calibration observability and
    // are not modified by the handoff.  Widths follow the frozen top-level
    // module exactly, including the 3-bit failure reason port.
    output logic        cal_busy_o,
    output logic        cal_done_o,
    output logic        cal_fail_o,
    output logic        lock_valid_o,
    output logic [4:0]  medium_code_o,
    output logic [3:0]  fine_code_o,
    output logic [2:0]  fail_reason_o,
    output logic [4:0]  fsm_state_o,
    output logic        q_sample_1_event_o,
    output logic        q_sample_2_event_o,
    output logic        config_update_event_o,
    output logic        probe_start_event_o,

    // ------------------------------------------------------------------------
    // H0 snapshot and ownership outputs
    // ------------------------------------------------------------------------
    // These outputs are the only H0 contract consumed by the next detection
    // stage.  Snapshot fields are immutable until POR; ownership/error fields
    // are registered state views from ftc_sensor_owner_handoff.
    output logic        cal_cfg_valid_o,
    output logic [4:0]  cal_medium_code_snapshot_o,
    output logic [3:0]  cal_fine_code_snapshot_o,
    output logic [15:0] cal_medium_therm_snapshot_o,
    output logic [9:0]  cal_fine_therm_snapshot_o,
    output logic        det_prepare_o,
    output logic        det_owner_valid_o,
    output logic        handoff_blocked_o,
    output logic        handoff_protocol_error_o,
    output logic [2:0]  handoff_state_o
);

    // The frozen child controller retains ownership of q_final_i and produces
    // the calibration-side controls.  No source line of that child is
    // modified for H0; all newly introduced behavior is below this instance.
    logic        cal_sense_dff_reset;
    logic        cal_sense_s_clk;
    logic [15:0] cal_medium_therm;
    logic [9:0]  cal_fine_therm;

    ftc_cal_controller_top u_cal_controller (
        .cal_clk(cal_clk_i),
        .ctrl_por_n(ctrl_por_n_i),
        .cal_start(cal_start_i),
        .q_final(q_final_i),
        .sense_dff_reset(cal_sense_dff_reset),
        .sense_s_clk(cal_sense_s_clk),
        .medium_therm(cal_medium_therm),
        .fine_therm(cal_fine_therm),
        .cal_busy(cal_busy_o),
        .cal_done(cal_done_o),
        .cal_fail(cal_fail_o),
        .lock_valid(lock_valid_o),
        .medium_code(medium_code_o),
        .fine_code(fine_code_o),
        .fail_reason(fail_reason_o),
        .fsm_state(fsm_state_o),
        .q_sample_1_event(q_sample_1_event_o),
        .q_sample_2_event(q_sample_2_event_o),
        .config_update_event(config_update_event_o),
        .probe_start_event(probe_start_event_o)
    );

    // The handoff module is the sole owner of the actual sensor-control mux.
    // q_final_i is intentionally absent from this instance, proving that the
    // H0 ownership layer cannot alter the frozen Q_FINAL return semantics.
    ftc_sensor_owner_handoff u_owner_handoff (
        .cal_clk_i(cal_clk_i),
        .ctrl_por_n_i(ctrl_por_n_i),
        .cal_busy_i(cal_busy_o),
        .cal_done_i(cal_done_o),
        .cal_fail_i(cal_fail_o),
        .lock_valid_i(lock_valid_o),
        .cal_sense_dff_reset_i(cal_sense_dff_reset),
        .cal_sense_s_clk_i(cal_sense_s_clk),
        .cal_medium_therm_i(cal_medium_therm),
        .cal_fine_therm_i(cal_fine_therm),
        .cal_medium_code_i(medium_code_o),
        .cal_fine_code_i(fine_code_o),
        .det_takeover_ready_i(det_takeover_ready_i),
        .det_sense_dff_reset_i(det_sense_dff_reset_i),
        .det_sense_s_clk_i(det_sense_s_clk_i),
        .det_medium_therm_i(det_medium_therm_i),
        .det_fine_therm_i(det_fine_therm_i),
        .sense_dff_reset_o(sense_dff_reset_o),
        .sense_s_clk_o(sense_s_clk_o),
        .medium_therm_o(medium_therm_o),
        .fine_therm_o(fine_therm_o),
        .cal_cfg_valid_o(cal_cfg_valid_o),
        .cal_medium_code_snapshot_o(cal_medium_code_snapshot_o),
        .cal_fine_code_snapshot_o(cal_fine_code_snapshot_o),
        .cal_medium_therm_snapshot_o(cal_medium_therm_snapshot_o),
        .cal_fine_therm_snapshot_o(cal_fine_therm_snapshot_o),
        .det_prepare_o(det_prepare_o),
        .det_owner_valid_o(det_owner_valid_o),
        .handoff_blocked_o(handoff_blocked_o),
        .handoff_protocol_error_o(handoff_protocol_error_o),
        .handoff_state_o(handoff_state_o)
    );

endmodule

`default_nettype wire
