// One same-index real XOR observation stage.
`timescale 1ns/1ps
`default_nettype none

module ftc_xor_stage_struct (
    // a_i is RVT tap i and b_i is LVT tap i.  The wrapper intentionally has
    // no index-offset interface, preventing an accidental Vernier topology.
    input wire a_i,
    input wire b_i,
    output wire y_o,
    // Single shared sensor rail pair used by the XOR cell.
    inout wire VDD_A,
    inout wire VSS_A
);
    XOR2_X0P5M_A9TR40 u_xor (.Y(y_o), .VDD(VDD_A), .VSS(VSS_A), .A(a_i), .B(b_i));
endmodule

`default_nettype wire
