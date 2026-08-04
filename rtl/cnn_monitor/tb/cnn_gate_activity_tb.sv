`timescale 1ns/1ps
`default_nettype none

// Gate-level, single-window activity characterization testbench.
//
// This simulation-only module instantiates the frozen mapped 16-lane netlist.
// It never compiles CNN RTL as the DUT.  The public ROM Q compatibility force
// is restricted to the mapped hard-macro output and receives only that same
// model instance's Q_ value; addresses, enables, timing, and all consumers
// remain the mapped implementation.
module cnn_gate_activity_tb;
    // Clock/reset and mapped top-level input group.
    logic clk;
    logic reset;
    logic [5:0] sensor_code;
    logic sample_valid;
    logic inference_request;

    // Mapped top-level output group checked against fixed cycle-model data.
    wire sample_ready;
    wire inference_ready;
    wire busy;
    wire result_valid;
    wire safe_critical_decision;
    wire signed [31:0] safe_logit;
    wire signed [31:0] critical_logit;
    wire signed [32:0] logit_difference;
    wire [31:0] result_endpoint_index;
    wire numeric_overflow;
    wire protocol_error;

    // Per-run vector, result, marker, and optional SDF controls.
    string vector_path;
    string result_path;
    string marker_path;
    integer vector_file;
    integer result_file;
    integer marker_file;
    integer status;
    integer index;
    integer cycles;
    integer expected_safe;
    integer expected_critical;
    integer expected_decision;
    logic [5:0] vector_codes [0:31];
    time acquisition_start;
    time acquisition_end;
    time compute_start;
    time compute_end;

    // The frozen task-two mapped top is explicit: an RTL module must never be
    // substituted here, otherwise generated SAIF would not describe the DDC.
    cnn_monitor_MAC_LANES16 dut (
        .clk(clk), .reset(reset), .sensor_code(sensor_code),
        .sample_valid(sample_valid), .sample_ready(sample_ready),
        .inference_request(inference_request), .inference_ready(inference_ready),
        .busy(busy), .result_valid(result_valid),
        .safe_critical_decision(safe_critical_decision), .safe_logit(safe_logit),
        .critical_logit(critical_logit), .logit_difference(logit_difference),
        .result_endpoint_index(result_endpoint_index), .numeric_overflow(numeric_overflow),
        .protocol_error(protocol_error)
    );

    // The legacy ROM model requires this verified 4 ns period.  It therefore
    // establishes a 250 MHz gate baseline; this testbench makes no 500 MHz
    // timing or power claim.
    initial begin
        clk = 1'b0;
        forever #2.0 clk = ~clk;
    end

    // Refresh only the public macro Q after every synchronous ROM response.
    // The 1.1 ns delay clears both macro and standard-cell model outputs while
    // leaving 0.9 ns before the following falling edge.  This is a testbench
    // visibility adapter, not a data injection into weight_word or CNN RTL.
    always @(posedge clk) begin
        #1.1;
        force dut.convolution_engine.weight_rom.u_weight_rom.Q =
              dut.convolution_engine.weight_rom.u_weight_rom.Q_;
    end

    task automatic fail(input string message);
        begin
            $display("GATE_ACTIVITY_FAIL: %s at %0t", message, $time);
            $fatal(1, "%s", message);
        end
    endtask

    task automatic fixed_reset;
        begin
            // Reset and post-reset settling are identical for every run and
            // occur with dumping disabled, so no initialization activity leaks
            // into acquisition/compute/end-to-end SAIF intervals.
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

    initial begin
        reset = 1'b1;
        sensor_code = 6'd0;
        sample_valid = 1'b0;
        inference_request = 1'b0;
        if (!$value$plusargs("VECTOR=%s", vector_path) ||
            !$value$plusargs("RESULT=%s", result_path) ||
            !$value$plusargs("MARKERS=%s", marker_path))
            $fatal(1, "VECTOR, RESULT, and MARKERS plusargs are required");
