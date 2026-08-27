// B-FE5 ARCH0 calibration and detector controller with pipelined decision.
//
// This block intentionally uses counters and done flags rather than a state
// machine: the frozen protocol has only two independent four-sample epochs,
// so an FSM would add state without adding behavior.  All storage is clocked
// by the existing clk_probe and asynchronously cleared by reset.
`timescale 1ns/1ps
`default_nettype none

module bfe_backend_ctrl (
    // The sole backend sequential clock, shared with the capture-bank DFFs.
    input  wire       clk_probe_i,
    // Active-high asynchronous reset; starts one fresh calibration epoch.
    input  wire       reset_i,
    // Backend consume strobe.  A sample is counted only when this is high.
    input  wire       event_valid_i,
    // Polarity selector: 1'b0 denotes RISE and 1'b1 denotes FALL.
    input  wire       edge_pol_i,
    // Explicit startup-calibration mode; normal detection is added in RTL2.
    input  wire       cal_mode_i,
    // Current nine-bit weighted capture feature from bfe_m_feature.
    input  wire [8:0] m_ff_i,
    // Programmable strict alarm margins for RISE and FALL events.
    input  wire [8:0] m_margin_rise_i,
    input  wire [8:0] m_margin_fall_i,
    // Indicates that both four-sample references are frozen and usable.
    output wire       cal_lock_o,
    // Registered alarm pulse, valid after the fixed detector pipeline latency.
    output wire       droop_alarm_o,
    // Sticky alarm, cleared only by reset_i.
    output reg        droop_alarm_sticky_o
);
    reg [10:0] sum_rise_q;
    reg [10:0] sum_fall_q;
    reg [2:0]  count_rise_q;
    reg [2:0]  count_fall_q;
    reg [8:0]  m_ref_rise_q;
    reg [8:0]  m_ref_fall_q;
    reg        done_rise_q;
    reg        done_fall_q;
    // Detector pipeline: capture event context first, then register the
    // absolute difference.  The final comparison is therefore shallow.
    reg [8:0]  event_m_q;
    reg [8:0]  event_ref_q;
    reg [8:0]  event_margin_q;
    reg        event_pending_q;
    reg        event_valid_q;
    reg        delta_valid_q;
    reg [8:0]  event_m_pipe_q;
    reg [8:0]  event_ref_pipe_q;
    reg [8:0]  event_margin_pipe_q;
    reg [8:0]  delta_q;
    reg        sub_valid_q;
    reg        sub_dir_q;
    reg [3:0]  sub_low_q;
    reg [4:0]  sub_high_m_q;
    reg [4:0]  sub_high_ref_q;
    reg        sub_borrow_q;
    reg [8:0]  sub_margin_q;
    // P4b companion context: sub_margin_q advances for the next event at the
    // same edge that delta_q is written for the current event.  Retaining the
    // old P4a margin here keeps the comparison pair atomic at the output
    // boundary while preserving one-event-per-clock throughput.
    reg [8:0]  alarm_margin_q;

    assign cal_lock_o = done_rise_q && done_fall_q;
    assign droop_alarm_o = delta_valid_q && (delta_q > alarm_margin_q);

    // Four samples require eleven accumulator bits (4*435=1740).  On the
    // fourth valid sample the current M value is included before the divide
    // by four, implemented as the specified two-bit right shift.  Once a
    // polarity is done, later events are ignored until reset.
    always @(posedge clk_probe_i or posedge reset_i) begin
        if (reset_i) begin
            sum_rise_q   <= 11'd0;
            sum_fall_q   <= 11'd0;
            count_rise_q <= 3'd0;
            count_fall_q <= 3'd0;
            m_ref_rise_q <= 9'd0;
            m_ref_fall_q <= 9'd0;
            done_rise_q  <= 1'b0;
            done_fall_q  <= 1'b0;
            event_m_q <= 9'd0;
            event_ref_q <= 9'd0;
            event_margin_q <= 9'd0;
            event_pending_q <= 1'b0;
            event_valid_q <= 1'b0;
            delta_valid_q <= 1'b0;
            event_m_pipe_q <= 9'd0;
            event_ref_pipe_q <= 9'd0;
            event_margin_pipe_q <= 9'd0;
            delta_q <= 9'd0;
            sub_valid_q <= 1'b0;
            sub_dir_q <= 1'b0;
            sub_low_q <= 4'd0;
            sub_high_m_q <= 5'd0;
            sub_high_ref_q <= 5'd0;
            sub_borrow_q <= 1'b0;
            sub_margin_q <= 9'd0;
            alarm_margin_q <= 9'd0;
            droop_alarm_sticky_o <= 1'b0;
        end else begin
            // First detector register captures the M/reference/margin context.
            event_m_q <= m_ff_i;
            if (edge_pol_i) begin
                event_ref_q <= m_ref_fall_q;
                event_margin_q <= m_margin_fall_i;
            end else begin
                event_ref_q <= m_ref_rise_q;
                event_margin_q <= m_margin_rise_i;
            end
            // Evaluate the qualifier directly at the sampling edge. This
            // avoids any simulation delta-cycle ambiguity while preserving
            // the hardware meaning of the consume strobe.
            event_pending_q <= event_valid_i && cal_lock_o && !cal_mode_i;
            event_valid_q <= event_pending_q;
            // Operand alignment register: this adds no logic, but isolates
            // the subtraction from the event-context capture path.
            event_m_pipe_q <= event_m_q;
            event_ref_pipe_q <= event_ref_q;
            event_margin_pipe_q <= event_margin_q;
            // P4a: split the absolute subtraction at bit 4.  Direction is
            // decided from the high nibble first; the low nibble and borrow
            // are registered separately, limiting this stage's carry depth.
            sub_valid_q <= event_valid_q;
            sub_margin_q <= event_margin_pipe_q;
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

            // P4b: only a five-bit high-half subtraction remains here.  The
            // registered low result and borrow complete delta_q atomically.
            delta_valid_q <= sub_valid_q;
            // sub_margin_q is the P4a margin for the event entering the
            // subtraction stage.  At this same clock edge it is replaced by
            // the next event's margin, so copy its pre-edge value alongside
            // delta_q for the P4b alarm comparison.
            alarm_margin_q <= sub_margin_q;
            if (sub_dir_q)
                delta_q <= {sub_high_m_q - sub_high_ref_q - sub_borrow_q, sub_low_q};
            else
                delta_q <= {sub_high_ref_q - sub_high_m_q - sub_borrow_q, sub_low_q};
            // Sticky observes the previously registered alarm pulse.
            if (droop_alarm_o)
                droop_alarm_sticky_o <= 1'b1;

            if (event_valid_i && cal_mode_i) begin
                if (!edge_pol_i && !done_rise_q) begin
                    if (count_rise_q == 3'd3) begin
                        m_ref_rise_q <= (sum_rise_q + m_ff_i) >> 2;
                        done_rise_q  <= 1'b1;
                    end else begin
                        sum_rise_q   <= sum_rise_q + m_ff_i;
                        count_rise_q <= count_rise_q + 3'd1;
                    end
                end else if (edge_pol_i && !done_fall_q) begin
                    if (count_fall_q == 3'd3) begin
                        m_ref_fall_q <= (sum_fall_q + m_ff_i) >> 2;
                        done_fall_q  <= 1'b1;
                    end else begin
                        sum_fall_q   <= sum_fall_q + m_ff_i;
                        count_fall_q <= count_fall_q + 3'd1;
                    end
                end
            end
        end
    end
endmodule

`default_nettype wire
