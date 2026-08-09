// Elaboration-only harness for the full standalone FTC structural hierarchy.
`timescale 1ns/1ps
`default_nettype none
module ftc_sensor_elab_tb;
    logic s_clk_i, latch_gate_i, capture_clk_i, reset_i;
    supply1 VDD_A;
    supply0 VSS_A;
    wire [4:0] start_index_o, end_index_o, one_run_length_o;
    wire valid_o;
    ftc_sensor u_sensor (.s_clk_i(s_clk_i), .latch_gate_i(latch_gate_i), .capture_clk_i(capture_clk_i), .reset_i(reset_i), .VDD_A(VDD_A), .VSS_A(VSS_A), .start_index_o(start_index_o), .end_index_o(end_index_o), .one_run_length_o(one_run_length_o), .valid_o(valid_o));
    initial begin s_clk_i=0; latch_gate_i=0; capture_clk_i=0; reset_i=1; #1; reset_i=0; $display("FTC_SENSOR_ELAB_PASS"); $finish; end
endmodule
`default_nettype wire
