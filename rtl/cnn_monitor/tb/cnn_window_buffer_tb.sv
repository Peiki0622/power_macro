`timescale 1ns/1ps
`default_nettype none

// Exhaustive self-checking unit test for physical-slot snapshot capture.
//
// The test reaches every one of the 32 circular write-pointer states through
// legal sample transfers, then checks both an ordinary request and a request
// sharing its edge with a new endpoint sample.  Two independent scoreboards
// are maintained: expected_physical mirrors the live circular slots, while
// expected_logical retains the newest 32 samples in chronological order.  A
// bug in either physical copying or snapshot_base therefore cannot be hidden
// by comparing only one representation.
module cnn_window_buffer_tb;
    // Clock and reset stimulus group.
    logic clk;                                  // 250 MHz test clock matching the 4 ns sample period.
    logic reset;                                // Active-high asynchronous DUT reset.

    // Sensor-stream stimulus/handshake group.
    logic [5:0] sensor_code;                    // Current candidate Vernier code.
    logic       sample_valid;                   // Requests one sample transfer.
    logic       sample_ready;                   // DUT acceptance qualification.

    // Snapshot request/status group.
    logic inference_request;                    // Requests a complete immutable L32 snapshot.
    logic compute_busy;                         // Held low because this unit test has no compute engine.
    logic inference_ready;                      // Full-window and idle indication from the DUT.
    logic snapshot_start;                       // One-cycle accepted-request pulse.

    // Captured payload and diagnostics group.
    logic [31:0] snapshot_endpoint_index;       // Newest accepted sample index in the snapshot.
    logic [4:0]  snapshot_base;                 // Physical slot containing logical position zero.
    logic [5:0]  snapshot [0:31];               // Physical-slot snapshot image.
    logic        protocol_error;                // Sticky invalid-transfer diagnostic.

    logic [5:0] expected_physical [0:31];
    logic [5:0] expected_logical [0:31];
    integer expected_write_pointer;
    integer expected_sample_count;
    integer expected_next_index;
    integer pointer_case;
    integer same_cycle_case;
    integer sample_number;
    integer check_index;
    integer physical_index;
    integer scenario_count;

    cnn_window_buffer dut (
        .clk(clk),
        .reset(reset),
        .sensor_code(sensor_code),
        .sample_valid(sample_valid),
        .sample_ready(sample_ready),
        .inference_request(inference_request),
        .compute_busy(compute_busy),
        .inference_ready(inference_ready),
        .snapshot_start(snapshot_start),
        .snapshot_endpoint_index(snapshot_endpoint_index),
        .snapshot_base(snapshot_base),
        .snapshot(snapshot),
        .protocol_error(protocol_error)
    );

    always #2 clk = ~clk;

    task automatic fail(input string message);
        begin
            $display("WINDOW_BUFFER_FAIL %s", message);
            $fatal(1);
        end
    endtask

    // Reset both DUT control state and the two software scoreboards.  Data
    // arrays are intentionally not inspected after reset because the RTL's
    // write-before-read contract deliberately leaves them unreset.
    task automatic reset_scenario;
        integer index;
        begin
            @(negedge clk);
            reset = 1'b1;
            sample_valid = 1'b0;
            inference_request = 1'b0;
            repeat (2) @(posedge clk);
            #0.01;
            if (sample_ready || inference_ready || snapshot_start)
                fail("reset did not suppress ready/start controls");
            @(negedge clk);
            reset = 1'b0;
            expected_write_pointer = 0;
            expected_sample_count = 0;
            expected_next_index = 0;
            for (index = 0; index < 32; index = index + 1) begin
                expected_physical[index] = 6'd0;
                expected_logical[index] = 6'd0;
            end
            #0.01;
            if (!sample_ready || inference_ready || protocol_error)
                fail("post-reset handshake state is incorrect");
        end
    endtask

    // Record one accepted sample in both representations.  Once the logical
    // queue is full, its left shift mirrors eviction of the oldest sample;
    // the physical scoreboard instead overwrites only the current ring slot.
    task automatic record_accepted_sample(input logic [5:0] accepted_code);
        integer index;
        begin
            expected_physical[expected_write_pointer] = accepted_code;
            expected_write_pointer = (expected_write_pointer + 1) & 31;
            expected_next_index = expected_next_index + 1;
            if (expected_sample_count < 32) begin
                expected_logical[expected_sample_count] = accepted_code;
                expected_sample_count = expected_sample_count + 1;
            end else begin
                for (index = 0; index < 31; index = index + 1)
                    expected_logical[index] = expected_logical[index + 1];
                expected_logical[31] = accepted_code;
            end
        end
    endtask

    task automatic send_sample(input logic [5:0] accepted_code);
        begin
            @(negedge clk);
            sensor_code = accepted_code;
            sample_valid = 1'b1;
            inference_request = 1'b0;
            #0.01;
            if (!sample_ready)
                fail("legal boundary/sample code was not ready");
            @(posedge clk);
            record_accepted_sample(accepted_code);
            #0.01;
            sample_valid = 1'b0;
        end
    endtask

    // Validate both representations after an accepted request.  Five-bit
    // addition intentionally wraps the reconstructed physical index modulo 32,
    // matching the synthesizable address arithmetic used by the convolution
    // engine rather than relying on a simulation-only modulo operator in RTL.
    task automatic check_captured_snapshot;
        begin
            if (!snapshot_start)
                fail("accepted request did not raise snapshot_start");
            if (snapshot_base !== expected_write_pointer[4:0])
                fail("snapshot_base does not identify the oldest slot");
            if (snapshot_endpoint_index !== (expected_next_index - 1))
                fail("snapshot endpoint index is not the newest sample index");
            for (check_index = 0; check_index < 32;
                 check_index = check_index + 1) begin
                if (snapshot[check_index] !== expected_physical[check_index])
                    fail("physical-slot snapshot copy mismatch");
                physical_index = (snapshot_base + check_index) & 31;
                if (snapshot[physical_index] !== expected_logical[check_index])
                    fail("snapshot_base logical reconstruction mismatch");
            end
        end
    endtask

    initial begin
        clk = 1'b0;
        reset = 1'b0;
        sensor_code = 6'd0;
        sample_valid = 1'b0;
        inference_request = 1'b0;
        compute_busy = 1'b0;
        scenario_count = 0;

        // Each pointer target is reached after the initial full window by
        // accepting pointer_case additional samples.  sample_number modulo 33
        // naturally covers both legal boundary codes 0 and 32.
        for (pointer_case = 0; pointer_case < 32;
             pointer_case = pointer_case + 1) begin
            for (same_cycle_case = 0; same_cycle_case < 2;
                 same_cycle_case = same_cycle_case + 1) begin
                reset_scenario();
                for (sample_number = 0; sample_number < (32 + pointer_case);
                     sample_number = sample_number + 1) begin
                    send_sample(sample_number % 33);
                    if ((sample_number == 30) && inference_ready)
                        fail("occupancy gate opened after only 31 samples");
                end
                if (!inference_ready)
                    fail("occupancy gate did not open after a complete window");
                if (expected_write_pointer != pointer_case)
                    fail("stimulus did not reach the requested pointer state");

                @(negedge clk);
                inference_request = 1'b1;
                sample_valid = same_cycle_case[0];
                sensor_code = 6'd32;
                if (!inference_ready)
                    fail("full idle window rejected a request");
                @(posedge clk);
                if (same_cycle_case != 0)
                    record_accepted_sample(6'd32);
                #0.01;
                check_captured_snapshot();
                @(negedge clk);
                inference_request = 1'b0;
                sample_valid = 1'b0;
                scenario_count = scenario_count + 1;
            end
        end

        if (scenario_count != 64)
            fail("not all pointer/same-cycle scenarios executed");
        $display("CNN_WINDOW_BUFFER_REGRESSION_PASS scenarios=%0d", scenario_count);
        $finish;
    end
endmodule

`default_nettype wire
