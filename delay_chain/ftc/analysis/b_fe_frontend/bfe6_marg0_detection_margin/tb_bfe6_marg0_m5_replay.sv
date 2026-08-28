// B-FE6-MARG0 M5 ARCH0 replay regression.
//
// The bench drives only the frozen bfe_backend_top ports.  Every non-boundary
// vector is copied from the retained CALN0/M2/M3 q_ff tables; the four
// boundary vectors are deliberately constructed weighted-code values required
// by the M4 strict-comparison check.  No production RTL signal is added.
`timescale 1ns/1ps
`default_nettype none

module bfe6_marg0_m5_replay_tb;
    // Public ARCH0 input ports, documented individually to keep the replay
    // contract reviewable at the testbench boundary.
    reg  [29:0] safe_d;          // 30-bit safe-domain restored capture word.
    reg         latch_gate;      // Active-high transparency control for LATQ.
    reg         clk_probe;       // Probe clock shared by capture and backend.
    reg         reset;           // Active-high asynchronous reset.
    reg         event_valid;     // E4 consume strobe for the captured event.
    reg         edge_pol;        // 0=RISE reference/margin, 1=FALL reference/margin.
    reg         cal_mode;        // 1=calibration sample, 0=locked detection.
    reg  [8:0]  m_margin_rise;   // Strict RISE margin, range 0..435.
    reg  [8:0]  m_margin_fall;   // Strict FALL margin, range 0..435.
    wire        cal_lock;        // High after four valid samples per polarity.
    wire        droop_alarm;     // Registered E7 alarm pulse.
    wire        droop_alarm_sticky; // E8 sticky alarm state.

    integer phase;
    integer cycle;
    integer source_index;
    integer total_events;
    integer consume_count;
    integer alarm_count;
    integer expected_m [0:24];
    integer expected_ref [0:24];
    integer expected_margin [0:24];
    integer expected_pol [0:24];
    integer expected_cal [0:24];
    reg [29:0] stimulus [0:24];

    bfe_backend_top dut (
        .safe_d(safe_d), .latch_gate(latch_gate), .clk_probe(clk_probe),
        .reset(reset), .event_valid(event_valid), .edge_pol(edge_pol),
        .cal_mode(cal_mode), .m_margin_rise(m_margin_rise),
        .m_margin_fall(m_margin_fall), .cal_lock(cal_lock),
        .droop_alarm(droop_alarm), .droop_alarm_sticky(droop_alarm_sticky)
    );

    always #5 clk_probe = ~clk_probe;

    // Populate one replay epoch.  The first epoch uses seed 41001 (RISE
    // reference 220, FALL reference 180); the second uses seed 41002 (RISE
    // reference 330, FALL reference 273).  q_ff strings in the evidence are
    // tap-29..tap-0 display strings, so their binary values are direct safe_d
    // words and their weighted sums are the expected M values below.
    task automatic initialize_epoch;
        input integer selected_phase;
        integer i;
        begin
            for (i = 0; i < 25; i = i + 1) begin
                stimulus[i] = 30'd0;
                expected_m[i] = 0;
                expected_ref[i] = 0;
                expected_margin[i] = 0;
                expected_pol[i] = 0;
                expected_cal[i] = 0;
            end
            if (selected_phase == 0) begin
                // Four identical retained healthy calibration samples per
                // polarity are intentional: CALN0 showed deterministic codes.
                for (i = 0; i < 4; i = i + 1) begin
                    stimulus[i] = 30'h03ff8000; expected_m[i] = 220;
                    expected_ref[i] = 220; expected_cal[i] = 1; expected_pol[i] = 0;
                    stimulus[i+4] = 30'h01ff0000; expected_m[i+4] = 180;
                    expected_ref[i+4] = 180; expected_cal[i+4] = 1; expected_pol[i+4] = 1;
                end
                // Seed 41001 retained normal/droop vectors and explicit M4
                // boundary vectors.  Events are intentionally back-to-back.
                stimulus[8] = 30'h03ff8000; expected_m[8] = 220; expected_ref[8] = 220; expected_pol[8] = 0;
                stimulus[9] = 30'h00ffe000; expected_m[9] = 198; expected_ref[9] = 220; expected_pol[9] = 0; expected_margin[9] = 7;
                stimulus[10] = 30'h3fe00005; expected_m[10] = 227; expected_ref[10] = 220; expected_pol[10] = 0; expected_margin[10] = 7;
                stimulus[11] = 30'h3fe00009; expected_m[11] = 228; expected_ref[11] = 220; expected_pol[11] = 0; expected_margin[11] = 7;
                stimulus[12] = 30'h01ff0000; expected_m[12] = 180; expected_ref[12] = 180; expected_pol[12] = 1;
                stimulus[13] = 30'h00ffc000; expected_m[13] = 185; expected_ref[13] = 180; expected_pol[13] = 1; expected_margin[13] = 3;
                stimulus[14] = 30'h3f800003; expected_m[14] = 183; expected_ref[14] = 180; expected_pol[14] = 1; expected_margin[14] = 3;
                stimulus[15] = 30'h3f800005; expected_m[15] = 184; expected_ref[15] = 180; expected_pol[15] = 1; expected_margin[15] = 3;
                // Captured FALL 0.89/0.86 V vectors exercise larger response.
                stimulus[16] = 30'h000ff800; expected_m[16] = 135; expected_ref[16] = 180; expected_pol[16] = 1; expected_margin[16] = 3;
                stimulus[17] = 30'h000ff800; expected_m[17] = 135; expected_ref[17] = 220; expected_pol[17] = 0; expected_margin[17] = 7;
                stimulus[18] = 30'h000ff800; expected_m[18] = 135; expected_ref[18] = 220; expected_pol[18] = 0; expected_margin[18] = 7;
                stimulus[19] = 30'h000ff800; expected_m[19] = 135; expected_ref[19] = 180; expected_pol[19] = 1; expected_margin[19] = 3;
                total_events = 20;
            end else begin
                // Four retained seed-41002 healthy samples per polarity.
                for (i = 0; i < 4; i = i + 1) begin
                    stimulus[i] = 30'h3fff8000; expected_m[i] = 330;
                    expected_ref[i] = 330; expected_cal[i] = 1; expected_pol[i] = 0;
                    stimulus[i+4] = 30'h0fff8000; expected_m[i+4] = 273;
                    expected_ref[i+4] = 273; expected_cal[i+4] = 1; expected_pol[i+4] = 1;
                end
                // Seed 41002 normal, shallow droop, and reverse-direction
                // FALL response overlap the same pipeline at one event/clock.
                stimulus[8] = 30'h3fff8000; expected_m[8] = 330; expected_ref[8] = 330; expected_pol[8] = 0;
                stimulus[9] = 30'h0fffc000; expected_m[9] = 287; expected_ref[9] = 330; expected_pol[9] = 0; expected_margin[9] = 7;
                stimulus[10] = 30'h03ffe000; expected_m[10] = 247; expected_ref[10] = 273; expected_pol[10] = 1; expected_margin[10] = 3;
                stimulus[11] = 30'h007ffc00; expected_m[11] = 208; expected_ref[11] = 273; expected_pol[11] = 1; expected_margin[11] = 3;
                total_events = 12;
            end
            // The four required boundaries are constructed from legal tap
            // bits and are checked against weighted M values by this bench.
            for (i = 0; i < total_events; i = i + 1)
                if (expected_m[i] != 0 && expected_m[i] > 435)
                    $fatal(1, "invalid replay M index=%0d", i);
        end
    endtask

    // Run one complete epoch with E0 capture and E4 consume separated by the
    // frozen four-edge parcel latency.  Alarm checking is delayed seven edges
    // to E7, while the sticky output is checked after the stream drains.
    task automatic run_epoch;
        input integer selected_phase;
        integer expected_alarm;
        begin
            initialize_epoch(selected_phase);
            safe_d = 30'd0; latch_gate = 1'b1; event_valid = 1'b0;
            edge_pol = 1'b0; cal_mode = 1'b0; m_margin_rise = 9'd0;
            m_margin_fall = 9'd0; consume_count = 0; alarm_count = 0;
            reset = 1'b1; #2; reset = 1'b0;

            for (cycle = 0; cycle < total_events + 14; cycle = cycle + 1) begin
                @(negedge clk_probe);
                if (cycle < total_events) safe_d = stimulus[cycle];
                else safe_d = 30'd0;
                source_index = cycle - 4;
                event_valid = (source_index >= 0 && source_index < total_events);
                if (event_valid) begin
                    edge_pol = expected_pol[source_index];
                    cal_mode = expected_cal[source_index];
                    m_margin_rise = (!expected_pol[source_index]) ? expected_margin[source_index] : 9'd0;
                    m_margin_fall = (expected_pol[source_index]) ? expected_margin[source_index] : 9'd0;
                end else begin
                    edge_pol = 1'b0; cal_mode = 1'b0;
                    m_margin_rise = 9'd0; m_margin_fall = 9'd0;
                end
                @(posedge clk_probe); #1;
                if (event_valid) begin
                    consume_count = consume_count + 1;
                    if (dut.u_backend_ctrl.event_m_q !== expected_m[source_index][8:0])
                        $fatal(1, "M5 event M mismatch phase=%0d event=%0d expected=%0d got=%0d", selected_phase, source_index, expected_m[source_index], dut.u_backend_ctrl.event_m_q);
                    // During calibration the selected reference is not valid
                    // yet; compare it only for locked detection events.
                    if (!expected_cal[source_index] &&
                        dut.u_backend_ctrl.event_ref_q !== expected_ref[source_index][8:0])
                        $fatal(1, "M5 event reference mismatch phase=%0d event=%0d", selected_phase, source_index);
                end
                if (cycle >= 7) begin
                    source_index = cycle - 7;
                    expected_alarm = (source_index >= 0 && source_index < total_events && !expected_cal[source_index]) ?
                        ((expected_m[source_index] - expected_ref[source_index] < 0) ?
                         (expected_ref[source_index] - expected_m[source_index] > expected_margin[source_index]) :
                         (expected_m[source_index] - expected_ref[source_index] > expected_margin[source_index])) : 0;
                    if (droop_alarm !== expected_alarm[0])
                        $fatal(1, "M5 E7 mismatch phase=%0d event=%0d expected=%0d got=%0d delta=%0d margin=%0d", selected_phase, source_index, expected_alarm, droop_alarm, dut.u_backend_ctrl.delta_q, dut.u_backend_ctrl.alarm_margin_q);
                    if (droop_alarm) alarm_count = alarm_count + 1;
                end
            end

            if (consume_count != total_events)
                $fatal(1, "M5 consume count mismatch phase=%0d expected=%0d got=%0d", selected_phase, total_events, consume_count);
            if (!cal_lock)
                $fatal(1, "M5 CAL_LOCK missing phase=%0d", selected_phase);
            if (selected_phase == 0) begin
                if (dut.u_backend_ctrl.m_ref_rise_q !== 9'd220 || dut.u_backend_ctrl.m_ref_fall_q !== 9'd180)
                    $fatal(1, "M5 seed41001 references mismatch rise=%0d fall=%0d", dut.u_backend_ctrl.m_ref_rise_q, dut.u_backend_ctrl.m_ref_fall_q);
                if (alarm_count != 8 || !droop_alarm_sticky)
                    $fatal(1, "M5 seed41001 alarm/sticky mismatch count=%0d sticky=%b", alarm_count, droop_alarm_sticky);
            end else begin
                if (dut.u_backend_ctrl.m_ref_rise_q !== 9'd330 || dut.u_backend_ctrl.m_ref_fall_q !== 9'd273)
                    $fatal(1, "M5 seed41002 references mismatch rise=%0d fall=%0d", dut.u_backend_ctrl.m_ref_rise_q, dut.u_backend_ctrl.m_ref_fall_q);
                if (alarm_count != 3 || !droop_alarm_sticky)
                    $fatal(1, "M5 seed41002 alarm/sticky mismatch count=%0d sticky=%b", alarm_count, droop_alarm_sticky);
            end
        end
    endtask

    initial begin
        safe_d = 30'd0; latch_gate = 1'b1; clk_probe = 1'b0; reset = 1'b1;
        event_valid = 1'b0; edge_pol = 1'b0; cal_mode = 1'b0;
        m_margin_rise = 9'd0; m_margin_fall = 9'd0;
        #1;
        run_epoch(0);
        run_epoch(1);
        $display("BFE6_MARG0_M5_RTL_REPLAY_PASS");
        $finish;
    end
endmodule

`default_nettype wire
