// ============================================================================
// Phase 9 R1 1 GHz synthesized-controller diagnostic testbench
//
// This bench is verification-only.  It deliberately keeps the transistor
// sensor out of the run and connects the mapped controller to the existing
// behavioral sensor oracle.  The purpose is to prove that the copied
// synthesized controller still implements the frozen 1 ns Phase 1 protocol
// before any VCS-XA electrical boundary is exercised.
//
// No signal owned by the controller is driven by the testbench.  The only
// externally driven inputs are the controller clock, POR, and calibration
// start request.  All sensor control outputs are observed and audited.
// ============================================================================
`timescale 1ns/1ps

module tb_ftc_vcs_xa_1ghz;
    // ------------------------------------------------------------------------
    // Controller input ports.
    // cal_clk is the canonical 1 GHz / 1 ns Phase 1 clock.  ctrl_por_n is the
    // controller POR input, and cal_start is a one-request startup command.
    // These are the complete digital inputs driven by this diagnostic bench.
    // ------------------------------------------------------------------------
    logic cal_clk;
    logic ctrl_por_n;
    logic cal_start;

    // ------------------------------------------------------------------------
    // Controller-to-sensor ports.
    // The mapped controller owns every one of these signals.  The behavioral
    // sensor reads the thermometer rails and the reset/S_CLK waveform but does
    // not alter them.  medium_therm is active-high; fine_therm is active-low.
    // ------------------------------------------------------------------------
    logic sense_dff_reset;
    logic sense_s_clk;
    logic [15:0] medium_therm;
    logic [9:0] fine_therm;

    // ------------------------------------------------------------------------
    // Sensor-to-controller and public audit ports.
    // q_final is supplied only by the behavioral sensor.  The remaining ports
    // are registered status, code, state, and one-cycle event markers exported
    // by the synthesized controller for exact protocol accounting.
    // ------------------------------------------------------------------------
    logic q_final;
    logic cal_busy;
    logic cal_done;
    logic cal_fail;
    logic lock_valid;
    logic [4:0] medium_code;
    logic [3:0] fine_code;
    logic [2:0] fail_reason;
    logic [4:0] fsm_state;
    logic q_sample_1_event;
    logic q_sample_2_event;
    logic config_update_event;
    logic probe_start_event;

    // ------------------------------------------------------------------------
    // Exact event counters.
    // These counters are driven by event edges, never inferred from periodic
    // CSV rows.  In particular, sclk_count counts physical S_CLK rising edges
    // and is therefore independent of how long S_CLK remains high.
    // ------------------------------------------------------------------------
    integer operation_count;
    integer config_count;
    integer probe_count;
    integer sclk_count;
    integer sample1_count;
    integer sample2_count;
    integer therm_change_count;
    integer monitor_error_count;

    logic [15:0] medium_previous;
    logic [9:0] fine_previous;
    logic terminal_seen;
    logic [15:0] terminal_medium;
    logic [9:0] terminal_fine;

    // The synthesized controller is the object under test.  Its netlist is
    // the same frozen blob used by the historical Phase 9 flow.
    ftc_cal_controller_top u_controller (
        .cal_clk(cal_clk),
        .ctrl_por_n(ctrl_por_n),
        .cal_start(cal_start),
        .q_final(q_final),
        .sense_dff_reset(sense_dff_reset),
        .sense_s_clk(sense_s_clk),
        .medium_therm(medium_therm),
        .fine_therm(fine_therm),
        .cal_busy(cal_busy),
        .cal_done(cal_done),
        .cal_fail(cal_fail),
        .lock_valid(lock_valid),
        .medium_code(medium_code),
        .fine_code(fine_code),
        .fail_reason(fail_reason),
        .fsm_state(fsm_state),
        .q_sample_1_event(q_sample_1_event),
        .q_sample_2_event(q_sample_2_event),
        .config_update_event(config_update_event),
        .probe_start_event(probe_start_event)
    );

    // This model is a verification oracle only.  It supplies the accepted
    // 0.80 V response table while leaving all controller-owned controls alone.
    ftc_sensor_behavior_model u_sensor_oracle (
        .medium_therm(medium_therm),
        .fine_therm(fine_therm),
        .sense_s_clk(sense_s_clk),
        .sense_dff_reset(sense_dff_reset),
        .q_sample_1_event(q_sample_1_event),
        .q_sample_2_event(q_sample_2_event),
        .q_final(q_final)
    );

    // A 1 ns period is required here.  This is intentionally not copied from
    // the historical Phase 8 10 ns relaxation or the failed Phase 9 bench.
    initial begin
        cal_clk = 1'b0;
        forever #0.5 cal_clk = ~cal_clk;
    end

    // Testbench-only helpers count changed physical rails.  These functions
    // are not synthesizable RTL and do not alter the controller implementation.
    function automatic integer changed_medium(input logic [15:0] newer, input logic [15:0] older);
        integer index;
        begin
            changed_medium = 0;
            for (index = 0; index < 16; index = index + 1)
                if (newer[index] !== older[index]) changed_medium = changed_medium + 1;
        end
    endfunction

    function automatic integer changed_fine(input logic [9:0] newer, input logic [9:0] older);
        integer index;
        begin
            changed_fine = 0;
            for (index = 0; index < 10; index = index + 1)
                if (newer[index] !== older[index]) changed_fine = changed_fine + 1;
        end
    endfunction

    // Public event markers are one-cycle pulses from the mapped sequencer.
    always @(posedge config_update_event) begin
        if (ctrl_por_n && cal_busy) begin
            config_count = config_count + 1;
            operation_count = operation_count + 1;
        end
    end

    always @(posedge probe_start_event) begin
        if (ctrl_por_n && cal_busy) begin
            probe_count = probe_count + 1;
            operation_count = operation_count + 1;
        end
    end

    always @(posedge q_sample_1_event)
        if (ctrl_por_n && cal_busy) sample1_count = sample1_count + 1;

    always @(posedge q_sample_2_event)
        if (ctrl_por_n && cal_busy) sample2_count = sample2_count + 1;

    // This is the authoritative S_CLK edge audit required by R1.  A released
    // reset is active-low at the sensor, so reset must be low on this edge.
    always @(posedge sense_s_clk) begin
        if (ctrl_por_n && cal_busy) begin
            sclk_count = sclk_count + 1;
            if (sense_dff_reset !== 1'b0) begin
                monitor_error_count = monitor_error_count + 1;
                $display("R1_ERROR cause=sclk_edge_while_reset count=%0d", sclk_count);
            end
        end
    end

    // Every configuration transaction must change exactly one rail, while the
    // sensor is held reset and its sampling clock is low.  This catches illegal
    // multi-bit or overlapping control transitions at the netlist boundary.
    always @(medium_therm or fine_therm) begin
        integer medium_delta;
        integer fine_delta;
        if (ctrl_por_n && cal_busy) begin
            medium_delta = changed_medium(medium_therm, medium_previous);
            fine_delta = changed_fine(fine_therm, fine_previous);
            if ((medium_delta != 0) || (fine_delta != 0)) begin
                therm_change_count = therm_change_count + 1;
                if (((medium_delta + fine_delta) != 1) ||
                    (sense_dff_reset !== 1'b1) || (sense_s_clk !== 1'b0)) begin
                    monitor_error_count = monitor_error_count + 1;
                    $display("R1_ERROR cause=illegal_therm_transition md=%0d fd=%0d reset=%b sclk=%b", medium_delta, fine_delta, sense_dff_reset, sense_s_clk);
                end
            end
        end
        medium_previous = medium_therm;
        fine_previous = fine_therm;
    end

    // Once terminal status appears, physical configuration must remain frozen.
    always @(posedge cal_clk) begin
        if (ctrl_por_n && (cal_done || cal_fail) && !terminal_seen) begin
            terminal_seen = 1'b1;
            terminal_medium = medium_therm;
            terminal_fine = fine_therm;
        end
        if (terminal_seen && ((medium_therm !== terminal_medium) || (fine_therm !== terminal_fine))) begin
            monitor_error_count = monitor_error_count + 1;
            $display("R1_ERROR cause=configuration_changed_after_terminal");
        end
    end

    // Initialization and one bounded nominal run.  The 1 GHz controller needs
    // only a few hundred cycles for 45 operations; the bound is intentionally
    // generous while remaining finite and auditable.
    initial begin : run_and_check
        integer cycle_count;
        cal_start = 1'b0;
        ctrl_por_n = 1'b0;
        operation_count = 0;
        config_count = 0;
        probe_count = 0;
        sclk_count = 0;
        sample1_count = 0;
        sample2_count = 0;
        therm_change_count = 0;
        monitor_error_count = 0;
        medium_previous = 16'b0;
        fine_previous = 10'b1;
        terminal_seen = 1'b0;
        terminal_medium = 16'b0;
        terminal_fine = 10'b1;

        repeat (10) @(posedge cal_clk);
        u_sensor_oracle.load_scenario("0p80V");
        u_sensor_oracle.reset_stats();
        ctrl_por_n = 1'b1;
        repeat (2) @(posedge cal_clk);
        @(negedge cal_clk);
        cal_start = 1'b1;
        @(negedge cal_clk);
        cal_start = 1'b0;

        cycle_count = 0;
        while (!(cal_done || cal_fail) && (cycle_count < 4000)) begin
            @(posedge cal_clk);
            cycle_count = cycle_count + 1;
        end
        repeat (10) @(posedge cal_clk);

        if (cycle_count >= 4000) $fatal(1, "R1_FAIL cause=timeout");
        if (!cal_done || cal_fail || !lock_valid) $fatal(1, "R1_FAIL cause=status");
        if ((medium_code !== 5'd7) || (fine_code !== 4'd6)) $fatal(1, "R1_FAIL cause=final_code M=%0d F=%0d", medium_code, fine_code);
        if (operation_count !== 45) $fatal(1, "R1_FAIL cause=operation_count got=%0d expected=45", operation_count);
        if (config_count !== 17) $fatal(1, "R1_FAIL cause=config_count got=%0d expected=17", config_count);
        if (probe_count !== 28) $fatal(1, "R1_FAIL cause=probe_count got=%0d expected=28", probe_count);
        if (sclk_count !== 28) $fatal(1, "R1_FAIL cause=sclk_edge_count got=%0d expected=28", sclk_count);
        if ((sample1_count !== 28) || (sample2_count !== 28)) $fatal(1, "R1_FAIL cause=sample_count got=%0d/%0d", sample1_count, sample2_count);
        if (therm_change_count !== 17) $fatal(1, "R1_FAIL cause=therm_change_count got=%0d expected=17", therm_change_count);
        if (u_sensor_oracle.violation_count != 0) $fatal(1, "R1_FAIL cause=sensor_oracle_violation count=%0d", u_sensor_oracle.violation_count);
        if (monitor_error_count != 0) $fatal(1, "R1_FAIL cause=monitor_errors count=%0d", monitor_error_count);

        $display("R1_PASS clock_period_ns=1 operations=45 configs=17 probes=28 sclk_edges=28 samples=28/28 final=M7/F6");
        $finish;
    end

    initial begin
        #5000;
        $fatal(1, "R1_FAIL cause=global_timeout");
    end
endmodule
