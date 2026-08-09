// Synthesizable FTC 30-bit bubble-repaired longest-one-run encoder.
//
// Physical stage zero is packed in captured_xor_word_i[0].  This matches the
// stage-ascending HSPICE CSV convention used by the characterization scripts:
// the first printed CSV character is stage zero, while a SystemVerilog binary
// literal prints bit 29 first.  Keeping this mapping explicit prevents a
// silent reversal of the FTC start/end indices.
`timescale 1ns/1ps
`default_nettype none

module ftc_longest_run_encoder (
    // Captured physical observation word.
    // captured_xor_word_i[0] is corresponding XOR/latch/FF stage 0 and
    // captured_xor_word_i[29] is stage 29.  The input is retained externally
    // by the structural capture bank; this combinational block never samples
    // it with another clock or changes its original evidence.
    input  logic [29:0] captured_xor_word_i,

    // Decode-observability output.
    // corrected_xor_word_o is the directional three-tap bubble-repaired word.
    // Only a 1-0-1 interior pattern changes its center zero to one; every
    // observed one, including a valid single-bit run, remains asserted.
    output logic [29:0] corrected_xor_word_o,

    // Primary FTC encoded result.
    // start_index_o and end_index_o are inclusive physical stage indices for
    // the longest corrected one-run.  Equal-length runs deterministically
    // retain the lower start index because the scan updates only on a strictly
    // longer candidate.  one_run_length_o is zero when valid_o is low.
    output logic [4:0]  start_index_o,
    output logic [4:0]  end_index_o,
    output logic [4:0]  one_run_length_o,
    output logic        valid_o,

    // Diagnostic output.
    // run_count_o counts all corrected contiguous one-runs.  bubble_count_o
    // counts isolated raw 1-0-1 zeros before repair, making the physical
    // captured word auditable even when the decoder closes that single bubble.
    output logic [4:0]  run_count_o,
    output logic [4:0]  bubble_count_o
);
    // All intermediate registers are fixed-width combinational hardware.
    // A 5-bit counter represents the complete 0..30 range without requiring
    // parameter-dependent widths or unsynthesizable dynamic storage.
    logic [4:0] current_start;
    logic [4:0] current_length;
    logic       previous_bit;
    integer     repair_index;
    integer     scan_index;

    // Directional three-tap repair is performed before run extraction.  The
    // endpoints are copied directly because a 30-stage line has no physical
    // neighbor beyond either end.  The loop has a constant 28-iteration bound
    // and therefore unrolls into ordinary combinational gates in synthesis.
    always_comb begin
        corrected_xor_word_o = captured_xor_word_i;
        bubble_count_o       = 5'd0;
        for (repair_index = 1; repair_index < 29; repair_index = repair_index + 1) begin
            if (captured_xor_word_i[repair_index - 1] &&
                !captured_xor_word_i[repair_index] &&
                captured_xor_word_i[repair_index + 1]) begin
                corrected_xor_word_o[repair_index] = 1'b1;
                bubble_count_o = bubble_count_o + 5'd1;
            end
        end
    end

    // Scan stage order from low index to high index and track one active run.
    // Strictly-greater replacement preserves the first, hence lowest-index,
    // candidate when two runs have the same maximum length.  No functions,
    // delays, or behavioral timing constructs are used in this synthesizable
    // implementation.
    always_comb begin
        start_index_o    = 5'd0;
        end_index_o      = 5'd0;
        one_run_length_o = 5'd0;
        run_count_o      = 5'd0;
        current_start    = 5'd0;
        current_length   = 5'd0;
        previous_bit     = 1'b0;
        for (scan_index = 0; scan_index < 30; scan_index = scan_index + 1) begin
            if (corrected_xor_word_o[scan_index]) begin
                if (!previous_bit) begin
                    current_start = scan_index[4:0];
                    current_length = 5'd0;
                    run_count_o = run_count_o + 5'd1;
                end
                current_length = current_length + 5'd1;
                if (current_length > one_run_length_o) begin
                    start_index_o = current_start;
                    end_index_o = scan_index[4:0];
                    one_run_length_o = current_length;
                end
                previous_bit = 1'b1;
            end else begin
                current_length = 5'd0;
                previous_bit = 1'b0;
            end
        end
        valid_o = (one_run_length_o != 5'd0);
    end
endmodule

`default_nettype wire
