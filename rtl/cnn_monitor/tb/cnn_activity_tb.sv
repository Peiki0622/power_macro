`timescale 1ns/1ps
`default_nettype none

// Single-window activity-characterization testbench.
//
// This file is simulation-only.  It intentionally keeps sample_valid low
// throughout computation, so the VCD interval measures the fixed CNN request
// rather than unrelated live-window acquisition traffic.  The synthesizable
// cnn_monitor hierarchy is instantiated unchanged and no observation counter
// is added to that hierarchy.
module cnn_activity_tb;
    // Clock/reset and complete cnn_monitor port group.
    logic clk;
    logic reset;
    logic [5:0] sensor_code;
    logic sample_valid;
    logic sample_ready;
    logic inference_request;
    logic inference_ready;
    logic busy;
    logic result_valid;
    logic safe_critical_decision;
    logic signed [31:0] safe_logit;
    logic signed [31:0] critical_logit;
    logic signed [32:0] logit_difference;
    logic [31:0] result_endpoint_index;
    logic numeric_overflow;
    logic protocol_error;

    // File and expected-payload group.  A compact whitespace vector file keeps
    // testbench parsing deterministic without making JSON parsing part of RTL.
    string vector_path;
    string vcd_path;
    string result_path;
    string pattern_id;
    integer vector_file;
    integer result_file;
    integer status;
    integer index;
    integer cycles;
    integer expected_safe;
    integer expected_critical;
    integer expected_decision;
    logic [5:0] vector_codes [0:31];

    // The release hardware remains the exact 16-lane configuration.  All port
    // connections are explicit so an interface change cannot silently leave a
    // measurement signal unconnected.
    cnn_monitor #(.MAC_LANES(16)) dut (
        .clk(clk), .reset(reset),
        .sensor_code(sensor_code), .sample_valid(sample_valid),
        .sample_ready(sample_ready), .inference_request(inference_request),
        .inference_ready(inference_ready), .busy(busy), .result_valid(result_valid),
        .safe_critical_decision(safe_critical_decision), .safe_logit(safe_logit),
        .critical_logit(critical_logit), .logit_difference(logit_difference),
        .result_endpoint_index(result_endpoint_index), .numeric_overflow(numeric_overflow),
        .protocol_error(protocol_error)
    );

    // The compiler ROM model is functionally checked at a 4 ns period by the
    // established regression.  Activity is later normalized per cycle, so this
    // testbench preserves that known-good simulation constraint.
    initial begin
        clk = 1'b0;
        forever #2.0 clk = ~clk;
    end

    task automatic fail(input string message);
        begin
            $display("ACTIVITY_TB_ERROR: %s at time %0t", message, $time);
            $fatal(1, "%s", message);
        end
    endtask

    task automatic apply_fixed_reset;
        begin
            // Two asserted clock edges and four idle edges after deassertion
            // are fixed for every pattern; the VCD remains disabled here.
            @(negedge clk);
            reset = 1'b1;
            sensor_code = 6'd0;
            sample_valid = 1'b0;
            inference_request = 1'b0;
            repeat (2) @(posedge clk);
            @(negedge clk);
            reset = 1'b0;
            repeat (4) @(posedge clk);
        end
    endtask

    task automatic load_window;
        begin
            // Exactly one legal code enters per edge.  This activity precedes
            // dumpon and therefore cannot create a pattern-dependent compute
            // metric through the acquisition interface.
            for (index = 0; index < 32; index = index + 1) begin
                @(negedge clk);
                sensor_code = vector_codes[index];
                sample_valid = 1'b1;
                if (!sample_ready)
                    fail("legal activity-window code was backpressured");
                @(posedge clk);
            end
            @(negedge clk);
            sample_valid = 1'b0;
            sensor_code = 6'd0;
            if (!inference_ready)
                fail("L32 prefill did not make inference_ready high");
            repeat (4) @(posedge clk);
        end
    endtask

    initial begin
        reset = 1'b1;
        sensor_code = 6'd0;
        sample_valid = 1'b0;
        inference_request = 1'b0;
        if (!$value$plusargs("VECTOR=%s", vector_path)
            || !$value$plusargs("VCD=%s", vcd_path)
            || !$value$plusargs("RESULT=%s", result_path))
            $fatal(1, "VECTOR, VCD, and RESULT plusargs are required");
        vector_file = $fopen(vector_path, "r");
        if (!vector_file)
            $fatal(1, "cannot open activity vector file");
        status = $fscanf(vector_file, "%s", pattern_id);
        for (index = 0; index < 32; index = index + 1)
            status = $fscanf(vector_file, "%d", vector_codes[index]);
        status = $fscanf(vector_file, "%d %d %d", expected_safe,
                         expected_critical, expected_decision);
        $fclose(vector_file);

        // Declare the complete DUT hierarchy once, then suppress dumping until
        // the request interval.  This retains internal groups needed by the
        // offline classifier while excluding reset and sample-fill transients.
        $dumpfile(vcd_path);
        $dumpvars(0, dut);
        $dumpoff;
        apply_fixed_reset();
        load_window();

        // Start dumping immediately before request assertion.  The following
        // rising edge atomically snapshots the window and begins the fixed CNN
        // schedule; future sample traffic remains disabled through result.
        @(negedge clk);
        $dumpon;
        inference_request = 1'b1;
        @(posedge clk);
        #0.01;
        inference_request = 1'b0;
        if (!busy)
            fail("accepted activity request did not assert busy");

        cycles = 0;
        while (!result_valid && cycles < 12900) begin
            @(negedge clk);
            sample_valid = 1'b0;
            inference_request = 1'b0;
            cycles = cycles + 1;
            @(posedge clk);
            #0.01;
        end
        if (cycles != 12892)
            fail("activity request latency differs from fixed 12892 cycles");
        if (numeric_overflow || protocol_error)
            fail("activity execution raised a sticky error");
        if (($signed(safe_logit) !== expected_safe)
            || ($signed(critical_logit) !== expected_critical)
            || (safe_critical_decision !== expected_decision))
            fail("activity result differs from cycle-model expected payload");
        $dumpoff;

        // A fixed postamble also verifies that result_valid is a one-cycle
        // pulse, without adding post-result signal changes to the VCD window.
        repeat (4) @(posedge clk);
        if (result_valid)
            fail("result_valid extended beyond one cycle");
        result_file = $fopen(result_path, "w");
        if (!result_file)
            $fatal(1, "cannot create activity result file");
        $fdisplay(result_file, "%s %0d %0d %0d %0d %0d %0d", pattern_id,
                  cycles, safe_logit, critical_logit, safe_critical_decision,
                  numeric_overflow, protocol_error);
        $fclose(result_file);
        $display("CNN_ACTIVITY_PASS pattern=%s cycles=%0d", pattern_id, cycles);
        $finish;
    end
endmodule

`default_nettype wire
