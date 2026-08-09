// Power-aware behavioral stubs used only for FTC VCS elaboration and replay.
// They match the selected vendor Verilog port contracts; SPICE remains the
// physical source of timing evidence and these modules are never synthesis RTL.
`timescale 1ns/1ps
`default_nettype none
module BUF_X0P7M_A9TR40(output wire Y, inout wire VDD, inout wire VSS, input wire A); assign Y = (VDD === 1'b1 && VSS === 1'b0) ? A : 1'bx; endmodule
module BUF_X0P7M_A9TL40(output wire Y, inout wire VDD, inout wire VSS, input wire A); assign Y = (VDD === 1'b1 && VSS === 1'b0) ? A : 1'bx; endmodule
module XOR2_X0P5M_A9TR40(output wire Y, inout wire VDD, inout wire VSS, input wire A, input wire B); assign Y = (VDD === 1'b1 && VSS === 1'b0) ? (A ^ B) : 1'bx; endmodule
module LATQ_X0P5M_A9TR40(output logic Q, inout wire VDD, inout wire VSS, input wire D, input wire G); always @* if (VDD === 1'b1 && VSS === 1'b0 && G) Q = D; endmodule
module DFFRPQ_X0P5M_A9TR40(output logic Q, inout wire VDD, inout wire VSS, input wire CK, input wire D, input wire R); always @(posedge CK or posedge R) if (R) Q <= 1'b0; else if (VDD === 1'b1 && VSS === 1'b0) Q <= D; else Q <= 1'bx; endmodule
`default_nettype wire
