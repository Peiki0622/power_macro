// Real FTC transparent-latch followed by post-latch FF capture stage.
`timescale 1ns/1ps
`default_nettype none

module ftc_capture_struct (
    // d_i is one physical XOR output.  latch_gate_i is active high for the
    // selected LATQ cell; capture_clk_i rises after the externally scheduled
    // latch close.  reset_i is the selected DFF's active-high async clear.
    input wire d_i,
    input wire latch_gate_i,
    input wire capture_clk_i,
    input wire reset_i,
    // q_o is the retained FF capture delivered to the longest-run encoder.
    output wire q_o,
    // All sequential cells share the one local sensor power pair.
    inout wire VDD_A,
    inout wire VSS_A
);
    wire latch_q;
    LATQ_X0P5M_A9TR40 u_latch (.Q(latch_q), .VDD(VDD_A), .VSS(VSS_A), .D(d_i), .G(latch_gate_i));
    DFFRPQ_X0P5M_A9TR40 u_ff (.Q(q_o), .VDD(VDD_A), .VSS(VSS_A), .CK(capture_clk_i), .D(latch_q), .R(reset_i));
endmodule

`default_nettype wire
