// Structural sampling-clock boundary for the FTC macro.
`timescale 1ns/1ps
`default_nettype none

module ftc_sampling_frontend (
    // s_clk_i is the externally generated FTC sampling edge.  The paper does
    // not disclose a gate-level sampling-clock generator, so this boundary
    // deliberately receives the real launch clock instead of inventing one.
    input  wire s_clk_i,
    // s_clk_o drives both Vt delay paths from exactly one common net.
    output wire s_clk_o
);
    // No buffer is inserted because characterization connected s_clk directly
    // to both selected initial chains.  This is a structural wire, not a delay model.
    assign s_clk_o = s_clk_i;
endmodule

`default_nettype wire
