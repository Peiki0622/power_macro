// BFE12 ARCH1-SIGN0 candidate controller.
//
// This file is deliberately a candidate fork.  The authoritative ARCH0
// controller is left untouched so that equivalence and provenance checks can
// compare the two implementations directly.  SIGN0 adds only the evidence-
// backed positive RISE signed-error comparator; startup calibration, the
// absolute comparator, sticky behavior, and the existing E4-to-E7 pipeline
// remain structurally equivalent to ARCH0.
`timescale 1ns/1ps
`default_nettype none

module bfe_backend_ctrl_arch1_sign0 (
    // Sole sequential clock for calibration, event-context capture, and the
    // detector pipeline.  It is shared with the capture-bank DFFs and the
    // M_FF feature pipeline, exactly as in the ARCH0 controller.
    input  wire       clk_probe_i,
    // Active-high asynchronous reset.  Reset starts a new independent RISE
    // and FALL calibration epoch and is the only sticky-alarm clear action.
    input  wire       reset_i,
    // Backend consume strobe.  A normal event is accepted only when this is
    // high at E4; calibration samples use the same strobe with cal_mode_i set.
    input  wire       event_valid_i,
    // Event polarity selector: 1'b0 selects RISE reference and 1'b1 selects
    // FALL reference.  The value is captured with the event and never read
    // live at the final comparator boundary.
    input  wire       edge_pol_i,
    // Explicit startup-calibration qualifier.  Normal detector events must
    // drive this low; calibration-mode events are prevented from alarming.
    input  wire       cal_mode_i,
    // Current nine-bit weighted capture feature M_FF, ranging from 0 to 435.
    input  wire [8:0] m_ff_i,
    // Frozen/programmed strict absolute alarm margin for RISE events.
    input  wire [8:0] m_margin_rise_i,
    // Frozen/programmed strict absolute alarm margin for FALL events.
    input  wire [8:0] m_margin_fall_i,
    // Evidence-backed diagnostic signed-RISE threshold.  SIGN0 evaluates
    // positive RISE error only; values 18 and 19 are exercised by replay,
    // while 435 is used solely as a deterministic regression disable value.
    input  wire [8:0] t_pos_rise_i,
    // High only after four valid RISE and four valid FALL calibration samples.
    output wire       cal_lock_o,
    // Registered E7 combined alarm pulse.  ABS and signed-RISE requests are
    // OR-combined at this existing output boundary without an added stage.
    output wire       droop_alarm_o,
    // E8 sticky alarm state.  It observes the preceding registered alarm and
    // remains set until reset_i, matching the ARCH0 next-edge semantics.
    output reg        droop_alarm_sticky_o
);
    // Startup calibration accumulators and completion state.  Eleven bits
    // cover the largest possible four-sample sum (4*435=1740).
    reg [10:0] sum_rise_q;
    reg [10:0] sum_fall_q;
    reg [2:0]  count_rise_q;
    reg [2:0]  count_fall_q;
    reg [8:0]  m_ref_rise_q;
    reg [8:0]  m_ref_fall_q;
    reg        done_rise_q;
    reg        done_fall_q;

    // E4 event parcel.  These registers capture M_FF and the selected
    // reference/margin together with the signed-decision metadata.
    reg [8:0]  event_m_q;
    reg [8:0]  event_ref_q;
    reg [8:0]  event_margin_q;
    reg        event_edge_pol_q;
    reg [8:0]  event_t_pos_rise_q;
    reg        event_pending_q;
    reg        event_valid_q;

    // Operand pipeline register.  Keeping every context field beside the
    // operands prevents a later event's live polarity or threshold from being
    // paired with the current event's delta.
    reg [8:0]  event_m_pipe_q;
    reg [8:0]  event_ref_pipe_q;
    reg [8:0]  event_margin_pipe_q;
    reg        event_edge_pol_pipe_q;
    reg [8:0]  event_t_pos_rise_pipe_q;

    // P4a split-subtraction state.  sub_dir_q is the sign of e=M_FF-M_REF:
    // one means non-negative/positive direction and zero means negative
    // direction.  delta is completed in P4b as the absolute magnitude.
    reg        sub_valid_q;
    reg        sub_dir_q;
    reg        sub_edge_pol_q;
    reg [8:0]  sub_t_pos_rise_q;
    reg [3:0]  sub_low_q;
    reg [4:0]  sub_high_m_q;
    reg [4:0]  sub_high_ref_q;
    reg        sub_borrow_q;
    reg [8:0]  sub_margin_q;

    // P4b output-alignment state.  These companion registers advance with
    // delta_q so the final compare always uses one event's polarity, sign,
    // threshold, and absolute margin atomically.
    reg [8:0]  delta_q;
    reg        delta_valid_q;
    reg [8:0]  alarm_margin_q;
    reg        alarm_edge_pol_q;
    reg [8:0]  alarm_t_pos_rise_q;
    reg        alarm_dir_q;

    // Named task-local observability nets make the two causal alarm sources
    // explicit while preserving the single registered droop_alarm output.
    wire abs_alarm;
    wire signed_rise_alarm;

    assign cal_lock_o = done_rise_q && done_fall_q;
    assign abs_alarm = delta_valid_q && (delta_q > alarm_margin_q);
    assign signed_rise_alarm = delta_valid_q && !alarm_edge_pol_q &&
                               alarm_dir_q && (delta_q > alarm_t_pos_rise_q);
    assign droop_alarm_o = abs_alarm || signed_rise_alarm;

    // All state below uses the original ARCH0 single-clock protocol.  The
    // event parcel is qualified at E4, the split subtraction occupies P4a/P4b,
    // and the final registered alarm remains at E7.  No tracker or reference
    // update logic is present in SIGN0; references freeze after calibration.
    always @(posedge clk_probe_i or posedge reset_i) begin
        if (reset_i) begin
            sum_rise_q <= 11'd0;
            sum_fall_q <= 11'd0;
            count_rise_q <= 3'd0;
            count_fall_q <= 3'd0;
            m_ref_rise_q <= 9'd0;
            m_ref_fall_q <= 9'd0;
            done_rise_q <= 1'b0;
            done_fall_q <= 1'b0;
            event_m_q <= 9'd0;
            event_ref_q <= 9'd0;
            event_margin_q <= 9'd0;
            event_edge_pol_q <= 1'b0;
            event_t_pos_rise_q <= 9'd0;
            event_pending_q <= 1'b0;
            event_valid_q <= 1'b0;
            event_m_pipe_q <= 9'd0;
            event_ref_pipe_q <= 9'd0;
            event_margin_pipe_q <= 9'd0;
            event_edge_pol_pipe_q <= 1'b0;
            event_t_pos_rise_pipe_q <= 9'd0;
            sub_valid_q <= 1'b0;
            sub_dir_q <= 1'b0;
            sub_edge_pol_q <= 1'b0;
            sub_t_pos_rise_q <= 9'd0;
            sub_low_q <= 4'd0;
            sub_high_m_q <= 5'd0;
            sub_high_ref_q <= 5'd0;
            sub_borrow_q <= 1'b0;
            sub_margin_q <= 9'd0;
            delta_q <= 9'd0;
            delta_valid_q <= 1'b0;
            alarm_margin_q <= 9'd0;
            alarm_edge_pol_q <= 1'b0;
            alarm_t_pos_rise_q <= 9'd0;
            alarm_dir_q <= 1'b0;
            droop_alarm_sticky_o <= 1'b0;
        end else begin
            // E4: capture the M/reference/margin and signed context parcel.
            event_m_q <= m_ff_i;
            event_edge_pol_q <= edge_pol_i;
            event_t_pos_rise_q <= t_pos_rise_i;
            if (edge_pol_i) begin
                event_ref_q <= m_ref_fall_q;
                event_margin_q <= m_margin_fall_i;
            end else begin
                event_ref_q <= m_ref_rise_q;
                event_margin_q <= m_margin_rise_i;
            end
            // Calibration and pre-lock events are intentionally invalid for
            // the detector, preserving ARCH0 qualification semantics.
            event_pending_q <= event_valid_i && cal_lock_o && !cal_mode_i;
            event_valid_q <= event_pending_q;

            // Operand/context alignment register before the split subtractor.
            event_m_pipe_q <= event_m_q;
            event_ref_pipe_q <= event_ref_q;
            event_margin_pipe_q <= event_margin_q;
            event_edge_pol_pipe_q <= event_edge_pol_q;
            event_t_pos_rise_pipe_q <= event_t_pos_rise_q;

            // P4a: determine the sign direction from the high half first,
            // then register the low-half magnitude and borrow.  This is the
            // existing timing-friendly sign+magnitude implementation, not a
            // second wide signed subtractor.
            sub_valid_q <= event_valid_q;
            sub_margin_q <= event_margin_pipe_q;
            sub_edge_pol_q <= event_edge_pol_pipe_q;
            sub_t_pos_rise_q <= event_t_pos_rise_pipe_q;
            if (event_m_pipe_q[8:4] > event_ref_pipe_q[8:4]) begin
                sub_dir_q <= 1'b1;
                sub_borrow_q <= (event_m_pipe_q[3:0] < event_ref_pipe_q[3:0]);
                sub_low_q <= event_m_pipe_q[3:0] - event_ref_pipe_q[3:0];
            end else if (event_m_pipe_q[8:4] < event_ref_pipe_q[8:4]) begin
                sub_dir_q <= 1'b0;
                sub_borrow_q <= (event_ref_pipe_q[3:0] < event_m_pipe_q[3:0]);
                sub_low_q <= event_ref_pipe_q[3:0] - event_m_pipe_q[3:0];
            end else if (event_m_pipe_q[3:0] >= event_ref_pipe_q[3:0]) begin
                sub_dir_q <= 1'b1;
                sub_borrow_q <= 1'b0;
                sub_low_q <= event_m_pipe_q[3:0] - event_ref_pipe_q[3:0];
            end else begin
                sub_dir_q <= 1'b0;
                sub_borrow_q <= 1'b0;
                sub_low_q <= event_ref_pipe_q[3:0] - event_m_pipe_q[3:0];
            end
            sub_high_m_q <= event_m_pipe_q[8:4];
            sub_high_ref_q <= event_ref_pipe_q[8:4];

            // P4b: complete the magnitude and carry every signed-decision
            // context bit alongside it.  The alarm therefore retains the
            // original event identity at the E7 comparison boundary.
            delta_valid_q <= sub_valid_q;
            alarm_margin_q <= sub_margin_q;
            alarm_edge_pol_q <= sub_edge_pol_q;
            alarm_t_pos_rise_q <= sub_t_pos_rise_q;
            alarm_dir_q <= sub_dir_q;
            if (sub_dir_q)
                delta_q <= {sub_high_m_q - sub_high_ref_q - sub_borrow_q, sub_low_q};
            else
                delta_q <= {sub_high_ref_q - sub_high_m_q - sub_borrow_q, sub_low_q};

            // Sticky observes the already-registered E7 alarm, so its set
            // timing is identical to ARCH0 and reset remains its only clear.
            if (droop_alarm_o)
                droop_alarm_sticky_o <= 1'b1;

            // Startup calibration is unchanged: four accepted samples per
            // polarity, with the fourth sample included before the specified
            // arithmetic right shift by two.  Completed references ignore all
            // later calibration-mode samples until reset.
            if (event_valid_i && cal_mode_i) begin
                if (!edge_pol_i && !done_rise_q) begin
                    if (count_rise_q == 3'd3) begin
                        m_ref_rise_q <= (sum_rise_q + m_ff_i) >> 2;
                        done_rise_q <= 1'b1;
                    end else begin
                        sum_rise_q <= sum_rise_q + m_ff_i;
                        count_rise_q <= count_rise_q + 3'd1;
                    end
                end else if (edge_pol_i && !done_fall_q) begin
                    if (count_fall_q == 3'd3) begin
                        m_ref_fall_q <= (sum_fall_q + m_ff_i) >> 2;
                        done_fall_q <= 1'b1;
                    end else begin
                        sum_fall_q <= sum_fall_q + m_ff_i;
                        count_fall_q <= count_fall_q + 3'd1;
                    end
                end
            end
        end
    end
endmodule

`default_nettype wire
