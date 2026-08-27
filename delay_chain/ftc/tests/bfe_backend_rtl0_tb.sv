// RTL0 self-checking VCS testbench.
//
// This bench drives the public RTL0 inputs and observes only the functional
// M result.  The capture bank's q_ff remains an internal implementation net;
// no test-only RTL port is added to expose it.
`timescale 1ns/1ps
`default_nettype none

module bfe_backend_rtl0_tb;
    reg  [29:0] safe_d;
    reg         latch_gate;
    reg         clk_probe;
    reg         reset;
    wire [8:0]  m_ff;
    integer    expected;
    integer    k;
    integer    bit_index;

    bfe_backend_rtl0_top dut (
        .safe_d     (safe_d),
        .latch_gate (latch_gate),
        .clk_probe  (clk_probe),
        .reset      (reset),
        .m_ff       (m_ff)
    );

    // Capture one vector through the actual LATQ->DFF structure, then check
    // the weighted result.  The latch is first opened to transfer safe_d,
    // closed to freeze the data, and finally sampled by one probe-clock edge.
    task automatic capture_and_check;
        input [29:0] vector;
        input integer golden;
        begin
            safe_d = vector;
            latch_gate = 1'b1;
            #1;
            latch_gate = 1'b0;
            #1;
            // E0 captures q_ff, E1 registers pair sums, and E2 registers
            // M_FF.  Check only after all three edges.
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            if (m_ff !== golden[8:0]) begin
                $fatal(1, "RTL0 M mismatch vector=%b expected=%0d got=%0d", vector, golden, m_ff);
            end
        end
    endtask

    initial begin
        safe_d = 30'd0;
        latch_gate = 1'b0;
        clk_probe = 1'b0;
        reset = 1'b1;
        #1;
        reset = 1'b0;

        capture_and_check(30'b0, 0);
        // Hex literals make the physical bit index explicit: bit 1 is 0x2,
        // bit 29 is 0x20000000, and all thirty legal bits are 0x3fffffff.
        capture_and_check(30'h00000002, 1);
        capture_and_check(30'h20000000, 29);
        capture_and_check(30'h3fffffff, 435);

        // Deterministic pseudo-random regression vectors.  The golden value
        // is calculated in the testbench only; no software-like helper is
        // present in synthesis RTL.
        for (k = 0; k < 32; k = k + 1) begin
            safe_d = (30'h15555555 ^ (30'h03a5c17 + k * 30'h0012345)) & 30'h3fffffff;
            expected = 0;
            for (bit_index = 0; bit_index < 30; bit_index = bit_index + 1) begin
                if (safe_d[bit_index]) expected = expected + bit_index;
            end
            // Reuse the capture sequence without a second task argument
            // variable so the vector is checked at the real bank boundary.
            latch_gate = 1'b1; #1; latch_gate = 1'b0; #1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            clk_probe = 1'b1; #1; clk_probe = 1'b0; #1;
            if (m_ff !== expected[8:0]) $fatal(1, "RTL0 random mismatch");
        end

        $display("BFE5_RTL0_CAPTURE_M_BACKEND_PASS");
        $finish;
    end
endmodule

`default_nettype wire
