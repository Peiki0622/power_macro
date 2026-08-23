// ============================================================================
// H0 ownership handoff RTL verification
// ============================================================================
// This bench intentionally instantiates only ftc_sensor_owner_handoff.  The
// frozen startup controller, XA bridge, and transistor sensor are not present:
// H0 verification is a focused proof of ownership, snapshot, and safe-switch
// behavior.  The three nominal vectors are reconstructed with the exact
// registered thermometer conventions used by ftc_cfg_therm_regs:
//   medium code M: bits [M-1:0] are 1, remaining bits are 0;
//   fine code F: bits [F-1:0] are 0, remaining bits are 1.
// ============================================================================
`timescale 1ns/1ps
`default_nettype none

module tb_ftc_sensor_owner_handoff;
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
    logic        det_takeover_ready;
    logic        det_sense_dff_reset;
    logic        det_sense_s_clk;
    logic [15:0] det_medium_therm;
    logic [9:0]  det_fine_therm;

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

    // The active H0 clock is the frozen 400 MHz calibration clock.
    initial begin
        cal_clk = 1'b0;
        forever #1.25 cal_clk = ~cal_clk;
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

    // Build the physical thermometer vectors without a decoder in the DUT.
    // This task mirrors the two registered encodings in ftc_cfg_therm_regs.
    task automatic drive_calibration_vector(input integer medium_code_i,
                                             input integer fine_code_i);
        integer index;
        begin
            cal_medium_code = medium_code_i[4:0];
            cal_fine_code   = fine_code_i[3:0];
            cal_medium_therm = 16'd0;
            cal_fine_therm   = 10'h3ff;
            for (index = 0; index < medium_code_i; index = index + 1)
                cal_medium_therm[index] = 1'b1;
            for (index = 0; index < fine_code_i; index = index + 1)
                cal_fine_therm[index] = 1'b0;
        end
    endtask

    task automatic check_state(input logic [2:0] expected,
                               input string label);
        begin
            #0.01;
            if (handoff_state !== expected) begin
                $display("FAIL %s: expected state %0d, got %0d", label,
                         expected, handoff_state);
                failures = failures + 1;
            end
        end
    endtask

    task automatic check_condition(input logic condition,
                                   input string label);
        begin
            if (!condition) begin
                $display("FAIL %s", label);
                failures = failures + 1;
            end
        end
    endtask

    task automatic reset_dut;
        begin
            // Make the reset pulse explicit even when the caller already left
            // POR asserted from a previous scenario.  The short setup delay
            // also prevents a same-timestamp testbench race with data inputs.
            ctrl_por_n = 1'b1;
            #0.01;
            ctrl_por_n = 1'b0;
            #0.01;
            // Model the frozen controller's reset outputs/status while POR is
            // active so a prior scenario cannot immediately retrigger BLOCKED
            // on the first edge after POR release.
            cal_busy = 1'b0;
            cal_done = 1'b0;
            cal_fail = 1'b0;
            lock_valid = 1'b0;
            cal_sense_dff_reset = 1'b1;
            cal_sense_s_clk = 1'b0;
            det_takeover_ready = 1'b0;
            det_sense_dff_reset = 1'b1;
            det_sense_s_clk = 1'b0;
            repeat (2) @(posedge cal_clk);
            ctrl_por_n = 1'b1;
            @(posedge cal_clk);
            #0.01;
            check_state(3'd0, "POR returns CAL ownership");
            check_condition(!cal_cfg_valid && !det_owner_valid &&
                            !handoff_blocked && !handoff_protocol_error,
                            "POR clears handoff state");
        end
    endtask

    // A complete successful handoff is replayed for each frozen PVT code.
    // The safe state is checked while it is active, before DET ownership is
    // allowed to become visible on the following clock edge.
    task automatic run_nominal(input string label,
                               input integer medium_code_i,
                               input integer fine_code_i);
        logic [15:0] saved_medium;
        logic [9:0]  saved_fine;
        begin
            reset_dut();
            drive_calibration_vector(medium_code_i, fine_code_i);
            cal_busy = 1'b0;
            cal_done = 1'b1;
            cal_fail = 1'b0;
            lock_valid = 1'b1;
            cal_sense_dff_reset = 1'b1;
            cal_sense_s_clk = 1'b0;
            det_takeover_ready = 1'b0;
            det_sense_dff_reset = 1'b1;
            det_sense_s_clk = 1'b0;
            det_medium_therm = 16'd0;
            det_fine_therm = 10'd0;

            @(posedge cal_clk);
            #0.01;
            check_state(3'd1, {label, " enters WAIT_DET"});
            check_condition(cal_cfg_valid && det_prepare && !det_owner_valid,
                            {label, " publishes snapshot before DET"});
            check_condition(cal_medium_code_snapshot == medium_code_i &&
                            cal_fine_code_snapshot == fine_code_i,
                            {label, " captures binary codes"});
            check_condition(cal_medium_therm_snapshot == cal_medium_therm &&
                            cal_fine_therm_snapshot == cal_fine_therm,
                            {label, " captures exact thermometer vectors"});

            saved_medium = cal_medium_therm_snapshot;
            saved_fine = cal_fine_therm_snapshot;
            det_medium_therm = saved_medium;
            det_fine_therm = saved_fine;
            det_takeover_ready = 1'b1;
            @(posedge cal_clk);
            #0.01;
            check_state(3'd2, {label, " enters SWITCH_SAFE"});
            check_condition(sense_dff_reset && !sense_s_clk &&
                            medium_therm == saved_medium &&
                            fine_therm == saved_fine,
                            {label, " safe switch has stable controls"});
            check_condition(!det_owner_valid && !handoff_blocked,
                            {label, " does not expose DET during safe cycle"});

            @(posedge cal_clk);
            #0.01;
            check_state(3'd3, {label, " enters DET_OWNED"});
            check_condition(det_owner_valid && !handoff_blocked,
                            {label, " publishes DET ownership"});

            // The mapped handoff keeps the precharged SAFE branch overlapped
            // for one clock to make the physical mux transition glitch-free.
            // Detector inputs remain equal to the snapshot until that branch
            // is drained; then live detector ownership is exercised.
            @(posedge cal_clk);
            #0.01;
            det_medium_therm = 16'h55aa;
            det_fine_therm = 10'h155;
            det_sense_dff_reset = 1'b1;
            det_sense_s_clk = 1'b0;
            #0.01;
            check_condition(medium_therm == det_medium_therm &&
                            fine_therm == det_fine_therm && sense_dff_reset &&
                            !sense_s_clk,
                            {label, " selects detector controls"});

            // Frozen calibration inputs are randomized after DET ownership.
            // The output must remain entirely detector-owned and the snapshot
            // must remain unchanged until POR.
            drive_calibration_vector(15, 2);
            cal_busy = 1'b1;
            cal_done = 1'b0;
            lock_valid = 1'b0;
            cal_sense_dff_reset = 1'b0;
            cal_sense_s_clk = 1'b1;
            @(posedge cal_clk);
            #0.01;
            check_condition(det_owner_valid && medium_therm == det_medium_therm &&
                            fine_therm == det_fine_therm &&
                            cal_medium_therm_snapshot == saved_medium &&
                            cal_fine_therm_snapshot == saved_fine,
                            {label, " CAL changes cannot revoke DET"});
        end
    endtask

    task automatic run_unsafe_calibration_case(input string label,
                                                input logic busy_i,
                                                input logic reset_i,
                                                input logic sclk_i);
        begin
            reset_dut();
            drive_calibration_vector(7, 6);
            cal_busy = busy_i;
            cal_done = 1'b1;
            cal_fail = 1'b0;
            lock_valid = 1'b1;
            cal_sense_dff_reset = reset_i;
            cal_sense_s_clk = sclk_i;
            det_takeover_ready = 1'b1;
            det_medium_therm = 16'hffff;
            det_fine_therm = 10'h3ff;
            det_sense_dff_reset = 1'b1;
            det_sense_s_clk = 1'b0;
            @(posedge cal_clk);
            check_condition(handoff_state == 3'd0 && !cal_cfg_valid &&
                            !det_owner_valid,
                            {label, " unsafe calibration cannot snapshot"});
        end
    endtask

    task automatic run_invalid_ready_case(input string label,
                                           input logic [15:0] medium_i,
                                           input logic [9:0] fine_i,
                                           input logic reset_i,
                                           input logic sclk_i);
        begin
            reset_dut();
            drive_calibration_vector(4, 6);
            cal_busy = 1'b0;
            cal_done = 1'b1;
            cal_fail = 1'b0;
            lock_valid = 1'b1;
            cal_sense_dff_reset = 1'b1;
            cal_sense_s_clk = 1'b0;
            det_takeover_ready = 1'b0;
            @(posedge cal_clk);
            det_medium_therm = medium_i;
            det_fine_therm = fine_i;
            det_sense_dff_reset = reset_i;
            det_sense_s_clk = sclk_i;
            det_takeover_ready = 1'b1;
            @(posedge cal_clk);
            #0.01;
            check_condition(handoff_state == 3'd4 && handoff_blocked &&
                            handoff_protocol_error && !det_owner_valid &&
                            sense_dff_reset && !sense_s_clk,
                            {label, " malformed ready is permanently blocked"});
        end
    endtask

    initial begin
        failures = 0;
        // Start high briefly so the first reset_dut call creates a real
        // active-low edge.  An initial 0 assignment alone is not guaranteed to
        // trigger an asynchronous reset from an X-valued simulation state.
        ctrl_por_n = 1'b1;
        #0.01;
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
        det_fine_therm = 10'd0;

        // Early ready is ignored while CAL owns the sensor.  Detector inputs
        // are intentionally inconsistent to ensure they cannot leak through.
        reset_dut();
        drive_calibration_vector(3, 2);
        det_takeover_ready = 1'b1;
        det_medium_therm = 16'hffff;
        det_fine_therm = 10'h000;
        repeat (2) @(posedge cal_clk);
        check_condition(handoff_state == 3'd0 && !det_owner_valid &&
                        medium_therm == cal_medium_therm &&
                        fine_therm == cal_fine_therm,
                        "early ready and random DET controls are ignored");

        run_unsafe_calibration_case("busy lock", 1'b1, 1'b1, 1'b0);
        run_unsafe_calibration_case("reset released", 1'b0, 1'b0, 1'b0);
        run_unsafe_calibration_case("S_CLK high", 1'b0, 1'b1, 1'b1);

        // A failed calibration is blocked and its last stable control vectors
        // are held with reset asserted and S_CLK forced low.
        reset_dut();
        drive_calibration_vector(5, 3);
        cal_fail = 1'b1;
        @(posedge cal_clk);
        #0.01;
        check_condition(handoff_state == 3'd4 && handoff_blocked &&
                        !det_owner_valid && sense_dff_reset && !sense_s_clk &&
                        medium_therm == cal_medium_therm &&
                        fine_therm == cal_fine_therm,
                        "cal_fail blocks and holds last calibration vectors");

        run_nominal("0p80_M7_F6", 7, 6);
        run_nominal("0p95_M4_F6", 4, 6);
        run_nominal("1p10_M2_F9", 2, 9);

        // Each ready safety rule is independently exercised after a fresh
        // successful snapshot; the first violation must prevent ownership.
        run_invalid_ready_case("medium mismatch", 16'hffff, 10'h3c0, 1'b1, 1'b0);
        run_invalid_ready_case("fine mismatch", 16'h000f, 10'h000, 1'b1, 1'b0);
        run_invalid_ready_case("reset low", 16'h000f, 10'h03f, 1'b0, 1'b0);
        run_invalid_ready_case("S_CLK high", 16'h000f, 10'h03f, 1'b1, 1'b1);

        // POR is the only legal path back from DET.  A new reset must clear
        // the snapshot-valid and sticky diagnostics as well as ownership.
        reset_dut();
        drive_calibration_vector(2, 9);
        cal_busy = 1'b0;
        cal_done = 1'b1;
        lock_valid = 1'b1;
        @(posedge cal_clk);
        #0.01;
        det_medium_therm = cal_medium_therm_snapshot;
        det_fine_therm = cal_fine_therm_snapshot;
        det_takeover_ready = 1'b1;
        @(posedge cal_clk);
        @(posedge cal_clk);
        #0.01;
        check_condition(det_owner_valid, "DET reached before POR reset test");
        reset_dut();

        if (failures != 0) begin
            $display("H0 RTL verification FAILED with %0d failures", failures);
            $fatal(1);
        end
        $display("H0 RTL verification PASS: nominal, negative, and POR-only paths covered");
        $finish;
    end

    initial begin
        $dumpfile("delay_chain/ftc/controller/h0_calibration_detection_handoff/verification/rtl/h0_owner_handoff.vcd");
        $dumpvars(0, tb_ftc_sensor_owner_handoff);
    end
endmodule

`default_nettype wire
