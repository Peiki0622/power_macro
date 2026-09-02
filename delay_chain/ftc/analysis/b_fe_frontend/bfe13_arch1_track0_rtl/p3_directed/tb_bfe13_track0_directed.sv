// BFE13 P3 directed TRACK0 regression.
//
// This is simulation-only glue.  The controller instance receives explicit
// M_FF values so every state transition is deterministic; the full-top
// instance separately exercises the unchanged capture/feature pipeline and
// records the E0-to-E7 alarm latency.  The test uses small
// DIRECTED_TEST_ONLY parameter values and never claims production tuning.
`timescale 1ns/1ps
`default_nettype none

module tb_bfe13_track0_directed;
    reg clk;
    reg reset;
    reg event_valid;
    reg edge_pol;
    reg cal_mode;
    reg [8:0] m_ff;
    reg [8:0] margin_rise;
    reg [8:0] margin_fall;
    reg [8:0] t_pos;
    wire cal_lock;
    wire alarm;
    wire sticky;

    // Full-top signals are separate so the controller-level stream can be
    // driven at one event per clock for the stale-reference check.
    reg [29:0] safe_d_top;
    reg latch_gate_top;
    reg clk_top;
    reg reset_top;
    reg event_valid_top;
    reg edge_pol_top;
    reg cal_mode_top;
    reg [8:0] margin_rise_top;
    reg [8:0] margin_fall_top;
    reg [8:0] t_pos_top;
    wire cal_lock_top;
    wire alarm_top;
    wire sticky_top;
    integer log_fd;
    integer edge_count_top;

    // Nonzero values are intentionally local to this directed regression.
    bfe_backend_ctrl_arch1_track0 #(
        .T_TRACK_RISE(5), .T_TRACK_FALL(5),
        .B_TRACK_RISE(2), .B_TRACK_FALL(2)
    ) dut (
        .clk_probe_i(clk), .reset_i(reset), .event_valid_i(event_valid),
        .edge_pol_i(edge_pol), .cal_mode_i(cal_mode), .m_ff_i(m_ff),
        .m_margin_rise_i(margin_rise), .m_margin_fall_i(margin_fall),
        .t_pos_rise_i(t_pos), .cal_lock_o(cal_lock), .droop_alarm_o(alarm),
        .droop_alarm_sticky_o(sticky)
    );

    bfe_backend_arch1_track0_top #(
        .T_TRACK_RISE(5), .T_TRACK_FALL(5),
        .B_TRACK_RISE(2), .B_TRACK_FALL(2)
    ) dut_top (
        .safe_d(safe_d_top), .latch_gate(latch_gate_top), .clk_probe(clk_top),
        .reset(reset_top), .event_valid(event_valid_top),
        .edge_pol(edge_pol_top), .cal_mode(cal_mode_top),
        .m_margin_rise(margin_rise_top), .m_margin_fall(margin_fall_top),
        .t_pos_rise(t_pos_top), .cal_lock(cal_lock_top),
        .droop_alarm(alarm_top), .droop_alarm_sticky(sticky_top)
    );

    task automatic ctrl_clock;
        begin clk = 1'b1; #1; clk = 1'b0; #1; end
    endtask

    // Drive one controller event and stop at its E7 alarm pulse.  One extra
    // edge is deliberately performed by callers when they need the E8 commit.
    task automatic ctrl_event;
        input integer value;
        input integer polarity;
        input integer calibration;
        input integer rise_margin;
        input integer fall_margin;
        input integer threshold;
        begin
            m_ff = value[8:0]; edge_pol = polarity[0]; cal_mode = calibration[0];
            margin_rise = rise_margin[8:0]; margin_fall = fall_margin[8:0];
            t_pos = threshold[8:0]; event_valid = 1'b1;
            ctrl_clock();
            event_valid = 1'b0;
            ctrl_clock(); ctrl_clock(); ctrl_clock();
        end
    endtask

    task automatic ctrl_commit_edge;
        begin ctrl_clock(); end
    endtask

    task automatic top_clock;
        begin clk_top = 1'b1; #1; clk_top = 1'b0; #1; edge_count_top = edge_count_top + 1; end
    endtask

    // Full-top event helper follows the established E0 capture, E1/E2/E3
    // feature advance, E4 consume, and E5/E6/E7 flush sequence.
    task automatic top_event;
        input [29:0] vector;
        input integer expected_m;
        input integer polarity;
        input integer calibration;
        input integer expected_alarm;
        input integer expected_latency;
        integer e0;
        begin
            safe_d_top = vector; edge_pol_top = polarity[0]; cal_mode_top = calibration[0];
            latch_gate_top = 1'b1; #1; latch_gate_top = 1'b0; #1;
            e0 = edge_count_top + 1;
            event_valid_top = 1'b0;
            top_clock(); top_clock(); top_clock(); top_clock();
            event_valid_top = 1'b1; top_clock(); event_valid_top = 1'b0;
            if (dut_top.u_m_feature.m_ff_o !== expected_m[8:0])
                $fatal(1, "P3 full-top M_FF mismatch expected=%0d got=%0d", expected_m, dut_top.u_m_feature.m_ff_o);
            top_clock(); top_clock(); top_clock();
            if (alarm_top !== expected_alarm[0])
                $fatal(1, "P3 full-top alarm mismatch M=%0d expected=%0d got=%0d", expected_m, expected_alarm, alarm_top);
            if (edge_count_top != e0 + expected_latency)
                $fatal(1, "P3 full-top latency mismatch expected=%0d got=%0d", e0 + expected_latency, edge_count_top);
        end
    endtask

    initial begin
        clk = 1'b0; reset = 1'b1; event_valid = 1'b0; edge_pol = 1'b0;
        cal_mode = 1'b0; m_ff = 9'd0; margin_rise = 9'd50; margin_fall = 9'd50; t_pos = 9'd435;
        safe_d_top = 30'd0; latch_gate_top = 1'b0; clk_top = 1'b0; reset_top = 1'b1;
        event_valid_top = 1'b0; edge_pol_top = 1'b0; cal_mode_top = 1'b0;
        margin_rise_top = 9'd22; margin_fall_top = 9'd24; t_pos_top = 9'd435;
        edge_count_top = 0;
        log_fd = $fopen("P3_DIRECTED_TRACE.csv", "w");
        if (log_fd == 0) $fatal(1, "P3 trace could not be opened");
        $fwrite(log_fd, "check,ref_startup_rise,ref_track_rise,ref_startup_fall,ref_track_fall,state_rise,state_fall,alarm,sticky\n");
        #1; reset = 1'b0; reset_top = 1'b0;

        // Controller calibration: RISE=100 and FALL=200, exact sum4>>2.
        ctrl_event(100,0,1,0,0,435); ctrl_event(100,0,1,0,0,435);
        ctrl_event(100,0,1,0,0,435); ctrl_event(100,0,1,0,0,435);
        ctrl_event(200,1,1,0,0,435); ctrl_event(200,1,1,0,0,435);
        ctrl_event(200,1,1,0,0,435); ctrl_event(200,1,1,0,0,435);
        if (!cal_lock || dut.m_ref_startup_rise_q !== 9'd100 || dut.m_ref_track_rise_q !== 9'd100 ||
            dut.m_ref_startup_fall_q !== 9'd200 || dut.m_ref_track_fall_q !== 9'd200)
            $fatal(1, "P3 dual-reference calibration failed");
        if (dut.track_upper_rise_q !== 9'd102 || dut.track_lower_rise_q !== 9'd98 ||
            dut.track_upper_fall_q !== 9'd202 || dut.track_lower_fall_q !== 9'd198)
            $fatal(1, "P3 bound precomputation failed");

        // First/second positive observation: WAIT_POS then exactly +1.
        ctrl_event(102,0,0,50,50,435); ctrl_commit_edge();
        if (dut.track_state_rise_q !== 2'b01 || dut.m_ref_track_rise_q !== 9'd100)
            $fatal(1, "P3 WAIT_POS transition failed");
        ctrl_event(102,0,0,50,50,435); ctrl_commit_edge();
        if (dut.track_state_rise_q !== 2'b00 || dut.m_ref_track_rise_q !== 9'd101)
            $fatal(1, "P3 positive +1 commit failed");

        // Negative symmetry and direction reversal.
        ctrl_event(99,0,0,50,50,435); ctrl_commit_edge();
        if (dut.track_state_rise_q !== 2'b10 || dut.m_ref_track_rise_q !== 9'd101)
            $fatal(1, "P3 WAIT_NEG transition failed");
        ctrl_event(99,0,0,50,50,435); ctrl_commit_edge();
        if (dut.track_state_rise_q !== 2'b00 || dut.m_ref_track_rise_q !== 9'd100)
            $fatal(1, "P3 negative -1 commit failed");
        ctrl_event(102,0,0,50,50,435); ctrl_commit_edge();
        ctrl_event(98,0,0,50,50,435); ctrl_commit_edge();
        if (dut.track_state_rise_q !== 2'b10 || dut.m_ref_track_rise_q !== 9'd100)
            $fatal(1, "P3 reversal did not switch WAIT_POS to WAIT_NEG");

        // Intervening FALL event leaves a pending RISE state untouched.
        ctrl_event(200,1,0,50,50,435); ctrl_commit_edge();
        if (dut.track_state_rise_q !== 2'b10 || dut.track_state_fall_q !== 2'b00)
            $fatal(1, "P3 polarity independence failed");

        // Zero/HOLD behavior clears the selected state without movement.
        ctrl_event(100,0,0,50,50,435); ctrl_commit_edge();
        if (dut.track_state_rise_q !== 2'b00 || dut.m_ref_track_rise_q !== 9'd100)
            $fatal(1, "P3 zero error hold failed");
        ctrl_event(110,0,0,50,50,435); ctrl_commit_edge();
        if (dut.track_state_rise_q !== 2'b00 || dut.m_ref_track_rise_q !== 9'd100)
            $fatal(1, "P3 out-of-range HOLD failed");

        // Bound upper edge: reach 102, then prove no wrap/update beyond it.
        ctrl_event(102,0,0,50,50,435); ctrl_commit_edge();
        ctrl_event(102,0,0,50,50,435); ctrl_commit_edge();
        ctrl_event(102,0,0,50,50,435); ctrl_commit_edge();
        ctrl_event(102,0,0,50,50,435); ctrl_commit_edge();
        if (dut.m_ref_track_rise_q !== 9'd102) $fatal(1, "P3 upper bound reach failed");
        ctrl_event(104,0,0,50,50,435); ctrl_commit_edge();
        ctrl_event(104,0,0,50,50,435); ctrl_commit_edge();
        if (dut.m_ref_track_rise_q !== 9'd102) $fatal(1, "P3 upper bound exceeded");

        // ABS alarm has priority and contributes zero update.
        ctrl_event(104,0,0,1,50,435);
        if (!alarm || !dut.abs_alarm)
            $fatal(1, "P3 ABS alarm priority failed");
        ctrl_commit_edge();
        if (dut.m_ref_track_rise_q !== 9'd102 || dut.track_state_rise_q !== 2'b00)
            $fatal(1, "P3 ABS alarm update was not blocked");

        // Start a clean epoch for signed-only and dual-reference checks.
        reset = 1'b1; #1; reset = 1'b0;
        ctrl_event(100,0,1,0,0,435); ctrl_event(100,0,1,0,0,435);
        ctrl_event(100,0,1,0,0,435); ctrl_event(100,0,1,0,0,435);
        ctrl_event(200,1,1,0,0,435); ctrl_event(200,1,1,0,0,435);
        ctrl_event(200,1,1,0,0,435); ctrl_event(200,1,1,0,0,435);
        // Move tracking reference to 101 while startup anchor remains 100.
        ctrl_event(102,0,0,50,50,435); ctrl_commit_edge();
        ctrl_event(102,0,0,50,50,435); ctrl_commit_edge();
        if (dut.m_ref_track_rise_q !== 9'd101 || dut.m_ref_startup_rise_q !== 9'd100)
            $fatal(1, "P3 dual-reference movement setup failed");
        // D_track=1 is quiet at margin 50, but anchor error=2 trips T_POS=1.
        ctrl_event(102,0,0,50,50,1);
        if (!alarm || dut.abs_alarm || !dut.signed_rise_alarm)
            $fatal(1, "P3 signed-only alarm composition failed");
        ctrl_commit_edge();
        if (dut.m_ref_track_rise_q !== 9'd101 || !sticky)
            $fatal(1, "P3 signed alarm did not block update/set sticky");
        ctrl_event(103,0,0,50,50,435); ctrl_commit_edge();
        if (dut.m_ref_track_rise_q !== 9'd101)
            $fatal(1, "P3 sticky freeze failed");

        // Clean epoch for stale guard and no-bypass test.
        reset = 1'b1; #1; reset = 1'b0;
        ctrl_event(100,0,1,0,0,435); ctrl_event(100,0,1,0,0,435);
        ctrl_event(100,0,1,0,0,435); ctrl_event(100,0,1,0,0,435);
        ctrl_event(200,1,1,0,0,435); ctrl_event(200,1,1,0,0,435);
        ctrl_event(200,1,1,0,0,435); ctrl_event(200,1,1,0,0,435);
        // Prime WAIT_POS, then present two events on consecutive E4 edges.
        ctrl_event(102,0,0,50,50,435); ctrl_commit_edge();
        if (dut.track_state_rise_q !== 2'b01) $fatal(1, "P3 stale setup WAIT_POS failed");
        m_ff=9'd102; edge_pol=1'b0; cal_mode=1'b0; margin_rise=9'd50; margin_fall=9'd50; t_pos=9'd435; event_valid=1'b1; ctrl_clock();
        // This second capture occurs before the first event reaches E8; it
        // must retain the pre-update reference and later be rejected stale.
        ctrl_clock(); event_valid=1'b0; ctrl_clock(); ctrl_clock(); ctrl_clock(); ctrl_clock();
        if (dut.m_ref_track_rise_q !== 9'd101)
            $fatal(1, "P3 stale snapshot guard/no-bypass failed: ref=%0d", dut.m_ref_track_rise_q);

        $fwrite(log_fd, "controller,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",
                dut.m_ref_startup_rise_q, dut.m_ref_track_rise_q,
                dut.m_ref_startup_fall_q, dut.m_ref_track_fall_q,
                dut.track_state_rise_q, dut.track_state_fall_q, alarm, sticky);

        // Full-top calibration and alarm latency.  30'h38010000 produces M=100;
        // 30'h3c100000 produces M=130 and an ABS-only alarm at margin 22.
        top_event(30'h38010000,100,0,1,0,7); top_event(30'h38010000,100,0,1,0,7);
        top_event(30'h38010000,100,0,1,0,7); top_event(30'h38010000,100,0,1,0,7);
        top_event(30'h38010000,100,1,1,0,7); top_event(30'h38010000,100,1,1,0,7);
        top_event(30'h38010000,100,1,1,0,7); top_event(30'h38010000,100,1,1,0,7);
        if (!cal_lock_top) $fatal(1, "P3 full-top calibration did not lock");
        top_event(30'h3c100000,130,0,0,1,7);
        $fclose(log_fd);
        $display("BFE13_TRACK0_P3_DIRECTED_RTL_PASS");
        $finish;
    end
endmodule

`default_nettype wire
