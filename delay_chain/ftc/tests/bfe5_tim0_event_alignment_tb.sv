// B-FE5-TIM0 event/cycle contract regression.
//
// The stimulus is intentionally one event per probe-clock cycle.  A small
// delayed input scoreboard models the frozen interface contract: the word
// captured at E0 is consumed four edges later, when P3/M_FF is stable.  The
// bench reaches internal registers hierarchically only as verification
// observability; no RTL debug port or new functional signal is introduced.
`timescale 1ns/1ps
`default_nettype none

module bfe5_tim0_event_alignment_tb;
    localparam integer CAL_EVENTS = 8;
    localparam integer DET_EVENTS = 4;
    localparam integer PIPELINE_LATENCY = 4;
    localparam integer ALARM_LATENCY = 7;
    localparam integer TOTAL_EVENTS = CAL_EVENTS + DET_EVENTS;
    localparam integer FLUSH_EDGES = ALARM_LATENCY + 2;

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

    // Each vector has an exact weighted sum.  The selected single/two/three
    // bit combinations make the expected M values obvious and reproducible:
    // 10,20,30,40 for RISE and 50,60,70,80 for FALL calibration.
    reg [29:0] stimulus [0:TOTAL_EVENTS-1];
    integer    expected_m [0:TOTAL_EVENTS-1];
    reg        expected_pol [0:TOTAL_EVENTS-1];
    integer    expected_margin [0:TOTAL_EVENTS-1];
    integer    cycle;
    integer    source_index;
    integer    consume_count;
    integer    alarm_count;
    integer    expected_alarm;

    bfe_backend_top dut (
        .safe_d(safe_d), .latch_gate(latch_gate), .clk_probe(clk_probe),
        .reset(reset), .event_valid(event_valid), .edge_pol(edge_pol),
        .cal_mode(cal_mode), .m_margin_rise(m_margin_rise),
        .m_margin_fall(m_margin_fall), .cal_lock(cal_lock),
        .droop_alarm(droop_alarm), .droop_alarm_sticky(droop_alarm_sticky)
    );

    always #5 clk_probe = ~clk_probe;

    function automatic integer expected_reference;
        input integer index;
        begin
            if (index < CAL_EVENTS) expected_reference = (index < 4) ? 25 : 65;
            else if (expected_pol[index]) expected_reference = 65;
            else expected_reference = 25;
        end
    endfunction

    // The alarm is observed seven edges after E0: four to consume, one to
    // register event_valid, one for P4a, and one for P4b/delta_valid.
    function automatic integer alarm_for_event;
        input integer index;
        integer delta;
        begin
            if (index < CAL_EVENTS) begin
                alarm_for_event = 0;
            end else begin
                delta = expected_m[index] - expected_reference(index);
                if (delta < 0) delta = -delta;
                alarm_for_event = (delta > expected_margin[index]);
            end
        end
    endfunction

    initial begin
        // Calibration RISE: M=10,20,30,40 -> 25. FALL: 50,60,70,80 -> 65.
        stimulus[0] = 30'h00000400; expected_m[0] = 10; expected_pol[0] = 0;
        stimulus[1] = 30'h00100000; expected_m[1] = 20; expected_pol[1] = 0;
        stimulus[2] = 30'h20000002; expected_m[2] = 30; expected_pol[2] = 0;
        stimulus[3] = 30'h20000800; expected_m[3] = 40; expected_pol[3] = 0;
        stimulus[4] = 30'h20200000; expected_m[4] = 50; expected_pol[4] = 1;
        stimulus[5] = 30'h30000008; expected_m[5] = 60; expected_pol[5] = 1;
        stimulus[6] = 30'h30002000; expected_m[6] = 70; expected_pol[6] = 1;
        stimulus[7] = 30'h30800000; expected_m[7] = 80; expected_pol[7] = 1;

        // Detection A/B/C/D deliberately alternates polarity and uses
        // distinct margins.  A and C are RISE alarms; B is a quiet FALL
        // equality case; D is a FALL alarm.  The stream overlaps every
        // detector stage, so a context shift would visibly change a result.
        stimulus[8] = 30'h20000002; expected_m[8] = 30; expected_pol[8] = 0; expected_margin[8] = 4;
        stimulus[9] = 30'h30000008; expected_m[9] = 60; expected_pol[9] = 1; expected_margin[9] = 5;
        stimulus[10] = 30'h00100000; expected_m[10] = 20; expected_pol[10] = 0; expected_margin[10] = 3;
        stimulus[11] = 30'h30800000; expected_m[11] = 80; expected_pol[11] = 1; expected_margin[11] = 10;

        safe_d = 30'd0; latch_gate = 1'b1; clk_probe = 1'b0;
        reset = 1'b1; event_valid = 1'b0; edge_pol = 1'b0; cal_mode = 1'b0;
        m_margin_rise = 9'd0; m_margin_fall = 9'd0;
        #2; reset = 1'b0;
        consume_count = 0;
        alarm_count = 0;

        // Keep LATQ transparent throughout the stream.  The safe-domain word
        // is changed only on falling edges, so each following rising edge is
        // a clean E0 capture and no latch-close protocol is hidden in TIM0.
        for (cycle = 0; cycle < TOTAL_EVENTS + PIPELINE_LATENCY + FLUSH_EDGES; cycle = cycle + 1) begin
            @(negedge clk_probe);
            if (cycle < TOTAL_EVENTS) safe_d = stimulus[cycle];
            else safe_d = 30'd0;

            source_index = cycle - PIPELINE_LATENCY;
            event_valid = (source_index >= 0 && source_index < TOTAL_EVENTS);
            if (event_valid) begin
                edge_pol = expected_pol[source_index];
                cal_mode = (source_index < CAL_EVENTS);
                m_margin_rise = (source_index >= CAL_EVENTS && !expected_pol[source_index]) ? expected_margin[source_index] : 9'd0;
                m_margin_fall = (source_index >= CAL_EVENTS && expected_pol[source_index]) ? expected_margin[source_index] : 9'd0;
            end else begin
                edge_pol = 1'b0; cal_mode = 1'b0;
                m_margin_rise = 9'd0; m_margin_fall = 9'd0;
            end

            @(posedge clk_probe);
            #1;
            if (event_valid) begin
                consume_count = consume_count + 1;
                // E4 event_valid is paired with the stable P3 value and the
                // same event's polarity/margin context at this edge.
                if (dut.u_backend_ctrl.event_m_q !== expected_m[source_index][8:0])
                    $fatal(1, "TIM0 M parcel error cycle=%0d event=%0d expected=%0d got=%0d", cycle, source_index, expected_m[source_index], dut.u_backend_ctrl.event_m_q);
                if (dut.u_backend_ctrl.event_margin_q !== ((expected_pol[source_index]) ? m_margin_fall : m_margin_rise))
                    $fatal(1, "TIM0 margin parcel error cycle=%0d event=%0d", cycle, source_index);
                if (!cal_mode && dut.u_backend_ctrl.event_ref_q !== expected_reference(source_index)[8:0])
                    $fatal(1, "TIM0 reference/polarity parcel error cycle=%0d event=%0d expected=%0d got=%0d", cycle, source_index, expected_reference(source_index), dut.u_backend_ctrl.event_ref_q);
            end

            if (cycle >= ALARM_LATENCY) begin
                source_index = cycle - ALARM_LATENCY;
                expected_alarm = (source_index >= 0 && source_index < TOTAL_EVENTS) ? alarm_for_event(source_index) : 0;
                if (droop_alarm !== expected_alarm[0])
                    $fatal(1, "BFE5_TIM0_STOP alarm/context misalignment cycle=%0d event=%0d expected_alarm=%0d got=%0d delta=%0d sub_margin=%0d; RTL margin parcel is not aligned through P4b", cycle, source_index, expected_alarm, droop_alarm, dut.u_backend_ctrl.delta_q, dut.u_backend_ctrl.sub_margin_q);
                if (droop_alarm) alarm_count = alarm_count + 1;
            end
        end

        if (consume_count != TOTAL_EVENTS)
            $fatal(1, "TIM0 calibration/detection consume count mismatch expected=%0d got=%0d", TOTAL_EVENTS, consume_count);
        if (dut.u_backend_ctrl.count_rise_q !== 3'd3 || dut.u_backend_ctrl.count_fall_q !== 3'd3 ||
            dut.u_backend_ctrl.m_ref_rise_q !== 9'd25 || dut.u_backend_ctrl.m_ref_fall_q !== 9'd65 ||
            cal_lock !== 1'b1)
            $fatal(1, "TIM0 calibration overlap error rise_ref=%0d fall_ref=%0d counts=%0d/%0d lock=%b", dut.u_backend_ctrl.m_ref_rise_q, dut.u_backend_ctrl.m_ref_fall_q, dut.u_backend_ctrl.count_rise_q, dut.u_backend_ctrl.count_fall_q, cal_lock);
        if (alarm_count != 3 || droop_alarm_sticky !== 1'b1)
            $fatal(1, "TIM0 detector throughput/alarm count error expected=3 got=%0d sticky=%b", alarm_count, droop_alarm_sticky);

        $display("BFE5_TIM0_EVENT_ALIGNMENT_PASS");
        $display("BFE5_TIM0_PIPELINE_THROUGHPUT_PASS");
        $finish;
    end
endmodule

`default_nettype wire
