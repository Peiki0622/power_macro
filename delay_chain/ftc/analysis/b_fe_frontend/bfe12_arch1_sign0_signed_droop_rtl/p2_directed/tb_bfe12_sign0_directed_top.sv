// BFE12 P2 directed full-top regression.
//
// The bench uses deterministic safe_d words whose weighted tap sums are known
// exactly.  It drives the same capture/feature/consume timing discipline as
// bfe_backend_rtl2_tb, while checking the candidate-only signed-RISE branch
// at its internal named nets for causal visibility.  This file is simulation
// glue only; it is never part of the synthesizable RTL.
`timescale 1ns/1ps
`default_nettype none

module tb_bfe12_sign0_directed_top;
    // Public candidate-top stimulus and status signals.
    reg [29:0] safe_d;
    reg        latch_gate;
    reg        clk_probe;
    reg        reset;
    reg        event_valid;
    reg        edge_pol;
    reg        cal_mode;
    reg [8:0]  m_margin_rise;
    reg [8:0]  m_margin_fall;
    reg [8:0]  t_pos_rise;
    wire       cal_lock;
    wire       droop_alarm;
    wire       droop_alarm_sticky;

    // Probe-edge counter provides an explicit E0/E7 cycle table without
    // changing the DUT interface.  The first capture edge is E0 and the
    // expected registered alarm edge is exactly seven probe edges later.
    integer probe_edges;
    integer capture_edge;
    integer alarm_edge;
    integer alarm_fd;

    bfe_backend_arch1_sign0_top dut (
        .safe_d(safe_d),
        .latch_gate(latch_gate),
        .clk_probe(clk_probe),
        .reset(reset),
        .event_valid(event_valid),
        .edge_pol(edge_pol),
        .cal_mode(cal_mode),
        .m_margin_rise(m_margin_rise),
        .m_margin_fall(m_margin_fall),
        .t_pos_rise(t_pos_rise),
        .cal_lock(cal_lock),
        .droop_alarm(droop_alarm),
        .droop_alarm_sticky(droop_alarm_sticky)
    );

    // One complete probe edge.  The #1 delay lets nonblocking assignments and
    // the behavioral LATQ/DFF elaboration stubs settle before observations.
    task automatic probe_edge;
        begin
            clk_probe = 1'b1;
            #1;
            clk_probe = 1'b0;
            #1;
            probe_edges = probe_edges + 1;
        end
    endtask

    // Capture one vector, consume it at E4, flush through E7, and check both
    // the public alarm and the two causal internal alarm terms.  The task
    // arguments are expected values derived from the frozen strict rules.
    task automatic send_event;
        input [29:0] vector;
        input        polarity;
        input        calibration;
        input [8:0]  expected_m;
        input        expected_alarm;
        input        expected_abs_alarm;
        input        expected_signed_alarm;
        input [8:0]  expected_ref;
        input [8:0]  threshold;
        begin
            safe_d = vector;
            edge_pol = polarity;
            cal_mode = calibration;
            t_pos_rise = threshold;
            latch_gate = 1'b1;
            #1;
            latch_gate = 1'b0;
            #1;

            // E0 capture followed by E1/E2/E3 feature-pipeline advances.
            capture_edge = probe_edges + 1;
            event_valid = 1'b0;
            probe_edge();
            probe_edge();
            probe_edge();
            probe_edge();

            // E4 consumes the stable M_FF and samples event context.
            event_valid = 1'b1;
            probe_edge();
            event_valid = 1'b0;
            if (dut.u_m_feature.m_ff_o !== expected_m)
                $fatal(1, "P2 M_FF mismatch expected=%0d got=%0d", expected_m, dut.u_m_feature.m_ff_o);
            if (dut.u_backend_ctrl.event_m_q !== expected_m)
                $fatal(1, "P2 event M parcel mismatch expected=%0d got=%0d", expected_m, dut.u_backend_ctrl.event_m_q);
            if (!calibration && dut.u_backend_ctrl.event_ref_q !== expected_ref)
                $fatal(1, "P2 reference parcel mismatch expected=%0d got=%0d", expected_ref, dut.u_backend_ctrl.event_ref_q);

            // E5, E6, E7 complete P4a/P4b and expose the registered alarm.
            probe_edge();
            probe_edge();
            probe_edge();
            alarm_edge = probe_edges;
            if (droop_alarm !== expected_alarm)
                $fatal(1, "P2 alarm mismatch E0=%0d E7=%0d expected=%b got=%b delta=%0d margin=%0d t_pos=%0d pol=%b dir=%b abs=%b signed=%b", capture_edge, alarm_edge, expected_alarm, droop_alarm, dut.u_backend_ctrl.delta_q, dut.u_backend_ctrl.alarm_margin_q, dut.u_backend_ctrl.alarm_t_pos_rise_q, dut.u_backend_ctrl.alarm_edge_pol_q, dut.u_backend_ctrl.alarm_dir_q, dut.u_backend_ctrl.abs_alarm, dut.u_backend_ctrl.signed_rise_alarm);
            if (dut.u_backend_ctrl.abs_alarm !== expected_abs_alarm)
                $fatal(1, "P2 ABS term mismatch expected=%b got=%b", expected_abs_alarm, dut.u_backend_ctrl.abs_alarm);
            if (dut.u_backend_ctrl.signed_rise_alarm !== expected_signed_alarm)
                $fatal(1, "P2 signed term mismatch expected=%b got=%b", expected_signed_alarm, dut.u_backend_ctrl.signed_rise_alarm);
            if (alarm_edge != capture_edge + 7)
                $fatal(1, "P2 latency changed expected E7=%0d got=%0d", capture_edge + 7, alarm_edge);
            $fwrite(alarm_fd, "%0d,%0d,%0d,%0d,%0d,%0d\n", capture_edge, alarm_edge,
                    expected_m, expected_alarm, expected_abs_alarm, expected_signed_alarm);
        end
    endtask

    initial begin
        // M=100 calibration word: tap-index weights 29+28+27+16.
        // Other words below add one weighted tap to create exact signed edges.
        safe_d = 30'd0;
        latch_gate = 1'b0;
        clk_probe = 1'b0;
        reset = 1'b1;
        event_valid = 1'b0;
        edge_pol = 1'b0;
        cal_mode = 1'b0;
        m_margin_rise = 9'd22;
        m_margin_fall = 9'd24;
        t_pos_rise = 9'd18;
        probe_edges = 0;
        alarm_fd = $fopen("P2_DIRECTED_CYCLE_TABLE.csv", "w");
        if (alarm_fd == 0) $fatal(1, "P2 cycle table could not be opened");
        $fwrite(alarm_fd, "e0_capture,e7_alarm,m_ff,alarm,abs_alarm,signed_rise_alarm\n");
        #1;
        reset = 1'b0;

        // Before CAL_LOCK, a normal RISE event is invalid and must be quiet.
        send_event(30'h38010000, 1'b0, 1'b0, 9'd100, 1'b0, 1'b0, 1'b0, 9'd0, 9'd18);
        if (cal_lock !== 1'b0 || droop_alarm_sticky !== 1'b0)
            $fatal(1, "P2 pre-lock event changed lock or sticky state");

        // Four RISE samples and four FALL samples establish exact reference
        // 100 using (100+100+100+100)>>2.  Calibration events cannot alarm.
        cal_mode = 1'b1;
        send_event(30'h38010000, 1'b0, 1'b1, 9'd100, 1'b0, 1'b0, 1'b0, 9'd0, 9'd18);
        send_event(30'h38010000, 1'b0, 1'b1, 9'd100, 1'b0, 1'b0, 1'b0, 9'd0, 9'd18);
        send_event(30'h38010000, 1'b0, 1'b1, 9'd100, 1'b0, 1'b0, 1'b0, 9'd0, 9'd18);
        send_event(30'h38010000, 1'b0, 1'b1, 9'd100, 1'b0, 1'b0, 1'b0, 9'd0, 9'd18);
        send_event(30'h38010000, 1'b1, 1'b1, 9'd100, 1'b0, 1'b0, 1'b0, 9'd0, 9'd18);
        send_event(30'h38010000, 1'b1, 1'b1, 9'd100, 1'b0, 1'b0, 1'b0, 9'd0, 9'd18);
        send_event(30'h38010000, 1'b1, 1'b1, 9'd100, 1'b0, 1'b0, 1'b0, 9'd0, 9'd18);
        send_event(30'h38010000, 1'b1, 1'b1, 9'd100, 1'b0, 1'b0, 1'b0, 9'd0, 9'd18);
        if (cal_lock !== 1'b1 || dut.u_backend_ctrl.m_ref_rise_q !== 9'd100 ||
            dut.u_backend_ctrl.m_ref_fall_q !== 9'd100)
            $fatal(1, "P2 calibration mismatch lock=%b refs=%0d/%0d", cal_lock,
                   dut.u_backend_ctrl.m_ref_rise_q, dut.u_backend_ctrl.m_ref_fall_q);

        cal_mode = 1'b0;
        // At T=18, e=+18 is quiet and e=+19 is signed-only alarm.
        send_event(30'h38050000, 1'b0, 1'b0, 9'd118, 1'b0, 1'b0, 1'b0, 9'd100, 9'd18);
        send_event(30'h38090000, 1'b0, 1'b0, 9'd119, 1'b1, 1'b0, 1'b1, 9'd100, 9'd18);
        // Sticky is defined at E8: it observes the preceding E7 pulse on the
        // next probe edge, so advance once before checking the state.
        probe_edge();
        if (droop_alarm_sticky !== 1'b1) $fatal(1, "P2 signed-only alarm did not set sticky");

        // At T=19, e=+19 is quiet and e=+20 is signed-only alarm.
        send_event(30'h38090000, 1'b0, 1'b0, 9'd119, 1'b0, 1'b0, 1'b0, 9'd100, 9'd19);
        send_event(30'h38110000, 1'b0, 1'b0, 9'd120, 1'b1, 1'b0, 1'b1, 9'd100, 9'd19);

        // Negative RISE e=-30 must not enter signed-RISE.  Margin 31 keeps
        // the inherited ABS branch quiet so the sign gate is isolated.
        m_margin_rise = 9'd31;
        send_event(30'h30002000, 1'b0, 1'b0, 9'd70, 1'b0, 1'b0, 1'b0, 9'd100, 9'd18);
        m_margin_rise = 9'd22;

        // FALL positive e=+20 is outside the RISE signed branch and is quiet
        // at the frozen FALL absolute margin of 24.
        send_event(30'h38110000, 1'b1, 1'b0, 9'd120, 1'b0, 1'b0, 1'b0, 9'd100, 9'd18);

        // Absolute comparator remains active for positive/negative excursions
        // and quiet at exact equality e=+22.
        send_event(30'h38410000, 1'b0, 1'b0, 9'd122, 1'b0, 1'b0, 1'b0, 9'd100, 9'd435);
        send_event(30'h3c100000, 1'b0, 1'b0, 9'd130, 1'b1, 1'b1, 1'b0, 9'd100, 9'd435);
        send_event(30'h30002000, 1'b0, 1'b0, 9'd70, 1'b1, 1'b1, 1'b0, 9'd100, 9'd435);

        // Reset is the only sticky clear mechanism.
        reset = 1'b1;
        #1;
        if (cal_lock !== 1'b0 || droop_alarm_sticky !== 1'b0)
            $fatal(1, "P2 reset failed to clear lock/sticky");
        $fclose(alarm_fd);
        $display("BFE12_SIGN0_P2_DIRECTED_TOP_RTL_PASS");
        $finish;
    end
endmodule

`default_nettype wire
