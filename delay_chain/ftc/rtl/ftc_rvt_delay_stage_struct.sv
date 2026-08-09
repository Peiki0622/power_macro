// One real RVT non-inverting FTC delay stage.
`timescale 1ns/1ps
`default_nettype none

module ftc_rvt_delay_stage_struct (
    // Physical buffer input/output for one delay-chain stage.
    input wire a_i,
    output wire y_o,
    // Shared target-library supply and ground rails; no reference rail exists.
    inout wire VDD_A,
    inout wire VSS_A
);
    // Exact selected SMIC40LL RVT buffer wrapper; no behavioral delay is used.
    BUF_X0P7M_A9TR40 u_rvt_buffer (.Y(y_o), .VDD(VDD_A), .VSS(VSS_A), .A(a_i));
endmodule

`default_nettype wire
