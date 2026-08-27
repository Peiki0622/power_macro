// B-FE5 ARCH0 integration top: capture, calibration, and minimal detector.
//
// The RTL0-only M output is intentionally replaced here by the final status
// interface. M_FF, q_ff, accumulators, references, and delta remain private
// implementation signals; the macro interface exposes only required status.
`timescale 1ns/1ps
`default_nettype none

module bfe_backend_top (
    // Fixed 30-bit safe-domain restored capture word.
    input  wire [29:0] safe_d,
    // Common active-high LATQ transparency control.
    input  wire        latch_gate,
    // Common positive-edge DFF/backend clock.
    input  wire        clk_probe,
    // Common active-high asynchronous DFF reset.
    input  wire        reset,
    // Backend consume strobe for the already captured M_FF sample.
    input  wire        event_valid,
    // Edge polarity selector: 0=RISE, 1=FALL.
    input  wire        edge_pol,
    // Explicit startup-calibration enable; normal detection uses cal_mode=0.
    input  wire        cal_mode,
    // Strict unsigned alarm margin for RISE events.
    input  wire [8:0]  m_margin_rise,
    // Strict unsigned alarm margin for FALL events.
    input  wire [8:0]  m_margin_fall,
    // Calibration lock status; high only after four valid samples per edge.
    output wire        cal_lock,
    // Current-event alarm, qualified by event_valid and calibration lock.
    output wire        droop_alarm,
    // Sticky alarm, cleared only by reset.
    output wire        droop_alarm_sticky
);
    wire [29:0] q_ff;
    wire [8:0]  m_ff;

    bfe_capture_bank u_capture_bank (
        .safe_d_i      (safe_d),
        .latch_gate_i  (latch_gate),
        .clk_probe_i   (clk_probe),
        .reset_i       (reset),
        .q_ff_o        (q_ff)
    );

    bfe_m_feature u_m_feature (
        .q_ff_i      (q_ff),
        .clk_probe_i (clk_probe),
        .reset_i     (reset),
        .m_ff_o      (m_ff)
    );

    bfe_backend_ctrl u_backend_ctrl (
        .clk_probe_i   (clk_probe),
        .reset_i       (reset),
        .event_valid_i (event_valid),
        .edge_pol_i    (edge_pol),
        .cal_mode_i    (cal_mode),
        .m_ff_i        (m_ff),
        .m_margin_rise_i (m_margin_rise),
        .m_margin_fall_i (m_margin_fall),
        .cal_lock_o    (cal_lock),
        .droop_alarm_o (droop_alarm),
        .droop_alarm_sticky_o (droop_alarm_sticky)
    );
endmodule

`default_nettype wire
