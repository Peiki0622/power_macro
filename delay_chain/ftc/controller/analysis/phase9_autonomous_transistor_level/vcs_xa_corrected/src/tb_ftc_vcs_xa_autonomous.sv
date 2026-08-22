// ============================================================================
// Corrected Phase 9 autonomous VCS-XA testbench
//
// This is the only full-calibration mixed-signal bench in the corrected flow.
// Its ownership boundary is strict: the testbench drives only ctrl_por_n,
// cal_start, and cal_clk.  The transistor sensor receives sense_s_clk,
// sense_dff_reset, medium_therm, and fine_therm exclusively from the mapped
// synthesized controller.  Sensor VDD/VSS are private analog nodes generated
// by ftc_sensor_ams_wrapper.sp and are never digital testbench ports.
//
// Every audit counter is event-driven.  The periodic CSV snapshot is taken at
// negedge cal_clk, after the preceding mapped clock-to-Q activity, and is not
// used to infer physical edge counts.  Analog q_final and the private sensor
// supply are sampled with the supported XA $snps_get_volt task at the two Q
// sample events and at each stable snapshot.
// ============================================================================
`timescale 1ns/1ps

module tb_ftc_vcs_xa_autonomous;
    // ------------------------------------------------------------------------
    // Scenario expectation constants.  The bridge, controller, sensor, and
    // event monitors are identical for every voltage.  Only these frozen
    // trajectory values are selected at compile time by the run script.
    // ------------------------------------------------------------------------
`ifdef AUTONOMOUS_0P95
    localparam integer EXPECTED_FINAL_M = 4;
    localparam integer EXPECTED_FINAL_F = 6;
    localparam integer EXPECTED_OPERATIONS = 36;
    localparam integer EXPECTED_CONFIGS = 14;
    localparam integer EXPECTED_PROBES = 22;
    localparam real EXPECTED_VDD_MIN = 0.94;
    localparam real EXPECTED_VDD_MAX = 0.96;
`elsif AUTONOMOUS_1P10
    localparam integer EXPECTED_FINAL_M = 2;
    localparam integer EXPECTED_FINAL_F = 9;
    localparam integer EXPECTED_OPERATIONS = 36;
    localparam integer EXPECTED_CONFIGS = 15;
    localparam integer EXPECTED_PROBES = 21;
    localparam real EXPECTED_VDD_MIN = 1.09;
    localparam real EXPECTED_VDD_MAX = 1.11;
`else
    localparam integer EXPECTED_FINAL_M = 7;
    localparam integer EXPECTED_FINAL_F = 6;
    localparam integer EXPECTED_OPERATIONS = 45;
    localparam integer EXPECTED_CONFIGS = 17;
    localparam integer EXPECTED_PROBES = 28;
    localparam real EXPECTED_VDD_MIN = 0.79;
    localparam real EXPECTED_VDD_MAX = 0.81;
