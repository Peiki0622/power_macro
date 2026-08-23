// ============================================================================
// H0 mapped + SDF ownership-handoff verification
// ============================================================================
// This bench is intentionally limited to the synthesized handoff module.  It
// drives the three frozen calibration snapshots (M7/F6, M4/F6, and M2/F9),
// annotates the H0 SDF at the DUT instance, and watches every sensor-control
// output during the two registered transition edges.  No startup-calibration
// controller, XA model, transistor sensor, or future detector implementation
// is instantiated here.
//
// The monitor window begins before the WAIT_DET -> SWITCH_SAFE edge and ends
// after the SWITCH_SAFE -> DET_OWNED edge has settled.  All three golden cases
// present identical detector controls to the calibration snapshot during this
// window.  Consequently any observed S_CLK rising edge, reset release, or
// thermometer bit change is an actual mapped/SDF handoff glitch rather than a
// legitimate detector data update.
// ============================================================================
`timescale 1ns/1ps
`default_nettype none

module tb_h0_owner_handoff_sdf;
    // ------------------------------------------------------------------------
    // H0 clock, POR, and frozen calibration-side inputs
    // ------------------------------------------------------------------------
    // cal_clk is the 400 MHz trusted controller clock.  The active-low POR is
    // kept away from clock edges so the SDF timing checks observe a clean
    // asynchronous reset release.
    logic        cal_clk;
    logic        ctrl_por_n;
    logic        cal_busy;
    logic        cal_done;
    logic        cal_fail;
    logic        lock_valid;
    logic        cal_sense_dff_reset;
    logic        cal_sense_s_clk;
    logic [15:0] cal_medium_therm;
    logic [9:0]  cal_fine_therm;
    logic [4:0]  cal_medium_code;
    logic [3:0]  cal_fine_code;

    // ------------------------------------------------------------------------
    // Future detector-side precharge and takeover inputs
    // ------------------------------------------------------------------------
    // The detector is precharged with the exact snapshot before ready rises;
    // it is changed only after the monitored ownership transition settles.
    logic        det_takeover_ready;
    logic        det_sense_dff_reset;
    logic        det_sense_s_clk;
    logic [15:0] det_medium_therm;
    logic [9:0]  det_fine_therm;

    // ------------------------------------------------------------------------
    // H0 sensor-control and contract outputs
    // ------------------------------------------------------------------------
    logic        sense_dff_reset;
    logic        sense_s_clk;
    logic [15:0] medium_therm;
    logic [9:0]  fine_therm;
    logic        cal_cfg_valid;
    logic [4:0]  cal_medium_code_snapshot;
    logic [3:0]  cal_fine_code_snapshot;
    logic [15:0] cal_medium_therm_snapshot;
    logic [9:0]  cal_fine_therm_snapshot;
    logic        det_prepare;
    logic        det_owner_valid;
    logic        handoff_blocked;
    logic        handoff_protocol_error;
    logic [2:0]  handoff_state;

    integer failures;
    integer glitch_events;
    logic   monitor_window;
    logic [15:0] expected_medium;
    logic [9:0]  expected_fine;

    // The monitored transition must remain reset-high and clock-low.  These
    // event monitors catch pulses between clock edges that edge-only checks
    // would miss after SDF delays are applied.
    always @(sense_s_clk) begin
        if (monitor_window && (sense_s_clk !== 1'b0)) begin
            $display("FAIL SDF transition: sense_s_clk was not held low at %0t value=%b state=%0d mode_inputs=%b/%b", $realtime, sense_s_clk, handoff_state, det_sense_s_clk, cal_sense_s_clk);
            failures = failures + 1;
            glitch_events = glitch_events + 1;
        end
    end

    always @(sense_dff_reset) begin
        if (monitor_window && (sense_dff_reset !== 1'b1)) begin
            $display("FAIL SDF transition: reset was released at %0t value=%b state=%0d mode_inputs=%b/%b", $realtime, sense_dff_reset, handoff_state, det_sense_dff_reset, cal_sense_dff_reset);
            failures = failures + 1;
            glitch_events = glitch_events + 1;
        end
    end

    always @(medium_therm) begin
        if (monitor_window && (medium_therm !== expected_medium)) begin
            $display("FAIL SDF transition: medium thermometer changed at %0t value=%h expected=%h state=%0d det=%h cal=%h", $realtime, medium_therm, expected_medium, handoff_state, det_medium_therm, cal_medium_therm);
            failures = failures + 1;
            glitch_events = glitch_events + 1;
        end
    end

    always @(fine_therm) begin
        if (monitor_window && (fine_therm !== expected_fine)) begin
            $display("FAIL SDF transition: fine thermometer changed at %0t value=%h expected=%h state=%0d det=%h cal=%h", $realtime, fine_therm, expected_fine, handoff_state, det_fine_therm, cal_fine_therm);
            failures = failures + 1;
            glitch_events = glitch_events + 1;
        end
    end

    ftc_sensor_owner_handoff dut (
        .cal_clk_i(cal_clk),
        .ctrl_por_n_i(ctrl_por_n),
        .cal_busy_i(cal_busy),
        .cal_done_i(cal_done),
        .cal_fail_i(cal_fail),
        .lock_valid_i(lock_valid),
        .cal_sense_dff_reset_i(cal_sense_dff_reset),
        .cal_sense_s_clk_i(cal_sense_s_clk),
        .cal_medium_therm_i(cal_medium_therm),
        .cal_fine_therm_i(cal_fine_therm),
        .cal_medium_code_i(cal_medium_code),
        .cal_fine_code_i(cal_fine_code),
        .det_takeover_ready_i(det_takeover_ready),
        .det_sense_dff_reset_i(det_sense_dff_reset),
        .det_sense_s_clk_i(det_sense_s_clk),
        .det_medium_therm_i(det_medium_therm),
        .det_fine_therm_i(det_fine_therm),
        .sense_dff_reset_o(sense_dff_reset),
        .sense_s_clk_o(sense_s_clk),
        .medium_therm_o(medium_therm),
        .fine_therm_o(fine_therm),
        .cal_cfg_valid_o(cal_cfg_valid),
        .cal_medium_code_snapshot_o(cal_medium_code_snapshot),
        .cal_fine_code_snapshot_o(cal_fine_code_snapshot),
        .cal_medium_therm_snapshot_o(cal_medium_therm_snapshot),
        .cal_fine_therm_snapshot_o(cal_fine_therm_snapshot),
        .det_prepare_o(det_prepare),
        .det_owner_valid_o(det_owner_valid),
        .handoff_blocked_o(handoff_blocked),
        .handoff_protocol_error_o(handoff_protocol_error),
        .handoff_state_o(handoff_state)
    );

    // 400 MHz clock: 2.5 ns period, matching the H0 synthesis constraint.
    initial begin
        cal_clk = 1'b0;
        forever #1.25 cal_clk = ~cal_clk;
    end

    // Reproduce the frozen registered thermometer encodings without adding a
    // decoder to the synthesized DUT.  Medium is one-hot-prefix positive
    // logic; fine is an inverted prefix as defined by ftc_cfg_therm_regs.
    task automatic drive_calibration_vector(input integer medium_code_i,
                                             input integer fine_code_i);
        integer index;
        begin
            cal_medium_code  = medium_code_i[4:0];
            cal_fine_code    = fine_code_i[3:0];
            cal_medium_therm = 16'd0;
            cal_fine_therm   = 10'h3ff;
            for (index = 0; index < medium_code_i; index = index + 1)
                cal_medium_therm[index] = 1'b1;
            for (index = 0; index < fine_code_i; index = index + 1)
                cal_fine_therm[index] = 1'b0;
        end
    endtask

    // POR is the only return path to CAL ownership.  The long release delay
    // also permits all asynchronous SDF reset arcs to settle before status is
    // made valid for a nominal calibration case.
    task automatic reset_dut;
        begin
            monitor_window = 1'b0;
            ctrl_por_n = 1'b0;
            cal_busy = 1'b0;
            cal_done = 1'b0;
            cal_fail = 1'b0;
            lock_valid = 1'b0;
            cal_sense_dff_reset = 1'b1;
            cal_sense_s_clk = 1'b0;
            det_takeover_ready = 1'b0;
            det_sense_dff_reset = 1'b1;
            det_sense_s_clk = 1'b0;
            det_medium_therm = 16'd0;
            det_fine_therm = 10'h3ff;
            repeat (2) @(posedge cal_clk);
            #0.40;
            ctrl_por_n = 1'b1;
            #1.00;
            if (handoff_state !== 3'd0) begin
                $display("FAIL SDF POR did not return CAL state: %0d", handoff_state);
                failures = failures + 1;
            end
        end
    endtask

    // Execute one complete mapped handoff.  The monitor covers both state
    // transitions; detector data is changed only once DET ownership is stable.
    task automatic run_golden_case(input string label,
                                   input integer medium_code_i,
                                   input integer fine_code_i);
        begin
            reset_dut();
            drive_calibration_vector(medium_code_i, fine_code_i);
            cal_busy = 1'b0;
            cal_done = 1'b1;
            cal_fail = 1'b0;
            lock_valid = 1'b1;
            cal_sense_dff_reset = 1'b1;
            cal_sense_s_clk = 1'b0;
            // Precharge detector data before the snapshot edge.  Only the
            // ready handshake is intentionally delayed until WAIT_DET; this
            // keeps SDF comparator inputs outside the setup aperture.
            det_medium_therm = cal_medium_therm;
            det_fine_therm = cal_fine_therm;
            det_sense_dff_reset = 1'b1;
            det_sense_s_clk = 1'b0;

            @(posedge cal_clk);
            #1.00;
            if (handoff_state !== 3'd1 || !cal_cfg_valid || !det_prepare) begin
                $display("FAIL %s snapshot/WAIT state invalid", label);
                failures = failures + 1;
            end

            expected_medium = cal_medium_therm_snapshot;
            expected_fine   = cal_fine_therm_snapshot;
            monitor_window = 1'b1;
            det_takeover_ready = 1'b1;

            @(posedge cal_clk);
            #1.00;
            if (handoff_state !== 3'd2 || det_owner_valid || handoff_blocked) begin
                $display("FAIL %s SWITCH_SAFE state invalid", label);
                failures = failures + 1;
            end
            if (sense_dff_reset !== 1'b1 || sense_s_clk !== 1'b0 ||
                medium_therm !== expected_medium || fine_therm !== expected_fine) begin
                $display("FAIL %s safe outputs invalid", label);
                failures = failures + 1;
            end

            @(posedge cal_clk);
            #1.00;
            if (handoff_state !== 3'd3 || !det_owner_valid || handoff_blocked) begin
                $display("FAIL %s DET ownership invalid", label);
                failures = failures + 1;
            end
            monitor_window = 1'b0;

            // The mapped mux intentionally drains its SAFE overlap on the
            // next controller edge.  The detector remains precharged and
            // therefore still sees the exact snapshot during this cycle.
            @(posedge cal_clk);
            #1.00;

            // A detector update is legal only after the monitored handoff.
            det_medium_therm = 16'h55aa;
            det_fine_therm = 10'h155;
            #1.00;
            if (medium_therm !== det_medium_therm || fine_therm !== det_fine_therm ||
                sense_dff_reset !== det_sense_dff_reset ||
                sense_s_clk !== det_sense_s_clk) begin
                $display("FAIL %s detector outputs did not follow DET owner", label);
                failures = failures + 1;
            end

            // CAL-side changes must not revoke registered DET ownership.
            drive_calibration_vector(15, 2);
            cal_busy = 1'b1;
            cal_done = 1'b0;
            lock_valid = 1'b0;
            cal_sense_dff_reset = 1'b0;
            cal_sense_s_clk = 1'b1;
            @(posedge cal_clk);
            #1.00;
            if (!det_owner_valid || medium_therm !== det_medium_therm ||
                fine_therm !== det_fine_therm) begin
                $display("FAIL %s CAL inputs revoked DET ownership", label);
                failures = failures + 1;
            end
            $display("PASS %s mapped+SDF ownership transition", label);
        end
    endtask

    initial begin
        failures = 0;
        glitch_events = 0;
        monitor_window = 1'b0;
        expected_medium = 16'd0;
        expected_fine = 10'h3ff;
        ctrl_por_n = 1'b0;
        cal_busy = 1'b0;
        cal_done = 1'b0;
        cal_fail = 1'b0;
        lock_valid = 1'b0;
        cal_sense_dff_reset = 1'b1;
        cal_sense_s_clk = 1'b0;
        cal_medium_therm = 16'd0;
        cal_fine_therm = 10'h3ff;
        cal_medium_code = 5'd0;
        cal_fine_code = 4'd0;
        det_takeover_ready = 1'b0;
        det_sense_dff_reset = 1'b1;
        det_sense_s_clk = 1'b0;
        det_medium_therm = 16'd0;
        det_fine_therm = 10'h3ff;

        run_golden_case("0p80_M7_F6", 7, 6);
        run_golden_case("0p95_M4_F6", 4, 6);
        run_golden_case("1p10_M2_F9", 2, 9);

        if (failures == 0 && glitch_events == 0)
            $display("H0 mapped+SDF verification PASS: 3 golden handoffs, no transition glitches");
        else
            $display("H0 mapped+SDF verification FAIL: failures=%0d glitches=%0d",
                     failures, glitch_events);
        $finish;
    end
endmodule

`default_nettype wire
