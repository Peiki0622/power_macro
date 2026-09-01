// BFE12 ARCH1-SIGN0 candidate integration top.
//
// The physical/frontend path and the feature pipeline are intentionally
// instantiated from the unchanged ARCH0 modules.  This top adds only the
// diagnostic T_POS_RISE configuration input required by the candidate signed
// comparator; no tracker, OPP, adaptation, or debug protocol is introduced.
`timescale 1ns/1ps
`default_nettype none

module bfe_backend_arch1_sign0_top (
    // Thirty-bit Level-0-restored safe-domain capture word.  Bit i feeds the
    // corresponding unchanged real LATQ/DFF lane in bfe_capture_bank.
    input  wire [29:0] safe_d,
    // Common active-high LATQ transparency gate shared by all capture lanes.
    input  wire        latch_gate,
    // Common positive-edge probe clock shared by capture, feature, and
    // controller sequential logic.
    input  wire        clk_probe,
    // Active-high asynchronous reset for the complete capture/backend path.
    input  wire        reset,
    // E4 backend consume strobe for the M_FF event presented four probe edges
    // after capture, following the frozen TIM0 timing discipline.
    input  wire        event_valid,
    // Event polarity selector: 0=RISE, 1=FALL.  The candidate captures this
    // value with the event before making either alarm decision.
    input  wire        edge_pol,
    // Startup-calibration qualifier.  Set for the four RISE and four FALL
    // samples; clear for normal detection events.
    input  wire        cal_mode,
    // Existing strict absolute-error margin for RISE events.
    input  wire [8:0]  m_margin_rise,
    // Existing strict absolute-error margin for FALL events.
    input  wire [8:0]  m_margin_fall,
    // Candidate-only strict signed-RISE threshold.  BFE12 exercises 18 and
    // 19 as retained-data diagnostics and 435 as equivalence/off configuration.
    input  wire [8:0]  t_pos_rise,
    // Calibration lock after both four-sample polarity epochs complete.
    output wire        cal_lock,
    // Registered E7 OR-combined absolute or signed-RISE alarm pulse.
    output wire        droop_alarm,
    // Sticky E8 alarm state, cleared only by reset.
    output wire        droop_alarm_sticky
);
    // Internal implementation signals remain private, matching the ARCH0
    // macro boundary.  Candidate-specific visibility is available through
    // hierarchical task-local assertions without widening this interface.
    wire [29:0] q_ff;
    wire [8:0]  m_ff;

    // Reuse the frozen thirty-lane capture topology unchanged.
    bfe_capture_bank u_capture_bank (
        .safe_d_i      (safe_d),
        .latch_gate_i  (latch_gate),
        .clk_probe_i   (clk_probe),
        .reset_i       (reset),
        .q_ff_o        (q_ff)
    );

    // Reuse the frozen three-stage weighted feature extraction unchanged.
    bfe_m_feature u_m_feature (
        .q_ff_i      (q_ff),
        .clk_probe_i (clk_probe),
        .reset_i     (reset),
        .m_ff_o      (m_ff)
    );

    // Candidate backend fork.  Its only additional functional input is the
    // evidence-backed signed-RISE threshold; all ARCH0 margins and controls
    // retain their original meaning and timing.
    bfe_backend_ctrl_arch1_sign0 u_backend_ctrl (
        .clk_probe_i       (clk_probe),
        .reset_i           (reset),
        .event_valid_i     (event_valid),
        .edge_pol_i        (edge_pol),
        .cal_mode_i        (cal_mode),
        .m_ff_i            (m_ff),
        .m_margin_rise_i   (m_margin_rise),
        .m_margin_fall_i   (m_margin_fall),
        .t_pos_rise_i      (t_pos_rise),
        .cal_lock_o        (cal_lock),
        .droop_alarm_o     (droop_alarm),
        .droop_alarm_sticky_o (droop_alarm_sticky)
    );
endmodule

`default_nettype wire
