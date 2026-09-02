// BFE13 ARCH1 TRACK0 candidate controller.
//
// This is deliberately a new candidate fork.  The authoritative ARCH0
// controller and the frozen BFE12 SIGN0 controller are not edited.  TRACK0
// keeps the existing E4-to-E7 split subtraction and adds only the minimal
// dual-reference state, two polarity-local persistence bits, and an E8
// commit point.  No function/task or inferred multi-cycle storage is used in
// this synthesizable RTL.
`timescale 1ns/1ps
`default_nettype none

module bfe_backend_ctrl_arch1_track0 #(
    // Small-error persistence limits.  These are compile-time research
    // parameters; zero is the required default that disables tracking.
    parameter integer T_TRACK_RISE = 0,
    parameter integer T_TRACK_FALL = 0,
    // Maximum distance that a mutable track reference may move from its
    // corresponding startup/security anchor.  Zero also disables movement.
    parameter integer B_TRACK_RISE = 0,
    parameter integer B_TRACK_FALL = 0
) (
    // Shared positive-edge clock for capture, feature extraction, and all
    // backend pipeline/state registers.  The existing TIM0 edge discipline
    // is preserved; no second clock domain is introduced.
    input  wire       clk_probe_i,
    // Active-high asynchronous reset.  Reset starts fresh calibration and is
    // the only way to clear the sticky alarm or unfreeze the autonomous
    // tracker.
    input  wire       reset_i,
    // E4 consume strobe paired with the already stable M_FF feature value.
    input  wire       event_valid_i,
    // Event polarity: zero is RISE and one is FALL.  It is captured and
    // pipelined with every operand; the live input is never used at E7/E8.
    input  wire       edge_pol_i,
    // High only for startup-calibration samples.  Calibration and pre-lock
    // events are excluded from the alarm and tracking pipelines.
    input  wire       cal_mode_i,
    // Existing strict absolute-error margins for RISE and FALL events.
    input  wire [8:0] m_margin_rise_i,
    input  wire [8:0] m_margin_fall_i,
    // Existing BFE12 signed-RISE threshold.  It remains an input for exact
    // SIGN0 replay; TRACK0 adds no threshold/control port.
    input  wire [8:0] t_pos_rise_i,
    // High after four accepted calibration samples for both polarities.
    output wire       cal_lock_o,
    // E7 registered alarm pulse, formed as ABS alarm OR signed RISE alarm.
    output wire       droop_alarm_o,
    // E8 sticky alarm state.  It observes the preceding E7 pulse and clears
    // only on reset, matching the existing BFE12 timing contract.
    output reg        droop_alarm_sticky_o
);
    // ------------------------------------------------------------------
    // Startup calibration and dual references
    // ------------------------------------------------------------------
    reg [10:0] sum_rise_q;
    reg [10:0] sum_fall_q;
    reg [2:0]  count_rise_q;
    reg [2:0]  count_fall_q;
    reg        done_rise_q;
    reg        done_fall_q;

    // Immutable startup references are also the TRACK0 security anchors.
    // Ordinary tracking logic below never assigns these registers.
    reg [8:0]  m_ref_startup_rise_q;
    reg [8:0]  m_ref_startup_fall_q;
    // Mutable references used only by the ABS/tracking lane.
    reg [8:0]  m_ref_track_rise_q;
    reg [8:0]  m_ref_track_fall_q;
    // Bounds are computed once, together with the fourth calibration sample,
    // using 10-bit intermediate arithmetic and then held for runtime use.
    reg [8:0]  track_upper_rise_q;
    reg [8:0]  track_lower_rise_q;
    reg [8:0]  track_upper_fall_q;
    reg [8:0]  track_lower_fall_q;

    // The following wires describe the fourth-sample arithmetic without a
    // procedural function.  The 11-bit sum covers 4*435=1740; the shifted
    // nine-bit reference remains in the legal 0..435 M_FF range.
    wire [10:0] rise_sum4_w = sum_rise_q + m_ff_i;
    wire [10:0] fall_sum4_w = sum_fall_q + m_ff_i;
    wire [8:0]  rise_ref4_w = rise_sum4_w[10:2];
    wire [8:0]  fall_ref4_w = fall_sum4_w[10:2];

    // ------------------------------------------------------------------
    // E4 event parcel and aligned context
    // ------------------------------------------------------------------
    reg [8:0] event_m_q;
    reg [8:0] event_track_ref_q;
    reg [8:0] event_startup_anchor_q;
    reg [8:0] event_margin_q;
    reg [8:0] event_t_pos_rise_q;
    reg       event_edge_pol_q;
    reg       event_pending_q;
    reg       event_valid_q;

    reg [8:0] event_m_pipe_q;
    reg [8:0] event_track_ref_pipe_q;
    reg [8:0] event_startup_anchor_pipe_q;
    reg [8:0] event_margin_pipe_q;
    reg [8:0] event_t_pos_rise_pipe_q;
    reg       event_edge_pol_pipe_q;

    // ------------------------------------------------------------------
    // P4a/P4b split tracking subtraction
    // ------------------------------------------------------------------
    reg       sub_valid_q;
    reg       sub_dir_q;
    reg       sub_edge_pol_q;
    reg [8:0] sub_track_ref_q;
    reg [8:0] sub_margin_q;
    reg [3:0] sub_low_q;
    reg [4:0] sub_high_m_q;
    reg [4:0] sub_high_ref_q;
    reg       sub_borrow_q;

    reg [8:0] delta_q;
    reg       delta_valid_q;
    reg [8:0] alarm_margin_q;
    reg       alarm_edge_pol_q;
    reg       alarm_dir_q;
    reg [8:0] alarm_track_ref_q;

    // ------------------------------------------------------------------
    // Shallow signed security lane
    // ------------------------------------------------------------------
    // The trip point is deliberately ten bits: startup anchor and threshold
    // can each be 435, so a nine-bit sum would overflow.  The compare is
    // strict and therefore naturally disabled at T_POS_RISE=435.
    reg [9:0] security_trip_q;
    reg [8:0] security_m_q;
    reg       security_valid_q;
    reg       security_edge_pol_q;
    reg       signed_rise_hit_q;

    // Named causal alarm terms are intentionally visible for task-local
    // hierarchical assertions while remaining private to the macro boundary.
    wire abs_alarm;
    wire signed_rise_alarm;
    assign cal_lock_o = done_rise_q && done_fall_q;
    assign abs_alarm = delta_valid_q && (delta_q > alarm_margin_q);
    assign signed_rise_alarm = delta_valid_q && signed_rise_hit_q;
    assign droop_alarm_o = abs_alarm || signed_rise_alarm;

    // Exactly two state bits per polarity implement the complete TRACK0
    // temporal filter.  2'b11 is reserved and is recovered as IDLE.
    localparam [1:0] TRACK_IDLE = 2'b00;
    localparam [1:0] TRACK_WAIT_POS = 2'b01;
    localparam [1:0] TRACK_WAIT_NEG = 2'b10;
    reg [1:0] track_state_rise_q;
    reg [1:0] track_state_fall_q;

    // ------------------------------------------------------------------
    // Single sequential process: E4..E8 pipeline plus state/commit
    // ------------------------------------------------------------------
    always @(posedge clk_probe_i or posedge reset_i) begin
        if (reset_i) begin
            sum_rise_q <= 11'd0;
            sum_fall_q <= 11'd0;
            count_rise_q <= 3'd0;
            count_fall_q <= 3'd0;
            done_rise_q <= 1'b0;
            done_fall_q <= 1'b0;
            m_ref_startup_rise_q <= 9'd0;
            m_ref_startup_fall_q <= 9'd0;
            m_ref_track_rise_q <= 9'd0;
            m_ref_track_fall_q <= 9'd0;
            track_upper_rise_q <= 9'd0;
            track_lower_rise_q <= 9'd0;
            track_upper_fall_q <= 9'd0;
            track_lower_fall_q <= 9'd0;

            event_m_q <= 9'd0;
            event_track_ref_q <= 9'd0;
            event_startup_anchor_q <= 9'd0;
            event_margin_q <= 9'd0;
            event_t_pos_rise_q <= 9'd0;
            event_edge_pol_q <= 1'b0;
            event_pending_q <= 1'b0;
            event_valid_q <= 1'b0;
            event_m_pipe_q <= 9'd0;
            event_track_ref_pipe_q <= 9'd0;
            event_startup_anchor_pipe_q <= 9'd0;
            event_margin_pipe_q <= 9'd0;
            event_t_pos_rise_pipe_q <= 9'd0;
            event_edge_pol_pipe_q <= 1'b0;

            sub_valid_q <= 1'b0;
            sub_dir_q <= 1'b0;
            sub_edge_pol_q <= 1'b0;
            sub_track_ref_q <= 9'd0;
            sub_margin_q <= 9'd0;
            sub_low_q <= 4'd0;
            sub_high_m_q <= 5'd0;
            sub_high_ref_q <= 5'd0;
            sub_borrow_q <= 1'b0;
            delta_q <= 9'd0;
            delta_valid_q <= 1'b0;
            alarm_margin_q <= 9'd0;
            alarm_edge_pol_q <= 1'b0;
            alarm_dir_q <= 1'b0;
            alarm_track_ref_q <= 9'd0;

            security_trip_q <= 10'd0;
            security_m_q <= 9'd0;
            security_valid_q <= 1'b0;
            security_edge_pol_q <= 1'b0;
            signed_rise_hit_q <= 1'b0;

            track_state_rise_q <= TRACK_IDLE;
            track_state_fall_q <= TRACK_IDLE;
            droop_alarm_sticky_o <= 1'b0;
        end else begin
            // E4: capture one atomic event parcel.  The selected mutable
            // reference and immutable startup anchor are sampled together;
            // later stages never read the live polarity or references.
            event_m_q <= m_ff_i;
            event_edge_pol_q <= edge_pol_i;
            event_t_pos_rise_q <= t_pos_rise_i;
            if (edge_pol_i) begin
                event_track_ref_q <= m_ref_track_fall_q;
                event_startup_anchor_q <= m_ref_startup_fall_q;
                event_margin_q <= m_margin_fall_i;
            end else begin
                event_track_ref_q <= m_ref_track_rise_q;
                event_startup_anchor_q <= m_ref_startup_rise_q;
                event_margin_q <= m_margin_rise_i;
            end
            event_pending_q <= event_valid_i && cal_lock_o && !cal_mode_i;
            event_valid_q <= event_pending_q;

            // Context alignment register before both arithmetic lanes.
            event_m_pipe_q <= event_m_q;
            event_track_ref_pipe_q <= event_track_ref_q;
            event_startup_anchor_pipe_q <= event_startup_anchor_q;
            event_margin_pipe_q <= event_margin_q;
            event_t_pos_rise_pipe_q <= event_t_pos_rise_q;
            event_edge_pol_pipe_q <= event_edge_pol_q;

            // E5/P4a: retain the existing timing-friendly high/low split.
            // Direction is decided from the high half; the low magnitude and
            // borrow are registered for the following shallow high subtract.
            sub_valid_q <= event_valid_q;
            sub_track_ref_q <= event_track_ref_pipe_q;
            sub_margin_q <= event_margin_pipe_q;
            sub_edge_pol_q <= event_edge_pol_pipe_q;
            if (event_m_pipe_q[8:4] > event_track_ref_pipe_q[8:4]) begin
                sub_dir_q <= 1'b1;
                sub_borrow_q <= event_m_pipe_q[3:0] < event_track_ref_pipe_q[3:0];
                sub_low_q <= event_m_pipe_q[3:0] - event_track_ref_pipe_q[3:0];
            end else if (event_m_pipe_q[8:4] < event_track_ref_pipe_q[8:4]) begin
                sub_dir_q <= 1'b0;
                sub_borrow_q <= event_track_ref_pipe_q[3:0] < event_m_pipe_q[3:0];
                sub_low_q <= event_track_ref_pipe_q[3:0] - event_m_pipe_q[3:0];
            end else if (event_m_pipe_q[3:0] >= event_track_ref_pipe_q[3:0]) begin
                sub_dir_q <= 1'b1;
                sub_borrow_q <= 1'b0;
                sub_low_q <= event_m_pipe_q[3:0] - event_track_ref_pipe_q[3:0];
            end else begin
                sub_dir_q <= 1'b0;
                sub_borrow_q <= 1'b0;
                sub_low_q <= event_track_ref_pipe_q[3:0] - event_m_pipe_q[3:0];
            end
            sub_high_m_q <= event_m_pipe_q[8:4];
            sub_high_ref_q <= event_track_ref_pipe_q[8:4];

            // E5 security lane: shallow 10-bit add.  It is independent of
            // the mutable tracking reference and therefore cannot learn drift.
            security_trip_q <= {1'b0, event_startup_anchor_pipe_q}
                             + {1'b0, event_t_pos_rise_pipe_q};
            security_m_q <= event_m_pipe_q;
            security_valid_q <= event_valid_q;
            security_edge_pol_q <= event_edge_pol_pipe_q;

            // E6/P4b: finish the split magnitude and align every event field.
            delta_valid_q <= sub_valid_q;
            alarm_margin_q <= sub_margin_q;
            alarm_edge_pol_q <= sub_edge_pol_q;
            alarm_dir_q <= sub_dir_q;
            alarm_track_ref_q <= sub_track_ref_q;
            if (sub_dir_q)
                delta_q <= {sub_high_m_q - sub_high_ref_q - sub_borrow_q, sub_low_q};
            else
                delta_q <= {sub_high_ref_q - sub_high_m_q - sub_borrow_q, sub_low_q};

            // E6 security compare.  The polarity gate is evaluated on the
            // aligned event context, never on the live input edge_pol_i.
            signed_rise_hit_q <= security_valid_q && !security_edge_pol_q
                              && ({1'b0, security_m_q} > security_trip_q);

            // E8: sticky observes the preceding registered E7 alarm pulse.
            if (droop_alarm_o)
                droop_alarm_sticky_o <= 1'b1;

            // Startup calibration is unchanged.  Bounds and both reference
            // classes are initialized atomically on each polarity's fourth
            // accepted sample; completed epochs ignore later cal samples.
            if (event_valid_i && cal_mode_i) begin
                if (!edge_pol_i && !done_rise_q) begin
                    if (count_rise_q == 3'd3) begin
                        m_ref_startup_rise_q <= rise_ref4_w;
                        m_ref_track_rise_q <= rise_ref4_w;
                        if (({1'b0, rise_ref4_w} + B_TRACK_RISE) > 10'd435)
                            track_upper_rise_q <= 9'd435;
                        else
                            track_upper_rise_q <= {1'b0, rise_ref4_w} + B_TRACK_RISE;
                        if (rise_ref4_w > B_TRACK_RISE)
                            track_lower_rise_q <= rise_ref4_w - B_TRACK_RISE;
                        else
                            track_lower_rise_q <= 9'd0;
                        done_rise_q <= 1'b1;
                    end else begin
                        sum_rise_q <= sum_rise_q + m_ff_i;
                        count_rise_q <= count_rise_q + 3'd1;
                    end
                end else if (edge_pol_i && !done_fall_q) begin
                    if (count_fall_q == 3'd3) begin
                        m_ref_startup_fall_q <= fall_ref4_w;
                        m_ref_track_fall_q <= fall_ref4_w;
                        if (({1'b0, fall_ref4_w} + B_TRACK_FALL) > 10'd435)
                            track_upper_fall_q <= 9'd435;
                        else
                            track_upper_fall_q <= {1'b0, fall_ref4_w} + B_TRACK_FALL;
                        if (fall_ref4_w > B_TRACK_FALL)
                            track_lower_fall_q <= fall_ref4_w - B_TRACK_FALL;
                        else
                            track_lower_fall_q <= 9'd0;
                        done_fall_q <= 1'b1;
                    end else begin
                        sum_fall_q <= sum_fall_q + m_ff_i;
                        count_fall_q <= count_fall_q + 3'd1;
                    end
                end
            end

            // E8 tracker commit.  This block is intentionally after the
            // alarm/sticky update and consumes the aligned E7 event context.
            // No assignment here can feed the already-computed E7 alarm.
            if (droop_alarm_o) begin
                track_state_rise_q <= TRACK_IDLE;
                track_state_fall_q <= TRACK_IDLE;
            end else if (!droop_alarm_sticky_o) begin
                if (delta_valid_q) begin
                    if (!alarm_edge_pol_q) begin
                        // A mismatch means this event was computed against an
                        // older reference and cannot count toward persistence.
                        if (alarm_track_ref_q != m_ref_track_rise_q) begin
                            track_state_rise_q <= TRACK_IDLE;
                        end else if (delta_q == 9'd0) begin
                            track_state_rise_q <= TRACK_IDLE;
                        end else if (delta_q > T_TRACK_RISE) begin
                            track_state_rise_q <= TRACK_IDLE;
                        end else if (alarm_dir_q) begin
                            if (track_state_rise_q == TRACK_WAIT_POS) begin
                                if (m_ref_track_rise_q < track_upper_rise_q)
                                    m_ref_track_rise_q <= m_ref_track_rise_q + 9'd1;
                                track_state_rise_q <= TRACK_IDLE;
                            end else begin
                                track_state_rise_q <= TRACK_WAIT_POS;
                            end
                        end else begin
                            if (track_state_rise_q == TRACK_WAIT_NEG) begin
                                if (m_ref_track_rise_q > track_lower_rise_q)
                                    m_ref_track_rise_q <= m_ref_track_rise_q - 9'd1;
                                track_state_rise_q <= TRACK_IDLE;
                            end else begin
                                track_state_rise_q <= TRACK_WAIT_NEG;
                            end
                        end
                    end else begin
                        if (alarm_track_ref_q != m_ref_track_fall_q) begin
                            track_state_fall_q <= TRACK_IDLE;
                        end else if (delta_q == 9'd0) begin
                            track_state_fall_q <= TRACK_IDLE;
                        end else if (delta_q > T_TRACK_FALL) begin
                            track_state_fall_q <= TRACK_IDLE;
                        end else if (alarm_dir_q) begin
                            if (track_state_fall_q == TRACK_WAIT_POS) begin
                                if (m_ref_track_fall_q < track_upper_fall_q)
                                    m_ref_track_fall_q <= m_ref_track_fall_q + 9'd1;
                                track_state_fall_q <= TRACK_IDLE;
                            end else begin
                                track_state_fall_q <= TRACK_WAIT_POS;
                            end
                        end else begin
                            if (track_state_fall_q == TRACK_WAIT_NEG) begin
                                if (m_ref_track_fall_q > track_lower_fall_q)
                                    m_ref_track_fall_q <= m_ref_track_fall_q - 9'd1;
                                track_state_fall_q <= TRACK_IDLE;
                            end else begin
                                track_state_fall_q <= TRACK_WAIT_NEG;
                            end
                        end
                    end
                end
            end
        end
    end
endmodule

`default_nettype wire
