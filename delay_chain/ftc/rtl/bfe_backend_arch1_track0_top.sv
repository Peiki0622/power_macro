// BFE13 ARCH1 TRACK0 candidate integration top.
//
// The top-level interface is intentionally identical to the frozen BFE12
// SIGN0 top.  Four compile-time tracker parameters are the only new
// configuration mechanism; no runtime tracking/debug/OPP/rebase port is
// exposed.  The physical capture bank and weighted feature pipeline are
// instantiated unchanged.
`timescale 1ns/1ps
`default_nettype none

module bfe_backend_arch1_track0_top #(
    // Compile-time TRACK0 research knobs.  All defaults are zero so an
    // unconfigured instance is tracker-disabled and suitable for SIGN0 A/B
    // equivalence replay.  These are not production-frozen values.
    parameter integer T_TRACK_RISE = 0,
    parameter integer T_TRACK_FALL = 0,
    parameter integer B_TRACK_RISE = 0,
    parameter integer B_TRACK_FALL = 0
) (
    // Thirty-bit Level-0-restored safe-domain capture word.  Each bit feeds
    // one unchanged LATQ/DFF lane in bfe_capture_bank.
    input  wire [29:0] safe_d,
    // Common active-high transparency gate shared by all capture LATQs.
    input  wire        latch_gate,
    // Common positive-edge probe clock for capture, feature, and controller.
    input  wire        clk_probe,
    // Active-high asynchronous reset for capture and backend state.
    input  wire        reset,
    // E4 consume strobe for the stable M_FF event presented by the frozen
    // capture/feature timing discipline.
    input  wire        event_valid,
    // Event polarity selector: 0=RISE, 1=FALL; sampled with the event.
    input  wire        edge_pol,
    // Startup calibration qualifier for the four RISE/FALL samples.
    input  wire        cal_mode,
    // Existing strict absolute alarm margins, unchanged from BFE12 SIGN0.
    input  wire [8:0]  m_margin_rise,
    input  wire [8:0]  m_margin_fall,
    // Existing strict signed-RISE threshold input retained for SIGN0 replay.
    input  wire [8:0]  t_pos_rise,
    // Calibration lock after both polarity epochs complete.
    output wire        cal_lock,
    // Registered E7 ABS-or-signed-RISE alarm pulse.
    output wire        droop_alarm,
    // Sticky E8 alarm state; reset is its only clear mechanism.
    output wire        droop_alarm_sticky
);
    // These internal nets preserve the existing macro boundary: q_ff and
    // M_FF are private implementation signals, not new external ports.
    wire [29:0] q_ff;
    wire [8:0]  m_ff;

    // Unchanged physical capture topology: thirty real LATQ/DFF wrappers.
    bfe_capture_bank u_capture_bank (
        .safe_d_i      (safe_d),
        .latch_gate_i  (latch_gate),
        .clk_probe_i   (clk_probe),
        .reset_i       (reset),
        .q_ff_o        (q_ff)
    );

    // Unchanged three-stage weighted feature extraction producing M_FF.
    bfe_m_feature u_m_feature (
        .q_ff_i      (q_ff),
        .clk_probe_i (clk_probe),
        .reset_i     (reset),
        .m_ff_o      (m_ff)
    );

    // Candidate-only backend fork.  Parameter values are elaboration-time;
    // all event/status ports retain the BFE12 SIGN0 contract exactly.
    bfe_backend_ctrl_arch1_track0 #(
        .T_TRACK_RISE (T_TRACK_RISE),
        .T_TRACK_FALL (T_TRACK_FALL),
        .B_TRACK_RISE (B_TRACK_RISE),
        .B_TRACK_FALL (B_TRACK_FALL)
    ) u_backend_ctrl (
        .clk_probe_i          (clk_probe),
        .reset_i              (reset),
        .event_valid_i        (event_valid),
        .edge_pol_i           (edge_pol),
        .cal_mode_i           (cal_mode),
        .m_ff_i               (m_ff),
        .m_margin_rise_i      (m_margin_rise),
        .m_margin_fall_i      (m_margin_fall),
        .t_pos_rise_i         (t_pos_rise),
        .cal_lock_o           (cal_lock),
        .droop_alarm_o        (droop_alarm),
        .droop_alarm_sticky_o (droop_alarm_sticky)
    );
endmodule

`default_nettype wire