`ifdef GATE_SDF
        // VCS requires the SDF pathname to be a compile-time string, not a
        // runtime plusarg.  The SDF driver copies the frozen file beside simv
        // and defines GATE_SDF; the functional build does not elaborate this
        // task at all and therefore cannot accidentally annotate timing.
        $sdf_annotate("cnn_monitor_mapped.sdf", dut);
`endif

        vector_file = $fopen(vector_path, "r");
        if (!vector_file)
            $fatal(1, "cannot open gate vector");
        status = $fscanf(vector_file, "%d %d %d", expected_safe, expected_critical,
                         expected_decision);
        for (index = 0; index < 32; index = index + 1)
            status = $fscanf(vector_file, "%d", vector_codes[index]);
        $fclose(vector_file);

        $dumpfile("gate_activity.vcd");
        $dumpvars(0, dut);
        $dumpoff;
        fixed_reset();

        // Acquisition begins before the first legal sample and ends only after
        // the final 32nd accepted sample.  The same waveform remains active
        // through compute so later tooling can extract each exact interval.
        acquisition_start = $time;
        $dumpon;
        // Launch immediately after a rising edge so each mapped input port
        // has a fixed 3.8 ns setup interval before the next capture edge.
        // The previous half-cycle launch was sufficient for RTL but not for
        // the mapped port-to-window-buffer propagation path.
        @(posedge clk);
        #0.2;
        for (index = 0; index < 32; index = index + 1) begin
            sensor_code = vector_codes[index];
            sample_valid = 1'b1;
            if (!sample_ready)
                fail("mapped sample interface backpressured a legal window");
            @(posedge clk);
            #0.2;
        end
        sample_valid = 1'b0;
        sensor_code = 6'd0;
        acquisition_end = $time;
        // The mapped ready path spans more than one gate level.  The fixed
        // four-cycle preamble is part of the frozen activity protocol, so
        // check readiness after that deterministic settling interval rather
        // than applying the zero-delay RTL observation point to gate logic.
        repeat (4) @(posedge clk);
        #1.1;
        if (!inference_ready)
            fail("mapped L32 buffer did not become inference-ready");

        @(negedge clk);
        #0.2;
        compute_start = $time;
        inference_request = 1'b1;
        @(posedge clk);
        #1.1;
        inference_request = 1'b0;
        if (!busy)
            fail("mapped request did not assert busy");
        cycles = 0;
        while (!result_valid && cycles < 12900) begin
            @(negedge clk);
            cycles = cycles + 1;
            @(posedge clk);
            #1.1;
        end
        compute_end = $time;
        if (cycles != 12892)
            fail("mapped latency differs from frozen 12892-cycle contract");
        if (numeric_overflow || protocol_error)
            fail("mapped execution raised overflow or protocol error");
        if ($signed(safe_logit) !== expected_safe ||
            $signed(critical_logit) !== expected_critical ||
            safe_critical_decision !== expected_decision)
            fail("mapped logits or decision differ from expected payload");
        $dumpoff;

        // Result-valid is an architectural one-cycle indication and is checked
        // after capture without adding variable activity to measured windows.
        @(posedge clk);
        #1.1;
        if (result_valid)
            fail("mapped result_valid exceeded one cycle");
        result_file = $fopen(result_path, "w");
        marker_file = $fopen(marker_path, "w");
        if (!result_file || !marker_file)
            $fatal(1, "cannot create gate result or marker output");
        $fdisplay(result_file, "%0d %0d %0d %0d %0d %0d", cycles, safe_logit,
                  critical_logit, safe_critical_decision, numeric_overflow, protocol_error);
        $fdisplay(marker_file, "acquisition_start_ps=%0t", acquisition_start);
        $fdisplay(marker_file, "acquisition_end_ps=%0t", acquisition_end);
        $fdisplay(marker_file, "compute_start_ps=%0t", compute_start);
        $fdisplay(marker_file, "compute_end_ps=%0t", compute_end);
        $fdisplay(marker_file, "end_to_end_start_ps=%0t", acquisition_start);
        $fdisplay(marker_file, "end_to_end_end_ps=%0t", compute_end);
        $fclose(result_file);
        $fclose(marker_file);
        release dut.convolution_engine.weight_rom.u_weight_rom.Q;
        $display("GATE_ACTIVITY_PASS cycles=%0d", cycles);
        $finish(0);
    end
endmodule

`default_nettype wire
