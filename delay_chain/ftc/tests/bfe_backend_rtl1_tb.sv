// RTL1 self-checking startup-calibration testbench.
//
// Calibration samples traverse the same public safe_d/latch_gate/clk_probe
// path as RTL0.  Internal reference registers are inspected hierarchically
// only to verify freeze behavior; they are not added to the RTL interface.
`timescale 1ns/1ps
`default_nettype none

module bfe_backend_rtl1_tb;
    reg [29:0] safe_d;
    reg        latch_gate;
    reg        clk_probe;
    reg        reset;
    reg        event_valid;
    reg        edge_pol;
    reg        cal_mode;
    reg [8:0]  m_margin_rise;
    reg [8:0]  m_margin_fall;
    wire       cal_lock;
    wire       droop_alarm;
    wire       droop_alarm_sticky;
    integer    sample;
    reg [8:0]  rise_ref_before;
    reg [8:0]  fall_ref_before;

    bfe_backend_top dut (
        .safe_d(safe_d), .latch_gate(latch_gate), .clk_probe(clk_probe),
        .reset(reset), .event_valid(event_valid), .edge_pol(edge_pol),
        .cal_mode(cal_mode), .m_margin_rise(m_margin_rise),
        .m_margin_fall(m_margin_fall), .cal_lock(cal_lock),
        .droop_alarm(droop_alarm), .droop_alarm_sticky(droop_alarm_sticky)
    );

    // Present one captured vector and consume it as one calibration event.
    task automatic send_cal_sample;
        input [29:0] vector;
        input        polarity;
        begin
            safe_d = vector;
            edge_pol = polarity;
            latch_gate = 1'b1; #1;
            latch_gate = 1'b0; #1;
            // E0 captures q_ff; E1..E3 advance the three M_FF pipeline
            // registers. The consume strobe is sampled at E4, when M_FF is
            // stable at the controller input.
            event_valid = 1'b0;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            event_valid = 1'b1;
            clk_probe = 1'b1; #1;
            clk_probe = 1'b0; #1;
            event_valid = 1'b0;
        end
    endtask

    initial begin
        safe_d=30'd0; latch_gate=0; clk_probe=0; reset=1;
        event_valid=0; edge_pol=0; cal_mode=0;
        m_margin_rise=0; m_margin_fall=0;
        #1; reset=0;

        // Invalid and non-calibration events must not advance either epoch.
        safe_d = 30'h2; latch_gate=1; #1; latch_gate=0; #1;
        event_valid=1; cal_mode=0; clk_probe=1; #1; clk_probe=0; #1;
        event_valid=0;
        if (cal_lock !== 1'b0) $fatal(1, "RTL1 lock advanced on invalid mode");

        // RISE M values 1,2,3,4 produce truncating mean 2.
        cal_mode = 1'b1;
        send_cal_sample(30'h00000002, 1'b0);
        send_cal_sample(30'h00000004, 1'b0);
        send_cal_sample(30'h00000008, 1'b0);
        if (cal_lock !== 1'b0) $fatal(1, "RTL1 rise-only lock asserted early");
        send_cal_sample(30'h00000010, 1'b0);
        if (dut.u_backend_ctrl.m_ref_rise_q !== 9'd2)
            $fatal(1, "RTL1 rise mean mismatch ref=%0d sum=%0d count=%0d m=%0d", dut.u_backend_ctrl.m_ref_rise_q, dut.u_backend_ctrl.sum_rise_q, dut.u_backend_ctrl.count_rise_q, dut.u_m_feature.m_ff_o);

        // FALL M values 5,6,7,8 produce truncating mean 6.
        send_cal_sample(30'h00000020, 1'b1);
        send_cal_sample(30'h00000040, 1'b1);
        send_cal_sample(30'h00000080, 1'b1);
        if (cal_lock !== 1'b0) $fatal(1, "RTL1 fall-only lock asserted early");
        send_cal_sample(30'h00000100, 1'b1);
        if (dut.u_backend_ctrl.m_ref_fall_q !== 9'd6 || cal_lock !== 1'b1)
            $fatal(1, "RTL1 fall mean or lock mismatch");

        // A locked epoch is immutable: both references remain unchanged even
        // when later valid calibration-mode events arrive.
        rise_ref_before = dut.u_backend_ctrl.m_ref_rise_q;
        fall_ref_before = dut.u_backend_ctrl.m_ref_fall_q;
        send_cal_sample(30'h20000000, 1'b0);
        send_cal_sample(30'h3fffffff, 1'b1);
        if (dut.u_backend_ctrl.m_ref_rise_q !== rise_ref_before ||
            dut.u_backend_ctrl.m_ref_fall_q !== fall_ref_before || cal_lock !== 1'b1)
            $fatal(1, "RTL1 locked references changed");

        $display("BFE5_RTL1_STARTUP_CALIBRATION_PASS");
        $finish;
    end
endmodule

`default_nettype wire
