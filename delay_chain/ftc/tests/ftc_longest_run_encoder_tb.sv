// Synthetic contract testbench for the standalone FTC longest-one encoder.
//
// This is verification-only code, not synthesizable sensor RTL.  Each test
// assigns physical stage i to packed bit i, exactly as documented by the
// encoder and the compact HSPICE evidence.  No SPICE simulation is launched.
`timescale 1ns/1ps
`default_nettype none

module ftc_longest_run_encoder_tb;
    // Testbench drive for the 30 physical captured XOR/FF bits.
    logic [29:0] captured_xor_word_i;

    // Observed DUT result signals, split into retained corrected evidence,
    // primary FTC start/end/length/valid data, and run/bubble diagnostics.
    wire [29:0] corrected_xor_word_o;
    wire [4:0]  start_index_o;
    wire [4:0]  end_index_o;
    wire [4:0]  one_run_length_o;
    wire        valid_o;
    wire [4:0]  run_count_o;
    wire [4:0]  bubble_count_o;
    integer     failure_count;

    ftc_longest_run_encoder u_dut (
        .captured_xor_word_i(captured_xor_word_i),
        .corrected_xor_word_o(corrected_xor_word_o),
        .start_index_o(start_index_o), .end_index_o(end_index_o),
        .one_run_length_o(one_run_length_o), .valid_o(valid_o),
        .run_count_o(run_count_o), .bubble_count_o(bubble_count_o)
    );

    // Check one settled combinational vector against its complete public
    // encoder contract.  The task makes each of the nine required patterns
    // concise while still reporting the exact mismatching result if VCS finds
    // a behavioral regression.
    task automatic check_case(
        input [8*24-1:0] case_name,
        input logic [4:0] expected_start,
        input logic [4:0] expected_end,
        input logic [4:0] expected_length,
        input logic expected_valid,
        input logic [4:0] expected_runs,
        input logic [4:0] expected_bubbles
    );
        begin
            #1;
            if ((start_index_o !== expected_start) ||
                (end_index_o !== expected_end) ||
                (one_run_length_o !== expected_length) ||
                (valid_o !== expected_valid) ||
                (run_count_o !== expected_runs) ||
                (bubble_count_o !== expected_bubbles)) begin
                $display("FTC_ENCODER_FAIL case=%0s raw=%030b corrected=%030b got=%0d,%0d,%0d,%0d,%0d,%0d expected=%0d,%0d,%0d,%0d,%0d,%0d",
                    case_name, captured_xor_word_i, corrected_xor_word_o,
                    start_index_o, end_index_o, one_run_length_o, valid_o, run_count_o, bubble_count_o,
                    expected_start, expected_end, expected_length, expected_valid, expected_runs, expected_bubbles);
                failure_count = failure_count + 1;
            end
        end
    endtask

    initial begin
        failure_count = 0;

        // One clean internal run.
        captured_xor_word_i = '0; captured_xor_word_i[10:5] = '1;
        check_case("clean_internal", 5, 10, 6, 1, 1, 0);
        // A legal one-bit run must not be removed by bubble repair.
        captured_xor_word_i = '0; captured_xor_word_i[12] = 1'b1;
        check_case("single_bit", 12, 12, 1, 1, 1, 0);
        // Left and right line endpoints remain observable as ordinary runs.
        captured_xor_word_i = '0; captured_xor_word_i[3:0] = '1;
        check_case("left_boundary", 0, 3, 4, 1, 1, 0);
        captured_xor_word_i = '0; captured_xor_word_i[29:26] = '1;
        check_case("right_boundary", 26, 29, 4, 1, 1, 0);
        // Empty and full words define both extrema of the encoder range.
        captured_xor_word_i = '0;
        check_case("all_zeros", 0, 0, 0, 0, 0, 0);
        captured_xor_word_i = '1;
        check_case("all_ones", 0, 29, 30, 1, 1, 0);
        // The 1-0-1 raw bubble is closed before longest-run extraction.
        captured_xor_word_i = '0; captured_xor_word_i[7:4] = '1; captured_xor_word_i[5] = 1'b0;
        check_case("single_bubble", 4, 7, 4, 1, 1, 1);
        // Longer unequal run wins even when it occurs later in the chain.
        captured_xor_word_i = '0; captured_xor_word_i[3:2] = '1; captured_xor_word_i[18:14] = '1;
        check_case("unequal_runs", 14, 18, 5, 1, 2, 0);
        // Equal run lengths retain the lower start index by contract.
        captured_xor_word_i = '0; captured_xor_word_i[4:2] = '1; captured_xor_word_i[14:12] = '1;
        check_case("equal_runs_low_tie", 2, 4, 3, 1, 2, 0);

        if (failure_count != 0) begin
            $fatal(1, "FTC encoder contract failures=%0d", failure_count);
        end
        $display("FTC_ENCODER_UNIT_PASS cases=9");
        $finish;
    end
endmodule

`default_nettype wire
