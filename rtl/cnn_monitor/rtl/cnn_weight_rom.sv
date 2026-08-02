`default_nettype none

// One-cycle synchronous-read adapter for the SMIC40LL CNNW384X128 macro.
//
// The adapter deliberately contains only hard-macro wiring and one valid
// register.  Address and CEN are presented before the rising edge; the macro
// updates Q on that edge and the consumer uses q_valid during the following
// cycle.  Test, repair, power-gating, and margin pins are tied to the normal
// functional values documented in smic40ll_rom_config_v1.json.  No procedural
// memory, initialization file, procedural helper, or data-dependent control is present,
// so synthesis sees a single library memory cell instead of a register array.
module cnn_weight_rom (
    // Clock and reset group.
    input  logic         clk,             // Rising-edge synchronous ROM clock.
    input  logic         reset,           // Active-high asynchronous reset for q_valid only.

    // Read request group.
    input  logic         read_enable,     // High before clk to request one ROM word.
    input  logic [8:0]   read_address,    // 0..383 physical word address.

    // Synchronous response group.
    output logic         q_valid,         // One-cycle response marker for the preceding request.
    output logic [127:0] weight_word     // Macro Q bus; lane zero is bits [7:0].
);
    // The compiler's legacy Verilog model drives Q through one continuous
    // assignment per bit.  A net receiver preserves that multi-driver net
    // semantics in VCS; the synthesized hard macro connection is unchanged.
    wire [127:0] macro_q;

    // The compiler model and Liberty cell use the same active-low CEN
    // convention.  Holding test controls at benign constants prevents an
    // unconnected test pin from becoming an X source in gate simulation.
    CNNW384X128 u_weight_rom (
        .CENY(),
        .AY(),
        .Q(macro_q),
        .CLK(clk),
        .CEN(~read_enable),
        .A(read_address),
        .EMA(3'b010),
        .TEN(1'b1),
        .BEN(1'b1),
        .TCEN(1'b1),
        .TA(9'd0),
        .TQ(128'd0),
        .PGEN(1'b0),
        .KEN(1'b1)
    );

    // The macro Q bus is already a registered synchronous output.  q_valid is
    // separately registered so the controller can use it as an explicit
    // pipeline token without sampling an uninitialized response after reset.
    always_ff @(posedge clk or posedge reset) begin
        if (reset)
            q_valid <= 1'b0;
        else
            q_valid <= read_enable;
    end

    // The r1p1 compiler model has a VCS W-2024.09 compatibility defect in the
    // per-bit continuous assignments that drive public Q: its internal
    // synchronous Q_ bus is correct, while public Q remains X.  Full compiler-
    // model regressions therefore define CNN_ROM_COMPILER_MODEL and read
    // that internal bus.  This branch contains no replacement memory and still
    // exercises the delivered decoder, RCF, control checks, and synchronous
    // timing behavior.  Synthesis does not define the symbol and consequently
    // sees only the public library pin connection below.
`ifdef CNN_ROM_COMPILER_MODEL
    assign weight_word = u_weight_rom.Q_;
`else
    assign weight_word = macro_q;
`endif
endmodule

`default_nettype wire
