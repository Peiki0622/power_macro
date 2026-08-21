// ============================================================================
// FTC Calibration Controller Negative Scenario Testbench
// ============================================================================
// Verifies that the controller correctly detects and reports all failure
// conditions defined in the Phase 0 contract.
//
// Test Coverage:
//   1. Coarse range exhausted (all M values HIGH, no boundary found)
//   2. Coarse backoff underflow (M boundary at M=0 or M=1, cannot backoff)
//   3. Fine range exhausted (all F values HIGH, no boundary found)
//   4. Guard probe not LOW (AMBIGUOUS or HIGH after fine boundary)
//   5. Hold probe not LOW (AMBIGUOUS or HIGH after guard passes)
//
// Each scenario must:
//   - Assert cal_fail
//   - Set correct fail_reason code
//   - Freeze configuration (no further M/F changes)
//   - NOT generate illegal control sequences
//
// Phase: 6 - Protocol assertions and negative-path verification
// Author: Failure detection verification
// Date: 2026-08-20
// ============================================================================

`timescale 1ns/1ps

module tb_ftc_negative_scenarios;

    // =========================================================================
    // Clock and Reset
    // =========================================================================
    logic cal_clk;
    logic ctrl_por_n;

    // Clock generation: 1 GHz (1 ns period)
    initial begin
        cal_clk = 0;
        forever #0.5 cal_clk = ~cal_clk;  // 0.5ns half-period = 1ns period
    end

    // =========================================================================
    // DUT Signals
    // =========================================================================
    logic        cal_start;
    logic        q_final;
    logic        sense_dff_reset;
    logic        sense_s_clk;
    logic [15:0] medium_therm;
    logic [9:0]  fine_therm;
    logic        cal_busy;
    logic        cal_done;
    logic        cal_fail;
    logic        lock_valid;
    logic [4:0]  medium_code;
    logic [3:0]  fine_code;
    logic [2:0]  fail_reason;
    logic [4:0]  fsm_state;
    logic        q_sample_1_event;
    logic        q_sample_2_event;
    logic        config_update_event;
    logic        probe_start_event;

    // =========================================================================
    // DUT Instantiation
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
        .fsm_state(fsm_state),
        .q_sample_1_event(q_sample_1_event),
        .q_sample_2_event(q_sample_2_event),
        .config_update_event(config_update_event),
        .probe_start_event(probe_start_event)
    );

    // =========================================================================
    // Behavioral Sensor Model Instantiation
    // =========================================================================
    ftc_sensor_behavior_model sensor_model (
        .medium_therm(medium_therm),
        .fine_therm(fine_therm),
        .sense_s_clk(sense_s_clk),
        .sense_dff_reset(sense_dff_reset),
        .q_sample_1_event(q_sample_1_event),
        .q_sample_2_event(q_sample_2_event),
        .q_final(q_final)
    );

    // =========================================================================
    // Bind Assertions Module
    // =========================================================================
    bind ftc_cal_controller_top ftc_cal_controller_sva sva_inst (
        .cal_clk(cal_clk),
        .ctrl_por_n(ctrl_por_n),
        .cal_start(cal_start),
        .cal_busy(cal_busy),
        .cal_done(cal_done),
        .cal_fail(cal_fail),
        .lock_valid(lock_valid),
        .sense_dff_reset(sense_dff_reset),
        .sense_s_clk(sense_s_clk),
        .medium_therm(medium_therm),
        .fine_therm(fine_therm),
        .q_sample_1_event(q_sample_1_event),
        .q_sample_2_event(q_sample_2_event),
        .config_update_event(config_update_event),
        .probe_start_event(probe_start_event),
        .q_class(dut.q_class),
        .q_class_valid(dut.q_class_valid),
        .medium_code(medium_code),
        .fine_code(fine_code),
        .fsm_state(fsm_state)
    );

    // =========================================================================
    // Test Control
    // =========================================================================
    initial begin
        $display("=== FTC Calibration Controller Negative Scenario Tests ===");
        $display("Time: %0t", $time);
        $display("");

        // Initialize
        ctrl_por_n = 0;
        cal_start = 0;

        // Power-on reset
        repeat(10) @(posedge cal_clk);
        ctrl_por_n = 1;
        repeat(5) @(posedge cal_clk);

        // Run all eight deterministic adversarial response scenarios required
        // by Phase 6.  The model's per-code occurrence table distinguishes the
        // independent guard and hold probes at the same final configuration.
        run_scenario("coarse_range_fail", 3'b001);      // FAIL_COARSE_RANGE
        run_scenario("backoff_underflow", 3'b010);      // FAIL_COARSE_BACKOFF_UNDERFLOW
        run_scenario("fine_range_fail", 3'b011);        // FAIL_FINE_RANGE
        run_scenario("guard_range_fail", 3'b100);      // FAIL_GUARD_RANGE
        run_scenario("guard_not_low_high", 3'b101);     // FAIL_GUARD_NOT_LOW
        run_scenario("guard_not_low_ambig", 3'b101);    // FAIL_GUARD_NOT_LOW
        run_scenario("hold_not_low_high", 3'b110);     // FAIL_HOLD_NOT_LOW
        run_scenario("hold_not_low_ambig", 3'b110);    // FAIL_HOLD_NOT_LOW

        $display("");
        $display("=== All Negative Scenario Tests Passed ===");
        $finish;
    end

    // =========================================================================
    // Scenario Execution Task
    // =========================================================================
    task automatic run_scenario(
        input string scenario_name,
        input logic [2:0] expected_fail_reason
    );
        int timeout_cycles;
        logic [3:0] final_m;
        logic [3:0] final_f;

        $display("[Test] Negative scenario: %s, Expected fail_reason=%0d",
                 scenario_name, expected_fail_reason);

        // Load scenario into sensor model
        sensor_model.load_scenario(scenario_name);
        sensor_model.reset_stats();

        // Reset DUT
        ctrl_por_n = 0;
        cal_start = 0;
        repeat(10) @(posedge cal_clk);
        ctrl_por_n = 1;
        repeat(5) @(posedge cal_clk);

        // Start calibration
        $display("[%0t] Starting calibration", $time);
        cal_start = 1;
        @(posedge cal_clk);
        cal_start = 0;

        // Wait for completion or timeout
        timeout_cycles = 2000;
        repeat(timeout_cycles) begin
            @(posedge cal_clk);
            if (cal_done || cal_fail) break;
        end

        // Check result
        if (!cal_fail) begin
            $display("[%0t] ERROR: cal_fail not asserted for scenario %s",
                     $time, scenario_name);
            $fatal(1);
        end

        if (cal_done) begin
            $display("[%0t] ERROR: cal_done asserted during failure scenario %s",
                     $time, scenario_name);
            $fatal(1);
        end

        // Verify fail_reason
        if (fail_reason !== expected_fail_reason) begin
            $display("[%0t] ERROR: Wrong fail_reason. Expected %0d, Got %0d",
                     $time, expected_fail_reason, fail_reason);
            $fatal(1);
        end

        // Record final configuration
        final_m = medium_code;
        final_f = fine_code;

        // Verify configuration freeze after failure
        repeat(20) @(posedge cal_clk);
        if (medium_code !== final_m || fine_code !== final_f) begin
            $display("[%0t] ERROR: Configuration changed after cal_fail! Was M%0d/F%0d, Now M%0d/F%0d",
                     $time, final_m, final_f, medium_code, fine_code);
            $fatal(1);
        end

        // Verify sensor model reports no violations
        sensor_model.print_stats();
        if (sensor_model.violation_count > 0) begin
            $display("[%0t] ERROR: Sensor model detected %0d violations",
                     $time, sensor_model.violation_count);
            $fatal(1);
        end

        $display("PASS: %s detected, fail_reason=%0d, config frozen at M%0d/F%0d",
                 scenario_name, fail_reason, final_m, final_f);
        $display("");

    endtask

    // =========================================================================
    // Waveform Dumping
    // =========================================================================
    initial begin
        $dumpfile("phase6_negative/negative_scenarios.vcd");
        $dumpvars(0, tb_ftc_negative_scenarios);
    end

endmodule