`endif
    // ------------------------------------------------------------------------
    // External inputs permitted by the autonomous Phase 9 contract.
    // cal_clk is fixed at 1 ns period; POR and start are the only digital
    // control stimuli.  No sensor control signal is assigned in this module.
    // ------------------------------------------------------------------------
    logic cal_clk;
    logic ctrl_por_n;
    logic cal_start;

    // ------------------------------------------------------------------------
    // Synthesized controller outputs and returned sensor result.
    // The controller owns all sensor controls.  q_final is the A2D-converted
    // analog standard-cell DFF output returned by the XA sensor view.
    // ------------------------------------------------------------------------
    logic q_final;
    logic sense_dff_reset;
    logic sense_s_clk;
    logic [15:0] medium_therm;
    logic [9:0] fine_therm;
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
    // Edge-accurate event counters and consistency state.
    // These counters are independent of CSV sampling and are the authoritative
    // proof of operation totals and physical sensor-clock edge totals.
    // ------------------------------------------------------------------------
    integer operation_count;
    integer config_count;
    integer probe_count;
    integer sclk_rise_count;
    integer sample1_count;
    integer sample2_count;
    integer therm_change_count;
    integer monitor_error_count;
    integer csv_fd;
    integer csv_edge;
    integer probe_sclk_at_start;
    integer probe_sclk_at_end;
    integer probe_sample1_at_start;
    integer probe_sample2_at_start;
    logic probe_active;
    logic [15:0] medium_previous;
    logic [9:0] fine_previous;
    logic [15:0] terminal_medium;
    logic [9:0] terminal_fine;
    logic terminal_seen;

    // Analog values are retained only for the current event/snapshot row.
    real analog_q;
    real analog_vdd;
    real analog_vss;
    real analog_sclk;
    real analog_reset;
    real analog_q_sample1;
    real analog_q_sample2;

    // Controller instance under test.  This is the frozen synthesized netlist
    // and not an RTL reimplementation.
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

    // The corrected sensor view owns analog supplies internally.  This cell
    // has no VDD/VSS digital ports, preventing generic supply D2A insertion.
    ftc_sensor_ams u_sensor (
        .q_final(q_final),
        .sense_s_clk(sense_s_clk),
        .sense_dff_reset(sense_dff_reset),
        .medium_therm(medium_therm),
        .fine_therm(fine_therm)
    );

    // Canonical Phase 1 clock: one nanosecond period and 50% duty cycle.
    initial begin
        cal_clk = 1'b0;
        forever #0.5 cal_clk = ~cal_clk;
    end

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

    // Analog reads are diagnostic measurements, never digital decisions.  The
    // controller always consumes q_final; these values prove that q_final and
    // the private supply are electrically meaningful at the sample events.
    task automatic read_analog_values;
        begin
            analog_q = $snps_get_volt(tb_ftc_vcs_xa_autonomous.u_sensor.q_final);
            analog_vdd = $snps_get_volt(tb_ftc_vcs_xa_autonomous.u_sensor.VDD_LOCAL);
            analog_vss = $snps_get_volt(tb_ftc_vcs_xa_autonomous.u_sensor.VSS_LOCAL);
            analog_sclk = $snps_get_volt(tb_ftc_vcs_xa_autonomous.u_sensor.sense_s_clk);
            analog_reset = $snps_get_volt(tb_ftc_vcs_xa_autonomous.u_sensor.sense_dff_reset);
        end
    endtask

    // Each probe must have exactly one start event, one physical clock edge,
    // and two sample events.  The active-window state also detects any
    // configuration mutation before recovery is complete.
    always @(posedge probe_start_event) begin
        if (cal_busy) begin
            probe_count = probe_count + 1;
            operation_count = operation_count + 1;
            if (probe_active) monitor_error_count = monitor_error_count + 1;
            probe_active = 1'b1;
            probe_sclk_at_start = sclk_rise_count;
            probe_sample1_at_start = sample1_count;
            probe_sample2_at_start = sample2_count;
        end
    end

    always @(posedge sense_s_clk) begin
        if (cal_busy) begin
            sclk_rise_count = sclk_rise_count + 1;
            if (!probe_active || sense_dff_reset !== 1'b0)
                monitor_error_count = monitor_error_count + 1;
        end
    end

    always @(posedge q_sample_1_event) begin
        if (cal_busy) begin
            sample1_count = sample1_count + 1;
            if (!probe_active) monitor_error_count = monitor_error_count + 1;
            read_analog_values();
            analog_q_sample1 = analog_q;
        end
    end

    always @(posedge q_sample_2_event) begin
        if (cal_busy) begin
            sample2_count = sample2_count + 1;
            if (!probe_active) monitor_error_count = monitor_error_count + 1;
            read_analog_values();
            analog_q_sample2 = analog_q;
        end
    end

    always @(posedge config_update_event) begin
        if (cal_busy) begin
            config_count = config_count + 1;
            operation_count = operation_count + 1;
        end
    end

    // Count one-bit physical rail transitions and enforce the frozen update
    // window: reset asserted and S_CLK low.  This is event-driven on vectors,
    // not inferred from a periodic state snapshot.
    always @(medium_therm or fine_therm) begin
        integer medium_delta;
        integer fine_delta;
        if (cal_busy) begin
            medium_delta = changed_medium(medium_therm, medium_previous);
            fine_delta = changed_fine(fine_therm, fine_previous);
            if ((medium_delta != 0) || (fine_delta != 0)) begin
                therm_change_count = therm_change_count + 1;
                if (((medium_delta + fine_delta) != 1) ||
                    (sense_dff_reset !== 1'b1) || (sense_s_clk !== 1'b0))
                    monitor_error_count = monitor_error_count + 1;
            end
        end
        medium_previous = medium_therm;
        fine_previous = fine_therm;
    end

    // Recovery completion closes the active probe window and checks the exact
    // local transaction count.  A new probe cannot start until this check has
    // observed one edge and two samples for the previous probe.
    always @(posedge config_update_event or posedge probe_start_event) begin
        if (probe_active && (sclk_rise_count - probe_sclk_at_start > 1))
            monitor_error_count = monitor_error_count + 1;
    end

    always @(negedge cal_clk) begin
        if (probe_active && (sample2_count > probe_sample2_at_start) &&
            (sclk_rise_count > probe_sclk_at_start)) begin
            probe_sclk_at_end = sclk_rise_count;
            if ((probe_sclk_at_end - probe_sclk_at_start) !== 1)
                monitor_error_count = monitor_error_count + 1;
            if ((sample1_count - probe_sample1_at_start) !== 1 ||
                (sample2_count - probe_sample2_at_start) !== 1)
                monitor_error_count = monitor_error_count + 1;
            probe_active = 1'b0;
        end
        read_analog_values();
        csv_edge = csv_edge + 1;
        $fwrite(csv_fd, "%0t,%0d,%b,%b,%b,%b,%b,%b,%b,%0d,%0d,%0d,%0d,%0d,%h,%h,%h,%h,%0d,%0d,%0d,%0d,%0d,%0.6f,%0.6f,%0.6f,%0.6f,%0.6f\n",
            $time, csv_edge, q_final, sense_s_clk, sense_dff_reset, cal_busy,
            cal_done, cal_fail, lock_valid, operation_count, config_count,
            probe_count, sclk_rise_count, sample1_count, medium_therm,
            fine_therm, medium_code, fine_code, fsm_state, q_sample_1_event,
            q_sample_2_event, config_update_event, probe_start_event, analog_q,
            analog_vdd, analog_vss, analog_sclk, analog_reset);
    end

    always @(posedge cal_clk) begin
        if (cal_done || cal_fail) begin
            if (!terminal_seen) begin
                terminal_seen = 1'b1;
                terminal_medium = medium_therm;
                terminal_fine = fine_therm;
            end
        end
        if (terminal_seen && ((medium_therm !== terminal_medium) || (fine_therm !== terminal_fine)))
            monitor_error_count = monitor_error_count + 1;
    end

    initial begin : autonomous_run
        integer cycle_count;
        csv_fd = $fopen("controller_events.csv", "w");
        if (csv_fd == 0) $fatal(1, "R6_FAIL cause=csv_open");
        $fwrite(csv_fd, "time_ps,clk_edge,q_final,sense_s_clk,sense_dff_reset,cal_busy,cal_done,cal_fail,lock_valid,operation_count,config_count,probe_count,sclk_rise_count,sample1_count,medium_therm,fine_therm,medium_code,fine_code,fsm_state,q_sample_1_event,q_sample_2_event,config_update_event,probe_start_event,analog_q,analog_vdd,analog_vss,analog_sclk,analog_reset\n");
        ctrl_por_n = 1'b0;
        cal_start = 1'b0;
        operation_count = 0;
        config_count = 0;
        probe_count = 0;
        sclk_rise_count = 0;
        sample1_count = 0;
        sample2_count = 0;
        therm_change_count = 0;
        monitor_error_count = 0;
        csv_edge = 0;
        probe_active = 1'b0;
        terminal_seen = 1'b0;
        medium_previous = 16'b0;
        fine_previous = 10'b1111111111;
        terminal_medium = 16'b0;
        terminal_fine = 10'b1111111111;
        analog_q_sample1 = 0.0;
        analog_q_sample2 = 0.0;

        repeat (10) @(posedge cal_clk);
        ctrl_por_n = 1'b1;
        repeat (2) @(posedge cal_clk);
        @(negedge cal_clk);
        cal_start = 1'b1;
        @(negedge cal_clk);
        cal_start = 1'b0;

        cycle_count = 0;
        // The 705-cycle bound is derived from bridge_contract.json:
        // 45 operations * (2 settle + 11 local transaction cycles) +
        // 20 startup cycles + 100 safety cycles = 705 cycles at 1 ns.
        while (!(cal_done || cal_fail) && (cycle_count < 705)) begin
            @(posedge cal_clk);
            cycle_count = cycle_count + 1;
        end
        repeat (12) @(posedge cal_clk);
        read_analog_values();
        $fclose(csv_fd);

        if (cycle_count >= 705) $fatal(1, "R6_FAIL cause=timeout");
        if (!cal_done || cal_fail || !lock_valid) $fatal(1, "R6_FAIL cause=status");
        if ((medium_code !== EXPECTED_FINAL_M) || (fine_code !== EXPECTED_FINAL_F)) $fatal(1, "R6_FAIL cause=final_code M=%0d F=%0d expected=M%0d/F%0d", medium_code, fine_code, EXPECTED_FINAL_M, EXPECTED_FINAL_F);
        if (operation_count !== EXPECTED_OPERATIONS || config_count !== EXPECTED_CONFIGS || probe_count !== EXPECTED_PROBES) $fatal(1, "R6_FAIL cause=operation_counts ops=%0d cfg=%0d probes=%0d expected=%0d/%0d/%0d", operation_count, config_count, probe_count, EXPECTED_OPERATIONS, EXPECTED_CONFIGS, EXPECTED_PROBES);
        if (sclk_rise_count !== EXPECTED_PROBES || sample1_count !== EXPECTED_PROBES || sample2_count !== EXPECTED_PROBES) $fatal(1, "R6_FAIL cause=edge_sample_counts sclk=%0d s1=%0d s2=%0d expected=%0d", sclk_rise_count, sample1_count, sample2_count, EXPECTED_PROBES);
        if (therm_change_count !== config_count) $fatal(1, "R6_FAIL cause=thermometer_count therm=%0d config=%0d", therm_change_count, config_count);
        if (monitor_error_count !== 0) $fatal(1, "R6_FAIL cause=monitor_errors count=%0d", monitor_error_count);
        if ((analog_vdd < EXPECTED_VDD_MIN) || (analog_vdd > EXPECTED_VDD_MAX) || (analog_vss < -0.01) || (analog_vss > 0.01)) $fatal(1, "R6_FAIL cause=supply analog_vdd=%0.6f analog_vss=%0.6f", analog_vdd, analog_vss);
        $display("R6_PASS supply=%0.6f operations=%0d configs=%0d probes=%0d sclk_edges=%0d samples=%0d/%0d final=M%0d/F%0d analog_vdd=%0.6f", analog_vdd, EXPECTED_OPERATIONS, EXPECTED_CONFIGS, EXPECTED_PROBES, EXPECTED_PROBES, EXPECTED_PROBES, EXPECTED_PROBES, EXPECTED_FINAL_M, EXPECTED_FINAL_F, analog_vdd);
        $finish;
    end

    initial begin
        #800;
        $fatal(1, "R6_FAIL cause=global_timeout");
    end
endmodule
