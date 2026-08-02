`timescale 1ns/1ps
`default_nettype none

// Self-checking full-regression testbench for the release 16-lane CNN monitor.
// Testbench tasks use file I/O and hierarchy intentionally; none of this file
// is included in synthesis.  All expected values originate from the independent
// cycle model and the authenticated task-one parameter package.
module cnn_monitor_tb;
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

    integer vectors_file;
    integer tensors_file;
    integer trace_file;
    integer special_file;
    integer scan_status;
    integer vector_count;
    integer tensor_count;
    integer trace_count;
    integer special_count;
    integer vector_index;
    integer code_index;
    integer check_index;
    integer error_count;
    integer expected_decision;
    integer expected_trace_cycle;
    integer expected_event;
    integer expected_layer;
    integer expected_position;
    integer expected_output_base;
    integer expected_input_channel;
    integer expected_kernel_tap;
    integer expected_rom_address;
    integer expected_activation;
    integer expected_product_valid;
    integer expected_product [0:15];
    integer expected_pipeline_accumulator [0:15];
    longint signed expected_safe;
    longint signed expected_critical;
    longint signed expected_difference;
    longint signed expected_accumulator [0:1];
    logic [5:0] vector_codes [0:31];
    integer expected_relu1 [0:575];
    integer expected_relu2 [0:575];
    integer expected_relu3 [0:575];
    integer expected_summary [0:53];
    string vector_name;
    string tensor_name;
    string vectors_path;
    string tensors_path;
    string trace_path;
    string special_path;
    string vcd_path;

    cnn_monitor #(.MAC_LANES(16)) dut (
        .clk(clk),
        .reset(reset),
        .sensor_code(sensor_code),
        .sample_valid(sample_valid),
        .sample_ready(sample_ready),
        .inference_request(inference_request),
        .inference_ready(inference_ready),
        .busy(busy),
        .result_valid(result_valid),
        .safe_critical_decision(safe_critical_decision),
        .safe_logit(safe_logit),
        .critical_logit(critical_logit),
        .logit_difference(logit_difference),
        .result_endpoint_index(result_endpoint_index),
        .numeric_overflow(numeric_overflow),
        .protocol_error(protocol_error)
    );

    initial begin
        clk = 1'b0;
        forever #2.0 clk = ~clk;
    end

    // A waveform is opt-in so ordinary regressions remain compact.  Power
    // characterization passes +VCD=<run-local-path> and receives one VCD in
    // that same run directory rather than scattering simulator artifacts.
    initial begin
        if ($value$plusargs("VCD=%s", vcd_path)) begin
            $dumpfile(vcd_path);
            $dumpvars(0, dut);
        end
    end

    task automatic fail(input string message);
        begin
            error_count = error_count + 1;
            $display("ERROR: %s at time %0t", message, $time);
        end
    endtask

    task automatic reset_design;
        begin
            @(negedge clk);
            reset = 1'b1;
            sensor_code = 6'd0;
            sample_valid = 1'b0;
            inference_request = 1'b0;
            repeat (2) @(posedge clk);
            @(negedge clk);
            reset = 1'b0;
            @(posedge clk);
            #0.01;
            if (busy || result_valid || protocol_error || numeric_overflow)
                fail("reset did not restore idle, clear status, and suppress result_valid");
        end
    endtask

    task automatic load_vector_window;
        begin
            // One legal sample is presented per clock.  Readiness must never
            // depend on compute state; this prefill also checks the 0/32 limits.
            for (code_index = 0; code_index < 32; code_index = code_index + 1) begin
                @(negedge clk);
                sensor_code = vector_codes[code_index];
                sample_valid = 1'b1;
                if (!sample_ready)
                    fail("legal sensor code was unexpectedly backpressured");
                @(posedge clk);
            end
            @(negedge clk);
            sample_valid = 1'b0;
            if (!inference_ready)
                fail("complete L32 window did not make inference_ready high");
        end
    endtask

    task automatic compare_layer_tensor(input integer layer_number);
        integer observed;
        begin
            // Milestone checks occur after the layer's final write edge.  They
            // prove all 576 activation entries, including same-padding edges,
            // rather than relying only on final logits to expose corruption.
            for (check_index = 0; check_index < 576;
                 check_index = check_index + 1) begin
                if (layer_number == 1)
                    // final_features is physical bank A for both conv1 and
                    // conv3.  This milestone samples it before conv2 starts,
                    // proving the storage reuse did not hide a conv1 mismatch.
                    observed = dut.convolution_engine.final_features[check_index];
                else if (layer_number == 2)
                    observed = dut.convolution_engine.feature_bank_b[check_index];
                else
                    observed = dut.convolution_engine.final_features[check_index];
                if ((layer_number == 1 && observed !== expected_relu1[check_index])
                    || (layer_number == 2 && observed !== expected_relu2[check_index])
                    || (layer_number == 3 && observed !== expected_relu3[check_index]))
                    fail($sformatf("layer %0d activation mismatch at flat address %0d",
                                   layer_number, check_index));
            end
        end
    endtask

    task automatic check_upcoming_trace(input integer compute_cycle);
        integer trace_lane;
        begin
            // Each trace row has ten scalar fields followed by all sixteen
            // product registers and all sixteen accumulators.  Reading every
            // field on every cycle detects both datapath age errors and trace
            // serialization drift; classifier checks use lanes zero and one.
            scan_status = $fscanf(trace_file,
                                  "%d %d %d %d %d %d %d %d %d %d",
                                  expected_trace_cycle, expected_event,
                                  expected_layer, expected_position,
                                  expected_output_base, expected_input_channel,
                                  expected_kernel_tap, expected_rom_address,
                                  expected_activation,
                                  expected_product_valid);
            if (scan_status != 10)
                fail("cycle trace ended before the fixed schedule");
            for (trace_lane = 0; trace_lane < 16;
                 trace_lane = trace_lane + 1)
                scan_status = $fscanf(trace_file, "%d",
                                      expected_product[trace_lane]);
            for (trace_lane = 0; trace_lane < 16;
                 trace_lane = trace_lane + 1)
                scan_status = $fscanf(
                    trace_file, "%d",
                    expected_pipeline_accumulator[trace_lane]);
            if (expected_trace_cycle != compute_cycle)
                fail("cycle trace index is not contiguous");

            // Event codes follow the complete registered schedule: 1 bias,
            // 2 ROM issue, 3/4 drain, 5 requant prepare, 6 requant write,
            // 7/8/9 pool init/scan/finalize, 10 class bias, 11 class product
            // issue, 12 class drain, 13 logit prepare, and 14 result commit.
            // State is sampled on the preceding negedge, so it describes the
            // operation executed by the immediately following rising edge.
            case (expected_event)
                1: begin
                    if (compute_cycle == 1) begin
                        if (!(dut.convolution_engine.state == 3'd0
                              && dut.snapshot_start))
                            fail("first bias cycle lacks the registered snapshot launch");
                    end else if (dut.convolution_engine.state != 2'd1)
                        fail("convolution bias event differs from cycle model");
                    if ((dut.convolution_engine.layer_id != expected_layer)
                        || (dut.convolution_engine.output_position != expected_position)
                        || (dut.convolution_engine.output_base != expected_output_base))
                        fail("convolution bias address differs from cycle model");
                end
                2: begin
                    if (dut.convolution_engine.state != 3'd2)
                        fail("convolution ROM issue differs from cycle model");
                    if ((dut.convolution_engine.layer_id != expected_layer)
                        || (dut.convolution_engine.output_position != expected_position)
                        || (dut.convolution_engine.output_base != expected_output_base)
                        || (dut.convolution_engine.input_channel != expected_input_channel)
                        || (dut.convolution_engine.kernel_tap != expected_kernel_tap)
                        || (dut.convolution_engine.rom_read_address
                            != expected_rom_address)
                        || ($signed(dut.convolution_engine.source_activation)
                            != expected_activation))
                        fail("convolution ROM/activation issue differs from cycle model");
                end
                3: if (dut.convolution_engine.state != 3'd3)
                    fail("convolution first drain differs from cycle model");
                4: if (dut.convolution_engine.state != 3'd4)
                    fail("convolution second drain differs from cycle model");
                5: if (dut.convolution_engine.state != 3'd5)
                    fail("convolution requantize prepare differs from cycle model");
                6: if ((dut.convolution_engine.state != 3'd6)
                       || (dut.convolution_engine.prepared_layer_id
                           != expected_layer)
                       || (dut.convolution_engine.prepared_output_position
                           != expected_position)
                       || (dut.convolution_engine.prepared_output_base
                           != expected_output_base))
                    fail("convolution registered write target differs from cycle model");
                7: if (!(dut.pool_classifier.state == 3'd0
                         && dut.convolution_done))
                    fail("pool initialization cycle differs from cycle model");
                8: if ((dut.pool_classifier.state != 3'd1)
                       || (dut.pool_classifier.pool_position != expected_position))
                    fail("pool scan address differs from cycle model");
                9: if (dut.pool_classifier.state != 3'd2)
                    fail("pool finalization cycle differs from cycle model");
                10: if (dut.pool_classifier.state != 3'd3)
                    fail("classifier bias cycle differs from cycle model");
                11: if ((dut.pool_classifier.state != 3'd4)
                       || (dut.pool_classifier.summary_index != expected_position))
                    fail("classifier summary/weight address differs from cycle model");
                12: if (dut.pool_classifier.state != 3'd5)
                    fail("classifier product drain differs from cycle model");
                13: if (dut.pool_classifier.state != 3'd6)
                    fail("classifier logit prepare differs from cycle model");
                14: if (dut.pool_classifier.state != 3'd7)
                    fail("classifier result cycle differs from cycle model");
                default: fail("unknown expected trace event code");
            endcase

            // Product/accumulator comparisons are made before the event edge,
            // exactly matching the cycle model's register-age convention.
            if ((expected_event >= 2) && (expected_event <= 6)) begin
                if (dut.convolution_engine.product_valid
                    !== expected_product_valid[0])
                    fail("convolution product-valid age differs from cycle model");
                for (trace_lane = 0; trace_lane < 16;
                     trace_lane = trace_lane + 1) begin
                    if ($signed(dut.convolution_engine.product_pipe[trace_lane])
                        !== expected_product[trace_lane][15:0])
                        fail($sformatf("convolution product mismatch in lane %0d",
                                       trace_lane));
                    if ($signed(dut.convolution_engine.accumulators[trace_lane])
                        !== expected_pipeline_accumulator[trace_lane][19:0])
                        fail($sformatf("convolution accumulator mismatch in lane %0d",
                                       trace_lane));
                end
            end else if ((expected_event >= 11)
                         && (expected_event <= 13)) begin
                if (dut.pool_classifier.classifier_product_valid
                    !== expected_product_valid[0])
                    fail("classifier product-valid age differs from cycle model");
                for (trace_lane = 0; trace_lane < 2;
                     trace_lane = trace_lane + 1) begin
                    if ($signed(dut.pool_classifier.classifier_product[trace_lane])
                        !== expected_product[trace_lane][15:0])
                        fail($sformatf("classifier product mismatch in lane %0d",
                                       trace_lane));
                    if ($signed(dut.pool_classifier.classifier_accumulator[trace_lane])
                        !== expected_pipeline_accumulator[trace_lane][19:0])
                        fail($sformatf("classifier accumulator mismatch in lane %0d",
                                       trace_lane));
                end
            end
        end
    endtask

    task automatic verify_final_payload(input integer expected_endpoint,
                                        input integer check_internal);
        begin
            if ($signed(safe_logit) !== expected_safe[31:0])
                fail("Safe INT32 logit differs from cycle model");
            if ($signed(critical_logit) !== expected_critical[31:0])
                fail("Critical INT32 logit differs from cycle model");
            if ($signed(logit_difference) !== expected_difference[32:0])
                fail("33-bit logit difference differs from cycle model");
            if (safe_critical_decision !== expected_decision[0])
                fail("Safe/Critical decision or tie policy differs from cycle model");
            if (result_endpoint_index !== expected_endpoint)
                fail("result endpoint does not identify the snapshotted window");
            if (numeric_overflow)
                fail("legal directed window asserted numeric_overflow");
            if (check_internal) begin
                for (check_index = 0; check_index < 54;
                     check_index = check_index + 1)
                    if (dut.pool_classifier.summary_features[check_index]
                        !== expected_summary[check_index][7:0])
                        fail($sformatf("summary feature mismatch at address %0d",
                                       check_index));
                if (($signed(dut.pool_classifier.classifier_accumulator[0])
                     !== expected_accumulator[0][19:0])
                    || ($signed(dut.pool_classifier.classifier_accumulator[1])
                        !== expected_accumulator[1][19:0]))
                    fail("classifier accumulator differs from cycle model");
            end
        end
    endtask

    task automatic monitor_active_inference(
        input integer expected_endpoint,
        input integer trace_enable,
        input integer future_mode,
        input integer inject_busy_request,
        input integer check_internal,
        input integer cleanup_after_result
    );
        integer compute_cycle;
        begin
            compute_cycle = 0;
            while (!result_valid && compute_cycle < 12900) begin
                @(negedge clk);
                compute_cycle = compute_cycle + 1;
                inference_request =
                    (inject_busy_request && (compute_cycle == 10));
                sample_valid = 1'b1;
                if (future_mode == 0)
                    sensor_code = (compute_cycle * 7 + vector_index) % 33;
                else if (future_mode == 1)
                    sensor_code = 6'd0;
                else
                    sensor_code = 6'd32;
                if (!sample_ready)
                    fail("continuous legal sample was lost while CNN was busy");
                if (trace_enable)
                    check_upcoming_trace(compute_cycle);
                @(posedge clk);
                #0.01;
                if (check_internal && (compute_cycle == 640))
                    compare_layer_tensor(1);
                else if (check_internal && (compute_cycle == 6720))
                    compare_layer_tensor(2);
                else if (check_internal && (compute_cycle == 12800))
                    compare_layer_tensor(3);
            end
            if (compute_cycle != 12892)
                fail($sformatf("request-to-result latency was %0d, expected 12892",
                               compute_cycle));
            if (!result_valid)
                fail("result_valid did not arrive within fixed schedule");
            verify_final_payload(expected_endpoint, check_internal);
            if (cleanup_after_result) begin
                @(negedge clk);
                inference_request = 1'b0;
                sample_valid = 1'b0;
                @(posedge clk);
                #0.01;
                if (result_valid)
                    fail("result_valid lasted longer than one cycle");
            end
        end
    endtask

    task automatic launch_loaded_window(
        input integer expected_endpoint,
        input integer trace_enable,
        input integer future_mode,
        input integer inject_busy_request
    );
        begin
            @(negedge clk);
            inference_request = 1'b1;
            sample_valid = 1'b0;
            if (!inference_ready)
                fail("request launch attempted without inference_ready");
            @(posedge clk);
            #0.01;
            if (!busy || !dut.snapshot_start)
                fail("accepted request did not reserve compute and pulse snapshot_start");
            monitor_active_inference(expected_endpoint, trace_enable,
                                     future_mode, inject_busy_request, 1, 1);
        end
    endtask

    task automatic read_special_record;
        begin
            scan_status = $fscanf(special_file, "%s", vector_name);
            if (scan_status != 1)
                fail("failed to read special integration record");
            for (code_index = 0; code_index < 32; code_index = code_index + 1)
                scan_status = $fscanf(special_file, "%d", vector_codes[code_index]);
            scan_status = $fscanf(special_file, "%d %d %d %d", expected_safe,
                                  expected_critical, expected_difference,
                                  expected_decision);
        end
    endtask

    task automatic test_reset_interruption_and_recovery;
        integer interrupted_cycle;
        begin
            // Start real work, interrupt it well inside conv1, and prove no
            // stale result escapes.  The following integration tests then
            // refill and infer normally, providing the recovery half of test.
            reset_design();
            for (code_index = 0; code_index < 32; code_index = code_index + 1)
                vector_codes[code_index] = 6'd15;
            load_vector_window();
            @(negedge clk);
            inference_request = 1'b1;
            @(posedge clk);
            #0.01;
            for (interrupted_cycle = 0; interrupted_cycle < 100;
                 interrupted_cycle = interrupted_cycle + 1) begin
                @(negedge clk);
                inference_request = 1'b0;
                sample_valid = 1'b1;
                sensor_code = 6'd0;
                @(posedge clk);
                #0.01;
                if (result_valid)
                    fail("interrupted inference produced an early result");
            end
            @(negedge clk);
            reset = 1'b1;
            sample_valid = 1'b0;
            repeat (2) @(posedge clk);
            @(negedge clk);
            reset = 1'b0;
            @(posedge clk);
            #0.01;
            if (busy || result_valid || inference_ready
                || (dut.window_buffer.retained_sample_count != 0))
                fail("reset interruption did not discard partial transaction and samples");
            $display("PASS_SPECIAL reset_interruption_and_recovery");
        end
    endtask

    task automatic test_classifier_numeric_boundaries;
        begin
            // This simulation-only directed test isolates the registered
            // logit prepare/commit boundary.  Maximum positive and negative
            // signed-20 accumulators exceed the task-one analytical bounds on
            // purpose and must saturate to the two INT32 rails after their
            // exact left shifts.  The following commit check then forces equal
            // prepared logits to prove an exact tie selects Safe.
            reset_design();
            @(negedge clk);
            force dut.pool_classifier.state = 3'd6;
            force dut.pool_classifier.classifier_accumulator[0] = 20'sh7ffff;
            force dut.pool_classifier.classifier_accumulator[1] = 20'sh80000;
            @(posedge clk);
            #0.01;
            if (($signed(dut.pool_classifier.prepared_safe_logit)
                 !== 32'sh7fffffff)
                || ($signed(dut.pool_classifier.prepared_critical_logit)
                    !== 32'sh80000000))
                fail("classifier prepare did not saturate both INT32 rails");
            release dut.pool_classifier.classifier_accumulator[0];
            release dut.pool_classifier.classifier_accumulator[1];

            @(negedge clk);
            force dut.pool_classifier.state = 3'd7;
            force dut.pool_classifier.prepared_safe_logit = 32'sd123456;
            force dut.pool_classifier.prepared_critical_logit = 32'sd123456;
            @(posedge clk);
            #0.01;
            if ((safe_critical_decision !== 1'b0)
                || ($signed(logit_difference) !== 33'sd0))
                fail("classifier exact tie did not commit a Safe decision");
            release dut.pool_classifier.prepared_safe_logit;
            release dut.pool_classifier.prepared_critical_logit;
            release dut.pool_classifier.state;
            reset_design();
            $display("PASS_SPECIAL classifier_saturation_and_exact_tie");
        end
    endtask

    task automatic test_same_cycle_sample_and_request;
        begin
            // special record zero is the expected window [15 x31, 32].  The
            // live buffer is first filled with 32 fifteens; code 32 and request
            // then share an edge.  The snapshot is stored in physical order,
            // so its logical endpoint is slot snapshot_base+31 modulo 32.
            read_special_record();
            if (vector_name != "same_cycle")
                fail("special record order changed before same-cycle test");
            reset_design();
            for (code_index = 0; code_index < 32; code_index = code_index + 1)
                vector_codes[code_index] = 6'd15;
            load_vector_window();
            @(negedge clk);
            sensor_code = 6'd32;
            sample_valid = 1'b1;
            inference_request = 1'b1;
            if (!inference_ready)
                fail("full window was not ready for same-cycle sample/request");
            @(posedge clk);
            #0.01;
            if (!dut.snapshot_start
                || (dut.snapshot[dut.snapshot_base + 5'd31] != 6'd32))
                fail("same-cycle accepted sample was not the snapshot endpoint");
            monitor_active_inference(32, 0, 0, 0, 0, 1);
            $display("PASS_SPECIAL same_cycle_sample_request");
        end
    endtask

    task automatic test_earliest_second_request;
        longint first_request_time;
        longint second_request_time;
        begin
            // First result uses all-fifteen.  Every busy cycle accepts zero,
            // leaving an all-zero live L32 window.  The second request is
            // asserted on the first negedge after result and must be accepted
            // exactly 12,893 rising edges after the first request.
            read_special_record();
            if (vector_name != "all_fifteen")
                fail("special record order changed before II test");
            reset_design();
            load_vector_window();
            @(negedge clk);
            inference_request = 1'b1;
            sample_valid = 1'b0;
            @(posedge clk);
            #0.01;
            first_request_time = $time;
            monitor_active_inference(31, 0, 1, 0, 0, 0);

            read_special_record();
            if (vector_name != "all_zero")
                fail("special record order changed before second II result");
            @(negedge clk);
            sample_valid = 1'b0;
            inference_request = 1'b1;
            if (!inference_ready)
                fail("earliest second request did not see inference_ready");
            @(posedge clk);
            #0.01;
            second_request_time = $time;
            if (((second_request_time - first_request_time) / 4) != 12893)
                fail("release initiation interval is not exactly 12893 cycles");
            // The first accepted window ends at index 31.  Exactly one legal
            // sample transfers on every one of its 12,892 compute cycles, so
            // the live window captured by the earliest second request ends at
            // 31 + 12,892 = 12,923.
            monitor_active_inference(12923, 0, 2, 0, 0, 1);
            $display("PASS_SPECIAL earliest_II_and_continuous_second_window");
        end
    endtask

    task automatic read_vector_and_tensors;
        begin
            scan_status = $fscanf(vectors_file, "%s", vector_name);
            if (scan_status != 1)
                fail("failed to read vector name");
            for (code_index = 0; code_index < 32; code_index = code_index + 1)
                scan_status = $fscanf(vectors_file, "%d", vector_codes[code_index]);
            scan_status = $fscanf(vectors_file, "%d %d %d %d", expected_safe,
                                  expected_critical, expected_difference,
                                  expected_decision);
            scan_status = $fscanf(tensors_file, "%s", tensor_name);
            if (tensor_name != vector_name)
                fail("vector and internal-tensor record ordering differ");
            for (check_index = 0; check_index < 576; check_index = check_index + 1)
                scan_status = $fscanf(tensors_file, "%d", expected_relu1[check_index]);
            for (check_index = 0; check_index < 576; check_index = check_index + 1)
                scan_status = $fscanf(tensors_file, "%d", expected_relu2[check_index]);
            for (check_index = 0; check_index < 576; check_index = check_index + 1)
                scan_status = $fscanf(tensors_file, "%d", expected_relu3[check_index]);
            for (check_index = 0; check_index < 54; check_index = check_index + 1)
                scan_status = $fscanf(tensors_file, "%d", expected_summary[check_index]);
            scan_status = $fscanf(tensors_file, "%d %d", expected_accumulator[0],
                                  expected_accumulator[1]);
        end
    endtask

    initial begin
        reset = 1'b1;
        sensor_code = 6'd0;
        sample_valid = 1'b0;
        inference_request = 1'b0;
        error_count = 0;
        vector_index = 0;

        if (!$value$plusargs("VECTORS=%s", vectors_path)
            || !$value$plusargs("TENSORS=%s", tensors_path)
            || !$value$plusargs("TRACE=%s", trace_path)
            || !$value$plusargs("SPECIAL=%s", special_path))
            $fatal(1, "VECTORS, TENSORS, TRACE, and SPECIAL plusargs are required");
        vectors_file = $fopen(vectors_path, "r");
        tensors_file = $fopen(tensors_path, "r");
        trace_file = $fopen(trace_path, "r");
        special_file = $fopen(special_path, "r");
        if (!vectors_file || !tensors_file || !trace_file || !special_file)
            $fatal(1, "failed to open generated verification data");
        scan_status = $fscanf(vectors_file, "%d", vector_count);
        scan_status = $fscanf(tensors_file, "%d", tensor_count);
        scan_status = $fscanf(trace_file, "%d", trace_count);
        scan_status = $fscanf(special_file, "%d", special_count);
        if ((vector_count != tensor_count) || (trace_count != 12892)
            || (special_count != 3))
            $fatal(1, "generated verification headers violate fixed contracts");

        // First verify error and reset behavior independently of CNN numerics.
        reset_design();
        @(negedge clk);
        sensor_code = 6'd63;
        sample_valid = 1'b1;
        #0.01;
        if (sample_ready)
            fail("illegal code 63 was reported ready");
        @(posedge clk);
        #0.01;
        if (!protocol_error)
            fail("illegal valid sample did not set protocol_error");
        $display("PASS_SPECIAL illegal_sensor_code_rejected");
        reset_design();

        // Every golden and directed vector receives a clean prefill, then
        // continuous unrelated future samples throughout inference.  The first
        // vector additionally checks every controller/address cycle and rejects
        // a deliberately injected request while busy.
        for (vector_index = 0; vector_index < vector_count;
             vector_index = vector_index + 1) begin
            read_vector_and_tensors();
            reset_design();
            load_vector_window();
            launch_loaded_window(31, (vector_index == 0), 0,
                                 (vector_index == 0));
            if ((vector_index == 0) && !protocol_error)
                fail("busy inference request did not set sticky protocol_error");
            if (vector_index == 0)
                $display("PASS_SPECIAL busy_request_rejected");
            $display("PASS_VECTOR %0d %s", vector_index, vector_name);
        end

        test_reset_interruption_and_recovery();
        test_same_cycle_sample_and_request();
        test_earliest_second_request();
        test_classifier_numeric_boundaries();

        if (error_count != 0)
            $fatal(1, "CNN RTL regression accumulated %0d errors", error_count);
        $display("CNN_MONITOR_REGRESSION_PASS vectors=%0d trace_cycles=%0d",
                 vector_count, trace_count);
        $finish;
    end
endmodule

`default_nettype wire
