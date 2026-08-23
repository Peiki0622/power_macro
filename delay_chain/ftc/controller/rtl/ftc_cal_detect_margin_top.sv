// ============================================================================
// FTC M1 calibration-to-detection-margin stage top
// ============================================================================
// This wrapper composes the frozen H0 calibration/handoff top with the new M1
// detector-side margin manager.  H0 remains an unchanged child and remains
// the sole mux owner of the physical FTC_SENSOR controls.  M1 supplies only
// the precharged detector inputs H0 already published for a future controller.
//
// M1 intentionally stops after one safe margin configuration.  It does not
// generate a runtime S_CLK waveform, release the sensor reset, sample Q, or
// implement an alarm.  Those functions are reserved for the later T0/D0 work.
// ============================================================================
`timescale 1ns/1ps
`default_nettype none

module ftc_cal_detect_margin_top (
    // ------------------------------------------------------------------------
    // Frozen calibration and shared sensor-return interface
    // ------------------------------------------------------------------------
    // cal_clk_i is the unchanged 400 MHz controller clock and ctrl_por_n_i is
    // the common active-low POR.  q_final_i remains H0's direct sensor return;
    // M1 neither muxes nor interprets this signal.
    input  logic        cal_clk_i,
    input  logic        ctrl_por_n_i,
    input  logic        cal_start_i,
    input  logic        q_final_i,

    // ------------------------------------------------------------------------
    // One-shot M1 margin-selection interface
    // ------------------------------------------------------------------------
    // Valid is a one-cal_clk_i-cycle request issued only after H0 exposes
    // det_prepare_o.  No asynchronous request is accepted at this stage.
    input  logic [1:0]  margin_sel_i,
    input  logic        margin_select_valid_i,

    // ------------------------------------------------------------------------
    // Sole physical FTC_SENSOR controls, emitted by the frozen H0 mux
    // ------------------------------------------------------------------------
    output logic        sense_dff_reset_o,
    output logic        sense_s_clk_o,
    output logic [15:0] medium_therm_o,
    output logic [9:0]  fine_therm_o,

    // ------------------------------------------------------------------------
    // Preserved calibration observability from the frozen H0 child
    // ------------------------------------------------------------------------
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
    // Preserved immutable H0 snapshot and handoff observability
    // ------------------------------------------------------------------------
    output logic        cal_cfg_valid_o,
    output logic [4:0]  cal_medium_code_snapshot_o,
    output logic [3:0]  cal_fine_code_snapshot_o,
    output logic [15:0] cal_medium_therm_snapshot_o,
    output logic [9:0]  cal_fine_therm_snapshot_o,
    output logic        det_prepare_o,
    output logic        det_owner_valid_o,
    output logic        handoff_blocked_o,
    output logic        handoff_protocol_error_o,
    output logic [2:0]  handoff_state_o,

    // ------------------------------------------------------------------------
    // M1 configuration status for later T0/D0 consumers
    // ------------------------------------------------------------------------
    output logic        margin_cfg_valid_o,
    output logic        mapping_supported_o,
    output logic        trip_qualified_o,
    output logic        margin_protocol_error_o,
    output logic [4:0]  m_det_o,
    output logic [3:0]  f_det_o,
    output logic [1:0]  margin_level_o
);

    // These are the only new signals connected to frozen H0.  They enter the
    // detector-input side exactly at the existing published port boundary;
    // they are never inserted into H0's CAL output or critical S_CLK path.
    logic        det_takeover_ready;
    logic        det_sense_dff_reset;
    logic        det_sense_s_clk;
    logic [15:0] det_medium_therm;
    logic [9:0]  det_fine_therm;

    ftc_detection_margin_manager u_margin_manager (
        .cal_clk_i                    (cal_clk_i),
        .ctrl_por_n_i                 (ctrl_por_n_i),
        .cal_cfg_valid_i              (cal_cfg_valid_o),
        .cal_medium_code_snapshot_i   (cal_medium_code_snapshot_o),
        .cal_fine_code_snapshot_i     (cal_fine_code_snapshot_o),
        .cal_medium_therm_snapshot_i  (cal_medium_therm_snapshot_o),
        .cal_fine_therm_snapshot_i    (cal_fine_therm_snapshot_o),
        .det_prepare_i                (det_prepare_o),
        .det_owner_valid_i            (det_owner_valid_o),
        .handoff_blocked_i            (handoff_blocked_o),
        .margin_sel_i                 (margin_sel_i),
        .margin_select_valid_i        (margin_select_valid_i),
        .det_takeover_ready_o         (det_takeover_ready),
        .det_sense_dff_reset_o        (det_sense_dff_reset),
        .det_sense_s_clk_o            (det_sense_s_clk),
        .det_medium_therm_o           (det_medium_therm),
        .det_fine_therm_o             (det_fine_therm),
        .margin_cfg_valid_o           (margin_cfg_valid_o),
        .mapping_supported_o          (mapping_supported_o),
        .trip_qualified_o             (trip_qualified_o),
        .margin_protocol_error_o      (margin_protocol_error_o),
        .m_det_o                      (m_det_o),
        .f_det_o                      (f_det_o),
        .margin_level_o               (margin_level_o)
    );

    // Frozen H0 implementation: this instance is not modified by M1.  H0
    // validates snapshot equality before handoff and owns the sole physical
    // control mux, preserving its safe-switch and CAL critical-path evidence.
    ftc_cal_detect_handoff_top u_frozen_h0 (
        .cal_clk_i                    (cal_clk_i),
        .ctrl_por_n_i                 (ctrl_por_n_i),
        .cal_start_i                  (cal_start_i),
        .q_final_i                    (q_final_i),
        .det_takeover_ready_i         (det_takeover_ready),
        .det_sense_dff_reset_i        (det_sense_dff_reset),
        .det_sense_s_clk_i            (det_sense_s_clk),
        .det_medium_therm_i           (det_medium_therm),
        .det_fine_therm_i             (det_fine_therm),
        .sense_dff_reset_o            (sense_dff_reset_o),
        .sense_s_clk_o                (sense_s_clk_o),
        .medium_therm_o               (medium_therm_o),
        .fine_therm_o                 (fine_therm_o),
        .cal_busy_o                   (cal_busy_o),
        .cal_done_o                   (cal_done_o),
        .cal_fail_o                   (cal_fail_o),
        .lock_valid_o                 (lock_valid_o),
        .medium_code_o                (medium_code_o),
        .fine_code_o                  (fine_code_o),
        .fail_reason_o                (fail_reason_o),
        .fsm_state_o                  (fsm_state_o),
        .q_sample_1_event_o           (q_sample_1_event_o),
        .q_sample_2_event_o           (q_sample_2_event_o),
        .config_update_event_o        (config_update_event_o),
        .probe_start_event_o          (probe_start_event_o),
        .cal_cfg_valid_o              (cal_cfg_valid_o),
        .cal_medium_code_snapshot_o   (cal_medium_code_snapshot_o),
        .cal_fine_code_snapshot_o     (cal_fine_code_snapshot_o),
        .cal_medium_therm_snapshot_o  (cal_medium_therm_snapshot_o),
        .cal_fine_therm_snapshot_o    (cal_fine_therm_snapshot_o),
        .det_prepare_o                (det_prepare_o),
        .det_owner_valid_o            (det_owner_valid_o),
        .handoff_blocked_o            (handoff_blocked_o),
        .handoff_protocol_error_o     (handoff_protocol_error_o),
        .handoff_state_o              (handoff_state_o)
    );

endmodule

`default_nettype wire
