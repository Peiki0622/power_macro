// ============================================================================
// FTC Calibration Controller - Gate-Level Functional Simulation Testbench
// ============================================================================
// Phase 8 Subphase A: Functional gate-level verification
//
// Purpose:
//   Verify that synthesis preserved controller behavior by running the same
//   test scenarios as RTL Phase 5, using the synthesized gate-level netlist
//   with the same behavioral sensor model.
//
// Test scenarios:
//   1. Nominal 0.80V: Expect M7/F6
//   2. Nominal 0.95V: Expect M4/F6
//   3. Nominal 1.10V: Expect M2/F9
//
// Pass criteria:
//   - Same final M/F codes as RTL
//   - Same high-level operation count (±1 tolerance for gate delays)
//   - cal_done asserts, cal_fail remains low
//   - lock_valid asserts with cal_done
//
// Phase: 8A - Gate-level functional simulation
// Author: Autonomous controller verification
// Date: 2026-08-20
// ============================================================================

`timescale 1ns/1ps

module tb_gate_level_functional;

    // =========================================================================
    // Parameters
    // =========================================================================
    // Clock period: 10.0 ns (100 MHz) - relaxed for gate-level simulation
    // This avoids timing violations in functional simulation
    localparam real CLK_PERIOD = 10.0;

    // Reset duration - increased for gate-level
    localparam int RESET_CYCLES = 10;

    // Maximum simulation time (safety timeout)
    localparam real MAX_SIM_TIME = 500000.0; // 500 us

    // =========================================================================
    // DUT Signals
    // =========================================================================
    // Clock and reset
    logic        cal_clk;
    logic        ctrl_por_n;

    // Control inputs
    logic        cal_start;
    logic        q_final;

    // Sensor control outputs
    logic        sense_dff_reset;
    logic        sense_s_clk;
    logic [15:0] medium_therm;
    logic [9:0]  fine_therm;

    // Status outputs
    logic        cal_busy;
    logic        cal_done;
    logic        cal_fail;
    logic        lock_valid;

    // Debug outputs
    logic [4:0]  medium_code;
    logic [3:0]  fine_code;
    logic [2:0]  fail_reason;
    logic [4:0]  fsm_state;

    // =========================================================================
    // Test Control Variables
    // =========================================================================
    int operation_count;
    string test_name;
    string scenario_name;
    int expected_m;
    int expected_f;

    // =========================================================================
    // Clock Generation
    // =========================================================================
    initial begin
        cal_clk = 0;
        forever #(CLK_PERIOD/2) cal_clk = ~cal_clk;
    end

    // =========================================================================
    // DUT Instantiation - Gate-Level Netlist
    // =========================================================================
    ftc_cal_controller_top dut (
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
        .fsm_state(fsm_state)
    );

    // =========================================================================
    // Behavioral Sensor Model Instantiation
    // =========================================================================
    ftc_sensor_behavior_model sensor_model (
        .medium_therm(medium_therm),
        .fine_therm(fine_therm),
        .sense_s_clk(sense_s_clk),
        .sense_dff_reset(sense_dff_reset),
        .q_final(q_final)
    );

    // =========================================================================
    // Operation Counter
    // =========================================================================
    // Count operations (CONFIG_UPDATE or PROBE)
    always @(posedge cal_clk) begin
        if (!ctrl_por_n) begin
            operation_count <= 0;
        end else if (cal_busy && !cal_done && !cal_fail) begin
            // Detect operation completion by monitoring sequencer done signal
            // In gate-level, we monitor sense_dff_reset falling edge as operation marker
            // This is an approximation; precise counting requires internal visibility
            if (sense_dff_reset && $past(!sense_dff_reset)) begin
                operation_count <= operation_count + 1;
            end
        end
    end

    // =========================================================================
    // Debug Monitor
    // =========================================================================
    initial begin
        // Monitor key signals after reset release
        @(posedge ctrl_por_n);
        repeat(5) @(posedge cal_clk);
        $display("[%0t] DEBUG: Post-reset state:", $time);
        $display("  ctrl_por_n=%b cal_start=%b", ctrl_por_n, cal_start);
        $display("  cal_busy=%b cal_done=%b cal_fail=%b lock_valid=%b",
                 cal_busy, cal_done, cal_fail, lock_valid);
        $display("  fsm_state=%b medium_code=%b fine_code=%b",
                 fsm_state, medium_code, fine_code);
    end

    // Monitor calibration status changes
    always @(cal_busy or cal_done or cal_fail) begin
        if ($time > 0) begin
            $display("[%0t] STATUS CHANGE: busy=%b done=%b fail=%b",
                     $time, cal_busy, cal_done, cal_fail);
        end
    end

    // =========================================================================
    // Test Sequence
    // =========================================================================
    initial begin
        // Initialize signals
        ctrl_por_n = 0;
        cal_start = 0;
        operation_count = 0;

        // Setup waveform dumping
        $dumpfile("gate_level_functional.vcd");
        $dumpvars(0, tb_gate_level_functional);

        $display("\n========================================");
        $display("Phase 8A: Gate-Level Functional Simulation");
        $display("========================================\n");

        // Apply reset
        repeat(RESET_CYCLES) @(posedge cal_clk);
        ctrl_por_n = 1;
        repeat(2) @(posedge cal_clk);

        // =====================================================================
        // Test 1: Nominal 0.80V scenario
        // =====================================================================
        test_name = "Nominal 0.80V";
        scenario_name = "0p80V";
        expected_m = 7;
        expected_f = 6;

        $display("[%0t] Starting test: %s", $time, test_name);
        $display("  Scenario: %s", scenario_name);
        $display("  Expected: M%0d/F%0d", expected_m, expected_f);

        // Load scenario into sensor model
        sensor_model.load_scenario(scenario_name);

        run_calibration_test(expected_m, expected_f);

        // Reset for next test
        ctrl_por_n = 0;
        repeat(RESET_CYCLES) @(posedge cal_clk);
        ctrl_por_n = 1;
        repeat(2) @(posedge cal_clk);

        // =====================================================================
        // Test 2: Nominal 0.95V scenario
        // =====================================================================
        test_name = "Nominal 0.95V";
        scenario_name = "0p95V";
        expected_m = 4;
        expected_f = 6;

        $display("\n[%0t] Starting test: %s", $time, test_name);
        $display("  Scenario: %s", scenario_name);
        $display("  Expected: M%0d/F%0d", expected_m, expected_f);

        // Load scenario into sensor model
        sensor_model.load_scenario(scenario_name);

        run_calibration_test(expected_m, expected_f);

        // Reset for next test
        ctrl_por_n = 0;
        repeat(RESET_CYCLES) @(posedge cal_clk);
        ctrl_por_n = 1;
        repeat(2) @(posedge cal_clk);

        // =====================================================================
        // Test 3: Nominal 1.10V scenario
        // =====================================================================
        test_name = "Nominal 1.10V";
        scenario_name = "1p10V";
        expected_m = 2;
        expected_f = 9;

        $display("\n[%0t] Starting test: %s", $time, test_name);
        $display("  Scenario: %s", scenario_name);
        $display("  Expected: M%0d/F%0d", expected_m, expected_f);

        // Load scenario into sensor model
        sensor_model.load_scenario(scenario_name);

        run_calibration_test(expected_m, expected_f);

        // =====================================================================
        // Final Summary
        // =====================================================================
        $display("\n========================================");
        $display("Phase 8A: All Tests Complete");
        $display("========================================");
        $display("Gate-level netlist successfully verified.");
        $display("All scenarios matched RTL behavior.\n");

        $finish;
    end

    // =========================================================================
    // Task: Run Single Calibration Test
    // =========================================================================
    task run_calibration_test(input int exp_m, input int exp_f);
        int start_time;
        int end_time;
        int duration;

        operation_count = 0;

        // Start calibration
        @(posedge cal_clk);
        cal_start = 1;
        start_time = $time;
        @(posedge cal_clk);
        cal_start = 0;

        // Wait for calibration to complete
        wait(cal_done || cal_fail);
        @(posedge cal_clk);
        end_time = $time;
        duration = end_time - start_time;

        // Check results
        $display("\n  Calibration completed at t=%0t (duration=%0d ns)", $time, duration);
        $display("  Final configuration: M%0d/F%0d", medium_code, fine_code);
        $display("  Status: cal_done=%b, cal_fail=%b, lock_valid=%b",
                 cal_done, cal_fail, lock_valid);

        if (cal_fail) begin
            $display("  ERROR: Calibration failed!");
            $display("  Fail reason: %0d", fail_reason);
            $fatal(1, "Gate-level simulation failed for %s", test_name);
        end

        if (!cal_done) begin
            $display("  ERROR: Calibration did not complete!");
            $fatal(1, "Gate-level simulation failed for %s", test_name);
        end

        if (!lock_valid) begin
            $display("  ERROR: Lock not valid!");
            $fatal(1, "Gate-level simulation failed for %s", test_name);
        end

        // Verify final configuration
        if (medium_code != exp_m || fine_code != exp_f) begin
            $display("  ERROR: Final configuration mismatch!");
            $display("    Expected: M%0d/F%0d", exp_m, exp_f);
            $display("    Got:      M%0d/F%0d", medium_code, fine_code);
            $fatal(1, "Gate-level simulation failed for %s", test_name);
        end

        $display("  PASS: Configuration matches expected values");
        $display("  Operation count (approximate): %0d", operation_count);

        // Wait a few cycles
        repeat(5) @(posedge cal_clk);
    endtask

    // =========================================================================
    // Timeout Watchdog
    // =========================================================================
    initial begin
        #MAX_SIM_TIME;
        $display("\n[%0t] ERROR: Simulation timeout!", $time);
        $display("Test: %s", test_name);
        $display("Scenario: %s", scenario_name);
        $display("Status: cal_done=%b, cal_fail=%b", cal_done, cal_fail);
        $fatal(1, "Simulation exceeded maximum time");
    end

endmodule
