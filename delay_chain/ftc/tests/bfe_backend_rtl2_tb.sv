// RTL2 self-checking detector regression.
//
// The bench deliberately separates capture and consume clocks.  This models
// the ARCH0 contract that event_valid qualifies the M_FF value captured by the
// preceding probe-clock edge, avoiding a same-edge race between the 30 DFFs
// and the backend controller.
`timescale 1ns/1ps
`default_nettype none

module bfe_backend_rtl2_tb;
    reg [29:0] safe_d;
    reg        latch_gate, clk_probe, reset;
    reg        event_valid, edge_pol, cal_mode;
    reg [8:0]  m_margin_rise, m_margin_fall;
    wire       cal_lock, droop_alarm, droop_alarm_sticky;
    integer    k;

    bfe_backend_top dut (
        .safe_d(safe_d), .latch_gate(latch_gate), .clk_probe(clk_probe),
        .reset(reset), .event_valid(event_valid), .edge_pol(edge_pol),
        .cal_mode(cal_mode), .m_margin_rise(m_margin_rise),
        .m_margin_fall(m_margin_fall), .cal_lock(cal_lock),
        .droop_alarm(droop_alarm), .droop_alarm_sticky(droop_alarm_sticky)
    );

    // Capture vector, advance the three M_FF stages, then consume at E4.
    task automatic send_event;
        input [29:0] vector;
        input        polarity;
        input        calibration;
        begin
            safe_d = vector; edge_pol = polarity; cal_mode = calibration;
            latch_gate = 1'b1; #1; latch_gate = 1'b0; #1;
            event_valid = 1'b0; clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            event_valid = 1'b1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            event_valid = 1'b0;
            // P4a/P4b align the split subtraction and delta register.
            // Returning after three idle edges makes droop_alarm observable;
            // sticky is checked after one additional edge.
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
        end
    endtask

    initial begin
        safe_d=0; latch_gate=0; clk_probe=0; reset=1;
        event_valid=0; edge_pol=0; cal_mode=0; m_margin_rise=0; m_margin_fall=0;
        #1; reset=0;

        // Before calibration lock, normal events are explicitly invalid.
        send_event(30'h00000002, 1'b0, 1'b0);
        if (droop_alarm !== 1'b0 || droop_alarm_sticky !== 1'b0)
            $fatal(1, "RTL2 alarm asserted before calibration lock");

        // Startup references: RISE mean=(1+2+3+4)>>2=2; FALL mean=6.
        cal_mode=1'b1;
        send_event(30'h00000002, 1'b0, 1'b1);
        send_event(30'h00000004, 1'b0, 1'b1);
        send_event(30'h00000008, 1'b0, 1'b1);
        send_event(30'h00000010, 1'b0, 1'b1);
        send_event(30'h00000020, 1'b1, 1'b1);
        send_event(30'h00000040, 1'b1, 1'b1);
        send_event(30'h00000080, 1'b1, 1'b1);
        send_event(30'h00000100, 1'b1, 1'b1);
        if (cal_lock !== 1'b1) $fatal(1, "RTL2 calibration did not lock");

        // Strict threshold: delta=2 is quiet at margin=2, but alarms at 1.
        cal_mode=1'b0; edge_pol=1'b0; m_margin_rise=9'd2;
        send_event(30'h00000010, 1'b0, 1'b0);
        if (droop_alarm !== 1'b0 || droop_alarm_sticky !== 1'b0)
            $fatal(1, "RTL2 equality threshold incorrectly alarmed");
        m_margin_rise=9'd1;
        send_event(30'h00000010, 1'b0, 1'b0);
        // The task returns after E5, when the registered alarm pulse is valid.
        if (droop_alarm !== 1'b1) $fatal(1, "RTL2 rise alarm pulse missing");
        // One further edge advances the registered pulse into sticky state.
        clk_probe=1'b1; #1; clk_probe=1'b0; #1;
        if (droop_alarm_sticky !== 1'b1)
            $fatal(1, "RTL2 rise alarm did not set sticky");

        // FALL polarity uses its independent reference and margin.
        m_margin_fall=9'd2; edge_pol=1'b1;
        send_event(30'h00000100, 1'b1, 1'b0);
        if (droop_alarm !== 1'b0) $fatal(1, "RTL2 fall equality alarmed");
        m_margin_fall=9'd1;
        send_event(30'h00000100, 1'b1, 1'b0);
        if (droop_alarm !== 1'b1 || droop_alarm_sticky !== 1'b1)
            $fatal(1, "RTL2 fall alarm or sticky behavior failed");

        // Calibration-mode and invalid events never produce a current alarm.
        cal_mode=1'b1; m_margin_fall=0;
        send_event(30'h3fffffff, 1'b1, 1'b1);
        if (droop_alarm !== 1'b0 || droop_alarm_sticky !== 1'b1)
            $fatal(1, "RTL2 calibration event affected alarm outputs");

        // Reset is the only sticky clear mechanism.
        reset=1'b1; #1;
        if (cal_lock !== 1'b0 || droop_alarm_sticky !== 1'b0)
            $fatal(1, "RTL2 reset did not clear lock/sticky");
        $display("BFE5_RTL2_MINIMAL_DETECTOR_PASS");
        $finish;
    end
endmodule

`default_nettype wire
