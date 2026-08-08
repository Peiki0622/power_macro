// Minimal decoder replay testbench.
//
// raw_q.mem is generated from retained HSPICE raw Q words.  Each line is
// reversed before writing so packed SV bit zero remains the earliest physical
// stage, exactly matching phase3_decoder's documented bit ordering.
`timescale 1ns/1ps
`default_nettype none

`ifndef PHASE3_VECTOR_COUNT
`define PHASE3_VECTOR_COUNT 1
`endif

module phase3_decoder_replay_tb;
    parameter integer VECTOR_COUNT = `PHASE3_VECTOR_COUNT;

    logic clk_i;
    logic rst_i;
    logic capture_enable_i;
    logic [31:0] raw_thermometer_i;
    wire [31:0] raw_thermometer_o;
    wire [31:0] normalized_thermometer_o;
    wire [31:0] corrected_thermometer_o;
    wire [5:0] sensor_code_o;
    wire [5:0] bubble_count_o;
    wire code_valid_o;
    wire sample_valid_o;
    logic [31:0] raw_vectors [0:VECTOR_COUNT-1];
    integer vector_index;

    phase3_decoder u_decoder (
        .clk_i(clk_i), .rst_i(rst_i), .capture_enable_i(capture_enable_i),
        .raw_thermometer_i(raw_thermometer_i),
        .raw_thermometer_o(raw_thermometer_o),
        .normalized_thermometer_o(normalized_thermometer_o),
        .corrected_thermometer_o(corrected_thermometer_o),
        .sensor_code_o(sensor_code_o), .bubble_count_o(bubble_count_o),
        .code_valid_o(code_valid_o), .sample_valid_o(sample_valid_o)
    );

    always #5 clk_i = ~clk_i;

    initial begin
        $readmemb("raw_q.mem", raw_vectors);
        clk_i = 1'b0;
        rst_i = 1'b1;
        capture_enable_i = 1'b0;
        raw_thermometer_i = '0;
        #12;
        rst_i = 1'b0;
        for (vector_index = 0; vector_index < VECTOR_COUNT; vector_index = vector_index + 1) begin
            raw_thermometer_i = raw_vectors[vector_index];
            capture_enable_i = 1'b1;
            @(posedge clk_i);
            #1;
            $display("CASE %0d raw=%032b normalized=%032b corrected=%032b code=%0d bubbles=%0d valid=%0d sample_valid=%0d",
                     vector_index, raw_thermometer_o, normalized_thermometer_o,
                     corrected_thermometer_o, sensor_code_o, bubble_count_o,
                     code_valid_o, sample_valid_o);
            capture_enable_i = 1'b0;
            @(posedge clk_i);
            #1;
        end
        $display("PHASE3_DECODER_REPLAY_PASS");
        $finish;
    end
endmodule

`default_nettype wire
