// Trace-driven RTL verification for the FTC static calibration controller.
//
// This is verification-only code.  It reads all 54 retained r2 real-DFF Q
// records published in calibration_trace.csv, checks their physical ordering
// and expected boundaries, then drives the controller with each trace's
// required Q transactions.  Four synthetic boundary cases additionally prove
// that a lock at code 0, 6, or 7 and an all-high scan through code 7 fail.
`timescale 1ns/1ps
`default_nettype none

module ftc_static_calibration_controller_tb;
    // Digital controller drive signals.  probe_done_i and q_compare_i model
    // only the already-measured comparator result handshake; no analogue or
    // delay model is introduced in this RTL testbench.
    logic       clk_i;
    logic       reset_i;
    logic       start_i;
    logic       probe_done_i;
    logic       q_compare_i;

    // DUT-observed command and result signals.  code_o is checked at every
    // physical trace response, while lock/done/fault are checked per run.
    wire        probe_req_o;
    wire [2:0]  code_o;
    wire [2:0]  lock_code_o;
    wire        done_o;
    wire        fault_o;

    // All 54 CSV rows are retained in testbench storage.  The raw timing and
    // annotation columns are parsed as well as Q so a malformed trace schema
    // cannot be hidden by a test that consumes only a short prefix.
    real        trace_vdd_v [0:53];
    integer     trace_step_index [0:53];
    integer     trace_code [0:53];
    integer     trace_selected_tap [0:53];
    integer     trace_q [0:53];
    real        trace_delay_ps [0:53];
    real        trace_width_ps [0:53];
    integer     trace_is_lock [0:53];
    integer     trace_headroom_verified [0:53];

    integer     trace_count;
    integer     trace_fd;
    integer     scan_count;
    integer     failure_count;
    integer     row_index;
    integer     group_index;
    integer     group_start;
    integer     group_rows;
    integer     group_lock_code;
    integer     expected_lock_code [0:6];
    integer     expected_group_start [0:6];
    string      trace_path;
    string      header_line;

    ftc_static_calibration_controller u_dut (
        // Clock/reset and explicit startup command.
        .clk_i(clk_i),
        .reset_i(reset_i),
        .start_i(start_i),
        // Completed physical-probe response handshake.
        .probe_done_i(probe_done_i),
        .q_compare_i(q_compare_i),
        // Threshold-programming request interface.
        .probe_req_o(probe_req_o),
        .code_o(code_o),
        // Sticky static-calibration result interface.
        .lock_code_o(lock_code_o),
        .done_o(done_o),
        .fault_o(fault_o)
    );

    // A fixed digital clock is sufficient because the DUT has no analogue
    // timing behavior.  Physical settling remains represented by the distinct
    // SETTLE state and the explicit probe completion handshake below.
    always #5 clk_i = ~clk_i;

    // Return the DUT to its documented clean startup state between independent
    // voltage traces and synthetic boundary cases.  The asynchronous reset is
    // also sampled across two clock edges before any new start command.
    task automatic apply_reset;
        begin
            reset_i = 1'b1;
            start_i = 1'b0;
            probe_done_i = 1'b0;
            q_compare_i = 1'b0;
            repeat (2) @(posedge clk_i);
            reset_i = 1'b0;
            @(negedge clk_i);
        end
    endtask

    // Deliver one completed comparator result only after the DUT explicitly
    // requests a probe.  The result remains asserted through the entire
    // WAIT_RESULT sampling cycle, then is removed before the next operation;
    // this verifies that the controller does not depend on a combinational or
    // same-cycle response.
    task automatic respond_to_probe(
        input integer expected_code,
        input integer response_q
    );
        begin
            wait (probe_req_o === 1'b1);
            if (code_o !== expected_code[2:0]) begin
                $display("FTC_CAL_FAIL code got=%0d expected=%0d", code_o, expected_code);
                failure_count = failure_count + 1;
            end
            @(negedge clk_i);
            q_compare_i = response_q[0];
            probe_done_i = 1'b1;
            @(posedge clk_i);
            @(posedge clk_i);
            @(negedge clk_i);
            probe_done_i = 1'b0;
            q_compare_i = 1'b0;
        end
    endtask

    // Start one calibration only from IDLE.  The start pulse is held across a
    // rising edge and then removed before the first SETTLE-to-PROBE transition.
    task automatic start_calibration;
        begin
            start_i = 1'b1;
            @(posedge clk_i);
            @(negedge clk_i);
            start_i = 1'b0;
        end
    endtask

    // Drive the subset of each physical trace that a real linear scan reaches:
    // codes zero through the first zero.  The preceding trace-schema checks
    // below still validate all 54 records, including the measured headroom
    // probes which are intentionally not re-scanned after a hardware lock.
    task automatic run_physical_trace(
        input integer local_group,
        input integer local_start,
        input integer local_lock
    );
        integer local_code;
        begin
            apply_reset;
            start_calibration;
            for (local_code = 0; local_code <= local_lock; local_code = local_code + 1) begin
                respond_to_probe(trace_code[local_start + local_code], trace_q[local_start + local_code]);
            end
            @(negedge clk_i);
            if (!done_o || fault_o || (lock_code_o !== local_lock[2:0])) begin
                $display("FTC_CAL_FAIL trace_group=%0d done=%0b fault=%0b lock=%0d expected_lock=%0d",
                    local_group, done_o, fault_o, lock_code_o, local_lock);
                failure_count = failure_count + 1;
            end
        end
    endtask

    // A terminal FAULT must be observable and must not accidentally retain a
    // legal-looking lock code.  This common check is shared by the four fault
    // sequences but does not change any DUT behavior.
    task automatic check_fault(
        input [8*28-1:0] case_name
    );
        begin
            @(negedge clk_i);
            if (done_o || !fault_o || (lock_code_o !== 3'd0)) begin
                $display("FTC_CAL_FAIL fault_case=%0s done=%0b fault=%0b lock=%0d",
                    case_name, done_o, fault_o, lock_code_o);
                failure_count = failure_count + 1;
            end
        end
    endtask

    initial begin
        clk_i = 1'b0;
        reset_i = 1'b0;
        start_i = 1'b0;
        probe_done_i = 1'b0;
        q_compare_i = 1'b0;
        trace_count = 0;
        failure_count = 0;

        // The trace file is supplied as an absolute VCS plusarg by the Python
        // runner, keeping generated simulation files in a temporary run
        // directory while the immutable physical evidence stays in analysis/.
        if (!$value$plusargs("TRACE=%s", trace_path)) begin
            $fatal(1, "FTC_CAL_FAIL missing +TRACE=<calibration_trace.csv>");
        end
        trace_fd = $fopen(trace_path, "r");
        if (trace_fd == 0) begin
            $fatal(1, "FTC_CAL_FAIL cannot open trace=%0s", trace_path);
        end
        scan_count = $fgets(header_line, trace_fd);
        if (scan_count == 0) begin
            $fatal(1, "FTC_CAL_FAIL trace has no header");
        end
        while (!$feof(trace_fd) && (trace_count < 54)) begin
            scan_count = $fscanf(trace_fd, "%f,%d,%d,%d,%d,%f,%f,%d,%d\n",
                trace_vdd_v[trace_count], trace_step_index[trace_count],
                trace_code[trace_count], trace_selected_tap[trace_count],
                trace_q[trace_count], trace_delay_ps[trace_count],
                trace_width_ps[trace_count], trace_is_lock[trace_count],
                trace_headroom_verified[trace_count]);
            if (scan_count == 9) begin
                trace_count = trace_count + 1;
            end else if (!$feof(trace_fd)) begin
                $fatal(1, "FTC_CAL_FAIL malformed trace row index=%0d fields=%0d", trace_count, scan_count);
            end
        end
        $fclose(trace_fd);
        if ((trace_count != 54) || !$feof(trace_fd)) begin
            $fatal(1, "FTC_CAL_FAIL expected 54 trace rows got=%0d", trace_count);
        end

        // Validate all recorded rows before applying any stimulus.  The first
        // five physical VDD groups include code 7; the 1.05 and 1.10 V groups
        // end at verified headroom code 6 because their lock is code 4.
        expected_group_start[0] = 0;
        expected_group_start[1] = 8;
        expected_group_start[2] = 16;
        expected_group_start[3] = 24;
        expected_group_start[4] = 32;
        expected_group_start[5] = 40;
        expected_group_start[6] = 47;
        expected_lock_code[0] = 5;
        expected_lock_code[1] = 5;
        expected_lock_code[2] = 5;
        expected_lock_code[3] = 5;
        expected_lock_code[4] = 5;
        expected_lock_code[5] = 4;
        expected_lock_code[6] = 4;
        for (group_index = 0; group_index < 7; group_index = group_index + 1) begin
            group_start = expected_group_start[group_index];
            group_rows = (group_index < 5) ? 8 : 7;
            group_lock_code = expected_lock_code[group_index];
            for (row_index = 0; row_index < group_rows; row_index = row_index + 1) begin
                if ((trace_code[group_start + row_index] != row_index) ||
                    ((row_index < group_lock_code) && (trace_q[group_start + row_index] != 1)) ||
                    ((row_index >= group_lock_code) && (trace_q[group_start + row_index] != 0))) begin
                    $display("FTC_CAL_FAIL trace_schema group=%0d row=%0d code=%0d q=%0d",
                        group_index, row_index, trace_code[group_start + row_index], trace_q[group_start + row_index]);
                    failure_count = failure_count + 1;
                end
            end
            if ((trace_is_lock[group_start + group_lock_code] != 1) ||
                (trace_headroom_verified[group_start + group_lock_code + 2] != 1)) begin
                $display("FTC_CAL_FAIL trace_annotation group=%0d", group_index);
                failure_count = failure_count + 1;
            end
        end

        // Seven real-DFF traces drive the linear controller to its published
        // locks: 0.80 through 1.00 V lock at 5; 1.05 and 1.10 V lock at 4.
        for (group_index = 0; group_index < 7; group_index = group_index + 1) begin
            run_physical_trace(group_index, expected_group_start[group_index], expected_lock_code[group_index]);
        end

        // Explicit boundary failures: no valid calibration can lock at zero,
        // 6, or 7, and a still-high Q at 7 must fault instead of rolling over.
        apply_reset;
        start_calibration;
        respond_to_probe(0, 0);
        check_fault("zero_at_code0");

        apply_reset;
        start_calibration;
        for (row_index = 0; row_index < 6; row_index = row_index + 1) begin
            respond_to_probe(row_index, 1);
        end
        respond_to_probe(6, 0);
        check_fault("zero_at_code6");

        apply_reset;
        start_calibration;
        for (row_index = 0; row_index < 7; row_index = row_index + 1) begin
            respond_to_probe(row_index, 1);
        end
        respond_to_probe(7, 0);
        check_fault("zero_at_code7");

        apply_reset;
        start_calibration;
        for (row_index = 0; row_index < 8; row_index = row_index + 1) begin
            respond_to_probe(row_index, 1);
        end
        check_fault("high_through_code7");

        if (failure_count != 0) begin
            $fatal(1, "FTC_CAL_FAIL failures=%0d", failure_count);
        end
        $display("FTC_CAL_TRACE_PASS traces=7 rows=54 locks=5,5,5,5,5,4,4 fault_cases=4");
        $finish;
    end
endmodule

`default_nettype wire
