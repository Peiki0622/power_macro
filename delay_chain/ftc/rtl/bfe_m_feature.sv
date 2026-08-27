// B-FE5 ARCH0 constant-weight feature extraction with two timing stages.
//
// P1 registers fifteen pairwise partial sums; P2 registers eight reduced
// partial sums; P3 registers the final M_FF.
// The mathematical equation remains M_FF=sum(i*q_ff[i]), i=0..29. There is no
// helper routine, multiplier, divider, lookup table, or inferred latch.
`timescale 1ns/1ps
`default_nettype none

module bfe_m_feature (
    // Thirty captured DFF bits in physical tap order.  q_ff_i[0] is retained
    // for the physical bank but has the mathematically defined zero weight.
    input  wire [29:0] q_ff_i,
    // Sole backend clock used by both feature pipeline registers.
    input  wire        clk_probe_i,
    // Active-high asynchronous reset for both feature pipeline registers.
    input  wire        reset_i,
    // Nine-bit registered weighted sum, range 0..435.
    output reg  [8:0]  m_ff_o
);
    integer i;
    // P1 pair sums and registered copies. Pair i covers taps 2i and 2i+1.
    reg [8:0] pair_d [0:14];
    reg [8:0] pair_q [0:14];
    // P2 reduction from registered pair sums to the final M_FF value.
    reg [8:0] level_two_d [0:7];
    reg [8:0] level_two_q [0:7];
    reg [8:0] level_three [0:3];
    reg [8:0] level_four [0:1];
    reg [8:0] final_sum_d;

    // Combinational work between P1/P2 registers. All nodes are nine bits;
    // every partial sum is bounded by the final maximum 435.
    always @* begin
        for (i = 0; i < 15; i = i + 1) begin
            if (q_ff_i[2*i])
                pair_d[i] = 2*i;
            else
                pair_d[i] = 9'd0;
            if (q_ff_i[2*i+1])
                pair_d[i] = pair_d[i] + (2*i+1);
        end
        for (i = 0; i < 7; i = i + 1)
            level_two_d[i] = pair_q[2*i] + pair_q[2*i+1];
        level_two_d[7] = pair_q[14];
        for (i = 0; i < 4; i = i + 1)
            level_three[i] = level_two_q[2*i] + level_two_q[2*i+1];
        level_four[0] = level_three[0] + level_three[1];
        level_four[1] = level_three[2] + level_three[3];
        final_sum_d = level_four[0] + level_four[1];
    end

    // P1/P2 state. Reset removes stale feature data before a new event epoch.
    always @(posedge clk_probe_i or posedge reset_i) begin
        if (reset_i) begin
            for (i = 0; i < 15; i = i + 1)
                pair_q[i] <= 9'd0;
            for (i = 0; i < 8; i = i + 1)
                level_two_q[i] <= 9'd0;
            m_ff_o <= 9'd0;
        end else begin
            for (i = 0; i < 15; i = i + 1)
                pair_q[i] <= pair_d[i];
            for (i = 0; i < 8; i = i + 1)
                level_two_q[i] <= level_two_d[i];
            m_ff_o <= final_sum_d;
        end
    end
endmodule

`default_nettype wire
