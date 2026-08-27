// B-FE5 RTL0 stage-view top.
//
// This module is retained solely as the reproducible RTL0 verification
// boundary.  RTL1 and later intentionally replace the temporary m_ff output
// with the frozen backend status interface in bfe_backend_top.  Keeping this
// stage view separate avoids widening the final macro interface while still
// allowing the RTL0 M-feature gate to observe its mathematically defined
// result.
`timescale 1ns/1ps
`default_nettype none

module bfe_backend_rtl0_top (
    // 30-bit safe-domain word presented to all transparent latches.
    input  wire [29:0] safe_d,
    // Common active-high LATQ transparency control for all 30 lanes.
    input  wire        latch_gate,
    // Common positive-edge capture/backend clock for all 30 DFFs.
    input  wire        clk_probe,
    // Common active-high asynchronous reset for all capture flops.
    input  wire        reset,
    // Nine-bit weighted feature result, range 0..435.
    output wire [8:0]  m_ff
);
    wire [29:0] q_ff;

    bfe_capture_bank u_capture_bank (
        .safe_d_i      (safe_d),
        .latch_gate_i  (latch_gate),
        .clk_probe_i   (clk_probe),
        .reset_i       (reset),
        .q_ff_o        (q_ff)
    );

    bfe_m_feature u_m_feature (
        .q_ff_i      (q_ff),
        .clk_probe_i (clk_probe),
        .reset_i     (reset),
        .m_ff_o      (m_ff)
    );
endmodule

`default_nettype wire
