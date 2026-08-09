// Complete synthesizable FTC-style RVT/LVT sensor structure.
`timescale 1ns/1ps
`default_nettype none

module ftc_sensor (
    // Common sampling launch clock.  It drives both delay lines through the
    // sampling boundary and is never split into independent source clocks.
    input wire s_clk_i,
    // Externally scheduled real-capture controls.  They make the target-process
    // 300 ps characterization choice explicit without unsynthesizable #delay.
    input wire latch_gate_i,
    input wire capture_clk_i,
    input wire reset_i,
    // Only FTC local supply rails exposed by the macro public interface.
    inout wire VDD_A,
    inout wire VSS_A,
    // Primary encoded output contract from the 30-bit captured XOR word.
    output wire [4:0] start_index_o,
    output wire [4:0] end_index_o,
    output wire [4:0] one_run_length_o,
    output wire valid_o
);
    import ftc_config_pkg::*;
    wire s_clk;
    wire [RVT_INITIAL_STAGES:0] rvt_initial;
    wire [LVT_INITIAL_STAGES:0] lvt_initial;
    wire [OBSERVABLE_STAGES-1:0] rvt_tap;
    wire [OBSERVABLE_STAGES-1:0] lvt_tap;
    wire [OBSERVABLE_STAGES-1:0] raw_xor_word;
    wire [OBSERVABLE_STAGES-1:0] captured_xor_word;
    wire [OBSERVABLE_STAGES-1:0] corrected_xor_word_unused;
    wire [4:0] run_count_unused;
    wire [4:0] bubble_count_unused;
    genvar stage;

    ftc_sampling_frontend u_sampling_frontend (.s_clk_i(s_clk_i), .s_clk_o(s_clk));
    assign rvt_initial[0] = s_clk;
    assign lvt_initial[0] = s_clk;

    // Initial chains position the fixed 30-stage observable regions.  Their
    // counts are selected physical constants, not runtime sparse masks.
    generate
        for (stage = 0; stage < RVT_INITIAL_STAGES; stage = stage + 1) begin : g_rvt_initial
            ftc_rvt_delay_stage_struct u_stage (.a_i(rvt_initial[stage]), .y_o(rvt_initial[stage + 1]), .VDD_A(VDD_A), .VSS_A(VSS_A));
        end
        for (stage = 0; stage < OBSERVABLE_STAGES; stage = stage + 1) begin : g_rvt_observable
            if (stage == 0) begin
                ftc_rvt_delay_stage_struct u_stage (.a_i(rvt_initial[RVT_INITIAL_STAGES]), .y_o(rvt_tap[stage]), .VDD_A(VDD_A), .VSS_A(VSS_A));
            end else begin
                ftc_rvt_delay_stage_struct u_stage (.a_i(rvt_tap[stage - 1]), .y_o(rvt_tap[stage]), .VDD_A(VDD_A), .VSS_A(VSS_A));
            end
        end
        for (stage = 0; stage < OBSERVABLE_STAGES; stage = stage + 1) begin : g_lvt_observable
            if (stage == 0) begin
                ftc_lvt_delay_stage_struct u_stage (.a_i(lvt_initial[LVT_INITIAL_STAGES]), .y_o(lvt_tap[stage]), .VDD_A(VDD_A), .VSS_A(VSS_A));
            end else begin
                ftc_lvt_delay_stage_struct u_stage (.a_i(lvt_tap[stage - 1]), .y_o(lvt_tap[stage]), .VDD_A(VDD_A), .VSS_A(VSS_A));
            end
        end
        // Each generate index feeds only its corresponding-tap XOR and capture.
        for (stage = 0; stage < OBSERVABLE_STAGES; stage = stage + 1) begin : g_observation_capture
            ftc_xor_stage_struct u_xor (.a_i(rvt_tap[stage]), .b_i(lvt_tap[stage]), .y_o(raw_xor_word[stage]), .VDD_A(VDD_A), .VSS_A(VSS_A));
            ftc_capture_struct u_capture (.d_i(raw_xor_word[stage]), .latch_gate_i(latch_gate_i), .capture_clk_i(capture_clk_i), .reset_i(reset_i), .q_o(captured_xor_word[stage]), .VDD_A(VDD_A), .VSS_A(VSS_A));
        end
    endgenerate

    ftc_longest_run_encoder u_encoder (.captured_xor_word_i(captured_xor_word), .corrected_xor_word_o(corrected_xor_word_unused), .start_index_o(start_index_o), .end_index_o(end_index_o), .one_run_length_o(one_run_length_o), .valid_o(valid_o), .run_count_o(run_count_unused), .bubble_count_o(bubble_count_unused));
endmodule

`default_nettype wire
